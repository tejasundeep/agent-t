import os
import sys
import json
import re
import time
import subprocess
import threading
import traceback
import datetime
from concurrent.futures import as_completed
from routines import get_db_connection
from concurrency import global_executor

# Global registry for active pipeline runs to allow cancellation
# run_id -> dict with: 'stop_event', 'active_subprocesses' (list of subprocess.Popen)
ACTIVE_RUNS = {}

def get_workspace_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workspace')

def interpolate_value(val, context):
    """Recursively interpolates {{variables.KEY}} and {{steps.STEP_ID.output}} inside val."""
    if isinstance(val, str):
        # Substitute {{variables.KEY}}
        def replace_var(match):
            key = match.group(1).strip()
            if key in context['variables']:
                return str(context['variables'][key])
            raise ValueError(f"Variable '{key}' is referenced but not defined in pipeline inputs.")
        
        val = re.sub(r"{{\s*variables\.([^}]+)\s*}}", replace_var, val)
        
        # Substitute {{steps.STEP_ID.output}}
        # Supports: steps.step_id.output (entire string/dict) or steps.step_id.output.key (nested)
        def replace_step_output(match):
            step_id = match.group(1).strip()
            field = match.group(2).strip() if match.group(2) else ""
            if step_id not in context['steps']:
                raise ValueError(f"Step '{step_id}' output is referenced before step execution or step did not run.")
            
            step_data = context['steps'][step_id]
            if step_data.get('status') != 'success':
                raise ValueError(f"Step '{step_id}' failed or did not finish successfully; output is unavailable.")
            
            output = step_data.get('output', "")
            if not field:
                return str(output)
            
            # If a subkey is requested (e.g. {{steps.step_id.output.sub_key}})
            try:
                # Try loading output as json if it is string
                if isinstance(output, str):
                    output_data = json.loads(output)
                else:
                    output_data = output
                
                # Fetch key
                field_parts = [p for p in field.split('.') if p]
                cur = output_data
                for part in field_parts:
                    if isinstance(cur, dict) and part in cur:
                        cur = cur[part]
                    else:
                        raise KeyError()
                return str(cur)
            except Exception:
                raise ValueError(f"Key '{field}' not found in step '{step_id}' output structure.")

        val = re.sub(r"{{\s*steps\.([a-zA-Z0-9_-]+)\.output(\.[a-zA-Z0-9_.-]+)?\s*}}", replace_step_output, val)
        return val
    elif isinstance(val, list):
        return [interpolate_value(item, context) for item in val]
    elif isinstance(val, dict):
        return {k: interpolate_value(v, context) for k, v in val.items()}
    return val

def resolve_arguments(args, context):
    """Safely resolves string and structured dictionary arguments with variable template resolution."""
    if not args:
        return args
    # If args is a JSON string, load it first
    is_str = isinstance(args, str)
    if is_str:
        try:
            parsed = json.loads(args)
            resolved = interpolate_value(parsed, context)
            return resolved
        except json.JSONDecodeError:
            # Not a JSON string, just interpolate as raw string
            return interpolate_value(args, context)
    else:
        return interpolate_value(args, context)

def execute_python_step(code, context):
    """Executes inline python code in an isolated scope containing pre-injected variables and returns output state."""
    # Build context dictionary
    scope = {
        'variables': context['variables'],
        'steps': {k: v.get('output') for k, v in context['steps'].items() if v.get('status') == 'success'}
    }
    
    # Capture standard outputs
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = sys_io = __import__("io").StringIO()
    sys.stderr = sys_err_io = __import__("io").StringIO()
    
    error = None
    try:
        exec(code, scope, scope)
    except Exception as e:
        error = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        
    stdout_val = sys_io.getvalue()
    stderr_val = sys_err_io.getvalue()
    
    if error:
        raise RuntimeError(f"Python script execution failed:\n{error}\nStdout:\n{stdout_val}\nStderr:\n{stderr_val}")
    
    # Return all locally defined non-private variables as step output dictionary
    user_vars = {k: v for k, v in scope.items() if not k.startswith("__") and k not in ('variables', 'steps')}
    user_vars['stdout'] = stdout_val
    user_vars['stderr'] = stderr_val
    return user_vars

class PipelineEngine:
    def __init__(self, socketio_emitter=None):
        self.socketio_emitter = socketio_emitter

    def _emit(self, event, data):
        if self.socketio_emitter:
            self.socketio_emitter(event, data)
        else:
            print(f"[Pipeline Event] {event}: {json.dumps(data)}")

    def run(self, pipeline_id, inputs=None):
        """Triggers and executes a pipeline execution DAG from start to finish."""
        inputs = inputs or {}
        now = datetime.datetime.now()
        
        # 1. Fetch Pipeline definition
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM pipelines WHERE id = ?", (pipeline_id,)).fetchone()
            if not row:
                raise ValueError(f"Pipeline with ID '{pipeline_id}' not found.")
            pipeline_name = row['name']
            definition = json.loads(row['definition'])
            
        steps = definition.get('steps', [])
        default_variables = definition.get('variables', {})
        
        # Combine default variables with run-time input variables
        run_variables = {}
        for k, v in default_variables.items():
            run_variables[k] = v
        for k, v in inputs.items():
            run_variables[k] = v
            
        # 2. Insert execution entry in SQLite
        with get_db_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO pipeline_runs (pipeline_id, status, inputs, triggered_at) VALUES (?, 'running', ?, ?)",
                (pipeline_id, json.dumps(run_variables), now.isoformat())
            )
            conn.commit()
            run_id = cursor.lastrowid
            
        # Register in ACTIVE_RUNS
        stop_event = threading.Event()
        ACTIVE_RUNS[run_id] = {
            'stop_event': stop_event,
            'active_subprocesses': [],
            'lock': threading.Lock()
        }
        
        self._emit('pipeline_status', {'run_id': run_id, 'status': 'running', 'pipeline_id': pipeline_id, 'name': pipeline_name})
        
        # Run in separate thread pool worker to avoid blocking Flask
        thread = threading.Thread(target=self._execute_pipeline_thread, args=(run_id, pipeline_name, steps, run_variables, stop_event))
        thread.start()
        
        return run_id

    def _execute_pipeline_thread(self, run_id, pipeline_name, steps, variables, stop_event):
        try:
            # 1. Map step configuration and DAG dependencies
            step_by_id = {s['id']: s for s in steps}
            dependency_graph = {s['id']: set(s.get('depends_on', [])) for s in steps}
            
            # Validate DAG and topological ordering
            ordered_steps = self._topological_sort(dependency_graph)
            
            # State context for outputs
            context = {
                'variables': variables,
                'steps': {} # step_id -> {status, output, error}
            }
            
            # Setup executor for parallel step execution
            executor = global_executor
            running_futures = {} # future -> step_id
            
            completed_steps = set()
            failed_steps = set()
            
            while len(completed_steps) + len(failed_steps) < len(steps):
                if stop_event.is_set():
                    # Handle cancellation
                    break
                
                # Check for steps that are ready to run (all dependencies in completed_steps)
                for step_id in ordered_steps:
                    if step_id in context['steps'] or step_id in running_futures.values():
                        continue
                        
                    deps = dependency_graph[step_id]
                    # If any dependency failed, mark this step as skipped/failed immediately
                    if any(d in failed_steps for d in deps):
                        # unless parent has continue_on_failure, check step settings
                        step_conf = step_by_id[step_id]
                        if not step_conf.get('continue_on_failure', False):
                            failed_steps.add(step_id)
                            context['steps'][step_id] = {'status': 'skipped', 'output': '', 'error': 'Dependency failed.'}
                            self._log_step(run_id, step_id, step_conf['name'], 'skipped', output='', error='Dependency failed.')
                            continue
                    
                    if deps.issubset(completed_steps):
                        # Ready to schedule
                        step_conf = step_by_id[step_id]
                        future = executor.submit(self._execute_step_wrapper, run_id, step_conf, context, stop_event)
                        running_futures[future] = step_id
                
                if not running_futures:
                    # No tasks running and none can be scheduled (circular/error state)
                    break
                    
                # Wait for any scheduled step to finish
                done_futures = []
                for fut in as_completed(running_futures, timeout=1.0):
                    done_futures.append(fut)
                    step_id = running_futures[fut]
                    try:
                        res = fut.result()
                        context['steps'][step_id] = res
                        if res['status'] == 'success':
                            completed_steps.add(step_id)
                        else:
                            failed_steps.add(step_id)
                    except Exception as e:
                        failed_steps.add(step_id)
                        context['steps'][step_id] = {'status': 'failed', 'output': '', 'error': str(e)}
                        
                for fut in done_futures:
                    del running_futures[fut]
            
            # Clean shutdown of executor is managed globally
            
            # Check final status
            final_status = 'completed'
            err_msg = None
            if stop_event.is_set():
                final_status = 'canceled'
                err_msg = 'Pipeline run canceled by user.'
            elif failed_steps:
                # If any failed step wasn't ignored by continue_on_failure
                unignored_failures = [step_id for step_id in failed_steps if not step_by_id[step_id].get('continue_on_failure', False)]
                if unignored_failures:
                    final_status = 'failed'
                    err_msg = f"Failed steps: {', '.join(unignored_failures)}"
                    
            # Finalize status in Database
            finished_at = datetime.datetime.now()
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE pipeline_runs SET status = ?, finished_at = ?, outputs = ?, error = ? WHERE id = ?",
                    (final_status, finished_at.isoformat(), json.dumps(context['steps']), err_msg, run_id)
                )
                conn.commit()
                
            self._emit('pipeline_complete', {
                'run_id': run_id,
                'status': final_status,
                'finished_at': finished_at.isoformat(),
                'error': err_msg,
                'outputs': context['steps']
            })
            
        except Exception as e:
            err_trace = traceback.format_exc()
            finished_at = datetime.datetime.now()
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE pipeline_runs SET status = 'failed', finished_at = ?, error = ? WHERE id = ?",
                    (finished_at.isoformat(), f"{e}\n{err_trace}", run_id)
                )
                conn.commit()
            self._emit('pipeline_complete', {
                'run_id': run_id,
                'status': 'failed',
                'finished_at': finished_at.isoformat(),
                'error': str(e)
            })
        finally:
            if run_id in ACTIVE_RUNS:
                del ACTIVE_RUNS[run_id]

    def _execute_step_wrapper(self, run_id, step, context, stop_event):
        """Wrapper for single step execution handling logging, retries, and errors."""
        step_id = step['id']
        name = step['name']
        retries = step.get('retry_count', 0)
        delay = step.get('retry_delay', 1)
        timeout = step.get('timeout', 300)
        
        # Log step started
        self._log_step(run_id, step_id, name, 'running')
        self._emit('pipeline_step_status', {'run_id': run_id, 'step_id': step_id, 'status': 'running'})
        
        attempt = 0
        last_error = ""
        while attempt <= retries:
            if stop_event.is_set():
                return {'status': 'canceled', 'output': '', 'error': 'Canceled'}
            
            try:
                # Perform parameter substitution/interpolation
                resolved_action = interpolate_value(step.get('action', ''), context)
                resolved_args = resolve_arguments(step.get('args', {}), context)
                
                # Execute depending on type
                output = self._run_step_action(step['type'], resolved_action, resolved_args, context, run_id, step_id, timeout, stop_event)
                
                # Success
                self._log_step_complete(run_id, step_id, 'success', output=str(output))
                self._emit('pipeline_step_status', {'run_id': run_id, 'step_id': step_id, 'status': 'success'})
                return {'status': 'success', 'output': output}
            except Exception as e:
                attempt += 1
                last_error = f"Attempt {attempt} failed: {e}\n{traceback.format_exc()}"
                self._emit('pipeline_step_log', {'run_id': run_id, 'step_id': step_id, 'log': f"Error: {last_error}"})
                if attempt <= retries:
                    time.sleep(delay)
                    
        # Failed all attempts
        status = 'failed'
        if step.get('continue_on_failure', False):
            status = 'success' # Treated as success to downstream dependencies if flagged
            
        self._log_step_complete(run_id, step_id, 'failed', error=last_error)
        self._emit('pipeline_step_status', {'run_id': run_id, 'step_id': step_id, 'status': 'failed'})
        return {'status': 'failed', 'output': '', 'error': last_error}

    def _run_step_action(self, step_type, action, args, context, run_id, step_id, timeout, stop_event):
        """Executes the action matching the step type."""
        if step_type == 'tool':
            from registry import registry
            if not registry:
                raise RuntimeError("Tools registry not available.")
            
            # Arguments resolving
            tool_args = args or {}
            if isinstance(tool_args, str):
                tool_args = json.loads(tool_args)
                
            self._emit('pipeline_step_log', {'run_id': run_id, 'step_id': step_id, 'log': f"Calling registry tool '{action}' with args: {json.dumps(tool_args)}"})
            res = registry.run(action, tool_args)
            return res
            
        elif step_type == 'python':
            self._emit('pipeline_step_log', {'run_id': run_id, 'step_id': step_id, 'log': f"Executing Python script block."})
            res = execute_python_step(action, context)
            return res
            
        elif step_type == 'shell':
            self._emit('pipeline_step_log', {'run_id': run_id, 'step_id': step_id, 'log': f"Executing shell command: {action}"})
            
            # Start process in workspace directory
            cwd = get_workspace_dir()
            proc = subprocess.Popen(
                action,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd
            )
            
            # Register process in ACTIVE_RUNS for termination if canceled
            if run_id in ACTIVE_RUNS:
                with ACTIVE_RUNS[run_id]['lock']:
                    ACTIVE_RUNS[run_id]['active_subprocesses'].append(proc)
                    
            try:
                # Dynamic logging output reading or simple communicate with timeout
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                raise RuntimeError(f"Command timed out after {timeout}s.")
            finally:
                if run_id in ACTIVE_RUNS:
                    with ACTIVE_RUNS[run_id]['lock']:
                        if proc in ACTIVE_RUNS[run_id]['active_subprocesses']:
                            ACTIVE_RUNS[run_id]['active_subprocesses'].remove(proc)
                            
            if proc.returncode != 0:
                raise RuntimeError(f"Process exited with code {proc.returncode}.\nStderr: {stderr}\nStdout: {stdout}")
                
            return {"stdout": stdout, "stderr": stderr, "exit_code": proc.returncode}
            
        elif step_type == 'prompt':
            from agent import Agent
            from config import SYSTEM_PROMPT
            
            self._emit('pipeline_step_log', {'run_id': run_id, 'step_id': step_id, 'log': f"Invoking Agent Prompt: {action}"})
            agent = Agent(SYSTEM_PROMPT)
            
            # Run prompt stream
            chunks = []
            for chunk in agent.stream(action):
                chunks.append(chunk)
                
            response = "".join(chunks)
            return response
            
        else:
            raise ValueError(f"Unsupported step type: {step_type}")

    def _log_step(self, run_id, step_id, step_name, status, output='', error=''):
        now = datetime.datetime.now().isoformat()
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO pipeline_run_logs (run_id, step_id, step_name, status, started_at, output, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, step_id, step_name, status, now, output, error)
            )
            conn.commit()

    def _log_step_complete(self, run_id, step_id, status, output='', error=''):
        now = datetime.datetime.now().isoformat()
        
        # Max log size limits to keep DB lightweight
        MAX_LOG_SIZE = 50 * 1024
        if len(output) > MAX_LOG_SIZE:
            output = output[-MAX_LOG_SIZE:] + "\n[Output truncated due to size limit]"
        if len(error) > MAX_LOG_SIZE:
            error = error[-MAX_LOG_SIZE:] + "\n[Error truncated due to size limit]"
            
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE pipeline_run_logs SET status = ?, finished_at = ?, output = ?, error = ? "
                "WHERE run_id = ? AND step_id = ?",
                (status, now, output, error, run_id, step_id)
            )
            conn.commit()

    def _topological_sort(self, graph):
        """Topological sort validation for Directed Acyclic Graph."""
        in_degree = {u: 0 for u in graph}
        for u in graph:
            for v in graph[u]:
                if v in in_degree:
                    in_degree[u] += 1
                    
        # Find sources (no dependencies)
        queue = [u for u in in_degree if in_degree[u] == 0]
        ordered = []
        
        while queue:
            u = queue.pop(0)
            ordered.append(u)
            
            # Decrease in-degree for nodes that depended on u
            for v in graph:
                if u in graph[v]:
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        queue.append(v)
                        
        if len(ordered) != len(graph):
            raise ValueError("Circular dependency detected in Pipeline steps configuration!")
            
        return ordered

def cancel_pipeline_run(run_id):
    """Safely aborts/cancels an active pipeline run by killing sub-processes and thread triggers."""
    if run_id not in ACTIVE_RUNS:
        return False
        
    run_ctx = ACTIVE_RUNS[run_id]
    run_ctx['stop_event'].set()
    
    # Kill any active subprocesses
    with run_ctx['lock']:
        for proc in run_ctx['active_subprocesses']:
            try:
                proc.terminate()
                time.sleep(0.5)
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
                
    return True

import json
import datetime
import sqlite3
from registry import tool
from routines import get_db_connection, init_db

@tool
def create_pipeline(id: str, name: str, description: str, definition_json: str):
    """Creates or updates a reusable pipeline.
    id: Unique ID for the pipeline (e.g. 'compile_and_test').
    name: Human-readable name (e.g. 'Build & Run Tests').
    description: Simple description of what it does.
    definition_json: JSON string defining variables and steps.
      Example structure:
      {
        "variables": { "branch": "main", "retries": 1 },
        "steps": [
          {
            "id": "fetch_code",
            "name": "Fetch Code",
            "type": "shell",
            "action": "git pull origin {{variables.branch}}"
          },
          {
            "id": "run_tests",
            "name": "Run unit tests",
            "type": "shell",
            "action": "pytest",
            "depends_on": ["fetch_code"]
          }
        ]
      }
    """
    init_db()
    try:
        # Validate JSON definition
        definition = json.loads(definition_json)
        if 'steps' not in definition:
            return "Error: definition must contain 'steps' list."
        for step in definition['steps']:
            if 'id' not in step or 'name' not in step or 'type' not in step:
                return "Error: each step must contain 'id', 'name', and 'type'."
            if step['type'] not in ('tool', 'python', 'shell', 'prompt'):
                return f"Error: step type '{step['type']}' is invalid. Supported types: 'tool', 'python', 'shell', 'prompt'."
    except Exception as e:
        return f"Error parsing definition JSON: {e}"

    now = datetime.datetime.now()
    try:
        with get_db_connection() as conn:
            # Check if exists to overwrite (upsert)
            cursor = conn.execute("SELECT id FROM pipelines WHERE id = ?", (id,))
            exists = cursor.fetchone()
            if exists:
                conn.execute(
                    "UPDATE pipelines SET name = ?, description = ?, definition = ? WHERE id = ?",
                    (name, description, json.dumps(definition), id)
                )
                action_word = "Updated"
            else:
                conn.execute(
                    "INSERT INTO pipelines (id, name, description, definition, created_at) VALUES (?, ?, ?, ?, ?)",
                    (id, name, description, json.dumps(definition), now.isoformat())
                )
                action_word = "Created"
            conn.commit()
        return f"Successfully {action_word.lower()} pipeline '{id}'."
    except Exception as e:
        return f"Error database transaction: {e}"

@tool
def run_pipeline(pipeline_id: str, inputs_json: str = "{}"):
    """Triggers and executes a pipeline DAG run asynchronously.
    pipeline_id: ID of the pipeline to run.
    inputs_json: JSON string of input variable values.
    """
    init_db()
    try:
        inputs = json.loads(inputs_json) if inputs_json else {}
    except Exception as e:
        return f"Error parsing inputs JSON: {e}"
        
    try:
        from pipeline_engine import PipelineEngine
        # Inject standard notification callback if wired in app.py
        # We can dynamically grab the socketio instance or callbacks
        from app import push_notification
        
        # Define a SocketIO broadcast emitter callback helper
        def socketio_emitter(event, data):
            try:
                from app import socketio
                socketio.emit(event, data)
                # If finished, push notification
                if event == 'pipeline_complete':
                    push_notification(
                        title=f"Pipeline Run #{data['run_id']} finished",
                        message=f"Status: {data['status']}",
                        level='info' if data['status'] == 'completed' else 'error'
                    )
            except Exception:
                pass
                
        engine = PipelineEngine(socketio_emitter=socketio_emitter)
        run_id = engine.run(pipeline_id, inputs)
        return f"Pipeline execution started. Run ID: {run_id}."
    except Exception as e:
        return f"Error starting pipeline run: {e}"

@tool
def cancel_pipeline(run_id: int):
    """Cancels/aborts an active pipeline run and kills any executing child processes.
    run_id: ID of the pipeline run.
    """
    try:
        from pipeline_engine import cancel_pipeline_run
        success = cancel_pipeline_run(int(run_id))
        if success:
            return f"Cancellation command sent to pipeline run #{run_id}."
            
        # Update run status in DB if it was found but not actively running in memory
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT status FROM pipeline_runs WHERE id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return f"Pipeline run #{run_id} not found."
            if row['status'] == 'running':
                conn.execute("UPDATE pipeline_runs SET status = 'canceled', finished_at = ? WHERE id = ?", (datetime.datetime.now().isoformat(), run_id))
                conn.commit()
                return f"Pipeline run #{run_id} marked as canceled in Database."
            return f"Pipeline run #{run_id} is already in status '{row['status']}'."
    except Exception as e:
        return f"Error: {e}"

@tool
def list_pipelines():
    """Lists all configured reusable pipelines."""
    init_db()
    try:
        with get_db_connection() as conn:
            rows = conn.execute("SELECT * FROM pipelines ORDER BY id ASC").fetchall()
            if not rows:
                return "No pipelines configured."
                
            output = ["Configured Pipelines:"]
            for r in rows:
                definition = json.loads(r['definition'])
                steps_count = len(definition.get('steps', []))
                desc = r['description'] or "No description"
                output.append(f"- {r['id']} | Name: {r['name']} | Steps: {steps_count} | {desc}")
            return "\n".join(output)
    except Exception as e:
        return f"Error: {e}"

@tool
def get_pipeline_run_logs(run_id: int):
    """Retrieves step-by-step logs and output state for a specific pipeline run.
    run_id: ID of the pipeline run.
    """
    init_db()
    try:
        with get_db_connection() as conn:
            run = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone()
            if not run:
                return f"Pipeline run #{run_id} not found."
                
            logs = conn.execute("SELECT * FROM pipeline_run_logs WHERE run_id = ? ORDER BY id ASC", (run_id,)).fetchall()
            
            output = [
                f"Pipeline Run #{run_id} Details:",
                f"Pipeline ID: {run['pipeline_id']}",
                f"Status: {run['status']}",
                f"Triggered: {run['triggered_at']}",
                f"Finished: {run['finished_at'] or 'N/A'}",
                f"Inputs: {run['inputs']}",
                f"Error: {run['error'] or 'None'}",
                "",
                "Step Logs:"
            ]
            
            for log in logs:
                duration = ""
                if log['finished_at']:
                    t1 = datetime.datetime.fromisoformat(log['started_at'])
                    t2 = datetime.datetime.fromisoformat(log['finished_at'])
                    duration = f" | Duration: {int((t2 - t1).total_seconds())}s"
                    
                output.append(f"--- Step: {log['step_id']} ({log['step_name']}) | Status: {log['status']}{duration} ---")
                if log['output']:
                    output.append(f"  Output:\n{log['output']}")
                if log['error']:
                    output.append(f"  Error:\n{log['error']}")
                    
            return "\n".join(output)
    except Exception as e:
        return f"Error: {e}"

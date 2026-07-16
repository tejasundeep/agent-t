sys_module = __import__("sys")
io_module = __import__("io")
traceback_module = __import__("traceback")
import threading
from registry import tool, registry

@tool
def python_interpreter(code: str):
    """Execute Python code in a stateful, persistent dictionary scope and return stdout/stderr or execution errors.
    Variable bindings, functions, and imports persist across multiple runs.
    Use ask_user(prompt) to prompt the user for input.
    """
    old_stdout = sys_module.stdout
    old_stderr = sys_module.stderr
    sys_module.stdout = io_module.StringIO()
    sys_module.stderr = io_module.StringIO()
    
    # Identify the execution session based on the current thread
    thread_name = threading.current_thread().name
    scope = registry.get_interpreter_scope(thread_name)
    
    try:
        # execute code within persistent thread scope
        exec(code, scope, scope)
        stdout_val = sys_module.stdout.getvalue()
        stderr_val = sys_module.stderr.getvalue()
        output = stdout_val + stderr_val
        if not output.strip():
            # If no prints, check if we can print the list of user-created variables
            user_vars = {k: v for k, v in scope.items() if not k.startswith("__") and k != "ask_user"}
            if user_vars:
                output = f"Execution successful. Local variables: {user_vars}"
            else:
                output = "Execution successful (no output produced)."
        return output
    except Exception:
        return f"Execution Error:\n{traceback_module.format_exc()}"
    finally:
        sys_module.stdout = old_stdout
        sys_module.stderr = old_stderr


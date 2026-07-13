sys_module = __import__("sys")
io_module = __import__("io")
traceback_module = __import__("traceback")
from registry import tool

@tool
def python_interpreter(code: str):
    """Execute Python code in an isolated dictionary scope and return stdout/stderr or execution errors.
    Useful for complex math, data processing, or script execution.
    """
    old_stdout = sys_module.stdout
    old_stderr = sys_module.stderr
    sys_module.stdout = io_module.StringIO()
    sys_module.stderr = io_module.StringIO()
    
    # We maintain a persistent or ephemeral scope
    scope = {}
    
    try:
        # execute code
        exec(code, scope, scope)
        stdout_val = sys_module.stdout.getvalue()
        stderr_val = sys_module.stderr.getvalue()
        output = stdout_val + stderr_val
        if not output.strip():
            # If no prints, check if we can print the last expression or list of variables
            # filter out double underscores
            user_vars = {k: v for k, v in scope.items() if not k.startswith("__")}
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

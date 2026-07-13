import os
from registry import tool

@tool
def get_env(name: str):
    """Retrieve the value of an environment variable. Returns error message if not set."""
    val = os.environ.get(name)
    if val is None:
        return f"Environment variable '{name}' is not set."
    return f"{name}={val}"

@tool
def list_env():
    """List the names of all active environment variables."""
    try:
        names = sorted(os.environ.keys())
        return "Active environment variables:\n" + "\n".join(names)
    except Exception as e:
        return f"Error listing environment variables: {e}"

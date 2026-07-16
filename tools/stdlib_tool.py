from registry import tool
import json, os
@tool
def stdlib_tool(path: str) -> str:
    """Lists files as JSON."""
    return json.dumps(os.listdir(path))

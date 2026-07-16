from registry import tool
@tool
def synthesized_test_tool(msg: str) -> str:
    """This is a dynamically created test tool."""
    return f"Synthesized Tool Received: {msg}"

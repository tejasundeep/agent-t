from registry import tool
@tool
def brand_new_tool(x: str):
    """A completely new tool."""
    return x.upper()
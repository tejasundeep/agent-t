from registry import tool
@tool
def read_file(path:str):
    """Read a text file."""
    return open(path,encoding="utf8").read()

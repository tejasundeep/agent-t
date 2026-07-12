from registry import tool
import subprocess
@tool
def shell(cmd:str):
    """Run a shell command."""
    return subprocess.check_output(cmd,shell=True,text=True)

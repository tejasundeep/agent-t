import platform
import os
import sys
from registry import tool

@tool
def system_info():
    """Retrieve details about the current operating system, machine specifications, Python version, and working directory."""
    try:
        info = [
            f"OS: {platform.system()} {platform.release()} ({platform.version()})",
            f"Architecture: {platform.machine()} ({platform.architecture()[0]})",
            f"Python Version: {sys.version.split()[0]}",
            f"Current Directory: {os.getcwd()}",
            f"CPU Cores: {os.cpu_count() or 'Unknown'}"
        ]
        return "\n".join(info)
    except Exception as e:
        return f"Error retrieving system info: {e}"

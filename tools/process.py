import subprocess
import os
import shutil
import tempfile
import pathlib
from registry import tool

# Dictionary mapping PID to process object and output file path
_bg_processes = {}

@tool
def list_processes(filter_name: str = ""):
    """List running system processes (PID, Name). Optional filter_name to narrow down."""
    try:
        output = ""
        if shutil.which("tasklist"):  # Windows
            cmd = ["tasklist"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = res.stdout
        else:  # Unix
            cmd = ["ps", "-ax"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = res.stdout
        
        lines = output.splitlines()
        header = lines[:3]
        body = lines[3:]
        
        filtered = []
        for line in body:
            if not filter_name or filter_name.lower() in line.lower():
                filtered.append(line)
        
        return "\n".join(header + filtered[:100]) # Limit to top 100 lines
    except Exception as e:
        return f"Error listing processes: {e}"

@tool
def kill_process(pid: int):
    """Terminate a process by its PID."""
    try:
        if shutil.which("taskkill"):  # Windows
            res = subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True, check=False)
        else:  # Unix
            res = subprocess.run(["kill", "-9", str(pid)], capture_output=True, text=True, check=False)
        
        if res.returncode == 0:
            return f"Successfully terminated process {pid}."
        return f"Failed to terminate process {pid}: {res.stderr or res.stdout}"
    except Exception as e:
        return f"Error killing process {pid}: {e}"

@tool
def run_background_command(cmd: str):
    """Run a shell command asynchronously in the background. Returns the process PID."""
    try:
        # Create a temporary file to store output logs
        temp_dir = pathlib.Path(tempfile.gettempdir())
        log_file = temp_dir / f"agent_bg_{os.getpid()}_{len(_bg_processes)}.log"
        
        # Open file descriptor
        fd = open(log_file, "w", encoding="utf-8", errors="replace")
        
        # Start background process
        p = subprocess.Popen(
            cmd,
            shell=True,
            stdout=fd,
            stderr=fd,
            text=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        
        _bg_processes[p.pid] = {"proc": p, "log": log_file, "fd": fd}
        return f"Process started in background with PID: {p.pid}. Logs will be saved to '{log_file}'."
    except Exception as e:
        return f"Error spawning background command: {e}"

@tool
def get_background_output(pid: int, lines: int = 50):
    """Get the latest stdout/stderr logs of a running background process using its PID."""
    # Find matching process in current session or inspect log templates
    log_path = None
    if pid in _bg_processes:
        log_path = _bg_processes[pid]["log"]
    else:
        # Fallback: scan temp dir for logs matching the PID pattern
        temp_dir = pathlib.Path(tempfile.gettempdir())
        for f in temp_dir.glob(f"agent_bg_*_{pid}.log"):
            log_path = f
            break
        # Or look for any logs from the main PID
        if not log_path:
            for f in temp_dir.glob(f"agent_bg_{os.getpid()}_*.log"):
                # We can check if it's the right one
                pass
    
    if not log_path or not os.path.isfile(log_path):
        return f"Error: No background log files found for process {pid}."
    
    try:
        # Flush the file descriptor if open to ensure up-to-date output
        if pid in _bg_processes:
            _bg_processes[pid]["fd"].flush()
            
        content = pathlib.Path(log_path).read_text(encoding="utf-8", errors="replace")
        content_lines = content.splitlines()
        sliced = content_lines[-max(1, lines):]
        status = "Running"
        if pid in _bg_processes:
            poll = _bg_processes[pid]["proc"].poll()
            if poll is not None:
                status = f"Finished (Exit Code {poll})"
        
        return f"Process Status: {status}\n--- Output Log (last {len(sliced)} lines) ---\n" + "\n".join(sliced)
    except Exception as e:
        return f"Error reading process output: {e}"

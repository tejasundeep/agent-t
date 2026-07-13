import shutil
import platform
import os
import subprocess
from registry import tool

@tool
def system_resources():
    """Retrieve system storage (disk usage) and memory availability info."""
    res = []
    # Disk Usage
    try:
        total, used, free = shutil.disk_usage(".")
        to_gb = 1024**3
        res.append("Disk Usage (Current Directory):")
        res.append(f"  Total: {total / to_gb:.2f} GB")
        res.append(f"  Used:  {used / to_gb:.2f} GB")
        res.append(f"  Free:  {free / to_gb:.2f} GB")
    except Exception as e:
        res.append(f"Disk Usage check failed: {e}")
        
    # Memory Usage
    try:
        sys_type = platform.system()
        res.append("\nMemory Info:")
        if sys_type == "Windows":
            # Run wmic to get memory size
            cmd = ["wmic", "OS", "get", "FreePhysicalMemory,TotalVisibleMemorySize", "/Value"]
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            data = {}
            for line in out.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = int(v.strip())
            total_mb = data.get("TotalVisibleMemorySize", 0) / 1024
            free_mb = data.get("FreePhysicalMemory", 0) / 1024
            res.append(f"  Total Memory: {total_mb:.1f} MB")
            res.append(f"  Free Memory:  {free_mb:.1f} MB")
        elif sys_type == "Linux":
            # Read /proc/meminfo
            total_mem, free_mem = 0, 0
            with open("/proc/meminfo") as f:
                for line in f:
                    if "MemTotal" in line:
                        total_mem = int(line.split()[1]) / 1024
                    elif "MemAvailable" in line:
                        free_mem = int(line.split()[1]) / 1024
            res.append(f"  Total Memory: {total_mem:.1f} MB")
            res.append(f"  Available Memory: {free_mem:.1f} MB")
        elif sys_type == "Darwin":  # macOS
            # Parse sysctl for memory
            out_total = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            total_gb = int(out_total) / (1024**3)
            # Get vm_stat for free memory
            out_vm = subprocess.check_output(["vm_stat"], text=True)
            page_size = 4096
            for line in out_vm.splitlines():
                if "page size of" in line:
                    page_size = int(line.split()[-2])
                if "Pages free" in line:
                    free_pages = int(line.split()[-1].replace(".", ""))
                    free_gb = (free_pages * page_size) / (1024**3)
            res.append(f"  Total Memory: {total_gb:.2f} GB")
            res.append(f"  Free Memory (Pages): {free_gb:.2f} GB")
        else:
            res.append("  Memory check not supported on this platform.")
    except Exception as e:
        res.append(f"  Memory check failed: {e}")
        
    return "\n".join(res)

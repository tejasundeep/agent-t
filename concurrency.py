import concurrent.futures
import atexit

# Global ThreadPoolExecutor for background tasks
global_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=16,
    thread_name_prefix="agent_t_bg_"
)

@atexit.register
def shutdown_executor():
    global_executor.shutdown(wait=False)

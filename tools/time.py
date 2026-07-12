from registry import tool
from datetime import datetime
@tool
def get_time():
    """Returns current local time."""
    return datetime.now().strftime("%H:%M:%S")

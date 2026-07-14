import PIL.ImageGrab
import os
from registry import tool

@tool
def take_screenshot():
    """Capture a screenshot of the entire primary screen and save it as screenshot.png."""
    try:
        # Capture the screen
        screenshot = PIL.ImageGrab.grab()
        path = "screenshot.png"
        screenshot.save(path)
        # Get absolute path for confirmation
        abs_path = os.path.abspath(path)
        return f"Success: Screenshot captured and saved to {abs_path}."
    except Exception as e:
        return f"Error capturing screenshot: {e}"

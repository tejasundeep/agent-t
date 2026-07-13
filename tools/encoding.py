import base64
from registry import tool

@tool
def base64_encode(data: str):
    """Encode a text string to Base64 format."""
    try:
        encoded = base64.b64encode(data.encode("utf-8")).decode("utf-8")
        return encoded
    except Exception as e:
        return f"Encoding Error: {e}"

@tool
def base64_decode(data: str):
    """Decode a Base64 encoded string back to plaintext."""
    try:
        decoded = base64.b64decode(data.encode("utf-8")).decode("utf-8")
        return decoded
    except Exception as e:
        return f"Decoding Error: {e}"

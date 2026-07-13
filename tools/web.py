import urllib.request
import urllib.parse
import re
from registry import tool

@tool
def fetch_url(url: str):
    """Fetch the text content of a webpage (HTML converted to simple plain text)."""
    # Normalize URL scheme
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8", errors="replace")
            
            # Simple HTML parser to get text
            # Remove scripts and styles
            html = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", " ", html, flags=re.IGNORECASE)
            html = re.sub(r"<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>", " ", html, flags=re.IGNORECASE)
            
            # Convert simple block elements to newlines
            html = re.sub(r"<(div|p|h1|h2|h3|h4|h5|h6|li|tr|br\s*/?)>", "\n", html, flags=re.IGNORECASE)
            
            # Strip remaining tags
            text = re.sub(r"<[^>]+>", " ", html)
            
            # Unescape basic HTML entities
            text = text.replace("&nbsp;", " ")
            text = text.replace("&lt;", "<")
            text = text.replace("&gt;", ">")
            text = text.replace("&amp;", "&")
            text = text.replace("&quot;", '"')
            
            # Normalize whitespace
            lines = [line.strip() for line in text.splitlines()]
            non_empty_lines = [line for line in lines if line]
            
            return "\n".join(non_empty_lines[:150]) # limit output length to prevent overloading context
    except Exception as e:
        return f"Error fetching URL '{url}': {e}"

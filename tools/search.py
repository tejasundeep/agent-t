import urllib.request
import urllib.parse
import re
from registry import tool

@tool
def web_search(query: str):
    """Search the web for the given query using DuckDuckGo HTML search. Returns titles, links, and snippets of results."""
    encoded_query = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8", errors="replace")
            
            # Simple regex search parser for DuckDuckGo HTML results
            # Each result is contained in a <div class="web-result"> or similar block
            # Let's extract result links, titles, and snippets.
            # Typical result structure in DDG HTML:
            # <a class="result__url" href="...">...</a>
            # <a class="result__snippet" href="...">...</a>
            
            results = []
            # Find result blocks
            # A simple regex to catch result titles, links, and snippets:
            # <a class="result__snippet" ...> matches snippet text.
            # <a class="result__url" href="...URL...">
            
            # Let's extract the results using matching blocks:
            # We can find all links with class="result__snippet" and class="result__url"
            # Or parse the HTML text for matches
            # Let's look for:
            # class="result__snippet"\s+href="(?P<url>[^"]+)"[^>]*>(?P<snippet>.*?)</a>
            # and class="result__title"\s*>[^<]*<a\s+class="result__url"\s+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>
            
            matches = re.finditer(r'<a\s+class="result__url"\s+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?<a\s+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>', html, re.DOTALL)
            
            for m in matches:
                url_val = urllib.parse.unquote(m.group("url"))
                # Sometimes URL is in form: //duckduckgo.com/l/?uddg=URL
                if "uddg=" in url_val:
                    parsed_url = urllib.parse.urlparse(url_val)
                    query_params = urllib.parse.parse_qs(parsed_url.query)
                    if "uddg" in query_params:
                        url_val = query_params["uddg"][0]
                
                title_val = re.sub(r"<[^>]+>", "", m.group("title")).strip()
                snippet_val = re.sub(r"<[^>]+>", "", m.group("snippet")).strip()
                
                results.append(f"- **{title_val}**\n  URL: {url_val}\n  {snippet_val}")
                if len(results) >= 6: # limit to top 6 results
                    break
            
            # Fallback if the detailed regex fails (e.g. structure changes)
            if not results:
                # Find all links that look like external web results
                # DDG HTML has results listed with class "result__snippet" or inside result__body
                # Let's do a broader regex match
                simple_links = re.findall(r'<a\s+class="result__url"\s+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>', html, re.DOTALL)
                for u, t in simple_links[:8]:
                    url_val = urllib.parse.unquote(u)
                    if "uddg=" in url_val:
                        parsed_url = urllib.parse.urlparse(url_val)
                        query_params = urllib.parse.parse_qs(parsed_url.query)
                        if "uddg" in query_params:
                            url_val = query_params["uddg"][0]
                    title_val = re.sub(r"<[^>]+>", "", t).strip()
                    results.append(f"- **{title_val}**\n  URL: {url_val}")
            
            if not results:
                return "No search results found. (The structure of the search provider may have changed or network issues occurred.)"
            
            return f"Search results for '{query}':\n\n" + "\n\n".join(results)
            
    except Exception as e:
        return f"Error executing web search: {e}"

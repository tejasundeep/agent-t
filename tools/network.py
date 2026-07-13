import urllib.request
import urllib.parse
import socket
import json
from registry import tool

@tool
def ping_host(host: str):
    """Verify if a remote host is reachable (resolves IP and tests connectivity)."""
    try:
        # Resolve hostname
        ip = socket.gethostbyname(host)
        # Try socket connect to port 80 or 443
        for port in [80, 443, 22]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3.0)
                s.connect((ip, port))
                s.close()
                return f"Host '{host}' ({ip}) is REACHABLE on port {port}."
            except Exception:
                continue
        return f"Host '{host}' ({ip}) resolved, but TCP connection timed out on standard ports."
    except Exception as e:
        return f"Host '{host}' is UNREACHABLE. Error: {e}"

@tool
def get_ip_addresses():
    """Retrieve the local and public IP addresses of this host."""
    res = {}
    # Local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        res["local_ip"] = s.getsockname()[0]
        s.close()
    except Exception as e:
        res["local_ip"] = f"Unknown ({e})"
        
    # Public IP
    try:
        req = urllib.request.Request("https://api.ipify.org?format=json", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            res["public_ip"] = json.loads(r.read().decode())["ip"]
    except Exception as e:
        res["public_ip"] = f"Could not determine public IP ({e})"
        
    return f"Local IP: {res['local_ip']}\nPublic IP: {res['public_ip']}"

@tool
def download_file(url: str, dest_path: str):
    """Download a file from a URL directly to the destination path."""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            with open(dest_path, "wb") as f:
                f.write(response.read())
        return f"Successfully downloaded file to '{dest_path}'."
    except Exception as e:
        return f"Error downloading from '{url}': {e}"

@tool
def http_request(method: str, url: str, headers: str = "{}", body: str = ""):
    """Execute a raw HTTP request (GET, POST, PUT, DELETE) with optional headers and body.
    headers parameter must be a JSON string of key-value pairs.
    """
    method = method.upper()
    try:
        hdr_dict = json.loads(headers)
    except Exception as e:
        return f"Error parsing headers JSON: {e}"
        
    if "User-Agent" not in hdr_dict:
        hdr_dict["User-Agent"] = "Mozilla/5.0"
        
    data_bytes = body.encode("utf-8") if body else None
    
    try:
        req = urllib.request.Request(url, data=data_bytes, headers=hdr_dict, method=method)
        with urllib.request.urlopen(req, timeout=15) as response:
            res_body = response.read().decode("utf-8", errors="replace")
            res_headers = dict(response.info())
            res_status = response.status
            return f"Status: {res_status}\nHeaders: {json.dumps(res_headers, indent=2)}\n\nBody:\n{res_body[:2000]}"
    except urllib.error.HTTPError as e:
        return f"HTTP Error Status: {e.code}\nHeaders: {json.dumps(dict(e.headers), indent=2)}\n\nBody:\n{e.read().decode('utf-8', errors='replace')[:2000]}"
    except Exception as e:
        return f"Request failed: {e}"

@tool
def scan_ports(host: str, ports: str):
    """Scan TCP ports on a host to check if they are open.
    ports parameter must be a comma-separated list of port numbers (e.g. '22,80,443,8080').
    """
    try:
        ip = socket.gethostbyname(host)
        port_list = [int(p.strip()) for p in ports.split(",") if p.strip()]
    except Exception as e:
        return f"Error parsing parameters: {e}"
        
    results = [f"Port scan results for {host} ({ip}):"]
    for port in port_list:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.5)
            res = s.connect_ex((ip, port))
            s.close()
            status = "OPEN" if res == 0 else "CLOSED"
            results.append(f"  Port {port}: {status}")
        except Exception as e:
            results.append(f"  Port {port}: ERROR ({e})")
    return "\n".join(results)

@tool
def dns_lookup(domain: str):
    """Resolve IP addresses associated with a domain name."""
    try:
        # Get host by name ex returns aliases and IPs
        name, aliases, ip_list = socket.gethostbyname_ex(domain)
        results = [
            f"DNS Lookup for: {domain}",
            f"Canonical Name: {name}",
            f"Aliases: {', '.join(aliases) if aliases else 'None'}",
            f"IP Addresses: {', '.join(ip_list) if ip_list else 'None'}"
        ]
        return "\n".join(results)
    except Exception as e:
        return f"DNS Lookup failed for '{domain}': {e}"

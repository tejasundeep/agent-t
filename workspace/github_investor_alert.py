"""
github_investor_alert.py
Fetches GitHub Trending repositories and prints a formatted investor alert.
Used by the 'thub_investor_alert' routine (schedule: 1m).
"""
import urllib.request
import urllib.parse
import urllib.error
import json
import datetime
import sys
import os

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Config ────────────────────────────────────────────────────────────────────
TRENDING_API   = "https://api.github.com/search/repositories"
SINCE_HOURS    = 24           # look-back window
TOP_N          = 5            # how many repos to report
LANGUAGE       = ""           # filter by language, e.g. "python" or "" for all

# ── Helpers ───────────────────────────────────────────────────────────────────
def fetch_trending(language="", top_n=5, since_hours=24):
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=since_hours)).strftime("%Y-%m-%d")
    query = f"created:>{since}"
    if language:
        query += f" language:{language}"
    params = f"q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page={top_n}"
    url    = f"{TRENDING_API}?{params}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "agent-t-investor-alert/1.0", "Accept": "application/vnd.github.v3+json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

def fmt_number(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"[GitHub Investor Alert] {now}")
    print("=" * 60)

    try:
        data  = fetch_trending(language=LANGUAGE, top_n=TOP_N, since_hours=SINCE_HOURS)
        items = data.get("items", [])
    except urllib.error.URLError as e:
        print(f"[ERROR] Network request failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

    if not items:
        print("No trending repositories found in the configured window.")
        return

    for i, repo in enumerate(items, 1):
        name        = repo.get("full_name", "N/A")
        description = (repo.get("description") or "No description provided")[:80]
        stars       = repo.get("stargazers_count", 0)
        forks       = repo.get("forks_count", 0)
        watchers    = repo.get("watchers_count", 0)
        lang        = repo.get("language") or "N/A"
        url         = repo.get("html_url", "")
        topics      = ", ".join(repo.get("topics", [])[:4]) or "none"
        created_at  = (repo.get("created_at") or "")[:10]
        open_issues = repo.get("open_issues_count", 0)

        print(f"\n  #{i}  {name}")
        print(f"       Stars    : {fmt_number(stars)}   Forks: {fmt_number(forks)}   Watchers: {fmt_number(watchers)}")
        print(f"       Language : {lang}")
        print(f"       Created  : {created_at}   Open Issues: {open_issues}")
        print(f"       Topics   : {topics}")
        print(f"       Desc     : {description}")
        print(f"       URL      : {url}")

    total = data.get("total_count", len(items))
    print(f"\n[Done] Showing top {len(items)} of {fmt_number(total)} repos trending in last {SINCE_HOURS}h.")

if __name__ == "__main__":
    main()

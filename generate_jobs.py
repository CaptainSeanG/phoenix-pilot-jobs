import requests
import datetime
from pathlib import Path
import os

# ==============================
# API Keys from GitHub Secrets
# ==============================
BING_KEY = os.getenv("BING_API_KEY")
BING_ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

GOOGLE_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX_ID")

# Keywords to search
KEYWORDS = ["Caravan", "PC-12", "Navajo", "Comanche"]

# Cutoff date (30 days ago, in case APIs don’t filter perfectly)
CUTOFF = datetime.datetime.utcnow() - datetime.timedelta(days=30)


def search_bing(query: str):
    """Search Bing Web API"""
    headers = {"Ocp-Apim-Subscription-Key": BING_KEY}
    params = {"q": query, "count": 20, "freshness": "Month"}
    r = requests.get(BING_ENDPOINT, headers=headers, params=params)
    r.raise_for_status()
    return r.json()


def search_google(query: str):
    """Search Google Custom Search API"""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": GOOGLE_KEY, "cx": GOOGLE_CX, "q": query, "num": 10}
    r = requests.get(url, params=params)
    r.raise_for_status()
    return r.json()


def build_html(results: list):
    """Build simple HTML page with search results"""
    html = """
    <html>
    <head>
        <title>Pilot Job Search</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            h1 { color: #004080; }
            ul { line-height: 1.6; }
            li { margin-bottom: 12px; }
            a { text-decoration: none; color: #0066cc; }
            a:hover { text-decoration: underline; }
            small { color: #444; }
        </style>
    </head>
    <body>
        <h1>Pilot Jobs (Last 30 Days)</h1>
        <ul>
    """
    for r in results:
        snippet = r.get("snippet", "")
        html += f"<li><a href='{r['url']}' target='_blank'>{r['title']}</a><br><small>{snippet}</small></li>"
    html += "</ul></body></html>"
    return html


if __name__ == "__main__":
    all_results = []

    # --- Bing search ---
    for kw in KEYWORDS:
        try:
            data = search_bing(f"{kw} pilot job")
            for item in data.get("webPages", {}).get("value", []):
                all_results.append({
                    "title": item["name"],
                    "url": item["url"],
                    "snippet": item.get("snippet", "")
                })
        except Exception as e:
            print(f"Bing error for {kw}: {e}")

    # --- Google search ---
    for kw in KEYWORDS:
        try:
            data = search_google(f"{kw} pilot job")
            for item in data.get("items", []):
                all_results.append({
                    "title": item["title"],
                    "url": item["link"],
                    "snippet": item.get("snippet", "")
                })
        except Exception as e:
            print(f"Google error for {kw}: {e}")

    # --- Deduplicate by URL ---
    seen = set()
    filtered = []
    for r in all_results:
        if r["url"] not in seen:
            seen.add(r["url"])
            filtered.append(r)

    # --- Write HTML file ---
    html = build_html(filtered)
    Path("index.html").write_text(html, encoding="utf-8")

    print(f"Generated index.html with {len(filtered)} unique results")

import requests
from pathlib import Path
import os
from datetime import datetime

# ==============================
# API Keys from environment variables (GitHub Secrets)
# ==============================
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX_ID")

# Keywords
KEYWORDS = ["Caravan", "PC-12", "Navajo", "Comanche"]


def search_google(query: str):
    """Search Google Custom Search API"""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": GOOGLE_KEY, "cx": GOOGLE_CX, "q": query, "num": 10}
    r = requests.get(url, params=params)
    r.raise_for_status()
    return r.json()


def build_html(results: list):
    """Generate HTML output"""
    updated_on = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    html = f"""
    <html>
    <head>
        <title>Pilot Job Search</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background: #f9f9f9; }}
            h1 {{ color: #004080; }}
            .updated {{ color: #666; font-size: 0.9em; margin-bottom: 20px; }}
            ul {{ line-height: 1.6; }}
            li {{ margin-bottom: 12px; }}
            a {{ text-decoration: none; color: #0066cc; }}
            a:hover {{ text-decoration: underline; }}
            small {{ color: #444; }}
        </style>
    </head>
    <body>
        <h1>Pilot Jobs (Last 30 Days)</h1>
        <div class="updated">Updated on: {updated_on}</div>
        <ul>
    """
    for r in results:
        snippet = r.get("snippet", "")
        html += f"<li><a href='{r['url']}' target='_blank'>{r['title']}</a><br><small>{snippet}</small></li>"
    html += "</ul></body></html>"
    return html


if __name__ == "__main__":
    all_results = []

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

    # --- Write HTML ---
    html = build_html(filtered)
    Path("index.html").write_text(html, encoding="utf-8")

    print(f"Generated index.html with {len(filtered)} unique results (Updated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')})")

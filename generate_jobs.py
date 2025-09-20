import requests
import datetime
from pathlib import Path

# Your Bing API key and endpoint
BING_KEY = "YOUR_BING_API_KEY"
BING_ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

# Keywords
keywords = ["Caravan", "PC-12", "Navajo", "Comanche"]

# Date cutoff (30 days ago)
cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)

def search_bing(query):
    headers = {"Ocp-Apim-Subscription-Key": BING_KEY}
    params = {"q": query, "count": 20, "freshness": "Month"}  # freshness=Month ensures <30 days
    r = requests.get(BING_ENDPOINT, headers=headers, params=params)
    r.raise_for_status()
    return r.json()

def build_html(results):
    html = "<html><head><title>Pilot Jobs Search</title></head><body>"
    html += "<h1>Pilot Jobs (Last 30 Days)</h1><ul>"
    for r in results:
        html += f"<li><a href='{r['url']}'>{r['name']}</a> - {r.get('snippet','')}</li>"
    html += "</ul></body></html>"
    return html

if __name__ == "__main__":
    all_results = []
    for kw in keywords:
        data = search_bing(f'{kw} pilot job')
        for web in data.get("webPages", {}).get("value", []):
            all_results.append(web)

    # Deduplicate by URL
    seen = set()
    filtered = []
    for r in all_results:
        if r['url'] not in seen:
            seen.add(r['url'])
            filtered.append(r)

    html = build_html(filtered)
    Path("index.html").write_text(html, encoding="utf-8")

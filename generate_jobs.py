import requests
from pathlib import Path
import os
from datetime import datetime

# ==============================
# API Keys from environment variables (GitHub Secrets)
# ==============================
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX_ID")

# Keywords to filter & tag results
KEYWORDS = ["Caravan", "PC-12", "Navajo", "Comanche"]


def search_google(query: str):
    """Search Google Custom Search API"""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": GOOGLE_KEY, "cx": GOOGLE_CX, "q": query, "num": 10}
    r = requests.get(url, params=params)
    r.raise_for_status()
    return r.json()


def build_html(results: list):
    """Generate HTML page with grid cards, filters, and light/dark toggle"""
    updated_on = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    html = f"""
    <html>
    <head>
        <title>Pilot Job Search</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background: var(--bg);
                color: var(--text);
                transition: background 0.3s, color 0.3s;
            }}
            :root {{
                --bg: #f9f9f9;
                --text: #111;
                --card-bg: #fff;
                --card-border: #ddd;
            }}
            body.dark {{
                --bg: #1e1e1e;
                --text: #eee;
                --card-bg: #2a2a2a;
                --card-border: #444;
            }}
            h1 {{ color: #004080; }}
            .updated {{ color: #666; font-size: 0.9em; margin-bottom: 20px; }}
            .controls {{ margin-bottom: 20px; }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
            }}
            .card {{
                background: var(--card-bg);
                border: 1px solid var(--card-border);
                border-radius: 8px;
                padding: 15px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
            .card a {{
                font-weight: bold;
                font-size: 1.1em;
                color: #0066cc;
                text-decoration: none;
            }}
            .card a:hover {{ text-decoration: underline; }}
            .toggle {{
                cursor: pointer;
                padding: 5px 10px;
                border: 1px solid #ccc;
                border-radius: 5px;
                background: var(--card-bg);
                color: var(--text);
                margin-left: 15px;
            }}
        </style>
    </head>
    <body>
        <h1>Pilot Jobs (Last 30 Days)</h1>
        <div class="updated">Updated on: {updated_on} — Showing {len(results)} jobs</div>

        <div class="controls">
            <strong>Filter:</strong>
            <label><input type="checkbox" value="caravan" onclick="filterJobs()"> Caravan</label>
            <label><input type="checkbox" value="pc-12" onclick="filterJobs()"> PC-12</label>
            <label><input type="checkbox" value="navajo" onclick="filterJobs()"> Navajo</label>
            <label><input type="checkbox" value="comanche" onclick="filterJobs()"> Comanche</label>
            <button class="toggle" onclick="toggleTheme()">🌙 Toggle Light/Dark</button>
        </div>

        <div id="jobs" class="grid">
    """

    for r in results:
        snippet = r.get("snippet", "")
        # Lowercase class names for filters
        classes = " ".join([kw.lower() for kw in KEYWORDS if kw.lower() in (r['title'] + snippet).lower()])
        html += f"""
        <div class="card {classes}">
            <a href="{r['url']}" target="_blank">{r['title']}</a>
            <p>{snippet}</p>
        </div>
        """

    html += """
        </div>
        <script>
            function filterJobs() {
                const checkboxes = document.querySelectorAll('input[type=checkbox]');
                const jobs = document.querySelectorAll('.card');
                let active = [];
                checkboxes.forEach(cb => { if (cb.checked) active.push(cb.value.toLowerCase()); });

                jobs.forEach(job => {
                    if (active.length === 0) {
                        job.style.display = 'block';
                    } else {
                        let match = active.some(a => job.classList.contains(a));
                        job.style.display = match ? 'block' : 'none';
                    }
                });
            }

            function toggleTheme() {
                document.body.classList.toggle('dark');
            }
        </script>
    </body>
    </html>
    """
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

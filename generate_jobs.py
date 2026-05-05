import os
import re
import html
import requests
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

GOOGLE_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX_ID")

AIRCRAFT_KEYWORDS = {
    "Caravan": ["caravan", "c208", "cessna 208", "grand caravan"],
    "PC-12": ["pc-12", "pc12", "pilatus"],
    "King Air": ["king air", "be200", "b200", "be90", "c90", "b90"],
    "Navajo": ["navajo", "pa-31", "pa31", "chieftain"],
    "Comanche": ["comanche", "pa-24", "pa24"],
}

MISSION_KEYWORDS = {
    "Cargo": ["cargo", "freight", "fedex feeder", "ups feeder"],
    "Part 135": ["part 135", "135"],
    "SIC": ["sic", "second in command", "first officer", "fo"],
    "PIC": ["pic", "captain", "pilot in command"],
    "Low-Time Friendly": ["low time", "low-time", "entry level", "minimum 500", "minimum 750", "minimum 1000"],
    "Arizona": ["phoenix", "scottsdale", "mesa", "tempe", "glendale", "tucson", "arizona", "az"],
}

GOOD_TERMS = [
    "pilot", "captain", "sic", "pic", "first officer", "second in command",
    "cargo", "charter", "part 135", "135", "aviation", "aircraft",
    "caravan", "c208", "pc-12", "pc12", "king air", "navajo", "pa-31"
]

BAD_TERMS = [
    "flight school", "training course", "type rating", "simulator", "forum",
    "salary", "how much", "resume", "template", "news", "crash",
    "accident", "wikipedia", "facebook", "youtube", "reddit",
    "mechanic", "maintenance technician", "electrician", "truck driver",
    "navajo express", "jeep", "piper comanche parts", "for sale"
]

SEARCH_QUERIES = [
    '"Caravan" pilot job OR captain OR SIC OR cargo',
    '"Cessna 208" pilot job OR captain OR cargo',
    '"PC-12" pilot job OR captain OR SIC OR "Part 135"',
    '"Pilatus PC-12" pilot job OR captain OR first officer',
    '"King Air" pilot job OR SIC OR captain OR "Part 135"',
    '"Navajo" pilot job OR "PA-31" OR cargo',
    '"Comanche" pilot job OR "PA-24"',
    '"low time" pilot job cargo "Part 135"',
    '"Phoenix" pilot job Caravan OR "PC-12" OR "King Air"',
    '"Arizona" pilot job cargo OR charter OR "Part 135"',
]

MAX_RESULTS_PER_QUERY = 10


def search_google(query):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_KEY,
        "cx": GOOGLE_CX,
        "q": query,
        "num": MAX_RESULTS_PER_QUERY,
        "dateRestrict": "m1",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def clean_url(url):
    parsed = urlparse(url)
    cleaned = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return cleaned.rstrip("/")


def source_name(url):
    domain = urlparse(url).netloc.lower().replace("www.", "")
    return domain


def text_blob(result):
    return f"{result.get('title', '')} {result.get('snippet', '')} {result.get('url', '')}".lower()


def find_tags(result):
    blob = text_blob(result)
    tags = []

    for label, terms in AIRCRAFT_KEYWORDS.items():
        if any(term in blob for term in terms):
            tags.append(label)

    for label, terms in MISSION_KEYWORDS.items():
        if any(term in blob for term in terms):
            tags.append(label)

    return tags


def score_result(result):
    blob = text_blob(result)
    score = 0

    for term in GOOD_TERMS:
        if term in blob:
            score += 8

    for aircraft_terms in AIRCRAFT_KEYWORDS.values():
        if any(term in blob for term in aircraft_terms):
            score += 20

    for mission_terms in MISSION_KEYWORDS.values():
        if any(term in blob for term in mission_terms):
            score += 10

    if "pilot" in blob:
        score += 25
    if "job" in blob or "career" in blob or "position" in blob:
        score += 15
    if "apply" in blob or "hiring" in blob:
        score += 15

    for bad in BAD_TERMS:
        if bad in blob:
            score -= 40

    if "comanche" in blob and "pilot" not in blob:
        score -= 50

    return score


def is_probably_job(result):
    blob = text_blob(result)

    if any(bad in blob for bad in BAD_TERMS):
        return False

    has_aircraft = any(
        term in blob
        for terms in AIRCRAFT_KEYWORDS.values()
        for term in terms
    )

    has_job_intent = any(term in blob for term in [
        "pilot", "captain", "sic", "pic", "first officer",
        "cargo", "charter", "part 135", "apply", "hiring", "job"
    ])

    return has_aircraft and has_job_intent


def badge_class(tag):
    return re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")


def build_html(results):
    updated_on = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    escaped_results = []

    for r in results:
        tags = find_tags(r)
        escaped_results.append({
            "title": html.escape(r["title"]),
            "url": html.escape(r["url"]),
            "snippet": html.escape(r.get("snippet", "")),
            "source": html.escape(source_name(r["url"])),
            "score": r["score"],
            "tags": tags,
            "tag_classes": " ".join(badge_class(t) for t in tags),
        })

    filter_tags = [
        "Caravan", "PC-12", "King Air", "Navajo", "Comanche",
        "Cargo", "Part 135", "SIC", "PIC", "Low-Time Friendly", "Arizona"
    ]

    cards = ""
    for r in escaped_results:
        badges = "".join(
            f'<span class="badge">{html.escape(tag)}</span>'
            for tag in r["tags"]
        )

        cards += f"""
        <article class="job-card {r['tag_classes']}" data-search="{r['title'].lower()} {r['snippet'].lower()} {r['source'].lower()} {' '.join(t.lower() for t in r['tags'])}">
          <div class="card-top">
            <span class="source">{r['source']}</span>
            <span class="score">Fit {r['score']}</span>
          </div>
          <h2><a href="{r['url']}" target="_blank" rel="noopener noreferrer">{r['title']}</a></h2>
          <p>{r['snippet']}</p>
          <div class="badges">{badges}</div>
        </article>
        """

    filter_buttons = "".join(
        f'<button class="filter-btn" data-filter="{badge_class(tag)}">{html.escape(tag)}</button>'
        for tag in filter_tags
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Phoenix Pilot Jobs</title>
  <style>
    :root {{
      --bg: #eef3f8;
      --panel: #ffffff;
      --text: #142033;
      --muted: #667085;
      --border: #d9e2ec;
      --accent: #2563eb;
      --accent-soft: #dbeafe;
      --shadow: rgba(15, 23, 42, 0.10);
    }}

    body.dark {{
      --bg: #0f172a;
      --panel: #172033;
      --text: #f8fafc;
      --muted: #aab4c5;
      --border: #334155;
      --accent: #60a5fa;
      --accent-soft: #1e3a5f;
      --shadow: rgba(0, 0, 0, 0.35);
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}

    header {{
      padding: 28px 24px;
      background: linear-gradient(135deg, #102a43, #2563eb);
      color: white;
    }}

    header h1 {{
      margin: 0 0 8px;
      font-size: 2rem;
    }}

    header p {{
      margin: 0;
      color: rgba(255,255,255,0.85);
    }}

    main {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 22px;
    }}

    .toolbar {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      margin-bottom: 20px;
      box-shadow: 0 8px 24px var(--shadow);
    }}

    .top-row {{
      display: flex;
      gap: 12px;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }}

    #searchBox {{
      flex: 1;
      min-width: 260px;
      padding: 11px 12px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--text);
      font-size: 1rem;
    }}

    #themeToggle {{
      padding: 11px 14px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: var(--panel);
      color: var(--text);
      cursor: pointer;
    }}

    .filters {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}

    .filter-btn {{
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--text);
      border-radius: 999px;
      padding: 8px 12px;
      cursor: pointer;
      font-size: 0.92rem;
    }}

    .filter-btn.active {{
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }}

    .summary {{
      color: var(--muted);
      margin-top: 12px;
      font-size: 0.95rem;
    }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 18px;
    }}

    .job-card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 8px 24px var(--shadow);
      min-height: 230px;
      display: flex;
      flex-direction: column;
    }}

    .card-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
    }}

    .source {{
      color: var(--muted);
      font-size: 0.82rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .score {{
      background: var(--accent-soft);
      color: var(--accent);
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 0.78rem;
      font-weight: bold;
      white-space: nowrap;
    }}

    .job-card h2 {{
      font-size: 1.05rem;
      margin: 0 0 10px;
      line-height: 1.25;
    }}

    .job-card a {{
      color: var(--accent);
      text-decoration: none;
    }}

    .job-card a:hover {{
      text-decoration: underline;
    }}

    .job-card p {{
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.4;
      margin: 0 0 12px;
      flex: 1;
    }}

    .badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: auto;
    }}

    .badge {{
      background: var(--accent-soft);
      color: var(--accent);
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 0.75rem;
      font-weight: bold;
    }}

    .no-results {{
      display: none;
      text-align: center;
      padding: 30px;
      color: var(--muted);
    }}

    footer {{
      text-align: center;
      color: var(--muted);
      padding: 24px;
      font-size: 0.85rem;
    }}

    @media (max-width: 1000px) {{
      .grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}

    @media (max-width: 680px) {{
      .grid {{ grid-template-columns: 1fr; }}
      header h1 {{ font-size: 1.6rem; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Phoenix Pilot Jobs</h1>
    <p>First turbine job hunter: Caravan, PC-12, King Air, Navajo, cargo, SIC, Part 135, and Arizona-friendly opportunities.</p>
  </header>

  <main>
    <section class="toolbar">
      <div class="top-row">
        <input id="searchBox" type="search" placeholder="Search visible jobs: Phoenix, cargo, SIC, PC-12..." />
        <button id="themeToggle">🌙 Toggle Theme</button>
      </div>

      <div class="filters">
        {filter_buttons}
      </div>

      <div class="summary">
        Updated: {updated_on} · <span id="visibleCount">{len(results)}</span> showing of {len(results)} ranked results
      </div>
    </section>

    <section id="jobsGrid" class="grid">
      {cards}
    </section>

    <div id="noResults" class="no-results">
      No jobs match those filters. Try clearing a filter or search term.
    </div>
  </main>

  <footer>
    Generated automatically by GitHub Actions using Google Programmable Search.
  </footer>

  <script>
    const filterButtons = document.querySelectorAll(".filter-btn");
    const cards = document.querySelectorAll(".job-card");
    const searchBox = document.getElementById("searchBox");
    const visibleCount = document.getElementById("visibleCount");
    const noResults = document.getElementById("noResults");
    const themeToggle = document.getElementById("themeToggle");

    function applyFilters() {{
      const activeFilters = Array.from(filterButtons)
        .filter(btn => btn.classList.contains("active"))
        .map(btn => btn.dataset.filter);

      const searchText = searchBox.value.trim().toLowerCase();
      let count = 0;

      cards.forEach(card => {{
        const matchesFilters = activeFilters.length === 0 ||
          activeFilters.some(filter => card.classList.contains(filter));

        const matchesSearch = searchText === "" ||
          card.dataset.search.includes(searchText);

        const show = matchesFilters && matchesSearch;
        card.style.display = show ? "flex" : "none";
        if (show) count++;
      }});

      visibleCount.textContent = count;
      noResults.style.display = count === 0 ? "block" : "none";
    }}

    filterButtons.forEach(btn => {{
      btn.addEventListener("click", () => {{
        btn.classList.toggle("active");
        applyFilters();
      }});
    }});

    searchBox.addEventListener("input", applyFilters);

    themeToggle.addEventListener("click", () => {{
      document.body.classList.toggle("dark");
      localStorage.setItem("theme", document.body.classList.contains("dark") ? "dark" : "light");
    }});

    if (localStorage.getItem("theme") === "dark") {{
      document.body.classList.add("dark");
    }}
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    if not GOOGLE_KEY or not GOOGLE_CX:
        raise RuntimeError("Missing GOOGLE_API_KEY or GOOGLE_CX_ID environment variable.")

    all_results = []

    for query in SEARCH_QUERIES:
        try:
            data = search_google(query)
            for item in data.get("items", []):
                result = {
                    "title": item.get("title", "").strip(),
                    "url": item.get("link", "").strip(),
                    "snippet": item.get("snippet", "").strip(),
                    "query": query,
                }

                if not result["title"] or not result["url"]:
                    continue

                result["clean_url"] = clean_url(result["url"])
                result["score"] = score_result(result)

                if is_probably_job(result):
                    all_results.append(result)

        except Exception as e:
            print(f"Google error for query [{query}]: {e}")

    deduped = {}
    for result in all_results:
        key = result["clean_url"]
        if key not in deduped or result["score"] > deduped[key]["score"]:
            deduped[key] = result

    filtered = sorted(
        deduped.values(),
        key=lambda r: r["score"],
        reverse=True
    )

    Path("index.html").write_text(build_html(filtered), encoding="utf-8")

    print(f"Generated index.html with {len(filtered)} ranked job results.")

import os
import re
import html
import requests
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

GOOGLE_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX_ID")

AIRCRAFT_KEYWORDS = {
    "Caravan": ["caravan", "c208", "cessna 208", "grand caravan"],
    "PC-12": ["pc-12", "pc12", "pilatus"],
    "King Air": ["king air", "be200", "b200", "be90", "c90", "b90"],
    "Navajo": ["navajo", "pa-31", "pa31", "chieftain"],
    "Comanche": ["comanche", "pa-24", "pa24"],
}

PRIMARY_AIRCRAFT_BOOST = {
    "Caravan": 45,
    "PC-12": 45,
    "King Air": 35,
    "Navajo": 20,
    "Comanche": 5,
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
    "cargo", "charter", "part 135", "135", "hiring", "apply", "position"
]

BAD_TERMS = [
    "flight school", "training course", "type rating", "simulator", "forum",
    "salary", "how much", "resume", "template", "news", "crash",
    "accident", "wikipedia", "facebook", "youtube", "reddit",
    "mechanic", "maintenance technician", "electrician", "truck driver",
    "navajo express", "jeep", "piper comanche parts", "for sale"
]

GENERIC_TERMS = [
    "browse jobs", "search jobs", "all jobs", "aviation jobs",
    "pilot jobs", "career center", "job search", "job board",
    "open positions", "current openings"
]

SEARCH_QUERIES = [
    '"Cessna Caravan" pilot job cargo',
    '"C208" pilot job cargo',
    '"Grand Caravan" pilot job "Part 135"',
    '"PC-12" pilot job "Part 135"',
    '"Pilatus PC-12" captain job',
    '"PC-12" first officer job',
    '"King Air" SIC pilot job',
    '"King Air" "Part 135" pilot job',
    '"PA-31" cargo pilot job',
    '"Navajo" cargo pilot job',
    '"Phoenix" "Caravan" pilot job',
    '"Arizona" "PC-12" pilot job',
    '"Phoenix" "King Air" SIC pilot job',
    '"low time" cargo pilot job "Part 135"',
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


def normalize_url(url):
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc.lower().replace("www.", ""), path, "", "", ""))


def source_name(url):
    return urlparse(url).netloc.lower().replace("www.", "")


def text_blob(result):
    return f"{result.get('title', '')} {result.get('snippet', '')} {result.get('url', '')}".lower()


def badge_class(tag):
    return re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")


def aircraft_matches(result):
    blob = text_blob(result)
    found = []
    for label, terms in AIRCRAFT_KEYWORDS.items():
        if any(term in blob for term in terms):
            found.append(label)
    return found


def mission_matches(result):
    blob = text_blob(result)
    found = []
    for label, terms in MISSION_KEYWORDS.items():
        if any(term in blob for term in terms):
            found.append(label)
    return found


def find_tags(result):
    return aircraft_matches(result) + mission_matches(result)


def is_generic_or_multi_aircraft(result):
    blob = text_blob(result)
    aircraft = aircraft_matches(result)

    if len(aircraft) >= 2:
        return True

    if any(term in blob for term in GENERIC_TERMS):
        return True

    if "jobs" in blob and len(aircraft) == 0:
        return True

    return False


def score_result(result):
    blob = text_blob(result)
    score = 0
    aircraft = aircraft_matches(result)

    for term in GOOD_TERMS:
        if term in blob:
            score += 8

    for aircraft_name in aircraft:
        score += PRIMARY_AIRCRAFT_BOOST.get(aircraft_name, 10)

    for mission_terms in MISSION_KEYWORDS.values():
        if any(term in blob for term in mission_terms):
            score += 12

    if "pilot" in blob:
        score += 30
    if "captain" in blob or "sic" in blob or "first officer" in blob:
        score += 25
    if "apply" in blob or "hiring" in blob or "position" in blob:
        score += 20
    if "phoenix" in blob or "arizona" in blob or "scottsdale" in blob:
        score += 35
    if "cargo" in blob or "part 135" in blob:
        score += 25

    for bad in BAD_TERMS:
        if bad in blob:
            score -= 60

    if is_generic_or_multi_aircraft(result):
        score -= 90

    if "comanche" in blob and "pilot" not in blob:
        score -= 80

    return score


def is_probably_job(result):
    blob = text_blob(result)

    if any(bad in blob for bad in BAD_TERMS):
        return False

    has_aircraft = len(aircraft_matches(result)) > 0
    has_job_intent = any(term in blob for term in [
        "pilot", "captain", "sic", "pic", "first officer",
        "cargo", "charter", "part 135", "apply", "hiring", "job", "position"
    ])

    return has_aircraft and has_job_intent


def loose_duplicate_key(result):
    title = result.get("title", "").lower()
    title = re.sub(r"[^a-z0-9 ]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    title = title.replace("pilot job", "pilot").replace("jobs", "job")
    return f"{source_name(result['url'])}|{title[:80]}"


def build_html(results):
    updated_on = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    filter_tags = [
        "Caravan", "PC-12", "King Air", "Navajo", "Comanche",
        "Cargo", "Part 135", "SIC", "PIC", "Low-Time Friendly", "Arizona", "Generic / Multi-Aircraft"
    ]

    cards = ""
    for r in results:
        tags = find_tags(r)
        if r["generic"]:
            tags.append("Generic / Multi-Aircraft")

        tag_classes = " ".join(badge_class(t) for t in tags)
        generic_class = "generic-card" if r["generic"] else ""

        badges = "".join(f'<span class="badge">{html.escape(tag)}</span>' for tag in tags)

        cards += f"""
        <article class="job-card {generic_class} {tag_classes}" data-search="{html.escape((r['title'] + ' ' + r['snippet'] + ' ' + ' '.join(tags)).lower())}">
          <div class="card-top">
            <span class="source">{html.escape(source_name(r['url']))}</span>
            <span class="score">Fit {r['score']}</span>
          </div>
          <h2><a href="{html.escape(r['url'])}" target="_blank" rel="noopener noreferrer">{html.escape(r['title'])}</a></h2>
          <p>{html.escape(r['snippet'])}</p>
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
      --bg:#eef3f8; --panel:#fff; --text:#142033; --muted:#667085;
      --border:#d9e2ec; --accent:#2563eb; --accent-soft:#dbeafe;
      --shadow:rgba(15,23,42,.10); --generic:#fff7ed; --generic-border:#fdba74;
    }}
    body.dark {{
      --bg:#0f172a; --panel:#172033; --text:#f8fafc; --muted:#aab4c5;
      --border:#334155; --accent:#60a5fa; --accent-soft:#1e3a5f;
      --shadow:rgba(0,0,0,.35); --generic:#2a2117; --generic-border:#9a5a18;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Arial,sans-serif; background:var(--bg); color:var(--text); }}
    header {{ padding:28px 24px; background:linear-gradient(135deg,#102a43,#2563eb); color:white; }}
    header h1 {{ margin:0 0 8px; font-size:2rem; }}
    header p {{ margin:0; color:rgba(255,255,255,.85); }}
    main {{ max-width:1400px; margin:0 auto; padding:22px; }}
    .toolbar {{ background:var(--panel); border:1px solid var(--border); border-radius:16px; padding:16px; margin-bottom:20px; box-shadow:0 8px 24px var(--shadow); }}
    .top-row {{ display:flex; gap:12px; justify-content:space-between; align-items:center; flex-wrap:wrap; margin-bottom:14px; }}
    #searchBox {{ flex:1; min-width:260px; padding:11px 12px; border-radius:10px; border:1px solid var(--border); background:var(--bg); color:var(--text); font-size:1rem; }}
    #themeToggle {{ padding:11px 14px; border-radius:10px; border:1px solid var(--border); background:var(--panel); color:var(--text); cursor:pointer; }}
    .filters {{ display:flex; gap:8px; flex-wrap:wrap; }}
    .filter-btn {{ border:1px solid var(--border); background:var(--bg); color:var(--text); border-radius:999px; padding:8px 12px; cursor:pointer; font-size:.92rem; }}
    .filter-btn.active {{ background:var(--accent); border-color:var(--accent); color:white; }}
    .summary {{ color:var(--muted); margin-top:12px; font-size:.95rem; }}
    .grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:18px; }}
    .job-card {{ background:var(--panel); border:1px solid var(--border); border-radius:16px; padding:16px; box-shadow:0 8px 24px var(--shadow); min-height:230px; display:flex; flex-direction:column; }}
    .job-card.generic-card {{ background:var(--generic); border-color:var(--generic-border); opacity:.86; }}
    .card-top {{ display:flex; justify-content:space-between; gap:8px; margin-bottom:10px; }}
    .source {{ color:var(--muted); font-size:.82rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .score {{ background:var(--accent-soft); color:var(--accent); border-radius:999px; padding:4px 8px; font-size:.78rem; font-weight:bold; white-space:nowrap; }}
    .job-card h2 {{ font-size:1.05rem; margin:0 0 10px; line-height:1.25; }}
    .job-card a {{ color:var(--accent); text-decoration:none; }}
    .job-card a:hover {{ text-decoration:underline; }}
    .job-card p {{ color:var(--muted); font-size:.92rem; line-height:1.4; margin:0 0 12px; flex:1; }}
    .badges {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:auto; }}
    .badge {{ background:var(--accent-soft); color:var(--accent); border-radius:999px; padding:4px 8px; font-size:.75rem; font-weight:bold; }}
    .no-results {{ display:none; text-align:center; padding:30px; color:var(--muted); }}
    footer {{ text-align:center; color:var(--muted); padding:24px; font-size:.85rem; }}
    @media(max-width:1000px) {{ .grid {{ grid-template-columns:repeat(2,1fr); }} }}
    @media(max-width:680px) {{ .grid {{ grid-template-columns:1fr; }} header h1 {{ font-size:1.6rem; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Phoenix Pilot Jobs</h1>
    <p>Ranked for first-turbine opportunities: Caravan, PC-12, King Air, cargo, SIC, Part 135, and Arizona-friendly leads.</p>
  </header>
  <main>
    <section class="toolbar">
      <div class="top-row">
        <input id="searchBox" type="search" placeholder="Search: Phoenix, cargo, SIC, PC-12..." />
        <button id="themeToggle">🌙 Toggle Theme</button>
      </div>
      <div class="filters">{filter_buttons}</div>
      <div class="summary">Updated: {updated_on} · <span id="visibleCount">{len(results)}</span> showing of {len(results)} ranked results</div>
    </section>
    <section id="jobsGrid" class="grid">{cards}</section>
    <div id="noResults" class="no-results">No jobs match those filters.</div>
  </main>
  <footer>Generic or multi-aircraft listings are shaded and sorted toward the bottom.</footer>

  <script>
    const filterButtons=document.querySelectorAll(".filter-btn");
    const cards=document.querySelectorAll(".job-card");
    const searchBox=document.getElementById("searchBox");
    const visibleCount=document.getElementById("visibleCount");
    const noResults=document.getElementById("noResults");
    const themeToggle=document.getElementById("themeToggle");

    function applyFilters(){{
      const active=Array.from(filterButtons).filter(b=>b.classList.contains("active")).map(b=>b.dataset.filter);
      const q=searchBox.value.trim().toLowerCase();
      let count=0;
      cards.forEach(card=>{{
        const matchFilter=active.length===0 || active.some(f=>card.classList.contains(f));
        const matchSearch=q==="" || card.dataset.search.includes(q);
        const show=matchFilter && matchSearch;
        card.style.display=show?"flex":"none";
        if(show) count++;
      }});
      visibleCount.textContent=count;
      noResults.style.display=count===0?"block":"none";
    }}

    filterButtons.forEach(btn=>btn.addEventListener("click",()=>{{btn.classList.toggle("active");applyFilters();}}));
    searchBox.addEventListener("input",applyFilters);
    themeToggle.addEventListener("click",()=>{{
      document.body.classList.toggle("dark");
      localStorage.setItem("theme",document.body.classList.contains("dark")?"dark":"light");
    }});
    if(localStorage.getItem("theme")==="dark") document.body.classList.add("dark");
  </script>
</body>
</html>"""


if __name__ == "__main__":
    if not GOOGLE_KEY or not GOOGLE_CX:
        raise RuntimeError("Missing GOOGLE_API_KEY or GOOGLE_CX_ID.")

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

                result["normalized_url"] = normalize_url(result["url"])

                if not is_probably_job(result):
                    continue

                result["generic"] = is_generic_or_multi_aircraft(result)
                result["score"] = score_result(result)
                all_results.append(result)

        except Exception as e:
            print(f"Google error for query [{query}]: {e}")

    deduped = {}

    for r in all_results:
        keys = [r["normalized_url"], loose_duplicate_key(r)]
        existing_key = next((k for k in keys if k in deduped), None)

        if existing_key:
            if r["score"] > deduped[existing_key]["score"]:
                deduped[existing_key] = r
        else:
            deduped[r["normalized_url"]] = r

    filtered = sorted(
        deduped.values(),
        key=lambda r: (r["generic"], -r["score"])
    )

    Path("index.html").write_text(build_html(filtered), encoding="utf-8")
    print(f"Generated index.html with {len(filtered)} ranked job results.")

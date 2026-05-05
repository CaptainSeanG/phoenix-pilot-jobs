import os
import re
import html
import requests
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

# ==============================
# API Keys from GitHub Secrets
# ==============================
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX_ID")

# ==============================
# Sean-specific pilot profile
# ==============================
PILOT_PROFILE = {
    "total_time": 1300,
    "multi_time": 25,
    "turbine_time": 0,
    "location": "Phoenix",
    "willing_to_relocate": False,
}

# ==============================
# Aircraft matching
# ==============================
AIRCRAFT_KEYWORDS = {
    "Caravan": [
        "caravan", "c208", "c-208", "cessna 208", "grand caravan"
    ],
    "PC-12": [
        "pc-12", "pc12", "pilatus"
    ],
    "King Air": [
        "king air", "be200", "b200", "be90", "c90", "b90", "kingair"
    ],
    "Navajo": [
        "navajo", "pa-31", "pa31", "chieftain"
    ],
    "Comanche": [
        "comanche", "pa-24", "pa24"
    ],
}

PRIMARY_AIRCRAFT_BOOST = {
    "Caravan": 85,
    "PC-12": 80,
    "King Air": 55,
    "Navajo": 25,
    "Comanche": 5,
}

# ==============================
# Mission / fit keywords
# ==============================
MISSION_KEYWORDS = {
    "Cargo": [
        "cargo", "freight", "fedex feeder", "ups feeder",
        "feeder", "night freight"
    ],
    "Part 135": [
        "part 135", "135", "charter", "on demand", "air taxi"
    ],
    "SIC": [
        "sic", "second in command", "first officer", "fo",
        "right seat", "co-pilot", "copilot"
    ],
    "PIC": [
        "pic", "captain", "pilot in command"
    ],
    "Low-Time Friendly": [
        "low time", "low-time", "entry level", "commercial pilot",
        "minimum 500", "minimum 750", "minimum 1000",
        "1000 hours", "1,000 hours",
        "1200 hours", "1,200 hours",
        "training provided", "will train"
    ],
    "Arizona": [
        "phoenix", "phx", "scottsdale", "mesa", "tempe",
        "glendale", "deer valley", "dvt", "tucson",
        "arizona", "az", "prescott", "flagstaff"
    ],
    "Commutable": [
        "home based", "home-based", "commutable", "commute",
        "rotational", "7 on 7 off", "8 on 6 off",
        "2 weeks on", "two weeks on"
    ],
    "Target Company": [
        "empire airlines", "ameriflight", "cutter aviation",
        "westwind", "advanced air", "boutique air",
        "southern airways", "key lime", "martinaire",
        "berry aviation", "guardian flight", "plane sense",
        "planesense", "tradewind aviation"
    ],
}

GOOD_TERMS = [
    "pilot", "captain", "sic", "pic", "first officer",
    "second in command", "co-pilot", "copilot",
    "hiring", "apply", "position", "opening", "career",
    "cargo", "freight", "part 135", "135", "charter",
    "fedex feeder", "ups feeder",
    "caravan", "c208", "cessna 208", "pc-12", "pc12",
    "pilatus", "king air", "be200", "b200", "be90", "c90",
    "phoenix", "arizona", "scottsdale", "mesa",
    "home based", "commutable", "training provided", "will train"
]

# Hard rejection terms: these are usually not job leads at all.
HARD_REJECT_TERMS = [
    "wikipedia", "facebook", "youtube", "reddit",
    "truck driver", "electrician", "navajo express",
    "jeep", "piper comanche parts", "for sale"
]

# Penalty terms: these may still appear on a page, but they reduce confidence.
BAD_PENALTY_TERMS = [
    "flight school", "training course", "type rating", "simulator",
    "forum", "salary", "how much", "resume", "template", "news",
    "crash", "accident", "mechanic", "maintenance technician",
    "certified flight instructor", "cfi only", "cfii required",
    "flight instructor", "instructor pilot"
]

GENERIC_TERMS = [
    "browse jobs", "search jobs", "all jobs", "aviation jobs",
    "pilot jobs", "career center", "job search", "job board",
    "open positions", "current openings", "view all jobs",
    "all pilot jobs", "pilot job board", "aviation job search"
]

# ==============================
# Search queries
# ==============================
SEARCH_QUERIES = [
    # Best first-turbine path: Caravan cargo / FedEx feeder
    '"Cessna Caravan" cargo pilot job',
    '"C208" cargo pilot job',
    '"Cessna 208" pilot job "Part 135"',
    '"Grand Caravan" pilot job cargo',
    '"FedEx Feeder" Caravan pilot job',
    '"Empire Airlines" Caravan pilot Phoenix',
    '"Ameriflight" Caravan pilot Arizona',
    '"Caravan" "1200 hours" pilot job',

    # PC-12 path
    '"PC-12" SIC pilot job',
    '"PC-12" first officer job',
    '"Pilatus PC-12" pilot job "Part 135"',
    '"PC-12" pilot job Phoenix',
    '"PC-12" "training provided" pilot job',
    '"Cutter Aviation" PC-12 pilot Phoenix',
    '"Advanced Air" PC-12 pilot Arizona',
    '"PlaneSense" PC-12 first officer job',

    # King Air SIC / Part 135 path
    '"King Air" SIC pilot job',
    '"King Air" first officer job',
    '"King Air" pilot job "Part 135"',
    '"BE200" SIC pilot job',
    '"King Air" pilot job Phoenix',
    '"Westwind" pilot King Air Phoenix',

    # Piston cargo fallback
    '"PA-31" cargo pilot job',
    '"Navajo" cargo pilot job',
    '"Piper Navajo" pilot job cargo',

    # Phoenix / Arizona focused
    '"Phoenix" pilot job Caravan',
    '"Phoenix" pilot job "PC-12"',
    '"Phoenix" pilot job "King Air"',
    '"Arizona" cargo pilot job',
    '"Arizona" "Part 135" pilot job',
    '"Scottsdale" pilot job "Part 135"',

    # Low-time / commercial pilot friendly
    '"commercial pilot" cargo pilot job "1200 hours"',
    '"low time" cargo pilot job "Part 135"',
    '"low time" Caravan pilot job',
]

MAX_RESULTS_PER_QUERY = 10


# ==============================
# Google Search
# ==============================
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


# ==============================
# Utility helpers
# ==============================
def normalize_url(url):
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return urlunparse((
        parsed.scheme,
        parsed.netloc.lower().replace("www.", ""),
        path,
        "",
        "",
        ""
    ))


def source_name(url):
    return urlparse(url).netloc.lower().replace("www.", "")


def text_blob(result):
    return f"{result.get('title', '')} {result.get('snippet', '')} {result.get('url', '')}".lower()


def has_any(blob, terms):
    return any(term in blob for term in terms)


def badge_class(tag):
    return re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")


def parse_hour_number(raw):
    return int(raw.replace(",", ""))


# ==============================
# Matching helpers
# ==============================
def aircraft_matches(result):
    blob = text_blob(result)
    found = []
    for label, terms in AIRCRAFT_KEYWORDS.items():
        if has_any(blob, terms):
            found.append(label)
    return found


def mission_matches(result):
    blob = text_blob(result)
    found = []
    for label, terms in MISSION_KEYWORDS.items():
        if has_any(blob, terms):
            found.append(label)
    return found


def extract_total_time_requirement(blob):
    patterns = [
        r"\b(?:minimum|min\.?|requires|required)\s*(?:of\s*)?(\d{1,2},?\d{3})\+?\s*(?:hours|hrs|tt|total time|total)\b",
        r"\b(\d{1,2},?\d{3})\+?\s*(?:hours|hrs)\s*(?:total|tt|total time)\b",
        r"\b(\d{1,2},?\d{3})\+?\s*(?:tt|total time)\b",
    ]

    matches = []
    for pattern in patterns:
        for match in re.findall(pattern, blob):
            try:
                value = parse_hour_number(match)
                if 500 <= value <= 10000:
                    matches.append(value)
            except ValueError:
                pass

    return min(matches) if matches else None


def extract_multi_time_requirement(blob):
    patterns = [
        r"\b(\d{2,4})\+?\s*(?:hours|hrs)?\s*(?:of\s*)?(?:multi|multi-engine|multi engine)\b",
        r"\b(?:multi|multi-engine|multi engine)\s*(?:time)?\s*(?:required|min\.?|minimum)?\s*(?:of\s*)?(\d{2,4})\+?\b",
    ]

    matches = []
    for pattern in patterns:
        for match in re.findall(pattern, blob):
            try:
                value = int(match)
                if 10 <= value <= 3000:
                    matches.append(value)
            except ValueError:
                pass

    return min(matches) if matches else None


def detects_1200_hour_fit(blob):
    return has_any(blob, [
        "1200 hours", "1,200 hours", "1200 total", "1,200 total",
        "1200 tt", "1,200 tt", "part 135 ifr", "135 ifr"
    ])


def detects_1500_hour_requirement(blob):
    return has_any(blob, [
        "1500 hours", "1,500 hours", "1500 total",
        "1,500 total", "1500 tt", "1,500 tt"
    ])


def detects_turbine_requirement(blob):
    return has_any(blob, [
        "turbine time required", "previous turbine",
        "turbine experience required", "500 turbine",
        "500 hours turbine", "500 hours of turbine",
        "1000 turbine", "1,000 turbine",
        "1000 hours turbine", "1,000 hours turbine"
    ])


def detects_atp_requirement(blob):
    return has_any(blob, [
        "atp required",
        "airline transport pilot required",
        "airline transport pilot certificate required",
        "airline transport pilot license required"
    ])


def detects_relocation_requirement(blob):
    return has_any(blob, [
        "relocation required", "must relocate", "must be willing to relocate"
    ])


def detects_training_provided(blob):
    return has_any(blob, [
        "training provided", "will train", "company paid training",
        "no turbine time required", "turbine not required"
    ])


def is_generic_or_multi_aircraft(result):
    blob = text_blob(result)
    aircraft = aircraft_matches(result)

    if len(aircraft) >= 2:
        return True

    if has_any(blob, GENERIC_TERMS):
        return True

    return False


def is_probably_job(result):
    blob = text_blob(result)

    if has_any(blob, HARD_REJECT_TERMS):
        return False

    has_aircraft = len(aircraft_matches(result)) > 0
    has_job_intent = has_any(blob, [
        "pilot", "captain", "sic", "pic", "first officer",
        "second in command", "cargo", "freight", "charter",
        "part 135", "apply", "hiring", "job", "position",
        "opening", "career"
    ])

    return has_aircraft and has_job_intent


# ==============================
# Sean-specific evaluation
# ==============================
def evaluate_result(result):
    blob = text_blob(result)

    score = 0
    tags = []
    reasons = []
    warnings = []

    aircraft = aircraft_matches(result)
    missions = mission_matches(result)

    tags.extend(aircraft)
    tags.extend(missions)

    # Aircraft scoring
    for aircraft_name in aircraft:
        boost = PRIMARY_AIRCRAFT_BOOST.get(aircraft_name, 10)
        score += boost
        reasons.append(f"{aircraft_name} match")

    # General good terms
    for term in GOOD_TERMS:
        if term in blob:
            score += 8

    # Mission scoring
    mission_weights = {
        "Cargo": 55,
        "Part 135": 50,
        "SIC": 65,
        "PIC": 20,
        "Low-Time Friendly": 55,
        "Arizona": 75,
        "Commutable": 40,
        "Target Company": 85,
    }

    for mission in missions:
        boost = mission_weights.get(mission, 15)
        score += boost
        reasons.append(mission)

    # Direct job intent
    if "pilot" in blob:
        score += 35
        reasons.append("Pilot role")

    if "captain" in blob:
        score += 25
        reasons.append("Captain/PIC wording")

    if has_any(blob, ["sic", "first officer", "second in command", "right seat", "co-pilot", "copilot"]):
        score += 70
        reasons.append("SIC/right-seat path")

    if has_any(blob, ["apply", "hiring", "position", "opening"]):
        score += 30
        reasons.append("Looks apply-able")

    # Phoenix / Arizona sweet spot
    if has_any(blob, [
        "phoenix", "phx", "deer valley", "dvt", "scottsdale",
        "mesa", "glendale", "tucson", "arizona", "az"
    ]):
        score += 80
        reasons.append("Phoenix/Arizona signal")

    # Strong combo boosts
    if any(a in aircraft for a in ["Caravan", "PC-12", "King Air"]):
        if has_any(blob, ["cargo", "freight", "fedex feeder", "ups feeder"]):
            score += 55
            reasons.append("Turbine/cargo path")

        if has_any(blob, ["part 135", "135", "charter", "on demand"]):
            score += 50
            reasons.append("Part 135 path")

        if has_any(blob, ["sic", "first officer", "second in command", "right seat"]):
            score += 65
            reasons.append("Good entry turbine angle")

    # Known companies / targets
    target_companies = [
        "empire airlines", "ameriflight", "cutter aviation",
        "westwind", "advanced air", "boutique air",
        "key lime", "martinaire", "berry aviation",
        "southern airways", "guardian flight",
        "plane sense", "planesense", "tradewind aviation"
    ]

    if has_any(blob, target_companies):
        score += 90
        reasons.append("Target company")

    # Requirement detection: total time
    total_req = extract_total_time_requirement(blob)

    if total_req is not None:
        if total_req <= PILOT_PROFILE["total_time"]:
            score += 85
            reasons.append(f"Meets {total_req:,} TT")
            tags.append("Meets TT")
        elif total_req <= 1500:
            score -= 35
            warnings.append(f"Near Future: {total_req:,} TT")
            tags.append("Near Future")
        else:
            score -= 110
            warnings.append(f"High TT Req: {total_req:,}")
            tags.append("High Time Required")
    elif detects_1200_hour_fit(blob):
        score += 85
        reasons.append("Meets 1200 TT")
        tags.append("Meets TT")

    if detects_1500_hour_requirement(blob) and PILOT_PROFILE["total_time"] < 1500:
        score -= 35
        warnings.append("Near Future: 1500 TT")
        tags.append("Near Future")

    # Requirement detection: multi time
    multi_req = extract_multi_time_requirement(blob)

    if multi_req is not None:
        if multi_req <= PILOT_PROFILE["multi_time"]:
            score += 20
            reasons.append(f"Meets {multi_req} multi")
            tags.append("Meets Multi")
        else:
            penalty = 70 if multi_req <= 100 else 120
            score -= penalty
            warnings.append(f"Multi Concern: {multi_req} multi")
            tags.append("Multi Concern")

    # Requirement detection: turbine time
    if detects_turbine_requirement(blob):
        score -= 140
        warnings.append("Turbine time required")
        tags.append("Turbine Required")

    # Requirement detection: ATP
    if detects_atp_requirement(blob):
        score -= 160
        warnings.append("ATP required")
        tags.append("ATP Required")

    # Requirement detection: relocation
    if detects_relocation_requirement(blob):
        score -= 90
        warnings.append("Relocation required")
        tags.append("Relocation Required")

    # Training provided is a big deal for your first turbine step
    if detects_training_provided(blob):
        score += 60
        reasons.append("Training provided")
        tags.append("Training Provided")

    # Penalty terms
    for bad in BAD_PENALTY_TERMS:
        if bad in blob:
            score -= 55
            warnings.append("Possible non-job/noisy result")
            break

    # Generic / multi-aircraft bucket
    generic = is_generic_or_multi_aircraft(result)

    if generic:
        score -= 110
        warnings.append("Generic/multi-aircraft listing")
        tags.append("Generic / Multi-Aircraft")

    # Comanche is noisy unless clearly pilot-job related
    if "comanche" in blob and "pilot" not in blob:
        score -= 100
        warnings.append("Comanche noise risk")

    # Clean up duplicated labels while preserving order
    tags = list(dict.fromkeys(tags))
    reasons = list(dict.fromkeys(reasons))
    warnings = list(dict.fromkeys(warnings))

    return {
        "score": score,
        "tags": tags,
        "reasons": reasons,
        "warnings": warnings,
        "generic": generic,
    }


def loose_duplicate_key(result):
    title = result.get("title", "").lower()
    title = re.sub(r"[^a-z0-9 ]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip()

    replacements = [
        ("pilot jobs", "pilot job"),
        ("aviation jobs", "aviation job"),
        ("first officer", "fo"),
        ("second in command", "sic"),
    ]

    for old, new in replacements:
        title = title.replace(old, new)

    return f"{source_name(result['url'])}|{title[:90]}"


# ==============================
# HTML generation
# ==============================
def build_html(results):
    updated_on = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    filter_tags = [
        "Caravan", "PC-12", "King Air", "Navajo",
        "Cargo", "Part 135", "SIC", "PIC",
        "Low-Time Friendly", "Arizona", "Commutable",
        "Target Company", "Meets TT", "Near Future",
        "Multi Concern", "Turbine Required", "ATP Required",
        "Training Provided", "Generic / Multi-Aircraft"
    ]

    cards = ""

    for r in results:
        tags = r["tags"]
        reasons = r["reasons"]
        warnings = r["warnings"]

        all_classes = " ".join(badge_class(t) for t in tags)
        generic_class = "generic-card" if r["generic"] else ""

        tag_badges = "".join(
            f'<span class="badge tag-badge">{html.escape(tag)}</span>'
            for tag in tags
        )

        reason_badges = "".join(
            f'<span class="badge reason-badge">{html.escape(reason)}</span>'
            for reason in reasons[:6]
        )

        warning_badges = "".join(
            f'<span class="badge warning-badge">{html.escape(warning)}</span>'
            for warning in warnings[:5]
        )

        why_block = ""
        if reason_badges or warning_badges:
            why_block = f"""
            <div class="why">
              <div class="why-label">Why:</div>
              <div class="why-badges">
                {reason_badges}
                {warning_badges}
              </div>
            </div>
            """

        search_text = html.escape(
            (
                r["title"] + " " +
                r["snippet"] + " " +
                source_name(r["url"]) + " " +
                " ".join(tags) + " " +
                " ".join(reasons) + " " +
                " ".join(warnings)
            ).lower()
        )

        cards += f"""
        <article class="job-card {generic_class} {all_classes}" data-search="{search_text}">
          <div class="card-top">
            <span class="source">{html.escape(source_name(r['url']))}</span>
            <span class="score">Fit {r['score']}</span>
          </div>

          <h2>
            <a href="{html.escape(r['url'])}" target="_blank" rel="noopener noreferrer">
              {html.escape(r['title'])}
            </a>
          </h2>

          <p>{html.escape(r['snippet'])}</p>

          <div class="badges">{tag_badges}</div>

          {why_block}
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
      --good: #047857;
      --good-soft: #d1fae5;
      --warn: #b45309;
      --warn-soft: #ffedd5;
      --generic: #fff7ed;
      --generic-border: #fdba74;
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
      --good: #6ee7b7;
      --good-soft: #064e3b;
      --warn: #fbbf24;
      --warn-soft: #422006;
      --generic: #2a2117;
      --generic-border: #9a5a18;
      --shadow: rgba(0, 0, 0, 0.35);
    }}

    * {{
      box-sizing: border-box;
    }}

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
      max-width: 950px;
      line-height: 1.45;
    }}

    main {{
      max-width: 1450px;
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

    .profile-note {{
      color: var(--muted);
      margin-top: 6px;
      font-size: 0.88rem;
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
      min-height: 275px;
      display: flex;
      flex-direction: column;
    }}

    .job-card.generic-card {{
      background: var(--generic);
      border-color: var(--generic-border);
      opacity: 0.90;
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

    .badges,
    .why-badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}

    .badge {{
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 0.73rem;
      font-weight: bold;
    }}

    .tag-badge {{
      background: var(--accent-soft);
      color: var(--accent);
    }}

    .reason-badge {{
      background: var(--good-soft);
      color: var(--good);
    }}

    .warning-badge {{
      background: var(--warn-soft);
      color: var(--warn);
    }}

    .why {{
      margin-top: 12px;
      padding-top: 10px;
      border-top: 1px solid var(--border);
    }}

    .why-label {{
      font-size: 0.75rem;
      color: var(--muted);
      margin-bottom: 6px;
      font-weight: bold;
      text-transform: uppercase;
      letter-spacing: 0.04em;
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

    @media (max-width: 1050px) {{
      .grid {{
        grid-template-columns: repeat(2, 1fr);
      }}
    }}

    @media (max-width: 700px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}

      header h1 {{
        font-size: 1.6rem;
      }}
    }}
  </style>
</head>

<body>
  <header>
    <h1>Phoenix Pilot Jobs</h1>
    <p>
      Ranked for Sean’s first-turbine path: 1,300 TT, 25 multi, Phoenix-based, no turbine yet.
      Best fits favor Caravan, PC-12, King Air SIC, cargo, Part 135, Arizona, commutable, and training-provided opportunities.
    </p>
  </header>

  <main>
    <section class="toolbar">
      <div class="top-row">
        <input id="searchBox" type="search" placeholder="Search: Phoenix, cargo, SIC, PC-12, 1200, Empire..." />
        <button id="themeToggle">🌙 Toggle Theme</button>
      </div>

      <div class="filters">
        {filter_buttons}
      </div>

      <div class="summary">
        Updated: {updated_on} · <span id="visibleCount">{len(results)}</span> showing of {len(results)} ranked results
      </div>

      <div class="profile-note">
        Fit score is personalized for 1,300 total time / 25 multi / Phoenix-based first turbine opportunity hunting.
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
    Generic, high-requirement, or multi-aircraft listings are penalized and pushed lower.
  </footer>

  <script>
    const filterButtons = document.querySelectorAll(".filter-btn");
    const cards = document.querySelectorAll(".job-card");
    const searchBox = document.getElementById("searchBox");
    const visibleCount = document.getElementById("visibleCount");
    const noResults = document.getElementById("noResults");
    const themeToggle = document.getElementById("themeToggle");

    function applyFilters() {{
      const active = Array.from(filterButtons)
        .filter(btn => btn.classList.contains("active"))
        .map(btn => btn.dataset.filter);

      const q = searchBox.value.trim().toLowerCase();
      let count = 0;

      cards.forEach(card => {{
        const matchFilter =
          active.length === 0 ||
          active.some(filter => card.classList.contains(filter));

        const matchSearch =
          q === "" ||
          card.dataset.search.includes(q);

        const show = matchFilter && matchSearch;
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
      localStorage.setItem(
        "theme",
        document.body.classList.contains("dark") ? "dark" : "light"
      );
    }});

    if (localStorage.getItem("theme") === "dark") {{
      document.body.classList.add("dark");
    }}
  </script>
</body>
</html>
"""


# ==============================
# Main build
# ==============================
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

                result["normalized_url"] = normalize_url(result["url"])

                if not is_probably_job(result):
                    continue

                evaluation = evaluate_result(result)

                result["score"] = evaluation["score"]
                result["tags"] = evaluation["tags"]
                result["reasons"] = evaluation["reasons"]
                result["warnings"] = evaluation["warnings"]
                result["generic"] = evaluation["generic"]

                all_results.append(result)

        except Exception as e:
            print(f"Google error for query [{query}]: {e}")

    # Stronger dedupe:
    # 1. Exact normalized URL
    # 2. Same source + similar title
    deduped = {}
    lookup = {}

    for r in all_results:
        keys = {
            r["normalized_url"],
            loose_duplicate_key(r)
        }

        existing_id = next((lookup[k] for k in keys if k in lookup), None)

        if existing_id:
            if r["score"] > deduped[existing_id]["score"]:
                deduped[existing_id] = r

            for k in keys:
                lookup[k] = existing_id
        else:
            new_id = r["normalized_url"]
            deduped[new_id] = r

            for k in keys:
                lookup[k] = new_id

    filtered = sorted(
        deduped.values(),
        key=lambda r: (
            r["generic"],
            "ATP Required" in r["tags"],
            "Turbine Required" in r["tags"],
            "Multi Concern" in r["tags"],
            -r["score"]
        )
    )

    Path("index.html").write_text(build_html(filtered), encoding="utf-8")

    print(f"Generated index.html with {len(filtered)} Sean-tuned ranked job results.")

"""
Run with: python -m app.discover_companies [--resume Sakshi_Patil_Resume]

Solves "the same small company list returns the same jobs every day":
searches Adzuna (recent postings only) for terms matching your role
profile, extracts company names you're NOT already tracking or haven't
already applied to, then VERIFIES each candidate against the real
Greenhouse/Lever public APIs before adding it — never adds a company on
a guess alone. Verified companies get written to discovered_companies.json,
which app.ingest also reads alongside app/companies.py's static list.

This is a discovery pass, not a replacement for companies.py — think of
it as "widen the pool," run occasionally (e.g. weekly), not necessarily
every single day, since it costs real Adzuna API quota (free tier: ~1000
calls/month).
"""

import argparse
import json
import re
from pathlib import Path

import httpx

from app.companies import ASHBY_COMPANIES, GREENHOUSE_COMPANIES, LEVER_COMPANIES
from app.connectors import adzuna
from app.db import get_raw_conn
from app.role_config import get_role_profile

DISCOVERED_PATH = Path("app") / "discovered_companies.json"
MAX_QUERIES = 5
MAX_DAYS_OLD = 3
CANDIDATES_PER_QUERY = 20


def load_discovered() -> dict:
    if DISCOVERED_PATH.exists():
        return json.loads(DISCOVERED_PATH.read_text())
    return {"greenhouse": [], "lever": []}


def save_discovered(data: dict) -> None:
    DISCOVERED_PATH.write_text(json.dumps(data, indent=2))


def get_already_tracked_companies(conn) -> set[str]:
    """Skip suggesting companies already in companies.py, already
    discovered before, already in the jobs table, or already applied to
    by anyone — the whole point is genuinely NEW coverage."""
    tracked = {c.lower() for c in GREENHOUSE_COMPANIES + LEVER_COMPANIES + ASHBY_COMPANIES}
    discovered = load_discovered()
    tracked |= {c.lower() for c in discovered.get("greenhouse", [])}
    tracked |= {c.lower() for c in discovered.get("lever", [])}

    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT lower(company) FROM jobs")
        tracked |= {row[0] for row in cur.fetchall()}
        cur.execute(
            "SELECT DISTINCT lower(j.company) FROM applications a JOIN jobs j ON j.id = a.job_id"
        )
        tracked |= {row[0] for row in cur.fetchall()}

    return tracked


def guess_slug(company_name: str) -> str:
    """Best-effort guess for verification only — a wrong guess just fails
    verification (404) and gets silently skipped, never added blindly."""
    name = re.sub(r"\b(inc|llc|corp|ltd|co)\b\.?", "", company_name, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", name.lower())


def verify_greenhouse(slug: str) -> bool:
    try:
        resp = httpx.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=10.0)
        return resp.status_code == 200 and len(resp.json().get("jobs", [])) > 0
    except httpx.HTTPError:
        return False


def verify_lever(slug: str) -> bool:
    try:
        resp = httpx.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=10.0)
        return resp.status_code == 200 and len(resp.json()) > 0
    except httpx.HTTPError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover new companies via Adzuna, verified against real ATS APIs.")
    parser.add_argument("--resume", default=None, help="version_label to base search queries on")
    args = parser.parse_args()

    profile = get_role_profile(args.resume)
    queries = profile["role_specific_markers"][:MAX_QUERIES]

    conn = get_raw_conn()
    try:
        exclude = get_already_tracked_companies(conn)
    finally:
        conn.close()

    print(f"Searching {len(queries)} terms on Adzuna (last {MAX_DAYS_OLD} days)...\n")

    candidate_companies = {}
    for query in queries:
        results = adzuna.search(query, max_days_old=MAX_DAYS_OLD, results_per_page=CANDIDATES_PER_QUERY)
        print(f"[adzuna] '{query}': {len(results)} results")
        for r in results:
            name = r.get("company", {}).get("display_name", "").strip()
            if name and name.lower() not in exclude:
                candidate_companies[name] = r

    print(f"\n{len(candidate_companies)} genuinely new company names found. Verifying against real ATS APIs...\n")

    discovered = load_discovered()
    newly_added = 0
    for name in candidate_companies:
        slug = guess_slug(name)
        if verify_greenhouse(slug):
            discovered["greenhouse"].append(slug)
            print(f"  [verified] {name} -> Greenhouse: '{slug}'")
            newly_added += 1
        elif verify_lever(slug):
            discovered["lever"].append(slug)
            print(f"  [verified] {name} -> Lever: '{slug}'")
            newly_added += 1

    save_discovered(discovered)
    print(f"\nDone. {newly_added} new companies verified and added to {DISCOVERED_PATH}.")
    print("Run 'python -m app.ingest' to pull jobs from them.")


if __name__ == "__main__":
    main()
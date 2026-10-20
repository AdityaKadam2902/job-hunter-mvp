"""
Cross-source deduplication for Task 2. content_hash (existing) only
catches EXACT duplicates from the same source re-scraped. This catches
the same real role appearing via multiple sources — e.g. a Snowflake job
on Ashby directly AND surfaced again via Adzuna's search.

Lower priority number = more authoritative = kept as canonical when a
duplicate group is found.
"""

import re

SOURCE_PRIORITY = {
    "greenhouse": 1,
    "lever": 1,
    "ashby": 1,
    "workday": 1,
    "smartrecruiters": 1,
    "remoteok": 2,
    "adzuna": 3,
}

_NOISE_WORDS = re.compile(r"\b(remote|hybrid|onsite|new|open)\b", re.I)
_PUNCT = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


def normalize_for_dedup(company: str, title: str, location: str | None) -> str:
    """Produces a stable grouping key — same real role should normalize
    to the same string even with minor formatting differences between
    sources (e.g. 'Senior ML Engineer (Remote)' vs 'Senior ML Engineer')."""
    def clean(s: str) -> str:
        s = s.lower()
        s = _NOISE_WORDS.sub("", s)
        s = _PUNCT.sub("", s)
        s = _WHITESPACE.sub(" ", s).strip()
        return s

    company_clean = clean(company)
    title_clean = clean(title)
    # Location deliberately excluded from the key by default when missing
    # (many sources don't reliably provide it) — company + title alone is
    # already a strong signal for the same real role.
    return f"{company_clean}|{title_clean}"


def pick_canonical(duplicate_group: list[dict]) -> dict:
    """Given a list of job dicts (same normalized key), returns the one
    to keep — lowest source priority number wins, tie-broken by earliest
    scraped_at (the one we actually saw first)."""
    return min(
        duplicate_group,
        key=lambda j: (SOURCE_PRIORITY.get(j["source"], 99), j["scraped_at"]),
    )


def find_and_mark_duplicates(conn) -> int:
    """Run as a separate pass AFTER ingest, over the whole jobs table —
    not wired into fetch_all(), since duplicates can exist between an
    old already-stored job and a newly-ingested one from a different
    source. Call this once per ingest run. Returns count marked."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, source, company, title, location, scraped_at FROM jobs "
            "WHERE is_duplicate_of IS NULL AND closed_at IS NULL"
        )
        cols = [d[0] for d in cur.description]
        jobs = [dict(zip(cols, row)) for row in cur.fetchall()]

    groups: dict[str, list[dict]] = {}
    for job in jobs:
        key = normalize_for_dedup(job["company"], job["title"], job["location"])
        groups.setdefault(key, []).append(job)

    marked = 0
    with conn.cursor() as cur:
        for group in groups.values():
            if len(group) < 2:
                continue
            canonical = pick_canonical(group)
            for job in group:
                if job["id"] != canonical["id"]:
                    cur.execute(
                        "UPDATE jobs SET is_duplicate_of = %s WHERE id = %s",
                        (canonical["id"], job["id"]),
                    )
                    marked += 1
    conn.commit()
    return marked
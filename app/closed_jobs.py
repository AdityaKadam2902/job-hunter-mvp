"""
Closed job detection for Task 2. Only meaningful for direct-ATS sources
(Greenhouse/Lever/Ashby/Workday/SmartRecruiters) — each ingest pulls the
FULL current set of open roles for a company, so anything previously
stored for that company+source but missing from the current pull is
reasonably inferred to have closed. Not applied to RemoteOK/Adzuna, since
those are partial, query-based pulls — absence from one search doesn't
mean a listing closed.
"""

DIRECT_ATS_SOURCES = {"greenhouse", "lever", "ashby", "workday", "smartrecruiters"}

# Closed-detection is ONLY valid when a pull returns the company's COMPLETE
# list of open roles. Workday is capped at 100 jobs/company (of ~750-2000)
# and SmartRecruiters is a single page (limit=100) — for those, a job
# rotating out of the capped window is NOT evidence it closed, so they are
# excluded here. Revisit if those connectors ever paginate fully.
COMPLETE_PULL_SOURCES = {"greenhouse", "lever", "ashby"}

# (source, company_slug) -> set of external_ids seen in THIS run's raw,
# unfiltered pull. Filled by track_pull() from inside fetch_all()'s loops.
_current_pulls: dict[tuple[str, str], set[str]] = {}


def track_pull(raw_jobs: list) -> None:
    """One-line hook, called right after each direct-ATS fetch with the
    RAW (pre-relevance-filter) job list. Reads source/company_slug off the
    records themselves so callers never have to pass or guess them.

    CRITICAL GUARD: an empty list is ignored, not recorded. A failed
    fetch returns [] (e.g. a 404 or timeout) — recording that would make
    every stored job at that company look 'closed'. Absence of data is
    not evidence of closure."""
    if not raw_jobs:
        return
    source = raw_jobs[0].source
    if source not in COMPLETE_PULL_SOURCES:
        return
    key = (source, raw_jobs[0].company_slug)
    _current_pulls[key] = {j.external_id for j in raw_jobs}


def mark_closed_jobs(conn) -> int:
    """Run once after the fetch phase. For every company that was
    successfully pulled this run, any stored, still-open job from that
    company+source that is absent from the pull gets closed_at = now().
    Returns the number of jobs newly marked closed."""
    closed_total = 0
    with conn.cursor() as cur:
        for (source, company_slug), current_ids in _current_pulls.items():
            cur.execute(
                "SELECT external_id FROM jobs "
                "WHERE source = %s AND company_slug = %s AND closed_at IS NULL",
                (source, company_slug),
            )
            previously_known = {row[0] for row in cur.fetchall()}
            newly_closed = find_newly_closed_external_ids(current_ids, previously_known)
            if newly_closed:
                cur.execute(
                    "UPDATE jobs SET closed_at = now() "
                    "WHERE source = %s AND company_slug = %s AND external_id = ANY(%s)",
                    (source, company_slug, list(newly_closed)),
                )
                closed_total += len(newly_closed)
    conn.commit()
    return closed_total


def find_newly_closed_external_ids(
    current_external_ids: set[str],
    previously_known_external_ids: set[str],
) -> set[str]:
    """Pure set logic — previously known but not in the current pull =
    newly closed. Kept as a standalone function so it's testable without
    a database."""
    return previously_known_external_ids - current_external_ids
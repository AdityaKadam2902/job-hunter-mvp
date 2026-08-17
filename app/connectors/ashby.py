import httpx

from app.normalize import JobRecord

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def fetch_jobs(company_slug: str) -> list[JobRecord]:
    """Fetch open roles for one Ashby company board. Ashby doesn't return a
    display company name in the response, so we title-case the slug as a
    reasonable fallback (e.g. 'openai' -> 'Openai') — good enough for
    display purposes, not worth an extra lookup call for."""
    url = BASE_URL.format(slug=company_slug)
    try:
        resp = httpx.get(url, params={"includeCompensation": "true"}, timeout=15.0)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"[ashby] failed for '{company_slug}': {e}")
        return []

    data = resp.json()
    postings = data.get("jobs", [])

    jobs = []
    for raw in postings:
        # isListed defaults True if missing — Ashby's own scrapers treat
        # missing isListed as "still active" rather than filtering it out.
        if not raw.get("isListed", True):
            continue

        # Description field naming has been inconsistent across Ashby's own
        # docs/changelog wording ('descriptionText' vs 'descriptionPlain') —
        # try both rather than assume one and silently get empty text.
        description = raw.get("descriptionText") or raw.get("descriptionPlain") or ""

        record = JobRecord(
            source="ashby",
            company=company_slug.replace("-", " ").title(),
            company_slug=company_slug,
            external_id=str(raw.get("id", "")),
            title=raw.get("title", "").strip(),
            location=raw.get("location"),
            description=description,
            url=raw.get("jobUrl") or raw.get("applyUrl"),
        ).finalize()
        jobs.append(record)
    return jobs
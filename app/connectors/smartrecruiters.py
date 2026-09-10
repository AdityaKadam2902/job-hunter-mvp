import httpx

from app.normalize import JobRecord

BASE_URL = "https://api.smartrecruiters.com/v1/companies/{company}/postings"


def fetch_jobs(company_identifier: str) -> list[JobRecord]:
    """Fetch open roles for one SmartRecruiters company. Public endpoint,
    no auth required for the basic postings list. SmartRecruiters powers
    many larger enterprises (Visa, Bosch, IKEA-scale) — a genuinely
    different company-size tier than Greenhouse/Lever/Ashby tend to skew
    toward (more startup/mid-size)."""
    url = BASE_URL.format(company=company_identifier)
    try:
        resp = httpx.get(url, params={"limit": 100}, timeout=15.0)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"[smartrecruiters] failed for '{company_identifier}': {e}")
        return []

    data = resp.json()
    postings = data.get("content", [])

    jobs = []
    for raw in postings:
        location = raw.get("location", {})
        location_str = location.get("city") or location.get("country") or None

        record = JobRecord(
            source="smartrecruiters",
            company=raw.get("company", {}).get("name", company_identifier),
            company_slug=company_identifier.lower(),
            external_id=str(raw.get("id", "")),
            title=raw.get("name", "").strip(),
            location=location_str,
            # NOTE: the list endpoint doesn't include the full description —
            # that requires one extra GET per job (same tradeoff as the
            # Workday connector). Title + location is enough for the
            # relevance filter and embedding; skipping per-job detail
            # fetches keeps this source fast and request-light.
            description="",
            url=f"https://jobs.smartrecruiters.com/{company_identifier}/{raw.get('id', '')}",
        ).finalize()
        jobs.append(record)
    return jobs
import httpx

from app.normalize import JobRecord

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def fetch_jobs(company_slug: str) -> list[JobRecord]:
    """Fetch open roles for one Greenhouse company. Returns [] and prints a
    warning on failure instead of raising — one bad slug shouldn't kill the
    whole ingest run."""
    url = BASE_URL.format(slug=company_slug)
    try:
        resp = httpx.get(url, timeout=15.0)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"[greenhouse] failed for '{company_slug}': {e}")
        return []

    data = resp.json()
    jobs = []
    for raw in data.get("jobs", []):
        record = JobRecord(
            source="greenhouse",
            company=raw.get("company_name") or company_slug,
            company_slug=company_slug,
            external_id=str(raw["id"]),
            title=raw.get("title", "").strip(),
            location=(raw.get("location") or {}).get("name"),
            description=_strip_html(raw.get("content", "")),
            url=raw.get("absolute_url"),
        ).finalize()
        jobs.append(record)
    return jobs


def _strip_html(html: str) -> str:
    """Greenhouse job descriptions come as HTML. Minimal strip — good enough
    for embedding and keyword matching, not meant to be pretty-printed."""
    import re

    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()

import httpx

from app.normalize import JobRecord

BASE_URL = "https://api.lever.co/v0/postings/{slug}?mode=json"


def fetch_jobs(company_slug: str) -> list[JobRecord]:
    """Fetch open roles for one Lever company. Returns [] and prints a
    warning on failure instead of raising."""
    url = BASE_URL.format(slug=company_slug)
    try:
        resp = httpx.get(url, timeout=15.0)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"[lever] failed for '{company_slug}': {e}")
        return []

    data = resp.json()
    jobs = []
    for raw in data:
        description_parts = [raw.get("descriptionPlain", "")]
        for section in raw.get("lists", []) or []:
            description_parts.append(section.get("text", ""))
            for item in section.get("content", "").split("\n") if isinstance(section.get("content"), str) else []:
                description_parts.append(item)

        record = JobRecord(
            source="lever",
            company=company_slug,
            company_slug=company_slug,
            external_id=raw.get("id", ""),
            title=raw.get("text", "").strip(),
            location=(raw.get("categories") or {}).get("location"),
            description=" ".join(p for p in description_parts if p).strip(),
            url=raw.get("hostedUrl"),
        ).finalize()
        jobs.append(record)
    return jobs

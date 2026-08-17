import httpx

from app.normalize import JobRecord

BASE_URL = "https://remoteok.com/api"


def fetch_jobs(tag: str) -> list[JobRecord]:
    """Fetch remote jobs by tag (e.g. 'machine-learning', 'python', 'ai').
    Unlike Greenhouse/Lever, this covers many companies in ONE call — no
    per-company slug to find or maintain. content_hash dedup in normalize.py
    handles overlap if you query multiple tags that return the same job."""
    try:
        resp = httpx.get(
            BASE_URL,
            params={"tag": tag},
            headers={"User-Agent": "job-hunter-mvp (personal project, low volume)"},
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"[remoteok] failed for tag '{tag}': {e}")
        return []

    data = resp.json()
    # RemoteOK's first array element is always a legal/notice object, not a
    # job — skip it rather than let it crash the parser downstream.
    postings = [item for item in data if isinstance(item, dict) and item.get("id")]

    jobs = []
    for raw in postings:
        record = JobRecord(
            source="remoteok",
            company=raw.get("company", "Unknown"),
            company_slug=raw.get("company", "unknown").lower().replace(" ", "-"),
            external_id=str(raw.get("id", "")),
            title=raw.get("position", "").strip(),
            location=raw.get("location") or "Remote",
            description=raw.get("description", ""),
            url=raw.get("url") or f"https://remoteok.com/remote-jobs/{raw.get('id')}",
        ).finalize()
        jobs.append(record)
    return jobs
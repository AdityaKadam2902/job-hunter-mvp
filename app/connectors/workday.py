import httpx

from app.normalize import JobRecord

MAX_PAGES = 5  # 20 jobs/page = 100 jobs per company cap, keeps this polite
# and bounded rather than trying to pull thousands of roles from one
# enterprise tenant on every run.


def fetch_jobs(tenant: str, wd_server: str, site: str, display_name: str) -> list[JobRecord]:
    """Workday has no documented public API, but every tenant's own careers
    page calls this same internal JSON endpoint — same principle as the
    other connectors, just a less obvious URL. Unlike Greenhouse/Lever/Ashby,
    this needs realistic browser-like headers (User-Agent, Referer) or
    Workday's bot protection can reject the request."""
    base_url = f"https://{tenant}.{wd_server}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    referer = f"https://{tenant}.{wd_server}.myworkdayjobs.com/en-US/{site}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) job-hunter-mvp/personal-project",
        "Referer": referer,
    }

    jobs: list[JobRecord] = []
    offset = 0
    limit = 20

    for _ in range(MAX_PAGES):
        try:
            resp = httpx.post(
                base_url,
                json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
                headers=headers,
                timeout=15.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            print(f"[workday] failed for '{tenant}/{site}' at offset {offset}: {e}")
            break

        data = resp.json()
        postings = data.get("jobPostings", [])
        if not postings:
            break

        for raw in postings:
            external_path = raw.get("externalPath", "")
            record = JobRecord(
                source="workday",
                company=display_name,
                company_slug=f"{tenant}-{site}".lower(),
                external_id=external_path or raw.get("bulletFields", [""])[0],
                title=raw.get("title", "").strip(),
                location=raw.get("locationsText"),
                # NOTE: listing endpoint doesn't include the full job
                # description — that requires one extra GET request PER JOB
                # (/wday/cxs/{tenant}/{site}{externalPath}), which isn't
                # worth the request volume for an initial discovery pass.
                # Title + location is enough for embedding/matching; a
                # future improvement could fetch full descriptions only for
                # jobs that already rank highly on title alone.
                description="",
                url=f"https://{tenant}.{wd_server}.myworkdayjobs.com/en-US/{site}{external_path}",
            ).finalize()
            jobs.append(record)

        total = data.get("total", 0)
        offset += limit
        if offset >= total:
            break

    return jobs
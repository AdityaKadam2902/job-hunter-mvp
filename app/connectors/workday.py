import time

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

    # Diagnostic run revealed: page 0 correctly reports the true total
    # (e.g. total=2000 for NVIDIA), but page 1 reports total=0 despite
    # still returning real postings. Root cause: each request was
    # independent, with no session state carried over — a real browser
    # would automatically carry cookies from the first response into the
    # next request, and Workday's backend appears to rely on that for
    # correctly tracking pagination context. Using one persistent client
    # for all pages of one company fixes this the same way a browser
    # naturally would.
    with httpx.Client(headers=headers, timeout=15.0) as client:
        confirmed_total = None  # captured once, from page 0 only

        for page_num in range(MAX_PAGES):
            try:
                resp = client.post(
                    base_url,
                    json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                print(f"[workday] failed for '{tenant}/{site}' at offset {offset}: {e}")
                break

            data = resp.json()
            postings = data.get("jobPostings", [])
            reported_total = data.get("total", 0)

            if page_num == 0:
                confirmed_total = reported_total
            # NOTE: 'total' only reliably reports the real count on the
            # first request (e.g. total=2000 for NVIDIA), then reports 0 on
            # every subsequent page despite still returning real postings —
            # confirmed deterministic across multiple runs. Not bot
            # blocking (would be inconsistent/return an error); this is
            # Workday's own API only computing 'total' fresh on page one.
            # Fix: capture it once, don't re-trust it on later pages.

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
                    description="",
                    url=f"https://{tenant}.{wd_server}.myworkdayjobs.com/en-US/{site}{external_path}",
                ).finalize()
                jobs.append(record)

            offset += limit
            if offset >= confirmed_total:
                break
            time.sleep(1.5)  # polite pause between paginated requests to the same company

    return jobs
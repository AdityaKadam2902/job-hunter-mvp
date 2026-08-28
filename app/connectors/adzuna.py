import httpx

from app.config import settings

BASE_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def fetch_jobs_for_role(query: str, max_days_old: int = 3, results_per_page: int = 20) -> list:
    """Fetches actual JOB LISTINGS matching a role query directly — unlike
    company-wide Greenhouse/Lever pulls, this is inherently relevance-
    targeted from the start, not filtered after the fact. Returns
    normalized JobRecord objects ready for the jobs table."""
    from app.normalize import JobRecord  # local import avoids a circular import at module load

    results = search(query, max_days_old=max_days_old, results_per_page=results_per_page)
    jobs = []
    for r in results:
        company = r.get("company", {}).get("display_name", "Unknown")
        record = JobRecord(
            source="adzuna",
            company=company,
            company_slug=company.lower().replace(" ", "-"),
            external_id=str(r.get("id", "")),
            title=r.get("title", "").strip(),
            location=(r.get("location") or {}).get("display_name"),
            description=r.get("description", ""),
            url=r.get("redirect_url"),
        ).finalize()
        jobs.append(record)
    return jobs


def search(query: str, country: str = "us", max_days_old: int = 3, results_per_page: int = 20) -> list[dict]:
    """Raw Adzuna search results — used for company DISCOVERY, not as a
    direct job source in the main jobs table. max_days_old=3 by default:
    the whole point of this is fresh signal, not a broad historical pull.

    NOTE: this connector could not be tested against the live Adzuna API
    from this environment (api.adzuna.com isn't reachable from this
    sandbox) — built against their documented response shape, same
    honesty as the original Workday connector before it was verified
    against real data. Watch the first real run closely."""
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        raise SystemExit(
            "ADZUNA_APP_ID / ADZUNA_APP_KEY not set in .env. "
            "Sign up free at developer.adzuna.com to get both."
        )

    url = BASE_URL.format(country=country, page=1)
    try:
        resp = httpx.get(
            url,
            params={
                "app_id": settings.adzuna_app_id,
                "app_key": settings.adzuna_app_key,
                "what": query,
                "max_days_old": max_days_old,
                "results_per_page": results_per_page,
                "content-type": "application/json",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"[adzuna] search failed for '{query}': {e}")
        return []

    return resp.json().get("results", [])
"""
Run with: python -m app.ingest

Fetches jobs from configured Greenhouse/Lever companies, dedupes against
what's already in the DB, embeds only new/changed listings, and upserts.

Deliberately re-runnable: run this daily and it'll only do embedding work
(the expensive-ish step) on genuinely new postings.
"""

from app.companies import ASHBY_COMPANIES, GREENHOUSE_COMPANIES, LEVER_COMPANIES, REMOTEOK_TAGS, WORKDAY_COMPANIES
from app.connectors import ashby, greenhouse, lever, remoteok, workday
from app.db import get_raw_conn
from app.embeddings import embed_text
from app.normalize import JobRecord, utcnow
import json
from pathlib import Path
from app.connectors import adzuna
from app.relevance_filter import build_shared_relevance_markers, is_relevant_title
from app.role_config import get_role_profile

def _load_discovered_companies():
    path = Path("app") / "discovered_companies.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"greenhouse": [], "lever": []}

_discovered = _load_discovered_companies()


def fetch_all() -> list[JobRecord]:
    records = []
    relevance_markers = build_shared_relevance_markers()

    # --- Greenhouse ---
    for slug in GREENHOUSE_COMPANIES:
        raw_jobs = greenhouse.fetch_jobs(slug)
        filtered = [j for j in raw_jobs if is_relevant_title(j.title, relevance_markers)]
        print(f"[greenhouse] {slug}: {len(raw_jobs)} jobs, {len(filtered)} kept")
        records.extend(filtered)

    # --- Lever ---
    for slug in LEVER_COMPANIES:
        raw_jobs = lever.fetch_jobs(slug)
        filtered = [j for j in raw_jobs if is_relevant_title(j.title, relevance_markers)]
        print(f"[lever] {slug}: {len(raw_jobs)} jobs, {len(filtered)} kept")
        records.extend(filtered)

    # --- Ashby ---
    for slug in ASHBY_COMPANIES:
        raw_jobs = ashby.fetch_jobs(slug)
        filtered = [j for j in raw_jobs if is_relevant_title(j.title, relevance_markers)]
        print(f"[ashby] {slug}: {len(raw_jobs)} jobs, {len(filtered)} kept")
        records.extend(filtered)

    # --- Workday ---
    for tenant, wd_server, site, display_name in WORKDAY_COMPANIES:
        raw_jobs = workday.fetch_jobs(tenant, wd_server, site, display_name)
        filtered = [j for j in raw_jobs if is_relevant_title(j.title, relevance_markers)]
        print(f"[workday] {display_name}: {len(raw_jobs)} jobs, {len(filtered)} kept")
        records.extend(filtered)

    # --- RemoteOK: NOT filtered, already searched by tag ---
    for tag in REMOTEOK_TAGS:
        jobs = remoteok.fetch_jobs(tag)
        print(f"[remoteok] tag '{tag}': {len(jobs)} jobs")
        records.extend(jobs)

    # --- Adzuna: NOT filtered, already searched by role query ---
        # --- Adzuna: NOW filtered too — evidence from a real run showed
    # Adzuna's search is broad full-text matching, not title-precise, so
    # results included noise like "Janitor Engineer" and "Graphic Designer"
    # even from an "ai"-targeted query. The earlier assumption that Adzuna
    # results were already precise enough to skip filtering was wrong.
    for version_label in {"default"}:
        profile = get_role_profile(version_label if version_label != "default" else None)
        for query in profile["role_specific_markers"][:3]:
            raw_jobs = adzuna.fetch_jobs_for_role(query, max_days_old=3)
            filtered = [j for j in raw_jobs if is_relevant_title(j.title, relevance_markers)]
            print(f"[adzuna] '{query}': {len(raw_jobs)} jobs, {len(filtered)} kept")
            records.extend(filtered)

    return records


def get_existing_hashes(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT content_hash FROM jobs")
        return {row[0] for row in cur.fetchall()}


def upsert_job(conn, record: JobRecord, embedding: list[float]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO jobs (
                source, company, company_slug, external_id, title, location,
                description, url, engagement_type, seniority, content_hash,
                scraped_at, last_seen_at, embedding
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (content_hash) DO UPDATE SET
                last_seen_at = EXCLUDED.last_seen_at,
                url = EXCLUDED.url
            """,
            (
                record.source, record.company, record.company_slug, record.external_id,
                record.title, record.location, record.description, record.url,
                record.engagement_type, record.seniority, record.content_hash,
                utcnow(), utcnow(), embedding,
            ),
        )


def main() -> None:
    records = fetch_all()
    if not records:
        print(
            "No jobs fetched. Check app/companies.py has real slugs in it "
            "(it ships empty on purpose — see README)."
        )
        return

    conn = get_raw_conn()
    try:
        existing = get_existing_hashes(conn)
        new_records = [r for r in records if r.content_hash not in existing]

        print(f"Fetched {len(records)} total, {len(new_records)} new — embedding new ones now...")

        embedded_count = 0
        total_new = len(new_records)
        for i, record in enumerate(new_records, start=1):
            text = f"{record.title}\n{record.company}\n{record.description or ''}"
            print(f"[embed] ({i}/{total_new}) {record.company}: {record.title[:60]}", flush=True)
            try:
                vector = embed_text(text)
            except Exception as e:
                print(f"[embed] skipped '{record.title}' at {record.company}: {e}")
                continue
            upsert_job(conn, record, vector)
            embedded_count += 1
            if i % 20 == 0:
                conn.commit()  # checkpoint periodically so a crash mid-run doesn't lose everything

        # Also refresh last_seen_at for already-known jobs still showing up
        # (i.e. still-open postings), without re-embedding them.
        already_seen = [r for r in records if r.content_hash in existing]
        for record in already_seen:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE jobs SET last_seen_at = %s WHERE content_hash = %s",
                    (utcnow(), record.content_hash),
                )

        conn.commit()
        print(f"Done. {embedded_count} new jobs embedded and stored.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
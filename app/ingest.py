"""
Run with: python -m app.ingest

Fetches jobs from configured Greenhouse/Lever companies, dedupes against
what's already in the DB, embeds only new/changed listings, and upserts.

Deliberately re-runnable: run this daily and it'll only do embedding work
(the expensive-ish step) on genuinely new postings.
"""

from app.companies import GREENHOUSE_COMPANIES, LEVER_COMPANIES
from app.connectors import greenhouse, lever
from app.db import get_raw_conn
from app.embeddings import embed_text
from app.normalize import JobRecord, utcnow


def fetch_all() -> list[JobRecord]:
    records: list[JobRecord] = []

    for slug in GREENHOUSE_COMPANIES:
        jobs = greenhouse.fetch_jobs(slug)
        print(f"[greenhouse] {slug}: {len(jobs)} jobs")
        records.extend(jobs)

    for slug in LEVER_COMPANIES:
        jobs = lever.fetch_jobs(slug)
        print(f"[lever] {slug}: {len(jobs)} jobs")
        records.extend(jobs)

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
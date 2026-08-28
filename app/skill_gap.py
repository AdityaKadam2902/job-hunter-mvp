"""
Run with: python -m app.skill_gap [--resume Sakshi_Patil_Resume]

Pulls your top N matches, asks Groq what skills each posting actually
requires, aggregates across all of them, and surfaces skills that show up
repeatedly but AREN'T in your resume — a concrete "add this to get past
more screens" signal, grounded in your real current match pool, not
generic advice.

Bounded to TOP_N_JOBS Groq calls per run (same cost-conscious pattern as
app.tailor and app.auto_label) — this spends real API quota, so it's a
deliberate command, not something to run on a tight loop.
"""

import argparse
import json
from collections import Counter

import httpx

from app.config import settings
from app.db import get_raw_conn
from app.tailor import get_resume, get_top_jobs

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
TOP_N_JOBS = 20
MIN_FREQUENCY = 2  # a skill must appear in at least this many top jobs to count as a real gap, not noise

_SYSTEM_PROMPT = (
    "You extract required technical skills from a single job posting. "
    "Return ONLY a JSON array of lowercase skill strings — no explanation, "
    "no markdown fences. Include languages, frameworks, tools, and named "
    "techniques explicitly mentioned as required or preferred. Do not "
    "include soft skills, degrees, or years-of-experience phrases."
)


import time

def extract_job_required_skills(title: str, description: str, max_retries: int = 3) -> list[str] | None:
    """Same retry-with-backoff pattern already proven in app.auto_label.
    Returns None (not []) on total failure, so the caller can distinguish
    'genuinely no skills extracted' from 'this job was never actually
    analyzed' — silently treating a rate-limited skip as a clean zero
    would make the final report's job count dishonest."""
    prompt = f"Job: {title}\n\nDescription: {(description or '')[:2000]}"

    for attempt in range(max_retries):
        try:
            resp = httpx.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                },
                timeout=30.0,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("retry-after", 5)) if resp.headers.get("retry-after", "5").isdigit() else 5
                print(f"    [rate limit] waiting {wait}s before retry ({attempt + 1}/{max_retries})...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.strip("`").removeprefix("json").strip()
            skills = json.loads(content)
            return [str(s).strip().lower() for s in skills if str(s).strip()] if isinstance(skills, list) else []
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"  [skip] '{title}' after {max_retries} attempts: {e}")
                return None
            time.sleep(2)

    return None


def compute_gaps(resume_skills: set[str], job_skill_lists: list[list[str]], min_frequency: int) -> list[tuple[str, int]]:
    """Pure aggregation logic, kept separate from I/O so it's testable
    without a real DB or Groq call. A skill counts as a gap if it appears
    in at least min_frequency jobs and isn't already in resume_skills."""
    counts = Counter()
    for skills in job_skill_lists:
        for s in set(skills):  # set() so a skill mentioned twice in one posting only counts once
            counts[s] += 1

    gaps = [(skill, count) for skill, count in counts.items() if skill not in resume_skills and count >= min_frequency]
    gaps.sort(key=lambda x: -x[1])
    return gaps


def get_resume_id_by_label(conn, label: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM resumes WHERE version_label = %s", (label,))
        row = cur.fetchone()
    if row is None:
        raise SystemExit(f"No resume found with version_label '{label}'.")
    return row[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Find skills frequently required in your top matches but missing from your resume.")
    parser.add_argument("--resume", default=None, help="version_label of the resume to check (defaults to active)")
    args = parser.parse_args()

    if not settings.groq_api_key:
        raise SystemExit("GROQ_API_KEY not set in .env — required for this script.")

    conn = get_raw_conn()
    try:
        resume_id = get_resume_id_by_label(conn, args.resume) if args.resume else None
        resume = get_resume(conn, resume_id)
        resume_skills = {s.lower() for s in (resume.get("skills") or [])}

        jobs = get_top_jobs(conn, resume, TOP_N_JOBS)
        if not jobs:
            print("No jobs found — run 'python -m app.ingest' first.")
            return

        print(f"Checking top {len(jobs)} matches for '{resume['version_label']}' against required skills...\n")

        job_skill_lists = []
        skipped_count = 0
        for i, job in enumerate(jobs, start=1):
            print(f"  ({i}/{len(jobs)}) {job['title']} — {job['company']}")
            result = extract_job_required_skills(job["title"], job["description"] or "")
            if result is None:
                skipped_count += 1
            else:
                job_skill_lists.append(result)
    finally:
        conn.close()

    analyzed_count = len(job_skill_lists)
    gaps = compute_gaps(resume_skills, job_skill_lists, MIN_FREQUENCY)

    print(f"\n{'='*60}")
    if skipped_count > 0:
        print(f"NOTE: {skipped_count} of {len(jobs)} jobs could not be analyzed (rate limits or "
              f"errors) and are NOT included below. This report reflects {analyzed_count} jobs, "
              f"not the full {len(jobs)}.\n")

    if not gaps:
        print(f"No significant gaps found across the {analyzed_count} jobs actually analyzed.")
        return

    print(f"Skills that show up in {MIN_FREQUENCY}+ of your {analyzed_count} analyzed matches "
          f"but aren't in your resume:\n")
    for skill, count in gaps[:15]:
        print(f"  {skill:30s} appears in {count}/{analyzed_count} analyzed matches")
    print(f"\nConsider adding these to your resume if you genuinely have the experience —\n"
          f"never claim a skill you don't actually have (see app.tailor's no-fabrication rule).")


if __name__ == "__main__":
    main()
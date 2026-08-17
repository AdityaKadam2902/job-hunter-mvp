"""
Run with: python -m app.tailor

For your top N matched jobs (from the most recent app.match run), asks
Groq to suggest 2-3 tailored resume bullets per job — pulled from what's
ACTUALLY in your resume, reworded/reprioritized to speak to that specific
job description, not generic advice invented from nothing.

Reuses the same resume text and Groq infrastructure already built for
skill extraction — this is deliberately a thin script, not a new pipeline.
"""

import json

import httpx

from app.config import settings
from app.db import get_raw_conn
from app.scoring import (
    ai_specificity_score,
    domain_fit_score,
    extract_resume_skills,
    final_score,
    keyword_overlap_score,
    seniority_fit_score,
)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
TOP_N_TO_TAILOR = 5

_SYSTEM_PROMPT = (
    "You help tailor resumes to specific job postings. You will be given a "
    "candidate's full resume text and a specific job description. Suggest "
    "2-3 resume bullet points that would make this candidate's application "
    "stronger for THIS SPECIFIC job. Rules: "
    "1) Every suggestion must be based on something ACTUALLY in the resume "
    "— reworded, reprioritized, or reframed toward the job's language, "
    "never invented or exaggerated experience the resume doesn't support. "
    "2) Prefer surfacing relevant existing bullets that might be buried "
    "lower in the resume, over rewriting top bullets. "
    "3) Keep each suggestion to one line. "
    "Return ONLY a JSON array of strings, no explanation, no markdown fences."
)


def get_active_resume_text(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT raw_text FROM resumes WHERE is_active = true ORDER BY uploaded_at DESC LIMIT 1")
        row = cur.fetchone()
    if row is None:
        raise SystemExit("No active resume found. Run 'python -m app.resume_ingest' first.")
    return row[0]


def get_top_jobs(conn, resume_text: str, limit: int):
    """Applies the SAME 5-factor rubric as match.py — similarity, keyword
    overlap, seniority fit, domain fit, AI specificity — not just raw
    embedding similarity. An earlier version of this function only ordered
    by similarity, which meant tailoring effort could be spent on jobs that
    weren't actually your real top matches (e.g. a senior-tagged role that
    match.py's seniority penalty would rank much lower)."""
    resume_skills = extract_resume_skills(resume_text)

    with conn.cursor() as cur:
        cur.execute("SELECT embedding FROM resumes WHERE is_active = true ORDER BY uploaded_at DESC LIMIT 1")
        resume_embedding = cur.fetchone()[0]

        # Same two-stage pattern as match.py: cheap similarity pull for a
        # shortlist, THEN apply the full rubric only on that shortlist.
        cur.execute(
            """
            SELECT id, company, title, description, url, seniority,
                   1 - (embedding <=> %s) AS similarity
            FROM jobs
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT 100
            """,
            (resume_embedding, resume_embedding),
        )
        cols = [d[0] for d in cur.description]
        candidates = [dict(zip(cols, row)) for row in cur.fetchall()]

    scored = []
    for job in candidates:
        job_text = f"{job['title']} {job['description'] or ''}"
        kw_score = keyword_overlap_score(resume_skills, job_text)
        sen_score = seniority_fit_score(job["seniority"])
        dom_score = domain_fit_score(job["title"])
        ai_score = ai_specificity_score(job["title"], job["description"] or "")
        score = final_score(job["similarity"], kw_score, sen_score, dom_score, ai_score)
        scored.append({**job, "final_score": score})

    scored.sort(key=lambda j: j["final_score"], reverse=True)
    return scored[:limit]


def suggest_bullets(resume_text: str, job_title: str, company: str, description: str) -> list[str]:
    prompt = (
        f"Resume:\n{resume_text[:3000]}\n\n"
        f"Job: {job_title} at {company}\n"
        f"Description: {(description or '')[:2000]}"
    )
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
                "temperature": 0.3,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.strip("`").removeprefix("json").strip()
        bullets = json.loads(content)
        if not isinstance(bullets, list):
            raise ValueError("expected a JSON array")
        return [str(b).strip() for b in bullets if str(b).strip()]
    except Exception as e:
        print(f"  [failed] {e}")
        return []


def main() -> None:
    if not settings.groq_api_key:
        raise SystemExit("GROQ_API_KEY not set in .env — required for this script.")

    conn = get_raw_conn()
    try:
        resume_text = get_active_resume_text(conn)
        jobs = get_top_jobs(conn, resume_text, TOP_N_TO_TAILOR)
    finally:
        conn.close()

    if not jobs:
        print("No jobs found — run 'python -m app.ingest' first.")
        return

    print(f"Generating tailored bullet suggestions for your top {len(jobs)} matches...\n")

    for i, job in enumerate(jobs, start=1):
        print(f"{i}. {job['title']} — {job['company']}")
        print(f"   {job['url']}")
        bullets = suggest_bullets(resume_text, job["title"], job["company"], job["description"] or "")
        if bullets:
            for b in bullets:
                print(f"   • {b}")
        else:
            print("   (no suggestions generated)")
        print()


if __name__ == "__main__":
    main()
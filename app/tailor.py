"""
Run with: python -m app.tailor

For your top N matched jobs, asks Groq to suggest 2-3 tailored resume
bullets per job — pulled from what's ACTUALLY in your resume, reworded
toward that specific job description, never invented.
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
    get_sub_role_tags,
    keyword_overlap_score,
    matched_skills,
    seniority_fit_score,
)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile was deprecated by Groq on 2026-06-17
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


def get_resume(conn, resume_id: str | None = None) -> dict:
    """Fetch a specific resume by id, or fall back to the most recently
    uploaded active one if no id given (preserves old single-user
    behavior for existing scripts). This is the actual fix that unblocks
    multi-person use — before, get_top_jobs always silently re-queried
    'the' active resume internally, making it impossible to match against
    a SPECIFIC person's resume by choice."""
    with conn.cursor() as cur:
        if resume_id:
            cur.execute(
                "SELECT id, version_label, raw_text, embedding, skills FROM resumes WHERE id = %s",
                (resume_id,),
            )
        else:
            cur.execute(
                "SELECT id, version_label, raw_text, embedding, skills FROM resumes "
                "WHERE is_active = true ORDER BY uploaded_at DESC LIMIT 1"
            )
        row = cur.fetchone()
    if row is None:
        raise SystemExit(f"No resume found" + (f" with id {resume_id}" if resume_id else " — run app.resume_ingest first."))
    return {"id": row[0], "version_label": row[1], "raw_text": row[2], "embedding": row[3], "skills": row[4]}


def get_top_jobs(conn, resume: dict, limit: int):
    """Applies the full 5-factor rubric against a SPECIFIC resume dict
    (from get_resume above) — not an internally re-queried 'active' one.
    Also attaches matched_skills per job now, for the frontend's 'why this
    matches' explainability view."""
    resume_skills = extract_resume_skills(resume["raw_text"])

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, company, title, description, url, seniority, engagement_type,
                   1 - (embedding <=> %s) AS similarity
            FROM jobs
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT 100
            """,
            (resume["embedding"], resume["embedding"]),
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
        scored.append({
            **job,
            "final_score": score,
            "keyword_score": kw_score,
            "seniority_score": sen_score,
            "domain_score": dom_score,
            "ai_specificity": ai_score,
            "matched_skills": matched_skills(resume_skills, job_text),
            "sub_role_tags": get_sub_role_tags(job["title"]),
        })

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
        resume = get_resume(conn)
        resume_text = resume["raw_text"]
        jobs = get_top_jobs(conn, resume, TOP_N_TO_TAILOR)
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
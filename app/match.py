"""
Run with: python -m app.match

Pulls your active resume, compares its embedding against every stored job
via pgvector cosine similarity, layers on the deterministic keyword +
seniority rubric from scoring.py, and prints a ranked, explainable list.

This is deliberately a script, not a web UI yet — the point of step 3 is to
prove the matching logic itself works before building anything on top of it.
"""

from app.db import get_raw_conn
from app.scoring import extract_resume_skills, final_score, keyword_overlap_score, matched_skills, seniority_fit_score

TOP_N = 20


def get_active_resume(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, version_label, raw_text, embedding, skills
            FROM resumes
            WHERE is_active = true
            ORDER BY uploaded_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
    if row is None:
        raise SystemExit(
            "No active resume found. Run 'python -m app.resume_ingest' first "
            "with a resume file in resumes/."
        )
    return {"id": row[0], "version_label": row[1], "raw_text": row[2], "embedding": row[3], "skills": row[4]}


def get_top_jobs_by_similarity(conn, resume_embedding, limit: int):
    """pgvector's <=> operator is cosine distance (0 = identical, 2 = opposite).
    We convert to similarity (1 - distance) so higher = better, matching the
    rest of the scoring scale."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, source, company, title, url, seniority, description,
                   1 - (embedding <=> %s) AS similarity
            FROM jobs
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (resume_embedding, resume_embedding, limit),
        )
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def main() -> None:
    conn = get_raw_conn()
    try:
        resume = get_active_resume(conn)
        print(f"Matching against resume version: '{resume['version_label']}'")

        if resume["skills"]:
            resume_skills = set(resume["skills"])
            print(f"Using {len(resume_skills)} LLM-extracted skills (cached at ingest time): "
                  f"{', '.join(sorted(resume_skills))}\n")
        else:
            # Resume was ingested before LLM extraction existed — fall back
            # rather than fail. Re-run resume_ingest.py to get the better version.
            resume_skills = extract_resume_skills(resume["raw_text"])
            print("No cached LLM skills found for this resume (ingested with an older "
                  "version of the script) — using regex fallback instead. Re-run "
                  "'python -m app.resume_ingest' to upgrade it.\n"
                  f"Extracted {len(resume_skills)} skills: {', '.join(sorted(resume_skills))}\n")

        # Pull a wider candidate pool via vector similarity first (cheap,
        # pgvector-indexed), THEN apply the more expensive rubric scoring
        # only on that shortlist — same two-stage pattern as the LLM
        # reranking step planned for later.
        candidates = get_top_jobs_by_similarity(conn, resume["embedding"], limit=100)

        scored = []
        for job in candidates:
            job_text = f"{job['title']} {job['description'] or ''}"
            kw_score = keyword_overlap_score(resume_skills, job_text)
            sen_score = seniority_fit_score(job["seniority"])
            score = final_score(job["similarity"], kw_score, sen_score)
            scored.append({**job, "keyword_score": kw_score, "seniority_score": sen_score, "final_score": score})

        scored.sort(key=lambda j: j["final_score"], reverse=True)

        print(f"Top {TOP_N} matches (of {len(candidates)} candidates considered):\n")
        for i, job in enumerate(scored[:TOP_N], start=1):
            matches = matched_skills(resume_skills, f"{job['title']} {job['description'] or ''}")
            print(f"{i}. [{job['final_score']:.2f}] {job['title']} — {job['company']} ({job['seniority']})")
            print(f"   similarity={job['similarity']:.2f}  keyword_overlap={job['keyword_score']:.2f}  seniority_fit={job['seniority_score']:.2f}")
            if matches:
                print(f"   matched skills: {', '.join(matches)}")
            print(f"   {job['url']}\n")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
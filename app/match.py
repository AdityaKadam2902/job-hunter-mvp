"""
Run with: python -m app.match

Pulls your active resume, compares its embedding against every stored job
via pgvector cosine similarity, layers on the deterministic keyword +
seniority rubric from scoring.py, and prints a ranked, explainable list.
Also writes the full scored candidate list to eval/predictions.csv so it
can be labeled for the eval harness (see app/eval.py).
"""

import csv
from pathlib import Path

from app.db import get_raw_conn
from app.scoring import (
    ai_specificity_score,
    domain_fit_score,
    extract_resume_skills,
    final_score,
    keyword_overlap_score,
    matched_skills,
    seniority_fit_score,
)

TOP_N = 20
EVAL_DIR = Path("eval")


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
            dom_score = domain_fit_score(job["title"])
            ai_score = ai_specificity_score(job["title"], job["description"] or "")
            score = final_score(job["similarity"], kw_score, sen_score, dom_score, ai_score)
            scored.append({**job, "keyword_score": kw_score, "seniority_score": sen_score,
                            "domain_score": dom_score, "ai_specificity": ai_score, "final_score": score})

        scored.sort(key=lambda j: j["final_score"], reverse=True)

        EVAL_DIR.mkdir(exist_ok=True)
        csv_path = EVAL_DIR / "predictions.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["rank", "job_id", "company", "title", "seniority", "final_score",
                              "similarity", "keyword_score", "seniority_score", "domain_score",
                              "ai_specificity", "url", "relevant"])
            for i, job in enumerate(scored, start=1):
                # 'relevant' column left blank on purpose — you fill in 1 or 0
                # by hand after reviewing each listing. That's the eval harness.
                writer.writerow([i, job["id"], job["company"], job["title"], job["seniority"],
                                  f"{job['final_score']:.3f}", f"{job['similarity']:.3f}",
                                  f"{job['keyword_score']:.3f}", f"{job['seniority_score']:.3f}",
                                  f"{job['domain_score']:.3f}", f"{job['ai_specificity']:.3f}",
                                  job["url"], ""])
        print(f"Full ranked list ({len(scored)} jobs) written to {csv_path}\n")

        print(f"Top {TOP_N} matches (of {len(candidates)} candidates considered):\n")
        for i, job in enumerate(scored[:TOP_N], start=1):
            matches = matched_skills(resume_skills, f"{job['title']} {job['description'] or ''}")
            print(f"{i}. [{job['final_score']:.2f}] {job['title']} — {job['company']} ({job['seniority']})")
            print(f"   similarity={job['similarity']:.2f}  keyword_overlap={job['keyword_score']:.2f}  "
                  f"seniority_fit={job['seniority_score']:.2f}  domain_fit={job['domain_score']:.2f}  "
                  f"ai_specificity={job['ai_specificity']:.2f}")
            if matches:
                print(f"   matched skills: {', '.join(matches)}")
            print(f"   {job['url']}\n")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
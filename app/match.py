"""
Run with: python -m app.match [--resume Sakshi_Resume]

Pulls a resume (yours by default, or --resume <version_label> for a
specific person), ranks stored jobs against it, and prints a ranked,
explainable list. Also writes the full scored candidate list to
eval/predictions.csv for the eval harness.

IMPORTANT: this now calls app.tailor's get_resume() / get_top_jobs()
instead of reimplementing scoring locally. It used to have its own
parallel copy of the scoring loop, which meant every fix made to
tailor.py (the already-applied-company demotion, per-person role
profiles, sub-role tags) silently never applied here. Sharing one
implementation is the actual fix — not just adding --resume support.
"""

import argparse
import csv
from pathlib import Path

from app.db import get_raw_conn
from app.tailor import get_resume, get_top_jobs

TOP_N = 20
EVAL_DIR = Path("eval")


def get_resume_id_by_label(conn, label: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM resumes WHERE version_label = %s", (label,))
        row = cur.fetchone()
    if row is None:
        raise SystemExit(f"No resume found with version_label '{label}'.")
    return row[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank jobs against a resume.")
    parser.add_argument("--resume", default=None, help="version_label to match against (defaults to most recently uploaded)")
    args = parser.parse_args()

    conn = get_raw_conn()
    try:
        resume_id = get_resume_id_by_label(conn, args.resume) if args.resume else None
        resume = get_resume(conn, resume_id)
        print(f"Matching against resume version: '{resume['version_label']}'")

        if resume.get("skills"):
            print(f"Using {len(resume['skills'])} LLM-extracted skills (cached at ingest time): "
                  f"{', '.join(sorted(resume['skills']))}\n")
        else:
            print("No cached LLM skills found for this resume — matching will rely on "
                  "regex fallback inside get_top_jobs. Re-run 'python -m app.resume_ingest' "
                  "to upgrade it.\n")

        # get_top_jobs already does the full 5-factor rubric, per-person role
        # profile selection, already-applied-company demotion, and sub-role
        # tagging — all the same logic app.tailor and the API use. No
        # separate scoring loop here anymore.
        scored = get_top_jobs(conn, resume, limit=100)

        EVAL_DIR.mkdir(exist_ok=True)
        csv_path = EVAL_DIR / "predictions.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["rank", "job_id", "company", "title", "seniority", "final_score",
                              "similarity", "keyword_score", "seniority_score", "domain_score",
                              "ai_specificity", "already_applied_company", "sub_role_tags",
                              "url", "relevant"])
            for i, job in enumerate(scored, start=1):
                # 'relevant' column left blank on purpose — you fill in 1 or 0
                # by hand after reviewing each listing. That's the eval harness.
                writer.writerow([
                    i, job["id"], job["company"], job["title"], job["seniority"],
                    f"{job['final_score']:.3f}", f"{job['similarity']:.3f}",
                    f"{job['keyword_score']:.3f}", f"{job['seniority_score']:.3f}",
                    f"{job['domain_score']:.3f}", f"{job['ai_specificity']:.3f}",
                    job["already_applied_company"], ";".join(job["sub_role_tags"]),
                    job["url"], "",
                ])
        print(f"Full ranked list ({len(scored)} jobs) written to {csv_path}\n")

        print(f"Top {TOP_N} matches (of {len(scored)} candidates considered):\n")
        for i, job in enumerate(scored[:TOP_N], start=1):
            tags = f" [{', '.join(job['sub_role_tags'])}]" if job["sub_role_tags"] else ""
            applied_note = " (already applied to this company)" if job["already_applied_company"] else ""
            print(f"{i}. [{job['final_score']:.2f}] {job['title']} — {job['company']} ({job['seniority']}){tags}{applied_note}")
            print(f"   similarity={job['similarity']:.2f}  keyword_overlap={job['keyword_score']:.2f}  "
                  f"seniority_fit={job['seniority_score']:.2f}  domain_fit={job['domain_score']:.2f}  "
                  f"ai_specificity={job['ai_specificity']:.2f}")
            if job["matched_skills"]:
                print(f"   matched skills: {', '.join(job['matched_skills'])}")
            print(f"   {job['url']}\n")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
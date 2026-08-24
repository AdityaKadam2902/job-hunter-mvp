"""
Run with: python -m app.auto_label

Speeds up labeling eval/predictions.csv WITHOUT replacing your judgment.
Two things happen here, and they're deliberately different in kind:

1. HARD FILTER (not a suggestion — applied automatically): roles that
   clearly mismatch your seniority (Staff/Principal/Director-type titles for
   an entry-level candidate) get auto-labeled 0 immediately. This isn't a
   judgment call, it's a realistic-application-odds rule, separate from
   scoring.py's formula — so using it here isn't circular.

2. LLM SUGGESTION (a starting point, not a final answer): for the
   remaining ambiguous rows, an independent Groq call reads your resume and
   the job description and suggests relevant=1/0 with a short reason. This
   goes in a SEPARATE 'suggested_relevant' column — your 'relevant' column
   is left for you to fill in yourself, informed by the suggestion but not
   overwritten by it. Auto-accepting LLM suggestions as ground truth would
   make the eval numbers meaningless just like using scoring.py's own
   output would.

Only processes rows that don't already have a human-entered 'relevant'
label, and only within the top N rows by rank, to keep Groq calls low.
"""

import csv
import json
import time
from pathlib import Path

import httpx

from app.config import settings
from app.db import get_raw_conn

PREDICTIONS_PATH = Path("eval") / "predictions.csv"
TOP_N_TO_SUGGEST = 30

# Title patterns that are almost never realistic for an entry-level
# candidate, regardless of how well the skills match. Kept separate and
# more conservative than normalize.py's seniority tagger on purpose — this
# is an application-odds filter, not a general classifier.
HARD_FILTER_TITLES = [
    "staff", "principal", "director", "head of", "vp ", "chief",
]

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"


def hard_filter_reject(title: str) -> bool:
    title_lower = title.lower()
    return any(p in title_lower for p in HARD_FILTER_TITLES)


def get_resume_text(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT raw_text FROM resumes WHERE is_active = true ORDER BY uploaded_at DESC LIMIT 1")
        row = cur.fetchone()
    if row is None:
        raise SystemExit("No active resume found.")
    return row[0]


def llm_judge(resume_text: str, title: str, company: str, max_retries: int = 3) -> tuple[str, str]:
    """Independent judgment call, separate from scoring.py's formula.
    Returns (suggested_relevant, reason). Retries with backoff on 429 —
    the free tier's rate limit is easy to hit when suggesting ~20-30 rows
    in a row, and a single 429 shouldn't just silently drop that row."""
    prompt = (
        f"Resume:\n{resume_text[:3000]}\n\n"
        f"Job: {title} at {company}\n\n"
        "Would this specific person realistically be a competitive applicant "
        "for this specific role today, given their actual experience level? "
        "Answer ONLY with JSON: {\"relevant\": 0 or 1, \"reason\": \"one short sentence\"}"
    )

    for attempt in range(max_retries):
        try:
            resp = httpx.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                },
                timeout=30.0,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("retry-after", 5)) if resp.headers.get("retry-after", "5").isdigit() else 5
                print(f"  [rate limit] waiting {wait}s before retry ({attempt + 1}/{max_retries})...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.strip("`").removeprefix("json").strip()
            data = json.loads(content)
            return str(data.get("relevant", "")), str(data.get("reason", ""))
        except Exception as e:
            if attempt == max_retries - 1:
                return "", f"LLM suggestion failed after {max_retries} attempts: {e}"
            time.sleep(2)

    return "", "LLM suggestion failed: rate limited after all retries"


def main() -> None:
    if not PREDICTIONS_PATH.exists():
        raise SystemExit(f"{PREDICTIONS_PATH} not found. Run 'python -m app.match' first.")

    with open(PREDICTIONS_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys())
    if "suggested_relevant" not in fieldnames:
        fieldnames += ["suggested_relevant", "suggested_reason"]

    conn = get_raw_conn()
    try:
        resume_text = get_resume_text(conn)
    finally:
        conn.close()

    hard_filtered = 0
    llm_suggested = 0

    for row in rows:
        row.setdefault("suggested_relevant", "")
        row.setdefault("suggested_reason", "")

        if row["relevant"].strip() in ("0", "1"):
            continue  # already human-labeled, don't touch it

        if int(row["rank"]) > TOP_N_TO_SUGGEST:
            continue  # keep Groq calls bounded

        if hard_filter_reject(row["title"]):
            row["relevant"] = "0"
            row["suggested_reason"] = "auto-filtered: senior/staff-level title, unrealistic at current experience level"
            hard_filtered += 1
            continue

        suggested, reason = llm_judge(resume_text, row["title"], row["company"])
        row["suggested_relevant"] = suggested
        row["suggested_reason"] = reason
        llm_suggested += 1
        print(f"[suggest] rank {row['rank']}: {row['title']} — {row['company']} -> {suggested} ({reason})")

        # Save after EVERY row, not just at the end — a locked file or a
        # crash partway through should never lose work already done.
        save_rows(rows, fieldnames)

    save_rows(rows, fieldnames)
    print(f"\nDone. {hard_filtered} rows auto-filtered to 0 (unrealistic seniority), "
          f"{llm_suggested} rows given an LLM suggestion in 'suggested_relevant'.")
    print("Open the CSV: hard-filtered rows are already marked 'relevant'=0 for you. "
          "For LLM-suggested rows, review 'suggested_relevant' and 'suggested_reason', "
          "then fill in YOUR OWN 'relevant' column — don't just copy the suggestion blindly.")


def save_rows(rows: list[dict], fieldnames: list[str]) -> None:
    """Writes to predictions.csv, falling back to a different filename if
    the original is locked (e.g. open in Excel) rather than crashing and
    losing everything gathered so far."""
    target = PREDICTIONS_PATH
    try:
        with open(target, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except PermissionError:
        fallback = target.with_name("predictions_autolabel_backup.csv")
        with open(fallback, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"  [warning] {target} is locked (probably open in Excel) — "
              f"saved progress to {fallback} instead. Close {target.name} in "
              f"Excel, delete it, then rename {fallback.name} to {target.name}.")


if __name__ == "__main__":
    main()

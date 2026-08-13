"""
Run with: python -m app.eval

Reads eval/predictions.csv (produced by app.match) AFTER you've filled in
the 'relevant' column by hand (1 = genuinely relevant to you, 0 = not,
blank = not yet reviewed), and computes precision@10 and precision@20 —
real numbers instead of eyeballing the ranked list.

Workflow:
  1. python -m app.match          -> writes eval/predictions.csv
  2. Open predictions.csv, look at each job (or at least the top 20-30),
     mark 'relevant' as 1 or 0 based on whether YOU would actually apply.
  3. python -m app.eval           -> prints precision@10, precision@20,
     and flags any clear mismatches (high score but marked 0, or vice versa)

Re-run this any time you change scoring.py's weights or vocabulary to see
whether the change actually improved things, instead of guessing from a
handful of examples.
"""

import csv
from pathlib import Path

PREDICTIONS_PATH = Path("eval") / "predictions.csv"


def load_labeled_rows():
    if not PREDICTIONS_PATH.exists():
        raise SystemExit(
            f"{PREDICTIONS_PATH} not found. Run 'python -m app.match' first, "
            "then label the 'relevant' column before running this."
        )

    with open(PREDICTIONS_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    labeled = [r for r in rows if r["relevant"].strip() in ("0", "1")]
    return rows, labeled


def precision_at_k(rows: list[dict], k: int) -> tuple[float, int, int]:
    """Of the top k ranked rows THAT HAVE A LABEL, what fraction are
    relevant? Unlabeled rows are skipped rather than counted as wrong —
    partial labeling (e.g. just the top 20) still gives a valid number."""
    top_k = [r for r in rows if int(r["rank"]) <= k]
    labeled_top_k = [r for r in top_k if r["relevant"].strip() in ("0", "1")]
    if not labeled_top_k:
        return 0.0, 0, 0
    relevant_count = sum(1 for r in labeled_top_k if r["relevant"].strip() == "1")
    return relevant_count / len(labeled_top_k), relevant_count, len(labeled_top_k)


def main() -> None:
    rows, labeled = load_labeled_rows()

    if not labeled:
        print(
            f"No labeled rows yet in {PREDICTIONS_PATH}. Open it and fill in "
            "'relevant' (1 or 0) for at least the top 20-30 rows, then re-run this."
        )
        return

    print(f"{len(labeled)} of {len(rows)} jobs labeled.\n")

    for k in (10, 20):
        score, relevant, total = precision_at_k(rows, k)
        print(f"Precision@{k}: {score:.2f}  ({relevant}/{total} labeled jobs in top {k} are relevant)")

    # Flag disagreements: high score but marked not relevant, or low score
    # but marked relevant — these are the most useful rows to look at when
    # deciding whether scoring.py's weights need adjusting.
    print("\nBiggest disagreements between score and your label:")
    disagreements = []
    for r in labeled:
        score = float(r["final_score"])
        label = int(r["relevant"])
        # high score (>0.5) marked irrelevant, or low score (<0.4) marked relevant
        if score > 0.5 and label == 0:
            disagreements.append((score, r, "scored high but you marked NOT relevant"))
        elif score < 0.4 and label == 1:
            disagreements.append((score, r, "scored low but you marked RELEVANT"))

    disagreements.sort(key=lambda d: d[0], reverse=True)
    if not disagreements:
        print("  None — scoring and your judgment are well aligned on labeled rows.")
    for score, r, reason in disagreements[:10]:
        print(f"  [{score:.2f}] {r['title']} — {r['company']}: {reason}")


if __name__ == "__main__":
    main()
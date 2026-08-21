"""
Run with: python -m app.track <command> ...

Commands:
  add <job_id_or_rank> [--status saved] [--notes "..."]
      Start tracking a job. Accepts either a real job UUID, or a rank
      number (1-100) from the most recent eval/predictions.csv — much
      easier to type than copy-pasting a UUID off the match output.

  list [--status applied]
      Show tracked applications, optionally filtered by status.

  update <application_id_or_rank> --status interviewing
      Change status on a tracked application.

  note <application_id_or_rank> "some note text"
      Append a timestamped note without changing status.

Valid statuses: saved, applied, interviewing, offer, rejected, withdrawn
"""

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.db import get_raw_conn

STATUSES = ["saved", "applied", "interviewing", "offer", "rejected", "withdrawn"]
PREDICTIONS_PATH = Path("eval") / "predictions.csv"


def is_uuid_like(s: str) -> bool:
    """Cheap, dependency-free UUID shape check — good enough to distinguish
    '3f9a2b1c-...' from a plain rank number like '4', without needing the
    uuid module's stricter (and less forgiving) parsing."""
    return len(s) == 36 and s.count("-") == 4


def resolve_job_id_from_rank(rank: int) -> str:
    """Look up a job's real UUID from its rank in the most recent
    eval/predictions.csv (written by app.match). Lets you type 'add 4'
    instead of a 36-character UUID."""
    if not PREDICTIONS_PATH.exists():
        raise SystemExit(
            f"No {PREDICTIONS_PATH} found — run 'python -m app.match' first, "
            "or pass a real job UUID directly instead of a rank number."
        )
    with open(PREDICTIONS_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["rank"]) == rank:
                return row["job_id"]
    raise SystemExit(f"No job at rank {rank} in {PREDICTIONS_PATH} (file has fewer rows than that).")


def resolve_job_id(identifier: str) -> str:
    if is_uuid_like(identifier):
        return identifier
    try:
        rank = int(identifier)
    except ValueError:
        raise SystemExit(f"'{identifier}' isn't a valid job UUID or a rank number.")
    return resolve_job_id_from_rank(rank)


def get_active_resume_id(conn) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM resumes WHERE is_active = true ORDER BY uploaded_at DESC LIMIT 1")
        row = cur.fetchone()
    return row[0] if row else None


def cmd_add(args) -> None:
    conn = get_raw_conn()
    try:
        job_id = resolve_job_id(args.job)
        resume_id = get_active_resume_id(conn)

        with conn.cursor() as cur:
            cur.execute("SELECT company, title FROM jobs WHERE id = %s", (job_id,))
            job = cur.fetchone()
            if job is None:
                raise SystemExit(f"No job found with id {job_id} — check the rank/UUID is correct.")

            applied_at = datetime.now(timezone.utc) if args.status == "applied" else None
            cur.execute(
                """
                INSERT INTO applications (job_id, resume_id, status, notes, applied_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    notes = COALESCE(EXCLUDED.notes, applications.notes),
                    applied_at = COALESCE(EXCLUDED.applied_at, applications.applied_at),
                    updated_at = now()
                RETURNING id
                """,
                (job_id, resume_id, args.status, args.notes, applied_at),
            )
            app_id = cur.fetchone()[0]
        conn.commit()
        print(f"Tracking '{job[1]}' at {job[0]} — status: {args.status} (application id: {app_id})")
    finally:
        conn.close()


def cmd_list(args) -> None:
    conn = get_raw_conn()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT a.id, a.status, j.company, j.title, a.applied_at, a.notes, j.url
                FROM applications a
                JOIN jobs j ON j.id = a.job_id
            """
            params = ()
            if args.status:
                query += " WHERE a.status = %s"
                params = (args.status,)
            query += " ORDER BY a.updated_at DESC"

            cur.execute(query, params)
            rows = cur.fetchall()

        if not rows:
            print("No tracked applications yet. Use 'python -m app.track add <rank>' to start.")
            return

        for app_id, status, company, title, applied_at, notes, url in rows:
            applied_str = applied_at.strftime("%Y-%m-%d") if applied_at else "-"
            print(f"[{status:12s}] {title} — {company}  (applied: {applied_str})")
            if notes:
                print(f"    notes: {notes}")
            print(f"    {url}")
            print(f"    id: {app_id}\n")
    finally:
        conn.close()


def cmd_update(args) -> None:
    if args.status not in STATUSES:
        raise SystemExit(f"'{args.status}' isn't a valid status. Choose from: {', '.join(STATUSES)}")

    conn = get_raw_conn()
    try:
        applied_at_clause = ", applied_at = COALESCE(applied_at, now())" if args.status == "applied" else ""
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE applications
                SET status = %s, updated_at = now(){applied_at_clause}
                WHERE id = %s
                RETURNING (SELECT title FROM jobs WHERE jobs.id = applications.job_id)
                """,
                (args.status, args.application_id),
            )
            row = cur.fetchone()
            if row is None:
                raise SystemExit(f"No tracked application found with id {args.application_id}")
        conn.commit()
        print(f"Updated '{row[0]}' -> status: {args.status}")
    finally:
        conn.close()


def cmd_note(args) -> None:
    conn = get_raw_conn()
    try:
        timestamped = f"[{datetime.now().strftime('%Y-%m-%d')}] {args.text}"
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE applications
                SET notes = COALESCE(notes || E'\\n', '') || %s, updated_at = now()
                WHERE id = %s
                RETURNING (SELECT title FROM jobs WHERE jobs.id = applications.job_id)
                """,
                (timestamped, args.application_id),
            )
            row = cur.fetchone()
            if row is None:
                raise SystemExit(f"No tracked application found with id {args.application_id}")
        conn.commit()
        print(f"Added note to '{row[0]}'")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Track applications after a match.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Start tracking a job (by rank or UUID)")
    p_add.add_argument("job", help="Rank number from last match run, or a real job UUID")
    p_add.add_argument("--status", default="saved", choices=STATUSES)
    p_add.add_argument("--notes", default=None)
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="List tracked applications")
    p_list.add_argument("--status", default=None, choices=STATUSES)
    p_list.set_defaults(func=cmd_list)

    p_update = sub.add_parser("update", help="Change an application's status")
    p_update.add_argument("application_id")
    p_update.add_argument("--status", required=True, choices=STATUSES)
    p_update.set_defaults(func=cmd_update)

    p_note = sub.add_parser("note", help="Append a note to a tracked application")
    p_note.add_argument("application_id")
    p_note.add_argument("text")
    p_note.set_defaults(func=cmd_note)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
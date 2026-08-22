"""
Run with: uvicorn app.api:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.db import get_raw_conn
from app.tailor import get_active_resume_text, get_top_jobs

STATUSES = ["saved", "applied", "interviewing", "offer", "rejected", "withdrawn"]

app = FastAPI(title="Job Hunter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApplicationCreate(BaseModel):
    job_id: str
    status: str = "saved"
    notes: str | None = None


class ApplicationStatusUpdate(BaseModel):
    status: str


@app.get("/api/jobs/top")
def get_top_matches(limit: int = 20):
    conn = get_raw_conn()
    try:
        resume_text = get_active_resume_text(conn)
        jobs = get_top_jobs(conn, resume_text, limit)
    finally:
        conn.close()
    return [
        {
            "id": str(j["id"]),
            "company": j["company"],
            "title": j["title"],
            "url": j["url"],
            "seniority": j["seniority"],
            "engagement_type": j["engagement_type"],
            "score": round(j["final_score"], 2),
            "breakdown": {
                "similarity": round(j["similarity"], 2),
                "keyword": round(j["keyword_score"], 2),
                "seniority": round(j["seniority_score"], 2),
                "domain": round(j["domain_score"], 2),
                "ai_fit": round(j["ai_specificity"], 2),
            },
        }
        for j in jobs
    ]


@app.get("/api/applications")
def list_applications():
    conn = get_raw_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.id, a.status, j.company, j.title, a.applied_at, a.notes, j.url
                FROM applications a
                JOIN jobs j ON j.id = a.job_id
                ORDER BY a.updated_at DESC
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {
            "id": str(r[0]), "status": r[1], "company": r[2], "title": r[3],
            "applied_at": r[4].isoformat() if r[4] else None, "notes": r[5], "url": r[6],
        }
        for r in rows
    ]


@app.post("/api/applications")
def add_application(payload: ApplicationCreate):
    if payload.status not in STATUSES:
        raise HTTPException(400, f"Invalid status. Choose from: {STATUSES}")
    conn = get_raw_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM resumes WHERE is_active = true ORDER BY uploaded_at DESC LIMIT 1")
            row = cur.fetchone()
            resume_id = row[0] if row else None
            cur.execute(
                """
                INSERT INTO applications (job_id, resume_id, status, notes)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE SET status = EXCLUDED.status, updated_at = now()
                RETURNING id
                """,
                (payload.job_id, resume_id, payload.status, payload.notes),
            )
            app_id = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return {"id": str(app_id)}


@app.patch("/api/applications/{application_id}")
def update_application_status(application_id: str, payload: ApplicationStatusUpdate):
    if payload.status not in STATUSES:
        raise HTTPException(400, f"Invalid status. Choose from: {STATUSES}")
    conn = get_raw_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE applications SET status = %s, updated_at = now() WHERE id = %s RETURNING id",
                (payload.status, application_id),
            )
            if cur.fetchone() is None:
                raise HTTPException(404, "Application not found")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
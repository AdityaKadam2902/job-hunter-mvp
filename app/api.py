"""
Run with: uvicorn app.api:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.db import get_raw_conn
from app.tailor import get_resume, get_top_jobs

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
    resume_id: str | None = None
    status: str = "saved"
    notes: str | None = None


class ApplicationStatusUpdate(BaseModel):
    status: str


@app.get("/api/resumes")
def list_resumes():
    """Powers the profile switcher — one entry per person/resume version
    tracked in this instance (e.g. your AI/ML resume, a friend's Data
    Analyst resume). The frontend lets you pick one; everything else
    filters by it from there."""
    conn = get_raw_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, version_label, uploaded_at FROM resumes ORDER BY uploaded_at DESC"
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [{"id": str(r[0]), "label": r[1], "uploaded_at": r[2].isoformat()} for r in rows]


@app.get("/api/jobs/top")
def get_top_matches(limit: int = 20, resume_id: str | None = None):
    conn = get_raw_conn()
    try:
        resume = get_resume(conn, resume_id)
        jobs = get_top_jobs(conn, resume, limit)
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
            "matched_skills": j["matched_skills"],
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
def list_applications(resume_id: str | None = None):
    """resume_id filters to only the applications tracked under that
    person's resume — this is what makes 'go to her list vs mine' work,
    reusing applications.resume_id which was already being recorded."""
    conn = get_raw_conn()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT a.id, a.status, j.company, j.title, a.applied_at, a.notes, j.url
                FROM applications a
                JOIN jobs j ON j.id = a.job_id
            """
            params = ()
            if resume_id:
                query += " WHERE a.resume_id = %s"
                params = (resume_id,)
            query += " ORDER BY a.updated_at DESC"
            cur.execute(query, params)
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
        resume = get_resume(conn, payload.resume_id)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO applications (job_id, resume_id, status, notes)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE SET status = EXCLUDED.status, resume_id = EXCLUDED.resume_id, updated_at = now()
                RETURNING id
                """,
                (payload.job_id, resume["id"], payload.status, payload.notes),
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
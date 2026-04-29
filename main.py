import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


APP_NAME = "Kaltum Job Search Assistant"

DB_PATH = Path.home() / ".kaltum_jobsearch" / "jobs.db"

app = FastAPI(
    title=APP_NAME,
    description="AI-assisted job search, tracking, follow-up, and cover letter automation platform.",
    version="2.0.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            location TEXT DEFAULT 'Remote',
            salary TEXT,
            job_type TEXT DEFAULT 'Full-time',
            status TEXT DEFAULT 'saved',
            url TEXT,
            description TEXT,
            notes TEXT,
            source TEXT DEFAULT 'web',
            applied_date TEXT,
            follow_up_date TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()


def get_connection():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_jobs():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    conn.close()
    return rows


def get_stats(rows):
    stats = {
        "total": len(rows),
        "saved": 0,
        "applied": 0,
        "interview": 0,
        "offer": 0,
        "rejected": 0,
    }

    for row in rows:
        status = (row["status"] or "saved").lower()
        if status in stats:
            stats[status] += 1

    return stats


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    rows = get_jobs()
    stats = get_stats(rows)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "app_name": APP_NAME,
            "jobs": rows,
            "stats": stats,
        }
    )


@app.post("/jobs/add")
def add_job(
    company: str = Form(...),
    title: str = Form(...),
    location: str = Form("Remote"),
    salary: str = Form(""),
    job_type: str = Form("Full-time"),
    status: str = Form("saved"),
    url: str = Form(""),
    notes: str = Form("")
):
    valid_statuses = {"saved", "applied", "interview", "offer", "rejected"}
    status = status.lower().strip()

    if status not in valid_statuses:
        status = "saved"

    applied_date = None
    follow_up_date = None

    if status == "applied":
        applied_date = datetime.now().strftime("%Y-%m-%d")
        follow_up_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    conn = get_connection()
    conn.execute("""
        INSERT INTO jobs (
            company, title, location, salary, job_type, status,
            url, notes, source, applied_date, follow_up_date, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        company,
        title,
        location,
        salary,
        job_type,
        status,
        url,
        notes,
        "web",
        applied_date,
        follow_up_date,
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/", status_code=303)


@app.get("/jobs/{job_id}/delete")
def delete_job(job_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/", status_code=303)


@app.get("/jobs/{job_id}/status/{status}")
def update_status(job_id: int, status: str):
    valid_statuses = {"saved", "applied", "interview", "offer", "rejected"}

    if status not in valid_statuses:
        return RedirectResponse("/", status_code=303)

    applied_date = None
    follow_up_date = None

    conn = get_connection()

    if status == "applied":
        applied_date = datetime.now().strftime("%Y-%m-%d")
        follow_up_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        conn.execute("""
            UPDATE jobs
            SET status = ?, applied_date = ?, follow_up_date = ?, updated_at = datetime('now')
            WHERE id = ?
        """, (status, applied_date, follow_up_date, job_id))
    else:
        conn.execute("""
            UPDATE jobs
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
        """, (status, job_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/", status_code=303)


@app.get("/health", response_class=PlainTextResponse)
def health():
    return "Kaltum Job Search Assistant is running."


@app.get("/followup", response_class=PlainTextResponse)
def followup():
    result = subprocess.run(
        ["python", "app.py", "followup"],
        capture_output=True,
        text=True
    )

    output = result.stdout or "No follow-ups due today."
    return output
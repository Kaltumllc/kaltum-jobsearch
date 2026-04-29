#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           KALTUM JOB SEARCH — Automated Job Assistant       ║
║         Scrape · Track · Apply · Generate Cover Letters     ║
╚══════════════════════════════════════════════════════════════╝

Features:
  1. Search jobs from multiple sources (JSearch API / RemoteOK / Adzuna)
  2. Track applications in a local SQLite database
  3. Generate personalized cover letters using Claude AI
  4. Export applications to CSV / Excel
  5. Send email reminders for follow-ups

Usage:
  python kaltum_jobsearch.py --help
  python kaltum_jobsearch.py search --role "Data Analyst" --location "Boston"
  python kaltum_jobsearch.py cover --company Google --title "Data Analyst"
  python kaltum_jobsearch.py track --list
  python kaltum_jobsearch.py export

Requirements:
  pip install anthropic requests rich typer sqlite-utils python-dotenv
"""

import os
import json
import sqlite3
import csv
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ── Try importing optional libraries ─────────────────────────────────────────
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import print as rprint
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = Path.home() / ".kaltum_jobsearch" / "jobs.db"
CONFIG_PATH = Path.home() / ".kaltum_jobsearch" / "config.json"
EXPORT_PATH = Path.home() / "Desktop" / "kaltum_jobs_export.csv"

KALTUM_PROFILE = {
    "name": "Kaltum",
    "target_roles": ["Data Analyst", "Business Analyst", "Project Manager", "Operations Manager"],
    "experience": "3-5 years",
    "skills": ["Excel", "SQL", "Python", "Data Analysis", "Project Management", "Communication"],
    "location": "Boston, MA",
    "work_type": "hybrid or remote",
    "bio": """Results-driven professional with experience in data analysis and business operations.
Strong communicator with a proven track record of delivering insights and driving efficiency.
Passionate about leveraging data to solve real-world problems."""
}

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Colors / print helpers ────────────────────────────────────────────────────
def cprint(msg, color="white", bold=False):
    if HAS_RICH:
        style = f"bold {color}" if bold else color
        console.print(msg, style=style)
    else:
        print(msg)

def print_banner():
    banner = """
╔══════════════════════════════════════════════════════════╗
║        🌟  KALTUM JOB SEARCH  🌟                        ║
║        Automated · Personalized · Powerful              ║
╚══════════════════════════════════════════════════════════╝
"""
    if HAS_RICH:
        console.print(Panel(Text(banner.strip(), style="bold green"), border_style="green"))
    else:
        print(banner)

# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    """Initialize SQLite database for job tracking."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            company     TEXT NOT NULL,
            title       TEXT NOT NULL,
            location    TEXT DEFAULT 'Remote',
            salary      TEXT,
            job_type    TEXT DEFAULT 'Full-time',
            status      TEXT DEFAULT 'saved',
            url         TEXT,
            description TEXT,
            notes       TEXT,
            source      TEXT DEFAULT 'manual',
            applied_date TEXT,
            follow_up_date TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cover_letters (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      INTEGER REFERENCES jobs(id),
            company     TEXT,
            title       TEXT,
            content     TEXT,
            tone        TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    return conn

def get_db():
    return sqlite3.connect(DB_PATH)

# ── Job Search ────────────────────────────────────────────────────────────────
def search_remoteok(role: str, limit: int = 10) -> list:
    """Search RemoteOK — free, no API key needed."""
    if not HAS_REQUESTS:
        cprint("⚠  Install 'requests': pip install requests", "yellow")
        return []

    try:
        url = "https://remoteok.com/api"
        headers = {"User-Agent": "Kaltum-JobSearch/1.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()

        results = []
        for job in data[1:]:  # first item is metadata
            if not isinstance(job, dict): continue
            tags = " ".join(job.get("tags", []))
            title = job.get("position", "").lower()
            role_lower = role.lower()

            if role_lower in title or any(w in title for w in role_lower.split()):
                results.append({
                    "company":  job.get("company", "Unknown"),
                    "title":    job.get("position", ""),
                    "location": "Remote",
                    "salary":   job.get("salary", ""),
                    "url":      job.get("url", ""),
                    "source":   "RemoteOK",
                    "description": job.get("description", "")[:500]
                })
            if len(results) >= limit:
                break
        return results

    except Exception as e:
        cprint(f"⚠  RemoteOK error: {e}", "yellow")
        return []


def search_adzuna(role: str, location: str = "us", limit: int = 10) -> list:
    """
    Search Adzuna API.
    Get free keys at: https://developer.adzuna.com/
    Set env vars: ADZUNA_APP_ID and ADZUNA_API_KEY
    """
    if not HAS_REQUESTS:
        return []

    app_id = os.getenv("ADZUNA_APP_ID", "")
    api_key = os.getenv("ADZUNA_API_KEY", "")

    if not app_id or not api_key:
        cprint("ℹ  Adzuna API keys not set. Set ADZUNA_APP_ID and ADZUNA_API_KEY.", "cyan")
        cprint("   Get free keys at: https://developer.adzuna.com/", "cyan")
        return []

    try:
        country = "us"
        url = (f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
               f"?app_id={app_id}&app_key={api_key}"
               f"&results_per_page={limit}&what={role.replace(' ', '+')}"
               f"&where={location.replace(' ', '+')}&content-type=application/json")

        resp = requests.get(url, timeout=10)
        data = resp.json()
        results = []

        for job in data.get("results", []):
            results.append({
                "company":  job.get("company", {}).get("display_name", "Unknown"),
                "title":    job.get("title", ""),
                "location": job.get("location", {}).get("display_name", location),
                "salary":   f"${job.get('salary_min', '')} - ${job.get('salary_max', '')}"
                            if job.get("salary_min") else "",
                "url":      job.get("redirect_url", ""),
                "source":   "Adzuna",
                "description": job.get("description", "")[:500]
            })
        return results

    except Exception as e:
        cprint(f"⚠  Adzuna error: {e}", "yellow")
        return []


def search_jobs(role: str, location: str = "", limit: int = 15):
    """Search all available job sources and display results."""
    print_banner()
    cprint(f"\n🔍  Searching for: '{role}' in '{location or 'Remote'}'...\n", "cyan", bold=True)

    all_jobs = []

    # RemoteOK (always available)
    cprint("  → Searching RemoteOK...", "white")
    rjobs = search_remoteok(role, limit=limit)
    all_jobs.extend(rjobs)
    cprint(f"     Found {len(rjobs)} jobs", "green")

    # Adzuna (if keys available)
    cprint("  → Searching Adzuna...", "white")
    ajobs = search_adzuna(role, location, limit=limit)
    all_jobs.extend(ajobs)
    cprint(f"     Found {len(ajobs)} jobs", "green")

    if not all_jobs:
        cprint("\n  No jobs found. Try a different role or check your API keys.", "yellow")
        return []

    cprint(f"\n✅  Total: {len(all_jobs)} jobs found\n", "green", bold=True)

    if HAS_RICH:
        table = Table(title=f"Job Results for '{role}'", border_style="green", show_lines=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Company", style="bold cyan", width=18)
        table.add_column("Title", style="white", width=28)
        table.add_column("Location", style="yellow", width=16)
        table.add_column("Salary", style="green", width=18)
        table.add_column("Source", style="dim", width=10)

        for i, job in enumerate(all_jobs, 1):
            table.add_row(
                str(i),
                job["company"][:17],
                job["title"][:27],
                job["location"][:15],
                job["salary"][:17] or "–",
                job["source"]
            )
        console.print(table)
    else:
        print(f"\n{'#':>3}  {'Company':<20} {'Title':<30} {'Location':<18} {'Source'}")
        print("─" * 80)
        for i, job in enumerate(all_jobs, 1):
            print(f"{i:>3}. {job['company']:<20} {job['title']:<30} {job['location']:<18} {job['source']}")

    # Save prompt
    print()
    cprint("  Save any jobs to your tracker? Enter numbers (e.g. 1,3,5) or press Enter to skip:", "cyan")
    choice = input("  → ").strip()

    if choice:
        conn = init_db()
        saved = 0
        for c in choice.split(","):
            try:
                idx = int(c.strip()) - 1
                if 0 <= idx < len(all_jobs):
                    job = all_jobs[idx]
                    add_job_to_db(conn, job["company"], job["title"],
                                  job["location"], job.get("salary", ""),
                                  "Full-time", "saved", job.get("url", ""),
                                  job.get("description", ""), job["source"])
                    saved += 1
            except (ValueError, IndexError):
                pass
        conn.commit()
        conn.close()
        cprint(f"\n✅  {saved} job(s) saved to your tracker!", "green", bold=True)

    return all_jobs

# ── Add Job ───────────────────────────────────────────────────────────────────
def add_job_to_db(conn, company, title, location="Remote", salary="",
                  job_type="Full-time", status="saved", url="",
                  description="", source="manual"):
    conn.execute("""
        INSERT INTO jobs (company, title, location, salary, job_type, status,
                          url, description, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (company, title, location, salary, job_type, status, url, description, source))


def add_job_interactive():
    """Interactively add a job to tracker."""
    print_banner()
    cprint("\n➕  Add a new job to your tracker\n", "cyan", bold=True)

    company = input("  Company name: ").strip()
    title   = input("  Job title:    ").strip()
    location = input("  Location [Remote]: ").strip() or "Remote"
    salary  = input("  Salary range (optional): ").strip()
    job_type = input("  Type [Full-time]: ").strip() or "Full-time"
    url     = input("  Job URL (optional): ").strip()
    notes   = input("  Notes (optional): ").strip()

    print()
    cprint("  Status options: saved / applied / interview / offer / rejected", "dim")
    status = input("  Status [saved]: ").strip() or "saved"

    conn = init_db()
    add_job_to_db(conn, company, title, location, salary, job_type, status, url, "", "manual")

    if notes:
        conn.execute("UPDATE jobs SET notes=? WHERE id=(SELECT max(id) FROM jobs)", (notes,))
    if status == "applied":
        today = datetime.now().strftime("%Y-%m-%d")
        followup = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        conn.execute("UPDATE jobs SET applied_date=?, follow_up_date=? WHERE id=(SELECT max(id) FROM jobs)",
                     (today, followup))

    conn.commit()
    conn.close()
    cprint(f"\n✅  '{title}' at {company} added successfully!", "green", bold=True)

# ── List / Track ──────────────────────────────────────────────────────────────
def list_jobs(status_filter: Optional[str] = None):
    """List all tracked jobs."""
    conn = init_db()
    if status_filter:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC", (status_filter,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    conn.close()

    if not rows:
        cprint("\n  No jobs tracked yet. Use 'add' to add your first job!\n", "yellow")
        return

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    cprint(f"\n📊  Kaltum's Job Tracker ({len(rows)} total)\n", "cyan", bold=True)

    status_colors = {
        "saved": "yellow", "applied": "green",
        "interview": "blue", "offer": "bright_green", "rejected": "red"
    }

    if HAS_RICH:
        table = Table(border_style="cyan", show_lines=True)
        table.add_column("ID", style="dim", width=4)
        table.add_column("Company", style="bold cyan", width=18)
        table.add_column("Title", style="white", width=28)
        table.add_column("Location", style="yellow", width=16)
        table.add_column("Status", width=12)
        table.add_column("Applied", style="dim", width=12)
        table.add_column("Follow-Up", style="dim", width=12)

        for r in rows:
            color = status_colors.get(r["status"], "white")
            table.add_row(
                str(r["id"]),
                r["company"][:17],
                r["title"][:27],
                r["location"][:15],
                Text(r["status"].upper(), style=f"bold {color}"),
                r["applied_date"] or "–",
                r["follow_up_date"] or "–"
            )
        console.print(table)
    else:
        print(f"\n{'ID':>4}  {'Company':<20} {'Title':<30} {'Status':<12} {'Applied'}")
        print("─" * 80)
        for r in rows:
            print(f"{r['id']:>4}. {r['company']:<20} {r['title']:<30} {r['status']:<12} {r['applied_date'] or '–'}")

    # Summary
    cprint("\n  Summary:", "white", bold=True)
    for s, c in counts.items():
        color = status_colors.get(s, "white")
        bar = "█" * c
        if HAS_RICH:
            console.print(f"  {s.upper():<12} {bar} {c}", style=color)
        else:
            print(f"  {s.upper():<12} {bar} {c}")


def update_job_status(job_id: int, status: str):
    """Update status of a tracked job."""
    valid = ["saved", "applied", "interview", "offer", "rejected"]
    if status not in valid:
        cprint(f"⚠  Invalid status. Choose from: {', '.join(valid)}", "yellow")
        return

    conn = init_db()
    conn.execute("UPDATE jobs SET status=?, updated_at=datetime('now') WHERE id=?",
                 (status, job_id))

    if status == "applied":
        today = datetime.now().strftime("%Y-%m-%d")
        followup = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        conn.execute("UPDATE jobs SET applied_date=?, follow_up_date=? WHERE id=?",
                     (today, followup, job_id))

    conn.commit()
    conn.close()
    cprint(f"✅  Job #{job_id} updated to '{status}'", "green", bold=True)

# ── Cover Letter ──────────────────────────────────────────────────────────────
def generate_cover_letter(
    company: str,
    title: str,
    job_description: str = "",
    tone: str = "professional",
    job_id: Optional[int] = None,
    save: bool = True
):
    """Generate a personalized cover letter using Claude AI."""
    print_banner()
    cprint(f"\n✍️   Generating cover letter for {title} at {company}...\n", "cyan", bold=True)

    if not HAS_ANTHROPIC:
        cprint("⚠  Install anthropic: pip install anthropic", "yellow")
        return None

    api_key = ANTHROPIC_API_KEY
    if not api_key:
        api_key = input("  Enter your Anthropic API key: ").strip()
        if not api_key:
            cprint("⚠  No API key provided.", "yellow")
            return None

    tone_descriptions = {
        "professional": "professional, confident, and polished",
        "warm":         "warm, personable, and genuine",
        "concise":      "concise, direct, and impactful (under 200 words)",
        "enthusiastic": "enthusiastic, energetic, and passionate"
    }

    profile = KALTUM_PROFILE
    prompt = f"""Write a personalized cover letter for {profile['name']} applying for the role of "{title}" at "{company}".

Candidate Profile:
- Name: {profile['name']}
- Target Roles: {', '.join(profile['target_roles'])}
- Experience Level: {profile['experience']}
- Key Skills: {', '.join(profile['skills'])}
- Location: {profile['location']}
- Background: {profile['bio']}

Job Description:
{job_description if job_description else f'Write a strong cover letter for a {title} position at {company}.'}

Tone: {tone_descriptions.get(tone, tone_descriptions['professional'])}

Requirements:
- Address it "Dear Hiring Manager,"
- Sign off as "{profile['name']}"
- 3-4 focused paragraphs, under 350 words
- Be specific to the role and company
- Highlight relevant skills naturally — no keyword stuffing
- Show genuine enthusiasm
- Do NOT use clichés like "I am writing to express my interest"
- Make the opening line memorable and unique"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        letter = message.content[0].text

        cprint("\n" + "─" * 60, "dim")
        if HAS_RICH:
            console.print(Panel(letter, title=f"[bold cyan]{title} @ {company}[/]", border_style="cyan"))
        else:
            print(f"\n{letter}\n")
        cprint("─" * 60 + "\n", "dim")

        if save:
            conn = init_db()
            conn.execute("""
                INSERT INTO cover_letters (job_id, company, title, content, tone)
                VALUES (?, ?, ?, ?, ?)
            """, (job_id, company, title, letter, tone))
            conn.commit()
            conn.close()
            cprint("✅  Cover letter saved to database!", "green")

            # Save to file
            output_dir = Path.home() / "Desktop" / "kaltum_cover_letters"
            output_dir.mkdir(parents=True, exist_ok=True)
            fname = f"{company.replace(' ','_')}_{title.replace(' ','_')}.txt"
            (output_dir / fname).write_text(letter)
            cprint(f"📄  Saved to: {output_dir / fname}", "cyan")

        return letter

    except Exception as e:
        cprint(f"⚠  Error generating cover letter: {e}", "red")
        return None

# ── Export ────────────────────────────────────────────────────────────────────
def export_jobs(output=None):
    """Export tracked jobs to CSV."""
    import csv

    if not output:
        output = EXPORT_PATH
    else:
        output = Path(output).expanduser()

    output.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM jobs ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("No jobs found to export.")
        return

    fieldnames = rows[0].keys()

    with open(output, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )
        writer.writeheader()

        for row in rows:
            writer.writerow(dict(row))

    print(f"? Jobs exported successfully to {output}")


def check_followups():
    """Show jobs that need a follow-up today or overdue."""
    conn = init_db()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT * FROM jobs
        WHERE follow_up_date <= ? AND status = 'applied'
        ORDER BY follow_up_date ASC
    """, (today,)).fetchall()
    conn.close()

    if not rows:
        cprint("\n✅  No follow-ups due today.\n", "green")
        return

    cprint(f"\n🔔  {len(rows)} follow-up(s) due!\n", "yellow", bold=True)
    for r in rows:
        days = (datetime.strptime(today, "%Y-%m-%d") -
                datetime.strptime(r["follow_up_date"], "%Y-%m-%d")).days
        status = f"OVERDUE by {days}d" if days > 0 else "DUE TODAY"
        cprint(f"  [{status}] {r['company']} — {r['title']} (Applied: {r['applied_date']})", "yellow")

# ── Main CLI ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="🌟 Kaltum Job Search — Automated Job Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python kaltum_jobsearch.py search --role "Data Analyst" --location "Boston"
  python kaltum_jobsearch.py search --role "Project Manager" --limit 20
  python kaltum_jobsearch.py add
  python kaltum_jobsearch.py track --list
  python kaltum_jobsearch.py track --list --status applied
  python kaltum_jobsearch.py track --update 3 --status interview
  python kaltum_jobsearch.py cover --company Google --title "Data Analyst"
  python kaltum_jobsearch.py cover --company Meta --title "PM" --tone warm --jd "Lead cross-functional teams..."
  python kaltum_jobsearch.py export
  python kaltum_jobsearch.py followup
        """
    )

    subparsers = parser.add_subparsers(dest="command")

    # search
    s = subparsers.add_parser("search", help="Search for jobs online")
    s.add_argument("--role", "-r", required=True, help="Job role/title to search")
    s.add_argument("--location", "-l", default="", help="Location (default: Remote)")
    s.add_argument("--limit", "-n", type=int, default=15, help="Max results (default: 15)")

    # add
    subparsers.add_parser("add", help="Manually add a job to tracker")

    # track
    t = subparsers.add_parser("track", help="View or update tracked jobs")
    t.add_argument("--list", "-l", action="store_true", help="List all jobs")
    t.add_argument("--status", help="Filter by or set status")
    t.add_argument("--update", "-u", type=int, metavar="ID", help="Job ID to update")

    # cover
    c = subparsers.add_parser("cover", help="Generate a cover letter with Claude AI")
    c.add_argument("--company", required=True, help="Company name")
    c.add_argument("--title", required=True, help="Job title")
    c.add_argument("--jd", default="", help="Job description text")
    c.add_argument("--tone", default="professional",
                   choices=["professional", "warm", "concise", "enthusiastic"],
                   help="Writing tone")
    c.add_argument("--job-id", type=int, help="Link to a tracked job ID")
    c.add_argument("--no-save", action="store_true", help="Don't save to database")

    # export
    e = subparsers.add_parser("export", help="Export jobs to CSV")
    e.add_argument("--output", "-o", help="Output path (default: Desktop)")

    # followup
    subparsers.add_parser("followup", help="Show follow-up reminders")

    # profile
    subparsers.add_parser("profile", help="Show Kaltum's profile")

    args = parser.parse_args()

    if args.command == "search":
        search_jobs(args.role, args.location, args.limit)

    elif args.command == "add":
        add_job_interactive()

    elif args.command == "track":
        if args.update and args.status:
            update_job_status(args.update, args.status)
        else:
            list_jobs(args.status)

    elif args.command == "cover":
        generate_cover_letter(
            company=args.company,
            title=args.title,
            job_description=args.jd,
            tone=args.tone,
            job_id=args.job_id,
            save=not args.no_save
        )

    elif args.command == "export":
        export_jobs(args.output)

    elif args.command == "followup":
        check_followups()

    elif args.command == "profile":
        print_banner()
        cprint("\n👤  Kaltum's Job Search Profile\n", "cyan", bold=True)
        for k, v in KALTUM_PROFILE.items():
            val = ", ".join(v) if isinstance(v, list) else v
            cprint(f"  {k.upper():<20} {val}", "white")

    else:
        print_banner()
        cprint("\n  Welcome to Kaltum Job Search! Run with --help to see all commands.\n", "cyan")
        cprint("  Quick start:", "white", bold=True)
        cprint("    python kaltum_jobsearch.py search --role 'Data Analyst'", "dim")
        cprint("    python kaltum_jobsearch.py add", "dim")
        cprint("    python kaltum_jobsearch.py cover --company Google --title 'Analyst'", "dim")
        cprint("    python kaltum_jobsearch.py track --list", "dim")
        cprint("    python kaltum_jobsearch.py export\n", "dim")

        # Show follow-ups if any jobs exist
        if DB_PATH.exists():
            check_followups()

if __name__ == "__main__":
    main()

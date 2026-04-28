"""
Helpdesk Email Triage Tool
---------------------------
A simple ticket-triage application that simulates the work an IT
service-desk technician does when emails arrive in a shared mailbox:

1. Parse incoming email-style messages into structured tickets
2. Classify them by category (Account / Hardware / Software / Network / Other)
3. Assign a priority (P1 / P2 / P3 / P4) based on simple keyword rules
4. Store tickets in a local SQLite database
5. Expose a small web UI to browse, filter, and resolve tickets

This is a learning project inspired by the manual email-processing
work I used to do at IKEA Logistics — where I first wrote a VBA macro
to automate batch saving of attachments. This project is the Python
version of "what I'd build now, with the tools I learned during my
Master of IT."

Author: Yixin (Jerry) Zhao
"""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from flask import Flask, render_template, request, redirect, url_for

from triage import classify_ticket, parse_email_message


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent / "helpdesk.db"


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row-dict access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the tickets table if it doesn't already exist."""
    with closing(get_connection()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                subject      TEXT    NOT NULL,
                sender       TEXT    NOT NULL,
                body         TEXT    NOT NULL,
                category     TEXT    NOT NULL,
                priority     TEXT    NOT NULL,
                status       TEXT    NOT NULL DEFAULT 'OPEN',
                received_at  TEXT    NOT NULL,
                resolved_at  TEXT
            );
            """
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Ticket data model
# ---------------------------------------------------------------------------

@dataclass
class Ticket:
    id: Optional[int]
    subject: str
    sender: str
    body: str
    category: str
    priority: str
    status: str
    received_at: str
    resolved_at: Optional[str]


def insert_ticket(t: Ticket) -> int:
    """Insert a ticket and return its new id."""
    with closing(get_connection()) as conn:
        cursor = conn.execute(
            """
            INSERT INTO tickets
              (subject, sender, body, category, priority, status,
               received_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (t.subject, t.sender, t.body, t.category, t.priority,
             t.status, t.received_at, t.resolved_at),
        )
        conn.commit()
        return cursor.lastrowid


def list_tickets(status: Optional[str] = None) -> list[Ticket]:
    """Return all tickets, optionally filtered by status."""
    sql = "SELECT * FROM tickets"
    params: tuple = ()
    if status and status.upper() != "ALL":
        sql += " WHERE status = ?"
        params = (status.upper(),)
    sql += (
        " ORDER BY"
        "   CASE priority"
        "     WHEN 'P1' THEN 1 WHEN 'P2' THEN 2"
        "     WHEN 'P3' THEN 3 WHEN 'P4' THEN 4 ELSE 5"
        "   END, received_at DESC"
    )
    with closing(get_connection()) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [Ticket(**dict(r)) for r in rows]


def resolve_ticket(ticket_id: int) -> None:
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE tickets SET status = 'RESOLVED', resolved_at = ?"
            " WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), ticket_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Ticket creation pipeline
# ---------------------------------------------------------------------------

def ingest_email(raw_email: str) -> Ticket:
    """Take a raw email message, classify it, and insert it as a ticket."""
    parsed = parse_email_message(raw_email)
    category, priority = classify_ticket(parsed["subject"], parsed["body"])
    ticket = Ticket(
        id=None,
        subject=parsed["subject"],
        sender=parsed["sender"],
        body=parsed["body"],
        category=category,
        priority=priority,
        status="OPEN",
        received_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        resolved_at=None,
    )
    ticket.id = insert_ticket(ticket)
    return ticket


# ---------------------------------------------------------------------------
# Flask web UI
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.route("/")
def index():
    status_filter = request.args.get("status", "OPEN")
    tickets = list_tickets(status_filter)
    counts = {
        "OPEN": len(list_tickets("OPEN")),
        "RESOLVED": len(list_tickets("RESOLVED")),
        "ALL": len(list_tickets("ALL")),
    }
    return render_template(
        "index.html",
        tickets=tickets,
        status_filter=status_filter,
        counts=counts,
    )


@app.route("/ticket/<int:ticket_id>/resolve", methods=["POST"])
def resolve(ticket_id: int):
    resolve_ticket(ticket_id)
    return redirect(url_for("index"))


@app.route("/submit", methods=["GET", "POST"])
def submit():
    if request.method == "POST":
        raw = request.form.get("email", "").strip()
        if raw:
            ingest_email(raw)
        return redirect(url_for("index"))
    return render_template("submit.html")


# ---------------------------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------------------------

def cli() -> None:
    parser = argparse.ArgumentParser(description="Helpdesk triage tool")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Create the database tables")
    sub.add_parser("seed", help="Load example emails from data/sample_emails")
    sub.add_parser("serve", help="Start the web UI on http://127.0.0.1:5000")

    list_p = sub.add_parser("list", help="Print tickets to the terminal")
    list_p.add_argument("--status", default="ALL",
                        help="Filter: OPEN / RESOLVED / ALL")

    args = parser.parse_args()

    if args.command == "init":
        init_db()
        print(f"Initialised database at {DB_PATH}")

    elif args.command == "seed":
        init_db()
        seed_dir = Path(__file__).parent / "data" / "sample_emails"
        loaded = 0
        for path in sorted(seed_dir.glob("*.txt")):
            ingest_email(path.read_text(encoding="utf-8"))
            loaded += 1
        print(f"Loaded {loaded} sample emails into the database.")

    elif args.command == "list":
        for t in list_tickets(args.status):
            print(f"[{t.priority}] #{t.id:>3} {t.category:<10} "
                  f"{t.status:<8} {t.subject[:50]}")

    elif args.command == "serve":
        init_db()
        app.run(debug=True)

    else:
        parser.print_help()


if __name__ == "__main__":
    cli()

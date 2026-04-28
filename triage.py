"""
Triage logic: parse incoming emails and classify them into a category
and priority. Kept as a separate module so the rules can be unit-tested
independently of the database and the web UI.
"""

from __future__ import annotations

import re
from typing import Tuple


# ---------------------------------------------------------------------------
# Email parsing
# ---------------------------------------------------------------------------

_FROM_RE = re.compile(r"^From:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
_SUBJECT_RE = re.compile(r"^Subject:\s*(.+)$", re.MULTILINE | re.IGNORECASE)


def parse_email_message(raw: str) -> dict:
    """
    Take a raw email-style string and return a dict with sender,
    subject, and body. Lenient parser — intended for the simple text
    files in data/sample_emails.
    """
    sender_match = _FROM_RE.search(raw)
    subject_match = _SUBJECT_RE.search(raw)

    sender = sender_match.group(1).strip() if sender_match else "unknown"
    subject = subject_match.group(1).strip() if subject_match else "(no subject)"

    # Body is everything after the first blank line. If no blank line
    # exists, treat the whole message as body.
    parts = re.split(r"\n\s*\n", raw, maxsplit=1)
    body = parts[1].strip() if len(parts) == 2 else raw.strip()

    return {"sender": sender, "subject": subject, "body": body}


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

# Order matters: the first category whose keywords match wins.
# The rules are deliberately simple and explainable — no ML "magic" —
# so a human supervisor (or interview panel) can audit every decision.

CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("Account",  ["password", "locked out", "mfa", "login", "sign in",
                  "account", "unlock", "reset"]),
    ("Network",  ["wifi", "wi-fi", "internet", "network",
                  "no connection", "slow connection", "dns",
                  "cannot connect", "can't connect", "vpn"]),
    ("Hardware", ["laptop", "monitor", "screen", "keyboard", "mouse",
                  "printer", "headset", "battery", "charger", "docking"]),
    ("Software", ["excel", "outlook", "word", "powerpoint", "teams",
                  "office app", "browser", "crash", "freezing",
                  "install", "update"]),
]

# Priority rules — higher (P1) wins over lower.
PRIORITY_RULES: list[tuple[str, list[str]]] = [
    ("P1", ["urgent", "asap", "critical", "production down",
            "whole team", "everyone", "ceo", "executive",
            "outage", "cannot work", "can't work"]),
    ("P2", ["important", "blocking", "client meeting", "demo today",
            "before end of day", "by tomorrow"]),
    ("P3", ["sometime today", "this week", "when you can"]),
    # P4 is the default if nothing else matches
]


def classify_ticket(subject: str, body: str) -> Tuple[str, str]:
    """
    Return (category, priority) for an email's subject + body.
    Categorisation: first matching rule.
    Priority: highest matching rule, default P4.
    """
    text = f"{subject}\n{body}".lower()

    category = "Other"
    for cat, keywords in CATEGORY_RULES:
        if any(k in text for k in keywords):
            category = cat
            break

    # Strip out common negations before priority matching, e.g. "not urgent"
    # would otherwise trigger the "urgent" P1 rule.
    priority_text = re.sub(r"\bnot\s+(\w+)", "", text)
    priority_text = re.sub(r"\bno\s+rush\b", "", priority_text)

    priority = "P4"
    for prio, keywords in PRIORITY_RULES:
        if any(k in priority_text for k in keywords):
            priority = prio
            break

    return category, priority

"""
Unit tests for the triage classifier.

Run with:
    pytest -v
"""

from triage import classify_ticket, parse_email_message


# ---------------------------------------------------------------------------
# Email parsing
# ---------------------------------------------------------------------------

def test_parse_extracts_sender_and_subject():
    raw = (
        "From: alice@example.com\n"
        "Subject: My laptop is broken\n"
        "\n"
        "Please help, the screen is black."
    )
    parsed = parse_email_message(raw)
    assert parsed["sender"] == "alice@example.com"
    assert parsed["subject"] == "My laptop is broken"
    assert "screen is black" in parsed["body"]


def test_parse_handles_missing_headers():
    parsed = parse_email_message("Hi, no headers here.")
    assert parsed["sender"] == "unknown"
    assert parsed["subject"] == "(no subject)"


# ---------------------------------------------------------------------------
# Categorisation
# ---------------------------------------------------------------------------

def test_password_ticket_is_account_category():
    cat, _ = classify_ticket(
        "Forgot my password",
        "Hi team, I forgot my password — can you reset it?",
    )
    assert cat == "Account"


def test_laptop_ticket_is_hardware_category():
    cat, _ = classify_ticket(
        "New laptop request",
        "I'd like to swap my old laptop for the new model.",
    )
    assert cat == "Hardware"


def test_outlook_ticket_is_software_category():
    cat, _ = classify_ticket(
        "Outlook keeps crashing",
        "Every time I open Outlook it freezes.",
    )
    assert cat == "Software"


def test_wifi_ticket_is_network_category():
    cat, _ = classify_ticket(
        "Wifi not working",
        "I cannot connect to the office wifi.",
    )
    assert cat == "Network"


def test_unknown_ticket_falls_through_to_other():
    cat, _ = classify_ticket(
        "Question about parking",
        "Where do I park my bike?",
    )
    assert cat == "Other"


# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------

def test_urgent_keyword_raises_to_p1():
    _, prio = classify_ticket(
        "URGENT — system down",
        "Production is down, the whole team cannot work.",
    )
    assert prio == "P1"


def test_blocking_keyword_is_p2():
    _, prio = classify_ticket(
        "Excel formulas not saving",
        "This is blocking my client meeting tomorrow.",
    )
    assert prio == "P2"


def test_relaxed_keyword_is_p3():
    _, prio = classify_ticket(
        "New monitor request",
        "Hi, when you can, could I get a second monitor this week?",
    )
    assert prio == "P3"


def test_default_priority_is_p4():
    _, prio = classify_ticket(
        "Just a general question",
        "Where can I find the company handbook?",
    )
    assert prio == "P4"


# ---------------------------------------------------------------------------
# Negation handling — these caught a real bug in early development
# ---------------------------------------------------------------------------

def test_not_urgent_is_not_treated_as_p1():
    """The phrase 'not urgent' should NOT match the 'urgent' P1 rule."""
    _, prio = classify_ticket(
        "Wifi keeps dropping in meeting room 4",
        "Not urgent — I can use the cable — but worth a look when you can.",
    )
    assert prio != "P1"


def test_no_rush_is_not_treated_as_p3_high():
    """'No rush' should not push priority above default."""
    _, prio = classify_ticket(
        "VPN setup request",
        "Could you send me the VPN setup instructions? No rush.",
    )
    assert prio == "P4"

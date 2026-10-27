"""
Prefill HD Ticket's ticket_type/custom_programme/custom_current_year from the
raising user's Student Master or PACE Application record when the ticket
arrives without them already set (i.e. tickets created via inbound email,
which never go through the portal form script that normally fills these
fields — see helpdesk.api.nls_student.get_student_context).

Runs on before_insert, i.e. before the core controller's before_validate
(hd_ticket.py: set_ticket_type, set_team_from_ticket_type), so that core's
own type-of-issue -> PACE/programme-year -> flat-team cascade has a real
ticket_type and programme to match against instead of always falling back
to HD Settings.default_ticket_type. This intentionally does NOT duplicate
core's rule-matching logic to avoid the two engines disagreeing.

If core still can't resolve a team (e.g. sender matches neither Student
Master nor PACE Application), the ticket falls back to DEFAULT_EMAIL_TEAM
for non-portal (email) tickets.
"""

import frappe

from slcm.slcm.utils.exam_schedule import get_student_programme

DEFAULT_EMAIL_TEAM = "PACE Team"
PACE_TICKET_TYPE = "PACE"


def prefill_student_context_before_insert(doc, method=None):
    """Hook: HD Ticket before_insert."""
    if doc.via_customer_portal:
        return

    student = _get_student(doc.raised_by)
    if student:
        if not doc.custom_programme:
            doc.custom_programme = student.get("programme") or ""
        if not doc.custom_current_year:
            doc.custom_current_year = student.get("current_year") or ""
        return

    applicant = _get_pace_applicant(doc.raised_by)
    if not applicant:
        return

    # An email arriving from a known PACE applicant should be routed through
    # the "PACE" ticket type's Programme/Year-wise rules, not whatever the
    # site-wide default ticket type happens to be — otherwise the programme
    # match in set_team_from_ticket_type() never runs and the ticket silently
    # falls back to the ticket type's flat team.
    if not doc.ticket_type:
        doc.ticket_type = PACE_TICKET_TYPE
    if not doc.custom_programme:
        doc.custom_programme = applicant.get("programme") or ""
    if not doc.custom_current_year:
        doc.custom_current_year = applicant.get("current_year") or ""


def apply_default_email_team(doc, method=None):
    """Hook: HD Ticket before_validate, registered AFTER the core controller's
    own before_validate (see execution-order note in hooks.py). By this point
    core's set_team_from_ticket_type has already had its chance to resolve
    agent_group from the ticket type configuration."""
    if doc.agent_group or doc.via_customer_portal:
        return
    doc.agent_group = DEFAULT_EMAIL_TEAM


def _get_student(email):
    """Return dict with programme and current_year for the student, or None."""
    if not email:
        return None

    sm = frappe.db.get_value(
        "Student Master",
        {"user": email},
        ["name", "current_year"],
        as_dict=True,
    )
    if not sm:
        sm = frappe.db.get_value(
            "Student Master",
            {"email": email},
            ["name", "current_year"],
            as_dict=True,
        )
    if not sm:
        sm = frappe.db.get_value(
            "Student Master",
            {"official_email_id": email},
            ["name", "current_year"],
            as_dict=True,
        )
    if not sm:
        return None

    return {
        "programme": get_student_programme(sm.name) or None,
        "current_year": (sm.get("current_year") or "").strip(),
    }


def _get_pace_applicant(email):
    """Return dict with programme (a PACE Programme name) and current_year
    (always blank, applicants have no year) for a PACE Application matching
    this email, or None. Mirrors helpdesk.api.nls_student._get_pace_applicant_context."""
    if not email:
        return None

    app = frappe.db.get_value(
        "PACE Application", {"owner": email}, "programme", order_by="modified desc"
    ) or frappe.db.get_value(
        "PACE Application",
        {"email_address": email},
        "programme",
        order_by="modified desc",
    )
    if not app:
        return None

    return {"programme": app, "current_year": ""}

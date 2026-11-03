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

from email.utils import parseaddr

import frappe

from slcm.permissions import AAD_ROLES
from slcm.slcm.utils.exam_schedule import get_student_programme

DEFAULT_EMAIL_TEAM = "PACE Team"
PACE_TICKET_TYPE = "PACE"
TECHNICAL_ISSUE_TICKET_TYPE = "Technical Issue"
# Technical Issue tickets raised by AAD / AAD Staff go to the SLCM technical
# team; the type's own flat team (PACE Team) stays for applicants
AAD_TECHNICAL_TEAM = "SLCM Technical Team"


def prefill_student_context_before_insert(doc, method=None):
    """Hook: HD Ticket before_insert."""
    if doc.via_customer_portal:
        return

    student = _get_student(doc.raised_by)
    if student:
        # A converted PACE student is routed like a PACE applicant.
        if student.get("pace") and not doc.ticket_type:
            doc.ticket_type = PACE_TICKET_TYPE
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


def route_aad_technical_issue(doc, method=None):
    """Hook: HD Ticket before_insert. Setting agent_group here, before core's
    set_team_from_ticket_type, makes core keep it, so SLA and escalation are
    resolved against the right team."""
    if doc.agent_group or doc.ticket_type != TECHNICAL_ISSUE_TICKET_TYPE:
        return
    user = parseaddr(doc.raised_by or "")[1] or frappe.session.user
    if not frappe.db.exists("User", user) or not AAD_ROLES & set(frappe.get_roles(user)):
        return
    if frappe.db.get_value("HD Team", AAD_TECHNICAL_TEAM, "disabled") == 0:
        doc.agent_group = AAD_TECHNICAL_TEAM


def apply_default_email_team(doc, method=None):
    """Hook: HD Ticket before_validate, registered AFTER the core controller's
    own before_validate (see execution-order note in hooks.py). By this point
    core's set_team_from_ticket_type has already had its chance to resolve
    agent_group from the ticket type configuration."""
    if doc.agent_group or doc.via_customer_portal:
        return
    doc.agent_group = DEFAULT_EMAIL_TEAM


def _get_student(email):
    """Return dict with programme and current_year for the student (and pace=True
    with the PACE Programme for PACE students), or None."""
    if not email:
        return None

    fields = ["name", "current_year", "admission_type", "pace_programme"]
    sm = None
    for key in ("user", "email", "official_email_id"):
        sm = frappe.db.get_value("Student Master", {key: email}, fields, as_dict=True)
        if sm:
            break
    if not sm:
        return None

    if sm.admission_type == "PACE" or sm.pace_programme:
        return {"programme": sm.pace_programme or "", "current_year": "", "pace": True}

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


def style_ticket_assignment_notification(doc, method=None):
    """Hook: Notification Log before_insert. Frappe's assignment notice for a
    Helpdesk ticket reads "<customer> assigned a new task HD Ticket <subject>"
    (auto-assignment runs in the raiser's request) with a bare link; replace it
    with a ticket card, rendered by slcm's new_notification.html override.
    Un-assignment notices (no open ToDo) are left as they are."""
    if doc.type != "Assignment" or doc.document_type != "HD Ticket" or not doc.document_name:
        return
    if not frappe.db.exists(
        "ToDo",
        {
            "reference_type": "HD Ticket",
            "reference_name": doc.document_name,
            "allocated_to": doc.for_user,
            "status": "Open",
        },
    ):
        return
    ticket = frappe.db.get_value(
        "HD Ticket",
        doc.document_name,
        ["name", "subject", "raised_by", "ticket_type", "agent_group"],
        as_dict=True,
    )
    if not ticket:
        return

    ticket_url = frappe.utils.get_url(f"/helpdesk/tickets/{ticket.name}")
    subject = frappe.utils.escape_html(ticket.subject or "")
    doc.subject = f'Ticket <b>#{ticket.name}</b> assigned to you: <b class="subject-title">{subject}</b>'
    doc.email_header = f"New Ticket Assigned: #{ticket.name}"
    doc.link = ticket_url
    doc.email_content = frappe.render_template(
        "slcm/templates/emails/helpdesk_ticket_assigned.html",
        {"ticket": ticket, "ticket_url": ticket_url},
    )

"""
slcm/admission/applicant_reminder_emails.py
-------------------------------------------
Scheduled reminder email logic for the Admission module.

Scheduler entry (hooks.py  "0 10 * * *"):
    slcm.admission.applicant_reminder_emails.send_not_started_reminders
    slcm.admission.applicant_reminder_emails.send_draft_applicant_reminders
    slcm.admission.applicant_reminder_emails.send_unpaid_fee_reminders
"""

import traceback
import frappe
from frappe.utils import get_url, getdate, today, now_datetime, formatdate
from slcm.admission.utils.nlsat_portal import get_user_portal_redirect_url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_active_cycle():
    """
    Returns (cycle_name, cycle_end_date, application_end_date, status) for the currently Active
    Admission Cycle, or fallback to the most recently Closed cycle.
    """
    cycle = frappe.db.get_value(
        "Admission Cycle",
        {"status": "Active"},
        ["name", "cycle_end_date", "application_end_date", "status"],
        as_dict=True,
    )
    if cycle:
        return cycle.name, cycle.cycle_end_date, cycle.application_end_date, cycle.status

    # Fallback: look for the most recently closed cycle so rejections can still be processed
    cycle = frappe.db.get_value(
        "Admission Cycle",
        {"status": "Closed"},
        ["name", "cycle_end_date", "application_end_date", "status"],
        as_dict=True,
        order_by="cycle_end_date desc",
    )
    if cycle:
        return cycle.name, cycle.cycle_end_date, cycle.application_end_date, cycle.status

    return None, None, None, None


def _get_template_sender(template_name):
    """Resolves the sender email address from an Email Template's email_account."""
    if not template_name:
        return None
    email_account = frappe.db.get_value("Email Template", template_name, "email_account")
    if email_account:
        return frappe.db.get_value("Email Account", email_account, "email_id") or None
    return None


def _get_institution_name():
    try:
        return frappe.get_single("Institution Settings").institution_name or "NLSIU"
    except Exception:
        return "NLSIU"


def _send_email_from_template(template_name, recipient, args, reference_doctype=None, reference_name=None, now=False):
    """
    Renders and sends an email from a named Email Template.
    Returns (subject, success_bool).
    """
    if not frappe.db.exists("Email Template", template_name):
        frappe.log_error(f"Email Template '{template_name}' not found.", "Applicant Reminder Email Missing Template")
        return None, False

    tmpl = frappe.get_doc("Email Template", template_name)

    if "doc" not in args:
        args["doc"] = frappe._dict()

    try:
        subject = frappe.render_template(tmpl.subject or template_name, args)

        body = ""
        if tmpl.get("use_html") and tmpl.get("response_html"):
            body = frappe.render_template(tmpl.response_html, args)
        elif tmpl.get("response"):
            body = frappe.render_template(tmpl.response, args)

        if not body:
            body = frappe.render_template(tmpl.get("message") or "", args)

        if not body:
            return subject, False

        cc_list = []
        cc_val = tmpl.get("cc")
        if cc_val:
            cc_list = [c.strip() for c in cc_val.replace(";", ",").split(",") if c.strip()]

        frappe.sendmail(
            recipients=[recipient],
            sender=_get_template_sender(template_name),
            cc=cc_list,
            subject=subject,
            message=body,
            reference_doctype=reference_doctype,
            reference_name=reference_name,
            now=now,
        )
        return subject, True

    except Exception:
        frappe.log_error(traceback.format_exc(), f"Applicant Reminder Send Error: {template_name} → {recipient}")
        return None, False


# ---------------------------------------------------------------------------
# 1. Not-Started Application Reminder
# ---------------------------------------------------------------------------

def send_not_started_reminders(current_item=0, total_items=0, is_rejection_only=False):
    """
    Sends reminders to users with role 'Applicant' who have NO Applicant record
    in the current active admission cycle.
    After application_end_date: disables the user's Applicant role (no application → no rejection record).
    """
    from slcm.admission.doctype.applicant_reminder_email_configuration.applicant_reminder_email_configuration import (
        should_send_reminder, get_rejection_reason,
    )
    from slcm.admission.doctype.applicant_reminder_email_log.applicant_reminder_email_log import (
        log_applicant_reminder_email,
    )

    cycle_name, cycle_end_date, application_end_date, cycle_status = _get_active_cycle()
    if not cycle_name or not application_end_date:
        return 0

    today_date = getdate(today())
    close_date = getdate(application_end_date)
    
    if is_rejection_only and today_date <= close_date:
        return 0

    # All users with Applicant role
    users = frappe.get_all("Has Role", filters={"role": "Applicant"}, fields=["parent"], limit=0)
    user_emails = list(set([u.parent for u in users]))

    # Emails that already have at least one Applicant record
    existing = frappe.get_all(
        "Applicant",
        filters={"admission_cycle": cycle_name},
        fields=["user_id"],
        pluck="user_id",
        limit=0,
    )
    existing_set = set(existing)

    already_rejected = frappe.get_all(
        "Applicant Reminder Email Log",
        filters={
            "reminder_type": "Not Started Application Rejected",
            "admission_cycle": cycle_name,
        },
        pluck="recipient",
        limit=0
    )
    already_rejected_set = set(already_rejected)

    template_name = "Applicant Not Started Application Reminder"
    institution_name = _get_institution_name()
    sent_count = 0

    for i, email in enumerate(user_emails):
        if total_items > 0:
            frappe.publish_realtime("progress", {
                "progress": [current_item + i, total_items],
                "title": "Applicant Reminders",
                "description": f"Not Started Reminders: {email}"
            }, user=frappe.session.user)

        if email in existing_set or email in already_rejected_set:
            continue

        try:
            if not email or not frappe.db.exists("User", email):
                continue

            user_doc = frappe.get_doc("User", email)
            if not user_doc.enabled:
                continue

            # Ensure we only send reminders for the admission cycle the user registered in
            # by checking if they've received a reminder for a DIFFERENT cycle in the past.
            previous_logs = frappe.get_all(
                "Applicant Reminder Email Log",
                filters={
                    "reference_doctype": "User",
                    "reference_name": email,
                },
                fields=["admission_cycle"],
                limit=0
            )
            belong_to_other_cycle = False
            for log in previous_logs:
                if log.admission_cycle and log.admission_cycle != cycle_name:
                    belong_to_other_cycle = True
                    break
            if belong_to_other_cycle:
                continue

            last_sent = frappe.db.get_value(
                "Applicant Reminder Email Log",
                {
                    "reference_doctype": "User",
                    "reference_name": email,
                    "reminder_type": "Not Started Application Reminder",
                    "admission_cycle": cycle_name,
                },
                "sent_at",
                order_by="sent_at desc",
            )

            if not should_send_reminder("not_started", last_sent, application_end_date):
                continue

            if today_date > close_date:
                # Past deadline — just log; no application to reject
                rejection_reason = get_rejection_reason("not_started_rejection_reason")
                subject, ok = _send_email_from_template(
                    "Applicant Application Rejected",
                    email,
                    {
                        "candidate_name": user_doc.full_name or email,
                        "rejection_reason": rejection_reason,
                        "cycle_end_date": formatdate(application_end_date),
                        "institution_name": institution_name,
                        "admission_portal_url": get_url(get_user_portal_redirect_url(email, "/admission-dashboard")),
                    },
                    reference_doctype="User",
                    reference_name=email,
                )
                if ok:
                    log_applicant_reminder_email(
                        recipient=email,
                        subject=subject or "Application Rejected",
                        reminder_type="Not Started Application Rejected",
                        sender=_get_template_sender("Applicant Application Rejected"),
                        reference_doctype="User",
                        reference_name=email,
                        email_template="Applicant Application Rejected",
                        admission_cycle=cycle_name,
                    )
                    sent_count += 1
                continue

            # Before deadline — send reminder
            if cycle_status == "Closed":
                continue

            subject, ok = _send_email_from_template(
                template_name,
                email,
                {
                    "candidate_name": user_doc.first_name or user_doc.full_name or email,
                    "cycle_end_date": formatdate(application_end_date, "dd MMMM yyyy"),
                    "application_end_date": formatdate(application_end_date, "dd MMMM yyyy"),
                    "app_end_date_formatted": formatdate(application_end_date, "dd MMMM yyyy"),
                    "institution_name": institution_name,
                    "admission_portal_url": get_url(get_user_portal_redirect_url(email, "/admission-dashboard")),
                },
                reference_doctype="User",
                reference_name=email,
            )
            if ok:
                log_applicant_reminder_email(
                    recipient=email,
                    subject=subject,
                    reminder_type="Not Started Application Reminder",
                    sender=_get_template_sender(template_name),
                    reference_doctype="User",
                    reference_name=email,
                    email_template=template_name,
                    admission_cycle=cycle_name,
                )
                sent_count += 1

        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Not Started Reminder Failed: {email}")

    return sent_count


# ---------------------------------------------------------------------------
# 2. Draft Application Reminder
# ---------------------------------------------------------------------------

def send_draft_applicant_reminders(current_item=0, total_items=0, is_rejection_only=False):
    """
    Sends reminders to applicants whose Applicant doc is still in Draft (docstatus=0).
    After application_end_date: rejects the application.
    """
    from slcm.admission.doctype.applicant_reminder_email_configuration.applicant_reminder_email_configuration import (
        should_send_reminder, get_rejection_reason,
    )
    from slcm.admission.doctype.applicant_reminder_email_log.applicant_reminder_email_log import (
        log_applicant_reminder_email,
    )

    cycle_name, cycle_end_date, application_end_date, cycle_status = _get_active_cycle()
    if not cycle_name or not application_end_date:
        return 0

    today_date = getdate(today())
    close_date = getdate(application_end_date)
    
    if is_rejection_only and today_date <= close_date:
        return 0

    applications = frappe.get_all(
        "Applicant",
        filters={"status": "Draft", "admission_cycle": cycle_name},
        fields=["name", "email", "candidate_name", "program", "last_draft_reminder_sent"],
        limit=0,
    )

    template_name = "Applicant Draft Application Reminder"
    institution_name = _get_institution_name()
    sent_count = 0

    for i, app in enumerate(applications):
        if total_items > 0:
            frappe.publish_realtime("progress", {
                "progress": [current_item + i, total_items],
                "title": "Applicant Reminders",
                "description": f"Draft Reminders: {app.name}",
            }, user=frappe.session.user)

        try:
            recipient = app.email
            if not recipient:
                continue

            if not should_send_reminder("draft", app.last_draft_reminder_sent, application_end_date):
                continue

            if today_date > close_date:
                rejection_reason = get_rejection_reason("draft_rejection_reason")
                subject, ok = _send_email_from_template(
                    "Applicant Application Rejected",
                    recipient,
                    {
                        "candidate_name": app.candidate_name or recipient,
                        "applicant_id": app.name,
                        "program": app.program or "",
                        "rejection_reason": rejection_reason,
                        "cycle_end_date": formatdate(application_end_date),
                        "institution_name": institution_name,
                        "admission_portal_url": get_url(get_user_portal_redirect_url(recipient, "/admission-dashboard")),
                    },
                    reference_doctype="Applicant",
                    reference_name=app.name,
                )
                if ok:
                    # Mark application as Rejected via db_set to skip submit validation
                    rejected_status = frappe.db.get_value("Applicant Status", {"name": "Rejected"}, "name") or "Rejected"
                    frappe.db.set_value("Applicant", app.name, "status", rejected_status, update_modified=False)
                    frappe.db.set_value("Applicant", app.name, "rejected_reason", rejection_reason, update_modified=False)
                    frappe.db.commit()
                    log_applicant_reminder_email(
                        recipient=recipient,
                        subject=subject or "Application Rejected",
                        reminder_type="Draft Application Rejected",
                        sender=_get_template_sender("Applicant Application Rejected"),
                        reference_doctype="Applicant",
                        reference_name=app.name,
                        email_template="Applicant Application Rejected",
                    )
                    sent_count += 1
                continue

            # Before deadline — send reminder
            if cycle_status == "Closed":
                continue

            subject, ok = _send_email_from_template(
                template_name,
                recipient,
                {
                    "candidate_name": app.candidate_name or recipient,
                    "applicant_id": app.name,
                    "program": app.program or "",
                    "cycle_end_date": formatdate(application_end_date),
                    "institution_name": institution_name,
                    "admission_portal_url": get_url(get_user_portal_redirect_url(recipient, "/admission-dashboard")),
                },
                reference_doctype="Applicant",
                reference_name=app.name,
            )
            if ok:
                frappe.db.set_value("Applicant", app.name, "last_draft_reminder_sent", now_datetime(), update_modified=False)
                log_applicant_reminder_email(
                    recipient=recipient,
                    subject=subject,
                    reminder_type="Draft Application Reminder",
                    sender=_get_template_sender(template_name),
                    reference_doctype="Applicant",
                    reference_name=app.name,
                    email_template=template_name,
                )
                sent_count += 1

        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Draft Reminder Failed: {app.name}")

    return sent_count


# ---------------------------------------------------------------------------
# 3. Submitted But Unpaid Application Fee Reminder
# ---------------------------------------------------------------------------

def send_unpaid_fee_reminders(current_item=0, total_items=0, is_rejection_only=False):
    """
    Sends reminders to submitted applicants (docstatus=1) whose application_fee_status
    is still Pending or Requested.
    After application_end_date: rejects the application.
    """
    from slcm.admission.doctype.applicant_reminder_email_configuration.applicant_reminder_email_configuration import (
        should_send_reminder, get_rejection_reason,
    )
    from slcm.admission.doctype.applicant_reminder_email_log.applicant_reminder_email_log import (
        log_applicant_reminder_email,
    )

    cycle_name, cycle_end_date, application_end_date, cycle_status = _get_active_cycle()
    if not cycle_name or not application_end_date:
        return 0

    today_date = getdate(today())
    close_date = getdate(application_end_date)
    
    if is_rejection_only and today_date <= close_date:
        return 0

    applications = frappe.get_all(
        "Applicant",
        filters={
            "status": "Submitted",
            "admission_cycle": cycle_name,
            "application_fee_status": ["in", ["Pending", "Requested"]],
        },
        fields=["name", "email", "candidate_name", "program", "application_fee_amount", "last_fee_reminder_sent"],
        limit=0,
    )

    template_name = "Applicant Fee Payment Pending Reminder"
    institution_name = _get_institution_name()
    sent_count = 0

    for i, app in enumerate(applications):
        if total_items > 0:
            frappe.publish_realtime("progress", {
                "progress": [current_item + i, total_items],
                "title": "Applicant Reminders",
                "description": f"Unpaid Fee Reminders: {app.name}",
            }, user=frappe.session.user)

        try:
            recipient = app.email
            if not recipient:
                continue

            if not should_send_reminder("unpaid_fee", app.last_fee_reminder_sent, application_end_date):
                continue

            if today_date > close_date:
                rejection_reason = get_rejection_reason("unpaid_fee_rejection_reason")
                subject, ok = _send_email_from_template(
                    "Applicant Application Rejected",
                    recipient,
                    {
                        "candidate_name": app.candidate_name or recipient,
                        "applicant_id": app.name,
                        "program": app.program or "",
                        "rejection_reason": rejection_reason,
                        "cycle_end_date": formatdate(application_end_date),
                        "institution_name": institution_name,
                        "admission_portal_url": get_url(get_user_portal_redirect_url(recipient, "/admission-dashboard")),
                    },
                    reference_doctype="Applicant",
                    reference_name=app.name,
                )
                if ok:
                    rejected_status = frappe.db.get_value("Applicant Status", {"name": "Rejected"}, "name") or "Rejected"
                    frappe.db.set_value("Applicant", app.name, "status", rejected_status, update_modified=False)
                    frappe.db.set_value("Applicant", app.name, "rejected_reason", rejection_reason, update_modified=False)
                    frappe.db.commit()
                    log_applicant_reminder_email(
                        recipient=recipient,
                        subject=subject or "Application Rejected",
                        reminder_type="Unpaid Application Fee Rejected",
                        sender=_get_template_sender("Applicant Application Rejected"),
                        reference_doctype="Applicant",
                        reference_name=app.name,
                        email_template="Applicant Application Rejected",
                    )
                    sent_count += 1
                continue

            # Before deadline — send reminder
            if cycle_status == "Closed":
                continue

            subject, ok = _send_email_from_template(
                template_name,
                recipient,
                {
                    "candidate_name": app.candidate_name or recipient,
                    "applicant_id": app.name,
                    "program": app.program or "",
                    "application_fee_amount": app.application_fee_amount or 0,
                    "cycle_end_date": formatdate(application_end_date),
                    "institution_name": institution_name,
                    "admission_portal_url": get_url(get_user_portal_redirect_url(recipient, "/admission-dashboard")),
                },
                reference_doctype="Applicant",
                reference_name=app.name,
            )
            if ok:
                frappe.db.set_value("Applicant", app.name, "last_fee_reminder_sent", now_datetime(), update_modified=False)
                log_applicant_reminder_email(
                    recipient=recipient,
                    subject=subject,
                    reminder_type="Application Fee Reminder",
                    sender=_get_template_sender(template_name),
                    reference_doctype="Applicant",
                    reference_name=app.name,
                    email_template=template_name,
                )
                sent_count += 1

        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Unpaid Fee Reminder Failed: {app.name}")

    return sent_count

# ---------------------------------------------------------------------------
# 4. Admission Fee Pending Reminder
# ---------------------------------------------------------------------------

def send_admission_fee_reminders(current_item=0, total_items=0, is_rejection_only=False):
    """
    Sends reminders to applicants who have an unpaid Admission Fee assigned.
    Uses Applicant Fee Assignment DocType where fee_type='Admission Fee' and status='Assigned'.
    """
    from slcm.admission.doctype.applicant_reminder_email_configuration.applicant_reminder_email_configuration import (
        should_send_reminder, get_rejection_reason
    )
    from slcm.admission.doctype.applicant_reminder_email_log.applicant_reminder_email_log import (
        log_applicant_reminder_email,
    )
    from frappe.utils import today, getdate, formatdate

    cycle_name, cycle_end_date, application_end_date, cycle_status = _get_active_cycle()
    if not cycle_name or not cycle_end_date:
        return 0

    today_date = getdate(today())
    close_date = getdate(cycle_end_date)
    
    if is_rejection_only and today_date <= close_date:
        return 0

    fee_assignments = frappe.get_all(
        "Applicant Fee Assignment",
        filters={
            "fee_type": ["in", ["Course Fee", "Admission Fee"]],
            "status": "Assigned"
        },
        fields=["name", "applicant", "applicant_name", "academic_year", "program"],
        limit=0
    )

    template_name = "Course Fee Pending Reminder" if frappe.db.exists("Email Template", "Course Fee Pending Reminder") else "Admission Fee Pending Reminder"
    institution_name = _get_institution_name()
    sent_count = 0

    for i, assignment in enumerate(fee_assignments):
        if total_items > 0:
            frappe.publish_realtime("progress", {
                "progress": [current_item + i, total_items],
                "title": "Applicant Reminders",
                "description": f"Course Fee Reminders: {assignment.applicant}",
            }, user=frappe.session.user)

        try:
            if not frappe.db.exists("Applicant", assignment.applicant):
                continue
            applicant_doc = frappe.get_doc("Applicant", assignment.applicant)
            if applicant_doc.status == "Rejected":
                continue
            if applicant_doc.admission_cycle != cycle_name:
                continue
            recipient = applicant_doc.email
            if not recipient:
                continue

            # Need to add last_admission_fee_reminder_sent_on if missing
            last_sent = applicant_doc.get("last_admission_fee_reminder_sent_on")

            if not should_send_reminder("admission_fee", last_sent, cycle_end_date):
                continue

            if today_date > close_date:
                # Get specific admission fee rejection reason, or fallback to unpaid fee reason
                rejection_reason = get_rejection_reason("unpaid_admission_fee_rejection_reason") or get_rejection_reason("unpaid_fee_rejection_reason")
                subject, ok = _send_email_from_template(
                    "Applicant Application Rejected",
                    recipient,
                    {
                        "candidate_name": assignment.applicant_name or recipient,
                        "applicant_id": assignment.applicant,
                        "program": assignment.program or "",
                        "rejection_reason": rejection_reason,
                        "cycle_end_date": formatdate(cycle_end_date),
                        "institution_name": institution_name,
                        "admission_portal_url": get_url(get_user_portal_redirect_url(recipient, "/admission-dashboard")),
                    },
                    reference_doctype="Applicant",
                    reference_name=assignment.applicant,
                )
                if ok:
                    rejected_status = frappe.db.get_value("Applicant Status", {"name": "Rejected"}, "name") or "Rejected"
                    frappe.db.set_value("Applicant", assignment.applicant, "status", rejected_status, update_modified=False)
                    frappe.db.set_value("Applicant", assignment.applicant, "rejected_reason", rejection_reason, update_modified=False)
                    
                    # Optional: We could also cancel the Applicant Fee Assignment itself
                    frappe.db.set_value("Applicant Fee Assignment", assignment.name, "status", "Cancelled", update_modified=False)
                    
                    frappe.db.commit()
                    log_applicant_reminder_email(
                        recipient=recipient,
                        subject=subject or "Application Rejected",
                        reminder_type="Unpaid Course Fee Rejected",
                        sender=_get_template_sender("Applicant Application Rejected"),
                        reference_doctype="Applicant",
                        reference_name=assignment.applicant,
                        email_template="Applicant Application Rejected",
                    )
                    sent_count += 1
                continue

            # Send reminder
            if cycle_status == "Closed":
                continue

            subject, ok = _send_email_from_template(
                template_name,
                recipient,
                {
                    "candidate_name": assignment.applicant_name or recipient,
                    "applicant_id": assignment.applicant,
                    "program": assignment.program or "",
                    "cycle_end_date": formatdate(cycle_end_date),
                    "institution_name": institution_name,
                    "admission_portal_url": get_url(get_user_portal_redirect_url(recipient, "/admission-dashboard")),
                },
                reference_doctype="Applicant",
                reference_name=assignment.applicant,
            )
            if ok:
                # Reliably update the field, using raw SQL as fallback if metadata cache is stale
                try:
                    frappe.db.set_value("Applicant", assignment.applicant, "last_admission_fee_reminder_sent_on", now_datetime(), update_modified=False)
                except Exception:
                    pass
                frappe.db.sql("""UPDATE `tabApplicant` SET last_admission_fee_reminder_sent_on = %s WHERE name = %s""", (now_datetime(), assignment.applicant))
                
                log_applicant_reminder_email(
                    recipient=recipient,
                    subject=subject,
                    reminder_type="Course Fee Pending Reminder",
                    sender=_get_template_sender(template_name),
                    reference_doctype="Applicant",
                    reference_name=assignment.applicant,
                    email_template=template_name,
                )
                sent_count += 1

        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Course Fee Reminder Failed: {assignment.name}")

    return sent_count


# ---------------------------------------------------------------------------
# 5. Confirmation Fee Pending Reminder
# ---------------------------------------------------------------------------

def send_confirmation_fee_reminders(current_item=0, total_items=0, is_rejection_only=False):
    """
    Sends reminders to applicants who have an unpaid Confirmation Fee assigned.
    Uses Applicant Fee Assignment DocType where fee_type='Confirmation Fee' and status='Assigned'.
    Retrieves confirmation fee deadline and details from Fee Structure (due_date_for_confirmation_fee).
    """
    from slcm.admission.doctype.applicant_reminder_email_configuration.applicant_reminder_email_configuration import (
        should_send_reminder, get_rejection_reason
    )
    from slcm.admission.doctype.applicant_reminder_email_log.applicant_reminder_email_log import (
        log_applicant_reminder_email,
    )
    from frappe.utils import today, getdate, formatdate

    cycle_name, cycle_end_date, application_end_date, cycle_status = _get_active_cycle()
    if not cycle_name:
        return 0

    today_date = getdate(today())

    fee_assignments = frappe.get_all(
        "Applicant Fee Assignment",
        filters={
            "fee_type": "Confirmation Fee",
            "status": "Assigned"
        },
        fields=["name", "applicant", "applicant_name", "academic_year", "program", "offer_letter", "confirmation_fee", "total_amount", "admission_cycle"],
        limit=0
    )

    template_name = "Confirmation Fee Pending Reminder"
    institution_name = _get_institution_name()
    sent_count = 0

    for i, assignment in enumerate(fee_assignments):
        if total_items > 0:
            frappe.publish_realtime("progress", {
                "progress": [current_item + i, total_items],
                "title": "Applicant Reminders",
                "description": f"Confirmation Fee Reminders: {assignment.applicant}",
            }, user=frappe.session.user)

        try:
            if not frappe.db.exists("Applicant", assignment.applicant):
                continue
            applicant_doc = frappe.get_doc("Applicant", assignment.applicant)
            if applicant_doc.status == "Rejected":
                continue
            if applicant_doc.admission_cycle and applicant_doc.admission_cycle != cycle_name:
                continue
            recipient = applicant_doc.email
            if not recipient:
                continue

            # Fetch Offer Letter & Fee Structure details
            offer_doc = None
            fee_structure_name = None
            if assignment.offer_letter and frappe.db.exists("Offer Letter", assignment.offer_letter):
                offer_doc = frappe.get_doc("Offer Letter", assignment.offer_letter)
                fee_structure_name = offer_doc.fee_structure

            if not fee_structure_name:
                offer_name = frappe.db.get_value("Offer Letter", {"applicant": assignment.applicant}, "name")
                if offer_name:
                    offer_doc = frappe.get_doc("Offer Letter", offer_name)
                    fee_structure_name = offer_doc.fee_structure

            if not fee_structure_name:
                fee_structure_name = frappe.db.get_value("Fee Structure", {
                    "program": assignment.program or applicant_doc.program,
                    "academic_year": assignment.academic_year or applicant_doc.academic_year,
                    "is_confirmation_fee_applicable": 1
                }, "name")

            fee_structure_doc = None
            if fee_structure_name and frappe.db.exists("Fee Structure", fee_structure_name):
                fee_structure_doc = frappe.get_doc("Fee Structure", fee_structure_name)

            # Extract deadline from Fee Structure (due_date_for_confirmation_fee)
            confirmation_fee_deadline = None
            if fee_structure_doc and fee_structure_doc.get("due_date_for_confirmation_fee"):
                confirmation_fee_deadline = fee_structure_doc.due_date_for_confirmation_fee
            elif offer_doc and offer_doc.get("confirmation_fee_deadline"):
                confirmation_fee_deadline = offer_doc.confirmation_fee_deadline
            else:
                confirmation_fee_deadline = cycle_end_date

            close_date = getdate(confirmation_fee_deadline) if confirmation_fee_deadline else getdate(cycle_end_date)

            if is_rejection_only and today_date <= close_date:
                continue

            # Get confirmation fee amount
            confirmation_fee_amount = (
                assignment.confirmation_fee
                or (fee_structure_doc.confirmation_fee_amount if fee_structure_doc else None)
                or assignment.total_amount
                or 0
            )

            # Check last reminder sent
            last_sent = applicant_doc.get("last_confirmation_fee_reminder_sent_on")
            if not last_sent:
                last_sent = frappe.db.get_value(
                    "Applicant Reminder Email Log",
                    {
                        "reference_doctype": "Applicant",
                        "reference_name": assignment.applicant,
                        "reminder_type": "Confirmation Fee Pending Reminder",
                        "admission_cycle": cycle_name,
                    },
                    "sent_at",
                    order_by="sent_at desc",
                )

            if not should_send_reminder("confirmation_fee", last_sent, confirmation_fee_deadline):
                continue

            if today_date > close_date:
                # Past deadline -> Reject flow
                rejection_reason = get_rejection_reason("unpaid_confirmation_fee_rejection_reason") or get_rejection_reason("unpaid_fee_rejection_reason")
                subject, ok = _send_email_from_template(
                    "Applicant Application Rejected",
                    recipient,
                    {
                        "candidate_name": assignment.applicant_name or applicant_doc.candidate_name or recipient,
                        "applicant_id": assignment.applicant,
                        "program": assignment.program or applicant_doc.program or "",
                        "rejection_reason": rejection_reason,
                        "cycle_end_date": formatdate(confirmation_fee_deadline, "dd MMMM yyyy") if confirmation_fee_deadline else formatdate(cycle_end_date),
                        "institution_name": institution_name,
                        "admission_portal_url": get_url(get_user_portal_redirect_url(recipient, "/admission-dashboard")),
                    },
                    reference_doctype="Applicant",
                    reference_name=assignment.applicant,
                )
                if ok:
                    rejected_status = frappe.db.get_value("Applicant Status", {"name": "Rejected"}, "name") or "Rejected"
                    frappe.db.set_value("Applicant", assignment.applicant, "status", rejected_status, update_modified=False)
                    frappe.db.set_value("Applicant", assignment.applicant, "rejected_reason", rejection_reason, update_modified=False)
                    frappe.db.set_value("Applicant Fee Assignment", assignment.name, "status", "Cancelled", update_modified=False)
                    if assignment.offer_letter:
                        frappe.db.set_value("Offer Letter", assignment.offer_letter, "status", "Expired", update_modified=False)
                    frappe.db.commit()

                    log_applicant_reminder_email(
                        recipient=recipient,
                        subject=subject or "Application Rejected",
                        reminder_type="Unpaid Confirmation Fee Rejected",
                        sender=_get_template_sender("Applicant Application Rejected"),
                        reference_doctype="Applicant",
                        reference_name=assignment.applicant,
                        email_template="Applicant Application Rejected",
                        admission_cycle=cycle_name,
                    )
                    sent_count += 1
                continue

            # Before deadline -> Send Confirmation Fee Pending Reminder
            if cycle_status == "Closed":
                continue

            formatted_deadline = formatdate(confirmation_fee_deadline, "dd MMMM yyyy") if confirmation_fee_deadline else ""
            formatted_amount = f"{float(confirmation_fee_amount):,.2f}".rstrip('0').rstrip('.') if confirmation_fee_amount else ""

            subject, ok = _send_email_from_template(
                template_name,
                recipient,
                {
                    "candidate_name": assignment.applicant_name or applicant_doc.candidate_name or recipient,
                    "applicant_id": assignment.applicant,
                    "program": assignment.program or applicant_doc.program or "",
                    "confirmation_fee_amount": formatted_amount,
                    "confirmation_fee_deadline": formatted_deadline,
                    "due_date": formatted_deadline,
                    "fee_structure": fee_structure_name or "",
                    "cycle_end_date": formatted_deadline or formatdate(cycle_end_date),
                    "institution_name": institution_name,
                    "admission_portal_url": get_url(get_user_portal_redirect_url(recipient, "/admission-dashboard")),
                },
                reference_doctype="Applicant",
                reference_name=assignment.applicant,
            )
            if ok:
                try:
                    frappe.db.set_value("Applicant", assignment.applicant, "last_confirmation_fee_reminder_sent_on", now_datetime(), update_modified=False)
                except Exception:
                    pass
                frappe.db.sql("""UPDATE `tabApplicant` SET last_confirmation_fee_reminder_sent_on = %s WHERE name = %s""", (now_datetime(), assignment.applicant))

                log_applicant_reminder_email(
                    recipient=recipient,
                    subject=subject,
                    reminder_type="Confirmation Fee Pending Reminder",
                    sender=_get_template_sender(template_name),
                    reference_doctype="Applicant",
                    reference_name=assignment.applicant,
                    email_template=template_name,
                    admission_cycle=cycle_name,
                )
                sent_count += 1

        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Confirmation Fee Reminder Failed: {assignment.name}")

    return sent_count


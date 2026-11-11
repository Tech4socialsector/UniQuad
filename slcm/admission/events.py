import frappe
from frappe.utils import now, getdate, today
from slcm.admission.utils.regulatory import log_audit_trail
from slcm.admission.doctype.email_template_config.email_template_config import EmailTemplateConfig

def on_applicant_submit(doc, method):
    log_audit_trail(
        doc.doctype, doc.name,
        "Submitted", "status",
        "Draft", "Submitted", "General"
    )
    EmailTemplateConfig.send(
        trigger_event="Application Submitted",
        recipient_email=doc.email,
        context={
            "candidate_name": doc.candidate_name,
            "program": doc.program,
            "applicant_id": doc.name,
            "submission_date": now()
        }
    )

def on_applicant_cancel(doc, method):
    log_audit_trail(
        doc.doctype, doc.name,
        "Cancelled", "status",
        "Submitted", "Draft", "General"
    )

def on_document_submit(doc, method):
    log_audit_trail(
        doc.doctype, doc.name,
        "Submitted", "is_locked", 0, 1, "Document"
    )

def on_merit_list_publish(doc, method):
    log_audit_trail(
        doc.doctype, doc.name,
        "Submitted", "is_published", 0, 1, "Rank"
    )
    # Status changed trigger usually happens when merit list is published and status updated
    # But here we send a general update if applicants are listed
    applicants = frappe.get_all(
        "Merit List Applicant",
        {"parent": doc.name, "status": "Selected"},
        ["applicant_id"]
    )
    for entry in applicants:
        if not entry.applicant_id:
            continue
        applicant = frappe.get_doc("Applicant", entry.applicant_id)
        EmailTemplateConfig.send(
            trigger_event="Status Changed",
            recipient_email=applicant.email,
            context={
                "candidate_name": applicant.candidate_name,
                "program": applicant.program,
                "applicant_id": applicant.name,
                "status": "Listed in Merit List",
                "old_status": applicant.status,
                "campus": doc.campus
            }
        )

def on_seat_matrix_lock(doc, method):
    log_audit_trail(
        doc.doctype, doc.name,
        "Submitted", "is_locked", 0, 1, "Reservation"
    )

def auto_update_cycle_status():
    cycles = frappe.get_all(
        "Admission Cycle",
        filters={"status": ["!=", "Closed"]},
        fields=["name", "cycle_start_date", "cycle_end_date", "status"]
    )
    today_date = getdate(today())
    status_updates = []
    active_candidates = []

    # First pass: compute date-based target status.
    for cycle in cycles:
        start_date = getdate(cycle.cycle_start_date) if cycle.cycle_start_date else None
        end_date = getdate(cycle.cycle_end_date) if cycle.cycle_end_date else None

        new_status = "Draft"
        if start_date and end_date and start_date <= today_date <= end_date:
            new_status = "Active"
            active_candidates.append(cycle)
        elif end_date and today_date > end_date:
            new_status = "Closed"

        status_updates.append((cycle, new_status))

    # Enforce exactly one active cycle at most.
    # If multiple cycles qualify as Active, keep only one and downgrade others to Draft.
    if len(active_candidates) > 1:
        active_candidates_sorted = sorted(
            active_candidates,
            key=lambda c: (
                getdate(c.cycle_start_date) if c.cycle_start_date else getdate("1900-01-01"),
                getdate(c.cycle_end_date) if c.cycle_end_date else getdate("1900-01-01"),
                c.name or ""
            ),
            reverse=True,
        )
        keep_active_name = active_candidates_sorted[0].name
        status_updates = [
            (cycle, "Draft" if (new_status == "Active" and cycle.name != keep_active_name) else new_status)
            for cycle, new_status in status_updates
        ]

    # Second pass: apply status changes.
    for cycle, new_status in status_updates:
        if new_status != cycle.status:
            frappe.db.set_value("Admission Cycle", cycle.name, "status", new_status)
            log_audit_trail(
                "Admission Cycle", cycle.name,
                "Modified", "status",
                cycle.status, new_status, "General"
            )
    frappe.db.commit()

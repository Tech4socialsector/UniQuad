import frappe
from frappe.model.document import Document


class ApplicantReminderEmailConfiguration(Document):
    pass


def is_reminder_enabled(reminder_fieldname):
    """
    Checks if a specific reminder is enabled.
    reminder_fieldname: e.g., 'enable_not_started_reminder'
    """
    config = frappe.get_single("Applicant Reminder Email Configuration")
    return config.get(reminder_fieldname) == "Active"


def get_rejection_reason(reason_fieldname):
    """
    Gets the configurable rejection reason.
    reason_fieldname: e.g., 'draft_rejection_reason' | 'unpaid_admission_fee_rejection_reason'
    """
    config = frappe.get_single("Applicant Reminder Email Configuration")
    reason = config.get(reason_fieldname)
    if reason:
        return reason

    defaults = {
        "not_started_rejection_reason": "Your registration has been closed as you did not start your application before the admission cycle closing date.",
        "draft_rejection_reason": "Your application has been rejected as it was not submitted before the admission cycle closing date.",
        "unpaid_fee_rejection_reason": "Your application has been rejected as the application fee was not paid before the admission cycle closing date.",
        "unpaid_admission_fee_rejection_reason": "Your application has been rejected as the course fee was not paid before the admission cycle closing date.",
        "unpaid_confirmation_fee_rejection_reason": "Your application has been rejected as the confirmation fee was not paid before the deadline.",
    }
    return defaults.get(reason_fieldname, "")


def should_send_reminder(reminder_type, last_sent_date, cycle_end_date=None):
    """
    Determines if a reminder should be sent.
    reminder_type: 'not_started' | 'draft' | 'unpaid_fee'
    last_sent_date: date/datetime or None
    cycle_end_date: cycle_end_date from Admission Cycle
    """
    from frappe.utils import today, getdate, date_diff

    config = frappe.get_single("Applicant Reminder Email Configuration")

    field_map = {
        "not_started": ("enable_not_started_reminder", "not_started_reminder_interval"),
        "draft":       ("enable_draft_reminder",       "draft_reminder_interval"),
        "unpaid_fee":  ("enable_unpaid_fee_reminder",  "unpaid_fee_reminder_interval"),
        "admission_fee": ("enable_admission_fee_reminder", "admission_fee_reminder_interval"),
        "course_fee":    ("enable_admission_fee_reminder", "admission_fee_reminder_interval"),
        "confirmation_fee": ("enable_confirmation_fee_reminder", "confirmation_fee_reminder_interval"),
    }

    if reminder_type not in field_map:
        return False

    enable_field, interval_field = field_map[reminder_type]

    # 1. Must be Active
    if config.get(enable_field) != "Active":
        return False

    today_date = getdate(today())

    # 2. Cycle end date special logic
    if cycle_end_date:
        close_date = getdate(cycle_end_date)
        if today_date == close_date:
            # Send on the last day unless already sent today
            if last_sent_date and getdate(last_sent_date) == today_date:
                return False
            return True
        # After close date → trigger rejection flow
        if today_date > close_date:
            return True

    # 3. Same-day safety
    if last_sent_date and getdate(last_sent_date) == today_date:
        return False

    # 4. First-ever reminder
    if not last_sent_date:
        return True

    # 5. Interval check
    interval_val = config.get(interval_field)
    interval = frappe.utils.cint(interval_val) if interval_val is not None else 1
    days_since = date_diff(today_date, getdate(last_sent_date))
    return days_since >= interval


@frappe.whitelist()
def trigger_manual_reminders(reminders, is_rejection_only=False):
    """
    Enqueues the manual reminder task to run in the background.
    """
    if isinstance(reminders, str):
        import json
        reminders = json.loads(reminders)
        
    is_rejection_only = frappe.utils.cint(is_rejection_only) == 1 or str(is_rejection_only).lower() == 'true'

    if not reminders:
        return {"status": "success", "sent_count": 0}

    frappe.enqueue(
        "slcm.admission.doctype.applicant_reminder_email_configuration.applicant_reminder_email_configuration.run_manual_reminders_in_background",
        queue="long",
        timeout=3600,
        reminders=reminders,
        is_rejection_only=is_rejection_only,
        user=frappe.session.user
    )
    return {
        "status": "queued",
        "message": frappe._("Reminder emails are being processed in the background. You can safely close or refresh this page. You will receive an alert once completed.")
    }


def run_manual_reminders_in_background(reminders, is_rejection_only, user):
    """
    Runs the manual reminders in a background worker to avoid timeouts.
    """
    frappe.set_user(user)

    from slcm.admission.applicant_reminder_emails import (
        send_not_started_reminders,
        send_draft_applicant_reminders,
        send_unpaid_fee_reminders,
        send_admission_fee_reminders,
        send_confirmation_fee_reminders,
    )

    tasks_with_counts = []
    total_items = 0

    if "enable_not_started_reminder" in reminders:
        users = frappe.get_all("Has Role", filters={"role": "Applicant"}, fields=["parent"], limit=0)
        count = len(list(set([u.parent for u in users])))
        tasks_with_counts.append({"task": send_not_started_reminders, "count": count})
        total_items += count

    if "enable_draft_reminder" in reminders:
        count = frappe.db.count("Applicant", {"status": "Draft"})
        tasks_with_counts.append({"task": send_draft_applicant_reminders, "count": count})
        total_items += count

    if "enable_unpaid_fee_reminder" in reminders:
        count = frappe.db.count("Applicant", {
            "status": "Submitted",
            "application_fee_status": ["in", ["Pending", "Requested"]]
        })
        tasks_with_counts.append({"task": send_unpaid_fee_reminders, "count": count})
        total_items += count

    if "enable_admission_fee_reminder" in reminders or "enable_course_fee_reminder" in reminders:
        count = frappe.db.count("Applicant Fee Assignment", {
            "fee_type": ["in", ["Course Fee", "Admission Fee"]],
            "status": "Assigned"
        })
        tasks_with_counts.append({"task": send_admission_fee_reminders, "count": count})
        total_items += count

    if "enable_confirmation_fee_reminder" in reminders:
        count = frappe.db.count("Applicant Fee Assignment", {
            "fee_type": "Confirmation Fee",
            "status": "Assigned"
        })
        tasks_with_counts.append({"task": send_confirmation_fee_reminders, "count": count})
        total_items += count

    total_sent = 0
    current_processed = 0

    for item in tasks_with_counts:
        try:
            res = item["task"](current_item=current_processed, total_items=total_items, is_rejection_only=is_rejection_only)
            total_sent += (res or 0)
            current_processed += item["count"]
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Manual Reminder Trigger Failed: {item['task'].__name__}")

    # Send final success alert directly to the user via sockets
    if total_sent == 0:
        msg = frappe._("Background Task Completed: No eligible applicant is rejected at this time.") if is_rejection_only else frappe._("Background Task Completed: No reminder emails were sent. All eligible recipients may have already received their reminders today.")
    else:
        msg = frappe._("Background Task Completed: {0} reminder email(s) sent successfully.").format(total_sent)

    frappe.publish_realtime(
        "msgprint",
        {
            "message": msg,
            "title": "Applicant Reminders",
            "indicator": "green" if total_sent > 0 else "orange"
        },
        user=user
    )

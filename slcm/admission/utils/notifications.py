import frappe
from frappe.utils import now, today, date_diff


def log_communication(applicant, communication_type, category, subject, content, reference_doctype=None, reference_name=None):
    """Logs communication with an applicant."""
    try:
        frappe.get_doc({
            "doctype": "Applicant Communication Log",
            "applicant": applicant,
            "communication_type": communication_type,
            "notification_category": category,
            "sender": frappe.session.user if frappe.session.user != 'Guest' else 'Administrator',
            "subject": subject[:140] if subject else "",
            "content": content,
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "timestamp": now()
        }).insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"log_communication failed for {applicant}: {e}", "Notifications")


def notify_applicant(applicant, notification_type, message, action_url=None):
    """
    Creates portal notification and optionally sends email.
    Called whenever applicant stage changes or action needed.
    """
    try:
        config = frappe.get_single("Applicant Portal Config")

        # Create portal notification if enabled
        if config.enable_portal_notifications:
            frappe.get_doc({
                "doctype": "Applicant Notification",
                "applicant": applicant,
                "notification_type": notification_type,
                "message": message,
                "action_url": action_url or "",
                "is_read": 0,
                "created_on": now()
            }).insert(ignore_permissions=True)
            frappe.db.commit()

            # Map category correctly to allowed options
            category_map = {
                "Offer": "Offer Letter",
                "Fee": "Fee",
                "Stage Update": "Admission",
                "Seat Allocation": "Seat Allocation",
                "Merit": "Merit"
            }
            log_category = category_map.get(notification_type, "Generic")

            # Log portal notification
            log_communication(
                applicant=applicant,
                communication_type="Portal Notification",
                category=log_category,
                subject=notification_type,
                content=message,
                reference_doctype="Applicant",
                reference_name=applicant
            )

        # Send email if enabled
        if config.enable_email_notifications:
            _send_email_notification(applicant, notification_type, message)

    except Exception as e:
        frappe.log_error(f"notify_applicant failed for {applicant}: {e}", "Notifications")


def _send_email_notification(applicant, notification_type, message):
    """Send email using Email Template Config if a matching template exists."""
    try:
        email = frappe.db.get_value("Applicant", applicant, "email")
        if not email:
            return

        # Map notification type to trigger event
        event_map = {
            "Stage Update": "Status Changed",
            "Offer": "Offer Sent",
            "Document Request": "Document Rejected",
            "Fee": "Payment Confirmed",
            "General": "Status Changed"
        }
        trigger_event = event_map.get(notification_type, "Status Changed")

        template = frappe.db.get_value(
            "Email Template Config",
            {"trigger_event": trigger_event, "is_active": 1},
            "name"
        )
        if not template:
            # Fallback: send plain email
            frappe.sendmail(
                recipients=[email],
                subject=f"Admission Update — {notification_type}",
                message=message
            )
            return

        tmpl = frappe.get_doc("Email Template Config", template)
        applicant_doc = frappe.get_doc("Applicant", applicant)

        # Replace placeholders
        subject = tmpl.subject or f"Admission Update — {notification_type}"
        body = tmpl.body or message
        replacements = {
            "{{candidate_name}}": applicant_doc.get("candidate_name", ""),
            "{{applicant_id}}": applicant_doc.name,
            "{{program}}": applicant_doc.get("program", ""),
            "{{status}}": applicant_doc.get("status", ""),
            "{{message}}": message
        }
        for placeholder, value in replacements.items():
            subject = subject.replace(placeholder, str(value or ""))
            body = body.replace(placeholder, str(value or ""))

        frappe.sendmail(
            recipients=[email],
            sender=frappe.db.get_value("Email Account", tmpl.get("email_account"), "email_id") if tmpl.get("email_account") else None,
            subject=subject,
            message=body
        )

        # Map notification type to trigger event
        category_map = {
            "Offer": "Offer Letter",
            "Fee": "Fee",
            "Stage Update": "Admission",
            "Seat Allocation": "Seat Allocation",
            "Merit": "Merit"
        }
        log_category = category_map.get(notification_type, "Generic")

        # Log email notification
        log_communication(
            applicant=applicant,
            communication_type="Email",
            category=log_category,
            subject=subject,
            content=body,
            reference_doctype="Applicant",
            reference_name=applicant
        )

    except Exception as e:
        frappe.log_error(f"_send_email_notification failed: {e}", "Notifications")


def notify_stage_change(applicant, old_stage, new_stage):
    """Called when applicant moves to a new admission stage."""
    message = f"Your application has moved to the '{new_stage}' stage."
    notify_applicant(
        applicant=applicant,
        notification_type="Stage Update",
        message=message,
        action_url="/applicant-portal"
    )
    # Update current_stage on Applicant
    try:
        frappe.db.set_value("Applicant", applicant, "current_stage", new_stage)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"notify_stage_change update failed: {e}", "Notifications")


def get_unread_count(applicant):
    """Returns count of unread notifications for an applicant."""
    try:
        return frappe.db.count(
            "Applicant Notification",
            {"applicant": applicant, "is_read": 0}
        )
    except Exception:
        return 0


def get_notifications(applicant, limit=10):
    """Returns latest notifications for an applicant."""
    try:
        notifications = frappe.get_all(
            "Applicant Notification",
            filters={"applicant": applicant},
            fields=["name", "notification_type", "message",
                    "is_read", "created_on", "action_url"],
            order_by="created_on desc",
            limit=limit
        )
        return notifications
    except Exception as e:
        frappe.log_error(f"get_notifications failed: {e}", "Notifications")
        return []


def mark_all_read(applicant):
    """Marks all notifications as read for an applicant."""
    try:
        frappe.db.set_value(
            "Applicant Notification",
            {"applicant": applicant, "is_read": 0},
            "is_read", 1
        )
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"mark_all_read failed: {e}", "Notifications")


def send_offer_deadline_reminder(applicant_name, campus, days_left):
    applicant = frappe.get_doc("Applicant", applicant_name)
    try:
        frappe.sendmail(
            recipients=[applicant.email],
            subject=f"NLSIU | Offer Deadline Reminder - {days_left} day(s) left",
            message=f"""
            Dear {applicant.candidate_name},<br><br>
            This is a reminder that your admission offer for
            <b>{applicant.program}</b> at <b>{campus}</b>
            expires in <b>{days_left} day(s)</b>.<br><br>
            Please login immediately to accept your offer:
            <a href="/applicant-portal">Accept Offer</a><br><br>
            If you do not respond before the deadline, your offer
            will be automatically cancelled.<br><br>
            NLSIU Admissions Team
            """
        )

        log_communication(
            applicant=applicant_name,
            communication_type="Email",
            category="Offer Letter",
            subject=f"NLSIU | Offer Deadline Reminder - {days_left} day(s) left",
            content=f"Offer reminder sent for {applicant.program} at {campus}. {days_left} day(s) left.",
            reference_doctype="Applicant",
            reference_name=applicant_name
        )
    except Exception as e:
        frappe.log_error(str(e), "Offer Reminder Error")


def check_and_send_offer_reminders():
    offered_prefs = frappe.get_all(
        "Applicant Campus Preference",
        filters={"status": "Offered"},
        fields=["applicant", "campus", "acceptance_deadline"]
    )
    for pref in offered_prefs:
        if pref.acceptance_deadline:
            days_left = date_diff(pref.acceptance_deadline, today())
            if days_left in [3, 1]:
                send_offer_deadline_reminder(
                    pref.applicant, pref.campus, days_left
                )

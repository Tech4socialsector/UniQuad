# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import now_datetime, get_datetime, getdate, format_datetime
from datetime import datetime, timedelta

from slcm.slcm.utils.exam_schedule import get_student_programme


def check_and_send_absence_alerts():
    """Hourly scheduled job — alert parents when student has no RFID swipe within threshold."""
    try:
        settings = _get_alert_settings()
        if not settings or not _is_within_active_window(settings):
            return

        threshold_dt = now_datetime() - timedelta(hours=settings["threshold_hours"])
        sent = 0

        for student in _get_active_students():
            try:
                if _already_alerted_today(student.name):
                    continue

                last_swipe = _get_last_swipe(student.name)
                if last_swipe and last_swipe >= threshold_dt:
                    continue

                parents = _get_parent_emails(student.name)
                if not parents:
                    continue

                _send_alerts(student, parents, last_swipe, settings)
                _mark_alerted_today(student.name)
                sent += 1

            except Exception:
                frappe.log_error(
                    title=f"Parent RFID Alert — {student.name}",
                    message=frappe.get_traceback(),
                )

        if sent:
            frappe.logger().info(f"Parent RFID Alert: sent {sent} alert(s)")

    except Exception:
        frappe.log_error(title="Parent RFID Alert", message=frappe.get_traceback())


def _get_alert_settings():
    s = frappe.get_single("Attendance Settings")
    if not s.enable_parent_rfid_alert:
        return None

    day_map = {
        "Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4,
        "Friday": 5, "Saturday": 6, "Sunday": 7,
    }
    active_days = {day_map[r.day] for r in (s.parent_alert_active_days or []) if r.day in day_map}

    return {
        "threshold_hours": int(s.rfid_absence_threshold_hours or 12),
        "template": s.parent_alert_email_template or "Parent RFID Absence Alert",
        "active_days": active_days,
        "from_time": s.parent_alert_from_time,
        "to_time": s.parent_alert_to_time,
    }


def _is_within_active_window(settings):
    now = now_datetime()

    active_days = settings["active_days"]
    if active_days and now.isoweekday() not in active_days:
        return False

    from_t, to_t = settings["from_time"], settings["to_time"]
    if from_t and to_t:
        now_t = now.time()
        if isinstance(from_t, str):
            from_t = datetime.strptime(from_t, "%H:%M:%S").time()
        if isinstance(to_t, str):
            to_t = datetime.strptime(to_t, "%H:%M:%S").time()
        if not (from_t <= now_t <= to_t):
            return False

    return True


def _get_active_students():
    return frappe.get_all(
        "Student Master",
        filters={"student_status": "Active"},
        fields=["name", "first_name", "last_name", "academic_year"],
    )


def _get_last_swipe(student):
    rows = frappe.db.get_all(
        "Attendance Log",
        filters={"student": student},
        fields=["swipe_time"],
        order_by="swipe_time desc",
        limit=1,
    )
    return get_datetime(rows[0].swipe_time) if rows else None


def _get_parent_emails(student):
    rows = frappe.db.get_all(
        "Student Parent",
        filters={"parent": student, "parenttype": "Student Master"},
        fields=["first_name", "last_name", "email"],
    )
    return [r for r in rows if r.get("email")]


def _cache_key(student):
    return f"parent_rfid_alert::{student}::{getdate()}"


def _already_alerted_today(student):
    return bool(frappe.cache().get_value(_cache_key(student)))


def _mark_alerted_today(student):
    frappe.cache().set_value(_cache_key(student), 1, expires_in_sec=86400)


def _send_alerts(student, parents, last_swipe, settings):
    student_name = f"{student.first_name} {student.last_name or ''}".strip()
    programme = get_student_programme(student.name)
    check_time = format_datetime(now_datetime(), "dd MMM yyyy, hh:mm a")
    last_swipe_time = (
        format_datetime(last_swipe, "dd MMM yyyy, hh:mm a") if last_swipe else "No swipe on record"
    )

    context = {
        "student_name": student_name,
        "programme": programme,
        "academic_year": student.academic_year or "",
        "last_swipe_time": last_swipe_time,
        "check_time": check_time,
        "threshold_hours": settings["threshold_hours"],
    }

    try:
        template_doc = frappe.get_doc("Email Template", settings["template"])
    except frappe.DoesNotExistError:
        frappe.log_error(
            title="Parent RFID Alert — template missing",
            message=f"Email Template '{settings['template']}' not found. Set it in Attendance Settings → Parent Absence Alert.",
        )
        return

    formatted = template_doc.get_formatted_email(context)

    for parent in parents:
        try:
            frappe.sendmail(
                recipients=[parent.email],
                subject=formatted["subject"],
                message=formatted["message"],
                header=["Student RFID Absence Alert", "red"],
                now=True,
            )
        except Exception:
            frappe.log_error(
                title=f"Parent RFID Alert — email failed ({parent.email})",
                message=frappe.get_traceback(),
            )


@frappe.whitelist()
def trigger_absence_alerts_manually():
    if "System Manager" not in frappe.get_roles() and frappe.session.user != "Administrator":
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
    check_and_send_absence_alerts()
    return {"status": "success", "message": "Parent RFID absence alert check completed"}

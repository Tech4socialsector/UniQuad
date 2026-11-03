import frappe
from frappe.utils import today as get_today


def auto_advance_applicant_stages():
    """
    Scheduled job — runs daily.
    For each active applicant, checks if their current stage has ended
    and advances them to the next stage based on today's date.

    Trigger: Add to hooks.py scheduler_events daily list.
    """
    today = get_today()

    # Get all applicants who are not yet at final stages
    terminal_statuses = {"Offer Accepted", "Rejected", "Enrolled", "Withdrawn"}
    applicants = frappe.get_all(
        "Applicant",
        filters=[
            ["status", "not in", list(terminal_statuses)],
            ["admission_cycle", "!=", ""]
        ],
        fields=["name", "program", "admission_cycle",
                "current_stage", "intake_type", "status"]
    )

    advanced = 0
    for a in applicants:
        if not a.admission_cycle:
            continue

        # Get intake from Program
        # Programme.intake_type has been removed: treat it as empty -> "All".
        intake = "All"

        try:
            from slcm.admission.utils.stage_control import get_cycle_stages
            stages = get_cycle_stages(a.admission_cycle, intake)
        except Exception:
            continue

        if not stages:
            continue

        # Find which stage is active today by date
        active_stage_name = ""
        for s in stages:
            sd = str(getattr(s, "start_date", None) or getattr(s, "stage_start_date", None) or "")
            ed = str(getattr(s, "end_date", None) or getattr(s, "stage_end_date", None) or "")
            if sd and ed and sd <= today <= ed:
                active_stage_name = s.stage_name
                break

        # If active stage differs from current_stage, advance the applicant
        if active_stage_name and active_stage_name != (a.current_stage or ""):
            old_stage = a.current_stage or "—"
            frappe.db.set_value(
                "Applicant", a.name, "current_stage", active_stage_name
            )

            # Notify if stage has notify_applicant_on_entry = 1
            for s in stages:
                if s.stage_name == active_stage_name:
                    _notify_if_needed(a.name, s, old_stage)
                    break

            frappe.log_error(
                f"Stage auto-advanced: {a.name} | {old_stage} → {active_stage_name}",
                "Stage Scheduler Info"
            )
            advanced += 1

    frappe.db.commit()
    return f"Advanced {advanced} applicants."


def _notify_if_needed(applicant_name, stage, old_stage):
    """Create portal notification when applicant enters new stage."""
    if not getattr(stage, "notify_applicant_on_entry", 0):
        return
    try:
        frappe.get_doc({
            "doctype":           "Applicant Notification",
            "applicant":         applicant_name,
            "title":             f"Stage Update: {stage.stage_name}",
            "message":           (
                f"Your application has moved from '{old_stage}' "
                f"to '{stage.stage_name}'."
            ),
            "notification_type": "Stage Update",
            "link":              "/nlsat/my-applications",
            "is_read":           0
        }).insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"Stage notify failed: {e}", "Stage Notification")

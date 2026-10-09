import json

import frappe
from slcm.utils.faculty_portal import get_faculty_name


@frappe.whitelist()
def get_faculty_notifications():
    """Return notifications for the logged-in faculty member."""
    user = frappe.session.user
    if user == "Guest":
        return {"notifications": [], "count": 0, "urgent_count": 0}

    notifications = []

    # ── Portal Announcements ────────────────────────────────────────
    try:
        announcements = frappe.get_all(
            "Portal Announcement",
            filters={"is_published": 1},
            fields=["name", "title", "category", "priority"],
            order_by="creation desc",
            limit=10,
            ignore_permissions=True,
        )
        for ann in announcements:
            notifications.append({
                "type": "announcement",
                "title": ann.title,
                "category": ann.category or "Announcement",
                "priority": ann.priority or "Normal",
                "icon": "priority_high" if ann.priority == "Urgent" else "campaign",
                "link": "/faculty-portal/communication",
                "subtitle": "",
            })
    except Exception:
        pass

    # ── Pending attendance sessions ─────────────────────────────────
    try:
        faculty_name = get_faculty_name()
        if faculty_name:
            today = frappe.utils.today()
            co_names = frappe.get_all(
                "Course Offering",
                filters={"faculty": faculty_name, "status": ["in", ["Open", "Active"]]},
                pluck="name",
                ignore_permissions=True,
            )
            if co_names:
                pending = frappe.db.count(
                    "Attendance Session",
                    filters={
                        "course_offering": ["in", co_names],
                        "attendance_marked": 0,
                        "session_date": ["<=", today],
                        "session_status": "Scheduled",
                    },
                )
                if pending:
                    notifications.append({
                        "type": "attendance",
                        "title": f"{pending} attendance session{'s' if pending > 1 else ''} pending",
                        "category": "Attendance",
                        "priority": "Important" if pending > 2 else "Normal",
                        "icon": "pending_actions",
                        "link": "/faculty-portal/attendance",
                        "subtitle": "Click to mark attendance",
                    })
    except Exception:
        pass

    # ── Pending condonation requests ────────────────────────────────
    try:
        faculty_name = faculty_name if 'faculty_name' in dir() else get_faculty_name()
        if faculty_name:
            co_names = co_names if 'co_names' in dir() else []
            if co_names:
                cond_pending = frappe.db.count(
                    "Student Attendance Condonation",
                    filters={
                        "course_offering": ["in", co_names],
                        "final_status": "Pending",
                        "faculty_recommendation": ["in", ["", None, "Pending"]],
                    },
                )
                if cond_pending:
                    notifications.append({
                        "type": "condonation",
                        "title": f"{cond_pending} condonation request{'s' if cond_pending > 1 else ''} pending",
                        "category": "Condonation",
                        "priority": "Important",
                        "icon": "rate_review",
                        "link": "/faculty-portal/attendance",
                        "subtitle": "Awaiting your recommendation",
                    })
    except Exception:
        pass

    count = len(notifications)
    urgent_count = sum(1 for n in notifications if n.get("priority") == "Urgent")

    # Pending attendance sessions count (used by sidebar quick-stat)
    pending_sessions = 0
    try:
        fn = get_faculty_name()
        if fn:
            _co = frappe.get_all(
                "Course Offering",
                filters={"faculty": fn, "status": ["in", ["Open", "Active"]]},
                pluck="name",
                ignore_permissions=True,
            )
            if _co:
                pending_sessions = frappe.db.count(
                    "Attendance Session",
                    filters={
                        "course_offering": ["in", _co],
                        "attendance_marked": 0,
                        "session_date": ["<=", frappe.utils.today()],
                        "session_status": "Scheduled",
                    },
                )
    except Exception:
        pass

    return {
        "notifications": notifications[:15],
        "count": count,
        "urgent_count": urgent_count,
        "pending_sessions": pending_sessions,
    }


def _assert_session_owned_by_faculty(session, faculty_name):
    """Raise PermissionError if the session's course offering does not belong to this faculty."""
    faculty_co_names = frappe.get_all(
        "Course Offering",
        filters={"faculty": faculty_name},
        pluck="name",
        ignore_permissions=True,
    )
    if session.course_offering and session.course_offering not in faculty_co_names:
        frappe.throw("Not permitted", frappe.PermissionError)


# Attendance Type shown to faculty: RFID/QR taps are "Biometric", everything
# else (Manual, Auto, or unset) reads as "Class attendance".
def _attendance_type_label(source):
    return "Biometric" if source in ("RFID", "QR") else "Class attendance"


@frappe.whitelist()
def get_session_students(session_name):
    """Return students in an attendance session with their current status."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    session = frappe.get_doc("Attendance Session", session_name, ignore_permissions=True)
    _assert_session_owned_by_faculty(session, faculty_name)
    # OH rosters come from the OH Student Group; refresh in memory so sessions
    # saved before that rule (or before the group changed) list the right students.
    if session.session_type == "Office Hour":
        session.update_attendance_summary()

    # Attendance Session Student (roster) has no source/who/when — that detail
    # only lives on the actual Student Attendance record, when one exists.
    att_by_student = {
        r.student: r
        for r in frappe.get_all(
            "Student Attendance",
            filters={"attendance_session": session_name},
            fields=["name", "student", "source", "modified_by", "modified"],
            ignore_permissions=True,
        )
    }

    students = []
    for row in session.get("students", []):
        student_doc = frappe.db.get_value(
            "Student Master",
            row.student,
            ["first_name", "last_name", "registration_id", "passport_size_photo"],
            as_dict=True,
        ) or frappe._dict()
        full_name = " ".join(filter(None, [student_doc.get("first_name"), student_doc.get("last_name")]))
        att = att_by_student.get(row.student)
        marked_by_name = frappe.db.get_value("User", att.modified_by, "full_name") if att else None
        students.append({
            "student": row.student,
            "student_name": full_name or row.student,
            "reg_id": student_doc.get("registration_id") or row.student,
            "student_image": student_doc.get("passport_size_photo"),
            "status": row.status or "Absent",
            "source": (att.source if att else None) or "—",
            "type_label": _attendance_type_label(att.source if att else None) if att else "Not marked",
            "marked_by": marked_by_name or (att.modified_by if att else None) or "—",
            "marked_on": frappe.utils.format_datetime(att.modified, "dd MMM yyyy, hh:mm a") if att and att.modified else "—",
            "attendance_record": att.name if att else None,
        })

    # Session-level audit trail for the footer: when/who activated RFID,
    # and when attendance was last touched (most recent Student Attendance
    # edit — falls back to the session doc's own modified timestamp when no
    # Student Attendance records exist yet).
    rfid_activated_by_name = (
        frappe.db.get_value("User", session.rfid_activated_by, "full_name")
        if session.rfid_activated_by else None
    )
    last_updated_by = session.modified_by
    last_updated_on = session.modified
    if att_by_student:
        most_recent = max(att_by_student.values(), key=lambda r: r.modified or "")
        if most_recent.modified and (not last_updated_on or most_recent.modified > last_updated_on):
            last_updated_on = most_recent.modified
            last_updated_by = most_recent.modified_by
    last_updated_by_name = frappe.db.get_value("User", last_updated_by, "full_name") if last_updated_by else None

    session_audit = {
        "rfid_activated_by": rfid_activated_by_name or session.rfid_activated_by or None,
        "rfid_activated_on": frappe.utils.format_datetime(session.rfid_activation_time, "dd MMM yyyy, hh:mm a")
            if session.rfid_activation_time else None,
        "last_updated_by": last_updated_by_name or last_updated_by or "—",
        "last_updated_on": frappe.utils.format_datetime(last_updated_on, "dd MMM yyyy, hh:mm a")
            if last_updated_on else "—",
    }

    return {"students": students, "session_name": session_name, "session_audit": session_audit}


@frappe.whitelist()
def get_attendance_history(attendance_record):
    """Return the change history (status + source over time) for one
    Student Attendance record, sourced from Frappe's Version log.
    Requires track_changes to be enabled on Student Attendance — only
    changes made after that was turned on will appear here."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    att = frappe.get_doc("Student Attendance", attendance_record, ignore_permissions=True)
    if att.attendance_session:
        session = frappe.get_doc("Attendance Session", att.attendance_session, ignore_permissions=True)
        _assert_session_owned_by_faculty(session, faculty_name)

    versions = frappe.get_all(
        "Version",
        filters={"ref_doctype": "Student Attendance", "docname": attendance_record},
        fields=["name", "data", "owner", "creation"],
        order_by="creation asc",
        ignore_permissions=True,
    )

    # Track running state so each entry shows the resulting status/source at
    # that point in time, not just whichever field happened to change.
    running_status = None
    running_source = None
    raw_entries = []

    for v in versions:
        try:
            data = json.loads(v.data or "{}")
        except (ValueError, TypeError):
            continue
        changed = data.get("changed") or []
        field_changes = {row[0]: row[2] for row in changed if len(row) >= 3}
        if "status" not in field_changes and "source" not in field_changes:
            continue

        running_status = field_changes.get("status", running_status)
        running_source = field_changes.get("source", running_source)
        by_name = frappe.db.get_value("User", v.owner, "full_name") or v.owner

        raw_entries.append({
            "creation": v.creation,
            "status": running_status or "—",
            "by": by_name,
            "source": running_source or "—",
            "type_label": _attendance_type_label(running_source),
        })

    # Always include the current state as the most recent entry, even if no
    # Version rows exist yet (e.g. track_changes was enabled after creation,
    # or this is the very first save since it was turned on).
    current_by = frappe.db.get_value("User", att.modified_by, "full_name") or att.modified_by
    raw_entries.append({
        "creation": att.modified,
        "status": att.status or "—",
        "by": current_by or "—",
        "source": att.source or "—",
        "type_label": _attendance_type_label(att.source),
    })

    # Collapse consecutive entries that look identical to the faculty — same
    # status and same displayed Type — even if the raw `source` values differ
    # (e.g. "Manual" vs None both render as "Class attendance"). Saving the
    # same attendance twice in a row (Mark then a no-op Edit) creates two
    # real Version rows but no real second event worth showing. Keep the
    # earliest timestamp of each such streak.
    entries = []
    for entry in raw_entries:
        if entries and entries[-1]["status"] == entry["status"] and entries[-1]["type_label"] == entry["type_label"]:
            continue
        entries.append(entry)

    for entry in entries:
        entry["date"] = frappe.utils.format_datetime(entry["creation"], "dd MMM yyyy, hh:mm a") if entry["creation"] else "—"
        del entry["creation"]

    entries.reverse()  # most recent first, matching the reference screenshot
    return {"entries": entries, "tracked": bool(versions)}


@frappe.whitelist()
def get_class_participation(session_name):
    """Class Participants tab: the week's Class-Participation group for this
    session, which hour slot this class records into, and each student's
    already-saved participation/mark for that slot."""
    from slcm.slcm.utils.class_participation import (
        get_participation_context,
        get_participation_roster,
    )

    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    session = frappe.get_doc("Attendance Session", session_name, ignore_permissions=True)
    _assert_session_owned_by_faculty(session, faculty_name)

    ctx = get_participation_context(session)
    if not ctx.available:
        return {"context": ctx, "students": [], "slot_recorded": False}

    return {"context": ctx, **get_participation_roster(ctx)}


@frappe.whitelist()
def save_attendance(session_name, attendance, participation=None):
    """Save attendance for an attendance session, plus (optionally) class
    participation marks for the session's week/slot - see
    slcm.slcm.utils.class_participation."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    session = frappe.get_doc("Attendance Session", session_name, ignore_permissions=True)
    _assert_session_owned_by_faculty(session, faculty_name)
    # Same roster the faculty was shown (see get_session_students)
    if session.session_type == "Office Hour":
        session.update_attendance_summary()

    if isinstance(attendance, str):
        attendance = json.loads(attendance)

    # Build a lookup of submitted statuses
    att_map = {row["student"]: row["status"] for row in attendance}

    present_count = 0
    absent_count = 0

    for row in session.get("students", []):
        status = att_map.get(row.student, "Absent")
        row.status = status
        if status == "Present":
            present_count += 1
        else:
            absent_count += 1

        # Upsert the real Student Attendance record — Attendance Session
        # Student (the roster row above) has no source/who/when, so without
        # this, "who marked it / via what method" can never be shown later.
        existing = frappe.db.exists(
            "Student Attendance",
            {"student": row.student, "attendance_session": session_name, "docstatus": ("<", 2)},
        )
        if existing:
            att_doc = frappe.get_doc("Student Attendance", existing)
            att_doc.status = status
            att_doc.source = "Manual"
            att_doc.save(ignore_permissions=True)
        else:
            frappe.get_doc({
                "doctype": "Student Attendance",
                "student": row.student,
                "attendance_session": session_name,
                "class_schedule": session.class_schedule,
                "course_schedule": session.course_schedule,
                "course_offer": session.course_offering,
                "attendance_date": session.session_date,
                "date": session.session_date,
                "session_type": session.session_type,
                "status": status,
                "source": "Manual",
                "hours_counted": session.duration_hours or 1.0,
            }).insert(ignore_permissions=True)

    total = len(session.get("students", []))
    pct = round((present_count / total) * 100, 2) if total else 0

    # Reload before this final save — the Student Attendance upserts above
    # can touch the parent session's `modified` timestamp via controller
    # hooks, and saving the stale in-memory `session` doc at that point
    # trips Frappe's TimestampMismatchError ("has been modified after you
    # have opened it").
    session = frappe.get_doc("Attendance Session", session_name, ignore_permissions=True)
    for row in session.get("students", []):
        row.status = att_map.get(row.student, "Absent")
    session.present_count = present_count
    session.absent_count = absent_count
    session.total_students = total
    session.attendance_percentage = pct
    session.attendance_marked = 1
    session.flags.ignore_validate = True

    session.save(ignore_permissions=True)

    # Force the aggregate counters in DB in case the controller overrides them
    frappe.db.sql("""
        UPDATE `tabAttendance Session`
        SET present_count=%s, absent_count=%s, total_students=%s,
            attendance_percentage=%s, attendance_marked=1
        WHERE name=%s
    """, (present_count, absent_count, total, pct, session_name))

    # Class participation goes in the same transaction, so a validation error
    # (e.g. a mark out of range) rolls back the attendance save too instead of
    # leaving the two half-saved.
    from slcm.slcm.utils.class_participation import (
        get_participation_context,
        save_class_participation,
    )

    if isinstance(participation, str):
        participation = json.loads(participation) if participation else None

    ctx = get_participation_context(session)
    if ctx.available:
        final_att_map = {row.student: row.status for row in session.get("students", [])}
        save_class_participation(session, ctx, participation, final_att_map)
    elif participation:
        frappe.throw(ctx.reason or "Class participation cannot be recorded for this session.")

    frappe.db.commit()

    return {"success": True, "present": present_count, "absent": absent_count, "total": total}


@frappe.whitelist()
def save_condonation_recommendation(doc_name, recommendation):
    """Save faculty recommendation on a condonation request."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    allowed = ["Recommended", "Not Recommended"]
    if recommendation not in allowed:
        frappe.throw("Invalid recommendation value")

    doc = frappe.get_doc("Student Attendance Condonation", doc_name, ignore_permissions=True)

    # Verify ownership: the condonation's course offering must belong to this faculty.
    # Use the same co_names list approach used throughout the portal so that empty/None
    # faculty fields on Course Offering don't cause a false permission denial.
    faculty_co_names = frappe.get_all(
        "Course Offering",
        filters={"faculty": faculty_name},
        pluck="name",
        ignore_permissions=True,
    )
    if doc.course_offering and doc.course_offering not in faculty_co_names:
        frappe.throw("Not permitted", frappe.PermissionError)

    doc.faculty_recommendation = recommendation
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True}


@frappe.whitelist()
def create_venue_booking(event_name, venue_type, room, start_datetime, end_datetime,
                         expected_attendees=0, reason=""):
    """Create a Venue Booking record on behalf of the logged-in faculty."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    if not event_name or not venue_type or not room or not start_datetime or not end_datetime:
        frappe.throw("Event name, venue type, room, start and end date/time are all required")

    # Resolve the faculty's full display name from the Faculty record
    faculty_doc = frappe.db.get_value(
        "Faculty", faculty_name, ["first_name", "last_name"], as_dict=True
    )
    if faculty_doc:
        requester_display = " ".join(filter(None, [faculty_doc.first_name, faculty_doc.last_name]))
    else:
        requester_display = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user

    doc = frappe.new_doc("Venue Booking")
    doc.event_name = event_name
    doc.venue_type = venue_type
    doc.venue = room
    doc.start_datetime = start_datetime
    doc.end_datetime = end_datetime
    doc.expected_attendees = int(expected_attendees or 0)
    doc.reason = reason
    doc.requester_type = "Faculty"
    doc.requester_name = requester_display or str(faculty_name)
    doc.status = "Pending Allotment"
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "name": doc.name}


@frappe.whitelist()
def update_profile(phone="", qualification="", specialization="", experience_years=None,
                   highlights="", institution=""):
    """Update editable fields on the Faculty record for the logged-in user."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    doc = frappe.get_doc("Faculty", faculty_name, ignore_permissions=True)

    if phone is not None:
        doc.phone = phone.strip()
    if qualification is not None:
        doc.qualification = qualification.strip()
    if specialization is not None:
        doc.specialization = specialization.strip()
    if experience_years is not None and str(experience_years).strip() != "":
        try:
            doc.experience_years = int(experience_years)
        except (ValueError, TypeError):
            frappe.throw("Experience years must be a number")
    if highlights is not None:
        doc.highlights = highlights.strip()
    if institution is not None:
        doc.institution = institution.strip()

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True}


@frappe.whitelist()
def change_password(old_password, new_password):
    """Change the logged-in user's password after verifying the current one."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    if not old_password or not new_password:
        frappe.throw("Both current and new password are required")

    if len(new_password) < 8:
        frappe.throw("New password must be at least 8 characters")

    from frappe.utils.password import check_password, update_password

    try:
        check_password(frappe.session.user, old_password)
    except Exception:
        frappe.throw("Current password is incorrect. Please try again.")

    try:
        update_password(frappe.session.user, new_password)
        frappe.db.commit()
    except Exception as e:
        frappe.throw(f"Could not update password: {e}")

    return {"success": True}


@frappe.whitelist()
def get_reset_password_url():
    """Generate a password reset key for the logged-in user and return the
    /update-password URL built from the actual request host — bypassing
    Frappe's host_name site config which may not match the dev server port."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    import hashlib, secrets

    key = secrets.token_hex(32)
    hashed_key = hashlib.sha256(key.encode()).hexdigest()

    frappe.db.set_value("User", user, {
        "reset_password_key": hashed_key,
        "last_reset_password_key_generated_on": frappe.utils.now_datetime(),
    })
    frappe.db.commit()

    # Build URL from the actual incoming request host so it always works
    # regardless of the site config host_name (fixes local dev port issues).
    request = getattr(frappe.local, "request", None)
    if request and getattr(request, "host", None):
        proto = "https://" if frappe.get_request_header("X-Forwarded-Proto", "") == "https" else "http://"
        base = proto + request.host
    else:
        base = frappe.utils.get_url()

    return {"url": base + "/update-password?key=" + key}


@frappe.whitelist()
def save_preferences(
    font_size_pref="Normal",
    layout_density_pref="Normal",
    notify_assignment_submission=1,
    notify_attendance_discrepancy=1,
    notify_student_query=1,
    notify_leave_request_update=1,
    notify_marks_due=1,
    email_digest_frequency="Realtime",
    hide_today_schedule=0,
    hide_pending_evaluations=0,
    hide_class_statistics=0,
    hide_workload_summary=0,
    hide_leave_status=0,
    default_course_view="Grid",
):
    """Create or update Faculty Portal User Preferences for the logged-in user."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    user = frappe.session.user

    try:
        doc = frappe.get_doc("Faculty Portal User Preferences", user)
    except frappe.DoesNotExistError:
        doc = frappe.new_doc("Faculty Portal User Preferences")
        doc.faculty_user = user

    doc.font_size_pref              = font_size_pref or "Normal"
    doc.layout_density_pref         = layout_density_pref or "Normal"
    doc.notify_assignment_submission = _int(notify_assignment_submission)
    doc.notify_attendance_discrepancy= _int(notify_attendance_discrepancy)
    doc.notify_student_query         = _int(notify_student_query)
    doc.notify_leave_request_update  = _int(notify_leave_request_update)
    doc.notify_marks_due             = _int(notify_marks_due)
    doc.email_digest_frequency       = email_digest_frequency or "Realtime"
    doc.hide_today_schedule          = _int(hide_today_schedule)
    doc.hide_pending_evaluations     = _int(hide_pending_evaluations)
    doc.hide_class_statistics        = _int(hide_class_statistics)
    doc.hide_workload_summary        = _int(hide_workload_summary)
    doc.hide_leave_status            = _int(hide_leave_status)
    doc.default_course_view          = default_course_view or "Grid"

    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True}


@frappe.whitelist()
def get_dashboard_stats():
    """Return faculty dashboard statistics."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found for this user", frappe.DoesNotExistError)

    today = frappe.utils.today()

    co_names = frappe.get_all(
        "Course Offering",
        filters={"faculty": faculty_name, "status": ["in", ["Open", "Active"]]},
        pluck="name",
        ignore_permissions=True,
    )

    today_classes = frappe.db.count(
        "Attendance Session",
        filters={
            "course_offering": ["in", co_names] if co_names else ["in", ["__none__"]],
            "session_date": today,
        },
    ) if co_names else 0

    pending_att = frappe.db.count(
        "Attendance Session",
        filters={
            "course_offering": ["in", co_names] if co_names else ["in", ["__none__"]],
            "attendance_marked": 0,
            "session_date": ["<=", today],
            "session_status": "Scheduled",
        },
    ) if co_names else 0

    return {
        "total_subjects": len(co_names),
        "todays_class_count": today_classes,
        "attendance_pending": pending_att,
    }


# ── Drill-down helpers ─────────────────────────────────────────────────────

def _get_faculty_co_names(faculty_name):
    """Return list of active course offering names for the faculty."""
    active_ays = frappe.get_all("Academic Year", filters={"status": "Active"}, pluck="name")
    return frappe.get_all(
        "Course Offering",
        filters={"faculty": faculty_name, "status": "Active", "academic_year": ["in", active_ays]},
        pluck="name",
        ignore_permissions=True,
    )


@frappe.whitelist()
def get_student_marks_detail(scm_name):
    """Return component-wise marks breakdown for a Student Course Marks record.
    Only accessible to the faculty who owns the course offering."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    scm = frappe.get_doc("Student Course Marks", scm_name, ignore_permissions=True)

    # Verify the course belongs to this faculty via Course Offering
    owns = frappe.db.sql(
        """
        SELECT 1
        FROM `tabCourse Offering` co
        WHERE co.course_title = %(course)s
          AND co.faculty = %(faculty)s
        LIMIT 1
        """,
        {"course": scm.course, "faculty": faculty_name},
    )
    if not owns:
        frappe.throw("Not permitted", frappe.PermissionError)

    # Fetch the evaluation schema components with max marks so the edit form
    # can show labels, current values, and enforce max-marks validation.
    schema_components = []
    if scm.evaluation_schema:
        schema_rows = frappe.db.sql(
            """
            SELECT sac.component, sac.assessment_type, sac.label,
                   sac.maximum_marks, ec.component_name, eat.type_name
            FROM `tabSchema Assessment Config` sac
            LEFT JOIN `tabExam Component` ec ON ec.name = sac.component
            LEFT JOIN `tabExam Assessment Type` eat ON eat.name = sac.assessment_type
            WHERE sac.parent = %(schema)s
            ORDER BY sac.idx ASC
            """,
            {"schema": scm.evaluation_schema},
            as_dict=True,
        )
        entry_map = {
            (r.component, r.assessment_type): frappe.utils.flt(r.marks)
            for r in scm.get("marks_entries", [])
        }
        for sr in schema_rows:
            label = sr.label or sr.component_name or sr.component or ""
            schema_components.append({
                "component": sr.component,
                "assessment_type": sr.assessment_type,
                "label": label,
                "max_marks": frappe.utils.flt(sr.maximum_marks),
                "marks": entry_map.get((sr.component, sr.assessment_type), None),
            })
    else:
        for row in scm.get("marks_entries", []):
            label = row.label or (
                frappe.db.get_value("Exam Component", row.component, "component_name")
                if row.component else ""
            ) or row.component or ""
            schema_components.append({
                "component": row.component,
                "assessment_type": row.assessment_type,
                "label": label,
                "max_marks": None,
                "marks": frappe.utils.flt(row.marks),
            })

    return {
        "scm_name": scm.name,
        "course": scm.course,
        "exam_plan": scm.exam_plan,
        "components": schema_components,
        "total_marks": frappe.utils.flt(scm.total_marks),
        "grade": scm.grade or "—",
        "moderated_grade": scm.moderated_grade or "",
        "updated_final_marks": frappe.utils.flt(scm.updated_final_marks) if scm.updated_final_marks else None,
        "updated_grade": scm.updated_grade or "",
        "remark": scm.remark or "",
        "enrollment_status": scm.enrollment_status or "",
        "attendance_status": scm.attendance_status or "",
    }


@frappe.whitelist()
def save_student_marks(scm_name, component, assessment_type, marks):
    """Save a single component marks entry for a student. Faculty-only."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    scm = frappe.get_doc("Student Course Marks", scm_name, ignore_permissions=True)

    # Verify ownership
    owns = frappe.db.sql(
        """SELECT 1 FROM `tabCourse Offering` co
           WHERE co.course_title = %(course)s AND co.faculty = %(faculty)s LIMIT 1""",
        {"course": scm.course, "faculty": faculty_name},
    )
    if not owns:
        frappe.throw("Not permitted", frappe.PermissionError)

    # Check Access Result Settings lock + deadline
    access = frappe.db.get_value(
        "Access Result Settings",
        {"exam_plan": scm.exam_plan, "course": scm.course},
        ["edit_access", "edit_deadline", "status"],
        as_dict=True,
    ) or frappe._dict({"edit_access": 1, "edit_deadline": None, "status": "UNLOCKED"})

    if access.get("status") == "LOCKED":
        frappe.throw("Result entry is locked for this course.")
    if not int(access.get("edit_access") or 1):
        frappe.throw("Edit access is disabled for this course.")
    edit_deadline = access.get("edit_deadline")
    if edit_deadline and frappe.utils.now_datetime() > frappe.utils.get_datetime(edit_deadline):
        frappe.throw("The edit deadline for this course has passed.")

    fvalue = frappe.utils.flt(marks) if marks not in (None, "", "null") else None

    sme_name = frappe.db.get_value(
        "Student Marks Entry",
        {"parent": scm_name, "component": component, "assessment_type": assessment_type},
        "name",
    )
    if sme_name:
        frappe.db.set_value("Student Marks Entry", sme_name, "marks", fvalue if fvalue is not None else 0.0)
    else:
        if fvalue is not None:
            frappe.db.sql(
                """INSERT INTO `tabStudent Marks Entry`
                   (name, creation, modified, modified_by, owner,
                    parent, parenttype, parentfield, component, assessment_type, marks)
                   VALUES (%(n)s, NOW(), NOW(), %(u)s, %(u)s,
                           %(p)s, 'Student Course Marks', 'marks_entries',
                           %(c)s, %(a)s, %(v)s)""",
                {"n": frappe.generate_hash("", 10), "u": frappe.session.user,
                 "p": scm_name, "c": component, "a": assessment_type, "v": fvalue},
            )

    frappe.db.commit()

    # Recalculate total + grade by delegating to examination_result module
    from slcm.slcm.page.examination_result.examination_result import _recalculate_student_marks
    return _recalculate_student_marks(scm_name, scm.course, scm.exam_plan)


@frappe.whitelist()
def drilldown_subjects():
    """Drill-down: all course offerings assigned to this faculty."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)
    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    active_ays = frappe.get_all("Academic Year", filters={"status": "Active"}, pluck="name")

    offerings = frappe.get_all(
        "Course Offering",
        filters={"faculty": faculty_name, "status": "Active", "academic_year": ["in", active_ays]},
        fields=["name", "course_name", "term_name", "academic_year",
                "credit_value", "status"],
        order_by="academic_year desc, term_name asc, course_name asc",
        ignore_permissions=True,
    )

    rows = []
    for co in offerings:
        try:
            enr = frappe.db.sql(
                """SELECT COUNT(DISTINCT se.student) AS cnt
                   FROM `tabStudent Enrollment Course` sec
                   JOIN `tabStudent Enrollment` se ON se.name = sec.parent
                   WHERE sec.course_offering = %s AND sec.status = 'Enrolled'""",
                co.name, as_dict=True,
            )
            students = (enr[0].cnt or 0) if enr else 0
        except Exception:
            students = 0

        try:
            att = frappe.db.sql(
                """SELECT AVG(attendance_percentage) AS avg_pct, COUNT(*) AS sess
                   FROM `tabAttendance Session`
                   WHERE course_offering = %s AND attendance_marked = 1""",
                co.name, as_dict=True,
            )
            avg_pct = round(float((att[0].avg_pct or 0) if att else 0), 1)
            sessions = (att[0].sess or 0) if att else 0
        except Exception:
            avg_pct = 0.0
            sessions = 0

        import urllib.parse
        rows.append({
            "course_offering": co.name,
            "course_name": co.course_name or co.name,
            "course_link": f"/faculty-portal/my-classes?course_offering={urllib.parse.quote(co.name)}",
            "term": co.term_name or "—",
            "academic_year": co.academic_year or "—",
            "credits": co.credit_value or 0,
            "students": students,
            "sessions": sessions,
            "avg_attendance": avg_pct,
            "status": co.status or "Active",
            "action_btn": "Mark Attendance",
            "action_link": f"/faculty-portal/attendance?course_offering={urllib.parse.quote(co.name)}#attendance-sessions-card",
        })

    return {
        "title": "Courses",
        "hide_count": True,
        "columns": [
            {"key": "course_name",    "label": "Course Name",      "type": "link", "link_key": "course_link"},
            {"key": "term",           "label": "Term",             "type": "text"},
            {"key": "academic_year",  "label": "Academic Year",    "type": "text"},
            {"key": "credits",        "label": "Credits",          "type": "number"},
            {"key": "students",       "label": "Students",         "type": "number"},
            {"key": "sessions",       "label": "Sessions Held",    "type": "number"},
            {"key": "avg_attendance", "label": "Avg Attendance %", "type": "percent"},
            {"key": "status",         "label": "Status",           "type": "badge"},
            {"key": "action_btn",     "label": "Action",           "type": "button", "link_key": "action_link"},
        ],
        "rows": rows,
        "count": len(rows),
    }


@frappe.whitelist()
def drilldown_students():
    """Drill-down: all enrolled students across this faculty's courses."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)
    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    co_names = _get_faculty_co_names(faculty_name)
    if not co_names:
        return {"title": "Total Students", "columns": [], "rows": [], "count": 0}

    try:
        raw = frappe.db.sql(
            """
            SELECT DISTINCT
                se.student,
                sm.first_name, sm.last_name,
                sm.registration_id,
                sm.gender,
                sm.passport_size_photo,
                sm.section as student_section,
                pm.program_name,
                sec.course_offering,
                co.course_name,
                co.term_name,
                co.academic_year
            FROM `tabStudent Enrollment Course` sec
            JOIN `tabStudent Enrollment` se ON se.name = sec.parent
            JOIN `tabCourse Offering` co ON co.name = sec.course_offering
            LEFT JOIN `tabStudent Master` sm ON sm.name = se.student
            LEFT JOIN `tabProgramme` pm ON pm.name = se.program
            WHERE sec.course_offering IN %s
              AND sec.status = 'Enrolled'
            ORDER BY co.course_name, sm.last_name, sm.first_name
            """,
            (tuple(co_names),),
            as_dict=True,
        )
    except Exception:
        raw = []

    rows = []
    for r in raw:
        full_name = " ".join(filter(None, [r.get("first_name"), r.get("last_name")])) or r.get("student", "")
        rows.append({
            "student_id": r.get("registration_id") or r.get("student", ""),
            "student_name": full_name,
            "student_image": r.get("passport_size_photo") or "",
            "gender": r.get("gender") or "—",
            "program": r.get("program_name") or r.get("program") or "—",
            "course_name": r.get("course_name") or r.get("course_offering", ""),
            "term": r.get("term_name") or "—",
            "academic_year": r.get("academic_year") or "—",
            "section": r.get("student_section") or "—",
        })
        
    active_ay = frappe.get_cached_value("Academic Year", {"status": "Active"}, "name")

    return {
        "title": "Enrolled Students",
        "columns": [
            {"key": "student_id",   "label": "Student ID",    "type": "text"},
            {"key": "student_name", "label": "Name",          "type": "person", "image_key": "student_image"},
            {"key": "gender",       "label": "Gender",        "type": "text"},
            {"key": "program",      "label": "Programme",       "type": "text"},
            {"key": "course_name",  "label": "Course",        "type": "text"},
            {"key": "section",      "label": "Section",       "type": "text"},
        ],
        "rows": rows,
        "count": len(rows),
        "filters": [
            {"key": "academic_year", "label": "Academic Year"},
            {"key": "term", "label": "Term"},
            {"key": "program", "label": "Programme"},
            {"key": "course_name", "label": "Course"},
            {"key": "section", "label": "Section"},
        ],
        "default_ay": active_ay
    }


@frappe.whitelist()
def drilldown_todays_classes():
    """Drill-down: today's scheduled sessions."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)
    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    co_names = _get_faculty_co_names(faculty_name)
    today = frappe.utils.today()

    if not co_names:
        return {"title": "Today's Classes", "columns": [], "rows": [], "count": 0}

    raw = frappe.get_all(
        "Attendance Session",
        filters=[
            ["course_offering", "in", co_names],
            ["session_date", "=", today],
        ],
        fields=["name", "course_offering", "session_date",
                "session_start_time", "session_end_time",
                "room", "session_status", "total_students",
                "present_count", "absent_count", "attendance_percentage", "attendance_marked"],
        order_by="session_start_time asc",
        ignore_permissions=True,
    )

    co_map = {co: frappe.db.get_value("Course Offering", co, "course_name") or co
              for co in co_names}

    from slcm.utils.faculty_portal import fmt_time

    rows = []
    for s in raw:
        rows.append({
            "session": s.name,
            "course_name": co_map.get(s.course_offering, s.course_offering),
            "date": frappe.utils.formatdate(s.session_date, "dd MMM yyyy"),
            "start_time": fmt_time(s.session_start_time),
            "end_time": fmt_time(s.session_end_time),
            "venue": s.room or "—",
            "total_students": s.total_students or 0,
            "present": s.present_count or 0,
            "absent": s.absent_count or 0,
            "attendance_pct": round(float(s.attendance_percentage or 0), 1),
            "status": "Marked" if s.attendance_marked else "Pending",
        })

    return {
        "title": "Today's Classes",
        "columns": [
            {"key": "course_name",    "label": "Course",        "type": "text"},
            {"key": "date",           "label": "Date",          "type": "text"},
            {"key": "start_time",     "label": "Start Time",    "type": "text"},
            {"key": "end_time",       "label": "End Time",      "type": "text"},
            {"key": "venue",          "label": "Venue",         "type": "text"},
            {"key": "total_students", "label": "Students",      "type": "number"},
            {"key": "present",        "label": "Present",       "type": "number"},
            {"key": "absent",         "label": "Absent",        "type": "number"},
            {"key": "attendance_pct", "label": "Attendance %",  "type": "percent"},
            {"key": "status",         "label": "Status",        "type": "badge"},
        ],
        "rows": rows,
        "count": len(rows),
    }


@frappe.whitelist()
def drilldown_pending_attendance():
    """Drill-down: all unmarked (pending) attendance sessions."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)
    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    co_names = _get_faculty_co_names(faculty_name)
    today = frappe.utils.today()

    if not co_names:
        return {"title": "Pending Attendance", "columns": [], "rows": [], "count": 0}

    raw = frappe.get_all(
        "Attendance Session",
        filters={
            "course_offering": ["in", co_names],
            "attendance_marked": 0,
            "session_date": ["<=", today],
            "session_status": "Scheduled",
        },
        fields=["name", "course_offering", "session_date",
                "session_start_time", "session_end_time",
                "room", "total_students"],
        order_by="session_date asc",
        ignore_permissions=True,
    )

    co_map = {co: frappe.db.get_value("Course Offering", co, "course_name") or co
              for co in co_names}

    from slcm.utils.faculty_portal import fmt_time

    rows = []
    for s in raw:
        date_obj = frappe.utils.getdate(s.session_date)
        today_obj = frappe.utils.getdate(today)
        days_overdue = (today_obj - date_obj).days
        rows.append({
            "session": s.name,
            "course_name": co_map.get(s.course_offering, s.course_offering),
            "date": frappe.utils.formatdate(s.session_date, "dd MMM yyyy"),
            "start_time": fmt_time(s.session_start_time),
            "venue": s.room or "—",
            "total_students": s.total_students or 0,
            "days_overdue": days_overdue,
            "action_link": f"/faculty-portal/attendance?session={s.name}",
        })

    return {
        "title": "Pending Attendance Sessions",
        "columns": [
            {"key": "course_name",    "label": "Course",          "type": "text"},
            {"key": "date",           "label": "Session Date",    "type": "text"},
            {"key": "start_time",     "label": "Time",            "type": "text"},
            {"key": "venue",          "label": "Venue",           "type": "text"},
            {"key": "total_students", "label": "Students",        "type": "number"},
            {"key": "days_overdue",   "label": "Days Overdue",    "type": "overdue"},
        ],
        "rows": rows,
        "count": len(rows),
    }


@frappe.whitelist()
def drilldown_venue_bookings():
    """Drill-down: pending venue bookings by this faculty."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)
    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    faculty_doc = frappe.db.get_value(
        "Faculty", faculty_name, ["first_name", "last_name", "email"], as_dict=True
    ) or frappe._dict()
    display_name = " ".join(filter(None, [faculty_doc.first_name, faculty_doc.last_name]))
    email = faculty_doc.email or ""

    name_filters = list(filter(None, [faculty_name, display_name, email]))

    try:
        raw = frappe.get_all(
            "Venue Booking",
            filters={"requester_name": ["in", name_filters], "status": "Pending Allotment"},
            fields=["name", "event_name", "venue_type", "venue as room",
                    "start_datetime", "end_datetime", "expected_attendees",
                    "status", "creation"],
            order_by="start_datetime asc",
            ignore_permissions=True,
        )
    except Exception:
        raw = []

    rows = []
    for b in raw:
        rows.append({
            "booking_id": b.name,
            "event_name": b.event_name or "—",
            "venue_type": b.venue_type or "—",
            "room": b.room or "—",
            "start": frappe.utils.format_datetime(b.start_datetime, "dd MMM yyyy HH:mm") if b.start_datetime else "—",
            "end": frappe.utils.format_datetime(b.end_datetime, "dd MMM yyyy HH:mm") if b.end_datetime else "—",
            "attendees": b.expected_attendees or 0,
            "status": b.status or "Pending Allotment",
        })

    return {
        "title": "Pending Venue Bookings",
        "columns": [
            {"key": "booking_id",  "label": "Booking ID",   "type": "text"},
            {"key": "event_name",  "label": "Event",        "type": "text"},
            {"key": "venue_type",  "label": "Venue Type",   "type": "text"},
            {"key": "room",        "label": "Room",         "type": "text"},
            {"key": "start",       "label": "Start",        "type": "text"},
            {"key": "end",         "label": "End",          "type": "text"},
            {"key": "attendees",   "label": "Attendees",    "type": "number"},
            {"key": "status",      "label": "Status",       "type": "badge"},
        ],
        "rows": rows,
        "count": len(rows),
    }


@frappe.whitelist()
def drilldown_condonation():
    """Drill-down: pending condonation requests for this faculty's courses."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)
    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    co_names = _get_faculty_co_names(faculty_name)
    if not co_names:
        return {"title": "Condonation Requests", "columns": [], "rows": [], "count": 0}

    try:
        raw = frappe.get_all(
            "Student Attendance Condonation",
            filters={
                "course_offering": ["in", co_names],
                "final_status": "Pending",
                "faculty_recommendation": ["in", ["", None, "Pending"]],
            },
            fields=["name", "student", "course_offering",
                    "reason", "faculty_recommendation", "final_status", "creation"],
            order_by="creation desc",
            ignore_permissions=True,
        )
    except Exception:
        raw = []

    co_map = {co: frappe.db.get_value("Course Offering", co, "course_name") or co
              for co in co_names}

    rows = []
    for r in raw:
        student_name = frappe.db.get_value(
            "Student Master", r.student,
            "concat(first_name, ' ', last_name)"
        ) or r.student

        rows.append({
            "request_id": r.name,
            "student": r.student,
            "student_name": student_name,
            "course_name": co_map.get(r.course_offering, r.course_offering),
            "reason": (r.reason or "—")[:80],
            "faculty_recommendation": r.faculty_recommendation or "Pending",
            "status": r.final_status or "Pending",
            "submitted": frappe.utils.formatdate(r.creation, "dd MMM yyyy"),
        })

    return {
        "title": "Condonation Requests",
        "columns": [
            {"key": "request_id",            "label": "Request ID",          "type": "text"},
            {"key": "student_name",          "label": "Student",             "type": "text"},
            {"key": "course_name",           "label": "Course",              "type": "text"},
            {"key": "reason",                "label": "Reason",              "type": "text"},
            {"key": "faculty_recommendation","label": "Your Recommendation", "type": "badge"},
            {"key": "status",                "label": "Final Status",        "type": "badge"},
            {"key": "submitted",             "label": "Submitted",           "type": "text"},
        ],
        "rows": rows,
        "count": len(rows),
    }


@frappe.whitelist()
def drilldown_student_groups():
    """Drill-down: course-wise student group summary."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)
    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    co_names = _get_faculty_co_names(faculty_name)
    if not co_names:
        return {"title": "Course Offerings", "columns": [], "rows": [], "count": 0}

    offerings = frappe.get_all(
        "Course Offering",
        filters={"name": ["in", co_names]},
        fields=["name", "course_name", "term_name", "academic_year"],
        ignore_permissions=True,
    )

    rows = []
    for co in offerings:
        try:
            enr = frappe.db.sql(
                """SELECT COUNT(DISTINCT se.student) AS cnt
                   FROM `tabStudent Enrollment Course` sec
                   JOIN `tabStudent Enrollment` se ON se.name = sec.parent
                   WHERE sec.course_offering = %s AND sec.status = 'Enrolled'""",
                co.name, as_dict=True,
            )
            students = (enr[0].cnt or 0) if enr else 0
        except Exception:
            students = 0

        if students > 0:
            try:
                att = frappe.db.sql(
                    """SELECT AVG(attendance_percentage) AS avg_pct
                       FROM `tabAttendance Session`
                       WHERE course_offering = %s AND attendance_marked = 1""",
                    co.name, as_dict=True,
                )
                avg_pct = round(float((att[0].avg_pct or 0) if att else 0), 1)
            except Exception:
                avg_pct = 0.0

            rows.append({
                "course_offering": co.name,
                "course_name": co.course_name or co.name,
                "term": co.term_name or "—",
                "academic_year": co.academic_year or "—",
                "student_count": students,
                "avg_attendance": avg_pct,
            })

    rows.sort(key=lambda x: x["student_count"], reverse=True)

    return {
        "title": "Course Offerings",
        "columns": [
            {"key": "course_name",    "label": "Course",           "type": "text"},
            {"key": "term",           "label": "Term",             "type": "text"},
            {"key": "academic_year",  "label": "Academic Year",    "type": "text"},
            {"key": "student_count",  "label": "Students",         "type": "number"},
            {"key": "avg_attendance", "label": "Avg Attendance %", "type": "percent"},
        ],
        "rows": rows,
        "count": len(rows),
    }


# ── Dashboard calendar ────────────────────────────────────────────────

_CAL_MAX_DAYS = 100
_HOLIDAY_ENTRY_TYPES = ("Holiday", "Weekly Off")


def _hhmm(t):
    """Time/timedelta/str → 'HH:MM' (24h), or '' when empty."""
    if not t:
        return ""
    if hasattr(t, "seconds"):
        h, rem = divmod(int(t.total_seconds()) % 86400, 3600)
        return f"{h:02d}:{rem // 60:02d}"
    parts = str(t).split(":")
    return f"{int(parts[0]):02d}:{int(parts[1]) if len(parts) > 1 else 0:02d}"


def _cal_events(start, end, timetable_event_names):
    """Frappe Events visible to the session user (public, owned or shared),
    with repeating events expanded. Events that only mirror a Time Table
    entry for Google sync are skipped — the class shows in the Time Table layer."""
    from frappe.desk.doctype.event.event import get_events

    items = []
    for ev in get_events(start, end) or []:
        # The description marker also catches mirrors whose Time Table lost its link
        if ev.name in timetable_event_names or (ev.description or "").startswith("Synced from Time Table:"):
            continue
        starts_on = frappe.utils.get_datetime(ev.starts_on)
        ends_on = frappe.utils.get_datetime(ev.ends_on) if ev.ends_on else starts_on
        all_day = bool(ev.all_day)
        items.append({
            "id": f"event::{ev.name}::{starts_on.date()}",
            "layer": "event",
            "title": ev.subject or "Event",
            "start_date": str(starts_on.date()),
            "end_date": str(max(ends_on, starts_on).date()),
            "start_time": "" if all_day else starts_on.strftime("%H:%M"),
            "end_time": "" if all_day else ends_on.strftime("%H:%M"),
            "all_day": all_day,
            "subtitle": ev.event_type or "",
            "description": frappe.utils.strip_html(ev.description or "")[:300],
        })
    return items


def _cal_institutional(start, end):
    rows = frappe.get_all(
        "Institutional Calendar",
        filters=[["start_date", "<=", end]],
        fields=["name", "name1", "entry_type", "status", "start_date", "end_date",
                "academic_year", "description"],
        order_by="start_date asc",
        ignore_permissions=True,
    )
    rows = [r for r in rows
            if r.status != "Inactive" and frappe.utils.getdate(r.end_date or r.start_date) >= start]
    off_days = {}
    weekly_off = [r.name for r in rows if r.entry_type == "Weekly Off"]
    if weekly_off:
        for d in frappe.get_all(
            "Institutional Calendar Weekly Off Day",
            filters={"parent": ["in", weekly_off], "parenttype": "Institutional Calendar"},
            fields=["parent", "day"],
            ignore_permissions=True,
        ):
            off_days.setdefault(d.parent, set()).add(d.day)

    items = []
    for r in rows:
        r_start = frappe.utils.getdate(r.start_date)
        r_end = frappe.utils.getdate(r.end_date or r.start_date)
        base = {
            "layer": "institutional",
            "title": r.name1 or r.name,
            "start_time": "",
            "end_time": "",
            "all_day": True,
            "subtitle": " · ".join(filter(None, [r.entry_type, r.academic_year])),
            "entry_type": r.entry_type or "",
            "is_holiday": r.entry_type in _HOLIDAY_ENTRY_TYPES,
            "description": frappe.utils.strip_html(r.description or "")[:300],
        }
        if r.entry_type == "Weekly Off" and off_days.get(r.name):
            # One entry per matching weekday inside the visible window
            day = max(r_start, start)
            while day <= min(r_end, end):
                if day.strftime("%A") in off_days[r.name]:
                    items.append({**base, "id": f"inst::{r.name}::{day}",
                                  "start_date": str(day), "end_date": str(day)})
                day = frappe.utils.add_days(day, 1)
        else:
            items.append({**base, "id": f"inst::{r.name}",
                          "start_date": str(r_start), "end_date": str(max(r_end, r_start))})
    return items


def _cal_timetable(faculty_name, start, end, today):
    base_filters = [["schedule_date", "between", [start, end]], ["docstatus", "<", 2]]
    fields = ["name", "title", "course", "course_offering", "section", "based_on",
              "schedule_date", "from_time", "to_time", "venue", "linked_google_event"]

    rows = {r.name: r for r in frappe.get_all(
        "Time Table", filters=base_filters + [["instructor", "=", faculty_name]],
        fields=fields, limit_page_length=0, ignore_permissions=True,
    )}
    co_names = frappe.get_all(
        "Course Offering", filters={"faculty": faculty_name}, pluck="name", ignore_permissions=True
    )
    if co_names:
        for r in frappe.get_all(
            "Time Table", filters=base_filters + [["course_offering", "in", co_names]],
            fields=fields, limit_page_length=0, ignore_permissions=True,
        ):
            rows.setdefault(r.name, r)
    if not rows:
        return [], set()

    co_titles = {}
    offering_names = list({r.course_offering for r in rows.values() if r.course_offering})
    if offering_names:
        co_titles = dict(frappe.get_all(
            "Course Offering", filters={"name": ["in", offering_names]},
            fields=["name", "course_name"], as_list=True, ignore_permissions=True,
        ))

    sessions = {}
    for s in frappe.get_all(
        "Attendance Session",
        filters={"class_schedule": ["in", list(rows)]},
        fields=["name", "class_schedule", "attendance_marked", "session_status", "session_type"],
        ignore_permissions=True,
    ):
        sessions[s.class_schedule] = s

    items = []
    for r in rows.values():
        sess = sessions.get(r.name)
        date = frappe.utils.getdate(r.schedule_date)
        # Same status rules as the attendance page's sessions list
        if sess and sess.session_status == "Cancelled":
            status = "Cancelled"
        elif sess and sess.attendance_marked:
            status = "Marked"
        elif date > today:
            status = "Upcoming"
        elif date == today:
            status = "Active"
        else:
            status = "Pending"
        is_oh = (sess.session_type == "Office Hour") if sess else r.based_on == "Office Hours"
        items.append({
            "id": f"tt::{r.name}",
            "layer": "timetable",
            "title": co_titles.get(r.course_offering) or r.title or r.course or "Class",
            "start_date": str(date),
            "end_date": str(date),
            "start_time": _hhmm(r.from_time),
            "end_time": _hhmm(r.to_time),
            "all_day": not r.from_time,
            "subtitle": " · ".join(filter(None, ["OH" if is_oh else "Class", r.section])),
            "venue": r.venue or "",
            "status": status,
            # Opens this session in the attendance page's Student Attendance Tool
            "session": sess.name if sess else "",
            "kind": "oh" if is_oh else "class",
        })
    linked_events = {r.linked_google_event for r in rows.values() if r.linked_google_event}
    return items, linked_events


@frappe.whitelist()
def get_faculty_calendar(start, end):
    """Calendar items for the dashboard between `start` and `end` (inclusive):
    Events, Institutional Calendar entries and the faculty's Time Table classes."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)
    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    start, end = frappe.utils.getdate(start), frappe.utils.getdate(end)
    if end < start:
        start, end = end, start
    if frappe.utils.date_diff(end, start) > _CAL_MAX_DAYS:
        end = frappe.utils.getdate(frappe.utils.add_days(start, _CAL_MAX_DAYS))

    today = frappe.utils.getdate()
    items, errors = [], []

    linked_events = set()
    try:
        tt_items, linked_events = _cal_timetable(faculty_name, start, end, today)
        items += tt_items
    except Exception:
        errors.append("timetable")
        frappe.log_error(frappe.get_traceback(), "Faculty Calendar – Time Table")
    try:
        items += _cal_institutional(start, end)
    except Exception:
        errors.append("institutional")
        frappe.log_error(frappe.get_traceback(), "Faculty Calendar – Institutional Calendar")
    try:
        items += _cal_events(start, end, linked_events)
    except Exception:
        errors.append("event")
        frappe.log_error(frappe.get_traceback(), "Faculty Calendar – Event")

    items.sort(key=lambda i: (i["start_date"], not i["all_day"], i["start_time"]))
    return {"start": str(start), "end": str(end), "today": str(today), "items": items, "errors": errors}


@frappe.whitelist()
def drilldown_weekly_hours():
    """Drill-down: this week's teaching sessions with duration."""
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)
    faculty_name = get_faculty_name()
    if not faculty_name:
        frappe.throw("No faculty record found", frappe.DoesNotExistError)

    co_names = _get_faculty_co_names(faculty_name)
    today = frappe.utils.today()
    week_start = frappe.utils.get_first_day_of_week(today)

    if not co_names:
        return {"title": "This Week's Teaching Hours", "columns": [], "rows": [], "count": 0}

    raw = frappe.get_all(
        "Attendance Session",
        filters=[
            ["course_offering", "in", co_names],
            ["session_date", ">=", week_start],
            ["session_date", "<=", today],
        ],
        fields=["name", "course_offering", "session_date",
                "session_start_time", "session_end_time",
                "room", "total_students", "present_count", "attendance_percentage"],
        order_by="session_date asc, session_start_time asc",
        ignore_permissions=True,
    )

    co_map = {co: frappe.db.get_value("Course Offering", co, "course_name") or co
              for co in co_names}

    from slcm.utils.faculty_portal import fmt_time

    rows = []
    for s in raw:
        duration_hrs = 0.0
        if s.session_start_time and s.session_end_time:
            secs = frappe.utils.time_diff_in_seconds(s.session_end_time, s.session_start_time)
            if secs > 0:
                duration_hrs = round(secs / 3600, 2)
        rows.append({
            "course_name": co_map.get(s.course_offering, s.course_offering),
            "date": frappe.utils.formatdate(s.session_date, "dd MMM yyyy"),
            "start_time": fmt_time(s.session_start_time),
            "end_time": fmt_time(s.session_end_time),
            "duration_hrs": duration_hrs,
            "venue": s.room or "—",
            "students": s.total_students or 0,
            "present": s.present_count or 0,
            "attendance_pct": round(float(s.attendance_percentage or 0), 1),
        })

    return {
        "title": "This Week's Teaching Sessions",
        "columns": [
            {"key": "course_name",    "label": "Course",       "type": "text"},
            {"key": "date",           "label": "Date",         "type": "text"},
            {"key": "start_time",     "label": "Start",        "type": "text"},
            {"key": "end_time",       "label": "End",          "type": "text"},
            {"key": "duration_hrs",   "label": "Duration (h)", "type": "number"},
            {"key": "venue",          "label": "Venue",        "type": "text"},
            {"key": "students",       "label": "Students",     "type": "number"},
            {"key": "present",        "label": "Present",      "type": "number"},
            {"key": "attendance_pct", "label": "Att. %",       "type": "percent"},
        ],
        "rows": rows,
        "count": len(rows),
    }

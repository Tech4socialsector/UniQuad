# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""
Background Processor: RFID Attendance Logs → Student Attendance
===============================================================
Converts raw RFID swipes (Attendance Log) into Student Attendance records
and then triggers the Attendance Summary recalculation.

Flow per student per day
------------------------
1. Fetch Attendance Sessions for the student on that date.
   If a Time Table entry exists but no Attendance Session was created yet,
   auto-create the session so RFID can still work without manual setup.
2. Match each swipe to a session window (±20 min buffer).
3. Apply RFID mode (In Only / In and Out) to determine Present/Absent.
4. Create or update Student Attendance — NEVER silently drops a swipe.
5. Mark Attendance Log rows as processed.
6. Attendance calculator fires automatically via Student Attendance on_update.

Business Rules
--------------
- First swipe within window → Present (In Only mode)
- Two swipes + ≥50 % duration covered → Present (In and Out mode)
- Single swipe + session ended > 30 min ago → Absent (In and Out mode)
- Duplicate swipes within 10 min → debounced / ignored
"""

import frappe
from frappe import _
from frappe.utils import (
    getdate,
    now_datetime,
    get_datetime,
    time_diff_in_hours,
    add_to_date,
    flt,
)
from collections import defaultdict
from slcm.slcm.doctype.rfid_device_room_mapping.rfid_device_room_mapping import (
    get_active_rooms_for_device,
)
from slcm.slcm.doctype.academic_term.academic_term import get_current_term


# ---------------------------------------------------------------------------
# Student Enrollment context — denormalized onto Attendance Log so the
# Attendance Sync UI can filter by Programme/AY/Term/Batch/Section without a
# join at query time.
# ---------------------------------------------------------------------------

def get_student_enrollment_context(student):
    """Return {programme, academic_year, academic_term, batch, section} from
    the student's active Student Enrollment, or {} if none / no student."""
    if not student:
        return {}

    enrollment = frappe.get_all(
        "Student Enrollment",
        filters={"student": student, "status": "Enrolled"},
        fields=["program", "academic_year", "batch", "section"],
        order_by="enrollment_date desc",
        limit=1,
    )
    if not enrollment:
        return {}

    e = enrollment[0]
    return {
        "programme": e.get("program"),
        "academic_year": e.get("academic_year"),
        "batch": e.get("batch"),
        "section": e.get("section"),
        "academic_term": get_current_term(),
    }


@frappe.whitelist()
def academic_year_link_query(doctype, txt, searchfield, start, page_len, filters):
    """Link-field query for Academic Year, scoped (when a Programme is
    selected) to years that actually have a Course Offering under it —
    mirrors examination_result.trimester_link_query's use of Course Offering
    as the Programme <-> Academic Year/Term bridge table."""
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    programme = filters.get("programme")
    params = {"txt": f"%{txt}%", "start": int(start or 0), "page_len": int(page_len or 20)}

    if programme:
        params["programme"] = programme
        return frappe.db.sql(
            """
            SELECT DISTINCT ay.name
            FROM `tabAcademic Year` ay
            JOIN `tabCourse Offering` co ON co.academic_year = ay.name
            WHERE co.program = %(programme)s AND ay.name LIKE %(txt)s
            ORDER BY ay.name ASC
            LIMIT %(start)s, %(page_len)s
            """,
            params,
        )

    return frappe.db.sql(
        """
        SELECT name FROM `tabAcademic Year`
        WHERE name LIKE %(txt)s
        ORDER BY name ASC
        LIMIT %(start)s, %(page_len)s
        """,
        params,
    )


@frappe.whitelist()
def academic_term_link_query(doctype, txt, searchfield, start, page_len, filters):
    """Link-field query for Academic Term, scoped by the selected Programme
    and/or Academic Year via Course Offering (co.term_name == Academic Term.name)."""
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    programme = filters.get("programme")
    academic_year = filters.get("academic_year")
    params = {"txt": f"%{txt}%", "start": int(start or 0), "page_len": int(page_len or 20)}

    conditions = ["at.name LIKE %(txt)s"]
    join = ""
    if programme or academic_year:
        join = "JOIN `tabCourse Offering` co ON co.term_name = at.name"
        if programme:
            params["programme"] = programme
            conditions.append("co.program = %(programme)s")
        if academic_year:
            params["academic_year"] = academic_year
            conditions.append("co.academic_year = %(academic_year)s")

    return frappe.db.sql(
        f"""
        SELECT DISTINCT at.name
        FROM `tabAcademic Term` at
        {join}
        WHERE {" AND ".join(conditions)}
        ORDER BY at.name ASC
        LIMIT %(start)s, %(page_len)s
        """,
        params,
    )


# ---------------------------------------------------------------------------
# Scheduled entry point  (*/10 * * * *)
# ---------------------------------------------------------------------------

def process_pending_logs():
    """Main scheduled entry point — processes all unprocessed Attendance Logs."""
    try:
        if not frappe.db.get_single_value("Attendance Settings", "enable_rfid"):
            return

        _tag_unmatched_unknown_cards()

        logs = _get_unprocessed_logs()
        if not logs:
            frappe.logger().info("RFID Processor: no pending logs")
            return

        grouped = _group_by_student_date(logs)

        processed_count = 0
        for key, student_logs in grouped.items():
            try:
                _process_student_day(student_logs)
                processed_count += len(student_logs)
            except Exception:
                frappe.log_error(
                    title=f"RFID Processor — error for {key}",
                    message=frappe.get_traceback(),
                )

        frappe.db.commit()
        frappe.logger().info(f"RFID Processor: processed {processed_count} log(s)")

    except Exception:
        frappe.log_error(
            title="RFID Processor — unhandled error",
            message=frappe.get_traceback(),
        )


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _get_unprocessed_logs():
    return frappe.get_all(
        "Attendance Log",
        filters={"processed": 0, "student": ["!=", ""]},
        fields=["name", "student", "swipe_time", "device_id", "location", "rfid_uid", "match_status"],
        order_by="swipe_time asc",
    )


def _tag_unmatched_unknown_cards():
    """Logs with no student link (unregistered card, or ingested via a path
    that doesn't resolve student e.g. RFID SQL Punch Log) can never be
    auto-matched — surface them for manual sync instead of leaving them
    silently pending forever."""
    frappe.db.sql("""
        UPDATE `tabAttendance Log`
        SET match_status = 'Unmatched - Unknown Card'
        WHERE processed = 0
        AND (student IS NULL OR student = '')
        AND match_status != 'Unmatched - Unknown Card'
    """)


def _group_by_student_date(logs):
    grouped = defaultdict(list)
    for log in logs:
        key = (log.get("student"), getdate(log.get("swipe_time")))
        grouped[key].append(log)
    return grouped


# ---------------------------------------------------------------------------
# Core: process one student on one day
# ---------------------------------------------------------------------------

def _process_student_day(logs):
    if not logs:
        return

    student   = logs[0].get("student")
    log_date  = getdate(logs[0].get("swipe_time"))
    rfid_mode = frappe.db.get_single_value("Attendance Settings", "rfid_swipe_mode") or "In Only"

    # Sort chronologically
    logs = sorted(logs, key=lambda x: x.get("swipe_time"))

    # Resolve matching sessions (creates missing ones from Time Table automatically)
    sessions = _get_or_create_sessions(student, log_date)

    if not sessions:
        reason = _diagnose_unmatched_reason(logs, log_date)
        frappe.logger().info(
            f"RFID Processor: no sessions for {student} on {log_date} — logs left unprocessed ({reason})"
        )
        for log in logs:
            if log.get("match_status") != reason:
                frappe.db.set_value("Attendance Log", log.name, "match_status", reason)
        return

    processed_names = set()
    matched_any_names = set()

    for session in sessions:
        matched = _match_swipes_to_session(logs, session)
        if not matched:
            continue

        for log in matched:
            matched_any_names.add(log.name)

        status = _determine_status(matched, session, rfid_mode)
        if not status:
            # Session still in progress — leave logs for next run
            continue

        if session.get("session_type") == "Office Hour":
            _upsert_office_hour_attendance(student, session, matched)
        else:
            _upsert_class_attendance(student, session, status, matched)

        for log in matched:
            processed_names.add(log.name)

    for log in logs:
        if log.name in processed_names:
            frappe.db.set_value("Attendance Log", log.name, {
                "processed": 1,
                "match_status": "Matched",
                "sync_method": "Biometric",
            })
        elif log.name not in matched_any_names:
            reason = "Unmatched - No Session"
            if _is_awaiting_activation(log, sessions):
                reason = "Early Tap - Awaiting Activation"
            if log.get("match_status") != reason:
                frappe.db.set_value("Attendance Log", log.name, "match_status", reason)


def _is_awaiting_activation(log, sessions):
    """True if this swipe falls inside a Class session's raw time window
    (±20 min) but that session hasn't been RFID-activated by faculty yet —
    i.e. the swipe is legitimate, just waiting on the Faculty Portal button."""
    swipe_time = get_datetime(log.get("swipe_time"))
    for session in sessions:
        if session.get("type") == "Office Hour":
            continue
        if session.get("rfid_activation_time") and session.get("rfid_active_until"):
            continue  # already activated — handled by the normal match path
        session_date = session.get("session_date") or getdate()
        start = add_to_date(get_datetime(f"{session_date} {session['session_start_time']}"), minutes=-20)
        end = add_to_date(get_datetime(f"{session_date} {session['session_end_time']}"), minutes=20)
        if start <= swipe_time <= end:
            return True
    return False


def _diagnose_unmatched_reason(logs, log_date):
    """Best-effort reason why no session could be resolved at all, so staff
    reviewing the Attendance Sync UI know whether to fix a device mapping
    or a missing Time Table entry."""
    for log in logs:
        device_id = log.get("device_id")
        if not device_id:
            continue
        if not frappe.db.exists("RFID Device", device_id):
            return "Unmatched - No Device Mapping"
        rooms = get_active_rooms_for_device(device_id, on_date=log_date)
        if not rooms:
            return "Unmatched - No Device Mapping"
    return "Unmatched - No Session"


# ---------------------------------------------------------------------------
# Session resolution — the key improvement
# ---------------------------------------------------------------------------

def _get_or_create_sessions(student, date):
    """
    Return Attendance Sessions the student should attend on *date*.
    If a Time Table entry exists but no Attendance Session has been created,
    auto-create the session so RFID never silently fails.
    """
    sessions = []

    # 1. Existing Attendance Sessions
    existing = frappe.get_all(
        "Attendance Session",
        filters={"session_date": date, "session_status": ["!=", "Cancelled"], "docstatus": ["<", 2]},
        fields=["name", "session_date", "session_start_time", "session_end_time",
                "course_schedule", "class_schedule", "course_offering",
                "session_type", "duration_hours",
                "rfid_activated_by", "rfid_activation_time", "rfid_active_until"],
    )

    for s in existing:
        if _is_student_in_session(student, s):
            s["type"] = "Office Hour" if s.get("session_type") == "Office Hour" else "Class"
            sessions.append(s)

    # 2. Time Table entries that have NO Attendance Session yet → auto-create
    class_schedules = frappe.get_all(
        "Time Table",
        filters={
            "schedule_date": date,
            "status": ["!=", "Cancelled"],
            "docstatus": ["<", 2],
        },
        fields=["name", "course", "course_offering", "from_time", "to_time",
                "duration_hours", "instructor", "venue"],
    )

    existing_from_schedule = {s.get("class_schedule") for s in existing if s.get("class_schedule")}

    for cs in class_schedules:
        if cs.name in existing_from_schedule:
            continue  # session already exists

        # Check student is enrolled in this course offering
        if not _is_student_in_course_offering(student, cs.course_offering):
            continue

        # Auto-create the Attendance Session
        new_session = _auto_create_session_from_schedule(cs, date)
        if new_session:
            new_session["type"] = "Class"
            sessions.append(new_session)

    # 3. Office Hours Sessions
    oh_sessions = frappe.get_all(
        "Office Hours Session",
        filters={"session_date": date, "session_status": ["!=", "Cancelled"]},
        fields=["name", "session_date",
                "start_time as session_start_time",
                "end_time as session_end_time",
                "course_offering"],
    )
    for s in oh_sessions:
        if _is_student_in_course_offering(student, s.get("course_offering")):
            s["session_type"] = "Office Hour"
            s["type"] = "Office Hour"
            sessions.append(s)

    return sessions


def _auto_create_session_from_schedule(cs, date):
    """Create an Attendance Session from a Time Table record."""
    try:
        from frappe.utils import time_diff_in_hours
        duration = flt(cs.get("duration_hours")) or (
            time_diff_in_hours(cs.get("to_time"), cs.get("from_time"))
            if cs.get("from_time") and cs.get("to_time")
            else 0
        )

        doc = frappe.get_doc({
            "doctype":           "Attendance Session",
            "based_on":          "Time Table",
            "class_schedule":    cs.name,
            "course_offering":   cs.course_offering,
            "session_date":      date,
            "session_type":      "Lecture",
            "session_start_time": cs.get("from_time"),
            "session_end_time":  cs.get("to_time"),
            "duration_hours":    duration,
            "session_status":    "Conducted",
            "instructor":        cs.get("instructor"),
        })
        doc.flags.skip_auto_attendance = True  # we don't pre-populate; RFID does it
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        return frappe._dict({
            "name":               doc.name,
            "session_date":       date,
            "session_start_time": doc.session_start_time,
            "session_end_time":   doc.session_end_time,
            "class_schedule":     cs.name,
            "course_offering":    cs.course_offering,
            "session_type":       "Lecture",
            "duration_hours":     duration,
        })

    except Exception:
        frappe.log_error(
            title=f"RFID Processor — failed to auto-create session for Time Table entry {cs.name}",
            message=frappe.get_traceback(),
        )
        return None


# ---------------------------------------------------------------------------
# Eligibility checks
# ---------------------------------------------------------------------------

def _is_student_in_session(student, session):
    """True if the student should attend this Attendance Session."""
    # Already has a Student Attendance record → definitely enrolled
    if frappe.db.exists("Student Attendance", {"student": student, "attendance_session": session.get("name")}):
        return True

    # Cohort enrollment
    return _is_student_in_course_offering(student, session.get("course_offering"))


def _is_student_in_course_offering(student, course_offering):
    """True if the student is actively enrolled in this Course Offering."""
    if not course_offering:
        return False
    if frappe.db.sql("""
        SELECT 1 FROM `tabStudent Enrollment Course` sec
        JOIN `tabStudent Enrollment` se ON se.name = sec.parent
        WHERE sec.course_offering = %s AND se.student = %s AND se.status = 'Enrolled'
        LIMIT 1
    """, (course_offering, student)):
        return True
    co = frappe.db.get_value(
        "Course Offering", course_offering, ["program", "academic_year", "year_no"], as_dict=True
    )
    if not co or not co.program:
        return False
    return bool(frappe.db.exists("Student Enrollment", {
        "student":       student,
        "program":       co.program,
        "academic_year": co.academic_year,
        "year_no":       co.year_no,
        "status":        "Enrolled",
    }))


# ---------------------------------------------------------------------------
# Swipe matching
# ---------------------------------------------------------------------------

def _match_swipes_to_session(logs, session):
    """Return logs whose swipe_time falls within the session's matchable window.

    Office Hours have no activation concept — keep the ±20 min session-time buffer.

    Class sessions require the faculty to have pressed 'Activate RFID' in the
    Faculty Portal: only swipes inside [rfid_activation_time, rfid_active_until]
    auto-match. Activation is no longer advisory — it is the gate. Swipes that
    arrive before activation (or after a Faculty never activates) are left
    pending as "Early Tap - Awaiting Activation" so the System Manager can
    review/bulk-sync them later, rather than being auto-marked Present.
    """
    if session.get("type") != "Office Hour" and session.get("rfid_activation_time") and session.get("rfid_active_until"):
        win_start = get_datetime(session["rfid_activation_time"])
        win_end = get_datetime(session["rfid_active_until"])
        return [lg for lg in logs if win_start <= get_datetime(lg.get("swipe_time")) <= win_end]

    if session.get("type") != "Office Hour":
        # Not yet activated by faculty — nothing auto-matches against this session.
        return []

    session_date = session.get("session_date") or getdate()
    start = get_datetime(f"{session_date} {session['session_start_time']}")
    end   = get_datetime(f"{session_date} {session['session_end_time']}")
    win_start = add_to_date(start, minutes=-20)
    win_end   = add_to_date(end,   minutes=20)

    return [lg for lg in logs if win_start <= get_datetime(lg.get("swipe_time")) <= win_end]


# ---------------------------------------------------------------------------
# Status determination
# ---------------------------------------------------------------------------

def _determine_status(matched_logs, session, mode):
    """Return 'Present', 'Absent', or None (still in progress)."""
    if not matched_logs:
        return None

    if mode == "In Only":
        return "Present"

    # In and Out — need swipe at both ends
    if len(matched_logs) >= 2:
        first = get_datetime(matched_logs[0].get("swipe_time"))
        last  = get_datetime(matched_logs[-1].get("swipe_time"))
        covered = time_diff_in_hours(last, first)

        s_start = get_datetime(f"{session.get('session_date')} {session['session_start_time']}")
        s_end   = get_datetime(f"{session.get('session_date')} {session['session_end_time']}")
        duration = time_diff_in_hours(s_end, s_start)

        if duration > 0 and covered >= (duration * 0.5):
            return "Present"

    # Single swipe or insufficient duration — wait unless session is over
    session_date = session.get("session_date") or getdate()
    cutoff = add_to_date(
        get_datetime(f"{session_date} {session['session_end_time']}"),
        minutes=30,
    )
    if now_datetime() > cutoff:
        return "Absent"

    return None  # Session still running — try again next cycle


# ---------------------------------------------------------------------------
# Upsert helpers — ALWAYS create, never silently drop
# ---------------------------------------------------------------------------

def _upsert_class_attendance(student, session, status, logs):
    """Create or update Student Attendance for a class/lecture session."""
    first_log = logs[0]
    last_log  = logs[-1]
    hours     = flt(session.get("duration_hours")) if status == "Present" else 0

    existing = frappe.db.exists("Student Attendance", {
        "student":            student,
        "attendance_session": session.get("name"),
    })

    if existing:
        doc = frappe.get_doc("Student Attendance", existing)
        doc.status        = status
        doc.source        = "RFID"
        doc.in_time       = first_log.get("swipe_time")
        doc.out_time      = last_log.get("swipe_time")
        doc.attendance_log = first_log.get("name")
        doc.hours_counted  = hours
        doc.session_type   = session.get("session_type") or "Lecture"
        doc.flags.ignore_attendance_lock = True  # system reconciliation, not a faculty edit
        doc.save(ignore_permissions=True)
    else:
        # Create a fresh record — this is the critical fix:
        # RFID attendance works even without a pre-created placeholder
        doc = frappe.get_doc({
            "doctype":            "Student Attendance",
            "student":            student,
            "attendance_session": session.get("name"),
            "course_offer":       session.get("course_offering"),
            "class_schedule":     session.get("class_schedule"),
            "course_schedule":    session.get("course_schedule"),
            "attendance_date":    getdate(first_log.get("swipe_time")),
            "date":               getdate(first_log.get("swipe_time")),
            "status":             status,
            "source":             "RFID",
            "in_time":            first_log.get("swipe_time"),
            "out_time":           last_log.get("swipe_time"),
            "attendance_log":     first_log.get("name"),
            "session_type":       session.get("session_type") or "Lecture",
            "hours_counted":      hours,
        })
        doc.flags.ignore_attendance_lock = True
        doc.insert(ignore_permissions=True)


def _upsert_office_hour_attendance(student, session, logs):
    """Create or update Student Attendance for an office hours session."""
    first_log = logs[0]
    last_log  = logs[-1]

    start = get_datetime(first_log.get("swipe_time"))
    end   = get_datetime(last_log.get("swipe_time"))
    duration = max(flt(time_diff_in_hours(end, start)), 0)

    existing = frappe.db.exists("Student Attendance", {
        "student":            student,
        "attendance_session": session.get("name"),
    })

    if existing:
        doc = frappe.get_doc("Student Attendance", existing)
        doc.status        = "Present"
        doc.source        = "RFID"
        doc.in_time       = first_log.get("swipe_time")
        doc.out_time      = last_log.get("swipe_time")
        doc.hours_counted  = duration
        doc.session_type   = "Office Hour"
        doc.flags.ignore_attendance_lock = True
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({
            "doctype":            "Student Attendance",
            "student":            student,
            "attendance_session": session.get("name"),
            "course_offer":       session.get("course_offering"),
            "attendance_date":    getdate(first_log.get("swipe_time")),
            "date":               getdate(first_log.get("swipe_time")),
            "status":             "Present",
            "source":             "RFID",
            "in_time":            first_log.get("swipe_time"),
            "out_time":           last_log.get("swipe_time"),
            "hours_counted":      duration,
            "session_type":       "Office Hour",
        })
        doc.flags.ignore_attendance_lock = True
        doc.insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Whitelisted manual trigger
# ---------------------------------------------------------------------------

@frappe.whitelist()
def process_logs_manually():
    """Admin/testing manual trigger. Also callable from bench console."""
    process_pending_logs()
    return {"status": "success", "message": "Attendance logs processed successfully"}


# ---------------------------------------------------------------------------
# Manual reconciliation — Attendance Sync UI
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_unmatched_logs(from_date=None, to_date=None, match_status=None, status_filter=None,
                        programme=None, academic_year=None, academic_term=None,
                        batch=None, section=None):
    """List Attendance Logs for the Attendance Sync UI.

    status_filter selects which slice of logs to show:
      - None/"" (default) — unresolved taps still needing review (processed=0).
      - "Biometric" / "Class Attendance" / "Bulk Sync" — already-resolved logs,
        filtered by how they were synced (Attendance Log.sync_method), so staff
        can audit past reconciliations, not just review pending ones.
    match_status ("Reason") only applies to the default unresolved view.
    """
    frappe.only_for(("System Manager", "slcm_Programme Chair"))

    if status_filter:
        filters = [
            ["Attendance Log", "processed", "=", 1],
            ["Attendance Log", "sync_method", "=", status_filter],
        ]
    else:
        filters = [["Attendance Log", "processed", "=", 0]]
        if match_status:
            filters.append(["Attendance Log", "match_status", "=", match_status])
        else:
            filters.append(["Attendance Log", "match_status", "!=", "Pending"])

    if from_date:
        filters.append(["Attendance Log", "swipe_time", ">=", from_date])
    if to_date:
        filters.append(["Attendance Log", "swipe_time", "<=", to_date])
    if programme:
        filters.append(["Attendance Log", "programme", "=", programme])
    if academic_year:
        filters.append(["Attendance Log", "academic_year", "=", academic_year])
    if academic_term:
        filters.append(["Attendance Log", "academic_term", "=", academic_term])
    if batch:
        filters.append(["Attendance Log", "batch", "=", batch])
    if section:
        filters.append(["Attendance Log", "section", "=", section])

    logs = frappe.get_all(
        "Attendance Log",
        filters=filters,
        fields=["name", "rfid_uid", "student", "swipe_time", "device_id",
                "terminal_alias", "location", "source", "match_status",
                "processed", "sync_method", "synced_by", "synced_on", "creation", "modified",
                "programme", "academic_year", "academic_term", "batch", "section"],
        order_by="swipe_time desc",
        limit=500,
    )

    for log in logs:
        log["student_name"] = None
        log["student_email"] = None
        if log.get("student"):
            student_info = frappe.db.get_value(
                "Student Master", log["student"], ["first_name", "email"], as_dict=True
            )
            if student_info:
                log["student_name"] = student_info.first_name
                log["student_email"] = student_info.email

        rooms = get_active_rooms_for_device(log.get("device_id"), on_date=getdate(log.get("swipe_time"))) \
            if log.get("device_id") else []
        log["resolved_rooms"] = rooms

        candidate_sessions = []
        if rooms:
            candidate_sessions = frappe.get_all(
                "Attendance Session",
                filters={
                    "room": ["in", rooms],
                    "session_date": getdate(log.get("swipe_time")),
                    "session_status": ["!=", "Cancelled"],
                },
                fields=["name", "course", "course_offering", "session_start_time", "session_end_time",
                        "instructor", "rfid_activated_by", "rfid_activation_time", "duration_hours"],
            )
            for session in candidate_sessions:
                session["course_code"] = frappe.db.get_value("Course", session.get("course"), "course_code") \
                    if session.get("course") else None
        log["candidate_sessions"] = candidate_sessions

    return logs


@frappe.whitelist()
def sync_attendance_log(log_name, session_name, student=None, synced_via="Class Attendance"):
    """Manually reconcile one Attendance Log against a staff-selected
    Attendance Session (used when auto-matching failed — missing device/room
    mapping, faculty forgot to activate, unknown card now identified, etc.).

    synced_via distinguishes how this reconciliation was triggered — the
    individual Sync dialog ("Class Attendance", the default) vs. the Bulk
    Sync action (passes "Bulk Sync") — purely for the Attendance Sync UI's
    Status column/filter."""
    frappe.only_for(("System Manager", "slcm_Programme Chair"))

    log_doc = frappe.get_doc("Attendance Log", log_name)
    if log_doc.processed:
        frappe.throw(_("This log has already been processed."))

    if student:
        log_doc.student = student
    if not log_doc.student:
        frappe.throw(_("Select a student before syncing this log — the card is not registered."))

    if student or not log_doc.programme:
        context = get_student_enrollment_context(log_doc.student)
        for fieldname, value in context.items():
            log_doc.set(fieldname, value)

    session = frappe.get_doc("Attendance Session", session_name)

    swipe_time = log_doc.swipe_time
    hours = flt(session.duration_hours) or 1.0

    existing = frappe.db.exists("Student Attendance", {
        "student": log_doc.student,
        "attendance_session": session.name,
    })

    if existing:
        att = frappe.get_doc("Student Attendance", existing)
        att.status = "Present"
        att.source = "RFID"
        att.in_time = swipe_time
        att.attendance_log = log_doc.name
        att.hours_counted = hours
        att.flags.ignore_attendance_lock = True  # staff reconciling RFID taps
        att.save(ignore_permissions=True)
    else:
        att = frappe.get_doc({
            "doctype": "Student Attendance",
            "student": log_doc.student,
            "attendance_session": session.name,
            "course_offer": session.course_offering,
            "course_schedule": session.course_schedule,
            "attendance_date": getdate(swipe_time),
            "date": getdate(swipe_time),
            "status": "Present",
            "source": "RFID",
            "in_time": swipe_time,
            "attendance_log": log_doc.name,
            "session_type": session.session_type or "Lecture",
            "hours_counted": hours,
        })
        att.flags.ignore_attendance_lock = True
        att.insert(ignore_permissions=True)

    log_doc.student_attendance = att.name
    log_doc.processed = 1
    log_doc.match_status = "Manually Synced"
    log_doc.sync_method = synced_via
    log_doc.synced_by = frappe.session.user
    log_doc.synced_on = now_datetime()
    log_doc.save(ignore_permissions=True)

    return {"student_attendance": att.name}


# ---------------------------------------------------------------------------
# Bulk sync — System Manager catch-up for a date range
# ---------------------------------------------------------------------------

@frappe.whitelist()
def bulk_sync_attendance_logs(from_date, to_date, from_time=None, to_time=None, venue=None):
    """Catch-up sync for unresolved Attendance Logs in a date range, for the
    two most common human misses that the scheduled processor can't fix on
    its own:

      1. Faculty forgot to press "Activate RFID" at all, but the student's
         swipe still falls within the first N minutes of the session
         (N = Attendance Settings.rfid_active_window_minutes) — treated as
         if it had been activated.
      2. The System Manager hadn't mapped the reader to a room yet at
         tap-time, but has since fixed the RFID Device Room Mapping — this
         re-evaluates every log fresh, so a mapping fix immediately makes
         past taps in that date range eligible.

    A log is auto-synced ONLY when it resolves to exactly one Attendance
    Session. Anything ambiguous, unregistered, unmapped, or tapped after the
    session ended is left untouched for individual review/Sync on the
    Attendance Sync page — this method never guesses.

    from_date/to_date are required: bulk actions must be scoped to an
    explicit window, never "all unresolved logs ever". from_time/to_time
    narrow that window to a time-of-day range within it; venue further
    restricts to taps on devices currently mapped to that Room.
    """
    frappe.only_for(("System Manager", "slcm_Programme Chair"))

    if not from_date or not to_date:
        frappe.throw(_("Select both a From Date and To Date before running Bulk Sync."))

    window_minutes = frappe.db.get_single_value("Attendance Settings", "rfid_active_window_minutes") or 10

    filters = {
        "processed": 0,
        "swipe_time": [
            "between",
            [f"{from_date} {from_time or '00:00:00'}", f"{to_date} {to_time or '23:59:59'}"],
        ],
    }
    if venue:
        device_ids = frappe.get_all(
            "RFID Device Room Mapping",
            filters={"room": venue, "is_active": 1},
            pluck="device",
        )
        filters["device_id"] = ["in", device_ids or [""]]

    logs = frappe.get_all(
        "Attendance Log",
        filters=filters,
        fields=["name", "student", "swipe_time", "device_id", "match_status"],
        order_by="swipe_time asc",
    )

    synced, skipped = [], []

    for log in logs:
        outcome = _try_bulk_sync_one(log, window_minutes)
        if outcome["synced"]:
            synced.append(outcome["log"])
        else:
            skipped.append({"log": log.name, "reason": outcome["reason"]})

    return {
        "status": "success",
        "from_date": str(from_date),
        "to_date": str(to_date),
        "total": len(logs),
        "synced_count": len(synced),
        "skipped_count": len(skipped),
        "synced": synced,
        "skipped": skipped,
    }


def _try_bulk_sync_one(log, window_minutes):
    """Evaluate + sync a single log for bulk_sync_attendance_logs. Never
    raises — any failure is reported back as a skip reason."""
    if not log.get("student"):
        return {"synced": False, "reason": "Unregistered card — identify the student manually"}

    if not log.get("device_id"):
        return {"synced": False, "reason": "No reader/device recorded on this log"}

    swipe_time = get_datetime(log.get("swipe_time"))
    log_date = getdate(swipe_time)

    rooms = get_active_rooms_for_device(log.get("device_id"), on_date=log_date)
    if not rooms:
        return {"synced": False, "reason": "Device not mapped to a room yet"}

    candidate_sessions = frappe.get_all(
        "Attendance Session",
        filters={
            "room": ["in", rooms],
            "session_date": log_date,
            "session_status": ["!=", "Cancelled"],
            "docstatus": ["<", 2],
        },
        fields=["name", "session_start_time", "session_end_time", "duration_hours"],
    )

    if not candidate_sessions:
        return {"synced": False, "reason": "No session found for this room/date"}
    if len(candidate_sessions) > 1:
        return {"synced": False, "reason": "Multiple candidate sessions — ambiguous, sync individually"}

    session = candidate_sessions[0]
    start = get_datetime(f"{log_date} {session['session_start_time']}")
    end = get_datetime(f"{log_date} {session['session_end_time']}")
    window_end = add_to_date(start, minutes=int(window_minutes))

    if swipe_time < start:
        return {"synced": False, "reason": "Tapped before the session start time"}
    if swipe_time > window_end:
        if swipe_time <= end:
            return {"synced": False, "reason": f"Tapped after the first {window_minutes}-minute window"}
        return {"synced": False, "reason": "Tapped after the session ended"}

    try:
        result = sync_attendance_log(log.name, session.name, student=log.get("student"), synced_via="Bulk Sync")
        return {"synced": True, "log": log.name, "student_attendance": result.get("student_attendance")}
    except Exception:
        frappe.log_error(
            title=f"Bulk Sync — failed to sync {log.name}",
            message=frappe.get_traceback(),
        )
        return {"synced": False, "reason": "Sync failed — see error log"}

import frappe
from slcm.slcm.utils.parent_portal import get_parent_context

no_cache = 1


def get_context(context):
    student = get_parent_context(context)
    if context.is_guest or context.not_a_parent or not student:
        _set_defaults(context)
        return context

    _set_defaults(context)
    context.active_page = "dashboard"

    ps = context.pp_settings or {}
    context.att_good = float(ps.get("att_good_threshold", 75))
    context.att_warn = float(ps.get("att_warn_threshold", 60))

    # Sections that failed to load — rendered as "Unable to load … [Retry]"
    # instead of an empty state, so a failure never looks like "no data".
    errors = {}

    # ── Attendance summary ─────────────────────────────────────────
    try:
        summaries = frappe.get_all(
            "Attendance Summary",
            filters={"student": student.name},
            fields=["course", "class_name", "academic_term as term_name",
                    "total_classes", "attended_classes",
                    "attendance_percentage", "eligible_for_exam"],
            order_by="academic_term desc, course asc",
            ignore_permissions=True,
        )
        for s in summaries:
            s["course_name"] = s.course
            if s.class_name:
                try:
                    cn = frappe.db.get_value("Classes", s.class_name, "course_name")
                    if cn:
                        s["course_name"] = cn
                except Exception:
                    pass
        context.attendance_summaries = summaries
        if summaries:
            percs = [s.attendance_percentage for s in summaries if s.attendance_percentage is not None]
            # Same formula as the Attendance page (mean of course percentages)
            context.avg_attendance   = round(sum(percs) / len(percs), 1) if percs else None
            context.courses_below_75 = sum(1 for p in percs if p < context.att_good)
            context.courses_eligible = sum(1 for s in summaries if s.eligible_for_exam)
            sessions = sum(frappe.utils.flt(s.total_classes) for s in summaries)
            present  = sum(frappe.utils.flt(s.attended_classes) for s in summaries)
            context.att_sessions = _num(sessions)
            context.att_present  = _num(present)
            context.att_absent   = _num(max(sessions - present, 0))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Parent Portal Dashboard: attendance")
        errors["attendance"] = True

    # ── Enrolled courses (Student Enrollment → Student Enrollment Course) ──
    enrolled_classes = []
    try:
        rows = frappe.db.sql(
            """
            SELECT DISTINCT sec.course, sec.class_name
            FROM   `tabStudent Enrollment Course` sec
            INNER JOIN `tabStudent Enrollment` se
                   ON se.name = sec.parent AND sec.parenttype = 'Student Enrollment'
            WHERE  se.student = %s AND se.status = 'Enrolled' AND se.docstatus < 2
            """,
            student.name,
            as_dict=True,
        )
        enrolled_classes = [r.class_name for r in rows if r.class_name]
        enrolled_courses = {r.course or r.class_name for r in rows}
        if enrolled_courses:
            context.course_count = len(enrolled_courses)
        elif not errors.get("attendance"):
            context.course_count = len(context.attendance_summaries)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Parent Portal Dashboard: enrolment")
        if not errors.get("attendance"):
            context.course_count = len(context.attendance_summaries)

    # ── Published results + latest grades ──────────────────────────
    try:
        pub_rows = frappe.get_all(
            "Student Result Publish",
            filters={"student": student.name, "is_published": 1},
            fields=["exam_plan", "published_on"],
            order_by="published_on desc",
            ignore_permissions=True,
        )
        context.results_published_count = len(pub_rows)
        if pub_rows:
            ep_name  = pub_rows[0].exam_plan
            ep_label = frappe.db.get_value("Exam Plan", ep_name, "exam_name") or ep_name
            context.latest_result = {
                "exam_name":    ep_label,
                "published_on": pub_rows[0].published_on,
            }
            marks = frappe.get_all(
                "Student Course Marks",
                filters={"student": student.name, "exam_plan": ep_name},
                fields=["course", "grade", "moderated_grade", "updated_grade"],
                ignore_permissions=True,
            )
            # One row per course; if a course has several marks rows, prefer a graded one
            by_course = {}
            for m in marks:
                # Same precedence as the Results page
                grade = m.updated_grade or m.moderated_grade or m.grade or ""
                if m.course not in by_course or (grade and not by_course[m.course]["grade"]):
                    by_course[m.course] = {
                        "course_name": frappe.db.get_value("Course", m.course, "course_name") or m.course,
                        "grade": grade,
                    }
            context.latest_grades = sorted(by_course.values(), key=lambda g: g["course_name"] or "")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Parent Portal Dashboard: results")
        errors["results"] = True

    # ── Fees summary ───────────────────────────────────────────────
    try:
        context.fee_summary = _fee_summary(student)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Parent Portal Dashboard: fees")
        errors["fees"] = True

    # ── Hostel details ─────────────────────────────────────────────
    try:
        context.is_hosteller = bool(student.is_hosteller)
        if context.is_hosteller:
            hostel_name = ""
            if student.hostel:
                hostel_name = frappe.db.get_value("Hostel", student.hostel, "hostel_name") or student.hostel
            room_number = ""
            if student.hostel_room:
                room_number = frappe.db.get_value("Hostel Room", student.hostel_room, "room_number") or student.hostel_room
            bed_no = ""
            if student.hostel_bed:
                bed_no = frappe.db.get_value("Hostel Bed", student.hostel_bed, "bed_no") or student.hostel_bed
            context.hostel_details = {
                "hostel_name":    hostel_name,
                "hostel_block":   student.hostel_block or "",
                "room_number":    room_number,
                "bed_no":         bed_no,
                "hostel_status":  student.hostel_status or "",
                "meal_plan":      student.meal_plan or "",
                "key_number":     student.key_number or "",
                "allocation_date": frappe.utils.formatdate(student.allocation_date, "dd MMM yyyy") if student.allocation_date else "",
            }
    except Exception:
        context.is_hosteller = False
        context.hostel_details = None

    # ── Academic profile ───────────────────────────────────────────
    context.ward_enrolment_no = getattr(student, "enrolment_number", "") or getattr(student, "student_id", "") or student.name
    context.ward_section      = getattr(student, "section", "") or ""
    context.ward_email        = getattr(student, "student_email_id", "") or ""

    # ── RFID In/Out — last 10 swipes ──────────────────────────────
    try:
        logs = frappe.get_all(
            "Attendance Log",
            filters={"student": student.name},
            fields=["swipe_time", "location", "terminal_alias", "source"],
            order_by="swipe_time desc",
            limit=10,
            ignore_permissions=True,
        )
        for lg in logs:
            if lg.swipe_time:
                lg["swipe_time_fmt"] = frappe.utils.format_datetime(lg.swipe_time, "dd MMM yyyy, hh:mm a")
                lg["swipe_date"]     = frappe.utils.formatdate(lg.swipe_time, "dd MMM yyyy")
                lg["swipe_clock"]    = frappe.utils.format_datetime(lg.swipe_time, "hh:mm a")
            else:
                lg["swipe_time_fmt"] = "—"
                lg["swipe_date"]     = "—"
                lg["swipe_clock"]    = "—"
        context.rfid_logs = logs
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Parent Portal Dashboard: rfid")
        errors["rfid"] = True

    # ── Time Table — today + next 7 days ──────────────────────
    try:
        today    = frappe.utils.today()
        end_date = frappe.utils.add_days(today, 7)

        # Classes this student is enrolled in or has attendance for
        from slcm.api.student_portal import _student_class_names

        active_classes = sorted(
            set(enrolled_classes)
            | set(_student_class_names(student.name))
            | {s.class_name for s in context.attendance_summaries if s.class_name}
        )

        schedules = []
        if active_classes:
            schedules = frappe.get_all(
                "Time Table",
                filters={
                    "schedule_date": ["between", [today, end_date]],
                    "class_name": ["in", active_classes],
                    "status": ["!=", "Cancelled"],
                },
                fields=["name", "course", "class_name", "instructor",
                        "schedule_date", "from_time", "to_time",
                        "venue", "duration_hours", "status"],
                order_by="schedule_date asc, from_time asc",
                limit=15,
                ignore_permissions=True,
            )

        for sc in schedules:
            # Course display name
            sc["course_name"] = sc.course or "—"
            if sc.class_name:
                try:
                    cn = frappe.db.get_value("Classes", sc.class_name, "course_name")
                    if cn:
                        sc["course_name"] = cn
                except Exception:
                    pass
            sd = sc.schedule_date
            if sd:
                sc["day_num"]  = frappe.utils.formatdate(sd, "dd")
                sc["month"]    = frappe.utils.formatdate(sd, "MMM").upper()
                sc["weekday"]  = frappe.utils.formatdate(sd, "EEE")
                sc["is_today"] = str(sd) == today
            else:
                sc["day_num"] = sc["month"] = sc["weekday"] = "—"
                sc["is_today"] = False
            sc["from_time_fmt"] = _fmt_time(sc.from_time)
            sc["to_time_fmt"]   = _fmt_time(sc.to_time)

        context.class_schedules = schedules
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Parent Portal Dashboard: timetable")
        errors["timetable"] = True

    context.load_errors = errors
    return context


def _fee_summary(sm):
    """
    Headline fee figures for the dashboard, taken from the parent Fees page's
    own context build (its "Overall" card and No Dues badge) instead of a
    separate calculation, so Total / Paid / Outstanding always match that page:
    programme fee invoices, Fee Demands, re-exam fees and hostel fines.
    Returns None when the student has no fee data at all; raises when the
    Fees page itself failed, so the dashboard shows its error state.
    """
    import importlib

    flt = frappe.utils.flt
    fees_page = importlib.import_module("slcm.www.parent-portal.fees")
    fctx = fees_page.get_context(frappe._dict())
    if fctx.get("portal_error"):
        raise frappe.ValidationError("Parent Fees page context failed")
    if fctx.get("is_guest") or fctx.get("not_a_parent") or fctx.get("ward_student_name") != sm.name:
        return None

    cards = fctx.get("charge_cards") or []
    if not cards:
        return None
    overall = cards[0]  # the "Overall" card
    total       = sum(flt(r.gross) for r in (fctx.get("charge_rows") or []) if r.get("group") != "Other")
    paid        = flt(overall.paid_amt)
    outstanding = flt(overall.outstanding)

    if not fctx.get("has_any_dues") and outstanding <= 0:
        status = "Paid"
    elif (overall.overdue or 0) > 0:
        status = "Overdue"
    elif paid > 0:
        status = "Partially Paid"
    else:
        status = "Pending"

    return {
        "total":       total,
        "paid":        paid,
        "outstanding": outstanding,
        "status":      status,
        "fmt_total":       overall.total_fmt,
        "fmt_paid":        overall.paid_fmt,
        "fmt_outstanding": overall.outstanding_fmt,
    }


def _num(v):
    """Render whole-number floats (e.g. class counts) without a trailing .0"""
    v = frappe.utils.flt(v)
    return int(v) if v == int(v) else round(v, 1)


def _fmt_time(t):
    if not t:
        return ""
    try:
        from datetime import time as dtime
        if isinstance(t, dtime):
            h, m = t.hour, t.minute
        else:
            parts = str(t).split(":")
            h, m  = int(parts[0]), int(parts[1])
        ampm = "AM" if h < 12 else "PM"
        h12  = h % 12 or 12
        return f"{h12}:{m:02d} {ampm}"
    except Exception:
        return str(t)


def _set_defaults(context):
    context.attendance_summaries = []
    context.avg_attendance       = None
    context.att_sessions         = None
    context.att_present          = None
    context.att_absent           = None
    context.courses_below_75     = 0
    context.course_count         = None
    context.courses_eligible     = 0
    context.latest_result        = None
    context.latest_grades        = []
    context.results_published_count = 0
    context.fee_summary          = None
    context.att_good             = 75.0
    context.att_warn             = 60.0
    context.is_hosteller         = False
    context.hostel_details       = None
    context.rfid_logs            = []
    context.class_schedules      = []
    context.load_errors          = {}
    context.ward_enrolment_no    = ""
    context.ward_section         = ""
    context.ward_email           = ""
    if not getattr(context, "pp_settings", None):
        from slcm.slcm.doctype.parent_portal_settings.parent_portal_settings import get_parent_portal_settings
        try:
            context.pp_settings = get_parent_portal_settings()
        except Exception:
            context.pp_settings = {}

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
            fields=["course", "course_offering", "term_name",
                    "total_classes", "attended_classes",
                    "attendance_percentage", "eligible_for_exam"],
            order_by="term_name desc, course asc",
            ignore_permissions=True,
        )
        for s in summaries:
            s["course_name"] = s.course
            if s.course_offering:
                try:
                    cn = frappe.db.get_value("Course Offering", s.course_offering, "course_name")
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
    enrolled_offerings = []
    try:
        rows = frappe.db.sql(
            """
            SELECT DISTINCT sec.course, sec.course_offering
            FROM   `tabStudent Enrollment Course` sec
            INNER JOIN `tabStudent Enrollment` se
                   ON se.name = sec.parent AND sec.parenttype = 'Student Enrollment'
            WHERE  se.student = %s AND se.status = 'Enrolled' AND se.docstatus < 2
            """,
            student.name,
            as_dict=True,
        )
        enrolled_offerings = [r.course_offering for r in rows if r.course_offering]
        enrolled_courses = {r.course or r.course_offering for r in rows}
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

        # Course offerings this student is enrolled in or has attendance for
        active_offerings = sorted(
            set(enrolled_offerings)
            | {s.course_offering for s in context.attendance_summaries if s.course_offering}
        )

        schedules = []
        if active_offerings:
            schedules = frappe.get_all(
                "Time Table",
                filters={
                    "schedule_date": ["between", [today, end_date]],
                    "course_offering": ["in", active_offerings],
                    "status": ["!=", "Cancelled"],
                },
                fields=["name", "course", "course_offering", "instructor",
                        "schedule_date", "from_time", "to_time",
                        "venue", "duration_hours", "status"],
                order_by="schedule_date asc, from_time asc",
                limit=15,
                ignore_permissions=True,
            )

        for sc in schedules:
            # Course display name
            sc["course_name"] = sc.course or "—"
            if sc.course_offering:
                try:
                    cn = frappe.db.get_value("Course Offering", sc.course_offering, "course_name")
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
    Headline fee figures for the dashboard — mirrors the hero summary on
    fees.py: invoices are the ground truth when they exist, otherwise the
    programme-level totals on Student Master are used.
    Returns None when the student has no fee data at all.
    """
    flt = frappe.utils.flt

    sm_total    = flt(sm.total_program_fee or 0)
    sm_disc     = flt(sm.discount_amount or 0) or flt(sm.scholarship_amount or 0)
    sm_paid_raw = flt(sm.total_paid_amount or 0)
    sm_net      = flt(sm.net_program_fee or 0) or max(sm_total - sm_disc, 0)
    sm_paid        = min(sm_paid_raw, sm_net) if sm_net > 0 else sm_paid_raw
    sm_outstanding = max(sm_net - sm_paid, 0)

    stored_status = sm.fee_payment_status or "Unpaid"
    if sm_net > 0:
        if sm_outstanding <= 0:
            sm_status = "Paid"
        elif sm_paid > 0:
            sm_status = "Partially Paid"
        elif stored_status in ("Payment Initiated", "Authorized"):
            sm_status = stored_status
        else:
            sm_status = "Unpaid"
    else:
        sm_status = stored_status or "Unpaid"

    invoices = frappe.get_all(
        "Fee Invoice",
        filters={"student": sm.name},
        fields=["final_payable_amount", "paid_amount", "scholarship_amount", "status"],
        ignore_permissions=True,
    )

    if not sm_total and not invoices:
        return None

    if not sm_disc and invoices:
        sm_disc = sum(flt(i.scholarship_amount or 0) for i in invoices)

    if sm_total > 0 and not invoices:
        payable, paid, outstanding, status = sm_net, sm_paid, sm_outstanding, sm_status
    else:
        payable = paid = outstanding = scholarship = 0.0
        for inv in invoices:
            inv_payable = flt(inv.final_payable_amount or 0)
            inv_paid    = flt(inv.paid_amount or 0)
            if inv_payable > 0:
                inv_paid = min(inv_paid, inv_payable)
            payable     += inv_payable
            paid        += inv_paid
            outstanding += max(inv_payable - inv_paid, 0)
            scholarship += flt(inv.scholarship_amount or 0)

        if payable > 0:
            if outstanding <= 0:
                status = "Paid"
            elif paid > 0:
                status = "Partially Paid"
            elif sm_status in ("Payment Initiated", "Authorized"):
                status = sm_status
            else:
                status = "Unpaid"
        else:
            status = sm_status or ""

        # Scholarship recorded on Student Master but not yet on invoices
        if round(sm_disc, 2) > round(scholarship, 2) and abs(sm_disc - scholarship) > 0.5 and payable > 0:
            outstanding = max(outstanding - round(sm_disc - scholarship, 2), 0)

    return {
        "total":       payable,
        "paid":        paid,
        "outstanding": outstanding,
        "status":      status,
        "fmt_total":       "₹{:,.0f}".format(payable),
        "fmt_paid":        "₹{:,.0f}".format(paid),
        "fmt_outstanding": "₹{:,.0f}".format(outstanding),
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

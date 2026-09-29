import frappe
from slcm.utils.faculty_portal import get_faculty_name, set_faculty_nav, set_nav_defaults, set_portal_settings, fmt_time

no_cache = 1


def get_context(context):
    context.no_cache = 1
    set_portal_settings(context)

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "dashboard"

    faculty_name = get_faculty_name()
    if not faculty_name:
        context.not_a_faculty = True
        set_nav_defaults(context)
        return context

    context.not_a_faculty = False

    try:
        faculty = frappe.get_doc("Faculty", faculty_name)
        set_faculty_nav(context, faculty)
        context.faculty_details = _build_faculty_details(faculty, context)

        today = frappe.utils.today()

        # ── Course Offerings assigned to this faculty ──────────────
        course_offerings = frappe.get_all(
            "Course Offering",
            filters={"faculty": faculty_name, "status": ["in", ["Open", "Active"]]},
            fields=["name", "course_name", "course_title", "term_name",
                    "academic_year", "credit_value", "status"],
            order_by="academic_year desc, term_name asc, course_name asc",
            ignore_permissions=True,
        )
        context.total_courses = len(course_offerings)
        co_names = [c.name for c in course_offerings]

        # ── Enrich course offerings with per-course student + session counts ──
        enriched_offerings = []
        for co in course_offerings:
            # Count enrolled students via Student Enrollment Course
            try:
                enr = frappe.db.sql(
                    """SELECT COUNT(DISTINCT se.student) AS cnt
                       FROM `tabStudent Enrollment Course` sec
                       JOIN `tabStudent Enrollment` se ON se.name = sec.parent
                       WHERE sec.course_offering = %s AND sec.status = 'Enrolled'""",
                    co.name, as_dict=True,
                )
                sc = (enr[0].cnt or 0) if enr else 0
            except Exception:
                sc = 0

            # Average attendance %
            try:
                att = frappe.db.sql(
                    """SELECT AVG(attendance_percentage) AS avg_pct, COUNT(*) AS sess
                       FROM `tabAttendance Session`
                       WHERE course_offering = %s AND attendance_marked = 1""",
                    co.name, as_dict=True,
                )
                avg_pct = round(float((att[0].avg_pct or 0) if att else 0), 1)
                sessions_done = (att[0].sess or 0) if att else 0
            except Exception:
                avg_pct = 0.0
                sessions_done = 0

            enriched_offerings.append({
                "name": co.name,
                "course_name": co.course_name or co.name,
                "term_name": co.term_name or "—",
                "academic_year": co.academic_year or "—",
                "credits": co.credit_value or 0,
                "student_count": sc,
                "avg_attendance": avg_pct,
                "sessions_done": sessions_done,
                "status": co.status or "Open",
            })
        context.course_offerings_list = enriched_offerings

        # ── Total unique students across all active course offerings ──────
        total_students = 0
        if co_names:
            try:
                res = frappe.db.sql(
                    """SELECT COUNT(DISTINCT se.student) AS cnt
                       FROM `tabStudent Enrollment Course` sec
                       JOIN `tabStudent Enrollment` se ON se.name = sec.parent
                       WHERE sec.course_offering IN %s AND sec.status = 'Enrolled'""",
                    (tuple(co_names),), as_dict=True,
                )
                total_students = (res[0].cnt or 0) if res else 0
            except Exception:
                total_students = 0
        context.total_students = total_students

        # ── Today's sessions ────────────────────────────────────────
        todays_sessions = []
        if co_names:
            try:
                raw = frappe.get_all(
                    "Attendance Session",
                    filters=[
                        ["course_offering", "in", co_names],
                        ["session_date", "=", today],
                    ],
                    fields=["name", "course_offering", "session_date",
                            "session_start_time", "session_end_time",
                            "room", "session_status", "total_students",
                            "present_count", "attendance_percentage"],
                    order_by="session_start_time asc",
                    ignore_permissions=True,
                )
                co_map = {c.name: c for c in course_offerings}
                for s in raw:
                    co = co_map.get(s.course_offering, frappe._dict())
                    todays_sessions.append({
                        "name": s.name,
                        "course_name": co.get("course_name") or s.course_offering,
                        "from_time": fmt_time(s.session_start_time),
                        "to_time": fmt_time(s.session_end_time),
                        "venue": s.room or "—",
                        "status": s.session_status or "Active",
                        "total_students": s.total_students or 0,
                        "present_count": s.present_count or 0,
                        "attendance_pct": round(float(s.attendance_percentage or 0), 1),
                        "attendance_marked": bool(s.present_count),
                    })
            except Exception:
                todays_sessions = []
        context.todays_sessions = todays_sessions
        context.todays_class_count = len(todays_sessions)

        # ── Attendance pending (sessions not yet marked today/recent) ─
        try:
            pending_att = frappe.db.count(
                "Attendance Session",
                filters={
                    "course_offering": ["in", co_names] if co_names else ["in", ["__none__"]],
                    "attendance_marked": 0,
                    "session_date": ["<=", today],
                    "session_status": "Scheduled",
                },
            ) if co_names else 0
        except Exception:
            pending_att = 0
        context.attendance_pending = pending_att

        # ── Upcoming class schedule (next 7 days) ──────────────────
        next_week = frappe.utils.add_days(today, 7)
        upcoming_classes = []
        if co_names:
            try:
                upcoming_raw = frappe.get_all(
                    "Attendance Session",
                    filters=[
                        ["course_offering", "in", co_names],
                        ["session_date", ">", today],
                        ["session_date", "<=", next_week],
                    ],
                    fields=["name", "course_offering", "session_date",
                            "session_start_time", "session_end_time", "room"],
                    order_by="session_date asc, session_start_time asc",
                    limit=8,
                    ignore_permissions=True,
                )
                co_map = {c.name: c for c in course_offerings}
                for s in upcoming_raw:
                    co = co_map.get(s.course_offering, frappe._dict())
                    upcoming_classes.append({
                        "course_name": co.get("course_name") or s.course_offering,
                        "session_date": frappe.utils.formatdate(s.session_date, "dd MMM"),
                        "from_time": fmt_time(s.session_start_time),
                        "to_time": fmt_time(s.session_end_time),
                        "venue": s.room or "—",
                    })
            except Exception:
                upcoming_classes = []
        context.upcoming_classes = upcoming_classes

        # ── Pending venue bookings ──────────────────────────────────
        try:
            fac_display = f"{faculty.first_name or ''} {faculty.last_name or ''}".strip()
            pending_venues = frappe.db.count(
                "Venue Booking",
                filters={"requester_name": ["in", [faculty_name, fac_display, faculty.email or ""]], "status": "Pending Allotment"},
            )
        except Exception:
            pending_venues = 0
        context.pending_venues = pending_venues

        # ── Condonation requests pending faculty recommendation ────
        try:
            pending_condonation = frappe.db.count(
                "Student Attendance Condonation",
                filters={
                    "course_offering": ["in", co_names] if co_names else ["in", ["__none__"]],
                    "faculty_recommendation": ["in", ["", None, "Pending"]],
                    "final_status": "Pending",
                },
            ) if co_names else 0
        except Exception:
            pending_condonation = 0
        context.pending_condonation = pending_condonation

        # ── Recent attendance sessions (last 5) ─────────────────────
        recent_sessions = []
        if co_names:
            try:
                recent_raw = frappe.get_all(
                    "Attendance Session",
                    filters=[
                        ["course_offering", "in", co_names],
                        ["session_date", "<", today],
                    ],
                    fields=["name", "course_offering", "session_date",
                            "total_students", "present_count", "absent_count",
                            "attendance_percentage", "attendance_marked"],
                    order_by="session_date desc",
                    limit=5,
                    ignore_permissions=True,
                )
                co_map = {c.name: c for c in course_offerings}
                for s in recent_raw:
                    co = co_map.get(s.course_offering, frappe._dict())
                    recent_sessions.append({
                        "course_name": co.get("course_name") or s.course_offering,
                        "session_date": frappe.utils.formatdate(s.session_date, "dd MMM yyyy"),
                        "total": s.total_students or 0,
                        "present": s.present_count or 0,
                        "absent": s.absent_count or 0,
                        "pct": round(float(s.attendance_percentage or 0), 1),
                        "marked": bool(s.attendance_marked),
                    })
            except Exception:
                recent_sessions = []
        context.recent_sessions = recent_sessions

        # ── Course-wise student counts (used as "groups" display) ──
        student_groups = []
        co_map = {c.name: c for c in course_offerings}
        for co in enriched_offerings:
            if co["student_count"] > 0:
                student_groups.append({
                    "name": co["name"],
                    "group_name": co["course_name"],
                    "course_name": f"{co['term_name']} · {co['academic_year']}",
                    "student_count": co["student_count"],
                    "course_offering": co["name"],
                })
        context.student_groups = student_groups
        context.total_groups = len(student_groups)

        # ── Weekly teaching hours ───────────────────────────────────
        try:
            week_start = frappe.utils.get_first_day_of_week(today)
            week_sessions = frappe.get_all(
                "Attendance Session",
                filters=[
                    ["course_offering", "in", co_names] if co_names else ["course_offering", "=", "__none__"],
                    ["session_date", ">=", week_start],
                    ["session_date", "<=", today],
                ],
                fields=["session_start_time", "session_end_time"],
                ignore_permissions=True,
            ) if co_names else []
            total_minutes = 0
            for ws in week_sessions:
                if ws.session_start_time and ws.session_end_time:
                    start = frappe.utils.time_diff_in_seconds(ws.session_end_time, ws.session_start_time)
                    if start > 0:
                        total_minutes += start / 60
            context.weekly_hours = round(total_minutes / 60, 1)
        except Exception:
            context.weekly_hours = 0

        # ── Attendance trend (last 10 sessions for chart) ───────────
        attendance_trend = []
        if co_names:
            try:
                trend_raw = frappe.get_all(
                    "Attendance Session",
                    filters=[
                        ["course_offering", "in", co_names],
                        ["attendance_marked", "=", 1],
                    ],
                    fields=["session_date", "course_offering", "attendance_percentage"],
                    order_by="session_date desc",
                    limit=10,
                    ignore_permissions=True,
                )
                co_map = {c.name: c for c in course_offerings}
                for s in reversed(trend_raw):
                    co = co_map.get(s.course_offering, frappe._dict())
                    attendance_trend.append({
                        "label": frappe.utils.formatdate(s.session_date, "dd MMM"),
                        "pct": round(float(s.attendance_percentage or 0), 1),
                        "course": co.get("course_name") or s.course_offering,
                    })
            except Exception:
                attendance_trend = []
        context.attendance_trend = attendance_trend

        # ── Course-wise average attendance ─────────────────────────
        course_attendance = []
        try:
            for co in enriched_offerings:
                if co["sessions_done"] > 0:
                    course_attendance.append({
                        "course_name": co["course_name"],
                        "avg_pct": co["avg_attendance"],
                        "session_count": co["sessions_done"],
                    })
            course_attendance.sort(key=lambda x: x["avg_pct"])
        except Exception:
            course_attendance = []
        context.course_attendance = course_attendance

        # ── Academic Year ───────────────────────────────────────────
        context.current_academic_year = ""
        if course_offerings:
            context.current_academic_year = course_offerings[0].academic_year or ""

        context.faculty_status = faculty.status or "Active"

        # ── User dashboard preferences ──────────────────────────────
        try:
            prefs_doc = frappe.get_doc(
                "Faculty Portal User Preferences", frappe.session.user
            )
            context.dash_prefs = {
                "hide_today_schedule":    bool(prefs_doc.hide_today_schedule),
                "hide_pending_evaluations": bool(prefs_doc.hide_pending_evaluations),
                "hide_class_statistics":  bool(prefs_doc.hide_class_statistics),
                "hide_workload_summary":  bool(prefs_doc.hide_workload_summary),
                "hide_leave_status":      bool(prefs_doc.hide_leave_status),
            }
        except frappe.DoesNotExistError:
            context.dash_prefs = {}
        except Exception:
            context.dash_prefs = {}

    except Exception as e:
        frappe.log_error(f"Faculty Portal Dashboard error: {e}", "Faculty Portal")
        context.portal_error = str(e)
        set_nav_defaults(context)
        _set_defaults(context)

    return context


def _build_faculty_details(faculty, context):
    """Faculty Details card on the dashboard.

    Isolated in its own try/except so a bad value in an optional field
    (e.g. a dangling Reporting To link) can never break the dashboard.
    Rows with no value are dropped rather than shown as dashes.
    """
    try:
        reporting_to = ""
        if faculty.reporting_to:
            rt = frappe.db.get_value(
                "Faculty", faculty.reporting_to, ["first_name", "last_name"], as_dict=True
            )
            if rt:
                reporting_to = " ".join(filter(None, [rt.first_name, rt.last_name]))
            reporting_to = reporting_to or faculty.reporting_to

        experience = ""
        if faculty.experience_years:
            yrs = int(faculty.experience_years)
            experience = f"{yrs} year{'s' if yrs != 1 else ''}"

        rows = [
            ("mail",              "Email",          faculty.official_email_id or faculty.email or ""),
            ("call",              "Phone",          faculty.phone or ""),
            ("supervisor_account","Reporting To",   reporting_to),
            ("event",             "Joined",         frappe.utils.formatdate(faculty.joining_date, "dd MMM yyyy") if faculty.joining_date else ""),
            ("work_history",      "Experience",     experience),
            ("school",            "Qualification",  faculty.qualification or ""),
            ("psychology",        "Specialization", faculty.specialization or ""),
        ]
        return {
            "is_hod": bool(faculty.is_hod),
            "status": faculty.status or "",
            "rows": [{"icon": i, "label": l, "value": str(v)} for i, l, v in rows if v],
        }
    except Exception as e:
        frappe.log_error(f"Faculty Portal Dashboard – faculty details: {e}", "Faculty Portal")
        return None


def _set_defaults(context):
    context.total_courses = 0
    context.total_students = 0
    context.todays_class_count = 0
    context.todays_sessions = []
    context.attendance_pending = 0
    context.upcoming_classes = []
    context.pending_venues = 0
    context.pending_condonation = 0
    context.current_academic_year = ""
    context.faculty_status = "Active"
    context.attendance_trend = []
    context.course_attendance = []
    context.course_offerings_list = []
    context.dash_prefs = {}

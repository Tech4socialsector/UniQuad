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
    context.active_page = "attendance"

    faculty_name = get_faculty_name()
    if not faculty_name:
        context.not_a_faculty = True
        set_nav_defaults(context)
        _set_defaults(context)
        return context

    context.not_a_faculty = False

    try:
        faculty = frappe.get_doc("Faculty", faculty_name)
        set_faculty_nav(context, faculty)

        today = frappe.utils.today()

        # ── Course offerings ────────────────────────────────────────
        course_offerings = frappe.get_all(
            "Course Offering",
            filters={"faculty": faculty_name, "status": ["in", ["Open", "Active"]]},
            fields=["name", "course_name", "term_name", "academic_year"],
            order_by="course_name asc",
            ignore_permissions=True,
        )
        context.course_offerings = course_offerings
        co_names = [c.name for c in course_offerings]
        co_map = {c.name: c for c in course_offerings}

        # ── Filter from URL params ──────────────────────────────────
        selected_co = frappe.request.args.get("course_offering", "") if frappe.request else ""
        context.selected_co = selected_co

        # ── Attendance Sessions ─────────────────────────────────────
        session_filters = [["course_offering", "in", co_names]] if co_names else [["name", "=", "__none__"]]
        if selected_co and selected_co in co_names:
            session_filters = [["course_offering", "=", selected_co]]

        all_sessions = []
        if co_names:
            raw_sessions = frappe.get_all(
                "Attendance Session",
                filters=session_filters,
                fields=["name", "course_offering", "session_date", "session_type",
                        "session_start_time", "session_end_time", "room", "course_schedule", "class_schedule",
                        "session_status", "total_students", "present_count",
                        "absent_count", "attendance_percentage", "attendance_marked",
                        "rfid_activated_by", "rfid_activation_time", "rfid_active_until"],
                order_by="session_date desc",
                ignore_permissions=True,
            )
            now = frappe.utils.now_datetime()
            
            # Pre-fetch rooms from course schedules or time tables if they are missing on the session
            cs_names = [s.course_schedule for s in raw_sessions if s.course_schedule and not s.room]
            cs_room_map = {}
            if cs_names:
                cs_data = frappe.get_all("Course Schedule", filters={"name": ("in", list(set(cs_names)))}, fields=["name", "room"])
                cs_room_map = {d.name: d.room for d in cs_data}
                
            tt_names = [s.class_schedule for s in raw_sessions if s.class_schedule and not s.room]
            tt_venue_map = {}
            if tt_names:
                tt_data = frappe.get_all("Time Table", filters={"name": ("in", list(set(tt_names)))}, fields=["name", "venue"])
                tt_venue_map = {d.name: d.venue for d in tt_data}

            for s in raw_sessions:
                co = co_map.get(s.course_offering, frappe._dict())
                pct = round(float(s.attendance_percentage or 0), 1)
                rfid_active = bool(
                    s.rfid_activation_time and s.rfid_active_until and now <= s.rfid_active_until
                )
                term_name = co.get("term_name") or "—"
                academic_year = co.get("academic_year") or "—"
                all_sessions.append({
                    "name": s.name,
                    "course_name": co.get("course_name") or s.course_offering,
                    "course_offering": s.course_offering,
                    "session_date": str(s.session_date) if s.session_date else "",
                    "session_date_fmt": frappe.utils.formatdate(s.session_date, "dd MMM yyyy"),
                    "session_type": s.session_type or "Lecture",
                    "from_time": fmt_time(s.session_start_time),
                    "to_time": fmt_time(s.session_end_time),
                    "from_time_sort": str(s.session_start_time) if s.session_start_time else "",
                    "venue": s.room or cs_room_map.get(s.course_schedule) or tt_venue_map.get(s.class_schedule) or "—",
                    "status": s.session_status or "Active",
                    "total": s.total_students or 0,
                    "present": s.present_count or 0,
                    "absent": s.absent_count or 0,
                    "pct": pct,
                    "marked": bool(s.attendance_marked),
                    "rfid_activated": bool(s.rfid_activation_time),
                    "rfid_active": rfid_active,
                    "rfid_active_until": str(s.rfid_active_until) if s.rfid_active_until else "",
                    "term_name": term_name,
                    "academic_year": academic_year,
                    "term_key": f"{term_name}|{academic_year}",
                })

        # ── Distinct terms present, most recent first ────────────────
        # "Most recent" = the term containing the latest session_date, since
        # Term/Academic Year have no reliable start/end dates to sort by.
        # Terms are seeded from two sources so a newly-assigned course
        # offering shows up as a switchable term even before any Attendance
        # Session has been created against it:
        #   1. Existing sessions (sorts to the top, real activity).
        #   2. Course offerings with no sessions yet (sorted after, using
        #      "" as their latest-date so they never outrank real activity).
        term_latest_date = {}
        term_labels = {}
        for s in all_sessions:
            key = s["term_key"]
            term_labels[key] = f"{s['term_name']} · {s['academic_year']}"
            if key not in term_latest_date or s["session_date"] > term_latest_date[key]:
                term_latest_date[key] = s["session_date"]

        for co in course_offerings:
            term_name = co.get("term_name") or "—"
            academic_year = co.get("academic_year") or "—"
            key = f"{term_name}|{academic_year}"
            if key not in term_latest_date:
                term_latest_date[key] = ""
                term_labels[key] = f"{term_name} · {academic_year}"

        terms = sorted(
            term_latest_date.keys(),
            key=lambda k: term_latest_date[k],
            reverse=True,
        )
        context.terms = [{"key": k, "label": term_labels[k]} for k in terms]

        # ── Selected term (defaults to the most recent) ──────────────
        selected_term = frappe.request.args.get("term", "") if frappe.request else ""
        if not selected_term or selected_term not in terms:
            selected_term = terms[0] if terms else ""
        context.selected_term = selected_term
        if selected_term:
            parts = selected_term.split("|")
            context.active_term_name = parts[0]
            context.active_academic_year = parts[1] if len(parts) > 1 else ""

        sessions = [s for s in all_sessions if not selected_term or s["term_key"] == selected_term]
        context.sessions = sessions

        # ── Today's sessions (for the quick-view cards) ──────────────
        # Grouped by course offering so a course with multiple time slots
        # today (e.g. two lecture sections) renders as one card with a
        # slot picker, instead of one card per slot.
        todays_sessions = [s for s in sessions if s["session_date"] == str(today)]
        todays_by_course = {}
        todays_order = []
        for s in todays_sessions:
            key = s["course_offering"]
            if key not in todays_by_course:
                todays_by_course[key] = []
                todays_order.append(key)
            todays_by_course[key].append(s)

        todays_courses = []
        for key in todays_order:
            slots = sorted(todays_by_course[key], key=lambda s: s["from_time"])
            todays_courses.append({
                "course_offering": key,
                "course_name": slots[0]["course_name"],
                "slots": slots,
            })
        context.todays_sessions = todays_sessions
        context.todays_courses = todays_courses

        # ── Stats ───────────────────────────────────────────────────
        now = frappe.utils.now_datetime()
        today_date_str = str(now.date())
        current_time_str = str(now.time())

        completed_sessions = 0
        marked_sessions = 0
        pending_sessions = 0
        upcoming_sessions = 0
        
        for s in sessions:
            is_completed = False
            # Check if date is in the past
            if s["session_date"] < today_date_str:
                is_completed = True
            elif s["session_date"] == today_date_str:
                # If today, check if time has passed or if it's already marked
                if s["marked"] or s["from_time_sort"] < current_time_str:
                    is_completed = True

            if is_completed:
                completed_sessions += 1
                if s["marked"]:
                    marked_sessions += 1
                    s["computed_status"] = "Marked"
                else:
                    pending_sessions += 1
                    s["computed_status"] = "Pending"
            else:
                upcoming_sessions += 1
                s["computed_status"] = "Upcoming"

        context.completed_sessions = completed_sessions
        context.marked_sessions = marked_sessions
        context.pending_sessions = pending_sessions
        context.upcoming_sessions = upcoming_sessions

        # ── Condonation requests pending faculty recommendation ─────
        condonation_requests = []
        if co_names:
            raw_cond = frappe.get_all(
                "Student Attendance Condonation",
                filters={
                    "course_offering": ["in", co_names],
                    "final_status": "Pending",
                },
                fields=["name", "student", "course_offering", "number_of_sessions",
                        "number_of_hours", "condonation_reason", "faculty_recommendation",
                        "final_status", "creation"],
                order_by="creation desc",
                ignore_permissions=True,
            )
            for req in raw_cond:
                student_name = frappe.db.get_value(
                    "Student Master", req.student, "first_name"
                ) or req.student
                co = co_map.get(req.course_offering, frappe._dict())
                condonation_requests.append({
                    "name": req.name,
                    "student": req.student,
                    "student_display": student_name,
                    "course_display": co.get("course_name") or req.course_offering,
                    "sessions": req.number_of_sessions or 0,
                    "hours": round(float(req.number_of_hours or 0), 1),
                    "reason": req.condonation_reason or "—",
                    "recommendation": req.faculty_recommendation or "",
                    "status": req.final_status or "Pending",
                    "created": frappe.utils.formatdate(req.creation, "dd MMM yyyy"),
                })
        context.condonation_requests = condonation_requests
        context.pending_condonation = len([r for r in condonation_requests if r["recommendation"] in ("", "Pending", None)])

        # ── Monthly summary per course offering ─────────────────────
        monthly_summary = []
        if co_names:
            for co in course_offerings[:6]:
                att_summary = frappe.db.get_value(
                    "Attendance Summary",
                    {"course_offering": co.name},
                    ["total_classes", "attended_classes", "attendance_percentage"],
                    as_dict=True,
                )
                if att_summary:
                    monthly_summary.append({
                        "course_name": co.course_name,
                        "total_classes": att_summary.total_classes or 0,
                        "attended": att_summary.attended_classes or 0,
                        "avg_pct": round(float(att_summary.attendance_percentage or 0), 1),
                    })
        context.monthly_summary = monthly_summary

    except Exception as e:
        frappe.log_error(f"Faculty Portal Attendance error: {e}", "Faculty Portal")
        context.portal_error = str(e)
        set_nav_defaults(context)
        _set_defaults(context)

    return context


def _set_defaults(context):
    context.course_offerings = []
    context.selected_co = ""
    context.sessions = []
    context.todays_sessions = []
    context.todays_courses = []
    context.terms = []
    context.selected_term = ""
    context.completed_sessions = 0
    context.marked_sessions = 0
    context.pending_sessions = 0
    context.upcoming_sessions = 0
    context.condonation_requests = []
    context.pending_condonation = 0
    context.monthly_summary = []

@frappe.whitelist(allow_guest=True)
def debug_venue():
    import json
    sessions = frappe.get_all("Attendance Session", fields=["name", "room", "course_schedule"], limit=5)
    cs_names = [s.course_schedule for s in sessions if s.course_schedule]
    cs_data = []
    if cs_names:
        cs_data = frappe.get_all("Course Schedule", filters={"name": ["in", cs_names]}, fields=["name", "room"])
    return {"sessions": sessions, "cs_data": cs_data}

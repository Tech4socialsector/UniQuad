import frappe
from slcm.slcm.utils.attendance_lock import compute_lock_state, get_lock_hours
from slcm.utils.faculty_portal import get_faculty_name, set_faculty_nav, set_nav_defaults, set_portal_settings, fmt_time

no_cache = 1

# Sessions that didn't take place: not counted in the stats or the
# Session 1, 2, 3… numbering.
NOT_HELD_STATUSES = ("Cancelled", "Postponed")


def _time_sort_key(t):
    """Zero-padded seconds, so times sort correctly as strings (a plain
    str(timedelta) puts "10:00:00" before "9:00:00")."""
    if not t:
        return ""
    return "%05d" % int(frappe.utils.to_timedelta(t).total_seconds())


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

        # ── Classes this faculty teaches (Active academic years) ────
        from slcm.api.faculty_portal import _class_label, _get_faculty_classes

        faculty_classes = _get_faculty_classes(
            faculty_name,
            fields=["name", "course", "course_name", "class_type", "section", "group_name",
                    "academic_term as term_name", "academic_year", "programme as program"],
        )
        for c in faculty_classes:
            c.course_name = _class_label(c)
        faculty_classes.sort(key=lambda c: c.course_name or "")
        context.faculty_classes = faculty_classes
        co_names = [c.name for c in faculty_classes]
        co_map = {c.name: c for c in faculty_classes}

        # Readable programme name shown under the course in the sessions table
        programme_ids = list({c.program for c in faculty_classes if c.program})
        programme_names = {
            p.name: p.program_name or p.name
            for p in frappe.get_all(
                "Programme",
                filters={"name": ["in", programme_ids]},
                fields=["name", "program_name"],
                ignore_permissions=True,
            )
        } if programme_ids else {}
        # Shown under each course in the Course filter
        for c in faculty_classes:
            c.programme_name = programme_names.get(c.program) or c.program or ""

        # ── Filter from URL params ──────────────────────────────────
        selected_co = frappe.request.args.get("class_name", "") if frappe.request else ""
        context.selected_co = selected_co

        # ── Attendance Sessions ─────────────────────────────────────
        session_filters = [["class_name", "in", co_names]] if co_names else [["name", "=", "__none__"]]
        if selected_co and selected_co in co_names:
            session_filters = [["class_name", "=", selected_co]]

        all_sessions = []
        if co_names:
            raw_sessions = frappe.get_all(
                "Attendance Session",
                filters=session_filters,
                fields=["name", "class_name", "session_date", "session_type",
                        "session_start_time", "session_end_time", "room", "course_schedule", "class_schedule",
                        "session_status", "total_students", "present_count",
                        "absent_count", "attendance_percentage", "attendance_marked",
                        "rfid_activated_by", "rfid_activation_time", "rfid_active_until",
                        "attendance_reopened", "reopened_by", "reopened_on", "reopen_reason"],
                order_by="session_date desc",
                ignore_permissions=True,
            )
            now = frappe.utils.now_datetime()
            lock_hours = get_lock_hours()
            reopener_ids = list({s.reopened_by for s in raw_sessions if s.reopened_by})
            reopener_names = {
                u.name: u.full_name or u.name
                for u in frappe.get_all(
                    "User", filters={"name": ["in", reopener_ids]}, fields=["name", "full_name"],
                    ignore_permissions=True,
                )
            } if reopener_ids else {}
            
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

            cp_dates_by_tt = _get_class_participation_ranges(
                [s.class_schedule for s in raw_sessions if s.class_schedule]
            )
            # Pending-task keys per session (same rules as the dashboard's
            # Pending Tasks card, which links here with ?pending=<key>)
            from slcm.slcm.utils.class_participation import get_session_task_flags
            task_flags = get_session_task_flags(raw_sessions, today)

            for s in raw_sessions:
                co = co_map.get(s.class_name, frappe._dict())
                session_type = s.session_type or "Lecture"
                session_day = frappe.utils.getdate(s.session_date) if s.session_date else None
                has_cp = bool(
                    session_day
                    and session_type != "Office Hour"
                    and any(start <= session_day <= end for start, end in cp_dates_by_tt.get(s.class_schedule, ()))
                )
                pct = round(float(s.attendance_percentage or 0), 1)
                rfid_active = bool(
                    s.rfid_activation_time and s.rfid_active_until and now <= s.rfid_active_until
                )
                term_name = co.get("term_name") or "—"
                academic_year = co.get("academic_year") or "—"
                lock = compute_lock_state(s, now=now, lock_hours=lock_hours)
                all_sessions.append({
                    "name": s.name,
                    "course_name": co.get("course_name") or s.class_name,
                    "class_name": s.class_name,
                    "programme_name": programme_names.get(co.get("program")) or co.get("program") or "",
                    "session_date": str(s.session_date) if s.session_date else "",
                    "session_date_fmt": frappe.utils.formatdate(s.session_date, "dd MMM yyyy"),
                    "session_type": session_type,
                    # What faculty see — "Office Hour" is shown as "OH" across the portal
                    "session_type_label": "OH" if session_type == "Office Hour" else session_type,
                    # Which page tab lists it: Office Hours vs class sessions;
                    # has_cp = also listed under Class Participants.
                    "category": "oh" if session_type == "Office Hour" else "class",
                    "has_cp": has_cp,
                    "tasks": " ".join(sorted(task_flags.get(s.name, ()))),
                    "from_time": fmt_time(s.session_start_time),
                    "to_time": fmt_time(s.session_end_time),
                    "from_time_sort": _time_sort_key(s.session_start_time),
                    "venue": s.room or cs_room_map.get(s.course_schedule) or tt_venue_map.get(s.class_schedule) or "—",
                    "status": s.session_status or "Active",
                    "not_held": s.session_status in NOT_HELD_STATUSES,
                    # Attendance lock (see slcm.slcm.utils.attendance_lock)
                    "locked": lock.locked,
                    "reopened": lock.reopened and lock.past_lock,
                    "lock_at_fmt": frappe.utils.format_datetime(lock.lock_at, "dd MMM yyyy, hh:mm a") if lock.lock_at else "",
                    "reopened_by_name": reopener_names.get(s.reopened_by, s.reopened_by or ""),
                    "reopened_on_fmt": frappe.utils.format_datetime(s.reopened_on, "dd MMM yyyy, hh:mm a") if s.reopened_on else "",
                    "reopen_reason": s.reopen_reason or "",
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

            # ── Session-wise numbering: Session 1, 2, 3… ────────────────
            # Chronological per class, class sessions and OH
            # numbered separately, sessions that weren't held skipped.
            # Counted over every term so the number never shifts when a
            # term filter is applied.
            seq_counts = {}
            for s in sorted(all_sessions, key=lambda x: (x["session_date"], x["from_time_sort"], x["name"])):
                if s["not_held"]:
                    s["seq"] = 0
                    continue
                key = (s["class_name"], s["category"])
                seq_counts[key] = seq_counts.get(key, 0) + 1
                s["seq"] = seq_counts[key]
            for s in all_sessions:
                s["seq_total"] = seq_counts.get((s["class_name"], s["category"]), 0)

        # ── Distinct terms present, most recent first ────────────────
        # "Most recent" = the term containing the latest session_date, since
        # Term/Academic Year have no reliable start/end dates to sort by.
        # Terms are seeded from two sources so a newly-assigned class
        # shows up as a switchable term even before any Attendance
        # Session has been created against it:
        #   1. Existing sessions (sorts to the top, real activity).
        #   2. Classes with no sessions yet (sorted after, using
        #      "" as their latest-date so they never outrank real activity).
        term_latest_date = {}
        term_labels = {}
        for s in all_sessions:
            key = s["term_key"]
            term_labels[key] = f"{s['term_name']} · {s['academic_year']}"
            if key not in term_latest_date or s["session_date"] > term_latest_date[key]:
                term_latest_date[key] = s["session_date"]

        for co in faculty_classes:
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

        # ── Selected term (only when asked for via ?term=) ──────────
        # Defaulting to the single most recent term hid every session of a
        # faculty's other active classes (e.g. Office Hours in a
        # Term 2 class while a Trimester I course had later classes), with
        # no visible way to switch. Classes are already limited to the
        # Active academic year(s), so show all of them unless a term is requested.
        selected_term = frappe.request.args.get("term", "") if frappe.request else ""
        if selected_term not in terms:
            selected_term = ""
        context.selected_term = selected_term
        if selected_term:
            parts = selected_term.split("|")
            context.active_term_name = parts[0]
            context.active_academic_year = parts[1] if len(parts) > 1 else ""

        sessions = [s for s in all_sessions if not selected_term or s["term_key"] == selected_term]
        context.sessions = sessions

        # ── Today's sessions (for the quick-view cards) ──────────────
        # Grouped by class so a course with multiple time slots
        # today (e.g. two lecture sections) renders as one card with a
        # slot picker, instead of one card per slot.
        todays_sessions = [s for s in sessions if s["session_date"] == str(today)]
        todays_by_course = {}
        todays_order = []
        for s in todays_sessions:
            key = s["class_name"]
            if key not in todays_by_course:
                todays_by_course[key] = []
                todays_order.append(key)
            todays_by_course[key].append(s)

        todays_courses = []
        for key in todays_order:
            slots = sorted(todays_by_course[key], key=lambda s: s["from_time"])
            todays_courses.append({
                "class_name": key,
                "course_name": slots[0]["course_name"],
                "slots": slots,
            })
        context.todays_sessions = todays_sessions
        context.todays_courses = todays_courses

        # ── Stats ───────────────────────────────────────────────────
        # Completed = Marked + Pending (today's unmarked "Active" sessions
        # count as Pending). Cancelled/Postponed sessions count nowhere.
        # The page recalculates these in the browser for the active tab and
        # filters (_fpRefreshStats); these are the first-paint values.
        today_date_str = str(frappe.utils.now_datetime().date())

        marked_sessions = 0
        pending_sessions = 0
        upcoming_sessions = 0

        for s in sessions:
            if s["not_held"]:
                s["computed_status"] = s["status"]
            elif s["session_date"] > today_date_str:
                upcoming_sessions += 1
                s["computed_status"] = "Upcoming"
            elif s["marked"]:
                marked_sessions += 1
                s["computed_status"] = "Marked"
            else:
                pending_sessions += 1
                s["computed_status"] = "Pending" if s["session_date"] < today_date_str else "Active"

        # Default table order: today and past sessions newest first (what
        # faculty act on), then upcoming ones soonest first.
        held = [s for s in sessions if s["session_date"] <= today_date_str]
        future = [s for s in sessions if s["session_date"] > today_date_str]
        held.sort(key=lambda s: (s["session_date"], s["from_time_sort"]), reverse=True)
        future.sort(key=lambda s: (s["session_date"], s["from_time_sort"]))
        sessions[:] = held + future

        context.completed_sessions = marked_sessions + pending_sessions
        context.marked_sessions = marked_sessions
        context.pending_sessions = pending_sessions
        context.upcoming_sessions = upcoming_sessions
        context.total_sessions = marked_sessions + pending_sessions + upcoming_sessions

        # ── Condonation requests pending faculty recommendation ─────
        condonation_requests = []
        if co_names:
            raw_cond = frappe.get_all(
                "Student Attendance Condonation",
                filters={
                    "class_name": ["in", co_names],
                    "final_status": "Pending",
                },
                fields=["name", "student", "class_name", "number_of_sessions",
                        "number_of_hours", "condonation_reason", "faculty_recommendation",
                        "final_status", "creation"],
                order_by="creation desc",
                ignore_permissions=True,
            )
            for req in raw_cond:
                student_name = frappe.db.get_value(
                    "Student Master", req.student, "first_name"
                ) or req.student
                co = co_map.get(req.class_name, frappe._dict())
                condonation_requests.append({
                    "name": req.name,
                    "student": req.student,
                    "student_display": student_name,
                    "course_display": co.get("course_name") or req.class_name,
                    "sessions": req.number_of_sessions or 0,
                    "hours": round(float(req.number_of_hours or 0), 1),
                    "reason": req.condonation_reason or "—",
                    "recommendation": req.faculty_recommendation or "",
                    "status": req.final_status or "Pending",
                    "created": frappe.utils.formatdate(req.creation, "dd MMM yyyy"),
                })
        context.condonation_requests = condonation_requests
        context.pending_condonation = len([r for r in condonation_requests if r["recommendation"] in ("", "Pending", None)])

        # ── Monthly summary per class ───────────────────────────────
        monthly_summary = []
        if co_names:
            for co in faculty_classes[:6]:
                att_summary = frappe.db.get_value(
                    "Attendance Summary",
                    {"class_name": co.name},
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


def _get_class_participation_ranges(time_table_names):
    """{Time Table name: [(start_date, end_date), ...]} of the Class
    Participation weeks configured for each entry's series, in two bulk
    queries. Generated occurrences carry a copy of the series root's week
    table, so the root's rows are used with the occurrence's own as fallback
    (same rule as slcm.slcm.utils.class_participation)."""
    time_table_names = list(set(time_table_names))
    if not time_table_names:
        return {}

    tts = frappe.get_all(
        "Time Table",
        filters={"name": ["in", time_table_names]},
        fields=["name", "parent_schedule"],
        ignore_permissions=True,
    )
    parents = {t.name for t in tts} | {t.parent_schedule for t in tts if t.parent_schedule}

    ranges_by_parent = {}
    for row in frappe.get_all(
        "Class Participation Week",
        filters={"parenttype": "Time Table", "parent": ["in", list(parents)]},
        fields=["parent", "start_date", "end_date"],
        ignore_permissions=True,
    ):
        if row.start_date and row.end_date:
            ranges_by_parent.setdefault(row.parent, []).append(
                (frappe.utils.getdate(row.start_date), frappe.utils.getdate(row.end_date))
            )

    return {
        t.name: ranges_by_parent.get(t.parent_schedule) or ranges_by_parent.get(t.name) or []
        for t in tts
    }


def _set_defaults(context):
    context.faculty_classes = []
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

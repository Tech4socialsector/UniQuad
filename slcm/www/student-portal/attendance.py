import frappe

no_cache = 1


def get_context(context):
    context.no_cache = 1

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "attendance"

    student_name = _get_student_name()
    if not student_name:
        context.no_student = True
        _set_nav_defaults(context)
        _set_defaults(context)
        return context

    context.no_student = False

    try:
        student = frappe.get_doc("Student Master", student_name)
        _set_student_nav(context, student)

        # ── Attendance Settings ────────────────────────────────────
        try:
            settings = frappe.get_single("Attendance Settings")
            context.allow_condonation = bool(settings.allow_condonation)
            context.min_condonation_pct = float(
                getattr(settings, "condonation_min_percentage", 66) or 66
            )
        except Exception:
            context.allow_condonation = True
            context.min_condonation_pct = 66.0

        # ── Portal colour thresholds (from Student Portal Settings) ─
        try:
            from slcm.slcm.doctype.student_portal_settings.student_portal_settings import (
                get_student_portal_settings,
            )
            _ps = get_student_portal_settings()
            context.att_good_threshold   = float(_ps.get("att_good_threshold", 75))
            context.att_warn_threshold   = float(_ps.get("att_warn_threshold", 60))
            context.att_label_good       = _ps.get("att_label_good",   "Good")
            context.att_label_warn       = _ps.get("att_label_warn",   "Low")
            context.att_label_danger     = _ps.get("att_label_danger", "Critical")
        except Exception:
            context.att_good_threshold   = 75.0
            context.att_warn_threshold   = 60.0
            context.att_label_good       = "Good"
            context.att_label_warn       = "Low"
            context.att_label_danger     = "Critical"

        # ── Condonation Reasons ────────────────────────────────────
        try:
            context.condonation_reasons = [
                r.name
                for r in frappe.get_all(
                    "Condonation Reason",
                    fields=["name"],
                    order_by="name asc",
                    ignore_permissions=True,
                )
            ]
        except Exception:
            context.condonation_reasons = []

        # ── Attendance Summaries ───────────────────────────────────
        summaries = frappe.get_all(
            "Attendance Summary",
            filters={"student": student_name},
            fields=[
                "name", "course_offering", "course", "department",
                "academic_year", "term_name",
                "total_classes", "attended_classes",
                "total_class_hours", "total_attended_class_hours",
                "total_office_hours", "total_condonation_hours",
                "attendance_percentage", "minimum_required_percentage",
                "eligible_for_exam", "last_updated",
            ],
            order_by="term_name desc, course_offering asc",
            ignore_permissions=True,
        )

        # Enrich with Course Offering info
        student_cos = []          # for Condonation dropdown (Course Offering link)
        seen_cos = set()

        for s in summaries:
            co_name = s.course_offering or ""
            s["course_display"] = co_name or s.course or "Unknown Course"
            s["faculty"] = "—"

            if co_name:
                try:
                    co = frappe.db.get_value(
                        "Course Offering",
                        co_name,
                        ["course_name", "faculty", "term_name", "course_title", "credit_value"],
                        as_dict=True,
                    )
                    if co:
                        s["course_display"] = co.course_name or s["course_display"]
                        s["faculty"] = co.faculty or "—"
                        s["course_code"] = co.course_title or ""
                        s["credits"] = co.credit_value or ""
                        if not s.term_name:
                            s["term_name"] = co.term_name or ""
                except Exception:
                    pass

            pct = float(s.attendance_percentage or 0)
            req = float(s.minimum_required_percentage or 75)
            s["pct"] = round(pct, 1)
            _good = context.att_good_threshold
            _warn = context.att_warn_threshold
            s["status_color"] = (
                "var(--sp-success)" if pct >= _good
                else "var(--sp-warning)" if pct >= _warn
                else "var(--sp-danger)"
            )
            s["status_label"] = (
                context.att_label_good if pct >= _good
                else context.att_label_warn if pct >= _warn
                else context.att_label_danger
            )
            s["shortfall"] = max(0, round(req - pct, 1))
            # Students may apply for condonation anytime regardless of their
            # current attendance % — the minimum-percentage floor is only
            # enforced at final (Programme Chair) approval time.
            s["can_apply_condonation"] = context.allow_condonation

            # Build unique course-offering list for Condonation modal
            if co_name and co_name not in seen_cos:
                seen_cos.add(co_name)
                student_cos.append({
                    "course_offering": co_name,
                    "name": s["course_display"],
                })

        context.student_cos = student_cos

        # ── Overall Stats ──────────────────────────────────────────
        if summaries:
            pcts = [float(s.attendance_percentage or 0) for s in summaries]
            context.avg_attendance = round(sum(pcts) / len(pcts), 1)
            context.total_courses = len(summaries)
            context.courses_below_75 = sum(1 for p in pcts if p < 75)
            context.courses_eligible = sum(
                1 for s in summaries if s.eligible_for_exam
            )
        else:
            context.avg_attendance = 0.0
            context.total_courses = 0
            context.courses_below_75 = 0
            context.courses_eligible = 0

        context.attendance_summaries = summaries

        # ── Group by term ──────────────────────────────────────────
        term_groups = {}
        for s in summaries:
            term = s.term_name or "Other"
            term_groups.setdefault(term, []).append(s)

        context.term_groups = [
            {"term": t, "summaries": v} for t, v in term_groups.items()
        ]

        # ── Condonation Applications ───────────────────────────────
        try:
            cond_apps = frappe.get_all(
                "Student Attendance Condonation",
                filters={"student": student_name},
                fields=[
                    "name", "course_offering", "course", "number_of_sessions",
                    "number_of_hours", "condonation_reason", "final_status",
                    "faculty_recommendation", "remarks", "creation",
                ],
                order_by="creation desc",
                ignore_permissions=True,
            )
            for app in cond_apps:
                st = app.final_status or "Pending"
                app["status_color"] = {
                    "Pending":  "var(--sp-warning)",
                    "Approved": "var(--sp-success)",
                    "Rejected": "var(--sp-danger)",
                }.get(st, "var(--sp-text-4)")
                app["status_bg"] = {
                    "Pending":  "var(--sp-warning-bg)",
                    "Approved": "var(--sp-success-bg)",
                    "Rejected": "var(--sp-danger-bg)",
                }.get(st, "var(--sp-bg)")
                # Resolve course display name from summaries
                app["course_display"] = app.course_offering or app.course or "—"
                for s in summaries:
                    if s.course_offering == app.course_offering:
                        app["course_display"] = s.get("course_display") or app["course_display"]
                        break
            context.condonation_applications = cond_apps
        except Exception:
            context.condonation_applications = []

        # ── OH & Class Participation (attendance + participation, no marks) ──
        # From the OH / Class-Participation Student Groups the student is in and
        # the Time Table sessions scheduled for them — same rules as the faculty
        # portal. (Replaces the older "Office Hours Session" records.)
        try:
            from slcm.slcm.utils.class_participation import get_student_participation

            participation = get_student_participation(student_name)
            context.oh_groups = participation["oh"]
            context.cp_groups = participation["cp"]
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Student Portal – OH / Class Participation")
            context.oh_groups = []
            context.cp_groups = []

        # ── Recent Daily Attendance (last 30 days) ─────────────────
        today_date = frappe.utils.today()
        from_date = frappe.utils.add_days(today_date, -30)
        try:
            recent_records = frappe.get_all(
                "Student Attendance",
                filters=[
                    ["student", "=", student_name],
                    ["attendance_date", ">=", from_date],
                    ["attendance_date", "<=", today_date],
                ],
                fields=[
                    "attendance_date", "course_offer", "status",
                    "in_time", "out_time", "session_type",
                ],
                order_by="attendance_date desc",
                limit=30,
                ignore_permissions=True,
            )
            context.recent_attendance = recent_records
        except Exception:
            context.recent_attendance = []

        # ── Calendar Data (3-month window: prev/current/next month) ──
        import json
        from datetime import timedelta
        try:
            _today_d = frappe.utils.getdate(today_date)
            _first_this = _today_d.replace(day=1)
            _first_prev = (_first_this - timedelta(days=1)).replace(day=1)
            _first_next = (_first_this.replace(day=28) + timedelta(days=4)).replace(day=1)
            _last_next = (_first_next.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            _cal_start_str = str(_first_prev)
            _cal_end_str = str(_last_next)

            # ── Fetch attendance with all useful fields ────────────
            _cal_att = frappe.get_all(
                "Student Attendance",
                filters=[
                    ["student", "=", student_name],
                    ["attendance_date", ">=", _cal_start_str],
                    ["attendance_date", "<=", _cal_end_str],
                ],
                fields=[
                    "attendance_date", "course_offer", "course", "status",
                    "in_time", "out_time", "session_type", "hours_counted",
                    "class_schedule", "instructor", "room",
                ],
                order_by="attendance_date asc",
                ignore_permissions=True,
            )

            # ── Batch-fetch Time Table for from/to times ───────
            _cs_ids = {str(_r.class_schedule) for _r in _cal_att if _r.class_schedule}
            _cs_map = {}
            if _cs_ids:
                _cs_rows = frappe.get_all(
                    "Time Table",
                    filters={"name": ["in", list(_cs_ids)]},
                    fields=["name", "from_time", "to_time", "venue"],
                    ignore_permissions=True,
                )
                _cs_map = {_r.name: _r for _r in _cs_rows}

            # ── Course name map: prefer summaries (already resolved) ──
            # summaries already ran frappe.db.get_value per course_offering
            _summary_display_map = {
                s.course_offering: s.get("course_display", "")
                for s in summaries if s.course_offering
            }
            _summary_faculty_map = {
                s.course_offering: s.get("faculty", "")
                for s in summaries if s.course_offering
            }
            # Batch-fetch any course_offers not in summaries
            _co_ids = {
                str(_r.course_offer) for _r in _cal_att
                if _r.course_offer and str(_r.course_offer) not in _summary_display_map
            }
            _co_extra_map = {}
            if _co_ids:
                _co_extra_rows = frappe.get_all(
                    "Course Offering",
                    filters={"name": ["in", list(_co_ids)]},
                    fields=["name", "course_name", "faculty"],
                    ignore_permissions=True,
                )
                _co_extra_map = {_r.name: _r for _r in _co_extra_rows}

            # ── Build session entries per date ─────────────────────
            _sessions_by_date = {}
            for _r in _cal_att:
                _d = str(_r.attendance_date)
                _cs      = _cs_map.get(str(_r.class_schedule or ""), frappe._dict())
                _co_id   = str(_r.course_offer or "")
                _co_extra = _co_extra_map.get(_co_id, frappe._dict())

                _cname = (
                    _summary_display_map.get(_co_id)
                    or _co_extra.get("course_name")
                    or str(_r.course or _co_id or "—")
                )
                _instructor = str(
                    _summary_faculty_map.get(_co_id)
                    or _co_extra.get("faculty")
                    or _r.instructor or ""
                )
                _venue      = str(_cs.get("venue") or _r.room or "")
                _from_time  = _fmt_time(_cs.get("from_time")) if _cs.get("from_time") else ""
                _to_time    = _fmt_time(_cs.get("to_time")) if _cs.get("to_time") else ""
                _in_time    = _fmt_datetime_time(_r.in_time)
                _out_time   = _fmt_datetime_time(_r.out_time)

                _sessions_by_date.setdefault(_d, []).append({
                    "course_name":    str(_cname),
                    "course_offering": str(_r.course_offer or ""),
                    "session_type":   str(_r.session_type or "Lecture"),
                    "from_time":      _from_time,
                    "to_time":        _to_time,
                    "instructor":     _instructor,
                    "venue":          _venue,
                    "status":         str(_r.status or ""),
                    "in_time":        _in_time,
                    "out_time":       _out_time,
                    "hours":          float(_r.hours_counted or 0),
                })

            # Sort each day's sessions by scheduled start time
            for _d in _sessions_by_date:
                _sessions_by_date[_d].sort(key=lambda x: x["from_time"] or "")

            # ── Add the student's upcoming OH sessions as Scheduled ─
            for _grp in (context.oh_groups or []):
                for _oh in _grp.sessions:
                    if _oh.attendance != "Upcoming":
                        continue
                    _sessions_by_date.setdefault(_oh.date, []).append({
                        "course_name":    str(_grp.course_name or _grp.title or "OH"),
                        "course_offering": str(_oh.course_offering or ""),
                        "session_type":   "Office Hour",
                        "from_time":      str(_oh.from_fmt or ""),
                        "to_time":        str(_oh.to_fmt or ""),
                        "instructor":     str(_oh.faculty or ""),
                        "venue":          str(_oh.venue or ""),
                        "status":         "Scheduled",
                        "in_time":        "",
                        "out_time":       "",
                        "hours":          0,
                    })

            # ── Fetch holidays ─────────────────────────────────────
            _holidays = {}
            try:
                _hol_rows = frappe.get_all(
                    "Academic Holiday",
                    filters=[
                        ["holiday_date", ">=", _cal_start_str],
                        ["holiday_date", "<=", _cal_end_str],
                    ],
                    fields=["holiday_date", "description", "holiday_type"],
                    ignore_permissions=True,
                )
                for _h in _hol_rows:
                    _holidays[str(_h.holiday_date)] = {
                        "description": str(_h.description or "Holiday"),
                        "type": str(_h.holiday_type or "Holiday"),
                    }
            except Exception:
                pass

            # ── Assemble final cal_data ────────────────────────────
            _all_dates = set(list(_sessions_by_date.keys()) + list(_holidays.keys()))
            _cal_data = {}
            for _d in _all_dates:
                _day_sess = _sessions_by_date.get(_d, [])
                _day_hol  = _holidays.get(_d)
                _cal_data[_d] = {
                    "has_present":   any(s["status"] == "Present" for s in _day_sess),
                    "has_absent":    any(s["status"] == "Absent" for s in _day_sess),
                    "has_scheduled": any(s["status"] == "Scheduled" for s in _day_sess),
                    "is_holiday":    bool(_day_hol),
                    "holiday_name":  (_day_hol.get("description", "") if _day_hol else ""),
                    "holiday_type":  (_day_hol.get("type", "") if _day_hol else ""),
                    "sessions":      _day_sess,
                }
            # Holiday-only dates (no attendance on that day)
            for _d, _h in _holidays.items():
                if _d not in _cal_data:
                    _cal_data[_d] = {
                        "has_present": False, "has_absent": False, "has_scheduled": False,
                        "is_holiday": True,
                        "holiday_name": _h["description"],
                        "holiday_type": _h["type"],
                        "sessions": [],
                    }

            context.attendance_calendar_json = json.dumps(_cal_data, default=str)
        except Exception:
            context.attendance_calendar_json = "{}"

        context.calendar_today = str(today_date)

    except Exception as e:
        frappe.log_error(f"Student Portal Attendance error: {e}", "Student Portal")
        context.portal_error = str(e)
        _set_nav_defaults(context)
        _set_defaults(context)

    return context


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_student_name():
    user = frappe.session.user
    name = frappe.db.get_value("Student Master", {"user": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"email": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
    return name


def _fmt_time(t):
    """Convert a Time/timedelta value to 12-hour format string."""
    if not t:
        return ""
    try:
        if hasattr(t, "seconds"):   # timedelta (Frappe stores Time as timedelta)
            total = int(t.seconds)
            h, rem = divmod(total, 3600)
            m = rem // 60
        else:
            parts = str(t).split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
        suffix = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {suffix}"
    except Exception:
        return str(t)


def _fmt_datetime_time(dt):
    """Extract and format just the time part from a Datetime value."""
    if not dt:
        return ""
    try:
        dt_str = str(dt)
        # Datetime comes as "2026-04-10 09:30:00" or "09:30:00"
        time_part = dt_str.split(" ")[1] if " " in dt_str else dt_str
        parts = time_part.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        suffix = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {suffix}"
    except Exception:
        return ""


def _set_defaults(context):
    context.allow_condonation = True
    context.min_condonation_pct = 66.0
    context.condonation_reasons = []
    context.student_cos = []
    context.attendance_summaries = []
    context.term_groups = []
    context.condonation_applications = []
    context.oh_groups = []
    context.cp_groups = []
    context.recent_attendance = []
    context.attendance_calendar_json = "{}"
    context.calendar_today = ""
    context.avg_attendance = 0.0
    context.total_courses = 0
    context.courses_below_75 = 0
    context.courses_eligible = 0


def _set_student_nav(context, student):
    full_name = " ".join(
        filter(None, [student.first_name, student.middle_name, student.last_name])
    )
    context.student_name = full_name or student.name
    context.student_id = student.registration_id or student.name
    context.student_photo = student.passport_size_photo or ""
    context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
    context.programme_name = (
        frappe.db.get_value("Batch", student.programme, "cohort_name")
        or student.programme
        or ""
    )
    context.department = student.department or ""
    context.batch_year = student.batch_year or ""


def _set_nav_defaults(context):
    user = frappe.session.user
    user_doc = frappe.db.get_value(
        "User", user, ["full_name", "user_image"], as_dict=True
    )
    context.student_name = (user_doc.full_name if user_doc else "") or user.split("@")[0]
    context.student_id = ""
    context.student_photo = (user_doc.user_image if user_doc else "") or ""
    context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
    context.programme_name = ""
    context.department = ""
    context.batch_year = ""

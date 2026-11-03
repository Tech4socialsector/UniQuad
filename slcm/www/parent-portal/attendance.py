import frappe
import json
from datetime import timedelta
from slcm.slcm.utils.parent_portal import get_parent_context

no_cache = 1


def get_context(context):
    student = get_parent_context(context)
    if context.is_guest or context.not_a_parent or not student:
        _set_defaults(context)
        return context

    context.active_page = "attendance"

    # ── Colour thresholds ──────────────────────────────────────────
    ps = context.pp_settings or {}
    context.att_good         = float(ps.get("att_good_threshold", 75))
    context.att_warn         = float(ps.get("att_warn_threshold", 60))
    context.att_label_good   = ps.get("att_label_good",   "Good")
    context.att_label_warn   = ps.get("att_label_warn",   "Low")
    context.att_label_danger = ps.get("att_label_danger", "Critical")

    # ── Attendance Summaries ───────────────────────────────────────
    summaries = frappe.get_all(
        "Attendance Summary",
        filters={"student": student.name},
        fields=[
            "name", "class_name", "course", "department",
            "academic_year", "academic_term",
            "total_classes", "attended_classes",
            "total_class_hours", "total_attended_class_hours",
            "attendance_percentage", "minimum_required_percentage",
            "eligible_for_exam", "last_updated",
        ],
        order_by="academic_term desc, class_name asc",
        ignore_permissions=True,
    )

    for s in summaries:
        co_name = s.class_name or ""
        s["term_name"] = s.academic_term or ""
        s["course_display"] = s.course or co_name or "Unknown"
        s["faculty"] = "—"
        if co_name:
            try:
                co = frappe.db.get_value(
                    "Classes", co_name,
                    ["course_name", "faculty", "faculty_name", "academic_term"], as_dict=True,
                )
                if co:
                    s["course_display"] = co.course_name or s["course_display"]
                    s["faculty"] = co.faculty_name or co.faculty or "—"
                    if not s["term_name"]:
                        s["term_name"] = co.academic_term or ""
            except Exception:
                pass

        pct = float(s.attendance_percentage or 0)
        req = float(s.minimum_required_percentage or 75)
        s["pct"] = round(pct, 1)
        s["status_color"] = (
            "var(--pp-success)" if pct >= context.att_good
            else "var(--pp-warning)" if pct >= context.att_warn
            else "var(--pp-danger)"
        )
        s["status_label"] = (
            context.att_label_good if pct >= context.att_good
            else context.att_label_warn if pct >= context.att_warn
            else context.att_label_danger
        )
        s["status_bg"] = (
            "var(--pp-success-bg)" if pct >= context.att_good
            else "var(--pp-warning-bg)" if pct >= context.att_warn
            else "var(--pp-danger-bg)"
        )
        s["shortfall"] = max(0, round(req - pct, 1))

    context.attendance_summaries = summaries

    # ── Overall stats ──────────────────────────────────────────────
    if summaries:
        pcts = [float(s.attendance_percentage or 0) for s in summaries]
        context.avg_attendance = round(sum(pcts) / len(pcts), 1)
        context.total_courses = len(summaries)
        context.courses_below_75 = sum(1 for p in pcts if p < context.att_good)
        context.courses_eligible = sum(1 for s in summaries if s.eligible_for_exam)
    else:
        context.avg_attendance = 0.0
        context.total_courses = 0
        context.courses_below_75 = 0
        context.courses_eligible = 0

    # ── Group by term ──────────────────────────────────────────────
    term_groups = {}
    for s in summaries:
        term = s.term_name or "Other"
        term_groups.setdefault(term, []).append(s)
    context.term_groups = [{"term": t, "summaries": v} for t, v in term_groups.items()]

    # ── Calendar JSON (same structure as Student Portal) ───────────
    today_date = frappe.utils.today()
    context.calendar_today = str(today_date)

    try:
        _today_d    = frappe.utils.getdate(today_date)
        _first_this = _today_d.replace(day=1)
        _first_prev = (_first_this - timedelta(days=1)).replace(day=1)
        _first_next = (_first_this.replace(day=28) + timedelta(days=4)).replace(day=1)
        _last_next  = (_first_next.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        _cal_start  = str(_first_prev)
        _cal_end    = str(_last_next)

        # Fetch attendance records for 3-month window
        _cal_att = frappe.get_all(
            "Student Attendance",
            filters=[
                ["student",         "=",  student.name],
                ["attendance_date", ">=", _cal_start],
                ["attendance_date", "<=", _cal_end],
            ],
            fields=[
                "attendance_date", "class_name", "course", "status",
                "in_time", "out_time", "session_type", "hours_counted",
                "class_schedule", "instructor", "room",
            ],
            order_by="attendance_date asc",
            ignore_permissions=True,
        )

        # Batch-fetch Time Table for from/to times
        _cs_ids = {str(r.class_schedule) for r in _cal_att if r.class_schedule}
        _cs_map = {}
        if _cs_ids:
            _cs_rows = frappe.get_all(
                "Time Table",
                filters={"name": ["in", list(_cs_ids)]},
                fields=["name", "from_time", "to_time", "venue"],
                ignore_permissions=True,
            )
            _cs_map = {r.name: r for r in _cs_rows}

        # Course name map from summaries already resolved above
        _summary_display_map = {
            s.class_name: s.get("course_display", "")
            for s in summaries if s.class_name
        }
        _summary_faculty_map = {
            s.class_name: s.get("faculty", "")
            for s in summaries if s.class_name
        }

        # Batch-fetch any classes not in summaries
        _co_ids = {
            str(r.class_name) for r in _cal_att
            if r.class_name and str(r.class_name) not in _summary_display_map
        }
        _co_extra_map = {}
        if _co_ids:
            _co_extra_rows = frappe.get_all(
                "Classes",
                filters={"name": ["in", list(_co_ids)]},
                fields=["name", "course_name", "faculty_name as faculty"],
                ignore_permissions=True,
            )
            _co_extra_map = {r.name: r for r in _co_extra_rows}

        # Build sessions per date
        _sessions_by_date = {}
        for r in _cal_att:
            _d       = str(r.attendance_date)
            _cs      = _cs_map.get(str(r.class_schedule or ""), frappe._dict())
            _co_id   = str(r.class_name or "")
            _co_ext  = _co_extra_map.get(_co_id, frappe._dict())

            _cname = (
                _summary_display_map.get(_co_id)
                or _co_ext.get("course_name")
                or str(r.course or _co_id or "—")
            )
            _instructor = str(
                _summary_faculty_map.get(_co_id)
                or _co_ext.get("faculty")
                or r.instructor or ""
            )
            _venue     = str(_cs.get("venue") or r.room or "")
            _from_time = _fmt_time(_cs.get("from_time")) if _cs.get("from_time") else ""
            _to_time   = _fmt_time(_cs.get("to_time"))   if _cs.get("to_time")   else ""
            _in_time   = _fmt_datetime_time(r.in_time)
            _out_time  = _fmt_datetime_time(r.out_time)

            _sessions_by_date.setdefault(_d, []).append({
                "course_name":     str(_cname),
                "class_name":      str(r.class_name or ""),
                "session_type":    str(r.session_type or "Lecture"),
                "from_time":       _from_time,
                "to_time":         _to_time,
                "instructor":      _instructor,
                "venue":           _venue,
                "status":          str(r.status or ""),
                "in_time":         _in_time,
                "out_time":        _out_time,
                "hours":           float(r.hours_counted or 0),
            })

        # Sort each day's sessions by scheduled start time
        for _d in _sessions_by_date:
            _sessions_by_date[_d].sort(key=lambda x: x["from_time"] or "")

        # Fetch holidays
        _holidays = {}
        try:
            _hol_rows = frappe.get_all(
                "Academic Holiday",
                filters=[
                    ["holiday_date", ">=", _cal_start],
                    ["holiday_date", "<=", _cal_end],
                ],
                fields=["holiday_date", "description", "holiday_type"],
                ignore_permissions=True,
            )
            for h in _hol_rows:
                _holidays[str(h.holiday_date)] = {
                    "description": str(h.description or "Holiday"),
                    "type":        str(h.holiday_type or "Holiday"),
                }
        except Exception:
            pass

        # Assemble final cal_data
        _all_dates = set(list(_sessions_by_date.keys()) + list(_holidays.keys()))
        _cal_data = {}
        for _d in _all_dates:
            _day_sess = _sessions_by_date.get(_d, [])
            _day_hol  = _holidays.get(_d)
            _cal_data[_d] = {
                "has_present":   any(s["status"] == "Present"   for s in _day_sess),
                "has_absent":    any(s["status"] == "Absent"    for s in _day_sess),
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

    return context


# ── Helpers ────────────────────────────────────────────────────────

def _fmt_time(t):
    """Convert a Time/timedelta value to 12-hour format string."""
    if not t:
        return ""
    try:
        if hasattr(t, "seconds"):
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
    context.attendance_summaries = []
    context.avg_attendance = 0.0
    context.total_courses = 0
    context.courses_below_75 = 0
    context.courses_eligible = 0
    context.term_groups = []
    context.att_good = 75.0
    context.att_warn = 60.0
    context.att_label_good   = "Good"
    context.att_label_warn   = "Low"
    context.att_label_danger = "Critical"
    context.attendance_calendar_json = "{}"
    context.calendar_today = str(frappe.utils.today())
    if not getattr(context, "pp_settings", None):
        from slcm.slcm.doctype.parent_portal_settings.parent_portal_settings import get_parent_portal_settings
        try:
            context.pp_settings = get_parent_portal_settings()
        except Exception:
            context.pp_settings = {}

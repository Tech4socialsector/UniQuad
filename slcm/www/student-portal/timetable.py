import frappe
from datetime import timedelta, date, datetime
import calendar

no_cache = 1

# Palette – one colour per enrolled course_offering (cycles if > 10)
_PALETTE = [
    "#920c24", "#3b82f6", "#10b981", "#6b091a", "#8b5cf6",
    "#ec4899", "#06b6d4", "#84cc16", "#b5364a", "#6366f1",
]


def get_context(context):
    context.no_cache = 1

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest    = False
    context.active_page = "timetable"

    student_name = _get_student_name()
    if not student_name:
        context.no_student = True
        _set_nav_defaults(context)
        return context

    context.no_student = False

    try:
        student = frappe.get_doc("Student Master", student_name)
        _set_student_nav(context, student)

        # ── Filters & View ───────────────────────────────────────
        today      = frappe.utils.getdate()
        view_param = frappe.local.form_dict.get("view", "week")
        course_param = frappe.local.form_dict.get("course", "all")
        from_date_param = frappe.local.form_dict.get("from_date", "")
        to_date_param = frappe.local.form_dict.get("to_date", "")

        context.view = view_param
        context.selected_course = course_param

        # Determine Date Bounds
        if view_param == "month":
            if from_date_param:
                try:
                    target_date = frappe.utils.getdate(from_date_param)
                except:
                    target_date = today
            else:
                target_date = today
            
            # Start of month and end of month
            week_start = target_date.replace(day=1)
            last_day = calendar.monthrange(week_start.year, week_start.month)[1]
            week_end = target_date.replace(day=last_day)
            
            context.month_name = week_start.strftime("%B %Y")
            context.prev_date = str((week_start - timedelta(days=1)).replace(day=1))
            context.next_date = str((week_end + timedelta(days=1)).replace(day=1))

        elif view_param == "day":
            if from_date_param:
                try:
                    target_date = frappe.utils.getdate(from_date_param)
                except:
                    target_date = today
            else:
                target_date = today
                
            week_start = target_date
            week_end = target_date
            
            context.prev_date = str(target_date - timedelta(days=1))
            context.next_date = str(target_date + timedelta(days=1))
            
        else:
            # Week View
            if from_date_param and to_date_param:
                try:
                    week_start = frappe.utils.getdate(from_date_param)
                    week_end = frappe.utils.getdate(to_date_param)
                except:
                    week_start = today - timedelta(days=today.weekday())
                    week_end = week_start + timedelta(days=5)
            elif from_date_param:
                try:
                    raw = frappe.utils.getdate(from_date_param)
                    week_start = raw - timedelta(days=raw.weekday())
                    week_end = week_start + timedelta(days=5)
                except:
                    week_start = today - timedelta(days=today.weekday())
                    week_end = week_start + timedelta(days=5)
            else:
                week_start = today - timedelta(days=today.weekday())
                week_end = week_start + timedelta(days=5) # Mon-Sat

            context.prev_date = str(week_start - timedelta(days=7))
            context.next_date = str(week_start + timedelta(days=7))

        context.week_start    = week_start
        context.week_end      = week_end
        context.today         = today
        context.is_current_week = (week_start <= today <= week_end)
        
        # Display label
        if view_param == "day":
            context.date_label = week_start.strftime('%d %b %Y')
        elif week_start.month == week_end.month:
            context.date_label = f"{week_start.strftime('%d')} - {week_end.strftime('%d %b %Y')}"
        else:
            context.date_label = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}"
        
        # Pass formatted strings for the date picker (DD/MM/YYYY)
        context.from_date_fmt = week_start.strftime("%d/%m/%Y")
        context.to_date_fmt = week_end.strftime("%d/%m/%Y")
        
        # Pass ISO strings for URLs
        context.from_date_iso = str(week_start)
        context.to_date_iso = str(week_end)


        # ── Enrolled course offerings ─────────────────────────────
        att_summaries = frappe.get_all(
            "Attendance Summary",
            filters={"student": student_name},
            fields=["course_offering", "course"],
            ignore_permissions=True,
        )
        enrolled_co_set = {s.course_offering for s in att_summaries if s.course_offering}

        # Build colour map (stable order → stable colours)
        color_map = {}
        for i, co in enumerate(sorted(enrolled_co_set)):
            color_map[co] = _PALETTE[i % len(_PALETTE)]

        # ── Fetch Time Table entries for the week ────────────────────
        raw_schedules = []
        if enrolled_co_set:
            filters = [
                ["course_offering", "in", list(enrolled_co_set)],
                ["schedule_date", "between", [str(week_start), str(week_end)]],
            ]
            if course_param and course_param != "all":
                filters.append(["course_offering", "=", course_param])

            raw_schedules = frappe.get_all(
                "Time Table",
                filters=filters,
                fields=["name", "course", "course_offering", "instructor",
                        "schedule_date", "from_time", "to_time", "duration_hours",
                        "venue", "title", "color"],
                order_by="schedule_date asc, from_time asc",
                ignore_permissions=True,
            )

            # ── Also handle weekly-repeating parent schedules ─────
            try:
                rec_filters = [
                    ["course_offering", "in", list(enrolled_co_set)],
                    ["repeat_frequency", "=", "Weekly"],
                    ["schedule_date", "<=", str(week_end)],
                    ["parent_schedule", "is", "not set"],
                ]
                if course_param and course_param != "all":
                    rec_filters.append(["course_offering", "=", course_param])

                recurring = frappe.get_all(
                    "Time Table",
                    filters=rec_filters,
                    fields=["name", "course", "course_offering", "instructor",
                            "schedule_date", "from_time", "to_time", "duration_hours",
                            "venue", "title", "color", "repeats_till"],
                    ignore_permissions=True,
                )
                for r in recurring:
                    orig = frappe.utils.getdate(r.schedule_date)
                    curr = week_start
                    while curr <= week_end:
                        if curr.weekday() == orig.weekday() and curr >= orig:
                            till = frappe.utils.getdate(r.repeats_till) if r.repeats_till else None
                            if not till or curr <= till:
                                already = any(
                                    frappe.utils.getdate(s.schedule_date) == curr
                                    and s.course_offering == r.course_offering
                                    and str(s.from_time) == str(r.from_time)
                                    for s in raw_schedules
                                )
                                if not already:
                                    copy = frappe._dict(r)
                                    copy.schedule_date = curr
                                    raw_schedules.append(copy)
                        curr += timedelta(days=1)
                        
            except Exception:
                pass

        # ── Enrich with course display names ──────────────────────
        co_names = {s.course_offering for s in raw_schedules if s.course_offering}
        co_info_map = {}
        if enrolled_co_set:
            rows = frappe.get_all(
                "Course Offering",
                filters={"name": ["in", list(enrolled_co_set)]},
                fields=["name", "course_name", "faculty"],
                ignore_permissions=True,
            )
            co_info_map = {r.name: r for r in rows}

        # ── Enrich with Faculty names ──────────────────────────────
        faculty_names = {}
        unique_faculties = {s.instructor for s in raw_schedules if s.instructor}
        if unique_faculties:
            try:
                facs = frappe.get_all("Faculty", filters={"name": ["in", list(unique_faculties)]}, fields=["name", "first_name", "last_name"])
                faculty_names = {f.name: f"{f.first_name or ''} {f.last_name or ''}".strip() for f in facs}
            except Exception as e:
                frappe.log_error(f"Timetable Faculty Lookup error: {e}", "Student Portal Timetable")
            
        # ── Group by day ──────────────────────────────────────────
        if view_param == "month":
            days = _build_month_days(week_start)
        elif view_param == "day":
            days = _build_single_day(week_start)
        else:
            days = _build_days(week_start)
            
        schedules_by_day = {d["date"]: [] for d in days}

        for s in raw_schedules:
            d     = frappe.utils.getdate(s.schedule_date)
            d_str = str(d)
            if d_str not in schedules_by_day:
                continue
            co   = co_info_map.get(s.course_offering, frappe._dict())
            name = (
                co.get("course_name")
                or s.get("title")
                or s.course
                or s.course_offering
                or "—"
            )
            
            top_px = 0
            height_px = 60
            from_str = ""
            to_str = ""
            if s.from_time:
                h, m = _parse_time(s.from_time)
                top_px = ((h - 8) * 60) + m
                top_px = max(0, top_px)
                from_str = _fmt_parsed(h, m)
            if s.to_time and s.from_time:
                eh, em = _parse_time(s.to_time)
                duration_mins = (eh * 60 + em) - (h * 60 + m)
                height_px = max(20, duration_mins)
                to_str = _fmt_parsed(eh, em)
            
            course_code = s.course or s.course_offering

            schedules_by_day[d_str].append({
                "name":           s.name,
                "course_offering": s.course_offering or "",
                "course":         course_code,
                "course_name":    name,
                "instructor":     faculty_names.get(s.instructor) or s.instructor or co.get("faculty") or "—",
                "from_time":      from_str,
                "to_time":        to_str,
                "top_px":         top_px,
                "height_px":      height_px,
                "venue":          s.venue or "—",
                "color":          color_map.get(s.course_offering) or s.color or _PALETTE[0],
            })

        # ── Clustering for Overlap ─────────────────────────────────
        for d_str, evs in schedules_by_day.items():
            evs.sort(key=lambda x: (x["top_px"], -x["height_px"]))
            
            clusters = []
            for ev in evs:
                ev_start = ev["top_px"]
                ev_end = ev_start + ev["height_px"]
                
                placed = False
                if clusters:
                    last_cluster = clusters[-1]
                    cluster_end = max((e["top_px"] + e["height_px"]) for e in last_cluster)
                    if ev_start < cluster_end:
                        last_cluster.append(ev)
                        placed = True
                
                if not placed:
                    clusters.append([ev])
                    
            for cluster in clusters:
                col_count = len(cluster)
                for col_index, ev in enumerate(cluster):
                    ev["left_pct"] = (col_index / col_count) * 100
                    ev["width_pct"] = (100 / col_count) - 1

        context.days             = days
        context.schedules_by_day = schedules_by_day
        context.color_map        = color_map
        context.total_this_week  = sum(len(v) for v in schedules_by_day.values())
        context.today_count      = len(schedules_by_day.get(str(today), []))

        # ── Unique course list (for filters) ───────────────────────
        context.all_courses = []
        for co_id, co_data in co_info_map.items():
            context.all_courses.append({
                "id": co_id,
                "name": co_data.get("course_name") or co_id
            })
        context.all_courses.sort(key=lambda x: x["name"])

    except Exception as exc:
        frappe.log_error(f"Timetable error: {exc}", "Student Portal Timetable")
        context.portal_error = str(exc)
        _set_nav_defaults(context)

    return context


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_single_day(day_date):
    name = day_date.strftime("%A")
    return [{
        "date":  str(day_date),
        "label": name,
        "short": name[:3].upper(),
        "num":   day_date.day,
        "month": day_date.strftime("%b"),
        "is_today": day_date == frappe.utils.getdate()
    }]


def _build_days(week_start):
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    days  = []
    for i, name in enumerate(names):
        d = week_start + timedelta(days=i)
        days.append({
            "date":  str(d),
            "label": name,
            "short": name[:3].upper(),
            "num":   d.day,
            "month": d.strftime("%b"),
            "is_today": d == frappe.utils.getdate()
        })
    return days

def _build_month_days(month_start):
    cal = calendar.Calendar(firstweekday=0) # Monday start
    days = []
    for d in cal.itermonthdates(month_start.year, month_start.month):
        days.append({
            "date": str(d),
            "num": d.day,
            "is_current_month": d.month == month_start.month,
            "is_today": d == frappe.utils.getdate()
        })
    return days

def _parse_time(t):
    if hasattr(t, "seconds"):
        total = int(t.seconds)
        h, rem = divmod(total, 3600)
        m = rem // 60
        return h, m
    elif isinstance(t, str):
        parts = t.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return h, m
    return 0, 0

def _fmt_parsed(h, m):
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def _get_student_name():
    user = frappe.session.user
    name = frappe.db.get_value("Student Master", {"user": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"email": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
    return name


def _set_student_nav(context, student):
    full = " ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))
    context.student_name    = full or student.name
    context.student_id      = student.registration_id or student.name
    context.student_photo   = student.passport_size_photo or ""
    context.student_initial = context.student_name[0].upper() if context.student_name else "S"
    context.programme_name  = (
        frappe.db.get_value("Batch", student.programme, "cohort_name")
        or student.programme or ""
    )
    context.department = student.department or ""
    context.batch_year = student.batch_year or ""
    context.official_email_id = student.official_email_id or ""
    context.personal_email    = student.personal_email or ""


def _set_nav_defaults(context):
    user     = frappe.session.user
    user_doc = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True)
    context.student_name    = (user_doc.full_name if user_doc else "") or user.split("@")[0]
    context.student_id      = ""
    context.student_photo   = (user_doc.user_image if user_doc else "") or ""
    context.student_initial = context.student_name[0].upper() if context.student_name else "S"
    context.programme_name  = ""
    context.department      = ""
    context.batch_year      = ""

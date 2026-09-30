import frappe

no_cache = 1


def get_context(context):
    context.no_cache = 1

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "exam_schedule"

    student_name = _get_student_name()
    if not student_name:
        context.no_student = True
        _set_nav_defaults(context)
        context.exam_plans = []
        context.has_exam_plans = False
        context.total_exams = 0
        context.total_courses = 0
        context.eligible_courses = 0
        context.upcoming_exams = 0
        context.next_exam_date = "–"
        context.next_exam_course = ""
        context.results_published = 0
        context.reexam_requests = 0
        return context

    context.no_student = False

    try:
        student = frappe.get_doc("Student Master", student_name)
        _set_student_nav(context, student)

        marks_rows = frappe.get_all(
            "Student Course Marks",
            filters={"student": student_name},
            fields=["name", "exam_plan", "course", "attendance_status", "enrollment_status", "status"],
            order_by="modified desc",
            ignore_permissions=True,
        )

        publish_rows = frappe.get_all(
            "Student Result Publish",
            filters={"student": student_name},
            fields=["exam_plan", "is_published", "published_on"],
            ignore_permissions=True,
        )
        published_map = {row.exam_plan: row for row in publish_rows}

        grouped = {}
        for row in marks_rows:
            grouped.setdefault(row.exam_plan, []).append(row)

        # Get the student's enrolled courses to match against exam plans
        enrolled_courses = set(row.course for row in marks_rows)

        # Also include any Active exam plan whose course_schedules contain
        # at least one course this student is enrolled in — this covers plans
        # that exist but where Student Course Marks haven't been created yet.
        all_active_plans = frappe.get_all(
            "Exam Plan",
            filters={"status": "Active"},
            fields=["name"],
            order_by="modified desc",
            limit=50,
            ignore_permissions=True,
        )
        for plan in all_active_plans:
            if plan.name in grouped:
                continue  # already have marks for this plan
            plan_courses = frappe.get_all(
                "Exam Course Schedule",
                filters={"parent": plan.name, "parenttype": "Exam Plan"},
                fields=["course"],
                ignore_permissions=True,
            )
            plan_course_set = {r.course for r in plan_courses}
            # Show plan if: student has matching enrolled courses, OR no marks exist at all
            if (not enrolled_courses and plan_course_set) or (enrolled_courses & plan_course_set):
                grouped.setdefault(plan.name, [])

        exam_plans = []
        for exam_plan, rows in grouped.items():
            ep = frappe.db.get_value(
                "Exam Plan",
                exam_plan,
                ["exam_name", "term", "status"],
                as_dict=True,
            ) or frappe._dict()
            pub = published_map.get(exam_plan)

            # Build per-course schedule map from child table
            schedule_rows = frappe.get_all(
                "Exam Course Schedule",
                filters={"parent": exam_plan, "parenttype": "Exam Plan"},
                fields=["course", "exam_date", "start_time", "end_time", "venue", "hall"],
                ignore_permissions=True,
            )
            schedule_map = {s.course: s for s in schedule_rows}

            courses = []
            if rows:
                # Build courses from Student Course Marks (normal path)
                for row in rows:
                    actual_course = frappe.db.get_value("Course Offering", row.course, "course") or row.course
                    c_doc = frappe.db.get_value("Course", actual_course, ["course_name", "course_code"], as_dict=True) or {}
                    course_name = c_doc.get("course_name") or actual_course
                    course_code = c_doc.get("course_code") or actual_course
                    
                    att = _get_attendance(row, student_name, exam_plan)
                    sched = schedule_map.get(row.course) or frappe._dict()
                    exam_date_str = frappe.utils.formatdate(sched.exam_date, "d MMM yyyy") if sched.exam_date else ""
                    start = _fmt_time(sched.start_time) if sched.start_time else ""
                    end = _fmt_time(sched.end_time) if sched.end_time else ""
                    exam_time = f"{start} – {end}" if start and end else (start or "To be announced")
                    venue_str = " | ".join(filter(None, [sched.venue, sched.hall])) or "To be announced"
                    courses.append({
                        "course": row.course,
                        "course_code": course_code,
                        "course_name": course_name,
                        "attendance_status": att,
                        "enrollment_status": row.enrollment_status or "Enrolled",
                        "marks_status": row.status or "Draft",
                        "hall_ticket_status": _hall_ticket_status(att, row.enrollment_status),
                        "exam_date": exam_date_str,
                        "_raw_exam_date": sched.exam_date,
                        "venue": venue_str,
                        "exam_time": exam_time,
                        "has_schedule": bool(sched.exam_date or sched.venue),
                    })
            else:
                # No Student Course Marks yet — build course list directly from
                # the Exam Plan's course_schedules child table so the timetable
                # is still visible to students before marks are created.
                for sched in schedule_rows:
                    actual_course = frappe.db.get_value("Course Offering", sched.course, "course") or sched.course
                    c_doc = frappe.db.get_value("Course", actual_course, ["course_name", "course_code"], as_dict=True) or {}
                    course_name = c_doc.get("course_name") or actual_course
                    course_code = c_doc.get("course_code") or actual_course
                    
                    exam_date_str = frappe.utils.formatdate(sched.exam_date, "d MMM yyyy") if sched.exam_date else ""
                    start = _fmt_time(sched.start_time) if sched.start_time else ""
                    end = _fmt_time(sched.end_time) if sched.end_time else ""
                    exam_time = f"{start} – {end}" if start and end else (start or "To be announced")
                    venue_str = " | ".join(filter(None, [sched.venue, sched.hall])) or "To be announced"
                    courses.append({
                        "course": sched.course,
                        "course_code": course_code,
                        "course_name": course_name,
                        "attendance_status": "",
                        "enrollment_status": "Enrolled",
                        "marks_status": "Draft",
                        "hall_ticket_status": "Eligible",
                        "exam_date": exam_date_str,
                        "_raw_exam_date": sched.exam_date,
                        "venue": venue_str,
                        "exam_time": exam_time,
                        "has_schedule": bool(sched.exam_date or sched.venue),
                    })

            courses.sort(key=lambda c: c["course_name"])
            exam_plans.append({
                "name": exam_plan,
                "exam_name": ep.exam_name or exam_plan,
                "term": ep.term or "",
                "status": ep.status or "Active",
                "is_published": bool(pub and pub.is_published),
                "published_on": pub.published_on if pub else None,
                "courses": courses,
                "course_count": len(courses),
                "eligible_count": sum(1 for c in courses if c["hall_ticket_status"] == "Eligible"),
            })

        # Sort: published first (is_published=True → 0), then alphabetically by name
        exam_plans.sort(key=lambda row: (not row["is_published"], row["exam_name"]))
        context.exam_plans = exam_plans
        context.has_exam_plans = bool(exam_plans)
        context.total_exams = len(exam_plans)
        context.total_courses = sum(row["course_count"] for row in exam_plans)
        context.eligible_courses = sum(row["eligible_count"] for row in exam_plans)

        # Tag upcoming courses and compute overview stats in one pass
        from datetime import date as _date
        _today = _date.today()
        upcoming_count = 0
        next_exam_date = None
        next_exam_course = None
        for plan in exam_plans:
            for course in plan["courses"]:
                raw = course.get("_raw_exam_date")
                is_up = bool(raw and raw >= _today)
                course["is_upcoming"] = is_up
                if is_up:
                    upcoming_count += 1
                    if next_exam_date is None or raw < next_exam_date:
                        next_exam_date = raw
                        next_exam_course = course.get("course_name", "")

        context.upcoming_exams = upcoming_count
        context.next_exam_date = (
            frappe.utils.formatdate(next_exam_date, "d MMM yyyy") if next_exam_date else "–"
        )
        context.next_exam_course = next_exam_course or ""
        context.results_published = sum(1 for p in exam_plans if p["is_published"])

        # Re-exam requests count
        try:
            reexam_count = frappe.db.count(
                "Re-Examination Request",
                filters={"student": student_name, "status": ["in", ["Pending", "Approved", "Submitted"]]},
            )
        except Exception:
            reexam_count = 0
        context.reexam_requests = reexam_count

    except Exception as exc:
        frappe.log_error(f"Exam Schedule error: {exc}", "Student Portal Exam Schedule")
        context.portal_error = str(exc)
        _set_nav_defaults(context)
        context.exam_plans = []
        context.has_exam_plans = False
        context.total_exams = 0
        context.total_courses = 0
        context.eligible_courses = 0
        context.upcoming_exams = 0
        context.next_exam_date = "–"
        context.next_exam_course = ""
        context.results_published = 0
        context.reexam_requests = 0

    return context


def _get_attendance(row, student_name, exam_plan):
    if row.attendance_status:
        return row.attendance_status
    summary = frappe.db.get_value(
        "Attendance Summary",
        {"student": student_name, "course": row.course},
        ["attendance_percentage", "eligible_for_exam", "student_status"],
        as_dict=True,
    )
    if not summary:
        summary = frappe.db.get_value(
            "Attendance Summary",
            {"student": student_name, "course": row.course, "exam_plan": exam_plan},
            ["attendance_percentage", "eligible_for_exam", "student_status"],
            as_dict=True,
        )
    if not summary:
        return ""
    if summary.student_status:
        return summary.student_status
    if summary.eligible_for_exam:
        return "Present"
    return "Detained" if float(summary.attendance_percentage or 0) < 75 else "Present"


def _fmt_time(t):
    if t is None:
        return ""
    if hasattr(t, "seconds"):
        total = int(t.seconds)
        h, rem = divmod(total, 3600)
        m = rem // 60
    elif isinstance(t, str):
        parts = t.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    else:
        return str(t)
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def _hall_ticket_status(attendance_status, enrollment_status):
    if enrollment_status in {"Dropped", "Detained"}:
        return "Blocked"
    if attendance_status in {"Detained", "Absent", "Low Attendance"}:
        return "Blocked"
    return "Eligible"


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
    context.student_name = full or student.name
    context.student_id = student.registration_id or student.name
    context.student_photo = student.passport_size_photo or ""
    context.student_initial = context.student_name[0].upper() if context.student_name else "S"
    context.programme_name = (
        frappe.db.get_value("Batch", student.programme, "cohort_name")
        or student.programme or ""
    )
    context.department = student.department or ""
    context.batch_year = student.batch_year or ""


def _set_nav_defaults(context):
    user = frappe.session.user
    user_doc = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True)
    context.student_name = (user_doc.full_name if user_doc else "") or user.split("@")[0]
    context.student_id = ""
    context.student_photo = (user_doc.user_image if user_doc else "") or ""
    context.student_initial = context.student_name[0].upper() if context.student_name else "S"
    context.programme_name = ""
    context.department = ""
    context.batch_year = ""


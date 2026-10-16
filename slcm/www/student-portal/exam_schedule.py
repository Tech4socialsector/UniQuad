import frappe
from slcm.slcm.utils.exam_schedule import get_visible_exam_plans

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

        # Only the exam plans / courses the student is enrolled in (same
        # source as the Courses page) — see slcm.slcm.utils.exam_schedule
        visible = get_visible_exam_plans(student_name)

        marks_rows = frappe.get_all(
            "Student Course Marks",
            filters={"student": student_name, "exam_plan": ["in", list(visible) or ["__none__"]]},
            fields=["name", "exam_plan", "course", "attendance_status", "enrollment_status", "status"],
            order_by="modified desc",
            ignore_permissions=True,
        )
        marks_map = {}
        for row in marks_rows:
            marks_map.setdefault((row.exam_plan, row.course), row)   # newest first

        published_map = {
            row.exam_plan: row
            for row in frappe.get_all(
                "Student Result Publish",
                filters={"student": student_name},
                fields=["exam_plan", "is_published", "published_on"],
                ignore_permissions=True,
            )
        }

        exam_plans = []
        for exam_plan, plan_courses in visible.items():
            ep = frappe.db.get_value(
                "Exam Plan",
                exam_plan,
                ["exam_name", "term", "status"],
                as_dict=True,
            ) or frappe._dict()
            pub = published_map.get(exam_plan)

            schedule_map = {
                s.course: s
                for s in frappe.get_all(
                    "Exam Course Schedule",
                    filters={"parent": exam_plan, "parenttype": "Exam Plan"},
                    fields=["course", "exam_date", "start_time", "end_time", "venue", "hall"],
                    ignore_permissions=True,
                )
            }

            courses = []
            for course in plan_courses:
                c_doc = frappe.db.get_value("Course", course, ["course_name", "course_code"], as_dict=True) or {}
                row = marks_map.get((exam_plan, course))
                att = _get_attendance(row, student_name, exam_plan) if row else ""
                sched = schedule_map.get(course) or frappe._dict()
                start = _fmt_time(sched.start_time) if sched.start_time else ""
                end = _fmt_time(sched.end_time) if sched.end_time else ""
                courses.append({
                    "course": course,
                    "course_code": c_doc.get("course_code") or course,
                    "course_name": c_doc.get("course_name") or course,
                    "attendance_status": att,
                    "enrollment_status": (row.enrollment_status if row else "") or "Enrolled",
                    "marks_status": (row.status if row else "") or "Draft",
                    "hall_ticket_status": _hall_ticket_status(att, row.enrollment_status if row else None),
                    "exam_date": frappe.utils.formatdate(sched.exam_date, "d MMM yyyy") if sched.exam_date else "",
                    "_raw_exam_date": sched.exam_date,
                    "venue": " | ".join(filter(None, [sched.venue, sched.hall])) or "To be announced",
                    "exam_time": f"{start} – {end}" if start and end else (start or "To be announced"),
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

        _attach_assessments(exam_plans, student_name)

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

                # Assessments / submission deadlines from Exam Assessment Schedule
                for a in course.get("assessments", []):
                    nxt = a.get("_next_date")
                    if not nxt:
                        continue
                    upcoming_count += 1
                    if next_exam_date is None or nxt.date() < next_exam_date:
                        next_exam_date = nxt.date()
                        next_exam_course = f"{course.get('course_name', '')} · {a['label']}"

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


def _attach_assessments(exam_plans, student_name):
    """Attach Exam Assessment Schedule rows (assessment date + submission deadlines)
    to each course on the page, for the course offerings the student is enrolled in.
    Assessments whose term has no Exam Plan card get a card of their own."""
    # Match on course + programme + term rather than the exact Course Offering, so a
    # student enrolled in a duplicate offering of the same course still sees the schedule.
    rows = frappe.db.sql(
        """
        SELECT DISTINCT eas.term, item.course_offering, item.course, item.course_name,
               item.assessment_label, item.assessment_date,
               item.first_submission_deadline, item.second_submission_deadline, item.remarks,
               item.idx
        FROM `tabExam Assessment Schedule Item` item
        JOIN `tabExam Assessment Schedule` eas ON eas.name = item.parent
        JOIN `tabCourse Offering` co
          ON co.course_title = item.course
         AND co.program = eas.programme
         AND co.term_name = eas.term
        JOIN `tabStudent Enrollment Course` sec ON sec.course_offering = co.name
        JOIN `tabStudent Enrollment` se ON se.name = sec.parent
        WHERE item.parenttype = 'Exam Assessment Schedule'
          AND eas.status = 'Active'
          AND se.student = %(student)s
          AND se.status != 'Dropped'
          AND sec.status = 'Enrolled'
        ORDER BY item.course_name,
                 COALESCE(item.assessment_date, item.first_submission_deadline) IS NULL,
                 COALESCE(item.assessment_date, item.first_submission_deadline),
                 item.idx
        """,
        {"student": student_name},
        as_dict=True,
    )
    if not rows:
        return

    now = frappe.utils.now_datetime()
    plans_by_term = {}
    for plan in exam_plans:
        plans_by_term.setdefault(plan["term"], plan)

    for r in rows:
        plan = plans_by_term.get(r.term)
        if not plan:
            plan = {
                "name": f"assessments-{r.term}",
                "exam_name": "Assessments",
                "term": r.term,
                "status": "Active",
                "is_published": False,
                "published_on": None,
                "courses": [],
                "course_count": 0,
                "eligible_count": 0,
            }
            exam_plans.append(plan)
            plans_by_term[r.term] = plan

        course = next((c for c in plan["courses"] if c["course"] == r.course), None)
        if not course:
            c_doc = frappe.db.get_value("Course", r.course, ["course_name", "course_code"], as_dict=True) or {}
            course = {
                "course": r.course,
                "course_code": c_doc.get("course_code") or r.course,
                "course_name": c_doc.get("course_name") or r.course_name or r.course,
                "attendance_status": "",
                "enrollment_status": "Enrolled",
                "marks_status": "Draft",
                "hall_ticket_status": "Eligible",
                "exam_date": "",
                "_raw_exam_date": None,
                "venue": "To be announced",
                "exam_time": "To be announced",
                "has_schedule": False,
            }
            plan["courses"].append(course)
            plan["course_count"] += 1
            plan["eligible_count"] += 1

        course.setdefault("assessments", []).append(_assessment_entry(r, now))

    for plan in exam_plans:
        plan["courses"].sort(key=lambda c: c["course_name"])
        for course in plan["courses"]:
            upcoming = [a for a in course.get("assessments", []) if a["_next_date"]]
            if upcoming:
                nxt = min(upcoming, key=lambda a: a["_next_date"])
                course["next_assessment"] = {
                    "date": _fmt_dt(nxt["_next_date"]),
                    "label": nxt["label"],
                }


def _assessment_entry(r, now):
    start = frappe.utils.get_datetime(r.assessment_date) if r.assessment_date else None
    first = frappe.utils.get_datetime(r.first_submission_deadline) if r.first_submission_deadline else None
    second = frappe.utils.get_datetime(r.second_submission_deadline) if r.second_submission_deadline else None

    if first and now <= first:
        if (first - now).days < 3:
            status, tone = "Due Soon", "due"
        elif start and now < start:
            status, tone = "Upcoming", "upcoming"
        else:
            status, tone = "Open", "open"
    elif second and now <= second:
        status, tone = "2nd Submission Open", "due"
    elif first or second:
        status, tone = "Closed", "closed"
    elif start:
        status, tone = ("Upcoming", "upcoming") if now < start else ("Completed", "closed")
    else:
        status, tone = "To be announced", "tba"

    future = [d for d in (start, first, second) if d and d >= now]
    return {
        "label": r.assessment_label,
        "assessment_date": _fmt_dt(start),
        "first_deadline": _fmt_dt(first),
        "second_deadline": _fmt_dt(second),
        "remarks": r.remarks or "",
        "status": status,
        "tone": tone,
        "_next_date": min(future) if future else None,
    }


def _fmt_dt(dt):
    if not dt:
        return ""
    return frappe.utils.format_datetime(dt, "d MMM yyyy, h:mm a")


def _get_attendance(row, student_name, exam_plan):
    if row.attendance_status:
        return row.attendance_status
    summary = frappe.db.get_value(
        "Attendance Summary",
        {"student": student_name, "course": row.course},
        ["attendance_percentage", "eligible_for_exam", "minimum_required_percentage"],
        as_dict=True,
        order_by="modified desc",
    )
    if not summary:
        return ""
    if summary.eligible_for_exam:
        return "Present"
    minimum = float(summary.minimum_required_percentage or 75)
    return "Detained" if float(summary.attendance_percentage or 0) < minimum else "Present"


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


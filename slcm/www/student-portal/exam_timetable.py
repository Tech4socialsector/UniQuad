import importlib

import frappe
from frappe.utils import formatdate, getdate, today

from slcm.slcm.utils.exam_schedule import get_visible_exam_plans

# NOTE: Frappe maps exam-timetable.html → exam_timetable.py (hyphens become
# underscores). Shared helpers (student lookup, nav, room by ID range, time
# format) live on the Assessment Schedule page.
_es = importlib.import_module("slcm.www.student-portal.exam_schedule")

no_cache = 1


def get_context(context):
    """The student's exam timetable: end-term and re-exam papers of their courses,
    shown only once the Examinations Office publishes the plan's timetable.
    Continuing evaluation (quizzes, projects, deadlines) is on Assessment Schedule."""
    context.no_cache = 1

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "exam_timetable"
    context.plans = []
    context.upcoming_count = 0
    context.next_exam = None

    student_name = _es._get_student_name()
    if not student_name:
        context.no_student = True
        _es._set_nav_defaults(context)
        return context

    context.no_student = False
    try:
        _es._set_student_nav(context, frappe.get_doc("Student Master", student_name))
        plans = [_plan(plan, courses, student_name) for plan, courses in get_visible_exam_plans(student_name).items()]
        plans = [p for p in plans if p]
        plans.sort(key=lambda p: (not p["published"], p["exam_name"]))
        context.plans = plans

        now = getdate(today())
        upcoming = sorted(
            (r for p in plans for r in p["rows"] if r["_date"] and r["_date"] >= now),
            key=lambda r: (r["_date"], r["_start"]),
        )
        context.upcoming_count = len(upcoming)
        context.next_exam = upcoming[0] if upcoming else None
    except Exception as exc:
        frappe.log_error(f"Exam Timetable error: {exc}", "Student Portal Exam Timetable")
        context.portal_error = str(exc)
        _es._set_nav_defaults(context)

    return context


def _plan(exam_plan, courses, student):
    ep = frappe.db.get_value(
        "Exam Plan", exam_plan,
        ["exam_name", "term", "timetable_published", "timetable_show_invigilator",
         "reexam_timetable_published", "reexam_show_invigilator"],
        as_dict=True,
    )
    if not ep:
        return None

    names = {
        c.name: c for c in frappe.get_all(
            "Course", filters={"name": ["in", list(courses) or ["__none__"]]},
            fields=["name", "course_name", "course_code"], ignore_permissions=True,
        )
    }
    attendance = dict(frappe.get_all(
        "Student Course Marks",
        filters={"student": student, "exam_plan": exam_plan},
        fields=["course", "attendance_status"], as_list=True, ignore_permissions=True,
    ))

    rows, scheduled = [], set()
    if ep.timetable_published:
        for course, s in _student_rows("Exam Course Schedule", exam_plan, courses, student).items():
            scheduled.add(course)
            rows.append(_row(s, names.get(course), attendance.get(course), ep.timetable_show_invigilator))

    reexam_courses = frappe.get_all(
        "Re Exam Registration",
        filters={"student": student, "exam_plan": exam_plan, "status": "Registered"},
        pluck="course", ignore_permissions=True,
    )
    if ep.reexam_timetable_published and reexam_courses:
        for course, s in _student_rows("Exam Reexam Schedule", exam_plan, reexam_courses, student).items():
            c = names.get(course) or frappe.db.get_value("Course", course, ["name", "course_name", "course_code"], as_dict=True)
            rows.append(_row(s, c, None, ep.reexam_show_invigilator, reexam=True))

    rows.sort(key=lambda r: (r["_date"] or getdate("2999-12-31"), r["_start"]))
    pending = sorted(
        (names[c].course_name or c) if c in names else c
        for c in courses if c not in scheduled
    ) if ep.timetable_published else []

    return {
        "name": exam_plan,
        "exam_name": ep.exam_name or exam_plan,
        "term": ep.term or "",
        "published": bool(ep.timetable_published or (ep.reexam_timetable_published and reexam_courses)),
        "rows": rows,
        "pending": pending,
        "show_invigilator": any(r["invigilator"] for r in rows),
    }


def _student_rows(doctype, exam_plan, courses, student):
    """{course: the row the student sits in}; a course in several rooms is split by ID Nos. range."""
    by_course = {}
    for s in frappe.get_all(
        doctype,
        filters={"parent": exam_plan, "parenttype": "Exam Plan", "course": ["in", list(courses) or ["__none__"]]},
        fields=["course", "exam_date", "session", "start_time", "end_time", "venue", "hall",
                "paper", "id_from", "id_to", "invigilator", "invigilator_name"],
        order_by="idx asc", ignore_permissions=True,
    ):
        by_course.setdefault(s.course, []).append(s)
    return {course: _es._student_room(rows, student) for course, rows in by_course.items()}


def _row(s, course, attendance_status, show_invigilator, reexam=False):
    start, end = _es._fmt_time(s.start_time), _es._fmt_time(s.end_time)
    course = course or frappe._dict(name=s.course, course_name=s.course, course_code=s.course)
    date = getdate(s.exam_date) if s.exam_date else None
    return {
        "course_name": (course.course_name or course.name) + (" (Re-exam)" if reexam else ""),
        "course_code": (course.course_code or course.name or "").split("-")[0],
        "paper": s.paper if s.paper and s.paper != course.course_name else "",
        "date": formatdate(date, "EEE, d MMM yyyy") if date else "",
        "session": s.session or "",
        "time": f"{start} – {end}" if start and end else start,
        "room": " | ".join(filter(None, [s.venue, s.hall])),
        "invigilator": _es._invigilator(s) if show_invigilator else "",
        "detained": attendance_status == "Detained",
        "is_reexam": reexam,
        "is_past": bool(date and date < getdate(today())),
        "_date": date,
        "_start": str(s.start_time or ""),
    }

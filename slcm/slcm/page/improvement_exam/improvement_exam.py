import frappe
import json as _json
from frappe import _

IMPROVEMENT_EXAM_ROLES = {"System Manager", "Academics User"}


def _check_access():
    """Admin-only actions (settings, marking paid) — this page is restricted
    at the desk UI level, but the whitelisted RPCs are directly callable via
    /api/method/, so they must enforce the same role themselves."""
    if not IMPROVEMENT_EXAM_ROLES & set(frappe.get_roles()):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


def _get_course_offering(exam_plan, course):
	"""Resolve the Course Offering for a course under this exam plan via its
	Course Schema Assignment. Throws if none exists yet."""
	course_offering = frappe.db.get_value(
		"Course Schema Assignment", {"exam_plan": exam_plan, "course": course}, "course_offering"
	)
	if not course_offering:
		frappe.throw(
			f"No Course Offering found for course '{course}' in exam plan '{exam_plan}'. "
			"Map a Course Schema Assignment for it first."
		)
	return course_offering


@frappe.whitelist()
def get_exam_plans(search=None):
    filters = {}
    if search:
        filters["exam_name"] = ["like", f"%{search}%"]
    return frappe.get_all(
        "Exam Plan",
        filters=filters,
        fields=["name", "exam_name", "term", "status"],
        order_by="creation desc",
    )


@frappe.whitelist()
def get_programmes_for_exam_plan(exam_plan):
    if not exam_plan:
        return []
    rows = frappe.db.sql(
        """
        SELECT DISTINCT sm.programme_of_study AS programme
        FROM `tabStudent Course Marks` scm
        INNER JOIN `tabStudent Master` sm ON sm.name = scm.student
        WHERE scm.exam_plan = %(exam_plan)s
          AND sm.programme_of_study IS NOT NULL AND sm.programme_of_study != ''
        ORDER BY sm.programme_of_study
        """,
        {"exam_plan": exam_plan},
        as_dict=True,
    )
    return rows


@frappe.whitelist()
def get_courses_for_exam_plan(exam_plan, programme=""):
    if not exam_plan:
        return []
    extra_join = ""
    extra_cond = ""
    params = {"exam_plan": exam_plan}
    if programme:
        extra_join = "INNER JOIN `tabStudent Master` sm ON sm.name = scm.student"
        extra_cond = " AND sm.programme_of_study = %(programme)s"
        params["programme"] = programme
    rows = frappe.db.sql(
        f"""
        SELECT DISTINCT scm.course, c.course_name
        FROM `tabStudent Course Marks` scm
        LEFT JOIN `tabCourse` c ON c.name = scm.course
        {extra_join}
        WHERE scm.exam_plan = %(exam_plan)s{extra_cond}
        ORDER BY c.course_name, scm.course
        """,
        params,
        as_dict=True,
    )
    return rows


@frappe.whitelist()
def get_improvement_setting(exam_plan, course):
    if not exam_plan or not course:
        return {}
    row = frappe.db.get_value(
        "Improvement Exam Course Setting",
        {"exam_plan": exam_plan, "course": course},
        ["name", "improvement_fee", "registration_limit", "deadline_from", "deadline_to"],
        as_dict=True,
    )
    return row or {}


@frappe.whitelist()
def save_improvement_setting(exam_plan, course, improvement_fee=None, registration_limit=None, deadline_from=None, deadline_to=None):
    _check_access()
    if not exam_plan or not course:
        frappe.throw("Exam Plan and Course are required.")

    existing_name = frappe.db.get_value(
        "Improvement Exam Course Setting",
        {"exam_plan": exam_plan, "course": course},
        "name",
    )

    if existing_name:
        doc = frappe.get_doc("Improvement Exam Course Setting", existing_name)
    else:
        doc = frappe.new_doc("Improvement Exam Course Setting")
        doc.exam_plan = exam_plan
        doc.course = course
        doc.course_offering = _get_course_offering(exam_plan, course)

    doc.improvement_fee = improvement_fee or None
    doc.registration_limit = int(registration_limit) if registration_limit else None
    doc.deadline_from = deadline_from or None
    doc.deadline_to = deadline_to or None
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"name": doc.name}


@frappe.whitelist()
def bulk_save_improvement_setting(exam_plan, improvement_fee=None, registration_limit=None, deadline_from=None, deadline_to=None, courses=None):
    _check_access()
    if not exam_plan:
        frappe.throw("Exam Plan is required.")

    if courses:
        course_list = _json.loads(courses) if isinstance(courses, str) else list(courses)
    else:
        rows = frappe.db.sql(
            "SELECT DISTINCT course FROM `tabStudent Course Marks` WHERE exam_plan = %(exam_plan)s",
            {"exam_plan": exam_plan},
            as_list=True,
        )
        course_list = [r[0] for r in rows]

    updated = 0
    for course in course_list:
        if not course:
            continue
        existing_name = frappe.db.get_value(
            "Improvement Exam Course Setting",
            {"exam_plan": exam_plan, "course": course},
            "name",
        )
        if existing_name:
            doc = frappe.get_doc("Improvement Exam Course Setting", existing_name)
        else:
            doc = frappe.new_doc("Improvement Exam Course Setting")
            doc.exam_plan = exam_plan
            doc.course = course
            doc.course_offering = _get_course_offering(exam_plan, course)
        doc.improvement_fee = improvement_fee or None
        doc.registration_limit = int(registration_limit) if registration_limit else None
        doc.deadline_from = deadline_from or None
        doc.deadline_to = deadline_to or None
        doc.save(ignore_permissions=True)
        updated += 1
    frappe.db.commit()
    return {"updated": updated}


@frappe.whitelist()
def get_eligible_students(exam_plan, course, search="", page=1, page_length=20):
    """Return only students who have PAID for the improvement exam."""
    if not exam_plan or not course:
        return {"students": [], "total": 0}

    page = int(page)
    page_length = int(page_length)
    offset = (page - 1) * page_length
    params = {"exam_plan": exam_plan, "course": course}

    extra_cond = ""
    if search:
        extra_cond += (
            " AND (sm.registration_id LIKE %(search)s"
            " OR sm.first_name LIKE %(search)s"
            " OR sm.last_name LIKE %(search)s)"
        )
        params["search"] = f"%{search}%"

    params["lim"] = page_length
    params["off"] = offset

    # Only students who have a Paid improvement exam registration
    students = frappe.db.sql(
        f"""
        SELECT
            sm.name                                                              AS student,
            sm.registration_id,
            TRIM(CONCAT_WS(' ', sm.first_name,
                COALESCE(NULLIF(sm.middle_name,''), NULL),
                sm.last_name))                                                   AS student_name,
            sm.programme_of_study                                                AS programme,
            sm.batch AS batch_year,
            sm.passport_size_photo                                               AS image,
            sm.email,
            scm.grade,
            COALESCE(scm.updated_final_marks, scm.total_marks)                  AS total_marks,
            scm.improvement_marks,
            scm.improvement_grade,
            scm.improvement_applied,
            ier.status                                                           AS reg_status,
            ier.payment_status,
            ier.improvement_fee
        FROM `tabImprovement Exam Registration` ier
        INNER JOIN `tabStudent Master` sm ON sm.name = ier.student
        INNER JOIN `tabStudent Course Marks` scm
               ON scm.student = ier.student
              AND scm.exam_plan = ier.exam_plan
              AND scm.course = ier.course
        WHERE ier.exam_plan = %(exam_plan)s
          AND ier.course = %(course)s
          AND ier.status != 'Cancelled'
          AND ier.payment_status = 'Paid'
        {extra_cond}
        ORDER BY sm.registration_id ASC
        LIMIT %(lim)s OFFSET %(off)s
        """,
        params,
        as_dict=True,
    )

    count_params = {k: v for k, v in params.items() if k not in ("lim", "off")}
    count_row = frappe.db.sql(
        f"""
        SELECT COUNT(*) AS cnt
        FROM `tabImprovement Exam Registration` ier
        INNER JOIN `tabStudent Master` sm ON sm.name = ier.student
        INNER JOIN `tabStudent Course Marks` scm
               ON scm.student = ier.student
              AND scm.exam_plan = ier.exam_plan
              AND scm.course = ier.course
        WHERE ier.exam_plan = %(exam_plan)s
          AND ier.course = %(course)s
          AND ier.status != 'Cancelled'
          AND ier.payment_status = 'Paid'
        {extra_cond}
        """,
        count_params,
        as_dict=True,
    )
    total = count_row[0]["cnt"] if count_row else 0

    for s in students:
        s["registered"] = True

    return {"students": students, "total": total}


@frappe.whitelist()
def get_improvement_stats(exam_plan, course):
    if not exam_plan or not course:
        return {}

    total_row = frappe.db.sql(
        "SELECT COUNT(*) AS cnt FROM `tabStudent Course Marks` WHERE exam_plan=%(ep)s AND course=%(c)s",
        {"ep": exam_plan, "c": course}, as_dict=True,
    )
    graded_row = frappe.db.sql(
        "SELECT COUNT(*) AS cnt FROM `tabStudent Course Marks` WHERE exam_plan=%(ep)s AND course=%(c)s AND grade IS NOT NULL AND grade != ''",
        {"ep": exam_plan, "c": course}, as_dict=True,
    )
    reg_row = frappe.db.sql(
        "SELECT COUNT(*) AS cnt FROM `tabImprovement Exam Registration` WHERE exam_plan=%(ep)s AND course=%(c)s AND status != 'Cancelled'",
        {"ep": exam_plan, "c": course}, as_dict=True,
    )
    applied_row = frappe.db.sql(
        "SELECT COUNT(*) AS cnt FROM `tabStudent Course Marks` WHERE exam_plan=%(ep)s AND course=%(c)s AND improvement_applied=1",
        {"ep": exam_plan, "c": course}, as_dict=True,
    )

    return {
        "total":      total_row[0]["cnt"] if total_row else 0,
        "graded":     graded_row[0]["cnt"] if graded_row else 0,
        "registered": reg_row[0]["cnt"] if reg_row else 0,
        "applied":    applied_row[0]["cnt"] if applied_row else 0,
    }


@frappe.whitelist()
def mark_improvement_paid(registration_name, payment_reference=""):
    _check_access()
    if not registration_name:
        frappe.throw("Registration name is required.")
    doc = frappe.get_doc("Improvement Exam Registration", registration_name)
    doc.payment_status = "Paid"
    if payment_reference:
        doc.payment_reference = payment_reference
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
def get_improvement_registrations(exam_plan, course=""):
    if not exam_plan:
        return []
    params = {"exam_plan": exam_plan}
    course_cond = ""
    if course:
        course_cond = "AND r.course = %(course)s"
        params["course"] = course
    rows = frappe.db.sql(
        f"""
        SELECT
            r.name,
            r.student,
            r.course,
            COALESCE(c.course_name, r.course)  AS course_name,
            TRIM(CONCAT_WS(' ', sm.first_name,
                COALESCE(NULLIF(sm.middle_name,''), NULL),
                sm.last_name))                 AS student_name,
            sm.registration_id,
            sm.programme_of_study                                                AS programme,
            r.improvement_fee,
            r.status,
            r.payment_status,
            r.payment_reference,
            r.remarks,
            r.creation
        FROM `tabImprovement Exam Registration` r
        INNER JOIN `tabStudent Master` sm ON sm.name = r.student
        LEFT  JOIN `tabCourse`         c  ON c.name  = r.course
        WHERE r.exam_plan = %(exam_plan)s
          {course_cond}
          AND r.status != 'Cancelled'
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    return rows

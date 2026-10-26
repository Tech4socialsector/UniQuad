import frappe
from slcm.permissions import (
    _get_faculty_name,
    _get_faculty_course_offerings,
    _get_faculty_assigned_students,
    _FULL_ACCESS_ROLES,
)


def _is_unrestricted(roles):
    return bool(roles & _FULL_ACCESS_ROLES) or "slcm_Programme Chair" in roles


def _faculty_scope(user):
    """
    Return (offerings, students, faculty_name) for the current faculty user,
    or (None, None, None) if the user has unrestricted access.
    Raises PermissionError if faculty has no linked Faculty record.
    """
    roles = set(frappe.get_roles(user))

    if _is_unrestricted(roles):
        return None, None, None

    if "slcm_Faculty" not in roles:
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

    faculty_name = _get_faculty_name(user)
    if not faculty_name:
        frappe.throw(frappe._("No Faculty record linked to your account."), frappe.PermissionError)

    offerings = _get_faculty_course_offerings(faculty_name)
    students = _get_faculty_assigned_students(faculty_name)
    return offerings, students, faculty_name


@frappe.whitelist()
def get_faculty_context():
    """
    Return the programmes, course offerings, and sections visible to the
    current user so the JS can restrict filter dropdowns accordingly.
    Returns None for each when the user has unrestricted access.
    """
    user = frappe.session.user
    offerings, students, faculty_name = _faculty_scope(user)

    if offerings is None:
        # Unrestricted user — no restriction needed
        return {"restricted": False}

    if not offerings:
        return {"restricted": True, "programmes": [], "course_offerings": [], "sections": []}

    # Derive visible programmes and sections from assigned Course Offerings
    offering_docs = frappe.get_all(
        "Course Offering",
        filters={"name": ["in", offerings]},
        fields=["name", "program", "section"],
    )

    programmes = list({o.program for o in offering_docs if o.program})
    sections = list({o.section for o in offering_docs if o.section})

    return {
        "restricted": True,
        "faculty_name": faculty_name,
        "course_offerings": offerings,
        "programmes": programmes,
        "sections": sections,
    }


@frappe.whitelist()
def get_attendance_data(
    programme=None,
    course_offering=None,
    from_date=None,
    to_date=None,
    period=None,
    status=None,
    section=None,
):
    user = frappe.session.user
    offerings, students, faculty_name = _faculty_scope(user)

    conditions = []
    values = {}

    # --- Faculty scoping: restrict to their assigned students ---
    if students is not None:
        if not students:
            # Faculty exists but has no students assigned — return empty
            return {"data": [], "summary": {"total": 0, "present": 0, "absent": 0, "late": 0, "od": 0, "excused": 0}}

    if from_date:
        conditions.append("sa.attendance_date >= %(from_date)s")
        values["from_date"] = from_date
    if to_date:
        conditions.append("sa.attendance_date <= %(to_date)s")
        values["to_date"] = to_date
    if programme:
        conditions.append("sa.program = %(programme)s")
        values["programme"] = programme
    if course_offering:
        conditions.append("sa.course_offer = %(course_offering)s")
        values["course_offering"] = course_offering
    if period:
        conditions.append("sa.period = %(period)s")
        values["period"] = period
    if status:
        conditions.append("sa.status = %(status)s")
        values["status"] = status
    if section:
        conditions.append("senr.section = %(section)s")
        values["section"] = section

    # Build the Student Enrollment join only when needed for a section filter
    section_join = (
        """LEFT JOIN (
            SELECT sec.course_offering, se.student, se.section
            FROM `tabStudent Enrollment` se
            JOIN `tabStudent Enrollment Course` sec ON sec.parent = se.name
            WHERE sec.status = 'Enrolled' AND se.status = 'Enrolled'
        ) senr ON senr.course_offering = sa.course_offer AND senr.student = sa.student"""
        if section else ""
    )

    if students is not None:
        conditions.append("sa.student IN %(students)s")
        values["students"] = students

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    data = frappe.db.sql(
        f"""
        SELECT
            sa.name,
            sa.student,
            sa.student_name,
            sa.attendance_date,
            sa.status,
            sa.course,
            sa.program,
            sa.course_offer,
            sa.period,
            sa.session_type,
            sa.in_time,
            sa.out_time,
            sa.attendance_session
        FROM `tabStudent Attendance` sa
        {section_join}
        {where_clause}
        ORDER BY sa.attendance_date DESC, sa.student_name ASC
        LIMIT 500
        """,
        values,
        as_dict=True,
    )

    total = len(data)
    present = sum(1 for r in data if r.status == "Present")
    absent  = sum(1 for r in data if r.status == "Absent")
    late    = sum(1 for r in data if r.status == "Late")
    od      = sum(1 for r in data if r.status == "OD")
    excused = sum(1 for r in data if r.status == "Excused")

    return {
        "data": data,
        "summary": {
            "total": total,
            "present": present,
            "absent": absent,
            "late": late,
            "od": od,
            "excused": excused,
        },
    }


@frappe.whitelist()
def get_course_offerings(programme=None):
    user = frappe.session.user
    offerings, students, faculty_name = _faculty_scope(user)

    filters = {}
    if programme:
        filters["program"] = programme

    if offerings is not None:
        if not offerings:
            return []
        filters["name"] = ["in", offerings]

    return frappe.get_all(
        "Course Offering",
        filters=filters,
        fields=["name", "course_title"],
        order_by="course_title asc",
        limit=200,
    )


@frappe.whitelist()
def get_sections(programme=None, course_offering=None):
    user = frappe.session.user
    offerings, students, faculty_name = _faculty_scope(user)

    filters = {}
    if programme:
        batches = frappe.get_all("SLCM Batch", filters={"program": programme}, pluck="name")
        if not batches:
            return []
        filters["batch"] = ["in", batches]

    if offerings is not None:
        if not offerings:
            return []
        offering_docs = frappe.get_all(
            "Course Offering",
            filters={"name": ["in", offerings]},
            pluck="section",
        )
        visible_sections = [s for s in offering_docs if s]
        if not visible_sections:
            return []
        filters["name"] = ["in", visible_sections]

    return frappe.get_all(
        "Section",
        filters=filters,
        fields=["name", "section_name"],
        order_by="section_name asc",
        limit=200,
    )

import frappe
from slcm.permissions import (
    _get_faculty_name,
    _get_faculty_classes,
    _get_faculty_assigned_students,
    _FULL_ACCESS_ROLES,
)


def _is_unrestricted(roles):
    return bool(roles & _FULL_ACCESS_ROLES) or "slcm_Programme Chair" in roles


def _faculty_scope(user):
    """
    Return (classes, students, faculty_name) for the current faculty user,
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

    classes = _get_faculty_classes(faculty_name)
    students = _get_faculty_assigned_students(faculty_name)
    return classes, students, faculty_name


def _class_sections(classes):
    """Sections taught in these Classes — the Section classes' own section,
    plus the sections of their enrolled students (Group classes)."""
    if not classes:
        return []
    sections = set(frappe.get_all("Classes", filters={"name": ["in", classes]}, pluck="section"))
    sections.update(
        frappe.get_all(
            "Class Enrolled Student",
            filters={"parent": ["in", classes], "parenttype": "Classes"},
            pluck="section",
        )
    )
    return [s for s in sections if s]


@frappe.whitelist()
def get_faculty_context():
    """
    Return the programmes, classes, and sections visible to the
    current user so the JS can restrict filter dropdowns accordingly.
    Returns None for each when the user has unrestricted access.
    """
    user = frappe.session.user
    classes, students, faculty_name = _faculty_scope(user)

    if classes is None:
        # Unrestricted user — no restriction needed
        return {"restricted": False}

    if not classes:
        return {"restricted": True, "programmes": [], "classes": [], "sections": []}

    # Derive visible programmes and sections from the assigned Classes
    class_docs = frappe.get_all(
        "Classes",
        filters={"name": ["in", classes]},
        fields=["name", "programme"],
    )

    programmes = list({c.programme for c in class_docs if c.programme})
    sections = _class_sections(classes)

    return {
        "restricted": True,
        "faculty_name": faculty_name,
        "classes": classes,
        "programmes": programmes,
        "sections": sections,
    }


@frappe.whitelist()
def get_attendance_data(
    programme=None,
    class_name=None,
    from_date=None,
    to_date=None,
    period=None,
    status=None,
    section=None,
):
    user = frappe.session.user
    classes, students, faculty_name = _faculty_scope(user)

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
    if class_name:
        conditions.append("sa.class_name = %(class_name)s")
        values["class_name"] = class_name
    if period:
        conditions.append("sa.period = %(period)s")
        values["period"] = period
    if status:
        conditions.append("sa.status = %(status)s")
        values["status"] = status
    if section:
        conditions.append("senr.section = %(section)s")
        values["section"] = section

    # Build the class-roster join only when needed for a section filter
    section_join = (
        """LEFT JOIN (
            SELECT ces.parent AS class_name, se.student,
                COALESCE(NULLIF(ces.section, ''), se.section) AS section
            FROM `tabClass Enrolled Student` ces
            JOIN `tabStudent Enrollment` se ON se.name = ces.student_enrollment
            WHERE ces.parenttype = 'Classes' AND ces.status = 'Enrolled' AND se.status = 'Enrolled'
        ) senr ON senr.class_name = sa.class_name AND senr.student = sa.student"""
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
            sa.class_name,
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
def get_classes(programme=None):
    user = frappe.session.user
    classes, students, faculty_name = _faculty_scope(user)

    filters = {}
    if programme:
        filters["programme"] = programme

    if classes is not None:
        if not classes:
            return []
        filters["name"] = ["in", classes]

    return frappe.get_all(
        "Classes",
        filters=filters,
        fields=["name", "course", "course_name"],
        order_by="course_name asc",
        limit=200,
    )


@frappe.whitelist()
def get_sections(programme=None, class_name=None):
    user = frappe.session.user
    classes, students, faculty_name = _faculty_scope(user)

    # Sections are global (no batch / programme), so `programme` doesn't narrow them.
    filters = {}

    if classes is not None:
        if not classes:
            return []
        visible_sections = _class_sections(classes)
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

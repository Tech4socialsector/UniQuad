import frappe
from slcm.utils.faculty_portal import get_faculty_name, set_faculty_nav, set_nav_defaults, set_portal_settings

no_cache = 1


def get_context(context):
    context.no_cache = 1
    set_portal_settings(context)

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "profile"

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

        # Full faculty details
        context.faculty_full = {
            "name": faculty.name,
            "faculty_id": faculty.faculty_id or "—",
            "first_name": faculty.first_name or "",
            "last_name": faculty.last_name or "",
            "email": faculty.email or frappe.session.user,
            "phone": faculty.phone or "—",
            "designation": faculty.designation or "—",
            "department": frappe.db.get_value("SLCM Department", faculty.department, "department_name")
                          if faculty.department else faculty.department or "—",
            "qualification": faculty.qualification or "—",
            "specialization": faculty.specialization or "—",
            "experience_years": faculty.experience_years or 0,
            "joining_date": frappe.utils.formatdate(faculty.joining_date, "dd MMM yyyy")
                            if faculty.joining_date else "—",
            "status": faculty.status or "Active",
            "photo": faculty.photo or "",
            "highlights": faculty.highlights or "",
            "institution": faculty.institution or "—",
        }

        # Active/Open course offerings
        courses = frappe.get_all(
            "Course Offering",
            filters={"faculty": faculty_name, "status": ["in", ["Open", "Active"]]},
            fields=["name", "course_name", "term_name", "academic_year", "credit_value"],
            order_by="academic_year desc, term_name asc, course_name asc",
            ignore_permissions=True,
        )
        context.assigned_courses = courses
        context.total_courses = len(courses)

    except Exception as e:
        frappe.log_error(f"Faculty Portal Profile error: {e}", "Faculty Portal")
        context.portal_error = str(e)
        set_nav_defaults(context)
        _set_defaults(context)

    return context


def _set_defaults(context):
    context.faculty_full = {}
    context.assigned_courses = []
    context.total_courses = 0

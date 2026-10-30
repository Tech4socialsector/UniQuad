import frappe
from slcm.api.faculty_grades import get_faculty_courses
from slcm.utils.faculty_portal import get_faculty_name, set_faculty_nav, set_nav_defaults, set_portal_settings

no_cache = 1


def course_key(course, academic_term):
    """Selector value for a course taught in a term (split again in the page JS)."""
    return f"{course or ''}::{academic_term or ''}"


def get_context(context):
    """Faculty Grades page. Only the list of the faculty's courses (course +
    academic term, from Classes.faculty) is rendered here; the grade sheet
    itself loads through slcm.api.faculty_grades, which applies the faculty /
    class / Access Result Settings checks.

    URL: /faculty-portal/marks?course=<Course>&academic_term=<Academic Term>"""
    context.no_cache = 1
    set_portal_settings(context)

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "marks"
    context.faculty_courses = []
    context.selected_co = ""
    context.selected_plan = ""

    faculty_name = get_faculty_name()
    if not faculty_name:
        context.not_a_faculty = True
        set_nav_defaults(context)
        return context

    context.not_a_faculty = False
    try:
        set_faculty_nav(context, frappe.get_doc("Faculty", faculty_name))
        courses = get_faculty_courses(faculty_name)
        for c in courses:
            c.key = course_key(c.course, c.academic_term)
        context.faculty_courses = courses

        args = frappe.request.args if frappe.request else {}
        selected = course_key(args.get("course", ""), args.get("academic_term", ""))
        # No auto-pick: faculty choose the course before any grades load
        context.selected_co = selected if selected in {c.key for c in courses} else ""
        context.selected_plan = args.get("exam_plan", "") if context.selected_co else ""
    except Exception as e:
        frappe.log_error(f"Faculty Portal Grades error: {e}", "Faculty Portal")
        context.portal_error = str(e)
        set_nav_defaults(context)

    return context

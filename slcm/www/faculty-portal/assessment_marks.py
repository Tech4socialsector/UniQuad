import frappe
from slcm.api.faculty_grades import get_faculty_offerings
from slcm.utils.faculty_portal import get_faculty_name, set_faculty_nav, set_nav_defaults, set_portal_settings

no_cache = 1


def get_context(context):
    """Faculty Assessment Marks page. Only the course-offering list is rendered
    here; assessments and the marks sheet load through
    slcm.api.faculty_assessment_marks, which checks ownership and the entry window."""
    context.no_cache = 1
    set_portal_settings(context)

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "assessment_marks"
    context.course_offerings = []
    context.selected_co = ""

    faculty_name = get_faculty_name()
    if not faculty_name:
        context.not_a_faculty = True
        set_nav_defaults(context)
        return context

    context.not_a_faculty = False
    try:
        set_faculty_nav(context, frappe.get_doc("Faculty", faculty_name))
        offerings = get_faculty_offerings(faculty_name)
        context.course_offerings = offerings

        args = frappe.request.args if frappe.request else {}
        selected = args.get("course_offering", "")
        context.selected_co = selected if selected in {o.name for o in offerings} else ""
    except Exception as e:
        frappe.log_error(f"Faculty Portal Assessment Marks error: {e}", "Faculty Portal")
        context.portal_error = str(e)
        set_nav_defaults(context)

    return context

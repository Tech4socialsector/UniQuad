import frappe
from urllib.parse import quote
from frappe.utils.oauth import get_oauth2_authorize_url

from slcm.slcm.utils.parent_portal import get_parent_wards
from slcm.utils.faculty_portal import get_faculty_name


no_cache = 1

TAB_FACULTY_STUDENT = "faculty-student"
TAB_PARENT = "parent"


def get_context(context):
    redirect_to = (
        frappe.local.request.args.get("redirect-to", "") or
        frappe.local.request.args.get("redirect_to", "") or
        frappe.local.request.args.get("redirect", "") or
        frappe.local.request.args.get("next", "")
    )

    requested_tab = frappe.local.request.args.get("tab", "")
    default_tab = getattr(frappe.local.flags, "default_login_tab", None)
    tab = requested_tab or default_tab or TAB_FACULTY_STUDENT
    if tab not in (TAB_FACULTY_STUDENT, TAB_PARENT):
        tab = TAB_FACULTY_STUDENT

    if frappe.session.user != "Guest":
        user = frappe.session.user
        user_type = frappe.db.get_value("User", user, "user_type") or "Website User"

        if get_faculty_name():
            frappe.local.flags.redirect_location = redirect_to or "/faculty-portal"
            raise frappe.Redirect

        if frappe.db.exists("Student Master", {"official_email_id": user}) or \
           frappe.db.exists("Student Master", {"user": user}):
            frappe.local.flags.redirect_location = redirect_to or "/student-portal"
            raise frappe.Redirect

        if get_parent_wards(user):
            frappe.local.flags.redirect_location = redirect_to or "/parent-portal"
            raise frappe.Redirect

        if user_type == "System User":
            frappe.local.flags.redirect_location = "/desk"
            raise frappe.Redirect

        frappe.local.login_manager.logout()
        frappe.db.commit()
        context.no_role_found = True

    context.tab = tab
    context.redirect_to = redirect_to

    _load_settings(context)

    context.no_cache = 1
    context.csrf_token = frappe.local.session.data.csrf_token or ""
    context.title = context.portal_title + " — Login"
    context.google_login_url_faculty_student = _get_google_login_url(TAB_FACULTY_STUDENT, redirect_to)
    context.google_login_url_parent = _get_google_login_url(TAB_PARENT, redirect_to)
    context.google_login_error = frappe.local.request.args.get("error", "")


def _get_google_login_url(tab, redirect_to):
    if tab == TAB_PARENT:
        enabled = frappe.db.get_single_value("Parent Portal Settings", "enable_google_login")
    else:
        enabled = (
            frappe.db.get_single_value("Student Portal Settings", "enable_google_login")
            or frappe.db.get_single_value("Faculty Portal Settings", "enable_google_login")
        )
    if not enabled:
        return None
    if not frappe.db.exists(
        "Social Login Key",
        {"social_login_provider": "Google", "enable_social_login": 1}
    ):
        return None
    try:
        callback_target = f"/portal-login?tab={tab}&redirect-to=" + quote(redirect_to, safe="")
        return get_oauth2_authorize_url("google", callback_target)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "portal-login/login: google oauth url failed")
        return None


def _load_settings(context):
    try:
        settings = frappe.get_single("Student Portal Settings")
        
        context.primary_color = "#920C24"
        context.secondary_color = "#2b2e4a"
        context.portal_title = settings.portal_title or "National Law School of India University"
        context.portal_tagline = settings.portal_subtitle or ""
        
        logo = settings.get("portal_favicon")
        if not logo:
            logo = frappe.db.get_single_value("Website Settings", "app_logo")
        context.portal_logo = logo or ""

        bg_image = settings.get("login_page_background_image")
        context.bg_image = bg_image if bg_image else ""
        context.bg_color = "#FAFAFA" if not bg_image else ""
    except Exception:
        frappe.log_error(frappe.get_traceback(), "portal-login/login: settings load failed")
        context.primary_color = "#920C24"
        context.secondary_color = "#2b2e4a"
        context.portal_title = "National Law School of India University"
        context.portal_tagline = ""
        context.portal_logo = ""
        context.bg_image = ""
        context.bg_color = "#FAFAFA"

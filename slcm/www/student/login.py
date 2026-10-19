import frappe
from frappe.utils.oauth import get_oauth2_authorize_url

no_cache = 1

def get_context(context):
    redirect_to = frappe.local.request.args.get("redirect-to", "/student-portal")
    
    settings = frappe.get_single("Student Portal Settings")
    
    context.primary_color = "#920C24"
    context.secondary_color = "#2b2e4a"
    context.portal_title = settings.portal_title or "National Law School of India University"
    context.portal_tagline = settings.portal_subtitle or ""
    context.portal_logo = frappe.db.get_single_value("Website Settings", "app_logo") or ""
    
    bg_image = settings.get("login_page_background_image")
    context.bg_image = bg_image if bg_image else ""
    context.bg_color = "#FAFAFA" if not bg_image else ""

    # get google login
    context.google_login_url = ""
    providers = frappe.get_all("Social Login Key", filters={"enable_social_login": 1, "provider_name": "Google"}, fields=["name"])
    if providers:
        context.google_login_url = get_oauth2_authorize_url(providers[0].name, redirect_to)

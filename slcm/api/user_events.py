import frappe
from slcm.permissions import AAD_ROLES

HELPDESK_CUSTOMER_ROLE = "HD Customer"


def grant_helpdesk_customer_role(doc, method=None):
    """
    Triggered on User validate.
    AAD / AAD Staff raise Helpdesk tickets as customers (they see only their own
    tickets). Helpdesk lets a user into the app only with an Agent / HD Customer
    role, so without it their Helpdesk icon is dropped and the Campus & Support
    folder opens empty.
    """
    roles = {r.role for r in doc.get("roles") or []}
    if roles & AAD_ROLES and HELPDESK_CUSTOMER_ROLE not in roles and frappe.db.exists("Role", HELPDESK_CUSTOMER_ROLE):
        doc.append("roles", {"role": HELPDESK_CUSTOMER_ROLE})


def user_before_insert(doc, method):
    """
    Triggered on User before_insert.

    Welcome emails: a user added from the desk with "Send Welcome Email" ticked
    gets Frappe's own welcome email (System Settings > Welcome Email Template),
    sent by Frappe. The NLSAT / PACE registration endpoints create users with
    send_welcome_email = 0 and send their portal's email themselves
    (slcm.admission.utils.auth_emails), so exactly one email goes out either way.
    """
    if doc.user_type != "Website User":
        return

    # Assign the current active admission cycle to the user for accurate applicant reminders
    try:
        from slcm.admission.applicant_reminder_emails import _get_active_cycle
        active_cycle_name = _get_active_cycle()[0]
        if active_cycle_name:
            doc.registered_admission_cycle = active_cycle_name
    except Exception:
        pass

    if doc.flags.no_welcome_mail:
        # Created without asking for a welcome email: a Google / social sign-up
        # (frappe.utils.oauth sets this flag), a portal registration (which sends
        # its own email), or code that creates users silently.
        doc.send_welcome_email = 0

def on_login_hook(login_manager):
    """
    Triggered on successful user authentication.
    Ensures System Users (like Administrator) are routed directly to /desk,
    overriding any Role-level home_page defaults (e.g. from the Applicant role).
    """
    try:
        user = frappe.session.user
        if user and user != "Guest":
            user_type = frappe.db.get_value("User", user, "user_type")
            if user_type == "System User":
                frappe.local.response["home_page"] = "/desk"
    except Exception:
        pass

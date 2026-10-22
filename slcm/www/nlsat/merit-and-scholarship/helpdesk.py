import frappe
from slcm.admission.utils.nlsat_portal import get_portal_login_url
from frappe import _

no_cache = 1

def _check_access(allowed_roles, login_redirect):
    """
    Check session and role access.
    - Guest users are redirected to login.
    - Logged-in users without required role see CleanNotPermittedException.
    """
    import frappe
    from slcm.admission.portal_application_web_form import CleanNotPermittedException

    # Guest check — redirect to login
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = login_redirect
        raise frappe.Redirect

    # Role check — must have at least one allowed role
    roles = frappe.get_roles(frappe.session.user)
    has_access = any(role in roles for role in allowed_roles)

    if not has_access:
        import frappe.website.serve
        if not getattr(frappe.website.serve, "_clean_patch_applied", False):
            orig_handle = frappe.website.serve.handle_exception
            def _patched_handle_exception(e, endpoint, path, http_status_code):
                if type(e).__name__ == "CleanNotPermittedException":
                    return e.get_response()
                return orig_handle(e, endpoint, path, http_status_code)
            frappe.website.serve.handle_exception = _patched_handle_exception
            frappe.website.serve._clean_patch_applied = True
            
        raise CleanNotPermittedException()

def get_context(context):
    _check_access(
        allowed_roles=["Applicant", "PACE Applicant", "System Manager", "Administrator"],
        login_redirect=get_portal_login_url()
    )
    context.no_cache = 1

    # ── Portal config (colours, fonts, mission text) ───────────────
    from slcm.admission.utils.portal import get_portal_config
    try:
        cfg = get_portal_config()
        context.portal_config = cfg.as_dict() if hasattr(cfg, "as_dict") else dict(cfg)
    except Exception:
        context.portal_config = {}

    # ── Mission text (used by the sidebar) ────────────────────────
    pc = context.portal_config
    context._mission_txt = (pc.get("mission_text") if callable(getattr(pc, "get", None)) else getattr(pc, "mission_text", "")) or ""

    context.title = _("Help Desk")
    return context

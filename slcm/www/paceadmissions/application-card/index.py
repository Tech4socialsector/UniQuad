import frappe
from slcm.admission.utils.portal import get_portal_config

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
        allowed_roles=["PACE Applicant", "System Manager", "Administrator", "PACE Admission Manager", "Admission Admin", "Document Verifier"],
        login_redirect="/paceadmissions/login"
    )
    context.portal_config = get_portal_config()
    context.no_cache = 1

    # ── Status colour map ─────────────────────────────────────────
    STATUS_STYLE = {
        "Draft":              {"color": "#6b7280", "bg": "#f3f4f6",  "icon": "edit_note"},
        "Submitted":          {"color": "#1d4ed8", "bg": "#dbeafe",  "icon": "check_circle"},
        "Under Verification": {"color": "#d97706", "bg": "#fef3c7",  "icon": "hourglass_top"},
        "Verified":           {"color": "#059669", "bg": "#d1fae5",  "icon": "verified"},
        "Admitted":           {"color": "#065f46", "bg": "#a7f3d0",  "icon": "school"},
        "Rejected":           {"color": "#991b1b", "bg": "#fee2e2",  "icon": "cancel"},
    }

    # ── Fetch PACE Applications for current user ──────────────────
    _user = frappe.session.user
    roles = frappe.get_roles(_user)
    
    admin_roles = {"System Manager", "Administrator", "PACE Admission Manager", "Admission Admin"}
    is_admin = bool(set(roles).intersection(admin_roles))
    is_verifier = "Document Verifier" in roles
    
    fields = [
        "name", "applicant_name", "first_name", "last_name",
        "programme", "status", "submission_date",
        "academic_year", "email_address", "upload_student_photo",
        "creation", "modified",
    ]

    try:
        if is_admin:
            all_apps_list = frappe.get_all(
                "PACE Application",
                fields=fields,
                order_by="creation desc",
                ignore_permissions=True,
            )
            combined = {a.name: a for a in all_apps_list}
        elif is_verifier:
            all_apps_list = frappe.get_all(
                "PACE Application",
                filters={"assigned_verifier": _user},
                fields=fields,
                order_by="creation desc",
                ignore_permissions=True,
            )
            combined = {a.name: a for a in all_apps_list}
        else:
            apps_by_owner = frappe.get_all(
                "PACE Application",
                filters={"owner": _user},
                fields=fields,
                order_by="creation desc",
                ignore_permissions=True,
            )
            apps_by_email = frappe.get_all(
                "PACE Application",
                filters={"email_address": _user},
                fields=fields,
                order_by="creation desc",
                ignore_permissions=True,
            )
            combined = {a.name: a for a in (apps_by_owner + apps_by_email)}
            
        all_apps = sorted(combined.values(), key=lambda x: x.modified, reverse=True)
    except Exception as e:
        frappe.log_error(f"PACE Application Card fetch failed: {e}", "PACE Card")
        all_apps = []

    try:
        page = int(frappe.form_dict.get('page', 1))
    except ValueError:
        page = 1

    limit = 12
    total_apps = len(all_apps)
    total_pages = (total_apps + limit - 1) // limit
    
    if page < 1:
        page = 1
    if total_pages > 0 and page > total_pages:
        page = total_pages
        
    start = (page - 1) * limit
    paged_apps = all_apps[start:start + limit]

    context.current_page = page
    context.total_pages = total_pages

    def get_page_range(curr, total):
        if total <= 7:
            return list(range(1, total + 1))
        if curr <= 4:
            return [1, 2, 3, 4, 5, '...', total]
        if curr >= total - 3:
            return [1, '...', total - 4, total - 3, total - 2, total - 1, total]
        return [1, '...', curr - 1, curr, curr + 1, '...', total]

    context.page_range = get_page_range(page, total_pages)

    # ── Build card data ───────────────────────────────────────────
    pace_cards = []
    _prog_cache = {}

    for app in paged_apps:
        prog_name = app.get("programme") or ""
        prog_data = _prog_cache.get(prog_name)

        if not prog_data and prog_name:
            try:
                prog_data = frappe.db.get_value(
                    "PACE Programme",
                    prog_name,
                    [
                        "programme_name", "programme_code", "programme_prefix",
                        "banner_image", "duration", "duration_type",
                        "contact_email",
                    ],
                    as_dict=True,
                )
                if prog_data:
                    _prog_cache[prog_name] = prog_data
            except Exception:
                prog_data = None

        status = app.get("status") or "Draft"
        sc = STATUS_STYLE.get(status, STATUS_STYLE["Draft"])

        # Duration label
        dur = ""
        if prog_data:
            d = prog_data.get("duration")
            dt = prog_data.get("duration_type") or ""
            if d:
                dur = f"{d} {dt}" if dt else f"{d}"

        display_name = app.get("applicant_name") or ""
        if not display_name:
            first = app.get("first_name") or ""
            last = app.get("last_name") or ""
            display_name = f"{first} {last}".strip()

        pace_cards.append({
            "name":             app.name,
            "applicant_name":   display_name,
            "programme":        prog_name,
            "programme_name":   (prog_data.get("programme_name") if prog_data else prog_name) or prog_name,
            "programme_code":   (prog_data.get("programme_code") if prog_data else "") or "",
            "programme_prefix": (prog_data.get("programme_prefix") if prog_data else "") or "",
            "banner_image":     (prog_data.get("banner_image") if prog_data else "") or "",
            "duration_label":   dur,
            "contact_email":    (prog_data.get("contact_email") if prog_data else "") or "",
            "status":           status,
            "status_color":     sc["color"],
            "status_bg":        sc["bg"],
            "status_icon":      sc["icon"],
            "submission_date":  frappe.utils.formatdate(app.get("submission_date"), "dd MMM yyyy")
                                if app.get("submission_date") else "",
            "academic_year":    app.get("academic_year") or "",
            "student_photo":    app.get("upload_student_photo") or "",
            "created_on":       frappe.utils.formatdate(app.get("creation"), "dd MMM yyyy"),
        })

    context.pace_cards = pace_cards
    context.has_pace_apps = len(pace_cards) > 0

    # ── Sidebar counts ───────────────────────────────────────────
    try:
        if is_admin:
            context.pace_app_count = frappe.db.count("PACE Application") or 0
        elif is_verifier:
            context.pace_app_count = frappe.db.count("PACE Application", filters={"assigned_verifier": _user}) or 0
        else:
            pace_by_owner = frappe.db.count("PACE Application", filters={"owner": _user}) or 0
            pace_by_email = frappe.db.count("PACE Application", filters={"email_address": _user}) or 0
            context.pace_app_count = max(pace_by_owner, pace_by_email)
    except Exception:
        context.pace_app_count = 0

    context.pace_enabled = 1

    # ── User info ─────────────────────────────────────────────────
    context.nav_user = _user
    context.is_guest = False
    context.user_display = (
        frappe.db.get_value("User", _user, "full_name") or _user.split("@")[0]
    )
    context.user_first = (context.user_display or "U")[0].upper()
    context.today = frappe.utils.getdate(frappe.utils.today())

    return context

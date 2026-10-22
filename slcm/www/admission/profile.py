import frappe
from slcm.admission.utils.nlsat_portal import get_candidate_login_url, get_candidate_prefix
from slcm.admission.api.profile import _user_address_value, _user_dob_value
from slcm.admission.utils.portal import get_portal_config

no_cache = 1


def _check_access(allowed_roles, login_redirect):
    """
    Check session and role access.
    - Guest users are redirected to login.
    - Logged-in users without required role see CleanNotPermittedException.
    """
    import frappe  # local: the `import frappe.website.serve` below makes `frappe` a local name
    from slcm.admission.portal_application_web_form import CleanNotPermittedException

    # Guest check — redirect to login
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = login_redirect
        raise frappe.Redirect

    # Role check — must have at least one allowed role
    roles = frappe.get_roles(frappe.session.user)
    if not any(role in roles for role in allowed_roles):
        # Patch Frappe's exception handler so it renders our custom Werkzeug Response
        # instead of a 500 error traceback when raised from get_context()
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
    """/nlsat/my-profile and /pace/my-profile — the candidate's profile, shared by NLSAT and PACE."""
    prefix = get_candidate_prefix()
    _check_access(
        allowed_roles=["Applicant", "PACE Applicant", "System Manager", "Administrator"],
        login_redirect=get_candidate_login_url(prefix) + "?redirect-to=" + prefix + "/my-profile",
    )
    context.portal_config = get_portal_config()
    context.no_cache = 1

    user = frappe.session.user
    if frappe.db.get_value("User", user, "user_type") == "System User":
        frappe.local.flags.redirect_location = "/desk"
        raise frappe.Redirect

    is_applicant = frappe.db.get_value("Has Role", {"parent": user, "role": "Applicant"}, "role")
    is_pace_applicant = frappe.db.get_value("Has Role", {"parent": user, "role": "PACE Applicant"}, "role")
    context.is_applicant = bool(is_applicant)
    context.is_pace_applicant = bool(is_pace_applicant)
    context.is_pace_only = bool(is_pace_applicant and not is_applicant)

    # ── Current user info ─────────────────────────────────────────
    context.nav_user     = user or ''
    context.is_guest     = context.nav_user == 'Guest' or not context.nav_user
    context.user_display = frappe.db.get_value(
        "User", context.nav_user, "full_name"
    ) or context.nav_user.split("@")[0] if context.nav_user else ''
    context.user_first   = (context.user_display or 'U')[0].upper()
    context.today = frappe.utils.getdate(frappe.utils.today())

    # ── Sidebar mission text from portal config ───────────────────
    _pc = context.portal_config
    try:
        context.portal_mission = (
            _pc.get("portal_mission") if _pc and _pc.get else getattr(_pc, "portal_mission", "")
        ) or ""
    except Exception:
        context.portal_mission = ""

    # ── Profile data (Sourced from User doctype) ────────────────────
    try:
        user_doc = frappe.get_doc("User", user)
        context.profile_data = {
            "candidate_name": user_doc.full_name,
            "email": user_doc.email,
            "mobile_number": getattr(user_doc, "mobile_no", ""),
            "date_of_birth": _user_dob_value(user_doc),
            "gender": user_doc.gender,
            "nationality": getattr(user_doc, "nationality", ""),
            "correspondence_address": _user_address_value(user_doc),
            "city": getattr(user_doc, "city", ""),
            "state": getattr(user_doc, "state", ""),
            "pincode": getattr(user_doc, "pincode", ""),
            "candidate_photo": user_doc.user_image,  # This is the profile photo
        }

        # Latest Applicant record — used for the documents checklist below
        _fields = ['name', 'status', 'candidate_photo', 'whether_scstobc_ncl', 'pwd', 'program_level', 'ka_study_7yrs']
        _ap = frappe.get_all('Applicant', filters={'email': user}, fields=_fields, limit=1, order_by='creation desc')
        if not _ap:
            _ap = frappe.get_all('Applicant', filters={'owner': user}, fields=_fields, limit=1, order_by='creation desc')
        if _ap:
            context.profile_data["name"] = _ap[0].name
            # Application fields stay off profile_data — profile UI is User-only; status lives on application cards.
            context.applicant_record = _ap[0]

        context.profile_data_json = frappe.as_json(context.profile_data)
    except Exception as e:
        frappe.log_error(f"Profile fetch failed: {e}", "NLSAT Profile")
        context.profile_data = {}
        context.profile_data_json = "{}"

    # ── Derive first name for navbar ──────────────────────────────────
    try:
        _fullname = context.profile_data.get('candidate_name', '') if context.profile_data else ''
        context.first_name = _fullname.split()[0] if _fullname else ''
    except Exception:
        context.first_name = ''

    # ── Documents Logic (Strictly Applicant fields) ──
    context.app_documents = []
    if context.profile_data and context.profile_data.get("name"):
        try:
            target_applicant = frappe.get_doc("Applicant", context.profile_data.get("name"), ignore_permissions=True)

            standard_checklist = [
                {"label": "10th Certificate", "field": "class_x_marksheet", "required": True},
                {"label": "12th Certificate", "field": "class_xii_marksheet", "required": True},
                {"label": "ID Proof", "field": "id_proof", "required": True},
                {"label": "Photo", "field": "candidate_photo", "required": True},
            ]

            if target_applicant.get("whether_scstobc_ncl") and target_applicant.get("whether_scstobc_ncl") != "NA":
                standard_checklist.append({"label": "Category Certificate", "field": "caste_certificate", "required": True})

            if target_applicant.get("pwd") == "Yes":
                standard_checklist.append({"label": "PwD Certificate", "field": "pwd_certificate", "required": True})

            if target_applicant.get("program_level") == "Research Course":
                standard_checklist.append({"label": "Research Proposal", "field": "phd_proposal", "required": True})
                standard_checklist.append({"label": "CV", "field": "cv", "required": True})

            if target_applicant.get("ka_study_7yrs"):
                standard_checklist.append({"label": "Karnataka Study Certificate", "field": "ka_study_7yrs_certificate", "required": True})

            for item in standard_checklist:
                val = target_applicant.get(item["field"])
                context.app_documents.append({
                    "document_name": item["label"],
                    "document_type": item["label"],
                    "is_uploaded": bool(val),
                    "file_url": val,
                    "field": item["field"],
                    "source": "field",
                    "required": item["required"]
                })
        except Exception as e:
            frappe.log_error(f"Profile doc error: {e}", "NLSAT Profile")

    return context

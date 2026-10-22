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
    scheme_id = frappe.form_dict.get('scheme')
    
    # Redirect back to dashboard if no scheme is provided
    if not scheme_id:
        frappe.local.flags.redirect_location = "/nlsat/merit-and-scholarship/admission_dashboard"
        raise frappe.Redirect

    _check_access(
        allowed_roles=["Applicant", "System Manager", "Administrator"],
        login_redirect=get_portal_login_url()
    )

    try:
        # Fetch scheme details
        context.scheme = frappe.get_doc("Scholarship Scheme", scheme_id)
        
        # Get applicant details matching the user's email
        user_email = frappe.session.user
        applicant = frappe.db.get_value("Applicant", {"email": user_email}, 
            ["name", "candidate_name", "admission_cycle", "campus", "program", "program_level"], as_dict=1)
        
        if not applicant:
            # Fallback 1: check Entrance Test Seat Allocation email
            applicant_id = frappe.db.get_value("Entrance Test Seat Allocation", {"email": user_email}, "applicant")
            if applicant_id:
                applicant = frappe.db.get_value("Applicant", applicant_id, 
                    ["name", "candidate_name", "admission_cycle", "campus", "program", "program_level"], as_dict=1)
        
        if not applicant:
            # Fallback 2: search by owner
            applicant = frappe.db.get_value("Applicant", {"owner": user_email}, 
                ["name", "candidate_name", "admission_cycle", "campus", "program", "program_level"], as_dict=1)
        
        if not applicant:
            context.error = _("No applicant record found for your account. Please complete your registration first.")
            return context
            
        context.applicant = applicant

        # Check if Admission Fee is paid (to block direct access)
        # Scholarships should only be blocked if the actual Admission/Program fee is paid,
        # not just the initial Application Fee.
        is_fee_paid = frappe.db.exists("Applicant Fee Assignment", {
            "applicant": applicant.name,
            "admission_cycle": applicant.admission_cycle,
            "fee_type": "Admission Fee",
            "status": ["in", ["Paid", "Converted"]],
            "docstatus": ["!=", 2]
        }) or (frappe.db.get_value("Applicant", applicant.name, "status") in ["Confirmation Fee Paid", "Full Fee Paid"])

        if is_fee_paid:
            context.error = _("Scholarship applications are not permitted once the admission fee has been paid. "
                              "Scholarships must be applied for and approved before final payment is made.")
            return context
        
        # Add portal config for contact details
        from slcm.admission.utils.portal import get_portal_config
        context.portal_config = get_portal_config()

    except frappe.DoesNotExistError:
        context.error = _("The requested scholarship scheme does not exist.")
    except Exception as e:
        frappe.log_error(f"Scholarship Apply Context Error: {e}")
        context.error = _("An unexpected error occurred. Please try again later.")

    return context

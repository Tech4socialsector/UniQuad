import frappe
from slcm.admission.utils.nlsat_portal import get_portal_login_url
from frappe import _
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
        allowed_roles=["Applicant", "System Manager", "Administrator"],
        login_redirect=get_portal_login_url()
    )
    context.portal_config = get_portal_config()
    _user = frappe.session.user
    context.today = frappe.utils.getdate(frappe.utils.today())

    # ── PACE Applications Count ──────────────────────────────────
    context._pace_enabled = True
    context.pace_app_count = frappe.db.count("PACE Application", {"owner": _user})

    # ── Active Admission Cycle ───────────────────────────────────
    active_cycle_name = frappe.db.get_value("Admission Cycle", {"status": "Active"}, "name")
    if active_cycle_name:
        active_cycle_doc = frappe.get_doc("Admission Cycle", active_cycle_name)
        context.active_cycle = frappe._dict({
            "name": active_cycle_doc.name,
            "cycle_start_date": frappe.utils.getdate(active_cycle_doc.cycle_start_date) if active_cycle_doc.cycle_start_date else None,
            "cycle_end_date": frappe.utils.getdate(active_cycle_doc.cycle_end_date) if active_cycle_doc.cycle_end_date else None
        })
    else:
        context.active_cycle = None
    
    # Initialize all context variables
    context.no_applicant = False
    context.applicant = None
    context.all_applicants = []
    context.eligible_scholarships = []
    context.applied_scholarships = []
    context.approved_scholarships = []
    context.rejected_scholarships = []
    context.kpis = {"eligible": 0, "applied": 0, "approved": 0, "amount_awarded": 0}
    context.error = None

    if _user == "Guest":
        frappe.local.flags.redirect_location = get_portal_login_url() + "?redirect=/nlsat/merit-and-scholarship/scholarships"
        raise frappe.Redirect

    try:
        # 1. Fetch Applicant Details
        _app_param = frappe.form_dict.get('app')
        
        # Match dashboard logic for finding applications
        fields = ["name", "applicant_id", "candidate_name", "program", "campus", 
                  "admission_cycle", "status", "annual_house_hold_income", 
                  "percentage", "whether_scstobc_ncl", "pwd", "karnataka_category"]
        
        apps_by_owner = frappe.get_all("Applicant", filters={"owner": _user}, fields=fields, ignore_permissions=True)
        apps_by_email = frappe.get_all("Applicant", filters={"email": _user}, fields=fields, ignore_permissions=True)
        
        combined = {a.name: a for a in (apps_by_owner + apps_by_email)}
        applicant_records = sorted(combined.values(), key=lambda x: x.name, reverse=True)

        if not applicant_records:
            context.no_applicant = True
            return context

        # Pick specific app if requested, else newest
        applicant = None
        if _app_param and _app_param in combined:
            applicant = combined[_app_param]
        else:
            applicant = applicant_records[0]
            
        context.applicant = applicant
        context.all_applicants = applicant_records

        # 1.5 Check if Admission Fee is paid (to disable new scholarship applications)
        # Scholarships should only be blocked if the actual Admission/Program fee is paid,
        # not just the initial Application Fee.
        context.is_fee_paid = frappe.db.exists("Applicant Fee Assignment", {
            "applicant": applicant.name,
            "admission_cycle": applicant.admission_cycle,
            "fee_type": "Admission Fee",
            "status": ["in", ["Paid", "Converted"]],
            "docstatus": ["!=", 2]
        }) or (applicant.status in ["Confirmation Fee Paid", "Full Fee Paid"])

        # 2. Get Categories from Applicant Category child table
        applicant_categories = set()
        categories = frappe.get_all(
            "Applicant Category",
            filters={"parent": applicant.name, "parenttype": "Applicant"},
            pluck="category"
        )
        for cat in categories:
            if cat:
                applicant_categories.add(cat)
        
        if not applicant_categories:
            sc_st_obc = (getattr(applicant, "whether_scstobc_ncl", None) or "").strip()
            if sc_st_obc and sc_st_obc.lower() != "na":
                applicant_categories.add(sc_st_obc)
            if (getattr(applicant, "pwd", None) or "").strip() == "Yes":
                applicant_categories.add("PWD")
            if (getattr(applicant, "karnataka_category", None) or "").strip() == "Yes":
                applicant_categories.add("Karnataka category")

        # 3. Fetch All Scholarship Applications
        all_apps = frappe.get_all(
            "Scholarship Application",
            filters={"applicant_id": applicant.name},
            fields=["name", "scholarship_scheme", "status", "creation", "modified", "approval_date", "calculated_benefit", "final_fee_amount", "rejection_reason", "original_fee_amount", "income_certificate", "supporting_documents"],
            order_by="creation desc",
            ignore_permissions=True
        )
        
        applied_scheme_names = [app.scholarship_scheme for app in all_apps]
        
        scheme_cache = {}
        def get_scheme_data(scheme_id):
            if scheme_id in scheme_cache: return scheme_cache[scheme_id]
            try:
                scheme_doc = frappe.get_doc("Scholarship Scheme", scheme_id, ignore_permissions=True)
                rules = frappe.get_all(
                    "Scholarship Coverage Rule",
                    filters={"parent": scheme_id},
                    fields=["fee_component", "coverage_type", "coverage_value", "maximum_cap"],
                    ignore_permissions=True
                )
                data = {
                    "name": scheme_doc.name,
                    "scheme_name": scheme_doc.scheme_name,
                    "scheme_type": scheme_doc.scheme_type,
                    "description": scheme_doc.description,
                    "max_amount": scheme_doc.max_amount,
                    "apply_on": scheme_doc.apply_on,
                    "coverage_type": scheme_doc.coverage_type,
                    "coverage_value": scheme_doc.coverage_value,
                    "application_end": scheme_doc.application_end,
                    "eligibility_criteria": scheme_doc.eligibility_criteria,
                    "coverage_rules": rules
                }
                scheme_cache[scheme_id] = data
                return data
            except:
                return None

        # Categorize Applications
        for app in all_apps:
            s_data = get_scheme_data(app.scholarship_scheme)
            if s_data:
                app.update(s_data)
                if app.status == "Approved":
                    context.approved_scholarships.append(app)
                elif app.status == "Rejected":
                    context.rejected_scholarships.append(app)
                else:
                    context.applied_scholarships.append(app)

        # 4. Fetch Eligible Schemes
        from slcm.admission.utils.scholarship_availability import get_available_scholarships_for_dashboard
        
        raw_eligible = get_available_scholarships_for_dashboard(
            applicant.name,
            applicant.admission_cycle,
            applicant.campus,
            applicant.program,
            [applicant.status]
        )

        eligible_schemes = []
        for s in raw_eligible:
            s_full = get_scheme_data(s.get('name'))
            if s_full:
                eligible_schemes.append(s_full)

        context.eligible_scholarships = eligible_schemes

        # 5. KPI Counts
        context.kpis = {
            "eligible": len(eligible_schemes),
            "applied": len(all_apps),
            "approved": len(context.approved_scholarships),
            "amount_awarded": sum([flt(app.calculated_benefit) for app in context.approved_scholarships if app.calculated_benefit])
        }

    except Exception as e:
        frappe.log_error(f"Scholarship Dashboard Error: {e}", "Scholarship Dashboard")
        context.error = str(e)

    return context

def flt(v):
    from frappe.utils import flt as _flt
    return _flt(v)

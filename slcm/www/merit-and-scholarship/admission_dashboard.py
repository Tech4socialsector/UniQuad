import frappe
from slcm.admission.utils.nlsat_portal import get_portal_login_url
from slcm.admission.api.profile import _user_address_value, _user_dob_value
from slcm.admission.doctype.eligibility_result.eligibility_result import get_applicant_data
from slcm.admission.utils.portal import get_portal_config
from slcm.admission.utils.scholarship_availability import get_available_scholarships_for_dashboard, get_applied_scholarships_for_dashboard

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
    _check_access(
        allowed_roles=["Applicant", "PACE Applicant", "System Manager", "Administrator"],
        login_redirect=get_portal_login_url()
    )
    context.portal_config = get_portal_config()
    context.no_cache = 1

    if frappe.session.user != "Guest":
        user_type = frappe.db.get_value("User", frappe.session.user, "user_type")
        if user_type == "System User":
            frappe.local.flags.redirect_location = "/desk"
            raise frappe.Redirect

    is_applicant = frappe.db.get_value("Has Role", {"parent": frappe.session.user, "role": "Applicant"}, "role")
    is_pace_applicant = frappe.db.get_value("Has Role", {"parent": frappe.session.user, "role": "PACE Applicant"}, "role")
    context.is_applicant = bool(is_applicant)
    context.is_pace_applicant = bool(is_pace_applicant)
    context.is_pace_only = bool(is_pace_applicant and not is_applicant)

    # ── Application cards (new) ──────────────────────────────────
    STATUS_STYLE = {
        "Draft":            {"color": "#6b7280", "bg": "#f3f4f6"},
        "Submitted":        {"color": "#1d4ed8", "bg": "#dbeafe"},
        "Merit Published":  {"color": "#0369a1", "bg": "#e0f2fe"},
        "Merit Selected":   {"color": "#065f46", "bg": "#d1fae5"},
        "Merit Rejected":   {"color": "#991b1b", "bg": "#fee2e2"},
        "Merit Waitlisted": {"color": "#7c3aed", "bg": "#ede9fe"},
        "Under Review":     {"color": "#d97706", "bg": "#fef3c7"},
        "Shortlisted":      {"color": "#059669", "bg": "#d1fae5"},
        "Waitlisted":       {"color": "#7c3aed", "bg": "#ede9fe"},
        "Offer Issued":     {"color": "#0369a1", "bg": "#e0f2fe"},
        "Offer Accepted":   {"color": "#065f46", "bg": "#d1fae5"},
        "Rejected":         {"color": "#991b1b", "bg": "#fee2e2"},
        "Selected":         {"color": "#065f46", "bg": "#d1fae5"},
    }

    applicants = frappe.get_all(
        "Applicant",
        filters=[["owner", "=", frappe.session.user]],
        fields=["name", "candidate_name", "program", "admission_cycle",
                "status", "creation", "current_stage"],
        order_by="creation desc"
    )

    cards = []
    for a in applicants:
        program_name = frappe.db.get_value(
            "Programme", a.program, "program_name"
        ) or a.program or "—"

        intake = frappe.db.get_value(
            "Programme", a.program, "intake_type"
        ) or "All"

        # current_stage is now a plain value (no Stage Master lookup needed)
        curr_stage = a.current_stage or ""

        status = a.status or "Draft"
        sc = STATUS_STYLE.get(status, STATUS_STYLE["Draft"])

        cards.append({
            "name":         a.name,
            "program_name": program_name,
            "cycle":        a.admission_cycle or "—",
            "status":       status,
            "color":        sc["color"],
            "bg":           sc["bg"],
            "intake_type":  intake,
            "stage":        curr_stage,
            "submitted_on": frappe.utils.formatdate(a.creation, "dd MMM yyyy"),
        })

    context.application_cards = cards
    context.has_applications = len(cards) > 0

    # ── Existing merit/scholarship data ─────────────────────────
    data = get_applicant_data()
    if isinstance(data, dict) and "error" in data:
        context.error = data["error"]
    else:
        context.applicant_data = data

    # ── Current user info ─────────────────────────────────────────
    context.nav_user     = frappe.session.user or ''
    context.is_guest     = context.nav_user == 'Guest' or not context.nav_user
    context.user_display = frappe.db.get_value(
        "User", context.nav_user, "full_name"
    ) or context.nav_user.split("@")[0] if context.nav_user else ''
    context.user_first   = (context.user_display or 'U')[0].upper()
    context.today = frappe.utils.getdate(frappe.utils.today())

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

    # ── All applicant records for this user (all cycles) ──────────
    try:
        _user = context.nav_user
        # Query by owner — fetch candidate_name directly (no SQL alias; aliases are unreliable in frappe.get_all)
        apps_by_owner = frappe.get_all(
            "Applicant",
            filters={"owner": _user},
            fields=[
                "name", "candidate_name", "program",
                "status", "current_stage",
                "admission_cycle", "creation", "modified", "campus"
            ],
            ignore_permissions=True
        )
        
        # Query by email
        apps_by_email = frappe.get_all(
            "Applicant",
            filters={"email": _user},
            fields=[
                "name", "candidate_name", "program",
                "status", "current_stage",
                "admission_cycle", "creation", "modified", "campus"
            ],
            ignore_permissions=True
        )
        
        # Combine and deduplicate
        combined = {a.name: a for a in (apps_by_owner + apps_by_email)}
        context.my_applications = sorted(
            combined.values(), 
            key=lambda x: x.get("modified") or x.get("creation") or "",
            reverse=True
        )[:10]

        for app in context.my_applications:
            # Map candidate_name -> applicant_name for template compatibility
            app["applicant_name"] = app.get("candidate_name") or ""
            prog = app.get("program") or ""
            app["program_name"] = (frappe.db.get_value("Programme", prog, "program_name") if prog else None) or prog or "—"
            app["program_image"] = frappe.db.get_value("Programme", prog, "program_image") if prog else None
            # current_stage is a plain field value — no Stage Master lookup
            app["current_stage_name"] = app.get("current_stage") or ""
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Dashboard my_applications query failed")
        context.my_applications = []

    # ── Scholarship Schemes (show if any active schemes exist) ─────
    try:
        available_scholarships = []
        applied_scholarships = []
        entrance_tests = []
        seen_schemes = set()
        seen_applications = set()
        
        for app in context.my_applications:
            # Get Entrance Test details
            try:
                etrows = frappe.get_all(
                    "Entrance Test Seat Allocation",
                    filters={"applicant": app.name},
                    fields=["entrance_test_name", "center_name",
                            "center_address", "seat_number",
                            "allocation_status", "name"],
                    order_by="creation desc", limit=1,
                    ignore_permissions=True
                )
                if etrows:
                    et = etrows[0]
                    test_name = et.get("entrance_test_name") or ""
                    test_date = ""
                    test_time = ""
                    if test_name:
                        try:
                            td = frappe.get_doc("Entrance Test List", test_name, ignore_permissions=True)
                            test_date = frappe.utils.format_date(str(td.get("test_date") or "")[:10], "MMMM d, yyyy") if td.get("test_date") else ""
                            test_time = str(td.get("test_time") or "")
                        except Exception: pass
                    
                    entrance_tests.append({
                        "app_id": app.name,
                        "program_name": app.program_name,
                        "test_name": test_name,
                        "test_date": test_date,
                        "test_time": test_time,
                        "center_name": et.get("center_name") or "",
                        "center_address": et.get("center_address") or "",
                        "seat_number": (et.get("seat_number").split("-")[-1] if et.get("seat_number") else ""),
                        "admit_status": et.get("allocation_status") or "",
                        "admit_card_url": f"/api/method/slcm.admission.utils.web.download_admit_card?admit_card={et.get('name')}"
                    })
            except Exception: pass

            # Get Applied Scholarships
            apps = get_applied_scholarships_for_dashboard(app.name)
            for a in apps:
                if a.name not in seen_applications:
                    # Enrich with scheme name
                    a["scheme_name"] = frappe.db.get_value("Scholarship Scheme", a.scholarship_scheme, "scheme_name") or a.scholarship_scheme
                    applied_scholarships.append(a)
                    seen_applications.add(a.name)

            if not all([app.admission_cycle, app.campus, app.program]):
                continue
                
            schemes = get_available_scholarships_for_dashboard(
                app.name, 
                app.admission_cycle, 
                app.campus, 
                app.program, 
                [app.status] if app.status else []
            )
            for s in schemes:
                if s.name not in seen_schemes:
                    available_scholarships.append(s)
                    seen_schemes.add(s.name)
        
        context.scholarships = available_scholarships[:20]
        context.applied_scholarships = sorted(applied_scholarships, key=lambda x: x.creation, reverse=True)
        context.entrance_tests = entrance_tests
    except Exception as e:
        frappe.log_error(f"Scholarship/ET fetch failed: {e}", "Dashboard Fix")
        context.scholarships = []
        context.applied_scholarships = []
        context.entrance_tests = []

    # ── Portal config extras ───────────────────────────────────────
    try:
        _pc = context.portal_config  # already fetched above
        context.portal_mission = (
            _pc.get("portal_mission") if _pc and _pc.get else
            getattr(_pc, "portal_mission", "")
        ) or ""
        context.value_cards = (
            _pc.get("value_cards") if _pc and _pc.get else
            getattr(_pc, "value_cards", [])
        ) or []
    except Exception:
        context.portal_mission = ""
        context.value_cards    = []

    # ── Unread messages count (placeholder — Messages not built) ───
    context.unread_messages = 0

    # ── Hero image from portal config ─────────────────────────────
    try:
        context.dashboard_hero_image = (
            _pc.get("hero_image") if _pc and _pc.get else
            getattr(_pc, "hero_image", "")
        ) or ""
    except Exception:
        context.dashboard_hero_image = ""

    # ── Profile data (Sourced from User doctype) ────────────────────
    try:
        _user = frappe.session.user
        if _user and _user != 'Guest':
            user_doc = frappe.get_doc("User", _user)
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
                "candidate_photo": user_doc.user_image, # This is the profile photo
            }
            # For backward compatibility in template and other logic that expects Applicant name
            # if Applicant record exists, we still want its name for reference in other parts?
            # No, requirement says: Source of Truth Change - Load ONLY from "User"
            
            # Fetch application-specific info from Applicant for the progress calculation/documents
            _ap = frappe.get_all(
                'Applicant',
                filters={'email': _user},
                fields=['name', 'status', 'candidate_photo', 'whether_scstobc_ncl', 'pwd', 'program_level', 'ka_study_7yrs'],
                limit=1,
                order_by='creation desc'
            )
            if not _ap:
                _ap = frappe.get_all(
                    'Applicant',
                    filters={'owner': _user},
                    fields=['name', 'status', 'candidate_photo', 'whether_scstobc_ncl', 'pwd', 'program_level', 'ka_study_7yrs'],
                    limit=1,
                    order_by='creation desc'
                )
            
            if _ap:
                context.profile_data["name"] = _ap[0].name
                # Application fields stay off profile_data — profile UI is User-only; status lives on application cards.
                context.applicant_record = _ap[0]

            context.profile_data_json = frappe.as_json(context.profile_data)
        else:
            context.profile_data = {}
            context.profile_data_json = "{}"
    except Exception as e:
        frappe.log_error(f"Dashboard profile fetch failed: {e}", "Dashboard Fix")
        context.profile_data = {}
        context.profile_data_json = "{}"

    # ── Derive first name for navbar ──────────────────────────────────
    try:
        _fullname = context.profile_data.get('candidate_name', '') if context.profile_data else ''
        context.first_name = _fullname.split()[0] if _fullname else ''
    except Exception:
        context.first_name = ''

    # ── Documents Logic (Mirror index.py logic - Strictly Applicant fields) ──
    context.app_documents = []
    if context.profile_data and context.profile_data.get("name"):
        try:
            doc_lookup_name = context.profile_data.get("name")
            target_applicant = frappe.get_doc("Applicant", doc_lookup_name, ignore_permissions=True)

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
                field = item["field"]
                val = target_applicant.get(field)
                context.app_documents.append({
                    "document_name": item["label"],
                    "document_type": item["label"],
                    "is_uploaded": bool(val),
                    "file_url": val,
                    "field": field,
                    "source": "field",
                    "required": item["required"]
                })
        except Exception as e:
            frappe.log_error(f"Admission Dashboard doc error: {e}")

    # ── PACE Application count (for sidebar badge) ────────────────────
    try:
        pace_by_owner = frappe.db.count(
            "PACE Application", filters={"owner": frappe.session.user}
        ) or 0
        pace_by_email = frappe.db.count(
            "PACE Application", filters={"email_address": frappe.session.user}
        ) or 0
        context.pace_app_count = max(pace_by_owner, pace_by_email)
    except Exception:
        context.pace_app_count = 0

    # ── PACE enabled flag (Always True per requirement) ────────────
    context._pace_enabled = True

    # ── Active panel from URL param ───────────────────────────────────
    context.active_panel = frappe.form_dict.get('panel', 'applications')

    return context

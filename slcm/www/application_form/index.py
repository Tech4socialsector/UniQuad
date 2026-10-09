import html

import frappe
from frappe import _
from frappe.utils import flt, now, nowdate, strip_html

from slcm.utils.phone_utils import sanitize_phone_for_frappe
from slcm.admission.utils.portal import is_application_editable
from slcm.admission.utils.multiprogram_applicant import (
    applicant_dict_for_multiprogram_copy,
    build_multiprogram_profile_copy_payload,
    store_multiprogram_profile_copy_in_cache,
)

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


def _redirect_portal_to_application_entry(program, admission_cycle, extra_q):
    """
    Redirect to the cycle's configured entry URL (Web Form or /application_form).
    When allow_multiple_applications applies, cache a one-shot profile copy for the web form.
    """
    from slcm.admission.utils.portal import build_applicant_form_new_url

    program = (program or "").strip()
    admission_cycle = (admission_cycle or "").strip()
    extra_q = extra_q or {}
    user = frappe.session.user
    email = frappe.db.get_value("User", user, "email") or user
    payload = build_multiprogram_profile_copy_payload(email, admission_cycle, program)
    store_multiprogram_profile_copy_in_cache(payload)
    ad_year, ac_year = frappe.db.get_value(
        "Admission Cycle", admission_cycle, ["admission_year", "academic_year"]
    ) or ("", "")
    frappe.local.flags.redirect_location = build_applicant_form_new_url(
        program,
        admission_cycle,
        campus=(extra_q.get("campus") or "").strip(),
        intake_type=(extra_q.get("intake_type") or "").strip(),
        admission_year=(extra_q.get("admission_year") or "").strip() or (ad_year or ""),
        academic_year=(extra_q.get("academic_year") or "").strip() or (ac_year or ""),
        program_level=(extra_q.get("program_level") or "").strip(),
    )
    raise frappe.Redirect


def _portal_unique_campuses_for_program_cycle(program, admission_cycle):
    """Ordered campus names from Admission Cycle Program. Website Users often lack Campus read permission."""
    program = (program or "").strip()
    admission_cycle = (admission_cycle or "").strip()
    if not program or not admission_cycle:
        return []
    rows = frappe.get_all(
        "Admission Cycle Program",
        filters={
            "parent": admission_cycle,
            "program": program,
            "is_active": 1,
        },
        fields=["campus"],
        order_by="idx asc",
        ignore_permissions=True,
    )
    out = []
    for r in rows or []:
        c = (r.get("campus") or "").strip()
        if c and c not in out:
            out.append(c)
    return out


# ═══════════════════════════════════════════════════════════════════
#  START APPLICATION (from admission listing only — sets session, no URL)
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=False)
def start_application(program=None, admission_cycle=None, campus=None, program_level=None, intake_type=None):
    """
    Validate program + cycle and redirect to the Applicant web form or /application_form (per cycle).
    """
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/admission/login?redirect-to=/admission"
        raise frappe.Redirect
    program = (program or "").strip()
    admission_cycle = (admission_cycle or "").strip()
    if not program or not admission_cycle:
        frappe.local.flags.redirect_location = "/admission"
        raise frappe.Redirect
    exists = frappe.db.exists(
        "Admission Cycle Program",
        {"parent": admission_cycle, "program": program, "is_active": 1},
    )
    if not exists:
        frappe.local.flags.redirect_location = "/admission"
        raise frappe.Redirect
    _redirect_portal_to_application_entry(
        program,
        admission_cycle,
        {
            "campus": (campus or "").strip(),
            "intake_type": (intake_type or "").strip(),
            "program_level": (program_level or "").strip(),
        },
    )


# ═══════════════════════════════════════════════════════════════════
#  PAGE CONTEXT
# ═══════════════════════════════════════════════════════════════════

def get_context(context):
    _check_access(
        allowed_roles=["Applicant", "System Manager", "Administrator"],
        login_redirect="/admission/login"
    )
    """
    Builds the Jinja context for the application form web page.
    """
    from slcm.admission.utils.portal import admission_cycle_uses_applicant_web_form

    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/admission/login?redirect-to=/admission"
        raise frappe.Redirect

    applicant_name = (frappe.form_dict.get("applicant") or "").strip()
    applicant_loaded_early = False
    early_applicant_doc = None
    if applicant_name:
        try:
            if not frappe.db.exists("Applicant", applicant_name):
                frappe.local.flags.redirect_location = "/my-applications"
                raise frappe.Redirect
            doc = frappe.get_doc("Applicant", applicant_name)
            user = frappe.session.user
            email = frappe.db.get_value("User", user, "email") or user
            if doc.owner != user and (doc.email or "").lower() != (email or "").lower():
                frappe.local.flags.redirect_location = "/my-applications"
                raise frappe.Redirect
            if admission_cycle_uses_applicant_web_form(doc.admission_cycle):
                frappe.local.flags.redirect_location = f"/applicant-form/{applicant_name}"
                raise frappe.Redirect
            context.applicant_data = frappe.parse_json(frappe.as_json(doc))
            context.application_submitted = doc.status == "Submitted"
            context.application_editable = is_application_editable(doc)
            early_applicant_doc = doc
            applicant_loaded_early = True
        except frappe.Redirect:
            raise
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Application Form — redirect by applicant")
            frappe.local.flags.redirect_location = "/my-applications"
            raise frappe.Redirect

    user = frappe.session.user
    email = frappe.db.get_value("User", user, "email") or user

    url_program = (frappe.form_dict.get("program") or "").strip()
    url_cycle = (frappe.form_dict.get("admission_cycle") or "").strip()
    if not applicant_loaded_early:
        if url_program and url_cycle:
            if frappe.db.exists(
                "Admission Cycle Program",
                {"parent": url_cycle, "program": url_program, "is_active": 1},
            ):
                if admission_cycle_uses_applicant_web_form(url_cycle):
                    _redirect_portal_to_application_entry(url_program, url_cycle, frappe.form_dict)
            else:
                frappe.local.flags.redirect_location = "/admission"
                raise frappe.Redirect

    session_sel = (
        frappe.session.get("application_form_selection") or {}
        if hasattr(frappe.session, "get")
        else {}
    )
    sp = (session_sel.get("program") or "").strip()
    sc = (session_sel.get("admission_cycle") or "").strip()
    if not applicant_loaded_early:
        if sp and sc and frappe.db.exists(
            "Admission Cycle Program",
            {"parent": sc, "program": sp, "is_active": 1},
        ):
            if admission_cycle_uses_applicant_web_form(sc):
                _redirect_portal_to_application_entry(sp, sc, session_sel)

    if applicant_loaded_early and early_applicant_doc:
        prefill_prog = early_applicant_doc.program or ""
        prefill_cycle = early_applicant_doc.admission_cycle or ""
    else:
        prefill_prog = url_program or sp or ""
        prefill_cycle = url_cycle or sc or ""
        context.applicant_data = {}
        context.application_submitted = False
        context.application_editable = True

    if not applicant_loaded_early and prefill_prog and prefill_cycle:
        try:
            existing_rows = frappe.get_all(
                "Applicant",
                filters={
                    "admission_cycle": prefill_cycle,
                    "program": prefill_prog,
                    "email": email,
                },
                fields=["name"],
                limit=1,
            )
            if existing_rows:
                doc = frappe.get_doc("Applicant", existing_rows[0].name)
                context.applicant_data = frappe.parse_json(frappe.as_json(doc))
                context.application_submitted = doc.status == "Submitted"
                context.application_editable = is_application_editable(doc)
            else:
                allow_multi = int(
                    frappe.db.get_value(
                        "Admission Cycle", prefill_cycle, "allow_multiple_applications"
                    )
                    or 0
                )
                if allow_multi:
                    other = frappe.get_all(
                        "Applicant",
                        filters={
                            "email": email,
                            "admission_cycle": prefill_cycle,
                            "program": ["!=", prefill_prog],
                        },
                        fields=["name"],
                        order_by="modified desc",
                        limit=1,
                    )
                    if other:
                        src = frappe.get_doc("Applicant", other[0].name)
                        context.applicant_data = applicant_dict_for_multiprogram_copy(src)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Application Form — Get Applicant")
            context.applicant_data = {}

    app_data = context.applicant_data or {}
    
    # --- Fetch Offer Letter for this applicant ---
    context.offer_name = ""
    context.status = ""
    if app_data.get("name"):
        offer_letter = frappe.get_all("Offer Letter", 
            filters={"applicant": app_data.get("name")},
            fields=["name", "status"],
            order_by="creation desc",
            limit=1,
            ignore_permissions=True
        )
        if offer_letter:
            context.offer_name = offer_letter[0].name
            context.status = offer_letter[0].status

    if app_data.get("name") and app_data.get("status") != "Submitted":
        context.prefill_program = app_data.get("program") or session_sel.get("program") or prefill_prog
        context.prefill_admission_cycle = app_data.get("admission_cycle") or session_sel.get("admission_cycle") or prefill_cycle
        context.prefill_campus = app_data.get("campus") or session_sel.get("campus") or ""
        context.prefill_program_level = app_data.get("program_level") or session_sel.get("program_level") or ""
        context.prefill_intake_type = app_data.get("intake_type") or session_sel.get("intake_type") or ""
        context.prefill_academic_year = app_data.get("academic_year") or ""
        context.prefill_admission_year = app_data.get("admission_year") or ""
    else:
        _q = frappe.form_dict
        context.prefill_program = session_sel.get("program") or prefill_prog
        context.prefill_admission_cycle = session_sel.get("admission_cycle") or prefill_cycle
        context.prefill_campus = (
            session_sel.get("campus")
            or (_q.get("campus") or "").strip()
            or ""
        )
        context.prefill_program_level = (
            session_sel.get("program_level") or (_q.get("program_level") or "").strip() or ""
        )
        context.prefill_intake_type = (
            session_sel.get("intake_type") or (_q.get("intake_type") or "").strip() or ""
        )
        context.prefill_academic_year = ""
        context.prefill_admission_year = ""

    context.program_readonly = True  # Always lock: user must select from listing

    # Display name for the program (shown at top of form for information)
    program_code = context.prefill_program or (app_data.get("program") if app_data else None)
    if program_code:
        context.program_display_name = (
            frappe.db.get_value("Programme", program_code, "program_name") or program_code
        )
    else:
        context.program_display_name = ""

    # ── Academic + Admission year from Admission Cycle (before seeding) ──
    if context.prefill_admission_cycle:
        try:
            ad_year, ac_year = frappe.db.get_value(
                "Admission Cycle",
                context.prefill_admission_cycle,
                ["admission_year", "academic_year"],
            ) or (None, None)
        except Exception:
            ad_year, ac_year = (None, None)

        # Only fill from cycle when not already present on existing application
        if not getattr(context, "prefill_admission_year", None) and ad_year:
            context.prefill_admission_year = ad_year
        if not context.prefill_academic_year and ac_year:
            context.prefill_academic_year = ac_year or ""

    # When no existing application for this cycle, seed applicant_data with locked values and default Draft
    if not context.applicant_data or not context.applicant_data.get("name"):
        context.application_editable = True  # New application is editable
        context.applicant_data = dict(context.applicant_data or {})
        context.applicant_data.setdefault("program", context.prefill_program)
        context.applicant_data.setdefault("admission_cycle", context.prefill_admission_cycle)
        context.applicant_data.setdefault("campus", context.prefill_campus or "")
        context.applicant_data.setdefault("program_level", context.prefill_program_level or "")
        context.applicant_data.setdefault("academic_year", context.prefill_academic_year or "")
        context.applicant_data.setdefault("admission_year", context.prefill_admission_year or "")
        context.applicant_data.setdefault("application_type", context.prefill_intake_type or "")
        context.applicant_data.setdefault("docstatus", 0)
        context.applicant_data.setdefault("status", "Draft")
        # Prefill mobile from User if not set (default country code +91)
        user_mobile = frappe.db.get_value("User", user, "mobile_no")
        if user_mobile and not context.applicant_data.get("mobile_number"):
            mobile_str = (user_mobile or "").strip()
            if mobile_str and not mobile_str.startswith("+"):
                context.applicant_data.setdefault("mobile_number", "+91" + mobile_str.lstrip("0"))
            else:
                context.applicant_data.setdefault("mobile_number", mobile_str or "+91")

    # When application is submitted, these fields/sections stay read-only (no edit on submitted application)
    context.readonly_after_submit = [
        "email", "candidate_name", "mobile_number",
        "father_name", "father_email", "father_mobile", "father_occupation",
        "mother_name", "mother_email", "mother_mobile", "mother_occupation",
        "guardian_name", "guardian_mobile", "guardian_email",
        "correspondence_address", "city", "state", "pincode",
        "class_x_school", "class_x_board", "class_x_year_of_completion", "class_x_percentage", "class_x_cgpa",
        "class_xii_name_of_examination", "class_xii_school", "class_xii_board", "class_xii_year_of_completion", "hsc_group", "hsc_percentage",
        "national_test_name", "percentage", "ug_degree_completion",
        "first_preference", "second_preference", "third_preference",
        "whether_scstobc_ncl", "pwd", "karnataka_category",
        "caste_certificate", "pwd_certificate",
        "ka_study_7yrs", "ka_defence_child", "ka_govt_child", "ka_ais_child", "ka_capf_child",
        "ka_study_7yrs_certificate", "ka_defence_child_certificate", "ka_govt_child_certificate",
        "ka_ais_child_certificate", "ka_capf_child_certificate",
    ]

    # ── Programs (for UG/PG degree link selects in the form) ─────────────
    try:
        # level_of_study is the correct fieldname; program_level is null for PG/Research
        try:
            raw_programs = frappe.get_all(
                "Programme",
                fields=["name", "level_of_study"],
                filters={"program_status": "Active"},
                order_by="name asc"
            )
        except Exception:
            raw_programs = frappe.get_all(
                "Programme",
                fields=["name", "level_of_study"],
                order_by="name asc"
            )
        # Expose as program_level so the JS filter (p.program_level === 'Undergraduate' etc.) works
        context.programs = [
            {"name": p.name, "program_level": p.level_of_study or ""}
            for p in raw_programs
        ]
    except Exception:
        context.programs = []

    # ── Campuses: from Admission Cycle Program (this cycle + program only) ──
    # ignore_permissions: portal users are often Website User only (no Campus DocType read).
    try:
        campus_ids = _portal_unique_campuses_for_program_cycle(
            context.prefill_program, context.prefill_admission_cycle
        )
        if campus_ids:
            fetched = (
                frappe.get_all(
                    "Campus",
                    fields=["name", "campus_name"],
                    filters={"name": ["in", campus_ids], "is_active": 1},
                    order_by="campus_name asc",
                    ignore_permissions=True,
                )
                or []
            )
            order_map = {n: i for i, n in enumerate(campus_ids)}
            fetched.sort(key=lambda x: order_map.get(x.get("name"), 999))
            context.campuses = fetched
        else:
            # No campus in ACP: allow all active campuses for backward compatibility
            context.campuses = (
                frappe.get_all(
                    "Campus",
                    fields=["name", "campus_name"],
                    filters={"is_active": 1},
                    order_by="campus_name asc",
                    ignore_permissions=True,
                )
                or []
            )
    except Exception:
        context.campuses = []

    # Single campus for this program+cycle: prefill so save payload is never blank
    if len(context.campuses or []) == 1:
        sole = (context.campuses[0].get("name") or "").strip()
        if sole:
            if not (context.prefill_campus or "").strip():
                context.prefill_campus = sole
            ad = context.get("applicant_data") or {}
            if isinstance(ad, dict) and not (ad.get("campus") or "").strip():
                ad["campus"] = sole
                context.applicant_data = ad

    # ── Entrance Test Cities (for Test City preference dropdowns) ──
    try:
        context.entrance_test_cities = frappe.get_all(
            "Entrance Test City",
            fields=["name", "entrance_test_city_name"],
            order_by="entrance_test_city_name asc"
        )
        context.entrance_test_providers = context.entrance_test_cities
    except Exception:
        context.entrance_test_cities = []
        context.entrance_test_providers = []

    # ── Academic Years; ensure prefill year is in list ──────────────────
    try:
        context.academic_years = frappe.get_all(
            "Academic Year",
            fields=["name"],
            order_by="name desc"
        ) or []
        if context.prefill_academic_year and not any(
            (y.get("name") or y.name) == context.prefill_academic_year
            for y in context.academic_years
        ):
            context.academic_years = [{"name": context.prefill_academic_year}] + list(context.academic_years)
    except Exception:
        context.academic_years = []

    # ── Admission Cycles (active only); ensure prefill cycle is in list ─
    try:
        context.admission_cycles = frappe.get_all(
            "Admission Cycle",
            fields=["name"],
            filters={"status": "Active"},
            order_by="name desc"
        ) or []
        if context.prefill_admission_cycle and not any(
            (c.get("name") or c.name) == context.prefill_admission_cycle
            for c in context.admission_cycles
        ):
            context.admission_cycles = [{"name": context.prefill_admission_cycle}] + list(context.admission_cycles)
    except Exception:
        context.admission_cycles = []

    # ── Nationalities ─────────────────────────────────────────────────
    try:
        context.nationalities = frappe.get_all(
            "Country",
            fields=["name"],
            order_by="name asc"
        )
    except Exception:
        context.nationalities = []

    # ── HSC Groups ────────────────────────────────────────────────────
    try:
        context.hsc_groups = frappe.get_all("HSC Groups", fields=["name"], order_by="name asc")
    except Exception:
        context.hsc_groups = []

    # ── National Tests ────────────────────────────────────────────────
    try:
        context.national_tests = frappe.get_all("National Test", fields=["name"], order_by="name asc")
    except Exception:
        context.national_tests = []

    # ── States: from State DocType filtered by country (Nationality) ─────
    # State doctype has state_name, country. Initial states when applicant has nationality.
    app_data = context.get("applicant_data") or {}
    if app_data.get("nationality"):
        context.initial_states = _get_states_for_country(app_data.get("nationality"))
    else:
        context.initial_states = []

    # ── Cities: from City DocType filtered by state ─────────────────────
    if app_data.get("state"):
        context.initial_cities = _get_cities_for_state(app_data.get("state"))
    else:
        context.initial_cities = []

    # ── Form config: admission cycle → entrance test / program levels ───
    # Used to show/hide sections by program (e.g. PhD section only for Research Course)
    context.form_config = get_form_config_for_cycles()

    # ── UG final year note: from Applicant doc (if set) else default from DocType field options ──
    try:
        meta = frappe.get_meta("Applicant")
        default_note = (meta.get_field("ug_final_year_note").options or "") if meta and meta.get_field("ug_final_year_note") else ""
    except Exception:
        default_note = ""
    context.ug_final_year_note = (app_data.get("ug_final_year_note") or default_note or "").strip()

    # ── Test centre allocation note: from Applicant doc (if set) else default from DocType field options ──
    try:
        meta_tc = frappe.get_meta("Applicant")
        default_tc_note = (meta_tc.get_field("test_center_allocation_note").options or "") if meta_tc and meta_tc.get_field("test_center_allocation_note") else ""
    except Exception:
        default_tc_note = ""
    context.test_center_allocation_note = (app_data.get("test_center_allocation_note") or default_tc_note or "").strip()

    return context


def _get_states_for_country(country_name):
    """Return list of state names (State DocType: state_name, country) for the given country. Used for initial context."""
    if not (country_name and isinstance(country_name, str) and country_name.strip()):
        return []
    try:
        states = frappe.get_all(
            "State",
            filters={"country": country_name.strip()},
            fields=["name", "state_name"],
            order_by="state_name asc",
        )
        # State autoname is field:state_name, so name == state_name
        return [s.get("state_name") or s.get("name") for s in (states or [])]
    except Exception:
        return []


def _get_cities_for_state(state_name):
    """Return list of city names (City DocType) for the given state. Used for initial context."""
    if not (state_name and isinstance(state_name, str) and state_name.strip()):
        return []
    try:
        cities = frappe.get_all(
            "City",
            filters={"state": state_name.strip()},
            fields=["name", "city_name"],
            order_by="city_name asc",
        )
        # City autoname is field:city_name, so name == city_name
        return [c.get("city_name") or c.get("name") for c in (cities or [])]
    except Exception:
        return []


@frappe.whitelist(allow_guest=False)
def get_states_for_country(country=None):
    """Return states for the given country (State DocType: state_name, country).
    Used by application form to filter state dropdown when Nationality is selected."""
    country = (country or "").strip()
    if not country:
        return []
    return _get_states_for_country(country)


@frappe.whitelist(allow_guest=False)
def get_cities_for_state(state=None):
    """Return cities for the given state (City DocType: city_name, state; country optional).
    Used by application form to filter city dropdown when state is selected."""
    state = (state or "").strip()
    if not state:
        return []
    return _get_cities_for_state(state)


def get_form_config_for_cycles():
    """
    Returns a dict keyed by admission_cycle name: which program_levels and
    intake_types exist in that cycle (from Admission Cycle Program + Program).
    Enables the form to show fields relevant to the selected program/entrance test.
    """
    out = {}
    try:
        cycles = frappe.get_all(
            "Admission Cycle",
            fields=["name"],
            filters={"status": "Active"},
            order_by="name desc"
        )
        for c in cycles or []:
            cycle_name = c.name
            programs = frappe.get_all(
                "Admission Cycle Program",
                filters={"parent": cycle_name},
                fields=["program", "program_level", "intake_type"]
            )
            if not programs:
                # Fallback: get program_level from Program link
                programs = frappe.db.sql("""
                    SELECT acp.program, p.program_level, acp.intake_type
                    FROM `tabAdmission Cycle Program` acp
                    LEFT JOIN `tabProgramme` p ON p.name = acp.program
                    WHERE acp.parent = %s
                """, (cycle_name,), as_dict=True)
            levels = set()
            intake_types = set()
            for row in programs or []:
                prog = row.get("program") if isinstance(row, dict) else getattr(row, "program", None)
                pl = (row.get("program_level") if isinstance(row, dict) else getattr(row, "program_level", None)) or (frappe.db.get_value("Programme", prog, "program_level") if prog else None)
                it = row.get("intake_type") if isinstance(row, dict) else getattr(row, "intake_type", None)
                if pl:
                    levels.add(pl)
                if it:
                    intake_types.add(it)
            out[cycle_name] = {
                "program_levels": list(levels),
                "intake_types": list(intake_types),
            }
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Application Form — form_config")
    return out


# ═══════════════════════════════════════════════════════════════════
#  SAVE / SUBMIT API
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist()
def save_form(data):
    """
    Save (draft) or submit (final) an Applicant document.
    """
    # Frappe may pass data as a JSON string or already-parsed dict
    if isinstance(data, str):
        data = frappe.parse_json(data)
    if not isinstance(data, dict):
        return {"error": "Invalid data format."}

    user = frappe.session.user
    if user == "Guest":
        return {"error": _("You must be logged in to save an application.")}

    user_email = frappe.db.get_value("User", user, "email") or user
    is_submit = bool(data.get("__submit"))

    # ── Allow edits based on Admission Cycle Stage ─────────────
    existing_name = data.get("name")
    if existing_name:
        applicant = frappe.get_doc("Applicant", existing_name, ignore_permissions=True)
        if not is_application_editable(applicant):
            return {"error": _("This application is currently not editable as per its admission stage ('{0}').").format(applicant.status or "unknown")}
    try:
        meta = frappe.get_meta("Applicant")
    except Exception:
        return {"error": _("Applicant DocType not found. Please contact the administrator.")}

    SKIP_TYPES = {"Table", "Section Break", "Column Break", "Tab Break", "HTML", "Button"}
    valid_scalar_fields = {f.fieldname for f in meta.fields if f.fieldtype not in SKIP_TYPES}
    child_table_fields  = {"ug_degree_details", "pg_degree_details", "categories"}

    # ── Sanitise — only accept known fields ──────────────────────────
    sanitized = {}
    for key, value in data.items():
        if key.startswith("__"):
            continue
        if key in valid_scalar_fields or key in child_table_fields:
            sanitized[key] = value

    # ── Build and sanitize phone fields (E.164 for Frappe Phone fieldtype) ─
    PHONE_FIELDS = ("mobile_number", "alternate_contact", "father_mobile", "mother_mobile", "guardian_mobile")
    for field in PHONE_FIELDS:
        if field not in valid_scalar_fields:
            continue
        combined = sanitized.get(field)
        cc_key = field + "_cc"
        num_key = field + "_num"
        if not combined and (cc_key in data or num_key in data):
            cc = (data.get(cc_key) or "+91")
            if isinstance(cc, str) and not cc.startswith("+"):
                cc = "+" + cc
            num = (data.get(num_key) or "")
            if isinstance(num, str):
                num = "".join(c for c in num if c.isdigit())
            combined = (cc or "+91") + num
        sanitized[field] = sanitize_phone_for_frappe(combined)

    # ── One application per applicant per admission_cycle ─────────────
    admission_cycle = (sanitized.get("admission_cycle") or data.get("admission_cycle") or "").strip()
    if not admission_cycle:
        return {"error": _("Admission cycle is required. Please select a program from the admission listing.")}

    try:
        allow_multi = int(
            frappe.db.get_value(
                "Admission Cycle", admission_cycle, "allow_multiple_applications"
            )
            or 0
        )
        program = (sanitized.get("program") or data.get("program") or "").strip()

        if allow_multi and program:
            existing_name = frappe.db.get_value(
                "Applicant",
                {
                    "email": user_email,
                    "admission_cycle": admission_cycle,
                    "program": program,
                },
                "name",
            )
            if not existing_name:
                existing_name = frappe.db.get_value(
                    "Applicant",
                    {
                        "owner": user,
                        "admission_cycle": admission_cycle,
                        "program": program,
                    },
                    "name",
                )
        else:
            existing_name = frappe.db.get_value(
                "Applicant",
                {"email": user_email, "admission_cycle": admission_cycle},
                "name",
            )
            if not existing_name:
                existing_name = frappe.db.get_value(
                    "Applicant",
                    {"owner": user, "admission_cycle": admission_cycle},
                    "name",
                )
    except Exception:
        existing_name = None

    try:
        if existing_name:
            doc = frappe.get_doc("Applicant", existing_name)
        else:
            doc = frappe.new_doc("Applicant")
            doc.email = user_email
            doc.admission_cycle = admission_cycle
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "save_form — get/new doc")
        return {"error": _("Could not load application record: {0}").format(str(e))}

    # ── Apply scalar fields (respecting restricted editing rules) ──
    # Fields that can NEVER be edited after first save (even in Draft)
    RESTRICTED_ALWAYS = {"email", "mobile_number", "alternate_contact"}

    # Fields allowed in partial editing mode (only for submitted/non-draft)
    PARENT_FIELDS = {
        "father_name", "father_email", "father_mobile", "father_occupation",
        "mother_name", "mother_email", "mother_mobile", "mother_occupation",
        "guardian_required", "guardian_name", "guardian_mobile", "guardian_email"
    }

    scalar_data = {k: v for k, v in sanitized.items() if k not in child_table_fields}
    
    # If not a new application, enforce restrictions
    if doc.name and not doc.is_new():
        current_status = doc.status or "Draft"
        
        if current_status == "Draft":
            # In Draft: Strip fields that are restricted after first save
            for key in RESTRICTED_ALWAYS:
                scalar_data.pop(key, None)
        else:
            # In Partial Editing / Submitted: Strip everything EXCEPT parent fields
            # Also allow program-related fields so the 'Switch Programme' feature can update the record
            # even after a failed (Rejected) submission attempt.
            ALLOWED_ALONG_WITH_PARENTS = PARENT_FIELDS | {"program", "program_level", "campus", "admission_cycle", "application_type"}
            for key in list(scalar_data.keys()):
                if key not in ALLOWED_ALONG_WITH_PARENTS:
                    scalar_data.pop(key, None)

    # On submit, never overwrite fee status/amount from form (set by payment flow)
    if is_submit:
        for key in ("application_fee_status", "application_fee_amount"):
            scalar_data.pop(key, None)

    prog = (scalar_data.get("program") or getattr(doc, "program", None) or "").strip()
    cyc = (scalar_data.get("admission_cycle") or getattr(doc, "admission_cycle", None) or "").strip()
    inc_campus = scalar_data.get("campus")
    inc_campus = (inc_campus or "").strip() if isinstance(inc_campus, str) else ""
    if not inc_campus and prog and cyc:
        camps = _portal_unique_campuses_for_program_cycle(prog, cyc)
        if len(camps) == 1:
            scalar_data["campus"] = camps[0]

    try:
        doc.update(scalar_data)

        # Rejected + programme change: reset so user can re-submit
        if scalar_data.get("program") and doc.status == "Rejected":
            doc.status = "Draft"
            doc.evaluation_status = "Not Evaluated"
            doc.rejected_reason = ""
            for ct in ["ug_degree_details", "pg_degree_details", "categories"]:
                doc.set(ct, [])

        # Same cache key as start_application / get_context (not frappe.session dict)
        sid = frappe.session.sid
        sel = frappe.cache().hget("application_form_selection", sid) or {}
        if scalar_data.get("program"):
            sel["program"] = (scalar_data.get("program") or "").strip()
        if scalar_data.get("admission_cycle"):
            sel["admission_cycle"] = (scalar_data.get("admission_cycle") or "").strip()
        if scalar_data.get("campus"):
            sel["campus"] = (scalar_data.get("campus") or "").strip()
        frappe.cache().hset("application_form_selection", sid, sel)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "save_form — doc.update")
        return {"error": _("Error setting fields: {0}").format(str(e))}

    # ── Apply child tables (Draft only) ─────────────────────────────
    if not doc.name or doc.is_new() or (doc.status or "Draft") == "Draft":
        # Strip internal Frappe row-keys so append() doesn't try to match existing rows
        _INTERNAL_KEYS = {"name", "idx", "doctype", "parent", "parentfield", "parenttype",
                          "owner", "creation", "modified", "modified_by", "docstatus"}

        for ct_field in child_table_fields:
            if ct_field in sanitized:
                # Categories are a bit different, might be handled by scalar_data pop logic if needed
                # but usually categories are set once. Let's keep them draft-only too.
                doc.set(ct_field, [])
                rows = sanitized[ct_field]
                if isinstance(rows, list):
                    for row in rows:
                        if isinstance(row, dict):
                            clean_row = {
                                k: v for k, v in row.items()
                                if k not in _INTERNAL_KEYS and not k.startswith("__")
                            }
                            try:
                                doc.append(ct_field, clean_row)
                            except Exception:
                                pass  # Skip malformed rows silently

    # Always stamp the authenticated email — do not trust form input
    doc.email = user_email

    # ── Normalise academic metadata and program mapping ────────────────
    # Admission / Academic Year from Admission Cycle
    if getattr(doc, "admission_cycle", None):
        try:
            ad_year, ac_year = frappe.db.get_value(
                "Admission Cycle",
                doc.admission_cycle,
                ["admission_year", "academic_year"],
            ) or (None, None)
        except Exception:
            ad_year, ac_year = (None, None)

        if ad_year:
            doc.admission_year = ad_year
        if ac_year:
            doc.academic_year = ac_year

    # Program Level + Intake Type from Program
    if getattr(doc, "program", None):
        try:
            level_of_study, intake_type = frappe.db.get_value(
                "Programme",
                doc.program,
                ["level_of_study", "intake_type"],
            ) or (None, None)
        except Exception:
            level_of_study, intake_type = (None, None)

        if level_of_study:
            doc.program_level = level_of_study
        if intake_type:
            # This will also be enforced again by Applicant.set_intake_type on validate
            doc.intake_type = intake_type

    # Campus validation against Admission Cycle Program
    if getattr(doc, "admission_cycle", None) and getattr(doc, "program", None) and getattr(doc, "campus", None):
        try:
            acp_exists = frappe.db.exists(
                "Admission Cycle Program",
                {
                    "parent": doc.admission_cycle,
                    "program": doc.program,
                    "campus": doc.campus,
                    "is_active": 1,
                },
            )
        except Exception:
            acp_exists = True

        if not acp_exists:
            return {
                "error": _(
                    "Selected campus is not available for the chosen program and admission cycle. "
                    "Please start the application again from the admission listing."
                )
            }

    # ── Save or Submit ───────────────────────────────────────────────
    if not is_submit:
        doc.flags.ignore_mandatory = True

    try:
        doc.flags.ignore_permissions = True

        if is_submit:
            doc.status = "Submitted"
            # Save the record
            if not doc.name or doc.is_new():
                doc.insert(ignore_permissions=True)
            else:
                doc.save(ignore_permissions=True)

            frappe.db.commit()

            # Cache print PDF on Applicant.application_form (portal users often lack Print permission during hooks).
            try:
                from slcm.admission.doctype.applicant.applicant import (
                    ensure_application_form_pdf_for_applicant,
                )

                ensure_application_form_pdf_for_applicant(doc.name)
                frappe.db.commit()
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    "save_form — ensure_application_form_pdf_for_applicant after portal submit",
                )

            # Resolve program and campus for success page display (name, not ID)
            program_name = ""
            campus_name = ""
            if getattr(doc, "program", None):
                program_name = frappe.db.get_value("Programme", doc.program, "program_name") or doc.program or ""
            if getattr(doc, "campus", None):
                campus_name = frappe.db.get_value("Campus", doc.campus, "campus_name") or doc.campus or ""

            return {
                "status": "success",
                "name": doc.name,
                "message": _("Application submitted successfully."),
                "docstatus": doc.docstatus,
                "status": getattr(doc, "status", None),
                "program_name": program_name,
                "campus_name": campus_name,
                "exemptions": {
                    "entrance_test": bool(doc.exempts_entrance_test),
                    "interview": bool(doc.exempts_interview),
                    "rule_name": doc.national_test_rule_used
                }
            }
        else:
            doc.status = "Draft"
            doc.flags.ignore_mandatory = True
            
            if doc.is_new():
                doc.insert(ignore_permissions=True)
            else:
                doc.save(ignore_permissions=True)

            frappe.db.commit()

            return {
                "status": "draft",
                "name": doc.name,
                "message": _("Draft saved."),
                "docstatus": doc.docstatus,
                "status": doc.status,
            }

    except frappe.ValidationError as e:
        frappe.db.rollback()
        # Ensure e is converted to string safely
        try:
            raw_msg = str(e.args[0]) if (e.args and len(e.args) > 0) else str(e)
        except Exception:
            raw_msg = str(e)
        
        raw_msg = raw_msg or ""

        # Ensure we always try to get programs for the 'Switch Program' feature
        programs = []
        try:
            # We already have doc from earlier in the function
            if doc:
                programs = doc._build_program_eligibility_data() if hasattr(doc, '_build_program_eligibility_data') else []
        except Exception:
            pass

        # Special handling for rich ineligibility HTML coming from Applicant._build_ineligibility_message
        lower_msg = raw_msg.lower()
        if "ineligibility alert" in lower_msg or "program options" in lower_msg:
            try:
                unescaped = html.unescape(raw_msg)
            except Exception:
                unescaped = raw_msg

            cleaned = strip_html(unescaped or "") if unescaped else ""
            cleaned = cleaned.replace("Ineligibility Alert", "").strip()

            if not cleaned:
                cleaned = _("You are not eligible for the selected program. Please review the eligibility criteria.")

            return {"error": cleaned, "is_eligibility_error": True, "programs": programs}

        # Handle the combined message with '|'
        if "|" in raw_msg:
            return {"error": raw_msg, "is_eligibility_error": True, "programs": programs}

        # Fallback for all other validation errors
        return {"error": raw_msg, "programs": programs}

    except frappe.MandatoryError as e:
        frappe.db.rollback()
        return {"error": _("Required fields missing: {0}").format(str(e))}

    except frappe.DuplicateEntryError as e:
        frappe.db.rollback()
        return {"error": _("A duplicate entry was found: {0}").format(str(e))}

    except frappe.PermissionError:
        frappe.db.rollback()
        return {"error": _("You do not have permission to submit this application.")}

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Application Form — save_form")
        return {"error": _("Submission error: {0}").format(str(e))}


# ═══════════════════════════════════════════════════════════════════
#  ELIGIBILITY CHECK API  (called from portal JS)
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist()
def check_portal_eligibility(applicant_data):
    """
    Runs a lightweight eligibility check for the portal without saving the doc.
    """
    if isinstance(applicant_data, str):
        applicant_data = frappe.parse_json(applicant_data)

    program       = applicant_data.get("program")
    campus        = applicant_data.get("campus")
    admission_cycle = applicant_data.get("admission_cycle")
    academic_year = applicant_data.get("academic_year")

    if not all([program, campus, admission_cycle, academic_year]):
        return {
            "eligible": True,
            "message":  "Fill in Program, Campus, Admission Cycle and Academic Year to check eligibility.",
            "programs": []
        }

    try:
        doc = frappe.new_doc("Applicant")
        meta = frappe.get_meta("Applicant")
        valid_fields = {f.fieldname for f in meta.fields}

        for key, val in applicant_data.items():
            if key in valid_fields and not key.startswith("__"):
                try:
                    setattr(doc, key, val)
                except Exception:
                    pass

        # Set child tables
        for ct in ["ug_degree_details", "pg_degree_details", "categories"]:
            rows = applicant_data.get(ct)
            if rows and isinstance(rows, list):
                doc.set(ct, [])
                for row in rows:
                    if isinstance(row, dict):
                        doc.append(ct, row)

        doc.flags.ignore_permissions = True

        program_level = doc._get_selected_program_level() if hasattr(doc, '_get_selected_program_level') else frappe.db.get_value("Programme", program, "level_of_study")
        all_programs  = doc._get_all_programs_for_level(program_level) if hasattr(doc, '_get_all_programs_for_level') else [program]

        programs_result = []
        main_eligible   = True
        main_message    = "You meet the eligibility criteria for the selected program."

        for prog_name in all_programs:
            is_elig, reason = doc._check_eligibility_for_program(prog_name) if hasattr(doc, '_check_eligibility_for_program') else (True, "")
            programs_result.append({
                "program":  prog_name,
                "eligible": is_elig,
                "reason":   reason or ""
            })
            if prog_name == program and not is_elig:
                main_eligible = False
                main_message  = reason or "You do not meet the eligibility criteria for this program."

        nt_result = doc._evaluate_national_test_exemption() if hasattr(doc, '_evaluate_national_test_exemption') else {}

        return {
            "eligible": main_eligible,
            "message":  main_message,
            "programs": programs_result,
            "exemptions": {
                "entrance_test": bool(nt_result.get("exempts_entrance_test")),
                "interview": bool(nt_result.get("exempts_interview")),
                "rule_name": nt_result.get("rule_name") if nt_result.get("passed") else None
            }
        }

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Portal Eligibility Check Error")
        return {
            "eligible": True,
            "message":  "Eligibility check encountered an error. Please review the form.",
            "programs": []
        }


# ═══════════════════════════════════════════════════════════════════
#  FILE UPLOAD API
# ═══════════════════════════════════════════════════════════════════

ALLOWED_FILE_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
}


@frappe.whitelist(allow_guest=False)
def upload_applicant_file(doctype="Applicant", docname=None, is_private=0, fieldname=None):
    """
    Secure file upload for Applicant document.
    """
    if frappe.session.user == "Guest":
        return {"error": _("Login required to upload files.")}

    docname = docname or frappe.form_dict.get("docname") or frappe.form_dict.get("doc_name")
    doctype = (doctype or frappe.form_dict.get("doctype") or "Applicant").strip()
    is_private = 1  # Security Fix: Force all applicant uploads to be private
    fieldname = fieldname or frappe.form_dict.get("fieldname") or ""

    if doctype != "Applicant" or not docname:
        return {"error": _("Applicant document name is required.")}

    if not frappe.db.exists("Applicant", docname):
        return {"error": _("Applicant not found.")}

    # Permission check
    doc = frappe.get_doc("Applicant", docname)
    user = frappe.session.user
    user_email = frappe.db.get_value("User", user, "email") or user
    if doc.owner != user and doc.email != user_email:
        return {"error": _("You do not have permission to upload files for this application.")}

    # Get file from request
    file = None
    if hasattr(frappe, "request") and frappe.request.files:
        file = frappe.request.files.get("file") or frappe.request.files.get("file[]")
    if not file or not getattr(file, "filename", None):
        return {"error": _("No file in request. Use multipart/form-data with 'file' field.")}

    filename = (file.filename or "").strip()
    if not filename:
        return {"error": _("Invalid filename.")}

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_FILE_EXTENSIONS:
        return {"error": _("Allowed file types: PDF, JPG, JPEG, PNG only.")}

    content = file.read()
    if not content:
        return {"error": _("File is empty.")}

    content_type = getattr(file, "content_type", "") or ""
    if content_type and content_type.lower() not in ALLOWED_CONTENT_TYPES and ext not in ("jpg", "jpeg", "png", "pdf"):
        return {"error": _("Invalid file type.")}

    try:
        from frappe.utils.file_manager import save_file
        f = save_file(
            fname=filename,
            content=content,
            dt=doctype,
            dn=docname,
            folder=None,
            is_private=is_private,
            decode=False,
        )
        if not f:
            return {"error": _("Failed to save file.")}
        return {
            "file_name": f.file_name,
            "file_url": f.file_url,
            "attached_doctype": f.attached_to_doctype,
            "attached_document_name": f.attached_to_name,
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Applicant File Upload")
        return {"error": _("Upload failed: {0}").format(str(e))}


# ═══════════════════════════════════════════════════════════════════
#  APPLICATION FEE RECEIPT — GET RECEIPT FOR APPLICANT
# ═══════════════════════════════════════════════════════════════════
@frappe.whitelist(allow_guest=False)
def get_application_fee_receipt(applicant_name):
    """
    Returns the latest Applicant Payment Receipt name and print URL for
    the given applicant's application fee, verifying the caller owns it.
    """
    import urllib.parse

    # Verify ownership
    user = frappe.session.user
    user_email = frappe.db.get_value("User", user, "email") or user
    
    applicant_owner, applicant_email = frappe.db.get_value(
        "Applicant", applicant_name, ["owner", "email"]
    ) or (None, None)
    
    is_owner = (user != "Guest") and (
        user == "Administrator" or 
        applicant_owner == user or 
        (applicant_email and applicant_email.lower() == user_email.lower())
    )
    
    if not is_owner:
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    # Confirm fee is actually Paid or Waived
    fee_status = frappe.db.get_value("Applicant", applicant_name, "application_fee_status") or ""
    if fee_status not in ("Paid", "Waived"):
        return {"receipt_name": None, "fee_status": fee_status}

    # Fetch receipt
    receipts = frappe.get_all(
        "Applicant Payment Receipt",
        filters={"applicant": applicant_name, "offer_letter": ["in", ["", None]]},
        fields=["name"],
        order_by="creation desc",
        limit=1,
        ignore_permissions=True,
    )

    if not receipts:
        receipts = frappe.get_all(
            "Applicant Payment Receipt",
            filters={"applicant": applicant_name},
            fields=["name"],
            order_by="creation desc",
            limit=1,
            ignore_permissions=True,
        )

    if not receipts:
        return {"receipt_name": None, "fee_status": fee_status}

    receipt_name = receipts[0].name
    encoded_name = urllib.parse.quote(receipt_name)
    print_url = (
        f"/api/method/slcm.www.application_form.index.download_applicant_receipt"
        f"?applicant_name={urllib.parse.quote(applicant_name)}"
        f"&receipt_name={encoded_name}"
    )
    return {
        "receipt_name": receipt_name,
        "print_url": print_url,
        "fee_status": fee_status,
    }


@frappe.whitelist(allow_guest=False)
def download_applicant_receipt(applicant_name, receipt_name):
    """
    Whitelisted method to download the PDF of a receipt.
    """
    user = frappe.session.user
    user_email = frappe.db.get_value("User", user, "email") or user
    
    applicant_owner, applicant_email = frappe.db.get_value(
        "Applicant", applicant_name, ["owner", "email"]
    ) or (None, None)
    
    is_owner = (user != "Guest") and (
        user == "Administrator" or 
        applicant_owner == user or 
        (applicant_email and applicant_email.lower() == user_email.lower())
    )
    
    if not is_owner:
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    receipt_applicant = frappe.db.get_value("Applicant Payment Receipt", receipt_name, "applicant")
    if receipt_applicant != applicant_name:
        frappe.throw(_("Receipt does not belong to this applicant"), frappe.PermissionError)

    # Resolve print format
    print_format = "Applicant Payment Receipt Format"
    try:
        app = frappe.get_doc("Applicant", applicant_name)
        policy_name = None
        if app.admission_cycle and app.program:
            if app.campus:
                policy_name = frappe.db.get_value("Admission Cycle Program",
                    {"parent": app.admission_cycle, "program": app.program, "campus": app.campus, "is_active": 1},
                    "reservation_policy")
            if not policy_name:
                policy_name = frappe.db.get_value("Admission Cycle Program",
                    {"parent": app.admission_cycle, "program": app.program, "is_active": 1},
                    "reservation_policy")
            if policy_name:
                template = frappe.db.get_value("Programme Reservation Policy", policy_name, "payment_receipt_template")
                if template: print_format = template
    except Exception:
        pass

    try:
        doc = frappe.get_doc("Applicant Payment Receipt", receipt_name, ignore_permissions=True)
        frappe.flags.ignore_print_permissions = True
        pdf_content = frappe.get_print("Applicant Payment Receipt", receipt_name, print_format, as_pdf=True, doc=doc)
        frappe.local.response.filename = f"Receipt_{receipt_name}.pdf"
        frappe.local.response.filecontent = pdf_content
        frappe.local.response.type = "download"
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Receipt PDF Generation Failed")
        frappe.throw(_("Failed to generate PDF receipt: {0}").format(str(e)))

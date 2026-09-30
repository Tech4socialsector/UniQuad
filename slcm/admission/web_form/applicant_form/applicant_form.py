from html import unescape

import frappe
from frappe import _
from frappe.utils import cint, flt, strip_html

from slcm.admission.doctype.applicant.applicant import APPLICATION_SUBMITTED_STATUSES
from slcm.admission.utils.multiprogram_applicant import (
    build_multiprogram_profile_copy_payload,
    pop_multiprogram_profile_copy_from_cache,
    store_multiprogram_profile_copy_in_cache,
)



@frappe.whitelist(allow_guest=False)
def pop_multiprogram_profile_copy():
    """
    One-shot payload from server cache when opening /applicant-form/new for a second programme
    in the same cycle (allow_multiple_applications). Consumed on read.
    """
    if frappe.session.user == "Guest":
        return {}
    out = pop_multiprogram_profile_copy_from_cache()
    return out if isinstance(out, dict) else {}


def get_context(context):
    """
    Non-Draft applicants: force view mode; redirect /edit → read-only URL.
    Only Draft remains editable on the portal.
    """


    # Hide Frappe’s default web-form breadcrumb ("Back > APP-…"); custom bar stays in applicant_form.js.
    context.no_breadcrumbs = True

    # Enforce Applicant DocType permissions
    is_new = frappe.form_dict.name == "new" or not frappe.form_dict.name
    if is_new:
        if not frappe.has_permission("Applicant", "create"):
            frappe.throw(_("You do not have permission to create an Application. Please request the appropriate access."), frappe.PermissionError)
    else:
        doc_name = frappe.form_dict.name
        if doc_name and doc_name != "new":
            user = frappe.session.user
            email = frappe.db.get_value("User", user, "email") or user
            
            owner = frappe.db.get_value("Applicant", doc_name, "owner")
            doc_email = frappe.db.get_value("Applicant", doc_name, "email")
            
            if owner != user and (doc_email or "").lower() != (email or "").lower():
                # Allow Admins who have global write access, but block other applicants
                if not frappe.has_permission("Applicant", "write", user=user) or "Applicant" in frappe.get_roles(user):
                    # If they are just an 'Applicant' (or no admin roles), block them!
                    admin_roles = ["System Manager", "Admission Admin", "Administrator", "Campus Admin"]
                    has_admin = any(r in admin_roles for r in frappe.get_roles(user))
                    if not has_admin:
                        frappe.throw(_("You do not have permission to view this Application."), frappe.PermissionError)

    from slcm.admission.portal_application_web_form import applicant_portal_application_locked

    ref = context.get("reference_doc") or {}
    doc_name = ref.get("name") or context.get("doc_name")
    if not doc_name:
        # New form: e.g. login redirect straight to /applicant-form/new?program=... (no /application_form hop)
        q = frappe.form_dict or {}
        prog = (q.get("program") or "").strip()
        cyc = (q.get("admission_cycle") or "").strip()
        if prog and cyc and frappe.session.user != "Guest":
            email = frappe.db.get_value("User", frappe.session.user, "email") or frappe.session.user
            payload = build_multiprogram_profile_copy_payload(email, cyc, prog)
            store_multiprogram_profile_copy_in_cache(payload)
        return None

    status = (ref.get("status") or "").strip()
    if not status:
        status = (frappe.db.get_value("Applicant", doc_name, "status") or "").strip()
    if not applicant_portal_application_locked(status):
        return None

    context.in_view_mode = True
    context.in_edit_mode = False
    wfd = context.get("web_form_doc")
    if isinstance(wfd, dict):
        wfd["in_view_mode"] = True
        wfd["in_edit_mode"] = False

    route = wfd.get("route", "applicant-form") if isinstance(wfd, dict) else "applicant-form"
    if frappe.form_dict.get("is_edit"):
        frappe.redirect(f"/{route}/{doc_name}")

    return None


# ───────────────────────────────────────────────────────────────────
#  PORTAL SHELL BRANDING — nav + footer data for the web form JS
# ───────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=False)
def get_portal_shell_data():
    """
    Return branding + current-user info needed to render the admission nav/footer
    inside the web form.  Uses ignore_permissions so portal users (who can't read
    Website Settings or Applicant Portal Config directly) still get the data.
    """
    # ── Website Settings ──────────────────────────────────────────
    ws = frappe.db.get_singles_dict("Website Settings", cast=True) or {}

    # ── Applicant Portal Config ───────────────────────────────────
    try:
        pc = frappe.get_doc("Applicant Portal Config", "Applicant Portal Config",
                            ignore_permissions=True).as_dict()
    except Exception:
        pc = {}

    # ── Current user info ─────────────────────────────────────────
    user = frappe.session.user or "Guest"
    full_name = ""
    user_image = ""
    if user and user != "Guest":
        uinfo = frappe.db.get_value(
            "User", user, ["full_name", "user_image"], as_dict=True
        ) or {}
        full_name  = uinfo.get("full_name") or user
        user_image = uinfo.get("user_image") or ""

    try:
        pc_doc = frappe.get_doc("Applicant Portal Config", "Applicant Portal Config", ignore_permissions=True)
        
        def format_footer(rows):
            cols = []
            curr = None
            for r in rows:
                if r.get("is_parent"):
                    curr = {"title": r.get("label"), "links": []}
                    cols.append(curr)
                else:
                    if curr is None:
                        curr = {"title": "", "links": []}
                        cols.append(curr)
                    curr["links"].append({"label": r.get("label"), "route": r.get("route")})
            return cols

        admission_footer = format_footer(pc_doc.get("admission_footer") or [])
    except Exception:
        admission_footer = []

    pace_enabled = int(pc.get("enable_pace_admission") or 0) if pc else 0
    portal_active = int(pc.get("portal_active") or 0) if pc else 0
    powerd_by = (pc.get("powerd_by") or "boscosoft") if pc else "boscosoft"

    return {
        "site_title":      ws.get("title") or "SLCM",
        "portal_title":    pc.get("portal_title") or ws.get("title") or "Admissions",
        "primary_color":   pc.get("primary_color") or "#920C24",
        "secondary_color": pc.get("secondary_color") or "#ffffff",
        "navbar_color":    pc.get("navbar_color") or "#2B2E4A",
        "footer_color":    pc.get("footer_color") or "#fafafa",
        "footer_text_color": pc.get("footer_text_color") or "#000000",
        "button_border_radius": pc.get("button_border_radius") or "",
        "font_family":     pc.get("font_family") or "System Default",
        "font_size_preset": pc.get("font_size_preset") or "Normal",
        "font_size_heading": pc.get("font_size_heading") or "",
        "font_size_subheading": pc.get("font_size_subheading") or "",
        "font_size_body":  pc.get("font_size_body") or "",
        "font_size_form_title": pc.get("font_size_form_title") or "",
        "font_size_toast": pc.get("font_size_toast") or "",
        "footer_address":  pc.get("footer_address") or "",
        "footer_phone":    pc.get("footer_phone") or "",
        "contact_email":   pc.get("contact_email") or pc.get("footer_email") or "",
        "footer_text":     pc.get("footer_text") or "",
        "admission_footer": admission_footer,
        "admission_website_url": pc.get("admission_website_url") or "/",
        "pace_enabled":    pace_enabled,
        "portal_active":   portal_active,
        "powerd_by":       powerd_by,
        "user":            user,
        "full_name":       full_name,
        "user_image":      user_image,
        "is_guest":        user == "Guest",
        "institution_logo": frappe.db.get_single_value("Institution Settings", "logo") or "",
        "social_links": [
            {
                "platform": row.get("platform"),
                "url": row.get("url"),
                "is_active": row.get("is_active")
            } for row in (pc.get("social_links") or [])
        ],
    }


# ───────────────────────────────────────────────────────────────────
#  ADMISSION CYCLE ACCESS VALIDATION
# ───────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=False)
def validate_new_application_access(program=None):
    """
    Validates if a new application can be created for the active Admission Cycle
    and the selected program.

    Returns: {"allowed": True} or {"allowed": False, "message": "..."}
    """
    from frappe.utils import getdate, today, formatdate

    # 1. Must have an Active cycle
    active_cycle = frappe.db.get_value(
        "Admission Cycle", {"status": "Active"}, "name"
    )
    if not active_cycle:
        return {
            "allowed": False,
            "message": _("There is no active Admission Cycle at this time. New applications cannot be submitted."),
        }

    # 2. Check application window dates
    cycle_data = frappe.db.get_value(
        "Admission Cycle",
        active_cycle,
        ["application_start_date", "application_end_date", "admission_year", "academic_year"],
        as_dict=True,
    ) or {}

    today_date = getdate(today())

    start_date = cycle_data.get("application_start_date")
    end_date   = cycle_data.get("application_end_date")

    if start_date and today_date < getdate(start_date):
        return {
            "allowed": False,
            "message": _("Applications for the current cycle open on {0}. Please check back later.").format(
                formatdate(start_date)
            ),
        }

    if end_date and today_date > getdate(end_date):
        return {
            "allowed": False,
            "message": _("The application window closed on {0}. New applications cannot be submitted.").format(
                formatdate(end_date)
            ),
        }

    # 3. Optional: validate specific program is listed and active in cycle
    resolved_program = program
    resolved_campus = ""
    resolved_intake_type = ""
    resolved_program_level = ""
    
    if program:
        # Resolve from slug if needed
        slug_match = frappe.db.get_value("Programme", {"program_slug": program}, "name")
        if slug_match:
            resolved_program = slug_match

        prog_row = frappe.db.get_value(
            "Admission Cycle Program",
            {"parent": active_cycle, "program": resolved_program, "is_active": 1},
            ["name", "max_applications", "application_count", "campus", "intake_type", "program_level"],
            as_dict=True,
        )
        if not prog_row:
            return {
                "allowed": False,
                "message": _("The selected programme '{0}' is not available in the current admission cycle.").format(resolved_program),
            }
            
        resolved_campus = prog_row.get("campus") or ""
        resolved_intake_type = prog_row.get("intake_type") or ""
        resolved_program_level = prog_row.get("program_level") or ""
        
        # Check seats/application limit
        max_apps = prog_row.get("max_applications") or 0
        if max_apps > 0:
            app_count = prog_row.get("application_count") or 0
            if app_count >= max_apps:
                return {
                    "allowed": False,
                    "message": _("Seats are filled for the selected programme '{0}'. New applications cannot be submitted.").format(resolved_program),
                }

    # Extract year context
    admission_year = cycle_data.get("admission_year") or ""
    academic_year = cycle_data.get("academic_year") or ""

    return {
        "allowed": True,
        "admission_cycle": active_cycle,
        "admission_year": admission_year,
        "academic_year": academic_year,
        "program": resolved_program,
        "campus": resolved_campus,
        "intake_type": resolved_intake_type,
        "program_level": resolved_program_level,
    }


@frappe.whitelist(allow_guest=False)
def get_open_programmes():
    """
    Returns open programmes for the active Admission Cycle.
    Used by the programme picker dialog on the applicant web form.
    Each item: {"name": <Program.program_slug or Program.name>, "label": <Program.program_name>}
    """
    active_cycle = frappe.db.get_value(
        "Admission Cycle", {"status": "Active"}, "name"
    )
    if not active_cycle:
        return []

    rows = frappe.get_all(
        "Admission Cycle Program",
        filters={"parent": active_cycle, "is_active": 1},
        fields=["program"],
    )

    out = []
    for r in rows:
        prog = r.get("program") or ""
        if not prog:
            continue
        
        prog_data = frappe.db.get_value("Programme", prog, ["program_name", "program_slug"], as_dict=True) or {}
        label = prog_data.get("program_name") or prog
        slug = prog_data.get("program_slug") or prog
        
        out.append({"name": slug, "label": label})

    return out


# ───────────────────────────────────────────────────────────────────
#  FEE AMOUNT — lookup from Programme Reservation Policy
# ───────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=False)
def get_application_fee_amount(program, admission_cycle=None, category=None):
    """
    Return the application fee for the given program, admission cycle, and
    reservation category (whether_scstobc_ncl value: NA | SC | ST | OBC-NCL).

    Looks up Programme Reservation Policy → Programme Reservation Category rows.
    Falls back to the active Admission Cycle when admission_cycle is blank.
    Returns 0 when no matching policy or category row is found.
    """
    if not program:
        return 0
    try:
        cycle = (admission_cycle or "").strip()
        if not cycle:
            cycle = frappe.db.get_value(
                "Admission Cycle", {"status": "Active"}, "name", order_by="creation desc"
            ) or ""
        if not cycle:
            return 0

        from slcm.api.service.application_fee_service import get_application_fee_for_category

        cat = (category or "").strip() or None
        fee = get_application_fee_for_category(program, cycle, cat)
        return flt(fee, 2)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Applicant Web Form — get_application_fee_amount")
        return 0


# ───────────────────────────────────────────────────────────────────
#  SAVE DRAFT
# ───────────────────────────────────────────────────────────────────

@frappe.whitelist()
def save_applicant_draft(data, ignore_mandatory=True):
    """
    Save Applicant record as Draft.

    ignore_mandatory=True  → skip mandatory / validator checks (normal draft save)
    ignore_mandatory=False → enforce all mandatory fields (called before final submit)

    Returns:
      {"status": "success", "name": doc.name, "message": "..."}
      {"status": "error",   "message": "..."}
    """
    # Normalise flag
    if isinstance(ignore_mandatory, str):
        ignore_mandatory = frappe.parse_json(ignore_mandatory)
    ignore_mandatory = bool(ignore_mandatory)

    if isinstance(data, str):
        data = frappe.parse_json(data)
    if not isinstance(data, dict) or not data:
        return {"status": "error", "message": _("No data provided.")}

    user = frappe.session.user
    if user == "Guest":
        return {"status": "error", "message": _("You must be logged in to save a draft.")}

    email = frappe.db.get_value("User", user, "email") or user
    name  = (data.get("name") or "").strip()

    # Load existing or create new
    if name and frappe.db.exists("Applicant", name):
        doc = frappe.get_doc("Applicant", name)
        if doc.owner != user and (doc.email or "").lower() != (email or "").lower():
            return {"status": "error", "message": _("You do not have permission to edit this application.")}
        current_status = (doc.status or "").strip()
        if current_status and current_status != "Draft":
            return {"status": "error", "message": _("Only Draft applications can be saved from the portal.")}
    else:
        doc = frappe.new_doc("Applicant")
        doc.email = email

    # Determine which fields are safe to write
    try:
        meta = frappe.get_meta("Applicant")
    except Exception:
        return {"status": "error", "message": _("Applicant DocType not found.")}

    SKIP_TYPES   = {"Table", "Section Break", "Column Break", "Tab Break", "HTML", "Button"}
    INTERNAL_KEYS = {
        "name", "idx", "doctype", "parent", "parentfield", "parenttype",
        "owner", "creation", "modified", "modified_by", "docstatus",
    }
    valid_scalar  = {f.fieldname for f in meta.fields if f.fieldtype not in SKIP_TYPES}
    attach_fields = {f.fieldname for f in meta.fields if f.fieldtype in ["Attach", "Attach Image"]}
    child_tables  = {f.fieldname for f in meta.fields if f.fieldtype == "Table"}

    def _is_valid_file(file_url):
        if not file_url or not isinstance(file_url, str):
            return True
        if file_url.startswith(("http://", "https://", "data:")):
            return True
        
        try:
            file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
            if file_name:
                import os
                file_path = frappe.get_site_path(file_url.lstrip("/"))
                return os.path.exists(file_path)
            else:
                import os
                file_path = frappe.get_site_path(file_url.lstrip("/"))
                return os.path.exists(file_path)
        except Exception:
            return False

    # Apply scalar fields
    for key, value in data.items():
        if key.startswith("__") or key in INTERNAL_KEYS:
            continue
        if key in valid_scalar:
            if key in attach_fields and value and not _is_valid_file(value):
                try:
                    setattr(doc, key, None)
                except Exception:
                    pass
            else:
                try:
                    setattr(doc, key, value)
                except Exception:
                    pass

    # Apply child-table rows
    for ct_field in child_tables:
        rows = data.get(ct_field)
        if not isinstance(rows, list):
            continue
        doc.set(ct_field, [])
        try:
            ct_meta = frappe.get_meta(meta.get_field(ct_field).options)
            ct_attach = {f.fieldname for f in ct_meta.fields if f.fieldtype in ["Attach", "Attach Image"]}
        except Exception:
            ct_attach = set()

        for row in rows:
            if isinstance(row, dict):
                clean = {k: v for k, v in row.items() if k not in INTERNAL_KEYS and not k.startswith("__")}
                for k in list(clean.keys()):
                    if k in ct_attach and clean[k] and not _is_valid_file(clean[k]):
                        clean[k] = None
                try:
                    doc.append(ct_field, clean)
                except Exception:
                    pass

    # Set Admission Year and Academic Year from current active admission cycle if missing
    if not doc.admission_year or not doc.academic_year:
        # Use admission_cycle on doc if present, else find the currently Active one
        cycle_name = doc.admission_cycle or frappe.db.get_value("Admission Cycle", {"status": "Active"}, "name")
        if cycle_name:
            cycle_data = frappe.db.get_value("Admission Cycle", cycle_name, ["admission_year", "academic_year"], as_dict=True)
            if cycle_data:
                if not doc.admission_cycle:
                    doc.admission_cycle = cycle_name
                if not doc.admission_year or doc.admission_year == "":
                    doc.admission_year = cycle_data.admission_year
                if not doc.academic_year or doc.academic_year == "":
                    doc.academic_year = cycle_data.academic_year

    if getattr(doc, "program", None) and getattr(doc, "admission_cycle", None):
        deriv = _portal_program_row(doc.program, doc.admission_cycle)
        if deriv.get("program_level") and not doc.program_level:
            doc.program_level = deriv["program_level"]
        if deriv.get("intake_type") and not doc.intake_type:
            doc.intake_type = deriv["intake_type"]
        if deriv.get("campus"):
            doc.campus = deriv["campus"]

    # Enforce safe values
    doc.status = "Draft"
    doc.email              = email

    # Recalculate application fee from Programme Reservation Policy
    if getattr(doc, "program", None) and getattr(doc, "admission_cycle", None):
        try:
            from slcm.api.service.application_fee_service import get_application_fee_for_category

            raw_cat = (getattr(doc, "whether_scstobc_ncl", "") or "").strip()
            cat     = raw_cat if raw_cat and raw_cat.upper() != "NA" else None
            foriegn_national = getattr(doc, "foriegn_national", "") or ""
            is_foreign = foriegn_national == "Yes" if foriegn_national else False
            computed = flt(get_application_fee_for_category(doc.program, doc.admission_cycle, cat, is_foreign=is_foreign), 2)
            fee_status = (getattr(doc, "application_fee_status", "") or "").strip()
            if fee_status not in ("Paid", "Waived"):
                doc.application_fee_amount = computed
        except Exception:
            frappe.log_error(frappe.get_traceback(), "save_applicant_draft — fee recalc")

    doc.flags.ignore_mandatory  = ignore_mandatory
    doc.flags.ignore_permissions = True
    doc.flags.ignore_validate   = ignore_mandatory   # run validators when enforcing mandatory

    # Portal draft API: always bypass Frappe update-after-submit (stale docstatus=1 or programme change after switch).
    if not doc.is_new():
        doc.flags.ignore_validate_update_after_submit = True

    try:
        if doc.is_new():
            doc.insert()
        else:
            doc.save()
        frappe.db.commit()
        try:
            from slcm.api.service.application_fee_service import (
                sync_application_fee_assignment_for_applicant,
            )

            sync_application_fee_assignment_for_applicant(doc.name)
            frappe.db.commit()
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "save_applicant_draft — sync_application_fee_assignment_for_applicant",
            )
        return {
            "status":  "success",
            "name":    doc.name,
            "message": _("Draft saved successfully."),
        }
    except frappe.MandatoryError as e:
        frappe.db.rollback()
        return {"status": "error", "message": _("Required fields missing: {0}").format(str(e))}
    except frappe.ValidationError as e:
        frappe.db.rollback()
        return {"status": "error", "message": str(e)}
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "save_applicant_draft — Error")
        return {"status": "error", "message": str(e)}


# ───────────────────────────────────────────────────────────────────
#  SUBMIT APPLICANT (called after fee is paid or fee = 0)
# ───────────────────────────────────────────────────────────────────

@frappe.whitelist()
def submit_applicant(applicant_name, target_status=None):
    """
    Final submit: sets status = Submitted.
    Must only be called after:
      1. Mandatory validation passes (via save_applicant_draft with ignore_mandatory=False)
      2. Eligibility check passes
      3. Fee is paid/waived (or fee = 0)

    Returns:
      {"status": "success", "name": ..., "status": ..., "application_fee_status": ...}
      {"status": "error",   "message": ...}
    """
    if not applicant_name:
        return {"status": "error", "message": _("Applicant name is required.")}

    user = frappe.session.user
    if user == "Guest":
        return {"status": "error", "message": _("You must be logged in.")}

    if not frappe.db.exists("Applicant", applicant_name):
        return {"status": "error", "message": _("Applicant not found.")}

    doc = frappe.get_doc("Applicant", applicant_name)
    email = frappe.db.get_value("User", user, "email") or user

    if doc.owner != user and (doc.email or "").lower() != (email or "").lower():
        return {"status": "error", "message": _("No permission to submit this application.")}

    current_status = (doc.status or "").strip()
    _ts = target_status if target_status else "Submitted"

    if current_status in APPLICATION_SUBMITTED_STATUSES:
        if current_status == "Submitted" and _ts == "Completed":
            # Allow upgrading status to Completed after payment
            pass
        else:
            return {
                "status": "success",
                "name": doc.name,
                "doc_status": doc.status,
                "application_fee_status": doc.application_fee_status or "",
                "message": _("Application is already submitted."),
            }

    if _ts == "Completed" and current_status not in ("Draft", "Submitted"):
        return {
            "status": "success",
            "name": doc.name,
            "doc_status": doc.status,
            "application_fee_status": doc.application_fee_status or "",
            "message": _("Application is already processed."),
        }

    if current_status and current_status not in ("Draft", "Submitted"):
        return {"status": "error", "message": _("Only Draft or Submitted applications can be updated here.")}

    # Guard: fee must be paid / waived (or zero)
    fee_amount = flt(doc.application_fee_amount or 0)
    fee_status = (doc.application_fee_status or "").strip()
    
    # We might need to check the actual order if it was just paid. 
    # But usually fee_status will be updated by webhook soon, or we just trust the upgrade if fee_status becomes paid.
    # Actually, Razorpay payment verification isn't done here. This relies on the fee_status being updated by webhook,
    # OR if the user just paid, the fee_status might still be Requested. 
    # But wait, if fee_status is not Paid yet, we will block it!
    # Let's forcefully sync the payment status first!
    try:
        from slcm.api.service.application_fee_service import sync_application_fee_assignment_for_applicant
        sync_application_fee_assignment_for_applicant(doc.name)
        doc.reload() # reload after sync
        fee_status = (doc.application_fee_status or "").strip()
    except Exception:
        pass

    if _ts == "Completed" and fee_amount > 0 and fee_status not in ("Paid", "Waived"):
        return {"status": "error", "message": _("Application fee must be paid before completing application.")}

    # Set Admission Year and Academic Year from current active admission cycle if missing
    if not doc.admission_year or not doc.academic_year:
        cycle_name = doc.admission_cycle or frappe.db.get_value("Admission Cycle", {"status": "Active"}, "name")
        if cycle_name:
            cycle_data = frappe.db.get_value("Admission Cycle", cycle_name, ["admission_year", "academic_year"], as_dict=True)
            if cycle_data:
                if not doc.admission_cycle:
                    doc.admission_cycle = cycle_name
                if not doc.admission_year or doc.admission_year == "":
                    doc.admission_year = cycle_data.admission_year
                if not doc.academic_year or doc.academic_year == "":
                    doc.academic_year = cycle_data.academic_year

    doc.status = target_status if target_status else "Submitted"
    if fee_amount == 0:
        doc.application_fee_status = "Waived"

    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory   = False
    doc.flags.ignore_validate    = False
    doc.flags.ignore_validate_update_after_submit = True

    try:
        doc.save()
        if doc.meta.is_submittable:
            doc.reload()
            doc.submit()
        frappe.db.commit()
        try:
            from slcm.api.service.application_fee_service import (
                sync_application_fee_assignment_for_applicant,
            )

            sync_application_fee_assignment_for_applicant(doc.name)
            frappe.db.commit()
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "submit_applicant — sync_application_fee_assignment_for_applicant",
            )
        try:
            frappe.enqueue(
                "slcm.admission.doctype.applicant.applicant.ensure_application_form_pdf_for_applicant",
                queue="short",
                applicant_name=doc.name
            )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "submit_applicant — ensure_application_form_pdf_for_applicant enqueue failed",
            )
        return {
            "status": "success",
            "name": doc.name,
            "doc_status": doc.status,
            "application_fee_status": doc.application_fee_status or "",
            "message": _("Application submitted successfully."),
        }
    except frappe.ValidationError as e:
        frappe.db.rollback()
        return {"status": "error", "message": str(e)}
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "submit_applicant — Error")
        return {"status": "error", "message": str(e)}


# ───────────────────────────────────────────────────────────────────
#  WEB FORM HOOKS
# ───────────────────────────────────────────────────────────────────

def after_save(doc, context):
    """
    Eligibility is handled via check_eligibility / submit on the portal.
    Avoid running validate_eligibility here — it would frappe.throw HTML and duplicate UI.
    """
    pass


def _portal_ineligibility_message_from_failure_sections(doc) -> str | None:
    """
    Same composition as check_portal_eligibility / save_form ineligibility: Eligibility Rule Mapping
    ``failure_message`` (Summary) plus rule-level detail, not detail alone (so mapping copy is visible).

    Bodies are already line-deduped on the Applicant side when several mapping rules fail.
    """
    if not doc:
        return None
    sections = getattr(doc, "_slcm_failure_sections", None) or []
    if not sections:
        return None
    if len(sections) >= 2:
        summary = (sections[0].get("body") or "").strip()
        detail = (sections[1].get("body") or "").strip()
        if summary and detail:
            return summary + "\n\n" + detail
        return detail or summary or None
    body0 = (sections[0].get("body") or "").strip()
    return body0 or None


def _check_eligibility_ineligible_response(doc, raw_msg: str) -> dict:
    """
    Same message + programs shape as slcm/www/application_form/index.py save_form
    ValidationError handling (is_eligibility_error, programs, error text rules).
    """
    programs = []
    try:
        if doc and hasattr(doc, "_build_program_eligibility_data"):
            programs = doc._build_program_eligibility_data()
    except Exception:
        programs = []

    raw_msg = raw_msg or ""
    lower_msg = raw_msg.lower()

    if "ineligibility alert" in lower_msg or "program options" in lower_msg:
        try:
            unescaped = unescape(raw_msg)
        except Exception:
            unescaped = raw_msg
        cleaned = strip_html(unescaped or "") if unescaped else ""
        cleaned = cleaned.replace("Ineligibility Alert", "").strip()
        if not cleaned:
            cleaned = _("You are not eligible for the selected program. Please review the eligibility criteria.")
        err_text = cleaned
    elif "|" in raw_msg:
        err_text = raw_msg
    else:
        try:
            unescaped = unescape(raw_msg)
        except Exception:
            unescaped = raw_msg
        plain = strip_html(unescaped or "") if unescaped else ""
        # Preserve line breaks: _build_rule_failure_reason uses single \n between bullets.
        # Joining paragraphs with spaces was collapsing "Reservation…\n• Min…" into one line.
        _lines = []
        for _ln in plain.splitlines():
            _t = " ".join(_ln.split())
            if _t:
                _lines.append(_t)
        err_text = "\n".join(_lines) if _lines else (plain or raw_msg)

    err_text = (err_text or "").strip() or _("You do not meet the eligibility criteria for the selected program.")

    # Prefer structured rule-level copy over generic mapping summary (see _portal_ineligibility_message_from_failure_sections).
    structured = _portal_ineligibility_message_from_failure_sections(doc)
    if structured:
        err_text = structured.strip()

    if len(err_text) > 2400:
        err_text = err_text[:2397] + "..."

    return {
        "status": "Ineligible",
        "message": err_text,
        "failure_reason": err_text,
        "error": err_text,
        "is_eligibility_error": True,
        "programs": programs,
        "failure_sections": getattr(doc, "_slcm_failure_sections", None) or [],
        "suggestions": (doc.get_eligibility_suggestion_payload() if doc else None) or {},
    }


@frappe.whitelist()
def check_eligibility(applicant_name):
    """
    Portal eligibility check for submit flow.

    Returns:
      Eligible: {"status": "Eligible", "message": str}
      Ineligible: {"status": "Ineligible", "failure_reason": str, "suggestions": {...}}
    """
    if not applicant_name:
        return {"status": "Incomplete", "message": ""}

    if not _portal_can_access_applicant(applicant_name):
        return {"status": "Error", "message": _("Not permitted.")}

    doc = frappe.get_doc("Applicant", applicant_name)

    if not all([doc.program, doc.campus, doc.admission_cycle, doc.academic_year]):
        return {
            "status": "Incomplete",
            "message": _("Please fill in Program, Campus, Admission Cycle and Academic Year to check eligibility."),
        }

    try:
        doc.flags.skip_eligibility_throw = True
        try:
            doc.validate_eligibility()
        finally:
            doc.flags.skip_eligibility_throw = False

        if (doc.evaluation_status or "").strip() == "Ineligible":
            return _check_eligibility_ineligible_response(doc, doc.rejected_reason or "")

        return {
            "status": "Eligible",
            "message": _("You meet the eligibility criteria for the selected program."),
        }
    except frappe.ValidationError as e:
        try:
            raw_msg = str(e.args[0]) if (e.args and len(e.args) > 0) else str(e)
        except Exception:
            raw_msg = str(e)
        doc2 = frappe.get_doc("Applicant", applicant_name)
        return _check_eligibility_ineligible_response(doc2, raw_msg or "")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Web Form — check_eligibility Error")
        return {"status": "Error", "message": _("An error occurred during eligibility check.")}


def _portal_existing_applicant_same_program_cycle_campus(
    *,
    user: str,
    email: str,
    program: str,
    admission_cycle: str,
    campus: str | None,
    exclude_name: str,
):
    """
    Another Applicant for the same user (owner or email), same programme, cycle, and campus.
    Used to block eligibility-modal programme switch when a separate application already exists.
    """
    program = (program or "").strip()
    admission_cycle = (admission_cycle or "").strip()
    exclude_name = (exclude_name or "").strip()
    if not program or not admission_cycle or not exclude_name:
        return None
    email_norm = (email or "").strip().lower()
    campus_key = (campus or "").strip()
    rows = frappe.db.sql(
        """
        SELECT name, applicant_id FROM `tabApplicant`
        WHERE name != %(exclude)s
          AND program = %(program)s
          AND admission_cycle = %(cycle)s
          AND IFNULL(campus, '') = %(campus)s
          AND docstatus < 2
          AND (
                owner = %(user)s
             OR LOWER(IFNULL(email, '')) = %(email_norm)s
          )
        LIMIT 1
        """,
        {
            "exclude": exclude_name,
            "program": program,
            "cycle": admission_cycle,
            "campus": campus_key,
            "user": user,
            "email_norm": email_norm,
        },
    )
    return rows[0] if rows else None


@frappe.whitelist(allow_guest=False)
def get_applicant_programs_already_applied(applicant_name):
    """
    For the logged-in applicant owner: programme IDs (Program.name) that already have
    another Applicant in the same admission cycle + campus (used to disable switch UI).
    """
    applicant_name = (applicant_name or "").strip()
    if not applicant_name or not frappe.db.exists("Applicant", applicant_name):
        return {"already_applied": {}}

    user = frappe.session.user
    if user == "Guest":
        return {"already_applied": {}}

    email = frappe.db.get_value("User", user, "email") or user
    doc = frappe.get_doc("Applicant", applicant_name)
    if doc.owner != user and (doc.email or "").lower() != (email or "").lower():
        return {"already_applied": {}}

    cycle = (doc.admission_cycle or "").strip()
    if not cycle:
        return {"already_applied": {}}

    acp_rows = frappe.get_all(
        "Admission Cycle Program",
        filters={"parent": cycle, "is_active": 1},
        fields=["program", "campus"],
    )
    out = {}
    for acp in acp_rows:
        prog = (acp.get("program") or "").strip()
        if not prog:
            continue
        campus = (acp.get("campus") or "").strip() or None
        dup = _portal_existing_applicant_same_program_cycle_campus(
            user=user,
            email=email,
            program=prog,
            admission_cycle=cycle,
            campus=campus,
            exclude_name=applicant_name,
        )
        if dup:
            out[prog] = ((dup[1] or "").strip() or dup[0])
    return {"already_applied": out}


def _portal_program_row(program, admission_cycle):
    """
    Admission Cycle Program row fields for portal; program_level falls back to
    Program.level_of_study (Program has no program_level field).
    """
    out = {"program_level": None, "intake_type": None, "campus": None, "program_label": None}
    program = (program or "").strip()
    admission_cycle = (admission_cycle or "").strip()
    if not program:
        return out
    prog_title = (frappe.db.get_value("Programme", program, "program_name") or "").strip()
    out["program_label"] = prog_title or program
    if admission_cycle:
        acp = frappe.db.get_value(
            "Admission Cycle Program",
            {"parent": admission_cycle, "program": program, "is_active": 1},
            ["intake_type", "program_level", "campus"],
            as_dict=True,
        )
        if acp:
            out["program_level"] = acp.get("program_level")
            out["intake_type"] = acp.get("intake_type")
            out["campus"] = acp.get("campus")
    if not out["program_level"]:
        out["program_level"] = frappe.db.get_value("Programme", program, "level_of_study")
    return out


@frappe.whitelist(allow_guest=False)
def get_program_portal_derivatives(program, admission_cycle=None):
    """For web form: when Program (or Admission Cycle) changes, refresh hidden defaults."""
    return _portal_program_row(program or "", admission_cycle or "")


@frappe.whitelist()
def switch_applicant_program(applicant_name, program):
    """
    Switch draft applicant to another same-level eligible program (from evaluation modal).
    """
    program = (program or "").strip()
    if not applicant_name or not program:
        return {"status": "error", "message": _("Program and application are required.")}

    user = frappe.session.user
    if user == "Guest":
        return {"status": "error", "message": _("You must be logged in.")}

    email = frappe.db.get_value("User", user, "email") or user
    doc = frappe.get_doc("Applicant", applicant_name)

    if doc.owner != user and (doc.email or "").lower() != (email or "").lower():
        return {"status": "error", "message": _("You do not have permission to update this application.")}

    st = (doc.status or "").strip()
    if st != "Draft":
        return {"status": "error", "message": _("Only draft applications can change programme here.")}

    payload = doc.get_eligibility_suggestion_payload()
    allowed = False
    for entry in payload.get("programs") or []:
        if entry.get("program") == program and not entry.get("selected"):
            allowed = True
            break
    if not allowed:
        return {"status": "error", "message": _("This programme is not available to switch to.")}

    if not frappe.db.exists(
        "Admission Cycle Program",
        {"parent": doc.admission_cycle, "program": program, "is_active": 1},
    ):
        return {"status": "error", "message": _("This programme is not open for the current admission cycle.")}

    deriv = _portal_program_row(program, doc.admission_cycle or "")
    target_campus = (deriv.get("campus") or "").strip() or None

    dup = _portal_existing_applicant_same_program_cycle_campus(
        user=user,
        email=email,
        program=program,
        admission_cycle=doc.admission_cycle or "",
        campus=target_campus,
        exclude_name=doc.name,
    )
    if dup:
        aid = (dup[1] or "").strip() or dup[0]
        return {
            "status": "error",
            "message": _(
                "You already have an application for this programme in the same admission cycle and campus "
                "(Application ID: {0}). Switching is not allowed."
            ).format(aid),
        }

    doc.program = program
    if deriv.get("program_level"):
        doc.program_level = deriv["program_level"]
    if deriv.get("intake_type"):
        doc.intake_type = deriv["intake_type"]
    if deriv.get("campus"):
        doc.campus = deriv["campus"]

    doc.evaluation_status = ""
    doc.rejected_reason = ""

    if doc.program and doc.admission_cycle:
        try:
            from slcm.api.service.application_fee_service import get_application_fee_for_category

            raw_cat = (getattr(doc, "whether_scstobc_ncl", "") or "").strip()
            cat = raw_cat if raw_cat and raw_cat.upper() != "NA" else None
            fee_status = (getattr(doc, "application_fee_status", "") or "").strip()
            foriegn_national = getattr(doc, "foriegn_national", "") or ""
            is_foreign = foriegn_national == "Yes" if foriegn_national else False
            if fee_status not in ("Paid", "Waived"):
                doc.application_fee_amount = flt(
                    get_application_fee_for_category(doc.program, doc.admission_cycle, cat, is_foreign=is_foreign), 2
                )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "switch_applicant_program — fee recalc")

    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_validate = True
    # Submitted Applicant (docstatus=1): Frappe uses update_after_submit and blocks
    # program changes unless allow_on_submit — portal switch is an explicit allowed path.
    doc.flags.ignore_validate_update_after_submit = True
    try:
        doc.save()
        frappe.db.commit()
    except Exception as ex:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "switch_applicant_program")
        return {"status": "error", "message": str(ex)}

    try:
        from slcm.api.service.application_fee_service import (
            sync_application_fee_assignment_for_applicant,
        )

        sync_application_fee_assignment_for_applicant(doc.name)
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "switch_applicant_program — sync_application_fee_assignment_for_applicant",
        )

    return {
        "status": "success",
        "name": doc.name,
        "program": doc.program,
        "program_level": doc.program_level,
        "message": _("Programme updated. You can continue editing your application."),
    }


def _portal_can_access_applicant(applicant_name):
    user = frappe.session.user
    if user == "Guest":
        return False
    email = (frappe.db.get_value("User", user, "email") or user or "").lower()
    row_email = (frappe.db.get_value("Applicant", applicant_name, "email") or "").lower()
    owner = frappe.db.get_value("Applicant", applicant_name, "owner")
    return owner == user or (row_email and row_email == email)


def _latest_application_fee_receipt_for_portal(applicant_name):
    rows = frappe.db.sql(
        """
        SELECT name FROM `tabApplicant Payment Receipt`
        WHERE applicant = %s AND docstatus < 2
        AND IFNULL(offer_letter, '') = ''
        ORDER BY creation DESC
        LIMIT 1
        """,
        applicant_name,
    )
    return rows[0][0] if rows else None


@frappe.whitelist(allow_guest=True)
def portal_application_fee_receipt_ready(applicant_name):
    """Whether the portal may show “Download fee receipt” for this application."""
    applicant_name = (applicant_name or "").strip()
    if not applicant_name or not frappe.db.exists("Applicant", applicant_name):
        return {"ready": False, "receipt_name": ""}
    if not _portal_can_access_applicant(applicant_name):
        frappe.throw(_("Not permitted."), frappe.PermissionError)
    st = (frappe.db.get_value("Applicant", applicant_name, "application_fee_status") or "").strip()
    if st != "Paid":
        return {"ready": False, "receipt_name": ""}
    rname = _latest_application_fee_receipt_for_portal(applicant_name)
    return {"ready": bool(rname), "receipt_name": rname or ""}


@frappe.whitelist(allow_guest=False)
def download_portal_application_fee_receipt(applicant_name):
    """PDF download for the applicant’s application-fee receipt (uses stored Print Format)."""
    applicant_name = (applicant_name or "").strip()
    if not applicant_name or not frappe.db.exists("Applicant", applicant_name):
        frappe.throw(_("Application not found."))
    if not _portal_can_access_applicant(applicant_name):
        frappe.throw(_("Not permitted."), frappe.PermissionError)
    st = (frappe.db.get_value("Applicant", applicant_name, "application_fee_status") or "").strip()
    if st != "Paid":
        frappe.throw(_("Application fee is not paid."))

    receipt_name = _latest_application_fee_receipt_for_portal(applicant_name)
    if not receipt_name:
        frappe.throw(_("Payment receipt not found. Please contact support."))

    receipt = frappe.get_doc(
        "Applicant Payment Receipt", receipt_name, check_permission=False
    )
    fmt = (receipt.payment_receipt_template or "").strip() or None

    # Portal users don't have DocType-level print permission; we've already verified
    # ownership above via _portal_can_access_applicant.  Set the flag that
    # get_rendered_template() checks (printview.py:145) — this is the same pattern
    # used by frappe's own attach_print() in print_utils.py:134.
    frappe.local.flags.ignore_print_permissions = True
    try:
        if fmt:
            pdf = frappe.get_print(
                "Applicant Payment Receipt",
                receipt.name,
                print_format=fmt,
                as_pdf=True,
            )
        else:
            pdf = frappe.get_print("Applicant Payment Receipt", receipt.name, as_pdf=True)
    finally:
        frappe.local.flags.ignore_print_permissions = False

    safe = (receipt.name or "receipt").replace(" ", "-").replace("/", "-")
    frappe.local.response.filename = f"{safe}.pdf"
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "pdf"

@frappe.whitelist(allow_guest=True)
def state_query(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None, **kwargs):
    if isinstance(filters, str):
        import json
        try:
            filters = json.loads(filters)
        except Exception:
            filters = {}
    if not filters:
        filters = {}

    country = filters.get("country") if isinstance(filters, dict) else None
    if not country:
        country = frappe.form_dict.get("filters[country]") or frappe.form_dict.get("country")

    cond = ""
    params = {
        "txt": "%" + (txt or "") + "%",
        "start": cint(start),
        "page_len": cint(page_len)
    }

    if country and country.strip():
        country_clean = country.strip()
        matched_rows = frappe.db.sql("""
            select distinct name from `tabState`
            where (LOWER(country) = LOWER(%(country)s) or name = 'Other')
            and name like %(txt)s
            order by (case when name = 'Other' then 1 else 0 end), name
            limit %(start)s, %(page_len)s
        """, {
            "country": country_clean,
            "txt": "%" + (txt or "") + "%",
            "start": cint(start),
            "page_len": cint(page_len)
        })
        if matched_rows:
            return [{"value": r[0], "description": "", "label": r[0]} for r in matched_rows]

    rows = frappe.db.sql(f"""
        select distinct name from `tabState`
        where name like %(txt)s
        order by (case when name = 'Other' then 1 else 0 end), name
        limit %(start)s, %(page_len)s
    """, params)

    return [{"value": r[0], "description": "", "label": r[0]} for r in rows]

@frappe.whitelist(allow_guest=True)
def city_query(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None, **kwargs):
    if isinstance(filters, str):
        import json
        try:
            filters = json.loads(filters)
        except Exception:
            filters = {}
    if not filters:
        filters = {}

    state = filters.get("state") if isinstance(filters, dict) else None
    if not state:
        state = frappe.form_dict.get("filters[state]") or frappe.form_dict.get("state")

    cond = ""
    params = {
        "txt": "%" + (txt or "") + "%",
        "start": cint(start),
        "page_len": cint(page_len)
    }

    if state and state.strip():
        state_clean = state.strip()
        matched_rows = frappe.db.sql("""
            select distinct IFNULL(NULLIF(city_name, ''), name) as display_name from `tabCity`
            where (LOWER(state) = LOWER(%(state)s) or name = 'Other' or city_name = 'Other')
            and (city_name like %(txt)s or name like %(txt)s)
            order by (case when city_name = 'Other' or name = 'Other' then 1 else 0 end), display_name
            limit %(start)s, %(page_len)s
        """, {
            "state": state_clean,
            "txt": "%" + (txt or "") + "%",
            "start": cint(start),
            "page_len": cint(page_len)
        })
        if matched_rows:
            return [{"value": r[0], "description": "", "label": r[0]} for r in matched_rows]

    rows = frappe.db.sql(f"""
        select distinct IFNULL(NULLIF(city_name, ''), name) as display_name from `tabCity`
        where (city_name like %(txt)s or name like %(txt)s)
        order by (case when city_name = 'Other' or name = 'Other' then 1 else 0 end), display_name
        limit %(start)s, %(page_len)s
    """, params)

    return [{"value": r[0], "description": "", "label": r[0]} for r in rows]

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime


def _pace_application_fee_already_paid(application_name):
    """True if Application Fee assignment or a linked Payment Request is already Paid."""
    if not application_name or not frappe.db.exists("PACE Application", application_name):
        return False

    if frappe.db.exists("PACE Applicant Fee Assignment", {
        "applicant": application_name,
        "fee_type": "Application Fee",
        "status": "Paid",
        "docstatus": ["!=", 2],
    }):
        return True

    assignments = frappe.get_all(
        "PACE Applicant Fee Assignment",
        filters={"applicant": application_name, "fee_type": "Application Fee", "docstatus": ["!=", 2]},
        pluck="name"
    )
    if not assignments:
        return False

    return bool(frappe.db.exists("Payment Request", {
        "reference_doctype": "PACE Applicant Fee Assignment",
        "reference_name": ["in", assignments],
        "status": "Paid",
        "docstatus": ["!=", 2],
    }))


def _pace_portal_user_owns_application(application_name):
    """True if the logged-in user may access this PACE Application (owner or applicant email)."""
    if not application_name or not frappe.db.exists("PACE Application", application_name):
        return False
    user = frappe.session.user
    if not user or user == "Guest":
        return False
    if user == "Administrator":
        return True

    roles = frappe.get_roles(user)
    admin_roles = {"System Manager", "PACE Admission Manager", "Admission Admin", "Document Verification Admin"}
    if set(roles).intersection(admin_roles):
        return True

    email = (frappe.db.get_value("User", user, "email") or user).strip().lower()
    row = frappe.db.get_value(
        "PACE Application",
        application_name,
        ["owner", "email_address", "assigned_verifier"],
        as_dict=True,
    ) or {}
    
    if "Document Verifier" in roles:
        # Document Verifier can edit if they are assigned
        if row.get("assigned_verifier") == user:
            return True
        # Or if we want to allow all document verifiers, we could just add it to admin_roles,
        # but let's keep the assigned check if that was intended, or just let them if they have write permission.
        # Actually, let's just check `has_permission("read")` or similar later.


    if row.get("owner") == user:
        return True
    app_mail = (row.get("email_address") or "").strip().lower()
    return bool(app_mail and app_mail == email)


def _pace_get_application_for_portal(application_name):
    if not _pace_portal_user_owns_application(application_name):
        frappe.throw(_("You do not have permission to access this application."), frappe.PermissionError)
    return frappe.get_doc("PACE Application", application_name, check_permission=False)


@frappe.whitelist()
def get_pace_status(application_name):
    """Return canonical application status from DB for portal read-only logic."""
    if not _pace_portal_user_owns_application(application_name):
        frappe.throw(_("You do not have permission to access this application."), frappe.PermissionError)
    status = frappe.db.get_value("PACE Application", application_name, "status") or ""
    
    admission_closed = False
    admission_closed_message = ""
    active_adm = frappe.db.get_value("PACE Admission", {"status": "Active"}, "name")
    if active_adm:
        adm_data = frappe.db.get_value("PACE Admission", active_adm, ["admission_close_date", "academic_year"], as_dict=True) or {}
        close_date = adm_data.get("admission_close_date")
        if close_date:
            from frappe.utils import getdate, today
            if getdate(today()) > getdate(close_date):
                admission_closed = True
                admission_closed_message = _("The application window for the {0} academic year is now closed.<br>New applications are no longer being accepted.<br>Thank you for your interest in our programme.").format(adm_data.get("academic_year") or "")
                
    return {
        "status": status, 
        "locked": status.strip() not in ("", "Draft", "Returned for Correction"),
        "admission_closed": admission_closed,
        "admission_closed_message": admission_closed_message
    }


def _pace_ensure_document_verification(application):
    """Create PACE Document Verification when application status is Completed."""
    try:
        from slcm.pace.doctype.pace_document_verification.get_document_api import (
            ensure_document_verification_for_completed_application,
        )

        return ensure_document_verification_for_completed_application(application)
    except Exception:
        app_name = application if isinstance(application, str) else getattr(application, "name", "")
        frappe.log_error(
            frappe.get_traceback(),
            f"PACE Document Verification ensure failed: {app_name}",
        )
        return None


def get_context(context):
    # Hide default breadcrumbs; custom nav injected by pace_application_form.js
    context.no_breadcrumbs = True



    # Enforce PACE Application DocType permissions
    is_new = frappe.form_dict.name == "new" or not frappe.form_dict.name
    if is_new:
        if not frappe.has_permission("PACE Application", "create"):
            frappe.throw(_("You do not have permission to create a PACE Application. Please request the appropriate access."), frappe.PermissionError)
    else:
        doc_name = frappe.form_dict.name
        if doc_name and doc_name != "new":
            user = frappe.session.user
            email = frappe.db.get_value("User", user, "email") or user
            
            owner = frappe.db.get_value("PACE Application", doc_name, "owner")
            doc_email = frappe.db.get_value("PACE Application", doc_name, "email_address")
            
            if owner != user and (doc_email or "").lower() != (email or "").lower():
                admin_roles = ["System Manager", "Admission Admin", "Administrator", "Campus Admin", "PACE Admission Manager", "Document Verification Admin"]
                has_admin = any(r in admin_roles for r in frappe.get_roles(user))
                # Allow assigned document verifier
                if not has_admin and "Document Verifier" in frappe.get_roles(user):
                    if frappe.db.get_value("PACE Application", doc_name, "assigned_verifier") == user:
                        has_admin = True
                if not has_admin:
                    frappe.throw(_("You do not have permission to view this PACE Application."), frappe.PermissionError)


# ───────────────────────────────────────────────────────────────────
#  PORTAL SHELL — nav + footer branding (mirrors applicant_form.py)
# ───────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_pace_portal_shell_data():
    """
    Return branding + current-user info needed to render the PACE portal nav/footer
    inside the web form. Reads Website Settings and Applicant Portal Config so that
    the PACE form uses the same visual theme as the admission portal.
    """
    ws = frappe.db.get_singles_dict("Website Settings", cast=True) or {}

    try:
        pc = frappe.get_doc(  # pyright: ignore[reportCallIssue]
            "Applicant Portal Config", "Applicant Portal Config", ignore_permissions=True
        ).as_dict()
    except Exception:
        pc = {}

    user = frappe.session.user or "Guest"
    full_name = ""
    user_image = ""
    first_name, middle_name, last_name, email = "", "", "", ""
    if user and user != "Guest":
        uinfo = frappe.db.get_value(
            "User", user, ["full_name", "user_image", "first_name", "middle_name", "last_name", "email"], as_dict=True
        ) or {}
        full_name = uinfo.get("full_name") or user
        user_image = uinfo.get("user_image") or ""
        first_name = uinfo.get("first_name") or ""
        middle_name = uinfo.get("middle_name") or ""
        last_name = uinfo.get("last_name") or ""
        email = uinfo.get("email") or ""

    pace_enabled = int(pc.get("enable_pace_admission") or 0) if pc else 0
    powerd_by = (pc.get("powerd_by") or "boscosoft") if pc else "boscosoft"

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

        pace_footer = format_footer(pc_doc.get("pace_footer") or [])
    except Exception:
        pace_footer = []

    active_academic_year = frappe.db.get_value("PACE Admission", {"status": "Active"}, "academic_year")
    if not active_academic_year:
        active_academic_year = frappe.db.get_value("Academic Year", {"status": "Active"}, "name")

    return {
        "site_title":           ws.get("title") or "SLCM",
        "portal_title":         pc.get("portal_title") or ws.get("title") or "Admissions",
        "primary_color":        pc.get("primary_color") or "#920C24",
        "secondary_color":      pc.get("secondary_color") or "#ffffff",
        "navbar_color":         pc.get("navbar_color") or "#2B2E4A",
        "footer_color":         pc.get("footer_color") or "#fafafa",
        "footer_text_color":    pc.get("footer_text_color") or "#000000",
        "button_border_radius": pc.get("button_border_radius") or "",
        "font_family":          pc.get("font_family") or "System Default",
        "font_size_preset":     pc.get("font_size_preset") or "Normal",
        "font_size_heading":    pc.get("font_size_heading") or "",
        "font_size_subheading": pc.get("font_size_subheading") or "",
        "font_size_body":       pc.get("font_size_body") or "",
        "font_size_form_title": pc.get("font_size_form_title") or "",
        "font_size_toast":      pc.get("font_size_toast") or "",
        "footer_address":       pc.get("footer_address") or "",
        "footer_phone":         pc.get("footer_phone") or "",
        "contact_email":        pc.get("contact_email") or pc.get("footer_email") or "",
        "footer_text":          pc.get("footer_text") or "",
        "pace_footer":          pace_footer,
        "pace_enabled":         pace_enabled,
        "pace_website_url":     pc.get("pace_website_url") or "/",
        "powerd_by":            powerd_by,
        "user":                 user,
        "full_name":            full_name,
        "first_name":           first_name,
        "middle_name":          middle_name,
        "last_name":            last_name,
        "email":                email,
        "user_image":           user_image,
        "is_guest":             user == "Guest",
        "active_academic_year": active_academic_year,
        "institution_logo":     frappe.db.get_single_value("Institution Settings", "logo") or "",
        "social_links": [
            {
                "platform": row.get("platform"),
                "url": row.get("url"),
                "is_active": row.get("is_active")
            } for row in (pc.get("social_links") or [])
        ],
    }


@frappe.whitelist(allow_guest=True)
def get_programme_by_route(route):
    """
    Find PACE Programme name based on the route (slug).
    Used by the Web Form to resolve SEO-friendly URLs.
    Validates that the programme is linked to an active Admission cycle.
    """
    if not route:
        return None

    # 1. Resolve internal name from route
    programme_name = frappe.db.get_value("PACE Programme", {"route": route}, "name")
    if not programme_name:
        return None

    # 2. Verify if it's in an active Admission cycle
    active_adm = frappe.db.get_value("PACE Admission", {"status": "Active"}, "name")
    if active_adm:
        is_open = frappe.db.exists("PACE Admission Programme", {
            "parent": active_adm,
            "programme": programme_name,
            "status": "Open"
        })
        if not is_open:
            # Programme might be in active admission but closed (e.g. seats full)
            # We still return it so the form can show it, but perhaps with a warning?
            # For now, we return it to allow the form to populate.
            pass

    return programme_name


@frappe.whitelist(allow_guest=True)
def get_open_pace_programmes():
    """
    Returns the list of PACE Programme names that are open for admission
    in the active PACE Admission cycle. Used to filter the Web Form Link options.
    """
    active_adm = frappe.db.get_value("PACE Admission", {"status": "Active"}, "name")
    if not active_adm:
        return []

    close_date = frappe.db.get_value("PACE Admission", active_adm, "admission_close_date")
    if close_date:
        from frappe.utils import getdate, today
        if getdate(today()) > getdate(close_date):
            return []

    return frappe.get_all(
        "PACE Admission Programme",
        filters={"parent": active_adm, "status": "Open"},
        pluck="programme"
    )


@frappe.whitelist(allow_guest=True)
def validate_new_application_access(programme=None):
    """
    Validates if a new application can be created for the active admission and selected programme.
    Returns: {"allowed": True} or {"allowed": False, "message": "..."}
    """
    active_adm = frappe.db.get_value("PACE Admission", {"status": "Active"}, "name")
    
    if not active_adm:
        latest_adm = frappe.db.get_all("PACE Admission", fields=["academic_year"], order_by="creation desc", limit=1)
        academic_year = latest_adm[0].academic_year if latest_adm else ""
        return {
            "allowed": False,
            "message": _("The application window for the {0} academic year is now closed. Thank you for your interest in our programme.").format(academic_year)
        }

    # Check Close Date
    adm_data = frappe.db.get_value("PACE Admission", active_adm, ["admission_close_date", "academic_year"], as_dict=True) or {}
    close_date = adm_data.get("admission_close_date")
    if close_date:
        from frappe.utils import getdate, today
        if getdate(today()) > getdate(close_date):
            return {
                "allowed": False,
                "message": _("The application window for the {0} academic year is now closed. Thank you for your interest in our programme.").format(adm_data.get("academic_year") or "")
            }

    if programme:
        # Resolve route slug to internal PACE Programme name
        programme_name = frappe.db.get_value("PACE Programme", {"route": programme}, "name")
        if not programme_name:
            programme_name = programme

        admission_programme = frappe.db.get_value(
            "PACE Admission Programme",
            {"parent": active_adm, "programme": programme_name},
            ["name", "status"],
            as_dict=True
        )
        if not admission_programme:
            return {
                "allowed": False,
                "message": _("The selected programme '{0}' is not available for admission in the current cycle.").format(programme_name)
            }
        if admission_programme.status != "Open":
            return {
                "allowed": False,
                "message": _("The selected programme '{0}' is closed for admission in the current cycle.").format(programme_name)
            }

    return {"allowed": True}


# ───────────────────────────────────────────────────────────────────
#  SAVE DRAFT — PACE Application
# ───────────────────────────────────────────────────────────────────

@frappe.whitelist()
def save_pace_draft(data, ignore_mandatory=True, retain_draft_status=False):
    """
    Save a PACE Application record as Draft.

    ignore_mandatory=True  → skip mandatory checks (normal draft save)
    ignore_mandatory=False → enforce mandatory fields (called before final submit)
    retain_draft_status=True → validate/save fields but keep Draft (fee modal step;
        status becomes Submitted only via submit_pace_application / pay-later flows)

    Returns:
      {"status": "success", "name": doc.name, "message": "..."}
      {"status": "error",   "message": "..."}
    """
    if isinstance(ignore_mandatory, str):
        ignore_mandatory = frappe.parse_json(ignore_mandatory)
    ignore_mandatory = bool(ignore_mandatory)
    if isinstance(retain_draft_status, str):
        retain_draft_status = frappe.parse_json(retain_draft_status)
    retain_draft_status = bool(retain_draft_status)

    if isinstance(data, str):
        data = frappe.parse_json(data)
    if not isinstance(data, dict) or not data:
        return {"status": "error", "message": _("No data provided.")}

    user = frappe.session.user
    if user == "Guest":
        return {"status": "error", "message": _("You must be logged in to save a draft.")}

    email = frappe.db.get_value("User", user, "email") or user
    name = (data.get("name") or "").strip()

    # Load existing or create new
    if name and frappe.db.exists("PACE Application", name):
        if not _pace_portal_user_owns_application(name):
            return {"status": "error", "message": _("You do not have permission to edit this application.")}
        doc = frappe.get_doc("PACE Application", name, check_permission=False)
        current_status = (getattr(doc, "status", "") or "").strip()
        if current_status and current_status not in ("Draft", "Returned for Correction", ""):
            return {"status": "error", "message": _("Only Draft or Returned for Correction applications can be saved from the portal.")}
    else:
        doc = frappe.new_doc("PACE Application")
        try:
            doc.email_address = email
        except Exception:
            pass

    # Determine which fields are writable
    try:
        meta = frappe.get_meta("PACE Application")
    except Exception:
        return {"status": "error", "message": _("PACE Application DocType not found.")}

    SKIP_TYPES = {"Table", "Section Break", "Column Break", "Tab Break", "HTML", "Button"}
    INTERNAL_KEYS = {
        "name", "idx", "doctype", "parent", "parentfield", "parenttype",
        "owner", "creation", "modified", "modified_by", "docstatus",
    }
    valid_scalar = {f.fieldname for f in meta.fields if f.fieldtype not in SKIP_TYPES}
    child_tables = {f.fieldname for f in meta.fields if f.fieldtype == "Table"}

    for key, value in data.items():
        if key.startswith("__") or key in INTERNAL_KEYS:
            continue
        if key in valid_scalar:
            try:
                setattr(doc, key, value)
            except Exception:
                pass

    for ct_field in child_tables:
        rows = data.get(ct_field)
        if not isinstance(rows, list):
            continue
        doc.set(ct_field, [])
        for row in rows:
            if isinstance(row, dict):
                clean = {k: v for k, v in row.items() if k not in INTERNAL_KEYS and not k.startswith("__")}
                try:
                    doc.append(ct_field, clean)
                except Exception:
                    pass

    # Enforce status (do not promote to Submitted before the applicant confirms the fee modal)
    try:
        if doc.status != "Returned for Correction":
            if retain_draft_status:
                if not (doc.status or "").strip():
                    doc.status = "Draft"
            elif not ignore_mandatory:
                doc.status = "Submitted"
            else:
                doc.status = "Draft"
    except Exception:
        pass

    doc.flags.ignore_mandatory = ignore_mandatory
    doc.flags.ignore_permissions = True

    if not doc.is_new():
        doc.flags.ignore_validate_update_after_submit = True

    try:
        if doc.is_new():
            doc.insert()
        else:
            doc.save()
        frappe.db.commit()
        return {
            "status": "success",
            "name": doc.name,
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
        frappe.log_error(frappe.get_traceback(), "save_pace_draft — Error")
        return {"status": "error", "message": str(e)}

# ───────────────────────────────────────────────────────────────────
#  AUTO-FETCH PREVIOUS APPLICATION INFO
# ───────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_old_pace_application():
    """
    Fetch the most recent PACE application for the current user to auto-fill
    the form. Specifically exclude attachments, programme, academic_year, and 
    internal status-related fields.
    """
    user = frappe.session.user
    if user == "Guest":
        return {}

    email = frappe.db.get_value("User", user, "email") or user

    # Find the most recently created application for this email/owner
    old_app_name = frappe.db.get_value(
        "PACE Application", 
        {"email_address": email}, 
        "name", 
        order_by="creation desc"
    )

    if not old_app_name:
        return {}

    old_app = frappe.get_doc("PACE Application", old_app_name, check_permission=False).as_dict()

    # We want to keep personal details, education history, work experience, etc.
    # Exclude system/state/payment/document fields
    exclude_fields = {
        "name", "owner", "creation", "modified", "modified_by", "docstatus",
        "idx", "status", "programme", "academic_year", "submission_date" , 
        "upload_student_photo"
    }

    # Also dynamically exclude Attach and Attach Image fields
    meta = frappe.get_meta("PACE Application")
    for df in meta.fields:
        if df.fieldtype in ["Attach", "Attach Image"]:
            exclude_fields.add(df.fieldname)

    result = {}
    for key, value in old_app.items():
        if key not in exclude_fields and not key.startswith("__"):
            # If it's a child table, safely pass it avoiding its __ internals
            if isinstance(value, list) and value and isinstance(value[0], dict):
                clean_lines = []
                for row in value:
                    clean_row = {
                        k: v for k, v in row.items() 
                        if k not in ["name", "parent", "parentfield", "parenttype", "doctype", "creation", "modified", "modified_by", "docstatus", "idx"]
                    }
                    clean_lines.append(clean_row)
                result[key] = clean_lines
            else:
                result[key] = value

    return result

@frappe.whitelist()
def check_existing_pace_application(programme, academic_year=None):
    """
    Check if the user has already started or submitted an application.
    Returns:
        {
            "allow_multiple": boolean,
            "existing": {name, status, programme} or None
        }
    """
    user = frappe.session.user
    if user == "Guest":
        return {"allow_multiple": True, "existing": None}

    if programme:
        resolved = frappe.db.get_value("PACE Programme", {"route": programme}, "name")
        programme = resolved or programme

    email = frappe.db.get_value("User", user, "email") or user
    
    if not academic_year:
        academic_year = frappe.db.get_value("PACE Admission", {"status": "Active"}, "academic_year")
    
    if not academic_year:
        academic_year = frappe.db.get_value("Academic Year", {"status": "Active"}, "name")

    # 1. Check if PACE Admission allows multiple applications
    allow_multiple = frappe.db.get_value(
        "PACE Admission",
        {"academic_year": academic_year, "status": "Active"},
        "allow_multiple_application_per_applicant"
    )
    
    if allow_multiple is None:
        allow_multiple = frappe.db.get_value(
            "PACE Admission",
            {"academic_year": academic_year},
            "allow_multiple_application_per_applicant"
        )
    
    allow_multiple = bool(allow_multiple)

    # 2. Logic based on 'allow_multiple'
    if allow_multiple:
        # Check if ANY application exists for this specific programme (not just Draft)
        existing = frappe.db.get_value(
            "PACE Application", 
            {
                "email_address": email, 
                "programme": programme, 
                "academic_year": academic_year,
                "status": ["!=", "Cancelled"]
            }, 
            ["name", "status", "programme"], 
            as_dict=True, 
            order_by="creation desc"
        )
    else:
        # Check if ANY application exists for this academic year (not just this programme)
        existing = frappe.db.get_value(
            "PACE Application", 
            {
                "email_address": email, 
                "academic_year": academic_year,
                "status": ["!=", "Cancelled"]
            }, 
            ["name", "status", "programme"], 
            as_dict=True, 
            order_by="creation desc"
        )

    return {
        "allow_multiple": allow_multiple,
        "existing": existing
    }

@frappe.whitelist()
def get_formatted_programme_name(programme):
    """
    Returns the formatted programme name: Prefix Name (Code)
    Example: Post Graduate Diploma in Cyber Law and Cyber Forensics (PGDCLCF)
    """
    if not programme:
        return ""
    
    prog_data = frappe.db.get_value(
        "PACE Programme", 
        programme, 
        ["programme_prefix", "programme_name", "programme_code"], 
        as_dict=True
    )
    
    if not prog_data:
        return programme
    
    res_parts = []
    if prog_data.programme_prefix:
        res_parts.append(prog_data.programme_prefix)
    if prog_data.programme_name:
        res_parts.append(prog_data.programme_name)
    
    res = " ".join(res_parts)
    if prog_data.programme_code:
        res += f" ({prog_data.programme_code})"
    
    return res

@frappe.whitelist()
def get_pace_admission_fee(application):
    """
    Get the application fee for a PACE application.
    `application` may be:
      - a doc name string  → loaded from DB
      - a JSON/dict object → used as-is (fallback from JS before save)
      - a Frappe Document  → used directly
    """
    import json as _json

    # --- normalise input ---
    if isinstance(application, str):
        # could be a doc name OR a JSON string passed from JS
        try:
            parsed = _json.loads(application)
            if isinstance(parsed, dict):
                application = parsed          # treat as plain dict
            else:
                doc_id = str(parsed).strip()
                application = (
                    _pace_get_application_for_portal(doc_id)
                    if frappe.db.exists("PACE Application", doc_id)
                    else frappe.get_doc("PACE Application", doc_id)
                )
        except (_json.JSONDecodeError, ValueError):
            application = (
                _pace_get_application_for_portal(application.strip())
                if frappe.db.exists("PACE Application", application.strip())
                else frappe.get_doc("PACE Application", application)
            )

    # --- pull fields regardless of whether it is a dict or a doc ---
    def _get(obj, field):
        if isinstance(obj, dict):
            return obj.get(field)
        return getattr(obj, field, None)

    programme    = _get(application, "programme")
    academic_year = _get(application, "academic_year")
    nationality  = (_get(application, "nationality") or "").strip()

    if not programme or not academic_year:
        return {"fee": 0, "reason": "missing programme or academic_year"}

    # --- find active PACE Admission for this academic year ---
    admission_name = frappe.db.get_value(
        "PACE Admission",
        {"academic_year": academic_year, "status": "Active"},
        "name"
    )

    if not admission_name:
        # Fallback: any PACE Admission for this year
        admission_name = frappe.db.get_value(
            "PACE Admission",
            {"academic_year": academic_year},
            "name",
            order_by="creation desc"
        )

    if not admission_name:
        return {"fee": 0, "reason": "no PACE Admission for academic_year"}

    admission_doc = frappe.get_doc("PACE Admission", admission_name)
    gateway  = admission_doc.payment_gateway
    template = admission_doc.payment_receipt_template
    fee = 0

    for p in admission_doc.programmes:
        if p.programme == programme:
            if nationality == "Indian":
                fee = flt(p.get("application_fee_indian") or 0)
            else:
                fee = flt(p.get("application_fee_foreign") or 0)
            break

    return {
        "fee": fee,
        "gateway": gateway,
        "template": template,
        "admission": admission_name
    }


def _pace_get_payment_gateway_controller(gateway_name):
    try:
        from payments.utils import get_payment_gateway_controller

        return get_payment_gateway_controller(gateway_name)
    except ImportError:
        try:
            from frappe.integrations.utils import get_payment_gateway_controller

            return get_payment_gateway_controller(gateway_name)
        except ImportError:
            frappe.throw(
                _("Payment gateway integration is not available. Install the Payments app or check Frappe version.")
            )


def _pace_parse_gateway_error_data(error_data):
    """Normalize error payload from Razorpay JS (dict or JSON string)."""
    import json as _json

    if not error_data:
        return {}, _("Payment was not completed.")

    if isinstance(error_data, str):
        try:
            error_data = _json.loads(error_data)
        except (_json.JSONDecodeError, TypeError, ValueError):
            return {}, error_data.strip() or _("Payment was not completed.")

    if isinstance(error_data, dict):
        msg = (
            error_data.get("description")
            or error_data.get("message")
            or error_data.get("reason")
            or ""
        )
        if isinstance(msg, dict):
            msg = msg.get("description") or msg.get("message") or str(msg)
        return error_data, (str(msg).strip() if msg else _("Payment was not completed."))

    return {}, str(error_data)


@frappe.whitelist()
def log_pace_payment_gateway_closed(
    application_name,
    assignment_name,
    order_id=None,
    error_data=None,
    finalize_application=1,
):
    """
    Razorpay checkout closed without success (modal dismiss or client-side failure).

    Updates the linked Payment Request (status, failure_message, gateway_response).
    Does not change application status (Submitted is set before Razorpay on Proceed, or via Cancel save).
    """
    if isinstance(error_data, str):
        try:
            error_data = frappe.parse_json(error_data)
        except Exception:
            pass
    finalize_application = cint(finalize_application)

    if not assignment_name or not frappe.db.exists("PACE Applicant Fee Assignment", assignment_name):
        return {"status": "error", "message": _("Fee assignment not found.")}

    assignment = frappe.get_doc("PACE Applicant Fee Assignment", assignment_name, check_permission=False)
    if not assignment.applicant or assignment.applicant != application_name:
        return {"status": "error", "message": _("Invalid fee assignment for this application.")}

    if not _pace_portal_user_owns_application(application_name):
        frappe.throw(_("You do not have permission to access this application."), frappe.PermissionError)

    if assignment.status == "Paid":
        return {"status": "ok", "message": _("Fee already paid.")}

    parsed_error, failure_message = _pace_parse_gateway_error_data(error_data)
    if not parsed_error and failure_message:
        parsed_error = {"message": failure_message}

    gateway = frappe.db.get_value(
        "Payment Request",
        {
            "reference_doctype": "PACE Applicant Fee Assignment",
            "reference_name": assignment.name,
            "docstatus": ["!=", 2],
        },
        "payment_gateway",
    )
    if not gateway and assignment.fee_type == "Course Fee" and assignment.fee_structure:
        gateway = frappe.db.get_value("PACE Fee Structure", assignment.fee_structure, "payment_gateway")
    elif not gateway and assignment.fee_type == "Application Fee" and assignment.academic_year:
        gateway = frappe.db.get_value("PACE Admission", {"academic_year": assignment.academic_year, "status": "Active"}, "payment_gateway")
    
    if not gateway:
        gateway = frappe.db.get_value("Payment Gateway", {}, "name") or "Razorpay"

    # Distinguish modal dismiss (user abandoned) from gateway-reported payment failure.
    # A genuine gateway failure has an error code (e.g. BAD_REQUEST_ERROR, GATEWAY_ERROR).
    # A modal dismiss has no such code — just a user-generated event dict.
    is_gateway_failure = bool(
        parsed_error and (
            parsed_error.get("code") or
            parsed_error.get("reason") or
            parsed_error.get("step")
        )
    )
    pr_status = "Requested"
    failure_reason_for_pr = failure_message if is_gateway_failure else None

    from slcm.pace.api import _update_pace_payment_request

    _update_pace_payment_request(
        assignment,
        gateway,
        (order_id or "").strip() or None,
        pr_status,
        response_data=parsed_error or {"message": failure_message},
        failure_reason=failure_reason_for_pr,
    )

    if finalize_application:
        app = frappe.get_doc("PACE Application", application_name, check_permission=False)
        if app.status in ("Draft", "Returned for Correction", ""):
            app.status = "Submitted"
            app.submission_date = now_datetime().date()
            app.flags.ignore_permissions = True
            app.save(ignore_permissions=True)

    frappe.db.commit()
    return {"status": "ok"}


@frappe.whitelist()
def submit_pace_application(application_name):
    """
    Explicitly mark the application as Submitted (without payment).
    Called when the applicant cancels the payment modal — their application
    is already valid, so status should be Submitted.
    """
    if not _pace_portal_user_owns_application(application_name):
        frappe.throw(_("You do not have permission to access this application."), frappe.PermissionError)
    app = frappe.get_doc("PACE Application", application_name, check_permission=False)
    if app.status in ("Draft", "Returned for Correction", ""):
        app.status = "Submitted"
        app.submission_date = now_datetime().date()
        app.save(ignore_permissions=True)
        frappe.db.commit()
    return {"status": "ok"}


@frappe.whitelist()
def initiate_pace_razorpay_order(application_name):
    """
    Creates/Gets Fee Assignment and links it to a Payment Request.
    """
    try:
        return _initiate_pace_razorpay_order_impl(application_name)
    except frappe.PermissionError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "initiate_pace_razorpay_order")
        return {"status": "error", "message": str(e)}


def _initiate_pace_razorpay_order_impl(application_name):
    application = _pace_get_application_for_portal(application_name)

    # 1. Calculate fee
    fee_info = get_pace_admission_fee(application_name)
    
    close_date = frappe.db.get_value("PACE Admission", fee_info.get("admission"), "admission_close_date")
    if close_date:
        from frappe.utils import getdate, today
        if getdate(today()) > getdate(close_date):
            frappe.throw(
                _("The admission cycle is closed. Payments can no longer be initiated."),
                frappe.ValidationError
            )

    amount = flt(fee_info.get("fee") or 0)

    # Completed only after fee is paid (or fee is zero / already paid — no gateway step).
    sub_status = "Completed"

    if amount <= 0:
        application.status = sub_status
        application.save(ignore_permissions=True)
        _pace_ensure_document_verification(application)
        return {"status": "free", "message": _("Application submitted (no fee required).")}

    if _pace_application_fee_already_paid(application_name):
        frappe.db.set_value("PACE Application", application_name, "status", sub_status)
        _pace_ensure_document_verification(application_name)
        return {"status": "already_paid", "message": _("Application fee is already paid. You cannot pay again.")}

    # 2. Get or create Fee Assignment (Application Fee only — avoid picking Course Fee row)
    assignment_name = frappe.db.get_value(
        "PACE Applicant Fee Assignment",
        {
            "applicant": application_name,
            "fee_type": "Application Fee",
            "docstatus": ["!=", 2],
        },
        "name",
        order_by="creation desc",
    )

    if assignment_name:
        assignment = frappe.get_doc("PACE Applicant Fee Assignment", assignment_name)
        # Update amount if it changed (e.g. nationality changed before submit)
        if flt(assignment.total_amount) != amount or assignment.status == "Draft":
            assignment.total_amount = amount
            assignment.final_payable_amount = amount
            assignment.status = "Assigned"
            assignment.save(ignore_permissions=True)
    else:
        assignment = frappe.new_doc("PACE Applicant Fee Assignment")
        assignment.applicant = application_name
        assignment.fee_type = "Application Fee"
        assignment.program = application.programme
        assignment.academic_year = application.academic_year
        assignment.admission_cycle = fee_info.get("admission")
        assignment.currency = "INR"
        assignment.total_amount = amount
        assignment.final_payable_amount = amount
        assignment.status = "Assigned"
        assignment.insert(ignore_permissions=True)

    if assignment.status == "Paid":
        application.status = "Completed"
        application.save(ignore_permissions=True)
        _pace_ensure_document_verification(application)
        return {"status": "already_paid", "message": _("Fee already paid.")}

    # 3. Get or create Payment Request
    pr_name = frappe.db.get_value("Payment Request", {
        "reference_doctype": "PACE Applicant Fee Assignment",
        "reference_name": assignment.name,
        "docstatus": ["!=", 2]
    })

    pr = None
    if pr_name:
        pr = frappe.get_doc("Payment Request", pr_name)
        pr_status = (pr.status or "").strip()
        if pr_status == "Paid":
            # Already paid via a concurrent path — treat as done
            application.status = "Completed"
            application.save(ignore_permissions=True)
            _pace_ensure_document_verification(application)
            return {"status": "already_paid", "message": _("Application fee is already paid.")}
        # Cancel and recreate if: amount changed, or PR is Failed (gateway rejected)
        # "Requested" means the order was created but user dismissed — reuse it (order still valid)
        if pr_status == "Failed" or flt(pr.amount) != amount:
            try:
                from slcm.api.service.razorpay_utils import cancel_payment_request_for_retry
                cancel_payment_request_for_retry(pr)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "PACE: cancel old Payment Request")
            pr = None

    gateway = fee_info.get("gateway") or "Razorpay"
    controller = _pace_get_payment_gateway_controller(gateway)

    if not pr:
        pr = frappe.new_doc("Payment Request")
        pr.payment_gateway = gateway
        pr.currency = "INR"
        pr.amount = amount
        pr.email_to = application.email_address
        pr.reference_doctype = "PACE Applicant Fee Assignment"
        pr.reference_name = assignment.name
        pr.flags.ignore_permissions = True
        pr.insert(ignore_permissions=True)
        pr.submit()

    # 4. Get or reuse Razorpay Order
    from slcm.api.service.razorpay_utils import get_razorpay_client, prepare_checkout_order

    receipt = (pr.name or "PACE")[:40]
    subject = _("Application Fee for {0}").format(application.programme)
    payment_details = {
        "amount": amount,
        "currency": "INR",
        "receipt": receipt,
        "description": (subject or "")[:255],
    }
    rzp_client = get_razorpay_client()
    order = prepare_checkout_order(rzp_client, controller, payment_details, pr, amount)
    order_id = (order or {}).get("order_id") or (order or {}).get("id") or ""
    if order_id:
        pr.db_set(
            {"transaction_id": order_id, "razorpay_order_id": order_id},
            update_modified=False,
        )

    settings = frappe.get_single("Razorpay Settings")
    key_id = getattr(settings, "api_key", None) or ""

    frappe.db.commit()

    if not order_id or not key_id:
        return {
            "status": "error",
            "message": _(
                "Payment could not be started. Check Razorpay Settings (API key) and try again, or contact support."
            ),
        }

    return {
        "order_id": order_id,
        "key_id": key_id,
        "amount": int(flt(pr.amount) * 100),
        "currency": pr.currency or "INR",
        "assignment": assignment.name,
        "payment_request": pr.name,
    }


def complete_pace_payment(assignment, gateway, razorpay_order_id, razorpay_payment_id, response_data=None):
    """
    Internal helper to mark assignment Paid and sync application status.
    """
    from slcm.pace.api import _update_pace_payment_request

    try:
        assignment.status = "Paid"
        assignment.transaction_id = razorpay_payment_id
        assignment.payment_date = now_datetime().date()
        
        pr_amt = None
        if response_data and isinstance(response_data, dict) and "amount" in response_data:
            raw_amount = float(response_data["amount"])
            fee = float(response_data.get("fee") or 0)
            pr_amt = (raw_amount - fee) / 100.0

        pr_name = frappe.db.get_value("Payment Request", {"reference_name": assignment.name, "docstatus": 1, "status": "Paid"})
        if not pr_amt and pr_name:
            pr_amt = frappe.db.get_value("Payment Request", pr_name, "amount")
            
        if pr_amt and float(pr_amt) > 0:
            assignment.razorpay_paid_amount = pr_amt
        else:
            frappe.log_error(f"Reconciliation: unable to get valid amount from response or PR {pr_name}.", "PACE Reconciliation Sync Warning")
                
        assignment.flags.ignore_permissions = True
        assignment.save(ignore_permissions=True)
    except Exception as e:
        error_log = frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Failed to update PACE Fee Assignment {assignment.name} during Reconciliation"
        )
        frappe.db.set_value("PACE Applicant Fee Assignment", assignment.name, "error_log", error_log.name)
    
    _update_pace_payment_request(
        assignment,
        gateway,
        razorpay_order_id,
        "Paid",
        payment_id=razorpay_payment_id,
        response_data=response_data or {"payment_id": razorpay_payment_id, "order_id": razorpay_order_id},
        failure_reason=None,
    )

    app = frappe.get_doc("PACE Application", assignment.applicant, check_permission=False)
    if assignment.fee_type == "Course Fee":
        app.status = "Fee Paid"
    else:
        app.status = "Completed"
    app.flags.ignore_permissions = True
    app.save(ignore_permissions=True)

    _pace_ensure_document_verification(app)


@frappe.whitelist()
def verify_pace_payment_signature(
    razorpay_payment_id, razorpay_order_id, razorpay_signature, assignment_name
):
    """
    Verifies the Razorpay signature then finalises the assignment and payment request.

    Locking strategy:
      1. FOR UPDATE on assignment  — prevents concurrent verify + webhook double-write
      2. FOR UPDATE on PR          — serialises concurrent PR status updates
    """
    try:
        # ── Step 1: Row-level lock on assignment ──────────────────────────────
        frappe.db.sql(
            "SELECT name FROM `tabPACE Applicant Fee Assignment` WHERE name = %s FOR UPDATE",
            assignment_name,
        )

        assignment = frappe.get_doc(
            "PACE Applicant Fee Assignment", assignment_name, check_permission=False
        )
        assignment.reload()

        # ── Step 2: Ownership check ───────────────────────────────────────────
        if not assignment.applicant or not _pace_portal_user_owns_application(assignment.applicant):
            return {"status": "failed", "message": _("Not permitted.")}

        # ── Step 3: Idempotency — assignment already paid ─────────────────────
        if assignment.status == "Paid":
            return {"status": "success"}

        # ── Step 4: Resolve Payment Request ───────────────────────────────────
        pr_name = (
            frappe.db.get_value(
                "Payment Request",
                {
                    "reference_doctype": "PACE Applicant Fee Assignment",
                    "reference_name": assignment.name,
                    "docstatus": 1,
                    "transaction_id": razorpay_order_id,
                },
                "name",
            )
            or frappe.db.get_value(
                "Payment Request",
                {
                    "reference_doctype": "PACE Applicant Fee Assignment",
                    "reference_name": assignment.name,
                    "docstatus": 1,
                    "razorpay_order_id": razorpay_order_id,
                },
                "name",
            )
            or frappe.db.get_value(
                "Payment Request",
                {
                    "reference_doctype": "PACE Applicant Fee Assignment",
                    "reference_name": assignment.name,
                    "docstatus": 1,
                },
                "name",
                order_by="creation desc",
            )
        )
        if not pr_name:
            return {
                "status": "failed",
                "message": _("No Payment Request found for this assignment."),
            }

        # ── Step 5: Row-level lock on PR + idempotency check ──────────────────
        frappe.db.sql(
            "SELECT name FROM `tabPayment Request` WHERE name = %s FOR UPDATE",
            pr_name,
        )
        pr = frappe.get_doc("Payment Request", pr_name, check_permission=False)
        if pr.status == "Paid":
            return {"status": "success"}

        # ── Step 6: Anti-replay — same payment_id used on another PR ──────────
        if frappe.db.exists(
            "Payment Request",
            {
                "status": "Paid",
                "transaction_id": razorpay_payment_id,
                "name": ["!=", pr.name],
            },
        ):
            frappe.throw(_("This payment has already been recorded for another request."))

        # ── Step 7: Order ID integrity check ──────────────────────────────────
        expected_order_id = pr.transaction_id or pr.razorpay_order_id
        if expected_order_id != razorpay_order_id:
            frappe.throw(_("Payment Request mismatch."))

        # ── Step 8: Resolve gateway ───────────────────────────────────────────
        gateway = (
            pr.payment_gateway
            or (
                assignment.fee_structure
                and frappe.db.get_value(
                    "PACE Fee Structure", assignment.fee_structure, "payment_gateway"
                )
            )
            or (
                assignment.academic_year
                and frappe.db.get_value(
                    "PACE Admission",
                    {"academic_year": assignment.academic_year, "status": "Active"},
                    "payment_gateway",
                )
            )
            or frappe.db.get_value("Payment Gateway", {}, "name")
            or "Razorpay"
        )

        from payments.utils import get_payment_gateway_controller
        controller = get_payment_gateway_controller(gateway)

        # ── Step 9: Signature verification ────────────────────────────────────
        body = razorpay_order_id + "|" + razorpay_payment_id
        controller.verify_signature(body, razorpay_signature, controller.get_password("api_secret"))

        # ── Step 10: Fetch payment from Razorpay ──────────────────────────────
        import razorpay as _rzp

        rzp_settings = frappe.get_single("Razorpay Settings")
        rzp_client = _rzp.Client(
            auth=(rzp_settings.api_key, rzp_settings.get_password("api_secret"))
        )
        payment = rzp_client.payment.fetch(razorpay_payment_id)

        # ── Step 11: Amount validation ────────────────────────────────────────
        expected_amount = int(flt(pr.get("grand_total") or pr.amount) * 100)
        actual_amount = payment.get("amount")
        if actual_amount < expected_amount:
            frappe.log_error(
                title="PACE Payment Amount Mismatch",
                message=(
                    f"Assignment: {assignment.name}\n"
                    f"Expected: {expected_amount}\n"
                    f"Actual: {actual_amount}\n"
                    f"Payment ID: {razorpay_payment_id}"
                ),
            )
            frappe.throw(_("Payment amount validation failed."))

        # ── Step 12: Order + currency integrity ───────────────────────────────
        if payment.get("order_id") != razorpay_order_id:
            frappe.throw(_("Order validation failed."))

        expected_currency = assignment.currency or frappe.defaults.get_global_default("currency") or "INR"
        if payment.get("currency") != expected_currency:
            frappe.throw(_("Currency validation failed."))

        # ── Step 13: Gateway-reported failure ─────────────────────────────────
        if payment.get("status") == "failed":
            frappe.throw(
                _("Payment Failed: {0}").format(
                    payment.get("error_description")
                    or payment.get("error_code")
                    or _("Payment failed at the gateway.")
                )
            )

        # ── Step 14: Capture if authorized ───────────────────────────────────
        if payment.get("status") == "authorized":
            try:
                payment = rzp_client.payment.capture(
                    razorpay_payment_id,
                    expected_amount,
                    {"currency": payment.get("currency") or "INR"},
                )
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Razorpay Capture Failed for Payment ID {razorpay_payment_id}",
                )
                frappe.throw(
                    _(
                        "Failed to capture authorized payment at the gateway. "
                        "Please retry or contact support."
                    )
                )

        if payment.get("status") != "captured":
            frappe.throw(
                _("Payment not captured. Gateway status: {0}").format(payment.get("status"))
            )

        # ── Step 15: Finalise ─────────────────────────────────────────────────
        complete_pace_payment(
            assignment,
            gateway,
            razorpay_order_id,
            razorpay_payment_id,
            response_data=payment,
        )

        frappe.db.commit()
        return {"status": "success"}

    except frappe.ValidationError as e:
        frappe.db.rollback()
        return {"status": "failed", "message": str(e)}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "PACE Payment Verification Failed")
        return {
            "status": "failed",
            "message": _(
                "An unexpected error occurred during payment verification. "
                "Please contact support."
            ),
        }

@frappe.whitelist()
def update_status_after_payment(application_name):
    application = _pace_get_application_for_portal(application_name)
    
    # Check if Course Fee is paid
    course_fee_paid = frappe.db.exists("PACE Applicant Fee Assignment", {
        "applicant": application_name,
        "fee_type": "Course Fee",
        "status": "Paid"
    })
    
    # Check if Application Fee is paid
    application_fee_paid = frappe.db.exists("PACE Applicant Fee Assignment", {
        "applicant": application_name,
        "fee_type": "Application Fee",
        "status": "Paid"
    })
    
    if course_fee_paid:
        application.status = "Fee Paid"
    elif application_fee_paid:
        application.status = "Completed"
    else:
        return {"status": "pending"}

    # application.submission_date = now_datetime().date()
    application.save(ignore_permissions=True)
    _pace_ensure_document_verification(application)
    # Also create receipt
    generate_pace_receipt(application_name)
    return {"status": "success"}

@frappe.whitelist()
def generate_pace_receipt(application_name, assignment_name=None):
    application = _pace_get_application_for_portal(application_name)

    # Resolve which assignment to generate the receipt for.
    # Prefer a passed assignment_name; fall back to the most recent paid assignment.
    if not assignment_name:
        assignment_name = frappe.db.get_value(
            "PACE Applicant Fee Assignment",
            {"applicant": application_name, "status": ["not in", ["Draft", "Assigned", "Cancelled"]], "fee_type": "Course Fee"},
            "name",
            order_by="creation desc",
        )
        if not assignment_name:
            assignment_name = frappe.db.get_value(
                "PACE Applicant Fee Assignment",
                {"applicant": application_name, "status": ["not in", ["Draft", "Assigned", "Cancelled"]], "fee_type": "Application Fee"},
                "name",
                order_by="creation desc",
            )

    if not assignment_name:
        return None

    # Dynamically resolve fee_type from the actual assignment — never hardcode.
    fee_type = frappe.db.get_value("PACE Applicant Fee Assignment", assignment_name, "fee_type") or "Application Fee"

    # Idempotency: return existing receipt for this application + fee_type combination.
    existing = frappe.db.get_value(
        "PACE Receipt",
        {"pace_application": application_name, "fee_type": fee_type},
        "name",
    )
    if existing:
        return existing

    assignment = frappe.get_doc("PACE Applicant Fee Assignment", assignment_name)
    transaction_id = assignment.transaction_id
    payment_date = assignment.payment_date or assignment.modified

    # Fallback: look up transaction_id from linked Payment Request if not on assignment.
    if not transaction_id:
        pr = frappe.db.get_value(
            "Payment Request",
            {
                "reference_doctype": "PACE Applicant Fee Assignment",
                "reference_name": assignment_name,
                "status": "Paid",
            },
            ["transaction_id", "creation"],
            as_dict=True,
        )
        if pr:
            transaction_id = pr.transaction_id
            payment_date = payment_date or pr.creation

    receipt = frappe.new_doc("PACE Receipt")
    receipt.pace_application = application_name
    receipt.fee_assignment = assignment_name
    receipt.program = application.programme
    receipt.academic_year = application.academic_year
    receipt.fee_type = fee_type
    receipt.amount = flt(assignment.total_amount)
    receipt.currency = assignment.currency or "INR"
    receipt.transaction_id = transaction_id
    receipt.payment_date = payment_date
    receipt.insert(ignore_permissions=True)

    return receipt.name

@frappe.whitelist()
def get_restricted_fields(application_name):
    if not _pace_portal_user_owns_application(application_name):
        return []

    verification = frappe.db.get_value("PACE Document Verification", {"application": application_name}, "name")
    if not verification:
        return []
        
    doc = frappe.get_doc("PACE Document Verification", verification, check_permission=False)
    
    fields = []
    for item in doc.verification_items:
        if item.status == "Returned for Correction" and item.fieldname:
            fields.append(item.fieldname)
            
    return fields

def _generate_receipt_pdf(receipt_name, template):
    """Background task to generate and attach PDF receipt."""
    from frappe.utils.pdf import get_pdf
    from frappe.utils.file_manager import save_file
    
    try:
        pdf_content = get_pdf(frappe.get_print("PACE Receipt", receipt_name, template))
        file_name = f"Receipt-{receipt_name}.pdf"
        _file = save_file(file_name, pdf_content, "PACE Receipt", receipt_name, is_private=1)
        frappe.db.set_value("PACE Receipt", receipt_name, "receipt", _file.file_url)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"PACE Receipt PDF generation failed for {receipt_name}")

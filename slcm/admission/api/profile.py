import frappe
from slcm.utils.phone_utils import sanitize_phone_for_frappe

# Strict mapping of fields for synchronization between User and Applicant
# Mapping: User field name -> Applicant field name
PROFILE_FIELD_MAP = {
    "full_name": "candidate_name",
    "email": "email",
    "mobile_no": "mobile_number",
    "date_of_birth": "date_of_birth",
    "gender": "gender",
    "nationality": "nationality",
    "address": "correspondence_address",
    "city": "city",
    "state": "state",
    "pincode": "pincode",
}

# The email identifies the applicant (record ownership is checked against it), so the portal never
# changes it on the User or the Applicant.
PORTAL_READ_ONLY_FIELDS = {"email"}

# Portal / code uses date_of_birth + address; standard Frappe User uses birth_date + location.
USER_WRITE_COLUMN_ALIASES = {
    "date_of_birth": ("date_of_birth", "birth_date"),
    "address": ("address", "location"),
}


def _user_table_columns():
    try:
        return set(frappe.db.get_table_columns("User"))
    except Exception:
        return set()


def _resolve_user_write_columns(user_update_dict, table_cols):
    """Map logical User field names to actual tabUser columns."""
    out = {}
    for fn, fv in user_update_dict.items():
        if fn in USER_WRITE_COLUMN_ALIASES:
            for cand in USER_WRITE_COLUMN_ALIASES[fn]:
                if cand in table_cols:
                    out[cand] = fv
                    break
            continue
        if fn in table_cols:
            out[fn] = fv
    return out


def _user_dob_value(user_doc):
    v = getattr(user_doc, "date_of_birth", None) or getattr(user_doc, "birth_date", None)
    if not v:
        return ""
    if isinstance(v, str):
        return v
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v)


def _user_address_value(user_doc):
    v = getattr(user_doc, "address", None) or getattr(user_doc, "location", None)
    return v or ""

@frappe.whitelist()
def get_user_profile_data():
    """
    Returns User fields for profile rendering.
    Source of Truth: User doctype.
    """
    user = frappe.session.user
    if not user or user == "Guest":
        return {"success": False, "error": "Authentication required."}
    
    user_doc = frappe.get_doc("User", user)
    
    data = {
        "full_name": user_doc.full_name,
        "email": user_doc.email,
        "mobile_no": getattr(user_doc, "mobile_no", ""),
        "date_of_birth": _user_dob_value(user_doc),
        "gender": user_doc.gender,
        "nationality": getattr(user_doc, "nationality", ""),
        "address": _user_address_value(user_doc),
        "city": getattr(user_doc, "city", ""),
        "state": getattr(user_doc, "state", ""),
        "pincode": getattr(user_doc, "pincode", ""),
        "user_image": user_doc.user_image,
    }
    
    return {"success": True, "data": data}

@frappe.whitelist(methods=["POST"])
def update_user_profile(**kwargs):
    """
    Updates User doctype.
    SYNC LOGIC (Requirement 2b): DON'T sync from User to Applicant.
    """
    user = frappe.session.user
    if not user or user == "Guest":
        return {"success": False, "error": "Authentication required."}

    # Extract relevant fields for User update
    user_update_dict = {}
    
    # Profile image (User doctype only - Requirement 3)
    if "user_image" in kwargs:
        user_update_dict["user_image"] = kwargs["user_image"]
    
    # Handle mapped fields from User names
    for user_field in PROFILE_FIELD_MAP.keys():
        if user_field in kwargs and user_field not in PORTAL_READ_ONLY_FIELDS:
            val = kwargs[user_field]
            if user_field == "mobile_no" and val:
                val = sanitize_phone_for_frappe(val)
            user_update_dict[user_field] = val
            
    # Also handle alternate names for fields (if coming from older template using Applicant names)
    INV_MAP = {v: k for k, v in PROFILE_FIELD_MAP.items()}
    for k, v in kwargs.items():
        if k in INV_MAP and INV_MAP[k] not in user_update_dict and INV_MAP[k] not in PORTAL_READ_ONLY_FIELDS:
            val = v
            if INV_MAP[k] == "mobile_no" and val:
                val = sanitize_phone_for_frappe(val)
            user_update_dict[INV_MAP[k]] = val

    if not user_update_dict:
        return {"success": False, "error": "No valid fields provided for profile update."}

    table_cols = _user_table_columns()
    safe_updates = _resolve_user_write_columns(user_update_dict, table_cols)
    skipped = []
    for fn in user_update_dict:
        if fn in USER_WRITE_COLUMN_ALIASES:
            if not any(c in table_cols for c in USER_WRITE_COLUMN_ALIASES[fn]):
                skipped.append(fn)
        elif fn not in table_cols:
            skipped.append(fn)

    if not safe_updates:
        return {
            "success": False,
            "error": "No valid profile fields exist on User for this site (add custom fields or use standard User fields).",
        }

    try:
        user_doc = frappe.get_doc("User", user)
        user_doc.update(safe_updates)
        user_doc.save(ignore_permissions=True)

        frappe.db.commit()
        return {
            "success": True,
            "status": "ok",
            "skipped_fields": skipped,
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "User profile update failed")
        return {"success": False, "error": str(e)}

@frappe.whitelist(methods=["POST"])
def update_applicant_from_form(**kwargs):
    """
    Updates Applicant doctype and syncs allowed fields to User (Requirement 2a).
    Triggered when applicant updates their application form.
    """
    user = frappe.session.user
    if not user or user == "Guest":
        return {"success": False, "error": "Authentication required."}

    app_name = kwargs.get("name") or kwargs.get("applicant")
    if not app_name:
        # Fallback to latest applicant for user
        app_name = frappe.db.get_value("Applicant", {"email": user}, "name", order_by="creation desc")
        if not app_name:
            app_name = frappe.db.get_value("Applicant", {"owner": user}, "name", order_by="creation desc")
            
    if not app_name:
        return {"success": False, "error": "Applicant record not found."}

    # Verify ownership
    if not frappe.db.exists("Applicant", {"name": app_name, "owner": user}) and \
       not frappe.db.exists("Applicant", {"name": app_name, "email": user}) and \
       "Admission Admin" not in frappe.get_roles():
        return {"success": False, "error": "Access denied for this applicant record."}

    applicant_update_dict = {}
    
    # Allowed fields for Applicant (including separate image)
    allowed_fields = {
        "candidate_photo", "alternate_contact", "id_proof",
        "class_x_marksheet", "class_xii_marksheet", "caste_certificate",
        "pwd_certificate", "phd_proposal", "cv", "ka_study_7yrs_certificate",
        "ews_certificate", "ka_defence_child_certificate", "ka_govt_child_certificate",
        "ka_ais_child_certificate", "ka_capf_child_certificate",
        "degree_certificate", "marksheets", 
        "pg_degree_certificatebonafide_certificate_to_be_uploaded", "transcriptsmarksheets_to_be_uploaded"
    }
    
    for k, v in kwargs.items():
        if k in allowed_fields:
            applicant_update_dict[k] = v
        elif k in PROFILE_FIELD_MAP.values():
            applicant_update_dict[k] = v
        # Support User field names as input for Applicant update too
        elif k in PROFILE_FIELD_MAP:
            applicant_update_dict[PROFILE_FIELD_MAP[k]] = v
    for k in PORTAL_READ_ONLY_FIELDS:
        applicant_update_dict.pop(k, None)

    if not applicant_update_dict:
        return {"success": False, "error": "No valid fields provided for applicant update."}

    try:
        target_doctype = kwargs.get("doctype") or "Applicant"
        target_docname = kwargs.get("docname") or app_name

        if target_doctype == "Applicant":
            # Always the applicant verified above — never a client-supplied docname.
            # Update Applicant only — User profile is updated only via update_user_profile (portal modal).
            doc = frappe.get_doc("Applicant", app_name)
            doc.update(applicant_update_dict)
            doc.save(ignore_permissions=True)
        else:
            parent = frappe.db.get_value(target_doctype, target_docname, "parent")
            if parent != app_name:
                return {"success": False, "error": "Invalid document reference."}
            doc = frappe.get_doc(target_doctype, target_docname)
            doc.update(applicant_update_dict)
            doc.save(ignore_permissions=True)

        frappe.db.commit()
        return {"success": True, "status": "ok"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Applicant sync update failed")
        return {"success": False, "error": str(e)}

def sync_applicant_to_user(doc, method=None):
    """
    Deprecated for portal flow: Applicant saves must not overwrite User.
    User is updated only through update_user_profile (dashboard profile modal).
    Kept as no-op for any legacy hook references.
    """
    return

@frappe.whitelist(methods=["POST"])
def update_profile(**kwargs):
    """
    Legacy wrapper for existing dashboard functionality.
    Routes to either User profile update or Applicant form update.
    """
    # Fields that specifically belong to Applicant doctype
    applicant_only_fields = {
        "applicant", "name", "doctype", "docname", "candidate_photo", "id_proof",
        "class_x_marksheet", "class_xii_marksheet", "caste_certificate",
        "pwd_certificate", "phd_proposal", "cv", "ka_study_7yrs_certificate",
        "ews_certificate", "ka_defence_child_certificate", "ka_govt_child_certificate",
        "ka_ais_child_certificate", "ka_capf_child_certificate",
        "degree_certificate", "marksheets", 
        "pg_degree_certificatebonafide_certificate_to_be_uploaded", "transcriptsmarksheets_to_be_uploaded"
    }
    
    if any(k in applicant_only_fields for k in kwargs.keys()):
        return update_applicant_from_form(**kwargs)
    else:
        return update_user_profile(**kwargs)

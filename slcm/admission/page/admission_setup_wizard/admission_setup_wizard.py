import frappe
import json
from slcm.security.access import require_desk_user

DRAFT_KEY_PREFIX = "admission_wizard_draft_"

def _get_draft(user=None):
    user = user or frappe.session.user
    raw = frappe.cache().get_value(f"{DRAFT_KEY_PREFIX}{user}")
    if raw:
        return json.loads(raw) if isinstance(raw, str) else raw
    return {}

def _save_draft(data, user=None):
    user = user or frappe.session.user
    frappe.cache().set_value(
        f"{DRAFT_KEY_PREFIX}{user}",
        json.dumps(data),
        expires_in_sec=86400
    )

def _clear_draft(user=None):
    user = user or frappe.session.user
    frappe.cache().delete_key(f"{DRAFT_KEY_PREFIX}{user}")

@frappe.whitelist()
def get_wizard_state():
    draft = _get_draft()
    settings = frappe.get_single("Institution Settings")
    step_status = _get_step_status(draft, settings)
    return {
        "draft": draft,
        "onboarding_complete": bool(settings.onboarding_complete),
        "institution_name": settings.institution_name or draft.get("institution_name", ""),
        "step_status": step_status,
        "existing": {
            "exam_types": frappe.get_all("Exam Type Config",
                fields=["name","exam_name","exam_code","exam_category","score_import_method"]),
            "document_configs": frappe.db.count("Document Requirement Config"),
            "email_templates": frappe.db.count("Email Template Config", {"is_active": 1}),
            "form_configs": frappe.db.count("Application Form Config")
        },
        "phase_progress": _get_phase_progress()
    }

def _get_step_status(draft, settings):
    return {
        "1": bool(draft.get("institution_name") and draft.get("institution_code")
                  and draft.get("compliance_mode"))
              or bool(settings.institution_name),
        "2": bool(draft.get("step2_done") or settings.institution_name),
        "3": bool(draft.get("exam_types") and len(draft.get("exam_types", [])) > 0)
              or frappe.db.count("Exam Type Config") > 0,
        "6": frappe.db.count("Document Requirement Config") > 0,
        "7": frappe.db.count("Email Template Config", {"is_active": 1}) > 0,
        "8": frappe.db.count("Application Form Config") > 0,
        "9": bool(settings.onboarding_complete)
    }

def _get_phase_progress():
    return [
        {"phase": 6, "name": "Generic Foundation", "status": "complete"},
        {"phase": 7, "name": "Workflow Engine", "status": "complete"},
        {"phase": 8, "name": "Forms & Docs", "status": "complete"},
        {"phase": 9, "name": "Fees & Payments", "status": "external"},
        {"phase": 10, "name": "Merit & Allocation", "status": "external"},
        {"phase": 11, "name": "Setup Wizard", "status": "active"},
        {"phase": 12, "name": "Compliance", "status": "pending"}
    ]

@frappe.whitelist()
def save_step_draft(step, data):
    require_desk_user()
    if isinstance(data, str):
        data = json.loads(data)
    step = int(step)
    draft = _get_draft()

    if step == 1:
        draft.update({
            "institution_name": data.get("institution_name", ""),
            "institution_code": data.get("institution_code", ""),
            "compliance_mode": data.get("compliance_mode", "India"),
            "support_email": data.get("support_email", ""),
            "portal_theme_color": data.get("portal_theme_color", "#1a237e"),
            "logo": data.get("logo", ""),
        })
    elif step == 2:
        draft.update({
            "enable_multi_campus": frappe.utils.cint(data.get("enable_multi_campus", 0)),
            "max_campus_preferences": frappe.utils.cint(data.get("max_campus_preferences", 3)),
            "payment_gateway": data.get("payment_gateway", "Offline Only"),
            "step2_done": True
        })
    elif step == 3:
        exam_types = data.get("exam_types", [])
        valid = [e for e in exam_types if e.get("exam_name") and e.get("exam_code")]
        draft["exam_types"] = valid

    _save_draft(draft)
    return {"success": True, "message": "Draft saved. Data will be committed at Step 9."}

@frappe.whitelist()
def get_draft():
    return _get_draft()

@frappe.whitelist()
def activate_system():
    require_desk_user()
    draft = _get_draft()
    errors = _validate_draft(draft)
    if errors:
        return {"success": False, "errors": errors}

    # Step 1+2 — Institution Settings
    settings = frappe.get_single("Institution Settings")
    settings.institution_name = draft.get("institution_name", "")
    settings.institution_code = draft.get("institution_code", "")
    settings.compliance_mode = draft.get("compliance_mode", "India")
    settings.support_email = draft.get("support_email", "")
    settings.portal_theme_color = draft.get("portal_theme_color", "")
    settings.enable_multi_campus = frappe.utils.cint(draft.get("enable_multi_campus", 0))
    settings.max_campus_preferences = frappe.utils.cint(draft.get("max_campus_preferences", 3))
    settings.payment_gateway = draft.get("payment_gateway", "Offline Only")
    settings.allow_self_configuration = 1
    if draft.get("logo"):
        settings.logo = draft.get("logo")
    settings.save(ignore_permissions=True)

    # Step 3 — Exam Types
    for et in draft.get("exam_types", []):
        if not frappe.db.exists("Exam Type Config", et.get("exam_code")):
            doc = frappe.get_doc({
                "doctype": "Exam Type Config",
                "exam_name": et.get("exam_name"),
                "exam_code": et.get("exam_code"),
                "exam_category": et.get("exam_category", "National"),
                "score_import_method": et.get("score_import_method", "CSV Upload"),
                "validity_years": 1
            })
            doc.insert(ignore_permissions=True)

    # Mark onboarding complete
    settings = frappe.get_single("Institution Settings")
    settings.onboarding_complete = 1
    settings.save(ignore_permissions=True)
    frappe.db.commit()

    _clear_draft()

    return {
        "success": True,
        "message": "System activated! All configuration has been saved."
    }

def _validate_draft(draft):
    errors = []
    if not draft.get("institution_name"):
        errors.append("Step 1: Institution Name is required.")
    if not draft.get("institution_code"):
        errors.append("Step 1: Institution Code is required.")
    if not draft.get("compliance_mode"):
        errors.append("Step 1: Compliance Mode is required.")
    if not draft.get("support_email"):
        errors.append("Step 1: Support Email is required.")
    exam_types = draft.get("exam_types", [])
    if not exam_types and frappe.db.count("Exam Type Config") == 0:
        errors.append("Step 3: At least one Exam Type is required.")
    if frappe.db.count("Document Requirement Config") == 0:
        errors.append("Step 6: At least one Document Requirement Config is required.")
    if frappe.db.count("Email Template Config", {"is_active": 1}) == 0:
        errors.append("Step 7: At least one active Email Template is required.")
    if frappe.db.count("Application Form Config") == 0:
        errors.append("Step 8: At least one Application Form Config is required.")
    return errors

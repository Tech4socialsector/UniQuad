"""
Helpers for Admission Cycle "allow multiple applications": copy profile from another
programme in the same cycle, and cache it for the Applicant web form (session-scoped).
"""

import frappe

_CACHE_PREFIX = "slcm_applicant_profile_copy:"
_CACHE_TTL_SEC = 600


def applicant_dict_for_multiprogram_copy(source_doc):
    """
    Serialize an Applicant for seeding a new programme application in the same cycle.
    Strips identity, Application Info, fee/stage fields; child rows lose Frappe row keys.
    """
    d = frappe.parse_json(frappe.as_json(source_doc))
    if not isinstance(d, dict):
        return {}
    strip_root = {
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "status",
        "program",
        "admission_cycle",
        "admission_year",
        "academic_year",
        "campus",
        "application_type",
        "intake_type",
        "program_level",
        "application_fee_status",
        "application_fee_amount",
        "fee_waived_by",
        "fee_waived_on",
        "current_stage",
        "merit_score",
        "evaluation_status",
        "rejected_reason",
    }
    for k in strip_root:
        d.pop(k, None)
    internal_row = {
        "name",
        "idx",
        "doctype",
        "parent",
        "parentfield",
        "parenttype",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
    }
    for ct in ("categories", "ug_degree_details", "pg_degree_details"):
        rows = d.get(ct)
        if not isinstance(rows, list):
            continue
        cleaned = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            cleaned.append(
                {
                    kk: vv
                    for kk, vv in row.items()
                    if kk not in internal_row and not str(kk).startswith("__")
                }
            )
        d[ct] = cleaned
    return d


def build_multiprogram_profile_copy_payload(user_email, admission_cycle, target_program):
    """
    If the cycle allows multiple applications, the user has no Applicant for target_program,
    and another Applicant exists in that cycle, return a cleaned dict for the web form.
    Otherwise None.
    """
    target_program = (target_program or "").strip()
    admission_cycle = (admission_cycle or "").strip()
    user_email = (user_email or "").strip()
    if not target_program or not admission_cycle or not user_email:
        return None
    allow_multi = int(
        frappe.db.get_value("Admission Cycle", admission_cycle, "allow_multiple_applications")
        or 0
    )
    if not allow_multi:
        return None
    if frappe.get_all(
        "Applicant",
        filters={
            "email": user_email,
            "admission_cycle": admission_cycle,
            "program": target_program,
        },
        limit=1,
    ):
        return None
    other = frappe.get_all(
        "Applicant",
        filters={
            "email": user_email,
            "admission_cycle": admission_cycle,
            "program": ["!=", target_program],
        },
        fields=["name"],
        order_by="modified desc",
        limit=1,
    )
    if not other:
        return None
    src = frappe.get_doc("Applicant", other[0].name)
    return applicant_dict_for_multiprogram_copy(src)


def store_multiprogram_profile_copy_in_cache(payload):
    """Store JSON-serializable dict for current session (one-shot pop on web form load)."""
    if not payload:
        return
    sid = getattr(frappe.local, "session", None) and frappe.session.sid
    if not sid:
        return
    frappe.cache().set_value(
        _CACHE_PREFIX + sid,
        frappe.as_json(payload),
        expires_in_sec=_CACHE_TTL_SEC,
    )


def pop_multiprogram_profile_copy_from_cache():
    """Return cached copy dict or None; delete key after read."""
    sid = getattr(frappe.local, "session", None) and frappe.session.sid
    if not sid:
        return None
    key = _CACHE_PREFIX + sid
    raw = frappe.cache().get_value(key)
    frappe.cache().delete_value(key)
    if not raw:
        return None
    try:
        return frappe.parse_json(raw)
    except Exception:
        return None

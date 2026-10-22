# Copyright (c) 2025, Frappe Technologies and contributors
# License: MIT. See LICENSE

import frappe
from slcm.admission.utils.nlsat_portal import get_portal_login_url
from frappe.utils import formatdate, getdate

from slcm.admission.utils.portal import build_existing_applicant_portal_url, is_application_editable


def get_context(context):
    """Build context for the read-only View Application page. Renders applicant data from DB."""
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = get_portal_login_url() + "?redirect-to=/view_application"
        raise frappe.Redirect

    name = (frappe.form_dict.get("name") or frappe.form_dict.get("applicant") or "").strip()
    if not name or not frappe.db.exists("Applicant", name):
        frappe.local.flags.redirect_location = "/my-applications"
        raise frappe.Redirect

    doc = frappe.get_doc("Applicant", name)
    user = frappe.session.user
    email = frappe.db.get_value("User", user, "email") or user
    if doc.owner != user and doc.email != email:
        frappe.local.flags.redirect_location = "/my-applications"
        raise frappe.Redirect

    context.no_cache = 1
    context.show_sidebar = False
    context.applicant = doc
    context.app_name = doc.name
    context.applicant_id = doc.applicant_id or doc.name
    context.status = doc.status or "Draft"
    context.program_name = frappe.db.get_value("Programme", doc.program, "program_name") or doc.program or "—"
    context.campus_name = frappe.db.get_value("Campus", doc.campus, "campus_name") if doc.campus else None
    context.campus_name = context.campus_name or doc.campus or "—"

    # Formatted values for display (so data always renders from DB)
    context.fmt = _format_display(doc)

    # Application fee (from Applicant)
    context.application_fee = None
    if doc.program and doc.admission_cycle:
        from slcm.api.service.application_fee_service import get_application_fee_details
        try:
            context.application_fee = get_application_fee_details(doc.name)
        except Exception:
            pass

    _editable = is_application_editable(doc)
    context.applicant_portal_open_url = build_existing_applicant_portal_url(
        doc.name,
        doc.admission_cycle,
        edit=_editable,
    )

    return context


def _format_display(doc):
    """Return a dict of formatted values for read-only display (dates, phones, etc.)."""
    out = {}
    if doc.get("date_of_birth"):
        try:
            out["date_of_birth"] = formatdate(getdate(doc.date_of_birth), "dd-MM-yyyy")
        except Exception:
            out["date_of_birth"] = str(doc.date_of_birth)
    else:
        out["date_of_birth"] = "—"

    for field in ("mobile_number", "alternate_contact", "father_mobile", "mother_mobile", "guardian_mobile"):
        val = doc.get(field)
        if val:
            out[field] = _display_phone(val)
        else:
            out[field] = "—"

    return out


def _display_phone(value):
    """Format stored E.164 or raw value for display."""
    if not value:
        return "—"
    s = (value or "").strip()
    if not s:
        return "—"
    # If it looks like E.164 (+digits), show as-is or with a space after country code
    if s.startswith("+"):
        return s
    return s

# Validates query params and redirects to the Applicant web form (/applicant-form/new?...).

import frappe
from slcm.admission.utils.nlsat_portal import get_portal_base, get_portal_login_url
from urllib.parse import quote, urlencode

from slcm.admission.utils.portal import build_applicant_form_new_url

login_required = False


def get_context(context):
    if frappe.session.user == "Guest":
        q = {k: (frappe.form_dict.get(k) or "").strip() for k in frappe.form_dict}
        q = {k: v for k, v in q.items() if v and not k.startswith("_")}
        path = "/application_form/start"
        if q:
            path = path + "?" + urlencode(q)
        context.redirect_url = get_portal_login_url() + "?redirect-to=" + quote(path, safe="/")
        return

    program = (frappe.form_dict.get("program") or "").strip()
    admission_cycle = (frappe.form_dict.get("admission_cycle") or "").strip()
    if not program or not admission_cycle:
        context.redirect_url = get_portal_base()
        return

    exists = frappe.db.exists(
        "Admission Cycle Program",
        {"parent": admission_cycle, "program": program, "is_active": 1},
    )
    if not exists:
        context.redirect_url = get_portal_base()
        return

    ad_year, ac_year = frappe.db.get_value(
        "Admission Cycle", admission_cycle, ["admission_year", "academic_year"]
    ) or ("", "")

    context.redirect_url = build_applicant_form_new_url(
        program,
        admission_cycle,
        campus=(frappe.form_dict.get("campus") or "").strip(),
        intake_type=(frappe.form_dict.get("intake_type") or "").strip(),
        admission_year=(frappe.form_dict.get("admission_year") or "").strip() or (ad_year or ""),
        academic_year=(frappe.form_dict.get("academic_year") or "").strip() or (ac_year or ""),
        program_level=(frappe.form_dict.get("program_level") or "").strip(),
    )

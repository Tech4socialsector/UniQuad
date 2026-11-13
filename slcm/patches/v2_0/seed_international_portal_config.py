"""Applicant Portal Config: the International portal now has its own copy of the
NLSAT Admission tab fields (intl_*). Start them with the values both portals
shared until now, so /nlsat-international looks the same right after migrate
(Single DocType fields added later are stored empty, and a Check like
intl_portal_active would read as 0 and put the portal in maintenance)."""

import frappe

DT = "Applicant Portal Config"


def execute():
	from slcm.admission.utils.portal import INTL_FIELD_PREFIX, NLSAT_PORTAL_FIELDS

	meta = frappe.get_meta(DT)
	if not meta.has_field(INTL_FIELD_PREFIX + "portal_active"):
		return

	saved = {
		r.field
		for r in frappe.db.sql("SELECT field FROM `tabSingles` WHERE doctype = %s", DT, as_dict=True)
	}
	if INTL_FIELD_PREFIX + "portal_active" in saved:
		return  # already seeded (or set by hand)

	doc = frappe.get_single(DT)
	for fn in NLSAT_PORTAL_FIELDS:
		intl_fn = INTL_FIELD_PREFIX + fn
		df = meta.get_field(fn)
		if not df or not meta.has_field(intl_fn):
			continue
		if df.fieldtype == "Table":
			doc.set(intl_fn, [])
			for row in doc.get(fn) or []:
				values = row.as_dict(no_default_fields=True)
				values.pop("parentfield", None)
				doc.append(intl_fn, values)
		else:
			value = doc.get(fn)
			if df.fieldtype == "Check" and value is None:
				value = df.default
			doc.set(intl_fn, value)

	doc.flags.ignore_mandatory = True
	doc.flags.ignore_validate = True
	doc.flags.ignore_permissions = True
	doc.save()

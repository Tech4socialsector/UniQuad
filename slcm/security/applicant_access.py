"""Record-level access for applicants (Website Users) on admission doctypes.

DocPerm rows decide *what* an applicant may do with a doctype; these hooks decide *which records*:
only those linked to an Applicant they own (created it, or its email is theirs). Desk users are
not affected. Registered in hooks.py under has_permission and permission_query_conditions.
"""

import frappe

from slcm.security.access import is_applicant_only, owns_applicant, owns_offer

# doctype -> field linking the record to an Applicant
APPLICANT_LINK = {
	"Scholarship Application": "applicant_id",
	"Applicant Document": "applicant",
	"Applicant Notification": "applicant",
	"Applicant Payment Receipt": "applicant",
	"Applicant Campus Preference": "applicant",
	"Entrance Test Seat Allocation": "applicant",
	"Interview Seat Allocation": "applicant",
}

# Fields only the server sets; applicants cannot change them through direct-write channels.
APPLICANT_PROTECTED_FIELDS = (
	"status", "application_fee_status", "application_fee_amount", "fee_waived_by", "fee_waived_on",
	"current_stage", "merit_score", "evaluation_status", "eligibility_status", "user_id", "email",
	"exempts_entrance_test", "exempts_interview", "applicant_id", "application_number", "intereview",
)

# Requests that write a document straight from client data (as opposed to dedicated endpoints).
_DIRECT_WRITE_METHODS = {
	"frappe.website.doctype.web_form.web_form.accept",
	"frappe.client.save", "frappe.client.set_value", "frappe.client.insert", "frappe.client.insert_many",
	"frappe.client.bulk_update", "frappe.desk.form.save.savedocs",
}


def _is_applicant_user(user):
	return is_applicant_only(user)


def _identities(user):
	email = frappe.get_cached_value("User", user, "email") or user
	return {user, email}


def _owned_applicants_sql(user):
	ids = ", ".join(frappe.db.escape(i) for i in _identities(user))
	return f"select name from `tabApplicant` where email in ({ids}) or owner in ({ids})"


# ── has_permission (single records) ─────────────────────────────────────────
# Frappe treats any falsy return as "deny", so every path returns a bool.

def applicant_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not _is_applicant_user(user):
		return True
	if doc.is_new():
		return not doc.get("email") or doc.email in _identities(user)
	return owns_applicant(doc.name, user)


def offer_letter_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not _is_applicant_user(user):
		return True
	return (doc.get("email") or "") in _identities(user) or owns_applicant(doc.get("applicant"), user) \
		or (not doc.is_new() and owns_offer(doc.name, user))


def linked_record_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not _is_applicant_user(user):
		return True
	field = APPLICANT_LINK.get(doc.doctype)
	return bool(field) and owns_applicant(doc.get(field), user)


# ── permission_query_conditions (lists, reports, get_list) ───────────────────

def _linked_condition(doctype, user):
	user = user or frappe.session.user
	if not _is_applicant_user(user):
		return ""
	return f"`tab{doctype}`.`{APPLICANT_LINK[doctype]}` in ({_owned_applicants_sql(user)})"


def offer_letter_query(user):
	user = user or frappe.session.user
	if not _is_applicant_user(user):
		return ""
	ids = ", ".join(frappe.db.escape(i) for i in _identities(user))
	return f"(`tabOffer Letter`.email in ({ids}) or `tabOffer Letter`.applicant in ({_owned_applicants_sql(user)}))"


def scholarship_application_query(user):
	return _linked_condition("Scholarship Application", user)


def applicant_document_query(user):
	return _linked_condition("Applicant Document", user)


def applicant_notification_query(user):
	return _linked_condition("Applicant Notification", user)


def applicant_payment_receipt_query(user):
	return _linked_condition("Applicant Payment Receipt", user)


def applicant_campus_preference_query(user):
	return _linked_condition("Applicant Campus Preference", user)


# ── Applicant protected fields (doc_events validate) ─────────────────────────

def _is_direct_write_request():
	request = getattr(frappe.local, "request", None)
	if not request:
		return False
	path = request.path or ""
	if path.startswith(("/api/resource/", "/api/v1/resource/", "/api/v2/document/")):
		return True
	method = frappe.form_dict.get("cmd") or ""
	if not method and "/method/" in path:
		method = path.split("/method/", 1)[1].strip("/")
	return method in _DIRECT_WRITE_METHODS


def guard_applicant_protected_fields(doc, method=None):
	"""Applicants (Website Users) saving their Applicant through the web form or the REST API
	cannot change status, fee, evaluation or identity fields: they keep their stored values
	(defaults on a new record). Server-side flows set these through their own endpoints."""
	user = frappe.session.user
	if not _is_applicant_user(user) or not _is_direct_write_request():
		return
	if doc.is_new():
		meta = doc.meta
		for field in APPLICANT_PROTECTED_FIELDS:
			if field == "email":
				doc.email = frappe.get_cached_value("User", user, "email") or user
			elif meta.has_field(field):
				doc.set(field, meta.get_field(field).default)
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	for field in APPLICANT_PROTECTED_FIELDS:
		if doc.meta.has_field(field) and doc.get(field) != before.get(field):
			doc.set(field, before.get(field))

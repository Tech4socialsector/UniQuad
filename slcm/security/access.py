"""Access checks shared by admission endpoints.

Staff are desk users (System Users); applicants are Website Users who may only act on their own
records. An applicant owns an Applicant record when they created it or its email is theirs.
"""

import frappe
from frappe import _


def is_desk_user(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return user != "Guest" and frappe.get_cached_value("User", user, "user_type") == "System User"


APPLICANT_ROLES = frozenset({"Applicant", "PACE Applicant"})


def is_applicant_only(user=None):
	"""A website account whose only roles are Applicant / PACE Applicant (not providers, staff, students)."""
	user = user or frappe.session.user
	if not user or user == "Guest" or is_desk_user(user):
		return False
	roles = set(frappe.get_roles(user)) - {"All", "Guest", "Desk User"}
	return bool(roles) and roles <= APPLICANT_ROLES


def require_desk_user():
	"""Staff-only endpoint: refuse guests and website users (applicants, students, parents)."""
	if not is_desk_user():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _session_identities(user):
	email = frappe.get_cached_value("User", user, "email") or user
	return {(user or "").lower(), (email or "").lower()}


def owns_applicant(applicant_name, user=None):
	user = user or frappe.session.user
	if not applicant_name or user == "Guest":
		return False
	row = frappe.db.get_value("Applicant", applicant_name, ["owner", "email"], as_dict=True)
	if not row:
		return False
	return bool(_session_identities(user) & {(row.owner or "").lower(), (row.email or "").lower()})


def assert_owns_applicant(applicant_name):
	"""Applicant endpoints: the caller must own the applicant (staff may act on any)."""
	if is_desk_user() or owns_applicant(applicant_name):
		return
	frappe.throw(_("Not permitted"), frappe.PermissionError)


def owns_offer(offer_name, user=None):
	user = user or frappe.session.user
	if not offer_name or user == "Guest":
		return False
	row = frappe.db.get_value("Offer Letter", offer_name, ["email", "applicant"], as_dict=True)
	if not row:
		return False
	if (row.email or "").lower() in _session_identities(user):
		return True
	return owns_applicant(row.applicant, user)


def assert_owns_offer(offer_name):
	if is_desk_user() or owns_offer(offer_name):
		return
	frappe.throw(_("Not permitted"), frappe.PermissionError)


def safe_redirect_path(target, default):
	"""Only same-site paths ("/x"); anything else (other sites, //host, /\\host, javascript:) -> default."""
	target = (target or "").strip()
	if not target.startswith("/") or target.startswith(("//", "/\\")) or any(c in target for c in "\r\n\t<>\"'`"):
		return default
	return target

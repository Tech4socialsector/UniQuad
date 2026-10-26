"""
Sidebar partial for the admission portal pages (profile, applications, scholarships,
offer letter, helpdesk …), shared by NLSAT (Domestic + International) and PACE pages.

_sidebar.html holds the portal_sidebar_css / portal_sidebar_html / portal_sidebar_js macros
and is imported by each page, not served as a page. The menu data comes from
get_nlsat_sidebar_context(), exposed to Jinja through the `jinja.methods` hook.
"""

import frappe


def get_context(context):
	# Partial only — must not render as a page
	raise frappe.PageDoesNotExistError


def _show_scholarships(user):
	"""Scholarships entry: shown when the active cycle enables it, or the user already applied."""
	active_cycle = frappe.db.get_value("Admission Cycle", {"status": "Active"}, "name")
	if active_cycle and frappe.db.get_value("Admission Cycle", active_cycle, "enable_scholarship"):
		return True
	applicant_names = frappe.get_all("Applicant", {"email": user}, pluck="name")
	return bool(
		applicant_names
		and frappe.db.count("Scholarship Application", {"applicant_id": ("in", applicant_names)})
	)


def _show_offer_letter(user, roles):
	"""Offer Letter entry: shown only when the user/candidate has at least one offer letter record."""
	if not user or user == "Guest":
		return False

	is_admin = user == "Administrator" or bool({"Administrator", "System Manager", "Admission Admin"} & roles)
	if is_admin:
		return bool(frappe.db.count("Offer Letter"))

	if frappe.db.exists("Offer Letter", {"email": user}):
		return True

	if frappe.db.exists("Offer Letter", {"owner": user}):
		return True

	applicant_names = set(frappe.get_all("Applicant", {"email": user}, pluck="name"))
	applicant_names.update(frappe.get_all("Applicant", {"owner": user}, pluck="name"))
	if applicant_names and frappe.db.exists("Offer Letter", {"applicant": ("in", list(applicant_names))}):
		return True

	if frappe.db.exists("Offer Letter", {"applicant": user}):
		return True

	return False


def get_nlsat_sidebar_context():
	from slcm.admission.utils.nlsat_portal import get_candidate_prefix

	user = frappe.session.user
	prefix = get_candidate_prefix(user)  # /nlsat or /pace — shared pages are served under it
	roles = set(frappe.get_all("Has Role", filters={"parent": user}, pluck="role"))
	is_admin = user == "Administrator" or bool({"Administrator", "System Manager"} & roles)
	has_applicant = "Applicant" in roles
	has_pace = "PACE Applicant" in roles
	is_pace_staff = not is_admin and ("Document Verifier" in roles or "PACE Admission Manager" in roles)
	pace_only = has_pace and not has_applicant and not is_admin
	show_admission_items = not pace_only and not is_pace_staff

	return frappe._dict(
		show_profile=not is_pace_staff,
		show_applications=show_admission_items,
		show_pace_applications=not (has_applicant and not has_pace),
		show_admission_items=show_admission_items,
		show_scholarships=show_admission_items and _show_scholarships(user),
		show_offer_letter=show_admission_items and _show_offer_letter(user, roles),
		show_helpdesk=not is_pace_staff,
		urls=frappe._dict(
			profile=prefix + "/my-profile",
			applications="/nlsat/dashboard?panel=applications",
			pace_applications="/paceadmissions/application-card",
			scholarships="/nlsat/scholarships",
			offer_letter="/nlsat/offer_letter/offer-letter-list",
			helpdesk=prefix + "/helpdesk",
			change_password="/update-password",
		),
	)

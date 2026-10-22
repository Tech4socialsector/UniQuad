"""
Navbar partial for the NLSAT portal layout (www/nlsat/admission_base.html).

_navbar.html is included by the layout, not served as a page. Its data comes from
get_nlsat_navbar_context(), exposed to Jinja through the `jinja.methods` hook.
"""

import frappe


def get_context(context):
	# Partial only — /nlsat/_navbar must not render as a page
	raise frappe.PageDoesNotExistError


def _has_role(user, role):
	return bool(frappe.db.get_value("Has Role", {"parent": user, "role": role}, "role"))


def get_nlsat_navbar_context(portal_config=None, current_path="", nlsat_login_url=""):
	"""Values the navbar + mobile drawer need (roles, signed-in user, login link)."""
	pc = portal_config or {}
	_get = pc.get if hasattr(pc, "get") else (lambda k, d=None: getattr(pc, k, d))

	user = frappe.session.user if frappe.session else ""
	is_guest = user == "Guest" or not user

	has_applicant = _has_role(user, "Applicant")
	has_pace_applicant = _has_role(user, "PACE Applicant")
	portal_active = _get("portal_active") if pc else 1

	# Guests on PACE pages (or PACE-only users) log in through the PACE portal
	login_url = (
		"/paceadmissions/login"
		if ("pace" in (current_path or "")) or (has_pace_applicant and not has_applicant)
		else (nlsat_login_url or "/nlsatadmissions/login")
	)

	full_name, user_image = user, ""
	if not is_guest:
		info = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True) or {}
		full_name = info.get("full_name") or user
		user_image = info.get("user_image") or ""

	inst_logo = (_get("institution_logo") if pc else "") or (
		frappe.db.get_single_value("Institution Settings", "logo") or ""
	)

	return frappe._dict(
		user=user,
		is_guest=is_guest,
		first_letter=(user[0].upper() if user and not is_guest else "U"),
		full_name=full_name,
		user_image=user_image,
		has_applicant=has_applicant,
		has_pace_applicant=has_pace_applicant,
		show_admission=bool(portal_active) and not (has_pace_applicant and not has_applicant),
		show_pace=not (has_applicant and not has_pace_applicant),
		login_url=login_url,
		is_pace_login="pace" in login_url,
		inst_logo=inst_logo,
		profile_url="/nlsat/profile",
		helpdesk_url="/nlsat/merit-and-scholarship/helpdesk",
	)

"""
NLSAT admission portals.

Domestic (Indian Nationals) candidates use /nlsatadmissions and International
candidates use /nlsat-international. Both routes render the same www pages in
slcm/www/nlsatadmissions; the portal is detected from the request path and
remembered in a cookie so shared pages (profile, my-applications, offer letter)
can send the candidate back to the login page they came from.
"""

import frappe

DOMESTIC = "Domestic"
INTERNATIONAL = "International"

PORTAL_BASES = {
	DOMESTIC: "/nlsatadmissions",
	INTERNATIONAL: "/nlsat-international",
}

PORTAL_COOKIE = "nlsat_portal"

# Routes under /nlsatadmissions shared by both portals (the applicant web form)
SHARED_SUBROUTES = ("application-form",)


def normalize_portal_type(value):
	return INTERNATIONAL if (value or "").strip().lower() == INTERNATIONAL.lower() else DOMESTIC


def get_portal_type_from_path(path):
	"""Return the portal type for an /nlsatadmissions or /nlsat-international path, else None."""
	parts = (path or "").split("?")[0].strip("/").split("/")
	if parts[0] == PORTAL_BASES[INTERNATIONAL].strip("/"):
		return INTERNATIONAL
	if parts[0] == PORTAL_BASES[DOMESTIC].strip("/"):
		if len(parts) > 1 and parts[1] in SHARED_SUBROUTES:
			return None
		return DOMESTIC
	return None


def _request_path():
	req = getattr(frappe.local, "request", None)
	return (req and getattr(req, "path", "")) or getattr(frappe.local, "path", "") or ""


def get_portal_cookie():
	req = getattr(frappe.local, "request", None)
	value = req.cookies.get(PORTAL_COOKIE) if req else None
	return normalize_portal_type(value) if value else None


def set_portal_cookie(portal_type):
	cookie_manager = getattr(frappe.local, "cookie_manager", None)
	if cookie_manager:
		from frappe.utils import add_days, now_datetime

		cookie_manager.set_cookie(
			PORTAL_COOKIE, normalize_portal_type(portal_type), expires=add_days(now_datetime(), 365)
		)


def get_applicant_portal_type(user=None):
	"""Portal type of the user's latest Applicant record (foriegn_national = Yes → International)."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	foreign = frappe.db.get_value(
		"Applicant", {"email": user}, "foriegn_national", order_by="creation desc"
	)
	if foreign is None:
		return None
	return INTERNATIONAL if (foreign or "").strip() == "Yes" else DOMESTIC


def get_current_portal_type():
	"""Portal for this request: URL path, then cookie, then the user's applicant record."""
	return (
		get_portal_type_from_path(_request_path())
		or get_portal_cookie()
		or get_applicant_portal_type()
		or DOMESTIC
	)


def get_portal_base(portal_type=None):
	return PORTAL_BASES[normalize_portal_type(portal_type or get_current_portal_type())]


def get_portal_login_url(portal_type=None):
	return get_portal_base(portal_type) + "/login"


def get_applicant_login_url(foriegn_national):
	"""Login URL for an Applicant based on their category (used in emails)."""
	portal_type = INTERNATIONAL if (foriegn_national or "").strip() == "Yes" else DOMESTIC
	return get_portal_login_url(portal_type)


def get_user_portal_redirect_url(user, path):
	"""Link (for emails) to `path` via the login page of the user's portal; logged-in users pass straight through."""
	from urllib.parse import quote

	portal_type = get_applicant_portal_type(user) or DOMESTIC
	return get_portal_login_url(portal_type) + "?redirect-to=" + quote(path, safe="/")


# ── Candidate prefix for pages shared by NLSAT and PACE (www/admission) ──
# The same page is served at /nlsat/<page> and /pace/<page> (website_route_rules),
# so the URL shows whose page it is: /nlsat/my-profile, /pace/my-profile, …

NLSAT_PREFIX = "/nlsat"
PACE_PREFIX = "/pace"
PACE_LOGIN_URL = "/paceadmissions/login"


def _is_pace_only(user):
	if not user or user == "Guest":
		return False
	roles = set(frappe.get_all("Has Role", filters={"parent": user}, pluck="role"))
	return "PACE Applicant" in roles and "Applicant" not in roles


def get_candidate_prefix(user=None, path=None):
	"""/pace on PACE pages (or for PACE-only users), otherwise /nlsat."""
	first = ((path if path is not None else _request_path()) or "").strip("/").split("/")[0]
	if first in ("pace", "paceadmissions"):
		return PACE_PREFIX
	if first in ("nlsat", "nlsatadmissions", "nlsat-international", "application_form"):
		return NLSAT_PREFIX
	return PACE_PREFIX if _is_pace_only(user or frappe.session.user) else NLSAT_PREFIX


def get_candidate_login_url(prefix=None):
	"""Login page for the candidate: PACE login under /pace, NLSAT login (cookie/category) otherwise."""
	return PACE_LOGIN_URL if (prefix or get_candidate_prefix()) == PACE_PREFIX else get_portal_login_url()

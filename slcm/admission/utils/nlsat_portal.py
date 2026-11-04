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
	"""Portal type of the user's latest Applicant record (foriegn_national = Yes →
	International), else the portal they signed up on (User.nlsat_portal)."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	foreign = frappe.db.get_value(
		"Applicant", {"email": user}, "foriegn_national", order_by="creation desc"
	)
	if foreign is None:
		return get_user_signup_portal(user)
	return INTERNATIONAL if (foreign or "").strip() == "Yes" else DOMESTIC


USER_PORTAL_FIELD = "nlsat_portal"


def get_user_signup_portal(user):
	"""The portal a user signed up on (User.nlsat_portal), else None."""
	if not user or user == "Guest" or not frappe.db.has_column("User", USER_PORTAL_FIELD):
		return None
	value = frappe.db.get_value("User", user, USER_PORTAL_FIELD)
	return normalize_portal_type(value) if value else None


def set_user_signup_portal(user, portal_type):
	"""Remember the portal a user signed up on (for emails sent before they apply)."""
	if portal_type and frappe.db.has_column("User", USER_PORTAL_FIELD):
		frappe.db.set_value(
			"User", user, USER_PORTAL_FIELD, normalize_portal_type(portal_type), update_modified=False
		)


def enforce_portal_access(portal_type):
	"""
	Keep a logged-in candidate on the portal they logged in through: a Domestic
	candidate opening an /nlsat-international page (or vice versa) is redirected to
	the same page on their own portal. Guests and System Users are not restricted.
	"""
	user = frappe.session.user
	if not user or user == "Guest":
		return
	if frappe.db.get_value("User", user, "user_type") == "System User":
		return

	allowed = get_applicant_portal_type(user) or get_portal_cookie()
	if not allowed or allowed == normalize_portal_type(portal_type):
		return

	req = getattr(frappe.local, "request", None)
	path = _request_path()
	current_base = PORTAL_BASES[normalize_portal_type(portal_type)]
	target = PORTAL_BASES[allowed] + (path[len(current_base):] if path.startswith(current_base) else "")
	query = req.query_string.decode() if req and req.query_string else ""
	frappe.local.flags.redirect_location = target + ("?" + query if query else "")
	raise frappe.Redirect


def get_current_portal_type():
	"""Portal for this request: URL path, then user's applicant record, then cookie."""
	return (
		get_portal_type_from_path(_request_path())
		or get_applicant_portal_type()
		or get_portal_cookie()
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
	"""Full link (for emails) to `path` via the login page of the user's portal, on
	that portal's domain; logged-in users pass straight through."""
	from urllib.parse import quote

	portal_type = get_applicant_portal_type(user) or DOMESTIC
	return get_portal_url(
		get_portal_login_url(portal_type) + "?redirect-to=" + quote(path, safe="/"), portal_type
	)


# ── Portal domains for links in emails ──
# Each portal can have its own domain (Site Domain Settings: a domain whose
# Redirect To is the portal's page, e.g. internationaladmissions.nls.ac.in →
# /nlsat-international). frappe.utils.get_url() always gives the site's
# host_name (app.nls.ac.in), so links in emails are built here instead.


def _portal_from_value(value):
	"""'International' / 'Domestic' / '/nlsat-international/...' → portal type, else None."""
	value = (value or "").strip()
	if not value:
		return None
	if value.lower() in (DOMESTIC.lower(), INTERNATIONAL.lower()):
		return normalize_portal_type(value)
	if value.startswith("/"):
		return get_portal_type_from_path(value)
	return None


def get_request_portal_type(*values):
	"""Portal a sign-up / password-reset request came from: the given values
	(portal type or page path), then the page it was sent from (Referer), then the
	portal cookie. None when it cannot be told."""
	for value in values:
		portal_type = _portal_from_value(value)
		if portal_type:
			return portal_type
	req = getattr(frappe.local, "request", None)
	referer = req.headers.get("Referer") if req else None
	if referer:
		from urllib.parse import urlparse

		portal_type = get_portal_type_from_path(urlparse(referer).path)
		if portal_type:
			return portal_type
	return get_portal_cookie()


def get_portal_domain(portal_type):
	"""The domain set for a portal in Site Domain Settings (enabled row whose
	Redirect To is the portal's page), else None."""
	if not portal_type:
		return None
	base = PORTAL_BASES[normalize_portal_type(portal_type)]
	try:
		from slcm.utils.domain_routing import get_domain_config

		redirects = get_domain_config().get("redirects") or {}
	except Exception:
		return None
	matches = sorted(d for d, target in redirects.items() if (target or "").split("?")[0].rstrip("/") == base)
	return matches[0] if matches else None


def _request_domain():
	"""The domain of the current request, only when it is an enabled domain in
	Site Domain Settings (a Host header is never trusted on its own: a reset
	link must not point to a domain someone made up)."""
	req = getattr(frappe.local, "request", None)
	if not req:
		return None
	try:
		from slcm.utils.domain_routing import get_domain_config, normalize_host

		host = normalize_host(req.host)
		return host if host and host in (get_domain_config().get("active") or []) else None
	except Exception:
		return None


def _scheme():
	from frappe.utils import get_url

	if get_url().startswith("https://") or not frappe.conf.get("developer_mode"):
		return "https"
	return "http"


def get_portal_site_url(portal_type=None, use_request_host=False):
	"""'https://<domain>' to use in an email link for a portal.

	use_request_host: the domain the user is on right now (sign-up, password
	reset), when it is a known domain. Otherwise the portal's own domain, else
	the site URL (get_url)."""
	from frappe.utils import get_url

	domain = (use_request_host and _request_domain()) or get_portal_domain(portal_type)
	if domain:
		return f"{_scheme()}://{domain}"
	return get_url().rstrip("/")


def get_portal_url(path="", portal_type=None, use_request_host=False):
	"""Full URL of a site path on the portal's domain (see get_portal_site_url)."""
	if path and path.startswith(("http://", "https://")):
		return path
	base = get_portal_site_url(portal_type, use_request_host)
	return base + ("/" + path.lstrip("/") if path else "")


def get_applicant_portal_url(path="", user=None, foriegn_national=None):
	"""Full URL for an email to an applicant, on their portal's domain. The portal
	comes from foriegn_national when given, else from the user's records."""
	if foriegn_national is not None and str(foriegn_national).strip():
		portal_type = INTERNATIONAL if str(foriegn_national).strip() == "Yes" else DOMESTIC
	else:
		portal_type = get_applicant_portal_type(user) if user else None
	return get_portal_url(path, portal_type or DOMESTIC)


def get_applicant_login_link(foriegn_national, fragment="#login"):
	"""Full login link (for emails) of an Applicant's portal, on its domain."""
	portal_type = INTERNATIONAL if (foriegn_national or "").strip() == "Yes" else DOMESTIC
	return get_portal_url(get_portal_login_url(portal_type) + (fragment or ""), portal_type)


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

"""Domain home pages (hooks.before_request), configured in Site Domain Settings.

The site answers on several domains (Frappe Cloud → Site → Domains). Opening
a domain's home page ("/") goes to the page set for it, e.g.
nlsatadmissions.nls.ac.in → /nlsatadmissions. Every other path, and every
domain without a mapping (e.g. app.nls.ac.in), is left as it is.
website_redirects cannot do this: it matches the path only, so a "/" rule
there would redirect every domain.

The settings are cached per site; a request costs one cache read. A domain
the site is opened on that is not listed yet is added by a background job
(at most once an hour per domain), so the table shows the site's real domains.
"""

import ipaddress
import re

import frappe

from slcm.utils.auth_routing import AuthRedirect

SETTINGS = "Site Domain Settings"
CACHE_KEY = "slcm_site_domains"
_HOST_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$")


def normalize_host(value):
	"""'https://App.Example.com:443/x' → 'app.example.com'."""
	value = (value or "").strip().lower()
	if "://" in value:
		value = value.split("://", 1)[1]
	return value.split("/", 1)[0].split(":", 1)[0].rstrip(".")


def is_valid_host(host):
	"""A real domain name: not an IP address, not localhost."""
	if not host or not _HOST_RE.match(host):
		return False
	try:
		ipaddress.ip_address(host)
		return False
	except ValueError:
		return True


PAGE_KEY = "slcm_site_domain_page:"


def clear_domain_cache():
	frappe.cache.delete_value(CACHE_KEY)
	frappe.cache.delete_keys(PAGE_KEY)


def target_page_ok(target):
	"""Whether the Redirect To page still exists, checked at most every 10
	minutes per page. A missing page is skipped (the domain shows its normal
	home page instead of Page Not Found) and logged once per check."""
	key = PAGE_KEY + target
	ok = frappe.cache.get_value(key)
	if ok is None:
		from slcm.slcm.doctype.site_domain_settings.site_domain_settings import page_exists

		ok = 1 if page_exists(target) else 0
		frappe.cache.set_value(key, ok, expires_in_sec=600)
		if not ok:
			frappe.log_error(
				title="Site Domain Settings: Redirect To page not found",
				message=f"{target} has no page, so the domain opens its normal home page. Fix Redirect To in Site Domain Settings.",
			)
	return bool(ok)


NOT_READY = {"enabled": 0, "known": [], "redirects": {}, "ready": 0}
# Detected domains are not queued past this many (Site Domain Settings MAX_DOMAINS)
MAX_KNOWN = 50


def get_domain_config():
	"""{"enabled", "known": [domains], "active": [enabled domains], "redirects": {domain: path}, "ready"}, cached."""
	config = frappe.cache.get_value(CACHE_KEY)
	if not isinstance(config, dict):
		config = _load_config()
		# A failed load is retried after a minute, a good one kept for 6 hours
		frappe.cache.set_value(CACHE_KEY, config, expires_in_sec=6 * 3600 if config["ready"] else 60)
	return config


def _load_config():
	try:
		if not frappe.db.table_exists("Site Domain Route"):
			return dict(NOT_READY)  # not migrated yet: nothing to redirect
		enabled = frappe.db.get_single_value(SETTINGS, "enabled")
		rows = frappe.db.get_all(
			"Site Domain Route",
			filters={"parenttype": SETTINGS, "parent": SETTINGS},
			fields=["domain", "redirect_to", "enabled", "is_primary"],
		)
	except Exception:
		frappe.log_error(title="Site Domain Settings: could not load domain redirects")
		return dict(NOT_READY)
	return {
		"enabled": 1 if enabled else 0,
		"known": [r.domain for r in rows],
		# enabled domains: links in emails may use these (slcm.admission.utils.nlsat_portal)
		"active": [r.domain for r in rows if r.enabled],
		"redirects": {
			r.domain: r.redirect_to for r in rows if r.enabled and r.redirect_to and not r.is_primary
		},
		"ready": 1,
	}


def _note_new_domain(host):
	"""Queue adding a host the site is opened on, at most once an hour."""
	pending = f"slcm_site_domain_pending:{host}"
	if frappe.cache.get_value(pending):
		return
	frappe.cache.set_value(pending, 1, expires_in_sec=3600)
	try:
		frappe.enqueue(
			"slcm.slcm.doctype.site_domain_settings.site_domain_settings.record_domain",
			queue="short",
			host=host,
		)
	except Exception:
		# Queue unavailable: try again on a later visit, not in an hour
		frappe.cache.delete_value(pending)
		raise


def redirect_domain_home():
	"""before_request. Fails open: any error here leaves the request as it was
	(no redirect), it never turns a page into an error."""
	try:
		request = getattr(frappe.local, "request", None)
		if not request:
			return
		host = normalize_host(request.host)
		if not is_valid_host(host):
			return
		config = get_domain_config()
	except Exception:
		return

	# Detecting a new domain is a side job; its failure must not stop the redirect
	try:
		known = config.get("known") or []
		if config.get("ready") and host not in known and len(known) < MAX_KNOWN:
			_note_new_domain(host)
	except Exception:
		pass

	try:
		if request.path not in ("", "/") or not config.get("enabled"):
			return
		# Only page visits. frappe.call() may POST RPC calls to "/" with a `cmd`
		# form field (frappe.request.url = "/"); redirecting those turns every
		# server call on the domain into the home page HTML.
		if request.method not in ("GET", "HEAD") or frappe.form_dict.get("cmd"):
			return
		target = (config.get("redirects") or {}).get(host)
		if not target or not target_page_ok(target):
			return
		query = request.query_string.decode("utf-8", "ignore") if request.query_string else ""
		location = f"{target}?{query}" if query else target
	except Exception:
		return
	raise AuthRedirect(location)

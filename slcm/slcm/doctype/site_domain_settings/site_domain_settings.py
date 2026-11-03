# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Site Domain Settings: the domains this site answers on and the page each
domain's home page opens (served by slcm.utils.domain_routing).

A Single doctype lives in the site's own database, so every site on a bench
keeps its own domains and redirects. The domains come from this site only:
its name, its site_config (host_name / domains), Frappe Cloud when the site is
connected to it (pilot_endpoint), and the hosts the site is opened on.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from slcm.utils.domain_routing import clear_domain_cache, is_valid_host, normalize_host

DOCTYPE = "Site Domain Settings"
# Detected domains stop being added past this many rows
MAX_DOMAINS = 50
SAFE_PATH_RE = re.compile(r"^/[A-Za-z0-9\-_./~%?=&+]*$")


class SiteDomainSettings(Document):
	def validate(self):
		self.sync_site_info()
		self.keep_domains()
		seen = set()
		for row in self.domains:
			row.domain = normalize_host(row.domain)
			if not row.domain:
				frappe.throw(_("Row {0}: Domain is empty.").format(row.idx))
			if not is_valid_host(row.domain) and row.domain != normalize_host(frappe.local.site):
				frappe.throw(_("Row {0}: {1} is not a valid domain name.").format(row.idx, row.domain))
			if row.domain in seen:
				frappe.throw(_("Row {0}: Domain {1} is listed twice.").format(row.idx, row.domain))
			seen.add(row.domain)
			row.is_primary = 1 if row.domain == self.primary_domain else 0
			row.redirect_to = clean_redirect(row.redirect_to, row)
			if row.is_primary and row.redirect_to:
				frappe.throw(
					_("Row {0}: {1} is the primary domain and cannot be redirected; staff reach the desk through it.").format(
						row.idx, row.domain
					)
				)
		self.warn_missing_pages()

	def keep_domains(self):
		"""Domain rows cannot be deleted (the form hides Delete; this also stops
		it through the API). Untick Enabled to stop a domain's redirect."""
		if self.flags.allow_domain_removal:
			return
		before = self.get_doc_before_save()
		if not before:
			return
		kept = {normalize_host(r.domain) for r in self.domains}
		removed = [r.domain for r in before.domains if normalize_host(r.domain) not in kept]
		if removed:
			frappe.throw(
				_("Domains cannot be removed: {0}. Untick Enabled or clear Redirect To instead.").format(", ".join(removed))
			)

	def on_update(self):
		clear_domain_cache()

	def sync_site_info(self):
		self.site_name = frappe.local.site
		self.primary_domain = get_primary_domain()

	def add_domain(self, domain, source):
		"""Add a domain row if it is new; True when added."""
		domain = normalize_host(domain)
		if not is_valid_host(domain) or any(r.domain == domain for r in self.domains):
			return False
		if len(self.domains) >= MAX_DOMAINS:
			return False
		self.append("domains", {"domain": domain, "source": source, "enabled": 1, "detected_on": now_datetime()})
		return True

	def warn_missing_pages(self):
		"""Set Page Status on every row and warn about the missing pages."""
		for row in self.domains:
			if not row.redirect_to:
				row.page_status, row.page_checked_on = "", None
				continue
			ok = page_exists(row.redirect_to)
			row.page_status = "OK" if ok else "Not Found"
			row.page_checked_on = now_datetime()
			if row.enabled and not ok:
				frappe.msgprint(
					_("Row {0}: no page was found at {1}. Until it exists, {2} opens its normal home page instead of redirecting.").format(
						row.idx, row.redirect_to, row.domain
					),
					title=_("Check Redirect To"),
					indicator="orange",
				)


def clean_redirect(value, row):
	"""Redirect To as a path of this site ("/page"), or "" for none."""
	value = (value or "").strip()
	if not value:
		return ""
	if "://" not in value and not value.startswith("/"):
		value = "/" + value  # "nlsatadmissions" → "/nlsatadmissions"
	bad = (
		value.startswith("//")
		or "://" in value
		or len(value) > 200
		# a URL path: letters, digits and - _ . / ~ % ? = & + only (no spaces,
		# quotes, backslashes or line breaks, which would break the redirect)
		or not SAFE_PATH_RE.match(value)
	)
	if bad:
		frappe.throw(
			_("Row {0}: Redirect To must be a page of this site starting with /, e.g. /nlsatadmissions (not a full web address).").format(
				row.idx
			)
		)
	value = "/" + value.strip("/") if value.strip("/") else "/"
	if value == "/":
		frappe.throw(_("Row {0}: Redirect To cannot be / (the home page itself).").format(row.idx))
	return value


def page_exists(path):
	"""Whether the website has a page at path (a redirect counts as a page).

	Frappe's resolver reads the current web request, which a background job
	does not have and which belongs to another page during a request, so it
	runs against a request built for path, and the real one is put back.
	True when it cannot be told, so an unexpected error never turns a working
	redirect off."""
	route = path.split("?")[0].strip("/")
	original = getattr(frappe.local, "request", None)
	try:
		from frappe.website.path_resolver import PathResolver
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		frappe.local.request = Request(EnvironBuilder(path="/" + route, method="GET").get_environ())
		_endpoint, renderer = PathResolver(route).resolve()
		return type(renderer).__name__ != "NotFoundPage"
	except frappe.Redirect:
		return True
	except Exception:
		frappe.log_error(title=f"Site Domain Settings: could not check page {path}")
		return True
	finally:
		frappe.local.request = original


def get_primary_domain():
	"""host_name from this site's config, else the site name."""
	return normalize_host(frappe.conf.get("host_name")) or normalize_host(frappe.local.site)


def site_domains():
	"""[(domain, source)] known to this site's own config."""
	found = [(frappe.local.site, "Site Name")]
	if frappe.conf.get("host_name"):
		found.append((frappe.conf.get("host_name"), "Site Config"))
	for d in frappe.conf.get("domains") or []:
		found.append((d.get("domain") if isinstance(d, dict) else d, "Site Config"))
	found.extend((d, "Frappe Cloud") for d in frappe_cloud_domains())
	return found


def frappe_cloud_domains():
	"""This site's domains from Frappe Cloud, when the site is connected to it
	(pilot_endpoint in site config, newer Frappe only); [] otherwise."""
	if not (frappe.conf.get("pilot_endpoint") and frappe.conf.get("pilot_auth_token")):
		return []
	try:
		from frappe.integrations.frappe_providers.cloud_settings import PilotClient

		client = PilotClient()
		response = client.get(client.site_path("domains")) or {}
		return [r.get("domain") if isinstance(r, dict) else r for r in response.get("domains") or []]
	except Exception:
		frappe.log_error(title="Site Domain Settings: Frappe Cloud domains")
		return []


def sync(settings, current_host=None):
	"""Add this site's domains (and the host it is open on) to the settings."""
	added = []
	for domain, source in site_domains():
		if settings.add_domain(domain, source):
			added.append(normalize_host(domain))
	if current_host and settings.add_domain(current_host, "Detected"):
		added.append(normalize_host(current_host))
	settings.last_synced = now_datetime()
	return added


@frappe.whitelist(methods=["POST"])
def sync_domains(current_host=None):
	"""Sync Domains button."""
	frappe.only_for("System Manager")
	settings = frappe.get_single(DOCTYPE)
	added = sync(settings, current_host)
	settings.save()
	return {"added": added}


def record_domain(host):
	"""Background job: add a host the site was opened on.

	Retries once when someone saved the settings at the same moment. On
	failure it is logged (Error Log) and the domain is tried again on its
	next visit; a request is never affected."""
	for attempt in (1, 2):
		try:
			settings = frappe.get_single(DOCTYPE)
			if not settings.add_domain(host, "Detected"):
				clear_domain_cache()  # already listed (or the table is full)
				return
			settings.flags.ignore_permissions = True
			settings.save()
			frappe.db.commit()
			return
		except frappe.TimestampMismatchError:
			frappe.db.rollback()
			if attempt == 2:
				break
		except Exception:
			frappe.db.rollback()
			break
	frappe.log_error(title=f"Site Domain Settings: could not add domain {host}")
	frappe.cache.delete_value(f"slcm_site_domain_pending:{host}")


def check_redirect_pages():
	"""Daily: re-check every Redirect To page and update Page Status, so a page
	deleted or renamed after the settings were saved shows up as Not Found
	(and in the Error Log). The rows are updated in place, not re-saved, so the
	job never clashes with someone editing the settings."""
	try:
		rows = frappe.get_all(
			"Site Domain Route",
			filters={"parenttype": DOCTYPE, "parent": DOCTYPE, "redirect_to": ["is", "set"]},
			fields=["name", "domain", "redirect_to", "enabled", "page_status"],
		)
	except Exception:
		frappe.log_error(title="Site Domain Settings: daily page check")
		return
	broken = []
	for r in rows:
		status = "OK" if page_exists(r.redirect_to) else "Not Found"
		frappe.db.set_value(
			"Site Domain Route", r.name,
			{"page_status": status, "page_checked_on": now_datetime()},
			update_modified=False,
		)
		if status == "Not Found" and r.enabled:
			broken.append(f"{r.domain} → {r.redirect_to}")
	if broken:
		frappe.log_error(
			title="Site Domain Settings: Redirect To page not found",
			message=_("These domains open their normal home page until Redirect To is fixed in Site Domain Settings:")
			+ "\n" + "\n".join(broken),
		)
	clear_domain_cache()
	frappe.db.commit()


def sync_after_migrate():
	"""after_migrate: keep the site's own domains listed. Never fails a migrate."""
	try:
		settings = frappe.get_single(DOCTYPE)
		sync(settings)
		settings.flags.ignore_permissions = True
		settings.save()
	except Exception:
		frappe.log_error(title="Site Domain Settings: sync after migrate")

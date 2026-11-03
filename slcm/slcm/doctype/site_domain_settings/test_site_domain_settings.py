# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from slcm.slcm.doctype.site_domain_settings.site_domain_settings import record_domain
from slcm.utils import domain_routing as R
from slcm.utils.auth_routing import AuthRedirect

D1 = "portal-one.example.org"
D2 = "portal-two.example.org"


class TestSiteDomainSettings(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for host in (D1, D2):
			record_domain(host)
		self.set_routes({D1: "nlsatadmissions", D2: "/nlsat-international"})

	def tearDown(self):
		doc = frappe.get_single("Site Domain Settings")
		doc.domains = [r for r in doc.domains if r.domain not in (D1, D2)]
		doc.enabled = 1
		doc.flags.allow_domain_removal = True
		doc.save()
		frappe.db.commit()  # record_domain commits, so the rows must be removed for good
		R.clear_domain_cache()

	def set_routes(self, routes, enabled=1):
		doc = frappe.get_single("Site Domain Settings")
		for r in doc.domains:
			if r.domain in routes:
				r.redirect_to = routes[r.domain]
		doc.enabled = enabled
		doc.save()
		return doc

	def visit(self, host, path="/", query=b""):
		frappe.local.request = SimpleNamespace(host=host, path=path, query_string=query)
		try:
			R.redirect_domain_home()
		except AuthRedirect as e:
			return e.location
		finally:
			del frappe.local.request

	def test_home_page_redirects_per_domain(self):
		self.assertEqual(self.visit(D1), "/nlsatadmissions")  # leading / added
		self.assertEqual(self.visit(D2 + ":443", query=b"a=1"), "/nlsat-international?a=1")

	def test_other_paths_and_domains_untouched(self):
		self.assertIsNone(self.visit(D1, "/nlsatadmissions/login"))
		self.assertIsNone(self.visit(frappe.local.site))

	def test_master_switch_off(self):
		self.set_routes({}, enabled=0)
		self.assertIsNone(self.visit(D1))

	def test_invalid_redirects_blocked(self):
		for bad in ("https://evil.com", "//evil.com", "/", "/a b"):
			with self.assertRaises(frappe.ValidationError):
				self.set_routes({D1: bad})

	def test_primary_domain_cannot_redirect(self):
		doc = frappe.get_single("Site Domain Settings")
		primary = next(r for r in doc.domains if r.is_primary)
		primary.redirect_to = "/nlsatadmissions"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_unknown_host_is_queued_once(self):
		host = "new-domain.example.org"
		frappe.cache.delete_value(f"slcm_site_domain_pending:{host}")
		with patch("frappe.enqueue") as enqueue:
			self.visit(host)
			self.visit(host)
		self.assertEqual(enqueue.call_count, 1)
		frappe.cache.delete_value(f"slcm_site_domain_pending:{host}")

	def test_cache_failure_never_breaks_request(self):
		with patch.object(R, "get_domain_config", side_effect=Exception("redis down")):
			self.assertIsNone(self.visit(D1))

	def test_queue_failure_does_not_stop_redirect(self):
		host = "queue-down.example.org"
		cfg = dict(R.get_domain_config())
		cfg["redirects"] = {**cfg["redirects"], host: "/nlsatadmissions"}
		with patch.object(R, "get_domain_config", return_value=cfg), patch(
			"frappe.enqueue", side_effect=Exception("queue down")
		):
			self.assertEqual(self.visit(host), "/nlsatadmissions")
		# the pending mark is dropped so the next visit tries again
		self.assertFalse(frappe.cache.get_value(f"slcm_site_domain_pending:{host}"))

	def test_unsafe_characters_blocked(self):
		for bad in ('/a"b', "/a\\b", "/a\r\nSet-Cookie:x", "/é"):
			with self.assertRaises(frappe.ValidationError):
				self.set_routes({D1: bad})

	def test_invalid_domain_row_blocked(self):
		doc = frappe.get_single("Site Domain Settings")
		next(r for r in doc.domains if r.domain == D1).domain = "not a domain"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_record_domain_failure_is_logged(self):
		with patch.object(frappe.model.document.Document, "save", side_effect=Exception("db error")), patch(
			"frappe.log_error"
		) as log:
			record_domain("fails.example.org")
		log.assert_called_once()

	def test_page_status_set_on_save(self):
		doc = self.set_routes({D1: "/no-such-page-xyz"})
		rows = {r.domain: r.page_status for r in doc.domains}
		self.assertEqual(rows[D1], "Not Found")
		self.assertEqual(rows[D2], "OK")

	def test_missing_page_is_not_redirected(self):
		self.set_routes({D1: "/no-such-page-xyz"})
		with patch("frappe.log_error") as log:
			self.assertIsNone(self.visit(D1))  # normal home page, not a 404
			self.assertIsNone(self.visit(D1))  # cached: logged once
		self.assertEqual(log.call_count, 1)
		self.assertEqual(self.visit(D2), "/nlsat-international")

	def test_page_deleted_after_save(self):
		from slcm.slcm.doctype.site_domain_settings import site_domain_settings as S

		self.assertEqual(self.visit(D1), "/nlsatadmissions")
		# the page goes away later: the daily check flags it, the redirect stops
		with patch.object(S, "page_exists", return_value=False), patch("frappe.log_error") as log:
			S.check_redirect_pages()
			self.assertIsNone(self.visit(D1))
		self.assertTrue(log.called)
		status = frappe.db.get_value("Site Domain Route", {"parent": "Site Domain Settings", "domain": D1}, "page_status")
		self.assertEqual(status, "Not Found")
		# the page is back: the next check restores the redirect
		S.check_redirect_pages()
		self.assertEqual(self.visit(D1), "/nlsatadmissions")

	def test_domain_rows_cannot_be_deleted(self):
		doc = frappe.get_single("Site Domain Settings")
		doc.domains = [r for r in doc.domains if r.domain != D1]
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_host_checks(self):
		self.assertEqual(R.normalize_host("https://App.Example.com:443/x"), "app.example.com")
		for bad in ("localhost", "127.0.0.1", "", "bad_host.com"):
			self.assertFalse(R.is_valid_host(bad))

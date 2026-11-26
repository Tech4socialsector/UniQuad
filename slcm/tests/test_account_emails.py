"""Register and password reset emails: exactly one email, from the right template.

- Desk: a user added with "Send Welcome Email" ticked gets Frappe's welcome email
  (System Settings > Welcome Email Template); Google sign-ups get nothing.
- NLSAT Domestic / International and PACE: the templates of Applicant Portal Config,
  falling back to System Settings, then to Frappe's own email.
- Password reset from the desk /login page follows the account's portal.
- Links expire after System Settings > Reset Password Link Expiry Duration.

Emails are counted in the real Email Queue, so Frappe's own emails count too.

The sign-up endpoints commit, so the IntegrationTestCase rollback cannot undo them:
test users and templates are deleted (and committed) by the tests themselves.

Run: bench --site <site> run-tests --module slcm.tests.test_account_emails
"""

import email as email_lib
import re
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.core.doctype.user.user import _get_user_for_update_password
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime
from frappe.utils.oauth import update_oauth_user

from slcm.admission.utils.auth_emails import validate_portal_templates
from slcm.api.user import (
	custom_sign_up, register_fle_user, register_pace_user, reset_password, reset_password_pace,
)

CONFIG = "Applicant Portal Config"
PREFIX = "zz-acct-mail-"
TEMPLATES = {
	"nlsat_register_email_template": "ZZ Domestic Register",
	"nlsat_reset_password_template": "ZZ Domestic Reset",
	"intl_register_email_template": "ZZ Intl Register",
	"intl_reset_password_template": "ZZ Intl Reset",
	"pace_register_email_template": "ZZ PACE Register",
	"pace_reset_password_template": "ZZ PACE Reset",
}
SYSTEM = {"welcome_email_template": "ZZ System Welcome", "reset_password_template": "ZZ System Reset"}
BROKEN = "ZZ Broken Register"  # saves (valid syntax) but fails when rendered
NO_LINK = "ZZ No Link Register"  # renders, but has no set-password link
EXTRA = {
	BROKEN: "<p>{{ full_name }}</p>{{ link }} {{ 1 / 0 }}",
	NO_LINK: "<p>Welcome {{ full_name }}</p>",
}


def email(name):
	return f"{PREFIX}{name}@example.com"


def unwrap(fn):
	"""The endpoint without its rate limit (tests send many resets for one user)."""
	return getattr(fn, "__wrapped__", fn)


def commit():
	# The sign-up endpoints commit, so test data must be removed for good.
	frappe.db.commit()  # nosemgrep: frappe-manual-commit


class TestAccountEmails(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.saved_config = {f: frappe.db.get_single_value(CONFIG, f) for f in TEMPLATES}
		cls.saved_system = {f: frappe.db.get_single_value("System Settings", f) for f in SYSTEM}
		cls.saved_expiry = frappe.db.get_single_value("System Settings", "reset_password_link_expiry_duration")

	@classmethod
	def tearDownClass(cls):
		for f, v in cls.saved_config.items():
			frappe.db.set_single_value(CONFIG, f, v)
		for f, v in cls.saved_system.items():
			frappe.db.set_single_value("System Settings", f, v)
		frappe.db.set_single_value("System Settings", "reset_password_link_expiry_duration", cls.saved_expiry)
		for name in [*TEMPLATES.values(), *SYSTEM.values(), *EXTRA]:
			frappe.delete_doc_if_exists("Email Template", name, force=True)
		commit()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		self.cleanup()
		for name in [*TEMPLATES.values(), *SYSTEM.values()]:
			if not frappe.db.exists("Email Template", name):
				frappe.get_doc(
					{
						"doctype": "Email Template",
						"name": name,
						"subject": name + " for {{ full_name }}",
						"use_html": 1,
						"response_html": "<p>{{ full_name }}</p><a href='{{ link }}'>{{ link }}</a> {{ link_expiry }}",
					}
				).insert(ignore_permissions=True)
		for name, body in EXTRA.items():
			if not frappe.db.exists("Email Template", name):
				frappe.get_doc(
					{"doctype": "Email Template", "name": name, "subject": name, "use_html": 1, "response_html": body}
				).insert(ignore_permissions=True)
		self.set_templates(config=True, system=True)
		self.addCleanup(self.cleanup)

	def cleanup(self):
		for name in frappe.get_all("User", filters={"name": ["like", PREFIX + "%"]}, pluck="name"):
			frappe.delete_doc("User", name, ignore_permissions=True, force=True)
		queued = frappe.get_all(
			"Email Queue Recipient", filters={"recipient": ["like", PREFIX + "%"]}, pluck="parent"
		)
		for name in set(queued):
			frappe.delete_doc_if_exists("Email Queue", name, force=True)
		commit()

	def set_templates(self, config, system):
		for f, v in TEMPLATES.items():
			frappe.db.set_single_value(CONFIG, f, v if config else None)
		for f, v in SYSTEM.items():
			frappe.db.set_single_value("System Settings", f, v if system else None)
		frappe.clear_cache()

	def subjects(self, address):
		"""Subjects of the emails queued for `address`."""
		out = []
		for parent in frappe.get_all("Email Queue Recipient", filters={"recipient": address}, pluck="parent"):
			message = frappe.db.get_value("Email Queue", parent, "message") or ""
			out.append(str(email_lib.message_from_string(message)["Subject"]))
		return out

	def html(self, address):
		"""HTML body of the one email queued for `address`."""
		parents = frappe.get_all("Email Queue Recipient", filters={"recipient": address}, pluck="parent")
		self.assertEqual(len(parents), 1, parents)
		message = email_lib.message_from_string(frappe.db.get_value("Email Queue", parents[0], "message"))
		for part in message.walk():
			if part.get_content_type() == "text/html":
				return part.get_payload(decode=True).decode()
		return ""

	def assert_one_email(self, address, subject_start):
		subjects = self.subjects(address)
		self.assertEqual(len(subjects), 1, subjects)
		self.assertTrue(subjects[0].startswith(subject_start), subjects)

	def make_user(self, name, roles=(), **fields):
		"""A user created silently (no email), as a portal account would be."""
		user = frappe.get_doc(
			{"doctype": "User", "email": email(name), "first_name": "ZZ", "user_type": "Website User",
			 "send_welcome_email": 0, **fields}
		)
		user.flags.no_welcome_mail = True
		user.insert(ignore_permissions=True)
		if roles:
			user.add_roles(*roles)
		self.assertEqual(self.subjects(email(name)), [])
		return user

	# --- registration -------------------------------------------------------

	def test_domestic_register(self):
		res = custom_sign_up(email("dom"), "ZZ Dom", portal="Domestic")
		self.assertEqual(res[0], 1, res)
		self.assert_one_email(email("dom"), "ZZ Domestic Register")

	def test_international_register(self):
		res = custom_sign_up(email("intl"), "ZZ Intl", portal="International")
		self.assertEqual(res[0], 1, res)
		self.assert_one_email(email("intl"), "ZZ Intl Register")

	def test_pace_register(self):
		res = unwrap(register_pace_user)(email("pace"), "ZZ Pace")
		self.assertEqual(res["status"], "success", res)
		self.assert_one_email(email("pace"), "ZZ PACE Register")

	def test_pace_register_drops_foreign_redirect(self):
		unwrap(register_pace_user)(email("pace-redir"), "ZZ Pace", redirect_to="https://evil.example/steal")
		self.assertNotIn("evil.example", self.html(email("pace-redir")))
		self.assertNotEqual(frappe.cache().hget("redirect_after_login", email("pace-redir")), "https://evil.example/steal")

	def test_empty_portal_template_uses_system_settings(self):
		self.set_templates(config=False, system=True)
		custom_sign_up(email("dom-sys"), "ZZ Dom", portal="Domestic")
		self.assert_one_email(email("dom-sys"), "ZZ System Welcome")

	def test_nothing_configured_sends_frappe_default(self):
		self.set_templates(config=False, system=False)
		unwrap(register_pace_user)(email("pace-default"), "ZZ Pace")
		subjects = self.subjects(email("pace-default"))
		self.assertEqual(len(subjects), 1, subjects)
		self.assertFalse(subjects[0].startswith("ZZ "), subjects)

	def test_register_link_expires_per_system_settings(self):
		frappe.db.set_single_value("System Settings", "reset_password_link_expiry_duration", 600)
		custom_sign_up(email("expiry"), "ZZ Dom", portal="Domestic")
		key = re.search(r"update-password\?key=(\w+)", self.html(email("expiry"))).group(1)
		self.assertIn("10 minutes", self.html(email("expiry")))

		self.assertFalse(_get_user_for_update_password(key, None).message)  # within 10 minutes: valid
		frappe.db.set_value(
			"User", email("expiry"), "last_reset_password_key_generated_on", now_datetime() - timedelta(minutes=11)
		)
		self.assertEqual(
			_get_user_for_update_password(key, None).message, "The reset password link has been expired"
		)

	def test_template_sent_without_frappe_container(self):
		custom_sign_up(email("no-box"), "ZZ Dom", portal="Domestic")
		# Frappe draws its bordered box only for <table class="body-table with-container">
		self.assertIsNone(re.search(r'class="body-table[^"]*with-container', self.html(email("no-box"))))

	def test_broken_portal_template_falls_back_and_registration_succeeds(self):
		frappe.db.set_single_value(CONFIG, "nlsat_register_email_template", BROKEN)
		res = custom_sign_up(email("broken"), "ZZ Dom", portal="Domestic")
		self.assertEqual(res[0], 1, res)
		self.assertTrue(frappe.db.exists("User", email("broken")))
		self.assert_one_email(email("broken"), "ZZ System Welcome")

	def test_config_rejects_broken_or_linkless_template(self):
		doc = frappe.get_single(CONFIG)
		for bad in (BROKEN, NO_LINK):
			doc.nlsat_register_email_template = bad
			with self.assertRaises(frappe.ValidationError):
				validate_portal_templates(doc)
		doc.nlsat_register_email_template = TEMPLATES["nlsat_register_email_template"]
		validate_portal_templates(doc)  # a good template passes

	def test_fle_keeps_its_own_email(self):
		register_fle_user(email("fle"))
		subjects = self.subjects(email("fle"))
		self.assertEqual(len(subjects), 1, subjects)
		self.assertFalse(subjects[0].startswith("ZZ "), subjects)

	def test_desk_user_with_box_ticked_gets_one_frappe_email(self):
		frappe.get_doc(
			{"doctype": "User", "email": email("desk"), "first_name": "ZZ", "user_type": "Website User",
			 "send_welcome_email": 1}
		).insert(ignore_permissions=True)
		self.assert_one_email(email("desk"), "ZZ System Welcome")

	def test_desk_user_with_box_unticked_gets_no_email(self):
		frappe.get_doc(
			{"doctype": "User", "email": email("desk-off"), "first_name": "ZZ", "user_type": "Website User",
			 "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		self.assertEqual(self.subjects(email("desk-off")), [])

	def test_google_sign_up_sends_no_email(self):
		data = {"id": "zz-acct-google-1", "email": email("sso"), "given_name": "ZZ", "family_name": "SSO"}
		# The only mock: lets Google sign-up through without a configured Social Login Key.
		with patch("frappe.integrations.doctype.social_login_key.social_login_key.provider_allows_signup", return_value=True):
			update_oauth_user(email("sso"), data, "google")
		self.assertTrue(frappe.db.exists("User", email("sso")))
		self.assertEqual(self.subjects(email("sso")), [])

	# --- password reset -----------------------------------------------------

	def test_reset_desk_user_uses_system_settings(self):
		self.make_user("staff")
		self.assertEqual(unwrap(reset_password)(email("staff"))["status"], "ok")
		self.assert_one_email(email("staff"), "ZZ System Reset")

	def test_reset_domestic_applicant_from_desk_login(self):
		self.make_user("dom-reset", roles=["Applicant"], nlsat_portal="Domestic")
		unwrap(reset_password)(email("dom-reset"))
		self.assert_one_email(email("dom-reset"), "ZZ Domestic Reset")

	def test_reset_international_applicant_from_desk_login(self):
		self.make_user("intl-reset", roles=["Applicant"], nlsat_portal="International")
		unwrap(reset_password)(email("intl-reset"))
		self.assert_one_email(email("intl-reset"), "ZZ Intl Reset")

	def test_reset_pace_applicant_from_desk_login(self):
		self.make_user("pace-reset", roles=["PACE Applicant"])
		unwrap(reset_password)(email("pace-reset"))
		self.assert_one_email(email("pace-reset"), "ZZ PACE Reset")

	def test_reset_from_pace_portal(self):
		self.make_user("pace-portal", roles=["PACE Applicant"])
		self.assertEqual(unwrap(reset_password_pace)(email("pace-portal"))["status"], "ok")
		self.assert_one_email(email("pace-portal"), "ZZ PACE Reset")

	def test_reset_from_pace_portal_follows_nlsat_account(self):
		self.make_user("dom-on-pace", roles=["Applicant"], nlsat_portal="Domestic")
		unwrap(reset_password_pace)(email("dom-on-pace"))
		self.assert_one_email(email("dom-on-pace"), "ZZ Domestic Reset")

	def test_reset_empty_pace_template_uses_system_settings(self):
		self.set_templates(config=False, system=True)
		self.make_user("pace-sys", roles=["PACE Applicant"])
		unwrap(reset_password_pace)(email("pace-sys"))
		self.assert_one_email(email("pace-sys"), "ZZ System Reset")

	def test_reset_nothing_configured_sends_frappe_default(self):
		self.set_templates(config=False, system=False)
		self.make_user("dom-default", roles=["Applicant"], nlsat_portal="Domestic")
		unwrap(reset_password)(email("dom-default"))
		self.assert_one_email(email("dom-default"), "Password Reset")

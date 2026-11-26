"""Admission Dashboard API: only the roles of the desk page may read its figures.

Candidates (Applicant role) can read their own Applicant record, which used to be
enough to call these methods and see cycle-wide counts and fee totals.

Run: bench --site <site> run-tests --module slcm.tests.test_admission_dashboard_access
"""

import frappe
from frappe.tests import IntegrationTestCase

from slcm.admission.page.admission_dashboard import admission_dashboard as dashboard

CANDIDATE = "zz-dash-candidate@example.com"
OFFICER = "zz-dash-officer@example.com"


class TestAdmissionDashboardAccess(IntegrationTestCase):
	# User hooks commit, so the users outlive the per-test rollback: made once, removed at the end.
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_user(CANDIDATE, "Website User", ["Applicant"])
		cls.make_user(OFFICER, "System User", ["Admission Officer"])

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for email in (CANDIDATE, OFFICER):
			frappe.delete_doc_if_exists("User", email, force=True)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")

	@staticmethod
	def make_user(email, user_type, roles):
		if frappe.db.exists("User", email):
			return
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "ZZ", "user_type": user_type, "send_welcome_email": 0}
		)
		user.flags.no_welcome_mail = True
		user.insert(ignore_permissions=True)
		user.add_roles(*roles)

	def call(self, user):
		frappe.set_user(user)
		return dashboard.get_bootstrap()

	def test_candidate_is_refused(self):
		self.assertTrue(frappe.has_permission("Applicant", "read", user=CANDIDATE))  # why the old check passed
		self.assertRaises(frappe.PermissionError, self.call, CANDIDATE)

	def test_guest_is_refused(self):
		self.assertRaises(frappe.PermissionError, self.call, "Guest")

	def test_page_role_is_allowed(self):
		self.assertIn("cycles", self.call(OFFICER))

# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
import unittest
from unittest.mock import patch
from frappe.utils import now_datetime, flt, cint

class MockRazorpayClient:
	class MockPayment:
		def __init__(self, payment_data=None):
			self.payment_data = payment_data or {}
		def fetch(self, payment_id):
			return self.payment_data

	class MockOrder:
		def __init__(self, payments_list=None, order_data=None):
			self.payments_list = payments_list or []
			self.order_data = order_data or {"status": "paid"}
		def payments(self, order_id):
			return {"items": self.payments_list}
		def fetch(self, order_id):
			res = dict(self.order_data)
			res["id"] = order_id
			return res

	def __init__(self, auth=None, payment_data=None, payments_list=None, order_data=None):
		self.payment = self.MockPayment(payment_data)
		self.order = self.MockOrder(payments_list, order_data)


TEST_CANDIDATE_NAME = "Test Applicant"
TEST_PACE_FIRST_NAME = "Pace"
TEST_PACE_LAST_NAME = "Applicant"
TEST_PROGRAMME = "Master’s Programme in Public Policy"
# Dedicated fee structure so offer tests never read or rename a real one.
TEST_FEE_STRUCTURE = "_Test Fee Structure Payments"


class PaymentTestBase(unittest.TestCase):
	def setUp(self):
		self.test_docs = []
		self._validate_webhook_signature = False
		self.cleanup_orphan_test_data()

		# Dynamic patch for get_password to skip signature validation by default in webhooks
		self.orig_get_password = frappe.model.base_document.BaseDocument.get_password
		def custom_get_password(doc_self, fieldname="password", raise_exception=True):
			if fieldname == "webhook_secret":
				return "dummy_secret"
			return self.orig_get_password(doc_self, fieldname=fieldname, raise_exception=raise_exception)

		patcher = patch('frappe.model.base_document.BaseDocument.get_password', new=custom_get_password)
		self.addCleanup(patcher.stop)
		patcher.start()

		# Setup bound mock request to avoid Werkzeug context errors in tests
		class MockRequest:
			def __init__(self, test_case):
				self.test_case = test_case
				self.host = "localhost"
				self.url = "http://localhost"
				self.base_url = "http://localhost"
				self.environ = {}
				self.cookies = {}
				self.headers = {}
			def get_data(self):
				payload = getattr(self.test_case, "_webhook_payload", b"")
				return payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

		import json
		self._webhook_payload = b""
		self._orig_request = getattr(frappe.local, "request", None)
		frappe.local.request = MockRequest(self)

		self._snapshot_site_settings()
		self.setup_academic_year_and_cycle()
		self.sync_naming_series_counters()
		self.setup_gateways()

	def _snapshot_site_settings(self):
		"""setUp deactivates site-wide records and overwrites Razorpay Settings; capture them so
		every test restores the site's real configuration afterwards (runs after tearDown, even on failure)."""
		self._site_snapshot = {
			"PACE Admission": dict(frappe.get_all("PACE Admission", fields=["name", "status"], as_list=True)),
			"Admission Year": dict(frappe.get_all("Admission Year", fields=["name", "is_active"], as_list=True)),
			"Fee Structure": dict(frappe.get_all("Fee Structure", fields=["name", "status"], as_list=True)),
			"Academic Year": dict(frappe.get_all("Academic Year", fields=["name", "status"], as_list=True)),
			"series": dict(frappe.db.sql("SELECT `name`, `current` FROM `tabSeries`")),
			"razorpay_singles": frappe.db.sql("SELECT field, value FROM `tabSingles` WHERE doctype = 'Razorpay Settings'"),
			"razorpay_auth": frappe.db.sql("SELECT name, fieldname, password FROM `__Auth` WHERE doctype = 'Razorpay Settings'"),
			"gateway_accounts": set(frappe.get_all("Payment Gateway Account", pluck="name")),
			"accounts": set(frappe.get_all("Account", pluck="name")) if frappe.db.table_exists("Account") else set(),
			"contacts": set(frappe.get_all("Contact", pluck="name")),
			"fee_components": set(frappe.get_all("Fee Component", pluck="name")),
			"integration_requests": set(frappe.get_all("Integration Request", pluck="name")),
		}
		self.addCleanup(self._restore_site_settings)

	def _restore_site_settings(self):
		snapshot = self._site_snapshot
		for doctype, field in (
			("PACE Admission", "status"), ("Admission Year", "is_active"),
			("Fee Structure", "status"), ("Academic Year", "status"),
		):
			for name, value in snapshot[doctype].items():
				if frappe.db.exists(doctype, name) and frappe.db.get_value(doctype, name, field) != value:
					frappe.db.set_value(doctype, name, field, value, update_modified=False)

		for series_key, current in snapshot["series"].items():
			frappe.db.sql("UPDATE `tabSeries` SET `current` = %s WHERE `name` = %s", (current, series_key))

		frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'Razorpay Settings'")
		for field, value in snapshot["razorpay_singles"]:
			frappe.db.sql("INSERT INTO `tabSingles` (doctype, field, value) VALUES ('Razorpay Settings', %s, %s)", (field, value))
		frappe.db.sql("DELETE FROM `__Auth` WHERE doctype = 'Razorpay Settings'")
		for name, fieldname, password in snapshot["razorpay_auth"]:
			frappe.db.sql(
				"INSERT INTO `__Auth` (doctype, name, fieldname, password, encrypted) VALUES ('Razorpay Settings', %s, %s, %s, 1)",
				(name, fieldname, password),
			)

		# Saving Razorpay Settings makes ERPNext (when installed) create a gateway account and ledger account.
		for pga in set(frappe.get_all("Payment Gateway Account", pluck="name")) - snapshot["gateway_accounts"]:
			account = frappe.db.get_value("Payment Gateway Account", pga, "payment_account")
			frappe.delete_doc("Payment Gateway Account", pga, ignore_permissions=True, force=True)
			if account and account not in snapshot["accounts"] and not frappe.db.exists("GL Entry", {"account": account}):
				frappe.delete_doc("Account", account, ignore_permissions=True, force=True)

		# Fee Components the app auto-creates during a test run (e.g. "Application Fee").
		for component in set(frappe.get_all("Fee Component", pluck="name")) - snapshot["fee_components"]:
			frappe.delete_doc("Fee Component", component, ignore_permissions=True, force=True)

		# Contacts auto-created for test users, and gateway logs whose test documents are gone.
		for contact in set(frappe.get_all("Contact", {"email_id": ["like", "%@example.com"]}, pluck="name")) - snapshot["contacts"]:
			frappe.delete_doc("Contact", contact, ignore_permissions=True, force=True)
		new_requests = set(frappe.get_all("Integration Request", pluck="name")) - snapshot["integration_requests"]
		for ir in frappe.get_all("Integration Request", {"name": ["in", list(new_requests) or [""]]}, ["name", "reference_doctype", "reference_docname"]):
			if not (ir.reference_doctype and ir.reference_docname and frappe.db.exists(ir.reference_doctype, ir.reference_docname)):
				frappe.delete_doc("Integration Request", ir.name, ignore_permissions=True, force=True)

		frappe.clear_document_cache("Razorpay Settings", "Razorpay Settings")
		frappe.db.commit()

	def tearDown(self):
		# Restore request
		if getattr(self, "_orig_request", None) is not None:
			frappe.local.request = self._orig_request
		elif hasattr(frappe.local, "request"):
			delattr(frappe.local, "request")

		seen = set()
		for doc in reversed(self.test_docs):
			key = (doc.doctype, doc.name)
			if key in seen:
				continue
			seen.add(key)
			self._delete_doc_tree(doc.doctype, doc.name)
		self.cleanup_orphan_test_data()
		frappe.db.commit()

	def _force_delete_doc(self, doctype, name):
		if not frappe.db.exists(doctype, name):
			return
		doc = frappe.get_doc(doctype, name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

	def _delete_doc_tree(self, doctype, name):
		try:
			if doctype == "Applicant":
				self._delete_applicant_tree(name)
			elif doctype == "PACE Application":
				self._delete_pace_application_tree(name)
			elif doctype == "Offer Letter":
				self._delete_offer_letter_tree(name)
			elif doctype == "Applicant Fee Assignment":
				self._delete_applicant_fee_assignment_tree(name)
			elif doctype == "PACE Applicant Fee Assignment":
				self._delete_pace_applicant_fee_assignment_tree(name)
			else:
				self._force_delete_doc(doctype, name)
		except Exception:
			pass

	def _delete_payment_requests_for(self, ref_doctype, ref_name):
		for pr_name in frappe.get_all(
			"SLCM Payment Request",
			filters={"reference_doctype": ref_doctype, "reference_name": ref_name},
			pluck="name",
		):
			self._force_delete_doc("SLCM Payment Request", pr_name)

	def _delete_applicant_payment_receipts(self, applicant_name):
		for receipt in frappe.get_all(
			"Applicant Payment Receipt",
			filters={"applicant": applicant_name},
			pluck="name",
		):
			self._force_delete_doc("Applicant Payment Receipt", receipt)

	def _delete_pace_payment_receipts(self, pace_application_name):
		for receipt in frappe.get_all(
			"PACE Receipt",
			filters={"pace_application": pace_application_name},
			pluck="name",
		):
			self._force_delete_doc("PACE Receipt", receipt)

	def _delete_applicant_tree(self, applicant_name):
		self._delete_applicant_payment_receipts(applicant_name)
		self._delete_payment_requests_for("Applicant", applicant_name)
		for afa in frappe.get_all(
			"Applicant Fee Assignment", filters={"applicant": applicant_name}, pluck="name"
		):
			self._delete_applicant_fee_assignment_tree(afa)
		for offer in frappe.get_all("Offer Letter", filters={"applicant": applicant_name}, pluck="name"):
			self._delete_offer_letter_tree(offer)
		self._force_delete_doc("Applicant", applicant_name)

	def _delete_applicant_fee_assignment_tree(self, afa_name):
		self._delete_payment_requests_for("Applicant Fee Assignment", afa_name)
		self._delete_applicant_payment_receipts(
			frappe.db.get_value("Applicant Fee Assignment", afa_name, "applicant")
		)
		self._force_delete_doc("Applicant Fee Assignment", afa_name)

	def _delete_offer_letter_tree(self, offer_name):
		applicant = frappe.db.get_value("Offer Letter", offer_name, "applicant")
		for afa in frappe.get_all(
			"Applicant Fee Assignment", filters={"offer_letter": offer_name}, pluck="name"
		):
			self._delete_applicant_fee_assignment_tree(afa)
		self._delete_payment_requests_for("Offer Letter", offer_name)
		if applicant:
			self._delete_applicant_payment_receipts(applicant)
		self._force_delete_doc("Offer Letter", offer_name)

	def _delete_pace_application_tree(self, pace_app_name):
		self._delete_pace_payment_receipts(pace_app_name)
		self._delete_payment_requests_for("PACE Application", pace_app_name)
		for pafa in frappe.get_all(
			"PACE Applicant Fee Assignment", filters={"applicant": pace_app_name}, pluck="name"
		):
			self._delete_pace_applicant_fee_assignment_tree(pafa)
		self._force_delete_doc("PACE Application", pace_app_name)

	def _delete_pace_applicant_fee_assignment_tree(self, pafa_name):
		self._delete_payment_requests_for("PACE Applicant Fee Assignment", pafa_name)
		pace_app = frappe.db.get_value("PACE Applicant Fee Assignment", pafa_name, "applicant")
		if pace_app:
			self._delete_pace_payment_receipts(pace_app)
		self._force_delete_doc("PACE Applicant Fee Assignment", pafa_name)

	def _max_serial_suffix(self, doctype, name_like):
		names = frappe.db.sql_list(
			f"SELECT name FROM `tab{doctype}` WHERE name LIKE %s", (name_like,)
		)
		import re
		max_val = 0
		for name in names:
			match = re.search(r'\d+$', name)
			if match:
				val = int(match.group())
				if val > max_val:
					max_val = val
		return max_val

	def _set_series_counter(self, series_key, value):
		# Only ever raise a counter: the "" key is shared by every format:{###} DocType on the site,
		# so lowering it makes unrelated DocTypes reuse existing names.
		if frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name`=%s", (series_key,)):
			frappe.db.sql("UPDATE `tabSeries` SET `current`=GREATEST(`current`, %s) WHERE `name`=%s", (value, series_key))
		else:
			frappe.db.sql("INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, %s)", (series_key, value))

	def sync_naming_series_counters(self):
		"""Prevent format: autoname collisions with stale tabSeries rows."""
		year = str(now_datetime().year)
		applicant_max = self._max_serial_suffix("Applicant", f"APP-{year}-%")
		for key in (f"APP-{year}-", ""):
			self._set_series_counter(key, applicant_max)

		afa_max = self._max_serial_suffix("Applicant Fee Assignment", f"AFA-{year}-%")
		self._set_series_counter(f"AFA-{year}-", afa_max)
		self._set_series_counter(f"AFA-{year}-.", afa_max)

		pace_max = self._max_serial_suffix("PACE Application", f"PACE-%")
		for key in (
			f"PACE-{self.academic_year}-",
			f"PACE-{year} - {self.academic_year}-",
			f"PACE-{year}-27-",
		):
			self._set_series_counter(key, pace_max)

		pafa_max = self._max_serial_suffix("PACE Applicant Fee Assignment", "AFA-PACE-%")
		self._set_series_counter(f"AFA-PACE-{year}-", pafa_max)

		frappe.db.commit()

	def cleanup_orphan_test_data(self):
		for applicant in frappe.get_all(
			"Applicant", filters={"candidate_name": TEST_CANDIDATE_NAME}, pluck="name"
		):
			self._delete_applicant_tree(applicant)
		for pace_app in frappe.get_all(
			"PACE Application",
			filters={"first_name": TEST_PACE_FIRST_NAME, "last_name": TEST_PACE_LAST_NAME},
			pluck="name",
		):
			self._delete_pace_application_tree(pace_app)
		frappe.db.commit()

	def setup_academic_year_and_cycle(self):
		self.academic_year = "2026-27"
		self.admission_cycle = "2026-May To June"
		self._ensure_test_programme()

		# Deactivate existing active PACE Admissions, Admission Years and Fee Structures to avoid single active conflicts
		frappe.db.sql("UPDATE `tabPACE Admission` SET status = 'Closed' WHERE status = 'Active'")
		frappe.db.sql("UPDATE `tabAdmission Year` SET is_active = 0 WHERE is_active = 1")
		frappe.db.sql("UPDATE `tabFee Structure` SET status = 'Inactive' WHERE status = 'Active'")
		
		# Setup Razorpay Settings bypassing validation
		for field, value in {
			'api_key': 'test_key',
			'api_secret': 'test_secret',
			'webhook_secret': 'test_secret'
		}.items():
			frappe.db.sql("""
				INSERT INTO `tabSingles` (doctype, field, value)
				VALUES ('Razorpay Settings', %s, %s)
				ON DUPLICATE KEY UPDATE value=%s
			""", (field, value, value))
		
		frappe.db.commit()

		# Ensure Academic Year exists and is Active
		if not frappe.db.exists("Academic Year", self.academic_year):
			ac_yr = frappe.new_doc("Academic Year")
			ac_yr.academic_year_name = self.academic_year
			ac_yr.status = "Active"
			ac_yr.insert(ignore_permissions=True, ignore_mandatory=True)
			self.test_docs.append(ac_yr)
		else:
			frappe.db.set_value("Academic Year", self.academic_year, "status", "Active")

		# Ensure Admission Year, Cycle and Campus exist for Link validation
		if not frappe.db.exists("Admission Year", self.academic_year):
			ay = frappe.new_doc("Admission Year")
			ay.year = self.academic_year
			ay.insert(ignore_permissions=True, ignore_mandatory=True)
			self.test_docs.append(ay)

		if not frappe.db.exists("Admission Cycle", self.admission_cycle):
			ac = frappe.new_doc("Admission Cycle")
			ac.cycle_name = self.admission_cycle
			ac.insert(ignore_permissions=True, ignore_mandatory=True)
			self.test_docs.append(ac)

		if not frappe.db.exists("Campus", "Bengaluru"):
			c = frappe.new_doc("Campus")
			c.campus_name = "Bengaluru"
			c.insert(ignore_permissions=True, ignore_mandatory=True)
			self.test_docs.append(c)

		if not frappe.db.exists("PACE Programme", "Postgraduate Diploma in Consumer Law & Practice"):
			prog = frappe.new_doc("PACE Programme")
			prog.programme_prefix = "Postgraduate Diploma in"
			prog.programme_name = "Consumer Law & Practice"
			prog.published = 1
			prog.insert(ignore_permissions=True, ignore_mandatory=True)
			self.test_docs.append(prog)

		# Active PACE Admission for testing
		expected_name = f"PACE-ADM-{self.academic_year}"
		if not frappe.db.exists("PACE Admission", expected_name):
			pa = frappe.new_doc("PACE Admission")
			pa.academic_year = self.academic_year
			pa.status = "Active"
			pa.payment_gateway = "Razorpay"
			pa.admission_close_date = "2030-12-31"
			pa.append("programmes", {
				"programme": "Postgraduate Diploma in Consumer Law & Practice",
				"application_fee_indian": 1000,
				"application_fee_foreign": 2000,
				"status": "Open"
			})
			pa.insert(ignore_permissions=True, ignore_mandatory=True)
			self.test_docs.append(pa)
		else:
			frappe.db.set_value("PACE Admission", expected_name, "status", "Active")
			pa = frappe.get_doc("PACE Admission", expected_name)
			has_prog = any(p.programme == "Postgraduate Diploma in Consumer Law & Practice" for p in pa.programmes)
			if not has_prog:
				pa.append("programmes", {
					"programme": "Postgraduate Diploma in Consumer Law & Practice",
					"application_fee_indian": 1000,
					"application_fee_foreign": 2000,
					"status": "Open"
				})
				pa.save(ignore_permissions=True)

	def _ensure_test_programme(self):
		"""Applicant / Offer Letter / Fee Assignment link to this Programme; create it when the site lacks it."""
		if frappe.db.exists("Programme", TEST_PROGRAMME):
			return
		prog = frappe.new_doc("Programme")
		prog.program_code = "TESTMPP"
		prog.program_name = TEST_PROGRAMME
		prog.level_of_study = "Postgraduate"
		prog.academic_year = self.academic_year
		prog.flags.ignore_links = True
		prog.insert(ignore_permissions=True, ignore_mandatory=True, set_name=TEST_PROGRAMME)
		# addCleanup also runs when a later setUp step fails (tearDown does not).
		self.addCleanup(self._force_delete_doc, "Programme", prog.name)

	def setup_gateways(self):
		# Ensure Razorpay settings doc exists and set dummy credentials
		settings = frappe.get_doc("Razorpay Settings")
		settings.api_key = "rzp_test_t2c16e5FQHvi6D"
		settings.api_secret = "NSVlhjaeUvoeweYNhaygaXat"
		settings.webhook_secret = "dummy_secret"
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)

	def register_doc(self, doc):
		self.test_docs.append(doc)
		return doc

	def create_applicant(self, name_prefix="TEST-APP", email=None, amount=1000):
		import random
		email = email or f"app_{frappe.generate_hash(length=8)}@example.com"
		app = frappe.new_doc("Applicant")
		app.candidate_name = TEST_CANDIDATE_NAME
		app.email = email
		app.mobile_number = f"+919{random.randint(100000000, 999999999)}"
		app.gender = "Male"
		app.date_of_birth = "2000-01-01"
		app.academic_year = self.academic_year
		app.admission_cycle = self.admission_cycle
		app.program = TEST_PROGRAMME
		app.application_fee_status = "Requested"
		app.application_fee_amount = amount
		app.insert(ignore_permissions=True, ignore_mandatory=True)
		return self.register_doc(app)

	def create_offer_letter(self, applicant_name, amount=5000):
		fc_name = frappe.db.get_value("Fee Component", {"component_name": "Admission Fee"}, "name")
		if not fc_name:
			fc = frappe.new_doc("Fee Component")
			fc.component_name = "Admission Fee"
			fc.amount = amount
			fc.insert(ignore_permissions=True, ignore_mandatory=True)
			self.test_docs.append(fc)
			fc_name = fc.name

		if not frappe.db.exists("Fee Structure", TEST_FEE_STRUCTURE):
			fs = frappe.new_doc("Fee Structure")
			fs.fee_structure = TEST_FEE_STRUCTURE
			fs.academic_year = self.academic_year
			fs.program = TEST_PROGRAMME
			fs.total_amount_for_indian = 5000
			fs.append("fee_components_for_indian", {
				"fee_component": fc_name,
				"amount": 5000,
				"total_amount": 5000
			})
			# Bypass autoname using rename_doc
			fs.flags.ignore_mandatory = True
			fs.insert(ignore_permissions=True, ignore_mandatory=True)
			if fs.name != TEST_FEE_STRUCTURE:
				frappe.rename_doc("Fee Structure", fs.name, TEST_FEE_STRUCTURE, force=True, ignore_if_exists=True)
				fs = frappe.get_doc("Fee Structure", TEST_FEE_STRUCTURE)
			self.test_docs.append(fs)

		offer = frappe.new_doc("Offer Letter")
		offer.applicant = applicant_name
		offer.program = TEST_PROGRAMME
		offer.campus = "Bengaluru"
		offer.academic_year = self.academic_year
		offer.admission_year = self.academic_year
		offer.status = "Accepted"
		offer.payable_amount = amount
		offer.fee_structure = TEST_FEE_STRUCTURE
		offer.insert(ignore_permissions=True, ignore_mandatory=True)
		if amount is not None:
			frappe.db.set_value("Offer Letter", offer.name, "payable_amount", amount, update_modified=False)
			offer.payable_amount = amount
		return self.register_doc(offer)

	def offer_amount_paise(self, offer_name, afa_name=None):
		amount_inr = flt(frappe.db.get_value("Offer Letter", offer_name, "payable_amount"))
		if afa_name:
			afa_amount = flt(frappe.db.get_value("Applicant Fee Assignment", afa_name, "final_payable_amount"))
			if afa_amount:
				amount_inr = afa_amount
		return amount_inr, int(amount_inr * 100)

	def create_applicant_fee_assignment(self, offer_name, applicant_name, fee_type="Confirmation Fee", amount=5000):
		existing = frappe.db.get_value("Applicant Fee Assignment", {"offer_letter": offer_name, "status": "Assigned"}, "name")
		if existing:
			afa = frappe.get_doc("Applicant Fee Assignment", existing)
			if amount is not None:
				afa.db_set("final_payable_amount", amount)
			return self.register_doc(afa)

		afa = frappe.new_doc("Applicant Fee Assignment")
		afa.offer_letter = offer_name
		afa.applicant = applicant_name
		afa.fee_type = fee_type
		afa.academic_year = self.academic_year
		afa.admission_cycle = self.admission_cycle
		afa.program = TEST_PROGRAMME
		afa.status = "Assigned"
		afa.total_amount = amount
		afa.final_payable_amount = amount
		afa.insert(ignore_permissions=True, ignore_mandatory=True)
		return self.register_doc(afa)

	def create_pace_application(self, email=None):
		import random
		email = email or f"pace_{frappe.generate_hash(length=8)}@example.com"
		# PACE Application.before_save links user_id to the applicant's email, so the User must exist.
		if not frappe.db.exists("User", email):
			user = frappe.get_doc({
				"doctype": "User", "email": email, "first_name": TEST_PACE_FIRST_NAME,
				"user_type": "Website User", "send_welcome_email": 0,
			}).insert(ignore_permissions=True)
			self.register_doc(user)
		papp = frappe.new_doc("PACE Application")
		papp.upload_student_photo = "/files/photo.jpg"
		papp.title = "Mr"
		papp.first_name = TEST_PACE_FIRST_NAME
		papp.last_name = TEST_PACE_LAST_NAME
		papp.email_address = email
		papp.mobile_number = f"+919{random.randint(100000000, 999999999)}"
		papp.date_of_birth = "1995-05-15"
		papp.gender = "Male"
		papp.nationality = "Indian"
		papp.category = "General"
		papp.currently_employed = "No"
		papp.differently_abled = "No"
		papp.how_did_you_hear_about_us = "NLSIU Website"
		papp.father_title = "Mr"
		papp.father_name = "Father"
		papp.mother_title = "Mrs"
		papp.mother_name = "Mother"
		papp.country = "India"
		papp.state = "Karnataka"
		papp.district = "Bengaluru"
		papp.city = "Bengaluru"
		papp.address_line_1 = "Test Address"
		papp.pincode = 560001
		papp.status = "Draft"
		papp.programme = "Postgraduate Diploma in Consumer Law & Practice"
		papp.academic_year = self.academic_year
		papp.student_signature = "/files/sig.png"
		papp.ug_degree_certificate = "/files/dummy_certificate.pdf"
		papp.govt_id = "/files/id.pdf"
		papp.i_agree = 1
		papp.append("ug_degree", {
			"institution_name": "Test Institution",
			"university": "Test University",
			"programme_studied": "Law",
			"year_of_passing": 2020,
			"result_status": "Waiting for result"
		})
		papp.insert(ignore_permissions=True, ignore_mandatory=True)
		return self.register_doc(papp)

	def create_pace_applicant_fee_assignment(self, applicant_name, fee_type="Application Fee", amount=1000):
		pafa = frappe.new_doc("PACE Applicant Fee Assignment")
		pafa.applicant = applicant_name
		pafa.fee_type = fee_type
		pafa.program = "Postgraduate Diploma in Consumer Law & Practice"
		pafa.academic_year = self.academic_year
		pafa.status = "Assigned"
		pafa.total_amount = amount
		pafa.final_payable_amount = amount
		pafa.insert(ignore_permissions=True, ignore_mandatory=True)
		return self.register_doc(pafa)

	def create_payment_request(self, ref_doctype, ref_name, transaction_id, amount=1000):
		pr = frappe.new_doc("SLCM Payment Request")
		pr.reference_doctype = ref_doctype
		pr.reference_name = ref_name
		pr.payment_gateway = "Razorpay"
		pr.amount = amount
		pr.currency = "INR"
		pr.email_to = "test@example.com"
		pr.subject = "Test Payment Request"
		pr.transaction_id = transaction_id
		pr.razorpay_order_id = transaction_id
		pr.status = "Requested"
		pr.insert(ignore_permissions=True, ignore_mandatory=True)
		pr.submit()
		return self.register_doc(pr)

	def create_fee_component(self, name, amount=1000, is_accommodation_fee=0):
		# Test-owned component: never reuse (and overwrite) a real component with the same name.
		name = f"_Test {name}"
		existing = frappe.db.get_value("Fee Component", {"component_name": name}, "name")
		if existing:
			frappe.db.set_value("Fee Component", existing, {"amount": amount, "is_accommodation_fee": is_accommodation_fee})
			return existing

		fc = frappe.new_doc("Fee Component")
		fc.component_name = name
		fc.amount = amount
		fc.is_accommodation_fee = is_accommodation_fee
		fc.insert(ignore_permissions=True, ignore_mandatory=True)
		self.test_docs.append(fc)
		return fc.name

	def create_fee_structure(self, name, components=None, confirmation_fee=0):
		components = components or []
		fs = frappe.new_doc("Fee Structure")
		fs.fee_structure = name
		fs.academic_year = self.academic_year
		fs.program = f"Program {name}"
		fs.is_confirmation_fee_applicable = 1 if confirmation_fee > 0 else 0
		fs.confirmation_fee_amount = confirmation_fee
		total = 0
		for comp_name, amt in components:
			fs.append("fee_components_for_indian", {
				"fee_component": comp_name,
				"amount": amt,
				"total_amount": amt
			})
			total += amt
		fs.total_amount_for_indian = total
		fs.flags.ignore_mandatory = True
		fs.flags.ignore_validate = True
		fs.flags.ignore_links = True
		fs.insert(ignore_permissions=True, ignore_mandatory=True)
		if fs.name != name:
			frappe.rename_doc("Fee Structure", fs.name, name, force=True, ignore_if_exists=True)
			fs = frappe.get_doc("Fee Structure", name)
		return self.register_doc(fs)

	def mock_razorpay(self, payment_data=None, payments_list=None, order_data=None):
		# Instantiate a mock client with desired return values
		mock_client = MockRazorpayClient(payment_data=payment_data, payments_list=payments_list, order_data=order_data)
		
		# Patch the Client constructor
		patcher = patch('razorpay.Client', return_value=mock_client)
		self.addCleanup(patcher.stop)
		return patcher.start()

	def bind_webhook_request(self, payload):
		import json
		data = json.dumps(payload).encode("utf-8") if isinstance(payload, dict) else payload

		class MockRequest:
			headers = {}

			def get_data(self):
				return data

		frappe.local.request = MockRequest()

	def sign_webhook_request(self, *args, **kwargs):
		"""Valid X-Razorpay-Signature for the mocked request body; the webhook rejects unsigned calls."""
		import hashlib, hmac
		return hmac.new(b"dummy_secret", frappe.request.get_data(), hashlib.sha256).hexdigest()

	def dispatch_razorpay_webhook(self, payload):
		from slcm.api.razorpay_webhook import handle_razorpay_webhook
		import hmac, hashlib, json
		
		self.bind_webhook_request(payload)
		raw_data = json.dumps(payload).encode("utf-8")
		# Provide the correct HMAC signature based on dummy_secret
		secret = b"dummy_secret"
		correct_sig = hmac.new(secret, raw_data, hashlib.sha256).hexdigest()
		with patch("frappe.get_request_header", return_value=correct_sig):
			handle_razorpay_webhook()

	def mock_signature_verification(self):
		patcher = patch('payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.RazorpaySettings.verify_signature', return_value=True)
		self.addCleanup(patcher.stop)
		return patcher.start()

# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Per-charge payment gateway routing (Razorpay / Easebuzz) for Student and Parent Portal payments.

Covers slcm.slcm.fee.payment_gateway, the gateway-aware "create order" endpoints in
slcm.api.student_payment / transcript_request, and the Easebuzz checkout, callback, webhook,
result and reconciliation code in slcm.api.easebuzz_payment.

Easebuzz's servers are never called: initiate / retrieve are mocked and callbacks are signed with
a test salt. Every test runs in one transaction that is rolled back (commits are disabled), so the
site's data is untouched.

Run: bench --site <site> run-tests --module slcm.tests.payment.test_portal_gateway_routing
"""

import datetime
import json
import os
import re
import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, flt, get_datetime, today

from payments.payment_gateways.doctype.easebuzz_settings import easebuzz_settings as ezs
from slcm.api import easebuzz_payment as ez
from slcm.api import student_payment as sp
from slcm.slcm.fee import payment_gateway as gw

SALT, KEY = "TESTSALT", "TESTMERCHANTKEY"
ACCESS_KEY = "TESTACCESSKEY123"


def signed(txnid, amount, status="success", easepayid="EZTEST0001", **extra):
	"""An Easebuzz callback payload with a valid response hash."""
	params = {
		"key": KEY, "txnid": txnid, "amount": f"{flt(amount):.2f}", "productinfo": "Fee", "firstname": "Test",
		"email": "t@example.com", "status": status, "easepayid": easepayid, "mode": "UPI", "bank_ref_num": "BRN1",
		**{f"udf{i}": "" for i in range(1, 11)},
		**extra,
	}
	params["hash"] = ezs.generate_response_hash(params, SALT)
	return params


class GatewayTestCase(unittest.TestCase):
	"""Fixtures: one student (+ parent) with two unpaid Fee Demands on two test components."""

	def setUp(self):
		self._commit = patch.object(frappe.db, "commit", lambda *a, **k: None)
		self._commit.start()
		self.calls = []
		calls = self.calls
		patches = [
			patch.object(ezs.EasebuzzSettings, "get_salt", lambda self: SALT),
			patch.object(ezs.EasebuzzSettings, "initiate_payment", lambda self, **kw: (calls.append(kw), ACCESS_KEY)[1]),
			# never call Razorpay's API (payment details lookups in the payment ledger sweep)
			patch.object(sp, "_fetch_razorpay_payment_details", lambda payment_id: {}),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)
		self._user = frappe.session.user
		frappe.set_user("Administrator")
		frappe.local.response = frappe._dict()
		frappe.db.set_single_value("Easebuzz Settings", {"enabled": 1, "merchant_key": KEY, "environment": "Test"})
		self.make_fixtures()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		self._commit.stop()
		frappe.set_user(self._user)
		# checkout claims live in Redis (not rolled back) and student names repeat after the rollback
		frappe.cache().delete_value(f"slcm_checkout_claim:{self.student}")

	# ── fixtures ──
	def make_user(self, email, first_name):
		if not frappe.db.exists("User", email):
			frappe.get_doc({
				"doctype": "User", "email": email, "first_name": first_name,
				"user_type": "Website User", "send_welcome_email": 0,
			}).insert(ignore_permissions=True)
		return email

	def make_fixtures(self):
		self.student_user = self.make_user("_gw_student@example.com", "GwStudent")
		self.parent_user = self.make_user("_gw_parent@example.com", "GwParent")
		self.other_user = self.make_user("_gw_other@example.com", "GwOther")

		sm = frappe.new_doc("Student Master")
		sm.update({
			"first_name": "Gateway", "last_name": "Tester", "email": self.student_user, "user": self.student_user,
			"official_email_id": self.student_user, "phone": "+91-98765 43210",
		})
		sm.append("parents", {"email": self.parent_user})
		sm.flags.ignore_mandatory = True
		sm.flags.ignore_validate = True
		sm.flags.ignore_links = True
		sm.insert(ignore_permissions=True)
		self.student = sm.name

		self.comp_rzp = self.make_component("_GW Razorpay Fee", "Razorpay")
		self.comp_ez = self.make_component("_GW Easebuzz Fee", "Easebuzz")
		self.d_rzp = self.make_demand(self.comp_rzp, 1000)
		self.d_ez = self.make_demand(self.comp_ez, 2500)

	def make_component(self, name, gateway):
		if not frappe.db.exists("Fee Component", name):
			frappe.get_doc({
				"doctype": "Fee Component", "component_name": name, "component_type": "Other",
				"demand_type": "Non Academic", "payment_gateway": gateway,
			}).insert(ignore_permissions=True)
		else:
			frappe.db.set_value("Fee Component", name, "payment_gateway", gateway)
		return name

	def make_demand(self, component, amount):
		doc = frappe.get_doc({
			"doctype": "Fee Demand", "student": self.student, "fee_component": component,
			"original_amount": amount, "demand_date": today(), "due_date": add_days(today(), 10),
			"academic_year": frappe.db.get_value("Academic Year", {}, "name", order_by="creation desc"),
		})
		doc.flags.ignore_links = True
		doc.insert(ignore_permissions=True)
		return doc.name

	def as_guest_callback(self, fn, params):
		frappe.set_user("Guest")
		frappe.local.response = frappe._dict()
		try:
			return fn(**params)
		finally:
			frappe.set_user("Administrator")

	def ir_status(self, txnid):
		return frappe.db.get_value("Integration Request", txnid, "status")

	def outstanding(self, demand):
		return flt(frappe.db.get_value("Fee Demand", demand, "outstanding_amount"))


class TestGatewayResolution(GatewayTestCase):
	def test_component_gateways(self):
		self.assertEqual(gw.for_component(self.comp_rzp), "Razorpay")
		self.assertEqual(gw.for_component(self.comp_ez), "Easebuzz")
		self.assertEqual(gw.for_demand(self.d_ez), "Easebuzz")

	def test_unknown_or_blank_falls_back_to_razorpay(self):
		self.assertEqual(gw.for_component(None), "Razorpay")
		self.assertEqual(gw.for_component("_GW does not exist"), "Razorpay")
		self.assertEqual(gw.normalize("PayU"), "Razorpay")

	def test_readiness(self):
		self.assertTrue(gw.is_ready("Easebuzz"))
		frappe.db.set_single_value("Easebuzz Settings", "enabled", 0)
		self.assertFalse(gw.is_ready("Easebuzz"))
		self.assertRaises(frappe.ValidationError, gw.ensure_ready, "Easebuzz")

	def test_transcript_setting(self):
		frappe.db.set_single_value("Transcript Fee Settings", "payment_gateway", "Easebuzz")
		self.assertEqual(gw.for_transcript(), "Easebuzz")

	def test_no_unfiltered_gateway_lookups_left(self):
		"""Admissions must never pick up the Easebuzz Payment Gateway row by accident."""
		root = frappe.get_app_path("slcm")
		pattern = re.compile(r"get_value\(\s*[\"']Payment Gateway[\"']\s*,\s*\{\s*\}")
		hits = []
		for base, _dirs, files in os.walk(root):
			if "/tests" in base or "node_modules" in base:
				continue
			for f in files:
				if f.endswith(".py"):
					path = os.path.join(base, f)
					with open(path, encoding="utf-8") as fh:
						if pattern.search(fh.read()):
							hits.append(path)
		self.assertEqual(hits, [], "unfiltered Payment Gateway lookups: %s" % hits)


class TestPortalCheckout(GatewayTestCase):
	def test_mixed_pay_all_returns_split(self):
		frappe.set_user(self.student_user)
		res = sp.create_bulk_demand_payment_order(json.dumps([self.d_rzp, self.d_ez]))
		self.assertEqual(res["status"], "split")
		groups = {g["gateway"]: g for g in res["groups"]}
		self.assertEqual(groups["Easebuzz"]["demand_names"], [self.d_ez])
		self.assertEqual(groups["Razorpay"]["demand_names"], [self.d_rzp])
		self.assertEqual(flt(groups["Easebuzz"]["total"]), 2500)
		self.assertFalse(self.calls, "no checkout is created for a split")

	def test_forcing_gateway_on_mixed_set_is_rejected(self):
		frappe.set_user(self.student_user)
		self.assertRaises(
			frappe.ValidationError, sp.create_bulk_demand_payment_order,
			json.dumps([self.d_rzp, self.d_ez]), None, "Easebuzz",
		)

	def test_easebuzz_checkout_uses_server_amount(self):
		frappe.set_user(self.student_user)
		res = sp.create_bulk_demand_payment_order(json.dumps([self.d_ez]))
		self.assertEqual(res["gateway"], "Easebuzz")
		self.assertTrue(res["checkout_url"].endswith("/pay/" + ACCESS_KEY))
		sent = self.calls[-1]
		self.assertEqual(flt(sent["amount"]), 2500)
		self.assertEqual(sent["phone"], "9876543210")
		self.assertEqual(sent["txnid"], res["txnid"])
		self.assertTrue(sent["surl"].endswith("/api/method/slcm.api.easebuzz_payment.complete"))
		data = json.loads(frappe.db.get_value("Integration Request", res["txnid"], "data"))
		self.assertEqual(data["demand_names"], [self.d_ez])
		self.assertEqual(data["user"], self.student_user)
		self.assertEqual(self.ir_status(res["txnid"]), "Queued")

	def test_single_demand_routes_by_component(self):
		frappe.set_user(self.student_user)
		self.assertEqual(sp.create_demand_payment_order(self.d_ez)["gateway"], "Easebuzz")

	def test_other_students_demand_is_refused(self):
		frappe.set_user(self.other_user)
		self.assertRaises(Exception, sp.create_demand_payment_order, self.d_ez)

	def test_easebuzz_not_ready_blocks_checkout(self):
		frappe.db.set_single_value("Easebuzz Settings", "enabled", 0)
		frappe.set_user(self.student_user)
		self.assertRaises(frappe.ValidationError, sp.create_demand_payment_order, self.d_ez)

	def test_missing_phone_is_explained(self):
		frappe.db.set_value("Student Master", self.student, {"phone": "", "alternate_phone": ""})
		frappe.set_user(self.student_user)
		with self.assertRaises(frappe.ValidationError) as ctx:
			sp.create_demand_payment_order(self.d_ez)
		self.assertIn("mobile", str(ctx.exception).lower())

	def test_unknown_return_page_is_refused(self):
		frappe.set_user(self.student_user)
		self.assertRaises(
			frappe.ValidationError, ez.start_checkout, "demands", self.student, 10,
			{"demand_names": [self.d_ez]}, "Fee", "https://evil.example.com/",
		)

	def test_parent_checkout_returns_to_ward(self):
		frappe.set_user(self.parent_user)
		res = sp.parent_create_bulk_demand_payment_order(json.dumps([self.d_ez]), self.student)
		data = json.loads(frappe.db.get_value("Integration Request", res["txnid"], "data"))
		self.assertEqual(data["paid_by_role"], "Parent")
		self.assertEqual(data["return_path"], f"/parent-portal/fees?ward={self.student}")

	def test_parent_mixed_returns_split(self):
		frappe.set_user(self.parent_user)
		res = sp.parent_create_bulk_demand_payment_order(json.dumps([self.d_rzp, self.d_ez]), self.student)
		self.assertEqual(res["status"], "split")


class TestEasebuzzSettlement(GatewayTestCase):
	def checkout(self, names=None, user=None):
		frappe.set_user(user or self.student_user)
		res = sp.create_bulk_demand_payment_order(json.dumps(names or [self.d_ez]))
		frappe.set_user("Administrator")
		return res["txnid"]

	def test_success_records_payment_once(self):
		txn = self.checkout()
		self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid="EZOK1"))
		self.assertEqual(frappe.local.response.get("type"), "redirect")
		self.assertIn(f"/student-portal/fees?payment_ref={txn}", frappe.local.response.get("location"))
		self.assertEqual(self.ir_status(txn), "Completed")
		fps = frappe.get_all(
			"Fee Payment", filters={"reference_number": "EZOK1", "docstatus": 1},
			fields=["name", "amount", "payment_gateway", "payment_mode", "owner"],
		)
		self.assertEqual(len(fps), 1)
		self.assertEqual(fps[0].payment_gateway, "Easebuzz")
		self.assertEqual(fps[0].payment_mode, "Online Payment")
		self.assertEqual(flt(fps[0].amount), 2500)
		self.assertEqual(fps[0].owner, self.student_user)
		self.assertEqual(frappe.db.get_value("Fee Demand", self.d_ez, "status"), "Paid")

		# Webhook for the same payment, then the return again: still one payment
		self.assertEqual(self.as_guest_callback(ez.webhook, signed(txn, 2500, easepayid="EZOK1")), "ok")
		self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid="EZOK1"))
		self.assertEqual(frappe.db.count("Fee Payment", {"reference_number": "EZOK1", "docstatus": 1}), 1)

	def test_bad_hash_records_nothing(self):
		txn = self.checkout()
		params = signed(txn, 2500)
		params["hash"] = "0" * 128
		self.as_guest_callback(ez.complete, params)
		self.assertEqual(self.ir_status(txn), "Queued")
		self.assertEqual(self.as_guest_callback(ez.webhook, params), "invalid hash")
		self.assertEqual(self.outstanding(self.d_ez), 2500)

	def test_amount_mismatch_is_rejected(self):
		txn = self.checkout()
		self.as_guest_callback(ez.complete, signed(txn, 1, easepayid="EZLOW"))
		self.assertEqual(self.ir_status(txn), "Failed")
		self.assertFalse(frappe.db.exists("Fee Payment", {"reference_number": "EZLOW"}))

	def test_callback_for_another_txnid_is_ignored(self):
		txn = self.checkout()
		params = signed("SOMEOTHERTXN", 2500)
		self.assertEqual(self.as_guest_callback(ez.webhook, params), "ignored")
		self.assertEqual(self.ir_status(txn), "Queued")

	def test_cancel_then_late_success(self):
		txn = self.checkout()
		self.as_guest_callback(ez.complete, signed(txn, 2500, status="userCancelled", easepayid=""))
		self.assertEqual(self.ir_status(txn), "Cancelled")
		self.assertEqual(self.outstanding(self.d_ez), 2500)
		self.as_guest_callback(ez.webhook, signed(txn, 2500, status="failure", easepayid=""))
		self.assertEqual(self.ir_status(txn), "Cancelled")
		self.as_guest_callback(ez.webhook, signed(txn, 2500, easepayid="EZLATE"))
		self.assertEqual(self.ir_status(txn), "Completed")
		self.assertEqual(frappe.db.get_value("Fee Demand", self.d_ez, "status"), "Paid")

	def test_failure_keeps_demand_payable(self):
		txn = self.checkout()
		self.as_guest_callback(ez.complete, signed(txn, 2500, status="failure", easepayid="EZFAIL"))
		self.assertEqual(self.ir_status(txn), "Failed")
		self.assertEqual(self.outstanding(self.d_ez), 2500)

	def test_pending_status_leaves_checkout_open(self):
		txn = self.checkout()
		self.as_guest_callback(ez.webhook, signed(txn, 2500, status="pending", easepayid=""))
		self.assertEqual(self.ir_status(txn), "Queued")

	def test_demand_settled_elsewhere_flags_excess(self):
		txn = self.checkout()
		fd = frappe.get_doc("Fee Demand", self.d_ez)
		fd.update_payment_status(paid_delta=1000)  # partly paid at the counter meanwhile
		self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid="EZPART"))
		self.assertEqual(flt(frappe.db.get_value("Fee Payment", {"reference_number": "EZPART"}, "amount")), 1500)
		self.assertIn("could not be allocated", frappe.db.get_value("Integration Request", txn, "error") or "")

	def test_parent_payment_is_attributed_to_parent(self):
		frappe.set_user(self.parent_user)
		txn = sp.parent_create_bulk_demand_payment_order(json.dumps([self.d_ez]), self.student)["txnid"]
		self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid="EZPAR"))
		self.assertIn(f"/parent-portal/fees?ward={self.student}", frappe.local.response.get("location"))
		self.assertEqual(frappe.db.get_value("Fee Payment", {"reference_number": "EZPAR"}, "owner"), self.parent_user)


class TestResultAndReconcile(GatewayTestCase):
	def test_result_visible_to_payer_only(self):
		frappe.set_user(self.student_user)
		txn = sp.create_demand_payment_order(self.d_ez)["txnid"]
		self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid="EZRES"))
		frappe.set_user(self.student_user)
		self.assertEqual(ez.get_payment_result(txn)["status"], "success")
		frappe.set_user(self.other_user)
		self.assertRaises(frappe.PermissionError, ez.get_payment_result, txn)

	def test_result_reconciles_queued_checkout(self):
		frappe.set_user(self.student_user)
		txn = sp.create_demand_payment_order(self.d_ez)["txnid"]
		txn_row = {"txnid": txn, "status": "success", "amount": "2500.00", "easepayid": "EZRET"}
		with patch.object(ezs.EasebuzzSettings, "retrieve_transaction", lambda self, t: {"status": True, "msg": [txn_row]}):
			self.assertEqual(ez.get_payment_result(txn)["status"], "success")
		self.assertEqual(frappe.db.get_value("Fee Demand", self.d_ez, "status"), "Paid")

	def test_scheduler_settles_and_expires(self):
		frappe.set_user(self.student_user)
		paid = sp.create_demand_payment_order(self.d_ez)["txnid"]
		abandoned = sp.create_demand_payment_order(self.d_ez)["txnid"]
		frappe.set_user("Administrator")
		frappe.db.set_value("Integration Request", paid, "creation", frappe.utils.add_to_date(None, minutes=-30), update_modified=False)
		frappe.db.set_value("Integration Request", abandoned, "creation", frappe.utils.add_to_date(None, days=-3), update_modified=False)

		def retrieve(self, t):
			if t == paid:
				return {"status": True, "msg": [{"txnid": t, "status": "success", "amount": "2500.00", "easepayid": "EZSCH"}]}
			return {"status": False, "msg": "Transaction not found"}

		with patch.object(ezs.EasebuzzSettings, "retrieve_transaction", retrieve):
			ez.reconcile_pending()
		self.assertEqual(self.ir_status(paid), "Completed")
		self.assertEqual(self.ir_status(abandoned), "Cancelled")


class TestReviewRegressions(GatewayTestCase):
	"""Bugs found in review; each test pins the fix."""

	def test_return_sends_no_session_cookie(self):
		"""The Guest callback must not answer with Set-Cookie sid=Guest (would log the payer out)."""
		from frappe.auth import CookieManager

		frappe.set_user(self.student_user)
		txn = sp.create_demand_payment_order(self.d_ez)["txnid"]
		frappe.set_user("Guest")
		frappe.local.response = frappe._dict()
		frappe.local.cookie_manager = CookieManager()
		frappe.local.cookie_manager.set_cookie("sid", "Guest")
		frappe.local.cookie_manager.delete_cookie("user_id")
		ez.complete(**signed(txn, 2500, easepayid="EZCOOKIE"))
		self.assertEqual(frappe.local.cookie_manager.cookies, {})
		self.assertEqual(list(frappe.local.cookie_manager.to_delete), [])
		frappe.set_user("Administrator")

	def test_missing_phone_leaves_no_in_flight_status(self):
		inv = frappe.get_doc({
			"doctype": "Fee Invoice", "student": self.student, "invoice_date": today(), "due_date": add_days(today(), 10),
			"fee_components": [{"fee_component": self.comp_ez, "amount": 900, "total_amount": 900}],
		})
		inv.flags.ignore_links = inv.flags.ignore_mandatory = True
		inv.insert(ignore_permissions=True)
		before = frappe.db.get_value("Fee Invoice", inv.name, "payment_status")
		frappe.db.set_value("Student Master", self.student, {"phone": "", "alternate_phone": ""})
		frappe.set_user(self.student_user)
		self.assertRaises(frappe.ValidationError, sp.create_payment_order, inv.name)
		self.assertEqual(frappe.db.get_value("Fee Invoice", inv.name, "payment_status"), before)

	def test_checkout_failure_reverts_initiated_status(self):
		reg = frappe.get_doc({
			"doctype": "Re Exam Registration", "student": self.student, "re_exam_fee": 700,
			"status": "Registered", "payment_status": "Payment Initiated",
		})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.db_insert()

		def boom(*a, **k):
			raise frappe.ValidationError("Could not reach Easebuzz")

		with patch.object(ez, "start_checkout", boom):
			self.assertRaises(
				frappe.ValidationError, sp._easebuzz_checkout, "re_exam", self.student, 700,
				{"registration": reg.name}, "x", "/student-portal/re-exam",
				revert=lambda: sp._revert_registration_initiated("Re Exam Registration", reg.name),
			)
		self.assertEqual(frappe.db.get_value("Re Exam Registration", reg.name, "payment_status"), "Pending")

	def test_expired_checkout_does_not_revive_cancelled_transcript(self):
		req = frappe.get_doc({
			"doctype": "Transcript Request", "student": self.student, "transcript_type": "Interim Transcript",
			"num_copies": 1, "requested_on": today(), "payment_required": 1, "fee_amount": 300,
			"payment_status": "Payment Initiated", "status": "Payment Pending",
		})
		req.flags.ignore_links = req.flags.ignore_mandatory = req.flags.ignore_validate = True
		req.db_insert()
		frappe.set_user(self.student_user)
		txn = ez.start_checkout("transcript", self.student, 300, {"request_name": req.name}, "T", "/student-portal/transcript-request")["txnid"]
		frappe.db.set_value("Transcript Request", req.name, "status", "Cancelled")
		self.as_guest_callback(ez.webhook, signed(txn, 300, status="dropped", easepayid=""))
		self.assertEqual(frappe.db.get_value("Transcript Request", req.name, "status"), "Cancelled")
		# A late success for a cancelled request is flagged for refund, not applied
		self.as_guest_callback(ez.webhook, signed(txn, 300, easepayid="EZCANC"))
		self.assertEqual(frappe.db.get_value("Transcript Request", req.name, "status"), "Cancelled")
		self.assertIn("refund", frappe.db.get_value("Integration Request", txn, "error") or "")

	def test_duplicate_exam_payment_is_flagged(self):
		reg = frappe.get_doc({
			"doctype": "Re Exam Registration", "student": self.student, "re_exam_fee": 700,
			"status": "Registered", "payment_status": "Paid", "payment_reference": "EZFIRST",
		})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.db_insert()
		frappe.set_user(self.student_user)
		txn = ez.start_checkout("re_exam", self.student, 700, {"registration": reg.name}, "R", "/student-portal/re-exam")["txnid"]
		self.as_guest_callback(ez.complete, signed(txn, 700, easepayid="EZSECOND"))
		self.assertIn("duplicate", frappe.db.get_value("Integration Request", txn, "error") or "")
		self.assertEqual(frappe.db.get_value("Re Exam Registration", reg.name, "payment_reference"), "EZFIRST")

	def test_admin_view_does_not_switch_user(self):
		frappe.set_user(self.student_user)
		txn = sp.create_demand_payment_order(self.d_ez)["txnid"]
		frappe.set_user("Administrator")
		with patch.object(ez, "_reconcile", side_effect=AssertionError("must not reconcile as admin")):
			self.assertEqual(ez.get_payment_result(txn)["status"], "pending")
		self.assertEqual(frappe.session.user, "Administrator")

	def test_settled_now_flag(self):
		frappe.set_user(self.student_user)
		txn = sp.create_demand_payment_order(self.d_ez)["txnid"]
		row = {"txnid": txn, "status": "success", "amount": "2500.00", "easepayid": "EZNOW"}
		with patch.object(ezs.EasebuzzSettings, "retrieve_transaction", lambda self, t: {"status": True, "msg": [row]}):
			res = ez.get_payment_result(txn)
		self.assertTrue(res["settled_now"])
		self.assertEqual(frappe.session.user, self.student_user)

	def test_as_user_restores_session(self):
		frappe.set_user(self.student_user)
		frappe.local.session.data.csrf_token = "keep-me"
		with ez._as_user(self.parent_user):
			self.assertEqual(frappe.session.user, self.parent_user)
		self.assertEqual(frappe.session.user, self.student_user)
		self.assertEqual(frappe.local.session.data.csrf_token, "keep-me")


class TestOtherFlows(GatewayTestCase):
	def settle(self, txn, amount, pid):
		self.as_guest_callback(ez.complete, signed(txn, amount, easepayid=pid))
		return self.ir_status(txn)

	def test_re_exam_flow(self):
		reg = frappe.get_doc({
			"doctype": "Re Exam Registration", "student": self.student, "re_exam_fee": 700,
			"status": "Registered", "payment_status": "Payment Initiated",
		})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.db_insert()
		frappe.set_user(self.student_user)
		txn = ez.start_checkout("re_exam", self.student, 700, {"registration": reg.name}, "Re-exam", "/student-portal/re-exam")["txnid"]
		self.assertEqual(self.settle(txn, 700, "EZREX"), "Completed")
		self.assertEqual(frappe.db.get_value("Re Exam Registration", reg.name, "payment_status"), "Paid")
		self.assertEqual(frappe.db.get_value("Re Exam Payment Log", {"razorpay_payment_id": "EZREX"}, "payment_gateway"), "Easebuzz")
		self.assertIn("/student-portal/re-exam?payment_ref=", frappe.local.response.get("location"))

	def test_improvement_exam_failure(self):
		reg = frappe.get_doc({
			"doctype": "Improvement Exam Registration", "student": self.student, "improvement_fee": 400,
			"status": "Registered", "payment_status": "Payment Initiated",
		})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.db_insert()
		frappe.set_user(self.student_user)
		txn = ez.start_checkout("improvement_exam", self.student, 400, {"registration": reg.name}, "Imp", "/student-portal/results")["txnid"]
		self.as_guest_callback(ez.complete, signed(txn, 400, status="failure", easepayid=""))
		self.assertEqual(frappe.db.get_value("Improvement Exam Registration", reg.name, "payment_status"), "Payment Failed")

	def test_transcript_flow_and_helpdesk_guard(self):
		from slcm.api import transcript_request as tr

		frappe.db.set_single_value("Transcript Fee Settings", "payment_gateway", "Easebuzz")
		req = frappe.get_doc({
			"doctype": "Transcript Request", "student": self.student, "transcript_type": "Interim Transcript",
			"num_copies": 1, "requested_on": today(), "payment_required": 1, "fee_amount": 300,
			"payment_status": "Pending", "status": "Payment Pending",
		})
		req.flags.ignore_links = req.flags.ignore_mandatory = req.flags.ignore_validate = True
		req.db_insert()
		frappe.set_user(self.student_user)
		self.assertRaises(frappe.ValidationError, tr.initiate_payment, req.name)  # Helpdesk panel
		txn = tr.initiate_payment(req.name, gateway_aware=1)["txnid"]
		self.assertEqual(self.settle(txn, 300, "EZTRN"), "Completed")
		row = frappe.db.get_value("Transcript Request", req.name, ["payment_status", "payment_reference"], as_dict=True)
		self.assertEqual((row.payment_status, row.payment_reference), ("Paid", "EZTRN"))

	def _pending_transcript(self, copies=1):
		req = frappe.get_doc({
			"doctype": "Transcript Request", "student": self.student, "transcript_type": "Interim Transcript",
			"num_copies": copies, "requested_on": today(), "payment_required": 1, "fee_amount": 300 * copies,
			"payment_status": "Pending", "status": "Payment Pending", "urgency": "Normal",
		})
		req.flags.ignore_links = req.flags.ignore_mandatory = req.flags.ignore_validate = True
		req.db_insert()
		return req

	def test_helpdesk_transcript_returns_to_support_form(self):
		from slcm.api import transcript_request as tr

		frappe.db.set_single_value("Transcript Fee Settings", "payment_gateway", "Easebuzz")
		req = self._pending_transcript()
		frappe.set_user(self.student_user)
		txn = tr.initiate_payment(req.name, gateway_aware=1, return_path="/student-portal/support?new=1")["txnid"]
		self.as_guest_callback(ez.complete, signed(txn, 300, status="userCancelled", easepayid=""))
		self.assertIn("/student-portal/support?new=1&payment_ref=", frappe.local.response.get("location"))
		frappe.set_user(self.student_user)
		back = tr.get_gateway_return_request(txn)
		self.assertEqual((back.name, back.payment_status), (req.name, "Payment Cancelled"))

		txn = tr.initiate_payment(req.name, gateway_aware=1, return_path="/student-portal/support?new=1")["txnid"]
		self.assertEqual(self.settle(txn, 300, "EZHDK"), "Completed")
		frappe.set_user(self.student_user)
		back = tr.get_gateway_return_request(txn)
		self.assertEqual((back.name, back.payment_status, back.payment_reference), (req.name, "Paid", "EZHDK"))

	def test_transcript_return_path_is_allowlisted(self):
		from slcm.api import transcript_request as tr

		frappe.db.set_single_value("Transcript Fee Settings", "payment_gateway", "Easebuzz")
		req = self._pending_transcript()
		frappe.set_user(self.student_user)
		txn = tr.initiate_payment(req.name, gateway_aware=1, return_path="https://evil.example/x")["txnid"]
		self.as_guest_callback(ez.complete, signed(txn, 300, status="failure", easepayid=""))
		self.assertIn("/student-portal/transcript-request?payment_ref=", frappe.local.response.get("location"))

	def test_return_request_is_payer_only(self):
		from slcm.api import transcript_request as tr

		frappe.db.set_single_value("Transcript Fee Settings", "payment_gateway", "Easebuzz")
		req = self._pending_transcript()
		frappe.set_user(self.student_user)
		txn = tr.initiate_payment(req.name, gateway_aware=1)["txnid"]
		frappe.db.set_value("Integration Request", txn, "data", frappe.as_json({
			**frappe.parse_json(frappe.db.get_value("Integration Request", txn, "data")), "user": "someone@else.test",
		}))
		self.assertRaises(frappe.PermissionError, tr.get_gateway_return_request, txn)
		self.assertRaises(frappe.PermissionError, tr.get_gateway_return_request, "not-a-txn")

	def test_helpdesk_retry_reuses_unpaid_request(self):
		from slcm.api import transcript_request as tr

		frappe.db.set_single_value("Transcript Fee Settings", {"allow_interim": 1, "enable_payment": 1})
		req = self._pending_transcript()
		frappe.set_user(self.student_user)
		self.assertRaises(frappe.ValidationError, tr.create_request, "Interim Transcript", 1, "Visa")
		again = tr.create_request("Interim Transcript", 1, "Visa", "Hard Copy (Physical)", reuse_unpaid=1)
		self.assertEqual(again["name"], req.name)
		self.assertEqual(frappe.db.get_value("Transcript Request", req.name, "purpose"), "Visa")

	def test_helpdesk_retry_with_other_copies_cancels_old_attempt(self):
		from slcm.api import transcript_request as tr

		frappe.db.set_single_value("Transcript Fee Settings", {"allow_interim": 1, "enable_payment": 1})
		req = self._pending_transcript()
		frappe.set_user(self.student_user)
		fresh = tr.create_request("Interim Transcript", 2, "Visa", reuse_unpaid=1)
		self.assertNotEqual(fresh["name"], req.name)
		self.assertEqual(frappe.db.get_value("Transcript Request", req.name, "status"), "Cancelled")
		self.assertEqual(frappe.db.get_value("Transcript Request", fresh["name"], "num_copies"), 2)

	def test_invoice_with_mixed_components_is_refused(self):
		inv = frappe.get_doc({
			"doctype": "Fee Invoice", "student": self.student, "invoice_date": today(), "due_date": add_days(today(), 10),
			"fee_components": [
				{"fee_component": self.comp_rzp, "amount": 100, "total_amount": 100},
				{"fee_component": self.comp_ez, "amount": 100, "total_amount": 100},
			],
		})
		inv.flags.ignore_links = inv.flags.ignore_mandatory = True
		inv.insert(ignore_permissions=True)
		self.assertRaises(frappe.ValidationError, gw.for_invoice, inv.name)

	def test_invoice_flow(self):
		inv = frappe.get_doc({
			"doctype": "Fee Invoice", "student": self.student, "invoice_date": today(), "due_date": add_days(today(), 10),
			"fee_components": [{"fee_component": self.comp_ez, "amount": 900, "total_amount": 900}],
		})
		inv.flags.ignore_links = inv.flags.ignore_mandatory = True
		inv.insert(ignore_permissions=True)
		frappe.set_user(self.student_user)
		res = sp.create_payment_order(inv.name)
		self.assertEqual(res["gateway"], "Easebuzz")
		amount = flt(frappe.db.get_value("Fee Invoice", inv.name, "outstanding_amount"))
		self.assertEqual(self.settle(res["txnid"], amount, "EZINV"), "Completed")
		self.assertLessEqual(flt(frappe.db.get_value("Fee Invoice", inv.name, "outstanding_amount")), 0)
		self.assertEqual(frappe.db.get_value("Fee Payment", {"reference_number": "EZINV"}, "payment_gateway"), "Easebuzz")


class TestPaymentRequestLedger(GatewayTestCase):
	"""Every online student payment gets one SLCM Payment Request (slcm.slcm.fee.payment_ledger)."""

	PR = "SLCM Payment Request"

	def pr(self, payment_id):
		name = frappe.db.get_value(self.PR, {"transaction_id": payment_id}, "name")
		return name and frappe.get_doc(self.PR, name)

	def razorpay_fee_payment(self, demand, payment_id, amount):
		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "payment_date": today(),
			"payment_mode": "Online Payment", "amount": amount, "reference_number": payment_id,
			"payment_gateway": "Razorpay",
			"payment_demands": [{"fee_demand": demand, "outstanding_amount": amount, "amount_allocated": amount}],
		})
		fp.insert(ignore_permissions=True)
		fp.submit()
		return fp

	def test_easebuzz_demand_payment_creates_one_request(self):
		frappe.set_user(self.student_user)
		txn = sp.create_bulk_demand_payment_order(json.dumps([self.d_ez]))["txnid"]
		frappe.set_user("Administrator")
		self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid="EZPR1"))
		pr = self.pr("EZPR1")
		self.assertTrue(pr)
		fp = frappe.db.get_value("Fee Payment", {"reference_number": "EZPR1", "docstatus": 1}, "name")
		self.assertEqual((pr.reference_doctype, pr.reference_name), ("Fee Payment", fp))
		self.assertEqual((pr.status, pr.docstatus, pr.payment_gateway, flt(pr.amount)), ("Paid", 1, "Easebuzz", 2500))
		self.assertEqual(pr.gateway_status, "success")  # Easebuzz's own status word
		self.assertEqual(pr.email_to, self.student_user)
		self.assertFalse(pr.razorpay_payment_id)
		self.assertFalse(pr.razorpay_order_id)  # admission webhooks look requests up by order id
		self.assertEqual(json.loads(pr.gateway_response)["order_id"], txn)

		self.as_guest_callback(ez.webhook, signed(txn, 2500, easepayid="EZPR1"))
		self.assertEqual(frappe.db.count(self.PR, {"transaction_id": "EZPR1"}), 1)

	def test_razorpay_payment_is_visible_to_settlement_sync(self):
		self.razorpay_fee_payment(self.d_rzp, "pay_PRTEST1", 1000)
		pr = self.pr("pay_PRTEST1")
		self.assertEqual((pr.payment_gateway, pr.razorpay_payment_id, pr.status), ("Razorpay", "pay_PRTEST1", "Paid"))
		self.assertEqual(pr.gateway_status, "captured")
		self.assertNotEqual(get_datetime(pr.paid_on).time(), datetime.time(0, 0))  # the capture time, not midnight
		# the query slcm.api.sync_settlements.run_sync matches settlements against
		self.assertIn(pr.name, frappe.db.sql_list(
			"""select name from `tabSLCM Payment Request`
			where status = 'Paid' and (settlement_status is null or settlement_status != 'processed')"""
		))
		from slcm.erpnext_bridge.sync import settlement_receipt
		self.assertEqual(settlement_receipt(pr)[0], "Fee Payment")

	def test_pay_all_with_re_exam_is_one_request_for_the_full_amount(self):
		reg = frappe.get_doc({
			"doctype": "Re Exam Registration", "student": self.student, "re_exam_fee": 700,
			"status": "Registered", "payment_status": "Payment Initiated",
		})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.db_insert()
		sp._mark_re_exams_paid([reg.name], self.student, "pay_PRMIX", "order_PRMIX")
		self.assertEqual(self.pr("pay_PRMIX").reference_doctype, "Re Exam Payment Log")
		fp = self.razorpay_fee_payment(self.d_rzp, "pay_PRMIX", 1000)
		pr = self.pr("pay_PRMIX")
		self.assertEqual((pr.reference_doctype, pr.reference_name, flt(pr.amount)), ("Fee Payment", fp.name, 1700))
		self.assertEqual(json.loads(pr.gateway_response)["order_id"], "order_PRMIX")
		self.assertEqual(frappe.db.count(self.PR, {"transaction_id": "pay_PRMIX"}), 1)

	def test_cancelled_fee_payment_cancels_the_request(self):
		fp = self.razorpay_fee_payment(self.d_rzp, "pay_PRCAN", 1000)
		fp.cancel()  # the request links back to it: must not block the cancel
		pr = self.pr("pay_PRCAN")
		# the money was captured (and may be settled): the request stays, pointing at the charge
		self.assertEqual((pr.status, pr.docstatus, pr.reference_doctype, pr.reference_name), ("Paid", 1, "Fee Demand", self.d_rzp))
		self.assertIn("was cancelled", json.loads(pr.gateway_response)["note"])
		self.assertFalse(frappe.db.exists(self.PR if hasattr(self, "PR") else "SLCM Payment Request",
			{"reference_doctype": "Fee Payment", "reference_name": fp.name, "docstatus": 1}))  # freed for deletion

	def test_partly_cancelled_pay_all_repoints_the_request(self):
		reg = frappe.get_doc({
			"doctype": "Re Exam Registration", "student": self.student, "re_exam_fee": 700,
			"status": "Registered", "payment_status": "Payment Initiated",
		})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.db_insert()
		sp._mark_re_exams_paid([reg.name], self.student, "pay_PRPART", "order_PRPART")
		fp = self.razorpay_fee_payment(self.d_rzp, "pay_PRPART", 1000)
		fp.cancel()
		pr = self.pr("pay_PRPART")
		self.assertEqual((pr.reference_doctype, flt(pr.amount), pr.docstatus), ("Re Exam Payment Log", 700, 1))

	def test_manual_online_payment_gets_no_request(self):
		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "payment_date": today(),
			"payment_mode": "Online Payment", "amount": 1000, "reference_number": "NEFT-PR-001",
			"payment_demands": [{"fee_demand": self.d_rzp, "outstanding_amount": 1000, "amount_allocated": 1000}],
		})
		fp.insert(ignore_permissions=True)
		fp.submit()
		self.assertFalse(self.pr("NEFT-PR-001"))

	def test_exam_and_transcript_payments(self):
		from slcm.api import transcript_request as tr

		reg = frappe.get_doc({
			"doctype": "Improvement Exam Registration", "student": self.student, "improvement_fee": 400,
			"status": "Registered", "payment_status": "Payment Initiated",
		})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.db_insert()
		frappe.set_user(self.student_user)
		txn = ez.start_checkout("improvement_exam", self.student, 400, {"registration": reg.name}, "Imp", "/student-portal/results")["txnid"]
		self.as_guest_callback(ez.complete, signed(txn, 400, easepayid="EZPRIMP"))
		pr = self.pr("EZPRIMP")
		self.assertEqual((pr.reference_doctype, flt(pr.amount), pr.payment_gateway), ("Improvement Exam Payment Log", 400, "Easebuzz"))

		frappe.db.set_single_value("Transcript Fee Settings", "payment_gateway", "Easebuzz")
		req = frappe.get_doc({
			"doctype": "Transcript Request", "student": self.student, "transcript_type": "Interim Transcript",
			"num_copies": 1, "requested_on": today(), "payment_required": 1, "fee_amount": 300,
			"payment_status": "Pending", "status": "Payment Pending",
		})
		req.flags.ignore_links = req.flags.ignore_mandatory = req.flags.ignore_validate = True
		req.db_insert()
		frappe.set_user(self.student_user)
		txn = tr.initiate_payment(req.name, gateway_aware=1)["txnid"]
		self.as_guest_callback(ez.complete, signed(txn, 300, easepayid="EZPRTRN"))
		pr = self.pr("EZPRTRN")
		self.assertEqual((pr.reference_doctype, pr.reference_name, flt(pr.amount)), ("Transcript Request", req.name, 300))

	def test_sweep_recreates_a_missing_request_and_is_idempotent(self):
		from slcm.slcm.fee import payment_ledger

		self.razorpay_fee_payment(self.d_rzp, "pay_PRSWEEP", 1000)
		frappe.db.delete(self.PR, {"transaction_id": "pay_PRSWEEP"})
		payment_ledger.sync_recent()
		first = self.pr("pay_PRSWEEP")
		self.assertTrue(first)
		modified = first.modified
		payment_ledger.sync_recent()
		self.assertEqual(frappe.db.count(self.PR, {"transaction_id": "pay_PRSWEEP"}), 1)
		self.assertEqual(frappe.db.get_value(self.PR, first.name, "modified"), modified)

	def test_admission_request_with_same_id_is_left_alone(self):
		from slcm.slcm.fee import payment_ledger

		pr = frappe.get_doc({
			"doctype": self.PR, "reference_doctype": "Applicant", "reference_name": "APPL-TEST",
			"amount": 500, "transaction_id": "pay_PRADM", "status": "Paid",
		})
		pr.flags.ignore_links = True
		pr.insert(ignore_permissions=True)
		payment_ledger.sync("pay_PRADM")
		self.assertEqual(frappe.db.get_value(self.PR, pr.name, ["reference_doctype", "amount"]), ("Applicant", 500))

	def test_ledger_failure_never_breaks_the_payment(self):
		from slcm.slcm.fee import payment_ledger

		with patch.object(payment_ledger, "_records", side_effect=RuntimeError("boom")):
			fp = self.razorpay_fee_payment(self.d_rzp, "pay_PRFAIL", 1000)
		self.assertEqual(frappe.db.get_value("Fee Payment", fp.name, "docstatus"), 1)
		self.assertFalse(self.pr("pay_PRFAIL"))


class TestFailedPaymentRequests(GatewayTestCase):
	"""Failed attempts get a Failed SLCM Payment Request carrying the gateway's reason."""

	PR = "SLCM Payment Request"

	def pr(self, **filters):
		name = frappe.db.get_value(self.PR, filters, "name")
		return name and frappe.get_doc(self.PR, name)

	def test_razorpay_demand_failure_records_reason(self):
		frappe.set_user(self.student_user)
		sp.mark_demand_payment_failed(
			json.dumps([self.d_rzp]), payment_id="pay_FAIL1", error_code="BAD_REQUEST_ERROR",
			error_description="Your card was declined by the bank",
		)
		frappe.set_user("Administrator")
		pr = self.pr(transaction_id="pay_FAIL1")
		self.assertEqual((pr.status, pr.docstatus, pr.gateway_status, pr.payment_gateway), ("Failed", 1, "failed", "Razorpay"))
		self.assertEqual((pr.reference_doctype, pr.reference_name, flt(pr.amount)), ("Fee Demand", self.d_rzp, 1000))
		self.assertIn("Your card was declined by the bank", pr.failure_message)
		self.assertFalse(pr.razorpay_order_id)

	def test_easebuzz_failure_records_reason_and_status(self):
		frappe.set_user(self.student_user)
		txn = sp.create_bulk_demand_payment_order(json.dumps([self.d_ez]))["txnid"]
		frappe.set_user("Administrator")
		self.as_guest_callback(ez.complete, signed(txn, 2500, status="failure", easepayid="EZFAIL1", error_Message="Insufficient funds"))
		pr = self.pr(transaction_id="EZFAIL1")
		self.assertEqual((pr.status, pr.gateway_status, pr.payment_gateway), ("Failed", "failure", "Easebuzz"))
		self.assertEqual((pr.reference_doctype, pr.reference_name, flt(pr.amount)), ("Fee Demand", self.d_ez, 2500))
		self.assertEqual(pr.failure_message, "Insufficient funds")
		self.assertEqual(json.loads(pr.gateway_response)["order_id"], txn)

	def test_easebuzz_user_cancel_is_not_a_failure(self):
		frappe.set_user(self.student_user)
		txn = sp.create_bulk_demand_payment_order(json.dumps([self.d_ez]))["txnid"]
		frappe.set_user("Administrator")
		self.as_guest_callback(ez.complete, signed(txn, 2500, status="userCancelled", easepayid="EZCAN1"))
		self.assertFalse(self.pr(transaction_id="EZCAN1"))

	def test_failure_never_downgrades_a_paid_request(self):
		from slcm.slcm.fee import payment_ledger

		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "payment_date": today(),
			"payment_mode": "Online Payment", "amount": 1000, "reference_number": "pay_FAILPAID",
			"payment_gateway": "Razorpay",
			"payment_demands": [{"fee_demand": self.d_rzp, "outstanding_amount": 1000, "amount_allocated": 1000}],
		})
		fp.insert(ignore_permissions=True)
		fp.submit()
		payment_ledger.record_failure("Razorpay", "pay_FAILPAID", "Fee Demand", self.d_rzp, 1000, self.student, "late failure")
		pr = self.pr(transaction_id="pay_FAILPAID")
		self.assertEqual((pr.status, pr.failure_message), ("Paid", None))

	def test_late_capture_turns_failed_request_paid(self):
		from slcm.slcm.fee import payment_ledger

		payment_ledger.record_failure("Razorpay", "pay_LATE", "Fee Demand", self.d_rzp, 1000, self.student, "timeout")
		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "payment_date": today(),
			"payment_mode": "Online Payment", "amount": 1000, "reference_number": "pay_LATE",
			"payment_gateway": "Razorpay",
			"payment_demands": [{"fee_demand": self.d_rzp, "outstanding_amount": 1000, "amount_allocated": 1000}],
		})
		fp.insert(ignore_permissions=True)
		fp.submit()
		self.assertEqual(frappe.db.count(self.PR, {"transaction_id": "pay_LATE"}), 1)
		pr = self.pr(transaction_id="pay_LATE")
		self.assertEqual((pr.status, pr.gateway_status, pr.reference_doctype, pr.failure_message), ("Paid", "captured", "Fee Payment", None))

	def test_repeated_failure_events_keep_one_request(self):
		frappe.set_user(self.student_user)
		for _ in range(2):
			sp.mark_demand_payment_failed(json.dumps([self.d_rzp]), payment_id="pay_FAILTWICE", error_description="Declined")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count(self.PR, {"transaction_id": "pay_FAILTWICE"}), 1)

	def test_razorpay_transcript_failure(self):
		from slcm.api import transcript_request as tr

		req = frappe.get_doc({
			"doctype": "Transcript Request", "student": self.student, "transcript_type": "Interim Transcript",
			"num_copies": 1, "requested_on": today(), "payment_required": 1, "fee_amount": 300,
			"payment_status": "Payment Initiated", "status": "Payment Pending", "razorpay_order_id": "order_TRFAIL",
		})
		req.flags.ignore_links = req.flags.ignore_mandatory = req.flags.ignore_validate = True
		req.db_insert()
		frappe.set_user(self.student_user)
		tr.record_payment_failure(req.name, error_description="UPI app timed out", error_code="GATEWAY_ERROR", payment_id="pay_TRFAIL")
		# Helpdesk panel sends no payment id: one Failed request per transcript, refreshed
		tr.record_payment_failure(req.name, error_description="Card declined")
		tr.record_payment_failure(req.name, error_description="Card declined again")
		frappe.set_user("Administrator")
		pr = self.pr(transaction_id="pay_TRFAIL")
		self.assertEqual((pr.reference_name, flt(pr.amount), pr.failure_message), (req.name, 300, "UPI app timed out"))
		self.assertEqual(json.loads(pr.gateway_response)["order_id"], "order_TRFAIL")
		no_id = frappe.get_all(self.PR, filters={"reference_name": req.name, "transaction_id": ("is", "not set")}, pluck="failure_message")
		self.assertEqual(no_id, ["Card declined again"])

	def test_backfill_records_old_failures_once(self):
		from slcm.slcm.doctype.student_master.student_master import _append_payment_log
		from slcm.slcm.fee import payment_ledger

		with patch.object(payment_ledger, "on_payment_log"):
			_append_payment_log(self.student, "Payment Failed", fee_demand=self.d_rzp, razorpay_payment_id="pay_OLDFAIL")
		frappe.db.delete(self.PR, {"transaction_id": "pay_OLDFAIL"})
		payment_ledger.sync_all()
		payment_ledger.sync_all()
		pr = self.pr(transaction_id="pay_OLDFAIL")
		self.assertEqual(frappe.db.count(self.PR, {"transaction_id": "pay_OLDFAIL"}), 1)
		self.assertEqual(pr.failure_message, "Payment failed at Razorpay (no reason given)")
		fetched = {"payment_method": "card", "raw_data": {"error_code": "GATEWAY_ERROR", "error_description": "Bank server down"}}
		with patch.object(sp, "_fetch_razorpay_payment_details", return_value=fetched):
			payment_ledger.enrich_razorpay_details()
		pr.reload()
		self.assertEqual((pr.gateway_error_code, pr.failure_message, pr.payment_method), ("GATEWAY_ERROR", "Bank server down", "card"))

	def test_failed_report_lists_fee_failures_once(self):
		from slcm.slcm.report.failed_payment_report.failed_payment_report import execute

		frappe.set_user(self.student_user)
		sp.mark_demand_payment_failed(json.dumps([self.d_rzp]), payment_id="pay_RPT1", error_description="Declined")
		frappe.set_user("Administrator")
		rows = [r for r in execute({"from_date": today(), "to_date": today()})[1] if "pay_RPT1" in str(r.get("razorpay_payment_id") or "")]
		self.assertEqual(len(rows), 1)


class TestCommonGatewayFields(GatewayTestCase):
	"""Gateway-neutral fields on SLCM Payment Request are filled the same way for Razorpay and Easebuzz."""

	PR = "SLCM Payment Request"

	def pr(self, **filters):
		name = frappe.db.get_value(self.PR, filters, "name")
		return name and frappe.get_doc(self.PR, name)

	def test_easebuzz_success_fills_common_fields(self):
		frappe.set_user(self.student_user)
		txn = sp.create_bulk_demand_payment_order(json.dumps([self.d_ez]))["txnid"]
		frappe.set_user("Administrator")
		self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid="EZCOMMON1", upi_va="student@okaxis"))
		pr = self.pr(gateway_payment_id="EZCOMMON1")
		self.assertEqual(
			(pr.gateway_order_id, pr.payment_method, pr.bank_reference, pr.payer_account, pr.gateway_error_code),
			(txn, "UPI", "BRN1", "student@okaxis", None),
		)

	def test_easebuzz_failure_fills_common_fields(self):
		frappe.set_user(self.student_user)
		txn = sp.create_bulk_demand_payment_order(json.dumps([self.d_ez]))["txnid"]
		frappe.set_user("Administrator")
		self.as_guest_callback(ez.complete, signed(
			txn, 2500, status="failure", easepayid="EZCOMMONF", mode="CC", cardnum="512345XXXXXX2346", error_Message="Declined",
		))
		pr = self.pr(gateway_payment_id="EZCOMMONF")
		self.assertEqual((pr.status, pr.gateway_order_id, pr.payment_method, pr.payer_account), ("Failed", txn, "CC", "512345XXXXXX2346"))

	def test_razorpay_paid_and_failed_fill_common_fields(self):
		from slcm.slcm.fee import payment_ledger

		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "payment_date": today(),
			"payment_mode": "Online Payment", "amount": 1000, "reference_number": "pay_COMMON1",
			"payment_gateway": "Razorpay",
			"payment_demands": [{"fee_demand": self.d_rzp, "outstanding_amount": 1000, "amount_allocated": 1000}],
		})
		fp.insert(ignore_permissions=True)
		fp.submit()
		pr = self.pr(transaction_id="pay_COMMON1")
		self.assertEqual((pr.gateway_payment_id, pr.razorpay_payment_id), ("pay_COMMON1", "pay_COMMON1"))

		fetched = {
			"payment_method": "upi", "transaction_id": "RRN123456", "account_number_or_upi_id": "payer@ybl",
			"raw_data": {"order_id": "order_COMMON1"},
		}
		with patch("slcm.api.student_payment._fetch_razorpay_payment_details", return_value=fetched) as fetch:
			payment_ledger.enrich_razorpay_details()
			pr.reload()
			self.assertEqual(
				(pr.gateway_order_id, pr.payment_method, pr.bank_reference, pr.payer_account),
				("order_COMMON1", "upi", "RRN123456", "payer@ybl"),
			)
			calls = fetch.call_count
			payment_ledger.enrich_razorpay_details()  # filled rows are not fetched again
			self.assertEqual(fetch.call_count, calls)
		payment_ledger.sync("pay_COMMON1")  # a later ledger sync keeps the fetched details
		pr.reload()
		self.assertEqual(pr.bank_reference, "RRN123456")

		frappe.set_user(self.student_user)
		sp.mark_demand_payment_failed(  # d_rzp is paid above; fail an attempt on the other demand
			json.dumps([self.d_ez]), payment_id="pay_COMMONF", error_code="BAD_REQUEST_ERROR", error_description="Declined",
		)
		frappe.set_user("Administrator")
		pr = self.pr(transaction_id="pay_COMMONF")
		self.assertEqual((pr.gateway_payment_id, pr.gateway_error_code), ("pay_COMMONF", "BAD_REQUEST_ERROR"))

	def test_admission_requests_get_common_ids(self):
		from slcm.slcm.fee import payment_ledger

		pr = frappe.get_doc({
			"doctype": self.PR, "reference_doctype": "Applicant", "reference_name": "APPL-COMMON",
			"amount": 500, "razorpay_order_id": "order_ADM1", "status": "Draft",
		})
		pr.flags.ignore_links = True
		pr.insert(ignore_permissions=True)
		self.assertEqual(pr.gateway_order_id, "order_ADM1")  # mirrored on save
		# the admission webhook updates with db_set, bypassing the controller
		frappe.db.set_value(self.PR, pr.name, {"razorpay_payment_id": "", "transaction_id": "pay_ADM1"})
		payment_ledger.fill_common_ids()
		self.assertEqual(frappe.db.get_value(self.PR, pr.name, "gateway_payment_id"), "pay_ADM1")
		self.assertEqual(payment_ledger.sync("pay_ADM1"), None)  # still an admission request, left alone


class TestCapturedAmounts(GatewayTestCase):
	"""The request shows what the gateway captured, including money no record could take."""

	PR = "SLCM Payment Request"

	def pr(self, **filters):
		name = frappe.db.get_value(self.PR, filters, "name")
		return name and frappe.get_doc(self.PR, name)

	def checkout(self, names):
		frappe.set_user(self.student_user)
		txn = sp.create_bulk_demand_payment_order(json.dumps(names))["txnid"]
		frappe.set_user("Administrator")
		return txn

	def test_easebuzz_excess_is_in_the_request_amount(self):
		txn = self.checkout([self.d_ez])
		frappe.db.set_value("Fee Demand", self.d_ez, "outstanding_amount", 2000)  # part paid elsewhere meanwhile
		self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid="EZEXCESS"))
		self.assertEqual(flt(frappe.db.get_value("Fee Payment", {"reference_number": "EZEXCESS"}, "amount")), 2000)
		pr = self.pr(transaction_id="EZEXCESS")
		self.assertEqual((flt(pr.amount), pr.reference_doctype), (2500, "Fee Payment"))
		self.assertEqual(json.loads(pr.gateway_response)["unallocated"], 500)

	def test_easebuzz_money_no_record_took_still_gets_a_request(self):
		txn = self.checkout([self.d_ez])
		frappe.db.set_value("Fee Demand", self.d_ez, {"status": "Paid", "outstanding_amount": 0})  # settled meanwhile
		self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid="EZUNAPPLIED"))
		self.assertFalse(frappe.db.exists("Fee Payment", {"reference_number": "EZUNAPPLIED"}))
		pr = self.pr(transaction_id="EZUNAPPLIED")
		self.assertEqual(
			(pr.status, pr.reference_doctype, pr.reference_name, flt(pr.amount), pr.gateway_order_id),
			("Paid", "Fee Demand", self.d_ez, 2500, txn),
		)
		self.assertTrue(frappe.db.exists("Comment", {"reference_doctype": self.PR, "reference_name": pr.name, "comment_type": "Comment"}))
		# the webhook for the same payment and a later sweep neither duplicate nor cancel it
		self.as_guest_callback(ez.webhook, signed(txn, 2500, easepayid="EZUNAPPLIED"))
		from slcm.slcm.fee import payment_ledger
		payment_ledger.sync("EZUNAPPLIED")
		self.assertEqual(frappe.db.count(self.PR, {"transaction_id": "EZUNAPPLIED", "docstatus": 1, "status": "Paid"}), 1)

	def test_easebuzz_payment_for_cancelled_transcript_gets_a_request(self):
		from slcm.api import transcript_request as tr

		frappe.db.set_single_value("Transcript Fee Settings", "payment_gateway", "Easebuzz")
		req = frappe.get_doc({
			"doctype": "Transcript Request", "student": self.student, "transcript_type": "Interim Transcript",
			"num_copies": 1, "requested_on": today(), "payment_required": 1, "fee_amount": 300,
			"payment_status": "Pending", "status": "Payment Pending",
		})
		req.flags.ignore_links = req.flags.ignore_mandatory = req.flags.ignore_validate = True
		req.db_insert()
		frappe.set_user(self.student_user)
		txn = tr.initiate_payment(req.name, gateway_aware=1)["txnid"]
		frappe.set_user("Administrator")
		frappe.db.set_value("Transcript Request", req.name, "status", "Cancelled")
		self.as_guest_callback(ez.complete, signed(txn, 300, easepayid="EZTRCANCEL"))
		pr = self.pr(transaction_id="EZTRCANCEL")
		self.assertEqual((pr.status, pr.reference_name, flt(pr.amount)), ("Paid", req.name, 300))
		self.assertIn("needs a refund", json.loads(pr.gateway_response)["note"])

	def test_failed_attempt_amount_comes_from_razorpay(self):
		from slcm.slcm.fee import payment_ledger

		frappe.set_user(self.student_user)
		sp.mark_demand_payment_failed(json.dumps([self.d_rzp]), payment_id="pay_AMTFAIL", error_description="Declined")
		frappe.set_user("Administrator")
		self.assertEqual(flt(self.pr(transaction_id="pay_AMTFAIL").amount), 1000)  # estimated from the outstanding
		fetched = {"payment_method": "card", "raw_data": {"amount": 120000, "order_id": "order_AMTFAIL"}}
		with patch.object(sp, "_fetch_razorpay_payment_details", return_value=fetched):
			payment_ledger.enrich_razorpay_details()
		self.assertEqual(flt(self.pr(transaction_id="pay_AMTFAIL").amount), 1200)
		payment_ledger.sync_failed_fee_attempt("pay_AMTFAIL")  # a later sweep keeps Razorpay's figure
		self.assertEqual(flt(self.pr(transaction_id="pay_AMTFAIL").amount), 1200)

	def test_paid_amount_mismatch_is_flagged_not_changed(self):
		from slcm.slcm.fee import payment_ledger

		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "payment_date": today(),
			"payment_mode": "Online Payment", "amount": 1000, "reference_number": "pay_AMTPAID",
			"payment_gateway": "Razorpay",
			"payment_demands": [{"fee_demand": self.d_rzp, "outstanding_amount": 1000, "amount_allocated": 1000}],
		})
		fp.insert(ignore_permissions=True)
		fp.submit()
		fetched = {"payment_method": "upi", "raw_data": {"amount": 150000, "order_id": "order_AMTPAID"}}
		with patch.object(sp, "_fetch_razorpay_payment_details", return_value=fetched), \
				patch.object(frappe, "log_error") as log_error:
			payment_ledger.enrich_razorpay_details(recheck=True)
		self.assertEqual(flt(self.pr(transaction_id="pay_AMTPAID").amount), 1000)
		titles = [c.args[1] if len(c.args) > 1 else c.kwargs.get("title") for c in log_error.call_args_list]
		self.assertIn("SLCM Payment Request amount differs from Razorpay", titles)


class TestPayerDetailsOnReceipt(GatewayTestCase):
	"""Bank Name / Account Number / Transaction Date reach Fee Payment, Fee Receipt and Fee Demand from the gateway."""

	PR = "SLCM Payment Request"

	def payer_fields(self, doctype, name):
		return frappe.db.get_value(doctype, name, ["bank_name", "account_number", "transaction_date", "ifsc_code"], as_dict=True)

	def razorpay_fee_payment(self, payment_id, **extra):
		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "payment_date": today(),
			"payment_mode": "Online Payment", "amount": 1000, "reference_number": payment_id,
			"payment_gateway": "Razorpay",
			"payment_demands": [{"fee_demand": self.d_rzp, "outstanding_amount": 1000, "amount_allocated": 1000}],
			**extra,
		})
		fp.insert(ignore_permissions=True)
		fp.submit()
		return fp

	def test_easebuzz_details_reach_receipt_and_demand(self):
		frappe.set_user(self.student_user)
		txn = sp.create_bulk_demand_payment_order(json.dumps([self.d_ez]))["txnid"]
		frappe.set_user("Administrator")
		self.as_guest_callback(ez.complete, signed(
			txn, 2500, easepayid="EZBANK1", mode="NB", bank_name="HDFC Bank", upi_va="",
		))
		fp = frappe.db.get_value("Fee Payment", {"reference_number": "EZBANK1"}, ["name", "receipt"], as_dict=True)
		self.assertTrue(fp.receipt)
		for doctype, name in (("Fee Payment", fp.name), ("Fee Receipt", fp.receipt), ("Fee Demand", self.d_ez)):
			row = self.payer_fields(doctype, name)
			self.assertEqual((row.bank_name, str(row.transaction_date), row.ifsc_code or None), ("HDFC Bank", today(), None), doctype)

		frappe.set_user(self.student_user)
		txn = sp.create_bulk_demand_payment_order(json.dumps([self.make_demand(self.comp_ez, 300)]))["txnid"]
		frappe.set_user("Administrator")
		self.as_guest_callback(ez.complete, signed(txn, 300, easepayid="EZBANK2", upi_va="payer@okhdfc"))
		receipt = frappe.db.get_value("Fee Payment", {"reference_number": "EZBANK2"}, "receipt")
		self.assertEqual(self.payer_fields("Fee Receipt", receipt).account_number, "payer@okhdfc")

	def test_razorpay_details_reach_receipt_after_lookup(self):
		from slcm.slcm.fee import payment_ledger

		fp = self.razorpay_fee_payment("pay_BANK1")
		pr = frappe.db.get_value(self.PR, {"transaction_id": "pay_BANK1"}, "name")
		self.assertFalse(self.payer_fields("Fee Receipt", fp.receipt).bank_name)  # not known until Razorpay is asked
		fetched = {"payment_method": "card", "transaction_id": "RRN9", "raw_data": {
			"order_id": "order_BANK1", "amount": 100000, "card": {"last4": "4242", "network": "Visa", "issuer": "UTIB"},
		}}
		with patch.object(sp, "_fetch_razorpay_payment_details", return_value=fetched), \
				patch.object(payment_ledger, "_razorpay_bank_name", lambda code: {"UTIB": "Axis Bank"}.get(code, code)):
			payment_ledger.enrich_one(pr)
		self.assertEqual(
			frappe.db.get_value(self.PR, pr, ["payer_bank", "payer_account"]), ("Axis Bank", "XXXX XXXX XXXX 4242 Visa"),
		)
		for doctype, name in (("Fee Payment", fp.name), ("Fee Receipt", fp.receipt), ("Fee Demand", self.d_rzp)):
			row = self.payer_fields(doctype, name)
			self.assertEqual((row.bank_name, row.account_number), ("Axis Bank", "XXXX XXXX XXXX 4242 Visa"), doctype)

	def test_accountant_entries_are_never_overwritten(self):
		from slcm.slcm.fee import payment_ledger

		fp = self.razorpay_fee_payment("pay_BANK2", bank_name="Typed by accountant")
		pr = frappe.db.get_value(self.PR, {"transaction_id": "pay_BANK2"}, "name")
		fetched = {"payment_method": "upi", "raw_data": {"vpa": "x@ybl", "bank": "SBIN", "amount": 100000}}
		with patch.object(sp, "_fetch_razorpay_payment_details", return_value=fetched), \
				patch.object(payment_ledger, "_razorpay_bank_name", lambda code: "State Bank of India"):
			payment_ledger.enrich_one(pr)
		self.assertEqual(self.payer_fields("Fee Receipt", fp.receipt).bank_name, "Typed by accountant")
		self.assertEqual(self.payer_fields("Fee Receipt", fp.receipt).account_number, "x@ybl")

	def test_bank_code_stored_as_payer_account_is_corrected(self):
		from slcm.slcm.fee import payment_ledger

		self.razorpay_fee_payment("pay_BANK3")
		pr = frappe.db.get_value(self.PR, {"transaction_id": "pay_BANK3"}, "name")
		frappe.db.set_value(self.PR, pr, {"payer_account": "SBIN", "payment_method": "netbanking"})  # old derivation
		fetched = {"payment_method": "netbanking", "raw_data": {"bank": "SBIN", "amount": 100000}}
		with patch.object(sp, "_fetch_razorpay_payment_details", return_value=fetched), \
				patch.object(payment_ledger, "_razorpay_bank_name", lambda code: "State Bank of India"):
			payment_ledger.enrich_razorpay_details(recheck=True)
		self.assertEqual(frappe.db.get_value(self.PR, pr, ["payer_account", "payer_bank"]), (None, "State Bank of India"))

	def test_queue_outage_never_reaches_the_payer(self):
		from slcm.slcm.fee import payment_ledger

		with patch.object(frappe, "enqueue", side_effect=RuntimeError("redis down")), patch.object(frappe, "log_error") as log:
			payment_ledger._enqueue_enrich("PR-X")
		self.assertTrue(log.called)


class TestReviewFindings(GatewayTestCase):
	"""Regressions for the independent review of the payment ledger."""

	PR = "SLCM Payment Request"

	def pr(self, **filters):
		name = frappe.db.get_value(self.PR, filters, "name")
		return name and frappe.get_doc(self.PR, name)

	def checkout(self, names):
		frappe.set_user(self.student_user)
		txn = sp.create_bulk_demand_payment_order(json.dumps(names))["txnid"]
		frappe.set_user("Administrator")
		return txn

	def test_refunded_exam_fee_keeps_the_request_paid(self):
		reg = frappe.get_doc({
			"doctype": "Re Exam Registration", "student": self.student, "re_exam_fee": 700,
			"status": "Registered", "payment_status": "Payment Initiated",
		})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.db_insert()
		sp._mark_re_exams_paid([reg.name], self.student, "pay_REFUND1", "order_REFUND1")
		log = frappe.db.get_value("Re Exam Payment Log", {"razorpay_payment_id": "pay_REFUND1"}, "name")
		frappe.db.set_value("Re Exam Payment Log", log, "payment_status", "Refunded")  # refund webhook path
		from slcm.slcm.fee import payment_ledger
		payment_ledger.sync("pay_REFUND1")
		pr = self.pr(transaction_id="pay_REFUND1")
		self.assertEqual(
			(pr.status, pr.docstatus, pr.gateway_status, pr.reference_doctype, pr.reference_name),
			("Paid", 1, "refunded", "Re Exam Registration", reg.name),
		)

	def test_late_easebuzz_success_after_failure_with_nothing_to_book(self):
		txn = self.checkout([self.d_ez])
		self.as_guest_callback(ez.complete, signed(txn, 2500, status="failure", easepayid="EZLATE1", error_Message="Timeout"))
		self.assertEqual(self.pr(transaction_id="EZLATE1").status, "Failed")
		frappe.db.set_value("Fee Demand", self.d_ez, {"status": "Paid", "outstanding_amount": 0})  # paid another way
		self.as_guest_callback(ez.webhook, signed(txn, 2500, easepayid="EZLATE1"))
		pr = self.pr(transaction_id="EZLATE1")
		self.assertEqual((pr.status, pr.failure_message, pr.gateway_status, flt(pr.amount)), ("Paid", None, "success", 2500))

	def test_failure_keyed_on_txnid_is_closed_by_the_capture(self):
		txn = self.checkout([self.d_ez])
		self.as_guest_callback(ez.complete, signed(txn, 2500, status="failure", easepayid=""))
		self.assertEqual(self.pr(transaction_id=txn).status, "Failed")
		self.as_guest_callback(ez.webhook, signed(txn, 2500, easepayid="EZREAL1"))
		self.assertEqual(self.pr(transaction_id="EZREAL1").status, "Paid")
		self.assertEqual(self.pr(transaction_id=txn).status, "Cancelled")

	def test_easebuzz_amount_mismatch_is_recorded_for_refund(self):
		txn = self.checkout([self.d_ez])
		self.as_guest_callback(ez.complete, signed(txn, 1, easepayid="EZMISMATCH"))
		pr = self.pr(transaction_id="EZMISMATCH")
		self.assertEqual((pr.status, flt(pr.amount), pr.reference_name), ("Paid", 1, self.d_ez))
		self.assertIn("mismatch", json.loads(pr.gateway_response)["note"])
		self.assertFalse(frappe.db.exists("Fee Payment", {"reference_number": "EZMISMATCH"}))

	def test_razorpay_duplicate_transcript_payment_is_recorded(self):
		from slcm.api import transcript_request as tr

		req = frappe.get_doc({
			"doctype": "Transcript Request", "student": self.student, "transcript_type": "Interim Transcript",
			"num_copies": 1, "requested_on": today(), "payment_required": 1, "fee_amount": 300,
			"payment_status": "Paid", "payment_reference": "pay_FIRST", "status": "Submitted",
		})
		req.flags.ignore_links = req.flags.ignore_mandatory = req.flags.ignore_validate = True
		req.db_insert()
		tr.mark_request_paid(req.name, self.student, "pay_SECOND", "order_SECOND")
		pr = self.pr(transaction_id="pay_SECOND")
		self.assertEqual((pr.status, pr.reference_name, flt(pr.amount), pr.razorpay_payment_id), ("Paid", req.name, 300, "pay_SECOND"))
		self.assertIn("duplicate", json.loads(pr.gateway_response)["note"])

	def test_admission_retry_moves_common_ids_and_drops_old_details(self):
		from slcm.slcm.fee import payment_ledger

		pr = frappe.get_doc({
			"doctype": self.PR, "reference_doctype": "Applicant", "reference_name": "APPL-RETRY", "amount": 500,
			"razorpay_order_id": "order_A1", "razorpay_payment_id": "pay_A1", "status": "Draft",
		})
		pr.flags.ignore_links = True
		pr.insert(ignore_permissions=True)
		frappe.db.set_value(self.PR, pr.name, {"payment_method": "card", "payer_bank": "Old Bank"})
		frappe.db.set_value(self.PR, pr.name, {"razorpay_order_id": "order_A2", "razorpay_payment_id": "pay_A2"})  # retry, db_set
		payment_ledger.fill_common_ids()
		row = frappe.db.get_value(self.PR, pr.name, ["gateway_order_id", "gateway_payment_id", "payment_method", "payer_bank"], as_dict=True)
		self.assertEqual(tuple(row.values()), ("order_A2", "pay_A2", None, None))

	def test_lookup_never_changes_an_admission_amount(self):
		from slcm.slcm.fee import payment_ledger

		pr = frappe.get_doc({
			"doctype": self.PR, "reference_doctype": "Applicant", "reference_name": "APPL-AMT", "amount": 500,
			"razorpay_payment_id": "pay_ADMAMT", "status": "Draft",
		})
		pr.flags.ignore_links = True
		pr.insert(ignore_permissions=True)
		frappe.db.set_value(self.PR, pr.name, "status", "Failed")
		fetched = {"payment_method": "upi", "raw_data": {"amount": 99900}}
		with patch.object(sp, "_fetch_razorpay_payment_details", return_value=fetched):
			payment_ledger.enrich_razorpay_details(recheck=True)
		self.assertEqual(flt(frappe.db.get_value(self.PR, pr.name, "amount")), 500)

	def test_browser_supplied_non_razorpay_id_is_ignored(self):
		from slcm.api import transcript_request as tr

		req = frappe.get_doc({
			"doctype": "Transcript Request", "student": self.student, "transcript_type": "Interim Transcript",
			"num_copies": 1, "requested_on": today(), "payment_required": 1, "fee_amount": 300,
			"payment_status": "Payment Initiated", "status": "Payment Pending",
		})
		req.flags.ignore_links = req.flags.ignore_mandatory = req.flags.ignore_validate = True
		req.db_insert()
		frappe.set_user(self.student_user)
		tr.record_payment_failure(req.name, error_description="x", payment_id="EZOTHERSTUDENT")
		frappe.set_user("Administrator")
		self.assertFalse(self.pr(transaction_id="EZOTHERSTUDENT"))
		self.assertTrue(self.pr(reference_name=req.name, status="Failed"))

	def test_easebuzz_invoice_failure_shows_in_failed_report(self):
		from slcm.slcm.report.failed_payment_report.failed_payment_report import execute

		inv = frappe.get_doc({
			"doctype": "Fee Invoice", "student": self.student, "invoice_date": today(), "due_date": add_days(today(), 10),
			"fee_components": [{"fee_component": self.comp_ez, "amount": 900, "total_amount": 900}],
		})
		inv.flags.ignore_links = inv.flags.ignore_mandatory = True
		inv.insert(ignore_permissions=True)
		frappe.set_user(self.student_user)
		res = sp.create_payment_order(inv.name)
		frappe.set_user("Administrator")
		amount = flt(frappe.db.get_value("Fee Invoice", inv.name, "outstanding_amount"))
		self.as_guest_callback(ez.complete, signed(res["txnid"], amount, status="failure", easepayid="EZINVFAIL"))
		rows = [r for r in execute({"from_date": today(), "to_date": today()})[1] if r.get("transaction_id") == "EZINVFAIL"]
		self.assertEqual(len(rows), 1)


class TestBridgeSettlementGuard(GatewayTestCase):
	def test_settlement_posts_only_when_booked_amount_matches(self):
		from slcm.erpnext_bridge.sync import _student_settlement_matches

		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "payment_date": today(),
			"payment_mode": "Online Payment", "amount": 1000, "reference_number": "pay_GUARD1",
			"payment_gateway": "Razorpay",
			"payment_demands": [{"fee_demand": self.d_rzp, "outstanding_amount": 1000, "amount_allocated": 1000}],
		})
		fp.insert(ignore_permissions=True)
		fp.submit()
		pr = frappe.get_doc("SLCM Payment Request", frappe.db.get_value("SLCM Payment Request", {"transaction_id": "pay_GUARD1"}))
		self.assertTrue(_student_settlement_matches(pr))
		pr.amount = 1700  # Pay All that also paid a ₹700 re-exam (not parked in clearing)
		with patch.object(frappe, "log_error") as log:
			self.assertFalse(_student_settlement_matches(pr))
		frappe.cache().delete_value(f"slcm_erp_settlement_mismatch:{pr.name}")
		self.assertTrue(log.called)


class TestBankCodeCleanup(GatewayTestCase):
	def test_bank_codes_from_an_earlier_run_are_replaced(self):
		from slcm.slcm.fee import payment_ledger

		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "payment_date": today(),
			"payment_mode": "Online Payment", "amount": 1000, "reference_number": "pay_CODE1",
			"payment_gateway": "Razorpay",
			"payment_demands": [{"fee_demand": self.d_rzp, "outstanding_amount": 1000, "amount_allocated": 1000}],
		})
		fp.insert(ignore_permissions=True)
		fp.submit()
		pr = frappe.db.get_value("SLCM Payment Request", {"transaction_id": "pay_CODE1"}, "name")
		frappe.db.set_value("SLCM Payment Request", pr, {"payment_method": "netbanking", "payer_bank": "ICIC"})
		frappe.db.set_value("Fee Receipt", fp.receipt, {"bank_name": "ICIC", "account_number": "ICIC"})
		fetched = {"payment_method": "netbanking", "raw_data": {"bank": "ICIC", "amount": 100000}}
		with patch.object(sp, "_fetch_razorpay_payment_details", return_value=fetched), \
				patch.object(payment_ledger, "_razorpay_bank_name", lambda code: {"ICIC": "ICICI Bank"}.get(code, code)):
			payment_ledger.enrich_razorpay_details(recheck=True)
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr, "payer_bank"), "ICICI Bank")
		self.assertEqual(
			frappe.db.get_value("Fee Receipt", fp.receipt, ["bank_name", "account_number"]), ("ICICI Bank", None),
		)

	def test_bank_name_lookup_uses_key_id_only(self):
		from slcm.slcm.fee import payment_ledger

		frappe.cache().delete_value("slcm_razorpay_bank_names")

		class Resp:
			status_code = 200

			@staticmethod
			def json():
				return {"netbanking": {"UTIB": "Axis Bank"}}

		with patch("requests.get", return_value=Resp) as get:
			self.assertEqual(payment_ledger._razorpay_bank_name("UTIB"), "Axis Bank")
			self.assertEqual(payment_ledger._razorpay_bank_name("ZZZZ"), "ZZZZ")
		self.assertEqual(get.call_args.kwargs["auth"][1], "")
		self.assertEqual(get.call_count, 1)  # cached
		frappe.cache().delete_value("slcm_razorpay_bank_names")


class TestEasebuzzPayouts(GatewayTestCase):
	"""Easebuzz payouts → settlement fields (slcm.slcm.fee.easebuzz_settlement) and the Payment Settlement Report."""

	def paid_request(self, easepayid):
		frappe.set_user(self.student_user)
		txn = sp.create_bulk_demand_payment_order(json.dumps([self.d_ez]))["txnid"]
		frappe.set_user("Administrator")
		self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid=easepayid))
		return txn, frappe.db.get_value("SLCM Payment Request", {"transaction_id": easepayid}, "name")

	def payout(self, easepayid, txnid, paid_out=True):
		return {
			"paid_out": paid_out, "payout_actual_date": "Nov-03-2026 10:33:29 AM", "payout_amount": 2455.12,
			"payout_id": "PAYOUT1", "bank_name": "Test Bank", "account_number": "123456789012",
			"bank_transaction_id": "UTR123", "service_charge_amount": 44.88, "peb_refunds": [],
			"peb_transactions": [{
				"peb_transaction_id": easepayid, "txnid": txnid, "amount": 2500, "peb_service_charge": 38.03,
				"peb_service_tax": 6.85, "peb_settlement_amount": 2455.12, "transaction_type": "UPI", "status": "settled",
			}],
		}

	def response(self, payouts, nxt=None):
		class Resp:
			@staticmethod
			def raise_for_status():
				pass

			@staticmethod
			def json():
				return {"next": nxt, "previous": None, "count": len(payouts), "data": payouts}

		return Resp

	def test_payout_settles_request_with_easebuzz_figures(self):
		from slcm.slcm.fee import easebuzz_settlement as es

		txn, pr = self.paid_request("EZSET1")
		with patch.object(es.requests, "post", return_value=self.response([self.payout("EZSET1", txn)])) as post:
			counts = es.sync_range(add_days(today(), -3), today())
		self.assertEqual(counts["settled"], 1)
		body = post.call_args.kwargs["json"]
		self.assertEqual(set(body), {"merchant_key", "hash", "payout_date"})
		start, end = body["payout_date"]["start_date"], body["payout_date"]["end_date"]
		self.assertEqual(body["hash"], ezs.sha512(f"{KEY}|{start}|{end}|{SALT}"))
		self.assertTrue(re.match(r"^\d{2}-\d{2}-\d{4}$", start))
		self.assertTrue(post.call_args.args[0].endswith("/settlements/v1/retrieve"))

		row = frappe.db.get_value("SLCM Payment Request", pr, [
			"settlement_status", "settlement_id", "settlement_utr", "settlement_date", "settlement_amount",
			"gateway_fees", "gateway_tax", "net_settled", "gateway_settlement_status", "settlement_response",
		], as_dict=True)
		self.assertEqual((row.settlement_status, row.settlement_id, row.settlement_utr), ("Settled", "PAYOUT1", "UTR123"))
		self.assertEqual((flt(row.settlement_amount), flt(row.gateway_fees), flt(row.gateway_tax), flt(row.net_settled)),
		                 (2500, 38.03, 6.85, 2455.12))
		self.assertEqual(row.gateway_settlement_status, "processed")
		self.assertEqual(get_datetime(row.settlement_date), datetime.datetime(2026, 11, 3, 10, 33, 29))
		self.assertNotIn("123456789012", row.settlement_response)  # bank account masked

		# re-running changes nothing
		with patch.object(es.requests, "post", return_value=self.response([self.payout("EZSET1", txn)])):
			self.assertEqual(es.sync_range(add_days(today(), -3), today())["unchanged"], 1)

	def test_scheduled_payout_is_processing_and_unknown_ids_are_skipped(self):
		from slcm.slcm.fee import easebuzz_settlement as es

		txn, pr = self.paid_request("EZSET2")
		payouts = [self.payout("EZSET2", txn, paid_out=False), self.payout("EZ_NOT_OURS", "NOTOURS")]
		counts = es.apply_payouts(payouts)
		self.assertEqual((counts["settled"], counts["not_found"]), (1, 1))
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr, "settlement_status"), "Processing")

	def test_rejected_request_raises_and_logs_without_secrets(self):
		from slcm.slcm.fee import easebuzz_settlement as es

		class Bad:
			@staticmethod
			def raise_for_status():
				pass

			@staticmethod
			def json():
				return {"status": False, "message": "Invalid hash"}

		with patch.object(es.requests, "post", return_value=Bad), patch.object(frappe, "log_error") as log:
			self.assertRaises(frappe.ValidationError, es.fetch_payouts, today(), today())
		self.assertNotIn(SALT, str(log.call_args))

	def test_settlement_report_lists_paid_requests_with_gateway_filter(self):
		from slcm.slcm.fee import easebuzz_settlement as es
		from slcm.slcm.report.payment_settlement_report import payment_settlement_report as rep

		txn, pr = self.paid_request("EZSET3")
		f = {"from_date": add_days(today(), -1), "to_date": today(), "payment_gateway": "Easebuzz"}
		_cols, data, _m, _c, summary = rep.execute(f)
		row = next(r for r in data if r.name == pr)
		self.assertEqual(row.settlement_status, rep.NOT_SETTLED)
		self.assertIn(pr, [r.name for r in rep.execute({**f, "settlement_status": rep.NOT_SETTLED})[1]])
		self.assertTrue(all(r.payment_gateway == "Easebuzz" for r in data))
		self.assertEqual(summary[0]["label"], "Collected")

		es.apply_payouts([self.payout("EZSET3", txn)])
		settled = rep.execute({**f, "settlement_status": "Settled"})[1]
		self.assertIn(pr, [r.name for r in settled])
		self.assertNotIn(pr, [r.name for r in rep.execute({**f, "settlement_status": rep.NOT_SETTLED})[1]])
		# a hostile filter value is a bound parameter, not SQL
		self.assertEqual(rep.execute({**f, "settlement_status": "x' or '1'='1"})[1], [])


class TestSettleRobustness(GatewayTestCase):
	"""Review fixes: retry rows from retrieve, unreachable Easebuzz at expiry, mismatch release, webhook errors."""

	def queued(self, days_old=0):
		frappe.set_user(self.student_user)
		txn = sp.create_demand_payment_order(self.d_ez)["txnid"]
		frappe.set_user("Administrator")
		age = frappe.utils.add_to_date(None, days=-days_old, minutes=-30)
		frappe.db.set_value("Integration Request", txn, "creation", age, update_modified=False)
		return txn

	def test_reconcile_prefers_the_successful_retry(self):
		txn = self.queued()
		rows = [
			{"txnid": txn, "status": "failure", "amount": "2500.00", "easepayid": "EZTRY1", "error_Message": "declined"},
			{"txnid": txn, "status": "success", "amount": "2500.00", "easepayid": "EZTRY2"},
		]
		with patch.object(ezs.EasebuzzSettings, "retrieve_transaction", lambda self, t: {"status": True, "msg": rows}):
			ez.reconcile_pending()
		self.assertEqual(self.ir_status(txn), "Completed")
		self.assertEqual(frappe.db.get_value("Fee Demand", self.d_ez, "status"), "Paid")

	def test_unreachable_easebuzz_never_expires_a_checkout(self):
		txn = self.queued(days_old=3)

		def down(self, t):
			raise ConnectionError("easebuzz down")

		# the checkout was committed at start in real use; keep this test's (uncommitted) one through rollback
		with patch.object(ezs.EasebuzzSettings, "retrieve_transaction", down), patch.object(frappe, "log_error"), \
				patch.object(frappe.db, "rollback", lambda *a, **k: None):
			ez.reconcile_pending()
		self.assertEqual(self.ir_status(txn), "Queued")

	def test_mismatch_releases_the_charge(self):
		txn = self.queued()
		calls = []
		flows = {**ez.FLOWS, "demands": {**ez.FLOWS["demands"], "failure": lambda *a, **k: calls.append(k)}}
		with patch.object(ez, "FLOWS", flows), patch.object(frappe, "log_error"):
			self.as_guest_callback(ez.complete, signed(txn, 1, easepayid="EZMIS"))
		self.assertEqual(self.ir_status(txn), "Failed")
		self.assertEqual(calls, [{"cancelled": False}])

	def test_webhook_error_answers_200_and_leaves_checkout_for_reconcile(self):
		txn = self.queued()

		def boom(*a, **k):
			raise frappe.ValidationError("booking failed")

		flows = {**ez.FLOWS, "demands": {**ez.FLOWS["demands"], "success": boom}}
		with patch.object(ez, "FLOWS", flows), patch.object(frappe, "log_error") as log, \
				patch.object(frappe.db, "rollback", lambda *a, **k: None):
			self.assertEqual(self.as_guest_callback(ez.webhook, signed(txn, 2500, easepayid="EZBOOM")), "logged")
		self.assertTrue(log.called)
		self.assertNotEqual(frappe.local.response.get("http_status_code"), 500)
		self.assertEqual(self.ir_status(txn), "Queued")


class TestFeeStructureGateway(GatewayTestCase):
	"""Programme-fee invoices follow the Fee Structure's Payment Gateway; admission payments stay on Razorpay."""

	def make_structure(self, gateway, online=1):
		fs = frappe.get_doc({
			"doctype": "Fee Structure", "fee_structure_name": f"_GW FS {gateway} {online} {frappe.generate_hash(length=5)}",
			"applicable": "Student", "online_payment": online, "payment_gateway": gateway if online else None,
			"status": "Active",
		})
		fs.flags.ignore_mandatory = fs.flags.ignore_links = fs.flags.ignore_validate = True
		fs.insert(ignore_permissions=True)
		return fs.name

	def program_fee_invoice(self, **extra):
		inv = frappe.get_doc({
			"doctype": "Fee Invoice", "student": self.student, "invoice_date": today(), "due_date": add_days(today(), 10),
			# the portal's own invoices carry one generic, Razorpay-collected "Program Fee" line
			"fee_components": [{"fee_component": self.comp_rzp, "amount": 900, "total_amount": 900}],
			**extra,
		})
		inv.flags.ignore_links = inv.flags.ignore_mandatory = True
		inv.insert(ignore_permissions=True)
		return inv.name

	def test_invoice_follows_the_students_fee_structure(self):
		frappe.db.set_value("Student Master", self.student, "fee_structure", self.make_structure("Easebuzz"))
		inv = self.program_fee_invoice()
		self.assertEqual(gw.for_invoice(inv), "Easebuzz")
		frappe.set_user(self.student_user)
		self.assertEqual(sp.create_payment_order(inv)["gateway"], "Easebuzz")

	def test_structure_without_online_payment_falls_back_to_components(self):
		frappe.db.set_value("Student Master", self.student, "fee_structure", self.make_structure("Easebuzz", online=0))
		self.assertEqual(gw.for_invoice(self.program_fee_invoice()), "Razorpay")

	def test_fee_assignment_structure_wins_over_the_students(self):
		frappe.db.set_value("Student Master", self.student, "fee_structure", self.make_structure("Easebuzz"))
		sfa = frappe.get_doc({
			"doctype": "Student Fee Assignment", "student": self.student, "fee_structure": self.make_structure("Razorpay"),
		})
		sfa.flags.ignore_mandatory = sfa.flags.ignore_links = sfa.flags.ignore_validate = True
		sfa.insert(ignore_permissions=True)
		self.assertEqual(gw.for_invoice(self.program_fee_invoice(fee_assignment=sfa.name)), "Razorpay")

	def test_offer_letter_payments_stay_on_razorpay(self):
		from slcm.api.service.fee_service import _offer_payment_gateway

		self.assertEqual(_offer_payment_gateway(self.make_structure("Easebuzz")), "Razorpay")
		self.assertEqual(_offer_payment_gateway(self.make_structure("Razorpay")), "Razorpay")
		self.assertEqual(_offer_payment_gateway(None), "Razorpay")


class TestStaleDemandLinks(GatewayTestCase):
	"""A payment is booked even when its demand's Source Document is gone; deleting a re-exam cancels its demand."""

	def test_payment_books_on_demand_whose_source_was_deleted(self):
		# (exam demands are not paid from the Fees page any more: a stale hostel-fine link stands in)
		frappe.db.set_value("Fee Demand", self.d_ez, {
			"trigger_ref_doctype": "Hostel Fine", "trigger_ref_name": "HF-DELETED-0001",
		})
		frappe.set_user(self.student_user)
		txn = sp.create_bulk_demand_payment_order(json.dumps([self.d_ez]))["txnid"]
		frappe.set_user("Administrator")
		self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid="EZSTALE"))
		self.assertEqual(self.ir_status(txn), "Completed")
		self.assertEqual(frappe.db.get_value("Fee Demand", self.d_ez, "status"), "Paid")

	def test_deleting_a_re_exam_cancels_its_unpaid_demand(self):
		from slcm.slcm.fee import event_hooks

		frappe.db.set_value("Fee Demand", self.d_ez, {
			"trigger_ref_doctype": "Re Exam Registration", "trigger_ref_name": "REX-TRASH-0001",
		})
		event_hooks.on_exam_registration_trash(frappe._dict(doctype="Re Exam Registration", name="REX-TRASH-0001"))
		self.assertEqual(frappe.db.get_value("Fee Demand", self.d_ez, "status"), "Cancelled")
		self.assertEqual(frappe.db.get_value("Fee Demand", self.d_rzp, "status"), "Pending")


class TestUnrecordedPaymentMessage(GatewayTestCase):
	"""Money captured but booking failed: the payer is told it was received (not "being confirmed")."""

	def test_payer_sees_received_until_a_retry_records_it(self):
		frappe.set_user(self.student_user)
		txn = sp.create_demand_payment_order(self.d_ez)["txnid"]
		frappe.set_user("Administrator")

		def boom(*a, **k):
			raise frappe.ValidationError("booking failed")

		flows = {**ez.FLOWS, "demands": {**ez.FLOWS["demands"], "success": boom}}
		with patch.object(ez, "FLOWS", flows), patch.object(frappe, "log_error") as log, \
				patch.object(frappe.db, "rollback", lambda *a, **k: None):
			self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid="EZUNREC"))
			self.as_guest_callback(ez.webhook, signed(txn, 2500, easepayid="EZUNREC"))
			frappe.set_user(self.student_user)
			row = {"txnid": txn, "status": "success", "amount": "2500.00", "easepayid": "EZUNREC"}
			with patch.object(ezs.EasebuzzSettings, "retrieve_transaction", lambda self, t: {"status": True, "msg": [row]}):
				res = ez.get_payment_result(txn)
			frappe.set_user("Administrator")
		self.assertEqual((res["status"], res["payment_id"]), ("received", "EZUNREC"))
		self.assertEqual(self.ir_status(txn), "Queued")  # still retried
		titles = [c.args[1] if len(c.args) > 1 else c.kwargs.get("title") for c in log.call_args_list]
		self.assertEqual(titles.count("Easebuzz payment received but not recorded"), 1)  # logged once

		# the next retry books it and the flag goes away
		self.as_guest_callback(ez.webhook, signed(txn, 2500, easepayid="EZUNREC"))
		frappe.set_user(self.student_user)
		self.assertEqual(ez.get_payment_result(txn)["status"], "success")
		frappe.set_user("Administrator")


class TestConcurrentPayers(GatewayTestCase):
	"""Student and parent paying the same fees at the same time (slcm.slcm.fee.checkout_guard)."""

	def parent_checkout(self, demands):
		frappe.set_user(self.parent_user)
		try:
			return sp.parent_create_bulk_demand_payment_order(json.dumps(demands), self.student)
		finally:
			frappe.set_user("Administrator")

	def student_checkout(self, demands):
		frappe.set_user(self.student_user)
		try:
			return sp.create_bulk_demand_payment_order(json.dumps(demands))
		finally:
			frappe.set_user("Administrator")

	def age(self, txn, minutes):
		frappe.db.set_value("Integration Request", txn, "creation",
		                    frappe.utils.add_to_date(None, minutes=-minutes), update_modified=False)

	def test_second_payer_is_stopped_while_first_checkout_is_open(self):
		self.parent_checkout([self.d_ez])
		with self.assertRaises(frappe.ValidationError) as ctx:
			self.student_checkout([self.d_ez])
		self.assertIn("started by the parent", str(ctx.exception))

	def test_own_retry_and_other_fees_are_not_blocked(self):
		first = self.parent_checkout([self.d_ez])["txnid"]
		self.assertNotEqual(self.parent_checkout([self.d_ez])["txnid"], first)  # the payer's own retry
		frappe.cache().delete_value(f"slcm_checkout_claim:{self.student}")
		from slcm.slcm.fee.checkout_guard import ensure_no_other_checkout

		frappe.set_user(self.student_user)
		try:
			ensure_no_other_checkout(self.student, demand_names=[self.d_rzp])  # a different fee: no error
		finally:
			frappe.set_user("Administrator")

	def test_finished_or_stale_checkout_does_not_block(self):
		txn = self.parent_checkout([self.d_ez])["txnid"]
		frappe.cache().delete_value(f"slcm_checkout_claim:{self.student}")
		frappe.db.set_value("Integration Request", txn, "status", "Cancelled")
		self.assertTrue(self.student_checkout([self.d_ez])["txnid"])

		frappe.cache().delete_value(f"slcm_checkout_claim:{self.student}")
		frappe.db.sql("update `tabIntegration Request` set status = 'Queued' where name = %s", txn)
		self.age(txn, 25)  # older than ACTIVE_MINUTES: its link has expired
		from slcm.slcm.fee.checkout_guard import active_checkout
		self.assertIsNone(active_checkout(self.student, {("Fee Demand", self.d_ez)}, exclude_user=self.student_user))

	def test_claim_stops_a_simultaneous_click(self):
		from slcm.slcm.fee import checkout_guard as cg

		frappe.set_user(self.parent_user)
		cg._claim(self.student, {("Fee Demand", self.d_ez)}, self.parent_user, "Parent")
		frappe.set_user("Administrator")
		self.assertRaises(frappe.ValidationError, self.student_checkout, [self.d_ez])

	def test_razorpay_checkout_blocks_the_other_payer_too(self):
		ir = frappe.get_doc({
			"doctype": "Integration Request", "integration_request_service": "Razorpay", "status": "Queued",
			"data": json.dumps({"slcm_intent": {
				"flow": "demands", "student": self.student, "user": self.parent_user, "paid_by_role": "Parent",
				"demand_names": [self.d_ez], "order_id": "order_TEST",
			}}),
		}).insert(ignore_permissions=True)
		self.assertTrue(ir.name)
		self.assertRaises(frappe.ValidationError, self.student_checkout, [self.d_ez])

	def test_second_payment_after_expiry_is_reported_as_refund(self):
		first = self.parent_checkout([self.d_ez])["txnid"]
		self.age(first, 25)
		frappe.cache().delete_value(f"slcm_checkout_claim:{self.student}")
		second = self.student_checkout([self.d_ez])["txnid"]
		self.as_guest_callback(ez.complete, signed(first, 2500, easepayid="EZPAR1"))
		with patch.object(frappe, "log_error"):
			self.as_guest_callback(ez.complete, signed(second, 2500, easepayid="EZSTU1"))
		frappe.set_user(self.student_user)
		res = ez.get_payment_result(second)
		frappe.set_user(self.parent_user)
		first_res = ez.get_payment_result(first)
		frappe.set_user("Administrator")
		self.assertEqual((res["status"], res["refund_amount"]), ("duplicate", 2500))
		self.assertEqual(first_res["status"], "success")
		pr = frappe.db.get_value("SLCM Payment Request", {"transaction_id": "EZSTU1"}, ["status", "amount"], as_dict=True)
		self.assertEqual((pr.status, flt(pr.amount)), ("Paid", 2500))  # recorded for the refund

	def test_razorpay_duplicate_confirm_is_flagged(self):
		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "payment_date": today(),
			"payment_mode": "Online Payment", "amount": 1000, "reference_number": "pay_FIRST1",
			"payment_gateway": "Razorpay",
			"payment_demands": [{"fee_demand": self.d_rzp, "outstanding_amount": 1000, "amount_allocated": 1000}],
		})
		fp.insert(ignore_permissions=True)
		fp.submit()
		self.assertEqual(sp._already_paid("pay_FIRST1")["status"], "success")  # its own, already recorded
		self.assertTrue(sp._already_paid("pay_SECOND1")["duplicate"])

	def test_unbooked_razorpay_capture_is_recorded_for_refund(self):
		from slcm.api import razorpay_reconcile as rr

		frappe.get_doc({
			"doctype": "Integration Request", "integration_request_service": "Razorpay", "status": "Completed",
			"data": json.dumps({"slcm_intent": {
				"flow": "demands", "student": self.student, "user": self.student_user, "paid_by_role": "Student",
				"demand_names": [self.d_rzp], "order_id": "order_DUP1", "amount": 1000,
			}}),
		}).insert(ignore_permissions=True)
		old = frappe.utils.now_datetime().timestamp() - 3600
		payments = [
			{"id": "pay_DUPLICATE1", "status": "captured", "amount": 100000, "created_at": old},
			{"id": "pay_JUSTNOW1", "status": "captured", "amount": 100000, "created_at": old + 3500},  # too fresh
			{"id": "pay_FAILED1", "status": "failed", "amount": 100000, "created_at": old},
		]
		with patch.object(rr, "_order_payments", lambda order_id: payments), patch.object(frappe, "log_error"):
			self.assertEqual(rr.record_unbooked_captures(), 1)
			self.assertEqual(rr.record_unbooked_captures(), 0)  # idempotent
		pr = frappe.db.get_value("SLCM Payment Request", {"transaction_id": "pay_DUPLICATE1"},
		                         ["status", "amount", "reference_doctype"], as_dict=True)
		self.assertEqual((pr.status, flt(pr.amount), pr.reference_doctype), ("Paid", 1000, "Fee Demand"))
		self.assertFalse(frappe.db.exists("SLCM Payment Request", {"transaction_id": "pay_JUSTNOW1"}))


class TestStudentIdentityInResponse(GatewayTestCase):
	"""gateway_response names the student: Student Name (first_name) and Student ID (registration_id)."""

	def test_paid_failed_and_backfilled_requests_carry_name_and_id(self):
		from slcm.slcm.fee import payment_ledger

		frappe.db.set_value("Student Master", self.student, {"first_name": "Gateway", "registration_id": "REG-GW-01"})
		frappe.set_user(self.student_user)
		txn = sp.create_bulk_demand_payment_order(json.dumps([self.d_ez]))["txnid"]
		frappe.set_user("Administrator")
		self.as_guest_callback(ez.complete, signed(txn, 2500, easepayid="EZIDENT"))
		pr = frappe.db.get_value("SLCM Payment Request", {"transaction_id": "EZIDENT"}, "name")
		response = json.loads(frappe.db.get_value("SLCM Payment Request", pr, "gateway_response"))
		self.assertEqual((response["student_name"], response["registration_id"]), ("Gateway", "REG-GW-01"))
		self.assertEqual(list(response)[:6], ["gateway", "payment_id", "order_id", "student", "student_name", "registration_id"])

		# a request written before the fields existed is filled in once
		old = {k: v for k, v in response.items() if k not in ("student_name", "registration_id")}
		frappe.db.set_value("SLCM Payment Request", pr, "gateway_response", json.dumps(old))
		self.assertGreaterEqual(payment_ledger.fill_student_identity(), 1)
		filled = json.loads(frappe.db.get_value("SLCM Payment Request", pr, "gateway_response"))
		self.assertEqual(filled["registration_id"], "REG-GW-01")
		self.assertEqual(payment_ledger.fill_student_identity(), 0)


class TestCriticalPaymentGaps(GatewayTestCase):
	"""C2 transcript replay, C3 part-paid invoices, H1/H2 Razorpay recovery, H3 over-capture, C5/M1 refunds, M11."""

	RZP_SECRET = "TESTRZPSECRET"

	def setUp(self):
		super().setUp()
		from payments.payment_gateways.doctype.razorpay_settings import razorpay_settings as rs

		secret = self.RZP_SECRET

		def verify_signature(self_, body, signature, key):
			import hashlib, hmac
			if not hmac.compare_digest(hmac.new(key.encode(), body.encode(), hashlib.sha256).hexdigest(), signature):
				raise frappe.ValidationError("bad signature")

		for p in (
			patch.object(rs.RazorpaySettings, "get_password", lambda self_, fieldname=None, raise_exception=True: secret),
			patch.object(rs.RazorpaySettings, "verify_signature", verify_signature, create=True),
			patch.object(rs, "order_payment_success", lambda *a, **k: None),
		):
			p.start()
			self.addCleanup(p.stop)
		frappe.db.set_single_value("Transcript Fee Settings", {"auto_approve_interim": 0, "auto_approve_final": 0})

	def sign(self, order_id, payment_id):
		import hashlib, hmac
		return hmac.new(self.RZP_SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()

	def intent_ir(self, flow, amount, user=None, role="Student", **refs):
		order_id = f"order_{frappe.generate_hash(length=10)}"
		ir = frappe.get_doc({
			"doctype": "Integration Request", "integration_request_service": "Razorpay", "status": "Queued",
			"data": json.dumps({"slcm_intent": {
				"flow": flow, "order_id": order_id, "student": self.student, "amount": amount,
				"user": user or self.student_user, "paid_by_role": role, **refs,
			}}),
		}).insert(ignore_permissions=True)
		return ir.name, order_id

	def invoice(self, amount):
		inv = frappe.get_doc({
			"doctype": "Fee Invoice", "student": self.student, "invoice_date": today(), "due_date": add_days(today(), 10),
			"fee_components": [{"fee_component": self.comp_rzp, "amount": amount, "total_amount": amount}],
		})
		inv.flags.ignore_links = inv.flags.ignore_mandatory = True
		inv.insert(ignore_permissions=True)
		return inv.name

	def transcript(self, fee, order_id=None):
		req = frappe.get_doc({
			"doctype": "Transcript Request", "student": self.student, "transcript_type": "Interim Transcript",
			"num_copies": 1, "requested_on": today(), "payment_required": 1, "fee_amount": fee,
			"payment_status": "Pending", "status": "Payment Pending", "razorpay_order_id": order_id,
		})
		req.flags.ignore_links = req.flags.ignore_mandatory = req.flags.ignore_validate = True
		req.db_insert()
		return req.name

	def outstanding_inv(self, inv):
		return flt(frappe.db.get_value("Fee Invoice", inv, "outstanding_amount"))

	# C3
	def test_part_paid_invoice_books_the_parents_online_payment(self):
		inv = self.invoice(900)
		counter = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "fee_invoice": inv, "payment_date": today(),
			"payment_mode": "Cash", "amount": 400,
		})
		counter.insert(ignore_permissions=True)
		counter.submit()
		self.assertEqual(self.outstanding_inv(inv), 500)
		ir, order = self.intent_ir("invoice", 500, user=self.parent_user, role="Parent", invoice_name=inv)
		frappe.set_user(self.parent_user)
		res = sp.parent_confirm_fee_payment(inv, self.student, ir, "pay_PARTPAID1", order, self.sign(order, "pay_PARTPAID1"))
		frappe.set_user("Administrator")
		self.assertEqual(res["status"], "success")
		self.assertEqual(flt(frappe.db.get_value("Fee Payment", {"reference_number": "pay_PARTPAID1", "docstatus": 1}, "amount")), 500)
		self.assertEqual(self.outstanding_inv(inv), 0)
		self.assertIn("Parent", frappe.db.get_value("Fee Payment", {"reference_number": "pay_PARTPAID1"}, "remarks"))

	# H3 + C5/M1
	def test_overcapture_shows_unallocated_and_refund_is_recorded(self):
		from slcm.slcm.fee import payment_ledger as pl
		from slcm.slcm.report.payments_to_refund import payments_to_refund as rep

		inv = self.invoice(500)
		ir, order = self.intent_ir("invoice", 900, invoice_name=inv)  # the order charged more than is now due
		frappe.set_user(self.student_user)
		sp.confirm_fee_payment(inv, ir, "pay_OVER1", order, self.sign(order, "pay_OVER1"))
		frappe.set_user("Administrator")
		pr = frappe.db.get_value("SLCM Payment Request", {"transaction_id": "pay_OVER1"}, "name")
		self.assertEqual(flt(frappe.db.get_value("SLCM Payment Request", pr, "amount")), 900)
		self.assertEqual(json.loads(frappe.db.get_value("SLCM Payment Request", pr, "gateway_response"))["unallocated"], 400)
		self.assertEqual(pl.refundable_amount(pr), 400)
		self.assertIn(pr, [r.name for r in rep.execute({})[1]])

		self.assertRaises(frappe.ValidationError, pl.record_refund, pr, "rfnd_1", today(), 500)  # more than unapplied
		pl.record_refund(pr, "rfnd_1", today(), 400)
		self.assertEqual(pl.refundable_amount(pr), 0)
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr, "refund_reference"), "rfnd_1")
		self.assertNotIn(pr, [r.name for r in rep.execute({})[1]])
		self.assertIn(pr, [r.name for r in rep.execute({"include_refunded": 1})[1]])

	# C2
	def test_transcript_payment_is_bound_to_its_own_request(self):
		from slcm.api import transcript_request as tr

		cheap = self.transcript(300)
		dear = self.transcript(1000, order_id="order_DEAR")
		ir, cheap_order = self.intent_ir("transcript", 300, request_name=cheap)
		frappe.db.set_value("Transcript Request", cheap, "razorpay_order_id", cheap_order)
		frappe.set_user(self.student_user)
		try:
			sig = self.sign(cheap_order, "pay_CHEAP1")
			with patch.object(frappe, "log_error"):
				self.assertRaises(frappe.PermissionError, tr.confirm_payment, dear, "pay_CHEAP1", cheap_order, sig)
			self.assertTrue(tr.confirm_payment(cheap, "pay_CHEAP1", cheap_order, sig)["success"])
			# the same payment on the other request's own order is refused too
			self.assertRaises(frappe.PermissionError, tr.confirm_payment, dear, "pay_CHEAP1", "order_DEAR",
			                  self.sign("order_DEAR", "pay_CHEAP1"))
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Transcript Request", dear, "payment_status"), "Pending")
		self.assertEqual(frappe.db.get_value("Transcript Request", cheap, "payment_status"), "Paid")

	def test_transcript_older_order_paid_late_is_accepted(self):
		from slcm.api import transcript_request as tr

		req = self.transcript(300)
		ir, old_order = self.intent_ir("transcript", 300, request_name=req)
		frappe.db.set_value("Transcript Request", req, "razorpay_order_id", "order_NEWERRETRY")  # student retried
		frappe.set_user(self.student_user)
		try:
			self.assertTrue(tr.confirm_payment(req, "pay_LATE1", old_order, self.sign(old_order, "pay_LATE1"))["success"])
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Transcript Request", req, "payment_reference"), "pay_LATE1")

	# H1 / H2
	def test_reconciler_recovers_razorpay_exam_and_transcript_payments(self):
		from slcm.api import razorpay_reconcile as rr

		reg = frappe.get_doc({
			"doctype": "Re Exam Registration", "student": self.student, "re_exam_fee": 700,
			"status": "Registered", "payment_status": "Payment Initiated",
		})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.insert(ignore_permissions=True)
		rex_ir, _o = self.intent_ir("re_exam", 700, registration=reg.name)
		req = self.transcript(300)
		tr_ir, _o2 = self.intent_ir("transcript", 300, request_name=req)

		payments = {"re": [{"id": "pay_RECREX1", "status": "captured", "amount": 70000}],
		            "tr": [{"id": "pay_RECTRN1", "status": "captured", "amount": 30000}]}
		with patch.object(rr, "_order_payments", lambda order_id: payments["re"]):
			self.assertEqual(rr.reconcile_one(rex_ir), "recorded")
		with patch.object(rr, "_order_payments", lambda order_id: payments["tr"]):
			self.assertEqual(rr.reconcile_one(tr_ir), "recorded")
		self.assertEqual(frappe.db.get_value("Re Exam Registration", reg.name, ["payment_status", "payment_reference"]),
		                 ("Paid", "pay_RECREX1"))
		self.assertTrue(frappe.db.exists("Re Exam Payment Log", {"razorpay_payment_id": "pay_RECREX1", "payment_status": "Paid"}))
		self.assertEqual(frappe.db.get_value("Transcript Request", req, "payment_reference"), "pay_RECTRN1")
		self.assertTrue(frappe.db.exists("SLCM Payment Request", {"transaction_id": "pay_RECREX1", "status": "Paid"}))

	# C5
	def test_rejected_transcript_is_not_refunded_until_it_is(self):
		from slcm.api import transcript_request as tr
		from slcm.slcm.fee import payment_ledger as pl

		req = self.transcript(300)
		tr.mark_request_paid(req, self.student, "pay_REJ1", "order_REJ1")
		pr = frappe.db.get_value("SLCM Payment Request", {"transaction_id": "pay_REJ1"}, "name")
		frappe.db.set_value("Transcript Request", req, {"status": "Rejected", "payment_status": "Refund Pending"})
		pl.sync("pay_REJ1")
		self.assertNotEqual(frappe.db.get_value("SLCM Payment Request", pr, "gateway_status"), "refunded")
		self.assertEqual(pl.refundable_amount(pr), 300)  # owed back, listed for the refund
		frappe.db.set_value("Transcript Request", req, "payment_status", "Refunded")
		pl.sync("pay_REJ1")
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr, "gateway_status"), "refunded")

	def test_failed_refund_webhook_puts_invoice_back(self):
		from slcm.slcm import api as slcm_api

		inv = self.invoice(500)
		frappe.db.set_value("Fee Invoice", inv, "payment_status", "Refunded")
		slcm_api._handle_refund_failed({"payload": {
			"refund": {"entity": {"id": "rfnd_X"}},
			"payment": {"entity": {"notes": {"reference_doctype": "Fee Invoice", "reference_name": inv}}},
		}})
		self.assertEqual(frappe.db.get_value("Fee Invoice", inv, "payment_status"), "Captured")

	# M11
	def test_status_cannot_be_edited_after_submit(self):
		meta = frappe.get_meta("SLCM Payment Request")
		self.assertFalse(meta.get_field("status").allow_on_submit)
		self.assertFalse(meta.get_field("gateway_status").allow_on_submit)


class TestHighPaymentGaps(GatewayTestCase):
	"""H5 receipt reports, H6 desk Pay Online, H7 exam fees only on the exam pages."""

	def exam_demand(self, registration, amount=750):
		frappe.db.set_value("Fee Demand", self.d_ez, {
			"trigger_ref_doctype": "Re Exam Registration", "trigger_ref_name": registration,
			"original_amount": amount,
		})
		return self.d_ez

	def re_exam_reg(self, fee=750, status="Pending"):
		reg = frappe.get_doc({
			"doctype": "Re Exam Registration", "student": self.student, "re_exam_fee": fee,
			"status": "Registered", "payment_status": status,
		})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.insert(ignore_permissions=True)
		return reg.name

	# H7
	def test_exam_fee_is_refused_on_the_fees_page(self):
		demand = self.exam_demand(self.re_exam_reg())
		frappe.set_user(self.student_user)
		try:
			self.assertRaises(frappe.ValidationError, sp.create_bulk_demand_payment_order, json.dumps([demand]))
			self.assertRaises(frappe.ValidationError, sp.create_demand_payment_order, demand)
		finally:
			frappe.set_user("Administrator")
		frappe.set_user(self.parent_user)
		try:
			self.assertRaises(frappe.ValidationError, sp.parent_create_bulk_demand_payment_order, json.dumps([demand]), self.student)
		finally:
			frappe.set_user("Administrator")
		from slcm.slcm.fee.portal_charges import is_unpaid_exam_demand
		self.assertTrue(is_unpaid_exam_demand(frappe.db.get_value("Fee Demand", demand, ["trigger_ref_doctype", "status"], as_dict=True)))
		self.assertFalse(is_unpaid_exam_demand(frappe.db.get_value("Fee Demand", self.d_rzp, ["trigger_ref_doctype", "status"], as_dict=True)))

	def test_paying_on_the_exam_page_cancels_the_enrolment_demand(self):
		reg = self.re_exam_reg()
		demand = self.exam_demand(reg)
		frappe.get_doc({
			"doctype": "Re Exam Payment Log", "re_exam_registration": reg, "razorpay_payment_id": "pay_EXAMPAGE1",
			"payment_gateway": "Razorpay", "payment_status": "Paid", "amount": 750,
		}).insert(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Fee Demand", demand, "status"), "Cancelled")
		self.assertEqual(frappe.db.get_value("Fee Demand", self.d_rzp, "status"), "Pending")  # other dues untouched

	def test_enrolled_fee_is_charged_without_a_course_setting_fee(self):
		exam_plan = frappe.db.get_value("Exam Plan", {}, "name")
		course = frappe.db.get_value("Course", {}, "name")
		if not (exam_plan and course):
			self.skipTest("needs an Exam Plan and a Course")
		frappe.db.delete("Re Exam Course Setting", {"exam_plan": exam_plan, "course": course})
		setting = frappe.get_doc({"doctype": "Re Exam Course Setting", "exam_plan": exam_plan, "course": course,
		                          "re_exam_fee": 0, "payment_gateway": "Easebuzz"})
		setting.flags.ignore_links = setting.flags.ignore_mandatory = True
		setting.insert(ignore_permissions=True)
		reg = frappe.get_doc({"doctype": "Re Exam Registration", "student": self.student, "exam_plan": exam_plan,
		                      "course": course, "re_exam_fee": 900, "status": "Registered", "payment_status": "Pending"})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.insert(ignore_permissions=True)
		frappe.set_user(self.student_user)
		try:
			res = sp.create_re_exam_payment_order(exam_plan, course)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(flt(res["amount"]), 900)

	# H5
	def test_receipt_reports_skip_cancelled_and_count_each_receipt_once(self):
		from slcm.slcm.report.collection_summary import collection_summary as cs
		from slcm.slcm.report.receipt_register import receipt_register as rr

		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "payment_date": today(), "payment_mode": "Cash",
			"amount": 3500,
			"payment_demands": [
				{"fee_demand": self.d_rzp, "outstanding_amount": 1000, "amount_allocated": 1000},
				{"fee_demand": self.d_ez, "outstanding_amount": 2500, "amount_allocated": 2500},
			],
		})
		fp.insert(ignore_permissions=True)
		fp.submit()
		receipt = frappe.db.get_value("Fee Receipt", {"fee_payment": fp.name}, "name")
		f = {"from_date": today(), "to_date": today()}
		mine = lambda rows: sum(flt(r.get("total_collected")) for r in rows if r.get("payment_mode") == "Cash")
		before_cancel = mine(cs.execute(f)[1])
		self.assertGreaterEqual(before_cancel, 3500)
		self.assertIn(receipt, [r.name for r in rr.execute(f)[1]])
		frappe.db.set_value("Fee Receipt", receipt, "status", "Cancelled")
		self.assertNotIn(receipt, [r.name for r in rr.execute(f)[1]])
		self.assertAlmostEqual(before_cancel - mine(cs.execute(f)[1]), 3500)  # once, not once per demand

	# H6
	def test_desk_pay_online_books_captured_amount_and_flags_excess(self):
		from slcm.api import razorpay_reconcile as rr

		inv = frappe.get_doc({
			"doctype": "Fee Invoice", "student": self.student, "invoice_date": today(), "due_date": add_days(today(), 10),
			"fee_components": [{"fee_component": self.comp_rzp, "amount": 500, "total_amount": 500}],
		})
		inv.flags.ignore_links = inv.flags.ignore_mandatory = True
		inv.insert(ignore_permissions=True)
		frappe.flags.data = {"razorpay_payment_id": "pay_DESK1"}
		try:
			with patch.object(rr, "_payment", lambda pid: {"status": "captured", "amount": 80000, "order_id": "order_DESK1"}):
				frappe.get_doc("Fee Invoice", inv.name).on_payment_authorized("Completed")
				frappe.get_doc("Fee Invoice", inv.name).on_payment_authorized("Completed")  # repeat: no second booking
		finally:
			frappe.flags.data = None
		fps = frappe.get_all("Fee Payment", {"reference_number": "pay_DESK1", "docstatus": 1}, ["amount", "payment_gateway"])
		self.assertEqual([(flt(f.amount), f.payment_gateway) for f in fps], [(500, "Razorpay")])


class TestMediumPaymentGaps(GatewayTestCase):
	"""M2 payout refunds, M4 cancelled online payment / exam registration, M5 exam failures, M8 parent amount,
	M9 parent invoice cancel / fail."""

	def invoice(self, amount):
		inv = frappe.get_doc({
			"doctype": "Fee Invoice", "student": self.student, "invoice_date": today(), "due_date": add_days(today(), 10),
			"fee_components": [{"fee_component": self.comp_rzp, "amount": amount, "total_amount": amount}],
		})
		inv.flags.ignore_links = inv.flags.ignore_mandatory = True
		inv.insert(ignore_permissions=True)
		return inv.name

	# M8
	def test_parent_pays_the_same_amount_as_the_student(self):
		inv = self.invoice(1000)
		frappe.db.set_value("Student Master", self.student, "discount_amount", 300)  # scholarship not on the invoice yet
		self.assertEqual(sp._effective_invoice_outstanding(inv, self.student, 1000), (700, 300))
		frappe.set_user(self.parent_user)
		try:
			order = sp.parent_create_payment_order(inv, self.student)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(flt(order.get("amount")) / (100 if flt(order.get("amount")) > 1000 else 1), 700)

	# M9
	def test_parent_closing_or_failing_the_checkout_releases_it(self):
		inv = self.invoice(1000)
		ir = frappe.get_doc({
			"doctype": "Integration Request", "integration_request_service": "Razorpay", "status": "Queued",
			"data": json.dumps({"slcm_intent": {"flow": "invoice", "order_id": "order_PARCAN1", "student": self.student,
			                                    "amount": 1000, "user": self.parent_user, "paid_by_role": "Parent",
			                                    "invoice_name": inv}}),
		}).insert(ignore_permissions=True)
		frappe.db.set_value("Fee Invoice", inv, "payment_status", "Payment Initiated")
		frappe.set_user(self.parent_user)
		try:
			sp.parent_cancel_fee_payment(inv, self.student, ir.name)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Integration Request", ir.name, "status"), "Cancelled")
		self.assertEqual(frappe.db.get_value("Fee Invoice", inv, "payment_status"), "Pending")
		from slcm.slcm.fee.checkout_guard import active_checkout
		self.assertIsNone(active_checkout(self.student, {("Fee Invoice", inv)}, exclude_user=self.student_user))

		frappe.db.set_value("Integration Request", ir.name, "status", "Queued")
		frappe.db.set_value("Fee Invoice", inv, "payment_status", "Payment Initiated")
		frappe.set_user(self.parent_user)
		try:
			sp.parent_mark_fee_payment_failed(inv, self.student, ir.name, "pay_PARFAIL1", "Card declined", "BAD_REQUEST_ERROR")
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Fee Invoice", inv, "payment_status"), "Payment Failed")
		self.assertTrue(frappe.db.exists("Student Fee Payment Log", {"razorpay_payment_id": "pay_PARFAIL1", "paid_by_role": "Parent"}))

	# M5
	def test_razorpay_exam_failure_is_recorded(self):
		reg = frappe.get_doc({"doctype": "Re Exam Registration", "student": self.student, "re_exam_fee": 700,
		                      "status": "Registered", "payment_status": "Payment Initiated"})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.insert(ignore_permissions=True)
		frappe.set_user(self.student_user)
		try:
			sp.mark_exam_payment_failed(reg.name, "re_exam", "pay_EXFAIL1", "Bank declined", "BAD_REQUEST_ERROR")
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Re Exam Registration", reg.name, "payment_status"), "Payment Failed")
		pr = frappe.db.get_value("SLCM Payment Request", {"transaction_id": "pay_EXFAIL1"},
		                         ["status", "failure_message", "reference_doctype"], as_dict=True)
		self.assertEqual((pr.status, pr.reference_doctype), ("Failed", "Re Exam Registration"))
		self.assertIn("declined", pr.failure_message)

	# M4
	def test_cancelled_paid_exam_registration_frees_its_fee_for_refund(self):
		from slcm.slcm.fee import payment_ledger as pl

		reg = frappe.get_doc({"doctype": "Re Exam Registration", "student": self.student, "re_exam_fee": 700,
		                      "status": "Registered", "payment_status": "Paid", "payment_reference": "pay_EXCAN1"})
		reg.flags.ignore_links = reg.flags.ignore_mandatory = reg.flags.ignore_validate = True
		reg.insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "Re Exam Payment Log", "re_exam_registration": reg.name, "razorpay_payment_id": "pay_EXCAN1",
		                "payment_gateway": "Razorpay", "payment_status": "Paid", "amount": 700}).insert(ignore_permissions=True)
		pr = frappe.db.get_value("SLCM Payment Request", {"transaction_id": "pay_EXCAN1"}, "name")
		self.assertEqual(pl.refundable_amount(pr), 0)  # held by the registration
		doc = frappe.get_doc("Re Exam Registration", reg.name)
		doc.status = "Cancelled"
		doc.flags.ignore_links = doc.flags.ignore_mandatory = doc.flags.ignore_validate = True
		doc.save(ignore_permissions=True)
		self.assertEqual(pl.refundable_amount(pr), 700)
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr, "status"), "Paid")  # never cancelled

	def test_cancelling_an_online_fee_payment_warns(self):
		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": self.student, "payment_date": today(), "payment_mode": "Online Payment",
			"amount": 1000, "reference_number": "pay_CANWARN1", "payment_gateway": "Razorpay",
			"payment_demands": [{"fee_demand": self.d_rzp, "outstanding_amount": 1000, "amount_allocated": 1000}],
		})
		fp.insert(ignore_permissions=True)
		fp.submit()
		with patch.object(frappe, "msgprint") as msg:
			fp.cancel()
		self.assertTrue(any("does not refund" in str(c) for c in msg.call_args_list))

	# M2
	def test_refund_lines_in_payouts_are_recorded_once(self):
		from slcm.slcm.fee import easebuzz_settlement as es
		from slcm.slcm.fee import payment_ledger as pl

		pl.record_unapplied("Easebuzz", "EZREF1", "txnREF1", "Fee Demand", self.d_ez, 2500, self.student, "duplicate")
		pr = frappe.db.get_value("SLCM Payment Request", {"transaction_id": "EZREF1"}, "name")
		payout = {"paid_out": True, "payout_actual_date": "Nov-10-2026 10:00:00 AM", "payout_id": "PO1",
		          "peb_transactions": [], "peb_refunds": [{"peb_transaction_id": "EZREF1", "refund_id": "RFEZ1", "refund_amount": 2500}]}
		self.assertEqual(es.apply_payouts([payout]).get("refunds"), 1)
		self.assertEqual(es.apply_payouts([payout]).get("refunds"), None)  # same refund id: not twice
		self.assertEqual((flt(frappe.db.get_value("SLCM Payment Request", pr, "refunded_amount")), pl.refundable_amount(pr)), (2500, 0))


class TestRefundLog(GatewayTestCase):
	"""One refund is recorded once, however it reaches SLCM (by hand, webhook, payout line)."""

	def test_hand_recorded_refund_is_matched_to_its_payout_line(self):
		from slcm.slcm.fee import payment_ledger as pl

		pl.record_unapplied("Easebuzz", "EZLOG1", "txnLOG1", "Fee Demand", self.d_ez, 2500, self.student, "duplicate")
		pr = frappe.db.get_value("SLCM Payment Request", {"transaction_id": "EZLOG1"}, "name")
		pl.record_refund(pr, "UTR-TYPED-BY-STAFF", today(), 2500)
		self.assertRaises(frappe.ValidationError, pl.record_refund, pr, "UTR-TYPED-BY-STAFF", today(), 1)  # same ref twice
		# the payout reports it under the gateway's own refund id: same amount, so it is the same refund
		pl.record_gateway_refund("EZLOG1", "RFEZ-GATEWAY-9", 2500, today(), payout="PO9 (UTR U9)", payout_date=today())
		row = frappe.db.get_value("SLCM Payment Request", pr,
		                          ["refunded_amount", "refund_settled_amount", "refund_settlement_reference"], as_dict=True)
		self.assertEqual((flt(row.refunded_amount), flt(row.refund_settled_amount)), (2500, 2500))
		self.assertIn("PO9", row.refund_settlement_reference)
		log = json.loads(frappe.db.get_value("SLCM Payment Request", pr, "refund_log"))
		self.assertEqual(len(log), 1)
		self.assertEqual(log[0]["gateway_refund_id"], "RFEZ-GATEWAY-9")

	def test_failed_refund_is_removed(self):
		from slcm.slcm.fee import payment_ledger as pl

		pl.record_unapplied("Easebuzz", "EZLOG2", "txnLOG2", "Fee Demand", self.d_ez, 1000, self.student, "duplicate")
		pr = frappe.db.get_value("SLCM Payment Request", {"transaction_id": "EZLOG2"}, "name")
		pl.record_gateway_refund("EZLOG2", "RF-FAIL-1", 1000, today(), source="webhook")
		self.assertEqual(pl.refundable_amount(pr), 0)
		pl.remove_gateway_refund("EZLOG2", "RF-FAIL-1")
		self.assertEqual(pl.refundable_amount(pr), 1000)

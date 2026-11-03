# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from unittest.mock import patch
from slcm.tests.payment.payment_test_base import PaymentTestBase
from slcm.pace.web_form.pace_application_form.pace_application_form import verify_pace_payment_signature
from slcm.api.razorpay_webhook import handle_razorpay_webhook
from slcm.api.service.fee_service import FeeService
import json

class TestPACEPayments(PaymentTestBase):
	def test_successful_payment(self):
		"""TC-PACE-001: Successful PACE Application Fee Payment"""
		papp = self.create_pace_application()
		afa = self.create_pace_applicant_fee_assignment(papp.name, fee_type="Application Fee", amount=1000)
		pr = self.create_payment_request("PACE Applicant Fee Assignment", afa.name, "order_pace_001", amount=1000)

		# Ensure portal user check passes: mock _pace_portal_user_owns_application to return True
		self.mock_razorpay(payment_data={
			"id": "pay_pace_001",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_pace_001",
			"status": "captured"
		})
		self.mock_signature_verification()

		with patch("slcm.pace.web_form.pace_application_form.pace_application_form._pace_portal_user_owns_application", return_value=True):
			res = verify_pace_payment_signature(
				razorpay_payment_id="pay_pace_001",
				razorpay_order_id="order_pace_001",
				razorpay_signature="sig",
				assignment_name=afa.name
			)

		self.assertEqual(res.get("status"), "success")
		self.assertEqual(frappe.db.get_value("PACE Applicant Fee Assignment", afa.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("PACE Application", papp.name, "status"), "Completed")

		# Verify Receipt Generated
		receipts = frappe.get_all("PACE Receipt", filters={"pace_application": papp.name, "fee_type": "Application Fee"})
		self.assertEqual(len(receipts), 1)

		# Verify Document Verification Created
		self.assertTrue(frappe.db.exists("PACE Document Verification", {"application": papp.name}))

	def test_close_browser(self):
		"""TC-PACE-002: Close Browser (marked Paid by Webhook)"""
		papp = self.create_pace_application()
		afa = self.create_pace_applicant_fee_assignment(papp.name, fee_type="Application Fee", amount=1000)
		pr = self.create_payment_request("PACE Applicant Fee Assignment", afa.name, "order_pace_002", amount=1000)

		payload = {
			"event": "payment.captured",
			"payload": {
				"payment": {
					"entity": {
						"id": "pay_pace_002",
						"amount": 100000,
						"currency": "INR",
						"order_id": "order_pace_002",
						"status": "captured"
					}
				}
			}
		}

		with patch("frappe.request.get_data", return_value=json.dumps(payload).encode("utf-8")), \
			 patch("frappe.get_request_header", side_effect=self.sign_webhook_request), \
			 patch("slcm.pace.web_form.pace_application_form.pace_application_form._pace_portal_user_owns_application", return_value=True):
			handle_razorpay_webhook()

		self.assertEqual(frappe.db.get_value("PACE Applicant Fee Assignment", afa.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("PACE Application", papp.name, "status"), "Completed")
		receipts = frappe.get_all("PACE Receipt", filters={"pace_application": papp.name, "fee_type": "Application Fee"})
		self.assertEqual(len(receipts), 1)

	def test_scheduler_recovery(self):
		"""TC-PACE-003: Scheduler Recovery completes payment"""
		papp = self.create_pace_application()
		afa = self.create_pace_applicant_fee_assignment(papp.name, fee_type="Application Fee", amount=1000)
		pr = self.create_payment_request("PACE Applicant Fee Assignment", afa.name, "order_pace_003", amount=1000)

		from frappe.utils import add_to_date
		old_time = add_to_date(frappe.utils.now_datetime(), minutes=-20)
		frappe.db.sql("UPDATE `tabSLCM Payment Request` SET modified = %s WHERE name = %s", (old_time, pr.name))
		frappe.db.commit()

		self.mock_razorpay(payments_list=[{
			"id": "pay_pace_003",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_pace_003",
			"status": "captured"
		}])

		with patch("slcm.pace.web_form.pace_application_form.pace_application_form._pace_portal_user_owns_application", return_value=True):
			FeeService.reconcile_pending_payments()

		self.assertEqual(frappe.db.get_value("PACE Applicant Fee Assignment", afa.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("PACE Application", papp.name, "status"), "Completed")
		receipts = frappe.get_all("PACE Receipt", filters={"pace_application": papp.name, "fee_type": "Application Fee"})
		self.assertEqual(len(receipts), 1)

	def test_duplicate_verify_calls(self):
		"""TC-PACE-004: Duplicate Verify Calls (run 5 times)"""
		papp = self.create_pace_application()
		afa = self.create_pace_applicant_fee_assignment(papp.name, fee_type="Application Fee", amount=1000)
		pr = self.create_payment_request("PACE Applicant Fee Assignment", afa.name, "order_pace_004", amount=1000)

		self.mock_razorpay(payment_data={
			"id": "pay_pace_004",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_pace_004",
			"status": "captured"
		})
		self.mock_signature_verification()

		for _ in range(5):
			with patch("slcm.pace.web_form.pace_application_form.pace_application_form._pace_portal_user_owns_application", return_value=True):
				res = verify_pace_payment_signature(
					razorpay_payment_id="pay_pace_004",
					razorpay_order_id="order_pace_004",
					razorpay_signature="sig",
					assignment_name=afa.name
				)
			self.assertEqual(res.get("status"), "success")

		receipts = frappe.get_all("PACE Receipt", filters={"pace_application": papp.name, "fee_type": "Application Fee"})
		self.assertEqual(len(receipts), 1)

	def test_invalid_signature(self):
		"""TC-PACE-005: Invalid Signature fails verification"""
		papp = self.create_pace_application()
		afa = self.create_pace_applicant_fee_assignment(papp.name, fee_type="Application Fee", amount=1000)
		pr = self.create_payment_request("PACE Applicant Fee Assignment", afa.name, "order_pace_005", amount=1000)

		# Patch signature verification to raise signature mismatch
		with patch("payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.RazorpaySettings.verify_signature", side_effect=Exception("Signature mismatch")), \
			 patch("slcm.pace.web_form.pace_application_form.pace_application_form._pace_portal_user_owns_application", return_value=True):
			res = verify_pace_payment_signature(
				razorpay_payment_id="pay_pace_005",
				razorpay_order_id="order_pace_005",
				razorpay_signature="sig",
				assignment_name=afa.name
			)

		self.assertEqual(res.get("status"), "failed")
		self.assertNotEqual(frappe.db.get_value("PACE Applicant Fee Assignment", afa.name, "status"), "Paid")

	def test_order_ownership(self):
		"""TC-PACE-006: Order Ownership Attack is rejected"""
		papp_a = self.create_pace_application(email="a@example.com")
		afa_a = self.create_pace_applicant_fee_assignment(papp_a.name, fee_type="Application Fee", amount=1000)

		papp_b = self.create_pace_application(email="b@example.com")
		afa_b = self.create_pace_applicant_fee_assignment(papp_b.name, fee_type="Application Fee", amount=1000)
		pr_b = self.create_payment_request("PACE Applicant Fee Assignment", afa_b.name, "order_pace_b_006", amount=1000)

		self.mock_razorpay(payment_data={
			"id": "pay_pace_b_006",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_pace_b_006",
			"status": "captured"
		})
		self.mock_signature_verification()

		# Applicant A attempts verification using B's Order ID
		with patch("slcm.pace.web_form.pace_application_form.pace_application_form._pace_portal_user_owns_application", return_value=True):
			res = verify_pace_payment_signature(
				razorpay_payment_id="pay_pace_b_006",
				razorpay_order_id="order_pace_b_006",
				razorpay_signature="sig",
				assignment_name=afa_a.name
			)

		self.assertEqual(res.get("status"), "failed")
		self.assertNotEqual(frappe.db.get_value("PACE Applicant Fee Assignment", afa_a.name, "status"), "Paid")

	def test_amount_mismatch(self):
		"""TC-PACE-007: Amount Mismatch is rejected"""
		papp = self.create_pace_application()
		afa = self.create_pace_applicant_fee_assignment(papp.name, fee_type="Application Fee", amount=1000)
		pr = self.create_payment_request("PACE Applicant Fee Assignment", afa.name, "order_pace_007", amount=1000)

		self.mock_razorpay(payment_data={
			"id": "pay_pace_007",
			"amount": 100, # 1 INR
			"currency": "INR",
			"order_id": "order_pace_007",
			"status": "captured"
		})
		self.mock_signature_verification()

		with patch("slcm.pace.web_form.pace_application_form.pace_application_form._pace_portal_user_owns_application", return_value=True):
			res = verify_pace_payment_signature(
				razorpay_payment_id="pay_pace_007",
				razorpay_order_id="order_pace_007",
				razorpay_signature="sig",
				assignment_name=afa.name
			)

		self.assertEqual(res.get("status"), "failed")
		self.assertNotEqual(frappe.db.get_value("PACE Applicant Fee Assignment", afa.name, "status"), "Paid")

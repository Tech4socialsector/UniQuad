# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from unittest.mock import patch
from slcm.tests.payment.payment_test_base import PaymentTestBase
from slcm.api.service.fee_service import FeeService
from slcm.api.razorpay_webhook import handle_razorpay_webhook
import json

class TestApplicantPayments(PaymentTestBase):
	def test_successful_payment(self):
		"""TC-AF-001: Successful Payment of Applicant Application Fee"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_af_001", amount=1000)

		self.mock_razorpay(payment_data={
			"id": "pay_af_001",
			"amount": 100000, # 1000 INR
			"currency": "INR",
			"order_id": "order_af_001",
			"status": "captured"
		})
		self.mock_signature_verification()

		res = FeeService.verify_application_fee_payment(
			razorpay_payment_id="pay_af_001",
			razorpay_order_id="order_af_001",
			razorpay_signature="sig",
			applicant_name=app.name
		)

		self.assertEqual(res.get("status"), "success")
		
		# Verify updates
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Paid")
		
		# Verify receipt generated
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"applicant": app.name, "docstatus": ["<", 2]})
		self.assertEqual(len(receipts), 1)

	def test_user_closes_browser(self):
		"""TC-AF-002: User Closes Browser after Payment (Webhook captures it)"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_af_002", amount=1000)

		# Simulate webhook payment.captured payload
		payload = {
			"event": "payment.captured",
			"payload": {
				"payment": {
					"entity": {
						"id": "pay_af_002",
						"amount": 100000,
						"currency": "INR",
						"order_id": "order_af_002",
						"status": "captured"
					}
				}
			}
		}

		class MockRequest:
			def __init__(self, data):
				self.data = data
			def get_data(self):
				return self.data

		orig_req = getattr(frappe.local, "request", None)
		frappe.local.request = MockRequest(json.dumps(payload).encode("utf-8"))

		try:
			with patch("frappe.get_request_header", side_effect=self.sign_webhook_request):
				handle_razorpay_webhook()
		finally:
			if orig_req:
				frappe.local.request = orig_req
			else:
				delattr(frappe.local, "request")

		# Verify updates
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Paid")
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"applicant": app.name, "docstatus": ["<", 2]})
		self.assertEqual(len(receipts), 1)

	def test_scheduler_recovery(self):
		"""TC-AF-003: Scheduler Recovery (pending payment reconciled)"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_af_003", amount=1000)

		# Modify modified time of Payment Request using direct SQL to bypass hooks
		from frappe.utils import add_to_date
		old_time = add_to_date(frappe.utils.now_datetime(), minutes=-20)
		frappe.db.sql("UPDATE `tabSLCM Payment Request` SET modified = %s WHERE name = %s", (old_time, pr.name))
		frappe.db.commit()

		self.mock_razorpay(payments_list=[{
			"id": "pay_af_003",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_af_003",
			"status": "captured"
		}])

		FeeService.reconcile_pending_payments()

		# Verify updates
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Paid")
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"applicant": app.name, "docstatus": ["<", 2]})
		self.assertEqual(len(receipts), 1)

	def test_failed_payment(self):
		"""TC-AF-004: Failed Payment at gateway"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_af_004", amount=1000)

		self.mock_razorpay(payment_data={
			"id": "pay_af_004",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_af_004",
			"status": "failed",
			"error_description": "Insufficent Funds"
		})
		self.mock_signature_verification()

		res = FeeService.verify_application_fee_payment(
			razorpay_payment_id="pay_af_004",
			razorpay_order_id="order_af_004",
			razorpay_signature="sig",
			applicant_name=app.name
		)

		self.assertEqual(res.get("status"), "failed")
		self.assertNotEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Paid")

	def test_duplicate_verify_call(self):
		"""TC-AF-005: Duplicate verify call does not create double receipts"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_af_005", amount=1000)

		self.mock_razorpay(payment_data={
			"id": "pay_af_005",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_af_005",
			"status": "captured"
		})
		self.mock_signature_verification()

		# Call 1
		res1 = FeeService.verify_application_fee_payment(
			razorpay_payment_id="pay_af_005",
			razorpay_order_id="order_af_005",
			razorpay_signature="sig",
			applicant_name=app.name
		)
		self.assertEqual(res1.get("status"), "success")

		# Call 2
		res2 = FeeService.verify_application_fee_payment(
			razorpay_payment_id="pay_af_005",
			razorpay_order_id="order_af_005",
			razorpay_signature="sig",
			applicant_name=app.name
		)
		self.assertEqual(res2.get("status"), "success")

		# Verify exactly one receipt exists
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"applicant": app.name, "docstatus": ["<", 2]})
		self.assertEqual(len(receipts), 1)

	def test_tampered_amount(self):
		"""TC-AF-006: Tampered Amount Attack is rejected"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_af_006", amount=1000)

		# Razorpay payment amount is tampered to 1 INR (100 paise) instead of 1000 INR
		self.mock_razorpay(payment_data={
			"id": "pay_af_006",
			"amount": 100, # 1 INR
			"currency": "INR",
			"order_id": "order_af_006",
			"status": "captured"
		})
		self.mock_signature_verification()

		res = FeeService.verify_application_fee_payment(
			razorpay_payment_id="pay_af_006",
			razorpay_order_id="order_af_006",
			razorpay_signature="sig",
			applicant_name=app.name
		)

		self.assertEqual(res.get("status"), "failed")
		self.assertNotEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Paid")

	def test_foreign_order(self):
		"""TC-AF-007: Foreign Order Attack (Applicant A verifying with Order of Applicant B)"""
		app_a = self.create_applicant(name_prefix="APP-A", email="a@example.com", amount=1000)
		app_b = self.create_applicant(name_prefix="APP-B", email="b@example.com", amount=1000)

		pr_b = self.create_payment_request("Applicant", app_b.name, "order_b_007", amount=1000)

		self.mock_razorpay(payment_data={
			"id": "pay_b_007",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_b_007",
			"status": "captured"
		})
		self.mock_signature_verification()

		# Applicant A attempts verification using Applicant B's Order ID
		res = FeeService.verify_application_fee_payment(
			razorpay_payment_id="pay_b_007",
			razorpay_order_id="order_b_007",
			razorpay_signature="sig",
			applicant_name=app_a.name
		)

		self.assertEqual(res.get("status"), "failed")
		self.assertNotEqual(frappe.db.get_value("Applicant", app_a.name, "application_fee_status"), "Paid")

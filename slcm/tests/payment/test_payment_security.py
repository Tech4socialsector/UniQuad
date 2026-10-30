# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from unittest.mock import patch
from slcm.tests.payment.payment_test_base import PaymentTestBase
from slcm.api.service.fee_service import FeeService
from slcm.pace.web_form.pace_application_form.pace_application_form import verify_pace_payment_signature
from slcm.api.razorpay_webhook import handle_razorpay_webhook
import json

class TestPaymentSecurity(PaymentTestBase):
	def test_wrong_signature(self):
		"""SEC-001: Wrong Signature Rejected"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_sec_001", amount=1000)

		self.mock_razorpay(payment_data={
			"id": "pay_sec_001",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_sec_001",
			"status": "captured"
		})

		# Patch signature check to raise signature mismatch error
		with patch("payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.RazorpaySettings.verify_signature", side_effect=Exception("Signature verification failed")):
			res = FeeService.verify_application_fee_payment(
				razorpay_payment_id="pay_sec_001",
				razorpay_order_id="order_sec_001",
				razorpay_signature="wrong_sig",
				applicant_name=app.name
			)

		self.assertEqual(res.get("status"), "failed")
		self.assertNotEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Paid")

	def test_wrong_order_id(self):
		"""SEC-002: Wrong Order ID Rejected"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_sec_002", amount=1000)

		self.mock_razorpay(payment_data={
			"id": "pay_sec_002",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_wrong_002",
			"status": "captured"
		})
		self.mock_signature_verification()

		# Pass an order ID that doesn't match the Payment Request
		res = FeeService.verify_application_fee_payment(
			razorpay_payment_id="pay_sec_002",
			razorpay_order_id="order_wrong_002",
			razorpay_signature="sig",
			applicant_name=app.name
		)

		self.assertEqual(res.get("status"), "failed")
		self.assertNotEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Paid")

	def test_wrong_amount(self):
		"""SEC-003: Wrong Amount Rejected"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_sec_003", amount=1000)

		# Amount returned by Razorpay is 50 INR (5000 paise) instead of 1000 INR
		self.mock_razorpay(payment_data={
			"id": "pay_sec_003",
			"amount": 5000,
			"currency": "INR",
			"order_id": "order_sec_003",
			"status": "captured"
		})
		self.mock_signature_verification()

		res = FeeService.verify_application_fee_payment(
			razorpay_payment_id="pay_sec_003",
			razorpay_order_id="order_sec_003",
			razorpay_signature="sig",
			applicant_name=app.name
		)

		self.assertEqual(res.get("status"), "failed")
		self.assertNotEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Paid")

	def test_wrong_currency(self):
		"""SEC-004: Wrong Currency Rejected"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_sec_004", amount=1000)

		self.mock_razorpay(payment_data={
			"id": "pay_sec_004",
			"amount": 100000,
			"currency": "USD", # Mismatch
			"order_id": "order_sec_004",
			"status": "captured"
		})
		self.mock_signature_verification()

		res = FeeService.verify_application_fee_payment(
			razorpay_payment_id="pay_sec_004",
			razorpay_order_id="order_sec_004",
			razorpay_signature="sig",
			applicant_name=app.name
		)

		self.assertEqual(res.get("status"), "failed")
		self.assertNotEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Paid")

	def test_captured_status_missing(self):
		"""SEC-005: Missing Captured Status Rejected (status = 'authorized')"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_sec_005", amount=1000)

		self.mock_razorpay(payment_data={
			"id": "pay_sec_005",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_sec_005",
			"status": "authorized" # authorized but not captured
		})
		self.mock_signature_verification()

		res = FeeService.verify_application_fee_payment(
			razorpay_payment_id="pay_sec_005",
			razorpay_order_id="order_sec_005",
			razorpay_signature="sig",
			applicant_name=app.name
		)

		self.assertEqual(res.get("status"), "failed")
		self.assertNotEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Paid")

	def test_webhook_replay(self):
		"""SEC-006: Webhook Replay Attack (same webhook 20 times)"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_sec_006", amount=1000)

		payload = {
			"event": "payment.captured",
			"payload": {
				"payment": {
					"entity": {
						"id": "pay_sec_006",
						"amount": 100000,
						"currency": "INR",
						"order_id": "order_sec_006",
						"status": "captured"
					}
				}
			}
		}

		# Send same webhook 20 times
		for _ in range(20):
			with patch("frappe.request.get_data", return_value=json.dumps(payload).encode("utf-8")), \
				 patch("frappe.get_request_header", side_effect=self.sign_webhook_request):
				handle_razorpay_webhook()

		# Verify exactly one receipt is generated
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"applicant": app.name, "docstatus": ["<", 2]})
		self.assertEqual(len(receipts), 1)

	def test_payment_request_ownership_attack(self):
		"""SEC-007: Payment Request Ownership Attack"""
		# Applicant A's Order
		app_a = self.create_applicant(name_prefix="APP-A", email="a@example.com", amount=1000)
		pr_a = self.create_payment_request("Applicant", app_a.name, "order_a_007", amount=1000)

		# Applicant B's Order
		app_b = self.create_applicant(name_prefix="APP-B", email="b@example.com", amount=1000)
		pr_b = self.create_payment_request("Applicant", app_b.name, "order_b_007", amount=1000)

		self.mock_razorpay(payment_data={
			"id": "pay_a_007",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_a_007",
			"status": "captured"
		})
		self.mock_signature_verification()

		# Applicant B attempts to verify his own record using A's Order ID
		res = FeeService.verify_application_fee_payment(
			razorpay_payment_id="pay_a_007",
			razorpay_order_id="order_a_007",
			razorpay_signature="sig",
			applicant_name=app_b.name
		)

		self.assertEqual(res.get("status"), "failed")
		self.assertNotEqual(frappe.db.get_value("Applicant", app_b.name, "application_fee_status"), "Paid")

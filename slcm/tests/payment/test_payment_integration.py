# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from unittest.mock import patch
import requests
from slcm.tests.payment.payment_test_base import PaymentTestBase
from slcm.api.service.fee_service import FeeService
from slcm.api.razorpay_webhook import handle_razorpay_webhook
import json

class TestPaymentIntegration(PaymentTestBase):
	def test_real_razorpay_order_creation(self):
		"""Layer 2: Real Razorpay Sandbox Order Creation integration"""
		# This uses the actual configured keys to hit the live Razorpay test server
		app = self.create_applicant(amount=1000)
		
		# Call real order creation logic
		res = FeeService.create_application_fee_razorpay_order(app.name)

		self.assertTrue(res.get("order_id"))
		self.assertTrue(str(res.get("order_id")).startswith("order_"))
		self.assertEqual(res.get("amount"), 100000) # paise
		self.assertEqual(res.get("currency"), "INR")

	def test_invalid_key_order_failure(self):
		"""RP-001: Invalid Razorpay Key - Order creation fails"""
		app = self.create_applicant(amount=1000)

		# Set invalid key
		orig_key = frappe.db.get_single_value("Razorpay Settings", "api_key")
		frappe.db.set_value("Razorpay Settings", "Razorpay Settings", "api_key", "rzp_test_invalidkey")
		frappe.db.commit()

		try:
			with self.assertRaises(Exception):
				FeeService.create_application_fee_razorpay_order(app.name)
		finally:
			# Restore key
			frappe.db.set_value("Razorpay Settings", "Razorpay Settings", "api_key", orig_key)
			frappe.db.commit()

	def test_invalid_webhook_signature(self):
		"""RP-002: Invalid Webhook Signature - Webhook rejected"""
		self._validate_webhook_signature = True
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_int_002", amount=1000)

		from frappe.utils.password import set_encrypted_password
		set_encrypted_password("Razorpay Settings", "Razorpay Settings", "test_webhook_sec", "webhook_secret")
		frappe.db.commit()

		payload = {
			"event": "payment.captured",
			"payload": {
				"payment": {
					"entity": {
						"id": "pay_int_002",
						"amount": 100000,
						"currency": "INR",
						"order_id": "order_int_002",
						"status": "captured"
					}
				}
			}
		}

		try:
			# Call webhook with a wrong/missing X-Razorpay-Signature header
			with patch("frappe.request.get_data", return_value=json.dumps(payload).encode("utf-8")), \
				 patch("frappe.get_request_header", return_value="wrong_signature_here"):
				
				# Signature validation error must raise PermissionError (frappe.throw throws PermissionError)
				with self.assertRaises(frappe.PermissionError):
					handle_razorpay_webhook()

			# Verify status is NOT Paid
			self.assertNotEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Paid")
		finally:
			self._validate_webhook_signature = False
			set_encrypted_password("Razorpay Settings", "Razorpay Settings", "dummy_secret", "webhook_secret")
			frappe.db.commit()

	def test_razorpay_api_timeout(self):
		"""RP-003: Razorpay API Timeout - No corruption, stays Requested"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_int_003", amount=1000)

		self.mock_signature_verification()

		# Mock requests to raise Timeout
		with patch("requests.sessions.Session.request", side_effect=requests.exceptions.Timeout("Connection Timeout")):
			res = FeeService.verify_application_fee_payment(
				razorpay_payment_id="pay_int_003",
				razorpay_order_id="order_int_003",
				razorpay_signature="sig",
				applicant_name=app.name
			)

		self.assertEqual(res.get("status"), "failed")
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Requested")

	def test_razorpay_api_500(self):
		"""RP-004: Razorpay API 500 - No payment completion"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_int_004", amount=1000)

		self.mock_signature_verification()

		# Mock response with 500 error
		mock_response = requests.Response()
		mock_response.status_code = 500
		mock_response.raise_for_status = lambda: requests.HTTPError("Internal Server Error", response=mock_response)

		with patch("requests.sessions.Session.request", return_value=mock_response):
			res = FeeService.verify_application_fee_payment(
				razorpay_payment_id="pay_int_004",
				razorpay_order_id="order_int_004",
				razorpay_signature="sig",
				applicant_name=app.name
			)

		self.assertEqual(res.get("status"), "failed")
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Requested")

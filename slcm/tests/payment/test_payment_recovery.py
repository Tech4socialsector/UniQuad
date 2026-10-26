# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from unittest.mock import patch
from slcm.tests.payment.payment_test_base import PaymentTestBase
from slcm.api.service.fee_service import FeeService
from slcm.api.razorpay_webhook import handle_razorpay_webhook
import json

class TestPaymentRecovery(PaymentTestBase):
	def test_browser_closed_webhook_recovery(self):
		"""Scenario 3: Browser Closes after payment - Webhook completes it"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_rec_001", amount=1000)

		payload = {
			"event": "payment.captured",
			"payload": {
				"payment": {
					"entity": {
						"id": "pay_rec_001",
						"amount": 100000,
						"currency": "INR",
						"order_id": "order_rec_001",
						"status": "captured"
					}
				}
			}
		}

		with patch("frappe.request.get_data", return_value=json.dumps(payload).encode("utf-8")), \
			 patch("frappe.get_request_header", side_effect=self.sign_webhook_request):
			handle_razorpay_webhook()

		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Paid")

	def test_webhook_down_scheduler_recovery(self):
		"""Scenario 1: Webhook fails/down - Scheduler recovers the pending payment"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_rec_002", amount=1000)

		# Make it older than 15 mins to hit scheduler cutoff
		from frappe.utils import add_to_date
		old_time = add_to_date(frappe.utils.now_datetime(), minutes=-20)
		frappe.db.sql("UPDATE `tabSLCM Payment Request` SET modified = %s WHERE name = %s", (old_time, pr.name))
		frappe.db.commit()

		self.mock_razorpay(payments_list=[{
			"id": "pay_rec_002",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_rec_002",
			"status": "captured"
		}])

		FeeService.reconcile_pending_payments()

		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Paid")

	def test_scheduler_safety_multiple_runs(self):
		"""SCH-001: Run scheduler 10 times - No duplicate completions/receipts"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_rec_003", amount=1000)

		# Trigger cutoff
		from frappe.utils import add_to_date
		old_time = add_to_date(frappe.utils.now_datetime(), minutes=-20)
		frappe.db.sql("UPDATE `tabSLCM Payment Request` SET modified = %s WHERE name = %s", (old_time, pr.name))
		frappe.db.commit()

		self.mock_razorpay(payments_list=[{
			"id": "pay_rec_003",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_rec_003",
			"status": "captured"
		}])

		for _ in range(10):
			FeeService.reconcile_pending_payments()

		# Exactly 1 receipt
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"applicant": app.name, "docstatus": ["<", 2]})
		self.assertEqual(len(receipts), 1)

	def test_scheduler_safety_after_completed(self):
		"""SCH-002: Run scheduler on already Paid request - No changes"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_rec_004", amount=1000)

		# Set status to Paid
		frappe.db.set_value("SLCM Payment Request", pr.name, "status", "Paid")
		frappe.db.set_value("Applicant", app.name, "application_fee_status", "Paid")
		frappe.db.commit()

		# Force cutoff
		from frappe.utils import add_to_date
		old_time = add_to_date(frappe.utils.now_datetime(), minutes=-20)
		frappe.db.sql("UPDATE `tabSLCM Payment Request` SET modified = %s WHERE name = %s", (old_time, pr.name))
		frappe.db.commit()

		self.mock_razorpay(payments_list=[{
			"id": "pay_rec_004",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_rec_004",
			"status": "captured"
		}])

		# Run scheduler
		FeeService.reconcile_pending_payments()

		# No new receipts or modifications
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"applicant": app.name, "docstatus": ["<", 2]})
		self.assertEqual(len(receipts), 0) # since we didn't call verification path, it stays at 0

	def test_scheduler_safety_authorized_only(self):
		"""SCH-003: Run scheduler on Authorized-only payment - No completion"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_rec_005", amount=1000)

		from frappe.utils import add_to_date
		old_time = add_to_date(frappe.utils.now_datetime(), minutes=-20)
		frappe.db.sql("UPDATE `tabSLCM Payment Request` SET modified = %s WHERE name = %s", (old_time, pr.name))
		frappe.db.commit()

		self.mock_razorpay(payments_list=[{
			"id": "pay_rec_005",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_rec_005",
			"status": "authorized" # authorized but not captured
		}])

		FeeService.reconcile_pending_payments()

		# Stays in Requested status
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Requested")
		self.assertEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Requested")

	def test_scheduler_safety_created_only(self):
		"""SCH-004: Run scheduler on Created-only (unattempted) payment - No completion"""
		app = self.create_applicant(amount=1000)
		pr = self.create_payment_request("Applicant", app.name, "order_rec_006", amount=1000)

		from frappe.utils import add_to_date
		old_time = add_to_date(frappe.utils.now_datetime(), minutes=-20)
		frappe.db.sql("UPDATE `tabSLCM Payment Request` SET modified = %s WHERE name = %s", (old_time, pr.name))
		frappe.db.commit()

		self.mock_razorpay(payments_list=[{
			"id": "pay_rec_006",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_rec_006",
			"status": "created" # order created, not attempted
		}])

		FeeService.reconcile_pending_payments()

		# Stays in Requested status
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Requested")
		self.assertEqual(frappe.db.get_value("Applicant", app.name, "application_fee_status"), "Requested")

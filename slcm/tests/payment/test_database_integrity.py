# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from unittest.mock import patch
from slcm.tests.payment.payment_test_base import PaymentTestBase
from slcm.api.service.fee_service import FeeService

class TestDatabaseIntegrity(PaymentTestBase):
	def test_status_synchronization(self):
		"""DI-001 & DI-005: Successful payment updates PR and synchronization of status"""
		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=5000)
		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=5000)
		pr = self.create_payment_request("Offer Letter", offer.name, "order_di_001", amount=5000)

		self.mock_razorpay(payment_data={
			"id": "pay_di_001",
			"amount": 500000,
			"currency": "INR",
			"order_id": "order_di_001",
			"status": "captured"
		})
		self.mock_signature_verification()

		FeeService.verify_offer_payment(
			razorpay_payment_id="pay_di_001",
			razorpay_order_id="order_di_001",
			razorpay_signature="sig",
			offer_name=offer.name
		)

		# DI-001: Payment Request status == Paid, gateway_status == captured
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "gateway_status"), "captured")

		# DI-005: Reference document matches
		self.assertEqual(frappe.db.get_value("Offer Letter", offer.name, "status"), "Full Fee Paid")
		self.assertEqual(frappe.db.get_value("Applicant Fee Assignment", afa.name, "status"), "Paid")

	def test_receipt_count(self):
		"""DI-002: Successful payment creates exactly 1 receipt"""
		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=5000)
		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=5000)
		pr = self.create_payment_request("Offer Letter", offer.name, "order_di_002", amount=5000)

		self.mock_razorpay(payment_data={
			"id": "pay_di_002",
			"amount": 500000,
			"currency": "INR",
			"order_id": "order_di_002",
			"status": "captured"
		})
		self.mock_signature_verification()

		FeeService.verify_offer_payment(
			razorpay_payment_id="pay_di_002",
			razorpay_order_id="order_di_002",
			razorpay_signature="sig",
			offer_name=offer.name
		)

		# Assert DI-002: count(receipts) == 1
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"offer_letter": offer.name})
		self.assertEqual(len(receipts), 1)

	def test_no_duplicate_razorpay_payment_id(self):
		"""DI-003: No duplicate razorpay_payment_id allowed in DB"""
		app_a = self.create_applicant(name_prefix="APP-A", email="a@example.com", amount=1000)
		offer_a = self.create_offer_letter(app_a.name, amount=5000)
		afa_a = self.create_applicant_fee_assignment(offer_a.name, app_a.name, amount=5000)
		pr_a = self.create_payment_request("Offer Letter", offer_a.name, "order_di_a", amount=5000)

		# Make A Paid
		frappe.db.set_value("SLCM Payment Request", pr_a.name, {
			"status": "Paid",
			"gateway_status": "captured",
			"transaction_id": "pay_di_dup"
		})
		frappe.db.commit()

		# Setup B with same transaction_id
		app_b = self.create_applicant(name_prefix="APP-B", email="b@example.com", amount=1000)
		offer_b = self.create_offer_letter(app_b.name, amount=5000)
		afa_b = self.create_applicant_fee_assignment(offer_b.name, app_b.name, amount=5000)
		pr_b = self.create_payment_request("Offer Letter", offer_b.name, "order_di_b", amount=5000)

		self.mock_razorpay(payment_data={
			"id": "pay_di_dup", # duplicate payment id
			"amount": 500000,
			"currency": "INR",
			"order_id": "order_di_b",
			"status": "captured"
		})
		self.mock_signature_verification()

		# Verify B with duplicate payment ID should fail, or at least we assert no two Paid PRs have same transaction_id
		res = FeeService.verify_offer_payment(
			razorpay_payment_id="pay_di_dup",
			razorpay_order_id="order_di_b",
			razorpay_signature="sig",
			offer_name=offer_b.name
		)

		self.assertEqual(res.get("status"), "failed")
		duplicates = frappe.db.sql("""
			SELECT transaction_id, COUNT(*)
			FROM `tabSLCM Payment Request`
			WHERE status = 'Paid' AND transaction_id = 'pay_di_dup'
			GROUP BY transaction_id
		""")
		if duplicates:
			self.assertLessEqual(duplicates[0][1], 1, "Duplicate Paid transaction_id detected in database!")

	def test_no_duplicate_receipt_numbers(self):
		"""DI-004: No duplicate receipt numbers exist"""
		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=5000)
		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=5000)
		# Receipts are only generated for a paid assignment.
		frappe.db.set_value("Applicant Fee Assignment", afa.name, "status", "Paid")

		# Generate receipt 1
		r1 = FeeService.generate_receipt(offer, "pay_di_r1", "Online")
		self.assertTrue(r1)

		# Generate receipt 2 for same transaction should return the existing one or fail, but not create a new one
		r2 = FeeService.generate_receipt(offer, "pay_di_r1", "Online")
		self.assertEqual(r1, r2)

		# Ensure only one receipt is in DB
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"offer_letter": offer.name})
		self.assertEqual(len(receipts), 1)

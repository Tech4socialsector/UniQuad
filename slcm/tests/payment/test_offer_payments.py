# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from slcm.tests.payment.payment_test_base import PaymentTestBase
from slcm.api.service.fee_service import FeeService

class TestOfferPayments(PaymentTestBase):
	def test_successful_payment(self):
		"""TC-OL-001: Successful Payment of Offer Letter Admission Fee"""
		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=5000)
		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=5000)
		pr = self.create_payment_request("Offer Letter", offer.name, "order_ol_001", amount=5000)

		self.mock_razorpay(payment_data={
			"id": "pay_ol_001",
			"amount": 500000,
			"currency": "INR",
			"order_id": "order_ol_001",
			"status": "captured"
		})
		self.mock_signature_verification()

		res = FeeService.verify_offer_payment(
			razorpay_payment_id="pay_ol_001",
			razorpay_order_id="order_ol_001",
			razorpay_signature="sig",
			offer_name=offer.name
		)

		self.assertEqual(res.get("status"), "success")
		self.assertEqual(frappe.db.get_value("Offer Letter", offer.name, "status"), "Full Fee Paid")
		self.assertEqual(frappe.db.get_value("Applicant Fee Assignment", afa.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Paid")
		
		# Verify receipt exists
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"offer_letter": offer.name, "docstatus": 0})
		self.assertEqual(len(receipts), 1)

	def test_webhook_only(self):
		"""TC-OL-002: Payment Completed through Webhook Only"""
		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=5000)
		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=5000)
		pr = self.create_payment_request("Offer Letter", offer.name, "order_ol_002", amount=5000)

		payload = {
			"event": "payment.captured",
			"payload": {
				"payment": {
					"entity": {
						"id": "pay_ol_002",
						"amount": 500000,
						"currency": "INR",
						"order_id": "order_ol_002",
						"status": "captured"
					}
				}
			}
		}

		self.dispatch_razorpay_webhook(payload)

		self.assertEqual(frappe.db.get_value("Offer Letter", offer.name, "status"), "Full Fee Paid")
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"offer_letter": offer.name, "docstatus": 0})
		self.assertEqual(len(receipts), 1)

	def test_scheduler_only(self):
		"""TC-OL-003: Payment Completed through Scheduler Only"""
		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=5000)
		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=5000)
		pr = self.create_payment_request("Offer Letter", offer.name, "order_ol_003", amount=5000)

		# Modify modified time of Payment Request to trigger reconciliation
		from frappe.utils import add_to_date
		old_time = add_to_date(frappe.utils.now_datetime(), minutes=-20)
		frappe.db.sql("UPDATE `tabSLCM Payment Request` SET modified = %s WHERE name = %s", (old_time, pr.name))
		frappe.db.commit()

		self.mock_razorpay(payments_list=[{
			"id": "pay_ol_003",
			"amount": 500000,
			"currency": "INR",
			"order_id": "order_ol_003",
			"status": "captured"
		}])

		FeeService.reconcile_pending_payments()

		self.assertEqual(frappe.db.get_value("Offer Letter", offer.name, "status"), "Full Fee Paid")
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"offer_letter": offer.name, "docstatus": 0})
		self.assertEqual(len(receipts), 1)

	def test_duplicate_payment_attempt(self):
		"""TC-OL-004: Duplicate Payment Attempt is blocked"""
		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=5000)
		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=5000)
		pr = self.create_payment_request("Offer Letter", offer.name, "order_ol_004", amount=5000)

		# Set Offer and Assignment as Paid
		frappe.db.set_value("Offer Letter", offer.name, "status", "Full Fee Paid")
		frappe.db.set_value("Applicant Fee Assignment", afa.name, "status", "Paid")
		frappe.db.commit()

		# Second payment attempt using verify_offer_payment should return success early without double-processing
		self.mock_razorpay(payment_data={
			"id": "pay_ol_004",
			"amount": 500000,
			"currency": "INR",
			"order_id": "order_ol_004",
			"status": "captured"
		})
		self.mock_signature_verification()

		res = FeeService.verify_offer_payment(
			razorpay_payment_id="pay_ol_004",
			razorpay_order_id="order_ol_004",
			razorpay_signature="sig",
			offer_name=offer.name
		)

		self.assertEqual(res.get("status"), "success")

	def test_duplicate_webhook(self):
		"""TC-OL-005: Duplicate Webhook Delivery (captured twice)"""
		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=5000)
		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=5000)
		pr = self.create_payment_request("Offer Letter", offer.name, "order_ol_005", amount=5000)

		payload = {
			"event": "payment.captured",
			"payload": {
				"payment": {
					"entity": {
						"id": "pay_ol_005",
						"amount": 500000,
						"currency": "INR",
						"order_id": "order_ol_005",
						"status": "captured"
					}
				}
			}
		}

		self.dispatch_razorpay_webhook(payload)
		self.dispatch_razorpay_webhook(payload)

		# Exactly one receipt exists
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"offer_letter": offer.name, "docstatus": 0})
		self.assertEqual(len(receipts), 1)

	def test_duplicate_scheduler(self):
		"""TC-OL-006: Duplicate Scheduler Run (reconcile 10 times)"""
		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=5000)
		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=5000)
		pr = self.create_payment_request("Offer Letter", offer.name, "order_ol_006", amount=5000)

		from frappe.utils import add_to_date
		old_time = add_to_date(frappe.utils.now_datetime(), minutes=-20)
		frappe.db.sql("UPDATE `tabSLCM Payment Request` SET modified = %s WHERE name = %s", (old_time, pr.name))
		frappe.db.commit()

		self.mock_razorpay(payments_list=[{
			"id": "pay_ol_006",
			"amount": 500000,
			"currency": "INR",
			"order_id": "order_ol_006",
			"status": "captured"
		}])

		for _ in range(10):
			print("Running reconcile_pending_payments")
			FeeService.reconcile_pending_payments()

		# Verify single receipt
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"offer_letter": offer.name, "docstatus": 0})
		self.assertEqual(len(receipts), 1)

	def test_scholarship_scenario(self):
		"""TC-OL-007: Scholarship Scenario (payable amount = fee total - scholarship)"""
		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=5000)

		# Modify AFA to apply a scholarship
		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=5000)
		frappe.db.set_value("Applicant Fee Assignment", afa.name, {
			"scholarship_applied": 1,
			"scholarship_amount": 1500,
			"total_amount": 5000,
			"final_payable_amount": 3500
		})
		frappe.db.set_value("Offer Letter", offer.name, "payable_amount", 3500, update_modified=False)
		offer.payable_amount = 3500

		# Create PR reflecting the scholarship-adjusted amount
		pr = self.create_payment_request("Offer Letter", offer.name, "order_ol_007", amount=3500)

		self.mock_razorpay(payment_data={
			"id": "pay_ol_007",
			"amount": 350000, # 3500 INR
			"currency": "INR",
			"order_id": "order_ol_007",
			"status": "captured"
		})
		self.mock_signature_verification()

		res = FeeService.verify_offer_payment(
			razorpay_payment_id="pay_ol_007",
			razorpay_order_id="order_ol_007",
			razorpay_signature="sig",
			offer_name=offer.name
		)

		self.assertEqual(res.get("status"), "success")
		self.assertEqual(frappe.db.get_value("Offer Letter", offer.name, "status"), "Full Fee Paid")
		self.assertEqual(frappe.db.get_value("Applicant Fee Assignment", afa.name, "status"), "Paid")

		# Verify Receipt net amount matches the adjusted payable amount
		receipt_name = frappe.db.get_value("Applicant Payment Receipt", {"offer_letter": offer.name, "docstatus": 0})
		self.assertTrue(receipt_name)
		receipt = frappe.get_doc("Applicant Payment Receipt", receipt_name)
		
		self.assertEqual(receipt.scholarship_amount, 1500)
		self.assertEqual(receipt.net_amount, 3500)

	def test_confirmation_to_admission_fee_transition(self):
		"""TC-OL-008: Verify successful Confirmation Fee payment generates Admission Fee assignment"""
		# Setup Fee Components & Structure
		tuition = self.create_fee_component("Tuition Fee", is_accommodation_fee=0)
		fs = self.create_fee_structure("FS-CONF-TEST", components=[(tuition, 150000)], confirmation_fee=50000)

		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=150000)
		frappe.db.set_value("Offer Letter", offer.name, "fee_structure", fs.name)
		
		# Initial Assignment: Confirmation Fee
		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=50000)
		frappe.db.set_value("Applicant Fee Assignment", afa.name, "fee_type", "Confirmation Fee")

		pr = self.create_payment_request("Offer Letter", offer.name, "order_conf_001", amount=50000)

		self.mock_razorpay(payment_data={
			"id": "pay_conf_001",
			"amount": 5000000, # 50000 INR
			"currency": "INR",
			"order_id": "order_conf_001",
			"status": "captured"
		})
		self.mock_signature_verification()

		res = FeeService.verify_offer_payment(
			razorpay_payment_id="pay_conf_001",
			razorpay_order_id="order_conf_001",
			razorpay_signature="sig",
			offer_name=offer.name
		)

		self.assertEqual(res.get("status"), "success")
		self.assertEqual(frappe.db.get_value("Offer Letter", offer.name, "status"), "Confirmation Fee Paid")
		self.assertEqual(frappe.db.get_value("Applicant Fee Assignment", afa.name, "status"), "Paid")

		# Check if Admission Fee Assignment was generated
		new_afa_name = frappe.db.get_value("Applicant Fee Assignment", {
			"offer_letter": offer.name, 
			"fee_type": "Admission Fee",
			"status": "Assigned"
		})
		self.assertIsNotNone(new_afa_name, "Admission Fee Assignment should be generated after Confirmation Fee is paid")
		new_afa = frappe.get_doc("Applicant Fee Assignment", new_afa_name)
		
		# Total was 150000, components generated should reflect tuition
		has_tuition = any(c.fee_component == tuition for c in new_afa.fee_components)
		self.assertTrue(has_tuition, "Tuition component should be copied to the new Admission Fee assignment")

	def test_accommodation_fee_inclusion(self):
		"""TC-OL-009: Verify Accommodation Fee is included when needs_accommodation is Yes"""
		tuition = self.create_fee_component("Tuition Fee", is_accommodation_fee=0)
		acc_fee = self.create_fee_component("Hostel Fee", is_accommodation_fee=1)
		fs = self.create_fee_structure("FS-ACC-INCL", components=[(tuition, 150000), (acc_fee, 50000)], confirmation_fee=50000)

		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=200000)
		frappe.db.set_value("Offer Letter", offer.name, "fee_structure", fs.name)
		frappe.db.set_value("Offer Letter", offer.name, "needs_accommodation", "Yes")

		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=50000)
		frappe.db.set_value("Applicant Fee Assignment", afa.name, "fee_type", "Confirmation Fee")
		pr = self.create_payment_request("Offer Letter", offer.name, "order_acc_yes", amount=50000)

		self.mock_razorpay(payment_data={
			"id": "pay_acc_yes", "amount": 5000000, "currency": "INR", "order_id": "order_acc_yes", "status": "captured"
		})
		self.mock_signature_verification()

		res = FeeService.verify_offer_payment("pay_acc_yes", "order_acc_yes", "sig", offer.name)
		self.assertEqual(res.get("status"), "success")

		new_afa_name = frappe.db.get_value("Applicant Fee Assignment", {"offer_letter": offer.name, "fee_type": "Admission Fee"})
		new_afa = frappe.get_doc("Applicant Fee Assignment", new_afa_name)
		
		has_acc = any(c.fee_component == acc_fee for c in new_afa.fee_components)
		self.assertTrue(has_acc, "Accommodation fee component should be INCLUDED when needs_accommodation is 'Yes'")

	def test_accommodation_fee_exclusion(self):
		"""TC-OL-010: Verify Accommodation Fee is excluded when needs_accommodation is No"""
		tuition = self.create_fee_component("Tuition Fee", is_accommodation_fee=0)
		acc_fee = self.create_fee_component("Hostel Fee", is_accommodation_fee=1)
		fs = self.create_fee_structure("FS-ACC-EXCL", components=[(tuition, 150000), (acc_fee, 50000)], confirmation_fee=50000)

		app = self.create_applicant(amount=1000)
		offer = self.create_offer_letter(app.name, amount=200000)
		frappe.db.set_value("Offer Letter", offer.name, "fee_structure", fs.name)
		frappe.db.set_value("Offer Letter", offer.name, "needs_accommodation", "No")

		afa = self.create_applicant_fee_assignment(offer.name, app.name, amount=50000)
		frappe.db.set_value("Applicant Fee Assignment", afa.name, "fee_type", "Confirmation Fee")
		pr = self.create_payment_request("Offer Letter", offer.name, "order_acc_no", amount=50000)

		self.mock_razorpay(payment_data={
			"id": "pay_acc_no", "amount": 5000000, "currency": "INR", "order_id": "order_acc_no", "status": "captured"
		})
		self.mock_signature_verification()

		res = FeeService.verify_offer_payment("pay_acc_no", "order_acc_no", "sig", offer.name)
		self.assertEqual(res.get("status"), "success")

		new_afa_name = frappe.db.get_value("Applicant Fee Assignment", {"offer_letter": offer.name, "fee_type": "Admission Fee"})
		new_afa = frappe.get_doc("Applicant Fee Assignment", new_afa_name)
		
		has_acc = any(c.fee_component == acc_fee for c in new_afa.fee_components)
		self.assertFalse(has_acc, "Accommodation fee component should be EXCLUDED when needs_accommodation is 'No'")


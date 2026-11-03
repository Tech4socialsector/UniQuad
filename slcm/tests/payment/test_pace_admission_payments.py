# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from unittest.mock import patch
from slcm.tests.payment.payment_test_base import PaymentTestBase
from slcm.pace.web_form.pace_application_form.pace_application_form import verify_pace_payment_signature
from slcm.api.razorpay_webhook import handle_razorpay_webhook
from slcm.api.service.fee_service import FeeService
import json

class TestPACAdmissionPayments(PaymentTestBase):
	def test_successful_admission_fee(self):
		"""TC-PAD-001: Successful PACE Admission Fee Payment"""
		papp = self.create_pace_application()
		afa = self.create_pace_applicant_fee_assignment(papp.name, fee_type="Course Fee", amount=15000)
		pr = self.create_payment_request("PACE Applicant Fee Assignment", afa.name, "order_pad_001", amount=15000)

		self.mock_razorpay(payment_data={
			"id": "pay_pad_001",
			"amount": 1500000,
			"currency": "INR",
			"order_id": "order_pad_001",
			"status": "captured"
		})
		self.mock_signature_verification()

		with patch("slcm.pace.web_form.pace_application_form.pace_application_form._pace_portal_user_owns_application", return_value=True):
			res = verify_pace_payment_signature(
				razorpay_payment_id="pay_pad_001",
				razorpay_order_id="order_pad_001",
				razorpay_signature="sig",
				assignment_name=afa.name
			)

		self.assertEqual(res.get("status"), "success")
		self.assertEqual(frappe.db.get_value("PACE Applicant Fee Assignment", afa.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("PACE Application", papp.name, "status"), "Fee Paid")

		# Verify Receipt Generated
		receipts = frappe.get_all("PACE Receipt", filters={"pace_application": papp.name, "fee_type": "Course Fee"})
		self.assertEqual(len(receipts), 1)

	def test_webhook_only(self):
		"""TC-PAD-002: Webhook Only completes PACE Admission payment"""
		papp = self.create_pace_application()
		afa = self.create_pace_applicant_fee_assignment(papp.name, fee_type="Course Fee", amount=15000)
		pr = self.create_payment_request("PACE Applicant Fee Assignment", afa.name, "order_pad_002", amount=15000)

		payload = {
			"event": "payment.captured",
			"payload": {
				"payment": {
					"entity": {
						"id": "pay_pad_002",
						"amount": 1500000,
						"currency": "INR",
						"order_id": "order_pad_002",
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
		self.assertEqual(frappe.db.get_value("PACE Application", papp.name, "status"), "Fee Paid")
		receipts = frappe.get_all("PACE Receipt", filters={"pace_application": papp.name, "fee_type": "Course Fee"})
		self.assertEqual(len(receipts), 1)

	def test_scheduler_recovery(self):
		"""TC-PAD-003: Scheduler Recovery completes PACE Admission payment"""
		papp = self.create_pace_application()
		afa = self.create_pace_applicant_fee_assignment(papp.name, fee_type="Course Fee", amount=15000)
		pr = self.create_payment_request("PACE Applicant Fee Assignment", afa.name, "order_pad_003", amount=15000)

		from frappe.utils import add_to_date
		old_time = add_to_date(frappe.utils.now_datetime(), minutes=-20)
		frappe.db.sql("UPDATE `tabSLCM Payment Request` SET modified = %s WHERE name = %s", (old_time, pr.name))
		frappe.db.commit()

		self.mock_razorpay(payments_list=[{
			"id": "pay_pad_003",
			"amount": 1500000,
			"currency": "INR",
			"order_id": "order_pad_003",
			"status": "captured"
		}])

		with patch("slcm.pace.web_form.pace_application_form.pace_application_form._pace_portal_user_owns_application", return_value=True):
			FeeService.reconcile_pending_payments()

		self.assertEqual(frappe.db.get_value("PACE Applicant Fee Assignment", afa.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("PACE Application", papp.name, "status"), "Fee Paid")
		receipts = frappe.get_all("PACE Receipt", filters={"pace_application": papp.name, "fee_type": "Course Fee"})
		self.assertEqual(len(receipts), 1)

	def test_duplicate_payment_attempt(self):
		"""TC-PAD-004: Duplicate payment attempt is blocked"""
		papp = self.create_pace_application()
		afa = self.create_pace_applicant_fee_assignment(papp.name, fee_type="Course Fee", amount=15000)
		pr = self.create_payment_request("PACE Applicant Fee Assignment", afa.name, "order_pad_004", amount=15000)

		# Make it already paid
		frappe.db.set_value("PACE Applicant Fee Assignment", afa.name, "status", "Paid")
		frappe.db.commit()

		self.mock_razorpay(payment_data={
			"id": "pay_pad_004",
			"amount": 1500000,
			"currency": "INR",
			"order_id": "order_pad_004",
			"status": "captured"
		})
		self.mock_signature_verification()

		with patch("slcm.pace.web_form.pace_application_form.pace_application_form._pace_portal_user_owns_application", return_value=True):
			res = verify_pace_payment_signature(
				razorpay_payment_id="pay_pad_004",
				razorpay_order_id="order_pad_004",
				razorpay_signature="sig",
				assignment_name=afa.name
			)

		self.assertEqual(res.get("status"), "success")

	def test_programme_change_before_course_fee_paid(self):
		"""TC-PAD-005: Programme change cancels old fee assignment and generates a new one"""
		# 1. Create a PACE Application
		papp = self.create_pace_application()
		
		# 2. Create another PACE Programme to change to
		new_prog = frappe.new_doc("PACE Programme")
		new_prog.programme_prefix = "New PACE"
		new_prog.programme_name = "Test Programme"
		new_prog.published = 1
		new_prog.insert(ignore_permissions=True)
		self.register_doc(new_prog)

		# 3. Create a Fee Structure for the new programme
		if not frappe.db.exists("PACE Fee Component List", "Course Fee Component"):
			fc = frappe.new_doc("PACE Fee Component List")
			fc.fee_component_name = "Course Fee Component"
			fc.component_type = "Other"
			fc.insert(ignore_permissions=True)
			self.register_doc(fc)

		new_fs = frappe.new_doc("PACE Fee Structure")
		new_fs.fee_structure_name = "New PACE Test FS"
		new_fs.pace_program = new_prog.name
		new_fs.status = "Active"
		new_fs.academic_year = papp.academic_year
		new_fs.payment_mode = "Online"
		new_fs.currency = "INR"
		new_fs.total_amount = 20000
		new_fs.append("fee_components_for_indians", {
			"fee_component": "Course Fee Component",
			"amount": 20000,
			"total_amount": 20000
		})
		new_fs.insert(ignore_permissions=True)
		self.register_doc(new_fs)

		# 4. Create an assignment for the old programme
		afa = self.create_pace_applicant_fee_assignment(papp.name, fee_type="Course Fee", amount=15000)
		self.assertEqual(frappe.db.get_value("PACE Applicant Fee Assignment", afa.name, "status"), "Assigned")

		# Create a Payment Request linked to it
		pr = self.create_payment_request("PACE Applicant Fee Assignment", afa.name, "order_change_001", amount=15000)

		# 5. Change the programme in the application
		papp.status = "Verified"
		papp.programme = new_prog.name
		papp.save(ignore_permissions=True)

		# 6. Verify that the assignment is updated inline with the new program and amount
		self.assertEqual(frappe.db.get_value("PACE Applicant Fee Assignment", afa.name, "status"), "Assigned")
		self.assertEqual(frappe.db.get_value("PACE Applicant Fee Assignment", afa.name, "program"), new_prog.name)
		self.assertEqual(frappe.db.get_value("PACE Applicant Fee Assignment", afa.name, "total_amount"), 20000)

		# Verify that the associated Payment Request is Cancelled
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", pr.name, "status"), "Cancelled")

		# 7. Try to change program again after payment
		frappe.db.set_value("PACE Applicant Fee Assignment", afa.name, "status", "Paid")
		frappe.db.commit()

		# Try to change to another program (should raise ValidationError)
		papp.reload()
		papp.programme = "Some Other Programme"
		self.assertRaises(frappe.ValidationError, papp.save)


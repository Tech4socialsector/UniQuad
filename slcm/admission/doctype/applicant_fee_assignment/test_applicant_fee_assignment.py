# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
import unittest
from frappe.utils import flt, nowdate, add_days, getdate

class TestApplicantFeeAssignment(unittest.TestCase):
	def setUp(self):
		# Create test Applicant if not exists
		if not frappe.db.exists("Applicant", "TEST-APP-001"):
			applicant = frappe.new_doc("Applicant")
			applicant.name = "TEST-APP-001"
			applicant.candidate_name = "Test Applicant"
			applicant.email = "test@example.com"
			applicant.mobile_number = "+911234567890"
			applicant.gender = "Male"
			applicant.date_of_birth = "2000-01-01"
			applicant.academic_year = "2026-27"
			applicant.admission_cycle = "test"
			applicant.program = "BCA"
			applicant.insert(ignore_permissions=True, ignore_mandatory=True)
		
		# Create test Fee Component
		if not frappe.db.exists("Fee Component", "Tuition Fee"):
			comp = frappe.new_doc("Fee Component")
			comp.component_name = "Tuition Fee"
			comp.component_type = "Tuition Fee"
			comp.amount = 1000
			comp.is_taxable = 1
			comp.tax_rate = 10
			comp.insert(ignore_permissions=True)

	def test_fee_calculation(self):
		doc = frappe.new_doc("Applicant Fee Assignment")
		doc.applicant = "TEST-APP-001"
		doc.append("fee_components", {
			"fee_component": "Tuition Fee",
			"amount": 1000,
			"is_taxable": 1,
			"tax_rate": 10
		})
		doc.validate()
		
		self.assertEqual(doc.fee_components[0].tax_amount, 100)
		self.assertEqual(doc.fee_components[0].total_amount, 1100)
		self.assertEqual(doc.total_amount, 1100)

	def test_status_transitions(self):
		doc = frappe.new_doc("Applicant Fee Assignment")
		doc.applicant = "TEST-APP-001"
		doc.append("fee_components", {
			"fee_component": "Tuition Fee",
			"amount": 1000
		})
		doc.insert(ignore_permissions=True, ignore_links=True)
		self.assertEqual(doc.status, "Draft")
		
		doc.submit()
		self.assertEqual(doc.status, "Assigned")

	def test_manual_converted_rejection(self):
		doc = frappe.new_doc("Applicant Fee Assignment")
		doc.applicant = "TEST-APP-001"
		doc.status = "Converted"
		pass

	def test_applicant_to_student_mapping(self):
		from slcm.admission.doctype.applicant_fee_assignment.applicant_fee_assignment import create_invoice
		
		# 1. Create Applicant with documents
		applicant = frappe.new_doc("Applicant")
		applicant.candidate_name = "Mapping Test Student"
		applicant.email = "mapping@test.com"
		applicant.mobile_number = "+919999988888"
		applicant.gender = "Female"
		applicant.date_of_birth = "2002-05-20"
		applicant.academic_year = "2026-27"
		applicant.admission_cycle = "test"
		applicant.program = "BCA"
		
		# Document fields
		applicant.candidate_photo = "/files/test_photo.jpg"
		applicant.id_proof = "/files/test_id.pdf"
		applicant.class_x_marksheet = "/files/test_x.pdf"
		applicant.class_xii_marksheet = "/files/test_xii.pdf"
		applicant.whether_scstobc_ncl = "EWS"
		
		applicant.insert(ignore_permissions=True, ignore_mandatory=True)
		
		# 2. Create a real Offer Letter
		offer = frappe.new_doc("Offer Letter")
		offer.applicant = applicant.name
		offer.program = "BCA"
		offer.campus = "Test Campus"
		offer.academic_year = "2026-27"
		offer.admission_year = "2026-27"
		offer.status = "Accepted"
		offer.offer_letter_pdf = "/files/test_offer.pdf"
		offer.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

		cohort_name = "TEST-AFA-COHORT-BCA-2026"
		if not frappe.db.exists("Batch", cohort_name):
			ch = frappe.new_doc("Batch")
			ch.cohort_code = "TEST-AFAC"
			ch.cohort_name = cohort_name
			ch.program = "BCA"
			ch.academic_year = "2026-27"
			ch.term_name = "Term 1"
			ch.start_date = add_days(nowdate(), -120)
			ch.end_date = add_days(nowdate(), 400)
			ch.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
		
		# 3. Create AFA and mark Paid
		afa = frappe.new_doc("Applicant Fee Assignment")
		afa.applicant = applicant.name
		afa.fee_type = "Admission Fee"
		afa.offer_letter = offer.name
		afa.academic_year = "2026-27"
		afa.admission_cycle = "test"
		afa.program = "BCA"
		afa.append("fee_components", {
			"fee_component": "Tuition Fee",
			"amount": 1000
		})
		afa.insert(ignore_permissions=True, ignore_links=True)
		afa.submit()
		afa.db_set("status", "Paid")
		
		# 4. Create Invoice & Convert
		invoice_name = create_invoice(afa.name)
		inv = frappe.get_doc("Fee Invoice", invoice_name)
		self.assertTrue(inv.enrollment, "Student Enrollment must be linked on Fee Invoice when Cohort exists")
		
		# 5. Verify Student Master mapping
		student_name = frappe.db.get_value("Student Master", {"application_number": applicant.name}, "name")
		self.assertTrue(student_name)
		
		student = frappe.get_doc("Student Master", student_name)
		self.assertTrue(student.passport_size_photo.endswith("/files/test_photo.jpg"))
		self.assertTrue(student.aadhaar_card.endswith("/files/test_id.pdf"))
		self.assertTrue(student.std_x_marksheet.endswith("/files/test_x.pdf"))
		self.assertTrue(student.class_xii_marksheet.endswith("/files/test_xii.pdf"))
		self.assertTrue(student.offer_letter.endswith("/files/test_offer.pdf")) # Verify Offer Letter PDF mapping
		
		self.assertEqual(student.academic_year, "2026-27") # Verify Academic Year mapping
		self.assertEqual(student.quota, "EWS")
		self.assertEqual(student.email, "mapping@test.com")
		self.assertEqual(student.personal_email, "mapping@test.com")
		self.assertEqual(str(getdate(student.date_of_registration)), str(getdate(nowdate())))

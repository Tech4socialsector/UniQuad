# Copyright (c) 2026, TFSS and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from slcm.api.service.applicant_to_student import convert_applicant_to_student


class TestApplicant(FrappeTestCase):
    def setUp(self):
        # Clean up previous test data
        frappe.db.sql("DELETE FROM `tabStudent Master` WHERE email IN ('domestic@test.com', 'intl@test.com', 'ews@test.com', 'obc@test.com', 'sc@test.com')")
        frappe.db.sql("DELETE FROM `tabApplicant` WHERE email IN ('domestic@test.com', 'intl@test.com', 'ews@test.com', 'obc@test.com', 'sc@test.com')")
        frappe.db.sql("DELETE FROM `tabEntrance Test Seat Allocation`")
        frappe.db.sql("DELETE FROM `tabMerit List Applicant`")
        if not frappe.db.exists("Academic Year", "2026-27"):
            frappe.get_doc({"doctype": "Academic Year", "academic_year_name": "2026-27"}).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
        if not frappe.db.exists("Term Master", "Semester 1"):
            frappe.get_doc({"doctype": "Term Master", "term_name": "Semester 1", "name": "Semester 1"}).insert(ignore_permissions=True, set_name="Semester 1", ignore_mandatory=True, ignore_links=True)
        if not frappe.db.exists("Academic Term", "Semester 1"):
            frappe.get_doc({"doctype": "Academic Term", "academic_term_name": "Semester 1", "academic_year": "2026-27", "term_name": "Semester 1"}).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

        # Create a Programme for testing
        if not frappe.db.exists("Programme", "TPA-2026-27-SEMESTER-1"):
            frappe.get_doc({
                "doctype": "Programme",
                "program_name": "Test Program - Applicant",
                "program_code": "TPA",
                "program_abbreviation": "TPA",
                "academic_year": "2026-27",
                "academic_term": "Semester 1",
            }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

        if not frappe.db.exists("Admission Cycle", "Test Cycle - Applicant"):
            frappe.get_doc({
                "doctype": "Admission Cycle",
                "cycle_name": "Test Cycle - Applicant",
            }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

        # Create Domestic Applicant
        if not frappe.db.exists("Applicant", "APP-TEST-DOMESTIC"):
            frappe.get_doc({
                "doctype": "Applicant",
                "first_name": "Domestic",
                "last_name": "Test",
                "foriegn_national": "No",
                "whether_scstobc_ncl": "General",
                "email": "domestic@test.com",
                "program": "TPA-2026-27-SEMESTER-1",
                "annual_house_hold_income": "₹ 0 - ₹ 3,00,000",
                "status": "Applied",
                "ews": "No",
                "gender": "Male",
                "pwd": "No",
                "intake_type": "Direct Merit",
                "date_of_birth": "2000-01-01"
            }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

        # Create International Applicant
        if not frappe.db.exists("Applicant", "APP-TEST-INTL"):
            frappe.get_doc({
                "doctype": "Applicant",
                "first_name": "Intl",
                "last_name": "Test",
                "foriegn_national": "Yes",
                "email": "intl@test.com",
                "program": "TPA-2026-27-SEMESTER-1",
                "annual_house_hold_income": "More than ₹ 50,00,000",
                "status": "Applied",
                "ews": "No",
                "gender": "Female",
                "pwd": "No",
                "intake_type": "Direct Merit",
                "date_of_birth": "2000-01-01"
            }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

        # Create EWS Applicant
        if not frappe.db.exists("Applicant", "APP-TEST-EWS"):
            frappe.get_doc({
                "doctype": "Applicant",
                "first_name": "EWS",
                "last_name": "Test",
                "foriegn_national": "No",
                "whether_scstobc_ncl": "General",
                "email": "ews@test.com",
                "program": "TPA-2026-27-SEMESTER-1",
                "status": "Applied",
                "ews": "Yes",
                "gender": "Male",
                "pwd": "No",
                "intake_type": "Direct Merit",
                "date_of_birth": "2000-01-01"
            }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

        # Create OBC Applicant
        if not frappe.db.exists("Applicant", "APP-TEST-OBC"):
            frappe.get_doc({
                "doctype": "Applicant",
                "first_name": "OBC",
                "last_name": "Test",
                "foriegn_national": "No",
                "whether_scstobc_ncl": "OBC-NCL",
                "email": "obc@test.com",
                "program": "TPA-2026-27-SEMESTER-1",
                "status": "Applied",
                "ews": "No",
                "gender": "Female",
                "pwd": "No",
                "intake_type": "Direct Merit",
                "date_of_birth": "2000-01-01"
            }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

        # Create SC Applicant
        if not frappe.db.exists("Applicant", "APP-TEST-SC"):
            frappe.get_doc({
                "doctype": "Applicant",
                "first_name": "SC",
                "last_name": "Test",
                "foriegn_national": "No",
                "whether_scstobc_ncl": "SC",
                "email": "sc@test.com",
                "program": "TPA-2026-27-SEMESTER-1",
                "status": "Applied",
                "ews": "No",
                "gender": "Male",
                "pwd": "No",
                "intake_type": "Direct Merit",
                "date_of_birth": "2000-01-01"
            }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

        # Fetch the actual ID of the domestic applicant (since autoname creates a dynamic ID like APP-2026-XXXX)
        domestic_applicant_name = frappe.db.get_value("Applicant", {"email": "domestic@test.com"}, "name")
        if domestic_applicant_name:
            # Create Entrance Test Seat Allocation for Domestic
            if not frappe.db.exists("Entrance Test Seat Allocation", {"applicant": domestic_applicant_name, "program": "TPA-2026-27-SEMESTER-1"}):
                frappe.get_doc({
                    "doctype": "Entrance Test Seat Allocation",
                    "applicant": domestic_applicant_name,
                    "program": "TPA-2026-27-SEMESTER-1",
                    "admit_card_number": "ADMIT-123",
                    "entrance_test_status": "Attended",
                    "part_a_total_marks_scored": 50,
                    "part_b_total_marks_scored": 45.5
                }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

            # Create Merit List Applicant for Domestic
            if not frappe.db.exists("Merit List Applicant", {"applicant_id": domestic_applicant_name}):
                frappe.get_doc({
                    "doctype": "Merit List Applicant",
                    "applicant_id": domestic_applicant_name,
                    "applicant": domestic_applicant_name,
                    "overall_rank": 10,
                    "category_rank": 2,
                    "shortlist_category": "General",
                    "vertical_category": "General",
                    "horizontal_categories": "None",
                    "percentile_score": 99.1
                }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

    def test_domestic_applicant_conversion(self):
        # Fetch the created domestic applicant
        applicant = frappe.get_doc("Applicant", {"email": "domestic@test.com"})
        
        # Convert to student
        res = convert_applicant_to_student(applicant.name, "TPA-2026-27-SEMESTER-1", "Test Cycle - Applicant", None)
        
        student_name = res.get("student_name")
        self.assertTrue(student_name)
        
        student = frappe.get_doc("Student Master", student_name)
        
        # Verify domestic specific mapping (Quota should be General)
        self.assertEqual(student.quota, "General")
        self.assertEqual(student.annual_income, "₹ 0 - ₹ 3,00,000")
        
        # Verify dynamic mapping from Entrance Test
        self.assertEqual(student.admit_card_number, "ADMIT-123")
        self.assertEqual(student.exam_attended, "Attended")
        self.assertEqual(float(student.total_marks_obtained), 95.5)
        
        # Verify dynamic mapping from Merit List
        self.assertEqual(int(student.final_rank), 10)
        self.assertEqual(int(student.final_category_rank), 2)
        self.assertEqual(float(student.final_percentile), 99.1)
        self.assertEqual(student.final_rank_category, "General")
        self.assertEqual(student.rank_category, "General")
        self.assertEqual(student.final_vertical, "General")
        self.assertEqual(student.final_horizontal, "None")
        
        # Verify applicant status is correctly updated to Enrolled
        applicant.reload()
        self.assertEqual(applicant.status, "Enrolled")

    def test_international_applicant_conversion(self):
        # Fetch the created international applicant
        applicant = frappe.get_doc("Applicant", {"email": "intl@test.com"})
        
        # Convert to student
        res = convert_applicant_to_student(applicant.name, "TPA-2026-27-SEMESTER-1", "Test Cycle - Applicant", None)
        
        student_name = res.get("student_name")
        self.assertTrue(student_name)
        
        student = frappe.get_doc("Student Master", student_name)
        
        # Verify international specific mapping (Quota should be NA)
        self.assertEqual(student.quota, "General")
        self.assertEqual(student.annual_income, "More than ₹ 50,00,000")
        
        # Verify applicant status is correctly updated to Enrolled
        applicant.reload()
        self.assertEqual(applicant.status, "Enrolled")

    def test_ews_applicant_conversion(self):
        applicant = frappe.get_doc("Applicant", {"email": "ews@test.com"})
        res = convert_applicant_to_student(applicant.name, "TPA-2026-27-SEMESTER-1", "Test Cycle - Applicant", None)
        
        student = frappe.get_doc("Student Master", res.get("student_name"))
        self.assertEqual(student.quota, "EWS")

    def test_obc_applicant_conversion(self):
        applicant = frappe.get_doc("Applicant", {"email": "obc@test.com"})
        res = convert_applicant_to_student(applicant.name, "TPA-2026-27-SEMESTER-1", "Test Cycle - Applicant", None)
        
        student = frappe.get_doc("Student Master", res.get("student_name"))
        self.assertEqual(student.quota, "OBC")

    def test_sc_applicant_conversion(self):
        applicant = frappe.get_doc("Applicant", {"email": "sc@test.com"})
        res = convert_applicant_to_student(applicant.name, "TPA-2026-27-SEMESTER-1", "Test Cycle - Applicant", None)
        
        student = frappe.get_doc("Student Master", res.get("student_name"))
        self.assertEqual(student.quota, "SC")

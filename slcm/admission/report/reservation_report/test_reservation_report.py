# Copyright (c) 2026, TFSS and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from slcm.admission.report.reservation_report.reservation_report import execute

class TestReservationReport(FrappeTestCase):
    def setUp(self):
        # 1. Clean up existing test data
        self.cleanup_test_records()

        # 2. Create mock admission categories to guarantee they exist in DB
        self.mock_categories = [
            {"doctype": "Admission Category", "name": "SC", "category_name": "SC", "category_code": "SC", "reservation_type": "Vertical", "is_active": 1},
            {"doctype": "Admission Category", "name": "ST", "category_name": "ST", "category_code": "ST", "reservation_type": "Vertical", "is_active": 1},
            {"doctype": "Admission Category", "name": "General", "category_name": "General", "category_code": "General", "reservation_type": "Vertical", "is_active": 1},
            {"doctype": "Admission Category", "name": "EWS", "category_name": "EWS", "category_code": "EWS", "reservation_type": "Vertical", "is_active": 1},
            {"doctype": "Admission Category", "name": "OBC-NCL", "category_name": "OBC-NCL", "category_code": "OBC-NCL", "reservation_type": "Vertical", "is_active": 1},
            {"doctype": "Admission Category", "name": "PWD", "category_name": "PWD", "category_code": "PWD", "reservation_type": "Horizontal", "is_active": 1},
            {"doctype": "Admission Category", "name": "Women", "category_name": "Women", "category_code": "Women", "reservation_type": "Horizontal", "is_active": 1},
            {"doctype": "Admission Category", "name": "Karnataka", "category_name": "Karnataka", "category_code": "Karnataka", "reservation_type": "Compartmentalised Horizontal", "is_active": 1}
        ]
        for cat in self.mock_categories:
            if not frappe.db.exists("Admission Category", cat["name"]):
                frappe.get_doc(cat).insert(ignore_permissions=True)

        # 3. Create mock Applicant 1 (Passed student - SC, PWD, Women, Karnataka)
        self.app1 = frappe.get_doc({
            "doctype": "Applicant",
            "candidate_name": "Test Candidate Passed",
            "email": "passed_test@example.com",
            "mobile_number": "+91-9876543210",
            "date_of_birth": "2000-01-01",
            "gender": "Female",
            "status": "Submitted",
            "program": "TEST-PROG-RESERVATION",
            "admission_cycle": "TEST-CYCLE-RESERVATION",
            "academic_year": "2026-2027",
            "whether_scstobc_ncl": "SC",
            "pwd": "Yes",
            "karnataka_category": "Yes"
        })
        self.app1.flags.ignore_mandatory = True
        self.app1.flags.ignore_links = True
        self.app1.insert(ignore_permissions=True)

        # 4. Create mock Entrance Test Seat Allocation 1 (Passed)
        self.allocation1 = frappe.get_doc({
            "doctype": "Entrance Test Seat Allocation",
            "applicant": self.app1.name,
            "entrance_test_status": "Attended",
            "result_status": "Pass",
            "program": "TEST-PROG-RESERVATION",
            "admission_cycle": "TEST-CYCLE-RESERVATION",
            "academic_year": "2026-2027",
            "campus": "TEST-CAMPUS-RESERVATION"
        })
        self.allocation1.flags.ignore_mandatory = True
        self.allocation1.flags.ignore_links = True
        self.allocation1.insert(ignore_permissions=True)

        # 5. Create mock Applicant 2 (Failed student)
        self.app2 = frappe.get_doc({
            "doctype": "Applicant",
            "candidate_name": "Test Candidate Failed",
            "email": "failed_test@example.com",
            "mobile_number": "+91-9876543211",
            "date_of_birth": "2000-01-02",
            "gender": "Male",
            "status": "Submitted",
            "program": "TEST-PROG-RESERVATION",
            "admission_cycle": "TEST-CYCLE-RESERVATION",
            "academic_year": "2026-2027",
            "whether_scstobc_ncl": "ST",
            "pwd": "No",
            "karnataka_category": "No"
        })
        self.app2.flags.ignore_mandatory = True
        self.app2.flags.ignore_links = True
        self.app2.insert(ignore_permissions=True)

        # 6. Create mock Entrance Test Seat Allocation 2 (Failed)
        self.allocation2 = frappe.get_doc({
            "doctype": "Entrance Test Seat Allocation",
            "applicant": self.app2.name,
            "entrance_test_status": "Attended",
            "result_status": "Fail",
            "program": "TEST-PROG-RESERVATION",
            "admission_cycle": "TEST-CYCLE-RESERVATION",
            "academic_year": "2026-2027",
            "campus": "TEST-CAMPUS-RESERVATION"
        })
        self.allocation2.flags.ignore_mandatory = True
        self.allocation2.flags.ignore_links = True
        self.allocation2.insert(ignore_permissions=True)

        frappe.db.commit()

    def tearDown(self):
        self.cleanup_test_records()

    def cleanup_test_records(self):
        # Delete test seat allocations
        frappe.db.delete("Entrance Test Seat Allocation", {"admission_cycle": "TEST-CYCLE-RESERVATION"})
        # Delete test applicants
        frappe.db.delete("Applicant", {"admission_cycle": "TEST-CYCLE-RESERVATION"})
        # Note: Do not delete predefined Admission Categories as they are master records
        frappe.db.commit()

    def test_reservation_counts(self):
        # Run report execution with filters matching our mock cycle & program
        filters = {
            "admission_cycle": "TEST-CYCLE-RESERVATION",
            "program": "TEST-PROG-RESERVATION",
            "academic_year": "2026-2027",
            "campus": "TEST-CAMPUS-RESERVATION"
        }
        
        columns, data, message, chart, report_summary = execute(filters)

        # Assert correct columns structure
        self.assertEqual(len(columns), 3)
        self.assertEqual(columns[0]["fieldname"], "category_type")
        self.assertEqual(columns[1]["fieldname"], "category_name")
        self.assertEqual(columns[2]["fieldname"], "student_count")

        # Map results to a dictionary for easy assertion
        results_map = {}
        for row in data:
            key = (row["category_type"], row["category_name"])
            results_map[key] = row["student_count"]

        # 1. Assert Vertical Categories (Passed student: SC, Failed student: ST - should be 0)
        self.assertEqual(results_map.get(("1. Vertical Category", "SC")), 1)
        self.assertEqual(results_map.get(("1. Vertical Category", "ST")), 0)
        self.assertEqual(results_map.get(("1. Vertical Category", "General")), 0)

        # 2. Assert Horizontal Categories (Passed student: PWD & Women)
        self.assertEqual(results_map.get(("2. Horizontal Category", "PWD")), 1)
        self.assertEqual(results_map.get(("2. Horizontal Category", "Women")), 1)

        # 3. Assert Compartmentalized Category (Passed student: Karnataka)
        self.assertEqual(results_map.get(("3. Compartmentalized Category", "Karnataka")), 1)

        # 4. Assert Vertical + Horizontal Combinations
        self.assertEqual(results_map.get(("4. Vertical + Horizontal", "SC + PWD")), 1)
        self.assertEqual(results_map.get(("4. Vertical + Horizontal", "SC + Women")), 1)
        self.assertEqual(results_map.get(("4. Vertical + Horizontal", "General + Women")), 0)

        # 5. Assert Vertical + Compartmentalized Combinations
        self.assertEqual(results_map.get(("5. Vertical + Compartmentalized", "SC + Karnataka")), 1)
        self.assertEqual(results_map.get(("5. Vertical + Compartmentalized", "General + Karnataka")), 0)

        # 6. Assert Vertical + Horizontal + Compartmentalized Combinations
        self.assertEqual(results_map.get(("6. Vertical + Horizontal + Compartmentalized", "SC + PWD + Karnataka")), 1)
        self.assertEqual(results_map.get(("6. Vertical + Horizontal + Compartmentalized", "SC + Women + Karnataka")), 1)
        self.assertEqual(results_map.get(("6. Vertical + Horizontal + Compartmentalized", "General + Women + Karnataka")), 0)

        # 7. Assert Report Summary Cards
        summary_map = {item["label"]: item["value"] for item in report_summary}
        self.assertEqual(summary_map.get("Total Passed Students"), 1)
        self.assertEqual(summary_map.get("General Category"), 0)
        self.assertEqual(summary_map.get("Reserved Categories"), 1)
        self.assertEqual(summary_map.get("Karnataka Category"), 1)


def run_test():
    t = TestReservationReport()
    t.setUp()
    try:
        t.test_reservation_counts()
        print("Unit test executed successfully and PASSED!")
        return "OK"
    finally:
        t.tearDown()

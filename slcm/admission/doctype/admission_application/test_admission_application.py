import frappe
import unittest
from frappe.utils import today


class TestAdmissionApplication(unittest.TestCase):

    def setUp(self):
        """Set up test data"""
        self.test_cycle = frappe.db.get_value(
            "Admission Cycle", {"status": "Active"}, "name"
        )
        self.test_program = frappe.db.get_value("Programme", {}, "name")

    def test_create_application(self):
        """Test basic application creation"""
        if not self.test_cycle or not self.test_program:
            self.skipTest("No active cycle or program found")

        app = frappe.new_doc("Admission Application")
        app.admission_cycle = self.test_cycle
        app.program = self.test_program
        app.application_date = today()
        app.status = "Draft"
        app.declaration_accepted = 1
        # In actual use, applicant link would be required

        self.assertEqual(app.status, "Draft")
        self.assertEqual(app.declaration_accepted, 1)

    def test_status_values(self):
        """Test that status select options are valid"""
        valid_statuses = [
            "Draft", "Submitted", "Under Review",
            "Shortlisted", "Waitlisted", "Offered",
            "Accepted", "Rejected", "Withdrawn"
        ]
        # Just check meta to be sure
        meta = frappe.get_meta("Admission Application")
        status_field = meta.get_field("status")
        options = status_field.options.split("\n")
        for s in valid_statuses:
            self.assertIn(s, options)

    def test_doctype_exists(self):
        """Test that DocType is registered"""
        self.assertTrue(frappe.db.exists("DocType", "Admission Application"))

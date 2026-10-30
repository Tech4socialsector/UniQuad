import frappe
import unittest

class TestAdmissionStageTemplate(unittest.TestCase):
    def test_duplicate_sequence_blocked(self):
        doc = frappe.new_doc("Admission Stage Template")
        doc.template_name = "Test Template"
        doc.append("stages", {"stage_name": "Application", "stage_type": "Application", "sequence": 1, "is_enabled": 1})
        doc.append("stages", {"stage_name": "Interview", "stage_type": "Interview", "sequence": 1, "is_enabled": 1})
        self.assertRaises(frappe.ValidationError, doc.validate)

    def test_empty_stages_blocked(self):
        doc = frappe.new_doc("Admission Stage Template")
        doc.template_name = "Empty Template"
        self.assertRaises(frappe.ValidationError, doc.validate)

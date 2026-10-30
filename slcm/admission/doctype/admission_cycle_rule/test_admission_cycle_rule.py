import frappe
import unittest

class TestAdmissionCycleRule(unittest.TestCase):
    def test_rule_value_required(self):
        doc = frappe.new_doc("Admission Cycle Rule")
        doc.admission_cycle = "TEST-CYCLE"
        doc.rule_type = "offer_validity_period"
        doc.rule_value = ""
        self.assertRaises(frappe.ValidationError, doc.validate)

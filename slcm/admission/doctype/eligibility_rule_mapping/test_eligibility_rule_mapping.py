# Copyright (c) 2026, TFSS and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

class TestEligibilityRuleMapping(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.docs_to_delete = []

    def tearDown(self):
        for doc in reversed(self.docs_to_delete):
            try:
                frappe.delete_doc(doc.doctype, doc.name, force=1)
            except Exception:
                pass
        frappe.db.commit()
        super().tearDown()

    def test_hsc_category_override(self):
        # Create a mock eligibility rule for HSC (XII)
        rule = frappe.get_doc({
            "doctype": "Eligibility Rule",
            "rule_name": "Test HSC Rule",
            "rule_type": "Percentage",
            "qualification_level": "XII",
            "required_percentage": 50.0,
            "sslc_percentage": 60.0,
            "operator": ">="
        })
        rule.insert(ignore_permissions=True, ignore_mandatory=True)
        self.docs_to_delete.append(rule)

        # Create an applicant belonging to category "OBC-NCL"
        app = frappe.get_doc({
            "doctype": "Applicant",
            "candidate_name": "Test HSC Applicant",
            "email": "hsc_test@example.com",
            "gender": "Male",
            "status": "Submitted and Paid",
            "evaluation_status": "Eligible",
            "hsc_percentage": 45.0, # lower than 50% baseline
            "class_x_percentage": 55.0, # lower than 60% baseline
            "whether_scstobc_ncl": "OBC-NCL" # matches reservation category OBC-NCL
        })
        app.insert(ignore_permissions=True, ignore_mandatory=True)
        self.docs_to_delete.append(app)

        # Create an active mapping
        mapping = frappe.get_doc({
            "doctype": "Eligibility Rule Mapping",
            "name": "TEST-MAP-HSC",
            "program": "BA LLB (Hons)",
            "admission_cycle": "AD",
            "campus": "NLSIU",
            "applicant_type": "Both",
            "is_active": 1,
            "rule": [{"rule": rule.name}],
            "reservation_category": [
                {
                    "category": "OBC-NCL",
                    "priority": 1,
                    "minimum_percentage_hsc": 40.0, # override lower than 45%
                    "minimum_percentage_sslc": 50.0  # override lower than 55%
                }
            ]
        })
        mapping.insert(ignore_permissions=True, ignore_mandatory=True)
        self.docs_to_delete.append(mapping)

        # Set applicant's program/campus to match mapping
        app.program = "BA LLB (Hons)"
        app.campus = "NLSIU"
        app.admission_cycle = "AD"
        app.academic_year = "2026-2027"

        # Check eligibility - should pass because of the OBC-NCL override
        is_eligible, reason = app._evaluate_mapping_with_category_priority(mapping)
        self.assertTrue(is_eligible)

        # Now test with another applicant who has lower marks
        app2 = frappe.get_doc({
            "doctype": "Applicant",
            "candidate_name": "Test HSC Applicant 2",
            "email": "hsc_test2@example.com",
            "gender": "Male",
            "status": "Submitted and Paid",
            "evaluation_status": "Eligible",
            "hsc_percentage": 38.0, # below 40.0% override
            "class_x_percentage": 55.0,
            "whether_scstobc_ncl": "OBC-NCL"
        })
        app2.insert(ignore_permissions=True, ignore_mandatory=True)
        self.docs_to_delete.append(app2)
        app2.program = "BA LLB (Hons)"
        app2.campus = "NLSIU"
        app2.admission_cycle = "AD"
        app2.academic_year = "2026-2027"

        is_eligible, reason = app2._evaluate_mapping_with_category_priority(mapping)
        self.assertFalse(is_eligible)

    def test_ug_cgpa_category_override(self):
        # Create a mock eligibility rule for UG
        rule = frappe.get_doc({
            "doctype": "Eligibility Rule",
            "rule_name": "Test UG Rule",
            "rule_type": "CGPA",
            "qualification_level": "Undergraduate",
            "required_cgpa": 7.0,
            "operator": ">="
        })
        rule.insert(ignore_permissions=True, ignore_mandatory=True)
        self.docs_to_delete.append(rule)

        # Create an applicant belonging to category "SC"
        app = frappe.get_doc({
            "doctype": "Applicant",
            "candidate_name": "Test UG Applicant",
            "email": "ug_test@example.com",
            "gender": "Male",
            "status": "Submitted and Paid",
            "evaluation_status": "Eligible",
            "whether_scstobc_ncl": "SC",
            "ug_degree_details": [
                {
                    "ug_program": "B.A.",
                    "ug_cgpa": 6.5 # below 7.0 baseline
                }
            ]
        })
        app.insert(ignore_permissions=True, ignore_mandatory=True)
        self.docs_to_delete.append(app)

        # Create active mapping with override
        mapping = frappe.get_doc({
            "doctype": "Eligibility Rule Mapping",
            "name": "TEST-MAP-UG",
            "program": "LLM",
            "admission_cycle": "AD",
            "campus": "NLSIU",
            "applicant_type": "Both",
            "is_active": 1,
            "rule": [{"rule": rule.name}],
            "reservation_category": [
                {
                    "category": "SC",
                    "priority": 1,
                    "minimum_cgpa_ug": 6.0 # override lower than 6.5
                }
            ]
        })
        mapping.insert(ignore_permissions=True, ignore_mandatory=True)
        self.docs_to_delete.append(mapping)

        app.program = "LLM"
        app.campus = "NLSIU"
        app.admission_cycle = "AD"
        app.academic_year = "2026-2027"

        # Check eligibility - should pass because of SC override
        is_eligible, reason = app._evaluate_mapping_with_category_priority(mapping)
        self.assertTrue(is_eligible)

    def test_multiple_category_priority_sorting(self):
        # Create a mock eligibility rule for HSC (XII)
        rule = frappe.get_doc({
            "doctype": "Eligibility Rule",
            "rule_name": "Test HSC Rule Priority",
            "rule_type": "Percentage",
            "qualification_level": "XII",
            "required_percentage": 50.0,
            "operator": ">="
        })
        rule.insert(ignore_permissions=True, ignore_mandatory=True)
        self.docs_to_delete.append(rule)

        # Create an applicant belonging to both category "Karnataka" and "SC"
        app = frappe.get_doc({
            "doctype": "Applicant",
            "candidate_name": "Test HSC Priority Applicant",
            "email": "hsc_priority_test@example.com",
            "gender": "Male",
            "status": "Submitted and Paid",
            "evaluation_status": "Eligible",
            "hsc_percentage": 45.0, # matches SC override (40%) but not Karnataka override (48%)
            "karnataka_category": "Yes",
            "whether_scstobc_ncl": "SC"
        })
        app.insert(ignore_permissions=True, ignore_mandatory=True)
        self.docs_to_delete.append(app)

        # Create an active mapping where Karnataka is Priority 1, SC is Priority 2
        # Since Karnataka is checked first (Priority 1) and applicant fails Karnataka (45% < 48%),
        # the system will continue to check SC (Priority 2) and applicant will qualify under SC (45% >= 40%)
        # and therefore the applied category should be set to "SC"
        mapping = frappe.get_doc({
            "doctype": "Eligibility Rule Mapping",
            "name": "TEST-MAP-PRIO-HSC",
            "program": "BA LLB (Hons)",
            "admission_cycle": "AD",
            "campus": "NLSIU",
            "applicant_type": "Both",
            "is_active": 1,
            "rule": [{"rule": rule.name}],
            "reservation_category": [
                {
                    "category": "Karnataka",
                    "priority": 1,
                    "minimum_percentage_hsc": 48.0
                },
                {
                    "category": "SC",
                    "priority": 2,
                    "minimum_percentage_hsc": 40.0
                }
            ]
        })
        mapping.insert(ignore_permissions=True, ignore_mandatory=True)
        self.docs_to_delete.append(mapping)

        app.program = "BA LLB (Hons)"
        app.campus = "NLSIU"
        app.admission_cycle = "AD"
        app.academic_year = "2026-2027"

        # Check eligibility - should fail because Karnataka is Priority 1, and applicant fails Karnataka (45% < 48%)
        # and we do not check lower priority categories (like SC).
        is_eligible, reason = app._evaluate_mapping_with_category_priority(mapping)
        self.assertFalse(is_eligible)

        # Now, if we swap the priorities: SC is Priority 1, Karnataka is Priority 2.
        # Since SC is evaluated first, and they pass SC, they immediately qualify under SC and the loop exits.
        # Thus, applied_category is SC.
        # What if they pass both?
        # e.g., hsc_percentage = 49.0 (passes both Karnataka [48%] and SC [40%]).
        # If Karnataka is Priority 1: applied_category should be "Karnataka".
        # If SC is Priority 1: applied_category should be "SC".
        
        app.hsc_percentage = 49.0
        # Check eligibility with Karnataka as Priority 1, SC as Priority 2
        is_eligible, reason = app._evaluate_mapping_with_category_priority(mapping)
        self.assertTrue(is_eligible)
        self.assertEqual(app.applied_category, "Karnataka")

        # Now update mapping to make SC Priority 1, Karnataka Priority 2
        for row in mapping.reservation_category:
            if row.category == "SC":
                row.priority = 1
            elif row.category == "Karnataka":
                row.priority = 2
        mapping.save()

        is_eligible, reason = app._evaluate_mapping_with_category_priority(mapping)
        self.assertTrue(is_eligible)
        self.assertEqual(app.applied_category, "SC")

def run_tests():
    import unittest
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEligibilityRuleMapping)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        raise Exception("Tests failed")

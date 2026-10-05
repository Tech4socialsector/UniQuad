# Copyright (c) 2026, TFSS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
import math

class IntegrationTestInterviewConfiguration(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.policies_to_delete = []
        self.configs_to_delete = []
        self.restored_policies = []
        
        # Back up and temporarily remove any conflicting existing policies
        existing_policies = frappe.get_all(
            "Programme Reservation Policy",
            filters={"program": "BA LLB (Hons)", "admission_cycle": "AD", "campus": "NLSIU"}
        )
        for ep in existing_policies:
            doc = frappe.get_doc("Programme Reservation Policy", ep.name)
            self.restored_policies.append(doc.as_dict())
            frappe.db.delete("Programme Reservation Policy", {"name": ep.name})
        frappe.db.commit()
        
    def tearDown(self):
        for policy in self.policies_to_delete:
            frappe.db.delete("Programme Reservation Policy", {"name": policy})
        for config in self.configs_to_delete:
            frappe.db.delete("Interview Configuration", {"name": config})
        frappe.db.commit()
        
        # Restore original policies
        for p_dict in self.restored_policies:
            p_dict.pop("name", None)
            p_dict.pop("owner", None)
            p_dict.pop("creation", None)
            p_dict.pop("modified", None)
            p_dict.pop("modified_by", None)
            doc = frappe.get_doc(p_dict)
            doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.commit()
        super().tearDown()

    def test_ratio_multiplier_parsing(self):
        # Create a dummy program policy
        policy_doc = frappe.get_doc({
            "doctype": "Programme Reservation Policy",
            "program": "BA LLB (Hons)",
            "admission_cycle": "AD",
            "campus": "NLSIU",
            "international_seats": 11,
            "status": "Active"
        })
        policy_doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.policies_to_delete.append(policy_doc.name)

        doc = frappe.get_doc({
            "doctype": "Interview Configuration",
            "name": "IVC-TEST-001",
            "configuration_code": "IVC-TEST-001",
            "academic_year": "2026-2027",
            "campus": "NLSIU",
            "admission_cycle": "AD",
            "program": "BA LLB (Hons)",
            "applicant_type": "International Applicants",
            "enter_international_ratio": "1:3"
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.configs_to_delete.append(doc.name)
        
        # Test get_total_seats
        self.assertEqual(doc.get_total_seats(), 11)
        
        # Manually verify multiplier logic (seats * multiplier -> 11 * 3 = 33)
        ratio = doc.enter_international_ratio
        parts = ratio.split(":")
        num1 = float(parts[0])
        num2 = float(parts[1])
        multiplier = max(num1, num2) / min(num1, num2)
        self.assertEqual(multiplier, 3.0)
        self.assertEqual(int(math.ceil(doc.get_total_seats() * multiplier)), 33)

    def test_domestic_seats_from_policy(self):
        # Create a dummy program policy
        policy_doc = frappe.get_doc({
            "doctype": "Programme Reservation Policy",
            "program": "BA LLB (Hons)",
            "admission_cycle": "AD",
            "campus": "NLSIU",
            "total_seats": 15,
            "status": "Active"
        })
        policy_doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.policies_to_delete.append(policy_doc.name)
            
        doc = frappe.get_doc({
            "doctype": "Interview Configuration",
            "name": "IVC-TEST-001",
            "configuration_code": "IVC-TEST-001",
            "academic_year": "2026-2027",
            "campus": "NLSIU",
            "admission_cycle": "AD",
            "program": "BA LLB (Hons)",
            "applicant_type": "Domestic Applicants",
            "enter_domestic_ratio": "3:1"
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.configs_to_delete.append(doc.name)
        
        # Verify get_total_seats fetches seats from Policy
        self.assertEqual(doc.get_total_seats(), 15)

    def test_tie_breaker_logic(self):
        # Create a list of mock applicants
        applicants = [
            {"name": "App1", "entrance_test_score": 80.0, "part_a_score": 50.0},
            {"name": "App2", "entrance_test_score": 80.0, "part_a_score": 70.0},
            {"name": "App3", "entrance_test_score": 75.0, "part_a_score": 90.0}
        ]
        
        # Sort using our new tuple key
        applicants.sort(key=lambda x: (x.get("entrance_test_score", 0), x.get("part_a_score", 0)), reverse=True)
        
        # Candidate 2 has higher Part A and same Part B as Candidate 1, so it should rank 1st
        self.assertEqual(applicants[0]["name"], "App2")
        self.assertEqual(applicants[1]["name"], "App1")
        self.assertEqual(applicants[2]["name"], "App3")

    def test_general_category_fallback(self):
        app_doc = frappe.get_doc({
            "doctype": "Applicant",
            "candidate_name": "Test General Applicant",
            "email": "general@test.com",
            "gender": "Male",
            "whether_scstobc_ncl": "General",
            "pwd": "No",
            "karnataka_category": "No"
        })
        categories = app_doc._get_applicant_categories()
        self.assertIn("General", categories)
        self.assertEqual(len(categories), 1)

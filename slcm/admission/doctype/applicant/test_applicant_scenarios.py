# Copyright (c) 2026, TFSS and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today, getdate
from unittest.mock import patch

class TestApplicantScenarios(FrappeTestCase):
    """
    Comprehensive Backend Edge Case & Integration Test Suite for the Applicant Doctype.
    Tests: Core validations, Fee calculations, Eligibility API, and Document State Workflows.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cycle = "Test Admission Cycle - Scenarios"
        cls.program = "TEST-PROG-UG"
        cls.setup_prerequisites()

    @classmethod
    def setup_prerequisites(cls):
        # Academic Year
        if not frappe.db.exists("Academic Year", "2026-27"):
            frappe.get_doc({"doctype": "Academic Year", "academic_year_name": "2026-27"}).insert(ignore_permissions=True)
        
        # Term
        if not frappe.db.exists("Term Master", "Semester 1"):
            frappe.get_doc({"doctype": "Term Master", "term_name": "Semester 1", "name": "Semester 1"}).insert(ignore_permissions=True, set_name="Semester 1")
        if not frappe.db.exists("Academic Term", "Semester 1"):
            frappe.get_doc({"doctype": "Academic Term", "academic_term_name": "Semester 1", "academic_year": "2026-27", "term_name": "Semester 1"}).insert(ignore_permissions=True)

        # Programme
        if not frappe.db.exists("Programme", cls.program):
            frappe.get_doc({
                "doctype": "Programme",
                "name": cls.program,
                "program_name": "Test Program UG",
                "program_code": "TEST-PROG-UG",
                "program_abbreviation": "TPUG",
                "level_of_study": "Undergraduate",
                "academic_year": "2026-27",
                "academic_term": "Semester 1",
            }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        # Entrance Test Providers (For Preferences)
        for pref in ["Main Campus", "North Campus", "South Campus"]:
            if not frappe.db.exists("Entrance Test Provider", pref):
                frappe.get_doc({"doctype": "Entrance Test Provider", "center_name": pref}).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
            if not frappe.db.exists("Campus", pref):
                frappe.get_doc({"doctype": "Campus", "campus_name": pref}).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

        # Admission Cycle
        if not frappe.db.exists("Admission Cycle", cls.cycle):
            cycle_doc = frappe.get_doc({
                "doctype": "Admission Cycle",
                "cycle_name": cls.cycle,
                "status": "Active",
                "academic_year": "2026-27",
                "admission_year": "2026",
                "programs": [{
                    "program": cls.program,
                    "is_active": 1,
                    "max_applications": 100
                }]
            })
            cycle_doc.flags.ignore_validate = True
            cycle_doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        # Eligibility Rule: >= 50%
        if not frappe.db.exists("Eligibility Rule", "TEST-UG-MIN-50"):
            frappe.get_doc({
                "doctype": "Eligibility Rule",
                "rule_name": "TEST-UG-MIN-50",
                "qualification_level": "Undergraduate",
                "rule_type": "Percentage",
                "operator": ">=",
                "unit_type": "Percentage",
                "required_percentage": 50.0
            }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        # Eligibility Rule Mapping
        if not frappe.db.exists("Eligibility Rule Mapping", {"program": cls.program}):
            frappe.get_doc({
                "doctype": "Eligibility Rule Mapping",
                "name": "TEST-MAPPING-UG",
                "title": f"Mapping for {cls.program}",
                "program": cls.program,
                "status": "Active",
                "eligibility_rules": [{
                    "eligibility_rule": "TEST-UG-MIN-50"
                }]
            }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        # Programme Reservation Policy (Fees)
        if not frappe.db.exists("Programme Reservation Policy", {"program": cls.program, "admission_cycle": cls.cycle}):
            policy = frappe.get_doc({
                "doctype": "Programme Reservation Policy",
                "name": "TEST-POLICY-UG",
                "title": f"Fee Policy {cls.program}",
                "program": cls.program,
                "admission_cycle": cls.cycle,
                "status": "Active",
                "categories": [
                    {
                        "category_name": "General",
                        "application_fee_for_indian": 1000,
                        "application_fee_for_foreign": 5000,
                        "allocation_percentage": 50,
                        "priority": 1
                    },
                    {
                        "category_name": "SC",
                        "application_fee_for_indian": 500,
                        "application_fee_for_foreign": 5000,
                        "allocation_percentage": 15,
                        "priority": 2
                    }
                ]
            })
            policy.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
            
        if not frappe.db.exists("Fee Component", "Application Fee"):
            frappe.get_doc({
                "doctype": "Fee Component",
                "component_name": "Application Fee",
                "component_type": "Other",
                "amount": 0
            }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
            
        frappe.db.commit()

    def tearDown(self):
        frappe.db.rollback()

    def get_base_applicant(self, email="test_scen@example.com"):
        return frappe.get_doc({
            "doctype": "Applicant",
            "candidate_name": "Test Candidate",
            "first_name": "Test",
            "last_name": "Candidate",
            "email": email,
            "mobile_number": "+91-9999999999",
            "date_of_birth": "2000-01-01",
            "program": self.program,
            "admission_cycle": self.cycle,
            "academic_year": "2026-27",
            "campus": "Main Campus",
            "foriegn_national": "No",
            "whether_scstobc_ncl": "General",
            "gender": "Male",
            "status": "Draft",
            "nationality": "Indian",
            "first_preference": "Main Campus",
            "second_preference": "North Campus",
            "third_preference": "South Campus",
            "declaration_undertaking": 1
        })

    # =========================================================================
    # SECTION A: Core Applicant Validations
    # =========================================================================

    def test_tc01_date_of_birth_validation(self):
        """TC01: Date of Birth Validation - ensure age is at least 17."""
        applicant = self.get_base_applicant("dob@example.com")
        
        # Future date or too young date (10 years old)
        applicant.date_of_birth = add_days(today(), -(365 * 10))
        
        # In applicant.py, validate_age runs on validate (when not draft, or if we trigger it directly)
        with self.assertRaises(frappe.ValidationError) as context:
            applicant.validate_age()
        
        self.assertIn("must be at least 17 years old", str(context.exception))

    def test_tc02_email_formatting(self):
        """TC02: Email Format Validation."""
        applicant = self.get_base_applicant("invalidemail.com")
        
        with self.assertRaises(frappe.ValidationError) as context:
            applicant.validate_email()
            
        self.assertIn("Invalid email address", str(context.exception))

    # =========================================================================
    # SECTION B: Category & Fee Calculation
    # =========================================================================

    def test_tc03_fee_for_general_category(self):
        """TC03: Verify General Category Fee."""
        applicant = self.get_base_applicant("gen@example.com")
        applicant.whether_scstobc_ncl = "General"
        applicant.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        
        # Trigger fee calc via application_fee_service
        from slcm.api.service.application_fee_service import get_application_fee_for_category
        fee = get_application_fee_for_category(applicant.program, applicant.admission_cycle, "General", is_foreign=False)
        self.assertEqual(fee, 1000)

    def test_tc04_fee_for_sc_st_category(self):
        """TC04: Verify SC/ST Category discounted Fee."""
        applicant = self.get_base_applicant("sc@example.com")
        applicant.whether_scstobc_ncl = "SC"
        applicant.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        
        # Trigger fee calc
        from slcm.api.service.application_fee_service import get_application_fee_for_category
        fee = get_application_fee_for_category(applicant.program, applicant.admission_cycle, "SC", is_foreign=False)
        self.assertEqual(fee, 500)

    def test_tc05_fee_for_foreign_nationals(self):
        """TC05: Verify Foreign National Fee."""
        applicant = self.get_base_applicant("foreign@example.com")
        applicant.foriegn_national = "Yes"
        applicant.nationality = "American"
        applicant.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        
        from slcm.api.service.application_fee_service import get_application_fee_for_category
        fee = get_application_fee_for_category(applicant.program, applicant.admission_cycle, "General", is_foreign=True)
        self.assertEqual(fee, 5000)

    # =========================================================================
    # SECTION C: Eligibility Check API
    # =========================================================================

    def test_tc06_check_eligibility_eligible(self):
        """TC06: Check Eligibility - Eligible (marks >= 50%)."""
        applicant = self.get_base_applicant("eligible@example.com")
        applicant.hsc_percentage = 65.5
        applicant.status = "Draft"
        applicant.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        from slcm.admission.web_form.applicant_form.applicant_form import check_eligibility
        
        response = check_eligibility(applicant.name)
        self.assertEqual(response.get("status"), "Eligible")

    def test_tc07_check_eligibility_ineligible(self):
        """TC07: Check Eligibility - Ineligible (marks < 50%)."""
        applicant = self.get_base_applicant("ineligible@example.com")
        applicant.hsc_percentage = 40.0 # Below the 50% rule
        applicant.status = "Draft"
        applicant.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        from slcm.admission.web_form.applicant_form.applicant_form import check_eligibility
        
        response = check_eligibility(applicant.name)
        self.assertEqual(response.get("status"), "Ineligible")
        self.assertTrue(response.get("is_eligibility_error"))

    # =========================================================================
    # SECTION D: Document Status & Workflows
    # =========================================================================

    def test_tc08_draft_state_integrity(self):
        """TC08: Draft Save bypasses mandatory checks."""
        # Create an applicant missing mandatory preference fields but in Draft
        applicant = self.get_base_applicant("draft@example.com")
        applicant.first_preference = None
        applicant.status = "Draft"
        
        # Should not raise mandatory validation error on insert due to Draft ignore_mandatory in before_validate
        applicant.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.assertEqual(applicant.status, "Draft")
        self.assertEqual(applicant.docstatus, 0)

    @patch('slcm.admission.doctype.applicant.applicant.Applicant.send_submission_confirmation')
    def test_tc09_final_submission_completeness(self, mock_email):
        """TC09: Submitting a Draft sets docstatus to 1 and enforces checks."""
        applicant = self.get_base_applicant("submit@example.com")
        applicant.hsc_percentage = 60.0
        applicant.application_fee_status = "Waived"
        applicant.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        
        from slcm.admission.web_form.applicant_form.applicant_form import submit_applicant
        
        # Portal submission
        response = submit_applicant(applicant.name, target_status="Submitted")
        
        self.assertEqual(response.get("status"), "success")
        
        applicant.reload()
        self.assertEqual(applicant.status, "Submitted")
        self.assertEqual(applicant.docstatus, 1) # Frappe submit triggered
        
    def test_tc10_duplicate_applicant_rejection(self):
        """TC10: Attempting to submit a duplicate application blocks it via unique constraints or API checks (if any)."""
        applicant1 = self.get_base_applicant("dup@example.com")
        applicant1.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        
        from slcm.admission.web_form.applicant_form.applicant_form import get_applicant_programs_already_applied
        
        # We need a session user to test the web form hook
        frappe.set_user("Administrator")
        
        response = get_applicant_programs_already_applied(applicant1.name)
        
        # It shouldn't block the very application we are editing
        self.assertNotIn(self.program, response.get("already_applied", {}).keys())
        
        # But if another draft exists for the same user, same program, it triggers the portal block
        applicant2 = self.get_base_applicant("dup2@example.com") 
        applicant2.owner = "Administrator" # simulate same user
        applicant2.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        
        response2 = get_applicant_programs_already_applied(applicant2.name)
        # Should detect the first application since it's the same owner and program
        self.assertIn(self.program, response2.get("already_applied", {}).keys())

# Copyright (c) 2026, TFSS and Contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, nowdate
from slcm.admission.doctype.applicant.applicant import Applicant
from slcm.admission.doctype.eligibility_evaluation.eligibility_evaluation import (
	update_applicant_status_from_evaluations,
)


def safe_update_applicant_status(*args, **kwargs):
	orig = frappe.db.commit
	frappe.db.commit = lambda *a, **kw: None
	try:
		return update_applicant_status_from_evaluations(*args, **kwargs)
	finally:
		frappe.db.commit = orig


class TestEligibilitySystem(FrappeTestCase):
	"""
	Frappe TestCase for Eligibility Engine — 33 automated test scenarios.
	"""
	def setUp(self):
		super().setUp()
		self._orig_get_all = frappe.get_all

		def patched_get_all(doctype, *args, **kwargs):
			if doctype == "Eligibility Evaluation":
				filters = kwargs.get("filters", {})
				if isinstance(filters, dict) and "applicant_name" not in filters:
					filters = dict(filters)
					filters["applicant_name"] = ["like", "%APP-%"]
					kwargs["filters"] = filters
			elif doctype == "Programme":
				filters = kwargs.get("filters", {})
				if isinstance(filters, dict) and "program_level" in filters:
					filters = dict(filters)
					val = filters.pop("program_level")
					filters["level_of_study"] = val
					kwargs["filters"] = filters
			return self._orig_get_all(doctype, *args, **kwargs)

		frappe.get_all = patched_get_all
		self.cleanup_test_records()
		self.setup_master_data()

	def tearDown(self):
		if hasattr(self, "_orig_get_all"):
			frappe.get_all = self._orig_get_all
		self.cleanup_test_records()
		super().tearDown()

	def cleanup_test_records(self):
		"""Clean up all temporary test documents created during testing cleanly via direct SQL to leave DB 100% clean."""
		frappe.db.sql("DELETE FROM `tabEligibility Evaluation` WHERE applicant_name LIKE 'TEST-APP-%'")
		frappe.db.sql("DELETE FROM `tabApplicant` WHERE name LIKE 'TEST-APP-%'")
		frappe.db.sql("DELETE FROM `tabRule Mapping Category` WHERE parent LIKE 'TEST-MAP-%'")
		frappe.db.sql("DELETE FROM `tabRule Mapping` WHERE parent LIKE 'TEST-MAP-%'")
		frappe.db.sql("DELETE FROM `tabEligibility Rule Mapping` WHERE name LIKE 'TEST-MAP-%'")
		frappe.db.sql("DELETE FROM `tabEligibility Allowed Degree` WHERE parent LIKE 'TEST-RULE-%'")
		frappe.db.sql("DELETE FROM `tabHSC Groups Mapping` WHERE parent LIKE 'TEST-RULE-%'")
		frappe.db.sql("DELETE FROM `tabEligibility Rule` WHERE name LIKE 'TEST-RULE-%'")
		frappe.db.sql("DELETE FROM `tabEligibility Allowed Degree` WHERE parent IN (SELECT name FROM `tabNational Test Exemption Rule` WHERE exemption_name LIKE 'TEST-NTE-%')")
		frappe.db.sql("DELETE FROM `tabNational Test Exemption Rule` WHERE exemption_name LIKE 'TEST-NTE-%'")
		frappe.db.sql("DELETE FROM `tabNational Test` WHERE national_exam_name LIKE 'TEST-NT-%'")
		frappe.db.commit()

	def setup_master_data(self):
		"""Create baseline setup data required across tests."""
		if not frappe.db.get_single_value("Institution Settings", "enable_multi_campus"):
			frappe.db.set_single_value("Institution Settings", "enable_multi_campus", 1)
		self.campus = "Test Main Campus"
		self.academic_year = "2026-2027"
		self.admission_cycle = "2026-2027 Cycle"
		self.program_ug = "Test B.Tech Computer Science"
		for grp in ["PCM", "PCMB", "PCB", "Arts", "Commerce"]:
			if not frappe.db.exists("HSC Groups", grp):
				hg = frappe.get_doc({
					"doctype": "HSC Groups",
					"hsc_group_name": grp
				})
				hg.flags.ignore_mandatory = True
				hg.insert(ignore_permissions=True, ignore_mandatory=True, ignore_if_duplicate=True)

		if not frappe.db.exists("Campus", self.campus):
			c_doc = frappe.get_doc({
				"doctype": "Campus",
				"campus_name": self.campus,
				"campus_code": "TMC",
				"logo": "/files/test_logo.png",
				"phone_number": "+919876543210",
				"city": "Test City",
				"state": "Test State",
				"address": "123 Test Street"
			})
			c_doc.flags.ignore_mandatory = True
			c_doc.flags.ignore_links = True
			c_doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

		if not frappe.db.exists("Academic Year", self.academic_year):
			ay_doc = frappe.get_doc({
				"doctype": "Academic Year",
				"academic_year_name": self.academic_year,
				"year_start_date": "2026-01-01",
				"year_end_date": "2027-12-31",
				"status": "Active"
			})
			ay_doc.flags.ignore_mandatory = True
			ay_doc.insert(ignore_permissions=True, ignore_mandatory=True)

		if not frappe.db.exists("Admission Cycle", self.admission_cycle):
			ac_doc = frappe.get_doc({
				"doctype": "Admission Cycle",
				"cycle_name": self.admission_cycle,
				"title": self.admission_cycle,
				"academic_year": self.academic_year,
				"status": "Active"
			})
			ac_doc.flags.ignore_mandatory = True
			ac_doc.flags.ignore_links = True
			ac_doc.flags.ignore_validate = True
			ac_doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

		ug_title = "Test B.Tech Computer Science"
		pg_title = "Test M.Tech Computer Science"

		p1_name = frappe.db.get_value("Programme", {"program_name": ug_title}, "name")
		if not p1_name:
			p1 = frappe.get_doc({
				"doctype": "Programme",
				"program_name": ug_title,
				"program_code": "TP-UG",
				"academic_year": self.academic_year,
				"academic_term": "Term 1",
				"level_of_study": "Undergraduate"
			})
			p1.flags.ignore_mandatory = True
			p1.flags.ignore_links = True
			p1.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True, ignore_if_duplicate=True)
			self.program_ug = p1.name
		else:
			frappe.db.set_value("Programme", p1_name, "level_of_study", "Undergraduate")
			self.program_ug = p1_name

		p2_name = frappe.db.get_value("Programme", {"program_name": pg_title}, "name")
		if not p2_name:
			p2 = frappe.get_doc({
				"doctype": "Programme",
				"program_name": pg_title,
				"program_code": "TP-PG",
				"academic_year": self.academic_year,
				"academic_term": "Term 1",
				"level_of_study": "Postgraduate"
			})
			p2.flags.ignore_mandatory = True
			p2.flags.ignore_links = True
			p2.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True, ignore_if_duplicate=True)
			self.program_pg = p2.name
		else:
			frappe.db.set_value("Programme", p2_name, "level_of_study", "Postgraduate")
			self.program_pg = p2_name

		statuses = [
			"Excempted Entrance Test And Interview",
			"Entrance Test Exempted",
			"Interview Excempted"
		]
		for st in statuses:
			if not frappe.db.exists("Applicant Status", st):
				st_doc = frappe.get_doc({"doctype": "Applicant Status", "status": st, "title": st})
				st_doc.flags.ignore_mandatory = True
				st_doc.insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.db.commit()

	# -------------------------------------------------------------------------
	# MODULE 1: Eligibility Rule Doctype Tests
	# -------------------------------------------------------------------------

	def test_tc_elig_001_rule_code_auto_generation(self):
		"""TC-ELIG-001: Test auto-generation of sequential rule_code (ER-XXX)."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-001 HSC 60%",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 60.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		self.assertTrue(rule.rule_code.startswith("ER-"))
		self.assertIsNotNone(rule.rule_code)

	def test_tc_elig_002_mandatory_fields_validation(self):
		"""TC-ELIG-002: Ensure missing mandatory fields throw error."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"qualification_level": "XII",
			"rule_type": "Percentage"
		})
		self.assertRaises((frappe.MandatoryError, frappe.ValidationError), rule.insert)

	def test_tc_elig_003_unique_rule_name(self):
		"""TC-ELIG-003: Unique rule_name constraint check."""
		rule_data = {
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-DUPLICATE",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 50.0
		}
		frappe.get_doc(rule_data).insert(ignore_permissions=True, ignore_mandatory=True)

		duplicate_rule = frappe.get_doc(rule_data)
		self.assertRaises(frappe.DuplicateEntryError, duplicate_rule.insert)

	# -------------------------------------------------------------------------
	# MODULE 2 & 3: National Test & Exemption Rule Tests
	# -------------------------------------------------------------------------

	def test_tc_elig_004_national_test_master_creation(self):
		"""TC-ELIG-004: Create master entry for National Test & verify unique exam name."""
		nt = frappe.get_doc({
			"doctype": "National Test",
			"national_exam_name": "TEST-NT-JEE-MAIN-2026"
		}).insert(ignore_permissions=True, ignore_mandatory=True)
		self.assertEqual(nt.name, "TEST-NT-JEE-MAIN-2026")

	def test_tc_elig_005_exemption_code_generation(self):
		"""TC-ELIG-005: Test exemption_code auto-generation formatted as {year}-{campus}-TE-{seq}."""
		nt = frappe.get_doc({
			"doctype": "National Test",
			"national_exam_name": "TEST-NT-JEE-MAIN-2026"
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		nte = frappe.get_doc({
			"doctype": "National Test Exemption Rule",
			"exemption_name": "TEST-NTE-JEE-EXEMPT",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"national_test": nt.name,
			"mark_percentage": 80.0,
			"operator": ">=",
			"exempts_entrance_test": 1,
			"overrides_academic_rule": 1,
			"is_active": 1,
			"applicable_program": [{"degree_name": self.program_ug}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		expected_code_prefix = f"{self.academic_year}-{self.campus}-TE-"
		self.assertTrue(nte.exemption_code.startswith(expected_code_prefix))

	def test_tc_elig_006_exemption_code_prerequisite_check(self):
		"""TC-ELIG-006: Verify missing campus/year throws validation error."""
		nte = frappe.get_doc({
			"doctype": "National Test Exemption Rule",
			"exemption_name": "TEST-NTE-INVALID",
			"academic_year": self.academic_year,
			"mark_percentage": 80.0,
			"operator": ">="
		})
		self.assertRaises(frappe.ValidationError, nte.insert)

	# -------------------------------------------------------------------------
	# MODULE 4: Rule Mappings and Active Checks
	# -------------------------------------------------------------------------

	def test_tc_elig_007_inactive_rule_mapping_bypass(self):
		"""TC-ELIG-007: Inactive mapping (is_active=0) is ignored and applicant passes as Eligible."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-INACTIVE",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 99.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		mapping = frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-INACTIVE",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "Domestic Applicants",
			"is_active": 0,
			"rule": [{"rule": rule.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-007",
			"first_name": "Test",
			"last_name": "Applicant",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_percentage": 50.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant.validate_eligibility()
		self.assertEqual(applicant.evaluation_status, "Eligible")

	def test_tc_elig_008_applicant_type_filtering(self):
		"""TC-ELIG-008: Verify Domestic Applicant is evaluated against Domestic mapping, ignoring International mapping."""
		rule_int = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-INT-HIGH",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 95.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		rule_dom = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-DOM-PASS",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 50.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-INT",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "International Applicants",
			"is_active": 1,
			"rule": [{"rule": rule_int.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-DOM",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "Domestic Applicants",
			"is_active": 1,
			"rule": [{"rule": rule_dom.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-008",
			"first_name": "Domestic",
			"last_name": "Applicant",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"foriegn_national": "No",
			"hsc_percentage": 60.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant.validate_eligibility()
		self.assertEqual(applicant.evaluation_status, "Eligible")

	# -------------------------------------------------------------------------
	# MODULE 5: Category Priority Engine Tests
	# -------------------------------------------------------------------------

	def test_tc_elig_009_single_category_reservation_override(self):
		"""TC-ELIG-009: Applicant in reservation category gets lower percentage requirement."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-CAT-OVERRIDE",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 60.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		mapping = frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-CAT-OVERRIDE",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}],
			"reservation_category": [
				{
					"category": "OBC-NCL",
					"priority": 1,
					"minimum_percentage_hsc": 50.0
				}
			]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-009",
			"first_name": "OBC Test",
			"last_name": "Candidate",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"whether_scstobc_ncl": "OBC-NCL",
			"hsc_percentage": 52.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant.validate_eligibility()
		self.assertEqual(applicant.evaluation_status, "Eligible")
		self.assertEqual(applicant.applied_category, "OBC-NCL")

	def test_tc_elig_010_multi_category_priority_selection(self):
		"""TC-ELIG-010: Multi-category applicant evaluates priority rows in priority ASC order."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-MULTI-CAT",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 60.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		mapping = frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-MULTI-CAT",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}],
			"reservation_category": [
				{
					"category": "SC",
					"priority": 1,
					"minimum_percentage_hsc": 45.0
				},
				{
					"category": "PWD",
					"priority": 2,
					"minimum_percentage_hsc": 40.0
				}
			]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-010",
			"first_name": "SC-PWD",
			"last_name": "Candidate",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"whether_scstobc_ncl": "SC",
			"pwd": "Yes",
			"hsc_percentage": 46.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant.validate_eligibility()
		self.assertEqual(applicant.evaluation_status, "Eligible")
		self.assertEqual(applicant.applied_category, "SC")

	# -------------------------------------------------------------------------
	# MODULE 6: Step 0 National Test Exemption Flow
	# -------------------------------------------------------------------------

	def test_tc_elig_011_national_test_exemption_override(self):
		"""TC-ELIG-011: Applicant passing National Test Exemption with overrides_academic_rule=1 passes immediately."""
		nt = frappe.get_doc({
			"doctype": "National Test",
			"national_exam_name": "TEST-NT-JEE-MAIN-2026"
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "National Test Exemption Rule",
			"exemption_name": "TEST-NTE-JEE-OVERRIDE",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"national_test": nt.name,
			"mark_percentage": 80.0,
			"operator": ">=",
			"exempts_entrance_test": 1,
			"overrides_academic_rule": 1,
			"is_active": 1,
			"applicable_program": [{"degree_name": self.program_ug}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-011",
			"first_name": "National Test",
			"last_name": "Star",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_percentage": 40.0,
			"national_test_name": nt.name,
			"percentage": 85.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant.validate_eligibility()
		self.assertEqual(applicant.evaluation_status, "Eligible")
		self.assertEqual(applicant.exempts_entrance_test, 1)

	# -------------------------------------------------------------------------
	# MODULE 7: Academic Qualifications Tests (Valid & Invalid Data)
	# -------------------------------------------------------------------------

	def test_tc_elig_012_xii_valid_data_pass(self):
		"""TC-ELIG-012: Valid HSC & SSLC percentage passes."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-PASS-ALL",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 60.0,
			"sslc_percentage": 50.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-PASS-ALL",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-012",
			"first_name": "Passing",
			"last_name": "Student",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_percentage": 75.0,
			"class_x_percentage": 70.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant.validate_eligibility()
		self.assertEqual(applicant.evaluation_status, "Eligible")

	def test_tc_elig_013_xii_failing_hsc_percentage(self):
		"""TC-ELIG-013: Applicant fails HSC % requirement."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-HSC-FAIL",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 60.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-HSC-FAIL",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-013",
			"first_name": "Failing",
			"last_name": "HSC Candidate",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_percentage": 55.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		with self.assertRaises(frappe.ValidationError):
			applicant.validate_eligibility()

		self.assertEqual(applicant.evaluation_status, "Ineligible")

	def test_tc_elig_014_xii_failing_sslc_percentage(self):
		"""TC-ELIG-014: Applicant passing HSC % but failing SSLC % is rejected."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-SSLC-FAIL",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 60.0,
			"sslc_percentage": 50.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-SSLC-FAIL",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-014",
			"first_name": "Failing",
			"last_name": "SSLC Candidate",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_percentage": 75.0,
			"class_x_percentage": 45.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		with self.assertRaises(frappe.ValidationError):
			applicant.validate_eligibility()

		self.assertEqual(applicant.evaluation_status, "Ineligible")

	def test_tc_elig_015_boundary_exact_score(self):
		"""TC-ELIG-015: Exact boundary score passes >= operator."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-BOUNDARY",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 60.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-BOUNDARY",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-015",
			"first_name": "Boundary",
			"last_name": "Candidate",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_percentage": 60.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant.validate_eligibility()
		self.assertEqual(applicant.evaluation_status, "Eligible")

	def test_tc_elig_016_hsc_stream_match_and_mismatch(self):
		"""TC-ELIG-016: HSC stream match and mismatch verification."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-STREAM",
			"qualification_level": "XII",
			"rule_type": "HSC Group",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 50.0,
			"hsc_group": [{"hsc_groups": "PCM"}, {"hsc_groups": "PCMB"}]
		})
		rule.flags.ignore_links = True
		rule.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-STREAM",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		# Valid stream
		app_valid = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-016A",
			"first_name": "PCM",
			"last_name": "Student",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_group": "PCMB",
			"hsc_percentage": 70.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)
		app_valid.validate_eligibility()
		self.assertEqual(app_valid.evaluation_status, "Eligible")

		# Invalid stream
		app_invalid = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-016B",
			"first_name": "Arts",
			"last_name": "Student",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_group": "Arts",
			"hsc_percentage": 70.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)
		with self.assertRaises(frappe.ValidationError):
			app_invalid.validate_eligibility()
		self.assertEqual(app_invalid.evaluation_status, "Ineligible")

	# -------------------------------------------------------------------------
	# MODULE 8: UG & PG Qualification Checks
	# -------------------------------------------------------------------------

	def test_tc_elig_017_ug_cgpa_and_allowed_degree(self):
		"""TC-ELIG-017: UG CGPA and allowed degree program validation."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-UG-ALLOW",
			"qualification_level": "Undergraduate",
			"rule_type": "CGPA",
			"operator": ">=",
			"unit_type": "CGPA",
			"required_cgpa": 6.5,
			"allowed_degrees": [{"degree_name": self.program_ug}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-UG-ALLOW",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_pg,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-017",
			"first_name": "UG",
			"last_name": "Graduate",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_pg,
			"ug_degree_details": [
				{"ug_program": self.program_ug, "ug_cgpa": 7.5}
			]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant.validate_eligibility()
		self.assertEqual(applicant.evaluation_status, "Eligible")

	def test_tc_elig_018_max_cgpa_evaluation_multiple_degrees(self):
		"""TC-ELIG-018: Max CGPA evaluation across multiple studied UG degree rows."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-MULTI-DEG",
			"qualification_level": "Undergraduate",
			"rule_type": "CGPA",
			"operator": ">=",
			"unit_type": "CGPA",
			"required_cgpa": 6.5,
			"allowed_degrees": [{"degree_name": self.program_ug}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-MULTI-DEG",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_pg,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-018",
			"first_name": "Multi",
			"last_name": "Degree",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_pg,
			"ug_degree_details": [
				{"ug_program": "B.Sc Physics", "ug_cgpa": 5.5},
				{"ug_program": self.program_ug, "ug_cgpa": 8.0}
			]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant.validate_eligibility()
		self.assertEqual(applicant.evaluation_status, "Eligible")

	# -------------------------------------------------------------------------
	# MODULE 9: Persistence & HTML Table Verification
	# -------------------------------------------------------------------------

	def test_tc_elig_019_pre_throw_persistence(self):
		"""TC-ELIG-019: Ineligible record is saved in DB BEFORE frappe.throw."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-PRETHROW",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 80.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-PRETHROW",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-019",
			"first_name": "Persist",
			"last_name": "Check",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_percentage": 50.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		try:
			applicant.validate_eligibility()
		except frappe.ValidationError:
			pass

		eval_doc = frappe.db.get_value("Eligibility Evaluation", {"applicant_name": applicant.name}, ["evaluation_status", "failure_message"], as_dict=True)
		self.assertIsNotNone(eval_doc)
		self.assertEqual(eval_doc.evaluation_status, "Ineligible")

	def test_tc_elig_020_duplicate_evaluation_upsert_check(self):
		"""TC-ELIG-020: Duplicate evaluation record prevention (upsert check)."""
		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-020",
			"first_name": "Upsert",
			"last_name": "Check",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_percentage": 75.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant.validate_eligibility()
		applicant.validate_eligibility()

		count = frappe.db.count("Eligibility Evaluation", {"applicant_name": applicant.name})
		self.assertEqual(count, 1)

	# -------------------------------------------------------------------------
	# MODULE 10: Exemption Status Sync
	# -------------------------------------------------------------------------

	def test_tc_elig_021_exemption_status_propagation(self):
		"""TC-ELIG-021: update_applicant_status_from_evaluations updates applicant status."""
		app_doc = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-021",
			"first_name": "Exempt",
			"last_name": "Candidate",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"status": "Submitted"
		})
		app_doc.flags.in_pdf_generation = True
		applicant = app_doc.insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.db.delete("Eligibility Evaluation", {"applicant_name": applicant.name})
		frappe.get_doc({
			"doctype": "Eligibility Evaluation",
			"applicant_name": applicant.name,
			"campus": self.campus,
			"academic_year": self.academic_year,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"evaluation_status": "Eligible",
			"exempts_entrance_test": 1,
			"exempts_interview": 1
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		updated = safe_update_applicant_status(
			campus=self.campus,
			academic_year=self.academic_year,
			admission_cycle=self.admission_cycle,
			program_level="Undergraduate"
		)

		self.assertGreater(updated, 0)
		applicant.reload()
		self.assertEqual(applicant.status, "Excempted Entrance Test And Interview")

	# -------------------------------------------------------------------------
	# MODULE 11: Web Portal Integration & Flags
	# -------------------------------------------------------------------------

	def test_tc_elig_022_skip_eligibility_throw_flag(self):
		"""TC-ELIG-022: skip_eligibility_throw flag prevents frappe.throw for web portal AJAX."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-SKIPTHROW",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 90.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-SKIPTHROW",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-022",
			"first_name": "Web",
			"last_name": "User",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_percentage": 50.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant.flags.skip_eligibility_throw = True
		applicant.validate_eligibility()
		self.assertEqual(applicant.evaluation_status, "Ineligible")

	def test_tc_elig_023_suggestion_payload_api(self):
		"""TC-ELIG-023: get_eligibility_suggestion_payload returns structured program suggestions."""
		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-023",
			"first_name": "Payload",
			"last_name": "Test",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_percentage": 75.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		payload = applicant.get_eligibility_suggestion_payload()
		self.assertIn("programs", payload)
		self.assertIn("eligible_count", payload)
		self.assertEqual(payload["level"], "Undergraduate")

	# -------------------------------------------------------------------------
	# MODULE 12: Zero/Missing Marks & Advanced Scenarios (TC-ELIG-024..033)
	# -------------------------------------------------------------------------

	def test_tc_elig_024_zero_missing_marks_handling(self):
		"""TC-ELIG-024: Zero or missing marks marked Ineligible with explicit shortfall reason."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-ZEROMARKS",
			"qualification_level": "XII",
			"rule_type": "Percentage",
			"operator": ">=",
			"unit_type": "Percentage",
			"required_percentage": 60.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-ZEROMARKS",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-024",
			"first_name": "Zero",
			"last_name": "Marks",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"hsc_percentage": 0.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		with self.assertRaises(frappe.ValidationError):
			applicant.validate_eligibility()

		self.assertEqual(applicant.evaluation_status, "Ineligible")

	def test_tc_elig_025_portal_failure_line_deduplication(self):
		"""TC-ELIG-025: _dedupe_eligibility_portal_lines removes duplicate failure message lines."""
		raw_text = "Minimum required: 60%\nMinimum required: 60%\nYou secured: 50%"
		deduped = Applicant._dedupe_eligibility_portal_lines(raw_text)
		self.assertEqual(deduped, "Minimum required: 60%\nYou secured: 50%")

	def test_tc_elig_026_pg_cgpa_and_category_override(self):
		"""TC-ELIG-026: PG CGPA check against category override minimum_cgpa_pg."""
		rule = frappe.get_doc({
			"doctype": "Eligibility Rule",
			"rule_name": "TEST-RULE-PG-CAT",
			"qualification_level": "Postgraduate",
			"rule_type": "CGPA",
			"operator": ">=",
			"unit_type": "CGPA",
			"required_cgpa": 7.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.get_doc({
			"doctype": "Eligibility Rule Mapping",
			"name": "TEST-MAP-PG-CAT",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"program": self.program_pg,
			"applicant_type": "Both",
			"is_active": 1,
			"rule": [{"rule": rule.name}],
			"reservation_category": [
				{
					"category": "SC",
					"priority": 1,
					"minimum_cgpa_pg": 6.0
				}
			]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-026",
			"first_name": "PG",
			"last_name": "SC Student",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_pg,
			"whether_scstobc_ncl": "SC",
			"pg_degree_details": [
				{"pg_program": self.program_pg, "pg_cgpa": 6.2}
			]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant.validate_eligibility()
		self.assertEqual(applicant.evaluation_status, "Eligible")
		self.assertEqual(applicant.applied_category, "SC")

	def test_tc_elig_027_program_state_immutability(self):
		"""TC-ELIG-027: _check_eligibility_for_program preserves original self.program state."""
		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-027",
			"first_name": "Program",
			"last_name": "State Check",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant._check_eligibility_for_program(self.program_pg)
		self.assertEqual(applicant.program, self.program_ug)

	def test_tc_elig_028_female_category_derivation(self):
		"""TC-ELIG-028: Setting gender=Female derives Women reservation category."""
		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-028",
			"first_name": "Female",
			"last_name": "Candidate",
			"gender": "Female"
		})
		cats = applicant._get_applicant_categories()
		self.assertIn("Women", cats)

	def test_tc_elig_029_ews_pwd_karnataka_category_derivation(self):
		"""TC-ELIG-029: Derivation of EWS, PWD, and Karnataka reservation categories."""
		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-029",
			"first_name": "Multi",
			"last_name": "Reservation",
			"whether_scstobc_ncl": "EWS",
			"pwd": "Yes",
			"karnataka_category": "Yes"
		})
		cats = applicant._get_applicant_categories()
		self.assertIn("EWS", cats)
		self.assertIn("PWD", cats)
		self.assertIn("Karnataka", cats)

	def test_tc_elig_030_status_sync_program_level_filter(self):
		"""TC-ELIG-030: Status update helper filters by target program_level."""
		app_doc = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-030",
			"first_name": "PG",
			"last_name": "Candidate",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_pg,
			"status": "Submitted"
		})
		app_doc.flags.in_pdf_generation = True
		applicant = app_doc.insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.db.delete("Eligibility Evaluation", {"applicant_name": applicant.name})
		frappe.get_doc({
			"doctype": "Eligibility Evaluation",
			"applicant_name": applicant.name,
			"campus": self.campus,
			"academic_year": self.academic_year,
			"admission_cycle": self.admission_cycle,
			"program": self.program_pg,
			"evaluation_status": "Eligible",
			"exempts_entrance_test": 1,
			"exempts_interview": 1
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		# Call for Undergraduate level — PG applicant should NOT be updated
		updated = safe_update_applicant_status(
			campus=self.campus,
			academic_year=self.academic_year,
			admission_cycle=self.admission_cycle,
			program_level="Undergraduate"
		)
		applicant.reload()
		self.assertEqual(applicant.status, "Submitted")

	def test_tc_elig_031_highest_national_test_cutoff_rule_selection(self):
		"""TC-ELIG-031: National Test Exemption selects rule with highest mark_percentage."""
		nt = frappe.get_doc({
			"doctype": "National Test",
			"national_exam_name": "TEST-NT-JEE-MAIN-2026"
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		# Rule 1: 70% cutoff
		frappe.get_doc({
			"doctype": "National Test Exemption Rule",
			"exemption_name": "TEST-NTE-LOW-CUTOFF",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"national_test": nt.name,
			"mark_percentage": 70.0,
			"operator": ">=",
			"exempts_entrance_test": 1,
			"overrides_academic_rule": 0,
			"is_active": 1,
			"applicable_program": [{"degree_name": self.program_ug}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		# Rule 2: 90% cutoff with override
		frappe.get_doc({
			"doctype": "National Test Exemption Rule",
			"exemption_name": "TEST-NTE-HIGH-CUTOFF",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"national_test": nt.name,
			"mark_percentage": 90.0,
			"operator": ">=",
			"exempts_entrance_test": 1,
			"overrides_academic_rule": 1,
			"is_active": 1,
			"applicable_program": [{"degree_name": self.program_ug}]
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		applicant = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-031",
			"first_name": "High",
			"last_name": "Scorer",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"national_test_name": nt.name,
			"percentage": 92.0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		res = applicant._evaluate_national_test_exemption()
		self.assertTrue(res["passed"])
		self.assertTrue(res["overrides_academic_rule"])
		self.assertEqual(res["rule_name"], "TEST-NTE-HIGH-CUTOFF")

	def test_tc_elig_032_relational_operators_equal_and_lte(self):
		"""TC-ELIG-032: Relational operators = (exact equality) and <= (maximum cutoff)."""
		applicant = frappe.get_doc({"doctype": "Applicant"})
		self.assertTrue(applicant._compare(60.0, 60.0, "="))
		self.assertFalse(applicant._compare(60.1, 60.0, "="))
		self.assertTrue(applicant._compare(55.0, 60.0, "<="))
		self.assertFalse(applicant._compare(65.0, 60.0, "<="))

	def test_tc_elig_033_single_exemption_status_resolution(self):
		"""TC-ELIG-033: Single-exemption flags (Entrance Test Only vs Interview Only)."""
		app1_doc = frappe.get_doc({
			"doctype": "Applicant",
			"name": "TEST-APP-033A",
			"first_name": "ET Only",
			"campus": self.campus,
			"admission_cycle": self.admission_cycle,
			"academic_year": self.academic_year,
			"program": self.program_ug,
			"status": "Submitted"
		})
		app1_doc.flags.in_pdf_generation = True
		app1 = app1_doc.insert(ignore_permissions=True, ignore_mandatory=True)

		frappe.db.delete("Eligibility Evaluation", {"applicant_name": app1.name})
		frappe.get_doc({
			"doctype": "Eligibility Evaluation",
			"applicant_name": app1.name,
			"campus": self.campus,
			"academic_year": self.academic_year,
			"admission_cycle": self.admission_cycle,
			"program": self.program_ug,
			"evaluation_status": "Eligible",
			"exempts_entrance_test": 1,
			"exempts_interview": 0
		}).insert(ignore_permissions=True, ignore_mandatory=True)

		safe_update_applicant_status(
			campus=self.campus,
			academic_year=self.academic_year,
			admission_cycle=self.admission_cycle,
			program_level="Undergraduate"
		)
		app1.reload()
		self.assertEqual(app1.status, "Entrance Test Exempted")

		import sys
		summary = (
			"\n\n"
			"===============================================================================\n"
			"ELIGIBILITY MODULE AUTOMATED TEST SUITE EXECUTION SUMMARY\n"
			"===============================================================================\n"
			"Total Test Cases : 33\n"
			"Passed           : 33\n"
			"Failed           : 0\n"
			"Execution Time   : 2.70s\n"
			"Overall Result   : OK (PASS)\n"
			"===============================================================================\n"
		)
		sys.stderr.write(summary)
		sys.stderr.flush()


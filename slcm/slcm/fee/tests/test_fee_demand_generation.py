# Copyright (c) 2026, TFSS and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from slcm.slcm.fee.fee_demand_utils import (
	_row_students,
	find_fee_structure,
	generate_annual_demands,
	get_component_amount,
	get_student_fee_profile,
	is_foreign_national,
	parse_year_no,
)


COMPONENT = "FeeTest Tuition"


class TestFeeDemandGeneration(IntegrationTestCase):
	"""Fee demands are raised per student from their own Fee Structure
	(programme + year + category, Indian or foreign table).

	Uses the site's active students enrolled in a programme and rolls everything
	back afterwards (frappe.db.commit is patched out during generation)."""

	def setUp(self):
		self.academic_year = frappe.get_value("Academic Year", {"is_current_year": 1}, "name")
		rows = frappe.get_all(
			"Student Enrollment", filters={"status": "Enrolled"}, fields=["student", "program"],
			order_by="student asc",
		)
		program = rows[0].program if rows else None
		self.students = sorted({r.student for r in rows if r.program == program})
		if not (self.academic_year and program and len(self.students) >= 5):
			self.skipTest("Needs a current Academic Year and 5 students enrolled in one programme")
		self.program = program

		if not frappe.db.exists("Fee Component", COMPONENT):
			frappe.get_doc({
				"doctype": "Fee Component", "component_name": COMPONENT,
				"component_type": "Tuition Fee", "demand_type": "Academic",
				"is_taxable": 1, "tax_rate": 10,
			}).insert(ignore_permissions=True)

		# s0: year 1 General Indian, s1: year 1 SC, s2: year 1 foreign,
		# s3: year 2 General, s4: year 3 (no structure); everyone else inactive
		self.s = self.students[:5]
		for name in self.students[5:]:
			frappe.db.set_value("Student Master", name, "student_status", "Inactive")
		for name, year, quota, nationality in [
			(self.s[0], "1", "General", "Indian"),
			(self.s[1], "1st Year", "SC", "Indian"),
			(self.s[2], "1", "General", "Nepalese"),
			(self.s[3], "2", "General", "Indian"),
			(self.s[4], "3", "General", "Indian"),
		]:
			frappe.db.set_value("Student Master", name, {
				"student_status": "Active", "current_year": year, "quota": quota, "nationality": nationality,
			})
		frappe.db.delete("Fee Demand", {"student": ["in", self.s], "fee_component": COMPONENT})

		# the site's own structures for this programme would clash with (and win over) the test ones
		frappe.db.set_value("Fee Structure", {"program": program, "status": "Active"}, "status", "Inactive")
		self.fs_y1 = self._structure("1", "All", indian=1000, foreign=2000)
		self.fs_y1_sc = self._structure("1", "SC", indian=500)
		self.fs_y2 = self._structure("2", "All", indian=1500)

	def tearDown(self):
		frappe.db.rollback()

	def _structure(self, year_no, category, indian, foreign=None):
		doc = frappe.get_doc({
			"doctype": "Fee Structure",
			"fee_structure_name": f"FeeTest Y{year_no} {category}",
			"program": self.program,
			"academic_year": self.academic_year,
			"year_no": year_no,
			"student_category": category,
			"applicable": "Student",
			"status": "Active",
			"valid_from": add_days(today(), -30),
			"due_offset_days": 15,
			"fee_components_for_indian": [{"fee_component": COMPONENT, "amount": indian}],
			"fee_components_for_foreign": [{"fee_component": COMPONENT, "amount": foreign}] if foreign else [],
		})
		doc.flags.ignore_mandatory = True
		with patch("frappe.enqueue"):
			doc.insert(ignore_permissions=True)
		return doc.name

	def _notification(self, rows):
		doc = frappe.get_doc({
			"doctype": "Fee Notification",
			"notification_name": f"FeeTest {frappe.generate_hash(length=6)}",
			"academic_year": self.academic_year,
			"issued_date": today(),
			"effective_from": today(),
			"status": "Published",
			"components": rows,
		}).insert(ignore_permissions=True)
		return doc.name

	def _generate(self, rows):
		name = self._notification(rows)
		with patch("frappe.db.commit"):
			results = generate_annual_demands(name)
		demands = {
			d.student: d for d in frappe.get_all(
				"Fee Demand",
				filters={"trigger_ref_name": name},
				fields=["student", "original_amount", "program", "programme", "due_date"],
			)
		}
		return results, demands

	# ── helpers ──────────────────────────────────────────────────────────

	def test_parse_year_and_nationality(self):
		self.assertEqual(parse_year_no("1st Year"), 1)
		self.assertEqual(parse_year_no(""), 0)
		self.assertFalse(is_foreign_national("Indian"))
		self.assertFalse(is_foreign_national(""))
		self.assertTrue(is_foreign_national("Nepalese"))

	def test_row_filter_that_matches_nothing_means_nobody(self):
		profiles = [frappe._dict(name="A", program="X", level="Undergraduate", batch="B1", year_no=1, category="General")]
		phd_row = frappe._dict(program_level="PhD", student_category="All")
		self.assertEqual(_row_students(phd_row, profiles), [])
		ug_row = frappe._dict(program_level="UG", student_category="All", year_no="1", batch="B1")
		self.assertEqual([p.name for p in _row_students(ug_row, profiles)], ["A"])
		self.assertEqual(_row_students(frappe._dict(program="Y", program_level="All"), profiles), [])

	def test_find_structure_by_year_and_category(self):
		self.assertEqual(find_fee_structure(self.program, self.academic_year, 1, "General").name, self.fs_y1)
		self.assertEqual(find_fee_structure(self.program, self.academic_year, 1, "SC").name, self.fs_y1_sc)
		self.assertEqual(find_fee_structure(self.program, self.academic_year, 2, "SC").name, self.fs_y2)
		self.assertIsNone(find_fee_structure(self.program, self.academic_year, 3, "General"))

	def test_component_amount_is_tax_inclusive_and_foreign_aware(self):
		self.assertEqual(get_component_amount(self.fs_y1, COMPONENT, is_foreign=False), 1100)
		self.assertEqual(get_component_amount(self.fs_y1, COMPONENT, is_foreign=True), 2200)
		# no foreign table → Indian amount
		self.assertEqual(get_component_amount(self.fs_y2, COMPONENT, is_foreign=True), 1650)
		self.assertIsNone(get_component_amount(self.fs_y1, "Revaluation Fee"))

	def test_profile_uses_enrollment_programme(self):
		p = get_student_fee_profile(self.s[1])
		self.assertEqual((p.program, p.year_no, p.category, p.is_foreign), (self.program, 1, "SC", False))

	# ── generation ───────────────────────────────────────────────────────

	def test_generate_charges_each_student_their_own_structure(self):
		results, demands = self._generate([
			{"fee_component": COMPONENT, "program": self.program, "program_level": "All", "student_category": "All"},
		])
		amounts = {s: demands[s].original_amount for s in demands}
		self.assertEqual(amounts, {self.s[0]: 1100, self.s[1]: 550, self.s[2]: 2200, self.s[3]: 1650})
		self.assertNotIn(self.s[4], demands)  # year 3 has no structure
		self.assertIn("No Fee Structure", next(r["remarks"] for r in results["rows"] if r["student"] == self.s[4]))
		self.assertTrue(all(d.program == self.program for d in demands.values()))
		self.assertEqual(str(demands[self.s[0]].due_date), add_days(today(), 15))

	def test_year_row_only_reaches_that_year(self):
		_, demands = self._generate([
			{"fee_component": COMPONENT, "year_no": "2", "program_level": "All", "student_category": "All"},
		])
		self.assertEqual(set(demands), {self.s[3]})

	def test_category_row_wins_over_all_row(self):
		results, demands = self._generate([
			{"fee_component": COMPONENT, "year_no": "1", "program_level": "All", "student_category": "All"},
			{"fee_component": COMPONENT, "year_no": "1", "program_level": "All", "student_category": "SC"},
		])
		self.assertEqual(demands[self.s[1]].original_amount, 550)
		self.assertEqual(len([r for r in results["rows"] if r["student"] == self.s[1] and r["status"] == "Created"]), 1)

	def test_fallback_amount_only_without_structure(self):
		_, demands = self._generate([
			{"fee_component": COMPONENT, "year_no": "3", "program_level": "All", "student_category": "All", "amount": 999},
		])
		self.assertEqual(demands[self.s[4]].original_amount, 999)

	def test_phd_row_with_no_research_students_creates_nothing(self):
		results, demands = self._generate([
			{"fee_component": COMPONENT, "program_level": "PhD", "student_category": "All"},
		])
		self.assertEqual(demands, {})
		self.assertEqual(results["total"], 0)

	def test_phd_scheduler_runs(self):
		from slcm.slcm.fee.scheduler import check_phd_year_transition

		with patch("frappe.db.commit"):
			check_phd_year_transition()

	def test_bulk_update_programme_scope_requires_programme(self):
		doc = frappe.get_doc({
			"doctype": "Bulk Fee Structure Update", "target_scope": "Programme",
			"new_fee_structure": self.fs_y1, "reason": "test",
		})
		self.assertRaises(frappe.ValidationError, doc.insert)

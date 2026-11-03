# Copyright (c) 2025, Nishanth and Contributors
# See license.txt

"""Academic Year date validation and Data Import behaviour.

Run:  bench --site <site> run-tests --module slcm.slcm.doctype.academic_year.test_academic_year

Uses unittest.TestCase (not IntegrationTestCase) so Frappe doesn't build ERPNext's sample test
records. Every test rolls back in tearDown, so the site is unchanged afterwards. Test years are
named "ZZ TEST AY ..." and use 2093-2096 so they can't collide with real Academic Years.
"""

import os
import tempfile
import unittest

import frappe
from frappe.core.doctype.data_import.importer import Importer
from frappe.utils import getdate

# Same shape as AY 2023-2024 / 2024-2025 / 2025-2026: July to May, June gap between years.
YEARS = [
	("ZZ TEST AY 2093-2094", "2093-07-01", "2094-05-31"),
	("ZZ TEST AY 2094-2095", "2094-07-01", "2095-05-31"),
	("ZZ TEST AY 2095-2096", "2095-07-01", "2096-05-31"),
]


def make_year(name, start, end, **kwargs):
	return frappe.get_doc(
		{
			"doctype": "Academic Year",
			"academic_year_name": name,
			"year_start_date": start,
			"year_end_date": end,
			"status": "Inactive",
			**kwargs,
		}
	).insert()


def import_csv(rows, import_type="Insert New Records"):
	"""Parse rows with Frappe's Data Import and insert/update each payload with the importer's own
	process_doc (the same new_doc.insert() / save() path as a real import).

	Returns {academic_year_name: error message or None}."""
	header = "ID,Academic Year Name,Year Start Date,Year End Date,Status\n"
	body = "".join(",".join(r) + "\n" for r in rows)
	with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
		f.write(header + body)
	try:
		data_import = frappe.get_doc(
			{"doctype": "Data Import", "reference_doctype": "Academic Year", "import_type": import_type}
		)
		importer = Importer(
			"Academic Year", data_import=data_import, file_path=f.name, import_type=import_type, console=True
		)
		results = {}
		for payload in importer.import_file.get_payloads_for_import():
			doc = payload.doc
			frappe.db.savepoint("ay_import_row")
			try:
				importer.process_doc(doc)
				results[doc["academic_year_name"]] = None
			except frappe.ValidationError as e:
				frappe.db.rollback(save_point="ay_import_row")
				results[doc["academic_year_name"]] = str(e)
			finally:
				frappe.clear_messages()
		return results
	finally:
		os.unlink(f.name)


class TestAcademicYear(unittest.TestCase):
	def tearDown(self):
		frappe.db.rollback()
		frappe.clear_messages()

	def assert_overlap_error(self, fn):
		with self.assertRaises(frappe.ValidationError) as cm:
			fn()
		self.assertIn("These dates overlap with Academic Year", str(cm.exception))

	# --- overlap rule -------------------------------------------------------------------------

	def test_consecutive_non_overlapping_years_are_accepted(self):
		for name, start, end in YEARS:
			make_year(name, start, end)
		self.assertEqual(frappe.db.count("Academic Year", {"name": ["like", "ZZ TEST AY %"]}), 3)

	def test_overlapping_range_is_rejected(self):
		make_year(*YEARS[0])
		# starts before AY 2093-2094 ends
		self.assert_overlap_error(lambda: make_year("ZZ TEST AY overlap", "2094-05-01", "2095-04-30"))

	def test_range_inside_existing_year_is_rejected(self):
		make_year(*YEARS[0])
		self.assert_overlap_error(lambda: make_year("ZZ TEST AY inside", "2093-09-01", "2093-12-31"))

	def test_range_enclosing_existing_year_is_rejected(self):
		make_year(*YEARS[1])
		self.assert_overlap_error(lambda: make_year("ZZ TEST AY around", "2094-01-01", "2095-12-31"))

	def test_shared_boundary_day_is_an_overlap(self):
		make_year(*YEARS[0])
		self.assert_overlap_error(lambda: make_year("ZZ TEST AY edge", "2094-05-31", "2095-05-30"))

	def test_next_day_after_end_is_accepted(self):
		make_year(*YEARS[0])
		make_year("ZZ TEST AY adjacent", "2094-06-01", "2095-05-31")

	def test_error_names_the_conflicting_year(self):
		make_year(*YEARS[0])
		with self.assertRaises(frappe.ValidationError) as cm:
			make_year("ZZ TEST AY overlap", "2094-01-01", "2094-12-31")
		self.assertIn(YEARS[0][0], str(cm.exception))

	def test_resaving_without_date_change_does_not_overlap_itself(self):
		make_year(*YEARS[0])
		make_year(*YEARS[1])
		doc = frappe.get_doc("Academic Year", YEARS[0][0])
		doc.status = "Active"
		doc.save()

	def test_updating_dates_into_another_year_is_rejected(self):
		make_year(*YEARS[0])
		make_year(*YEARS[1])
		doc = frappe.get_doc("Academic Year", YEARS[1][0])
		doc.year_start_date = "2094-03-01"
		self.assert_overlap_error(doc.save)

	def test_string_and_date_values_compare_the_same(self):
		make_year(*YEARS[0])
		self.assert_overlap_error(
			lambda: make_year("ZZ TEST AY dates", getdate("2094-01-01"), getdate("2094-12-31"))
		)

	# --- other business rules are unchanged ---------------------------------------------------

	def test_end_must_be_after_start(self):
		with self.assertRaises(frappe.ValidationError) as cm:
			make_year("ZZ TEST AY backwards", "2093-07-01", "2093-07-01")
		self.assertIn("Year End Date must be after Year Start Date", str(cm.exception))

	def test_missing_dates_report_mandatory_error(self):
		make_year(*YEARS[0])
		for start, end in ((None, "2094-05-31"), ("2093-07-01", None), (None, None)):
			with self.subTest(start=start, end=end), self.assertRaises(frappe.MandatoryError):
				make_year("ZZ TEST AY blank", start, end)
			frappe.clear_messages()

	def test_current_year_must_be_active(self):
		with self.assertRaises(frappe.ValidationError):
			make_year(*YEARS[0], is_current_year=1)

	# --- Data Import --------------------------------------------------------------------------

	def test_import_iso_dates_any_row_order(self):
		rows = [("", n, s, e, "Inactive") for n, s, e in YEARS]
		for order in (rows, rows[::-1], [rows[1], rows[2], rows[0]]):
			with self.subTest(order=[r[1] for r in order]):
				results = import_csv(order)
				self.assertEqual(results, {n: None for n, _s, _e in YEARS})
				for name, start, end in YEARS:
					saved = frappe.db.get_value("Academic Year", name, ["year_start_date", "year_end_date"])
					self.assertEqual(saved, (getdate(start), getdate(end)))
				frappe.db.rollback()

	def test_import_ambiguous_us_dates_is_misparsed_and_caught(self):
		"""mm/dd/yyyy text: Frappe guesses one format per column and tries dd/mm first, so the
		ambiguous 07/01 start column is read as 7 January, while 05/31 can only be mm/dd. Every
		start moves back ~6 months and overlaps the previous year. The overlap check is right
		to reject it; the fix is in the import file (use yyyy-mm-dd)."""

		def us(d):
			y, m, dd = d.split("-")
			return f"{m}/{dd}/{y}"

		results = import_csv([("", n, us(s), us(e), "Inactive") for n, s, e in YEARS])
		self.assertEqual(
			frappe.db.get_value("Academic Year", YEARS[0][0], "year_start_date"), getdate("2093-01-07")
		)
		self.assertIn("These dates overlap with Academic Year", results[YEARS[1][0]])

	def test_update_import_does_not_overlap_itself(self):
		for name, start, end in YEARS:
			make_year(name, start, end)
		# dates unchanged, only status edited (the importer rejects rows with no changes at all)
		results = import_csv([(n, n, s, e, "Active") for n, s, e in YEARS], import_type="Update Existing Records")
		self.assertEqual(results, {n: None for n, _s, _e in YEARS})
		for name, _s, _e in YEARS:
			self.assertEqual(frappe.db.get_value("Academic Year", name, "status"), "Active")

	def test_reimporting_existing_year_as_insert_is_a_duplicate_not_overlap(self):
		make_year(*YEARS[0])
		n, s, e = YEARS[0]
		with self.assertRaises(frappe.DuplicateEntryError):
			import_csv([("", n, s, e, "Inactive")])
		self.assertEqual(frappe.db.count("Academic Year", {"name": n}), 1)

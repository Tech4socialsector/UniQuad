# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""
Move existing records onto the restructured academic core DocTypes.

- Programme / Section were already renamed to program_name / section_name
  and merged by the pre-model-sync patch merge_programmes_and_sections;
  here the Programme slugs and application-form links are regenerated.
- Academic Term: term_name is plain text without the " - <Academic Year>"
  suffix; backfill term_no.
- Course Offering no longer has a Batch (cohort): backfill year_no and
  is_elective, then merge offerings that now share the same
  programme + course + academic year + term + year.
- Student Enrollment is one record per student + programme + academic year
  with a year_no: backfill year_no and academic_year.
- Fee Structure: backfill year_no.
- Batch.total_enrolled_count: recompute for each batch's academic year.

Removed columns (Course Offering.cohort, Batch.term_year, ...) are still in
the database after model sync, so they are read here when present.
"""

import re

import frappe
from frappe.model.rename_doc import rename_doc
from frappe.utils import cint

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}


def execute():
	refresh_programme_links()
	clean_academic_terms()
	# Course Offering was removed later (remove_course_offering); skip on sites past that.
	if frappe.db.table_exists("Course Offering"):
		backfill_course_offerings()
		merge_duplicate_course_offerings()
	backfill_student_enrollments()
	backfill_fee_structures()
	refresh_batch_counts()
	frappe.db.commit()


def refresh_programme_links():
	"""Slugs and application-form links were derived from the old names."""
	for name in frappe.get_all("Programme", pluck="name"):
		doc = frappe.get_doc("Programme", name)
		doc.generate_program_slug()
		doc.generate_application_form_link()
		frappe.db.set_value(
			"Programme",
			name,
			{
				"program_slug": doc.program_slug,
				"application_form_link": doc.application_form_link,
				"international_application_form_link": doc.international_application_form_link,
			},
			update_modified=False,
		)


def _term_number(term_name):
	match = re.search(r"(\d+|[IVX]+)\s*$", term_name or "")
	if not match:
		return 0
	token = match.group(1)
	return cint(token) if token.isdigit() else ROMAN.get(token, 0)


def clean_academic_terms():
	terms = frappe.db.sql(
		"""SELECT name, academic_year, term_name, term_no
		   FROM `tabAcademic Term` ORDER BY academic_year, term_start_date""",
		as_dict=True,
	)
	used = {}
	for term in terms:
		term_name = (term.term_name or term.name).strip()
		ay = term.academic_year or ""
		# "Trimester I - AY 2025-26" -> "Trimester I" (also the doubled "AY AY" variant)
		for suffix in (f" - {ay}", f" - AY {ay}"):
			if ay and term_name.endswith(suffix):
				term_name = term_name[: -len(suffix)].strip()

		taken = used.setdefault(ay, set())
		term_no = cint(term.term_no) or _term_number(term_name)
		if not term_no or term_no in taken:
			term_no = next(n for n in range(1, 100) if n not in taken)
		taken.add(term_no)

		frappe.db.set_value(
			"Academic Term", term.name, {"term_name": term_name, "term_no": term_no}, update_modified=False
		)


def _batch_year(batch):
	"""Year of study the old Batch represented (Batch.term_year), or 0."""
	if not batch or not frappe.db.has_column("SLCM Batch", "term_year"):
		return 0
	return cint(frappe.db.sql("SELECT term_year FROM `tabSLCM Batch` WHERE name = %s", batch)[0][0]) if frappe.db.exists("SLCM Batch", batch) else 0


def backfill_course_offerings():
	has_cohort = frappe.db.has_column("Course Offering", "cohort")
	fields = "name, course_title, year_no" + (", cohort" if has_cohort else "")
	for row in frappe.db.sql(f"SELECT {fields} FROM `tabCourse Offering`", as_dict=True):
		values = {}
		if not cint(row.year_no):
			values["year_no"] = _batch_year(row.get("cohort")) or 1
		course_type = frappe.db.get_value("Course", row.course_title, "course_type")
		values["is_elective"] = 1 if course_type == "Elective" else 0
		frappe.db.set_value("Course Offering", row.name, values, update_modified=False)


def merge_duplicate_course_offerings():
	"""Without a Batch, offerings of different batches can now share the same key."""
	rows = frappe.db.sql(
		"""SELECT name, program, course_title, academic_year, term_name, year_no
		   FROM `tabCourse Offering` ORDER BY creation""",
		as_dict=True,
	)
	keep_by_key = {}
	for row in rows:
		key = (row.program, row.course_title, row.academic_year, row.term_name, cint(row.year_no))
		keep = keep_by_key.setdefault(key, row.name)
		if keep == row.name:
			continue
		try:
			rename_doc(
				"Course Offering", row.name, keep,
				merge=True, force=True, ignore_permissions=True, show_alert=False, rebuild_search=False,
			)
		except Exception:
			frappe.log_error(
				title=f"academic_core_restructure: could not merge Course Offering {row.name}",
				message=frappe.get_traceback(),
			)

	# A merge can leave the same offering twice on one enrollment.
	frappe.db.sql(
		"""DELETE dup FROM `tabStudent Enrollment Course` dup
		   JOIN `tabStudent Enrollment Course` first
		     ON first.parent = dup.parent
		    AND first.course_offering = dup.course_offering
		    AND first.idx < dup.idx
		   WHERE dup.parenttype = 'Student Enrollment'"""
	)


def backfill_student_enrollments():
	# Sites coming from TFSS never had Student Enrollment.year_no; merge_enrollments_into_academic_log
	# fills academic_year from the batch there.
	if not frappe.db.has_column("Student Enrollment", "year_no"):
		return
	for row in frappe.db.sql(
		"SELECT name, student, batch, academic_year, year_no FROM `tabStudent Enrollment`", as_dict=True
	):
		values = {}
		if not row.academic_year and row.batch:
			values["academic_year"] = frappe.db.get_value("SLCM Batch", row.batch, "academic_year")
		if not cint(row.year_no):
			year_no = _batch_year(row.batch)
			if not year_no:
				current = frappe.db.get_value("Student Master", row.student, "current_year") or ""
				digits = re.search(r"\d+", str(current))
				year_no = cint(digits.group()) if digits else 0
			values["year_no"] = year_no or 1
		if values:
			frappe.db.set_value("Student Enrollment", row.name, values, update_modified=False)


def backfill_fee_structures():
	frappe.db.sql("UPDATE `tabFee Structure` SET year_no = 1 WHERE IFNULL(year_no, 0) = 0")


def refresh_batch_counts():
	from slcm.slcm.doctype.slcm_batch.slcm_batch import update_enrolled_count

	for batch in frappe.get_all("SLCM Batch", pluck="name"):
		update_enrolled_count(batch)

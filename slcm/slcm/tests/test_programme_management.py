# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""
Programme Management workspace: Academic Year -> Time Table
===========================================================
Integration tests for the DocTypes on the Programme Management workspace,
in the order the workspace lists them:

    Academic Year, Academic Term, Programme, Section, SLCM Batch, Course,
    Student Master, Student Enrollment, Classes, Time Table

Every record is created by the tests themselves in the year 2091 onwards (so
nothing overlaps real Academic Years / Terms) with a random prefix, and
everything is rolled back afterwards: each test runs inside a savepoint, and
each class inside one transaction. Student Master's on_update calls
frappe.db.commit(), so commits are disabled while these tests run - nothing is
ever written to the site. Google Calendar sync is switched off.

Run:
    bench --site slcm.local run-tests --module slcm.slcm.tests.test_programme_management
"""

import unittest
from datetime import date, timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from slcm.slcm.doctype.academic_term.academic_term import get_current_term, get_programme_term
from slcm.slcm.doctype.academic_year.academic_year import get_current_academic_year
from slcm.slcm.doctype.classes.classes import create_classes, get_class_students, get_enrollment_students
from slcm.slcm.doctype.programme.programme import Programme
from slcm.slcm.doctype.student_enrollment.student_enrollment import (
	change_section,
	get_current_log,
	promote_enrollment,
	term_course_status,
)

# Year 1 of the test calendar: two terms. Year 2: one term.
AY1_START, AY1_END = date(2091, 6, 1), date(2092, 5, 31)
AY2_START, AY2_END = date(2092, 6, 1), date(2093, 5, 31)
T1_START, T1_END = date(2091, 6, 1), date(2091, 9, 30)
T2_START, T2_END = date(2091, 10, 1), date(2092, 1, 31)
T3_START, T3_END = date(2092, 6, 1), date(2092, 9, 30)


def next_weekday(d, weekday):
	"""First date on or after `d` that falls on `weekday` (Monday = 0)."""
	return d + timedelta(days=(weekday - d.weekday()) % 7)


MONDAY = next_weekday(date(2091, 6, 4), 0)
SUNDAY = next_weekday(MONDAY, 6)


class ProgrammeManagementTestCase(IntegrationTestCase):
	"""Builds one academic setup shared by the tests of a class:

	Academic Years AY1 (terms T1, T2) and AY2 (term T3), Term Masters, a
	3-year Programme, Sections A and B, a Batch in AY1, an Active and an
	Inactive Course, a Faculty and a Venue."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Student Master.on_update commits; keep every write inside the test transaction.
		for patcher in (
			patch.object(frappe.db, "commit", lambda *args, **kwargs: None),
			patch(
				"slcm.slcm.doctype.time_table.google_calendar_sync.get_active_google_calendar_account",
				return_value=None,
			),
		):
			patcher.start()
			cls.addClassCleanup(patcher.stop)

		cls.p = "PMT" + frappe.generate_hash(length=6).upper()
		cls.ay1 = cls.make_academic_year(f"{cls.p} AY1", AY1_START, AY1_END)
		cls.ay2 = cls.make_academic_year(f"{cls.p} AY2", AY2_START, AY2_END)
		cls.t1 = cls.make_term(cls.ay1, "Term 1", 1, T1_START, T1_END)
		cls.t2 = cls.make_term(cls.ay1, "Term 2", 2, T2_START, T2_END)
		cls.t3 = cls.make_term(cls.ay2, "Term 1", 1, T3_START, T3_END)
		cls.tm1 = cls.make_term_master(f"{cls.p} Trimester I")
		cls.tm2 = cls.make_term_master(f"{cls.p} Trimester II")
		cls.programme = cls.make_programme(f"{cls.p} BA LLB", duration=3)
		cls.section_a = cls.make_section(f"{cls.p}-A")
		cls.section_b = cls.make_section(f"{cls.p}-B")
		cls.batch = cls.make_batch(f"{cls.p} Batch 2091", cls.ay1, status="Active")
		cls.course = cls.make_course(f"{cls.p} Legal Methods", f"{cls.p}LM101", credit=4)
		cls.course2 = cls.make_course(f"{cls.p} Contracts", f"{cls.p}CT102", credit=3, course_type="Elective")
		cls.inactive_course = cls.make_course(f"{cls.p} Old Course", f"{cls.p}OLD", status="Inactive")
		cls.faculty = cls.make_faculty()
		cls.venue = cls.make_venue(f"{cls.p} Room 1")
		cls.venue2 = cls.make_venue(f"{cls.p} Room 2")

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.savepoint("pm_test")
		self.addCleanup(frappe.db.rollback, save_point="pm_test")

	# ── Fixture builders ──────────────────────────────────────────────────────

	@staticmethod
	def make_academic_year(name, start, end, **kwargs):
		return frappe.get_doc({
			"doctype": "Academic Year",
			"academic_year_name": name,
			"year_start_date": start,
			"year_end_date": end,
			"status": "Active",
			**kwargs,
		}).insert().name

	@staticmethod
	def make_term(academic_year, term_name, term_no, start, end, **kwargs):
		return frappe.get_doc({
			"doctype": "Academic Term",
			"academic_year": academic_year,
			"term_name": term_name,
			"term_no": term_no,
			"term_start_date": start,
			"term_end_date": end,
			"status": "Active",
			**kwargs,
		}).insert().name

	@staticmethod
	def make_term_master(name):
		return frappe.get_doc({"doctype": "Term Master", "__newname": name}).insert().name

	@staticmethod
	def make_programme(name, duration=3, **kwargs):
		return frappe.get_doc({
			"doctype": "Programme",
			"program_name": name,
			"program_code": frappe.generate_hash(length=8).upper(),
			"level_of_study": "Undergraduate",
			"program_duration": duration,
			"program_status": "Active",
			"program_image": "/files/pm-test-programme.png",
			**kwargs,
		}).insert().name

	@staticmethod
	def make_section(name):
		return frappe.get_doc({"doctype": "Section", "section_name": name}).insert().name

	@staticmethod
	def make_batch(name, academic_year, **kwargs):
		return frappe.get_doc({
			"doctype": "SLCM Batch",
			"batch_name": name,
			"academic_year": academic_year,
			**kwargs,
		}).insert().name

	@staticmethod
	def make_course(name, code, credit=None, status="Active", course_type="Core"):
		return frappe.get_doc({
			"doctype": "Course",
			"course_name": name,
			"course_code": code,
			"credit_value": credit,
			"course_type": course_type,
			"status": status,
		}).insert().name

	@classmethod
	def make_faculty(cls):
		# Faculty is autoincrement-named; Link fields hold the name as a string.
		return str(frappe.get_doc({
			"doctype": "Faculty",
			"faculty_id": f"{cls.p}-FAC-{frappe.generate_hash(length=4)}",
			"first_name": "Test Faculty",
			"email": f"{frappe.generate_hash(length=10)}@pm-test.example.com",
			"status": "Active",
			"photo": "/files/pm-test-faculty.png",
		}).insert().name)

	@classmethod
	def make_venue(cls, name):
		venue_type = f"{cls.p} Classroom"
		if not frappe.db.exists("Venue Type", venue_type):
			frappe.get_doc({"doctype": "Venue Type", "venue_type_name": venue_type, "is_active": 1}).insert()
		venue = frappe.get_doc({
			"doctype": "Venue Master",
			"venue_name_or_number": name,
			"venue_type": venue_type,
			"capacity": 60,
		})
		# Amenities and allowed roles are irrelevant to scheduling.
		venue.insert(ignore_mandatory=True)
		return venue.name

	@classmethod
	def student_doc(cls, first_name="Test", admission_type="Regular", **kwargs):
		"""An unsaved Student Master with every field a Regular admission requires."""
		school = {}
		if admission_type != "PACE":
			school = {
				"class_x_completion_year": "2085", "class_x_percentage": 90, "class_x_school": "Test School",
				"class_x_board": "CBSE", "class_x_max_cgpa": 10, "class_xii_exam_name": "AISSCE",
				"class_xii_completion_year": "2087", "class_xii_school": "Test School",
				"class_xii_board": "CBSE", "class_xii_percentage": 92, "class_xii_max_cgpa": 10,
				"std_x_marksheet": "/files/pm-test-x.pdf", "class_xii_marksheet": "/files/pm-test-xii.pdf",
			}
		return frappe.get_doc({
			"doctype": "Student Master",
			"first_name": f"{cls.p} {first_name}",
			"email": f"{frappe.generate_hash(length=10)}@pm-test.example.com",
			"admission_type": admission_type,
			**school,
			**kwargs,
		})

	@classmethod
	def make_student(cls, first_name="Test", **kwargs):
		return cls.student_doc(first_name, **kwargs).insert().name

	@classmethod
	def make_enrollment(cls, student=None, programme=None, batch=None, section=None, **kwargs):
		return frappe.get_doc({
			"doctype": "Student Enrollment",
			"student": student or cls.make_student(),
			"program": programme or cls.programme,
			"batch": batch or cls.batch,
			"section": section if section is not None else cls.section_a,
			**kwargs,
		}).insert()

	@classmethod
	def make_class(cls, enrollments=(), course=None, section=None, class_type="Section", **kwargs):
		values = {
			"doctype": "Classes",
			"class_type": class_type,
			"academic_year": cls.ay1,
			"academic_term": cls.t1,
			"programme": cls.programme,
			"year_no": 1,
			"course": course or cls.course,
			"faculty": cls.faculty,
			"enrolled_students": [{"student_enrollment": e, "status": "Enrolled"} for e in enrollments],
			**kwargs,
		}
		if class_type == "Section":
			values["section"] = section or cls.section_a
		return frappe.get_doc(values).insert()

	@classmethod
	def time_table_doc(cls, class_name, schedule_date=MONDAY, from_time="09:00:00", to_time="10:00:00", **kwargs):
		return frappe.get_doc({
			"doctype": "Time Table",
			"based_on": "Class",
			"class_name": class_name,
			"schedule_date": schedule_date,
			"from_time": from_time,
			"to_time": to_time,
			"venue": kwargs.pop("venue", cls.venue),
			"repeat_frequency": kwargs.pop("repeat_frequency", "Never"),
			**kwargs,
		})


# ── Academic Year ─────────────────────────────────────────────────────────────


class TestAcademicYear(ProgrammeManagementTestCase):
	def test_create_valid_year(self):
		doc = frappe.get_doc("Academic Year", self.ay1)
		self.assertEqual(doc.name, f"{self.p} AY1")
		self.assertEqual(getdate(doc.year_start_date), AY1_START)
		self.assertEqual(doc.status, "Active")
		self.assertEqual(doc.is_current_year, 0)

	def test_end_date_before_start_date_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "must be after Year Start Date"):
			self.make_academic_year(f"{self.p} Bad", date(2095, 6, 1), date(2095, 5, 1))

	def test_end_date_equal_to_start_date_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "must be after Year Start Date"):
			self.make_academic_year(f"{self.p} Bad", date(2095, 6, 1), date(2095, 6, 1))

	def test_overlapping_year_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "overlap"):
			self.make_academic_year(f"{self.p} Overlap", date(2092, 1, 1), date(2092, 12, 31))

	def test_year_containing_another_year_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "overlap"):
			self.make_academic_year(f"{self.p} Wide", date(2090, 1, 1), date(2094, 12, 31))

	def test_year_starting_the_day_after_another_ends_is_allowed(self):
		name = self.make_academic_year(f"{self.p} AY3", AY2_END + timedelta(days=1), date(2094, 5, 31))
		self.assertTrue(frappe.db.exists("Academic Year", name))

	def test_saving_existing_year_does_not_overlap_itself(self):
		doc = frappe.get_doc("Academic Year", self.ay1)
		doc.status = "Inactive"
		doc.save()
		self.assertEqual(frappe.db.get_value("Academic Year", self.ay1, "status"), "Inactive")

	def test_duplicate_name_is_rejected(self):
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make_academic_year(self.ay1, date(2097, 6, 1), date(2098, 5, 31))

	def test_mandatory_fields(self):
		# validate() runs before the mandatory check, so either error may come first.
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Academic Year", "academic_year_name": f"{self.p} NoDates", "status": "Active",
			}).insert()

	def test_current_year_must_be_active(self):
		with self.assertRaisesRegex(frappe.ValidationError, "must have status Active"):
			self.make_academic_year(
				f"{self.p} Cur", date(2097, 6, 1), date(2098, 5, 31), status="Inactive", is_current_year=1
			)

	def test_only_one_current_year(self):
		frappe.db.sql("UPDATE `tabAcademic Year` SET is_current_year = 0")
		doc = frappe.get_doc("Academic Year", self.ay1)
		doc.is_current_year = 1
		doc.save()
		self.assertEqual(get_current_academic_year(), self.ay1)

		with self.assertRaisesRegex(frappe.ValidationError, "already the current Academic Year"):
			self.make_academic_year(f"{self.p} Cur2", date(2097, 6, 1), date(2098, 5, 31), is_current_year=1)

		# Re-saving the current year itself is fine.
		doc.reload()
		doc.save()


# ── Academic Term ─────────────────────────────────────────────────────────────


class TestAcademicTerm(ProgrammeManagementTestCase):
	def test_name_is_term_name_and_year(self):
		self.assertEqual(self.t1, f"Term 1 - {self.ay1}")

	def test_term_name_is_trimmed(self):
		name = self.make_term(self.ay2, "  Term 2  ", 2, date(2092, 10, 1), date(2092, 12, 31))
		self.assertEqual(name, f"Term 2 - {self.ay2}")
		self.assertEqual(frappe.db.get_value("Academic Term", name, "term_name"), "Term 2")

	def test_same_term_name_allowed_in_another_year(self):
		# "Term 1" exists in both AY1 and AY2.
		self.assertNotEqual(self.t1, self.t3)
		self.assertEqual(frappe.db.get_value("Academic Term", self.t3, "term_name"), "Term 1")

	def test_term_no_must_be_positive(self):
		for term_no in (0, -1):
			with self.assertRaisesRegex(frappe.ValidationError, "Term No must be 1 or more"):
				self.make_term(self.ay2, f"Bad {term_no}", term_no, date(2092, 10, 1), date(2092, 12, 31))

	def test_term_no_unique_within_year(self):
		with self.assertRaisesRegex(frappe.ValidationError, "already used"):
			self.make_term(self.ay1, "Term X", 1, date(2092, 2, 1), date(2092, 3, 31))

	def test_end_date_must_be_after_start_date(self):
		with self.assertRaisesRegex(frappe.ValidationError, "must be after Term Start Date"):
			self.make_term(self.ay1, "Term 3", 3, date(2092, 3, 31), date(2092, 2, 1))

	def test_dates_must_fall_inside_academic_year(self):
		with self.assertRaisesRegex(frappe.ValidationError, "inside Academic Year"):
			self.make_term(self.ay1, "Term 3", 3, date(2092, 4, 1), date(2092, 6, 30))
		with self.assertRaisesRegex(frappe.ValidationError, "inside Academic Year"):
			self.make_term(self.ay1, "Term 0", 3, date(2091, 5, 1), date(2091, 5, 31))

	def test_terms_of_same_year_must_not_overlap(self):
		with self.assertRaisesRegex(frappe.ValidationError, "overlap"):
			self.make_term(self.ay1, "Term 3", 3, date(2092, 1, 15), date(2092, 3, 31))

	def test_term_mapping_year_must_be_positive(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Year must be 1 or more"):
			self.make_term(
				self.ay1, "Term 3", 3, date(2092, 2, 1), date(2092, 3, 31),
				term_mapping=[{"year_no": 0, "term": self.tm1}],
			)

	def test_term_mapping_duplicate_year_and_batch_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "already mapped"):
			self.make_term(
				self.ay1, "Term 3", 3, date(2092, 2, 1), date(2092, 3, 31),
				term_mapping=[
					{"year_no": 1, "batch": self.batch, "term": self.tm1},
					{"year_no": 1, "batch": self.batch, "term": self.tm2},
				],
			)

	def test_programme_term_prefers_batch_row_over_general_row(self):
		other_batch = self.make_batch(f"{self.p} Batch Other", self.ay1)
		term = self.make_term(
			self.ay1, "Term 3", 3, date(2092, 2, 1), date(2092, 3, 31),
			term_mapping=[
				{"year_no": 1, "term": self.tm1},
				{"year_no": 1, "batch": other_batch, "term": self.tm2},
			],
		)
		self.assertEqual(get_programme_term(term, 1), self.tm1)
		self.assertEqual(get_programme_term(term, 1, self.batch), self.tm1)
		self.assertEqual(get_programme_term(term, 1, other_batch), self.tm2)
		self.assertIsNone(get_programme_term(term, 2))
		self.assertIsNone(get_programme_term(term, 0))

	def test_term_mapping_updates_enrollment_log_and_student(self):
		enrollment = self.make_enrollment()
		term = frappe.get_doc("Academic Term", self.t1)
		term.append("term_mapping", {"year_no": 1, "term": self.tm1})
		term.save()

		row = frappe.db.get_value(
			"Student Academic Log", {"parent": enrollment.name, "academic_term": self.t1}, ["term", "status"], as_dict=True
		)
		self.assertEqual(row.term, self.tm1)
		self.assertEqual(row.status, "Ongoing")
		self.assertEqual(frappe.db.get_value("Student Master", enrollment.student, "current_term"), self.tm1)

	def test_get_current_term(self):
		self.assertEqual(get_current_term(date(2091, 7, 15)), self.t1)
		self.assertEqual(get_current_term(T2_END), self.t2)
		self.assertIsNone(get_current_term(date(2092, 3, 1)))

	def test_inactive_term_is_not_current(self):
		frappe.db.set_value("Academic Term", self.t1, "status", "Inactive")
		self.assertIsNone(get_current_term(date(2091, 7, 15)))


# ── Programme ─────────────────────────────────────────────────────────────────


class TestProgramme(ProgrammeManagementTestCase):
	def test_slug_is_generated_from_name(self):
		key = frappe.generate_hash(length=6)
		name = self.make_programme(f"Pmt {key} B.A., LL.B. (Hons) & Policy")
		self.assertEqual(
			frappe.db.get_value("Programme", name, "program_slug"), f"pmt-{key}-ba-llb-hons-and-policy"
		)

	def test_slugify(self):
		self.assertEqual(Programme._slugify("  Master of Public Policy (MPP)  "), "master-of-public-policy-mpp")
		self.assertEqual(Programme._slugify("Law & Society -- 2091"), "law-and-society-2091")

	def test_clashing_slug_gets_suffix(self):
		key = frappe.generate_hash(length=6)
		first = self.make_programme(f"Pmt {key} Policy")
		second = self.make_programme(f"Pmt {key}-Policy")
		first_slug = frappe.db.get_value("Programme", first, "program_slug")
		second_slug = frappe.db.get_value("Programme", second, "program_slug")
		self.assertEqual(first_slug, f"pmt-{key}-policy")
		self.assertNotEqual(first_slug, second_slug)
		self.assertTrue(second_slug.startswith(first_slug + "-"))

	def test_resave_keeps_its_own_slug(self):
		doc = frappe.get_doc("Programme", self.programme)
		slug = doc.program_slug
		doc.program_description = "Updated"
		doc.save()
		self.assertEqual(doc.program_slug, slug)

	def test_application_form_links(self):
		doc = frappe.get_doc("Programme", self.programme)
		self.assertIn(f"program={doc.program_slug}", doc.application_form_link)
		self.assertIn("foriegn_national=No", doc.application_form_link)
		self.assertIn(f"program={doc.program_slug}", doc.international_application_form_link)
		self.assertIn("foriegn_national=Yes", doc.international_application_form_link)

	def test_duplicate_name_is_rejected(self):
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make_programme(self.programme)

	def test_mandatory_fields(self):
		with self.assertRaises(frappe.MandatoryError):
			self.make_programme(f"{self.p} No Image", program_image=None)
		with self.assertRaises(frappe.MandatoryError):
			self.make_programme(f"{self.p} No Level", level_of_study=None)

	def test_invalid_level_of_study_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_programme(f"{self.p} Bad Level", level_of_study="Diploma")


# ── Section ───────────────────────────────────────────────────────────────────


class TestSection(ProgrammeManagementTestCase):
	def test_create_section(self):
		self.assertEqual(self.section_a, f"{self.p}-A")
		self.assertEqual(frappe.db.get_value("Section", self.section_a, "section_name"), f"{self.p}-A")

	def test_duplicate_section_is_rejected(self):
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make_section(self.section_a)

	def test_section_name_is_mandatory(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Section"}).insert()


# ── SLCM Batch ────────────────────────────────────────────────────────────────


class TestSLCMBatch(ProgrammeManagementTestCase):
	def test_defaults(self):
		doc = frappe.get_doc("SLCM Batch", self.make_batch(f"{self.p} New Batch", self.ay1))
		self.assertEqual(doc.status, "Planned")
		self.assertEqual(doc.total_enrolled_count, 0)

	def test_academic_year_is_mandatory(self):
		with self.assertRaises(frappe.MandatoryError):
			frappe.get_doc({"doctype": "SLCM Batch", "batch_name": f"{self.p} No AY"}).insert()

	def test_invalid_academic_year_link_is_rejected(self):
		with self.assertRaises(frappe.LinkValidationError):
			self.make_batch(f"{self.p} Bad AY", f"{self.p} Missing Year")

	def test_duplicate_batch_name_is_rejected(self):
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make_batch(self.batch, self.ay1)

	def test_duplicate_batch_code_is_rejected(self):
		code = f"{self.p}-CODE"
		self.make_batch(f"{self.p} Coded 1", self.ay1, batch_code=code)
		with self.assertRaises(frappe.UniqueValidationError):
			self.make_batch(f"{self.p} Coded 2", self.ay1, batch_code=code)

	def test_enrolled_count_follows_enrollments(self):
		batch = self.make_batch(f"{self.p} Count Batch", self.ay1)
		first = self.make_enrollment(batch=batch)
		self.make_enrollment(batch=batch)
		self.assertEqual(frappe.db.get_value("SLCM Batch", batch, "total_enrolled_count"), 2)

		first.status = "Dropped"
		first.save()
		self.assertEqual(frappe.db.get_value("SLCM Batch", batch, "total_enrolled_count"), 1)

	def test_enrolled_count_moves_with_batch_change(self):
		old_batch = self.make_batch(f"{self.p} Old Batch", self.ay1)
		new_batch = self.make_batch(f"{self.p} New Batch", self.ay1)
		enrollment = self.make_enrollment(batch=old_batch)
		enrollment.batch = new_batch
		enrollment.save()
		self.assertEqual(frappe.db.get_value("SLCM Batch", old_batch, "total_enrolled_count"), 0)
		self.assertEqual(frappe.db.get_value("SLCM Batch", new_batch, "total_enrolled_count"), 1)

	def test_enrolled_count_drops_when_enrollment_deleted(self):
		batch = self.make_batch(f"{self.p} Del Batch", self.ay1)
		enrollment = self.make_enrollment(batch=batch)
		enrollment.delete()
		self.assertEqual(frappe.db.get_value("SLCM Batch", batch, "total_enrolled_count"), 0)


# ── Course ────────────────────────────────────────────────────────────────────


class TestCourse(ProgrammeManagementTestCase):
	def test_name_is_course_name_and_code(self):
		self.assertEqual(self.course, f"{self.p} Legal Methods-{self.p}LM101")

	def test_name_is_trimmed_and_slash_replaced(self):
		name = self.make_course(f"  {self.p} Law / Society ", f" {self.p}LS1 ")
		self.assertEqual(name, f"{self.p} Law - Society-{self.p}LS1")

	def test_same_name_with_different_code_is_allowed(self):
		name = self.make_course(f"{self.p} Legal Methods", f"{self.p}LM201")
		self.assertNotEqual(name, self.course)

	def test_duplicate_name_and_code_is_rejected(self):
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make_course(f"{self.p} Legal Methods", f"{self.p}LM101")

	def test_code_and_name_are_required(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Course", "course_name": f"{self.p} No Code", "status": "Active"}).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Course", "course_code": f"{self.p}NN", "status": "Active"}).insert()

	def test_status_is_mandatory(self):
		with self.assertRaises(frappe.MandatoryError):
			frappe.get_doc({"doctype": "Course", "course_name": f"{self.p} S", "course_code": f"{self.p}S"}).insert()


# ── Student Master ────────────────────────────────────────────────────────────


class TestStudentMaster(ProgrammeManagementTestCase):
	def test_new_student_defaults(self):
		doc = frappe.get_doc("Student Master", self.make_student())
		self.assertTrue(doc.name.startswith(f"STUD-{frappe.utils.nowdate()[:4]}-"))
		self.assertEqual(doc.registration_status, "Selected")
		self.assertEqual(doc.current_year, "1")

	def test_first_name_and_email_are_mandatory(self):
		with self.assertRaises(frappe.MandatoryError):
			self.make_student(email=None)
		doc = self.student_doc()
		doc.first_name = None
		with self.assertRaises(frappe.MandatoryError):
			doc.insert()

	def test_invalid_email_is_rejected(self):
		with self.assertRaises(frappe.InvalidEmailAddressError):
			self.make_student(email="not-an-email")

	def test_school_details_not_required_for_pace(self):
		self.assertTrue(frappe.db.exists("Student Master", self.make_student(admission_type="PACE")))

	def test_ifsc_is_normalised(self):
		doc = frappe.get_doc("Student Master", self.make_student(savings_ifsc_code=" sbin0001234 "))
		self.assertEqual(doc.savings_ifsc_code, "SBIN0001234")

	def test_invalid_ifsc_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "11 alphanumeric"):
			self.make_student(savings_ifsc_code="SBIN-123")

	def test_loan_details_cleared_without_education_loan(self):
		doc = frappe.get_doc(
			"Student Master",
			self.make_student(availed_education_loan="No", loan_bank_name="Some Bank", loan_account_number="123"),
		)
		self.assertIsNone(doc.loan_bank_name)
		self.assertIsNone(doc.loan_account_number)

	def loan_details(self, account):
		return {
			"availed_education_loan": "Yes",
			"education_loan_scheme": "PM Vidyalaxmi",
			"loan_account_number": account,
			"loan_account_holder_name": "Holder",
			"loan_bank_name": "Bank",
			"loan_branch_name": "Branch",
			"loan_ifsc_code": "SBIN0001234",
		}

	def test_account_numbers_are_normalised(self):
		account = f"{frappe.generate_hash(length=8)} 12"
		doc = frappe.get_doc("Student Master", self.make_student(savings_account_number=account))
		self.assertEqual(doc.savings_account_number, account.replace(" ", "").upper())

	def test_savings_and_loan_account_must_differ(self):
		account = frappe.generate_hash(length=12).upper()
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be the same"):
			self.make_student(savings_account_number=account, **self.loan_details(account))

	def test_account_number_unique_across_students(self):
		account = frappe.generate_hash(length=12).upper()
		self.make_student(savings_account_number=account)
		with self.assertRaisesRegex(frappe.ValidationError, "already registered"):
			self.make_student("Second", savings_account_number=account)
		# Another student's savings number cannot be used as a loan number either.
		with self.assertRaisesRegex(frappe.ValidationError, "already registered"):
			self.make_student("Third", **self.loan_details(account))

	def test_resave_does_not_clash_with_itself(self):
		account = frappe.generate_hash(length=12).upper()
		doc = frappe.get_doc("Student Master", self.make_student(savings_account_number=account))
		doc.phone = "9999999999"
		doc.save()


# ── Student Enrollment ────────────────────────────────────────────────────────


class TestStudentEnrollment(ProgrammeManagementTestCase):
	def test_named_after_student_until_id_assigned(self):
		enrollment = self.make_enrollment()
		self.assertEqual(enrollment.name, enrollment.student)
		self.assertEqual(enrollment.status, "Enrolled")

	def test_named_after_registration_id_with_suffix_for_second_programme(self):
		reg_id = f"{self.p}-REG-1"
		student = self.make_student(registration_id=reg_id)
		first = self.make_enrollment(student=student)
		second = self.make_enrollment(student=student, programme=self.make_programme(f"{self.p} LLM", duration=1))
		self.assertEqual(first.name, reg_id)
		self.assertEqual(second.name, f"{reg_id}-2")

	def test_initial_log_built_from_batch_academic_year(self):
		enrollment = self.make_enrollment()
		log = [(r.academic_year, r.academic_term, r.year_no, r.status, r.section) for r in enrollment.academic_log]
		self.assertEqual(log, [
			(self.ay1, self.t1, 1, "Ongoing", self.section_a),
			(self.ay1, self.t2, 1, "Upcoming", self.section_a),
		])
		self.assertTrue(all(r.updated_on and r.updated_by for r in enrollment.academic_log))

	def test_inactive_terms_are_left_out_of_the_log(self):
		frappe.db.set_value("Academic Term", self.t2, "status", "Inactive")
		enrollment = self.make_enrollment()
		self.assertEqual([r.academic_term for r in enrollment.academic_log], [self.t1])

	def test_student_master_follows_enrollment(self):
		enrollment = self.make_enrollment()
		student = frappe.db.get_value(
			"Student Master", enrollment.student,
			["academic_year", "current_year", "year_of_study", "student_status", "academic_status"], as_dict=True,
		)
		self.assertEqual(student.academic_year, self.ay1)
		self.assertEqual(student.current_year, "1")
		self.assertEqual(student.year_of_study, "1st Year")
		self.assertEqual(student.student_status, "Active")
		self.assertEqual(student.academic_status, "Active")

	def test_student_name_is_fetched(self):
		student = self.make_student("Fetch")
		enrollment = self.make_enrollment(student=student)
		self.assertEqual(enrollment.student_name, frappe.db.get_value("Student Master", student, "first_name"))

	def test_one_enrollment_per_student_and_programme(self):
		student = self.make_student()
		self.make_enrollment(student=student)
		with self.assertRaisesRegex(frappe.ValidationError, "already enrolled"):
			self.make_enrollment(student=student)

	def test_batch_is_mandatory(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Student Enrollment", "student": self.make_student(), "program": self.programme,
			}).insert()

	def test_section_cannot_be_edited_directly(self):
		enrollment = self.make_enrollment()
		enrollment.section = self.section_b
		with self.assertRaisesRegex(frappe.ValidationError, "Change Section"):
			enrollment.save()

	def test_change_section(self):
		enrollment = self.make_enrollment()
		result = change_section(enrollment.name, self.section_b, reason="Timetable clash")
		self.assertEqual(result["section"], self.section_b)
		self.assertIn("Timetable clash", result["note"])

		enrollment.reload()
		self.assertEqual(enrollment.section, self.section_b)
		self.assertTrue(all(r.section == self.section_b for r in enrollment.academic_log))
		ongoing = next(r for r in enrollment.academic_log if r.status == "Ongoing")
		self.assertIn(self.section_b, ongoing.remarks)
		self.assertEqual(frappe.db.get_value("Student Master", enrollment.student, "section"), self.section_b)

	def test_change_section_validations(self):
		enrollment = self.make_enrollment()
		with self.assertRaisesRegex(frappe.ValidationError, "already in section"):
			change_section(enrollment.name, self.section_a)
		with self.assertRaisesRegex(frappe.ValidationError, "does not exist"):
			change_section(enrollment.name, f"{self.p}-NOPE")

		enrollment.status = "Dropped"
		enrollment.save()
		with self.assertRaisesRegex(frappe.ValidationError, "Only an Enrolled student"):
			change_section(enrollment.name, self.section_b)

	def test_dropping_closes_log_and_updates_student(self):
		enrollment = self.make_enrollment()
		enrollment.status = "Dropped"
		enrollment.save()
		self.assertEqual({r.status for r in enrollment.academic_log}, {"Dropped"})
		student = frappe.db.get_value(
			"Student Master", enrollment.student, ["student_status", "academic_status"], as_dict=True
		)
		self.assertEqual(student.student_status, "Dropped")
		self.assertEqual(student.academic_status, "Inactive")

	def test_completing_closes_log_and_graduates_student(self):
		enrollment = self.make_enrollment()
		enrollment.status = "Completed"
		enrollment.save()
		self.assertEqual({r.status for r in enrollment.academic_log}, {"Completed"})
		self.assertEqual(frappe.db.get_value("Student Master", enrollment.student, "student_status"), "Graduated")

	def test_log_year_beyond_programme_duration_is_rejected(self):
		enrollment = self.make_enrollment()
		enrollment.append("academic_log", {"academic_year": self.ay2, "year_no": 4, "status": "Upcoming"})
		with self.assertRaisesRegex(frappe.ValidationError, "beyond the 3-year duration"):
			enrollment.save()

	def test_log_year_must_be_positive(self):
		enrollment = self.make_enrollment()
		enrollment.append("academic_log", {"academic_year": self.ay2, "year_no": 0, "status": "Upcoming"})
		with self.assertRaisesRegex(frappe.ValidationError, "Year must be 1 or more"):
			enrollment.save()

	def test_log_term_must_belong_to_its_year(self):
		enrollment = self.make_enrollment()
		enrollment.append(
			"academic_log", {"academic_year": self.ay2, "academic_term": self.t1, "year_no": 2, "status": "Upcoming"}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "does not belong to Academic Year"):
			enrollment.save()

	def test_only_one_ongoing_log_row(self):
		enrollment = self.make_enrollment()
		for row in enrollment.academic_log:
			row.status = "Ongoing"
		with self.assertRaisesRegex(frappe.ValidationError, "Only one Academic Log row can be Ongoing"):
			enrollment.save()

	def test_log_is_kept_in_chronological_order(self):
		enrollment = self.make_enrollment()
		enrollment.append(
			"academic_log", {"academic_year": self.ay2, "academic_term": self.t3, "year_no": 2, "status": "Upcoming"}
		)
		enrollment.academic_log.reverse()
		enrollment.save()
		self.assertEqual([r.academic_term for r in enrollment.academic_log], [self.t1, self.t2, self.t3])
		self.assertEqual([r.idx for r in enrollment.academic_log], [1, 2, 3])

	def test_current_log(self):
		enrollment = self.make_enrollment()
		current = get_current_log(enrollment.name)
		self.assertEqual((current.academic_term, current.year_no, current.status), (self.t1, 1, "Ongoing"))

	def test_promotion_to_next_year(self):
		enrollment = self.make_enrollment()
		name, moved = promote_enrollment(enrollment.name, self.ay2)
		self.assertTrue(moved)

		enrollment = frappe.get_doc("Student Enrollment", name)
		log = [(r.academic_year, r.year_no, r.status) for r in enrollment.academic_log]
		self.assertEqual(log, [
			(self.ay1, 1, "Completed"),
			(self.ay1, 1, "Completed"),
			(self.ay2, 2, "Ongoing"),
		])
		student = frappe.db.get_value(
			"Student Master", enrollment.student, ["academic_year", "current_year", "year_of_study"], as_dict=True
		)
		self.assertEqual((student.academic_year, student.current_year, student.year_of_study), (self.ay2, "2", "2nd Year"))

		# Running it again changes nothing.
		self.assertEqual(promote_enrollment(enrollment.name, self.ay2), (enrollment.name, False))

	def test_repeat_year(self):
		enrollment = self.make_enrollment()
		promote_enrollment(enrollment.name, self.ay2, repeat=True)
		enrollment.reload()
		log = [(r.academic_year, r.year_no, r.status) for r in enrollment.academic_log]
		self.assertEqual(log, [(self.ay1, 1, "Redo"), (self.ay1, 1, "Redo"), (self.ay2, 1, "Ongoing")])

	def test_promotion_must_move_forward_in_time(self):
		enrollment = self.make_enrollment()
		earlier = self.make_academic_year(f"{self.p} AY0", date(2090, 6, 1), date(2091, 5, 31))
		with self.assertRaisesRegex(frappe.ValidationError, "must start after"):
			promote_enrollment(enrollment.name, earlier)

	def test_no_promotion_beyond_final_year(self):
		one_year = self.make_programme(f"{self.p} One Year", duration=1)
		enrollment = self.make_enrollment(programme=one_year)
		with self.assertRaisesRegex(frappe.ValidationError, "final year"):
			promote_enrollment(enrollment.name, self.ay2)


# ── Classes ───────────────────────────────────────────────────────────────────


class TestClasses(ProgrammeManagementTestCase):
	def test_naming_and_course_details(self):
		cls_doc = self.make_class()
		self.assertTrue(cls_doc.name.startswith(f"CLS-91-1-T1-{self.section_a}-"), cls_doc.name)
		self.assertEqual(cls_doc.course_name, f"{self.p} Legal Methods")
		self.assertEqual(cls_doc.course_type, "Core")
		self.assertEqual(cls_doc.credit, 4)
		self.assertEqual(cls_doc.total_students, 0)

	def test_explicit_credit_is_kept(self):
		self.assertEqual(self.make_class(credit=2).credit, 2)

	def test_group_class(self):
		cls_doc = self.make_class(class_type="Group", group_name="Moot Court", section=None)
		self.assertTrue(cls_doc.name.startswith("CLS-91-1-T1-G-"), cls_doc.name)
		self.assertIsNone(cls_doc.section)

	def test_section_class_clears_group_name(self):
		self.assertIsNone(self.make_class(group_name="Ignored").group_name)

	# KNOWN GAP: Frappe enforces mandatory_depends_on only in the form, and
	# Classes.validate does not check it, so the server (and create_classes)
	# accepts a Group class without a group name and a Section class without
	# a section (named CLS-..-None-#####). Remove expectedFailure once fixed.
	@unittest.expectedFailure
	def test_group_name_required_for_group_class(self):
		with self.assertRaises(frappe.MandatoryError):
			self.make_class(class_type="Group")

	@unittest.expectedFailure
	def test_section_required_for_section_class(self):
		doc = frappe.get_doc({
			"doctype": "Classes", "class_type": "Section", "academic_year": self.ay1, "academic_term": self.t1,
			"programme": self.programme, "year_no": 1, "course": self.course,
		})
		with self.assertRaises(frappe.MandatoryError):
			doc.insert()

	def test_term_must_belong_to_academic_year(self):
		with self.assertRaisesRegex(frappe.ValidationError, "does not belong to Academic Year"):
			self.make_class(academic_term=self.t3)

	def test_inactive_course_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "is Inactive"):
			self.make_class(course=self.inactive_course)

	def test_year_must_be_within_programme_duration(self):
		for year_no in (0, 4):
			with self.assertRaisesRegex(frappe.ValidationError, "Year must be between 1 and 3"):
				self.make_class(year_no=year_no)

	def test_duplicate_section_class_is_rejected(self):
		self.make_class()
		with self.assertRaisesRegex(frappe.ValidationError, "already has a class"):
			self.make_class()
		# Same course for another section, or another course for the same section, is fine.
		self.make_class(section=self.section_b)
		self.make_class(course=self.course2)

	def test_duplicate_group_class_is_rejected(self):
		self.make_class(class_type="Group", group_name="Moot Court")
		with self.assertRaisesRegex(frappe.ValidationError, "already has a class"):
			self.make_class(class_type="Group", group_name="Moot Court")
		self.make_class(class_type="Group", group_name="Legal Aid")

	def test_student_added_twice_is_rejected(self):
		enrollment = self.make_enrollment()
		with self.assertRaisesRegex(frappe.ValidationError, "more than once"):
			self.make_class([enrollment.name, enrollment.name])

	def test_student_of_another_programme_is_rejected_from_section_class(self):
		other = self.make_enrollment(programme=self.make_programme(f"{self.p} BBA LLB"))
		with self.assertRaisesRegex(frappe.ValidationError, "is enrolled in"):
			self.make_class([other.name])
		# A Group class may mix programmes.
		cls_doc = self.make_class([other.name], class_type="Group", group_name="Mixed")
		self.assertEqual(cls_doc.total_students, 1)

	def test_only_enrolled_students_can_be_added(self):
		enrollment = self.make_enrollment()
		enrollment.status = "Dropped"
		enrollment.save()
		with self.assertRaisesRegex(frappe.ValidationError, "is not Enrolled"):
			self.make_class([enrollment.name])

	def test_existing_student_stays_after_dropping(self):
		enrollment = self.make_enrollment()
		cls_doc = self.make_class([enrollment.name])
		frappe.db.set_value("Student Enrollment", enrollment.name, "status", "Dropped")
		cls_doc.reload()
		cls_doc.save()  # the dropped student is history, not an error

	def test_pace_student_is_rejected(self):
		enrollment = self.make_enrollment(student=self.make_student("Pace", admission_type="PACE"))
		with self.assertRaisesRegex(frappe.ValidationError, "PACE student"):
			self.make_class([enrollment.name])

	def test_class_is_written_to_enrolled_courses(self):
		enrollment = self.make_enrollment()
		cls_doc = self.make_class([enrollment.name])
		self.assertEqual(cls_doc.total_students, 1)

		enrollment.reload()
		self.assertEqual(len(enrollment.enrolled_courses), 1)
		row = enrollment.enrolled_courses[0]
		self.assertEqual(row.course, self.course)
		self.assertEqual(row.class_name, cls_doc.name)
		self.assertEqual(row.academic_term, self.t1)
		self.assertEqual(row.year_no, 1)
		self.assertEqual(row.credits, 4)
		self.assertEqual(str(row.faculty), self.faculty)
		self.assertEqual(row.status, "Upcoming")  # T1 starts in 2091
		self.assertEqual(term_course_status(self.t1), "Upcoming")

	def test_removed_student_keeps_course_row_without_class(self):
		enrollment = self.make_enrollment()
		cls_doc = self.make_class([enrollment.name])
		cls_doc.enrolled_students = []
		cls_doc.save()

		enrollment.reload()
		self.assertEqual(len(enrollment.enrolled_courses), 1)
		self.assertIsNone(enrollment.enrolled_courses[0].class_name)

	def test_deleting_class_unlinks_course_rows(self):
		enrollment = self.make_enrollment()
		self.make_class([enrollment.name]).delete()
		enrollment.reload()
		self.assertEqual(len(enrollment.enrolled_courses), 1)
		self.assertIsNone(enrollment.enrolled_courses[0].class_name)

	def test_class_student_status_flows_to_course_row(self):
		enrollment = self.make_enrollment()
		cls_doc = self.make_class([enrollment.name])
		cls_doc.enrolled_students[0].status = "Withdrawn"
		cls_doc.save()
		enrollment.reload()
		self.assertEqual(enrollment.enrolled_courses[0].status, "Withdrawn")

	def test_dropping_enrollment_drops_open_courses(self):
		enrollment = self.make_enrollment()
		self.make_class([enrollment.name])
		enrollment.reload()
		enrollment.status = "Dropped"
		enrollment.save()
		self.assertEqual(enrollment.enrolled_courses[0].status, "Dropped")

	def test_get_class_students(self):
		first = self.make_enrollment(student=self.make_student("Alpha"))
		second = self.make_enrollment(student=self.make_student("Beta"))
		cls_doc = self.make_class([first.name, second.name])
		self.assertEqual([r.student for r in get_class_students(cls_doc.name)], [first.student, second.student])

		frappe.db.set_value("Student Enrollment", second.name, "status", "Dropped")
		self.assertEqual([r.student for r in get_class_students(cls_doc.name)], [first.student])
		self.assertEqual(get_class_students(None), [])

	def test_get_enrollment_students_filters(self):
		regular = self.make_enrollment()
		pace = self.make_enrollment(student=self.make_student("Pace", admission_type="PACE"))
		section_b = self.make_enrollment(section=self.section_b)

		names = [r.name for r in get_enrollment_students(programme=self.programme, academic_year=self.ay1, year_no=1)]
		self.assertIn(regular.name, names)
		self.assertIn(section_b.name, names)
		self.assertNotIn(pace.name, names)

		names = [r.name for r in get_enrollment_students(programme=self.programme, section=self.section_b)]
		self.assertEqual(names, [section_b.name])

		self.assertEqual(get_enrollment_students(programme=self.programme, academic_year=self.ay2), [])

	def test_create_classes_creates_and_skips_existing(self):
		enrollment = self.make_enrollment()
		data = {
			"academic_year": self.ay1, "academic_term": self.t1, "programme": self.programme, "year_no": 1,
			"section": self.section_a,
			"courses": [{"course": self.course, "faculty": self.faculty}, {"course": self.course2}],
			"students": [enrollment.name, enrollment.name],
		}
		result = create_classes(frappe.as_json(data))
		self.assertEqual(len(result["created"]), 2)
		self.assertEqual(result["skipped"], [])
		self.assertEqual(frappe.db.get_value("Classes", result["created"][0], "total_students"), 1)

		again = create_classes(data)
		self.assertEqual(again["created"], [])
		self.assertEqual(sorted(s["class"] for s in again["skipped"]), sorted(result["created"]))

	def test_create_classes_needs_courses_and_students(self):
		data = {"academic_year": self.ay1, "academic_term": self.t1, "programme": self.programme,
			"section": self.section_a}
		with self.assertRaisesRegex(frappe.ValidationError, "at least one Course"):
			create_classes({**data, "courses": [], "students": ["x"]})
		with self.assertRaisesRegex(frappe.ValidationError, "at least one student"):
			create_classes({**data, "courses": [{"course": self.course}], "students": []})


# ── Time Table ────────────────────────────────────────────────────────────────


class TestTimeTable(ProgrammeManagementTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enrollment = cls.make_enrollment()
		cls.class_name = cls.make_class([cls.enrollment.name]).name
		cls.class_b = cls.make_class(section=cls.section_b).name

	def test_details_are_taken_from_class(self):
		doc = self.time_table_doc(self.class_name).insert()
		self.assertEqual(doc.course, self.course)
		self.assertEqual(doc.programme, self.programme)
		self.assertEqual(doc.section, self.section_a)
		self.assertEqual(doc.academic_year, self.ay1)
		self.assertEqual(doc.academic_term, self.t1)
		self.assertEqual(str(doc.instructor), self.faculty)
		self.assertEqual(doc.title, f"{self.p} Legal Methods - {self.section_a}")
		self.assertEqual(doc.duration_hours, 1)

	def test_duration_is_hours_dot_minutes(self):
		doc = self.time_table_doc(self.class_name, from_time="09:00:00", to_time="10:30:00").insert()
		self.assertEqual(doc.duration_hours, 1.3)

	def test_class_is_required_for_class_entry(self):
		with self.assertRaises(frappe.ValidationError):
			self.time_table_doc(None).insert()

	def test_missing_class_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.time_table_doc(f"{self.p}-NO-CLASS").insert()

	def test_venue_is_mandatory(self):
		with self.assertRaises(frappe.MandatoryError):
			self.time_table_doc(self.class_name, venue=None).insert()

	def test_to_time_must_be_after_from_time(self):
		for to_time in ("09:00:00", "08:00:00"):
			with self.assertRaisesRegex(frappe.ValidationError, "To Time must be after From Time"):
				self.time_table_doc(self.class_name, from_time="09:00:00", to_time=to_time).insert()

	def test_schedule_must_be_inside_class_term(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Schedule Date and Repeats Till"):
			self.time_table_doc(self.class_name, schedule_date=next_weekday(T2_START, 0)).insert()
		with self.assertRaisesRegex(frappe.ValidationError, "Schedule Date and Repeats Till"):
			self.time_table_doc(
				self.class_name, repeat_frequency="Weekly", repeats_till=T1_END + timedelta(days=7)
			).insert()

	def test_sunday_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Weekly Off"):
			self.time_table_doc(self.class_name, schedule_date=SUNDAY).insert()

	def test_holiday_is_rejected(self):
		holiday = MONDAY + timedelta(days=7)
		frappe.get_doc({
			"doctype": "Institutional Calendar", "name1": f"{self.p} Holiday", "academic_year": self.ay1,
			"entry_type": "Holiday", "start_date": holiday, "end_date": holiday, "status": "Active",
		}).insert()
		with self.assertRaisesRegex(frappe.ValidationError, "Holiday"):
			self.time_table_doc(self.class_name, schedule_date=holiday).insert()

	def test_repeat_needs_valid_repeats_till(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Repeats Till"):
			self.time_table_doc(self.class_name, repeat_frequency="Weekly").insert()
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be before Schedule Date"):
			self.time_table_doc(
				self.class_name, repeat_frequency="Weekly", repeats_till=MONDAY - timedelta(days=1)
			).insert()

	def test_venue_double_booking_is_rejected(self):
		self.time_table_doc(self.class_name).insert()
		with self.assertRaisesRegex(frappe.ValidationError, "already booked"):
			self.time_table_doc(self.class_b, from_time="09:30:00", to_time="10:30:00").insert()

	def test_back_to_back_and_other_venue_are_allowed(self):
		self.time_table_doc(self.class_name).insert()
		self.time_table_doc(self.class_b, from_time="10:00:00", to_time="11:00:00").insert()
		self.time_table_doc(self.class_b, from_time="09:00:00", to_time="10:00:00", venue=self.venue2).insert()

	def test_instructor_clash_is_only_a_warning(self):
		# Both classes have the same faculty; different venues, same time.
		self.time_table_doc(self.class_name).insert()
		doc = self.time_table_doc(self.class_b, venue=self.venue2).insert()
		self.assertTrue(frappe.db.exists("Time Table", doc.name))

	def test_attendance_session_is_created_and_updated(self):
		doc = self.time_table_doc(self.class_name).insert()
		session = frappe.get_doc("Attendance Session", {"class_schedule": doc.name})
		self.assertEqual(getdate(session.session_date), MONDAY)
		self.assertEqual(session.class_name, self.class_name)
		self.assertEqual(session.course, self.course)
		self.assertEqual(session.section, self.section_a)
		self.assertEqual(str(session.instructor), self.faculty)
		self.assertEqual(session.session_type, "Lecture")
		self.assertEqual(session.session_status, "Scheduled")

		doc.from_time, doc.to_time = "11:00:00", "12:30:00"
		doc.save()
		session.reload()
		self.assertEqual(str(session.session_start_time), "11:00:00")
		self.assertEqual(str(session.session_end_time), "12:30:00")
		self.assertEqual(frappe.db.count("Attendance Session", {"class_schedule": doc.name}), 1)

	def test_weekly_repeat_creates_occurrences(self):
		doc = self.time_table_doc(
			self.class_name, repeat_frequency="Weekly", repeats_till=MONDAY + timedelta(weeks=3)
		).insert()
		children = frappe.get_all(
			"Time Table",
			filters={"parent_schedule": doc.name},
			fields=["schedule_date", "repeat_frequency", "class_name", "venue"],
			order_by="schedule_date",
		)
		self.assertEqual([getdate(c.schedule_date) for c in children],
			[MONDAY + timedelta(weeks=n) for n in (1, 2, 3)])
		self.assertTrue(all(c.repeat_frequency == "Never" and c.class_name == self.class_name for c in children))
		self.assertEqual(frappe.db.count("Attendance Session", {"class_name": self.class_name}), 4)

	def test_daily_repeat_skips_sundays_and_holidays(self):
		holiday = MONDAY + timedelta(days=2)
		frappe.get_doc({
			"doctype": "Institutional Calendar", "name1": f"{self.p} Mid-week Holiday", "academic_year": self.ay1,
			"entry_type": "Holiday", "start_date": holiday, "end_date": holiday, "status": "Active",
		}).insert()
		doc = self.time_table_doc(
			self.class_name, repeat_frequency="Daily", repeats_till=MONDAY + timedelta(days=7)
		).insert()
		dates = [getdate(d) for d in frappe.get_all(
			"Time Table", filters={"parent_schedule": doc.name}, pluck="schedule_date", order_by="schedule_date"
		)]
		expected = [MONDAY + timedelta(days=n) for n in range(1, 8)]
		expected = [d for d in expected if d.weekday() != 6 and d != holiday]
		self.assertEqual(dates, expected)

	def test_repeat_skips_dates_where_venue_is_booked(self):
		booked = MONDAY + timedelta(weeks=1)
		self.time_table_doc(self.class_b, schedule_date=booked).insert()
		doc = self.time_table_doc(
			self.class_name, repeat_frequency="Weekly", repeats_till=MONDAY + timedelta(weeks=2)
		).insert()
		dates = [getdate(d) for d in frappe.get_all(
			"Time Table", filters={"parent_schedule": doc.name}, pluck="schedule_date"
		)]
		self.assertEqual(dates, [MONDAY + timedelta(weeks=2)])

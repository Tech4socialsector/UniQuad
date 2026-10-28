# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import cint, getdate

from slcm.slcm.doctype.student_enrollment.student_enrollment import (
	enrollments_in_year,
	get_current_logs,
	sync_class_to_enrollments,
)

# Stands in for the section in the name of a Group class.
GROUP_CODE = "G"


class Classes(Document):
	def autoname(self):
		# CLS-{YY}-{year_no}-T{term_no}-{section}-{#####}, e.g. CLS-26-1-T1-A-00001
		# (a Group class uses G for the section: CLS-26-1-T1-G-00001)
		year_start = frappe.db.get_value("Academic Year", self.academic_year, "year_start_date")
		yy = getdate(year_start).strftime("%y")
		term_no = cint(frappe.db.get_value("Academic Term", self.academic_term, "term_no"))
		section = GROUP_CODE if self.class_type == "Group" else self.section
		self.name = make_autoname(f"CLS-{yy}-{cint(self.year_no)}-T{term_no}-{section}-.#####", doc=self)

	def validate(self):
		if self.class_type == "Group":
			self.section = None
		else:
			self.group_name = None
		self.validate_term_and_course()
		self.validate_duplicate_class()
		self.validate_students()
		self.total_students = len(self.enrolled_students)

	def on_update(self):
		# Each student's enrolled course row carries this class, term, year and status.
		sync_class_to_enrollments(self)

	def on_trash(self):
		sync_class_to_enrollments(self, removed=True)

	def validate_term_and_course(self):
		term_year = frappe.db.get_value("Academic Term", self.academic_term, "academic_year")
		if term_year != self.academic_year:
			frappe.throw(_("Academic Term {0} does not belong to Academic Year {1}").format(
				self.academic_term, self.academic_year))

		course = frappe.db.get_value("Course", self.course,
			["course_name", "course_type", "credit_value", "status"], as_dict=True)
		if not course:
			frappe.throw(_("Course {0} does not exist").format(self.course))
		if course.status == "Inactive" and self.is_new():
			frappe.throw(_("Course {0} is Inactive").format(course.course_name or self.course))
		self.course_name = course.course_name
		self.course_type = course.course_type
		if not cint(self.credit):
			self.credit = course.credit_value

		duration = cint(frappe.db.get_value("Programme", self.programme, "program_duration"))
		if cint(self.year_no) < 1 or (duration and cint(self.year_no) > duration):
			frappe.throw(_("Year must be between 1 and {0} for {1}").format(duration or 1, self.programme))

	def validate_duplicate_class(self):
		"""One Section class per course, term and section; one Group class per
		course, term and group name."""
		filters = {"course": self.course, "academic_term": self.academic_term,
			"class_type": self.class_type, "name": ["!=", self.name]}
		if self.class_type == "Group":
			filters["group_name"] = self.group_name
		else:
			filters["section"] = self.section
		existing = frappe.db.get_value("Classes", filters)
		if existing:
			frappe.throw(_("{0} already has a class for {1} in {2}: {3}").format(
				self.section or self.group_name, self.course_name or self.course, self.academic_term,
				frappe.bold(existing)))

	def validate_students(self):
		seen = set()
		for row in self.enrolled_students:
			if row.student_enrollment in seen:
				frappe.throw(_("Row {0}: Student {1} is added more than once").format(
					row.idx, row.student_enrollment))
			seen.add(row.student_enrollment)

			# A Group class may mix programmes, years and sections; a Section class may not.
			if self.class_type == "Group":
				continue
			program = frappe.db.get_value("Student Enrollment", row.student_enrollment, "program")
			if program != self.programme:
				frappe.throw(_("Row {0}: Student {1} is enrolled in {2}, not {3}").format(
					row.idx, row.student_enrollment, program, self.programme))


def get_class_students(class_name):
	"""Students of a class: its Enrolled rows whose enrollment is itself
	Enrolled, as [{student, student_name}] sorted by name. Used as the roster
	for Time Table / Attendance Session entries linked to the class."""
	if not class_name:
		return []
	return frappe.db.sql(
		"""
		SELECT DISTINCT se.student, se.student_name
		FROM `tabClass Enrolled Student` ces
		JOIN `tabStudent Enrollment` se ON se.name = ces.student_enrollment
		WHERE ces.parent = %s AND ces.parenttype = 'Classes'
		  AND ces.status = 'Enrolled' AND se.status = 'Enrolled'
		ORDER BY se.student_name
		""",
		(class_name,),
		as_dict=True,
	)


@frappe.whitelist()
def get_enrollment_students(programme=None, academic_year=None, year_no=None, section=None):
	"""Active enrollments matching the given filters (any left empty is ignored).
	Academic year and year are matched against the enrollment's Academic Log."""
	filters = {"status": "Enrolled"}
	if programme:
		filters["program"] = programme
	if section:
		filters["section"] = section
	if academic_year or cint(year_no):
		filters["name"] = ["in", enrollments_in_year(academic_year, year_no) or [""]]
	rows = frappe.get_all(
		"Student Enrollment",
		filters=filters,
		fields=["name", "student_name", "section", "program"],
		order_by="section, name",
	)
	current = get_current_logs([r.name for r in rows])
	for r in rows:
		r.year_no = cint(year_no) or cint((current.get(r.name) or {}).get("year_no"))
	return rows


@frappe.whitelist()
def create_classes(data):
	"""Create one Classes record per course picked, all with the same students.

	data.courses: [{course, faculty, credit}]. A class that already exists for
	the course, term and section (or group name) is skipped, not duplicated.
	"""
	data = frappe._dict(json.loads(data) if isinstance(data, str) else data)
	frappe.has_permission("Classes", "create", throw=True)

	courses = [frappe._dict(c) for c in (data.courses or []) if c and c.get("course")]
	if not courses:
		frappe.throw(_("Select at least one Course"))
	students = list(dict.fromkeys(s for s in (data.students or []) if s))
	if not students:
		frappe.throw(_("Add at least one student"))

	class_type = data.class_type or "Section"
	created, skipped = [], []
	for c in courses:
		filters = {"course": c.course, "academic_term": data.academic_term, "class_type": class_type}
		if class_type == "Group":
			filters["group_name"] = data.group_name
		else:
			filters["section"] = data.section
		existing = frappe.db.get_value("Classes", filters)
		if existing:
			skipped.append({"course": c.course, "class": existing})
			continue
		doc = frappe.get_doc({
			"doctype": "Classes",
			"class_type": class_type,
			"academic_year": data.academic_year,
			"academic_term": data.academic_term,
			"programme": data.programme,
			"year_no": cint(data.year_no) or 1,
			"section": data.section,
			"group_name": data.group_name,
			"course": c.course,
			"faculty": c.faculty,
			"credit": cint(c.credit),
			"enrolled_students": [{"student_enrollment": s, "status": "Enrolled"} for s in students],
		})
		doc.insert()
		created.append(doc.name)
	return {"created": created, "skipped": skipped}

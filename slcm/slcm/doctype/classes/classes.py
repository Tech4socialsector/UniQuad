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
		self.validate_term_and_offering()
		self.validate_students()
		self.total_students = len(self.enrolled_students)

	def on_update(self):
		# Each student's enrolled course row carries this class, term, year and status.
		sync_class_to_enrollments(self)

	def on_trash(self):
		sync_class_to_enrollments(self, removed=True)

	def validate_term_and_offering(self):
		term_year = frappe.db.get_value("Academic Term", self.academic_term, "academic_year")
		if term_year != self.academic_year:
			frappe.throw(_("Academic Term {0} does not belong to Academic Year {1}").format(
				self.academic_term, self.academic_year))

		offering = frappe.db.get_value("Course Offering", self.course_offering,
			["program", "academic_year", "term_name", "year_no"], as_dict=True)
		if (offering.program, offering.academic_year, offering.term_name) != (
			self.programme, self.academic_year, self.academic_term):
			frappe.throw(_("Course Offering {0} is not offered for this Programme, Academic Year and Term").format(
				self.course_offering))
		self.year_no = offering.year_no

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
	"""Create one Classes record per Course Offering, all with the same students.

	Section classes that already exist for an offering + section are skipped, not duplicated.
	"""
	data = frappe._dict(json.loads(data) if isinstance(data, str) else data)
	frappe.has_permission("Classes", "create", throw=True)

	offerings = [o for o in (data.course_offerings or []) if o]
	if not offerings:
		frappe.throw(_("Select at least one Course Offering"))
	students = list(dict.fromkeys(s for s in (data.students or []) if s))
	if not students:
		frappe.throw(_("Add at least one student"))

	created, skipped = [], []
	for offering in offerings:
		if data.class_type != "Group":
			existing = frappe.db.get_value("Classes",
				{"course_offering": offering, "section": data.section, "class_type": "Section"})
			if existing:
				skipped.append({"course_offering": offering, "class": existing})
				continue
		doc = frappe.get_doc({
			"doctype": "Classes",
			"class_type": data.class_type or "Section",
			"academic_year": data.academic_year,
			"academic_term": data.academic_term,
			"programme": data.programme,
			"section": data.section,
			"group_name": data.group_name,
			"course_offering": offering,
			"enrolled_students": [{"student_enrollment": s, "status": "Enrolled"} for s in students],
		})
		doc.insert()
		created.append(doc.name)
	return {"created": created, "skipped": skipped}

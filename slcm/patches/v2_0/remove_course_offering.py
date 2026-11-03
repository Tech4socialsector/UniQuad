"""Remove the Course Offering doctype.

Classes (course + programme + academic year + term + year + section/group +
faculty) replace Course Offerings. Records about a taught group of students
now link the class (class_name) and its course; records about a course in a
term across sections link course + academic_term.

Runs after model sync: the old `course_offering` columns are no longer in the
doctypes but are still in the tables, so the new fields are filled from them
(and from `tabCourse Offering`) before the Course Offering doctype, its table
and the dashboards built on it are deleted. Values already set are kept.
"""

import frappe

# Course Offering column for each source name used in MAPPINGS.
OFFERING = {
	"course": "course_title",
	"academic_term": "term_name",
	"academic_year": "academic_year",
	"programme": "program",
	"year_no": "year_no",
	"faculty": "faculty",
	"credit": "credit_value",
}

# (doctype, old column, [(new field, source), ...]), applied in order; a field
# listed twice takes the second source where the first left it empty.
# Sources:
#   offering.<key>  the offering's column (OFFERING)
#   class           the Classes record made for the offering: the one the
#                   record's student is in, else the one of its section, else
#                   the offering's only class
#   cls.<field>     from the class now in class_name
#   col.<column>    another (old) column of the same record
#   plan.<field>    from the record's Exam Plan (exam_plan)
# "force:" in front overwrites a value already set.
CLASS_LINKED = [("class_name", "class"), ("course", "cls.course")]
EXAM = [("course", "offering.course"), ("academic_term", "offering.academic_term"), ("academic_term", "plan.term")]
MAPPINGS = [
	# Core
	("Classes", "course_offering", [("course", "offering.course"), ("year_no", "offering.year_no")]),
	("Student Enrollment Course", "course_offering", [
		("course", "offering.course"), ("academic_year", "offering.academic_year"),
		("academic_term", "offering.academic_term"), ("year_no", "offering.year_no"),
	]),
	("Program Enrollment", "course_offering", [("course", "offering.course")]),
	("Program Enrollment Course", "course_offering", [("course", "offering.course")]),
	("Program Course", "course_offering", [("course", "offering.course")]),
	("Curriculum Course", "course_offering", [("course", "offering.course")]),
	("Course Prerequisite", "prerequisite_course_offering", [("prerequisite_course", "offering.course")]),
	("Course Enrollment", "course_offering", [("course", "offering.course")]),
	("Class Configuration", "course_offering", [("course", "offering.course")]),
	# Attendance, time table, office hours
	("Student Attendance", "course_offer", CLASS_LINKED + [("course", "offering.course")]),
	("Attendance Session", "course_offering", CLASS_LINKED + [("course", "offering.course")]),
	("Time Table", "course_offering", [
		("class_name", "class"), ("course", "force:cls.course"), ("course", "offering.course"),
	]),
	("Attendance Summary", "course_offering", CLASS_LINKED + [
		("course", "offering.course"), ("programme", "cls.programme"), ("programme", "offering.programme"),
		("academic_year", "cls.academic_year"), ("academic_year", "offering.academic_year"),
		("academic_term", "cls.academic_term"), ("academic_term", "col.term_name"),
		("academic_term", "offering.academic_term"),
	]),
	("Student Attendance Condonation", "course_offering", CLASS_LINKED + [
		("course", "offering.course"), ("academic_year", "cls.academic_year"),
		("academic_year", "offering.academic_year"),
	]),
	("Office Hours Attendance", "course_offering", CLASS_LINKED),
	("Office Hours Group", "course_offering", CLASS_LINKED),
	("Office Hours Session", "course_offering", CLASS_LINKED),
	("Student Group", "course_offering", CLASS_LINKED),
	("Course Schedule", "course_offering", CLASS_LINKED),
	("Attendance Edit Log", "course_offering", CLASS_LINKED),
	("Attendance Reopen Log", "course_offering", CLASS_LINKED),
	# Exams, marks, results: course + academic term
	*[(doctype, "course_offering", EXAM) for doctype in (
		"Exam Assessment Schedule Item", "Exam Course Schedule", "Exam Barcode", "Student Course Marks",
		"Grade Appeal", "Course Schema Assignment", "Schema Change Log", "Access Result Settings",
		"Re Exam Student Override", "Re Exam Registration", "Re Exam Course Setting", "Re Exam Payment Log",
		"Improvement Exam Registration", "Improvement Exam Course Setting", "Improvement Exam Payment Log",
		"FA MFA Application",
	)],
]

OLD_CARDS = ("Open Course Offerings", "Faculty Open Course Offerings", "Faculty My Course Offerings")
OLD_CHARTS = ("Course Offerings by Status", "Faculty Course Offerings by Status")


def execute():
	if frappe.db.table_exists("Course Offering"):
		for doctype, old, targets in MAPPINGS:
			migrate(doctype, old, targets)
		fill_class_details()
		dedupe_schema_assignments()

	map_statuses()
	delete_course_offering()
	frappe.db.commit()


def _cols(doctype):
	return set(frappe.db.get_table_columns(doctype)) if frappe.db.table_exists(doctype) else set()


def migrate(doctype, old, targets):
	cols = _cols(doctype)
	if old not in cols:
		return
	table = f"`tab{doctype}`"
	class_field = next((f for f, s in targets if s == "class"), "class_name")
	for new, source in targets:
		if new not in cols:
			continue
		force = source.startswith("force:")
		source = source.removeprefix("force:")
		if force:
			empty = "1 = 1"
		elif new in ("year_no", "credit"):
			empty = f"IFNULL(t.`{new}`, 0) = 0"
		else:
			empty = f"IFNULL(t.`{new}`, '') = ''"

		if source.startswith("offering."):
			src = OFFERING[source.split(".", 1)[1]]
			frappe.db.sql(f"""
				UPDATE {table} t JOIN `tabCourse Offering` co ON co.name = t.`{old}`
				SET t.`{new}` = co.`{src}` WHERE {empty}""")
		elif source.startswith("cls."):
			if class_field not in cols:
				continue
			src = source.split(".", 1)[1]
			frappe.db.sql(f"""
				UPDATE {table} t JOIN `tabClasses` cls ON cls.name = t.`{class_field}`
				SET t.`{new}` = cls.`{src}` WHERE {empty} AND IFNULL(cls.`{src}`, '') != ''""")
		elif source.startswith("plan."):
			src = source.split(".", 1)[1]
			if "exam_plan" in cols:
				frappe.db.sql(f"""
					UPDATE {table} t JOIN `tabExam Plan` ep ON ep.name = t.exam_plan
					SET t.`{new}` = ep.`{src}` WHERE {empty} AND IFNULL(ep.`{src}`, '') != ''""")
		elif source.startswith("col."):
			src = source.split(".", 1)[1]
			if src in cols:
				frappe.db.sql(f"UPDATE {table} t SET t.`{new}` = t.`{src}` WHERE {empty}")
		elif source == "class":
			_set_class(table, cols, old, new, empty)


def _set_class(table, cols, old, new, empty):
	"""The Classes record made for the offering: the one the record's student
	is enrolled in, else the one of its section, else the offering's only class."""
	if "course_offering" not in _cols("Classes"):
		return
	if "student" in cols:
		frappe.db.sql(f"""
			UPDATE {table} t
			JOIN `tabClasses` cls ON cls.course_offering = t.`{old}`
			JOIN `tabClass Enrolled Student` ces ON ces.parent = cls.name AND ces.parenttype = 'Classes'
			JOIN `tabStudent Enrollment` se ON se.name = ces.student_enrollment AND se.student = t.student
			SET t.`{new}` = cls.name WHERE {empty}""")
	if "section" in cols:
		frappe.db.sql(f"""
			UPDATE {table} t JOIN `tabClasses` cls
			  ON cls.course_offering = t.`{old}` AND cls.section = t.section
			SET t.`{new}` = cls.name WHERE {empty}""")
	frappe.db.sql(f"""
		UPDATE {table} t JOIN (
			SELECT course_offering, MIN(name) AS name FROM `tabClasses`
			GROUP BY course_offering HAVING COUNT(*) = 1
		) cls ON cls.course_offering = t.`{old}`
		SET t.`{new}` = cls.name WHERE {empty}""")


def fill_class_details():
	"""Classes carry the course's name, type and credit."""
	frappe.db.sql("""
		UPDATE `tabClasses` cls JOIN `tabCourse` c ON c.name = cls.course
		SET cls.course_name = IFNULL(NULLIF(cls.course_name, ''), c.course_name),
		    cls.course_type = c.course_type,
		    cls.credit = IF(IFNULL(cls.credit, 0) = 0, c.credit_value, cls.credit)""")
	frappe.db.sql("UPDATE `tabClasses` SET year_no = 1 WHERE IFNULL(year_no, 0) = 0")


def dedupe_schema_assignments():
	"""One Course Schema Assignment per exam plan and course: two offerings of
	a course (different programmes) in one plan had one each."""
	frappe.db.sql("""
		DELETE dup FROM `tabCourse Schema Assignment` dup
		JOIN `tabCourse Schema Assignment` keep
		  ON keep.exam_plan = dup.exam_plan AND keep.course = dup.course
		 AND (keep.creation < dup.creation OR (keep.creation = dup.creation AND keep.name < dup.name))""")


def map_statuses():
	"""Class students: Failed -> Carry Forward. Enrolled courses: Failed / Redo
	-> Carry Forward; Enrolled (and anything open) follows the term's dates,
	and is Completed once the student has left that academic year."""
	from slcm.slcm.doctype.student_enrollment.student_enrollment import (
		MANUAL_COURSE_STATUSES,
		OPEN_LOG_STATUSES,
		term_course_status,
	)

	frappe.db.sql("UPDATE `tabClass Enrolled Student` SET status = 'Carry Forward' WHERE status = 'Failed'")
	frappe.db.sql("""UPDATE `tabMarks Import Log Detail` SET status = 'Missing Class'
		WHERE status = 'Missing Course Offering'""")
	frappe.db.sql("""UPDATE `tabStudent Enrollment Course` SET status = 'Carry Forward'
		WHERE status IN ('Failed', 'Redo')""")

	open_years = {}
	for row in frappe.get_all(
		"Student Academic Log",
		filters={"parenttype": "Student Enrollment", "status": ["in", list(OPEN_LOG_STATUSES)]},
		fields=["parent", "academic_year"],
	):
		open_years.setdefault(row.parent, set()).add(row.academic_year)

	for row in frappe.get_all(
		"Student Enrollment Course",
		filters={"parenttype": "Student Enrollment", "status": ["not in", list(MANUAL_COURSE_STATUSES)]},
		fields=["name", "parent", "academic_year", "academic_term", "status"],
	):
		status = term_course_status(row.academic_term)
		if status in ("Ongoing", "Upcoming") and row.academic_year \
				and row.academic_year not in open_years.get(row.parent, set()):
			status = "Completed"
		if status != row.status:
			frappe.db.set_value("Student Enrollment Course", row.name, "status", status, update_modified=False)


def delete_course_offering():
	for name in OLD_CARDS:
		frappe.delete_doc_if_exists("Number Card", name, force=1)
	for name in OLD_CHARTS:
		frappe.delete_doc_if_exists("Dashboard Chart", name, force=1)

	# Desk links / shortcuts / sidebar items to the doctype now open Course
	# (site-made sidebars too; the app's own are re-synced from their files).
	for child in ("Workspace Link", "Workspace Shortcut", "Workspace Sidebar Item", "Sidebar Item"):
		if frappe.db.table_exists(child):
			frappe.db.sql(f"""UPDATE `tab{child}`
				SET link_to = 'Course', label = IF(label = 'Course Offering', 'Course', label)
				WHERE link_to = 'Course Offering'""")

	frappe.db.delete("Custom Field", {"dt": ["in", ["Course Offering", "Course Offering Faculty"]]})
	frappe.db.delete("Property Setter", {"doc_type": ["in", ["Course Offering", "Course Offering Faculty"]]})
	frappe.db.delete("Custom Field", {"options": "Course Offering"})
	# Customisations of the removed fields on other doctypes
	frappe.db.delete("Property Setter", {
		"field_name": ["in", ["course_offering", "course_offer", "prerequisite_course_offering"]]})

	for doctype in ("Course Offering Faculty", "Course Offering"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=1, ignore_missing=True)
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")

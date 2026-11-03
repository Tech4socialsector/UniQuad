# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import cint, getdate, now_datetime

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
		self.track_student_changes()
		self.total_students = len(self.enrolled_students)

	def track_student_changes(self):
		"""Stamp who added each student and when, and log every student added,
		removed or changed in status after the class was created. Set here on
		the server for every path (grid, Add / Remove Students, import, API);
		values sent by the client for these fields and the log are ignored."""
		now, user = now_datetime(), frappe.session.user
		previous = self.get_doc_before_save()
		if not previous:
			for row in self.enrolled_students:
				row.update({"added_on": now, "added_by": user, "added_after_creation": 0})
			self.set("student_log", [])
			return

		# The log only grows: rebuild it from the saved rows, then append.
		self.set("student_log", [r.as_dict() for r in previous.get("student_log") or []])

		def log(action, row, from_status=None, to_status=None):
			self.append("student_log", {
				"changed_on": now, "changed_by": user, "action": action,
				"student_enrollment": row.student_enrollment, "student_name": row.student_name,
				"from_status": from_status, "to_status": to_status,
			})

		was = {r.student_enrollment: r for r in previous.enrolled_students}
		for row in self.enrolled_students:
			old = was.get(row.student_enrollment)
			if not old:
				row.update({"added_on": now, "added_by": user, "added_after_creation": 1})
				log("Added", row, to_status=row.status)
				continue
			row.update({"added_on": old.added_on, "added_by": old.added_by,
				"added_after_creation": old.added_after_creation})
			if old.status != row.status:
				log("Status Changed", row, old.status, row.status)

		staying = {r.student_enrollment for r in self.enrolled_students}
		for enrollment, old in was.items():
			if enrollment not in staying:
				log("Removed", old, from_status=old.status)

	def on_update(self):
		# Each student's enrolled course row carries this class, term, year and status.
		sync_class_to_enrollments(self)
		self.sync_exam_plans()

	def sync_exam_plans(self, deleted=False):
		# Students & marks of every active Exam Plan mapping this course follows
		# the class. An exam-side failure must not block the class.
		from slcm.slcm.page.examination_result.examination_result import sync_class_to_exam_plans

		message_count = len(frappe.local.message_log)
		frappe.db.savepoint("class_exam_students")
		try:
			sync_class_to_exam_plans(self, deleted=deleted)
		except Exception:
			frappe.db.rollback(save_point="class_exam_students")
			del frappe.local.message_log[message_count:]  # only this step's messages
			frappe.log_error(f"Syncing students of {self.name} to exam plans")
			frappe.msgprint(_("The class is saved, but Students & marks of the exam plan could not be updated. "
				"See the Error Log, or use Fetch from Enrollment on the course in the Exam Planner."),
				indicator="orange", alert=True)

	def on_trash(self):
		sync_class_to_enrollments(self, removed=True)
		self.sync_exam_plans(deleted=True)

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
		previous = self.get_doc_before_save()
		existing = {r.student_enrollment for r in (previous.enrolled_students if previous else [])}
		enrollments = {
			e.name: e for e in frappe.get_all(
				"Student Enrollment",
				filters={"name": ["in", [r.student_enrollment for r in self.enrolled_students] or [""]]},
				fields=["name", "student", "status"],
			)
		}
		pace = set(pace_students())
		seen = set()
		for row in self.enrolled_students:
			if row.student_enrollment in seen:
				frappe.throw(_("Row {0}: Student {1} is added more than once").format(
					row.idx, row.student_enrollment))
			seen.add(row.student_enrollment)

			enrollment = enrollments.get(row.student_enrollment) or frappe._dict()
			if enrollment.student in pace:
				frappe.throw(_("Row {0}: {1} is a PACE student and cannot be added to a class.").format(
					row.idx, row.student_name or row.student_enrollment))
			# Students already in the class stay (history); new ones must be Enrolled.
			if row.student_enrollment not in existing and enrollment.status != "Enrolled":
				frappe.throw(_("Row {0}: {1} is not Enrolled (status: {2}), so cannot be added to the class.").format(
					row.idx, row.student_name or row.student_enrollment, enrollment.status or _("not found")))

			# A Group class may mix programmes, years and sections; a Section class may not.
			if self.class_type == "Group":
				continue
			program = frappe.db.get_value("Student Enrollment", row.student_enrollment, "program")
			if program != self.programme:
				frappe.throw(_("Row {0}: Student {1} is enrolled in {2}, not {3}").format(
					row.idx, row.student_enrollment, program, self.programme))


def pace_students():
	"""Student Masters admitted through PACE (admission type PACE, or a PACE
	programme set). They are not part of degree classes."""
	return frappe.get_all(
		"Student Master",
		or_filters=[["admission_type", "=", "PACE"], ["pace_programme", "is", "set"]],
		pluck="name",
	)


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
	"""Active (Enrolled) enrollments matching the given filters (any left empty
	is ignored), without PACE students. Academic year and year are matched
	against the enrollment's Academic Log."""
	filters = {"status": "Enrolled"}
	pace = pace_students()
	if pace:
		filters["student"] = ["not in", pace]
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


# Create Class → Import Students sheet. Only Student ID is used to find the
# student; the other columns are there to help whoever fills the sheet.
STUDENT_SHEET_COLUMNS = ["Student ID", "Student Name", "Section", "Programme", "Year"]


@frappe.whitelist()
def download_class_students_template():
	"""Blank Import Students sheet (.xlsx) with the column headings."""
	from frappe.utils.xlsxutils import make_xlsx

	frappe.has_permission("Classes", "create", throw=True)
	xlsx = make_xlsx([STUDENT_SHEET_COLUMNS], "Students")
	frappe.response["filename"] = "class_students_template.xlsx"
	frappe.response["filecontent"] = xlsx.getvalue()
	frappe.response["type"] = "binary"


def _read_student_sheet(filename, content):
	"""Rows of an uploaded .xlsx or .csv (base64 content), as lists of cells."""
	import base64

	from frappe.utils.csvutils import read_csv_content
	from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

	try:
		raw = base64.b64decode((content or "").split(",")[-1])
	except Exception:
		frappe.throw(_("The file could not be read. Upload the .xlsx or .csv template."))
	ext = (filename or "").rsplit(".", 1)[-1].lower()
	try:
		if ext == "xlsx":
			return read_xlsx_file_from_attached_file(fcontent=raw)
		if ext == "csv":
			return read_csv_content(raw)
	except Exception:
		frappe.throw(_("The file could not be read. Upload the .xlsx or .csv template."))
	frappe.throw(_("Upload an .xlsx or .csv file (use Download Template)."))


@frappe.whitelist(methods=["POST"])
def import_class_students(filename, content):
	"""Students listed in an uploaded Import Students sheet.

	Returns {students: rows shaped like get_enrollment_students, not_found,
	not_enrolled, duplicates}; the last three are [{id, student_name}] (the
	name from the sheet when there is no record). Only the Student ID column
	is used to find students."""
	frappe.has_permission("Classes", "create", throw=True)
	rows = [[("" if c is None else str(c)).strip() for c in (r or [])] for r in _read_student_sheet(filename, content)]

	# The heading row is the first one with a "Student ID" cell
	header = next((i for i, r in enumerate(rows) if any(c.lower() == "student id" for c in r)), None)
	if header is None:
		frappe.throw(_("The sheet has no Student ID column. Use Download Template and keep its headings."))
	heads = [c.lower() for c in rows[header]]
	col = heads.index("student id")
	name_col = heads.index("student name") if "student name" in heads else None

	ids, duplicates, sheet_names = [], [], {}
	for r in rows[header + 1:]:
		sid = r[col].upper() if col < len(r) else ""
		if sid.endswith(".0"):  # a numeric ID read back from Excel
			sid = sid[:-2]
		if not sid:
			continue
		sheet_name = r[name_col] if name_col is not None and name_col < len(r) else ""
		if sid in ids:
			duplicates.append({"id": sid, "student_name": sheet_name or sheet_names.get(sid, "")})
		else:
			ids.append(sid)
			sheet_names[sid] = sheet_name
	if not ids:
		frappe.throw(_("The sheet has no Student IDs under the Student ID heading."))

	records = {
		r.name.upper(): r
		for r in frappe.get_all(
			"Student Enrollment",
			filters={"name": ["in", ids]},
			fields=["name", "student", "student_name", "section", "program", "status"],
		)
	}
	pace = set(pace_students())
	students, not_found, not_enrolled = [], [], []
	for sid in ids:
		r = records.get(sid)
		if not r:
			not_found.append({"id": sid, "student_name": sheet_names.get(sid, "")})
		elif r.status != "Enrolled" or r.student in pace:
			not_enrolled.append({"id": r.name, "student_name": r.student_name,
				"status": "PACE" if r.student in pace else r.status})
		else:
			students.append(r)

	current = get_current_logs([r.name for r in students])
	return {
		"students": [
			{"name": r.name, "student_name": r.student_name, "section": r.section, "program": r.program,
				"year_no": cint((current.get(r.name) or {}).get("year_no"))}
			for r in students
		],
		"not_found": not_found,
		"not_enrolled": not_enrolled,
		"duplicates": duplicates,
	}


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

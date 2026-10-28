import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_time

from slcm.slcm.doctype.student_enrollment.student_enrollment import year_log_exists

class OfficeHoursGroup(Document):
	def on_update(self):
		sync_office_hours_session(self)

	def on_trash(self):
		if self.office_hours_session:
			frappe.delete_doc(
				"Office Hours Session", self.office_hours_session,
				ignore_permissions=True, ignore_missing=True,
			)


def get_course_offering(course, program, academic_term):
	"""Resolve a Course Offering for this Course/Program/Term. Mirrors the
	fallback lookup used in Course Schedule (course_schedule.py)."""
	if not course:
		return None

	filters = {"course_title": course, "status": "Active"}
	if program:
		filters["program"] = program
	if academic_term:
		filters["term_name"] = academic_term

	offering = frappe.get_all("Course Offering", filters=filters, limit=1, pluck="name")
	if offering:
		return offering[0]

	if program:
		del filters["program"]
		offering = frappe.get_all("Course Offering", filters=filters, limit=1, pluck="name")
		if offering:
			return offering[0]

	return None


def sync_office_hours_session(doc):
	"""Keep an Office Hours Session in sync with this Office Hours Group so
	the session shows up under the Student Portal's Office Hours tab."""
	course_offering = get_course_offering(doc.course, doc.program, doc.academic_term)
	if not course_offering or not doc.date or not doc.from_time or not doc.to_time or not doc.instructor:
		return

	from_time = get_time(doc.from_time)
	to_time = get_time(doc.to_time)
	duration = round(
		(datetime.datetime.combine(datetime.date.min, to_time)
			- datetime.datetime.combine(datetime.date.min, from_time)).total_seconds() / 3600,
		2,
	)

	if doc.office_hours_session and frappe.db.exists("Office Hours Session", doc.office_hours_session):
		session = frappe.get_doc("Office Hours Session", doc.office_hours_session)
	else:
		session = frappe.new_doc("Office Hours Session")

	session.course_offering = course_offering
	session.faculty = doc.instructor
	session.session_date = doc.date
	session.start_time = doc.from_time
	session.end_time = doc.to_time
	session.duration_hours = duration
	if not session.session_status:
		session.session_status = "Scheduled"
	session.flags.ignore_permissions = True
	session.save()

	if doc.office_hours_session != session.name:
		frappe.db.set_value("Office Hours Group", doc.name, "office_hours_session", session.name)

@frappe.whitelist()
def get_students(program, course, academic_year=None, academic_term=None, batch=None, section=None):
	if not program:
		return []

	# Base query on Student Enrollment
	# We want students who are Active and Enrolled in the Program

	params = {"program": program}
	conditions = ["se.program = %(program)s", "se.status = 'Enrolled'", "se.docstatus < 2"]

	if academic_year:
		conditions.append(year_log_exists("se", "%(academic_year)s"))
		params["academic_year"] = academic_year

	if academic_term:
		# Match enrollments with a log row in the term's academic year.
		conditions.append(year_log_exists(
			"se",
			"(SELECT at.academic_year FROM `tabAcademic Term` at WHERE at.name = %(academic_term)s)",
		))
		params["academic_term"] = academic_term

	if batch:
		conditions.append("se.batch = %(batch)s")
		params["batch"] = batch

	if section:
		conditions.append("se.section = %(section)s")
		params["section"] = section

	# Join with Course via Student Enrollment Course → Course Offering
	join_course = ""
	if course:
		join_course = """
			INNER JOIN `tabStudent Enrollment Course` sec
			ON sec.parent = se.name
			INNER JOIN `tabCourse Offering` co
			ON co.name = sec.course_offering
			AND co.course_title = %(course)s
		"""
		params["course"] = course

	sql = f"""
		SELECT DISTINCT
			se.student,
			se.student_name
		FROM
			`tabStudent Enrollment` se
		{join_course}
		WHERE
			{" AND ".join(conditions)}
		ORDER BY se.student_name
	"""
	
	students = frappe.db.sql(sql, params, as_dict=True)
	
	# Check Student Master status to be consistent
	for s in students:
		status = frappe.db.get_value("Student Master", s.student, "student_status")
		s.active = 1 if status == "Active" else 0
		
	return students

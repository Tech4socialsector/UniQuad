# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class StudentAttendanceTool(Document):
	pass


def _get_enrolled_students(class_name):
	"""Roster for a Class: its Enrolled students."""
	if not class_name:
		return []

	from slcm.slcm.doctype.classes.classes import get_class_students

	return get_class_students(class_name)


@frappe.whitelist()
def get_student_attendance_records(
	based_on=None,
	date=None,
	class_schedule=None,
	office_hours_group=None,
):
	"""
	Get student list with existing attendance status
	"""

	# -------------------- VALIDATION --------------------

	if not based_on:
		frappe.throw(_("Based On is required"))

	# A class period (Based On "Class") is taken against its Time Table entry.
	if based_on == "Class":
		based_on = "Time Table"

	if based_on == "Time Table":
		if not class_schedule:
			frappe.throw(_("Time Table is required"))

	if based_on == "Office Hours":
		if not office_hours_group:
			frappe.throw(_("Office Hours Group is required"))

	# -------------------- FETCH STUDENTS --------------------

	if based_on == "Office Hours":
		# Office Hours Group is a Student Group (group_based_on = Office Hours);
		# its Student Group Student rows carry only the student link and
		# registration ID, so the display name comes from Student Master.
		student_list = frappe.db.sql("""
			SELECT sgs.student, sm.first_name AS student_name, sgs.student_id AS group_roll_number
			FROM `tabStudent Group Student` sgs
			LEFT JOIN `tabStudent Master` sm ON sm.name = sgs.student
			WHERE sgs.parent = %s AND sgs.parenttype = 'Student Group'
			ORDER BY sgs.idx
		""", (office_hours_group,), as_dict=True)
	else:
		class_name = None
		if based_on == "Time Table" and class_schedule:
			class_name = frappe.db.get_value("Time Table", class_schedule, "class_name")

		# A class-based entry: exactly that class's students.
		student_list = _get_enrolled_students(class_name)

	if not student_list:
		return []

	# -------------------- FETCH PHOTOS --------------------

	student_ids = [s["student"] for s in student_list]
	photo_map = {}
	if student_ids:
		photo_rows = frappe.get_all(
			"Student Master",
			fields=["name", "passport_size_photo"],
			filters={"name": ["in", student_ids]},
		)
		photo_map = {row["name"]: row["passport_size_photo"] for row in photo_rows}

	for student in student_list:
		student["student_image"] = photo_map.get(student["student"])

	# -------------------- FETCH EXISTING ATTENDANCE --------------------

	StudentAttendance = frappe.qb.DocType("Student Attendance")

	query = (
		frappe.qb.from_(StudentAttendance)
		.select(
			StudentAttendance.student,
			StudentAttendance.status,
		)
		.where(StudentAttendance.docstatus < 2)
	)

	if based_on == "Time Table":
		query = query.where(StudentAttendance.class_schedule == class_schedule)

	if date:
		query = query.where(StudentAttendance.attendance_date == date)

	if based_on == "Office Hours":
		query = query.where(StudentAttendance.office_hours_group == office_hours_group)

	attendance_rows = query.run(as_dict=True)

	# -------------------- MERGE STATUS --------------------

	attendance_map = {row["student"]: row["status"] for row in attendance_rows}

	for student in student_list:
		student["status"] = attendance_map.get(student["student"], "Present")

	return student_list

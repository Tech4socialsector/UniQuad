# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _


def execute(filters=None):
	if not filters:
		filters = {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"fieldname": "student",
			"label": _("Student"),
			"fieldtype": "Link",
			"options": "Student Master",
			"width": 150
		},
		{
			"fieldname": "student_name",
			"label": _("Student Name"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "program",
			"label": _("Batch"),
			"fieldtype": "Link",
			"options": "SLCM Batch",
			"width": 130
		},
		{
			"fieldname": "section",
			"label": _("Section"),
			"fieldtype": "Link",
			"options": "Section",
			"width": 100
		},
		{
			"fieldname": "course",
			"label": _("Course"),
			"fieldtype": "Data",
			"width": 200
		},
		{
			"fieldname": "total_classes",
			"label": _("Total Sessions"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "total_class_hours",
			"label": _("Total Class Hours"),
			"fieldtype": "Float",
			"width": 110
		},
		{
			"fieldname": "manual_attended_hours",
			"label": _("Manual Attended (hrs)"),
			"fieldtype": "Float",
			"width": 130
		},
		{
			"fieldname": "rfid_attended_hours",
			"label": _("RFID Attended (hrs)"),
			"fieldtype": "Float",
			"width": 130
		},
		{
			"fieldname": "raw_attended_classes",
			"label": _("Total Class Attended (hrs)"),
			"fieldtype": "Float",
			"width": 150
		},
		{
			"fieldname": "office_hours_attended",
			"label": _("Office Hours (hrs)"),
			"fieldtype": "Float",
			"width": 120
		},
		{
			"fieldname": "total_hours_attended_calc",
			"label": _("Total Attended (Class+Office)"),
			"fieldtype": "Float",
			"width": 160
		},
		{
			"fieldname": "is_condonation_applied",
			"label": _("Condonation"),
			"fieldtype": "Data",
			"width": 90
		},
		{
			"fieldname": "condonation_hours",
			"label": _("Condonation Hours"),
			"fieldtype": "Float",
			"width": 110
		},
		{
			"fieldname": "condonation_reason",
			"label": _("Condonation Reason"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "condonation_proof",
			"label": _("Condonation Proof"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "is_fa_mfa_applied",
			"label": _("FA/MFA"),
			"fieldtype": "Data",
			"width": 80
		},
		{
			"fieldname": "fa_mfa_reason",
			"label": _("FA/MFA Reason"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "fa_mfa_proof",
			"label": _("FA/MFA Proof"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "percentage_before_condonation",
			"label": _("% Before Condonation"),
			"fieldtype": "Percent",
			"width": 130
		},
		{
			"fieldname": "percentage_after_condonation",
			"label": _("% After Condonation"),
			"fieldtype": "Percent",
			"width": 130
		},
		{
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 100
		}
	]


def _attendance_match_clause(table_alias, class_alias):
	"""
	Return the SQL WHERE fragment that matches a Student Attendance row to a
	Class, handling two cases:

	  1. class_name is set and matches the class (RFID / Auto / well-formed Manual)
	  2. class_name is NULL but the course Link matches (older manual records)

	NOTE: a third tier matching solely on academic_year was removed — it caused every
	null-course record to match ALL classes in the same year, inflating attendance figures.

	{sa}  = Student Attendance table alias
	{cls} = Classes table alias (must expose: name, course)
	"""
	return """(
		{sa}.class_name = {cls}.name
		OR (
			({sa}.class_name IS NULL OR {sa}.class_name = '')
			AND {sa}.course = {cls}.course
		)
	)""".format(sa=table_alias, cls=class_alias)


def get_data(filters):
	conditions = ""
	values = {}

	if filters.get("programme_of_study"):
		conditions += " AND s.programme_of_study = %(programme_of_study)s"
		values["programme_of_study"] = filters["programme_of_study"]
	if filters.get("program"):
		conditions += " AND s.programme = %(program)s"
		values["program"] = filters["program"]
	if filters.get("section"):
		conditions += " AND att.section = %(section)s"
		values["section"] = filters["section"]
	if filters.get("class_name"):
		conditions += " AND att.class_name = %(class_name)s"
		values["class_name"] = filters["class_name"]
	if filters.get("course"):
		conditions += " AND att.course = %(course)s"
		values["course"] = filters["course"]
	if filters.get("source"):
		conditions += (
			" AND EXISTS ("
			"  SELECT 1 FROM `tabStudent Attendance` sa_f"
			"  JOIN `tabClasses` co_f ON co_f.name = att.class_name"
			"  WHERE sa_f.student = att.student"
			"  AND " + _attendance_match_clause("sa_f", "co_f") +
			"  AND sa_f.source = %(source)s"
			"  AND sa_f.status IN ('Present', 'Late', 'Excused')"
			"  AND sa_f.docstatus < 2"
			")"
		)
		values["source"] = filters["source"]

	# Build the match clause for the inline subqueries
	match = _attendance_match_clause("sa", "co")

	query = """
		SELECT
			att.student,
			att.student_name,
			s.programme AS program,
			att.section,
			COALESCE(co.course_name, att.course) AS course,
			att.total_classes,
			COALESCE(att.total_class_hours, 0) AS total_class_hours,

			(
				SELECT COALESCE(SUM(sa.hours_counted), 0)
				FROM `tabStudent Attendance` sa
				WHERE sa.student = att.student
				AND {match}
				AND sa.source != 'RFID'
				AND sa.status IN ('Present', 'Late', 'Excused')
				AND sa.session_type IN ('Lecture', 'Tutorial')
				AND sa.docstatus < 2
			) AS manual_attended_hours,

			(
				SELECT COALESCE(SUM(sa.hours_counted), 0)
				FROM `tabStudent Attendance` sa
				WHERE sa.student = att.student
				AND {match}
				AND sa.source = 'RFID'
				AND sa.status IN ('Present', 'Late', 'Excused')
				AND sa.session_type IN ('Lecture', 'Tutorial')
				AND sa.docstatus < 2
			) AS rfid_attended_hours,

			COALESCE(att.total_attended_class_hours, 0) AS raw_attended_classes,
			COALESCE(att.total_office_hours, 0) AS office_hours_attended,
			(COALESCE(att.total_attended_class_hours, 0) + COALESCE(att.total_office_hours, 0)) AS total_hours_attended_calc,

			CASE WHEN COALESCE(att.total_condonation_hours, 0) > 0 THEN 'Yes' ELSE 'No' END AS is_condonation_applied,
			COALESCE(att.total_condonation_hours, 0) AS condonation_hours,
			(SELECT GROUP_CONCAT(condonation_reason SEPARATOR ', ') FROM `tabAttendance Condonation Reference` WHERE parent = att.name) AS condonation_reason,
			(SELECT GROUP_CONCAT(proof_document SEPARATOR ', ') FROM `tabAttendance Condonation Reference` WHERE parent = att.name) AS condonation_proof,

			CASE WHEN COALESCE(att.total_fa_mfa_hours, 0) > 0 THEN 'Yes' ELSE 'No' END AS is_fa_mfa_applied,
			(SELECT GROUP_CONCAT(reason SEPARATOR ', ') FROM `tabAttendance FA MFA Reference` WHERE parent = att.name) AS fa_mfa_reason,
			(SELECT GROUP_CONCAT(proof_document SEPARATOR ', ') FROM `tabAttendance FA MFA Reference` WHERE parent = att.name) AS fa_mfa_proof,

			CASE
				WHEN COALESCE(att.total_class_hours, 0) > 0 THEN
					(COALESCE(att.total_attended_class_hours, 0) / att.total_class_hours) * 100
				ELSE 0
			END AS percentage_before_condonation,

			att.attendance_percentage AS percentage_after_condonation,

			CASE
				WHEN att.eligible_for_exam = 1 THEN 'Eligible'
				ELSE 'Not Eligible'
			END AS status

		FROM `tabAttendance Summary` att
		LEFT JOIN `tabStudent Master` s ON att.student = s.name
		LEFT JOIN `tabClasses` co ON att.class_name = co.name
		WHERE att.docstatus < 2
		{conditions}
		ORDER BY s.first_name, co.course_name
	""".format(conditions=conditions, match=match)

	if values:
		return frappe.db.sql(query, values, as_dict=True)
	return frappe.db.sql(query, as_dict=True)

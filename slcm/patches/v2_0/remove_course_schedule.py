"""Remove the Course Schedule doctype and rename the "Course Schedule" Based On value to "Class".

The new flow is Classes → Time Table → Attendance Session → Student Attendance.
A regular class period on the Time Table (and the sessions / attendance made
from it) had Based On = "Course Schedule", although it never linked a Course
Schedule record. That value is now "Class".

Runs after model sync: the Select options already read Class / Time Table /
Office Hours, so the stored rows are renamed here. The old `course_schedule`
columns stay in the tables (Frappe does not drop removed fields); they are
empty on every site where Course Schedule had no records.
"""

import frappe

OLD, NEW = "Course Schedule", "Class"

# (doctype, Select field) holding the Based On value
BASED_ON = [
	("Time Table", "based_on"),
	("Attendance Session", "based_on"),
	("Student Attendance", "based_on"),
	("Student Attendance", "attendance_based_on"),
]

LINKED = ("Time Table", "Attendance Session", "Student Attendance", "Student Attendance Tool")


def execute():
	rename_based_on()
	delete_course_schedule()
	frappe.db.commit()


def _has_column(doctype, column):
	return frappe.db.table_exists(doctype) and column in frappe.db.get_table_columns(doctype)


def rename_based_on():
	for doctype, field in BASED_ON:
		if _has_column(doctype, field):
			frappe.db.sql(f"UPDATE `tab{doctype}` SET `{field}` = %s WHERE `{field}` = %s", (NEW, OLD))

	# Student Attendance Tool is a Single: its values live in tabSingles
	frappe.db.sql("""UPDATE `tabSingles` SET value = %s
		WHERE doctype = 'Student Attendance Tool' AND field = 'based_on' AND value = %s""", (NEW, OLD))
	frappe.db.sql("""DELETE FROM `tabSingles`
		WHERE doctype = 'Student Attendance Tool' AND field = 'course_schedule'""")

	# Customised defaults of the Based On fields
	frappe.db.sql("""UPDATE `tabProperty Setter` SET value = %s
		WHERE doc_type IN %s AND field_name IN ('based_on', 'attendance_based_on')
		AND property = 'default' AND value = %s""", (NEW, LINKED, OLD))


def delete_course_schedule():
	# Desk links / shortcuts / sidebar items to the doctype (site-made ones
	# too; the app's own sidebars are re-synced from their files). Time Table
	# is already next to them.
	for child in ("Workspace Link", "Workspace Shortcut", "Workspace Sidebar Item", "Sidebar Item"):
		if _has_column(child, "link_to"):
			frappe.db.delete(child, {"link_to": OLD})

	frappe.db.delete("Custom Field", {"dt": OLD})
	frappe.db.delete("Property Setter", {"doc_type": OLD})
	frappe.db.delete("Custom Field", {"options": OLD})
	# Customisations of the removed course_schedule fields on other doctypes
	frappe.db.delete("Property Setter", {"doc_type": ["in", LINKED], "field_name": "course_schedule"})

	if frappe.db.table_exists(OLD) and frappe.db.count(OLD):
		# Never drop records: leave the doctype for someone to move them first.
		print(f"{OLD} still has records; not deleted. Move them to the Time Table first.")
		return

	if frappe.db.exists("DocType", OLD):
		frappe.delete_doc("DocType", OLD, force=1, ignore_missing=True)
	frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{OLD}`")

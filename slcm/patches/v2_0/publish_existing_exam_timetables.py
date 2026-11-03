import frappe


def execute():
	"""Exam Plan got a "Publish timetable to students" switch. Plans that already
	have exam dates were visible on the portal, so keep them published."""
	frappe.reload_doc("slcm", "doctype", "exam_reexam_schedule")
	frappe.reload_doc("slcm", "doctype", "exam_plan")
	for plan in frappe.db.sql_list(
		"""SELECT DISTINCT parent FROM `tabExam Course Schedule`
		   WHERE parenttype = 'Exam Plan' AND exam_date IS NOT NULL"""
	):
		frappe.db.set_value("Exam Plan", plan, "timetable_published", 1, update_modified=False)

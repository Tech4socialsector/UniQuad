import frappe
from frappe.utils import flt, nowdate

def generate_eligibility_list(course, academic_term, cutoff_date=None):
	"""
	Generate a list of students with their eligibility status for a course in
	a term (across all its Classes / sections).
	"""
	if not cutoff_date:
		cutoff_date = nowdate()

	# Ensure summaries are up to date
	update_summaries(course, academic_term)

	settings = frappe.get_single("Attendance Settings")
	min_req = flt(settings.minimum_attendance_percentage)
	condonable_range = [min_req - 10, min_req] # E.g., 65-75%

	data = []

	# Attendance Summary is per student per class; course + term spans sections
	summaries = frappe.get_all("Attendance Summary",
		filters={"course": course, "academic_term": academic_term},
		fields=["student", "student_name", "class_name", "attendance_percentage", "attended_classes", "total_classes"]
	)

	for s in summaries:
		status = "Eligible"
		action = "Release Hall Ticket"

		# Recalculate if needed or trust summary
		pct = s.attendance_percentage

		if pct < min_req:
			if pct >= condonable_range[0]:
				status = "Condonable Shortage"
				action = "Fine Applicable"
			else:
				status = "Detained"
				action = "Block Hall Ticket"

		data.append({
			"student": s.student,
			"student_name": s.student_name,
			"class_name": s.class_name,
			"attendance_percentage": pct,
			"status": status,
			"recommended_action": action
		})

	return data

def update_summaries(course, academic_term):
	"""Force update of all summaries for this course in this term"""
	from slcm.slcm.utils.attendance_calculator import calculate_student_attendance

	rows = frappe.db.sql("""
		SELECT DISTINCT student, class_name FROM `tabAttendance Summary`
		WHERE course=%s AND academic_term=%s AND IFNULL(class_name, '') != ''
	""", (course, academic_term), as_dict=True)

	for row in rows:
		calculate_student_attendance(row.student, row.class_name)

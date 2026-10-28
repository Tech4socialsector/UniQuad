import frappe


def get_context(context):
	pass


@frappe.whitelist()
def get_doctype_counts():
	"""Return record counts for all doctypes shown in the data entry map."""
	doctypes = [
		"Gender", "Student Category", "Skill", "SLCM Designation", "Condonation Reason",
		"SLCM Department", "Faculty", "Room",
		"Academic Year", "Academic Term", "Academic Holiday",
		"Course Master", "Course", "Programme", "Curriculum", "Batch",
		"Classes", "Class Configuration", "Time Table",
		"Grading Schema", "Evaluation Schema", "Exam Assessment Type",
		"Exam Component", "CGPA Percentage Scale",
		"Course Schema Assignment", "Access Result Settings", "Publish Result Setting",
		"Student Master", "Student Parent",
		"Program Enrollment", "Student Enrollment", "Student Enrollment Course",
		"Attendance Session", "Attendance Session Student", "Student Attendance",
		"FA MFA Application", "Student Attendance Condonation",
		"Exam Plan", "Student Course Marks", "Student Marks Entry",
		"Student Result Publish", "Re Exam Registration",
		"Improvement Exam Registration", "Grade Appeal",
		"Exam Barcode", "Student Transcript",
		"Fee Structure", "Fee Invoice", "Fee Payment",
		"Admission Cycle", "Applicant", "Admission Application",
		"Offer Letter", "Merit List",
		"ID Card Template", "ID Card Generation",
		"Venue Booking",
		"Promotion Policy", "Student Promotion",
		"Hostel", "Hostel Block", "Hostel Floor", "Hostel Room",
		"Hostel Bed", "Hostel Allocation",
		"Placement Opportunity", "Placement Application", "Placement Offer",
	]

	counts = {}
	for dt in doctypes:
		try:
			if frappe.db.exists("DocType", dt):
				counts[dt] = frappe.db.count(dt)
			else:
				counts[dt] = 0
		except Exception:
			counts[dt] = 0

	return counts

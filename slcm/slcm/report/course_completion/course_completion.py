import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
	columns = [
		{
			"fieldname": "class_name",
			"label": _("Class"),
			"fieldtype": "Link",
			"options": "Classes",
			"width": 150
		},
		{
			"fieldname": "course_name",
			"label": _("Course Name"),
			"fieldtype": "Data",
			"width": 200
		},
		{
			"fieldname": "instructor",
			"label": _("Instructor"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "course_type",
			"label": _("Type"),
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "planned_hours",
			"label": _("Planned Hours"),
			"fieldtype": "Float",
			"width": 120
		},
		{
			"fieldname": "conducted_hours",
			"label": _("Conducted Hours"),
			"fieldtype": "Float",
			"width": 120
		},
		{
			"fieldname": "completion_percentage",
			"label": _("% Completion"),
			"fieldtype": "Percent",
			"width": 120
		},
		{
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 120
		}
	]
	
	data = get_course_completion_data(filters)
	
	return columns, data

def get_course_completion_data(filters):
	# 1. Get Settings for Planned Hours
	settings = frappe.get_single("Attendance Settings")
	core_hours = flt(settings.core_course_hours)
	elective_hours = flt(settings.elective_course_hours)
	
	filters = filters or {}
	conditions = "1=1"
	params = {}
	if filters.get("term"):
		conditions += " AND cl.academic_term = %(term)s"
		params["term"] = filters.get("term")
	if filters.get("academic_year"):
		conditions += " AND cl.academic_year = %(academic_year)s"
		params["academic_year"] = filters.get("academic_year")

	# 2. Fetch Classes (the taught groups) with Course details
	classes = frappe.db.sql(f"""
		SELECT
			cl.name as class_name,
			cl.course_name as course_name,
			CONCAT_WS(' ', f.first_name, f.last_name) as instructor,
			c.course_type
		FROM `tabClasses` cl
		LEFT JOIN `tabCourse` c ON c.name = cl.course
		LEFT JOIN `tabFaculty` f ON f.name = cl.faculty
		WHERE {conditions}
	""", params, as_dict=True)

	result = []

	for off in classes:
		# Determine Planned Hours
		planned = core_hours # Default
		if off.course_type == "Elective":
			planned = elective_hours
			
		# 3. Calculate Conducted Hours
		# specific method to calculate hours from sessions
		# Using SQL for aggregation
		stats = frappe.db.sql("""
			SELECT SUM(duration_hours) as conducted
			FROM `tabAttendance Session`
			WHERE class_name = %s
			AND session_status = 'Completed'
		""", (off.class_name,), as_dict=True)
		
		conducted = flt(stats[0].conducted) if stats and stats[0].conducted else 0.0
		
		# 4. Calculate Percentage
		pct = 0.0
		if planned > 0:
			pct = (conducted / planned) * 100
			
		status = "On Track"
		if pct >= 100:
			status = "Completed"
		elif pct < 50: # Arbitrary warning threshold, maybe improve later
			status = "Lagging"
			
		result.append({
			"class_name": off.class_name,
			"course_name": off.course_name,
			"instructor": off.instructor,
			"course_type": off.course_type,
			"planned_hours": planned,
			"conducted_hours": conducted,
			"completion_percentage": pct,
			"status": status
		})
		
	return result

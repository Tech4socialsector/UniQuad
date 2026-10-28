import json
import frappe
from frappe.model.document import Document
from frappe.utils import cint


class CourseManagement(Document):
	def onload(self):
		self.set_default_course_types()
		self.set_default_enrollment_types()

	def set_default_course_types(self):
		defaults = [
			{"course_type": "Core", "is_active": 1, "display_name": "Core"},
			{"course_type": "Open Elective", "is_active": 1, "display_name": "Open Elective"},
			{"course_type": "Program Elective", "is_active": 1, "display_name": "Program Elective"},
			{"course_type": "Seminar", "is_active": 1, "display_name": "Seminar"},
		]
		
		# Get course_types safely (might not exist for Single DocType on first load)
		course_types = getattr(self, "course_types", None) or []
		
		# If empty, populate all
		if not course_types:
			for d in defaults:
				self.append("course_types", d)
		else:
			# Ensure missing ones are added
			existing = [d.course_type for d in course_types]
			for d in defaults:
				if d["course_type"] not in existing:
					self.append("course_types", d)

	def set_default_enrollment_types(self):
		defaults = [
			{"enrollment_type": "Full", "is_active": 1, "display_name": "Full"},
			{"enrollment_type": "Zero Credit", "is_active": 0, "display_name": "Zero Credit"}, # Default inactive per screenshot logic if needed, but user said "Load these". Check screenshot users defaults.
			# Screenshot shows: Core, Prog Elective... in Enrollment Types (OLD BAD STATE). 
			# User REQUIREMENT: Enrollment Type: Full, Zero Credit, Audit.
			# Screenshot 1 shows Enrollment Types with: Core, Prog El, Open El, Zero Credit, Audit.
			# This implies 'Zero Credit' and 'Audit' were ALREADY there but mixed with Course Types.
			# And 'Full' is missing.
			
			{"enrollment_type": "Audit", "is_active": 0, "display_name": "Audit"},
		]
		
		# User wanted: Enrollment_type: Full, Zero Credit, Audit.
		# I will ensure these exist.
		
		# Clean up WRONG types from Enrollment Types if they exist?
		# The user screenshot shows "Core", "Programme Elective", "Open Elective" INSIDE Enrollment Types.
		# These are WRONG. They belong in Course Types.
		# I should probably remove them from Enrollment Types to be clean, OR just leave them if user didn't ask to remove.
		# "so based on that the screenshot details should load" implies I should match the requirement.
		# Requirement: "Enrollment_type: Data field for the type name (Full, Zero credit, Audit) this need to show in default"
		
		# I'll simply ensure Full, Zero Credit, Audit are present.
		
		desired_types = ["Full", "Zero Credit", "Audit"]
	
		# Get enrollment_types safely (might not exist for Single DocType on first load)
		enrollment_types = getattr(self, "enrollment_types", None) or []
		
		if not enrollment_types:
			# Completley empty, easy.
			self.append("enrollment_types", {"enrollment_type": "Full", "is_active": 1, "display_name": "Full"})
			self.append("enrollment_types", {"enrollment_type": "Zero Credit", "is_active": 1, "display_name": "Zero Credit"})
			self.append("enrollment_types", {"enrollment_type": "Audit", "is_active": 1, "display_name": "Audit"})
		else:
			# Check existing
			existing_map = {d.enrollment_type: d for d in enrollment_types}
			
			if "Full" not in existing_map:
				self.append("enrollment_types", {"enrollment_type": "Full", "is_active": 1, "display_name": "Full"})
			
			if "Zero Credit" not in existing_map:
				self.append("enrollment_types", {"enrollment_type": "Zero Credit", "is_active": 1, "display_name": "Zero Credit"})
			
			if "Audit" not in existing_map:
				self.append("enrollment_types", {"enrollment_type": "Audit", "is_active": 1, "display_name": "Audit"})



# ---------------------------------------------------------------------
# GET CURRICULUM
# ---------------------------------------------------------------------
@frappe.whitelist()
def get_curriculum(program, academic_year, batch=None, section=None):
	if not program or not academic_year:
		return None

	# Prefer batch-specific curriculum
	filters = {
		"program": program,
		"academic_year": academic_year,
	}

	if batch:
		filters["batch"] = batch

	name = frappe.db.get_value("Course List", filters, "name")

	# Fallback to generic curriculum
	if not name and batch:
		name = frappe.db.get_value(
			"Course List",
			{"program": program, "academic_year": academic_year, "batch": ["is", "not set"]},
			"name",
		)

	if name:
		doc = frappe.get_doc("Course List", name)
		return doc.as_dict()

	# Return empty structure
	return {
		"program": program,
		"academic_year": academic_year,
		"batch": batch,
		"academic_system": "Semester",
		"curriculum_courses": [],
	}


# ---------------------------------------------------------------------
# SAVE CURRICULUM (MASTER FIX)
# ---------------------------------------------------------------------
@frappe.whitelist()
def save_curriculum(
	program,
	academic_year,
	courses,
	academic_system="Semester",
	batch=None,
	section=None,
):

	if isinstance(courses, str):
		courses = json.loads(courses)

	# ----------------------------------
	# Determine EXISTING document NAME
	# ----------------------------------
	filters = {
		"program": program,
		"academic_year": academic_year,
	}

	if batch:
		filters["batch"] = batch

	name = frappe.db.get_value("Course List", filters, "name")
	
	# If not found with batch, try without batch (fallback for existing records without batch)
	if not name and batch:
		name = frappe.db.get_value("Course List", {
			"program": program,
			"academic_year": academic_year,
		}, "name")

	# ----------------------------------
	# CASE 1: UPDATE EXISTING
	# ----------------------------------
	if name:
		doc = frappe.get_doc("Course List", name)

		# Update fields
		doc.academic_system = academic_system
		doc.batch = batch
		doc.section = section

		# Replace child table
		doc.set("curriculum_courses", [])

		for course in courses:
			doc.append("curriculum_courses", {
				"semester": course.get("semester"),
				"enrollment_type": course.get("enrollment_type"),
				"course_type": course.get("course_type"),
				"course_group_type": course.get("course_group_type", "Course"),
				"course": course.get("course"),
				"cluster_name": course.get("cluster_name"),
				"min_courses": course.get("min_courses"),
				"max_courses": course.get("max_courses"),
				"credits": course.get("credits"),
			})

		# Save the document properly
		doc.save(ignore_permissions=True)
		generate_offerings_from_curriculum(doc)
		frappe.db.commit()

		return {"status": "updated", "name": doc.name}

	# ----------------------------------
	# CASE 2: CREATE NEW (ONCE)
	# ----------------------------------
	doc = frappe.new_doc("Course List")
	doc.program = program
	doc.academic_year = academic_year
	doc.academic_system = academic_system
	doc.batch = batch
	doc.section = section

	for course in courses:
		doc.append("curriculum_courses", {
			"semester": course.get("semester"),
			"enrollment_type": course.get("enrollment_type"),
			"course_type": course.get("course_type"),
			"course_group_type": course.get("course_group_type", "Course"),
			"course": course.get("course"),
			"cluster_name": course.get("cluster_name"),
			"min_courses": course.get("min_courses"),
			"max_courses": course.get("max_courses"),
			"credits": course.get("credits"),
		})

	# 🔥 INSERT ONLY ONCE
	doc.insert(ignore_permissions=True)
	generate_offerings_from_curriculum(doc)
	frappe.db.commit()

	return {"status": "created", "name": doc.name}


# ---------------------------------------------------------------------
# GENERATE COURSE OFFERINGS FROM CURRICULUM
# ---------------------------------------------------------------------
def generate_offerings_from_curriculum(course_list_doc):
	"""Create/update one Course Offering per (course, batch, semester) in the
	saved curriculum, so Course Management's plan is what actually drives
	enrollment instead of requiring offerings to be entered by hand.

	Only runs for batch-specific curricula (a generic, batch-less curriculum
	has no cohort to scope an offering to, so there is nothing to generate).
	Cluster rows are skipped since they don't map to a single Course.
	"""
	if not course_list_doc.batch:
		return

	# Offerings are keyed by programme + academic year + year no + term (no
	# cohort); the batch only tells us which year of study this plan is for.
	year_no = _get_batch_year_no(
		course_list_doc.batch, course_list_doc.program, course_list_doc.academic_year
	)
	if not year_no:
		return

	for row in course_list_doc.curriculum_courses:
		if row.course_group_type != "Course" or not row.course or not row.semester:
			continue

		academic_term = frappe.db.get_value(
			"Academic Term",
			{"academic_year": course_list_doc.academic_year, "term_name": row.semester},
			"name",
		)
		if not academic_term:
			continue

		filters = {
			"course_title": row.course,
			"program": course_list_doc.program,
			"academic_year": course_list_doc.academic_year,
			"year_no": year_no,
			"term_name": academic_term,
		}
		existing = frappe.db.get_value("Course Offering", filters, "name")

		message_log_len = len(frappe.message_log)
		try:
			if existing:
				offering = frappe.get_doc("Course Offering", existing)
			else:
				offering = frappe.new_doc("Course Offering")
				offering.course_title = row.course
				offering.academic_year = course_list_doc.academic_year
				offering.year_no = year_no
				offering.term_name = academic_term

			offering.program = course_list_doc.program
			if not offering.status:
				offering.status = "Active"

			if existing:
				offering.save(ignore_permissions=True)
			else:
				offering.insert(ignore_permissions=True)
		except Exception:
			# Drop any message queued by the failed attempt (e.g. a validation
			# error) so it doesn't leak into the response of what is otherwise
			# a successful Course Management save.
			del frappe.message_log[message_log_len:]
			frappe.log_error(
				title="Course Offering generation failed",
				message=frappe.get_traceback(),
			)



# ---------------------------------------------------------------------
# COURSE DIALOG COLUMNS
# ---------------------------------------------------------------------
@frappe.whitelist()
def get_course_dialog_columns():
	meta = frappe.get_meta("Course")
	columns = [
		df.fieldname
		for df in meta.fields
		if df.in_list_view
		and not df.hidden
		and df.fieldtype not in ["Section Break", "Column Break", "HTML", "Table", "Button"]
	]

	for field in ["course_name", "course_code", "department_name"]:
		if field not in columns and any(f.fieldname == field for f in meta.fields):
			columns.insert(0, field)

	return columns or ["course_name", "department_name"]


# ---------------------------------------------------------------------
# SECTION DETAILS
# ---------------------------------------------------------------------
@frappe.whitelist()
def get_details_from_section(section):
	# Sections are global (not tied to a batch / programme), so there is
	# nothing to derive from one.
	return {}


def _get_batch_year_no(batch, program, academic_year):
	"""Year of study of `batch` in `academic_year`: taken from the batch's
	Student Enrollments, else counted from the batch's starting year."""
	year_no = frappe.db.sql(
		"""
		SELECT l.year_no
		FROM `tabStudent Academic Log` l
		INNER JOIN `tabStudent Enrollment` se
			ON se.name = l.parent AND l.parenttype = 'Student Enrollment'
		WHERE se.batch = %(batch)s AND se.program = %(program)s
			AND l.academic_year = %(academic_year)s
			AND l.status NOT IN ('Redo', 'Dropped')
			AND IFNULL(l.year_no, 0) > 0
		LIMIT 1
		""",
		{"batch": batch, "program": program, "academic_year": academic_year},
	)
	if year_no:
		return cint(year_no[0][0])

	batch_start = frappe.db.get_value(
		"Academic Year",
		frappe.db.get_value("Batch", batch, "academic_year"),
		"year_start_date",
	)
	target_start = frappe.db.get_value("Academic Year", academic_year, "year_start_date")
	if not batch_start or not target_start or target_start < batch_start:
		return 0

	return frappe.db.count(
		"Academic Year",
		{"year_start_date": ["between", [batch_start, target_start]]},
	)


# ---------------------------------------------------------------------
# COURSE SEARCH (CUSTOM DIALOG)
# ---------------------------------------------------------------------
@frappe.whitelist()
def get_courses_for_curriculum(department, txt=None, start=0, page_length=20):
	start = int(start or 0)
	page_length = int(page_length or 20)
	txt = f"%{txt}%" if txt else "%"

	return frappe.db.sql(
		"""
		SELECT
			c.name,
			c.course_name,
			c.course_code,
			c.credit_value,
			COALESCE(d.department_name, d.name) AS department_name
		FROM `tabCourse` c
		LEFT JOIN `tabDepartment` d ON d.name = c.department
		WHERE
			c.department = %s
			AND c.status = 'Active'
			AND c.course_name LIKE %s
		ORDER BY c.course_name
		LIMIT %s, %s
		""",
		(department, txt, start, page_length),
		as_dict=True,
	)

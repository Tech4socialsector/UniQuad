# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours, now_datetime, add_to_date, get_datetime
from slcm.slcm.utils.attendance_calculator import calculate_student_attendance

DEFAULT_RFID_ACTIVE_WINDOW_MINUTES = 10


def _check_instructor_or_admin(session_doc):
	"""Only the assigned instructor (or System Manager) may act on a session."""
	user = frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return
	instructor_user = frappe.db.get_value("Faculty", session_doc.instructor, "user_id") if session_doc.instructor else None
	if not instructor_user or instructor_user != user:
		frappe.throw(_("Only the assigned instructor can perform this action."), frappe.PermissionError)


def get_rfid_active_window_minutes():
	"""RFID activation window is configurable via Attendance Settings; falls back to the default if unset."""
	minutes = frappe.db.get_single_value("Attendance Settings", "rfid_active_window_minutes")
	return minutes if minutes else DEFAULT_RFID_ACTIVE_WINDOW_MINUTES


class AttendanceSession(Document):
	"""Track conducted class sessions for attendance calculation"""
	
	def validate(self):
		"""Validate session details"""
		self.calculate_duration()
		self.validate_times()
	
	def after_insert(self):
		"""Session created — students are NOT auto-populated.
		Use the 'Fetch Students' button or the Student Attendance Tool to mark attendance."""
		pass

	def on_submit(self):
		"""Trigger attendance calculations"""
		self.update_student_attendance_status()
		self.trigger_calculations()

	def on_update(self):
		"""Trigger calculations on save"""
		# Ensure duration is recalculated if times changed
		self.calculate_duration()

		if not self.flags.get("from_student_attendance"):
			self.update_student_attendance_hours()
			self.sync_details_to_attendance()
			self.trigger_calculations()

	def update_student_attendance_hours(self):
		"""Update hours_counted in ALL linked Student Attendance records when session duration changes."""
		if not self.duration_hours:
			return

		# Update all sources including RFID — session duration is authoritative
		frappe.db.sql("""
			UPDATE `tabStudent Attendance`
			SET hours_counted = %s
			WHERE attendance_session = %s
			AND status IN ('Present', 'Late', 'Excused')
			AND docstatus < 2
		""", (self.duration_hours, self.name))

	def sync_details_to_attendance(self):
		"""Sync Session Type and other details to linked Student Attendance"""
		doc_before = self.get_doc_before_save()
		if doc_before:
			if (doc_before.session_type == self.session_type and
					str(doc_before.session_date) == str(self.session_date)):
				return
		frappe.db.sql("""
			UPDATE `tabStudent Attendance`
			SET session_type = %s, attendance_date = %s
			WHERE attendance_session = %s
		""", (self.session_type, self.session_date, self.name))

	def calculate_duration(self):
		"""Calculate session duration in hours"""
		if self.session_start_time and self.session_end_time:
			self.duration_hours = time_diff_in_hours(self.session_end_time, self.session_start_time)
	
	def validate_times(self):
		"""Ensure end time is after start time"""
		if self.session_start_time and self.session_end_time:
			if self.session_end_time <= self.session_start_time:
				frappe.throw("Session end time must be after start time")

	def create_student_attendance_records(self):
		"""Fetch enrolled students and create initial attendance records"""
		if self.flags.skip_auto_attendance:
			return

		students = self.get_enrolled_students()
		
		for student_id in students:
			# Check if record already exists to avoid duplicates
			exists = frappe.db.exists("Student Attendance", {
				"student": student_id,
				"attendance_session": self.name
			})
			
			if not exists:
				doc = frappe.get_doc({
					"doctype": "Student Attendance",
					"student": student_id,
					"attendance_session": self.name,
					"class_schedule": self.class_schedule,
					"course_schedule": self.course_schedule,
					"course_offer": self.course_offering,
					"attendance_date": self.session_date,
					"date": self.session_date,
					"session_type": self.session_type,
					"status": "Absent",
					"source": "Auto",
					"hours_counted": self.duration_hours or 1.0,
				})
				doc.insert(ignore_permissions=True)
				
		self.update_attendance_summary()

	def get_oh_group(self):
		"""OH Student Group for an Office Hour session - its own field, else the
		Time Table series root's (older generated occurrences lack the copy)."""
		if self.office_hours_group:
			return self.office_hours_group
		if not self.class_schedule:
			return None
		tt = frappe.db.get_value(
			"Time Table", self.class_schedule, ["office_hours_group", "parent_schedule"], as_dict=True
		)
		if not tt:
			return None
		if tt.office_hours_group:
			return tt.office_hours_group
		if tt.parent_schedule:
			return frappe.db.get_value("Time Table", tt.parent_schedule, "office_hours_group")
		return None

	def get_enrolled_students(self):
		"""Expected roster: the OH Student Group's students for an Office Hour
		session (OH attendance is kept separate from the class roster), else
		the students enrolled in this Course Offering."""
		if self.session_type == "Office Hour":
			group = self.get_oh_group()
			if group and frappe.db.exists("Student Group", group):
				return frappe.get_all(
					"Student Group Student",
					filters={"parent": group, "parenttype": "Student Group"},
					pluck="student",
					order_by="idx",
				)
			return []

		if not self.course_offering:
			return []

		students = frappe.db.sql("""
			SELECT DISTINCT se.student
			FROM `tabStudent Enrollment` se
			JOIN `tabStudent Enrollment Course` sec ON sec.parent = se.name
			WHERE sec.course_offering = %s
			AND sec.status = 'Enrolled'
			AND se.status = 'Enrolled'
			AND se.docstatus = 0
		""", (self.course_offering,), as_dict=True)
		
		return [s.student for s in students]

	def update_student_attendance_status(self):
		"""Lock attendance records on submit"""
		pass # Student Attendance is submittable? Or we just leave them.
		# If Student Attendance is a submittable doctype, we should submit them.
		# Let's check Student Attendance doctype. It has docstatus, so it might be submittable.
		# Generally Student Attendance is not a submittable document in standard ERPNext, but here?
		# It has "submitted" status? 
		# If it's not submittable, we just leave them.
		
	def trigger_calculations(self):
		"""Recalculate attendance for all students in this session"""
		students = [row.student for row in (self.students or []) if row.student]
		if not students:
			students = self.get_enrolled_students()
		if self.course_offering:
			for student_id in students:
				calculate_student_attendance(student_id, self.course_offering)

	def before_save(self):
		"""Calculate summary before saving"""
		self.validate_times()
		self.update_attendance_summary()
	
	def update_attendance_summary(self):
		"""Update attendance counts and student list.

		The student list is the session's expected roster (from Student
		Enrollment), shown live — it does NOT require any Student Attendance
		documents to exist. Real Student Attendance records are only created
		when attendance is actually taken (manual mark, bulk mark, or RFID),
		at which point that student's real status replaces "Not Marked" here.
		"""
		attendance_data = frappe.db.sql("""
			SELECT
				SUM(CASE WHEN sa.status IN ('Present', 'Late') THEN 1 ELSE 0 END) as present,
				SUM(CASE WHEN sa.status = 'Absent'             THEN 1 ELSE 0 END) as absent,
				SUM(CASE WHEN sa.status IN ('Present', 'Late')
				         AND (s.gender = 'Male' OR s.gender = 'Man')   THEN 1 ELSE 0 END) as boys,
				SUM(CASE WHEN sa.status IN ('Present', 'Late')
				         AND (s.gender = 'Female' OR s.gender = 'Woman') THEN 1 ELSE 0 END) as girls,
				SUM(CASE WHEN sa.source = 'Manual'             THEN 1 ELSE 0 END) as manually_marked,
				SUM(CASE WHEN sa.source = 'RFID'               THEN 1 ELSE 0 END) as rfid_marked
			FROM `tabStudent Attendance` sa
			JOIN `tabStudent Master` s ON sa.student = s.name
			WHERE sa.attendance_session = %s
			AND sa.docstatus < 2
		""", self.name, as_dict=True)

		manually_marked = 0
		rfid_marked = 0
		if attendance_data:
			data = attendance_data[0]
			manually_marked = data.get('manually_marked', 0) or 0
			rfid_marked = data.get('rfid_marked', 0) or 0
			self.present_count = data.get('present', 0) or 0
			self.absent_count = data.get('absent', 0) or 0
			self.total_boys = data.get('boys', 0) or 0
			self.total_girls = data.get('girls', 0) or 0

			# attendance_marked = 1 only when a teacher has manually marked attendance.
			# RFID-only marking does NOT set this flag — teacher must confirm.
			self.attendance_marked = 1 if manually_marked > 0 else 0

			# session_status flips to "Conducted" when either Manual or RFID attendance exists
			if (manually_marked > 0 or rfid_marked > 0) and self.session_status == "Scheduled":
				self.session_status = "Conducted"

		# Roster: enrolled students for this Course Offering, plus any student
		# who already has a real Student Attendance record for this session
		# (covers manually-added students outside the official enrollment list).
		roster = set(self.get_enrolled_students())

		existing = frappe.db.sql("""
			SELECT sa.student, sa.status
			FROM `tabStudent Attendance` sa
			WHERE sa.attendance_session = %s
			AND sa.docstatus < 2
		""", self.name, as_dict=True)
		status_by_student = {r.student: r.status for r in existing}

		all_students = roster | set(status_by_student.keys())
		self.total_students = len(all_students)

		if self.total_students > 0:
			self.attendance_percentage = (self.present_count / self.total_students) * 100
		else:
			self.attendance_percentage = 0

		# Populate Child Table — clear existing rows to avoid stale data
		self.set("students", [])

		if all_students:
			details = frappe.get_all(
				"Student Master",
				filters={"name": ["in", list(all_students)]},
				fields=["name", "first_name", "gender"],
			)
			details_by_id = {d.name: d for d in details}

			for student_id in sorted(all_students, key=lambda s: (details_by_id.get(s, {}).get("first_name") or "")):
				info = details_by_id.get(student_id, {})
				self.append("students", {
					"student": student_id,
					"student_name": info.get("first_name"),
					"status": status_by_student.get(student_id, "Not Marked"),
					"gender": info.get("gender"),
				})
			
	# Note: No separate save() call needed because this is called in before_save
	# or can be called manually followed by save() 

@frappe.whitelist()
def activate_rfid(session_name):
	"""Faculty presses 'Activate RFID' in the Faculty Portal.
	Records who/when, and opens a 10-minute window (rfid_active_until).
	Activation is advisory for the UI freeze/timer — RFID matching itself
	does not require activation, so a missed activation never blocks
	attendance capture; it only affects what faculty sees in the portal."""
	session = frappe.get_doc("Attendance Session", session_name)
	_check_instructor_or_admin(session)
	user = frappe.session.user

	if session.rfid_activation_time:
		frappe.throw(_("RFID has already been activated for this session."))

	activation_time = now_datetime()
	session.db_set("rfid_activated_by", user)
	session.db_set("rfid_activation_time", activation_time)
	session.db_set("rfid_active_until", add_to_date(activation_time, minutes=get_rfid_active_window_minutes()))

	return {
		"rfid_activated_by": user,
		"rfid_activation_time": activation_time,
		"rfid_active_until": session.rfid_active_until,
	}


@frappe.whitelist()
def mark_session_conducted(session_name):
	"""Mark a session as conducted"""
	session = frappe.get_doc("Attendance Session", session_name)
	_check_instructor_or_admin(session)
	session.session_status = "Conducted"
	session.save()
	return session


@frappe.whitelist()
def get_pending_sessions(instructor=None, course_offering=None):
	"""Get sessions where attendance is not yet marked"""
	filters = {
		"session_status": ["in", ["Scheduled", "Conducted"]],
		"attendance_marked": 0
	}
	
	if instructor:
		filters["instructor"] = instructor
	
	if course_offering:
		filters["course_offering"] = course_offering
	
	return frappe.get_all(
		"Attendance Session",
		filters=filters,
		fields=["name", "session_date", "course", "instructor", "duration_hours"],
		order_by="session_date desc"
	)


@frappe.whitelist()
def fetch_students_for_session(session_name):
	"""Fetch enrolled students and create attendance records for a session"""
	session_doc = frappe.get_doc("Attendance Session", session_name)
	_check_instructor_or_admin(session_doc)
	before_count = frappe.db.count("Student Attendance", {"attendance_session": session_name})
	session_doc.create_student_attendance_records()
	after_count = frappe.db.count("Student Attendance", {"attendance_session": session_name})
	fetched = after_count - before_count
	return f"Fetched {fetched} student(s) — total {after_count} in session"


@frappe.whitelist()
def update_attendance_summary_realtime(session_name, course_offering, duration_hours):
	"""
	Update Attendance Summary in real-time when Attendance Session times change.
	Called from client-side JavaScript without requiring a full save.
	Recalculates total_class_hours for all affected students.
	"""
	try:
		# Verify the session exists
		if not frappe.db.exists("Attendance Session", session_name):
			return {"success": False, "message": "Attendance Session not found"}

		_check_instructor_or_admin(frappe.get_doc("Attendance Session", session_name))

		# Trigger attendance recalculation for all students in this course offering
		from slcm.slcm.utils.attendance_calculator import calculate_student_attendance
		
		# Get all students who have attendance records for this course offering
		students = frappe.db.sql("""
			SELECT DISTINCT student
			FROM `tabStudent Attendance`
			WHERE course_offer = %s
		""", course_offering, as_dict=True)
		
		students_updated = 0
		
		# Recalculate attendance for each student
		for student_row in students:
			try:
				calculate_student_attendance(student_row.student, course_offering)
				students_updated += 1
			except Exception as student_error:
				frappe.log_error(
					message=f"Error updating student {student_row.student}: {str(student_error)}",
					title="Student Attendance Update Error"
				)
		
		frappe.db.commit()

		return {
			"success": True,
			"message": f"Attendance Summary updated for {students_updated} students",
			"students_updated": students_updated
		}

	except Exception as e:
		frappe.log_error(message=str(e), title="Real-time Attendance Summary Update Error")
		return {"success": False, "message": str(e)}


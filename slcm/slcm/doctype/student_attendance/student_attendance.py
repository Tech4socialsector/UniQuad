# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class StudentAttendance(Document):
	def validate(self):
		self.validate_attendance_lock()
		self.validate_duplicate_attendance()
		self.fetch_course_details()
		self.track_changes()
	
	def validate_attendance_lock(self):
		"""Refuse changes once the session's attendance is locked (Attendance
		Settings lock hours after it ended) unless AAD has reopened it. The
		RFID pipeline sets flags.ignore_attendance_lock."""
		if self.flags.ignore_attendance_lock:
			return

		from slcm.slcm.utils.attendance_lock import assert_date_editable, assert_session_editable

		if self.attendance_session:
			assert_session_editable(self.attendance_session)
		else:
			assert_date_editable(self.attendance_date)

	
	def validate_duplicate_attendance(self):
		"""Prevent duplicate attendance for same student, date, and Session/Schedule"""
		filters = {"student": self.student, "docstatus": ["<", 2]}
		
		# If linked to a Session, uniqueness is strictly on Session
		if self.attendance_session:
			filters["attendance_session"] = self.attendance_session
		else:
			# Legacy/Manual checks
			filters["attendance_date"] = self.attendance_date
			if self.course_schedule:
				filters["course_schedule"] = self.course_schedule
			elif self.course_offer:
				filters["course_offer"] = self.course_offer
			
			if self.period:
				filters["period"] = self.period
			
			# Allow same day attendance if Session Type is different (e.g. Lecture vs Office Hour)
			if self.session_type:
				filters["session_type"] = self.session_type

		existing = frappe.db.exists("Student Attendance", filters)

		if existing and existing != self.name:
			if self.attendance_session:
				frappe.throw(_("Attendance already marked for this session."))
			else:
				frappe.throw(_("Attendance already exists for this student on {0}").format(self.attendance_date))

	def fetch_course_details(self):
		"""Fetch course details based on based_on field."""
		if self.based_on == "Course Schedule" and self.course_schedule:
			schedule = frappe.get_doc("Course Schedule", self.course_schedule)
			if not self.course:
				self.course = schedule.course
			if not self.program:
				self.program = schedule.program
			if not self.instructor and schedule.instructor:
				faculty_name = frappe.db.get_value(
					"Faculty", schedule.instructor, ["first_name", "last_name"], as_dict=True
				)
				self.instructor = (
					" ".join(filter(None, [faculty_name.first_name, faculty_name.last_name]))
					if faculty_name else schedule.instructor
				) or schedule.instructor
			if not self.room:
				self.room = schedule.room

		# Pull course_offer from the linked Attendance Session when not set directly.
		# This fixes Manual records created without selecting a Course Offering.
		if not self.course_offer and self.attendance_session:
			session_co = frappe.db.get_value(
				"Attendance Session", self.attendance_session, "course_offering"
			)
			if session_co:
				self.course_offer = session_co

		# Fetch course from course offering
		if self.course_offer and not self.course:
			offering = frappe.get_doc("Course Offering", self.course_offer)
			self.course = offering.course_title

		# Sync attendance_date → date (both fields are required)
		if self.attendance_date and not self.date:
			self.date = self.attendance_date
	
	def track_changes(self):
		"""Track changes for audit log"""
		if self.is_new():
			return
		
		# Get old doc
		old_doc = self.get_doc_before_save()
		if not old_doc:
			return
		
		# Track status changes
		if old_doc.status != self.status:
			self._log_change("status", old_doc.status, self.status)
	
	def _log_change(self, field, old_value, new_value):
		"""Store change information for logging after save"""
		if not hasattr(self, "_changes_to_log"):
			self._changes_to_log = []
		
		self._changes_to_log.append({
			"field": field,
			"old_value": old_value,
			"new_value": new_value
		})
	
	def on_update(self):
		"""Create audit log entries for changes"""
		if hasattr(self, "_changes_to_log"):
			for change in self._changes_to_log:
				self.create_edit_log(
					change["field"],
					change["old_value"],
					change["new_value"]
				)
		self.trigger_recalculation()
		self.trigger_session_update()
	
	def create_edit_log(self, field_changed, old_value, new_value):
		"""Create an attendance edit log entry"""
		try:
			from slcm.slcm.doctype.attendance_edit_log.attendance_edit_log import log_attendance_edit
			
			edit_reason = self.get("edit_reason") or "Attendance updated"
			
			log_attendance_edit(
				attendance_record=self.name,
				field_changed=field_changed,
				old_value=old_value,
				new_value=new_value,
				edit_reason=edit_reason
			)
		except Exception as e:
			frappe.log_error(message=f"Error creating edit log: {str(e)}", title="Edit Log Creation Error")
	
	def on_trash(self):
		"""Trigger updates on deletion"""
		self.trigger_recalculation()
		self.trigger_session_update()
	
	def after_insert(self):
		"""Trigger attendance recalculation after insert"""
		self.trigger_recalculation()
		self.trigger_session_update()
	
	def on_update_after_submit(self):
		"""Trigger attendance recalculation after update"""
		self.trigger_recalculation()
		self.trigger_session_update()
	
	def on_cancel(self):
		"""Trigger attendance recalculation after cancel"""
		self.trigger_recalculation()
		self.trigger_session_update()
	
	def resolve_course_offerings(self):
		"""
		Return a list of course_offering IDs to recalculate for this record.

		Priority order:
		  1. course_offer directly on the record (RFID / Auto / well-formed Manual)
		  2. course_offering from the linked Attendance Session

		NOTE: a previous fallback that matched all summaries by academic_year alone was
		removed — it caused every ambiguous record to trigger recalculation for every
		course in the same year, leading to ghost double-counting.
		"""
		if self.course_offer:
			return [self.course_offer]

		# Fallback — get from the linked session
		if self.attendance_session:
			co = frappe.db.get_value("Attendance Session", self.attendance_session, "course_offering")
			if co:
				return [co]

		return []

	def trigger_recalculation(self):
		"""Trigger attendance summary recalculation for all relevant course offerings."""
		if not self.student:
			return
		try:
			from slcm.slcm.utils.attendance_calculator import calculate_student_attendance
			for course_offering in self.resolve_course_offerings():
				frappe.enqueue(
					calculate_student_attendance,
					student=self.student,
					course_offering=course_offering,
					queue="short"
				)
		except Exception as e:
			frappe.log_error(message=f"Error triggering recalculation: {str(e)}", title="Recalculation Trigger Error")

	def trigger_session_update(self):
		"""Update the parent Attendance Session counts.

		Multiple Student Attendance records for the same session can save in
		quick succession (e.g. bulk-marking a whole class), each triggering
		this update — a normal load -> modify -> doc.save() here would race
		on the session's in-memory timestamp and fail under that contention.
		Recompute in memory (reusing the doctype's own aggregation logic),
		then write the scalar fields directly via frappe.db.set_value(),
		which has no timestamp to go stale.
		"""
		if not self.attendance_session:
			return

		try:
			doc = frappe.get_doc("Attendance Session", self.attendance_session)
			doc.flags.from_student_attendance = True  # Prevents cascade recalculations
			doc.update_attendance_summary()
			frappe.db.set_value(
				"Attendance Session",
				doc.name,
				{
					"present_count": doc.present_count,
					"absent_count": doc.absent_count,
					"total_boys": doc.total_boys,
					"total_girls": doc.total_girls,
					"attendance_marked": doc.attendance_marked,
					"session_status": doc.session_status,
					"total_students": doc.total_students,
					"attendance_percentage": doc.attendance_percentage,
				},
				update_modified=True,
			)
		except Exception as e:
			frappe.log_error(message=f"Error updating session summary: {str(e)}", title="Session Summary Update Error")


@frappe.whitelist()
def get_enrolled_offerings(student):
	"""
	Fetch all Course Offerings of the student's active enrollments: the
	enrollment's enrolled courses, else the offerings of its programme,
	academic year and year no.
	Used to filter Course Offerings in the UI.
	"""
	if not student:
		return []

	from slcm.slcm.doctype.student_enrollment.student_enrollment import get_current_logs

	offerings = []
	enrollments = frappe.get_all(
		"Student Enrollment",
		filters={"student": student, "status": "Enrolled"},
		fields=["name", "program"],
	)
	current_logs = get_current_logs([e.name for e in enrollments])
	for enrollment in enrollments:
		rows = frappe.get_all(
			"Student Enrollment Course",
			filters={"parent": enrollment.name, "parenttype": "Student Enrollment"},
			pluck="course_offering",
		)
		rows = [r for r in rows if r]
		log = current_logs.get(enrollment.name)
		if not rows and log and log.academic_year:
			rows = frappe.get_all(
				"Course Offering",
				filters={
					"program": enrollment.program,
					"academic_year": log.academic_year,
					"year_no": log.year_no,
					"status": "Active",
				},
				pluck="name",
			)
		offerings.extend(rows)

	return list(dict.fromkeys(offerings))

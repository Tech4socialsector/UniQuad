
# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

import frappe
import os
from frappe.model.document import Document
from frappe.utils import getdate, date_diff

class FAMFAApplication(Document):
	def before_save(self):
		self.rename_proof_document()

	def rename_proof_document(self):
		"""Prefix the document name to proof_document filename to avoid collisions across students."""
		if not self.proof_document or not self.name:
			return

		prefix = self.name + "_"

		# Look up the File doc to get the real file_url on disk
		file_doc = frappe.db.get_value("File", {
			"file_url": self.proof_document,
			"attached_to_doctype": self.doctype,
			"attached_to_name": self.name
		}, "name")
		if not file_doc:
			file_doc = frappe.db.get_value("File", {"file_url": self.proof_document}, "name")

		if not file_doc:
			return

		file_obj = frappe.get_doc("File", file_doc)
		actual_url = file_obj.file_url  # authoritative path on disk
		actual_basename = os.path.basename(actual_url)

		if actual_basename.startswith(prefix):
			return  # already renamed

		new_basename = prefix + actual_basename
		is_private = actual_url.startswith("/private/")
		new_url = ("/private/files/" if is_private else "/files/") + new_basename

		base_dir = "private" if is_private else "public"
		old_path = frappe.get_site_path(base_dir, actual_url.lstrip("/"))
		new_path = frappe.get_site_path(base_dir, new_url.lstrip("/"))

		if os.path.exists(old_path) and not os.path.exists(new_path):
			os.rename(old_path, new_path)

		file_obj.file_name = new_basename
		file_obj.file_url = new_url
		file_obj.db_update()

		self.proof_document = new_url

	def validate(self):
		self.validate_dates()
		self.validate_approval_status()

	def validate_approval_status(self):
		if self.status == "Approved":
			if not self.approver:
				self.approver = frappe.session.user
		
		if self.status == "Rejected":
			if not self.rejection_reason:
				frappe.throw("Rejection Reason is required when rejecting an application.")
			if not self.approver:
				self.approver = frappe.session.user

	def validate_dates(self):
		if not self.examination_date:
			return

		exam_date = getdate(self.examination_date)
		today = getdate()
		
		# If applying strictly for University Representation (Competitions), check dates
		if self.reason == "University Representation":
			if not self.event_from_date or not self.event_to_date:
				frappe.throw("Event dates are required for University Representation.")
			
			event_from = getdate(self.event_from_date)
			event_to = getdate(self.event_to_date)
			
			# Rule: participation dates fall within three days of the exam
			# Logic: Check if exam_date is within [event_from - 3 days, event_to + 3 days]
			# Or if the event overlaps with Exam Date +/- 3 days window.
			# Simplified Interpretation: The event happened within 3 days (before/after/during) of the exam.
			
			days_diff_from = date_diff(exam_date, event_from) # exam - event_start
			days_diff_to = date_diff(event_to, exam_date)     # event_end - exam
			
			# Check if event is too far in past or future relative to exam
			# Distance between interval [event_from, event_to] and point exam_date should be <= 3
			
			# If exam is BEFORE event:
			if exam_date < event_from:
				gap = date_diff(event_from, exam_date)
			# If exam is AFTER event:
			elif exam_date > event_to:
				gap = date_diff(exam_date, event_to)
			else:
				# During event
				gap = 0
				
			if gap > 3:
				frappe.throw("For University Representation, participation dates must be within 3 days of the examination date.")

		# General Check: Application shouldn't be too old if applying AFTER exam?
		if date_diff(today, exam_date) > 10:
			if self.reason != "University Representation":
				frappe.msgprint("Warning: Application is submitted more than 10 days after the examination.")

	def on_submit(self):
		if self.status != "Approved":
			frappe.throw("Only Approved applications can be submitted.")
		self.trigger_attendance_recalculation()

	def on_cancel(self):
		self.trigger_attendance_recalculation()

	def on_trash(self):
		self.trigger_attendance_recalculation()

	def trigger_attendance_recalculation(self):
		"""
		Recalculate attendance for the Student and Course linked to this application.
		Since FA/MFA applies to a Course, we recalculate every Class of that course
		(in the application's term, when set) the student is enrolled in.
		"""
		try:
			term_cond = "AND cl.academic_term = %(academic_term)s" if self.academic_term else ""
			classes = frappe.db.sql_list(f"""
				SELECT DISTINCT cl.name
				FROM `tabClasses` cl
				JOIN `tabClass Enrolled Student` ces
					ON ces.parent = cl.name AND ces.parenttype = 'Classes'
				JOIN `tabStudent Enrollment` se ON se.name = ces.student_enrollment
				WHERE cl.course = %(course)s
				  AND se.student = %(student)s
				  {term_cond}
			""", {"course": self.course, "student": self.student, "academic_term": self.academic_term})

			if not classes:
				return

			from slcm.slcm.utils.attendance_calculator import calculate_student_attendance

			for class_name in classes:
				# Synchronous call for immediate UI update
				# This handles getting or creating the summary proactively
				calculate_student_attendance(self.student, class_name)
				
		except Exception as e:
			frappe.log_error(f"FA/MFA Recalc Error: {str(e)}")

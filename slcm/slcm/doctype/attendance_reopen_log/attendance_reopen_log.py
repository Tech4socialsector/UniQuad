# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AttendanceReopenLog(Document):
	"""Audit record of AAD reopening / re-locking a session's attendance.

	Rows are written only by slcm.slcm.utils.attendance_lock and are
	immutable afterwards, so the trail can be trusted."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Attendance Reopen Log entries cannot be modified."))

	def on_trash(self):
		if frappe.session.user != "Administrator":
			frappe.throw(_("Attendance Reopen Log entries cannot be deleted."))

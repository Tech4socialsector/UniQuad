# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Who created, edited, cancelled, swapped or deleted a Class's Time Table
sessions, and when. Rows are written by the system (add_log) and shown on the
Classes form's Schedule Log tab."""

from contextlib import contextmanager

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class ClassScheduleLog(Document):
	pass


def add_log(class_name, action, time_table=None, session_date=None, details=""):
	"""One log row; nothing is written for entries without a Class or while
	no_schedule_log() is active (the caller logs a summary instead)."""
	if not class_name or frappe.flags.no_class_schedule_log:
		return
	frappe.get_doc({
		"doctype": "Class Schedule Log",
		"class_name": class_name,
		"action": action,
		"time_table": time_table,
		"session_date": session_date,
		"details": details,
		"changed_by": frappe.session.user,
		"changed_on": now_datetime(),
	}).insert(ignore_permissions=True)


@contextmanager
def no_schedule_log():
	"""Silence the per-entry logs (Time Table on_update / on_trash) while one
	operation writes many entries and logs a single summary itself."""
	prev = frappe.flags.no_class_schedule_log
	frappe.flags.no_class_schedule_log = True
	try:
		yield
	finally:
		frappe.flags.no_class_schedule_log = prev


@frappe.whitelist()
def get_class_schedule_log(class_name, limit=200):
	"""The class's log, newest first, for the Classes form."""
	frappe.has_permission("Classes", "read", doc=class_name, throw=True)
	rows = frappe.get_all(
		"Class Schedule Log",
		filters={"class_name": class_name},
		fields=["action", "time_table", "session_date", "details", "changed_by", "changed_on"],
		order_by="changed_on desc, creation desc",
		limit=int(limit),
	)
	names = {u.name: u.full_name for u in frappe.get_all(
		"User", filters={"name": ["in", list({r.changed_by for r in rows if r.changed_by}) or [""]]},
		fields=["name", "full_name"],
	)}
	for r in rows:
		r.changed_by_name = names.get(r.changed_by) or r.changed_by
	return rows

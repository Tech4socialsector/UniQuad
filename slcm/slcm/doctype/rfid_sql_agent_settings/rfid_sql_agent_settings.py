# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

_IDENT = re.compile(r"^[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)*$")


class RFIDSQLAgentSettings(Document):
	def validate(self):
		self._validate_student_map()

	def _validate_student_map(self):
		"""Student Map table/column names are put into SQL, so only plain identifiers are allowed."""
		for field in ("map_source_table", "map_code_column"):
			value = (self.get(field) or "").strip()
			self.set(field, value)
			if value and not _IDENT.match(value):
				frappe.throw(_("{0}: use only letters, digits, _ and . (got {1})").format(
					self.meta.get_label(field), frappe.bold(value)))

		cols = [c.strip() for c in (self.map_name_columns or "").split(",") if c.strip()]
		for c in cols:
			if not _IDENT.match(c):
				frappe.throw(_("Name Column(s): {0} is not a valid column name").format(frappe.bold(c)))
		self.map_name_columns = ",".join(cols)

		field = (self.map_student_field or "").strip() or "registration_id"
		self.map_student_field = field
		if field != "name":
			df = frappe.get_meta("Student Master").get_field(field)
			if not df or df.fieldtype not in ("Data", "Link", "Read Only", "Dynamic Link"):
				frappe.throw(_("Match To Student Master Field: {0} is not a text field of Student Master").format(
					frappe.bold(field)))

# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AttendanceSummary(Document):
	def autoname(self):
		from frappe.model.naming import make_autoname
		# Deterministic name based on Student and Class
		if self.student and self.class_name:
			# Create a hash or structured ID to ensure uniqueness.
			# Using a hash is safer for length limits (140 chars max for name).
			# Format: ASU-{Student}-{Hash(Class)}
			import hashlib
			class_hash = hashlib.md5(self.class_name.encode("utf-8")).hexdigest()[:10]
			self.name = f"ASU-{self.student}-{class_hash}"
		else:
			self.name = make_autoname("ASU-.YYYY.-.#####")

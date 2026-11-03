# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Course(Document):

	def autoname(self):
		if not (self.course_code and self.course_name):
			frappe.throw(frappe._("Course Code and Course Name are required to name the Course."))

		course_name = self.course_name.strip().replace("/", "-")
		
		self.name = f"{course_name}-{self.course_code.strip()}"


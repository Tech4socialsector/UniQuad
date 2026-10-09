# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

CP = "Class-Participation"
OH = "Office Hours"

# Child-table (Student Group Student) fields owned by each group type
CP_FIELDS = [
	f"class_participation_{n}_hour" for n in ("1st", "2nd", "3rd", "4th", "5th", "6th")
] + [f"{n}_cp_grade" for n in ("1st", "2nd", "3rd", "4th", "5th", "6th")]
OH_FIELDS = ["office_hour_1st_hour", "office_hour_2nd_hour", "1st_oh_grade", "2nd_oh_grade"]


class StudentGroup(Document):
	def autoname(self):
		# {CP|OH}-{Programme Code}-{Academic Term}-{Week Name}, with the code
		# taken from the linked Programme's program_code. Several groups can
		# share these (different courses), so a numeric suffix is added when
		# the base name is already taken.
		prefix = "CP" if self.group_based_on == CP else "OH"
		programme_code = (
			frappe.db.get_value("Programme", self.programme, "program_code") if self.programme else None
		)
		parts = [prefix, programme_code, self.academic_term, self.week_name]
		base = "-".join(str(p).strip() for p in parts if p and str(p).strip())
		name, n = base, 1
		while frappe.db.exists("Student Group", name):
			name = f"{base}-{n}"
			n += 1
		self.name = name

	def validate(self):
		self._clear_other_group_type()

	def _clear_other_group_type(self):
		"""The child rows only show the section for this group type — clear
		the hidden section so stale CP/OH values aren't saved alongside."""
		hidden = OH_FIELDS if self.group_based_on == CP else CP_FIELDS
		for row in self.students:
			for field in hidden:
				row.set(field, 0)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def programme_query(doctype, txt, searchfield, start, page_len, filters):
	"""Programmes that have a Course Offering in the selected Academic Year + Term."""
	filters = filters or {}
	conditions = ["co.program IS NOT NULL", "co.program != ''"]
	values = {"txt": f"%{txt}%", "start": start, "page_len": page_len}
	if filters.get("academic_year"):
		conditions.append("co.academic_year = %(academic_year)s")
		values["academic_year"] = filters["academic_year"]
	if filters.get("academic_term"):
		conditions.append("co.term_name = %(academic_term)s")
		values["academic_term"] = filters["academic_term"]

	return frappe.db.sql(
		f"""SELECT DISTINCT p.name, p.program_name
		    FROM `tabCourse Offering` co
		    JOIN `tabProgramme` p ON p.name = co.program
		    WHERE {" AND ".join(conditions)}
		      AND (p.name LIKE %(txt)s OR p.program_name LIKE %(txt)s)
		    ORDER BY p.name
		    LIMIT %(start)s, %(page_len)s""",
		values,
	)

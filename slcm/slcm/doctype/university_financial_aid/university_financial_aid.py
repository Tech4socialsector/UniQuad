# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

AID_COMPONENTS = (
	"tuition_facilities",
	"hostel_mess",
	"lunch_dinner_charges",
	"stipend",
	"laptop",
	"loan",
)


class UniversityFinancialAid(Document):
	def validate(self):
		self._validate_duplicate()
		self.total_financial_aid = sum(flt(self.get(f)) for f in AID_COMPONENTS)

	def _validate_duplicate(self):
		existing = frappe.db.exists(
			"University Financial Aid",
			{"student": self.student, "academic_year": self.academic_year, "name": ["!=", self.name]},
		)
		if existing:
			frappe.throw(
				_("Financial Aid for {0} in {1} already exists: {2}").format(
					frappe.bold(self.student_name or self.student),
					frappe.bold(self.academic_year),
					frappe.get_desk_link("University Financial Aid", existing),
				)
			)

# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EvaluationSchema(Document):
	def validate(self):
		self.sync_reexam_effective_marks()
		self.validate_component_marks()
		self.validate_reexam_substitutes()

	def sync_reexam_effective_marks(self):
		"""Auto-set effective_max_marks for Re-Exam/Makeup schema_components from reexam_configs."""
		if not self.schema_components:
			return
		reexam_totals = {}
		for r in self.reexam_configs or []:
			if r.component:
				reexam_totals[r.component] = reexam_totals.get(r.component, 0) + (r.maximum_marks or 0)
		for comp_row in self.schema_components:
			ctype = self._get_component_type(comp_row.component)
			if ctype in ("Re Exam", "Makeup") and comp_row.component in reexam_totals:
				comp_row.effective_max_marks = reexam_totals[comp_row.component]

	def validate_component_marks(self):
		if not self.schema_components:
			return
		custom_components = [c for c in self.schema_components if self._get_component_type(c.component) == "Custom"]
		total = sum(c.effective_max_marks or 0 for c in custom_components)
		if custom_components and total != self.total_marks:
			self.total_marks = total

	def validate_reexam_substitutes(self):
		"""Substitute For must name a component this schema actually assesses."""
		used = {c.component for c in self.schema_components or []} | {a.component for a in self.assessment_configs or []}
		for row in self.reexam_configs or []:
			if row.substitute_for and row.substitute_for not in used:
				frappe.throw(
					frappe._("Re-Exam Configuration row {0}: Substitute For {1} is not a component of this schema.").format(
						row.idx, frappe.bold(row.substitute_for)
					)
				)

	def _get_component_type(self, component_name):
		if component_name:
			return frappe.db.get_value("Exam Component", component_name, "component_type") or "Custom"
		return "Custom"

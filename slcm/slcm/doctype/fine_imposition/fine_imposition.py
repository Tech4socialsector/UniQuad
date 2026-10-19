# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime


class FineImposition(Document):
	def validate(self):
		if getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To Date cannot be before From Date."))

	@frappe.whitelist()
	def get_outstanding_preview(self):
		demands = self._get_outstanding_demands()

		rows = []
		total_outstanding = 0
		total_estimated_fine = 0

		for demand in demands:
			estimated_fine = self._compute_fine_amount(demand.outstanding_amount)
			rows.append({
				"student": demand.student,
				"fee_component": demand.fee_component,
				"demand_type": demand.demand_type,
				"due_date": demand.due_date,
				"outstanding_amount": demand.outstanding_amount,
				"estimated_fine_amount": estimated_fine,
			})
			total_outstanding += flt(demand.outstanding_amount)
			total_estimated_fine += estimated_fine

		return {
			"rows": rows,
			"total_demands": len(rows),
			"total_outstanding": total_outstanding,
			"total_estimated_fine": total_estimated_fine,
		}

	@frappe.whitelist()
	def apply_fine(self):
		if self.status == "Applied":
			frappe.throw(_("This Fine Imposition has already been applied."))

		demands = self._get_outstanding_demands()
		if not demands:
			frappe.msgprint(_("No outstanding Fee Demands matched the selection criteria."))
			return {"total_demands_affected": 0, "total_fine_amount": 0}

		total_fine_amount = 0
		self.fine_log = []

		for demand in demands:
			fine_amount = self._compute_fine_amount(demand.outstanding_amount)
			if fine_amount <= 0:
				continue

			demand_doc = frappe.get_doc("Fee Demand", demand.name)
			demand_doc.penalty_amount = flt(demand_doc.penalty_amount) + fine_amount
			demand_doc.save(ignore_permissions=True)

			self.append("fine_log", {
				"student": demand.student,
				"source_fee_demand": demand.name,
				"outstanding_amount": demand.outstanding_amount,
				"fine_amount": fine_amount,
			})
			total_fine_amount += fine_amount

		self.status = "Applied"
		self.applied_on = now_datetime()
		self.applied_by = frappe.session.user
		self.total_demands_affected = len(self.fine_log)
		self.total_fine_amount = total_fine_amount
		self.save(ignore_permissions=True)

		return {
			"total_demands_affected": self.total_demands_affected,
			"total_fine_amount": self.total_fine_amount,
		}

	@frappe.whitelist()
	def reverse_fine(self):
		if self.status != "Applied":
			frappe.throw(_("Only an Applied Fine Imposition can be reversed."))

		for row in self.fine_log:
			if not row.source_fee_demand or not row.fine_amount:
				continue

			try:
				demand_doc = frappe.get_doc("Fee Demand", row.source_fee_demand)
			except frappe.DoesNotExistError:
				continue

			new_penalty = flt(demand_doc.penalty_amount) - flt(row.fine_amount)
			if new_penalty < 0:
				new_penalty = 0

			new_net_payable = flt(demand_doc.original_amount) - flt(demand_doc.waiver_amount) + new_penalty
			if flt(demand_doc.paid_amount) > new_net_payable:
				frappe.log_error(
					title="Fine Imposition Reversal Skipped",
					message=(
						f"Cannot reverse penalty on Fee Demand {demand_doc.name}: the amount already "
						f"paid ({demand_doc.paid_amount}) exceeds what would be owed after removing "
						f"the penalty ({new_net_payable})."
					),
				)
				continue

			demand_doc.penalty_amount = new_penalty
			demand_doc.save(ignore_permissions=True)

		self.status = "Reversed"
		self.reversed_on = now_datetime()
		self.reversed_by = frappe.session.user
		self.save(ignore_permissions=True)

		return {"status": self.status}

	def _compute_fine_amount(self, outstanding_amount):
		if self.fine_type == "Flat Amount":
			amount = flt(self.flat_amount)
		else:
			amount = flt(outstanding_amount) * flt(self.percentage) / 100

		if flt(self.max_fine_amount) > 0:
			amount = min(amount, flt(self.max_fine_amount))

		return flt(amount)

	def _get_outstanding_demands(self):
		filters = {
			"outstanding_amount": [">", 0],
			"status": ["not in", ["Paid", "Cancelled", "Waived"]],
			"due_date": ["between", [self.from_date, self.to_date]],
		}
		# never fine a fine: exclude dues whose Fee Component is a fine type ("Fine - …")
		fine_components = frappe.get_all("Fee Component", filters={"component_type": ["like", "Fine%"]}, pluck="name")
		if fine_components:
			filters["fee_component"] = ["not in", fine_components]
		if self.demand_type_filter:
			filters["demand_type"] = self.demand_type_filter
		if self.programme:
			filters["program"] = self.programme
		if self.academic_year:
			filters["academic_year"] = self.academic_year
		if flt(self.min_outstanding_amount) > 0:
			filters["outstanding_amount"] = [">=", flt(self.min_outstanding_amount)]

		return frappe.get_all(
			"Fee Demand",
			filters=filters,
			fields=[
				"name",
				"student",
				"academic_year",
				"outstanding_amount",
				"fee_component",
				"demand_type",
				"due_date",
			],
		)

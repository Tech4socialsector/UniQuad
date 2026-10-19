import json

import frappe
from frappe.model.document import Document
from frappe.utils import flt, today

EXCESS = "Excess Amount"


def get_available_excess(student, for_update=False):
	"""Active Student Credit Notes with unused balance, oldest first."""
	return frappe.db.sql(
		f"""SELECT name, available_credit, used_credit FROM `tabStudent Credit Note`
		WHERE student = %s AND docstatus = 1 AND status = 'Active' AND available_credit > 0
		ORDER BY creation ASC {"FOR UPDATE" if for_update else ""}""",
		(student,),
		as_dict=True,
	)


class FeeRefund(Document):

	def validate(self):
		if flt(self.refund_amount) <= 0:
			frappe.throw("Refund Amount must be greater than zero.")
		if self.refund_source == EXCESS:
			self._validate_excess_refund()
		else:
			self._validate_refund_amount()

	def on_submit(self):
		if self.refund_source == EXCESS:
			self._apply_excess_refund()
		else:
			self._apply_refund()
		self.db_set("status", "Approved")
		self.db_set("approved_by", frappe.session.user)
		self.db_set("approved_on", today())

	def on_cancel(self):
		if self.refund_source == EXCESS:
			self._reverse_excess_refund()
		else:
			self._reverse_refund()
		self.db_set("status", "Reversed")

	# ── Refund of the student's excess (Student Credit Notes) ───────────────
	def _validate_excess_refund(self):
		self.fee_demand = None
		self.fee_component = None
		self.original_amount = 0
		self.paid_amount = 0
		available = sum(flt(n.available_credit) for n in get_available_excess(self.student))
		if self.docstatus == 0:
			self.available_excess = available
		if flt(self.refund_amount) > available:
			frappe.throw(
				f"Refund Amount (₹{flt(self.refund_amount):,.2f}) cannot exceed the student's "
				f"available excess (₹{available:,.2f})."
			)

	def _apply_excess_refund(self):
		"""Take the refund from the student's active credit notes, oldest first."""
		notes = get_available_excess(self.student, for_update=True)
		remaining = flt(self.refund_amount)
		if remaining > sum(flt(n.available_credit) for n in notes):
			frappe.throw("The student's available excess changed and no longer covers this refund.")

		allocation = []
		for n in notes:
			if remaining <= 0:
				break
			take = min(remaining, flt(n.available_credit))
			new_available = flt(n.available_credit) - take
			frappe.db.set_value("Student Credit Note", n.name, {
				"available_credit": new_available,
				"used_credit": flt(n.used_credit) + take,
				"status": "Exhausted" if new_available <= 0 else "Active",
			})
			# Audit row on the credit note, same table the due adjustments use
			frappe.get_doc({
				"doctype": "Credit Adjustment Row",
				"parent": n.name,
				"parenttype": "Student Credit Note",
				"parentfield": "adjustments",
				"idx": frappe.db.count("Credit Adjustment Row", {"parent": n.name}) + 1,
				"fee_component": f"Refund {self.name}",
				"amount_adjusted": take,
				"adjusted_on": today(),
				"adjusted_by": frappe.session.user,
			}).insert(ignore_permissions=True)
			allocation.append({"credit_note": n.name, "amount": take})
			remaining -= take

		self.db_set("excess_allocation", json.dumps(allocation))

	def _reverse_excess_refund(self):
		for a in json.loads(self.excess_allocation or "[]"):
			note = frappe.db.get_value(
				"Student Credit Note", a["credit_note"], ["available_credit", "used_credit"], as_dict=True
			)
			if not note:
				continue
			frappe.db.set_value("Student Credit Note", a["credit_note"], {
				"available_credit": flt(note.available_credit) + flt(a["amount"]),
				"used_credit": max(0, flt(note.used_credit) - flt(a["amount"])),
				"status": "Active",
			})
			frappe.db.delete(
				"Credit Adjustment Row",
				{"parent": a["credit_note"], "parenttype": "Student Credit Note", "fee_component": f"Refund {self.name}"},
			)

	# ── Refund of money paid against one Fee Demand ─────────────────────────
	def _validate_refund_amount(self):
		refund = flt(self.refund_amount)
		if not self.fee_demand:
			frappe.throw("Fee Demand is required when the Refund Source is Fee Demand.")

		paid = flt(frappe.db.get_value("Fee Demand", self.fee_demand, "paid_amount"))
		if paid <= 0:
			frappe.throw(
				f"Cannot create a refund for demand {self.fee_demand} — "
				"no payment has been made yet. Refunds are only allowed after "
				"the student has paid towards this demand."
			)
		if refund > paid:
			frappe.throw(
				f"Refund Amount (₹{refund:,.2f}) cannot exceed the amount already paid "
				f"(₹{paid:,.2f}) on demand {self.fee_demand}."
			)

		existing = frappe.db.exists(
			"Fee Refund",
			{
				"fee_demand": self.fee_demand,
				"status": "Approved",
				"name": ["!=", self.name],
			}
		)
		if existing:
			frappe.throw(
				f"Fee Demand {self.fee_demand} already has an approved refund ({existing}). "
				"Cancel it before creating a new one."
			)

	def _apply_refund(self):
		demand = frappe.db.get_value(
			"Fee Demand", self.fee_demand,
			["status", "paid_amount", "refunded_amount", "net_payable",
			 "original_amount", "credit_adjusted", "outstanding_amount"],
			as_dict=True,
		)
		if not demand:
			frappe.throw(f"Fee Demand {self.fee_demand} not found.")
		if demand.status == "Cancelled":
			frappe.throw(f"Cannot process refund — Fee Demand {self.fee_demand} is Cancelled.")

		refund      = flt(self.refund_amount)
		new_paid    = max(0, flt(demand.paid_amount) - refund)
		new_refunded = flt(demand.refunded_amount) + refund
		net         = flt(demand.net_payable or demand.original_amount)
		new_outstanding = max(0, net - new_paid - flt(demand.credit_adjusted))

		new_status = demand.status
		if new_outstanding > 0 and demand.status == "Paid":
			new_status = "Partially Paid"
		elif new_outstanding > 0 and demand.status not in ("Partially Paid", "Overdue", "Waived", "Cancelled"):
			new_status = "Partially Paid"

		frappe.db.set_value("Fee Demand", self.fee_demand, {
			"paid_amount":       new_paid,
			"refunded_amount":   new_refunded,
			"outstanding_amount": new_outstanding,
			"status":            new_status,
		})

	def _reverse_refund(self):
		demand = frappe.db.get_value(
			"Fee Demand", self.fee_demand,
			["status", "paid_amount", "refunded_amount", "net_payable",
			 "original_amount", "credit_adjusted"],
			as_dict=True,
		)
		if not demand:
			return

		refund      = flt(self.refund_amount)
		new_paid    = flt(demand.paid_amount) + refund
		new_refunded = max(0, flt(demand.refunded_amount) - refund)
		net         = flt(demand.net_payable or demand.original_amount)
		new_outstanding = max(0, net - new_paid - flt(demand.credit_adjusted))

		new_status = demand.status
		if new_outstanding <= 0 and new_paid > 0:
			new_status = "Paid"
		elif new_paid > 0 and new_outstanding > 0:
			new_status = "Partially Paid"

		frappe.db.set_value("Fee Demand", self.fee_demand, {
			"paid_amount":       new_paid,
			"refunded_amount":   new_refunded,
			"outstanding_amount": new_outstanding,
			"status":            new_status,
		})

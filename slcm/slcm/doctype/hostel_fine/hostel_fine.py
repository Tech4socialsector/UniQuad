# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class HostelFine(Document):
	"""A fine is collected through the Fee Demand raised for it (slcm.slcm.fee.event_hooks.on_hostel_fine_insert),
	so the money is a Fee Payment with a receipt and reaches ERPNext. Status follows that demand: Paid is set when
	the demand is paid (FeeDemand.update_payment_status), Waived waives the demand."""

	def validate(self):
		before = self.get_doc_before_save()
		if not before:
			# without the component no demand is raised, and the fine could never be collected
			if not frappe.db.exists("Fee Component", {"component_type": "Fine - Hostel"}):
				frappe.throw(_("Create a Fee Component of type 'Fine - Hostel' first; the fine is collected through it."))
			return
		demand = self.fee_demand()
		collected = demand and flt(demand.paid_amount) + flt(demand.credit_adjusted) > 0

		if self.status == "Paid" and before.status != "Paid" and not (demand and demand.status == "Paid"):
			frappe.throw(
				_("Collect the fine with a Fee Payment against Fee Demand {0}; it is marked Paid when that demand is paid.").format(
					demand.name
				)
				if demand
				else _("Save the fine as Unpaid to raise its Fee Demand, then collect it with a Fee Payment.")
			)
		if before.status == "Paid" and self.status != "Paid" and demand and demand.status == "Paid":
			frappe.throw(_("Fee Demand {0} is paid. Cancel its Fee Payment first.").format(demand.name))
		if collected and (self.status == "Waived" or flt(self.amount) != flt(before.amount)):
			frappe.throw(
				_("Fee Demand {0} already has money against it. Refund or cancel the Fee Payment first.").format(demand.name)
			)

	def on_update(self):
		before = self.get_doc_before_save()
		if not before:
			return  # after_insert raises the demand
		demand = self.fee_demand()
		if not demand:
			if self.status == "Unpaid":
				from slcm.slcm.fee.event_hooks import on_hostel_fine_insert

				on_hostel_fine_insert(self)
			return
		if demand.status == "Paid":
			return
		doc = frappe.get_doc("Fee Demand", demand.name)
		if self.status == "Waived":
			doc.waiver_amount = doc.original_amount
		else:
			doc.original_amount = flt(self.amount)
			if before.status == "Waived":
				doc.waiver_amount = 0
				doc.status = "Pending"
		doc.save(ignore_permissions=True)

	def fee_demand(self):
		return frappe.db.get_value(
			"Fee Demand",
			{"trigger_ref_doctype": self.doctype, "trigger_ref_name": self.name, "status": ["!=", "Cancelled"]},
			["name", "status", "paid_amount", "credit_adjusted"],
			as_dict=True,
			order_by="creation desc",
		)

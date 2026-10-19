# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class FeePayment(Document):
	def validate(self):
		self._apply_voucher()
		self._fill_student_details()
		if self.fee_invoice:
			self.validate_payment_amount()
		# Validate multi-demand allocation if demands table is used
		if self.payment_demands:
			self._validate_demand_allocation()

	def on_submit(self):
		self.db_set("status", "Submitted", update_modified=False)
		if self.fee_invoice:
			self.update_fee_invoice()
		# Process multi-demand payments
		if self.payment_demands:
			self._apply_demand_payments()
		# Always create a receipt
		self._create_fee_receipt()

	def on_cancel(self):
		self.db_set("status", "Cancelled", update_modified=False)
		if self.fee_invoice:
			self.update_fee_invoice(cancel=True)
		# Reverse multi-demand payments
		if self.payment_demands:
			self._reverse_demand_payments()
		# Cancel linked receipt
		self._cancel_fee_receipt()

	def _apply_voucher(self):
		"""Single-due payment (Voucher Number, as in the bulk-upload sheet): the student and dues columns
		come from the voucher and the Fee Demands Covered row is built from the payment amount."""
		if not self.fee_demand:
			return
		d = frappe.db.get_value(
			"Fee Demand",
			self.fee_demand,
			["student", "fee_component", "description", "demand_date", "academic_year", "due_date", "remarks",
			 "original_amount", "penalty_amount", "waiver_amount", "net_payable", "paid_amount", "outstanding_amount"],
			as_dict=True,
		)
		if not d:
			frappe.throw(_("Voucher Number {0} was not found. It must be an existing Fee Demand ID.").format(self.fee_demand))
		if self.student and d.student and self.student != d.student:
			frappe.throw(
				_("Voucher {0} belongs to student {1}, not the selected Student ID {2}.").format(self.fee_demand, d.student, self.student)
			)
		self.student = d.student or self.student
		self.update({
			"fee_component": d.fee_component,
			"demand_date": d.demand_date,
			"academic_year": d.academic_year or self.academic_year,
			"due_date": d.due_date,
			"demand_remark": d.remarks or d.description,
			"original_amount": d.original_amount,
			"penalty_amount": d.penalty_amount,
			"waiver_amount": d.waiver_amount,
			"total_payable": d.net_payable,
			"paid_amount": d.paid_amount,
			"pending_amount": d.outstanding_amount,
		})

		others = [r.fee_demand for r in self.payment_demands if r.fee_demand != self.fee_demand]
		if others:
			frappe.throw(
				_("Voucher Number {0} is set, but Fee Demands Covered also lists {1}. Use either the Voucher Number "
				  "(one due) or the Fee Demands Covered table (several dues).").format(self.fee_demand, ", ".join(others))
			)
		if not self.payment_demands:
			self.append("payment_demands", {"fee_demand": self.fee_demand})
		row = self.payment_demands[0]
		row.demand_description = d.description or d.fee_component
		row.outstanding_amount = d.outstanding_amount
		row.amount_allocated = flt(self.amount)

	def _fill_student_details(self):
		if not self.student:
			return
		sm = frappe.db.get_value(
			"Student Master", self.student, ["registration_id", "application_number", "official_email_id", "email"], as_dict=True
		)
		if sm:
			self.registration_id = sm.registration_id or sm.application_number
			self.student_email = sm.official_email_id or sm.email

	def _validate_demand_allocation(self):
		total_allocated = sum(flt(row.amount_allocated) for row in self.payment_demands)
		if round(total_allocated, 2) != round(flt(self.amount), 2):
			frappe.throw(
				_("Total allocated amount ({0}) must equal the payment amount ({1}). "
				  "Please adjust the amounts in the Fee Demands table.").format(
					frappe.utils.fmt_money(total_allocated, currency="INR"),
					frappe.utils.fmt_money(flt(self.amount), currency="INR"),
				)
			)
		for row in self.payment_demands:
			if flt(row.amount_allocated) <= 0:
				frappe.throw(
					_("Row {0}: Amount Allocated must be greater than zero.").format(row.idx)
				)
			outstanding = frappe.db.get_value("Fee Demand", row.fee_demand, "outstanding_amount") or 0
			if flt(row.amount_allocated) > flt(outstanding):
				frappe.throw(
					_("Row {0}: Amount Allocated ({1}) exceeds outstanding amount ({2}) "
					  "for demand <b>{3}</b>.").format(
						row.idx,
						frappe.utils.fmt_money(row.amount_allocated, currency="INR"),
						frappe.utils.fmt_money(outstanding, currency="INR"),
						row.fee_demand,
					)
				)

	def _apply_demand_payments(self):
		for row in self.payment_demands:
			demand = frappe.get_doc("Fee Demand", row.fee_demand)
			demand.update_payment_status(paid_delta=flt(row.amount_allocated))
			frappe.db.set_value("Fee Demand", row.fee_demand, {
				"last_payment_date": self.payment_date,
				"payment_mode": self.payment_mode,
				"transaction_number": self.reference_number,
				"transaction_date": self.transaction_date,
				"bank_name": self.bank_name,
				"account_number": self.account_number,
				"ifsc_code": self.ifsc_code,
			}, update_modified=False)

	def _reverse_demand_payments(self):
		for row in self.payment_demands:
			try:
				demand = frappe.get_doc("Fee Demand", row.fee_demand)
				demand.update_payment_status(paid_delta=-flt(row.amount_allocated))
				frappe.db.set_value("Fee Demand", row.fee_demand, {
					"last_payment_date": None,
					"payment_mode": None,
					"transaction_number": None,
					"transaction_date": None,
					"bank_name": None,
					"account_number": None,
					"ifsc_code": None,
				}, update_modified=False)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"FeePayment: failed to reverse demand {row.fee_demand}")

	def _create_fee_receipt(self):
		student = frappe.db.get_value(
			"Student Master", self.student,
			["registration_id", "first_name", "last_name", "programme", "academic_year", "year_of_study"],
			as_dict=True
		) or {}

		receipt = frappe.get_doc({
			"doctype": "Fee Receipt",
			"student": self.student,
			"student_name": student.get("first_name", ""),
			"registration_id": student.get("registration_id", ""),
			"programme": student.get("programme", ""),
			"academic_year": student.get("academic_year", ""),
			"year_of_study": student.get("year_of_study", ""),
			"fee_payment": self.name,
			"receipt_date": self.payment_date,
			"amount": self.amount,
			"payment_mode": self.payment_mode,
			"bank_account": self.bank_account,
			"reference_number": self.reference_number,
			"transaction_date": self.transaction_date,
			"bank_name": self.bank_name,
			"account_number": self.account_number,
			"ifsc_code": self.ifsc_code,
			"received_by": frappe.session.user,
			"demands_paid": [
				{
					"fee_demand": row.fee_demand,
					"description": row.demand_description or row.fee_demand,
					"amount": row.amount_allocated,
				}
				for row in (self.payment_demands or [])
			],
		})
		receipt.insert(ignore_permissions=True)
		self.db_set("receipt", receipt.name, update_modified=False)

	def _cancel_fee_receipt(self):
		if self.receipt:
			try:
				receipt_doc = frappe.get_doc("Fee Receipt", self.receipt)
				if receipt_doc.docstatus == 1:
					receipt_doc.cancel()
				else:
					receipt_doc.db_set("status", "Cancelled")
			except Exception:
				frappe.log_error(frappe.get_traceback(), "FeePayment: failed to cancel receipt")

	def validate_payment_amount(self):
		"""Validate that payment amount doesn't exceed outstanding amount"""
		invoice = frappe.get_doc("Fee Invoice", self.fee_invoice)

		# Get existing payments for this invoice
		existing_payments = frappe.db.sql(
			"""
			SELECT SUM(amount) as total
			FROM `tabFee Payment`
			WHERE fee_invoice = %s
			AND docstatus = 1
			AND name != %s
		""",
			(self.fee_invoice, self.name),
			as_dict=True,
		)

		paid_amount = (existing_payments[0].total or 0) if existing_payments else 0
		# Use final_payable_amount (after scholarship) as the ceiling, not total_amount.
		# total_amount is the gross fee before any scholarship deduction, so using it
		# would allow payments beyond what the student actually owes.
		outstanding = invoice.final_payable_amount - paid_amount

		if self.amount > outstanding:
			frappe.throw(
				_("Payment amount ({0}) cannot exceed outstanding amount ({1})").format(
					self.amount, outstanding
				)
			)

	def update_fee_invoice(self, cancel=False):
		"""Update fee invoice with payment"""
		invoice = frappe.get_doc("Fee Invoice", self.fee_invoice)

		# Add or remove payment entry
		if cancel:
			# Remove payment entry
			invoice.payments = [p for p in invoice.payments if p.payment != self.name]
		else:
			# Add payment entry if not exists
			payment_exists = False
			for payment in invoice.payments:
				if payment.payment == self.name:
					payment.amount = self.amount
					payment.payment_date = self.payment_date
					payment.payment_mode = self.payment_mode
					payment_exists = True
					break

			if not payment_exists:
				invoice.append(
					"payments",
					{
						"payment": self.name,
						"amount": self.amount,
						"payment_date": self.payment_date,
						"payment_mode": self.payment_mode,
					},
				)

		invoice.save(ignore_permissions=True)
		invoice.reload()
		self._sync_student_master()

	def _sync_student_master(self):
		"""Aggregate paid/outstanding across all invoices and update Student Master fields."""
		student = getattr(self, "student", None) or frappe.db.get_value(
			"Fee Invoice", self.fee_invoice, "student"
		)
		if not student:
			return
		try:
			row = frappe.db.sql(
				"""
				SELECT
					COALESCE(SUM(GREATEST(paid_amount, 0)), 0)        AS total_paid,
					COALESCE(SUM(GREATEST(outstanding_amount, 0)), 0) AS total_outstanding
				FROM `tabFee Invoice`
				WHERE student = %s
				""",
				student,
				as_dict=True,
			)[0]
			total_paid        = frappe.utils.flt(row.total_paid or 0)
			total_outstanding = frappe.utils.flt(row.total_outstanding or 0)

			if total_outstanding <= 0 and total_paid > 0:
				status = "Paid"
			elif total_paid > 0:
				status = "Partially Paid"
			else:
				status = "Unpaid"

			prev_status = frappe.db.get_value("Student Master", student, "fee_payment_status") or "Unpaid"
			frappe.db.set_value(
				"Student Master", student,
				{
					"total_paid_amount":   total_paid,
					"outstanding_balance": total_outstanding,
					"fee_payment_status":  status,
				},
				update_modified=False,
			)

			# Rebuild the fee_invoices child table so admin can see updated invoice rows
			from slcm.slcm.doctype.student_master.student_master import (
				_rebuild_fee_invoices,
				_append_payment_log,
			)
			sm_doc = frappe.get_doc("Student Master", student, ignore_permissions=True)
			_rebuild_fee_invoices(sm_doc)

			_append_payment_log(
				student,
				"Payment Recorded",
				amount=total_paid,
				invoice=self.fee_invoice,
				payment_mode=getattr(self, "payment_mode", "") or "",
				from_status=prev_status,
				to_status=status,
				remarks=(
					f"Total paid: ₹{total_paid:,.0f} · Outstanding: ₹{total_outstanding:,.0f}"
				),
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "FeePayment._sync_student_master failed")

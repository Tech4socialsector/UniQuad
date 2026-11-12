# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate


class FeeInvoice(Document):
	def validate(self):
		self.calculate_amounts()
		self.update_status()

	def after_insert(self):
		self._sync_sm_invoice_table()

	def on_update(self):
		self._sync_sm_invoice_table()

	def _sync_sm_invoice_table(self):
		"""Rebuild the Student Master fee_invoices child table after any invoice change."""
		if not self.student:
			return
		try:
			from slcm.slcm.doctype.student_master.student_master import _rebuild_fee_invoices
			sm = frappe.get_doc("Student Master", self.student, ignore_permissions=True)
			_rebuild_fee_invoices(sm)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "FeeInvoice._sync_sm_invoice_table failed")

	def calculate_amounts(self):
		# Calculate total from components
		total = 0
		for row in self.fee_components:
			if row.is_taxable:
				row.tax_amount = flt(row.amount) * flt(row.tax_rate) / 100
			else:
				row.tax_amount = 0
			row.total_amount = flt(row.amount) + flt(row.tax_amount)
			
			total += flt(row.total_amount)
		
		self.total_amount = total
		self.final_payable_amount = max(0, flt(self.total_amount) - flt(self.scholarship_amount))

		# Calculate paid amount from payments
		paid = 0
		for payment in self.payments:
			paid += flt(payment.amount)
		self.paid_amount = paid

		self.outstanding_amount = flt(self.final_payable_amount) - flt(self.paid_amount)

	def update_status(self):
		if self.outstanding_amount <= 0:
			self.status = "Paid"
		elif self.paid_amount > 0:
			self.status = "Partially Paid"
		else:
			self.status = "Unpaid"

		# Check if overdue
		if self.due_date and getdate(nowdate()) > getdate(self.due_date) and self.status != "Paid":
			self.status = "Overdue"

	def on_update_after_submit(self):
		# Update fee assignment when payment is made
		reference_assignment = self.fee_assignment or self.applicant_fee_assignment
		if reference_assignment:
			# Check which doctype it belongs to
			assignment_doctype = None
			if self.fee_assignment and frappe.db.exists("Student Fee Assignment", self.fee_assignment):
				assignment_doctype = "Student Fee Assignment"
			elif self.applicant_fee_assignment and frappe.db.exists("Applicant Fee Assignment", self.applicant_fee_assignment):
				assignment_doctype = "Applicant Fee Assignment"
			
			if not assignment_doctype:
				return

			assignment = frappe.get_doc(assignment_doctype, reference_assignment)
			
			if assignment_doctype == "Student Fee Assignment":
				assignment.paid_amount = self.paid_amount
				assignment.outstanding_amount = self.outstanding_amount
				if hasattr(assignment, 'update_status'):
					assignment.update_status()
				assignment.save()
			else:
				# Applicant Fee Assignment
				if self.status == "Paid":
					assignment.status = "Converted"
				elif self.status == "Partially Paid":
					assignment.status = "Partially Paid"
				assignment.save()


	def on_payment_authorized(self, payment_status):
		"""Called by the payments app after a desk "Pay Online" checkout succeeds.

		Books what Razorpay actually took (not the client's checkout options), capped at what is still due;
		any excess - or the whole payment when the invoice was settled meanwhile - is recorded as unapplied
		on its SLCM Payment Request so it is refunded instead of lost. Idempotent on the payment id."""
		if payment_status not in ("Authorized", "Completed"):
			return

		# Razorpay payment ID is passed via frappe.flags.data by authorize_payment()
		flags_data = frappe.flags.get("data") or {}
		razorpay_payment_id = (flags_data.get("razorpay_payment_id") or "") if isinstance(flags_data, dict) else ""
		if razorpay_payment_id and frappe.db.exists(
			"Fee Payment", {"reference_number": razorpay_payment_id, "docstatus": 1}
		):
			return

		captured, order_id = None, None
		if razorpay_payment_id:
			try:
				from slcm.api.razorpay_reconcile import _payment

				gateway_payment = _payment(razorpay_payment_id)
				if gateway_payment.get("status") in ("captured", "authorized"):
					captured = flt(gateway_payment.get("amount")) / 100
					order_id = gateway_payment.get("order_id")
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"Fee Invoice {self.name}: could not fetch Razorpay payment")

		# Reload to get the latest outstanding_amount (may have changed)
		self.reload()
		outstanding = max(flt(self.outstanding_amount), 0)
		amount = min(captured, outstanding) if captured is not None else outstanding

		if amount > 0:
			payment = frappe.get_doc({
				"doctype":          "Fee Payment",
				"fee_invoice":      self.name,
				"student":          self.student,
				"amount":           amount,
				"payment_date":     frappe.utils.today(),
				"payment_mode":     "Online Payment",
				"payment_gateway":  "Razorpay",
				"reference_number": razorpay_payment_id,
				"remarks":          "Desk Pay Online (Fee Invoice)",
			})
			payment.insert(ignore_permissions=True)
			payment.submit()

		if razorpay_payment_id and captured is not None and order_id:
			self._attach_desk_intent(razorpay_payment_id, order_id, captured)
		excess = flt((captured or 0) - amount, 2)
		if razorpay_payment_id and excess > 0.01:
			from slcm.slcm.fee.payment_ledger import record_unapplied_quietly, sync_quietly

			if amount > 0:
				sync_quietly(razorpay_payment_id)  # its request shows the captured amount, the excess as unallocated
			else:
				record_unapplied_quietly(
					"Razorpay", razorpay_payment_id, order_id, "Fee Invoice", self.name, excess, self.student,
					f"Desk Pay Online on {self.name}: Razorpay payment {razorpay_payment_id} (₹{excess:,.2f}) arrived "
					"after the invoice was settled. Needs refund.",
				)

		# the attempt logged by initiate_online_payment
		log = frappe.db.get_value(
			"Online Payment Log", {"fee_invoice": self.name, "status": "Pending"}, "name", order_by="creation desc"
		)
		if log:
			frappe.db.set_value("Online Payment Log", log, {
				"status": "Success", "transaction_id": razorpay_payment_id, "amount": captured if captured is not None else amount,
			})

	def _attach_desk_intent(self, payment_id, order_id, captured):
		"""Give the desk checkout's Integration Request the same intent portal orders carry
		(slcm.api.razorpay_reconcile.attach_intent), so the payment ledger knows what the order charged and
		record_unbooked_captures can see it."""
		import json

		rows = frappe.get_all(
			"Integration Request",
			filters={"integration_request_service": "Razorpay", "reference_docname": self.name,
			         "data": ("like", f"%{payment_id}%")},
			fields=["name", "data"], limit=1, ignore_permissions=True,
		)
		if not rows:
			return
		try:
			data = json.loads(rows[0].data or "{}")
		except ValueError:
			return
		if not isinstance(data, dict) or data.get("slcm_intent"):
			return
		data["slcm_intent"] = {
			"flow": "invoice", "order_id": order_id, "student": self.student, "amount": flt(captured, 2),
			"user": frappe.session.user, "paid_by_role": "Desk", "invoice_name": self.name,
		}
		frappe.db.set_value("Integration Request", rows[0].name, "data", json.dumps(data, default=str), update_modified=False)

	def get_payment_details(self):
		"""Returns details for the payment gateway."""
		return {
			"amount": self.outstanding_amount,
			"title": _("Fee Payment for {0}").format(self.name),
			"description": _("Payment for Student: {0}").format(self.student_name),
			"reference_doctype": self.doctype,
			"reference_docname": self.name,
			"payer_email": frappe.db.get_value("Student Master", self.student, "email"),
			"payer_name": self.student_name,
			"currency": "INR",  # Adjust as needed
		}

	@frappe.whitelist()
	def initiate_online_payment(self):
		"""
		Logs the attempt and returns the checkout URL.
		Handles gateway resolution server-side to avoid permission issues.
		"""
		# run_doc_method only checks read; this saves the invoice and logs a payment attempt
		self.check_permission("write")
		self.flags.ignore_links = True
		self.save(ignore_permissions=True) # Ensure amounts are calculated
		from slcm.slcm.fee import payment_gateway as gw

		gateway = gw.for_invoice(self.name)
		if gateway != gw.RAZORPAY:
			frappe.throw(
				_("This invoice is collected through {0}. The student or parent can pay it from their portal.").format(gateway)
			)
		if not frappe.db.exists("Payment Gateway", gateway):
			frappe.throw(_("Payment Gateway {0} is not configured.").format(gateway))

		# Create Log
		log = frappe.get_doc({
			"doctype": "Online Payment Log",
			"fee_invoice": self.name,
			"gateway": gateway,
			"amount": self.outstanding_amount,
			"status": "Pending"
		})
		log.insert(ignore_permissions=True)

		# Get Checkout URL
		from payments.utils.utils import get_checkout_url
		return get_checkout_url(
			payment_gateway=gateway,
			amount=self.outstanding_amount,
			reference_doctype=self.doctype,
			reference_docname=self.name,
			currency="INR" # Adjust as needed
		)

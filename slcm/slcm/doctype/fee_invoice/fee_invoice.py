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
		"""Called by the payments app after a successful transaction."""
		if payment_status not in ("Authorized", "Completed"):
			return

		# Reload to get the latest outstanding_amount (may have changed)
		self.reload()
		outstanding = flt(self.outstanding_amount)
		if outstanding <= 0:
			return  # already fully paid — nothing to record

		# Razorpay payment ID is passed via frappe.flags.data by authorize_payment()
		flags_data = frappe.flags.get("data") or {}
		razorpay_payment_id = (
			flags_data.get("razorpay_payment_id") or ""
			if isinstance(flags_data, dict) else ""
		)

		payment = frappe.get_doc({
			"doctype":          "Fee Payment",
			"fee_invoice":      self.name,
			"student":          self.student,
			"amount":           outstanding,
			"payment_date":     frappe.utils.today(),
			"payment_mode":     "Online Payment",
			"reference_number": razorpay_payment_id,
		})
		payment.insert(ignore_permissions=True)
		payment.submit()

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

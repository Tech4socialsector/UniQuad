# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _

# Mapping: Razorpay gateway_status -> internal system status (only backend/webhook may set status)
GATEWAY_TO_SYSTEM_STATUS = {
	"created": "Requested",
	"authorized": "Requested",
	"captured": "Paid",
	"failed": "Failed",
	"refunded": "Cancelled",
}


class SLCMPaymentRequest(Document):
	def validate(self):
		self.set_common_gateway_ids()
		if self.amount <= 0:
			frappe.throw(_("Amount must be greater than zero."))
		# System status must never be set directly from frontend; only backend/webhook updates it.
		if self.get("__islocal"):
			return
		old_status = frappe.db.get_value(self.doctype, self.name, "status")
		if old_status is not None and self.status != old_status:
			if not frappe.flags.get("payment_request_status_from_backend"):
				frappe.throw(
					_("Status cannot be changed from the form. It is updated by the payment gateway webhook.")
				)

	def set_common_gateway_ids(self):
		"""Fill the gateway-neutral ids from the Razorpay-named fields (admission / PACE flows write those).
		Rows updated with db_set are filled by slcm.slcm.fee.payment_ledger.fill_common_ids."""
		txn = self.transaction_id or ""
		order_id = self.razorpay_order_id or (txn if txn.startswith("order_") and not self.gateway_order_id else None)
		if order_id and order_id != self.gateway_order_id:
			self.gateway_order_id = order_id
		payment_id = self.razorpay_payment_id or (txn if txn.startswith("pay_") and not self.gateway_payment_id else None)
		if payment_id and payment_id != self.gateway_payment_id:
			if self.gateway_payment_id:
				# a retry on the same request: details looked up for the previous attempt no longer apply
				self.payment_method = self.bank_reference = self.payer_account = self.payer_bank = None
			self.gateway_payment_id = payment_id

	def before_save(self):
		if self.status == "Paid" and not self.paid_on:
			self.paid_on = frappe.utils.now_datetime()

	def on_submit(self):
		# Student payments are recorded after the gateway's result (slcm.slcm.fee.payment_ledger): no checkout to create
		if self.status in ("Paid", "Failed"):
			return
		if not self.payment_url:
			self.get_payment_url()

	def get_payment_url(self):
		"""
		Generates the checkout URL using the payments app.
		"""
		if not self.payment_gateway:
			self.payment_gateway = "Razorpay"  # admissions always collect through Razorpay
		
		if not self.payment_gateway:
			frappe.throw(_("Please configure and enable a Payment Gateway."))

		from payments.utils.utils import get_checkout_url
		
		url = get_checkout_url(
			payment_gateway=self.payment_gateway,
			amount=self.amount,
			currency=self.currency or "INR",
			reference_doctype=self.reference_doctype,
			reference_docname=self.reference_name,
			payer_email=self.email_to,
			payer_name=self.email_to # Fallback
		)
		
		self.db_set("payment_url", url)
		self.db_set("status", "Requested")
		
		return url

	def on_payment_authorized(self, status):
		"""
		Called by payments app after successful payment.
		"""
		if status in ["Authorized", "Completed"]:
			self.db_set("status", "Paid")
			
			# Update the referencing document
			if self.reference_doctype and self.reference_name:
				try:
					ref_doc = frappe.get_doc(self.reference_doctype, self.reference_name)
					# According to requirement: Update status to "Payment Completed"
					if hasattr(ref_doc, "status"):
						ref_doc.db_set("status", "Payment Completed")
					elif hasattr(ref_doc, "status"):
						ref_doc.db_set("status", "Payment Completed")
						
					frappe.msgprint(_("Payment successful for {0}").format(self.reference_name))
				except Exception as e:
					frappe.log_error(frappe.get_traceback(), _("Payment Success Callback Error"))

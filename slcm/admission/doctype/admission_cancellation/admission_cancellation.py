import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, flt
from slcm.admission.doctype.refund_request.refund_request import create_refund_request

class AdmissionCancellation(Document):
	def after_insert(self):
		refund_name = create_refund_request(self)
		if refund_name:
			self.db_set("refund_request", refund_name)

	def validate(self):
		# Only auto-fetch on first creation to avoid overwriting manually set values
		if self.is_new():
			self.fetch_applicant_details()
		self.set_cancellation_metadata()

	def fetch_applicant_details(self):
		if not self.applicant:
			return

		# Fetch program and campus from applicant
		applicant_doc = frappe.get_doc("Applicant", self.applicant)
		if not self.program:
			self.program = applicant_doc.program
		if not self.campus:
			self.campus = applicant_doc.campus

		if not self.offer:
			offer_name = frappe.db.get_value(
				"Offer Letter",
				{"applicant": self.applicant, "status": ["not in", ["Rejected", "Withdrawn"]]},
				"name",
				order_by="creation desc"
			)
			if offer_name:
				self.offer = offer_name

		if self.applicant_payment_receipt:
			return

		offer_name = self.offer
		if not offer_name:
			return

		# ── Primary: resolve via Applicant Payment Receipts linked to the Offer Letter ──

		receipts = frappe.get_all(
			"Applicant Payment Receipt",
			filters={"offer_letter": offer_name, "docstatus": ["<", 2]},
			fields=["name", "net_amount", "total_amount", "transaction_id"],
			order_by="creation desc"
		)

		if receipts:
			total_paid = 0.0
			for r in receipts:
				amt = flt(r.net_amount) if flt(r.get("net_amount")) > 0 else flt(r.total_amount)
				total_paid += amt
			self.applicant_payment_receipt = receipts[0].name
			self.amount_paid = total_paid
			self.razorpay_id = receipts[0].transaction_id
			return

		# ── Fallback: no APR found, try Payment Request on Offer Letter ──
		pr = frappe.db.get_value(
			"SLCM Payment Request",
			{"reference_doctype": "Offer Letter", "reference_name": offer_name, "status": "Paid"},
			["name", "amount", "transaction_id"],
			as_dict=True,
			order_by="creation desc"
		)
		if pr:
			self.amount_paid = flt(pr.amount)
			self.razorpay_id = pr.transaction_id


	def set_cancellation_metadata(self):
		if self.is_new():
			self.requested_by = frappe.session.user
			self.requested_on = now_datetime()

		if self.status in ["Approved", "Completed"]:
			if not self.cancelled_by:
				self.cancelled_by = frappe.session.user
				self.cancelled_on = now_datetime()
		else:
			self.cancelled_by = None
			self.cancelled_on = None

	def on_trash(self):
		"""
		Breaks the circular link with Refund Request to allow deletion.
		"""
		if self.refund_request:
			# Unset the link in the child refund record
			frappe.db.set_value("Refund Request", self.refund_request, "admission_cancellation", None)
			frappe.db.commit()

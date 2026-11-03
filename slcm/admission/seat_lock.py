# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt.
"""
Admission seat lock after payment: mark offer as confirmed and lock seat.
"""

from __future__ import unicode_literals

import frappe
from frappe import _


def lock_seat_after_payment(payment_request):
	"""
	Called when a Payment Request becomes Paid (e.g. from Razorpay webhook).
	Fetches the linked Admission Offer (Offer Letter), updates status = Payment Completed, 
	and syncs seat allocation status.
	"""
	if not payment_request:
		return
	# Resolve to doc if name passed
	if isinstance(payment_request, str):
		pr_doc = frappe.get_doc("SLCM Payment Request", payment_request)
	else:
		pr_doc = payment_request
	if getattr(pr_doc, "reference_doctype", None) != "Offer Letter":
		return
	offer_name = getattr(pr_doc, "reference_name", None) or frappe.db.get_value(
		"SLCM Payment Request", pr_doc.name, "reference_name"
	)
	if not offer_name:
		return
	try:
		offer = frappe.get_doc("Offer Letter", offer_name)
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=_("Seat Lock: Offer Letter not found"),
		)
		return

	# Mark seat locked and confirm offer (Payment Completed = confirmed in this codebase)
	offer.db_set("status", "Payment Completed")
	frappe.db.commit()

	# Update Applicant Fee Assignment to Paid
	frappe.db.set_value(
		"Applicant Fee Assignment",
		{"offer_letter": offer.name, "status": ["!=", "Cancelled"]},
		"status",
		"Paid",
	)

	# Sync to Seat Allocation and trigger post-payment logic (receipt, notifications)
	from slcm.api.service.offer_service import OfferService
	from slcm.api.service import fee_service as fee_service_module

	OfferService.sync_seat_allocation_status(offer, "Confirmation Fee Paid")
	OfferService.update_applicant_status(offer.applicant, status="Confirmation Fee Paid")

	# Generate receipt if not already generated
	payment_id = getattr(pr_doc, "razorpay_payment_id", None) or pr_doc.get("razorpay_payment_id") or pr_doc.get("transaction_id")
	if payment_id and frappe.db.get_value("Offer Letter", offer.name, "status") == "Payment Completed":
		try:
			fee_service_module.FeeService.generate_receipt(offer, payment_id, "Online")
		except Exception as e:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=_("Seat Lock: Receipt generation failed"),
			)

	# Optional: log communication
	try:
		from slcm.admission.utils.notifications import log_communication
		log_communication(
			applicant=offer.applicant,
			communication_type="Portal Notification",
			category="Fee",
			subject=_("Admission Fee Payment Completed"),
			content=_("Your payment has been received. Your seat is confirmed."),
			reference_doctype="Offer Letter",
			reference_name=offer.name,
		)
	except Exception:
		pass

	frappe.db.commit()

# Copyright (c) 2026, TFSS and contributors
"""Shared Razorpay helpers for admission payment flows (Applicant, Offer, PACE)."""

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import flt, now_datetime


ADMISSION_REF_DOCTYPES = ("PACE Applicant Fee Assignment", "Offer Letter", "Applicant")


def get_razorpay_client():
	import razorpay

	settings = frappe.get_single("Razorpay Settings")
	api_key = settings.api_key
	api_secret = settings.get_password("api_secret")
	if not api_key or not api_secret:
		frappe.throw(_("Razorpay credentials are not configured."))
	return razorpay.Client(auth=(api_key, api_secret))


def get_offer_payable_amount(offer):
	"""Scholarship-adjusted payable amount in rupees (matches order creation)."""
	if isinstance(offer, str):
		offer = frappe.get_doc("Offer Letter", offer)
	actual = flt(offer.payable_amount)
	target_fee_type = "Confirmation Fee" if offer.status == "Accepted" else "Admission Fee"
	afa = frappe.db.get_value(
		"Applicant Fee Assignment",
		{"offer_letter": offer.name, "fee_type": target_fee_type, "status": "Assigned", "docstatus": ["!=", 2]},
		["final_payable_amount"],
		as_dict=True,
	)
	if afa and afa.final_payable_amount is not None:
		actual = flt(afa.final_payable_amount)
	return actual


def get_expected_amount_paise(ref_doctype, ref_name, pr_amount_fallback=None):
	if ref_doctype == "PACE Applicant Fee Assignment":
		amount = frappe.db.get_value(
			"PACE Applicant Fee Assignment", ref_name, "final_payable_amount"
		)
	elif ref_doctype == "Offer Letter":
		amount = get_offer_payable_amount(ref_name)
	elif ref_doctype == "Applicant":
		amount = frappe.db.get_value("Applicant", ref_name, "application_fee_amount")
	else:
		amount = pr_amount_fallback
	return int(flt(amount or pr_amount_fallback or 0) * 100)


def payment_amount_matches(payment, expected_paise):
	actual = int(payment.get("amount") or 0)
	fee = int(payment.get("fee") or 0)
	return actual >= expected_paise


def fetch_order_payments(rzp_client, order_id):
	if not order_id:
		return []
	try:
		resp = rzp_client.order.payments(order_id)
		return (resp or {}).get("items") or []
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Razorpay order.payments failed for {order_id}")
		return []


def get_blocking_payment_on_order(rzp_client, order_id):
	"""Return captured or authorized payment on the order, if any."""
	for payment in fetch_order_payments(rzp_client, order_id):
		if payment.get("status") in ("captured", "authorized"):
			return payment
	return None


def order_id_is_reusable(rzp_client, order_id):
	"""False when the Razorpay order is paid or has an in-flight authorized/captured payment."""
	if not order_id:
		return False
	try:
		order = rzp_client.order.fetch(order_id)
		if (order or {}).get("status") not in ("created", "attempted"):
			return False
	except Exception as e:
		if "does not exist" in str(e) or e.__class__.__name__ == "BadRequestError":
			# Quietly handle non-existent order IDs (e.g. from different environment/keys)
			return False
		frappe.log_error(frappe.get_traceback(), f"Razorpay order.fetch failed for {order_id}")
		return False
	return get_blocking_payment_on_order(rzp_client, order_id) is None


def resolve_reusable_order_id(rzp_client, order_id, pr_status="Requested"):
	order_id = (order_id or "").strip()
	if not order_id or (pr_status or "").strip() not in ("Requested", "Draft", "Initiated"):
		return order_id
	if order_id_is_reusable(rzp_client, order_id):
		return order_id
	return ""


def cancel_payment_request_for_retry(pr):
	"""Cancel or delete a failed/stale Payment Request so a fresh order can be created."""
	if not pr:
		return
	try:
		pr.flags.ignore_permissions = True
		pr.flags.ignore_links = True
		if pr.docstatus == 1:
			pr.cancel()
		elif pr.docstatus == 0:
			pr.delete()
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Cancel Payment Request {pr.name} for retry")


def capture_authorized_payment(rzp_client, payment, expected_paise):
	"""Capture an authorized payment; return updated payment dict or None on failure."""
	if not payment or payment.get("status") != "authorized":
		return payment
	try:
		return rzp_client.payment.capture(
			payment.get("id"),
			expected_paise,
			{"currency": payment.get("currency") or "INR"},
		)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Razorpay capture failed for payment {payment.get('id')}",
		)
		return None


def try_capture_authorized_on_order(rzp_client, order_id, expected_paise):
	"""Capture the first authorized payment on an order. Returns captured payment dict or None."""
	for payment in fetch_order_payments(rzp_client, order_id):
		if payment.get("status") == "authorized":
			captured = capture_authorized_payment(rzp_client, payment, expected_paise)
			if captured and captured.get("status") == "captured":
				return captured
	return None


def sync_business_doc_on_payment_failed(ref_doctype, ref_name, error_desc=None):
	"""Align Applicant / Offer / PACE records when gateway reports payment.failed."""
	if ref_doctype == "Applicant":
		if frappe.db.get_value("Applicant", ref_name, "application_fee_status") != "Paid":
			frappe.db.set_value(
				"Applicant", ref_name, "application_fee_status", "Pending", update_modified=True
			)
	elif ref_doctype == "Offer Letter":
		if frappe.db.get_value("Offer Letter", ref_name, "status") != "Payment Completed":
			try:
				from slcm.api.service.offer_service import OfferService
				OfferService.log_action(
					ref_name,
					"Payment Failed",
					notes=error_desc or _("Payment attempt failed at the gateway."),
				)
			except Exception:
				pass
	# PACE assignment stays Assigned — PR carries Failed status for audit


def complete_admission_payment_from_gateway(
	ref_doctype, ref_name, pr_name, order_id, payment_id, payment, gateway=None
):
	"""
	Validate gateway payment payload and mark the admission record paid.
	Used by webhooks and reconciliation.
	Returns True if completed, False if skipped/invalid.
	"""
	if not payment or payment.get("status") != "captured":
		return False

	stored_order = frappe.db.get_value("SLCM Payment Request", pr_name, "razorpay_order_id")
	if stored_order and stored_order != order_id:
		return False

	pr_amount = frappe.db.get_value("SLCM Payment Request", pr_name, "amount")
	expected_paise = get_expected_amount_paise(ref_doctype, ref_name, pr_amount)
	if not payment_amount_matches(payment, expected_paise):
		frappe.logger().error(
			f"Gateway payment amount mismatch: ref={ref_doctype}/{ref_name}, "
			f"expected={expected_paise}, actual={payment.get('amount')}"
		)
		return False

	if payment.get("order_id") and payment.get("order_id") != order_id:
		return False

	gateway = gateway or frappe.db.get_value("SLCM Payment Request", pr_name, "payment_gateway")
	response_data = payment

	if ref_doctype == "PACE Applicant Fee Assignment":
		frappe.db.sql(
			"SELECT name FROM `tabPACE Applicant Fee Assignment` WHERE name = %s FOR UPDATE",
			ref_name,
		)
		assignment = frappe.get_doc(
			"PACE Applicant Fee Assignment", ref_name, check_permission=False
		)
		assignment.reload()
		if assignment.status == "Paid":
			return True
		expected_currency = assignment.currency or "INR"
		if payment.get("currency") != expected_currency:
			return False
		from slcm.pace.web_form.pace_application_form.pace_application_form import (
			complete_pace_payment,
		)
		complete_pace_payment(
			assignment=assignment,
			gateway=gateway,
			razorpay_order_id=order_id,
			razorpay_payment_id=payment_id,
			response_data=response_data,
		)
	elif ref_doctype == "Offer Letter":
		frappe.db.sql("SELECT name FROM `tabOffer Letter` WHERE name = %s FOR UPDATE", ref_name)
		offer = frappe.get_doc("Offer Letter", ref_name, check_permission=False)
		offer.reload()
		if offer.status == "Payment Completed":
			return True
		if payment.get("currency") != "INR":
			return False
		from slcm.api.service.fee_service import FeeService
		FeeService.complete_offer_payment(
			offer, payment_id, order_id, gateway, response_data=response_data
		)
	elif ref_doctype == "Applicant":
		frappe.db.sql("SELECT name FROM `tabApplicant` WHERE name = %s FOR UPDATE", ref_name)
		applicant = frappe.get_doc("Applicant", ref_name, check_permission=False)
		applicant.reload()
		if applicant.application_fee_status == "Paid":
			return True
		currency = (
			getattr(applicant, "currency", None)
			or frappe.defaults.get_global_default("currency")
			or "INR"
		)
		if payment.get("currency") != currency:
			return False
		from slcm.api.service.fee_service import FeeService
		FeeService.complete_application_fee_payment(
			applicant, payment_id, order_id, gateway, response_data=response_data
		)
	else:
		return False

	frappe.db.commit()
	return True


def reconcile_payment_request_record(pr_row, rzp_client=None):
	"""
	Poll Razorpay for an admission Payment Request and complete or fail it.
	pr_row: dict or document with name, reference_doctype, reference_name,
	        transaction_id, razorpay_order_id, payment_gateway, amount, currency.
	Returns: captured | failed | pending | skipped
	"""
	if isinstance(pr_row, str):
		pr_row = frappe.get_doc("SLCM Payment Request", pr_row).as_dict()

	ref_doctype = pr_row.get("reference_doctype")
	if ref_doctype not in ADMISSION_REF_DOCTYPES:
		return "skipped"

	order_id = pr_row.get("razorpay_order_id") or pr_row.get("transaction_id")
	if not order_id or not str(order_id).startswith("order_"):
		return "skipped"

	if not rzp_client:
		rzp_client = get_razorpay_client()

	expected_paise = get_expected_amount_paise(
		ref_doctype, pr_row.get("reference_name"), pr_row.get("amount")
	)

	captured_payment = try_capture_authorized_on_order(rzp_client, order_id, expected_paise)
	if not captured_payment:
		payments_list = fetch_order_payments(rzp_client, order_id)
		captured_payment = next(
			(p for p in payments_list if p.get("status") == "captured"), None
		)
		failed_payment = next(
			(p for p in payments_list if p.get("status") == "failed"), None
		)
	else:
		failed_payment = None

	if captured_payment:
		if not payment_amount_matches(captured_payment, expected_paise):
			frappe.logger().error(
				f"Reconciliation amount mismatch PR={pr_row.get('name')}"
			)
			return "skipped"
		expected_currency = pr_row.get("currency") or "INR"
		if captured_payment.get("currency") != expected_currency:
			return "skipped"

		ok = complete_admission_payment_from_gateway(
			ref_doctype,
			pr_row.get("reference_name"),
			pr_row.get("name"),
			order_id,
			captured_payment.get("id"),
			captured_payment,
			gateway=pr_row.get("payment_gateway"),
		)
		return "captured" if ok else "skipped"

	if failed_payment:
		frappe.db.set_value(
			"SLCM Payment Request",
			pr_row.get("name"),
			{
				"gateway_status": "failed",
				"failure_message": failed_payment.get("error_description")
				or _("Payment failed at gateway"),
				"gateway_response": frappe.as_json(failed_payment),
			},
			update_modified=True,
		)
		sync_business_doc_on_payment_failed(
			ref_doctype,
			pr_row.get("reference_name"),
			failed_payment.get("error_description"),
		)
		frappe.db.commit()
		return "failed"

	return "pending"


def prepare_checkout_order(rzp_client, controller, payment_details, pr, actual_payable):
	"""
	Reuse a valid Razorpay order when possible; otherwise create a new one.
	Handles in-flight authorized/captured payments on the same order.
	Returns dict with order_id, amount (paise), currency.
	"""
	order_id = (getattr(pr, "razorpay_order_id", None) or pr.transaction_id or "").strip()
	pr_status = (pr.status or "").strip()
	expected_paise = int(flt(actual_payable) * 100)

	if order_id and pr_status in ("Requested", "Draft", "Initiated"):
		blocking = get_blocking_payment_on_order(rzp_client, order_id)
		if blocking:
			status = blocking.get("status")
			if status == "captured":
				frappe.throw(
					_("Payment is already captured. Please refresh the page."),
					frappe.ValidationError,
				)
			if status == "authorized":
				frappe.throw(
					_(
						"A payment is pending capture on this order. "
						"Please wait a few minutes and refresh, or contact support."
					),
					frappe.ValidationError,
				)

		order_id = resolve_reusable_order_id(rzp_client, order_id, pr_status)
		if not order_id:
			pr.db_set({"transaction_id": "", "razorpay_order_id": ""}, update_modified=False)

	if order_id:
		return {
			"order_id": order_id,
			"amount": expected_paise,
			"currency": pr.currency or payment_details.get("currency") or "INR",
		}

	order = controller.create_order(**payment_details)
	if not order or not order.get("id"):
		frappe.throw(_("Order creation failed. Please check gateway logs."))
	return order

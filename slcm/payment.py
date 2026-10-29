# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt.
"""
Payment gateway integration: Razorpay order creation and webhook handling.
System status is derived from gateway_status; only backend/webhook updates status.
"""

from __future__ import unicode_literals

import json
import hmac
import hashlib
import frappe
from frappe import _


# Razorpay gateway_status -> internal system status (only backend/webhook may set status)
GATEWAY_TO_SYSTEM_STATUS = {
	"created": "Requested",
	"authorized": "Requested",
	"captured": "Paid",
	"failed": "Failed",
	"refunded": "Cancelled",
}


@frappe.whitelist()
def create_payment_order(payment_request_name):
	"""
	Create a Razorpay order for the given Payment Request.
	Stores razorpay_order_id, sets status=Requested, gateway_status=created.
	Returns order_id, amount, currency, key_id for frontend checkout.
	"""
	try:
		pr = frappe.get_doc("SLCM Payment Request", payment_request_name)
	except Exception:
		frappe.throw(_("Payment Request not found: {0}").format(payment_request_name))

	if pr.docstatus != 1:
		frappe.throw(_("Payment Request must be submitted before creating an order."))

	if pr.status == "Paid":
		frappe.throw(_("This payment has already been completed."))

	if pr.status == "Cancelled":
		frappe.throw(_("This payment request has been cancelled."))

	gateway = pr.payment_gateway or frappe.db.get_value("Payment Gateway", {}, "name") or "Razorpay"
	controller = _get_controller(gateway)

	# Build payment_details for create_order (amount in paise for Razorpay)
	amount = frappe.utils.flt(pr.amount, precision=2)
	payment_details = {
		"amount": amount,
		"title": _("Payment"),
		"description": _("Payment for {0} - {1}").format(pr.reference_doctype, pr.reference_name),
		"reference_doctype": pr.reference_doctype,
		"reference_docname": pr.reference_name,
		"payer_email": pr.email_to or "",
		"payer_name": pr.email_to or "",
		"currency": pr.currency or frappe.defaults.get_global_default("currency") or "INR",
		"receipt": (payment_request_name[:40]) if payment_request_name else None,
	}

	order = controller.create_order(**payment_details)
	if not order or not order.get("id"):
		frappe.throw(_("Order creation failed. Please check gateway logs."))

	# Update Payment Request: store order id, set status and gateway_status (backend only)
	frappe.flags.payment_request_status_from_backend = True
	pr.db_set("razorpay_order_id", order.get("id"))
	pr.db_set("status", "Requested")
	pr.db_set("gateway_status", "created")
	if order.get("amount"):
		pr.db_set("gateway_response", json.dumps(order, indent=2))
	frappe.db.commit()
	del frappe.flags.payment_request_status_from_backend

	return {
		"order_id": order.get("id"),
		"amount": order.get("amount"),
		"currency": order.get("currency", "INR"),
		"key_id": getattr(controller, "api_key", None) or frappe.conf.get("razorpay_key"),
	}


@frappe.whitelist(allow_guest=True)
def razorpay_webhook():
	"""
	Razorpay webhook endpoint. Must be called with POST; no auth (Razorpay signs payload).
	Validates HMAC, parses event, updates Payment Request by razorpay_order_id,
	applies status mapping, and on payment.captured triggers seat lock.
	Idempotent: if webhook_received is already 1 for this doc, skip duplicate processing.
	"""
	if frappe.request.method != "POST":
		frappe.respond_as_web_page(
			_("Invalid Request"),
			_("Method not allowed"),
			http_status_code=405,
		)
		return

	raw_body = frappe.request.get_data(as_text=True)
	if not raw_body:
		frappe.respond_as_web_page(
			_("Bad Request"),
			_("Empty body"),
			http_status_code=400,
		)
		return

	signature = frappe.request.headers.get("X-Razorpay-Signature") or ""
	if not signature:
		_log_webhook("rejected", "missing X-Razorpay-Signature", raw_body)
		frappe.respond_as_web_page(
			_("Bad Request"),
			_("Missing signature"),
			http_status_code=400,
		)
		return

	try:
		payload = json.loads(raw_body)
	except Exception as e:
		_log_webhook("rejected", "invalid JSON: {0}".format(str(e)), raw_body)
		frappe.respond_as_web_page(
			_("Bad Request"),
			_("Invalid JSON"),
			http_status_code=400,
		)
		return

	event = payload.get("event") or ""
	# Razorpay payload: payload.payment.entity has id, order_id, status, error_description
	payload_data = payload.get("payload") or {}
	payment_entity = (payload_data.get("payment") or {}).get("entity") or payload_data.get("payment") or payload.get("payment") or {}
	order_id = payment_entity.get("order_id") or (payload_data.get("order") or {}).get("id")

	# Log raw payload for audit
	_log_webhook("received", event or "unknown", raw_body)

	# Verify signature using webhook secret (or API secret fallback)
	webhook_secret = _get_webhook_secret()
	if not _verify_razorpay_webhook_signature(raw_body, signature, webhook_secret):
		_log_webhook("rejected", "invalid signature", raw_body)
		frappe.respond_as_web_page(
			_("Forbidden"),
			_("Invalid signature"),
			http_status_code=403,
		)
		return
	
	# Webhook event idempotency check
	event_id = payload.get("id")
	if event_id:
		cache_key = f"razorpay_webhook_event:{event_id}"
		if frappe.cache().get_value(cache_key):
			_log_webhook("ignored", f"Duplicate webhook event ID {event_id}", raw_body)
			frappe.response["http_status_code"] = 200
			return
		frappe.cache().set_value(cache_key, 1, expires_in_sec=86400)

	# Find Payment Request by razorpay_order_id (fallback: legacy rows only had transaction_id)
	pr_name = None
	if order_id:
		pr_name = frappe.db.get_value(
			"SLCM Payment Request",
			{"razorpay_order_id": order_id},
			"name",
		)
		if not pr_name:
			pr_name = frappe.db.get_value(
				"SLCM Payment Request",
				{"transaction_id": order_id},
				"name",
			)
	if not pr_name:
		frappe.log_error(
			message="Razorpay webhook: no Payment Request for order_id={0}".format(order_id),
			title="Razorpay Webhook Unknown Order",
		)
		# Return 200 so Razorpay does not retry
		frappe.response["http_status_code"] = 200
		return

	pr = frappe.get_doc("SLCM Payment Request", pr_name)

	# Idempotency: if already in a terminal state and we received a terminal webhook, skip duplicate
	terminal_states = ("captured", "failed", "refunded")
	gateway_status = _event_to_gateway_status(event, payment_entity)
	if pr.webhook_received and gateway_status in terminal_states:
		frappe.response["http_status_code"] = 200
		return

	# Persist full gateway payload for audit
	pr.db_set("gateway_response", raw_body if isinstance(raw_body, str) else json.dumps(payload, indent=2))

	# Map gateway event to gateway_status and system status
	system_status = GATEWAY_TO_SYSTEM_STATUS.get(gateway_status) or pr.status

	payment_id = payment_entity.get("id") or ""
	failure_msg = None
	if gateway_status == "failed":
		failure_msg = payment_entity.get("error_description") or payment_entity.get("error_code") or _("Payment failed")

	frappe.flags.payment_request_status_from_backend = True
	pr.db_set("gateway_status", gateway_status)
	pr.db_set("razorpay_payment_id", payment_id or pr.razorpay_payment_id)
	if failure_msg:
		pr.db_set("failure_message", failure_msg)
	pr.db_set("status", system_status)
	if gateway_status == "captured":
		pr.db_set("paid_on", frappe.utils.now_datetime())
		if payment_id:
			# Align with client verify path so Applicant Payment Receipt can link Payment Request
			pr.db_set("transaction_id", payment_id)
	# Mark webhook received for terminal states to prevent duplicate processing
	if gateway_status in terminal_states:
		pr.db_set("webhook_received", 1)
	frappe.db.commit()
	del frappe.flags.payment_request_status_from_backend

	if gateway_status == "captured":
		# Trigger seat lock / admission confirmation (Offer Letter only)
		try:
			from slcm.admission.seat_lock import lock_seat_after_payment
			lock_seat_after_payment(frappe.get_doc("SLCM Payment Request", pr_name))
		except Exception as e:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=_("Seat Lock After Payment Failed"),
			)
		# Application fee: Applicant-linked Payment Request → receipt + applicant status
		try:
			from slcm.api.service.fee_service import FeeService
			FeeService.sync_application_fee_after_gateway_capture(pr_name)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=_("Application Fee Webhook Sync Failed"),
			)

		# PACE payment: PACE Applicant Fee Assignment-linked Payment Request → receipt + application status
		try:
			from slcm.pace.api.service.pace_payment import sync_pace_payment_after_gateway_capture
			sync_pace_payment_after_gateway_capture(pr_name)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=_("PACE Payment Webhook Sync Failed"),
			)

	frappe.response["http_status_code"] = 200


def _get_controller(gateway):
	from payments.utils import get_payment_gateway_controller
	return get_payment_gateway_controller(gateway)


def _get_webhook_secret():
	"""Webhook secret for Razorpay HMAC verification. Prefer webhook_secret; fallback to API secret."""
	gateway = frappe.db.get_value("Payment Gateway", {}, "name") or "Razorpay"
	controller = _get_controller(gateway)
	try:
		# Some setups store a separate webhook secret on the gateway
		secret = controller.get_password("webhook_secret")
		if secret:
			return secret
	except Exception:
		pass
	return controller.get_password("api_secret")


def _verify_razorpay_webhook_signature(body, signature, secret):
	if not secret:
		return False
	expected = hmac.new(
		secret.encode("utf-8") if isinstance(secret, str) else secret,
		body.encode("utf-8") if isinstance(body, str) else body,
		hashlib.sha256,
	).hexdigest()
	return hmac.compare_digest(expected, signature)


def _event_to_gateway_status(event, payment_entity):
	"""Map Razorpay webhook event to our gateway_status."""
	if not event:
		return ""
	ev = (event or "").lower()
	if "captured" in ev or (payment_entity and (payment_entity.get("status") == "captured")):
		return "captured"
	if "failed" in ev or (payment_entity and (payment_entity.get("status") == "failed")):
		return "failed"
	if "refunded" in ev:
		return "refunded"
	if "authorized" in ev:
		return "authorized"
	if "created" in ev or "order" in ev:
		return "created"
	return "created"


def _log_webhook(disposition, message, raw_body):
	frappe.logger().info("Razorpay webhook {0}: {1}".format(disposition, message))
	# Optionally log to Error Log for audit (without raising)
	try:
		frappe.log_error(
			message=message + "\n\nPayload (truncated): " + (raw_body[:2000] if raw_body else ""),
			title="Razorpay Webhook {0}".format(disposition),
		)
	except Exception:
		pass

import datetime
import frappe
import json
import hmac
import hashlib
import requests
from frappe import _
from frappe.utils import now_datetime


@frappe.whitelist(allow_guest=True)
def handle_razorpay_webhook():
	"""
	Endpoint for Razorpay Webhooks.
	URL: https://your-site.com/api/method/slcm.api.razorpay_webhook.handle_razorpay_webhook

	Handles:
	  - payment.captured  — marks PACE/Offer/Applicant payment as Paid if client verify missed it
	  - payment.authorized — late auth: capture then complete
	  - payment.failed    — marks PR Failed and syncs business doc status
	  - refund.processed
	  - refund.failed
	  - settlement.processed  — stores settlement data in FLE Payment Log
	"""

	# Read raw body ONCE — frappe.request.get_data() returns empty bytes on second call
	raw_data = frappe.request.get_data()

	# 1. Verify webhook signature — fail closed: a webhook that isn't
	#    configured with a secret must be rejected, never trusted.
	settings = frappe.get_single("Razorpay Settings")
	webhook_secret = settings.get_password("webhook_secret")

	if not webhook_secret:
		frappe.log_error(
			title="Razorpay Webhook: secret not configured",
			message="Rejected an incoming webhook because Razorpay Settings.webhook_secret is not set."
		)
		frappe.throw(_("Webhook is not configured"), frappe.PermissionError)

	razorpay_signature = frappe.get_request_header("X-Razorpay-Signature")

	if not razorpay_signature:
		frappe.throw(_("Missing Razorpay Signature Header"), frappe.PermissionError)

	secret_bytes = webhook_secret.encode("utf-8") if isinstance(webhook_secret, str) else webhook_secret

	expected_signature = hmac.new(
		secret_bytes,
		raw_data,
		hashlib.sha256
	).hexdigest()

	if not hmac.compare_digest(razorpay_signature, expected_signature):
		frappe.throw(_("Invalid Webhook Signature"), frappe.PermissionError)

	# 2. Parse JSON
	try:
		event_data = json.loads(raw_data)
	except Exception:
		frappe.logger().error("Razorpay Webhook: Invalid JSON received")
		return {"status": "error", "message": "Invalid JSON"}

	event = event_data.get("event")
	event_payload = event_data.get("payload", {})

	frappe.logger().info(f"Razorpay Webhook received: event={event}")

	# 3. Route by event type
	if event == "payment.captured":
		_handle_payment_captured_webhook(event_payload)

	elif event == "payment.authorized":
		_handle_payment_authorized_webhook(event_payload)

	elif event == "payment.failed":
		_handle_payment_failed_webhook(event_payload)

	elif event == "refund.processed":
		entity = event_payload.get("refund", {}).get("entity", {})
		handle_refund_processed(entity)

	elif event == "refund.failed":
		entity = event_payload.get("refund", {}).get("entity", {})
		handle_refund_failed(entity)

	elif event == "settlement.processed":
		entity = event_payload.get("settlement", {}).get("entity", {})
		handle_settlement_processed(entity)

	else:
		frappe.logger().info(f"Razorpay Webhook: Unhandled event type '{event}'")

	return {"status": "success"}


# ---------------------------------------------------------------------------
# Payment captured / failed handlers (PACE + Offer Letter flows)
# ---------------------------------------------------------------------------

def _resolve_pr_from_order_id(order_id):
	"""
	Look up Payment Request by razorpay_order_id (primary) then transaction_id (fallback).
	Returns (pr_name, reference_doctype, reference_name) or (None, None, None).
	"""
	if not order_id:
		return None, None, None

	pr_name = (
		frappe.db.get_value(
			"SLCM Payment Request",
			{"razorpay_order_id": order_id, "docstatus": ["!=", 2]},
			"name",
		) or
		frappe.db.get_value(
			"SLCM Payment Request",
			{"transaction_id": order_id, "docstatus": ["!=", 2]},
			"name",
		)
	)
	if not pr_name:
		return None, None, None

	ref_doctype, ref_name = frappe.db.get_value(
		"SLCM Payment Request", pr_name, ["reference_doctype", "reference_name"]
	)
	return pr_name, ref_doctype, ref_name


def _handle_payment_captured_webhook(event_payload):
	"""
	Razorpay payment.captured webhook handler for PACE, Offer Letter, and Applicant flows.
	"""
	payment = event_payload.get("payment", {}).get("entity", {})
	order_id = payment.get("order_id", "")
	payment_id = payment.get("id", "")

	if not order_id or not payment_id:
		frappe.logger().warning("Razorpay Webhook: payment.captured has no order_id or payment_id")
		return

	pr_name, ref_doctype, ref_name = _resolve_pr_from_order_id(order_id)

	if not pr_name:
		frappe.logger().info(
			f"Razorpay Webhook: payment.captured — no Payment Request found for order_id={order_id}. "
			f"May be handled by slcm.slcm.api (Re Exam / Fee Invoice flow)."
		)
		return

	if ref_doctype not in ("PACE Applicant Fee Assignment", "Offer Letter", "Applicant"):
		return

	frappe.logger().info(
		f"Razorpay Webhook: payment.captured — PR={pr_name}, doctype={ref_doctype}, ref={ref_name}, payment_id={payment_id}"
	)

	try:
		from slcm.api.service.razorpay_utils import complete_admission_payment_from_gateway

		complete_admission_payment_from_gateway(
			ref_doctype,
			ref_name,
			pr_name,
			order_id,
			payment_id,
			payment,
			gateway=frappe.db.get_value("SLCM Payment Request", pr_name, "payment_gateway"),
		)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Razorpay Webhook: payment.captured handler failed — {ref_doctype}/{ref_name}",
		)


def _handle_payment_authorized_webhook(event_payload):
	"""
	Late authorization: capture the authorized payment, then complete admission records.
	"""
	payment = event_payload.get("payment", {}).get("entity", {})
	order_id = payment.get("order_id", "")
	payment_id = payment.get("id", "")

	if not order_id or not payment_id:
		return

	pr_name, ref_doctype, ref_name = _resolve_pr_from_order_id(order_id)
	if not pr_name or ref_doctype not in ("PACE Applicant Fee Assignment", "Offer Letter", "Applicant"):
		return

	if frappe.db.get_value("SLCM Payment Request", pr_name, "status") == "Paid":
		return

	try:
		from slcm.api.service.razorpay_utils import (
			capture_authorized_payment,
			complete_admission_payment_from_gateway,
			get_expected_amount_paise,
			get_razorpay_client,
		)

		frappe.db.set_value(
			"SLCM Payment Request",
			pr_name,
			{
				"gateway_status": "authorized",
				"status": "Requested",
				"gateway_response": json.dumps(payment, indent=4),
			},
			update_modified=True,
		)

		expected_paise = get_expected_amount_paise(
			ref_doctype, ref_name, frappe.db.get_value("SLCM Payment Request", pr_name, "amount")
		)
		rzp_client = get_razorpay_client()
		captured = capture_authorized_payment(rzp_client, payment, expected_paise)
		if not captured or captured.get("status") != "captured":
			frappe.db.commit()
			frappe.logger().info(
				f"Razorpay Webhook: payment.authorized — capture pending for PR={pr_name}"
			)
			return

		complete_admission_payment_from_gateway(
			ref_doctype,
			ref_name,
			pr_name,
			order_id,
			payment_id,
			captured,
			gateway=frappe.db.get_value("SLCM Payment Request", pr_name, "payment_gateway"),
		)
		frappe.logger().info(
			f"Razorpay Webhook: payment.authorized — captured and completed PR={pr_name}"
		)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Razorpay Webhook: payment.authorized handler failed — PR={pr_name}",
		)


def _handle_payment_failed_webhook(event_payload):
	"""
	Razorpay payment.failed webhook handler for PACE and Offer Letter flows.
	Updates Payment Request status to Failed for audit trail.
	"""
	payment = event_payload.get("payment", {}).get("entity", {})
	order_id = payment.get("order_id", "")
	payment_id = payment.get("id", "")
	error_desc = payment.get("error_description") or payment.get("error_reason") or "Payment failed at gateway"

	if not order_id:
		return

	pr_name, ref_doctype, ref_name = _resolve_pr_from_order_id(order_id)

	if not pr_name:
		return

	if ref_doctype not in ("PACE Applicant Fee Assignment", "Offer Letter", "Applicant"):
		return

	try:
		current_status, current_gateway_status = frappe.db.get_value(
			"SLCM Payment Request", pr_name, ["status", "gateway_status"]
		)
		if current_status == "Paid":
			return  # Don't overwrite a successful payment

		if current_gateway_status in ("authorized", "captured"):
			frappe.logger().info(f"Razorpay Webhook: PR={pr_name} is already {current_gateway_status}. Ignoring failed webhook.")
			return

		frappe.db.set_value(
			"SLCM Payment Request",
			pr_name,
			{
				"status": "Failed",
				"failure_message": error_desc,
				"gateway_status": "failed",
				"gateway_response": json.dumps(payment, indent=4),
			},
			update_modified=True,
		)
		from slcm.api.service.razorpay_utils import sync_business_doc_on_payment_failed
		sync_business_doc_on_payment_failed(ref_doctype, ref_name, error_desc)
		frappe.db.commit()
		frappe.logger().info(
			f"Razorpay Webhook: payment.failed — PR={pr_name} marked Failed. Order={order_id}"
		)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Razorpay Webhook: payment.failed handler failed — PR={pr_name}",
		)


# ---------------------------------------------------------------------------
# Settlement handler
# ---------------------------------------------------------------------------

def handle_settlement_processed(payload):
	"""
	When Razorpay fires settlement.processed:
	  1. Extract settlement metadata (id, utr, date, fees, tax).
	  2. Fetch per-payment recon from /v1/settlements/{id}/recon/combined.
	  3. Update FLE Payment Log records with settlement data so the
	     FLE Payment Journal report can read them without live API calls.
	"""
	settlement_id = payload.get("id")
	if not settlement_id:
		frappe.logger().warning("Razorpay Webhook: settlement.processed has no id in payload")
		return

	utr              = payload.get("utr") or ""
	settlement_status = payload.get("status") or "processed"
	created_at       = payload.get("created_at")
	settlement_date  = None
	if created_at:
		try:
			settlement_date = datetime.datetime.utcfromtimestamp(int(created_at)).date()
		except Exception:
			pass

	# Batch-level fee/tax (paise → rupees)
	batch_fees = round((payload.get("fees") or 0) / 100, 2)
	batch_tax  = round((payload.get("tax") or 0) / 100, 2)

	# Fetch credentials for recon API call
	settings   = frappe.get_single("Razorpay Settings")
	api_key    = settings.api_key
	api_secret = settings.get_password("api_secret")

	if not api_key or not api_secret:
		frappe.logger().error("Razorpay Webhook: API credentials not configured in Razorpay Settings")
		return

	settlement_payload = {
		"id": settlement_id,
		"utr": utr,
		"status": settlement_status,
		"settlement_date": settlement_date,
	}

	# Fetch per-payment recon (paginated; max 1000 per call)
	recon_items = _fetch_settlement_recon(settlement_id, api_key, api_secret)

	updated = 0
	for item in recon_items:
		# Only process payment credits (not refund debits)
		if item.get("type") not in ("payment", None):
			continue

		rzp_payment_id = item.get("razorpay_payment_id") or item.get("entity_id") or ""
		if not rzp_payment_id:
			continue

		# Try FLE Payment Log first
		log_name = frappe.db.get_value(
			"FLE Payment Log",
			{"transaction_id": rzp_payment_id},
			"name"
		)
		target_doctype = "FLE Payment Log"

		if not log_name:
			# Try Payment Request
			log_name = frappe.db.get_value(
				"SLCM Payment Request",
				{"razorpay_payment_id": rzp_payment_id, "status": "Paid"},
				"name"
			)
			if not log_name:
				log_name = frappe.db.get_value(
					"SLCM Payment Request",
					{"transaction_id": rzp_payment_id, "status": "Paid"},
					"name"
				)
			target_doctype = "SLCM Payment Request"

		if not log_name:
			continue

		complete_payment_settlement(target_doctype, log_name, item, settlement_payload)
		updated += 1

	frappe.logger().info(
		f"Razorpay settlement {settlement_id} (UTR: {utr}): updated {updated} FLE Payment Log records."
	)

def complete_payment_settlement(target_doctype, log_name, item, settlement_payload):
	"""Shared helper to update Payment Request or FLE Payment Log with settlement data."""
	import json
	gross_paise  = int(item.get("amount") or 0)
	fee_paise    = int(item.get("fee") or 0)
	tax_paise    = int(item.get("tax") or 0)
	net_paise    = int(item.get("credit") or 0)

	gateway_status = settlement_payload.get("status") or "processed"

	fields_to_update = {
		"settlement_id":     settlement_payload.get("id"),
		"settlement_utr":    settlement_payload.get("utr") or "",
		"settlement_date":   settlement_payload.get("settlement_date"),
		"gateway_fees":      round(fee_paise / 100, 2),
		"gateway_tax":       round(tax_paise / 100, 2),
		"net_settled":       round(net_paise / 100, 2) if net_paise else round((gross_paise - fee_paise - tax_paise) / 100, 2),
	}

	if target_doctype == "SLCM Payment Request":
		fields_to_update["settlement_amount"] = round(gross_paise / 100, 2)
		fields_to_update["settlement_response"] = json.dumps(item, indent=4)
		fields_to_update["gateway_settlement_status"] = gateway_status
		
		# Map to Payment Request internal select options
		if gateway_status == "processed":
			fields_to_update["settlement_status"] = "Settled"
		elif gateway_status == "created":
			fields_to_update["settlement_status"] = "Processing"
		elif gateway_status == "failed":
			fields_to_update["settlement_status"] = "Failed"
		else:
			fields_to_update["settlement_status"] = "Pending"
	else:
		fields_to_update["settlement_status"] = gateway_status

	frappe.db.set_value(target_doctype, log_name, fields_to_update)



def _fetch_settlement_recon(settlement_id, api_key, api_secret):
	"""Fetch all recon items for a settlement (handles pagination)."""
	items = []
	skip  = 0
	count = 500

	while True:
		url  = f"https://api.razorpay.com/v1/settlements/{settlement_id}/recon/combined"
		resp = requests.get(
			url,
			auth=(api_key, api_secret),
			params={"count": count, "skip": skip},
			timeout=30
		)
		if resp.status_code != 200:
			frappe.logger().error(
				f"Razorpay recon API error for {settlement_id}: {resp.status_code} {resp.text[:200]}"
			)
			break

		data  = resp.json()
		batch = data.get("items") or []
		items.extend(batch)

		if len(batch) < count:
			break  # last page
		skip += count

	return items


# ---------------------------------------------------------------------------
# Refund handlers (unchanged)
# ---------------------------------------------------------------------------

def handle_refund_processed(payload):
	"""
	Syncs SLCM when Razorpay confirms successful processing.
	"""
	rzp_refund_id = payload.get("id")
	if not rzp_refund_id:
		frappe.logger().warning("Razorpay Webhook: refund.processed has no refund ID in payload")
		return

	txn_name = frappe.db.get_value(
		"Refund Transaction",
		{"razorpay_refund_id": rzp_refund_id},
		"name"
	)

	if not txn_name:
		frappe.logger().warning(f"Razorpay Webhook: No Refund Transaction found for refund ID {rzp_refund_id}")
		return

	txn = frappe.get_doc("Refund Transaction", txn_name)
	txn.db_set("status", "Processed")
	if payload.get("created_at"):
		from frappe.utils import format_datetime, get_datetime
		payload["processed_date"] = format_datetime(get_datetime(payload.get("created_at")))

	txn.db_set("gateway_response", json.dumps(payload, indent=4))

	refund = frappe.get_doc("Refund Request", txn.refund_request)

	# Duplicate Safety — avoid processing twice
	if refund.status == "Processed":
		frappe.logger().info(f"Refund {refund.name} already Processed — skipping duplicate webhook.")
		return

	refund.db_set("status", "Processed")
	refund.db_set("refund_date", now_datetime())
	refund.db_set("failure_message", "")

	refund.sync_cancellation_status()

	frappe.logger().info(f"Refund {refund.name} marked as Processed via Webhook.")


def handle_refund_failed(payload):
	"""
	Handles refund failure notifications from Razorpay.
	"""
	rzp_refund_id = payload.get("id")
	if not rzp_refund_id:
		frappe.logger().warning("Razorpay Webhook: refund.failed has no refund ID in payload")
		return

	txn_name = frappe.db.get_value(
		"Refund Transaction",
		{"razorpay_refund_id": rzp_refund_id},
		"name"
	)

	if not txn_name:
		frappe.logger().warning(f"Razorpay Webhook: No Refund Transaction found for failed refund ID {rzp_refund_id}")
		return

	txn = frappe.get_doc("Refund Transaction", txn_name)
	txn.db_set("status", "Failed")
	if payload.get("created_at"):
		from frappe.utils import format_datetime, get_datetime
		payload["processed_date"] = format_datetime(get_datetime(payload.get("created_at")))

	txn.db_set("gateway_response", json.dumps(payload, indent=4))

	refund = frappe.get_doc("Refund Request", txn.refund_request)

	refund.db_set("status", "Failed")
	refund.db_set(
		"failure_message",
		payload.get("error_description", _("Refund failed at gateway."))
	)

	if refund.admission_cancellation:
		frappe.db.set_value(
			"Admission Cancellation",
			refund.admission_cancellation,
			"status",
			"Approved"
		)
	else:
		frappe.logger().warning(
			f"Refund {refund.name} has no linked admission_cancellation — skipping status revert."
		)

	frappe.logger().error(
		f"Refund {refund.name} failed via Webhook: {payload.get('error_description')}"
	)

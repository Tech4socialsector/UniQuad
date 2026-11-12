# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Easebuzz settlements (payouts) on SLCM Payment Requests.

Easebuzz pays captured money out to the bank in payouts. Each payout lists the transactions it
settled with Easebuzz's charges, GST and the net amount. This module writes those figures on the
Easebuzz SLCM Payment Requests, in the same fields the Razorpay settlement sync fills
(slcm.api.razorpay_webhook.complete_payment_settlement), so the Payment Settlement Report and the
ERPNext bridge treat both gateways alike.

API (Easebuzz Payment Gateway → Settlement APIs, as used by Easebuzz's own PHP kit):
POST {dashboard}/settlements/v1/retrieve, JSON
	{"merchant_key", "hash": sha512(merchant_key|start_date|end_date|salt),
	 "payout_date": {"start_date": "DD-MM-YYYY", "end_date": "DD-MM-YYYY"}}

Requests are matched on the Easebuzz payment id (``peb_transaction_id`` = easepayid, stored as
gateway_payment_id / transaction_id) and then on our txnid (gateway_order_id).
"""

import datetime
import json

import frappe
import requests
from frappe import _
from frappe.utils import add_days, flt, get_datetime, getdate, now_datetime, today

PR = "SLCM Payment Request"
EASEBUZZ = "Easebuzz"
LOOKBACK_DAYS = 10  # payouts land T+1..T+3; the margin covers bank holidays and a missed run
WINDOW_DAYS = 7  # one API call per week of payout dates
MAX_PAGES = 50
TIMEOUT = 30


def _settings():
	"""Easebuzz Settings with credentials, or None. Settlements are read even when checkout is disabled,
	so payments taken before switching it off still get settled."""
	if not frappe.db.exists("DocType", "Easebuzz Settings"):
		return None
	settings = frappe.get_single("Easebuzz Settings")
	try:
		return settings, settings.get_salt()
	except frappe.ValidationError:
		frappe.clear_last_message()
		return None


def _hash(key, start, end, salt):
	from payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings import sha512

	return sha512("|".join([key, start, end, salt]))


def fetch_payouts(start_date, end_date):
	"""Payouts Easebuzz made between the two dates (inclusive), following pagination."""
	conf = _settings()
	if not conf:
		frappe.throw(_("Easebuzz Merchant Key and Salt are not configured in Easebuzz Settings."))
	settings, salt = conf
	start, end = getdate(start_date).strftime("%d-%m-%Y"), getdate(end_date).strftime("%d-%m-%Y")
	body = {
		"merchant_key": settings.merchant_key,
		"hash": _hash(settings.merchant_key, start, end, salt),
		"payout_date": {"start_date": start, "end_date": end},
	}
	base = settings.get_base_url("dashboard")
	url, payouts = f"{base}/settlements/v1/retrieve", []
	for _page in range(MAX_PAGES):
		try:
			resp = requests.post(url, json=body, headers={"Accept": "application/json"}, timeout=TIMEOUT)
			resp.raise_for_status()
			data = resp.json()
		except Exception as e:
			# never log the body: it carries the hash; the response carries bank details
			frappe.log_error(f"url: {url}\nerror: {type(e).__name__}", "Easebuzz settlement fetch failed")
			frappe.throw(_("Could not reach Easebuzz to read settlements. Please try again later."))
		rows = data.get("data") if isinstance(data, dict) else None
		if rows is None and isinstance(data, dict):
			rows = data.get("payouts_history_data")
		if not isinstance(rows, list):
			msg = (data.get("message") or data.get("error") or data.get("data")) if isinstance(data, dict) else ""
			frappe.log_error(f"{start} to {end}: {str(msg)[:300]}", "Easebuzz settlement fetch rejected")
			frappe.throw(_("Easebuzz did not return settlements: {0}").format(str(msg)[:200] or _("unknown error")))
		payouts.extend(rows)
		nxt = data.get("next")
		if not nxt or not str(nxt).startswith(base):
			break
		url = nxt
	return payouts


def _parse_date(value):
	"""Easebuzz sends "Nov-27-2024 10:33:29 AM" (v1) or an ISO timestamp (older payout API)."""
	if not value:
		return None
	value = str(value).strip()
	for fmt in ("%b-%d-%Y %I:%M:%S %p", "%b-%d-%Y"):
		try:
			return datetime.datetime.strptime(value, fmt)
		except ValueError:
			pass
	try:
		return get_datetime(value.replace("Z", "").replace("T", " ")[:19])
	except Exception:
		return None


def _mask(account):
	account = str(account or "")
	return ("XXXX" + account[-4:]) if len(account) > 4 else account


def _find_request(txn):
	for field, value in (
		("gateway_payment_id", txn.get("peb_transaction_id")),
		("transaction_id", txn.get("peb_transaction_id")),
		("gateway_order_id", txn.get("txnid")),
	):
		if value:
			name = frappe.db.get_value(
				PR, {"payment_gateway": EASEBUZZ, "docstatus": 1, "status": "Paid", field: value}, "name"
			)
			if name:
				return name
	return None


def apply_payouts(payouts):
	"""Write each settled transaction's payout on its Easebuzz request. Returns counts."""
	counts = {"settled": 0, "unchanged": 0, "not_found": 0}
	unmatched = []
	for payout in payouts or []:
		paid_out = bool(payout.get("paid_out"))
		settled_at = _parse_date(payout.get("payout_actual_date") or payout.get("payout_scheduled_date"))
		if paid_out and not settled_at:
			settled_at = now_datetime()
		summary = {
			"payout_id": payout.get("payout_id"),
			"payout_amount": payout.get("payout_amount"),
			"paid_out": paid_out,
			"payout_date": payout.get("payout_actual_date") or payout.get("payout_scheduled_date"),
			"bank_name": payout.get("bank_name"),
			"account_number": _mask(payout.get("account_number")),
			"bank_transaction_id": payout.get("bank_transaction_id"),
		}
		for refund in payout.get("peb_refunds") or []:
			from slcm.slcm.fee.payment_ledger import record_gateway_refund

			if record_gateway_refund(
				refund.get("peb_transaction_id"), refund.get("refund_id"), refund.get("refund_amount"),
				settled_at, source=f"Easebuzz payout {summary['payout_id']}",
			):
				counts["refunds"] = counts.get("refunds", 0) + 1
		for txn in payout.get("peb_transactions") or []:
			name = _find_request(txn)
			if not name:
				counts["not_found"] += 1
				unmatched.append(f"{txn.get('peb_transaction_id')} / {txn.get('txnid')} ₹{flt(txn.get('amount')):,.2f}")
				continue
			settled = paid_out and (txn.get("status") or "settled").lower() == "settled"
			status = "Settled" if settled else "Processing"
			current = frappe.db.get_value(PR, name, ["settlement_id", "settlement_status"], as_dict=True)
			if current.settlement_id == summary["payout_id"] and current.settlement_status == status:
				counts["unchanged"] += 1
				continue
			fees = flt(txn.get("peb_service_charge")) + flt(txn.get("express_transaction_service_charge"))
			tax = flt(txn.get("peb_service_tax")) + flt(txn.get("express_transaction_service_tax"))
			frappe.db.set_value(PR, name, {
				"settlement_id": summary["payout_id"],
				"settlement_utr": summary["bank_transaction_id"] or "",
				"settlement_date": settled_at,
				"settlement_amount": flt(txn.get("amount"), 2),
				"gateway_fees": flt(fees, 2),
				"gateway_tax": flt(tax, 2),
				"net_settled": flt(txn.get("peb_settlement_amount"), 2) or flt(flt(txn.get("amount")) - fees - tax, 2),
				"settlement_status": status,
				"gateway_settlement_status": "processed" if settled else "created",
				"settlement_response": json.dumps({"payout": summary, "transaction": txn}, indent=2, default=str),
			})
			counts["settled"] += 1
	if unmatched:
		# money Easebuzz settled that no SLCM request explains (another product on the account, or a gap)
		frappe.logger("slcm.easebuzz_settlement").info(f"payout transactions without an SLCM request: {unmatched[:50]}")
	return counts


def sync_range(from_date, to_date):
	"""Fetch and apply payouts week by week between the two dates. Returns counts."""
	start, end = getdate(from_date), min(getdate(to_date), getdate(today()))
	totals = {"settled": 0, "unchanged": 0, "not_found": 0, "refunds": 0}
	while start <= end:
		stop = min(add_days(start, WINDOW_DAYS - 1), end)
		for k, v in apply_payouts(fetch_payouts(start, stop)).items():
			totals[k] = totals.get(k, 0) + v
		frappe.db.commit()
		start = add_days(stop, 1)
	return totals


def _has_unsettled():
	return frappe.db.exists(PR, {
		"payment_gateway": EASEBUZZ, "docstatus": 1, "status": "Paid",
		"settlement_status": ("in", ["", "Pending", "Processing"]),
	}) or frappe.db.exists(PR, {
		"payment_gateway": EASEBUZZ, "docstatus": 1, "status": "Paid", "settlement_status": ("is", "not set"),
	})


def daily_sync():
	"""Scheduler (daily): settle Easebuzz requests from the last LOOKBACK_DAYS of payouts."""
	if not _settings() or not _has_unsettled():
		return
	try:
		sync_range(add_days(today(), -LOOKBACK_DAYS), today())
	except Exception:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Easebuzz daily settlement sync failed")


@frappe.whitelist()
def sync_for_request(pr_name):
	"""Desk button on an Easebuzz SLCM Payment Request: look for its payout."""
	frappe.has_permission(PR, "write", pr_name, throw=True)
	pr = frappe.db.get_value(
		PR, pr_name, ["payment_gateway", "status", "docstatus", "paid_on", "creation", "settlement_status"], as_dict=True
	)
	if not pr or pr.payment_gateway != EASEBUZZ:
		frappe.throw(_("This is not an Easebuzz payment."))
	if pr.docstatus != 1 or pr.status != "Paid":
		frappe.throw(_("Only paid requests are settled."))
	paid = getdate(pr.paid_on or pr.creation)
	sync_range(paid, add_days(paid, LOOKBACK_DAYS))
	status = frappe.db.get_value(PR, pr_name, "settlement_status")
	if status == "Settled":
		return {"status": "success", "message": _("Settlement found. Status: Settled.")}
	if status == "Processing":
		return {"status": "info", "message": _("Easebuzz has scheduled this payout but not paid it out yet.")}
	return {"status": "info", "message": _("This payment has not been included in an Easebuzz settlement yet.")}


@frappe.whitelist()
def sync_dates(from_date, to_date):
	"""Desk: re-read Easebuzz payouts for a date range (e.g. after a long outage)."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	if getdate(from_date) > getdate(to_date):
		frappe.throw(_("From Date must be on or before To Date."))
	if (getdate(to_date) - getdate(from_date)).days > 92:
		frappe.throw(_("Pick at most three months at a time."))
	return sync_range(from_date, to_date)

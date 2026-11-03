"""
Admission Payment Settlement Report

Fetches live settlement and payment data from Razorpay API.

API calls:
  GET /v1/settlements                    – settlement list (supports date filters)
  GET /v1/settlements/recon/combined     – payment items per month (year + month params)

One row per payment item inside a settlement.
Falls back to one settlement-level row when recon returns no items.

Auth priority:
  1. Razorpay Settings DocType (api_key / api_secret)
  2. site_config.json  (razorpay_api_key / razorpay_api_secret)
"""

import json
from datetime import datetime, timezone

import frappe
import requests
from frappe import _

RAZORPAY_BASE   = "https://api.razorpay.com/v1"
PAGE_SIZE       = 10
RECON_PAGE_SIZE = 1000


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    try:
        data, summary = get_data(filters)
    except frappe.ValidationError:
        raise
    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "Admission Payment Settlement Report")
        frappe.throw(
            _("Razorpay API error: {0}").format(str(exc)),
            title=_("API Error"),
        )
    message = build_summary(summary) if summary else None
    return columns, data, message


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

def get_columns():
    return [
        {"label": _("Settlement ID"),        "fieldname": "settlement_id",      "fieldtype": "Data",     "width": 200},
        {"label": _("Transaction ID"),       "fieldname": "transaction_id",     "fieldtype": "Data",     "width": 200},
        {"label": _("Currency"),             "fieldname": "currency",           "fieldtype": "Data",     "width":  70},
        {"label": _("Amount (₹)"),           "fieldname": "amount",             "fieldtype": "Currency", "width": 130},
        {"label": _("Fees (₹)"),             "fieldname": "fees",               "fieldtype": "Currency", "width": 110},
        {"label": _("Tax (₹)"),              "fieldname": "tax",                "fieldtype": "Currency", "width": 100},
        {"label": _("Net Amount (₹)"),       "fieldname": "net_amount",         "fieldtype": "Currency", "width": 130},
        {"label": _("Payment Method"),       "fieldname": "payment_method",     "fieldtype": "Data",     "width": 130},
        {"label": _("Payment Notes"),        "fieldname": "payment_notes",      "fieldtype": "Data",     "width": 210},
        {"label": _("Contact Name"),         "fieldname": "contact_name",       "fieldtype": "Data",     "width": 160},
        {"label": _("Debit"),               "fieldname": "debit",              "fieldtype": "Currency", "width": 120},
        {"label": _("Credit"),              "fieldname": "credit",             "fieldtype": "Currency", "width": 120},
        {"label": _("Status"),              "fieldname": "status",             "fieldtype": "Data",     "width": 110},
        {"label": _("UTR"),                 "fieldname": "utr",                "fieldtype": "Data",     "width": 170},
        {"label": _("Entity Created At"),    "fieldname": "entity_created_at",  "fieldtype": "Datetime", "width": 160},
        {"label": _("Payment Captured At"),  "fieldname": "payment_captured_at","fieldtype": "Datetime", "width": 165},
        {"label": _("Settlement Created"),   "fieldname": "created_date",       "fieldtype": "Datetime", "width": 155},
        {"label": _("Settlement Processed"), "fieldname": "processed_date",     "fieldtype": "Datetime", "width": 165},
    ]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def get_data(filters):
    auth = get_credentials()
    from_ts, to_ts = date_to_unix(filters.get("from_date"), filters.get("to_date"))
    status_filter  = (filters.get("status") or "").strip().lower()

    settlements = fetch_settlements(auth, from_ts, to_ts)
    if not settlements:
        frappe.msgprint(_("No settlements found for the selected date range."), alert=True, indicator="blue")
        return [], {}

    setl_by_id  = {s["id"]: s for s in settlements if s.get("id")}
    setl_by_utr = {s["utr"]: s["id"] for s in settlements if s.get("utr")}

    year_months = resolve_year_months(filters.get("from_date"), filters.get("to_date"), settlements)
    recon_items = fetch_recon(auth, set(setl_by_id.keys()), year_months)

    local_map = build_local_map()

    rows = []
    totals = {"amount": 0.0, "fees": 0.0, "tax": 0.0, "net": 0.0}
    matched = set()

    for item in recon_items:
        sid = item.get("settlement_id") or setl_by_utr.get(item.get("settlement_utr", "")) or ""
        s   = setl_by_id.get(sid) or {}
        utr    = item.get("settlement_utr") or s.get("utr") or ""
        status = "settled" if utr else "pending"
        if status_filter and status != status_filter:
            continue

        entity_id      = item.get("entity_id") or item.get("payment_id") or ""
        transaction_id = item.get("payment_id") or entity_id
        amount  = to_inr(item.get("amount", 0))
        fees    = to_inr(item.get("fee",    0))
        tax     = to_inr(item.get("tax",    0))
        net     = round(amount - fees - tax, 2)
        r_debit  = to_inr(item.get("debit",  0))
        r_credit = to_inr(item.get("credit", 0))
        debit  = r_debit  if r_debit  else amount
        credit = r_credit if r_credit else net

        local          = local_map.get(transaction_id) or local_map.get(entity_id) or {}
        notes_from_api = item.get("description") or item.get("order_receipt") or ""

        totals["amount"] += amount
        totals["fees"]   += fees
        totals["tax"]    += tax
        totals["net"]    += net
        matched.add(sid)

        rows.append(make_row(
            sid, transaction_id, 
            amount, fees, tax, net, debit, credit,
            local.get("payment_method", ""),
            notes_from_api or local.get("payment_notes", ""),
            local.get("contact_name", ""),
            status.capitalize(), utr,
            to_dt(item.get("created_at")),
            to_dt(item.get("posted_at") or item.get("settled_at")),
            to_dt(s.get("created_at")),
            to_dt(s.get("settlement_time") or s.get("created_at")),
        ))

    # Fallback: settlements with no recon items
    for s in settlements:
        sid = s.get("id", "")
        if sid in matched:
            continue
        utr    = s.get("utr") or ""
        status = "settled" if utr else "pending"
        if status_filter and status != status_filter:
            continue
        amount = to_inr(s.get("amount", 0))
        fees   = to_inr(s.get("fees",   0))
        tax    = to_inr(s.get("tax",    0))
        net    = round(amount - fees - tax, 2)
        totals["amount"] += amount
        totals["fees"]   += fees
        totals["tax"]    += tax
        totals["net"]    += net
        rows.append(make_row(
            sid, "", amount, fees, tax, net, amount, net,
            "", "", "", 
            status.capitalize(), utr,
            None, None,
            to_dt(s.get("created_at")),
            to_dt(s.get("settlement_time") or s.get("created_at")),
        ))

    summary = {
        "count":  len(rows),
        "amount": round(totals["amount"], 2),
        "fees":   round(totals["fees"],   2),
        "tax":    round(totals["tax"],    2),
        "net":    round(totals["net"],    2),
    }
    return rows, summary


def make_row(sid, txn_id, amount, fees, tax, net, debit, credit,
             method, notes, contact, status, utr,
             entity_created_at, payment_captured_at, created_date, processed_date):
    return {
        "settlement_id":       sid,
        "transaction_id":      txn_id,
        "currency":            "INR",
        "amount":              amount,
        "fees":                fees,
        "tax":                 tax,
        "net_amount":          net,
        "payment_method":      method,
        "payment_notes":       notes,
        "contact_name":        contact,
        "debit":               debit,
        "credit":              credit,
        "status":              status,
        "utr":                 utr,
        "entity_created_at":   entity_created_at,
        "payment_captured_at": payment_captured_at,
        "created_date":        created_date,
        "processed_date":      processed_date,
    }


# ---------------------------------------------------------------------------
# Razorpay API
# ---------------------------------------------------------------------------

def fetch_settlements(auth, from_ts=None, to_ts=None):
    results, skip = [], 0
    while True:
        params = {"count": PAGE_SIZE, "skip": skip}
        if from_ts:
            params["from"] = from_ts
        if to_ts:
            params["to"] = to_ts
        resp = requests.get(f"{RAZORPAY_BASE}/settlements", auth=auth, params=params, timeout=30)
        check_error(resp)
        items = resp.json().get("items", [])
        results.extend(items)
        if len(items) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
    return results


def fetch_recon(auth, target_ids, year_months):
    """
    GET /v1/settlements/recon/combined requires year + month params.
    Iterates each year-month, deduplicates by entity_id, keeps only settled items.
    """
    seen, results = set(), []
    for year, month in year_months:
        skip = 0
        while True:
            resp = requests.get(
                f"{RAZORPAY_BASE}/settlements/recon/combined",
                auth=auth,
                params={"year": year, "month": month, "count": RECON_PAGE_SIZE, "skip": skip},
                timeout=60,
            )
            if resp.status_code == 404:
                return results
            check_error(resp)
            page = resp.json().get("items", [])
            for item in page:
                if item.get("settlement_id") not in target_ids:
                    continue
                eid = item.get("entity_id") or item.get("payment_id") or ""
                if eid in seen:
                    continue
                seen.add(eid)
                results.append(item)
            if len(page) < RECON_PAGE_SIZE:
                break
            skip += RECON_PAGE_SIZE
    return results


def check_error(resp):
    if resp.status_code == 401:
        frappe.throw(_("Razorpay authentication failed. Verify API Key and Secret in Razorpay Settings."), title=_("Auth Error"))
    if not resp.ok:
        frappe.throw(_("Razorpay error {0}: {1}").format(resp.status_code, resp.text[:300]), title=_("API Error"))


# ---------------------------------------------------------------------------
# Local enrichment from Payment Request
# ---------------------------------------------------------------------------

def build_local_map():
    if not frappe.db.table_exists("SLCM Payment Request"):
        return {}
    rows = frappe.db.sql("""
        SELECT razorpay_payment_id AS rzp_pid, transaction_id, reference_doctype, reference_name,
               gateway_response, email_to
        FROM `tabSLCM Payment Request`
        WHERE status = 'Paid'
          AND (razorpay_payment_id IS NOT NULL OR transaction_id IS NOT NULL)
    """, as_dict=True)
    result = {}
    for r in rows:
        pid = r.rzp_pid or r.transaction_id
        if not pid or pid in result:
            continue
        method, notes = parse_gateway(r.gateway_response, "")
        result[pid] = {
            "contact_name":   r.email_to or "",
            "student_id":     r.reference_name or "",
            "payment_method": method,
            "payment_notes":  f"{r.reference_doctype} - {r.reference_name}" + (" | " + notes if notes else ""),
        }
    return result


def parse_gateway(gw, upi):
    method, notes = "", upi or ""
    if not gw:
        return method, notes
    try:
        data   = json.loads(gw)
        entity = data.get("payload", {}).get("payment", {}).get("entity", data)
        method = entity.get("method") or ""
        parts  = [str(entity.get(k)) for k in ("bank", "wallet", "vpa", "description") if entity.get(k)]
        if parts:
            notes = " | ".join(parts)
    except Exception:
        pass
    return method.title() if method else "", notes


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def get_credentials():
    try:
        s = frappe.get_doc("Razorpay Settings")
        k, sec = s.api_key, s.get_password("api_secret")
        if k and sec:
            return (k, sec)
    except Exception:
        pass
    key = next((frappe.conf.get(a) for a in ("razorpay_api_key", "razorpay_key_id") if frappe.conf.get(a)), None)
    sec = next((frappe.conf.get(a) for a in ("razorpay_api_secret", "razorpay_key_secret") if frappe.conf.get(a)), None)
    if key and sec:
        return (key, sec)
    frappe.throw(
        _("Razorpay credentials not found. Set them in <b>Razorpay Settings</b> or site_config.json."),
        title=_("Missing Config"),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_inr(paise):
    try:
        return round(int(paise) / 100, 2)
    except (TypeError, ValueError):
        return 0.0


def to_dt(ts):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def date_to_unix(from_date, to_date):
    from_ts = to_ts = None
    if from_date:
        try:
            from_ts = int(datetime.strptime(str(from_date), "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            pass
    if to_date:
        try:
            to_ts = int(datetime.strptime(str(to_date), "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc).timestamp())
        except ValueError:
            pass
    return from_ts, to_ts


def resolve_year_months(from_date, to_date, settlements):
    ym = set()
    if from_date and to_date:
        try:
            s = datetime.strptime(str(from_date), "%Y-%m-%d")
            e = datetime.strptime(str(to_date),   "%Y-%m-%d")
            y, m = s.year, s.month
            while (y, m) <= (e.year, e.month):
                ym.add((y, m))
                m += 1
                if m > 12:
                    m, y = 1, y + 1
        except ValueError:
            pass
    if not ym:
        for s in settlements:
            ts = s.get("created_at")
            if ts:
                try:
                    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                    ym.add((dt.year, dt.month))
                except Exception:
                    pass
    return sorted(ym)


def build_summary(s):
    if not s.get("count"):
        return None
    return (
        f"<b>Summary</b><br>"
        f"Total Payments : {s['count']}<br>"
        f"Total Amount (₹) : {s['amount']:,.2f}<br>"
        f"Total Fees (₹) : {s['fees']:,.2f}<br>"
        f"Total Tax (₹) : {s['tax']:,.2f}<br>"
        f"Net Total (₹) : {s['net']:,.2f}"
    )

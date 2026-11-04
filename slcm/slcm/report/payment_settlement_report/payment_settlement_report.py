import frappe
from frappe import _
from frappe.utils import flt

NOT_SETTLED = "Not settled yet"


def execute(filters=None):
    filters = frappe._dict(filters or {})
    data = get_data(filters)
    return get_columns(), data, None, None, get_summary(data)


def get_columns():
    return [
        {"label": _("Payment Request"), "fieldname": "name", "fieldtype": "Link", "options": "SLCM Payment Request", "width": 150},
        {"label": _("Payment Gateway"), "fieldname": "payment_gateway", "fieldtype": "Data", "width": 120},
        {"label": _("Paid On"), "fieldname": "paid_on", "fieldtype": "Datetime", "width": 150},
        {"label": _("Email"), "fieldname": "email_to", "fieldtype": "Data", "width": 180},
        {"label": _("For"), "fieldname": "reference_doctype", "fieldtype": "Link", "options": "DocType", "width": 140},
        {"label": _("Reference"), "fieldname": "reference_name", "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 150},
        {"label": _("Transaction ID"), "fieldname": "transaction_id", "fieldtype": "Data", "width": 170},
        {"label": _("Method"), "fieldname": "payment_method", "fieldtype": "Data", "width": 100},
        {"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 110},
        {"label": _("Settlement Status"), "fieldname": "settlement_status", "fieldtype": "Data", "width": 130},
        {"label": _("Settlement / Payout ID"), "fieldname": "settlement_id", "fieldtype": "Data", "width": 170},
        {"label": _("UTR Number"), "fieldname": "settlement_utr", "fieldtype": "Data", "width": 160},
        {"label": _("Settled At"), "fieldname": "settlement_date", "fieldtype": "Datetime", "width": 150},
        {"label": _("Gateway Fees (INR)"), "fieldname": "gateway_fees", "fieldtype": "Currency", "width": 130},
        {"label": _("Gateway Tax (INR)"), "fieldname": "gateway_tax", "fieldtype": "Currency", "width": 130},
        {"label": _("Net Settled (INR)"), "fieldname": "net_settled", "fieldtype": "Currency", "width": 140},
    ]


def get_data(filters):
    # Only money actually received: submitted, paid requests (failed attempts have nothing to settle)
    conditions = ["docstatus = 1", "status = 'Paid'"]
    values = {}

    if filters.get("from_date"):
        conditions.append("paid_on >= %(from_date)s")
        values["from_date"] = f"{filters.from_date} 00:00:00"
    if filters.get("to_date"):
        conditions.append("paid_on <= %(to_date)s")
        values["to_date"] = f"{filters.to_date} 23:59:59"
    if filters.get("payment_gateway"):
        conditions.append("payment_gateway = %(payment_gateway)s")
        values["payment_gateway"] = filters.payment_gateway
    if filters.get("settlement_status") == NOT_SETTLED:
        conditions.append("ifnull(settlement_status, '') in ('', 'Pending')")
    elif filters.get("settlement_status"):
        conditions.append("settlement_status = %(settlement_status)s")
        values["settlement_status"] = filters.settlement_status

    data = frappe.db.sql(
        f"""
        SELECT
            name, payment_gateway, paid_on, email_to, reference_doctype, reference_name,
            transaction_id, payment_method, amount,
            settlement_status, settlement_id, settlement_utr, settlement_date,
            gateway_fees, gateway_tax, net_settled
        FROM `tabSLCM Payment Request`
        WHERE {" AND ".join(conditions)}
        ORDER BY paid_on DESC
        """,
        values,
        as_dict=True,
    )
    for row in data:
        row.settlement_status = row.settlement_status or NOT_SETTLED
    return data


def get_summary(data):
    settled = [r for r in data if r.settlement_status == "Settled"]
    waiting = [r for r in data if r.settlement_status != "Settled"]
    return [
        {"label": _("Collected"), "value": sum(flt(r.amount) for r in data), "datatype": "Currency", "indicator": "Blue"},
        {"label": _("Settled to bank (net)"), "value": sum(flt(r.net_settled) for r in settled), "datatype": "Currency", "indicator": "Green"},
        {"label": _("Gateway fees + tax"), "value": sum(flt(r.gateway_fees) + flt(r.gateway_tax) for r in settled), "datatype": "Currency", "indicator": "Grey"},
        {"label": _("Awaiting settlement"), "value": sum(flt(r.amount) for r in waiting), "datatype": "Currency",
         "indicator": "Orange" if waiting else "Green"},
    ]

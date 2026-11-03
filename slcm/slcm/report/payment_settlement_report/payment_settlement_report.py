import frappe
from frappe import _

def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("Email"), "fieldname": "email_to", "fieldtype": "Data", "width": 180},
        {"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Payment Gateway"), "fieldname": "payment_gateway", "fieldtype": "Data", "width": 140},
        {"label": _("Transaction ID"), "fieldname": "transaction_id", "fieldtype": "Data", "width": 160},
        {"label": _("Paid On"), "fieldname": "paid_on", "fieldtype": "Datetime", "width": 150},
        {"label": _("Settlement ID"), "fieldname": "settlement_id", "fieldtype": "Data", "width": 180},
        {"label": _("Settlement Status"), "fieldname": "settlement_status", "fieldtype": "Data", "width": 140},
        {"label": _("UTR Number"), "fieldname": "settlement_utr", "fieldtype": "Data", "width": 160},
        {"label": _("Settled At"), "fieldname": "settlement_date", "fieldtype": "Datetime", "width": 150},
        {"label": _("Gateway Fees (INR)"), "fieldname": "gateway_fees", "fieldtype": "Currency", "width": 140},
        {"label": _("Gateway Tax (INR)"), "fieldname": "gateway_tax", "fieldtype": "Currency", "width": 140},
        {"label": _("Net Settled (INR)"), "fieldname": "net_settled", "fieldtype": "Currency", "width": 140},
    ]

def get_data(filters):
    conditions = []
    
    if filters.get("from_date"):
        conditions.append(f"paid_on >= '{filters.get('from_date')} 00:00:00'")
    if filters.get("to_date"):
        conditions.append(f"paid_on <= '{filters.get('to_date')} 23:59:59'")
    if filters.get("settlement_status"):
        conditions.append(f"settlement_status = '{filters.get('settlement_status')}'")
        
    where_clause = " AND ".join(conditions) if conditions else "1=1"

    data = frappe.db.sql(f"""
        SELECT 
            email_to,
            amount,
            payment_gateway,
            transaction_id,
            paid_on,
            settlement_id,
            settlement_status,
            settlement_utr,
            settlement_date,
            gateway_fees,
            gateway_tax,
            net_settled
        FROM `tabSLCM Payment Request`
        WHERE {where_clause}
        ORDER BY paid_on DESC
    """, as_dict=True)

    return data

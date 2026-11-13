import frappe
from frappe.utils import flt, getdate


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Fee Component", "fieldname": "fee_component", "fieldtype": "Data", "width": 200},
        {"label": "Demand Type", "fieldname": "demand_type", "fieldtype": "Data", "width": 130},
        {"label": "Academic Year", "fieldname": "academic_year", "fieldtype": "Data", "width": 130},
        {"label": "Payment Mode", "fieldname": "payment_mode", "fieldtype": "Data", "width": 120},
        {"label": "No. of Receipts", "fieldname": "receipt_count", "fieldtype": "Int", "width": 120},
        {"label": "Total Collected (₹)", "fieldname": "total_collected", "fieldtype": "Currency", "width": 150},
    ]


def get_data(filters):
    # Fee Receipt is not submittable: a cancelled receipt keeps docstatus 0 with status "Cancelled"
    conditions = "r.docstatus != 2 AND IFNULL(r.status, '') != 'Cancelled'"

    if filters.get("from_date"):
        conditions += " AND r.receipt_date >= %(from_date)s"

    if filters.get("to_date"):
        conditions += " AND r.receipt_date <= %(to_date)s"

    if filters.get("academic_year"):
        conditions += " AND r.academic_year = %(academic_year)s"

    if filters.get("payment_mode"):
        conditions += " AND p.payment_mode = %(payment_mode)s"

    # What each receipt paid per demand (its allocation, so a receipt over three demands is counted once in total)
    demand_rows = frappe.db.sql(f"""
        SELECT
            d.fee_component,
            d.demand_type,
            r.academic_year,
            p.payment_mode,
            r.name AS receipt,
            pd.amount_allocated AS amount
        FROM `tabFee Receipt` r
        JOIN `tabFee Payment` p ON p.name = r.fee_payment
        JOIN `tabFee Payment Demand Row` pd ON pd.parent = p.name AND pd.parenttype = 'Fee Payment'
        JOIN `tabFee Demand` d ON d.name = pd.fee_demand
        WHERE {conditions}
    """, filters, as_dict=True)

    # Programme-fee (Fee Invoice) payments carry no demand rows
    invoice_rows = frappe.db.sql(f"""
        SELECT
            'Programme Fee (Fee Invoice)' AS fee_component,
            'Academic' AS demand_type,
            r.academic_year,
            p.payment_mode,
            r.name AS receipt,
            r.amount AS amount
        FROM `tabFee Receipt` r
        JOIN `tabFee Payment` p ON p.name = r.fee_payment
        WHERE {conditions}
          AND IFNULL(p.fee_invoice, '') != ''
          AND NOT EXISTS (SELECT 1 FROM `tabFee Payment Demand Row` pd
                          WHERE pd.parent = p.name AND pd.parenttype = 'Fee Payment')
    """, filters, as_dict=True)

    groups = {}
    for row in demand_rows + invoice_rows:
        key = (row.fee_component, row.demand_type, row.academic_year, row.payment_mode)
        g = groups.setdefault(key, {
            "fee_component": row.fee_component, "demand_type": row.demand_type,
            "academic_year": row.academic_year, "payment_mode": row.payment_mode,
            "receipts": set(), "total_collected": 0.0,
        })
        g["receipts"].add(row.receipt)
        g["total_collected"] += flt(row.amount)

    rows = []
    for g in groups.values():
        g["receipt_count"] = len(g.pop("receipts"))
        g["total_collected"] = flt(g["total_collected"], 2)
        rows.append(g)
    rows.sort(key=lambda g: (str(g["academic_year"] or ""), g["total_collected"]), reverse=True)
    return rows

import frappe
from frappe.utils import getdate, nowdate, date_diff


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Student ID", "fieldname": "student", "fieldtype": "Link", "options": "Student Master", "width": 130},
        {"label": "Student Name", "fieldname": "student_name", "fieldtype": "Data", "width": 160},
        {"label": "Programme", "fieldname": "programme", "fieldtype": "Data", "width": 130},
        {"label": "Academic Year", "fieldname": "academic_year", "fieldtype": "Data", "width": 120},
        {"label": "Demand ID", "fieldname": "name", "fieldtype": "Link", "options": "Fee Demand", "width": 140},
        {"label": "Fee Component", "fieldname": "fee_component", "fieldtype": "Data", "width": 180},
        {"label": "Demand Type", "fieldname": "demand_type", "fieldtype": "Data", "width": 120},
        {"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 100},
        {"label": "Days Overdue", "fieldname": "days_overdue", "fieldtype": "Int", "width": 110},
        {"label": "Aging Bucket", "fieldname": "aging_bucket", "fieldtype": "Data", "width": 120},
        {"label": "Net Payable", "fieldname": "net_payable", "fieldtype": "Currency", "width": 120},
        {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 120},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
    ]


def get_data(filters):
    as_of = getdate(filters.get("as_of_date") or nowdate())

    conditions = "d.outstanding_amount > 0 AND d.status NOT IN ('Paid', 'Waived', 'Cancelled')"

    if filters.get("academic_year"):
        conditions += " AND d.academic_year = %(academic_year)s"
    if filters.get("demand_type"):
        conditions += " AND d.demand_type = %(demand_type)s"
    if filters.get("student"):
        conditions += " AND d.student = %(student)s"
    if filters.get("programme"):
        conditions += " AND sm.programme_of_study = %(programme)s"

    rows = frappe.db.sql(f"""
        SELECT
            d.name,
            d.student,
            d.student_name,
            COALESCE(sm.programme_of_study, '') AS programme,
            d.academic_year,
            d.fee_component,
            d.demand_type,
            d.due_date,
            d.net_payable,
            d.outstanding_amount,
            d.status
        FROM `tabFee Demand` d
        LEFT JOIN `tabStudent Master` sm ON sm.name = d.student
        WHERE {conditions}
        ORDER BY d.due_date ASC, d.student ASC
    """, filters, as_dict=True)

    for row in rows:
        due = getdate(row.due_date)
        if due < as_of:
            row["days_overdue"] = date_diff(as_of, due)
        else:
            row["days_overdue"] = 0

        days = row["days_overdue"]
        if days == 0:
            row["aging_bucket"] = "Not Overdue"
        elif days <= 30:
            row["aging_bucket"] = "1 – 30 Days"
        elif days <= 60:
            row["aging_bucket"] = "31 – 60 Days"
        elif days <= 90:
            row["aging_bucket"] = "61 – 90 Days"
        else:
            row["aging_bucket"] = "90+ Days"

    # filter out "Not Overdue" unless explicitly requested
    if not filters.get("include_not_overdue"):
        rows = [r for r in rows if r["days_overdue"] > 0]

    return rows

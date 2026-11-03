import frappe
from frappe.utils import getdate, nowdate


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": "Source", "fieldname": "source", "fieldtype": "Data", "width": 110},
		{"label": "Date/Time", "fieldname": "timestamp", "fieldtype": "Datetime", "width": 160},
		{"label": "Student", "fieldname": "student", "fieldtype": "Link", "options": "Student Master", "width": 130},
		{"label": "Student Name", "fieldname": "student_name", "fieldtype": "Data", "width": 150},
		{"label": "Reference", "fieldname": "reference", "fieldtype": "Data", "width": 140},
		{"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 100},
		{"label": "Payment Mode / Gateway", "fieldname": "gateway", "fieldtype": "Data", "width": 140},
		{"label": "Paid By", "fieldname": "paid_by_role", "fieldtype": "Data", "width": 90},
		{"label": "Failure Reason", "fieldname": "failure_reason", "fieldtype": "Small Text", "width": 220},
		{"label": "Error Message", "fieldname": "error_message", "fieldtype": "Small Text", "width": 220},
		{"label": "Retry Count", "fieldname": "retry_count", "fieldtype": "Int", "width": 90},
		{"label": "Transaction ID", "fieldname": "transaction_id", "fieldtype": "Data", "width": 150},
		{"label": "Razorpay Payment ID", "fieldname": "razorpay_payment_id", "fieldtype": "Data", "width": 160},
		{"label": "Razorpay Order ID", "fieldname": "razorpay_order_id", "fieldtype": "Data", "width": 160},
		{"label": "Gateway Response", "fieldname": "gateway_response", "fieldtype": "Code", "width": 200},
	]


def get_data(filters):
	from_date = getdate(filters.get("from_date")) if filters.get("from_date") else None
	to_date = getdate(filters.get("to_date") or nowdate())

	rows = []
	rows.extend(_get_student_fee_payment_failures(filters, from_date, to_date))
	rows.extend(_get_payment_request_failures(filters, from_date, to_date))

	rows.sort(key=lambda r: r["timestamp"] or "", reverse=True)
	return rows


def _get_student_fee_payment_failures(filters, from_date, to_date):
	if filters.get("source") and filters.get("source") != "Fee Payment":
		return []

	conditions = "l.event_type = 'Payment Failed'"
	values = {"to_date": to_date}

	if from_date:
		conditions += " AND DATE(l.timestamp) >= %(from_date)s"
		values["from_date"] = from_date
	conditions += " AND DATE(l.timestamp) <= %(to_date)s"

	if filters.get("student"):
		conditions += " AND l.parent = %(student)s"
		values["student"] = filters.get("student")

	rows = frappe.db.sql(
		f"""
		SELECT
			'Fee Payment' AS source,
			l.timestamp AS timestamp,
			l.parent AS student,
			sm.first_name AS student_name,
			COALESCE(l.invoice, l.fee_demand, '') AS reference,
			l.amount AS amount,
			COALESCE(l.payment_method, l.payment_mode, '') AS gateway,
			l.paid_by_role AS paid_by_role,
			l.failure_reason AS failure_reason,
			l.error_message AS error_message,
			l.retry_count AS retry_count,
			l.transaction_id AS transaction_id,
			l.razorpay_payment_id AS razorpay_payment_id,
			l.razorpay_order_id AS razorpay_order_id,
			l.gateway_response AS gateway_response
		FROM `tabStudent Fee Payment Log` l
		LEFT JOIN `tabStudent Master` sm ON sm.name = l.parent
		WHERE {conditions}
		ORDER BY l.timestamp DESC
		""",
		values,
		as_dict=True,
	)
	return rows


def _get_payment_request_failures(filters, from_date, to_date):
	if filters.get("source") and filters.get("source") != "Payment Request":
		return []
	if filters.get("student"):
		return []

	conditions = "pr.status = 'Failed'"
	values = {"to_date": to_date}

	if from_date:
		conditions += " AND DATE(pr.modified) >= %(from_date)s"
		values["from_date"] = from_date
	conditions += " AND DATE(pr.modified) <= %(to_date)s"

	rows = frappe.db.sql(
		f"""
		SELECT
			'Payment Request' AS source,
			pr.modified AS timestamp,
			'' AS student,
			'' AS student_name,
			CONCAT(pr.reference_doctype, ': ', pr.reference_name) AS reference,
			pr.amount AS amount,
			COALESCE(pr.payment_gateway, pr.gateway_status, '') AS gateway,
			'' AS paid_by_role,
			pr.failure_message AS failure_reason,
			pr.failure_message AS error_message,
			0 AS retry_count,
			pr.transaction_id AS transaction_id,
			pr.razorpay_payment_id AS razorpay_payment_id,
			pr.razorpay_order_id AS razorpay_order_id,
			pr.gateway_response AS gateway_response
		FROM `tabSLCM Payment Request` pr
		WHERE {conditions}
		ORDER BY pr.modified DESC
		""",
		values,
		as_dict=True,
	)
	return rows

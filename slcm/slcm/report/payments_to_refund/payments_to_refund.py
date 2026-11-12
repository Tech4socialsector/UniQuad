# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Online student payments captured but not applied to any fee (duplicate payments, dues settled meanwhile,
cancelled requests or Fee Payments): the money to refund from the gateway dashboard, and what was recorded
as refunded (SLCM Payment Request → Record Refund)."""

import json

import frappe
from frappe import _
from frappe.utils import flt

from slcm.slcm.fee.payment_ledger import LEDGER_DOCTYPES, refundable_amount


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	pending = [r for r in data if r.to_refund > 0.01]
	summary = [
		{"label": _("Waiting for refund"), "value": len(pending), "datatype": "Int",
		 "indicator": "Orange" if pending else "Green"},
		{"label": _("Amount to refund"), "value": sum(r.to_refund for r in pending), "datatype": "Currency",
		 "indicator": "Orange" if pending else "Green"},
		{"label": _("Recorded as refunded"), "value": sum(flt(r.refunded_amount) for r in data), "datatype": "Currency",
		 "indicator": "Blue"},
	]
	return get_columns(), data, None, None, summary


def get_columns():
	return [
		{"label": _("Payment Request"), "fieldname": "name", "fieldtype": "Link", "options": "SLCM Payment Request", "width": 150},
		{"label": _("Gateway"), "fieldname": "payment_gateway", "fieldtype": "Data", "width": 100},
		{"label": _("Paid On"), "fieldname": "paid_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Student"), "fieldname": "student", "fieldtype": "Link", "options": "Student Master", "width": 140},
		{"label": _("Student Name"), "fieldname": "student_name", "fieldtype": "Data", "width": 160},
		{"label": _("Student ID"), "fieldname": "registration_id", "fieldtype": "Data", "width": 110},
		{"label": _("Payment ID"), "fieldname": "transaction_id", "fieldtype": "Data", "width": 170},
		{"label": _("Captured"), "fieldname": "amount", "fieldtype": "Currency", "width": 110},
		{"label": _("To Refund"), "fieldname": "to_refund", "fieldtype": "Currency", "width": 110},
		{"label": _("Refunded"), "fieldname": "refunded_amount", "fieldtype": "Currency", "width": 110},
		{"label": _("Refund Reference"), "fieldname": "refund_reference", "fieldtype": "Data", "width": 150},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 320},
	]


def get_data(filters):
	conditions = [
		"docstatus = 1", "status = 'Paid'", "reference_doctype in %(doctypes)s",
		"(gateway_response like '%%\"records\": []%%' or gateway_response like '%%\"unallocated\"%%'"
		" or ifnull(refunded_amount, 0) > 0)",
	]
	values = {"doctypes": tuple(LEDGER_DOCTYPES)}
	if filters.get("payment_gateway"):
		conditions.append("payment_gateway = %(payment_gateway)s")
		values["payment_gateway"] = filters.payment_gateway
	if filters.get("from_date"):
		conditions.append("paid_on >= %(from_date)s")
		values["from_date"] = f"{filters.from_date} 00:00:00"
	if filters.get("to_date"):
		conditions.append("paid_on <= %(to_date)s")
		values["to_date"] = f"{filters.to_date} 23:59:59"
	rows = frappe.db.sql(
		f"""select name, payment_gateway, paid_on, transaction_id, amount, refunded_amount, refund_reference,
			gateway_response
		from `tabSLCM Payment Request` where {" and ".join(conditions)} order by paid_on desc""",
		values,
		as_dict=True,
	)
	out = []
	for r in rows:
		r.to_refund = refundable_amount(r.name)
		if not filters.get("include_refunded") and r.to_refund <= 0.01:
			continue
		try:
			response = json.loads(r.pop("gateway_response") or "{}")
		except ValueError:
			response = {}
		r.student = response.get("student")
		r.student_name = response.get("student_name") or ""
		r.registration_id = response.get("registration_id") or ""
		r.reason = response.get("note") or (
			_("₹{0} captured beyond the dues").format(f"{flt(response.get('unallocated')):,.2f}")
			if response.get("unallocated") else ""
		)
		out.append(r)
	return out

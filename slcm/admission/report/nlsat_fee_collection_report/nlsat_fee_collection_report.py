# Copyright (c) 2026, SLCM and contributors
# For license information, please see license.txt

"""NLSAT Fee Collection Report.

Lists every NLSAT application-fee payment attempt (SLCM Payment Request raised
against an Applicant) in the layout of docs/application_report/Fee collection report.xlsx.

The shared query lives here and is reused by "Student Admission Fee Report",
which covers Confirmation / Admission Fee payments made against Offer Letters.
"""

import frappe
from frappe import _
from frappe.utils import flt

NOT_SETTLED = "Not settled yet"
OFFLINE_GATEWAY = "Manual Payment"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_fee_rows(filters, source="Applicant")
	return get_columns(), data, None, None, get_summary(data)


def get_columns(include_student_id=False):
	columns = []
	if include_student_id:
		columns.append(
			{"label": _("Student ID"), "fieldname": "student_id", "fieldtype": "Data", "width": 140}
		)
	columns += [
		{"label": _("Student Application Number"), "fieldname": "application_number", "fieldtype": "Link", "options": "Applicant", "width": 170},
		{"label": _("Student name"), "fieldname": "student_name", "fieldtype": "Data", "width": 180},
		{"label": _("Amount paid"), "fieldname": "amount_paid", "fieldtype": "Currency", "width": 110},
		{"label": _("Payment Date"), "fieldname": "payment_date", "fieldtype": "Datetime", "width": 150},
		{"label": _("Settlement Date"), "fieldname": "settlement_date", "fieldtype": "Datetime", "width": 150},
		{"label": _("Reference Number"), "fieldname": "reference_number", "fieldtype": "Data", "width": 180},
		{"label": _("Remarks / Description"), "fieldname": "remarks", "fieldtype": "Data", "width": 220},
		{"label": _("Fee Component"), "fieldname": "fee_component", "fieldtype": "Data", "width": 130},
		{"label": _("phone"), "fieldname": "phone", "fieldtype": "Data", "width": 130},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 90},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Data", "width": 110},
		{"label": _("Programme"), "fieldname": "programme", "fieldtype": "Link", "options": "Programme", "width": 140},
		{"label": _("Payment Status"), "fieldname": "payment_status", "fieldtype": "Data", "width": 110},
		{"label": _("Settlement Status"), "fieldname": "settlement_status", "fieldtype": "Data", "width": 130},
		{"label": _("Payment Request"), "fieldname": "payment_request", "fieldtype": "Link", "options": "SLCM Payment Request", "width": 150},
	]
	return columns


def get_fee_rows(filters, source):
	"""Return report rows.

	source = "Applicant"    -> application-fee payments (pr.reference_name is the Applicant)
	source = "Offer Letter" -> confirmation / admission-fee payments (pr.reference_name is the Offer Letter)
	"""
	values = {"reference_doctype": source}
	conditions = ["pr.reference_doctype = %(reference_doctype)s", "pr.docstatus < 2"]

	if source == "Offer Letter":
		joins = """
			INNER JOIN `tabOffer Letter` ol ON ol.name = pr.reference_name
			INNER JOIN `tabApplicant` app ON app.name = ol.applicant
		"""
		programme_expr = "COALESCE(NULLIF(ol.program, ''), app.program)"
		# Payment Request has no fee-type field: take it from the receipt, else from the
		# latest fee assignment on that offer created before the payment attempt.
		fee_component_expr = """COALESCE(
			(SELECT r.fee_type FROM `tabApplicant Payment Receipt` r
			  WHERE r.payment_reference = pr.name AND r.docstatus < 2
			  ORDER BY r.creation DESC LIMIT 1),
			(SELECT afa.fee_type FROM `tabApplicant Fee Assignment` afa
			  WHERE afa.offer_letter = ol.name AND afa.docstatus < 2 AND afa.creation <= pr.creation
			  ORDER BY afa.creation DESC LIMIT 1),
			'Admission Fee')"""
	else:
		joins = "INNER JOIN `tabApplicant` app ON app.name = pr.reference_name"
		programme_expr = "app.program"
		fee_component_expr = "'Application Fee'"

	if filters.get("from_date"):
		conditions.append("COALESCE(pr.paid_on, pr.creation) >= %(from_date)s")
		values["from_date"] = f"{filters.from_date} 00:00:00"
	if filters.get("to_date"):
		conditions.append("COALESCE(pr.paid_on, pr.creation) <= %(to_date)s")
		values["to_date"] = f"{filters.to_date} 23:59:59"
	if filters.get("admission_cycle"):
		conditions.append("app.admission_cycle = %(admission_cycle)s")
		values["admission_cycle"] = filters.admission_cycle
	if filters.get("admission_year"):
		conditions.append("app.admission_year = %(admission_year)s")
		values["admission_year"] = filters.admission_year
	if filters.get("program"):
		conditions.append(f"{programme_expr} = %(program)s")
		values["program"] = filters.program
	if filters.get("status"):
		conditions.append("pr.status = %(status)s")
		values["status"] = filters.status
	if filters.get("settlement_status") == NOT_SETTLED:
		conditions.append("IFNULL(pr.settlement_status, '') IN ('', 'Pending')")
	elif filters.get("settlement_status") == "Settled":
		# some records carry Razorpay's raw state ("processed") instead of "Settled"
		conditions.append("pr.settlement_status IN ('Settled', 'processed')")
	elif filters.get("settlement_status"):
		conditions.append("pr.settlement_status = %(settlement_status)s")
		values["settlement_status"] = filters.settlement_status
	if filters.get("applicant"):
		conditions.append("app.name = %(applicant)s")
		values["applicant"] = filters.applicant

	rows = frappe.db.sql(
		f"""
		SELECT
			pr.name AS payment_request,
			app.name AS application_number,
			app.candidate_name AS student_name,
			app.mobile_number AS phone,
			{programme_expr} AS programme,
			{fee_component_expr} AS fee_component,
			pr.amount,
			pr.status AS payment_status,
			pr.paid_on AS payment_date,
			pr.settlement_date,
			pr.settlement_status,
			pr.payment_gateway,
			COALESCE(NULLIF(pr.razorpay_payment_id, ''), NULLIF(pr.transaction_id, ''), pr.razorpay_order_id) AS reference_number,
			(SELECT r.remarks FROM `tabApplicant Payment Receipt` r
			  WHERE r.payment_reference = pr.name AND r.docstatus < 2
			  ORDER BY r.creation DESC LIMIT 1) AS receipt_remarks,
			(SELECT r.payment_mode FROM `tabApplicant Payment Receipt` r
			  WHERE r.payment_reference = pr.name AND r.docstatus < 2
			  ORDER BY r.creation DESC LIMIT 1) AS receipt_payment_mode,
			(SELECT COALESCE(NULLIF(sm.registration_id, ''), sm.name) FROM `tabStudent Master` sm
			  WHERE sm.application_number = app.name
			  ORDER BY sm.creation DESC LIMIT 1) AS student_id
		FROM `tabSLCM Payment Request` pr
		{joins}
		WHERE {" AND ".join(conditions)}
		ORDER BY COALESCE(pr.paid_on, pr.creation) DESC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		paid = row.payment_status == "Paid"
		row.amount_paid = flt(row.amount) if paid else 0
		row.remarks = row.receipt_remarks or _("{0} for {1}").format(row.fee_component, row.programme or "")
		row.description = _get_online_offline(row)
		row.department = ""  # intentionally blank
		if row.settlement_status == "processed":
			row.settlement_status = "Settled"
		row.settlement_status = (row.settlement_status or NOT_SETTLED) if paid else ""
		if row.reference_number == "N/A":
			row.reference_number = ""
	return rows


def _get_online_offline(row):
	if row.receipt_payment_mode:
		return "online" if row.receipt_payment_mode == "Online" else "offline"
	return "offline" if row.payment_gateway == OFFLINE_GATEWAY else "online"


def get_summary(data):
	paid = [r for r in data if r.payment_status == "Paid"]
	settled = [r for r in paid if r.settlement_status == "Settled"]
	pending = [r for r in paid if r.settlement_status != "Settled"]
	return [
		{"label": _("Payments Collected"), "value": len(paid), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Amount Collected"), "value": sum(flt(r.amount_paid) for r in paid), "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Settled"), "value": sum(flt(r.amount_paid) for r in settled), "datatype": "Currency", "indicator": "Green"},
		{"label": _("Awaiting Settlement"), "value": sum(flt(r.amount_paid) for r in pending), "datatype": "Currency",
		 "indicator": "Orange" if pending else "Green"},
		{"label": _("Unpaid Attempts"), "value": len(data) - len(paid), "datatype": "Int", "indicator": "Grey"},
	]

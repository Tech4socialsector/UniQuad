# Copyright (c) 2026, Azim Premji Foundation and contributors
# For license information, please see license.txt

"""Income, tax and expense booked in ERPNext from SLCM fees. Reads only ERPNext GL Entries."""

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import flt, getdate

from slcm.erpnext_bridge import erpnext_installed

SOURCE_LABELS = {
	"Fee Payment": _("Fee Receipts"),
	"Fee Refund": _("Fee Refunds"),
	"SLCM Payment Request": _("Gateway Settlements"),
	"Student Credit Note": _("Moved to Excess"),
	"Credit Adjustment Row": _("Excess Adjusted"),
	"Applicant Payment Receipt": _("Admission Receipts"),
	"PACE Receipt": _("PACE Receipts"),
	"FLE Payment Log": _("FLE Receipts"),
	"FLE Settlement": _("Gateway Settlements"),
	"Stipend Payment": _("Stipends"),
	"Refund Transaction": _("Admission Refunds"),
}

MEASURES = (
	("fee_income", _("Fee Income"), "Currency"),
	("deposits", _("Deposits & Advances Held"), "Currency"),
	("output_tax", _("Output GST"), "Currency"),
	("refunds", _("Refunds"), "Currency"),
	("gateway_charges", _("Gateway Charges"), "Currency"),
	("input_tax", _("GST on Gateway Charges"), "Currency"),
	("net_income", _("Net Fee Income"), "Currency"),
	("stipends", _("Stipends Paid"), "Currency"),
	("cash_movement", _("Net Cash, Bank & Gateway Clearing"), "Currency"),
)


def execute(filters=None):
	if not erpnext_installed():
		frappe.throw(_("ERPNext is not installed on this site."))
	filters = frappe._dict(filters or {})
	if not filters.company:
		return [], []
	entries = get_gl_entries(filters)
	classify = get_classifier(filters.company)

	if filters.group_by == "Fee Ledger":
		return ledger_view(entries, classify)

	groups = OrderedDict()
	for e in entries:
		key, label = group_key(e, filters.group_by)
		row = groups.setdefault(key, {"group": label, **{m[0]: 0.0 for m in MEASURES}})
		category, sign = classify(e)
		row[category] += sign * (flt(e.debit) - flt(e.credit))

	data = []
	for key in sorted(groups):
		row = groups[key]
		row["net_income"] = row["fee_income"] - row["refunds"] - row["gateway_charges"]
		data.append(row)

	columns = [{"fieldname": "group", "label": _(filters.group_by or "Month"), "fieldtype": "Data", "width": 220}]
	columns += [{"fieldname": f, "label": label, "fieldtype": ft, "width": 150} for f, label, ft in MEASURES]

	totals = {m[0]: sum(flt(r[m[0]]) for r in data) for m in MEASURES}
	if data:
		data.append({"group": _("Total"), "bold": 1, **totals})
	return columns, data, None, get_chart(data[:-1]), get_summary(totals)


def get_gl_entries(filters):
	gle = frappe.qb.DocType("GL Entry")
	je = frappe.qb.DocType("Journal Entry")
	acc = frappe.qb.DocType("Account")
	query = (
		frappe.qb.from_(gle)
		.join(je)
		.on(je.name == gle.voucher_no)
		.join(acc)
		.on(acc.name == gle.account)
		.select(
			gle.posting_date,
			gle.account,
			gle.debit,
			gle.credit,
			acc.root_type,
			je.slcm_reference_doctype,
			je.slcm_programme,
		)
		.where(gle.voucher_type == "Journal Entry")
		.where(gle.is_cancelled == 0)
		.where(gle.company == filters.company)
		.where(je.slcm_reference_doctype.isnotnull())
		.orderby(gle.posting_date)
	)
	if filters.from_date:
		query = query.where(gle.posting_date >= filters.from_date)
	if filters.to_date:
		query = query.where(gle.posting_date <= filters.to_date)
	if filters.programme:
		query = query.where(je.slcm_programme == filters.programme)
	if filters.student:
		query = query.where(je.slcm_student == filters.student)
	return query.run(as_dict=True)


def get_classifier(company):
	"""Return f(gl_entry) -> (measure, sign) where sign makes the measure positive in its natural direction."""
	c = frappe.db.get_value(
		"Company",
		company,
		[
			"slcm_output_gst_account",
			"slcm_fee_refund_account",
			"slcm_gateway_charges_account",
			"slcm_gateway_gst_account",
			"slcm_stipend_account",
		],
		as_dict=True,
	)
	special = {
		c.slcm_output_gst_account: ("output_tax", -1),
		c.slcm_fee_refund_account: ("refunds", 1),
		c.slcm_gateway_charges_account: ("gateway_charges", 1),
		c.slcm_gateway_gst_account: ("input_tax", 1),
		c.slcm_stipend_account: ("stipends", 1),
	}
	special.pop(None, None)

	def classify(e):
		if e.account in special:
			return special[e.account]
		if e.root_type == "Income":
			return "fee_income", -1
		if e.root_type == "Liability":
			return "deposits", -1
		if e.root_type == "Expense":
			return "gateway_charges", 1
		return "cash_movement", 1

	return classify


def group_key(e, group_by):
	if group_by == "Programme":
		return (e.slcm_programme or "~"), (e.slcm_programme or _("Programme not set"))
	if group_by == "Source Type":
		return e.slcm_reference_doctype, SOURCE_LABELS.get(e.slcm_reference_doctype, e.slcm_reference_doctype)
	d = getdate(e.posting_date)
	return d.strftime("%Y-%m"), d.strftime("%b %Y")


def ledger_view(entries, classify):
	labels = {m[0]: m[1] for m in MEASURES}
	rows = OrderedDict()
	for e in entries:
		row = rows.setdefault(
			e.account, {"account": e.account, "category": labels[classify(e)[0]], "debit": 0.0, "credit": 0.0}
		)
		row["debit"] += flt(e.debit)
		row["credit"] += flt(e.credit)
	data = sorted(rows.values(), key=lambda r: (r["category"], r["account"]))
	for r in data:
		r["balance"] = r["debit"] - r["credit"]
	columns = [
		{"fieldname": "account", "label": _("Account"), "fieldtype": "Link", "options": "Account", "width": 320},
		{"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
		{"fieldname": "debit", "label": _("Debit"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "credit", "label": _("Credit"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "balance", "label": _("Balance (Dr - Cr)"), "fieldtype": "Currency", "width": 160},
	]
	if data:
		data.append(
			{
				"account": _("Total"),
				"bold": 1,
				"debit": sum(r["debit"] for r in data),
				"credit": sum(r["credit"] for r in data),
				"balance": sum(r["balance"] for r in data),
			}
		)
	return columns, data


def get_chart(data):
	if not data:
		return None
	return {
		"data": {
			"labels": [r["group"] for r in data],
			"datasets": [
				{"name": _("Fee Income"), "values": [flt(r["fee_income"]) for r in data]},
				{"name": _("Refunds"), "values": [flt(r["refunds"]) for r in data]},
				{"name": _("Gateway Charges"), "values": [flt(r["gateway_charges"]) for r in data]},
			],
		},
		"type": "bar",
		"fieldtype": "Currency",
	}


def get_summary(t):
	return [
		{"value": t["fee_income"], "label": _("Fee Income"), "datatype": "Currency", "indicator": "Green"},
		{"value": t["output_tax"], "label": _("Output GST"), "datatype": "Currency", "indicator": "Blue"},
		{"value": t["refunds"], "label": _("Refunds"), "datatype": "Currency", "indicator": "Red"},
		{"value": t["gateway_charges"], "label": _("Gateway Charges"), "datatype": "Currency", "indicator": "Orange"},
		{"value": t["net_income"], "label": _("Net Fee Income"), "datatype": "Currency", "indicator": "Green"},
	]

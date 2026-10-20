# Copyright (c) 2026, Azim Premji Foundation and contributors
# For license information, please see license.txt

"""Every SLCM fee transaction next to the ERPNext Journal Entry posted for it, with exceptions flagged."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from slcm.erpnext_bridge import config as conf
from slcm.erpnext_bridge import erpnext_installed
from slcm.erpnext_bridge.sync import last_error


def execute(filters=None):
	if not erpnext_installed():
		frappe.throw(_("ERPNext is not installed on this site."))
	filters = frappe._dict(filters or {})
	cfg = conf.get_config()
	start = getdate(cfg.slcm_posting_from_date) if cfg and cfg.slcm_posting_from_date else None

	rows = []
	if filters.source in (None, "", "Fee Payment"):
		rows += get_sources(filters, "Fee Payment", "payment_date", "amount", "payment_mode")
	if filters.source in (None, "", "Fee Refund"):
		rows += get_sources(filters, "Fee Refund", "refund_date", "refund_amount", "refund_mode")
	if filters.source in (None, "", "SLCM Payment Request"):
		rows += get_settlements(filters)

	jes = get_journal_entries(rows)
	fallback = components_on_default_ledger(cfg, [r["reference_name"] for r in rows if r["reference_doctype"] == "Fee Payment"])

	data = []
	for r in rows:
		entries = jes.get((r["reference_doctype"], r["reference_name"]), [])
		live = next((je for je in entries if je.docstatus in (0, 1)), None)
		r.update(
			journal_entry=(live or (entries[0] if entries else {})).get("name"),
			erpnext_amount=flt(live.total_debit) if live else 0.0,
		)
		r["difference"] = flt(r["slcm_amount"] - r["erpnext_amount"], 2)
		r["remark"], r["exception"] = assess(r, live, entries, start, cfg)
		if not r["exception"] and r["reference_name"] in fallback:
			r["remark"] += _(" - {0} posted to the default fee income ledger").format(", ".join(fallback[r["reference_name"]]))
		if cint(filters.only_exceptions) and not r["exception"]:
			continue
		data.append(r)

	data.sort(key=lambda r: (str(r["date"]), r["reference_name"]))
	return get_columns(), data, None, None, get_summary(data)


def get_sources(filters, doctype, date_field, amount_field, mode_field):
	conditions, values = ["docstatus in (1, 2)"], {}
	if filters.from_date:
		conditions.append(f"{date_field} >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.to_date:
		conditions.append(f"{date_field} <= %(to_date)s")
		values["to_date"] = filters.to_date
	if filters.student:
		conditions.append("student = %(student)s")
		values["student"] = filters.student
	records = frappe.db.sql(
		f"""select name, {date_field} as date, student, {amount_field} as amount, {mode_field} as mode, docstatus
		from `tab{doctype}` where {" and ".join(conditions)}""",
		values,
		as_dict=True,
	)
	return [
		{
			"reference_doctype": doctype,
			"reference_name": d.name,
			"date": getdate(d.date),
			"student": d.student,
			"mode": d.mode,
			"slcm_state": _("Cancelled") if d.docstatus == 2 else _("Submitted"),
			"active": d.docstatus == 1,
			"slcm_amount": flt(d.amount, 2) if d.docstatus == 1 else 0.0,
		}
		for d in records
	]


def get_settlements(filters):
	conditions, values = [], {}
	if filters.from_date:
		conditions.append("date(pr.settlement_date) >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.to_date:
		conditions.append("date(pr.settlement_date) <= %(to_date)s")
		values["to_date"] = filters.to_date
	date_where = "".join(f" and {c}" for c in conditions)
	records = frappe.db.sql(
		f"""select pr.name, pr.settlement_date, pr.docstatus, pr.settlement_status,
			pr.net_settled, pr.settlement_amount, pr.gateway_fees, pr.gateway_tax, fp.student
		from `tabSLCM Payment Request` pr
		left join `tabFee Payment` fp on fp.reference_number = pr.razorpay_payment_id
			and fp.docstatus = 1 and fp.payment_mode = 'Online Payment'
		where (
			(pr.settlement_status = 'Settled' and fp.name is not null)
			or exists (select 1 from `tabJournal Entry` je
				where je.slcm_reference_doctype = 'SLCM Payment Request' and je.slcm_reference_name = pr.name)
		){date_where}""",
		values,
		as_dict=True,
	)
	rows = []
	for d in records:
		if filters.student and d.student != filters.student:
			continue
		fees, tax = flt(d.gateway_fees, 2), flt(d.gateway_tax, 2)
		net = flt(d.net_settled, 2) or flt(flt(d.settlement_amount) - fees - tax, 2)
		active = d.docstatus < 2 and d.settlement_status == "Settled"
		rows.append(
			{
				"reference_doctype": "SLCM Payment Request",
				"reference_name": d.name,
				"date": getdate(d.settlement_date) if d.settlement_date else None,
				"student": d.student,
				"mode": _("Razorpay Settlement"),
				"slcm_state": d.settlement_status or _("Not Settled"),
				"active": active,
				"slcm_amount": flt(net + fees + tax, 2) if active else 0.0,
			}
		)
	return rows


def get_journal_entries(rows):
	names = list({r["reference_name"] for r in rows})
	if not names:
		return {}
	out = {}
	for je in frappe.get_all(
		"Journal Entry",
		filters={"slcm_reference_name": ("in", names)},
		fields=["name", "docstatus", "total_debit", "slcm_reference_doctype", "slcm_reference_name"],
		order_by="creation desc",
	):
		out.setdefault((je.slcm_reference_doctype, je.slcm_reference_name), []).append(je)
	return out


def components_on_default_ledger(cfg, payments):
	"""{fee payment: [components whose Ledger has no matching Account]} - posted to the default income ledger."""
	if not cfg or not payments:
		return {}
	rows = frappe.db.sql(
		"""select distinct r.parent, d.fee_component from `tabFee Payment Demand Row` r
		join `tabFee Demand` d on d.name = r.fee_demand where r.parent in %s""",
		(tuple(payments),),
		as_dict=True,
	)
	resolved, out = {}, {}
	for row in rows:
		if row.fee_component not in resolved:
			name = conf.component_ledger_name(row.fee_component)
			resolved[row.fee_component] = bool(
				name and frappe.db.exists("Account", {"company": cfg.company, "account_name": name, "is_group": 0})
			)
		if not resolved[row.fee_component]:
			out.setdefault(row.parent, []).append(row.fee_component)
	return out


def assess(r, live, entries, start, cfg):
	"""Return (remark, is_exception)."""
	if r["active"] and start and r["date"] and r["date"] < start:
		return _("Before posting start date - not posted by design"), False
	if not r["active"]:
		if live:
			return _("Cancelled in SLCM but Journal Entry still active"), True
		return _("Cancelled in SLCM and in ERPNext") if entries else _("Cancelled in SLCM before posting"), False
	if not live:
		if entries:
			return _("Journal Entry cancelled in ERPNext - use Re-post if it should be booked"), True
		error = last_error(r["reference_doctype"], r["reference_name"])
		if error:
			return _("Posting failed: {0}").format(error), True
		if r["reference_doctype"] == "SLCM Payment Request":
			return _("Waiting for the receipt to be posted"), True
		return _("Not yet posted"), True
	if abs(r["difference"]) >= 0.01:
		return _("Amount mismatch"), True
	if live.docstatus == 0:
		return _("Journal Entry is in Draft"), bool(cfg and cfg.slcm_submit_journal_entries)
	return _("OK"), False


def get_columns():
	return [
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "reference_doctype", "label": _("SLCM Type"), "fieldtype": "Link", "options": "DocType", "width": 150},
		{
			"fieldname": "reference_name",
			"label": _("SLCM Document"),
			"fieldtype": "Dynamic Link",
			"options": "reference_doctype",
			"width": 170,
		},
		{"fieldname": "student", "label": _("Student"), "fieldtype": "Link", "options": "Student Master", "width": 140},
		{"fieldname": "mode", "label": _("Mode"), "fieldtype": "Data", "width": 130},
		{"fieldname": "slcm_state", "label": _("SLCM Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "slcm_amount", "label": _("SLCM Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "journal_entry", "label": _("Journal Entry"), "fieldtype": "Link", "options": "Journal Entry", "width": 160},
		{"fieldname": "erpnext_amount", "label": _("ERPNext Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "difference", "label": _("Difference"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "remark", "label": _("Remark"), "fieldtype": "Data", "width": 340},
	]


def get_summary(data):
	exceptions = sum(1 for r in data if r["exception"])
	return [
		{"value": len(data), "label": _("Documents"), "datatype": "Int", "indicator": "Blue"},
		{"value": len(data) - exceptions, "label": _("Reconciled"), "datatype": "Int", "indicator": "Green"},
		{"value": exceptions, "label": _("Exceptions"), "datatype": "Int", "indicator": "Red" if exceptions else "Green"},
		{"value": sum(flt(r["slcm_amount"]) for r in data), "label": _("SLCM Total"), "datatype": "Currency"},
		{"value": sum(flt(r["erpnext_amount"]) for r in data), "label": _("ERPNext Total"), "datatype": "Currency"},
	]

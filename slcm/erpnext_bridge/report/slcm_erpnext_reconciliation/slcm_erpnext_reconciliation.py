# Copyright (c) 2026, Azim Premji Foundation and contributors
# For license information, please see license.txt

"""Every SLCM fee transaction next to the ERPNext Journal Entry posted for it, with exceptions flagged."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from slcm.erpnext_bridge import config as conf
from slcm.erpnext_bridge import erpnext_installed
from slcm.erpnext_bridge.sync import SOURCES, last_error, settlement_receipt

# Receipts and payments: (who paid / was paid, amount, mode) as SQL on `src`. Date and "active" come from SOURCES,
# so this report and the posting can never disagree about what should be booked.
DIRECT = {
	"Fee Payment": ("src.student", "src.amount", "src.payment_mode"),
	"Fee Refund": ("src.student", "src.refund_amount", "src.refund_mode"),
	"Stipend Payment": ("src.student", "src.amount", "src.payment_mode"),
	"Applicant Payment Receipt": ("src.applicant", "src.net_amount", "src.payment_mode"),
	"PACE Receipt": ("src.pace_application", "src.amount", "'Online'"),
	"FLE Payment Log": ("src.reference_no", "src.paid_amount", "'Online'"),
	"Refund Transaction": ("src.refund_request", "src.refund_amount", "'Razorpay refund'"),
}


def execute(filters=None):
	if not erpnext_installed():
		frappe.throw(_("ERPNext is not installed on this site."))
	filters = frappe._dict(filters or {})
	cfg = conf.get_config()
	start = getdate(cfg.slcm_posting_from_date) if cfg and cfg.slcm_posting_from_date else None

	rows = []
	for key in DIRECT:
		if filters.source in (None, "", key):
			rows += get_sources(filters, key)
	if filters.source in (None, "", "SLCM Payment Request"):
		rows += get_settlements(filters)
	if filters.source in (None, "", "FLE Settlement"):
		rows += get_fle_settlements(filters)
	if filters.source in (None, "", "Student Credit Note"):
		rows += get_excess(filters)

	jes = get_journal_entries(rows)
	fallback = components_on_default_ledger(cfg, [r["reference_name"] for r in rows if r["reference_doctype"] == "Fee Payment"])

	data = []
	for r in rows:
		entries = jes.get(key_of(r), [])
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


def _has_entry(key):
	return f"""exists (select 1 from `tabJournal Entry` je where je.slcm_reference_doctype = '{key}'
		and je.slcm_reference_name = src.name)"""


def get_sources(filters, key):
	"""Receipts and payments that should be booked, or were booked (incl. cancelled since)."""
	who, amount, mode = DIRECT[key]
	source = SOURCES[key]
	active = f"coalesce(({source['active']}), 0)"
	conditions, values = [f"({active} or {_has_entry(key)} or src.docstatus = 2)"], {}
	if filters.from_date:
		conditions.append(f"{source['date']} >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.to_date:
		conditions.append(f"{source['date']} <= %(to_date)s")
		values["to_date"] = filters.to_date
	if filters.student:
		conditions.append(f"{who} = %(student)s")
		values["student"] = filters.student
	records = frappe.db.sql(
		f"""select src.name, {source["date"]} as date, {who} as student, {amount} as amount, {mode} as mode,
			{active} as active
		from `tab{key}` src where {" and ".join(conditions)}""",
		values,
		as_dict=True,
	)
	return [
		{
			"reference_doctype": key,
			"reference_name": d.name,
			"date": getdate(d.date) if d.date else None,
			"student": d.student,
			"mode": d.mode,
			"slcm_state": _("Active") if d.active else _("Cancelled / not active"),
			"active": bool(d.active),
			"slcm_amount": flt(d.amount, 2) if d.active else 0.0,
		}
		for d in records
	]


def _settlement_row(key, d, student):
	fees, tax = flt(d.gateway_fees, 2), flt(d.gateway_tax, 2)
	net = flt(d.net_settled, 2) or flt(flt(d.get("settlement_amount")) - fees - tax, 2)
	return {
		"reference_doctype": "FLE Payment Log" if key == "FLE Settlement" else key,
		"reference_name": d.name,
		"key": (key, d.name),
		"date": getdate(d.settlement_date) if d.settlement_date else None,
		"student": student,
		"mode": _("Razorpay Settlement"),
		"slcm_state": d.settlement_status or _("Not Settled"),
		"active": d.active,
		"slcm_amount": flt(net + fees + tax, 2) if d.active else 0.0,
	}


def _date_conditions(filters, expr):
	conditions, values = [], {}
	if filters.from_date:
		conditions.append(f"{expr} >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.to_date:
		conditions.append(f"{expr} <= %(to_date)s")
		values["to_date"] = filters.to_date
	return "".join(f" and {c}" for c in conditions), values


def get_settlements(filters):
	"""Razorpay settlements of student, admission and PACE payments."""
	date_where, values = _date_conditions(filters, "date(src.settlement_date)")
	records = frappe.db.sql(
		f"""select src.name, src.settlement_date, src.docstatus, src.settlement_status, src.razorpay_payment_id,
			src.transaction_id, src.net_settled, src.settlement_amount, src.gateway_fees, src.gateway_tax
		from `tabSLCM Payment Request` src
		where ((src.settlement_status = 'Settled' and src.docstatus < 2) or {_has_entry("SLCM Payment Request")}){date_where}""",
		values,
		as_dict=True,
	)
	rows = []
	for d in records:
		receipt_dt, receipt = settlement_receipt(d)
		student = None
		if receipt_dt == "Fee Payment":
			student = frappe.db.get_value("Fee Payment", receipt, "student")
		elif receipt_dt == "Applicant Payment Receipt":
			student = frappe.db.get_value("Applicant Payment Receipt", receipt, "applicant")
		if filters.student and student != filters.student:
			continue
		d.active = d.docstatus < 2 and d.settlement_status == "Settled"
		rows.append(_settlement_row("SLCM Payment Request", d, student))
	return rows


def get_fle_settlements(filters):
	date_where, values = _date_conditions(filters, "src.settlement_date")
	records = frappe.db.sql(
		f"""select src.name, src.reference_no, src.settlement_date, src.settlement_status, src.net_settled,
			src.gateway_fees, src.gateway_tax
		from `tabFLE Payment Log` src
		where (src.settlement_status = 'processed' or {_has_entry("FLE Settlement")}){date_where}""",
		values,
		as_dict=True,
	)
	rows = []
	for d in records:
		if filters.student and d.reference_no != filters.student:
			continue
		d.active = d.settlement_status == "processed"
		rows.append(_settlement_row("FLE Settlement", d, d.reference_no))
	return rows


def get_excess(filters):
	"""Paid fees moved to a student's excess (Student Credit Note) and excess applied to a due (its adjustment
	rows). Only notes that hold real money post; an adjustment is shown against its credit note, since its
	own row has no form to open."""
	conditions, values = ["note.docstatus in (1, 2)"], {}
	if filters.student:
		conditions.append("note.student = %(student)s")
		values["student"] = filters.student
	notes = frappe.db.sql(
		f"""select note.name, note.creation, note.student, note.credit_amount, note.docstatus,
			note.source_fee_demand, note.remarks, note.received_via, note.received_date
		from `tabStudent Credit Note` note where {" and ".join(conditions)}""",
		values,
		as_dict=True,
	)
	rows = []
	for n in notes:
		if not conf.credit_note_holds_money(n):
			continue
		active = n.docstatus == 1
		moved = bool(conf.credit_note_source_demand(n))
		rows.append(
			{
				"reference_doctype": "Student Credit Note",
				"reference_name": n.name,
				"date": getdate(conf.credit_note_date(n)),
				"student": n.student,
				"mode": _("Moved to excess") if moved else _("Excess received via {0}").format(n.received_via),
				"slcm_state": _("Cancelled") if not active else _("Submitted"),
				"active": active,
				"slcm_amount": flt(n.credit_amount, 2) if active else 0.0,
			}
		)
		for a in frappe.get_all(
			"Credit Adjustment Row",
			filters={"parent": n.name, "parenttype": "Student Credit Note", "fee_demand": ("is", "set")},
			fields=["name", "fee_demand", "amount_adjusted", "adjusted_on"],
		):
			rows.append(
				{
					"key": ("Credit Adjustment Row", a.name),
					"reference_doctype": "Student Credit Note",
					"reference_name": n.name,
					"date": getdate(a.adjusted_on) if a.adjusted_on else getdate(n.creation),
					"student": n.student,
					"mode": _("Excess adjusted to {0}").format(a.fee_demand),
					"slcm_state": _("Submitted"),
					"active": active,
					"slcm_amount": flt(a.amount_adjusted, 2) if active else 0.0,
				}
			)
	return [r for r in rows if _in_range(r["date"], filters)]


def _in_range(date, filters):
	if filters.from_date and date < getdate(filters.from_date):
		return False
	if filters.to_date and date > getdate(filters.to_date):
		return False
	return True


def key_of(r):
	"""(doctype, name) the Journal Entry was posted for."""
	return r.get("key") or (r["reference_doctype"], r["reference_name"])


def get_journal_entries(rows):
	names = list({key_of(r)[1] for r in rows})
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
		error = last_error(*key_of(r))
		if error:
			return _("Posting failed: {0}").format(error), True
		if key_of(r)[0] in ("SLCM Payment Request", "FLE Settlement"):
			return _("Waiting for the receipt to be posted"), True
		if key_of(r)[0] == "Credit Adjustment Row":
			return _("Waiting for the credit note to be posted"), True
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
		# Data, not a Link: also holds applicants, PACE applications, FLE enrolments and refund requests.
		{"fieldname": "student", "label": _("Student / Applicant"), "fieldtype": "Data", "width": 150},
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

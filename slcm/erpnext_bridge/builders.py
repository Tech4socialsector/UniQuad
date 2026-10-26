"""Turn SLCM fee documents into balanced Journal Entry lines (cash basis, same treatment as the Zoho export).

Receipt  (Fee Payment)            Dr Cash / Bank / Gateway Clearing      Cr Fee ledger per component (+ Output GST)
                                                                         Cr Unallocated Fee Receipts (part not allocated)
Refund   (Fee Refund)             Dr Fee Refunds (or the deposit ledger) Cr Cash / Bank
         from excess              Dr Unallocated Fee Receipts            Cr Cash / Bank
Gateway settlement (Payment Req.) Dr Bank (net) + Gateway Charges + GST  Cr Gateway Clearing (gross)
Moved to excess (Credit Note)     Dr Fee ledger of the due (+ Output GST) Cr Unallocated Fee Receipts
Excess adjusted to a due (row)    Dr Unallocated Fee Receipts            Cr Fee ledger of the due (+ Output GST)

Unallocated Fee Receipts is a liability: money held for the student until it is applied to a due or refunded.
"""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate

from slcm.erpnext_bridge import config as conf

PRECISION = 2


def build_entry(cfg, src, key=None):
	builder = {
		"Fee Payment": _receipt,
		"Fee Refund": _refund,
		"SLCM Payment Request": _settlement,
		"Student Credit Note": _moved_to_excess,
		"Credit Adjustment Row": _excess_adjusted,
		"Applicant Payment Receipt": _applicant_receipt,
		"PACE Receipt": _pace_receipt,
		"FLE Payment Log": _fle_receipt,
		"FLE Settlement": _fle_settlement,
		"Stipend Payment": _stipend,
		"Refund Transaction": _gateway_refund,
	}[key or src.doctype]
	entry = builder(cfg, src)
	_check_balanced(entry["lines"])
	return entry


# ── receipts ────────────────────────────────────────────────────────────────────


def _receipt(cfg, fp):
	amount = flt(fp.amount, PRECISION)
	credits = defaultdict(float)

	allocated = 0.0
	for row in fp.payment_demands or []:
		share = flt(row.amount_allocated, PRECISION)
		if not share:
			continue
		component = frappe.db.get_value("Fee Demand", row.fee_demand, "fee_component") if row.fee_demand else None
		_credit_component(cfg, credits, component, share)
		allocated += share

	unallocated = flt(amount - allocated, PRECISION)
	if unallocated < 0:
		frappe.throw(_("Allocated amount exceeds the payment amount on {0}").format(fp.name))
	if unallocated:
		credits[conf.require(cfg, "slcm_unallocated_fee_account")] += unallocated

	cash_account = conf.receipt_cash_account(cfg, fp.payment_mode, fp.get("university_bank_account"))
	lines = [(cash_account, amount, 0.0)] + [(acc, 0.0, flt(cr, PRECISION)) for acc, cr in credits.items()]
	return {
		"posting_date": getdate(fp.payment_date),
		"cash_account": cash_account,
		"reference": fp.reference_number or fp.name,
		"remark": _("SLCM Fee Payment {0} | {1} ({2}) | {3}").format(
			fp.name, fp.student, fp.get("student_name") or "", fp.payment_mode
		),
		"student": fp.student,
		"programme": _programme_of(fp.get("program"), fp.student),
		"lines": lines,
	}


def _credit_component(cfg, credits, component, share):
	account, _default = conf.component_account(cfg, component)
	tax_rate = 0.0
	if component and conf.fees_include_gst(cfg):
		is_taxable, rate = frappe.db.get_value("Fee Component", component, ["is_taxable", "tax_rate"]) or (0, 0)
		tax_rate = flt(rate) if is_taxable else 0.0
	if tax_rate > 0:
		# The cash received is the gross amount; carve the GST out of it (tax-inclusive split).
		tax = flt(share * tax_rate / (100 + tax_rate), PRECISION)
		credits[conf.require(cfg, "slcm_output_gst_account", _("taxable Fee Component {0}").format(component))] += tax
		credits[account] += flt(share - tax, PRECISION)
	else:
		credits[account] += share


# ── refunds ─────────────────────────────────────────────────────────────────────


def _refund(cfg, fr):
	amount = flt(fr.refund_amount, PRECISION)
	cash_account = conf.mode_of_payment_account(cfg, fr.refund_mode) or conf.require(
		cfg, "default_cash_account" if fr.refund_mode == "Cash" else "default_bank_account"
	)

	if fr.get("refund_source") == "Excess Amount":
		debits = _excess_refund_debits(cfg, fr, amount)
	else:
		debit_account = conf.require(cfg, "slcm_fee_refund_account")
		if fr.get("fee_component"):
			account, used_default = conf.component_account(cfg, fr.fee_component)
			# Deposits are held as liabilities, so refunding one releases the liability instead of booking an expense.
			if not used_default and frappe.get_cached_value("Account", account, "root_type") in ("Liability", "Asset"):
				debit_account = account
		debits = [(debit_account, amount, 0.0)]

	return {
		"posting_date": getdate(fr.refund_date),
		"cash_account": cash_account,
		"reference": fr.get("utr_number") or fr.name,
		"remark": _("SLCM Fee Refund {0} | {1} | {2} | {3}").format(
			fr.name, fr.student, fr.refund_type, fr.refund_source
		),
		"student": fr.student,
		"programme": _programme_of(None, fr.student),
		"lines": debits + [(cash_account, 0.0, amount)],
	}


def _excess_refund_debits(cfg, fr, amount):
	"""A refund of the student's excess pays out money held in Unallocated Fee Receipts - for the part drawn from
	credit notes whose money was posted there. Anything else (e.g. scholarship credit, which never held cash)
	is a Fee Refunds expense."""
	from slcm.erpnext_bridge.sync import live_journal_entry

	held = 0.0
	for row in json.loads(fr.get("excess_allocation") or "[]"):
		note = row.get("credit_note")
		if note and live_journal_entry("Student Credit Note", note):
			held += flt(row.get("amount"), PRECISION)
	held = min(flt(held, PRECISION), amount)
	debits = []
	if held:
		debits.append((conf.require(cfg, "slcm_unallocated_fee_account"), held, 0.0))
	if flt(amount - held, PRECISION):
		debits.append((conf.require(cfg, "slcm_fee_refund_account"), flt(amount - held, PRECISION), 0.0))
	return debits


# ── student excess (Student Credit Note) ────────────────────────────────────────


def _moved_to_excess(cfg, note):
	"""Paid fees moved off a due into the student's excess: the income booked for that due becomes money held.
	Excess entered by hand for money received directly (Received Via) is a receipt into money held."""
	demand = conf.credit_note_source_demand(note)
	if not demand:
		return _excess_received(cfg, note)
	component = frappe.db.get_value("Fee Demand", demand, "fee_component") if demand else None
	amount = flt(note.credit_amount, PRECISION)
	split = defaultdict(float)
	_credit_component(cfg, split, component, amount)
	held = conf.require(cfg, "slcm_unallocated_fee_account")
	return {
		"posting_date": getdate(note.creation),
		"cash_account": held,
		"reference": note.name,
		"remark": _("SLCM Student Credit Note {0} | {1} | moved from due {2} ({3})").format(
			note.name, note.student, demand or "-", component or "-"
		),
		"student": note.student,
		"programme": _programme_of(None, note.student),
		"lines": [(acc, flt(v, PRECISION), 0.0) for acc, v in split.items()] + [(held, 0.0, amount)],
	}


def _excess_received(cfg, note):
	amount = flt(note.credit_amount, PRECISION)
	cash_account = conf.receipt_cash_account(cfg, note.received_via, note.get("received_bank_account"))
	held = conf.require(cfg, "slcm_unallocated_fee_account")
	return {
		"posting_date": getdate(conf.credit_note_date(note)),
		"cash_account": cash_account,
		"reference": note.get("received_reference") or note.name,
		"remark": _("SLCM Student Credit Note {0} | {1} | {2} received via {3}").format(
			note.name, note.student, note.credit_type, note.received_via
		),
		"student": note.student,
		"programme": _programme_of(None, note.student),
		"lines": [(cash_account, amount, 0.0), (held, 0.0, amount)],
	}


def _excess_adjusted(cfg, row):
	"""Excess applied to a due: the held money becomes income for that due's component."""
	student = frappe.db.get_value("Student Credit Note", row.parent, "student")
	component = (frappe.db.get_value("Fee Demand", row.fee_demand, "fee_component") if row.fee_demand else None) or row.get(
		"fee_component"
	)
	amount = flt(row.amount_adjusted, PRECISION)
	split = defaultdict(float)
	_credit_component(cfg, split, component, amount)
	held = conf.require(cfg, "slcm_unallocated_fee_account")
	return {
		"posting_date": getdate(row.adjusted_on or row.creation),
		"cash_account": held,
		"reference": row.parent,
		"remark": _("SLCM excess from {0} adjusted to due {1} ({2}) | {3}").format(
			row.parent, row.fee_demand, component or "-", student
		),
		"student": student,
		"programme": _programme_of(None, student),
		"lines": [(held, amount, 0.0)] + [(acc, 0.0, flt(v, PRECISION)) for acc, v in split.items()],
	}


# ── gateway settlement ──────────────────────────────────────────────────────────


def _settlement(cfg, pr):
	from slcm.erpnext_bridge.sync import settlement_receipt

	receipt_dt, receipt = settlement_receipt(pr)
	student = None
	if receipt_dt == "Fee Payment":
		student = frappe.db.get_value("Fee Payment", receipt, "student")
	elif receipt_dt == "Applicant Payment Receipt":
		student = frappe.db.get_value("Applicant Payment Receipt", receipt, "applicant")
	remark = _("Razorpay settlement {0} | payment {1} | {2} {3} | UTR {4}").format(
		pr.name, pr.razorpay_payment_id or pr.get("transaction_id") or "-", receipt_dt or "", receipt or "-", pr.settlement_utr or "-"
	)
	return _settle(cfg, pr, remark, student)


def _fle_settlement(cfg, log):
	remark = _("Razorpay settlement for FLE {0} | payment {1} | log {2} | UTR {3}").format(
		log.reference_no, log.transaction_id or "-", log.name, log.settlement_utr or "-"
	)
	return _settle(cfg, log, remark, log.reference_no)


def _settle(cfg, src, remark, student):
	"""Dr Bank (net) + Gateway Charges + GST on charges / Cr Gateway Clearing (gross), from Razorpay's settlement
	figures stored on the SLCM record."""
	fees = flt(src.gateway_fees, PRECISION)
	tax = flt(src.gateway_tax, PRECISION)
	net = flt(src.net_settled, PRECISION) or flt(flt(src.get("settlement_amount")) - fees - tax, PRECISION)
	gross = flt(net + fees + tax, PRECISION)
	if gross <= 0:
		frappe.throw(_("Settlement amount on {0} is zero").format(src.name))

	bank = conf.require(cfg, "default_bank_account", _("Razorpay settles into the Company's default bank account"))
	charges = conf.require(cfg, "slcm_gateway_charges_account")
	tax_account = cfg.slcm_gateway_gst_account or charges

	lines = [(bank, net, 0.0), (charges, fees, 0.0), (tax_account, tax, 0.0)]
	lines.append((conf.gateway_clearing_account(cfg), 0.0, gross))
	return {
		"posting_date": getdate(src.settlement_date),
		"cash_account": bank,
		"reference": src.settlement_utr or src.name,
		"remark": remark,
		"student": student,
		"programme": _programme_of(None, student),
		"lines": lines,
	}


# ── admission, PACE and FLE receipts ────────────────────────────────────────────


def _applicant_receipt(cfg, r):
	"""Admission fees paid by an applicant: credited per fee component like a student's receipt. A scholarship
	shown on the receipt reduces what was paid, so the components share the net amount proportionally."""
	amount = flt(r.net_amount, PRECISION)
	rows = [row for row in (r.get("fee_components") or []) if flt(row.amount) > 0]
	total = flt(sum(flt(row.amount) for row in rows), PRECISION)
	credits = defaultdict(float)
	allocated = 0.0
	for i, row in enumerate(rows):
		last = i == len(rows) - 1
		share = flt(amount - allocated, PRECISION) if last else flt(flt(row.amount) * amount / total, PRECISION)
		_credit_component(cfg, credits, row.fee_component, share)
		allocated += share
	if not rows:
		_credit_component(cfg, credits, None, amount)

	cash_account = conf.receipt_cash_account(cfg, r.payment_mode)
	return {
		"posting_date": getdate(r.payment_date),
		"cash_account": cash_account,
		"reference": r.get("transaction_id") or r.get("cheque_number") or r.name,
		"remark": _("SLCM Applicant Payment Receipt {0} | {1} ({2}) | {3} | {4}").format(
			r.name, r.applicant, r.get("applicant_name") or "", r.fee_type, r.payment_mode
		),
		"student": r.applicant,
		"programme": r.get("program") if r.get("program") and frappe.db.exists("Programme", r.program) else None,
		"lines": [(cash_account, amount, 0.0)] + [(acc, 0.0, flt(cr, PRECISION)) for acc, cr in credits.items()],
	}


def _pace_receipt(cfg, r):
	currency = r.get("currency") or cfg.default_currency
	if currency and cfg.default_currency and currency != cfg.default_currency:
		frappe.throw(
			_("PACE Receipt {0} is in {1}; only {2} receipts are posted (multi-currency is not set up)").format(
				r.name, currency, cfg.default_currency
			)
		)
	amount = flt(r.amount, PRECISION)
	income = conf.account_named(cfg, f"PACE {r.fee_type}") or conf.require(
		cfg, "slcm_default_fee_income_account", _("PACE {0}").format(r.fee_type)
	)
	# PACE fees are paid online through Razorpay.
	cash_account = (
		conf.gateway_clearing_account(cfg)
		if (r.get("payment_request") or r.get("transaction_id"))
		else conf.require(cfg, "default_bank_account")
	)
	return {
		"posting_date": getdate(r.payment_date),
		"cash_account": cash_account,
		"reference": r.get("transaction_id") or r.name,
		"remark": _("SLCM PACE Receipt {0} | {1} | {2}").format(r.name, r.pace_application, r.fee_type),
		"student": r.pace_application,
		"programme": None,
		"lines": [(cash_account, amount, 0.0), (income, 0.0, amount)],
	}


def _fle_receipt(cfg, log):
	amount = flt(log.paid_amount, PRECISION)
	income = conf.account_named(cfg, "FLE Course Fee") or conf.require(
		cfg, "slcm_default_fee_income_account", _("Foundations for a Legal Education")
	)
	clearing = conf.gateway_clearing_account(cfg)
	return {
		"posting_date": getdate(log.transaction_date),
		"cash_account": clearing,
		"reference": log.transaction_id or log.name,
		"remark": _("SLCM FLE payment {0} | {1} ({2}) | {3}").format(
			log.name, log.reference_no, log.get("full_name") or "", log.payment_status
		),
		"student": log.reference_no,
		"programme": None,
		"lines": [(clearing, amount, 0.0), (income, 0.0, amount)],
	}


# ── money paid out ──────────────────────────────────────────────────────────────


def _stipend(cfg, sp):
	amount = flt(sp.amount, PRECISION)
	expense = conf.require(cfg, "slcm_stipend_account")
	cash_account = conf.payment_out_account(cfg, sp.payment_mode)
	return {
		"posting_date": getdate(sp.payment_date),
		"cash_account": cash_account,
		"reference": sp.get("reference_number") or sp.name,
		"remark": _("SLCM Stipend Payment {0} | {1} | {2} | {3}").format(
			sp.name, sp.student, sp.get("stipend_type") or "", sp.payment_mode
		),
		"student": sp.student,
		"programme": _programme_of(sp.get("programme"), sp.student),
		"lines": [(expense, amount, 0.0), (cash_account, 0.0, amount)],
	}


def _gateway_refund(cfg, rt):
	"""An admission refund paid back through Razorpay: Razorpay takes it out of the money it holds for the university,
	so it comes off the gateway clearing account."""
	amount = flt(rt.refund_amount, PRECISION)
	clearing = conf.gateway_clearing_account(cfg)
	applicant = (
		frappe.db.get_value("Refund Request", rt.refund_request, "applicant") if rt.get("refund_request") else None
	)
	return {
		"posting_date": getdate(rt.processed_at),
		"cash_account": clearing,
		"reference": rt.get("razorpay_refund_id") or rt.name,
		"remark": _("SLCM Refund Transaction {0} | Refund Request {1} | payment {2}").format(
			rt.name, rt.get("refund_request") or "-", rt.get("razorpay_payment_id") or "-"
		),
		"student": applicant,
		"programme": None,
		"lines": [(conf.require(cfg, "slcm_fee_refund_account"), amount, 0.0), (clearing, 0.0, amount)],
	}


# ── journal entry ───────────────────────────────────────────────────────────────


def make_journal_entry(cfg, src, entry, key=None):
	voucher_type = {"Bank": "Bank Entry", "Cash": "Cash Entry"}.get(
		frappe.get_cached_value("Account", entry["cash_account"], "account_type"), "Journal Entry"
	)
	je = frappe.new_doc("Journal Entry")
	je.update(
		{
			"company": cfg.company,
			"posting_date": entry["posting_date"],
			"voucher_type": voucher_type,
			"cheque_no": (entry["reference"] or src.name)[:140],
			"cheque_date": entry["posting_date"],
			"user_remark": entry["remark"],
			"slcm_reference_doctype": key or src.doctype,
			"slcm_reference_name": src.name,
			"slcm_student": entry.get("student"),
			"slcm_programme": entry.get("programme"),
		}
	)
	merged = defaultdict(lambda: [0.0, 0.0])
	for account, debit, credit in entry["lines"]:
		merged[account][0] += flt(debit, PRECISION)
		merged[account][1] += flt(credit, PRECISION)
	for account, (debit, credit) in merged.items():
		net = flt(debit - credit, PRECISION)
		if not net:
			continue
		je.append(
			"accounts",
			{
				"account": account,
				"debit_in_account_currency": net if net > 0 else 0,
				"credit_in_account_currency": -net if net < 0 else 0,
				"cost_center": cfg.cost_center,
				"user_remark": entry["remark"][:140],
			},
		)
	je.flags.ignore_permissions = True
	je.insert()
	if cfg.slcm_submit_journal_entries:
		je.submit()
	return je


# ── helpers ─────────────────────────────────────────────────────────────────────


def _check_balanced(lines):
	debit = flt(sum(flt(line[1], PRECISION) for line in lines), PRECISION)
	credit = flt(sum(flt(line[2], PRECISION) for line in lines), PRECISION)
	if debit != credit:
		frappe.throw(_("Internal error: entry not balanced (Dr {0} / Cr {1})").format(debit, credit))


def _programme_of(programme, student):
	if programme and frappe.db.exists("Programme", programme):
		return programme
	if student:
		return frappe.db.get_value("Student Master", student, "programme_of_study")
	return None

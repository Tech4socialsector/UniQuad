"""Turn SLCM fee documents into balanced Journal Entry lines (cash basis, same treatment as the Zoho export).

Receipt  (Fee Payment)            Dr Cash / Bank / Gateway Clearing      Cr Fee ledger per component (+ Output GST)
Refund   (Fee Refund)             Dr Fee Refunds (or the deposit ledger) Cr Cash / Bank
Gateway settlement (Payment Req.) Dr Bank (net) + Gateway Charges + GST  Cr Gateway Clearing (gross)
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate

from slcm.erpnext_bridge import config as conf

PRECISION = 2


def build_entry(cfg, src):
	builder = {
		"Fee Payment": _receipt,
		"Fee Refund": _refund,
		"SLCM Payment Request": _settlement,
	}[src.doctype]
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
	if component:
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

	debit_account = conf.require(cfg, "slcm_fee_refund_account")
	if fr.get("fee_component"):
		account, used_default = conf.component_account(cfg, fr.fee_component)
		# Deposits are held as liabilities, so refunding one releases the liability instead of booking an expense.
		if not used_default and frappe.get_cached_value("Account", account, "root_type") in ("Liability", "Asset"):
			debit_account = account

	return {
		"posting_date": getdate(fr.refund_date),
		"cash_account": cash_account,
		"reference": fr.get("utr_number") or fr.name,
		"remark": _("SLCM Fee Refund {0} | {1} | {2} | {3}").format(
			fr.name, fr.student, fr.refund_type, fr.refund_source
		),
		"student": fr.student,
		"programme": _programme_of(None, fr.student),
		"lines": [(debit_account, amount, 0.0), (cash_account, 0.0, amount)],
	}


# ── gateway settlement ──────────────────────────────────────────────────────────


def _settlement(cfg, pr):
	from slcm.erpnext_bridge.sync import settlement_receipt

	fees = flt(pr.gateway_fees, PRECISION)
	tax = flt(pr.gateway_tax, PRECISION)
	net = flt(pr.net_settled, PRECISION) or flt(flt(pr.settlement_amount) - fees - tax, PRECISION)
	gross = flt(net + fees + tax, PRECISION)
	if gross <= 0:
		frappe.throw(_("Settlement amount on {0} is zero").format(pr.name))

	bank = conf.require(cfg, "default_bank_account", _("Razorpay settles into the Company's default bank account"))
	charges = conf.require(cfg, "slcm_gateway_charges_account")
	tax_account = cfg.slcm_gateway_gst_account or charges
	receipt = settlement_receipt(pr.razorpay_payment_id)
	student = frappe.db.get_value("Fee Payment", receipt, "student") if receipt else None

	lines = [(bank, net, 0.0), (charges, fees, 0.0), (tax_account, tax, 0.0)]
	lines.append((conf.gateway_clearing_account(cfg), 0.0, gross))
	return {
		"posting_date": getdate(pr.settlement_date),
		"cash_account": bank,
		"reference": pr.settlement_utr or pr.name,
		"remark": _("Razorpay settlement {0} | payment {1} | Fee Payment {2} | UTR {3}").format(
			pr.name, pr.razorpay_payment_id, receipt or "-", pr.settlement_utr or "-"
		),
		"student": student,
		"programme": _programme_of(None, student),
		"lines": lines,
	}


# ── journal entry ───────────────────────────────────────────────────────────────


def make_journal_entry(cfg, src, entry):
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
			"slcm_reference_doctype": src.doctype,
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

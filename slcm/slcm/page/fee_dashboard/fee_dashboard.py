# Fees Dashboard: amount + count cards for dues, collections, concessions, excess and
# refunds, scoped by Academic Year / Programme / Batch. Each card names the list it
# opens (doctype + filters). Numbers go through DatabaseQuery, so DocPerm, User
# Permissions and permission_query_conditions apply; a doctype the user can't read
# is left out.

import frappe
from frappe import _
from frappe.model.db_query import DatabaseQuery
from frappe.utils import add_days, flt, get_first_day, getdate, today

OPEN_DUES = ["Pending", "Partially Paid", "Overdue"]


def _agg(doctype, filters=None, sums=()):
	"""(count, {field: sum}) for the records the user may read, or None without read access."""
	if not frappe.has_permission(doctype, "read"):
		return None
	t = f"`tab{doctype}`"
	fields = ["count(*) as n"] + [f"sum({t}.`{s}`) as `{s}`" for s in sums]
	row = DatabaseQuery(doctype).execute(fields=fields, filters=filters or {}, order_by=None, as_list=True)[0]
	return row[0] or 0, {s: flt(v) for s, v in zip(sums, row[1:])}


def _card(label, doctype, filters=None, amount=None, hint="", count_label=None):
	"""amount: the field (or list of fields, added up) shown as rupees; None for a count-only card."""
	fields = [amount] if isinstance(amount, str) else list(amount or [])
	res = _agg(doctype, filters, fields)
	if res is None:
		return None
	n, sums = res
	return {
		"label": label, "hint": hint, "doctype": doctype, "filters": filters or {},
		"count": n, "count_label": count_label,
		"amount": sum(sums.values()) if fields else None,
		"drill": doctype in DRILL,
	}


def _group(title, cards, note=""):
	cards = [c for c in cards if c]
	return {"title": title, "note": note, "cards": cards} if cards else None


def current_academic_year():
	return frappe.db.get_value("Academic Year", {"is_current_year": 1}, "name")


def _ay_dates(academic_year):
	if not academic_year:
		return None, None
	return frappe.db.get_value("Academic Year", academic_year, ["year_start_date", "year_end_date"]) or (None, None)


# Breakdown dialog: doctype -> (allowed group-by fields with labels, summed amount fields with labels)
DRILL = {
	"Fee Demand": (
		{"program": "Programme", "programme": "Batch", "fee_component": "Fee component", "status": "Status", "demand_type": "Demand type"},
		{"net_payable": "Demanded", "paid_amount": "Paid", "credit_adjusted": "From excess", "outstanding_amount": "Outstanding"},
	),
	"Fee Payment": (
		{"program": "Programme", "payment_mode": "Payment mode", "payment_gateway": "Gateway", "university_bank_account": "Bank account"},
		{"amount": "Received"},
	),
}


@frappe.whitelist()
def get_breakdown(doctype, filters=None, group_by=None):
	"""One card's records grouped by programme, fee component, mode... with their amounts.
	Only the doctypes and fields in DRILL are allowed; the query applies the user's permissions."""
	if doctype not in DRILL or not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	groups, sums = DRILL[doctype]
	group_by = group_by if group_by in groups else next(iter(groups))
	t = f"`tab{doctype}`"
	fields = [f"{t}.`{group_by}` as g", "count(*) as n"] + [f"sum({t}.`{s}`) as `{s}`" for s in sums]
	rows = DatabaseQuery(doctype).execute(
		fields=fields, filters=frappe.parse_json(filters) or {}, group_by=f"{t}.`{group_by}`",
		order_by=None, as_list=True)
	out = [{"value": r[0], "count": r[1], "sums": {s: flt(v) for s, v in zip(sums, r[2:])}} for r in rows]
	first = next(iter(sums))
	out.sort(key=lambda r: (-r["sums"][first], str(r["value"] or "")))
	return {
		"group_by": group_by,
		"groups": [{"field": k, "label": _(v)} for k, v in groups.items()],
		"sums": [{"field": k, "label": _(v)} for k, v in sums.items()],
		"rows": out,
	}


@frappe.whitelist()
def get_filter_options():
	return {
		"academic_years": frappe.get_list("Academic Year", pluck="name", order_by="year_start_date desc", limit=50),
		"current_academic_year": current_academic_year(),
		"programmes": frappe.get_list("Programme", pluck="name", order_by="name asc", limit=500),
		"batches": frappe.get_list("SLCM Batch", pluck="name", order_by="name desc", limit=500),
	}


@frappe.whitelist()
def get_dashboard(academic_year=None, programme=None, batch=None):
	ay = academic_year or None
	ay_from, ay_to = _ay_dates(ay)

	def dues(**x):
		# Fee Demand: `program` is the Programme, `programme` the Batch
		f = {"status": ["!=", "Cancelled"]}
		if ay:
			f["academic_year"] = ay
		if programme:
			f["program"] = programme
		if batch:
			f["programme"] = batch
		f.update(x)
		return f

	def paid(**x):
		f = {"docstatus": 1}
		if ay:
			f["academic_year"] = ay
		if programme:
			f["program"] = programme
		f.update(x)
		return f

	def in_year(**x):
		f = {"academic_year": ay} if ay else {}
		f.update(x)
		return f

	refund_dates = {"refund_date": ["between", [str(ay_from), str(ay_to)]]} if ay_from and ay_to else {}
	scoped = bool(programme or batch)

	groups = [
		_group(_("Dues"), [
			_card(_("Demanded"), "Fee Demand", dues(), "net_payable", _("after concessions and fines"), _("dues")),
			_card(_("Collected"), "Fee Demand", dues(), ["paid_amount", "credit_adjusted"], _("paid, incl. excess applied"), _("dues")),
			_card(_("Outstanding"), "Fee Demand", dues(status=["in", OPEN_DUES]), "outstanding_amount", _("still to be paid"), _("dues")),
			_card(_("Overdue"), "Fee Demand", dues(status="Overdue"), "outstanding_amount", _("past the due date"), _("dues")),
			_card(_("Due in 7 days"), "Fee Demand",
				dues(status=["in", ["Pending", "Partially Paid"]], due_date=["between", [today(), str(add_days(today(), 7))]]),
				"outstanding_amount", _("reminders go out automatically"), _("dues")),
			_card(_("Paid in full"), "Fee Demand", dues(status="Paid"), "net_payable", "", _("dues")),
		]),
		_group(_("Dues by type"), [
			_card(_("Academic outstanding"), "Fee Demand", dues(status=["in", OPEN_DUES], demand_type="Academic"), "outstanding_amount", "", _("dues")),
			_card(_("Non academic outstanding"), "Fee Demand", dues(status=["in", OPEN_DUES], demand_type="Non Academic"), "outstanding_amount", _("hostel, exam, fines…"), _("dues")),
			_card(_("Fines & penalties"), "Fee Demand", dues(penalty_amount=[">", 0]), "penalty_amount", _("added to dues"), _("dues")),
			_card(_("Raised by events"), "Fee Demand", dues(trigger_ref_doctype=["not in", ["", "Fee Notification"]]), "net_payable",
				_("re-exam, hostel, revaluation…"), _("dues")),
			_card(_("Cancelled"), "Fee Demand", dict(dues(), status="Cancelled"), "original_amount", _("incl. moved to excess"), _("dues")),
		]),
		_group(_("Collections"), [
			_card(_("Payments received"), "Fee Payment", paid(), "amount", _("submitted Fee Payments"), _("payments")),
			_card(_("Online"), "Fee Payment", paid(payment_mode="Online Payment"), "amount", _("Razorpay / Easebuzz"), _("payments")),
			_card(_("Bank transfer"), "Fee Payment", paid(payment_mode="Bank Transfer"), "amount", "", _("payments")),
			_card(_("Cheque / cash / card"), "Fee Payment",
				paid(payment_mode=["in", ["Cheque", "Cash", "Credit Card", "Debit Card", "Other"]]), "amount", "", _("payments")),
			_card(_("Not submitted"), "Fee Payment", dict(paid(), docstatus=0), "amount", _("draft payments, no receipt yet"), _("payments")),
		], _("by the payment's academic year; Batch doesn't apply") if batch else ""),
		_group(_("Concessions & aid"), [
			_card(_("Concessions approved"), "Fee Concession", in_year(docstatus=1), "waiver_value", "", _("concessions")),
			_card(_("Concessions in draft"), "Fee Concession", in_year(docstatus=0), "waiver_value", _("not yet applied to dues"), _("concessions")),
			_card(_("University Financial Aid"), "University Financial Aid", in_year(), "total_financial_aid", _("allocated"), _("students")),
			_card(_("Stipends paid"), "Stipend Payment", in_year(docstatus=1), "amount", "", _("payments")),
		], _("Programme and Batch don't apply") if scoped else ""),
		_group(_("Excess & refunds"), [
			_card(_("Excess held"), "Student Credit Note", {"status": "Active", "available_credit": [">", 0]}, "available_credit",
				_("money students can use or get back"), _("credit notes")),
			_card(_("Refunds paid"), "Fee Refund", dict(refund_dates, docstatus=1), "refund_amount", "", _("refunds")),
			_card(_("Refunds in draft"), "Fee Refund", dict(refund_dates, docstatus=0), "refund_amount", _("waiting for approval"), _("refunds")),
		], _("Programme and Batch don't apply; excess is for any year")),
		_group(_("Setup"), [
			_card(_("Fee components"), "Fee Component", {}, hint=_("what can be charged")),
			_card(_("Active fee structures"), "Fee Structure", in_year(status="Active", applicable="Student"),
				hint=_("one per programme, year and category")),
			_card(_("Fee notifications"), "Fee Notification", in_year(), hint=_("bulk demand runs")),
			_card(_("Students without a fee structure"), "Student Master", {"student_status": "Active", "fee_structure": ["is", "not set"]},
				hint=_("active students")),
		], _("any programme")),
	]
	return {
		"filters": {"academic_year": ay, "programme": programme, "batch": batch},
		"groups": [g for g in groups if g],
	}


@frappe.whitelist()
def get_home():
	"""Numbers for the Fees workspace home block: collections, attention items and setup."""
	d = today()
	ay = current_academic_year()
	month = str(get_first_day(d))

	def amt(doctype, filters, field):
		res = _agg(doctype, filters, [field])
		return None if res is None else {"count": res[0], "amount": res[1][field]}

	def cnt(doctype, filters=None):
		res = _agg(doctype, filters)
		return None if res is None else res[0]

	open_ay = {"status": ["in", OPEN_DUES]}
	if ay:
		open_ay["academic_year"] = ay
	try:
		reminders = frappe.db.get_single_value("Student Portal Settings", "enable_fee_reminders")
		reminders = 1 if reminders in (None, "") else int(reminders)
	except Exception:
		reminders = None

	return {
		"academic_year": ay,
		"tiles": {
			"today": amt("Fee Payment", {"docstatus": 1, "payment_date": d}, "amount"),
			"month": amt("Fee Payment", {"docstatus": 1, "payment_date": ["between", [month, d]]}, "amount"),
			"outstanding": amt("Fee Demand", open_ay, "outstanding_amount"),
			"overdue": amt("Fee Demand", dict(open_ay, status="Overdue"), "outstanding_amount"),
			"due_week": amt("Fee Demand", dict(open_ay, status=["in", ["Pending", "Partially Paid"]],
				due_date=["between", [d, str(add_days(d, 7))]]), "outstanding_amount"),
			"excess": amt("Student Credit Note", {"status": "Active", "available_credit": [">", 0]}, "available_credit"),
		},
		"attention": {
			"draft_payments": cnt("Fee Payment", {"docstatus": 0}),
			"draft_concessions": cnt("Fee Concession", {"docstatus": 0}),
			"draft_refunds": cnt("Fee Refund", {"docstatus": 0}),
			"overdue": cnt("Fee Demand", {"status": "Overdue"}),
			"not_generated": cnt("Fee Notification", {"status": "Published", "generation_log": ["is", "not set"]}),
			"failed_online": cnt("Online Payment Log", {"status": "Failed", "creation": [">=", str(add_days(d, -30))]}),
			"no_structure": cnt("Student Master", {"student_status": "Active", "fee_structure": ["is", "not set"]}),
			"certificates": cnt("Fee Certificate Request", {"status": "Draft"}),
		},
		"setup": {
			"Fee Component": cnt("Fee Component"),
			"Fee Structure": cnt("Fee Structure", {"status": "Active", "applicable": "Student"}),
			"Fee Notification": cnt("Fee Notification", dict({"status": "Published"}, **({"academic_year": ay} if ay else {}))),
			"Payment Gateway": cnt("Payment Gateway"),
			"reminders": reminders if frappe.has_permission("Student Portal Settings", "read") else None,
		},
	}

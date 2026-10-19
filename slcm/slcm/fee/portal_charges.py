"""Re-examination fees and hostel fines as rows for the student / parent portal fee Summary.

Unpaid ones are listed with the other outstanding charges; paid ones are listed too, with a
receipt to download:
* when the charge has a Fee Demand (event hooks raise one) and that demand was paid through a
  Fee Receipt, that receipt;
* a re-exam paid online (Razorpay, no Fee Receipt) gets the Re Exam Receipt print of its
  registration (slcm.api.student_portal.download_re_exam_receipt);
* a hostel fine marked paid at the office without a Fee Receipt has nothing to download.
"""

import frappe
from frappe.utils import flt, formatdate


def _fmt_inr(amount):
	return "₹{:,.0f}".format(flt(amount))


def _linked_demands(student, doctype, names):
	"""{trigger name: latest non-cancelled Fee Demand (name, status)} for these records."""
	if not names:
		return {}
	rows = frappe.get_all(
		"Fee Demand",
		filters={
			"student": student,
			"trigger_ref_doctype": doctype,
			"trigger_ref_name": ["in", list(names)],
			"status": ["!=", "Cancelled"],
		},
		fields=["name", "trigger_ref_name", "status"],
		order_by="creation asc",
		ignore_permissions=True,
	)
	return {r.trigger_ref_name: r for r in rows}


def _receipts_for_demands(demand_names):
	"""{fee demand: latest active Fee Receipt that paid it}."""
	if not demand_names:
		return {}
	rows = frappe.db.sql(
		"""SELECT rdp.fee_demand, fr.name
		FROM `tabFee Receipt Demands Paid` rdp
		JOIN `tabFee Receipt` fr ON fr.name = rdp.parent AND rdp.parenttype = 'Fee Receipt'
		WHERE rdp.fee_demand IN %(demands)s AND IFNULL(fr.status, '') != 'Cancelled'
		ORDER BY fr.receipt_date ASC, fr.creation ASC""",
		{"demands": tuple(demand_names)},
		as_dict=True,
	)
	return {r.fee_demand: r.name for r in rows}


def re_exam_and_fine_rows(student, re_exams, fines):
	"""Summary rows for the student's re-exam registrations and hostel fines.

	Each row: component, sub, kind ("reexam" / "fine"), demand_type, due_date(_fmt), amount_fmt,
	status, is_paid, is_overdue, days_overdue, receipt (Fee Receipt name), re_exam_receipt
	(registration name, for the generated receipt); re-exam rows also carry registration,
	exam_plan, course and can_pay for the online Pay button. A charge whose Fee Demand is still unpaid
	is left out here: that demand is already listed with the other charges.
	"""
	re_exams = re_exams or []
	fines = fines or []
	rex_demands = _linked_demands(student, "Re Exam Registration", [r.name for r in re_exams])
	fine_demands = _linked_demands(student, "Hostel Fine", [f.name for f in fines])
	receipts = _receipts_for_demands(
		[d.name for d in list(rex_demands.values()) + list(fine_demands.values())]
	)

	rows = []
	for r in re_exams:
		if flt(r.re_exam_fee) <= 0 or r.payment_status == "Cancelled":
			continue
		demand = rex_demands.get(r.name)
		paid_online = r.payment_status in ("Paid", "Captured")
		paid = paid_online or (demand and demand.status == "Paid")
		if not paid and demand:
			continue
		receipt = receipts.get(demand.name) if demand else None
		rows.append(frappe._dict(
			component=r.get("course_name") or r.course or "Re-examination fee",
			sub="Re-examination fee" + (f" · {r.exam_plan}" if r.get("exam_plan") else ""),
			kind="reexam", demand_type="Academic", due_date=None, due_date_fmt="",
			amount=flt(r.re_exam_fee), amount_fmt=_fmt_inr(r.re_exam_fee),
			status="Paid" if paid else (r.payment_status or "Pending"),
			is_paid=bool(paid), is_overdue=False, days_overdue=0,
			receipt=receipt or "",
			re_exam_receipt=r.name if (paid_online and not receipt) else "",
			# For the portal's online Pay button (same rule as the old Re-Examination Fees card)
			registration=r.name, exam_plan=r.exam_plan or "", course=r.course or "",
			can_pay=not paid and r.payment_status in ("Pending", "Payment Failed", "Payment Initiated", "Failed"),
		))
	for f in fines:
		if flt(f.amount) <= 0 or f.status not in ("Unpaid", "Paid"):
			continue
		demand = fine_demands.get(f.name)
		paid = f.status == "Paid" or (demand and demand.status == "Paid")
		if not paid and demand:
			continue
		rows.append(frappe._dict(
			component=f.reason or "Hostel fine",
			sub="Hostel fine" + (f" · {formatdate(f.fine_date, 'dd MMM yyyy')}" if f.fine_date else ""),
			kind="fine", demand_type="Non Academic", due_date=None, due_date_fmt="",
			amount_fmt=_fmt_inr(f.amount), status="Paid" if paid else "Unpaid",
			is_paid=bool(paid), is_overdue=False, days_overdue=0,
			receipt=(receipts.get(demand.name) if demand else None) or "",
			re_exam_receipt="",
		))
	return rows


def get_re_exams_and_fines(student):
	"""The registered re-exams and the unpaid / paid hostel fines of a student."""
	re_exams = frappe.get_all(
		"Re Exam Registration",
		filters={"student": student, "status": "Registered"},
		fields=["name", "exam_plan", "course", "re_exam_fee", "payment_status"],
		order_by="creation desc",
		ignore_permissions=True,
	)
	for r in re_exams:
		r["course_name"] = frappe.db.get_value("Course", r.course, "course_name") or r.course or ""
	fines = frappe.get_all(
		"Hostel Fine",
		filters={"student": student, "status": ["in", ["Unpaid", "Paid"]]},
		fields=["name", "reason", "amount", "fine_date", "status"],
		order_by="fine_date desc",
		ignore_permissions=True,
	)
	return re_exams, fines


# Transcript Request stores "Final Transcript" but students see "Provisional Transcript"
_TRANSCRIPT_LABELS = {"Final Transcript": "Provisional Transcript"}


def transcript_and_improvement_rows(student):
	"""Paid transcript request fees and paid improvement exam fees as Summary rows.

	Both are paid online (Razorpay) without a Fee Demand, so they would otherwise be missing
	from the fee list. Each row carries receipt_kind ("transcript" / "improvement") and
	receipt_doc for its generated receipt, and a payment detail. Unpaid ones are left out: an
	unpaid transcript request or improvement registration is an abandoned or cancelled checkout,
	not a due. One that has a Fee Demand is left to that demand."""
	requests = frappe.get_all(
		"Transcript Request",
		filters={"student": student, "payment_required": 1, "payment_status": "Paid", "fee_amount": [">", 0]},
		fields=["name", "transcript_type", "num_copies", "fee_amount", "payment_date", "payment_reference",
		        "requested_on", "academic_year"],
		order_by="creation desc",
		ignore_permissions=True,
	)
	improvements = frappe.get_all(
		"Improvement Exam Registration",
		filters={"student": student, "status": "Registered", "payment_status": ["in", ["Paid", "Captured"]],
		         "improvement_fee": [">", 0]},
		fields=["name", "exam_plan", "course", "improvement_fee", "payment_reference"],
		order_by="creation desc",
		ignore_permissions=True,
	)
	linked = set(_linked_demands(student, "Transcript Request", [r.name for r in requests]).keys())
	linked |= set(_linked_demands(student, "Improvement Exam Registration", [r.name for r in improvements]).keys())

	logs = {}
	if improvements:
		for log in frappe.get_all(
			"Improvement Exam Payment Log",
			filters={"improvement_exam_registration": ["in", [r.name for r in improvements]], "payment_status": "Paid"},
			fields=["improvement_exam_registration", "transaction_date", "amount", "payment_method", "razorpay_payment_id"],
			order_by="creation asc",
			ignore_permissions=True,
		):
			logs.setdefault(log.improvement_exam_registration, []).append(log)

	def row(group, kind, component, sub, amount, doc, details):
		return frappe._dict(
			group=group, kind=kind, component=component, sub=sub,
			due_date=None, due_date_fmt="", days_overdue=0,
			amount=flt(amount), paid=flt(amount), waiver=0, outstanding=0, status="Paid",
			receipt="", re_exam_receipt="", receipt_kind=kind, receipt_doc=doc, invoice="",
			academic_year="", can_pay=False, is_paid=True, details=details,
		)

	rows = []
	for r in requests:
		if r.name in linked:
			continue
		label = _TRANSCRIPT_LABELS.get(r.transcript_type, r.transcript_type) or "Transcript"
		copies = int(r.num_copies or 1)
		ref = r.payment_reference or ""
		pay = _detail(
			"payment", r.payment_date, "Payment",
			" · ".join(filter(None, ["Online" if ref.startswith("pay_") else "", ref, r.name])),
			r.fee_amount, "Paid", receipt_kind="transcript", receipt_doc=r.name,
		)
		rows.append(row(
			"Non Academic", "transcript", label,
			"Transcript request · " + r.name + (f" · {copies} copies" if copies > 1 else ""),
			r.fee_amount, r.name, [pay],
		))

	course_names = {}
	for r in improvements:
		if r.name in linked:
			continue
		if r.course and r.course not in course_names:
			course_names[r.course] = frappe.db.get_value("Course", r.course, "course_name") or r.course
		details = [
			_detail(
				"payment", log.transaction_date, "Payment",
				" · ".join(filter(None, [(log.payment_method or "Online").title(), log.razorpay_payment_id])),
				log.amount or r.improvement_fee, "Paid", receipt_kind="improvement", receipt_doc=r.name,
			)
			for log in logs.get(r.name, [])
		]
		rows.append(row(
			"Academic", "improvement", course_names.get(r.course) or "Improvement examination fee",
			"Improvement examination fee" + (f" · {r.exam_plan}" if r.exam_plan else ""),
			r.improvement_fee, r.name, details,
		))
	return rows



def demand_type_cards(demands):
	"""The Summary cards (Total Levied / Settled / Scholarship / Outstanding) split into Academic
	and Non Academic, with the same figures the combined cards used. Any demand type other than
	"Academic" (Non Academic, Fine, Examination…) counts as Non Academic. Only groups with demands."""
	groups = []
	for label in ("Academic", "Non Academic"):
		rows = [d for d in demands or [] if (d.get("demand_type") == "Academic") == (label == "Academic")]
		if not rows:
			continue
		open_rows = [d for d in rows if d.status not in ("Paid", "Waived", "Cancelled")]
		overdue = sum(1 for d in open_rows if d.status == "Overdue" or d.get("is_demand_overdue"))
		outstanding = sum(flt(d.outstanding_amount) for d in open_rows)
		groups.append(frappe._dict(
			label=label,
			count=len(rows),
			total_fmt=_fmt_inr(sum(flt(d.net_payable) for d in rows)),
			paid_amt=sum(flt(d.paid_amount) + flt(d.credit_adjusted) for d in rows),
			paid_count=sum(1 for d in rows if d.status == "Paid"),
			waived_fmt=_fmt_inr(sum(flt(d.waiver_amount) for d in rows)),
			outstanding=outstanding,
			outstanding_fmt=_fmt_inr(outstanding),
			overdue=overdue,
			pending=len(open_rows) - overdue,
		))
	for g in groups:
		g["paid_fmt"] = _fmt_inr(g.paid_amt)
	return groups


def _group(demand_type):
	return "Academic" if demand_type == "Academic" else "Non Academic"


def charge_rows(student, demands, invoices, re_exams, fines):
	"""Every charge for the fee Summary, paid ones included: Fee Demands, programme fee
	invoices, re-exam fees and hostel fines. Each row: group ("Academic" / "Non Academic"),
	kind, component, sub, due_date_fmt, days_overdue, amount, paid, waiver, outstanding
	(numbers and *_fmt), status, status_key (paid / pending / overdue), receipt (Fee Receipt),
	re_exam_receipt, invoice, academic_year, plus the re-exam Pay fields. A re-exam fee or
	hostel fine with a Fee Demand is represented by that demand."""
	flt_ = flt
	demands = [d for d in demands or [] if d.status != "Cancelled"]
	receipts = _receipts_for_demands([d.name for d in demands])
	rows = []

	for d in demands:
		status = "Overdue" if (d.get("is_demand_overdue") and d.status == "Pending") else d.status
		trigger = (d.get("trigger_ref_doctype") or "").replace("Course Reregistration", "Re-registration")
		rows.append(frappe._dict(
			group=_group(d.get("demand_type")), kind="demand",
			component=d.fee_component or d.description or "Charge",
			sub=(d.description if d.description and d.description != d.fee_component else (trigger or "Additional charge")),
			due_date=d.due_date, due_date_fmt=d.get("due_date_fmt") or "", days_overdue=d.get("days_overdue") or 0,
			amount=flt_(d.net_payable), paid=flt_(d.paid_amount) + flt_(d.credit_adjusted),
			waiver=flt_(d.waiver_amount),
			outstanding=0 if d.status in ("Paid", "Waived") else flt_(d.outstanding_amount),
			status=status, receipt=receipts.get(d.name) or "", re_exam_receipt="", invoice="",
			academic_year=d.get("academic_year") or "", can_pay=False, demand_name=d.name,
		))

	for inv in invoices or []:
		if (inv.get("display_status") or inv.status) == "Cancelled":
			continue
		rcpts = inv.get("receipts") or []
		out = flt_(inv.get("eff_outstanding") if inv.get("eff_outstanding") is not None else inv.outstanding_amount)
		rows.append(frappe._dict(
			group="Academic", kind="invoice", component=inv.get("label") or "Programme Fee", sub=inv.name,
			due_date=inv.due_date, due_date_fmt=inv.get("due_date_fmt") or "", days_overdue=0,
			amount=flt_(inv.get("final_payable_amount") or inv.get("total_amount")), paid=flt_(inv.get("paid_amount")),
			waiver=flt_(inv.get("scholarship_amount")), outstanding=out,
			status=inv.get("display_status") or inv.status or "Unpaid",
			receipt=(rcpts[-1].receipt_name if rcpts else ""), re_exam_receipt="", invoice=inv.name,
			academic_year=inv.get("academic_year") or "", can_pay=False,
		))

	linked = set()
	for doctype, recs in (("Re Exam Registration", re_exams or []), ("Hostel Fine", fines or [])):
		linked |= set(_linked_demands(student, doctype, [r.name for r in recs]).keys())
	for r in re_exam_and_fine_rows(student, [x for x in re_exams or [] if x.name not in linked],
	                               [x for x in fines or [] if x.name not in linked]):
		amount = flt_(r.get("amount")) or flt_(str(r.amount_fmt).replace("₹", "").replace(",", ""))
		r.update(
			group=_group(r.demand_type), amount=amount, paid=amount if r.is_paid else 0, waiver=0,
			outstanding=0 if r.is_paid else amount, invoice="", academic_year="",
		)
		rows.append(r)

	try:
		rows += transcript_and_improvement_rows(student)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Portal Fees: transcript / improvement rows")

	for r in rows:
		r["status_key"] = "paid" if r.status in ("Paid", "Waived") or (r.outstanding <= 0 and r.paid > 0) else (
			"overdue" if r.status == "Overdue" else "pending")
		# Amount before scholarship: Amount − Scholarship − Paid = Outstanding on every row
		r["gross"] = r.amount + r.waiver
		for k in ("amount", "paid", "outstanding", "waiver", "gross"):
			r[k + "_fmt"] = _fmt_inr(r[k])
	today = frappe.utils.getdate()
	rows.sort(key=lambda r: (
		r.group != "Academic", r.status_key == "paid",
		frappe.utils.getdate(r.due_date) if r.get("due_date") else today,
	))
	_attach_details(student, rows, invoices)
	return rows


def _fmt_date(value):
	return formatdate(value, "dd MMM yyyy") if value else ""


def _detail(kind, date, title, sub, amount, status, receipt="", re_exam_receipt="", sign="",
            receipt_kind="", receipt_doc=""):
	return frappe._dict(
		kind=kind, date=date, date_fmt=_fmt_date(date), title=title, sub=sub,
		amount_fmt=sign + _fmt_inr(amount), status=status, receipt=receipt, re_exam_receipt=re_exam_receipt,
		receipt_kind=receipt_kind, receipt_doc=receipt_doc,
	)


def _attach_details(student, rows, invoices):
	"""Give each Summary row its payments, refunds and scholarships (row.details), so the fee
	list shows them under the component. Anything not tied to one fee (a receipt with no
	demand lines, a refund from excess, an unlinked concession, credit notes) goes on an
	"Other" row at the end."""
	for r in rows:
		r["details"] = r.get("details") or []
	demand_rows = {r.demand_name: r for r in rows if r.get("demand_name")}
	other = []

	# Payments: Fee Receipt lines allocated to each demand
	for p in frappe.db.sql(
		"""SELECT fr.name, fr.receipt_date, fr.payment_mode, fr.reference_number, fr.amount AS receipt_amount,
			rdp.fee_demand, rdp.amount, rdp.description
		FROM `tabFee Receipt` fr
		LEFT JOIN `tabFee Receipt Demands Paid` rdp ON rdp.parent = fr.name AND rdp.parenttype = 'Fee Receipt'
		WHERE fr.student = %s AND IFNULL(fr.status, '') != 'Cancelled'
		ORDER BY fr.receipt_date DESC, fr.creation DESC""",
		(student,),
		as_dict=True,
	):
		row = demand_rows.get(p.fee_demand)
		d = _detail(
			"payment", p.receipt_date, "Payment", " · ".join(filter(None, [p.payment_mode, p.reference_number, p.name])),
			p.amount if p.fee_demand else p.receipt_amount, "Paid", receipt=p.name,
		)
		if row:
			row.details.append(d)
		elif not any(p.name == (r.get("receipt") or "") for r in rows if r.kind == "invoice"):
			# no demand lines, or paid towards a demand that has since been cancelled
			d.title = p.description or "Payment"
			other.append(d)

	# Invoice payments (programme fee) come with the invoice itself
	inv_rows = {r.invoice: r for r in rows if r.kind == "invoice"}
	for inv in invoices or []:
		row = inv_rows.get(inv.name)
		if not row:
			continue
		rcpts = inv.get("receipts") or []
		for i, pay in enumerate(inv.get("payments") or []):
			if pay.get("is_rzp_only"):
				continue
			rc = rcpts[i].receipt_name if i < len(rcpts) else ""
			row.details.append(_detail(
				"payment", pay.get("payment_date"), "Payment",
				" · ".join(filter(None, [pay.get("payment_mode"), pay.get("reference_number")])),
				pay.get("amount"), "Paid", receipt=rc,
			))

	# Re-exam fees paid online: the payment log
	for r in rows:
		if r.kind == "reexam" and r.get("re_exam_receipt"):
			for log in frappe.get_all(
				"Re Exam Payment Log",
				filters={"re_exam_registration": r.registration, "payment_status": "Paid"},
				fields=["transaction_date", "amount", "payment_method", "razorpay_payment_id"],
				ignore_permissions=True,
			):
				r.details.append(_detail(
					"payment", log.transaction_date, "Payment",
					" · ".join(filter(None, [(log.payment_method or "Online").title(), log.razorpay_payment_id])),
					log.amount, "Paid", re_exam_receipt=r.registration,
				))

	# Refunds
	for f in frappe.get_all(
		"Fee Refund",
		filters={"student": student, "docstatus": ["!=", 2]},
		fields=["name", "fee_demand", "refund_type", "refund_amount", "refund_date", "refund_mode", "utr_number", "status"],
		order_by="refund_date desc",
		ignore_permissions=True,
	):
		d = _detail(
			"refund", f.refund_date, f.refund_type or "Refund",
			" · ".join(filter(None, [f.refund_mode, f.utr_number and f"UTR {f.utr_number}", f.name])),
			f.refund_amount, f.status or "Draft", sign="+",
		)
		row = demand_rows.get(f.fee_demand)
		(row.details if row else other).append(d)

	# Scholarships / concessions
	for c in frappe.get_all(
		"Fee Concession",
		filters={"student": student, "docstatus": ["!=", 2]},
		fields=["name", "fee_demand", "fee_component", "concession_type", "waiver_amount", "status", "approved_on", "reason"],
		order_by="approved_on desc",
		ignore_permissions=True,
	):
		d = _detail(
			"scholarship", c.approved_on, c.concession_type or "Concession",
			" · ".join(filter(None, [c.reason, c.name])), c.waiver_amount, c.status or "Draft", sign="−",
		)
		row = demand_rows.get(c.fee_demand) or (
			None if c.fee_demand else next((r for r in rows if r.kind == "demand" and r.component == c.fee_component), None)
		)
		if row:
			row.details.append(d)
		else:
			d.title = f"{d.title} – {c.fee_component}" if c.fee_component else d.title
			other.append(d)

	# Excess / advance credit
	for cn in frappe.get_all(
		"Student Credit Note",
		filters={"student": student, "docstatus": 1},
		fields=["name", "credit_type", "credit_amount", "available_credit", "status", "creation"],
		order_by="creation desc",
		ignore_permissions=True,
	):
		other.append(_detail(
			"credit", cn.creation, cn.credit_type or "Credit",
			f"{cn.name} · {_fmt_inr(cn.available_credit)} available", cn.credit_amount, cn.status,
		))

	for r in rows:
		r.details.sort(key=lambda d: frappe.utils.getdate(d.date) if d.date else frappe.utils.getdate("1900-01-01"), reverse=True)
	if other:
		rows.append(frappe._dict(
			group="Other", kind="other", component="Payments, refunds and credit",
			sub="Not tied to a single fee", due_date=None, due_date_fmt="", days_overdue=0,
			amount=0, paid=0, waiver=0, outstanding=0, status="", status_key="", receipt="", re_exam_receipt="",
			invoice="", academic_year="", can_pay=False, details=other,
			amount_fmt="", paid_fmt="", outstanding_fmt="", waiver_fmt="", gross=0, gross_fmt="",
		))


def charge_cards(rows):
	"""Overall, Academic and Non Academic card figures from the Summary rows."""
	def card(label, rs):
		overdue = sum(1 for r in rs if r.status_key == "overdue")
		pending = sum(1 for r in rs if r.status_key == "pending")
		outstanding = sum(r.outstanding for r in rs)
		paid = sum(r.paid for r in rs)
		return frappe._dict(
			label=label, count=len(rs), total_fmt=_fmt_inr(sum(r.gross for r in rs)),
			paid_amt=paid, paid_fmt=_fmt_inr(paid), paid_count=sum(1 for r in rs if r.status_key == "paid"),
			waived_fmt=_fmt_inr(sum(r.waiver for r in rs)), outstanding=outstanding,
			outstanding_fmt=_fmt_inr(outstanding), overdue=overdue, pending=pending,
		)
	rows = [r for r in rows if r.group != "Other"]  # the "Other" row holds only payments / refunds / credit
	cards = [card("Overall", rows)] if rows else []
	for label in ("Academic", "Non Academic"):
		rs = [r for r in rows if r.group == label]
		if rs:
			cards.append(card(label, rs))
	return cards

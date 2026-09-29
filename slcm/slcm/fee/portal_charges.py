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

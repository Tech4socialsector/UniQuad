"""Exam fees paid at the counter (cash, cheque, bank transfer): 'Mark as Paid' on a Re Exam / Improvement Exam
Registration records how and when the money came in as a payment log, the same record an online payment leaves.
A counter log has no gateway and no gateway payment id; the ERPNext bridge posts it to the mode's cash / bank
ledger (slcm.erpnext_bridge)."""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, now_datetime, today

# registration -> (payment log, link field on the log, fee field on the registration)
EXAMS = {
	"Re Exam Registration": ("Re Exam Payment Log", "re_exam_registration", "re_exam_fee"),
	"Improvement Exam Registration": ("Improvement Exam Payment Log", "improvement_exam_registration", "improvement_fee"),
}
ONLINE_MODE = "Online Payment"


def counter_modes():
	field = frappe.get_meta("Fee Payment").get_field("payment_mode")
	return [m.strip() for m in (field.options or "").split("\n") if m.strip() and m.strip() != ONLINE_MODE]


@frappe.whitelist()
def get_counter_modes():
	return counter_modes()


@frappe.whitelist()
def record_counter_payment(doctype, name, payment_mode, payment_date=None, reference=None):
	if doctype not in EXAMS:
		frappe.throw(_("Counter payments are recorded for exam registrations only"))
	if payment_mode not in counter_modes():
		frappe.throw(_("Choose how the money was received: {0}").format(", ".join(counter_modes())))
	date = getdate(payment_date or today())
	if date > getdate(today()):
		frappe.throw(_("Payment date cannot be in the future"))

	log_doctype, link_field, fee_field = EXAMS[doctype]
	reg = frappe.get_doc(doctype, name)
	reg.check_permission("write")
	if reg.payment_status in ("Paid", "Captured", "Refunded") or reg.status == "Cancelled":
		frappe.throw(_("{0} is already {1}").format(name, reg.status if reg.status == "Cancelled" else reg.payment_status))
	amount = flt(reg.get(fee_field), 2)
	if amount <= 0:
		frappe.throw(_("{0} has no fee to collect").format(name))

	paid_at = now_datetime() if date == getdate(today()) else get_datetime(f"{date} 00:00:00")
	log = frappe.get_doc(
		{
			"doctype": log_doctype,
			link_field: name,
			"student": reg.student,
			"exam_plan": reg.get("exam_plan"),
			"course": reg.get("course"),
			"academic_term": reg.get("academic_term"),
			"payment_status": "Paid",
			"amount": amount,
			"payment_method": payment_mode,
			"transaction_id": (reference or "").strip()[:140],
			"transaction_date": paid_at,
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value(
		doctype, name, {"payment_status": "Paid", "payment_reference": (reference or "").strip() or log.name}
	)
	return log.name

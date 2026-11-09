"""Which online payment gateway collects a given student/parent portal charge.

The gateway is configured where the charge is defined, never chosen by the payer:
* Fee Demand               → its Fee Component's ``payment_gateway``
* Fee Invoice (programme)  → its Fee Structure's Payment Gateway, else its components'
* Re-exam fee               → Re Exam Course Setting (exam plan + course)
* Improvement exam fee      → Improvement Exam Course Setting (exam plan + course)
* Transcript fee            → Transcript Fee Settings

Anything unset falls back to Razorpay, so records created before the field existed keep
working exactly as before. Admission flows (PACE / FLE / NLSAT) do not use this module.
"""

import frappe
from frappe import _

RAZORPAY = "Razorpay"
EASEBUZZ = "Easebuzz"
GATEWAYS = (RAZORPAY, EASEBUZZ)
DEFAULT_GATEWAY = RAZORPAY


def normalize(gateway):
	return gateway if gateway in GATEWAYS else DEFAULT_GATEWAY


def for_component(fee_component):
	if not fee_component:
		return DEFAULT_GATEWAY
	return normalize(frappe.db.get_value("Fee Component", fee_component, "payment_gateway"))


def for_demand(fee_demand):
	return for_component(frappe.db.get_value("Fee Demand", fee_demand, "fee_component"))


def for_fee_structure(fee_structure):
	"""The Fee Structure's online Payment Gateway, or None when it has none we can collect through."""
	if not fee_structure:
		return None
	fs = frappe.db.get_value("Fee Structure", fee_structure, ["online_payment", "payment_gateway"], as_dict=True)
	if fs and fs.online_payment and fs.payment_gateway in GATEWAYS:
		return fs.payment_gateway
	return None


def _invoice_fee_structure(invoice_name):
	"""The Fee Structure an invoice was priced from: its Student Fee Assignment's, else the student's."""
	inv = frappe.db.get_value("Fee Invoice", invoice_name, ["fee_assignment", "student"], as_dict=True)
	if not inv:
		return None
	return (
		inv.fee_assignment and frappe.db.get_value("Student Fee Assignment", inv.fee_assignment, "fee_structure")
	) or (inv.student and frappe.db.get_value("Student Master", inv.student, "fee_structure"))


def for_invoice(invoice_name):
	"""Gateway of a programme-fee invoice: its Fee Structure's Payment Gateway; without one, the gateway
	of the invoice's components, which must all agree (one checkout per invoice)."""
	gateway = for_fee_structure(_invoice_fee_structure(invoice_name))
	if gateway:
		return gateway
	components = frappe.get_all(
		"Fee Component Child",
		filters={"parent": invoice_name, "parenttype": "Fee Invoice"},
		pluck="fee_component",
		ignore_permissions=True,
	)
	gateways = {for_component(c) for c in components if c} or {DEFAULT_GATEWAY}
	if len(gateways) > 1:
		frappe.throw(
			_(
				"Invoice {0} has fee components collected through different payment gateways ({1}). "
				"Please contact the Bursar's Office."
			).format(invoice_name, ", ".join(sorted(gateways))),
			title=_("Payment Gateway Conflict"),
		)
	return gateways.pop()


def for_re_exam(exam_plan, course):
	return normalize(
		frappe.db.get_value("Re Exam Course Setting", {"exam_plan": exam_plan, "course": course}, "payment_gateway")
	)


def for_improvement_exam(exam_plan, course):
	return normalize(
		frappe.db.get_value(
			"Improvement Exam Course Setting", {"exam_plan": exam_plan, "course": course}, "payment_gateway"
		)
	)


def for_transcript():
	if not frappe.db.exists("DocType", "Transcript Fee Settings"):
		return DEFAULT_GATEWAY
	return normalize(frappe.db.get_single_value("Transcript Fee Settings", "payment_gateway"))


def is_ready(gateway):
	"""True when the gateway has credentials (and, for Easebuzz, is switched on)."""
	try:
		if gateway == EASEBUZZ:
			if not frappe.db.exists("DocType", "Easebuzz Settings"):
				return False
			return bool(
				frappe.db.get_single_value("Easebuzz Settings", "enabled")
				and frappe.db.get_single_value("Easebuzz Settings", "merchant_key")
			)
		return bool(frappe.db.get_single_value("Razorpay Settings", "api_key"))
	except Exception:
		return False


def ensure_ready(gateway):
	if not is_ready(gateway):
		frappe.throw(
			_("Online payment through {0} is not set up yet. Please contact the Bursar's Office.").format(gateway),
			title=_("Payment Unavailable"),
		)

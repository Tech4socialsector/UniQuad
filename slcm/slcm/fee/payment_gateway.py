"""Which online payment gateway collects a given student/parent portal charge.

The gateway is configured where the charge is defined, never chosen by the payer:
* Fee Demand / Fee Invoice  → its Fee Component's ``payment_gateway``
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


def for_invoice(invoice_name):
	"""Gateway of an invoice's components; they must all agree (one checkout per invoice)."""
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

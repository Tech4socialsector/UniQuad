"""Repair payment statuses saved with values their Select fields do not allow (written with db.set_value,
so never validated). Left as they were, the next save of the record fails, and the ERPNext bridge misreads them.

* Fee Invoice.payment_status "Pending" -> blank (no payment in flight).
* SLCM Payment Request.settlement_status of student / parent requests: Razorpay's raw word written by the old
  daily settlement sync -> SLCM's own value ("processed" -> "Settled", "created" -> "Processing",
  "failed" -> "Failed"), keeping Razorpay's word in gateway_settlement_status. Admission requests are untouched.
"""

import frappe


def execute():
	frappe.db.sql("update `tabFee Invoice` set payment_status = '' where payment_status = 'Pending'")

	from slcm.slcm.fee.payment_ledger import LEDGER_DOCTYPES

	for raw, value in (("processed", "Settled"), ("created", "Processing"), ("failed", "Failed")):
		frappe.db.sql(
			"""update `tabSLCM Payment Request`
			set settlement_status = %(value)s, gateway_settlement_status = %(raw)s
			where settlement_status = %(raw)s and reference_doctype in %(doctypes)s""",
			{"value": value, "raw": raw, "doctypes": tuple(LEDGER_DOCTYPES)},
		)

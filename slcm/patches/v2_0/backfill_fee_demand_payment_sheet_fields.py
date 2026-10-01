import frappe


def execute():
	"""Fill the Fee Demand / Fee Payment fields added to match the bulk-upload sheets on existing records.

	Fee Payment: Voucher Number + the voucher's static details for payments that cover exactly one due.
	"Paid / Pending before this payment" are not backfilled — those historical values are unknown.
	"""
	frappe.reload_doc("slcm", "doctype", "fee_demand")
	frappe.reload_doc("slcm", "doctype", "fee_payment")

	students = {
		s.name: s
		for s in frappe.get_all(
			"Student Master", fields=["name", "registration_id", "application_number", "official_email_id", "email"]
		)
	}
	email = lambda s: s and (s.official_email_id or s.email)

	for d in frappe.get_all("Fee Demand", filters={"student_email": ["in", ["", None]]}, fields=["name", "student"]):
		if email(students.get(d.student)):
			frappe.db.set_value("Fee Demand", d.name, "student_email", email(students[d.student]), update_modified=False)

	rows = frappe.get_all(
		"Fee Payment Demand Row", filters={"parenttype": "Fee Payment"}, fields=["parent", "fee_demand"]
	)
	by_payment = {}
	for r in rows:
		by_payment.setdefault(r.parent, []).append(r.fee_demand)

	for p in frappe.get_all("Fee Payment", fields=["name", "student", "fee_demand"]):
		values = {}
		s = students.get(p.student)
		if s:
			values["registration_id"] = s.registration_id or s.application_number
			values["student_email"] = email(s)
		vouchers = by_payment.get(p.name, [])
		if not p.fee_demand and len(vouchers) == 1 and vouchers[0]:
			d = frappe.db.get_value(
				"Fee Demand",
				vouchers[0],
				["fee_component", "demand_date", "due_date", "remarks", "description", "original_amount",
				 "penalty_amount", "waiver_amount", "net_payable"],
				as_dict=True,
			)
			if d:
				values.update({
					"fee_demand": vouchers[0],
					"fee_component": d.fee_component,
					"demand_date": d.demand_date,
					"due_date": d.due_date,
					"demand_remark": d.remarks or d.description,
					"original_amount": d.original_amount,
					"penalty_amount": d.penalty_amount,
					"waiver_amount": d.waiver_amount,
					"total_payable": d.net_payable,
				})
		if values:
			frappe.db.set_value("Fee Payment", p.name, values, update_modified=False)

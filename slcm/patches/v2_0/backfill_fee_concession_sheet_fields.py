import frappe


def execute():
	"""Fill the Fee Concession fields added to match the concession bulk-upload sheet
	(student registration / email, voucher dues details, date of concession) on existing records."""
	frappe.reload_doc("slcm", "doctype", "fee_concession")

	for c in frappe.get_all(
		"Fee Concession", fields=["name", "student", "fee_demand", "approved_on", "creation", "concession_date"]
	):
		values = {}
		student = c.student
		if c.fee_demand:
			d = frappe.db.get_value(
				"Fee Demand",
				c.fee_demand,
				["student", "fee_component", "demand_date", "academic_year", "due_date", "remarks",
				 "original_amount", "penalty_amount", "net_payable", "paid_amount", "outstanding_amount"],
				as_dict=True,
			)
			if d:
				student = student or d.student
				values.update({
					"fee_component": d.fee_component,
					"demand_date": d.demand_date,
					"academic_year": d.academic_year,
					"due_date": d.due_date,
					"remarks": d.remarks,
					"original_amount": d.original_amount,
					"penalty_amount": d.penalty_amount,
					"total_payable": d.net_payable,
					"paid_amount": d.paid_amount,
					"pending_amount": d.outstanding_amount,
				})
		if student:
			sm = frappe.db.get_value(
				"Student Master", student, ["registration_id", "application_number", "official_email_id", "email"], as_dict=True
			)
			if sm:
				values.update({
					"student": student,
					"registration_id": sm.registration_id or sm.application_number,
					"student_email": sm.official_email_id or sm.email,
				})
		if not c.concession_date:
			values["concession_date"] = c.approved_on or frappe.utils.getdate(c.creation)
		if values:
			frappe.db.set_value("Fee Concession", c.name, values, update_modified=False)

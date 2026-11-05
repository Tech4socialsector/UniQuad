"""
Application Fee moved from Admission Cycle (one fee per cycle) to Admission Cycle Program
(one fee per programme row). Copy each cycle's old fee onto its programme rows that have none.

The old `application_fee` column stays in `tabAdmission Cycle` after the field is removed from the
DocType (Frappe does not drop columns on migrate), so it can be read here. When a cycle had no fee,
fall back to the Application Fee for the cycle's Academic Year when that year has exactly one.
"""

import frappe


def execute():
	if not frappe.db.has_column("Admission Cycle Program", "application_fee"):
		return

	has_old_column = frappe.db.has_column("Admission Cycle", "application_fee")
	fields = ["name", "academic_year"] + (["application_fee"] if has_old_column else [])
	cycles = frappe.get_all("Admission Cycle", fields=fields)

	fee_by_year = {}
	for cycle in cycles:
		fee = cycle.get("application_fee") if has_old_column else None
		if fee and not frappe.db.exists("Application Fee", fee):
			fee = None
		if not fee and cycle.academic_year:
			if cycle.academic_year not in fee_by_year:
				year_fees = frappe.get_all(
					"Application Fee", filters={"academic_year": cycle.academic_year}, pluck="name", limit=2
				)
				# Several fees for the year: don't guess, leave the rows for an admin to pick.
				fee_by_year[cycle.academic_year] = year_fees[0] if len(year_fees) == 1 else None
			fee = fee_by_year[cycle.academic_year]
		if not fee:
			continue

		frappe.db.sql(
			"""
			UPDATE `tabAdmission Cycle Program`
			SET application_fee = %s
			WHERE parent = %s AND parenttype = 'Admission Cycle'
				AND IFNULL(application_fee, '') = ''
			""",
			(fee, cycle.name),
		)

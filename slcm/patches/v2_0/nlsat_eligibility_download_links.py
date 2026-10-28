import frappe


def execute():
	"""Point stored admit/result card links at the moved eligibility module.

	www/eligibility moved to www/nlsat/eligibility, so the whitelisted download methods
	are now slcm.www.nlsat.eligibility.entrance_test_seat_allocation.*.
	"""
	for field in ("admit_card_download", "entrance_test_result_card"):
		if not frappe.db.has_column("Entrance Test Seat Allocation", field):
			continue
		frappe.db.sql(
			f"""
			UPDATE `tabEntrance Test Seat Allocation`
			SET `{field}` = REPLACE(`{field}`, 'slcm.www.eligibility.', 'slcm.www.nlsat.eligibility.')
			WHERE `{field}` LIKE '%%slcm.www.eligibility.%%'
			"""
		)

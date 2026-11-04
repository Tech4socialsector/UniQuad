import frappe

from slcm.slcm.doctype.id_card_generation_tool_log.id_card_generation_tool_log import rebuild_results


def execute():
	"""List the students of ID card runs recorded before per-student results
	were kept, rebuilt from the cards each run rendered."""
	frappe.reload_doc("slcm", "doctype", "id_card_generation_tool_log_item")
	frappe.reload_doc("slcm", "doctype", "id_card_generation_tool_log")

	logs = frappe.get_all(
		"ID Card Generation Tool Log",
		filters={"total_id_cards_generated": [">", 0], "results_reconstructed": 0},
		pluck="name",
		order_by="generated_on asc",
	)
	for name in logs:
		log = frappe.get_doc("ID Card Generation Tool Log", name)
		if log.results:
			continue
		rebuild_results(log)

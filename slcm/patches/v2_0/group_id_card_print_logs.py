import frappe

# Old per-card columns still on the ID Card Print Log table after the move to a cards table.
LEGACY_FIELDS = (
	"id_card_generation", "student_id_card", "student", "academic_year", "department",
	"program", "batch", "print_type", "reprint_reason", "front_image", "back_image",
)


def execute():
	"""ID Card Print Log used to hold one card per log, so a bulk sheet left one
	log per card sharing a bulk_print_id. Fold each such run into a single log
	whose Cards table lists every card, and delete the now-empty duplicates."""
	frappe.reload_doc("slcm", "doctype", "id_card_print_log_item")
	frappe.reload_doc("slcm", "doctype", "id_card_print_log")

	if not frappe.db.has_column("ID Card Print Log", "id_card_generation"):
		return  # fresh install, nothing legacy to fold

	logs = frappe.db.sql(
		f"""
		select name, bulk_print_id, {", ".join(f"`{f}`" for f in LEGACY_FIELDS)}
		from `tabID Card Print Log` log
		where (ifnull(id_card_generation, '') != '' or ifnull(student_id_card, '') != '')
			and not exists (select 1 from `tabID Card Print Log Item` item
				where item.parent = log.name and item.parenttype = 'ID Card Print Log')
		order by printed_on, creation
		""",
		as_dict=True,
	)

	runs = {}
	for log in logs:
		runs.setdefault(log.bulk_print_id or log.name, []).append(log)

	for run in runs.values():
		doc = frappe.get_doc("ID Card Print Log", run[0].name)
		for log in run:
			doc.append("cards", _card_row(log))
		doc.flags.ignore_links = True
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)

		for log in run[1:]:
			frappe.delete_doc("ID Card Print Log", log.name, ignore_permissions=True, force=True)


def _card_row(log):
	row = {f: log.get(f) for f in LEGACY_FIELDS}
	card = ("ID Card Generation", log.id_card_generation) if log.id_card_generation else (
		"Student ID Card", log.student_id_card)
	holder = frappe.db.get_value(*card, ["card_type", "student_name"], as_dict=True) or {}
	row["card_type"] = holder.get("card_type")
	row["student_name"] = holder.get("student_name")
	return row

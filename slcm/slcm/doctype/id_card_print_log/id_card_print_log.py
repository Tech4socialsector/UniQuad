import frappe
from frappe.model.document import Document
from frappe.utils import cint

# Header fields copied from the cards when every card in the run shares the value.
SHARED_FIELDS = ("academic_year", "department", "program", "batch")

# Card doctype -> its link field on ID Card Print Log Item.
CARD_LINK_FIELDS = {
	"ID Card Generation": "id_card_generation",
	"Student ID Card": "student_id_card",
}


class IDCardPrintLog(Document):
	def validate(self):
		cards = self.get("cards") or []
		self.total_cards_in_bulk = len(cards)

		types = {c.print_type for c in cards if c.print_type}
		self.print_type = types.pop() if len(types) == 1 else ("Mixed" if types else None)

		for field in SHARED_FIELDS:
			values = {c.get(field) for c in cards}
			self.set(field, values.pop() if len(values) == 1 else None)


def insert_print_log(cards, layout="Single"):
	"""Record one print action covering `cards` (dicts of ID Card Print Log Item fields)."""
	log = frappe.new_doc("ID Card Print Log")
	log.bulk_print_id = frappe.generate_hash(length=10)
	log.print_layout = layout
	log.print_action_type = "Bulk" if layout == "Bulk" else "Single"
	log.printed_by = frappe.session.user
	log.printed_on = frappe.utils.now()
	for card in cards:
		log.append("cards", card)
	log.insert(ignore_permissions=True)
	return log


@frappe.whitelist()
def get_print_history(doctype, name, limit=50):
	"""Prints of one card, newest first: one entry per print run it was part of."""
	if doctype not in CARD_LINK_FIELDS:
		frappe.throw(frappe._("Print history is not available for {0}.").format(doctype))
	frappe.has_permission(doctype, "read", name, throw=True)

	log = frappe.qb.DocType("ID Card Print Log")
	item = frappe.qb.DocType("ID Card Print Log Item")
	return (
		frappe.qb.from_(item)
		.join(log)
		.on(item.parent == log.name)
		.select(
			log.name,
			log.printed_on,
			log.printed_by,
			log.print_layout,
			log.print_action_type,
			log.total_cards_in_bulk,
			item.print_type,
		)
		.where(item.parenttype == "ID Card Print Log")
		.where(item[CARD_LINK_FIELDS[doctype]] == name)
		.orderby(log.printed_on, order=frappe.qb.desc)
		.limit(cint(limit) or 50)
		.run(as_dict=True)
	)

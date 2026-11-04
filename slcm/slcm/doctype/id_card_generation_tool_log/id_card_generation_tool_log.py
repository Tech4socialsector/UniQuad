from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_datetime

# How far back from a run's finish time to look for the cards it rendered,
# for runs recorded before start times were kept: a fixed margin plus a
# generous allowance per card.
SEARCH_MARGIN = timedelta(seconds=60)
SEARCH_PER_CARD = timedelta(seconds=60)


class IDCardGenerationToolLog(Document):
	@frappe.whitelist()
	def rebuild_results(self):
		"""Rebuild the per-student list of an older run from its cards."""
		self.check_permission("write")
		if self.results:
			frappe.throw(_("This run already lists its students."))
		found = rebuild_results(self)
		return {"found": found, "expected": cint(self.total_id_cards_generated)}


def _search_window(log):
	end = get_datetime(log.generated_on) + timedelta(seconds=2)
	if log.started_on:
		return get_datetime(log.started_on) - timedelta(seconds=2), end

	start = end - SEARCH_MARGIN - SEARCH_PER_CARD * max(cint(log.total_id_cards_generated), 1)
	# Never reach back into the previous run.
	previous = frappe.db.get_value(
		"ID Card Generation Tool Log",
		{"generated_on": ["<", log.generated_on], "name": ["!=", log.name]},
		"generated_on",
		order_by="generated_on desc",
	)
	if previous and get_datetime(previous) > start:
		start = get_datetime(previous)
	return start, end


def find_run_cards(log):
	"""Cards whose front image was rendered by this run's user and template
	inside the run's time window."""
	start, end = _search_window(log)
	files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "ID Card Generation",
			"file_name": ["like", "%_Front%"],
			"creation": ["between", [start, end]],
			"owner": log.generated_by or "Administrator",
		},
		fields=["attached_to_name", "creation"],
		order_by="creation asc",
	)
	names = list(dict.fromkeys(f.attached_to_name for f in files if f.attached_to_name))
	if not names:
		return [], start

	filters = {"name": ["in", names]}
	if log.template_used:
		filters["id_card_template"] = log.template_used
	cards = {
		c.name: c
		for c in frappe.get_all(
			"ID Card Generation",
			filters=filters,
			fields=["name", "student", "student_name", "photo", "creation"],
		)
	}
	# Keep the order in which the run rendered them.
	return [cards[n] for n in names if n in cards and cards[n].student], start


def rebuild_results(log):
	"""Fill `results` (and the counts derived from it) for a run recorded
	before per-student results were kept. Returns how many cards were found."""
	cards, start = find_run_cards(log)
	expected = cint(log.total_id_cards_generated)
	cards = cards[:expected] if expected else cards

	new = regenerated = no_photo = 0
	log.set("results", [])
	for card in cards:
		is_new = get_datetime(card.creation) >= start
		new += 1 if is_new else 0
		regenerated += 0 if is_new else 1
		no_photo += 0 if card.photo else 1
		log.append(
			"results",
			{
				"student": card.student,
				"student_name": card.student_name,
				"has_photo": 1 if card.photo else 0,
				"result": "New" if is_new else "Regenerated",
				"id_card": card.name,
				"message": "",
			},
		)

	log.results_reconstructed = 1
	if cards:
		log.new_cards = new
		log.regenerated_cards = regenerated
		log.missing_photo_count = no_photo
	log.flags.ignore_permissions = True
	log.save()
	return len(cards)

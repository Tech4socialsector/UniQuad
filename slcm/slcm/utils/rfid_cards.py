# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""Student RFID cards.

Student Master.rfid_uid is the card attendance matching reads (poller, RFID
processor). Student RFID Card is the history of every card a student has had:
one Active card at most, older ones Replaced / Lost / Blocked / Damaged.

Every path keeps the two in step:
  * Student RFID Card saved        -> StudentRFIDCard.on_update -> sync_student_master()
  * RFID Card Management link/bulk -> assign_card()
  * RFID Card Management unlink    -> remove_wrong_assignment()
  * Student Master rfid_uid edited -> on_student_master_validate() / _update() (doc_events)
"""

import frappe
from frappe import _
from frappe.utils import today

INACTIVE_STATUSES = ("Blocked", "Lost", "Damaged", "Replaced")


def _card_by_uid(rfid_uid):
	return frappe.db.get_value(
		"Student RFID Card", {"rfid_uid": rfid_uid}, ["name", "student", "card_status"], as_dict=True
	)


def backfill_logs(student, rfid_uid):
	"""Attach earlier swipes of this card that were not linked to anyone. Returns Attendance Log count."""
	frappe.db.sql(
		"""UPDATE `tabAttendance Log` SET student = %s
		WHERE rfid_uid = %s AND (student IS NULL OR student = '')""",
		(student, rfid_uid),
	)
	frappe.db.sql(
		"""UPDATE `tabRFID SQL Punch Log` SET student = %s, sync_status = 'Matched'
		WHERE emp_code = %s AND (student IS NULL OR student = '')""",
		(student, rfid_uid),
	)
	return frappe.db.count("Attendance Log", {"rfid_uid": rfid_uid, "student": student})


def sync_student_master(card):
	"""After a Student RFID Card is saved: retire the student's other active cards and
	point Student Master.rfid_uid at the active card (or clear it when this card is retired)."""
	current = frappe.db.get_value("Student Master", card.student, "rfid_uid")

	if card.card_status == "Active":
		for name in frappe.get_all(
			"Student RFID Card",
			filters={"student": card.student, "card_status": "Active", "name": ["!=", card.name]},
			pluck="name",
		):
			old = frappe.get_doc("Student RFID Card", name)
			old.card_status = "Replaced"
			old.remarks = "\n".join(filter(None, [old.remarks, _("Replaced by card {0}").format(card.rfid_uid)]))
			old.flags.skip_rfid_sync = True
			old.save(ignore_permissions=True)

		if current != card.rfid_uid:
			frappe.db.set_value("Student Master", card.student, "rfid_uid", card.rfid_uid)
		backfill_logs(card.student, card.rfid_uid)

	elif current == card.rfid_uid:
		frappe.db.set_value("Student Master", card.student, "rfid_uid", None)


def check_assignable(student, rfid_uid):
	"""Throw unless rfid_uid can become this student's card. Returns the card's existing history row, if any."""
	holder = frappe.db.get_value("Student Master", {"rfid_uid": rfid_uid, "name": ["!=", student]}, "name")
	if holder:
		frappe.throw(
			_("RFID UID <b>{0}</b> is already assigned to student <b>{1}</b>. Remove it from that student first.").format(
				rfid_uid, holder
			)
		)

	existing = _card_by_uid(rfid_uid)
	if existing and existing.student != student:
		frappe.throw(
			_("Card <b>{0}</b> was issued to student <b>{1}</b> before (status: {2}). "
			"Delete that Student RFID Card record ({3}) if the card is being reissued.").format(
				rfid_uid, existing.student, existing.card_status, existing.name
			)
		)
	return existing


def assign_card(student, rfid_uid, remarks=None):
	"""Make rfid_uid the student's active card (creating its history record if needed).
	Returns the number of Attendance Logs now linked to the student for this card."""
	student = (student or "").strip()
	rfid_uid = (rfid_uid or "").strip()
	if not student or not rfid_uid:
		frappe.throw(_("Both RFID UID and Student are required."))
	if not frappe.db.exists("Student Master", student):
		frappe.throw(_("Student {0} not found.").format(student))

	existing = check_assignable(student, rfid_uid)
	if existing:
		card = frappe.get_doc("Student RFID Card", existing.name)
		if card.card_status != "Active":
			card.card_status = "Active"
			if remarks:
				card.remarks = "\n".join(filter(None, [card.remarks, remarks]))
			card.save(ignore_permissions=True)
		elif frappe.db.get_value("Student Master", student, "rfid_uid") != rfid_uid:
			sync_student_master(card)
		else:
			backfill_logs(student, rfid_uid)
	else:
		frappe.get_doc({
			"doctype": "Student RFID Card",
			"student": student,
			"rfid_uid": rfid_uid,
			"card_status": "Active",
			"issued_date": today(),
			"remarks": remarks,
		}).insert(ignore_permissions=True)

	return frappe.db.count("Attendance Log", {"rfid_uid": rfid_uid, "student": student})


def remove_wrong_assignment(student):
	"""Undo a card linked to the wrong student: drop its history record, clear
	Student Master and unlink its swipes so they show as unassigned again."""
	old_uid = frappe.db.get_value("Student Master", student, "rfid_uid")
	if not old_uid:
		return None
	card = frappe.db.get_value("Student RFID Card", {"rfid_uid": old_uid, "student": student}, "name")
	if card:
		frappe.delete_doc("Student RFID Card", card, ignore_permissions=True, force=True)
	frappe.db.set_value("Student Master", student, "rfid_uid", None)
	frappe.db.sql(
		"UPDATE `tabAttendance Log` SET student = NULL WHERE student = %s AND rfid_uid = %s", (student, old_uid)
	)
	frappe.db.sql(
		"""UPDATE `tabRFID SQL Punch Log` SET student = NULL, sync_status = 'Unmatched'
		WHERE student = %s AND emp_code = %s""",
		(student, old_uid),
	)
	return old_uid


def on_student_master_validate(doc, method=None):
	"""Reject an unusable RFID UID before the Student Master row is written."""
	doc.rfid_uid = (doc.rfid_uid or "").strip() or None
	if doc.rfid_uid and not doc.flags.skip_rfid_sync and doc.has_value_changed("rfid_uid"):
		check_assignable(doc.name, doc.rfid_uid)


def on_student_master_update(doc, method=None):
	"""RFID UID typed on the Student Master form: record it in the card history."""
	if doc.flags.skip_rfid_sync or not doc.has_value_changed("rfid_uid"):
		return
	before = doc.get_doc_before_save()
	old_uid = (before.rfid_uid or "").strip() if before else ""
	new_uid = (doc.rfid_uid or "").strip()

	if new_uid:
		assign_card(doc.name, new_uid, _("Set on Student Master"))
	elif old_uid:
		card = frappe.db.get_value(
			"Student RFID Card", {"rfid_uid": old_uid, "student": doc.name, "card_status": "Active"}, "name"
		)
		if card:
			card = frappe.get_doc("Student RFID Card", card)
			card.card_status = "Blocked"
			card.remarks = "\n".join(filter(None, [card.remarks, _("Removed from Student Master")]))
			card.flags.skip_rfid_sync = True
			card.save(ignore_permissions=True)


def on_student_master_trash(doc, method=None):
	"""Card history goes with the student (runs before Frappe's link check)."""
	for name in frappe.get_all("Student RFID Card", filters={"student": doc.name}, pluck="name"):
		frappe.delete_doc("Student RFID Card", name, ignore_permissions=True, force=True)

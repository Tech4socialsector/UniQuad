# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""Student RFID cards.

Student Master.rfid_uid is the card attendance matching reads (poller, RFID
processor). Student RFID Card is the history of every card a student has had:
one Active card at most, older ones Replaced / Lost / Blocked / Damaged.

Every change of Student Master.rfid_uid goes through set_student_uid() (or is
logged by on_student_master_update for form edits) and is recorded in the
student's "RFID UID Change Log": one log per student, one row per change
(who, when, from -> to, and which screen did it).
Callers name the screen with `with change_source("..."):`.

Every path keeps the two in step:
  * Student RFID Card saved        -> StudentRFIDCard.on_update -> sync_student_master()
  * RFID Card Management link/bulk -> assign_card()
  * RFID Card Management unlink    -> remove_wrong_assignment()
  * Unmap (one or many, any screen) -> unmap_card()
  * Student Master rfid_uid edited -> on_student_master_validate() / _update() (doc_events)
"""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import now_datetime, today

INACTIVE_STATUSES = ("Blocked", "Lost", "Damaged", "Replaced")
CHANGE_LOG = "RFID UID Change Log"
CHANGE_ROW = "RFID UID Change Log Entry"
# Why a card is taken off a student. "Wrong student" undoes the link; the others retire the card.
UNMAP_REASONS = ("Wrong student", "Lost", "Damaged", "Blocked")


@contextmanager
def change_source(label):
	"""Name the screen/process making RFID changes, for the change log. The outermost caller wins."""
	prev = frappe.flags.get("rfid_change_source")
	frappe.flags.rfid_change_source = prev or label
	try:
		yield
	finally:
		frappe.flags.rfid_change_source = prev


def log_uid_change(student, old_uid, new_uid, source=None, message=None):
	"""Add one change of a student's RFID UID to their change log. Never blocks the change itself."""
	old_uid = (old_uid or "").strip()
	new_uid = (new_uid or "").strip()
	if old_uid == new_uid or not frappe.db.table_exists(CHANGE_ROW):
		return
	sm = frappe.db.get_value("Student Master", student, ["registration_id", "first_name"], as_dict=True) or {}
	change_type = "Assigned" if not old_uid else "Removed" if not new_uid else "Changed"
	source = frappe.flags.get("rfid_change_source") or source or _("System")
	if not message:
		message = {
			"Assigned": _("Card {0} assigned"),
			"Removed": _("Card {0} removed"),
			"Changed": _("Card changed from {0} to {1}"),
		}[change_type].format(old_uid or new_uid, new_uid)
	changed_on = now_datetime()

	if frappe.db.exists(CHANGE_LOG, student):
		log = frappe.get_doc(CHANGE_LOG, student)
	else:
		log = frappe.new_doc(CHANGE_LOG)
		log.student = student
	log.append("changes", {
		"changed_on": changed_on,
		"change_type": change_type,
		"old_rfid_uid": old_uid or None,
		"new_rfid_uid": new_uid or None,
		"changed_by": frappe.session.user,
		"source": source,
		"message": message,
	})
	log.update({
		"student_id": sm.get("registration_id"),
		"student_name": sm.get("first_name"),
		"current_rfid_uid": new_uid or None,
		"last_change": change_type,
		"last_changed_on": changed_on,
		"last_changed_by": frappe.session.user,
		"change_count": len(log.changes),
	})
	log.save(ignore_permissions=True)


def set_student_uid(student, new_uid, source=None):
	"""Write Student Master.rfid_uid and log the change."""
	new_uid = (new_uid or "").strip() or None
	old_uid = frappe.db.get_value("Student Master", student, "rfid_uid")
	if (old_uid or None) == new_uid:
		return
	frappe.db.set_value("Student Master", student, "rfid_uid", new_uid)
	log_uid_change(student, old_uid, new_uid, source)


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
			set_student_uid(card.student, card.rfid_uid, _("Student RFID Card"))
		backfill_logs(card.student, card.rfid_uid)

	elif current == card.rfid_uid:
		set_student_uid(card.student, None, _("Student RFID Card ({0})").format(card.card_status))


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
	set_student_uid(student, None, _("Wrong card removed"))
	frappe.db.sql(
		"UPDATE `tabAttendance Log` SET student = NULL WHERE student = %s AND rfid_uid = %s", (student, old_uid)
	)
	frappe.db.sql(
		"""UPDATE `tabRFID SQL Punch Log` SET student = NULL, sync_status = 'Unmatched'
		WHERE student = %s AND emp_code = %s""",
		(student, old_uid),
	)
	return old_uid


def unmap_card(student, reason):
	"""Take the student's current card off them. Returns the card UID, or None when they had no card.

	Wrong student            the link was a mistake: the card history row is dropped and the card's swipes
	                         go back to unassigned, so the card can be given to the right student.
	Lost / Damaged / Blocked the card was the student's: history and past attendance stay, the card is
	                         marked with the reason and stops counting. It cannot be given to anyone else.
	"""
	if reason not in UNMAP_REASONS:
		frappe.throw(_("Choose why the card is being removed: {0}.").format(", ".join(UNMAP_REASONS)))
	uid = (frappe.db.get_value("Student Master", student, "rfid_uid") or "").strip()
	if not uid:
		return None
	if reason == "Wrong student":
		return remove_wrong_assignment(student)

	existing = _card_by_uid(uid)
	if existing and existing.student != student:
		# history says another student had this card: leave that row alone, just clear this student
		set_student_uid(student, None, _("Card removed ({0})").format(reason))
		return uid
	card = frappe.get_doc("Student RFID Card", existing.name) if existing else frappe.new_doc("Student RFID Card")
	card.update({"student": student, "rfid_uid": uid, "card_status": reason})
	card.remarks = "\n".join(filter(None, [card.remarks, _("Removed from the student: {0}").format(reason)]))
	card.save(ignore_permissions=True)  # on_update -> sync_student_master() clears Student Master.rfid_uid
	return uid


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
	log_uid_change(doc.name, old_uid, new_uid, _("Student Master form"))

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
	"""Card history and change log go with the student (runs before Frappe's link check)."""
	for name in frappe.get_all("Student RFID Card", filters={"student": doc.name}, pluck="name"):
		frappe.delete_doc("Student RFID Card", name, ignore_permissions=True, force=True)
	if frappe.db.exists(CHANGE_LOG, doc.name):
		frappe.delete_doc(CHANGE_LOG, doc.name, ignore_permissions=True, force=True)

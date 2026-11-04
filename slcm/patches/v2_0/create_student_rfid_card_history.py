import frappe
from frappe.utils import getdate


def execute():
	"""Give every Student Master that already has an RFID UID an Active Student RFID Card,
	so the card history starts complete. Student Master and its logs are left untouched."""
	frappe.reload_doc("slcm", "doctype", "student_rfid_card")

	students = frappe.get_all(
		"Student Master",
		filters={"rfid_uid": ["is", "set"]},
		fields=["name", "rfid_uid", "modified"],
		limit=0,
	)
	for s in students:
		uid = (s.rfid_uid or "").strip()
		if not uid or frappe.db.exists("Student RFID Card", {"rfid_uid": uid}):
			continue
		card = frappe.get_doc({
			"doctype": "Student RFID Card",
			"student": s.name,
			"rfid_uid": uid,
			"card_status": "Active",
			"issued_date": getdate(s.modified),
			"remarks": "Created from Student Master when card history was introduced",
		})
		card.flags.skip_rfid_sync = True
		card.insert(ignore_permissions=True)

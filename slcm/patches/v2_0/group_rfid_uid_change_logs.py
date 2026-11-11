import frappe

LEGACY = "change_type, old_rfid_uid, new_rfid_uid, changed_by, changed_on, source, message"


def execute():
	"""RFID UID Change Log used to hold one change per record, so a student with an assign and a removal had two
	records. Fold every student's changes into one log (named after the student) with a Changes table, oldest
	first, and delete the old per-change records."""
	frappe.reload_doc("slcm", "doctype", "rfid_uid_change_log_entry")
	frappe.reload_doc("slcm", "doctype", "rfid_uid_change_log")

	if not frappe.db.has_column("RFID UID Change Log", "change_type"):
		return  # fresh install, nothing legacy to fold

	rows = frappe.db.sql(
		f"""select name, student, {LEGACY} from `tabRFID UID Change Log`
		where name != ifnull(student, '') order by changed_on, creation""",
		as_dict=True,
	)
	by_student = {}
	for r in rows:
		if r.student:
			by_student.setdefault(r.student, []).append(r)

	for student, changes in by_student.items():
		if frappe.db.exists("RFID UID Change Log", student):
			log = frappe.get_doc("RFID UID Change Log", student)
		else:
			log = frappe.new_doc("RFID UID Change Log")
			log.student = student
		for c in changes:
			log.append("changes", {f: c.get(f) for f in LEGACY.split(", ")})
		log.changes.sort(key=lambda c: (str(c.changed_on or ""), c.idx or 0))
		for i, c in enumerate(log.changes, 1):
			c.idx = i
		last = log.changes[-1]
		sm = frappe.db.get_value("Student Master", student, ["registration_id", "first_name"], as_dict=True) or {}
		log.update({
			"student_id": sm.get("registration_id"),
			"student_name": sm.get("first_name"),
			"current_rfid_uid": last.new_rfid_uid,
			"last_change": last.change_type,
			"last_changed_on": last.changed_on,
			"last_changed_by": last.changed_by,
			"change_count": len(log.changes),
		})
		log.flags.ignore_links = True
		log.save(ignore_permissions=True)

	for r in rows:
		frappe.db.delete("RFID UID Change Log", {"name": r.name})

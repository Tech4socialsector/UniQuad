import json

import frappe


def execute():
	"""Fill Added On / Added By / Added Later on existing class students and
	build each class's Student Change Log from its Version history (Classes
	tracks changes). Child rows carry the class's creation time, so the
	Versions are the only record of when a student was added later."""
	frappe.reload_doc("slcm", "doctype", "class_student_log")
	frappe.reload_doc("slcm", "doctype", "class_enrolled_student")
	frappe.reload_doc("slcm", "doctype", "classes")

	for cls in frappe.get_all("Classes", fields=["name", "creation", "owner"]):
		rows = frappe.get_all("Class Enrolled Student",
			filters={"parent": cls.name, "parenttype": "Classes", "parentfield": "enrolled_students"},
			fields=["name", "student_enrollment", "student_name", "added_on"])
		if any(r.added_on for r in rows) or frappe.db.exists("Class Student Log", {"parent": cls.name}):
			continue  # already tracked

		events, added = _events(cls.name, rows)
		for r in rows:
			by = added.get(r.student_enrollment)
			frappe.db.set_value("Class Enrolled Student", r.name, {
				"added_after_creation": 1 if by else 0,
				"added_on": by[1] if by else cls.creation,
				"added_by": by[0] if by else cls.owner,
			}, update_modified=False)

		for idx, e in enumerate(events, 1):
			frappe.get_doc(dict(e, doctype="Class Student Log", parent=cls.name, parenttype="Classes",
				parentfield="student_log", idx=idx)).db_insert()


def _events(class_name, rows):
	"""Added / Removed / Status Changed events from the class's Versions, and
	who added each student still in the class, and when (latest add)."""
	enrollment_of = {r.name: r.student_enrollment for r in rows}
	names = {r.student_enrollment: r.student_name for r in rows}
	events, added = [], {}

	for v in frappe.get_all("Version", filters={"ref_doctype": "Classes", "docname": class_name},
			fields=["owner", "creation", "data"], order_by="creation asc"):
		try:
			data = json.loads(v.data or "{}")
		except ValueError:
			continue

		def event(action, enrollment, from_status=None, to_status=None):
			events.append({"changed_on": v.creation, "changed_by": v.owner, "action": action,
				"student_enrollment": enrollment, "student_name": names.get(enrollment),
				"from_status": from_status, "to_status": to_status})

		for table, row in data.get("added") or []:
			if table != "enrolled_students" or not row.get("student_enrollment"):
				continue
			enrollment_of[row.get("name")] = row["student_enrollment"]
			names.setdefault(row["student_enrollment"], row.get("student_name"))
			added[row["student_enrollment"]] = (v.owner, v.creation)
			event("Added", row["student_enrollment"], to_status=row.get("status"))

		for table, row in data.get("removed") or []:
			if table != "enrolled_students" or not row.get("student_enrollment"):
				continue
			names.setdefault(row["student_enrollment"], row.get("student_name"))
			added.pop(row["student_enrollment"], None)
			event("Removed", row["student_enrollment"], from_status=row.get("status"))

		for change in data.get("row_changed") or []:
			table, row_name, changes = change[0], change[2], change[3]
			enrollment = enrollment_of.get(row_name)
			if table != "enrolled_students" or not enrollment:
				continue
			for field, old, new in changes:
				if field == "status":
					event("Status Changed", enrollment, old, new)

	for e in events:
		if not e["student_name"]:
			e["student_name"] = frappe.db.get_value("Student Enrollment", e["student_enrollment"], "student_name")
	return events, added

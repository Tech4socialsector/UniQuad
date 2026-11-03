import frappe


def generate_id_card_images(docname):
	try:
		doc = frappe.get_doc("Student ID Card", docname)
		doc.generate_card()
		frappe.db.commit()
		status, error = "Generated", None
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(f"ID Card Generation Failed for {docname}: {e!s}", "ID Card Generation Error")
		frappe.db.set_value("Student ID Card", docname, "card_status", "Error")
		frappe.db.commit()
		status, error = "Error", frappe.utils.strip_html(str(e))[:300]

	# Lets an open form refresh itself instead of waiting for a manual reload.
	frappe.publish_realtime(
		"id_card_generated",
		{"doctype": "Student ID Card", "name": docname, "status": status, "error": error},
		doctype="Student ID Card",
		docname=docname,
	)

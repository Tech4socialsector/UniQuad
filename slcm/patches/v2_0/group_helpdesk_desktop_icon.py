import frappe


def execute():
	"""Nest the Helpdesk app icon under the Campus & Support desktop icon.

	Helpdesk's icon belongs to the helpdesk app, so it can't ship as a JSON file in
	slcm/desktop_icon like the other grouped icons — set its parent here instead.
	"""
	if frappe.db.exists("Desktop Icon", "Helpdesk") and frappe.db.exists("Desktop Icon", "Campus & Support"):
		frappe.db.set_value("Desktop Icon", "Helpdesk", "parent_icon", "Campus & Support")
		frappe.cache.delete_key("desktop_icons")
		frappe.cache.delete_key("bootinfo")

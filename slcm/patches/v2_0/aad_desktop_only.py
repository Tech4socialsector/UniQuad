"""AAD / AAD Staff see only the desktop icons granted to their roles — drop
the rest from their saved Desktop Layouts (see slcm.slcm.utils.academics_desktop)."""

import frappe

from slcm.slcm.utils.academics_desktop import sync_all_layouts


def execute():
	sync_all_layouts()
	frappe.cache.delete_key("bootinfo")
	frappe.cache.delete_key("desktop_icons")

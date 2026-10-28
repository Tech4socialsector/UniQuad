"""
Put the Programme Management sidebar on the SLCM dock for sites that already
saved their own dock arrangement.

The app dock (slcm/dock/slcm/slcm.json) ships the entry, but a saved site or
user layer is the whole rail: an app entry it does not name stays off it. So
append a reference row (no icon/title, inherited from the app layer) to every
saved slcm layer that lacks one.
"""

import frappe

SIDEBAR = "Programme Management"


def execute():
    if not frappe.db.exists("Sidebar", SIDEBAR):
        return

    layers = frappe.get_all("Dock", filters={"app": "slcm", "standard": 0}, pluck="name")
    for name in layers:
        dock = frappe.get_doc("Dock", name)
        if any(r.link_type == "Sidebar" and r.link_to == SIDEBAR for r in dock.items):
            continue
        dock.append("items", {"link_type": "Sidebar", "link_to": SIDEBAR, "added": 0, "hidden": 0})
        dock.save(ignore_permissions=True)

    frappe.clear_cache()

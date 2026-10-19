"""
Backfill the 'app' field on Desktop Icon records that were auto-created from
a Workspace before the app_name -> app typo was fixed in
frappe.desk.doctype.desktop_icon.desktop_icon.create_desktop_icons_from_workspace.

Without 'app' set, the desktop's icon lookup (frappe.utils.get_desktop_icon)
can never resolve a matching SVG, so these icons silently fall back to a
plain letter avatar even when the SVG asset exists on disk.
"""

import frappe


def execute():
    icons = frappe.get_all(
        "Desktop Icon",
        filters={"app": ["in", ["", None]], "icon_type": "Link"},
        fields=["name", "link_to"],
    )

    for icon in icons:
        if not icon.link_to:
            continue

        module = frappe.db.get_value("Workspace", icon.link_to, "module")
        if not module:
            continue

        app_name = frappe.db.get_value("Module Def", module, "app_name")
        if app_name and app_name in frappe.get_installed_apps():
            frappe.db.set_value("Desktop Icon", icon.name, "app", app_name)

    # Icons without a backing Workspace (e.g. linking to another installed
    # app's own desk) can't be resolved via Module Def, so map them directly.
    manual_app_map = {"LMS": "lms", "Faculty Management": "slcm"}
    for label, app_name in manual_app_map.items():
        if app_name in frappe.get_installed_apps() and frappe.db.exists("Desktop Icon", label):
            frappe.db.set_value("Desktop Icon", label, "app", app_name)

    frappe.db.commit()
    frappe.clear_cache()

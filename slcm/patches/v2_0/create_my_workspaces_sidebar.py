"""
The standard 'My Workspaces' Desktop Icon (frappe.desktop_icon.my_workspaces)
ships on every site, but its backing 'My Workspaces' Workspace Sidebar record
is only ever created lazily, the first time a user creates a private
workspace (see workspace_sidebar.add_to_my_workspace). On a site where that
has never happened, frappe.boot.workspace_sidebar_item["my workspaces"] is
undefined, which crashes the whole desktop icon grid (not just this one
icon) in DesktopIcon.validate_icon.

Create the base sidebar record up front so it's always present.
"""

import frappe


def execute():
    if not frappe.db.exists("Workspace Sidebar", "My Workspaces"):
        frappe.get_doc(
            {
                "doctype": "Workspace Sidebar",
                "name": "My Workspaces",
                "title": "My Workspaces",
                "items": [],
            }
        ).insert(ignore_permissions=True)
        frappe.db.commit()

    frappe.clear_cache()

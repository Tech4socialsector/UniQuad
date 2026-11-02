"""AAD / AAD Staff access to the Academics desktop.

The DocType JSONs carry the AAD (full) and AAD Staff (no delete) DocPerms, but
Frappe ignores standard DocPerms on any DocType that has Custom DocPerms, so
copy those roles' rows into Custom DocPerm wherever it is in use. Then bring
saved Desktop Layouts in line with the Academics icons' new roles.
"""

import frappe
from frappe.permissions import rights

from slcm.permissions import AAD_ROLES
from slcm.slcm.utils.academics_desktop import sync_all_layouts


def execute():
	for role in sorted(AAD_ROLES):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)

	meta = frappe.get_meta("Custom DocPerm")
	fields = ["role", "permlevel", "if_owner", *(r for r in rights if meta.has_field(r))]
	doctypes = set(frappe.get_all("DocPerm", filters={"role": ["in", list(AAD_ROLES)]}, pluck="parent"))
	customised = set(frappe.get_all("Custom DocPerm", filters={"parent": ["in", list(doctypes)]}, pluck="parent"))

	for dt in sorted(customised):
		frappe.db.delete("Custom DocPerm", {"parent": dt, "role": ["in", list(AAD_ROLES)]})
		for perm in frappe.get_all(
			"DocPerm", filters={"parent": dt, "role": ["in", list(AAD_ROLES)]}, fields=fields, order_by="idx"
		):
			frappe.get_doc(
				{"doctype": "Custom DocPerm", "parent": dt, "parenttype": "DocType", "parentfield": "permissions", **perm}
			).insert(ignore_permissions=True)
		frappe.clear_cache(doctype=dt)

	sync_all_layouts()

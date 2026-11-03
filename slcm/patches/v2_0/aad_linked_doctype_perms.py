"""AAD / AAD Staff access to the DocTypes linked from the Academics DocTypes.

The slcm link targets carry the new rows in their JSON (read on academic
masters, select-only on fee / hostel records); re-run the Custom DocPerm copy
so DocTypes with customised permissions pick them up. Currency and Role are
Frappe's, so give them select through Custom DocPerm directly.
"""

import frappe
from frappe.permissions import setup_custom_perms

from slcm.patches.v2_0 import aad_role_access
from slcm.permissions import AAD_ROLES

CORE_SELECT_ONLY = ("Currency", "Role")


def execute():
	aad_role_access.execute()

	for dt in CORE_SELECT_ONLY:
		setup_custom_perms(dt)
		for role in sorted(AAD_ROLES):
			if frappe.db.exists("Custom DocPerm", {"parent": dt, "role": role, "permlevel": 0, "if_owner": 0}):
				continue
			frappe.get_doc(
				{
					"doctype": "Custom DocPerm",
					"parent": dt,
					"parenttype": "DocType",
					"parentfield": "permissions",
					"role": role,
					"permlevel": 0,
					"select": 1,
					# Custom DocPerm defaults read and export to 1
					"read": 0,
					"export": 0,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(doctype=dt)

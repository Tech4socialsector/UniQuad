"""
NLSIU Admin — a site-wide admin role that mirrors System Manager.

Frappe has no role inheritance, so every grant System Manager holds is copied
to NLSIU Admin: DocType permissions, Page / Report / Workspace / Dashboard Chart
roles, and desktop icons (except ERPNext icons). Standard DocPerm rows are
rebuilt from JSON on migrate, so this runs from after_migrate and is idempotent.
Run manually with:
    bench --site slcm.local execute slcm.setup.nlsiu_admin_role.sync
"""
import frappe

ROLE = "NLSIU Admin"
SOURCE_ROLE = "System Manager"
HAS_ROLE_PARENTTYPES = ("Page", "Report", "Workspace", "Dashboard Chart")
SKIP_PERM_FIELDS = {"name", "role", "creation", "modified", "modified_by", "owner", "idx", "docstatus"}


def sync():
	ensure_role()
	copy_doctype_permissions()
	copy_has_roles()
	add_to_desktop_icons()
	frappe.db.commit()
	frappe.clear_cache()


def ensure_role():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(ignore_permissions=True)


def copy_doctype_permissions():
	custom_perm_doctypes = set(frappe.get_all("Custom DocPerm", pluck="parent", distinct=True))

	for perm_doctype in ("Custom DocPerm", "DocPerm"):
		source_rows = frappe.get_all(perm_doctype, filters={"role": SOURCE_ROLE}, fields=["*"])
		existing = {
			(r.parent, r.permlevel, r.if_owner)
			for r in frappe.get_all(perm_doctype, filters={"role": ROLE}, fields=["parent", "permlevel", "if_owner"])
		}
		for row in source_rows:
			# Doctypes with Custom DocPerm ignore their standard DocPerm rows
			if perm_doctype == "DocPerm" and row.parent in custom_perm_doctypes:
				continue
			if (row.parent, row.permlevel, row.if_owner) in existing:
				continue
			new_row = {k: v for k, v in row.items() if k not in SKIP_PERM_FIELDS}
			new_row.update({"doctype": perm_doctype, "role": ROLE, "idx": _next_idx(perm_doctype, row.parent)})
			frappe.get_doc(new_row).db_insert()


def copy_has_roles():
	for parenttype in HAS_ROLE_PARENTTYPES:
		parents = frappe.get_all(
			"Has Role", filters={"parenttype": parenttype, "role": SOURCE_ROLE}, pluck="parent"
		)
		for parent in parents:
			_add_has_role(parenttype, parent)


def add_to_desktop_icons():
	"""Add the role to every role-restricted desktop icon outside ERPNext.

	Icons with no roles are already visible to everyone, so they are left alone.
	"""
	erpnext_icons = set(frappe.get_all("Desktop Icon", filters={"app": "erpnext"}, pluck="name"))
	restricted = set(frappe.get_all("Has Role", filters={"parenttype": "Desktop Icon"}, pluck="parent"))
	for icon in frappe.get_all("Desktop Icon", fields=["name", "app", "parent_icon"]):
		if icon.app == "erpnext" or icon.parent_icon in erpnext_icons or icon.name not in restricted:
			continue
		_add_has_role("Desktop Icon", icon.name)
	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")


def _add_has_role(parenttype, parent):
	if frappe.db.exists("Has Role", {"parenttype": parenttype, "parent": parent, "role": ROLE}):
		return
	frappe.get_doc({
		"doctype": "Has Role",
		"parenttype": parenttype,
		"parent": parent,
		"parentfield": "roles",
		"role": ROLE,
		"idx": _next_idx("Has Role", parent, parenttype),
	}).db_insert()


def _next_idx(child_doctype, parent, parenttype=None):
	filters = {"parent": parent}
	if parenttype:
		filters["parenttype"] = parenttype
	idx = frappe.get_all(child_doctype, filters=filters, fields=[{"MAX": "idx", "as": "idx"}])
	return ((idx and idx[0].idx) or 0) + 1

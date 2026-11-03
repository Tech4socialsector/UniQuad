# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""
Migration patch: prefix SLCM DocTypes whose names clash with ERPNext.

ERPNext ships its own Batch, Company, Department, Designation, Driver,
Payment Request and Video DocTypes. DocType names are global, so installing
ERPNext on an SLCM site would overwrite SLCM's definitions. Each SLCM DocType
is renamed in place to "SLCM <name>" (table, meta, customizations and every
stored reference to the DocType name), keeping all records and their names.

Runs pre_model_sync so the renamed DocTypes and the SLCM DocTypes linking to
them are then synced from their updated JSON.

frappe.rename_doc("DocType", ...) is deliberately not used (unlike
rename_program_to_programme.py): it rewrites every Link pointing at the old
name across all apps - on a site where ERPNext DocTypes already exist that
would repoint ERPNext's own Company/Batch/... links at SLCM's tables, and in
developer mode it re-exports other apps' DocType JSON. This patch does the
same work but skips anything owned by ERPNext. Link field options on SLCM
DocTypes are left to the model sync, which applies them from the JSON.

A DocType that is no longer owned by SLCM (e.g. ERPNext already replaced it)
is skipped; the model sync then creates the "SLCM <name>" DocType fresh.
"""

import frappe
from frappe.model.dynamic_links import get_dynamic_link_map
from frappe.model.rename_doc import get_link_fields

RENAMES = {
    "Batch": "SLCM Batch",
    "Company": "SLCM Company",
    "Department": "SLCM Department",
    "Designation": "SLCM Designation",
    "Driver": "SLCM Driver",
    "Payment Request": "SLCM Payment Request",
    "Video": "SLCM Video",
}


def execute():
    erpnext_modules = set(frappe.get_all("Module Def", filters={"app_name": "erpnext"}, pluck="name"))

    for old, new in RENAMES.items():
        if frappe.db.exists("DocType", new) or not _is_slcm_doctype(old):
            continue

        if frappe.db.table_exists(old, cached=False) and not frappe.db.table_exists(new, cached=False):
            frappe.db.rename_table(old, new)
        _rename_doctype_meta(old, new)
        _migrate_customizations(old, new)

        # Link field maps are cached per flag/local and include table names
        # that just changed, so rebuild them for every rename.
        frappe.flags.link_fields = {}
        frappe.local.dynamic_link_map = None
        frappe.clear_cache(doctype=old)

        _update_doctype_references(old, new, erpnext_modules)
        _update_user_settings(old, new)

    frappe.clear_cache()


def _is_slcm_doctype(doctype):
    module = frappe.db.get_value("DocType", doctype, "module")
    return bool(module) and frappe.db.get_value("Module Def", module, "app_name") == "slcm"


def _rename_doctype_meta(old, new):
    frappe.db.sql("UPDATE `tabDocType` SET name = %s WHERE name = %s", (new, old))

    for df in frappe.get_meta("DocType").get_table_fields():
        frappe.db.sql(
            f"UPDATE `tab{df.options}` SET parent = %s WHERE parent = %s AND parenttype = 'DocType'",
            (new, old),
        )

    # Child tables of the renamed DocType point back at it through parenttype.
    for child in frappe.get_all(
        "DocField",
        filters={"parent": new, "fieldtype": ["in", frappe.model.table_fields]},
        pluck="options",
    ):
        if frappe.db.table_exists(child, cached=False):
            frappe.db.sql(f"UPDATE `tab{child}` SET parenttype = %s WHERE parenttype = %s", (new, old))


def _migrate_customizations(old, new):
    frappe.db.sql("UPDATE `tabCustom DocPerm` SET parent = %s WHERE parent = %s", (new, old))

    for name in frappe.get_all("Property Setter", filters={"doc_type": old}, pluck="name"):
        new_name = new + name[len(old):] if name.startswith(f"{old}-") else name
        if new_name != name and frappe.db.exists("Property Setter", new_name):
            frappe.db.delete("Property Setter", {"name": name})
        else:
            frappe.db.set_value("Property Setter", name, {"doc_type": new, "name": new_name})

    for name in frappe.get_all("Custom Field", filters={"dt": old}, pluck="name"):
        new_name = new + name[len(old):] if name.startswith(f"{old}-") else name
        frappe.db.set_value("Custom Field", name, {"dt": new, "name": new_name})


def _update_doctype_references(old, new, erpnext_modules):
    """Repoint fields that store a DocType name (Link to DocType, Dynamic Link)."""
    for field in get_link_fields("DocType"):
        _update_field(field["parent"], field["fieldname"], old, new, erpnext_modules)

    for df in get_dynamic_link_map().get("DocType", []):
        _update_field(df.parent, df.fieldname, old, new, erpnext_modules, type_field=df.options)


def _update_field(doctype, fieldname, old, new, erpnext_modules, type_field=None):
    try:
        meta = frappe.get_meta(doctype)
    except Exception:
        return

    if meta.is_virtual or meta.module in erpnext_modules:
        return

    if meta.issingle:
        values = frappe.db.get_singles_dict(doctype)
        if values.get(fieldname) == old and (not type_field or values.get(type_field) == "DocType"):
            frappe.db.set_single_value(doctype, fieldname, new)
        return

    if not frappe.db.table_exists(doctype, cached=True) or not frappe.db.has_column(doctype, fieldname):
        return

    table = frappe.qb.DocType(doctype)
    query = frappe.qb.from_(table).select(table.name).where(table[fieldname] == old)
    if type_field:
        if not frappe.db.has_column(doctype, type_field):
            return
        query = query.where(table[type_field] == "DocType")

    has_module = frappe.db.has_column(doctype, "module")
    if has_module:
        query = query.select(table.module)
    if meta.istable:
        query = query.select(table.parent, table.parenttype)

    for row in query.run(as_dict=True):
        if has_module and row.module in erpnext_modules:
            continue
        if meta.istable and _parent_module(row.parenttype, row.parent) in erpnext_modules:
            continue
        frappe.db.set_value(doctype, row.name, fieldname, new, update_modified=False)


def _parent_module(parenttype, parent):
    if not parenttype or not parent:
        return None
    try:
        if frappe.db.table_exists(parenttype, cached=True) and frappe.db.has_column(parenttype, "module"):
            val = frappe.db.get_value(parenttype, parent, "module")
            if val:
                return val
        return frappe.get_meta(parenttype).module
    except Exception:
        return None


def _update_user_settings(old, new):
    frappe.db.sql("UPDATE `__UserSettings` SET doctype = %s WHERE doctype = %s", (new, old))
    if frappe.db.exists("List View Settings", old):
        frappe.db.sql("UPDATE `tabList View Settings` SET name = %s WHERE name = %s", (new, old))

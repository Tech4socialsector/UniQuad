# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""
Pre-model-sync: Programme is now named by (and unique on) program_name, and
Section by section_name. Rename every record to that value and merge
duplicates (all links are re-pointed) BEFORE the unique index is added,
otherwise the schema sync fails on the existing duplicates.

The rest of the data move runs post-model-sync in academic_core_restructure.
"""

import frappe
from frappe.model.rename_doc import rename_doc


def execute():
	rename_by_field("Programme", "program_name")
	rename_by_field("Section", "section_name")
	frappe.db.commit()


def rename_by_field(doctype, fieldname):
	"""Rename each record to its `fieldname` value; merge records that share it."""
	if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, fieldname):
		return

	rows = frappe.db.sql(
		f"SELECT name, `{fieldname}` AS target FROM `tab{doctype}` ORDER BY creation",
		as_dict=True,
	)
	groups = {}
	for row in rows:
		target = (row.target or "").strip()
		if target:
			groups.setdefault(target, []).append(row.name)

	for target, names in groups.items():
		keep = target if target in names else names[0]
		if keep != target:
			rename_doc(
				doctype, keep, target,
				force=True, ignore_permissions=True, show_alert=False, rebuild_search=False,
			)
		for other in names:
			if other not in (keep, target):
				rename_doc(
					doctype, other, target,
					merge=True, force=True, ignore_permissions=True, show_alert=False, rebuild_search=False,
				)

import frappe


def execute():
	"""Cancelled Classes Report is replaced by the Cancelled filter on Time Table Report."""
	frappe.delete_doc("Report", "Cancelled Classes Report", ignore_missing=True, force=True)

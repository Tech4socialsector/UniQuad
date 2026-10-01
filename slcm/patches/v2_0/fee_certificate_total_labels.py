import frappe

# purpose -> (labels still on an old default, new label)
LABELS = {
	"Fee Certificate for Education Loan": (("", "Total"), "Total Fee Payable"),
	"Fee Certificate/ Receipt for Scholarship/others": (("", "Total", "Total Fee paid"), "Total Fee Paid"),
}


def execute():
	"""Rename the table's total row; labels staff have already customised are left alone."""
	for purpose, (old_labels, new_label) in LABELS.items():
		name = frappe.db.get_value(
			"Fee Certificate Purpose Template", {"parent": "Fee Certificate Settings", "purpose": purpose}, ["name", "total_label"]
		)
		if name and (name[1] or "") in old_labels:
			frappe.db.set_value("Fee Certificate Purpose Template", name[0], "total_label", new_label)
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")

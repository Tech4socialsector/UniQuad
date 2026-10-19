import frappe

# Old Student Master bank columns -> new savings-account columns
FIELD_MAP = {
    "bank_name": "savings_bank_name",
    "bank_account_number": "savings_account_number",
    "ifsc_code": "savings_ifsc_code",
    "branch_name": "savings_branch_name",
    "account_holder_name": "savings_account_holder_name",
}


def execute():
    """Keep existing bank details by renaming the columns before the DocType sync."""
    if not frappe.db.table_exists("Student Master"):
        return

    for old, new in FIELD_MAP.items():
        if frappe.db.has_column("Student Master", old) and not frappe.db.has_column("Student Master", new):
            frappe.db.rename_column("Student Master", old, new)

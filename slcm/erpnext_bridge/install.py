"""ERPNext-side pieces of the bridge, created only on sites that have ERPNext.

Custom fields on Journal Entry and Company, the "SLCM Finance" Workspace, Workspace Sidebar and Desktop Icon all
reference ERPNext, so they are created in code here (not shipped as JSON) and skipped entirely on sites without
ERPNext. They are non-standard and module-less, so developer mode never exports them into the slcm app folder.
Nothing in this module may break `bench migrate`: errors are logged, never raised.
"""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from slcm.erpnext_bridge import erpnext_installed

NAME = "SLCM Finance"
ACCOUNTS_ROLES = ("System Manager", "Accounts Manager", "Accounts User")
REPORTS = ("SLCM Fee Accounting Summary", "SLCM ERPNext Reconciliation")
STATEMENTS = (
	("General Ledger", "General Ledger"),
	("Trial Balance", "Trial Balance"),
	("Profit and Loss", "Profit and Loss Statement"),
	("Balance Sheet", "Balance Sheet"),
)


def _data(fieldname, label, insert_after, **extra):
	return {
		"fieldname": fieldname,
		"fieldtype": "Data",
		"label": label,
		"options": "",
		"insert_after": insert_after,
		"read_only": 1,
		"no_copy": 1,
		**extra,
	}


def _account(fieldname, label, insert_after, description):
	return {
		"fieldname": fieldname,
		"fieldtype": "Link",
		"label": label,
		"options": "Account",
		"insert_after": insert_after,
		"description": description,
	}


CUSTOM_FIELDS = {
	# Journal Entries posted by the bridge carry their SLCM source. These are Data, not Link fields: a Link from a
	# submitted Journal Entry would make Frappe refuse to cancel the Fee Payment / Fee Refund (or delete the Student).
	"Journal Entry": [
		{
			"fieldname": "slcm_section",
			"fieldtype": "Section Break",
			"label": "SLCM Reference",
			"insert_after": "remark",
			"collapsible": 1,
			"depends_on": "eval:doc.slcm_reference_name",
		},
		_data("slcm_reference_doctype", "SLCM Document Type", "slcm_section", in_standard_filter=1),
		_data("slcm_reference_name", "SLCM Document", "slcm_reference_doctype", search_index=1),
		{"fieldname": "slcm_column_break", "fieldtype": "Column Break", "insert_after": "slcm_reference_name"},
		_data("slcm_student", "Student", "slcm_column_break", in_standard_filter=1),
		_data("slcm_programme", "Programme", "slcm_student"),
	],
	# Bridge settings live on the Company they post to. Cost center, cash and bank come from the Company's own
	# defaults; payment modes from Mode of Payment; university banks from Bank Account.
	"Company": [
		# Own tab: Frappe moves a custom Section Break forward to the next section (skipping tab breaks), which
		# would land it inside "Accounts Closing"; a Tab Break is placed exactly after the Accounts tab's last field.
		{
			"fieldname": "slcm_fee_tab",
			"fieldtype": "Tab Break",
			"label": "SLCM Fees",
			"insert_after": "asset_received_but_not_billed",
		},
		{
			"fieldname": "slcm_fee_section",
			"fieldtype": "Section Break",
			"label": "SLCM Fee Accounting",
			"insert_after": "slcm_fee_tab",
			"collapsible": 1,
			"description": "Posts SLCM fee receipts, refunds and Razorpay settlements to this company as Journal "
			"Entries (cash basis). Cash, bank and cost center come from this company's defaults, payment-mode "
			"accounts from Mode of Payment, university banks from Bank Account, and each Fee Component's income "
			"ledger from the Account named like its Ledger.",
		},
		{
			"fieldname": "slcm_enable_fee_posting",
			"fieldtype": "Check",
			"label": "Enable SLCM Fee Posting",
			"insert_after": "slcm_fee_section",
		},
		{
			"fieldname": "slcm_submit_journal_entries",
			"fieldtype": "Check",
			"label": "Submit SLCM Journal Entries",
			"default": "1",
			"insert_after": "slcm_enable_fee_posting",
			"description": "Untick to create them as Draft for review.",
		},
		{
			"fieldname": "slcm_posting_from_date",
			"fieldtype": "Date",
			"label": "Post SLCM Fees Dated On/After",
			"insert_after": "slcm_submit_journal_entries",
			"mandatory_depends_on": "eval:doc.slcm_enable_fee_posting",
		},
		_account(
			"slcm_default_fee_income_account",
			"Default Fee Income Account",
			"slcm_posting_from_date",
			"For Fee Components whose Ledger has no Account of the same name",
		),
		{"fieldname": "slcm_fee_column_break", "fieldtype": "Column Break", "insert_after": "slcm_default_fee_income_account"},
		_account(
			"slcm_unallocated_fee_account",
			"Unallocated Fee Receipts Account",
			"slcm_fee_column_break",
			"Part of a payment not allocated to any Fee Demand",
		),
		_account(
			"slcm_output_gst_account", "Output GST on Fees Account", "slcm_unallocated_fee_account", "GST in taxable Fee Components"
		),
		_account("slcm_fee_refund_account", "Fee Refunds Account", "slcm_output_gst_account", "Expense for Fee Refunds"),
		_account(
			"slcm_gateway_charges_account", "Payment Gateway Charges Account", "slcm_fee_refund_account", "Razorpay fees"
		),
		_account(
			"slcm_gateway_gst_account", "GST on Gateway Charges Account", "slcm_gateway_charges_account", "GST on Razorpay fees"
		),
	],
}


# ── hooks ───────────────────────────────────────────────────────────────────────


def after_migrate():
	"""slcm after_install / after_migrate."""
	if not erpnext_installed():
		return
	try:
		setup_erpnext_side()
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="SLCM ERPNext Bridge: setup failed")


def after_app_install(app_name=None):
	"""ERPNext installed later on an SLCM site."""
	if app_name == "erpnext":
		after_migrate()


def before_app_uninstall(app_name=None):
	"""ERPNext being removed: remove what the bridge added to ERPNext."""
	if app_name != "erpnext":
		return
	try:
		for doctype in ("Desktop Icon", "Workspace Sidebar", "Workspace"):
			if frappe.db.exists(doctype, NAME):
				frappe.delete_doc(doctype, NAME, force=True, ignore_permissions=True)
		for dt, fields in CUSTOM_FIELDS.items():
			for df in fields:
				if frappe.db.exists("Custom Field", f"{dt}-{df['fieldname']}"):
					frappe.delete_doc("Custom Field", f"{dt}-{df['fieldname']}", force=True, ignore_permissions=True)
	except Exception:
		frappe.log_error(title="SLCM ERPNext Bridge: cleanup before ERPNext uninstall failed")


# ── setup ───────────────────────────────────────────────────────────────────────


def setup_erpnext_side():
	_ensure_custom_fields()
	_ensure_workspace()
	_ensure_sidebar()
	_ensure_desktop_icon()


def _ensure_custom_fields():
	# Frappe refuses to change a Custom Field's type in place (an early build used Link fields); recreate those.
	for dt, fields in CUSTOM_FIELDS.items():
		for df in fields:
			name = f"{dt}-{df['fieldname']}"
			if frappe.db.get_value("Custom Field", name, "fieldtype") not in (None, df["fieldtype"]):
				frappe.delete_doc("Custom Field", name, ignore_permissions=True)
	create_custom_fields(CUSTOM_FIELDS, update=True)


def _ensure_workspace():
	shortcuts = [
		("Fee Accounting Summary", "SLCM Fee Accounting Summary", "Report", "Green"),
		("Fee Reconciliation", "SLCM ERPNext Reconciliation", "Report", "Orange"),
		("SLCM Journal Entries", "Journal Entry", "DocType", "Blue"),
		("Company Settings", "Company", "DocType", "Grey"),
	]
	cards = [
		("SLCM Fee Reports", [(r, r, "Report", 1) for r in REPORTS]),
		("Financial Statements", [(label, report, "Report", 1) for label, report in STATEMENTS]),
		(
			"Setup",
			[
				("Company (SLCM Fee Accounting)", "Company", "DocType", 0),
				("Mode of Payment", "Mode of Payment", "DocType", 0),
				("Bank Account", "Bank Account", "DocType", 0),
				("Chart of Accounts", "Account", "DocType", 0),
			],
		),
	]
	content = [{"id": "slcmfin_h", "type": "header", "data": {"text": f'<span class="h4"><b>{NAME}</b></span>', "col": 12}}]
	content += [{"id": f"slcmfin_s{i}", "type": "shortcut", "data": {"shortcut_name": s[0], "col": 3}} for i, s in enumerate(shortcuts)]
	content += [{"id": "slcmfin_sp", "type": "spacer", "data": {"col": 12}}]
	content += [{"id": f"slcmfin_c{i}", "type": "card", "data": {"card_name": c[0], "col": 4}} for i, c in enumerate(cards)]

	doc = frappe.get_doc("Workspace", NAME) if frappe.db.exists("Workspace", NAME) else frappe.new_doc("Workspace")
	doc.update(
		{
			"label": NAME,
			"title": NAME,
			"icon": "accounting",
			"public": 1,
			"module": None,
			"app": None,
			"content": json.dumps(content),
		}
	)
	doc.set("shortcuts", [])
	for label, link_to, link_type, color in shortcuts:
		row = {"label": label, "link_to": link_to, "type": link_type, "color": color}
		if link_to == "Journal Entry":
			row.update(doc_view="List", stats_filter=json.dumps([["Journal Entry", "slcm_reference_name", "is", "set"]]))
		doc.append("shortcuts", row)
	doc.set("links", [])
	for card, links in cards:
		doc.append("links", {"type": "Card Break", "label": card, "link_count": len(links)})
		for label, link_to, link_type, is_query_report in links:
			doc.append(
				"links",
				{"type": "Link", "label": label, "link_to": link_to, "link_type": link_type, "is_query_report": is_query_report},
			)
	doc.set("roles", [{"role": r} for r in ACCOUNTS_ROLES if frappe.db.exists("Role", r)])
	doc.flags.ignore_permissions = True
	doc.save()


def _ensure_sidebar():
	items = [("Link", "Home", NAME, "Workspace", "home")]
	items += [("Section Break", "SLCM Fee Reports", None, None, "sheet")]
	items += [("Link", r.replace("SLCM ", ""), r, "Report", None) for r in REPORTS]
	items += [("Section Break", "Financial Statements", None, None, "accounting")]
	items += [("Link", label, report, "Report", None) for label, report in STATEMENTS]
	items += [("Section Break", "Setup", None, None, "settings")]
	items += [
		("Link", "Company", "Company", "DocType", None),
		("Link", "Mode of Payment", "Mode of Payment", "DocType", None),
		("Link", "Bank Account", "Bank Account", "DocType", None),
		("Link", "Journal Entry", "Journal Entry", "DocType", None),
	]
	doc = (
		frappe.get_doc("Workspace Sidebar", NAME)
		if frappe.db.exists("Workspace Sidebar", NAME)
		else frappe.new_doc("Workspace Sidebar")
	)
	doc.update({"title": NAME, "header_icon": "accounting", "standard": 0, "app": None})
	doc.set("items", [])
	for item_type, label, link_to, link_type, icon in items:
		section = item_type == "Section Break"
		row = {
			"type": item_type,
			"label": label,
			"link_to": link_to,
			"link_type": link_type or "DocType",
			"child": 0 if section or label == "Home" else 1,
			"indent": 1 if section else 0,
			"collapsible": 1,
		}
		if icon:
			row["icon"] = icon
		doc.append("items", row)
	doc.flags.ignore_permissions = True
	doc.save()


def _ensure_desktop_icon():
	# Owned by Administrator and non-standard: visible to users with an accounts role, never exported.
	if not frappe.db.exists("Desktop Icon", "Accounting"):
		return
	doc = (
		frappe.get_doc("Desktop Icon", NAME) if frappe.db.exists("Desktop Icon", NAME) else frappe.new_doc("Desktop Icon")
	)
	doc.update(
		{
			"label": NAME,
			"icon": "file",
			"icon_type": "Link",
			"link_type": "Workspace Sidebar",
			"link_to": NAME,
			"parent_icon": "Accounting",
			"standard": 0,
			"app": None,
			"hidden": 0,
			"idx": 20,
		}
	)
	doc.set("roles", [{"role": role} for role in ACCOUNTS_ROLES if frappe.db.exists("Role", role)])
	doc.flags.ignore_permissions = True
	doc.save()
	if doc.owner != "Administrator":
		frappe.db.set_value("Desktop Icon", doc.name, "owner", "Administrator", update_modified=False)

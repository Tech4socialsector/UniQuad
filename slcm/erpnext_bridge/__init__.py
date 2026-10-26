"""SLCM fees -> ERPNext accounting bridge (one-way, reporting only).

Everything here is inert unless ERPNext is installed on the site AND "Enable SLCM Fee Posting" is ticked on an
ERPNext Company. All configuration lives in ERPNext records (Company, Mode of Payment, Bank Account, Account);
see config.py and docs/erpnext_fee_bridge_test_checklist.md.
"""

import frappe


def erpnext_installed():
	try:
		return "erpnext" in frappe.get_installed_apps()
	except Exception:
		return False

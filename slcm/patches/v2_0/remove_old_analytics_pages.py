import frappe

# Replaced by the Uniquad Overall Dashboard (uniquad-overall-dashboard).
# slcm-record-drilldown only served the workspace analytics page.
OLD_PAGES = ("slcm-analytics-dashboard", "slcm-analytics-workspace-dashboard", "slcm-record-drilldown")


def execute():
	for name in OLD_PAGES:
		if frappe.db.exists("Page", name):
			frappe.delete_doc("Page", name, force=True, ignore_missing=True)

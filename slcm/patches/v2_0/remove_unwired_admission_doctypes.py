"""Remove admission doctypes that no live flow uses.

Quota Policy, the Admission Stage Template / Stage Config / Evaluation
Config engine, Admission CC Role, Admission Round and Admission Application
were only read by code that never ran with data (the old setup-wizard
backend, an empty daily deadline job, empty dashboard widgets). That code
is gone; this deletes the DocType records, site customisations and tables.
Parents come before their child tables.
"""

import frappe

DOCTYPES = (
	"Quota Policy",
	"Quota Policy Entry",
	"Admission Stage Template",
	"Admission Stage Config",
	"Evaluation Config",
	"Score Component",
	"Admission Stages",
	"Admission CC Role",
	"Admission Round",
	"Admission Application",
)


def execute():
	frappe.db.delete("Custom Field", {"dt": ["in", DOCTYPES]})
	frappe.db.delete("Custom Field", {"options": ["in", DOCTYPES]})
	frappe.db.delete("Property Setter", {"doc_type": ["in", DOCTYPES]})
	frappe.delete_doc_if_exists("Workflow", "Admission Application Workflow", force=1)

	for doctype in DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=1, ignore_missing=True)
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")
	frappe.db.commit()

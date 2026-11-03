"""Remove admission doctypes that no flow uses.

None of these holds data, is linked from another doctype or is called from
code: the standalone ones were never wired into the admission flow, and the
child tables are not the options of any Table field. Their folders are gone,
so this deletes the DocType records, any site customisations and the tables.
"""

import frappe

DOCTYPES = (
	"Admission Cycle Rule",
	"Admission Year Audit Log",
	"Reservation Rule",
	"CLAT Rank Import",
	"GDPR Data Request",
	"Compliance Report Config",
	"Admission Dashboard Config",
	"Admission Report Config",
	# Child tables not used by any doctype
	"Admission Stage Next Step",
	"Applicant Document Detail",
	"Campus Seat Matrix Detail",
	"Interview Configuration Program",
	"Participating Campus",
	"Program Career Item",
	"Program Curriculum Item",
	"Program Faculty Item",
	"Program Mapping",
	"Eligibility Program",
)


def execute():
	frappe.db.delete("Custom Field", {"dt": ["in", DOCTYPES]})
	frappe.db.delete("Property Setter", {"doc_type": ["in", DOCTYPES]})

	for doctype in DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=1, ignore_missing=True)
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")
	frappe.db.commit()

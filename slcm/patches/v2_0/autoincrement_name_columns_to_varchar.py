import frappe
from frappe.core.doctype.doctype.doctype import change_name_column_type

# DocTypes that used to be named by autoincrement and now use the default
# (hash) naming
DOCTYPES = ("Student Group Student", "Eligibility Evaluation")


def execute():
	"""Turn the `name` column of former autoincrement DocTypes back into varchar.

	On sites created while these DocTypes were autoincrement, `name` is an
	integer column. Frappe only converts it when the naming rule changes on an
	empty table, so sites that already had rows kept the integer column and
	every new row fails with "Incorrect integer value: '<hash>' for column
	`name`" (e.g. saving a Student Group). Existing numeric names stay valid
	as strings.
	"""
	for doctype in DOCTYPES:
		if not frappe.db.table_exists(doctype):
			continue

		column_type = (frappe.db.get_column_type(doctype, "name") or "").lower()
		if not any(t in column_type for t in ("int", "serial")):
			continue  # already varchar (new sites, or patched before)

		change_name_column_type(doctype, "varchar(140)")

		# The autoincrement sequence is no longer used
		if frappe.db.db_type == "mariadb":
			frappe.db.sql_ddl(f"drop sequence if exists `{frappe.scrub(doctype)}_id_seq`")

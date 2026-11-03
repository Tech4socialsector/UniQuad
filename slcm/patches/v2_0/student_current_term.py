"""Student Master: Current Year (year_of_study) shows "1st Year" etc. and
Current Term links the Term Master.

year_of_study was empty or just "1" for many students; fill it from the
numeric current_year. Current Term and each Academic Log row's Programme Term
come from the Academic Terms' Term Mapping (none exist yet when this runs;
saving an Academic Term's mapping fills them)."""

import frappe
from frappe.utils import cint

from slcm.slcm.doctype.student_enrollment.student_enrollment import _ordinal


def execute():
	for name, current_year, year_of_study in frappe.db.sql(
		"SELECT name, current_year, year_of_study FROM `tabStudent Master`"
	):
		year = cint("".join(ch for ch in str(current_year or "") if ch.isdigit()))
		if not year:
			continue
		label = f"{_ordinal(year)} Year"
		if year_of_study != label:
			frappe.db.set_value("Student Master", name, "year_of_study", label, update_modified=False)

	from slcm.slcm.doctype.academic_term.academic_term import apply_term_mapping

	for term in frappe.get_all("Academic Term Mapping", filters={"parenttype": "Academic Term"}, pluck="parent", distinct=True):
		apply_term_mapping(term)

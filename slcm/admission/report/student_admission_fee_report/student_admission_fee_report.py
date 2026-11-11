# Copyright (c) 2026, SLCM and contributors
# For license information, please see license.txt

"""Student Admission Fee Report.

Confirmation Fee / Admission Fee payment attempts made against NLSAT Offer Letters,
in the Fee collection report.xlsx layout including Student ID (from Student Master).
"""

import frappe

from slcm.admission.report.nlsat_fee_collection_report.nlsat_fee_collection_report import (
	get_columns,
	get_fee_rows,
	get_summary,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_fee_rows(filters, source="Offer Letter")
	if filters.get("fee_component"):
		data = [r for r in data if r.fee_component == filters.fee_component]
	return get_columns(include_student_id=True), data, None, None, get_summary(data)

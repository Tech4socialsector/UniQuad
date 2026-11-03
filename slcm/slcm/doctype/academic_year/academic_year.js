// Copyright (c) 2025, Nishanth and contributors
// For license information, please see license.txt

frappe.ui.form.on("Academic Year", {
	refresh(frm) {
		set_date_limits(frm);
	},

	year_start_date(frm) {
		set_date_limits(frm);
		if (
			frm.doc.year_end_date &&
			frm.doc.year_start_date &&
			frm.doc.year_end_date <= frm.doc.year_start_date
		) {
			frm.set_value("year_end_date", null);
		}
	},
});

// Past dates are disabled in the date pickers. The end date picker also
// starts after the chosen start date.
function set_date_limits(frm) {
	const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	set_min_date(frm, "year_start_date", today);

	let end_min = today;
	if (frm.doc.year_start_date) {
		const start = frappe.datetime.str_to_obj(frappe.datetime.add_days(frm.doc.year_start_date, 1));
		if (start > end_min) end_min = start;
	}
	set_min_date(frm, "year_end_date", end_min);
}

function set_min_date(frm, fieldname, min_date) {
	const field = frm.get_field(fieldname);
	if (field && field.datepicker) {
		field.datepicker.update({ minDate: min_date });
	}
}

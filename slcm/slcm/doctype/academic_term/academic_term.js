// Copyright (c) 2025, Nishanth and contributors
// For license information, please see license.txt

frappe.ui.form.on("Academic Term", {
	refresh(frm) {
		set_term_date_limits(frm);
	},

	academic_year(frm) {
		set_term_date_limits(frm);
	},

	term_start_date(frm) {
		set_term_date_limits(frm);
	},
});

// Keep the date pickers inside the selected Academic Year.
function set_term_date_limits(frm) {
	if (!frm.doc.academic_year) return;

	frappe.db
		.get_value("Academic Year", frm.doc.academic_year, ["year_start_date", "year_end_date"])
		.then(({ message }) => {
			if (!message) return;
			const year_start = frappe.datetime.str_to_obj(message.year_start_date);
			const year_end = frappe.datetime.str_to_obj(message.year_end_date);

			let end_min = year_start;
			if (frm.doc.term_start_date) {
				end_min = frappe.datetime.str_to_obj(frappe.datetime.add_days(frm.doc.term_start_date, 1));
			}

			update_picker(frm, "term_start_date", year_start, year_end);
			update_picker(frm, "term_end_date", end_min, year_end);
		});
}

function update_picker(frm, fieldname, min_date, max_date) {
	const field = frm.get_field(fieldname);
	if (field && field.datepicker) {
		field.datepicker.update({ minDate: min_date, maxDate: max_date });
	}
}

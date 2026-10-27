// Copyright (c) 2025, Nishanth and contributors
// For license information, please see license.txt

frappe.ui.form.on("Course Offering", {
	refresh(frm) {
		set_term_query(frm);
	},

	academic_year(frm) {
		set_term_query(frm);
		if (frm.doc.term_name) {
			frappe.db.get_value("Academic Term", frm.doc.term_name, "academic_year").then(({ message }) => {
				if (message && message.academic_year !== frm.doc.academic_year) {
					frm.set_value("term_name", null);
				}
			});
		}
	},

	course_title(frm) {
		if (!frm.doc.course_title) return;
		frappe.db.get_value("Course", frm.doc.course_title, "course_type").then(({ message }) => {
			frm.set_value("is_elective", message && message.course_type === "Elective" ? 1 : 0);
		});
	},
});

// Only terms of the selected Academic Year can be picked.
function set_term_query(frm) {
	frm.set_query("term_name", function () {
		return { filters: { academic_year: frm.doc.academic_year } };
	});
}

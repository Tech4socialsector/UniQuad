// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Classes", {
	setup(frm) {
		// Only terms of the selected Academic Year can be picked.
		frm.set_query("academic_term", () => ({
			filters: { academic_year: frm.doc.academic_year },
		}));
		frm.set_query("course", () => ({ filters: { status: "Active" } }));
		// A Group class may take students from any programme.
		frm.set_query("student_enrollment", "enrolled_students", () => ({
			filters:
				frm.doc.class_type === "Group"
					? { status: "Enrolled" }
					: { program: frm.doc.programme, status: "Enrolled" },
		}));
	},

	refresh(frm) {
		if (frm.doc.class_type !== "Group") {
			frm.add_custom_button(__("Get Students"), () => get_students(frm));
		}
		if (frm.perm[0] && frm.perm[0].write) {
			frm.add_custom_button(__("Add / Remove Students"), () => add_remove_students(frm));
		}
		// Dialogs in public/js/class_time_table.js
		if (!frm.is_new() && !frm.is_dirty()) {
			if (frappe.model.can_create("Time Table")) {
				frm.add_custom_button(__("Create Time Table"), () => slcm.class_time_table.open_create(frm), __("Time Table"));
			}
			if (frappe.model.can_read("Time Table")) {
				frm.add_custom_button(__("View Time Table"), () => slcm.class_time_table.open_view(frm), __("Time Table"));
			}
		}
	},

	class_type(frm) {
		frm.refresh();
	},

	academic_year(frm) {
		frm.set_value("academic_term", null);
	},
});

// The class's Enrolled students ticked, others found with any filters (any
// year); ticked ones not listed are added, unticked ones taken off. Rows with
// another status (Completed, Withdrawn ...) stay as history.
function add_remove_students(frm) {
	const enrolled = (frm.doc.enrolled_students || []).filter((r) => r.status === "Enrolled");
	slcm.class_students.pick({
		current: enrolled.map((r) => ({ student_enrollment: r.student_enrollment, student_name: r.student_name, section: r.section })),
		programme: frm.doc.class_type === "Group" ? "" : frm.doc.programme,
	}).then((picked) => {
		if (!picked) return;
		const keep = new Set(picked.map((r) => r.student_enrollment));
		const listed = new Set((frm.doc.enrolled_students || []).map((r) => r.student_enrollment));
		const removed = enrolled.filter((r) => !keep.has(r.student_enrollment));
		removed.forEach((r) => frappe.model.clear_doc(r.doctype, r.name));
		const added = picked.filter((r) => !listed.has(r.student_enrollment));
		added.forEach((r) => frm.add_child("enrolled_students", {
			student_enrollment: r.student_enrollment,
			student_name: r.student_name,
			section: r.section,
			status: "Enrolled",
		}));
		if (!added.length && !removed.length) return;
		frm.refresh_field("enrolled_students");
		frm.save().then(() => frappe.show_alert({
			message: __("{0} student(s) added, {1} removed.", [added.length, removed.length]),
			indicator: "green",
		}));
	});
}

// Fill the table with the section's enrolled students, skipping ones already listed.
function get_students(frm) {
	const { programme, academic_year, year_no, section } = frm.doc;
	if (!programme || !academic_year || !section || !year_no) {
		frappe.msgprint(__("Select Academic Year, Programme, Year and Section first."));
		return;
	}
	frappe.call({
		method: "slcm.slcm.doctype.classes.classes.get_enrollment_students",
		args: { programme, academic_year, year_no, section },
		callback({ message }) {
			const existing = new Set((frm.doc.enrolled_students || []).map((r) => r.student_enrollment));
			const rows = (message || []).filter((s) => !existing.has(s.name));
			rows.forEach((s) => {
				frm.add_child("enrolled_students", {
					student_enrollment: s.name,
					student_name: s.student_name,
					section: s.section,
					status: "Enrolled",
				});
			});
			frm.refresh_field("enrolled_students");
			frappe.show_alert({
				message: __("Added {0} student(s)", [rows.length]),
				indicator: rows.length ? "green" : "orange",
			});
		},
	});
}

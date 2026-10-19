// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Grade Appeal", {
	setup(frm) {
		// Only exam plans the student has marks in
		frm.set_query("exam_plan", () => {
			if (!frm.doc.student) return {};
			return {
				query: "slcm.slcm.doctype.grade_appeal.grade_appeal.exam_plans_for_student",
				filters: { student: frm.doc.student },
			};
		});
		// Only offerings of courses the student has marks for in that exam plan
		frm.set_query("course_offering", () => {
			if (!frm.doc.student || !frm.doc.exam_plan) return {};
			return {
				query: "slcm.slcm.doctype.grade_appeal.grade_appeal.offerings_for_student",
				filters: { student: frm.doc.student, exam_plan: frm.doc.exam_plan },
			};
		});
	},

	refresh(frm) {
		if (frm.is_new()) return;
		const open = ["Submitted", "Under Review"].includes(frm.doc.status);
		frm.dashboard.clear_headline();
		if (open) {
			frm.dashboard.set_headline(
				__("Set the status to Resolved or Rejected and enter the Resolution Details — the student sees them in the portal."),
				"orange"
			);
		}
		if (frm.doc.status === "Submitted") {
			frm.add_custom_button(__("Start Review"), () => {
				frm.set_value("status", "Under Review");
				frm.save();
			});
		}
	},

	student(frm) {
		frm.set_value("exam_plan", "");
		frm.set_value("course_offering", "");
	},

	exam_plan(frm) {
		frm.set_value("course_offering", "");
		frm.set_value("current_grade", "");
		frm.set_value("current_marks", 0);
	},

	course_offering(frm) {
		// Grade/marks are snapshotted on save; clear stale values when the course changes
		frm.set_value("current_grade", "");
		frm.set_value("current_marks", 0);
	},
});

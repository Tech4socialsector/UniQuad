// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

// Student Group Student fields belonging to each group type
const SG_HOURS = ["1st", "2nd", "3rd", "4th", "5th", "6th"];
const SG_CP_FIELDS = ["class_participation_section"]
	.concat(SG_HOURS.map((h) => `class_participation_${h}_hour`))
	.concat(SG_HOURS.map((h) => `${h}_cp_grade`));
const SG_OH_FIELDS = [
	"office_hours_section",
	"office_hour_1st_hour",
	"office_hour_2nd_hour",
	"1st_oh_grade",
	"2nd_oh_grade",
];

// Show only the Class Participation or Office Hours section in the student
// rows, according to Group Based On (nothing shown until a type is chosen).
function sg_toggle_group_sections(frm) {
	const grid = frm.fields_dict.students && frm.fields_dict.students.grid;
	if (!grid) return;
	const is_cp = frm.doc.group_based_on === "Class-Participation";
	const is_oh = frm.doc.group_based_on === "Office Hours";
	SG_CP_FIELDS.forEach((f) => grid.toggle_display(f, is_cp));
	SG_OH_FIELDS.forEach((f) => grid.toggle_display(f, is_oh));
	// An already-open row editor (grid.open_grid_row is its GridRowForm) keeps
	// its old layout until refreshed; its fields share the docfields updated above.
	const open_form = grid.open_grid_row;
	if (open_form && open_form.layout && open_form.row) {
		open_form.layout.refresh(open_form.row.doc);
	}
}

frappe.ui.form.on("Student Group", {
	setup(frm) {
		// Academic Year → only Active years
		frm.set_query("academic_year", () => ({
			filters: { status: "Active" },
		}));

		// Academic Term → terms of the selected Academic Year
		frm.set_query("academic_term", () => ({
			filters: { academic_year: frm.doc.academic_year || "" },
		}));

		// Programme → programmes that have a Course Offering in the selected year + term
		frm.set_query("programme", () => ({
			query: "slcm.slcm.doctype.student_group.student_group.programme_query",
			filters: {
				academic_year: frm.doc.academic_year || "",
				academic_term: frm.doc.academic_term || "",
			},
		}));

		// Course Offering → matches the selected year, term and programme
		frm.set_query("course_offering", () => ({
			filters: {
				academic_year: frm.doc.academic_year || "",
				term_name: frm.doc.academic_term || "",
				program: frm.doc.programme || "",
			},
		}));
	},

	// Changing a parent filter clears everything that depended on it
	academic_year(frm) {
		frm.set_value("academic_term", "");
	},

	academic_term(frm) {
		frm.set_value("programme", "");
	},

	programme(frm) {
		frm.set_value("course_offering", "");
	},

	refresh(frm) {
		sg_toggle_group_sections(frm);
	},

	group_based_on(frm) {
		sg_toggle_group_sections(frm);
	},
});

frappe.ui.form.on("Student Group Student", {
	// Re-apply when a row editor opens (covers rows added after load)
	form_render(frm) {
		sg_toggle_group_sections(frm);
	},
	students_add(frm) {
		sg_toggle_group_sections(frm);
	},
});

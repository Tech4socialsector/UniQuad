frappe.ui.form.on("Fee Notification", {
	refresh(frm) {
		frm.page.clear_primary_action();
		frm.page.clear_secondary_action();

		if (frm.doc.status === "Draft" && !frm.is_new()) {
			frm.add_custom_button(__("Publish"), () => {
				frappe.confirm(
					__("Are you sure you want to publish this Fee Notification? "
						+ "Once published, fee demands can be generated for all eligible students."),
					() => {
						frm.call("publish").then(() => frm.reload_doc());
					}
				);
			}, __("Actions")).addClass("btn-warning");
		}

		if (frm.doc.status === "Published") {
			frm.page.set_primary_action(__("Generate Fee Demands"), () => {
				frappe.confirm(
					__("This will create Fee Demands for all eligible students "
						+ "for Academic Year <b>{0}</b>. "
						+ "Existing demands will be skipped automatically.<br><br>"
						+ "This runs as a background job and may take a few minutes. Proceed?",
						[frm.doc.academic_year]),
					() => {
						frm.call("generate_demands").then(() => frm.reload_doc());
					}
				);
			});

			if (frm.doc.generation_log) {
				frm.add_custom_button(__("View Generation Log"), () => {
					frappe.set_route("Form", "Fee Demand Generation Log", frm.doc.generation_log);
				}, __("Actions"));
			}

			frm.set_intro(
				__("This notification is Published. Click <b>Generate Fee Demands</b> "
					+ "to create demands for all eligible students."),
				"blue"
			);
		} else if (!frm.is_new()) {
			frm.set_intro(
				__("This notification is in <b>Draft</b> state. "
					+ "Add all fee components and click <b>Actions → Publish</b> to activate it."),
				"orange"
			);
		}

		// Make components table read-only after publish
		frm.set_df_property("components", "read_only", frm.doc.status === "Published" ? 1 : 0);
	},

	academic_year(frm) {
		// Auto-filter fee_structure in child rows by academic_year
		frm.fields_dict["components"].grid.update_docfield_property(
			"fee_structure", "get_query", () => ({
				filters: { academic_year: frm.doc.academic_year, status: "Active" }
			})
		);
	},

	components_add(frm, cdt, cdn) {
		// Auto-set program_level / student_category to All when a row is added
		let row = frappe.get_doc(cdt, cdn);
		if (!row.program_level) {
			frappe.model.set_value(cdt, cdn, "program_level", "All");
		}
		if (!row.student_category) {
			frappe.model.set_value(cdt, cdn, "student_category", "All");
		}
	},
});

// Child table events
frappe.ui.form.on("Fee Notification Component", {
	fee_structure(frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		if (row.fee_structure) {
			// Narrow the row to the students the chosen Fee Structure is for
			frappe.db.get_value(
				"Fee Structure",
				row.fee_structure,
				["program", "year_no", "student_category"],
				(r) => {
					if (!r) return;
					if (r.program) frappe.model.set_value(cdt, cdn, "program", r.program);
					if (r.year_no) frappe.model.set_value(cdt, cdn, "year_no", r.year_no);
					if (r.student_category) frappe.model.set_value(cdt, cdn, "student_category", r.student_category);
				}
			);
		}
	},
});

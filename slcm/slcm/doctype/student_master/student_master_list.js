// Copyright (c) 2025, Nishanth and contributors
// For license information, please see license.txt

frappe.listview_settings["Student Master"] = {
	add_fields: ["registration_status", "status_updated_by", "status_updated_on"],

	onload(listview) {
		$("span.sidebar-toggle-btn").hide();
		$(".col-lg-2.layout-side-section").hide();
		inject_status_css();
		add_listview_status_actions(listview);
		add_listview_status_button(listview);
		add_bulk_delete_button(listview);
		add_bulk_enroll_button(listview);
		add_download_slip_button(listview);
		add_generate_student_id_button(listview);
		add_bulk_section_upload_button(listview);
		style_action_group_button(listview);
		// Ensure status column is visible
		ensure_status_column_visible(listview);
	},

	get_indicator(doc) {
		const status = doc.registration_status || "Selected";

		const status_config = {
			Draft: ["Draft", "grey", "registration_status,=,Draft"],
			Selected: ["Selected", "grey", "registration_status,=,Selected"],
			"Pending REGO": ["Pending REGO", "orange", "registration_status,=,Pending REGO"],
			"Pending FINO": ["Pending FINO", "red", "registration_status,=,Pending FINO"],
			"Pending Registration": [
				"Pending Registration",
				"blue",
				"registration_status,=,Pending Registration",
			],
			"Pending Print & Scan": [
				"Pending Print & Scan",
				"yellow",
				"registration_status,=,Pending Print & Scan",
			],
			"Pending Residences": [
				"Pending Residences",
				"purple",
				"registration_status,=,Pending Residences",
			],
			"Pending IT": ["Pending IT", "pink", "registration_status,=,Pending IT"],
			"Final Verification REGO": [
				"Final Verification REGO",
				"cyan",
				"registration_status,=,Final Verification REGO",
			],
			Completed: ["Completed", "green", "registration_status,=,Completed"],
		};

		if (status_config[status]) {
			return status_config[status];
		}

		return [__(status), "grey", `registration_status,=,${status}`];
	},

	formatters: {
		registration_status(value, field, doc) {
			const status = value || "Selected";
			const status_colors = {
				Selected: "grey",
				"Pending REGO": "orange",
				"Pending FINO": "red",
				"Pending Registration": "blue",
				"Pending Print & Scan": "yellow",
				"Pending Residences": "purple",
				"Pending IT": "pink",
				"Final Verification REGO": "cyan",
				Completed: "green",
			};

			const color = status_colors[status] || "grey";
			return `<span class="indicator-pill ${color}">${status}</span>`;
		},
	},
};

/* --------------------------------------------------
   List View → "Action" dropdown holding all custom buttons
-------------------------------------------------- */
const ACTION_GROUP = __("Action");

function style_action_group_button(listview) {
	listview.page.get_inner_group_button(ACTION_GROUP).children(":not(.dropdown-menu)").css({
		"background-color": "#000",
		color: "#fff",
		"border-color": "#000",
		"box-shadow": "none",
	});
}

/* --------------------------------------------------
   List View → Custom Button in Toolbar
-------------------------------------------------- */
function add_listview_status_button(listview) {
	// Add custom button in toolbar for bulk status update
	listview.page.add_inner_button(
		__("Update Status"),
		function () {
			const selected = listview.get_checked_items();

			if (selected.length === 0) {
				frappe.msgprint({
					title: __("No Selection"),
					message: __("Please select at least one student to update status."),
					indicator: "orange",
					
				});
				
				return;
			}

			show_bulk_status_dialog(listview, selected);
		},
		ACTION_GROUP
	);
}

/* --------------------------------------------------
   List View → Actions → Status (Bulk Update) - Menu Item
-------------------------------------------------- */
function add_listview_status_actions(listview) {
	// Add Status menu to list view actions
	listview.page.add_menu_item(__("Update Status"), function () {
		const selected = listview.get_checked_items();

		if (selected.length === 0) {
			frappe.msgprint({
				title: __("No Selection"),
				message: __("Please select at least one student to update status."),
				indicator: "orange",
			});
			return;
		}

		show_bulk_status_dialog(listview, selected);
	});
	
}

/* --------------------------------------------------
   List View → Bulk Delete (System Manager only)
-------------------------------------------------- */
function add_bulk_delete_button(listview) {
	// Show only for System Manager or Administrator
	if (!frappe.user.has_role("System Manager") && frappe.session.user !== "Administrator") return;

	listview.page.add_inner_button(
		__("Delete"),
		function () {
			const selected = listview.get_checked_items();

			if (!selected.length) {
				frappe.msgprint({
					title: __("No Selection"),
					message: __("Please select at least one student to delete."),
					indicator: "orange",
				});
				return;
			}

			frappe.confirm(
				__("Are you sure you want to delete {0} student(s)?", [selected.length]),
				function () {
					const names = selected.map((row) => row.name);
					frappe.call({
						method: "frappe.desk.reportview.delete_items",
						args: {
							items: names,
							doctype: "Student Master",
						},
						freeze: true,
						freeze_message: __("Deleting records..."),
						callback: function () {
							frappe.show_alert({
								message: __("Deleted {0} student(s)", [names.length]),
								indicator: "green",
							});
							listview.refresh();
						},
						error: function (r) {
							frappe.msgprint({
								title: __("Error"),
								message: r.message || __("Failed to delete records"),
								indicator: "red",
							});
						},
					});
				}
			);
		},
		ACTION_GROUP
	);
}

/* --------------------------------------------------
   List View → Bulk Enroll
-------------------------------------------------- */
function add_bulk_enroll_button(listview) {
	listview.page.add_inner_button(__("Enroll"), function () {
		const selected = listview.get_checked_items();

		if (selected.length === 0) {
			frappe.msgprint({
				title: __("No Selection"),
				message: __("Please select at least one student to enroll."),
				indicator: "orange",
			});
			return;
		}

		frappe.confirm(
			__(
				"Are you sure you want to enroll {0} student(s)? This will create new Enrollment records for eligible students.",
				[selected.length]
			),
			function () {
				const names = selected.map((row) => row.name);

				frappe.call({
					method: "slcm.slcm.doctype.student_master.student_master.bulk_student_enrollment",
					args: {
						students: names,
					},
					freeze: true,
					freeze_message: __("Enrolling students..."),
					callback: function (r) {
						if (r.message) {
							const success_count = r.message.success.length;
							const failure_count = r.message.failed.length;

							let message = `Successfully enrolled: <b>${success_count}</b>`;
							let indicator = "green";

							if (failure_count > 0) {
								indicator = "orange"; // Warning if some failed
								message += `<br>Failed: <b>${failure_count}</b>`;
								message += "<br><br><b>Reasons:</b><ul>";
								r.message.failed.forEach((f) => {
									message += `<li>${f.student}: ${f.reason}</li>`;
								});
								message += "</ul>";

								// Clean up message if too long
								if (r.message.failed.length > 5) {
									message = `Successfully enrolled: <b>${success_count}</b><br>Failed: <b>${failure_count}</b><br>(Check logs for details)`;
								}

								frappe.msgprint({
									title: __("Bulk Enrollment Results"),
									message: message,
									indicator: indicator,
								});
							} else {
								frappe.show_alert({
									message: message,
									indicator: "green",
								});
							}

							listview.refresh();
						}
					},
				});
			}
		);
	}, ACTION_GROUP);
}

const VALID_TRANSITIONS = {
	"Draft":                   ["Selected"],
	"Selected":                ["Pending REGO"],
	"Pending REGO":            ["Pending FINO"],
	"Pending FINO":            ["Pending Registration"],
	"Pending Registration":    ["Pending Print & Scan"],
	"Pending Print & Scan":    ["Pending Residences"],
	"Pending Residences":      ["Pending IT"],
	"Pending IT":              ["Final Verification REGO"],
	"Final Verification REGO": ["Completed"],
	"Completed":               ["Re-Open"],
	"Re-Open":                 ["Pending REGO"],
};

function show_bulk_status_dialog(listview, selected) {
	const is_admin = frappe.user.has_role("System Manager") || frappe.session.user === "Administrator";

	// Collect unique current statuses
	const current_statuses = [...new Set(selected.map(s => s.registration_status || "Selected"))];

	// Determine valid next states: intersection of next states for ALL selected statuses
	// (Admin sees all states; regular users only see commonly-valid next states)
	let statuses;
	if (is_admin) {
		statuses = Object.keys(VALID_TRANSITIONS);
	} else {
		// Find next states valid for every selected student's current status
		const next_sets = current_statuses.map(s => VALID_TRANSITIONS[s] || []);
		if (next_sets.length === 0) {
			statuses = [];
		} else {
			statuses = next_sets.reduce((a, b) => a.filter(s => b.includes(s)));
		}
	}

	if (statuses.length === 0) {
		frappe.msgprint({
			title: __("No Common Next State"),
			message: __("The selected students are in different states with no common valid next state. Please select students in the same status."),
			indicator: "orange",
		});
		return;
	}

	// Get current statuses for selected students
	const status_summary = {};
	selected.forEach((student) => {
		const status = student.registration_status || "Selected";
		status_summary[status] = (status_summary[status] || 0) + 1;
	});

	const status_html = Object.entries(status_summary)
		.map(([status, count]) => `<strong>${status}:</strong> ${count} student(s)`)
		.join("<br>");

	let dialog = new frappe.ui.Dialog({
		title: __("Bulk Update Status"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<div class="alert alert-info">
					<strong>Selected:</strong> ${selected.length} student(s)<br><br>
					<strong>Current Status:</strong><br>${status_html}
				</div>`,
			},
			{
				fieldtype: "Select",
				fieldname: "new_status",
				label: __("New Status"),
				options: statuses.join("\n"),
				reqd: 1,
			},
			{
				fieldtype: "Small Text",
				fieldname: "remarks",
				label: __("Remarks"),
				reqd: 1,
			},
		],
		primary_action_label: __("Update Status"),
		primary_action: function () {
			const values = dialog.get_values();

			if (!values.new_status) {
				frappe.msgprint({
					title: __("Required"),
					message: __("Please select a new status"),
					indicator: "orange",
				});
				return;
			}

			if (!values.remarks || !values.remarks.trim()) {
				frappe.msgprint({
					title: __("Required"),
					message: __("Please enter remarks"),
					indicator: "orange",
				});
				return;
			}

			frappe.confirm(
				__("Update status to <b>{0}</b> for {1} student(s)?", [
					values.new_status,
					selected.length,
				]),
				function () {
					// Yes - Update status
					dialog.hide();

					let success_count = 0;
					let error_count = 0;
					let errors = [];

					// Process each student
					selected.forEach((student, index) => {
						frappe.call({
							method: "slcm.slcm.doctype.student_master.student_master.update_registration_status",
							args: {
								student_id: student.name,
								new_status: values.new_status,
								remarks: values.remarks,
							},
							async: false,
							callback: function (r) {
								if (r.message && r.message.status === "success") {
									success_count++;
								} else {
									error_count++;
									errors.push(
										`${student.name}: ${
											r.message
												? r.message.message || r.message
												: "Unknown error"
										}`
									);
								}

								// Check if all processed
								if (success_count + error_count === selected.length) {
									if (error_count === 0) {
										frappe.show_alert({
											message: __(
												"Status updated successfully for {0} student(s)",
												[success_count]
											),
											indicator: "green",
										});
									} else {
										frappe.msgprint({
											title: __("Update Status - Partial Success"),
											message: __(
												"Successfully updated: {0}<br>Failed: {1}<br><br>Errors:<br>{2}",
												[success_count, error_count, errors.join("<br>")]
											),
											indicator: "orange",
										});
									}
									listview.refresh();
								}
							},
							error: function (r) {
								error_count++;
								errors.push(
									`${student.name}: ${r.message || "Error updating status"}`
								);

								if (success_count + error_count === selected.length) {
									frappe.msgprint({
										title: __("Update Status - Errors"),
										message: __(
											"Successfully updated: {0}<br>Failed: {1}<br><br>Errors:<br>{2}",
											[success_count, error_count, errors.join("<br>")]
										),
										indicator: "red",
									});
									listview.refresh();
								}
							},
						});
					});
				},
				function () {
					// No - Cancel
					dialog.hide();
				}
			);
		},
	});

	dialog.show();
}

/* --------------------------------------------------
   Ensure Status Column is Visible
-------------------------------------------------- */
function ensure_status_column_visible(listview) {
	// Add registration_status to visible columns if not already there
	setTimeout(() => {
		const columns = listview.columns || [];
		const has_status = columns.some((col) => col.fieldname === "registration_status");

		if (!has_status) {
			// Status column will be shown via get_indicator and formatters
			// The field is already set to in_list_view: 1 in JSON
		}
	}, 500);
}

/* --------------------------------------------------
   List View → Download Registration Slip
-------------------------------------------------- */
function add_download_slip_button(listview) {
	listview.page.add_inner_button(__("Download Slip"), function () {
		const selected = listview.get_checked_items();

		if (selected.length === 0) {
			frappe.msgprint({
				title: __("No Selection"),
				message: __("Please select at least one student to download the Registration Slip."),
				indicator: "orange",
			});
			return;
		}

		if (selected.length > 5) {
			frappe.msgprint({
				title: __("Too Many Selected"),
				message: __("Please select a maximum of 5 students at a time to avoid browser popup blocking."),
				indicator: "orange",
			});
			return;
		}

		selected.forEach((student, idx) => {
			setTimeout(() => {
				download_registration_slip(student.name);
			}, idx * 600);
		});
	}, ACTION_GROUP);
}

/* --------------------------------------------------
   Download Registration Slip as named PDF
-------------------------------------------------- */
function download_registration_slip(student_name) {
	const url = frappe.urllib.get_full_url(
		`/api/method/frappe.utils.print_format.download_pdf?doctype=Student+Master&name=${encodeURIComponent(student_name)}&format=Student+Registration+Slip`
	);

	fetch(url, { credentials: "same-origin" })
		.then((res) => {
			if (!res.ok) throw new Error("Failed to generate PDF");
			return res.blob();
		})
		.then((blob) => {
			const a = document.createElement("a");
			a.href = URL.createObjectURL(blob);
			a.download = `Registration_Slip_${student_name}.pdf`;
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(a.href);
		})
		.catch(() => {
			frappe.msgprint({
				title: __("Error"),
				message: __("Could not generate PDF for {0}. Please try again.", [student_name]),
				indicator: "red",
			});
		});
}

/* --------------------------------------------------
   Status Indicator Styling
-------------------------------------------------- */
function inject_status_css() {
	if (document.getElementById("student-status-css")) {
		return;
	}

	const style = document.createElement("style");
	style.id = "student-status-css";
	style.innerHTML = `
		.indicator-pill.grey {
			background-color: #e9ecef !important;
			color: #495057 !important;
			font-weight: 600;
		}
		.indicator-pill.orange {
			background-color: #fff3cd !important;
			color: #856404 !important;
			font-weight: 600;
		}
		.indicator-pill.red {
			background-color: #f8d7da !important;
			color: #721c24 !important;
			font-weight: 600;
		}
		.indicator-pill.blue {
			background-color: #d1ecf1 !important;
			color: #0c5460 !important;
			font-weight: 600;
		}
		.indicator-pill.yellow {
			background-color: #fff3cd !important;
			color: #856404 !important;
			font-weight: 600;
		}
		.indicator-pill.purple {
			background-color: #e2d9f3 !important;
			color: #6f42c1 !important;
			font-weight: 600;
		}
		.indicator-pill.pink {
			background-color: #fce4ec !important;
			color: #c2185b !important;
			font-weight: 600;
		}
		.indicator-pill.cyan {
			background-color: #e0f7fa !important;
			color: #006064 !important;
			font-weight: 600;
		}
		.indicator-pill.green {
			background-color: #d4edda !important;
			color: #155724 !important;
			font-weight: 600;
		}
	`;

	document.head.appendChild(style);
}

/* --------------------------------------------------
   List View → Generate Student ID (Bulk Upload / Auto Generate)
-------------------------------------------------- */
function add_generate_student_id_button(listview) {
	listview.page.add_inner_button(__("Generate Student ID"), function () {
		show_generate_id_chooser(listview);
	}, ACTION_GROUP);
}

function show_generate_id_chooser(listview) {
	const chooser = new frappe.ui.Dialog({
		title: __("Generate Student ID"),
		fields: [
			{
				fieldtype: "HTML",
				options: `
					<div style="display:flex; gap:12px;">
						<button class="btn btn-default" id="gen-id-bulk-upload" style="flex:1; height:76px; text-align:left; padding:10px 14px;">
							<div style="font-weight:600;">${__("Bulk Upload")}</div>
							<div style="font-size:12px; color:#6b7280; white-space:normal;">
								${__("Download a template with existing students, fill in Student IDs, upload back")}
							</div>
						</button>
						<button class="btn btn-default" id="gen-id-auto-generate" style="flex:1; height:76px; text-align:left; padding:10px 14px;">
							<div style="font-weight:600;">${__("Auto Generate")}</div>
							<div style="font-size:12px; color:#6b7280; white-space:normal;">
								${__("Filter by Programme / Academic Year / Term and auto-assign IDs")}
							</div>
						</button>
					</div>
				`,
			},
		],
	});

	chooser.show();
	chooser.$wrapper.find("#gen-id-bulk-upload").on("click", () => {
		chooser.hide();
		show_bulk_upload_dialog(listview);
	});
	chooser.$wrapper.find("#gen-id-auto-generate").on("click", () => {
		chooser.hide();
		show_auto_generate_dialog(listview);
	});
}

function fetch_batch_filter_options(callback) {
	frappe.call({
		method: "slcm.slcm.doctype.student_master.student_master.get_batch_filter_options",
		freeze: true,
		freeze_message: __("Loading Batches..."),
		callback: function (r) {
			const options = r.message || [];
			if (!options.length) {
				frappe.msgprint({
					title: __("No Batches"),
					message: __("No Batch records found to filter by."),
					indicator: "orange",
				});
				return;
			}
			callback(options);
		},
	});
}

function wire_programme_cascade(dialog, options, { includeBlank }) {
	const blank = includeBlank ? [""] : [];
	const programmes = [...new Set(options.map((o) => o.programme_label))];
	dialog.set_df_property("programme", "options", [...blank, ...programmes]);

	dialog.fields_dict.programme.df.change = function () {
		const prog = dialog.get_value("programme");
		const years = [...new Set(
			options.filter((o) => o.programme_label === prog).map((o) => o.academic_year)
		)];
		dialog.set_df_property("academic_year", "options", [...blank, ...years]);
		dialog.set_value("academic_year", "");
		if (dialog.fields_dict.term_name) {
			dialog.set_df_property("term_name", "options", blank);
			dialog.set_value("term_name", "");
		}
	};

	dialog.fields_dict.academic_year.df.change = function () {
		if (!dialog.fields_dict.term_name) return;
		const prog = dialog.get_value("programme");
		const ay = dialog.get_value("academic_year");
		const terms = [...new Set(
			options
				.filter((o) => o.programme_label === prog && o.academic_year === ay)
				.map((o) => o.term_name)
		)];
		dialog.set_df_property("term_name", "options", [...blank, ...terms]);
		dialog.set_value("term_name", "");
	};
}

function resolve_selected_batches(dialog, options) {
	const prog = dialog.get_value("programme");
	const ay = dialog.get_value("academic_year");
	const term = dialog.fields_dict.term_name ? dialog.get_value("term_name") : null;

	if (!prog && !ay && !term) return null; // no filters selected — all students

	return options
		.filter((o) =>
			(!prog || o.programme_label === prog) &&
			(!ay || o.academic_year === ay) &&
			(!term || o.term_name === term)
		)
		.map((o) => o.batch);
}

/* ---------------- Auto Generate ---------------- */

function show_auto_generate_dialog(listview) {
	fetch_batch_filter_options((options) => render_auto_generate_dialog(listview, options));
}

function render_auto_generate_dialog(listview, options) {
	let dialog;
	dialog = new frappe.ui.Dialog({
		title: __("Auto Generate Student IDs"),
		size: "large",
		fields: [
			{ fieldtype: "Select", fieldname: "programme", label: __("Programme"), options: [], reqd: 1 },
			{ fieldtype: "Column Break" },
			{ fieldtype: "Select", fieldname: "academic_year", label: __("Academic Year"), options: [], reqd: 1 },
			{ fieldtype: "Section Break" },
			{ fieldtype: "Button", fieldname: "load_preview", label: __("Show Students") },
			{ fieldtype: "Section Break" },
			{ fieldtype: "HTML", fieldname: "preview_html" },
		],
		primary_action_label: __("Proceed"),
		primary_action() {
			if (!dialog._preview || !dialog._preview.length) {
				frappe.msgprint({
					message: __("Load the student preview first."),
					indicator: "orange",
				});
				return;
			}
			frappe.confirm(
				__(
					"This will (re)assign Student IDs for all {0} student(s) shown, in alphabetical order. " +
					"Any student already having an ID may be renumbered. Continue?",
					[dialog._preview.length]
				),
				() => {
					frappe.call({
						method: "slcm.slcm.doctype.student_master.student_master.apply_student_ids",
						args: { assignments: dialog._preview },
						freeze: true,
						freeze_message: __("Updating Student IDs..."),
						callback: function (r) {
							frappe.show_alert({
								message: __("Updated {0} student(s)", [(r.message || {}).updated || 0]),
								indicator: "green",
							});
							dialog.hide();
							listview.refresh();
						},
					});
				}
			);
		},
	});

	wire_programme_cascade(dialog, options, { includeBlank: false });

	dialog.fields_dict.load_preview.$input.on("click", function () {
		const batches = resolve_selected_batches(dialog, options);
		if (!batches || !batches.length) {
			frappe.msgprint({
				message: __("Select Programme, Academic Year and Term first."),
				indicator: "orange",
			});
			return;
		}

		frappe.call({
			method: "slcm.slcm.doctype.student_master.student_master.preview_student_ids",
			args: { batches },
			freeze: true,
			freeze_message: __("Generating preview..."),
			callback: function (r) {
				const rows = r.message || [];
				dialog._preview = rows;
				render_student_id_preview_table(dialog.fields_dict.preview_html, rows);
			},
		});
	});

	dialog.show();
}

function render_student_id_preview_table(field, rows) {
	if (!rows.length) {
		field.$wrapper.html(
			`<div class="text-muted">${__("No students found in this Batch.")}</div>`
		);
		return;
	}
	let html = `<table class="table table-bordered">
		<thead><tr><th>${__("Student Name")}</th><th>${__("Current ID")}</th><th>${__("Proposed Student ID")}</th></tr></thead>
		<tbody>`;
	rows.forEach((r) => {
		const changed = r.current_id && r.current_id !== r.student_id;
		const current = r.current_id
			? `<span style="${changed ? "text-decoration:line-through;color:#9ca3af;" : ""}">${frappe.utils.escape_html(r.current_id)}</span>`
			: `<span class="text-muted">${__("None")}</span>`;
		html += `<tr><td>${frappe.utils.escape_html(r.student_name)}</td><td>${current}</td><td><b>${frappe.utils.escape_html(r.student_id)}</b></td></tr>`;
	});
	html += "</tbody></table>";
	field.$wrapper.html(html);
}

/* ---------------- Bulk Upload ---------------- */

function show_bulk_upload_dialog(listview) {
	fetch_batch_filter_options((options) => render_bulk_upload_dialog(listview, options));
}

function render_bulk_upload_dialog(listview, options) {
	let dialog;
	dialog = new frappe.ui.Dialog({
		title: __("Bulk Upload Student IDs"),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				options: `<div class="text-muted" style="margin-bottom:8px;">
					${__("Leave the filters blank to include all students, or narrow down to one Batch before downloading the template.")}
				</div>`,
			},
			{ fieldtype: "Select", fieldname: "programme", label: __("Programme"), options: [] },
			{ fieldtype: "Select", fieldname: "academic_year", label: __("Academic Year"), options: [] },
			{ fieldtype: "Column Break" },
			{ fieldtype: "Select", fieldname: "term_name", label: __("Term"), options: [] },
			{ fieldtype: "Button", fieldname: "download_template", label: __("Download Sample Template") },
			{ fieldtype: "Section Break" },
			{ fieldtype: "Attach", fieldname: "filled_file", label: __("Upload Filled Template") },
		],
		primary_action_label: __("Upload"),
		primary_action() {
			const file_url = dialog.get_value("filled_file");
			if (!file_url) {
				frappe.msgprint({
					message: __("Please attach the filled template first."),
					indicator: "orange",
				});
				return;
			}
			frappe.call({
				method: "slcm.slcm.doctype.student_master.student_master.upload_student_ids_bulk",
				args: { file_url },
				freeze: true,
				freeze_message: __("Processing upload..."),
				callback: function (r) {
					const res = r.message || {};
					let msg = __("Updated {0} student(s).", [res.updated || 0]);
					if (res.skipped && res.skipped.length) {
						msg += `<br>${__("Skipped (not found)")}: ${res.skipped.join(", ")}`;
					}
					frappe.msgprint({
						title: __("Upload Complete"),
						message: msg,
						indicator: res.skipped && res.skipped.length ? "orange" : "green",
					});
					dialog.hide();
					listview.refresh();
				},
			});
		},
	});

	wire_programme_cascade(dialog, options, { includeBlank: true });

	dialog.fields_dict.download_template.$input.on("click", function () {
		const batches = resolve_selected_batches(dialog, options);

		frappe.call({
			method: "slcm.slcm.doctype.student_master.student_master.download_student_id_bulk_template",
			args: { batches },
			freeze: true,
			freeze_message: __("Preparing template..."),
			callback: function (r) {
				const res = r.message;
				if (!res) return;
				download_base64_file(res.content, res.filename, res.mime);
			},
		});
	});

	dialog.show();
}

/* ---------------- Bulk Upload Section ---------------- */

function add_bulk_section_upload_button(listview) {
	listview.page.add_inner_button(__("Bulk Upload Section"), function () {
		show_bulk_section_upload_dialog(listview);
	}, ACTION_GROUP);
}

function show_bulk_section_upload_dialog(listview) {
	fetch_batch_filter_options((options) => render_bulk_section_upload_dialog(listview, options));
}

function render_bulk_section_upload_dialog(listview, options) {
	let dialog;
	dialog = new frappe.ui.Dialog({
		title: __("Bulk Upload Section"),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				options: `<div class="text-muted" style="margin-bottom:8px;">
					${__("Filter by Programme / Academic Year (or leave blank for all students) before downloading the template. Fill in the Section column and upload it back.")}
				</div>`,
			},
			{ fieldtype: "Select", fieldname: "programme", label: __("Programme"), options: [] },
			{ fieldtype: "Select", fieldname: "academic_year", label: __("Academic Year"), options: [] },
			{ fieldtype: "Column Break" },
			{ fieldtype: "Button", fieldname: "download_template", label: __("Download Sample Template") },
			{ fieldtype: "Section Break" },
			{ fieldtype: "Attach", fieldname: "filled_file", label: __("Upload Filled Template") },
			{ fieldtype: "Section Break", fieldname: "log_section", label: __("Upload Log") },
			{ fieldtype: "HTML", fieldname: "log_html" },
		],
		primary_action_label: __("Upload"),
		primary_action() {
			const file_url = dialog.get_value("filled_file");
			if (!file_url) {
				frappe.msgprint({
					message: __("Please attach the filled template first."),
					indicator: "orange",
				});
				return;
			}
			frappe.call({
				method: "slcm.slcm.doctype.student_master.student_master.upload_sections_bulk",
				args: { file_url },
				freeze: true,
				freeze_message: __("Processing upload..."),
				callback: function (r) {
					const res = r.message || {};
					render_section_upload_log(dialog.fields_dict.log_html, res.log || []);

					let msg = __("Updated {0} student(s).", [res.updated || 0]);
					if (res.errors) {
						msg += `<br>${__("Errors")}: ${res.errors}`;
					}
					frappe.show_alert({
						message: msg,
						indicator: res.errors ? "orange" : "green",
					});
					listview.refresh();
				},
			});
		},
	});

	wire_programme_cascade(dialog, options, { includeBlank: true });

	dialog.fields_dict.download_template.$input.on("click", function () {
		const batches = resolve_selected_batches(dialog, options);

		frappe.call({
			method: "slcm.slcm.doctype.student_master.student_master.download_section_bulk_template",
			args: { batches },
			freeze: true,
			freeze_message: __("Preparing template..."),
			callback: function (r) {
				const res = r.message;
				if (!res) return;
				download_base64_file(res.content, res.filename, res.mime);
			},
		});
	});

	dialog.show();
}

function render_section_upload_log(field, log_rows) {
	if (!log_rows.length) {
		field.$wrapper.html("");
		return;
	}

	const error_rows = log_rows.filter((r) => r.status === "Error");
	const success_count = log_rows.length - error_rows.length;

	let html = `<div style="margin-bottom:8px;">
		<span class="indicator-pill green">${__("Success")}: ${success_count}</span>
		${error_rows.length ? ` <span class="indicator-pill red">${__("Errors")}: ${error_rows.length}</span>` : ""}
	</div>`;

	html += `<div style="max-height:300px; overflow-y:auto;">
		<table class="table table-bordered">
			<thead><tr>
				<th>${__("Student")}</th>
				<th>${__("Section")}</th>
				<th>${__("Status")}</th>
				<th>${__("Message")}</th>
			</tr></thead>
			<tbody>`;

	log_rows.forEach((r) => {
		const pill = r.status === "Error" ? "red" : "green";
		html += `<tr>
			<td>${frappe.utils.escape_html(r.student_name || r.student)}</td>
			<td>${frappe.utils.escape_html(r.section || "")}</td>
			<td><span class="indicator-pill ${pill}">${r.status}</span></td>
			<td>${frappe.utils.escape_html(r.message || "")}</td>
		</tr>`;
	});

	html += "</tbody></table></div>";
	field.$wrapper.html(html);
}

function download_base64_file(base64_content, filename, mime) {
	const byteChars = atob(base64_content);
	const byteNumbers = new Array(byteChars.length);
	for (let i = 0; i < byteChars.length; i++) {
		byteNumbers[i] = byteChars.charCodeAt(i);
	}
	const byteArray = new Uint8Array(byteNumbers);
	const blob = new Blob([byteArray], { type: mime });
	const a = document.createElement("a");
	a.href = URL.createObjectURL(blob);
	a.download = filename;
	document.body.appendChild(a);
	a.click();
	a.remove();
	URL.revokeObjectURL(a.href);
}

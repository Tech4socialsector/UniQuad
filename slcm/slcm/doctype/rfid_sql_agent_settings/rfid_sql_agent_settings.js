// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

const RSA_API = "slcm.slcm.rfid_sql_agent.";

frappe.ui.form.on("RFID SQL Agent Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.call({
				method: RSA_API + "poller.test_connection",
				freeze: true,
				freeze_message: __("Testing connection..."),
				callback(r) {
					if (!r.message) return;
					frappe.msgprint({
						message: r.message.message,
						indicator: r.message.success ? "green" : "red",
						title: r.message.success ? __("Success") : __("Failed"),
					});
				},
			});
		});

		frm.add_custom_button(__("Run Now"), () => {
			frappe.call({
				method: RSA_API + "poller.poll_now",
				freeze: true,
				freeze_message: __("Polling..."),
				callback(r) {
					if (!r.message) return;
					frappe.msgprint({
						message: r.message.message,
						indicator: r.message.success ? "green" : "red",
						title: r.message.success ? __("Done") : __("Failed"),
					});
					frm.reload_doc();
				},
			});
		});

		frm.add_custom_button(__("Find Name Columns"), () => find_name_columns(frm), __("Student Map Tools"));
		frm.add_custom_button(__("Student Map Log"), () => frappe.set_route("List", "RFID Student Map Log"), __("Student Map Tools"));
		frm.add_custom_button(__("RFID UID Change Log"), () => frappe.set_route("List", "RFID UID Change Log"), __("Student Map Tools"));
		frm.add_custom_button(__("Student Map"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save the settings first so Student Map uses them."));
				return;
			}
			frappe.require("/assets/slcm/js/rfid_student_map.js", () =>
				slcm.rfid_student_map.open({ on_done: () => frm.reload_doc() }));
		}).addClass("btn-primary");
	},
});

// Browse the device database for a table holding card codes + names, preview it, and fill the settings.
function find_name_columns(frm) {
	frappe.call({
		method: RSA_API + "student_map.discover_name_sources",
		freeze: true,
		freeze_message: __("Reading tables from the device database…"),
		callback(r) {
			const res = r.message || {};
			const cands = res.candidates || [];
			if (!cands.length) {
				frappe.msgprint({
					title: __("No table found"),
					indicator: "orange",
					message: __("None of the {0} tables in the device database has both a code column and a name column. Type the table and columns in the Student Map tab instead.", [res.table_count || 0]),
				});
				return;
			}
			const by_table = {};
			cands.forEach((c) => (by_table[c.table] = c));

			const d = new frappe.ui.Dialog({
				title: __("Find where names are stored"),
				size: "large",
				fields: [
					{ fieldname: "table", fieldtype: "Select", label: __("Table"), reqd: 1,
					  options: cands.map((c) => c.table),
					  default: frm.doc.map_source_table && by_table[frm.doc.map_source_table] ? frm.doc.map_source_table : cands[0].table,
					  description: __("Best guesses first, out of {0} tables.", [res.table_count]),
					  onchange: () => fill_columns() },
					{ fieldname: "code_column", fieldtype: "Select", label: __("Card code column"), reqd: 1 },
					{ fieldname: "cb", fieldtype: "Column Break" },
					{ fieldname: "name_columns", fieldtype: "MultiCheck", label: __("Name column(s)"), columns: 2, options: [] },
					{ fieldname: "sb", fieldtype: "Section Break" },
					{ fieldname: "sample", fieldtype: "HTML" },
				],
				primary_action_label: __("Use these columns"),
				primary_action(v) {
					const names = d.fields_dict.name_columns.get_checked_options();
					if (!names.length) {
						frappe.msgprint(__("Tick at least one name column."));
						return;
					}
					frm.set_value("map_source_table", v.table);
					frm.set_value("map_code_column", v.code_column);
					frm.set_value("map_name_columns", names.join(","));
					d.hide();
					frm.save().then(() => frm.scroll_to_field("map_source_table"));
				},
				secondary_action_label: __("Preview 10 rows"),
				secondary_action: () => preview(),
			});

			function fill_columns() {
				const c = by_table[d.get_value("table")];
				if (!c) return;
				const code = d.fields_dict.code_column;
				code.df.options = c.code_columns;
				code.refresh();
				const keep = frm.doc.map_code_column;
				code.set_value(c.code_columns.includes(keep) ? keep : c.code_columns.find((x) => x.toLowerCase() === "emp_code") || c.code_columns[0]);

				const chosen = (frm.doc.map_name_columns || "").split(",").map((x) => x.trim());
				const nm = d.fields_dict.name_columns;
				nm.df.options = c.name_columns.map((col) => ({
					label: col, value: col,
					checked: chosen.includes(col) || (!chosen.some((x) => c.name_columns.includes(x)) && ["first_name", "last_name"].includes(col.toLowerCase())),
				}));
				nm.refresh();
				d.fields_dict.sample.$wrapper.html(`<div class="text-muted small">${__("Click Preview 10 rows to check the names look right.")}</div>`);
			}

			function preview() {
				const names = d.fields_dict.name_columns.get_checked_options();
				frappe.call({
					method: RSA_API + "student_map.sample_device_records",
					args: { table: d.get_value("table"), code_column: d.get_value("code_column"), name_columns: names.join(",") },
					freeze: true,
					callback(r) {
						const rows = r.message || [];
						const esc = (s) => frappe.utils.escape_html(String(s == null ? "" : s));
						d.fields_dict.sample.$wrapper.html(rows.length
							? `<table class="table table-bordered table-sm" style="margin:0">
								<thead><tr><th>${__("Card code")}</th><th>${__("Name")}</th></tr></thead>
								<tbody>${rows.map((x) => `<tr><td><code>${esc(x.code)}</code></td><td>${esc(x.name) || "—"}</td></tr>`).join("")}</tbody></table>`
							: `<div class="text-muted">${__("The table returned no rows.")}</div>`);
					},
				});
			}

			d.show();
			fill_columns();
		},
	});
}

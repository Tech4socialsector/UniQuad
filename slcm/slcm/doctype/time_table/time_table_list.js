frappe.listview_settings["Time Table"] = {
	add_fields: ["session_status"],
	get_indicator(doc) {
		const colors = { Scheduled: "blue", Completed: "green", Cancelled: "red", Swapped: "purple" };
		const status = doc.session_status || "Scheduled";
		return [__(status), colors[status] || "gray", `session_status,=,${status}`];
	},
	onload(listview) {
		setup_export_defaults();

		// One dark dropdown for all Time Table tools. Not called "Actions" so it
		// can't be mistaken for Frappe's bulk Actions menu shown on row selection.
		const group = __("Time Table Actions");
		listview.page.add_inner_button(
			__("Update Venue / Time"),
			() => {
				const selected = listview.get_checked_items();
				if (selected.length) {
					show_bulk_venue_time_dialog(listview, selected);
				} else {
					show_lookup_venue_time_dialog(listview);
				}
			},
			group
		);
		listview.page.add_inner_button(
			__("Time Table Report"),
			() => frappe.set_route("query-report", "Time Table Report", get_report_route_options(listview)),
			group
		);
		// Ticked sessions (any classes), or with nothing ticked, chosen classes and dates
		listview.page.add_inner_button(
			__("RFID Swipe Report"),
			() => frappe.require("/assets/slcm/js/rfid_swipe_report.js", () => slcm.rfid_swipe_report.open_list(listview)),
			group
		);
		listview.page.get_inner_group_button(group).addClass("tt-actions-dark");
		add_dark_actions_style();
	},
};

function add_dark_actions_style() {
	if (document.getElementById("tt-actions-dark-style")) return;
	$(`<style id="tt-actions-dark-style">
		.tt-actions-dark > .btn,
		.tt-actions-dark > .btn:hover,
		.tt-actions-dark > .btn:focus,
		.tt-actions-dark.show > .btn {
			background-color: #171717;
			border-color: #171717;
			color: #fff;
			box-shadow: none;
			--icon-stroke: #fff;
		}
		.tt-actions-dark > .btn:hover { background-color: #383838; border-color: #383838; }
	</style>`).appendTo("head");
}

/* --------------------------------------------------------------------
   Time Table Report opens with the filters currently applied on the list.
   Every report filter is sent (blank when unused) so values left over from
   an earlier visit to the report don't silently narrow the result.
-------------------------------------------------------------------- */
const REPORT_EQUAL_FILTERS = [
	"class_name",
	"academic_year",
	"academic_term",
	"programme",
	"course",
	"instructor",
	"section",
	"based_on",
	"session_status",
];

function get_report_route_options(listview) {
	const options = { time_table: "", from_date: "", to_date: "", is_cancelled: 0 };
	REPORT_EQUAL_FILTERS.forEach((f) => (options[f] = ""));

	(listview.get_filters_for_args() || []).forEach(([doctype, field, op, value]) => {
		if (doctype !== "Time Table" || value === undefined || value === null || value === "") return;
		op = (op || "").toLowerCase();

		if (field === "name" && (op === "=" || op === "like")) {
			options.time_table = String(value).replace(/%/g, "");
		} else if (REPORT_EQUAL_FILTERS.includes(field) && op === "=") {
			options[field] = value;
		} else if (field === "is_cancelled" && op === "=") {
			options.is_cancelled = cint(value);
		} else if (field === "schedule_date") {
			if (op === "=") {
				options.from_date = options.to_date = value;
			} else if (op === "between" && Array.isArray(value)) {
				[options.from_date, options.to_date] = value;
			} else if (op === ">=" || op === ">") {
				options.from_date = value;
			} else if (op === "<=" || op === "<") {
				options.to_date = value;
			}
		}
	});
	return options;
}

/* --------------------------------------------------------------------
   Actions > Export: pre-select the columns people actually want (faculty
   name, course, section) and leave out the ID / faculty ID columns.
-------------------------------------------------------------------- */
const EXPORT_DEFAULT_ON = ["instructor_name", "course", "section"];
const EXPORT_DEFAULT_OFF = ["name", "instructor"];

function setup_export_defaults() {
	const BulkOperations = frappe.ui.BulkOperations;
	if (!BulkOperations || BulkOperations.prototype.__tt_export_patched) return;
	BulkOperations.prototype.__tt_export_patched = true;

	const original_export = BulkOperations.prototype.export;
	BulkOperations.prototype.export = function (doctype, docnames) {
		if (doctype !== "Time Table") return original_export.call(this, doctype, docnames);

		frappe.require("data_import_tools.bundle.js", () => {
			const DataExporter = frappe.data_import.DataExporter;
			if (!DataExporter.prototype.__tt_patched) {
				DataExporter.prototype.__tt_patched = true;
				const original_show = DataExporter.prototype.setup_on_page_show;
				DataExporter.prototype.setup_on_page_show = function () {
					original_show.call(this);
					if (this.doctype !== "Time Table") return;

					const $parent = this.dialog.get_field("Time Table").$wrapper;
					const toggle = (fieldnames, checked) =>
						fieldnames.forEach((fieldname) =>
							$parent
								.find(`:checkbox[data-unit="${fieldname}"]`)
								.prop("checked", checked)
								.trigger("change")
						);
					toggle(EXPORT_DEFAULT_ON, true);
					toggle(EXPORT_DEFAULT_OFF, false);
				};
			}
			original_export.call(this, doctype, docnames);
		});
	};
}

/* --------------------------------------------------------------------
   Path 1: rows already checked in the list - update exactly those rows.
-------------------------------------------------------------------- */
function show_bulk_venue_time_dialog(listview, selected) {
	const names = selected.map((d) => d.name);

	const dialog = new frappe.ui.Dialog({
		title: __("Update Venue / Time for {0} Selected Occurrence(s)", [names.length]),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p>${__(
					"This updates exactly the {0} row(s) you selected in the list. Any row that conflicts with an existing booking will block the whole update - nothing is saved until every selected row is conflict-free."
				).replace("{0}", `<b>${names.length}</b>`)}</p>`,
			},
			{
				fieldname: "venue",
				fieldtype: "Link",
				options: "Venue Master",
				label: __("New Venue"),
			},
			{
				fieldname: "from_time",
				fieldtype: "Time",
				label: __("New From Time"),
			},
			{
				fieldname: "to_time",
				fieldtype: "Time",
				label: __("New To Time"),
			},
		],
		primary_action_label: __("Apply"),
		primary_action: function (values) {
			const updates = {};
			if (values.venue) updates.venue = values.venue;
			if (values.from_time) updates.from_time = values.from_time;
			if (values.to_time) updates.to_time = values.to_time;

			if (!Object.keys(updates).length) {
				frappe.msgprint(__("Please provide at least one field to update."));
				return;
			}

			frappe.call({
				method: "slcm.slcm.doctype.time_table.time_table.bulk_update_selected_occurrences",
				args: {
					names: names,
					updates: updates,
				},
				freeze: true,
				freeze_message: __("Checking for conflicts and updating..."),
				callback: function (res) {
					if (res.message) {
						dialog.hide();
						let message = __("Updated {0} occurrence(s)", [res.message.updated_count]);
						if (res.message.skipped_count) {
							message += " " + __("({0} selected row(s) were skipped - cancelled or no longer exist)", [
								res.message.skipped_count,
							]);
						}
						frappe.show_alert(
							{
								message: message,
								indicator: res.message.skipped_count ? "orange" : "green",
							},
							7
						);
						listview.refresh();
					}
				},
			});
		},
	});

	dialog.show();
}

/* --------------------------------------------------------------------
   Path 2: nothing checked in the list - browse every Time Table session
   (Programme/Section/Date optionally narrow it live), tick any number of
   rows with checkboxes, then apply one venue/time change to all of them.
-------------------------------------------------------------------- */
function show_lookup_venue_time_dialog(listview) {
	const dialog = new frappe.ui.Dialog({
		title: __("Find & Update Class Venue / Time"),
		size: "large",
		fields: [
			{
				fieldname: "programme",
				fieldtype: "Link",
				options: "Programme",
				label: __("Programme"),
				onchange: () => reload_sessions(dialog),
			},
			{
				fieldname: "section",
				fieldtype: "Link",
				options: "Section",
				label: __("Section"),
				onchange: () => reload_sessions(dialog),
			},
			{
				fieldname: "schedule_date",
				fieldtype: "Date",
				label: __("Date"),
				onchange: () => reload_sessions(dialog),
			},
			{ fieldtype: "Section Break" },
			{ fieldname: "sessions_html", fieldtype: "HTML" },
			{ fieldtype: "Section Break", fieldname: "selected_section" },
			{ fieldname: "selected_html", fieldtype: "HTML" },
			{
				fieldname: "venue",
				fieldtype: "Link",
				options: "Venue Master",
				label: __("New Venue"),
			},
			{
				fieldname: "new_schedule_date",
				fieldtype: "Date",
				label: __("New Date"),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "from_time",
				fieldtype: "Time",
				label: __("New From Time"),
			},
			{
				fieldname: "to_time",
				fieldtype: "Time",
				label: __("New To Time"),
			},
		],
		primary_action_label: __("Apply"),
		primary_action: function (values) {
			const names = Array.from(dialog._selected_sessions || []);
			if (!names.length) {
				frappe.msgprint(__("Please select at least one session from the list first."));
				return;
			}

			const updates = {};
			if (values.venue) updates.venue = values.venue;
			if (values.new_schedule_date) updates.schedule_date = values.new_schedule_date;
			if (values.from_time) updates.from_time = values.from_time;
			if (values.to_time) updates.to_time = values.to_time;

			if (!Object.keys(updates).length) {
				frappe.msgprint(__("Please provide at least one field to update."));
				return;
			}

			frappe.call({
				method: "slcm.slcm.doctype.time_table.time_table.bulk_update_selected_occurrences",
				args: {
					names: names,
					updates: updates,
				},
				freeze: true,
				freeze_message: __("Checking for conflicts and updating..."),
				callback: function (res) {
					if (res.message) {
						dialog.hide();
						let message = __("Updated {0} occurrence(s)", [res.message.updated_count]);
						if (res.message.skipped_count) {
							message += " " + __("({0} selected row(s) were skipped - cancelled or no longer exist)", [
								res.message.skipped_count,
							]);
						}
						frappe.show_alert(
							{
								message: message,
								indicator: res.message.skipped_count ? "orange" : "green",
							},
							7
						);
						listview.refresh();
					}
				},
			});
		},
	});

	dialog._selected_sessions = new Set();

	// Apply is disabled until at least one row is checked.
	dialog.disable_primary_action();

	dialog.$wrapper.on("change", ".tt-session-checkbox", function () {
		const session_name = $(this).attr("data-session");
		if (this.checked) {
			dialog._selected_sessions.add(session_name);
		} else {
			dialog._selected_sessions.delete(session_name);
		}
		sync_select_all_checkbox(dialog);
		render_selection_summary(dialog);
	});

	dialog.$wrapper.on("change", ".tt-select-all-checkbox", function () {
		const rows = Object.keys(dialog._sessions_by_name || {});
		if (this.checked) {
			rows.forEach((n) => dialog._selected_sessions.add(n));
		} else {
			dialog._selected_sessions.clear();
		}
		dialog.$wrapper.find(".tt-session-checkbox").prop("checked", this.checked);
		render_selection_summary(dialog);
	});

	// Clicking anywhere else on the row toggles its checkbox too, so users
	// don't have to hit the tiny checkbox target precisely.
	dialog.$wrapper.on("click", ".tt-session-row", function (e) {
		if (e.target.classList.contains("tt-session-checkbox")) return;
		const checkbox = $(this).find(".tt-session-checkbox").get(0);
		if (checkbox) {
			checkbox.checked = !checkbox.checked;
			$(checkbox).trigger("change");
		}
	});

	dialog.show();

	// Show every session by default (most recent first, capped server-side);
	// the three filter fields above narrow this list live as they're set.
	reload_sessions(dialog);
}

function reload_sessions(dialog) {
	const values = dialog.get_values(true) || {};

	frappe.call({
		method: "slcm.slcm.doctype.time_table.time_table.find_sessions",
		args: {
			programme: values.programme || null,
			section: values.section || null,
			schedule_date: values.schedule_date || null,
		},
		freeze: true,
		callback: function (r) {
			const sessions = (r.message && r.message.sessions) || [];
			dialog._sessions_by_name = {};
			sessions.forEach((s) => (dialog._sessions_by_name[s.name] = s));

			// A re-filter may drop rows that were checked - keep only
			// selections that are still visible in the new list.
			dialog._selected_sessions = new Set(
				Array.from(dialog._selected_sessions || []).filter((n) => dialog._sessions_by_name[n])
			);

			render_sessions_table(dialog, sessions);
			render_selection_summary(dialog);
		},
	});
}

function render_sessions_table(dialog, sessions) {
	if (!sessions.length) {
		dialog.set_df_property(
			"sessions_html",
			"options",
			`<p style="color:var(--text-muted);">${__("No Time Table sessions match these filters.")}</p>`
		);
		return;
	}

	const selected = dialog._selected_sessions || new Set();
	const rows = sessions
		.map((s) => {
			const checked = selected.has(s.name) ? "checked" : "";
			return `<tr class="tt-session-row">
				<td><input type="checkbox" class="tt-session-checkbox" data-session="${frappe.utils.escape_html(
					s.name
				)}" ${checked}></td>
				<td>${frappe.utils.escape_html(s.name)}</td>
				<td>${frappe.utils.escape_html(s.schedule_date || "-")}</td>
				<td>${format_time(s.from_time)} - ${format_time(s.to_time)}</td>
				<td>${frappe.utils.escape_html(s.programme || "-")}</td>
				<td>${frappe.utils.escape_html(s.section || "-")}</td>
				<td>${frappe.utils.escape_html(s.course || "-")}</td>
				<td>${frappe.utils.escape_html(s.venue || "-")}</td>
			</tr>`;
		})
		.join("");

	const all_checked = sessions.every((s) => selected.has(s.name));

	dialog.set_df_property(
		"sessions_html",
		"options",
		`<div style="max-height:280px;overflow-y:auto;">
			<table class="table table-bordered table-hover" style="margin-bottom:0;">
				<thead>
					<tr>
						<th><input type="checkbox" class="tt-select-all-checkbox" ${all_checked ? "checked" : ""}></th>
						<th>${__("ID")}</th>
						<th>${__("Date")}</th>
						<th>${__("Time")}</th>
						<th>${__("Programme")}</th>
						<th>${__("Section")}</th>
						<th>${__("Course")}</th>
						<th>${__("Venue")}</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		</div>
		<p style="color:var(--text-muted);margin-top:6px;">${__("Tick one or more sessions (or use the header checkbox to select all), then set the new venue/date/time below and click Apply.")}</p>`
	);
}

function sync_select_all_checkbox(dialog) {
	const rows = Object.keys(dialog._sessions_by_name || {});
	const all_checked = rows.length > 0 && rows.every((n) => dialog._selected_sessions.has(n));
	dialog.$wrapper.find(".tt-select-all-checkbox").prop("checked", all_checked);
}

function render_selection_summary(dialog) {
	const names = Array.from(dialog._selected_sessions || []);

	if (!names.length) {
		dialog.set_df_property(
			"selected_html",
			"options",
			`<p style="color:var(--text-muted);">${__("No sessions selected yet.")}</p>`
		);
		dialog.disable_primary_action();
		return;
	}

	dialog.set_df_property(
		"selected_html",
		"options",
		`<p><b>${__("{0} session(s) selected", [names.length])}:</b> ${names
			.map((n) => frappe.utils.escape_html(n))
			.join(", ")}</p>
		<p style="color:var(--text-muted);">${__("Loading student roster...")}</p>`
	);
	dialog.enable_primary_action();

	// Roster is shown for confirmation only - it has no effect on what gets
	// saved. Union the roster across every selected session's class.
	frappe.call({
		method: "slcm.slcm.doctype.time_table.time_table.get_sessions_roster",
		args: { time_table_names: names },
		callback: function (r) {
			// Bail if the selection changed while this was loading.
			const current = Array.from(dialog._selected_sessions || []);
			if (current.length !== names.length || !current.every((n) => names.includes(n))) return;

			const students = (r.message && r.message.students) || [];
			const roster_html = students.length
				? `<ul style="max-height:120px;overflow-y:auto;">${students
						.map((st) => `<li>${frappe.utils.escape_html(st.student_name || st.student)}</li>`)
						.join("")}</ul>`
				: `<p style="color:var(--text-muted);">${__("No enrolled students found for the selected class(es).")}</p>`;

			dialog.set_df_property(
				"selected_html",
				"options",
				`<p><b>${__("{0} session(s) selected", [names.length])}:</b> ${names
					.map((n) => frappe.utils.escape_html(n))
					.join(", ")}</p>
				<h6 style="margin-top:6px;">${__("Students ({0})", [students.length])}</h6>
				${roster_html}`
			);
		},
	});
}

function format_time(t) {
	return t ? moment(t, "HH:mm:ss").format("hh:mm A") : "-";
}

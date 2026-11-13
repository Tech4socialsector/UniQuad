// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

// RFID Swipe Report: the class students' RFID swipes around one session (time_table) or every session of
// the class in a date range, as Excel or CSV. Opened from the class Time Table pop-up (Classes form) and
// from a Time Table record. Server: slcm.slcm.doctype.classes.class_swipe_report.export_class_swipes

frappe.provide("slcm.rfid_swipe_report");

slcm.rfid_swipe_report.download = function (content, filename, mime) {
	const bytes = Uint8Array.from(atob(content), (c) => c.charCodeAt(0));
	const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
	const a = Object.assign(document.createElement("a"), { href: url, download: filename });
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
};

// open(class_name, { time_table, label })        one session
// open(class_name, { from_date, to_date })       every session in the dates (editable in the dialog)
slcm.rfid_swipe_report.open = function (class_name, { time_table, label, from_date, to_date } = {}) {
	const range = !time_table;
	const fields = [
		{ fieldtype: "HTML", fieldname: "intro", options: `<p class="text-muted small" style="margin:0">${range
			? __("Each student's first swipe time in every session of these dates.")
			: __("Each student's swipes for {0}.", [frappe.utils.escape_html(label || "")])}</p>` },
		{ fieldtype: "Section Break", fieldname: "sb_intro" },
	];
	if (range) {
		fields.push(
			{ fieldtype: "Date", fieldname: "from_date", label: __("From Date"), reqd: 1, default: from_date },
			{ fieldtype: "Column Break", fieldname: "cb_dates" },
			{ fieldtype: "Date", fieldname: "to_date", label: __("To Date"), reqd: 1, default: to_date },
			{ fieldtype: "Section Break", fieldname: "sb_window" },
		);
	}
	fields.push(
		{ fieldtype: "Int", fieldname: "before", label: __("Minutes Before Start"), default: 20, reqd: 1 },
		{ fieldtype: "Column Break", fieldname: "cb_window" },
		{ fieldtype: "Int", fieldname: "after", label: __("Minutes After End"), default: 20, reqd: 1 },
		{ fieldtype: "Section Break", fieldname: "sb_format" },
		{ fieldtype: "Select", fieldname: "file_format", label: __("Format"), reqd: 1, default: "xlsx",
		  options: [{ value: "xlsx", label: __("Excel") }, { value: "csv", label: __("CSV") }] },
	);
	const d = new frappe.ui.Dialog({
		title: range ? __("RFID Swipe Report: Date Range") : __("RFID Swipe Report: This Session"),
		fields,
		primary_action_label: __("Download"),
		primary_action(v) {
			const minutes_ok = (m) => Number.isInteger(m) && m >= 0 && m <= 120;
			if (!minutes_ok(v.before) || !minutes_ok(v.after)) {
				frappe.msgprint(__("Minutes before / after must be between 0 and 120."));
				return;
			}
			if (range && v.from_date > v.to_date) {
				frappe.msgprint(__("From Date cannot be after To Date."));
				return;
			}
			frappe.call({
				method: "slcm.slcm.doctype.classes.class_swipe_report.export_class_swipes",
				args: { class_name, time_table: time_table || "", from_date: v.from_date || "", to_date: v.to_date || "",
					before: v.before, after: v.after, file_format: v.file_format },
				freeze: true,
				freeze_message: __("Preparing the RFID swipe report..."),
			}).then((r) => {
				const m = r && r.message;
				if (!m) return;
				slcm.rfid_swipe_report.download(m.content, m.filename, m.mime);
				d.hide();
			});
		},
	});
	d.show();
};

// Time Table list: the ticked sessions (any classes), or, with nothing ticked, every session of the chosen
// classes in a date range. One row per student per session.
slcm.rfid_swipe_report.open_list = function (listview) {
	const ticked = (listview.get_checked_items() || []).map((r) => r.name);
	const pick = !ticked.length;
	const fields = [
		{ fieldtype: "HTML", fieldname: "intro", options: `<p class="text-muted small" style="margin:0">${pick
			? __("No session is ticked: choose the classes and dates.")
			: __("Each student's swipes for the {0} ticked session(s).", [ticked.length])}</p>` },
		{ fieldtype: "Section Break", fieldname: "sb_intro" },
	];
	if (pick) {
		fields.push(
			{ fieldtype: "MultiSelectList", fieldname: "classes", label: __("Classes"), reqd: 1,
			  get_data: (txt) => frappe.db.get_link_options("Classes", txt) },
			{ fieldtype: "Section Break", fieldname: "sb_dates" },
			{ fieldtype: "Date", fieldname: "from_date", label: __("From Date"), reqd: 1, default: frappe.datetime.month_start() },
			{ fieldtype: "Column Break", fieldname: "cb_dates" },
			{ fieldtype: "Date", fieldname: "to_date", label: __("To Date"), reqd: 1, default: frappe.datetime.month_end() },
			{ fieldtype: "Section Break", fieldname: "sb_window" },
		);
	}
	fields.push(
		{ fieldtype: "Int", fieldname: "before", label: __("Minutes Before Start"), default: 20, reqd: 1 },
		{ fieldtype: "Column Break", fieldname: "cb_window" },
		{ fieldtype: "Int", fieldname: "after", label: __("Minutes After End"), default: 20, reqd: 1 },
		{ fieldtype: "Section Break", fieldname: "sb_format" },
		{ fieldtype: "Select", fieldname: "file_format", label: __("Format"), reqd: 1, default: "xlsx",
		  options: [{ value: "xlsx", label: __("Excel") }, { value: "csv", label: __("CSV") }] },
	);
	const d = new frappe.ui.Dialog({
		title: pick ? __("RFID Swipe Report: Classes") : __("RFID Swipe Report: Selected Sessions"),
		fields,
		primary_action_label: __("Download"),
		primary_action(v) {
			const minutes_ok = (m) => Number.isInteger(m) && m >= 0 && m <= 120;
			if (!minutes_ok(v.before) || !minutes_ok(v.after)) {
				frappe.msgprint(__("Minutes before / after must be between 0 and 120."));
				return;
			}
			const classes = pick ? (d.fields_dict.classes.get_value() || []).filter(Boolean) : [];
			if (pick && !classes.length) {
				frappe.msgprint(__("Select at least one Class."));
				return;
			}
			if (pick && v.from_date > v.to_date) {
				frappe.msgprint(__("From Date cannot be after To Date."));
				return;
			}
			frappe.call({
				method: "slcm.slcm.doctype.classes.class_swipe_report.export_session_swipes",
				args: pick
					? { classes, from_date: v.from_date, to_date: v.to_date, before: v.before, after: v.after, file_format: v.file_format }
					: { time_tables: ticked, before: v.before, after: v.after, file_format: v.file_format },
				freeze: true,
				freeze_message: __("Preparing the RFID swipe report..."),
			}).then((r) => {
				const m = r && r.message;
				if (!m) return;
				slcm.rfid_swipe_report.download(m.content, m.filename, m.mime);
				d.hide();
			});
		},
	});
	d.show();
};

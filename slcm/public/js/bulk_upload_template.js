// Bulk-upload templates for Fee Concession, Fee Payment and Fee Demand (server: slcm.slcm.fee.bulk_upload).
// Loaded on those three list views and on the Data Import form (see hooks.py).
//   Fee Concession / Fee Payment — one row per open due, pre-filled; only the yellow columns are filled in.
//   Fee Demand — blank creation sheet (Voucher No. is assigned by the system) + a Students reference sheet.
// A filled sheet imports through Data Import → Insert New Records without column mapping.

(function () {
	const API = "slcm.slcm.fee.bulk_upload.";
	const TEMPLATES = {
		"Fee Concession": {
			info: __(
				"The sheet lists open dues for all students (not settled, with a pending amount, and no approved concession yet). " +
					"Fill only the yellow columns — Concession Type, Waiver Value, Date of concession and Reason."
			),
			filters: ["academic_year", "programme", "fee_component"],
			dates: true,
		},
		"Fee Payment": {
			info: __(
				"The sheet lists open dues for all students (not settled, with a pending amount). Fill only the yellow columns — " +
					"Payment Amount, Payment Date, Settlement Date, Payment Mode, Reference Number, University bank account and Remarks. " +
					"Tick “Submit After Import” in Data Import to post the payments and generate receipts."
			),
			filters: ["academic_year", "programme", "fee_component"],
			dates: true,
		},
		"Fee Demand": {
			info: __(
				"A blank sheet for creating fee demands — one row per demand. Voucher No. is assigned by the system, and " +
					"Student Email / Name, Net Payable and Status are filled automatically. The “Students” sheet lists every " +
					"Student ID with its Registration Id; the filters below only narrow that list."
			),
			filters: ["academic_year", "programme"],
		},
	};
	const FILTER_LABELS = {
		academic_year: __("Academic Year"),
		programme: __("Programme"),
		fee_component: __("Fee Component"),
	};

	window.slcm_download_bulk_template = async function (doctype) {
		const cfg = TEMPLATES[doctype];
		if (!cfg) return;
		// Only values that exist (with counts) are offered; an empty filter means "all".
		const opts = (await frappe.call({ method: API + "get_filter_options", args: { doctype } })).message || {};
		const count_label = doctype === "Fee Demand" ? __("{0} student(s)") : __("{0} open due(s)");
		const multi = (fieldname) => ({
			fieldtype: "MultiSelectList",
			fieldname,
			label: FILTER_LABELS[fieldname],
			options: (opts[fieldname] || []).map((r) => ({ value: r.value, label: r.value, description: count_label.replace("{0}", r.n) })),
			description: __("Leave empty for all"),
		});
		const half = Math.ceil(cfg.filters.length / 2);
		const dialog = new frappe.ui.Dialog({
			title: __("Download {0} Bulk Upload Template", [__(doctype)]),
			fields: [
				{ fieldtype: "HTML", fieldname: "info", options: `<p class="text-muted small">${cfg.info}</p>` },
				...cfg.filters.slice(0, half).map(multi),
				{ fieldtype: "Column Break" },
				...cfg.filters.slice(half).map(multi),
				...(cfg.dates
					? [
							{ fieldtype: "Section Break", label: __("Date Range") },
							{
								fieldtype: "Select",
								fieldname: "date_based_on",
								label: __("Date Based On"),
								options: ["Due Date", "Date of creation"],
								default: "Due Date",
							},
							{ fieldtype: "Column Break" },
							{ fieldtype: "Date", fieldname: "from_date", label: __("From Date") },
							{ fieldtype: "Column Break" },
							{ fieldtype: "Date", fieldname: "to_date", label: __("To Date") },
							{ fieldtype: "Section Break" },
					  ]
					: []),
				{
					fieldtype: "Select",
					fieldname: "file_type",
					label: __("File Type"),
					options: ["Excel", "CSV"],
					default: "Excel",
					description: __("Excel keeps the highlighted columns and the dropdowns."),
				},
			],
			primary_action_label: __("Download"),
			primary_action(values) {
				if (values.from_date && values.to_date && values.from_date > values.to_date) {
					return frappe.msgprint(__("From Date cannot be after To Date."));
				}
				const args = { doctype, file_type: values.file_type || "Excel" };
				if (cfg.dates) {
					if (values.from_date) args.from_date = values.from_date;
					if (values.to_date) args.to_date = values.to_date;
					args.date_based_on = values.date_based_on || "Due Date";
				}
				cfg.filters.forEach((f) => {
					if ((values[f] || []).length) args[f] = JSON.stringify(values[f]);
				});
				open_url_post("/api/method/" + API + "download_template", args);
				dialog.hide();
			},
		});
		dialog.show();
	};
	// kept for callers of the earlier concession-only helper
	window.slcm_download_concession_template = () => window.slcm_download_bulk_template("Fee Concession");

	// List buttons — added on top of each doctype's own list settings (their onload still runs first)
	Object.keys(TEMPLATES).forEach((doctype) => {
		const settings = (frappe.listview_settings[doctype] = frappe.listview_settings[doctype] || {});
		if (settings.__slcm_bulk_template) return;
		settings.__slcm_bulk_template = true;
		const previous = settings.onload;
		settings.onload = function (listview) {
			if (previous) previous.call(this, listview);
			if (!frappe.model.can_create(doctype)) return;
			listview.page.add_inner_button(__("Download Bulk Upload Template"), () => window.slcm_download_bulk_template(doctype));
			listview.page.add_inner_button(__("Upload Filled Template"), () =>
				frappe.new_doc("Data Import", { reference_doctype: doctype, import_type: "Insert New Records" })
			);
		};
	});

	// Data Import → "Download Template" gives these sheets for the three doctypes (Insert New Records).
	const handlers = frappe.ui.form.handlers && frappe.ui.form.handlers["Data Import"];
	if (handlers && handlers.download_template && !handlers.__slcm_bulk_template) {
		handlers.__slcm_bulk_template = true;
		const original = handlers.download_template.slice();
		handlers.download_template = [
			function (frm) {
				if (TEMPLATES[frm.doc.reference_doctype] && frm.doc.import_type !== "Update Existing Records") {
					return window.slcm_download_bulk_template(frm.doc.reference_doctype);
				}
				original.forEach((fn) => fn(frm));
			},
		];
	}
})();

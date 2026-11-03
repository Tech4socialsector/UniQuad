// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.listview_settings["Classes"] = {
	onload(listview) {
		if (frappe.model.can_get_report("Classes")) {
			listview.page.add_inner_button(__("Student Changes Report"), () =>
				frappe.set_route("query-report", "Class Student Changes"));
		}
	},
};

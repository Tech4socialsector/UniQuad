// Copyright (c) 2026, Nishanth and contributors
frappe.listview_settings["RFID Student Map Log"] = {
	add_fields: ["status", "mapped", "not_matched"],
	get_indicator(doc) {
		return {
			"In Progress": [__("In Progress"), "orange", "status,=,In Progress"],
			Completed: [__("Completed"), "green", "status,=,Completed"],
			"Completed with Issues": [__("Completed with Issues"), "yellow", "status,=,Completed with Issues"],
			Failed: [__("Failed"), "red", "status,=,Failed"],
		}[doc.status] || [__(doc.status || "—"), "gray"];
	},
};

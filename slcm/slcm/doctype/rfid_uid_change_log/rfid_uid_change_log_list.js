// Copyright (c) 2026, Nishanth and contributors
frappe.listview_settings["RFID UID Change Log"] = {
	add_fields: ["last_change"],
	get_indicator(doc) {
		return {
			Assigned: [__("Assigned"), "green", "last_change,=,Assigned"],
			Changed: [__("Changed"), "blue", "last_change,=,Changed"],
			Removed: [__("Removed"), "red", "last_change,=,Removed"],
		}[doc.last_change] || [__(doc.last_change || "—"), "gray"];
	},
};

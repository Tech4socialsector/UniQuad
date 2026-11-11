// Copyright (c) 2026, Nishanth and contributors
frappe.listview_settings["RFID UID Change Log"] = {
	add_fields: ["change_type"],
	get_indicator(doc) {
		return {
			Assigned: [__("Assigned"), "green", "change_type,=,Assigned"],
			Changed: [__("Changed"), "blue", "change_type,=,Changed"],
			Removed: [__("Removed"), "red", "change_type,=,Removed"],
		}[doc.change_type] || [__(doc.change_type || "—"), "gray"];
	},
};

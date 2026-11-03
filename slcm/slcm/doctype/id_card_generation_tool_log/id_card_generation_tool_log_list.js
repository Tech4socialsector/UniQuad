frappe.listview_settings["ID Card Generation Tool Log"] = {
	add_fields: ["generation_status", "total_id_cards_generated", "failed_count"],
	get_indicator(doc) {
		const colors = { Success: "green", Partial: "orange", Failed: "red" };
		return [
			__(doc.generation_status || "Unknown"),
			colors[doc.generation_status] || "gray",
			`generation_status,=,${doc.generation_status}`,
		];
	},
};

frappe.query_reports["Consecutive Absents"] = {
    "filters": [
        {
            "fieldname": "threshold",
            "label": __("Minimum Consecutive Days"),
            "fieldtype": "Int",
            "default": 3
        },
        {
            "fieldname": "program",
            "label": __("Programme"),
            "fieldtype": "Link",
            "options": "SLCM Batch"
        }
    ]
};

frappe.query_reports["Course Completion"] = {
    "filters": [
        {
            "fieldname": "academic_year",
            "label": __("Academic Year"),
            "fieldtype": "Link",
            "options": "Academic Year",
            "default": frappe.defaults.get_user_default("academic_year")
        },
        {
            "fieldname": "term",
            "label": __("Academic Term"),
            "fieldtype": "Link",
            "options": "Academic Term",
            "get_query": () => {
                const academic_year = frappe.query_report.get_filter_value("academic_year");
                return { filters: academic_year ? { academic_year } : {} };
            }
        }
    ]
};

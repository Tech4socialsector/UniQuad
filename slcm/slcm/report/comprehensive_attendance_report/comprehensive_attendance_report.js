// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

frappe.query_reports["Comprehensive Attendance Report"] = {
    "filters": [
        {
            "fieldname": "programme_of_study",
            "label": __("Programme"),
            "fieldtype": "Link",
            "options": "Programme",
            "reqd": 0
        },
        {
            "fieldname": "program",
            "label": __("Batch"),
            "fieldtype": "Link",
            "options": "Batch",
            "reqd": 0
        },
        {
            "fieldname": "section",
            "label": __("Section"),
            "fieldtype": "Link",
            "options": "Section",
            "reqd": 0
        },
        {
            "fieldname": "class_name",
            "label": __("Class"),
            "fieldtype": "Link",
            "options": "Classes",
            "reqd": 0
        },
        {
            "fieldname": "course",
            "label": __("Course"),
            "fieldtype": "Link",
            "options": "Course",
            "reqd": 0
        },
        {
            "fieldname": "source",
            "label": __("Attendance Source"),
            "fieldtype": "Select",
            "options": "\nRFID\nManual\nQR\nAuto",
            "reqd": 0
        }
    ]
};

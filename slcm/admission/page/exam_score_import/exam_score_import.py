import frappe
import json

@frappe.whitelist()
def get_exam_types():
    """Returns all configured exam types for dropdown."""
    return frappe.get_all(
        "Exam Type Config",
        fields=["name", "exam_name", "exam_code", "score_import_method",
                "exam_category", "csv_field_mapping"],
        order_by="exam_name asc"
    )

@frappe.whitelist()
def import_csv_scores(exam_type, file_url, admission_cycle):
    """
    Imports exam scores from uploaded CSV file.
    Reads csv_field_mapping from Exam Type Config.
    Matches applicants by email.
    """
    from slcm.admission.utils.exam_import import csv_import
    return csv_import(exam_type, file_url, admission_cycle)

@frappe.whitelist()
def trigger_api_sync(exam_type, admission_cycle):
    """
    Triggers API-based score sync for configured exam type.
    """
    from slcm.admission.utils.exam_import import api_sync
    return api_sync(exam_type, admission_cycle)

@frappe.whitelist()
def get_import_log(admission_cycle):
    """Returns recent import audit log entries for a cycle."""
    return frappe.get_all(
        "Admission Audit Log",
        filters={"reference_doctype": "Exam Type Config",
                 "remarks": ["like", f"Cycle: {admission_cycle} |%"]},
        fields=["name", "action", "creation as created_on",
                "performed_by as created_by", "remarks"],
        order_by="creation desc",
        limit=20
    )

@frappe.whitelist()
def get_admission_cycles():
    """Returns active and draft admission cycles for dropdown."""
    return frappe.get_all(
        "Admission Cycle",
        filters={"status": ["in", ["Draft", "Active"]]},
        fields=["name", "cycle_name", "admission_year",
                "status", "application_start_date", "application_end_date"],
        order_by="application_start_date desc"
    )

@frappe.whitelist()
def get_phase_progress():
    """Returns platform build progress for the top progress bar."""
    return [
        {"phase": 6, "name": "Generic Foundation", "status": "complete"},
        {"phase": 7, "name": "Workflow Engine",    "status": "complete"},
        {"phase": 8, "name": "Forms & Docs",       "status": "complete"},
        {"phase": 9, "name": "Fees & Payments",    "status": "external"},
        {"phase": 10,"name": "Merit & Allocation", "status": "external"},
        {"phase": 11,"name": "Setup Wizard",       "status": "active"},
        {"phase": 12,"name": "Compliance",         "status": "pending"}
    ]

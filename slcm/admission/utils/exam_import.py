import frappe
import json

def csv_import(exam_type_name, file_url, admission_cycle):
    """
    Imports exam scores from a CSV file.
    Uses csv_field_mapping from Exam Type Config to map columns.
    Matches applicants by email address.
    Creates audit log entry for every import.
    """
    import csv, io
    result = {
        "success": False,
        "matched": 0,
        "imported": 0,
        "unmatched": 0,
        "unmatched_rows": [],
        "error": None
    }
    try:
        exam_type = frappe.get_doc("Exam Type Config", exam_type_name)
        field_mapping = {}
        if exam_type.csv_field_mapping:
            field_mapping = json.loads(exam_type.csv_field_mapping)

        file_doc = frappe.get_doc("File", {"file_url": file_url})
        file_path = file_doc.get_full_path()

        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                email = (
                    row.get("Email") or row.get("email") or
                    row.get("EMAIL") or row.get("Applicant Email") or ""
                ).strip().lower()

                applicant_name = frappe.db.get_value(
                    "Applicant",
                    {"email": email, "admission_cycle": admission_cycle},
                    "name"
                )

                if not applicant_name:
                    result["unmatched"] += 1
                    result["unmatched_rows"].append(
                        f"Email not found: {email or 'BLANK'}"
                    )
                    continue

                score_data = {}
                for csv_col, sys_field in field_mapping.items():
                    if csv_col in row:
                        score_data[sys_field] = row[csv_col]

                if not frappe.db.exists(
                    "Applicant Exam Score",
                    {"applicant": applicant_name, "exam_type": exam_type_name}
                ):
                    score_doc = frappe.get_doc({
                        "doctype": "Applicant Exam Score",
                        "applicant": applicant_name,
                        "exam_type": exam_type_name,
                        "admission_cycle": admission_cycle,
                        **score_data
                    })
                    score_doc.insert(ignore_permissions=True)
                else:
                    frappe.db.set_value(
                        "Applicant Exam Score",
                        {"applicant": applicant_name, "exam_type": exam_type_name},
                        score_data
                    )

                result["matched"] += 1
                result["imported"] += 1

        frappe.db.commit()
        _log_import(exam_type_name, admission_cycle,
                    result["imported"], result["unmatched"])
        result["success"] = True

    except Exception as e:
        result["error"] = str(e)
        frappe.log_error(str(e), "CSV Import Error")

    return result


def api_sync(exam_type_name, admission_cycle):
    """
    Fetches exam scores from configured API endpoint.
    Uses api_endpoint, api_auth_type, api_credentials from Exam Type Config.
    """
    import requests
    result = {
        "success": False,
        "matched": 0,
        "imported": 0,
        "error": None
    }
    try:
        exam_type = frappe.get_doc("Exam Type Config", exam_type_name)
        if not exam_type.api_endpoint:
            frappe.throw(f"No API endpoint configured for {exam_type_name}.")

        headers = {}
        if exam_type.api_auth_type == "API Key":
            headers["Authorization"] = f"Bearer {exam_type.get_password('api_credentials')}"
        elif exam_type.api_auth_type == "Basic":
            import base64
            creds = base64.b64encode(
                exam_type.get_password("api_credentials").encode()
            ).decode()
            headers["Authorization"] = f"Basic {creds}"

        response = requests.get(
            exam_type.api_endpoint,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        records = data if isinstance(data, list) else data.get("results", [])

        for record in records:
            email = str(record.get("email", "")).strip().lower()
            applicant_name = frappe.db.get_value(
                "Applicant",
                {"email": email, "admission_cycle": admission_cycle},
                "name"
            )
            if not applicant_name:
                continue

            score_fields = {sf.field_name: record.get(sf.field_name)
                           for sf in exam_type.score_fields
                           if sf.field_name in record}

            if not frappe.db.exists(
                "Applicant Exam Score",
                {"applicant": applicant_name, "exam_type": exam_type_name}
            ):
                score_doc = frappe.get_doc({
                    "doctype": "Applicant Exam Score",
                    "applicant": applicant_name,
                    "exam_type": exam_type_name,
                    "admission_cycle": admission_cycle,
                    **score_fields
                })
                score_doc.insert(ignore_permissions=True)
                result["imported"] += 1

            result["matched"] += 1

        frappe.db.commit()
        _log_import(exam_type_name, admission_cycle,
                    result["imported"], 0, method="API")
        result["success"] = True

    except Exception as e:
        result["error"] = str(e)
        frappe.log_error(str(e), "API Sync Error")

    return result


def _log_import(exam_type, cycle, imported, unmatched, method="CSV"):
    """Creates an audit log entry for the import."""
    try:
        frappe.get_doc({
            "doctype": "Admission Audit Log",
            "action": f"Exam Score Import ({method})",
            "reference_doctype": "Exam Type Config",
            "reference_name": exam_type,
            "remarks": f"Cycle: {cycle} | Imported: {imported} | Unmatched: {unmatched}",
            "performed_by": frappe.session.user
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass

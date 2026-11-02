import frappe
import json
from frappe.utils import now, get_datetime


# ─────────────────────────────────────────────
# INSTITUTION HELPERS
# ─────────────────────────────────────────────

def get_compliance_mode():
    """Returns compliance_mode from Institution Settings."""
    try:
        return frappe.db.get_single_value("Institution Settings", "compliance_mode") or "India"
    except Exception:
        return "India"


def is_india_mode():
    mode = get_compliance_mode()
    return mode in ("India", "Both")


def is_international_mode():
    mode = get_compliance_mode()
    return mode in ("International", "Both")


# ─────────────────────────────────────────────
# GRACEFUL DEGRADATION HELPERS
# Phase 9 / Phase 10 may not be installed
# ─────────────────────────────────────────────

def get_fee_status(applicant, cycle):
    """
    Returns fee payment status for applicant in cycle.
    Returns None if Phase 9 (Fee module) is not installed.
    """
    try:
        if not frappe.db.table_exists("tabFee Payment"):
            return None
        result = frappe.db.get_value(
            "Fee Payment",
            {"applicant": applicant, "admission_cycle": cycle},
            "status"
        )
        return result
    except Exception:
        return None


def get_allocation_status(applicant, cycle):
    """
    Returns seat allocation status for applicant in cycle.
    Returns None if Phase 10 (Merit module) is not installed.
    """
    try:
        if not frappe.db.table_exists("tabSeat Allocation"):
            return None
        result = frappe.db.get_value(
            "Seat Allocation",
            {"applicant": applicant, "admission_cycle": cycle},
            "status"
        )
        return result
    except Exception:
        return None


# ─────────────────────────────────────────────
# RTI EXPORT (India mode)
# ─────────────────────────────────────────────

def rti_export(cycle=None, from_date=None, to_date=None):
    """
    Generates RTI-compliant audit export.
    Returns list of audit log entries as dicts.
    """
    if not is_india_mode():
        frappe.throw("RTI Export is only available in India compliance mode.")

    filters = {}
    if cycle:
        filters["reference_name"] = cycle
    if from_date:
        filters["creation"] = [">=", from_date]
    if to_date:
        filters["creation"] = ["<=", to_date]

    try:
        logs = frappe.get_all(
            "Admission Audit Log",
            filters=filters,
            fields=["name", "action", "reference_doctype", "reference_name",
                    "performed_by", "old_value", "new_value", "creation", "reason"],
            order_by="creation asc"
        )
        return {
            "report_type": "RTI Response Export",
            "generated_on": now(),
            "generated_by": frappe.session.user,
            "record_count": len(logs),
            "records": logs
        }
    except Exception as e:
        frappe.log_error(f"RTI Export failed: {e}", "Compliance")
        return {"error": str(e), "record_count": 0, "records": []}


# ─────────────────────────────────────────────
# NAAC REPORT (India mode)
# ─────────────────────────────────────────────

def naac_report(cycle=None):
    """
    Generates NAAC/UGC admission summary.
    Returns aggregated admission statistics.
    """
    if not is_india_mode():
        frappe.throw("NAAC Report is only available in India compliance mode.")

    filters = {}
    if cycle:
        filters["admission_cycle"] = cycle

    try:
        applicants = frappe.get_all(
            "Applicant",
            filters=filters,
            fields=["name", "status", "admission_cycle"]
        )

        summary = {
            "total_applications": len(applicants),
            "submitted": len([a for a in applicants if a.status == "Submitted"]),
            "draft": len([a for a in applicants if a.status == "Draft"]),
        }

        # Add fee data if Phase 9 installed
        if frappe.db.table_exists("tabFee Payment"):
            summary["fees_collected"] = frappe.db.count("Fee Payment", {"status": "Success"})

        # Add allocation data if Phase 10 installed
        if frappe.db.table_exists("tabSeat Allocation"):
            summary["seats_allocated"] = frappe.db.count("Seat Allocation")

        return {
            "report_type": "NAAC Admission Summary",
            "generated_on": now(),
            "cycle": cycle,
            "summary": summary
        }
    except Exception as e:
        frappe.log_error(f"NAAC Report failed: {e}", "Compliance")
        return {"error": str(e)}


# ─────────────────────────────────────────────
# UGC REPORT (India mode)
# ─────────────────────────────────────────────

def ugc_report(cycle=None):
    """
    Generates UGC-compliant admission summary.
    Includes category-wise seat utilization.
    """
    if not is_india_mode():
        frappe.throw("UGC Report is only available in India compliance mode.")

    try:
        seat_matrix = frappe.get_all(
            "Campus Seat Matrix",
            fields=["campus", "program", "category", "intake_capacity"]
        )
        return {
            "report_type": "UGC Compliance Report",
            "generated_on": now(),
            "cycle": cycle,
            "seat_matrix": seat_matrix,
            "record_count": len(seat_matrix)
        }
    except Exception as e:
        frappe.log_error(f"UGC Report failed: {e}", "Compliance")
        return {"error": str(e)}


# ─────────────────────────────────────────────
# GDPR EXPORT (International mode)
# ─────────────────────────────────────────────

def gdpr_export(applicant):
    """
    Exports all personal data for an applicant (GDPR Article 15).
    Returns structured dict of all applicant data.
    """
    if not is_international_mode():
        frappe.throw("GDPR Export is only available in International compliance mode.")

    try:
        app_data = frappe.get_doc("Applicant", applicant)
        documents = frappe.get_all(
            "Applicant Document",
            filters={"applicant": applicant},
            fields=["document_type", "file", "creation"]
        )
        audit_logs = frappe.get_all(
            "Admission Audit Log",
            filters={"reference_name": applicant},
            fields=["action", "creation", "performed_by"]
        )

        export_data = {
            "applicant_id": app_data.name,
            "full_name": app_data.get("full_name"),
            "email": app_data.get("email"),
            "mobile": app_data.get("mobile"),
            "status": app_data.get("status"),
            "documents": documents,
            "audit_logs": audit_logs,
            "export_timestamp": now(),
            "record_count": 1 + len(documents) + len(audit_logs)
        }
        return export_data
    except Exception as e:
        frappe.log_error(f"GDPR Export failed for {applicant}: {e}", "Compliance")
        return {"error": str(e), "record_count": 0}


@frappe.whitelist()
def gdpr_export_preview(applicant):
    """Whitelisted — used by GDPR form preview button."""
    return gdpr_export(applicant)


# ─────────────────────────────────────────────
# GDPR DELETION / RIGHT TO ERASURE (International mode)
# ─────────────────────────────────────────────

def gdpr_delete(applicant):
    """
    Anonymises all personal data for an applicant (GDPR Article 17).
    Replaces PII fields with anonymised placeholders.
    Preserves statistical/audit records.
    IRREVERSIBLE — always creates audit log before deletion.
    """
    if not is_international_mode():
        frappe.throw("GDPR Erasure is only available in International compliance mode.")

    try:
        app_doc = frappe.get_doc("Applicant", applicant)

        # Log before erasure
        frappe.get_doc({
            "doctype": "Admission Audit Log",
            "action": "GDPR Erasure",
            "reference_doctype": "Applicant",
            "reference_name": applicant,
            "performed_by": frappe.session.user,
            "reason": "GDPR Right to Erasure request",
            "old_value": json.dumps({
                "full_name": app_doc.get("full_name"),
                "email": app_doc.get("email"),
                "mobile": app_doc.get("mobile")
            })
        }).insert(ignore_permissions=True)

        # Anonymise PII fields
        pii_fields = {
            "full_name": f"[ERASED-{applicant}]",
            "email": f"erased_{applicant}@gdpr.invalid",
            "mobile": "0000000000"
        }
        fields_cleared = 0
        for field, placeholder in pii_fields.items():
            if app_doc.get(field):
                frappe.db.set_value("Applicant", applicant, field, placeholder)
                fields_cleared += 1

        frappe.db.commit()
        return {"success": True, "fields_cleared": fields_cleared, "applicant": applicant}
    except Exception as e:
        frappe.log_error(f"GDPR Delete failed for {applicant}: {e}", "Compliance")
        return {"error": str(e), "fields_cleared": 0}


# ─────────────────────────────────────────────
# AUDIT EXPORT (All modes)
# ─────────────────────────────────────────────

def audit_export(from_date=None, to_date=None, reference_doctype=None, cycle=None):
    """
    Exports admission audit log entries.
    Available in all compliance modes.
    """
    filters = {}
    if from_date:
        filters["creation"] = [">=", from_date]
    if to_date:
        filters["creation"] = ["<=", to_date]
    if reference_doctype:
        filters["reference_doctype"] = reference_doctype
    if cycle:
        filters["reference_name"] = cycle

    try:
        logs = frappe.get_all(
            "Admission Audit Log",
            filters=filters,
            fields=["name", "action", "reference_doctype", "reference_name", "performed_by", "old_value", "new_value", "creation", "reason"],
            order_by="creation desc"
        )
        return {
            "report_type": "Audit Export",
            "generated_on": now(),
            "record_count": len(logs),
            "records": logs
        }
    except Exception as e:
        frappe.log_error(f"Audit Export failed: {e}", "Compliance")
        return {"error": str(e), "record_count": 0, "records": []}


# ─────────────────────────────────────────────
# ADMISSION FUNNEL REPORT (All modes)
# ─────────────────────────────────────────────

def admission_funnel(cycle=None):
    """
    Returns stage-by-stage conversion data for admission funnel.
    """
    filters = {}
    if cycle:
        filters["admission_cycle"] = cycle

    try:
        total = frappe.db.count("Applicant", filters)
        submitted = frappe.db.count("Applicant", {**filters, "status": "Submitted"})

        funnel = {
            "Total Registered": total,
            "Applications Submitted": submitted,
        }

        # Add allocation data only if Phase 10 is installed
        if frappe.db.table_exists("tabSeat Allocation"):
            offered = frappe.db.count("Seat Allocation", {"status": "Offered"})
            accepted = frappe.db.count("Seat Allocation", {"status": "Accepted"})
            funnel["Offers Made"] = offered
            funnel["Acceptances"] = accepted

        return {
            "report_type": "Admission Funnel",
            "generated_on": now(),
            "cycle": cycle,
            "funnel": funnel
        }
    except Exception as e:
        frappe.log_error(f"Admission Funnel failed: {e}", "Compliance")
        return {"error": str(e)}


# ─────────────────────────────────────────────
# SEAT UTILIZATION REPORT (All modes)
# ─────────────────────────────────────────────

def seat_utilization(cycle=None):
    """
    Returns seat utilization by category across campuses.
    """
    try:
        matrix = frappe.get_all(
            "Campus Seat Matrix",
            fields=["campus", "program", "category", "intake_capacity"]
        )
        return {
            "report_type": "Seat Utilization by Category",
            "generated_on": now(),
            "cycle": cycle,
            "data": matrix,
            "record_count": len(matrix)
        }
    except Exception as e:
        frappe.log_error(f"Seat Utilization failed: {e}", "Compliance")
        return {"error": str(e)}

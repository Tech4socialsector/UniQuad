
import frappe
from frappe.utils import now

def log_admission_action(
    reference_doctype,
    reference_name,
    applicant=None,
    program=None,
    action_type=None,
    old_value=None,
    new_value=None,
    remarks=None,
    snapshot=None
):
    """
    Central logging function for all admission-related actions.
    """
    log_data = {
        "doctype": "Admission Audit Log",
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "applicant": applicant,
        "program": program,
        "action_type": action_type,
        "old_value": str(old_value) if old_value is not None else None,
        "new_value": str(new_value) if new_value is not None else None,
        "remarks": remarks,
        "performed_by": frappe.session.user,
        "performed_on": now()
    }
    
    if snapshot:
        import json
        log_data["snapshot_json"] = json.dumps(snapshot, indent=2, default=str)

    frappe.get_doc(log_data).insert(ignore_permissions=True)


def log_merit_action(
    merit_list,
    admission_cycle=None,
    applicant=None,
    program=None,
    action_type=None,
    remarks=None
):
    """
    Specialized logging for Merit List activities.
    """
    log_data = {
        "doctype": "Merit Audit Log",
        "merit_list": merit_list,
        "admission_cycle": admission_cycle,
        "applicant": applicant,
        "program": program,
        "action_type": action_type,
        "remarks": remarks,
        "performed_by": frappe.session.user,
        "performed_on": now()
    }
    frappe.get_doc(log_data).insert(ignore_permissions=True)


def log_seat_allocation_action(
    seat_allocation,
    admission_cycle=None,
    applicant=None,
    program=None,
    action_type=None,
    old_value=None,
    new_value=None,
    remarks=None
):
    """
    Specialized logging for Seat Allocation activities.
    """
    log_data = {
        "doctype": "Seat Allocation Audit Log",
        "seat_allocation": seat_allocation,
        "admission_cycle": admission_cycle,
        "applicant": applicant,
        "program": program,
        "action_type": action_type,
        "old_value": str(old_value) if old_value is not None else None,
        "new_value": str(new_value) if new_value is not None else None,
        "remarks": remarks,
        "performed_by": frappe.session.user,
        "performed_on": now()
    }
    frappe.get_doc(log_data).insert(ignore_permissions=True)


def bulk_log_seat_allocation_actions(logs):
    """
    Efficiently logs multiple seat allocation actions using bulk insert.
    'logs' should be a list of dicts matching Seat Allocation Audit Log schema.
    """
    if not logs:
        return
        
    user = frappe.session.user
    time_now = now()
    
    # Exact fieldnames from DocType definition
    field_names = ["name", "creation", "modified", "modified_by", "owner", "docstatus", 
                   "seat_allocation", "admission_cycle", "applicant", "applicant_id", 
                   "program", "action_type", "old_value", "new_value", "remarks", 
                   "performed_by", "performed_on"]
    
    values = []
    for l in logs:
        # Generate random name/ID for the record
        doc_name = frappe.generate_hash(length=10)
        
        row = [
            doc_name, time_now, time_now, user, user, 0,
            l.get("seat_allocation"),
            l.get("admission_cycle"),
            l.get("applicant"),
            l.get("applicant_id") or l.get("applicant"), # Fallback
            l.get("program"),
            l.get("action_type"),
            str(l.get("old_value")) if l.get("old_value") is not None else None,
            str(l.get("new_value")) if l.get("new_value") is not None else None,
            l.get("remarks"),
            user,
            time_now
        ]
        values.append(row)
        
    frappe.db.bulk_insert("Seat Allocation Audit Log", field_names, values)

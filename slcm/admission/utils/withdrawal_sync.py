# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""When an application is withdrawn, keep Student Master and Student Enrollment in sync."""

import frappe
from frappe import _

WITHDRAWN_WORKFLOW_STATE = "Closed"
ENROLLMENT_STATUS_DROPPED = "Dropped"
STUDENT_STATUS_WITHDRAWN = "Withdrawn"


def ensure_workflow_state_withdrawn():
    if frappe.db.exists("Workflow State", WITHDRAWN_WORKFLOW_STATE):
        return
    doc = frappe.get_doc(
        {
            "doctype": "Workflow State",
            "workflow_state_name": WITHDRAWN_WORKFLOW_STATE,
        }
    )
    doc.insert(ignore_permissions=True)


def sync_student_records_for_withdrawn_application(applicant_name, status_remark=None):
    """
    For a withdrawn application (Applicant name):
    - Student Master: Current Status (registration_status) -> Closed (Workflow State)
    - Student Master: Student Status -> Withdrawn
    - Student Master: academic inactive + remark
    - Student Enrollment: status -> Dropped (for non-terminal enrollments)
    """
    if not applicant_name:
        return

    student_name = frappe.db.get_value(
        "Student Master",
        {"application_number": applicant_name},
        "name",
    )
    if not student_name:
        return

    ensure_workflow_state_withdrawn()

    remark = status_remark or _("Application withdrawn")

    # Drop active / pending enrollments; leave Completed and already Dropped unchanged
    for enr in frappe.get_all(
        "Student Enrollment",
        filters={
            "student": student_name,
            "status": ["not in", ["Completed", "Dropped"]],
        },
        pluck="name",
    ):
        frappe.db.set_value("Student Enrollment", enr, "status", ENROLLMENT_STATUS_DROPPED)

    frappe.db.set_value(
        "Student Master",
        student_name,
        {
            "registration_status": WITHDRAWN_WORKFLOW_STATE,
            "student_status": STUDENT_STATUS_WITHDRAWN,
            "academic_status": "Inactive",
            "status_remark": remark,
        },
    )

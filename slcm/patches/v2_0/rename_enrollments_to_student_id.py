"""
Student Enrollment is now named by the Student Master's Student ID
(registration_id): Year 1 = the bare ID, later years "<ID>-Y<n>", and the
Student Master name until an ID is assigned. Rename existing records
(ENR-YYYY-#####, or named by the Student Master name) to match; rename_doc
re-points every Link to them (Fee Invoice, etc.).
"""

import frappe

from slcm.slcm.doctype.student_enrollment.student_enrollment import sync_enrollment_names


def execute():
    students = frappe.get_all(
        "Student Enrollment", filters={"student": ["is", "set"]}, pluck="student", distinct=True
    )
    sync_enrollment_names(students)

# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""
Backfill Batch.total_enrolled_count from existing Student Enrollment records.

Student Enrollment now keeps this field in sync going forward (see
student_enrollment.py on_update/after_delete), but records created before
that logic existed need a one-time recompute.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "SLCM Batch") or not frappe.db.exists("DocType", "Student Enrollment"):
        return
    if not frappe.db.has_column("SLCM Batch", "total_enrolled_count"):
        return

    counts = frappe.db.sql(
        """
        SELECT cohort, COUNT(name) AS total
        FROM `tabStudent Enrollment`
        WHERE status != 'Dropped' AND docstatus < 2
        GROUP BY cohort
        """,
        as_dict=True,
    )
    count_by_batch = {row["cohort"]: row["total"] for row in counts if row["cohort"]}

    for batch_name in frappe.db.get_all("SLCM Batch", pluck="name"):
        frappe.db.set_value(
            "SLCM Batch", batch_name,
            "total_enrolled_count", count_by_batch.get(batch_name, 0),
            update_modified=False,
        )

    frappe.db.commit()

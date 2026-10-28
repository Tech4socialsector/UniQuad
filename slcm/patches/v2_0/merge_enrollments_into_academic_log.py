# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""
Student Enrollment is now one record per student + programme. The year-by-year
history moved from separate per-year enrollments (academic_year / year_no
columns) into the Academic Log child table (Student Academic Log).

For every student + programme:
- the newest enrollment is kept; the older ones are merged into it (their
  Links - fee assignments, invoices, promotion logs, classes... - are
  repointed by rename_doc) after their course rows are moved onto it;
- each former enrollment becomes the log rows of its academic year (one per
  term): the latest year keeps date-based Ongoing/Upcoming/Completed unless it
  was Completed/Dropped, earlier years are Completed (Dropped if dropped, Redo
  when the same year was taken again later);
- course rows get academic year / term / year from their Course Offering;
  Enrolled courses of earlier years take that year's status.
Finally enrollments are renamed to the bare Student ID and Batch counts
refreshed.

The removed academic_year / year_no columns are still in the database after
model sync, so they are read here; on a site without them there is nothing to
migrate.
"""

import frappe
from frappe.model.rename_doc import rename_doc
from frappe.utils import cint, now_datetime

from slcm.slcm.doctype.student_enrollment.student_enrollment import (
    _ay_start,
    build_year_log,
    sync_enrollment_names,
)


def execute():
    if not frappe.db.has_column("Student Enrollment", "academic_year"):
        return

    enrollments = frappe.db.sql(
        """SELECT name, student, program, batch, section, status, academic_year, year_no, creation
           FROM `tabStudent Enrollment`""",
        as_dict=True,
    )
    with_log = set(frappe.get_all(
        "Student Academic Log", filters={"parenttype": "Student Enrollment"}, pluck="parent", distinct=True
    ))

    groups = {}
    for e in enrollments:
        e.academic_year = e.academic_year or frappe.db.get_value("Batch", e.batch, "academic_year")
        groups.setdefault((e.student, e.program), []).append(e)

    touched = set()
    for members in groups.values():
        members.sort(key=lambda e: (_ay_start(e.academic_year), cint(e.year_no), str(e.creation)))
        keeper = members[-1]
        if keeper.name in with_log:
            continue
        try:
            _merge_group(keeper, members)
            touched.add(keeper.student)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=f"merge_enrollments_into_academic_log: {keeper.student} / {keeper.program}",
                message=frappe.get_traceback(),
            )
            continue
        frappe.db.commit()

    _backfill_course_rows()
    if touched:
        sync_enrollment_names(touched)

    from slcm.slcm.doctype.batch.batch import update_enrolled_count

    for batch in frappe.get_all("Batch", pluck="name"):
        update_enrolled_count(batch)
    frappe.db.commit()


def _member_status(member, later):
    """Log status for the rows of a former per-year enrollment, or None to keep
    the date-based statuses (the current year of an active enrollment)."""
    if member.status == "Dropped":
        return "Dropped"
    if any(cint(m.year_no) == cint(member.year_no) for m in later):
        return "Redo"
    if later or member.status == "Completed":
        return "Completed"
    return None


def _merge_group(keeper, members):
    now = now_datetime()
    idx = 0
    seen = set()
    for pos, member in enumerate(members):
        later = members[pos + 1:]
        status = _member_status(member, later)

        if member.academic_year:
            for row in build_year_log(member.academic_year, cint(member.year_no) or 1):
                key = (row["academic_year"], row.get("academic_term"), row["year_no"])
                if key in seen:
                    continue
                seen.add(key)
                idx += 1
                frappe.get_doc({
                    "doctype": "Student Academic Log",
                    "parent": keeper.name,
                    "parenttype": "Student Enrollment",
                    "parentfield": "academic_log",
                    "idx": idx,
                    **row,
                    "section": member.section,
                    "status": status or row["status"],
                    "updated_on": now,
                    "updated_by": "Administrator",
                }).db_insert()

        if member.name == keeper.name:
            continue

        # Close the earlier year's open courses, then move them onto the keeper.
        frappe.db.sql(
            """UPDATE `tabStudent Enrollment Course` SET status = %(status)s
               WHERE parent = %(old)s AND parenttype = 'Student Enrollment' AND status = 'Enrolled'""",
            {"status": status or "Completed", "old": member.name},
        )
        frappe.db.sql(
            """UPDATE `tabStudent Enrollment Course` c
               JOIN `tabStudent Enrollment Course` k
                 ON k.parent = %(keeper)s AND k.parenttype = 'Student Enrollment'
                AND k.course_offering = c.course_offering
               SET c.parent = CONCAT(c.parent, '~dup')
               WHERE c.parent = %(old)s AND c.parenttype = 'Student Enrollment'""",
            {"keeper": keeper.name, "old": member.name},
        )
        frappe.db.sql(
            """UPDATE `tabStudent Enrollment Course` SET parent = %(keeper)s, idx = idx + 1000
               WHERE parent = %(old)s AND parenttype = 'Student Enrollment'""",
            {"keeper": keeper.name, "old": member.name},
        )
        frappe.db.sql(
            "DELETE FROM `tabStudent Enrollment Course` WHERE parent = %s",
            (member.name + "~dup",),
        )
        rename_doc(
            "Student Enrollment", member.name, keeper.name,
            merge=True, force=True, ignore_permissions=True, show_alert=False, rebuild_search=False,
        )

    # Renumber the keeper's course rows after the moves.
    rows = frappe.db.sql(
        """SELECT name FROM `tabStudent Enrollment Course`
           WHERE parent = %s AND parenttype = 'Student Enrollment' ORDER BY idx""",
        keeper.name,
    )
    for n, (row_name,) in enumerate(rows, 1):
        frappe.db.set_value("Student Enrollment Course", row_name, "idx", n, update_modified=False)


def _backfill_course_rows():
    frappe.db.sql(
        """UPDATE `tabStudent Enrollment Course` c
           JOIN `tabCourse Offering` co ON co.name = c.course_offering
           SET c.academic_year = IFNULL(c.academic_year, co.academic_year),
               c.academic_term = IFNULL(c.academic_term, co.term_name),
               c.year_no = IF(IFNULL(c.year_no, 0) = 0, co.year_no, c.year_no)
           WHERE c.parenttype = 'Student Enrollment'"""
    )

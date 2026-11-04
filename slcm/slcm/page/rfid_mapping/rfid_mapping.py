# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

import frappe
import csv
import io

from slcm.permissions import AAD_ROLES
from slcm.slcm.utils.rfid_cards import assign_card, remove_wrong_assignment


# ── Page data APIs ────────────────────────────────────────────────

@frappe.whitelist()
def get_rfid_summary():
    """Full page load — stats + unlinked cards + linked cards + live feed."""
    frappe.only_for(("System Manager", *AAD_ROLES))

    stats = frappe.db.sql("""
        SELECT
            COUNT(*)                                            AS total_logs,
            SUM(student IS NOT NULL AND student != '')         AS linked_logs,
            SUM(student IS NULL OR student = '')               AS unlinked_logs,
            MAX(swipe_time)                                    AS last_swipe,
            MAX(source_id)                                     AS last_sql_id
        FROM `tabAttendance Log`
    """, as_dict=True)[0]

    student_stats = frappe.db.sql("""
        SELECT
            COUNT(*)                                            AS total_students,
            SUM(rfid_uid IS NOT NULL AND rfid_uid != '')       AS students_with_rfid,
            SUM(rfid_uid IS NULL OR rfid_uid = '')             AS students_without_rfid
        FROM `tabStudent Master`
    """, as_dict=True)[0]

    # Distinct RFID UIDs seen from SQL Server that are NOT linked to any student
    unlinked_cards = frappe.db.sql("""
        SELECT
            al.rfid_uid,
            COUNT(*)               AS swipe_count,
            MAX(al.swipe_time)     AS last_seen,
            MAX(al.device_id)      AS terminal_id,
            MAX(al.terminal_alias) AS terminal,
            MAX(al.location)       AS area
        FROM `tabAttendance Log` al
        WHERE al.student IS NULL OR al.student = ''
        GROUP BY al.rfid_uid
        ORDER BY last_seen DESC
    """, as_dict=True)

    # Students already linked — either rfid_uid set on Student Master OR
    # they appear as student on an Attendance Log (covers backfill gap).
    linked_students = frappe.db.sql("""
        SELECT
            sm.name                                         AS student_id,
            sm.first_name                                   AS student_name,
            sm.programme_of_study                           AS programme,
            sm.batch                                        AS batch_year,
            sm.department,
            COALESCE(sm.rfid_uid, MAX(al.rfid_uid))         AS rfid_uid,
            COUNT(al.name)                                  AS total_swipes,
            MAX(al.swipe_time)                              AS last_swipe
        FROM `tabStudent Master` sm
        LEFT JOIN `tabAttendance Log` al ON al.student = sm.name
        WHERE (sm.rfid_uid IS NOT NULL AND sm.rfid_uid != '')
           OR (al.student IS NOT NULL AND al.student != '')
        GROUP BY sm.name, sm.first_name, sm.programme_of_study, sm.batch, sm.department, sm.rfid_uid
        ORDER BY sm.first_name ASC
    """, as_dict=True)

    # Live feed — last 100 logs with all SQL Server source columns
    recent_logs = frappe.db.sql("""
        SELECT
            al.rfid_uid,
            al.student,
            sm.first_name       AS student_name,
            al.swipe_time,
            al.terminal_alias,
            al.location         AS area_alias,
            al.device_id,
            al.processed
        FROM `tabAttendance Log` al
        LEFT JOIN `tabStudent Master` sm ON sm.name = al.student
        ORDER BY al.swipe_time DESC
    """, as_dict=True)

    return {
        "stats":           stats,
        "student_stats":   student_stats,
        "unlinked_cards":  unlinked_cards,
        "linked_students": linked_students,
        "recent_logs":     recent_logs,
    }


@frappe.whitelist()
def get_live_feed(since_swipe_time=None):
    """Incremental refresh every 30 s — only new logs + updated stats."""
    frappe.only_for(("System Manager", *AAD_ROLES))

    stats = frappe.db.sql("""
        SELECT
            COUNT(*)                                            AS total_logs,
            SUM(student IS NOT NULL AND student != '')         AS linked_logs,
            SUM(student IS NULL OR student = '')               AS unlinked_logs,
            MAX(swipe_time)                                    AS last_swipe,
            MAX(source_id)                                     AS last_sql_id
        FROM `tabAttendance Log`
    """, as_dict=True)[0]

    args = []
    where = ""
    if since_swipe_time:
        # Use >= to avoid missing swipes at the exact same second; JS deduplicates by rfid_uid+swipe_time
        where = "WHERE al.swipe_time >= %s"
        args.append(since_swipe_time)

    new_logs = frappe.db.sql(f"""
        SELECT
            al.rfid_uid,
            al.student,
            sm.first_name       AS student_name,
            al.swipe_time,
            al.terminal_alias,
            al.location         AS area_alias,
            al.device_id,
            al.processed
        FROM `tabAttendance Log` al
        LEFT JOIN `tabStudent Master` sm ON sm.name = al.student
        {where}
        ORDER BY al.swipe_time DESC
    """, args, as_dict=True)

    return {"stats": stats, "new_logs": new_logs}


# ── Linking APIs ──────────────────────────────────────────────────

@frappe.whitelist()
def link_rfid_to_student(rfid_uid, student):
    """
    Make rfid_uid the student's active card: Student Master + Student RFID Card history.
    Backfills existing swipes for that UID.
    """
    frappe.only_for(("System Manager", *AAD_ROLES))

    rfid_uid = (rfid_uid or "").strip()
    student  = (student  or "").strip()
    linked = assign_card(student, rfid_uid, "Linked in RFID Card Management")
    frappe.db.commit()

    student_name = frappe.db.get_value("Student Master", student, "first_name")
    return {
        "success": True,
        "message": f"RFID <b>{rfid_uid}</b> linked to <b>{student_name}</b>. {linked} log(s) updated."
    }


@frappe.whitelist()
def unlink_rfid_from_student(student):
    """Undo a wrong link: clear the card from the student, drop its history record and unlink its logs."""
    frappe.only_for(("System Manager", *AAD_ROLES))
    if not frappe.db.exists("Student Master", student):
        frappe.throw(f"Student '{student}' not found.")
    old_uid = remove_wrong_assignment(student)
    frappe.db.commit()
    return {"success": True, "message": f"RFID UID '{old_uid}' removed from student."}


# ── Export for vendor ─────────────────────────────────────────────

@frappe.whitelist()
def get_export_data():
    """
    Returns student list for vendor — columns the vendor needs to
    program RFID cards: Student ID, Name, Programme, Batch, Department.
    Excludes students who already have an RFID UID assigned.
    """
    frappe.only_for(("System Manager", *AAD_ROLES))

    rows = frappe.db.sql("""
        SELECT
            sm.name         AS student_id,
            sm.first_name   AS student_name,
            sm.programme_of_study                           AS programme,
            sm.batch        AS batch_year,
            sm.department   AS department,
            sm.official_email_id AS email
        FROM `tabStudent Master` sm
        WHERE sm.rfid_uid IS NULL OR sm.rfid_uid = ''
        ORDER BY sm.programme_of_study, sm.batch, sm.first_name
    """, as_dict=True)

    return rows


# ── Bulk import (CSV upload) ──────────────────────────────────────

@frappe.whitelist()
def read_uploaded_file(file_url):
    """Read an uploaded CSV or Excel file and return its content as CSV text."""
    frappe.only_for(("System Manager", *AAD_ROLES))

    import os
    try:
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        file_path = file_doc.get_full_path()
        if not os.path.exists(file_path):
            return {"success": False, "error": "File not found on server."}

        if file_path.endswith(".xlsx") or file_path.endswith(".xls"):
            # Convert Excel to CSV text
            import openpyxl, io
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
            lines = []
            for row in ws.iter_rows(values_only=True):
                if any(cell is not None for cell in row):
                    lines.append(",".join(f'"{str(c) if c is not None else ""}"' for c in row))
            content = "\n".join(lines)
        else:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                content = f.read()

        return {"success": True, "content": content}
    except Exception:
        frappe.log_error(title="RFID read_uploaded_file error", message=frappe.get_traceback())
        return {"success": False, "error": "Could not read file. Ensure it is a valid CSV or Excel (.xlsx) file."}


@frappe.whitelist()
def bulk_import_rfid(csv_data):
    """
    Accept CSV text with columns: student_id, rfid_uid
    Links each student to their RFID UID and backfills logs.

    Returns per-row results so UI can show exactly what succeeded/failed.
    """
    frappe.only_for(("System Manager", *AAD_ROLES))

    results = {"linked": [], "skipped": [], "errors": []}

    try:
        reader = csv.DictReader(io.StringIO(csv_data))
    except Exception as e:
        frappe.throw(f"Invalid CSV: {e}")

    for i, row in enumerate(reader, start=2):  # row 1 = header
        student_id = (row.get("student_id") or row.get("Student ID") or "").strip()
        rfid_uid   = (row.get("rfid_uid")   or row.get("RFID UID")   or "").strip()

        if not student_id or not rfid_uid:
            results["skipped"].append({"row": i, "reason": "Empty student_id or rfid_uid"})
            continue

        if not frappe.db.exists("Student Master", student_id):
            results["errors"].append({
                "row": i, "student_id": student_id, "rfid_uid": rfid_uid,
                "reason": f"Student '{student_id}' not found in system"
            })
            continue

        # each row is all-or-nothing: a failure rolls back only that row
        frappe.db.savepoint("rfid_import_row")
        try:
            assign_card(student_id, rfid_uid, "Bulk import in RFID Card Management")
            student_name = frappe.db.get_value("Student Master", student_id, "first_name")
            results["linked"].append({
                "row": i, "student_id": student_id,
                "student_name": student_name, "rfid_uid": rfid_uid
            })
        except Exception as e:
            frappe.db.rollback(save_point="rfid_import_row")
            frappe.clear_messages()
            results["errors"].append({
                "row": i, "student_id": student_id, "rfid_uid": rfid_uid,
                "reason": frappe.utils.strip_html(str(e)) or "Could not link"
            })

    frappe.db.commit()

    total = len(results["linked"])
    errors = len(results["errors"])
    return {
        "success": True,
        "message": f"Import complete: {total} linked, {errors} error(s).",
        "results": results
    }

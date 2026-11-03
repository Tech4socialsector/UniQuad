# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""
RFID SQL Agent — SQL Server Poller
===================================
Reads new biometric/RFID punch rows from a SQL Server table and stores
them in SLCM as "RFID SQL Punch Log" records.

Independent of the live device-push HTTP API (create_attendance_log) and
the Attendance Log doctype — this is a separate ingestion path for devices
that log to a SQL Server table instead of pushing over HTTP.

Flow:
  1. Read watermark (RFID SQL Agent Settings.last_log_id)
  2. SELECT <id, emp_code, terminal_id, terminal_alias, punch_time>
       FROM <table> WHERE id > last_log_id ORDER BY id ASC
       (TOP <batch_size> rows, batch_size default 20)
  3. For each row:
       a. Skip if source_log_id already imported (idempotent)
       b. Resolve emp_code -> Student via Student Master.rfid_uid
       c. Insert RFID SQL Punch Log
  4. Advance watermark to the max id seen
  5. On any unhandled error, optionally email a failure notice
"""

import re
import frappe
from frappe.utils import now_datetime, get_datetime


# ---------------------------------------------------------------------------
# Scheduled entry point
# ---------------------------------------------------------------------------

def poll_rfid_sql_agent():
    """
    Scheduled entry point — ticks every minute (Frappe's finest cron interval)
    but only actually polls once "Poll Interval (seconds)" has elapsed since
    the last run, so admins can dial the effective frequency from the
    RFID SQL Agent Settings form without touching code/hooks.py. The floor is
    60 seconds since Frappe's scheduler itself can't tick faster than that.
    Silently exits when not configured/enabled.
    """
    try:
        cfg = frappe.get_single("RFID SQL Agent Settings")

        if not cfg.enabled:
            return

        if not cfg.db_server:
            return

        interval = max(60, int(cfg.poll_interval_seconds or 300))
        if cfg.last_polled_at:
            elapsed = (now_datetime() - get_datetime(cfg.last_polled_at)).total_seconds()
            if elapsed < interval:
                return

        frappe.db.set_single_value("RFID SQL Agent Settings", "last_polled_at", now_datetime())
        frappe.db.commit()

        _run_poll(cfg)

    except Exception:
        frappe.log_error(
            title="RFID SQL Agent — Unhandled Error",
            message=frappe.get_traceback()
        )
        _maybe_send_failure_mail(frappe.get_single("RFID SQL Agent Settings"), frappe.get_traceback())


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _safe_ident(value, default):
    """Whitelist table/column names to alphanumeric + underscore + dot — prevents SQL injection."""
    cleaned = re.sub(r"[^\w\.]", "", (value or "").strip())
    return cleaned or default


def _run_poll(cfg):
    from slcm.slcm.rfid_sql_agent.connection import get_connection

    last_id = int(cfg.last_log_id or 0)
    batch   = int(cfg.batch_size or 20)

    table     = _safe_ident(cfg.db_table, "iclock_transaction_reffer")
    id_col    = _safe_ident(cfg.sql_id_column, "id")
    emp_col   = _safe_ident(cfg.sql_empcode_column, "emp_code")
    term_col  = _safe_ident(cfg.sql_terminal_id_column, "terminal_id")
    alias_col = _safe_ident(cfg.sql_terminal_alias_column, "terminal_alias")
    time_col  = _safe_ident(cfg.sql_punchtime_column, "punch_time")

    where_clause = f"WHERE {id_col} > ?"
    params = [last_id]
    if cfg.fetch_from_date:
        where_clause += f" AND {time_col} >= ?"
        params.append(cfg.fetch_from_date)
    if cfg.fetch_to_date:
        where_clause += f" AND {time_col} <= ?"
        params.append(cfg.fetch_to_date)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP {batch}
                {id_col},
                {emp_col},
                {term_col},
                {alias_col},
                {time_col}
            FROM {table}
            {where_clause}
            ORDER BY {id_col} ASC
            """,
            params
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        if cfg.is_first_run:
            frappe.db.set_single_value("RFID SQL Agent Settings", "is_first_run", 0)
            frappe.db.commit()
        return

    imported = 0
    skipped  = 0
    max_id   = last_id
    student_cache = {}  # emp_code -> student name or None

    for row in rows:
        sql_id         = row[0]
        emp_code       = (row[1] or "").strip()
        terminal_id    = str(row[2] or "")
        terminal_alias = (row[3] or "").strip()
        punch_time     = row[4]

        if sql_id > max_id:
            max_id = sql_id

        if not emp_code or not punch_time:
            skipped += 1
            continue

        if frappe.db.exists("RFID SQL Punch Log", {"source_log_id": sql_id}):
            skipped += 1
            continue

        if cfg.is_deviceid_zero_padded and terminal_id:
            terminal_id = terminal_id.lstrip("0") or "0"
        if terminal_id.isdigit():
            terminal_id = str(int(terminal_id) + int(cfg.add_to_deviceid or 0))

        if emp_code not in student_cache:
            student_cache[emp_code] = frappe.db.get_value(
                "Student Master", {"rfid_uid": emp_code}, "name"
            )
        student = student_cache[emp_code]

        try:
            doc = frappe.get_doc({
                "doctype":        "RFID SQL Punch Log",
                "source_log_id":  sql_id,
                "emp_code":       emp_code,
                "student":        student,
                "punch_time":     punch_time,
                "terminal_id":    terminal_id,
                "terminal_alias": terminal_alias,
                "sync_status":    "Matched" if student else "Unmatched",
            })
            doc.insert(ignore_permissions=True)
            imported += 1

            _bridge_to_attendance_log(doc)

            if cfg.enable_remote_push:
                _push_to_remote(cfg, doc)
        except Exception:
            frappe.log_error(
                title=f"RFID SQL Agent — Failed to insert punch for emp {emp_code} (SQL id {sql_id})",
                message=frappe.get_traceback()
            )

    if max_id > last_id:
        frappe.db.set_single_value("RFID SQL Agent Settings", "last_log_id", max_id)
    if cfg.is_first_run:
        frappe.db.set_single_value("RFID SQL Agent Settings", "is_first_run", 0)

    frappe.db.commit()

    if imported or skipped:
        frappe.logger("rfid_sql_agent").info(
            f"RFID SQL Agent: imported={imported}, skipped={skipped}, "
            f"max_id={max_id}, ran_at={now_datetime()}"
        )


def _bridge_to_attendance_log(punch_doc):
    """Mirror this punch into Attendance Log so it flows through the same
    reconciliation queue as live-device swipes (create_attendance_log) —
    the Attendance Sync page and the scheduled RFID processor both only
    look at Attendance Log, not RFID SQL Punch Log. Deduped via source_id
    (this punch's source_log_id), so re-polling never creates duplicates.
    RFID SQL Punch Log remains the raw, untouched audit trail of the SQL feed."""
    if frappe.db.exists("Attendance Log", {"source_id": punch_doc.source_log_id, "source": "RFID"}):
        return

    match_status = "Pending"
    if not punch_doc.student:
        match_status = "Unmatched - Unknown Card"
    elif punch_doc.terminal_id and not frappe.db.exists("RFID Device", punch_doc.terminal_id):
        match_status = "Unmatched - No Device Mapping"

    try:
        frappe.get_doc({
            "doctype": "Attendance Log",
            "rfid_uid": punch_doc.emp_code,
            "student": punch_doc.student,
            "swipe_time": punch_doc.punch_time,
            "device_id": punch_doc.terminal_id,
            "terminal_alias": punch_doc.terminal_alias,
            "source": "RFID",
            "source_id": punch_doc.source_log_id,
            "processed": 0,
            "match_status": match_status,
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title=f"RFID SQL Agent — failed to bridge punch {punch_doc.name} to Attendance Log",
            message=frappe.get_traceback()
        )


# ---------------------------------------------------------------------------
# Remote push — forwards each punch to a remote/cloud SLCM site over its
# REST API, for setups where the SQL Server is only reachable from this
# machine (e.g. via a VPN a cloud-hosted site can't run itself).
# ---------------------------------------------------------------------------

def _push_to_remote(cfg, doc):
    """POST one punch to the remote site's REST API. Best-effort: logs and
    marks unsynced on failure so a later retry sweep can pick it up, never
    raises (must not break the local import if the remote is unreachable)."""
    import requests

    site_url = (cfg.remote_site_url or "").rstrip("/")
    api_key = cfg.remote_api_key
    api_secret = cfg.get_password("remote_api_secret")

    if not site_url or not api_key or not api_secret:
        return

    payload = {
        "source_log_id": doc.source_log_id,
        "emp_code": doc.emp_code,
        "student": doc.student,
        "punch_time": str(doc.punch_time),
        "terminal_id": doc.terminal_id,
        "terminal_alias": doc.terminal_alias,
        "sync_status": doc.sync_status,
    }

    try:
        resp = requests.post(
            f"{site_url}/api/resource/RFID SQL Punch Log",
            json=payload,
            headers={"Authorization": f"token {api_key}:{api_secret}"},
            timeout=15,
        )
        # Already pushed earlier counts as success — Frappe reports the
        # unique source_log_id clash as UniqueValidationError.
        if resp.status_code in (200, 409) or (
            resp.status_code == 417
            and ("DuplicateEntryError" in resp.text or "UniqueValidationError" in resp.text)
        ):
            frappe.db.set_value("RFID SQL Punch Log", doc.name, "remote_synced", 1)
        else:
            frappe.log_error(
                title=f"RFID SQL Agent — remote push failed for {doc.name}",
                message=f"HTTP {resp.status_code}: {resp.text[:500]}"
            )
    except Exception:
        frappe.log_error(
            title=f"RFID SQL Agent — remote push error for {doc.name}",
            message=frappe.get_traceback()
        )


@frappe.whitelist()
def retry_unsynced_pushes(limit=200):
    """Retry pushing any punches that failed to reach the remote site earlier.
    bench execute slcm.slcm.rfid_sql_agent.poller.retry_unsynced_pushes"""
    frappe.only_for("System Manager")

    cfg = frappe.get_single("RFID SQL Agent Settings")
    if not cfg.enable_remote_push:
        return {"success": False, "message": "Remote Push is not enabled in RFID SQL Agent Settings."}

    names = frappe.get_all(
        "RFID SQL Punch Log",
        filters={"remote_synced": 0},
        pluck="name",
        limit_page_length=int(limit),
        order_by="punch_time asc",
    )

    for name in names:
        doc = frappe.get_doc("RFID SQL Punch Log", name)
        _push_to_remote(cfg, doc)

    frappe.db.commit()
    return {"success": True, "message": f"Retried {len(names)} unsynced punch(es)."}


def _maybe_send_failure_mail(cfg, traceback_text):
    """Optional SMTP failure notice."""
    try:
        if not cfg or not cfg.cp_is_send_mail or not cfg.mail_to:
            return
        frappe.sendmail(
            recipients=[cfg.mail_to],
            cc=[cfg.mail_cc] if cfg.mail_cc else None,
            bcc=[cfg.mail_bcc] if cfg.mail_bcc else None,
            subject=cfg.mail_subject or "RFID SQL Agent — Biometric Data Sync Failure",
            message=f"<pre>{frappe.utils.escape_html(traceback_text)}</pre>",
        )
    except Exception:
        frappe.log_error(
            title="RFID SQL Agent — Failed to send failure email",
            message=frappe.get_traceback()
        )


# ---------------------------------------------------------------------------
# Whitelisted manual triggers
# ---------------------------------------------------------------------------

@frappe.whitelist()
def poll_now():
    """Manually trigger the poller. bench execute slcm.slcm.rfid_sql_agent.poller.poll_now"""
    frappe.only_for("System Manager")
    try:
        cfg = frappe.get_single("RFID SQL Agent Settings")
        if not cfg.db_server:
            return {"success": False, "message": "SQL Server not configured in RFID SQL Agent Settings."}
        _run_poll(cfg)
        new_last = frappe.db.get_single_value("RFID SQL Agent Settings", "last_log_id")
        return {"success": True, "message": f"Poll complete. Last processed SQL ID: {new_last}"}
    except Exception as e:
        frappe.log_error(title="RFID SQL Agent — poll_now error", message=frappe.get_traceback())
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def test_connection():
    """Whitelisted API — called from RFID SQL Agent Settings 'Test Connection' button."""
    frappe.only_for("System Manager")
    try:
        from slcm.slcm.rfid_sql_agent.connection import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0]
        conn.close()
        return {"success": True, "message": f"Connected. Server: {version[:80]}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def reset_watermark(new_id=0):
    """bench execute slcm.slcm.rfid_sql_agent.poller.reset_watermark --kwargs '{"new_id": 0}'"""
    frappe.only_for("System Manager")
    frappe.db.set_single_value("RFID SQL Agent Settings", "last_log_id", int(new_id))
    frappe.db.commit()
    return {"success": True, "message": f"Watermark reset to {new_id}"}


@frappe.whitelist()
def get_dashboard_summary():
    """Stats + live feed for the RFID SQL Agent Dashboard page."""
    frappe.only_for("System Manager")

    cfg = frappe.get_single("RFID SQL Agent Settings")

    stats = frappe.db.sql("""
        SELECT
            COUNT(*)                                        AS total_punches,
            SUM(sync_status = 'Matched')                    AS matched,
            SUM(sync_status = 'Unmatched')                  AS unmatched,
            MAX(punch_time)                                 AS last_punch
        FROM `tabRFID SQL Punch Log`
    """, as_dict=True)[0]

    recent = frappe.db.sql("""
        SELECT
            cpl.emp_code, cpl.student, sm.first_name AS student_name,
            cpl.punch_time, cpl.terminal_id, cpl.terminal_alias, cpl.sync_status
        FROM `tabRFID SQL Punch Log` cpl
        LEFT JOIN `tabStudent Master` sm ON sm.name = cpl.student
        ORDER BY cpl.punch_time DESC
        LIMIT 5000
    """, as_dict=True)

    return {
        "enabled":             bool(cfg.enabled),
        "last_log_id":         cfg.last_log_id,
        "poll_interval_seconds": max(60, int(cfg.poll_interval_seconds or 300)),
        "stats":               stats,
        "recent":              recent,
    }

#!/usr/bin/env python3
# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""
SLCM RFID Sync Agent (standalone)
=================================
Runs on an always-on machine inside the campus network. Reads new punch rows
from the biometric SQL Server table and pushes them to the live SLCM site over
its REST API — the same job the in-app "RFID SQL Agent" does, without needing
Frappe, a VPN, or any inbound firewall change.

Per punch it:
  1. resolves emp_code -> Student Master (rfid_uid) on the live site
  2. creates an "RFID SQL Punch Log" (deduped by unique source_log_id)
  3. mirrors it into "Attendance Log" (deduped by source + source_id), so the
     live site's scheduled RFID processor turns it into Student Attendance

The watermark (last SQL id pushed) lives in state.json next to this file.
On the very first run it starts from the highest source_log_id already on the
live site, so nothing is re-sent.

Usage:
  python rfid_sync_agent.py              # run forever, poll every N seconds
  python rfid_sync_agent.py --once       # catch up on new punches, then exit (Task Scheduler / cron)
  python rfid_sync_agent.py --test       # check SQL + live site connectivity only
  python rfid_sync_agent.py --once --dry-run [--from-id N]
                                         # show what would be pushed, write nothing
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# SQL Server 2014 only speaks TLS 1.0, which OpenSSL 3 / GnuTLS refuse by
# default on modern Linux. These must be set before anything initialises
# OpenSSL (requests, pyodbc), so they sit above the other imports.
if os.name != "nt":
    _openssl_cnf = os.path.join(HERE, "mssql_openssl.cnf")
    _gnutls_cnf = os.path.join(HERE, "mssql_gnutls_override.conf")
    if os.path.exists(_openssl_cnf):
        os.environ.setdefault("OPENSSL_CONF", _openssl_cnf)
    if os.path.exists(_gnutls_cnf):
        os.environ.setdefault("GNUTLS_SYSTEM_PRIORITY_FILE", _gnutls_cnf)
        os.environ.setdefault("GNUTLS_SYSTEM_PRIORITY_FAIL_ON_INVALID", "0")

import argparse
import configparser
import json
import logging
import re
import time
from logging.handlers import RotatingFileHandler

import pyodbc
import requests

CONFIG_FILE = os.path.join(HERE, "config.ini")
STATE_FILE = os.path.join(HERE, "state.json")
LOCK_FILE = os.path.join(HERE, "agent.lock")
LOG_FILE = os.path.join(HERE, "agent.log")

STUDENT_CACHE_TTL = 15 * 60  # seconds
STALE_LOCK_SECONDS = 10 * 60  # lock is touched every row/cycle, so older means a crashed run

log = logging.getLogger("rfid_sync_agent")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_logging():
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        sys.exit(f"Missing {CONFIG_FILE} — copy config.example.ini to config.ini and fill it in.")
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(CONFIG_FILE, encoding="utf-8")
    return cp


def _safe_ident(value, default):
    """Whitelist table/column names to alphanumeric + underscore + dot — prevents SQL injection."""
    cleaned = re.sub(r"[^\w\.]", "", (value or "").strip())
    return cleaned or default


# ---------------------------------------------------------------------------
# State + lock
# ---------------------------------------------------------------------------

def read_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, STATE_FILE)


def acquire_lock():
    """Stops two copies (e.g. overlapping scheduled runs) from pushing at once."""
    if os.path.exists(LOCK_FILE) and time.time() - os.path.getmtime(LOCK_FILE) > STALE_LOCK_SECONDS:
        os.remove(LOCK_FILE)
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def touch_lock():
    try:
        os.utime(LOCK_FILE, None)
    except OSError:
        pass


def release_lock():
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# SQL Server
# ---------------------------------------------------------------------------

def get_sql_connection(cfg):
    s = cfg["sql"]
    available = pyodbc.drivers()
    # Windows: the built-in "SQL Server" driver handles SQL Server 2014's
    # TLS 1.0 without extra setup. Linux: FreeTDS (apt install tdsodbc).
    preferred = ["SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server", "FreeTDS"]
    if os.name != "nt":
        preferred = ["FreeTDS", "ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"]
    driver = s.get("driver", "").strip() or next((d for d in preferred if d in available), None)
    if not driver:
        raise RuntimeError(f"No SQL Server ODBC driver found. Installed drivers: {available}")

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={s['server']},{s.getint('port', 1433)};"
        f"DATABASE={s['database']};"
        f"UID={s['username']};"
        f"PWD={s['password']};"
        "TrustServerCertificate=yes;"
    )
    if driver == "FreeTDS":
        conn_str += "TDS_Version=7.4;"
    if driver == "ODBC Driver 18 for SQL Server":
        conn_str += "Encrypt=no;"
    return pyodbc.connect(conn_str, autocommit=True, timeout=15)


def fetch_rows(cfg, last_id, batch):
    s = cfg["sql"]
    table = _safe_ident(s.get("table"), "iclock_transaction")
    id_col = _safe_ident(s.get("id_column"), "id")
    emp_col = _safe_ident(s.get("empcode_column"), "emp_code")
    term_col = _safe_ident(s.get("terminal_id_column"), "terminal_id")
    alias_col = _safe_ident(s.get("terminal_alias_column"), "terminal_alias")
    time_col = _safe_ident(s.get("punchtime_column"), "punch_time")

    where = f"WHERE {id_col} > ?"
    params = [last_id]
    from_date = s.get("fetch_from_date", "").strip()
    if from_date:
        where += f" AND {time_col} >= ?"
        params.append(from_date)

    conn = get_sql_connection(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT TOP {int(batch)} {id_col}, {emp_col}, {term_col}, {alias_col}, {time_col} "
            f"FROM {table} {where} ORDER BY {id_col} ASC",
            params,
        )
        return cur.fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Live site (Frappe REST API)
# ---------------------------------------------------------------------------

class TransientError(Exception):
    """Network / server error — stop this cycle and retry the row next time."""


def is_duplicate(resp):
    """Live already has this row. Frappe reports a unique-key clash as either
    DuplicateEntryError or (for a unique field like source_log_id)
    UniqueValidationError, with HTTP 409 or 417."""
    return resp.status_code == 409 or (
        resp.status_code == 417
        and ("DuplicateEntryError" in resp.text or "UniqueValidationError" in resp.text)
    )


class LiveSite:
    def __init__(self, cfg):
        lv = cfg["live"]
        self.url = lv["site_url"].rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {lv['api_key']}:{lv['api_secret']}"
        self.students = {}  # emp_code -> (student or None, fetched_at)
        self.devices = {}   # terminal_id -> bool

    def _request(self, method, path, **kw):
        try:
            resp = self.session.request(method, f"{self.url}{path}", timeout=30, **kw)
        except requests.RequestException as e:
            raise TransientError(f"{method} {path}: {e}") from e
        if resp.status_code >= 500 and not is_duplicate(resp):
            raise TransientError(f"{method} {path}: HTTP {resp.status_code} {resp.text[:300]}")
        return resp

    def get_list(self, doctype, filters, fields, order_by=None, limit=1):
        params = {"filters": json.dumps(filters), "fields": json.dumps(fields), "limit_page_length": limit}
        if order_by:
            params["order_by"] = order_by
        resp = self._request("GET", f"/api/resource/{doctype}", params=params)
        if resp.status_code != 200:
            raise TransientError(f"GET {doctype}: HTTP {resp.status_code} {resp.text[:300]}")
        return resp.json().get("data", [])

    def insert(self, doctype, doc):
        """Returns True if created or already present (duplicate)."""
        resp = self._request("POST", f"/api/resource/{doctype}", json=doc)
        if resp.status_code == 200 or is_duplicate(resp):
            return True
        raise TransientError(f"POST {doctype}: HTTP {resp.status_code} {resp.text[:300]}")

    def whoami(self):
        resp = self._request("GET", "/api/method/frappe.auth.get_logged_user")
        if resp.status_code != 200:
            raise RuntimeError(f"Live site rejected the API key/secret: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json().get("message")

    def max_source_log_id(self):
        rows = self.get_list("RFID SQL Punch Log", [], ["source_log_id"], order_by="source_log_id desc")
        return int(rows[0]["source_log_id"]) if rows else 0

    def student_for(self, emp_code):
        hit = self.students.get(emp_code)
        if hit and time.time() - hit[1] < STUDENT_CACHE_TTL:
            return hit[0]
        rows = self.get_list("Student Master", [["rfid_uid", "=", emp_code]], ["name"])
        student = rows[0]["name"] if rows else None
        self.students[emp_code] = (student, time.time())
        return student

    def device_exists(self, terminal_id):
        if terminal_id not in self.devices:
            self.devices[terminal_id] = bool(self.get_list("RFID Device", [["name", "=", terminal_id]], ["name"]))
        return self.devices[terminal_id]

    def attendance_log_exists(self, source_id):
        return bool(self.get_list("Attendance Log", [["source", "=", "RFID"], ["source_id", "=", source_id]], ["name"]))


# ---------------------------------------------------------------------------
# Sync cycle
# ---------------------------------------------------------------------------

def normalise_terminal(cfg, terminal_id):
    s = cfg["sql"]
    if s.getboolean("device_id_zero_padded", False) and terminal_id:
        terminal_id = terminal_id.lstrip("0") or "0"
    if terminal_id.isdigit():
        terminal_id = str(int(terminal_id) + s.getint("add_to_device_id", 0))
    return terminal_id


def push_row(cfg, live, row, dry_run):
    sql_id, emp_code, terminal_id, terminal_alias, punch_time = row
    emp_code = (emp_code or "").strip()
    if not emp_code or not punch_time:
        return "skipped"

    terminal_id = normalise_terminal(cfg, str(terminal_id or ""))
    terminal_alias = (terminal_alias or "").strip()
    punch_time = str(punch_time)
    student = live.student_for(emp_code)

    punch = {
        "source_log_id": sql_id,
        "emp_code": emp_code,
        "student": student,
        "punch_time": punch_time,
        "terminal_id": terminal_id,
        "terminal_alias": terminal_alias,
        "sync_status": "Matched" if student else "Unmatched",
        "remote_synced": 1,
    }

    match_status = "Pending"
    if not student:
        match_status = "Unmatched - Unknown Card"
    elif terminal_id and not live.device_exists(terminal_id):
        match_status = "Unmatched - No Device Mapping"

    if dry_run:
        log.info(f"[dry-run] id={sql_id} emp={emp_code} student={student} t={punch_time} "
                 f"terminal={terminal_id}/{terminal_alias} -> {match_status}")
        return "pushed"

    live.insert("RFID SQL Punch Log", punch)

    if cfg["agent"].getboolean("create_attendance_log", True) and not live.attendance_log_exists(sql_id):
        live.insert("Attendance Log", {
            "rfid_uid": emp_code,
            "student": student,
            "swipe_time": punch_time,
            "device_id": terminal_id,
            "terminal_alias": terminal_alias,
            "source": "RFID",
            "source_id": sql_id,
            "processed": 0,
            "match_status": match_status,
        })
    return "pushed"


def run_cycle(cfg, live, dry_run=False, from_id=None):
    state = read_state()
    if from_id is not None:
        last_id = from_id
    elif "last_log_id" in state:
        last_id = int(state["last_log_id"])
    else:
        last_id = live.max_source_log_id()
        log.info(f"First run: starting after the live site's highest source_log_id {last_id}")
        if not dry_run:
            write_state({"last_log_id": last_id})

    rows = fetch_rows(cfg, last_id, cfg["agent"].getint("batch_size", 500))
    if not rows:
        return 0

    pushed = skipped = 0
    new_last = last_id
    failed = None
    for row in rows:
        try:
            if push_row(cfg, live, row, dry_run) == "pushed":
                pushed += 1
            else:
                skipped += 1
            new_last = max(new_last, row[0])
            touch_lock()
        except TransientError as e:
            # Rows sharing this id may already be in; step back one so the
            # whole id group is retried (live dedupes the ones that landed).
            new_last = min(new_last, row[0] - 1)
            failed = e
            break

    if not dry_run and new_last > last_id:
        write_state({"last_log_id": new_last, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")})

    log.info(f"Cycle: fetched={len(rows)} pushed={pushed} skipped={skipped} watermark {last_id} -> {new_last}"
             + (" (dry-run, not saved)" if dry_run else ""))
    if failed:
        log.warning(f"Stopped early, will retry next cycle: {failed}")
    return len(rows)


def test_connections(cfg):
    ok = True
    try:
        conn = get_sql_connection(cfg)
        cur = conn.cursor()
        cur.execute("SELECT @@VERSION")
        log.info(f"SQL Server OK: {cur.fetchone()[0].splitlines()[0]}")
        conn.close()
    except Exception as e:
        ok = False
        log.error(f"SQL Server FAILED: {e}")
    try:
        live = LiveSite(cfg)
        log.info(f"Live site OK: logged in as {live.whoami()}, highest source_log_id {live.max_source_log_id()}")
    except Exception as e:
        ok = False
        log.error(f"Live site FAILED: {e}")
    return ok


def main():
    ap = argparse.ArgumentParser(description="SLCM RFID Sync Agent")
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    ap.add_argument("--test", action="store_true", help="test SQL Server and live site connectivity")
    ap.add_argument("--dry-run", action="store_true", help="show what would be pushed; write nothing")
    ap.add_argument("--from-id", type=int, help="with --dry-run: start after this SQL id")
    args = ap.parse_args()

    setup_logging()
    cfg = load_config()

    if args.test:
        sys.exit(0 if test_connections(cfg) else 1)

    if not acquire_lock():
        log.info("Another copy is already running — exiting.")
        return
    try:
        live = LiveSite(cfg)
        interval = max(30, cfg["agent"].getint("poll_interval_seconds", 60))
        while True:
            try:
                fetched = run_cycle(cfg, live, dry_run=args.dry_run, from_id=args.from_id)
            except Exception as e:
                fetched = 0
                log.error(f"Cycle failed: {e}")
            if args.dry_run:
                break
            # A full batch means there's a backlog — go again straight away.
            if fetched < cfg["agent"].getint("batch_size", 500):
                if args.once:
                    break
                time.sleep(interval)
            touch_lock()
    finally:
        release_lock()


if __name__ == "__main__":
    main()

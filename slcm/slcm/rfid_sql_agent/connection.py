# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""
SQL Server connection helper for the RFID SQL Agent.

Reads credentials from "RFID SQL Agent Settings" (single doctype) and
returns a live pyodbc connection. Callers are responsible for closing it.
"""

import os
import socket

import frappe

# Seconds. Kept well under the web worker timeout so a slow or unreachable SQL Server gives a clear
# message instead of a 502: reach the port, log in, then each query (when the caller sets one).
TCP_TIMEOUT = 5
LOGIN_TIMEOUT = 10

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))

# Absolute path to the custom OpenSSL config that enables TLS 1.0.
# Required because SQL Server 2014 only supports TLS 1.0, which Ubuntu 22.04
# / OpenSSL 3 disables by default. We override OPENSSL_CONF at the process
# level before opening the pyodbc connection so only this code is affected.
_OPENSSL_CNF = os.path.join(_APP_ROOT, "mssql_openssl.cnf")

# Absolute path to the custom GnuTLS priority override that allows TLS 1.0/1.1.
# FreeTDS uses GnuTLS (not OpenSSL) for its encrypted-login handshake on this
# system, and GnuTLS also refuses TLS 1.0 by default — the OPENSSL_CONF
# override above has no effect on it, so it needs its own env var.
_GNUTLS_CNF = os.path.join(_APP_ROOT, "mssql_gnutls_override.conf")


_FREETDS_LIB_CANDIDATES = [
    "/usr/lib/x86_64-linux-gnu/odbc/libtdsodbc.so",
    "/usr/lib/aarch64-linux-gnu/odbc/libtdsodbc.so",
    "/usr/lib/odbc/libtdsodbc.so",
    "/usr/lib64/libtdsodbc.so",
]


def _find_freetds_lib():
    """Locate the FreeTDS ODBC shared library on disk, regardless of whether
    it's registered in /etc/odbcinst.ini. Returns the path, or None."""
    import glob
    for path in _FREETDS_LIB_CANDIDATES:
        if os.path.exists(path):
            return path
    matches = glob.glob("/usr/lib/*/odbc/libtdsodbc.so") + glob.glob("/usr/lib/**/libtdsodbc.so", recursive=True)
    return matches[0] if matches else None


def get_connection(query_timeout=None):
    """
    Return an open pyodbc connection to the SQL Server configured in
    RFID SQL Agent Settings. Raises frappe.ValidationError with a clear
    message if config is incomplete or the connection fails.

    query_timeout: seconds each query may run (screens a person waits on pass one;
    the background poller leaves it unset).
    """
    try:
        import pyodbc
    except ImportError:
        frappe.throw(
            "pyodbc is not installed. Run: bench pip install pyodbc",
            title="Missing Dependency"
        )

    cfg = frappe.get_single("RFID SQL Agent Settings")

    server   = (cfg.db_server   or "").strip()
    port     = int(cfg.db_port  or 1433)
    database = (cfg.db_database or "").strip()
    username = (cfg.db_login    or "").strip()
    password = cfg.get_password("db_password") or ""

    if not all([server, database, username]):
        frappe.throw(
            "SQL Server connection is not fully configured. "
            "Fill Server Host, Database, and Username in RFID SQL Agent Settings → SQL Server tab.",
            title="RFID SQL Agent — SQL Server Not Configured"
        )

    # FreeTDS first: it uses GnuTLS, whose TLS policy we can still relax at
    # runtime via env vars inside a long-running Frappe worker (see below).
    # Microsoft's driver links the process-wide OpenSSL library, which Frappe
    # itself already initializes during startup (requests, crypto, etc.)
    # *before* this code ever runs — OpenSSL only reads OPENSSL_CONF once, at
    # that first init, so setting it here has no effect on Microsoft's driver
    # once the worker is already running. Only reached for for the newer,
    # stricter TLS modes FreeTDS can't do at all.
    drivers = [
        "FreeTDS",
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ]

    available = list(pyodbc.drivers())
    chosen = next((d for d in drivers if d in available), None)
    is_freetds = chosen == "FreeTDS"

    if not chosen:
        # Fall back to pointing pyodbc straight at the FreeTDS shared library,
        # in case tdsodbc is installed but never got registered in
        # /etc/odbcinst.ini (e.g. on Frappe Cloud, where there's no way to
        # write that file by hand). pyodbc accepts a raw .so path as DRIVER.
        chosen = _find_freetds_lib()
        is_freetds = bool(chosen)

    if not chosen:
        frappe.throw(
            f"No compatible ODBC driver found. Add 'tdsodbc', 'unixodbc', and 'unixodbc-dev' "
            f"as APT dependencies (Frappe Cloud) or install 'ODBC Driver 17 for SQL Server' "
            f"on the server. Drivers found: {available}",
            title="ODBC Driver Missing"
        )

    conn_str = (
        f"DRIVER={{{chosen}}};"
        f"SERVER={server},{port};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
        "Connection Timeout=10;"
    )

    if is_freetds:
        conn_str += "TDS_Version=7.4;"

    # FreeTDS ignores "Connection Timeout" in the string, so an unreachable host would hang the request.
    # Only a plain host is checked: a named instance (host\\INSTANCE, port found through SQL Browser) or a
    # host already carrying its own port connects exactly as before.
    try:
        if "\\" not in server and "," not in server:
            socket.create_connection((server, port), timeout=TCP_TIMEOUT).close()
    except OSError as e:
        frappe.throw(
            f"This server cannot reach SQL Server {server}:{port} (no answer within {TCP_TIMEOUT} seconds: {e}). "
            "The SQL Server is on the campus network: run this from a machine that can reach it (on campus or "
            "over the VPN), or check the Server Host / Port in RFID SQL Agent Settings.",
            title="RFID SQL Agent — SQL Server Not Reachable"
        )

    _prev_openssl_conf = os.environ.get("OPENSSL_CONF")
    _prev_gnutls_prio  = os.environ.get("GNUTLS_SYSTEM_PRIORITY_FILE")
    _prev_gnutls_fail  = os.environ.get("GNUTLS_SYSTEM_PRIORITY_FAIL_ON_INVALID")

    if os.path.exists(_OPENSSL_CNF):
        os.environ["OPENSSL_CONF"] = _OPENSSL_CNF
    if os.path.exists(_GNUTLS_CNF):
        os.environ["GNUTLS_SYSTEM_PRIORITY_FILE"] = _GNUTLS_CNF
        os.environ["GNUTLS_SYSTEM_PRIORITY_FAIL_ON_INVALID"] = "0"

    try:
        conn = pyodbc.connect(conn_str, autocommit=True, timeout=LOGIN_TIMEOUT)
    except Exception as e:
        frappe.throw(
            f"Could not connect to SQL Server ({server}:{port}/{database}): {e}",
            title="RFID SQL Agent — SQL Server Connection Failed"
        )
    finally:
        for var, prev in (
            ("OPENSSL_CONF", _prev_openssl_conf),
            ("GNUTLS_SYSTEM_PRIORITY_FILE", _prev_gnutls_prio),
            ("GNUTLS_SYSTEM_PRIORITY_FAIL_ON_INVALID", _prev_gnutls_fail),
        ):
            if prev is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = prev

    if query_timeout:
        conn.timeout = int(query_timeout)
    return conn

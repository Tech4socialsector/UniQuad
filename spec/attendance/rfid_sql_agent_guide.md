# RFID SQL Agent — Setup, Connection & Verification Guide

This is a separate, independent way to pull RFID/biometric attendance data
into SLCM: it polls a Microsoft SQL Server table (the same one older
on-premise devices/agents wrote to) and stores punches in SLCM's own
**RFID SQL Punch Log** doctype. It does **not** touch the existing live
device-push API (`create_attendance_log`) or the **Attendance Log** doctype —
those keep working exactly as before, independently of this agent.

---

## 1. What's involved

| Piece | Purpose |
|---|---|
| **RFID SQL Agent Settings** (doctype, single) | All configuration: DB connection, table/column names, batch size, poll interval, date range, failure email. |
| **RFID SQL Punch Log** (doctype) | Where every pulled punch is stored. |
| **RFID SQL Agent Dashboard** (page) | Live monitoring: stats, status, and a searchable/sortable table of recent punches. |
| `slcm.slcm.rfid_sql_agent.poller` | The background code that does the actual pulling. |
| `slcm.slcm.rfid_sql_agent.connection` | SQL Server connection helper (handles ODBC driver + legacy TLS quirks). |

---

## 2. One-time machine setup (already done on this dev box, needed on any new machine)

1. **Database driver**: `bench pip install pyodbc`, plus an ODBC driver installed at the OS level. On Ubuntu, FreeTDS is the simplest:
   ```
   sudo apt install -y tdsodbc unixodbc unixodbc-dev
   sudo bash -c 'cat > /etc/odbcinst.ini << EOF
   [FreeTDS]
   Description = FreeTDS Driver
   Driver = /usr/lib/x86_64-linux-gnu/odbc/libtdsodbc.so
   Setup = /usr/lib/x86_64-linux-gnu/odbc/libtdsS.so
   FileUsage = 1
   EOF'
   odbcinst -q -d   # should list [FreeTDS]
   ```

2. **Legacy TLS support**: if the target SQL Server is old (e.g. SQL Server 2014, which only supports TLS 1.0/1.1), two override config files are already checked into the app root (`apps/slcm/mssql_openssl.cnf` and `apps/slcm/mssql_gnutls_override.conf`). `connection.py` applies them automatically around every connection attempt — no manual step needed once these files exist.

---

## 3. Connecting to the network (VPN)

If the SQL Server is on a private/internal network (as with the NLS deployment), you need a VPN tunnel up before anything else will work.

**For a FortiGate SSL-VPN** (the NLS setup uses this):
```
sudo apt install -y openfortivpn

# First attempt will likely fail on certificate trust and print a fingerprint — copy it.
sudo openfortivpn <vpn-gateway-host>:<vpn-port> --username=<user> --password='<password>'

# Re-run with the fingerprint it printed, in a terminal you leave open:
sudo openfortivpn <vpn-gateway-host>:<vpn-port> --username=<user> --password='<password>' \
     --trusted-cert <sha256-fingerprint-from-previous-attempt>
```
Leave that terminal running — closing it drops the tunnel and the agent stops getting new data until reconnected.

**Verify the tunnel is actually up:**
```
ip addr show ppp0        # should show an active ppp0 interface with an IP
ping -c 2 <internal-ip>  # confirm you can reach the internal network
```

**Important — hostnames often don't resolve over the VPN.** If the DB is referred to by an internal hostname (e.g. `NLSADSERVER`) and DNS isn't pushed through the tunnel, resolution will fail even though the tunnel is up. In that case, ask IT/network admin for the actual internal IP address and use that directly instead of the hostname.

---

## 4. Configuring RFID SQL Agent Settings

Open the doctype (search "RFID SQL Agent Settings" in the awesome-bar) and fill in:

**General tab**
- **Enable RFID SQL Agent** — turn on.
- **Poll Interval (seconds)** — how often to check for new swipes (floor is 60s — Frappe's scheduler can't tick faster than once a minute).
- **Batch Size** — max rows pulled per poll. Use a small number (20–100) for steady-state; temporarily raise it a lot (e.g. 5000) if you need to fast-catch-up through a big backlog, then lower it back down afterward.

**SQL Server tab**
- Server Host / Port / Database / Username / Password.
- Table/View and column names — defaults match `iclock_transaction_reffer`'s shape (`id`, `emp_code`, `terminal_id`, `terminal_alias`, `punch_time`); adjust if your source table differs.

**Watermark tab**
- **Last Log ID** — auto-managed; only reset manually if you want to re-import from scratch.
- **Fetch Swipes From / To** — set a date range to skip a large historical backlog and jump straight to a relevant period (e.g. set "Fetch Swipes From" to today's date to only get live data going forward).

**Failure Email tab** — optional SMTP alert if a poll run errors.

---

## 5. Testing the connection

Click **Test Connection** on the form. It should return something like:
```
Connected. Server: Microsoft SQL Server 2014 - 12.0.2000.8 (X64) ...
```

If it fails, the error message is specific — common ones:
- `ODBC Driver Missing` → install FreeTDS (see step 2).
- `Unable to connect to data source (0)` → usually means either (a) you're not on the VPN, (b) wrong host/port, or (c) an old SQL Server needing the TLS override (see step 2.2).
- `Login failed` → wrong username/password.

You can also test from the command line:
```
bench --site <your-site> execute slcm.slcm.rfid_sql_agent.poller.test_connection
```

---

## 6. Pulling data and verifying it

**Manual pull (don't wait for the scheduler):**
```
bench --site <your-site> execute slcm.slcm.rfid_sql_agent.poller.poll_now
```
or click **Run Now** on the Settings form or the Dashboard page.

**Where to check the data:**
1. **RFID SQL Agent Dashboard** (search it in the awesome-bar) — live stats (total/matched/unmatched, watermark, enabled status) plus a searchable, sortable table of the most recent punches. Auto-refreshes every 30 seconds.
2. **RFID SQL Punch Log** (search it in the awesome-bar) — the full doctype list view, for filtering/exporting beyond what the dashboard shows.
3. Quick DB check without opening the browser:
   ```
   bench --site <your-site> mariadb -e "SELECT COUNT(*), MAX(punch_time) FROM \`tabRFID SQL Punch Log\`;"
   ```

**Confirming it's genuinely live (not just replaying backlog):**
- Note the current watermark (`Last Log ID` on the dashboard).
- Have someone swipe a real card at a gate right now.
- Wait for the next poll tick (or click Run Now) — the new swipe should appear at the top of the dashboard feed within moments, with `punch_time` matching the swipe you just did.

---

## 7. Mapping RFID cards to students

New swipes show as `Unmatched` until a student's `Student Master.rfid_uid` field matches the `emp_code` from the source table. Set that field (directly on Student Master, or via the existing "Student RFID Card" doctype) to link them — matched punches will then show the student's name and `Matched` status automatically on the next poll.

---

## 8. Known limitations

- **VPN dependency**: if the source DB is behind a VPN, this whole pipeline stops working the moment the VPN tunnel drops (terminal closed, machine sleeps, reboot). For production reliability, this VPN connection should run as a persistent systemd service rather than a manual foreground terminal — ask to have this set up if it isn't already.
- **Poll floor of 60 seconds**: Frappe's scheduler can't tick faster than once a minute, so true sub-minute polling isn't possible without a different (non-scheduler-based) mechanism.
- **Large backlogs are slow at small batch sizes**: if the source table has years of history, use the **Fetch Swipes From** date field to skip ahead, or temporarily raise **Batch Size** to catch up faster.

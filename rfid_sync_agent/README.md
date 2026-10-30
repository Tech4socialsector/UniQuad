# SLCM RFID Sync Agent: Installation Guide

This small program copies biometric/RFID punches from the campus SQL Server to the
live SLCM site (https://app.nls.ac.in) every minute.

```
Biometric SQL Server (192.168.10.10, campus network)
        |  reads new punches every minute
SLCM RFID Sync Agent  (this folder, on an always-on campus machine)
        |  HTTPS, outbound only
Live SLCM site (app.nls.ac.in)
```

## What the machine needs

- It is **always on** and does not sleep. A server or a desktop that never shuts down is fine.
- It is **on the campus network** and can reach `192.168.10.10` on port **1433**, without a VPN.
- It can open **https://app.nls.ac.in** (normal outbound internet).
- It runs Windows 10/11/Server or Linux.
- It has **Python 3.10 or newer**.

The agent does not need a database, a web server or any inbound firewall rule.

## Files in this folder

| File | Purpose |
|---|---|
| `rfid_sync_agent.py` | The agent itself |
| `config.example.ini` | Settings template. Copy it to `config.ini` and fill it in |
| `requirements.txt` | Python packages it needs |
| `mssql_openssl.cnf`, `mssql_gnutls_override.conf` | Linux only. Allow the old TLS 1.0 that SQL Server 2014 uses |

The agent creates these files itself while running:
- `state.json` stores the last punch ID sent.
- `agent.log` is the activity log. It rotates automatically and keeps up to 30 MB.

---

## Windows setup

1. **Install Python** from https://www.python.org/downloads/. In the installer, tick
   **"Add python.exe to PATH"** and choose **"Install for all users"**.
2. **Copy this folder** to `C:\slcm_rfid_sync\`.
3. **Install the packages.** Open Command Prompt **as Administrator** and run:
   ```
   cd C:\slcm_rfid_sync
   py -m pip install -r requirements.txt
   ```
4. **Configure.** Copy `config.example.ini` to `config.ini`, open it in Notepad and fill in:
   - `[sql] password`, the SQL Server password
   - `[live] api_key` / `api_secret`, which SLCM gives you (see "API user" below)
5. **Test.** Both lines must say OK:
   ```
   py rfid_sync_agent.py --test
   ```
   Expected output:
   ```
   SQL Server OK: Microsoft SQL Server 2014 ...
   Live site OK: logged in as ..., highest source_log_id ...
   ```
6. **Schedule it to run every minute.** In the same Administrator Command Prompt:
   ```
   for /f "delims=" %p in ('py -c "import sys;print(sys.executable)"') do set PY=%p
   schtasks /Create /TN "SLCM RFID Sync" /RU SYSTEM /RL HIGHEST /SC MINUTE /MO 1 /F /TR "\"%PY%\" C:\slcm_rfid_sync\rfid_sync_agent.py --once"
   ```
   It runs in the background as SYSTEM, even when nobody is logged in.
7. **Check it after 2 minutes** by opening `C:\slcm_rfid_sync\agent.log`. You should see
   `First run: starting after the live site's highest source_log_id ...` and then `Cycle: ...` lines
   whenever new punches arrive.

The Windows built-in "SQL Server" ODBC driver is used automatically, so no driver install is needed.

## Linux setup (Ubuntu/Debian)

```bash
sudo apt install -y python3 python3-venv unixodbc unixodbc-dev tdsodbc
sudo mkdir -p /opt/slcm_rfid_sync && sudo cp -r ./* /opt/slcm_rfid_sync/
cd /opt/slcm_rfid_sync
sudo python3 -m venv venv && sudo venv/bin/pip install -r requirements.txt
sudo cp config.example.ini config.ini && sudo nano config.ini      # fill in passwords
sudo chmod 600 config.ini
sudo venv/bin/python rfid_sync_agent.py --test
```

Then run it every minute with cron (`sudo crontab -e`):
```
* * * * * /opt/slcm_rfid_sync/venv/bin/python /opt/slcm_rfid_sync/rfid_sync_agent.py --once >/dev/null 2>&1
```

---

## API user (done by the SLCM team on the live site)

1. On app.nls.ac.in, create a user such as `rfid-agent@...` with permission to **create**
   *RFID SQL Punch Log* and *Attendance Log*, and to **read** *Student Master* and *RFID Device*.
2. Open that user and go to **Settings → API Access → Generate Keys**. Put the key and the secret into `config.ini`.

Using a dedicated user, rather than a personal or Administrator account, means the key can be
revoked at any time without affecting anyone's login.

## After it is running

- In SLCM, under **RFID Configuration**, untick **Enable** on any other machine that was syncing
  before (for example a developer laptop). That avoids doing the same work twice. Duplicates are
  rejected safely either way.
- Punches show up in **RFID SQL Punch Log** and **Attendance Log** on the live site within about a minute.

## Useful commands

| Command | What it does |
|---|---|
| `py rfid_sync_agent.py --test` | Check both connections |
| `py rfid_sync_agent.py --once` | Sync now |
| `py rfid_sync_agent.py --once --dry-run` | Show what would be sent, without sending anything |
| `py rfid_sync_agent.py --once --dry-run --from-id 3576600` | Same, but starting after a given SQL ID |

To re-send from an earlier point, stop the task, edit `last_log_id` in `state.json`, and start the
task again. Already-sent punches are skipped automatically.

## Troubleshooting

| Symptom in `agent.log` | Fix |
|---|---|
| `SQL Server FAILED ... Unable to connect` | This machine cannot reach 192.168.10.10:1433. Check the network and firewall |
| `SQL Server FAILED ... SSL / TLS / encryption` (Windows) | Windows has TLS 1.0 turned off. Set `driver = SQL Server` in config.ini, or ask IT to allow TLS 1.0 for this machine |
| `Live site FAILED ... HTTP 401/403` | The API key/secret is wrong, or the API user lacks permission |
| `Another copy is already running` | Normal when a sync takes longer than a minute. The next run continues |
| `Stopped early, will retry next cycle` | Temporary network or site issue. Nothing is lost; it retries automatically |

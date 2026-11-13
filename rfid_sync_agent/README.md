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

---
---

# NEW: Student Map (RFID) update

*Everything above this line is the original guide and is unchanged. This section covers only what the
Student Map (RFID) update adds.*

## What is new

The agent now also sends the **card list** (every card code on the device) to the live site, **every 6
hours**, automatically. The live **Student Map (RFID)** screen uses this list to link cards to students,
because the live site cannot read the campus SQL Server itself.

- **Swipes work exactly as before.** Nothing changes in how swipes are sent.
- **Only one file changes:** `rfid_sync_agent.py`.
- **config.ini and state.json stay as they are.** They work with both the old and the new version.

**Order matters:** the SLCM team deploys the update to the live site first (Part 2 below), then IT
upgrades the agent (Part 3 below).

---

## Part 1: What the update adds

| Added | What it does |
|---|---|
| `--cards` command | Sends the card list to the live site now |
| Automatic card list | Sent every 6 hours by the scheduled task, with nothing to set up |
| `--test` | Now also checks the card list, as a third line |
| Retry wait | If sending the card list fails, the agent waits 30 minutes before trying again. Swipes are not affected |
| Lock wait | `--cards` waits up to 3 minutes if a scheduled sync is running at that moment |
| `cards_every_hours` | Optional setting in config.ini. The default is 6, so you do not need to add it |

---

## Part 2: Live site settings (SLCM team, done first)

### Step 2.1: Deploy the SLCM update

1. Commit and push the SLCM changes.
2. On the **Frappe Cloud** dashboard, open the bench group for app.nls.ac.in and click **Deploy**, with
   **slcm** ticked.
3. Wait for **Success**, then press **Ctrl+Shift+R** in the browser.

### Step 2.2: Open RFID SQL Agent Settings

On app.nls.ac.in, in the sidebar, click **RFID Management → RFID Configuration**.

The page has these tabs: **General · SQL Server · Watermark · Failure Email · Remote Sync · Student Map**.

### Step 2.3: Student Map tab

Click the **Student Map** tab (the last tab) and set:

| Field | Value |
|---|---|
| Names Table / View | iclock_trans_ajim |
| Card Code Column | emp_code |
| Name Column(s) | leave empty |
| Match To Student Master Field | registration_id |
| Ignore Case And Spaces When Matching | ticked |

Name Column(s) stays empty because the campus database has no student names.

### Step 2.4: General tab

Click the **General** tab (the first tab). At the top left, **untick "Enable RFID SQL Agent"**.

The live site cannot reach the SQL Server itself, so leaving it ticked only produces connection errors.
Swipes keep coming from this agent.

### Step 2.5: Save

Click **Save** (top right). The **Enabled** badge next to the page title disappears.

The API user does not need any change. The card list uses the same permission the swipes already use.

---

## Part 3: Upgrade the installed agent (IT, Windows, about 10 minutes)

### Step 3.1: Open an Administrator Command Prompt

1. Click **Start**.
2. Type **cmd**.
3. Right-click **Command Prompt** and choose **Run as administrator**.

Type every command below in this window.

### Step 3.2: Find the install folder

Run:

```bat
schtasks /Query /TN "SLCM RFID Sync" /V /FO LIST | findstr /C:"Task To Run"
```

You will see a line like this:

```text
Task To Run:   "C:\...\python.exe" C:\slcm_rfid_sync\rfid_sync_agent.py --once
```

The folder before `rfid_sync_agent.py` (here **C:\slcm_rfid_sync**) is the **install folder**. If yours is
different, use your folder in the steps below.

### Step 3.3: Pause the scheduled sync

Run:

```bat
schtasks /Change /TN "SLCM RFID Sync" /DISABLE
```

Expected: `SUCCESS: The parameters of scheduled task "SLCM RFID Sync" have been changed.`

### Step 3.4: Replace one file

Copy the new **rfid_sync_agent.py** into the install folder and choose **Replace**.

**Do NOT replace or delete these files in the install folder:**

- **config.ini** holds the SQL password and the API key.
- **state.json** records how far the swipes have been sent. Losing it can re-send or skip swipes.
- **agent.log** is the activity log.

### Step 3.5: Go to the install folder

Run:

```bat
cd /d C:\slcm_rfid_sync
```

### Step 3.6: Test the connections

Run:

```bat
py rfid_sync_agent.py --test
```

Expected, three lines:

```text
SQL Server OK: Microsoft SQL Server 2014 ...
Live site OK: logged in as ..., highest source_log_id ...
Card list OK: Student Map reads iclock_trans_ajim.emp_code (no names)
```

- **First two lines say OK:** swipes are fine. Continue.
- **Third line says "Card list WARNING":** the live site does not have the update yet. Swipes are **not**
  affected. Finish Part 2, then run this step again.

### Step 3.7: Send the card list once

Run:

```bat
py rfid_sync_agent.py --cards
```

Expected (the numbers will vary):

```text
Card list sent: 2858 read from iclock_trans_ajim, 2858 stored on the live site
```

### Step 3.8: Resume the scheduled sync (do not skip this)

Run:

```bat
schtasks /Change /TN "SLCM RFID Sync" /ENABLE
```

Expected: `SUCCESS: The parameters of scheduled task "SLCM RFID Sync" have been changed.`

### Step 3.9: Keep the machine awake

Open **Settings → System → Power** and set **Sleep when plugged in** to **Never**.

### Upgrade on Linux instead

1. Run `sudo crontab -e` and put `#` in front of the agent line, which pauses it.
2. Replace only **/opt/slcm_rfid_sync/rfid_sync_agent.py**.
3. Test and send the card list:

```bash
cd /opt/slcm_rfid_sync
sudo venv/bin/python rfid_sync_agent.py --test
sudo venv/bin/python rfid_sync_agent.py --cards
```

4. Run `sudo crontab -e` again and remove the `#`, which resumes it.

### Undo the upgrade (only if needed)

1. Put the old **rfid_sync_agent.py** back in the install folder.
2. Run the command from Step 3.8.

**config.ini** and **state.json** work with both versions.

---

## Part 4: Check that it is working

### On the live site

- **RFID Management → RFID Agent Dashboard** shows the status **"Running · campus agent"** and the line
  *"Student Map card list from the campus agent: sent … (N cards)"*.
- **RFID Card Management → Student Map (RFID)** shows a green banner: *"Card list sent by the campus agent
  on … (N records)"*. Pick filters if needed (several values are allowed), check the tiles, and click
  **Map N student(s)**.
- After mapping, swipes show student names, and past swipes are linked to the right students
  automatically.

### On the campus machine

**agent.log** in the install folder shows `Card list sent ...` about every 6 hours, as well as the usual
`Cycle: ...` lines.

---

## Part 5: New commands

Run these in the install folder. On Linux, use **sudo venv/bin/python** instead of **py**.

Send the card list now (if a scheduled sync is running, it waits up to 3 minutes):

```bat
py rfid_sync_agent.py --cards
```

Read the card list and show a sample, without sending anything:

```bat
py rfid_sync_agent.py --cards --dry-run
```

Send a fresh card list:

- after changing the Student Map settings on live
- before a large mapping run

---

## Part 6: New troubleshooting

### "Card list WARNING" or "Card list not sent ... HTTP 417 Failed to get method"

The live site does not have the update yet (Step 2.1). Swipes are not affected, and the agent retries every
30 minutes on its own.

### "Card list not sent ... HTTP 403"

The API user needs permission to create *RFID SQL Punch Log*. This is the same permission the swipes use.

### Live Student Map says "Card list is out of date"

The Student Map settings were changed on live. Run `py rfid_sync_agent.py --cards`.

### Live Student Map says "the campus agent has not sent a card list yet"

Run Step 3.7 on the campus machine, then open Student Map again.

### Live Student Map banner is amber ("more than a day old")

The scheduled task is not sending the list. Check that the task is enabled (Step 3.8), that the machine is
awake, and read agent.log.

### Live dashboard says "Campus agent · no recent swipes" during college hours

The campus machine is off, asleep or offline. Check the machine, then read agent.log.

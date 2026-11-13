# SLCM RFID Sync Agent

## 1. What this program does

This program runs on a campus machine. It sends two things to the live SLCM site
(https://app.nls.ac.in):

- **Swipes**: new RFID punches, every minute. Live uses them for attendance.
- **Card list**: every card code on the device, every 6 hours. The live **Student Map (RFID)** screen
  uses it to link cards to students.

```text
Campus SQL Server (192.168.10.10, database etpdb)
        |  read on the campus network
This agent (on an always-on campus machine)
        |  HTTPS, outbound only
Live SLCM site (app.nls.ac.in on Frappe Cloud)
```

**Why it is needed:** the live site is hosted outside campus and cannot reach 192.168.10.10. Being on the
campus Wi-Fi in a browser does not change that, because the connection would be made by the server, not
the browser. The agent sits inside campus and pushes the data out.

---

## 2. Which part do I need?

- **The agent is already running and you got a new `rfid_sync_agent.py`:** go to **Part 3: Upgrade**.
- **Installing on a Windows machine for the first time:** go to **Part 4: New install on Windows**.
- **Installing on a Linux machine for the first time:** go to **Part 5: New install on Linux**.
- **You are on the SLCM team and setting up the live site:** go to **Part 6: Live site settings**.

**Order matters:** the SLCM team deploys the update to the live site first (Part 6), and then IT upgrades
the agent (Part 3). Swipes work either way; the card list only works once live has the update.

---

## 3. Upgrade an installed agent (Windows)

About 10 minutes. Swipes keep working exactly as before. **Only one file changes.**

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
  affected. Ask the SLCM team to finish Part 6, then run this step again.

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

### Undo the upgrade (only if needed)

1. Put the old **rfid_sync_agent.py** back in the install folder.
2. Run the command from Step 3.8.

**config.ini** and **state.json** work with both the old and the new version.

---

## 4. New install on Windows

### What the machine needs

- It is **always on**, with sleep set to *Never*.
- It is **on the campus network** and can reach 192.168.10.10 on port 1433 **without a VPN**.
- It can open **https://app.nls.ac.in**. No inbound firewall rule is needed.
- It runs Windows 10, 11 or Server, with **Python 3.10 or newer**.

### Step 4.1: Install Python

Download Python from https://www.python.org/downloads/ and run the installer. In the installer:

- Tick **Add python.exe to PATH**.
- Choose **Install for all users**.

### Step 4.2: Copy the folder

Copy this **rfid_sync_agent** folder to **C:\slcm_rfid_sync**.

### Step 4.3: Install the packages

Open an Administrator Command Prompt (see Step 3.1) and run:

```bat
cd /d C:\slcm_rfid_sync
py -m pip install -r requirements.txt
```

### Step 4.4: Create the settings file

Run:

```bat
copy config.example.ini config.ini
notepad config.ini
```

In Notepad, fill in these three values, then save and close:

- **password** (under `[sql]`): the SQL Server password
- **api_key** (under `[live]`): from the SLCM team (Part 6)
- **api_secret** (under `[live]`): from the SLCM team (Part 6)

Leave every other value as it is.

### Step 4.5: Test the connections

Run:

```bat
py rfid_sync_agent.py --test
```

The expected output is the same as in Step 3.6.

### Step 4.6: Send the card list

Run:

```bat
py rfid_sync_agent.py --cards
```

### Step 4.7: Schedule it to run every minute

Run these two lines, one after the other:

```bat
for /f "delims=" %p in ('py -c "import sys;print(sys.executable)"') do set PY=%p
```

```bat
schtasks /Create /TN "SLCM RFID Sync" /RU SYSTEM /RL HIGHEST /SC MINUTE /MO 1 /F /TR "\"%PY%\" C:\slcm_rfid_sync\rfid_sync_agent.py --once"
```

The task runs in the background as SYSTEM, even when nobody is logged in, and it starts again after a
restart.

### Step 4.8: Check after 2 minutes

Open **C:\slcm_rfid_sync\agent.log** in Notepad. You should see:

```text
First run: starting after the live site's highest source_log_id ...
Cycle: fetched=... pushed=... watermark ... -> ...
```

The built-in Windows "SQL Server" ODBC driver is used automatically, so no driver install is needed.

---

## 5. New install on Linux (Ubuntu / Debian)

### Step 5.1: Install system packages

```bash
sudo apt install -y python3 python3-venv unixodbc unixodbc-dev tdsodbc
```

### Step 5.2: Copy the folder and install Python packages

Run these from inside this folder:

```bash
sudo mkdir -p /opt/slcm_rfid_sync
sudo cp -r ./* /opt/slcm_rfid_sync/
cd /opt/slcm_rfid_sync
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt
```

### Step 5.3: Create the settings file

```bash
sudo cp config.example.ini config.ini
sudo nano config.ini
sudo chmod 600 config.ini
```

Fill in **password**, **api_key** and **api_secret**, as in Step 4.4.

### Step 5.4: Test and send the card list

```bash
sudo venv/bin/python rfid_sync_agent.py --test
sudo venv/bin/python rfid_sync_agent.py --cards
```

### Step 5.5: Run it every minute

Open the root crontab:

```bash
sudo crontab -e
```

Add this line, then save:

```text
* * * * * /opt/slcm_rfid_sync/venv/bin/python /opt/slcm_rfid_sync/rfid_sync_agent.py --once >/dev/null 2>&1
```

### Upgrade on Linux

1. Run `sudo crontab -e` and put `#` in front of the agent line, which pauses it.
2. Replace only **/opt/slcm_rfid_sync/rfid_sync_agent.py**.
3. Run the two commands from Step 5.4.
4. Run `sudo crontab -e` again and remove the `#`, which resumes it.

---

## 6. Live site settings (SLCM team)

This is done once on **app.nls.ac.in**.

### Step 6.1: Deploy the SLCM update

1. Commit and push the SLCM changes.
2. On the **Frappe Cloud** dashboard, open the bench group for app.nls.ac.in and click **Deploy**, with
   **slcm** ticked.
3. Wait for **Success**, then press **Ctrl+Shift+R** in the browser.

### Step 6.2: API user (skip if the agent is already sending swipes)

1. Go to **User → New User** and create, for example, **rfid-agent@nls.ac.in**.
2. Give it **AAD Staff** or **System Manager**. It needs to create *RFID SQL Punch Log* and
   *Attendance Log*, and to read *Student Master* and *RFID Device*. The card list uses the same
   permission.
3. Open the user and go to **Settings → API Access → Generate Keys**.
4. Give the key and the secret to IT for config.ini. Send them separately, never in the same email as this
   folder.

Use a dedicated user, not a personal or Administrator account, so the key can be revoked without affecting
anyone's login.

### Step 6.3: Open RFID SQL Agent Settings

In the sidebar, click **RFID Management → RFID Configuration**.

The page has these tabs: **General · SQL Server · Watermark · Failure Email · Remote Sync · Student Map**.

### Step 6.4: Student Map tab

Click the **Student Map** tab (the last tab) and set:

| Field | Value |
|---|---|
| Names Table / View | iclock_trans_ajim |
| Card Code Column | emp_code |
| Name Column(s) | leave empty |
| Match To Student Master Field | registration_id |
| Ignore Case And Spaces When Matching | ticked |

Name Column(s) stays empty because the campus database has no student names.

### Step 6.5: General tab

Click the **General** tab (the first tab). At the top left, **untick "Enable RFID SQL Agent"**.

The live site cannot reach the SQL Server itself, so leaving it ticked only produces connection errors.
Swipes keep coming from the campus agent.

### Step 6.6: Save

Click **Save** (top right). The **Enabled** badge next to the page title disappears.

---

## 7. Check that it is working

### On the live site

- **RFID Management → RFID Agent Dashboard** shows the status **"Running · campus agent"** and the line
  *"Student Map card list from the campus agent: sent … (N cards)"*.
- **RFID Card Management → Student Map (RFID)** shows a green banner: *"Card list sent by the campus agent
  on … (N records)"*.
- **RFID SQL Punch Log** shows new swipes within about a minute.

### On the campus machine

**agent.log** in the install folder shows:

- `Cycle: ...` lines whenever swipes arrive
- `Card list sent ...` about every 6 hours

### When to send the card list by hand

Run `py rfid_sync_agent.py --cards` in the install folder:

- after changing the Student Map settings on live
- before a large mapping run, so the list is fresh

---

## 8. Command reference

Run these in the install folder. On Linux, use **sudo venv/bin/python** instead of **py**.

Check the SQL Server, the live site and the card list (changes nothing):

```bat
py rfid_sync_agent.py --test
```

Send the card list now (if a scheduled sync is running, it waits up to 3 minutes):

```bat
py rfid_sync_agent.py --cards
```

Read the card list and show a sample, without sending:

```bat
py rfid_sync_agent.py --cards --dry-run
```

Send new swipes now:

```bat
py rfid_sync_agent.py --once
```

Show which swipes would be sent, without sending:

```bat
py rfid_sync_agent.py --once --dry-run
```

Same, starting after a given SQL ID:

```bat
py rfid_sync_agent.py --once --dry-run --from-id 3576600
```

### Re-send swipes from an earlier point

1. Pause the task (Step 3.3).
2. In **state.json**, set **last_log_id** to the ID to start after.
3. Resume the task (Step 3.8).

Swipes already on live are skipped automatically.

---

## 9. Files in this folder

| File | What it is |
|---|---|
| rfid_sync_agent.py | The agent |
| config.example.ini | Settings template. Copy it to config.ini and fill it in |
| requirements.txt | Python packages it needs |
| mssql_openssl.cnf | Linux only. Allows the old TLS 1.0 that SQL Server 2014 uses |
| mssql_gnutls_override.conf | Linux only. Same purpose |
| config.ini | Created by you. Holds the passwords. Keep it private; never email it |
| state.json | Created by the agent. How far swipes have been sent, and when the card list was last sent |
| agent.log | Created by the agent. Activity log; rotates automatically, up to 30 MB |

---

## 10. Troubleshooting

### "SQL Server FAILED ... Unable to connect"

This machine cannot reach 192.168.10.10 on port 1433. Check the network cable or Wi-Fi, and the firewall.

### "SQL Server FAILED ... SSL / TLS / encryption" (Windows)

Windows has TLS 1.0 turned off. Add `driver = SQL Server` under `[sql]` in config.ini, or allow TLS 1.0 on
this machine.

### "Live site FAILED ... HTTP 401" or "HTTP 403"

The API key or secret in config.ini is wrong, or the API user lacks permission (Step 6.2).

### "Card list WARNING" or "Card list not sent ... HTTP 417 Failed to get method"

The live site does not have the update yet (Step 6.1). Swipes are not affected, and the agent retries every
30 minutes on its own.

### "Card list not sent ... HTTP 403"

The API user needs permission to create *RFID SQL Punch Log* (Step 6.2).

### Live Student Map says "Card list is out of date"

The Student Map settings were changed on live. Run `py rfid_sync_agent.py --cards`.

### "Another copy is already running"

This is normal when one sync takes longer than a minute. The next run continues.

### "Stopped early, will retry next cycle"

A temporary network or site problem. Nothing is lost; it retries automatically.

### Live dashboard says "Campus agent · no recent swipes" during college hours

The campus machine is off, asleep or offline. Check the machine, then read agent.log.

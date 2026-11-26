[← Uniquad User Manual](README.md)

# 7. Attendance

Attendance is marked per class session, either by hand or from RFID card swipes. The system keeps a running **Attendance Summary** per student and course and flags whether the student is **Eligible for Exam**. Shortages are handled through condonation or FA/MFA. Everything is under the **Attendance** workspace (`/desk/attendance`).

**Desk path:** Desk home → **Academics** → **Attendance**.

> *Screenshot: Attendance workspace* (see the online manual)

| Role | What they do |
| --- | --- |
| slcm\_Faculty | Marks attendance, activates RFID for a class (from the faculty portal), sees reports for own courses |
| slcm\_Programme Chair | Fixes unmatched RFID swipes, sees all reports, second-level condonation approver |
| AAD, Programme Chair | Attendance settings and condonation decisions |
| System Manager | RFID devices, SQL agent, everything else |

## 7.1 One-time setup: Attendance Settings

Open `/desk/attendance-settings`:

- **General**: **Minimum Attendance Percentage**, **Attendance Lock Days**, **Late Entry Buffer (Minutes)**.
- **Course Hours**: hours for core and elective courses and office hours.
- **Condonation**: **Allow Condonation**, **Minimum Attendance for Condonation**, and the **Level One AAD Authority** and **Level Two Authority** tables (approver, programme, year, batch).
- **Parent Absence Alert**: emails parents when a student has not swiped for a set number of hours.
- **RFID Configuration**: **Enable RFID Attendance**, **RFID Swipe Mode**, **RFID Active Window (Minutes)**.

> *Screenshot: Attendance Settings* (see the online manual)

## 7.2 Mark attendance by hand

1. Open **Student Attendance Tool** (`/desk/student-attendance-tool`).
2. Choose **Based On**: Course Schedule, Time Table or Office Hours, then pick the session. **Course Offering** and **Date** fill in.
3. The student list loads. Tick the students who are present (**Check all** / **Uncheck all** help). A counter shows Total, Present and Absent.
4. Click **Mark Attendance** and confirm. The message "Attendance marked" appears.

> *Screenshot: Student Attendance Tool* (see the online manual)

> *Screenshot: Attendance Session* (see the online manual)

> *Screenshot: A Student Attendance record* (see the online manual)

Attendance cannot be marked for future dates. Faculty can also mark attendance from the faculty portal (section 15.2).

## 7.3 RFID attendance

1. Card readers record swipes. The **RFID SQL Agent** pulls them in regularly (status on `/desk/rfid-sql-agent-dashboard`; **Run Now** pulls immediately).
2. At the start of class, the faculty member clicks **Activate RFID** in the faculty portal. Swipes in that room during the active window count as present.
3. Matched swipes create attendance automatically. Unmatched swipes wait on the **Attendance Sync** page.

**Assign RFID cards** on **RFID Card Management** (`/desk/rfid-mapping`):

1. One card: on the **Unassigned Cards** tab click **Assign Student**, choose the **Student**, click **Assign and Save**.
2. Many cards: click **Export for Vendor** to download the student list, have the vendor fill `rfid_uid`, then click **Bulk Import CSV**, upload the file and click **Import**.

> *Screenshot: RFID Card Management* (see the online manual)

**Fix unmatched swipes** on **Attendance Sync** (`/desk/attendance-sync`):

1. Filter by **Reason** (for example Unmatched - No Session or Unmatched - Unknown Card), dates, programme or batch.
2. For one row click **View**, then **Sync**. If asked, pick the card owner or the **Attendance Session**, then confirm.
3. For many, click **Bulk Sync**, enter **From Date** and **To Date** (optionally time and venue) and click **Run Bulk Sync**. Only swipes that match exactly one session are synced.

> *Screenshot: Attendance Sync: unmatched swipes* (see the online manual)

> *Screenshot: An Attendance Log (swipe) record* (see the online manual)

## 7.4 View attendance

| Screen | Address | Use it to |
| --- | --- | --- |
| Attendance Quick View | `/desk/attendance-quick-view` | Search records by programme, course, dates, section or status, then **Search** |
| Attendance Summary Report | `/desk/attendance-summary-report` | See each student's **Attendance %** against the minimum; **Summary**, **Weekly**, **Monthly** and **Daily** tabs; **Export CSV** |
| Student Attendance | `/desk/student-attendance` | Individual records (Present, Absent, Late, Excused, OD; source Manual or RFID) |
| Comprehensive Attendance Report | Search "Comprehensive Attendance Report" | Report by programme, batch, section, course and source |
| RFID Attendance Report | Search "RFID Attendance Report" | Daily, weekly or monthly swipe report |

> *Screenshot: Attendance Quick View* (see the online manual)

> *Screenshot: Attendance Summary Report* (see the online manual)

> *Screenshot: Attendance Summary record with Eligible for Exam* (see the online manual)

Tick **Include Condonation Report** on the summary report to add condonation hours and approvers. Faculty see only their own courses.

## 7.5 Condonation (two-level approval)

1. The student (or staff) creates a **Student Attendance Condonation** with **Student**, **Course Offering**, **Absence From/To Date**, sessions and hours to condone, **Reason** and **Proof Document**, and clicks **Submit**.
2. An AAD approver is assigned automatically and emailed. The status is **Pending**.
3. The AAD approver opens it and uses **AAD Decision** → **May Be Approve** (with optional remarks) or **Reject** (with a reason).
4. If recommended, a Programme Chair approver is assigned. They use **Programme Chair Decision** → **Approve** or **Reject**.
5. On **Approved**, the student is emailed and the condoned hours count towards attendance.

> *Screenshot: New Condonation request* (see the online manual)

> *Screenshot: A Pending condonation* (see the online manual)

Only the assigned approver sees the decision buttons. Requests still open after the term ends are auto-rejected if attendance is below the condonation minimum.

## 7.6 FA/MFA and leave

- **FA / MFA Application** (`/desk/fa-mfa-application`): fill **Student**, **Course Offering**, **Examination Date**, **Application Type** (FA or MFA), **Reason**, **Proof Document**. Set **Status** to Approved with **Granted Hours**, then **Submit**. Granted hours add to attendance.
- **Student Leave Applications** (`/desk/student-leave-applications`): students send dates and reason; an Academic Admin sets **Status** and **Admin Remarks**.

> *Screenshot: New FA / MFA Application* (see the online manual)

# Attendance Module — Workflow & Testing Guide

**Last Updated**: 2026-05-23  
**App**: `slcm`  
**Module**: Attendance

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Key DocTypes & Their Roles](#2-key-doctypes--their-roles)
3. [Attendance Percentage Formula](#3-attendance-percentage-formula)
4. [Student Attendance Tool — Based On Types](#4-student-attendance-tool--based-on-types)
5. [Part 1 — Lecture / Tutorial Attendance](#5-part-1--lecture--tutorial-attendance)
6. [Part 2 — Office Hour Attendance](#6-part-2--office-hour-attendance)
7. [Part 3 — RFID-Based Attendance](#7-part-3--rfid-based-attendance)
8. [Part 4 — Condonation Workflow](#8-part-4--condonation-workflow)
9. [Part 5 — FA Application (First Attempt)](#9-part-5--fa-application-first-attempt)
10. [Part 6 — MFA Application (Medical First Attempt)](#10-part-6--mfa-application-medical-first-attempt)
11. [Roles & Permissions](#11-roles--permissions)
12. [Quick Test Checklist](#12-quick-test-checklist)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. System Overview

The attendance system tracks student presence across **Lectures**, **Tutorials**, and **Office Hours**. It automatically calculates each student's attendance percentage per course offering and determines their **exam eligibility** (minimum 75% by default).

### End-to-End Data Flow

```
RFID Swipe ──► Attendance Log ──► rfid_processor ──► Student Attendance
                                                            │
Manual Entry via Student Attendance Tool ──────────────────┤
                                                            │
                                                   trigger_recalculation()
                                                            │
                                              attendance_calculator.py
                                                            │
                                              Attendance Summary
                                         (% calculated + Eligible for Exam flag)
```

### Key Source Files

| File | Purpose |
|---|---|
| `slcm/api/bulk_attendance.py` | Main API called by Student Attendance Tool |
| `slcm/utils/attendance_calculator.py` | Central calculation engine |
| `slcm/utils/rfid_processor.py` | RFID log processing logic |
| `slcm/doctype/student_attendance/student_attendance.py` | Student Attendance controller |
| `slcm/doctype/attendance_session/attendance_session.py` | Session container controller |
| `slcm/doctype/fa_mfa_application/fa_mfa_application.py` | FA/MFA validation & workflow |
| `slcm/doctype/student_attendance_condonation/student_attendance_condonation.py` | Condonation workflow |

---

## 2. Key DocTypes & Their Roles

| DocType | Role |
|---|---|
| **Student Attendance** | Atomic record — one row per student per session. Stores status (Present/Absent/Late/Excused), session type, hours counted |
| **Attendance Session** | Container for a class session. Created automatically by the tool. Tracks present/absent counts per session |
| **Attendance Log** | Raw RFID swipe record. Staging area before processing |
| **Attendance Summary** | Aggregated scorecard per student per course offering. Stores final %, eligibility flag, condonation list, FA/MFA list |
| **Student Attendance Condonation** | Application to add condoned hours for missed classes |
| **FA MFA Application** | Application to override exam eligibility despite low attendance |
| **Attendance Settings** | Global config — minimum %, lock days, FA/MFA toggle, condonation minimum % |
| **Attendance Edit Log** | Tamper-evident audit trail for any status changes |
| **Attendance Period** | Time slot definitions (Period 1: 09:00–10:00, etc.) |

---

## 3. Attendance Percentage Formula

```
Numerator   = Lecture Hours Attended
            + Tutorial Hours Attended
            + Office Hours (actual duration visited)
            + Condonation Hours (approved applications)
            + FA/MFA Hours (approved applications)

Denominator = Sum of duration_hours of all Conducted Attendance Sessions
              (Lecture + Tutorial ONLY — Office Hours do NOT add to denominator)

Percentage  = (Numerator / Denominator) × 100

Eligible    = Percentage >= minimum_attendance_percentage (default 75%)
              OR has an Approved + Submitted FA/MFA Application
```

**Example:**
```
Total Lecture Hours conducted:   10
Student attended:                 7  (Lectures)
Office Hours visited:             1.5
Condonation approved:             0
FA/MFA:                           None

Numerator  = 7 + 1.5 = 8.5
Denominator = 10
Percentage  = 85%  → Eligible: YES
```

---

## 4. Student Attendance Tool — Based On Types

The **Student Attendance Tool** is the primary UI for marking attendance. It has **4 modes**. There is NO "Attendance Session" selector — the tool **auto-creates an Attendance Session** in the background.

| Based On | When to Use | Session Type Created |
|---|---|---|
| **Class Schedule** | Daily timetable-based attendance (most common) | Lecture (uses actual class times) |
| **Student Group** | Ad-hoc attendance not tied to a schedule | Lecture (defaults to 09:00–10:00) |
| **Office Hours** | Faculty office hour attendance tracking | Office Hour |

### What Happens When You Click "Mark Attendance"

The tool calls `slcm.api.bulk_attendance.mark_attendance` which:

1. Determines **Program**, **Course**, **Course Offering** from the selected entity
2. Finds or creates an **Attendance Session** for that date + course offering
3. Creates or updates `Student Attendance` records (`source = Manual`)
4. Updates `Attendance Session` summary counts (`present_count`, `absent_count`)
5. Triggers `Attendance Summary` recalculation for all affected students

---

## 5. Part 1 — Lecture / Tutorial Attendance

Lectures and Tutorials form the **denominator** of the attendance formula. Every conducted session adds to Total Class Hours.

### 5.1 Using Class Schedule (Recommended Daily Method)

**Pre-requisites:**
- A `Class Schedule` record exists for the course (recurring timetable entry)
- Students are in a `Student Group` linked to the Class Schedule

**Steps:**
1. Go to **Attendance** workspace → **Student Attendance Tool**
2. `Based On` → `Class Schedule`
3. Select the `Class Schedule` (e.g., "Constitutional Law — Section A")
4. `Date` auto-fills — for recurring schedules, defaults to today; change if marking past attendance
5. Student list loads with checkboxes — already-present students are pre-checked
6. Tick/untick students
7. Click **Mark Attendance** → confirm the Present/Absent counts
8. Green alert "Attendance marked" confirms success

**Verify:**
- Go to **Student Attendance** list → filter by date and course → records should show `source = Manual`
- Go to **Attendance Session** list → a session for that date/course should exist with `session_status = Conducted`
- Go to **Attendance Summary** for a student → `attendance_percentage` updated

---

### 5.2 Using Student Group (Ad-hoc Method)

Use when there is no Class Schedule entry (e.g., extra class, makeup session).

**Steps:**
1. `Based On` → `Student Group`
2. `Group Based On` → select group type (Batch / Course / Section)
3. `Student Group` → select the group
4. `Date` → manually enter the date (defaults to today)
5. Mark students → Click **Mark Attendance**

**Note:** The Attendance Session created will have default times 09:00–10:00 and `duration_hours = 1.0`. If the actual class was longer/shorter, manually update the Attendance Session afterwards so the hours are correct.

---

### 5.3 Individual Entry (Single Student)

Use only for corrections or one-off entries.

**Steps:**
1. Go to **Student Attendance** → New
2. Fill in:
   - `Student`
   - `Attendance Date`
   - `Based On` → Student Group or Class Schedule
   - `Student Group` or `Class Schedule`
   - `Course Offer`
   - `Session Type` → Lecture or Tutorial
   - `Status` → Present / Absent / Late / Excused
   - `Hours Counted` → e.g., `1.0`
3. Save

---

## 6. Part 2 — Office Hour Attendance

Office Hours are **bonus time**. They add to attended hours (numerator) but **do NOT increase Total Class Hours (denominator)**. A student can use office hours to compensate for missed lectures.

### 6.1 Using the Tool (Office Hours Group)

**Pre-requisites:**
- An `Office Hours Group` record exists with the instructor, course, and academic year/term
- Students are listed in the group

**Steps:**
1. **Student Attendance Tool** → `Based On` → `Office Hours`
2. Select `Office Hours Group`
3. Mark students who attended → **Mark Attendance**

**What is created:**
- `Student Attendance` with `session_type = Office Hour`
- `Attendance Session` with `session_type = Office Hour`
- `hours_counted` defaults to the session duration (or 1.0 if time not specified)

### 6.2 Individual Entry (Manual)

Use when you need to specify a custom duration (e.g., student stayed for 45 mins).

**Steps:**
1. **Student Attendance** → New
2. Fill in:
   - `Student`
   - `Session Type` → `Office Hour`
   - `Status` → Present
   - `Hours Counted` → enter actual duration (e.g., `0.75` for 45 mins)
   - `Course Offer` → the linked course offering
   - `Attendance Date`
3. Save

**Verify:**
- Go to **Attendance Summary** → `total_office_hours` increases
- `attended_classes` (numerator) increases
- `total_class_hours` (denominator) is **unchanged**

---

## 7. Part 3 — RFID-Based Attendance

RFID is automated hardware-triggered attendance. Raw swipe data enters `Attendance Log` and is processed by `rfid_processor.py`.

> **Current Status**: Auto-processing on insert is **disabled** (commented out in `attendance_log.py`). Processing must be triggered manually or via the Frappe Scheduler.

### 7.1 RFID Processing Flow

```
Student taps card at reader
        │
        ▼
Attendance Log created
  rfid_uid = card UID
  device_id = reader ID
  swipe_time = timestamp
  processed = 0
        │
        ▼
Run batch processor (manual or scheduled)
        │
        ▼
rfid_processor.py:
  1. Debounce: ignore if same UID swiped within last 10 minutes
  2. Lookup student via rfid_uid in Student Master
  3. Lookup device location (room) from RFID Device
  4. Find Attendance Session: same room, same date, time overlaps
  5. Update Student Attendance → status=Present, source=RFID
  6. Mark Attendance Log → processed=1
        │
        ▼
Student Attendance.trigger_recalculation()
        │
        ▼
Attendance Summary updated
```

### 7.2 Simulated RFID Test

**Pre-requisites:**
- `Student Master` has `rfid_uid` set for the student
- `RFID Device` record exists with `device_id` and `location` (room name)
- `Attendance Session` exists for the same room, date, and overlapping time window
- Student has an existing `Student Attendance` record for that session (created via Fetch Students)

**Step 1 — Create Attendance Log**
1. Go to **Attendance Log** → New
2. Fill in:
   - `rfid_uid` = student's card UID (copy from Student Master)
   - `device_id` = the registered RFID device ID
   - `swipe_time` = a datetime that falls within the session's start/end time
3. Save → `processed = 0`

**Step 2 — Run Processor**
```bash
bench --site [your-site] execute \
  "slcm.slcm.utils.rfid_processor.process_log_entry" \
  --args '["[log-name]"]'
```

**Step 3 — Verify**
- `Attendance Log` → `processed = 1`, `student` field is populated
- `Student Attendance` for that student + session → `status = Present`, `source = RFID`
- `Attendance Summary` → percentage updated

### 7.3 RFID Edge Case Tests

| Test | How | Expected Result |
|---|---|---|
| Double swipe within 10 mins | Create two logs for same UID within 10 min | Second log → `processed=1`, no attendance change |
| Unknown RFID card | Use an `rfid_uid` not in Student Master | Log left unprocessed, `frappe.msgprint` warning logged |
| No matching session | Swipe time doesn't match any session | Log processed, no attendance record created |
| Unknown device | `device_id` not in RFID Device | Log left unprocessed |

---

## 8. Part 4 — Condonation Workflow

Condonation allows a student to claim "forgiven hours" for missed classes due to valid reasons. Approved hours add to the attended count (numerator) without changing the denominator.

### 8.1 Rules (from Attendance Settings)

| Rule | Value |
|---|---|
| Minimum % to be eligible for condonation | `condonation_min_percentage` (default: **66%**) |
| Maximum % where condonation is meaningful | `minimum_attendance_percentage` (default: **75%**) |
| Student below 66% | **Cannot apply** — system throws error |
| Student already at or above 75% | System shows warning but allows it |

### 8.2 Workflow

```
Student creates Condonation request
        │
        ▼
validate_shortage() checks current attendance %
  < 66% → throws error "cannot apply"
  >= 75% → shows warning "already sufficient"
        │
        ▼
Programme Chair reviews → sets final_status = Approved / Rejected
        │
        ▼
Submit (only Approved can be submitted)
        │
        ▼
trigger_recalculation() → Attendance Summary updated
  total_condonation_hours += number_of_hours
  attendance_percentage recalculated
```

### 8.3 Step-by-step Test

**Setup:** Student should have attendance between 66%–75% for a clean test.

**Step 1 — Check current attendance**
- Go to **Attendance Summary** → find student + course → note the current `attendance_percentage`
- Confirm it's between 66% and 75%

**Step 2 — Create Condonation**
1. Go to **Student Attendance Condonation** → New
2. Fill in:
   - `Student`
   - `Course Offering`
   - `Condonation Reason` → Medical / Personal
   - `Number of Sessions` → e.g., `2`
   - `Number of Hours` → e.g., `2`
   - `Proof Document` → attach file
3. Save → validation runs automatically

**Step 3 — Approve**
1. Set `Final Status` → `Approved`
2. `Approver` auto-fills with current user
3. Save

**Step 4 — Submit**
- Click **Submit**

**Step 5 — Verify**
- **Attendance Summary** → `total_condonation_hours` increased by `2`
- `attended_classes` increased
- `attendance_percentage` recalculated upward
- `condonation_list` child table in the summary shows this application

**Rejection Test:**
- Set `Final Status` → `Rejected` → Submit
- Verify `total_condonation_hours` is NOT changed in Attendance Summary

**Error Test:**
- Try creating a condonation for a student with % below 66%
- Expected error: `"Your attendance is less than the required 66%, so you cannot apply for condonation."`

---

## 9. Part 5 — FA Application (First Attempt)

FA (First Attempt) allows a student with **low attendance** to sit for exams because they were representing the university (sports, competitions, events).

### 9.1 Rules

| Rule | Detail |
|---|---|
| `allow_fa_mfa` | Must be **enabled** in Attendance Settings |
| Reason: University Representation | Event dates must be **within 3 days** of the examination date |
| Reason: Medical | Requires medical certificate — no date proximity check |
| Only `Approved` apps can be submitted | Trying to submit a Pending/Rejected app throws error |
| Late submission warning | If submitted more than 10 days after exam, warning shown |
| Effect on Summary | `eligible_for_exam = 1` regardless of actual percentage |

### 9.2 Workflow

```
Student creates FA MFA Application
  application_type = FA
  reason = University Representation / Medical
        │
        ▼
validate_dates():
  - Checks settings.allow_fa_mfa is ON
  - For University Representation: validates event dates within 3 days of exam_date
  - For late submission: shows warning
        │
        ▼
Programme Chair reviews
  status = Approved → approver auto-filled
        │
        ▼
Submit → on_submit()
  → finds all Course Offerings for this course
  → calls calculate_student_attendance() for each
  → Attendance Summary: eligible_for_exam = 1 (override)
```

### 9.3 Step-by-step Test

**Setup:** Student must have `attendance_percentage < 75%`.

**Step 1 — Confirm student is ineligible**
- **Attendance Summary** → student's `eligible_for_exam = 0`, % < 75%

**Step 2 — Create FA Application**
1. Go to **FA MFA Application** → New
2. Fill in:
   - `Student`
   - `Course` → the course name (not course offering)
   - `Application Type` → `FA`
   - `Reason` → `University Representation`
   - `Examination Date` → e.g., `2026-06-10`
   - `Event From Date` → e.g., `2026-06-08` (within 3 days of exam)
   - `Event To Date` → e.g., `2026-06-09`
   - `Proof Document` → attach
3. Save

**Step 3 — Approve**
1. Set `Status` → `Approved`
2. Save → `Approver` auto-fills

**Step 4 — Submit**
- Click **Submit**

**Step 5 — Verify**
- **Attendance Summary** → `eligible_for_exam = 1` even though % < 75%
- `fa_mfa_list` child table in summary shows this application

**Cancel Test:**
- Cancel the FA application
- Verify `eligible_for_exam` reverts back to `0` (since % is still < 75%)

**Date Validation Test:**
- Set `event_from_date` to be 5+ days away from exam date
- Expected error: `"For University Representation, participation dates must be within 3 days of the examination date."`

**Settings Disabled Test:**
- Disable `allow_fa_mfa` in **Attendance Settings**
- Try creating an FA application
- Expected error: `"FA/MFA Applications are currently disabled in Attendance Settings."`

---

## 10. Part 6 — MFA Application (Medical First Attempt)

MFA (Medical First Attempt) is the same override as FA but for medical reasons. No date proximity validation is applied.

### 10.1 Difference from FA

| | FA | MFA |
|---|---|---|
| `Application Type` | `FA` | `MFA` |
| Reason | University Representation | Medical |
| Date proximity check | Yes (within 3 days of exam) | No |
| Document required | Proof of event/representation | Medical Certificate |

### 10.2 Step-by-step Test

Same as FA Application test, with these changes:

1. Set `Application Type` → `MFA`
2. Set `Reason` → `Medical`
3. No `Event From Date` / `Event To Date` needed
4. Attach medical certificate as `Proof Document`
5. Approve → Submit → verify `eligible_for_exam = 1`

---

## 11. Roles & Permissions

| Role | Allowed Actions |
|---|---|
| **Student** | Create: Condonation, FA/MFA Applications. Read: Own attendance, own summary |
| **Faculty** | Read: Course attendance. Define: Office Hours |
| **Programme Chair** | Approve/Reject: Condonation, FA/MFA. Edit: Manual attendance |
| **System Manager** | Full access. Configure: Attendance Settings, RFID modes |

---

## 12. Quick Test Checklist

| # | Test | Steps | Expected Result |
|---|---|---|---|
| 1 | Mark lecture attendance via Class Schedule | Tool → Class Schedule → mark → submit | `Student Attendance` created, session `Conducted`, Summary % updated |
| 2 | Mark lecture attendance via Student Group | Tool → Student Group → select group + date → mark | Same as above, session times default to 09:00–10:00 |
| 3 | Mark Office Hour attendance | Tool → Office Hours → select group → mark | `session_type = Office Hour`, `total_office_hours` in Summary increases |
| 4 | Individual student present | Student Attendance → New → status=Present → save | Summary recalculates via background queue |
| 5 | Change Present to Absent | Open existing record → change status → save | `Attendance Edit Log` created, Summary recalculates |
| 6 | Attempt future date | Tool → set date to tomorrow | Error: "Cannot mark attendance for future dates" |
| 7 | Condonation for valid student | Create condonation (66%–75%) → approve → submit | `total_condonation_hours` increases, % goes up |
| 8 | Condonation for student below 66% | Create condonation for student at 50% | Error: "cannot apply for condonation" |
| 9 | FA Application — approve and submit | Create FA app → approve → submit | `eligible_for_exam = 1` despite % < 75% |
| 10 | FA Application — cancel | Cancel submitted FA app | `eligible_for_exam` reverts to 0 |
| 11 | FA date validation | Set event dates 5+ days from exam | Error: "within 3 days of the examination date" |
| 12 | MFA Application | Create MFA (Medical) → approve → submit | `eligible_for_exam = 1` |
| 13 | RFID simulated swipe | Create Attendance Log → run processor | `Student Attendance` → Present, `source = RFID` |
| 14 | RFID double-swipe (debounce) | Create two logs for same UID within 10 min | Second log skipped, no duplicate attendance |
| 15 | Recalculate all summaries | `bench execute attendance_calculator.recalculate_all_summaries` | All Attendance Summary records updated |

---

## 13. Troubleshooting

### Attendance Summary not updating after marking

- Background queue might be delayed. Run manually:
  ```bash
  bench --site [your-site] execute \
    "slcm.slcm.utils.attendance_calculator.calculate_student_attendance" \
    --kwargs '{"student": "STUD-XXXX", "course_offering": "CO-XXXX"}'
  ```
- Or recalculate all:
  ```bash
  bench --site [your-site] execute \
    "slcm.slcm.utils.attendance_calculator.recalculate_all_summaries"
  ```

### RFID logs stuck at `processed = 0`

- Check that `Student Master` has `rfid_uid` set for the student
- Check that `RFID Device` has the correct `device_id` and `location` matching the session's `room`
- Check that the `Attendance Session` exists for that room, date, and time window
- Check `frappe.log_error` for any error messages from `rfid_processor.py`

### "Attendance for this date is locked" error

- The date is older than `attendance_lock_days` in Attendance Settings
- Only `Administrator` or `System Manager` role can edit locked records

### Course Offering not found (Attendance Summary not calculated)

- The `Student Group` or `Class Schedule` must have the correct `course`, `program`, and `academic_year`
- Go to **Course Offering** list and verify a record exists for that course + program + year

### FA/MFA application disabled error

- Go to **Attendance Settings** → enable `Allow FA/MFA`

### Condonation shows warning "already sufficient attendance"

- Student is already above 75% — the condonation will not increase eligibility further but is still saved

---

*Document covers code as of 2026-05-23. Verify against current controller files if behaviour differs.*

# Plan: OH, Class Participation and Small-Group Attendance

**Status:** Proposal, not started. Nothing gets built until the decisions at the end are agreed.
**Scope:** Faculty Portal, Student Portal, Attendance and Marks in the `slcm` app.

## Requirements

1. Include small-group attendance in the Faculty attendance view.
2. Rename "Office Hours" to "OH".
3. Include OH attendance in the Faculty attendance view, as part of each course.
4. Show a weekly class-participation (CP) student list in a popup or quick view within the course. AAD maintains the weekly list from the backend at the start of term (list master plus upload).
5. Show a weekly OH student list in a popup or quick view, with the same workflow as class participation.
6. Faculty mark attendance and enter CP/OH marks from the list, then submit. Students see their attendance but not their marks.
7. Faculty can mark OH attendance directly from the OH student list.
8. OH attendance is captured as directly as regular session attendance within the course.

---

## Part A — What the system has today

Paths are relative to `slcm/` (the package directory). `doctype/` means `slcm/slcm/doctype/`.

### A1. Attendance data model

**Attendance Session** (`doctype/attendance_session/`)
- `based_on`: `Course Schedule | Time Table | Office Hours`.
- `session_type`: `Lecture | Office Hour | Tutorial`. Note the singular "Office Hour".
- Links: `course_offering`, `course_schedule`, `class_schedule` (links to Time Table), `office_hours_group`, `section`, `instructor`, `room`.
- There is no `student_group` field.
- Child table **Attendance Session Student** has `student`, `student_name`, `status` and `gender`.
- The roster (`get_enrolled_students`) always comes from course-offering enrolment (Student Enrollment, then Student Enrollment Course). It does this even for OH sessions, so the Office Hours Group roster is never used.

**Student Attendance** (`doctype/student_attendance/`)
- One record per student per session (unique on `attendance_session`).
- Carries `session_type`, `based_on`, `office_hours_group`, `course_offer`, `status`, `source` and `hours_counted`.
- On save, it recomputes the parent session's counts and queues `calculate_student_attendance`.

**Attendance Summary** (`utils/attendance_calculator.py`)
- Class hours count only `Lecture` and `Tutorial`.
- OH hours (`session_type='Office Hour'`) go into `total_office_hours`. They are added to the numerator only, not the denominator.
- `calculate_sessions` adds **all** Time Table rows to scheduled class hours, including OH rows.

**Time Table** (`doctype/time_table/`)
- Creates one Attendance Session per row.
- `session_type` is `"Office Hour"` when `based_on == "Office Hours"`, and `"Lecture"` otherwise.
- Time Table has no `session_type` field of its own.

**Course Schedule** (`doctype/course_schedule/`)
- Always creates a `Lecture` session.

### A2. Office Hours: three parallel mechanisms

| Mechanism | Used by | Notes |
|---|---|---|
| Attendance Session with `session_type="Office Hour"` | Faculty portal attendance | Roster is the whole course enrolment, not the OH group |
| Office Hours Session plus `register_office_hours_attendance` (`api/student_portal.py` ~L351–406) | Student portal OH tab (self-registration) | Writes Student Attendance with no `attendance_session` |
| Office Hours Attendance | Nothing | No code ever creates one |

**Office Hours Group**
- Fields: course offering (required), course, batch, section, instructor, a single date and time slot, and a student table.
- Each student row (Office Hours Group Student) has `total_office_hours` and `active`.
- "Get Students" pulls from Student Enrollment.

**Settings**
- Attendance Settings: `include_office_hours_in_attendance`, `core_office_hours`, `elective_office_hours`.
- Faculty Portal Settings: `enable_office_hours`, `office_hours_advance_booking_days`, `max_office_hour_bookings`. Nothing reads these three.

**Naming split**
- `based_on` uses "Office Hours" (plural) and `session_type` uses "Office Hour" (singular).
- Both strings are compared in about 25 places in the Python code.

### A3. Class participation and weekly lists

- CP does not exist as data. The only mentions are static dashboard text in `www/faculty-portal/index.html`, around lines 305–322.
- There is no week-number field anywhere in the app.
- The faculty dashboard "Pending Tasks" tiles:

| Tile | Count |
|---|---|
| Lecture attendance | Real: `index.py`, from Attendance Session with `attendance_marked=0` |
| Office Hour Attendance | Hard-coded `4`, link `#` |
| Office Hour Grading | Hard-coded `3`, link `#` |
| Class Participation Attendance | Hard-coded `3`, link `#` |
| Class Participation Grade | Hard-coded `2`, link `#` |

### A4. Small groups

- The `Student Group` doctypes have been deleted. Their folders contain only `__pycache__`.
- **Section** and **Group** doctypes exist, but neither has a student table.
- **Class Configuration** (`class_configuration_type`: `Section | Group`) is the closest thing to a group roster.
  - Its Class Student table holds `student`, `registration_id` and `section`.
  - It is filled by filter or by CSV upload.
  - Time Table links to it, **but attendance never reads it**.
- Session type `Tutorial` exists, but nothing sets it.

### A5. Marks / grades

- The faculty Grades page (`www/faculty-portal/marks.py`) uses Course Schema Assignment, Access Result Settings and Student Course Marks.
- Marks are stored in **Student Course Marks** (one per student, course and exam plan). Component marks are in the child table `marks_entries` (Student Marks Entry).
- `save_student_marks` (`api/faculty_portal.py`) writes one component row and then recalculates.
- Components come from master data (Exam Component, Evaluation Schema). There is no CP or OH component today. One could be added as a "Custom" Exam Component.
- None of these doctypes is submittable. Locking uses Access Result Settings `status` (LOCKED/UNLOCKED) plus an edit deadline.

### A6. What students can see

- **Attendance:** the student portal reads Attendance Summary and Student Attendance directly. Attendance has no publish gate.
- **Marks:** gated by **Student Result Publish `is_published`**, per student and exam plan. Publish Result Setting controls which components and totals are shown.
- No `show_to_student` flag exists.

### A7. Upload patterns we can reuse

1. **Examination Result page** (`slcm/page/examination_result/`):
   - Download a pre-filled openpyxl template, then upload through an Attach dialog. The result comes back as `{updated, errors}`.
   - `add_students_by_registration_ids` is a ready-made pattern for uploading a student list.
2. **Staged background import** (`marks_bulk_import.py` with Marks Import Log): parse, preview, validate, import, then retry failed rows, all run in the background.
3. **Frappe Data Import** with a custom template, as used for fees.

### A8. Roles

- `AAD` exists but appears on only 4 doctypes (attendance settings and condonation).
- `Academics User` is the exam/results admin role, with 43 permission entries.
- `Academic Admin` has 16 permission entries.
- Other roles: `slcm_Programme Chair`, `slcm_Registrar`, `slcm_Faculty`, `slcm_Student`.
- `AAD`, `Academics User` and `Academic Admin` are **not** exported in fixtures, so they must already exist on each site.

### A9. Bugs to fix first (the new work builds on these paths)

1. **OH roster.** An OH Attendance Session's roster ignores the Office Hours Group and uses the whole course enrolment (`attendance_session.py` `get_enrolled_students`).
2. **Portal "new attendance" path.** `bulk_attendance.mark_attendance` calls `row.get("student")` on a plain string, so this path probably fails.
3. **RFID.** `process_attendance_logs.py` `_upsert_office_hour_attendance` writes an Office Hours Session name into `attendance_session`, which must link to an Attendance Session.
4. **Class-hours total.** `attendance_calculator.calculate_sessions` counts scheduled OH Time Table hours as class hours.
5. **Grades access.** `int(x or 1)` turns `view_access=0` / `edit_access=0` into 1, so faculty access is never actually blocked (`marks.py` lines 104 and 113, `api/faculty_portal.py` line 813).

---

## Part B — Proposed design

### B1. Rename "Office Hours" to "OH" (display only)

- Change only what users see: portal pages, select labels, dashboard tiles and the student portal.
- **Keep the stored values** (`"Office Hour"` / `"Office Hours"`). Renaming the data would need a migration across about 25 comparisons, with real risk of breaking things.
- The faculty attendance popup has already been done. The rest gets updated in one pass.

### B2. One OH mechanism

- **Attendance Session (`session_type="Office Hour"`)** becomes the only way OH is recorded.
- **Roster:** the weekly OH list for that course and week (B4). If there isn't one, it falls back to the Office Hours Group's active students.
- The student portal's OH tab reads these sessions.
- Office Hours Session and Office Hours Attendance are retired: hidden, and no longer created.
- **Result:** requirements 7 and 8 come for free. OH uses the same modal, the same save path and the same attendance totals as regular sessions.

### B3. Small groups

- Add the session type **"Small Group"**, or reuse the unused `Tutorial`.
- Link the session to a **Class Configuration (Group)**, which becomes the session's roster.
- Time Table rows with a Group configuration create small-group sessions automatically.
- The faculty Attendance view lists them under each course, with a **Type** filter: Lecture / Small Group / OH / CP.

### B4. New master: Weekly Student List (maintained by AAD)

| Part | Fields |
|---|---|
| Header | Course Offering, Academic Term, List Type (`CP` / `OH`), Week No, Week Start, Week End (calculated from the term start date), Faculty |
| Child table | Student, Student Name, Registration ID |

- **Entry:** AAD can enter lists manually, or upload one Excel file for the whole term (rows of week, course and student registration ID). This reuses the openpyxl template and upload pattern from A7.
- **Permissions:** AAD / Academics User can write. Faculty can read their own courses. Students have no access.

### B5. New transaction: Weekly Participation Entry (one per list per week)

- Each student row holds an attendance status, marks (CP or OH), and remarks.
- **When the faculty submits:**
  1. A **Student Attendance** record is created or updated for each student, with session type CP or `Office Hour`, against an Attendance Session for that week. This is how students see their attendance.
  2. The entry is locked (`docstatus = 1`). AAD can amend it.
  3. Marks stay **only on this entry**. Students have no permission on it and no student-portal page reads it. This meets requirement 6.
- **Optional:** also roll the marks into Student Course Marks as an Exam Component (CP / OH). They would then follow the existing publish rules. See decision 3.

### B6. Faculty portal UI

- **Course Details popup:** add "CP — Week N" and "OH — Week N" tabs with a week picker. Each tab shows the list with inline attendance toggles and marks inputs, plus **Save draft** and **Submit** buttons.
- **Attendance page:** OH can be marked straight from the OH list. Small-group and OH sessions appear under each course.
- **Dashboard:** replace the four hard-coded tiles with real pending counts, meaning lists for past weeks that haven't been submitted.

### B7. Student portal

- CP, OH and small-group attendance show up automatically, because these pages read Student Attendance.
- No marks are shown.
- How each type affects the attendance percentage is set by decision 2.

---

## Part C — Phases

| # | Scope | Depends on |
|---|---|---|
| 0 | Fix bugs A9.1–A9.5 | — |
| 1 | OH label rename everywhere; single OH mechanism; OH roster fix | 0 |
| 2 | Small-group session type and Class Configuration roster; Type filter on the Attendance page | 0 |
| 3 | Weekly Student List doctype, AAD screens, Excel template and upload | — |
| 4 | Weekly Participation Entry; mark and submit; Student Attendance write-through | 3 |
| 5 | Faculty UI (popup tabs, OH from list); dashboard counts; student-portal check | 1, 4 |

---

## Part D — Decisions needed before development

1. **What is a "small group"?** Is it a Class Configuration "Group" (already exists, with a student list), or something new?
2. **Attendance percentage:**
   - Should CP and small-group sessions count toward a student's attendance percentage?
   - Should OH stay as "bonus hours" (numerator only), as it is today?
3. **CP / OH marks:** should they stay only in the weekly entry (internal), or also feed Student Course Marks as a component, so they reach final results once published?
4. **Week definition:** Monday to Sunday counted from the term start date, or weeks defined by AAD?
5. **AAD in the system:** the existing `AAD` role, `Academics User`, or a new role?
6. **Retiring Office Hours Session:** can the student self-registration flow for OH stop, or must it stay alongside the new one?

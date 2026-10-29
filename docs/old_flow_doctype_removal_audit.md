# Audit log: removal of old-flow academic DocTypes and pages

| | |
|---|---|
| Date | 29 Oct 2026 |
| Site | slcm.local (developer mode) |
| Branch | `TFSS`, on top of `3d4d5f9c` (workspace cleanup, cherry-picked from `1189f74d`) |
| Requested by | Jenifar A |
| Reason | The new academic flow (Academic Year → Academic Term + Term Mapping → Programme / Section / Batch → Student Enrollment with Academic Log → Classes → Time Table) replaces these DocTypes and pages. |

## 1. What was removed

### 1.1 DocTypes (13)

All had **0 records**. The three Single DocTypes held only default values (listed below).

| # | DocType | Type | Records before | Replaced by |
|---|---|---|---|---|
| 1 | Term Configuration | Document | 0 | Academic Term + Term Mapping |
| 2 | Term Programme Mapping | Child table of Term Configuration | 0 | Academic Term Mapping |
| 3 | Term Administration | Single (settings) | 7 default values | Academic Term |
| 4 | Academic Management System | Single (settings) | 7 default values | Programme Management workspace |
| 5 | Class Configuration | Document | 0 | Classes |
| 6 | Class Student | Child table of Class Configuration | 0 | Class Enrolled Student |
| 7 | Course Management | Single (settings) | 13 values (only `academic_system = Semester` set; rest empty or system) | Student Enrollment → Create Class |
| 8 | Course Type | Child table of Course Management | 0 | Course.course_type |
| 9 | Course Enrollment Type | Child table of Course Management | 0 | n/a |
| 10 | Course List | Document | 0 | Classes |
| 11 | Curriculum | Document | 0 | Classes |
| 12 | Curriculum Course | Child table of Course List / Curriculum | 0 | Student Enrollment Course |
| 13 | Program Enrollment | Child table (not used by any DocType) | 0 | Student Enrollment Academic Log |

### 1.2 Pages (2)

| Page | Purpose (old flow) | Replaced by |
|---|---|---|
| `academic-management` | Created Term Configuration / Class Configuration | Programme Management workspace, Student Enrollment → Create Class |
| `timetable-configuration` | Old timetable builder (Class Configuration based) | Classes form → Time Table → Create / View Time Table |

## 2. Database actions on slcm.local

Done in this order. Each step succeeded.

1. `bench migrate`: applied the Time Table field removal and the cherry-picked workspace cleanup.
2. Deleted the **REGO** Workspace Sidebar again. Migrating the TFSS branch had restored it; its code was already removed in `3d4d5f9c`.
3. Deleted 5 **Property Setters** on Course List (`in_list_view` for department, academic_system, academic_year, program, batch).
4. Deleted the 13 **DocTypes** (`frappe.delete_doc("DocType", …)`, parents before child tables). In developer mode this also removed their code folders.
5. Deleted the 2 **Pages**. Their code folders were removed too.
6. Dropped the 10 **empty tables** Frappe leaves behind after deleting a DocType. Each was re-checked to have 0 rows immediately before `DROP TABLE`:
   `tabTerm Configuration`, `tabTerm Programme Mapping`, `tabClass Configuration`, `tabClass Student`, `tabCourse Type`, `tabCourse Enrollment Type`, `tabCourse List`, `tabCurriculum`, `tabCurriculum Course`, `tabProgram Enrollment`.
7. Removed the 27 stored values of the 3 Single DocTypes from `tabSingles`.
8. `bench migrate` + `bench clear-cache`: no errors.

**Verified after deletion:** 0 DocTypes left, 0 tables left, 0 DocPerms, 0 Property Setters, 0 Singles values, 0 pages, 0 code folders.

## 3. Code changes

| File | Change |
|---|---|
| `slcm/doctype/<13 folders>/` | Deleted (DocType definitions and controllers) |
| `slcm/page/academic_management/`, `slcm/page/timetable_configuration/` | Deleted |
| `time_table/time_table.json` | Removed fields `class_configuration` (Link → Class Configuration, hidden) and `term` (Link → Term Configuration). None of the 13 Time Table entries used them. |
| `time_table/time_table.py` | A class-based entry now always requires a Class (the Class Configuration fallback is gone). Removed `get_timetable_data` and `create_time_table` (only the deleted timetable-configuration page called them). `get_sessions_roster` uses Classes only. Dropped `class_configuration` from the `get_events` query. |
| `time_table/time_table.js` | Removed the `class_configuration` field handler |
| `student_enrollment/student_enrollment.py` | Removed the sync that copied students into Class Configuration rosters (`_sync_class_configuration_rosters`, `_add_to_class_roster`, `_leave_section_rosters`, `_remove_from_class_roster`) and the now-unused `skip_roster_sync` flag |
| `page/examination_result/examination_result.py` | Result hover card takes the section from the student's Class, not Class Configuration. Removed `get_course_overview` and `get_course_students_with_marks` (Class Configuration based; nothing called them). |
| `page/exam_barcode_sheet/exam_barcode_sheet.py` | Barcode sheet takes the section from the student's Class in the exam plan's term |
| `page/uniquad_dashboard/uniquad_dashboard.py` | Removed Course List and the two deleted pages from the Programme Management module list |
| `page/slcm_data_map/slcm_data_map.py` / `.js` | Removed Curriculum, Class Configuration and Program Enrollment |
| `fixtures/property_setter.json` | Removed the 5 Course List property setters |
| `tests/test_erpnext_coexistence.py` | Removed the assertion on Curriculum's department field |

Diff size: 70 files, +32 / −5,588 lines.

**Left unchanged on purpose:**
- `patches/v1_0/rename_academic_management_to_term_administration.py` and `patches/v2_0/remove_course_offering.py` mention these DocTypes, but have already run and check `table_exists` first.
- The one-off scripts in `migrations/` only check `frappe.db.exists`. They are not run by migrate.

## 4. Verification (after deletion)

Run on slcm.local inside a transaction that was rolled back, so no test data was kept.

**Academic flow, 12/12 passed:**
- Academic Term save (Term Mapping → Academic Log)
- Change Section
- Create Section class, Group class, duplicate skipped
- Time Table preview + create (weekly × 3 with a class-participation week)
- Venue clash detection
- Class roster
- Promote to Year 2
- Repeat Year 1
- Promotion Run
- Drop enrollment

**Exams and portals:**
- Exam setup, marks sync from Classes, Examination Result grid and hover, barcode sheet, Term Results (GPA), Publish, Transcript: **8/8 passed**.
- Result hover and barcode sheet now show **section A**. Both were blank before this change.
- Student portal **22/23** pages (Placement fails on an existing, unrelated `nowdatetime` import bug), parent portal **4/4**, faculty portal **10/10**.

## 5. Not removed in this change

| Item | Records | Why it stays (for now) |
|---|---|---|
| Course Enrollment | 0 | Unused child table, same as Program Enrollment. Kept because the agreed list was 13. Safe to remove next. |
| Programme Master | 0 | Still read by attendance condonation (Programme link), the Zoho journal report (`zoho_course`) and fee certificates (duration). Move these fields to Programme first. |
| Term Master, Academic Term Mapping | in use | Part of the new flow (programme terms such as Trimester II) |
| Student Group, Student Group Student, Class Participation Week | in use | Office Hours and Class Participation in the new timetable |

## 6. Applying this to other sites (staging / production)

`bench migrate` removes DocTypes and Pages whose code is gone ("Removing orphan doctypes / pages"), **including any data they hold**. Run these checks **before** deploying:

```sql
SELECT 'Term Configuration' dt, COUNT(*) FROM `tabTerm Configuration`
UNION ALL SELECT 'Class Configuration', COUNT(*) FROM `tabClass Configuration`
UNION ALL SELECT 'Class Student', COUNT(*) FROM `tabClass Student`
UNION ALL SELECT 'Course List', COUNT(*) FROM `tabCourse List`
UNION ALL SELECT 'Curriculum', COUNT(*) FROM `tabCurriculum`
UNION ALL SELECT 'Curriculum Course', COUNT(*) FROM `tabCurriculum Course`
UNION ALL SELECT 'Term Programme Mapping', COUNT(*) FROM `tabTerm Programme Mapping`
UNION ALL SELECT 'Program Enrollment', COUNT(*) FROM `tabProgram Enrollment`;
SELECT COUNT(*) AS time_tables_on_old_fields FROM `tabTime Table`
WHERE IFNULL(class_configuration, '') != '' OR IFNULL(term, '') != '';
```

- If every count is 0: deploy and run `bench --site <site> migrate`. Then drop only the 10 leftover empty tables, by name:
  ```sql
  DROP TABLE IF EXISTS `tabTerm Configuration`, `tabTerm Programme Mapping`, `tabClass Configuration`,
    `tabClass Student`, `tabCourse Type`, `tabCourse Enrollment Type`, `tabCourse List`, `tabCurriculum`,
    `tabCurriculum Course`, `tabProgram Enrollment`;
  DELETE FROM `tabSingles`
  WHERE doctype IN ('Term Administration', 'Academic Management System', 'Course Management');
  ```
  **Do not use `bench trim-database`** for this. On slcm.local its dry run also lists many unrelated leftover tables (e.g. Program Reservation Policy, Class Schedule, Course List Course) that may still hold data.
- If any count is above 0, **stop**: that site still has old-flow data. Move it to Classes / Academic Term first.
- REGO, SLCM Master, Fees & Payments, Programme Setup, Masters and Fee Management screens (see commit `3d4d5f9c`) must be deleted by hand on each site. Migrate does not remove them.

## 7. Rollback

- **Code:** revert the commit for this change. The DocType and page folders come back.
- **Database:** `bench migrate` recreates the DocTypes, pages and tables (empty). Nothing else needs restoring: no records existed, and the Single values were defaults only.

## 8. Follow-up: Course Schedule removed (29 Oct 2026)

Course Schedule had **0 records** on slcm.local. Its attendance code path is gone; attendance runs only on Classes → Time Table (venue = Venue Master) → Attendance Session → Student Attendance / Attendance Summary.

**"Based On" value renamed.** The literal "Course Schedule" was also the **Based On** value of a regular class period on Time Table, Attendance Session, Student Attendance (`based_on`, `attendance_based_on`) and Student Attendance Tool, though those rows never linked a Course Schedule record. That value is now **"Class"**. The options are `Class / Time Table / Office Hours`, and the default is Class. "Time Table" and "Office Hours" are unchanged.

**Patch** `slcm.patches.v2_0.remove_course_schedule` (post model sync) does the following:
- Renames `Course Schedule` → `Class` in the Based On columns above, in the Student Attendance Tool Single, and in any Property Setter defaults.
- Deletes sidebar, workspace link and shortcut items to the doctype, plus its Custom Fields and Property Setters (including the `CSH-.YYYY.-` naming series setter) and setters on the removed `course_schedule` fields.
- Deletes the DocType and drops its table. It **skips** this if the table still holds records.

On slcm.local, migrate renamed the 13 Time Tables and 13 Attendance Sessions to Class. There were no Student Attendance rows.

| Area | Change |
|---|---|
| `doctype/course_schedule/` | Deleted |
| Time Table, Attendance Session, Student Attendance, Student Attendance Tool (JSON) | Removed the `course_schedule` Link field and the `fetch_from: course_schedule.*` on instructor, room and programme. Based On options and `depends_on` now use Class. Student Attendance and Student Attendance Tool show the Time Table link for Class too. |
| `time_table.py` / `.js` / `_calendar.js` | Class checks use "Class". Removed the copy of `course_schedule` onto sessions, the Course Schedule field handler and the calendar popover row. |
| `attendance_session.py` / `.js`, `student_attendance.py` | Removed the `course_schedule` copy, toggle, duplicate filter and the Course Schedule detail fetch. Class details now come only from the session's Class. |
| `student_attendance_tool` (DocType) | A Class entry is taken against its Time Table (`class_schedule`). The Course Schedule branch is removed. |
| `api/bulk_attendance.py` | Removed `get_students_from_schedule`, `create_bulk_attendance_from_schedule` and their helper `_get_or_create_attendance_session`, and the Course Schedule source in `mark_attendance` and `get_faculty_context`. `mark_attendance` matches sessions by Time Table for Class or Time Table, and now also accepts a plain list of student IDs (as the faculty portal sends). |
| `page/student_attendance_tool` | Picks a class period's **Time Table** entry (Based On = Class, limited to the faculty's classes) and marks through `mark_attendance` |
| Faculty portal (`attendance.html` / `.py`, `index.py`) | Removed the "Course Schedule" Based On option and the Course Schedule room lookup. Removed the guest-accessible `debug_venue` endpoint. |
| RFID (`process_attendance_logs.py`, `rfid_processor.py`), `api/faculty_portal.py`, `permissions.py` | Removed `course_schedule` reads and writes, and Course Schedule as a source of a faculty's classes |
| `classes/class_time_table.py`, tests | New class Time Tables use Based On = Class |
| Sidebars, fixtures, dashboards | Removed from the Faculty Management sidebar (app file and fixture), the property setter fixture, the Uniquad Dashboard module list and the SLCM module flow (now Time Table) |

**Other sites:** run ``SELECT COUNT(*) FROM `tabCourse Schedule` `` before deploying. If it is above 0, move those records to the Time Table first. The patch will not delete the doctype while it has records.

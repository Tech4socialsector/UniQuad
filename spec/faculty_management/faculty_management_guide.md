# Faculty Management: User Guide

**Applies to:** Uniquad (SLCM v16), as on disk November 2026
**Who this is for:** Academic office staff who set up faculty records and portal access, and faculty who use the Faculty Portal to take attendance and enter marks.
**Where:** Desk → **Faculty Management** (desktop icon) and **Master → People / Portals**. Faculty work in the **Faculty Portal** at `/faculty-portal`.

---

## 1. The flow at a glance

```
1. Faculty record        Master → People → Faculty  (+ Auto Create User)
2. Portal access         User gets role slcm_Faculty; signs in with Google on /login
3. Teaching load         Classes.faculty = this Faculty  (set in Programme Management)
4. Timetable             Time Table + Attendance Sessions created for the class
5. Daily work (portal)   Attendance → Class Participation / Office Hours → Condonation recommendation
6. Marks (portal)        Grades → Grade Sheet, Re-Exam & Improvement, Assessment Marks
7. Submit                Faculty mark students Submitted; exam office locks
```

Everything a faculty member sees in the portal comes from **Classes** where *Faculty* is their record. If a faculty member is not the faculty of any class, the portal pages are empty.

### Key ideas

| Term | Meaning |
|---|---|
| **Faculty** | One record per teacher. Named by a running number (1, 2, 3 …); the title is the full name. |
| **slcm_Faculty** | The role that opens the Faculty Portal. Its home page is `/faculty-portal`. |
| **Class** | One course taught to one section or group in one term. Its *Faculty* field decides who teaches it. See the [Programme Management guide](../programme_management/programme_management_guide.md#5-creating-classes). |
| **Attendance Session** | One teaching session, created from the timetable. Faculty mark attendance on it. |
| **Student Course Marks** | One record per student per course per exam plan. Holds marks, total, grade and a status: *Draft / Submitted / Locked*. |
| **Access Result Settings** | One record per exam plan + course. Controls what faculty may see and change for that course. |
| **Admin preview** | A System Manager with no Faculty record of their own sees the portal as the first Active faculty, with a banner. |

---

## 2. Faculty records

### 2.1 Faculty
*Master → People → Faculty* (also in the **Student Registration** sidebar)

| Field | Notes |
|---|---|
| Faculty ID | Required. Shown in the portal. |
| Full name / Last Name | Full name is required and is the record title. |
| Email | Required. |
| Official Email ID | The institutional (Google) address. Used to create the login. |
| User Account | Link to the Frappe User. Filled automatically (see 2.2). |
| Auto Create User | Tick to create the login. System Manager only. |
| Phone Number | |
| Department / Designation | Links to *SLCM Department* / *SLCM Designation*. |
| Reporting To | Another Faculty. |
| Is HOD | Tick for head of department. |
| Status | Active / Inactive. Required. |
| Photo | Required. Shown in the portal. |
| Highest Qualification, Specialization, Years of Experience, Highlights, Studied Institution, Joining Date | Profile details. Faculty can edit most of these from the portal (section 6). |

**Rules the system enforces**
- Only a **System Manager** can tick *Auto Create User*.
- *Auto Create User* needs the *Official Email ID*.
- If *User Account* is already set, nothing is created.

**Who can edit Faculty records:** System Manager, slcm_Registrar, PACE Admission Manager, Admission Admin, AAD, AAD Staff. slcm_Faculty can read and write (but not create). Programme Chair and Student can read.

### 2.2 How a faculty member gets a login

Two ways:

| Way | What happens |
|---|---|
| **Auto Create User** on the Faculty form | On save, a User is created for the *Official Email ID*: type *Website User*, a random password, no welcome email, role **slcm_Faculty**. If a User with that email already exists, it is linked and given the role. |
| **First Google sign-in** | When the faculty member signs in with Google on `/login`, the system finds the Faculty record by *User Account*, *Official Email ID* or *Email*, links the User and adds the **slcm_Faculty** role. |

### 2.3 Signing in
*`/login` → **Faculty & Student** tab*

- Faculty sign in **with Google only**. Password sign-in is refused (unless the account is also office staff).
- Google sign-in for faculty is switched on by **Faculty Portal Settings → Enable Google Login for Faculty**.
- **Allowed Google Account Domain** (same settings) limits which email domain may sign in. Blank = any domain.
- An unknown Google account (no Faculty, Student or Parent record) is refused.
- The old address `/faculty/login` redirects to `/login?tab=faculty-student`.
- Which roles may open the Faculty Portal is set on the **Roles & Permissions** page (Portals section).

---

## 3. The Faculty Management sidebar (desk)

*Desk → Faculty Management*

| Section | Links |
|---|---|
| Academic Management | Course, Time Table, Student Enrollment |
| Attendance | Bulk Attendance Tool (page `student-attendance-tool`), Attendance Session, Student Attendance, Attendance Log, Attendance Condonation, Attendance Summary |
| Examination & Evaluation | Student Course Marks, Grade Appeal |
| Students | Student Master, Office Hours (Office Hours Group), Office Hours Session |
| Venue Booking | New Venue Booking, My Bookings |
| Reports | Comprehensive Attendance Report, Consecutive Absents, Daily Absentees, Course Completion |

**What a faculty user sees in these lists** (row-level filters in `slcm/permissions.py`):

| DocType | Faculty sees |
|---|---|
| Student Master | Only students of the Classes they teach, and only if *Academic Status* is Active. Nothing if the user is not linked to a Faculty record. |
| Attendance Session | Sessions of their Classes, or where they are the *Instructor*. |
| Student Attendance, Attendance Log, Attendance Summary, Attendance Condonation, FA MFA Application | Records of the Classes they teach. |
| Time Table | Schedules of their Classes. |
| Venue Booking | Their own bookings only. |

**Role rights for slcm_Faculty** (DocType permissions)

| DocType | Rights |
|---|---|
| Course, Time Table | Read |
| Classes | Read, write, create, delete |
| Student Course Marks | Read, write, create |
| Grade Appeal | Read, write |
| Student Attendance Condonation | Read, write |
| Office Hours Group | Read, write, create, delete |
| Office Hours Session | Read, write, create |
| Venue Booking | Read, write, create |
| Faculty Announcement | Read, write, create |

> Note: users created by *Auto Create User* are **Website Users**, so they normally work in the portal, not the desk. See Open questions.

---

## 4. The Faculty Portal

*`/faculty-portal`* (home page of the slcm_Faculty role)

### 4.1 Menu

| Menu item | URL | What it is for |
|---|---|---|
| Dashboard | `/faculty-portal` | Today's sessions, pending tasks, calendar, quick actions |
| Announcements | `/faculty-portal/communication` | Faculty Announcements for this faculty member |
| My Courses | `/faculty-portal/my-classes` | The faculty's classes with students and attendance figures |
| Attendance | `/faculty-portal/attendance` | Mark attendance, class participation, Office Hours, condonation |
| Grades | `/faculty-portal/marks` | Enter marks and grades |
| Venue Booking | `/faculty-portal/venue-booking` | Request a room and see own bookings |
| LMS | *(external link)* | Shown only when *Enable LMS Navigation* is on; opens *LMS URL* |
| Helpdesk | `/faculty-portal/support` | Helpdesk tickets (embedded `/helpdesk`) |
| Profile *(user menu)* | `/faculty-portal/profile` | Own details and assigned courses |
| Settings *(user menu)* | `/faculty-portal/settings` | Change password / reset password |

The bell icon shows notifications: published **Portal Announcements**, sessions waiting for attendance, and condonation requests waiting for a recommendation.

### 4.2 Which classes a faculty member sees

- Every page starts from **Classes where Faculty = this faculty member**.
- Dashboard, My Courses and Attendance show only classes of **Active** academic years (all years, if none is marked Active).
- Grades lists each **course + academic term** the faculty teaches.

### 4.3 Dashboard

| Panel | Shows |
|---|---|
| Summary cards | Courses, students (distinct, Enrolled), today's sessions, weekly teaching hours. Each card opens a detail list. |
| Today's Sessions | Today's attendance sessions with venue and marked / pending state |
| Attendance Tasks | Counts of sessions waiting for: course attendance, class-participation attendance, class-participation grades, Office Hours attendance, Office Hours grades. Each links to the Attendance page, filtered. |
| Calendar | Timetable sessions, institutional calendar holidays and events the faculty takes part in |
| Sync to Google Calendar | Pushes the faculty's upcoming timetable to their Google Calendar (official or personal email) |
| Upcoming (next 7 days) | Next sessions with venue |
| Pending condonation / venue bookings | Counts that need action |
| Attendance trend / course-wise attendance | Last 10 marked sessions; average per class |
| Quick Actions | Take Attendance, My Courses, Grades, Venue Booking |

---

## 5. What faculty can do

### 5.1 Attendance
*Faculty Portal → Attendance*

The page has three tabs: **Attendance** (class sessions), **Class Participants** (sessions with a participation week), **OH** (Office Hours sessions). It can be filtered by class and term.

| Action | What happens |
|---|---|
| **Mark attendance** on a session | Open the session, mark each student Present or Absent, save. A **Student Attendance** record is created or updated for each student (source *Manual*). The session's present / absent counts and % are updated and it is marked done. Students not marked are saved as **Absent**. |
| **Class participation marks** | Entered in the same dialog for sessions that have a participation week. Saved together with attendance: if a mark is invalid, nothing is saved. |
| **Office Hours** | OH sessions use the Office Hours group roster. |
| **Bulk mark** (Student Attendance Tool in the portal) | Based on *Time Table* or *Office Hours* group and a date; marks the whole list at once. |
| **Activate RFID** | Opens a 10-minute window (shown as a timer) for card swipes. Can be done once per session. Swipes are recorded even without activation; activation only affects what the portal shows. |
| **Attendance history** | Shows who marked a student's attendance and how (*Class attendance* or *Biometric* for RFID/QR). |
| **Condonation recommendation** | For condonation requests of the faculty's classes: choose *Recommended* or *Not Recommended*. |

**Rules the system enforces**
- A faculty member can only save attendance for sessions of **their own** classes.
- A session **locks** a set number of hours after it ends (*Attendance Settings → attendance lock hours*, default **24**). After that, saving and RFID activation are refused, unless AAD has **reopened** the session; edits made then carry the reopen reason in the Attendance Edit Log.
- Attendance cannot be marked for future sessions.

For the attendance rules themselves (75 % eligibility, condonation and FA/MFA approval, RFID), see:
- [Attendance workflows](../attendance/attendance_workflows.md)
- [Attendance session deep dive](../attendance/attendance_session_deep_dive.md)
- [Office Hours / Class Participation plan](../attendance/oh_cp_small_group_attendance_plan.md)
- [Programme Management guide, section 7](../programme_management/programme_management_guide.md#7-attendance-summary)

### 5.2 Grades (marks entry)
*Faculty Portal → Grades → pick a Course (course · term) → pick the Assessment (Exam Plan)*

Nothing loads until a course is chosen. The page has two views: **Grades** and **Assessment Marks**.

**Grades view: Grade Sheet tab**

| Action | Notes |
|---|---|
| Enter marks | Inline, per student per component. The Student Course Marks record is created on the first save. Total and grade are recalculated the same way as the desk *Course Results* page. |
| Revaluation marks | A second field per component. |
| Remark | Free text per student. |
| Grade override | Only if *Edit Grade Access* is on. The grade must belong to the grading schema (or *Ab* / *AS*). |
| Auto generate grades | Only if *Auto Generate Grade Access* is on. Recalculates every **Draft** student. |
| Mark as Submitted / Mark as Draft | For selected students. **Locked** rows are skipped. |
| Download template / Import | Excel (.xlsx) template from this page. The import is checked first; **nothing is saved unless every row is valid**. |
| Statistics | Only if *Generate Grade Report* is on. |

**Grades view: Re-Exam & Improvement tab**

| Action | Notes |
|---|---|
| Re-exam marks | Only for students with a **paid** *Re Exam Registration* for the course and exam plan. Allowed even if the student's regular result is Submitted. |
| Improvement marks | Only for students with a **paid** *Improvement Exam Registration*. Applied to the final result when higher (shown with an **I** mark). |

Re-exam grades carry an **R / RR / RRR** mark (one R per re-exam written); MFA shows **Mfa**.

**Assessment Marks view**

Faculty enter **1st Submission** and **2nd Submission** marks for each assessment set up in the **Exam Assessment Schedule** (Assessment 1, Assessment 2, Re-Exam …). They are stored per student in Student Course Marks → Assessment Marks. Download / import of the sheet works the same way.

| Rule | |
|---|---|
| Entry opens | When the assessment closes: the 2nd submission deadline, else the 1st, else the assessment date. |
| Entry closes | At the row's **Marks Entry Deadline** (open-ended when blank). |

**What decides whether a faculty member can see or change marks** (*Access Result Settings*, per exam plan + course)

| Setting | Effect for faculty | Default when no record exists |
|---|---|---|
| View Access / View Deadline | Off or past the deadline: the sheet is hidden, "contact your Programme Chair". | On, no deadline |
| Edit Access / Edit Deadline | Off or past the deadline: read-only. | On, no deadline |
| Status = LOCKED | Read-only for everyone. | Unlocked |
| Mask Student Info | Student details masked on the sheet. | Off |
| Edit Grade Access | Allows grade override. | Off |
| Auto Generate Grade Access | Allows *Auto generate grades*. | Off |
| Generate Grade Report | Shows statistics. | Off |
| Visible exam types | Only these assessment columns are shown. | All |

**Rules the system enforces**
- A faculty member must teach a Class of that course in that term.
- Only **Enrolled** students of the faculty's own Classes of the course are listed. In a course split across sections, each faculty sees only their section(s).
- A student marked **Submitted** is read-only for faculty (the office reviews it or sets it back to Draft). **Locked** is read-only for everyone.
- Marks must be numbers from 0 to the component's maximum. Blank means "no mark", not 0.
- If no exam plan is set up for the course, the page says to contact the examination office.

For how exam plans, schemas and results are set up, see the examination specs (not part of this guide).

### 5.3 Other things faculty can do

| Where | What |
|---|---|
| **My Courses** | Each class with student count, sessions held, average attendance, sessions pending marking, next session. Filter by academic year (Active years only) and term. |
| **Announcements** | Active **Faculty Announcements** with a publish date up to today and not expired, for *All Faculty*, the faculty's department, or the faculty by name. Sorted by priority (Urgent, Important, Normal). |
| **Venue Booking** | Request a venue: event name, venue type, room, start and end, expected attendees, reason. The booking is created as *Pending Allotment* with requester type *Faculty*. The page lists the faculty's own bookings (Pending / Allotted / Rejected) and admin remarks. |
| **Helpdesk** | Regular faculty see their own tickets (`/helpdesk/my-tickets`). Helpdesk agents see the full ticket list. |

---

## 6. Profile and settings (faculty self-service)

| Page | What faculty can change |
|---|---|
| **Profile** | Phone, Highest Qualification, Specialization, Years of Experience, Highlights, Studied Institution. Also lists assigned courses. Name, email, department, designation and status are read-only. |
| **Settings** | Change password (current password + new password of at least 8 characters), or get a password-reset link. |

> Faculty normally sign in with Google, so the password options matter only for accounts that are allowed a password.

---

## 7. Portal setup (admin)

### 7.1 Faculty Portal Settings
*Master → Portals → Faculty Portal Settings* (System Manager / Administrator only)

| Group | Fields that the portal uses |
|---|---|
| Branding | Portal Title, Subtitle, Show Logo, Navbar Brand Text, Logo, Favicon |
| Typography | Font Family (default Merriweather), Font Size |
| Theme colours | Primary (#2b2e4a), Secondary (#920c24), background, card, sidebar and menu colours |
| Status / grade colours | Success, warning, danger, info; grade band colours |
| Attendance thresholds | Good (75 %) and Warning (60 %) thresholds and their labels. Warning must be lower than Good. |
| Layout | Sidebar width, navbar height, corner style |
| Dashboard | Announcements ticker, Quick Actions panel |
| Login & Security | Enable Google Login for Faculty, Allowed Google Account Domain |
| LMS | Enable LMS Navigation, LMS URL |
| Advanced | Custom CSS (added after all portal styles) |
| Self-service permissions | Allow theme / density / font size / dashboard / notification preferences |

Many other fields on this form are **not read by any code** (see Open questions).

### 7.2 Faculty Portal User Preferences
*Master → Portals → Faculty Portal User Preferences*. One record per user (named by the user): theme mode, font size, density, dashboard panels to hide, notification switches, email digest frequency.

### 7.3 Faculty Announcement
*Master → Portals → Faculty Announcements*

| Field | Notes |
|---|---|
| Title, Content | |
| Type | Academic / Administrative / Examination / Research / General |
| Priority | Normal / Important / Urgent |
| Publish Date / Expiry Date | Shown from the publish date until the expiry date |
| Active | Untick to hide |
| Audience Type | All Faculty / Specific Department(s) / Specific Faculty, with the matching target table |

Named `FA-YYYY-#####`.

---

## 8. Troubleshooting

| Problem | Cause and fix |
|---|---|
| Portal says the user is not a faculty member | No Faculty record matches the user by User Account, Official Email ID or Email. Link the User on the Faculty record. |
| Google sign-in refused | *Enable Google Login for Faculty* is off, the email domain is not the allowed domain, or there is no Faculty record for that email. |
| "Only a System Manager can enable Auto Create User" | Ask a System Manager to tick it, or link an existing User manually. |
| Portal pages are empty | The faculty is not set as *Faculty* on any Class, or the classes are in an academic year that is not Active. |
| "Not permitted" when saving attendance | The session's class belongs to another faculty member. |
| Cannot save attendance / RFID refused | The session is locked (default 24 h after it ends). AAD can reopen it. |
| "RFID has already been activated for this session" | RFID can be activated once per session. |
| Grades: "You are not assigned to a class of this course in this term" | The faculty is not the faculty of a Class of that course in that term. |
| Grades: "No exam plan is set up for this course yet" | No Course Schema Assignment links an exam plan to this course and its classes. Contact the examination office. |
| Grades: view / edit turned off or deadline passed | Change *Access Result Settings* for the exam plan + course. |
| A student's row is read-only | The student's marks are *Submitted* (office can set back to Draft) or *Locked*. |
| Re-exam row missing | The student has no **paid** Re Exam / Improvement Exam Registration, or is not in the faculty's class. |
| Import rejected | Use the .xlsx template from the same page; fix every listed row. Nothing is saved until all rows pass. |
| Assessment Marks closed | Entry opens only after the assessment's submission deadline and closes at its Marks Entry Deadline. |

---

## 9. Open questions

1. **Desk sidebar vs. Website Users.** *Auto Create User* makes faculty **Website Users** (no desk). Who is the desk *Faculty Management* sidebar for: faculty with desk access, or office staff? Its desktop icon has no role restriction.
2. **Faculty can create and delete Classes** (slcm_Faculty has create/delete on Classes and Office Hours Group). Is this intended, or should class creation stay with the academic office?
3. **slcm_Faculty can create and edit Faculty Announcements**, and can write their own and others' Faculty records (no row filter on Faculty). Intended?
4. **Two announcement sources.** The bell icon reads **Portal Announcement**; the Announcements page reads **Faculty Announcement**. Which one should faculty use?
5. **Unused settings.** About 35 fields on Faculty Portal Settings are not read by any code, for example: show_faculty_id_sidebar, show_department_sidebar, show_today_schedule, show_pending_evaluations, show_class_statistics, show_workload_summary, show_leave_status, show_student_performance_overview, show_upcoming_exams, the whole *Attendance Module* group (enable_attendance_marking, allow_attendance_edit_window_days, auto_close_session_minutes …), *Marks & Grading* (enable_marks_entry, marks_edit_approval_required …), *Assignments*, *Student Interaction* (office hours booking limits) and *Leave & Workload*. Remove them, or wire them up?
6. **User preferences are not saved from the portal.** `save_preferences` exists in `slcm/api/faculty_portal.py` but no page calls it; the Settings page shows only password options. Same for `get_dashboard_stats`, `get_student_marks_detail` and `save_student_marks` (old marks API, replaced by `slcm/api/faculty_grades.py`). Remove the dead endpoints?
7. **`/faculty-portal/course-offerings`** (`course-offerings.py/.html`) still exists, duplicates My Courses and is not in the menu. Delete?
8. **Ownership check on sessions without a class.** `save_attendance` checks ownership only through the session's *Class*. A session with no class (e.g. some Office Hours sessions) is not checked against the faculty. Should it also check *Instructor* or the Office Hours group's faculty?
9. **Admin preview** shows the first Active faculty's data to any System Manager without a Faculty record. Is that acceptable on production?
10. **Desk links in the portal** ("Link one here" / "Create faculty") point to `/slcm/faculty…`. Confirm these resolve on v16 (desk lives under `/desk`).
11. **Faculty number cards and charts** (Faculty My Classes, Faculty Active Classes, Faculty Attendance Trend …) are shipped as fixtures, but no Faculty Management workspace exists to show them. Where should they appear?
12. **Grade Appeal**: slcm_Faculty has read/write on Grade Appeal, but the portal has no Grade Appeal screen and the controller has no faculty step. What is the faculty's role in an appeal?

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| Faculty DocType, Auto Create User | `slcm/slcm/doctype/faculty/faculty.py` |
| Find the Faculty for the session user (7 lookups, back-fills User Account, admin preview) | `slcm/utils/faculty_portal.py` (`get_faculty_name`, `is_admin_preview`) |
| Portal pages | `slcm/www/faculty-portal/` (`_base.html` = layout + menu) |
| Portal API: attendance, condonation, venue booking, profile, password, dashboard drill-downs, calendar, notifications | `slcm/api/faculty_portal.py` |
| Grades page API | `slcm/api/faculty_grades.py` (reuses `slcm/slcm/page/examination_result/examination_result.py`) |
| Assessment Marks API | `slcm/api/faculty_assessment_marks.py` |
| Result access rules (view/edit/lock/status) | `slcm/slcm/utils/result_access.py` |
| Bulk attendance used by the portal | `slcm/api/bulk_attendance.py` |
| Attendance lock | `slcm/slcm/utils/attendance_lock.py` |
| Class participation, pending task flags | `slcm/slcm/utils/class_participation.py` |
| RFID activation | `attendance_session.py` → `activate_rfid` |
| Google Calendar sync | `slcm/slcm/doctype/time_table/google_calendar_sync.py` (`get_faculty_sync_classes`, `sync_faculty_calendar`) |
| Login (Google-only, role linking) | `slcm/utils/login_page.py`, `slcm/www/login.py`; old `/faculty/login` redirect in `slcm/www/faculty/login.py` |
| Portal role gate | `slcm/utils/portal_access.py` (`before_request` hook) |
| Row-level filters for faculty | `slcm/permissions.py` (`permission_query_conditions` in `hooks.py`) |
| Routes, role home page | `hooks.py`: `website_route_rules` (Faculty Portal block), `role_home_page` |
| Sidebar / desktop icon | `slcm/workspace_sidebar/faculty_management.json`, `fixtures/workspace_sidebar.json`, `fixtures/desktop_icon.json` ("Faculty Management") |
| Settings | `slcm/slcm/doctype/faculty_portal_settings/`, `faculty_portal_user_preferences/`, `faculty_announcement/` |

- Faculty is named by autoincrement, so the database returns an **int**; Link fields (`Classes.faculty`, `Attendance Session.instructor`) hold a **string**. Always compare with `get_faculty_name()`, which returns a string.
- `slcm/permissions.py` finds the faculty by `user_id` only, while the portal also matches by email. A faculty member who has never signed in (User Account empty) sees the portal but gets empty desk lists until `user_id` is back-filled.

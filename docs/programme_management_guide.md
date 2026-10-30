# Programme Management: User Guide

**Applies to:** SLCM v16, new academic flow (October 2026)
**Who this is for:** Academic office staff (Registrar, Academic Incharge) who set up the academic year, enroll students, create classes and timetables, and promote students.
**Where:** Desk → **Academics → Programme Management**

---

## 1. The flow at a glance

```
1. Academic Calendar     Academic Year → Term Master → Academic Term (+ Term Mapping)
2. Programme Structure   Programme → Section → Batch → Course
3. Enrollment            Student Master list → Enroll   (creates Student Enrollment)
4. Classes               Student Enrollment list → Action → Create Class
5. Timetable             Classes form → Time Table → Create Time Table
6. Attendance            Attendance Sessions created from the timetable
7. Year end              Promotion (promote / repeat)
   ↺ next year: back to step 4
```

Steps 1 and 2 are set up once per academic year, before any student is enrolled.

### Key ideas

| Term | Meaning |
|---|---|
| **Academic Year** | The calendar year of the institution, e.g. *AY 2026 -2027*. Exactly one is the **current** year. |
| **Term Master** | The programme's own term names, e.g. *Trimester I, II, III*. |
| **Academic Term** | A dated term inside an academic year, e.g. *Trimester II - AY 2026 -2027* (1 Nov – 31 Jan). |
| **Term Mapping** | Tells the system which programme term (Term Master) each year of study is in during an Academic Term. |
| **Batch** | The intake cohort, e.g. *2026*. It belongs to one academic year. |
| **Section** | A division of students, e.g. A, B, C. |
| **Student Enrollment** | **One record per student per programme**, kept for the whole programme. It is named by the Student ID (e.g. *B26001*). |
| **Academic Log** | The table inside a Student Enrollment that records the student's path: one row per term, with status *Upcoming / Ongoing / Completed / Redo / Dropped*. |
| **Class** | One course taught to one section (or one named group) in one term, e.g. *CLS-26-1-T2-A-00001*. |

---

## 2. Academic Calendar

### 2.1 Academic Year
*Academic Calendar → Academic Year → + Add*

| Field | What to enter |
|---|---|
| Academic Year Name | e.g. `AY 2026 -2027` (this becomes the record name) |
| Year Start Date / Year End Date | The full span of the academic year |
| Status | Active |
| Is Current Year | Tick for the year now running |

**Rules the system enforces**
- The end date must be after the start date.
- Academic years cannot overlap.
- Only **one** year can be *Is Current Year*, and it must be Active. Untick the old year first.

### 2.2 Term Master
*Search bar → Term Master → + Add*

Create each programme term once: `Trimester I`, `Trimester II`, `Trimester III`. These are reused every year.

### 2.3 Academic Term
*Academic Calendar → Academic Term → + Add*

| Field | What to enter |
|---|---|
| Academic Year | The year this term belongs to |
| Term Name | e.g. `Trimester II`. The record is named `Trimester II - AY 2026 -2027`. |
| Term No | 1, 2, 3 … (order of the term within the year) |
| Term Start Date / Term End Date | Dates of the term |
| Status | Active |
| **Term Mapping** (table) | One row per year of study, see below |

**Term Mapping** example for *Trimester II - AY 2026 -2027*:

| Year | Batch | Term (Term Master) |
|---|---|---|
| 1 | 2026 | Trimester II |
| 2 | *(empty = all other batches)* | Trimester V |

A row with no batch covers every batch in that year of study. A row with a batch overrides it for that batch only.

**Rules the system enforces**
- Term dates must fall inside the academic year.
- Terms of the same year cannot overlap.
- Term No must be unique within the year.
- One mapping row per Year + Batch.

> Saving an Academic Term updates the *Programme Term* on every student's Academic Log for that term, and the **Current Term** on Student Master.

> **Timetables can only be created inside the term dates.** Create every term of the year before scheduling classes.

---

## 3. Programme Structure

### 3.1 Programme
*Programme Structure → Programme*

| Field | Notes |
|---|---|
| Programme Code / Programme Name | e.g. `BALLB`. The name becomes the record name. |
| Level of Study | Undergraduate / Postgraduate / … |
| Programme Duration (in years) | **Required for the academic flow.** It limits the year of study (e.g. 5 for BALLB) and marks the final year for promotion. |
| Status | Active |

### 3.2 Section
*Programme Structure → Section*. One record per section name: `A`, `B`, `C`.

### 3.3 Batch
*Programme Structure → Batch*

| Field | Notes |
|---|---|
| Batch name | e.g. `2026` (record name) |
| Academic Year | The intake year |
| Status | Active |

*Total enrolled count* updates automatically as students are enrolled or dropped.

### 3.4 Course
*Courses & Enrollment → Course*

| Field | Notes |
|---|---|
| Course Name / Course Code | e.g. *Criminal Law*, `CL001` |
| Credit Value | Used in GPA calculation |
| Course Type | Core / Elective |
| Status | **Active.** Only active courses can be used in new classes. |

---

## 4. Enrolling students

Students must have **Registration Status = Completed** on Student Master before they can be enrolled.

*Courses & Enrollment → Student Master → list view → **Enroll***

The Enroll wizard has five steps:

| Step | What you do |
|---|---|
| **1. Academic Setup** | Academic Year (current year by default), Academic Term (the running term by default), Year of study, Programme, Batch |
| **2. Students** | Shows students whose registration is Completed, whose Student Master academic year matches, and who are not yet enrolled in this programme. Tick the ones to enroll. |
| **3. Student ID** | Enter the ID format with `#` for the running number, e.g. `B26###` → B26001, B26002 … IDs are given in alphabetical order. **Numbering:** *Fill gaps* (lowest free numbers) or *Continue after highest*. Existing IDs are kept unless you tick *Re-number*. |
| **4. Sections** | **Mid-off:** alphabetical blocks, split by room capacity. **One-by-one:** dealt out in turn. **Manual:** pick per student. **Upload:** download the template, fill in sections, upload. Tick *Keep each student's current section* to keep sections already set. |
| **5. Summary** | Check and confirm |

**What enrollment creates**
- A **Student Enrollment** named by the Student ID, with status *Enrolled*.
- An **Academic Log** row for each term of the chosen year: the chosen term *Ongoing*, earlier terms *Completed*, later terms *Upcoming*.
- On Student Master: Student ID, section, batch, programme, academic year, *Current Term* and *Year of Study* (e.g. "1st Year").

If one student fails (for example, the ID is already taken), the others are still enrolled, and the failures are listed with reasons.

### Changing a student's section
*Open the Student Enrollment → **Change Section***

Editing the Section field directly is blocked. The button records the move on the Ongoing term's remarks and in Student Master's *Section Update Log*.

### Dropping a student
*Student Enrollment list → tick rows → Action → set status **Dropped***

Open terms and courses become *Dropped*. On Student Master, Student Status becomes *Dropped* and Academic Status *Inactive*.

---

## 5. Creating classes

*Courses & Enrollment → Student Enrollment → list view → **Action → Create Class***

| Field | Notes |
|---|---|
| Class Type | **Section:** all students of one section. **Group:** students picked from any section, year or programme (e.g. electives, moot groups). |
| Academic Year / Academic Term | The term the class runs in |
| Programme / Year No | Programme and year of study |
| Section *(Section class)* or Group Name *(Group class)* | |
| Courses (table) | One row per course: course (type and credit fill in) + **faculty** |

For a Section class, the students load automatically. For a Group class, use **Find Students** (filter by programme, year, section) and add them.

**One Class is created per course**, all with the same students. Names follow `CLS-{YY}-{year}-T{term no}-{section}-#####`, e.g. `CLS-26-1-T2-A-00001`. Group classes use `G` in place of the section.

**What happens automatically**
- Each student's Student Enrollment gets an **Enrolled Courses** row: course, class, term, faculty and credits.
- The course status follows the term dates: *Upcoming*, then *Ongoing*, then *Completed*.

**Rules the system enforces**
- Only one Section class per course + term + section, and one Group class per course + term + group name. A duplicate is **skipped**, not created twice.
- A Section class can only contain students of its programme.
- Year No must be between 1 and the programme duration.

> **Note:** any active course can be added to a class. There is no curriculum check, so make sure the course belongs to the programme and year.

You can also open a class (**Classes** in the sidebar) and use **Get Students** to refresh its student list.

---

## 6. Creating the timetable

*Classes → open a class → **Time Table → Create Time Table***

| Field | Notes |
|---|---|
| Date, From Time, To Time | First session |
| Venue | Room for the class |
| Instructor | Defaults to the class faculty |
| Repeat | Never / Daily / Weekly / Monthly, with a *Repeats Till* date |
| Class Participation (optional) | Split the class into weekly participation groups |

**Before you create it, the preview shows every date and its status:**
- **OK**: the session will be created.
- **Holiday**: a non-teaching day in the Institutional Calendar. That date is skipped.
- **Venue clash**: the venue is already booked at that time. That date is skipped.
- **Faculty busy**: the faculty has another session. This is only a warning; the session is still created.

A problem on the **first** date blocks the whole series. Pick another date, time or venue.

**What timetable creation produces**
- One **Time Table** entry per date.
- One **Attendance Session** per date, which faculty use to mark attendance.

**View Time Table** on the class shows all sessions on a calendar.

---

## 7. Attendance (summary)

Attendance runs on the sessions created by the timetable.

| How | Where |
|---|---|
| Desk | **Student Attendance Tool** (pick the timetable session, mark present/absent) |
| Faculty | **Faculty Portal → Attendance** |
| RFID | Card swipe at the venue *(see Known limitations)* |

- Attendance **cannot be marked for future dates**.
- A session locks **24 hours** after it ends (configurable in *Attendance Settings*). After that, only an approved reopen allows changes.
- Attendance % = attended hours ÷ conducted hours. **75%** or more = eligible for exams (configurable).
- Students short of 75% can apply for **Condonation** or **FA / MFA** (from the Student Portal or desk). Approved hours count towards attendance, up to 100%.
- Condonation approvers are set in **Attendance Settings → Condonation** (Level 1 and Level 2, per programme).

---

## 8. Terms moving forward (automatic)

Every night the system:
- moves a student's *Ongoing* term to *Completed* once its end date has passed, and makes the next *Upcoming* term of the same year *Ongoing*;
- updates enrolled-course statuses to match the term dates.

The **last term of a year stays Ongoing until the student is promoted.**

---

## 9. Promotion (year end)

**Before promoting:**
- Create the next Academic Year and its Academic Terms, with Term Mapping for the next year of study.
- Publish the year's results.

Two ways to promote:

| Where | Use |
|---|---|
| **Promotion Management** page | Policy-based: fetch students, evaluate against the **Promotion Policy** (CGPA, backlogs, attendance, fee dues), review, override, then **Publish** |
| Student Enrollment list → **Action → Promote Students** | Direct promotion of the selected students; creates a **Promotion Run** (see *View Promotion Log*) |

**What promotion does**
- **Promote:** the same Student Enrollment gets new Academic Log rows for *Year + 1* in the next academic year. The old year's rows and courses become *Completed*.
- **Repeat:** the old year's rows become *Redo* and its courses *Carry Forward*. The same year starts again in the next academic year.
- Student Master's academic year and year of study update automatically.
- New-year courses are added when students are put into the new year's classes (back to step 4).

**Rules the system enforces**
- The target academic year must start after the current one.
- A final-year student cannot be promoted.
- Promoting twice to the same year is skipped as *Already Promoted*.

---

## 10. Quick checklist for a new academic year

- [ ] Academic Year created and marked *Is Current Year*
- [ ] Term Masters exist (Trimester I, II, III)
- [ ] All Academic Terms created with dates and Term Mapping
- [ ] Programme duration set; Sections and the new Batch created
- [ ] Courses created and Active
- [ ] Faculty and venues set up; holidays in the Institutional Calendar
- [ ] New students' registration *Completed*, then **Enroll**
- [ ] Classes created for every course, section and year
- [ ] Timetables created for every class
- [ ] Continuing students promoted from last year

---

## 11. Troubleshooting

| Problem | Cause and fix |
|---|---|
| Student not listed in the Enroll wizard | Registration Status is not *Completed*, the Student Master academic year differs, or the student is already enrolled in that programme. |
| "Term dates must fall inside Academic Year" | Adjust the term dates or the academic year dates. |
| Timetable won't save: date outside term | Timetables must fall inside the Academic Term dates. Check the term's start and end. |
| First timetable date blocked | Holiday or venue clash on the first date. Pick another date, time or venue. |
| Class not created ("skipped") | A class for that course + term + section (or group name) already exists. |
| "Use Change Section to move the student" | Section changes must go through the **Change Section** button. |
| Programme Term empty on Academic Log | Term Mapping is missing for that year of study / batch on the Academic Term. |
| Promotion: "Target Academic Year must start after…" | Create the next Academic Year first, with later dates. |
| Cannot mark attendance | The session is in the future, or locked (24 h after it ended). |

---

## 12. Known limitations (October 2026)

- **RFID attendance** does not yet match sessions created from Classes: sessions have no Room. Pending decision: link venues to rooms, or map devices to venues.
- RFID cards are read from Student Master's RFID field; cards issued as *Student RFID Card* are not used yet.
- **Promotion Policy** does not yet handle *Repeat year* or *Graduation* of final-year students. *Promote Students* (list action) does not apply a policy.
- Classes accept any active course (no curriculum per programme / year).
- The student and parent portal **Exam Schedule** only shows courses of a running term.
- Registration step *Pending Print & Scan* fails because it checks a `last_name` field that Student Master does not have.

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| Enrollment and Academic Log logic, promotion (`promote_enrollment`), class sync, nightly `advance_term_status` | `slcm/slcm/doctype/student_enrollment/student_enrollment.py` |
| Enroll wizard | `slcm/public/js/enrollment_wizard.js`, `slcm/slcm/doctype/student_master/enrollment_wizard.py` |
| Classes and Create Class | `slcm/slcm/doctype/classes/classes.py`, `student_enrollment_list.js` |
| Class timetable | `slcm/public/js/class_time_table.js`, `slcm/slcm/doctype/classes/class_time_table.py` |
| Term Mapping → programme term | `academic_term.py` (`get_programme_term`, `apply_term_mapping`) |
| Policy promotion | `slcm/slcm/page/promotion_management/`, `slcm/slcm/doctype/promotion_run/` |
| Sidebar / workspace | `slcm/workspace_sidebar/programme_management.json`, `slcm/slcm/workspace/programme_management/` **and** `fixtures/workspace.json` (the fixture copy is imported last and wins) |

- Read a student's current position with `get_current_log()` / `get_current_logs()`, or in SQL with `current_log_join()` / `year_log_exists()`. Never read `academic_year` / `year_no` from Student Enrollment: those columns were removed (stale columns may still exist in the database).
- Removed old-flow DocTypes (Term Configuration, Class Configuration, Course List, Curriculum, …) are listed in `docs/old_flow_doctype_removal_audit.md`.

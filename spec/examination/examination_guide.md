# Examination: User Guide

**Applies to:** Uniquad (SLCM v16), November 2026
**Who this is for:** Examination office staff (Controller of Examinations, Academics User, AAD) who set up exams, build the timetable, collect marks, publish results and run re-exams. Faculty and students are covered where they take part.
**Where:** Desk → **Examinations** (sidebar), with the **Exam Planner** page as the main screen.

---

## 1. The flow at a glance

```
0. One-time setup     Exam Component → Exam Assessment Type → Evaluation Schema → Grading Schema
                      → Examination Settings
1. Plan & courses     Exam Plan (one per Academic Term) → map every course to its schemas
2. Exam timetable     Exam timetable (rooms, ID ranges, invigilators) + Continuing Evaluation
                      Schedule + Barcodes → publish the timetable to students
3. Students & marks   Students from Classes → attendance eligibility → marks entry access
                      → faculty / office enter marks → Submit → Lock
4. Results & publish  Term GPA, Term %, Cumulative GPA / % → what students see → Publish
5. After results      Re-exam & improvement (one timetable, one window, one student list)
                      Grade Appeal (re-evaluation) from the Student Portal
   ↺ next term: a new Exam Plan; students still failing are carried forward to its re-exam
```

The Exam Planner opens steps in order. A step shows **Done** when its check passes (see 3.1). Step 5 opens once step 4 can be opened and is never "Done".

### Key ideas

| Term | Meaning |
|---|---|
| **Exam Plan** | One exam cycle for one Academic Term, e.g. *Trimester II - AY 2026 -2027 Examinations*. It covers every assessment of the term (internal and end term). Named by its Exam Name. |
| **Exam Component** | A part of a course, e.g. *Internal*, *End Term*. Type *Custom* or *Re Exam*. |
| **Exam Assessment Type** | What is marked, e.g. *Quiz*, *Project*, *End Term Paper*. Type *Assessment* or *ReExam*. |
| **Evaluation Schema** | How a course is marked: components, the assessments inside each, their maximum and effective marks, pass rules, and re-exam rules. |
| **Grading Schema** | How marks become grades and grade points. Has a regular composition and an optional re-exam composition. |
| **Course Schema Assignment** | The mapping of one course in one Exam Plan to an Evaluation Schema and a Grading Schema. |
| **Student Course Marks** | One record per student per course per Exam Plan. Holds the marks, total, grade, status (Draft / Submitted / Locked), attendance status and re-exam / improvement results. |
| **Access Result Settings** | Per Exam Plan + course: who may view and edit marks, deadlines, the course lock and faculty options. |
| **Student Result Publish** | Per student per Exam Plan: Term GPA, Term %, Cumulative GPA / %, and whether the result is published. |
| **Re-exam** | A further attempt for a failed (or absent) student. Repeated in later plans until the student passes. |
| **Improvement exam** | A further attempt for a student who passed, to raise the grade. |

---

## 2. One-time setup

*Examinations → 1. Setup (do first)*

Step 1 of the Exam Planner also shows this checklist, with counts, until every item exists. Its "Add" and "Create" buttons open quick dialogs; *Open full form instead* opens the normal form.

### 2.1 Exam Component and Exam Assessment Type

| DocType | Fields | Notes |
|---|---|---|
| Exam Component | Component Name, Component Type (*Custom* / *Re Exam*), Is Active | Named by Component Name |
| Exam Assessment Type | Type Name, Assessment Type (*Assessment* / *ReExam*), Is Active | Named by Type Name. A type named *Project* is treated specially (see 6.4). |

### 2.2 Evaluation Schema

| Section | Fields |
|---|---|
| Header | Schema Name, Description, Total Marks (default 100), Passing Marks (default 40) |
| **Schema Components** | Component, Label, Effective Max. Marks, Weightage, Passing Marks, **Consider For Pass/Fail** |
| **Assessment Configuration** | Component, Assessment Type, Label, Maximum Marks (marked out of), Effective Marks (counts as), Minimum / Passing Marks, Consider For Pass/Fail, Weightage, Enrollment (Auto / Manual) |
| **Re-Exam Configuration** | Component, Re-Exam Type Category, Assessment Type, Label, Maximum / Minimum / Passing / Effective Marks, Enrollment, **Substitute For** (an Exam Component), Substitute Weightage |
| **Re-exam Result** | *Replace substituted component* (default) or *Replace whole course total* |
| Calculation options | Consider higher of regular and revaluation marks; higher of regular and make-up; higher of regular and re-exam |

**Rules the system enforces**
- A re-exam row's *Substitute For* must be a component that exists in the schema (*Re-exam substitute not found*).
- In the planner dialog, Total Marks is worked out from the component marks on save.

### 2.3 Grading Schema

| Field | Notes |
|---|---|
| Schema Code | e.g. `G10-100`. The record name. |
| Maximum Marks | Required |
| Grading Type | Absolute / Relative-Manual / Relative-Auto |
| **Regular/Makeup Exam Composition** (grades) | Grade, Qualitative Meaning, From operator (`>=` / `>`) + Marks From, To operator (`<=` / `<`) + Marks To, **Grade Point**, **Failed**, Consider for SGPA |
| Use Re Exam Composition | When ticked, re-exam results are graded with the **Re Exam Composition** table instead |
| Re Exam Eligibility Criteria | Free-text criteria rows |

**Rules the system enforces**
- Every grade row needs Marks From and Marks To, and the range must be valid.
- The planner's quick dialog pre-fills an example 10-point scale.

### 2.4 Examination Settings

*Examinations → Examination Settings* (single record; System Manager and AAD can edit, Academics User can read)

| Setting | Default | What it does |
|---|---|---|
| Allow more than one Exam Plan per term | Off | When off, a second Exam Plan for the same term is refused. |
| Require Both Schemas | Off | Mapping a course needs both an Evaluation and a Grading Schema. |
| Allow Partial Mapping | On | Read by the mapping API. *See Open questions.* |
| Default Evaluation Schema / Default Grade Schema | — | Suggested for courses never mapped before. |
| Schema Lock Date | — | From this date, mapping changes are refused, except for users with the **Lock Override Role**. |
| Require Change Reason | Off | Changing a mapped course's schemas asks for a reason. |
| Notify on Schema Change / Notify on Unmap, Notification Recipients | Off | Emails the recipients when courses are mapped/changed or unmapped. |
| Enable Change Log, Log Retention (Months) | On, 12 | Writes a **Schema Change Log** for every schema change. |
| Default Re-exam Enrollment, Re-exam Max Marks Cap (%) | Auto, 0 | Read by the settings API only. *See Open questions.* |
| Courses Per Page, Show Unmapped Courses | 500, On | Course list paging for mapping. |
| Max CGPA for Improvement Exam | 7.0 | Students at or above this published CGPA cannot apply for improvement on the portal. 0 = no limit. Must not exceed the highest grade point in any Grading Schema. |
| Revaluation Fee per Paper | 0 | Fee raised for a *Re-evaluation* Grade Appeal. |
| Appeal Window (days after publishing) | 0 | Students can appeal only within this many days of publishing. 0 = no limit. |

### 2.5 Venues

Exam rooms are **Venue Master** records (Venue Name/Number, Venue Type, Capacity, Building, Floor, amenities, allowed roles). The same rooms are used by the class Time Table, so exams and classes cannot book a room at the same time.

---

## 3. The Exam Planner

*Examinations → 2. Run an exam → **Exam Planner*** (page `examination-planner`; roles System Manager, Academics User, AAD)

The **Examination Home** workspace (Home in the sidebar) lists plans with their step progress and a *Continue* button. The planner remembers the last plan you opened. With no step given it opens the first unfinished step. The Exam Plan form has **Map courses in Exam Planner** and an **Exam Planner** button group that jump to each step.

### 3.1 When a step shows "Done"

| Step | Done when |
|---|---|
| 1. Plan & courses | Every course taught in the term (any Class of the term) has both schemas mapped |
| 2. Exam timetable | Every mapped course has a timetable row with date, start, end and a venue or room |
| 3. Students & marks | Every mapped course has students **and** every student has a grade or is Detained / Absent |
| 4. Results & publish | Every Student Result Publish row of the plan is published |
| 5. After results | Never (always open) |

### 3.2 Creating an Exam Plan

*Exam Planner → **New Exam Plan*** (or Examinations → Exam Plans → New)

| Field | Notes |
|---|---|
| Academic Term | Required in the planner dialog |
| Exam Name | Required; becomes the record name. Default "{term} Examinations". |
| Status | Active / Inactive |

**Rules the system enforces**
- One Exam Plan per Academic Term, unless *Allow more than one Exam Plan per term* is on.
- An Exam Name that already exists is refused.

---

## 4. Step 1: Plan & courses

The courses come from the **Classes** of the plan's Academic Term (one line per course, across all sections). If the term has no Classes, the step says so; create Classes first (Programme Management).

| Group | What you do |
|---|---|
| **Not mapped yet** | Each course shows a suggested Evaluation and Grading Schema: the course's schemas in its latest other plan, else the Examination Settings defaults. **Map** one course, or **Map all N as suggested**. |
| **Mapped** | Read-only. **Change** edits inline (Save / Cancel). **Remove** unmaps after a confirm. |

**What happens automatically**
- A **Course Schema Assignment** is created per course (exam plan + course + term + schemas).
- A newly mapped course gets a timetable row placeholder and brings in the students already in its Classes as **Student Course Marks** ("Students added from Classes").
- Changing schemas writes a **Schema Change Log** (when enabled) and can email the recipients.

**Rules the system enforces**
- Schema Lock Date, Require Change Reason and Require Both Schemas (see 2.4).
- Clearing both schemas of a course deletes its assignment.

---

## 5. Step 2: Exam timetable

Three tabs: **Exam timetable**, **Continuing Evaluation Schedule**, **Barcodes**.

### 5.1 Exam timetable (classroom allocation sheet)

The grid follows the office's Excel sheet: a grey row per exam day, then one line per room with **Forenoon** on the left and **Afternoon** on the right. Session start times are edited in the header.

Each line is an **Exam Course Schedule** row on the Exam Plan:

| Field | Notes |
|---|---|
| Course | Link to Course. Optional: a paper that is not a course (e.g. a combined paper) is kept as **Paper (as on sheet)** text. |
| Year | Programme year, as text |
| Exam Date, Session (Forenoon / Afternoon), Start / End Time | |
| Venue | Venue Master room. Seat Capacity fills from the venue when empty; a lower manual value is kept. |
| Room (not in Venue Master) | Free text; not checked for clashes or seats |
| ID Nos. From / To | Student ID range sitting in this room |
| Invigilator | Faculty (status not Inactive), or text in *Invigilator (as on sheet)* |

Tools: **Add exam day**, **+ Forenoon / Afternoon line**, *Another room for this paper*, filters (day, session, venue, year, course; "Showing N of M"), **+ Add invigilator** (creates a Faculty; needs Photo; shown only to users who can create Faculty), **Clear timetable**, **Save timetable**.

**Student ID ranges:** a course split over rooms gives each row the students whose Student ID falls in its range. Rows of the course with no range share the students no range covers.

**Checks on save** (also run on the Exam Plan form):

| Check | Result |
|---|---|
| End time after start time | Error |
| Exam date inside the Academic Term (regular timetable only) | Error |
| Not a non-teaching day / weekly off in the Institutional Calendar | Error |
| No class (Time Table) in the venue at that time | Error |
| Students of all papers sharing the room fit its seats | Error |
| The same students are not in two exams at the same time (this plan, other plans of the term, re-exams) | Error |
| An invigilator is not on duty in two rooms at once | Error |
| Invigilator teaches a class at that time | Warning only |

### 5.2 Download and import the timetable sheet

- **Download sheet** gives the Excel sheet in the office's layout. A sheet imported and downloaded again comes back the same.
- **Import sheet** asks for the .xlsx and the **Exam length (hours)** (default 3; end time = session start + length). A preview lists lines, errors and notes. **Import N valid line(s), skip M** replaces the plan's timetable with the valid lines. **Download problems** exports the problem lines.
- Text that does not match a Course, Venue Master room or Faculty is kept as written.
- Every import writes an **Exam Sheet Import Log** (`ESIL-#####`): sheet, plan, file, counts and the issue rows. Status *Imported*, *Imported with skipped lines* or *Failed*.

### 5.3 Publishing the timetable

The publish bar asks **With invigilator** or **Without invigilator**. It sets *Publish timetable to students* and *Show invigilator names to students* on the Exam Plan. **Hide from students** unpublishes. The re-exam timetable has its own pair of flags.

### 5.4 Continuing Evaluation Schedule

The office's second sheet: per programme, one block per subject with its components (Course Faculty | Subject | Component | Marks | Due Date for Submission | Date for activities / Mid-Term Exam / Class Test | Extension Applicable | extra columns).

- Rows start from the mapped Evaluation Schemas ("From the Evaluation Schema, not saved yet"). **Use faculty from Classes** fills the faculty names.
- Extra columns can be added after *Extension Applicable*, renamed or removed (stored on the Exam Plan).
- **Save evaluation schedule** writes to the Active **Exam Assessment Schedule** (`EAS-#####`) of every programme that teaches the course. Each component is an **Exam Assessment Schedule Item**; faculty, SGD and remarks are an **Exam Assessment Course Note**.
- Evaluations are matched to schema assessments by label, then shared words, then order. End-term only pairs with end-term. Re-exam items are not touched, and items that already have marks are never deleted.
- **Download sheet / Download blank sheet / Import sheet** work like the timetable. On import you pick the course for unmatched subjects; unmatched ones left empty are skipped.

**Exam Assessment Schedule rules** (form and save)
- The term belongs to the chosen Academic Year; the Exam Plan is for the same term.
- Only one Active schedule per programme + term.
- Each course must have a Class under the programme and term; an assessment appears once per course.
- Deadlines in order: Assessment Date ≤ 1st Submission < 2nd Submission < Marks Entry Deadline.

### 5.5 Barcodes

Pick exam dates and courses, then:
- **Generate barcodes**: a random 6-digit barcode per student per course (`Exam Barcode`, `BC-YYYY-###`), unique within the plan. Existing barcodes are kept; only the copy count changes.
- **Download selected**: attendance / barcode Excel, **one sheet per exam date** or **one sheet per course**.

The standalone **Exam Barcode Sheet** page does the same (active plans only).

---

## 6. Step 3: Students & marks

One table per course: students in Classes, students in the plan, detained, barcodes, marks entered, status and evaluators. Clicking a course opens **Course Results** inline, with Previous / Next.

### 6.1 Students

| Action | What it does |
|---|---|
| **Add students from Classes** | Creates Student Course Marks for the Enrolled students of the course's Classes in the term, for every mapped course |
| Course Results → add / remove student, add by Registration IDs | Manual changes (flagged *Manually Added*) |

Student Course Marks are also kept in step with Classes: adding or removing a student in a Class updates the plan.

### 6.2 Attendance eligibility

**Update eligibility** reads **Attendance Summary** for the plan's term (attendance %, approved condonation and FA/MFA are already counted there).

- Not eligible → Attendance Status **Detained**.
- A Detained student who is now eligible → cleared.
- Left alone: students whose class has no hours yet, Absent students and Locked rows.

The result reads "N detained, N cleared, N without attendance yet". In Course Results, a student below the minimum attendance shows grade **AS**.

### 6.3 Marks entry access

**Marks entry access** opens the per-course Access settings. *Same settings for all courses…* applies one setting to every course and adds each course's Class faculty as evaluators (if it has none).

| Access Result Settings field | Effect |
|---|---|
| View Access, View Access Deadline | Faculty can see the course's marks until the deadline |
| Edit Access, Edit Access Deadline | Faculty can enter marks until the deadline |
| Status LOCKED / UNLOCKED | **Locked blocks everyone**, desk included |
| Auto Generate Grade Access | Faculty may auto-generate grades |
| Edit Grade Access | Faculty may override a grade (manually / upload) |
| Mask Student Information | Faculty see masked student details |
| Generate Grade Report | Faculty may download the grade report |
| Visible Exams | Exam types faculty may see |
| Evaluators | Class Faculty or Custom evaluators |

### 6.4 Entering marks

| Who | Where | Notes |
|---|---|---|
| Examination office | **Course Results** (inside step 3) | Cell-by-cell entry, Excel export / import, re-exam template export / import, grade upload, auto-generate grades, remarks, status |
| Faculty | **Faculty Portal → Grades** (`/faculty-portal/marks`) | Only courses they teach in the term, only their Class students, within Access Result Settings. Excel template download / import. |
| Faculty | **Faculty Portal → Assessment Marks** | 1st and 2nd submission marks per Continuing Evaluation item. See below. |
| Office (legacy results) | Student Course Marks list → **Bulk Import Marks** | Wizard that writes a Marks Import Log (see 6.6) |

**How the total and grade are worked out** (same code for desk, portal and the Student Course Marks form)
1. Per assessment: moderated marks win over marks.
2. With *higher of regular and revaluation*, the higher of the two counts. For an assessment type named *Project*, revaluation marks are a **deduction** instead.
3. Each assessment adds `marks × effective ÷ maximum` to the total.
4. **Fail rules:** an assessment marked *Consider For Pass/Fail* that is below its passing marks, or a component (*Consider For Pass/Fail*) whose weighted marks are below its passing marks once all its assessments have marks, gives the Grading Schema's failed grade.
5. **Absent** → grade **Ab**, total 0.
6. **Re-exam:** with *Replace substituted component*, the regular total with the substituted component swapped for the re-exam marks; with *Replace whole course total* (or no Substitute For), the re-exam rows alone. Updated Final Marks = the higher of regular and re-exam total. The updated grade uses the Re Exam Composition when the schema has one.
7. **Improvement:** improvement marks count when higher than the regular total and the updated final marks.

In Course Results, the Updated Final Marks cell opens **How the final marks were calculated** (desk only; students do not see it).

**Grade marks shown next to a grade** (one only, in this order): **Mfa** (MFA = Yes), **RR** (course carried from an earlier plan), **R** (paid re-exam registration in this plan), **I** (improvement applied).

**Assessment Marks (faculty portal)**
- The entry window opens when the assessment closes (2nd submission deadline, else 1st, else the assessment date) and closes at the item's Marks Entry Deadline (open if blank).
- Stored in Student Course Marks → **Assessment Marks** (one row per schedule item, with entered by / on).
- These marks are **not** added to the course total. *See Open questions.*

### 6.5 Status: Draft → Submitted → Locked

| Status | Who can edit |
|---|---|
| Draft | Office and faculty (within access) |
| Submitted | Office only. Faculty can set Draft ↔ Submitted for their students. |
| Locked | No one |

Step 4 (or the course) sets **Submitted** for all Draft rows, then **Locked** for all rows; locking also sets the course's Access Result Settings to LOCKED.

### 6.6 Bulk Import Marks (Marks Import Log)

*Student Course Marks list → **Bulk Import Marks*** (also *Examinations → Records & reports → Marks Import Log*)

| Wizard step | What you do |
|---|---|
| 1. Upload | File (.xlsx), Exam Plan, Evaluation Schema, Exam Component + Assessment Type, Re-exam Component + Assessment Type |
| 2. Validate | Rows are checked in the background: student, course, class |
| 3. Import | Valid rows are imported in the background; progress is shown live |

- Required columns: **Registration ID**, **Course Code**, **Term Name**. Also read: Batch Year, Total Marks, Grade, Grade Point, Re-Exam Grade, Re-Exam Total Marks.
- Imported rows are created **Submitted**, and their total and grade are kept as imported (not recalculated).
- Row statuses: Pending, Valid, Missing Student, Missing Course, Missing Class, Duplicate (Skip), Success, Failed. Log statuses: Staging, Queued, In Progress, Completed, Completed with Errors, Failed.
- The log form has **Retry Failed/Edited Rows**. A draft import can be discarded.

---

## 7. Step 4: Results & publish

The step shows a stats strip and an ordered checklist, then three tabs.

| Tab | What you do |
|---|---|
| **Term results** | **Generate** Term GPA, Term %, Cumulative GPA, Cumulative % (or *All results*) for every student of the plan |
| **What students see** | **Publish Result Setting** for the plan (see below) |
| **Publish** | Publish / unpublish per student or in bulk; send a result email with an Email Template |

**Generating results** (Student Result Publish, one per student per plan)
- **Term GPA** = Σ(grade point × credits) ÷ Σ credits, over courses with *Consider For SGPA* and a grade. The grade used is the updated grade when there is one.
- **Cumulative GPA** counts every plan, and a re-attempted course only once (latest attempt).
- **Cumulative %** uses the **CGPA Percentage Scale** where set. Cumulative values are also written to Student Master.

**Publish Result Setting**

| Field | Used by the portal |
|---|---|
| Publish Marks For Components | Yes: which component marks students see |
| Show Total Marks | Yes (also on the Grade Appeal page) |
| Show SGPA, Hide SGPA for students who failed a course | Yes |
| Show E-GradeSheet Download, Do not publish for unpaid fees, Do not publish without faculty feedback | Saved only. *See Open questions.* |

**What publishing does**
- Sets *Is Published*, with published by / on (or unpublished by / on).
- Students and parents see the plan under **Results** only when it is published.

**Consolidated report:** *Records & reports → Consolidated Report* (or the planner header button) downloads an Excel report by plan, academic year, programme, trimester or batch. See `spec/transcript/transcript_guide.md`.

---

## 8. Step 5: After results (re-exam and improvement)

Re-exam and improvement are one sitting: one timetable, one registration window, one student list. The old **Re Exam** and **Improvement Exam** pages now redirect here.

### 8.1 Still failing from earlier plans (carry forward)

A bar lists students whose latest record for a course is a fail in an earlier Exam Plan. **Bring all into this re-exam** (or per student) creates a Student Course Marks record in this plan with the **regular marks copied** (not the earlier re-exam marks), and the course mapping if missing.

**Rules the system enforces**
- A student who has passed a course gets no further re-exam (registration and carry forward refused).
- The next attempt must be in a later plan (by term start date).

### 8.2 Re-exam & improvement timetable

Same grid, checks and import / download as 5.1, stored in **Re-exam Schedules** on the Exam Plan. Differences:
- The term-dates rule is skipped.
- Students are those registered for the re-exam or the improvement exam; an ID range counts only them.
- Exams, re-exams and classes all avoid each other's rooms.
- Publish with its own flags (5.3).

### 8.3 Registration window

One window per course (or all courses): Deadline From / To, Payment gateway (Easebuzz / Razorpay), Improvement seats (Registration Limit). It is written to both **Re Exam Course Setting** and **Improvement Exam Course Setting**. Fees are **not** set here.

### 8.4 Re-exam & improvement students

One list with filters (type, course, enrolment, payment, name / ID).

| Who appears | |
|---|---|
| Re-exam | Students with a failed (or absent) result in the plan, and anyone registered for its re-exam |
| Improvement | Students registered for the plan's improvement exam |

| Action | What it does |
|---|---|
| **Enrol** / **Enrol selected** | Creates a **Re Exam Registration** (`REX-…`) or **Improvement Exam Registration** (`IMPX-…`). Fee per student is optional: with a fee, a **Fee Demand** is raised; with no fee, payment status is *Paid* (nothing due). |
| **Upload sheet** | CSV with Registration ID, Student Name, Course, Type, Fee. A preview shows *Enrol*, *Enrol + demand* or *Skip* with the reason. |
| **Mark paid** | Sets payment status Paid with an optional reference |
| **Block / Allow** (re-exam) | Writes a **Re Exam Student Override** (`is_allowed`, reason). A blocked student cannot register on the portal. |

**Rules the system enforces**
- One active registration per student + plan + course (re-exam and improvement each).
- Re-exam is refused once the student has passed the course.
- Improvement needs a pass in this plan and respects the seat limit.
- A paid Fee Demand marks the linked registration Paid. Deleting an unpaid registration cancels its demand.

### 8.5 Student Portal registration

| Page | Rules |
|---|---|
| **Re-exam** | Needs a Re Exam Course Setting for the course, before Deadline To, and a mapped course; one registration per course. Blocked students are refused. Earlier plans show only where the student registered; the latest record shows while still failing. |
| **Results → Improvement** | Needs a **published** result in the plan and published Cumulative GPA **below** *Max CGPA for Improvement Exam*. |

Receipts can be downloaded for both.

### 8.6 Re-exam and improvement marks

- Office: Course Results (re-exam columns, re-exam template import).
- Faculty: Faculty Portal Grades → re-exam sheet and improvement mark, **only for students with a Paid registration**, and not when Locked.
- Results recalculate as in 6.4 (steps 6 and 7).

---

## 9. Grade Appeal (revaluation)

Grade Appeal is the **single revaluation path**. **Revaluation Request is retired**: new ones are refused with "Revaluation Request is replaced by Grade Appeal". Old records are kept.

### 9.1 Student raises an appeal

*Student Portal → Grade Appeal* (menu shown when Student Portal Settings → *menu_grade_appeal* is on)

| Field | Notes |
|---|---|
| Exam Plan, Course | Only published results |
| Appeal Type | Re-evaluation / Marks Correction / Grade Change |
| Reason | At least 20 characters |
| Supporting Remarks | Optional |

**Rules the system enforces**
- The result must be published, and today must be within the **Appeal Window** after publishing (if set).
- The student must have Student Course Marks for that plan + course.
- One active appeal (Submitted / Under Review) per student + plan + course + appeal type.

**What happens automatically**
- The current grade and marks are snapshotted.
- For *Re-evaluation*, the fee is **Revaluation Fee per Paper** (one appeal = one paper). A **Fee Demand** with the *Revaluation Fee* component is raised on creation.

### 9.2 Office resolves it

*Grade Appeal form* (`GA-YYYY-#####`)

| Step | What you do |
|---|---|
| **Start Review** | Status → Under Review |
| **Open Marks** | Opens the student's Student Course Marks; change marks there or in Course Results |
| Resolve / Reject | Set status **Resolved** or **Rejected** and enter **Resolution Details** (required; the student sees it) |

On *Resolved*, **Grade After Review** and **Marks After Review** are copied from the current Student Course Marks. Resolved by / on are recorded. Re-opening clears them.

---

## 10. Portal views

| Page | Shows |
|---|---|
| Student Portal → **Exam Timetable** | End-term and re-exam papers of the student's courses, only after the plan's timetable is published. The student's own room from the ID range. Invigilator only if published with names. Only lines linked to a course. |
| Student Portal → **Assessment Schedule** | Continuing evaluation items (quizzes, projects, deadlines) for the student's courses |
| Student Portal → **Results** | Published plans only, per the Publish Result Setting; grade marks Mfa / RR / R / I |
| Parent Portal → **Results** | The ward's published results, same rules |
| Student Portal → **Re-exam**, **Grade Appeal** | See 8.5 and 9.1 |

A plan is shown for a course only when the student is enrolled in that course in the plan's term (Student Enrollment → courses).

---

## 11. Records and reports

*Examinations → Records & reports*

| Item | Use |
|---|---|
| Exam Dashboard (`exam-dashboard`, top of the sidebar under Home) | Count cards of records created (setup, plans, schedules, students & marks, results, re-exam & improvement), for all plans or one; a card opens the filtered list |
| Consolidated Report | Excel result report (see 7) |
| Student Course Marks | All marks records |
| Course Schema Assignment, Schema Change Log | Mappings and their change history |
| Marks Import Log | Bulk marks imports |
| Exam Sheet Import Log | Timetable / evaluation sheet imports |
| Course Schema Mapping Report, Schema Change Audit | Reports |

---

## 12. Who can do what

| Role | Can |
|---|---|
| System Manager, Academics User, AAD | Exam Planner, Course Results, Term Result, Publish Result, Barcode Sheet, Exam Dashboard (server methods check these roles) |
| System Manager, AAD | Edit Examination Settings, Grading Schema |
| slcm_Faculty | Faculty Portal Grades / Assessment Marks within Access Result Settings; read Evaluation Schema; read/write Grade Appeal |
| slcm_Programme Chair | Read Student Course Marks; edit Access Result Settings; read/write Grade Appeal |
| Academic Admin | Create / edit Grade Appeal |
| slcm_Student | Create Grade Appeal (portal); read own Re Exam Registration |
| slcm_Registrar, AAD | Marks Import Log |

---

## 13. Quick checklist for a term's exams

- [ ] Components, assessment types, Evaluation and Grading Schemas exist
- [ ] Examination Settings checked (improvement CGPA limit, revaluation fee, appeal window)
- [ ] Classes exist for the term
- [ ] Exam Plan created; every course mapped
- [ ] Exam timetable saved with no errors, and published
- [ ] Continuing Evaluation Schedule saved
- [ ] Students added from Classes; eligibility updated
- [ ] Barcodes generated and sheets downloaded
- [ ] Marks entry access set; marks entered
- [ ] All marks Submitted, then Locked
- [ ] Term results generated; What students see set; results Published
- [ ] Re-exam window set; failed students enrolled; re-exam timetable published
- [ ] Grade Appeals resolved

---

## 14. Troubleshooting

| Problem | Cause and fix |
|---|---|
| "{term} already has the Exam Plan …" | One plan per term. Use the existing plan, or turn on *Allow more than one Exam Plan per term*. |
| Step 1 says no Classes | Create Classes for the term in Programme Management. |
| "Schemas are locked as of …" | Schema Lock Date passed. A user with the Lock Override Role must make the change. |
| Timetable row: "… is outside {term}" | The exam date is outside the Academic Term. Re-exams are exempt. |
| Timetable row: "… is a non-teaching day" | Holiday or weekly off in the Institutional Calendar. |
| Timetable row: "… has a class at this time" | A Time Table class uses the venue. Pick another room or time. |
| Timetable row: "N students … but {room} has N seats" | Too many students for the room; split by ID range or use a bigger room. |
| Imported sheet rejects all dates | The sheet is for another term. Check the plan's term. |
| Room not checked for clashes | It is typed in *Room (not in Venue Master)*. Create the Venue Master room and pick it. |
| Faculty: "No exam plan is set up for this course yet" | The course is not mapped in a plan for that term. |
| Faculty: "Edit access … turned off" / "deadline has passed" / "locked" | Change Access Result Settings for the course. |
| Faculty: "marks have been submitted" | The office sets the student back to Draft. |
| Faculty cannot enter re-exam marks | The student's re-exam registration is not Paid. Mark it paid in step 5. |
| Student cannot see the timetable | The timetable (or re-exam timetable) is not published, or the line is not linked to a course. |
| Student cannot see results | The result is not published for that student. |
| Improvement: "must be published" / "only open to students with a CGPA below …" | Publish the result; check Max CGPA for Improvement Exam. |
| "… has already passed …; no further re-exam" | The latest record is a pass. Use improvement instead. |
| Appeal: "The appeal window for this result has closed" | Appeal Window days have passed since publishing. |
| No revaluation fee demand | Revaluation Fee per Paper is 0, or no Fee Component of type *Revaluation Fee* exists (logged in Error Log). |

---

## 15. Known limitations / Open questions

1. **Assessment Marks do not feed the result.** Faculty 1st / 2nd submission marks (Student Assessment Marks) are stored but not added to the course total (`api/faculty_assessment_marks.py`, `_save_student`: "these marks don't feed (yet)"). How should they reach Student Marks Entry?
2. **Publish Result Setting fields with no effect:** *Show E-GradeSheet Download*, *Do not publish for unpaid fees*, *Do not publish without faculty feedback* are saved but never read (`publish_result.py`, portal `results.py`).
3. **Examination Settings fields with no effect:** *Default Re-exam Enrollment* and *Re-exam Max Marks Cap (%)* are only returned by `get_exam_settings`; *Allow Partial Mapping* and *Show Unmapped Courses* are not used by the planner. `purge_old_change_logs` (Log Retention) is not scheduled in `hooks.py`.
4. **Portal re-exam fee.** The planner window no longer stores a fee, but the portal `initiate_re_exam_registration` still reads `re_exam_fee` from Re Exam Course Setting. A portal registration with no fee stays *Pending* (the office enrol path sets *Paid*), so faculty cannot enter its marks until someone marks it paid. Intended?
5. **Grade Appeal permissions.** The DocType grants Academic Admin, slcm_Student, slcm_Faculty and slcm_Programme Chair, but not Academics User or AAD, who run the rest of the exam flow. Grade Appeal is in the **Faculty Management** sidebar, not in Examinations.
6. **Detained students.** Detained has no grade rule in `compute_student_result` (only Absent → Ab). Detained rows count as "graded" in step 3. Are they still given barcodes and marks? What grade do they get on the result?
7. **Two CGPA calculations.** `term_result._compute_cumulative_stats` and `student_result_publish._calculate_cgpa` differ (also flagged in the transcript guide). Which is authoritative?
8. **Improvement grade** is looked up with the regular composition, not the re-exam composition (`compute_student_result`). Confirm.
9. **Exam Plan has no Academic Year / programme**; a plan covers all programmes of the term. Assessment Schedules are per programme. Confirm this is intended for multi-programme terms.
10. **Exam Barcode Sheet page** lists only Active plans; the planner shows all.
11. **Grading Type** Relative-Manual / Relative-Auto: no relative grading calculation was found beyond the access flag. Is relative grading supported?
12. Marks Import Log has a "Missing Offerings Count" field left over from Course Offering (removed).

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| Exam Planner page and step APIs | `slcm/slcm/page/examination_planner/` |
| Embedded screens (Course Results, Term Results, Publish, Result Settings, re-exam lists) | `slcm/public/js/exam/` (`slcm.exam_ui.<module>`) |
| Course mapping, settings, schema lock, change log | `slcm/slcm/doctype/exam_plan/exam_plan_api.py` |
| One-plan-per-term, timetable validation | `slcm/slcm/doctype/exam_plan/exam_plan.py` |
| Timetable rules, ID ranges, exam bookings | `slcm/slcm/utils/exam_timetable.py` |
| Excel sheets (timetable, evaluation schedule, import logs) | `slcm/slcm/utils/exam_sheets.py` |
| Result calculation (`compute_student_result`), eligibility, student sync, Course Results APIs | `slcm/slcm/page/examination_result/examination_result.py` |
| Access rules, grade marks (Mfa / RR / R / I) | `slcm/slcm/utils/result_access.py` |
| Faculty Grades / Assessment Marks | `slcm/api/faculty_grades.py`, `slcm/api/faculty_assessment_marks.py`, `slcm/www/faculty-portal/marks.*` |
| Bulk Import Marks | `slcm/slcm/doctype/student_course_marks/marks_bulk_import.py`, `student_course_marks_list.js` |
| Term GPA / CGPA, Consolidated report | `slcm/slcm/page/term_result/term_result.py` |
| Publish | `slcm/slcm/page/publish_result/publish_result.py` |
| Re-exam attempts and carry forward | `slcm/slcm/utils/reexam_attempts.py` |
| Step 5 list, window, enrol | `slcm/slcm/utils/after_results.py` |
| Re-exam / improvement fee demands | `slcm/slcm/fee/event_hooks.py`, `hooks.py` doc_events |
| Barcodes | `slcm/slcm/page/exam_barcode_sheet/` |
| Grade Appeal | `slcm/slcm/doctype/grade_appeal/`, `slcm/www/student-portal/grade_appeal.py` |
| Portal exam pages | `slcm/www/student-portal/exam_timetable.py`, `exam_schedule.py`, `re_exam.py`, `results.py`; `slcm/slcm/utils/exam_schedule.py` |
| Improvement eligibility (portal) | `slcm/api/student_portal.py` (`check_improvement_cgpa_eligibility`) |
| Sidebar / home | `slcm/workspace_sidebar/examinations.json`; Examination Home block in `slcm/fixtures/custom_html_block.json` |

- The sidebar is named **Examinations** to match the desktop icon label (v16 finds a sidebar by icon label).
- Student Course Marks recalculates only when its marks inputs change; bulk import sets `flags.keep_imported_result`, and `flags.recalculate_result` forces a recalculation.

# Promotion: User Guide

**Applies to:** Uniquad / SLCM v16, November 2026
**Who this is for:** Academic office staff (AAD, AAD Staff, Academic Incharge, Registrar) who move students from one year of study to the next at year end.
**Where:** Desk → **Academics → Promotions** (Promotion Management page, Promotion Policy, Student Promotion, Promotion Run). The **Promote Students** action is on the **Student Enrollment** list.

---

## 1. The flow at a glance

```
Before        Next Academic Year + its Academic Terms exist; results published
1. Policy     Promotion Policy for Programme + Academic Year + Year N → N+1 (status Active)
2. Preview    Promotion Management → pick Programme, Academic Year, Policy, From/To Year → Preview
3. Draft      Run Promotion → one Student Promotion per student, stage Draft
4. Review     Promotion Log tab → Promote anyway / Not promoted (with a reason)
5. Publish    Publish → promoted students move to Year N+1 in the next Academic Year
6. Fix-ups    Retry move for students whose move failed
   ↺ then put promoted students into the new year's Classes (Programme Management, step 4)

Alternative   Student Enrollment list → tick rows → Action → Promote Students
              (no policy check; creates a Promotion Run)
```

There are two ways to promote. They write different records.

| Route | Policy check | Record it writes | Applies the move |
|---|---|---|---|
| **Promotion Management** page | Yes, always (an Active policy is required) | **Student Promotion** (one per student) | On **Publish** |
| **Student Enrollment list → Promote Students** | No | **Promotion Run** + **Promotion Run Log** rows | At once, in a background job |

Both routes end in the same function, `promote_enrollment`, which moves the student's **Student Enrollment** forward.

### Key ideas

| Term | Meaning |
|---|---|
| **Promotion Policy** | The rules for one step, e.g. *BALLB, AY 2025 -2026, Year 1 → 2*. Each check can be switched on or off. |
| **Student Promotion** | One decision for one student for one step. It is also the per-student **Promotion Log**. Stage: *Draft*, *Published* or *Superseded*. |
| **Draft** | A decision that is saved but not applied. Students see no change and get no email. |
| **Published** | The decision is applied (promoted students are moved) and released. |
| **Superseded** | An older Published decision replaced by a newer one for the same student and step. Kept as history. |
| **Promotion Status** | *Promoted*, *Not Promoted*, *Conditional*, *Override - Promoted*, *Override - Not Promoted*. |
| **Enrollment Status** (on Student Promotion) | What happened to the student's enrollment: *Pending* (moves on publish), *Enrolled* (moved), *Failed* (move failed), *Not Applicable*. |
| **Promotion Run** | A batch job from the Student Enrollment list that promotes the ticked students. |
| **Backlog** | A course failed in this academic year's exams and not yet passed in a later attempt. |
| **Promote** | The same Student Enrollment gets Academic Log rows for *Year + 1* in the next academic year. No new enrollment is created. |
| **Repeat** | The current year's rows become *Redo* and the same year starts again. Exists in code only (see section 7). |

---

## 2. Promotion Policy

*Promotions → Setup → Promotion Policy → + Add*. Named `PP-YYYY-####`.

### 2.1 Policy details

| Field | What to enter |
|---|---|
| Policy Title | A readable name, e.g. `BALLB Year 1 → 2` |
| Programme | The programme this policy is for |
| Academic Year | The academic year being finished (the *source* year) |
| Status | *Draft*, *Active* or *Archived*. **Only Active policies can be used.** |
| From Year | The year of study being evaluated, e.g. `1` |
| To Year | The year students move to, e.g. `2` |
| Description / Notes | Free text |

### 2.2 Criteria

Each check is off by default. A check that is off shows *Not Checked* on the result.

| Check (switch) | Threshold field | Passes when | Where the number comes from |
|---|---|---|---|
| **CGPA** (*Enable CGPA Check*) | Minimum CGPA Required | CGPA ≥ minimum | `Student Master.current_cgpa` |
| **Backlogs** (*Enable Backlog Check*) | Maximum Backlogs Allowed (default 0) | backlogs ≤ maximum | Distinct courses failed in this academic year (see 2.3) |
| **Attendance** (*Enable Attendance Check*) | Minimum Attendance % Required | average % ≥ minimum | Average of `attendance_percentage` over the student's **Attendance Summary** rows for the academic year |
| **Course shortage** (*Enable Course Shortage Check*) | Max Courses with Attendance Shortage (default 2) | shortage courses ≤ maximum | Attendance Summary rows where `attendance_percentage < minimum_required_percentage` |
| **Carry-forward** (*Enable Carry-Forward*) | Max Allowed CF Courses (default 0) | CF courses ≤ maximum | Attendance Summary rows with FA/MFA hours (`total_fa_mfa_hours > 0`) that are still not exam-eligible (`eligible_for_exam = 0`) |
| **Fee due** (*Block Promotion on Fee Due*) | — | No Fee Demand in *Pending*, *Partially Paid* or *Overdue* | **Fee Demand** of the student (any academic year) |

### 2.3 How backlogs are counted

- A course is failed when its final grade is a fail grade in the course's **Grading Schema** (`failed = 1`). If no schema is assigned, only grade `F` counts.
- The final grade is the moderated / updated grade if present, else the original grade.
- Only exams whose **Academic Term** is in the policy's academic year count.
- Marks with enrollment status *Dropped*, *Detained* or *Migrated* are ignored.
- A course re-attempted in a later Exam Plan stays a backlog until a later attempt passes (that attempt may be in another academic year).

### 2.4 Advanced settings

| Field | Effect |
|---|---|
| **When Criteria Partially Fail** | *Not Promoted* (default) or *Conditional (Pending Review)*. Used only when **some but not all** enabled academic checks fail. |
| **Auto-update Student Year on Confirm** | On by default. If off, publishing records decisions only. No student is moved. |

**Rules the system enforces**
- To Year must be greater than From Year.
- CGPA check on → a Minimum CGPA must be set (0 is refused).
- Attendance check on → a Minimum Attendance % must be set (0 is refused).
- Course shortage and Carry-forward limits must be 0 or more.
- The page uses a policy only if it is **Active** and matches the chosen Programme and Academic Year.
- A policy whose From Year is 1–10 can only be used for exactly that From Year → To Year step.

---

## 3. Evaluation outcomes

For each student the system counts the enabled academic checks (CGPA, backlogs, attendance, course shortage, carry-forward) that fail.

| Result | When |
|---|---|
| **Promoted** | No enabled check fails (also when no check is enabled at all). |
| **Not Promoted** | Every enabled academic check fails. |
| **Conditional** | Some, but not all, checks fail **and** the policy says *Conditional (Pending Review)*. Otherwise these students are *Not Promoted*. |
| **Not Promoted** (fee) | Fee check is on and the student has an unpaid Fee Demand. This wins over every other result. |

- If only one academic check is on and it fails, the result is *Not Promoted*, never *Conditional*.
- The fee check is not counted when deciding between Conditional and Not Promoted. It only forces Not Promoted.
- The **Remarks** list each failed check in plain words, e.g. *"CGPA 4.20 below minimum 5.00; Outstanding fee due"*.

---

## 4. Promotion Management page (policy-based)

*Promotions → Promotion Management* (route `/desk/promotion-management`)

### 4.1 Selection

| Field | Notes |
|---|---|
| Programme, Academic Year | Pick these first. The Policy list fills with Active policies for them. |
| Promotion Policy | Picking a policy fills From Year and To Year (when the policy uses year levels 1–10). |
| From Year / To Year | Typing From Year sets To Year to From Year + 1. |

The page shows the policy's checks in a strip. *What do these mean?* explains each. *Edit policy* opens the policy.

**Which students are picked up**
- Student Enrollment status *Enrolled*.
- The enrollment's **current** Academic Log row is in the chosen Academic Year and Year of study = From Year.
- Student Master **Student Status = Active**.

### 4.2 Preview
Click **Preview**. Each student is evaluated and shown with CGPA, result and reason. **Preview never saves anything.**

### 4.3 Run Promotion (saves a Draft)
Click **Run Promotion**. The page evaluates again on current data and shows a summary (Promoted / Not promoted / Conditional). Confirm with **Save draft**.

- One **Student Promotion** is created per student, stage *Draft*.
- It stores the figures (CGPA, backlogs, attendance %, shortage courses, CF courses), each check result, the status and the remarks.
- **Enrollment Status** is *Pending* for promoted students when auto-update is on; else *Not Applicable*.
- Running again **replaces** this step's earlier Draft rows for these students. Published rows are not touched.
- Nothing changes for the student yet.

### 4.4 Promotion Log tab
Shows the current decision per student for the step. A Draft wins over the Published row it will replace. Superseded rows are hidden.

| Column | Shows |
|---|---|
| Result | Status, plus *Draft* and *Emailed* tags |
| Reason | Failed checks, or the override reason |
| Next year | *On publish*, the new enrollment link, or *Move failed* |
| Action | **Promote anyway**, **Not promoted**, **Retry move** (see 4.6) |

Filter chips split the list by outcome. **Download ▾** gives Excel lists: Promoted, Not promoted, Conditional, Move failed (if any), Full log. A list that contains drafts is titled *DRAFT (not published)*.

### 4.5 Publish
Click **Publish** on a Draft log. The dialog shows how many will move to Year N+1, stay in Year N, or are Conditional. Tick **Email each student their result** to send emails.

**What happens automatically on Publish**
- Each Published row for the same student and step that this Draft replaces becomes *Superseded*.
- For each **promoted** student, when auto-update is on:
  - The system checks Student Master's *Current Year* is still the From Year. If not, the row is marked *Failed* ("Not moved: student is no longer in Year N").
  - Otherwise it finds the student's Enrolled Student Enrollment whose current row is Year N, and the **next Academic Year** (the one that starts right after the current one).
  - It calls `promote_enrollment` (see section 6). On success Enrollment Status = *Enrolled* and *New Enrollment* links the enrollment.
  - On any error the change is rolled back for that student only. Enrollment Status = *Failed*, the error goes to Remarks and the Error Log.
- Not Promoted and Conditional rows get Enrollment Status *Not Applicable*. **Their enrollment is not changed.**
- Every row becomes *Published*, with Published By / On.
- If email was ticked, a background job emails each student with an email address:
  - Promoted: "promoted to N Year of {programme}".
  - Conditional: "under review".
  - Not promoted: the reasons as a list, and "contact the office".
  - Promoted students whose move **failed are not emailed**.
  - *Student Notified On* is stamped when the email is queued.

**Discard draft** deletes the step's Draft rows. Nothing was applied, so nothing else changes.

### 4.6 Overrides
From the log, **Promote anyway** or **Not promoted**. A **reason is required**.

| Stage | Promote anyway | Not promoted |
|---|---|---|
| **Draft** | Status → *Override - Promoted*, Enrollment Status → *Pending* (if auto-update on). Applied on publish. | Status → *Override - Not Promoted*, Enrollment Status → *Not Applicable*. |
| **Published** | Applied **now**: the student is moved as in Publish. Option to email the student. | Allowed only if no next-year enrollment was made. If Student Master's year was already moved to the To Year, it is set back to the From Year. Option to email. |
| **Superseded** | Refused | Refused |

- The override reason is stored with a time and user stamp, and *Manual Override* is ticked.
- Overriding to the status the student already has is refused ("already promoted" / "already not promoted").
- *Not promoted* on a Published row with Enrollment Status *Enrolled* is refused. The office must revert that enrollment by hand first.
- Conditional students are resolved only through these two buttons.

### 4.7 Retry move
For Published, promoted rows with Enrollment Status *Failed*: **Retry move** (one row) or **Retry failed moves** (all).
- Auto-update must be on for the policy.
- A policy-based *Promoted* row (not an override) is **re-checked** on current data first. If the student no longer meets the policy, the retry is refused.
- Override rows are honoured as they are.
- Optionally emails students who moved now and were not emailed before.

### 4.8 History tab and Official Report
- **History** lists every step run for the chosen Programme + Academic Year: counts, drafts, last run and last publish. Open a row to see its log.
- **Official Report** (header button, also *Download Report* in the sidebar) downloads an Excel *Promotion List*:
  - One sheet per year of study.
  - Sections: *Promoted to N Year*, *Conditional — pending review*, *Re-admitted to N Year* (the Not Promoted students).
  - Term-wise columns of failed (F) and attendance-shortage (AS) courses, and C / C+ improvement courses.
  - Optional university name at the top. Drafts are left out unless *Include draft* is ticked (then marked DRAFT).
  - If no decision exists yet, it lists the currently enrolled students per year instead.

### 4.9 On Student Master
The Student Master form shows a **Progression & Promotion** card: year and term position, the year-end eligibility under the matching Active policy (same engine as the page), and the latest non-superseded decision. Before the last term of the year it is marked *projected*.

---

## 5. Promote Students (Student Enrollment list)

*Student Enrollment list → tick rows → **Action → Promote Students***

| Step | What happens |
|---|---|
| Select | Tick enrollments. All must be of **one programme**. Rows with no Batch are left out (you are asked to continue with the rest). |
| Dialog | Pick **Target Academic Year**. A read-only preview shows the courses that already have classes in that year for Year + 1. Missing classes do not block promotion. |
| Promote | Confirm. A **Promotion Run** (`PR-YYYY-#####`) is created with status *Queued* and a background job starts. |

The job works in batches of 25 students. For each student, in order:

| Check | Log result | Reason code |
|---|---|---|
| Academic Log already has the target academic year | Skipped | Already Promoted |
| Current year = programme duration (final year) | Skipped | Other |
| `promote_enrollment` succeeds | Promoted | — |
| `promote_enrollment` raises an error | Failed | Other (traceback in detail) |

When done, the run is *Completed* (nothing skipped) or *Completed with Errors*. A crash sets *Error* with the traceback. The user who ran it gets a realtime alert.

**No policy is checked here.** `create_and_queue` always leaves *Promotion Policy* empty.

### On the Promotion Run form
| Button | Effect |
|---|---|
| **Promote Anyway** (row) / **Promote Selected** | Calls `promote_enrollment` for the row. Row → *Promoted*, *Resolved*, action *Manually Promoted*. |
| **Mark Exempt** / **Mark Selected Exempt** | Row → *Resolved*, action *Marked Exempt*. The student is **not** moved. A reason can be entered. |
| **Retry Unresolved** | Tries again for unresolved Skipped / Failed rows (still skips final year and already promoted). |

*View Promotion Log* on the list opens the Promotion Run list.

---

## 6. What promotion changes (`promote_enrollment`)

Both routes call this function. It works on **one Student Enrollment** and is atomic (a failure rolls back everything for that student).

**Promote (the only mode used by the UI)**
- The current year's open log rows (*Ongoing* / *Upcoming*) in the current academic year become *Completed*.
- That academic year's enrolled course rows become *Completed* (except *Carry Forward*, *Withdrawn*, *Dropped*).
- New Academic Log rows are added for **Year + 1** in the target academic year: one per Active Academic Term. The term running today is *Ongoing* (else the next to start, else the last), earlier ones *Completed*, later ones *Upcoming*. A year with no terms gets one *Ongoing* row with no term.
- Enrollment status is set to *Enrolled*.
- On save, Student Master is updated from the new current row: *Academic Year*, *Current Year*, *Year of Study* (e.g. "2nd Year"), *Current Term*, Student Status *Active*.
- New-year courses are **not** added here. They are added when the student is put in the new year's classes.

**Rules the system enforces**
- If the log already has a live row in the target academic year, nothing changes (returns "not moved"). This is how double promotion is avoided.
- The target academic year must **start after** the current one.
- If Year + 1 is greater than the programme's *Programme Duration*, it stops: "is in the final year … There is no next year to promote to." (No limit if duration is blank.)
- There must be an Academic Log to promote from.

---

## 7. Repeat year and final year

**Repeat year**
- `promote_enrollment(..., repeat=True)` exists: all current-year rows become *Redo* (except *Dropped*), current-year courses become *Carry Forward*, and the **same** year is added in the target academic year.
- **No screen calls it.** Publishing a *Not Promoted* decision does not repeat the year. The student's enrollment simply stays where it is. The *Re-admitted* section of the Official Report is a list only.

**Final year**
- Promotion Run: final-year students are *Skipped* with "Final year (Year N) of {programme}; nothing to promote to."
- Promotion Management: there is no special handling. A promoted final-year student fails to move, so the row shows *Move failed* with the final-year message.
- Graduation is done by setting the Student Enrollment status to *Completed* (list action). That closes open log rows and sets Student Master *Student Status = Graduated*. It is not part of promotion.

---

## 8. Permissions and roles

| What | Who |
|---|---|
| **Promotion Management** page | System Manager, Academics User, AAD, AAD Staff |
| Preview, log, history, downloads | Read on Student Promotion |
| Run Promotion (save draft) | Create on Student Promotion |
| Publish, overrides, retry move | Write on Student Promotion |
| Discard draft | Delete on Student Promotion |
| **Student Promotion** / **Promotion Policy** DocTypes | System Manager, AAD: full. AAD Staff: all but delete. Academics User: create, read, write (no delete). |
| **Promotion Run** DocType | System Manager, AAD: full. AAD Staff, slcm_Academic Incharge: all but delete. slcm_Programme Chair: read, print, export. |
| Promotion Run server actions (create, promote anyway, exempt, retry) | System Manager, slcm_Academic Incharge, AAD, AAD Staff |
| **Promote Students** / **View Promotion Log** buttons on the list | System Manager, slcm_Academic Incharge only (client check) |
| **Promotions** desktop icon | AAD, AAD Staff, System Manager |

So AAD and AAD Staff can run Promotion Runs on the server but do not see the list button. Academics User and AAD Staff cannot discard a draft.

---

## 9. Where it appears in the menus

| Place | Entries |
|---|---|
| **Promotions** sidebar | Home · *Run Promotions:* Promotion Management, Download Report · *Setup:* Promotion Policy · *Records:* Student Promotion, Promotion Run |
| Programme Management sidebar | Promotion Run (and a *Promotion* section with Promotion Policy, Promotion Run in the page sidebar) |
| Master sidebar | Promotion Policy |
| Number cards | Active Promotion Policies, Students Promoted, Students Not Promoted, Promotions Pending Review, Promotion Enrollment Failures, Promotion Runs with Errors |
| Charts | Promotion Outcome Distribution, Promotions Over Time, Promotion Runs by Status, Promotion Exceptions by Reason |
| Dashboards | Programme Dashboard (Promotion runs group), Uniquad Overall Dashboard (Promotion section) |

---

## 10. Quick checklist for year-end promotion

- [ ] Next Academic Year created (starts after the current one)
- [ ] Its Academic Terms created, Active, with Term Mapping for the new year of study
- [ ] Exam results final (grades and moderation done)
- [ ] Attendance Summary up to date (incl. FA/MFA)
- [ ] Fee Demands up to date, if the fee check is used
- [ ] Programme Duration set on the Programme
- [ ] One **Active** Promotion Policy per programme + academic year + year step
- [ ] Preview → Run Promotion → review → Publish
- [ ] Clear all *Move failed* rows (Retry move)
- [ ] Decide every *Conditional* student
- [ ] Put promoted students into the new year's Classes

---

## 11. Troubleshooting

| Problem | Cause and fix |
|---|---|
| Policy list is empty | No **Active** policy for that Programme + Academic Year. Set the policy status to Active. |
| "Promotion Policy … is for Year 1 → 2, not Year 2 → 3" | The From / To Year do not match the policy. Pick the right policy or years. |
| "No active students found for the selected filters" | No enrollment is *Enrolled* with its current row in that academic year and year, or Student Status is not Active. |
| Student missing from Preview | Their current Academic Log row is in another year / academic year, or the enrollment is not Enrolled. |
| "There are no Draft decisions to publish" | Already published, or discarded. Run Promotion again to make a new draft. |
| *Move failed*: "no Academic Year starts after …" | Create the next Academic Year, then **Retry move**. |
| *Move failed*: "Target Academic Year … must start after …" | Academic Year dates are wrong. Fix the dates, then retry. |
| *Move failed*: "is in the final year" | The student is in the last year of the programme. Mark them *Not promoted* and handle graduation separately. |
| *Move failed*: "Not moved: student is no longer in Year N" | Student Master's Current Year changed after the draft. Run Promotion again. |
| Retry refused: "No longer meets the policy" | Data changed since the draft. Run Promotion again, or use *Promote anyway*. |
| "…is already enrolled in … Revert that enrollment manually" | You tried *Not promoted* on a student who was already moved. Undo the Academic Log change by hand first. |
| Publish says decisions were recorded but nobody moved | *Auto-update Student Year on Confirm* is off on the policy. |
| CGPA check fails for everyone | `Student Master.current_cgpa` is empty (counts as 0). Publish results first. |
| Promotion Run row *Skipped — Already Promoted* | The enrollment already has the target academic year. Nothing to do. |
| Promote Students button not visible | Only System Manager and slcm_Academic Incharge see it. |

---

## 12. Known limitations / Open questions (November 2026)

1. **Repeat year has no UI.** `promote_enrollment(repeat=True)` is only used in tests (`slcm/slcm/tests/test_programme_management.py`). Publishing *Not Promoted* leaves the enrollment unchanged. The Programme Management guide (section 9) describes Repeat as part of promotion; in code it is not reachable from any screen. Decide whether Not Promoted should trigger Repeat. (`student_enrollment.py` `promote_enrollment`, `promotion_management.py` `publish_promotion`)
2. **Graduation of final-year students** is not handled by the page. They fail the move. (`promotion_management.py` `_apply_year_promotion`)
3. **To Year is not used for the move.** `promote_enrollment` always moves to Year + 1. A policy like Year 1 → 3 would look for an enrollment in Year 2 and fail. (`promotion_management.py` `_promote_enrollment`)
4. **Target academic year is automatic** on the page: the next Academic Year by start date. It cannot be chosen. (`_next_academic_year`)
5. **"Next year's Batch" wording.** Page dialogs, the `enrollment_status` description and Retry messages say students are "enrolled into next year's Batch". The code does not change the Batch and does not create a new enrollment; it adds log rows to the same enrollment. (`promotion_management.js`, `student_promotion.json`)
6. **"Term-to-term" wording.** The page header, the module docstring and the Student Master card say Promote Students does term-to-term moves. In code it moves the student to the **next year of study** (`promotion_run.py` `create_and_queue`). Term moves inside a year are done by the nightly `advance_term_status`.
7. **Promote Students dialog text** says "with that year's courses added". Courses are only added when the student is put in classes. (`student_enrollment_list.js` line ~823)
8. **Policy branch of Promotion Run is dead code.** `create_and_queue` never sets `promotion_policy`, so `_evaluate_student`, the fee check and reason codes *Attendance Shortage*, *Backlog*, *CGPA Shortfall*, *Fee Due* are never used there. *Manual Hold* and *No Target Batch* are never set anywhere. The form's "How this works" text still mentions a policy and "next term's Batch". (`promotion_run.py`, `promotion_run.js`)
9. **Promotion Run fields never filled:** Batch, Source Term, Target Term (Programme Dashboard lists Source/Target Term). (`promotion_run.py`, `programme_dashboard.py`)
10. **Role mismatch for Promote Students.** The list button shows only for System Manager and slcm_Academic Incharge; the server also allows AAD and AAD Staff. The page roles include Academics User; the Promotion Run DocType does not. (`student_enrollment_list.js`, `promotion_run.py` `ALLOWED_ROLES`)
11. **Student Promotion field labels.** `programme` is labelled *Batch* and links **SLCM Batch**; `batch_year` is labelled *Batch* but stores Student Master's *Year of Study*. (`student_promotion.json`, `confirm_promotion`)
12. **Attendance is a plain average** of per-course percentages, not hours-weighted. Students with no Attendance Summary get 0%. (`_attach_metrics`)
13. **Fee check covers all Fee Demands**, not only the policy's academic year. (`_fee_due_students`)
14. **Shortage default.** A blank *Max Courses with Attendance Shortage* falls back to 2 in code; the field default is also 2.
15. **FA / MFA meaning.** The page help text expands FA/MFA as "First Attempt" / "Medical First Attempt". Attendance docs elsewhere use FA/MFA for condonation; confirm the wording. (`promotion_management.js` line ~392)
16. **Policies with calendar years.** Code tolerates policies whose From Year is above 10 (e.g. 2026) and skips the year match. Unclear if any exist; consider blocking them.
17. **Sidebar patch path.** The patch listed in `patches.txt` (`slcm/patches/v2_0/fix_promotion_policy_sidebar.py`) imports `slcm/slcm/workspace/promotion_policy/promotion_policy.json`, which no longer exists (the workspace is now `promotions`). A newer copy lives at `slcm/slcm/patches/v2_0/fix_promotion_policy_sidebar.py` but is not the one registered. Check fresh-site migrate.
18. **Academic Log year options** are 1–5 (`student_academic_log.json`). A programme longer than 5 years cannot be promoted past Year 5.
19. **Student Promotion.js and Promotion Policy.js** are empty stubs; there are no form-level actions.

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| Page APIs: `fetch_students`, `confirm_promotion`, `publish_promotion`, `discard_draft`, `save_override`, `retry_enrollment`, `get_promotion_log`, `get_promotion_history`, `download_promotion_list`, `download_formatted_promotion_list` | `slcm/slcm/page/promotion_management/promotion_management.py` |
| Evaluation engine: `_evaluate_student`, `_evaluate_year_promotion`, `_attach_metrics`, `_course_result_rows`, `_fee_due_students` | same file |
| Student eligibility card: `get_student_progression` (called from `get_academic_progress`) | same file; `slcm/slcm/doctype/student_master/student_master.py`, `student_master.js` |
| Page UI | `slcm/slcm/page/promotion_management/promotion_management.js` (+ `.json` for roles) |
| Move logic: `promote_enrollment`, `build_year_log`, `_sync_student_master_status`, nightly `advance_term_status` | `slcm/slcm/doctype/student_enrollment/student_enrollment.py` |
| Promote Students dialog | `slcm/slcm/doctype/student_enrollment/student_enrollment_list.js` (`open_promote_students_dialog`) |
| Promotion Run job: `create_and_queue`, `process_promotion_run`, `promote_anyway`, `mark_as_exempt`, `bulk_resolve`, `retry_unresolved` | `slcm/slcm/doctype/promotion_run/promotion_run.py`, `promotion_run.js` |
| DocTypes | `slcm/slcm/doctype/promotion_policy/`, `student_promotion/`, `promotion_run/`, `promotion_run_log/` (child table) |
| Re-exam attempt logic used for backlogs | `slcm/slcm/utils/reexam_attempts.py` |
| Patches | `slcm/patches/v2_0/student_promotion_stage.py` (old rows → Published), `slcm/patches/v2_0/fix_promotion_policy_sidebar.py` |
| Sidebar / icon | `slcm/workspace_sidebar/promotions.json`, `slcm/desktop_icon/promotions.json`, `slcm/slcm/workspace/promotions/` |
| Number cards / charts | `slcm/fixtures/number_card.json`, `slcm/fixtures/dashboard_chart.json`, listed in `hooks.py` |
| Tests | `slcm/slcm/tests/test_programme_management.py` (`test_promotion_*`, repeat, final year) |

- Publish locks the Draft rows with `SELECT … FOR UPDATE`, so a second publish at the same time finds nothing.
- Each student's move runs in its own savepoint. A failure is rolled back and the `frappe.throw` popup is dropped from the message log; the error is kept on the row and in Error Log ("Student Promotion: enrollment creation failed").
- Student Master *Current Year* is compared as both `1` and `Year 1`.
- Emails are sent by `_notify_promotion_results` on the `short` queue, with reference to the Student Promotion.
- Read a student's position with `get_current_log()` / `current_log_join()`; never from columns on Student Enrollment.

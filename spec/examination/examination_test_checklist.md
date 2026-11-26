# Examination: Test Checklist

**Applies to:** Uniquad (SLCM v16), November 2026
**Who this is for:** QA and the examination office, testing the exam flow end to end.
**Where:** Desk → **Examinations → Exam Planner**, Faculty Portal, Student Portal.

Rules behind each test are in `spec/examination/examination_guide.md` (section numbers in brackets).

---

## 0. Test data

- One Academic Term with dates, two programmes, Classes for at least 3 courses with Enrolled students and faculty.
- Venue Master rooms with known capacity (one small, e.g. 5 seats).
- One holiday inside the term in the Institutional Calendar.
- Attendance Summary rows: one student below the minimum, one above, one course with no hours yet.
- A Fee Component of type *Revaluation Fee* and one of type *Examination Fee*.
- Users: an Academics User, a faculty (slcm_Faculty) who teaches one of the courses, a student, a parent.

---

## 1. Setup and settings [2]

| # | Scenario | Expected result |
|---|---|---|
| 1.1 | Create Exam Components, Assessment Types, an Evaluation Schema and a Grading Schema from planner step 1 dialogs | Records created; the setup checklist disappears once all exist |
| 1.2 | Evaluation Schema re-exam row with *Substitute For* = a component not in the schema | Save refused: "Re-exam substitute not found" |
| 1.3 | Grading Schema row without Marks From / To | Save refused |
| 1.4 | Examination Settings: Max CGPA for Improvement = 12 on a 10-point scale | Refused: above the highest grade point |
| 1.5 | Max CGPA for Improvement = -1 | Refused: cannot be negative |

## 2. Exam Plan and mapping [3, 4]

| # | Scenario | Expected result |
|---|---|---|
| 2.1 | New Exam Plan for the term | Plan created; planner opens step 1 |
| 2.2 | Second plan for the same term, setting off | Refused: "{term} already has the Exam Plan …" |
| 2.3 | Same, setting *Allow more than one Exam Plan per term* on | Allowed |
| 2.4 | Plan for a term with no Classes | Step 1 says "No Classes in this term yet" |
| 2.5 | Map all as suggested | Course Schema Assignments created; "Students added from Classes" lists counts; Student Course Marks exist |
| 2.6 | Change a mapped course with *Require Change Reason* on | Reason asked; Schema Change Log row with old/new schemas and reason |
| 2.7 | Map one schema only with *Require Both Schemas* on | Refused: "Both Evaluation Schema and Grade Schema are required" |
| 2.8 | Set Schema Lock Date to today, change a mapping as a normal user | Refused: "Schemas are locked as of …" |
| 2.9 | Same, as a user with the Lock Override Role | Allowed |
| 2.10 | Remove a mapping | Confirm shown; course returns to "Not mapped yet" |
| 2.11 | All courses mapped | Step 1 shows Done |

## 3. Exam timetable [5.1–5.3]

| # | Scenario | Expected result |
|---|---|---|
| 3.1 | Row with end time before start time | Error: "End time must be after start time." |
| 3.2 | Exam date outside the term | Error: "… is outside {term} …" |
| 3.3 | Exam on the holiday | Error: non-teaching day |
| 3.4 | Exam in a room with a class at that time | Error: "{room} has a class …" |
| 3.5 | Course with more students than the small room | Error: "N students … but {room} has N seats" |
| 3.6 | Two papers in one room whose students together exceed seats | Error naming the other course ("together with …") |
| 3.7 | Two courses sharing students at the same time | Error: "N student(s) also sit …" |
| 3.8 | Same invigilator in two rooms at the same time | Error: "Invigilator … is also on duty …" |
| 3.9 | Invigilator teaches a class at that time | Orange warning only; saves |
| 3.10 | Split one course over two rooms with ID ranges | Each row counts only its range; seat check uses those counts |
| 3.11 | Venue picked, Seat Capacity blank | Seat Capacity filled from Venue Master |
| 3.12 | Seat Capacity typed lower than the venue | Lower value kept |
| 3.13 | Room typed as text (not Venue Master) | Saved; no clash or seat checks |
| 3.14 | Book a class Time Table in a room during a saved exam | Class creation reports the venue clash |
| 3.15 | Download sheet, then import it unchanged | Same lines come back; Exam Sheet Import Log *Imported* |
| 3.16 | Import a sheet with some bad lines | Preview lists problems; "Import N valid line(s), skip M"; log *Imported with skipped lines*; Download problems gives the bad lines |
| 3.17 | Import a sheet for another term | All dated lines rejected for term dates |
| 3.18 | Paper text that is not a course | Kept as Paper text; not shown on the student portal |
| 3.19 | All mapped courses scheduled | Step 2 shows Done |
| 3.20 | Publish without invigilator | Students see the timetable, no invigilator names |
| 3.21 | Change to with invigilator | Students see invigilator names |
| 3.22 | Hide from students | Portal shows the plan as not published |

## 4. Continuing Evaluation Schedule [5.4]

| # | Scenario | Expected result |
|---|---|---|
| 4.1 | Open the tab after mapping | Rows from the Evaluation Schemas, marked "not saved yet" |
| 4.2 | Fill dates and marks, Save | Active Exam Assessment Schedule per programme teaching the course, with items |
| 4.3 | Course taught in two programmes | Both programmes' schedules updated |
| 4.4 | Add a custom column, save, download | Column kept and in the sheet |
| 4.5 | Two columns with the same name | Refused: "Two columns are called …" |
| 4.6 | Remove a component that already has marks | Item is not deleted |
| 4.7 | Second Active schedule for the same programme + term (form) | Refused: active schedule already exists |
| 4.8 | 2nd submission deadline before the 1st | Refused |
| 4.9 | Marks Entry Deadline before the last submission deadline | Refused |
| 4.10 | Import the office sheet with an unknown subject | Asked to pick the course; left empty → skipped |
| 4.11 | Student Portal → Assessment Schedule | Items of the student's courses shown |

## 5. Students, eligibility, barcodes [5.5, 6.1, 6.2]

| # | Scenario | Expected result |
|---|---|---|
| 5.1 | Add students from Classes (again) | "N added, M already in the plan"; no duplicates |
| 5.2 | Add a student to a Class | Student Course Marks created in the plan |
| 5.3 | Update eligibility | Low-attendance student Detained; course with no hours counted "without attendance yet" |
| 5.4 | Student becomes eligible (condonation approved), Update eligibility | Detained cleared |
| 5.5 | Absent or Locked student, Update eligibility | Unchanged |
| 5.6 | Generate barcodes | 6-digit barcodes, unique in the plan |
| 5.7 | Generate again with copies = 2 | No new barcodes; copies updated; message says all already have barcodes |
| 5.8 | Download one sheet per date / per course | Excel with one sheet per date / per course |

## 6. Marks entry [6.3–6.5]

| # | Scenario | Expected result |
|---|---|---|
| 6.1 | Apply the same access to all courses | Access Result Settings per course; Class faculty added as evaluators |
| 6.2 | Faculty opens Grades for a course they do not teach | Not listed / refused |
| 6.3 | Faculty enters marks within access | Saved; total and grade recalculated |
| 6.4 | Mark above the assessment maximum | Refused |
| 6.5 | Edit Access off, or Edit deadline passed | Faculty refused with the reason |
| 6.6 | View Access off | Faculty cannot see the course |
| 6.7 | Course LOCKED | Desk and faculty both refused: "Result entry is locked" |
| 6.8 | Student set to Submitted | Faculty refused; desk can edit |
| 6.9 | Faculty template import with an extra student | Row error: "Student is not enrolled in your class." |
| 6.10 | Assessment with weightage: max 20, effective 10, marks 15 | Adds 7.5 to the total |
| 6.11 | *Must pass* assessment below its passing marks | Grade = the schema's failed grade even if the total passes |
| 6.12 | Component pass rule, one assessment still empty | No component fail yet |
| 6.13 | Mark student Absent | Grade Ab, total 0 |
| 6.14 | Moderated marks entered | Moderated value used instead of marks |
| 6.15 | Project assessment with revaluation marks | Revaluation marks deducted |
| 6.16 | Updated Final Marks cell (desk) | "How the final marks were calculated" popup matches the stored result |
| 6.17 | Faculty Assessment Marks before the submission deadline | "Marks entry opens after the submission deadline" |
| 6.18 | After the Marks Entry Deadline | "The marks entry deadline … has passed" |
| 6.19 | Save 1st/2nd submission marks | Stored in Assessment Marks with entered by/on; course total unchanged (known gap) |
| 6.20 | Step 4: Submit all, then Lock all | Draft → Submitted; all Locked; access LOCKED |
| 6.21 | Bulk Import Marks with a missing Registration ID column | Refused: missing required columns |
| 6.22 | Bulk import with an unknown student | Row *Missing Student*; valid rows import as Submitted with grade as in the file |
| 6.23 | Retry Failed/Edited Rows on the log | Only failed rows re-run |

## 7. Results and publishing [7]

| # | Scenario | Expected result |
|---|---|---|
| 7.1 | Generate All results | Student Result Publish per student with Term GPA, Term %, Cumulative GPA / % |
| 7.2 | Course with *Consider For SGPA* off | Excluded from Term GPA |
| 7.3 | Student with a re-attempted course | Counted once (latest attempt) in Cumulative GPA |
| 7.4 | CGPA Percentage Scale set | Cumulative % from the scale; Student Master updated |
| 7.5 | Before publishing, student opens Results | Plan not shown |
| 7.6 | Publish one student | Shown on student and parent portals; published by/on set |
| 7.7 | Unpublish | Hidden again; unpublished by/on set |
| 7.8 | Show SGPA on, Hide SGPA for failed on, student with a fail | SGPA hidden for that student |
| 7.9 | Publish Marks For Components = End Term only | Only that component's marks shown |
| 7.10 | All published | Step 4 shows Done |

## 8. Re-exam and improvement [8]

| # | Scenario | Expected result |
|---|---|---|
| 8.1 | Step 5 list | Failed / absent students listed under Re-exam |
| 8.2 | Save window for all courses | Re Exam and Improvement Course Settings created with dates, gateway, seats |
| 8.3 | Enrol a failed student with fee 500 | Re Exam Registration *Pending*; Fee Demand 500 |
| 8.4 | Enrol with no fee | Registration *Paid*; no demand |
| 8.5 | Enrol the same student again | Refused: registration already exists |
| 8.6 | Enrol a passed student for re-exam | Refused / skipped: already passed, use Improvement |
| 8.7 | Enrol a failed student for improvement | Skipped: has not passed, use Re-exam |
| 8.8 | Improvement beyond the seat limit | Skipped: seats full |
| 8.9 | Upload CSV with mixed rows | Preview shows Enrol / Enrol + demand / Skip with reasons |
| 8.10 | Pay the Fee Demand | Registration becomes Paid |
| 8.11 | Block a student | Student Portal re-exam registration refused |
| 8.12 | Portal re-exam after Deadline To | "The registration deadline for this course has passed." |
| 8.13 | Portal improvement with unpublished result | "must be published" |
| 8.14 | Portal improvement with CGPA ≥ the limit | Refused with the limit and CGPA |
| 8.15 | Faculty enters re-exam marks for an unpaid registration | Refused: no paid re-exam registration |
| 8.16 | Re-exam marks, *Replace substituted component* | End-term swapped for re-exam marks; Updated Final = higher of the two |
| 8.17 | *Replace whole course total* | Re-exam rows alone form the re-exam total |
| 8.18 | Improvement marks higher than the total | Updated Final Marks = improvement marks; grade mark I |
| 8.19 | Re-exam timetable on a date after the term | Accepted (term rule skipped) |
| 8.20 | Re-exam room clashes with a regular exam of another plan | Error |
| 8.21 | Student fails the re-exam; open the next term's plan step 5 | Listed under "Still failing from earlier exam plans" |
| 8.22 | Bring all into this re-exam | New Student Course Marks with regular marks copied, no re-exam marks; grade mark RR |
| 8.23 | Carry forward into an earlier plan | Refused: must be a later plan |
| 8.24 | Student passes, then tries another re-exam | Refused: already passed |
| 8.25 | Old Re Exam / Improvement Exam page routes | Redirect to planner step 5 |

## 9. Grade Appeal [9]

| # | Scenario | Expected result |
|---|---|---|
| 9.1 | Student appeals an unpublished result | Refused: only published results |
| 9.2 | Reason shorter than 20 characters | Refused |
| 9.3 | Appeal after the Appeal Window | Refused: window closed |
| 9.4 | Re-evaluation appeal with fee 300 set | Appeal `GA-…`, fee 300, Fee Demand with Revaluation Fee component |
| 9.5 | Same appeal type again while active | Refused: active appeal exists |
| 9.6 | Different appeal type, same course | Allowed |
| 9.7 | Start Review | Status Under Review |
| 9.8 | Resolve without Resolution Details | Refused |
| 9.9 | Change marks, then Resolve | Grade / Marks After Review filled; resolved by/on set |
| 9.10 | Re-open a resolved appeal | Resolved by/on and revised values cleared |
| 9.11 | Create a new Revaluation Request | Refused: replaced by Grade Appeal |

## 10. Access and roles [12]

| # | Scenario | Expected result |
|---|---|---|
| 10.1 | User without System Manager / Academics User / AAD calls a planner or Course Results method | "Not permitted" |
| 10.2 | Academics User edits Examination Settings | Read-only |
| 10.3 | Student opens another student's results URL | Only own data shown |

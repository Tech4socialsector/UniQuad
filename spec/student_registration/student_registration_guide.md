# Student Registration: User Guide

**Applies to:** Uniquad (SLCM v16), November 2026
**Who this is for:** Registration staff (REGO, FINO, Registration, Documentation, Hostel and IT officers), the Registrar and the Academic Affairs office (AAD). They take a selected candidate through registration until the student can be enrolled.
**Where:** Desk → **Academics → Student Registration** (sidebar), Desk → **Master** (setup sidebar), Desk → **Student Services** (Placement, Hostel Management, Student Portal)

How a candidate applies, is selected and pays the admission fee is covered in [spec/admission/](../admission/admission_portal_restructure.md). This guide starts when the **Student Master** record exists. Enrolling students into a programme, classes and promotion are in the [Programme Management guide](../programme_management/programme_management_guide.md).

---

## 1. The flow at a glance

```
Admission  Applicant → Applicant Fee Assignment → Convert to Student   (creates Student Master)
1. Selected                 Student Master created
2. Pending REGO             Submit for REGO          (Registration User / Student)
3. Pending FINO             Approve Documents        (REGO Officer)
4. Pending Registration     Approve Finances         (FINO Officer)
5. Pending Print & Scan     Complete Registration    (Registration Officer)
6. Pending Residences       Upload Documents         (Documentation Officer)
7. Pending IT               Allocate Room            (Hostel Admin)
8. Final Verification REGO  Allocate Assets          (IT Admin)
9. Completed                Final Approval           (Registration Officer)
   → student can now be enrolled (Programme Management, step 3)
   ↺ Completed → Re-Open → Pending REGO   (System Manager only)
```

Each step is a change of the **Registration Status** field on Student Master. Every change needs a remark and is written to the student's **Status History**.

### Key ideas

| Term | Meaning |
|---|---|
| **Student Master** | One record per student. It holds registration, finance, bank, personal, contact, parent, residence, qualification, document and status data. Named `STUD-YYYY-#####`. |
| **Registration Status** | The registration step the student is in. A link to *Workflow State*. Read-only on the form; change it with **Update Registration Status**. |
| **Student ID** | The `registration_id` field, e.g. *B26001*. Given at enrollment or with **Generate Student ID**. Student Enrollment records are named by it. |
| **Student Status / Academic Status** | Separate from registration. Both become *Active* when registration is *Completed*. |
| **Status History** | The *Student Workflow History* table: new state, previous state, who, when, remarks. |

---

## 2. Where a Student Master comes from

| Source | Registration Status set to | Notes |
|---|---|---|
| Admission: **Applicant Fee Assignment → create invoice**, or **Convert to Student** on the Applicant | `Active` | `slcm/api/service/applicant_to_student.py`. Copies applicant data, sets Student Status and Account Status *Active*, gives the user the `slcm_Student` role, marks the Applicant *Enrolled*. One Student Master per application number; blocked if an *Active* student with the same email belongs to another application. *See open question 1.* |
| PACE: convert a PACE applicant | `Active` | See the [PACE guide](../pace/pace_guide.md). PACE students are never enrolled in degree programmes. |
| Desk: **Student Master → + Add** | `Selected` (if left empty) | First Name and Email are mandatory. |
| Admission withdrawal | `Closed` | `slcm/admission/utils/withdrawal_sync.py`: Student Status *Withdrawn*, enrollment *Dropped*. |

**What happens on a new record**
- If a batch and programme are set and no fee is given, the current **Fee Structure** for the programme, year, category (quota) and nationality is applied. Total, discount, net fee and outstanding balance are filled in, and a row is added to *Fee Structure Change History*.
- *Current Year* defaults to 1, and *Year of Study* to "1st Year" (not for PACE students).

---

## 3. The registration workflow

### 3.1 Moving a student to the next step
*Student Master → open a student → **Registration → Update Registration Status***

The dialog shows only the next step(s) your role may set. Pick the new status, enter **Remarks** (mandatory), confirm.

*Student Master list → tick students → **Update Status*** does the same for many students. The students must share a common next step. Each student is updated on its own; the result lists successes and failures.

### 3.2 Steps, roles and checks

| Move into | Button label | Allowed roles | The system checks |
|---|---|---|---|
| Pending REGO | Submit for REGO | slcm_Student, slcm_Registration User | — |
| Pending FINO | Approve Documents | slcm_REGO Officer | Aadhaar Card, PAN Card, Std X Marksheet and Passport Size Photo are uploaded |
| Pending Registration | Approve Finances | slcm_FINO Officer | Fee Payment Status is *Paid* or *Partially Paid* |
| Pending Print & Scan | Submit for Print & Scan | slcm_Registration Officer | First name, last name, date of birth, gender, email, phone, batch and programme are filled *(see Known limitations)* |
| Pending Residences | Upload Documents | slcm_Documentation Officer | ID Card Issued = Yes, and Aadhaar Verified is ticked |
| Pending IT | Allocate Room | slcm_Hostel Admin | Hostellers only: Hostel Room is set and Keys Handed Over is ticked |
| Final Verification REGO | Allocate Assets | slcm_IT Admin | Official Email ID is set |
| Completed | Complete Registration | slcm_Registration Officer | Aadhaar, PAN, Offer Letter and Student Declaration are uploaded **and** verified; ID Card Issued = Yes; Official Email ID is set |
| Re-Open | Re-Open | System Manager | — |

> The button labels in the dialog come from `get_available_status_actions`. They are one step off from the names in `student_master_workflow.json` (for example the JSON calls the move into *Pending Print & Scan* "Complete Registration"). The table above shows what users see.

**Rules the system enforces**
- Steps must be taken in order. Skipping a step gives "Invalid status transition … Please follow the workflow sequence."
- **System Manager** may set any status from any status ("Set to …"), but the checks in the table still apply.
- Remarks are mandatory for every change.
- A change made by saving the form directly (not through the dialog) is also checked for order, except for System Manager.

### 3.3 What each change records
- **Status History** row: new state, previous state, user, time, remarks.
- A *Workflow* comment on the form: "Status changed from X to Y by Z".
- *Status Updated By / On* on the record.

### 3.4 When registration is Completed
- **Student Status** and **Academic Status** become *Active*.
- An email "Registration Completed – {first name}" goes to the student's email and every parent email, with the **Registration Slip** PDF attached.
- The student can now be enrolled (*Student Master list → **Enroll***). Enrollment refuses students whose registration is not *Completed*, whose status is *Inactive*, who are PACE students, or who have no programme.

### 3.5 Who sees which students (desk list)

| Role | Sees |
|---|---|
| System Manager, slcm_Registrar, Accounts User, AAD, AAD Staff | All students |
| slcm_REGO Officer | Pending REGO |
| slcm_FINO Officer | Pending FINO |
| slcm_Registration Officer | Pending Registration, Final Verification REGO |
| slcm_Documentation Officer | Pending Print & Scan |
| slcm_Hostel Admin, slcm_Hostel Warden | Pending Residences |
| slcm_IT Admin | Pending IT, Final Verification REGO |
| slcm_Registration User | Selected |
| slcm_Faculty | Active students of the classes they teach |
| slcm_Programme Chair | Academically active students |
| slcm_Student | Own record only |

Field groups are protected by permission level: quota, offer-letter / declaration verification and Karnataka category fields (level 1: Registrar, System Manager, AAD, FINO read-only); scholarship amount and all bank fields (level 2: Accounts User, FINO Officer, System Manager); *Is Hosteller* (level 3: Hostel Admin, Hostel Warden, System Manager).

---

## 4. Student Master form

### 4.1 Tabs

| Tab | Holds |
|---|---|
| Registration | Student ID, RFID UID, application number, admission type, quota, academic status |
| Finance | Scholarship, fee structure and totals, fee payment status, fee structure history, fee invoices, payment log, stipend log, **savings bank and loan account details** |
| Programme Mapping / Current Academic Progress | Current CGPA and percentage; year of study; a progress panel built from the student's enrollments |
| Personal / Contact / Parent / Guardian | Personal details, contact details, the *Parents* table |
| Residence | Hostel, room, bed, allocation dates, meal plan, agreement signed, keys handed over |
| Academic Qualification | Class X and XII details |
| Account | Student status, ID card issued, laptop issued and laptop details |
| Status History | Status History table and Registration Status |
| Documents | Personal and educational documents with *Verified* ticks, declarations, official email, addresses, academic year, programme, PACE programme, section, section update log, income and category certificates |
| Admission | NLSAT/CLAT rank details copied from admission, batch, current term, scholarship beneficiary |

### 4.2 Form buttons

| Group | Button | What it does |
|---|---|---|
| Registration | Update Registration Status | The dialog in 3.1 |
| Registration | ID Card | Opens the student's active *ID Card Generation*, or starts a new one with the default Student template |
| Registration | Download Registration Slip | PDF with print format *Student Registration Slip* |
| Fees | Fee Invoices & Receipts, Payment Logs, Sync Fee Invoices | Fee records of the student |
| Fees | Change Fee Structure | System Manager / slcm_FINO Officer only. A reason is mandatory; recalculates totals and logs the change. |
| Parents | Send Parent Login Invite | Invites the parents in the *Parents* table who have an email |
| — | Enroll | Shown only when the student passes the enrollment check (3.4) |

### 4.3 List view buttons

| Button | What it does |
|---|---|
| Update Status | Bulk status change (3.1) |
| Delete | System Manager only |
| Enroll | The Enroll wizard (see the Programme Management guide) |
| Download Slip | Registration Slips for up to 5 selected students |
| Generate Student ID | Numbers every student of the chosen programme + academic year alphabetically as `<programme code><academic year><###>`, e.g. `BALLB20262027001`. Re-running re-sorts everyone; existing IDs are not kept. Also available as an Excel template download / upload. System Manager only to apply. *See open question 4.* |
| Student Map (RFID), Remove RFID Card | Map or unmap RFID cards (see [spec/attendance/](../attendance/attendance_workflows.md)) |
| Bulk Upload Section | Download a section template, fill it, upload. Each change is logged in the *Section Update Log*. |
| Parent Login Invite | Opens a *Parent Login Invite Tool* for the selected students |

---

## 5. Student bank details

Two sets of fields on the **Finance** tab.

| Section | Fields |
|---|---|
| Savings Bank Account Details | Account Number, Account Holder Name, Bank Name, Branch Name, IFSC Code, Passbook (attachment), *Bank Details Submitted by Student*, *Submitted On* |
| Loan Account Details | Availed Education Loan? (Yes / No), Loan Scheme (*PM Vidyalaxmi* / *Others*), Specify Other Scheme, Loan Account Number, Holder Name, Bank, Branch, IFSC Code, Passbook |

Account numbers and IFSC codes are **masked** fields.

### 5.1 Student submits once (Student Portal)
*Student Portal → Profile → Bank Details → **Add Bank Details***

- All savings fields are required, plus *Availed Education Loan?*.
- If a loan was availed: scheme, loan account number, holder, bank, branch and IFSC are required; *Others* also needs the scheme name.
- Passbooks are optional uploads: PDF, JPG or PNG, uploaded privately.
- After submit the card shows "Submitted on …" and a lock. The student can no longer edit. Account number and IFSC are shown as `•••• 1234`.

### 5.2 Office edits
Staff with level-2 access (Accounts User, slcm_FINO Officer, System Manager) edit the fields on the form. To let the student submit again, untick **Bank Details Submitted by Student**.

**Rules the system enforces** (desk and portal)
- IFSC must be exactly 11 letters or digits. It is stored in capitals.
- Spaces are removed from account numbers.
- Once any savings detail is entered (or the details were submitted), Account Number and IFSC Code become required.
- Savings and loan account numbers must differ.
- An account number can belong to only one student (savings or loan). Office users see which student already has it; students see only "already registered to another student".
- If *Availed Education Loan* is not *Yes*, all loan fields are cleared on save.

---

## 6. Master (setup sidebar)

*Desk → **Master***. Visible to slcm_Registrar, slcm_Registration Officer, slcm_Programme Chair, Campus Admin, Admission Admin and System Manager. It groups setup records used by every module:

| Section | Links |
|---|---|
| Academic Calendar | Academic Year, Academic Term, Academic Holiday |
| Academic Structure | Programme, Section, Batch (*SLCM Batch*), Course |
| People | Student Category, Gender, Skill, Faculty, Student Master |
| Assessment & Grading | Exam Component, Exam Assessment Type, Grading Schema, Course Schema Assignment, CGPA Percentage Scale |
| Attendance & Examination | Attendance Settings, Condonation Reason, Examination Settings, Publish Result Setting, Access Result Settings, Promotion Policy |
| Institution Settings | Admission Settings, Transcript Settings |
| Portals | Student Portal Settings, Faculty Portal Settings, Faculty Portal User Preferences, Faculty Announcements, Parent Portal Settings, Parent Login Invite Tool |
| Insights & Tools | Uniquad Overall Dashboard, Data Entry Map, Uniquad Dashboard |
| Users & Access | Roles & Permissions |

The academic setup records are explained in the [Programme Management guide](../programme_management/programme_management_guide.md#2-academic-calendar).

---

## 7. Student Registration sidebar and workspace

*Desk → Academics → **Student Registration***. The desktop icon is granted to AAD, AAD Staff and System Manager.

| Sidebar link | Opens |
|---|---|
| Home | The Student Registration workspace |
| Academic Year, Academic Term, Department (*SLCM Department*), Faculty, Programme, Course, Batch (*SLCM Batch*) | Setup lists |
| Student Master, Student Enrollment | Student lists |

The **workspace** shows:
- Overview cards: Total Students, Active Enrollments, Active Programs, Active Courses; shortcut to Parent Login Invite Tool.
- **Registration pipeline**: one number card per status (Draft … Re-Open).
- Charts: *Student Registration Status*, *Student Enrollment by Program*.
- Shortcuts to the academic setup lists, Student Master and Student Enrollment.

---

## 8. Student Services

*Desk → **Student Services*** is a folder icon (Registrar, Registration Officer, Campus Admin, Admission Admin, Hostel Admin, Hostel Warden, Placement Officer). It contains three sidebars:

| Sidebar | Roles (icon) | Links |
|---|---|---|
| **Hostel Management** | Hostel Admin, Hostel Warden, Campus Admin, Admission Admin | Hostel, Hostel Room, Hostel Bed, Hostel Allocation |
| **Placement** | Placement Officer, Campus Admin, Admission Admin | Student Placement Profile, Placement Opportunity, Shortlist Upload, Placement Event, Placement Application, Company Contact, Company Interaction, Company (*SLCM Company*) |
| **Student Portal** | Registrar, Registration Officer, Campus Admin, Admission Admin | Open Student Portal, Student Portal Settings, Student Announcement, Student Leave Applications |

### 8.1 Hostel Allocation and registration
A **Hostel Allocation** (student, hostel, room, bed, from date, agreement signed, keys handed over, status) writes back to Student Master on every save:
- Status *Allocated*: *Is Hosteller* ticked; hostel, room, bed, dates, agreement and keys copied.
- Any other status: hostel fields cleared, *Vacated Date* set from the To Date.
- Deleting the allocation clears the fields if the student is still in that room.

This is how the **Pending IT** check (room + keys for hostellers) is met.

**Rules:** the room must belong to the hostel and the bed to the room; an occupied bed or full room is refused.

### 8.2 Other services (summary)

| Record | Notes |
|---|---|
| Student Leave Applications | Student, from/to dates, reason; status *Pending / Approved / Rejected* with reviewer and remarks. Students create them from the portal. |
| Student Announcement | Type, priority, publish/expiry date, audience: all students, programmes, batch years or named students. Expiry cannot be before publish. |
| Student Placement Profile | One per student: programme, batch year, CGPA, internships, skills, resume; status *Draft / Verified / Locked*. |
| Placement Opportunity / Application | Opportunity open between start and end; a student can apply once, only while applications are open. |

The Student Portal itself is described in [spec/portal/portal_theme.md](../portal/portal_theme.md).

---

## 9. Troubleshooting

| Problem | Cause and fix |
|---|---|
| "Invalid status transition from X to Y" | Steps must be taken in order. Ask a System Manager to set a status out of order. |
| Update Registration Status shows no action | Your role is not allowed to set the next step, or the student's status is outside the workflow (e.g. *Active* from admission). |
| "Cannot move to Pending FINO. Missing documents" | Upload Aadhaar, PAN, Std X Marksheet and Passport Size Photo on the Documents tab. |
| "Fee Payment Status must be 'Paid' or 'Partially Paid'" | The admission/registration fee is not recorded as paid. *Authorized* does not count. |
| "Cannot move to Pending Residences" | Set *ID Card Issued = Yes* (Account tab) and tick *Aadhaar Verified*. |
| "Hostel Room must be allocated for hostellers" | Create a Hostel Allocation with status *Allocated* and *Keys Handed Over* ticked. |
| "Official Email ID must be set" | Fill *Official Email ID* on the Documents tab. |
| Student not in my list | Each workflow role sees only its own step (3.5). |
| Student cannot edit bank details | They were already submitted. Untick *Bank Details Submitted by Student*. |
| "…is already registered for student …" | The account number is on another Student Master. Check both records. |
| Student cannot be enrolled | Registration is not *Completed*, a status is *Inactive*, the student is PACE, or there is no programme. |

---

## 10. Known limitations (November 2026)

- The move into **Pending Print & Scan** checks `last_name`. Student Master has no *Last Name* field on the form (an old database column may still exist), so the step fails for any student without a stored last name.
- The **Student Registration Workflow** (Frappe Workflow) is listed in the `hooks.py` fixtures, but `fixtures/workflow.json` is empty and slcm.local has no Workflow for Student Master. All transitions run through the Python state machine in `student_master.py`. `student_master_workflow.json` in the DocType folder is not loaded by anything.
- Students (`slcm_Student`) are allowed to *Submit for REGO*, but no Student Portal page offers this action.
- *ID Card Issued* is a manual Yes/No field. Generating an ID card does not set it.

---

## 11. Open questions

1. **Admission sets Registration Status = "Active".** `applicant_to_student.py` and the PACE conversion set `registration_status = "Active"`, which is not a step of the workflow. From *Active* the Python checks let any workflow role jump to its own step, but the desk dialog and list button offer non-admins nothing. Should converted students start at *Selected*?
2. **Desktop access for workflow officers.** The *Student Registration* icon is granted only to AAD, AAD Staff and System Manager. REGO, FINO, Registration, Documentation, Hostel and IT officers have no icon to reach it (they would use Student Master directly). Intended?
3. **before_save runs twice.** `hooks.py` registers `before_save_hook`, which calls `doc.before_save()`; Frappe also calls the controller's `before_save`. This may add two Status History rows and two comments per change. No duplicates were found on slcm.local; confirm on live.
4. **Two Student ID generators.** *Generate Student ID* (`BALLB20262027001`, re-numbers everyone, System Manager only) and the Enroll wizard (`B26###`, keeps existing IDs) produce different formats. Which one is official?
5. **Enrollment through `bulk_student_enrollment`** is System Manager only, while the Enroll wizard is used by the academic office. Is the older bulk method still needed?
6. **Fee Payment Status "Authorized".** The FINO step accepts only *Paid* / *Partially Paid*. Should *Authorized* (Razorpay) count?
7. **Hostel fee on allocation.** `slcm/slcm/fee/event_hooks.on_hostel_allocation_insert` reads `Fee Structure.total_amount`, which the DocType does not have. A Hostel Allocation insert may fail or create no hostel fee demand. Verify.
8. **Hostel Allocation permissions** list only System Manager, yet the sidebar is shown to Hostel Admin and Hostel Warden.
9. **Student Services scope.** Should Placement and Hostel Management get their own guides? This guide gives only a summary.

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| State machine (`VALID_TRANSITIONS`, `TRANSITION_ROLES`), transition checks, status history, fee auto-fetch, bank validation | `slcm/slcm/doctype/student_master/student_master.py` |
| Status dialog, form buttons, bank field toggles | `student_master.js` |
| List buttons (Update Status, Generate Student ID, sections, RFID, invites) | `student_master_list.js` |
| Enroll wizard | `slcm/public/js/enrollment_wizard.js`, `student_master/enrollment_wizard.py` |
| Completion email | `slcm/slcm/utils/student_email.py` (`handle_registration_completion`) |
| Desk row-level access | `slcm/permissions.py` (`student_master_query_conditions`, `_WORKFLOW_ROLE_STATUS_MAP`), `slcm/security/student_scope.py` |
| Applicant → Student Master | `slcm/api/service/applicant_to_student.py` |
| Portal bank submit | `slcm/api/student_portal.py` (`submit_bank_details`, `_claim_passbook_file`), `slcm/www/student-portal/profile.py` / `.html` |
| Hostel sync | `slcm/slcm/doctype/hostel_allocation/hostel_allocation.py` |
| Sidebars / icons | `slcm/workspace_sidebar/student_registration.json`, `master.json`, `student_portal.json`, `placement.json`, `hostel_management.json`; `slcm/desktop_icon/student_registration.json`, `student_services.json`, `master.json` |
| Workspace | `slcm/slcm/workspace/student_registration/` **and** `fixtures/workspace.json` (the fixture copy wins) |

- Bank fields are **masked**. Frappe resets masked fields to their stored values when a user without unmask permission saves through `doc.save()`. Portal code therefore validates with `validate_bank_details(reveal_owner=False)` and writes with `frappe.db.set_value`.
- `update_registration_status` saves with `ignore_permissions=True` and commits; role checks are done in the method itself.
- Workflow States for registration are created by `slcm/setup/sample_data.py` and shipped in `fixtures/workflow_state.json`.

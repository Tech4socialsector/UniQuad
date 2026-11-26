# PACE: User Guide

**Applies to:** Uniquad (SLCM v16), PACE module, as on disk November 2026
**Who this is for:** PACE admission staff (PACE Admission Manager, Admission Admin), document verifiers (Document Verifier, Document Verification Admin) and developers supporting them.
**Where:** Desk → **Admission → PACE** (desktop icon *PACE*, sidebar *PACE*). Applicants use the PACE portal at `/paceadmissions/...` and `/pace/...`.

PACE is the institution's professional / continuing-education admission line. It runs separately from the regular NLSAT admission (see `spec/admission/`). A PACE applicant applies online, pays an **application fee**, has documents verified, pays a **course fee**, and is then converted to a **Student Master** record.

---

## 1. The flow at a glance

```
1. Set up             PACE Programme → PACE Fee Structure → PACE Admission (cycle, Active)
                      → PACE Verifier Configuration (who verifies which programme)
2. Applicant signs up /paceadmissions/login → register (role PACE Applicant)
3. Application form   /paceadmissions/application-form → Draft → Submitted
4. Application fee    Razorpay → Fee Assignment (Application Fee) Paid → PACE Receipt
                      → Application status Completed
5. Verification       PACE Document Verification created, verifier auto-assigned (round robin)
                      → Verified   or   Returned for Correction (applicant re-uploads) or Rejected
6. Course fee         On Verified: Fee Assignment (Course Fee) created from the Fee Structure
                      → applicant pays → PACE Receipt → Application status Fee Paid
7. Convert            Desk: Convert to Student → Student Master created, status Enrolled
                      (admission letter PDF, role slcm_Student added)
   Any time:          Withdraw Application (staff) → Withdrawn
```

### Application statuses

The application `status` is a link to **PACE Application Status** (shipped in `fixtures/pace_application_status.json`). The `next_step_note` of each status is shown to the applicant.

| Status | Set by | Meaning |
|---|---|---|
| **Draft** | Portal save | Form not yet submitted. Mandatory checks are skipped while Draft. |
| **Submitted** | Portal submit, or applicant closes the payment modal | Form complete, application fee not yet paid. |
| **Completed** | Application fee paid (or fee is zero) | Ready for document verification. |
| **Returned for Correction** | Verifier finalises with at least one document returned | Applicant must re-upload. |
| **Verified** | Verifier finalises with all documents verified | Course fee assignment is created. |
| **Rejected** | Verifier/manager **Reject Application** | Closed. |
| **Fee Paid** | Course fee paid | Ready to convert. |
| **Enrolled** | **Convert to Student** | Student Master exists. |
| **Withdrawn** | Staff **Withdraw Application** | Closed; linked Student Master is also withdrawn. |

The fixture also contains *Provisionally Submitted*, *Under Verification* and *Admitted*. No code path sets them (see Open questions).

On live (checked 2026-11-05) the statuses in use were Enrolled, Draft, Submitted, Verified, Returned for Correction and Withdrawn.

---

## 2. Setup (once per cycle)

### 2.1 PACE Programme
*PACE → PACE Programme*

| Field | Notes |
|---|---|
| Programme Prefix / Programme Name | Required. The record name and title are `"{prefix} {name}"`. |
| Route | Built automatically from the programme name (a slug). A clash adds the record name. |
| Application Form Link | Built automatically: `<site>/paceadmissions/application-form/new?programme=<route>`. |
| Admission Status, Published | Open/Closed; whether the programme shows on the portal. |
| Duration / Duration Type | e.g. 1 Year, 6 Months. |
| Overview, Apply Intro, Eligibility | Text shown on the programme page; each tab has a *Show …* tick. |
| Faculty (table) | Links to **Faculty**. |
| Course (table) | Links to **PACE Programme Course** (course title, intro, units). |
| Banner Image, Contact Email, Instructions | Portal display. |

### 2.2 PACE Fee Structure (course fee)
*PACE → Configurations → Fee Structure*

| Field | Notes |
|---|---|
| Fee Structure Name, PACE Programme, Academic Year | Required. Named `{fee_structure_name}-{academic_year}`. |
| Payment Mode | Online / Cash / Both |
| Payment Gateway | Used for the course fee payment. |
| Valid From / Valid To | The payment window. Payment is blocked outside these dates. |
| Status | Draft / Active / Inactive |
| Currency | Required |
| Fee Components for Indians / for Foreign | One row per **PACE Fee Component List** item: amount + tax rate. Totals fill in. |
| Other Fees | Calculated per row but **not** added to either total. |
| Payment Receipt Template | Print format for the course-fee receipt. |

**Rules the system enforces**
- Only **one Active** fee structure per programme + academic year.
- A component cannot appear twice in the same table. Amounts cannot be negative.
- Tax = amount × tax rate ÷ 100; row total = amount + tax.
- Valid From cannot be after Valid To. Once Valid To has passed, saving sets status *Inactive*.

### 2.3 PACE Admission (the cycle)
*PACE → Configurations → PACE Admission*

| Field | Notes |
|---|---|
| Academic Year | Required. Record name is `PACE-ADM-{academic year}`, so one per year. |
| Admission Open / Close Date | Required. |
| Programmes (table) | Programme, total seats, max applications, **application fee (Indian)** and **(Foreign)**, status Open/Closed. *Application Received* counts up automatically. |
| Payment Gateway | Used for the application fee. |
| Payment Receipt Template | Print format for the application-fee receipt. |
| Status | Draft / Active / Closed |
| Allow Multiple Application per Applicant | Off = one application per email per academic year. |
| Enable Applicant Register Tab | Portal option. |

**Activate Admission** (button on Draft/Closed records) submits the record and sets it Active.

**Rules the system enforces**
- Only **one** PACE Admission can be Active at a time, and its Academic Year must be Active.
- Open date cannot be after close date. A programme cannot be listed twice.
- A Closed admission cannot be edited (only its status can change). Cancelling sets it Closed.
- When a programme's *Application Received* reaches *Total Seats* (if seats > 0), that programme closes automatically.

**Automatic (daily):** an admission opens on its open date (if its year is Active and no other admission is Active) and closes after its close date.

### 2.4 PACE Verifier Configuration
*PACE → Configurations → PACE Verifier Configuration*

| Field | Notes |
|---|---|
| Configuration Name, Academic Year | Required |
| Days to Verify | The SLA. The verification due date = assignment date + this many days (default 2). |
| Verifiers (table) | User + PACE Programme. *Total assigned / verified / pending* are counters. |

**Rules:** a programme can appear only once in the table, and only in one configuration per academic year.

### 2.5 Other setup records

| DocType | Use |
|---|---|
| PACE Fee Component List | Master list of fee components (type: Tuition, Library, Lab, Examination, Hostel, Transport, Other; taxable flag). |
| PACE Programme Course | Course title, intro and units, shown on the programme page. |
| PACE FAQs | Portal FAQs by category (Admission, Fee, Documents, Hostel), optionally per programme. |
| PACE Enquiry | Enquiries submitted from the portal (New / Contacted / Closed). |
| PACE Reminder Email Configuration | See section 8. |
| Applicant Portal Config → *Enable PACE Site* | The PACE portal home returns *Page not found* while this is off. PACE news ticker rows also live here. |

---

## 3. Applicant portal

The applicant pages live in `www/paceadmissions/` (PACE only). Profile, helpdesk and announcements are shared with NLSAT and served as `/pace/my-profile`, `/pace/helpdesk`, `/pace/announcement/<name>`. The folder layout and route rules are described in [`spec/admission/admission_portal_restructure.md`](../admission/admission_portal_restructure.md); they are not repeated here.

| Page | URL | What the applicant does |
|---|---|---|
| Login / register | `/paceadmissions/login` | Registers (email verified; user gets role **PACE Applicant**) and logs in. |
| Forgot / update password | `/paceadmissions/forgot_password`, `/update_password` | |
| Programme list (home) | `/paceadmissions/admission` | Sees open programmes, FAQs, own applications; can send an enquiry. Requires login. |
| Programme page | `/paceadmissions/admission/<route>` | Overview, eligibility, courses, faculty, Apply link. |
| Application form | `/paceadmissions/application-form` (Web Form *PACE Application Form*, login required) | Fills the form, saves a draft, submits and pays. |
| Application card | `/paceadmissions/application-card` | Summary card of the application. |
| Progress tracker | `/paceadmissions/progress-tracker` | Status, documents, re-upload of returned documents, course fee payment, downloads (application form PDF, receipts, admission letter). |

### 3.1 The application form

| Section | Fields |
|---|---|
| Personal | Title, first/middle/last name (stored in UPPER CASE), email, mobile, date of birth, gender, nationality, category, employed (organisation, designation), differently abled, how did you hear about us |
| Family | Father and mother name |
| Address | Present address (country → state → district must match) and permanent address (or *same as present*) |
| Programme | PACE Programme |
| UG Degree (table) | Institution, university, programme, year of passing, result status (Declared / Waiting for result), marking scheme, % / CGPA |
| Documents | Photo, signature, UG degree certificate / marksheet, Govt ID (passport for foreign nationals) |
| Declarations | Acknowledge / understand / communication ticks |

**Rules the system enforces**
- A new or editable (Draft / Returned for Correction) application needs an **Active** PACE Admission, today must be on or before its close date, and the programme must be in that admission with status **Open**.
- One application per email per academic year (ignoring Cancelled), unless the admission allows multiple.
- The portal can save only Draft or Returned for Correction applications. Once Submitted the form is locked for the applicant.
- Application names follow `PACE-{academic year}-#####`.

**What saving does automatically**
- Updates the applicant's User profile (name, phone, gender, birth date, country, location).
- Generates the **application form PDF** (print format *Pace Application Form*) on Draft / Submitted / Completed and attaches it to *Application Form*.
- On *Submitted*: sends the *PACE Application Submitted* email and an in-app notification.
- If the programme is changed later, an unpaid Course Fee assignment is rebuilt from the new programme's fee structure and its open payment requests are cancelled. Paid / Enrolled assignments are not touched.

---

## 4. Application fee

The applicant pays at the end of the form.

1. The fee comes from the Active **PACE Admission** row for the programme: *Application Fee (Indian)* if nationality is *Indian*, otherwise *(Foreign)*.
2. A **PACE Applicant Fee Assignment** (fee type *Application Fee*, status *Assigned*) is created or updated, and an **SLCM Payment Request** is created for it.
3. A Razorpay order opens. If the applicant closes it, the application becomes *Submitted* (unpaid).
4. On success (browser callback **or** Razorpay webhook, whichever arrives first) the assignment becomes **Paid**, a **PACE Receipt** is created with a PDF, the confirmation email is sent, and the application becomes **Completed**.

| Case | Result |
|---|---|
| Fee is zero | Application goes straight to *Completed*. |
| Already paid | Payment is refused; application set to *Completed*. |
| After the admission close date | Payment cannot be started. |

---

## 5. Document verification

### 5.1 How a record is created and assigned
When an application becomes **Completed**, one **PACE Document Verification** is created (status *Pending*) with one **Verification Item** per uploaded document: photo, signature, UG degree certificate, Govt ID.

A verifier is picked **round robin** from the PACE Verifier Configuration rows for that programme, skipping users on approved leave. The due date is today + *Days to Verify*. The verifier gets an email, a ToDo and a share of the record, and the application's *Assigned Verifier* is set.

Verifiers (Document Verifier, Faculty, Guest Faculty roles) see **only records assigned to them**. Managers (System Manager, Academic Manager, PACE Admission Manager, Admission Admin) see all.

### 5.2 Verifying
*PACE → PACE Document Verification → open record*

1. Set each item to **Verified** or **Returned for Correction**. A returned item **needs remarks**.
2. Click **Finalize Verification**. Every item must be decided first.

| Outcome | Verification status | Application status | Also |
|---|---|---|---|
| All items Verified | Verified | Verified | Course Fee assignment created (section 6). |
| Any item Returned | Returned for Correction | Returned for Correction | Due date cleared. Applicant is emailed. |
| **Reject Application** (needs a reason) | Rejected | Rejected | Reason added as a comment; applicant emailed. |

Verifiers cannot delete, add or replace the files in the items, and cannot change the due date.

### 5.3 Re-upload by the applicant
On the progress tracker the applicant re-uploads each returned document, then clicks submit. The record goes back to **Pending**, re-uploaded items are flagged, the due date is reset by the SLA, and the verifier is emailed. If the verifier is on leave, the record is reassigned.

### 5.4 Reassigning (managers)
| Action | Where |
|---|---|
| Re-assign one record | Form → **Re-assign Verifier** |
| Bulk assign Pending records to one verifier | List → bulk assign (also allowed for Document Verification Admin) |
| Bulk re-assign (round robin again) | List → bulk re-assign |
| Transfer all Pending records from one verifier to another | List → transfer |
| Show overdue for a verifier | List → overdue |

Each reassignment is logged in **PACE Assignment Log** (from, to, by, reason).

### 5.5 Overdue
A Pending record past its due date is flagged *Is Overdue* (on list load and by the daily job). The daily job emails verifiers a pending reminder before the due date and an overdue notice after it, at the intervals set in section 8.

---

## 6. Course fee

When verification is finalised as Verified, a **PACE Applicant Fee Assignment** (fee type *Course Fee*, status *Assigned*) is created from the programme's **Active PACE Fee Structure** for the academic year:
- Indian nationals get the *Indian* components and total; everyone else the *Foreign* ones.
- Final payable amount = total amount.
- If no Active fee structure exists, finalising fails with *Active Fee Structure not found*.

The applicant pays from the progress tracker; staff can also use **Pay Now** on the assignment (desk). Payment is refused if the assignment is Draft or already Paid, or today is outside the fee structure's Valid From / Valid To.

On success: assignment **Paid**, **PACE Receipt** created, confirmation email, application **Fee Paid**.

Paid / Enrolled assignments can be edited only by System Manager, Academic Manager, PACE Admission Manager or Admission Admin.

### Fee Assignment statuses
Draft, Assigned, Partially Paid, Paid, Cancelled, Withdrawn, Enrolled, Rejected.

### Sync Razorpay Amount
*Assignment → Actions → Sync Razorpay Amount* (or list → **Bulk Sync Razorpay Amount**) fills *Razorpay Paid Amount* from the paid payment request: gateway amount minus gateway fee.

---

## 7. Convert to student, withdraw

### 7.1 Convert to Student
| Where | Selects |
|---|---|
| PACE Application form (status *Fee Paid*) → **Convert to Student** | One application |
| PACE Application list → **Convert to Student** | Applications with status *Fee Paid* |
| PACE Applicant Fee Assignment list → **Convert to Student** | Course Fee assignments with status *Paid* |

Allowed for PACE Admission Manager, Admission Admin, Academic Manager, System Manager, and only if the user can create Student Master.

**What conversion does**
- Creates a **Student Master**: application number = PACE application, *PACE Programme*, academic year, admission type *PACE*, level of study *Diploma*, personal, address and parent details, user = applicant email, student status *Active*.
- Generates the **admission letter** PDF (print format *PACE Admission Letter*) if missing.
- Sets the application and its Course Fee assignments to **Enrolled**; sends the enrollment confirmation email.
- Adds role **slcm_Student** to the applicant's user (the PACE Applicant role is kept).

**Rules:** an application already linked to a Student Master is skipped (and marked Enrolled). Conversion fails if another **Active** Student Master has the same email. Bulk runs report success / skipped / errors per row.

### 7.2 Withdraw Application
*PACE Application → **Withdraw Application*** (any status except Withdrawn; System Manager, PACE Admission Manager, Admission Admin). Needs a reason. Sets *Withdrawn*, stores the reason, and withdraws the linked Student Master records if any.

---

## 8. Reminder emails (automatic)

All run **daily at 10:00**. Each can be switched on/off and given an interval (days) in **PACE Reminder Email Configuration**. **Send Reminder Email** on that form runs selected reminders now. Each email is logged in **PACE Reminder Email Log** (Sent / Failed).

| Reminder | Sent to | Condition |
|---|---|---|
| Application | Users with role PACE Applicant | No application yet in the cycle |
| Draft | Applicant | Application still Draft |
| Payment | Applicant | Status *Submitted* (application fee unpaid) |
| Missing Document | Applicant | Status *Provisionally Submitted* and a document missing |
| Correction | Applicant | Status *Returned for Correction* |
| Course Fee | Applicant | Course Fee assignment still *Assigned* |
| Verifier Pending | Verifier | Pending records not yet due (grouped per verifier) |
| Verifier Overdue | Verifier | Pending records past due |

Reminders stop after the admission close date. On the close date itself one is sent regardless of the interval. Templates are **Email Template** records named *PACE …* (sidebar *Pace Email Template*).

---

## 9. Receipts and payments data

| Record | One per | Key fields |
|---|---|---|
| **PACE Applicant Fee Assignment** | Applicant + fee type | applicant, fee_type (Application Fee / Course Fee), status, total_amount, final_payable_amount, razorpay_paid_amount, transaction_id, payment_date, fee_receipt |
| **SLCM Payment Request** | Payment attempt | reference_doctype = *PACE Applicant Fee Assignment*, status Requested / Paid / Failed / Cancelled, gateway fields |
| **PACE Receipt** | Paid assignment | pace_application, fee_assignment, payment_request, program, academic_year, fee_type, amount, transaction_id, payment_date, receipt (PDF) |

**Receipt print format:** Course Fee → the fee structure's *Payment Receipt Template*; Application Fee → the PACE Admission's template; fallback *PACE Payment Reciept*. The PACE Receipt list has a **bulk download** (ZIP, built in the background).

Other print formats: *PACE Application Form*, *PACE Admission Letter*, *PACE Payment Invoice* (shown as *Application Fee Invoice* / *Course Fee Invoice* buttons), *PACE Payment Reciept v1*.

The PACE Application list also has **Bulk download** of all uploaded documents (ZIP, background) and **Send Email** to selected applicants.

> **Where PACE money lives:** PACE payments are **not** in Fee Payment / Fee Invoice. Count them from PACE Receipt, PACE Applicant Fee Assignment and SLCM Payment Request.

---

## 10. Dashboards and reports

| Item | Type | Who |
|---|---|---|
| **PACE** (sidebar *Dashboard*) | Dashboard: 18 number cards (applications by status, fees collected, documents by status) and 10 charts (revenue by programme, daily trend, weekly revenue, funnel, marketing source, verifier performance, geography …) | PACE staff |
| **Document Verifier** | Dashboard: allocated / pending / completed / sent for correction / rejected, daily processing | Verifiers |
| **pace-admin-dashboard** | Desk page: KPIs, charts, fee summary, recent applications, pending work, filters | System Manager, PACE Admission Manager, Admission Admin |

Reports in the sidebar: **Applicant User States** (*PACE Applicant Registration Status*, by user), **PACE Applicant Report**, **PACE Fee Report**, **Daily Application Summary** (*PACE Daily Application Status Summary*).

Other reports in the module: Application Conversion Funnel, Application Statistics, Course Revenue Report, Daily Application Trend, Marketing Source Analysis, PACE Applicant Fee Payment Status, PACE Applications by Geography, PACE Verification Summary, PACE Verifier Performance, Revenue by Program, Verifier Performance, Weekly Revenue Trend.

---

## 11. Sidebar (Desk → PACE)

| Group | Items |
|---|---|
| (top) | Dashboard (*PACE*), PACE Programme, PACE Programme Course, PACE Application, PACE Document Verification |
| Configurations | PACE Admission, PACE Verifier Configuration, Fee Structure (*PACE Fee Structure*) |
| Reports | Applicant User States, PACE Applicant Report, PACE Fee Report, Daily Application Summary |
| Logs | PACE Applicant Fee Assignment, PACE Payment Receipt (*PACE Receipt*), PACE Assignment Log, PACE Reminder Email Configuration, PACE Reminder Email Log, Pace Email Template (*Email Template*) |

The desktop icon *PACE* sits under the *Admission* icon and is visible to Academic Admin, Admission Admin, PACE Admission Manager, Document Verification Admin and Document Verifier.

---

## 12. Roles

| Role | Can do |
|---|---|
| PACE Admission Manager | Everything in PACE: setup, verification overview, reassign, convert, withdraw, reminders |
| Admission Admin | Same as above for most actions (setup, reassign, convert, withdraw) |
| Document Verification Admin | Read/write verifications, bulk assign |
| Document Verifier (also Faculty / Guest Faculty) | Verify and finalise records assigned to them |
| PACE Applicant | Portal: own application, payments, re-uploads, receipts |
| slcm_Student | Added on conversion |

---

## 13. Troubleshooting

| Problem | Cause and fix |
|---|---|
| "There is no active PACE Admission cycle" | No PACE Admission is Active. Activate one (its Academic Year must be Active). |
| "The selected programme … is not available / closed" | Programme missing from the Active admission's table, or its row is Closed (manually or seat limit reached). |
| "Another PACE Admission … is already Active" | Close the other one first. |
| "You have already submitted an application" | One application per email per academic year. Tick *Allow Multiple Application per Applicant* if intended. |
| Application fee shows 0 / goes straight to Completed | Application fee for that nationality is 0 on the admission's programme row. |
| No verifier assigned | No PACE Verifier Configuration row for the programme in that academic year, or all its verifiers are on leave. Use bulk assign. |
| Finalize fails: "All documents must be verified…" | An item is still Pending. |
| Finalize fails: "Active Fee Structure not found" | Create / activate the PACE Fee Structure for that programme and year. |
| "The payment period has not started / has ended" | Today is outside the fee structure's Valid From / Valid To. |
| Convert fails: "An active Student Master … already exists" | Another active student uses the same email. |
| PACE portal shows Page not found | *Enable PACE Site* is off in Applicant Portal Config. |

---

## 14. Open questions

1. **Missing APIs called by the UI.** `slcm.pace.api.reset_verification_status` (desk PACE Application form, on file change) and `slcm.pace.api.submit_provisionally_uploaded_document` (progress tracker) are called but not defined anywhere. Are these flows dead, or was code lost?
2. **Unused statuses.** *Provisionally Submitted*, *Under Verification* and *Admitted* exist in the status fixture but nothing sets them. The **Missing Document** reminder only looks at *Provisionally Submitted*, so it never fires. Should it target *Completed* (as its docstring says)?
3. **Round-robin fallbacks.** `assign_verifier_round_robin` / `get_sla_days` fall back to filtering PACE Verifier Configuration by a `programme` field, and the second pass reads `config.programme`, but that DocType has no `programme` field. What should happen when a programme has no mapping row?
4. **Leave check** reads *Leave Application* (HRMS). Is HRMS installed on the PACE site? If not, "skip verifiers on leave" never applies.
5. **Finance sync on conversion** looks for a Course Fee assignment with `docstatus = 1`, but the assignment DocType is not submittable, so Student Master fee fields are never filled from PACE. Intended?
6. **Course fee reminder docstring** says unpaid applicants are rejected after the close date; the code only stops sending. Should auto-rejection exist?
7. **Status values not in the Select:** code checks fee assignment status *Converted* (not an option); fixture status *Rejected* uses stage type *Enrolment* (not an option).
8. **Application fee currency** is hard-coded INR even when the foreign fee is charged. Is the foreign fee meant to be in INR?
9. **Permissions on PACE Applicant Fee Assignment:** role *All* has read and *Guest Faculty* has write. Intended?
10. **Student Master fields on conversion:** `registration_status` is set to *Active* (a Workflow State link, inserted with `ignore_links`) and `level_of_study` is hard-coded *Diploma*. Should PACE students go through the regular registration workflow (see the Student Registration guide)?
11. Should the *PACE Applicant* role be removed after conversion? The removal code is commented out "as per user request".

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| DocTypes | `slcm/pace/doctype/` |
| Application controller (validation, programme change, PDF, reminders, bulk ZIP, withdraw) | `pace/doctype/pace_application/pace_application.py` |
| Portal form + application-fee payment (`save_pace_draft`, `submit_pace_application`, `initiate_pace_razorpay_order`, `verify_pace_payment_signature`, `complete_pace_payment`, `generate_pace_receipt`) | `pace/web_form/pace_application_form/pace_application_form.py` |
| Portal APIs (programmes, FAQs, enquiry, re-upload, bulk assign, document download) | `pace/api/__init__.py` |
| Desk/portal course-fee payment, webhook sync (`sync_pace_payment_after_gateway_capture`) | `pace/api/service/pace_payment.py`; called from `slcm/payment.py` and `slcm/api/razorpay_webhook.py` / `api/service/razorpay_utils.py` |
| Convert to Student | `pace/api/service/pace_to_student.py` |
| Verifier assignment, reassignment, overdue job | `pace/assignment_logic.py` |
| Verification create / finalise / reject | `pace/doctype/pace_document_verification/get_document_api.py` |
| Verification permissions | `pace_document_verification.py` (`get_permission_query_conditions`, `has_permission`, registered in `hooks.py`) |
| Course fee assignment creation | `pace/utils.py` (`create_pace_fee_assignment`) |
| Receipts, receipt template, bulk ZIP | `pace/doctype/pace_receipt/pace_receipt.py` |
| Reminder switches / intervals | `pace_reminder_email_configuration.py` (`is_reminder_enabled`, `should_send_reminder`) |
| Scheduler | `hooks.py`: `0 10 * * *` (6 PACE reminder/overdue jobs), `daily` (`auto_close_outdated_admissions`) |
| Portal pages | `slcm/www/paceadmissions/`; registration `slcm/api/user.py` (`register_pace_user`) |
| Admin page | `pace/page/pace_admin_dashboard/` |
| Dashboards, number cards, charts, reports | `pace/pace_dashboard/`, `pace/number_card/`, `pace/dashboard_chart/`, `pace/report/` |
| Email templates (HTML source) | `pace/pace_email_template/` |
| Status master | `fixtures/pace_application_status.json` |
| Sidebar / icon | `slcm/workspace_sidebar/pace.json`, `slcm/desktop_icon/pace.json` |

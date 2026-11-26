# Transcript: User Guide

**Applies to:** Uniquad / SLCM v16 (November 2026)
**Who this is for:** Academic office staff (AAD, Academics User) who set up transcript fees and layouts, process student transcript requests, and print transcripts. Also useful for exam staff who publish results, because transcripts read those results.
**Where:** Desk → **Transcript Management** (sidebar: *Home · Transcripts → Transcript Request, Student Transcript · Configuration → Transcript Settings, Transcript Template · Settings → Transcript Fee Settings*). The **Transcript Management** page opens from the workspace shortcuts *Transcript management page* and *Transcript Request Management*.

---

## 1. The flow at a glance

```
1. Setup (once)        Transcript Fee Settings → Transcript Template (default) → Transcript Settings
                       → CGPA Percentage Scale
2. Results             Marks entered (Student Course Marks) → Term Results: term GPA, CGPA,
                       cumulative % → Publish Results
3. Request             Student Portal → Transcript Request page   (or Helpdesk "Transcript Request" ticket)
                       creates a Transcript Request
4. Payment             Student pays online (Razorpay or Easebuzz)   → status Submitted
5. Review              Transcript Management → Requests tab → Approve & Generate / Reject
                       (Interim may be auto-approved after payment)
6. Generate            A Student Transcript record is created     → status Generated
7. Download            Student downloads the PDF from the portal; staff download from the Students tab
```

Staff can also skip steps 3–5 and generate a transcript for any student from the **Students** tab (section 7).

### Key ideas

| Term | Meaning |
|---|---|
| **Transcript Request** | A student's request for a transcript. Named `TRQ-YYYY-#####`. Holds type, copies, fee, payment and processing status. |
| **Student Transcript** | The record that says "a transcript was generated for this student". Named `TR-YYYY-#####`. It holds **no marks**: the PDF is built from live result data each time it is printed. |
| **Transcript type** | *Interim, Final, Consolidated Marksheet, Duplicate, Digital*. Students see **Final Transcript** as **"Provisional Transcript"** on the portal, the request form and Helpdesk. |
| **Transcript Template** | Logo, institute name/address, header title, signatures and watermark. Only the **default** template is used. |
| **Transcript Settings** | Colours and options for the year-based layout, and the **Year Mapping** that groups terms into "I Year", "II Year" … |
| **CGPA Percentage Scale** | A lookup table that turns a CGPA into a final percentage. |
| **Student Result Publish** | One record per student per exam plan with term GPA, term %, CGPA and cumulative %, and the *Is Published* flag. |

---

## 2. Setup (once)

### 2.1 Transcript Fee Settings
*Transcript Management → Settings → Transcript Fee Settings* (single record)

| Field | Default | Notes |
|---|---|---|
| Enable Payment for Transcript Requests | On | Off = requests are free (*Payment Status: Not Required*). |
| Payment Gateway | Razorpay | Razorpay or Easebuzz. |
| Currency | INR | |
| Urgent Processing Surcharge | 0 | Added once per request when the student picks *Urgent*. |
| Tax / GST (%) | 0 | Shown in the fee preview only. See *Open questions*. |
| Free Requests Per Student | 0 | Not used by the code. |
| Allow … Requests (5 ticks) | All on | Untick a type to hide it on the portal and block new requests of that type. |
| Fee per copy (5 fields) | Interim 300, Final 1000, Consolidated Marksheet 500, Duplicate 500, Digital 150 | Per copy. |
| Restrict Final Transcript to Graduated Students Only | Off | Also applies to Consolidated Marksheet. |
| Auto-Approve Interim Transcripts (after payment) | On | |
| Auto-Approve Final Transcripts (after payment) | Off | Covers Final, Consolidated Marksheet, Duplicate and Digital. |
| Normal / Urgent Processing Days | 5 / 2 | Display text on the portal only. |
| Email templates (5 links) | empty | Submission, Payment, Approval, Rejection, Ready. Empty = no email for that event. |
| Assignment Rules (table) | | Academic Year, Programme, Assignee, Note. Not used by the code. |

**How the fee is worked out** (when the request is created):

```
Fee Amount = fee per copy for the type × Number of Copies  (+ Urgent surcharge if Urgent)
```

The amount is always calculated on the server. The student cannot change it.

**Email templates** can use these variables: `student`, `student_name`, `request_name`, `transcript_type`, plus `status`, `fee_amount`, `payment_required` (submission), `fee_amount`, `payment_id` (payment), `rejection_reason`, `transcript_doc` (approval / rejection / ready). No templates ship with the app.

### 2.2 Transcript Template
*Transcript Management → Configuration → Transcript Template*, or **Transcript Management page → Templates button** (opens the *Transcript Templates* page with a live preview).

| Section | Fields |
|---|---|
| Basic | Template Name (record name), Type (*System* / *Custom*), Default Template, Page Size, Orientation |
| Institute Logo | Logo Image, Show Logo, Logo Width (px), Logo Alignment |
| Institute Address | Institute Name, Address, City / State, Country, Pincode, Show Address on Transcript |
| Basic Details | Transcript Header Title, Show Student Photo, Show Registration ID, Show CGPA, Show Credits, Show Semester-wise Grades |
| Signatures | Up to 3 labels + signature images |
| Watermark | Watermark Image or Watermark Text, Opacity (%), Show Watermark |

**Rules the system enforces**
- Only **one** template can be the default. Ticking *Default* on one clears it on the others.
- *System* templates cannot be deleted from the Templates page.
- Images must be uploaded with the Upload button. Pasted (base64) images are refused.
- The Templates page creates a *Default Transcript Template* (System, default) the first time it opens, if it does not exist.

If there is no default template, the transcript uses the header *OFFICIAL TRANSCRIPT OF ACADEMIC RECORDS* and shows logo, address, photo, registration ID and CGPA.

### 2.3 Transcript Settings
*Transcript Management → Configuration → Transcript Settings* (single record; also under *Master → Institution Settings*)

| Section | Fields | Used by |
|---|---|---|
| Layout | Show Prescribed Courses Column, Show Course Numbers (1.1, 1.2 …), Use Two-Column Layout | Year Based Transcript print format |
| Colours / Background | Header and table colours, page and mild background colours | Year Based Transcript print format |
| **Year Mappings** (table) | Year Label, Semester/Trimester List (comma-separated), Year Number | All layouts |

**Year Mapping** tells the transcript which terms belong to which year, for example:

| Year Label | Semester/Trimester List | Year Number |
|---|---|---|
| I Year | Trimester I - AY 2024 -2025, Trimester II - AY 2024 -2025, Trimester III - AY 2024 -2025 | 1 |

The names are matched against the exam plan's **Academic Term**. The standard layout also tries the exam plan name and exam name, ignoring case.

> **Without Year Mappings, every exam plan becomes its own "year"** on the standard and compact layouts (YEAR I, YEAR II, … one per exam plan). On the year-based layout, unmapped terms go into one group labelled *Other*. Set up the mapping before printing transcripts.

### 2.4 CGPA Percentage Scale
*Master → Assessment & Grading → CGPA Percentage Scale*, or **Term Results → CGPA % Scale** button (opens the *CGPA Percentage Scale* page).

A table of **CGPA → Final Percentage** rows.

| Action on the page | What it does |
|---|---|
| **Populate** | Replaces all rows with the standard formula, CGPA 0.00 to 7.00 in 0.01 steps: `percentage = 50 + (CGPA − 3) × 12.5`, and 0 for CGPA below 3.00. |
| Edit and **Save** | Replaces all rows with the table as shown. |

**How the lookup works:** the system takes the row with the **largest CGPA that is less than or equal to** the student's CGPA (rounded to 2 decimals). If the table is empty, or the CGPA is below the first row, it falls back to the marks-based percentage (total marks ÷ maximum marks × 100).

---

## 3. Where the transcript gets its data

A Student Transcript record stores no marks. Every time a transcript PDF is printed, it is built from these sources:

| Data on the transcript | Source |
|---|---|
| Name, photo, registration ID, batch | **Student Master** |
| Programme | The student's latest *Enrolled* **Student Enrollment**, else Student Master *Programme of Study* |
| Courses | **Student Course Marks**, one row per course per **Exam Plan**. Rows with enrollment status *Dropped, Detained* or *Migrated* are left out. |
| Course name, code, credits | **Course** |
| Grade | *Updated Grade* if set (after re-evaluation / moderation), else *Grade* |
| Grade point, failed flag | **Grading Schema** linked through the **Course Schema Assignment** for that exam plan + course |
| MFA mark | Course Marks *MFA = Yes*, or an approved, submitted **FA MFA Application** of type *Medical First Attempt (MFA)* for that course. Shown as a superscript "MFA" next to the grade. |
| SGPA per term | **Student Result Publish** *Term GPA* for that exam plan (if above 0); otherwise calculated: Σ(grade point × credits) ÷ Σ credits over courses marked *Consider for SGPA* |
| CGPA | Student Master **Current CGPA** |
| Academic period (compact layout) | Earliest term start to latest term end of the student's exam plans |

**Re-exams:** when a failed course is taken again in a later exam plan, the earlier attempt is "superseded".
- Standard and compact layouts: the earlier attempt is still listed, but its credits do not count and it is left out of the calculated SGPA.
- Year-based layout: the earlier attempt is left out.

### How CGPA and cumulative percentage get onto Student Master

Transcripts print whatever CGPA is on Student Master. It is set by the exam result screens:

| Where | What it writes |
|---|---|
| **Term Results** page → action *Cumulative GPA* | CGPA over all the student's courses (latest attempt only, *Consider for SGPA* courses with a grade): Σ(grade point × credits) ÷ Σ credits. Saved on Student Result Publish and on Student Master *Current CGPA* (only if above 0). |
| **Term Results** page → action *Cumulative Percentage* | CGPA looked up in the CGPA Percentage Scale (else marks-based %). Saved on Student Result Publish and Student Master *Cumulative Percentage*. |
| **Term Results** → *Term GPA* / *Term Percentage* | Saved on Student Result Publish only. |
| **Publish Results** page | Sets *Is Published* on Student Result Publish. |

> If Term Results has not been run, Student Master *Current CGPA* may be empty or out of date, and the transcript shows a blank CGPA (standard layout) or 0.00 (year-based layout).

---

## 4. Students request a transcript

### 4.1 Student Portal
*Student Portal → `/student-portal/transcript-request`*

> The sidebar link to this page is commented out in the portal menu, so students reach it only by the direct URL (or from Helpdesk, below).

| Field | Options |
|---|---|
| Transcript Type | Only the types allowed in Transcript Fee Settings. *Final Transcript* is shown as *Provisional Transcript*. |
| Number of Copies | 1 or more |
| Delivery Mode | Soft Copy (PDF) / Hard Copy (Physical) / Both |
| Urgency | Normal / Urgent |
| Purpose / Remarks | Free text |

The page shows a live fee preview (fee × copies, urgent surcharge, tax, total), the student's CGPA, and their past requests with status, payment status and a **Download** button when ready.

If the student has no published results, the page shows a warning and the form buttons are disabled.

**Rules the system enforces**
- Only logged-in students with a Student Master record can request (the account is matched on Student Master *User*, *Email* or *Official Email ID*).
- The type must be allowed in Transcript Fee Settings.
- If *Restrict Final Transcript to Graduated Students Only* is on, Final Transcript and Consolidated Marksheet need Student Master *Academic Status* = Graduated, Programme Completed or Completed.
- Only **one open request per type**. A request in *Draft, Payment Pending, Submitted, Under Review* or *Approved* blocks a new one of the same type.
- A student can cancel their own request only while it is *Draft* or *Payment Pending*.

### 4.2 Helpdesk
A Helpdesk ticket of type **Transcript Request** (Student Portal → Support) also creates a Transcript Request. The ticket form offers only *Final Transcript* (shown as *Provisional Transcript*).
- **Pay first (normal):** the form creates the request and takes payment before the ticket is submitted. The ticket is then linked to the paid request.
- **Fallback:** a ticket created any other way creates an unpaid request and posts a note on the ticket.
- If the browser closed after payment, the form finds the paid, unlinked request and continues without charging again.
- Status and payment changes are posted on the linked ticket. *Generated/Delivered* moves the ticket to *Resolved*; *Rejected/Cancelled* moves it to *Closed*.

---

## 5. Payment

The gateway comes from **Transcript Fee Settings → Payment Gateway**.

| Step | Request status | Payment status |
|---|---|---|
| Request created, payment on | Payment Pending | Pending |
| Student clicks **Pay** | Payment Pending | Payment Initiated |
| Student closes the checkout | Payment Pending | Payment Cancelled |
| Gateway reports a failure | Payment Pending | Payment Failed (reason saved in *Payment Failure Reason*) |
| Payment verified | **Submitted** | **Paid** |
| Auto-approve on for the type | **Generated** | Paid |
| Staff reject a paid request | Rejected | **Refund Pending** |

After a failed or cancelled attempt the student can pay again.

**What happens automatically**
- **Razorpay:** the payment signature is checked. The order must belong to this request, and one payment ID cannot pay two requests.
- **Easebuzz:** the student is redirected to Easebuzz and back to the Transcript Request page (or the Helpdesk form).
- Payments whose browser confirmation never arrived are picked up by the scheduled Razorpay / Easebuzz reconcilers and marked paid the same way.
- A second payment for an already-paid request, or a payment for a cancelled request, is **not** applied. It is recorded as unapplied money that needs a refund.
- Every gateway payment or failure is also logged as an **SLCM Payment Request** (payment ledger).
- If the ERPNext bridge is on, transcript fees post to the *Transcript Fee* ledger.
- The *Payment Confirmation* email is sent (if a template is set).
- Paid requests appear on the Student Portal **Fees** page, with a downloadable **Transcript Fee Receipt** (print format on Transcript Request). Parents can download the same receipt.

---

## 6. Processing requests (staff)

*Transcript Management page → **Requests** tab* (or the shortcut *Transcript Request Management*, which opens `/app/transcript-management-page/requests`).

The tab shows counts (payment pending, under review, approved, generated/delivered, rejected, paid count, revenue), a status chart, and a list you can search and filter by status, type and payment status. **Payment Info** shows the gateway details for one request.

| Action | Where | What happens |
|---|---|---|
| **Approve & Generate** | Tick rows → bottom bar; or the Transcript Request form (for *Submitted, Under Review, Approved*) | Creates (or reuses) the Student Transcript for this request, sets the request to **Generated**, links *Generated Transcript*, records *Reviewed By / On*, sends the *Ready* email. |
| **Reject** | Tick rows → bottom bar; or the form | A rejection reason is required. Status **Rejected**; a paid request becomes *Refund Pending*; the *Rejection* email is sent. |
| Mark **Delivered** | Edit the *Status* field on the form | Sends the *Ready* email if not already sent. |

**Rules the system enforces**
- A request that needs payment cannot be approved until Payment Status is *Paid* (or *Not Required*).
- Requests already *Generated, Delivered, Rejected* or *Cancelled* cannot be approved or rejected again.
- Bulk actions report success or failure per row; one failure does not stop the others.

**What happens automatically on the form** (status changed by hand in the desk)
- *Approved* → Approval email; *Rejected* → Rejection email; *Generated / Delivered* → Ready email. Each email is sent once (tracked by the *… Email Sent* ticks).
- The linked Helpdesk ticket is updated.

The **Refund Pending → Refunded** step is not automated; a refunded payment is matched in the payment ledger when Payment Status is set to *Refunded*.

---

## 7. Generating transcripts directly (Students tab)

*Transcript Management page → **Students** tab*

Lists students with Learning Pathway(s), Registration ID, credits (earned / total from Student Enrollment courses not *Dropped*), CGPA and an **Interim** transcript column. Filter by Programme, Department, Course, Academic Year, Batch and Academic Status; sort by name, ID or CGPA. The header shows counts of Interim and Final transcripts generated.

| Action | What happens |
|---|---|
| **+ Generate** in the Interim column | Creates the student's Interim Student Transcript (or refreshes the existing one: status *Generated*, today's date). No request or payment needed. |
| **Generated** badge | Downloads the PDF in the standard *Student Transcript* format. |
| **Revoked** badge | Generates again. |
| **Download Compact** (one student ticked) | Downloads the compact two-column transcript. Uses the student's Final, else Interim Student Transcript; creates one if none exists. |
| **Templates** | Opens the Transcript Templates page. |

One Student Transcript is kept per student per type from this tab; generating again updates it.

---

## 8. Transcript layouts and downloads

| Layout | Print format / template | Used for |
|---|---|---|
| **Standard** | Print format *Student Transcript* (fixture) | Students tab download; student download of every type except Final; portal *Documents* page |
| **Compact** (two-column, one A4 page, CGPA "/ 7.00", date, Registrar) | `compact_transcript.html` | *Download Compact*; student download of **Final** (Provisional) Transcript |
| **Year-based** | Print format *Year Based Transcript* | Desk print view of a Student Transcript; uses Transcript Settings colours |

Students download from:
- **Transcript Request page → Download** (request must be *Generated* or *Delivered* and linked to a Student Transcript).
- **Documents page → Transcripts**, which lists their Interim and Final Student Transcripts.

Consolidated Marksheet, Duplicate and Digital requests print in the standard layout; there is no separate layout for them.

---

## 9. Statuses

### Transcript Request: Status

| Status | Meaning |
|---|---|
| Draft | Created with payment switched off (stays here until staff act) |
| Payment Pending | Waiting for payment |
| Submitted | Paid, waiting for review |
| Under Review | Assigned to a staff user (no screen sets this today) |
| Approved | Approved, but the Student Transcript could not be created |
| Generated | Student Transcript created |
| Delivered | Set by hand after a hard copy is handed over |
| Rejected | Rejected by staff, with a reason |
| Cancelled | Cancelled by the student (or replaced by a Helpdesk retry) |

### Transcript Request: Payment Status
*Not Required, Pending, Payment Initiated, Authorized, Paid, Payment Failed, Payment Cancelled, Refund Pending, Refunded.* The raw gateway value is kept separately in *Razorpay Payment Status* (*created, authorized, captured, failed, refunded, cancelled*).

### Student Transcript: Status
*Generated* or *Revoked*. Revoking is done by editing the record; it changes nothing else.

---

## 10. Who can do what

| DocType / Page | System Manager | AAD | Academics User | Student |
|---|---|---|---|---|
| Transcript Request | Full | Full | none (DocType) | Read own (owner + own Student Master) |
| Student Transcript | Full | Full | Create, read, write (no delete) | none (downloads via portal) |
| Transcript Template | Full | Full | Create, read, write (no delete) | none |
| Transcript Settings, Transcript Fee Settings | Full | Full | none | none |
| CGPA Percentage Scale (DocType) | Full | none | none | none |
| Transcript Management, Transcript Templates, Result Settings, Consolidated Report pages | Yes | Yes | Yes | No |
| CGPA Percentage Scale page | Yes | No | (role "Academic User", see Open questions) | No |

Website users (students, parents) cannot call any desk-page method; the API guard blocks them.

---

## 11. Related result screens

| Screen | What it does for transcripts |
|---|---|
| **Result Settings** page (Examination) | Per exam plan: *Publish Result Setting* (components shown, show total marks / SGPA, hide SGPA for failed, e-gradesheet, do not publish for unpaid fees / missing feedback). Per course: **Access Result Settings** (LOCKED / UNLOCKED, view and edit access with deadlines, evaluators, grade-access options, visible exams). Saving checks the user has System Manager, Academics User or AAD. A course must have a Course Schema Assignment in the plan first. |
| **Consolidated Report** page | Opens a dialog to download one Excel of results (one sheet for everyone plus one per course) filtered by exam plan, academic year, programme, trimester, batch, all courses or one course. Includes SGPA and CGPA from Student Result Publish. At least one filter is required. |
| **Student Marksheet Transcript** report | Script report on Student Course Marks for one student (exam plan, course, component …). |

---

## 12. Troubleshooting

| Problem | Cause and fix |
|---|---|
| Student sees "You already have an open request …" | An earlier request of the same type is still open. Finish, reject or cancel it first. |
| "Final Transcript and Consolidated Marksheet are only issued after programme completion" | *Restrict Final Transcript to Graduated Students Only* is on and the student's Academic Status is not Graduated / Programme Completed / Completed. |
| "… requests are currently not accepted" | That type is unticked in Transcript Fee Settings. |
| "Cannot approve: payment is not complete" | Payment Status is not *Paid*. Check **Payment Info**; a stuck payment may be picked up by the reconciler. |
| Paid twice | The second payment is logged as unapplied in the payment ledger. Refund it from the gateway. |
| Request is *Generated* but the student has no Download button | The request has no *Generated Transcript* link. This happens after auto-approval (see Open questions). Approving again is blocked for *Generated* requests, so set *Generated Transcript* on the request form by hand. |
| Transcript shows YEAR I, YEAR II … one per term | Year Mappings are missing in Transcript Settings. |
| CGPA blank or 0.00 | Student Master *Current CGPA* is empty. Run *Cumulative GPA* on the Term Results page. |
| Course missing from the transcript | Its Course Marks row is *Dropped, Detained* or *Migrated*, or (year-based) it was replaced by a later re-exam attempt. |
| Grade point shows 0.0 | No Course Schema Assignment for that exam plan + course, or the grade is not in its grading schema. |
| Logo or signature upload refused | Upload with the Upload button; pasted images are not accepted. |
| Request stuck in *Draft* | Payment is switched off. Approve it from the Requests tab (the form button shows only for Submitted / Under Review / Approved). |

---

## 13. Known limitations / Open questions

1. **Auto-approved requests are not linked to their transcript.** After payment with auto-approve on, `mark_request_paid` sets status *Generated* but never writes `transcript_doc`, and sends no *Ready* email. The portal Download button and `download_my_transcript` both need `transcript_doc`, so the student cannot download. (`slcm/api/transcript_request.py`, `mark_request_paid` and `_do_generate_transcript`)
2. **Tax is previewed but not charged.** `get_fee_preview` adds Tax / GST to the total, but `TranscriptRequest._apply_fee_settings` stores fee × copies + urgent surcharge only, and that is what the gateway charges. (`slcm/api/transcript_request.py`, `slcm/slcm/doctype/transcript_request/transcript_request.py`)
3. **Settings fields with no effect:** *Free Requests Per Student*, *Assignment Rules* (Transcript Assignment Rule), *Normal/Urgent Processing Days* (display only), *Currency* (Razorpay orders are always INR); Transcript Settings *Use Year-Based Layout* and *Courses Per Page*; Transcript Template *Page Size, Orientation, Show Credits* and *Type* (except blocking delete). (`transcript_fee_settings.json`, `transcript_settings.json`, `transcript_template.json`, `student_transcript.py`)
4. **Transcript Assignment Rule → Programme links to *SLCM Batch*,** not Programme. (`slcm/slcm/doctype/transcript_assignment_rule/transcript_assignment_rule.json`)
5. **Payment switched off leaves requests in *Draft*.** Nothing moves them to *Submitted*, and the form's Approve button is hidden for *Draft*. (`transcript_request.py` `_apply_fee_settings`, `transcript_request.js`)
6. **A type with fee 0 while payment is on** still sets *Payment Required* and *Payment Pending*; a zero-amount gateway order is likely to fail. Not tested. (`_apply_fee_settings`)
7. **Unpublished results are printed.** Transcripts read all Student Course Marks and any Student Result Publish *Term GPA*, without checking *Is Published*. The "no published results" check exists only as a warning and disabled buttons on the portal page; `create_request` does not check it. (`student_transcript.py` `get_transcript_context`; `www/student-portal/transcript-request.html`)
8. **Superseded re-exam attempts are listed without a marker** on the standard and compact layouts, so a course can appear twice with different grades. (`student_transcript.py`; fixture print format *Student Transcript*)
9. **Approve / Reject from the page do not update the Helpdesk ticket.** `approve_request` / `reject_request` use `frappe.db.set_value`, which skips `on_update` and `_sync_helpdesk_ticket`. (`slcm/slcm/page/transcript_management_page/transcript_management_page.py`)
10. **Page methods have no role check.** `approve_request`, `reject_request`, `generate_transcript`, the download methods, and the CGPA scale `save_scale` / `populate_scale` (which use `ignore_permissions`) can be called by any desk user, not only the page roles. Academics User has no DocType permission on Transcript Request but can approve through the page. (`transcript_management_page.py`, `cgpa_percentage_scale.py`)
11. **CGPA Percentage Scale page role is "Academic User"**, which does not exist in the role fixtures (the app uses *Academics User*). The DocType itself is System Manager only. (`slcm/slcm/page/cgpa_scale_page/cgpa_scale_page.json`)
12. **`StudentResultPublish.after_save` never runs.** Frappe has no `after_save` hook, so publishing through that DocType does not write CGPA to Student Master. Only the Term Results page does. (`slcm/slcm/doctype/student_result_publish/student_result_publish.py`)
13. **CGPA scale is fixed at 0–7** in *Populate*, and the compact layout prints "/ 7.00". Another grading scale needs a manual table and a template change. (`cgpa_percentage_scale.py`, `compact_transcript.html`)
14. **Two different CGPA calculations.** `student_result_publish._calculate_cgpa` uses `Grading Schema.get_grade_point(marks)` over published plans and does not drop superseded attempts; Term Results `_compute_cumulative_stats` uses the grade's grade point over all plans and does. Which is authoritative? (`student_result_publish.py`, `slcm/slcm/page/term_result/term_result.py`)
15. **Unused code paths:** `assign_request` (no UI; the only way to *Under Review*), `download_year_based_transcript(_pdf)` and `generate_and_download` have no caller; `slcm/templates/transcript_pdf.html` is not referenced. The Students tab "Final" column is commented out.
16. **One Student Transcript per student + type** from the Students tab; `download_transcript` picks any record of that type, which may be one created by a request.
17. **No layout for Consolidated Marksheet**, Duplicate or Digital; they print as the standard transcript.
18. **Portal menu link is commented out** for the Transcript Request page (`www/student-portal/_base.html`). Is Helpdesk now the intended entry point?
19. **Revoked** has no workflow: no button sets it and it does not block downloads.

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| Request DocType, fee on insert, desk emails, Helpdesk sync | `slcm/slcm/doctype/transcript_request/transcript_request.py`, `.js` (Approve & Generate / Reject buttons, "Provisional" label) |
| Portal API: fee preview, create, pay (Razorpay / Easebuzz), confirm, cancel, failures, download | `slcm/api/transcript_request.py` |
| Transcript data builders (`get_transcript_context`, `get_compact_transcript_context`, `get_year_based_transcript_context`) | `slcm/slcm/doctype/student_transcript/student_transcript.py` (registered as Jinja methods in `hooks.py`) |
| Management page (Students + Requests tabs, approve/reject, downloads, print-format self-patching) | `slcm/slcm/page/transcript_management_page/` |
| Templates page | `slcm/slcm/page/transcript_template_page/` |
| CGPA scale lookup / populate | `slcm/slcm/doctype/cgpa_percentage_scale/cgpa_percentage_scale.py`, page `slcm/slcm/page/cgpa_scale_page/` |
| CGPA / term GPA written to Student Result Publish and Student Master | `slcm/slcm/page/term_result/term_result.py` (`generate_term_results`, `_compute_cumulative_stats`) |
| Publish flag | `slcm/slcm/page/publish_result/publish_result.py` (`toggle_publish`) |
| Re-exam superseded attempts | `slcm/slcm/utils/reexam_attempts.py` (`superseded_records`) |
| Print formats | fixture *Student Transcript* in `slcm/fixtures/print_format.json` (imported on migrate); `slcm/slcm/print_format/year_based_transcript/`, `compact_transcript/` (HTML file read directly), `transcript_fee_receipt/` |
| Portal pages | `slcm/www/student-portal/transcript-request.html` + `transcript_request.py`, `documents.html/.py`, fees receipt in `slcm/api/student_portal.py` (`download_transcript_receipt`) |
| Helpdesk ticket flow | `helpdesk/helpdesk/api/nls_student.py` (`create_transcript_request_on_ticket`, `sync_transcript_status_to_ticket`) in the separate helpdesk app |
| Gateway choice / reconcilers / ledger | `slcm/slcm/fee/payment_gateway.py` (`for_transcript`), `slcm/api/razorpay_reconcile.py` (`record_transcript_payment`), `slcm/api/easebuzz_payment.py` (`_transcript_success/_failure`), `slcm/slcm/fee/payment_ledger.py`, `slcm/slcm/fee/portal_charges.py` |
| Row-level student access | `slcm/security/student_scope.py` (wired in `hooks.py`); website-user block on `slcm.slcm.page.*` in `slcm/security/api_guard.py` |
| Result Settings / Consolidated Report | `slcm/slcm/page/result_settings/`, `slcm/public/js/exam/result_settings.js`; `slcm/slcm/page/consolidated_report/`, `slcm/public/js/exam/common.js` → `term_result.download_consolidated_report` |
| Workspace / sidebar / cards | `slcm/workspace_sidebar/transcript_management.json`, `slcm/slcm/workspace/transcript_management/` **and** `slcm/fixtures/workspace.json`; number cards `slcm/slcm/number_card/transcript_requests_*`; charts `transcript_requests_by_status`, `transcript_revenue_trend` |
| Tests | `test_transcript_request.py`, `test_transcript_fee_settings.py`, `test_transcript_template.py`, `slcm/tests/payment/test_portal_gateway_routing.py` |

- All status changes in the API go through `_set_status()` so the Helpdesk ticket stays in sync. Do not call `frappe.db.set_value` on Transcript Request status directly.
- The management page rewrites the *Student Transcript* and *Year Based Transcript* print formats in the database on download if they still contain old markup (`_sync_standard_print_format_template`, `_sync_year_based_print_format_template`).

# Fee Management: User Guide

**Applies to:** Uniquad (SLCM v16), student fee module as on disk, 26 November 2026
**Who this is for:** Finance & Accounts staff (Accounts Manager, Accounts User, Campus Admin) who set up fees, raise dues, record payments, give concessions, refund money and issue fee certificates. Also System Managers who configure gateways and the scheduler.
**Where:** Desk → **Fees Management** workspace (sidebar *Fees Management*). Admission-stage money and admission refunds sit in the **Fee & Refund** sidebar (sections 13.2 and 14).

---

## 1. The flow at a glance

```
1. Set up            Fee Component → Fee Structure (amounts per programme / year / category / Indian-foreign)
2. Raise dues        Fee Notification → Publish → Generate Demands   (one Fee Demand per student per component)
                     + dues raised by events (re-exam, hostel fine, discipline, revaluation, ...)
                     + dues added by hand (Student Fee Management, Fee Demand form, bulk upload)
3. Collect           Student / parent pays online (Razorpay or Easebuzz)  ──┐
                     Office records cash / cheque / bank transfer         ──┴→ Fee Payment → Fee Receipt
4. Adjust            Concession (waiver) · Fine (penalty) · Excess (credit note) · Refund · Stipend
5. Follow up         Daily: mark Overdue → reminder emails → PhD annual dues
6. Report            Fees Dashboard · Fee Reports · registers · settlement reports · fee certificates
7. Accounting        Every money record is posted to ERPNext by the bridge (see spec/erpnext_bridge)
```

**The one rule to remember:** the **Fee Structure** is the single source of amounts. A Fee Notification only says *which component is raised, when, and for whom*. Its row amount is only a fallback.

### Key ideas

| Term | Meaning |
|---|---|
| **Fee Component** | One thing that can be charged, e.g. *Tuition and Facilities Fee*. It carries its Demand Type (Academic / Non Academic), its payment gateway and its Zoho ledger. |
| **Fee Structure** | The price list for one programme + academic year + year of study (+ category). Two tables: Indian and foreign. Named `FS-YYYY-#####`. |
| **Fee Notification** | A run that raises dues for one academic year. Each row = one component for a group of students. |
| **Fee Demand** ("due", "Voucher Number") | One charge on one student. Named `FD-YYYY-#####`. Everything else (payments, concessions, fines, refunds) changes a Fee Demand. |
| **Fee Payment** | Money received against one or more Fee Demands. Submittable. Named `FP-YYYY-#####`. |
| **Fee Receipt** | Made automatically when a Fee Payment is submitted. Named `NLS-RPT-#####`. |
| **Excess** | Money the student has with the university that is not on any due. Held as **Student Credit Notes** (`CRN-YYYY-#####`). |
| **SLCM Payment Request** | The ledger row for every online gateway payment (paid or failed), with settlement and refund details. Named `PR-YYYY-#####`. |

---

## 2. Setting up fees

### 2.1 Fee Component
*Fees Management → Set up fees → Fee Component* (System Manager only)

| Field | Notes |
|---|---|
| Component Name | The record name, e.g. `Tuition and Facilities Fee`. |
| Component Type | Fixed list (Tuition Fee, Hostel Fee, Housing and Mess Fee, Examination Fee, Revaluation Fee, Gap Year Fee, Fine - Hostel, Fine - Disciplinary, Annual Fee (PhD), Continuation Fee (PhD), Convocation Fee, Student Refundable Deposit, …). Event dues find their component **by type** (section 3.3). |
| Demand Type | **Academic** or **Non Academic**. Every Fee Demand copies this, whatever the caller passed. |
| Payment Gateway | **Razorpay** (default) or **Easebuzz**. Decides which gateway collects this component online. |
| Is Taxable / Tax Rate | Used by the Fee Structure to add tax to the amount. |
| Ledger | Zoho ledger name (used by the Zoho journal report). |

The Fee Component list has a bulk action to change the payment gateway of many components at once. It warns when the target gateway is not configured.

### 2.2 Fee Structure
*Fees Management → Set up fees → Fee Structure*

| Field | What to enter |
|---|---|
| Fee Structure Name | Free text label |
| Programme, Academic Year | Required |
| Year No | 1–5. The year of study this price applies to. |
| PhD Year From / To | For research programmes: a range of years (e.g. 1–3) instead of one Year No. |
| Student Category | Blank / All = general. A specific category (SC, ST, OBC, OBC-NCL, EWS, NRI, NA, Other) wins over the general structure for those students. (The field is hidden on the form.) |
| Applicable | **Student** for campus fees. Applicant / Faculty / Others are used by the admission flow. |
| Valid From / Valid Until | Validity window. Open end is allowed. |
| Status | Active / Inactive |
| Demand Type, Due Offset Days (default 30), Is One-Time Fee | Used when dues are generated (section 3). |
| Fee Components for Indian / for Foreign | One row per component: amount, tax (from the component), total, optional student category. |
| Online Payment + Payment Gateway | Used only by the legacy Fee Invoice flow (section 15). |

**What the system calculates**
- Each row: `tax = amount × tax rate`, `total = amount + tax`.
- *Total Amount for Indian* and *Total Amount for Foreign* = sum of row totals.

**Rules the system enforces**
- Valid From cannot be after Valid Until.
- Only one **Active** structure may cover overlapping dates for the same Programme + Academic Year + Year No + Category + Applicable + Offer Round + Payment Gateway. Blank and "All" category count as the same.
- A structure used by an Offer Configuration cannot be set Inactive.

**What happens on save:** when an Active *Student* structure changes status, dates or totals, a background job re-syncs the fee fields on Student Master for every active student of that programme (section 15).

**How a student's structure is chosen** (`fee_demand_utils.find_fee_structure`)
1. Programme = the student's latest **Enrolled** Student Enrollment, else Student Master *Programme of Study*.
2. Year = Student Master *Current Year* read as a number ("1st Year" → 1).
3. Category = Student Master *Quota*.
4. Only Active, Applicable = Student, valid on the date.
5. Own-category structure first, else the general one.

**How a component's amount is read** (`get_component_amount`)
- Indian students use the Indian table. Foreign students (nationality not blank / Indian / India) use the foreign table, **falling back to the Indian table** when the structure has no foreign rows.
- A row for the student's category wins over "All" rows.
- The amount is the tax-inclusive *total*.

### 2.3 Hostel Fee Structure
*Set up fees → Hostel Fee Structure*. One record per Academic Year + Hostel (+ room type): fee component, amount, refundable flag. Named `FEE-{academic_year}-{hostel}`. See open question Q1: no code reads it.

### 2.4 Bulk Fee Structure Update
*Set up fees → Bulk Fee Structure Update* (System Manager, `slcm_FINO Officer`)

Moves many students to a new Fee Structure at once.

| Step | What happens |
|---|---|
| Choose scope | **Batch** (SLCM Batch) or **Programme**, the new structure, optional batch-year and academic-year filters, a reason. |
| Preview | Lists the students, the fee increase and the new outstanding. Status → *Previewed*. |
| Apply | Updates Student Master fee fields (and, if ticked, outstanding Fee Invoices). Status → *Applied*. An applied record cannot be changed. |

This works on the Student Master / Fee Invoice fields (section 15), not on Fee Demands.

### 2.5 Online gateways
*Settings → Payment Gateway, Razorpay Settings, Easebuzz Settings*

| Charge | Gateway is taken from |
|---|---|
| Fee Demand | Its Fee Component's *Payment Gateway* |
| Fee Invoice (legacy) | Its Fee Structure's gateway (if Online Payment is ticked), else its components' (must all agree) |
| Re-exam / improvement exam fee | Re Exam / Improvement Exam Course Setting, default **Easebuzz** |
| Transcript fee | Transcript Fee Settings |
| Anything unset | Razorpay |

The payer never chooses the gateway. A gateway is "ready" when Razorpay has an API key, or Easebuzz is enabled and has a merchant key. A checkout on a gateway that is not ready is refused with "Online payment through … is not set up yet".

---

## 3. Raising dues

### 3.1 Fee Notification (bulk annual dues)
*Fees Management → Raise dues → Fee Notification* (Accounts Manager, Campus Admin, System Manager)

| Field | Notes |
|---|---|
| Notification Name | Record name |
| Academic Year | The dues' academic year |
| Issued Date / Effective From | Effective From cannot be before Issued Date. Due dates count from Effective From. |
| Fee Components (table) | One row per component + student group (below) |
| Status | Draft → Published |

**Component row**

| Field | Meaning |
|---|---|
| Fee Component | Required |
| Fee Structure | Optional. Forces this structure for every student of the row. |
| Programme / Batch (SLCM Batch) / Year No | Optional filters |
| Program Level | All / UG / PG / PhD (PhD = "Research Course") |
| Student Category | All or one category |
| Fallback Amount | Used only when no Fee Structure lists the component |

**Rules**
- Each combination of component + programme + batch + year + level + category may appear once.
- A filter that matches nobody raises nothing.
- Category rows are processed first. An "All" row then skips students a category row of the same component already covered.

**Buttons**
- **Publish**: needs at least one row. Status → Published. It cannot be un-published.
- **Generate Demands**: only when Published. Runs as a background job (queue *long*).

**What generation does, per student per row** (`generate_annual_demands`)

| Check | Result |
|---|---|
| Component is a hostel type (Hostel Fee, Housing and Mess Fee, Off-campus Housing and Mess Fee) | Skipped: "handled by hostel allocation" |
| No amount from structure and no Fallback Amount | Skipped with the reason (programme, year, category) |
| Structure is One-Time and student is not in year 1 | Skipped |
| A non-cancelled demand already exists for student + component + academic year | Skipped (so the run can be repeated safely) |
| Otherwise | Fee Demand created: amount from the structure, due date = Effective From + structure's Due Offset Days (30 if none), source = this notification |

Only students with Student Status **Active** are considered.

A **Fee Demand Generation Log** (`FDGL-YYYY-#####`) records totals (students, created, skipped, errors) and one result row per student. The notification shows *Last Generated On / By* and links the log.

### 3.2 PhD annual dues (scheduler)
Daily, for every active research-level student with a year of study, in the current academic year:
- Years 1–3: component of type *Annual Fee (PhD)*. Year 4+: *Continuation Fee (PhD)*.
- Skipped when the student already has a non-cancelled Academic demand whose component name contains "PhD" this year.
- Amount from the student's Fee Structure (PhD year range). Due in the structure's offset days.

### 3.3 Dues raised by events
These create a Fee Demand automatically (default due in 30 days). The component is found **by Component Type**. If that type has no component, nothing is raised and an Error Log is written.

| Event | Component type | Amount | Undo |
|---|---|---|---|
| Hostel Allocation inserted | Housing and Mess Fee | An Active Fee Structure with Demand Type *Hostel* (see Q1) | Allocation deleted → unpaid demand cancelled |
| Course Reregistration submitted | Re-registration Tuition Fee | courses × fee per course | Cancel → demand cancelled |
| Re Exam Registration inserted (status Registered, fee > 0) | Examination Fee (else Revaluation Fee) | Re-exam fee | Registration deleted → demand cancelled |
| Revaluation Request submitted | Revaluation Fee | papers × fee per paper | Cancel → cancelled |
| Deferral Order submitted | Gap Year Fee | Gap year fee | Cancel → cancelled |
| Hostel Fine inserted | Fine - Hostel | Fine amount, due in 15 days | — |
| Discipline Order submitted | Fine - Disciplinary | Fine amount, due in 15 days | Cancel → cancelled |
| Convocation Registration submitted | Convocation Fee | Set by the registration (see Q2) | Cancel → cancelled |

- A triggered demand that already has a payment is **not** cancelled; an Error Log is written instead.
- Paying a re-exam or improvement exam fee on its own page cancels the unpaid enrolment demand, so it cannot be paid twice.
- When a hostel-fine or re-exam demand becomes Paid, the fine / registration is marked Paid too (and back to Unpaid / Pending on reversal).

### 3.4 Dues added by hand
- **Student Fee Management → student → Manage Dues → Create Due** (section 8). Remarks are mandatory.
- **Fee Demand form** (+ Add).
- **Bulk upload**: the *Fee demand creation* sheet through Data Import (section 11).

---

## 4. The Fee Demand

*Fees Management → Raise dues → Fee Demand*

### 4.1 Amounts

```
Net Payable  = Original Amount − Waiver (scholarship / concession) + Penalty (fines)
Outstanding  = Net Payable − Paid − Credit Adjusted (excess applied)      (never below 0; 0 when Cancelled)
```

Other money fields: *Refunded Amount*, *Moved to Excess*, *Last Payment Date*, and the last payment's mode, transaction no., bank details.

### 4.2 Filled in automatically
- Registration ID, student email, academic year (if blank), **Batch** (`programme` field, SLCM Batch) and **Programme** (`program`, from the Enrolled Student Enrollment). Stale links on the student are skipped, not errors.
- Demand Type from the Fee Component.
- Description = component name when blank.
- A student given only by Registration ID (bulk upload) is resolved to the Student Master.

### 4.3 Statuses

| Status | When |
|---|---|
| **Pending** | Nothing paid, not past due |
| **Partially Paid** | Some paid, some outstanding, not past due |
| **Overdue** | Past due date with outstanding (set on save and by the daily job) |
| **Paid** | Outstanding 0 and something paid or adjusted |
| **Waived** | Waiver ≥ original amount |
| **Moved to Excess** | Paid money moved to excess and the due kept |
| **Cancelled** | Cancelled. Shown as *Cancelled & Moved to Excess* when money was moved before cancelling. |

### 4.4 Rules the system enforces
- **Once per academic year:** a new demand is refused when the student already has a live demand (not Cancelled / Moved to Excess) in the same group for that year. Groups (matched on words in the component name + type): *Admission*, *Re-admission*, *Tuition* (not "registration"), *Housing* (hostel / housing), *Student Refundable Deposit* (refundable / deposit).
- Waiver cannot be negative or more than the original amount.
- A cancelled demand cannot be edited. Only a payment reversal may still touch it.
- Bulk-imported dues: Due Date must be after Date of Creation.
- Email given on import must match one of the student's emails.
- **Cancel Demand** (form button) only when nothing is paid.
- A stale *Source Document* link (e.g. a deleted re-exam) never blocks later saves or payments.

### 4.5 Who sees which dues
Fee Demand and Fee Receipt reads are scoped by `slcm.security.student_scope` (a student sees only their own).

---

## 5. Collecting payments

### 5.1 Fee Payment
*Collections → Fee Payment*. Submittable.

| Field | Notes |
|---|---|
| Student | Required |
| Voucher Number (`fee_demand`) | For a payment against **one** due. The dues columns fill from it and the covered row is built from the amount. |
| Fee Demands Covered (table) | For a payment across **several** dues: demand + amount allocated. Use either this or Voucher Number. |
| Payment Amount, Payment Date, Payment Mode | Mode: Cash, Bank Transfer, Cheque, Credit Card, Debit Card, Online Payment, Other |
| Reference Number | UTR / cheque no. / gateway payment id |
| Settlement Date, University Bank Account | Bank account is a fixed list of four accounts |
| Payment Gateway | Set only for gateway payments |

**Rules the system enforces**
- Rows with a blank allocation are filled in order up to each due's outstanding. Blank Amount = sum of allocations.
- Total allocated must equal the payment amount. Each allocation > 0 and ≤ the due's outstanding.
- **Offline** payment (no gateway, mode not Online Payment): its Reference / UTR may be used by only one submitted Fee Payment. Settlement Date cannot be before Payment Date.
- Bulk-uploaded payments must have a University Bank Account.

**On submit:** each due's paid amount and status update, the due records the payment details, a payment event is logged on Student Master, and a **Fee Receipt** is created and linked. The ERPNext bridge and the payment ledger are queued.

**On cancel:** dues are re-opened, payment details cleared, the receipt cancelled. For an **online** payment a comment and warning say the money is still with the gateway: re-record it or refund it (it then shows in *Payments to Refund*).

### 5.2 Receipts
- The official receipt is the **Fee Payment** printed in *Fee Payment Receipt - Admin Copy* (desk) or *- Student Copy* (portal).
- Fee Receipt lists the dues paid (*Fee Particulars*). Status Active / Cancelled.
- Other print formats on disk: fee_payment_receipt, fee_receipt, fee_demand_invoice, fee_invoice_receipt, re_exam_receipt, improvement_exam_receipt, transcript_fee_receipt.

### 5.3 Recording offline money
| Where | Use for |
|---|---|
| **Student Fee Management → Record Payment** | Normal route. One Fee Payment across the student's dues. Mandatory: mode (not Online), Reference / UTR, university bank account, payment date, settlement date, remarks (≥ 15 characters). |
| Student Fee Management → **Edit / Delete payment** | Edit = cancel + amended copy (`FP-…-1`) in one transaction. Delete = cancel (record kept). Not allowed once a credit note was raised from its receipt. Offline payments only. |
| Fee Payment form | Hand entry |
| Fee Payment bulk upload | Section 11 |
| **Bulk Fee Collection** (`BFC-YYYY-#####`) | Pick academic year / batch year / programme → *Fetch Students* with pending dues → *Process* creates one Fee Payment + Receipt per student row. Status Draft / Processing / Completed / Completed with Errors. |
| **Mark dues cleared** (Fee Demand list action) | Creates and submits a Fee Payment per student for the full outstanding of the selected dues. Finance roles only. |

### 5.4 Exam fees at the counter
On a Re Exam / Improvement Exam Registration, **Mark as Paid** records a counter payment (any mode except Online Payment, date not in the future). It writes a Re Exam / Improvement Exam Payment Log with status Paid and marks the registration Paid. Refused if already Paid / Captured / Refunded / Cancelled, or the fee is 0.

### 5.5 Paying online (student and parent portals)
*Student portal → Fees & Payments* (`/student-portal/fees`), *Parent portal → Fees* (`/parent-portal/fees`)

The portal shows the student's dues (Fee Demands), legacy Fee Invoices, re-exam fees and hostel fines, with receipts for paid items. The Pending / No Dues badge comes from one shared check (`portal_charges.has_outstanding_dues`); if any dues section failed to load, the badge says Pending.

| Step | What happens |
|---|---|
| Pay one due, or **Pay All** | Server takes the amounts from the dues (max 50 dues per checkout). Paid / Waived / Cancelled dues and dues with nothing outstanding are refused. |
| Exam fees | Refused here: "paid on the Re-Exam / Results page". Unpaid exam demands are hidden from the fee pages. |
| Gateway split | If the selected dues use different gateways, no order is made; the portal offers one checkout per gateway. |
| Checkout guard | Refused if another payer (student vs parent) started a checkout for any of the same charges in the last **20 minutes** that has not finished. The payer's own retry is always allowed. |
| Easebuzz precheck | Needs the payer's mobile number. |
| Razorpay | Order created → browser pays → signature verified → order bound to its intent → one Fee Payment for all dues (capped at what the order charged). |
| Easebuzz | Hosted checkout → return URL / webhook (hash-verified) → settled exactly once against the stored intent; the callback amount must match. |
| Close / fail | Logged as Payment Cancelled / Payment Failed on Student Master's payment log. |

Parents go through the same endpoints with a parent-of-student check (`parent_*` functions in `student_payment.py`, `parent_payment.py`).

### 5.6 Recovery when the browser never comes back
| Job | Interval | What it does |
|---|---|---|
| `razorpay_reconcile.reconcile_pending` | every 15 min | Razorpay orders 10 min – 3 days old with no booking: if Razorpay captured the money, record the Fee Payment (idempotent on the payment id). |
| `easebuzz_payment.reconcile_pending` | every 15 min | Same for Easebuzz; expires abandoned checkouts. |
| `razorpay_reconcile.record_unbooked_captures` | hourly | A captured payment that no record took (paid twice, dues already settled) → **unapplied** SLCM Payment Request, Error Log "needs refund". |
| `payment_ledger.sync_recent` | hourly | Builds missing SLCM Payment Requests for student payments. |
| `fee_service.reconcile_pending_payments` | every 15 min | Admission-side reconciliation. |

### 5.7 SLCM Payment Request (online ledger)
*Collections → Online payments → Payment Request*

- One submitted request per gateway payment id. Reference = the Fee Payment it was booked on (else the exam log / Transcript Request).
- Failed attempts get a **Failed** request with the gateway's reason. A Paid request is never turned Failed.
- Holds payment method, bank reference (RRN/UTR), payer account / bank (filled from the Razorpay API in the background), settlement and refund details.
- **Unapplied money** = captured money no record holds. It is listed in *Payments to Refund*.
- **Record refund** (Accounts Manager, System Manager): records a refund made in the gateway dashboard against unapplied money only. SLCM does not call the gateway's refund API for student fees. A refund of money applied to dues is a **Fee Refund** with Refund Mode *Payment Gateway* (section 6.4).

### 5.8 Settlements
| Source | How |
|---|---|
| Razorpay | Webhook `slcm.api.razorpay_webhook.handle_razorpay_webhook` (signature checked; rejected if no webhook secret) handles payment captured / authorized / failed, refund processed / failed, settlement processed. Daily `sync_settlements.daily_sync_settlements` re-reads the last 5 days of settlements for Payment Requests and FLE Payment Logs. |
| Easebuzz | Daily `easebuzz_settlement.daily_sync` reads payouts (10-day look-back) and fills the same settlement fields. Also per request / date range from the desk. |

Settlement fields: settlement id, UTR, settled at, status, amount, gateway fees, gateway tax, net settled.

---

## 6. Concessions, fines, excess, refunds, stipends

### 6.1 Fee Concession (waiver / scholarship)
*Concessions, excess & refunds → Fee Concession*. Submittable. `CON-YYYY-#####`.

| Field | Notes |
|---|---|
| Voucher Number (`fee_demand`) | The due. Required. Student and dues columns fill from it. |
| Concession Type | University Financial Aid / Mukhyamantri Medhavi Vidyarthi Yojana (MMVY) Scholarship / Aditya Birla Schoalrship (sic) |
| Waiver Value | The amount (not a percentage) |
| Date of concession, Reason | Required |

**Rules:** waiver > 0, ≤ original amount, ≤ unpaid balance; one Approved concession per due; due must not be Paid or Cancelled.
**On submit:** the due's waiver = this value; outstanding recalculated; status Waived (full waiver, nothing paid) or Paid (nothing left).
**On cancel:** waiver removed; due back to Pending if outstanding. A cancelled due stays cancelled.
Also: Student Fee Management **Apply Scholarship** (edit / delete with remarks), list-level bulk apply, bulk upload sheet.

### 6.2 Fine Imposition
*Raise dues → Fine Imposition*. `FINE-YYYY-#####`.

| Step | What happens |
|---|---|
| Criteria | Due date between From / To, optional demand type, programme, academic year, minimum outstanding |
| Rule | Flat amount, or % of outstanding; optional maximum per due |
| Preview | Lists matching dues and the estimated fine |
| Apply | Adds the fine to each due's **Penalty Amount**, logs each row. Status → Applied (once only). |
| Reverse | Takes the penalty back off. Skips a due whose payments would exceed the new net payable (Error Log). Status → Reversed. |

Open, unpaid dues only (not Paid / Cancelled / Waived). Dues of a "Fine…" component type are never fined.

### 6.3 Excess (Student Credit Note)
*Concessions, excess & refunds → Student Credit Note*. Submittable. `CRN-YYYY-#####`.

| Field | Notes |
|---|---|
| Credit Type | Overpayment / Advance Deposit / Scholarship Credit / Other |
| Credit Amount | > 0 |
| Money Received section | How cash-type credits reached the university. Required (Received Via + Date) for cash credit types entered by hand. Can be completed after submit. |
| Source Receipt / Source Fee Demand | Set when excess comes from a paid due |

- Submit → status **Active**, available = credit amount.
- **Apply credit to a due** (form button / *Adjust from Excess* on the page): amount ≤ available and ≤ the due's outstanding; due must belong to the same student and not be Paid / Cancelled / Waived. Adds to the due's *Credit Adjusted*, writes a Credit Adjustment Row. Available 0 → **Exhausted**.
- Cancel only when nothing was used.

**Move to Excess** (Student Fee Management): takes paid money off a due (≤ paid amount) and creates a submitted credit note for it. Option to cancel the due — only when the whole paid amount is moved.

### 6.4 Fee Refund
*Concessions, excess & refunds → Fee Refund*. Submittable. `REF-YYYY-#####`.

| Refund Source | Rules |
|---|---|
| **Fee Demand** (default) | Due required, something paid, refund ≤ paid, one Approved refund per due, due not Cancelled. On submit: due's paid amount ↓, refunded amount ↑, status recalculated. |
| **Excess Amount** | No due. Refund ≤ available excess. On submit: drawn from the student's active credit notes **oldest first** (audit row "Refund REF-…" on each). Cancel restores them. |

Common: refund mode Cash / NEFT / Cheque / Online / Payment Gateway; university bank account required; NEFT / Cheque / Online need account holder, bank, account number and IFSC. Submit → status Approved with approver and date; cancel → Reversed. A *Payment Gateway* refund with a UTR matching a gateway refund id is linked to that Payment Request so ERPNext books it once.

Page route: Student Fee Management → **Refund from Excess** (pre-fills the student's bank details).

### 6.5 Stipend Payment
*Concessions, excess & refunds → Stipend Payment*. Submittable. `STIP-YYYY-#####`. Stipend type *University Financial*, amount > 0, mode, date. Logged on Student Master. Recorded / edited / deleted from Student Fee Management with remarks. See also spec/scholarship.

---

## 7. Daily automation

| Job | When | What |
|---|---|---|
| `fee.scheduler.mark_overdue_demands` | daily | Pending / Partially Paid dues past due → **Overdue** |
| `fee.scheduler.send_due_reminders` | daily | Reminder emails (below) |
| `fee.scheduler.check_phd_year_transition` | daily | PhD annual dues (3.2) |
| `student_master.auto_sync_all_student_fee_structures` | daily | Re-pick each active student's Fee Structure (15) |
| `sync_settlements.daily_sync_settlements` | daily | Razorpay settlements |
| `easebuzz_settlement.daily_sync` | daily | Easebuzz payouts |
| Reconcilers | 15 min / hourly | Section 5.6 |
| `erpnext_bridge.sync.sync_pending` | hourly (long) | ERPNext posting sweeper |

### 7.1 Reminder emails
Settings live in **Student Portal Settings → Reminders**.

| Reminder | Sent | Flag on the due | Default template |
|---|---|---|---|
| 7 days before | on the exact day | 7-Day Reminder Sent | Student Fee Reminder - 7 Days Before Due |
| 1 day before | on the exact day | 1-Day Reminder Sent | Student Fee Reminder - 1 Day Before Due |
| Overdue notice | every due ≥ N days past due (N = *overdue notice offset*, default 3) not yet notified | Overdue Notice Sent | Student Fee Overdue Notice |

- Master switch, each reminder's switch, sender name and from / reply-to address are in the settings.
- Dues that are Paid, Waived or Cancelled are skipped. Each reminder is sent once per due.
- Sent to Student Master *Official Email ID*. Template placeholders: `student_name`, `student_id`, `fee_head`, `outstanding_amount`, `due_date`, `sender_name`. If the template is missing a plain fallback email is sent.

### 7.2 Fee Reminder Tool
*Page `fee-reminder-tool`* (System Manager, Academics User, slcm_finance)

Filter open dues by programme, academic year, demand type and reminder type (7-day / 1-day: not yet due; overdue: past due). Up to 500 rows; shows whether this reminder was already sent. **Send** queues the chosen reminder for the selected dues as a background job, even if sent before, and sets the flag.

---

## 8. Student Fee Management page

*Fees Management → Student Fee Management* (page `student-fee-management`; System Manager, Campus Admin, Accounts Manager, Accounts User)

**Students list:** filters (academic year, term, programme, dues status, fee component, search) apply on **Search**. Totals per student. Header buttons: Fee Reports, Fee Certificates, Bulk Upload, Upload History.

**Student Due Details** (`/student-fee-management/<student>`): dues, payments, receipts, excess, concessions, stipends, refunds.

| Action | Effect |
|---|---|
| Create Due | New Fee Demand (amount > 0, waiver ≤ amount, both dates) |
| Cancel Due | Cancels an unpaid due |
| Record / Edit / Delete Payment | 5.3 |
| Adjust from Excess | 6.3 |
| Move to Excess | 6.3 |
| Add Credit Note | Hand-entered excess |
| Apply / Edit / Delete Scholarship | Fee Concession (6.1) |
| Record / Edit / Delete Stipend | 6.5 |
| Refund from Excess | 6.4 |
| Download Receipt / Receipts (ZIP) / Dues (xlsx) | Receipts print the Fee Payment admin copy |

Every action needs **remarks of at least 15 characters**.

---

## 9. Fee certificates

### 9.1 Setup
*Settings → Fee Certificate Settings* (System Manager): institute details, letterhead header / footer images, signatory (name, designation, signature, seal), bank account details, and **Purposes & Templates**.

Each purpose row: purpose label, certificate type, enabled, include bank details, **Download Only When Fully Paid**, heading, body text (campus student / admission stage, Jinja placeholders), paid line, total label, paid / outstanding rows, bank text, closing text.

| Certificate type | Typical purpose |
|---|---|
| Single Year Fee Demand | Fee Demand Letter |
| Multi Year Fee Structure | Education Loan ("FEE CERTIFICATE") |
| Single Year Fee Receipt | Scholarship Receipt |

### 9.2 Fee Certificate Request
`FCR-YYYY-#####` (Accounts Manager, Campus Admin, System Manager)

| Field | Notes |
|---|---|
| Certificate For | Campus Student (Student Master) or Admission Stage (Applicant) |
| Purpose | Autocomplete from the settings; drives certificate type |
| Academic Year | Requested year |
| Has University Scholarship | Shows the waiver as "Less: University Scholarship" |
| Year-wise Breakdown | Rows computed for multi-year |
| Status | Draft / Generated / Cancelled |
| Edited Certificate | Staff can upload an edited PDF or .docx (converted to PDF); it is then served instead |

**Rules**
- A **Fee Demand Letter** is refused when that year's dues are fully paid ("Generate the Fee Receipt instead").
- Portal download of a purpose with *Download Only When Fully Paid* is refused while the student has any outstanding.
- Amounts shown are each due's original amount; one row per Fee Component.
- Output: PDF (wkhtmltopdf) or Word (.docx).

### 9.3 Where
- **Fee Certificates page** (`fee-certificates`): Generate, list, Bulk Generate (campus students by programme / batch / year / term, up to 1,000, sent 10 at a time), ZIP download (background job above 15 files).
- **Student portal** → Services & Requests → Fee Certificate (`/student-portal/fee-certificate`): the student picks purpose and academic year (from their batch start onward).

---

## 10. Dashboards and reports

### 10.1 Fees Home and Fees Dashboard
- **Fees Home** (workspace block): money tiles, needs-attention list, setup checklist, "How fees work" steps.
- **Fees Dashboard** (page `fee-dashboard`; System Manager, Campus Admin, Accounts Manager, Accounts User): filter by academic year, programme, batch. Card groups: Dues, Dues by type, Collections, Concessions & aid, Excess & refunds, Setup. Fee Demand / Payment / Credit Note / Refund / Concession / UFA / Stipend cards open a breakdown by programme, batch, component, status or mode. Queries respect permissions.

### 10.2 Fee Reports page
*Page `fee-reports`* (same four roles)

| Report | Content |
|---|---|
| Due Wise | One row per due. Filters incl. demand date range, settlement date range (fully paid dues), demand type. |
| Student Wise Outstanding | One row per student, a column per Fee Component |

Both export to Excel in the office sheet layout with a Total row. Cancelled dues are left out.

### 10.3 Script reports

| Report | Based on | Shows |
|---|---|---|
| Defaulter List | Fee Demand | Open dues with days overdue |
| Fee Demand Register | Fee Demand | Every due with amounts and last transaction |
| Fee Demand Aging Report | Fee Demand | Days overdue and aging bucket |
| Collection Summary | Fee Receipt | Collected by component, type, year, mode |
| Receipt Register | Fee Receipt | Every receipt |
| Fee Refund Register | Fee Refund | Every refund |
| Fee Payment Zoho Journal Upload | Fee Payment | Journal rows in Zoho import layout |
| Payment Settlement Report | SLCM Payment Request | Collected vs settled per gateway payment |
| Failed Payment Report | Student Fee Payment Log | Failed attempts with reasons |
| Payments to Refund | SLCM Payment Request | Unapplied money still to refund; Record refund |
| Razorpay Settlement Journal Upload | FLE Payment Log | FLE settlements as journal rows |
| Admission Payment Settlement Report | SLCM Payment Request | Admission-side settlements |

---

## 11. Bulk upload

Sheets mirror the office spreadsheets. Header labels equal field labels, so Data Import (*Insert New Records*) maps them without changes. Data Import's **Download Template** returns these sheets for the fee DocTypes.

| DocType | Sheet |
|---|---|
| Fee Demand | Blank creation sheet (500 rows) with dropdowns and a *Students* lookup sheet; give Registration ID or Student |
| Fee Payment | One row per open due, pre-filled; office fills payment columns. Mandatory: Payment Date, Payment Mode, University bank account |
| Fee Concession | One row per open due, pre-filled; mandatory Date of concession |
| Fee Refund | Rows for excess or paid dues |
| Student Credit Note | Excess sheet |

- A Fee Payment / Concession sheet with a blank mandatory cell is rejected when attached (it is not defaulted to today / Cash).
- **Upload History** (Student Fee Management): lists each fee Data Import with what it created and how much is still active. **Delete upload** reverses every active record through its own cancel logic, all or nothing. Reversed records stay as Cancelled / Reversed.

---

## 12. Roles and access

| Area | Roles (from DocType / page JSON) |
|---|---|
| Fee Component, Hostel Fee Structure, Fee Certificate Settings | System Manager |
| Fee Structure | System Manager, Accounts Manager, Campus Admin, AAD, AAD Staff, Offer Letter Admin |
| Fee Notification, Fee Demand Generation Log, Fine Imposition | System Manager, Accounts Manager, Campus Admin |
| Fee Demand | + AAD, AAD Staff, NLSIU Admin, Student (own only) |
| Fee Payment | System Manager only (see Q5) |
| Fee Concession, Fee Refund, Student Credit Note, Bulk Fee Collection, UFA | System Manager, Campus Admin |
| Stipend Payment | System Manager, Accounts Manager, Campus Admin, AAD, AAD Staff, Student |
| SLCM Payment Request | Several admission and finance roles |
| Fee pages (dashboard, student fee management, reports, certificates) | System Manager, Campus Admin, Accounts Manager, Accounts User |
| Fee Reminder Tool | System Manager, Academics User, slcm_finance |

Site-level Custom DocPerms (Roles & Permissions page) may add to these.

---

## 13. Workspace sidebars

### 13.1 Fees Management (shipped in `fixtures/workspace_sidebar.json`)

| Section | Links |
|---|---|
| (top) | Home, Dashboard, Student Fee Management |
| Set up fees | Fee Component, Fee Structure, Bulk Fee Structure Update, Hostel Fee Structure |
| Raise dues | Fee Notification, Generation Log, Fee Demand, Fine Imposition |
| Collections | Fee Payment, Fee Receipt, Bulk Fee Collection |
| Online payments | Payment Request, Payment Settlement Report, Failed Payment Report, Payments to Refund |
| Concessions, excess & refunds | Fee Concession, University Financial Aid, Student Credit Note, Fee Refund, Stipend Payment |
| Dues raised by events | Re Exam Registration, Course Re-registration, Revaluation Request, Hostel Fine, Discipline Order, Deferral Order, Convocation Registration |
| Reports & certificates | Fee Reports, Defaulter List, Collection Summary, Fee Demand Register, Receipt Register, Zoho Journal Upload, Fee Certificates, Fee Certificate Request |
| Settings | Fee Certificate Settings, Payment Gateway, Razorpay Settings, Easebuzz Settings |
| Audit | User Activity Log |

### 13.2 Fee & Refund (`slcm/workspace_sidebar/fee_&_refund.json`, module SLCM)

| Section | Links |
|---|---|
| (top) | Fee Structure, Applicant Fee Assignment, Payment Gateway, Razorpay Settings, Zoho Journal Settings, Payment Request (SLCM Payment Request) |
| Reports | Applicant Fee Collection (*NLSAT Fee Collection Report*), Student Application Fee Collection (*Student Admission Fee Report*), Zoho Journal Upload (*Fee Payment Zoho Journal Upload*) |
| Refund | Refund Dashboard (page), Admission Cancellation, Refund Policy, Refund Request, Refund Transaction |

This sidebar serves admission-stage money. Section 14 covers its refund part.

---

## 14. Admission refunds (Fee & Refund sidebar)

These are applicant refunds, separate from the student Fee Refund (6.4).

```
Admission Cancellation (ADCAN-#####) → Refund Request (RR-YYYY-#####) → Refund Transaction (RFTR-#####)
```

| DocType | Notes |
|---|---|
| Refund Policy | Name, days from payment, refund %, active |
| Admission Cancellation | Applicant, offer, payment, cancellation type (Student / Admin), reason; status Initiated / Approved / Completed |
| Refund Request | Applicant, Applicant Fee Assignment / Payment Receipt, Razorpay ids, refund type (Full / Partial / No Refund), policy, amount; status Draft → Under Review → Approved / Rejected → Processing → Processed / Failed |
| Refund Transaction | One per gateway refund attempt, with the gateway response |

**Rules (Refund Request):** only Admission Fee or Confirmation Fee assignments; amount from the policy that matches days since payment (confirmation fee uses the structure's confirmation refund %); refund ≤ amount paid, including other open requests. When status becomes **Processed** and the payment id starts with `pay_`, the Razorpay refund API is called and a Refund Transaction is written.

**Refund Dashboard** (page `refund_dashboard`): KPIs and charts over Refund Request + Admission Cancellation (totals, today, this month, status, reasons, programme, campus, processing time) and a recent-refunds list. It does not include student Fee Refunds.

**Zoho Journal Settings** (single): fee component, bank account and department for regular and PACE application fees, used by the Zoho journal report.

---

## 15. Legacy flow: Fee Invoice and Student Fee Assignment

Still on disk and still read by the portals. Not in the Fees Management sidebar.

| DocType | Notes |
|---|---|
| Student Fee Assignment (`SFA-YYYY-#####`) | Student + Fee Structure + due date; its `on_submit` would create a Fee Invoice, but the DocType is not submittable (Q8) |
| Fee Invoice (`FI-YYYY-#####`) | Programme-fee invoice with components and payments; status Unpaid / Partially Paid / Paid / Overdue / Cancelled; online status Payment Initiated / Authorized / Captured / Payment Failed / Refunded. Desk *Pay Online* exists. |
| Student Master fee fields | Fee Structure, Total Program Fee, Scholarship (discount), Net Program Fee, Total Paid, Due Balance, Fee Payment Status, Fee Structure History, Fee Invoices, Payment Log |

- The student portal shows Student Master fee totals in its summary and can mint a Fee Invoice from them (*Pay Now* → `ensure_invoice_and_create_order`).
- A Fee Payment with a Fee Invoice: amount ≤ invoice final payable − earlier payments; updates the invoice and re-totals Student Master. **Fee Demand payments do not update these Student Master totals.**
- **Student Master fee sync** (daily, and on Fee Structure save): picks the student's structure (programme, year, category, nationality) and, when it changed, rewrites Fee Structure, totals and discount, and adds a Fee Structure History row.

---

## 16. ERPNext bridge

Fee Payment, Fee Refund, Student Credit Note (+ adjustments), Stipend Payment, exam payment logs, and admission / PACE / FLE / hostel money are queued for posting to ERPNext on submit / cancel / insert. It does nothing unless ERPNext is installed and posting is on. See **spec/erpnext_bridge/**.

---

## 17. Open questions

| # | Question |
|---|---|
| Q1 | **Hostel fee on allocation.** `on_hostel_allocation_insert` reads `total_amount` from a Fee Structure with Demand Type *Hostel*. Fee Structure has no `total_amount` column (only Indian / foreign totals), so this lookup will fail. The **Hostel Fee Structure** DocType is not read by any code. Which should price hostel fees? |
| Q2 | **Convocation fee.** Convocation Registration reads an `amount` field from Fee Component, which does not exist; it falls back to built-in amounts. Intended source? |
| Q3 | **Unused Fee Structure fields.** *Auto Generate Demand*, *Late Fee* (enabled / amount / after days) and *Cash* have no logic. *Instalments* are used only by the legacy Student Master / Bulk Fee Structure Update code. Keep, hide or implement? |
| Q4 | **Moved to Excess dues.** Moving paid money off a due (without cancelling) raises its outstanding again, but the status stays *Moved to Excess*. The overdue job ignores it; reminders still go out. Is that intended? |
| Q5 | **Fee Payment permission.** Only System Manager has Fee Payment rights in the DocType. *Record Payment* on Student Fee Management inserts a Fee Payment with normal permission checks, so Accounts Manager / User need a site Custom DocPerm. Similarly Fee Concession, Fee Refund and Student Credit Note grant only System Manager and Campus Admin. Confirm the intended roles. |
| Q6 | **Fee Reminder Tool roles** (Academics User, slcm_finance) differ from every other fee page. Do these roles exist on live? |
| Q7 | **Fine Imposition by programme** filters on Fee Demand `program`, which is blank on older dues unless the backfill patch ran. Confirm the backfill on each site. |
| Q8 | **Legacy flow.** Student Fee Assignment is not submittable, so its Fee Invoice creation never runs. Is the Fee Invoice / Student Fee Assignment / Student Master fee-totals flow to be retired, and the portal summary moved to Fee Demands? |
| Q9 | **Bank accounts** are a fixed Select list in Fee Payment, Fee Refund and Student Credit Note ("UBI Bank Scholarship" has no number). Should this be a master? |
| Q10 | **Zoho vs ERPNext.** Both the Zoho journal reports and the ERPNext bridge exist. Which is the accounting record of truth? |
| Q11 | **Fee Notification** cannot be un-published or edited back to Draft from the UI. Is a correction path needed beyond re-running Generate Demands (which skips existing dues)? |
| Q12 | **Fee & Refund sidebar** is admission-facing (module SLCM). Which workspace shows it, and should it be merged with Fees Management? |
| Q13 | **Per-course / per-term fees and hostel proration** are not supported (dues are per component per academic year). Confirm they are out of scope. |

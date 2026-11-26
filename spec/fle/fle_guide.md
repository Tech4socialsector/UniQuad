# FLE (Foundations for a Legal Education): User Guide

**Applies to:** Uniquad (SLCM v16), as on disk November 2026
**Who this is for:** Admissions and finance staff who run the FLE certificate course registrations, and developers who support them.
**Where:** Desk → **Admission → FLE** (desktop icon *FLE*, sidebar *FLE*). Candidates use the website pages under `/fle/` and the web form `/foundations-for-a-legal-education`.

FLE is a short online certificate course run through PACE. It has its own sign-up, one-page application form and Razorpay payment. It does **not** use the regular admission portal (Applicant, NLSAT) or the PACE application flow. For those, see [spec/admission/](../admission/).

---

## 1. The flow at a glance

```
1. Account        /fle/login → Create Account (email + mobile)   → "set password" email
2. Password       /fle/update_password.html                       → logged in
3. Application    /foundations-for-a-legal-education/new          (record FLE-YYYY-####)
4. Payment        web form "Pay" button → Razorpay                → Payment Initiated
5. Paid           Razorpay callback "Authorized"                  → FLE Payment Log row,
                                                                     Enrolled, LMS Student role,
                                                                     confirmation email
6. Candidate      /fle/enrolled → view application, view receipt
7. Finance        Razorpay settlement (webhook + daily sync)      → settlement fields on FLE Payment Log
                  → FLE Payment Journal / Settlement reports, ERPNext journal (if bridge is on)
```

### Key ideas

| Term | Meaning |
|---|---|
| **Foundations for a Legal Education** | The DocType that holds one candidate's application. Named `FLE-{YYYY}-{####}`, e.g. *FLE-2026-0042*. One per email address. |
| **FLE Payment Log** | One row per payment callback for an application. Named `FPL-{YYYY}-{####}`. Holds amount, Razorpay payment ID, raw gateway response and settlement data. |
| **Authorized = paid** | FLE treats a Razorpay **Authorized** status as a successful payment. Live data uses *Authorized*, not *Captured*. Code that checks "paid" accepts *Authorized*, *Captured* (and *Paid* on the portal pages). |
| **LMS Student** | The role given to the candidate's website user once paid. |

---

## 2. Candidate side (website)

### 2.1 Account and login
*`/fle/login`* (`www/fle/login.html`)

| Action | What happens |
|---|---|
| **Create Account** (email + mobile) | Creates a **Website User** with a random password and sends the *fle_new_user* email with a "set your password" link to `/fle/update_password.html`. The link does not expire (generated date pushed 10 years ahead). An email that already has a user is refused. |
| **Set password** | `/fle/update_password.html`. Sets the password, logs the user in and redirects (see below). |
| **Sign In** | Email + password. Unknown email: "No account found…". Wrong password: "Incorrect password". A desk (System) user is sent to `/desk`. |
| **Forgot password** | `/fle/forgot_password.html`. Sends the *fle_password_reset* email with a link to `/fle/update_password.html`. Not allowed for Administrator or disabled users. |

**Where the candidate lands after login or password set**

| Candidate has… | Goes to |
|---|---|
| An application with payment *Authorized / Paid / Captured* | `/fle/enrolled` |
| An application not yet paid | That application in the web form, to continue |
| No application | `/foundations-for-a-legal-education/new` |

> **Note:** on the login page the "New user? Register Here" link is hidden (commented out). The Create Account panel exists but cannot be reached from the page. See *Open questions*.

### 2.2 Application form
*Web form `/foundations-for-a-legal-education`* (login required)

- Guests are sent to the login page.
- Email (and mobile, when cached) are pre-filled from the account and made read-only.
- Text fields are auto-capitalised (except the email fields). Phone defaults to India (+91).
- The URL is cleaned so the record name is never shown in the address bar.
- One application per account (*allow multiple* is off; edit is allowed until paid).
- Button labels: **Save**, then **Pay**.

**Sections and fields** (from the DocType)

| Section | Fields |
|---|---|
| Candidate Details | Email Address*, Name as it should appear on the Certificate*, Relationship with the candidate (Self / Parent / Guardian), Candidate's email ID, Current occupation (Studying / Working / Other), Gender, Date of Birth*, Nationality (Indian / Foreign National), Address, City*, Pincode, State, Country of Residence* (default India), Contact Number, Where did you hear about the FLE Programme?* |
| Educational Background | Last examination attended* (10th / 12th / UG / PG / Other), Latest Board attended*, Year of passing* (2016–2026 or "Prior to 2016"), Last institution attended |
| Parent/Guardian Details | Name, contact number, email, occupation |
| Payment Details | Payment instructions text (see *Open questions* on the amount) |
| Documents | Government ID card, signature, photo (images) |
| Declaration | Parent/guardian declaration text and **I hereby consent** tick |

\* = mandatory in the DocType. Several selects have an *If Others, mention here* box.

**Rules the system enforces**
- **One application per email address.** A second one is refused with the existing reference number.
- **Declaration consent must be ticked** on a new application (server check, all ages). The form itself only marks it mandatory when the candidate is under 18.
- New records start as *Enrollment Status = In Progress*, *Payment Status = Unpaid*.

### 2.3 Payment
Payment uses the Frappe **Payments** app web-form payment with gateway **Razorpay** (currency INR).

| Event | Effect on the application |
|---|---|
| Candidate clicks **Pay** | Payment Status → *Payment Initiated* |
| Razorpay returns *Authorized* or *Completed* | A **FLE Payment Log** row (status *Authorized*). Payment Status → *Authorized*, Enrollment Status → *Enrolled*. Payment Id and Paid Amount copied from the Integration Request. User gets the **LMS Student** role (user created if missing; an existing password is not reset). *LMS Account Created* ticked. **Registration Confirmed – FLE 2026** email sent with links to the application and receipt. |
| Razorpay returns *Failed* / *Cancelled* | FLE Payment Log row with that status; Payment Status set to it. |
| Any other status | FLE Payment Log row with status *Pending*; application unchanged. |

### 2.4 After payment
*`/fle/enrolled`*: "You have successfully registered for the FLE programme", with:
- **View your application details** → `/fle/view-application?docname=…` (PDF)
- **Payment receipt** → `/fle/view-receipt?docname=…` (PDF)
- Contact: `fle@nls.ac.in`; Sign out.

Only the record's owner or a System Manager can open these pages or PDFs.

---

## 3. Staff side (desk)

### 3.1 Sidebar and workspace
Sidebar **FLE** (`slcm/workspace_sidebar/fle.json`): **Home** (FLE workspace) and **Foundations for a Legal Education** (list).

Desktop icon **FLE** sits under **Admission** and is shown to: *slcm_Registrar, slcm_FINO Officer, slcm_Registration Officer, Campus Admin, Admission Admin, System Manager*.

**FLE workspace (Home)**

| Block | Content |
|---|---|
| FLE Applications (number cards) | **Total Registrations** (all records), **Completed Application** (Payment Status = Authorized), **In Progress Applications** (Enrollment Status = In Progress), **Registered but not applied** (Payment Status = Unpaid) |
| FLE Application Reports (shortcuts) | **Payment Report** → *FLE Payment Journal*; **Settlement Report** → *FLE Razorpay Settlement Report* |
| FLE Analytics (charts) | Where did you hear about the FLE Programme, Gender, FLE Payment (by status, excl. Unpaid), Geography – Nationality, Payment Status Distribution, Geography – State, FLE Registration (count over time) |

### 3.2 Application list and form
*FLE → Foundations for a Legal Education*

| Where | Button | Does |
|---|---|---|
| List → Actions (select rows) | **Download Receipt** / **Download Application** | Opens a PDF per selected record |
| Form | **Payment Log** | Opens the linked FLE Payment Log (first found) |
| Form | **Download Receipt** / **Download Application** | PDF of this record |

**Account Status section** (staff fields): Enrollment Status (*Save / Enrolled / In Progress / Completed / Failed / Dropped / Certificate Issued*), Payment Status (*Unpaid / Payment Initiated / Authorized / Captured / Failed / Refunded / Pending / Cancelled*), Paid Amount, Payment Id, LMS Account Created.

Only *In Progress*, *Enrolled* and the payment statuses in §2.3 are set by the system. *Completed, Failed, Dropped, Certificate Issued* are set by hand; nothing in code reacts to them.

### 3.3 FLE Payment Log
Not in the sidebar; open it from the application form (**Payment Log**) or by search.

| Field | Source |
|---|---|
| Reference No | The FLE application |
| Name, Email | Copied from the application |
| Payment Status | Authorized / Captured / Failed / Refunded / Pending / Cancelled / Payment Initiated |
| Paid Amount, Transaction ID, Transaction Date, Gateway Response | Razorpay Integration Request data |
| Account Number or UPI ID | Not filled by the payment callback |
| **Settlement Details** (read-only): Settlement ID, UTR, Settlement Date, Settlement Status, Gateway Fees, Gateway Tax, Net Settled | Razorpay settlement (§4) |

> One payment can produce more than one log row (e.g. one callback per status). Count paid applications from the application's Payment Status, or count distinct Reference No.

---

## 4. Settlement and accounting

| Mechanism | What it does |
|---|---|
| **Razorpay webhook** `settlement.processed` (`slcm.api.razorpay_webhook.handle_razorpay_webhook`) | Fetches the settlement's per-payment breakdown and writes settlement fields onto the FLE Payment Log whose Transaction ID matches (falls back to SLCM Payment Request for other payments). |
| **Daily job** `daily_sync_settlements` | Re-syncs the last 5 days of settlements, in case webhooks were missed. |
| **ERPNext bridge** (when enabled) | First paid FLE Payment Log of a payment (Authorized/Captured, amount > 0) posts a receipt journal (Credit *FLE Course Fee*); a processed settlement posts an *FLE Settlement* journal. See [spec/erpnext_bridge/erpnext_fee_bridge_test_checklist.md](../erpnext_bridge/erpnext_fee_bridge_test_checklist.md). |

### Reports

| Report | Reads | Use |
|---|---|---|
| **FLE Applications Report** | Applications | Full applicant export; filters on dates, payment/enrollment status, gender, nationality, state, year of passing, LMS account |
| **FLE Payment Journal** (sidebar: *Payment Report*) | FLE Payment Log (local) | Accounting journal export (debit = paid, credit = net settled). Filters for status, dates and journal fields (prefix, suffix, type, account, department, course). Excel/CSV download. **Default status filter is *Captured*** |
| **FLE Razorpay Settlement Report** (sidebar: *Settlement Report*) | Razorpay API live + FLE Payment Log | Per-payment settlement view with fees, tax, UTR. Buttons: **Diagnose Missing Names**, **Fix Contact Names**, **Sync Settlements** (background). Roles: System Manager, Accounts Manager, Accounts User |
| **FLE Settlement Report** | Razorpay API live | Older per-settlement view; not linked from the workspace |
| **Razorpay Settlement Journal Upload** | Razorpay API + FLE Payment Log | Zoho Books journal import format, one debit + credit row per settlement; only FLE payments |

The Uniquad Overall Dashboard also shows FLE cards (registrations, paid, enrolled, money) and counts *Authorized* or *Captured* as paid.

---

## 5. Troubleshooting

| Problem | Cause and fix |
|---|---|
| "An application with the email address … already exists" | One application per email. Use the existing record (candidate logs in and is sent to it). |
| "Please accept the declaration consent…" | Tick the consent box. Required on every new application, whatever the age. |
| Candidate paid but still shows Unpaid | The Razorpay callback did not reach the site. Check the Integration Request for the application and the FLE Payment Log. |
| "No Payment Log Found" on the form | No callback has been logged for this application yet. |
| FLE Payment Journal is empty | The default status filter is *Captured*; live FLE payments are *Authorized*. Change the filter. |
| Settlement fields empty on a log | Settlement not processed yet, or webhook missed. Run **Sync Settlements** in FLE Razorpay Settlement Report, or wait for the daily job. |
| Registrar / FINO user can open the FLE icon but not the list | DocType permissions grant only System Manager (see *Open questions*). |

---

## 6. Open questions

1. **Fee amount.** The web form charges **₹500** (`amount: 500`), but the payment text on the form says **Rs. 12,500/-**. Live data (378 logs, about ₹47.25 L) suggests ₹12,500. The web form is *not standard* (`is_standard 0`), so the live site may have a different amount. Which is correct?
2. **Web form vs DocType fields.** The web form JSON lists fields that do not exist on the DocType (`where_did_you_hear_about_the_fle_programme`, `declaration_html`) and omits mandatory DocType fields (`where_did_you_hear`, `city`, `country_of_residence`, `latest_board_attended`, `year_of_passing`, `last_class_attended`). Is the live web form edited in the database? The JSON on disk may be stale.
3. **Registration link hidden.** "New user? Register Here" on `/fle/login` is commented out and hidden. Is FLE registration closed for the season, or is this a bug?
4. **Success page missing.** The web form's success URL is `fle-success-page`, and [spec/admission/razorpay_success_integration_manual.md](../admission/razorpay_success_integration_manual.md) describes `slcm/slcm/www/fle_success_page.html`. No such page exists on disk. Where does the candidate land after paying? (Login later sends them to `/fle/enrolled`.)
5. **Declaration consent.** Server requires consent for every new application; the form only makes it mandatory under 18, and the text says it is "only for students below 18". Should the server check be age-based?
6. **Desk permissions.** Both DocTypes give access only to System Manager, but the FLE desktop icon is shown to Registrar, FINO Officer, Registration Officer, Campus Admin and Admission Admin. Should those roles get read access? The PDF download APIs also allow only the owner or System Manager.
7. **Dead `lms_automation.handle_payment_paid` hook.** It runs on every save but only acts when Payment Status = *Paid*, which is not an option. It would also reset the password. Remove it?
8. **Enrollment statuses** *Completed, Failed, Dropped, Certificate Issued* have no workflow or code. Who sets them, and is there a certificate step?
9. **FLE Payment Journal default filter** is *Captured*, which hides live *Authorized* payments. Change the default to *Authorized*?
10. **Hard-coded year.** The confirmation email subject says "FLE 2026" and page footers say © 2026. How should next year's intake be handled (new records reuse the same DocType; no intake / year field)?
11. **"Registered but not applied"** number card counts applications with Payment Status = Unpaid. Accounts created without any application are not counted. Is the label right?

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| Application DocType, payment callback `on_payment_authorized`, `validate_payment`, user creation, success email | `slcm/slcm/doctype/foundations_for_a_legal_education/` |
| List/form buttons (PDF downloads, Payment Log) | `foundations_for_a_legal_education_list.js` |
| Payment log DocType | `slcm/slcm/doctype/fle_payment_log/` (list-view columns via `fixtures/property_setter.json`) |
| Web form | `slcm/slcm/web_form/foundations_for_a_legal_education/` (+ `client_script` inside the JSON); header/footer theme `public/js/fle_theme.js` (`webform_include_js`, `web_include_js` in `hooks.py`) |
| Portal pages | `slcm/www/fle/` (`login`, `update_password`, `forgot_password`, `enrolled`, `view-application`, `view-receipt`) |
| Account / login / PDF APIs | `slcm/api/user.py`: `register_fle_user`, `update_password_fle`, `reset_password_fle`, `login_fle_user`, `get_fle_prefill_data`, `download_fle_receipt`, `get_fle_receipt_pdf_base64`, `download_fle_application_pdf`, `get_fle_application_pdf_base64`, `get_payment_status` |
| Emails | `slcm/templates/emails/fle_new_user.html`, `fle_password_reset.html`, `fle_payment_success.html` |
| Settlement webhook | `slcm/api/razorpay_webhook.py` (`handle_settlement_processed`, `complete_payment_settlement`). The `payment.authorized` webhook handles SLCM Payment Request only, not FLE. |
| Settlement sync | `slcm/api/sync_settlements.py` (`run_sync`, `run_sync_background`, `daily_sync_settlements` in `scheduler_events.daily`) |
| Reports | `slcm/slcm/report/fle_applications_report/`, `fle_payment_journal/`, `fle_razorpay_settlement_report/`, `fle_settlement_report/`, `razorpay_settlement_journal_upload/` |
| Workspace, cards, charts | `slcm/slcm/workspace/fle/fle.json`, `slcm/slcm/number_card/fle_*`, `slcm/slcm/dashboard_chart/fle_*` |
| Workspace / sidebar shipping | Created once by patch `slcm.patches.v2_0.create_fle_workspace_and_sidebar`. FLE is excluded from the Workspace fixture so admin edits on the live site survive migrate. |
| ERPNext bridge | `slcm/erpnext_bridge/sync.py` (`FLE_PAID`, `FLE_FIRST_PAID_LOG`, `fle_first_paid_log`), `builders.py` (`_fle_receipt`, `_fle_settlement`) |
| Payments app hook point | `apps/payments/payments/overrides/payment_webform.py` (`accept` → `validate_payment`; gateway URL) |

- Treat FLE **Authorized** as paid everywhere (`["Authorized", "Captured"]`; portal pages also accept `"Paid"`).
- `on_payment_authorized` writes the log with `ignore_permissions` and sets `full_name` / `email` explicitly, because `fetch_from` does not fire on programmatic insert.
- Prefill data is passed through the cache (`fle_prefill`), read once, so the URL stays clean.

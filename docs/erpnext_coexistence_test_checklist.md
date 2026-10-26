# ERPNext Coexistence — Test Checklist

Covers the rename of SLCM DocTypes that clash with ERPNext v16, the ERPNext v16.7.3 install, and the bugs fixed while testing. Sections 1–6 are from `slcm.local` on 2026-10-20 (branch `erp-next-clash`). Section 7 re-verifies everything on 2026-10-26, after `erp-next-clash` was merged into `TFSS` (PR #644).

## 1. What changed

### Renamed DocTypes

Records, record names and field names are unchanged.

| Old | New | Route | Why |
|---|---|---|---|
| Batch | SLCM Batch | `/app/slcm-batch` | ERPNext `Batch` = stock batches |
| Company | SLCM Company | `/app/slcm-company` | ERPNext `Company` = legal entity |
| Department | SLCM Department | `/app/slcm-department` | ERPNext `Department` = HR tree |
| Designation | SLCM Designation | `/app/slcm-designation` | ERPNext ships `Designation` |
| Driver | SLCM Driver | `/app/slcm-driver` | ERPNext `Driver` = delivery trips |
| Payment Request | SLCM Payment Request | `/app/slcm-payment-request` | ERPNext `Payment Request` = accounting document |
| Video | SLCM Video | `/app/slcm-video` | ERPNext ships `Video` |

- **Migration:** patch `slcm.patches.v2_0.rename_erpnext_clashing_doctypes` (pre_model_sync) renames each table and its meta. It also moves customizations and every stored DocType reference, and skips anything owned by ERPNext.
- **Admission "Campus" fields keep linking to `Company`**, which now means ERPNext's Company. That's what the campus API expects (`is_group`).

### Bugs fixed while testing

| Area | Problem | Fix |
|---|---|---|
| CLAT Rank Import, Course Scheduling Tool | Controller class names didn't match the DocType, so every `migrate` deleted both DocTypes as orphans | Classes renamed to `CLATRankImport`, `CourseSchedulingTool` |
| Bulk Fee Structure Update | `batch_year` linked to a non-existent DocType; students were filtered on removed field `programme` | Link → `Student Batch Name`; filter on `batch`; batch year applied through the student's fee structure |
| Application fee payment | Auto-created "Application Fee" component missed mandatory `demand_type`, so payment completion failed | `demand_type = "Non Academic"` |
| Payment reconciliation scheduler | A failure after an inner commit raised "SAVEPOINT does not exist" and stopped the whole run | Falls back to a full rollback |
| Student portal → Placement | Imported non-existent `frappe.utils.nowdatetime`, so the page crashed | Uses `frappe.utils.now` |
| Placement analytics | Grouped Placement Offer by non-existent `status` | Uses `offer_status` |
| Examination result → faculty list | Queried non-existent `faculty_name` / `image` | Built from `first_name` / `last_name` / `photo` |
| Payment Settlement report | Crashed when called without filters | `filters = filters or {}` |
| New upstream patch `backfill_student_master_batch` | Queried `tabBatch` after the rename | Uses `SLCM Batch` |
| Dependencies | `xlsxwriter` imported but undeclared; `pytest` missing | Added to `pyproject.toml` (dependency / dev-dependency) |

### Payment test suite fixes

The suite used to damage the site, which made it unsafe to run.

| Problem | Fix |
|---|---|
| Restored every naming counter to its value before the test, winding back numbers that background jobs had taken meanwhile (duplicate Journal Entry `ACC-JV-2026-00065` after the merge) | Counters are never lowered (2026-10-26) |
| `setUp` deactivated all Fee Structures / Admission Years, closed PACE Admissions, overwrote Razorpay keys, and never restored them | Snapshot taken before each test; restored after it, even on failure |
| Overwrote real Fee Component amounts (Hostel Fee 30,000 → 1,000; Tuition Fee 50,000 → 1,000) | Tests use their own `_Test …` components |
| Reset the site-wide naming counter `""` (shared by 22 `format:` DocTypes) to ~1, causing duplicate names, e.g. Admission Cycle Audit Log | Counters are only ever raised |
| Reused real Fee Structure `FS-2026-00003` | Dedicated `_Test Fee Structure Payments` |
| Missing fixture data (Programme, PACE user) | Created by the tests and removed afterwards |
| Stale expectations: unsigned webhooks, receipt `docstatus`, offer status names, unpaid receipt | Updated to current app behaviour |

## 2. Deployment order (production)

1. `bench --site <site> backup --with-files`
2. Install Python deps: `bench setup requirements --python` (adds `xlsxwriter`).
3. Deploy the SLCM code, then run `bench --site <site> migrate` **with a background worker running**. Without a worker, Module Profile fixtures leave document locks that fail the next migrate.
4. Check: `bench --site <site> console` → `frappe.db.exists("DocType", "SLCM Batch")` is truthy, and `frappe.db.get_value("DocType", "Batch", "module")` is `None` or an ERPNext module.
5. `bench get-app erpnext` at tag **v16.7.3**, then `bench --site <site> install-app erpnext`.
6. Run the ERPNext setup wizard (Company, currency, fiscal year), then create the campus Companies Admission uses.
7. `bench --site <site> migrate` again. Expect no "Orphaned DocType(s)" message.

Before step 3 on production, search Server Scripts, Client Scripts, custom Reports and print-format HTML for the old names. The patch moves structured references but not names written inside code.

## 3. Test data

Every automated scenario creates its own dummy records and deletes them afterwards (or rolls back).

| Data | Used by | Example values |
|---|---|---|
| SLCM Batch | D1 | name `ZZ Test Batch`, existing Programme; dates fetched from Programme |
| SLCM Department / Designation / Driver / Company / Video | D2, E8, E9 | `ZZ Test Dept` (`department_id` ZZD1); `ZZ Test Designation`; driver `ZZ01` licence `ZZ-LIC-01`; `ZZ Test Recruiter`; video `https://example.invalid/v` |
| SLCM Payment Request | D4 | reference `SLCM Batch` / any batch, amount 100 INR, status Paid; second request with amount 0 (must fail) |
| Placement | E4 | `SLCM Company` "ZZ-E2E Recruiter" → Placement Opportunity (Open, ends in 10 days) → student `anishanthclinton@gmail.com` applies with `/files/zz-e2e-resume.pdf` |
| Faculty + department | E9 | Faculty `ZZE2E`, email `zz-e2e@example.invalid`, department "ZZ-E2E Dept" |
| ERPNext Department | E10 | "ZZ-E2E ERP Dept" under company TFSS |
| Payment suite | G | Applicant "Test Applicant", Programme "Master's Programme in Public Policy" (dummy), Fee Structure `_Test Fee Structure Payments`, components `_Test Tuition Fee` / `_Test Hostel Fee` (accommodation), mocked Razorpay orders `order_*` / payments `pay_*` |

## 4. Results

**PASS** = verified. **ENV** = blocked by the test environment, not the app.

### A. Static checks (whole app)

| # | Check | Result |
|---|---|---|
| A1 | 915 JSON files parse | PASS |
| A2 | 1,677 Python files compile | PASS |
| A3 | 27 changed JS files (`node --check`) | PASS |
| A4 | No merge-conflict markers (after resolving 7 stash-pop conflicts with `development`) | PASS |
| A5 | No old DocType names left in queries, links, routes or SQL (`tab<Old>`, `/app/<old>`) | PASS |
| A6 | No SLCM DocType name clashes with ERPNext v16.7.3 (including the 8 new upstream DocTypes) | PASS |
| A7 | All 430 DocType files: controller class matches name; no dangling Link/Table targets | PASS |

### B. Migration and data

| # | Check | Result |
|---|---|---|
| B1 | Rename preserved data: identical row counts + checksum of names (Batch 8, Department 26, Designation 2) | PASS |
| B2 | All references moved: Comments, Workspace links/shortcuts, Sidebar items, Number Card, Dashboard Chart, Reports, DocType Link, list settings, Notification | PASS |
| B3 | ERPNext-owned records untouched (e.g. Bank Account → Payment Request link) | PASS |
| B4 | Repeated `migrate` is clean; no orphan DocType deletion | PASS |
| B5 | ERPNext 16.7.3 installed; 7 ERPNext + 7 `SLCM …` DocTypes with correct owners | PASS |

### C. Functional checks (rename)

| # | Check | Result |
|---|---|---|
| C1 | No dangling links in SLCM DocTypes / Custom Fields | PASS |
| C2 | Only the 6 Admission campus fields link to ERPNext `Company` | PASS |
| C3 | No SLCM workspace/sidebar/card/chart/report/print format/notification/web form/property setter on old names | PASS |
| C4 | All SLCM Python modules import | PASS, except `foundations_for_a_legal_education/check_config.py` (unused debug script importing a non-existent function) |
| C5 | All 423 SLCM DocType metas + controllers load | PASS |
| D1 | SLCM Batch: create, dates fetched from Programme, term days/weeks (28/4), end-before-start rejected | PASS |
| D2 | Create SLCM Department / Designation / Driver / Company / Video | PASS |
| D3 | Faculty, Student Master, Placement Opportunity links → `SLCM …` | PASS |
| D4 | SLCM Payment Request: `paid_on` auto-set, amount ≤ 0 rejected, manual status change blocked | PASS |
| D5 | SLCM `doc_events` fire on SLCM Payment Request only | PASS |
| E | ERPNext's own 7 DocTypes load | PASS |
| F1 | Data Map counts use SLCM DocTypes | PASS |
| F2 | Campus API returns ERPNext companies (TFSS, TFSS (Demo)) | PASS |
| F3 | 44 read-only page/report/API functions in changed files | PASS (0 errors) |
| F4 | 23 changed student/faculty portal pages render for a real student | PASS (23/23) |

### E. End-to-end scenarios with dummy data

| # | Scenario | Result |
|---|---|---|
| E1 | CLAT Rank Import & Course Scheduling Tool load (no longer deleted on migrate) | PASS |
| E2 | Shared naming series issues unique names above existing (VID-…-0830, 0831) | PASS |
| E3 | Bulk Fee Structure Update: batch scope and programme scope find the student; unknown batch year → 0 students | PASS |
| E4 | SLCM Company → Placement Opportunity → student applies → placement page renders | PASS |
| E5 | Placement analytics | PASS |
| E6 | Examination result faculty list | PASS |
| E7 | Application Fee component auto-created with `demand_type` | PASS |
| E8 | SLCM Driver + Student ID Card link | PASS |
| E9 | Faculty → SLCM Department name lookup | PASS |
| E10 | ERPNext Department created only in ERPNext's table | PASS |
| E11 | Admission campus options come from ERPNext Company | PASS |

### G. SLCM unit tests (`bench run-tests`, 66 modules)

| Group | Modules | Result |
|---|---|---|
| Payment suite (`slcm.tests.payment.*`) | 9 (55 tests) | **PASS 55/55**; site settings restored afterwards (naming counters keep the numbers the tests used) |
| Other modules | 21 | PASS |
| Blocked by ERPNext test records | 21 | ENV: Frappe's test runner follows User → Email Account → Company into ERPNext and creates ERPNext's sample Fiscal Years, which overlap the real FY 2026-2027. Run these on a dedicated test site. |
| Merit-system pytest files | 8 | ENV: pytest-style tests; Frappe's runner discovers 0 tests |
| Admission tests out of date with their DocTypes / fixtures | 6 | Pre-existing (program_media, admission_stage_template, programme_reservation_category, programme_reservation_policy, applicant_fee_assignment, marks_import_export) |

## 5. Manual UI checklist (QA)

Log in as System Manager, then repeat with each role.

**Renamed DocTypes**
- [ ] `/app/slcm-batch`, `/slcm-department`, `/slcm-designation`, `/slcm-company`, `/slcm-driver`, `/slcm-video`, `/slcm-payment-request` list existing records.
- [ ] SLCM Batch: select a Programme → dates and term days/weeks fill in.
- [ ] Faculty form: Department / Designation dropdowns list SLCM records.
- [ ] Student Master: Batch link opens the SLCM Batch.
- [ ] Placement Opportunity: Company dropdown lists recruiter companies.
- [ ] Student ID Card (card type Driver): pick a driver → name/photo fill in.
- [ ] SLCM Payment Request list: "Bulk Sync Settlements" button present; Status read-only.

**Fixed features**
- [ ] CLAT Rank Import and Course Scheduling Tool open and save; still present after `bench migrate`.
- [ ] Bulk Fee Structure Update: preview with Update Scope = Programme (cohort) lists that batch's active students; Batch Year filter limits to students whose fee structure has that batch year.
- [ ] Student portal → Placement: page opens; applying to an open opportunity works.
- [ ] Analytics dashboard → Placement section loads.

**Payments (Razorpay test mode)**
- [ ] Applicant application fee: order → pay → receipt generated → SLCM Payment Request = Paid (works even when "Application Fee" component doesn't exist yet).
- [ ] Offer confirmation fee → full-fee assignment created (accommodation excluded when "needs accommodation" = No) → full fee → Offer Letter = Full Fee Paid.
- [ ] PACE fee payment and receipt.
- [ ] Failed payment → SLCM Payment Request = Failed.
- [ ] Webhook `payment.captured` / settlement updates the SLCM Payment Request.
- [ ] Reports: Payment Settlement, Admission Payment Settlement, Failed Payment.

**ERPNext**
- [ ] `/app/batch`, `/app/company`, `/app/department`, `/app/payment-request` open ERPNext's DocTypes.
- [ ] Admission campus dropdown lists ERPNext Companies.

## 6. Known gaps (not changed)

- **Student Master `programme` → `batch` refactor (upstream, in progress).** About 220 references in 33 files (portal pages, reports, utilities) still read `student.programme`, a field removed in 338603c7. They work on existing sites only through the leftover DB column; a fresh site would fail. Finish this together with the team that owns it.
- `get_value("SLCM Batch", …, "cohort_name")` in portal pages reads a field Batch doesn't have; the pages fall back to the raw value.
- Admission Cycle Audit Log names use the odd format `ACAL-.2026.-.NNNNN`. The names are harmless now that the shared counter is correct.
- `admission/utils/deadline.py` is dead code referencing removed objects (`check_config.py` was deleted on 2026-10-26).
- 6 Admission unit tests are out of date with their DocTypes.

## 7. Re-verification after merging into TFSS (2026-10-26)

`erp-next-clash` (rename + ERPNext fee bridge) was merged into `TFSS`, which had gained 34 commits since the branch was cut. Backup taken first (`20261026_125155-slcm_local-database.sql.gz`), then `bench migrate` with a worker running.

### Fixed during this round

| Area | Problem | Fix |
|---|---|---|
| Admission sidebar (new on TFSS) | `link_to: "Payment Request"` would open ERPNext's Payment Request list | `SLCM Payment Request`. The file is a Frappe 17 `Sidebar`, so it only syncs after the Frappe 17 upgrade |
| `foundations_for_a_legal_education/check_config.py` | Unused debug script; failed to import (`create_razorpay_order` no longer exists) | Deleted |
| Fixtures | 4 Property Setters for DocTypes that no longer exist (Class Schedule, LMS Certificate, Program Reservation Policy ×2) and LMS's `job-opportunity` Web Form | Removed from `property_setter.json` / `web_form.json` and from the site DB (otherwise `export-fixtures` writes them back) |
| Payment test suite | Wound naming counters back after each test; with the fee bridge now posting Journal Entries in the background, this reissued `ACC-JV-2026-00065` and the next posting failed with a duplicate name | Counters are never lowered |

### Automated tests

Run in this order; all three are safe on a development site (the first rolls back, the others clean up after themselves).

```
bench --site <site> run-tests --module slcm.tests.test_erpnext_coexistence
bench --site <site> run-tests --module slcm.tests.payment.<module>      # 9 modules
bench --site <site> run-tests --module slcm.erpnext_bridge.tests.test_bridge
```

| # | Check | Result |
|---|---|---|
| H1 | Trial merge `erp-next-clash` → `TFSS` | PASS, no conflicts |
| H2 | No code added on TFSS since the branch point uses the old names | PASS (only the Admission sidebar, fixed) |
| H3 | `hooks.py` after merge: no duplicate `doc_events` keys | PASS |
| H4 | `bench migrate` | PASS, no errors, no orphan DocTypes deleted |
| H5 | 30 JS files changed by the merge pass `node --check`; all Python compiles | PASS |
| H6 | `slcm.tests.test_erpnext_coexistence` (new, 28 tests) | **PASS 28/28**, 0 skipped, no records left behind |
| H7 | Payment suite, 9 modules | **PASS 55/55** |
| H8 | ERPNext fee bridge tests | **PASS 32/32**, three rounds right after the payment suite (the order that exposed the counter bug) |
| H9 | Every naming counter ≥ the highest record using it (56 series) | PASS |

`slcm.tests.test_erpnext_coexistence` covers:

| Class | What it checks |
|---|---|
| `TestRenameSchema` | 7 `SLCM …` DocTypes in SLCM modules with tables; bare names not owned by SLCM; rename patch logged; no SLCM Link field on a bare name except the 6 Admission campus fields; no SLCM report / number card / chart / notification / script / workspace link on a bare name; Property Setters moved to `SLCM Payment Request`; stale fixtures gone; Admission sidebar file; every SLCM Python module imports |
| `TestSLCMBatch` | Batch created from a Programme takes its term dates, term days/weeks computed; end-before-start rejected; Section names `<batch>-A`; Student Master batch links resolve; nothing lands in ERPNext's stock `Batch` |
| `TestFacultyMasters` | Department + Designation on a Faculty; faculty portal nav shows the SLCM department name; Curriculum / Programme link to `SLCM Department`; nothing lands in ERPNext's `Department` |
| `TestPlacementCompany` | Recruiter `SLCM Company` → Company Contact (`<company>-<contact>`) → Placement Opportunity; end-before-start rejected; nothing lands in ERPNext's `Company` |
| `TestDriverAndVideo` | Driver named `DRV-<id>`; Driver ID card fills name and phone from the driver and queues image generation; Video named `VID-…` |
| `TestSLCMPaymentRequest` | `PR-…` naming; Paid sets `paid_on`; amount 0 rejected; status locked on the form, changeable only with the backend flag; receipts link to `SLCM Payment Request`; nothing lands in ERPNext's `Payment Request` |
| `TestERPNextSide` | ERPNext Department stays in ERPNext's table; campus options are ERPNext Companies; ERPNext's Payment Request is intact |
| `TestPortalPages` | 9 student portal pages render (200, no traceback) as a real student with a batch; Data Map counts use the SLCM DocTypes |

### Test data used

All records are prefixed `ZZT` (or use `example.com` addresses) and are rolled back.

| DocType | Values |
|---|---|
| SLCM Batch | `ZZT MPP 2026 - Trimester I`, from the latest Programme with term dates and a Programme Master (e.g. `MPP-2026-2027-TRIMESTER-I`, 2026-06-01 → 2026-08-31) |
| SLCM Department | `ZZT Constitutional & Administrative Law`, id `ZZT-CAL`, Active |
| SLCM Designation | `ZZT Associate Professor` |
| Faculty | Ananya Rao, `ZZT-FAC-001`, `ananya.rao.zzt@example.com` |
| SLCM Company | `ZZT Khaitan Legal Associates`, industry Legal; contact Meera Iyer |
| Placement Opportunity | Internship, Open, closes in 10 days, role `ZZT Litigation Associate` |
| SLCM Driver | Ravi Kumar, id `ZZT07`, licence `KA01 20190012345`, phone 9845012345 → Driver ID card valid 1 year |
| SLCM Video | "Orientation 2026: Welcome Address" |
| SLCM Payment Request | ₹25,000 INR for `priya.nair.zzt@example.com`, referencing the test batch |
| ERPNext Department | `ZZT Accounts Office` under the first ERPNext Company |
| Portal | First Student Master with a batch and a user (here `STUD-2026-00003`) |

### Manual QA after deploying TFSS

- [ ] Section 5 checklist still passes on the merged build.
- [ ] `/app/slcm-payment-request` lists admission payments; `/app/payment-request` opens ERPNext's (empty) list.
- [ ] Desk search for "Job Opportunity" and the old Class Schedule naming series shows nothing from SLCM.
- [ ] After the Frappe 17 upgrade: Admission sidebar → "Payment Request" opens `SLCM Payment Request`.

### Not caused by the merge (noted, not changed)

- `bench migrate` prints 6 "…json missing" lines for dashboard cards (e.g. `total_quizzes`, `fa_mfa_applications`) that a Dashboard record references but no file defines.
- Several Programmes (`B.Sc Biotechnology`, `BA LLB (Hons)`, `LLM`, `PhD in Law`, `P-2026-2027-TRIMESTER-I`) point at Programme Masters that don't exist, so a Batch can't be created from them.
- The payment suite leaves well over a hundred Error Log entries on every full run: "Error Attaching File" for dummy files (`photo.jpg`, `sig.png`, `id.pdf`, `dummy_certificate.pdf`) that don't exist; PDF generation failing on its mock request (`'MockRequest' object has no attribute 'query_string'`); and its failing-gateway cases. Test noise, not app errors. The 54 "Admission Cycle Audit Log Error" duplicates seen on the first run were the counter bug fixed above; none since.
- `slcm.tests.test_erpnext_coexistence` writes no Error Logs.

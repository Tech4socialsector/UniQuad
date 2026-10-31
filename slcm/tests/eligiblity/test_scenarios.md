# SLCM Eligibility Evaluation & National Test Exemption - QA Test Specification & Playbook

**Document Type:** Frappe QA Test Specification & Execution Standard  
**Applies To:** `slcm` (Student Lifecycle Management System)  
**Module:** Admission (`admission`)  
**Feature:** Eligibility Evaluation, Eligibility Rules, Rule Mapping, National Test Exemptions  
**Target DocTypes:**
- `Eligibility Rule` (`tabEligibility Rule`)
- `Eligibility Allowed Degree` (`tabEligibility Allowed Degree`)
- `Eligibility Rule Mapping` (`tabEligibility Rule Mapping`)
- `National Test` (`tabNational Test`)
- `National Test Exemption Rule` (`tabNational Test Exemption Rule`)
- `Eligibility Evaluation` (`tabEligibility Evaluation`)
- `Applicant` (`tabApplicant` - `validate_eligibility()`)

---

## 1. Feature Analysis & Architecture

### 1.1 Business Rules & Logic Overview
1. **Pre-requisite Validation**: `validate_eligibility()` requires `program`, `campus`, `admission_cycle`, and `academic_year`. If any are missing, status is cleared and validation exits.
2. **Step 0 — National Test Exemption Check**:
   - System searches active `National Test Exemption Rule` matching `campus`, `admission_cycle`, `academic_year`, `national_test`, and target `program` (in `applicable_program` child table), ordered by `mark_percentage DESC LIMIT 1`.
   - If applicant score (`percentage`) >= rule `mark_percentage`:
     - If `overrides_academic_rule == 1`: Applicant is immediately marked **Eligible**, academic checks are bypassed, exemption flags (`exempts_entrance_test`, `exempts_interview`) are set, `Eligibility Evaluation` is saved, and validation returns.
     - If `overrides_academic_rule == 0`: Exemption flags are set, but execution proceeds to academic rule checks.
   - If score < cutoff or rule inactive/mismatched: Exemption flags are cleared (`0`) and execution proceeds to academic checks.
3. **Step 1 — Academic Rule Mapping Search**:
   - System queries active `Eligibility Rule Mapping` matching `campus`, `admission_cycle`, `program`, and `applicant_type` ("Domestic Applicants" for `foriegn_national == "No"`, "International Applicants" for `foriegn_national == "Yes"`, or "Both").
   - **No Mapping Rule**: If no active mapping exists for the program, the program has open admission → Applicant marked **Eligible**.
4. **Step 2 — Reservation Category Priority & Academic Evaluation**:
   - Applicant categories are derived (`EWS`, `OBC-NCL`/`SC`/`ST`/`General`, `PWD`, `Karnataka`, `Women`).
   - If mapping defines `Rule Mapping Category` overrides, applicant's categories are matched and sorted by `priority ASC` (lowest integer is evaluated first). Primary matched category row is evaluated.
   - If no category matches, system falls back to `General` baseline (base `Eligibility Rule` thresholds).
   - **Nested OR Logic**: Evaluation across category paths and rules uses OR logic — if ANY qualifying path (Category + Rule) passes both numeric thresholds and non-percentage checks (HSC stream / allowed degrees), applicant is **Eligible**.
   - **Academic Threshold Checks**:
     - Class XII: Checks `hsc_percentage` against required HSC % with operator (`>=`, `<=`, `=`). Also checks `class_x_percentage` against `sslc_percentage`.
     - Undergraduate: Checks max `ug_cgpa` across studied degrees in `ug_degree_details` against required UG CGPA.
     - Postgraduate: Checks max `pg_cgpa` across studied degrees in `pg_degree_details` against required PG CGPA.
   - **Non-Percentage Checks**:
     - HSC Group: Applicant's `hsc_group` must match an entry in rule's `HSC Groups Mapping` child table (if child table is empty, open to all streams).
     - Allowed Degrees: Applicant's studied degree program must match an entry in rule's `Eligibility Allowed Degree` child table (if child table is empty, open to all degrees).
5. **Step 3 — Ineligibility & Persistence**:
   - If ineligible: `evaluation_status = "Ineligible"`, `status = "Rejected"`, `failure_message` populated with formatted breakdown.
   - **Pre-Throw Persistence**: `Eligibility Evaluation` record is saved to database **BEFORE** `frappe.throw()` is executed. This prevents lost ineligible records due to transaction unwinding.
   - **Web Portal Bypass**: If `flags.skip_eligibility_throw = True`, `validate_eligibility()` updates status and saves DB record without raising `frappe.throw()`.
6. **Exemption Status Sync (`update_applicant_status_from_evaluations`)**:
   - Scans `Eligible` evaluations with checked exemption flags and updates `Applicant.status` to "Excempted Entrance Test And Interview", "Entrance Test Exempted", or "Interview Excempted".

---

## 2. Requirement Traceability Matrix (RTM)

| Requirement ID | Scenario ID | Test Case ID | Requirement Description |
| :--- | :--- | :--- | :--- |
| **REQ-ELIG-001** | `SC-ER-001` | `TC-ELIG-001` | Auto-generation of `rule_code` on `Eligibility Rule` insertion (`ER-001`). |
| **REQ-ELIG-002** | `SC-ER-002` | `TC-ELIG-002` | Validation of mandatory fields on `Eligibility Rule`. |
| **REQ-ELIG-003** | `SC-ER-003` | `TC-ELIG-003` | Unique rule name enforcement on `Eligibility Rule`. |
| **REQ-ELIG-004** | `SC-NT-001` | `TC-ELIG-004` | Master entry creation & unique exam name for `National Test`. |
| **REQ-ELIG-005** | `SC-NTE-001` | `TC-ELIG-005` | Auto-generation of `exemption_code` on `National Test Exemption Rule` (`{year}-{campus}-TE-001`). |
| **REQ-ELIG-006** | `SC-NTE-002` | `TC-ELIG-006` | Pre-requisite check (`campus`, `academic_year`) for exemption code generation. |
| **REQ-ELIG-007** | `SC-ERM-001` | `TC-ELIG-007` | Active status filtering (`is_active = 0` bypasses mapping). |
| **REQ-ELIG-008** | `SC-ERM-002` | `TC-ELIG-008` | Applicant Type filtering (`Domestic Applicants` vs `International Applicants` vs `Both`). |
| **REQ-ELIG-009** | `SC-CAT-001` | `TC-ELIG-009` | Single category reservation override threshold evaluation. |
| **REQ-ELIG-010** | `SC-CAT-002` | `TC-ELIG-010` | Multi-category priority engine evaluation (`priority ASC`). |
| **REQ-ELIG-011** | `SC-NTE-003` | `TC-ELIG-011` | National Test Exemption with `overrides_academic_rule = 1` immediately approving applicant. |
| **REQ-ELIG-012** | `SC-XII-001` | `TC-ELIG-012` | Class XII valid data pass (HSC % & SSLC % >= required). |
| **REQ-ELIG-013** | `SC-XII-002` | `TC-ELIG-013` | Class XII invalid data failure (HSC % < required). |
| **REQ-ELIG-014** | `SC-XII-003` | `TC-ELIG-014` | Class XII invalid data failure (SSLC % < required `sslc_percentage`). |
| **REQ-ELIG-015** | `SC-XII-004` | `TC-ELIG-015` | Boundary value testing (exact required percentage vs just below). |
| **REQ-ELIG-016** | `SC-XII-005` | `TC-ELIG-016` | HSC Group stream match and mismatch verification. |
| **REQ-ELIG-017** | `SC-UG-001` | `TC-ELIG-017` | UG CGPA and allowed degree program validation. |
| **REQ-ELIG-018** | `SC-UG-002` | `TC-ELIG-018` | Max CGPA evaluation across multiple studied UG degree rows. |
| **REQ-ELIG-019** | `SC-EE-001` | `TC-ELIG-019` | Pre-throw persistence of `Eligibility Evaluation` on ineligibility. |
| **REQ-ELIG-020** | `SC-EE-002` | `TC-ELIG-020` | Duplicate evaluation record prevention (upsert key `applicant_name`). |
| **REQ-ELIG-021** | `SC-STAT-001`| `TC-ELIG-021` | Exemption status propagation to `Applicant.status` via `update_applicant_status_from_evaluations()`. |
| **REQ-ELIG-022** | `SC-WEB-001` | `TC-ELIG-022` | Web form `flags.skip_eligibility_throw = True` graceful execution. |
| **REQ-ELIG-023** | `SC-WEB-002` | `TC-ELIG-023` | Program suggestion payload generation (`get_eligibility_suggestion_payload()`). |
| **REQ-ELIG-024** | `SC-EDGE-001`| `TC-ELIG-024` | Handling zero/missing marks and empty child tables. |
| **REQ-ELIG-025** | `SC-TXT-001` | `TC-ELIG-025` | De-duplication of portal failure message lines (`_dedupe_eligibility_portal_lines`). |
| **REQ-ELIG-026** | `SC-PG-001`  | `TC-ELIG-026` | Postgraduate CGPA evaluation against required CGPA or category override `minimum_cgpa_pg`. |
| **REQ-ELIG-027** | `SC-STATE-001`| `TC-ELIG-027` | Immutability of `self.program` state during program switch checks. |
| **REQ-ELIG-028** | `SC-CAT-003` | `TC-ELIG-028` | Derivation of Women reservation category for `gender == "Female"`. |
| **REQ-ELIG-029** | `SC-CAT-004` | `TC-ELIG-029` | Derivation of EWS, PWD, and Karnataka reservation categories. |
| **REQ-ELIG-030** | `SC-STAT-002`| `TC-ELIG-030` | Program level filtering in bulk exemption status updates (`Programme.level_of_study`). |
| **REQ-ELIG-031** | `SC-NTE-004` | `TC-ELIG-031` | Highest mark percentage rule selection when multiple National Test rules match. |
| **REQ-ELIG-032** | `SC-OP-001`  | `TC-ELIG-032` | Relational operators `=` (exact equality) and `<=` (less than or equal). |
| **REQ-ELIG-033** | `SC-STAT-003`| `TC-ELIG-033` | Single-exemption handling (Entrance Test Only vs Interview Only). |

---

## 3. Playbook Standardized Test Cases Matrix

### TC-ELIG-001: Rule Code Auto-Generation
- **Module:** Admission (`admission`) | **Feature:** Eligibility Rule
- **Scenario ID:** `SC-ER-001` | **Requirement ID:** `REQ-ELIG-001`
- **Priority:** P1 | **Severity:** Medium | **Test Type:** Positive / Functional
- **Test Objective:** Prove that inserting a new `Eligibility Rule` automatically generates a unique, sequential `rule_code` with format `ER-XXX`.
- **User / Role:** Eligibility Admin
- **Preconditions:** System has existing eligibility rules `ER-001` and `ER-002`.
- **Test Data:** `rule_name`: "B.Tech Science PCM Min 60%", `qualification_level`: "XII", `rule_type`: "Percentage", `operator`: ">=", `unit_type`: "Percentage", `required_percentage`: 60.0.
- **Steps:**
  1. Login as Eligibility Admin.
  2. Create a new `Eligibility Rule` document with the specified test data.
  3. Save the document.
- **Expected Result:** Document saves successfully with `rule_code` automatically populated as `ER-003`.

---

### TC-ELIG-002: Mandatory Fields Validation on Eligibility Rule
- **Module:** Admission (`admission`) | **Feature:** Eligibility Rule
- **Scenario ID:** `SC-ER-002` | **Requirement ID:** `REQ-ELIG-002`
- **Priority:** P2 | **Severity:** Medium | **Test Type:** Negative / Validation
- **Test Objective:** Verify that saving an `Eligibility Rule` without required fields is blocked.
- **User / Role:** Eligibility Admin
- **Preconditions:** None.
- **Test Data:** `rule_name`: "", `qualification_level`: "XII", `rule_type`: None.
- **Steps:**
  1. Instantiate a new `Eligibility Rule` omitting `rule_name` and `rule_type`.
  2. Attempt to save the document.
- **Expected Result:** System blocks save and raises `frappe.MandatoryError`.

---

### TC-ELIG-003: Unique Rule Name Enforcement
- **Module:** Admission (`admission`) | **Feature:** Eligibility Rule
- **Scenario ID:** `SC-ER-003` | **Requirement ID:** `REQ-ELIG-003`
- **Priority:** P2 | **Severity:** Medium | **Test Type:** Security / Integrity
- **Test Objective:** Ensure system blocks duplicate `rule_name` entries.
- **User / Role:** System Manager
- **Preconditions:** Existing `Eligibility Rule` named "UG CS CGPA Rule".
- **Test Data:** `rule_name`: "UG CS CGPA Rule".
- **Steps:**
  1. Create another `Eligibility Rule` using `rule_name = "UG CS CGPA Rule"`.
  2. Attempt to save.
- **Expected Result:** System throws `frappe.DuplicateEntryError` and aborts transaction.

---

### TC-ELIG-004: National Test Master Creation & Unique Exam Name
- **Module:** Admission (`admission`) | **Feature:** National Test
- **Scenario ID:** `SC-NT-001` | **Requirement ID:** `REQ-ELIG-004`
- **Priority:** P1 | **Severity:** Medium | **Test Type:** Positive & Negative
- **Test Objective:** Verify master entry creation for `National Test` and unique constraint enforcement.
- **User / Role:** Entrance Test Admin
- **Preconditions:** None.
- **Test Data:** `national_exam_name`: "JEE Main 2026".
- **Steps:**
  1. Insert `National Test` with `national_exam_name = "JEE Main 2026"`.
  2. Attempt to insert a second record with identical `national_exam_name`.
- **Expected Result:** First insert succeeds; second insert throws `frappe.DuplicateEntryError`.

---

### TC-ELIG-005: Exemption Code Auto-Generation on National Test Exemption Rule
- **Module:** Admission (`admission`) | **Feature:** National Test Exemption Rule
- **Scenario ID:** `SC-NTE-001` | **Requirement ID:** `REQ-ELIG-005`
- **Priority:** P1 | **Severity:** Medium | **Test Type:** Positive / Functional
- **Test Objective:** Verify auto-generation of `exemption_code` in format `{academic_year}-{campus}-TE-{seq}`.
- **User / Role:** Eligibility Admin
- **Preconditions:** Campus "Main Campus" and Academic Year "2026-2027" exist.
- **Test Data:** `exemption_name`: "JEE Top Rankers Exemption", `campus`: "Main Campus", `academic_year`: "2026-2027", `national_test`: "JEE Main 2026", `mark_percentage`: 85.0, `operator`: ">=", `applicable_program`: [{"degree_name": "B.Tech Computer Science"}].
- **Steps:**
  1. Create and save `National Test Exemption Rule` with test data.
- **Expected Result:** `exemption_code` is auto-generated as `2026-2027-Main Campus-TE-001`.

---

### TC-ELIG-006: Pre-requisite Check for Exemption Code Generation
- **Module:** Admission (`admission`) | **Feature:** National Test Exemption Rule
- **Scenario ID:** `SC-NTE-002` | **Requirement ID:** `REQ-ELIG-006`
- **Priority:** P2 | **Severity:** Low | **Test Type:** Negative / Validation
- **Test Objective:** Verify that saving an exemption rule without `campus` or `academic_year` raises validation error.
- **User / Role:** Eligibility Admin
- **Preconditions:** None.
- **Test Data:** `exemption_name`: "Invalid Exemption", `campus`: None, `academic_year`: None.
- **Steps:**
  1. Attempt to insert `National Test Exemption Rule` with missing `campus`.
- **Expected Result:** System throws `"Academic Year and Campus are required to generate Exemption Code."`.

---

### TC-ELIG-007: Inactive Rule Mapping Bypass
- **Module:** Admission (`admission`) | **Feature:** Eligibility Rule Mapping
- **Scenario ID:** `SC-ERM-001` | **Requirement ID:** `REQ-ELIG-007`
- **Priority:** P0 | **Severity:** High | **Test Type:** Functional / Negative
- **Test Objective:** Prove that if an `Eligibility Rule Mapping` has `is_active = 0`, the engine ignores it and evaluates applicant as Eligible.
- **User / Role:** System Manager
- **Preconditions:** Rule mapping configured with `required_percentage = 99.0%` but `is_active = 0`.
- **Test Data:** Applicant with `hsc_percentage = 50.0%`.
- **Steps:**
  1. Run `applicant.validate_eligibility()`.
- **Expected Result:** Engine skips inactive mapping. Applicant marked `evaluation_status = "Eligible"`.

---

### TC-ELIG-008: Applicant Type Filtering (Domestic vs International)
- **Module:** Admission (`admission`) | **Feature:** Eligibility Rule Mapping
- **Scenario ID:** `SC-ERM-002` | **Requirement ID:** `REQ-ELIG-008`
- **Priority:** P1 | **Severity:** High | **Test Type:** Functional / Logic
- **Test Objective:** Verify mapping evaluation respects `applicant_type` ("Domestic Applicants", "International Applicants", "Both").
- **User / Role:** Admission Officer
- **Preconditions:** Mapping 1 set to "International Applicants" (requires 90%); Mapping 2 set to "Domestic Applicants" (requires 50%).
- **Test Data:** Applicant with `foriegn_national = "No"` and `hsc_percentage = 55.0%`.
- **Steps:**
  1. Run `applicant.validate_eligibility()`.
- **Expected Result:** Applicant evaluated against Domestic Mapping (55% >= 50%) -> `evaluation_status = "Eligible"`. International mapping ignored.

---

### TC-ELIG-009: Single Category Reservation Override Threshold
- **Module:** Admission (`admission`) | **Feature:** Category Priority Engine
- **Scenario ID:** `SC-CAT-001` | **Requirement ID:** `REQ-ELIG-009`
- **Priority:** P0 | **Severity:** Critical | **Test Type:** Positive / Business Rule
- **Test Objective:** Prove that an applicant in a reservation category (e.g. OBC-NCL) passes using lower category threshold override.
- **User / Role:** Admission Officer
- **Preconditions:** Rule baseline = 60%; `Rule Mapping Category` for OBC-NCL = 50%.
- **Test Data:** Applicant with `whether_scstobc_ncl = "OBC-NCL"` and `hsc_percentage = 52.0%`.
- **Steps:**
  1. Run `applicant.validate_eligibility()`.
- **Expected Result:** Applicant evaluates against OBC-NCL override (52% >= 50%). `evaluation_status = "Eligible"`, `applied_category = "OBC-NCL"`.

---

### TC-ELIG-010: Multi-Category Priority Selection (`priority ASC`)
- **Module:** Admission (`admission`) | **Feature:** Category Priority Engine
- **Scenario ID:** `SC-CAT-002` | **Requirement ID:** `REQ-ELIG-010`
- **Priority:** P0 | **Severity:** Critical | **Test Type:** Functional / Logic
- **Test Objective:** Verify multi-category applicant evaluates category rows in strict priority order (Priority 1 before Priority 2).
- **User / Role:** Admission Officer
- **Preconditions:** Mapping has Priority 1 (SC: min 45%) and Priority 2 (PWD: min 40%).
- **Test Data:** Applicant with `whether_scstobc_ncl = "SC"` and `pwd = "Yes"`, `hsc_percentage = 46.0%`.
- **Steps:**
  1. Run `applicant.validate_eligibility()`.
- **Expected Result:** Engine evaluates Priority 1 (SC: 46% >= 45%) first -> `evaluation_status = "Eligible"`, `applied_category = "SC"`.

---

### TC-ELIG-011: National Test Exemption with Override
- **Module:** Admission (`admission`) | **Feature:** National Test Exemption
- **Scenario ID:** `SC-NTE-003` | **Requirement ID:** `REQ-ELIG-011`
- **Priority:** P0 | **Severity:** Critical | **Test Type:** Positive / Exemption
- **Test Objective:** Prove applicant with qualifying National Test score and `overrides_academic_rule = 1` is immediately marked Eligible.
- **User / Role:** Applicant / Admission Officer
- **Preconditions:** Exemption rule for JEE Main score >= 80% with `overrides_academic_rule = 1`, `exempts_entrance_test = 1`.
- **Test Data:** Applicant with failing HSC percentage (40.0% < 60.0%), but `national_test_name = "JEE Main 2026"` and `percentage = 85.0%`.
- **Steps:**
  1. Run `applicant.validate_eligibility()`.
- **Expected Result:** Applicant immediately marked `evaluation_status = "Eligible"`, academic rules bypassed, `exempts_entrance_test = 1`.

---

### TC-ELIG-012: Class XII Valid Data Pass (HSC & SSLC)
- **Module:** Admission (`admission`) | **Feature:** XII Academic Checks
- **Scenario ID:** `SC-XII-001` | **Requirement ID:** `REQ-ELIG-012`
- **Priority:** P0 | **Severity:** High | **Test Type:** Positive / Happy Path
- **Test Objective:** Validate applicant passing both HSC % and SSLC % requirements is marked Eligible.
- **User / Role:** Applicant
- **Preconditions:** Rule: HSC >= 60.0%, SSLC >= 50.0%.
- **Test Data:** `hsc_percentage`: 75.0%, `class_x_percentage`: 70.0%.
- **Steps:**
  1. Run `applicant.validate_eligibility()`.
- **Expected Result:** `evaluation_status = "Eligible"`, `rejected_reason = ""`.

---

### TC-ELIG-013: Class XII Invalid Data Failure (Failing HSC %)
- **Module:** Admission (`admission`) | **Feature:** XII Academic Checks
- **Scenario ID:** `SC-XII-002` | **Requirement ID:** `REQ-ELIG-013`
- **Priority:** P0 | **Severity:** High | **Test Type:** Negative / Validation
- **Test Objective:** Validate applicant with HSC % below required threshold is rejected.
- **User / Role:** Applicant
- **Preconditions:** Rule: HSC >= 60.0%.
- **Test Data:** `hsc_percentage`: 55.0%.
- **Steps:**
  1. Call `applicant.validate_eligibility()`.
- **Expected Result:** System raises `frappe.ValidationError`, `evaluation_status = "Ineligible"`, `rejected_reason` specifies 55.0% secured vs 60.0% required.

---

### TC-ELIG-014: Class XII Invalid Data Failure (Failing SSLC %)
- **Module:** Admission (`admission`) | **Feature:** XII Academic Checks
- **Scenario ID:** `SC-XII-003` | **Requirement ID:** `REQ-ELIG-014`
- **Priority:** P1 | **Severity:** High | **Test Type:** Negative / Validation
- **Test Objective:** Validate applicant passing HSC % but failing `sslc_percentage` requirement is rejected.
- **User / Role:** Applicant
- **Preconditions:** Rule: HSC >= 60.0%, SSLC >= 50.0%.
- **Test Data:** `hsc_percentage`: 75.0%, `class_x_percentage`: 45.0%.
- **Steps:**
  1. Call `applicant.validate_eligibility()`.
- **Expected Result:** System raises `frappe.ValidationError`, `evaluation_status = "Ineligible"`, `rejected_reason` specifies Class X shortfall.

---

### TC-ELIG-015: Boundary Value Testing (Exact vs Just Below)
- **Module:** Admission (`admission`) | **Feature:** Boundary Testing
- **Scenario ID:** `SC-XII-004` | **Requirement ID:** `REQ-ELIG-015`
- **Priority:** P1 | **Severity:** High | **Test Type:** Boundary Value Analysis
- **Test Objective:** Verify exact boundary value passes `>=` operator while 0.01% below fails.
- **User / Role:** QA Tester
- **Preconditions:** Rule: HSC >= 60.00%.
- **Test Data:** Case A: `hsc_percentage = 60.00%`; Case B: `hsc_percentage = 59.99%`.
- **Steps:**
  1. Test Case A: run `validate_eligibility()`.
  2. Test Case B: run `validate_eligibility()`.
- **Expected Result:** Case A is `Eligible`. Case B raises `frappe.ValidationError` and is marked `Ineligible`.

---

### TC-ELIG-016: HSC Stream Match and Mismatch Verification
- **Module:** Admission (`admission`) | **Feature:** HSC Stream Mapping
- **Scenario ID:** `SC-XII-005` | **Requirement ID:** `REQ-ELIG-016`
- **Priority:** P1 | **Severity:** High | **Test Type:** Positive & Negative
- **Test Objective:** Verify applicant's `hsc_group` is validated against allowed groups in `HSC Groups Mapping`.
- **User / Role:** Applicant
- **Preconditions:** Rule allowed groups: `["PCM", "PCMB"]`.
- **Test Data:** Case A: `hsc_group = "PCMB"`; Case B: `hsc_group = "Arts"`.
- **Steps:**
  1. Test Case A with valid marks.
  2. Test Case B with valid marks.
- **Expected Result:** Case A passes as `Eligible`. Case B is rejected as `Ineligible` (reason lists allowed vs studied streams).

---

### TC-ELIG-017: UG CGPA and Allowed Degree Validation
- **Module:** Admission (`admission`) | **Feature:** UG Academic Checks
- **Scenario ID:** `SC-UG-001` | **Requirement ID:** `REQ-ELIG-017`
- **Priority:** P0 | **Severity:** High | **Test Type:** Positive & Negative
- **Test Objective:** Verify UG qualification check validates both required CGPA and studied degree program in `Eligibility Allowed Degree`.
- **User / Role:** Applicant
- **Preconditions:** Rule for PG admission requires UG CGPA >= 6.5 and allowed degree `["B.Tech Computer Science"]`.
- **Test Data:** Case A: studied "B.Tech Computer Science" with CGPA 7.5; Case B: studied "B.A English" with CGPA 9.0.
- **Steps:**
  1. Run `validate_eligibility()` for Case A.
  2. Run `validate_eligibility()` for Case B.
- **Expected Result:** Case A is `Eligible`. Case B fails as `Ineligible` due to unallowed degree.

---

### TC-ELIG-018: Max CGPA Evaluation Across Multiple UG Degrees
- **Module:** Admission (`admission`) | **Feature:** UG Academic Checks
- **Scenario ID:** `SC-UG-002` | **Requirement ID:** `REQ-ELIG-018`
- **Priority:** P1 | **Severity:** Medium | **Test Type:** Functional / Multi-Row
- **Test Objective:** Verify engine evaluates max CGPA across multiple studied degree rows in `ug_degree_details`.
- **User / Role:** Applicant
- **Preconditions:** Rule requires UG CGPA >= 6.5 for "B.Tech Computer Science".
- **Test Data:** `ug_degree_details`: [Row 1: "B.Sc Physics", CGPA 6.0], [Row 2: "B.Tech Computer Science", CGPA 8.0].
- **Steps:**
  1. Run `validate_eligibility()`.
- **Expected Result:** Engine evaluates Row 2 max CGPA (8.0 >= 6.5) -> `evaluation_status = "Eligible"`.

---

### TC-ELIG-019: Pre-Throw Database Persistence on Ineligibility
- **Module:** Admission (`admission`) | **Feature:** Persistence & Fraud Prevention
- **Scenario ID:** `SC-EE-001` | **Requirement ID:** `REQ-ELIG-019`
- **Priority:** P0 | **Severity:** Critical | **Test Type:** Database / Data Integrity
- **Test Objective:** Confirm `Eligibility Evaluation` record is committed to database BEFORE `frappe.throw()` unwinds stack on failure.
- **User / Role:** QA / DB Inspector
- **Preconditions:** Ineligible applicant setup.
- **Test Data:** `hsc_percentage = 40.0%` (fails 60.0% rule).
- **Steps:**
  1. Execute `applicant.validate_eligibility()` inside a `try...except frappe.ValidationError:` block.
  2. Query database directly: `frappe.db.get_value("Eligibility Evaluation", {"applicant_name": applicant.name}, ["evaluation_status", "failure_message"])`.
- **Expected Result:** DB query returns existing record with `evaluation_status = "Ineligible"` and populated `failure_message`.

---

### TC-ELIG-020: Duplicate Evaluation Record Prevention (Upsert Check)
- **Module:** Admission (`admission`) | **Feature:** Persistence & Fraud Prevention
- **Scenario ID:** `SC-EE-002` | **Requirement ID:** `REQ-ELIG-020`
- **Priority:** P1 | **Severity:** High | **Test Type:** Data Integrity / Idempotency
- **Test Objective:** Ensure multiple calls to `validate_eligibility()` update the existing evaluation document rather than creating duplicate records.
- **User / Role:** System
- **Preconditions:** Applicant record created.
- **Test Data:** Run validation twice for same applicant.
- **Steps:**
  1. Call `applicant.validate_eligibility()` (Eligible).
  2. Modify applicant mark and call `applicant.validate_eligibility()` again.
  3. Count DB records: `frappe.db.count("Eligibility Evaluation", {"applicant_name": applicant.name})`.
- **Expected Result:** Count is exactly 1. Existing document is updated.

---

### TC-ELIG-021: Exemption Status Propagation to Applicant Status
- **Module:** Admission (`admission`) | **Feature:** Status Sync
- **Scenario ID:** `SC-STAT-001` | **Requirement ID:** `REQ-ELIG-021`
- **Priority:** P0 | **Severity:** High | **Test Type:** Integration / Batch Sync
- **Test Objective:** Verify `update_applicant_status_from_evaluations()` bulk updates `Applicant.status` for exempt candidates.
- **User / Role:** System / Admission Admin
- **Preconditions:** `Eligibility Evaluation` exists with `evaluation_status = "Eligible"`, `exempts_entrance_test = 1`, `exempts_interview = 1`.
- **Test Data:** `Applicant.status = "Submitted"`.
- **Steps:**
  1. Call `update_applicant_status_from_evaluations(campus, academic_year, admission_cycle, program_level="Undergraduate")`.
  2. Reload applicant.
- **Expected Result:** `Applicant.status` updated to "Excempted Entrance Test And Interview".

---

### TC-ELIG-022: Web Form Skip Throw Flag (`skip_eligibility_throw`)
- **Module:** Admission (`admission`) | **Feature:** Web Form Integration
- **Scenario ID:** `SC-WEB-001` | **Requirement ID:** `REQ-ELIG-022`
- **Priority:** P1 | **Severity:** High | **Test Type:** Web / API Integration
- **Test Objective:** Verify setting `applicant.flags.skip_eligibility_throw = True` persists ineligible status without raising exception.
- **User / Role:** Web Portal AJAX API
- **Preconditions:** Ineligible applicant data.
- **Test Data:** `applicant.flags.skip_eligibility_throw = True`.
- **Steps:**
  1. Call `applicant.validate_eligibility()`.
- **Expected Result:** Method completes gracefully without throwing exception. `evaluation_status` set to "Ineligible".

---

### TC-ELIG-023: Program Suggestion Payload Generation
- **Module:** Admission (`admission`) | **Feature:** Web Form Integration
- **Scenario ID:** `SC-WEB-002` | **Requirement ID:** `REQ-ELIG-023`
- **Priority:** P1 | **Severity:** Medium | **Test Type:** API / Web
- **Test Objective:** Verify `get_eligibility_suggestion_payload()` returns structured alternative programs passing eligibility.
- **User / Role:** Web Portal
- **Preconditions:** 3 active UG programs in cycle; applicant eligible for 2 of them.
- **Test Data:** Ineligible for primary program, eligible for secondary.
- **Steps:**
  1. Call `applicant.get_eligibility_suggestion_payload()`.
- **Expected Result:** Returns dict containing `programs` list with eligible programs, `eligible_count = 2`, `level = "Undergraduate"`.

---

### TC-ELIG-024: Zero/Missing Marks Handling
- **Module:** Admission (`admission`) | **Feature:** Null / Edge Case Handling
- **Scenario ID:** `SC-EDGE-001` | **Requirement ID:** `REQ-ELIG-024`
- **Priority:** P2 | **Severity:** Medium | **Test Type:** Null / Missing Data
- **Test Objective:** Verify handling when applicant mark is zero (`0.0`) or missing (`None`).
- **User / Role:** Applicant
- **Preconditions:** Rule: HSC >= 60.0%.
- **Test Data:** `hsc_percentage = 0.0`.
- **Steps:**
  1. Run `validate_eligibility()`.
- **Expected Result:** System catches zero mark, marks `Ineligible`, failure message states "marks were not found or are zero".

---

### TC-ELIG-025: Portal Failure Message Line De-duplication
- **Module:** Admission (`admission`) | **Feature:** Text Formatting & UX
- **Scenario ID:** `SC-TXT-001` | **Requirement ID:** `REQ-ELIG-025`
- **Priority:** P2 | **Severity:** Low | **Test Type:** Text / UX
- **Test Objective:** Verify `_dedupe_eligibility_portal_lines()` removes duplicate failure lines when multiple rules fail.
- **User / Role:** Web Portal
- **Preconditions:** Text with repeated lines.
- **Test Data:** `"Minimum required: 60%\nMinimum required: 60%\nYou secured: 50%"`.
- **Steps:**
  1. Pass text through `Applicant._dedupe_eligibility_portal_lines()`.
- **Expected Result:** Returns `"Minimum required: 60%\nYou secured: 50%"` without duplicated lines.

---

### TC-ELIG-026: Postgraduate CGPA and Category Override Validation
- **Module:** Admission (`admission`) | **Feature:** PG Academic Checks
- **Scenario ID:** `SC-PG-001` | **Requirement ID:** `REQ-ELIG-026`
- **Priority:** P0 | **Severity:** High | **Test Type:** Positive & Category
- **Test Objective:** Verify PG admission checks `pg_cgpa` against PG rule required CGPA or category override `minimum_cgpa_pg`.
- **User / Role:** Postgraduate Applicant
- **Preconditions:** Mapping has `minimum_cgpa_pg = 6.0` for SC category (vs General 7.0).
- **Test Data:** `pg_degree_details`: [{"pg_program": "M.Sc Physics", "pg_cgpa": 6.2}], `whether_scstobc_ncl`: "SC".
- **Steps:**
  1. Run `validate_eligibility()`.
- **Expected Result:** `evaluation_status = "Eligible"`, `applied_category = "SC"`.

---

### TC-ELIG-027: Immutability of Program State During Alternative Program Checks
- **Module:** Admission (`admission`) | **Feature:** State Safety
- **Scenario ID:** `SC-STATE-001` | **Requirement ID:** `REQ-ELIG-027`
- **Priority:** P1 | **Severity:** High | **Test Type:** State Integrity / Safety
- **Test Objective:** Ensure `_check_eligibility_for_program()` temporarily swaps `self.program` and restores original program in `finally` block.
- **User / Role:** System
- **Preconditions:** Original program = "B.Tech Computer Science".
- **Test Data:** Check eligibility for program = "B.Tech Electrical".
- **Steps:**
  1. Call `applicant._check_eligibility_for_program("B.Tech Electrical")`.
  2. Inspect `applicant.program`.
- **Expected Result:** `applicant.program` remains unchanged as "B.Tech Computer Science".

---

### TC-ELIG-028: Automatic Female Reservation Category Derivation ("Women")
- **Module:** Admission (`admission`) | **Feature:** Category Derivation
- **Scenario ID:** `SC-CAT-003` | **Requirement ID:** `REQ-ELIG-028`
- **Priority:** P1 | **Severity:** Medium | **Test Type:** Business Rule / Category
- **Test Objective:** Verify setting `gender = "Female"` automatically adds "Women" to derived applicant categories.
- **User / Role:** Female Applicant
- **Preconditions:** None.
- **Test Data:** `gender = "Female"`.
- **Steps:**
  1. Call `applicant._get_applicant_categories()`.
- **Expected Result:** Returned categories set contains `"Women"`.

---

### TC-ELIG-029: EWS, PWD, and Karnataka Reservation Category Derivations
- **Module:** Admission (`admission`) | **Feature:** Category Derivation
- **Scenario ID:** `SC-CAT-004` | **Requirement ID:** `REQ-ELIG-029`
- **Priority:** P1 | **Severity:** Medium | **Test Type:** Business Rule / Category
- **Test Objective:** Verify flags `ews = "Yes"`, `pwd = "Yes"`, `karnataka_category = "Yes"` derive `EWS`, `PWD`, and `Karnataka` categories.
- **User / Role:** Applicant
- **Preconditions:** None.
- **Test Data:** `ews = "Yes"`, `pwd = "Yes"`, `karnataka_category = "Yes"`.
- **Steps:**
  1. Call `applicant._get_applicant_categories()`.
- **Expected Result:** Returned set contains `EWS`, `PWD`, and `Karnataka`.

---

### TC-ELIG-030: Bulk Exemption Status Sync Program Level Restriction
- **Module:** Admission (`admission`) | **Feature:** Status Sync
- **Scenario ID:** `SC-STAT-002` | **Requirement ID:** `REQ-ELIG-030`
- **Priority:** P1 | **Severity:** Medium | **Test Type:** Integration / Filter
- **Test Objective:** Ensure `update_applicant_status_from_evaluations` restricts updates to applicants matching target `program_level`.
- **User / Role:** Admission Admin
- **Preconditions:** Eligible evaluation with exemptions exists for PG program.
- **Test Data:** Call status update with `program_level = "Undergraduate"`.
- **Steps:**
  1. Run `update_applicant_status_from_evaluations(campus, year, cycle, program_level="Undergraduate")`.
  2. Inspect PG applicant status.
- **Expected Result:** PG applicant status is NOT updated (only UG applicants updated).

---

### TC-ELIG-031: National Test Exemption Highest Cutoff Rule Selection
- **Module:** Admission (`admission`) | **Feature:** National Test Exemption
- **Scenario ID:** `SC-NTE-004` | **Requirement ID:** `REQ-ELIG-031`
- **Priority:** P1 | **Severity:** High | **Test Type:** Functional / Ordering
- **Test Objective:** Verify that when multiple National Test Exemption rules match, system selects the rule with highest `mark_percentage`.
- **User / Role:** Applicant
- **Preconditions:** Rule 1 (JEE Main >= 70%), Rule 2 (JEE Main >= 90% with `overrides_academic_rule = 1`).
- **Test Data:** Applicant score = 92.0%.
- **Steps:**
  1. Run `_evaluate_national_test_exemption()`.
- **Expected Result:** Rule 2 (90%) is selected due to `ORDER BY nter.mark_percentage DESC LIMIT 1`.

---

### TC-ELIG-032: Relational Operators `=` and `<=` Evaluation
- **Module:** Admission (`admission`) | **Feature:** Relational Operators
- **Scenario ID:** `SC-OP-001` | **Requirement ID:** `REQ-ELIG-032`
- **Priority:** P2 | **Severity:** Medium | **Test Type:** Boundary / Relational
- **Test Objective:** Verify comparison logic works accurately for `=` (exact) and `<=` (maximum threshold).
- **User / Role:** QA
- **Preconditions:** Rules with operators `=` and `<=`.
- **Test Data:** Case A: score 60.0 vs required 60.0 (`=`); Case B: score 65.0 vs max threshold 60.0 (`<=`).
- **Steps:**
  1. Run `_compare(60.0, 60.0, "=")`.
  2. Run `_compare(65.0, 60.0, "<=")`.
- **Expected Result:** Case A returns `True`; Case B returns `False`.

---

### TC-ELIG-033: Single-Exemption Status Resolution (Entrance Test Only vs Interview Only)
- **Module:** Admission (`admission`) | **Feature:** Status Resolution
- **Scenario ID:** `SC-STAT-003` | **Requirement ID:** `REQ-ELIG-033`
- **Priority:** P1 | **Severity:** Medium | **Test Type:** Functional / Logic
- **Test Objective:** Verify status resolution for single-exemption flags (Entrance Test Only vs Interview Only).
- **User / Role:** System
- **Preconditions:** Evaluation 1 (`exempts_entrance_test=1, exempts_interview=0`), Evaluation 2 (`exempts_entrance_test=0, exempts_interview=1`).
- **Test Data:** Run status update helper.
- **Steps:**
  1. Execute `update_applicant_status_from_evaluations()`.
- **Expected Result:** Evaluation 1 updates status to "Entrance Test Exempted"; Evaluation 2 updates status to "Interview Excempted".

---

## 4. Execution & Verification Command
Execute unit tests using the Frappe test runner command:
```bash
bench --site <site_name> run-tests --module slcm.tests.eligiblity.test_eligibility
```

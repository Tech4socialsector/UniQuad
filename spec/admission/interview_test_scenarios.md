# Interview Module — Test Scenarios & Specifications

This document defines the comprehensive test scenario specifications for the **Interview System** in the SLCM Admission Module.

---

## Scenario Overview

| Test ID | Module | Feature | Short Title |
| :--- | :--- | :--- | :--- |
| **TC-INT-001** | Configuration | Ratio Validation | Valid Ratio Format Parsing (`3` or `1:3`) |
| **TC-INT-002** | Configuration | Ratio Validation | Invalid Ratio Format Rejection |
| **TC-INT-003** | Configuration | Auto Code | Configuration Code Auto-Generation |
| **TC-INT-004** | Candidate Pool | Source Extraction | Source 1: Direct National Test Exemption |
| **TC-INT-005** | Candidate Pool | Source Extraction | Source 2: Entrance Test Passers |
| **TC-INT-006** | Candidate Pool | Source Extraction | Source 3: Direct Academic Eligibility |
| **TC-INT-007** | Candidate Pool | Filtering | Exclusion of Already Scheduled Applicants |
| **TC-INT-008** | Candidate Pool | Filtering | Exclusion of Rejected Applicants |
| **TC-INT-009** | Candidate Pool | Stage Flags | Domestic vs International Stage Flag Filter |
| **TC-INT-010** | Seat Allocation | Quota Lookup | Domestic Applicant Quota Lookup |
| **TC-INT-011** | Seat Allocation | Quota Lookup | International Applicant Quota Lookup |
| **TC-INT-012** | Seat Allocation | Quota Lookup | Combined Both Applicants Quota Lookup |
| **TC-INT-013** | Selection Engine | Ratio Multiplier | Selection Multiplier Quota Calculation |
| **TC-INT-014** | Selection Engine | Exemption Bypass | Fetch Exempted Applicants Bypass Flag |
| **TC-INT-015** | Selection Engine | Rank Sorting | Cumulative Rank Ascending Sort |
| **TC-INT-016** | Selection Engine | Tie Breaking | Cutoff Boundary Equal Rank Tie-Breaking |
| **TC-INT-017** | List Generation | Failure Handling | Zero Candidate Exception & Failure Status |
| **TC-INT-018** | Interview List | Naming Sequence | Interview List Auto Naming (`IVL-2026-001`) |
| **TC-INT-019** | Interview List | Gap Filling | Naming Sequence Gap Filling for Deleted Lists |
| **TC-INT-020** | Slot Allocation | Staff Validation | Inactive Staff Member Assignment Block |
| **TC-INT-021** | Slot Allocation | Overlap Prevention | Panel Double-Booking Overlap Prevention |
| **TC-INT-022** | Slot Allocation | Stage Validation | Program Stage Interview Enabled Check |
| **TC-INT-023** | Slot Allocation | Record Creation | Interview Seat Allocation Record Generation |
| **TC-INT-024** | Slot Allocation | Category Sync | Candidate Category Resolution Sync |
| **TC-INT-025** | Status Sync | Status Propagation | Applicant Status Propagation to 'Interview Scheduled' |

---

## Detailed Scenario Breakdown

### MODULE 1: RATIO VALIDATION & AUTO CODE
- **TC-INT-001**: Validates ratio formats like `3` or `1:3` pass regex validation.
- **TC-INT-002**: Invalid ratio formats like `-1`, `0:0`, `abc` throw validation errors.
- **TC-INT-003**: System auto-generates 8-character upper hash code before saving.

### MODULE 2: CANDIDATE POOL EXTRACTION
- **TC-INT-004**: Extracts applicants with National Test Exemption (`exempts_entrance_test=1`, `exempts_interview=0`).
- **TC-INT-005**: Extracts Entrance Test passers (`result_status='Pass'`, `part_b_total_marks_scored > 0`).
- **TC-INT-006**: Extracts Direct Academic candidates (`entrance_test=0`, `exempts_interview=0`).
- **TC-INT-007**: Ensures candidates already present in an `Interview List` are excluded.
- **TC-INT-008**: Ensures candidates with status `'Rejected'` are excluded.
- **TC-INT-009**: Differentiates domestic (`intereview=1`) and international (`international_interview=1`) stage requirements.

### MODULE 3: SEAT QUOTA & RATIO CALCULATION
- **TC-INT-010**: Fetches domestic total seats from active `Programme Reservation Policy`.
- **TC-INT-011**: Fetches international total seats from policy.
- **TC-INT-012**: Sums domestic and international seats for `applicant_type = "Both"`.
- **TC-INT-013**: Applies ratio multiplier formula `ceil(seats * multiplier)`.
- **TC-INT-014**: Bypasses multiplier logic when `fetch_exempted_applicant = 1`.

### MODULE 4: RANK SORTING & TIE-BREAKING
- **TC-INT-015**: Sorts candidate pool by `cumulative_rank` in ascending order.
- **TC-INT-016**: Includes all candidates sharing the exact same rank at the cutoff boundary.

### MODULE 5: LIST GENERATION & NAMING
- **TC-INT-017**: Throws structured "No Candidates Found" error and sets status to "Failed" when candidate pool is empty.
- **TC-INT-018**: Generates `Interview List` with naming sequence `IVL-{academic_year}-001`.
- **TC-INT-019**: Reuses deleted sequence numbers (gap-filling strategy).

### MODULE 6: SLOT ALLOCATION & PANEL SAFETY
- **TC-INT-020**: Rejects slot allocation if selected interviewer is inactive (`is_active = 0`).
- **TC-INT-021**: Prevents double-booking the same interviewer on identical date and time.
- **TC-INT-022**: Verifies program has `intereview = 1` enabled before allocating slot.
- **TC-INT-023**: Creates individual `Interview Seat Allocation` documents with `interview_status = 'Scheduled'`.
- **TC-INT-024**: Automatically populates candidate categories (`_get_applicant_categories()`).
- **TC-INT-025**: Updates `Applicant` document status to `'Interview Scheduled'`.

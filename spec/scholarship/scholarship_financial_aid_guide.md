# Scholarship and University Financial Aid: User Guide

**Applies to:** Uniquad (SLCM v16), scholarship and financial-aid records as on disk, 26 November 2026
**Who this is for:** Scholarship Admin and Admission staff who run admission-stage scholarships, and Finance staff (Campus Admin, Accounts) who record University Financial Aid and apply it to students' dues.
**Where:** Desk → **Scholarship** sidebar (module Admission). Aid applied to dues is done in **Fees Management** (see spec/fee_management).

---

## 1. The flow at a glance

There are two separate tracks. They do not feed each other automatically.

```
A. Admission-stage scholarship (applicants)
   1. Admission Cycle: Enable Scholarship, Max Schemes Per Applicant
   2. Scholarship Scheme        (who, how much, budget, when)
   3. Scholarship Application   (applicant applies on /nlsat/scholarships, or staff create on desk)
   4. Approve                   → benefit calculated → scheme budget used
                                → Applicant Fee Assignment (Admission Fee) scholarship + final payable updated
                                → email "Scholarship Updates"; Scholarship Audit Log row on every change

B. Campus students (after enrolment)
   1. University Financial Aid  (one record per student per academic year: tier + T/R/S/... amounts)
   2. Apply to dues by hand     → Fee Concession (type "University Financial Aid") on each Fee Demand
                                → Stipend Payment for the stipend part
   3. Shown in                  → Fees Dashboard "Concessions & aid", fee certificates ("Less: University Scholarship")
```

### Key ideas

| Term | Meaning |
|---|---|
| **Scholarship Scheme** | A scholarship offered in one admission cycle and campus, e.g. a need-based 50% tuition scheme. Named `SS-{cycle}-{scheme code}`. |
| **Scholarship Application** | One applicant's request for one scheme. Named `SA-{cycle}-#####`. |
| **Benefit** | The rupee amount the scheme gives this applicant (*Calculated Benefit*). |
| **Applicant Fee Assignment** (AFA) | The admission-stage fee bill (`AFA-YYYY-#####`). Approved scholarships reduce its *Final Payable Amount*. |
| **University Financial Aid** (UFA) | The finance office's yearly aid allocation for an enrolled student, copied from the FA allocation sheet. Named `UFA-YYYY-#####`. |
| **Fee Concession** | The record that actually takes a waiver off a student's Fee Demand. |

---

## 2. Admission Cycle settings

*Admission Cycle* form:

| Field | Effect |
|---|---|
| Enable Scholarship | Off → every Scholarship Application in this cycle is refused ("Scholarships are not enabled for this admission cycle") |
| Max Scholarship Schemes Per Applicant | 0 = no limit. Otherwise an applicant cannot have more Approved applications than this in the cycle. |

---

## 3. Scholarship Scheme

*Scholarship → Scholarship Scheme* (System Manager, Scholarship Admin, Campus Admin; Applicant can read)

| Field | What to enter |
|---|---|
| Scheme Name, Scheme Code | Code is part of the record name |
| Admission Cycle, Campus | Required. The scheme applies only to this cycle and campus. |
| Programme Level, Programme, Category | Optional limits. Blank = any. |
| Scholarship For | Domestic / International (International = applicant marked foreign national) |
| Scheme Type | Need / Merit / Government / Institutional |
| Min / Max Income | Required for **Need** schemes. Max ≥ Min. |
| Minimum merit score | Required for **Merit** schemes, 0–100 |
| Income Certificate Required | With Need type: family income must fall within Min–Max |
| Apply On | Total Fee / Tuition Only |
| Coverage Type, Coverage Value | Percentage (≤ 100) or Fixed amount. Not negative. |
| Maximum amount | Cap on the benefit |
| Component-wise Coverage (table) | Fee component, Percentage / Fixed, value, cap, applicable, sequence (see Q2) |
| Total Budget, Maximum Beneficiaries | Limits. *Utilized Budget* and *Current Beneficiaries* are kept by the system. |
| Stage Availability | Anytime / Post-Selection / Post-Offer |
| Application Start / End | Start cannot be in the past; End ≥ Start |
| Status | Draft / Active / Archived |

**What the system does**
- Approving an application adds its benefit to *Utilized Budget* and 1 to *Current Beneficiaries*. Reversing takes them off.
- When beneficiaries or budget reach the limit, the scheme becomes **Archived**. When a reversal brings it back under both limits, it becomes **Active** again.
- **Sync Budget** button: recounts beneficiaries and budget from Approved applications and fixes the status.

---

## 4. Scholarship Application

*Scholarship → Scholarship Application* (System Manager, Scholarship Admin, Campus Admin, Applicant). Kanban board *Scholarship View* groups by status.

### 4.1 How applicants apply
Applicant portal **/nlsat/scholarships** lists the schemes the applicant can apply for and the ones already applied. **/nlsat/scholarships/apply** submits an application with annual family income and an income certificate (PDF / JPG / PNG, up to 5 MB) and optional supporting documents. Old `/merit-and-scholarship/...` and `/apply` links redirect here.

### 4.2 Fields

| Field | Notes |
|---|---|
| Applicant, Candidate name | Required |
| Admission Cycle, Campus, Programme, Scholarship Scheme | Required |
| Academic Year | Filled from the cycle's admission year |
| Family Income, Income Certificate | Always required |
| Original Fee Amount | Total payable from the programme's Fee Structure in the cycle's Offer Configuration (Indian or foreign) |
| Calculated Benefit, Final Fee Amount | Calculated (below) |
| Status | Submitted / Approved / Rejected / Revoked |
| Reviewed By, Approval Date | Filled on approval. Approval date cannot be in the future. |
| Rejection Reason | Required when Rejected |

### 4.3 Rules the system enforces (on every save)

| Check | Error when it fails |
|---|---|
| Cycle has Enable Scholarship | "Scholarships are not enabled for this admission cycle." |
| No other live (not Rejected / Revoked) application for the same scheme | "You have already applied for this scholarship." |
| Scheme's cycle and campus match | "Scholarship is not applicable for selected admission cycle or campus." |
| Scheme's programme / category match (category from the applicant's categories) | "Scholarship not applicable for selected program/category." |
| Domestic / International match | "only available for {0} applicants" |
| Need + income certificate required: income within Min–Max | "exceeds the maximum" / "is below the minimum" |
| Merit: score ≥ minimum (Merit List total score, else entrance test marks) | "Your merit score … is below the required minimum". No score found → orange warning only. |
| Scheme Active; stage reached (Post-Selection / Post-Offer, from applicant status and offer letter); today inside the application window; beneficiaries and budget not reached | "not active" / "available only after selection" / "only after offer issuance" / "not started" / "closed" / "limit reached" / "budget exhausted" |
| Approved count < Max Schemes Per Applicant | "Limit Reached …" |
| No Admission Fee assignment already Paid / Converted | "Scholarship applications are not permitted once the admission fee has been paid." |

The stage, window and limit checks are skipped when rejecting or revoking, and when an already Approved application is saved again.

### 4.4 How the benefit is calculated

```
base     = Original Fee Amount              (Apply On = Total Fee)
         = Tuition component of the structure (Apply On = Tuition Only)
benefit  = base × Coverage Value %          (Percentage)
         = Coverage Value                   (Fixed)
benefit  = min(benefit, Maximum amount, Original Fee Amount)
Final Fee Amount = Original Fee Amount − benefit
```

### 4.5 What happens when the status changes

| Change | Effect |
|---|---|
| → **Approved** | Scheme budget and count go up. AFA updated. Email sent. |
| → **Rejected** | Email sent. |
| Approved → anything else, or Approved record deleted | Scheme budget and count go down. AFA recalculated without it. |
| Approved, benefit changed | Scheme budget adjusted by the difference. AFA recalculated. |

**Applicant Fee Assignment update:** the applicant's AFA with fee type **Admission Fee** in the same cycle gets
- *Scholarship Amount* = sum of all Approved benefits for the applicant in the cycle, capped at the AFA total,
- *Scholarship Applied* = ticked when > 0,
- *Final Payable Amount* = total − scholarship (not below 0).

If no Admission Fee AFA exists yet, nothing is updated.

**Email:** Email Template **Scholarship Updates** (created automatically if missing).

---

## 5. Scholarship Audit Log

*Scholarship → Scholarship Audit Log* (System Manager, Scholarship Admin, Admission Admin)

One row every time an application is saved: action (Apply / Approve / Reject / Revoke / Modify), previous and new state (JSON), performed by, triggered by (Applicant / Admin / System), time, reason, IP address and a SHA-256 **record hash** for tamper detection. Named from the admission cycle's code.

---

## 6. Scholarship Utilization Report

*Scholarship → Scholarship Utilization Report* (script report on Scholarship Application)

Approved applications grouped by Admission Cycle, Campus, Programme and Scheme: **Total Beneficiaries** and **Total Scholarship Utilized** (sum of calculated benefit). Filters: cycle, campus, programme, scheme.

---

## 7. University Financial Aid

*Scholarship → University Financial Aid*, also *Fees Management → Concessions, excess & refunds* (System Manager, Campus Admin)

Mirrors the finance office's *University Financial Aid Allocation* sheet.

| Field | Notes |
|---|---|
| Academic Year, Student | Required |
| Registration ID / Student ID No., Name, Email, Gender, Programme | Fetched from Student Master (official email, programme of study) |
| Category | General, OBC, SC, ST, EWS, PWD and the "& PWD" combinations |
| Year | 1st-year … 5th-year |
| Aid Given (FA Tier) | T1, T2, T3, T4, LI+S, Stipened (sic), LI, TRS |
| T (Tuition & Facilities), R (Hostel & Mess), Lunch / Dinner Charges, S (Stipend), Laptop, Loan Interest | Amounts |
| Total Financial Aid Awarded | Sum of the six amounts (on the form and on save) |
| Status of Acceptance | Pending / Accepted / Rejected |
| Remarks | |

**Rule:** one record per student per academic year ("Financial Aid for … already exists").

**What it does not do:** saving a UFA does **not** change any Fee Demand. It is the allocation record only (see Q1).

### 7.1 Importing the allocation sheet
Use Data Import. Clean the sheet first: genders must match the Genders records, status values must not carry trailing spaces ("Accepted "), programme names must match Programme records, and students must be matched to Student Master.

---

## 8. Applying aid to a student's dues

| Aid part | How it reaches the dues |
|---|---|
| Tuition / hostel waiver | **Fee Concession** on each Fee Demand, Concession Type *University Financial Aid* (or *MMVY Scholarship*, *Aditya Birla Schoalrship* (sic)). Waiver Value = rupee amount. From Student Fee Management → **Apply Scholarship**, the Fee Concession form, the list's bulk apply, or the *Concession Bulk Upload* sheet. |
| Stipend | **Stipend Payment** (type *University Financial*), from Student Fee Management → Record Stipend Payment |
| Aid already paid by the student, or credited in advance | **Student Credit Note**, credit type *Scholarship Credit*, then adjusted against dues |

Concession rules (from the fee module): waiver > 0, ≤ original amount and ≤ the unpaid balance, one Approved concession per due, due not Paid / Cancelled. Full waiver with nothing paid → due **Waived**. Cancelling the concession removes the waiver.

---

## 9. Student Master scholarship fields

These sit on Student Master and are older than UFA.

| Field | Used by |
|---|---|
| Applying for Scholarship (Yes / No), Scholarship Type (Cultural / Merit / Need-Based / Other / Sports), Scholarship Amount, Scholarship Percentage, Date of Approval | The legacy Student Master fee sync: *Scholarship Amount* (discount) and *Net Program Fee* are worked out from these when the student's Fee Structure changes. Not used by Fee Demands. |
| Whether Student is Scholarship beneficiary? (Yes / No), If yes (University Financial Aid / External Scholarship / Both), If External Scholarship or both (table of *External Scholarship or Both Scholarship*) | Information only. The *External Scholarship or Both Scholarship* master has no fields besides its name. |

---

## 10. Where scholarships and aid show up

| Place | What it shows |
|---|---|
| Fees Dashboard → Concessions & aid | Concessions approved / in draft, University Financial Aid (total allocated, by tier / programme / year / category), Stipends paid |
| Uniquad Dashboard | A UFA card |
| Fee certificates | With *Has University Scholarship* ticked: "Less: University Scholarship" (the dues' waivers) and "Net Fee payable". Admission-stage certificates take the scholarship from the AFA. |
| Student / parent portal | Waiver on each due (net payable) |

---

## 11. Scholarship sidebar

`slcm/workspace_sidebar/scholarship.json` (module Admission):

| Link | Type |
|---|---|
| Scholarship Scheme | DocType |
| Scholarship Application | DocType |
| University Financial Aid | DocType |
| Applicant Fee Assignment | DocType |
| Scholarship Utilization Report | Report |
| Scholarship Audit Log | DocType |

---

## 12. Roles

| DocType / report | Roles (DocType JSON) |
|---|---|
| Scholarship Scheme, Scholarship Application | System Manager, Scholarship Admin, Campus Admin, Applicant |
| Scholarship Audit Log | System Manager, Scholarship Admin, Admission Admin |
| Applicant Fee Assignment | System Manager, Admission Admin, Admission Officer, Campus Admin, Offer Letter Admin |
| University Financial Aid | System Manager, Campus Admin |
| Fee Concession | System Manager, Campus Admin |
| Stipend Payment | System Manager, Accounts Manager, Campus Admin, AAD, AAD Staff, Student |

Applicant access to applications is limited to their own by `slcm.security.applicant_access.scholarship_application_query`.

---

## 13. Open questions

| # | Question |
|---|---|
| Q1 | **UFA → dues.** A University Financial Aid record does not create Fee Concessions or Stipend Payments. Finance applies each part by hand. Should approving / accepting a UFA raise the concessions (T on tuition dues, R on hostel dues) and the stipend automatically? |
| Q2 | **Component-wise coverage is unreachable.** The engine uses the coverage-rules table only when Coverage Type or Apply On is "Component-wise", but neither field offers that option (Percentage / Fixed; Total Fee / Tuition Only). Add the option, or drop the table? |
| Q3 | **Submit / cancel code is dead.** Scholarship Application is not submittable, so its `on_submit` / `on_cancel` never run, and the hidden `workflow_state` field has no Workflow shipped in fixtures. Is an approval workflow intended? |
| Q4 | **Past start date blocks edits.** A scheme whose Application Start is in the past can no longer be saved ("cannot be in the past"), even to change its status or budget. Intended? |
| Q5 | **Two scholarship models for students.** Student Master scholarship fields (amount / percentage) and UFA + Fee Concession both exist. Which is the source of truth for enrolled students? |
| Q6 | **AFA scope.** Only the *Admission Fee* AFA is reduced. Confirmation Fee and Course Fee assignments are not. Confirm. |
| Q7 | **Typos in option values** ("Stipened" FA tier, "Aditya Birla Schoalrship" concession type). Fixing them changes stored values; agree a patch before changing. |
| Q8 | **Category lists differ.** UFA categories (incl. PWD combinations) do not match Fee Structure / Fee Notification categories (General, SC, ST, OBC, OBC-NCL, EWS, NRI, NA, Other). Should they be unified? |
| Q9 | **Need schemes without "Income Certificate Required"** skip the income range check, although Min / Max Income are mandatory for Need schemes. Intended? |

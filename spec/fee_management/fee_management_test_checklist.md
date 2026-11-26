# Fee Management: QA Test Checklist

**Applies to:** Uniquad (SLCM v16), student fee module as on disk, 26 November 2026
**Who this is for:** QA and Finance staff testing the fee flows on a test site (slcm.local or UAT).
**Where:** Desk → **Fees Management**; student portal `/student-portal/fees`; parent portal `/parent-portal/fees`. Companion to `fee_management_guide.md` (section numbers in brackets).

---

## 1. Before you start

```
1. Fee Components exist for every type used (Tuition and Facilities Fee, Examination Fee, Fine - Hostel, ...)
2. One Active Programme with an Enrolled Student Enrollment for each test student
3. Test students: Active; Current Year set (1, 2 ...); Quota set; one Indian, one foreign nationality; one SC
4. Razorpay test keys (and Easebuzz test keys, enabled) in settings; webhook secret set
5. Student Portal Settings → Reminders: real SMTP OFF or test mailbox only (reminders email students)
6. A parent user linked to one test student
```

Tick each row. "Expected" is what the code on disk does.

---

## 2. Fee Structure [2.2]

| # | Scenario | Expected |
|---|---|---|
| FS-1 | Save a structure with Indian rows 1,00,000 (tax 0) and 10,000 (tax 18%) | Row totals 1,00,000 and 11,800; Total for Indian 1,11,800 |
| FS-2 | Valid From after Valid Until | Error "Valid From date cannot be after Valid Until date" |
| FS-3 | Second Active structure, same programme / AY / year / category / applicable / round / gateway, overlapping dates | Error naming the existing structure |
| FS-4 | Same as FS-3 but category SC | Saves (different category) |
| FS-5 | Same as FS-3 but category "All" when the first is blank | Error (blank = All) |
| FS-6 | Set Inactive a structure used in an Offer Configuration | Error "Cannot set status to 'Inactive'…" |
| FS-7 | Change total of an Active Student structure | Blue alert "updated in the background"; Student Master Fee Structure / totals of that programme's students refresh; Fee Structure History row added |

## 3. Fee Notification and generation [3.1]

| # | Scenario | Expected |
|---|---|---|
| FN-1 | Effective From before Issued Date | Error |
| FN-2 | Two identical component rows | Error "Duplicate entry for Fee Component…" |
| FN-3 | Generate Demands while Draft | Error "Please publish…" |
| FN-4 | Publish with no rows | Error "add at least one fee component" |
| FN-5 | Publish, Generate (Programme X, year 1, All) | Background job; Fee Demand Generation Log Completed; one Fee Demand per active year-1 student of X; amount = structure total of that component; due = Effective From + Due Offset Days |
| FN-6 | Foreign student in FN-5 | Amount from the foreign table; Indian table if the structure has no foreign rows |
| FN-7 | Rows SC + All for the same component | SC students get the SC amount; the All row logs them "covered by a SC row" |
| FN-8 | Run Generate again | No new dues; log rows "Demand already exists" |
| FN-9 | Component not in any structure, Fallback Amount 5,000 | Dues of 5,000 |
| FN-10 | Component not in any structure, no fallback | Skipped "No Fee Structure lists …" |
| FN-11 | One-Time structure, year-2 student | Skipped "One-time fee — not Year 1 student" |
| FN-12 | Row for a Hostel Fee component | Skipped "handled by hostel allocation" |
| FN-13 | Row filtered to a batch with no students | Nothing raised for that row |
| FN-14 | Inactive (Student Status ≠ Active) student | Not charged |

## 4. Fee Demand rules [4]

| # | Scenario | Expected |
|---|---|---|
| FD-1 | Create a due: original 50,000, waiver 5,000, penalty 1,000 | Net Payable 46,000; Outstanding 46,000; Pending |
| FD-2 | Waiver > original | Error |
| FD-3 | Second Tuition due for the same student + AY | Error "Duplicate Fee Demand … once per Academic Year" |
| FD-4 | FD-3 after cancelling the first | Saves |
| FD-5 | Two Examination Fee dues same AY | Both save (not a once-per-year group) |
| FD-6 | Edit a Cancelled due | Error "is cancelled and can no longer be edited" |
| FD-7 | Cancel Demand on a part-paid due | Error "reverse the payment first" |
| FD-8 | New due: Programme and Batch filled from the student's enrollment | `program` and Batch set |
| FD-9 | Due date in the past, nothing paid, save | Status Overdue |
| FD-10 | Run `mark_overdue_demands` | Pending / Partially Paid past-due dues → Overdue |
| FD-11 | Student logs into desk and lists Fee Demand | Sees only own dues |

## 5. Event dues [3.3]

| # | Scenario | Expected |
|---|---|---|
| EV-1 | Re Exam Registration (Registered, fee 500) | Examination Fee due 500, source = the registration |
| EV-2 | Delete that registration (unpaid) | Due Cancelled |
| EV-3 | Pay the re-exam on its own page | Registration Paid; enrolment due Cancelled |
| EV-4 | Hostel Fine inserted | Fine - Hostel due, 15 days |
| EV-5 | Pay the hostel-fine due | Hostel Fine status Paid; cancel the payment → Unpaid |
| EV-6 | Submit / cancel Discipline Order, Deferral Order, Revaluation Request, Course Reregistration | Due raised / cancelled |
| EV-7 | Cancel a trigger whose due is part-paid | Due stays; Error Log "partial payment exists" |
| EV-8 | Component type missing (e.g. no Gap Year Fee) | No due; Error Log |
| EV-9 | Hostel Allocation inserted | Check Error Log / failure (open question Q1) |
| EV-10 | Run `check_phd_year_transition` for a year-2 PhD student | One Annual Fee (PhD) due; second run adds nothing |

## 6. Offline payments [5.1–5.3]

| # | Scenario | Expected |
|---|---|---|
| OP-1 | SFM → Record Payment 46,000 on FD-1, Bank Transfer, UTR, bank, dates, remarks ≥ 15 chars | Fee Payment submitted; Fee Receipt created; due Paid; last payment details on the due |
| OP-2 | Remarks of 10 characters | Error "must be at least 15 characters" |
| OP-3 | Mode = Online Payment | Error "Online payments are recorded by the payment gateway" |
| OP-4 | Settlement Date before Payment Date | Error |
| OP-5 | Reuse the UTR of OP-1 | Error "Duplicate UTR" |
| OP-6 | Allocate more than a due's outstanding | Error "exceeds outstanding amount" |
| OP-7 | Allocations ≠ amount | Error "Total allocated amount … must equal" |
| OP-8 | Fee Payment with Voucher Number and another due in the table | Error "Use either the Voucher Number … or the table" |
| OP-9 | Part payment 20,000 on a 46,000 due | Partially Paid, outstanding 26,000 |
| OP-10 | Edit Payment (OP-9) to 25,000 | Original cancelled; `FP-…-1` submitted; due outstanding 21,000 |
| OP-11 | Delete Payment | Cancelled; due re-opened; receipt Cancelled |
| OP-12 | Print receipt from SFM | PDF of Fee Payment Receipt - Admin Copy |
| OP-13 | Bulk Fee Collection: fetch, process | One Fee Payment + Receipt per student; rows Processed / Skipped; status Completed |
| OP-14 | Fee Demand list → Mark dues cleared | One submitted Fee Payment per student; dues Paid; already-paid dues listed as skipped |
| OP-15 | Re Exam Registration → Mark as Paid (Cash, today) | Payment Log Paid; registration Paid; future date refused |

## 7. Online payments [5.5–5.8]

| # | Scenario | Expected |
|---|---|---|
| ON-1 | Student pays one Razorpay due (test card) | Fee Payment (Online Payment, gateway Razorpay, reference = pay_ id); receipt; due Paid; one SLCM Payment Request Paid |
| ON-2 | Pay All with Razorpay + Easebuzz components | Response "split"; one checkout per gateway |
| ON-3 | Easebuzz due, payer has no mobile | Refused before checkout |
| ON-4 | Easebuzz due paid | Return page shows result; Fee Payment recorded once even if webhook and return both arrive |
| ON-5 | Gateway not configured | Error "Online payment through … is not set up yet" |
| ON-6 | Student starts checkout; parent tries the same dues within 20 min | Parent refused "A payment for these fees was started by the student…" |
| ON-7 | Student retries own checkout | Allowed |
| ON-8 | Try to pay an exam-fee demand from Fees page | Error "paid on the Re-Exam / Results page" |
| ON-9 | Close the Razorpay window | Payment Cancelled log; due unchanged |
| ON-10 | Failed card | Payment Failed log; Failed SLCM Payment Request with reason; Failed Payment Report row |
| ON-11 | Pay, then block the browser confirm (close tab after capture) | Within ~15 min the reconciler records the Fee Payment |
| ON-12 | Same dues paid twice (two tabs, guard bypassed) | Second capture → unapplied Payment Request; Error Log "needs refund"; listed in Payments to Refund |
| ON-13 | Payments to Refund → Record refund more than unapplied | Error "Only ₹… is unapplied" |
| ON-14 | Record refund with a used reference | Error "already recorded" |
| ON-15 | Cancel an online Fee Payment | Dues re-open; orange warning "Money still with the gateway"; comment added |
| ON-16 | Webhook without / with wrong signature | Rejected (PermissionError) |
| ON-17 | Run `daily_sync_settlements` / Easebuzz `daily_sync` after a settlement | Settlement id, UTR, fees, tax, net filled; Payment Settlement Report shows it |
| ON-18 | Parent pays a ward's due | Same as ON-1; parent cannot pay another student's due |

## 8. Concessions, fines, excess, refunds, stipends [6]

| # | Scenario | Expected |
|---|---|---|
| CN-1 | Apply Scholarship 10,000 on a 50,000 unpaid due | Concession submitted; due waiver 10,000, outstanding 40,000 |
| CN-2 | Second concession on the same due | Error "already has an approved concession" |
| CN-3 | Concession larger than unpaid balance | Error |
| CN-4 | Concession equal to the whole due, nothing paid | Due Waived |
| CN-5 | Cancel the concession | Waiver 0; due Pending |
| FI-1 | Fine Imposition 2%, max 5,000; Preview; Apply | Penalty added to each matching open due; log rows; status Applied |
| FI-2 | Apply again | Error "already been applied" |
| FI-3 | Reverse | Penalties removed; status Reversed |
| FI-4 | Dues of a "Fine - …" component | Never fined |
| EX-1 | Add Credit Note Overpayment without Received Via | Error "Received Via is required" |
| EX-2 | Adjust from Excess 5,000 to an open due | Due credit adjusted 5,000; credit note available ↓; adjustment row |
| EX-3 | Adjust more than the due's outstanding | Error |
| EX-4 | Move to Excess 10,000 from a paid due | Credit note created; due status Moved to Excess; paid ↓ |
| EX-5 | Move part and tick Cancel due | Error "only … when its whole paid amount is moved" |
| EX-6 | Cancel a credit note that was used | Error "Reverse the adjustments first" |
| RF-1 | Refund from Excess 8,000 (NEFT) without bank details | Error "Account Holder Name… required" |
| RF-2 | Refund from Excess with details | Fee Refund Approved; credit notes drawn oldest first |
| RF-3 | Cancel RF-2 | Status Reversed; credit notes restored |
| RF-4 | Fee Demand refund on an unpaid due | Error "no payment has been made yet" |
| RF-5 | Fee Demand refund 5,000 on a paid due | Due paid ↓ 5,000, refunded 5,000, status Partially Paid |
| ST-1 | Record Stipend 3,000 | Stipend Payment submitted; shows on SFM and dashboard |

## 9. Reminders [7]

| # | Scenario | Expected |
|---|---|---|
| RM-1 | Due date = today + 7, run `send_due_reminders` | Email to official email; 7-Day flag set; second run sends nothing |
| RM-2 | Due 5 days past, overdue offset 3 | Overdue notice sent; flag set |
| RM-3 | Master switch off | Nothing sent |
| RM-4 | Template deleted | Plain fallback email |
| RM-5 | Fee Reminder Tool: overdue filter, send selected | Job queued; emails sent even if flag already set |
| RM-6 | Paid / Waived / Cancelled dues | Never reminded |

## 10. Student Fee Management, reports, dashboard [8, 10]

| # | Scenario | Expected |
|---|---|---|
| SF-1 | Change filters without Search | List does not refresh until Search |
| SF-2 | Open a student | Dues, payments, excess, concessions, stipends, refunds match the records |
| SF-3 | Download Dues (xlsx) / Receipts (ZIP) | Files download |
| SF-4 | User without the four page roles opens the page | Not permitted |
| RP-1 | Fee Reports → Due Wise, settlement date filter | Only fully paid dues settled in range |
| RP-2 | Student Wise Outstanding export | One column per component, Total row; cancelled dues excluded |
| RP-3 | Fees Dashboard, filter AY + programme; click Outstanding | Breakdown dialog; totals equal Fee Demand list sums |
| RP-4 | Defaulter List, Aging, Demand Register, Collection Summary, Receipt Register, Refund Register | Figures agree with the records of the test data |

## 11. Fee certificates [9]

| # | Scenario | Expected |
|---|---|---|
| FC-1 | Generate Fee Demand Letter for a year with dues outstanding | PDF with heading, one row per component, bank table if ticked |
| FC-2 | Fee Demand Letter for a fully paid year | Error "Fees Already Paid … Generate the Fee Receipt instead" |
| FC-3 | Education Loan with Has University Scholarship | Columns for programme years; "Less: University Scholarship" row |
| FC-4 | Word output | .docx downloads |
| FC-5 | Upload an edited .docx | Converted PDF served instead of the generated one |
| FC-6 | Bulk Generate for a batch, ZIP download | One certificate per student; per-student errors listed |
| FC-7 | Portal: purpose with "Download Only When Fully Paid", student owes money | Refused |
| FC-8 | Admission Stage certificate for an Applicant | Generated from applicant fee data |

## 12. Bulk upload [11]

| # | Scenario | Expected |
|---|---|---|
| BU-1 | Data Import → Fee Payment → Download Template | Office sheet with one row per open due |
| BU-2 | Import a Fee Payment sheet with a blank Payment Mode | Rejected when attached, row named |
| BU-3 | Import the Fee Demand sheet by Registration ID | Dues created; due date ≤ creation date rejected |
| BU-4 | Upload History → Delete upload | All active records reversed; if one cannot be reversed nothing changes and the reason is shown |

## 13. Admission refunds (Fee & Refund sidebar) [14]

| # | Scenario | Expected |
|---|---|---|
| AR-1 | Refund Request on an Application Fee assignment | Error (only Admission / Confirmation Fee) |
| AR-2 | Refund amount > amount paid | Error |
| AR-3 | Set status Processed with a `pay_` id (test mode) | Razorpay refund called; Refund Transaction created |
| AR-4 | Refund Dashboard with date filter | KPIs and charts reflect Refund Requests only |

## 14. ERPNext bridge (smoke)

Run the full list in `spec/erpnext_bridge/erpnext_fee_bridge_test_checklist.md`. Smoke: submit OP-1 and confirm one Journal Entry is queued and posted when posting is enabled; cancel it and confirm the reversal.

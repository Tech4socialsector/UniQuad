# SLCM Fees → ERPNext Accounting — Design and Test Checklist

SLCM's fee payment details are posted into ERPNext so that income, tax and expenses can be reported there. The flow is one-way: SLCM → ERPNext, and nothing is ever written back to SLCM. Fees Management keeps working exactly as before. Results below are from `slcm.local` (ERPNext v16.7.3, frappe v16.7.0), 2026-10-20.

## 1. Workflow

### One-time setup (Accounts Manager, in ERPNext)

1. Open **Company → TFSS → SLCM Fees** tab.
2. Click **SLCM Fees → Create SLCM Fee Ledgers**. This creates the ledgers, payment-mode accounts and university Bank Accounts, and fills empty settings.
3. Review the result:
   - one income ledger per Fee Component, named after its *Ledger* field;
   - *Mode of Payment* accounts;
   - *Bank Account* records.
4. Tick **Enable SLCM Fee Posting**, check **Post SLCM Fees Dated On/After**, and save.
5. Click **Post Pending Fees Now** once, to post existing fees from the start date.

### Every day (automatic, nobody needs to do anything)

```
Fee Payment / Fee Refund submitted or cancelled in SLCM
        │  (the SLCM save finishes first; nothing waits for ERPNext)
        ▼
background job ──► Journal Entry posted / cancelled in ERPNext
        ▲
hourly sweeper ── also posts Razorpay settlements and retries anything that failed
```

### Checking (Accounts team)

- **ERPNext → Accounting → SLCM Finance** opens a Workspace with:
  - **SLCM Fee Accounting Summary:** income, GST, refunds and gateway charges by month, programme, ledger or source;
  - **SLCM ERPNext Reconciliation:** every SLCM fee transaction next to its Journal Entry, with exceptions flagged;
  - General Ledger, Trial Balance, Profit and Loss and Balance Sheet.
- **Reconciliation actions:**
  - *Post Pending Now* posts anything pending immediately;
  - *Re-post Document* re-books a document whose Journal Entry was cancelled by hand in ERPNext.

## 2. Where everything lives

No custom DocTypes are added. Configuration uses ERPNext's own records:

| What | Where (ERPNext) |
|---|---|
| On/off, start date, submit or draft | **Company → SLCM Fees** tab (custom fields `slcm_*`) |
| Default fee income, unallocated receipts, Output GST, Fee Refunds, Gateway Charges, GST on charges | **Company → SLCM Fees** tab |
| Cost center, cash ledger, bank ledger (Razorpay settles here) | **Company** native defaults: Cost Center, Default Cash Account, Default Bank Account |
| Payment mode → ledger (Cash, Bank Transfer, Cheque, Online Payment → gateway clearing, NEFT, …) | **Mode of Payment** → Accounts table |
| SLCM *University Bank Account* (e.g. "HDFC Bank General 50100508244465") → bank ledger | **Bank Account** (company account, matched by account number) |
| Fee Component → income ledger | **Account** named like the component's *Ledger* (or its name if Ledger is blank). Any other component goes to the default fee income ledger and is flagged in Reconciliation |
| Which SLCM document a posting came from | **Journal Entry → SLCM Reference** section (custom Data fields) |
| Navigation | **Workspace**, **Workspace Sidebar** and **Desktop Icon** "SLCM Finance" (inside Accounting) |

Code in SLCM is in `slcm/erpnext_bridge/`:

| File | Purpose |
|---|---|
| `config.py` | Reads the configuration from the ERPNext records above |
| `builders.py` | Turns a fee document into balanced Journal Entry lines |
| `sync.py` | Posts or cancels idempotently (doc_events, hourly sweeper) |
| `company.py`, `company.js` | Company validation and the *SLCM Fees* buttons |
| `setup_accounts.py` | *Create SLCM Fee Ledgers* |
| `install.py` | Creates the custom fields, Workspace, Sidebar and Icon (ERPNext sites only) |
| `report/` | The 2 reports |
| `demo.py` | Test data |
| `tests/` | Automated tests |

SLCM's own files change only in `hooks.py` (hook registrations) and `modules.txt` (one line).

## 3. What is posted (cash basis, same as the Zoho journal export)

| SLCM event | Journal Entry |
|---|---|
| Fee Payment submitted | **Debit:** the payment-mode ledger (Cash / Bank / Gateway Clearing), or the matched University Bank. **Credit:** each Fee Component's ledger, split by the demand allocation. The GST portion of taxable components goes to Output GST, and any amount not allocated to a demand goes to Unallocated Fee Receipts |
| Fee Payment cancelled | The Journal Entry is cancelled |
| Fee Refund submitted / cancelled | **Debit:** Fee Refunds, or the deposit's liability ledger for deposit components. **Credit:** the refund-mode ledger. Cancelled with the refund |
| Fee Refund from *Excess Amount* | **Debit:** Unallocated Fee Receipts, for the part drawn from credit notes whose money was posted there; anything else goes to Fee Refunds. **Credit:** the refund-mode ledger |
| SLCM Payment Request marked *Settled* (Razorpay) | **Debit:** Bank (net) + Gateway Charges + GST on charges. **Credit:** Gateway Clearing (gross). Posted once its receipt is posted: a Fee Payment, Applicant Payment Receipt or PACE Receipt |
| Applicant Payment Receipt created (admission) | **Debit:** the payment-mode ledger (*Online* → Gateway Clearing). **Credit:** each fee component on the receipt, sharing the net amount when a scholarship reduced it. Deposits go to their liability ledger. Reversed if the receipt is deleted |
| PACE Receipt created | **Debit:** Gateway Clearing. **Credit:** the Account named *PACE &lt;fee type&gt;*. Receipts in a currency other than the company's are not posted and show as "Posting failed" |
| FLE Payment Log (Authorized / Captured) | **Debit:** Gateway Clearing. **Credit:** *FLE Course Fee*. One payment can log several callbacks; only the first paid log posts |
| FLE Payment Log settlement (*processed*) | Same as a Payment Request settlement, posted under the reference type *FLE Settlement* |
| Stipend Payment submitted / cancelled | **Debit:** Stipend Expense. **Credit:** the payment-mode ledger (an *Online* payment out is a bank transfer) |
| Refund Transaction *Processed* (admission refund via Razorpay) | **Debit:** Fee Refunds. **Credit:** Gateway Clearing |
| Student Credit Note: paid fees moved to excess | **Debit:** the income ledger of the due the money came from. **Credit:** Unallocated Fee Receipts |
| Student Credit Note entered by hand with *Received Via* (e.g. a duplicate NEFT) | **Debit:** the bank / cash ledger. **Credit:** Unallocated Fee Receipts. *Received Via* is required for Overpayment and Advance Deposit, and can be filled in after submit |
| Excess adjusted to a due (Credit Adjustment Row) | **Debit:** Unallocated Fee Receipts. **Credit:** the due's income ledger. Only for credit notes whose money was posted |
| Fee Demand, Fee Concession, Scholarship Credit | Nothing is posted, because no cash moves |

**Unallocated Fee Receipts is a liability:** money held for students until it is applied to a due or refunded. The Company form rejects any other account type.

**GST:** *Students Pay GST on Taxable Fees* (Company → SLCM Fees). When ticked, payments for taxable components include GST and the GST part goes to Output GST. When unticked, the whole amount is fee income.

## 4. Safety: why live and Fees Management are not affected

| Risk | How it is avoided |
|---|---|
| Live site without ERPNext | Every entry point checks `erpnext_installed()` first. Hooks, the sweeper and setup do nothing; no fields, menus or reports are created |
| ERPNext present but not wanted yet | Nothing happens until *Enable SLCM Fee Posting* is ticked on a Company |
| ERPNext error while posting | Runs in a background job after the SLCM save; errors go to Error Log (once per document per day) and are retried hourly. The fee save never fails |
| Job queue (Redis) down | After-commit callback is wrapped; the payment still saves with no error popup; the sweeper posts later |
| Cancelling a posted payment or refund | Journal Entry references are plain Data fields, not Links, so ERPNext can never block an SLCM cancel or delete |
| Double posting (two workers at once) | Per-document database lock (`GET_LOCK`), plus a fresh transaction after taking it |
| Accountant cancels a Journal Entry on purpose | It is not re-posted automatically. Reconciliation flags it, and *Re-post Document* re-books it on request |
| Two companies posting the same fees | Company validation allows only one company with posting enabled |
| Name clashes with ERPNext | Every custom field is prefixed `slcm_`; Workspace, Sidebar and Icon are named "SLCM Finance" |
| ERPNext upgrades overwriting the bridge | No ERPNext file is edited; custom fields are recreated by `after_migrate` |
| Overwriting accountant choices | Setup only fills blank Company fields and adds missing Mode of Payment rows; it never changes existing values |
| Developer mode exporting into app files | Workspace, Sidebar and Icon are non-standard and module-less, so they are never exported |

## 5. Test results

Automated: `bench --site slcm.local run-tests --module slcm.erpnext_bridge.tests.test_bridge`. 16 tests, run 3 times in a row with a background worker processing the same documents. All passing, with no duplicates and no leftover records. Legend: ✅ pass · 👤 needs a person.

### A. Isolation

| # | Test | Result |
|---|---|---|
| A1 | No ERPNext: hooks, sweeper, setup and posting all do nothing | ✅ `test_no_erpnext_everything_is_inert`, `test_erpnext_installed_guard` |
| A2 | Real site without ERPNext: `bench migrate`, then submit and cancel a Fee Payment | 👤 needs a test site without ERPNext |
| A3 | Posting disabled on Company: nothing posted | ✅ `test_disabled_bridge_does_nothing` |
| A4 | ERPNext misconfigured: payment still submits; one Error Log; posts after the fix | ✅ `test_erpnext_failure_never_blocks_fee_payment` |
| A5 | Queue down: no error on save | ✅ `test_hook_is_silent_when_queue_is_unavailable` |
| A6 | Cancel a posted Fee Payment / Fee Refund: allowed; Journal Entry cancelled | ✅ `test_receipt_posts_once_and_cancel_reverses`, `test_refund_posts_and_cancel_reverses` |
| A7 | Journal Entry fields are not Links | ✅ `test_journal_entry_reference_fields_are_not_links` |
| A8 | Concurrent workers: no double posting | ✅ demo recreated with the worker live: 0 duplicates; 3 test runs with the worker live |
| A9 | SLCM files changed | ✅ only `hooks.py`, `modules.txt` and new files under `slcm/erpnext_bridge/` |

### B. Posting

| # | Test | Result |
|---|---|---|
| B1 | Bank transfer split over Tuition + Hostel | ✅ Dr HDFC 80,000 / Cr Tuition Fee 60,000 + Hostel Fee 20,000 |
| B2 | Cash ₹1,180 on an 18% GST component | ✅ Dr Cash 1,180 / Cr component 1,000 + Output GST 180 |
| B3 | Cheque for Caution Deposit | ✅ Dr bank / Cr Caution Deposit (liability) |
| B4 | Online payment | ✅ Dr Payment Gateway Clearing / Cr fee ledger |
| B5 | Advance with no demand | ✅ Cr Unallocated Fee Receipts |
| B6 | University bank matched by account number | ✅ `test_university_bank_is_matched_by_account_number` |
| B7 | Component with no matching ledger | ✅ goes to Default Fee Income and is flagged in Reconciliation (`test_component_without_matching_ledger_uses_default_income`) |
| B8 | Refunds: overpayment → Fee Refunds; deposit → liability | ✅ |
| B9 | Razorpay settlement ₹50,000 (fee 1,000, GST 180) | ✅ Dr Bank 48,820 + Charges 1,000 + GST 180 / Cr Clearing 50,000 |
| B10 | Settlement waits for its receipt to be posted | ✅ `test_settlement_waits_for_receipt_then_posts` |
| B11 | Payment cancelled before sync / concession | ✅ nothing posted (`test_concession_posts_nothing`) |
| B12 | Before the start date | ✅ not posted (`test_documents_before_start_date_are_not_posted`) |
| B13 | Journal Entry cancelled by hand in ERPNext | ✅ not auto re-posted; *Re-post* works (`test_journal_entry_cancelled_in_erpnext_is_not_auto_reposted`) |

### C. Reports and screens

| # | Test | Result |
|---|---|---|
| C1 | Fee Accounting Summary (all 4 groupings) | ✅ income ₹2,98,735 · GST ₹180 · refunds ₹5,500 · gateway ₹1,400 · net ₹2,91,835; ledger view Dr = Cr = ₹3,90,415 |
| C2 | Reconciliation | ✅ 25 documents, 0 exceptions, SLCM = ERPNext = ₹3,90,415 |
| C3 | ERPNext P&L | ✅ income ₹2,98,735, expense ₹6,900, profit ₹2,91,835, matching C1 |
| C4 | Workspace "SLCM Finance" | ✅ 4 shortcuts and 3 cards; sidebar and icon under Accounting, for accounts roles (server check) · 👤 look in the browser |
| C5 | Company → SLCM Fees tab | ✅ tab sits between *Accounts* and *Accounts Closing* · 👤 buttons in the browser |

### D. Setup

| # | Test | Result |
|---|---|---|
| D1 | *Create SLCM Fee Ledgers* run twice | ✅ no duplicate accounts, modes or bank accounts; existing values untouched (`test_fee_ledger_setup_is_idempotent`) |
| D2 | Receivable account, another company's account, or a second enabled company | ✅ refused (`test_company_rejects_party_foreign_accounts_and_second_company`) |

### E. Migration

| # | Test | Result |
|---|---|---|
| E1 | Old design removed | ✅ the separate `slcm_erpnext` app was uninstalled and archived; the 4 old DocTypes were removed by `bench migrate` and their tables dropped |
| E2 | Full `bench migrate` | ✅ passes (after ERPNext was moved back to tag `v16.7.3`) |

## 6. Known limitations

- **Cash basis only.** Demands (receivables) and concessions are not booked, matching current Zoho practice.
- **GST on refunds.** A refund of a taxable component does not reverse Output GST; raise a GST credit note in ERPNext if needed.
- **One company.** Only one company can post SLCM fees.
- **Fiscal year.** Each posting date needs an ERPNext Fiscal Year. If one is missing, Reconciliation shows "Posting failed" with ERPNext's message.
- **Renaming accounts.** If a Fee Component ledger's Account is renamed, that component falls back to the default fee income ledger until the names match again. Reconciliation flags this.
- **Razorpay refunds and settlements.** Settlements are posted per payment from Razorpay's per-payment figures. Razorpay takes refunds out of later settlement batches, and the settlement sync skips refund lines. So after an online refund, Gateway Clearing keeps a balance equal to the refund until an accountant clears it against the bank statement.
- **Admission refunds** are booked as Fee Refunds expense, including any deposit portion. They are not split between income and the deposit liability.
- **Not created by any SLCM code:** Mess Payment, Hostel Refund Request, Re Exam Payment Log and Improvement Exam Payment Log. They are not posted (re-exam fees go through Fee Demand → Fee Payment).
- **Tests post real data.** Some tests run the hourly sweeper, which posts every pending document on the site. Run them only on a development or test site.

## 7. Environment notes

- `apps/erpnext` must stay on tag `v16.7.3`. The `UniQuad` branch needs frappe ≥ 17 and breaks `bench migrate` and the P&L.
- Helpdesk's search-index job fails with `FT.CREATE` because the bench Redis has no RediSearch module. This was already the case and is unrelated.

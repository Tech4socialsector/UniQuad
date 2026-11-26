[← Uniquad User Manual](README.md)

# 10. Fees and payments

Every charge to a student is a **Fee Demand** (a "due" or voucher, ID `FD-YYYY-#####`) for one fee component. Payments are recorded against dues and each creates a **Fee Receipt**. Money paid beyond what is due is held as **Excess** (a Student Credit Note) that can be adjusted or refunded. Daily jobs mark unpaid dues **Overdue** and email reminders 7 days and 1 day before the due date and after it. The main screen is the **Student Fee Management** page; the workspace is **Fees Management** (`/desk/fees-management`).

**Desk path:** Desk home → **Fees Management** or **Fees & Payments**.

| Role | Can do |
| --- | --- |
| Accounts User, Accounts Manager, Campus Admin | Student Fee Management, Fee Certificates, Fee Reports; fee structures, dues, notifications, certificates |
| Campus Admin | Also concessions, refunds, bulk collection, University Financial Aid, **Mark Dues Cleared** |
| slcm\_finance, Academics User | Fee Reminder Tool |
| System Manager | Everything |

> *Screenshot: Fees Management workspace* (see the online manual)

> *Screenshot: Fees & Payments workspace* (see the online manual)

Fee Demand statuses: **Pending**, **Partially Paid**, **Paid**, **Overdue**, **Waived**, **Moved to Excess**, **Cancelled**.

## 10.1 Set up fees for the year

1. **Fee Component**: create one per charge (tuition, hostel and so on).
2. **Fee Structure** (`/desk/fee-structure/new`): fill **Fee Structure Name**, **Programme**, **Academic Year**, **Valid From**, **Status** and **Applicable** (Applicant, Student, Faculty or Others). Add rows to **Fee Components for Indian** and/or **Fee Components for Foreign**; totals add up automatically. Set payment options (**Online Payment**, **Cash**, **Payment Gateway**, **Allow Instalment Payments**, **Enable Late Fee**). Click **Save**.
3. **Fee Notification** (`/desk/fee-notification/new`): fill **Notification Name**, **Academic Year**, **Issued Date**, **Effective From**, and add rows to **Fee Components** (component, batch year, programme level, student category, amount). Click **Save**.
4. Click **Actions** → **Publish** and confirm.
5. Click **Generate Fee Demands** and confirm. Dues are created for all eligible students in the background. **Actions** → **View Generation Log** shows the result.

> *Screenshot: New Fee Structure* (see the online manual)

> *Screenshot: Fee Structure with fee components* (see the online manual)

> *Screenshot: New Fee Notification* (see the online manual)

> *Screenshot: Fee Notification list* (see the online manual)

## 10.2 Find a student's fees

1. Open **Student Fee Management** (`/desk/student-fee-management`).
2. Set **Academic Year**, **Term**, **Programme**, **Dues Status** or type in **Search**, then click **Search** (filters apply only when you click it).
3. The tiles show **Students**, **Total Payable**, **Collected**, **Pending Dues**, **Overdue** and **Excess Amount**. Click a student's row.
4. The student page has tabs **Manage Dues**, **Payments**, **Excess Breakdown** and **Scholarship / Stipend**.

> *Screenshot: Student Fee Management: filters, totals and student list* (see the online manual)

> *Screenshot: A student's dues (Manage Dues tab)* (see the online manual)

## 10.3 Record a payment

1. On **Manage Dues**, tick one or more dues and choose **Actions** → **Record Payment** (or click **Multiple Due Payment**).
2. Enter **Paying Now** for each due (up to its pending amount).
3. Choose **Payment Mode** and **Payment Date**, and fill any of **Settlement Date**, **University bank account**, **Bank Name**, **Reference / UTR No.**, **Transaction Date**.
4. Enter **Remarks** (required) and click **Record Payment**, then confirm.

> *Screenshot: A Fee Payment* (see the online manual)

The dues become Partially Paid or Paid and a receipt is created. Download it from the due row or the **Payments** tab (**Download Receipt**).

## 10.4 Other actions on a due

| To | Do this |
| --- | --- |
| Apply a scholarship or waiver | Tick one due → **Actions** → **Apply Waiver / Concession**. Choose **Concession Type**, enter **Waiver Value** and **Reason**, **Save**, **Submit** |
| Pay a due from the student's credit | **Actions** → **Adjust from Excess**, enter **Amount to Adjust** and **Remarks**, click **Adjust** |
| Turn a paid amount into credit | **Actions** → **Move to Excess**, fill **Amount to Move**, **Excess Type**, **Academic Year**, **Remarks**; optionally tick **Cancel this due after moving** |
| Cancel a due | **Actions** → **Cancel Due**, enter **Reason / Remarks**. Paid dues cannot be cancelled; this cannot be undone |
| Refund a paid due | **Actions** → **Issue Refund for Due**; fill **Refund Type**, **Refund Amount**, **Refund Date**, **Refund Mode**, **Reason for Refund**; **Submit** |
| Refund the student's credit | **Refund from Excess**; bank fields fill from the student's bank details; click **Refund** |
| Add a one-off charge | **Create a due**; fill **Fee Component**, **Original Amount**, **Due Date**; **Save** |
| Record a stipend | **Scholarship / Stipend** tab → **Record Stipend Payment** |

> *Screenshot: A Fee Demand* (see the online manual)

> *Screenshot: New Fee Demand (Create a due)* (see the online manual)

> *Screenshot: An approved Fee Concession* (see the online manual)

> *Screenshot: A Fee Refund* (see the online manual)

## 10.5 Bulk work

- **Bulk Upload** (Student Fee Management list): pick **Fee Demands**, **Fee Payments** or **Fee Concessions**, click **Download Template**, fill the yellow columns, then **Import** and start the import.
- **Bulk Fee Collection** (`/desk/bulk-fee-collection/new`): set **Academic Year**, **Payment Date**, **Payment Mode**, **Save**, click **Fetch Students with Dues**, edit **Amount to Collect**, then **Process Bulk Payment**.
- **Fine Imposition** (`/desk/fine-imposition/new`): set the due-date window and **Fine Type** (Flat Amount or Percentage of Outstanding), **Save**, **Preview Outstanding Demands**, **Apply Fine**. **Reverse Fine** undoes it.

> *Screenshot: New Bulk Fee Collection* (see the online manual)

> *Screenshot: New Fine Imposition* (see the online manual)

## 10.6 Reminders and reports

1. **Fee Reminder Tool** (`/desk/fee-reminder-tool`): choose **Reminder Type** (Overdue Notice, 7-Day Advance Reminder or 1-Day Final Reminder), optional filters, click **Search**, tick students (or **Select All**), click **Send Reminders**.
2. **Fee Reports** (`/desk/fee-reports`): tabs **Due Wise Report** and **Student Wise Outstanding**. Set filters, click **Search**, then **Export Excel**.
3. Other reports from the workspace: Defaulter List, Collection Summary, Fee Demand Register, Receipt Register.

> *Screenshot: Fee Reminder Tool* (see the online manual)

> *Screenshot: Fee Reports* (see the online manual)

## 10.7 Fee certificates

1. **Set up once** in **Fee Certificate Settings** (`/desk/fee-certificate-settings`): institute details, **Letter Head Header Image** and **Footer Image**, signatory with **Signature Image** and **Seal / Stamp Image**, bank details, and the **Purposes & Templates** table. **Restore Default Purposes** re-adds the three standard purposes.
2. **One certificate**: on **Fee Certificates** (`/desk/fee-certificates`) click **Generate Certificate**. Choose **Certificate For** (Campus Student or Admission Stage), the **Student** (or **Applicant**), **Purpose**, **Academic Year**, **Download As** (PDF or Word). Click **Generate & Download**.
3. **Many certificates**: click **Bulk Generate**, filter and click **Find Students**, tick students, click **Generate N Certificate(s)**, then **Download All as ZIP**.
4. To replace a generated file with an edited copy, click **Upload Edited** on its row.

> *Screenshot: Fee Certificate Settings* (see the online manual)

> *Screenshot: Fee Certificates page* (see the online manual)

> *Screenshot: New Fee Certificate Request* (see the online manual)

Students can also download certificates themselves from the portal. Purposes marked **Download Only When Fully Paid** are blocked while dues are outstanding.

## 10.8 University Financial Aid and bank details

- **University Financial Aid** (`/desk/university-financial-aid/new`): pick **Academic Year** and **Student**, fill **Aid Given (FA Tier)** and the amounts (tuition, hostel and mess, stipend, laptop, loan interest). **Total Financial Aid Awarded** adds up. Set **Status of Acceptance** and **Save**. This is a record only; to reduce a due, apply a concession of type University Financial Aid.
- **Bank details**: students submit savings and loan account details once from the portal. To let a student change them, untick **Bank Details Submitted by Student** on their Student Master and save.

> *Screenshot: New University Financial Aid* (see the online manual)

[← Uniquad User Manual](README.md)

# 9. Promotions

Promotion moves students to the next year or term and enrols them in the next batch. There are two ways:

**Desk path:** Desk home → **Academics** → **Promotions**.

| Way | Use it for | Where | Who |
| --- | --- | --- | --- |
| Year to year, checked against a policy | End of an academic year | **Promotion Management** page (`/desk/promotion-management`) | System Manager, Academics User |
| Term to term, no policy | Moving to the next term within a year | **Promote Students** on the Student Enrollment list | System Manager, slcm\_Academic Incharge |

> *Screenshot: Promotions workspace* (see the online manual)

Both need next year's **Batch** to exist already, with the same Programme and Section, **Term Year** plus 1 and the next Academic Year (section 3.7). The **Promotions** workspace (`/desk/promotions`) has shortcuts and cards for promoted, not promoted and pending students.

## 9.1 Create a promotion policy

1. Go to `/desk/promotion-policy/new`.
2. Fill **Policy Title**, **Programme**, **Academic Year** and **Status** (Active).
3. Under **Year Transition** set **From Year** and **To Year** as year levels (for example 1 and 2).
4. Tick the checks you want and set each limit:
   - **Enable CGPA Check** + **Minimum CGPA Required**
   - **Enable Backlog Check** + **Maximum Backlogs Allowed**
   - **Enable Attendance Check** + **Minimum Attendance % Required**
   - **Enable Course Shortage Check** + **Max Courses with Attendance Shortage**
   - **Enable Carry-Forward** + **Max Allowed CF Courses**
   - **Block Promotion on Fee Due**
5. Under **Advanced Settings** choose **When Criteria Partially Fail** (Not Promoted or Conditional) and tick **Auto-update Student Year on Confirm** if publishing should move students automatically.
6. Click **Save**.

> *Screenshot: New Promotion Policy* (see the online manual)

## 9.2 Run a year-to-year promotion

1. Open **Promotion Management** (`/desk/promotion-management`).
2. Choose **Programme**, **Academic Year** and **Promotion Policy**, then enter **From Year** and **To Year**.
3. Click **Preview**. Each student shows CGPA, Result (Promoted, Not promoted or Conditional) and the reason.
4. Click **Run Promotion**, then **Save draft**. Nothing changes for students yet.
5. On the **Promotion Log** tab review the draft. Use **Promote anyway** or **Not promoted** with a **Reason** to override a student. **Download** exports the lists; **Discard draft** throws the draft away.
6. Click **Publish**, choose whether to tick **Email each student their result**, and click **Publish N decision(s)**.

> *Screenshot: Promotion Management page* (see the online manual)

If the policy auto-updates, each promoted student's current enrollment is completed and a new one is created in next year's batch. If the target batch is missing, the student stays put with the message "N student(s) could not be moved"; create the batch and click **Retry failed moves**.

The **History** tab lists past runs. **Official Report** → **Download Excel** gives the university report.

## 9.3 Promote to the next term

1. Open `/desk/student-enrollment`, filter to one programme and tick the students.
2. Click **Promote Students**.
3. Choose **Target Academic Year** and **Target Term**. The dialog previews the courses in the target term, or warns if the target batch does not exist.
4. Click **Promote** and confirm. A **Promotion Run** starts in the background.
5. Click **View Promotion Log** to see each student's result (Promoted, Skipped or Failed). In the Promotion Run, fix skipped rows with **Promote anyway**, **Mark as exempt** or **Retry**.

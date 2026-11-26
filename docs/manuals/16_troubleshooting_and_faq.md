[← Uniquad User Manual](README.md)

# 16. Troubleshooting and FAQ

## 16.1 Common messages

| Message or problem | Why | What to do |
| --- | --- | --- |
| **Not a Student / Faculty / Parent Account** | The login email is not linked to a record | Student: the Google email must equal **Official Email** on the Student Master. Faculty: the email must match the Faculty record. Parent: the email must be in the student's **Parents** table |
| **No student record found for this email** | Same as above, at Google sign-in | Ask the office to fill **Official Email** on the Student Master |
| **Submission Not Allowed: Applicant is not eligible.** | The applicant fails an eligibility rule | Check the rule mapping for the programme and campus (section 4A.4) |
| Applicant cannot submit | Application fee is not Paid or Waived | Applicant pays online, or staff use **Record Application Fee Payment** or **Waive Application Fee** |
| **No Actions Available** on Update Status | Your role cannot move the student from their current stage | Check the stage table in section 5.2 |
| **Cannot move to … Missing documents: …** | A required document or field is missing | Upload or fill what the message names, then try again |
| **No Common Next State** | Students selected for bulk update are at different stages | Filter the list to one stage first |
| **Enroll** opens with an empty Batch | Batch is not carried over | Choose the **Batch** on the enrollment before saving |
| Course Offering not added to a new enrollment | The offering is not **Active** | Set the Course Offering's **Status** to Active |
| **Cannot mark attendance for future dates.** | Date is in the future | Pick today or a past date |
| RFID swipe not counted | No active session, room not mapped or card unknown | Fix it on **Attendance Sync** (section 7.3) |
| **No Exam Plan assigned for this course** | Schemas not mapped | Map schemas on the Exam Plan (section 8.2) |
| **Result entry is locked for this course.** | Course is locked in Course Results | The exam office clicks **Lock** again to unlock |
| **Edit deadline has passed** (faculty) | Edit access deadline in Result Settings | Ask the exam office to extend it (section 8.4) |
| Students cannot see results | Results not published | Publish in **Publish Results** (section 8.7) |
| **N student(s) could not be moved** after promotion | Next year's batch does not exist | Create the batch, then **Retry failed moves** |
| Fee filters seem to do nothing | Filters apply only on **Search** | Click **Search** |
| Fee certificate card locked on the portal | Purpose requires fees fully paid | Clear the outstanding dues first |
| Student cannot change bank details | Details can be submitted once | Office unticks **Bank Details Submitted by Student** |
| Venue not in the list | Your role is not in the venue's **Allowed Roles** | Ask the Registrar to add your role on the Venue Master |

## 16.2 Quick FAQ

- **Where do I start each academic year?** Follow the setup order in section 3.1: academic year, terms, programmes, batches, sections, course offerings, fee structure and fee notification.
- **How does an applicant become a student?** Offer accepted → confirmation and full fee paid → **Convert to Student** on the fee assignment (section 4A.9) → registration stages (section 5).
- **Can a student be enrolled before registration is complete?** No. **Current Status** must be **Completed**.
- **How do I give a faculty member portal access?** Tick **Auto Create User** on their Faculty record with **Official Email ID** filled (section 3.4).
- **How do parents get access?** Add the parent with email in the student's **Parents** table and use **Send Parent Login Invite** (section 5.5).
- **How do I reverse a waiver?** Cancel the Fee Concession; the status becomes Reversed and the waiver is removed.
- **Can I undo a published result?** Yes: **Unpublish Selected** or **Unpublish All** on Publish Results.
- **Who approves condonation?** First an AAD approver, then a Programme Chair approver, assigned automatically from Attendance Settings (section 7.5).

[← Uniquad User Manual](README.md)

# 5. Student registration (REGO)

Every new student passes through registration stages, one office at a time, until the status is **Completed**. Only then can the student be enrolled in courses. Each officer sees only the students waiting at their own stage; System Manager, slcm\_Registrar and Accounts User see everyone. The **Student Registration** workspace (`/desk/student-registration`) shows a count card for each stage.

**Desk path:** Desk home → **Academics** → **Student Registration**, or Desk home → **REGO**.

> *Screenshot: Student Registration workspace: one card per stage* (see the online manual)

> *Screenshot: REGO workspace* (see the online manual)

## 5.1 How a student record starts

- **From admissions**: **Convert to Student** on a paid Applicant Fee Assignment creates the Student Master (section 4A.9).
- **By hand**: go to `/desk/student-master/new`, fill **Full Name** and **Email** (Contact tab), Batch, Programme and documents, then **Save**. The ID is `STUD-YYYY-#####` and **Current Status** starts at **Selected**. The valid fee structure for the programme is attached automatically.

> *Screenshot: Student Master list with Update Status, Enroll and Generate Student ID* (see the online manual)

> *Screenshot: New Student Master form* (see the online manual)

The Student Master has tabs **Registration**, **Finance**, **Programme Mapping**, **Current Academic Progress**, **Personal**, **Contact**, **Parent / Guardian**, **Residence**, **Academic Qualification**, **Account**, **Status History**, **Documents**, **Admission**.

## 5.2 Registration stages

| # | From | To | Who moves it | Must be done first |
| --- | --- | --- | --- | --- |
| 1 | Selected | Pending REGO | Student or slcm\_Registration User | – |
| 2 | Pending REGO | Pending FINO | slcm\_REGO Officer | Uploaded: Aadhaar Card, PAN Card, STD X Marksheet, Passport size photo |
| 3 | Pending FINO | Pending Registration | slcm\_FINO Officer | **Fee Payment Status** is Paid or Partially Paid |
| 4 | Pending Registration | Pending Print & Scan | slcm\_Registration Officer | Name, Date of Birth, Gender, Email, Phone, Batch, Programme Of Study filled |
| 5 | Pending Print & Scan | Pending Residences | slcm\_Documentation Officer | **ID Card Issued** set to Yes, **Aadhaar Verified** ticked |
| 6 | Pending Residences | Pending IT | slcm\_Hostel Admin | For hostellers: room allocated and **Keys Handed Over** ticked |
| 7 | Pending IT | Final Verification REGO | slcm\_IT Admin | **Official Email ID** filled |
| 8 | Final Verification REGO | Completed | slcm\_Registration Officer | Aadhaar, PAN, Offer Letter and Student Declaration uploaded and verified |
| 9 | Completed | Re-Open | System Manager | – (all details may need re-verification) |

The checks apply to everyone, including System Manager.

## 5.3 Move one student to the next stage

1. Open the student, for example `/desk/student-master/STUD-2026-00006`.
2. Click **Update Status** → **Status** (top right).
3. In **Update Registration Status**, pick **New Status**. You only see the stages your role may set; otherwise the message is "No Actions Available".
4. Enter **Remarks** (required) and click **Update Status**, then **Yes** to confirm.

> *Screenshot: Student at the Selected stage with the Update Status button* (see the online manual)

> *Screenshot: Student whose registration is Completed* (see the online manual)

The new stage is saved, a row is added on the **Status History** tab and a comment appears on the timeline. If something is missing, the error names it (for example "Cannot move to Pending FINO. Missing documents: …").

When the student reaches **Completed**, **Student Status** and **Academic Status** become **Active**, and the student and parents receive a "Registration Completed" email with the Registration Slip PDF.

## 5.4 Move many students at once

1. Open `/desk/student-master` and tick students who are all at the same stage (otherwise: "No Common Next State").
2. Click **Update Status** in the toolbar.
3. In **Bulk Update Status**, choose **New Status**, enter **Remarks** and click **Update Status**.

Each student is checked separately and a summary lists successes and errors.

## 5.5 Other student tools

| Tool | Where | What it does |
| --- | --- | --- |
| **Registration Slip** | Student form | Downloads the registration slip PDF |
| **Send Parent Login Invite** | Student form | Emails parents a portal login (parents need email addresses) |
| **Change Fee Structure** | Student form, under **Update Status** | Changes the fee structure and logs it |
| **Download Slip** | Student list | Slips for up to 5 students |
| **Generate Student ID** → **Auto Generate** | Student list | Pick **Programme**, **Academic Year**, term; **Show Students** to preview; **Proceed** |
| **Generate Student ID** → **Bulk Upload** | Student list | **Download Sample Template**, fill IDs, **Upload Filled Template**, **Upload** |
| **Bulk Upload Section** | Student list | Assigns sections from a template file |

## 5.6 Enroll a student

A student can be enrolled only when **Current Status** is **Completed**, a **Batch** is set and they are not already enrolled in that batch.

1. On the student form click **Enroll**. A new **Student Enrollment** opens with the student filled in.
2. Choose the **Batch**. The **Courses** table fills with every Active Course Offering of that batch.
3. Set **Enrollment Date**, **Section**, **Faculty Advisor** and **Enrollment Status** (Enrolled, Dropped, Completed or Pending).
4. Click **Save**.

> *Screenshot: New Student Enrollment* (see the online manual)

To enroll many students, tick them in the Student Master list and click **Enroll** (System Manager). Enrollment status updates the student: Dropped makes the student inactive, Completed marks them Graduated.

## 5.7 ID cards

Uniquad designs ID card layouts, produces front and back card images for each person, and records every print. Card types are **Student**, **Faculty**, **Driver**, **Visitor** and **Non-Faculty**; card numbers start STU-, FAC-, DRV-, VIS- or STF-. Card work is done by the IT team (**System Manager**) from the **IT Team** workspace (`/desk/it-team`); slcm\_Registrar can use the bulk tool and read the logs. The workspace shows **Total ID Cards**, **Active ID Cards**, **Pending (Draft) Cards**, **Cancelled Cards** and **Print Log Entries**.

**Desk path:** Desk home → **Campus & Support** → **IT Team**.

**Design a template**

1. Go to `/desk/id-card-template/new`.
2. Enter **Template Name**, and choose **Card Type** and **Card Size** (CR80, 85.6 × 54 mm). Tick **Is Default Template** if it should be used by default.
3. Fill **Institute Details**: **Institute Name**, **Institute Logo**, **Authority Signature**, **Default Watermark**, **Institute Address**, **Validity Text**.
4. Choose **Template Creation Mode**. **Drag and Drop** is the easiest:
   - Pick a starting design under **Select a Template** (for example **Blank Canvas**, **University Standard - Vertical**, **Faculty ID Card**).
   - In **Card Settings** choose **ORIENTATION** (Landscape or Portrait) and **ACTIVE SIDE** (Front or Back).
   - From **Tools & Fields**, add design items (**Add Text**, **Add Image**, **Add Box**, **Add Header**, **Add Footer**), student fields (Student Name, Student Photo, Student ID, Blood Group, Programme, Batch, QR Code, Expiry Date and more) and institute items (logo, signature, name, address).
   - Drag each item into place and adjust it in **Properties** (size, colour, **Center H**, **Center V**).
5. Click **Show Preview** to see the card with a sample student, then **Save**.

> *Screenshot: IT Team workspace: ID card and RFID tools* (see the online manual)

> *Screenshot: New ID Card Template* (see the online manual)

> *Screenshot: ID Card Template in Drag and Drop mode* (see the online manual)

Text can include placeholders in square brackets, such as `[Student Name]`, `[Student ID]`, `[Blood Group]`, `[Programme]`, `[Expiry Date]`; they are replaced with each person's details. Other modes: **Field Mapping** (upload **Front Background** and **Back Background** images and position each field in the **Fields** table), **Jinja Template** (HTML, for IT) and **Canva** (design in Canva, then upload the image).

**Generate cards for a whole batch**

1. Open **Generate ID Cards** (`/desk/id-card-generation-tool`).
2. Under **Filters** choose **Academic Year**, **Programme** and/or **Batch**, and click **Get Students**. Only Active students load; each row shows **Pending** (no card yet) or **Already Exists**.
3. Choose the **ID Card Template**, **Issue Date** and **Expiry Date**. **Generate Front** and **Generate Back** are ticked.
4. Click **Generate Cards** and confirm with **Yes**. The message shows how many cards were made and the log run ID. Each row becomes **Generated** or shows the error.
5. Click **Download ZIP** for the individual card images, or **Download Print Layout** for print-ready A4 sheets (front and back side by side).

> *Screenshot: ID Card Generation Tool* (see the online manual)

Running the tool again also redraws existing cards with the chosen template.

**Generate one card**

1. Go to `/desk/id-card-generation/new` and choose the **Card Type** and the person (for example **Student**).
2. Choose the **ID Card Template**, **Issue Date** and **Expiry Date** (for students it defaults to the batch end date).
3. Click **Save**. The card starts as **Draft** and the images are produced automatically; if not, click **Generate Card**.
4. The **Generated Images** section shows the front and back; **Verification** shows the QR code and verification link.

> *Screenshot: New ID Card Generation* (see the online manual)

> *Screenshot: ID Card Generation list with card statuses* (see the online manual)

> *Screenshot: A Generated card with Print Card and Actions* (see the online manual)

A person can have only one active card. The photo comes from the student's passport size photo on the Student Master, so update it there first.

**Print**

1. Open a **Generated** card and click **Print Card**. The images open with the print dialog.
2. Each print adds to **Print Count** and creates an **ID Card Print Log** entry: the first print is **Original**, later ones **Reprint**.
3. For many cards, use **Download Print Layout** in the tool.

Printing does not change the status. Set **Card Status** to **Printed** by hand if you track that.

**Lost, damaged or withdrawn cards**

| To | Do this |
| --- | --- |
| Replace a lost or damaged card | **Actions** → **Reissue Card**, enter the reason, **Confirm Reissue**. The old card is cancelled and a new Draft card is created; open it from the list, **Generate Card**, then **Print Card** |
| Withdraw a card | **Actions** → **Cancel Card**, enter **Reason for Cancellation**, **Confirm Cancellation** |
| Retry a card in **Error** | Check the photo and template, then click **Generate Card** |

> *Screenshot: A Cancelled card with its reason and status history* (see the online manual)

> *Screenshot: A card in Error with Generate Card* (see the online manual)

Card statuses: **Draft**, **Generated**, **Printed**, **Cancelled**, **Expired**, **Error**. Every change is kept in the **Status History** table.

**Logs**: **ID Card Generation Log** (one entry per bulk run with students selected, cards generated and **Success**, **Partial** or **Failed**) and **ID Card Print Log** (one entry per printed card with **Print Type**, **Print Layout**, who printed it and the images printed).

> *Screenshot: ID Card Generation Log* (see the online manual)

> *Screenshot: ID Card Print Log* (see the online manual)

## 5.8 RFID cards

Each student's swipe card is linked to their record so classroom readers can mark attendance (section 7.3). A swipe counts when the card belongs to a student, the reader is mapped to a room, and a class is running in that room.

1. **Register readers**: go to `/desk/rfid-device/new`, enter **Device ID** (the ID the reader sends), **Device Name**, **Location**, tick **Is Active** and **Save**.
2. **Map readers to rooms**: go to `/desk/rfid-device-room-mapping/new`, choose **RFID Device** and **Room**, set **Effective From** (and **Effective To** if temporary) and **Save**.
3. **Assign cards to students** on **RFID Card Management** (`/desk/rfid-mapping`): on **Unassigned RFID Cards** click **Assign Student**, choose the **Student** and click **Assign and Save**. Past swipes from that card are linked too. For many cards use **Export for Vendor** and **Bulk Import CSV** (columns `student_id` and `rfid_uid`).
4. **Lost RFID card**: record it in **Student RFID Card** with **Card Status** Lost or Blocked and a **Deactivated Date**, remove the old card from the student on RFID Card Management, then assign the new card. Marking it Lost alone does not stop the old card working.

> *Screenshot: New RFID Device* (see the online manual)

> *Screenshot: RFID Device list* (see the online manual)

> *Screenshot: New RFID Device Room Mapping* (see the online manual)

> *Screenshot: Device room mappings* (see the online manual)

> *Screenshot: RFID Card Management page* (see the online manual)

> *Screenshot: Student RFID Card form* (see the online manual)

IT staff set up the connection to the reader database in **RFID Configuration** (`/desk/rfid-sql-agent-settings`): use **Test Connection** to check it and **Run Now** to fetch swipes immediately. Fetched swipes appear in **RFID Punch Log** with status **Matched** or **Unmatched**.

> *Screenshot: RFID Configuration (SQL Agent)* (see the online manual)

> *Screenshot: RFID Agent Dashboard* (see the online manual)

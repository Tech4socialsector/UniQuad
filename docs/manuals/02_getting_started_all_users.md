[← Uniquad User Manual](README.md)

# 2. Getting started (all users)

Staff sign in at `/login` and work in the Desk. Students, faculty and parents sign in at `/portal-login`. Applicants sign in on the admissions portal (see section 4).

| Who | Login address | How they sign in |
| --- | --- | --- |
| Staff | `/login` | Username or email + password |
| Students and faculty | `/portal-login`, tab **Faculty & Student** | **Sign in with Google** with the institutional account |
| Parents and guardians | `/portal-login`, tab **Parent & Guardian** | Username or email + password |
| Admissions applicants | `/admission/login` | Register, then email + password |
| PACE applicants | `/paceadmissions/login` | Register, then email + password |
| FLE applicants | /fle/login | Register, then email + password (SIGN IN) |

## Staff: log in to the Desk

1. Open `/login` on the Uniquad site.
2. Enter your **Email** and **Password**.
3. Click **Login**. The Desk home screen opens at `/desk`.

If a student, faculty member or parent opens `/login`, the system sends them to `/portal-login`.

> *Screenshot: Staff login page* (see the online manual)

## Students and faculty: log in to the portal

1. Open `/portal-login`. The **Faculty & Student** tab is selected.
2. Click **Sign in with Google** and choose your institutional Google account.
3. You land on the Faculty Portal if your email matches a Faculty record, or on the Student Portal if it matches a Student record.

You do not register yourself. On your first login the system links your account automatically:

- **Students**: your Google email must equal the **Official Email** on your Student Master record.
- **Faculty**: your Google email must match the email on your Faculty record.

> *Screenshot: Portal login, Faculty & Student tab* (see the online manual)

## Parents: log in to the portal

1. Open `/portal-login` and click the **Parent & Guardian** tab.
2. Enter **Username or email** and **Password**, then click **Login**.
3. If a **Verification Code** step appears, type the 6-digit code and click **Verify**.
4. Forgot your password? Click **Forgot password?**, enter your email and click **Reset Password**. A reset link is emailed to you.

A parent is recognised because their email is in the **Parents** table on the student's Student Master record. A parent linked to several students sees all of them.

## Find your way around the Desk

- **Desk home (`/desk`)**: the screen you see after login, with one icon per area. Some icons open a workspace straight away; others are **groups** that open a small window listing their workspaces. Click the one you need.
- **Workspace**: the left sidebar lists the workspace's lists, reports and pages. The main area shows number cards, shortcuts and charts. Click the logo at the top left to return to the Desk home.
- **Search bar**: the box at the top says **Search** (Ctrl+K). Type a record type (for example `Student Master`), a record ID or a page name, then press Enter. Type `new Fee Demand` to start a new record.
- **Addresses**: a list is `/desk/<record-type>` (for example `/desk/student-master`), a record is `/desk/<record-type>/<ID>`, and a page is `/desk/<page-name>`.

> *Screenshot: Desk home screen* (see the online manual)

| Icon on Desk home | What it opens |
| --- | --- |
| **Academics** (group) | Attendance, Programme Management, Promotions, Student Registration |
| **Admission** (group) | Eligibility, Fee & Refund, FLE, Interview, Merit, Offer Letters, PACE, Scholarship, Test, Settings |
| **Admission Eligibility** | Admission Eligibility workspace |
| **Campus & Support** (group) | Helpdesk, IT Team (ID cards and RFID), Venue Bookings |
| **Examination Management** (group) | Exam Planner, Exam Result, Transcript Management |
| **Faculty Management** (group) | Not set up yet (shows "Icon is not correctly configured") |
| **Fee Management** (group) | Not set up yet (shows "Icon is not correctly configured") |
| **Fees & Payments**, **Fees Management** | Fee workspaces (section 10) |
| **Framework** (group) | System settings for administrators: Automation, Build, Data, Email, Integrations, Printing, System, Users, Website |
| **Master**, **Masters**, **SLCM Master** | Master data workspaces (section 3) |
| **MSA** | Merit and seat allocation workspace (section 4A.7) |
| **Programme Setup** | Programme, course and timetable setup (sections 3 and 6) |
| **REGO** | Registration workspace (section 5) |
| **Student Services** (group) | Hostel Management, Placement, Student Portal |

> *Screenshot: Academics group* (see the online manual)

> *Screenshot: Admission group* (see the online manual)

> *Screenshot: Campus & Support group* (see the online manual)

> *Screenshot: Examination Management group* (see the online manual)

> *Screenshot: Student Services group* (see the online manual)

> *Screenshot: A workspace: sidebar on the left, number cards and shortcuts on the right* (see the online manual)

## Common actions on any record

| To | Do this |
| --- | --- |
| Create a record | Open the list and click **+ Add \<record type>**, or press Ctrl+B |
| Save | Click **Save** or press Ctrl+S |
| Filter a list | Use the filter boxes above the list, or **Filter** → **+ Add a Filter** |
| Import many records | In the list, open the menu (⋯) → **Import** |
| Export | In the list, open the menu (⋯) → **Export** |
| Delete | Tick the rows in the list → **Actions** → **Delete** |

## Edit, rename, cancel and delete a record

These steps work on every form in the Desk (Academic Year, Programme, Student Master, Fee Structure and so on).

**Edit**

1. Open the list (for example `/desk/academic-year`) and click the record.
2. Change the fields you need. "Not Saved" appears next to the title.
3. Click **Save** (Ctrl+S).

> *Screenshot: A saved record: edit the fields and click Save* (see the online manual)

**Rename** (where allowed): click the record title at the top of the form, type the new name and click **Rename**. Links in other records update automatically.

**Cancel and amend a submitted record** (fee payments, concessions, condonations and other records with a **Submit** button): a submitted record cannot be edited.

1. Open it and click **Cancel**, then **Yes**. The status becomes **Cancelled**.
2. To correct it, click **Amend**. A copy opens (named `<original>-1`); fix it, **Save** and **Submit**.

**Delete one record**

1. Open the record.
2. Click the **⋯** menu (top right) → **Delete**, then **Yes**.

> *Screenshot: Form menu (⋯) with Delete* (see the online manual)

**Delete many records**: in the list, tick the rows, click **Actions** → **Delete** and confirm.

> *Screenshot: List view: tick rows, then Actions → Delete* (see the online manual)

If another record uses it, Uniquad refuses with "Cannot delete or cancel because … is linked with …". Delete or change the linked records first, or set the record's **Status** to Inactive instead of deleting it. Submitted records must be cancelled before they can be deleted. Deleted records go to **Deleted Documents** (search it in the search bar), where a System Manager can **Restore** them.

## Wrong account message

If your login has no matching record, the portal shows **Not a Student Account**, **Not a Faculty Account** or **Not a Parent Account**. Click **Sign Out & Login Again** and use the right account, or ask the administration office to link your record.

## Log out

- **Desk**: click your avatar (top right) → **Log out**.
- **Student and faculty portals**: click **Sign Out** at the bottom of the sidebar, or avatar → **Sign Out**, then confirm.
- **Parent portal**: click **Sign Out** in the sidebar.

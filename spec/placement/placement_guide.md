# Placement: User Guide

**Applies to:** Uniquad (SLCM v16), as on disk in November 2026
**Who this is for:** Placement officers who keep company records, open placement and internship opportunities, run placement events, and track applications and offers.
**Where:** Desk → **Student Services → Placement**. Students use **Student Portal → Placements**.

---

## 1. The flow at a glance

```
1. Companies        SLCM Company → Company Contact → Company Interaction
2. Student profiles Student Placement Profile (CGPA, resume, skills, internships)
                      Draft → Verified → Locked
3. Opportunity      Placement Opportunity (company, roles, window, status Draft → Open → Closed)
4. Events           Placement Event (PPT / Test / GD) inside the application window
5. Applications     Student applies (portal) → Placement Application: Applied
6. Shortlist        Shortlist Upload (file only) · set application Status: Shortlisted / Rejected
7. Offer            Placement Offer: Offered → Accepted / Declined
```

### Key ideas

| Term | Meaning |
|---|---|
| **SLCM Company** | A recruiter. Named by company name. (Not ERPNext's Company.) |
| **Placement Opportunity** | A job or internship from one company, with an application window. |
| **Student Placement Profile** | The student's placement CV in Uniquad. One per student. |
| **Placement Application** | One student's application to one opportunity. |
| **Placement Offer** | The offer a student gets from an opportunity. |

---

## 2. Where things are

### 2.1 Sidebar (`slcm/workspace_sidebar/placement.json`)

| Sidebar item | Opens |
|---|---|
| Home | Placement workspace |
| Student Placement Profile | Student Placement Profile list |
| Placement Opportunity | Placement Opportunity list |
| Shortlist Upload | Shortlist Upload list |
| Create Placement Event | Placement Event list |
| Student Placement Profile Creation | Student Placement Profile list (same as above) |
| Placement Application | Placement Application list |
| Company Contact | Company Contact list |
| Company Interaction | Company Interaction list |
| Company | SLCM Company list |

**Placement Offer is not on the sidebar or the workspace.** Open it from the search bar.

### 2.2 Workspace
Number cards *Placement Applied*, *Shortlisted*, *Placement Rejected*, then shortlists for the DocTypes above and a "Workflow" block (Profile Creation → Company → Contact → Interaction → Opportunity).

### 2.3 Desktop icon (`slcm/desktop_icon/placement.json`)
**Placement** sits inside the **Student Services** folder. Shown to `slcm_Placement Officer`, `Campus Admin`, `Admission Admin`.

---

## 3. Companies

### 3.1 SLCM Company
*Placement → Company → + Add*

| Field | Notes |
|---|---|
| Company Name | Required. Becomes the record name. |
| Industry / Sector | Legal / Consulting / Technology / Finance / Manufacturing / Education / Healthcare / Other (required) |
| Practice Area, Hiring Locations, Website | |
| Company Status | Active / Inactive |

### 3.2 Company Contact
Named `{company}-{contact_name}`. Fields: Company, Contact Name, Designation, Email (required), Phone, **Primary Contact**.

**Rule:** ticking Primary Contact unticks it on every other contact of the same company.

### 3.3 Company Interaction
Fields: Company, Interaction Type (Call / Email / Meeting), Interaction Date (default today), Notes, Logged By (defaults to you).

> The record is **named by the company and Company is unique**, so each company can have only one interaction record. See Open questions.

---

## 4. Student Placement Profile

*Placement → Student Placement Profile → + Add*. Named by the student.

| Field | Notes |
|---|---|
| Student | Required, unique. A plain text field holding the Student Master ID. |
| Programme, Batch Year, CGPA | Required, typed in |
| Internships (table) | Company, Role / Title, Duration, Location, Work Description |
| Skills | Multi-select from **Skill** |
| Final Resume | Required attachment |
| LinkedIn Profile URL, Supporting Documents | |
| Profile Status | Draft / Verified / Locked (default Draft) |
| Verified By | Shown when Verified or Locked |

**Rules**
- A student (role `slcm_Student`) sees and edits only their own profile.
- When the profile is **Locked**, the form is read-only for a student.
- CGPA and programme are not fetched; they are typed.

---

## 5. Placement Opportunity

*Placement → Placement Opportunity → + Add*

| Field | Notes |
|---|---|
| Company | SLCM Company, required |
| Role Name | Multi-select of role names (DocType *Placement Opportunity setbyuser*, created on the fly), required |
| Opportunity Type | Placement / Internship |
| Eligibility Criteria | Free text |
| Compensation, Job Location | |
| Application Start / Application End | Date and time. Start defaults to now. |
| Status | Draft / Open / Closed (default Draft) |
| Applicable Batches | Multi-select (DocType *Applicable Batches setbyuser*) |

**Rules the system enforces**
- Application End must be after Application Start.

> The record is **named by the company** (`format:{company}`), so a second opportunity from the same company cannot be saved under the same name. See Open questions.

> Eligibility Criteria and Applicable Batches are **not checked** when a student applies.

---

## 6. Placement Event

*Placement → Create Placement Event → + Add*. Named `{opportunity}-{event_type}-{event_date}`.

| Field | Notes |
|---|---|
| Placement Opportunity | Required |
| Event Type | PPT / Test / GD |
| Event Date & Time | Required |
| Venue | Free text (not linked to Venue Master or Venue Booking) |
| Attendance Mandatory | Default ticked. Nothing reads it. |

**Rule:** the event date must fall inside the opportunity's application window.

---

## 7. Applications

### 7.1 Student applies (portal)
*Student Portal → Placements* (`/student-portal/placement`). The menu item shows only when **Student Portal Settings → menu_placement** is on.

The page shows the student's placement profile, all **Open** opportunities (company, type, compensation, location, window), their own applications and any offer. **Apply** calls `apply_for_opportunity`.

### 7.2 Placement Application
Named by an auto number.

| Field | Notes |
|---|---|
| Student | Required. Plain text holding the Student Master ID. |
| Placement Opportunity | Required |
| Applied On | Set to now, read-only |
| Resume Used | Required attachment |
| Status | Applied / Shortlisted / Rejected (default Applied) |
| Remarks | |

**Rules the system enforces**
- One application per student per opportunity: "You have already applied for this opportunity."
- The portal accepts an application only while the opportunity is **Open**.
- The application must be inside the window: "Applications are closed for this opportunity."
- A student sees only their own applications (`slcm/security/student_scope.py`).

### 7.3 Shortlisting
**Shortlist Upload** stores a file against an opportunity (Uploaded On / Uploaded By are filled in). **Nothing reads the file**: the processing step is an empty stub. Set each application's Status to *Shortlisted* or *Rejected* by hand.

---

## 8. Placement Offer

*Search bar → Placement Offer → + Add*. Named `{student}-{opportunity}-OFFER`.

| Field | Notes |
|---|---|
| Student, Placement Opportunity | Required |
| Offered Role, Job Location, Compensation | Required |
| PPO | Yes / No (pre-placement offer) |
| Offer Status | Offered / Accepted / Declined |
| Decision Date | Set to today when status becomes Accepted or Declined and it is empty |

The student sees their offer as a banner on the portal page. The student cannot accept or decline from the portal.

---

## 9. Permissions

| DocType | slcm_Placement Officer | slcm_Student | System Manager |
|---|---|---|---|
| SLCM Company, Company Contact, Company Interaction, Placement Opportunity, Placement Event, Placement Offer, Shortlist Upload | read, write, create, delete | — | all |
| Student Placement Profile | read, write, create, delete | read, write, create (own only) | all |
| Placement Application | read, write, delete (no create) | read, create (own only) | all |

---

## 10. Troubleshooting

| Problem | Cause and fix |
|---|---|
| "Application End must be after Application Start" | Fix the window on the opportunity. |
| "Event date must be within the application period." | Move the event inside the opportunity's start and end. |
| "Applications are closed for this opportunity." | The current time is outside the window. Extend Application End. |
| "This opportunity is no longer accepting applications." | Status is not *Open*. |
| Student can't edit their profile | Profile Status is *Locked*. |
| Second opportunity / interaction for a company won't save | Both are named by the company. See Open questions. |

---

## 11. Open questions

1. **Student portal page looks broken.** `slcm/www/student-portal/placement.py` imports `nowdatetime` from `frappe.utils` (no such function) and calls `now()` without importing it. Confirm the page loads; it likely fails on import.
2. **One opportunity per company.** Placement Opportunity is named `format:{company}`. Is a second role / year from the same company meant to be a new record?
3. **One interaction per company.** Company Interaction is named by the company and Company is unique, so it cannot hold a history of calls. Intended?
4. **Shortlist Upload does nothing.** Should it parse the file and set applications to *Shortlisted* (as its docstring plans)?
5. **Eligibility is not checked.** Eligibility Criteria, Applicable Batches and CGPA are not compared with the student on apply.
6. **Placement Offer is not on the sidebar/workspace.** Add it? Should students accept / decline on the portal?
7. **Student is a text field** on Placement Application and Student Placement Profile (not a Link), so names are not validated and do not link to Student Master.
8. **Profile data is typed.** Programme, Batch Year and CGPA are not fetched from Student Master / results.
9. **Placement Event Venue** is free text and is not booked in Venue Bookings. Should it create a Venue Booking?
10. **No notifications** to students on shortlist, event or offer.
11. **Placement is left out of the Uniquad dashboards** on purpose (user rule). Confirm it should stay out.
12. **Workspace number cards are not shipped.** The workspace uses *Placement Applied*, *Placement Shortlisted*, *Placement Rejected*, but no Number Card of those names is in `fixtures/number_card.json` or the app. They show only if they exist in the database.

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| DocTypes | `slcm/slcm/doctype/{slcm_company, company_contact, company_interaction, student_placement_profile, placement_opportunity, placement_event, placement_application, shortlist_upload, placement_offer}` |
| Child / helper tables | `internship_record`, `skill`, `skill_child`, `placement_opportunity_child`, `placement_opportunity_setbyuser`, `applicable_batches_child`, `applicable_batches_setbyuser` |
| Portal page | `slcm/www/student-portal/placement.py`, `placement.html` (calls `slcm.www.student-portal.placement.apply_for_opportunity`) |
| Own-record scope for students | `slcm/security/student_scope.py`; wired in `hooks.py` `permission_query_conditions` and `has_permission` |
| Sidebar / workspace / icon | `slcm/workspace_sidebar/placement.json`, `slcm/slcm/workspace/placement/` **and** `fixtures/workspace.json` (fixture copy wins), `slcm/desktop_icon/placement.json` |

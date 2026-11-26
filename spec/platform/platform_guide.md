# Uniquad Platform: Cross-cutting Guide

**Applies to:** Uniquad (SLCM v16), as on disk in November 2026
**Who this is for:** System Managers and the Registrar's office who run the whole system (dashboards, roles, sign-in, audit), and developers who add modules, sidebars and icons.
**Where:** Desk → **Master** sidebar (*Insights & Tools*, *Users & Access*), **IT Team → Audit**, the desk home (desktop icons), and `/login`.

---

## 1. The platform at a glance

```
Sign in        /login (staff · faculty-student · parent tabs)   applicants: /nlsat/login, /pace/login
                 → role home page: staff → desk, faculty → /faculty-portal,
                   student → /student-portal, parent → /parent-portal
Every request  before_request: domain home redirect → API guard → login redirects
                 → portal role gate → admission web-form checks
Desk home      Desktop icons (folders: Admission, Academics, Examination Management,
                 Student Services, Campus & Support) → Workspace Sidebar per module
Data access    DocPerm / Custom DocPerm  +  row rules (permission_query_conditions, has_permission)
Manage access  Roles & Permissions page (DocTypes · Pages & Reports · Desktop Icons · Portals · Users)
Insight        Uniquad Overall Dashboard · Uniquad Dashboard · module dashboards · Data Entry Map
Audit          User Activity Log (every user action, 365 days)
```

---

## 2. Desktop icons and sidebars

### 2.1 How the desk home is built
- **Desktop icons** are JSON files in `slcm/desktop_icon/`. Each is one tile on the desk home.
- An icon with `icon_type: App` is a **folder**. An icon with `icon_type: Link` and `parent_icon` set sits **inside** that folder.
- A Link icon opens a **Workspace Sidebar** (`link_type: Workspace Sidebar`, `link_to` = sidebar name).
- Each icon has a **roles** table. Only users with one of those roles see it. **An icon with no roles is visible to everyone.**
- **Workspace Sidebars** are JSON files in `slcm/workspace_sidebar/`. Each item is a *Link* (DocType / Page / Report / Workspace) or a *Section Break* heading.
- Frappe syncs both folders on `bench migrate`.

### 2.2 Folders and what is in them

| Folder icon | Icons inside |
|---|---|
| **Admission** | Eligibility, Interview, Merit, Offer Letters, Scholarship, Test, PACE, FLE, Fee & Refund (sidebar *Admission Fee*), **Settings** (sidebar *Admission*) |
| **Academics** (AAD, AAD Staff, System Manager) | Programme Management, Attendance, Promotions, Student Registration |
| **Examination Management** | Examinations, Transcript Management |
| **Student Services** | Hostel Management, Placement, Student Portal |
| **Campus & Support** | Venue Bookings, IT Team, Helpdesk (Helpdesk app icon, grouped by patch) |
| (no folder) | Master |

Sidebars with no desktop icon: *Faculty Management* (has its own fixture icon with no roles), *Fees Management*, *INM*, *Reports*, *Settings*.

### 2.3 Fixture copies win
Some sidebars, icons and workspaces are **also** exported as fixtures. On migrate the fixture is imported last and overwrites the file version.

| Fixture | Records |
|---|---|
| `fixtures/workspace.json` | Every SLCM / Admission / PACE workspace except Student Portal, Master, FLE |
| `fixtures/workspace_sidebar.json` | Faculty Management, Fees Management, Admission Fee |
| `fixtures/desktop_icon.json` | Faculty Management |
| `fixtures/custom_html_block.json` | Examination Home, Attendance Home, Fees Home |

> When you change one of these, change the fixture copy too.

### 2.4 Desk behaviour added by Uniquad (`hooks.py` `app_include_js/css`)

| Script | What it does |
|---|---|
| `sidebar_toggle.js/.css` | On **dashboard pages** (first route segment ends in `dashboard`, plus `uniquad-roles-permissions`) the desk sidebar opens hidden, with a show/hide button before the breadcrumbs. All other pages keep the normal sidebar. Desktop widths only (≥ 768 px). Also pads single-column pages listed in the CSS. |
| `sidebar_fallback.js` | When a DocType is on several sidebars and Frappe picks none after a refresh, shows the sidebar last used (if it lists the route), else the first that does. |
| `student_workspace_redirect.js` | Opening the Student Enrollment list as a student redirects to the student's own record. |
| `bulk_email_dialog.js`, `tree_route_filters.js` | Bulk email dialog; ERPNext Company → tree views open for that company. |

### 2.5 Settings sidebar (`workspace_sidebar/settings.json`, module Admission)

| Section | Items |
|---|---|
| (top) | Dashboard (page `admission-dashboard`), Applicant User States (report *Applicant Registration Status*), Institution Settings, Campus |
| Admission Settings | Admission Year, Academic Year, Programme, Reservation Policy (*Programme Reservation Policy*), Admission Cycle, Applicant Portal Settings (*Applicant Portal Config*), Portal Announcement, Portal Important Dates (*Important Dates*) |
| Report & Logs | Merit Report (*Overall Merit Report*), Seat Availability Report, Scholarship Utilization Report, Application Trends, Applicant Fee Payments (*Applicant Fee Payment Status*), Student Selection Report, Admission Log (*Admission Audit Log*), Admission Cycle Log (*Admission Cycle Audit Log*) |

### 2.6 Reports sidebar (`workspace_sidebar/reports.json`, module Admission)
Overall Merit Report, Seat Availability Report, Scholarship Utilization Report, Primary Program Choice, Applicant Fee Payment Status, Fee Assignment (*Fee Assignment Dashboard*). All six reports exist under `slcm/admission/report/`.

---

## 3. Dashboards and insight pages

| Page (route) | What it is | Roles (Page JSON) | Linked from |
|---|---|---|---|
| **Uniquad Overall Dashboard** (`uniquad-overall-dashboard`) | Every module on one page. Tabs: **Dashboard** (filters → headline funnel *Total › Submitted › Merit selected › Offer accepted › Enrolled* → one section of cards per module), **Timeline** (one person start to end), **Admission Funnel**. Cards drill into tables with CSV export. | System Manager, slcm_Registrar, slcm_Programme Chair, Programme Chair, slcm_Academic Incharge, Academic Admin, Academics User, Campus Admin, Admission Admin, Admission Manager | Master → Insights & Tools |
| **Uniquad Dashboard** (`uniquad-dashboard`) | Operations dashboard with a module sidebar, global search, filters, overview KPIs, sections (incl. Helpdesk Tickets and Venue Bookings), drilldown previews and a student profile (`/desk/uniquad-dashboard/student/<id>`). | Same as above **plus slcm_Faculty** | Master → Insights & Tools |
| **Programme Dashboard** (`programme-dashboard`) | Count cards for academic calendar, programme structure, students, classes, timetable and promotion runs; drilldown, records view, CSV export | System Manager, AAD, AAD Staff, slcm_Programme Chair, slcm_Registrar | Programme Management → Dashboard |
| **SLCM Data Entry Map** (`slcm-data-map`) | Modules in the order data must be entered (Master → Programme → Admission → Registration → Attendance → Exams → Fees → IT → Venue → Promotions → Transcripts → PACE → FLE), built from each module's Workspace Sidebar, with record counts | System Manager, slcm_Registrar, slcm_Programme Chair, slcm_REGO Officer | Master → Insights & Tools |
| **SLCM Module Flow** (`slcm-module-flow`) | Static, hand-written diagram of module flow with links to lists and pages | same as Data Entry Map | No sidebar link (only from the wiki page) |
| **SLCM Wiki** (`slcm-wiki`) | Renders a Markdown file `docs/SLCM_WIKI.md` | same as Data Entry Map | No sidebar link |

Module dashboards (exam, attendance, fee, RFID agent) are covered in their module specs.

**Security rule for the two Uniquad dashboards:** every number and row is read through `frappe.get_list`, so DocType permissions, User Permissions and the row rules in section 5 apply. The browser sends only card / drilldown keys; DocTypes, fields and sorts come from server-side registries. A card whose DocType the user cannot read is hidden. Placement and Hostel are not on either dashboard.

---

## 4. Roles & Permissions page

*Master → Users & Access → Roles & Permissions* (`/desk/uniquad-roles-permissions`). **System Manager only.** Opens with the desk sidebar hidden.

Pick a role on the left, then a tab:

| Tab | What you set | Stored as |
|---|---|---|
| **Document Types** | read / write / create / delete / submit / cancel / amend on every non-child DocType in modules SLCM, Admission, PACE. Tags show module, the sidebar menus it appears in, "Row rules" (has a row-level hook) and "Customised". **Reset** restores the shipped permissions. | **Custom DocPerm**, level 0, not if-owner (same rows as Role Permission Manager) |
| **Pages & Reports** | Which roles may open each Page / Report of those modules | **Custom Role** (the shipped Page/Report JSON stays untouched); Reset deletes it |
| **Desktop Icons** | Roles on each slcm icon and each icon inside an slcm folder | The icon's own roles table |
| **Portals** | Which roles may open the Student / Faculty / Parent portal | Global default `uniquad_portal_roles` |
| **Users (n)** | Users holding the role: assign / unassign | User roles |

Buttons: **New Role** (name, Desk access tick), **New Staff User** (email, first / last name, roles; System User; Frappe's welcome email with set-password link).

**Rules the system enforces**
- Ticking a permission ticks what it needs (write → read; submit → write; cancel → submit; amend → cancel). Unticking one unticks what depends on it.
- Protected roles (Administrator, Guest, All, Desk User, System Manager) cannot be managed here.
- Portal roles (slcm_Student, slcm_parent, Student, Applicant, PACE Applicant) have **fixed** document permissions; only their portal access can change. They cannot be given to a new staff user.
- An item with no roles is open to everyone. Unticking a role on such an item restricts it to **all other Uniquad roles plus System Manager**. System Manager is always kept.
- A role can be removed from the list only if it has no grants anywhere and is not an `slcm_*` role. The Role record itself stays.
- Role names are matched case-insensitively.

**Which roles are listed:** every role with a grant on Uniquad DocTypes / pages / icons / portals, every `slcm_*` role, and roles added with New Role (global default `uniquad_access_extra_roles`).

> In developer mode, saving a Desktop Icon's roles also rewrites `slcm/desktop_icon/*.json`.

---

## 5. Access control in code

### 5.1 Row-level rules (`hooks.py`)

| DocTypes | Rule | Code |
|---|---|---|
| Student Master | Workflow roles see only students at their registration stage (e.g. Hostel Admin / Warden → *Pending Residences*, IT Admin → *Pending IT* / *Final Verification REGO*). System Manager, slcm_Registrar, Accounts User, AAD, AAD Staff see all. Faculty / Programme Chair see active students of their classes. | `slcm/permissions.py` |
| Time Table, Attendance Session, Student Attendance, Attendance Log, Attendance Summary, Student Attendance Condonation, FA MFA Application | Faculty see only their classes | `slcm/permissions.py` |
| Venue Booking | Admins (System Manager, slcm_Registrar, AAD, AAD Staff) see all; others see only their own | `slcm/permissions.py` |
| Applicant, Entrance Test Provider, Seat Allocations, Interview Staff / Seat Allocation, Offer Letter, Scholarship Application, Applicant Document / Notification / Payment Receipt / Campus Preference | Applicants see only their own | `slcm/permissions.py`, `slcm/security/applicant_access.py` |
| Student Placement Profile, Placement Application, Grade Appeal, Re Exam / Improvement Exam Registration, Fee Demand, Fee Receipt, Stipend Payment, Transcript Request, Student Leave Applications, Office Hours Attendance, Attendance Summary, FA MFA Application, Venue Booking, Student Master | A user whose only route in is a student role (slcm_Student / Student) sees only their own records | `slcm/security/student_scope.py` |

### 5.2 Request gates (`before_request`, in this order)

| Step | Code | What it does |
|---|---|---|
| 1 | `slcm/utils/domain_routing.py` `redirect_domain_home` | On a domain's home page (`/`, GET only), redirects to the page set for that domain in **Site Domain Settings** (e.g. an admissions domain → `/nlsatadmissions`). New domains the site is opened on are added to the table by a background job. Fails open. |
| 2 | `slcm/security/api_guard.py` | Website users may call admission / offer / fee / staff methods only if a portal page uses them (allow-list). Applicant-only accounts cannot use Frappe's generic write APIs. `admission_api_guard: "log"` in site_config turns enforcement into log-only. |
| 3 | `slcm/utils/auth_routing.py` `intercept_login` | Guests on portal pages go to the right login (`/login?tab=faculty-student`, `/login?tab=parent`, PACE / NLSAT login with `redirect-to`). Signed-in applicants opening the application form go to their existing application. `/login` picks its tab from the `logged_out_from` cookie. |
| 4 | `slcm/utils/portal_access.py` `guard` | A signed-in user opening `/student-portal`, `/faculty-portal` or `/parent-portal` without an allowed role gets "Not Permitted". Administrator is exempt. Defaults: slcm_Student + Student / slcm_Faculty / slcm_parent. |
| 5 | `slcm.admission.portal_application_web_form.slcm_before_request` | Admission web-form checks |

### 5.3 Sign-in and home pages

| Item | Rule |
|---|---|
| `/login` tabs | **staff** (password, email link, Google if enabled) → desk; **faculty-student** (Google only, switched on per portal settings) ; **parent** (password, Google if allowed). Code: `slcm/utils/login_page.py`. |
| `on_login` | Faculty and students cannot use a password (staff exempt). Accounts with no staff / faculty / student / parent record are refused on `/login`. NLSAT candidates sign in only on their own portal. |
| `on_session_creation` | Google sign-ins checked against portal settings and allowed domain, and linked to the Faculty / Student Master record. |
| Home page | `role_home_page`: slcm_Faculty → `/faculty-portal`, slcm_Student → `/student-portal`, slcm_parent → `/parent-portal`. Administrator always goes to the desk. |
| Logout | Sets cookie `logged_out_from` (desk / pace / admission / student / faculty / parent, from the referrer or roles) so the next `/login` opens the right tab or page. |

---

## 6. User Activity Log (audit trail)

*IT Team → Audit → User Activity Log*. **System Manager only** (read, delete). Read-only. Kept **365 days** (change in *Log Settings*).

| Field | Notes |
|---|---|
| User, Full Name | Who acted |
| Action | Login, Login Failed, Logout, Create, Update, Submit, Cancel, Update After Submit, Delete, Rename, View, Export, Print, Download, Action |
| Document Type / Document | What was touched. **Open Document** button. |
| Source | Web / Background Job |
| Summary, Method / Path | Short text and the called method |
| Changes | JSON: changed fields old → new, child-table rows added / removed / changed; or the method's arguments |
| IP Address, User Agent | |

**What is recorded**

| Action | Trigger |
|---|---|
| Login / Logout | Session hooks (only logins that passed the routing checks) |
| Login Failed | Frappe's failed-login Activity Log, including unknown user names |
| Create / Update / Submit / Cancel / Update After Submit / Delete / Rename | Every DocType (`doc_events "*"`). Updates without a real change are skipped. Password fields are masked. |
| Export / Print / Download | Frappe's Access Log (report / list exports, PDFs, files) |
| View | A user opening a record in the desk form |
| Action | Any `slcm.*` server method a user calls. Arguments whose name contains password, pwd, secret, token, otp, account_number or api_key are masked. |

**Not recorded:** Guest, scheduler jobs, console, install / migrate / patches, child tables, failed requests (HTTP ≥ 400), and system / log DocTypes (Version, Error Log, Email Queue, Communication, Desktop Icon, Number Card, …) plus Attendance Log, RFID SQL Punch Log and Marks Import Log Detail. Logging never stops the user's action; failures go to the Error Log.

> "User Activity Log" must stay in `ignore_links_on_delete` in `hooks.py`, or no logged record could be deleted.

---

## 7. Adding a new module (checklist)

- [ ] DocTypes in module SLCM (or Admission / PACE) so they appear on Roles & Permissions
- [ ] `slcm/workspace_sidebar/<module>.json` with Home + links
- [ ] `slcm/desktop_icon/<module>.json`: `icon_type: Link`, `link_type: Workspace Sidebar`, `parent_icon` = the folder, **roles set** (no roles = everyone)
- [ ] Workspace under `slcm/slcm/workspace/<module>/`, and update `fixtures/workspace.json` if the workspace is a fixture
- [ ] Row rules in `hooks.py` if students or faculty must see only their own records
- [ ] Add the module's cards to the Uniquad dashboards' registries if it should show there
- [ ] A new full-width Page: pad its own content, or add it to `sidebar_toggle.css`

---

## 8. Troubleshooting

| Problem | Cause and fix |
|---|---|
| Icon missing on the desk home | User lacks every role on the icon (or its folder). Check *Roles & Permissions → Desktop Icons*. |
| Icon visible to everyone | Its roles table is empty. Add roles. |
| Sidebar change lost after migrate | A fixture copy (section 2.3) overwrote it. Edit the fixture too. |
| Empty sidebar after refresh | DocType on several sidebars; `sidebar_fallback.js` picks one. Open the module from its icon once. |
| "Your account does not have access to the Student Portal" | The user's roles are not allowed on *Roles & Permissions → Portals*. |
| Faculty / student cannot sign in with a password | By design: Google only. |
| Dashboard card missing | The user cannot read that card's DocType. |
| Cannot delete a record ("linked with User Activity Log") | `User Activity Log` was removed from `ignore_links_on_delete`. Put it back. |

---

## 9. Open questions

1. **Settings icon points at a sidebar that is not shipped.** `desktop_icon/settings.json` links to Workspace Sidebar **Admission**, but there is no `admission.json` in `slcm/workspace_sidebar/`; the shipped file `settings.json` is named **Settings** and no icon opens it. Which is correct?
2. **Reports sidebar has no icon.** `workspace_sidebar/reports.json` is not opened by any desktop icon. Is it still used?
3. **Faculty Management icon has no roles** (fixture), so everyone sees it.
4. **SLCM Wiki has no content.** It reads `apps/docs/SLCM_WIKI.md` (outside the app), which does not exist, so the page is empty. Remove the page or ship the file?
5. **SLCM Module Flow** is hand-written and not linked from any sidebar. Keep it, or rely on the Data Entry Map?
6. **slcm_Faculty has no desk access**, yet is a role on Uniquad Dashboard. Faculty-only users cannot open it.
7. **Data Entry Map** has no Hostel or Placement module. Intended?
8. **User Activity Log retention vs volume.** Every View and every `slcm.*` call is logged. Is 365 days the agreed retention, and should other roles (e.g. slcm_IT Admin, who has the IT Team sidebar) be able to read it? Today only System Manager can.
9. **Portal roles default** includes the plain `Student` role. Is that role still used?

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| Desktop icons / sidebars | `slcm/desktop_icon/`, `slcm/workspace_sidebar/`, fixtures in `slcm/fixtures/`, fixture filters in `hooks.py` |
| Helpdesk icon grouping | `slcm/patches/v2_0/group_helpdesk_desktop_icon.py` |
| Sidebar scripts | `slcm/public/js/sidebar_toggle.js`, `sidebar_fallback.js`, `slcm/public/css/sidebar_toggle.css` (bump the `?v=` in `hooks.py` when changed) |
| Dashboards | `slcm/slcm/page/{uniquad_overall_dashboard, uniquad_dashboard, programme_dashboard, slcm_data_map, slcm_module_flow, slcm_wiki}` |
| Roles & Permissions | `slcm/slcm/page/uniquad_roles_permissions/` |
| Portal gate | `slcm/utils/portal_access.py` |
| Login routing, logout cookie, Administrator home | `slcm/utils/auth_routing.py` |
| Domain home redirects | `slcm/utils/domain_routing.py`, DocTypes Site Domain Settings / Site Domain Route |
| Sign-in page rules | `slcm/utils/login_page.py`, `slcm/www/login.py`; tests `slcm/tests/test_login_page.py` |
| API allow-list for website users | `slcm/security/api_guard.py` |
| Row rules | `slcm/permissions.py`, `slcm/security/student_scope.py`, `slcm/security/applicant_access.py` |
| Audit log | `slcm/utils/activity_log.py`, `slcm/slcm/doctype/user_activity_log/`; hooks: `doc_events "*"`, `Activity Log`, `Access Log`, `on_session_creation`, `on_logout`, `after_request`, `default_log_clearing_doctypes`, `ignore_links_on_delete` |

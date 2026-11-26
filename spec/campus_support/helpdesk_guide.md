# Campus & Support: Helpdesk and IT Team Guide

**Applies to:** Uniquad (SLCM v16) with the Helpdesk app, as on disk in November 2026
**Who this is for:** Helpdesk agents and team leads, AAD staff who raise tickets, the IT team (RFID, ID cards), and developers who maintain the Uniquad side of the Helpdesk integration.
**Where:** Desk → **Campus & Support** (Helpdesk, IT Team, Venue Bookings). Students: **Student Portal → Helpdesk**. Faculty: **Faculty Portal → Helpdesk**. Applicants: `/nlsat/helpdesk`, `/pace/helpdesk`.

---

## 1. The flow at a glance

```
Raise         Student / faculty portal (Helpdesk iframe) · applicant portal · email · AAD from desk
                 → HD Ticket (Ticket Type + Type of Issue)
Route         before_insert: Uniquad fills programme / year / type from the sender
                 core Helpdesk: Type of Issue team → programme/year rule → type's team
                 Uniquad fallback: no team on an email ticket → "PACE Team"
Validate      Facilities tickets need a preferred visit slot (next 24 h, 09:00–20:00)
Assign        Team round-robin → agent gets a styled "Ticket assigned" notification
Escalate      Every 5 min: no first response within the team's window
                 → add the next agent, email both, log on the ticket (up to max hops)
```

The Helpdesk app (`apps/helpdesk`) owns tickets, teams, SLAs and the agent UI. This guide covers what **Uniquad adds** on top, plus the IT Team area.

### Key ideas

| Term | Meaning |
|---|---|
| **HD Ticket** | A support ticket (Helpdesk app). |
| **Ticket Type** | Top-level category, e.g. Academics, Facilities, Finance, IT, PACE, Technical Issue. |
| **Type of Issue** | A sub-category of a Ticket Type (DocType **HD Ticket Type Of Issue**, named `{ticket_type}-{issue_name}`), with an optional fixed team. |
| **HD Team** | A group of agents (Helpdesk "agent group"). |
| **Hop** | One automatic escalation: the ticket is given to the next agent in the team. |

---

## 2. Where things are

### 2.1 Desktop folders

| Folder (`slcm/desktop_icon/`) | Contains | Shown to |
|---|---|---|
| **Campus & Support** (`campus_&_support.json`) | Venue Bookings, IT Team, **Helpdesk** (the Helpdesk app's own icon, moved into this folder by patch `group_helpdesk_desktop_icon`) | slcm_Registrar, slcm_Registration Officer, Campus Admin, Admission Admin, slcm_Faculty, slcm_IT Admin, System Manager, Agent, AAD, AAD Staff |
| **Student Services** (`student_services.json`) | Hostel Management, Placement, Student Portal | slcm_Registrar, slcm_Registration Officer, Campus Admin, Admission Admin, slcm_Hostel Admin, slcm_Hostel Warden, slcm_Placement Officer |

The **Helpdesk** icon roles are set by patch `aad_helpdesk_access`: System Manager, Agent, slcm_Faculty, AAD, AAD Staff are added to its existing roles.

### 2.2 IT Team sidebar (`slcm/workspace_sidebar/it_team.json`)
Desktop icon **IT Team** (folder Campus & Support), shown to `slcm_IT Admin` and `System Manager`.

| Section | Items |
|---|---|
| (top) | Home (IT Team workspace) |
| RFID Management | RFID Device, Device Mapping (RFID Device Room Mapping), RFID Card Management (page `rfid-mapping`), RFID Attendance Report, RFID Agent Dashboard (page `rfid-sql-agent-dashboard`), RFID Configuration (RFID SQL Agent Settings) |
| ID Card Management | Generate ID Cards (ID Card Generation Tool), ID Card Generation, ID Card Template |
| Student Management | Student Master, Student RFID Card |
| Logs & Audit | ID Card Generation Log, ID Card Print Log, RFID Punch Log (RFID SQL Punch Log), Student Map Log (RFID Student Map Log), RFID UID Change Log |
| Audit | User Activity Log (see the Platform guide) |

The IT Team workspace adds number cards (Active Students, Total / Active / Pending (Draft) / Cancelled ID Cards, Print Log Entries) and two charts (ID Card Status Distribution, ID Cards Generated Over Time).

---

## 3. Raising a ticket

| Who | Where | How |
|---|---|---|
| Student | *Student Portal → Helpdesk* (`/student-portal/support`) | The Helpdesk customer portal in an iframe: `/helpdesk/my-tickets`, `/helpdesk/my-tickets/new`, or one ticket (`?ticket=`). The page mirrors the iframe's route into its own URL so a refresh keeps the place. |
| Faculty | *Faculty Portal → Helpdesk* (`/faculty-portal/support`) | Helpdesk in an iframe. |
| NLSAT / PACE applicant | `/nlsat/helpdesk`, `/pace/helpdesk` (page `www/admission/helpdesk`) | Needs role Applicant or PACE Applicant (or System Manager). Guests are sent to their portal login. |
| AAD / AAD Staff | Helpdesk app as a customer | Users with AAD / AAD Staff get the **HD Customer** role automatically (User validate hook). They see only tickets they raised. |
| Anyone | Email to the support inbox | Ticket created by Helpdesk from the email. |

### Ticket types and issues (seeded by patch)

| Ticket Type | Types of Issue |
|---|---|
| Academics | Attendance Discrepancy, Certificates - Letters, Examination, Learning Material, Projects, Viva, FA, MFA, Others |
| Facilities | Carpentry, Electrical, House Keeping, Plumbing, Security, Others |
| Finance | Fees, Others |
| IT | Admin Portal, Gsuite, Group Creation, ID Card, Internet Connectivity, Learning Platform, Microsoft Office, Online Library Access, Others |
| PACE | Admission, Academics, Degree and Certificate, Examination/Result, Fee-related, Grievance, Technical Issues, Transcripts |

Edit the list in **HD Ticket Type Of Issue** (Issue Name, Ticket Type, Team, Enabled).

---

## 4. Routing a ticket to a team

Order of checks on a new ticket:

| Step | Owner | What happens |
|---|---|---|
| 1. Prefill (email tickets only) | Uniquad `prefill_student_context_before_insert` | If the sender matches a **Student Master** (by user, email or official email): fills programme and current year. A PACE student gets Ticket Type *PACE* and the PACE programme. Otherwise, if the sender owns a **PACE Application**: Ticket Type *PACE* and its programme. Portal tickets are skipped (the portal form fills these). |
| 2. AAD technical issues | Uniquad `route_aad_technical_issue` | Ticket Type *Technical Issue* raised by an AAD / AAD Staff user → team **SLCM Technical Team** (if that team is enabled). |
| 3. Core routing | Helpdesk `set_team_from_ticket_type` | Type of Issue's own team → NLSAT technical-issue team → programme / year rule (**PACE Ticket Type Assignment Rule**, **HD Ticket Type Assignment Rule**) → the Ticket Type's team. |
| 4. Email fallback | Uniquad `apply_default_email_team` | Still no team and not from the portal → **PACE Team**. |

**SLCM Technical Team** is created once by patch `aad_helpdesk_access` with two technical-team members as agents (names are hard-coded in the patch). Membership is then managed on the HD Team form.

---

## 5. Facilities tickets: preferred visit slot

For Ticket Type **Facilities**, the ticket must have **Preferred Visit Date** and **Preferred Visit Time**.

**Rules the system enforces**
- Both are mandatory.
- The slot must be between now and the next *N* hours (default 24).
- The time must be within working hours (default 09:00–20:00).

Settings: **HD Settings → Facility Visit Scheduling** (`facility_visit_window_hours`, `facility_visit_hours_start`, `facility_visit_hours_end`; fields from the Helpdesk app).

---

## 6. Assignment notification

When a ticket is assigned, Frappe's default notice ("… assigned a new task HD Ticket …") is replaced with a ticket card: subject *"Ticket #N assigned to you: <subject>"*, email header *"New Ticket Assigned: #N"*, a link to `/helpdesk/tickets/<N>`, body from `slcm/templates/emails/helpdesk_ticket_assigned.html`. Un-assignment notices are unchanged.

---

## 7. SLA escalation

Runs **every 5 minutes** (`run_sla_escalation`).

### 7.1 Team settings (HD Team)

| Field | Meaning |
|---|---|
| Enable SLA Escalation | Switch per team (team must not be disabled) |
| Escalation After (hours) | Grace period. Fractions allowed (0.5 = 30 min). Default 1 h if empty or 0. |
| Escalation Max Hops | Stop after this many hops. Default 3. |
| Escalation Users | Ordered list of agents to escalate to. If empty, the team's Users list is used (and an Error Log note is written). |
| Escalation email templates (new agent / previous agent / max hops) | Optional per-team templates. Defaults: *HD Ticket SLA Escalation - New Agent / - Previous Agent / - Max Hops Reached*. |
| Notify On Max Hops | Email assignees when the limit is reached. Off by default. |

### 7.2 What it does
A ticket qualifies when it is in the team, its status category is *Open*, and it has **no first response**.

- The clock starts at creation, or at the last hop.
- Only **working time** counts: Saturdays, Sundays and Active *Holiday* entries in the **Institutional Calendar** are skipped.
- When the grace period is over, the next agent in the list who has not been tried and whose user is enabled is **added** as an assignee. Earlier agents stay assigned.
- The ticket's Escalation Count, Last Escalated On and Escalated From Agents are updated, and a line is written to the ticket's Activity tab.
- The new agent and all other assignees are emailed (unless **HD Settings → Skip Email Workflow** is on).
- At the hop limit, or when no untried agent is left, the ticket is logged as *"needs manual action"* (at most once per 6 hours per ticket), and assignees are emailed only if Notify On Max Hops is on.

---

## 8. Agent views for AAD

AAD / AAD Staff users who are also Helpdesk agents get two pinned views in the agent sidebar: **Student Tickets** (assigned to me) and **My Raised Tickets** (raised by me). They are added or removed when the User or HD Agent record changes (and by patch `aad_helpdesk_views`).

---

## 9. IT Team: RFID and ID cards (summary)

| Area | DocTypes / pages | Notes |
|---|---|---|
| RFID readers | RFID Device (Device ID, reader label, type Classroom / Entry Gate / Other, Current Venue), RFID Device Room Mapping (device → Venue Master, effective dates) | Overlapping mappings for one device are blocked. Mapping suggestions: `suggest_venue_mappings`. |
| RFID cards | Student RFID Card (Student, RFID UID unique, status Active / Blocked / Lost / Damaged / Replaced), RFID UID Change Log, RFID Student Map Log | A UID cannot be on two students. |
| Punches | RFID SQL Punch Log, RFID Agent Dashboard, RFID Configuration | Fed by the campus RFID agent; see `spec/attendance/rfid_sql_agent_guide.md`. |
| ID cards | ID Card Template (designer, card types Student / Faculty / Driver / Visitor / Non-Faculty, CR80), ID Card Generation Tool (bulk by academic year / programme / batch / section, ZIP download, print layout), ID Card Generation (one card: Draft / Generated / Printed / Cancelled / Expired / Error, QR verification), ID Card Generation Tool Log, ID Card Print Log | Only one bulk run at a time. Students who already have an active card are skipped unless *Regenerate Existing Cards* is ticked. |

---

## 10. Troubleshooting

| Problem | Cause and fix |
|---|---|
| "Preferred Visit Date and Time are mandatory for Facilities tickets." | Fill both fields. |
| "Preferred Visit Date/Time must be within the next 24 hours from now." | Pick a slot inside the window (see HD Settings). |
| Email ticket lands in PACE Team | The sender matched no Student Master / PACE Application, and no rule gave a team. Fix the Type of Issue team or assignment rules. |
| AAD user's Helpdesk icon missing | User lacks HD Customer. Save the User (the hook adds it) or run patch `aad_helpdesk_access`. |
| Tickets never escalate | Team has Enable SLA Escalation off, the ticket has a first response, or the window falls on a weekend / holiday. |
| Escalation emails not sent | Template missing, user disabled / no email, or Skip Email Workflow on. Check Error Log ("HD Ticket SLA Escalation: …"). |

---

## 11. Open questions

1. **Duplicate DocType name.** `HD Ticket Type Assignment Rule` exists in both `slcm/slcm/doctype/` (module SLCM, 3 fields) and the Helpdesk app (module Helpdesk, 4 fields). Which one is meant to be installed? The slcm copy looks like a leftover.
2. **Leftover folder:** `slcm/slcm/doctype/hd_ticket_type_of_issue_assignment_rule/` has only `__pycache__` (removed DocType). Safe to delete?
3. **Hard-coded team members** in patch `aad_helpdesk_access` (two named users). Should this come from settings?
4. **Default email team is "PACE Team"** for every unrouted email ticket, including non-PACE senders. Intended?
5. **Escalation adds agents but never removes them.** Tickets can collect many assignees. Intended (the code says yes)?
6. **Profile link mismatch:** the Student Portal profile page links to `/student-portal/helpdesk`, but the route is `/student-portal/support`.
7. **Faculty portal iframe** opens `/helpdesk` (agent UI) rather than `/helpdesk/my-tickets`. Confirm faculty are meant to act as customers or agents.
8. **Helpdesk app is a customised fork** (`helpdesk/api/nls_student.py`, NLS fields on HD Ticket / HD Team / HD Settings). This guide covers only the slcm side; the fork needs its own spec.

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| Prefill, AAD routing, email-team fallback, assignment notification | `slcm/api/helpdesk_assignment.py` |
| SLA escalation (scheduler `*/5 * * * *`) | `slcm/api/helpdesk_escalation.py` |
| Facilities visit slot | `slcm/api/helpdesk_facility_visit.py` |
| AAD agent views | `slcm/api/helpdesk_views.py` |
| HD Customer for AAD | `slcm/api/user_events.py` `grant_helpdesk_customer_role` |
| Hooks | `hooks.py` doc_events: HD Ticket (before_insert, before_validate, validate), Notification Log (before_insert), User, HD Agent; `scheduler_events` cron |
| Type of Issue DocType and seed | `slcm/slcm/doctype/hd_ticket_type_of_issue/`, patches `migrate_type_of_issue_to_link_doctype`, `update_academics_issue_types` |
| Icon / roles / team setup | patches `group_helpdesk_desktop_icon`, `aad_helpdesk_access`, `aad_helpdesk_views`, `helpdesk_reply_email_template` (all `slcm/patches/v2_0/`) |
| Portal pages | `slcm/www/student-portal/support.*`, `slcm/www/faculty-portal/support.*`, `slcm/www/admission/helpdesk.*` |
| Email templates | `hooks.py` fixtures (Email Template) |
| Custom fields on HD Ticket / HD Ticket Type | owned by the Helpdesk app (`helpdesk/fixtures/`); slcm excludes them from its Custom Field fixture |
| IT Team sidebar / workspace / icon | `slcm/workspace_sidebar/it_team.json`, `slcm/slcm/workspace/it_team/` **and** `fixtures/workspace.json` (fixture copy wins), `slcm/desktop_icon/it_team.json` |

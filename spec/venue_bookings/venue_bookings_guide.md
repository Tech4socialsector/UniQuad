# Venue Bookings: User Guide

**Applies to:** Uniquad (SLCM v16), as on disk in November 2026
**Who this is for:** The Registrar's office and Academic Affairs (AAD) staff who set up venues and allot bookings; faculty and students who request rooms.
**Where:** Desk → **Campus & Support → Venue Bookings**. Faculty: **Faculty Portal → Venue Booking**. Students: **Student Portal → Venue Booking**.

---

## 1. The flow at a glance

```
1. Masters       Building · Floor · Venue Type · Venue Amenity → Venue Master
                   (capacity, amenities, which roles may book it)
2. Request       Faculty / student / staff creates a Venue Booking  → status Pending Allotment
                   (optionally recurring: one booking per date)
                   → email to Registrar + System Manager users
3. Decide        Admin: Allot / Reject / Cancel  → email to the requester
4. Changes       Swap request (student) → Approve / Reject Swap
                 Admin "Swap Venue" between two bookings
5. Reports       Weekly / Monthly Venue Booking, Room Availability Checker
```

A **Pending Allotment** booking already holds the venue: nobody else can book the same venue for an overlapping time.

### Key ideas

| Term | Meaning |
|---|---|
| **Venue Master** | A bookable room or space. The same records are used by class timetables and exams. |
| **Venue Booking** | One request for one venue for one time slot. Named `VB-{YY}-{###}`. |
| **Blocking status** | *Pending Allotment* and *Allotted*. Only these block the venue. |
| **Series** | A recurring booking: the first booking plus one booking per extra date, each with *Parent Booking* set. |
| **Admin** | System Manager, Administrator, `slcm_Registrar`, `AAD`, `AAD Staff`. |

---

## 2. Where things are

### 2.1 Sidebar (`slcm/workspace_sidebar/venue_bookings.json`)

| Section | Items |
|---|---|
| (top) | Home, Venue Booking |
| Configuration & Scheduling | Venue Type, Building, Floor, Amenities (Venue Amenity), Venue (Venue Master), Time Table |
| Reports | Room Availability Check, Weekly Venue Booking, Monthly Venue Booking |
| Notification Settings | Email Templates |

### 2.2 Workspace
Number cards: Total / Pending / Approved / Rejected / Cancelled Venue Bookings, Total Rooms. Shortcuts for masters, bookings by status (Pending Allotment, Allotted, Rejected, Cancelled), Room Master, Time Table and the three reports.

### 2.3 Desktop icon (`slcm/desktop_icon/venue_bookings.json`)
**Venue Bookings** sits inside the **Campus & Support** folder. Shown to `slcm_Registrar`, `slcm_Registration Officer`, `Campus Admin`, `Admission Admin`, `slcm_Faculty`.

---

## 3. Setting up venues

### 3.1 Small masters

| DocType | Fields |
|---|---|
| Venue Type | Venue Type Name (unique), Is Active |
| Building | Building Name (unique), Is Active |
| Floor | Floor Name (unique) |
| Venue Amenity | Amenity Name (unique) |

### 3.2 Venue Master
*Venue Bookings → Venue → + Add*. Named by *Venue Name/Number*.

| Field | Notes |
|---|---|
| Venue Name/Number | Required, unique |
| Venue Code | |
| Venue Type | Required |
| Is Active | Default ticked. An inactive venue cannot be booked. |
| Building, Floor | Links |
| Capacity | Required |
| Venue Amenity | Multi-select, required |
| **Allowed Roles** (table) | Required. Only users holding one of these roles see the venue in the booking form. System Manager sees all. |

Everyone can read Venue Master, Venue Type, Building and Floor (`All` read).

---

## 4. Requesting a booking

### 4.1 From the desk
*Venue Bookings → Venue Booking → + Add*

| Field | Notes |
|---|---|
| Event / Purpose | Required |
| Venue Type | Required |
| Expected Attendees | Must be above 0 if given |
| Filter By Expected Occupancy | When ticked, the Venue list shows only venues with capacity ≥ attendees |
| Venue | Required. List shows active venues of the type, allowed for your roles, and marks booked ones. |
| Capacity, Building, Floor | Filled from the venue |
| Start / End Date & Time | Required |
| Status | Read-only. Always *Pending Allotment* on a new booking. |
| Recurring Booking | Tick, then Repeat Frequency (Daily / Weekly / Monthly), Repeat Until, and for Weekly the weekdays |
| Requester Type / Name, Student | Filled from the logged-in user (Student / Faculty / Staff / Other by role). A student's Student Master is linked, and batch, academic year, level fill in. |
| Description / Remarks, Supporting Document | |

**Rules the system enforces**
- The start cannot be in the past.
- The end must be after the start.
- The venue must be active.
- The venue must be free: no other *Pending Allotment* or *Allotted* booking may overlap. "Venue … is already booked during this period (Ref: …)".
- Recurring: frequency and Repeat Until are required; Repeat Until cannot be before the start; Weekly needs at least one weekday.
- Only an admin may change Status on an existing booking.

**What saving does**
- Emails the users with role `slcm_Registrar` or `System Manager` (template *Venue Booking - New Request (Admin)*), with a link to the booking.
- For a recurring booking, creates one more booking per date up to Repeat Until. Each is its own *Pending Allotment* booking needing its own approval. Dates that clash are **skipped**, and a message gives the number created and skipped.

### 4.2 From the Faculty Portal
*Faculty Portal → Venue Booking*. Faculty see their own bookings (last 40) and the active venues, and submit Event, Venue Type, Room, Start, End, Expected Attendees, Reason. Requester Type is *Faculty*. The same desk rules apply.

### 4.3 From the Student Portal
*Student Portal → Venue Booking*. Students see their bookings (last 100) with counts by status and any swap history. They can:
- **Book**: Event, Venue Type, Venue, Start, End, Reason, Expected Attendees, Attachment (`submit_venue_booking`);
- **Cancel** their own booking while it is *Pending Allotment* (`cancel_venue_booking`);
- **Update the attachment** while it is *Pending Allotment* (`update_venue_booking_attachment`).

---

## 5. Deciding a booking (admins)

### 5.1 On the form

| Button | When | Result |
|---|---|---|
| **Allot** | *Pending Allotment* | Status *Allotted*, admin remarks saved |
| **Reject** | *Pending Allotment* | Status *Rejected* |
| **Cancel Booking** | *Pending Allotment* or *Allotted* | Status *Cancelled* |
| **View Occurrences** | Recurring series | Opens the Venue Booking list filtered to this series (Parent Booking) |

Each stamps *Replied By / Replied On* and emails the requester (template *Venue Booking - Status Update (Requester)*).

### 5.2 From the list
Tick bookings, then **Allot** / **Reject** or **Bulk Status → Mark …**. This sets the status and remarks directly: it does **not** check the current status and does **not** email the requester. Bulk status is allowed for System Manager, Administrator and `slcm_Registrar` only.

### 5.3 Who sees what
Admins (System Manager, `slcm_Registrar`, `AAD`, `AAD Staff`) see every booking. Everyone else sees only bookings they created. A student also passes the own-record check on Student.

---

## 6. Swaps

### 6.1 Swap request (raised by the requester)
A requester can ask to move a *Pending Allotment* or *Allotted* booking to another venue (`request_venue_swap`). This sets Swap Requested, the requested venue and reason, adds a row to the **Swap Request Log** table and emails the admins. The requester can withdraw it (`cancel_venue_swap_request`; the log row becomes *Withdrawn*).

On the booking form an admin then sees:
- **Approve Swap**: checks the new venue is free, moves the booking there, marks the log row *Approved*, emails the requester (template *Venue Booking - Swap Request Decision (Requester)*).
- **Reject Swap**: keeps the venue, marks the log row *Rejected*, emails the requester.

### 6.2 Swap Venue (admin only)
**Swap Venue** on the form picks another booking and exchanges the two venues. Each booking must fit in the other's venue (no clash with a third booking). A comment is added to both bookings.

---

## 7. Reports

| Report | Shows |
|---|---|
| Weekly Venue Booking Report | Bookings of the week containing a chosen date; filters Status, Requester Type, Room |
| Monthly Venue Booking Report | Bookings of a month; same filters |
| Room Availability Checker | For a from/to time, which **Room** records are free or booked |

---

## 8. Timetable and exams

Class timetables (Time Table) and exam schedules use the same Venue Master records. Time Table blocks a clash with another Time Table entry or an exam in the same venue. **Venue Booking and Time Table do not check each other** (see Open questions).

---

## 9. Troubleshooting

| Problem | Cause and fix |
|---|---|
| "Start Date & Time cannot be in the past" | Pick a future start. |
| "Venue … is already booked during this period" | Another Pending or Allotted booking overlaps. Pick another time or venue. |
| Venue missing from the list | It is inactive, of another type, too small (with occupancy filter on), or your roles are not in its Allowed Roles. |
| "You are not allowed to change the booking status" | Only admins change Status. Use the buttons. |
| "Only bookings Pending Allotment can be allotted." | The booking was already decided. |
| Recurring series has fewer bookings than expected | Clashing dates were skipped. |
| No email arrived | Check the three Venue Booking email templates exist and the user has an email. Failures go to Error Log. |

---

## 10. Open questions

1. **Reports query a column that does not exist.** Weekly / Monthly Venue Booking Report and Room Availability Checker read `room` from Venue Booking, but the field is `venue`. They are likely to fail. Room Availability Checker also lists the old **Room** DocType, not Venue Master.
2. **Number cards use old status names.** *Pending Venue Bookings* filters status = "Pending" and *Approved Venue Bookings* status = "Approved"; real statuses are *Pending Allotment* and *Allotted*, so both cards show 0. *Total Rooms* counts the old **Room** DocType, not Venue Master.
3. **Venue Booking vs Time Table.** A booking can overlap a class or exam in the same venue, and vice versa. Should they block each other?
4. **AAD override is dead code.** `override_booking` (AAD cancels another booking with 24 h notice) is indented inside `_notify_requester`, so it can never be called. Keep and fix, or delete?
5. **Swap request has no UI.** `request_venue_swap` exists in `slcm/api/student_portal.py` but no portal page calls it. Faculty have no swap path either.
6. **List bulk actions skip rules.** Bulk status ignores the current status, sends no emails, and excludes AAD roles (form buttons allow them).
7. **Admin email goes to Registrar and System Manager users only**, not AAD.
8. **Field labels are swapped.** On Venue Booking, field `programme` is labelled *Batch* (links SLCM Batch) and field `batch` is labelled *Programme* (links Programme, never filled).
9. **Sidebar shows Time Table and Email Templates.** Confirm these belong in Venue Bookings.
10. **Room DocType** (with "Room Master" shortcut on the workspace) is still used by Room Availability Checker. Retire it in favour of Venue Master?

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| Booking rules, recurrence, admin actions, swaps, emails, venue query | `slcm/slcm/doctype/venue_booking/venue_booking.py`, `.js` (form + list) |
| Row filter (own bookings) | `slcm/permissions.py` `venue_booking_query_conditions`; `slcm/security/student_scope.py`; wired in `hooks.py` |
| Student portal endpoints | `slcm/api/student_portal.py` (`get_rooms_for_type`, `submit_venue_booking`, `request_venue_swap`, `cancel_venue_swap_request`, `get_swap_log`, `update_venue_booking_attachment`, `cancel_venue_booking`, `bulk_update_venue_booking_status`); page `slcm/www/student-portal/venue_booking.py`, `venue-booking.html` |
| Faculty portal | `slcm/api/faculty_portal.py` `create_venue_booking`; `slcm/www/faculty-portal/venue_booking.py`, `venue-booking.html` |
| Time Table venue clash | `slcm/slcm/doctype/time_table/time_table.py` `check_venue_conflict` |
| Reports | `slcm/slcm/report/{weekly_venue_booking_report, monthly_venue_booking_report, room_availability_checker}` |
| Email templates, number cards, charts | `hooks.py` fixtures (Email Template, Number Card, Dashboard Chart) |
| Tests | `slcm/slcm/doctype/venue_booking/test_venue_booking.py`, `test_venue_booking_flow.py` |
| Sidebar / workspace / icon | `slcm/workspace_sidebar/venue_bookings.json`, `slcm/slcm/workspace/venue_bookings/` **and** `fixtures/workspace.json` (fixture copy wins), `slcm/desktop_icon/venue_bookings.json` |

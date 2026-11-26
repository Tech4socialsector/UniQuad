# Hostel Management: User Guide

**Applies to:** Uniquad (SLCM v16), as on disk in November 2026
**Who this is for:** Hostel office staff (Hostel Admin, Hostel Warden) who set up hostels, allot rooms and beds, and handle complaints, leave, fines and maintenance.
**Where:** Desk → **Student Services → Hostel Management**

---

## 1. The flow at a glance

```
1. Set up            Hostel (+ wardens) → Hostel Room → Hostel Bed
2. Allot             Hostel Allocation (student + hostel + room + bed)
                       → room occupancy, bed status, Student Master "Residence" fields
                       → Housing and Mess Fee demand (Fee Demand)
3. Registration      Student Master stage "Pending Residences" → "Pending IT"
                       (a hosteller must have a room before moving on)
4. Day to day        Complaints → Maintenance Log
                     Leave requests · Hostel Attendance · Visitor Entry Log
                     Fines (→ Fee Demand) · Refund Requests (→ ERPNext bridge)
5. Move out          Hostel Allocation → Update Status → Vacated
```

Only steps 1 and 2 are on the Hostel Management sidebar. Everything in step 4 exists as a DocType but is reached from the search bar (see section 2).

### Key ideas

| Term | Meaning |
|---|---|
| **Hostel** | A residence hall, e.g. a Boys / Girls / Co-ed hostel. Holds its wardens and hall leader. |
| **Hostel Room** | A room in a hostel, with a capacity (beds) and a live occupied count. |
| **Hostel Bed** | One bed in a room. It is *occupied* or free. |
| **Hostel Allocation** | One student placed in one hostel, room and bed from a date. Its **Status** drives occupancy. |
| **Residence tab** | The hostel fields on Student Master (`is_hosteller`, hostel, room, bed, dates, agreement, keys). Filled by the allocation. |

---

## 2. Where things are

### 2.1 Sidebar (`slcm/workspace_sidebar/hostel_management.json`)

| Sidebar item | Opens |
|---|---|
| Home | Hostel Management workspace (4 shortcuts: Hostel, Hostel Room, Hostel Bed, Hostel Allocation) |
| Hostel | Hostel list |
| Hostel Bed | Hostel Bed list |
| Hostel Room | Hostel Room list |
| Hostel Allocation | Hostel Allocation list |

### 2.2 Desktop icon (`slcm/desktop_icon/hostel_management.json`)

The **Hostel Management** icon sits inside the **Student Services** folder. It is shown to: `slcm_Hostel Admin`, `slcm_Hostel Warden`, `Campus Admin`, `Admission Admin`.

### 2.3 Other hostel DocTypes (not on the sidebar)

Open these from the search bar.

| DocType | Purpose |
|---|---|
| Hostel Block, Hostel Floor | Block / floor of a hostel, with a warden user |
| Hostel Settings (single) | Default Academic Year |
| Student Hostel Profile | Current hostel / room / bed and status per student |
| Room Change Request | Student asks to move room |
| Hostel Complaint | Complaint from a resident |
| Hostel Maintenance Log | Work done, spares, cost, linked to a complaint |
| Hostel Leave Request | Leave from the hostel |
| Hostel Attendance | Daily present / absent / leave per student |
| Visitor Entry Log | Visitor in / out times |
| Hostel Fine | Fine on a student, collected through a Fee Demand |
| Hostel Refund Request | Money paid back to a student |
| Hostel Fee Structure | Fee per academic year, hostel and room type |
| Hostel Rules | Rule title, description, default penalty |
| Hostel Asset, Hostel Inventory | Furniture / equipment and stock |
| Hostel Approval Dashboard (single) | Only a notes field |
| Mess, Mess Subscription, Mess Menu, Mess Attendance, Mess Payment, Mess Feedback | Mess (dining) records |

---

## 3. Setting up a hostel

### 3.1 Hostel
*Hostel Management → Hostel → + Add*

| Field | Notes |
|---|---|
| Hostel Name | Required, unique. Becomes the record name. |
| Hostel Code | Unique |
| Hostel Type | Boys / Girls / Co-ed |
| Total Rooms, Total Capacity (Beds) | Typed in by hand. Not calculated from rooms. |
| Warden Details (table) | One row per warden: name, code (unique), contact, email, system user, Active / Inactive |
| Hall Leader Name / Contact / Email | Shown on the student's hostel page |

### 3.2 Hostel Room
*Hostel Management → Hostel Room → + Add*. Named `{hostel}-{room_number}`.

| Field | Notes |
|---|---|
| Hostel | Required |
| Room Number | Required |
| Floor | Free text (not a link to Hostel Floor) |
| Room Type | Non-AC / AC |
| Capacity | Required. Number of beds. |
| Occupied | Read-only. Changed by allocations. |
| Is Available | Read-only. Cleared when Occupied reaches Capacity. |

### 3.3 Hostel Bed
*Hostel Management → Hostel Bed → + Add*. Named `BED-{room}-{bed_no}`.

| Field | Notes |
|---|---|
| Room | Required. Hostel fills in from the room. |
| Bed No/Name | Required |
| Is Occupied | Read-only. Set by allocations. |

---

## 4. Allotting a room (Hostel Allocation)

*Hostel Management → Hostel Allocation → + Add*. Named `ALL-{student}-{hostel}`.

| Field | Notes |
|---|---|
| Student | Student Master, required |
| Hostel, Room, Bed | All required. The Room list shows only rooms of the chosen hostel. Changing the hostel clears the room. |
| From Date / To Date | From Date required |
| Agreement Signed, Keys Handed Over | Tick boxes |
| Status | Default *Allocated*. Change it with the **Update Status** button: *Allocated / Vacated / Dropped Out / Suspended / Cancelled*. |
| Is Active | Default ticked |
| Remarks | |

**Rules the system enforces**
- The room must belong to the hostel.
- The bed must belong to the room.
- A new (or changed) bed must be free: "Bed … is already occupied."
- A new (or changed) room must have space: "Room … is fully occupied."

**What saving an allocation does**
- **Occupancy:** a new *Allocated* record adds 1 to the room and marks the bed occupied. Moving away from *Allocated* subtracts 1 and frees the bed. Moving back to *Allocated* adds it again. Changing room or bed while *Allocated* moves the count.
- **Student Master (Residence tab):** with status *Allocated*, sets Is Hosteller, hostel, room, bed, allocation dates, agreement and keys, and clears the vacated date. With any other status, clears the location fields, sets Is Hosteller off and copies To Date into *Vacated Date*. Status and remarks are always copied.
- **Fee:** on first insert, a **Housing and Mess Fee** demand is raised (Fee Component of type *Housing and Mess Fee*, amount = the active Fee Structure with demand type *Hostel*). No component or no active structure = no demand, only an Error Log entry.

**Deleting an allocation** frees the room and bed (if it was *Allocated*), clears the Student Master residence fields (only if they still point to this hostel and room) and cancels its fee demand.

### Registration link
Student Master registration moves *Pending Print & Scan → Pending Residences → Pending IT*. `slcm_Hostel Admin` moves a student to *Pending IT*. A student marked **Is Hosteller** cannot move to *Pending IT* until a hostel room is set. Hostel Admin and Hostel Warden see only students at *Pending Residences* in the Student Master list.

---

## 5. Complaints and maintenance

### 5.1 Hostel Complaint
Named `CMP-{YYYY}-{MM}-{DD}-{####}`.

| Field | Options |
|---|---|
| Student | Required |
| Type | Maintenance / Discipline / Cleanliness / Food / Other (required) |
| Severity | Low / Medium / High / Critical (default Medium) |
| Description | |
| Status | Open / In Progress / Resolved / Closed (default Open) |
| Resolution Details | |

There are no automatic status changes or notifications.

### 5.2 Hostel Maintenance Log
Named `MNT-{date}-{####}`. Fields: Complaint Reference (link to a complaint), Hostel (required), Work Done, Spares Used, Cost, Date (default today), Performed By (free text). Saving a log does **not** change the complaint's status.

---

## 6. Leave

Two leave DocTypes exist.

| | Hostel Leave Request | Student Leave Applications |
|---|---|---|
| Naming | `HLR-{student}-{YYYY}-{MM}-{DD}` | `SLA-YYYY-#####` |
| Fields | Student, From/To Date, Reason, Status (Pending / Approved / Rejected), Approved By | Student, Student Name, Submitted On, From/To Date, Total Leave Days, Reason, Status, Reviewed By/On, Admin Remarks |
| Automation | None | On Approved / Rejected: stamps Reviewed By/On and posts a **Student Announcement** to that student |
| Portal page | Read by `/student-portal/hostel` | `/student-portal/leave-request` (its menu link is commented out) |
| Permissions | System Manager only | System Manager, Academic Admin, slcm_Student (read, create; own records only) |

---

## 7. Fines

### 7.1 Hostel Fine
Named `FINE-{student}-{date}-{####}`.

| Field | Notes |
|---|---|
| Student | Required. Registration ID fills in. |
| Reason, Amount | Required |
| Fine Date | Default today |
| Status | Unpaid / Paid / Waived (default Unpaid) |
| Issued By | User |

**A fine is collected through a Fee Demand.** On insert the system raises a demand (Fee Component of type **Fine - Hostel**, demand type *Fine*, due in 15 days).

**Rules the system enforces**
- A Fee Component of type *Fine - Hostel* must exist before the first fine is saved.
- You cannot set *Paid* by hand. Collect the money with a Fee Payment against the demand; the fine becomes *Paid* when the demand is paid.
- You cannot move a fine off *Paid* while its demand is paid. Cancel the Fee Payment first.
- Once money is against the demand, you cannot waive the fine or change its amount.
- *Waived* waives the whole demand. Changing the amount updates the demand. Going back from *Waived* to *Unpaid* clears the waiver.

Unpaid hostel fines show on the student portal fee pages (`slcm/slcm/fee/portal_charges.py`).

### 7.2 Fine Imposition (not hostel-specific)
`Fine Imposition` adds a late fine (flat or % of outstanding) to outstanding Fee Demands in a date range. It is a fees tool; see the fees specs.

---

## 8. Other records

| DocType | Fields and behaviour |
|---|---|
| Hostel Refund Request | Student, Amount, Reason, Status (Pending / Approved / Processed / Rejected). Refund Mode, Processed On, Transaction Reference. *Processed* needs a Refund Mode and sets Processed On to today if empty. Saving or deleting it is sent to the ERPNext bridge. |
| Hostel Fee Structure | Academic Year, Hostel, Room Type, Fee Component, Amount, Is Refundable. Not read by any code (the allocation fee uses Fee Structure, see 4). |
| Hostel Attendance | Student, Date, Status (Present / Absent / Leave), Time, Hostel, Room. Manual entry. |
| Visitor Entry Log | Visitor Name, Student to meet, Relationship, Purpose, In Time, Out Time. |
| Room Change Request | Student, Current Room, Requested Room, Reason, Status (Pending / Approved / Rejected). Approving does **not** move the student. |
| Student Hostel Profile | One per student (`SHP-{student}`). Current hostel / room / bed are read-only, but no code fills them. |
| Mess Payment | Saving or deleting it is sent to the ERPNext bridge. |

---

## 9. Student portal

*Student Portal → Hostel Management* (`/student-portal/hostel`)

The page shows:
- hostel details (name, code, type, capacity, hall leader, first Active warden), room (number, floor, type, capacity, occupancy) and bed;
- the allocation (dates, agreement, keys, status), tenure and days to the end date;
- a move-in checklist: room allotted, agreement signed, keys handed over, bed assigned;
- the student's complaints (if any).

Data comes from Student Hostel Profile first, then Student Master's residence fields, then the active Hostel Allocation.

The page code also loads leave requests and fines and has `submit_complaint` and `submit_leave_request` endpoints, but the page template has no form or section for them.

---

## 10. Permissions

| DocType | Roles with access (DocType JSON) |
|---|---|
| Hostel, Hostel Room, Hostel Bed | System Manager, NLSIU Admin (full); slcm_Student (read) |
| Hostel Allocation and all other hostel / mess DocTypes | System Manager only |
| Student Leave Applications | System Manager, Academic Admin, slcm_Student (own only) |

---

## 11. Troubleshooting

| Problem | Cause and fix |
|---|---|
| "Bed … is already occupied." | Pick a free bed. The Bed list in the form is not filtered, so it also offers occupied beds and beds of other rooms. |
| "Room … is fully occupied." | Occupied has reached Capacity. Raise capacity or pick another room. |
| Room missing from the Room list | Only rooms of the chosen hostel are offered. Choose the hostel first. |
| No housing fee demand after allotting | No Fee Component of type *Housing and Mess Fee*, or no Active Fee Structure with demand type *Hostel*. See Error Log. |
| "Create a Fee Component of type 'Fine - Hostel' first" | Create that Fee Component, then save the fine. |
| Cannot mark a fine Paid | Collect it with a Fee Payment against its Fee Demand. |
| Student stuck at *Pending Residences* | Is Hosteller is ticked but no hostel room. Allot a room first. |

---

## 12. Open questions

1. **Hostel roles have no DocType rights.** `slcm_Hostel Admin` and `slcm_Hostel Warden` see the desktop icon, but no hostel DocType grants them any permission in its JSON (Custom DocPerm may exist only in the database). Which roles should work these screens?
2. **Sidebar covers only setup and allocation.** Complaints, leave, fines, maintenance, attendance, visitors, refunds and mess are not on the sidebar or workspace. Should they be added?
3. **Is Active on Hostel Allocation is never cleared** when status changes to Vacated. The portal picks the allocation with Is Active = 1. Should status drive it?
4. **Student Hostel Profile is never filled** by code, yet the portal reads it first. Keep it, fill it from the allocation, or remove it?
5. **Two leave DocTypes** (Hostel Leave Request and Student Leave Applications). Which one is the hostel's?
6. **Hostel Fee Structure is unused.** The housing fee comes from the first Active Fee Structure with demand type *Hostel*, the same amount for every hostel and room type. Is that intended?
7. **Room Change Request approval** does not move the student. Should it update the allocation?
8. **Hostel Block / Hostel Floor** are not linked from Hostel Room (floor is free text). Student Master `hostel_block` is set to the hostel name. Are blocks needed?
9. **Portal complaint / leave forms**: the endpoints exist but the page has no form. Should students raise complaints and hostel leave from the portal?
10. **Bed picker is unfiltered.** `get_room_query` / `get_bed_query` (free rooms, free beds of the room) exist in the controller but the form does not use them. Should the Bed field be limited to free beds of the room?
11. **Status list mismatch:** the allocation Status field is plain Data (default *Allocated*); the five statuses exist only in the Update Status dialog.
12. **Mess module** (6 DocTypes) has no sidebar, workspace or portal page. Is it in scope?

---

## Appendix: technical notes for developers

| Topic | Where |
|---|---|
| Allocation rules, occupancy, Student Master sync, room/bed queries | `slcm/slcm/doctype/hostel_allocation/hostel_allocation.py`, `.js` |
| Room availability flag | `slcm/slcm/doctype/hostel_room/hostel_room.py` |
| Housing fee demand on allocation, fine demand | `slcm/slcm/fee/event_hooks.py` (`on_hostel_allocation_insert`, `on_hostel_allocation_trash`, `on_hostel_fine_insert`); wired in `hooks.py` doc_events |
| Fine status ↔ demand | `slcm/slcm/doctype/hostel_fine/hostel_fine.py` |
| Refund / mess payment → ERPNext | `hooks.py` doc_events → `slcm.erpnext_bridge.sync.enqueue_sync` |
| Leave notification | `slcm/slcm/doctype/student_leave_applications/student_leave_applications.py` |
| Registration stage check | `slcm/slcm/doctype/student_master/student_master.py` (`VALID_TRANSITIONS`, *Pending IT* hostel-room check) |
| Student Master row filter for hostel roles | `slcm/permissions.py` (`_WORKFLOW_ROLE_STATUS_MAP`) |
| Portal page | `slcm/www/student-portal/hostel.py`, `hostel.html` |
| Sidebar / workspace / icon | `slcm/workspace_sidebar/hostel_management.json`, `slcm/slcm/workspace/hostel_management/` **and** `fixtures/workspace.json` (fixture copy wins), `slcm/desktop_icon/hostel_management.json` |

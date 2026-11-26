[← Uniquad User Manual](README.md)

# 11. Hostel management

Staff set up hostels, rooms and beds, then allocate a bed to each hosteller. Allocation raises the hostel fee automatically. Students raise complaints and leave requests from the portal. Hostel records currently need the **System Manager** role. Workspace: **Hostel Management** (`/desk/hostel-management`).

**Desk path:** Desk home → **Student Services** → **Hostel Management**.

> *Screenshot: Hostel Management workspace* (see the online manual)

## 11.1 Set up hostels, rooms and beds

1. **Hostel** (`/desk/hostel/new`): **Hostel Name**, **Hostel Code**, **Hostel Type** (Boys, Girls or Co-ed), **Total Rooms**, **Total Capacity (Beds)**, the **Warden Details** table and hall leader. **Save**.
2. **Hostel Room** (`/desk/hostel-room/new`): **Hostel**, **Room Number**, **Floor**, **Room Type** (AC or Non-AC), **Capacity**. **Save**. **Is Available** updates by itself.
3. **Hostel Bed** (`/desk/hostel-bed/new`): **Room** and **Bed No/Name**. **Save**.

> *Screenshot: New Hostel* (see the online manual)

> *Screenshot: New Hostel Room* (see the online manual)

## 11.2 Allocate a room

1. Go to `/desk/hostel-allocation/new`.
2. Choose **Student**, **Hostel**, **Room** and **Bed**, and fill **From Date** (and **To Date** if known).
3. Tick **Agreement Signed** and **Keys Handed Over** when done.
4. Click **Save**. The system refuses a bed that is taken or a room that is full.
5. Click **Update Status**, choose **Allocated** and click **Update**.

> *Screenshot: New Hostel Allocation* (see the online manual)

The room and bed become occupied, the Student Master shows the hostel details, and a "Housing and Mess Fee" due is raised (due in 30 days) from the hostel fee structure. Later set **Vacated**, **Dropped Out**, **Suspended** or **Cancelled** the same way.

## 11.3 Complaints, leave and fines

| Record | Address | How it works |
| --- | --- | --- |
| Hostel Complaint | `/desk/hostel-complaint` | Created **Open** from the portal (type, severity, description). Staff move it to **In Progress**, **Resolved**, **Closed** and fill **Resolution Details**. Log repair work in **Hostel Maintenance Log** |
| Hostel Leave Request | `/desk/hostel-leave-request` | Created **Pending** from the portal. The warden sets **Approved** or **Rejected** and **Approved By** |
| Hostel Fine | `/desk/hostel-fine/new` | Fill **Student**, **Reason**, **Amount**, **Fine Date**. Saving raises a "Fine - Hostel" due (15 days) that the student pays like any fee |
| Room Change Request, Hostel Refund Request | Search bar | Status set by hand |

> *Screenshot: Hostel Complaint list* (see the online manual)

> *Screenshot: New Hostel Fine* (see the online manual)

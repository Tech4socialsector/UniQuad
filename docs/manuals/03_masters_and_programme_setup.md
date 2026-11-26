[← Uniquad User Manual](README.md)

# 3. Masters and programme setup

Masters are the building blocks every other module uses. Set them up once per year, in the order below, because each record links to the ones before it. Most masters need the **System Manager** role; **slcm\_Registrar** can maintain Academic Year, Term, Batch, Section, Department and Faculty. The **Uniquad Data Entry Map** page (`/desk/slcm-data-map`) shows the same order on screen.

## 3.1 Setup order

1. **Lookups**: Gender, Student Category, Designation, **Department**.
2. **Faculty**.
3. **Room**, **Venue Type**, then **Venue Master** (a timetable entry needs a venue).
4. **Academic Year**.
5. **Term Master** (term names such as `Trimester I`).
6. **Academic Term**.
7. **Programme Master** (the catalogue entry).
8. **Programme** (the programme offered in a given year and term).
9. **Course**.
10. **Batch**.
11. **Section**.
12. **Course Offering** (by hand or with the **Course Management Tool**).
13. Optional: **Term Configuration**, **Class Configuration**, **Time Table**.
14. **Fee Structure** (section 10).
15. **Student Master** (from admissions or by hand), then registration (section 5).
16. **Student Enrollment**, after registration is **Completed**.
17. **Promotion Policy** (section 9).

The **Master** workspace (`/desk/master`) has shortcuts to all of these, plus cards for Active Students, Active Faculty, Active Programmes and Active Course Catalogue.

**Desk path:** Desk home → **Master**, **Masters** or **Programme Setup**.

> *Screenshot: Masters workspace* (see the online manual)

> *Screenshot: Master workspace with shortcuts to every master* (see the online manual)

> *Screenshot: Programme Setup workspace* (see the online manual)

> *Screenshot: Uniquad Data Entry Map: the setup order on screen* (see the online manual)

## 3.2 Create an Academic Year

1. Go to `/desk/academic-year` and click **+ Add Academic Year**.
2. Enter **Academic Year Name**, for example `2026 - 2027`.
3. Choose **Academic System**: Semester, Trimester, Quarter or Year.
4. Enter **Year Start Date** and **Year End Date**.
5. Set **Status** to Active and click **Save**.

> *Screenshot: New Academic Year form* (see the online manual)

> *Screenshot: A saved Academic Year* (see the online manual)

Promotion uses the start dates to decide which academic year comes next.

## 3.3 Create terms

1. **Term Master**: go to `/desk/term-master/new`, type the term name (for example `Trimester I`) and click **Save**.
2. **Academic Term**: go to `/desk/academic-term/new`.
3. Choose **Academic Year** and **Term Name** (from Term Master).
4. Fill **Term Type**, **Academic System**, **Previous Term** (optional) and **Number of terms per academic year**.
5. Enter **Term Start Date**, **Term End Date** and **Status**, then click **Save**.

> *Screenshot: New Term Master* (see the online manual)

> *Screenshot: New Academic Term form* (see the online manual)

> *Screenshot: A saved Academic Term* (see the online manual)

The term is named `<Term Name> - <Academic Year>`, for example `Trimester I - 2026 - 2027`.

## 3.4 Create a Department and Faculty

1. **Department** (`/desk/department/new`): fill **Department ID**, **Department Name**, **Head of Department**, **Status**, then **Save**.
2. **Faculty** (`/desk/faculty/new`): fill **Faculty ID**, **Full name**, **Email**, **Official Email ID**, **Phone Number**, **Department**, **Designation** and **Status**.
3. To give the faculty member a portal login, tick **Auto Create User** (System Manager only; **Official Email ID** must be filled).
4. Click **Save**. With **Auto Create User** ticked, a login with the slcm\_Faculty role is created and linked in **User Account**.

> *Screenshot: New Department form* (see the online manual)

> *Screenshot: New Faculty form (Auto Create User at the bottom)* (see the online manual)

> *Screenshot: A saved Faculty record* (see the online manual)

## 3.5 Create a Programme

A **Programme Master** is the catalogue entry (for example BA LLB). A **Programme** is that programme offered in a particular academic year and term.

1. **Programme Master** (`/desk/programme-master/new`): fill **Programme Code**, **Programme Name**, **Level of Study**, **Programme duration (in years)**, **Graduation Credits** and **Programme Status**, then **Save**.
2. **Programme** (`/desk/programme/new`): choose **Programme Name**. Code, level, duration and credits fill in automatically.
3. Choose **Department**, **Academic Year** and **Academic Term**. The term dates fill in.
4. Set **Status** to Active.
5. If the programme takes applications, fill the **Admissions** tab (Intake Type, Program Image, Program Description, Brochure File, Curriculum, Career Prospects, Faculty) and the **Stages** tab. These show on the admissions portal.
6. Click **Save**. The record is named `<PROGRAMME CODE>-<Academic Year>-<TERM>`.

> *Screenshot: New Programme Master* (see the online manual)

> *Screenshot: New Programme form* (see the online manual)

> *Screenshot: A saved Programme* (see the online manual)

## 3.6 Create a Course

1. Go to `/desk/course/new`.
2. Fill **Course Code**, **Course Name**, **Credit Value**, **Course Type** (Core or Elective) and **Status**. Add **Topics** if needed.
3. Click **Save**. The course is named `<Course Code>-<Course Name>`, for example `LS001-Law of Crime`.

> *Screenshot: New Course form* (see the online manual)

> *Screenshot: A saved Course* (see the online manual)

## 3.7 Create a Batch and Sections

1. **Batch** (`/desk/batch/new`): choose **Programme**. Academic Year, term dates and programme details fill in.
2. Enter **Batch name** (for example `BALLB 2026 Batch`) and **Batch code**.
3. Set **Status** and **Term Year** (the year level, for example 1). Click **Save**.
4. **Section** (`/desk/section/new`): choose **Batch**, enter **Section Name** (for example `A`), **Capacity** and **Status**, then **Save**. The section is named `<Batch>-<Section Name>`.
5. Open the Batch again and set its **Section**.

> *Screenshot: New Batch form* (see the online manual)

> *Screenshot: A saved Batch* (see the online manual)

> *Screenshot: New Section form* (see the online manual)

> *Screenshot: A saved Section* (see the online manual)

For promotion to work, next year's Batch must have the same Programme and Section, **Term Year** plus 1, and the next Academic Year.

## 3.8 Create Course Offerings

A Course Offering says which course runs for which batch, term and section, and who teaches it.

1. Go to `/desk/course-offering/new`.
2. Choose **Course** and **Batch**. Programme, Academic Year and Term fill in.
3. Check **Term**, then choose **Section** and **Year**.
4. In the **Faculty** table add a row per teacher: **Faculty**, **Section**, **Role** (Primary, Co-Faculty or Guest) and **Is Primary**. Only one Primary is allowed per section.
5. Set **Status** to Active and click **Save**.

> *Screenshot: New Course Offering with the Faculty table* (see the online manual)

> *Screenshot: A saved Course Offering* (see the online manual)

Only **Active** offerings are added to new Student Enrollments automatically.

## 3.9 Plan a whole curriculum with the Course Management Tool

1. Go to `/desk/course-management` (System Manager).
2. Choose **Programmes**, **Academic Year**, **Academic System** and, optionally, **Batch** and **Section**.
3. Use **+ Add Trimester** (or Semester) to add terms, then **+ Add Course** or **+ Add Cluster** inside each term.
4. Click **Save**. The message "Curriculum Saved Successfully" appears.

> *Screenshot: Course Management Tool* (see the online manual)

If a Batch was selected, one Course Offering per course, batch and term is created or updated with status Active.

## 3.10 Rooms and venues

- **Room** (`/desk/room/new`): **Room Name**, **Room Type** (Classroom, Moot Court, Meeting Room and others), Floor, Capacity, **Is Booking Allowed**, Block.
- **Venue Type** (`/desk/venue-type/new`): **Venue Type Name**, **Is Active**.
- **Venue Master** (`/desk/venue-master/new`): **Venue Name/Number**, **Venue Type**, **Capacity**, **Venue Amenity** table and **Allowed Roles** table (who may book it).

> *Screenshot: New Room* (see the online manual)

> *Screenshot: New Venue Type* (see the online manual)

> *Screenshot: New Venue Master* (see the online manual)

> *Screenshot: A saved Venue Master* (see the online manual)

## 3.11 Edit or delete a master

Open the master's list, click the record, change it and click **Save**. To delete, open it and use **⋯** → **Delete** (or tick rows in the list → **Actions** → **Delete**). Masters are linked to many other records, so deleting is often refused; in that case set **Status** to Inactive.

| Master | List address | Before you edit or delete |
| --- | --- | --- |
| Academic Year | `/desk/academic-year` | Cannot be deleted once terms, programmes, batches or fees use it. Set **Status** to Inactive at year end |
| Term Master | `/desk/term-master` | Renaming changes the term name used in new Academic Terms |
| Academic Term | `/desk/academic-term` | Changing dates affects timetables and attendance for that term |
| Department | `/desk/department` | Cannot be deleted while faculty or programmes link to it |
| Faculty | `/desk/faculty` | Set **Status** to Inactive when a faculty member leaves; deleting fails if they teach a Course Offering |
| Programme Master | `/desk/programme-master` | Edits do not change Programmes already created from it |
| Programme | `/desk/programme` | Cannot be deleted once batches, applicants or students use it |
| Course | `/desk/course` | Cannot be deleted while Course Offerings or marks use it; set **Status** to Inactive |
| Batch | `/desk/batch` | Cannot be deleted while students are enrolled |
| Section | `/desk/section` | Change **Capacity** any time; cannot be deleted while students use it |
| Course Offering | `/desk/course-offering` | Set **Status** to Inactive to stop it being added to new enrollments; faculty changes apply from now on |
| Room, Venue Type, Venue Master | `/desk/room`, `/desk/venue-type`, `/desk/venue-master` | Untick **Is Active** instead of deleting when bookings or timetables use them |

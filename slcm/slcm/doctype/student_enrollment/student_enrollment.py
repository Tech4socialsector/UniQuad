# Copyright (c) 2025, TFSS and contributors
# For license information, please see license.txt

"""Student Enrollment: one record per student and programme.

The student's path through the programme is kept in the `academic_log` child
table (Student Academic Log), one row per academic term:

    Upcoming  - a later term of the current year
    Ongoing   - the current term; at most one row, and the source of the
                student's current academic year / term / year of study
    Completed - a finished term
    Redo      - a term of a year the student has to repeat
    Dropped   - closed because the enrollment was dropped

Promotion does not create a new enrollment: it closes the current year's rows
and adds rows for the next year to the same record.

`enrolled_courses` (Student Enrollment Course) lists every course the student
takes through the programme. A row is added when the student is put in a
class (sync_class_to_enrollments). Its status follows the term's dates -
Upcoming, Ongoing, then Completed once the term has ended - unless it is set
to Carry Forward, Withdrawn or Dropped, which stay as set.

Other modules read the current position with get_current_log() /
get_current_logs(), or in SQL with current_log_join() / year_log_exists().
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, now_datetime, today

from slcm.slcm.doctype.batch.batch import update_enrolled_count

LOG_DOCTYPE = "Student Academic Log"
OPEN_LOG_STATUSES = ("Ongoing", "Upcoming")
# Rows that are not part of the student's live position.
CLOSED_LOG_STATUSES = ("Redo", "Dropped")
# Enrolled course statuses set by staff; the others follow the term's dates.
MANUAL_COURSE_STATUSES = ("Carry Forward", "Withdrawn", "Dropped")
OPEN_COURSE_STATUSES = ("Ongoing", "Upcoming")


class StudentEnrollment(Document):
    def autoname(self):
        self.name = make_enrollment_name(self.student)

    def validate(self):
        self.validate_section_change()
        if not self.academic_log:
            self.set_initial_log()
        self.sync_log_sections()
        self.validate_log()
        self.close_log_on_status()
        self.refresh_course_statuses()
        self.stamp_changed_rows()
        self.validate_duplicate_enrollment()

    def on_update(self):
        """Sync Student Master when enrollment status changes."""
        self._sync_student_master_status()
        update_enrolled_count(self.batch)
        previous = self.get_doc_before_save()
        if previous and previous.batch and previous.batch != self.batch:
            update_enrolled_count(previous.batch)
        if not self.flags.skip_roster_sync:
            self._sync_class_configuration_rosters()

    # ── Academic log ──────────────────────────────────────────────────────────

    def current_log(self):
        """The Ongoing log row, else the latest open/completed one."""
        return _pick_current(self.academic_log)

    def set_initial_log(self):
        """A new enrollment starts in Year 1 of the Batch's academic year."""
        academic_year = frappe.db.get_value("Batch", self.batch, "academic_year") if self.batch else None
        if not academic_year:
            frappe.throw(_("Add the first Academic Log row (academic year and year), or pick a Batch that has an Academic Year."))
        self.add_year_log(academic_year, 1)

    def add_year_log(self, academic_year, year_no, current_term=None):
        for row in build_year_log(academic_year, year_no, current_term):
            self.append("academic_log", {**row, "section": self.section})

    def validate_section_change(self):
        """Section is set on creation; afterwards it only changes through
        change_section(), which records the move in the Academic Log."""
        if self.is_new() or self.flags.section_change:
            return
        previous = self.get_doc_before_save()
        if previous and (previous.section or None) != (self.section or None):
            frappe.throw(_("Use Change Section to move the student to another section, so the move is logged in the Academic Log."))

    def sync_log_sections(self):
        """Upcoming terms follow the enrollment's Section; an Ongoing row
        without a section takes it too. Completed / Redo / Dropped rows keep
        the section the student was in at the time."""
        for row in self.academic_log:
            if row.status == "Upcoming" or (row.status == "Ongoing" and not row.section):
                row.section = self.section

    def validate_log(self):
        duration = cint(frappe.db.get_value("Programme", self.program, "program_duration"))
        for row in self.academic_log:
            if cint(row.year_no) < 1:
                frappe.throw(_("Academic Log row {0}: Year must be 1 or more.").format(row.idx))
            if duration and cint(row.year_no) > duration:
                frappe.throw(_("Academic Log row {0}: Year {1} is beyond the {2}-year duration of {3}.").format(
                    row.idx, row.year_no, duration, self.program))
            if row.academic_term:
                term_year = frappe.db.get_value("Academic Term", row.academic_term, "academic_year")
                if term_year != row.academic_year:
                    frappe.throw(_("Academic Log row {0}: Term {1} does not belong to Academic Year {2}.").format(
                        row.idx, row.academic_term, row.academic_year))

        ongoing = [r for r in self.academic_log if r.status == "Ongoing"]
        if len(ongoing) > 1:
            frappe.throw(_("Only one Academic Log row can be Ongoing (rows {0}).").format(
                ", ".join(str(r.idx) for r in ongoing)))

        # Keep the log in chronological order.
        self.academic_log.sort(key=_log_sort_key)
        for idx, row in enumerate(self.academic_log, 1):
            row.idx = idx

    def close_log_on_status(self):
        """Completing or dropping the enrollment closes its open terms."""
        closing = {"Completed": "Completed", "Dropped": "Dropped"}.get(self.status)
        if not closing:
            return
        for row in self.academic_log:
            if row.status in OPEN_LOG_STATUSES:
                row.status = closing
        if self.status == "Dropped":
            for row in self.enrolled_courses:
                if row.status in OPEN_COURSE_STATUSES:
                    row.status = "Dropped"

    def stamp_changed_rows(self):
        """Fill Updated On / By on log and course rows that are new or changed."""
        previous = self.get_doc_before_save()
        old_log = {r.name: r for r in (previous.academic_log if previous else [])}
        old_courses = {r.name: r for r in (previous.enrolled_courses if previous else [])}
        now, user = now_datetime(), frappe.session.user

        for row in self.academic_log:
            old = old_log.get(row.name)
            if not old or any(old.get(f) != row.get(f) for f in ("academic_year", "academic_term", "year_no", "section", "status")):
                row.updated_on, row.updated_by = now, user

        for row in self.enrolled_courses:
            old = old_courses.get(row.name)
            if not old or any(old.get(f) != row.get(f) for f in ("status", "grade", "class_name")):
                row.updated_on = now

    # ── Courses ───────────────────────────────────────────────────────────────

    def refresh_course_statuses(self):
        """Course rows follow their term: Upcoming before it starts, Ongoing
        while it runs, Completed after it ends (or once the student has left
        that academic year in the log). Carry Forward / Withdrawn / Dropped
        are set by staff and kept."""
        open_years = {r.academic_year for r in self.academic_log if r.status in OPEN_LOG_STATUSES}
        for row in self.enrolled_courses:
            if row.status in MANUAL_COURSE_STATUSES:
                continue
            status = term_course_status(row.academic_term)
            if status in OPEN_COURSE_STATUSES and row.academic_year and row.academic_year not in open_years:
                status = "Completed"
            row.status = status

    # ── Class Configuration rosters ───────────────────────────────────────────

    def _sync_class_configuration_rosters(self):
        """Add/remove this student on the Class Configuration roster of every
        course of their current academic year they are enrolled/dropped in.

        Nothing else in the system puts them on a
        Class Configuration's student list. Exams/results read that list
        (via the `Class Student` child table) to decide who is eligible for
        a course, so without this a properly enrolled student would be
        invisible to exams unless someone manually added them to the class.

        Matches by course + batch, and additionally by section when the
        student has one set - if a batch has multiple sections offering the
        same course and the student's section is not recorded, they end up
        on every matching section's roster since there is nothing to
        disambiguate with. Courses of earlier years are left alone.
        """
        if not self.student or not self.batch:
            return

        current = self.current_log()
        for row in self.enrolled_courses:
            if not row.course:
                continue
            if current and row.academic_year and row.academic_year != current.academic_year:
                continue

            dropped = self.status == "Dropped" or row.status in MANUAL_COURSE_STATUSES

            filters = {"course": row.course, "batch": self.batch}
            if self.section:
                filters["section"] = self.section

            class_configs = frappe.get_all(
                "Class Configuration",
                filters=filters,
                pluck="name",
            )
            for class_config_name in class_configs:
                if dropped:
                    self._remove_from_class_roster(class_config_name)
                else:
                    self._add_to_class_roster(class_config_name)

    def _add_to_class_roster(self, class_config_name):
        cc = frappe.get_doc("Class Configuration", class_config_name)
        if any(r.student == self.student for r in cc.students):
            return

        first, middle, last, registration_id, email = frappe.db.get_value(
            "Student Master",
            self.student,
            ["first_name", "middle_name", "last_name", "registration_id", "email"],
        )
        student_name = " ".join(filter(None, [first, middle, last]))

        cc.append("students", {
            "student": self.student,
            "student_name": student_name,
            "registration_id": registration_id,
            "email": email,
        })
        cc.save(ignore_permissions=True)

    def _leave_section_rosters(self, section):
        """Take the student off the Class Configuration rosters of `section`
        for their current year's courses (after a section change)."""
        if not (section and self.batch):
            return
        current = self.current_log()
        courses = {
            r.course for r in self.enrolled_courses
            if r.course and (not current or not r.academic_year or r.academic_year == current.academic_year)
        }
        for course in courses:
            for name in frappe.get_all(
                "Class Configuration",
                filters={"course": course, "batch": self.batch, "section": section},
                pluck="name",
            ):
                self._remove_from_class_roster(name)

    def _remove_from_class_roster(self, class_config_name):
        cc = frappe.get_doc("Class Configuration", class_config_name)
        remaining = [r for r in cc.students if r.student != self.student]
        if len(remaining) == len(cc.students):
            return
        cc.set("students", remaining)
        cc.save(ignore_permissions=True)

    def after_delete(self):
        update_enrolled_count(self.batch)

    def validate_duplicate_enrollment(self):
        """One enrollment per student + programme."""
        existing = frappe.db.get_value(
            "Student Enrollment",
            {
                "student": self.student,
                "program": self.program,
                "name":    ["!=", self.name],
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("{0} is already enrolled in {1} ({2}).").format(
                    self.student_name or self.student, self.program, frappe.bold(existing),
                )
            )

    def _sync_student_master_status(self):
        """Reflect this enrollment's status and current year on Student Master.

        Status changes are unrestricted (including moving away from
        Completed/Dropped), so this always sets Student Master to match the
        current status rather than only reacting to Dropped/Completed.
        """
        if not self.student:
            return
        if self.status == "Dropped":
            values = {"student_status": "Dropped", "academic_status": "Inactive"}
        elif self.status == "Completed":
            values = {"student_status": "Graduated"}
        else:
            values = {"student_status": "Active", "academic_status": "Active"}

        current = self.current_log()
        if current and self.status != "Dropped":
            values.update({
                "academic_year": current.academic_year,
                "current_year":  str(cint(current.year_no)),
                "year_of_study": f"{_ordinal(current.year_no)} Year",
            })
        frappe.db.set_value("Student Master", self.student, values)


# ── Log helpers (shared with other modules) ───────────────────────────────────

def _ay_start(academic_year):
    # str() so years without a start date ("") still compare; ISO dates sort chronologically.
    if not academic_year:
        return ""
    return str(frappe.get_cached_value("Academic Year", academic_year, "year_start_date") or "")


def _term_no(academic_term):
    return cint(frappe.get_cached_value("Academic Term", academic_term, "term_no")) if academic_term else 0


def _log_sort_key(row):
    return (_ay_start(row.academic_year), cint(row.year_no), _term_no(row.academic_term))


def _pick_current(rows):
    """Ongoing row; failing that, the latest row that is not Redo/Dropped;
    failing that, the latest row. None for an empty log."""
    rows = sorted(rows or [], key=_log_sort_key)
    for row in rows:
        if row.status == "Ongoing":
            return row
    live = [r for r in rows if r.status not in CLOSED_LOG_STATUSES]
    return (live or rows or [None])[-1]


def build_year_log(academic_year, year_no, current_term=None):
    """Log rows for one year of study: one per Active term of `academic_year`.

    `current_term` (else the term running today, else the next one to start,
    else the last one) is Ongoing, earlier terms Completed and later ones
    Upcoming. A year with no terms set up yet gets a single Ongoing row
    without a term."""
    terms = frappe.get_all(
        "Academic Term",
        filters={"academic_year": academic_year, "status": "Active"},
        fields=["name", "term_start_date", "term_end_date"],
        order_by="term_no asc, term_start_date asc",
    )
    if not terms:
        return [{"academic_year": academic_year, "year_no": cint(year_no), "status": "Ongoing"}]

    now = getdate(today())
    current = next((i for i, t in enumerate(terms) if t.name == current_term), None)
    if current is None:
        current = next((i for i, t in enumerate(terms) if getdate(t.term_end_date) >= now), len(terms) - 1)
    return [
        {
            "academic_year": academic_year,
            "academic_term": t.name,
            "year_no":       cint(year_no),
            "status":        "Ongoing" if i == current else ("Completed" if i < current else "Upcoming"),
        }
        for i, t in enumerate(terms)
    ]


def get_current_log(enrollment):
    """frappe._dict(academic_year, academic_term, year_no, status) of an
    enrollment's current position, or None."""
    return get_current_logs([enrollment]).get(enrollment)


def get_current_logs(enrollments):
    """{enrollment name: current log row} for many enrollments at once."""
    enrollments = [e for e in (enrollments or []) if e]
    if not enrollments:
        return {}
    rows = frappe.get_all(
        LOG_DOCTYPE,
        filters={"parenttype": "Student Enrollment", "parent": ["in", enrollments]},
        fields=["parent", "academic_year", "academic_term", "year_no", "status"],
    )
    by_parent = {}
    for row in rows:
        by_parent.setdefault(row.parent, []).append(row)
    return {parent: _pick_current(parent_rows) for parent, parent_rows in by_parent.items()}


def get_log(enrollment):
    """All log rows of an enrollment, oldest first."""
    rows = frappe.get_all(
        LOG_DOCTYPE,
        filters={"parenttype": "Student Enrollment", "parent": enrollment},
        fields=["name", "academic_year", "academic_term", "year_no", "status", "updated_on", "updated_by"],
    )
    return sorted(rows, key=_log_sort_key)


def current_log_join(se="se", log="sal", join="INNER"):
    """SQL join that attaches the Ongoing log row of Student Enrollment `se` as
    `log` (log.academic_year, log.academic_term, log.year_no). Use join="LEFT"
    to keep enrollments that have no Ongoing row (completed/dropped)."""
    return f"""{join} JOIN `tab{LOG_DOCTYPE}` {log}
        ON {log}.parent = {se}.name AND {log}.parenttype = 'Student Enrollment'
        AND {log}.status = 'Ongoing'"""


def year_log_exists(se="se", academic_year=None, year_no=None):
    """SQL condition: Student Enrollment `se` has a (non Dropped/Redo) log row
    for the given academic year and/or year of study. Pass SQL expressions,
    e.g. "%(academic_year)s" or "co.academic_year"."""
    conds = [f"l.parent = {se}.name", "l.parenttype = 'Student Enrollment'",
             "l.status NOT IN ('Redo', 'Dropped')"]
    if academic_year:
        conds.append(f"l.academic_year = {academic_year}")
    if year_no:
        conds.append(f"l.year_no = {year_no}")
    return f"EXISTS (SELECT 1 FROM `tab{LOG_DOCTYPE}` l WHERE {' AND '.join(conds)})"


def enrollments_in_year(academic_year=None, year_no=None, filters=None, current_only=False):
    """Names of Student Enrollments with a log row for `academic_year` and/or
    `year_no` (any left empty is ignored). current_only=True matches only the
    Ongoing row, i.e. students who are in that year right now."""
    log_filters = {"parenttype": "Student Enrollment"}
    if academic_year:
        log_filters["academic_year"] = academic_year
    if cint(year_no):
        log_filters["year_no"] = cint(year_no)
    log_filters["status"] = "Ongoing" if current_only else ["not in", list(CLOSED_LOG_STATUSES)]
    parents = set(frappe.get_all(LOG_DOCTYPE, filters=log_filters, pluck="parent"))
    if not parents:
        return []
    return frappe.get_all(
        "Student Enrollment",
        filters={**(filters or {}), "name": ["in", list(parents)]},
        pluck="name",
    )


def term_course_status(academic_term, on_date=None):
    """Upcoming / Ongoing / Completed for a course taught in `academic_term`,
    from the term's dates (Ongoing when the term or its dates are not set)."""
    if not academic_term:
        return "Ongoing"
    start, end = frappe.get_cached_value("Academic Term", academic_term, ["term_start_date", "term_end_date"]) or (None, None)
    day = getdate(on_date or today())
    if start and day < getdate(start):
        return "Upcoming"
    if end and day > getdate(end):
        return "Completed"
    return "Ongoing"


def advance_term_status():
    """Daily: move each Ongoing row whose term has ended on to the next term of
    the same year (Ongoing -> Completed, next Upcoming -> Ongoing). The last
    term of a year stays Ongoing until the student is promoted. Enrolled
    course rows whose term has started or ended are refreshed too."""
    stale_courses = frappe.db.sql(
        """
        SELECT DISTINCT c.parent
        FROM `tabStudent Enrollment Course` c
        INNER JOIN `tabAcademic Term` t ON t.name = c.academic_term
        WHERE c.parenttype = 'Student Enrollment'
          AND ((c.status = 'Ongoing' AND t.term_end_date < %(today)s)
            OR (c.status = 'Upcoming' AND t.term_start_date <= %(today)s))
        """,
        {"today": today()},
        pluck=True,
    )
    ended = frappe.db.sql(
        f"""
        SELECT l.parent
        FROM `tab{LOG_DOCTYPE}` l
        INNER JOIN `tabAcademic Term` t ON t.name = l.academic_term
        WHERE l.parenttype = 'Student Enrollment' AND l.status = 'Ongoing'
          AND t.term_end_date < %(today)s
          AND EXISTS (SELECT 1 FROM `tab{LOG_DOCTYPE}` n
                      WHERE n.parent = l.parent AND n.parenttype = 'Student Enrollment'
                        AND n.status = 'Upcoming')
        """,
        {"today": today()},
        pluck=True,
    )
    for name in dict.fromkeys(ended + stale_courses):
        doc = frappe.get_doc("Student Enrollment", name)
        if name in ended:
            rows = sorted(doc.academic_log, key=_log_sort_key)
            cur = next(i for i, r in enumerate(rows) if r.status == "Ongoing")
            nxt = next((r for r in rows[cur + 1:] if r.status == "Upcoming"
                        and r.academic_year == rows[cur].academic_year), None)
            if nxt:
                rows[cur].status, nxt.status = "Completed", "Ongoing"
        # validate() refreshes the course statuses
        doc.flags.skip_roster_sync = True
        doc.save(ignore_permissions=True)
    frappe.db.commit()


# ── Naming ────────────────────────────────────────────────────────────────────

def _enrollment_base_name(student):
    """The enrollment is named by the Student Master's Student ID
    (registration_id), falling back to the Student Master name until an ID is
    assigned."""
    student_id = (frappe.db.get_value("Student Master", student, "registration_id") or "").strip()
    return student_id or student


def make_enrollment_name(student, exclude=None):
    """Next free name for a new enrollment; a second programme (or a Student ID
    shared by two students) gets a numeric suffix."""
    base = _enrollment_base_name(student)
    name, n = base, 1
    while name != exclude and frappe.db.exists("Student Enrollment", name):
        n += 1
        name = f"{base}-{n}"
    return name


def sync_enrollment_names(students):
    """Rename the given students' enrollments to match their current Student ID.

    Called whenever a Student ID is assigned or changed. Student IDs can be
    swapped between students (the ID generator renumbers a whole batch), so a
    target may still be held by another enrollment in the same run: those wait
    until it is freed, and a cycle is broken through a temporary name.
    """
    from frappe.model.rename_doc import rename_doc

    rows = frappe.get_all(
        "Student Enrollment",
        filters={"student": ["in", list(students)]},
        fields=["name", "student"],
        order_by="student asc, creation asc",
    )
    pending, seen = {}, {}
    for row in rows:
        base = _enrollment_base_name(row.student)
        seen[base] = seen.get(base, 0) + 1
        target = base if seen[base] == 1 else f"{base}-{seen[base]}"
        if target != row.name:
            pending[row.name] = target

    def _rename(old, new):
        rename_doc("Student Enrollment", old, new, force=True,
                   ignore_permissions=True, show_alert=False, rebuild_search=False)

    while pending:
        progressed = False
        for old, new in list(pending.items()):
            if not frappe.db.exists("Student Enrollment", new):
                _rename(old, new)
                del pending[old]
                progressed = True
        if progressed:
            continue
        old, new = next(iter(pending.items()))
        del pending[old]
        if new in pending:
            # held by another enrollment that is itself moving: park this one
            tmp = f"{old}~{frappe.generate_hash(length=6)}"
            _rename(old, tmp)
            pending[tmp] = new
        else:
            # held by an enrollment outside this run: take the next free suffix
            free = make_enrollment_name(frappe.db.get_value("Student Enrollment", old, "student"), exclude=old)
            if free != old:
                _rename(old, free)


def _ordinal(n):
    n = cint(n)
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# ── Promotion ─────────────────────────────────────────────────────────────────

def promote_enrollment(enrollment_name, target_academic_year, repeat=False):
    """Move one Student Enrollment on to `target_academic_year`.

    Promotion (repeat=False): the current year's open log rows become
    Completed (its courses too) and rows for year + 1 are added.
    Repeat (repeat=True): the current year's rows become Redo, its courses
    Carry Forward, and rows for the same year are added. The new year's
    courses are added as the student is put in its classes. Student Master's
    academic year / current year follow (via on_update).

    Atomic: a failure rolls everything back. Safe to re-run: if the log already
    has the target academic year nothing changes.

    Returns (enrollment_name, moved)."""
    doc = frappe.get_doc("Student Enrollment", enrollment_name)

    if any(r.academic_year == target_academic_year and r.status not in CLOSED_LOG_STATUSES
           for r in doc.academic_log):
        return doc.name, False

    current = doc.current_log()
    if not current:
        frappe.throw(_("{0} has no Academic Log to promote from.").format(doc.student_name or doc.student))
    if _ay_start(target_academic_year) <= _ay_start(current.academic_year):
        frappe.throw(_("Target Academic Year {0} must start after {1}.").format(
            target_academic_year, current.academic_year))

    from_year = cint(current.year_no)
    next_year = from_year if repeat else from_year + 1
    duration = cint(frappe.db.get_value("Programme", doc.program, "program_duration"))
    if not repeat and duration and next_year > duration:
        frappe.throw(
            _("{0} is in the final year ({1} of {2}) of {3}. There is no next year to promote to.").format(
                doc.student_name or doc.student, from_year, duration, doc.program
            ),
            title=_("Final year"),
        )

    save_point = "se_promote_" + frappe.generate_hash(length=10)
    frappe.db.savepoint(save_point)
    try:
        for row in doc.academic_log:
            if row.academic_year != current.academic_year or cint(row.year_no) != from_year:
                continue
            if repeat and row.status != "Dropped":
                row.status = "Redo"
            elif row.status in OPEN_LOG_STATUSES:
                row.status = "Completed"
        for row in doc.enrolled_courses:
            if row.academic_year == current.academic_year and row.status not in MANUAL_COURSE_STATUSES:
                row.status = "Carry Forward" if repeat else "Completed"

        doc.add_year_log(target_academic_year, next_year)
        doc.status = "Enrolled"
        doc.save(ignore_permissions=True)
    except Exception:
        frappe.db.rollback(save_point=save_point)
        raise
    frappe.db.release_savepoint(save_point)
    return doc.name, True


def get_classes_for_year(program, academic_year, year_no):
    """The courses that have classes for this programme, academic year and
    year of study (one row per course and term)."""
    return frappe.db.sql(
        """
        SELECT cls.course, cls.course_name, cls.course_type, MAX(cls.credit) AS credit,
               cls.academic_year, cls.academic_term, cls.year_no
        FROM `tabClasses` cls
        WHERE cls.programme = %(program)s
          AND cls.academic_year = %(academic_year)s
          AND cls.year_no = %(year_no)s
        GROUP BY cls.course, cls.course_name, cls.course_type, cls.academic_year, cls.academic_term, cls.year_no
        ORDER BY cls.academic_term, cls.course_name
        """,
        {"program": program, "academic_year": academic_year, "year_no": cint(year_no)},
        as_dict=True,
    )


# ── Class → enrolled courses ──────────────────────────────────────────────────

# Class Enrolled Student status -> Student Enrollment Course status. Enrolled
# (still in the class) has none: the row follows the term's dates.
CLASS_TO_COURSE_STATUS = {
    "Completed": "Completed", "Carry Forward": "Carry Forward",
    "Withdrawn": "Withdrawn", "Dropped": "Dropped",
}


def sync_class_to_enrollments(class_doc, removed=False):
    """Write a Classes record onto the enrolled course row of each of its
    students: course, class, academic year, term, year, faculty, credits,
    grade and status. The row is added if the student did not have that
    course in that term yet. Students taken off the class (or every student,
    removed=True) only lose the class link; their course row and its status
    stay as history."""
    in_class = {} if removed else {r.student_enrollment: r for r in class_doc.enrolled_students}
    previous = class_doc.get_doc_before_save() if not removed else None
    was = {r.student_enrollment: r.status for r in (previous.enrolled_students if previous else [])}
    linked = set(frappe.get_all(
        "Student Enrollment Course",
        filters={"parenttype": "Student Enrollment", "class_name": class_doc.name},
        pluck="parent",
    ))

    for enrollment in set(in_class) | linked:
        if not frappe.db.exists("Student Enrollment", enrollment):
            continue
        doc = frappe.get_doc("Student Enrollment", enrollment)
        class_row = in_class.get(enrollment)
        row = next((r for r in doc.enrolled_courses if r.class_name == class_doc.name), None) \
            or next((r for r in doc.enrolled_courses if not r.class_name and r.course == class_doc.course
                     and r.academic_term == class_doc.academic_term), None)

        if not class_row:
            if row and row.class_name == class_doc.name:
                row.class_name = None
                doc.flags.skip_roster_sync = True
                doc.save(ignore_permissions=True)
            continue

        if not row:
            row = doc.append("enrolled_courses", {})
        status = CLASS_TO_COURSE_STATUS.get(class_row.status)
        if not status and row.status in MANUAL_COURSE_STATUSES and was.get(enrollment) == "Enrolled":
            # Still in the class: a status staff set on the course row stays.
            # (A class row moved back to Enrolled resets it to the term's.)
            status = row.status
        row.update({
            "course":        class_doc.course,
            "course_type":   class_doc.course_type,
            "academic_year": class_doc.academic_year,
            "academic_term": class_doc.academic_term,
            "year_no":       class_doc.year_no,
            "class_name":    class_doc.name,
            "faculty":       class_doc.faculty or row.faculty,
            "credits":       class_doc.credit or row.credits,
            "grade":         class_row.grade or row.grade,
            # validate() fills it from the term's dates when not set
            "status":        status or term_course_status(class_doc.academic_term),
        })
        doc.flags.skip_roster_sync = True
        doc.save(ignore_permissions=True)


# ── Whitelisted ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_year_courses(program, academic_year, year_no):
    """Courses that have classes for this programme, academic year and year."""
    return get_classes_for_year(program, academic_year, year_no)


@frappe.whitelist()
def get_academic_timeline(enrollment):
    """The enrollment's Academic Log, oldest first, for the timeline strip on
    the Student Enrollment form."""
    frappe.has_permission("Student Enrollment", "read", doc=enrollment, throw=True)
    rows = get_log(enrollment)
    names = [r.academic_term for r in rows if r.academic_term]
    term_names = dict(frappe.get_all(
        "Academic Term", filters={"name": ["in", names]}, fields=["name", "term_name"], as_list=True
    )) if names else {}
    for r in rows:
        r.term_name = term_names.get(r.academic_term)
    return rows


@frappe.whitelist()
def change_section(enrollment, to_section, reason=None):
    """Move a student to another section from the current term on.

    The Ongoing log row and every Upcoming row get `to_section`; the Ongoing
    row's Remarks note the move (from, to, date, user, reason). Completed rows
    keep their section. The enrollment, Student Master (with its Section
    Update Log) and the Class Configuration rosters follow."""
    doc = frappe.get_doc("Student Enrollment", enrollment)
    doc.check_permission("write")
    if not frappe.db.exists("Section", to_section):
        frappe.throw(_("Section {0} does not exist.").format(to_section))
    from_section = doc.section
    if to_section == from_section:
        frappe.throw(_("The student is already in section {0}.").format(to_section))
    current = next((r for r in doc.academic_log if r.status == "Ongoing"), None)
    if doc.status != "Enrolled" or not current:
        frappe.throw(_("Only an Enrolled student with an Ongoing term in the Academic Log can change section."))

    now = now_datetime()
    note = _("Section {0} → {1} on {2} by {3}").format(
        from_section or _("(none)"), to_section,
        frappe.utils.format_datetime(now), frappe.utils.get_fullname(frappe.session.user),
    )
    if reason:
        note += f": {reason}"

    current.section = to_section
    current.remarks = "\n".join(filter(None, [current.remarks, note]))
    doc.section = to_section  # Upcoming rows follow in sync_log_sections()
    doc.flags.section_change = True
    doc.save()

    doc._leave_section_rosters(from_section)
    frappe.db.set_value("Student Master", doc.student, "section", to_section)
    from slcm.slcm.doctype.student_master.student_master import _append_section_update_log
    _append_section_update_log(doc.student, to_section, "Success", note, now)
    doc.add_comment("Info", note)
    return {"section": to_section, "note": note}


@frappe.whitelist()
def bulk_update_enrollment_status(names, status):
    """Update status on multiple Student Enrollment records via save(),
    so validate() (duplicate/transition checks) still applies.
    """
    if isinstance(names, str):
        names = frappe.parse_json(names)

    updated, failed = [], []
    for name in names:
        try:
            doc = frappe.get_doc("Student Enrollment", name)
            doc.status = status
            doc.save()
            updated.append(name)
        except Exception as e:
            failed.append({"name": name, "error": str(e)})

    return {"updated": updated, "failed": failed}

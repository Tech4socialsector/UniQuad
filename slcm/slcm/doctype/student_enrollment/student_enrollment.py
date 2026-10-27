# Copyright (c) 2025, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from slcm.slcm.doctype.batch.batch import update_enrolled_count


class StudentEnrollment(Document):
    def autoname(self):
        self.name = make_enrollment_name(self.student, self.year_no)

    def validate(self):
        if not self.academic_year and self.batch:
            self.academic_year = frappe.db.get_value("Batch", self.batch, "academic_year")
        self.validate_year_no()
        self.validate_duplicate_enrollment()

    def before_save(self):
        self.fetch_courses()

    def on_update(self):
        """Sync Student Master when enrollment status changes."""
        self._sync_student_master_status()
        update_enrolled_count(self.batch)
        previous = self.get_doc_before_save()
        if previous and previous.batch and previous.batch != self.batch:
            update_enrolled_count(previous.batch)
        self._sync_class_configuration_rosters()

    def _sync_class_configuration_rosters(self):
        """Add/remove this student on the Class Configuration roster of every
        course they are enrolled/dropped in.

        Enrolling a student only attaches a Course Offering to
        `enrolled_courses` - nothing else in the system puts them on a
        Class Configuration's student list. Exams/results read that list
        (via the `Class Student` child table) to decide who is eligible for
        a course, so without this a properly enrolled student would be
        invisible to exams unless someone manually added them to the class.

        Matches by course + batch, and additionally by section when the
        student has one set - if a batch has multiple sections offering the
        same course and the student's section is not recorded, they end up
        on every matching section's roster since there is nothing to
        disambiguate with.
        """
        if not self.student or not self.batch:
            return

        for row in self.enrolled_courses:
            if not row.course:
                continue

            dropped = self.status == "Dropped" or row.status == "Dropped"

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

    def _remove_from_class_roster(self, class_config_name):
        cc = frappe.get_doc("Class Configuration", class_config_name)
        remaining = [r for r in cc.students if r.student != self.student]
        if len(remaining) == len(cc.students):
            return
        cc.set("students", remaining)
        cc.save(ignore_permissions=True)

    def after_delete(self):
        update_enrolled_count(self.batch)

    def fetch_courses(self):
        """Attach the year's Active Course Offerings (all terms) for this
        programme + academic year + year, unless courses were already added."""
        if self.enrolled_courses or not (self.program and self.academic_year and self.year_no):
            return

        for offering in get_offerings_for_year(self.program, self.academic_year, self.year_no):
            self.append("enrolled_courses", {
                "course_offering": offering.name,
                "course":          offering.course_title,
                "course_type":     offering.course_type or "",
                "credits":         offering.credit_value,
                "status":          "Enrolled",
            })

    def validate_year_no(self):
        if cint(self.year_no) < 1:
            frappe.throw(_("Year No must be 1 or more."))

        duration = cint(frappe.db.get_value("Programme", self.program, "program_duration"))
        if duration and cint(self.year_no) > duration:
            frappe.throw(
                _("Year No {0} is beyond the {1}-year duration of {2}.").format(
                    self.year_no, duration, self.program
                )
            )

    def validate_duplicate_enrollment(self):
        """One enrollment per student + programme + academic year."""
        existing = frappe.db.get_value(
            "Student Enrollment",
            {
                "student":       self.student,
                "program":       self.program,
                "academic_year": self.academic_year,
                "name":          ["!=", self.name],
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("{0} is already enrolled in {1} for {2} ({3}).").format(
                    self.student_name or self.student, self.program, self.academic_year,
                    frappe.bold(existing),
                )
            )

    def _sync_student_master_status(self):
        """Reflect this enrollment's status on Student Master.

        Status changes are unrestricted (including moving away from
        Completed/Dropped), so this always sets Student Master to match the
        current status rather than only reacting to Dropped/Completed.
        """
        if not self.student:
            return
        if self.status == "Dropped":
            frappe.db.set_value("Student Master", self.student, {
                "student_status": "Dropped",
                "academic_status": "Inactive",
            })
        elif self.status == "Completed":
            frappe.db.set_value("Student Master", self.student, {
                "student_status": "Graduated",
            })
        else:
            frappe.db.set_value("Student Master", self.student, {
                "student_status": "Active",
                "academic_status": "Active",
            })


def _enrollment_base_name(student, year_no):
    """The enrollment is named by the Student Master's Student ID
    (registration_id), falling back to the Student Master name until an ID is
    assigned. A student has one enrollment per year, so Year 1 is the bare ID
    and later years add "-Y<n>"."""
    student_id = (frappe.db.get_value("Student Master", student, "registration_id") or "").strip()
    student_id = student_id or student
    return student_id if cint(year_no) <= 1 else f"{student_id}-Y{cint(year_no)}"


def make_enrollment_name(student, year_no, exclude=None):
    """Next free name for a new enrollment; a repeated year (or a Student ID
    shared by two students) gets a numeric suffix."""
    base = _enrollment_base_name(student, year_no)
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
        fields=["name", "student", "year_no"],
        order_by="student asc, year_no asc, creation asc",
    )
    pending, seen = {}, {}
    for row in rows:
        base = _enrollment_base_name(row.student, row.year_no)
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
            free = make_enrollment_name(*frappe.db.get_value(
                "Student Enrollment", old, ["student", "year_no"]), exclude=old)
            if free != old:
                _rename(old, free)


def _ordinal(n):
    n = cint(n)
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def create_next_year_enrollment(enrollment_name, target_academic_year):
    """Promote one Student Enrollment to the next year of study.

    Marks `enrollment_name` Completed (nothing else on it changes) and creates
    a NEW enrollment with the same programme, batch and section, in
    `target_academic_year`, with year_no + 1. Student Master's academic year
    and current year are moved along with it.

    Atomic: a failure rolls everything back. Safe to re-run: if the student
    already has an enrollment for this programme in the target academic year,
    nothing changes and that enrollment is returned.

    Returns (enrollment_name, created)."""
    old = frappe.get_doc("Student Enrollment", enrollment_name)

    existing = frappe.db.get_value(
        "Student Enrollment",
        {"student": old.student, "program": old.program, "academic_year": target_academic_year},
        "name",
    )
    if existing:
        return existing, False

    next_year = cint(old.year_no) + 1
    duration = cint(frappe.db.get_value("Programme", old.program, "program_duration"))
    if duration and next_year > duration:
        frappe.throw(
            _("{0} is in the final year ({1} of {2}) of {3}. There is no next year to promote to.").format(
                old.student_name or old.student, old.year_no, duration, old.program
            ),
            title=_("Final year"),
        )

    save_point = "se_promote_" + frappe.generate_hash(length=10)
    frappe.db.savepoint(save_point)
    try:
        # Completing the old enrollment flips Student Master to "Graduated"
        # until the new Enrolled one sets it back to "Active".
        old.status = "Completed"
        old.save(ignore_permissions=True)

        new = frappe.new_doc("Student Enrollment")
        new.update({
            "student":         old.student,
            "program":         old.program,
            "batch":           old.batch,
            "section":         old.section,
            "academic_year":   target_academic_year,
            "year_no":         next_year,
            "faculty_advisor": old.faculty_advisor,
            "status":          "Enrolled",
            "enrollment_date": frappe.db.get_value("Academic Year", target_academic_year, "year_start_date")
                               or frappe.utils.today(),
        })
        new.insert(ignore_permissions=True)

        frappe.db.set_value("Student Master", old.student, {
            "academic_year": target_academic_year,
            "current_year":  str(next_year),
            "year_of_study": f"{_ordinal(next_year)} Year",
        }, update_modified=False)
    except Exception:
        frappe.db.rollback(save_point=save_point)
        raise
    frappe.db.release_savepoint(save_point)
    return new.name, True


def get_offerings_for_year(program, academic_year, year_no):
    """Active Course Offerings of every term of `academic_year` for this
    programme and year of study, with the course type."""
    return frappe.db.sql(
        """
        SELECT co.name, co.course_title, co.credit_value, c.course_type
        FROM `tabCourse Offering` co
        LEFT JOIN `tabCourse` c ON c.name = co.course_title
        WHERE co.program = %(program)s
          AND co.academic_year = %(academic_year)s
          AND co.year_no = %(year_no)s
          AND co.status = 'Active'
        ORDER BY co.term_name, co.course_name
        """,
        {"program": program, "academic_year": academic_year, "year_no": cint(year_no)},
        as_dict=True,
    )


@frappe.whitelist()
def get_year_courses(program, academic_year, year_no):
    """Course Offerings to pre-fill on the Student Enrollment form."""
    return get_offerings_for_year(program, academic_year, year_no)


@frappe.whitelist()
def get_other_terms(student, exclude=None):
    """List a student's Student Enrollment records (one per academic year),
    most recent academic year first, for the Academic Timeline on the Student
    Enrollment form. Pass exclude=None to include every year (the form marks
    the one currently being viewed); pass a docname to omit just that record."""
    if not student:
        return []

    enrollments = frappe.get_all(
        "Student Enrollment",
        filters={"student": student, "docstatus": ["<", 2]},
        fields=["name", "academic_year", "year_no", "status"],
    )

    ay_names = {e.academic_year for e in enrollments if e.academic_year}
    ay_start = {}
    if ay_names:
        for ay in frappe.get_all(
            "Academic Year",
            filters={"name": ["in", list(ay_names)]},
            fields=["name", "year_start_date"],
        ):
            ay_start[ay.name] = ay.year_start_date

    # str() so enrollments without a start date ("") compare with real dates;
    # ISO date strings sort chronologically.
    enrollments.sort(key=lambda e: str(ay_start.get(e.academic_year) or ""), reverse=True)

    return [e for e in enrollments if e.name != exclude]


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

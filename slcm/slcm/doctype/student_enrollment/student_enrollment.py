# Copyright (c) 2025, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class StudentEnrollment(Document):
    def validate(self):
        self.validate_duplicate_enrollment()

    def before_save(self):
        self.fetch_program_and_courses()

    def on_update(self):
        """Sync Student Master when enrollment status changes."""
        self._sync_student_master_status()
        self._refresh_batch_enrolled_count(self.batch)
        if self.has_value_changed("batch"):
            previous = self.get_doc_before_save()
            if previous and previous.batch and previous.batch != self.batch:
                self._refresh_batch_enrolled_count(previous.batch)
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
        self._refresh_batch_enrolled_count(self.batch)

    def fetch_program_and_courses(self):
        if not self.program and self.batch:
            self.program = frappe.db.get_value("Batch", self.batch, "program")

        if self.program and self.batch and not self.enrolled_courses:
            offerings = frappe.get_all(
                "Course Offering",
                filters={"cohort": self.batch, "status": "Active"},
                fields=["name", "course_title"],
            )
            for offering in offerings:
                course_type = frappe.db.get_value("Course", offering.course_title, "course_type")
                self.append("enrolled_courses", {
                    "course_offering": offering.name,
                    "course":          offering.course_title,
                    "course_type":     course_type or "",
                    "status":          "Enrolled",
                })

    def validate_duplicate_enrollment(self):
        """Prevent duplicate enrollment for same student + batch + academic_year."""
        filters = {
            "student":       self.student,
            "batch":         self.batch,
            "academic_year": self.academic_year,
            "docstatus":     ["<", 2],
        }
        existing = frappe.db.exists("Student Enrollment", filters)
        if existing and existing != self.name:
            frappe.throw(_("Enrollment already exists for this student in the selected batch"))

    def _refresh_batch_enrolled_count(self, batch):
        """Recompute the Batch's total_enrolled_count from actual enrollments."""
        if not batch or not frappe.db.exists("Batch", batch):
            return
        count = frappe.db.count(
            "Student Enrollment",
            {
                "batch": batch,
                "status": ["not in", ["Dropped"]],
                "docstatus": ["<", 2],
            },
        )
        frappe.db.set_value("Batch", batch, "total_enrolled_count", count, update_modified=False)

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


@frappe.whitelist()
def get_other_terms(student, exclude=None):
    """List a student's Student Enrollment records across terms, most recent
    academic year first, for the Academic Timeline on the Student Enrollment
    form. Pass exclude=None to include every term (the form marks the one
    currently being viewed); pass a docname to omit just that record."""
    if not student:
        return []

    enrollments = frappe.get_all(
        "Student Enrollment",
        filters={"student": student, "docstatus": ["<", 2]},
        fields=["name", "academic_year", "term_name", "status"],
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

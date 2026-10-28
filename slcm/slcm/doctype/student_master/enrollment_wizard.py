# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Server side of the Student Master list → Action → Enroll wizard.

Steps (see public/js/enrollment_wizard.js):
    1. Academic setup  - academic year (current by default), term, programme,
                         batch and year of study
    2. Students        - registration Completed, not yet enrolled in the programme
    3. Student ID      - a format such as M26#### (the #s are the running
                         number), assigned in alphabetical order
    4. Sections        - Mid-off / One-by-one (split by section capacities),
                         Manual, or Upload
    5. Summary         - enroll_students() saves everything
"""

import base64
import io
import re

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime, today

from slcm.slcm.doctype.student_master.student_master import (
    _append_section_update_log,
    _sync_enrollment_names,
)

ALLOWED_ROLES = ("System Manager", "slcm_Registrar")


def _check_permission():
    if frappe.session.user != "Administrator" and not set(ALLOWED_ROLES) & set(frappe.get_roles()):
        frappe.throw(_("You are not permitted to enroll students."), frappe.PermissionError)


def _full_name(s):
    return " ".join(filter(None, [s.get("first_name"), s.get("middle_name"), s.get("last_name")])).strip()


def _alpha_key(s):
    return (_full_name(s).lower(), s.get("name") or "")


def _parse_id_format(id_format):
    """'M26####' -> ('M26', 4, ''). Exactly one run of #s marks the number."""
    match = re.fullmatch(r"([^#]*)(#+)([^#]*)", (id_format or "").strip())
    if not match:
        frappe.throw(_("Student ID format must contain one run of # for the running number, e.g. M26####."))
    return match.group(1), len(match.group(2)), match.group(3)


def _existing_ids(prefix, width, suffix, exclude=()):
    """{number: student} of Student IDs already using this format."""
    pattern = re.compile(rf"{re.escape(prefix)}(\d{{{width}}}){re.escape(suffix)}")
    out = {}
    for r in frappe.get_all(
        "Student Master",
        filters={"registration_id": ["like", f"{prefix}%{suffix}"]},
        fields=["name", "registration_id"],
    ):
        match = pattern.fullmatch(r.registration_id or "")
        if match and r.name not in exclude:
            out[int(match.group(1))] = r.name
    return out


# ── Step 1 ────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_wizard_defaults():
    """Current academic year and its current term."""
    academic_year = frappe.db.get_value("Academic Year", {"is_current_year": 1}, "name") \
        or frappe.db.get_value("Academic Year", {}, "name", order_by="year_start_date desc")
    return {"academic_year": academic_year, **get_year_defaults(academic_year)}


@frappe.whitelist()
def get_year_defaults(academic_year):
    """Default term (the one running today, else the first) and batch of an academic year."""
    if not academic_year:
        return {"academic_term": None, "batch": None}
    terms = frappe.get_all(
        "Academic Term",
        filters={"academic_year": academic_year, "status": "Active"},
        fields=["name", "term_start_date", "term_end_date"],
        order_by="term_no asc",
    )
    now = getdate(today())
    term = next((t.name for t in terms if getdate(t.term_start_date) <= now <= getdate(t.term_end_date)), None)
    return {
        "academic_term": term or (terms[0].name if terms else None),
        "batch": frappe.db.get_value("Batch", {"academic_year": academic_year}, "name", order_by="creation desc"),
    }


# ── Step 2 ────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_enrollable_students(programme, academic_year):
    """Students with registration Completed in `academic_year` (Student
    Master's Academic Year), of this programme (or with no programme set
    yet), who are not enrolled in it yet; alphabetical."""
    _check_permission()
    if not (programme and academic_year):
        return []
    enrolled = set(frappe.get_all("Student Enrollment", filters={"program": programme}, pluck="student"))
    students = frappe.get_all(
        "Student Master",
        filters={"registration_status": "Completed", "academic_year": academic_year},
        or_filters=[
            ["programme_of_study", "=", programme],
            ["programme_of_study", "is", "not set"],
        ],
        fields=["name", "first_name", "middle_name", "last_name", "registration_id",
                "gender", "batch", "section", "programme_of_study"],
    )
    out = []
    for s in sorted(students, key=_alpha_key):
        if s.name in enrolled:
            continue
        s.student_name = _full_name(s)
        out.append(s)
    return out


# ── Step 3 ────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def preview_student_ids(students, id_format, start_from=None, renumber_existing=0):
    """Order `students` alphabetically and give each a Student ID in
    `id_format`. Students who already have an ID keep it unless
    renumber_existing. Numbering starts at `start_from`, by default right
    after the highest number already used with this format."""
    _check_permission()
    students = frappe.parse_json(students) if isinstance(students, str) else students
    prefix, width, suffix = _parse_id_format(id_format)
    renumber_existing = cint(renumber_existing)

    rows = frappe.get_all(
        "Student Master",
        filters={"name": ["in", students or []]},
        fields=["name", "first_name", "middle_name", "last_name", "registration_id"],
    )
    rows.sort(key=_alpha_key)

    to_number = {r.name for r in rows if renumber_existing or not r.registration_id}
    taken = _existing_ids(prefix, width, suffix, exclude=to_number)
    number = cint(start_from) or (max(taken, default=0) + 1)

    out = []
    for r in rows:
        new_id = None
        if r.name in to_number:
            while number in taken:
                number += 1
            if len(str(number)) > width:
                frappe.throw(_("Student ID format {0} has room for {1} digits only; {2} students do not fit.").format(
                    id_format, width, len(to_number)))
            new_id = f"{prefix}{number:0{width}d}{suffix}"
            taken[number] = r.name
            number += 1
        out.append({
            "student": r.name,
            "student_name": _full_name(r),
            "current_id": r.registration_id or "",
            "student_id": new_id or r.registration_id or "",
            "is_new": bool(new_id),
        })
    return out


# ── Step 4 (Upload) ───────────────────────────────────────────────────────────

@frappe.whitelist()
def download_section_template(rows):
    """xlsx of the wizard's students (alphabetical, with their Student ID) and
    an empty Section column to fill in."""
    _check_permission()
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sections"
    headers = ["Row Key", "Student ID", "Student Name", "Section"]
    ws.append(headers)
    for ci in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=ci)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="3949AB")
    for r in rows or []:
        ws.append([r.get("student"), r.get("student_id") or "", r.get("student_name") or "", r.get("section") or ""])
    ws.column_dimensions["A"].hidden = True
    for col, width in zip("BCD", [16, 32, 14]):
        ws.column_dimensions[col].width = width

    output = io.BytesIO()
    wb.save(output)
    return {
        "filename": "enrollment_sections.xlsx",
        "content":  base64.b64encode(output.getvalue()).decode("utf-8"),
        "mime":     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }


@frappe.whitelist()
def read_section_upload(file_url):
    """{student: section} from a filled-in section template."""
    _check_permission()
    import openpyxl

    file_doc = frappe.get_doc("File", {"file_url": file_url})
    file_doc.check_permission("read")
    ws = openpyxl.load_workbook(file_doc.get_full_path(), data_only=True).active

    sections, unknown = {}, set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0] or len(row) < 4 or not row[3]:
            continue
        section = str(row[3]).strip()
        if not frappe.db.exists("Section", section):
            unknown.add(section)
        sections[str(row[0]).strip()] = section
    return {"sections": sections, "unknown": sorted(unknown)}


# ── Step 5 ────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def enroll_students(data):
    """Enroll the wizard's students.

    data: academic_year, academic_term, programme, batch, year_no and rows
    [{student, student_id, section}]. For each student: Student Master gets
    the Student ID, section, batch, programme and academic year, then a
    Student Enrollment is created whose Academic Log starts at the chosen
    year and term. Each student is saved on its own: one failure does not
    stop the rest. Returns {success: [...], failed: [{student, reason}]}."""
    _check_permission()
    data = frappe._dict(frappe.parse_json(data) if isinstance(data, str) else data)
    for field, label in (("academic_year", _("Academic Year")), ("programme", _("Programme")),
                         ("batch", _("Batch"))):
        if not data.get(field):
            frappe.throw(_("{0} is required.").format(label))
    if data.academic_term and frappe.db.get_value("Academic Term", data.academic_term, "academic_year") != data.academic_year:
        frappe.throw(_("Academic Term {0} is not in {1}.").format(data.academic_term, data.academic_year))
    year_no = cint(data.year_no) or 1

    rows = data.rows or []
    ids = [r.get("student_id") for r in rows if r.get("student_id")]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        frappe.throw(_("Student ID used more than once: {0}").format(", ".join(sorted(dupes))))

    success, failed, renamed = [], [], []
    now = now_datetime()
    for r in rows:
        student = r.get("student")
        save_point = "enroll_wizard_" + frappe.generate_hash(length=8)
        frappe.db.savepoint(save_point)
        try:
            sm = frappe.db.get_value(
                "Student Master", student,
                ["name", "first_name", "middle_name", "last_name", "registration_status", "registration_id"],
                as_dict=True,
            )
            if not sm:
                raise frappe.ValidationError(_("Student Master not found."))
            if sm.registration_status != "Completed":
                raise frappe.ValidationError(_("Registration status is {0}, not Completed.").format(sm.registration_status))
            if frappe.db.exists("Student Enrollment", {"student": student, "program": data.programme}):
                raise frappe.ValidationError(_("Already enrolled in {0}.").format(data.programme))

            new_id = (r.get("student_id") or "").strip()
            if new_id and new_id != sm.registration_id:
                holder = frappe.db.get_value("Student Master", {"registration_id": new_id, "name": ["!=", student]})
                if holder:
                    raise frappe.ValidationError(_("Student ID {0} is already used by {1}.").format(new_id, holder))
            section = (r.get("section") or "").strip()
            if section and not frappe.db.exists("Section", section):
                raise frappe.ValidationError(_("Section {0} does not exist.").format(section))

            values = {
                "batch": data.batch,
                "programme_of_study": data.programme,
                "academic_year": data.academic_year,
            }
            if new_id:
                values["registration_id"] = new_id
            if section:
                values["section"] = section
            frappe.db.set_value("Student Master", student, values)
            if section:
                _append_section_update_log(student, section, "Success",
                    _("Section set to '{0}' on enrollment.").format(section), now)

            enrollment = frappe.get_doc({
                "doctype":         "Student Enrollment",
                "student":         student,
                "student_name":    _full_name(sm),
                "program":         data.programme,
                "batch":           data.batch,
                "section":         section or None,
                "status":          "Enrolled",
                "enrollment_date": today(),
            })
            enrollment.add_year_log(data.academic_year, year_no, data.academic_term)
            # Roles were checked above; Registrars cannot create enrollments directly.
            enrollment.insert(ignore_permissions=True)

            if new_id and new_id != sm.registration_id:
                renamed.append(student)
            success.append({"student": student, "enrollment": enrollment.name})
        except Exception as e:
            frappe.db.rollback(save_point=save_point)
            frappe.clear_messages()
            if not isinstance(e, frappe.ValidationError):
                frappe.log_error(title=f"Enrollment wizard: {student}", message=frappe.get_traceback())
            failed.append({"student": student, "reason": frappe.utils.strip_html(str(e)) or e.__class__.__name__})
        else:
            frappe.db.release_savepoint(save_point)

    # Other enrollments of these students follow the new Student ID.
    _sync_enrollment_names(renamed)
    frappe.db.commit()
    return {"success": success, "failed": failed}

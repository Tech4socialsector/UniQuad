# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe


# ── Helpers ─────────────────────────────────────────────────────────────────────

YEAR_BASED_PRINT_FORMAT = "Year Based Transcript"
STANDARD_PRINT_FORMAT = "Student Transcript"
BROKEN_YEAR_BASED_CONTEXT_LINE = (
    "{% set ctx = frappe.get_attr('slcm.slcm.doctype.student_transcript.student_transcript."
    "get_year_based_transcript_context')(doc.student) %}"
)
SAFE_YEAR_BASED_CONTEXT_LINE = "{% set ctx = get_year_based_transcript_context(doc.student) %}"
STANDARD_OLD_COURSE_HEADER = """<tr>
                <th>Course</th>
                <th class="center">Grade</th>
              </tr>"""
STANDARD_NEW_COURSE_HEADER = """<tr>
                <th class="center" style="width: 15%;">Course<br>No.</th>
                <th>Prescribed Courses</th>
                <th class="center" style="width: 20%;">Grade<br>Obtained</th>
              </tr>"""
STANDARD_OLD_COURSE_ROW = """<tr>
                <td>{{ c.course_name }}</td>
                <td class="center {% if c.is_failed %}grade-failed{% endif %}">{{ c.grade_html | safe }}</td>
              </tr>"""
STANDARD_NEW_COURSE_ROW = """<tr>
                <td class="center">{{ c.course_number }}</td>
                <td>{{ c.course_name }}</td>
                <td class="center {% if c.is_failed %}grade-failed{% endif %}">{{ c.grade_html | safe }}</td>
              </tr>"""
STANDARD_STYLE_REPLACEMENTS = {
    ".page-wrap { width: 100%; padding: 0; }":
        ".page-wrap { width: 100%; padding: 12px 14px; border: 1.5px solid #d8c8c2; box-sizing: border-box; }",
    ".student-row { display: flex; align-items: flex-start; gap: 18px; padding: 8px 14px 6px; border-bottom: 1px solid #e0e0e0; }":
        ".student-row { display: flex; align-items: flex-start; padding: 8px 14px 6px; border-bottom: 1px solid #e0e0e0; }",
    ".student-photo { width: 50px; height: 60px; object-fit: cover; border-radius: 2px; border: 1px solid #ddd; flex-shrink: 0; }":
        ".student-photo { width: 50px; height: 60px; object-fit: cover; border-radius: 2px; border: 1px solid #ddd; flex-shrink: 0; margin-right: 18px; }",
    ".student-photo-placeholder { width: 50px; height: 60px; background: #e8eaed; border-radius: 2px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 7pt; color: #aaa; }":
        ".student-photo-placeholder { width: 50px; height: 60px; background: #e8eaed; border-radius: 2px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 7pt; color: #aaa; margin-right: 18px; }",
    ".student-info { flex: 1; }":
        ".student-info { flex: 1; min-width: 0; }",
}
STANDARD_YEAR_REPLACEMENTS = {
    "{% set semesters = ctx.semesters %}":
        "{% set years = ctx.years %}",
    "{% if semesters %}":
        "{% if years %}",
    "{% for sem in semesters %}":
        "{% for year in years %}",
    "{{ sem.label }}":
        "{{ year.label }}",
    "{% for c in sem.courses %}":
        "{% for c in year.courses %}",
    """
          {% if t.show_semester_wise and sem.sgpa %}
          <div class="sgpa-row">Semester GPA (SGPA): <span>{{ sem.sgpa }}</span></div>
          {% endif %}""":
        "",
}


def _get_year_based_template_html():
    path = frappe.get_app_path(
        "slcm",
        "slcm",
        "print_format",
        "year_based_transcript",
        "year_based_transcript.html",
    )
    with open(path, encoding="utf-8") as template_file:
        return template_file.read().replace(
            BROKEN_YEAR_BASED_CONTEXT_LINE,
            SAFE_YEAR_BASED_CONTEXT_LINE,
        )


def _sync_year_based_print_format_template():
    """Patch the database Print Format if it still has the old unsafe Jinja call."""
    if not frappe.db.exists("Print Format", YEAR_BASED_PRINT_FORMAT):
        return

    html = frappe.db.get_value("Print Format", YEAR_BASED_PRINT_FORMAT, "html") or ""
    if BROKEN_YEAR_BASED_CONTEXT_LINE not in html:
        return

    frappe.db.set_value(
        "Print Format",
        YEAR_BASED_PRINT_FORMAT,
        "html",
        html.replace(BROKEN_YEAR_BASED_CONTEXT_LINE, SAFE_YEAR_BASED_CONTEXT_LINE),
        update_modified=False,
    )
    frappe.db.commit()


def _sync_standard_print_format_template():
    """Patch the database Student Transcript Print Format with the three-column course table."""
    if not frappe.db.exists("Print Format", STANDARD_PRINT_FORMAT):
        return

    html = frappe.db.get_value("Print Format", STANDARD_PRINT_FORMAT, "html") or ""
    updated = html.replace(STANDARD_OLD_COURSE_HEADER, STANDARD_NEW_COURSE_HEADER)
    updated = updated.replace(STANDARD_OLD_COURSE_ROW, STANDARD_NEW_COURSE_ROW)
    for old_style, new_style in STANDARD_STYLE_REPLACEMENTS.items():
        updated = updated.replace(old_style, new_style)
    for old_year_text, new_year_text in STANDARD_YEAR_REPLACEMENTS.items():
        updated = updated.replace(old_year_text, new_year_text)

    if updated == html:
        return

    frappe.db.set_value(
        "Print Format",
        STANDARD_PRINT_FORMAT,
        "html",
        updated,
        update_modified=False,
    )
    frappe.db.commit()


def _build_filters(search="", programme="", course="", academic_year="", batch="",
                   student_status="", department=""):
    """Build WHERE clause and params for student list queries."""
    conditions = []
    params = {}

    if search:
        conditions.append(
            "(sm.registration_id LIKE %(search)s"
            " OR sm.first_name LIKE %(search)s"
            " OR sm.last_name LIKE %(search)s"
            " OR sm.email LIKE %(search)s"
            " OR CONCAT(sm.first_name,' ',IFNULL(sm.last_name,'')) LIKE %(search)s)"
        )
        params["search"] = f"%{search}%"

    if programme:
        conditions.append("sm.programme_of_study = %(programme)s")
        params["programme"] = programme

    if department:
        conditions.append("sm.department = %(department)s")
        params["department"] = department

    if batch:
        conditions.append("sm.programme = %(batch)s")
        params["batch"] = batch

    if academic_year:
        conditions.append("sm.academic_year = %(academic_year)s")
        params["academic_year"] = academic_year

    if student_status:
        conditions.append("sm.academic_status = %(student_status)s")
        params["student_status"] = student_status

    if course:
        conditions.append(
            "EXISTS ("
            "  SELECT 1 FROM `tabStudent Enrollment Course` sec"
            "  JOIN `tabStudent Enrollment` se ON se.name = sec.parent"
            "  WHERE se.student = sm.name AND sec.course = %(course)s"
            ")"
        )
        params["course"] = course

    where = "WHERE 1=1"
    if conditions:
        where += " AND " + " AND ".join(conditions)

    return where, params


# ── Public API ───────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_students(
    search="", programme="", course="", academic_year="", batch="",
    student_status="", department="",
    page=1, page_length=50,
    sort_by="registration_id", sort_order="asc"
):
    """
    Return a paginated list of students with transcript status columns.
    Each row contains:
      student, student_name, registration_id, email, photo,
      programme, programme_name, batch_year, academic_year,
      department, department_name,
      learning_pathways,
      earned_credits, total_credits,
      cgpa,
      interim_transcript, final_transcript
    """
    page        = int(page)
    page_length = int(page_length)
    offset      = (page - 1) * page_length

    sort_map = {
        "student_name":    "CONCAT(sm.first_name,' ',IFNULL(sm.last_name,''))",
        "registration_id": "sm.registration_id",
        "cgpa":            "sm.current_cgpa",
    }
    sort_col = sort_map.get(sort_by, "sm.registration_id")
    sort_dir = "DESC" if sort_order == "desc" else "ASC"

    where, params = _build_filters(
        search=search, programme=programme, course=course,
        academic_year=academic_year, batch=batch,
        student_status=student_status, department=department,
    )
    params.update({"lim": page_length, "off": offset})

    students = frappe.db.sql(
        f"""
        SELECT
            sm.name                                              AS student,
            CONCAT(sm.first_name,' ',IFNULL(sm.last_name,''))   AS student_name,
            sm.registration_id,
            sm.email,
            sm.passport_size_photo                              AS photo,
            sm.programme_of_study                               AS programme,
            sm.programme                                        AS batch_year,
            sm.current_term,
            sm.academic_year,
            sm.department,
            sm.current_cgpa                                     AS cgpa,
            sm.student_status
        FROM `tabStudent Master` sm
        {where}
        ORDER BY {sort_col} {sort_dir}
        LIMIT %(lim)s OFFSET %(off)s
        """,
        params,
        as_dict=True,
    )

    # Remove pagination params before reusing for count query
    count_params = {k: v for k, v in params.items() if k not in ("lim", "off")}
    total_row = frappe.db.sql(
        f"""
        SELECT COUNT(sm.name) AS cnt
        FROM `tabStudent Master` sm
        {where}
        """,
        count_params,
        as_dict=True,
    )

    student_names = [s["student"] for s in students]

    # ── Fetch programme display names ──────────────────────────────────────────
    prog_names = {}
    if student_names:
        prog_ids = list({s["programme"] for s in students if s.get("programme")})
        if prog_ids:
            rows = frappe.db.sql(
                "SELECT name, program_name FROM `tabProgramme` WHERE name IN %(ids)s",
                {"ids": prog_ids},
                as_dict=True,
            )
            prog_names = {r["name"]: r["program_name"] for r in rows}

    # ── Fetch department display names ─────────────────────────────────────────
    dept_names = {}
    if student_names:
        dept_ids = list({s["department"] for s in students if s.get("department")})
        if dept_ids:
            rows = frappe.db.sql(
                "SELECT name, department_name FROM `tabDepartment` WHERE name IN %(ids)s",
                {"ids": dept_ids},
                as_dict=True,
            )
            dept_names = {r["name"]: r["department_name"] for r in rows}

    # ── Fetch credit totals from Student Enrollment Course ─────────────────────
    # earned = credits for courses not dropped; total = all credits in enrollment
    credit_map = {}
    if student_names:
        credit_rows = frappe.db.sql(
            """
            SELECT
                se.student,
                SUM(CASE WHEN sec.status != 'Dropped' THEN IFNULL(sec.credits, 0) ELSE 0 END) AS earned,
                SUM(IFNULL(sec.credits, 0))                                                    AS total
            FROM `tabStudent Enrollment` se
            JOIN `tabStudent Enrollment Course` sec ON sec.parent = se.name
            WHERE se.student IN %(students)s
            GROUP BY se.student
            """,
            {"students": student_names},
            as_dict=True,
        )
        credit_map = {
            r["student"]: {
                "earned": int(r["earned"] or 0),
                "total":  int(r["total"] or 0),
            }
            for r in credit_rows
        }

    # ── Fetch learning pathways (via Student Enrollment → Cohort → Program) ────
    pathway_map = {}
    if student_names:
        pw_rows = frappe.db.sql(
            """
            SELECT
                se.student,
                se.program,
                p.program_name
            FROM `tabStudent Enrollment` se
            LEFT JOIN `tabProgramme` p ON p.name = se.program
            WHERE se.student IN %(students)s
            ORDER BY se.creation ASC
            """,
            {"students": student_names},
            as_dict=True,
        )
        for r in pw_rows:
            if r.get("program"):
                pathway_map.setdefault(r["student"], []).append({
                    "program":      r["program"],
                    "program_name": r.get("program_name") or r["program"],
                    "type":         "Major",
                })

    # ── Fetch transcript generation status ─────────────────────────────────────
    transcript_map = {}
    if student_names:
        try:
            tr_rows = frappe.db.sql(
                """
                SELECT student, transcript_type, status, generation_date
                FROM `tabStudent Transcript`
                WHERE student IN %(students)s
                ORDER BY creation DESC
                """,
                {"students": student_names},
                as_dict=True,
            )
            for r in tr_rows:
                # Keep most recent record per (student, type)
                key = r["transcript_type"]
                student_map = transcript_map.setdefault(r["student"], {})
                if key not in student_map:
                    student_map[key] = {
                        "status": r["status"],
                        "date":   str(r.get("generation_date") or ""),
                    }
        except Exception:
            # Table may not exist yet (before bench migrate)
            pass

    # ── Assemble final rows ────────────────────────────────────────────────────
    for s in students:
        sid = s["student"]
        s["programme_name"]  = prog_names.get(s.get("programme"), s.get("programme") or "")
        s["department_name"] = dept_names.get(s.get("department"), s.get("department") or "")
        s["learning_pathways"] = pathway_map.get(sid, [])
        credits = credit_map.get(sid, {})
        s["earned_credits"] = credits.get("earned", 0)
        s["total_credits"]  = credits.get("total", 0)
        tr = transcript_map.get(sid, {})
        s["interim_transcript"] = tr.get("Interim", {}).get("status", "")
        s["final_transcript"]   = tr.get("Final", {}).get("status", "")

    return {
        "students": students,
        "total":    total_row[0]["cnt"] if total_row else 0,
    }


@frappe.whitelist()
def get_transcript_stats(search="", programme="", course="", academic_year="",
                         batch="", student_status="", department=""):
    """Return aggregate transcript counts for the current filter set."""
    where, params = _build_filters(
        search=search, programme=programme, course=course,
        academic_year=academic_year, batch=batch,
        student_status=student_status, department=department,
    )
    try:
        row = frappe.db.sql(
            f"""
            SELECT
                COUNT(DISTINCT sm.name) AS total_students,
                COUNT(DISTINCT CASE WHEN it.status = 'Generated' THEN sm.name END) AS interim_generated,
                COUNT(DISTINCT CASE WHEN ft.status = 'Generated' THEN sm.name END) AS final_generated
            FROM `tabStudent Master` sm
            LEFT JOIN `tabStudent Transcript` it
                ON it.student = sm.name AND it.transcript_type = 'Interim'
            LEFT JOIN `tabStudent Transcript` ft
                ON ft.student = sm.name AND ft.transcript_type = 'Final'
            {where}
            """,
            params,
            as_dict=True,
        )
        return row[0] if row else {"total_students": 0, "interim_generated": 0, "final_generated": 0}
    except Exception:
        return {"total_students": 0, "interim_generated": 0, "final_generated": 0}


@frappe.whitelist()
def get_filter_options():
    """Return filter dropdown options: programmes, departments, academic_years, batches, courses, student_statuses."""
    programmes = frappe.db.sql(
        "SELECT name, program_name FROM `tabProgramme` ORDER BY program_name ASC LIMIT 500",
        as_dict=True,
    )
    departments = frappe.db.sql(
        "SELECT name, department_name FROM `tabDepartment` ORDER BY department_name ASC LIMIT 200",
        as_dict=True,
    )
    academic_years = frappe.db.sql(
        "SELECT DISTINCT academic_year FROM `tabStudent Master`"
        " WHERE academic_year IS NOT NULL AND academic_year != ''"
        " ORDER BY academic_year DESC LIMIT 50",
        as_dict=True,
    )
    # Batch options come from Batch itself, not the stale/unpopulated
    # Student Master.batch_year column — students link to their Batch via the
    # (confusingly named) Student Master.programme field.
    batches = frappe.db.sql(
        "SELECT name, batch_name FROM `tabBatch` ORDER BY batch_name ASC LIMIT 500",
        as_dict=True,
    )
    courses = frappe.db.sql(
        "SELECT name, course_name, course_code FROM `tabCourse` ORDER BY course_name ASC LIMIT 500",
        as_dict=True,
    )
    # Match actual Student Master academic_status field options (tabStudent Master → Academic Status)
    student_statuses = ["Active", "Inactive", "Graduated", "Dropped", "Alumni", "Dormant"]

    return {
        "programmes":       programmes,
        "departments":      departments,
        "academic_years":   [r["academic_year"] for r in academic_years],
        "batches":          batches,
        "courses":          courses,
        "student_statuses": student_statuses,
    }


@frappe.whitelist()
def generate_transcript(students, transcript_type="Interim"):
    """
    Create or update Student Transcript records for the given students.
    students – JSON list of student names (document IDs from tabStudent Master).
    transcript_type – "Interim" or "Final"
    """
    import json
    if isinstance(students, str):
        students = json.loads(students)

    if transcript_type not in ("Interim", "Final"):
        frappe.throw("transcript_type must be 'Interim' or 'Final'.")

    results = []
    for student in students:
        try:
            existing = frappe.db.get_value(
                "Student Transcript",
                {"student": student, "transcript_type": transcript_type},
                "name",
            )
            if existing:
                frappe.db.set_value("Student Transcript", existing, {
                    "status":          "Generated",
                    "generation_date": frappe.utils.today(),
                    "generated_by":    frappe.session.user,
                })
            else:
                doc = frappe.new_doc("Student Transcript")
                doc.student          = student
                doc.transcript_type  = transcript_type
                doc.status           = "Generated"
                doc.generation_date  = frappe.utils.today()
                doc.generated_by     = frappe.session.user
                doc.insert(ignore_permissions=True)
            results.append({"student": student, "success": True})
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"Transcript generation failed for {student}")
            results.append({"student": student, "success": False, "error": str(e)})

    frappe.db.commit()
    return results


@frappe.whitelist()
def download_transcript(student, transcript_type="Final"):
    """
    Return transcript record details and a print URL for the given student.
    Uses Frappe's built-in PDF print endpoint so the browser downloads a PDF.
    """
    record = frappe.db.get_value(
        "Student Transcript",
        {"student": student, "transcript_type": transcript_type},
        ["name", "status", "generation_date"],
        as_dict=True,
    )
    if not record:
        frappe.throw(
            f"No {transcript_type} transcript found for student {student}. "
            "Please generate the transcript first."
        )

    _sync_standard_print_format_template()

    # Build a Frappe print/PDF URL for the Student Transcript document
    # Uses the custom "Student Transcript" print format that renders marks + grades
    print_url = (
        f"/api/method/frappe.utils.print_format.download_pdf"
        f"?doctype=Student+Transcript&name={frappe.utils.quote(record['name'])}"
        f"&format=Student+Transcript&no_letterhead=1"
    )

    return {
        "student":         student,
        "transcript_type": transcript_type,
        "transcript_name": record["name"],
        "status":          record.get("status", ""),
        "generation_date": str(record.get("generation_date") or ""),
        "print_url":       print_url,
    }


@frappe.whitelist()
def download_year_based_transcript(student):
    """
    Return a print URL for the Year Based Transcript print format.
    The print format only needs a Student Transcript document as its anchor and
    builds the actual transcript from the linked student.
    """
    if not student:
        frappe.throw("Student is required.")

    _sync_year_based_print_format_template()

    record = frappe.db.get_value(
        "Student Transcript",
        {"student": student, "transcript_type": "Final"},
        ["name", "status", "generation_date"],
        as_dict=True,
    )

    if not record:
        record = frappe.db.get_value(
            "Student Transcript",
            {"student": student, "transcript_type": "Interim"},
            ["name", "status", "generation_date"],
            as_dict=True,
        )

    if not record:
        doc = frappe.new_doc("Student Transcript")
        doc.student = student
        doc.transcript_type = "Final"
        doc.status = "Generated"
        doc.generation_date = frappe.utils.today()
        doc.generated_by = frappe.session.user
        doc.remarks = "Auto-created for year-based transcript download."
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        record = {
            "name": doc.name,
            "status": doc.status,
            "generation_date": doc.generation_date,
        }

    print_url = (
        f"/api/method/slcm.slcm.page.transcript_management_page."
        f"transcript_management_page.download_year_based_transcript_pdf"
        f"?student={frappe.utils.quote(student)}"
    )

    return {
        "student": student,
        "transcript_name": record["name"],
        "status": record.get("status", ""),
        "generation_date": str(record.get("generation_date") or ""),
        "print_url": print_url,
    }


@frappe.whitelist()
def download_year_based_transcript_pdf(student):
    """Render and download the year-based transcript PDF without the print sandbox."""
    if not student:
        frappe.throw("Student is required.")

    from frappe.utils.pdf import get_pdf
    from slcm.slcm.doctype.student_transcript.student_transcript import (
        get_year_based_transcript_context,
    )

    ctx = get_year_based_transcript_context(student)
    transcript_name = frappe.db.get_value(
        "Student Transcript",
        {"student": student, "transcript_type": "Final"},
        "name",
    ) or frappe.db.get_value(
        "Student Transcript",
        {"student": student, "transcript_type": "Interim"},
        "name",
    )
    doc = (
        frappe.get_doc("Student Transcript", transcript_name)
        if transcript_name
        else frappe._dict({"student": student})
    )
    html = frappe.render_template(
        _get_year_based_template_html(),
        {
            "doc": doc,
            "ctx": ctx,
            "get_year_based_transcript_context": get_year_based_transcript_context,
        },
    )

    student_info = ctx.get("student") or {}
    file_label = student_info.get("registration_id") or student
    pdf_content = get_pdf(html)
    frappe.local.response.filename = f"Year-Based-Transcript-{file_label}.pdf"
    frappe.local.response.filecontent = pdf_content
    frappe.local.response.type = "download"


COMPACT_PRINT_FORMAT = "Compact Transcript"


def _get_compact_template_html():
    path = frappe.get_app_path(
        "slcm",
        "slcm",
        "print_format",
        "compact_transcript",
        "compact_transcript.html",
    )
    with open(path, encoding="utf-8") as f:
        return f.read().replace(
            "{% set ctx = get_compact_transcript_context(doc.student) %}",
            "{% set ctx = get_compact_transcript_context(doc.student) %}",
        )


@frappe.whitelist()
def download_compact_transcript(student):
    """
    Return a URL for the compact transcript PDF.
    Admin-side generation — no Transcript Request/approval needed; staff can
    generate and download the compact transcript for any student on demand.
    Reuses an existing Student Transcript (Final, then Interim) if present,
    otherwise creates one on the fly.
    """
    if not student:
        frappe.throw("Student is required.")

    # Find or use an existing Student Transcript
    record = frappe.db.get_value(
        "Student Transcript",
        {"student": student, "transcript_type": "Final"},
        ["name", "status", "generation_date"],
        as_dict=True,
    )
    if not record:
        record = frappe.db.get_value(
            "Student Transcript",
            {"student": student, "transcript_type": "Interim"},
            ["name", "status", "generation_date"],
            as_dict=True,
        )
    if not record:
        # No prior request needed — admin can generate directly
        final_request = frappe.db.get_value(
            "Transcript Request",
            {"student": student, "transcript_type": "Final Transcript"},
            "name",
            order_by="creation desc",
        )
        interim_request = frappe.db.get_value(
            "Transcript Request",
            {"student": student, "transcript_type": "Interim Transcript"},
            "name",
            order_by="creation desc",
        )
        doc = frappe.new_doc("Student Transcript")
        doc.student = student
        doc.transcript_type = "Final" if final_request else "Interim"
        doc.status = "Generated"
        doc.generation_date = frappe.utils.today()
        doc.generated_by = frappe.session.user
        doc.transcript_request = final_request or interim_request or None
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        record = {"name": doc.name, "status": doc.status, "generation_date": doc.generation_date}

    print_url = (
        f"/api/method/slcm.slcm.page.transcript_management_page."
        f"transcript_management_page.download_compact_transcript_pdf"
        f"?student={frappe.utils.quote(student)}"
    )
    return {
        "student": student,
        "transcript_name": record["name"],
        "status": record.get("status", ""),
        "generation_date": str(record.get("generation_date") or ""),
        "print_url": print_url,
    }


@frappe.whitelist()
def download_compact_transcript_pdf(student):
    """Render and stream the compact transcript as a PDF."""
    if not student:
        frappe.throw("Student is required.")

    from frappe.utils.pdf import get_pdf
    from slcm.slcm.doctype.student_transcript.student_transcript import (
        get_compact_transcript_context,
    )

    ctx = get_compact_transcript_context(student)
    transcript_name = frappe.db.get_value(
        "Student Transcript",
        {"student": student, "transcript_type": "Final"},
        "name",
    ) or frappe.db.get_value(
        "Student Transcript",
        {"student": student, "transcript_type": "Interim"},
        "name",
    )
    doc = (
        frappe.get_doc("Student Transcript", transcript_name)
        if transcript_name
        else frappe._dict({"student": student})
    )

    html = frappe.render_template(
        _get_compact_template_html(),
        {
            "doc": doc,
            "ctx": ctx,
            "get_compact_transcript_context": get_compact_transcript_context,
        },
    )

    student_info = ctx.get("student") or {}
    file_label = student_info.get("registration_id") or student
    pdf_content = get_pdf(html)
    frappe.local.response.filename = f"Compact-Transcript-{file_label}.pdf"
    frappe.local.response.filecontent = pdf_content
    frappe.local.response.type = "download"


@frappe.whitelist()
def generate_and_download(students, transcript_type="Interim"):
    """
    Generate transcripts for given students then return download info for each.
    Convenience method used by the 'Generate & Download' action.
    """
    import json
    if isinstance(students, str):
        students = json.loads(students)

    gen_results = generate_transcript(students=students, transcript_type=transcript_type)

    download_info = []
    for res in gen_results:
        if res.get("success"):
            try:
                info = download_transcript(
                    student=res["student"],
                    transcript_type=transcript_type,
                )
                download_info.append(info)
            except Exception:
                pass

    return {"generated": gen_results, "downloads": download_info}


# ── Transcript Request management (admin side) ────────────────────────────────

@frappe.whitelist()
def get_requests(
    search="", status="", transcript_type="", payment_status="",
    programme="", department="", academic_year="", batch="",
    page=1, page_length=50,
):
    """Return paginated list of Transcript Requests for the admin view."""
    page        = int(page)
    page_length = int(page_length)
    offset      = (page - 1) * page_length

    conditions = []
    params     = {}

    if search:
        conditions.append(
            "(tr.name LIKE %(search)s"
            " OR sm.registration_id LIKE %(search)s"
            " OR sm.first_name LIKE %(search)s"
            " OR sm.last_name LIKE %(search)s"
            " OR CONCAT(sm.first_name,' ',IFNULL(sm.last_name,'')) LIKE %(search)s)"
        )
        params["search"] = f"%{search}%"
    if status:
        conditions.append("tr.status = %(status)s")
        params["status"] = status
    if transcript_type:
        conditions.append("tr.transcript_type = %(transcript_type)s")
        params["transcript_type"] = transcript_type
    if payment_status:
        conditions.append("tr.payment_status = %(payment_status)s")
        params["payment_status"] = payment_status
    if programme:
        conditions.append("sm.programme_of_study = %(programme)s")
        params["programme"] = programme
    if department:
        conditions.append("sm.department = %(department)s")
        params["department"] = department
    if academic_year:
        conditions.append("sm.academic_year = %(academic_year)s")
        params["academic_year"] = academic_year
    if batch:
        conditions.append("sm.programme = %(batch)s")
        params["batch"] = batch

    where = "WHERE 1=1" + ("" if not conditions else " AND " + " AND ".join(conditions))

    params.update({"lim": page_length, "off": offset})

    rows = frappe.db.sql(
        f"""
        SELECT
            tr.name, tr.student,
            CONCAT(sm.first_name,' ',IFNULL(sm.last_name,''))  AS student_name,
            sm.registration_id,
            sm.email,
            sm.passport_size_photo                             AS photo,
            sm.programme_of_study                              AS programme,
            sm.programme                                       AS batch_year,
            sm.academic_year,
            sm.department,
            tr.transcript_type,
            tr.num_copies,
            tr.status,
            tr.payment_status,
            tr.fee_amount,
            tr.payment_required,
            tr.requested_on,
            tr.urgency,
            tr.delivery_mode,
            tr.purpose,
            tr.assigned_to,
            tr.rejection_reason,
            tr.transcript_doc,
            tr.payment_reference
        FROM `tabTranscript Request` tr
        JOIN `tabStudent Master` sm ON sm.name = tr.student
        {where}
        ORDER BY tr.requested_on DESC, tr.creation DESC
        LIMIT %(lim)s OFFSET %(off)s
        """,
        params,
        as_dict=True,
    )

    count_params = {k: v for k, v in params.items() if k not in ("lim", "off")}
    total_row = frappe.db.sql(
        f"""
        SELECT COUNT(tr.name) AS cnt
        FROM `tabTranscript Request` tr
        JOIN `tabStudent Master` sm ON sm.name = tr.student
        {where}
        """,
        count_params,
        as_dict=True,
    )

    # Attach programme names
    prog_ids = list({r["programme"] for r in rows if r.get("programme")})
    prog_names = {}
    if prog_ids:
        prows = frappe.db.sql(
            "SELECT name, program_name FROM `tabProgramme` WHERE name IN %(ids)s",
            {"ids": prog_ids}, as_dict=True,
        )
        prog_names = {p["name"]: p["program_name"] for p in prows}

    for r in rows:
        r["programme_name"] = prog_names.get(r.get("programme"), r.get("programme") or "")

    return {
        "requests": rows,
        "total": total_row[0]["cnt"] if total_row else 0,
    }


@frappe.whitelist()
def get_request_stats():
    """Return aggregate counts for the requests dashboard."""
    try:
        rows = frappe.db.sql(
            """
            SELECT
                COUNT(*) AS total,
                SUM(status = 'Payment Pending')                    AS payment_pending,
                SUM(status IN ('Submitted','Under Review'))        AS under_review,
                SUM(status = 'Approved')                           AS approved,
                SUM(status IN ('Generated','Delivered'))           AS generated,
                SUM(status = 'Rejected')                           AS rejected,
                SUM(payment_status = 'Paid' AND fee_amount > 0)    AS paid_count,
                SUM(CASE WHEN payment_status = 'Paid' THEN IFNULL(fee_amount,0) ELSE 0 END) AS revenue
            FROM `tabTranscript Request`
            """,
            as_dict=True,
        )
        return rows[0] if rows else {}
    except Exception:
        return {}


#: payment_status values that clear a payment-required request for approval
APPROVABLE_PAYMENT_STATUSES = ("Not Required", "Paid")


@frappe.whitelist()
def approve_request(request_name):
    """Approve a Transcript Request and generate the Student Transcript."""
    if not frappe.db.exists("Transcript Request", request_name):
        frappe.throw("Transcript Request not found.")

    doc = frappe.get_doc("Transcript Request", request_name)
    if doc.status in ("Generated", "Delivered", "Rejected", "Cancelled"):
        frappe.throw(f"Request is already in {doc.status} state.")

    if doc.payment_required and doc.payment_status not in APPROVABLE_PAYMENT_STATUSES:
        frappe.throw(
            f"Cannot approve: payment is not complete for this request "
            f"(payment status: {doc.payment_status})."
        )

    from slcm.api.transcript_request import _do_generate_transcript
    tr_name = _do_generate_transcript(request_name, doc.student, doc.transcript_type)

    new_status = "Generated" if tr_name else "Approved"

    # Reload doc so email template context has the latest transcript_doc etc.
    doc = frappe.get_doc("Transcript Request", request_name)
    email_flags = _notify_student(doc, "approved", tr_name)

    # Single set_value + single commit — all fields including transcript_doc atomically
    update = {
        "status":        new_status,
        "transcript_doc": tr_name or doc.transcript_doc,
        "reviewed_by":   frappe.session.user,
        "reviewed_on":   frappe.utils.now_datetime(),
        **email_flags,
    }
    frappe.db.set_value("Transcript Request", request_name, update)
    frappe.db.commit()
    return {"success": True, "status": new_status, "transcript_doc": tr_name}


@frappe.whitelist()
def reject_request(request_name, rejection_reason=""):
    """Reject a Transcript Request."""
    if not frappe.db.exists("Transcript Request", request_name):
        frappe.throw("Transcript Request not found.")

    rejection_reason = (rejection_reason or "").strip()
    if not rejection_reason:
        frappe.throw("Rejection reason is required.")

    doc = frappe.get_doc("Transcript Request", request_name)
    if doc.status in ("Generated", "Delivered", "Rejected", "Cancelled"):
        frappe.throw(f"Request is already in {doc.status} state.")

    # Build a temporary doc-like object so _notify_student has rejection_reason
    # without needing a DB round-trip before the data is committed.
    doc.rejection_reason = rejection_reason
    email_flags = _notify_student(doc, "rejected")

    update = {
        "status":               "Rejected",
        "rejection_reason":     rejection_reason,
        "reviewed_by":          frappe.session.user,
        "reviewed_on":          frappe.utils.now_datetime(),
        "rejection_email_sent": 0,
        **email_flags,
    }

    # A request that already collected payment needs a refund trail, not a
    # silent "Paid" left dangling on a Rejected request.
    if doc.payment_required and doc.payment_status == "Paid":
        update["payment_status"] = "Refund Pending"

    # Single set_value + single commit
    frappe.db.set_value("Transcript Request", request_name, update)
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist()
def assign_request(request_name, assignee):
    """Assign a Transcript Request to a user and mark it Under Review."""
    if not frappe.db.exists("Transcript Request", request_name):
        frappe.throw("Transcript Request not found.")

    frappe.db.set_value("Transcript Request", request_name, {
        "assigned_to": assignee,
        "status": "Under Review",
    })
    frappe.db.commit()
    return {"success": True}


def _notify_student(doc, event, transcript_doc=None):
    """
    Queue notification email for the student and return flag fields to set.
    Does NOT commit — callers must include the returned flags in their own
    set_value + commit so everything stays in one transaction.
    Returns a dict of Transcript Request fields to update (may be empty).
    """
    try:
        from slcm.api.transcript_request import _send_template_email, _get_student_full_name
        if not frappe.db.exists("DocType", "Transcript Fee Settings"):
            return {}
        settings = frappe.get_doc("Transcript Fee Settings", "Transcript Fee Settings")

        ctx = {
            "student":          doc.student,
            "student_name":     _get_student_full_name(doc.student),
            "request_name":     doc.name,
            "transcript_type":  doc.transcript_type,
            "rejection_reason": doc.rejection_reason or "",
            "transcript_doc":   transcript_doc or "",
        }

        flag_updates = {}

        if event == "approved":
            if transcript_doc:
                if _send_template_email(doc.student, settings.notify_on_ready, ctx):
                    flag_updates["approval_email_sent"]         = 1
                    flag_updates["transcript_ready_email_sent"] = 1
            else:
                if _send_template_email(doc.student, settings.notify_on_approval, ctx):
                    flag_updates["approval_email_sent"] = 1

        elif event == "rejected":
            if _send_template_email(doc.student, settings.notify_on_rejection, ctx):
                flag_updates["rejection_email_sent"] = 1

        return flag_updates

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Transcript notification error")
        return {}


@frappe.whitelist()
def bulk_approve_requests(request_names):
    """Approve & generate transcripts for multiple requests. Returns per-row results."""
    import json
    if isinstance(request_names, str):
        request_names = json.loads(request_names)

    results = []
    for name in request_names:
        try:
            res = approve_request(name)
            results.append({"name": name, "success": True, **res})
        except Exception as e:
            frappe.db.rollback()
            results.append({"name": name, "success": False, "error": str(e)})

    return {
        "results": results,
        "succeeded": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
    }


@frappe.whitelist()
def bulk_reject_requests(request_names, rejection_reason=""):
    """Reject multiple requests at once. Returns per-row results."""
    import json
    if isinstance(request_names, str):
        request_names = json.loads(request_names)

    results = []
    for name in request_names:
        try:
            res = reject_request(name, rejection_reason)
            results.append({"name": name, "success": True, **res})
        except Exception as e:
            frappe.db.rollback()
            results.append({"name": name, "success": False, "error": str(e)})

    return {
        "results": results,
        "succeeded": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
    }


@frappe.whitelist()
def get_payment_details(request_name):
    """Return a parsed, human-readable payment summary for one Transcript Request."""
    if not frappe.db.exists("Transcript Request", request_name):
        frappe.throw("Transcript Request not found.")

    doc = frappe.get_doc("Transcript Request", request_name)

    parsed_gateway_response = None
    if doc.gateway_response:
        try:
            import json
            parsed_gateway_response = json.loads(doc.gateway_response)
        except Exception:
            parsed_gateway_response = doc.gateway_response

    return {
        "request_name":            doc.name,
        "student":                 doc.student,
        "student_name":            doc.student_name,
        "payment_required":        doc.payment_required,
        "fee_amount":              doc.fee_amount,
        "payment_status":          doc.payment_status,
        "razorpay_payment_status": doc.razorpay_payment_status,
        "razorpay_order_id":       doc.razorpay_order_id,
        "payment_reference":       doc.payment_reference,
        "payment_date":            doc.payment_date,
        "payment_failure_reason":  doc.payment_failure_reason,
        "gateway_response":        parsed_gateway_response,
    }

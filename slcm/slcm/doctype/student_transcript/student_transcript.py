# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from collections import defaultdict
from functools import lru_cache
import subprocess


class StudentTranscript(Document):
    pass


# ── Superscript helper ────────────────────────────────────────────────────────

def _grade_with_superscript(grade):
    """
    Convert trailing numeric digits and +/- in a grade to HTML <sup> tags.
    e.g.  "A+"  →  "A<sup>+</sup>"
          "B1"  →  "B<sup>1</sup>"
          "O"   →  "O"
    """
    if not grade:
        return grade or ""
    grade = str(grade).strip()
    SUFFIX_CHARS = set("0123456789+-")
    i = len(grade) - 1
    while i >= 0 and grade[i] in SUFFIX_CHARS:
        i -= 1
    prefix = grade[: i + 1]
    suffix = grade[i + 1 :]
    if suffix:
        return f"{frappe.utils.escape_html(prefix)}<sup>{frappe.utils.escape_html(suffix)}</sup>"
    return frappe.utils.escape_html(prefix)


# ── Data fetcher ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_transcript_context(student_id):
    """
    Return all data needed to render a student transcript.

    Called from the 'Student Transcript' Jinja print format via:
        get_transcript_context(doc.student)
    """
    if not frappe.has_permission("Student Master", "read", doc=student_id):
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

    # ── 1. Template settings ──────────────────────────────────────────────────
    tmpl_name = frappe.db.get_value("Transcript Template", {"is_default": 1}, "name")
    if tmpl_name:
        tmpl = frappe.db.get_value(
            "Transcript Template", tmpl_name,
            [
                "template_name", "page_size", "orientation",
                "institute_logo", "show_institute_logo", "logo_width", "logo_alignment",
                "institute_name", "header_title",
                "institute_address", "show_institute_address",
                "institute_city", "institute_country", "pincode",
                "show_student_photo", "show_registration_id",
                "show_cgpa", "show_credits", "show_semester_wise",
                "sig_label_1", "sig_image_1",
                "sig_label_2", "sig_image_2",
                "sig_label_3", "sig_image_3",
                "show_watermark", "watermark_logo", "watermark_text", "watermark_opacity",
            ],
            as_dict=True,
        ) or {}
    else:
        tmpl = {}

    # Defaults for template fields
    tmpl.setdefault("show_institute_logo", 1)
    tmpl.setdefault("logo_width", 120)
    tmpl.setdefault("logo_alignment", "Center")
    tmpl.setdefault("show_institute_address", 1)
    tmpl.setdefault("header_title", "OFFICIAL TRANSCRIPT OF ACADEMIC RECORDS")
    tmpl.setdefault("show_student_photo", 1)
    tmpl.setdefault("show_registration_id", 1)
    tmpl.setdefault("show_cgpa", 1)
    tmpl.setdefault("show_credits", 1)
    tmpl.setdefault("show_semester_wise", 1)
    tmpl.setdefault("show_watermark", 0)
    tmpl.setdefault("watermark_opacity", 20)

    # Build institute address string
    addr_parts = [
        tmpl.get("institute_address") or "",
        tmpl.get("institute_city") or "",
        tmpl.get("institute_country") or "",
        tmpl.get("pincode") or "",
    ]
    tmpl["institute_address_full"] = ", ".join(p.strip() for p in addr_parts if p.strip())

    # ── 2. Student info ───────────────────────────────────────────────────────
    sm = frappe.db.get_value(
        "Student Master", student_id,
        [
            "first_name", "middle_name", "last_name",
            "registration_id", "passport_size_photo",
            "programme", "batch_year", "academic_year",
            "current_cgpa", "cumulative_percentage",
            "email", "department", "specialisation",
        ],
        as_dict=True,
    ) or {}

    name_parts = [sm.get("first_name") or "", sm.get("middle_name") or "", sm.get("last_name") or ""]
    sm["full_name"] = " ".join(p.strip() for p in name_parts if p.strip())

    # Programme display name
    prog_id = sm.get("programme")
    if prog_id:
        cohort_name = frappe.db.get_value("Batch", prog_id, "cohort_name")
        sm["programme_name"] = cohort_name or prog_id
    else:
        sm["programme_name"] = ""

    # ── 3. Fetch all course marks for the student ─────────────────────────────
    rows = frappe.db.sql(
        """
        SELECT
            scm.exam_plan,
            ep.exam_name,
            ep.term,
            scm.course,
            c.course_name,
            c.course_code,
            COALESCE(c.credit_value, 0)                                         AS credit_value,
            COALESCE(NULLIF(scm.updated_grade, ''), NULLIF(scm.grade, ''))      AS final_grade,
            CASE
                WHEN scm.updated_grade IS NOT NULL AND scm.updated_grade != ''
                     THEN COALESCE(scm.updated_final_marks, 0)
                ELSE COALESCE(scm.total_marks, 0)
            END                                                                  AS final_marks,
            COALESCE(gsc.grade_point, 0)                                        AS grade_point,
            COALESCE(gsc.failed, 0)                                             AS is_failed,
            COALESCE(scm.consider_for_sgpa, 0)                                  AS consider_for_sgpa,
            COALESCE(scm.mfa, 'No')                                             AS mfa,
            EXISTS (
                SELECT 1
                FROM `tabFA MFA Application` fma
                WHERE fma.student = scm.student
                  AND fma.course = scm.course
                  AND fma.docstatus = 1
                  AND fma.status = 'Approved'
                  AND fma.application_type = 'Medical First Attempt (MFA)'
            )                                                                   AS has_approved_mfa,
            scm.enrollment_status
        FROM `tabStudent Course Marks` scm
        INNER JOIN `tabExam Plan` ep ON ep.name = scm.exam_plan
        LEFT JOIN `tabCourse` c ON c.name = scm.course
        LEFT JOIN `tabCourse Schema Assignment` csa
            ON csa.exam_plan = scm.exam_plan AND csa.course = scm.course
        LEFT JOIN `tabGrading Schema Component` gsc
            ON gsc.parent = csa.grade_schema
            AND gsc.parentfield = 'grades'
            AND gsc.grade = COALESCE(NULLIF(scm.updated_grade, ''), NULLIF(scm.grade, ''))
        WHERE scm.student = %(student)s
          AND COALESCE(scm.enrollment_status, '') NOT IN ('Dropped', 'Detained', 'Migrated')
        ORDER BY ep.name ASC, c.course_code ASC, c.course_name ASC
        """,
        {"student": student_id},
        as_dict=True,
    )

    # ── 4. Fetch published SGPA values per exam plan ──────────────────────────
    sgpa_rows = frappe.db.sql(
        """
        SELECT exam_plan, term_gpa
        FROM `tabStudent Result Publish`
        WHERE student = %(student)s AND term_gpa IS NOT NULL AND term_gpa > 0
        """,
        {"student": student_id},
        as_dict=True,
    )
    published_sgpa = {r["exam_plan"]: r["term_gpa"] for r in sgpa_rows}

    # ── 5. Group by exam plan / semester ─────────────────────────────────────
    plan_order = []
    plan_courses = defaultdict(list)
    plan_meta = {}

    for row in rows:
        ep = row["exam_plan"]
        if ep not in plan_meta:
            plan_order.append(ep)
            plan_meta[ep] = {
                "exam_plan": ep,
                "exam_name": row.get("exam_name") or ep,
                "term":      row.get("term") or "",
            }
        plan_courses[ep].append(row)

    # ── 6. Build semester list with SGPA ──────────────────────────────────────
    ordinals = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
                "XI", "XII", "XIII", "XIV", "XV", "XVI"]

    semesters = []
    total_earned_credits = 0

    for sem_idx, ep in enumerate(plan_order):
        meta    = plan_meta[ep]
        courses = plan_courses[ep]

        # Compute SGPA for this term
        sgpa = published_sgpa.get(ep)
        if sgpa is None:
            wgp   = 0.0
            tc    = 0.0
            for c in courses:
                if c["consider_for_sgpa"] and c["final_grade"] and c["credit_value"]:
                    wgp += float(c["grade_point"]) * float(c["credit_value"])
                    tc  += float(c["credit_value"])
            sgpa = round(wgp / tc, 2) if tc > 0 else None

        # Semester label: prefer "Semester I", fallback to exam_name
        label_roman = ordinals[sem_idx] if sem_idx < len(ordinals) else str(sem_idx + 1)
        label = f"SEMESTER {label_roman}"

        # Build course rows with HTML grade
        course_rows = []
        sem_credits = 0
        for course_idx, c in enumerate(courses, 1):
            grade_html = _grade_with_superscript(c["final_grade"])
            has_mfa = (c.get("mfa") == "Yes") or bool(c.get("has_approved_mfa"))
            if has_mfa:
                grade_html = f"{grade_html} <sup class=\"mfa-sup\">MFA</sup>" if grade_html else "<sup class=\"mfa-sup\">MFA</sup>"
            credit_val = int(c["credit_value"]) if float(c["credit_value"]) == int(c["credit_value"]) else float(c["credit_value"])
            gp_val     = float(c["grade_point"])
            course_rows.append({
                "course_number": f"{sem_idx + 1}.{course_idx}",
                "course_name":   c.get("course_name") or c.get("course_code") or "",
                "course_code":   c.get("course_code") or "",
                "credit_value":  credit_val,
                "final_grade":   c.get("final_grade") or "",
                "grade_html":    grade_html,
                "grade_point":   f"{gp_val:.1f}",
                "is_failed":     bool(c["is_failed"]),
                "mfa":           "Yes" if has_mfa else "No",
                "final_marks":   float(c.get("final_marks") or 0),
            })
            sem_credits += float(c["credit_value"])

        total_earned_credits += sem_credits

        semesters.append({
            "label":        label,
            "exam_name":    meta["exam_name"],
            "term":         meta["term"],
            "courses":      course_rows,
            "sgpa":         f"{sgpa:.2f}" if sgpa is not None else "",
            "total_credits": int(sem_credits) if sem_credits == int(sem_credits) else sem_credits,
        })

    # ── 7. Build year list for transcript display ────────────────────────────
    # Prefer explicit Transcript Settings year mappings. If mappings are not
    # configured yet, keep each term as its own year label so the print format
    # shows YEAR I, YEAR II, etc. instead of SEMESTER I, SEMESTER II.
    year_lookup = {}
    try:
        settings_doc = frappe.get_single("Transcript Settings")
        for mapping in settings_doc.get("year_mappings") or []:
            year_label = mapping.get("year_label") or ""
            year_number = int(mapping.get("year_number") or 99)
            terms = [t.strip() for t in (mapping.get("semester_trimester_list") or "").split(",")]
            for term in terms:
                if term:
                    year_lookup[term.lower()] = {
                        "year_label": year_label,
                        "year_number": year_number,
                    }
    except Exception:
        year_lookup = {}

    years_by_key = {}
    for sem_idx, sem in enumerate(semesters):
        match = None
        for candidate in (sem.get("term"), sem.get("exam_plan"), sem.get("exam_name"), sem.get("label")):
            if candidate and str(candidate).strip().lower() in year_lookup:
                match = year_lookup[str(candidate).strip().lower()]
                break

        fallback_year_number = sem_idx + 1
        fallback_roman = ordinals[sem_idx] if sem_idx < len(ordinals) else str(fallback_year_number)
        year_number = int((match or {}).get("year_number") or fallback_year_number)
        year_label = (match or {}).get("year_label") or f"YEAR {fallback_roman}"
        key = (year_number, year_label)

        year_data = years_by_key.setdefault(key, {
            "label": year_label,
            "year_label": year_label,
            "year_number": year_number,
            "courses": [],
            "total_credits": 0,
        })
        year_data["courses"].extend(sem["courses"])
        year_data["total_credits"] += float(sem.get("total_credits") or 0)

    years = []
    for year_idx, key in enumerate(sorted(years_by_key.keys()), 1):
        year_data = years_by_key[key]
        for course_idx, course in enumerate(year_data["courses"], 1):
            course["course_number"] = f"{year_idx}.{course_idx}"
        total_credits = year_data["total_credits"]
        year_data["total_credits"] = int(total_credits) if total_credits == int(total_credits) else total_credits
        years.append(year_data)

    # ── 8. CGPA ───────────────────────────────────────────────────────────────
    cgpa_raw = sm.get("current_cgpa")
    cgpa_display = f"{float(cgpa_raw):.2f}" if cgpa_raw else ""

    return {
        "template":              tmpl,
        "student":               sm,
        "semesters":             semesters,
        "years":                 years,
        "cgpa":                  cgpa_display,
        "total_earned_credits":  int(total_earned_credits) if total_earned_credits == int(total_earned_credits) else total_earned_credits,
        "generation_date":       frappe.utils.formatdate(frappe.utils.today(), "dd-MM-yyyy"),
    }


# ── Compact Transcript ───────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _compact_page_height_mm():
    """
    CSS min-height (mm) that makes the compact transcript wrapper fill exactly one
    printable A4 page, so the CGPA / Date / Registrar footer sits at the page bottom.

    wkhtmltopdf built with patched Qt honours --disable-smart-shrinking and renders
    1:1, but the unpatched build ignores it and shrinks everything by ~0.775, so the
    same CSS height lands much higher on the page. Detect the build once per worker.
    """
    try:
        out = subprocess.run(
            ["wkhtmltopdf", "--version"], capture_output=True, text=True, timeout=10
        ).stdout.lower()
        patched = "patched qt" in out
    except Exception:
        patched = True
    return 260 if patched else 340


@frappe.whitelist()
def get_compact_transcript_context(student_id):
    """
    Return flat row lists for the compact two-column transcript layout.
    Uses get_transcript_context so year grouping has proper ordinal fallback
    even when Transcript Settings year mappings are not configured.
    """
    ORDINALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII",
                "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI"]

    ctx = get_transcript_context(student_id)

    # Normalise year labels → "I Year", "II Year", ... format
    for idx, year in enumerate(ctx.get("years", [])):
        label = (year.get("year_label") or "").strip()
        roman = ORDINALS[idx] if idx < len(ORDINALS) else str(idx + 1)
        if not label or label.upper() in ("OTHER", "YEAR"):
            year["year_label"] = f"{roman} Year"
        elif label.upper().startswith("YEAR "):
            # "YEAR I" → "I Year"
            year["year_label"] = f"{label[5:].strip()} Year"

    # Build flat row list from all years — no spacers; year header provides separation
    all_rows = []
    for year in ctx.get("years", []):
        all_rows.append({"type": "header", "text": year["year_label"]})
        for course in year.get("courses", []):
            all_rows.append({
                "type": "course",
                "course_number": course.get("course_number", ""),
                "course_name": course.get("course_name", ""),
                "grade_html": course.get("grade_html", ""),
            })

    mid = (len(all_rows) + 1) // 2
    ctx["left_rows"] = all_rows[:mid]
    ctx["right_rows"] = all_rows[mid:]
    ctx["max_rows"] = max(len(ctx["left_rows"]), len(ctx["right_rows"]), 0)

    # Derive academic period from term start/end dates
    try:
        date_rows = frappe.db.sql(
            """
            SELECT MIN(at.term_start_date) AS min_date, MAX(at.term_end_date) AS max_date
            FROM `tabExam Plan` ep
            INNER JOIN `tabAcademic Term` at ON at.name = ep.term
            WHERE ep.name IN (
                SELECT DISTINCT exam_plan FROM `tabStudent Course Marks`
                WHERE student = %(student)s
            )
            """,
            {"student": student_id},
            as_dict=True,
        )
        min_date = date_rows[0].get("min_date") if date_rows else None
        max_date = date_rows[0].get("max_date") if date_rows else None
        if min_date and max_date:
            period = (
                f"{frappe.utils.formatdate(min_date, 'MMMM yyyy')}"
                f" to "
                f"{frappe.utils.formatdate(max_date, 'MMMM yyyy')}"
            )
        else:
            period = ctx["student"].get("batch_year") or ""
    except Exception:
        period = ctx["student"].get("batch_year") or ""

    ctx["period"] = period
    ctx["page_height_mm"] = _compact_page_height_mm()
    return ctx


# ── Year-Based Transcript ─────────────────────────────────────────────────────

@frappe.whitelist()
def get_year_based_transcript_context(student_id):
    """
    Return year-based transcript data with prescribed courses.
    Used for year-based transcript format (I Year, II Year, etc.)
    """
    if not frappe.has_permission("Student Master", "read", doc=student_id):
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

    from collections import defaultdict

    # Get transcript settings
    settings_doc = frappe.get_single("Transcript Settings")
    settings = {
        "use_year_based_layout": settings_doc.get("use_year_based_layout", 1),
        "show_prescribed_courses": settings_doc.get("show_prescribed_courses", 1),
        "show_course_numbers": settings_doc.get("show_course_numbers", 1),
        "use_two_column_layout": settings_doc.get("use_two_column_layout", 1),
        "header_bg_color": settings_doc.get("header_bg_color", "#C94A38"),
        "header_text_color": settings_doc.get("header_text_color", "#FFFFFF"),
        "table_header_bg_color": settings_doc.get("table_header_bg_color", "#F5C6CB"),
        "table_border_color": settings_doc.get("table_border_color", "#000000"),
        "use_page_background": settings_doc.get("use_page_background", 0),
        "page_bg_color": settings_doc.get("page_bg_color", "#FFFFFF"),
        "use_mild_background": settings_doc.get("use_mild_background", 1),
        "mild_bg_color": settings_doc.get("mild_bg_color", "#F9F9F9"),
    }

    # Get template settings
    tmpl_name = frappe.db.get_value("Transcript Template", {"is_default": 1}, "name")
    if tmpl_name:
        tmpl = frappe.db.get_value(
            "Transcript Template", tmpl_name,
            [
                "template_name", "institute_logo", "show_institute_logo",
                "logo_width", "institute_name", "header_title",
                "institute_address", "show_institute_address",
                "show_student_photo", "show_cgpa"
            ],
            as_dict=True,
        ) or {}
    else:
        tmpl = {}

    tmpl.setdefault("show_institute_logo", 1)
    tmpl.setdefault("logo_width", 120)
    tmpl.setdefault("header_title", "OFFICIAL TRANSCRIPT OF ACADEMIC RECORDS")
    tmpl.setdefault("show_student_photo", 1)
    tmpl.setdefault("show_cgpa", 1)

    # Get student info
    sm = frappe.db.get_value(
        "Student Master", student_id,
        [
            "first_name", "middle_name", "last_name",
            "registration_id", "passport_size_photo",
            "programme", "batch_year", "current_cgpa"
        ],
        as_dict=True,
    ) or {}

    name_parts = [sm.get("first_name") or "", sm.get("middle_name") or "", sm.get("last_name") or ""]
    sm["full_name"] = " ".join(p.strip() for p in name_parts if p.strip())

    # Programme display name
    prog_id = sm.get("programme")
    if prog_id:
        cohort_name = frappe.db.get_value("Batch", prog_id, "cohort_name")
        sm["programme_name"] = cohort_name or prog_id
    else:
        sm["programme_name"] = ""

    # Get all course marks
    rows = frappe.db.sql("""
        SELECT
            scm.exam_plan,
            ep.exam_name,
            ep.term,
            scm.course,
            c.course_name,
            c.course_code,
            COALESCE(c.credit_value, 0) AS credit_value,
            COALESCE(NULLIF(scm.updated_grade, ''), NULLIF(scm.grade, '')) AS final_grade,
            COALESCE(gsc.grade_point, 0) AS grade_point,
            COALESCE(scm.mfa, 'No') AS mfa,
            EXISTS (
                SELECT 1
                FROM `tabFA MFA Application` fma
                WHERE fma.student = scm.student
                  AND fma.course = scm.course
                  AND fma.docstatus = 1
                  AND fma.status = 'Approved'
                  AND fma.application_type = 'Medical First Attempt (MFA)'
            ) AS has_approved_mfa
        FROM `tabStudent Course Marks` scm
        INNER JOIN `tabExam Plan` ep ON ep.name = scm.exam_plan
        LEFT JOIN `tabCourse` c ON c.name = scm.course
        LEFT JOIN `tabCourse Schema Assignment` csa
            ON csa.exam_plan = scm.exam_plan AND csa.course = scm.course
        LEFT JOIN `tabGrading Schema Component` gsc
            ON gsc.parent = csa.grade_schema
            AND gsc.parentfield = 'grades'
            AND gsc.grade = COALESCE(NULLIF(scm.updated_grade, ''), NULLIF(scm.grade, ''))
        WHERE scm.student = %(student)s
          AND COALESCE(scm.enrollment_status, '') NOT IN ('Dropped', 'Detained', 'Migrated')
        ORDER BY ep.name ASC, c.course_code ASC, c.course_name ASC
    """, {"student": student_id}, as_dict=True)

    # Build year mapping from settings
    year_map = {}  # Maps term name to year info
    for mapping in settings_doc.get("year_mappings") or []:
        terms = [t.strip() for t in (mapping.get("semester_trimester_list") or "").split(',')]
        for term in terms:
            if term:
                year_map[term] = {
                    "year_label": mapping.get("year_label", ""),
                    "year_number": mapping.get("year_number", 99)
                }

    # Group courses by year
    years_data = defaultdict(lambda: {"courses": [], "year_label": "", "year_number": 99})

    for row in rows:
        term = row.get("term") or row.get("exam_plan") or ""
        year_info = year_map.get(term, {"year_label": "Other", "year_number": 99})

        year_key = year_info["year_number"]
        years_data[year_key]["year_label"] = year_info["year_label"]
        years_data[year_key]["year_number"] = year_info["year_number"]

        grade_html = _grade_with_superscript(row["final_grade"])
        has_mfa = (row.get("mfa") == "Yes") or bool(row.get("has_approved_mfa"))
        if has_mfa:
            grade_html = f"{grade_html} <sup class=\"mfa-sup\">MFA</sup>" if grade_html else "<sup class=\"mfa-sup\">MFA</sup>"

        years_data[year_key]["courses"].append({
            "course_name": row.get("course_name") or "",
            "course_code": row.get("course_code") or "",
            "credit_value": row.get("credit_value") or 0,
            "grade_html": grade_html,
            "final_grade": row.get("final_grade") or "",
            "grade_point": row.get("grade_point") or 0
        })

    # Sort years and add course numbers
    years = []
    for year_num in sorted(years_data.keys()):
        year_data = years_data[year_num]

        # Add course numbers
        for idx, course in enumerate(year_data["courses"], 1):
            course["course_number"] = f"{year_num}.{idx}"

        years.append(year_data)

    # Calculate CGPA
    cgpa_raw = sm.get("current_cgpa") or 0
    cgpa_display = f"{float(cgpa_raw):.2f}" if cgpa_raw else "0.00"

    return {
        "settings": settings,
        "template": tmpl,
        "student": sm,
        "years": years,
        "cgpa": cgpa_display,
        "generation_date": frappe.utils.formatdate(frappe.utils.today(), "dd.MM.yyyy")
    }

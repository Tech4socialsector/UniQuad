import frappe

no_cache = 1


def get_context(context):
    context.no_cache = 1

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "results"

    student_name = _get_student_name()
    if not student_name:
        context.no_student = True
        _set_nav_defaults(context)
        context.published_results = []
        return context

    context.no_student = False

    try:
        student = frappe.get_doc("Student Master", student_name)
        _set_student_nav(context, student)

        exam_settings = frappe.get_single("Examination Settings")
        max_cgpa_for_improvement = float(exam_settings.max_cgpa_for_improvement or 3.0)

        # ── Only show exam plans where this student's result is published ──
        publish_records = frappe.get_all(
            "Student Result Publish",
            filters={"student": student_name, "is_published": 1},
            fields=[
                "name", "exam_plan",
                "term_gpa", "term_percentage",
                "cumulative_gpa", "cumulative_percentage",
                "published_on",
            ],
            ignore_permissions=True,
        )

        published_results = []

        for rec in publish_records:
            ep_name = rec.exam_plan

            # ── Exam Plan label ────────────────────────────────────
            ep = frappe.db.get_value(
                "Exam Plan", ep_name,
                ["exam_name", "term", "status"],
                as_dict=True,
            ) or frappe._dict()

            # ── Improvement Exam eligibility gate — only students with a
            # published CGPA below the configured threshold may apply ──
            cgpa_for_eligibility = float(rec.cumulative_gpa) if rec.cumulative_gpa else None
            improvement_cgpa_ok = bool(
                cgpa_for_eligibility is not None and cgpa_for_eligibility < max_cgpa_for_improvement
            )

            # ── Publish Result Setting ─────────────────────────────
            setting       = _get_publish_setting(ep_name)
            show_total    = bool(setting and setting.show_total_marks)
            show_sgpa     = bool(setting and setting.show_sgpa)
            hide_sgpa_fail = bool(setting and setting.hide_sgpa_for_failed)

            # Components the admin has whitelisted (empty set = show all)
            allowed_components = set()
            if setting and setting.publish_components:
                for pc in setting.publish_components:
                    if pc.component:
                        allowed_components.add(pc.component)

            # ── Course Marks — NO status filter; is_published is the gate ──
            marks_records = frappe.get_all(
                "Student Course Marks",
                filters={"student": student_name, "exam_plan": ep_name},
                fields=[
                    "name", "course", "evaluation_schema",
                    "total_marks", "grade", "moderated_grade",
                    "updated_final_marks", "updated_grade", "re_exam_grade",
                    "improvement_marks", "improvement_grade", "improvement_applied",
                    "enrollment_status", "attendance_status",
                    "mfa", "fairness_status", "remark", "consider_for_sgpa",
                ],
                ignore_permissions=True,
            )

            courses_out  = []
            has_any_fail = False

            for m in marks_records:
                _course = frappe.db.get_value(
                    "Course", m.course, ["course_name", "course_code"], as_dict=True
                ) or frappe._dict()
                course_name = _course.course_name or m.course
                course_code = _course.course_code or m.course

                # ── Component groups split by regular vs re-exam ──
                regular_groups, reexam_groups = _get_component_groups(
                    m.name, ep_name, m.course, allowed_components
                )

                # ── Effective total marks ──────────────────────────
                raw_total = m.updated_final_marks or m.total_marks or sum(
                    c["effective_marks"]
                    for grp in regular_groups
                    for c in grp["components"]
                )
                display_total = round(float(raw_total), 2) if raw_total else None

                # ── Effective grade: updated > moderated > raw ─────
                display_grade = m.updated_grade or m.moderated_grade or m.grade or ""

                # ── Pass / Fail ────────────────────────────────────
                if display_grade:
                    is_fail = _is_failing_grade(display_grade, ep_name, m.course)
                    overall_status = "Fail" if is_fail else "Pass"
                    if is_fail:
                        has_any_fail = True
                else:
                    is_fail        = False
                    overall_status = ""

                # ── Attendance status with fallback ───────────────
                att_status = m.attendance_status or ""
                if not att_status:
                    att_status = _get_attendance_fallback(student_name, m.course, ep_name)

                # ── Enrollment status with fallback ───────────────
                enroll_status = m.enrollment_status or ""
                if not enroll_status:
                    enroll_status = _get_enrollment_fallback(student_name, m.course)

                arrear_marker = _get_arrear_marker(student_name, m.course, is_currently_failing=is_fail)

                # ── Improvement Exam info ─────────────────────────
                improv_setting = _get_improvement_setting(ep_name, m.course)
                improv_reg = _get_improvement_registration(student_name, ep_name, m.course)

                # Check if registration limit is reached
                improv_limit_reached = False
                if improv_setting and improv_setting.registration_limit:
                    reg_count = frappe.db.sql(
                        """SELECT COUNT(*) FROM `tabImprovement Exam Registration`
                           WHERE exam_plan=%s AND course=%s AND status!='Cancelled'""",
                        (ep_name, m.course),
                    )[0][0]
                    improv_limit_reached = int(reg_count) >= int(improv_setting.registration_limit)

                courses_out.append({
                    "course":                   m.course,
                    "course_name":              course_name,
                    "course_code":              course_code,
                    "display_grade":            display_grade,
                    "display_total":            display_total,
                    "overall_status":           overall_status,
                    "is_fail":                  is_fail,
                    "enrollment_status":        enroll_status,
                    "attendance_status":        att_status,
                    "mfa":                      m.mfa or "",
                    "fairness_status":          m.fairness_status or "",
                    "consider_for_sgpa":        int(m.consider_for_sgpa or 1),
                    "remark":                   m.remark or "",
                    "updated_final_marks":      round(float(m.updated_final_marks), 2) if m.updated_final_marks else None,
                    "updated_grade":            m.updated_grade or "",
                    "re_exam_grade":            m.re_exam_grade or "",
                    "improvement_marks":        round(float(m.improvement_marks), 2) if m.improvement_marks else None,
                    "improvement_grade":        m.improvement_grade or "",
                    "improvement_applied":      int(m.improvement_applied or 0),
                    "regular_groups":           regular_groups,
                    "reexam_groups":            reexam_groups,
                    "has_comp_marks":           bool(regular_groups or reexam_groups),
                    "show_total":               show_total,
                    "arrear_marker":            arrear_marker,
                    "improvement_available":      bool(improv_setting) and improvement_cgpa_ok,
                    "improvement_setting_exists": bool(improv_setting),
                    "improvement_cgpa_ok":        improvement_cgpa_ok,
                    "improvement_fee":           float(improv_setting.improvement_fee or 0) if improv_setting else 0,
                    "improvement_deadline_to":   str(improv_setting.deadline_to or "") if improv_setting else "",
                    "improvement_payment_status": improv_reg.payment_status if improv_reg else "",
                    "improvement_reg_name":      improv_reg.name if improv_reg else "",
                    "improvement_paid":          bool(improv_reg and improv_reg.payment_status in ("Paid", "Captured")),
                    # True only when registration is confirmed — NOT when payment was cancelled/failed
                    "improvement_registered":    bool(
                        improv_reg and improv_reg.payment_status not in
                        ("Payment Cancelled", "Payment Failed", "Pending", "Payment Initiated")
                    ),
                    # Can retry payment if previously cancelled or failed
                    "improvement_can_retry":     bool(
                        improv_reg and improv_reg.payment_status in ("Payment Cancelled", "Payment Failed")
                    ),
                    "improvement_limit_reached": improv_limit_reached,
                    "improvement_limit":         int(improv_setting.registration_limit or 0) if improv_setting else 0,
                })

            courses_out.sort(key=lambda c: c["course_name"])

            # ── Summary counts ─────────────────────────────────────
            pass_count    = sum(1 for c in courses_out if c["overall_status"] == "Pass")
            fail_count    = sum(1 for c in courses_out if c["overall_status"] == "Fail")
            pending_count = sum(1 for c in courses_out if c["overall_status"] == "")

            # ── Term GPA / % with admin visibility rules ───────────
            term_gpa = round(float(rec.term_gpa), 2)   if rec.term_gpa         else None
            term_pct = round(float(rec.term_percentage), 2) if rec.term_percentage else None
            cgpa     = round(float(rec.cumulative_gpa), 2)  if rec.cumulative_gpa  else None
            cpct     = round(float(rec.cumulative_percentage), 2) if rec.cumulative_percentage else None

            if show_sgpa and hide_sgpa_fail and has_any_fail:
                term_gpa = None
                term_pct = None

            published_results.append({
                "exam_plan":             ep_name,
                "exam_name":             ep.exam_name or ep_name,
                "term":                  ep.term or "",
                "published_on":          rec.published_on,
                "term_gpa":              term_gpa,
                "term_percentage":       term_pct,
                "cumulative_gpa":        cgpa,
                "cumulative_percentage": cpct,
                "courses":               courses_out,
                "has_any_fail":          has_any_fail,
                "show_sgpa":             show_sgpa,
                "show_total":            show_total,
                "show_cumulative":       bool(cgpa or cpct),
                "pass_count":            pass_count,
                "fail_count":            fail_count,
                "pending_count":         pending_count,
            })

        # Most recently published first
        published_results.sort(
            key=lambda r: str(r["published_on"] or ""), reverse=True
        )

        context.published_results = published_results
        context.has_results = bool(published_results)

        # ── GPA Trend data for chart (chronological order) ────────
        chart_data = []
        for r in sorted(published_results, key=lambda x: str(x["published_on"] or "")):
            # Respect the exam's "show SGPA" publish setting in the trend too
            sgpa = r["term_gpa"] if r["show_sgpa"] else None
            if sgpa is not None or r["term_percentage"] is not None:
                chart_data.append({
                    "label": r["term"] or r["exam_name"],
                    "sgpa":  sgpa,
                    "pct":   r["term_percentage"],
                    "cgpa":  r["cumulative_gpa"],
                })
        context.gpa_chart_data = chart_data

    except Exception as e:
        frappe.log_error(f"Student Portal Results error: {e}", "Student Portal")
        context.portal_error = str(e)
        _set_nav_defaults(context)
        context.published_results = []
        context.has_results = False

    return context


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_attendance_fallback(student_name, course, exam_plan):
    """
    Derive attendance status from Attendance Summary when Student Course Marks
    has an empty attendance_status (common for freshly imported records).
    Returns 'Present', 'Low Attendance', 'Detained', or '' if not found.
    """
    try:
        row = frappe.db.get_value(
            "Attendance Summary",
            {"student": student_name, "course": course},
            ["attendance_percentage", "student_status"],
            as_dict=True,
        )
        if not row:
            # Try with exam_plan filter as well
            row = frappe.db.get_value(
                "Attendance Summary",
                {"student": student_name, "course": course, "exam_plan": exam_plan},
                ["attendance_percentage", "student_status"],
                as_dict=True,
            )
        if row:
            # Prefer explicit student_status if present
            if row.get("student_status"):
                return row.student_status
            pct = float(row.attendance_percentage or 0)
            if pct >= 75:
                return "Present"
            elif pct >= 50:
                return "Low Attendance"
            else:
                return "Detained"
    except Exception:
        pass
    return ""


def _get_enrollment_fallback(student_name, course):
    """
    Derive enrollment status from Student Enrollment when Student Course Marks
    has an empty enrollment_status (common for freshly imported records).
    Returns 'Enrolled', 'Detained', 'Dropped', or '' if not found.
    """
    try:
        # Try Student Enrollment child record first
        row = frappe.db.get_value(
            "Student Enrollment",
            {"student": student_name, "course": course},
            ["status", "enrollment_status"],
            as_dict=True,
        )
        if row:
            status = row.get("status") or row.get("enrollment_status") or ""
            if status:
                return status
            return "Enrolled"   # record exists → considered enrolled
    except Exception:
        pass
    return ""


def _get_publish_setting(exam_plan):
    try:
        return frappe.get_doc(
            "Publish Result Setting", exam_plan, ignore_permissions=True
        )
    except Exception:
        return None


def _is_failing_grade(grade, exam_plan=None, course=None):
    """True when grade is a failing grade per Grading Schema, with heuristic fallback."""
    if not grade:
        return False
    # Schema-based lookup via Course Schema Assignment
    if exam_plan and course:
        try:
            grading_schema = frappe.db.get_value(
                "Course Schema Assignment",
                {"exam_plan": exam_plan, "course": course},
                "grade_schema",
            )
            if grading_schema:
                failed = frappe.get_all(
                    "Grading Schema Component",
                    filters={"parent": grading_schema, "failed": 1},
                    pluck="grade",
                    ignore_permissions=True,
                )
                if failed:
                    return grade in set(failed)
        except Exception:
            pass
    # Heuristic fallback
    return grade.upper() in {"F", "FF", "FAIL", "AB", "I", "W", "U", "E"}


def _get_component_groups(marks_doc_name, exam_plan, course, allowed_components):
    """
    Build component groups exactly as the admin sees them — driven by
    Schema Assessment Config (regular) and Schema Reexam Config (re-exam)
    from the Evaluation Schema, ordered by idx.

    Returns: (regular_groups, reexam_groups)
    Each group: {type_name, components: [{label, max_marks, marks, revaluation_marks, effective_marks}]}
    """
    try:
        # 1. Get evaluation schema for this course + exam plan
        evaluation_schema = frappe.db.get_value(
            "Course Schema Assignment",
            {"exam_plan": exam_plan, "course": course},
            "evaluation_schema",
        )
        if not evaluation_schema:
            return [], []

        # 2. Regular columns from Schema Assessment Config (ordered by idx)
        regular_cols = frappe.db.sql(
            """
            SELECT sac.component, ec.component_name,
                   sac.assessment_type, eat.type_name,
                   sac.label, sac.maximum_marks, sac.idx
            FROM `tabSchema Assessment Config` sac
            LEFT JOIN `tabExam Component` ec  ON ec.name  = sac.component
            LEFT JOIN `tabExam Assessment Type` eat ON eat.name = sac.assessment_type
            WHERE sac.parent = %s
            ORDER BY sac.idx ASC
            """,
            (evaluation_schema,),
            as_dict=True,
        )

        # 3. Re-exam columns from Schema Reexam Config (ordered by idx)
        reexam_cols = frappe.db.sql(
            """
            SELECT src.component, ec.component_name,
                   src.assessment_type, eat.type_name,
                   src.label, src.maximum_marks, src.idx
            FROM `tabSchema Reexam Config` src
            LEFT JOIN `tabExam Component` ec  ON ec.name  = src.component
            LEFT JOIN `tabExam Assessment Type` eat ON eat.name = src.assessment_type
            WHERE src.parent = %s
            ORDER BY src.idx ASC
            """,
            (evaluation_schema,),
            as_dict=True,
        )

        # 4. Actual marks from Student Marks Entry, keyed by (component|assessment_type)
        entries = frappe.get_all(
            "Student Marks Entry",
            filters={"parent": marks_doc_name},
            fields=["component", "assessment_type", "label", "marks", "revaluation_marks", "moderated_marks"],
            ignore_permissions=True,
        )
        marks_map = {}
        for e in entries:
            key = (e.component or "") + "|" + (e.assessment_type or "")
            marks_map[key] = e

        def _build_groups(cols):
            # Admin groups by ec.component_name (Row 1) and shows sac.label per column (Row 2)
            groups = {}   # ordered dict: component_name -> list of column dicts
            group_keys = []  # preserve insertion order
            for col in cols:
                if allowed_components and col.get("component") not in allowed_components:
                    continue
                # Row 1 header = ec.component_name (e.g. "External", "Internal (Custom)")
                tname = col.get("component_name") or col.get("component") or "General"
                key   = (col.get("component") or "") + "|" + (col.get("assessment_type") or "")
                e     = marks_map.get(key, {})

                marks = round(float(e.get("marks") or 0), 2)
                reval = round(float(e.get("revaluation_marks") or 0), 2)
                eff   = round(float(e.get("moderated_marks") or e.get("revaluation_marks") or e.get("marks") or 0), 2)

                if tname not in groups:
                    groups[tname] = []
                    group_keys.append(tname)
                groups[tname].append({
                    # Row 2 label = sac.label (e.g. "Class Work Assessment", "Project")
                    "label":             col.get("label") or col.get("type_name") or col.get("assessment_type") or "—",
                    "max_marks":         float(col.get("maximum_marks") or 0),
                    "marks":             marks,
                    "revaluation_marks": reval,
                    "effective_marks":   eff,
                })
            return [{"type_name": k, "components": groups[k]} for k in group_keys]

        return _build_groups(regular_cols), _build_groups(reexam_cols)

    except Exception as e:
        frappe.log_error(f"_get_component_groups: {e}", "Student Portal")
        return [], []


def _get_improvement_setting(exam_plan, course):
    """Return Improvement Exam Course Setting for this exam_plan+course, or None."""
    try:
        name = frappe.db.get_value(
            "Improvement Exam Course Setting",
            {"exam_plan": exam_plan, "course": course},
            "name",
        )
        if name:
            return frappe.get_doc("Improvement Exam Course Setting", name)
    except Exception:
        pass
    return None


def _get_improvement_registration(student_name, exam_plan, course):
    """Return active improvement registration dict (name, payment_status) or None."""
    try:
        row = frappe.db.get_value(
            "Improvement Exam Registration",
            {"student": student_name, "exam_plan": exam_plan, "course": course, "status": ["!=", "Cancelled"]},
            ["name", "payment_status"],
            as_dict=True,
        )
        return row or None
    except Exception:
        return None


def _get_arrear_marker(student_name, course, is_currently_failing=False):
    """Return arrear marker based on total arrear count.

    total = re-exam registrations (non-cancelled) + 1 if currently failing.
    This means the very first failure already shows R.
    >= 3 total → RR, >= 1 → R, 0 → ''.
    """
    try:
        reg_count = frappe.db.count(
            "Re Exam Registration",
            filters={
                "student": student_name,
                "course": course,
                "status": ["!=", "Cancelled"],
            },
        )
        total = reg_count + (1 if is_currently_failing else 0)
        if total >= 3:
            return "RR"
        elif total >= 1:
            return "R"
    except Exception:
        pass
    return ""


# ── Nav helpers ───────────────────────────────────────────────────────────────

def _get_student_name():
    user = frappe.session.user
    name = frappe.db.get_value("Student Master", {"user": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"email": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
    return name


def _set_student_nav(context, student):
    full_name = " ".join(
        filter(None, [student.first_name, student.middle_name, student.last_name])
    )
    context.student_name    = full_name or student.name
    context.student_id      = student.registration_id or student.name
    context.student_photo   = student.passport_size_photo or ""
    context.student_initial = (
        context.student_name[0].upper() if context.student_name else "S"
    )
    context.programme_name = (
        frappe.db.get_value("Batch", student.programme, "cohort_name")
        or student.programme or ""
    )
    context.department = student.department or ""
    context.batch_year = student.batch_year or ""
    context.academic_year = student.get("academic_year") or ""
    context.academic_term = student.get("academic_term") or _current_enrollment_term(student.name)


def _current_enrollment_term(student_name):
    """Current trimester from the latest Enrolled Student Enrollment (same as the Fees page)."""
    try:
        return frappe.db.get_value(
            "Student Enrollment",
            {"student": student_name, "status": "Enrolled"},
            "term_name",
            order_by="creation desc",
        ) or ""
    except Exception:
        return ""


def _set_nav_defaults(context):
    user     = frappe.session.user
    user_doc = frappe.db.get_value(
        "User", user, ["full_name", "user_image"], as_dict=True
    )
    context.student_name    = (user_doc.full_name if user_doc else "") or user.split("@")[0]
    context.student_id      = ""
    context.student_photo   = (user_doc.user_image if user_doc else "") or ""
    context.student_initial = (
        context.student_name[0].upper() if context.student_name else "S"
    )
    context.programme_name = ""
    context.department     = ""
    context.batch_year     = ""

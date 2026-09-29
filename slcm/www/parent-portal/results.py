import frappe
from slcm.slcm.utils.parent_portal import get_parent_context

no_cache = 1


def get_context(context):
    student = get_parent_context(context)
    if context.is_guest or context.not_a_parent or not student:
        context.published_results = []
        context.has_results = False
        context.gpa_chart_data = []
        return context

    context.active_page = "results"

    try:
        student_name = student.name

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
            ep = frappe.db.get_value(
                "Exam Plan", ep_name,
                ["exam_name", "term", "status"], as_dict=True,
            ) or frappe._dict()

            setting        = _get_publish_setting(ep_name)
            show_total     = bool(setting and setting.show_total_marks)
            show_sgpa      = bool(setting and setting.show_sgpa)
            hide_sgpa_fail = bool(setting and setting.hide_sgpa_for_failed)

            allowed_components = set()
            if setting and setting.publish_components:
                for pc in setting.publish_components:
                    if pc.component:
                        allowed_components.add(pc.component)

            marks_records = frappe.get_all(
                "Student Course Marks",
                filters={"student": student_name, "exam_plan": ep_name},
                fields=[
                    "name", "course", "total_marks", "grade", "moderated_grade",
                    "updated_final_marks", "updated_grade", "re_exam_grade",
                    "enrollment_status", "attendance_status",
                    "mfa", "remark", "consider_for_sgpa",
                ],
                ignore_permissions=True,
            )

            courses_out  = []
            has_any_fail = False

            for m in marks_records:
                course_name = frappe.db.get_value("Course", m.course, "course_name") or m.course
                regular_groups, reexam_groups = _get_component_groups(m.name, ep_name, m.course, allowed_components)

                raw_total = m.updated_final_marks or m.total_marks or sum(
                    c["effective_marks"] for grp in regular_groups for c in grp["components"]
                )
                display_total = round(float(raw_total), 2) if raw_total else None
                display_grade = m.updated_grade or m.moderated_grade or m.grade or ""

                if display_grade:
                    is_fail = _is_failing_grade(display_grade, ep_name, m.course)
                    overall_status = "Fail" if is_fail else "Pass"
                    if is_fail:
                        has_any_fail = True
                else:
                    is_fail, overall_status = False, ""

                att_status    = m.attendance_status or _get_attendance_fallback(student_name, m.course, ep_name)
                enroll_status = m.enrollment_status or _get_enrollment_fallback(student_name, m.course)

                courses_out.append({
                    "course":            m.course,
                    "course_name":       course_name,
                    "display_grade":     display_grade,
                    "display_total":     display_total,
                    "overall_status":    overall_status,
                    "is_fail":           is_fail,
                    "enrollment_status": enroll_status,
                    "attendance_status": att_status,
                    "mfa":               m.mfa or "",
                    "remark":            m.remark or "",
                    "consider_for_sgpa": int(m.consider_for_sgpa or 1),
                    "regular_groups":    regular_groups,
                    "reexam_groups":     reexam_groups,
                    "has_comp_marks":    bool(regular_groups or reexam_groups),
                    "show_total":        show_total,
                    "re_exam_grade":     m.re_exam_grade or "",
                })

            courses_out.sort(key=lambda c: c["course_name"])

            pass_count    = sum(1 for c in courses_out if c["overall_status"] == "Pass")
            fail_count    = sum(1 for c in courses_out if c["overall_status"] == "Fail")
            pending_count = sum(1 for c in courses_out if c["overall_status"] == "")

            term_gpa = round(float(rec.term_gpa), 2)              if rec.term_gpa            else None
            term_pct = round(float(rec.term_percentage), 2)       if rec.term_percentage      else None
            cgpa     = round(float(rec.cumulative_gpa), 2)        if rec.cumulative_gpa       else None
            cpct     = round(float(rec.cumulative_percentage), 2) if rec.cumulative_percentage else None

            if show_sgpa and hide_sgpa_fail and has_any_fail:
                term_gpa = term_pct = None

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

        published_results.sort(key=lambda r: str(r["published_on"] or ""), reverse=True)
        context.published_results = published_results
        context.has_results = bool(published_results)

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
        frappe.log_error(f"Parent Portal Results error: {e}", "Parent Portal")
        context.published_results = []
        context.has_results = False
        context.gpa_chart_data = []

    return context


# ── Helpers (mirrored from student portal results.py) ──────────────────────────

def _get_publish_setting(exam_plan):
    try:
        return frappe.get_doc("Publish Result Setting", exam_plan, ignore_permissions=True)
    except Exception:
        return None


def _is_failing_grade(grade, exam_plan=None, course=None):
    if not grade:
        return False
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
    return grade.upper() in {"F", "FF", "FAIL", "AB", "I", "W", "U", "E"}


def _get_component_groups(marks_doc_name, exam_plan, course, allowed_components):
    try:
        evaluation_schema = frappe.db.get_value(
            "Course Schema Assignment",
            {"exam_plan": exam_plan, "course": course},
            "evaluation_schema",
        )
        if not evaluation_schema:
            return [], []

        regular_cols = frappe.db.sql(
            """
            SELECT sac.component, ec.component_name,
                   sac.assessment_type, eat.type_name,
                   sac.label, sac.maximum_marks, sac.idx
            FROM `tabSchema Assessment Config` sac
            LEFT JOIN `tabExam Component` ec  ON ec.name  = sac.component
            LEFT JOIN `tabExam Assessment Type` eat ON eat.name = sac.assessment_type
            WHERE sac.parent = %s ORDER BY sac.idx ASC
            """,
            (evaluation_schema,), as_dict=True,
        )

        reexam_cols = frappe.db.sql(
            """
            SELECT src.component, ec.component_name,
                   src.assessment_type, eat.type_name,
                   src.label, src.maximum_marks, src.idx
            FROM `tabSchema Reexam Config` src
            LEFT JOIN `tabExam Component` ec  ON ec.name  = src.component
            LEFT JOIN `tabExam Assessment Type` eat ON eat.name = src.assessment_type
            WHERE src.parent = %s ORDER BY src.idx ASC
            """,
            (evaluation_schema,), as_dict=True,
        )

        entries = frappe.get_all(
            "Student Marks Entry",
            filters={"parent": marks_doc_name},
            fields=["component", "assessment_type", "marks", "revaluation_marks", "moderated_marks"],
            ignore_permissions=True,
        )
        marks_map = {(e.component or "") + "|" + (e.assessment_type or ""): e for e in entries}

        def _build_groups(cols):
            groups, group_keys = {}, []
            for col in cols:
                if allowed_components and col.get("component") not in allowed_components:
                    continue
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
                    "label":             col.get("label") or col.get("type_name") or "—",
                    "max_marks":         float(col.get("maximum_marks") or 0),
                    "marks":             marks,
                    "revaluation_marks": reval,
                    "effective_marks":   eff,
                })
            return [{"type_name": k, "components": groups[k]} for k in group_keys]

        return _build_groups(regular_cols), _build_groups(reexam_cols)
    except Exception as e:
        frappe.log_error(f"_get_component_groups (parent portal): {e}", "Parent Portal")
        return [], []


def _get_attendance_fallback(student_name, course, exam_plan):
    try:
        row = frappe.db.get_value(
            "Attendance Summary",
            {"student": student_name, "course": course},
            ["attendance_percentage", "student_status"], as_dict=True,
        )
        if row:
            if row.get("student_status"):
                return row.student_status
            pct = float(row.attendance_percentage or 0)
            return "Present" if pct >= 75 else ("Low Attendance" if pct >= 60 else "Detained")
    except Exception:
        pass
    return ""


def _get_enrollment_fallback(student_name, course):
    try:
        row = frappe.db.get_value(
            "Student Enrollment Course",
            {"student": student_name, "course": course},
            "enrollment_status",
        )
        return row or ""
    except Exception:
        return ""

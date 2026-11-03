import frappe
from slcm.slcm.utils.exam_schedule import get_student_programme

no_cache = 1


def get_context(context):
    context.no_cache = 1

    user = frappe.session.user

    if user == "Guest":
        _log_access(user=user, student=None, outcome="denied_guest")
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "re_exam"

    # Ownership enforcement: student_name is derived solely from the
    # session user's linked Student Master record — the caller cannot
    # influence which student's data is loaded (no student param accepted).
    student_name = _get_student_name()
    if not student_name:
        _log_access(user=user, student=None, outcome="denied_no_student")
        context.no_student = True
        _set_nav_defaults(context)
        context.failed_courses = []
        context.all_passed = False
        return context

    context.no_student = False

    _log_access(user=user, student=student_name, outcome="allowed")

    try:
        student = frappe.get_doc("Student Master", student_name)
        _set_student_nav(context, student)

        # Fetch all student course marks with grades
        marks_rows = frappe.db.sql(
            """
            SELECT
                scm.name,
                scm.exam_plan,
                scm.course,
                scm.grade,
                scm.total_marks,
                scm.status
            FROM `tabStudent Course Marks` scm
            WHERE scm.student = %(student)s
              AND scm.grade IS NOT NULL AND scm.grade != ''
            ORDER BY scm.exam_plan, scm.course
            """,
            {"student": student_name},
            as_dict=True,
        )

        # ── Fetch ALL registrations for this student in one raw query ──────
        # Raw SQL bypasses all Frappe permission layers so a paid registration
        # is never hidden, regardless of the `status` field or role setup.
        raw_regs = frappe.db.sql(
            """
            SELECT name, exam_plan, course, status, payment_status, payment_reference
            FROM `tabRe Exam Registration`
            WHERE student = %(student)s
            ORDER BY modified DESC
            """,
            {"student": student_name},
            as_dict=True,
        )

        # Build a lookup: (exam_plan, course) → best registration
        # Priority: Paid/Captured > any non-Cancelled > first found
        reg_map = {}
        for r in raw_regs:
            key = (r.get("exam_plan"), r.get("course"))
            existing = reg_map.get(key)
            if existing is None:
                reg_map[key] = r
            elif r.get("payment_status") in ("Paid", "Captured"):
                # Always prefer a paid registration over whatever was there
                reg_map[key] = r
            elif (existing.get("payment_status") not in ("Paid", "Captured")
                  and r.get("status") != "Cancelled"
                  and existing.get("status") == "Cancelled"):
                reg_map[key] = r

        # Fallback map: course → paid registration, used when the primary
        # (exam_plan, course) key doesn't match due to any data inconsistency
        paid_by_course = {}
        for r in raw_regs:
            c = r.get("course")
            if c and r.get("payment_status") in ("Paid", "Captured"):
                existing = paid_by_course.get(c)
                if existing is None:
                    paid_by_course[c] = r

        failed_courses = []

        for row in marks_rows:
            # Determine failed grades for this exam_plan+course
            assignment = frappe.db.sql(
                """
                SELECT grade_schema FROM `tabCourse Schema Assignment`
                WHERE course = %(course)s AND exam_plan = %(exam_plan)s
                LIMIT 1
                """,
                {"course": row.course, "exam_plan": row.exam_plan},
                as_dict=True,
            )
            grade_schema = assignment[0]["grade_schema"] if assignment else None

            if not grade_schema:
                row_gs = frappe.db.get_value(
                    "Course Schema Assignment", {"course": row.course}, "grade_schema"
                )
                grade_schema = row_gs or None

            # Prefer reexam_eligibility_criteria from grading schema if defined;
            # fall back to grades marked failed=1 in the regular composition.
            eligible_grades = []
            if grade_schema:
                criteria_rows = frappe.db.sql(
                    "SELECT criteria FROM `tabGrading Schema Reexam Criteria` WHERE parent = %s",
                    grade_schema,
                    as_list=True,
                )
                eligible_grades = [r[0] for r in criteria_rows if r[0]]

            if not eligible_grades and grade_schema:
                fg_rows = frappe.db.sql(
                    "SELECT grade FROM `tabGrading Schema Component` WHERE parent = %s AND failed = 1",
                    grade_schema,
                    as_list=True,
                )
                eligible_grades = [r[0] for r in fg_rows if r[0]]

            is_failed = False
            if eligible_grades:
                is_failed = row.grade in eligible_grades
            else:
                # No criteria defined — treat any graded student as needing re-exam check
                is_failed = bool(row.grade)

            if not is_failed:
                continue

            # Check if admin has explicitly blocked this student
            override = frappe.db.get_value(
                "Re Exam Student Override",
                {"exam_plan": row.exam_plan, "course": row.course, "student": student_name},
                "is_allowed",
            )
            student_is_allowed = not (override is not None and not override)

            # Fetch re-exam setting for this exam_plan+course
            setting = frappe.db.get_value(
                "Re Exam Course Setting",
                {"exam_plan": row.exam_plan, "course": row.course},
                ["re_exam_fee", "deadline_from", "deadline_to"],
                as_dict=True,
            ) or {}

            ep = frappe.db.get_value(
                "Exam Plan",
                row.exam_plan,
                ["exam_name", "term"],
                as_dict=True,
            ) or frappe._dict()

            course_name = frappe.db.get_value("Course", row.course, "course_name") or row.course

            deadline_from_str = frappe.utils.formatdate(setting.get("deadline_from"), "d MMM yyyy") if setting.get("deadline_from") else ""
            deadline_to_str   = frappe.utils.formatdate(setting.get("deadline_to"),   "d MMM yyyy") if setting.get("deadline_to")   else ""

            # Check deadline status using proper date objects to avoid string/timezone bugs
            today_date = frappe.utils.getdate(frappe.utils.nowdate())
            deadline_passed = False
            deadline_active = False
            if setting.get("deadline_to"):
                deadline_passed = frappe.utils.getdate(setting["deadline_to"]) < today_date
            if setting.get("deadline_from") and setting.get("deadline_to") and not deadline_passed:
                deadline_active = (
                    frappe.utils.getdate(setting["deadline_from"]) <= today_date
                    <= frappe.utils.getdate(setting["deadline_to"])
                )

            days_remaining = None
            if setting.get("deadline_to") and not deadline_passed:
                days_remaining = max(frappe.utils.date_diff(setting["deadline_to"], today_date), 0)

            # Look up pre-fetched registration from the bulk map.
            # Fall back to paid_by_course if the primary key doesn't match
            # (guards against any exam_plan value inconsistency in the DB).
            reg = (
                reg_map.get((row.exam_plan, row.course))
                or paid_by_course.get(row.course)
                or frappe._dict()
            )

            failed_courses.append({
                "exam_plan":          row.exam_plan,
                "exam_name":          ep.exam_name or row.exam_plan,
                "term":               ep.term or "",
                "course":             row.course,
                "course_name":        course_name,
                "grade":              row.grade,
                "total_marks":        row.total_marks,
                "re_exam_fee":        setting.get("re_exam_fee"),
                "deadline_from":      deadline_from_str,
                "deadline_to":        deadline_to_str,
                "_deadline_to_raw":   frappe.utils.getdate(setting["deadline_to"]) if setting.get("deadline_to") else None,
                "_deadline_from_raw": frappe.utils.getdate(setting["deadline_from"]) if setting.get("deadline_from") else None,
                "deadline_passed":    deadline_passed,
                "deadline_active":    deadline_active,
                "has_setting":        bool(setting),
                "is_allowed":         student_is_allowed,
                "registration_name":  reg.get("name") or "",
                "registration_status": reg.get("status") or "",
                "payment_status":     reg.get("payment_status") or "",
                "is_paid":            reg.get("payment_status") in ("Paid", "Captured"),
                "is_registered":      bool(reg.get("name")),
                "days_remaining":     days_remaining,
            })

        # Sort: latest deadline_to first; ties broken by latest deadline_from.
        # Courses with no deadline setting fall to the bottom.
        _epoch = frappe.utils.getdate("1900-01-01")
        failed_courses.sort(
            key=lambda fc: (
                fc["_deadline_to_raw"]   or _epoch,
                fc["_deadline_from_raw"] or _epoch,
            ),
            reverse=True,
        )

        context.failed_courses = failed_courses
        context.all_passed = len(failed_courses) == 0
        context.failed_count = len(failed_courses)

    except Exception as exc:
        frappe.log_error(f"Re Exam portal error: {exc}", "Student Portal Re Exam")
        context.portal_error = str(exc)
        context.failed_courses = []
        context.all_passed = False

    return context


def _get_student_name():
    user = frappe.session.user
    name = frappe.db.get_value("Student Master", {"user": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"email": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
    return name


def _set_student_nav(context, student):
    full = " ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))
    context.student_name    = full or student.name
    context.student_id      = student.registration_id or student.name
    context.student_photo   = student.passport_size_photo or ""
    context.student_initial = context.student_name[0].upper() if context.student_name else "S"
    context.programme_name  = get_student_programme(student.name)
    context.department  = student.department or ""
    context.batch_year  = student.batch or ""


def _set_nav_defaults(context):
    user     = frappe.session.user
    user_doc = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True)
    context.student_name    = (user_doc.full_name if user_doc else "") or user.split("@")[0]
    context.student_id      = ""
    context.student_photo   = (user_doc.user_image if user_doc else "") or ""
    context.student_initial = context.student_name[0].upper() if context.student_name else "S"
    context.programme_name  = ""
    context.department      = ""
    context.batch_year      = ""


def _log_access(user, student, outcome):
    """Write a lightweight access log entry to the Frappe error log.

    outcome values:
      allowed             — authenticated student, data served
      denied_guest        — unauthenticated request
      denied_no_student   — authenticated user with no Student Master record
    """
    try:
        ip = frappe.local.request.environ.get("REMOTE_ADDR", "unknown") if frappe.local.request else "unknown"
        msg = (
            f"Re Exam portal access | outcome={outcome} "
            f"| user={user} | student={student or 'none'} | ip={ip}"
        )
        if outcome == "allowed":
            frappe.logger("slcm.re_exam_access").info(msg)
        else:
            frappe.log_error(msg, "Student Portal Re Exam Access Denied")
    except Exception:
        pass

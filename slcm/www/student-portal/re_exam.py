import frappe

no_cache = 1


def get_context(context):
    context.no_cache = 1

    # Respect the Student Portal Settings toggle for Re Exam menu
    enabled = frappe.db.get_single_value("Student Portal Settings", "enable_re_exam_menu")
    if enabled == 0:
        frappe.local.flags.redirect_location = "/student-portal"
        raise frappe.Redirect

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "re_exam"

    student_name = _get_student_name()
    if not student_name:
        context.no_student = True
        _set_nav_defaults(context)
        context.failed_courses = []
        context.all_passed = False
        return context

    context.no_student = False

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

            failed_grades = []
            if grade_schema:
                fg_rows = frappe.db.sql(
                    "SELECT grade FROM `tabGrading Schema Component` WHERE parent = %s AND failed = 1",
                    grade_schema,
                    as_list=True,
                )
                failed_grades = [r[0] for r in fg_rows if r[0]]

            is_failed = False
            if failed_grades:
                is_failed = row.grade in failed_grades
            else:
                # No failed flags set — treat any graded student as needing re-exam check
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

            # Check deadline status
            today = frappe.utils.today()
            deadline_passed = False
            deadline_active = False
            if setting.get("deadline_to"):
                deadline_passed = str(setting["deadline_to"]) < today
            if setting.get("deadline_from") and setting.get("deadline_to"):
                deadline_active = str(setting["deadline_from"]) <= today <= str(setting["deadline_to"])

            failed_courses.append({
                "exam_plan":        row.exam_plan,
                "exam_name":        ep.exam_name or row.exam_plan,
                "term":             ep.term or "",
                "course":           row.course,
                "course_name":      course_name,
                "grade":            row.grade,
                "total_marks":      row.total_marks,
                "re_exam_fee":      setting.get("re_exam_fee"),
                "deadline_from":    deadline_from_str,
                "deadline_to":      deadline_to_str,
                "deadline_passed":  deadline_passed,
                "deadline_active":  deadline_active,
                "has_setting":      bool(setting),
                "is_allowed":       student_is_allowed,
            })

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
    context.programme_name  = (
        frappe.db.get_value("SLCM Batch", student.programme, "cohort_name")
        or student.programme or ""
    )
    context.department  = student.department or ""
    context.batch_year  = student.batch_year or ""


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

import frappe

no_cache = 1


def get_context(context):
    context.no_cache = 1

    # ── Guest redirect ─────────────────────────────────────────
    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "dashboard"

    # ── Role check: block non-student accounts ────────────────
    roles = frappe.get_roles(frappe.session.user)
    has_student_role = "slcm_student" in roles or "Student" in roles
    student_name = _get_student_name()
    if not has_student_role and not student_name:
        context.not_a_student = True
        _set_nav_defaults(context)
        return context

    context.not_a_student = False

    # ── Find Student Master ────────────────────────────────────
    if not student_name:
        context.no_student = True
        _set_nav_defaults(context)
        return context

    context.no_student = False

    try:
        student = frappe.get_doc("Student Master", student_name)
        _set_student_nav(context, student)

        # ── Active Enrollment ──────────────────────────────────
        enrollment = _get_active_enrollment(student_name)
        context.enrollment = enrollment

        # ── Attendance Summaries ───────────────────────────────
        att_summaries = frappe.get_all(
            "Attendance Summary",
            filters={"student": student_name},
            fields=["attendance_percentage", "eligible_for_exam", "course_offering", "course"],
            order_by="creation desc",
            limit=50,
            ignore_permissions=True,
        )

        # Build a fast lookup map
        att_map = {}
        for s in att_summaries:
            if s.course_offering:
                att_map[s.course_offering] = s
            if s.course:
                att_map.setdefault(s.course, s)

        if att_summaries:
            pcts = [s.attendance_percentage or 0 for s in att_summaries]
            avg_att = round(sum(pcts) / len(pcts), 1)
        else:
            avg_att = 0.0

        # Enrich att_summaries with course display names and faculty
        for s in att_summaries:
            co_name = s.course_offering or ""
            s["course_display"] = s.course or co_name or "—"
            s["faculty"] = "—"
            if co_name:
                try:
                    co = frappe.db.get_value(
                        "Course Offering", co_name,
                        ["course_name", "faculty", "credit_value"],
                        as_dict=True,
                    )
                    if co:
                        if co.course_name:
                            s["course_display"] = co.course_name
                        s["faculty"] = co.faculty or "—"
                        s["credits"] = co.credit_value or 0
                except Exception:
                    pass

        context.avg_attendance = avg_att
        context.attendance_summaries = att_summaries[:6]
        context.courses_eligible = sum(1 for s in att_summaries if s.eligible_for_exam)

        # ── Course Count from enrollment child rows (Student Enrollment Course) ──
        enrolled_courses = []
        if enrollment:
            enrolled_courses = frappe.get_all(
                "Student Enrollment Course",
                filters={"parent": enrollment.name},
                fields=["course_offering", "course", "credits", "course_type", "status", "grade"],
                ignore_permissions=True,
            )

        # Fallback: derive course list from attendance summaries if child rows empty
        if not enrolled_courses and att_summaries:
            enrolled_courses = [
                frappe._dict({
                    "course_offering": s.course_offering or "",
                    "course": s.course or "",
                    "credits": s.get("credits") or 0,
                    "course_type": "—",
                    "_faculty": s.get("faculty") or "—",
                })
                for s in att_summaries
            ]

        context.course_count = len(enrolled_courses)

        # ── Stat: Outstanding Fees ─────────────────────────────
        fee_invoices = frappe.get_all(
            "Fee Invoice",
            filters={"student": student_name},
            fields=["name", "academic_term", "final_payable_amount", "paid_amount",
                    "outstanding_amount", "status", "due_date"],
            order_by="creation desc",
            limit=20,
            ignore_permissions=True,
        )

        total_outstanding = sum(inv.outstanding_amount or 0 for inv in fee_invoices)
        context.total_outstanding = total_outstanding
        context.fee_invoices = fee_invoices[:3]
        context.has_dues = total_outstanding > 0

        # ── CGPA ──────────────────────────────────────────────
        context.cgpa = round(student.current_cgpa or 0.0, 2)

        # ── Courses Quick View ─────────────────────────────────
        course_display = []
        for ec in enrolled_courses[:6]:
            co_name = ec.get("course_offering") or ""
            course_id = ec.course or ""

            co_data = frappe._dict()
            if co_name:
                try:
                    co = frappe.db.get_value(
                        "Course Offering",
                        co_name,
                        ["course_name", "faculty", "credit_value", "term_name"],
                        as_dict=True,
                    )
                    if co:
                        co_data = co
                except Exception:
                    pass

            att = att_map.get(co_name) or att_map.get(course_id) or frappe._dict()
            att_pct = round(float(att.get("attendance_percentage") or 0), 1)

            course_display.append({
                "course_offering": co_name,
                "course": course_id,
                "course_name": co_data.get("course_name") or ec.get("course_name") or course_id or "—",
                "credits": co_data.get("credit_value") or ec.get("credits") or 0,
                "faculty": co_data.get("faculty") or ec.get("_faculty") or "—",
                "attendance_pct": att_pct,
            })

        context.courses_display = course_display

        # ── Upcoming / Today's Sessions ─────────────────────────
        today = frappe.utils.today()
        context.calendar_today = today  # My Calendar's "Today"
        enrolled_co_set = {s.course_offering for s in att_summaries if s.course_offering}
        context.todays_classes = []
        if enrolled_co_set:
            try:
                todays_raw = frappe.get_all(
                    "Time Table",
                    filters=[
                        ["course_offering", "in", list(enrolled_co_set)],
                        ["schedule_date", "=", today],
                    ],
                    fields=[
                        "name", "course", "course_offering", "instructor",
                        "from_time", "to_time", "venue", "title",
                    ],
                    order_by="from_time asc",
                    limit=6,
                    ignore_permissions=True,
                )
                co_names = [row.course_offering for row in todays_raw if row.course_offering]
                co_info = {}
                if co_names:
                    co_rows = frappe.get_all(
                        "Course Offering",
                        filters={"name": ["in", co_names]},
                        fields=["name", "course_name", "faculty"],
                        ignore_permissions=True,
                    )
                    co_info = {row.name: row for row in co_rows}
                for row in todays_raw:
                    co = co_info.get(row.course_offering, frappe._dict())
                    context.todays_classes.append({
                        "course_name": co.get("course_name") or row.title or row.course or row.course_offering or "Class",
                        "faculty": co.get("faculty") or row.instructor or "",
                        "from_time": _fmt_time(row.from_time),
                        "to_time": _fmt_time(row.to_time),
                        "venue": row.venue or "",
                    })
            except Exception:
                context.todays_classes = []
        # Next 7 days of timetable entries for the dashboard Timetable panel
        context.week_classes = []
        if enrolled_co_set:
            try:
                week_raw = frappe.get_all(
                    "Time Table",
                    filters=[
                        ["course_offering", "in", list(enrolled_co_set)],
                        ["schedule_date", "between", [today, frappe.utils.add_days(today, 6)]],
                    ],
                    fields=["course", "course_offering", "schedule_date",
                            "from_time", "to_time", "venue", "title"],
                    order_by="schedule_date asc, from_time asc",
                    limit=8,
                    ignore_permissions=True,
                )
                wk_cos = list({r.course_offering for r in week_raw if r.course_offering})
                wk_names = dict(frappe.get_all(
                    "Course Offering", filters={"name": ["in", wk_cos]},
                    fields=["name", "course_name"], as_list=True, ignore_permissions=True,
                )) if wk_cos else {}
                for r in week_raw:
                    context.week_classes.append({
                        "course_name": wk_names.get(r.course_offering) or r.title or r.course or "Class",
                        "date": frappe.utils.formatdate(r.schedule_date, "EEE, dd MMM"),
                        "is_today": str(r.schedule_date) == str(today),
                        "from_time": _fmt_time(r.from_time),
                        "to_time": _fmt_time(r.to_time),
                        "venue": r.venue or "",
                    })
            except Exception:
                context.week_classes = []
        try:
            upcoming_sessions = frappe.get_all(
                "Attendance Session",
                filters=[
                    ["session_date", ">=", today],
                    ["status", "=", "Active"],
                ],
                fields=["name", "session_date", "start_time", "course_offering",
                        "session_type", "venue"],
                order_by="session_date asc, start_time asc",
                limit=10,
                ignore_permissions=True,
            )
            context.upcoming_sessions = [
                s for s in upcoming_sessions if s.course_offering in enrolled_co_set
            ][:4]
        except Exception:
            context.upcoming_sessions = []

        # ── Important links (Student Portal Settings) ─────────
        try:
            _ps = frappe.get_single("Student Portal Settings")
            context.important_links = {
                "academic_calendar": _ps.get("academic_calendar") or "#",
                "student_handbook": _ps.get("student_handbook") or "#",
                "examination_guidelines": _ps.get("examination_guidelines") or "#",
            }
        except Exception:
            context.important_links = {"academic_calendar": "#", "student_handbook": "#", "examination_guidelines": "#"}

        # ── Student status info ────────────────────────────────
        context.student_status = student.student_status or "Active"
        context.registration_status = student.registration_status or ""
        context.current_term = student.current_term or ""
        context.current_year = student.current_year or ""
        context.year_of_study = _ordinal_year(student.current_year)
        context.academic_year = student.academic_year or ""
        context.is_hosteller = student.is_hosteller or 0

    except Exception as e:
        frappe.log_error(f"Student Portal Dashboard error: {e}", "Student Portal")
        context.portal_error = str(e)
        _set_nav_defaults(context)

    return context


def _get_student_name():
    user = frappe.session.user
    name = frappe.db.get_value("Student Master", {"user": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"email": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
    if name:
        try:
            if not frappe.db.get_value("Student Master", name, "user"):
                frappe.db.set_value("Student Master", name, "user", user, update_modified=False)
        except Exception:
            pass
    return name


def _get_active_enrollment(student_name):
    enrollments = frappe.get_all(
        "Student Enrollment",
        filters={"student": student_name, "status": "Enrolled"},
        fields=["name", "cohort", "program", "academic_year", "term_name",
                "status", "faculty_advisor", "enrollment_date"],
        order_by="creation desc",
        limit=1,
        ignore_permissions=True
    )
    if enrollments:
        return enrollments[0]
    # Fallback: any enrollment
    all_enrollments = frappe.get_all(
        "Student Enrollment",
        filters={"student": student_name},
        fields=["name", "cohort", "program", "academic_year", "term_name",
                "status", "faculty_advisor", "enrollment_date"],
        order_by="creation desc",
        limit=1,
        ignore_permissions=True
    )
    return all_enrollments[0] if all_enrollments else None


def _fmt_time(t):
    if t is None:
        return ""
    if hasattr(t, "seconds"):
        total = int(t.seconds)
        h, rem = divmod(total, 3600)
        m = rem // 60
    elif isinstance(t, str):
        parts = t.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    else:
        return str(t)
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def _set_student_nav(context, student):
    full_name = " ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))
    context.student_name = full_name or student.name
    context.student_id = student.registration_id or student.name
    context.student_photo = student.passport_size_photo or ""
    context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
    prog_name = frappe.db.get_value("Batch", student.programme, "cohort_name") if student.programme else None
    if not prog_name and student.programme_of_study:
        prog_name = frappe.db.get_value("Programme", student.programme_of_study, "program_name")
    context.programme_name = prog_name or student.programme or student.programme_of_study or ""

    context.department = student.department or ""
    context.batch_year = student.batch_year or ""


def _ordinal_year(val):
    if not val:
        return ""
    try:
        n = int(val)
    except (ValueError, TypeError):
        return str(val)
    suffixes = ["th", "st", "nd", "rd"]
    v = n % 100
    # 11, 12, 13 are exceptions — always "th"
    if 11 <= v <= 13:
        suffix = "th"
    else:
        r = n % 10
        suffix = suffixes[r] if r < len(suffixes) else "th"
    return f"{n}{suffix} Year"


def _set_nav_defaults(context):
    user = frappe.session.user
    user_doc = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True)
    context.student_name = (user_doc.full_name if user_doc else "") or user.split("@")[0]
    context.student_id = ""
    context.student_photo = (user_doc.user_image if user_doc else "") or ""
    context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
    context.programme_name = ""
    context.department = ""
    context.batch_year = ""

import frappe
from slcm.utils.faculty_portal import get_faculty_name, set_faculty_nav, set_nav_defaults, set_portal_settings

no_cache = 1


def get_context(context):
    context.no_cache = 1
    set_portal_settings(context)
    _set_defaults(context)

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "my_classes"
    context.not_a_faculty = False

    faculty_name = get_faculty_name()
    if not faculty_name:
        context.not_a_faculty = True
        set_nav_defaults(context)
        return context

    try:
        faculty = frappe.get_doc("Faculty", faculty_name)
        set_faculty_nav(context, faculty)
    except Exception as e:
        frappe.log_error(f"Faculty Portal Classes page - faculty load error: {e}", "Faculty Portal")
        context.not_a_faculty = True
        set_nav_defaults(context)
        return context

    try:
        from slcm.api.faculty_portal import _active_academic_years, _class_label

        raw_classes = frappe.get_all(
            "Classes",
            filters={"faculty": faculty_name},
            fields=["name", "course", "course_name", "class_type", "section", "group_name",
                    "academic_term", "academic_year", "credit"],
            order_by="academic_year desc, academic_term asc, course_name asc",
            ignore_permissions=True,
        )
        active_ays = set(_active_academic_years())

        enriched = []
        for cls in raw_classes:
            student_count = _get_student_count(cls.name)
            avg_att, sessions_done = _get_attendance(cls.name)
            enriched.append({
                "name": cls.name,
                "course": cls.course or "",
                "course_name": _class_label(cls),
                "term_name": cls.academic_term or "—",
                "academic_term": cls.academic_term or "",
                "academic_year": cls.academic_year or "—",
                "credits": cls.credit or 0,
                "student_count": student_count,
                "avg_attendance": avg_att,
                "sessions_done": sessions_done,
                # Classes carry no status: a class of an Active academic year is current
                "status": "Active" if cls.academic_year in active_ays else "Closed",
            })

        context.faculty_classes = enriched
        context.filter_terms = sorted(
            set(c["term_name"] for c in enriched if c["term_name"] != "—")
        )
        context.filter_years = sorted(
            set(c["academic_year"] for c in enriched if c["academic_year"] != "—"),
            reverse=True,
        )

        # Summary stats
        context.total_courses = len(enriched)
        context.total_students = sum(c["student_count"] for c in enriched)
        context.total_sessions = sum(c["sessions_done"] for c in enriched)
        context.active_courses = sum(1 for c in enriched if c["status"] == "Active")
        att_values = [c["avg_attendance"] for c in enriched if c["avg_attendance"] > 0]
        context.overall_avg_att = (
            round(sum(att_values) / len(att_values), 1) if att_values else 0.0
        )

    except Exception as e:
        frappe.log_error(
            f"Faculty Portal Classes page error for faculty {faculty_name}: {e}",
            "Faculty Portal",
        )
        context.portal_error = str(e)

    return context


def _get_student_count(class_name):
    try:
        return frappe.db.count(
            "Class Enrolled Student",
            {"parenttype": "Classes", "parent": class_name, "status": "Enrolled"},
        )
    except Exception:
        return 0


def _get_attendance(class_name):
    try:
        rows = frappe.db.sql(
            """SELECT AVG(attendance_percentage) AS avg_pct, COUNT(*) AS sess
               FROM `tabAttendance Session`
               WHERE class_name = %s AND attendance_marked = 1""",
            class_name,
            as_dict=True,
        )
        avg_pct = round(float((rows[0].avg_pct or 0) if rows else 0), 1)
        sessions = int((rows[0].sess or 0) if rows else 0)
        return avg_pct, sessions
    except Exception:
        return 0.0, 0


def _set_defaults(context):
    context.is_guest = False
    context.not_a_faculty = False
    context.faculty_classes = []
    context.filter_terms = []
    context.filter_years = []
    context.total_courses = 0
    context.total_students = 0
    context.total_sessions = 0
    context.active_courses = 0
    context.overall_avg_att = 0.0
    context.portal_error = None

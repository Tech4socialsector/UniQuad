import frappe


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Rank", "fieldname": "rank", "fieldtype": "Int", "width": 60},
        {"label": "Student ID", "fieldname": "student", "fieldtype": "Link", "options": "Student Master", "width": 130},
        {"label": "Student Name", "fieldname": "student_name", "fieldtype": "Data", "width": 160},
        {"label": "Programme", "fieldname": "programme", "fieldtype": "Data", "width": 130},
        {"label": "Batch Year", "fieldname": "batch_year", "fieldtype": "Data", "width": 100},
        {"label": "Exam Plan", "fieldname": "exam_plan", "fieldtype": "Link", "options": "Exam Plan", "width": 160},
        {"label": "Term GPA", "fieldname": "term_gpa", "fieldtype": "Float", "width": 100},
        {"label": "Term %", "fieldname": "term_percentage", "fieldtype": "Percent", "width": 100},
        {"label": "Cumulative GPA", "fieldname": "cumulative_gpa", "fieldtype": "Float", "width": 120},
        {"label": "Cumulative %", "fieldname": "cumulative_percentage", "fieldtype": "Percent", "width": 120},
        {"label": "Published", "fieldname": "is_published", "fieldtype": "Check", "width": 90},
        {"label": "Published On", "fieldname": "published_on", "fieldtype": "Datetime", "width": 150},
    ]


def get_data(filters):
    conditions = "1=1"

    if filters.get("exam_plan"):
        conditions += " AND srp.exam_plan = %(exam_plan)s"
    if filters.get("student"):
        conditions += " AND srp.student = %(student)s"
    if filters.get("programme"):
        conditions += " AND sm.programme_of_study = %(programme)s"
    if filters.get("batch_year"):
        conditions += " AND sm.batch = %(batch_year)s"
    if filters.get("is_published"):
        conditions += " AND srp.is_published = 1"

    order_by = "srp.cumulative_gpa DESC, srp.cumulative_percentage DESC"

    rows = frappe.db.sql(f"""
        SELECT
            srp.student,
            sm.student_name,
            COALESCE(sm.programme_of_study, '') AS programme,
            COALESCE(sm.batch, '') AS batch_year,
            srp.exam_plan,
            srp.term_gpa,
            srp.term_percentage,
            srp.cumulative_gpa,
            srp.cumulative_percentage,
            srp.is_published,
            srp.published_on
        FROM `tabStudent Result Publish` srp
        LEFT JOIN `tabStudent Master` sm ON sm.name = srp.student
        WHERE {conditions}
        ORDER BY {order_by}
    """, filters, as_dict=True)

    for i, row in enumerate(rows, start=1):
        row["rank"] = i

    return rows

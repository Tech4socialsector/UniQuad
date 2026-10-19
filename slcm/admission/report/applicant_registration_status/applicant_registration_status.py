import frappe


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    report_summary = get_report_summary(filters)
    return columns, data, None, None, report_summary


def get_columns():
    return [
        {
            "label": "User ID",
            "fieldname": "user_id",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": "Full Name",
            "fieldname": "full_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": "Created On",
            "fieldname": "created_on",
            "fieldtype": "Datetime",
            "width": 180,
        },
        {
            "label": "Application Status",
            "fieldname": "application_status",
            "fieldtype": "Data",
            "width": 150,
        },
    ]


def build_conditions(filters):
    conditions = ["u.enabled = 1", "u.user_type = 'Website User'"]
    values = {}

    if filters.get("from_date"):
        conditions.append("u.creation >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("u.creation <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("user"):
        conditions.append("u.name = %(user)s")
        values["user"] = filters["user"]

    return " AND ".join(conditions), values


def get_data(filters):
    condition_str, values = build_conditions(filters)

    query = f"""
        SELECT
            u.email AS user_id,
            u.full_name,
            u.creation AS created_on,
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM `tabApplicant` pa
                    WHERE (pa.email = u.email OR pa.user_id = u.name) AND pa.status = 'Enrolled'
                ) THEN 'Enrolled'
                WHEN EXISTS (
                    SELECT 1 FROM `tabApplicant` pa
                    WHERE pa.email = u.email OR pa.user_id = u.name
                ) THEN 'Applied'
                ELSE 'Not Applied'
            END AS application_status
        FROM `tabUser` u
        INNER JOIN `tabHas Role` hr
            ON hr.parent = u.name AND hr.role = 'Applicant'
        WHERE {condition_str}
        ORDER BY u.full_name
    """

    rows = frappe.db.sql(query, values, as_dict=True)

    case = filters.get("case")
    if case == "With Application":
        rows = [r for r in rows if r.application_status == "Applied"]
    elif case == "Without Application":
        rows = [r for r in rows if r.application_status == "Not Applied"]
    elif case == "Enrolled":
        rows = [r for r in rows if r.application_status == "Enrolled"]

    return rows


def get_report_summary(filters):
    condition_str, values = build_conditions(filters)

    query = f"""
        SELECT
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM `tabApplicant` pa
                    WHERE (pa.email = u.email OR pa.user_id = u.name) AND pa.status = 'Enrolled'
                ) THEN 'Enrolled'
                WHEN EXISTS (
                    SELECT 1 FROM `tabApplicant` pa
                    WHERE pa.email = u.email OR pa.user_id = u.name
                ) THEN 'Applied'
                ELSE 'Not Applied'
            END AS application_status
        FROM `tabUser` u
        INNER JOIN `tabHas Role` hr
            ON hr.parent = u.name AND hr.role = 'Applicant'
        WHERE {condition_str}
    """

    rows = frappe.db.sql(query, values, as_dict=True)

    total = len(rows)
    enrolled = len([r for r in rows if r.application_status == "Enrolled"])
    applied = len([r for r in rows if r.application_status == "Applied"])
    not_applied = len([r for r in rows if r.application_status == "Not Applied"])

    return [
        {"value": total, "label": "Total Registered (Applicant)", "datatype": "Int", "indicator": "blue"},
        {"value": applied, "label": "Registered & Applied", "datatype": "Int", "indicator": "green"},
        {"value": enrolled, "label": "Enrolled", "datatype": "Int", "indicator": "green"},
        {"value": not_applied, "label": "Registered & Not Applied", "datatype": "Int", "indicator": "red"},
    ]

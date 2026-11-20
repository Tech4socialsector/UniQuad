import frappe
from frappe.utils import add_days, getdate


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

    from_date = getdate(filters["from_date"]) if filters.get("from_date") else None
    to_date = getdate(filters["to_date"]) if filters.get("to_date") else None

    if from_date and to_date and from_date > to_date:
        frappe.throw("'Registered On or After' cannot be later than 'Registered On or Before'.")

    if from_date:
        # On or After: from the start (00:00:00) of that day
        conditions.append("u.creation >= %(from_date)s")
        values["from_date"] = from_date

    if to_date:
        # On or Before: the whole of that day, i.e. everything before the next day's midnight
        # (comparing with the bare date would stop at the day's 00:00:00)
        conditions.append("u.creation < %(to_date)s")
        values["to_date"] = add_days(to_date, 1)

    if filters.get("user"):
        conditions.append("u.name = %(user)s")
        values["user"] = filters["user"]

    return " AND ".join(conditions), values


def get_registered_users(filters, sort=True):
    """Applicant-role users with their application status (Enrolled / Applied / Not Applied).

    A user "has applied" when any Applicant carries their email or their user id. That used to
    be a correlated `EXISTS (... email = u.email OR user_id = u.name)` per user, which the OR
    keeps off any index: users x applicants full scans, and a 504 on a real site. Instead the
    Applicant table is read once and matched in Python.
    """
    condition_str, values = build_conditions(filters)

    users = frappe.db.sql(
        f"""
        SELECT u.name, u.email, u.full_name, u.creation
        FROM `tabUser` u
        INNER JOIN `tabHas Role` hr
            ON hr.parent = u.name AND hr.role = 'Applicant' AND hr.parenttype = 'User'
        WHERE {condition_str}
        GROUP BY u.name
        {"ORDER BY u.full_name" if sort else ""}
        """,
        values,
        as_dict=True,
    )
    if not users:
        return []

    applied, enrolled = set(), set()
    for email, user_id, status in frappe.db.sql(
        "SELECT email, user_id, status FROM `tabApplicant` WHERE IFNULL(email, '') != '' OR IFNULL(user_id, '') != ''"
    ):
        keys = {k for k in (email, user_id) if k}
        applied |= keys
        if status == "Enrolled":
            enrolled |= keys

    for u in users:
        keys = {u.email, u.name}
        u.application_status = (
            "Enrolled" if keys & enrolled else "Applied" if keys & applied else "Not Applied"
        )
    return users


def get_data(filters):
    rows = [
        frappe._dict(
            user_id=u.email,
            full_name=u.full_name,
            created_on=u.creation,
            application_status=u.application_status,
        )
        for u in get_registered_users(filters)
    ]

    case = filters.get("case")
    if case == "With Application":
        rows = [r for r in rows if r.application_status == "Applied"]
    elif case == "Without Application":
        rows = [r for r in rows if r.application_status == "Not Applied"]
    elif case == "Enrolled":
        rows = [r for r in rows if r.application_status == "Enrolled"]

    return rows


def get_report_summary(filters):
    counts = get_registration_counts(filters.get("from_date"), filters.get("to_date"))
    return [
        {"value": counts["total"], "label": "Total Registered (Applicant)", "datatype": "Int", "indicator": "blue"},
        {"value": counts["applied"], "label": "Registered & Applied", "datatype": "Int", "indicator": "green"},
        {"value": counts["enrolled"], "label": "Enrolled", "datatype": "Int", "indicator": "green"},
        {"value": counts["not_applied"], "label": "Registered & Not Applied", "datatype": "Int", "indicator": "red"},
    ]


def get_registration_counts(from_date=None, to_date=None):
    """Applicant accounts registered in the period, by what they did next.

    Also used by the Admission Dashboard, so its cards match this report.
    """
    # Only counted, so skip sorting every user by name.
    rows = get_registered_users({"from_date": from_date, "to_date": to_date}, sort=False)

    total = len(rows)
    enrolled = len([r for r in rows if r.application_status == "Enrolled"])
    applied = len([r for r in rows if r.application_status == "Applied"])
    not_applied = len([r for r in rows if r.application_status == "Not Applied"])

    return {"total": total, "applied": applied, "enrolled": enrolled, "not_applied": not_applied}

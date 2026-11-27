import frappe
from frappe.query_builder.functions import IfNull
from frappe.utils import add_days, getdate

DOMESTIC = "Domestic"
INTERNATIONAL = "International"
APPLIED = "Applied"
ENROLLED = "Enrolled"
NOT_APPLIED = "Not Applied"


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
            "label": "Portal",
            "fieldname": "portal",
            "fieldtype": "Data",
            "width": 120,
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

    # The portal the candidate signed up on. A blank portal counts as Domestic, the same
    # default the NLSAT pages use for an account that has not applied yet.
    portal = filters.get("nlsat_portal")
    if portal in (DOMESTIC, INTERNATIONAL) and frappe.db.has_column("User", "nlsat_portal"):
        conditions.append(
            "u.nlsat_portal = %(portal)s" if portal == INTERNATIONAL else "IFNULL(u.nlsat_portal, '') != %(portal)s"
        )
        values["portal"] = INTERNATIONAL

    return " AND ".join(conditions), values


def get_registered_users(filters, sort=True):
    """Applicant-role users with their application status (Enrolled / Applied / Not Applied).

    A user "has applied" when any Applicant carries their email or their user id; with an
    `admission_cycle` filter, only that cycle's applications count. That used to
    be a correlated `EXISTS (... email = u.email OR user_id = u.name)` per user, which the OR
    keeps off any index: users x applicants full scans, and a 504 on a real site. Instead the
    Applicant table is read once and matched in Python.
    """
    condition_str, values = build_conditions(filters)
    # User.nlsat_portal is a custom field a site may not have yet
    portal_column = "u.nlsat_portal" if frappe.db.has_column("User", "nlsat_portal") else "NULL"

    users = frappe.db.sql(
        f"""
        SELECT u.name, u.email, u.full_name, u.creation, {portal_column} AS portal
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

    applied, enrolled = _application_keys(filters.get("admission_cycle"))
    for u in users:
        keys = {u.email, u.name}
        u.application_status = (
            ENROLLED if keys & enrolled else APPLIED if keys & applied else NOT_APPLIED
        )
    return users


def _application_keys(admission_cycle=None):
    """Emails and user ids found on Applicants (all, and Enrolled ones), optionally of one cycle."""
    A = frappe.qb.DocType("Applicant")
    query = (
        frappe.qb.from_(A)
        .select(A.email, A.user_id, A.status)
        .where((IfNull(A.email, "") != "") | (IfNull(A.user_id, "") != ""))
    )
    if admission_cycle:
        query = query.where(A.admission_cycle == admission_cycle)

    applied, enrolled = set(), set()
    for email, user_id, status in query.run():
        keys = {k for k in (email, user_id) if k}
        applied |= keys
        if status == ENROLLED:
            enrolled |= keys
    return applied, enrolled


def get_data(filters):
    rows = [
        frappe._dict(
            user_id=u.email,
            full_name=u.full_name,
            # The NLSAT Portal filter counts a blank portal as Domestic
            portal=u.portal or "Not set",
            created_on=u.creation,
            application_status=u.application_status,
        )
        for u in get_registered_users(filters)
    ]

    case = filters.get("case")
    if case == "With Application":
        rows = [r for r in rows if r.application_status == APPLIED]
    elif case == "Without Application":
        rows = [r for r in rows if r.application_status == NOT_APPLIED]
    elif case == "Enrolled":
        rows = [r for r in rows if r.application_status == ENROLLED]
    elif case == "Any Application":
        rows = [r for r in rows if r.application_status != NOT_APPLIED]

    return rows


def get_report_summary(filters):
    counts = get_registration_counts(filters)
    return [
        {"value": counts["total"], "label": "Total Registered (Applicant)", "datatype": "Int", "indicator": "blue"},
        {"value": counts["applied"], "label": "Registered & Applied", "datatype": "Int", "indicator": "green"},
        {"value": counts["enrolled"], "label": "Enrolled", "datatype": "Int", "indicator": "green"},
        {"value": counts["not_applied"], "label": "Registered & Not Applied", "datatype": "Int", "indicator": "red"},
    ]


def get_registration_counts(filters):
    """Applicant accounts registered in the period, by what they did next."""
    keys = ("from_date", "to_date", "admission_cycle", "nlsat_portal")
    # Only counted, so skip sorting every user by name.
    rows = get_registered_users({k: filters.get(k) for k in keys}, sort=False)

    total = len(rows)
    enrolled = len([r for r in rows if r.application_status == ENROLLED])
    applied = len([r for r in rows if r.application_status == APPLIED])
    not_applied = len([r for r in rows if r.application_status == NOT_APPLIED])

    return {"total": total, "applied": applied, "enrolled": enrolled, "not_applied": not_applied}

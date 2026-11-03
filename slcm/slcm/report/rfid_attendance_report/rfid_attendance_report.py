# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""
RFID Attendance Report
======================
Two-level table:
  Summary row: Period totals across ALL terminals
  Detail rows: Breakdown by terminal + area

Columns:
  Period | [Weekday] | Terminal/Room | Area | Total Swipes
  Unique Students | Known Students | Unknown Swipes
  Student ID | Student Name | Programme | Academic Year
  Period First Swipe | Period Last Swipe

Number Cards: Total Swipes | Unique Students | Terminals Active |
              Unknown Swipes | Cards Assigned | No Card Assigned Yet

Chart: Stacked bar — Known Students (navy) + Unknown Swipes (maroon)
"""

import frappe
from frappe import _
from frappe.utils import getdate
import calendar as _calendar
import json as _json


# ── Filter options API ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_filter_options(filter_name, txt=""):
    frappe.only_for("System Manager")
    txt = (txt or "").strip().lower()

    if filter_name == "academic_year":
        rows = frappe.db.sql("""
            SELECT DISTINCT academic_year AS val
            FROM `tabStudent Master`
            WHERE academic_year IS NOT NULL AND academic_year != ''
            ORDER BY academic_year DESC
        """, as_list=True)

    elif filter_name == "programme":
        rows = frappe.db.sql("""
            SELECT DISTINCT programme_of_study AS val
            FROM `tabStudent Master`
            WHERE programme_of_study IS NOT NULL AND programme_of_study != ''
            ORDER BY programme_of_study ASC
        """, as_list=True)

    elif filter_name == "terminal_alias":
        rows = frappe.db.sql("""
            SELECT DISTINCT terminal_alias AS val
            FROM `tabAttendance Log`
            WHERE terminal_alias IS NOT NULL AND terminal_alias != ''
            ORDER BY terminal_alias ASC
        """, as_list=True)

    elif filter_name == "area_alias":
        rows = frappe.db.sql("""
            SELECT DISTINCT location AS val
            FROM `tabAttendance Log`
            WHERE location IS NOT NULL AND location != ''
            ORDER BY location ASC
        """, as_list=True)

    elif filter_name == "student":
        rows = frappe.db.sql("""
            SELECT DISTINCT al.student AS val, sm.first_name AS lbl
            FROM `tabAttendance Log` al
            INNER JOIN `tabStudent Master` sm ON sm.name = al.student
            WHERE al.student IS NOT NULL AND al.student != ''
            ORDER BY sm.first_name ASC
            LIMIT 300
        """, as_list=True)
        results = []
        for r in rows:
            sid, name = r[0], r[1] or r[0]
            if not txt or txt in sid.lower() or txt in name.lower():
                results.append({"label": f"{name}  ({sid})", "value": sid, "description": ""})
        return results

    else:
        return []

    results = []
    for r in rows:
        val = r[0] or ""
        if not txt or txt in val.lower():
            results.append({"label": val, "value": val, "description": ""})
    return results


# ── Entry point ────────────────────────────────────────────────────────────────

def execute(filters=None):
    filters = filters or {}
    _validate(filters)

    columns = _get_columns(filters)
    data    = _get_data(filters)
    summary = _get_summary(filters)
    chart   = _get_chart(data, filters)

    return columns, data, None, chart, summary


# ── Validation ─────────────────────────────────────────────────────────────────

def _validate(filters):
    if filters.get("from_date") and filters.get("to_date"):
        if getdate(filters["from_date"]) > getdate(filters["to_date"]):
            frappe.throw(_("From Date cannot be after To Date."))


# ── Columns ────────────────────────────────────────────────────────────────────

def _get_columns(filters):
    view = filters.get("view_by", "Daily")
    period_label = {"Daily": _("Date"), "Weekly": _("Week"), "Monthly": _("Month")}[view]

    return [
        {"fieldname": "period_label",    "label": period_label,               "fieldtype": "Data",     "width": 185},
        {"fieldname": "terminal_alias",  "label": _("Terminal / Room"),       "fieldtype": "Data",     "width": 165},
        {"fieldname": "area_alias",      "label": _("Area"),                  "fieldtype": "Data",     "width": 130},
        {"fieldname": "total_swipes",    "label": _("Total Swipes"),          "fieldtype": "Int",      "width": 110},
        {"fieldname": "unique_students", "label": _("Unique Students"),       "fieldtype": "Int",      "width": 130},
        {"fieldname": "known_students",  "label": _("Known Students"),        "fieldtype": "Int",      "width": 130},
        {"fieldname": "unknown_swipes",  "label": _("Unknown Swipes"),        "fieldtype": "Int",      "width": 130},
        {"fieldname": "student",         "label": _("Student ID"),            "fieldtype": "Link",
         "options": "Student Master",                                                                   "width": 145},
        {"fieldname": "student_name",    "label": _("Student Name"),          "fieldtype": "Data",     "width": 175},
        {"fieldname": "programme",       "label": _("Programme"),             "fieldtype": "Data",     "width": 230},
        {"fieldname": "academic_year",   "label": _("Academic Year"),         "fieldtype": "Data",     "width": 120},
        {"fieldname": "first_swipe",     "label": _("First Swipe (Period)"),  "fieldtype": "Datetime", "width": 175},
        {"fieldname": "last_swipe",      "label": _("Last Swipe (Period)"),   "fieldtype": "Datetime", "width": 175},
    ]


# ── WHERE builder ──────────────────────────────────────────────────────────────

def _parse_multiselect(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return [v for v in raw if v]
    if isinstance(raw, str):
        raw = raw.strip()
        if raw.startswith("["):
            try:
                return [v for v in _json.loads(raw) if v]
            except Exception:
                pass
        return [v.strip() for v in raw.split(",") if v.strip()]
    return []


def _build_where(filters):
    from_date = filters.get("from_date")
    to_date   = filters.get("to_date")

    conditions = [
        "al.swipe_time >= %(from_dt)s",
        "al.swipe_time <= %(to_dt)s",
    ]
    params = {
        "from_dt": f"{from_date} 00:00:00",
        "to_dt":   f"{to_date} 23:59:59",
    }

    def _add_in(field_expr, values, key_prefix):
        ph = ", ".join([f"%({key_prefix}_{i})s" for i in range(len(values))])
        conditions.append(f"{field_expr} IN ({ph})")
        for i, v in enumerate(values):
            params[f"{key_prefix}_{i}"] = v

    terminals  = _parse_multiselect(filters.get("terminal_alias"))
    areas      = _parse_multiselect(filters.get("area_alias"))
    students   = _parse_multiselect(filters.get("student"))
    acad_years = _parse_multiselect(filters.get("academic_year"))
    programmes = _parse_multiselect(filters.get("programme"))

    if terminals:  _add_in("al.terminal_alias", terminals,  "t")
    if areas:      _add_in("al.location",        areas,      "a")
    if students:   _add_in("al.student",         students,   "s")
    if acad_years: _add_in("sm.academic_year",   acad_years, "y")
    if programmes: _add_in("sm.programme_of_study",        programmes, "p")

    if filters.get("known_only"):
        conditions.append("(al.student IS NOT NULL AND al.student != '')")

    return conditions, params


# ── Data — two-level hierarchy ─────────────────────────────────────────────────

def _get_data(filters):
    view = filters.get("view_by", "Daily")
    conditions, params = _build_where(filters)
    where = " AND ".join(conditions)

    period_expr = {
        "Daily":   "DATE(al.swipe_time)",
        "Weekly":  "YEARWEEK(al.swipe_time, 3)",
        "Monthly": "DATE_FORMAT(al.swipe_time, '%%Y-%%m')",
    }[view]

    # ── Detail rows: grouped by period + terminal + area ───────────────────────
    detail_sql = f"""
        SELECT
            {period_expr}                                           AS period_key,
            COALESCE(al.terminal_alias, 'Unknown Terminal')         AS terminal_alias,
            COALESCE(al.location,       'Unknown Area')             AS area_alias,
            COUNT(*)                                                 AS total_swipes,
            COUNT(DISTINCT CASE
                WHEN al.student IS NOT NULL AND al.student != ''
                THEN al.student END)                                 AS unique_students,
            COUNT(DISTINCT CASE
                WHEN al.student IS NOT NULL AND al.student != ''
                THEN al.student END)                                 AS known_students,
            SUM(CASE
                WHEN al.student IS NULL OR al.student = ''
                THEN 1 ELSE 0 END)                                   AS unknown_swipes,
            MAX(CASE
                WHEN al.student IS NOT NULL AND al.student != ''
                THEN al.student END)                                 AS student,
            MAX(CASE
                WHEN al.student IS NOT NULL AND al.student != ''
                THEN sm.first_name END)                              AS student_name,
            MAX(sm.programme_of_study)                                        AS programme,
            MAX(sm.academic_year)                                    AS academic_year,
            MIN(al.swipe_time)                                       AS first_swipe,
            MAX(al.swipe_time)                                       AS last_swipe
        FROM `tabAttendance Log` al
        LEFT JOIN `tabStudent Master` sm ON sm.name = al.student
        WHERE {where}
        GROUP BY period_key, al.terminal_alias, al.location
        ORDER BY period_key ASC, total_swipes DESC
    """
    detail_rows = frappe.db.sql(detail_sql, params, as_dict=True)

    # ── True unique-student counts per period (avoids double-counting
    #    students who swipe at multiple terminals in the same period) ────────────
    unique_sql = f"""
        SELECT
            {period_expr}                                        AS period_key,
            COUNT(DISTINCT CASE
                WHEN al.student IS NOT NULL AND al.student != ''
                THEN al.student END)                             AS unique_students
        FROM `tabAttendance Log` al
        LEFT JOIN `tabStudent Master` sm ON sm.name = al.student
        WHERE {where}
        GROUP BY period_key
    """
    unique_by_period = {
        str(r.period_key): int(r.unique_students or 0)
        for r in frappe.db.sql(unique_sql, params, as_dict=True)
    }

    # ── Group detail rows by period to build summary rows ──────────────────────
    from collections import OrderedDict
    period_groups = OrderedDict()  # period_key → [detail_row, ...]

    for r in detail_rows:
        key = str(r.period_key)
        if key not in period_groups:
            period_groups[key] = []
        period_groups[key].append(r)

    # ── Build flat list: summary row then its detail rows ─────────────────────
    data = []

    for period_key, rows in period_groups.items():
        label = _period_label(period_key, view)
        # For Daily view, embed the weekday name inside the date label
        if view == "Daily":
            label = f"{label}  ({_weekday_name(period_key)})"

        # Summary aggregates — use true period-level unique student count
        sum_swipes    = sum(r.total_swipes    or 0 for r in rows)
        sum_unique    = unique_by_period.get(period_key, 0)
        sum_known     = sum_unique  # known = students identified by RFID
        sum_unknown   = sum(r.unknown_swipes  or 0 for r in rows)
        period_first  = min((r.first_swipe for r in rows if r.first_swipe), default=None)
        period_last   = max((r.last_swipe  for r in rows if r.last_swipe),  default=None)

        # ── Summary row ───────────────────────────────────────────────────────────
        data.append({
            "period_label":    label,
            "terminal_alias":  f"All terminals  ({len(rows)})",
            "area_alias":      "",
            "total_swipes":    sum_swipes,
            "unique_students": sum_unique,
            "known_students":  sum_known,
            "unknown_swipes":  sum_unknown,
            "student":         "",
            "student_name":    "",
            "programme":       "",
            "academic_year":   "",
            "first_swipe":     period_first,
            "last_swipe":      period_last,
        })

        # ── Detail rows ────────────────────────────────────────────────────────
        for r in rows:
            data.append({
                "period_label":    "",
                "terminal_alias":  r.terminal_alias,
                "area_alias":      r.area_alias,
                "total_swipes":    int(r.total_swipes    or 0),
                "unique_students": int(r.unique_students or 0),
                "known_students":  int(r.known_students  or 0),
                "unknown_swipes":  int(r.unknown_swipes  or 0),
                "student":         r.student       or "",
                "student_name":    r.student_name  or "",
                "programme":       r.programme     or "",
                "academic_year":   r.academic_year or "",
                "first_swipe":     r.first_swipe,
                "last_swipe":      r.last_swipe,
            })

    return data


# ── Summary cards ──────────────────────────────────────────────────────────────

def _get_summary(filters):
    conditions, params = _build_where(filters)
    where = " AND ".join(conditions)

    agg = frappe.db.sql(f"""
        SELECT
            COUNT(*)                                                    AS total_swipes,
            COUNT(DISTINCT CASE
                WHEN al.student IS NOT NULL AND al.student != ''
                THEN al.student END)                                    AS unique_known,
            COUNT(DISTINCT al.terminal_alias)                           AS terminals,
            SUM(CASE
                WHEN al.student IS NULL OR al.student = ''
                THEN 1 ELSE 0 END)                                      AS unknown_swipes
        FROM `tabAttendance Log` al
        LEFT JOIN `tabStudent Master` sm ON sm.name = al.student
        WHERE {where}
    """, params, as_dict=True)[0]

    total_students = frappe.db.count("Student Master") or 1
    cards_assigned = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabStudent Master` "
        "WHERE rfid_uid IS NOT NULL AND rfid_uid != ''",
        as_list=True
    )[0][0]

    return [
        {"label": _("Total Swipes"),        "value": int(agg.total_swipes  or 0), "datatype": "Int", "indicator": "blue"},
        {"label": _("Unique Students"),     "value": int(agg.unique_known  or 0), "datatype": "Int", "indicator": "green"},
        {"label": _("Terminals Active"),    "value": int(agg.terminals     or 0), "datatype": "Int", "indicator": "blue"},
        {"label": _("Unknown Swipes"),      "value": int(agg.unknown_swipes or 0),"datatype": "Int", "indicator": "red"},
        {"label": _("Cards Assigned"),      "value": int(cards_assigned),          "datatype": "Int", "indicator": "green"},
        {"label": _("No Card Assigned Yet"),"value": int(total_students - cards_assigned), "datatype": "Int", "indicator": "orange"},
    ]


# ── Chart ──────────────────────────────────────────────────────────────────────

def _get_chart(data, filters):
    # Use only summary rows (bold=1) for the chart
    period_known   = {}
    period_unknown = {}

    for row in data:
        if not str(row.get("terminal_alias", "")).startswith("All terminals"):
            continue
        lbl = row["period_label"]
        period_known[lbl]   = period_known.get(lbl, 0)   + (row["known_students"] or 0)
        period_unknown[lbl] = period_unknown.get(lbl, 0) + (row["unknown_swipes"] or 0)

    labels = list(period_known.keys())
    if not labels:
        return None
    if len(labels) > 31:
        labels = labels[-31:]

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": _("Known Students"), "values": [period_known.get(l, 0)   for l in labels], "chartType": "bar"},
                {"name": _("Unknown Swipes"), "values": [period_unknown.get(l, 0) for l in labels], "chartType": "bar"},
            ],
        },
        "type":       "bar",
        "colors":     ["#2b2e4a", "#8b1a1a"],
        "barOptions": {"stacked": True},
        "title":      _("Swipe Activity — ") + filters.get("view_by", "Daily"),
        "height":     280,
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _weekday_name(date_str):
    try:
        return _WEEKDAYS[getdate(date_str).weekday()]
    except Exception:
        return ""


def _period_label(key, view):
    if view == "Daily":
        return key
    if view == "Weekly":
        return _week_label(key)
    # Monthly: YYYY-MM → Month YYYY
    parts = key.split("-")
    return f"{_calendar.month_name[int(parts[1])]} {parts[0]}"


def _week_label(yearweek_str):
    try:
        import datetime
        yw   = str(yearweek_str)
        year = int(yw[:4])
        week = int(yw[4:])
        monday = datetime.datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u").date()
        sunday = monday + datetime.timedelta(days=6)
        return f"Wk {week}, {year}  ({monday.strftime('%d %b')}–{sunday.strftime('%d %b')})"
    except Exception:
        return str(yearweek_str)

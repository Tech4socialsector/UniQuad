# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt


import frappe
from frappe import _

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data, chart, report_summary = get_data(filters)
    message = _("This Reservation Report displays category-wise candidate counts for applicants who have passed Part A (Entrance Test).")
    return columns, data, message, chart, report_summary

def get_columns():
    return [
        {
            "label": _("Category Type"),
            "fieldname": "category_type",
            "fieldtype": "Data",
            "width": 260
        },
        {
            "label": _("Category / Combination"),
            "fieldname": "category_name",
            "fieldtype": "Data",
            "width": 320
        },
        {
            "label": _("Passed Students Count"),
            "fieldname": "student_count",
            "fieldtype": "Int",
            "width": 180
        }
    ]

def get_data(filters):
    # Fetch categories dynamically from database
    categories = frappe.get_all("Admission Category", fields=["name", "reservation_type"])
    
    vertical_list = [c.name for c in categories if c.reservation_type == "Vertical"]
    horizontal_list = [c.name for c in categories if c.reservation_type == "Horizontal"]
    compartmental_list = [c.name for c in categories if c.reservation_type == "Compartmentalised Horizontal"]

    # Fallback to standard categories if DB has none
    if not vertical_list:
        vertical_list = ["General", "SC", "ST", "OBC-NCL", "EWS"]
    if not horizontal_list:
        horizontal_list = ["PWD", "Women"]
    if not compartmental_list:
        compartmental_list = ["Karnataka"]

    # Ensure "General" is in vertical_list and is first
    if "General" in vertical_list:
        vertical_list.remove("General")
    vertical_list.insert(0, "General")

    # 1. Fetch passed students matching filters
    conditions = ["etsa.result_status = 'Pass'"]
    params = {}

    if filters.get("academic_year"):
        conditions.append("etsa.academic_year = %(academic_year)s")
        params["academic_year"] = filters.get("academic_year")

    if filters.get("admission_cycle"):
        conditions.append("etsa.admission_cycle = %(admission_cycle)s")
        params["admission_cycle"] = filters.get("admission_cycle")

    if filters.get("campus"):
        conditions.append("etsa.campus = %(campus)s")
        params["campus"] = filters.get("campus")

    if filters.get("program"):
        conditions.append("etsa.program = %(program)s")
        params["program"] = filters.get("program")

    where_clause = " WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            app.name as applicant_id,
            app.candidate_name,
            app.gender,
            app.whether_scstobc_ncl,
            app.pwd,
            app.karnataka_category
        FROM
            `tabEntrance Test Seat Allocation` etsa
        INNER JOIN
            `tabApplicant` app ON etsa.applicant = app.name
        {where_clause}
    """
    
    applicants = frappe.db.sql(sql, params, as_dict=True)

    # 2. Categorization helper
    def get_vertical_category(r):
        sc_st_obc = (r.whether_scstobc_ncl or "").strip()
        if sc_st_obc and sc_st_obc in vertical_list:
            return sc_st_obc
        return "General"

    # Initialize counter mappings
    counts = {
        "vertical": {vc: 0 for vc in vertical_list},
        "horizontal": {hc: 0 for hc in horizontal_list},
        "compartmentalized": {cc: 0 for cc in compartmental_list},
        "vertical_horizontal": {},
        "vertical_horizontal_compartmentalized": {},
        "vertical_compartmentalized": {}
    }

    # Pre-populate all combinations for uniform display
    for vc in vertical_list:
        for hc in horizontal_list:
            counts["vertical_horizontal"][(vc, hc)] = 0
            for cc in compartmental_list:
                counts["vertical_horizontal_compartmentalized"][(vc, hc, cc)] = 0
        for cc in compartmental_list:
            counts["vertical_compartmentalized"][(vc, cc)] = 0

    # Aggregate counts from passed applicants
    for r in applicants:
        v_cat = get_vertical_category(r)
        
        # Vertical count
        if v_cat in counts["vertical"]:
            counts["vertical"][v_cat] += 1

        # Horizontal checks
        is_pwd = (r.pwd or "").strip() == "Yes"
        is_women = r.gender == "Female"
        
        active_h_cats = []
        if is_pwd and "PWD" in counts["horizontal"]:
            counts["horizontal"]["PWD"] += 1
            active_h_cats.append("PWD")
        if is_women and "Women" in counts["horizontal"]:
            counts["horizontal"]["Women"] += 1
            active_h_cats.append("Women")

        # Compartmentalized checks
        is_karnataka = (r.karnataka_category or "").strip() == "Yes"
        active_c_cats = []
        if is_karnataka and "Karnataka" in counts["compartmentalized"]:
            counts["compartmentalized"]["Karnataka"] += 1
            active_c_cats.append("Karnataka")

        # Vertical + Horizontal counts
        for hc in active_h_cats:
            counts["vertical_horizontal"][(v_cat, hc)] += 1

        # Vertical + Compartmentalized counts
        for cc in active_c_cats:
            counts["vertical_compartmentalized"][(v_cat, cc)] += 1

        # Vertical + Horizontal + Compartmentalized counts
        for hc in active_h_cats:
            for cc in active_c_cats:
                counts["vertical_horizontal_compartmentalized"][(v_cat, hc, cc)] += 1

    # 3. Construct data rows organized by sections
    data = []

    # Section 1: Vertical Categories
    for vc in vertical_list:
        data.append({
            "category_type": _("1. Vertical Category"),
            "category_name": vc,
            "student_count": counts["vertical"][vc]
        })

    # Section 2: Horizontal Categories
    for hc in horizontal_list:
        data.append({
            "category_type": _("2. Horizontal Category"),
            "category_name": hc,
            "student_count": counts["horizontal"][hc]
        })

    # Section 3: Compartmentalized Categories
    for cc in compartmental_list:
        data.append({
            "category_type": _("3. Compartmentalized Category"),
            "category_name": cc,
            "student_count": counts["compartmentalized"][cc]
        })

    # Section 4: Vertical + Horizontal
    for vc in vertical_list:
        for hc in horizontal_list:
            data.append({
                "category_type": _("4. Vertical + Horizontal"),
                "category_name": f"{vc} + {hc}",
                "student_count": counts["vertical_horizontal"][(vc, hc)]
            })

    # Section 5: Vertical + Compartmentalized
    for vc in vertical_list:
        for cc in compartmental_list:
            data.append({
                "category_type": _("5. Vertical + Compartmentalized"),
                "category_name": f"{vc} + {cc}",
                "student_count": counts["vertical_compartmentalized"][(vc, cc)]
            })

    # Section 6: Vertical + Horizontal + Compartmentalized
    for vc in vertical_list:
        for hc in horizontal_list:
            for cc in compartmental_list:
                data.append({
                    "category_type": _("6. Vertical + Horizontal + Compartmentalized"),
                    "category_name": f"{vc} + {hc} + {cc}",
                    "student_count": counts["vertical_horizontal_compartmentalized"][(vc, hc, cc)]
                })

    # 4. Generate visual elements (chart & summary cards)
    total_passed = len(applicants)
    general_count = counts["vertical"].get("General", 0)
    reserved_count = total_passed - general_count
    karnataka_count = counts["compartmentalized"].get("Karnataka", 0)

    report_summary = [
        {"value": total_passed, "label": _("Total Passed Students"), "indicator": "Green", "datatype": "Int"},
        {"value": general_count, "label": _("General Category"), "indicator": "Blue", "datatype": "Int"},
        {"value": reserved_count, "label": _("Reserved Categories"), "indicator": "Orange", "datatype": "Int"},
        {"value": karnataka_count, "label": _("Karnataka Category"), "indicator": "Purple", "datatype": "Int"}
    ]

    chart = {
        "data": {
            "labels": vertical_list,
            "datasets": [
                {
                    "name": _("Students Count"),
                    "values": [counts["vertical"][vc] for vc in vertical_list]
                }
            ]
        },
        "type": "bar",
        "colors": ["#1fb5ad", "#ffa00a", "#ff5858", "#9b59b6", "#34495e"]
    }

    return data, chart, report_summary

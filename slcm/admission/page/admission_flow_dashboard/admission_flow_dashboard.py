import frappe
import json
from frappe import _
from frappe.utils import flt, getdate, add_days, today

@frappe.whitelist()
def get_dashboard_data(filters=None):
    if isinstance(filters, str):
        filters = json.loads(filters)
    
    if not filters:
        filters = {}

    query_filters = []
    if filters.get("admission_year"):
        query_filters.append(f"admission_year = {frappe.db.escape(filters.get('admission_year'))}")
    if filters.get("admission_cycle"):
        query_filters.append(f"admission_cycle = {frappe.db.escape(filters.get('admission_cycle'))}")
    if filters.get("campus"):
        query_filters.append(f"campus = {frappe.db.escape(filters.get('campus'))}")
    if filters.get("program"):
        query_filters.append(f"program = {frappe.db.escape(filters.get('program'))}")
    if filters.get("whether_scstobc_ncl"):
        query_filters.append(f"whether_scstobc_ncl = {frappe.db.escape(filters.get('whether_scstobc_ncl'))}")
    
    if filters.get("date_range"):
        date_range = filters.get("date_range")
        if isinstance(date_range, str):
             date_range = json.loads(date_range)
        if len(date_range) == 2:
            query_filters.append(f"creation >= {frappe.db.escape(date_range[0])}")
            query_filters.append(f"creation <= {frappe.db.escape(date_range[1] + ' 23:59:59')}")

    where_clause = " WHERE docstatus < 2 " # Exclude cancelled
    if query_filters:
        where_clause += " AND " + " AND ".join(query_filters)

    # 1. Summary Cards
    summary = get_summary_cards(where_clause)

    # 2. Funnel Data
    funnel = get_funnel_data(where_clause)

    # 3. Distribution by Campus
    campus_dist = get_distribution(where_clause, "campus")

    # 4. Distribution by Program
    program_dist = get_distribution(where_clause, "program")

    # 5. Application Trend (Last 30 days)
    trend = get_application_trend(where_clause)
    
    # 6. Category wise
    category_dist = get_distribution(where_clause, "whether_scstobc_ncl")

    # 7. Gender Distribution
    gender_dist = get_distribution(where_clause, "gender")

    # 8. Geographic Distribution (State)
    state_dist = get_distribution(where_clause, "state")

    # 9. Offer Status Breakdown
    offer_breakdown = get_offer_status_breakdown(where_clause)

    # 10. Fee Payment Status
    fee_payment_dist = get_fee_payment_status(where_clause)

    # 11. Yield Metrics
    yield_metrics = get_yield_metrics(summary)

    return {
        "summary": summary,
        "funnel": funnel,
        "campus_dist": campus_dist,
        "program_dist": program_dist,
        "trend": trend,
        "category_dist": category_dist,
        "gender_dist": gender_dist,
        "state_dist": state_dist,
        "offer_breakdown": offer_breakdown,
        "fee_payment_dist": fee_payment_dist,
        "yield_metrics": yield_metrics
    }

def get_summary_cards(where_clause):
    sql = f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status NOT IN ('Draft') THEN 1 ELSE 0 END) as submitted,
            SUM(CASE WHEN status IN ('Selected', 'Offer Issued', 'Offer Accepted', 'Confirmation Fee Paid', 'Full Fee Paid', 'Accepted') THEN 1 ELSE 0 END) as selected,
            SUM(CASE WHEN status = 'Waitlisted' THEN 1 ELSE 0 END) as waitlisted,
            SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END) as rejected,
            SUM(CASE WHEN status IN ('Confirmation Fee Paid', 'Full Fee Paid') THEN 1 ELSE 0 END) as enrolled
        FROM `tabApplicant`
        {where_clause}
    """
    res = frappe.db.sql(sql, as_dict=1)[0]
    
    # Get Total Offers Issued (cumulative)
    sql_offers = f"""
        SELECT COUNT(*) FROM `tabApplicant` 
        {where_clause} AND status IN ('Offer Issued', 'Offer Accepted', 'Offer Declined', 'Offer Expired', 'Confirmation Fee Paid', 'Full Fee Paid')
    """
    offers_count = frappe.db.sql(sql_offers)[0][0]
    
    return {
        "total": res.total or 0,
        "submitted": res.submitted or 0,
        "selected": res.selected or 0,
        "waitlisted": res.waitlisted or 0,
        "rejected": res.rejected or 0,
        "enrolled": res.enrolled or 0,
        "offers": offers_count or 0
    }

def get_funnel_data(where_clause):
    # Stages for funnel
    stages = [
        {"label": "Submitted", "statuses": ["Submitted", "Submitted and Paid", "Selected", "Waitlisted", "Rejected", "Offer Accepted", "Offer Issued", "Offer Declined", "Offer Expired", "Confirmation Fee Paid", "Full Fee Paid", "Accepted"]},
        {"label": "Selected", "statuses": ["Selected", "Offer Issued", "Offer Accepted", "Offer Declined", "Offer Expired", "Confirmation Fee Paid", "Full Fee Paid", "Accepted"]},
        {"label": "Offer Issued", "statuses": ["Offer Issued", "Offer Accepted", "Offer Declined", "Offer Expired", "Confirmation Fee Paid", "Full Fee Paid"]},
        {"label": "Offer Accepted", "statuses": ["Offer Accepted", "Confirmation Fee Paid", "Full Fee Paid", "Accepted"]},
        {"label": "Confirmation Fee Paid", "statuses": ["Confirmation Fee Paid", "Full Fee Paid"]}
    ]
    
    data = []
    for stage in stages:
        status_list = ",".join([f"'{s}'" for s in stage["statuses"]])
        count_sql = f"SELECT COUNT(*) FROM `tabApplicant` {where_clause} AND status IN ({status_list})"
        count = frappe.db.sql(count_sql)[0][0]
        data.append({"label": stage["label"], "count": count})
    
    return data

def get_distribution(where_clause, field):
    sql = f"""
        SELECT IFNULL({field}, 'Not Specified') as label, COUNT(*) as count
        FROM `tabApplicant`
        {where_clause}
        GROUP BY {field}
        ORDER BY count DESC
        LIMIT 10
    """
    return frappe.db.sql(sql, as_dict=1)

def get_application_trend(where_clause):
    # Last 30 days trend
    date_limit = add_days(today(), -30)
    sql = f"""
        SELECT DATE(creation) as date, COUNT(*) as count
        FROM `tabApplicant`
        {where_clause} AND creation >= '{date_limit}'
        GROUP BY DATE(creation)
        ORDER BY date ASC
    """
    return frappe.db.sql(sql, as_dict=1)

def get_offer_status_breakdown(where_clause):
    sql = f"""
        SELECT 
            CASE 
                WHEN status = 'Offer Issued' THEN 'Pending Action'
                WHEN status IN ('Offer Accepted', 'Confirmation Fee Paid', 'Full Fee Paid', 'Accepted') THEN 'Accepted'
                WHEN status = 'Offer Declined' THEN 'Declined'
                WHEN status = 'Offer Expired' THEN 'Expired'
                ELSE 'Other'
            END as label,
            COUNT(*) as count
        FROM `tabApplicant`
        {where_clause} AND status IN ('Offer Issued', 'Offer Accepted', 'Offer Declined', 'Offer Expired', 'Confirmation Fee Paid', 'Full Fee Paid', 'Accepted')
        GROUP BY label
    """
    return frappe.db.sql(sql, as_dict=1)

def get_fee_payment_status(where_clause):
    # Join with Applicant to apply same filters (campus, cycle, year, etc.)
    sql = f"""
        SELECT 
            afa.status as label,
            COUNT(*) as count
        FROM `tabApplicant Fee Assignment` afa
        JOIN `tabApplicant` app ON afa.applicant = app.name
        {where_clause.replace('WHERE', 'WHERE afa.docstatus < 2 AND ')}
        GROUP BY label
        ORDER BY count DESC
    """
    # Note: where_clause already has 'WHERE docstatus < 2'. 
    # If where_clause has 'WHERE docstatus < 2 AND ...', replace 'WHERE' with 'WHERE afa.docstatus < 2 AND' 
    # is a bit tricky if it's already there.
    
    # Let's be safer with the replacement:
    final_where = where_clause.replace('admission_year', 'app.admission_year')\
                              .replace('admission_cycle', 'app.admission_cycle')\
                              .replace('campus', 'app.campus')\
                              .replace('program', 'app.program')\
                              .replace('whether_scstobc_ncl', 'app.whether_scstobc_ncl')\
                              .replace('gender', 'app.gender')\
                              .replace('state', 'app.state')\
                              .replace('creation', 'app.creation')\
                              .replace('docstatus', 'app.docstatus')

    sql = f"""
        SELECT 
            afa.status as label,
            COUNT(*) as count
        FROM `tabApplicant Fee Assignment` afa
        JOIN `tabApplicant` app ON afa.applicant = app.name
        {final_where}
        GROUP BY label
        ORDER BY count DESC
    """
    return frappe.db.sql(sql, as_dict=1)

def get_yield_metrics(summary):
    offers = summary.get("offers", 0)
    enrolled = summary.get("enrolled", 0)
    selected = summary.get("selected", 0)
    
    yield_rate = (enrolled / offers * 100) if offers > 0 else 0
    acceptance_rate = (enrolled / selected * 100) if selected > 0 else 0
    
    return {
        "yield_rate": round(yield_rate, 1),
        "acceptance_rate": round(acceptance_rate, 1)
    }

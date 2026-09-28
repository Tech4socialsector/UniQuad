import frappe
from frappe import _
from frappe.utils import flt, getdate, formatdate

def execute(filters=None):
    if not filters:
        filters = {}
        
    export_mode = filters.get("export_mode", "Student Level")
    if export_mode == "Grouped":
        columns = get_grouped_columns()
    else:
        columns = get_columns()
        
    data, warnings = get_data(filters)
    
    if export_mode == "Grouped":
        data = group_data(data)
        
    # Apply blank zeros
    for r in data:
        if "debit" in r and r["debit"] == 0:
            r["debit"] = None
        if "credit" in r and r["credit"] == 0:
            r["credit"] = None
            
    # Format message for warnings
    msg = ""
    if warnings:
        warn_text = "<br>".join([f"Ref: {w['reference_number']} | Student: {w['student']} | Reason: {w['reason']}" for w in warnings[:20]])
        msg = f"<div style='color: orange'><b>{len(warnings)} Warnings (Showing first 20)</b><br>{warn_text}</div>"
        
    return columns, data, msg

def get_columns():
    return [
        {"fieldname": "journal_date", "label": _("Journal Date (DD-MM-YYYY)"), "fieldtype": "Data", "width": 120},
        {"fieldname": "settlement_date", "label": _("Settlement Date (DD-MM-YYYY)"), "fieldtype": "Data", "width": 120},
        {"fieldname": "reference_number", "label": _("Reference Number"), "fieldtype": "Data", "width": 150},
        {"fieldname": "journal_number_prefix", "label": _("Journal Number Prefix"), "fieldtype": "Data", "width": 150},
        {"fieldname": "journal_number_suffix", "label": _("Journal Number Suffix"), "fieldtype": "Data", "width": 150},
        {"fieldname": "notes", "label": _("Notes"), "fieldtype": "Data", "width": 200},
        {"fieldname": "journal_type", "label": _("Journal Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Data", "width": 80},
        {"fieldname": "account", "label": _("Account"), "fieldtype": "Data", "width": 150},
        {"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 150},
        {"fieldname": "contact_name", "label": _("Contact Name"), "fieldtype": "Data", "width": 120},
        {"fieldname": "debit", "label": _("Debit"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "credit", "label": _("Credit"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Data", "width": 180},
        {"fieldname": "course", "label": _("Course"), "fieldtype": "Data", "width": 120},
        {"fieldname": "student_id", "label": _("Student ID"), "fieldtype": "Data", "width": 120},
        {"fieldname": "student_name", "label": _("Student Name"), "fieldtype": "Data", "width": 150},
    ]

def get_grouped_columns():
    cols = get_columns()
    return [c for c in cols if c["fieldname"] not in ("student_id", "student_name")]

def get_razorpay_settlements(filters):
    from datetime import datetime, timezone
    
    start_ts = None
    end_ts = None
    if filters.get("from_settlement_date"):
        start_ts = int(datetime.combine(getdate(filters.get("from_settlement_date")), datetime.min.time()).replace(tzinfo=timezone.utc).timestamp())
    if filters.get("to_settlement_date"):
        end_ts = int(datetime.combine(getdate(filters.get("to_settlement_date")), datetime.max.time()).replace(tzinfo=timezone.utc).timestamp())
        
    if getattr(frappe.conf, "developer_mode", False) and frappe.conf.get("zoho_report_mock_path"):
        import json
        with open(frappe.conf.get("zoho_report_mock_path"), "r") as f:
            mock_data = json.load(f)
            
        settlements = []
        for s in mock_data.get("settlements", []):
            s_ts = s.get("settlement_time") or s.get("created_at")
            if start_ts and s_ts < start_ts: continue
            if end_ts and s_ts > end_ts: continue
            settlements.append(s)
            
        return settlements, mock_data.get("recon_items", [])
        
    if filters.get("mock_settlements_json") and getattr(frappe.conf, "developer_mode", False):
        import json
        with open(filters.get("mock_settlements_json"), "r") as f:
            mock_data = json.load(f)
        return mock_data.get("settlements", []), mock_data.get("recon_items", [])
    
    settings = frappe.get_doc("Razorpay Settings", "Razorpay Settings")
    
    import requests
    from requests.auth import HTTPBasicAuth
    
    settlements = []
    recon_items = []
    
    url = "https://api.razorpay.com/v1/settlements"
    params = {"count": 100}
    
    resp = requests.get(url, params=params, auth=HTTPBasicAuth(settings.api_key, settings.get_password("api_secret")))
    if resp.status_code == 200:
        settlements_data = resp.json().get("items", [])
        
        for s in settlements_data:
            s_ts = s.get("settlement_time") or s.get("created_at")
            
            if start_ts and s_ts < start_ts: continue
            if end_ts and s_ts > end_ts: continue
            
            settlements.append(s)
            
            recon_url = "https://api.razorpay.com/v1/settlements/recon/combined"
            r_resp = requests.post(recon_url, json={"settlement_id": s["id"]}, auth=HTTPBasicAuth(settings.api_key, settings.get_password("api_secret")))
            if r_resp.status_code == 200:
                recon_items.extend(r_resp.json().get("items", []))
                
    return settlements, recon_items

def _preload_course_resolution(fp_list):
    pm_list = frappe.db.get_all("Programme Master", fields=["name", "zoho_course"])
    zoho_course_map = {pm.name: pm.zoho_course for pm in pm_list if pm.zoho_course}
    
    prog_names = {fp.program for fp in fp_list if fp.program}
    student_names = {fp.student for fp in fp_list if fp.student}
    
    prog_map = {}
    if prog_names:
        progs = frappe.db.get_all("Programme", filters={"name": ("in", list(prog_names))}, fields=["name", "program_name"])
        prog_map = {p.name: p.program_name for p in progs if p.program_name}
        
    student_map = {}
    if student_names:
        students = frappe.db.get_all("Student Master", filters={"name": ("in", list(student_names))}, fields=["name", "master_programme", "programme_of_study"])
        for s in students:
            pos_prog_name = None
            if s.programme_of_study:
                pos_prog_name = frappe.db.get_value("Programme", s.programme_of_study, "program_name")
            student_map[s.name] = {
                "master_programme": s.master_programme,
                "pos_prog_name": pos_prog_name
            }
            
    return zoho_course_map, prog_map, student_map

def resolve_course(fp, zoho_course_map, prog_map, student_map):
    prog_master = prog_map.get(fp.program) if fp.program else None
    
    s_info = student_map.get(fp.student, {})
    if not prog_master:
        prog_master = s_info.get("master_programme")
        
    if not prog_master:
        prog_master = s_info.get("pos_prog_name")
        
    zoho_course = zoho_course_map.get(prog_master) if prog_master else None
    
    return prog_master, zoho_course

def get_data(filters):
    rows = []
    warnings = []
    
    transaction_type = filters.get("transaction_type")
    
    def process_fp_list(fp_list, is_online, s_date_override=None, ref_override=None):
        if not fp_list: return
        
        zoho_course_map, prog_map, student_map = _preload_course_resolution(fp_list)
        
        demand_rows = frappe.db.sql("""
            SELECT fpdr.parent, fpdr.amount_allocated, fd.fee_component, fd.description 
            FROM `tabFee Payment Demand Row` fpdr
            LEFT JOIN `tabFee Demand` fd ON fd.name = fpdr.fee_demand
            WHERE fpdr.parent IN %s
        """, (tuple([f.name for f in fp_list]),), as_dict=True)
        
        demands_map = {}
        for r in demand_rows:
            demands_map.setdefault(r.parent, []).append(r)
        
        comp_names = {r.fee_component for r in demand_rows if r.fee_component}
        comp_ledger = {}
        if comp_names:
            comp_ledger = {c.name: c.ledger for c in frappe.db.get_all("Fee Component", filters={"name": ["in", list(comp_names)]}, fields=["name", "ledger"])}
            
        for fp in fp_list:
            s_date = s_date_override if s_date_override else fp.settlement_date
            date_str = formatdate(s_date, "dd-MM-yyyy") if s_date else ""
            utr = ref_override if ref_override else (fp.reference_number or "")
            bank = fp.university_bank_account or filters.get("bank_account") or "Unknown Bank Account"
            
            prog_master, course = resolve_course(fp, zoho_course_map, prog_map, student_map)
            
            if filters.get("program") and prog_master != filters.get("program"):
                continue
                
            if not course:
                reason = "No Programme found" if not prog_master else f"Programme Master '{prog_master}' has empty zoho_course"
                warnings.append({
                    "reference_number": utr,
                    "student": fp.student,
                    "reason": reason
                })
                course = ""
                
            d_rows = demands_map.get(fp.name, [])
            comp_amounts = {}
            for dr in d_rows:
                c = dr.fee_component or "Unallocated Fee"
                comp_amounts[c] = comp_amounts.get(c, 0) + flt(dr.amount_allocated)
                
            allocated_total = round(sum(comp_amounts.values()), 2)
            amount = round(flt(fp.amount), 2)
            rem = round(amount - allocated_total, 2)
            if abs(rem) >= 0.01:
                comp_amounts["Unallocated Fee"] = comp_amounts.get("Unallocated Fee", 0) + rem
                
            for c_name, c_amt in comp_amounts.items():
                if abs(c_amt) < 0.01: continue
                ledger = comp_ledger.get(c_name, c_name)
                
                rows.append({
                    "journal_date": date_str,
                    "settlement_date": date_str,
                    "reference_number": utr,
                    "journal_number_prefix": "JN-Frappe-",
                    "journal_number_suffix": "",
                    "notes": f"online payment settlement on {date_str} for bank account {bank}" if is_online else (fp.remarks or ""),
                    "journal_type": "Both",
                    "currency": "INR",
                    "account": ledger,
                    "description": "online" if is_online else fp.payment_mode,
                    "contact_name": "Frappe",
                    "debit": 0.0,
                    "credit": c_amt,
                    "department": "ACADEMICS - TEACHING",
                    "course": course,
                    "student_name": fp.student_name,
                    "student_id": fp.student,
                    "batch_id": f"online_{date_str}" if is_online else f"offline_{utr}",
                    "is_credit": True,
                    "is_online": is_online,
                    "raw_date": s_date,
                    "ref_sort": utr
                })
                
            rows.append({
                "journal_date": date_str,
                "settlement_date": date_str,
                "reference_number": utr,
                "journal_number_prefix": "JN-Frappe-",
                "journal_number_suffix": "",
                "notes": f"online payment settlement on {date_str} for bank account {bank}" if is_online else (fp.remarks or ""),
                "journal_type": "Both",
                "currency": "INR",
                "account": bank,
                "description": "online" if is_online else fp.payment_mode,
                "contact_name": "Frappe",
                "debit": amount,
                "credit": 0.0,
                "department": "ACADEMICS - TEACHING",
                "course": course,
                "student_name": fp.student_name,
                "student_id": fp.student,
                "batch_id": f"online_{date_str}" if is_online else f"offline_{utr}",
                "is_credit": False,
                "is_online": is_online,
                "raw_date": s_date,
                "ref_sort": utr
            })

    # 1. ONLINE RECEIPTS
    if not transaction_type or transaction_type == "Online":
        settlements, recon_items = get_razorpay_settlements(filters)
        
        pay_ids = {r.get("entity_id") for r in recon_items if r.get("entity_id") and r.get("type", "").lower() in ("payment", "")}
        if pay_ids:
            conds = ["reference_number IN %s", "status != 'Cancelled'"]
            params = [tuple(pay_ids)]
            if filters.get("student"):
                conds.append("student = %s")
                params.append(filters.get("student"))
            if filters.get("academic_year"):
                conds.append("academic_year = %s")
                params.append(filters.get("academic_year"))
            if filters.get("academic_term"):
                conds.append("academic_term = %s")
                params.append(filters.get("academic_term"))
                
            q = f"""
                SELECT name, reference_number, student, student_name, program, amount, payment_mode, university_bank_account
                FROM `tabFee Payment`
                WHERE {" AND ".join(conds)}
            """
            fp_list = frappe.db.sql(q, tuple(params), as_dict=True)
            
            fp_map = {f.reference_number: f for f in fp_list}
            
            if fp_list:
                settlements_by_id = {s["id"]: s for s in settlements}
                items_by_settlement = {}
                for item in recon_items:
                    items_by_settlement.setdefault(item.get("settlement_id"), []).append(item)
                    
                for sid, items in items_by_settlement.items():
                    s = settlements_by_id.get(sid)
                    if not s: continue
                    
                    s_ts = s.get("settlement_time") or s.get("created_at")
                    import datetime
                    s_date = datetime.datetime.fromtimestamp(s_ts, tz=datetime.timezone.utc).date()
                    
                    if filters.get("from_date") and s_date < getdate(filters.get("from_date")): continue
                    if filters.get("to_date") and s_date > getdate(filters.get("to_date")): continue
                    
                    utr = s.get("utr", "").strip()
                    
                    valid_fp_list = []
                    for item in items:
                        if item.get("type", "").lower() not in ("payment", ""): continue
                        pay_id = item.get("entity_id", "").strip()
                        fp = fp_map.get(pay_id)
                        if not fp: continue
                        
                        amount = round(flt(item.get("amount") or 0) / 100, 2)
                        if amount <= 0: continue
                        
                        fp.amount = amount
                        valid_fp_list.append(fp)
                        
                    process_fp_list(valid_fp_list, is_online=True, s_date_override=s_date, ref_override=utr)

    # 2. OFFLINE RECEIPTS
    if not transaction_type or transaction_type == "Offline":
        conds = ["status != 'Cancelled'", "payment_mode != 'Online Payment'"]
        params = []
        
        if filters.get("student"): 
            conds.append("student = %s")
            params.append(filters.get("student"))
        if filters.get("from_date"):
            conds.append("settlement_date >= %s")
            params.append(filters.get("from_date"))
        if filters.get("to_date"):
            conds.append("settlement_date <= %s")
            params.append(filters.get("to_date"))
        if filters.get("from_settlement_date"):
            conds.append("settlement_date >= %s")
            params.append(filters.get("from_settlement_date"))
        if filters.get("to_settlement_date"):
            conds.append("settlement_date <= %s")
            params.append(filters.get("to_settlement_date"))
        if filters.get("academic_year"):
            conds.append("academic_year = %s")
            params.append(filters.get("academic_year"))
        if filters.get("academic_term"):
            conds.append("academic_term = %s")
            params.append(filters.get("academic_term"))
            
        q2 = f"""
            SELECT name, reference_number, student, student_name, program, amount, payment_mode, settlement_date, remarks, university_bank_account
            FROM `tabFee Payment`
            WHERE {" AND ".join(conds)}
        """
        fp_list = frappe.db.sql(q2, tuple(params), as_dict=True)
        
        process_fp_list(fp_list, is_online=False)

    return rows, warnings

def group_data(data):
    groups = {}
    for row in data:
        batch_id = row.get("batch_id")
        groups.setdefault(batch_id, []).append(row)
        
    grouped_rows = []
    
    def sort_logic(tup):
        batch, rows = tup
        base = rows[0]
        d = getdate(base.get("raw_date", "2099-01-01"))
        is_online = 1 if base.get("is_online") else 0
        ref = base.get("ref_sort", "")
        return (d, is_online)
        
    sorted_batches = sorted(groups.items(), key=sort_logic)
    
    for batch_id, group_rows in sorted_batches:
        if not group_rows: continue
        
        credit_sums = {}
        total_debit = 0.0
        
        base_row = group_rows[0]
        is_online = base_row.get("is_online")
        debit_account = None
        
        for r in group_rows:
            if r.get("is_credit"):
                key = (r["account"], r["course"])
                credit_sums[key] = credit_sums.get(key, 0.0) + flt(r["credit"])
            else:
                total_debit += flt(r["debit"])
                if not debit_account:
                    debit_account = r["account"]
                    
        for (account, course), amt in credit_sums.items():
            if abs(amt) < 0.01: continue
            new_r = base_row.copy()
            new_r["account"] = account
            new_r["course"] = course
            new_r["debit"] = 0.0
            new_r["credit"] = amt
            new_r["student_id"] = ""
            new_r["student_name"] = ""
            new_r["department"] = "ACADEMICS - TEACHING"
            new_r["contact_name"] = "CollPoll"
            
            if is_online:
                new_r["reference_number"] = ""
                
            grouped_rows.append(new_r)
            
        if total_debit > 0:
            new_r = base_row.copy()
            new_r["account"] = debit_account or ""
            new_r["course"] = ""
            new_r["department"] = ""
            new_r["student_id"] = ""
            new_r["student_name"] = ""
            new_r["debit"] = total_debit
            new_r["credit"] = 0.0
            new_r["contact_name"] = "CollPoll"
            
            if is_online:
                new_r["reference_number"] = ""
                
            grouped_rows.append(new_r)
            
    return grouped_rows


@frappe.whitelist()
def download_zoho_upload_file(filters, file_format):
    import json
    if isinstance(filters, str):
        filters = json.loads(filters)
        
    columns = get_columns()
    export_mode = filters.get("export_mode", "Student Level")
    if export_mode == "Grouped":
        columns = get_grouped_columns()
        
    data, warnings = get_data(filters)
    
    if export_mode == "Grouped":
        data = group_data(data)
        for r in data:
            r["contact_name"] = "CollPoll"
    else:
        for r in data:
            r["contact_name"] = "Frappe"
            
    for r in data:
        if "debit" in r and r["debit"] == 0:
            r["debit"] = ""
        if "credit" in r and r["credit"] == 0:
            r["credit"] = ""
            
    debits = sum([flt(d.get("debit") or 0) for d in data])
    credits = sum([flt(d.get("credit") or 0) for d in data])
    balanced = abs(debits - credits) < 0.1
    
    import csv, io, base64
    out = io.StringIO()
    writer = csv.writer(out)
    
    writer.writerow([c["label"] for c in columns])
    for row in data:
        writer.writerow([row.get(c["fieldname"], "") for c in columns])
        
    content = out.getvalue().encode("utf-8")
    b64 = base64.b64encode(content).decode("utf-8")
    
    return {
        "content": b64,
        "filename": f"zoho_journal_{export_mode.lower().replace(' ', '_')}.csv",
        "mime": "text/csv",
        "row_count": len(data),
        "balanced": balanced,
        "warnings": len(warnings)
    }

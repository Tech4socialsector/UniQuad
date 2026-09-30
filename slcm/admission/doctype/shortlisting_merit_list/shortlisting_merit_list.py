import frappe
import re
from frappe.model.document import Document

class ShortlistingMeritList(Document):
    def autoname(self):
        from frappe.model.naming import make_autoname
        if not self.admission_cycle or not self.campus:
            frappe.throw("Admission Cycle and Campus are required for naming.")

        # Use codes instead of names to keep it short
        cycle_code = frappe.db.get_value("Admission Cycle", self.admission_cycle, "cycle_code") or self.admission_cycle
        campus_code = frappe.db.get_value("Campus", self.campus, "campus_code") or self.campus
        
        cycle = cycle_code.replace(" ", "").upper()
        campus = campus_code.replace(" ", "").upper()
        level = (self.program_level or "ALL").upper()

        if self.program:
            program_code = frappe.db.get_value("Programme", self.program, "program_code") or self.program
            # Allow: - . , ( ) along with Alphanumeric
            prog = re.sub(r'[^A-Z0-9\-\.\,\(\)]', '', program_code.replace(" ", "").upper())
            # Use ignore_validate=True to allow parentheses and commas in naming series prefix
            self.name = make_autoname(f"SP-{cycle}-{campus}-{prog}-.####", ignore_validate=True)
        else:
            self.name = make_autoname(f"SP-{cycle}-{campus}-{level}-.####", ignore_validate=True)

    def clear_all_lists(self):
        tables = [
            "shortlist_applicants", "master_rank_list", "general_list", 
            "sc_list", "st_list", "obc_list", "ews_list",
            "karnataka_list", "women_list", "pwd_list"
        ]
        for t in tables:
            self.set(t, [])

    def clear_category_lists(self):
        tables = [
            "general_list", "sc_list", "st_list", "obc_list", "ews_list",
            "karnataka_list", "women_list", "pwd_list"
        ]
        for t in tables:
            self.set(t, [])

    def validate(self):
        self.calculate_summary_counts()

    def calculate_summary_counts(self):
        if self.shortlist_applicants:
            self.total_candidates = len(self.shortlist_applicants)
            self.total_shortlisted = len([a for a in self.shortlist_applicants if a.shortlist_status == "Shortlisted"])
            self.total_rejected = len([a for a in self.shortlist_applicants if a.shortlist_status == "Rejected"])

    def pull_from_merit_list(self, merit):
        if isinstance(merit, str):
            merit = frappe.get_doc("Merit List", merit)
            
        self.clear_all_lists()
        
        for row in merit.merit_applicants:
            self.append("shortlist_applicants", {
                "applicant_id": row.applicant_id,
                "candidate_name": row.candidate_name,
                "program": row.program,
                "nlsat_part_a_score": row.total_score, # Use total_score from Part A Ranking
                "percentile_score": row.get("percentile_score") or getattr(row, "percentile_score", 0),
                "shortlist_rank": row.overall_rank,
                "category_rank": row.category_rank,
                "actual_category": row.get("actual_category"),
                "date_of_birth": row.get("date_of_birth"),
                "shortlist_status": "Shortlisted"
            })
        self.calculate_summary_counts()
        
        # Automatically execute shortlisting logic to fill categories
        from slcm.admission.doctype.merit_generation.merit_service import execute_advanced_allocation_logic, _populate_category_lists
        execute_advanced_allocation_logic(self, is_shortlist_allocation=True)
        _populate_category_lists(self)
        
        # Re-calculate shortlisted count after allocation
        self.calculate_summary_counts()
        
        self.status = "Allocated"
        self.save()

    @frappe.whitelist()
    def execute_shortlisting_logic(self):
        self.clear_category_lists()
        from slcm.admission.doctype.merit_generation.merit_service import execute_advanced_allocation_logic, _populate_category_lists
        execute_advanced_allocation_logic(self, is_shortlist_allocation=True)
        _populate_category_lists(self)
        self.calculate_summary_counts()
        self.status = "Allocated"
        self.save()
        frappe.db.commit()

    @frappe.whitelist()
    def clear_generation_progress(self):
        cache_key = f"merit_generation_{self.admission_cycle}_{self.campus}_{self.program_level}_{self.program or ''}".replace(" ", "_")
        frappe.cache().delete_value(cache_key)
        frappe.cache().set_value(cache_key, {
            "percent": 0,
            "status": "In Progress",
            "description": "Starting Final Merit List generation...",
            "current": 0,
            "total": 100
        }, expires_in_sec=300)

    @frappe.whitelist()
    def generate_final_merit_list(self):
        """
        Triggers the Phase 2 Merit Generation (Entrance + Interview).
        """
        self.clear_generation_progress()

        from slcm.admission.doctype.merit_generation.merit_service import generate_merit_for_level
        merit_list = generate_merit_for_level(
            self.admission_cycle, 
            self.campus, 
            self.program_level, 
            program=self.program,
            processing_stage="Final Allotment Ranking"
        )

        total_applicants = merit_list.total_applicants or len(merit_list.merit_applicants)
        total_selected = merit_list.total_selected or 0
        total_rejected = merit_list.total_rejected or 0

        frappe.msgprint(
            msg=(
                f"Final Admission Merit List generated. Results pushed to <b><a href='/app/merit-list/{merit_list.name}'>{merit_list.name}</a></b>.<br><br>"
                f"<b>Summary:</b><br>"
                f"• Total Applicants: {total_applicants}<br>"
                f"• Selected: {total_selected}<br>"
                f"• Rejected: {total_rejected}"
            ),
            title="Final Merit List Generated",
            indicator="green",
            primary_action={
                "label": "View Final Merit List",
                "client_action": "frappe.set_route",
                "args": ["Form", "Merit List", merit_list.name]
            }
        )

        return merit_list.name

    def on_update(self):
        self.sync_shortlisted_status_to_entrance_test_allocations()

    def on_trash(self):
        self.clear_shortlisted_status_in_entrance_test_allocations()

    def on_cancel(self):
        self.clear_shortlisted_status_in_entrance_test_allocations()

    def sync_shortlisted_status_to_entrance_test_allocations(self):
        """
        Synchronizes shortlisted_status field in Entrance Test Seat Allocation
        with candidate shortlist_status from this Shortlisting Merit List using bulk SQL queries.
        """
        status_groups = {}
        if self.shortlist_applicants:
            for row in self.shortlist_applicants:
                if row.applicant_id:
                    st = row.shortlist_status or "Shortlisted"
                    status_groups.setdefault(st, []).append(row.applicant_id)

        batch_size = 1000
        # Bulk update status for shortlisted applicants using Primary Key
        for status_val, app_ids in status_groups.items():
            for i in range(0, len(app_ids), batch_size):
                batch = app_ids[i:i + batch_size]
                frappe.db.sql("""
                    UPDATE `tabEntrance Test Seat Allocation`
                    SET shortlisted_status = %(status)s
                    WHERE name IN %(applicants)s
                      AND (shortlisted_status != %(status)s OR shortlisted_status IS NULL)
                """, {"status": status_val, "applicants": tuple(batch)})

    def clear_shortlisted_status_in_entrance_test_allocations(self):
        """
        Clears shortlisted_status to blank ("") in Entrance Test Seat Allocation
        for all applicants associated with this Shortlisting Merit List using bulk SQL queries.
        """
        applicant_ids = [row.applicant_id for row in (self.shortlist_applicants or []) if row.applicant_id]

        batch_size = 1000
        if applicant_ids:
            for i in range(0, len(applicant_ids), batch_size):
                batch = applicant_ids[i:i + batch_size]
                frappe.db.sql("""
                    UPDATE `tabEntrance Test Seat Allocation`
                    SET shortlisted_status = ''
                    WHERE name IN %(applicants)s
                      AND shortlisted_status != ''
                      AND shortlisted_status IS NOT NULL
                """, {"applicants": tuple(batch)})

        frappe.db.delete("Admission Audit Log", {
            "reference_doctype": "Shortlisting Merit List",
            "reference_name": self.name
        })

@frappe.whitelist()
def get_generation_progress(docname):
    """
    Returns cached progress for Final Merit List generation.
    """
    doc = frappe.get_doc("Shortlisting Merit List", docname)
    cache_key = f"merit_generation_{doc.admission_cycle}_{doc.campus}_{doc.program_level}_{doc.program or ''}".replace(" ", "_")
    progress = frappe.cache().get_value(cache_key) or {}
    
    if "status" not in progress:
        progress["status"] = "In Progress"
    if "percent" not in progress:
        progress["percent"] = 0
    if "description" not in progress:
        progress["description"] = "Starting Final Merit List generation..."

    return progress

def build_styled_excel(workbook, sheet_name, headers, rows):
    worksheet = workbook.add_worksheet(sheet_name[:31])
    worksheet.hide_gridlines(0)

    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#166534',
        'font_color': '#FFFFFF',
        'font_name': 'Calibri',
        'font_size': 11,
        'align': 'center',
        'valign': 'vcenter',
        'border': 1,
        'border_color': '#94A3B8'
    })

    cell_even_format = workbook.add_format({
        'font_name': 'Calibri',
        'font_size': 10,
        'valign': 'vcenter',
        'border': 1,
        'border_color': '#E2E8F0',
        'bg_color': '#FFFFFF'
    })

    cell_odd_format = workbook.add_format({
        'font_name': 'Calibri',
        'font_size': 10,
        'valign': 'vcenter',
        'border': 1,
        'border_color': '#E2E8F0',
        'bg_color': '#F8FAFC'
    })

    perc_even_format = workbook.add_format({
        'font_name': 'Calibri',
        'font_size': 10,
        'align': 'right',
        'valign': 'vcenter',
        'num_format': '0.00000',
        'border': 1,
        'border_color': '#E2E8F0',
        'bg_color': '#FFFFFF'
    })

    perc_odd_format = workbook.add_format({
        'font_name': 'Calibri',
        'font_size': 10,
        'align': 'right',
        'valign': 'vcenter',
        'num_format': '0.00000',
        'border': 1,
        'border_color': '#E2E8F0',
        'bg_color': '#F8FAFC'
    })

    num_even_format = workbook.add_format({
        'font_name': 'Calibri',
        'font_size': 10,
        'align': 'right',
        'valign': 'vcenter',
        'num_format': '0.00',
        'border': 1,
        'border_color': '#E2E8F0',
        'bg_color': '#FFFFFF'
    })

    num_odd_format = workbook.add_format({
        'font_name': 'Calibri',
        'font_size': 10,
        'align': 'right',
        'valign': 'vcenter',
        'num_format': '0.00',
        'border': 1,
        'border_color': '#E2E8F0',
        'bg_color': '#F8FAFC'
    })

    center_even_format = workbook.add_format({
        'font_name': 'Calibri',
        'font_size': 10,
        'align': 'center',
        'valign': 'vcenter',
        'border': 1,
        'border_color': '#E2E8F0',
        'bg_color': '#FFFFFF'
    })

    center_odd_format = workbook.add_format({
        'font_name': 'Calibri',
        'font_size': 10,
        'align': 'center',
        'valign': 'vcenter',
        'border': 1,
        'border_color': '#E2E8F0',
        'bg_color': '#F8FAFC'
    })

    worksheet.set_row(0, 26)
    col_widths = [len(str(h)) for h in headers]
    for col_idx, header in enumerate(headers):
        worksheet.write(0, col_idx, header, header_format)

    for row_idx, row in enumerate(rows, start=1):
        worksheet.set_row(row_idx, 20)
        is_odd = (row_idx % 2 == 1)
        for col_idx, val in enumerate(row):
            header_name = headers[col_idx]
            val_str = str(val) if val is not None else ""
            col_widths[col_idx] = max(col_widths[col_idx], len(val_str))

            if "Percentile" in header_name:
                fmt = perc_odd_format if is_odd else perc_even_format
                try:
                    val_num = float(val) if val is not None else 0.0
                    worksheet.write_number(row_idx, col_idx, val_num, fmt)
                except Exception:
                    worksheet.write(row_idx, col_idx, val_str, fmt)
            elif "Score" in header_name or "Marks" in header_name:
                fmt = num_odd_format if is_odd else num_even_format
                try:
                    val_num = float(val) if val is not None else 0.0
                    worksheet.write_number(row_idx, col_idx, val_num, fmt)
                except Exception:
                    worksheet.write(row_idx, col_idx, val_str, fmt)
            elif "Rank" in header_name or "ID" in header_name or "Status" in header_name:
                fmt = center_odd_format if is_odd else center_even_format
                if isinstance(val, int):
                    worksheet.write_number(row_idx, col_idx, val, fmt)
                else:
                    worksheet.write(row_idx, col_idx, val_str, fmt)
            else:
                fmt = cell_odd_format if is_odd else cell_even_format
                worksheet.write(row_idx, col_idx, val_str, fmt)

    for col_idx, width in enumerate(col_widths):
        worksheet.set_column(col_idx, col_idx, max(width + 4, 12))


@frappe.whitelist()
def download_merit_list(name, download_type, category=None):
    doc = frappe.get_doc("Shortlisting Merit List", name)
    
    columns = [
        "Applicant ID", "Candidate Name", "Part A Rank", "Candidate Category", 
        "Category Rank", "Part A Score", "Part A Percentile", "Vertical Category", 
        "Compartmentalized Category", "Horizontal Categories", 
        "Allocation Type", "Shortlisted Category", "Shortlist Status"
    ]
    
    def get_row(candidate):
        perc = candidate.get("percentile_score")
        if perc is not None:
            try:
                perc = round(float(perc), 5)
            except Exception:
                pass
        else:
            perc = 0.0

        return [
            candidate.applicant_id,
            candidate.candidate_name,
            candidate.shortlist_rank or candidate.get("overall_rank") or "",
            candidate.actual_category,
            candidate.category_rank or "",
            candidate.nlsat_part_a_score,
            perc,
            candidate.vertical_category or "",
            candidate.compartmentalized_category or "",
            candidate.horizontal_categories or "",
            candidate.allocation_type or "Not Allocated",
            candidate.shortlist_category or "",
            candidate.shortlist_status or "Draft"
        ]

    xlsx_data = {}

    if download_type == "Overall":
        sheet_name = "Overall Shortlist Rank List"
        rows = []
        for cand in doc.shortlist_applicants:
            rows.append(get_row(cand))
        xlsx_data[sheet_name] = rows
    
    elif download_type == "Category Wise":
        category_map = {
            "General": ("Vertical Shortlist Rank List", lambda c: (c.actual_category == "General" or (c.shortlist_category and "General" in c.shortlist_category))),
            "SC": ("SC Shortlist Rank List", lambda c: (c.actual_category == "SC" or (c.shortlist_category and "SC" in c.shortlist_category))),
            "ST": ("ST Shortlist Rank List", lambda c: (c.actual_category == "ST" or (c.shortlist_category and "ST" in c.shortlist_category))),
            "OBC": ("OBC Shortlist Rank List", lambda c: (c.actual_category in ["OBC-NCL", "OBC"] or (c.shortlist_category and "OBC" in c.shortlist_category))),
            "EWS": ("EWS Shortlist Rank List", lambda c: (c.actual_category == "EWS" or (c.shortlist_category and "EWS" in c.shortlist_category))),
            "Karnataka": ("Karnataka Shortlist Rank List", lambda c: (c.compartmentalized_category == "Karnataka" or (c.shortlist_category and "Karnataka" in c.shortlist_category) or getattr(c, "is_karnataka", False))),
            "Women": ("Women Shortlist Rank List", lambda c: ("Women" in (c.horizontal_categories or "") or (c.shortlist_category and "Women" in c.shortlist_category) or getattr(c, "is_female", False))),
            "PWD": ("PWD Shortlist Rank List", lambda c: ("PWD" in (c.horizontal_categories or "") or (c.shortlist_category and "PWD" in c.shortlist_category) or getattr(c, "is_pwd", False)))
        }
        
        if category and category != "All":
            if category in category_map:
                label, filter_fn = category_map.get(category)
                rows = []
                for cand in doc.shortlist_applicants:
                    if filter_fn(cand):
                        rows.append(get_row(cand))
                xlsx_data[label] = rows
        else:
            for cat_key, (label, filter_fn) in category_map.items():
                cat_rows = []
                for cand in doc.shortlist_applicants:
                    if filter_fn(cand):
                        cat_rows.append(get_row(cand))
                if len(cat_rows) > 0:
                    xlsx_data[label] = cat_rows

    if not xlsx_data or not any(len(rows) > 0 for rows in xlsx_data.values()):
        frappe.throw("No candidate records found for the selected criteria. Please ensure the shortlisting logic has been run.")

    from io import BytesIO
    import xlsxwriter

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    
    for sheet_name, rows in xlsx_data.items():
        build_styled_excel(workbook, sheet_name, columns, rows)
    
    workbook.close()
    
    prog = doc.program or "Programme"
    year = frappe.db.get_value("Admission Cycle", doc.admission_cycle, "academic_year") or "Year"
    if download_type == "Overall":
        fname = f"overall shortlisting rank report - {prog} - {year}.xlsx"
    else:
        cat_label = category if category and category != "All" else "Category Wise"
        fname = f"{cat_label} shortlisting rank list - {prog} - {year}.xlsx"
    
    frappe.response['filename'] = fname
    frappe.response['filecontent'] = output.getvalue()
    frappe.response['type'] = 'binary'

@frappe.whitelist()
def clear_generation_progress(docname=None):
    if not docname:
        return
    doc = frappe.get_doc("Shortlisting Merit List", docname) if isinstance(docname, str) else docname
    cache_key = f"merit_generation_{doc.admission_cycle}_{doc.campus}_{doc.program_level}_{doc.program or ''}".replace(" ", "_")
    frappe.cache().delete_value(cache_key)
    frappe.cache().set_value(cache_key, {
        "percent": 0,
        "status": "In Progress",
        "description": "Starting Final Merit List generation...",
        "current": 0,
        "total": 100
    }, expires_in_sec=300)

@frappe.whitelist()
def generate_final_merit_list(docname=None):
    if not docname:
        frappe.throw("Document Name is required.")
    doc = frappe.get_doc("Shortlisting Merit List", docname) if isinstance(docname, str) else docname
    return doc.generate_final_merit_list()

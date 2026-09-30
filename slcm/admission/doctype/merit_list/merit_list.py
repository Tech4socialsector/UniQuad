import frappe
import re
import json
from frappe.model.document import Document


class MeritList(Document):

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
            self.name = make_autoname(f"ML-{cycle}-{campus}-{prog}-.#####", ignore_validate=True)
        else:
            self.name = make_autoname(f"ML-{cycle}-{campus}-{level}-.#####", ignore_validate=True)

    def validate(self):
        self.validate_uniqueness()
        self.calculate_summary_counts()

    def calculate_summary_counts(self):
        if self.merit_applicants:
            self.total_applicants = len(self.merit_applicants)
            self.total_selected = len([a for a in self.merit_applicants if a.status == "Selected"])
            self.total_rejected = len([a for a in self.merit_applicants if a.status == "Rejected"])

    def on_trash(self):
        """
        When a Merit List is deleted, clear its associated audit logs
        to prevent Frappe's link constraint errors.
        """
        frappe.db.delete("Merit Audit Log", {"merit_list": self.name})
        frappe.db.delete("Admission Audit Log", {
            "reference_doctype": "Merit List",
            "reference_name": self.name
        })

    def validate_uniqueness(self):
        """
        Ensures only one PUBLISHED Merit List exists per Campus, Admission Cycle, and Program Level.
        """
        if self.status != "Published":
            return

        filters = {
            "campus": self.campus,
            "admission_cycle": self.admission_cycle,
            "program_level": self.program_level,
            "status": "Published",
            "name": ["!=", self.name]
        }
        if self.program:
            filters["program"] = self.program

        existing = frappe.db.exists("Merit List", filters)
        if existing:
            from frappe.utils import get_link_to_form
            link = get_link_to_form("Merit List", existing)
            frappe.throw(
                f"A Merit List is already PUBLISHED for Campus '{self.campus}', "
                f"Admission Cycle '{self.admission_cycle}' and Program Level '{self.program_level or 'All'}'. "
                f"Unpublish it first if you need to publish this one. "
                f"<br><br>Existing Published Merit List: {link}",
                title="Duplicate Published Merit List"
            )


@frappe.whitelist()
def create_seat_allocation(merit_list_name, selected_applicants):
    """
    Creates a Seat Allocation from selected applicant names.
    Fetches merit data (score, ranks) from the Merit List child table.
    Returns the name of the created Seat Allocation.
    """
    if isinstance(selected_applicants, str):
        selected_applicants = json.loads(selected_applicants)

    if not selected_applicants:
        frappe.throw("No applicants selected.", title="Empty Selection")

    merit = frappe.get_doc("Merit List", merit_list_name)
    cache_key = f"merit_generation_{merit.admission_cycle}_{merit.campus}_{merit.program_level}_{merit.program or ''}".replace(" ", "_")
    frappe.cache().delete_value(cache_key)

    # Build a lookup map: applicant ID -> merit row data
    merit_data = {
        row.applicant_id: row
        for row in merit.merit_applicants
    }

    # Check if a Draft Seat Allocation already exists for this merit list
    existing_name = frappe.db.get_value("Seat Allocation", {
        "merit_list": merit_list_name,
        "status": "Draft"
    }, "name")

    if existing_name:
        alloc = frappe.get_doc("Seat Allocation", existing_name)
        # Reset basic fields in case they changed in Merit List
        alloc.admission_cycle = merit.admission_cycle
        alloc.campus = merit.campus
        alloc.program_level = merit.program_level
        alloc.program = merit.program
    else:
        # Create New Seat Allocation
        alloc = frappe.new_doc("Seat Allocation")
        alloc.admission_cycle = merit.admission_cycle
        alloc.campus = merit.campus
        alloc.program_level = merit.program_level
        alloc.program = merit.program
        alloc.merit_list = merit_list_name
        alloc.status = "Draft"

    alloc.set("selection_applicant", [])
    for applicant_id in selected_applicants:
        row = merit_data.get(applicant_id)
        # Skip Rejected applicants — they must not receive a seat allocation
        if row and row.status == "Rejected":
            continue
        alloc.append("selection_applicant", {
            "applicant_id": row.applicant_id if row else applicant_id,
            "candidate_name": row.candidate_name if row else None,
            "program": row.program if row else None,
            "total_score": row.total_score if row else 0,
            "entrance_score": row.entrance_score if row else 0,
            "interview_score": row.interview_score if row else 0,
            "nlsat_part_a_score": row.entrance_score if row else 0,
            "nlsat_part_b_score": row.interview_score if row else 0,
            "hsc_percentage": getattr(row, "hsc_percentage", 0) if row else 0,
            "overall_rank": row.overall_rank if row else None,
            "shortlist_rank": row.overall_rank if row and merit.merit_processing_stage == "Part A Ranking" else None,
            "admission_rank": row.overall_rank if row and merit.merit_processing_stage == "Final Allotment Ranking" else None,
            "actual_category": row.actual_category if row else None,
            "vertical_category": row.vertical_category if row else None,
            "percentile_score": row.percentile_score if row else 0,
            "selection_status": "Draft"
        })

    if not alloc.selection_applicant:
        frappe.throw("No eligible applicants to allocate. Rejected applicants cannot be added to a Seat Allocation.", title="No Eligible Applicants")

    alloc.total_selected = len(alloc.selection_applicant)
    alloc.insert()
    
    # Run automatic allocation logic immediately
    alloc.allocate_seats()
    
    frappe.db.commit()

    return alloc.name


@frappe.whitelist()
def publish_merit_list(merit_list_name):
    """
    Publishes the Merit List so students can view their scores
    on the applicant results portal page.
    Sets status to 'Publishing' during execution and 'Published' once completed.
    Also updates the Application Status of all applicants in the list to 'Merit Published'.
    """
    doc = frappe.get_doc("Merit List", merit_list_name)

    if doc.status == "Published":
        frappe.throw(f"Merit List '{merit_list_name}' is already published.")
    if doc.status in ["Publishing", "In Progress"]:
        frappe.throw(f"Merit List '{merit_list_name}' is currently being published. Please wait.")

    # Mark status as Publishing while processing
    doc.db_set("status", "Publishing")
    frappe.db.commit()

    total = len(doc.merit_applicants)

    frappe.publish_realtime(
        "publish_merit_list_progress",
        {
            "current": 0,
            "total": total,
            "percent": 0,
            "message": "Starting publication...",
            "docname": doc.name
        },
        user=frappe.session.user
    )

    try:
        # Update Applicant status & trigger notifications in one loop with realtime progress
        for i, row in enumerate(doc.merit_applicants):
            if row.applicant_id:
                new_status = "Merit Published"
                if row.status == "Selected":
                    new_status = "Merit Selected"
                elif row.status == "Rejected":
                    new_status = "Merit Rejected"
                elif row.status == "Waitlisted":
                    new_status = "Merit Waitlisted"
                    
                frappe.db.set_value("Applicant", row.applicant_id, "status", new_status)

                applicant_email = frappe.db.get_value("Applicant", row.applicant_id, "email")
                if applicant_email:
                    try:
                        _send_merit_email_local(doc, row, applicant_email)
                        _send_merit_system_notification_local(doc, row, applicant_email)
                    except Exception:
                        frappe.log_error(frappe.get_traceback(), f"Merit Notification Failed for {row.applicant_id}")

            percent = int(((i + 1) / max(total, 1)) * 100)
            frappe.publish_realtime(
                "publish_merit_list_progress",
                {
                    "current": i + 1,
                    "total": total,
                    "percent": percent,
                    "message": f"Publishing: {row.candidate_name or row.applicant_id} ({i + 1} of {total})",
                    "docname": doc.name
                },
                user=frappe.session.user
            )

            if (i + 1) % 10 == 0:
                frappe.db.commit()

        # Mark as Published only AFTER all candidates are processed
        from frappe.utils import now_datetime
        doc.reload()
        doc.status = "Published"
        doc.published_on = now_datetime()
        doc.save()

        frappe.publish_realtime(
            "publish_merit_list_progress",
            {
                "current": total,
                "total": total,
                "percent": 100,
                "message": "Merit list published successfully.",
                "docname": doc.name
            },
            user=frappe.session.user
        )

        frappe.db.commit()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Merit List Publish Failed for {doc.name}")
        doc.db_set("status", "Generated")
        frappe.db.commit()
        frappe.throw(f"Failed to publish merit list: {str(e)}")

    return {"status": "Published"}


def _trigger_merit_notifications_local(doc):
    """
    Directly loops through applicants and sends notifications.
    Matches the pattern used in Interview Seat Allocation.
    """
    total = len(doc.merit_applicants)
    for i, row in enumerate(doc.merit_applicants):
        if not row.applicant_id:
            continue
            
        applicant_email = frappe.db.get_value("Applicant", row.applicant_id, "email")
        if not applicant_email:
            continue
            
        try:
            _send_merit_email_local(doc, row, applicant_email)
            _send_merit_system_notification_local(doc, row, applicant_email)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Merit Notification Failed for {row.applicant_id}")

        # Commit every 10 records to match the Interview method
        if i % 10 == 0:
            frappe.db.commit()

def _send_merit_email_local(doc, row, email):
    """
    Sends email using 'Merit List Template' following the Interview style.
    """
    template_name = "Merit List Template"
    if not frappe.db.exists("Email Template", template_name):
        return

    template = frappe.get_doc("Email Template", template_name)
    
    # Prepare context
    pub_date = frappe.utils.format_date(doc.modified or frappe.utils.now(), "dd MMMM yyyy")
    args = {
        "doc": doc,
        "row": row,
        "candidate_name": row.candidate_name,
        "merit_list_name": doc.name,
        "overall_rank": row.overall_rank or "—",
        "total_score": row.total_score or "0",
        "published_date": pub_date,
        "portal_link": frappe.utils.get_url(f"/my-applications?app={row.applicant_id}")
    }

    subject = frappe.render_template(template.subject, args)
    
    if template.get("use_html"):
        message = frappe.render_template(template.response_html, args)
    else:
        message = frappe.render_template(template.response, args)

    if not message:
        message = frappe.render_template(template.get("message") or "", args)

    cc_list = []
    cc_field_value = template.get("cc")
    if cc_field_value:
        cc_list = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]

    if message:
        sender = None
        if template.get("email_account"):
            sender = frappe.db.get_value("Email Account", template.get("email_account"), "email_id") or template.get("email_account")

        frappe.sendmail(
            recipients=[email],
            sender=sender,
            cc=cc_list,
            subject=subject,
            message=message,
            reference_doctype="Merit List",
            reference_name=doc.name,
            now=False
        )
        frappe.logger().info(f"Merit email queued to {email} for {doc.name}")

def _send_merit_system_notification_local(doc, row, email):
    """
    Creates Notification Log following the Interview style.
    """
    if frappe.db.exists("User", email):
        message_body = f"""
            <p>The merit list <strong>"{doc.name}"</strong> has been published.</p>
            <p>Your rank and merit score are now available.</p>
            <p><a href="/my-applications?app={row.applicant_id}" style="color: #16a34a; font-weight: bold;">Click here to view your result.</a></p>
        """
        
        frappe.get_doc({
            "doctype": "Notification Log",
            "subject": "Merit List Published",
            "for_user": email,
            "type": "Alert",
            "email_content": message_body,
            "document_type": "Merit List",
            "document_name": doc.name,
            "from_user": frappe.session.user,
            "link": f"/my-applications?app={row.applicant_id}"
        }).insert(ignore_permissions=True)




@frappe.whitelist()
def unpublish_merit_list(merit_list_name):
    """
    Reverts the Merit List status to 'Generated', hiding scores from students.
    Also reverts the Application Status of all applicants in the list to 'Submitted'.
    """
    doc = frappe.get_doc("Merit List", merit_list_name)

    if doc.status != "Published":
        frappe.throw("Merit List is not currently published.")

    doc.status = "Generated"
    doc.published_on = None
    doc.save()

    # Revert Applicant status
    for row in doc.merit_applicants:
        if row.applicant_id:
            # Revert to Submitted if it was any Merit status
            current_status = frappe.db.get_value("Applicant", row.applicant_id, "status")
            if current_status in ["Merit Published", "Merit Selected", "Merit Rejected", "Merit Waitlisted"]:
                frappe.db.set_value("Applicant", row.applicant_id, "status", "Submitted")



    frappe.db.commit()
    return {"status": "Generated"}


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
    doc = frappe.get_doc("Merit List", name)
    
    columns = [
        "Applicant ID", "Candidate Name", "Rank", "Candidate Category", 
        "Category Rank", "Part A Score", "Part B Score", "Total Score", "Final Percentile",
        "Vertical Category", "Shortlisted Category", "Allocation Type", "Selection Status"
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
            candidate.overall_rank or "",
            candidate.actual_category,
            candidate.category_rank or "",
            candidate.entrance_score or candidate.get("nlsat_part_a_score") or 0,
            candidate.interview_score or candidate.get("nlsat_part_b_score") or 0,
            candidate.total_score,
            perc,
            candidate.vertical_category or "",
            candidate.shortlist_category or "",
            candidate.allocation_type or "Not Allocated",
            candidate.status or "Draft"
        ]

    xlsx_data = {}

    if download_type == "Overall":
        sheet_name = "Overall Final Merit Rank List"
        rows = []
        for cand in doc.merit_applicants:
            rows.append(get_row(cand))
        xlsx_data[sheet_name] = rows
    
    elif download_type == "Category Wise":
        category_map = {
            "General": ("Vertical Merit Rank List", lambda c: (c.actual_category == "General" or (c.shortlist_category and "General" in c.shortlist_category))),
            "SC": ("SC Merit Rank List", lambda c: (c.actual_category == "SC" or (c.shortlist_category and "SC" in c.shortlist_category))),
            "ST": ("ST Merit Rank List", lambda c: (c.actual_category == "ST" or (c.shortlist_category and "ST" in c.shortlist_category))),
            "OBC": ("OBC Merit Rank List", lambda c: (c.actual_category in ["OBC-NCL", "OBC"] or (c.shortlist_category and "OBC" in c.shortlist_category))),
            "EWS": ("EWS Merit Rank List", lambda c: (c.actual_category == "EWS" or (c.shortlist_category and "EWS" in c.shortlist_category))),
            "Karnataka": ("Karnataka Merit Rank List", lambda c: (c.compartmentalized_category == "Karnataka" or (c.shortlist_category and "Karnataka" in c.shortlist_category) or getattr(c, "is_karnataka", False))),
            "Women": ("Women Merit Rank List", lambda c: ("Women" in (c.horizontal_categories or "") or (c.shortlist_category and "Women" in c.shortlist_category) or getattr(c, "is_female", False))),
            "PWD": ("PWD Merit Rank List", lambda c: ("PWD" in (c.horizontal_categories or "") or (c.shortlist_category and "PWD" in c.shortlist_category) or getattr(c, "is_pwd", False)))
        }
        
        if category and category != "All":
            if category in category_map:
                label, filter_fn = category_map.get(category)
                rows = []
                for cand in doc.merit_applicants:
                    if filter_fn(cand):
                        rows.append(get_row(cand))
                xlsx_data[label] = rows
        else:
            for cat_key, (label, filter_fn) in category_map.items():
                cat_rows = []
                for cand in doc.merit_applicants:
                    if filter_fn(cand):
                        cat_rows.append(get_row(cand))
                if len(cat_rows) > 0:
                    xlsx_data[label] = cat_rows

    if not xlsx_data or not any(len(rows) > 0 for rows in xlsx_data.values()):
        frappe.throw("No candidate records found for the selected criteria. Please ensure the merit list has been generated.")

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
        fname = f"overall final merit rank report - {prog} - {year}.xlsx"
    else:
        cat_label = category if category and category != "All" else "Category Wise"
        fname = f"{cat_label} final merit rank list - {prog} - {year}.xlsx"
    
    frappe.response['filename'] = fname
    frappe.response['filecontent'] = output.getvalue()
    frappe.response['type'] = 'binary'

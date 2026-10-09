import frappe
from frappe import _
import json
import traceback
from frappe.model.document import Document
from frappe.utils import now_datetime, get_url, get_datetime, nowdate, format_date, flt, get_site_path
from frappe.utils.pdf import get_pdf
import os
import base64
import re



class EntranceTestSeatAllocation(Document):

    def validate(self):
        max_marks = self.total_marks or 200
        if (self.part_a_total_marks_scored or 0) + (self.part_b_total_marks_scored or 0) > max_marks:
            frappe.throw(f"Total Score (Part A + Part B) cannot be more than {max_marks}.")

    def before_save(self):
        # Fetch start/end time from Admission Cycle Entrance Test Details child table
        is_res = (self.is_rescheduled == 1 or self.entrance_test_status == "Rescheduled")
        f_test = self.re_entrance_test_name or self.re_entrance_test_list if is_res else (self.entrance_test_name or self.entrance_test_list)
        if self.admission_cycle and f_test:
            filters = {"parent": self.admission_cycle, "entrance_test_name": f_test}
            if self.program_level:
                filters["programme_level"] = self.program_level
            test_details = frappe.db.get_value("Entrance Test Details", 
                filters, 
                ["start_time", "end_time"], 
                as_dict=True
            )
            if not test_details and self.program_level:
                test_details = frappe.db.get_value("Entrance Test Details", 
                    {"parent": self.admission_cycle, "entrance_test_name": f_test}, 
                    ["start_time", "end_time"], 
                    as_dict=True
                )
            if test_details:
                self.start_time = test_details.start_time
                self.end_time = test_details.end_time

        # Check if the applicant is an international applicant
        if self.applicant:
            foreign_national = frappe.db.get_value("Applicant", self.applicant, "foriegn_national")
            self.is_international_applicant = 1 if foreign_national == "Yes" else 0

        # Calculate total marks and percentage
        self.total_marks_secured_in_part_a_b = (self.part_a_total_marks_scored or 0) + (self.part_b_total_marks_scored or 0)
        
        max_marks = self.total_marks or 200
        if max_marks > 0:
            # Rounding to 2 decimal places as requested
            self.percentage = flt((self.total_marks_secured_in_part_a_b / float(max_marks)) * 100.0, 2)
        else:
            self.percentage = 0

        # Update attendance_marked_on if status changes to Attended, Absent, or Rescheduled
        doc_before = self.get_doc_before_save()
        if not self.is_new():
            if doc_before and self.entrance_test_status != doc_before.entrance_test_status:
                if self.entrance_test_status in ["Attended", "Absent"]:
                    self.attendance_marked_on = now_datetime()

        # Update Applicant's status in DB immediately when user changes to Scheduled/Rescheduled/Absent (same transaction = fast, no refresh needed).
        if self.applicant and self.entrance_test_status in ("Scheduled", "Rescheduled", "Absent"):
            status_actually_changed = (
                self.is_new()
                or (doc_before and doc_before.entrance_test_status != self.entrance_test_status)
            )
            if status_actually_changed:
                _update_applicant_status_for_entrance_test_status(
                    self.applicant, self.entrance_test_status
                )

        # Update Applicant's status based on Result Status
        if self.applicant and self.result_status:
            status_actually_changed = (
                self.is_new()
                or (doc_before and doc_before.result_status != self.result_status)
            )
            if status_actually_changed:
                _update_applicant_status_for_result_status(self.applicant, self.result_status)

        # Fetch categories from Applicant if newly set or empty
        # Priority: Seat Allocation category (if already filled) vs Applicant's categories
        if self.applicant and (not self.category or self.is_new()):
            from slcm.admission.doctype.applicant.applicant import Applicant
            app_doc = frappe.get_doc("Applicant", self.applicant)
            app_categories = app_doc._get_applicant_categories()
            # Re-initialize the child table ONLY if it's currently empty
            if not self.category:
                for cat in app_categories:
                    self.append("category", {"category": cat})

    def generate_result_card(self):
        """Generates the dummy URL for Entrance Test Result Card."""
        try:
            dummy_url = f"/api/method/slcm.www.eligibility.entrance_test_seat_allocation.download_result_card?allocation_name={self.name}"
            self.db_set("entrance_test_result_card", dummy_url)
            return dummy_url
        except Exception:
            frappe.log_error(traceback.format_exc(), f"Result Card Dummy URL Generation Failed: {self.name}")
            return None

    def _generate_physical_result_card(self):
        """Generates the actual Entrance Test Result Card PDF using the 'Entrance Test Result Card' print format."""
        try:
            if self.entrance_test_result_card and self.entrance_test_result_card.startswith("/private/files/"):
                old_file_url = self.entrance_test_result_card
                frappe.db.delete("File", {"file_url": old_file_url})
            
            frappe.flags.ignore_print_permissions = True
            pdf_content = frappe.get_print(
                self.doctype,
                self.name,
                "Entrance Test Result Card",
                as_pdf=True
            )
            
            filename = f"Result_Card_{self.applicant.replace('/', '_')}.pdf"
            _file = frappe.get_doc({
                "doctype": "File",
                "file_name": filename,
                "attached_to_doctype": self.doctype,
                "attached_to_name": self.name,
                "content": pdf_content,
                "is_private": 1
            })
            _file.save(ignore_permissions=True)
            
            self.db_set("entrance_test_result_card", _file.file_url)
            frappe.db.commit()
            return _file.file_url
            
        except Exception:
            frappe.log_error(traceback.format_exc(), f"Result Card Generation Failed: {self.name}")
            return None

    def on_update(self):
        # Regenerate Admit Card if any relevant fields are changed or if it hasn't been generated yet
        is_rescheduled = (self.is_rescheduled == 1 or self.entrance_test_status == "Rescheduled")
        status = self.re_allocation_status if is_rescheduled else self.allocation_status
        field_to_update = "re_admit_card_download" if is_rescheduled else "admit_card_download"
        
        if status in ["Allocated", "Reallocated"]:
            doc_before = self.get_doc_before_save()
            should_regenerate = False
            
            if not getattr(self, field_to_update):
                should_regenerate = True
            elif doc_before:
                fields_to_check = [
                    "candidate_name", "gender", "date_of_birth", "email",
                    "entrance_test_name", "entrance_test_provider", "center_name",
                    "center_address", "room_code", "room_name", "building", "floor",
                    "seat_number", "allocation_status", "allocation_date", "start_time", "end_time",
                    "re_entrance_test_name", "re_entrance_test_provider", "re_center_name",
                    "re_center_address", "re_room_code", "re_room_name", "re_building", "re_floor",
                    "re_seat_number", "re_allocation_status", "re_allocation_date",
                    "campus", "academic_year", "admission_cycle", "program"
                ]
                for f in fields_to_check:
                    if self.get(f) != doc_before.get(f):
                        should_regenerate = True
                        break
                        
            if should_regenerate and not self.flags.ignore_admit_card_generation:
                from slcm.admission.doctype.entrance_test_list.entrance_test_list import generate_and_store_admit_card
                generate_and_store_admit_card(self, is_rescheduled=is_rescheduled)

        doc_before = self.get_doc_before_save()
        # (Result Card generation is now handled explicitly via bulk_generate_result_cards)

def _update_applicant_status_for_entrance_test_status(applicant_name, entrance_test_status):
    """
    Update Applicant's status (Applicant Status doctype) when
    Entrance Test Seat Allocation's entrance_test_status is Scheduled, Rescheduled, or Absent.
    - Scheduled / Rescheduled \u2192 "Entrance Test Scheduled"
    - Absent \u2192 "Entrance Test Rejected"
    """
    status_map = {
        "Scheduled": "Entrance Test Scheduled",
        "Rescheduled": "Entrance Test Scheduled",
        "Absent": "Entrance Test Rejected",
    }
    new_status = status_map.get(entrance_test_status)
    if not new_status:
        return
    if not frappe.db.exists("Applicant Status", new_status):
        frappe.log_error(
            message=f"Applicant Status '{new_status}' does not exist. Create it in Applicant Status doctype.",
            title="Applicant Status Sync Skipped",
        )
        return
    app_doc = frappe.get_doc("Applicant", applicant_name)
    if app_doc.status != new_status:
        old_status = app_doc.status
        app_doc.status = new_status
        app_doc.flags.old_status = old_status
        app_doc.save(ignore_permissions=True)
    frappe.clear_document_cache("Applicant", applicant_name)
    # Notify clients so the Applicant form can auto-refresh if open
    frappe.publish_realtime(
        "applicant_status_updated",
        {"docname": applicant_name, "status": new_status},
    )

def _update_applicant_status_for_result_status(applicant_name, result_status):
    """
    Update Applicant's status (Applicant Status doctype) when
    Entrance Test Seat Allocation's result_status is set.
    - Pass \u2192 "Entrance Test Completed"
    - Fail / Absent / Withheld / Disqualified \u2192 "Entrance Test Rejected"
    """
    new_status = "Entrance Test Completed" if result_status == "Pass" else "Entrance Test Rejected"
    
    if not frappe.db.exists("Applicant Status", new_status):
        frappe.log_error(
            message=f"Applicant Status '{new_status}' does not exist. Create it in Applicant Status doctype.",
            title="Applicant Status Sync Skipped (Result Status)",
        )
        return
    frappe.db.set_value("Applicant", applicant_name, "status", new_status)
    frappe.clear_document_cache("Applicant", applicant_name)
    # Notify clients
    frappe.publish_realtime(
        "applicant_status_updated",
        {"docname": applicant_name, "status": new_status},
    )


@frappe.whitelist()
def bulk_download_all_records(names):
    """
    Creates a ZIP archive containing ALL available documents (Admit Cards and Result Cards)
    for the selected records. Organized by applicant ID folders.
    """
    import io
    import os
    import zipfile
    from frappe.utils.file_manager import save_file, get_file_path

    if isinstance(names, str):
        names = frappe.parse_json(names)

    if not names:
        frappe.throw("No records selected for download.")

    total = len(names)
    zip_buffer = io.BytesIO()
    found_files = 0

    frappe.publish_progress(0, title=_("Bulk Download"), description=_("Starting..."))

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
        for idx, name in enumerate(names, start=1):
            doc = frappe.get_doc("Entrance Test Seat Allocation", name)
            applicant_id = doc.applicant or doc.name

            pct = int((idx / total) * 100)
            frappe.publish_progress(
                pct,
                title=_("Bulk Download"),
                description=_("Processing {0} of {1}: {2}").format(idx, total, applicant_id)
            )
            
            def add_admit_to_zip(field, suffix=""):
                nonlocal found_files
                
                file_url = getattr(doc, field)
                fpath = None
                
                if file_url and file_url.startswith("/private/files/"):
                    fname = file_url.split('/')[-1]
                    fpath = get_file_path(fname)
                    
                # If there is no URL, or if it is a dynamic API URL, or the physical file is missing
                if not file_url or file_url.startswith("/api/method/") or (fpath and not os.path.exists(fpath)):
                    from slcm.admission.doctype.entrance_test_list.entrance_test_list import generate_and_store_admit_card
                    is_re = (field == "re_admit_card_download")
                    file_url = generate_and_store_admit_card(doc, is_rescheduled=is_re)
                    doc.reload()
                    
                    if file_url and file_url.startswith("/private/files/"):
                        fname = file_url.split('/')[-1]
                        fpath = get_file_path(fname)
                
                if file_url and fpath and os.path.exists(fpath):
                    zip_path = f"{applicant_id}/Admit_Card{suffix}.pdf"
                    zip_file.write(fpath, arcname=zip_path)
                    found_files += 1

            # Process Admit Cards
            if doc.allocation_status in ["Allocated", "Reallocated"]:
                add_admit_to_zip("admit_card_download")
            if doc.is_rescheduled and doc.re_allocation_status in ["Allocated", "Reallocated"]:
                add_admit_to_zip("re_admit_card_download", suffix="_Rescheduled")

            # Result Card — only if result is declared or at least one score exists
            if doc.result_status or doc.total_marks_secured_in_part_a_b:
                if not doc.entrance_test_result_card:
                    doc.generate_result_card()
                
                file_url = doc.entrance_test_result_card
                fpath = None
                
                if file_url and file_url.startswith("/private/files/"):
                    fname = file_url.split('/')[-1]
                    fpath = get_file_path(fname)
                    
                if not file_url or file_url.startswith("/api/method/") or (fpath and not os.path.exists(fpath)):
                    file_url = doc._generate_physical_result_card()
                    if file_url and file_url.startswith("/private/files/"):
                        fname = file_url.split('/')[-1]
                        fpath = get_file_path(fname)

                if file_url and fpath and os.path.exists(fpath):
                    zip_path = f"{applicant_id}/Entrance_Test_Result_Card.pdf"
                    zip_file.write(fpath, arcname=zip_path)
                    found_files += 1

    frappe.publish_progress(100, title=_("Bulk Download"), description=_("Finalizing archive..."))

    if found_files == 0:
        frappe.throw("No documents (Admit Cards or Results) found for the selected records.")

    zip_filename = f"Bulk_Admission_Records_{frappe.utils.now_datetime().strftime('%Y%m%d_%H%M%S')}.zip"
    
    saved_zip = save_file(
        zip_filename,
        zip_buffer.getvalue(),
        "Entrance Test Seat Allocation",
        names[0],
        is_private=1
    )

    return saved_zip.file_url


@frappe.whitelist()
def download_centre_list_excel(
    academic_year=None,
    admission_cycle=None,
    program_level=None,
    program=None,
    applicant_type=None,
    entrance_test_city=None,
    center_name=None
):
    """
    Generates per-centre Excel sheets (one sheet = one centre) bundled in a single ZIP.

    Columns per sheet:
        Candidate Name, Programme, Email, Gender,
        Entrance Test Name, Entrance Test Provider,
        Centre Name, Centre Address, Admit Card Number,
        Entrance Test Status, Part-A Total Mark Scored, Part-A All India Rank,
        Part-A Shortlisted Status, Part-B Total Marks Scored, Part-B All India Rank,
        Total Marks Secured (Part A+B), Percentage, Cumulative Rank,
        Entrance Test Percentile, Status (Result), Admission Status
    """
    import io
    import zipfile
    import xlsxwriter
    from frappe.utils.file_manager import save_file

    # ── Filters ────────────────────────────────────────────────────────────────
    filters = {}
    if academic_year:
        filters["academic_year"] = academic_year
    if admission_cycle:
        filters["admission_cycle"] = admission_cycle
    if program_level:
        filters["program_level"] = program_level
    if program:
        filters["program"] = program
    if applicant_type == "Domestic Applicants":
        filters["is_international_applicant"] = 0
    elif applicant_type == "International Applicants":
        filters["is_international_applicant"] = 1

    # Resolve city → centres filter supporting multi-select
    cities = _parse_multi_arg(entrance_test_city)
    centres = _parse_multi_arg(center_name)

    if cities:
        city_providers = frappe.get_all(
            "Entrance Test Provider",
            filters={"city": ["in", cities]},
            fields=["center_name"],
            limit_page_length=0
        )
        city_centres = list({p.center_name for p in city_providers if p.center_name})
        if city_centres:
            if centres:
                valid_centres = [c for c in centres if c in city_centres]
                if valid_centres:
                    filters["center_name"] = ["in", valid_centres] if len(valid_centres) > 1 else valid_centres[0]
                else:
                    filters["center_name"] = "__none__"
            else:
                filters["center_name"] = ["in", city_centres] if len(city_centres) > 1 else city_centres[0]
        else:
            filters["center_name"] = "__none__"
    elif centres:
        filters["center_name"] = ["in", centres] if len(centres) > 1 else centres[0]

    # ── Fetch Records ──────────────────────────────────────────────────────────
    records = frappe.get_all(
        "Entrance Test Seat Allocation",
        filters=filters,
        fields=[
            "name", "applicant", "candidate_name", "program", "email", "gender",
            "entrance_test_name", "entrance_test_provider",
            "center_name", "center_address", "admit_card_number",
            # Result tab fields (exclude result_published)
            "entrance_test_status",
            "part_a_total_marks_scored", "part_a_all_india_rank", "shortlisted_status",
            "part_b_total_marks_scored", "part_b_all_india_rank",
            "total_marks_secured_in_part_a_b", "percentage", "entrance_test_rank",
            "percentile", "result_status", "admission_status"
        ],
        order_by="center_name asc, candidate_name asc"
    )

    if not records:
        frappe.throw(_("No applicant records found matching the selected filters."))

    # ── Build center_name → city lookup from Entrance Test Provider ────────────
    all_providers = frappe.get_all(
        "Entrance Test Provider",
        fields=["center_name", "city"],
        limit_page_length=0
    )
    centre_to_city = {
        p.center_name: (p.city or "Unassigned").strip()
        for p in all_providers
    }

    # ── Group: City → Centre → [records] ──────────────────────────────────────
    from collections import OrderedDict
    city_groups = OrderedDict()
    for rec in records:
        c_name = (rec.center_name or "Unassigned").strip()
        city   = centre_to_city.get(c_name, "Unassigned")
        city_groups.setdefault(city, OrderedDict())
        city_groups[city].setdefault(c_name, []).append(rec)

    total_centres_count = sum(len(centres) for centres in city_groups.values())

    # ── Excel Column Definitions ───────────────────────────────────────────────
    COLUMNS = [
        ("S.No",                          10),
        ("Application Number",            20),
        ("Candidate Name",                25),
        ("Programme",                     20),
        ("Email",                         30),
        ("Gender",                        12),
        ("Entrance Test Name",            25),
        ("Entrance Test Provider",        25),
        ("Centre Name",                   25),
        ("Centre Address",                35),
        ("Admit Card Number",             20),
        # Result fields
        ("Entrance Test Status",          20),
        ("Part-A Mark Scored",            18),
        ("Part-A All India Rank",         20),
        ("Part-A Shortlisted Status",     22),
        ("Part-B Mark Scored",            18),
        ("Part-B All India Rank",         20),
        ("Total Marks (Part A+B)",        22),
        ("Percentage (%)",                15),
        ("Cumulative Rank",               16),
        ("Percentile",                    14),
        ("Result Status",                 16),
        ("Admission Status",              22),
    ]

    def _safe_path(name):
        """Strip characters not allowed in ZIP path components."""
        return (
            name
            .replace("/", "-").replace("\\", "-")
            .replace(":", "-").replace("*", "")
            .replace("?", "").replace('"', "")
            .replace("<", "").replace(">", "")
            .replace("|", "")
        ).strip() or "Unnamed"

    def _build_worksheet(workbook, centre_name_key, rows):
        """Create and populate a single worksheet for one centre."""
        safe_sheet = centre_name_key[:31].replace("/", "-").replace("\\", "-").replace(":", "-").replace("*", "-").replace("?", "-").replace("[", "(").replace("]", ")")
        worksheet = workbook.add_worksheet(safe_sheet)

        title_fmt = workbook.add_format({
            "bold": True, "font_size": 13,
            "bg_color": "#1E3A8A", "font_color": "#FFFFFF",
            "align": "center", "valign": "vcenter", "border": 1
        })
        header_fmt = workbook.add_format({
            "bold": True, "bg_color": "#1E40AF", "font_color": "#FFFFFF",
            "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True
        })
        cell_fmt = workbook.add_format({"border": 1, "valign": "vcenter"})
        num_fmt  = workbook.add_format({"border": 1, "num_format": "0.00", "valign": "vcenter"})
        int_fmt  = workbook.add_format({"border": 1, "num_format": "0", "valign": "vcenter"})
        alt_cell = workbook.add_format({"border": 1, "valign": "vcenter", "bg_color": "#EFF6FF"})
        alt_num  = workbook.add_format({"border": 1, "num_format": "0.00", "valign": "vcenter", "bg_color": "#EFF6FF"})
        alt_int  = workbook.add_format({"border": 1, "num_format": "0", "valign": "vcenter", "bg_color": "#EFF6FF"})

        num_cols = len(COLUMNS)
        worksheet.merge_range(0, 0, 0, num_cols - 1,
            f"Centre: {centre_name_key}  |  Total Applicants: {len(rows)}", title_fmt)
        worksheet.set_row(0, 22)

        for col_idx, (col_label, col_width) in enumerate(COLUMNS):
            worksheet.write(1, col_idx, col_label, header_fmt)
            worksheet.set_column(col_idx, col_idx, col_width)
        worksheet.set_row(1, 32)

        float_cols = {12, 15, 17, 18, 20}
        int_cols   = {13, 16, 19}

        for row_idx, rec in enumerate(rows, start=2):
            is_alt    = (row_idx % 2 == 0)
            base_cell = alt_cell if is_alt else cell_fmt
            base_num  = alt_num  if is_alt else num_fmt
            base_int  = alt_int  if is_alt else int_fmt

            row_data = [
                row_idx - 1,
                rec.applicant or rec.name,
                rec.candidate_name or "",
                rec.program or "",
                rec.email or "",
                rec.gender or "",
                rec.entrance_test_name or "",
                rec.entrance_test_provider or "",
                rec.center_name or "",
                rec.center_address or "",
                rec.admit_card_number or "",
                rec.entrance_test_status or "",
                rec.part_a_total_marks_scored or 0,
                rec.part_a_all_india_rank or 0,
                rec.shortlisted_status or "",
                rec.part_b_total_marks_scored or 0,
                rec.part_b_all_india_rank or 0,
                rec.total_marks_secured_in_part_a_b or 0,
                rec.percentage or 0,
                rec.entrance_test_rank or 0,
                rec.percentile or 0,
                rec.result_status or "",
                rec.admission_status or "",
            ]

            for col_idx, val in enumerate(row_data):
                if col_idx in float_cols:
                    worksheet.write_number(row_idx, col_idx, float(val or 0), base_num)
                elif col_idx in int_cols:
                    worksheet.write_number(row_idx, col_idx, int(val or 0), base_int)
                else:
                    worksheet.write(row_idx, col_idx, str(val) if val is not None else "", base_cell)

    # ── Build ZIP: City/Centre.xlsx ────────────────────────────────────────────
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
        for city_name in sorted(city_groups.keys()):
            centres_in_city = city_groups[city_name]
            safe_city = _safe_path(city_name)

            for centre_name_key in sorted(centres_in_city.keys()):
                rows = centres_in_city[centre_name_key]

                wb_buffer = io.BytesIO()
                workbook  = xlsxwriter.Workbook(wb_buffer, {"constant_memory": True, "in_memory": True})
                _build_worksheet(workbook, centre_name_key, rows)
                workbook.close()

                safe_centre = _safe_path(centre_name_key)
                # Path inside ZIP: CityName/CentreName.xlsx
                zip_entry = f"{safe_city}/{safe_centre}.xlsx"
                zip_file.writestr(zip_entry, wb_buffer.getvalue())


    # ── Save & Return ZIP ──────────────────────────────────────────────────────
    ts = frappe.utils.now_datetime().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"Centre_List_{ts}.zip"

    # Attach to the first matching record (arbitrary anchor)
    anchor = records[0].name if records else "Entrance Test Seat Allocation"
    saved = save_file(
        zip_filename,
        zip_buffer.getvalue(),
        "Entrance Test Seat Allocation",
        anchor,
        is_private=1
    )

    return {
        "file_url": saved.file_url,
        "filename": zip_filename,
        "total_centres": total_centres_count,
        "total_applicants": len(records)
    }


@frappe.whitelist()
def get_centre_list_preview(
    academic_year=None,
    admission_cycle=None,
    program_level=None,
    program=None,
    applicant_type=None,
    center_name=None,
    entrance_test_city=None
):
    """
    Returns a lightweight preview for the Centre List Download dialog:
    { total_applicants: int, total_cities: int, centres: [{ name: str, count: int }, ...] }
    """
    # Build center_name → city lookup
    all_providers = frappe.get_all(
        "Entrance Test Provider",
        fields=["center_name", "city"],
        limit_page_length=0
    )
    centre_to_city = {p.center_name: (p.city or "Unassigned").strip() for p in all_providers}

    filters = {}
    if academic_year:
        filters["academic_year"] = academic_year
    if admission_cycle:
        filters["admission_cycle"] = admission_cycle
    if program_level:
        filters["program_level"] = program_level
    if program:
        filters["program"] = program

    if applicant_type == "Domestic Applicants":
        filters["is_international_applicant"] = 0
    elif applicant_type == "International Applicants":
        filters["is_international_applicant"] = 1

    # Resolve city → centres filter
    cities = _parse_multi_arg(entrance_test_city)
    centres = _parse_multi_arg(center_name)

    if cities:
        city_providers = [p.center_name for p in all_providers if (p.city or "").strip() in cities and p.center_name]
        if city_providers:
            if centres:
                valid_centres = [c for c in centres if c in city_providers]
                if valid_centres:
                    filters["center_name"] = ["in", valid_centres] if len(valid_centres) > 1 else valid_centres[0]
                else:
                    filters["center_name"] = "__none__"
            else:
                filters["center_name"] = ["in", city_providers] if len(city_providers) > 1 else city_providers[0]
        else:
            return {"total_applicants": 0, "total_cities": 0, "centres": []}
    elif centres:
        filters["center_name"] = ["in", centres] if len(centres) > 1 else centres[0]

    records = frappe.get_all(
        "Entrance Test Seat Allocation",
        filters=filters,
        fields=["name", "center_name"],
        order_by="center_name asc"
    )

    if not records:
        return {"total_applicants": 0, "total_cities": 0, "centres": []}

    # Group by centre name and count unique cities
    counts = {}
    cities_seen = set()
    for r in records:
        key = (r.center_name or "Unassigned").strip()
        counts[key] = counts.get(key, 0) + 1
        cities_seen.add(centre_to_city.get(key, "Unassigned"))

    centres = [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: x[0])]

    return {
        "total_applicants": len(records),
        "total_cities": len(cities_seen),
        "centres": centres
    }


@frappe.whitelist()
def get_cities_for_filter(academic_year=None, admission_cycle=None):
    """
    Returns the list of Entrance Test City names that have at least one
    Entrance Test Provider with records in the current ETSA data.
    Used to populate the City filter dropdown in the Centre List Download dialog.
    """
    # Get all distinct center_names for the given AY + AC
    et_filters = {}
    if academic_year:
        et_filters["academic_year"] = academic_year
    if admission_cycle:
        et_filters["admission_cycle"] = admission_cycle

    centre_records = frappe.get_all(
        "Entrance Test Seat Allocation",
        filters=et_filters,
        fields=["center_name"],
        distinct=True,
        limit_page_length=0
    )
    centre_names = list({r.center_name for r in centre_records if r.center_name})

    if not centre_names:
        return {"cities": []}

    # Look up city for each centre via Entrance Test Provider
    providers = frappe.get_all(
        "Entrance Test Provider",
        filters={"center_name": ["in", centre_names]},
        fields=["center_name", "city"],
        limit_page_length=0
    )
    cities = sorted({(p.city or "").strip() for p in providers if (p.city or "").strip()})

    return {"cities": cities}


@frappe.whitelist()
def update_ranks_by_category(academic_year, admission_cycle, program_level, entrance_test_list=None, program=None, applicant_type=None):
    """
    Ranks applicants based on total_marks_secured_in_part_a_b for a given batch and sends result emails.
    Filters: Academic Year, Admission Cycle, Program Level.
    Optional: entrance_test_list, program, applicant_type
    """
    if not (academic_year and admission_cycle and program_level):
        frappe.throw("Academic Year, Admission Cycle, and Program Level are required for ranking.")

    # 1. Rank Attended applicants
    attended_filters = {
        "academic_year": academic_year,
        "admission_cycle": admission_cycle,
        "program_level": program_level,
        "entrance_test_status": "Attended"
    }
    if program:
        attended_filters["program"] = program
    if entrance_test_list:
        attended_filters["entrance_test_list"] = entrance_test_list
    if applicant_type == "Domestic Applicants":
        attended_filters["is_international_applicant"] = 0
    elif applicant_type == "International Applicants":
        attended_filters["is_international_applicant"] = 1

    attended_records = frappe.get_all("Entrance Test Seat Allocation",
        filters=attended_filters,
        fields=["name", "part_a_total_marks_scored", "part_b_total_marks_scored", "total_marks_secured_in_part_a_b"],
        order_by="total_marks_secured_in_part_a_b desc"
    )

    total_attended = len(attended_records)
    if total_attended == 0:
        return 0

    # --- Helper to calculate ranks and percentiles ---
    def calculate_ranks_and_percentiles(records, score_fieldname):
        # Sort by score desc
        sorted_recs = sorted(records, key=lambda x: flt(x.get(score_fieldname)), reverse=True)
        
        results = {}
        last_score = None
        current_rank = 0
        total_students = len(sorted_recs)
        
        for i, rec in enumerate(sorted_recs, start=1):
            score = flt(rec.get(score_fieldname))
            if last_score is None or score != last_score:
                current_rank = i
                last_score = score
            
            # Standard competitive exam percentile logic:
            # Top rank (1) gets 100 percentile.
            # If total_students == 1, they get 100.
            # Same score -> Same Rank -> Same Percentile.
            if total_students <= 1:
                percentile = 100.0
            else:
                percentile = ((total_students - current_rank) / float(total_students - 1)) * 100.0
            
            # Round to 2 decimal places for standard display
            percentile = round(percentile, 2)
            
            results[rec.name] = {
                "rank": current_rank,
                "percentile": percentile
            }
        return results

    frappe.publish_progress(10, title=_("Update Ranking"), description=_("Calculating scores and percentiles..."))

    # 1.1 Perform ranking passes
    part_a_data = calculate_ranks_and_percentiles(attended_records, "part_a_total_marks_scored")
    part_b_data = calculate_ranks_and_percentiles(attended_records, "part_b_total_marks_scored")
    cumulative_data = calculate_ranks_and_percentiles(attended_records, "total_marks_secured_in_part_a_b")

    # 1.2 Update records in bulk (no per-doc load – much faster)
    for i, rec in enumerate(attended_records, start=1):
        rank_a = part_a_data.get(rec.name, {}).get("rank") or 0
        rank_b = part_b_data.get(rec.name, {}).get("rank") or 0
        rank_cum = cumulative_data.get(rec.name, {}).get("rank") or 0
        percentile = cumulative_data.get(rec.name, {}).get("percentile") or 0.0

        frappe.db.set_value("Entrance Test Seat Allocation", rec.name, {
            "part_a_all_india_rank": rank_a,
            "part_b_all_india_rank": rank_b,
            "entrance_test_rank": rank_cum,
            "percentile": percentile
        }, update_modified=False)

        percent = 10 + int((i / total_attended) * 90)
        frappe.publish_progress(
            percent,
            title=_("Update Ranking"),
            description=_("Ranked {0} of {1}").format(i, total_attended)
        )

    frappe.db.commit()

    # 1.3 Clear ranks and percentiles for Absent/Non-attended applicants (bulk)
    absent_filters = attended_filters.copy()
    absent_filters["entrance_test_status"] = ["!=", "Attended"]
    absent_records = frappe.get_all("Entrance Test Seat Allocation", filters=absent_filters, fields=["name"])

    for rec in absent_records:
        frappe.db.set_value("Entrance Test Seat Allocation", rec.name, {
            "part_a_all_india_rank": 0,
            "part_b_all_india_rank": 0,
            "entrance_test_rank": 0,
            "percentile": 0.0
        }, update_modified=False)

    frappe.db.commit()
    return total_attended


@frappe.whitelist()
def bulk_generate_result_cards(academic_year, admission_cycle, program_level=None, program=None, applicant_type=None):
    """
    Bulk generates Result Card PDFs for Attended applicants matching the given filters.
    """
    if not (academic_year and admission_cycle):
        frappe.throw(_("Academic Year and Admission Cycle are required."))

    filters = {
        "academic_year": academic_year,
        "admission_cycle": admission_cycle,
        "entrance_test_status": ["in", ["Attended", "Absent"]]
    }
    if program_level:
        filters["program_level"] = program_level
    if program:
        filters["program"] = program
    if applicant_type == "Domestic Applicants":
        filters["is_international_applicant"] = 0
    elif applicant_type == "International Applicants":
        filters["is_international_applicant"] = 1

    records = frappe.get_all(
        "Entrance Test Seat Allocation",
        filters=filters,
        fields=["name"]
    )

    total = len(records)
    if total == 0:
        frappe.throw(_("No matching records found to generate result cards."))

    count = 0
    for i, rec in enumerate(records, start=1):
        frappe.publish_progress(
            (i / total) * 100,
            title=_("Generating Result Cards"),
            description=_("Generating {0} of {1}").format(i, total)
        )
        
        doc = frappe.get_doc("Entrance Test Seat Allocation", rec.name)
        try:
            doc.generate_result_card()
            count += 1
        except Exception:
            frappe.log_error(title=f"Result Card Generation Failed: {doc.name}")

    return {"generated": count}


@frappe.whitelist()
def publish_results(academic_year, admission_cycle, program_level=None, program=None, entrance_test_list=None, applicant_type=None, send_email=0, email_format="Default", custom_email_content=None, selected_names=None):
    """
    Sets result_published = 1 for all Entrance Test Seat Allocation records
    matching the given filters (Attended applicants) in bulk.
    Also queues result notification emails for each record.
    """
    if not (academic_year and admission_cycle):
        frappe.throw(_("Academic Year and Admission Cycle are required."))

    import json
    selected_list = []
    if selected_names:
        selected_list = json.loads(selected_names)

    filters = {
        "academic_year": academic_year,
        "admission_cycle": admission_cycle,
        "entrance_test_status": ["in", ["Attended", "Absent"]]
    }
    
    if program_level:
        filters["program_level"] = program_level
    if program:
        filters["program"] = program
    if entrance_test_list:
        filters["entrance_test_list"] = entrance_test_list
    if applicant_type == "Domestic Applicants":
        filters["is_international_applicant"] = 0
    elif applicant_type == "International Applicants":
        filters["is_international_applicant"] = 1

    if selected_list:
        filters["name"] = ["in", selected_list]

    records = frappe.get_all(
        "Entrance Test Seat Allocation",
        filters=filters,
        fields=["name", "applicant", "candidate_name", "email",
                "entrance_test_status", "total_marks_secured_in_part_a_b",
                "entrance_test_rank", "entrance_test_list", "entrance_test_result_card"]
    )

    total = len(records)
    if total == 0:
        frappe.throw(_("No matching records found to publish."))

    count = 0
    for i, rec in enumerate(records, start=1):
        frappe.publish_progress(
            (i / total) * 100,
            title=_("Publishing Results"),
            description=_("Generating & publishing {0} of {1}").format(i, total)
        )

        # Load full doc (needed for generate_result_card + email)
        doc = frappe.get_doc("Entrance Test Seat Allocation", rec.name)

        # Mark as published
        doc.db_set("result_published", 1, update_modified=False)

        # Resolve email
        email = doc.email or ""
        if not email and doc.applicant:
            try:
                email = frappe.db.get_value("Applicant", doc.applicant, "email") or ""
            except Exception:
                pass

        if int(send_email) == 1 and email:
            try:
                if email_format == "Custom":
                    _send_custom_result_email(doc, email, custom_email_content)
                    _send_result_notification(doc, email)
                    count += 1
                else:
                    _send_result_notification_email(doc, email)
                    _send_result_notification(doc, email)
                    count += 1
            except Exception:
                frappe.log_error(title=f"Publish Result Email Failed: {doc.name}")

        if i % 50 == 0:
            frappe.db.commit()

    frappe.db.commit()
    return {"published": total, "notified": count}


def get_custom_email_html(custom_content):
    header = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Merriweather:ital,wght@0,300;0,400;0,700;1,300;1,400;1,700&display=swap" rel="stylesheet">
    <style>
        /* Base reset for email clients */
        body { margin: 0; padding: 0; background-color: #ffffff; font-family: 'Merriweather', serif; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }
        table, td { mso-table-lspace: 0pt; mso-table-rspace: 0pt; border-collapse: collapse !important; }
        img { border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; }
        
        /* Responsive overrides */
        @media only screen and (max-width: 600px) {
            .container { width: 100% !important; min-width: 100% !important; }
            .mobile-header-padding { padding: 30px 20px 15px 20px !important; }
            .logo-img { height: 42px !important; width: auto !important; }
            .univ-name, .campus-name { font-size: 16px !important; line-height: 1.2 !important; white-space: nowrap !important; }
            .body-content { padding: 20px 20px !important; }
        }
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: #ffffff; font-family: 'Merriweather', serif;">
    <!-- Gmail mobile auto-shrink fix -->
    <div style="display:none; white-space:nowrap; font:15px courier; line-height:0;">
        &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp;
    </div>

    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="width: 100%; background-color: #ffffff; table-layout: fixed;">
        <!-- Header Section -->
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" border="0" class="container" style="max-width: 600px; width: 100%;">
                    <tr>
                        <td style="padding: 40px 40px 15px 40px;" class="mobile-header-padding">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="width: 100%;">
                                <tr>
                                    <!-- Logo Cell -->
                                    <td width="1" style="vertical-align: middle; padding-right: 20px;">
                                        {% set inst_logo = frappe.db.get_single_value('Institution Settings', 'logo') %}
                                        {% if inst_logo %}
                                            <img src="{{ frappe.utils.get_url(inst_logo) }}" alt="Logo" class="logo-img" style="height: 52px; width: auto; display: block; border: 0;">
                                        {% else %}
                                            <div style="width: 40px; height: 40px; background-color: #f3f4f6; border-radius: 4px;"></div>
                                        {% endif %}
                                    </td>
                                    <!-- Title Cell -->
                                    <td style="vertical-align: middle; text-align: left;">
                                        <div class="univ-name" style="font-family: 'Merriweather', serif; font-size: 20px; color: #920c24; line-height: 1.25; font-weight: 400; margin: 0; white-space: nowrap;">
                                            National Law School of India University
                                        </div>
                                        <div style="border-top: 1.5px solid #920c24; margin: 5px 0; padding: 0; font-size: 0px; line-height: 0px;">&nbsp;</div>
                                        <div class="campus-name" style="font-family: 'Merriweather', serif; font-size: 20px; color: #920c24; line-height: 1.25; font-weight: 700; margin: 0; white-space: nowrap;">
                                            Bengaluru
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- Body Section -->
        <tr>
            <td align="center">
                <!-- Content Wrapper -->
                <table width="600" cellpadding="0" cellspacing="0" border="0" class="container" style="max-width: 600px; width: 100%;">
                    <!-- Body Content -->
                    <tr>
                        <td class="body-content" style="padding: 20px 40px 40px 40px; font-family: 'Merriweather', serif; font-size: 16px; line-height: 1.6; color: #333333;">
"""

    footer = """
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    return header + (custom_content or "") + footer


def _send_custom_result_email(doc, email, custom_email_content):
    """Send a custom result notification email to the applicant."""
    try:
        # Prepare arguments for Jinja
        doc_dict = doc.as_dict()
        args = {
            "doc": doc_dict,
            "portal_url": get_url("/merit-and-scholarship/admission_dashboard?panel=applications")
        }

        # Use the header (subject) and sender from the default email template
        template_name = "Entrance Test Result"
        sender = None
        if frappe.db.exists("Email Template", template_name):
            template = frappe.get_doc("Email Template", template_name)
            subject = frappe.render_template(template.subject, args)
            if template.get("email_account"):
                sender = frappe.db.get_value("Email Account", template.get("email_account"), "email_id") or template.get("email_account")
        else:
            subject = f"Entrance Test Result - {doc.entrance_test_list or doc.entrance_test_name}"
        
        # Render the custom content wrapped in the HTML header/footer template to allow variables
        full_html_template = get_custom_email_html(custom_email_content)
        message_body = frappe.render_template(full_html_template, args)

        frappe.sendmail(
            recipients=[email],
            sender=sender,
            subject=subject,
            message=message_body,
            reference_doctype="Entrance Test Seat Allocation",
            reference_name=doc.name,
            now=False
        )
        frappe.logger().info(f"Custom Entrance Test Notification Email queued successfully to {email} for {doc.name}")
    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"Custom Result Email Failed: {doc.name}")


def _send_result_notification_email(doc, email):
    """Send a result/rank notification email to the applicant using a configurable template."""
    try:
        template_name = "Entrance Test Result"
        if not frappe.db.exists("Email Template", template_name):
            frappe.log_error(f"Email Template '{template_name}' not found.", "Email Sending Error")
            return

        template = frappe.get_doc("Email Template", template_name)
        
        # Prepare arguments for Jinja
        doc_dict = doc.as_dict()
        args = {
            "doc": doc_dict,
            "portal_url": get_url("/merit-and-scholarship/admission_dashboard?panel=applications")
        }

        subject = frappe.render_template(template.subject, args)
        
        # Determine the content field correctly
        message_body = ""
        if template.get("use_html"):
            message_body = frappe.render_template(template.response_html, args)
        else:
            message_body = frappe.render_template(template.response, args)

        if not message_body:
            message_body = frappe.render_template(template.get("message") or "", args)
            
        # Robust CC handling from the manual 'cc' field added to Email Template
        cc_list = []
        cc_field_value = template.get("cc")
        if cc_field_value:
            # Split by comma or semicolon, strip whitespace, and filter out empties
            cc_list = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]
        
        if message_body:
            try:
                # Use now=False to queue the email.
                sender = None
                if template.get("email_account"):
                    sender = frappe.db.get_value("Email Account", template.get("email_account"), "email_id") or template.get("email_account")

                frappe.sendmail(
                    recipients=[email],
                    sender=sender,
                    cc=cc_list,
                    subject=subject,
                    message=message_body,
                    reference_doctype="Entrance Test Seat Allocation",
                    reference_name=doc.name,
                    now=False
                )
                frappe.logger().info(f"Entrance Test Notification Email queued successfully to {email} for {doc.name}")
            except Exception:
                frappe.log_error(traceback.format_exc(), f"Entrance Test Notification Email Queueing Failed: {doc.name}")

    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"Result Email Failed: {doc.name}")


@frappe.whitelist()
def reschedule_applicants(applicants, providers, allocation_date, reschedule_reason=None, re_entrance_test_name=None):
    if isinstance(applicants, str):
        applicants = json.loads(applicants)
    if isinstance(providers, str):
        providers = json.loads(providers)

    if not applicants:
        frappe.throw("No applicants selected.")
    if not providers:
        frappe.throw("No providers selected.")
    if not reschedule_reason:
        frappe.throw("Reason for Reschedule is mandatory.")

    # Validate allocation_date is not in the past
    if allocation_date and get_datetime(allocation_date) < now_datetime():
        frappe.throw("New Allocation Date cannot be in the past. Please select today or a future date.")

    # Validate providers
    provider_docs = []
    for pname in providers:
        pdoc = frappe.get_doc("Entrance Test Provider", pname)
        if not pdoc.active:
            frappe.throw(f"Provider '{pname}' is not active.")
        provider_docs.append(pdoc)

    count = 0
    total = len(applicants)
    for i, name in enumerate(applicants):
        # Publish progress
        percent = (float(i + 1) / total * 100)
        frappe.publish_progress(
            percent, 
            title=_("Rescheduling Applicants..."), 
            description=f"Processing {i + 1} of {total}"
        )

        doc = frappe.get_doc("Entrance Test Seat Allocation", name)


        # Update reschedule fields
        doc.is_rescheduled = 1
        doc.re_allocation_date = allocation_date
        doc.re_allocation_status = "Preferences Assigned"
        doc.rescheduled_on = now_datetime()
        doc.rescheduled_by = frappe.session.user
        doc.reschedule_reason = reschedule_reason
        doc.re_entrance_test_name = re_entrance_test_name
        doc.entrance_test_status = "Scheduled"

        # Set re_assigned_preferences
        doc.set("re_assigned_preferences", [])
        for idx, pdoc in enumerate(provider_docs, start=1):
            doc.append("re_assigned_preferences", {
                "provider": pdoc.name,
                "center_name": pdoc.center_name,
                "center_address": pdoc.center_address,
                "preference_order": idx
            })

        doc.save(ignore_permissions=True)

        # \u2500\u2500 Resolve email \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # Priority: allocation.email \u2192 Applicant doctype email
        email = doc.email or ""
        if not email and doc.applicant:
            # Try fetching from Applicant doctype
            try:
                app_email = frappe.db.get_value("Applicant", doc.applicant, "email")
                if app_email:
                    email = app_email
            except Exception:
                pass

        # \u2500\u2500 Send reschedule notification email \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        if email:
            try:
                _send_reschedule_email(doc, email)
                _send_reschedule_notification(doc, email)
            except Exception:
                frappe.log_error(
                    message=traceback.format_exc(),
                    title=f"Reschedule Email/Notification Failed: {doc.name}"
                )
        else:
            frappe.log_error(
                message=f"No email found for applicant {doc.applicant} (record: {doc.name}). Reschedule email was not sent.",
                title="Reschedule Email Skipped"
            )

        if i % 10 == 0:
            frappe.db.commit()

        count += 1

    frappe.db.commit()
    return count


def _send_reschedule_email(doc, email):
    """Send a reschedule notification email to the applicant using a configurable template."""
    try:
        template_name = "Entrance Test Reschedule"
        if not frappe.db.exists("Email Template", template_name):
            frappe.log_error(f"Email Template '{template_name}' not found.", "Email Sending Error")
            return

        template = frappe.get_doc("Email Template", template_name)
        
        # Prepare arguments for Jinja
        doc_dict = doc.as_dict()
        # Convert child table to list of dicts for Jinja
        doc_dict["re_assigned_preferences"] = [p.as_dict() for p in doc.re_assigned_preferences]
        
        args = {
            "doc": doc_dict,
            "portal_url": get_url("/merit-and-scholarship/admission_dashboard?panel=applications")
        }

        subject = frappe.render_template(template.subject, args)
        
        # Determine the content field correctly
        message_body = ""
        if template.get("use_html"):
            message_body = frappe.render_template(template.response_html, args)
        else:
            message_body = frappe.render_template(template.response, args)

        if not message_body:
            message_body = frappe.render_template(template.get("message") or "", args)
            
        # Robust CC handling from the manual 'cc' field added to Email Template
        cc_list = []
        cc_field_value = template.get("cc")
        if cc_field_value:
            # Split by comma or semicolon, strip whitespace, and filter out empties
            cc_list = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]
        
        if message_body:
            attachments = []
            if not getattr(doc, "is_international_applicant", 0):
                card_field = "re_admit_card_download" if doc.is_rescheduled else "admit_card_download"
                if not getattr(doc, card_field, None):
                    try:
                        from slcm.admission.doctype.entrance_test_list.entrance_test_list import generate_and_store_admit_card
                        generate_and_store_admit_card(doc, is_rescheduled=bool(doc.is_rescheduled))
                        doc.reload()
                    except Exception:
                        pass

                card_url = getattr(doc, card_field, None)
                if card_url:
                    try:
                        file_name = frappe.db.get_value("File", {"file_url": card_url}, "name")
                        if file_name:
                            file_doc = frappe.get_doc("File", file_name)
                            attachments.append({
                                "fname": file_doc.file_name,
                                "fcontent": file_doc.get_content()
                            })
                    except Exception:
                        pass

            try:
                # Use now=False to queue the email.
                sender = None
                if template.get("email_account"):
                    sender = frappe.db.get_value("Email Account", template.get("email_account"), "email_id") or template.get("email_account")

                frappe.sendmail(
                    recipients=[email],
                    sender=sender,
                    cc=cc_list,
                    subject=subject,
                    message=message_body,
                    attachments=attachments,
                    reference_doctype="Entrance Test Seat Allocation",
                    reference_name=doc.name,
                    now=False
                )
                frappe.logger().info(f"Entrance Test Notification Email queued successfully to {email} for {doc.name}")
            except Exception:
                frappe.log_error(traceback.format_exc(), f"Entrance Test Notification Email Queueing Failed: {doc.name}")

    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"Reschedule Email Failed: {doc.name}")


def _send_result_notification(doc, email):
    """Creates a Notification Log entry for the entrance test result."""
    if not email:
        return
    
    if frappe.db.exists("User", email):
        try:
            message_body = f"""
                <p>Your entrance test result for <strong>"{doc.entrance_test_list}"</strong> has been published.</p>
                <p>Your score: <strong>{doc.total_marks_secured_in_part_a_b}</strong></p>
                <p>Your rank: <strong>{doc.entrance_test_rank or "\u2014"}</strong></p>
                <p><a href="/merit-and-scholarship/admission_dashboard?panel=applications" style="color: #16a34a; font-weight: bold;">Click here to view details.</a></p>
            """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": "Entrance Test Result Published",
                "for_user": email,
                "type": "Alert",
                "email_content": message_body,
                "document_type": "Entrance Test Seat Allocation",
                "document_name": doc.name,
                "from_user": frappe.session.user,
                "link": "/merit-and-scholarship/admission_dashboard?panel=applications"
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(message=frappe.get_traceback(), title=f"Result Notification Failed: {doc.name}")


def _send_reschedule_notification(doc, email):
    """Creates a Notification Log entry for the rescheduled entrance test."""
    if not email:
        return
    
    if frappe.db.exists("User", email):
        try:
            message_body = f"""
                <p>Your entrance test for <strong>"{doc.entrance_test_list}"</strong> has been rescheduled.</p>
                <p>Please check your admission dashboard to view the new details and select your preferred center.</p>
                <p><a href="/merit-and-scholarship/admission_dashboard?panel=applications" style="color: #16a34a; font-weight: bold;">Click here to view details.</a></p>
            """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": "Entrance Test Rescheduled",
                "for_user": email,
                "type": "Alert",
                "email_content": message_body,
                "document_type": "Entrance Test Seat Allocation",
                "document_name": doc.name,
                "from_user": frappe.session.user,
                "link": "/merit-and-scholarship/admission_dashboard?panel=applications"
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(message=frappe.get_traceback(), title=f"Reschedule Notification Failed: {doc.name}")





@frappe.whitelist()
def get_applicant_count(academic_year=None, admission_cycle=None, program_level=None, applicant_type=None, program=None):
    """
    Returns total, attended, and absent applicant counts for Entrance Test Seat Allocation
    matching the dialog filters.
    """
    filters = {}
    if academic_year:
        filters["academic_year"] = academic_year
    if admission_cycle:
        filters["admission_cycle"] = admission_cycle
    if program_level:
        filters["program_level"] = program_level
    if program:
        filters["program"] = program

    if applicant_type == "Domestic Applicants":
        filters["is_international_applicant"] = 0
    elif applicant_type == "International Applicants":
        filters["is_international_applicant"] = 1

    total = frappe.db.count("Entrance Test Seat Allocation", filters=filters)

    filters_attended = filters.copy()
    filters_attended["entrance_test_status"] = "Attended"
    attended = frappe.db.count("Entrance Test Seat Allocation", filters=filters_attended)

    filters_absent = filters.copy()
    filters_absent["entrance_test_status"] = "Absent"
    absent = frappe.db.count("Entrance Test Seat Allocation", filters=filters_absent)

    filters_unpublished = filters.copy()
    filters_unpublished["result_published"] = 0
    filters_unpublished["entrance_test_status"] = ["in", ["Attended", "Absent"]]
    unpublished = frappe.db.count("Entrance Test Seat Allocation", filters=filters_unpublished)

    return {
        "total": total,
        "attended": attended,
        "absent": absent,
        "unpublished": unpublished
    }

@frappe.whitelist()
def get_unpublished_applicants_for_dialog(
    academic_year=None, admission_cycle=None, program_level=None, applicant_type=None, program=None,
    filter_applicant=None, filter_candidate_name=None, filter_entrance_test_status=None,
    filter_status=None, filter_admission_status=None, filter_program=None,
    limit_start=0, limit_page_length=20, fetch_all_names=0
):
    """
    Returns a paginated list of applicants whose results are not yet published.
    """
    filters = {"result_published": 0}
    
    # Main Dialog Filters
    if academic_year:
        filters["academic_year"] = academic_year
    if admission_cycle:
        filters["admission_cycle"] = admission_cycle
    if program_level:
        filters["program_level"] = program_level
    if program:
        filters["program"] = program
    if applicant_type == "Domestic Applicants":
        filters["is_international_applicant"] = 0
    elif applicant_type == "International Applicants":
        filters["is_international_applicant"] = 1
        
    # Table Specific Filters
    if filter_applicant:
        filters["applicant"] = ["like", f"%{filter_applicant}%"]
    if filter_candidate_name:
        filters["candidate_name"] = ["like", f"%{filter_candidate_name}%"]
    if filter_entrance_test_status:
        filters["entrance_test_status"] = filter_entrance_test_status
    if filter_status:
        filters["result_status"] = filter_status
    if filter_admission_status:
        filters["admission_status"] = filter_admission_status
    if filter_program:
        filters["program"] = filter_program

    if int(fetch_all_names) == 1:
        return [r.name for r in frappe.get_all("Entrance Test Seat Allocation", filters=filters, fields=["name"], order_by="creation desc")]

    # Get data
    records = frappe.get_all(
        "Entrance Test Seat Allocation",
        filters=filters,
        fields=[
            "name", "applicant", "candidate_name", 
            "entrance_test_status", "result_status", "admission_status", "program_level", "program"
        ],
        limit_start=limit_start,
        limit_page_length=limit_page_length,
        order_by="creation desc"
    )
    
    # Get total count for pagination
    total_count = frappe.db.count("Entrance Test Seat Allocation", filters=filters)
    
    # Get unique programs for dropdown before applying table-specific filters (so dropdown doesn't disappear when selected)
    # Wait, we want dropdown options based on the global filters, not table filters.
    global_filters = {"result_published": 0}
    if academic_year: global_filters["academic_year"] = academic_year
    if admission_cycle: global_filters["admission_cycle"] = admission_cycle
    if program_level: global_filters["program_level"] = program_level
    if program: global_filters["program"] = program
    if applicant_type == "Domestic Applicants": global_filters["is_international_applicant"] = 0
    elif applicant_type == "International Applicants": global_filters["is_international_applicant"] = 1
        
    unique_programs = [r.program for r in frappe.get_all(
        "Entrance Test Seat Allocation",
        filters=global_filters,
        fields=["program"],
        distinct=1
    ) if r.program]
    
    return {
        "records": records,
        "total_count": total_count,
        "unique_programs": sorted(unique_programs)
    }



@frappe.whitelist()
def reject_and_allocate_applicants(applicants, providers, allocation_type=None, send_email=1):
    if isinstance(applicants, str):
        applicants = json.loads(applicants)
    if isinstance(providers, str):
        providers = json.loads(providers)

    if not applicants:
        frappe.throw("No applicants selected.")
    if (allocation_type == "Allocate Directly" or not allocation_type) and not providers:
        frappe.throw("No providers selected.")

    # Validate providers
    provider_docs = []
    if providers:
        for pname in providers:
            pdoc = frappe.get_doc("Entrance Test Provider", pname)
            if not pdoc.active:
                frappe.throw(f"Provider '{pname}' is not active.")
            if allocation_type == "Allocate Directly" or not allocation_type:
                if pdoc.available_capacity <= 0:
                    frappe.throw(f"Provider '{pname}' has no available capacity.")
            provider_docs.append(pdoc)

    count = 0
    total = len(applicants)
    try:
        from slcm.admission.doctype.entrance_test_list.entrance_test_list import _send_allocation_email, _send_allocation_notification
    except ImportError:
        _send_allocation_email = None

    for i, name in enumerate(applicants):
        percent = round(float(i + 1) / total * 100, 1)

        doc = frappe.get_doc("Entrance Test Seat Allocation", name)

        frappe.publish_realtime(
            event="entrance_test_seat_allocation_progress",
            message={
                "progress": percent,
                "current": i + 1,
                "total": total,
                "allocated_count": count,
                "applicant_name": getattr(doc, "candidate_name", "Unknown") or "Unknown"
            },
            user=frappe.session.user
        )

        # 1. Update the existing record directly (no new record creation)
        old_provider = doc.entrance_test_provider
        if allocation_type == "Allocate Directly" or not allocation_type:
            if not provider_docs:
                frappe.throw(_("No provider selected for direct allocation."))
            pdoc = provider_docs[0]
            
            if old_provider == pdoc.name:
                continue
                
            pdoc.reload()
            if pdoc.available_capacity <= 0:
                frappe.throw(_("Not enough available capacity in {0} to allocate {1}.").format(pdoc.center_name, doc.candidate_name))
        else:
            # Allow applicant selection - we don't strictly need a provider
            pass
        
        # Revert old provider capacity if one existed

        if old_provider:
            try:
                old_pdoc = frappe.get_doc("Entrance Test Provider", old_provider)
                updated = False
                if hasattr(old_pdoc, "programme_capacity") and old_pdoc.programme_capacity and doc.program:
                    for r in old_pdoc.programme_capacity:
                        if r.program == doc.program:
                            r.reserved_seats = max(0, (r.reserved_seats or 0) - 1)
                            updated = True
                            break
                if not updated:
                    old_pdoc.reserved_seats = max(0, (old_pdoc.reserved_seats or 0) - 1)
                
                old_pdoc.calculate_capacity()
                old_pdoc.save(ignore_permissions=True)
            except Exception:
                pass

        # Capture the old centre name before modifying
        old_center_name = doc.center_name or ""

        if allocation_type == "Allocate Directly" or not allocation_type:
            doc.allocation_status = "Allocated"
            doc.entrance_test_status = "Scheduled"
        else:
            doc.allocation_status = "Not Allocated"
            doc.entrance_test_status = "Not Scheduled"

        doc.result_status = ""
        doc.result_published = 0
        doc.part_a_total_marks_scored = 0
        doc.part_b_total_marks_scored = 0
        doc.total_marks_secured_in_part_a_b = 0
        doc.percentile = 0
        doc.entrance_test_rank = 0
        doc.part_a_all_india_rank = 0
        doc.part_b_all_india_rank = 0
        doc.admit_card_generated = 0
        doc.admit_card_download = None
        doc.admit_card_number = None
        doc.entrance_test_result_card = None

        # Assign first provider (direct allocation)
        if allocation_type == "Allocate Directly" or not allocation_type:
            doc.entrance_test_provider = pdoc.name
            doc.center_name = pdoc.center_name
            doc.center_address = pdoc.center_address
            
            # Compute new seat number based on provider's current reserved_seats + 1
            new_reserved = (pdoc.reserved_seats or 0) + 1
            doc.seat_number = f"{new_reserved:02d}"
            
            try:
                from slcm.admission.doctype.entrance_test_list.entrance_test_list import _generate_admit_card_number
                admit_card_number = _generate_admit_card_number(doc, is_rescheduled=False)
                if admit_card_number:
                    doc.admit_card_number = admit_card_number
            except Exception:
                pass
        else:
            doc.entrance_test_provider = None
            doc.center_name = None
            doc.center_address = None
            doc.seat_number = None

        doc.set("assigned_preferences", [])
        if provider_docs:
            for idx, p in enumerate(provider_docs, start=1):
                doc.append("assigned_preferences", {
                    "provider": p.name,
                    "center_name": p.center_name,
                    "center_address": p.center_address,
                    "preference_order": idx
                })

        # Prevent on_update hook from synchronously generating the admit card
        doc.flags.ignore_admit_card_generation = True
        doc.save(ignore_permissions=True)
        
        # Assign a dynamic URL for lazy PDF generation
        if allocation_type == "Allocate Directly" or not allocation_type:
            dummy_url = f"/api/method/slcm.www.eligibility.entrance_test_seat_allocation.download_admit_card?allocation_name={doc.name}"
            frappe.db.set_value(doc.doctype, doc.name, "admit_card_download", dummy_url)

        # 2. Decrement capacity for the chosen provider only if Allocated Directly
        if allocation_type == "Allocate Directly" or not allocation_type:
            updated = False
            if hasattr(pdoc, "programme_capacity") and pdoc.programme_capacity and doc.program:
                for r in pdoc.programme_capacity:
                    if r.program == doc.program:
                        r.reserved_seats = (r.reserved_seats or 0) + 1
                        updated = True
                        break
            if not updated:
                pdoc.reserved_seats = (pdoc.reserved_seats or 0) + 1

            pdoc.calculate_capacity()
            pdoc.save(ignore_permissions=True)

        # 4. Email trigger (like entrance test list)
        email = doc.email or ""
        if not email and doc.applicant:
            try:
                email = frappe.db.get_value("Applicant", doc.applicant, "email") or ""
            except Exception:
                pass

        if email and _send_allocation_email and frappe.utils.cint(send_email):
            try:
                # Attach reallocation flag for Jinja templates
                doc.is_reallocation = True
                doc.old_center_name = old_center_name
                _send_allocation_email(doc, email, allocation_type)
                try:
                    _send_allocation_notification(doc, email)
                except Exception:
                    pass
            except Exception:
                frappe.log_error(traceback.format_exc(), f"Reject and Allocate Email Failed: {doc.name}")

        if i % 10 == 0:
            frappe.db.commit()

        count += 1

    frappe.db.commit()
    return count

import json
import frappe
from frappe import _

@frappe.whitelist()
def check_reallocation_seat_availability(providers, selected_applicants, allocation_type=None):
    if isinstance(providers, str):
        providers = json.loads(providers)
    if isinstance(selected_applicants, str):
        selected_applicants = json.loads(selected_applicants)

    if not selected_applicants:
        return {"can_allocate": False, "error": "No applicants selected."}
    
    if (allocation_type == "Allocate Directly" or not allocation_type) and not providers:
        return {"can_allocate": False, "error": "No providers selected."}

    if not allocation_type:
        allocation_type = "Allocate Directly"

    programme_counts = {}
    programme_pwd_counts = {}
    total_selected = 0
    total_pwd = 0
    pwd_applicants = []

    allocations = frappe.get_all("Entrance Test Seat Allocation", 
                                 filters={"name": ["in", selected_applicants]}, 
                                 fields=["name", "candidate_name", "applicant", "program", "pwd"])

    for alloc in allocations:
        total_selected += 1
        prog = alloc.program or "Unspecified"
        programme_counts[prog] = programme_counts.get(prog, 0) + 1

        app_pwd = 0
        if alloc.pwd == 1:
            app_pwd = 1
        elif alloc.applicant:
            try:
                pwd_val = frappe.db.get_value("Applicant", alloc.applicant, "pwd") or ""
                if str(pwd_val).strip().lower() == "yes":
                    app_pwd = 1
            except Exception:
                pass

        if app_pwd:
            total_pwd += 1
            programme_pwd_counts[prog] = programme_pwd_counts.get(prog, 0) + 1
            pwd_applicants.append({
                "name": alloc.candidate_name or "Unknown",
                "applicant_id": alloc.applicant,
                "programme": prog
            })

    if total_selected == 0:
        return {"can_allocate": False, "error": "No applicants found."}

    centre_details = []
    total_available = 0
    has_pwd_centre = False

    for pname in providers:
        try:
            pdoc = frappe.get_doc("Entrance Test Provider", pname)
        except Exception:
            continue

        avail = pdoc.available_capacity or 0
        total_available += avail

        is_pwd_accessible = getattr(pdoc, "pwd_accessible", 0) == 1
        if is_pwd_accessible:
            has_pwd_centre = True

        centre_prog_caps = {}
        if hasattr(pdoc, "programme_capacity") and pdoc.programme_capacity:
            for row in pdoc.programme_capacity:
                prog_avail = max(0, (row.capacity or 0) - (row.reserved_seats or 0))
                centre_prog_caps[row.program] = {
                    "capacity": row.capacity or 0,
                    "reserved": row.reserved_seats or 0,
                    "available": prog_avail
                }

        centre_details.append({
            "provider": pname,
            "center_name": pdoc.center_name or pname,
            "total_capacity": pdoc.total_capacity or 0,
            "reserved_seats": pdoc.reserved_seats or 0,
            "available_capacity": avail,
            "pwd_accessible": 1 if is_pwd_accessible else 0,
            "programme_capacities": centre_prog_caps
        })

    programme_breakdown = []
    has_shortage = False
    for prog, count in sorted(programme_counts.items()):
        prog_total_available = 0
        centre_avails = []
        for cd in centre_details:
            prog_caps = cd["programme_capacities"]
            if prog in prog_caps:
                prog_total_available += prog_caps[prog]["available"]
                centre_avails.append({
                    "center_name": cd["center_name"],
                    "available": prog_caps[prog]["available"],
                    "capacity": prog_caps[prog]["capacity"],
                    "reserved": prog_caps[prog]["reserved"]
                })
            else:
                centre_avails.append({
                    "center_name": cd["center_name"],
                    "available": cd["available_capacity"],
                    "capacity": cd["total_capacity"],
                    "reserved": cd["reserved_seats"]
                })
                prog_total_available += cd["available_capacity"]

        shortage = max(0, count - prog_total_available)
        if shortage > 0:
            has_shortage = True

        programme_breakdown.append({
            "programme": prog,
            "applicant_count": count,
            "pwd_count": programme_pwd_counts.get(prog, 0),
            "total_available": prog_total_available,
            "shortage": shortage,
            "sufficient": shortage == 0,
            "centre_details": centre_avails
        })

    effective_total_available = sum(p["total_available"] for p in programme_breakdown)
    pwd_conflict = total_pwd > 0 and not has_pwd_centre

    return {
        "can_allocate": True,
        "allocation_type": allocation_type,
        "total_selected": total_selected,
        "total_available_seats": total_available,
        "effective_total_available": effective_total_available,
        "overall_sufficient": effective_total_available >= total_selected,
        "has_programme_shortage": has_shortage,
        "programme_breakdown": programme_breakdown,
        "centre_details": centre_details,
        "total_pwd": total_pwd,
        "has_pwd_centre": has_pwd_centre,
        "pwd_conflict": pwd_conflict,
        "pwd_applicants": pwd_applicants
    }


def _parse_multi_arg(val):
    if not val:
        return []
    if isinstance(val, (list, tuple)):
        return [str(v).strip() for v in val if v and str(v).strip() not in ("(All Cities)", "(All Centres)")]
    if isinstance(val, str):
        val = val.strip()
        if not val or val in ("(All Cities)", "(All Centres)"):
            return []
        if val.startswith("[") and val.endswith("]"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if v and str(v).strip() not in ("(All Cities)", "(All Centres)")]
            except Exception:
                pass
        if "," in val:
            return [v.strip() for v in val.split(",") if v.strip() and v.strip() not in ("(All Cities)", "(All Centres)")]
        return [val]
    return []


def _safe_path_component(name):
    import re
    if not name:
        return "Unknown"
    cleaned = re.sub(r'[/\\:*?"<>|]', '_', str(name)).strip()
    return cleaned or "Unknown"


def _get_compressed_photo_b64(file_url):
    import io
    import base64
    from PIL import Image
    from slcm.admission.utils.jinja import get_file_b64

    if not file_url:
        return ""
    
    cache_key = f"photo_b64_v4_{file_url}"
    try:
        cached = frappe.cache().get_value(cache_key)
        if cached:
            return cached
    except Exception:
        pass

    raw_b64 = get_file_b64(file_url)
    if not raw_b64:
        return ""
    
    try:
        raw_bytes = base64.b64decode(raw_b64)
        buf_in = io.BytesIO(raw_bytes)
        img = Image.open(buf_in)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((180, 225), Image.Resampling.LANCZOS)
        buf_out = io.BytesIO()
        img.save(buf_out, format="JPEG", quality=85, optimize=True)
        result = base64.b64encode(buf_out.getvalue()).decode("utf-8")
        
        try:
            frappe.cache().set_value(cache_key, result, expires_in_sec=86400)
        except Exception:
            pass
        return result
    except Exception:
        return raw_b64


def _save_generated_file(filename, content, dt, dn, is_private=0):
    from frappe.utils.file_manager import save_file_on_filesystem
    try:
        res = save_file_on_filesystem(filename, content, is_private=is_private)
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": res.get("file_name") or filename,
            "file_url": res.get("file_url"),
            "attached_to_doctype": dt,
            "attached_to_name": dn,
            "is_private": is_private
        })
        file_doc.flags.ignore_permissions = True
        file_doc.flags.ignore_file_validate = True
        file_doc.insert()
        return file_doc
    except Exception as e:
        frappe.log_error(f"Error saving generated file {filename}: {e}", "Save Generated File")
        raise e


def _build_attendance_sheet_filters(
    academic_year=None,
    admission_cycle=None,
    program_level=None,
    program=None,
    applicant_type=None,
    entrance_test_city=None,
    center_name=None,
    filters=None
):
    if filters:
        if isinstance(filters, str):
            try:
                filters = json.loads(filters)
            except Exception:
                filters = {}
        if isinstance(filters, dict):
            academic_year = filters.get("academic_year") or academic_year
            admission_cycle = filters.get("admission_cycle") or admission_cycle
            program_level = filters.get("program_level") or program_level
            program = filters.get("program") or program
            applicant_type = filters.get("applicant_type") or applicant_type
            entrance_test_city = filters.get("entrance_test_city") or entrance_test_city
            center_name = filters.get("center_name") or center_name

    query_filters = {}
    if academic_year:
        query_filters["academic_year"] = academic_year
    if admission_cycle:
        query_filters["admission_cycle"] = admission_cycle
    if program_level:
        query_filters["program_level"] = program_level
    if program:
        query_filters["program"] = program

    if applicant_type == "Domestic Applicants":
        query_filters["is_international_applicant"] = 0
    elif applicant_type == "International Applicants":
        query_filters["is_international_applicant"] = 1

    cities = _parse_multi_arg(entrance_test_city)
    centres = _parse_multi_arg(center_name)

    if cities:
        city_providers = frappe.get_all(
            "Entrance Test Provider",
            filters={"city": ["in", cities]},
            fields=["center_name"],
            limit_page_length=0
        )
        city_centres = list({p.center_name for p in city_providers if p.center_name})
        if city_centres:
            if centres:
                valid_centres = [c for c in centres if c in city_centres]
                if valid_centres:
                    query_filters["center_name"] = ["in", valid_centres] if len(valid_centres) > 1 else valid_centres[0]
                else:
                    query_filters["center_name"] = "__none__"
            else:
                query_filters["center_name"] = ["in", city_centres] if len(city_centres) > 1 else city_centres[0]
        else:
            query_filters["center_name"] = "__none__"
    elif centres:
        query_filters["center_name"] = ["in", centres] if len(centres) > 1 else centres[0]

    return query_filters


@frappe.whitelist()
def get_attendance_sheet_preview_count(
    academic_year=None,
    admission_cycle=None,
    program_level=None,
    program=None,
    applicant_type=None,
    entrance_test_city=None,
    center_name=None,
    filters=None
):
    query_filters = _build_attendance_sheet_filters(
        academic_year=academic_year,
        admission_cycle=admission_cycle,
        program_level=program_level,
        program=program,
        applicant_type=applicant_type,
        entrance_test_city=entrance_test_city,
        center_name=center_name,
        filters=filters
    )
    count = frappe.db.count("Entrance Test Seat Allocation", filters=query_filters)

    records = frappe.get_all(
        "Entrance Test Seat Allocation",
        filters=query_filters,
        fields=["center_name"],
        distinct=True,
        limit_page_length=0
    )
    total_centres = len({r.center_name for r in records if r.center_name})

    return {"count": count, "total_centres": total_centres}


@frappe.whitelist()
def download_attendance_sheet_pdf(
    academic_year=None,
    admission_cycle=None,
    program_level=None,
    program=None,
    applicant_type=None,
    entrance_test_city=None,
    center_name=None,
    download_mode=None,
    filters=None
):
    from frappe.utils.pdf import get_pdf
    from collections import OrderedDict
    import zipfile
    import io
    import re

    query_filters = _build_attendance_sheet_filters(
        academic_year=academic_year,
        admission_cycle=admission_cycle,
        program_level=program_level,
        program=program,
        applicant_type=applicant_type,
        entrance_test_city=entrance_test_city,
        center_name=center_name,
        filters=filters
    )

    records = frappe.get_all(
        "Entrance Test Seat Allocation",
        filters=query_filters,
        fields=[
            "name", "applicant", "candidate_name", "program",
            "center_name", "center_address", "admit_card_number",
            "profile", "father_name", "mother_name", "allocation_date",
            "start_time", "end_time", "entrance_test_name", "academic_year"
        ],
        order_by="center_name asc, program asc, admit_card_number asc, candidate_name asc",
        limit_page_length=0
    )

    if not records:
        frappe.throw(_("No applicant records found matching the selected filters."))

    total_candidates = len(records)
    frappe.publish_realtime("attendance_sheet_progress", {
        "progress": 5,
        "description": _("Prefetching candidate records and photos..."),
        "current": 0,
        "total": total_candidates
    })

    # Bulk fetch applicant photos and parent/guardian names in ONE query
    applicant_ids = list({rec.applicant for rec in records if rec.applicant})
    applicant_data = {}
    if applicant_ids:
        app_list = frappe.get_all(
            "Applicant",
            filters={"name": ["in", applicant_ids]},
            fields=["name", "candidate_photo", "father_name", "mother_name", "guardian_name"],
            limit_page_length=0
        )
        applicant_data = {a.name: a for a in app_list}

    # Fetch centre to city map for ZIP folder structure
    all_providers = frappe.get_all(
        "Entrance Test Provider",
        fields=["center_name", "city"],
        limit_page_length=0
    )
    centre_to_city = {p.center_name: (p.city or "Centres").strip() for p in all_providers if p.center_name}

    b64_cache = {}
    unique_photos = set()
    for rec in records:
        app_info = applicant_data.get(rec.applicant) if rec.applicant else None
        p_path = app_info.candidate_photo if app_info else None
        if not p_path:
            p_path = rec.profile
        if p_path:
            unique_photos.add(p_path)
        if rec.profile:
            unique_photos.add(rec.profile)

    if unique_photos:
        from concurrent.futures import ThreadPoolExecutor
        def _worker(p):
            try:
                return p, _get_compressed_photo_b64(p)
            except Exception:
                return p, ""
        with ThreadPoolExecutor(max_workers=16) as executor:
            for p_url, b64_val in executor.map(_worker, unique_photos):
                if b64_val:
                    b64_cache[p_url] = b64_val

    centre_records_map = OrderedDict()
    for rec in records:
        cn = (rec.center_name or "Unknown Centre").strip()
        if cn not in centre_records_map:
            centre_records_map[cn] = OrderedDict()
        prog_key = rec.program or "Unknown Programme"
        if prog_key not in centre_records_map[cn]:
            centre_records_map[cn][prog_key] = []
        centre_records_map[cn][prog_key].append(rec)

    total_centres = len(centre_records_map)
    is_zip = False
    if total_centres <= 1:
        is_zip = False
    elif download_mode == "Single Combined PDF File":
        is_zip = False
    else:
        is_zip = True

    inst_name = frappe.db.get_single_value("Institution Settings", "institution_name") or "National Law School of India University"

    template_path = frappe.get_app_path(
        "slcm", "admission", "print_format",
        "entrance_test_attendance_sheet",
        "entrance_test_attendance_sheet.html"
    )
    with open(template_path, "r", encoding="utf-8") as f:
        template_str = f.read()

    pdf_options = {
        "page-size": "A4",
        "orientation": "Portrait",
        "margin-top": "8mm",
        "margin-bottom": "8mm",
        "margin-left": "10mm",
        "margin-right": "10mm",
        "encoding": "UTF-8",
        "no-outline": None,
        "disable-smart-shrinking": None,
        "disable-javascript": None,
        "quiet": None
    }

    def _build_sheets_for_groups(groups_dict, processed_counter_ref):
        sheets = []
        for (c_name, prog_key), cand_list in groups_dict.items():
            first_rec = cand_list[0]
            c_address = first_rec.center_address or ""
            course_display = frappe.db.get_value("Programme", prog_key, "program_name") or prog_key

            exam_date_str = ""
            if first_rec.allocation_date:
                try:
                    exam_date_str = frappe.utils.format_date(first_rec.allocation_date, "EEEE, MMMM d, yyyy")
                except Exception:
                    exam_date_str = str(first_rec.allocation_date)

            s_time = first_rec.start_time
            e_time = first_rec.end_time
            if not s_time or not e_time:
                t_details = frappe.db.get_value(
                    "Entrance Test Details",
                    {"parent": first_rec.academic_year or admission_cycle},
                    ["start_time", "end_time"],
                    as_dict=True
                )
                if t_details:
                    s_time = s_time or t_details.start_time
                    e_time = e_time or t_details.end_time

            fmt_start = frappe.utils.format_time(s_time, "hh:mm a") if s_time else "10:00 AM"
            fmt_end = frappe.utils.format_time(e_time, "hh:mm a") if e_time else "12:30 PM"
            exam_time_str = f"{fmt_start} to {fmt_end}"

            test_title = first_rec.entrance_test_name
            if not test_title or test_title.lower() == "test":
                ay_str = first_rec.academic_year or academic_year or "2026"
                y_part = ay_str.split("-")[0].strip() if "-" in ay_str else ay_str[:4]
                test_title = f"NLSAT {y_part}"

            processed_candidates = []
            for idx, c in enumerate(cand_list):
                processed_counter_ref[0] += 1
                curr_count = processed_counter_ref[0]
                if curr_count % max(1, total_candidates // 40) == 0 or curr_count == total_candidates:
                    pct = int(5 + (curr_count / total_candidates) * 65)
                    frappe.publish_realtime("attendance_sheet_progress", {
                        "progress": pct,
                        "description": _("Processing candidates ({0}/{1})...").format(curr_count, total_candidates),
                        "current": curr_count,
                        "total": total_candidates
                    })

                p_src = ""
                app_info = applicant_data.get(c.applicant) if c.applicant else None
                profile_path = app_info.candidate_photo if app_info else None
                if not profile_path:
                    profile_path = c.profile

                pb64 = ""
                if profile_path:
                    if profile_path not in b64_cache:
                        try:
                            b64_cache[profile_path] = _get_compressed_photo_b64(profile_path)
                        except Exception:
                            b64_cache[profile_path] = ""
                    pb64 = b64_cache[profile_path]

                if not pb64 and c.profile and c.profile != profile_path:
                    if c.profile not in b64_cache:
                        try:
                            b64_cache[c.profile] = _get_compressed_photo_b64(c.profile)
                        except Exception:
                            b64_cache[c.profile] = ""
                    pb64 = b64_cache[c.profile]

                if pb64:
                    p_src = f"data:image/jpeg;base64,{pb64}"

                p_name = getattr(c, "father_name", None) or getattr(c, "mother_name", None) or getattr(c, "guardian_name", None)
                if not p_name and app_info:
                    p_name = getattr(app_info, "father_name", None) or getattr(app_info, "mother_name", None) or getattr(app_info, "guardian_name", None)

                processed_candidates.append({
                    "sl_no": idx + 1,
                    "photo_src": p_src,
                    "admit_card_no": c.admit_card_number or "",
                    "student_name": (c.candidate_name or "").upper(),
                    "parent_name": (p_name or "").upper()
                })

            pages = []
            for i in range(0, len(processed_candidates), 10):
                pages.append({
                    "page_number": len(pages) + 1,
                    "candidates": processed_candidates[i:i + 10]
                })

            sheets.append({
                "institution_name": (inst_name or "").upper(),
                "center_name": c_name,
                "center_address": c_address,
                "course_name": course_display,
                "exam_date": exam_date_str,
                "exam_time": exam_time_str,
                "test_title": test_title,
                "pages": pages
            })
        return sheets

    processed_counter = [0]

    ts = frappe.utils.now_datetime().strftime("%Y%m%d_%H%M%S")

    parsed_centres = _parse_multi_arg(center_name)
    parsed_cities = _parse_multi_arg(entrance_test_city)

    if parsed_centres:
        if len(parsed_centres) == 1:
            c_slug = frappe.scrub(parsed_centres[0])[:25]
        else:
            c_slug = f"{len(parsed_centres)}_Centres"
    elif parsed_cities:
        if len(parsed_cities) == 1:
            c_slug = frappe.scrub(parsed_cities[0])[:25]
        else:
            c_slug = f"{len(parsed_cities)}_Cities"
    else:
        c_slug = "All_Centres"

    c_slug = (c_slug or "Centres").strip("_")

    if not is_zip:
        all_groups = OrderedDict()
        for cn, progs in centre_records_map.items():
            for p_key, recs in progs.items():
                all_groups[(cn, p_key)] = recs

        sheets = _build_sheets_for_groups(all_groups, processed_counter)

        frappe.publish_realtime("attendance_sheet_progress", {
            "progress": 75,
            "description": _("Rendering HTML layout..."),
            "current": total_candidates,
            "total": total_candidates
        })

        rendered_html = frappe.render_template(template_str, {"sheets": sheets})

        frappe.publish_realtime("attendance_sheet_progress", {
            "progress": 85,
            "description": _("Generating PDF document structure..."),
            "current": total_candidates,
            "total": total_candidates
        })

        pdf_content = get_pdf(rendered_html, options=pdf_options)
        filename = f"Attendance_Sheet_{c_slug}_{ts}.pdf"

        anchor = records[0].name if records else "Entrance Test Seat Allocation"
        saved = _save_generated_file(
            filename,
            pdf_content,
            "Entrance Test Seat Allocation",
            anchor,
            is_private=0
        )

        frappe.publish_realtime("attendance_sheet_progress", {
            "progress": 100,
            "description": _("PDF Generation Complete!"),
            "current": total_candidates,
            "total": total_candidates
        })

        return {
            "file_url": saved.file_url,
            "filename": filename,
            "total_candidates": total_candidates,
            "total_pages": sum(len(s["pages"]) for s in sheets),
            "is_zip": False
        }

    else:
        zip_buffer = io.BytesIO()
        total_sheets_count = 0
        total_pages_count = 0
        centre_idx = 0

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
            for c_name, progs in centre_records_map.items():
                centre_idx += 1
                c_groups = OrderedDict()
                for p_key, recs in progs.items():
                    c_groups[(c_name, p_key)] = recs

                c_sheets = _build_sheets_for_groups(c_groups, processed_counter)
                total_sheets_count += len(c_sheets)
                total_pages_count += sum(len(s["pages"]) for s in c_sheets)

                pct = int(70 + (centre_idx / total_centres) * 25)
                frappe.publish_realtime("attendance_sheet_progress", {
                    "progress": pct,
                    "description": _("Generating PDF for Centre {0}/{1}: {2}...").format(centre_idx, total_centres, c_name),
                    "current": processed_counter[0],
                    "total": total_candidates
                })

                rendered_html = frappe.render_template(template_str, {"sheets": c_sheets})
                pdf_bytes = get_pdf(rendered_html, options=pdf_options)

                city_name = centre_to_city.get(c_name, "Centres")
                safe_city = _safe_path_component(city_name)
                safe_centre = _safe_path_component(c_name)
                zip_entry = f"{safe_city}/{safe_centre}.pdf"

                zip_file.writestr(zip_entry, pdf_bytes)

        zip_filename = f"Attendance_Sheets_{c_slug}_{ts}.zip"

        anchor = records[0].name if records else "Entrance Test Seat Allocation"
        saved = _save_generated_file(
            zip_filename,
            zip_buffer.getvalue(),
            "Entrance Test Seat Allocation",
            anchor,
            is_private=0
        )

        frappe.publish_realtime("attendance_sheet_progress", {
            "progress": 100,
            "description": _("ZIP Generation Complete!"),
            "current": total_candidates,
            "total": total_candidates
        })

        return {
            "file_url": saved.file_url,
            "filename": zip_filename,
            "total_candidates": total_candidates,
            "total_pages": total_pages_count,
            "total_centres": total_centres,
            "is_zip": True
        }



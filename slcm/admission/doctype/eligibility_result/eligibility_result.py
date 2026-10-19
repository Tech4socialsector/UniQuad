# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.pdf import get_pdf


class EligibilityResult(Document):

    def before_save(self):
        """
        Fetch the Applicant's multi-category child table and populate
        the local `category` table if it is currently empty.
        Also populate basic profile fields from Applicant.
        """
        if self.applicant_id:
            from slcm.admission.doctype.applicant.applicant import Applicant
            app_doc = frappe.get_doc("Applicant", self.applicant_id)
            
            # Populate basic info if missing
            if not self.candidate_name: self.candidate_name = app_doc.candidate_name
            if not self.email: self.email = app_doc.email
            if not self.gender: self.gender = app_doc.gender
            if not self.mobile_number: self.mobile_number = app_doc.mobile_number
            if not self.date_of_birth: self.date_of_birth = app_doc.date_of_birth

            if not self.category:
                app_categories = app_doc._get_applicant_categories()
                for cat in app_categories:
                    self.append("category", {"category": cat})

        # FETCH ENTRANCE TEST DETAILS
        self._fetch_entrance_test_details()

    def _fetch_entrance_test_details(self):
        """Fetch entrance test result details from Entrance Test Seat Allocation."""
        if not self.applicant_id:
            return

        etsa = frappe.db.get_value("Entrance Test Seat Allocation", {"applicant": self.applicant_id}, [
            "attendance_marked_on", "total_marks", "part_a_total_marks_scored",
            "part_a_all_india_rank", "part_b_total_marks_scored", "part_b_all_india_rank",
            "total_marks_secured_in_part_a_b", "percentage", "entrance_test_rank",
            "percentile", "result_status", "result_published"
        ], as_dict=True)

        if etsa:
            self.et_attendance_marked_on = etsa.attendance_marked_on
            self.et_total_marks = etsa.total_marks
            self.et_part_a_total_marks_scored = etsa.part_a_total_marks_scored
            self.et_part_a_all_india_rank = etsa.part_a_all_india_rank
            self.et_part_b_total_marks_scored = etsa.part_b_total_marks_scored
            self.et_part_b_all_india_rank = etsa.part_b_all_india_rank
            self.et_total_marks_secured_in_part_a_b = etsa.total_marks_secured_in_part_a_b
            self.et_percentage = etsa.percentage
            self.et_entrance_test_rank = etsa.entrance_test_rank
            self.et_percentile = etsa.percentile
            self.et_result_status = etsa.result_status
            self.et_result_published = etsa.result_published
            self.et_source = "Entrance Test"
        else:
            # Handle exempted or other sources
            # For Eligibility Result, source_type options are different, 
            # but we follow the logic: if not in ETSA, it's exempted or similar.
            if not self.et_total_marks: self.et_total_marks = 0
            if not self.et_part_a_total_marks_scored: self.et_part_a_total_marks_scored = 0
            if not self.et_part_a_all_india_rank: self.et_part_a_all_india_rank = 0
            if not self.et_part_b_total_marks_scored: self.et_part_b_total_marks_scored = 0
            if not self.et_part_b_all_india_rank: self.et_part_b_all_india_rank = 0
            if not self.et_total_marks_secured_in_part_a_b: self.et_total_marks_secured_in_part_a_b = 0
            if not self.et_percentage: self.et_percentage = 0
            if not self.et_entrance_test_rank: self.et_entrance_test_rank = 0
            if not self.et_percentile: self.et_percentile = 0
            self.et_source = getattr(self, "source_type", "Exempted")

    def on_update(self):
        """
        Generate and store the Eligibility Result Mark Sheet PDF.
        """
        if not self.flags.in_card_generation:
            self.generate_eligibility_card()

    def generate_eligibility_card(self):
        if getattr(frappe.flags, "in_test", False):
            return
            
        self.flags.in_card_generation = True
        try:
            html = self.get_card_html()
            pdf_content = get_pdf(html)
            
            filename = f"Eligibility_Result_{self.applicant_id}.pdf"
            
            # Check if file already exists for this document to avoid duplicates
            existing_file = frappe.get_all("File", filters={
                "attached_to_doctype": self.doctype,
                "attached_to_name": self.name,
                "attached_to_field": "eligibility_result_card"
            }, limit=1)
            
            if existing_file:
                _file = frappe.get_doc("File", existing_file[0].name)
                _file.content = pdf_content
                _file.save(ignore_permissions=True)
                file_url = _file.file_url
            else:
                _file = frappe.get_doc({
                    "doctype": "File",
                    "file_name": filename,
                    "attached_to_doctype": self.doctype,
                    "attached_to_name": self.name,
                    "attached_to_field": "eligibility_result_card",
                    "content": pdf_content,
                    "is_private": 1
                })
                _file.save(ignore_permissions=True)
                file_url = _file.file_url
            
            # Set the URL in the doctype and save only that field to avoid re-triggering on_update
            self.db_set("eligibility_result_card", file_url)
        finally:
            self.flags.in_card_generation = False

    def get_card_html(self):
        """
        Fetches the Eligibility Result Card HTML using Frappe Print Format.
        """
        print_format_name = "Eligibility Result Card"
        
        if not frappe.db.exists("Print Format", print_format_name):
            frappe.throw(
                _("Print Format '{0}' not found. Please create it in the Desk using the code in Sample_Eligibillity.html.").format(print_format_name),
                title=_("Configuration Missing")
            )

        return frappe.get_print(
            self.doctype, 
            self.name, 
            print_format_name, 
            as_pdf=False, 
            no_letterhead=True
        )

@frappe.whitelist()
def bulk_download_cards(names):
    """
    Creates a ZIP archive containing the Eligibility Result Card (PDF)
    for the selected records.
    """
    import io
    import os
    import zipfile
    from frappe.utils.file_manager import save_file, get_file_path

    if isinstance(names, str):
        names = frappe.parse_json(names)

    if not names:
        frappe.throw("No records selected for download.")

    zip_buffer = io.BytesIO()
    found_files = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for name in names:
            doc = frappe.get_doc("Eligibility Result", name)
            
            # Ensure the card exists
            if not doc.eligibility_result_card:
                doc.generate_eligibility_card()
            
            if doc.eligibility_result_card:
                file_url = doc.eligibility_result_card
                
                # Get local path for the file
                fname = file_url.split('/')[-1]
                fpath = get_file_path(fname)
                
                if os.path.exists(fpath):
                    # Organize PDFs into folders named by applicant ID for better organization
                    # Each folder contains the specific result PDF for that applicant
                    applicant_id = doc.applicant_id or doc.name
                    zip_path = f"{applicant_id}/Eligibility_Result.pdf"
                    
                    zip_file.write(fpath, arcname=zip_path)
                    found_files += 1

    if found_files == 0:
        frappe.throw("No Eligibility Cards found or generated for the selected records.")

    zip_filename = f"Bulk_Eligibility_Cards_{frappe.utils.now_datetime().strftime('%Y%m%d_%H%M%S')}.zip"
    
    # Save the ZIP as a temporary file to provide a URL
    saved_zip = save_file(
        zip_filename,
        zip_buffer.getvalue(),
        "Eligibility Result",
        names[0], 
        is_private=1,
        df="eligibility_result_card"
    )

    return saved_zip.file_url

@frappe.whitelist()
def get_applicant_data():
    """
    Fetches merit scores and admission statuses for the currently logged-in applicant.
    Security: Only returns data matching the session user's email.
    """
    user_email = frappe.session.user
    if user_email == "Guest":
        return {"error": "Unauthorized"}

    # 1. Fetch the primary Eligibility Result names first to get full docs
    result_names = frappe.get_all("Eligibility Result", 
        filters={"email": user_email},
        pluck="name"
    )
    
    if not result_names:
        result_names = frappe.get_all("Eligibility Result", 
            filters={"owner": user_email},
            pluck="name"
        )

    results = []
    for name in result_names:
        doc = frappe.get_doc("Eligibility Result", name)
        
        # Calculate averaged UG CGPA
        ug_avg = 0
        if doc.ug_degree_details:
            scores = [float(r.ug_cgpa or r.percentage_cgpa_obtained or 0) for r in doc.ug_degree_details]
            if scores: ug_avg = sum(scores) / len(scores)
            
        # Calculate averaged PG CGPA
        pg_avg = 0
        if doc.pg_degree_details:
            scores = [float(r.pg_cgpa or r.percentagecgpa_obtained or 0) for r in doc.pg_degree_details]
            if scores: pg_avg = sum(scores) / len(scores)

        results.append({
            "name": doc.name,
            "applicant_id": doc.applicant_id,
            "candidate_name": doc.candidate_name,
            "campus": doc.campus,
            "program": doc.program,
            "program_level": doc.program_level,
            "admission_cycle": doc.admission_cycle,
            "reservation_category": ", ".join([c.category for c in doc.category if c.category]) if doc.category else "General",
            "hsc_percentage": doc.hsc_percentage,
            "et_total_marks": doc.et_total_marks,
            "et_total_marks_secured_in_part_a_b": doc.et_total_marks_secured_in_part_a_b,
            "et_part_a_total_marks_scored": doc.et_part_a_total_marks_scored,
            "et_part_b_total_marks_scored": doc.et_part_b_total_marks_scored,
            "et_source": doc.et_source,
            "interview_score": doc.interview_score,
            "source_type": doc.source_type,
            "result_status": doc.result_status,
            "ug_cgpa": round(ug_avg, 2),
            "pg_cgpa": round(pg_avg, 2),
            "eligibility_result_card": doc.eligibility_result_card
        })

    if not results:
        # Check if any data is published even without Eligibility Result
        app_id = frappe.db.get_value("Applicant", {"email": user_email}, "name")
        if not app_id:
             app_id = frappe.db.get_value("Applicant", {"owner": user_email}, "name")

        if not app_id:
            return {"error": "No admission application record found for this account."}

        # Check for published Merit List or Seat Allocation
        merit_exists = frappe.db.exists("Merit List Applicant", {"applicant_id": app_id})
        allocation_exists = frappe.db.exists("Seat Selection Applicant", {"applicant_id": app_id})
        
        # If neither exists, then it's truly in progress
        if not merit_exists and not allocation_exists:
            # Check if any scholarship is published to allow early application
            scholarship_available = frappe.db.get_single_value("Admission Settings", "is_scholarship_available")
            if not scholarship_available:
                return {"error": "Your application is under review. Merit lists and scholarships will be visible here once published."}


    # 2. For each result, get the specific selection statuses from Seat Allocation child tables
    settings = frappe.get_single("Admission Settings")
    
    combined_data = []

    # If results is empty but we have an app_id, we might want to synthesize a result
    if not results and app_id:
        app = frappe.get_doc("Applicant", app_id)
        results.append({
            "applicant_id": app_id,
            "candidate_name": app.candidate_name,
            "campus": app.campus,
            "program": app.program,
            "admission_cycle": app.admission_cycle,
            "program_level": app.get("program_level"),
            "reservation_category": app.get("whether_scstobc_ncl") if app.get("whether_scstobc_ncl") and app.get("whether_scstobc_ncl") != "General" else ("Karnataka" if app.get("karnataka_category") == "Yes" else "General"),
            "hsc_percentage": getattr(app, "hsc_percentage", 0),
            "interview_score": getattr(app, "interview_score", None),
            "source_type": getattr(app, "source_type", None),
            "result_status": getattr(app, "result_status", None),
            "ug_cgpa": 0,
            "pg_cgpa": 0,
            "eligibility_result_card": None
        })

    for res in results:  
        # Fetch Merit List Entries
        merit_entries = frappe.get_all("Merit List Applicant",
            filters={"applicant_id": res['applicant_id']},
            fields=["total_score", "overall_rank", "category_rank", "status", "parent"]
        )
        for m in merit_entries:
            if m.get("parent"):
                m["published"] = frappe.db.get_value("Merit List", m.get("parent"), "status") == "Published"
        
        # Fetch Seat Allocation Statuses
        statuses = frappe.get_all("Seat Selection Applicant",
            filters={"applicant_id": res['applicant_id']},
            fields=["selection_status", "overall_rank", "allocation_type", "parent", "total_score", "allocated_category"]
        )
        
        # Inject Seat Allocation details
        for s in statuses:
            if s.get("parent"):
                s["published"] = frappe.db.get_value("Seat Allocation", s.get("parent"), "status") == "Published"
        
        published_statuses = [s.get("selection_status") for s in statuses if s.get("published")]
        
        available_scholarships = []
        applied_scholarships = []
        if res['applicant_id'] and settings.is_scholarship_available:
            from slcm.admission.utils.scholarship_availability import get_available_scholarships_for_dashboard, get_applied_scholarships_for_dashboard
            available_scholarships = get_available_scholarships_for_dashboard(
                res['applicant_id'], res['admission_cycle'], res['campus'], res['program'], published_statuses
            )
            applied_scholarships = get_applied_scholarships_for_dashboard(res['applicant_id'])

        combined_data.append({
            "profile": res,
            "merit": [m for m in merit_entries if m.get("published")],
            "results": [s for s in statuses if s.get("published")],
            "available_scholarships": available_scholarships,
            "applied_scholarships": applied_scholarships
        })

    return combined_data

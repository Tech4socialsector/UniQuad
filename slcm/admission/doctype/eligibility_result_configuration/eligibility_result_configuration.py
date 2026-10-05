# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now, get_url
import traceback


class EligibilityResultConfiguration(Document):

    def before_save(self):
        if not self.configuration_code:
            yr = getdate().strftime("%y")
            code = frappe.generate_hash("EligibilityResultConfiguration", 8).upper()[:8]
            self.configuration_code = f"ERC-{yr}-{code}"

    @frappe.whitelist()
    def generate_result(self):
        """
        Generates Eligibility Result records.
        """
        # Force reload the doctype to ensure the latest source_type options are picked up
        frappe.reload_doc("admission", "doctype", "eligibility_result")

        if self.status not in ["Draft", "In Progress", "Failed"]:
            frappe.throw("Document must be in Draft, In Progress, or Failed to generate results.")

        # ─── Source 1: Interview Passers ──────────────────────────────────────
        passed_interviewees = frappe.db.sql("""
            SELECT
                itsa.applicant AS applicant_id,
                itsa.candidate_name,
                itsa.email,
                itsa.gender,
                itsa.program,
                itsa.program_level,
                itsa.academic_year,
                itsa.admission_cycle,
                itsa.campus,
                itsa.entrance_test,
                itsa.intereview,
                itsa.entrance_test_score,
                itsa.interview_score
            FROM `tabInterview Seat Allocation` itsa
            WHERE
                itsa.academic_year = %(academic_year)s
                AND itsa.campus = %(campus)s
                AND itsa.admission_cycle = %(admission_cycle)s
                AND itsa.program_level = %(program_level)s
                AND itsa.interview_result_status = 'Pass'
        """, {
            "academic_year": self.academic_year,
            "campus": self.campus,
            "admission_cycle": self.admission_cycle,
            "program_level": self.program_level
        }, as_dict=True)

        # ─── Source 2: Dual Exempted Applicants ───────────────────────────────
        exempted_applicants = frappe.db.sql("""
            SELECT
                app.name AS applicant_id,
                app.candidate_name,
                app.email,
                app.gender,
                app.program,
                app.program_level,
                app.academic_year,
                app.admission_cycle,
                app.campus,
                app.entrance_test,
                app.intereview
            FROM `tabApplicant` app
            INNER JOIN `tabEligibility Evaluation` ee ON ee.applicant_name = app.name
            WHERE
                app.academic_year = %(academic_year)s
                AND app.campus = %(campus)s
                AND app.admission_cycle = %(admission_cycle)s
                AND app.program_level = %(program_level)s
                AND ee.exempts_entrance_test = 1
                AND ee.exempts_interview = 1
                AND app.status != 'Rejected'
        """, {
            "academic_year": self.academic_year,
            "campus": self.campus,
            "admission_cycle": self.admission_cycle,
            "program_level": self.program_level
        }, as_dict=True)

        et_pass_interview_exempt = frappe.db.sql("""
            SELECT
                etsa.applicant AS applicant_id,
                etsa.candidate_name,
                etsa.email,
                etsa.gender,
                etsa.program,
                etsa.program_level,
                etsa.academic_year,
                etsa.admission_cycle,
                etsa.campus,
                etsa.entrance_test,
                etsa.intereview,
                etsa.total_marks_secured_in_part_a_b AS entrance_test_score
            FROM `tabEntrance Test Seat Allocation` etsa
            WHERE
                etsa.academic_year = %(academic_year)s
                AND etsa.campus = %(campus)s
                AND etsa.admission_cycle = %(admission_cycle)s
                AND etsa.program_level = %(program_level)s
                AND etsa.result_status = 'Pass'
                AND COALESCE(etsa.exempts_interview, 0) = 1
        """, {
            "academic_year": self.academic_year,
            "campus": self.campus,
            "admission_cycle": self.admission_cycle,
            "program_level": self.program_level
        }, as_dict=True)

        # ─── Source 4: ET Pass, No Interview Requirement ─────────────────────
        et_pass_no_interview = frappe.db.sql("""
            SELECT
                etsa.applicant AS applicant_id,
                etsa.candidate_name,
                etsa.email,
                etsa.gender,
                etsa.program,
                etsa.program_level,
                etsa.academic_year,
                etsa.admission_cycle,
                etsa.campus,
                etsa.entrance_test,
                etsa.intereview,
                etsa.total_marks_secured_in_part_a_b AS entrance_test_score
            FROM `tabEntrance Test Seat Allocation` etsa
            INNER JOIN `tabProgramme` p ON p.name = etsa.program
            WHERE
                etsa.academic_year = %(academic_year)s
                AND etsa.campus = %(campus)s
                AND etsa.admission_cycle = %(admission_cycle)s
                AND etsa.program_level = %(program_level)s
                AND etsa.result_status = 'Pass'
                AND p.intereview = 0
        """, {
            "academic_year": self.academic_year,
            "campus": self.campus,
            "admission_cycle": self.admission_cycle,
            "program_level": self.program_level
        }, as_dict=True)

        # ─── Source 5: Direct Admission (No ET, No Interview) ────────────────
        direct_admission_applicants = frappe.db.sql("""
            SELECT
                app.name AS applicant_id,
                app.candidate_name,
                app.email,
                app.gender,
                app.program,
                app.program_level,
                app.academic_year,
                app.admission_cycle,
                app.campus,
                app.entrance_test,
                app.intereview
            FROM `tabApplicant` app
            INNER JOIN `tabEligibility Evaluation` ee ON ee.applicant_name = app.name
            INNER JOIN `tabProgramme` p ON p.name = app.program
            WHERE
                app.academic_year = %(academic_year)s
                AND app.campus = %(campus)s
                AND app.admission_cycle = %(admission_cycle)s
                AND app.program_level = %(program_level)s
                AND ee.evaluation_status = 'Eligible'
                AND p.entrance_test = 0
                AND p.intereview = 0
                AND app.status != 'Rejected'
        """, {
            "academic_year": self.academic_year,
            "campus": self.campus,
            "admission_cycle": self.admission_cycle,
            "program_level": self.program_level
        }, as_dict=True)

        count = 0
        source_counts = {
            "Interview Pass": 0,
            "ET Pass (Interview Exempt)": 0,
            "Exempted": 0,
            "Entrance Test Ignored": 0,
            "Interview Ignored": 0,
            "Dual Ignored": 0
        }

        # Track processed IDs to avoid duplicates across sources
        finalized_applicant_ids = set()
        
        # Build prioritized list for progress tracking
        applicants_to_process = []
        for app in passed_interviewees:
            if app.applicant_id not in finalized_applicant_ids:
                stype = "Interview Pass"
                if app.entrance_test == 0:
                    stype = "Entrance Test Ignored"
                applicants_to_process.append((app, stype))
                finalized_applicant_ids.add(app.applicant_id)
        
        for app in et_pass_interview_exempt:
            if app.applicant_id not in finalized_applicant_ids:
                applicants_to_process.append((app, "ET Pass (Interview Exempt)"))
                finalized_applicant_ids.add(app.applicant_id)

        for app in et_pass_no_interview:
            if app.applicant_id not in finalized_applicant_ids:
                applicants_to_process.append((app, "Interview Ignored"))
                finalized_applicant_ids.add(app.applicant_id)
        
        for app in exempted_applicants:
            if app.applicant_id not in finalized_applicant_ids:
                stype = "Exempted"
                if app.entrance_test == 0 and app.intereview == 0:
                    stype = "Dual Ignored"
                applicants_to_process.append((app, stype))
                finalized_applicant_ids.add(app.applicant_id)

        for app in direct_admission_applicants:
            if app.applicant_id not in finalized_applicant_ids:
                applicants_to_process.append((app, "Dual Ignored"))
                finalized_applicant_ids.add(app.applicant_id)

        total_to_process = len(applicants_to_process)
        if total_to_process == 0:
            self.db_set("status", "Failed")
            msg = self._get_failure_message(
                len(passed_interviewees), 
                len(et_pass_interview_exempt), 
                len(exempted_applicants),
                len([a for a in applicants_to_process if a[1] == "Entrance Test Ignored"]),
                len(et_pass_no_interview),
                len(direct_admission_applicants) + len([a for a in applicants_to_process if a[1] == "Dual Ignored"])
            )
            frappe.throw(msg, title=_("Generation Failed"))

        def get_applicant_education(applicant_id, program_level):
            edu = {
                "hsc_group": None,
                "hsc_percentage": None,
                "ug_degree_details": [],
                "pg_degree_details": [],
                "categories": []
            }
            try:
                app = frappe.get_doc("Applicant", applicant_id)
            except Exception:
                return edu

            edu["hsc_group"] = getattr(app, "hsc_group", None)
            edu["hsc_percentage"] = getattr(app, "hsc_percentage", None)
            
            # Fetch categories from individual fields as done in other doctypes
            cats = []
            if getattr(app, "whether_scstobc_ncl", None) and app.whether_scstobc_ncl != "General":
                cats.append(app.whether_scstobc_ncl)
            if getattr(app, "pwd", None) == "Yes":
                cats.append("PWD")
            if getattr(app, "karnataka_category", None) == "Yes":
                cats.append("Karnataka")

            edu["categories"] = cats

            if (program_level or "").strip() in ("Postgraduate", "Research Course", "PG"):
                for row in getattr(app, "ug_degree_details", []) or []:
                    edu["ug_degree_details"].append({
                        "ug_program": getattr(row, "ug_program", None),
                        "ug_cgpa": getattr(row, "ug_cgpa", None),
                        "percentage_cgpa_obtained": getattr(row, "percentage_cgpa_obtained", None),
                        "year_of_completion": getattr(row, "year_of_completion", None),
                        "college": getattr(row, "college", None),
                        "degree_certificate": getattr(row, "degree_certificate", None),
                        "marksheets": getattr(row, "marksheets", None)
                    })
                for row in getattr(app, "pg_degree_details", []) or []:
                    edu["pg_degree_details"].append({
                        "pg_program": getattr(row, "pg_program", None),
                        "pg_cgpa": getattr(row, "pg_cgpa", None),
                        "percentagecgpa_obtained": getattr(row, "percentagecgpa_obtained", None),
                        "year_of_completion": getattr(row, "year_of_completion", None),
                        "collegeuniversity": getattr(row, "collegeuniversity", None),
                        "pg_degree_certificatebonafide_certificate_to_be_uploaded": getattr(row, "pg_degree_certificatebonafide_certificate_to_be_uploaded", None),
                        "transcriptsmarksheets_to_be_uploaded": getattr(row, "transcriptsmarksheets_to_be_uploaded", None)
                    })
            return edu

        def upsert_result(data, source_type):
            nonlocal count
            existing = frappe.db.get_value("Eligibility Result", {"applicant_id": data.applicant_id}, "name")
            if existing:
                return

            if source_type in source_counts:
                source_counts[source_type] += 1

            res = frappe.new_doc("Eligibility Result")
            res.applicant_id = data.applicant_id
            res.candidate_name = data.candidate_name
            res.email = data.email
            res.gender = data.gender

            edu = get_applicant_education(data.applicant_id, data.program_level)
            res.set("category", [])
            for cat_name in (edu.get("categories") or []):
                res.append("category", {"category": cat_name})
            res.program = data.program
            res.program_level = data.program_level
            res.academic_year = data.academic_year
            res.admission_cycle = data.admission_cycle
            res.campus = data.campus

            # Scoring Logic:
            # - Exempted/Ignored stages get 100 marks.
            # - Attended stages get their actual score.

            res.interview_score = data.get("interview_score") or 0

            if source_type == "Exempted":
                res.interview_score = 100
            elif source_type == "Dual Ignored":
                res.interview_score = 100
            elif source_type == "ET Pass (Interview Exempt)":
                res.interview_score = 100
            elif source_type == "Interview Ignored":
                res.interview_score = 100
            elif source_type == "Entrance Test Ignored":
                pass

            res.hsc_group = edu.get("hsc_group")
            res.hsc_percentage = edu.get("hsc_percentage")

            if (data.program_level or "").strip() in ("Postgraduate", "Research Course", "PG"):
                for row in edu.get("ug_degree_details", []) or []:
                    res.append("ug_degree_details", row)
                for row in edu.get("pg_degree_details", []) or []:
                    res.append("pg_degree_details", row)

            res.source_type = source_type
            res.result_status = "Qualified"
            res.configuration_reference = self.name
            res.flags.ignore_mandatory = True
            res.save(ignore_permissions=True)
            
            if res.email:
                try:
                    _send_eligibility_result_email(res)
                    _send_eligibility_result_notification(res)
                except Exception:
                    frappe.log_error(message=traceback.format_exc(), title=f"Eligibility Result Email/Notification Failed: {res.name}")

            frappe.db.sql("""
                UPDATE `tabApplicant` 
                SET status = 'Interview Completed', modified = %(now)s 
                WHERE name = %(name)s
            """, {"now": now(), "name": data.applicant_id})
            frappe.clear_document_cache("Applicant", data.applicant_id)
            count += 1

        for i, (app, stype) in enumerate(applicants_to_process):
            upsert_result(app, stype)
            if i % 5 == 0 or (i + 1) == total_to_process:
                percent = (i + 1) * 100 / total_to_process
                frappe.publish_progress(percent, title=_("Generating Results..."))

        if count > 0:
            frappe.db.commit()
            self.db_set({
                "status": "Completed",
                "generated_on": now(),
                "generated_by": frappe.session.user
            })
            return {
                "total": count,
                "interview_pass": source_counts.get("Interview Pass", 0),
                "et_pass_exempt": source_counts.get("ET Pass (Interview Exempt)", 0),
                "dual_exempt": source_counts.get("Exempted", 0),
                "et_ignored": source_counts.get("Entrance Test Ignored", 0),
                "int_ignored": source_counts.get("Interview Ignored", 0),
                "dual_ignored": source_counts.get("Dual Ignored", 0)
            }
        else:
            self.db_set("status", "Failed")
            msg = self._get_failure_message(
                len(passed_interviewees), 
                len(et_pass_interview_exempt), 
                len(exempted_applicants),
                len([a for a in applicants_to_process if a[1] == "Entrance Test Ignored"]),
                len(et_pass_no_interview),
                len([a for a in applicants_to_process if a[1] == "Dual Ignored"])
            )
            frappe.throw(msg, title=_("Generation Failed"))

        return count

    def _get_failure_message(self, pi_len, et_len, ex_len, eti_len=0, ii_len=0, di_len=0):
        return f"""
            <div style="padding: 10px; font-family: sans-serif;">
                <div style="font-size: 16px; font-weight: 700; color: #dc2626; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                    <i class="fa fa-exclamation-triangle"></i> No eligible applicants found
                </div>
                <p style="font-size: 13px; color: #64748b; margin-bottom: 20px;">
                    No applicants matching the selected criteria were found for result generation.
                </p>
                <div style="background: #fef2f2; border: 1px solid #fee2e2; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                    <h4 style="margin: 0 0 10px 0; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #991b1b;">Diagnostic Summary</h4>
                    <table style="width: 100%; font-size: 12px; color: #991b1b;">
                        <tr><td style="padding: 4px 0;">Interview Passers</td><td style="padding: 4px 0; font-weight: 700; text-align: right;">{pi_len}</td></tr>
                        <tr><td style="padding: 4px 0;">ET Pass (Exempt Interview)</td><td style="padding: 4px 0; font-weight: 700; text-align: right;">{et_len}</td></tr>
                        <tr><td style="padding: 4px 0;">Dual Exempted</td><td style="padding: 4px 0; font-weight: 700; text-align: right;">{ex_len}</td></tr>
                        <tr><td style="padding: 4px 0;">Entrance Test Ignored</td><td style="padding: 4px 0; font-weight: 700; text-align: right;">{eti_len}</td></tr>
                        <tr><td style="padding: 4px 0;">Interview Ignored</td><td style="padding: 4px 0; font-weight: 700; text-align: right;">{ii_len}</td></tr>
                        <tr><td style="padding: 4px 0;">Dual Ignored</td><td style="padding: 4px 0; font-weight: 700; text-align: right;">{di_len}</td></tr>
                    </table>
                </div>
                <div style="font-size: 13px; color: #475569;">
                    <strong>Filters Applied:</strong><br>
                    <span style="font-size: 12px; color: #64748b;">Year: {self.academic_year} | Campus: {self.campus} | Cycle: {self.admission_cycle} | Level: {self.program_level}</span>
                </div>
            </div>
        """


def _send_eligibility_result_email(res):
    """Send an eligibility result notification using a configurable template."""
    try:
        template_name = "Eligibility Result"
        if not frappe.db.exists("Email Template", template_name):
            frappe.log_error(f"Email Template '{template_name}' not found.", "Email Sending Error")
            return

        template = frappe.get_doc("Email Template", template_name)
        
        # Prepare arguments for Jinja
        doc_dict = res.as_dict()
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
                    recipients=[res.email],
                    sender=sender,
                    cc=cc_list,
                    subject=subject,
                    message=message_body,
                    reference_doctype="Eligibility Result",
                    reference_name=res.name,
                    now=False
                )
                frappe.logger().info(f"Eligibility Result Email queued successfully to {res.email} for {res.name}")
            except Exception:
                frappe.log_error(traceback.format_exc(), f"Eligibility Result Email Queueing Failed: {res.name}")
    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"Eligibility Result Email Failed: {res.name}")


def _send_eligibility_result_notification(res):
    """Creates a Notification Log entry for the eligibility result."""
    if not res.email:
        return
    
    if frappe.db.exists("User", res.email):
        try:
            # Custom message for Eligibility Result
            message_body = f"""
                <p>Your eligibility evaluation result for <strong>"{res.program}"</strong> has been published.</p>
                <p>Status: <strong>{res.result_status or "Qualified"}</strong></p>
                <p>Source: <strong>{res.et_source or res.source_type or "—"}</strong></p>
                <p>Interview Score: <strong>{res.interview_score or 0}</strong></p>
                <p><a href="/merit-and-scholarship/admission_dashboard?panel=applications" style="color: #16a34a; font-weight: bold;">Click here to view details.</a></p>
            """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": "Eligibility Result Published",
                "for_user": res.email,
                "type": "Alert",
                "email_content": message_body,
                "document_type": "Eligibility Result",
                "document_name": res.name,
                "from_user": frappe.session.user,
                "link": "/merit-and-scholarship/admission_dashboard?panel=applications"
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(message=frappe.get_traceback(), title=f"Eligibility Result Notification Failed: {res.name}")

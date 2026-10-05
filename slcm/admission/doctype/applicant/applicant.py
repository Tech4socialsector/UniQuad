import json
import traceback
from contextlib import contextmanager
import os
import uuid

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import validate_email_address, getdate, date_diff, today, now, flt, nowdate, cint
from slcm.admission.portal_application_web_form import (
	applicant_portal_application_locked,
)
from slcm.admission.utils.regulatory import log_audit_trail

# Statuses treated as "submitted" for confirmation email, PDF cache, etc.
APPLICATION_SUBMITTED_STATUSES = frozenset(
    {
        "Submitted",
        "Completed",
        "Entrance Test Scheduled",
        "Entrance Test Allocated",
        "Entrance Test Exempted",
        "Entrance Test Completed",
        "Interview Scheduled",
        "Interview Exempted",
        "Interview Excempted",
        "Interview Completed",
        "Exempted Entrance Test And Interview",
        "Excempted Entrance Test And Interview",
        "Merit Selected",
        "Merit Waitlisted",
        "Merit Published",
        "Seat Selected",
        "Seat Waitlisted",
        "Offer Issued",
        "Offer Accepted",
        "Enrolled",
    }
)


class Applicant(Document):

    # ──────────────────────────────────────────────
    # VALIDATE
    # ──────────────────────────────────────────────

    def before_validate(self):
        # Save Draft: skip mandatory check so user can save incomplete form.
        if self.status == "Draft":
            self.flags.ignore_mandatory = True

    def _deny_portal_web_form_edit_if_locked(self):
        if not frappe.flags.get("in_web_form") or not self.name:
            return
        prev = (frappe.db.get_value("Applicant", self.name, "status") or "").strip()
        if not applicant_portal_application_locked(prev):
            return
        frappe.throw(
            _("Only draft applications can be edited on the portal."),
            title=_("Not allowed"),
        )

    def _restrict_program_change_on_submitted_applicant(self):
        """Block programme changes only when portal workflow has left Draft (e.g. Submitted), not when only docstatus is 1."""
        if self.is_new() or not self.has_value_changed("program"):
            return
        if getattr(self.flags, "ignore_validate_update_after_submit", False):
            return
        if not applicant_portal_application_locked((self.status or "").strip()):
            return
        frappe.throw(
            _("Changing programme is not allowed after this application has been submitted for review."),
            title=_("Not allowed"),
        )

    def validate(self):
        """
        Runs on every save.
        Eligibility and mandatory are checked only when the user clicks "Submit Application":
        the portal sets status = "Submitted" before save(), so this block runs
        during that submit request. Save Draft does not set Submitted, so no eligibility/mandatory here.
        create_or_update_evaluation() is called inside validate_eligibility().
        """
        self._deny_portal_web_form_edit_if_locked()
        self._restrict_program_change_on_submitted_applicant()

        set_intake_type(self)
        set_admission_details(self)
        self._validate_education_percentage_bounds()

        if self.status in ("Submitted", "Completed") and self.has_value_changed("status"):
            self._validate_application_limit_before_submit()
            if self.status == "Completed":
                self._validate_application_fee_before_submit()

        if self.status in ("Submitted", "Completed"):
            self._validate_national_test_percentage()
            self.validate_eligibility()
            self.validate_dynamic_conditions()
            if self.evaluation_status == "Ineligible":
                frappe.throw(
                    _("Submission Not Allowed: Applicant is not eligible."),
                    title=_("Submission Not Allowed")
                )
            # Set status from national test exemption (only when student submits)
            if self.status == "Submitted":
                self.status = _get_submission_status(self)

        self.update_applicant_stage_flags()

    def validate_dynamic_conditions(self):
        """Enforce dynamic form conditions on the server side."""
        if self.status not in ("Submitted", "Completed"):
            return
            
        filters = {}
        if frappe.db.has_column("Form Condition Rule", "is_active"):
            filters["is_active"] = 1

        rules = frappe.get_all("Form Condition Rule", filters=filters, fields=["trigger_field", "condition", "trigger_value", "action", "target_field"])
        for rule in rules:
            trigger_val = self.get(rule.trigger_field)
            if trigger_val is None:
                continue
                
            match = False
            if rule.condition == "=":
                match = str(trigger_val) == str(rule.trigger_value)
            elif rule.condition == "!=":
                match = str(trigger_val) != str(rule.trigger_value)
            elif rule.condition == ">":
                match = flt(trigger_val) > flt(rule.trigger_value)
            elif rule.condition == "<":
                match = flt(trigger_val) < flt(rule.trigger_value)
                
            if match and rule.action == "Require":
                if not self.get(rule.target_field):
                    frappe.throw(
                        f"Field '{rule.target_field}' is mandatory because '{rule.trigger_field}' meets the condition.",
                        title="Missing Conditional Mandatory Field"
                    )

    def update_applicant_stage_flags(self):
        """
        Populates entrance_test and intereview flags based on Program stages.
        Exemption flags (exempts_entrance_test, exempts_interview) are handled by validate_eligibility.
        """
        if self.program:
            is_intl = (getattr(self, "foriegn_national", "") or "").strip() == "Yes"
            if is_intl:
                program_stages = frappe.db.get_value("Programme", self.program, ["international_entrance_test", "international_interview"], as_dict=True)
                if program_stages:
                    self.entrance_test = program_stages.get("international_entrance_test", 0)
                    self.intereview = program_stages.get("international_interview", 0)
            else:
                program_stages = frappe.db.get_value("Programme", self.program, ["entrance_test", "intereview"], as_dict=True)
                if program_stages:
                    self.entrance_test = program_stages.get("entrance_test", 0)
                    self.intereview = program_stages.get("intereview", 0)

    def validate_email(self):
        if not validate_email_address(self.email):
            frappe.throw(
                f"Invalid email address: {self.email}",
                title="Invalid Email"
            )

    def validate_age(self):
        if self.date_of_birth:
            age = date_diff(today(), self.date_of_birth) / 365
            if age < 17:
                frappe.throw(
                    "Applicant must be at least 17 years old.",
                    title="Age Restriction"
                )

    def _validate_education_percentage_bounds(self):
        """Class X % and HSC % use 0–100 scale (CGPA uses separate fields)."""
        for fieldname, label in (
            ("class_x_percentage", _("Class X percentage")),
            ("hsc_percentage", _("HSC / Class XII percentage")),
        ):
            val = getattr(self, fieldname, None)
            if val is None:
                continue
            v = flt(val)
            if v < 0 or v > 100:
                frappe.throw(
                    _("{0} must be between 0 and 100.").format(label),
                    title=_("Invalid value"),
                )

    def validate_reservation_documents(self):
        if getattr(self, "whether_scstobc_ncl", None) == "EWS" and not self.ews_certificate:
            frappe.throw(
                "EWS Certificate is mandatory for EWS category.",
                title="Missing Document"
            )

        # Derive caste categories from the whether_scstobc_ncl field
        caste_categories = {"SC", "ST", "OBC-NCL"}
        applicant_cats = self._get_applicant_categories()
        matched_caste = applicant_cats & caste_categories

        if matched_caste and not self.caste_certificate:
            frappe.throw(
                f"Caste Certificate is mandatory for {', '.join(sorted(matched_caste))} category.",
                title="Missing Document"
            )

        if self.pwd == "Yes" and not self.pwd_certificate:
            frappe.throw(
                "PwD Certificate is mandatory for PwD category.",
                title="Missing Document"
            )

    def _validate_national_test_percentage(self):
        """When National test is selected, score/percentage is mandatory."""
        if self.get("national_test_name") and not self.flags.ignore_mandatory:
            pct = self.get("percentage")
            if pct is None or pct == "" or (isinstance(pct, (int, float)) and flt(pct) < 0):
                frappe.throw(
                    _("Score or percentage is required when National test is selected."),
                    title=_("National Test Score Required"),
                )

    def validate_preferences(self):
        if not self.first_preference:
            frappe.throw(
                "First Campus Preference is mandatory.",
                title="Missing Preference"
            )
        preferences = [
            self.first_preference,
            self.second_preference,
            self.third_preference
        ]
        filled = [p for p in preferences if p]
        if len(filled) != len(set(filled)):
            frappe.throw(
                "Duplicate campus preferences are not allowed.",
                title="Duplicate Preference"
            )

    def _validate_application_limit_before_submit(self):
        """
        Block submission if the maximum application limit for the selected program 
        in the current admission cycle has been reached.
        """
        if not self.admission_cycle or not self.program:
            return

        # Fetch max_applications limit from Admission Cycle Program
        acp = frappe.db.get_value(
            "Admission Cycle Program", 
            {"parent": self.admission_cycle, "program": self.program, "is_active": 1}, 
            ["max_applications", "name"], 
            as_dict=True
        )
        
        if acp and cint(acp.max_applications) > 0:
            # Count existing active (not Closed) applications for this program and cycle
            # We exclude the current record from the count.
            received_rows = frappe.db.sql("""
                SELECT COUNT(*) AS received
                FROM `tabApplicant` a
                LEFT JOIN `tabApplicant Status` s ON s.name = a.status
                WHERE a.admission_cycle = %s
                  AND a.program = %s
                  AND a.name != %s
                  AND COALESCE(s.status_type, '') != 'Closed'
            """, (self.admission_cycle, self.program, self.name), as_dict=True)
            
            received = received_rows[0].get("received") if received_rows else 0
            
            if received >= cint(acp.max_applications):
                frappe.throw(
                    _("Submission failed: The maximum application limit ({0}) for <b>{1}</b> has been reached for this admission cycle.").format(
                        acp.max_applications, self.program
                    ),
                    title=_("Limit Reached")
                )

    def _validate_application_fee_before_submit(self):
        """Block submission if application fee is required and not paid/waived.
        When category has no fee or fee is 0, allow submit and set application_fee_status to 'Paid'."""
        from slcm.api.service.application_fee_service import get_application_fee_for_category
        from slcm.api.service.application_fee_service import _get_applicant_category

        category = _get_applicant_category(self.name)
        is_foreign = self.nationality != "Indian" if self.nationality else False
        fee_amount = get_application_fee_for_category(self.program, self.admission_cycle, category, is_foreign=is_foreign)

        if flt(fee_amount, 2) <= 0:
            # No fee or zero fee: allow submit without payment; set status to Paid so UI/reports treat as complete
            self.application_fee_status = "Paid"
            if flt(self.application_fee_amount or 0, 2) != flt(fee_amount, 2):
                self.application_fee_amount = flt(fee_amount, 2)
            return

        # Fee > 0: require Paid or Waived
        db_status = frappe.db.get_value("Applicant", self.name, "application_fee_status")
        status = (db_status or self.application_fee_status or "Pending").strip()

        if status not in ("Paid", "Waived"):
            frappe.throw(
                _("Application fee must be paid or waived before you can submit. "
                  "Current status: {0}. Amount: {1}. "
                  "Go to View Application and click \"Pay Application Fee\" to open the payment gateway and pay; then return here to submit.").format(
                    status, fee_amount
                ),
                title=_("Pay Application Fee First")
            )

    def validate_declaration(self):
        if self.status in ("Submitted", "Completed") and not self.declaration_undertaking:
            frappe.throw(
                "Declaration Undertaking must be accepted before submission.",
                title="Declaration Required"
            )

    def before_save(self):
        """
        Stale docstatus=1 on a portal-Draft application triggers Frappe's update-after-submit checks
        (even when Applicant is not submittable — see patch normalize_applicant_docstatus_not_submittable).
        """
        if not self.is_new() and self.name and cint(self.docstatus) == 1:
            st_db = (frappe.db.get_value(self.doctype, self.name, "status") or "").strip()
            if st_db == "Draft" and (self.status or "").strip() == "Draft":
                self.flags.ignore_validate_update_after_submit = True

        if not self.applicant_id:
            self.applicant_id = frappe.generate_hash(length=8).upper()
        doc_before = self.get_doc_before_save()
        if doc_before:
            self.flags.old_status = doc_before.status
            self.flags.old_admission_cycle = doc_before.admission_cycle
            self.flags.old_program = doc_before.program
            self.flags.old_campus = doc_before.campus
        else:
            self.flags.old_status = None
            self.flags.old_admission_cycle = None
            self.flags.old_program = None
            self.flags.old_campus = None

    def on_update(self):
        if not self.user_id:
            frappe.db.set_value(self.doctype, self.name, "user_id", self.email, update_modified=False)
        self.sync_user_profile()

        # Generate the application PDF when the status is submitted and form is missing
        if (
            self.name
            and self.status in APPLICATION_SUBMITTED_STATUSES
            and not self.flags.get("in_pdf_generation")
            and not frappe.db.get_value("Applicant", self.name, "application_form")
        ):
            self.generate_application_pdf()

        doc_before_save = self.get_doc_before_save()
        old_status = (
            doc_before_save.status
            if doc_before_save and hasattr(doc_before_save, "status")
            else self.flags.get("old_status")
        )
        just_submitted = (
            (not old_status or old_status == "Draft" or old_status not in APPLICATION_SUBMITTED_STATUSES)
            and self.status == "Submitted"
            and (self.is_new() or self.has_value_changed("status"))
        )

        if just_submitted:
            log_audit_trail(
                self.doctype, self.name,
                self.status, "status",
                "Draft", self.status, "General"
            )

            # ── Rich confirmation email with PDF attachment (Immediate) ────
            try:
                sent = self.send_submission_confirmation()
                if sent:
                    frappe.msgprint(
                        _("Application Submitted email sent to the applicant successfully."),
                        alert=True,
                        indicator="green",
                    )
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Submission confirmation email failed — {self.applicant_id or self.name}"
                )
            # ─────────────────────────────────────────────────────────────

            from slcm.admission.utils.notifications import log_communication
            log_communication(
                applicant=self.name,
                communication_type="Email",
                category="Admission",
                subject=f"Application Submitted — {self.applicant_id} | {self.program or 'Admissions'}",
                content=(
                    f"Submission confirmation email sent for {self.applicant_id}. "
                    f"Program: {self.program or '—'}, "
                    f"Cycle: {self.admission_cycle or '—'}, "
                    f"Campus: {self.campus or '—'}"
                ),
                reference_doctype="Applicant",
                reference_name=self.name
            )

        old_status = self.flags.get("old_status")
        just_completed = (
            old_status in ("Draft", "Submitted")
            and self.status == "Completed"
            and self.has_value_changed("status")
        )

        if just_completed:
            try:
                _auto_allocate_entrance_test_on_submission(self)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Auto entrance test allocation failed for Applicant {self.name}",
                )

            # Send completion confirmation with receipt
            try:
                self.send_completion_confirmation()
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Completion confirmation email failed — {self.name}"
                )

        # If current_stage changed, notify applicant
        if self.is_new() or self.has_value_changed("current_stage"):
            if self.current_stage and self.admission_cycle:
                try:
                    from slcm.admission.utils.stage_control import get_cycle_stages
                    stages = get_cycle_stages(
                        self.admission_cycle,
                        self.intake_type or "All"
                    )
                    for s in stages:
                        if s.stage_name == self.current_stage:
                            notify_stage_entry(self, s)
                            break
                except Exception:
                    pass

        # Withdrawn application: Student Master (Current Status) + enrollments
        if self.status == "Withdrawn" and self.has_value_changed("status"):
            try:
                from slcm.admission.utils.withdrawal_sync import (
                    sync_student_records_for_withdrawn_application,
                )

                sync_student_records_for_withdrawn_application(
                    self.name,
                    status_remark=_("Application withdrawn"),
                )
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Withdrawal sync failed for Applicant {self.name}",
                )

        if self.name and any(
            self.has_value_changed(f)
            for f in (
                "application_fee_status",
                "program",
                "admission_cycle",
                "application_fee_amount",
            )
        ):
            try:
                from slcm.api.service.application_fee_service import (
                    sync_application_fee_assignment_for_applicant,
                )

                sync_application_fee_assignment_for_applicant(self.name)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Applicant {self.name} — sync_application_fee_assignment_for_applicant",
                )

        # PDF snapshot for bulk download: fill when missing (desk-created Submitted rows,
        # or if submission email PDF step failed). Skips when ``application_form`` already set.
        if (
            self.name
            and self.status in APPLICATION_SUBMITTED_STATUSES
            and not getattr(self.flags, "in_application_form_cache_job", False)
        ):
            if not frappe.db.get_value("Applicant", self.name, "application_form"):
                self.flags.in_application_form_cache_job = True
                try:
                    frappe.enqueue(
                        "slcm.admission.doctype.applicant.applicant.ensure_application_form_pdf_for_applicant",
                        applicant_name=self.name,
                        queue="long",
                        enqueue_after_commit=True
                    )
                except Exception:
                    frappe.log_error(
                        frappe.get_traceback(),
                        f"ensure_application_form_pdf_for_applicant queuing failed for {self.name}",
                    )
                finally:
                    self.flags.in_application_form_cache_job = False

        # Update application count for current and potentially old cycle/program/campus
        self.update_admission_cycle_program_count()
        
        old_cycle = self.flags.get("old_admission_cycle")
        old_program = self.flags.get("old_program")
        old_campus = self.flags.get("old_campus")
        
        if (old_cycle and old_program) and (
            old_cycle != self.admission_cycle or 
            old_program != self.program or 
            old_campus != self.campus
        ):
            self.update_admission_cycle_program_count(old_cycle, old_program, old_campus)

    def on_trash(self):
        self.update_admission_cycle_program_count()

    def sync_user_profile(self):
        if not self.email:
            return
            
        user_name = frappe.db.get_value("User", {"email": self.email}, "name")
        if not user_name:
            return
            
        user = frappe.get_doc("User", user_name)
        updated = False
        
        if self.candidate_name:
            parts = str(self.candidate_name).split(" ", 1)
            first_name = parts[0].strip()
            last_name = parts[1].strip() if len(parts) > 1 else ""
            if user.first_name != first_name or (user.last_name or "") != last_name:
                user.first_name = first_name
                user.last_name = last_name
                updated = True
                
        if self.mobile_number and user.phone != self.mobile_number:
            user.phone = self.mobile_number
            updated = True
            
        if self.gender and user.gender != self.gender:
            user.gender = self.gender
            updated = True
            
        if self.date_of_birth and getdate(user.birth_date) != getdate(self.date_of_birth):
            user.birth_date = self.date_of_birth
            updated = True
            
        if self.country and user.country != self.country:
            user.country = self.country
            updated = True

        if self.status in APPLICATION_SUBMITTED_STATUSES:
            address_parts = [
                self.city,
                self.state,
                self.country
            ]
            # Clean up and combine parts into a single line
            address_str = ", ".join([str(p).strip().replace("\n", " ").replace("\r", "") for p in address_parts if p]).strip()
            # Remove any double spaces
            while "  " in address_str:
                address_str = address_str.replace("  ", " ")

            if self.pincode:
                address_str += f" - {self.pincode}"

            # Update location if field exists on User and has changed
            if hasattr(user, "location") and user.location != address_str:
                user.location = address_str
                updated = True
            
        if updated:
            user.flags.ignore_permissions = True
            user.save(ignore_permissions=True)

    def update_admission_cycle_program_count(self, cycle=None, program=None, campus=None):
        """
        Recalculates the application_count for a specific Admission Cycle Program.
        Excludes applications with 'Draft' status.
        """
        target_cycle = cycle or self.admission_cycle
        target_program = program or self.program
        target_campus = campus or self.campus

        if not (target_cycle and target_program):
            return

        # Locate the specific program row in the cycle
        filters = {"parent": target_cycle, "program": target_program}
        if target_campus:
            filters["campus"] = target_campus

        acp_name = frappe.db.get_value("Admission Cycle Program", filters, "name")
        if acp_name:
            # Count all submitted applications (any status except Draft)
            count_filters = {
                "admission_cycle": target_cycle,
                "program": target_program,
                "status": ["!=", "Draft"]
            }
            if target_campus:
                count_filters["campus"] = target_campus
            
            # If we are in on_trash, we should exclude the current record if it's not yet deleted from DB
            # Actually, on_trash runs BEFORE deletion. So we exclude self.name.
            new_count = frappe.db.count("Applicant", count_filters)
            
            # If current doc is being deleted and matches filters, decrement
            if frappe.flags.in_trash and self.status != "Draft":
                if self.admission_cycle == target_cycle and self.program == target_program:
                    if not target_campus or self.campus == target_campus:
                        new_count = max(0, new_count - 1)

            # Update the application_count field
            frappe.db.set_value("Admission Cycle Program", acp_name, "application_count", new_count, update_modified=True)
            
            # Trigger a reload for the parent if it's being viewed (optional but helpful for some workflows)
            # frappe.publish_realtime("list_update", {"doctype": "Admission Cycle"})

    def generate_application_pdf(self):
        """Generates application PDF using 'Applicant Application Form' print format and attaches to application_form field."""
        self.flags.in_pdf_generation = True
        try:
            pdf_content = self.get_application_pdf_content()
            if not pdf_content:
                return None

            save_application_form_pdf_to_applicant(self, pdf_content)
            return pdf_content
        except Exception:
            frappe.log_error(message=frappe.get_traceback(), title=f"Applicant PDF Generation Failed: {self.name}")
            return None
        finally:
            self.flags.in_pdf_generation = False

    def prepare_html_for_pdf(self, html):
        """Inlines images and cleans up relative CSS links to avoid wkhtmltopdf network errors/timeouts."""
        if not html:
            return html
        try:
            import base64, mimetypes, os, re
            from bs4 import BeautifulSoup
            
            # Remove external and relative link tags that cause wkhtmltopdf network timeouts / errors
            html = re.sub(r'<link[^>]*href=["\']?/print\.bundle\.css["\']?[^>]*>', '', html)
            html = re.sub(r'<link[^>]*fonts\.googleapis\.com[^>]*>', '', html)
            html = re.sub(r'@import\s+url\([^)]*fonts\.googleapis\.com[^)]*\);?', '', html)

            soup = BeautifulSoup(html, "html.parser")
            for img in soup.find_all("img"):
                src = img.get("src")
                if not src or src.startswith("data:"):
                    continue
                file_url = src.split("?")[0]
                file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
                if not file_name:
                    file_name = frappe.db.get_value("File", {"file_name": file_url.split("/")[-1]}, "name")
                
                full_path = None
                if file_name:
                    try:
                        fdoc = frappe.get_doc("File", file_name)
                        full_path = fdoc.get_full_path()
                    except Exception:
                        pass
                
                if not full_path or not os.path.exists(full_path):
                    if file_url.startswith("/private/files/"):
                        full_path = frappe.get_site_path("private", "files", file_url.replace("/private/files/", ""))
                    elif file_url.startswith("/files/"):
                        full_path = frappe.get_site_path("public", "files", file_url.replace("/files/", ""))

                if full_path and os.path.exists(full_path):
                    mime_type = mimetypes.guess_type(full_path)[0] or "image/jpeg"
                    with open(full_path, "rb") as f:
                        encoded = base64.b64encode(f.read()).decode("utf-8")
                        img["src"] = f"data:{mime_type};base64,{encoded}"
                else:
                    img["src"] = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
            return str(soup)
        except Exception:
            frappe.log_error(title="prepare_html_for_pdf error", message=frappe.get_traceback())
            return html

    def get_application_pdf_content(self):
        """Returns rendered PDF bytes for 'Applicant Application Form' print format."""
        print_format_name = resolve_application_form_print_format_for_cycle(self.admission_cycle) or "Applicant Application Form"
        if not frappe.db.exists("Print Format", print_format_name):
            print_format_name = "Applicant Application Form"

        with _ignore_print_permissions():
            html = frappe.get_print(
                self.doctype, 
                self.name, 
                print_format_name, 
                as_pdf=False, 
                no_letterhead=True,
                doc=self
            )
            html = self.prepare_html_for_pdf(html)
            from frappe.utils.pdf import get_pdf
            return get_pdf(html, options={"load-error-handling": "ignore", "load-media-error-handling": "ignore"})

    def send_submission_confirmation(self):
        """
        Sends a formatted confirmation email on application submission.
        - Uses 'Application Submitted Email' Email Template
        - Uses 'Applicant Application Form' Print Format
        - Generates and stores PDF in application_form field
        """
        email_template_name = "Application Submitted Email"
        print_format_name = resolve_application_form_print_format_for_cycle(self.admission_cycle) or "Applicant Application Form"

        recipient = self.email
        if not recipient:
            frappe.log_error(
                f"No email address on Applicant {self.name}. Submission email skipped.",
                "Applicant Submission Email: No Recipient"
            )
            return False

        # ── Reservation summary ──────────────────────────────────────────────
        reservation_parts = []
        if self.whether_scstobc_ncl:
            reservation_parts.append(self.whether_scstobc_ncl)
        if self.pwd == "Yes":
            reservation_parts.append("PwD")
        if self.karnataka_category:
            reservation_parts.append(f"Karnataka: {self.karnataka_category}")
        reservation_summary = (
            ", ".join(reservation_parts) if reservation_parts else "General (Unreserved)"
        )

        # ── Test center preference summary ───────────────────────────────────
        test_centers = []
        if self.first_preference:
            test_centers.append(f"1st: {self.first_preference}")
        if self.second_preference:
            test_centers.append(f"2nd: {self.second_preference}")
        if self.third_preference:
            test_centers.append(f"3rd: {self.third_preference}")
        test_center_summary = " | ".join(test_centers) if test_centers else "Not specified"

        # ── Program-level academic summary ───────────────────────────────────
        academic_line = ""
        if self.program_level == "UG":
            academic_line = (
                f"Class XII: {self.class_xii_school or '—'} "
                f"({self.class_xii_year_of_completion or '—'}) "
                f"— {self.hsc_percentage or '—'}%"
            )
        elif self.program_level in ["PG", "LLM"]:
            academic_line = f"UG Degree completion: {self.ug_degree_completion or '—'}"
        elif self.program_level == "PhD":
            academic_line = f"PhD Program Type: {self.phd_program_type or '—'}"

        # ── Institution name ─────────────────────────────────────────────────
        institution_name = (
            frappe.db.get_single_value("Institution Settings", "institution_name")
            or "Admissions Office"
        )

        admission_portal_url = frappe.utils.get_url("/admission/login#login")

        # ── Institution logo ──────────────────────────────────────────────────
        institution_logo = frappe.db.get_single_value("Institution Settings", "logo") or ""
        if institution_logo and not institution_logo.startswith("http"):
            institution_logo = frappe.utils.get_url(institution_logo)

        # ── Context dict for template rendering ──────────────────────────────
        doc_dict = self.as_dict() if hasattr(self, "as_dict") else self
        template_context = {
            "doc": doc_dict,
            "applicant_id": self.name,
            "candidate_name": self.candidate_name or "",
            "first_name": (self.candidate_name or "").split()[0] if self.candidate_name else "",
            "program": frappe.db.get_value("Programme", self.program, "program_name") if self.program else "—",
            "program_level": self.program_level or "—",
            "application_type": self.application_type or "—",
            "admission_cycle": self.admission_cycle or "—",
            "campus": self.campus or "—",
            "status": self.status or "Submitted",
            "date_of_birth": frappe.utils.formatdate(self.date_of_birth) if self.date_of_birth else "—",
            "gender": self.gender or "—",
            "mobile_number": self.mobile_number or "—",
            "nationality": self.nationality or "—",
            "city": self.city or "—",
            "state": self.state or "—",
            "class_x_school": self.class_x_school or "—",
            "class_x_percentage": f"{self.class_x_percentage}%" if self.class_x_percentage else "—",
            "class_xii_school": self.class_xii_school or "—",
            "hsc_percentage": f"{self.hsc_percentage}%" if self.hsc_percentage else "—",
            "reservation_summary": reservation_summary,
            "annual_house_hold_income": self.annual_house_hold_income or "—",
            "test_center_summary": test_center_summary,
            "application_fee_status": self.application_fee_status or "—",
            "application_fee_amount": (
                frappe.utils.fmt_money(self.application_fee_amount, currency="INR")
                if self.application_fee_amount else "—"
            ),
            "institution_name": institution_name,
            "institution_logo": institution_logo,
            "admission_portal_url": admission_portal_url,
            "generated_on": frappe.utils.now_datetime().strftime("%d %b %Y, %I:%M %p"),
        }

        # ── Resolve email subject and body ────────────────────────────────────
        email_subject = f"Application Submitted — {self.applicant_id or self.name} | {self.program or 'Admissions'}"
        html_body = None
        email_template = None

        if frappe.db.exists("Email Template", email_template_name):
            try:
                email_template = frappe.get_doc("Email Template", email_template_name)
                if email_template.get("subject"):
                    email_subject = frappe.render_template(email_template.subject, template_context)
                
                if email_template.get("use_html") and email_template.get("response_html"):
                    html_body = frappe.render_template(email_template.response_html, template_context)
                elif email_template.get("response"):
                    html_body = frappe.render_template(email_template.response, template_context)

                if not html_body:
                    html_body = frappe.render_template(email_template.get("message") or "", template_context)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Email template render failed for {self.name}, falling back to default"
                )
                html_body = None

        # ── Fallback to hardcoded HTML if no template or render failed ────────
        if not html_body:
            html_body = self._build_default_email_html(template_context)

        # ── PDF generation & storage in application_form field ────────────────
        try:
            pdf_content = read_stored_application_form_pdf(self.name)
            if not pdf_content and not self.flags.get("in_pdf_generation"):
                pdf_content = self.generate_application_pdf()
            
            attachments = []
            if pdf_content:
                attachments.append({
                    "fname": f"Application_Form_{self.applicant_id or self.name}.pdf",
                    "fcontent": pdf_content
                })
            elif self.application_form:
                attachments = get_application_attachments(self)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"PDF generation failed for {self.applicant_id or self.name} using format '{print_format_name}'"
            )
            attachments = []

        # ── Send email ────────────────────────────────────────────────────────
        sender = None
        if email_template and email_template.get("email_account"):
            sender = frappe.db.get_value("Email Account", email_template.get("email_account"), "email_id") or email_template.get("email_account")

        cc_list = []
        if email_template and email_template.get("cc"):
            cc_val = email_template.get("cc")
            cc_list = [c.strip() for c in cc_val.replace(";", ",").split(",") if c.strip()]

        frappe.sendmail(
            recipients=[recipient],
            sender=sender,
            cc=cc_list if cc_list else None,
            subject=email_subject,
            message=html_body,
            attachments=attachments,
            reference_doctype=self.doctype,
            reference_name=self.name,
            now=True
        )

        # ── System notification ──────────────────────────────────────────────
        self._create_system_notification(institution_name)
        return True


    def _create_system_notification(self, institution_name):
        """
        Creates a Frappe Notification Log entry so the bell icon in the desk
        shows a notification to the Admission Admin role.
        No new DocType required — uses the built-in Notification Log.
        """
        try:
            # Notify all users who have the Admission Admin role
            admin_users = frappe.get_all(
                "Has Role",
                filters={"role": "Admission Admin", "parenttype": "User"},
                pluck="parent"
            )

            # Also notify the applicant if they have a user account
            applicant_user = frappe.db.get_value("User", {"email": self.email}, "name")
            
            notify_users = set(admin_users)
            if applicant_user:
                notify_users.add(applicant_user)

            for user in notify_users:
                # Skip system/guest users
                if user in ("Administrator", "Guest"):
                    continue

                if user == applicant_user:
                    subject = f"Application Submitted Successfully — {self.name}"
                    msg = (
                        f"Dear <b>{self.candidate_name}</b>,<br><br>"
                        f"Your application for <b>{self.program or 'N/A'}</b> has been successfully submitted (ID: {self.name}).<br>"
                        f"Track your status in the admission portal."
                    )
                else:
                    subject = f"New Application Submitted — {self.name}"
                    msg = (
                        f"<b>{self.candidate_name}</b> has submitted their application "
                        f"for <b>{self.program or 'N/A'}</b> "
                        f"(Cycle: {self.admission_cycle or 'N/A'}, "
                        f"Campus: {self.campus or 'N/A'}).<br><br>"
                        f"Application ID: <b>{self.name}</b><br>"
                        f"Status: <b>{self.status or 'Submitted'}</b>"
                    )

                notification = frappe.get_doc({
                    "doctype": "Notification Log",
                    "subject": subject,
                    "email_content": msg,
                    "for_user": user,
                    "from_user": frappe.session.user if user != applicant_user else "Administrator",
                    "document_type": "Applicant",
                    "document_name": self.name,
                    "type": "Alert",
                    "read": 0,
                })
                notification.insert(ignore_permissions=True)

            frappe.db.commit()

        except Exception:
            # Non-fatal — log but don't break the submission flow
            frappe.log_error(
                frappe.get_traceback(),
                f"System notification failed for {self.name}"
            )


    def _build_default_email_html(self, ctx):
        """
        Returns the hardcoded HTML email body as a fallback when no
        Email Template is configured on the Admission Cycle.
        """
        html_template = """
<html>
<head>
<meta charset="UTF-8">
<style>
    body {
        font-family: Georgia, 'Times New Roman', serif;
        font-size: 14px;
        color: #1a1a1a;
        line-height: 1.7;
        margin: 0;
        padding: 0;
        background: #f0f0f0;
    }
    .wrapper {
        max-width: 600px;
        margin: 32px auto;
        background: #ffffff;
        border: 1px solid #cccccc;
    }
    .header {
        background: #920c24;
        padding: 24px 32px;
        text-align: center;
    }
    .header img {
        max-height: 56px;
        margin-bottom: 10px;
        display: block;
        margin-left: auto;
        margin-right: auto;
    }
    .header h1 {
        color: #ffffff;
        font-size: 16px;
        font-weight: normal;
        letter-spacing: 0.04em;
        margin: 0;
        font-family: Georgia, serif;
    }
    .header .sub {
        color: rgba(255,255,255,0.80);
        font-size: 12px;
        margin-top: 4px;
        font-family: Arial, sans-serif;
    }
    .content {
        padding: 32px 40px;
        font-family: Arial, sans-serif;
    }
    .content p {
        margin: 0 0 16px 0;
        font-size: 14px;
        color: #1a1a1a;
    }
    .ref-box {
        background: #f7f7f7;
        border: 1px solid #dddddd;
        border-left: 4px solid #920c24;
        padding: 14px 18px;
        margin: 20px 0;
        font-family: Arial, sans-serif;
        font-size: 13px;
        color: #1a1a1a;
    }
    .ref-box strong {
        display: block;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #666666;
        margin-bottom: 6px;
    }
    .ref-box .ref-id {
        font-size: 17px;
        font-weight: bold;
        color: #920c24;
        letter-spacing: 0.04em;
    }
    .steps-title {
        font-size: 13px;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #555555;
        border-bottom: 1px solid #dddddd;
        padding-bottom: 6px;
        margin: 28px 0 14px 0;
    }
    .step-list {
        margin: 0;
        padding: 0;
        list-style: none;
    }
    .step-list li {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        margin-bottom: 12px;
        font-size: 13px;
        color: #1a1a1a;
    }
    .step-num {
        background: #920c24;
        color: #ffffff;
        font-size: 11px;
        font-weight: bold;
        min-width: 22px;
        height: 22px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-top: 1px;
        flex-shrink: 0;
    }
    .cta-wrap {
        text-align: center;
        margin: 28px 0 8px 0;
    }
    .cta-link {
        display: inline-block;
        background: #920c24;
        color: #ffffff !important;
        font-size: 13px;
        font-weight: bold;
        padding: 11px 28px;
        text-decoration: none;
        letter-spacing: 0.03em;
        font-family: Arial, sans-serif;
    }
    .cta-fallback {
        text-align: center;
        font-size: 11px;
        color: #888888;
        margin-top: 8px;
        word-break: break-all;
    }
    .cta-fallback a {
        color: #920c24;
    }
    .attachment-note {
        background: #fffbf0;
        border: 1px solid #e8ddb5;
        padding: 11px 16px;
        font-size: 13px;
        color: #4a3c00;
        margin: 24px 0 0 0;
    }
    .footer {
        background: #f7f7f7;
        border-top: 1px solid #dddddd;
        padding: 18px 40px;
        text-align: center;
    }
    .footer .inst-name {
        font-size: 13px;
        font-weight: bold;
        color: #1a1a1a;
        margin-bottom: 4px;
        font-family: Georgia, serif;
    }
    .footer p {
        font-size: 11px;
        color: #888888;
        margin: 3px 0;
        font-family: Arial, sans-serif;
    }
</style>
</head>
<body>
<div class="wrapper">

    <div class="header">
        {% if institution_logo %}
        <img src="{{ institution_logo }}" alt="{{ institution_name }}">
        {% endif %}
        <h1>{{ institution_name }}</h1>
        <div class="sub">Office of Admissions</div>
    </div>

    <div class="content">

        <p>Dear {{ candidate_name }},</p>

        <p>
            We acknowledge receipt of your application to
            <strong>{{ institution_name }}</strong> for the
            <strong>{{ program }}</strong> programme
            for the admission cycle <strong>{{ admission_cycle }}</strong>.
        </p>

        <div class="ref-box">
            <strong>Your Application Reference</strong>
            <span class="ref-id">{{ applicant_id }}</span>
            <span style="font-size:12px;color:#555555;margin-top:4px;display:block;">
                Please quote this reference in all correspondence with the Admissions Office.
            </span>
        </div>

        <p>
            Your completed application form is attached to this email as a PDF.
            Please retain it for your records.
        </p>

        <div class="steps-title">What happens next</div>
        <ul class="step-list">
            <li>
                <span class="step-num">1</span>
                <span>Your application will be reviewed for eligibility. You will be notified by email if any documents or information are required.</span>
            </li>
            <li>
                <span class="step-num">2</span>
                <span>Shortlisted candidates will receive details regarding the entrance test or interview, as applicable to your programme.</span>
            </li>
            <li>
                <span class="step-num">3</span>
                <span>Admit card and examination schedule details will be communicated to eligible candidates in due course.</span>
            </li>
            <li>
                <span class="step-num">4</span>
                <span>You may track the status of your application and complete any pending actions by logging into the admission portal.</span>
            </li>
        </ul>

        <div class="cta-wrap">
            <a class="cta-link" href="{{ admission_portal_url }}" target="_blank" rel="noopener noreferrer">
                Track Your Application
            </a>
        </div>
        <p class="cta-fallback">
            If the button does not open, copy this link into your browser:<br>
            <a href="{{ admission_portal_url }}">{{ admission_portal_url }}</a>
        </p>

        <div class="attachment-note">
            <strong>Note:</strong> Please check your spam or promotions folder if you do not receive further communications. Keep your original documents ready for verification when requested.
        </div>

    </div>

    <div class="footer">
        <p class="inst-name">{{ institution_name }}</p>
        <p>This is a system-generated email. Please do not reply to this message.</p>
        <p>For assistance, contact the Admissions Helpdesk.</p>
        <p style="margin-top:8px;">
            Ref: {{ applicant_id }} &nbsp;|&nbsp; Generated: {{ generated_on }}
        </p>
    </div>

</div>
</body>
</html>
"""
        return frappe.render_template(html_template, ctx)

    def send_completion_confirmation(self):
        """
        Sends a formatted confirmation email when the application is completely processed (fee paid).
        - Uses the template from the Admission Cycle's `application_completed_email` field.
        - Falls back to 'Application Completed Email' template.
        - Generates and attaches PDF application form.
        - Fetches and attaches Applicant Payment Receipt PDF if it exists.
        """
        recipient = self.email
        if not recipient:
            return False

        # ── Resolve email template name ────────────────────────────────────────
        email_template_name = "Application Completed Email"
        if self.admission_cycle:
            cycle_template = frappe.db.get_value("Admission Cycle", self.admission_cycle, "application_completed_email")
            if cycle_template:
                email_template_name = cycle_template

        # ── Context dict for template rendering ──────────────────────────────
        doc_dict = self.as_dict() if hasattr(self, "as_dict") else self
        institution_name = frappe.db.get_single_value("Institution Settings", "institution_name") or "Admissions Office"
        institution_logo = frappe.db.get_single_value("Institution Settings", "logo") or ""
        if institution_logo and not institution_logo.startswith("http"):
            institution_logo = frappe.utils.get_url(institution_logo)
        admission_portal_url = frappe.utils.get_url("/admission/login#login")

        template_context = {
            "doc": doc_dict,
            "applicant_id": self.applicant_id or self.name,
            "applicant_document_id": self.name,
            "candidate_name": self.candidate_name or "",
            "program": self.program or "—",
            "program_name": frappe.db.get_value("Programme", self.program, "program_name") if self.program else "—",
            "admission_cycle": self.admission_cycle or "—",
            "campus": self.campus or "—",
            "application_fee_amount": frappe.utils.fmt_money(self.application_fee_amount, currency="INR") if self.application_fee_amount else "—",
            "institution_name": institution_name,
            "institution_logo": institution_logo,
            "admission_portal_url": admission_portal_url,
            "generated_on": frappe.utils.now_datetime().strftime("%d %b %Y, %I:%M %p"),
        }

        email_subject = f"Application Completed — {self.applicant_id or self.name} | {self.program or 'Admissions'}"
        html_body = None
        email_template = None

        if frappe.db.exists("Email Template", email_template_name):
            try:
                email_template = frappe.get_doc("Email Template", email_template_name)
                if email_template.get("subject"):
                    email_subject = frappe.render_template(email_template.subject, template_context)
                
                if email_template.get("use_html") and email_template.get("response_html"):
                    html_body = frappe.render_template(email_template.response_html, template_context)
                elif email_template.get("response"):
                    html_body = frappe.render_template(email_template.response, template_context)

                if not html_body:
                    html_body = frappe.render_template(email_template.get("message") or "", template_context)
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"Email template render failed for {self.name}, falling back")
                html_body = None

        if not html_body:
            return False

        # ── Attachments (Application Form + Receipt) ─────────────────────────
        attachments = []
        
        # 1. Application Form PDF
        try:
            pdf_content = read_stored_application_form_pdf(self.name)
            if not pdf_content and not self.flags.get("in_pdf_generation"):
                pdf_content = self.generate_application_pdf()
            if pdf_content:
                attachments.append({
                    "fname": f"Application_Form_{self.applicant_id or self.name}.pdf",
                    "fcontent": pdf_content
                })
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Application PDF generation failed in completion email")

        # 2. Payment Receipt PDF
        try:
            receipt_name = frappe.db.get_value(
                "Applicant Payment Receipt",
                {"applicant": self.name, "fee_type": "Application Fee", "docstatus": ["<", 2]},
                "name",
                order_by="creation desc"
            )
            if receipt_name:
                receipt = frappe.get_doc("Applicant Payment Receipt", receipt_name)
                receipt_pdf_content = None
                if receipt.receipt_pdf:
                    from frappe.utils.file_manager import get_file_path
                    import os
                    file_path = get_file_path(receipt.receipt_pdf)
                    if file_path and os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            receipt_pdf_content = f.read()
                
                if not receipt_pdf_content:
                    print_format = receipt.get("payment_receipt_template") or "Applicant Payment Receipt"
                    receipt_pdf_content = frappe.get_print(
                        "Applicant Payment Receipt",
                        receipt.name,
                        print_format,
                        as_pdf=True,
                    )
                
                if receipt_pdf_content:
                    attachments.append({
                        "fname": f"Payment_Receipt_{self.applicant_id or self.name}.pdf",
                        "fcontent": receipt_pdf_content
                    })
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Receipt PDF generation failed in completion email")

        # ── Send email ────────────────────────────────────────────────────────
        sender = None
        if email_template and email_template.get("email_account"):
            sender = frappe.db.get_value("Email Account", email_template.get("email_account"), "email_id") or email_template.get("email_account")

        cc_list = []
        if email_template and email_template.get("cc"):
            cc_val = email_template.get("cc")
            cc_list = [c.strip() for c in cc_val.replace(";", ",").split(",") if c.strip()]

        frappe.sendmail(
            recipients=[recipient],
            sender=sender,
            cc=cc_list if cc_list else None,
            subject=email_subject,
            message=html_body,
            attachments=attachments,
            reference_doctype=self.doctype,
            reference_name=self.name,
            now=True
        )
        return True


    # ──────────────────────────────────────────────
    # APPLICANT CATEGORY HELPER
    # ──────────────────────────────────────────────

    def _get_applicant_categories(self):
        """
        Derive the applicant's Admission Category set from the existing
        reservation fields in the eligibility_for_reservation_tab.

        Field → Admission Category mapping (static, matches DB records):
          whether_scstobc_ncl  (not "General")  →  OBC-NCL / ST / SC
          pwd == "Yes"                     →  PWD
          karnataka_category == "Yes"      →  Karnataka

        Returns a set of category name strings.
        """
        cats = set()

        sc_st_obc = (getattr(self, "whether_scstobc_ncl", None) or "").strip()
        if sc_st_obc and sc_st_obc.lower() != "general":
            cats.add(sc_st_obc)  # Only include real categories like "OBC-NCL", "ST", or "SC"
        else:
            cats.add("General")

        if (getattr(self, "pwd", None) or "").strip() == "Yes":
            cats.add("PWD")

        if (getattr(self, "karnataka_category", None) or "").strip() == "Yes":
            cats.add("Karnataka")

        if getattr(self, "gender", None) == "Female":
            cats.add("Women")

        return cats

    # ──────────────────────────────────────────────
    # CHILD TABLE VALUE HELPERS
    # ──────────────────────────────────────────────

    def _get_ug_cgpa_values(self):
        """Return a list of all UG CGPA values from the ug_degree_details child table."""
        rows = getattr(self, "ug_degree_details", None) or []
        return [flt(row.ug_cgpa) for row in rows if row.ug_cgpa not in (None, "")]

    def _get_pg_cgpa_values(self):
        """Return a list of all PG CGPA values from the pg_degree_details child table."""
        rows = getattr(self, "pg_degree_details", None) or []
        return [flt(row.pg_cgpa) for row in rows if row.pg_cgpa not in (None, "")]

    @frappe.whitelist()
    def waive_fee(self):
        """Admin marks fee as waived — records who waived and when."""
        self.application_fee_status = "Waived"
        self.fee_waived_by = frappe.session.user
        self.fee_waived_on = frappe.utils.now()
        self.save(ignore_permissions=True)
        frappe.get_doc({
            "doctype": "Admission Audit Log",
            "action": "Fee Waived",
            "reference_doctype": "Applicant",
            "reference_name": self.name,
            "performed_by": frappe.session.user,
            "reason": "Application fee waived by admin"
        }).insert(ignore_permissions=True)

    def _get_ug_programs(self):
        """Return a list of all UG programs from the ug_degree_details child table."""
        rows = getattr(self, "ug_degree_details", None) or []
        return [row.ug_program for row in rows if row.ug_program]

    def _get_pg_programs(self):
        """Return a list of all PG programs from the pg_degree_details child table."""
        rows = getattr(self, "pg_degree_details", None) or []
        return [row.pg_program for row in rows if row.pg_program]

    def _get_applicant_hsc_groups(self):
        """
        Return the applicant's HSC group as a set (single value from hsc_group field).
        """
        hsc_group = getattr(self, "hsc_group", None)
        if hsc_group:
            return {hsc_group.strip()}
        return set()

    # ──────────────────────────────────────────────
    # PROGRAM LEVEL HELPER
    # ──────────────────────────────────────────────

    def _get_selected_program_level(self):
        """
        Returns the level_of_study ('Undergraduate', 'Postgraduate', 'Research Course') of the
        currently selected program by querying the Program doctype.

        NOTE: The correct DB column is `level_of_study`.
        `program_level` is a different (often-null) field on older data.

        Returns None if not found.
        """
        if not self.program:
            return None
        return frappe.db.get_value("Programme", self.program, "level_of_study")

    def _get_all_programs_for_level(self, program_level):
        """
        Returns programs of the same level that are part of the ACTIVE admission cycle.
        Prioritizes the applicant's linked admission cycle if set.

        This ensures the eligibility table shows programs from the current admission cycle —
        not just EVERY program of the same level from the Program doctype.
        """
        if not program_level:
            return []

        # 1. Use the applicant's cycle if set
        cycle = self.admission_cycle

        # 2. If not set, look for any 'Active' cycle
        if not cycle:
            cycle = frappe.db.get_value("Admission Cycle", {"status": "Active"}, "name")

        if cycle:
            # Fetch programs from the selected cycle that match the level
            # We filter by acp.is_active = 1 (Show on Portal)
            programs = frappe.db.sql("""
                SELECT DISTINCT acp.program
                FROM `tabAdmission Cycle Program` acp
                JOIN `tabProgramme` p ON p.name = acp.program
                WHERE acp.parent = %(cycle)s
                  AND acp.is_active = 1
                  AND p.level_of_study = %(program_level)s
                ORDER BY acp.program ASC
            """, {
                "cycle": cycle,
                "program_level": program_level
            }, as_dict=True)

            if programs:
                return [row.program for row in programs if row.program]

        # 3. Fallback: all programs of that level if no cycle or no programs found in cycle
        programs = frappe.db.sql("""
            SELECT name AS program
            FROM `tabProgramme`
            WHERE level_of_study = %(program_level)s
            ORDER BY name ASC
        """, {"program_level": program_level}, as_dict=True)

        return [row.program for row in programs if row.program]

    # ──────────────────────────────────────────────
    # CORE ELIGIBILITY LOGIC
    # ──────────────────────────────────────────────

    def validate_eligibility(self):
        """
        Main eligibility entry point.

        Flow:
        ─────
        STEP 0 — National Test Exemption check.
        STEP 1 — Academic Eligibility Rule Mapping checks.

        KEY BEHAVIOUR:
        ─────────────
        On ineligibility:
          1. Sets self.evaluation_status = "Ineligible" and self.rejected_reason.
          2. Calls create_or_update_evaluation() IMMEDIATELY — so the Ineligible
             record is persisted to the Eligibility Evaluation doctype BEFORE the
             throw. Without this, frappe.throw() exits the call stack and the
             save in validate() never runs, meaning ineligible records are lost.
          3. Raises a single frappe.throw() containing:
               • Red reason box  (the specific failure message)
               • Full program table  (all same-level programs + full eligibility check)

        On eligibility:
          1. Sets self.evaluation_status = "Eligible".
          2. Calls create_or_update_evaluation() here (NOT in validate()).
             This prevents the double-save duplicate record bug.
        """

        if not all([self.program, self.campus, self.admission_cycle, self.academic_year]):
            self.evaluation_status = ""
            self.rejected_reason = ""
            self._slcm_failure_sections = None
            self._clear_national_test_flags()
            return

        try:
            self._slcm_failure_sections = None
            # ── STEP 0: National Test Exemption ─────────────────────────────
            national_test_result = self._evaluate_national_test_exemption()

            if national_test_result.get("passed") and national_test_result.get("overrides_academic_rule"):
                # Passed national test AND rule overrides academic checks → Eligible immediately
                self.evaluation_status = "Eligible"
                self.rejected_reason   = ""
                self._apply_national_test_flags(national_test_result)

                # Save the eligible record here (not in validate())
                program_table_html = self._build_program_eligibility_html()
                self.create_or_update_evaluation(program_details_html=program_table_html)

                frappe.msgprint(
                    _("Eligible via National Test ({0}). Academic rule check bypassed.").format(
                        self.national_test_name or ""
                    ),
                    title=_("National Test Exemption Applied"),
                    indicator="green"
                )
                return

            # National test passed but does NOT override → store flags, continue
            if national_test_result.get("passed"):
                self._apply_national_test_flags(national_test_result)
            else:
                self._clear_national_test_flags()

            # ── STEP 1: Academic Eligibility Rule Mapping checks ─────────────
            rule_mappings = self._get_rule_mappings_for_applicant()

            if not rule_mappings:
                # No mapping found → no restriction → eligible
                self.evaluation_status = "Eligible"
                self.rejected_reason   = ""
                # Save eligible record here (not in validate())
                program_table_html = self._build_program_eligibility_html()
                self.create_or_update_evaluation(program_details_html=program_table_html)
                return

            for mapping in rule_mappings:
                is_eligible, failure_message = self._evaluate_mapping_with_category_priority(mapping)

                if not is_eligible:
                    self.evaluation_status  = "Ineligible"
                    self.status = "Rejected"
                    self.rejected_reason    = failure_message

                    # ── Build combined HTML: reason box + program table ────────
                    program_table_html = self._build_program_eligibility_html()

                    # ── CRITICAL: Save the Ineligible record NOW, before throw ──
                    # frappe.throw() raises ValidationError which unwinds the stack,
                    # so create_or_update_evaluation() would never execute after throw.
                    # We must save here explicitly before throwing.
                    self.create_or_update_evaluation(program_details_html=program_table_html)

                    # Portal calls validate_eligibility with flags.skip_eligibility_throw so the
                    # web form can show its own dialog — frappe.throw also triggers a second
                    # Frappe msgprint-style modal on the client.
                    if getattr(self.flags, "skip_eligibility_throw", False):
                        return

                    full_message = self._build_ineligibility_message(failure_message, program_table_html)

                    # ONE single frappe.throw() — contains reason box + program table
                    # NOTE: allow_dangerous_html=True is required for modern Frappe versions (v15+)
                    # to render styles correctly. We check dynamically to avoid TypeError on older versions.
                    throw_kwargs = {
                        "msg": full_message,
                        "title": _("Eligibility Evaluation Results"),
                        "wide": True,
                    }

                    import inspect
                    if "allow_dangerous_html" in inspect.signature(frappe.throw).parameters:
                        throw_kwargs["allow_dangerous_html"] = True

                    frappe.throw(**throw_kwargs)
                    return

            # Passed all mappings → Eligible
            self.evaluation_status = "Eligible"
            self.rejected_reason   = ""
            program_table_html = self._build_program_eligibility_html()
            self.create_or_update_evaluation(program_details_html=program_table_html)

        except frappe.ValidationError:
            # Standard validation failure — let it raise naturally for the frontend
            raise
        except Exception:
            # Unexpected system error — log it to Error Log then raise
            frappe.log_error(frappe.get_traceback(), "Applicant Eligibility Validation Error")
            raise

    # ──────────────────────────────────────────────
    # INELIGIBILITY MESSAGE BUILDER  (Frappe-native)
    # ──────────────────────────────────────────────

    def _build_ineligibility_message(self, failure_message, program_table_html):
        """
        Builds a high-end, premium ineligibility message with focused styling for 
        required vs secured scores and specific eligibility mismatches.
        """
        # Split combined message if it contains '|' (multi-reason support)
        reasons_list = []
        if "|" in failure_message:
            parts = failure_message.split("|")
            main_reason = parts[0].strip()
            sub_reasons = " ".join(parts[1:]).strip()
            reason_html = (
                f"{frappe.utils.escape_html(main_reason)}"
                f"<div style='font-weight: 400; font-size: 12px; color: #666; margin-top: 4px;'>"
                f"{frappe.utils.escape_html(sub_reasons)}</div>"
            )
        else:
            reason_html = frappe.utils.escape_html(failure_message)

        return (
            '<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif;">'
            '<!-- ── Ineligibility Alert ───────────────────────────────── -->'
            '<div style="display: flex; align-items: flex-start; gap: 10px; margin-bottom: 16px; padding: 12px 16px; '
            'background-color: #fff2f2; border: 1px solid #f5c6cb; border-left: 4px solid #e74c3c; border-radius: 6px;">'
            '<span style="display: inline-block; width: 10px; height: 10px; background-color: #e74c3c; border-radius: 50%; '
            'margin-top: 4px; flex-shrink: 0;"></span>'
            '<div>'
            '<div style="font-weight: 600; font-size: 14px; color: #c0392b;">{reason}</div>'
            '<div style="font-size: 12px; color: #666; margin-top: 3px;">{note}</div>'
            '</div>'
            '</div>'
            '<!-- ── Program Options ───────────────────────────────────── -->'
            '{table}'
            '</div>'
        ).format(
            reason=reason_html,
            note=_("The applicant does not meet the eligibility criteria for the selected program."),
            table=program_table_html,
        )

    def get_eligibility_suggestion_payload(self):
        """
        Portal / web-form: structured list of same-level programs the applicant can switch to.
        Only programs passing _check_eligibility_for_program are included.
        """
        selected_program_level = self._get_selected_program_level()
        if not selected_program_level:
            return {
                "programs": [],
                "eligible_count": 0,
                "total_count": 0,
                "level": "",
                "campus": self.campus or "",
                "cycle": self.admission_cycle or "",
            }

        all_programs = self._get_all_programs_for_level(selected_program_level)
        programs_out = []
        eligible_count = 0

        for prog_name in all_programs:
            is_ok, _reason = self._check_eligibility_for_program(prog_name)
            if not is_ok:
                continue
            eligible_count += 1
            display = frappe.db.get_value("Programme", prog_name, "program_name") or prog_name
            programs_out.append(
                {
                    "program": prog_name,
                    "program_name": display,
                    "selected": prog_name == self.program,
                }
            )

        return {
            "programs": programs_out,
            "eligible_count": eligible_count,
            "total_count": len(all_programs),
            "level": selected_program_level,
            "campus": self.campus or "",
            "cycle": self.admission_cycle or "",
        }

    # ──────────────────────────────────────────────
    # PROGRAM ELIGIBILITY TABLE (rendered inside throw)
    # ──────────────────────────────────────────────

    def _build_program_eligibility_data(self):
        """
        Returns a list of dicts for EVERY program of the SAME LEVEL as the
        applicant's selected program (UG / PG / Research Course).
        Used by the portal 'Switch Program' feature.
        """
        selected_program_level = self._get_selected_program_level()
        if not selected_program_level:
            return []

        all_programs = self._get_all_programs_for_level(selected_program_level)
        if not all_programs:
            return []

        data = []
        for prog_name in all_programs:
            is_eligible, reason = self._check_eligibility_for_program(prog_name)
            data.append({
                "program": prog_name,
                "eligible": is_eligible,
                "reason": reason
            })
        return data

    def _build_program_eligibility_html(self):
        """
        Returns styled HTML listing EVERY program of the SAME LEVEL as the
        applicant's selected program (UG / PG / Research Course).

        FIX — Previously only showed programs that had eligibility rules configured.
        Now shows ALL programs from the Program doctype with matching program_level:
          • Programs WITH eligibility rules → full eligibility check (pass/fail + reason)
          • Programs WITHOUT eligibility rules → shown as "Eligible" (no restriction)
          • Programs of a DIFFERENT level (e.g., PG when applicant applied for UG)
            are completely excluded — they are irrelevant to the applicant.

        The currently selected program is marked with a "Selected" badge.
        """

        # Get the level of the selected program (UG / PG / Research Course)
        selected_program_level = self._get_selected_program_level()

        if not selected_program_level:
            return (
                "<p style='color:#888;font-size:12px;'>{0}</p>".format(
                    _("Could not determine program level for the selected program.")
                )
            )

        # Get ALL programs of the same level from Program doctype
        all_programs = self._get_all_programs_for_level(selected_program_level)

        if not all_programs:
            return (
                "<p style='color:#888;font-size:12px;'>{0}</p>".format(
                    _("No programs found for program level: {0}").format(selected_program_level)
                )
            )

        rows_html        = ""
        eligible_count   = 0
        ineligible_count = 0

        for prog_name in all_programs:
            is_prog_eligible, reason = self._check_eligibility_for_program(prog_name)
            is_selected = (prog_name == self.program)

            if not is_prog_eligible:
                ineligible_count += 1
                continue

            eligible_count += 1
            dot_color    = "#27ae60"
            status_label = _("Eligible")
            status_color = "#27ae60"
            row_bg       = "#fff"

            # Program name cell — bold + "Selected" badge for the active program
            if is_selected:
                prog_display = """
                    <strong style="color:#2c3e50;">{name}</strong>
                    &nbsp;<span style="
                        font-size: 10px;
                        padding: 2px 8px;
                        background-color: #3498db;
                        color: #fff;
                        border-radius: 10px;
                        font-weight: 600;
                        vertical-align: middle;
                    ">{label}</span>
                """.format(
                    name  = frappe.utils.escape_html(prog_name),
                    label = _("Selected"),
                )
            else:
                prog_display = "<span style='color:#2c3e50;'>{0}</span>".format(
                    frappe.utils.escape_html(prog_name)
                )

            rows_html += """
                <tr style="background-color:{row_bg};">
                    <td style="padding:10px 12px;vertical-align:middle;border-bottom:1px solid #eee;">
                        {prog}
                    </td>
                    <td style="padding:10px 12px;vertical-align:middle;text-align:center;white-space:nowrap;border-bottom:1px solid #eee;">
                        <span style="
                            display: inline-block;
                            width: 8px;
                            height: 8px;
                            background-color: {dot};
                            border-radius: 50%;
                            vertical-align: middle;
                            margin-right: 4px;
                        "></span>
                        <span style="font-size:13px;font-weight:500;color:{status_color};">{status}</span>
                    </td>
                </tr>
            """.format(
                row_bg       = row_bg,
                prog         = prog_display,
                dot          = dot_color,
                status_color = status_color,
                status       = status_label,
            )

        # ── Summary counts ───────────────────────────────────────────────────
        summary_html = (
            '<div style="display:flex;align-items:center;gap:16px;margin-bottom:12px;flex-wrap:wrap;">'
            '<span style="display:inline-flex;align-items:center;gap:6px;">'
            '<span style="display:inline-block;width:8px;height:8px;background:#27ae60;border-radius:50%;"></span>'
            '<strong style="color:#2c3e50;">{ec}</strong>'
            '<span style="font-size:12px;color:#888;">{el}</span>'
            '</span>'
            '<span style="font-size:12px;color:#aaa;">({total}&nbsp;{tl})</span>'
            '</div>'
        ).format(
            ec    = eligible_count,
            el    = _("eligible programs found"),
            total = eligible_count + ineligible_count,
            tl    = _("total same-level programs"),
        )

        # ── Section heading ──────────────────────────────────────────────────
        heading_html = (
            '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px;">'
            '<span style="font-weight:700;font-size:14px;color:#2c3e50;">{heading}</span>'
            '<span style="font-size:12px;color:#888;">&mdash;&nbsp;{campus}&nbsp;&middot;&nbsp;{cycle}&nbsp;&middot;&nbsp;{level}</span>'
            '</div>'
        ).format(
            heading = _("Suggested Eligible Programs"),
            campus  = frappe.utils.escape_html(self.campus or ""),
            cycle   = frappe.utils.escape_html(self.admission_cycle or ""),
            level   = frappe.utils.escape_html(selected_program_level or ""),
        )

        # ── Full table ───────────────────────────────────────────────────────
        table_html = (
            '<div style="margin-top:8px;">'
            '{heading}'
            '<hr style="margin:6px 0 12px 0;border:none;border-top:1px solid #eee;">'
            '{summary}'
            '<div style="overflow-x:auto;">'
            '<table style="width: 100%; border-collapse: collapse; border: 1px solid #e0e0e0; border-radius: 6px; overflow: hidden; font-size: 13px;">'
            '<thead>'
            '<tr style="background-color:#f8f9fa;">'
            '<th style="padding:10px 12px;text-align:left;font-weight:600;color:#555;width:70%;border-bottom:2px solid #e0e0e0;">{col1}</th>'
            '<th style="padding:10px 12px;text-align:center;font-weight:600;color:#555;border-bottom:2px solid #e0e0e0;">{col2}</th>'
            '</tr>'
            '</thead>'
            '<tbody>'
            '{rows}'
            '</tbody>'
            '</table>'
            '</div>'
            '</div>'
        ).format(
            heading = heading_html,
            summary = summary_html,
            col1    = _("Programme"),
            col2    = _("Status"),
            rows    = rows_html,
        )

        return table_html

    def _check_eligibility_for_program(self, program_name):
        """
        Runs the full eligibility engine for a given program using the current
        applicant's scores, categories, campus, admission_cycle, and academic_year —
        WITHOUT permanently modifying self.

        Temporarily swaps self.program → runs check → restores original in finally.

        KEY BEHAVIOUR for programs WITHOUT eligibility rules:
          If no rule mappings exist for a program, it is treated as Eligible
          (no restriction configured = open to all applicants of that level).

        Returns (is_eligible: bool, failure_message: str)
        """
        original_program = self.program
        prev_failure_sections = getattr(self, "_slcm_failure_sections", None)
        try:
            self.program = program_name

            # National test exemption for this program
            national_test_result = self._evaluate_national_test_exemption()
            if (national_test_result.get("passed")
                    and national_test_result.get("overrides_academic_rule")):
                return True, ""

            # Rule mappings for this program (direct link now)
            # Determine applicant type from foriegn_national field (Yes = International, No/blank = Domestic)
            applicant_type = "International Applicants" if getattr(self, "foriegn_national", "") == "Yes" else "Domestic Applicants"
            rule_mappings = frappe.db.sql("""
                SELECT erm.name
                FROM `tabEligibility Rule Mapping` erm
                WHERE erm.is_active       = 1
                  AND erm.campus          = %(campus)s
                  AND erm.admission_cycle = %(admission_cycle)s
                  AND erm.program         = %(program)s
                  AND (erm.applicant_type = %(applicant_type)s OR erm.applicant_type = 'Both')
            """, {
                "campus":          self.campus,
                "admission_cycle": self.admission_cycle,
                "program":         program_name,
                "applicant_type":  applicant_type,
            }, as_dict=True)

            # No rule mapping → no restriction → eligible
            if not rule_mappings:
                return True, ""

            for mapping in rule_mappings:
                is_eligible, failure_message = self._evaluate_mapping_with_category_priority(mapping)
                if not is_eligible:
                    return False, failure_message

            return True, ""

        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "Program Eligibility Check Error — {0}".format(program_name)
            )
            return False, _("Error during eligibility check")
        finally:
            self.program = original_program
            self._slcm_failure_sections = prev_failure_sections

    # ──────────────────────────────────────────────
    # NATIONAL TEST EXEMPTION
    # ──────────────────────────────────────────────

    def _evaluate_national_test_exemption(self):
        """
        Check if the applicant qualifies under a National Test Exemption Rule.

        Returns a dict:
        {
            "passed":                  bool,
            "overrides_academic_rule": bool,
            "exempts_entrance_test":   bool,
            "exempts_interview":       bool,
            "rule_name":               str,
        }
        """
        empty = {
            "passed":                  False,
            "overrides_academic_rule": False,
            "exempts_entrance_test":   False,
            "exempts_interview":       False,
            "rule_name":               "",
        }

        national_test = getattr(self, "national_test_name", None)
        applicant_pct = flt(getattr(self, "percentage", None) or 0)

        if not national_test:
            return empty

        exemption_rules = frappe.db.sql("""
            SELECT
                nter.name,
                nter.mark_percentage,
                nter.operator,
                nter.overrides_academic_rule,
                nter.exempts_entrance_test,
                nter.exempts_interview
            FROM `tabNational Test Exemption Rule` nter
            INNER JOIN `tabEligibility Allowed Degree` ead
                ON ead.parent      = nter.name
               AND ead.degree_name = %(program)s
            WHERE nter.is_active        = 1
              AND nter.campus           = %(campus)s
              AND nter.admission_cycle  = %(admission_cycle)s
              AND nter.academic_year    = %(academic_year)s
              AND nter.national_test    = %(national_test)s
            ORDER BY nter.mark_percentage DESC
            LIMIT 1
        """, {
            "program":         self.program,
            "campus":          self.campus,
            "admission_cycle": self.admission_cycle,
            "academic_year":   self.academic_year,
            "national_test":   national_test,
            "today":           nowdate(),
        }, as_dict=True)

        if not exemption_rules:
            return empty

        rule         = exemption_rules[0]
        required_pct = flt(rule.get("mark_percentage") or 0)
        operator     = rule.get("operator") or ">="
        passed       = self._compare(applicant_pct, required_pct, operator)

        return {
            "passed":                  passed,
            "overrides_academic_rule": bool(rule.get("overrides_academic_rule")),
            "exempts_entrance_test":   bool(rule.get("exempts_entrance_test")),
            "exempts_interview":       bool(rule.get("exempts_interview")),
            "rule_name":               rule.get("name", ""),
        }

    def _apply_national_test_flags(self, result):
        self.exempts_entrance_test   = 1 if result.get("exempts_entrance_test")   else 0
        self.exempts_interview       = 1 if result.get("exempts_interview")        else 0
        self.national_test_rule_used = result.get("rule_name", "")

    def _clear_national_test_flags(self):
        self.exempts_entrance_test   = 0
        self.exempts_interview       = 0
        self.national_test_rule_used = ""

    # ──────────────────────────────────────────────
    # STEP 1 — Fetch matching rule mappings
    # ──────────────────────────────────────────────

    def _get_rule_mappings_for_applicant(self):
        # Determine applicant type from foriegn_national field (Yes = International, No/blank = Domestic)
        applicant_type = "International Applicants" if getattr(self, "foriegn_national", "") == "Yes" else "Domestic Applicants"
        return frappe.db.sql("""
            SELECT erm.name
            FROM `tabEligibility Rule Mapping` erm
            WHERE erm.is_active         = 1
              AND erm.campus            = %(campus)s
              AND erm.admission_cycle   = %(admission_cycle)s
              AND erm.program           = %(program)s
              AND (erm.applicant_type   = %(applicant_type)s OR erm.applicant_type = 'Both')
        """, {
            "campus":          self.campus,
            "admission_cycle": self.admission_cycle,
            "program":         self.program,
            "applicant_type":  applicant_type,
        }, as_dict=True)

    # ──────────────────────────────────────────────
    # STEP 2 — Multi-category priority engine
    # ──────────────────────────────────────────────

    def _allowed_hsc_groups_for_rule(self, rule_name):
        rows = frappe.db.sql("""
            SELECT hsc_groups
            FROM `tabHSC Groups Mapping`
            WHERE parent = %(rule_name)s
              AND parenttype = 'Eligibility Rule'
              AND hsc_groups IS NOT NULL
              AND hsc_groups != ''
        """, {"rule_name": rule_name}, as_dict=True)
        return [
            row.hsc_groups.strip()
            for row in rows
            if row.get("hsc_groups")
        ]

    def _build_rule_failure_reason(self, base_rule, applied_threshold, cat_row=None):
        """
        Human-readable failure copy for applicants (no internal rule IDs).
        Uses short titled sections and bullet lines; joined with newlines for the portal modal.
        """
        qualification_level = base_rule.get("qualification_level") or "Academic"
        rule_type = base_rule.get("rule_type")
        operator = base_rule.get("operator") or ">="

        unit = ""
        is_cgpa = (rule_type == "CGPA" or "cgpa" in (base_rule.get("unit_type") or "").lower())
        if is_cgpa:
            unit = " CGPA"
        else:
            unit = "%"

        display_level = "HSC (Class XII)" if qualification_level == "XII" else qualification_level
        applicant_val = self._get_applicant_value(base_rule)

        score_failed = bool(
            applied_threshold
            and applicant_val > 0
            and not self._compare(applicant_val, applied_threshold, operator)
        )
        non_pct_failed = not self._evaluate_non_percentage_checks(base_rule)

        blocks = []

        # ── Block 1: Marks — reservation paths use neutral “Minimum required” (actual
        #    threshold for the evaluated path) + “You secured”; we omit the old
        #    “for your category” / “general-category baseline” pair of lines.
        score_lines = []
        has_general_header = False

        def append_lines(l_display, l_threshold, l_app_val, l_failed):
            nonlocal has_general_header
            if not cat_row or not (cat_row.get("category") or "").strip():
                if not has_general_header:
                    score_lines.append(_("Academic requirement (general)"))
                    has_general_header = True
            
            if l_failed:
                if l_threshold is not None:
                    score_lines.append(_("• Minimum required ({0}): {1}{2}").format(l_display, flt(l_threshold), unit))
                score_lines.append(_("• You secured ({0}): {1}{2}").format(l_display, flt(l_app_val), unit))
            elif l_threshold and l_app_val <= 0:
                score_lines.append(_("• Your {0} marks were not found or are zero; minimum required is {1}{2}.").format(l_display, flt(l_threshold), unit))

        append_lines(display_level, applied_threshold, applicant_val, score_failed)

        if qualification_level == "XII":
            sslc_threshold = None
            if cat_row and cat_row.get("minimum_percentage_sslc"):
                sslc_threshold = flt(cat_row.minimum_percentage_sslc)
            elif base_rule.get("sslc_percentage"):
                sslc_threshold = flt(base_rule.get("sslc_percentage"))
                
            if sslc_threshold:
                applicant_sslc = flt(getattr(self, "class_x_percentage", None) or 0)
                sslc_failed = bool(sslc_threshold and applicant_sslc > 0 and not self._compare(applicant_sslc, sslc_threshold, operator))
                
                # Check if we should append SSLC lines (either failed or missing)
                if sslc_failed or (sslc_threshold and applicant_sslc <= 0):
                    append_lines("Class X", sslc_threshold, applicant_sslc, sslc_failed)

        if cat_row and (cat_row.get("category") or "").strip():
            if score_lines:
                blocks.append("\n".join(score_lines))
        elif len(score_lines) > 1:
            blocks.append("\n".join(score_lines))

        # ── Block 2: HSC group / degree rules ──
        if non_pct_failed:
            if rule_type == "HSC Group" and not self._check_hsc_group_eligibility(base_rule.name):
                applicant_group = (getattr(self, "hsc_group", None) or "").strip() or _("Not provided")
                allowed_g = self._allowed_hsc_groups_for_rule(base_rule.name)
                glines = [_("{0} stream / group").format(display_level)]
                if allowed_g:
                    glines.append(_("• Allowed: {0}").format(", ".join(allowed_g)))
                glines.append(_("• You have: {0}").format(applicant_group))
                blocks.append("\n".join(glines))
            else:
                rule_allowed = frappe.get_all(
                    "Eligibility Allowed Degree",
                    filters={"parent": base_rule.name},
                    pluck="degree_name",
                )
                applicant_studied = []
                if qualification_level == "Undergraduate":
                    applicant_studied = [
                        r.ug_program for r in (self.get("ug_degree_details") or []) if r.ug_program
                    ]
                elif qualification_level == "Postgraduate":
                    applicant_studied = [
                        r.pg_program for r in (self.get("pg_degree_details") or []) if r.pg_program
                    ]
                studied_val = ", ".join(applicant_studied) if applicant_studied else _("Not provided")
                if rule_allowed:
                    dlines = [_("{0} qualification — degrees").format(display_level)]
                    dlines.append(_("• Allowed: {0}").format(", ".join(rule_allowed)))
                    dlines.append(_("• You have: {0}").format(studied_val))
                    blocks.append("\n".join(dlines))
                elif not blocks:
                    blocks.append(_("Program mismatch for {0} qualification.").format(display_level))

        custom_rule_msg = ""

        if not blocks:
            return ""

        return "\n\n".join(blocks)

    @staticmethod
    def _dedupe_eligibility_portal_lines(text: str) -> str:
        """
        Collapse repeated lines (e.g. same “You secured …” / rule ineligible_message) when
        several Rule Mapping rows fail for one mapping — one line per distinct message, order kept.
        """
        if not (text or "").strip():
            return (text or "").strip()
        seen: set[str] = set()
        out_lines: list[str] = []
        for raw in (text or "").splitlines():
            line = raw.rstrip()
            key = " ".join(line.split()).strip().casefold()
            if not key:
                out_lines.append("")
                continue
            if key in seen:
                continue
            seen.add(key)
            out_lines.append(line.strip())
        result = "\n".join(out_lines).strip()
        while "\n\n\n" in result:
            result = result.replace("\n\n\n", "\n\n")
        return result

    def _evaluate_mapping_with_category_priority(self, mapping):
        """
        Comprehensive eligibility engine:
        Checks ALL categories the applicant belongs to (against the mapping table)
        AND the 'General' (default) path using 'OR' logic.

        Result: Eligible if ANY (Category, Rule) combination passes.

        Portal messaging when ineligible:
        • No reservation row matches the applicant’s categories → show failures for the General
          path only (thresholds from the Eligibility Rule).
        • One or more rows match → show failure copy for the single row with the lowest
          priority number (1 before 2), i.e. the primary mapping category — not every matched
          row and not the General path, so applicants do not see multiple “required %” lines.
        Eligibility itself is still OR across all paths (any pass → eligible).
        """
        mapping_name = mapping.get("name")
        failure_msg  = "You do not meet the eligibility criteria for the selected program."

        # 1. Fetch ALL rules for this mapping
        rules_in_mapping = frappe.db.get_all("Rule Mapping",
            filters={"parent": mapping_name},
            fields=["rule"]
        )

        if not rules_in_mapping:
            return True, ""

        # 2. Get reservation overrides defined for this mapping
        reservation_rows = frappe.db.sql("""
            SELECT category, priority,
                   minimum_percentage_hsc, minimum_percentage_sslc,
                   minimum_cgpa_ug, minimum_cgpa_pg
            FROM `tabRule Mapping Category`
            WHERE parent = %(mapping_name)s
            ORDER BY priority ASC
        """, {"mapping_name": mapping_name}, as_dict=True)

        # 3. Identify all evaluation paths (Matched categories + General)
        applicant_categories = self._get_applicant_categories()
        
        # Path 1: Categories matching the mapping table
        matched_categories = [
            row for row in reservation_rows
            if (row.category or "").strip() in applicant_categories
        ]

        if matched_categories:
            matched_categories = sorted(
                matched_categories,
                key=lambda r: (flt(r.get("priority") or 999999), (r.get("category") or "").strip()),
            )
            primary_matched_row = matched_categories[0]
        else:
            primary_matched_row = None

        # If the applicant has matching category overrides, ONLY evaluate the highest priority matching category.
        # Otherwise, fall back to evaluating General/base rules.
        if matched_categories:
            evaluation_paths = [primary_matched_row]
        else:
            evaluation_paths = [None]

        # Collect rule-specific ineligible messages to show if ALL paths fail (subset; see docstring)
        ineligible_messages = []

        # 4. Nested OR Evaluation: Success if ANY (Path, Rule) combination passes
        for cat_row in evaluation_paths:
            for r_row in rules_in_mapping:
                base_rule = self._get_base_rule(r_row.rule)
                if not base_rule:
                    continue

                # Threshold: Category Override or Rule Default
                if cat_row:
                    qual_level = base_rule.get("qualification_level")
                    if qual_level == "XII":
                        required_val = flt(cat_row.minimum_percentage_hsc) if cat_row.minimum_percentage_hsc else self._get_required_value(base_rule)
                    elif qual_level == "Undergraduate":
                        required_val = flt(cat_row.minimum_cgpa_ug) if cat_row.minimum_cgpa_ug else self._get_required_value(base_rule)
                    elif qual_level == "Postgraduate":
                        required_val = flt(cat_row.minimum_cgpa_pg) if cat_row.minimum_cgpa_pg else self._get_required_value(base_rule)
                    else:
                        required_val = self._get_required_value(base_rule)
                else:
                    required_val = self._get_required_value(base_rule)

                operator = (base_rule.get("operator") or ">=")
                
                # Perform academic value comparison
                passes_threshold = self._compare_any_academic_value(base_rule, required_val, operator, cat_row=cat_row)
                # Perform non-percentage checks (Degrees/HSC Groups)
                passes_non_percentage = self._evaluate_non_percentage_checks(base_rule)

                if passes_threshold and passes_non_percentage:
                    # ELIGIBLE: Found a valid qualifying path
                    self._set_applied_category_info(
                        category=cat_row.category if cat_row else "General",
                        priority=cat_row.priority if cat_row else None,
                        minimum=required_val
                    )
                    return True, ""
                else:
                    # If this specific rule failed, collect its detailed failure reason
                    rule_msg = self._build_rule_failure_reason(
                        base_rule, required_val, cat_row=cat_row
                    )
                    if rule_msg:
                        if matched_categories:
                            if (
                                cat_row is not None
                                and primary_matched_row is not None
                                and (cat_row.get("category") or "").strip()
                                == (primary_matched_row.get("category") or "").strip()
                                and flt(cat_row.get("priority"))
                                == flt(primary_matched_row.get("priority"))
                            ):
                                ineligible_messages.append(rule_msg)
                        elif cat_row is None:
                            ineligible_messages.append(rule_msg)

        # If all paths and all rules failed, combine the mapping-level failure_message
        # with the specific ineligible_message(s) from the rules.
        mapping_heading = _("Summary")
        detail_heading = _("Eligibility details")
        self._slcm_failure_sections = [
            {"heading": mapping_heading, "body": failure_msg},
        ]
        final_message = failure_msg
        unique_parts = []
        for m in ineligible_messages:
            m = (m or "").strip()
            if m and m not in unique_parts:
                unique_parts.append(m)

        if unique_parts:
            merged_detail = Applicant._dedupe_eligibility_portal_lines("\n\n".join(unique_parts))
            self._slcm_failure_sections.append(
                {"heading": detail_heading, "body": merged_detail}
            )
            final_message = Applicant._dedupe_eligibility_portal_lines(
                failure_msg + "\n\n" + merged_detail
            )

        return False, final_message



    # ──────────────────────────────────────────────
    # STEP 3 — Base rule fetch
    # ──────────────────────────────────────────────

    def _get_base_rule(self, rule_name):
        if not rule_name:
            return None

        rules = frappe.db.sql("""
            SELECT *
            FROM `tabEligibility Rule`
            WHERE name            = %(rule_name)s
        """, {
            "rule_name":     rule_name,
        }, as_dict=True)

        return rules[0] if rules else None

    # ──────────────────────────────────────────────
    # NON-PERCENTAGE CHECKS (used in CASE A)
    # ──────────────────────────────────────────────

    def _evaluate_non_percentage_checks(self, rule):
        """
        Run only the non-percentage checks from the base rule:
          - Allowed Degree check  (any matching UG or PG program qualifies)
          - HSC Group check       (multi-group: passes if applicant's group is in
                                   the rule's hsc_group child table)
        """
        rule_type           = rule.get("rule_type")
        qualification_level = rule.get("qualification_level")
        rule_name           = rule.get("name")

        allowed_degrees = frappe.db.sql("""
            SELECT degree_name
            FROM `tabEligibility Allowed Degree`
            WHERE parent = %(rule_name)s
        """, {"rule_name": rule_name}, as_dict=True)

        allowed_degree_list = [r.degree_name for r in allowed_degrees if r.degree_name]

        if allowed_degree_list:
            if qualification_level == "Postgraduate":
                applicant_degrees = self._get_pg_programs()
            else:
                applicant_degrees = self._get_ug_programs()

            if not any(deg in allowed_degree_list for deg in applicant_degrees):
                return False

        if rule_type == "HSC Group":
            if not self._check_hsc_group_eligibility(rule_name):
                return False

        return True

    # ──────────────────────────────────────────────
    # HSC GROUP CHECK — multi-group support
    # ──────────────────────────────────────────────

    def _check_hsc_group_eligibility(self, rule_name):
        """
        Check if the applicant's HSC group is in the list of allowed HSC groups
        defined in the Eligibility Rule's hsc_group child table (HSC Groups Mapping).

        Returns True if applicant's group matches any allowed group in the rule,
        or if the rule has NO groups defined (no restriction).
        """
        allowed_groups_rows = frappe.db.sql("""
            SELECT hsc_groups
            FROM `tabHSC Groups Mapping`
            WHERE parent = %(rule_name)s
              AND parenttype = 'Eligibility Rule'
              AND hsc_groups IS NOT NULL
              AND hsc_groups != ''
        """, {"rule_name": rule_name}, as_dict=True)

        allowed_hsc_groups = [
            row.hsc_groups.strip()
            for row in allowed_groups_rows
            if row.hsc_groups
        ]

        # If no groups are configured in the rule → no restriction → pass
        if not allowed_hsc_groups:
            return True

        # Get applicant's HSC group
        applicant_hsc_group = (getattr(self, "hsc_group", None) or "").strip()

        if not applicant_hsc_group:
            return False

        return applicant_hsc_group in allowed_hsc_groups

    # ──────────────────────────────────────────────
    # RULE EVALUATION (single base rule — full check)
    # ──────────────────────────────────────────────

    def evaluate_single_rule(self, rule):
        """
        Full evaluation of a base Eligibility Rule against the applicant.
        Checks: Allowed Degrees, HSC Group (multi-group), and numeric threshold
        (Percentage / CGPA).
        """
        rule_type           = rule.get("rule_type")
        qualification_level = rule.get("qualification_level")
        operator            = rule.get("operator") or ">="
        rule_name           = rule.get("name")

        allowed_degrees = frappe.db.sql("""
            SELECT degree_name
            FROM `tabEligibility Allowed Degree`
            WHERE parent = %(rule_name)s
        """, {"rule_name": rule_name}, as_dict=True)

        allowed_degree_list = [r.degree_name for r in allowed_degrees if r.degree_name]

        # ── HSC Group check (multi-group via child table) ────────────────────
        if rule_type == "HSC Group":
            if not self._check_hsc_group_eligibility(rule_name):
                return False

        if qualification_level in ("Undergraduate", "Postgraduate"):
            required_value = self.get_required_academic_value(rule)

            if qualification_level == "Undergraduate":
                child_rows = getattr(self, "ug_degree_details", None) or []
            else:
                child_rows = getattr(self, "pg_degree_details", None) or []

            if not child_rows:
                return False

            for row in child_rows:
                program_field = "ug_program" if qualification_level == "Undergraduate" else "pg_program"
                cgpa_field    = "ug_cgpa"    if qualification_level == "Undergraduate" else "pg_cgpa"

                row_program = getattr(row, program_field, None)
                row_cgpa    = flt(getattr(row, cgpa_field, None) or 0)

                if allowed_degree_list and row_program not in allowed_degree_list:
                    continue

                if rule_type in ("CGPA", "Percentage"):
                    if required_value is None:
                        continue
                    if not self._compare(row_cgpa, required_value, operator):
                        continue

                return True

            return False

        if rule_type in ("HSC Group", "Percentage"):
            applicant_value = flt(getattr(self, "hsc_percentage", None) or 0)
            required_value  = self.get_required_academic_value(rule)

            if required_value is None:
                return False

            passed = self._compare(applicant_value, required_value, operator)
            if not passed:
                return False
                
            if qualification_level == "XII" and rule.get("sslc_percentage"):
                sslc_val = flt(getattr(self, "class_x_percentage", None) or 0)
                if not self._compare(sslc_val, flt(rule.get("sslc_percentage")), operator):
                    return False
                    
            return True

        return True

    # ──────────────────────────────────────────────
    # MULTI-DEGREE ACADEMIC VALUE CHECK (CASE A)
    # ──────────────────────────────────────────────

    def _compare_any_academic_value(self, rule, required_min, operator, cat_row=None):
        if not rule:
            return self._compare(flt(getattr(self, "hsc_percentage", 0) or 0), required_min, operator)

        qualification_level = rule.get("qualification_level")

        if qualification_level == "XII":
            value = flt(getattr(self, "hsc_percentage", None) or 0)
            passed = self._compare(value, required_min, operator)
            if not passed:
                return False
            
            # Determine required SSLC percentage
            required_sslc = None
            if cat_row and cat_row.get("minimum_percentage_sslc"):
                required_sslc = flt(cat_row.minimum_percentage_sslc)
            elif rule.get("sslc_percentage"):
                required_sslc = flt(rule.get("sslc_percentage"))

            if required_sslc is not None:
                sslc_val = flt(getattr(self, "class_x_percentage", None) or 0)
                if not self._compare(sslc_val, required_sslc, operator):
                    return False
            return True

        elif qualification_level == "Undergraduate":
            values = self._get_ug_cgpa_values()
            if not values:
                return False
            return any(self._compare(v, required_min, operator) for v in values)

        elif qualification_level == "Postgraduate":
            values = self._get_pg_cgpa_values()
            if not values:
                return False
            return any(self._compare(v, required_min, operator) for v in values)

        return False

    # ──────────────────────────────────────────────
    # VALUE HELPERS
    # ──────────────────────────────────────────────

    def _get_applicant_value(self, rule):
        if not rule:
            return flt(getattr(self, "hsc_percentage", 0) or 0)

        qualification_level = rule.get("qualification_level")

        if qualification_level == "XII":
            return flt(getattr(self, "hsc_percentage", None) or 0)
        elif qualification_level == "Undergraduate":
            values = self._get_ug_cgpa_values()
            return max(values) if values else 0.0
        elif qualification_level == "Postgraduate":
            values = self._get_pg_cgpa_values()
            return max(values) if values else 0.0

        return 0.0

    def _get_required_value(self, rule):
        if not rule:
            return None
        return self.get_required_academic_value(rule)

    def get_applicant_academic_value(self, qualification_level):
        if qualification_level == "XII":
            return flt(getattr(self, "hsc_percentage", None) or 0)
        if qualification_level == "Undergraduate":
            values = self._get_ug_cgpa_values()
            return max(values) if values else None
        if qualification_level == "Postgraduate":
            values = self._get_pg_cgpa_values()
            return max(values) if values else None
        return None

    def get_required_academic_value(self, rule):
        if rule.get("required_percentage"):
            return flt(rule["required_percentage"])
        if rule.get("required_cgpa"):
            return flt(rule["required_cgpa"])
        if rule.get("required_score"):
            return flt(rule["required_score"])
        return None

    def _compare(self, actual, required, operator):
        try:
            actual   = flt(actual)
            required = flt(required)
            if operator == ">=":
                return actual >= required
            elif operator == "<=":
                return actual <= required
            elif operator == "=":
                return actual == required
        except Exception:
            pass
        return False

    def compare_values(self, actual, required, operator):
        return self._compare(actual, required, operator)

    def _set_applied_category_info(self, category, priority, minimum):
        self.applied_category = category
        self.applied_priority = priority if priority is not None else ""
        self.applied_minimum  = minimum

    # ──────────────────────────────────────────────
    # CREATE / UPDATE ELIGIBILITY EVALUATION RECORD
    # ──────────────────────────────────────────────

    def create_or_update_evaluation(self, program_details_html=None):
        """
        Saves (insert or update) an Eligibility Evaluation record for this applicant.

        FIX — Duplicate Record Prevention:
        ────────────────────────────────────
        This method is now called ONLY from within validate_eligibility():
          • Ineligible path: called before frappe.throw() — required because throw
            exits the call stack before validate() can complete normally.
          • Eligible path: called at the end of validate_eligibility() directly.

        It is NO LONGER called separately from validate(). This eliminates the
        duplicate save that was occurring previously.

        The upsert logic (get existing → update OR insert new) prevents duplicate
        records even if called more than once for the same applicant.
        """
        if not all([self.program, self.campus, self.admission_cycle, self.academic_year]):
            return

        applicant_name = self.name or "New Applicant"

        existing = frappe.db.get_value(
            "Eligibility Evaluation",
            {"applicant_name": applicant_name},
            "name"
        )

        current_status = getattr(self, "evaluation_status", None) or "Eligible"
        current_reason = getattr(self, "rejected_reason", None) or ""

        exempts_entrance_test   = getattr(self, "exempts_entrance_test",   0)
        exempts_interview       = getattr(self, "exempts_interview",       0)
        national_test_rule_used = getattr(self, "national_test_rule_used", "")

        doc_data = {
            "doctype":                 "Eligibility Evaluation",
            "applicant_name":          applicant_name,
            "academic_year":           self.academic_year,
            "admission_cycle":         self.admission_cycle,
            "program":                 self.program,
            "campus":                  self.campus,
            "evaluation_status":       current_status,
            "failure_message":         current_reason,
            "exempts_entrance_test":   exempts_entrance_test,
            "exempts_interview":       exempts_interview,
            "entrance_test":           getattr(self, "entrance_test", 0),
            "intereview":              getattr(self, "intereview", 0),
            "national_test_rule_used": national_test_rule_used,
            "program_eligibility_details": program_details_html,
            "reservation_category": [
                {"category": cat}
                for cat in self._get_applicant_categories()
            ]
        }

        if existing:
            doc = frappe.get_doc("Eligibility Evaluation", existing)
            doc.update(doc_data)
        else:
            doc = frappe.get_doc(doc_data)

        try:
            doc.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            frappe.logger().warning(
                f"Failed to save Eligibility Evaluation for {applicant_name}: {str(e)}"
            )


# ──────────────────────────────────────────────
# SUBMISSION APPLICATION STATUS (from national test exemption)
# ──────────────────────────────────────────────


def _truthy(val):
    """Treat 1, True, '1' as True; 0, False, None as False."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    return str(val).strip().lower() in ("1", "true", "yes")


def _status_from_exemption_flags(exempts_entrance_test, exempts_interview):
    """
    Return Applicant Status name from exemption flags.
    - Both exempt → "Excempted Entrance Test And Interview"
    - Only interview exempt → "Interview Excempted"
    - Only entrance test exempt → "Entrance Test Exempted"
    - Neither → "Submitted"
    """
    if _truthy(exempts_entrance_test) and _truthy(exempts_interview):
        return "Excempted Entrance Test And Interview"
    if _truthy(exempts_interview):
        return "Interview Excempted"
    if _truthy(exempts_entrance_test):
        return "Entrance Test Exempted"
    return "Submitted"


def _get_eligibility_evaluation_for_applicant(applicant_name, applicant_id=None):
    """Get Eligibility Evaluation by applicant_name (doc name) or applicant_id. Returns dict or None."""
    for key in [applicant_name, applicant_id]:
        if not key:
            continue
        ev = frappe.db.get_value(
            "Eligibility Evaluation",
            {"applicant_name": key},
            ["evaluation_status", "exempts_entrance_test", "exempts_interview"],
            as_dict=True,
        )
        if ev:
            return ev
    return None


def _sync_status_from_eligibility_evaluation(applicant_doc):
    """
    If the applicant is "Submitted" but has an Eligibility Evaluation that is Eligible
    with exemption flags, set status from that Evaluation so it shows
    "Entrance Test Exempted" / "Interview Excempted" / "Excempted Entrance Test And Interview".
    """
    if not getattr(applicant_doc, "name", None):
        return
    ev = _get_eligibility_evaluation_for_applicant(
        applicant_doc.name,
        getattr(applicant_doc, "applicant_id", None),
    )
    if not ev or ev.get("evaluation_status") != "Eligible":
        return
    if not _truthy(ev.get("exempts_entrance_test")) and not _truthy(ev.get("exempts_interview")):
        return
    new_status = _status_from_exemption_flags(
        ev.get("exempts_entrance_test"), ev.get("exempts_interview")
    )
    if new_status and new_status != "Submitted" and frappe.db.exists("Applicant Status", new_status):
        applicant_doc.status = new_status


def _get_submission_status(applicant_doc):
    """
    When the student submits, return status from national test exemption flags.
    """
    exempt_et = getattr(applicant_doc, "exempts_entrance_test", 0)
    exempt_int = getattr(applicant_doc, "exempts_interview", 0)
    status = _status_from_exemption_flags(exempt_et, exempt_int)
    if status == "Submitted":
        return status
    if frappe.db.exists("Applicant Status", status):
        return status
    frappe.log_error(
        message=f"Applicant Status '{status}' does not exist. Using 'Submitted'.",
        title="Applicant Status Fallback",
    )
    return "Submitted"


# ──────────────────────────────────────────────
# WHITELIST API
# ──────────────────────────────────────────────


@frappe.whitelist()
def get_eligible_programs_for_campus(campus, admission_cycle):
    programs = frappe.db.sql("""
        SELECT DISTINCT erm.program
        FROM `tabEligibility Rule Mapping` erm
        WHERE erm.is_active         = 1
          AND erm.campus            = %(campus)s
          AND erm.admission_cycle   = %(admission_cycle)s
    """, {
        "campus":          campus,
        "admission_cycle": admission_cycle,
    }, as_dict=True)

    return [p.program for p in programs if p.program]


# ──────────────────────────────────────────────
# Async helper — create Eligibility Evaluation
# ──────────────────────────────────────────────


def create_eligibility_evaluation_async(
    applicant_name, status, failure_msg, categories,
    program, campus, admission_cycle, academic_year
):
    """Create or update Eligibility Evaluation record."""

    if not all([program, campus, admission_cycle, academic_year]):
        return

    existing = frappe.db.get_value(
        "Eligibility Evaluation",
        filters={"applicant_name": applicant_name},
        fieldname="name"
    )

    eval_data = {
        "doctype":           "Eligibility Evaluation",
        "applicant_name":    applicant_name,
        "academic_year":     academic_year,
        "admission_cycle":   admission_cycle,
        "program":           program,
        "campus":            campus,
        "evaluation_status": status,
        "failure_message":   failure_msg,
        "reservation_category": [
            {
                "category": row.get("category") if isinstance(row, dict) else row.category
            }
            for row in (categories or [])
        ] if categories else [],
    }

    if existing:
        doc = frappe.get_doc("Eligibility Evaluation", existing)
        doc.update(eval_data)
    else:
        doc = frappe.get_doc(eval_data)

    doc.save(ignore_permissions=True)


# ──────────────────────────────────────────────
# Hook functions
# ──────────────────────────────────────────────


def validate_applicant(doc, method):
    """Called via hooks.py doc_events validate"""
    doc.validate_eligibility()


def before_submit_applicant(doc, method):
    """Called via hooks.py doc_events before_submit"""
    if doc.evaluation_status == "Ineligible":
        frappe.throw(
            _("In-Eligible: {0}").format(
                doc.rejected_reason or "You are not eligible for the selected program."
            ),
            title=_("Submission Not Allowed")
        )

def set_intake_type(doc, method=None):
    """
    Copy intake_type from the linked Program.
    Program is the source of truth for intake type.
    BA LLB / BCom LLB / BBA LLB = CLAT
    LLM / LLM Business Law       = NLSAT
    PhD Law                      = Direct Merit
    """
    if doc.program:
        intake = frappe.db.get_value("Programme", doc.program, "intake_type")
        if intake:
            doc.intake_type = intake

def set_admission_details(doc):
    """
    Populate Admission Year and Academic Year from Admission Cycle if missing.
    """
    if doc.admission_cycle and (not doc.admission_year or not doc.academic_year):
        details = frappe.db.get_value(
            "Admission Cycle", 
            doc.admission_cycle, 
            ["admission_year", "academic_year"], 
            as_dict=True
        )
        if details:
            if not doc.admission_year:
                doc.admission_year = details.admission_year
            if not doc.academic_year:
                doc.academic_year = details.academic_year

@contextmanager
def _ignore_print_permissions():
    """Server-side PDF generation (portal/desk hooks) must not depend on Print permission."""
    prev = getattr(frappe.flags, "ignore_print_permissions", False)
    frappe.flags.ignore_print_permissions = True
    try:
        yield
    finally:
        frappe.flags.ignore_print_permissions = prev


def notify_stage_entry(applicant_doc, stage):
    """
    Called when applicant enters a new stage.
    Creates portal notification. Sends email if template configured.
    Only fires if notify_applicant_on_entry = 1 on the stage.
    """
    if not getattr(stage, "notify_applicant_on_entry", 0):
        return

    try:
        frappe.get_doc({
            "doctype":           "Applicant Notification",
            "applicant":         applicant_doc.name,
            "title":             f"Stage Update: {stage.stage_name}",
            "message":           f"Your application has moved to the {stage.stage_name} stage.",
            "notification_type": "Stage Update",
            "link":              "/my-applications",
            "is_read":           0
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"notify_stage_entry failed: {e}", "Stage Notification")


def resolve_application_form_print_format_for_cycle(cycle_name):
    """Print format name for Applicant PDF (matches submission email resolution)."""
    default = "Applicant Application Form"
    if not cycle_name:
        return default
    fmt = frappe.db.get_value(
        "Admission Cycle",
        {"name": cycle_name, "status": "Active"},
        "application_form_template",
    )
    if not fmt:
        fmt = frappe.db.get_value("Admission Cycle", cycle_name, "application_form_template")
    return fmt or default


def ensure_application_form_pdf_for_applicant(applicant_name):
    """
    Generate application-form PDF and attach to ``application_form`` when still empty.
    Used for desk-created applicants (never Draft) and when the email path did not persist the file.
    """
    if not applicant_name or not frappe.db.exists("Applicant", applicant_name):
        return
    if frappe.db.get_value("Applicant", applicant_name, "application_form"):
        return
    status = frappe.db.get_value("Applicant", applicant_name, "status")
    if (status or "").strip() not in APPLICATION_SUBMITTED_STATUSES:
        return
    doc = frappe.get_doc("Applicant", applicant_name, check_permission=False)
    print_format_name = resolve_application_form_print_format_for_cycle(doc.admission_cycle)
    try:
        pdf_content = doc.get_application_pdf_content()
        if pdf_content:
            save_application_form_pdf_to_applicant(doc, pdf_content)
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"ensure_application_form_pdf_for_applicant get_print failed for {applicant_name}",
        )


def _clear_application_form_attachment_files(applicant_name):
    url = frappe.db.get_value("Applicant", applicant_name, "application_form")
    file_names = set(
        frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": "Applicant",
                "attached_to_name": applicant_name,
                "attached_to_field": "application_form",
            },
            pluck="name",
        )
    )
    if url:
        for fn in frappe.get_all("File", filters={"file_url": url}, pluck="name"):
            file_names.add(fn)

    for fn in file_names:
        try:
            frappe.delete_doc("File", fn, force=1, ignore_permissions=True)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Clear application_form File {fn} for {applicant_name}",
            )


def save_application_form_pdf_to_applicant(applicant_doc, pdf_content):
    """Persist submission PDF on ``Applicant.application_form`` for cached bulk download."""
    if not pdf_content or not getattr(applicant_doc, "name", None):
        return
    try:
        from frappe.utils.file_manager import save_file

        _clear_application_form_attachment_files(applicant_doc.name)
        fname = f"Application_Form_{applicant_doc.applicant_id or applicant_doc.name}.pdf"
        file_doc = save_file(
            fname,
            pdf_content,
            "Applicant",
            applicant_doc.name,
            decode=False,
            is_private=1,
            df="application_form",
        )
        if file_doc:
            if not file_doc.is_private or (file_doc.file_url and not file_doc.file_url.startswith("/private")):
                file_doc.is_private = 1
                file_doc.save(ignore_permissions=True)

        # ``save_file`` creates the File row but does not set the parent Attach field on Applicant.
        if file_doc and getattr(file_doc, "file_url", None):
            frappe.db.set_value(
                "Applicant",
                applicant_doc.name,
                "application_form",
                file_doc.file_url,
                update_modified=False,
            )
            applicant_doc.application_form = file_doc.file_url
            frappe.db.commit()
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"save_application_form_pdf_to_applicant failed for {applicant_doc.name}",
        )


def read_stored_application_form_pdf(applicant_name):
    """Return cached PDF bytes from ``application_form`` attachment, or None."""
    if not applicant_name:
        return None
    files = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "Applicant",
            "attached_to_name": applicant_name,
            "attached_to_field": "application_form",
        },
        pluck="name",
        order_by="creation desc",
        limit=1,
    )
    if not files:
        url = frappe.db.get_value("Applicant", applicant_name, "application_form")
        if not url:
            return None
        alt = frappe.get_all("File", filters={"file_url": url}, pluck="name", limit=1)
        if not alt:
            return None
        files = alt
    try:
        fdoc = frappe.get_doc("File", files[0])
        return fdoc.get_content()
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"read_stored_application_form_pdf failed for {applicant_name}",
        )
        return None


def get_application_attachments(doc):
    """
    Helper function to get the PDF attachment from application_form field.
    """
    attachments = []
    if getattr(doc, "application_form", None):
        file_name = frappe.db.get_value("File", {"file_url": doc.application_form}, "name")
        if file_name:
            file_doc = frappe.get_doc("File", file_name)
            attachments.append({
                "fname": file_doc.file_name,
                "fcontent": file_doc.get_content()
            })
    return attachments


@frappe.whitelist()
def get_bulk_applications_zip(campus=None, program=None, admission_cycle=None, academic_year=None, admission_year=None, status=None, print_format=None):
    """
    Whitelisted entry point for bulk applicant form download.
    Draft applications are never included. Prefer cached ``application_form`` PDF when set;
    otherwise generate with the selected print format.
    """
    if status and (status or "").strip() == "Draft":
        frappe.throw(_("Bulk download cannot include applications in Draft status."))

    filters = {}
    if campus:
        filters["campus"] = campus
    if program:
        filters["program"] = program
    if admission_cycle:
        filters["admission_cycle"] = admission_cycle
    if academic_year:
        filters["academic_year"] = academic_year
    if admission_year:
        filters["admission_year"] = admission_year
    if status:
        filters["status"] = status

    rows = frappe.get_all("Applicant", filters=filters, fields=["name", "status"])
    applicants = [
        r.name
        for r in rows
        if (r.status or "").strip() != "Draft"
    ]

    if not applicants:
        if rows:
            frappe.throw(
                _("All matching applications are in Draft status and cannot be downloaded.")
            )
        frappe.throw(_("No applicants found matching the selected filters."))

    if not print_format:
        print_format = "Applicant Application Form"

    # LARGE BATCH HANDLING (> 10)
    if len(applicants) > 10:
        frappe.enqueue(
            "slcm.admission.doctype.applicant.applicant.background_bulk_worker",
            applicants=applicants,
            print_format=print_format,
            user=frappe.session.user,
            queue='long',
            timeout=3600
        )
        return {
            "queued": True,
            "message": _("Large batch detected ({0} applicants). Processing started in the background. You will receive a notification when finished.").format(len(applicants))
        }

    # SMALL BATCH SYNC
    return background_bulk_worker(applicants, print_format, sync=True)


@frappe.whitelist()
def bulk_convert_applicants_to_student(applicants=None):
    """
    Resolve Applicant Fee Assignment (Admission Fee, Paid / Partially Paid) per applicant,
    then delegate to the same bulk convert pipeline as Applicant Fee Assignment.

    Only applicants with status == Fee Paid are eligible (others are skipped with a reason).
    """
    from slcm.admission.doctype.applicant_fee_assignment.applicant_fee_assignment import (
        bulk_convert_to_student as bulk_convert_assignments,
    )

    if isinstance(applicants, str):
        applicants = json.loads(applicants)
    if not applicants:
        return {"message": _("No applicants selected.")}

    eligible_assignments = []
    skipped = []
    seen = set()

    for an in applicants:
        if not an:
            continue
        if not frappe.db.exists("Applicant", an):
            skipped.append({"applicant": an, "reason": _("Applicant not found.")})
            continue
        st = frappe.db.get_value("Applicant", an, "status")
        if st not in ["Confirmation Fee Paid", "Full Fee Paid"]:
            skipped.append(
                {
                    "applicant": an,
                    "reason": _("Only applicants with status Fee Paid can be converted (current: {0}).").format(
                        st or _("—")
                    ),
                }
            )
            continue
        rows = frappe.get_all(
            "Applicant Fee Assignment",
            filters={"applicant": an, "fee_type": "Admission Fee", "docstatus": 1},
            fields=["name", "status"],
            order_by="modified desc",
        )
        afa_name = None
        for r in rows:
            if r.status in ("Paid", "Partially Paid"):
                afa_name = r.name
                break
        if not afa_name:
            skipped.append(
                {
                    "applicant": an,
                    "reason": _(
                        "No submitted Admission Fee assignment in Paid or Partially Paid status was found."
                    ),
                }
            )
            continue
        if afa_name not in seen:
            seen.add(afa_name)
            eligible_assignments.append(afa_name)

    if not eligible_assignments:
        return {
            "message": _(
                "No eligible applicants. Select applicants with status Fee Paid and a paid or partially paid Admission Fee assignment."
            ),
            "skipped": skipped,
        }

    result = bulk_convert_assignments(eligible_assignments)
    if not isinstance(result, dict):
        return result
    result.setdefault("skipped", [])
    result["skipped"] = skipped + list(result["skipped"])
    return result


def background_bulk_worker(applicants, print_format, user=None, sync=False):
    """
    Build ZIP of application forms. Uses ``Applicant.application_form`` when set (fast);
    otherwise falls back to ``frappe.get_print(..., as_pdf=True)``.
    """
    import zipfile
    from io import BytesIO
    from frappe.utils.file_manager import save_file

    total = len(applicants)
    success_count = 0
    errors = []
    from_cache_count = 0
    generated_count = 0

    # One query for filenames — avoids N get_value round-trips (small vs PDF cost).
    id_rows = frappe.get_all(
        "Applicant",
        filters={"name": ["in", applicants]},
        fields=["name", "applicant_id"],
    )
    id_by_name = {r.name: (r.applicant_id or r.name) for r in id_rows}

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for i, name in enumerate(applicants):
            try:
                pdf_content = read_stored_application_form_pdf(name)
                if pdf_content:
                    from_cache_count += 1
                    prog_msg = _("Adding cached form for {0}").format(name)
                else:
                    if not sync:
                        prog_msg = _("Generating PDF for {0}").format(name)
                    with _ignore_print_permissions():
                        pdf_content = frappe.get_print(
                            doctype="Applicant",
                            name=name,
                            print_format=print_format,
                            as_pdf=True,
                        )
                    generated_count += 1
                    if not sync:
                        prog_msg = _("Generated PDF for {0}").format(name)

                if not sync:
                    frappe.publish_realtime(
                        "bulk_download_progress",
                        {
                            "progress": i + 1,
                            "total": total,
                            "message": prog_msg,
                        },
                        user=user,
                    )

                applicant_id = id_by_name.get(name) or name
                zip_file.writestr(f"{applicant_id}.pdf", pdf_content)
                success_count += 1

            except Exception as e:
                errors.append({"applicant": name, "error": str(e)})

    if success_count == 0:
        error_msg = _("Failed to generate any PDFs. Errors: {0}").format(len(errors))
        if sync: frappe.throw(error_msg)
        return

    # Save ZIP File
    zip_buffer.seek(0)
    file_name = f"Applicant_Forms_{frappe.utils.now_datetime().strftime('%Y%m%d_%H%M%S')}.zip"
    saved_file = save_file(file_name, zip_buffer.getvalue(), "Applicant", "Bulk Download", is_private=1)

    if sync:
        return {
            "file_url": saved_file.file_url,
            "success": success_count,
            "errors": errors,
            "from_cache": from_cache_count,
            "generated_live": generated_count,
        }

    # Background cleanup and notification
    notification_content = f"""
        <div style="font-family: sans-serif; padding: 5px;">
            <h4 style="color: #1a202c; margin-bottom: 12px;">{_('Bulk Form Generation Report')}</h4>
            <p style="font-size: 12px; color: #718096; margin: 0 0 10px 0;">
                {_('{0} from stored PDF, {1} generated live.').format(from_cache_count, generated_count)}
            </p>
            <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                <span style="background: #f0fff4; color: #2f855a; padding: 4px 10px; border-radius: 4px; border: 1px solid #c6f6d5; font-weight: bold; font-size: 12px;">
                    {success_count} {_('Included')}
                </span>
                <span style="background: { '#fff5f5' if errors else '#f7fafc' }; color: { '#c53030' if errors else '#718096' }; padding: 4px 10px; border-radius: 4px; border: 1px solid { '#fed7d7' if errors else '#edf2f7' }; font-weight: bold; font-size: 12px;">
                    {len(errors)} {_('Failed')}
                </span>
            </div>
            <p style="font-size: 13px; color: #4a5568;">{_('Your ZIP archive is ready for download.')}</p>
            <div style="margin-top: 15px; border-top: 1px solid #edf2f7; padding-top: 12px;">
                <a href="{saved_file.file_url}" target="_blank" style="background: #1a202c; color: #ffffff !important; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 13px; display: inline-block;">
                    {_('Download ZIP')}
                </a>
            </div>
        </div>
    """

    from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
    enqueue_create_notification([user], {
        "subject": _("Bulk Applicant Forms Ready"),
        "email_content": notification_content,
        "type": "Alert",
        "document_type": "Applicant"
    })

    frappe.publish_realtime(
        "bulk_download_complete",
        {
            "file_url": saved_file.file_url,
            "doctype": "Applicant",
            "success": success_count,
            "from_cache": from_cache_count,
            "generated_live": generated_count,
        },
        user=user,
    )

    frappe.publish_realtime(
        "msgprint",
        {
            "message": _(
                "ZIP with {0} application form(s) is ready. If you are on the Applicant list, "
                "a download dialog will appear; otherwise use the desk notification link."
            ).format(success_count),
            "title": _("Bulk download ready"),
            "indicator": "green" if not errors else "orange",
        },
        user=user,
    )


def _auto_allocate_entrance_test_on_submission(applicant_doc):
    """
    Auto-allocate Entrance Test seat on Applicant submit.

    Rules:
    - Only for Eligible applicants
    - Skip exempted-from-entrance-test applicants
    - Only when Program has `entrance_test` enabled
    - Resolve Entrance Test by programme in Admission Cycle, else by programme level
    - International applicants (foriegn_national == "Yes"):
        * Bypass all center/seat capacity checks
        * Create ETSA record without center/room/seat fields
        * No admit card generated or sent
        * Dedicated email template "International Entrance Test Allocation" is used
    - Domestic applicants: Allocate first available preferred center (1st/2nd/3rd)
    - If no center available, skip silently so manual Entrance Test Generation/List flow can be used
    """
    if not applicant_doc or not getattr(applicant_doc, "name", None):
        frappe.log_error("Auto Allocate skipped: No applicant_doc or name", "Auto Allocate Debug")
        return

    if applicant_doc.status != "Completed":
        frappe.log_error(f"Auto Allocate skipped: status is {applicant_doc.status}, not Completed", "Auto Allocate Debug")
        return

    if (getattr(applicant_doc, "evaluation_status", "") or "").strip() != "Eligible":
        frappe.log_error(f"Auto Allocate skipped: evaluation_status is {getattr(applicant_doc, 'evaluation_status', '')}", "Auto Allocate Debug")
        return

    if _truthy(getattr(applicant_doc, "exempts_entrance_test", 0)):
        frappe.log_error("Auto Allocate skipped: exempts_entrance_test is true", "Auto Allocate Debug")
        return

    if not applicant_doc.program:
        frappe.log_error("Auto Allocate skipped: no program", "Auto Allocate Debug")
        return

    is_international = (getattr(applicant_doc, "foriegn_national", "") or "").strip() == "Yes"

    if is_international:
        if not _truthy(frappe.db.get_value("Programme", applicant_doc.program, "international_entrance_test")):
            frappe.log_error(f"Auto Allocate skipped: international_entrance_test not enabled for program {applicant_doc.program}", "Auto Allocate Debug")
            return
        # ── International applicant branch ──────────────────────────────────────
        _auto_allocate_international_entrance_test(applicant_doc)
        return
    else:
        if not _truthy(frappe.db.get_value("Programme", applicant_doc.program, "entrance_test")):
            frappe.log_error(f"Auto Allocate skipped: entrance_test not enabled for program {applicant_doc.program}", "Auto Allocate Debug")
            return
    # ─────────────────────────────────────────────────────────────────────────

    # Domestic Applicants:
    # No automated seat allocation. Look up or create Entrance Test List record for chosen Entrance Test City
    city_pref = (
        (applicant_doc.first_preference or "").strip()
        or (applicant_doc.second_preference or "").strip()
        or (applicant_doc.third_preference or "").strip()
    )

    if not city_pref:
        frappe.log_error(f"Domestic Applicant Entrance Test List sync skipped: No test city preference for {applicant_doc.name}")
        return

    etl_name = _get_or_create_city_entrance_test_list(applicant_doc, city_pref)
    if not etl_name:
        return

    try:
        etl = frappe.get_doc("Entrance Test List", etl_name)
        exists_row = any(
            (row.applicant_id or "").strip() == applicant_doc.name
            for row in (etl.entrance_test_applicant or [])
        )
        if not exists_row:
            etl.append(
                "entrance_test_applicant",
                {
                    "applicant_id": applicant_doc.name,
                    "candidate_name": applicant_doc.candidate_name,
                    "program": applicant_doc.program,
                    "program_level": applicant_doc.program_level,
                    "email": applicant_doc.email,
                    "gender": applicant_doc.gender,
                    "exempts_entrance_test": cint(getattr(applicant_doc, "exempts_entrance_test", 0)),
                    "exempts_interview": cint(getattr(applicant_doc, "exempts_interview", 0)),
                    "allocation_status": "Not Allocated",
                },
            )
            etl.save(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Domestic applicant Entrance Test List sync failed for {applicant_doc.name}",
        )


def _get_or_create_city_entrance_test_list(applicant_doc, city):
    """
    Get or create Entrance Test List record for a given Entrance Test City.
    If a list already exists for this city, reuse it.
    """
    if not city:
        return None

    filters = {"entrance_test_city": city}
    if applicant_doc.academic_year:
        filters["academic_year"] = applicant_doc.academic_year
    if applicant_doc.admission_cycle:
        filters["admission_cycle"] = applicant_doc.admission_cycle

    list_name = frappe.db.get_value("Entrance Test List", filters, "name")
    if not list_name:
        list_name = frappe.db.get_value("Entrance Test List", {"entrance_test_city": city}, "name")

    if list_name:
        return list_name

    etl = frappe.get_doc(
        {
            "doctype": "Entrance Test List",
            "academic_year": applicant_doc.academic_year,
            "campus": applicant_doc.campus,
            "admission_cycle": applicant_doc.admission_cycle,
            "program_level": applicant_doc.program_level,
            "entrance_test_city": city,
            "generated_on": now(),
            "status": "Generated",
            "entrance_test_applicant": [],
        }
    )
    etl.insert(ignore_permissions=True)
    return etl.name


def _resolve_entrance_test_config_for_applicant(applicant_doc):
    """
    Resolve Entrance Test from Admission Cycle Entrance Test Details:
    1) exact programme match
    2) programme level match (fallback)
    """
    if not applicant_doc.admission_cycle:
        return {}

    rows = frappe.get_all(
        "Entrance Test Details",
        filters={"parent": applicant_doc.admission_cycle, "parenttype": "Admission Cycle"},
        fields=["programme", "programme_level", "entrance_test_name", "entrance_test_date", "start_time", "end_time", "idx"],
        order_by="idx asc",
    )
    if not rows:
        return {}

    for row in rows:
        if (
            (row.get("programme") or "").strip() == (applicant_doc.program or "").strip()
            and row.get("entrance_test_name")
        ):
            return row

    for row in rows:
        if (
            (row.get("programme_level") or "").strip() == (applicant_doc.program_level or "").strip()
            and row.get("entrance_test_name")
        ):
            return row

    return {}


def _get_preference_provider_names(applicant_doc):
    prefs = [
        (applicant_doc.first_preference or "").strip(),
        (applicant_doc.second_preference or "").strip(),
        (applicant_doc.third_preference or "").strip(),
    ]
    seen = set()
    out = []
    for p in prefs:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _try_allocate_provider_seat_atomic(provider_name):
    """
    Atomically reserve one seat in the first available active room for the provider.
    Uses SELECT ... FOR UPDATE to avoid race conditions for simultaneous submissions.
    """
    if not provider_name:
        return None

    provider_rows = frappe.db.sql(
        """
        SELECT name, center_name, center_address
        FROM `tabEntrance Test Provider`
        WHERE name = %s AND IFNULL(active, 0) = 1
        LIMIT 1
        FOR UPDATE
        """,
        provider_name,
        as_dict=True,
    )
    if not provider_rows:
        return None

        
    room_rows = frappe.db.sql(
        """
        SELECT name, room_code, room_name, building, floor, room_capacity, room_reserved_seats
        FROM `tabProvider Room`
        WHERE parent = %s
          AND IFNULL(active, 1) = 1
          AND (IFNULL(room_capacity, 0) - IFNULL(room_reserved_seats, 0)) > 0
        ORDER BY idx ASC
        LIMIT 1
        FOR UPDATE
        """,
        provider_name,
        as_dict=True,
    )
    if not room_rows:
        return None

    room = room_rows[0]
    reserved = cint(room.get("room_reserved_seats") or 0)
    capacity = cint(room.get("room_capacity") or 0)
    if reserved >= capacity:
        return None

    new_reserved = reserved + 1

    seat_number = f"{new_reserved:02d}"
    frappe.db.set_value(
        "Provider Room",
        room["name"],
        {
            "room_reserved_seats": new_reserved,
            "room_available_capacity": max(0, capacity - new_reserved),
        },
        update_modified=False,
    )

    totals = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(IFNULL(room_capacity, 0)), 0) AS total_capacity,
            COALESCE(SUM(IFNULL(room_reserved_seats, 0)), 0) AS reserved_seats,
            COALESCE(SUM(GREATEST(IFNULL(room_capacity, 0) - IFNULL(room_reserved_seats, 0), 0)), 0) AS available_capacity
        FROM `tabProvider Room`
        WHERE parent = %s
        """,
        provider_name,
        as_dict=True,
    )[0]

    frappe.db.set_value(
        "Entrance Test Provider",
        provider_name,
        {
            "total_capacity": cint(totals.get("total_capacity") or 0),
            "reserved_seats": cint(totals.get("reserved_seats") or 0),
            "available_capacity": cint(totals.get("available_capacity") or 0),
        },
        update_modified=False,
    )

    provider = provider_rows[0]
    return {
        "provider": provider_name,
        "center_name": provider.get("center_name"),
        "center_address": provider.get("center_address"),
        "room_code": room.get("room_code"),
        "room_name": room.get("room_name"),
        "building": room.get("building"),
        "floor": room.get("floor"),
        "seat_number": seat_number,
    }


def _get_or_create_auto_entrance_test_list(applicant_doc):
    list_name = frappe.db.get_value(
        "Entrance Test List",
        {
            "academic_year": applicant_doc.academic_year,
            "campus": applicant_doc.campus,
            "admission_cycle": applicant_doc.admission_cycle,
            "program_level": applicant_doc.program_level,
        },
        "name",
    )
    if list_name:
        return list_name

    etl = frappe.get_doc(
        {
            "doctype": "Entrance Test List",
            "academic_year": applicant_doc.academic_year,
            "campus": applicant_doc.campus,
            "admission_cycle": applicant_doc.admission_cycle,
            "program_level": applicant_doc.program_level,
            "generated_on": now(),
            "status": "Generated",
            "entrance_test_applicant": [],
        }
    )
    etl.insert(ignore_permissions=True)
    return etl.name


def _send_automated_entrance_test_allocation_email(allocation, email):
    """
    Send dedicated email for automated entrance test allocation (domestic applicants).
    Uses Email Template: 'Automated Entrance Test Allocation'
    """
    if not allocation or not email:
        return

    try:
        template_name = "Automated Entrance Test Allocation"
        if not frappe.db.exists("Email Template", template_name):
            frappe.log_error(
                f"Email Template '{template_name}' not found.",
                "Automated Allocation Email Sending Error",
            )
            return

        template = frappe.get_doc("Email Template", template_name)
        doc_dict = allocation.as_dict()
        doc_dict["assigned_preferences"] = [p.as_dict() for p in (allocation.assigned_preferences or [])]
        args = {
            "doc": doc_dict,
            "portal_url": frappe.utils.get_url("/merit-and-scholarship/admission_dashboard?panel=applications"),
        }

        subject = frappe.render_template(template.subject or "", args)
        if template.get("use_html"):
            message_body = frappe.render_template(template.response_html or "", args)
        else:
            message_body = frappe.render_template(template.response or "", args)

        if not message_body:
            message_body = frappe.render_template(template.get("message") or "", args)

        cc_list = []
        cc_field_value = template.get("cc")
        if cc_field_value:
            cc_list = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]

        if message_body:
            attachments = []
            if not getattr(allocation, "is_international_applicant", 0):
                if not getattr(allocation, "admit_card_download", None):
                    try:
                        from slcm.admission.doctype.entrance_test_list.entrance_test_list import generate_and_store_admit_card
                        generate_and_store_admit_card(allocation, is_rescheduled=False)
                        allocation.reload()
                    except Exception:
                        frappe.log_error(traceback.format_exc(), f"Admit card generation failed for {allocation.name}")

                if getattr(allocation, "admit_card_download", None):
                    try:
                        file_name = frappe.db.get_value("File", {"file_url": allocation.admit_card_download}, "name")
                        if file_name:
                            file_doc = frappe.get_doc("File", file_name)
                            attachments.append({
                                "fname": file_doc.file_name,
                                "fcontent": file_doc.get_content()
                            })
                    except Exception:
                        frappe.log_error(traceback.format_exc(), f"Failed to attach Admit Card for {allocation.name}")

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
                reference_name=allocation.name,
                now=False,
            )
    except Exception:
        frappe.log_error(
            message=traceback.format_exc(),
            title=f"Automated Allocation Email Failed: {allocation.name if allocation else 'unknown'}",
        )


# ──────────────────────────────────────────────────────────────────────────────
# INTERNATIONAL APPLICANT — ENTRANCE TEST ALLOCATION
# No center/seat/room logic; online test; no admit card; dedicated email template
# ──────────────────────────────────────────────────────────────────────────────

def _auto_allocate_international_entrance_test(applicant_doc):
    """
    Create an Entrance Test Seat Allocation for an international applicant
    (foriegn_national == "Yes") without any center/seat/room assignment.

    Rules:
    - No center availability or seat capacity checks.
    - test name and test date resolved from Admission Cycle config (same as domestic).
    - No admit card generated or attached.
    - Sends "International Entrance Test Allocation" email template.
    - Adds a Notification Log entry like the domestic flow.
    """
    if not applicant_doc or not getattr(applicant_doc, "name", None):
        return

    # Idempotency: a seat allocation already exists for this applicant
    existing = frappe.db.get_value(
        "Entrance Test Seat Allocation",
        {"applicant": applicant_doc.name},
        "name",
    )
    if existing:
        frappe.log_error(
            f"International Auto Allocate skipped: existing allocation {existing}",
            "Auto Allocate Debug",
        )
        return

    # Resolve test config from Admission Cycle (same logic as domestic)
    test_cfg = _resolve_entrance_test_config_for_applicant(applicant_doc)
    if not test_cfg or not test_cfg.get("entrance_test_name"):
        frappe.log_error(
            "International Auto Allocate skipped: no entrance_test_name in cycle config",
            "Auto Allocate Debug",
        )
        return

    # No Entrance Test List created or linked for international applicants.
    allocation = frappe.new_doc("Entrance Test Seat Allocation")
    allocation.academic_year        = applicant_doc.academic_year
    allocation.admission_cycle      = applicant_doc.admission_cycle
    allocation.campus               = applicant_doc.campus
    allocation.program_level        = applicant_doc.program_level
    allocation.entrance_test_name   = test_cfg.get("entrance_test_name")
    allocation.allocation_date      = test_cfg.get("entrance_test_date")
    allocation.start_time           = test_cfg.get("start_time")
    allocation.end_time             = test_cfg.get("end_time")

    allocation.applicant            = applicant_doc.name
    allocation.candidate_name       = applicant_doc.candidate_name
    allocation.program              = applicant_doc.program
    allocation.email                = applicant_doc.email
    allocation.gender               = applicant_doc.gender
    allocation.entrance_test        = getattr(applicant_doc, "entrance_test", 0)
    allocation.intereview           = getattr(applicant_doc, "intereview", 0)
    allocation.exempts_entrance_test = cint(getattr(applicant_doc, "exempts_entrance_test", 0))
    allocation.exempts_interview    = cint(getattr(applicant_doc, "exempts_interview", 0))

    # Mark as allocated (online); leave center/room/seat fields blank
    allocation.allocation_status    = "Allocated"
    allocation.entrance_test_status = "Scheduled"
    allocation.allocated_by         = frappe.session.user
    allocation.is_international_applicant = 1

    # Attach applicant categories
    try:
        categories = applicant_doc._get_applicant_categories()
        for cat in categories:
            allocation.append("category", {"category": cat})
    except Exception:
        pass

    allocation.insert(ignore_permissions=True)


    # Send international-specific email (NO admit card attached)
    try:
        from slcm.admission.doctype.entrance_test_list.entrance_test_list import (
            _send_allocation_notification,
        )

        if allocation.email:
            _send_international_entrance_test_email(allocation, allocation.email)
            _send_allocation_notification(allocation, allocation.email)
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"International auto allocation email failed for {allocation.name}",
        )


def _send_international_entrance_test_email(allocation, email):
    """
    Send the international applicant entrance test notification email.
    Uses Email Template: 'International Entrance Test Allocation'

    This email:
    - Informs the applicant their entrance test is scheduled as an ONLINE test
    - Provides test name, test date, and basic application info
    - Does NOT include any admit card or center details

    If the template does not exist, a default fallback HTML email is sent
    so that the applicant is always notified.
    """
    if not allocation or not email:
        return

    try:
        template_name = "International Entrance Test Allocation"

        # Resolve institution name for fallback
        institution_name = (
            frappe.db.get_single_value("Institution Settings", "institution_name")
            or "Admissions Office"
        )
        portal_url = frappe.utils.get_url(
            "/merit-and-scholarship/admission_dashboard?panel=applications"
        )

        # Format test date for display
        test_date_raw = allocation.allocation_date
        test_date_display = (
            frappe.utils.formatdate(str(test_date_raw), "dd MMM yyyy")
            if test_date_raw
            else "To be announced"
        )

        args = {
            "doc": allocation.as_dict(),
            "candidate_name":    allocation.candidate_name or "",
            "entrance_test_name": allocation.entrance_test_name or "Entrance Test",
            "test_date":         test_date_display,
            "program":           allocation.program or "",
            "institution_name":  institution_name,
            "portal_url":        portal_url,
        }

        subject = ""
        message_body = ""

        if frappe.db.exists("Email Template", template_name):
            template = frappe.get_doc("Email Template", template_name)
            subject = frappe.render_template(template.subject or "", args)
            if template.get("use_html"):
                message_body = frappe.render_template(template.response_html or "", args)
            else:
                message_body = frappe.render_template(template.response or "", args)
            if not message_body:
                message_body = frappe.render_template(template.get("message") or "", args)

            cc_list = []
            cc_field_value = template.get("cc")
            if cc_field_value:
                cc_list = [
                    c.strip()
                    for c in cc_field_value.replace(";", ",").split(",")
                    if c.strip()
                ]

            sender = None
            if template.get("email_account"):
                sender = (
                    frappe.db.get_value(
                        "Email Account", template.get("email_account"), "email_id"
                    )
                    or template.get("email_account")
                )
        else:
            # ── Fallback: built-in HTML (template not yet created) ────────────
            frappe.log_error(
                f"Email Template '{template_name}' not found — using built-in fallback.",
                "International Allocation Email",
            )
            subject = (
                f"Entrance Test Scheduled (Online) — "
                f"{allocation.entrance_test_name or 'Entrance Test'} | "
                f"{allocation.candidate_name or email}"
            )
            message_body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
  <h2 style="color:#1a5276;">Entrance Test Allocated — Online</h2>
  <p>Dear <strong>{allocation.candidate_name or 'Applicant'}</strong>,</p>
  <p>
    Congratulations! Your entrance test has been scheduled for the programme
    <strong>{allocation.program or ''}</strong>.
  </p>
  <table style="border-collapse:collapse;width:100%;margin:16px 0;">
    <tr>
      <td style="padding:8px;border:1px solid #ddd;font-weight:bold;width:40%;">Test Name</td>
      <td style="padding:8px;border:1px solid #ddd;">{allocation.entrance_test_name or '—'}</td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Test Date</td>
      <td style="padding:8px;border:1px solid #ddd;">{test_date_display}</td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Test Mode</td>
      <td style="padding:8px;border:1px solid #ddd;">
        <strong style="color:#1a5276;">Online</strong>
      </td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Programme</td>
      <td style="padding:8px;border:1px solid #ddd;">{allocation.program or '—'}</td>
    </tr>
  </table>
  <p>
    As an international applicant, your entrance test will be conducted
    <strong>online</strong>. Further instructions regarding the online test
    platform, login credentials, and technical requirements will be shared
    with you separately.
  </p>
  <p>
    You can view your application and test details on your admission dashboard:
    <a href="{portal_url}" style="color:#1a5276;font-weight:bold;">Click here to view</a>.
  </p>
  <p>We wish you the best of luck!</p>
  <p style="color:#555;">Regards,<br/><strong>{institution_name}</strong></p>
</div>
"""
            cc_list = []
            sender = None

        if not message_body:
            return

        frappe.sendmail(
            recipients=[email],
            sender=sender,
            cc=cc_list,
            subject=subject,
            message=message_body,
            reference_doctype="Entrance Test Seat Allocation",
            reference_name=allocation.name,
            now=False,
        )

    except Exception:
        frappe.log_error(
            message=traceback.format_exc(),
            title=f"International Entrance Test Email Failed: {allocation.name if allocation else 'unknown'}",
        )


def send_submission_confirmation_background(applicant_name):
    doc = frappe.get_doc("Applicant", applicant_name)
    doc.send_submission_confirmation()

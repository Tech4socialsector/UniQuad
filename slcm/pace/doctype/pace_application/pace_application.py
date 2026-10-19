# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.pdf import get_pdf
from frappe.utils import cint, get_url
import traceback
import time
import random
import io
import os
import uuid
import zipfile
from frappe.utils.file_manager import save_file

class PACEApplication(Document):
    def before_validate(self):
        # Save Draft: skip mandatory check so user can save incomplete form.
        if self.status == "Draft":
            self.flags.ignore_mandatory = True

    def validate(self):
        self.enforce_uppercase()
        self.set_applicant_name()
        self.validate_ug_degree_rows()
        self.validate_ug_certificate()
        self.validate_single_application_per_year()
        self.validate_programme_admission_status()
        self.validate_programme_change()
        self.validate_geography_hierarchy()

 
    def validate_geography_hierarchy(self):
        def _validate_hierarchy(country, state, district):
            if state and str(state).lower() not in ["other", "others"] and country and str(country).lower() not in ["other", "others"]:
                state_country = frappe.db.get_value("State", state, "country")
                if state_country and state_country != country:
                    frappe.throw(_("State '{0}' does not belong to country '{1}'.").format(state, country))

            if district and str(district).lower() not in ["other", "others"] and state and str(state).lower() not in ["other", "others"]:
                city_data = frappe.db.get_value("City", district, ["state", "country"], as_dict=True)
                if city_data:
                    if city_data.get("state") and city_data.get("state") != state:
                        frappe.throw(_("District '{0}' does not belong to state '{1}'.").format(district, state))
                    if country and str(country).lower() not in ["other", "others"] and city_data.get("country") and city_data.get("country") != country:
                        frappe.throw(_("District '{0}' does not belong to country '{1}'.").format(district, country))

        _validate_hierarchy(self.country, self.state, self.district)
        if not self.is_permanent_address_same:
            _validate_hierarchy(self.p_country, self.p_state, self.p_district)

    def enforce_uppercase(self):
        uppercase_fields = [
            "first_name", "middle_name", "last_name", "applicant_name",
            "organization_name", "designation", "please_specify",
            "father_name", "mother_name", "address_line_1", "address_line_2", "city"
        ]
        for field in uppercase_fields:
            if getattr(self, field, None):
                setattr(self, field, str(getattr(self, field)).upper())

        # Child table fields
        for row in self.get("ug_degree", []):
            if row.institution_name:
                row.institution_name = str(row.institution_name).upper()
            if row.university:
                row.university = str(row.university).upper()
            if row.programme_studied:
                row.programme_studied = str(row.programme_studied).upper()

    def validate_programme_admission_status(self):
        # Only validate for draft/new applications
        if not self.is_new() and self.status not in ["Draft", "Returned for Correction"]:
            return

        if not self.programme:
            return

        # 1. Check if there is an active PACE Admission
        active_admission = frappe.db.get_value("PACE Admission", {"status": "Active"}, "name")
        if not active_admission:
            msg = _("There is no active PACE Admission cycle at this time.")
            if self.is_new():
                msg += " " + _("New applications cannot be created.")
            else:
                msg += " " + _("Applications cannot be edited or submitted.")
            frappe.throw(msg, title=_("Admission Closed"))

        # Check Close Date
        close_date = frappe.db.get_value("PACE Admission", active_admission, "admission_close_date")
        if close_date:
            from frappe.utils import getdate, today
            if getdate(today()) > getdate(close_date):
                msg = _("The admission cycle closed on {0}.").format(frappe.utils.formatdate(close_date))
                if self.is_new():
                    msg += " " + _("New applications cannot be created.")
                else:
                    msg += " " + _("You can no longer edit or submit your application.")
                frappe.throw(msg, title=_("Admission Closed"))

        # 2. Check if the programme is in the active PACE Admission and its status is Open
        admission_programme = frappe.db.get_value(
            "PACE Admission Programme",
            {"parent": active_admission, "programme": self.programme},
            ["name", "status"],
            as_dict=True
        )

        if not admission_programme:
            frappe.throw(
                _("The selected programme '{0}' is not available for admission in the current cycle.").format(self.programme),
                title=_("Programme Not Available")
            )

        if admission_programme.status != "Open":
            frappe.throw(
                _("The selected programme '{0}' is closed for admission in the current cycle.").format(self.programme),
                title=_("Programme Closed")
            )

    def validate_programme_change(self):
        """
        Programme change validation.
        Programme change on PACE Application is allowed at any stage.
        If the Course Fee is already Paid/Enrolled/Converted, the Fee Assignment will not be altered.
        """
        pass

    def handle_programme_change(self):
        if self.is_new():
            return

        doc_before_save = self.get_doc_before_save()
        if not doc_before_save:
            return

        old_programme = getattr(doc_before_save, "programme", None)
        if old_programme and self.programme != old_programme:
            # 1. Update existing Course Fee assignment ONLY if it exists and is UNPAID (not Paid, Enrolled, or Converted)
            assignment_name = frappe.db.get_value("PACE Applicant Fee Assignment", {
                "applicant": self.name,
                "fee_type": "Course Fee",
                "status": ["not in", ["Paid", "Enrolled", "Converted"]]
            }, "name")

            if assignment_name:
                assign_doc = frappe.get_doc("PACE Applicant Fee Assignment", assignment_name)
                
                # Determine nationality type to select the right child table
                nationality = (self.get("nationality") or "").strip().lower()
                nationality_type = "Indian" if nationality in ["indian", "india"] else "Foreign"

                # Find active fee structure for this program
                filters = {
                    "pace_program": self.programme,
                    "status": "Active"
                }
                if self.academic_year:
                    filters["academic_year"] = self.academic_year

                fee_structure_name = frappe.db.get_value("PACE Fee Structure", filters, "name")

                if not fee_structure_name:
                    frappe.throw(
                        _("Active Fee Structure not found for program {0}. Please create one to update fee assignment.").format(self.programme)
                    )

                fs_doc = frappe.get_doc("PACE Fee Structure", fee_structure_name)

                assign_doc.program = self.programme
                assign_doc.fee_structure = fs_doc.name
                assign_doc.nationality_type = nationality_type
                assign_doc.currency = fs_doc.currency
                assign_doc.academic_year = self.academic_year

                assign_doc.set("fee_components", [])
                if nationality_type == "Indian":
                    components = fs_doc.fee_components_for_indians
                    total_amount = fs_doc.total_amount
                else:
                    components = fs_doc.fee_components_for_foreign
                    total_amount = fs_doc.total_amount_for_foreign

                for row in components:
                    assign_doc.append("fee_components", {
                        "fee_component": row.fee_component,
                        "amount": row.amount,
                        "tax_rate": row.tax_rate,
                        "tax_amount": row.tax_amount,
                        "total_amount": row.total_amount
                    })

                assign_doc.total_amount = total_amount
                assign_doc.final_payable_amount = total_amount
                assign_doc.flags.ignore_permissions = True
                assign_doc.save(ignore_permissions=True)

                # Cancel associated Payment Requests
                frappe.db.sql("""
                    UPDATE `tabPayment Request`
                    SET status = 'Cancelled'
                    WHERE reference_doctype = 'PACE Applicant Fee Assignment'
                      AND reference_name = %s
                      AND status not in ('Paid', 'Cancelled')
                """, (assign_doc.name,))

            # 2. Update PACE Document Verification's programme
            verification_name = frappe.db.get_value("PACE Document Verification", {"application": self.name}, "name")
            if verification_name:
                frappe.db.set_value("PACE Document Verification", verification_name, "programme", self.programme)

            # 3. If application is Verified but no assignment exists at all, generate a new fee assignment
            has_any_assignment = frappe.db.exists("PACE Applicant Fee Assignment", {
                "applicant": self.name,
                "fee_type": "Course Fee"
            })
            if not has_any_assignment and self.status in ["Verified", "Payment Pending"]:
                from slcm.pace.utils import create_pace_fee_assignment
                create_pace_fee_assignment(self.name)


    def validate_single_application_per_year(self):
        """
        Enforce that an applicant can only have ONE application per academic year,
        unless 'allow_multiple_application_per_applicant' is checked in the PACE Admission.
        """
        if not self.email_address or not self.academic_year:
            return

        # 1. Check if PACE Admission allows multiple applications for this academic year
        allow_multiple = frappe.db.get_value(
            "PACE Admission",
            {"academic_year": self.academic_year, "status": "Active"},
            "allow_multiple_application_per_applicant"
        )
        
        # Fallback to any admission for that year if no active one is found
        if allow_multiple is None:
            allow_multiple = frappe.db.get_value(
                "PACE Admission",
                {"academic_year": self.academic_year},
                "allow_multiple_application_per_applicant"
            )

        if allow_multiple:
            return

        # 2. Check if any other application exists for the same email and same academic year
        # that is NOT the current record.
        existing = frappe.db.get_value(
            "PACE Application",
            {
                "email_address": self.email_address,
                "academic_year": self.academic_year,
                "name": ["!=", self.name],
                "status": ["!=", "Cancelled"]
            },
            "name"
        )

        if existing:
            frappe.throw(
                _("You have already submitted an application ({0}) for the {1} academic year. Only one application is allowed per academic year.").format(
                    existing, self.academic_year
                ),
                title=_("Duplicate Application")
            )

    def validate_ug_degree_rows(self):
        """Portal web form does not always enforce child-table reqd; enforce here."""
        if getattr(self, "flags", None) and (
            self.flags.get("ignore_validate") or self.flags.get("ignore_mandatory")
        ):
            return

        rows = self.get("ug_degree") or []
        if not rows:
            frappe.throw(
                _("Please add at least one UG Degree entry."),
                title=_("Education Details"),
            )

        for i, row in enumerate(rows, start=1):
            if not (getattr(row, "institution_name", None) or "").strip():
                frappe.throw(_("UG Degree row {0}: Institution Name is mandatory").format(i))
            if not (getattr(row, "university", None) or "").strip():
                frappe.throw(_("UG Degree row {0}: University is mandatory").format(i))
            if not (getattr(row, "programme_studied", None) or "").strip():
                frappe.throw(_("UG Degree row {0}: Programme Studied is mandatory").format(i))
            yp = getattr(row, "year_of_passing", None)
            if yp is None or yp == "" or cint(yp) <= 0:
                frappe.throw(_("UG Degree row {0}: Year of Passing is mandatory").format(i))
            yi = cint(yp)
            if yi < 1000 or yi > 9999:
                frappe.throw(
                    _("UG Degree row {0}: Year of Passing must be exactly 4 digits (1000–9999).").format(i)
                )
            rs = (getattr(row, "result_status", None) or "").strip()
            if not rs:
                frappe.throw(_("UG Degree row {0}: Result Status is mandatory").format(i))
            if rs == "Declared":
                if not (getattr(row, "marking_scheme", None) or "").strip():
                    frappe.throw(
                        _(
                            "UG Degree row {0}: Marking Scheme is mandatory when Result Status is Declared"
                        ).format(i)
                    )
                pct = getattr(row, "obtained_percentagecgpa", None)
                if pct is None or pct == "":
                    frappe.throw(
                        _(
                            "UG Degree row {0}: Obtained Percentage/CGPA is mandatory when Result Status is Declared"
                        ).format(i)
                    )

    def validate_ug_certificate(self):
        """UG Degree Certificate attachment check.

        TEMPORARY: always require the certificate when not Draft.
        Original logic (Declared vs Waiting for result only) is kept in comments below.
        """
        if self.status not in ["Draft"]:
            if not self.ug_degree_certificate:
                frappe.throw(
                    _("UG Degree Certificate is mandatory."),
                    title=_("Mandatory Document Missing"),
                )

        # --- ORIGINAL (result status) — restore when removing TEMP above ---
        # waiting = any(row.result_status == "Waiting for result" for row in self.get("ug_degree") or [])
        # declared = any(row.result_status == "Declared" for row in self.get("ug_degree") or [])
        # if declared and not waiting and self.status not in ["Draft"]:
        #     if not self.ug_degree_certificate:
        #         frappe.throw(
        #             _("UG Degree Certificate is mandatory since result status is 'Declared'."),
        #             title=_("Mandatory Document Missing"),
        #         )

    def before_save(self):
        """Set submission date when status transitions to Submitted or Completed."""
        doc_before_save = self.get_doc_before_save()
        prev_status = (doc_before_save.status if doc_before_save and hasattr(doc_before_save, "status") else None)

        if self.status in ["Submitted", "Completed"] and prev_status not in ["Submitted", "Completed"]:
            if not self.submission_date:
                self.submission_date = frappe.utils.today()
        # NOTE: File renaming is now handled entirely on the frontend (FormData patch in
        # pace_application_form.js) so handle_file_name() is no longer called here.
        # This eliminates the deferred after_commit rename that caused orphaned files.

        if not self.user_id:
            self.user_id = self.email_address or None

    
    def handle_file_name(self):
        doc_before = self.get_doc_before_save()
        for df in self.meta.fields:
            if df.fieldtype in ["Attach", "Attach Image"]:
                file_url = self.get(df.fieldname)
                if not file_url:
                    continue
                    
                # Skip if the file was not changed in this transaction (prevents auto-upgrading old files and breaking validations)
                if doc_before:
                    prev_url = doc_before.get(df.fieldname)
                    if prev_url == file_url:
                        continue
                    
                file_name_from_url = file_url.split("/")[-1]
                is_uuid = False
                if len(file_name_from_url) > 13 and file_name_from_url[12] == "_" and file_name_from_url[:12].isalnum():
                    is_uuid = True
                
                if is_uuid:
                    try:
                        file_doc = frappe.get_doc("File", {"file_url": file_url})
                        if not file_doc.is_private:
                            file_doc.is_private = 1
                            file_doc.save(ignore_permissions=True)
                            self.set(df.fieldname, file_doc.file_url)
                    except Exception:
                        pass
                    continue
                
                # Check for stale frontend state sending the old URL
                if doc_before:
                    prev_url = doc_before.get(df.fieldname)
                    if prev_url and prev_url != file_url:
                        prev_name = prev_url.split("/")[-1]
                        if len(prev_name) > 13 and prev_name[12] == "_" and prev_name[13:] == file_name_from_url:
                            self.set(df.fieldname, prev_url)
                            continue
                
                # It's a genuine new upload, generate a UUID
                try:
                    import uuid
                    file_doc = frappe.get_doc("File", {"file_url": file_url})

                    new_file_name = f"{uuid.uuid4().hex[:12]}_{file_doc.file_name}"
                    new_file_url = f"/private/files/{new_file_name}"

                    # Update doc IMMEDIATELY so the DB transaction saves it
                    self.set(df.fieldname, new_file_url)

                    # Defer physical move to avoid 404 on transaction rollback
                    f_name = file_doc.name
                    _doc_name = self.name
                    _doc_type = self.doctype
                    _fieldname = df.fieldname

                    def move_file_after_commit(f_name, n_name, n_url, doc_type, doc_name, fieldname):
                        try:
                            import shutil, os
                            f_doc = frappe.get_doc("File", f_name)

                            old_path = f_doc.get_full_path()
                            new_path = frappe.get_site_path("private", "files", n_name)

                            if os.path.exists(old_path):
                                shutil.move(old_path, new_path)

                            frappe.db.set_value("File", f_name, {
                                "file_name": n_name,
                                "file_url": n_url,
                                "is_private": 1,
                                "attached_to_doctype": doc_type,
                                "attached_to_name": doc_name,
                                "attached_to_field": fieldname,
                            })
                            frappe.db.commit()
                        except Exception as e:
                            frappe.log_error("handle_file_name deferred error", str(e))

                    frappe.db.after_commit.add(lambda f=f_name, n=new_file_name, u=new_file_url, dt=_doc_type, dn=_doc_name, fn=_fieldname: move_file_after_commit(f, n, u, dt, dn, fn))
                except Exception:
                    frappe.log_error(title="handle_file_name error", message=frappe.get_traceback())

    def set_applicant_name(self):
        """Populate applicant_name from first, middle, and last names."""
        name_parts = [self.first_name, self.middle_name, self.last_name]
        full_name = " ".join([p for p in name_parts if p]).strip()
        # Remove any double spaces
        while "  " in full_name:
            full_name = full_name.replace("  ", " ")
        self.applicant_name = full_name

    def autoname(self):
        from frappe.model.naming import make_autoname
        # Incremental serial number with random-like unique padding
        # Format example: PACE-2024-00001
        year = self.academic_year or frappe.utils.now_datetime().year
        self.name = make_autoname(f"PACE-{year}-.#####")
		

    def on_update(self):
        """
        Sync documents, generate PDF, and on status change to Submitted/Completed:
        send confirmation email directly (no background worker dependency).
        """
        self.handle_programme_change()
        self.sync_user_profile()
        self.sync_documents_to_verification()

        # Generate the application PDF when the status is "Draft", "Submitted", or "Completed"
        if self.status in ["Draft", "Submitted", "Completed"] and not self.flags.get("in_pdf_generation"):
            self.generate_application_pdf()

        doc_before_save = self.get_doc_before_save()
        prev_status = (doc_before_save.status if doc_before_save and hasattr(doc_before_save, 'status') else None)

        # Fire when status is Submitted (for email/notification) or Completed (for verification)
        # and (it just changed OR verification record is missing)
        verification_exists = frappe.db.exists("PACE Document Verification", {"application": self.name})
        if self.status in ["Submitted", "Completed"] and (prev_status != self.status or not verification_exists):
            
            if self.status == "Submitted":
                # Send email DIRECTLY — returns True if queued, False if failed
                email_sent = send_pace_submission_email(self)

                # Send in-app system notification directly
                try:
                    send_pace_system_notification(self)
                except Exception:
                    frappe.log_error(traceback.format_exc(), f"PACE System Notification Failed: {self.name}")

                # Push toast to browser via realtime
                user = self.owner or frappe.session.user or "Administrator"
                frappe.publish_realtime(
                    event="pace_email_status",
                    message={
                        "status": "success" if email_sent else "error",
                        "doc_name": self.name,
                        "recipient": self.email_address or ""
                    },
                    user=user
                )

            # Create document verification record synchronously for better reliability
            if self.status == "Completed":
                try:
                    from slcm.pace.doctype.pace_document_verification.get_document_api import (
                        ensure_document_verification_for_completed_application,
                    )
                    ensure_document_verification_for_completed_application(self)
                except Exception:
                    frappe.log_error(message=traceback.format_exc(), title=f"Post Submission Doc Verification Failed: {self.name}")

        # --- Update application_received count and handle seat limit ---
        if self.status in ["Completed"] and prev_status not in ["Completed"]:
            self.update_admission_programme_stats()

    def update_admission_programme_stats(self):
        """
        Increments the application_received count in the PACE Admission Programme child table.
        If the total_seats limit is reached, it closes the programme.
        """
        try:
            from slcm.pace.api import _get_active_pace_admission_name
            pace_admission = _get_active_pace_admission_name(academic_year=self.academic_year)
            if not pace_admission:
                return

            # Find the specific row for this programme
            programme_row = frappe.db.get_value(
                "PACE Admission Programme",
                {"parent": pace_admission, "programme": self.programme},
                ["name", "total_seats", "application_received", "status"],
                as_dict=True
            )

            if programme_row:
                new_received = (programme_row.application_received or 0) + 1
                update_dict = {"application_received": new_received}
                
                # Check if we need to close the programme
                # 0 or None means infinity
                if programme_row.status == "Open" and programme_row.total_seats and programme_row.total_seats > 0:
                    if new_received >= programme_row.total_seats:
                        update_dict["status"] = "Closed"
                        frappe.logger().info(f"PACE Admission: Closing programme {self.programme} in {pace_admission} due to seat limit.")

                frappe.db.set_value("PACE Admission Programme", programme_row.name, update_dict)
                frappe.db.commit()

        except Exception:
            frappe.log_error(traceback.format_exc(), f"PACE Application: Failed to update admission stats for {self.name}")

    def sync_user_profile(self):
        if not self.email_address:
            return
            
        user_name = frappe.db.get_value("User", {"email": self.email_address}, "name")
        if not user_name:
            return
            
        user = frappe.get_doc("User", user_name)
        updated = False
        
        if self.first_name and user.first_name != self.first_name:
            user.first_name = self.first_name
            updated = True
            
        if self.last_name is not None and (user.last_name or "") != self.last_name:
            user.last_name = self.last_name
            updated = True
                
        if self.mobile_number and user.phone != self.mobile_number:
            user.phone = self.mobile_number
            updated = True
            
        if self.gender and user.gender != self.gender:
            user.gender = self.gender
            updated = True
            
        from frappe.utils import getdate
        if self.date_of_birth and getdate(user.birth_date) != getdate(self.date_of_birth):
            user.birth_date = self.date_of_birth
            updated = True
            
        if self.country and user.country != self.country:
            user.country = self.country
            updated = True
            
        if self.status in ["Submitted", "Completed"]:
            address_parts = [
                self.city,
                self.district,
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

    def sync_documents_to_verification(self):
        """
        Sync document files to the verification record if they have changed.
        Also add missing document items if they exist on the application.
        """
        verification_name = frappe.db.get_value("PACE Document Verification", {"application": self.name}, "name")
        if not verification_name:
            return

        verification = frappe.get_doc(
            "PACE Document Verification", verification_name, check_permission=False
        )
        updated = False

        # Identify specific document fields to sync
        verify_fieldnames = [
            "upload_student_photo",
            "student_signature",
            "ug_degree_certificate",
            "govt_id",
        ]
        
        meta = frappe.get_meta("PACE Application")
        attach_fields = [
            f for f in meta.fields 
            if f.fieldname in verify_fieldnames
        ]

        existing_fieldnames = [row.fieldname for row in verification.verification_items]

        for field in attach_fields:
            current_file = self.get(field.fieldname)

            if field.fieldname in existing_fieldnames:
                # Update existing entry (even if current_file is empty)
                for row in verification.verification_items:
                    if row.fieldname == field.fieldname:
                        if row.file != current_file:
                            row.file = current_file
                            updated = True
                        break
            elif current_file:
                # Add missing entry (only if there is actually a file)
                verification.append("verification_items", {
                    "document_name": field.label,
                    "fieldname": field.fieldname,
                    "file": current_file,
                    "status": "Pending"
                })
                updated = True
        
        if updated:
            verification.save(ignore_permissions=True)

    def generate_application_pdf(self):
        self.flags.in_pdf_generation = True
        try:
            pdf_content = self.get_application_pdf_content()
            if not pdf_content:
                return

            timestamp = int(time.time())
            filename = f"PACE_Application_{self.name}_{timestamp}.pdf"
            
            existing_files = frappe.get_all("File", filters={
                "attached_to_doctype": self.doctype,
                "attached_to_name": self.name,
                "attached_to_field": "application_form"
            })
            
            for f in existing_files:
                frappe.delete_doc("File", f.name, ignore_permissions=True)
            
            _file = frappe.get_doc({
                "doctype": "File",
                "file_name": filename,
                "attached_to_doctype": self.doctype,
                "attached_to_name": self.name,
                "attached_to_field": "application_form",
                "content": pdf_content,
                "is_private": 1
            })
            _file.insert(ignore_permissions=True)
            file_url = _file.file_url
            
            if self.application_form != file_url:
                self.db_set("application_form", file_url, update_modified=False)
                self.application_form = file_url
                
        except Exception:
            frappe.log_error(message=traceback.format_exc(), title=f"PACE Application PDF Generation Failed: {self.name}")
        finally:
            self.flags.in_pdf_generation = False

    def get_application_pdf_content(self):
        print_format_name = "Pace Application Form"
        if not frappe.db.exists("Print Format", print_format_name):
            return None

        return frappe.get_print(
            self.doctype, 
            self.name, 
            print_format_name, 
            as_pdf=True, 
            no_letterhead=True,
            doc=self
        )

    def has_permission(self, permtype="read", user=None, **kwargs):
        """
        Security: Ensures that PACE Applicants can only access their own records.
        """
        if not user:
            user = frappe.session.user

        if user == "Guest":
            return False

        roles = frappe.get_roles(user)

        # Full access
        if "Administrator" in roles or "System Manager" in roles:
            return True

        if "PACE Applicant" in roles:
            owner = getattr(self, "owner", None)
            email = getattr(self, "email_address", None)
            if owner and owner != user and email and email != user:
                return False
            # Check if this is a new doc or being created
            if not self.is_new() and self.name:
                # Extra DB check just to be absolutely sure
                db_owner = frappe.db.get_value("PACE Application", self.name, "owner")
                db_email = frappe.db.get_value("PACE Application", self.name, "email_address")
                if db_owner and db_owner != user and db_email and db_email != user:
                    return False
            return True

        # Everyone else -> use standard Frappe permissions
        return super().has_permission(permtype=permtype, user=user, **kwargs)

    def has_website_permission(self):
        """
        Security: Native web view security hook.
        """
        if frappe.session.user == "Guest":
            return False
            
        roles = frappe.get_roles(frappe.session.user)
        if "Administrator" in roles or "System Manager" in roles:
            return True
            
        if getattr(self, "email_address", None) and self.email_address == frappe.session.user:
            return True
            
        return False

    def has_webform_permission(self):
        """
        Security: Native web form security hook.
        """
        return self.has_website_permission()

def send_pace_submission_email(doc):
    """
    Sends the submission confirmation email using the 'PACE Application Submitted' Email Template.
    Follows the exact same pattern as the working entrance_test_seat_allocation email sender:
      - now=False  → queues to Email Queue (visible in Email Queue list)
      - doc.as_dict() → correct Jinja template rendering
      - message_body guard → never sends blank emails
    Returns True if queued successfully, False otherwise.
    """
    template_name = "PACE Application Submitted"

    # --- 1. Recipient ---
    recipient = doc.email_address
    if not recipient:
        frappe.log_error(
            f"No email_address on {doc.name}. Email skipped.",
            "PACE Email: No Recipient"
        )
        return False

    # --- 2. Institution name (safe) ---
    institution_name = "NLSIU"
    try:
        inst_settings = frappe.get_single("Institution Settings")
        institution_name = inst_settings.institution_name or institution_name
    except Exception:
        pass  # Use fallback silently

    # --- 3. Template args using as_dict() (matches working reference exactly) ---
    doc_dict = doc.as_dict()
    args = {
        "doc": doc_dict,
        "first_name": doc.first_name or "",
        "candidate_name": f"{doc.first_name or ''} {doc.last_name or ''}".strip(),
        "program": doc.programme or "",
        "applicant_id": doc.name,
        "institution_name": institution_name,
        "admission_portal_url": get_url("/admissions"),
        "generated_on": frappe.utils.format_datetime(frappe.utils.now_datetime(), "dd-MM-yyyy HH:mm:ss")
    }

    # --- 4. Load Email Template ---
    if not frappe.db.exists("Email Template", template_name):
        frappe.log_error(
            f"Email Template '{template_name}' not found.",
            f"PACE Email: Template Missing ({doc.name})"
        )
        return False

    email_template = frappe.get_doc("Email Template", template_name)

    # --- 5. Render Subject ---
    try:
        subject = frappe.render_template(email_template.subject or "PACE Application Submitted", args)
    except Exception:
        subject = "PACE Application Submitted"

    # --- 6. Render Message body (matches working reference pattern exactly) ---
    message_body = ""
    try:
        if email_template.get("use_html") and email_template.get("response_html"):
            message_body = frappe.render_template(email_template.response_html, args)
        elif email_template.get("response"):
            message_body = frappe.render_template(email_template.response, args)

        if not message_body:
            message_body = frappe.render_template(email_template.get("message") or "", args)
    except Exception:
        frappe.log_error(traceback.format_exc(), f"PACE Email: Body render failed ({doc.name})")

    # Built-in fallback — never skip email due to bad template
    if not message_body:
        message_body = (
            f"<p>Dear {args['first_name']},</p>"
            f"<p>Your PACE application <strong>{doc.name}</strong> for "
            f"<strong>{args['program']}</strong> has been successfully submitted.</p>"
            f"<p>You can track your application at: "
            f"<a href='{args['admission_portal_url']}'>Admissions Portal</a></p>"
            f"<p>Regards,<br>{institution_name}</p>"
        )

    # --- 7. CC list (safe access, matches reference exactly) ---
    cc_list = []
    cc_field_value = email_template.get("cc")
    if cc_field_value:
        cc_list = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]

    # --- 8. PDF attachment ---
    attachments = get_application_attachments(doc)

    # --- 9. Send (now=False = queued for background sending) ---
    if message_body:
        try:
            # We use now=False to queue the email.
            # This ensures the process is fast and background workers handle the SMTP.
            frappe.sendmail(
                recipients=[recipient],
                sender=get_template_sender(email_template),
                cc=cc_list,
                subject=subject,
                message=message_body,
                attachments=attachments,
                reference_doctype=doc.doctype,
                reference_name=doc.name,
                now=False
            )
            
            # Log successful queueing
            frappe.logger().info(f"PACE Submission Email queued successfully to {recipient} for {doc.name}")
            return True
            
        except Exception:
            frappe.log_error(
                traceback.format_exc(),
                f"PACE Email Queueing Failed: {doc.name}"
            )
            return False

    frappe.log_error(
        f"message_body was empty, email NOT sent for {doc.name}",
        f"PACE Email: Empty Body ({doc.name})"
    )
    return False

def process_post_submission(doc_name):
    """
    Background job (default queue) — handles document verification after submission.
    Email and system notification are sent directly in on_update (not here).
    """
    try:
        from slcm.pace.doctype.pace_document_verification.get_document_api import (
            ensure_document_verification_for_completed_application,
        )
        ensure_document_verification_for_completed_application(doc_name)
    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"Post Submission Doc Verification Failed: {doc_name}")

def send_pace_system_notification(doc):
    """
    Creates a Notification Log entry for the applicant in the system portal.
    """
    try:
        recipient = doc.email_address
        if not recipient:
            return

        # Check if the user exists in the system (email is usually the User ID)
        if frappe.db.exists("User", recipient):
            message_body = f"""
                <p>Your application to <strong>National Law School of India University (NLSIU)</strong> for the <strong>{doc.programme} (PACE)</strong> has been successfully submitted.</p>
                <p>Application Reference: <strong>{doc.name}</strong></p>
                <p><a href="/paceadmissions/progress-tracker?app={doc.name}" style="color: #920c24; font-weight: bold;">Click here to track your application.</a></p>
            """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": "PACE Application Submitted",
                "for_user": recipient,
                "type": "Alert",
                "email_content": message_body,
                "document_type": doc.doctype,
                "document_name": doc.name,
                "from_user": frappe.session.user or "Administrator",
                "link": f"/paceadmissions/progress-tracker?app={doc.name}"
            }).insert(ignore_permissions=True)

    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"PACE System Notification Failed: {doc.name}")


def get_template_sender(template):
    """Helper to resolve the sender email address from an Email Template's email_account field.
    Accepts either an Email Template doc or a template name string.
    """
    if not template:
        return None
    
    email_account = None
    if isinstance(template, str):
        email_account = frappe.db.get_value("Email Template", template, "email_account")
    else:
        email_account = template.get("email_account")

    if email_account:
        return frappe.db.get_value("Email Account", email_account, "email_id") or email_account
    return None

@frappe.whitelist(allow_guest=True)
def get_city_details(city):
    """
    Return state and country for a given city.
    Used by the PACE Application Web Form to auto-fill address details.
    """
    if not city:
        return {}
    return frappe.db.get_value("City", city, ["state", "country"], as_dict=True) or {}

def get_application_attachments(doc):
    """
    Helper function to get the PDF attachment.
    """
    attachments = []
    if doc.application_form:
        file_name = frappe.db.get_value("File", {"file_url": doc.application_form}, "name")
        if file_name:
            try:
                file_doc = frappe.get_doc("File", file_name)
                content = file_doc.get_content()
                if content:
                    attachments.append({
                        "fname": file_doc.file_name,
                        "fcontent": content
                    })
            except Exception as e:
                frappe.log_error(
                    message=f"Could not read application form PDF for {doc.name}: {str(e)}",
                    title="PACE Application Attachment Error"
                )
    return attachments

def chunked(iterable, size=500):
    """Yield successive chunks from iterable."""
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]

def get_file_bytes_and_ext(file_url, file_meta_map):
    """
    Fast file reader directly accessing disk file path.
    Avoids loading full File Document ORM objects.
    """
    if not file_url:
        return None, None
    from urllib.parse import unquote
    clean_url = unquote(file_url)

    ext = ""
    file_meta = file_meta_map.get(clean_url) or file_meta_map.get(file_url)
    if file_meta and file_meta.get("file_name"):
        ext = os.path.splitext(file_meta["file_name"])[1]
    if not ext:
        ext = os.path.splitext(clean_url)[1]
    if not ext:
        ext = ".bin"

    if clean_url.startswith("/private/files/"):
        rel_path = clean_url.split("/private/files/", 1)[1]
        file_path = frappe.get_site_path("private", "files", rel_path)
    elif clean_url.startswith("/files/"):
        rel_path = clean_url.split("/files/", 1)[1]
        file_path = frappe.get_site_path("public", "files", rel_path)
    else:
        file_path = frappe.get_site_path(clean_url.lstrip("/"))

    if os.path.exists(file_path):
        try:
            with open(file_path, "rb") as f:
                return f.read(), ext
        except Exception:
            pass

    if file_meta and file_meta.get("name"):
        try:
            file_doc = frappe.get_doc("File", file_meta["name"])
            content = file_doc.get_content()
            if content:
                return content, ext
        except Exception:
            pass

    return None, ext

@frappe.whitelist()
def bulk_download_all_records(names):
    """
    Creates a ZIP archive containing ALL uploaded documents for the selected PACE Applications.
    Organized by applicant ID folders. High-performance streaming implementation optimized for up to 10,000+ applicants.
    """
    if isinstance(names, str):
        names = frappe.parse_json(names)

    if not names:
        frappe.throw(_("Please select at least one application to download."))

    import tempfile

    # Disk-backed temporary file to avoid RAM exhaustion on 10,000+ applicants
    temp_zip_file = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    zip_path = temp_zip_file.name
    temp_zip_file.close()

    found_files = 0
    report_rows = []

    document_map = {
        "upload_student_photo": ("Student Photo", "Student_Photo"),
        "student_signature": ("Student Signature", "Student_Signature"),
        "ug_degree_certificate": ("UG Degree Certificate", "UG_Degree_Certificate"),
        "govt_id": ("Govt ID", "Govt_ID"),
        "application_form": ("Application Form", "Application_Form"),
        "admission_letter": ("Admission Letter", "Admission_Letter")
    }

    # 1. Batch fetch all PACE Application records in chunks of 500
    apps_dict = {}
    for chunk in chunked(names, 500):
        records = frappe.get_all(
            "PACE Application",
            filters={"name": ["in", chunk]},
            fields=[
                "name", "applicant_name", "first_name", "last_name", "programme", 
                "email_address", "mobile_number", "status",
                "upload_student_photo", "student_signature", "ug_degree_certificate",
                "govt_id", "application_form", "admission_letter"
            ],
            limit=0
        )
        for r in records:
            apps_dict[r.name] = r

    ordered_apps = [apps_dict[n] for n in names if n in apps_dict]

    # 2. Batch fetch all PACE Receipts in chunks of 500
    receipts_by_app = {}
    for chunk in chunked(names, 500):
        receipt_list = frappe.get_all(
            "PACE Receipt",
            filters={"pace_application": ["in", chunk]},
            fields=["name", "pace_application", "fee_type", "receipt"],
            limit=0
        )
        for r in receipt_list:
            receipts_by_app.setdefault(r.pace_application, []).append(r)

    # 3. Collect all File URLs and batch fetch File Doc metadata in chunks of 500
    all_file_urls = set()
    for app_data in ordered_apps:
        for fieldname in document_map:
            url = app_data.get(fieldname)
            if url:
                all_file_urls.add(url)
        for receipt in receipts_by_app.get(app_data.name, []):
            if receipt.get("receipt"):
                all_file_urls.add(receipt.receipt)

    file_meta_map = {}
    if all_file_urls:
        for chunk in chunked(list(all_file_urls), 500):
            file_records = frappe.get_all(
                "File",
                filters={"file_url": ["in", chunk]},
                fields=["name", "file_name", "file_url"],
                limit=0
            )
            for fr in file_records:
                if fr.file_url not in file_meta_map:
                    file_meta_map[fr.file_url] = fr

    total_names = len(ordered_apps)

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, doc in enumerate(ordered_apps, start=1):
                applicant_id = doc.name
                applicant_name = doc.applicant_name or f"{doc.first_name or ''} {doc.last_name or ''}".strip() or "Unknown_Applicant"
                folder_name = f"{applicant_name}-{applicant_id}"

                # Explicitly create folder entry in ZIP so extracted folder exists even if 0 files are retrieved
                zip_file.writestr(f"{folder_name}/", "")

                # Dynamic progress update step (every record for small sets, up to 50 updates for large sets)
                progress_step = max(1, total_names // 50)
                if idx % progress_step == 0 or idx == total_names:
                    percent = int((idx / total_names) * 100)
                    frappe.publish_realtime("progress", {
                        "progress": [idx, total_names],
                        "percent": percent,
                        "title": _("Exporting Attachments"),
                        "description": f"Processing {idx}/{total_names}: {applicant_name}"
                    }, user=frappe.session.user)

                missing_docs = []
                retrieved_docs = []

                for fieldname, (label, zip_label) in document_map.items():
                    file_url = doc.get(fieldname)
                    if not file_url:
                        if fieldname == "admission_letter":
                            continue
                        missing_docs.append(label)
                        continue

                    content, ext = get_file_bytes_and_ext(file_url, file_meta_map)
                    if content:
                        arcname = f"{folder_name}/{applicant_id}_{zip_label}{ext}"
                        zip_file.writestr(arcname, content)
                        found_files += 1
                        retrieved_docs.append(label)
                    else:
                        missing_docs.append(label)

                app_receipts = receipts_by_app.get(doc.name, [])
                for receipt in app_receipts:
                    if receipt.get("receipt"):
                        if receipt.fee_type == "Application Fee":
                            label = "Application Fee Receipt"
                            zip_label = "Application_Fee_Receipt"
                        elif receipt.fee_type == "Course Fee":
                            label = "Course Fee Receipt"
                            zip_label = "Course_Fee_Receipt"
                        else:
                            label = f"{receipt.fee_type} Receipt"
                            zip_label = f"{str(receipt.fee_type).replace(' ', '_')}_Receipt"

                        file_url = receipt.receipt
                        content, ext = get_file_bytes_and_ext(file_url, file_meta_map)
                        if content:
                            arcname = f"{folder_name}/{applicant_id}_{zip_label}{ext}"
                            zip_file.writestr(arcname, content)
                            found_files += 1
                            retrieved_docs.append(label)
                        else:
                            missing_docs.append(label)

                # If no document files could be downloaded, add an explanatory text file in their folder
                if len(retrieved_docs) == 0:
                    txt_content = (
                        f"Applicant ID: {applicant_id}\n"
                        f"Applicant Name: {applicant_name}\n"
                        f"Status: {doc.status or ''}\n\n"
                        f"No downloadable document files were found for this applicant on the server.\n\n"
                        f"Missing Documents Detail:\n"
                        + "\n".join([f"- {d}" for d in missing_docs])
                    )
                    zip_file.writestr(f"{folder_name}/{applicant_id}_MISSING_DOCUMENTS.txt", txt_content)

                if missing_docs:
                    report_rows.append({
                        "applicant_id": applicant_id,
                        "applicant_name": applicant_name,
                        "programme": doc.programme or "",
                        "email": doc.email_address or "",
                        "mobile": doc.mobile_number or "",
                        "status": doc.status or "",
                        "retrieved_count": len(retrieved_docs),
                        "missing_count": len(missing_docs),
                        "missing_documents": ", ".join(missing_docs)
                    })

            # Generate Excel report inside ZIP using constant memory mode
            if report_rows:
                try:
                    import xlsxwriter
                    excel_temp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
                    excel_path = excel_temp.name
                    excel_temp.close()

                    workbook = xlsxwriter.Workbook(excel_path, {"constant_memory": True})
                    worksheet = workbook.add_worksheet("Missing Documents Report")

                    header_format = workbook.add_format({
                        "bold": True,
                        "bg_color": "#920C24",
                        "font_color": "#FFFFFF",
                        "border": 1,
                        "align": "center",
                        "valign": "vcenter"
                    })
                    cell_format = workbook.add_format({"border": 1, "valign": "vcenter"})

                    headers = [
                        "Applicant ID",
                        "Applicant Name",
                        "Programme",
                        "Email",
                        "Mobile",
                        "Application Status",
                        "Downloaded Files Count",
                        "Missing Files Count",
                        "Missing Documents List"
                    ]

                    for col_idx, header in enumerate(headers):
                        worksheet.write(0, col_idx, header, header_format)

                    for row_idx, r in enumerate(report_rows, start=1):
                        worksheet.write(row_idx, 0, r["applicant_id"], cell_format)
                        worksheet.write(row_idx, 1, r["applicant_name"], cell_format)
                        worksheet.write(row_idx, 2, r["programme"], cell_format)
                        worksheet.write(row_idx, 3, r["email"], cell_format)
                        worksheet.write(row_idx, 4, r["mobile"], cell_format)
                        worksheet.write(row_idx, 5, r["status"], cell_format)
                        worksheet.write(row_idx, 6, r["retrieved_count"], cell_format)
                        worksheet.write(row_idx, 7, r["missing_count"], cell_format)
                        worksheet.write(row_idx, 8, r["missing_documents"], cell_format)

                    worksheet.set_column(0, 0, 25)
                    worksheet.set_column(1, 1, 28)
                    worksheet.set_column(2, 2, 25)
                    worksheet.set_column(3, 3, 28)
                    worksheet.set_column(4, 4, 15)
                    worksheet.set_column(5, 5, 20)
                    worksheet.set_column(6, 6, 22)
                    worksheet.set_column(7, 7, 18)
                    worksheet.set_column(8, 8, 60)

                    workbook.close()

                    with open(excel_path, "rb") as ef:
                        zip_file.writestr("Missing_Documents_Report.xlsx", ef.read())
                    os.remove(excel_path)
                except Exception as e:
                    frappe.log_error(
                        message=f"Failed to generate Excel missing documents report: {str(e)}",
                        title="PACE Bulk Export Excel Report Error"
                    )

        if found_files == 0 and not any(r["missing_count"] > 0 for r in report_rows):
            frappe.throw(_("No uploaded documents found for the selected records."))

        zip_filename = f"PACE_Bulk_Records_{frappe.utils.now_datetime().strftime('%Y%m%d_%H%M%S')}.zip"
        
        from frappe.utils import file_manager as utils_fm
        from frappe.core.api import file as core_file

        orig_utils_get_max = utils_fm.get_max_file_size
        orig_core_get_max = core_file.get_max_file_size

        large_limit = 5 * 1024 * 1024 * 1024
        utils_fm.get_max_file_size = lambda: large_limit
        core_file.get_max_file_size = lambda: large_limit

        try:
            with open(zip_path, "rb") as zf:
                _file = save_file(
                    zip_filename,
                    zf.read(),
                    "PACE Application",
                    names[0],
                    is_private=1
                )
        finally:
            utils_fm.get_max_file_size = orig_utils_get_max
            core_file.get_max_file_size = orig_core_get_max

        return _file.file_url

    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)


def send_document_reminders(current_item=0, total_items=0):
    """
    Scheduled task (daily at 10:00 AM) to send reminders for missing documents.
    Criteria:
    - Status is "Completed"
    - Missing any of: upload_student_photo, student_signature, ug_degree_certificate, govt_id
    - Before closing date: Send reminder
    - After closing date: Send rejection and update status
    """
    from frappe.utils import today, date_diff, getdate

    # Get active admission closing date
    from slcm.pace.api import _get_active_pace_admission_name
    pace_admission_name = _get_active_pace_admission_name()
    if not pace_admission_name:
        # If no Active admission, look for the admission record of the current active Academic Year
        active_ay = frappe.db.get_value("Academic Year", {"status": "Active"}, "name")
        if active_ay:
            pace_admission_name = frappe.db.get_value("PACE Admission", {"academic_year": active_ay, "docstatus": ["<", 2]}, "name")
            
    if not pace_admission_name:
        return 0

    admission_close_date = frappe.db.get_value("PACE Admission", pace_admission_name, "admission_close_date")
    if not admission_close_date:
        return 0

    today_date = getdate(today())
    close_date = getdate(admission_close_date)

    # Find applications that are Provisionally Submitted
    applications = frappe.get_all("PACE Application", filters={
        "status": "Provisionally Submitted"
    }, fields=["name", "email_address", "first_name", "last_name", "programme", 
              "student_signature", "ug_degree_certificate", "govt_id", 
              "last_reminder_sent"], limit=0)

    sent_count = 0
    total_apps = len(applications)
    
    for i, app_data in enumerate(applications):
        if total_items > 0:
            frappe.publish_realtime("progress", {
                "progress": [current_item + i, total_items],
                "title": "PACE Reminders",
                "description": f"Processing Missing Documents: {app_data.name}"
            }, user=frappe.session.user)

        # Check for missing documents
        missing = []
        doc_fields = {
            "upload_student_photo": "Upload Student Photo",
            "student_signature": "Student Signature",
            "ug_degree_certificate": "UG Degree Certificate / Semester Marksheet",
            "govt_id": "Govt. ID (Passport for Foreign Nationals)"
        }

        for field, label in doc_fields.items():
            if not app_data.get(field):
                missing.append(label)

        if not missing:
            continue

        # Skip if Document Verification status is "Pending" (Overall Status)
        verification_status = frappe.db.get_value("PACE Document Verification", {"application": app_data.name}, "status")
        if verification_status == "Pending":
            continue

        app_doc = frappe.get_doc("PACE Application", app_data.name)

        from slcm.pace.doctype.pace_reminder_email_configuration.pace_reminder_email_configuration import should_send_reminder, is_reminder_enabled

        # Check if reminder should be sent based on interval and status
        if not should_send_reminder("missing_document", app_data.last_reminder_sent, admission_close_date):
            continue
        
        if send_pace_reminder_email(app_doc, missing, admission_close_date):
            send_pace_reminder_system_notification(app_doc, missing, admission_close_date)
            app_doc.db_set("last_reminder_sent", today(), update_modified=False)
            sent_count += 1
    
    return sent_count

def send_pace_reminder_email(doc, missing_documents, admission_close_date):
    """
    Sends the reminder email using 'PACE Document Reminder Email' template.
    """
    template_name = "PACE Document Reminder Email"
    recipient = doc.email_address
    if not recipient:
        return False

    institution_name = "NLSIU"
    try:
        inst_settings = frappe.get_single("Institution Settings")
        institution_name = inst_settings.institution_name or institution_name
    except Exception:
        pass

    args = {
        "doc": doc.as_dict(),
        "first_name": doc.first_name or "",
        "missing_documents": missing_documents,
        "admission_close_date": frappe.utils.formatdate(admission_close_date),
        "admission_portal_url": get_url("/admissions"),
        "institution_name": institution_name
    }

    if not frappe.db.exists("Email Template", template_name):
        return False

    email_template = frappe.get_doc("Email Template", template_name)
    
    try:
        subject = frappe.render_template(email_template.subject or "Missing Documents Reminder", args)
        
        message_body = ""
        if email_template.get("use_html") and email_template.get("response_html"):
            message_body = frappe.render_template(email_template.response_html, args)
        elif email_template.get("response"):
            message_body = frappe.render_template(email_template.response, args)
        
        if not message_body:
            message_body = frappe.render_template(email_template.get("message") or "", args)

        if message_body:
            # CC handling
            cc_list = []
            cc_field_value = email_template.get("cc")
            if cc_field_value:
                cc_list = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]

            frappe.sendmail(
                recipients=[recipient],
                sender=get_template_sender(email_template),
                cc=cc_list,
                subject=subject,
                message=message_body,
                reference_doctype=doc.doctype,
                reference_name=doc.name,
                now=False
            )
            from slcm.pace.doctype.pace_reminder_email_log.pace_reminder_email_log import log_pace_reminder_email
            log_pace_reminder_email(
                recipient=recipient,
                subject=subject,
                reminder_type="Missing Document Reminder",
                sender=get_template_sender(email_template),
                reference_doctype=doc.doctype,
                reference_name=doc.name,
                email_template=template_name
            )
            return True
    except Exception:
        error_msg = traceback.format_exc()
        frappe.log_error(error_msg, f"PACE Reminder Email Failed: {doc.name}")
        from slcm.pace.doctype.pace_reminder_email_log.pace_reminder_email_log import log_pace_reminder_email
        log_pace_reminder_email(
            recipient=recipient,
            subject="Missing Documents Reminder",
            reminder_type="Missing Document Reminder",
            status="Failed",
            reference_doctype=doc.doctype,
            reference_name=doc.name,
            email_template=template_name,
            error_log=error_msg
        )
    
    return False

def send_pace_rejection_email(doc, admission_close_date, rejection_reason=None):
    """
    Sends the rejection email after the deadline.
    """
    template_name = "PACE Application Rejected - Missing Documents"
    recipient = doc.email_address
    if not recipient:
        return False

    institution_name = "NLSIU"
    try:
        inst_settings = frappe.get_single("Institution Settings")
        institution_name = inst_settings.institution_name or institution_name
    except Exception:
        pass

    args = {
        "doc": doc.as_dict(),
        "first_name": doc.first_name or "",
        "admission_close_date": frappe.utils.formatdate(admission_close_date),
        "institution_name": institution_name,
        "rejection_reason": rejection_reason or "Failure to upload mandatory documents before the deadline."
    }

    if not frappe.db.exists("Email Template", template_name):
        return _send_fallback_rejection_email(doc, args)

    email_template = frappe.get_doc("Email Template", template_name)
    
    try:
        subject = frappe.render_template(email_template.subject or "Application Rejected: Missing Documents", args)
        
        message_body = ""
        if email_template.get("use_html") and email_template.get("response_html"):
            message_body = frappe.render_template(email_template.response_html, args)
        elif email_template.get("response"):
            message_body = frappe.render_template(email_template.response, args)
        
        if not message_body:
            message_body = frappe.render_template(email_template.get("message") or "", args)

        if message_body:
            # CC handling
            cc_list = []
            cc_field_value = email_template.get("cc")
            if cc_field_value:
                cc_list = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]

            frappe.sendmail(
                recipients=[recipient],
                sender=get_template_sender(email_template),
                cc=cc_list,
                subject=subject,
                message=message_body,
                reference_doctype=doc.doctype,
                reference_name=doc.name,
                now=True
            )
            
            from slcm.pace.doctype.pace_reminder_email_log.pace_reminder_email_log import log_pace_reminder_email
            log_pace_reminder_email(
                recipient=recipient,
                subject=subject,
                reminder_type="Application Rejection",
                sender=get_template_sender(email_template),
                reference_doctype=doc.doctype,
                reference_name=doc.name,
                email_template=template_name
            )
            return True
    except Exception:
        frappe.log_error(traceback.format_exc(), f"PACE Rejection Email Failed: {doc.name}")
    
    return False

def _send_fallback_rejection_email(doc, args):
    """Fallback if Email Template record is missing."""
    try:
        subject = f"Application Rejected: Missing Documents - {doc.name}"
        message = f"""
            <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2 style="color: #920c24;">Application Rejected</h2>
                <p>Dear {args['first_name']},</p>
                <p>We regret to inform you that your application for the <strong>{doc.programme}</strong> at <strong>{args['institution_name']}</strong> has been rejected.</p>
                <p>This decision was made because the required documents were not uploaded by the admission closing date ({args['admission_close_date']}), despite previous reminders.</p>
                <p>We wish you the best in your future endeavors.</p>
                <p>Warm regards,<br><strong>Office of Admissions</strong><br>{args['institution_name']}</p>
            </div>
        """
        frappe.sendmail(
            recipients=[doc.email_address],
            sender=None,
            subject=subject,
            message=message,
            reference_doctype=doc.doctype,
            reference_name=doc.name,
            now=True
        )

        from slcm.pace.doctype.pace_reminder_email_log.pace_reminder_email_log import log_pace_reminder_email
        log_pace_reminder_email(
            recipient=doc.email_address,
            subject=subject,
            reminder_type="Application Rejection (Fallback)",
            sender=None,
            reference_doctype=doc.doctype,
            reference_name=doc.name,
            email_template=None
        )
        return True
    except Exception:
        frappe.log_error(traceback.format_exc(), f"PACE Rejection Fallback Email Failed: {doc.name}")
    return False

def send_pace_reminder_system_notification(doc, missing_documents, admission_close_date):
    """
    Creates a Notification Log entry for missing documents.
    """
    try:
        recipient = doc.email_address
        if not recipient:
            return

        if frappe.db.exists("User", recipient):
            docs_list = "<ul>" + "".join([f"<li>{d}</li>" for d in missing_documents]) + "</ul>"
            formatted_date = frappe.utils.formatdate(admission_close_date)
            message_body = f"""
                <p>Dear {doc.first_name},</p>
                <p>Your application <strong>{doc.name}</strong> is missing the following documents:</p>
                {docs_list}
                <p><strong>Please ensure you upload them before the admission closing date: {formatted_date}.</strong></p>
                <p><a href="/paceadmissions/progress-tracker?app={doc.name}" style="color: #920c24; font-weight: bold;">Click here to update your application.</a></p>
            """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": "Missing Documents Reminder",
                "for_user": recipient,
                "type": "Alert",
                "email_content": message_body,
                "document_type": doc.doctype,
                "document_name": doc.name,
                "from_user": frappe.session.user or "Administrator",
                "link": f"/paceadmissions/progress-tracker?app={doc.name}"
            }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"PACE Reminder Notification Failed: {doc.name}")

def send_pace_rejection_system_notification(doc, admission_close_date):
    """
    Creates a Notification Log entry for rejection due to missing documents.
    """
    try:
        recipient = doc.email_address
        if not recipient:
            return

        if frappe.db.exists("User", recipient):
            formatted_date = frappe.utils.formatdate(admission_close_date)
            message_body = f"""
                <p>Dear {doc.first_name},</p>
                <p>Your application <strong>{doc.name}</strong> has been rejected because the required documents were not uploaded by the admission closing date ({formatted_date}).</p>
            """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": "Application Rejected: Missing Documents",
                "for_user": recipient,
                "type": "Alert",
                "email_content": message_body,
                "document_type": doc.doctype,
                "document_name": doc.name,
                "from_user": frappe.session.user or "Administrator",
                "link": f"/paceadmissions/progress-tracker?app={doc.name}"
            }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"PACE Rejection Notification Failed: {doc.name}")

def send_correction_reminders(current_item=0, total_items=0):
    """
    Scheduled task to send reminders for documents returned for correction.
    Criteria:
    - Status is "Returned for Correction"
    - Before closing date: Send reminder
    - After closing date: Send rejection and update status
    """
    from frappe.utils import today, date_diff, getdate

    # Get active admission closing date
    from slcm.pace.api import _get_active_pace_admission_name
    pace_admission_name = _get_active_pace_admission_name()
    if not pace_admission_name:
        # If no Active admission, look for the admission record of the current active Academic Year
        active_ay = frappe.db.get_value("Academic Year", {"status": "Active"}, "name")
        if active_ay:
            pace_admission_name = frappe.db.get_value("PACE Admission", {"academic_year": active_ay, "docstatus": ["<", 2]}, "name")
            
    if not pace_admission_name:
        return 0

    admission_close_date = frappe.db.get_value("PACE Admission", pace_admission_name, "admission_close_date")
    if not admission_close_date:
        return 0

    today_date = getdate(today())
    close_date = getdate(admission_close_date)

    # Find applications that are Returned for Correction
    applications = frappe.get_all("PACE Application", filters={
        "status": "Returned for Correction"
    }, fields=["name", "email_address", "first_name", "last_name", "programme"], limit=0)

    sent_count = 0
    total_apps = len(applications)
    
    for i, app_data in enumerate(applications):
        if total_items > 0:
            frappe.publish_realtime("progress", {
                "progress": [current_item + i, total_items],
                "title": "PACE Reminders",
                "description": f"Processing Corrections: {app_data.name}"
            }, user=frappe.session.user)

        # Get the verification record to check last_reminder_sent
        verification_name = frappe.db.get_value("PACE Document Verification", {"application": app_data.name}, "name")
        if not verification_name:
            continue
        
        verification_doc = frappe.get_doc("PACE Document Verification", verification_name)
        if verification_doc.status == "Pending":
            continue
        
        app_doc = frappe.get_doc("PACE Application", app_data.name)

        from slcm.pace.doctype.pace_reminder_email_configuration.pace_reminder_email_configuration import should_send_reminder, is_reminder_enabled

        # Check if reminder should be sent based on interval and status
        if not should_send_reminder("correction", verification_doc.last_reminder_sent, admission_close_date):
            continue
        
        if send_pace_correction_reminder_email(app_doc, verification_doc, admission_close_date):
            send_pace_correction_reminder_system_notification(app_doc, admission_close_date)
            verification_doc.db_set("last_reminder_sent", today(), update_modified=False)
            sent_count += 1
    
    return sent_count

def send_pace_correction_reminder_email(doc, verification_doc, admission_close_date):
    """
    Sends the correction reminder email using 'PACE Document Verification Final Update' template.
    """
    template_name = "PACE Document Verification Final Update"
    recipient = doc.email_address
    if not recipient:
        return False

    institution_name = "NLSIU"
    try:
        inst_settings = frappe.get_single("Institution Settings")
        institution_name = inst_settings.institution_name or institution_name
    except Exception:
        pass

    args = {
        "doc": verification_doc,
        "admission_portal_url": get_url("/admissions"),
        "institution_name": institution_name,
        "admission_close_date": frappe.utils.formatdate(admission_close_date)
    }

    if not frappe.db.exists("Email Template", template_name):
        return False

    email_template = frappe.get_doc("Email Template", template_name)
    
    try:
        subject = frappe.render_template(email_template.subject or "Document Correction Required", args)
        
        message_body = ""
        if email_template.get("use_html") and email_template.get("response_html"):
            message_body = frappe.render_template(email_template.response_html, args)
        elif email_template.get("response"):
            message_body = frappe.render_template(email_template.response, args)
        
        if not message_body:
            message_body = frappe.render_template(email_template.get("message") or "", args)

        if message_body:
            frappe.sendmail(
                recipients=[recipient],
                sender=get_template_sender(email_template),
                subject=subject,
                message=message_body,
                reference_doctype="PACE Document Verification",
                reference_name=verification_doc.name,
                now=False
            )
            from slcm.pace.doctype.pace_reminder_email_log.pace_reminder_email_log import log_pace_reminder_email
            log_pace_reminder_email(
                recipient=recipient,
                subject=subject,
                reminder_type="Correction Reminder",
                sender=get_template_sender(email_template),
                reference_doctype="PACE Document Verification",
                reference_name=verification_doc.name,
                email_template=template_name
            )
            return True
    except Exception:
        error_msg = traceback.format_exc()
        frappe.log_error(error_msg, f"PACE Correction Reminder Email Failed: {doc.name}")
        from slcm.pace.doctype.pace_reminder_email_log.pace_reminder_email_log import log_pace_reminder_email
        log_pace_reminder_email(
            recipient=recipient,
            subject="Document Correction Required",
            reminder_type="Correction Reminder",
            status="Failed",
            reference_doctype="PACE Document Verification",
            reference_name=verification_doc.name,
            email_template=template_name,
            error_log=error_msg
        )
    
    return False

def send_pace_correction_reminder_system_notification(doc, admission_close_date):
    """
    Creates a Notification Log entry for document correction.
    """
    try:
        recipient = doc.email_address
        if not recipient:
            return

        if frappe.db.exists("User", recipient):
            formatted_date = frappe.utils.formatdate(admission_close_date)
            message_body = f"""
                <p>Dear {doc.first_name},</p>
                <p>Your application <strong>{doc.name}</strong> still has documents that require correction.</p>
                <p><strong>Please ensure you re-upload them before the admission closing date: {formatted_date}.</strong></p>
                <p><a href="/paceadmissions/progress-tracker?app={doc.name}" style="color: #920c24; font-weight: bold;">Click here to update your application.</a></p>
            """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": "Document Correction Reminder",
                "for_user": recipient,
                "type": "Alert",
                "email_content": message_body,
                "document_type": doc.doctype,
                "document_name": doc.name,
                "from_user": frappe.session.user or "Administrator",
                "link": f"/paceadmissions/progress-tracker?app={doc.name}"
            }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"PACE Correction Reminder Notification Failed: {doc.name}")

def send_payment_reminders(current_item=0, total_items=0):
    """
    Scheduled task (daily at 10:00 AM) to send reminders for pending payments.
    Criteria:
    - Status is "Submitted"
    - Before closing date: Send reminder
    """
    from frappe.utils import today, getdate, now_datetime

    # Get active admission closing date
    from slcm.pace.api import _get_active_pace_admission_name
    pace_admission_name = _get_active_pace_admission_name()
    if not pace_admission_name:
        # If no Active admission, look for the admission record of the current active Academic Year
        active_ay = frappe.db.get_value("Academic Year", {"status": "Active"}, "name")
        if active_ay:
            pace_admission_name = frappe.db.get_value("PACE Admission", {"academic_year": active_ay, "docstatus": ["<", 2]}, "name")
            
    if not pace_admission_name:
        return 0

    admission_close_date = frappe.db.get_value("PACE Admission", pace_admission_name, "admission_close_date")
    if not admission_close_date:
        return 0

    today_date = getdate(today())
    close_date = getdate(admission_close_date)

    # Find applications that are Submitted
    applications = frappe.get_all("PACE Application", filters={
        "status": "Submitted"
    }, fields=["name", "email_address", "first_name", "last_name", "programme", "application_remainder_sent_on"], limit=0)

    sent_count = 0
    
    for i, app_data in enumerate(applications):
        if total_items > 0:
            frappe.publish_realtime("progress", {
                "progress": [current_item + i, total_items],
                "title": "PACE Reminders",
                "description": f"Processing Payment Reminders: {app_data.name}"
            }, user=frappe.session.user)

        app_doc = frappe.get_doc("PACE Application", app_data.name)

        from slcm.pace.doctype.pace_reminder_email_configuration.pace_reminder_email_configuration import should_send_reminder, is_reminder_enabled

        # Skip if Document Verification status is "Pending" (Overall Status)
        verification_status = frappe.db.get_value("PACE Document Verification", {"application": app_data.name}, "status")
        if verification_status == "Pending":
            continue



        # Check if reminder should be sent based on interval and status
        if not should_send_reminder("payment", app_data.application_remainder_sent_on, admission_close_date):
            continue

        if send_pace_payment_reminder_email(app_doc, admission_close_date):
            send_pace_payment_reminder_system_notification(app_doc, admission_close_date)
            app_doc.db_set("application_remainder_sent_on", now_datetime(), update_modified=False)
            sent_count += 1

    return sent_count

def send_pace_payment_reminder_email(doc, admission_close_date):
    """
    Sends the payment reminder email using 'Pace Application Completed but Payment Pending' template.
    """
    template_name = "Pace Application Completed but Payment Pending"
    recipient = doc.email_address
    if not recipient:
        return False

    institution_name = "NLSIU"
    try:
        inst_settings = frappe.get_single("Institution Settings")
        institution_name = inst_settings.institution_name or institution_name
    except Exception:
        pass

    args = {
        "doc": doc.as_dict(),
        "first_name": doc.first_name or "",
        "admission_close_date": frappe.utils.formatdate(admission_close_date),
        "admission_portal_url": get_url("/admissions"),
        "institution_name": institution_name
    }

    if not frappe.db.exists("Email Template", template_name):
        return False

    email_template = frappe.get_doc("Email Template", template_name)
    
    try:
        subject = frappe.render_template(email_template.subject or "Payment Pending for Your PACE Application", args)
        
        message_body = ""
        if email_template.get("use_html") and email_template.get("response_html"):
            message_body = frappe.render_template(email_template.response_html, args)
        elif email_template.get("response"):
            message_body = frappe.render_template(email_template.response, args)
        
        if not message_body:
            message_body = frappe.render_template(email_template.get("message") or "", args)

        if message_body:
            # CC handling
            cc_list = []
            cc_field_value = email_template.get("cc")
            if cc_field_value:
                cc_list = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]

            frappe.sendmail(
                recipients=[recipient],
                sender=get_template_sender(email_template),
                cc=cc_list,
                subject=subject,
                message=message_body,
                reference_doctype=doc.doctype,
                reference_name=doc.name,
                now=False
            )
            from slcm.pace.doctype.pace_reminder_email_log.pace_reminder_email_log import log_pace_reminder_email
            log_pace_reminder_email(
                recipient=recipient,
                subject=subject,
                reminder_type="Payment Reminder",
                sender=get_template_sender(email_template),
                reference_doctype=doc.doctype,
                reference_name=doc.name,
                email_template=template_name
            )
            return True
    except Exception:
        error_msg = traceback.format_exc()
        frappe.log_error(error_msg, f"PACE Payment Reminder Email Failed: {doc.name}")
        from slcm.pace.doctype.pace_reminder_email_log.pace_reminder_email_log import log_pace_reminder_email
        log_pace_reminder_email(
            recipient=recipient,
            subject="Payment Pending for Your PACE Application",
            reminder_type="Payment Reminder",
            status="Failed",
            reference_doctype=doc.doctype,
            reference_name=doc.name,
            email_template=template_name,
            error_log=error_msg
        )
    
    return False

def send_pace_payment_reminder_system_notification(doc, admission_close_date):
    """
    Creates a Notification Log entry for payment pending.
    """
    try:
        recipient = doc.email_address
        if not recipient:
            return

        if frappe.db.exists("User", recipient):
            formatted_date = frappe.utils.formatdate(admission_close_date)
            message_body = f"""
                <p>Dear {doc.first_name},</p>
                <p>Your application <strong>{doc.name}</strong> has been successfully submitted, but the application fee is yet to be received.</p>
                <p>Please complete the payment before the deadline: <strong>{formatted_date}</strong> to avoid any delays.</p>
                <p><a href="/paceadmissions/progress-tracker?app={doc.name}" style="color: #920c24; font-weight: bold;">Click here to PAY NOW.</a></p>
            """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": "Payment Pending for Your PACE Application",
                "for_user": recipient,
                "type": "Alert",
                "email_content": message_body,
                "document_type": doc.doctype,
                "document_name": doc.name,
                "from_user": frappe.session.user or "Administrator",
                "link": f"/paceadmissions/progress-tracker?app={doc.name}"
            }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"PACE Payment Reminder Notification Failed: {doc.name}")

def send_daily_pace_application_reminders(current_item=0, total_items=0):
    """
    Scheduled task (daily) to send reminders to PACE Applicants.
    Case 1: Registered but no application.
    Case 2: Application in Draft.
    """
    from frappe.utils import today, getdate, formatdate
    from slcm.pace.api.service.pace_payment import _get_active_pace_admission_name
    
    admission_name = _get_active_pace_admission_name()
    if not admission_name:
        # If no Active admission, look for the admission record of the current active Academic Year
        # This allows rejection logic to run after the admission is Closed.
        active_ay = frappe.db.get_value("Academic Year", {"status": "Active"}, "name")
        if active_ay:
            admission_name = frappe.db.get_value("PACE Admission", {"academic_year": active_ay, "docstatus": ["<", 2]}, "name")
    
    if not admission_name:
        return 0

    admission_doc = frappe.get_doc("PACE Admission", admission_name)
    if not admission_doc.admission_close_date:
        return 0

    today_date = getdate(today())
    admission_close_date = admission_doc.admission_close_date
    close_date = getdate(admission_close_date)

    formatted_close_date = formatdate(admission_close_date)

    # Get all users with role "PACE Applicant"
    users = frappe.get_all("Has Role", filters={"role": "PACE Applicant"}, fields=["parent"], limit=0)
    user_emails = list(set([u.parent for u in users]))
    
    if not user_emails:
        return 0

    sent_count = 0
    for i, email in enumerate(user_emails):
        if total_items > 0:
            frappe.publish_realtime("progress", {
                "progress": [current_item + i, total_items],
                "title": "PACE Reminders",
                "description": f"Processing Daily Application Reminders: {email}"
            }, user=frappe.session.user)

        try:
            # Skip if email is actually a role or invalid user
            if not email or not frappe.db.exists("User", email):
                continue
                
            # Check for PACE Application
            applications = frappe.get_all("PACE Application", 
                filters={"email_address": email}, 
                fields=["name", "status"],
                limit=0
            )
            
            user_doc = frappe.get_doc("User", email)
            if not user_doc.enabled:
                continue

            if not applications:
                # Case 1: Registered but not started
                if today_date > close_date:
                    continue

                # Ensure we only send reminders for the admission cycle the user registered in
                # by checking if they've received a reminder for a DIFFERENT cycle in the past.
                previous_logs = frappe.get_all(
                    "PACE Reminder Email Log",
                    filters={
                        "reference_doctype": "User",
                        "reference_name": email,
                    },
                    fields=["pace_admission"],
                    limit=0
                )
                belong_to_other_cycle = False
                for log in previous_logs:
                    if log.pace_admission and log.pace_admission != admission_name:
                        belong_to_other_cycle = True
                        break
                if belong_to_other_cycle:
                    continue

                from slcm.pace.doctype.pace_reminder_email_configuration.pace_reminder_email_configuration import should_send_reminder
                if not should_send_reminder("application", user_doc.get("last_pace_reminder_sent"), admission_close_date):
                    continue
                
                send_pace_application_reminder_email(user_doc, formatted_close_date, admission_name)
                user_doc.db_set("last_pace_reminder_sent", today_date, update_modified=False)
                sent_count += 1
            else:
                # Case 2: Check for Draft status
                # Skip users whose applications are submitted/completed
                # We skip the user if they have already successfully submitted or completed at least one application.
                submitted_statuses = [
                    'Fee Paid', 'Provisionally Submitted', 'Enrolled', 'Verified', 
                    'Under Verification', 'Submitted', 'Admitted', 'Completed', 'Converted'
                ]
                
                has_submitted = any(app.status in submitted_statuses for app in applications)
                if has_submitted:
                    # User has at least one in-progress or successful application
                    continue
                
                draft_apps = [app for app in applications if app.status == "Draft"]
                for app in draft_apps:
                    # Skip if Document Verification status is "Pending" (Overall Status)
                    verification_status = frappe.db.get_value("PACE Document Verification", {"application": app.name}, "status")
                    if verification_status == "Pending":
                        continue
                    
                    app_doc = frappe.get_doc("PACE Application", app.name)
                    
                    from slcm.pace.doctype.pace_reminder_email_configuration.pace_reminder_email_configuration import should_send_reminder, is_reminder_enabled



                    # Send reminder if enabled by interval and status
                    if not should_send_reminder("draft", app_doc.draft_application_email_sent_on, admission_close_date):
                        continue
                        
                    send_pace_draft_reminder_email(app_doc, user_doc, formatted_close_date)
                    app_doc.db_set("draft_application_email_sent_on", frappe.utils.now_datetime(), update_modified=False)
                    sent_count += 1
        except Exception:
            frappe.log_error(message=frappe.get_traceback(), title=f"PACE Daily Reminder Failed for {email}")
    
    return sent_count

def send_pace_application_reminder_email(user_doc, admission_close_date, pace_admission_name=None):
    """Sends Case 1 reminder email using Email Template doctype."""
    from frappe.email.doctype.email_template.email_template import get_email_template
    
    template_name = "PACE Application Reminder"
    args = {
        "first_name": user_doc.first_name or user_doc.full_name,
        "admission_close_date": admission_close_date
    }
    
    template = get_email_template(template_name, args)
    
    # CC handling
    cc_list = []
    cc_field_value = frappe.db.get_value("Email Template", template_name, "cc")
    if cc_field_value:
        cc_list = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]

    frappe.sendmail(
        recipients=[user_doc.email],
        sender=get_template_sender(template_name),
        cc=cc_list,
        subject=template.get("subject") or _("PACE Application Reminder"),
        message=template.get("message"),
        now=True
    )
    
    # Send System Notification
    try:
        send_pace_application_reminder_system_notification(user_doc, admission_close_date)
    except Exception:
        frappe.log_error(traceback.format_exc(), f"PACE Application Reminder System Notification Failed: {user_doc.name}")

    from slcm.pace.doctype.pace_reminder_email_log.pace_reminder_email_log import log_pace_reminder_email
    log_pace_reminder_email(
        recipient=user_doc.email,
        subject=template.get("subject") or _("PACE Application Reminder"),
        reminder_type="Application Reminder",
        sender=get_template_sender(template_name),
        reference_doctype="User",
        reference_name=user_doc.name,
        email_template=template_name,
        pace_admission=pace_admission_name
    )

def send_pace_application_reminder_system_notification(user_doc, admission_close_date):
    """
    Creates a Notification Log entry for application reminder.
    """
    try:
        if frappe.db.exists("User", user_doc.name):
            message_body = f"""
                <p>Dear {user_doc.first_name or user_doc.full_name},</p>
                <p>You have registered on our Admissions Portal but have not yet started your PACE application.</p>
                <p>The deadline for submission is <strong>{admission_close_date}</strong>. We encourage you to start your application soon.</p>
                <p><a href="http://pace.nls.ac.in" style="color: #920c24; font-weight: bold;">Click here to START your application.</a></p>
            """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": "PACE Application Reminder",
                "for_user": user_doc.name,
                "type": "Alert",
                "email_content": message_body,
                "from_user": frappe.session.user or "Administrator",
                "link": "http://pace.nls.ac.in"
            }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"PACE Application Reminder Notification Failed: {user_doc.name}")

def send_pace_draft_reminder_email(app_doc, user_doc, admission_close_date):
    """Sends Case 2 reminder email using Email Template doctype."""
    from frappe.email.doctype.email_template.email_template import get_email_template
    
    template_name = "PACE Draft Application Reminder"
    # The template uses {{ doc.application }} as per requirements
    app_doc.application = app_doc.name
    
    args = {
        "doc": app_doc,
        "first_name": user_doc.first_name or user_doc.full_name,
        "admission_close_date": admission_close_date
    }
    
    template = get_email_template(template_name, args)
    
    # CC handling
    cc_list = []
    cc_field_value = frappe.db.get_value("Email Template", template_name, "cc")
    if cc_field_value:
        cc_list = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]

    frappe.sendmail(
        recipients=[user_doc.email],
        sender=get_template_sender(template_name),
        cc=cc_list,
        subject=template.get("subject") or _("PACE Draft Application Reminder"),
        message=template.get("message"),
        now=True
    )
    
    # Send System Notification
    try:
        send_pace_draft_reminder_system_notification(app_doc, admission_close_date)
    except Exception:
        frappe.log_error(traceback.format_exc(), f"PACE Draft Reminder System Notification Failed: {app_doc.name}")

    from slcm.pace.doctype.pace_reminder_email_log.pace_reminder_email_log import log_pace_reminder_email
    log_pace_reminder_email(
        recipient=user_doc.email,
        subject=template.get("subject") or _("PACE Draft Application Reminder"),
        reminder_type="Draft Reminder",
        sender=get_template_sender(template_name),
        reference_doctype="PACE Application",
        reference_name=app_doc.name,
        email_template=template_name
    )

def send_pace_draft_reminder_system_notification(app_doc, admission_close_date):
    """
    Creates a Notification Log entry for draft application reminder.
    """
    try:
        recipient = app_doc.email_address
        if not recipient:
            return

        if frappe.db.exists("User", recipient):
            message_body = f"""
                <p>Dear {app_doc.first_name},</p>
                <p>Your PACE application <strong>{app_doc.name}</strong> is still in Draft status.</p>
                <p>Please complete and submit your application before the deadline: <strong>{admission_close_date}</strong>.</p>
                <p><a href="/admissions" style="color: #920c24; font-weight: bold;">Click here to COMPLETE your application.</a></p>
            """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": "PACE Draft Application Reminder",
                "for_user": recipient,
                "type": "Alert",
                "email_content": message_body,
                "document_type": app_doc.doctype,
                "document_name": app_doc.name,
                "from_user": frappe.session.user or "Administrator",
                "link": "/admissions"
            }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"PACE Draft Reminder Notification Failed: {app_doc.name}")

@frappe.whitelist()
def withdraw_application(application_name, reason):
	"""
	Whitelisted method to withdraw an enrolled PACE Application and the corresponding Student Master.
	Only accessible to System Manager, PACE Admission Manager, and Admission Admin.
	"""
	if not application_name or not reason:
		frappe.throw(_("Application Name and Reason are required."))

	# Check roles/permission
	user_roles = frappe.get_roles()
	allowed_roles = {"System Manager", "PACE Admission Manager", "Admission Admin"}
	if not allowed_roles.intersection(user_roles):
		frappe.throw(_("You are not authorized to perform this action."), frappe.PermissionError)

	# Fetch application
	app_doc = frappe.get_doc("PACE Application", application_name)
	if app_doc.status == "Withdrawn":
		frappe.throw(_("Application is already withdrawn."))

	# Update PACE Application status and failure message
	app_doc.db_set("status", "Withdrawn")
	app_doc.db_set("failure_message_box", reason)
	app_doc.add_comment("Info", _("Application withdrawn. Reason: {0}").format(reason))

	# Update Student Master status if exists
	student_name = frappe.db.get_value("Student Master", {"application_number": application_name}, "name")
	if student_name:
		from slcm.admission.utils.withdrawal_sync import sync_student_records_for_withdrawn_application
		sync_student_records_for_withdrawn_application(application_name, status_remark=reason)

	return {
		"status": "success",
		"message": _("Application and student record withdrawn successfully.")
	}


@frappe.whitelist()
def fix_orphaned_pace_files():
	"""
	One-time utility: Re-links any private file uploaded against a PACE Application
	whose attached_to_doctype / attached_to_name / attached_to_field got lost during
	the handle_file_name rename process.

	Accessible via: bench --site <site> execute
	  slcm.pace.doctype.pace_application.pace_application.fix_orphaned_pace_files
	"""
	if not ("System Manager" in frappe.get_roles() or "Administrator" in frappe.get_roles()):
		frappe.throw(_("Only System Managers can run this utility."), frappe.PermissionError)

	ATTACH_FIELDS = [
		"upload_student_photo",
		"student_signature",
		"ug_degree_certificate",
		"govt_id",
	]

	apps = frappe.get_all("PACE Application", pluck="name")
	fixed = 0
	errors = 0

	for app_name in apps:
		try:
			doc_vals = frappe.db.get_value(
				"PACE Application", app_name, ATTACH_FIELDS, as_dict=True
			)
			if not doc_vals:
				continue

			for fieldname in ATTACH_FIELDS:
				file_url = doc_vals.get(fieldname)
				if not file_url:
					continue

				file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
				if not file_name:
					continue

				fd = frappe.db.get_value(
					"File", file_name,
					["attached_to_doctype", "attached_to_name", "attached_to_field", "is_private"],
					as_dict=True,
				)
				if not fd:
					continue

				needs_update = (
					fd.attached_to_doctype != "PACE Application"
					or fd.attached_to_name != app_name
					or fd.attached_to_field != fieldname
					or not fd.is_private
				)

				if needs_update:
					frappe.db.set_value("File", file_name, {
						"attached_to_doctype": "PACE Application",
						"attached_to_name": app_name,
						"attached_to_field": fieldname,
						"is_private": 1,
					})
					frappe.logger().info(
						f"fix_orphaned_pace_files: Fixed {file_name} → {app_name}.{fieldname}"
					)
					fixed += 1
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"fix_orphaned_pace_files: error processing {app_name}"
			)
			errors += 1

	frappe.db.commit()
	result = f"Done. Fixed {fixed} orphaned file(s). Errors: {errors}."
	frappe.logger().info(result)
	return result

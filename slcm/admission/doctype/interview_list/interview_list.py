# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
import json
import re
import traceback
from frappe.model.document import Document
from frappe.utils import now, get_url, format_date, format_time


class InterviewList(Document):

    def autoname(self):
        """
        Custom naming: IVL-{academic_year}-###
        Gap-filling strategy — reuses deleted numbers.
        """
        if self.academic_year:
            prefix = f"IVL-{self.academic_year}-"

            rows = frappe.db.sql(
                "SELECT name FROM `tabInterview List` WHERE name LIKE %s",
                prefix + "%",
                as_list=True,
            )

            used = set()
            pattern = re.compile(re.escape(prefix) + r"(\d{1,})$")
            for r in rows:
                m = pattern.match(r[0])
                if m:
                    try:
                        used.add(int(m.group(1)))
                    except ValueError:
                        pass

            idx = 1
            while idx in used:
                idx += 1

            self.name = f"{prefix}{idx:03d}"
        else:
            self.name = frappe.generate_hash(self.doctype, 6)

    @frappe.whitelist()
    def allocate_interview_slots(self, staff_member, selected_applicants, interview_date=None, interview_time=None):
        """
        Logic:
          - Creates ONE Interview Seat Allocation record per selected applicant.
          - Assigns the chosen staff member.
          - Marks child row as 'Scheduled'.
          - Sends email notification to each applicant.
        """
        if isinstance(selected_applicants, str):
            selected_applicants = json.loads(selected_applicants)

        if not staff_member:
            frappe.throw("Please select an Interview Staff Member.")
        if not selected_applicants:
            frappe.throw("No applicants selected.")

        staff = frappe.get_doc("Interview Staff Member", staff_member)
        if not staff.is_active:
            frappe.throw(f"Staff member '{staff.staff_name}' is not active.")

        if interview_date and interview_time:
            # Prevent double-booking panel members
            overlap = frappe.db.sql("""
                SELECT name FROM `tabInterview Seat Allocation`
                WHERE interview_staff_member = %s
                  AND interview_date = %s
                  AND interview_time = %s
                  AND interview_status = 'Scheduled'
            """, (staff_member, interview_date, interview_time))
            if overlap:
                frappe.throw(f"Staff member {staff.staff_name} is already booked for an interview on {interview_date} at {interview_time}.")

        applicant_map = {row.name: row for row in self.interview_applicant}

        created_count = 0
        total_applicants = len(selected_applicants)

        for i, row_name in enumerate(selected_applicants):
            # Publish progress to the UI
            frappe.publish_progress(
                float(i + 1) / total_applicants * 100, 
                title=_("Generating Interview Slots..."),

                description=f"Processing {i + 1} of {total_applicants}"
            )

            row = applicant_map.get(row_name)
            if not row:
                continue

            if getattr(row, "interview_status", "") == "Scheduled":
                continue

            # Verify Program has Interview enabled in its Stages
            if row.program:
                is_intl = False
                if row.applicant_id:
                    is_intl = frappe.db.get_value("Applicant", row.applicant_id, "foriegn_national") == "Yes"
                
                check_field = "international_interview" if is_intl else "intereview"
                program_intereview = frappe.db.get_value("Programme", row.program, check_field)
                if not program_intereview:
                    frappe.throw(_("Program {0} does not have Interview enabled in its Stages.").format(row.program))

            existing = frappe.db.get_value("Interview Seat Allocation", {
                "interview_list": self.name,
                "applicant":      row.applicant_id
            }, "name")

            if existing:
                allocation = frappe.get_doc("Interview Seat Allocation", existing)
            else:
                allocation = frappe.new_doc("Interview Seat Allocation")
                allocation.interview_list      = self.name
                allocation.academic_year       = self.academic_year
                allocation.admission_cycle     = self.admission_cycle
                allocation.campus              = self.campus
                allocation.program_level       = self.program_level

                allocation.applicant           = row.applicant_id
                allocation.candidate_name      = row.candidate_name
                allocation.program             = row.program
                allocation.email               = row.email
                allocation.gender              = row.gender
                allocation.entrance_test         = row.entrance_test
                allocation.intereview            = row.intereview
                allocation.is_international_applicant = row.is_international_applicant or (1 if frappe.db.get_value("Applicant", row.applicant_id, "foriegn_national") == "Yes" else 0)

                # FETCH CATEGORIES CORRECTLY
                if allocation.applicant:
                    try:
                        from slcm.admission.doctype.applicant.applicant import Applicant
                        app_doc = frappe.get_doc("Applicant", allocation.applicant)
                        app_categories = app_doc._get_applicant_categories()
                        allocation.set("category", [])
                        for cat in app_categories:
                            allocation.append("category", {"category": cat})
                    except Exception:
                        pass

                allocation.source_type         = row.source_type

            allocation.interview_staff_member = staff_member
            allocation.staff_name             = staff.staff_name
            allocation.staff_email            = staff.email
            allocation.staff_contact          = staff.contact_number
            allocation.interview_slot_status  = "Slot Assigned"
            allocation.slot_assigned_by       = frappe.session.user
            allocation.interview_status       = "Scheduled"

            if interview_date:
                allocation.interview_date = interview_date
            if interview_time:
                allocation.interview_time = interview_time

            allocation.save(ignore_permissions=True)

            row.interview_status = "Scheduled"
            created_count += 1

            # Direct SQL status update for Applicant
            if row.applicant_id:
                frappe.db.sql("""
                    UPDATE `tabApplicant` 
                    SET status = 'Interview Scheduled', modified = %(now)s 
                    WHERE name = %(name)s
                """, {"now": now(), "name": row.applicant_id})
                
                frappe.clear_document_cache("Applicant", row.applicant_id)
                
                frappe.publish_realtime(
                    "applicant_status_updated",
                    {"docname": row.applicant_id, "status": "Interview Scheduled"},
                )

                email = row.email or frappe.db.get_value("Applicant", row.applicant_id, "email")
                if email:
                    try:
                        _send_interview_slot_email(allocation, email)
                        _send_interview_slot_notification(allocation, email)
                    except Exception:
                        frappe.log_error(message=traceback.format_exc(), title=f"Interview Slot Email/Notification Failed: {allocation.name}")
            
            # Commit periodically to update progress
            if i % 5 == 0:
                frappe.db.commit()

        # Send combined email to the interviewer
        if created_count > 0:
            try:
                _send_interviewer_allocation_email(staff_member, self.name, interview_date, interview_time)
                _send_interviewer_allocation_notification(staff_member, self.name, interview_date, interview_time, created_count)
            except Exception:
                frappe.log_error(message=traceback.format_exc(), title=f"Interviewer Allocation Email/Notification Failed: {self.name}")

        self.save(ignore_permissions=True)
        frappe.db.commit()
        return created_count


def _send_interviewer_allocation_email(staff_member, interview_list_name, interview_date, interview_time):
    """Send a combined email to the interviewer with the list of assigned students."""
    try:
        template_name = "Interviewer Allocation"
        if not frappe.db.exists("Email Template", template_name):
            return

        staff = frappe.get_doc("Interview Staff Member", staff_member)
        if not staff.email:
            return

        # Fetch all students assigned to this staff for this list and schedule
        filters = {
            "interview_list": interview_list_name,
            "interview_staff_member": staff_member,
            "interview_date": interview_date,
            "interview_time": interview_time,
            "interview_status": "Scheduled"
        }
        
        allocations = frappe.get_all("Interview Seat Allocation", 
            filters=filters,
            fields=["applicant", "candidate_name", "program"]
        )

        if not allocations:
            return

        template = frappe.get_doc("Email Template", template_name)
        
        args = {
            "staff_name": staff.staff_name,
            "interview_date": interview_date,
            "interview_time": interview_time,
            "interview_address": staff.interview_address,
            "students": allocations,
            "is_rescheduled": False
        }

        subject = frappe.render_template(template.subject, args)
        message_body = frappe.render_template(template.response_html if template.use_html else template.response, args)

        sender = None
        if template.get("email_account"):
            sender = frappe.db.get_value("Email Account", template.get("email_account"), "email_id") or template.get("email_account")

        cc_list = []
        if template.get("cc"):
            cc_field_value = template.get("cc")
            cc_list = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]

        frappe.sendmail(
            recipients=[staff.email],
            sender=sender,
            cc=cc_list if cc_list else None,
            subject=subject,
            message=message_body,
            now=False
        )
    except Exception:
        frappe.log_error(message=traceback.format_exc(), title="Interviewer Allocation Email Function Failed")


def _send_interviewer_allocation_notification(staff_member, interview_list_name, interview_date, interview_time, count):
    """Creates a Notification Log entry for the interviewer."""
    try:
        staff = frappe.get_doc("Interview Staff Member", staff_member)
        if not staff.email:
            return
            
        if frappe.db.exists("User", staff.email):
            # Custom message for Interviewer
            message_body = f"""
                <p>You have been assigned <strong>{count}</strong> students for an interview session.</p>
                <p>Interview List: <strong>"{interview_list_name}"</strong></p>
                <p>Date: <strong>{format_date(interview_date) or "—"}</strong></p>
                <p>Time: <strong>{format_time(interview_time) or "—"}</strong></p>
                <p>Venue: <strong>{staff.interview_address or "—"}</strong></p>
                <p>Please check your email for the detailed list of students.</p>
            """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": f"New Interview Assignment: {count} Students",
                "for_user": staff.email,
                "type": "Alert",
                "email_content": message_body,
                "document_type": "Interview List",
                "document_name": interview_list_name,
                "from_user": frappe.session.user
            }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(message=frappe.get_traceback(), title=f"Interviewer Allocation Notification Failed: {interview_list_name}")


def _send_interview_slot_email(allocation, email):
    """Send an interview slot assignment notification using a configurable template."""
    try:
        template_name = "Interview Allocation"
        if not frappe.db.exists("Email Template", template_name):
            frappe.log_error(f"Email Template '{template_name}' not found.", "Email Sending Error")
            return

        template = frappe.get_doc("Email Template", template_name)
        
        doc_dict = allocation.as_dict()
        args = {
            "doc": doc_dict,
            "portal_url": get_url("/nlsat/merit-and-scholarship/admission_dashboard?panel=applications")
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
                    reference_doctype="Interview Seat Allocation",
                    reference_name=allocation.name,
                    now=False
                )
                frappe.logger().info(f"Interview Allocation Email queued successfully to {email} for {allocation.name}")
            except Exception:
                frappe.log_error(traceback.format_exc(), f"Interview Allocation Email Queueing Failed: {allocation.name}")
    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"Interview Slot Email Failed: {allocation.name}")


def _send_interview_slot_notification(allocation, email):
    """Creates a Notification Log entry for the interview slot."""
    if not email:
        return
    
    if frappe.db.exists("User", email):
        try:
            # Custom message for Interview
            message_body = f"""
                <p>An interview slot has been scheduled for you in <strong>"{allocation.interview_list}"</strong>.</p>
                <p>Date: <strong>{format_date(allocation.interview_date) or "—"}</strong></p>
                <p>Time: <strong>{format_time(allocation.interview_time) or "—"}</strong></p>
                <p>Staff: <strong>{allocation.staff_name or "—"}</strong></p>
                <p><a href="/nlsat/merit-and-scholarship/admission_dashboard?panel=applications" style="color: #16a34a; font-weight: bold;">Click here to view details.</a></p>
            """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": "Interview Slot Scheduled",
                "for_user": email,
                "type": "Alert",
                "email_content": message_body,
                "document_type": "Interview Seat Allocation",
                "document_name": allocation.name,
                "from_user": frappe.session.user,
                "link": "/nlsat/merit-and-scholarship/admission_dashboard?panel=applications"
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(message=frappe.get_traceback(), title=f"Interview Slot Notification Failed: {allocation.name}")

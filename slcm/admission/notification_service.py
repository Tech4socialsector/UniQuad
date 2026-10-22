import frappe
from frappe.utils import now, get_url, fmt_money, flt, nowdate

try:
    from slcm.admission.utils.notifications import log_communication
except ImportError:
    log_communication = None

try:
    from slcm.admission.doctype.admission_audit_log.audit_service import log_admission_action
except ImportError:
    log_admission_action = None


def _robust_sendmail(recipients, subject, message, reference_doctype=None, reference_name=None, cc=None, template=None):
    """
    Standard asynchronous email sending helper. 
    Uses the background Email Queue (now=False) for reliability and performance.
    """
    sender = None
    if template:
        # Honor custom Email Account if specified in the template
        template_email_account = template.get("email_account")
        if template_email_account:
            sender = frappe.db.get_value("Email Account", template_email_account, "email_id") or template_email_account

        if not cc:
            # Extract CC from template if available
            cc_field_value = template.get("cc")
            if cc_field_value:
                cc = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]

    try:
        # Use now=False for standard asynchronous delivery via Email Queue.
        frappe.sendmail(
            recipients=recipients,
            subject=subject,
            message=message,
            sender=sender,
            cc=cc,
            reference_doctype=reference_doctype,
            reference_name=reference_name,
            now=False
        )
    except Exception:
        import traceback
        frappe.log_error(traceback.format_exc(), f"Email Queueing Failed: {reference_name or recipients}")


def notify_status_change(applicant, program, old_status, new_status, allocation_name, admission_cycle=None, row=None):
    """
    Sends an email notification to the applicant about a status change
    using the 'Seat Allocation Result Notification' template record and logs it.
    Only sends notifications for the core 'Selected', 'Waitlisted', and 'Rejected' statuses.
    Lifecycle statuses like 'Offer Issued' or 'Fee Paid' are skipped here.
    """
    # 1. Define allowed statuses for notification
    allowed_statuses = ["Selected", "Waitlisted", "Rejected"]

    if new_status not in allowed_statuses:
        frappe.logger().info(f"Notification skipped: Status '{new_status}' is not in allowed list (Selected, Waitlisted, Rejected) for {applicant}")
        return

    try:
        etsa_doc = frappe.get_doc("Entrance Test Seat Allocation", applicant)
        # Create a compatible applicant_doc mimicking Eligibility Result
        applicant_doc = frappe._dict(etsa_doc.as_dict())
        applicant_doc.applicant_id = etsa_doc.applicant
    except frappe.DoesNotExistError:
        frappe.logger().error(f"Notification error: Entrance Test Seat Allocation '{applicant}' not found.")
        return

    # Resolve email: Try Eligibility Result first, then fallback to Applicant
    email = getattr(applicant_doc, "email", None) or getattr(applicant_doc, "email_id", None)
    
    if not email and applicant_doc.applicant_id:
        email = frappe.db.get_value("Applicant", applicant_doc.applicant_id, "email")
        if email:
            frappe.logger().info(f"Notification: Using fallback email from Applicant {applicant_doc.applicant_id} for {applicant}")

    if not email:
        frappe.logger().warning(f"Notification skipped: No email found for applicant {applicant} (ID: {applicant_doc.applicant_id})")
        return

    # Fetch and render the Email Template record
    template_name = "Seat Allocation Result Notification"
    if not frappe.db.exists("Email Template", template_name):
        # Fallback to older name if some reason this one isn't there
        template_name = "Seat Allocation Status"
        if not frappe.db.exists("Email Template", template_name):
            frappe.logger().error(f"Notification error: Email Template '{template_name}' not found.")
            return

    template = frappe.get_doc("Email Template", template_name)
    
    # Determine the content field correctly based on 'use_html' toggle
    if template.get("use_html"):
        template_body = template.response_html
    else:
        template_body = template.response
        
    if not template_body:
        template_body = template.get("message")
        
    if not template_body:
        frappe.logger().error(f"Notification error: Email Template '{template_name}' has no content.")
        return

    # Construct combined context for the template (it expects 'doc')
    doc_context = dict(applicant_doc)
    if row:
        row_dict = row.as_dict()
        # Ensure child table values take precedence (selection status, etc.)
        doc_context.update({k: v for k, v in row_dict.items() if v is not None})
    
    # Ensure admission_cycle and program are in the context even if not in ER/Row
    if admission_cycle and not doc_context.get("admission_cycle"):
        doc_context["admission_cycle"] = admission_cycle
    if program and not doc_context.get("program"):
        doc_context["program"] = program

    # Force Candidate Name resolution if missing or None
    raw_name = doc_context.get("candidate_name") or applicant_doc.candidate_name
    if not raw_name and doc_context.get("applicant_id"):
        raw_name = frappe.db.get_value("Applicant", doc_context["applicant_id"], "candidate_name")
    
    # Absolute string fallback
    safe_name = str(raw_name or "Applicant")
    if safe_name == "None":
        safe_name = "Applicant"
        
    doc_context["candidate_name"] = safe_name
    doc_context["applicant_name"] = safe_name
    doc_context["applicant_id"] = applicant_doc.applicant_id or applicant

    # Resolve Merit Total Score for context
    merit_total_score = doc_context.get("total_score")
    if merit_total_score is None:
        # Try fetching from Merit List Applicant for this cycle
        merit_total_score = frappe.db.get_value("Merit List Applicant", {
            "applicant_id": doc_context.get("applicant_id"),
            "parentfield": "merit_applicants"
        }, "total_score")
    
    # Format if number
    if merit_total_score is not None:
        try:
            merit_total_score = flt(merit_total_score, 3)
        except:
            pass
    
    doc_context["merit_total_score"] = merit_total_score
    doc_context["total_score"] = merit_total_score

    # Re-map status for convenience
    status_label = new_status
    if status_label == "Selected" and doc_context.get("allocation_type") == "Waitlisted":
        status_label = "Waitlisted" # Edge case safety
         
    args = {
        "doc": doc_context,
        "candidate_name": safe_name,
        "applicant_name": safe_name,
        "program": program or doc_context.get("program"),
        "admission_cycle": admission_cycle or doc_context.get("admission_cycle"),
        "status": status_label,
        "old_status": old_status,
        "new_status": new_status,
        "allocation_name": allocation_name,
        "merit_total_score": merit_total_score,
        "total_score": merit_total_score,
        "get_url": get_url,
        "base_url": get_url()
    }

    try:
        subject = frappe.render_template(template.subject, args)
        message = frappe.render_template(template_body, args)
    except Exception as e:
        frappe.logger().error(f"Notification error (Jinja rendering) for {applicant}: {e}\n{frappe.get_traceback()}")
        return

    # Create internal system notification (bell icon)
    try:
        from_user = frappe.session.user if frappe.session.user != "Guest" else "Administrator"
        if frappe.db.exists("User", email):
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": f"Seat Allocation Status: {status_label}",
                "for_user": email,
                "type": "Alert",
                "email_content": f"Your status for Seat Allocation {allocation_name} has been updated to <strong>{status_label}</strong>. <br><br> <a href='/nlsat/my-applications?app={applicant_doc.applicant_id}'>Click here to view details.</a>",
                "document_type": "Seat Allocation",
                "document_name": allocation_name,
                "from_user": from_user,
                "link": f"/nlsat/my-applications?app={applicant_doc.applicant_id}"
            }).insert(ignore_permissions=True)
    except Exception as e:
        frappe.logger().error(f"Notification Log error for {applicant}: {e}")

    # Send the email using robust method
    try:
        _robust_sendmail(
            recipients=[email],
            subject=subject,
            message=message,
            reference_doctype="Seat Allocation",
            reference_name=allocation_name,
            template=template
        )

        # Log specialized communication
        if log_communication:
            log_communication(
                applicant=applicant,
                communication_type="Email",
                category="Seat Allocation",
                subject=subject,
                content=message,
                reference_doctype="Seat Allocation",
                reference_name=allocation_name
            )
    except Exception as e:
        frappe.logger().error(f"Notification error (sendmail) for {applicant}: {e}")
        return

    # Log to Admission Audit Log
    try:
        if log_admission_action:
            log_admission_action(
                reference_doctype="Seat Allocation",
                reference_name=allocation_name,
                applicant=applicant,
                program=program,
                action_type="Notification Sent",
                old_value=old_status,
                new_value=new_status,
                remarks=f"Email notification ('{template_name}' template record) sent to {email}."
            )
        else:
            frappe.logger().warning("Notification: log_admission_action not found, skipping audit log.")
    except Exception as e:
        frappe.logger().error(f"Notification error (audit log) for {applicant}: {e}")


def notify_published_allocation(allocation_name):
    """
    Sends email notifications ONLY to the applicants listed in the 
    Seat Allocation document. Optimized for large volumes.
    """
    allocation = frappe.get_doc("Seat Allocation", allocation_name)
    
    if not allocation.selection_applicant:
        frappe.logger().info(f"Notification: No applicants found in {allocation_name}. Skipping.")
        return

    count = len(allocation.selection_applicant)
    frappe.logger().info(f"Notification: Publishing {allocation_name}. Notifying {count} applicants.")

    # 1. Pre-fetch common data
    template_name = "Seat Allocation Result Notification"
    if not frappe.db.exists("Email Template", template_name):
        frappe.log_error(f"Missing Email Template: '{template_name}'. Seat Allocation notifications skipped for {allocation_name}.", "Email Template Missing")
        return
        
    template = frappe.get_doc("Email Template", template_name)
    template_body = template.response_html if template.get("use_html") else (template.response or template.get("message"))
    
    # 2. Pre-fetch all applicant emails in bulk
    applicant_ids = [row.applicant_id for row in allocation.selection_applicant if row.applicant_id]
    
    # Map applicant_id -> email
    email_map = {}
    if applicant_ids:
        # Check Applicant records
        applicants = frappe.get_all("Applicant", 
            filters={"name": ["in", applicant_ids]}, 
            fields=["name", "email", "candidate_name"]
        )
        for a in applicants:
            if a.email:
                email_map[a.name] = a.email

    # 3. Batch process notifications
    notification_logs = []
    audit_logs = []
    from_user = frappe.session.user if frappe.session.user != "Guest" else "Administrator"
    time_now = now()
    base_url = get_url()

    allowed_statuses = ["Selected", "Waitlisted", "Rejected"]

    for row in allocation.selection_applicant:
        # Skip if status not in allowed list
        if row.selection_status not in allowed_statuses:
            continue

        email = email_map.get(row.applicant_id)
        if not email:
            continue

        # Prepare context for Jinja (Minimal to save memory in large loops)
        safe_name = str(row.candidate_name or "Applicant")
        status_label = row.selection_status
        
        doc_context = {
            "applicant_id": row.applicant_id,
            "candidate_name": safe_name,
            "applicant_name": safe_name,
            "admission_cycle": allocation.admission_cycle,
            "campus": allocation.campus,
            "program": row.program,
            "selection_status": row.selection_status,
            "allocation_type": row.allocation_type,
            "overall_rank": row.overall_rank,
            "total_score": row.total_score
        }

        args = {
            "doc": doc_context,
            "candidate_name": safe_name,
            "applicant_name": safe_name,
            "status": status_label,
            "new_status": row.selection_status,
            "allocation_name": allocation_name,
            "get_url": get_url,
            "base_url": base_url
        }

        try:
            subject = frappe.render_template(template.subject, args)
            message = frappe.render_template(template_body, args)
        except Exception:
            continue

        # A. Send Email using robust method
        _robust_sendmail(
            recipients=[email],
            subject=subject,
            message=message,
            reference_doctype="Seat Allocation",
            reference_name=allocation_name,
            template=template
        )

        # B. Prepare System Notification Log
        if frappe.db.exists("User", email):
            notification_logs.append([
                frappe.generate_hash(length=10), # name
                time_now, time_now, from_user, from_user, 0, # creation, modified, modified_by, owner, docstatus
                subject, # subject
                email, # for_user
                "Alert", # type
                f"Your status for Seat Allocation {allocation_name} has been updated to <strong>{status_label}</strong>.", # email_content
                "Seat Allocation", # document_type
                allocation_name, # document_name
                from_user, # from_user
                f"/nlsat/my-applications?app={row.applicant_id}" # link
            ])

        # C. Prepare Audit Log
        audit_logs.append([
            frappe.generate_hash(length=10), time_now, time_now, from_user, from_user, 0, # name, creation, modified, modified_by, owner, docstatus
            "Seat Allocation", # reference_doctype
            allocation_name, # reference_name
            "Notification Sent", # action_type (maps to action_type field)
            row.applicant_id, # applicant
            row.program, # program
            from_user, # performed_by
            time_now, # performed_on
            f"Bulk email notification sent to {email} on publication.", # remarks
            "Draft", # old_value
            row.selection_status # new_value
        ])

    # 4. Bulk Inserts
    if notification_logs:
        frappe.db.bulk_insert("Notification Log", [
            "name", "creation", "modified", "modified_by", "owner", "docstatus",
            "subject", "for_user", "type", "email_content", 
            "document_type", "document_name", "from_user", "link"
        ], notification_logs)

    if audit_logs:
        frappe.db.bulk_insert("Admission Audit Log", [
            "name", "creation", "modified", "modified_by", "owner", "docstatus",
            "reference_doctype", "reference_name", "action_type", "applicant", "program",
            "performed_by", "performed_on", "remarks", "old_value", "new_value"
        ], audit_logs)

    # Ensure all bulk insertions and queued emails are committed
    frappe.db.commit()
    frappe.logger().info(f"Notification: Bulk publication finished and committed for {allocation_name}.")



def notify_scholarship_status(application_name):
    """
    Sends a professionally designed HTML email notification to scholarship applicant.
    Now uses 'Scholarship Updates' Email Template for easy customization.
    """
    app = frappe.get_doc("Scholarship Application", application_name)
    
    email = frappe.db.get_value("Applicant", app.applicant_id, "email")
    if not email:
        return

    scheme_name = frappe.db.get_value("Scholarship Scheme", app.scholarship_scheme, "scheme_name")
    benefit_amount = fmt_money(app.calculated_benefit) if app.calculated_benefit else "0.00"
    portal_url = get_url("/nlsat/scholarships")
    
    template_name = "Scholarship Updates"
    
    # Lazy Setup: Create the template if it doesn't exist
    if not frappe.db.exists("Email Template", template_name):
        _create_scholarship_template(template_name)

    template = frappe.get_doc("Email Template", template_name)
    
    # Prepare Context
    context = {
        "doc": app,
        "applicant_name": app.applicant_name,
        "application_id": app.name,
        "scheme_name": scheme_name,
        "benefit_amount": benefit_amount,
        "portal_url": portal_url,
        "portal_link": portal_url,
        "status": app.status,
        "rejection_reason": app.rejection_reason,
    }
    
    # Fetch Content based on use_html toggle
    if template.get("use_html"):
        template_body = template.response_html
    else:
        template_body = template.response
        
    if not template_body:
        template_body = template.get("message")

    try:
        # Render the template
        subject = frappe.render_template(template.subject, context)
        message = frappe.render_template(template_body, context)
        
        # Send the email using robust method
        _robust_sendmail(
            recipients=[email],
            subject=subject or f"Scholarship Application Update – {scheme_name}",
            message=message,
            reference_doctype="Scholarship Application",
            reference_name=app.name,
            template=template
        )
    except Exception as e:
        frappe.logger().error(f"Scholarship Notification error for {app.name}: {e}\n{frappe.get_traceback()}")
    
    # Create internal system notification (bell icon)
    try:
        from_user = frappe.session.user if frappe.session.user != "Guest" else "Administrator"
        if frappe.db.exists("User", email):
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": f"Scholarship Status: {app.status}",
                "for_user": email,
                "type": "Alert",
                "email_content": f"Your scholarship application for <strong>{scheme_name}</strong> has been <strong>{app.status}</strong>. <br><br> <a href='/nlsat/scholarships'>Click here to view details.</a>",
                "document_type": "Scholarship Application",
                "document_name": app.name,
                "from_user": from_user,
                "link": "/nlsat/scholarships"
            }).insert(ignore_permissions=True)
    except Exception as e:
        frappe.logger().error(f"Scholarship Notification Log error for {app.name}: {e}")


def _create_scholarship_template(name):
    """Hidden helper to bootstrap the scholarship template with premium styling."""
    try:
        html = f"""
<style>
    .email-container {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }}
    .header {{ background-color: #1a3c6e; color: #ffffff; padding: 30px; text-align: center; }}
    .header h1 {{ margin: 0; font-size: 24px; letter-spacing: 1px; }}
    .content {{ padding: 40px; background-color: #ffffff; }}
    .status-badge {{ display: inline-block; padding: 6px 12px; border-radius: 4px; font-weight: bold; text-transform: uppercase; font-size: 12px; margin-bottom: 20px; }}
    .status-approved {{ background-color: #d1fae5; color: #065f46; }}
    .status-rejected {{ background-color: #fee2e2; color: #991b1b; }}
    .details-box {{ background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 20px; margin: 25px 0; }}
    .label {{ font-weight: bold; color: #64748b; font-size: 13px; }}
    .value {{ font-weight: bold; color: #1e293b; font-size: 14px; }}
    .button {{ display: inline-block; background-color: #1a3c6e; color: #ffffff !important; padding: 14px 28px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-top: 20px; }}
    .footer {{ background-color: #f1f5f9; color: #64748b; padding: 20px; text-align: center; font-size: 12px; }}
</style>

<div class='email-container'>
    <div class='header'>
        <h1>SCHOLARSHIP BOARD</h1>
    </div>
    <div class='content'>
        {{% if doc.status == 'Approved' %}}
            <div class='status-badge status-approved'>Application Approved</div>
            <p>Dear <strong>{{{{ doc.applicant_name }}}}</strong>,</p>
            <p>On behalf of the Scholarship Committee, we are pleased to inform you that your application for the <strong>{{{{ scheme_name strip }}}}</strong> has been officially approved.</p>
            
            <div class='details-box'>
                <table style='width: 100%; border-collapse: collapse;'>
                    <tr>
                        <td style='padding: 10px 0; border-bottom: 1px solid #edf2f7; font-weight: bold; color: #64748b; font-size: 13px; text-align: left;'>Application ID:</td>
                        <td style='padding: 10px 0; border-bottom: 1px solid #edf2f7; font-weight: bold; color: #1e293b; font-size: 14px; text-align: right;'>{{{{ doc.name }}}}</td>
                    </tr>
                    <tr>
                        <td style='padding: 10px 0; border-bottom: 1px solid #edf2f7; font-weight: bold; color: #64748b; font-size: 13px; text-align: left;'>Scholarship Scheme:</td>
                        <td style='padding: 10px 0; border-bottom: 1px solid #edf2f7; font-weight: bold; color: #1e293b; font-size: 14px; text-align: right;'>{{{{ scheme_name }}}}</td>
                    </tr>
                    <tr>
                        <td style='padding: 10px 0; font-weight: bold; color: #64748b; font-size: 13px; text-align: left;'>Approved Benefit:</td>
                        <td style='padding: 10px 0; font-weight: bold; color: #1e293b; font-size: 14px; text-align: right;'>{{{{ benefit_amount }}}}</td>
                    </tr>
                </table>
            </div>
            
            <p>The approved benefit has been automatically applied to your Fee Assignment. You may log in to the student portal to view your updated fee details and complete any pending formalities.</p>
            
            <div style='text-align: center;'>
                <a href='{{{{ portal_url }}}}' class='button'>View on Admission Portal</a>
            </div>
        {{% else %}}
            <div class='status-badge status-rejected'>Application Not Selected</div>
            <p>Dear <strong>{{{{ doc.applicant_name }}}}</strong>,</p>
            <p>Thank you for your application for the <strong>{{{{ scheme_name }}}}</strong>. After a comprehensive review of all submissions, we regret to inform you that we are unable to grant your scholarship request at this time.</p>
            
            <div class='details-box'>
                <p class='label' style='margin-bottom: 5px;'>Reason for Decision:</p>
                <p class='value' style='color: #991b1b;'>{{{{ doc.rejection_reason or 'Eligibility criteria not met / Limited budget availability' }}}}</p>
            </div>
            
            <p>Although you were not selected for this specific scheme, we encourage you to explore other financial aid opportunities available on the admission portal.</p>
            
            <div style='text-align: center;'>
                <a href='{{{{ portal_url }}}}' class='button'>Check Other Schemes</a>
            </div>
        {{% endif %}}
    </div>
    <div class='footer'>
        <p>&copy; {nowdate()[:4]} University Admissions Office. All rights reserved.</p>
        <p>This is an automated notification. Please do not reply directly to this email.</p>
    </div>
</div>
"""
        frappe.get_doc({
            "doctype": "Email Template",
            "name": name,
            "template_name": name,
            "subject": "Scholarship Application Update – {{ scheme_name }}",
            "use_html": 1,
            "response_html": html,
            "owner": "Administrator"
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.logger().error(f"Error bootstrapping Scholarship email template: {e}")


def notify_refund_processed(refund_request_name):
    """
    Sends a professional HTML email notification to the applicant 
    when their refund has been successfully processed via Razorpay.
    """
    refund = frappe.get_doc("Refund Request", refund_request_name)
    
    # Get applicant email
    email = frappe.db.get_value("Applicant", refund.applicant, "email")
    applicant_name = frappe.db.get_value("Applicant", refund.applicant, "candidate_name") or "Applicant"
    
    if not email:
        frappe.logger().warning(f"Refund Notification skipped: No email found for applicant {refund.applicant}")
        return

    refund_amount_str = fmt_money(refund.refund_amount)
    
    template_name = "Refund Processed"
    if not frappe.db.exists("Email Template", template_name):
        frappe.logger().error(f"Notification error: Email Template '{template_name}' not found.")
        return

    template = frappe.get_doc("Email Template", template_name)

    context = {
        "doc": refund,
        "applicant_name": applicant_name,
        "refund_amount_str": refund_amount_str,
        "refund_amount": refund_amount_str,
        "razorpay_refund_id": refund.razorpay_refund_id or "N/A",
        "razorpay_payment_id": refund.razorpay_payment_id or "N/A",
        "portal_url": get_url("/nlsat/my-applications?app=" + str(refund.applicant))
    }

    # Render body
    if template.get("use_html"):
        template_body = template.response_html
    else:
        template_body = template.response or template.get("message")

    try:
        subject = frappe.render_template(template.subject, context)
        message = frappe.render_template(template_body, context)

        # Send the email using robust method
        _robust_sendmail(
            recipients=[email],
            subject=subject or f"Refund Processed Successfully - {refund.name}",
            message=message,
            reference_doctype="Refund Request",
            reference_name=refund.name,
            template=template
        )
        frappe.logger().info(f"Refund Notification sent (robust) for {refund.name} to {email}")

        # Create internal system notification (bell icon)
        try:
            from_user = frappe.session.user if frappe.session.user != "Guest" else "Administrator"
            if frappe.db.exists("User", email):
                frappe.get_doc({
                    "doctype": "Notification Log",
                    "subject": "Refund Processed Successfully",
                    "for_user": email,
                    "type": "Alert",
                    "email_content": f"Your refund request <strong>{refund.name}</strong> has been successfully processed for the amount of <strong>{refund_amount_str}</strong>. <br><br> <a href='/nlsat/my-applications?app={refund.applicant}'>Click here to view details.</a>",
                    "document_type": "Refund Request",
                    "document_name": refund.name,
                    "from_user": from_user,
                    "link": f"/nlsat/my-applications?app={refund.applicant}"
                }).insert(ignore_permissions=True)
        except Exception as e:
            frappe.logger().error(f"Refund Notification Log error for {refund.name}: {e}")

    except Exception as e:
        frappe.logger().error(f"Refund Notification error for {refund.name}: {e}")



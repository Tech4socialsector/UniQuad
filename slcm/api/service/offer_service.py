import frappe
import json
from frappe import _, throw
from frappe.utils import add_days, getdate, now_datetime, get_datetime, flt
from frappe.utils.pdf import get_pdf
from slcm.admission.doctype.offer_configuration.offer_configuration import (
    validate_offer_config_fee_deadlines,
)
from slcm.api.service.fee_service import FeeService

class OfferService:
    """
    Offer Lifecycle Engine - Service Layer.
    Consolidates business logic for student offer management.
    """

    @staticmethod
    def get_config(admission_year, admission_cycle, campus):
        """
        Validates and returns the unique Offer Configuration 
        for a given year, cycle, and campus.
        """
        filters = {
            "admission_year": admission_year,
            "campus": campus
        }
        
        # 1. Try strict match with provided cycle
        if admission_cycle:
            filters["admission_cycle"] = admission_cycle
            config_name = frappe.db.get_value("Offer Configuration", filters)
            
            # Fallback: Try matching admission_year against the Configuration's academic_year field
            if not config_name:
                alt_filters = filters.copy()
                alt_filters["academic_year"] = alt_filters.pop("admission_year")
                config_name = frappe.db.get_value("Offer Configuration", alt_filters)

            if config_name:
                return frappe.get_doc("Offer Configuration", config_name)
        
        # 2. Fallback: If no strict match, try to find ANY config for this Year and Campus
        # This helps if the applicant's cycle is missing, invalid, or pointing to a different ID
        # that actually represents the same semantic cycle.
        filters.pop("admission_cycle", None)
        configs = frappe.db.get_all("Offer Configuration", filters=filters, fields=["name"])
        
        if len(configs) == 1:
            return frappe.get_doc("Offer Configuration", configs[0].name)
        elif len(configs) > 1:
            # If multiple cycles exist, we can't safely fallback without more info
            throw(_("Multiple Offer Configurations found for Year: {0}, Campus: {1}. Please specify a valid Admission Cycle.").format(
                admission_year, campus
            ))

        # 3. Final error if nothing found
        throw(_("No Offer Configuration found for Year: {0}, Cycle: {1}, Campus: {2}").format(
            admission_year, admission_cycle, campus
        ))

    @staticmethod
    def resolve_admission_year(applicant, campus, cycle, admission_year=None):
        """
        Resolves the Admission Year based on direct input, Application, or Academic Year.
        """
        # Helper to find by configuration bridge
        def _resolve_from_config(year_val):
            # Check if this value is linked to any configuration as either admission or academic year
            config_match = frappe.db.get_value("Offer Configuration", {
                "academic_year": year_val
            }, "admission_year") or frappe.db.get_value("Offer Configuration", {
                "admission_year": year_val
            }, "admission_year")
            return config_match

        # 1. If admission_year is provided, check if it exists as a record name
        if admission_year:
            if not frappe.db.exists("Admission Year", admission_year):
                # Probably an Academic Year name (e.g. 2026-2027), find valid Admission Year for it
                # via explicit year field
                resolved = frappe.db.get_value("Admission Year", 
                    {"year": admission_year, "is_active": 1}, "name")
                
                # If still not found, use Offer Configuration as a bridge (common case)
                if not resolved:
                    resolved = _resolve_from_config(admission_year)
                
                if resolved:
                    return resolved
            return admission_year

        # 2. Try to get from Applicant (most specific)
        admission_year = frappe.db.get_value("Applicant", 
            {"name": applicant, "campus": campus, "admission_cycle": cycle}, 
            "admission_year")
        if admission_year:
            return admission_year

        # 3. Try to map from Applicant's Academic Year (most common fallback)
        academic_year = frappe.db.get_value("Applicant", applicant, "academic_year")
        if academic_year:
            # Try to resolve directly via year field
            admission_year = frappe.db.get_value("Admission Year", 
                {"year": academic_year, "is_active": 1}, "name")
            
            # If still not found, use Offer Configuration bridge
            if not admission_year:
                admission_year = _resolve_from_config(academic_year)
            
        return admission_year

    @staticmethod
    @frappe.whitelist()
    def generate_offer(applicant, campus, program, cycle, admission_year=None):
        """
        Main entry point for generating an offer letter.
        Ensures idempotency and follows financial snapshotting rules.
        """
        if not applicant:
            throw(_("Applicant is required to generate an offer letter."))
        if not campus:
            throw(_("Campus is required to generate an offer letter."))

        # Resolve the actual Admission Year DocType entry
        admission_year = OfferService.resolve_admission_year(applicant, campus, cycle, admission_year)

        if not admission_year:
            throw(_("No active Admission Year found for applicant {0}. Please ensure an Admission Year is configured and active for their Academic Year.").format(applicant))

        config = OfferService.get_config(admission_year, cycle, campus)
        resolved_cycle = config.admission_cycle

        validate_offer_config_fee_deadlines(config, program=program)

        # --- PRE-FLIGHT CHECKS (Before Transaction) ---
        if config.enable_notifications:
            if not config.offer_issued_email:
                throw(_("Email Template For Offer Issued is missing in Offer Configuration {0}").format(config.name))
            
            applicant_email = frappe.db.get_value("Applicant", applicant, "email")
            if not applicant_email:
                throw(_("Applicant {0} does not have a valid email address. Cannot send offer letter.").format(applicant))
        
        if not config.pdf_format:
            throw(_("PDF Print Format is missing in Offer Configuration {0}").format(config.name))


        # Status verification: Only 'Selected' applicants in published Seat Allocations can receive offers
        is_foreign = frappe.db.get_value("Applicant", applicant, "foriegn_national") == "Yes"

        if is_foreign:
            isa = frappe.db.get_value("Interview Seat Allocation", {
                "applicant": applicant,
                "program": program
            }, ["name", "status", "result_published"], as_dict=True)
            
            if not isa:
                already_issued = frappe.db.exists("Offer Letter", {"applicant": applicant, "program": program, "status": ["not in", ["Rejected", "Expired", "Withdrawn"]]})
                if not already_issued:
                    throw(_("Applicant {0} is not in any Interview Seat Allocation for Program {1}.").format(applicant, program))
            else:
                if isa.status != "Selected":
                    already_issued = frappe.db.exists("Offer Letter", {"applicant": applicant, "program": program, "status": ["not in", ["Rejected", "Expired", "Withdrawn"]]})
                    if not already_issued:
                        throw(_("Applicant {0} is not in 'Selected' status in Interview Seat Allocation for Program {1}. Current status: {2}").format(applicant, program, isa.status))
        else:
            sa_filters = {
                "applicant_id": applicant,
                "program": program,
                "selection_status": "Selected",
                "parenttype": "Seat Allocation"
            }
            sa_parents = frappe.db.get_all("Seat Selection Applicant", filters=sa_filters, pluck="parent")

            if not sa_parents:
                 # Check if an offer was ALREADY issued (in which case they would be 'Offer Issued')
                 already_issued = frappe.db.exists("Offer Letter", {
                    "applicant": applicant,
                    "program": program,
                    "status": ["not in", ["Rejected", "Expired", "Withdrawn"]]
                 })
                 if not already_issued:
                    throw(_("Applicant {0} is not in 'Selected' status for Program {1} in any Seat Allocation. Offer letter cannot be generated.").format(applicant, program))
            else:
                # Check if parent Seat Allocation matching campus and cycle is Published
                published_filters = {
                    "name": ["in", sa_parents],
                    "status": "Published"
                }
                if resolved_cycle or cycle:
                    published_filters["admission_cycle"] = resolved_cycle or cycle
                if campus:
                    published_filters["campus"] = campus

                published_sa = frappe.db.exists("Seat Allocation", published_filters)
                if not published_sa:
                    # Fallback check without strict cycle/campus if specific match failed
                    published_sa = frappe.db.exists("Seat Allocation", {
                        "name": ["in", sa_parents],
                        "status": "Published"
                    })

                if not published_sa:
                     throw(_("Seat Allocation for Applicant {0} is not yet 'Published'. Please publish the allocation first.").format(applicant))

        # Idempotency: Prevent duplicate offers for same campus, cycle, program and admission_year
        existing = frappe.db.exists("Offer Letter", {
            "applicant": applicant,
            "admission_cycle": resolved_cycle,
            "campus": campus,
            "program": program,
            "admission_year": admission_year,
            "status": ["not in", ["Expired", "Withdrawn", "Rejected", "Draft"]]
        })
        if existing:
            throw(_("An active offer already exists for Applicant {0} in Cycle {1} for Campus {2} and Program {3}. (Offer: {4})").format(
                applicant, resolved_cycle, campus, program, existing
            ))

        # Start Transaction
        frappe.db.begin()
        
        try:
            offer = frappe.new_doc("Offer Letter")
            offer.applicant = applicant
            offer.campus = campus
            offer.program = program
            
            # Use the cycle from config as the primary source of truth
            config_cycle = config.admission_cycle
            
            # Always fetch mandatory years directly from the source Admission Cycle record 
            # to avoid issues with empty fetch_from fields in the Configuration record.
            cycle_data = frappe.db.get_value("Admission Cycle", config_cycle, 
                ["admission_year", "academic_year"], as_dict=1) or {}
            
            offer.admission_cycle = config_cycle
            offer.admission_year = cycle_data.get("admission_year") or admission_year
            offer.academic_year = cycle_data.get("academic_year") or \
                                 frappe.db.get_value("Applicant", applicant, "academic_year") or \
                                 offer.admission_year

            # Identification/Tracking
            offer.offer_id = f"OFF-{applicant}" # Safe temporary ID for templates
            offer.offer_configrationn = config.name
            offer.status = "Draft"
            from frappe.utils import now_datetime
            offer.issued_on = now_datetime()
            
            # Handle possible name duplication if a rejected offer exists with the same ID
            potential_name = f"OL-{applicant}"
            if frappe.db.exists("Offer Letter", potential_name):
                # If it already exists, use standard naming series to avoid SQL Collision
                offer.naming_series = "OL-RE-."
                offer.autoname() # Force standard naming

        
            # Find matching Fee Structure from Configuration
            fee_structure_name = None
            for row in config.fee_structure:
                fs_program = frappe.db.get_value("Fee Structure", row.fee_structure, "program")
                if fs_program == program:
                    fee_structure_name = row.fee_structure
                    break
            
            if not fee_structure_name:
                throw(_("No Fee Structure found for program {0} in Offer Configuration {1}").format(
                    frappe.bold(program), frappe.bold(config.name)
                ))

            offer.fee_structure = fee_structure_name
            
            # Set deadlines
            offer.offer_acceptance_deadline = config.due_date
            
            fee_doc = frappe.get_cached_doc("Fee Structure", fee_structure_name)
            if fee_doc:
                offer.confirmation_fee_deadline = fee_doc.due_date_for_confirmation_fee
                offer.payment_deadline = fee_doc.valid_until
            
            # Freeze Fees from Fee Structure
            foriegn_national = frappe.db.get_value("Applicant", applicant, "foriegn_national")
            is_foreign = foriegn_national == "Yes"
            fee_data = FeeService._calculate_and_freeze_fees(fee_structure_name, is_foreign=is_foreign)
            
            if fee_data.get("is_confirmation_fee_applicable"):
                offer.payable_amount = fee_data.get("confirmation_fee_amount")
            else:
                offer.payable_amount = fee_data.get("total_payable")
            
            # Ensure Fetch From doesn't overwrite our resolved campus and cycle 
            # if they differ from the applicant's default preferences
            offer.insert(ignore_permissions=True)
            
            if is_foreign and isa:
                frappe.db.set_value("Interview Seat Allocation", isa.name, "status", "Offer Issued")

            if campus:
                offer.campus = campus
                offer.db_set('campus', campus)
            if resolved_cycle:
                offer.admission_cycle = resolved_cycle
                offer.db_set('admission_cycle', resolved_cycle)
                
                



            # Commit here so that frappe.get_print (used by _generate_offer_pdf) can
            # read the fully-committed offer record from DB. This is critical in bulk/
            # background jobs where the worker runs in a separate DB connection.
            frappe.db.commit()

            # Generate and Attach PDF
            if config.pdf_format:
                OfferService._generate_offer_pdf(offer, config.pdf_format)
            
            # Send offer letter email logic is now handled by OfferNotificationService via on_update hooks
            
            offer.status = "Issued"
            offer.save(ignore_permissions=True)

            # Sync applicant status only after successful generation and email queuing
            OfferService.update_applicant_status(applicant, status="Offer Issued")
            OfferService.sync_seat_allocation_status(offer, "Offer Issued")

            frappe.db.commit()
            return {
                "offer_name": offer.name,
                "status": offer.status,
                "message": _("Offer letter generated successfully")
            }
        except Exception as e:
            frappe.db.rollback()
            # If it's a known Frappe exception, keep the message clean
            raise e

    @staticmethod
    def accept_offer(offer_name, needs_accommodation=None):
        """
        Business logic for accepting an offer.
        Validates transition and deadline.
        """
        offer = frappe.get_doc("Offer Letter", offer_name)
        
        if offer.status not in ["Issued", "Accepted"]:
            throw(_("Only 'Issued' or 'Accepted' offers can be processed. Current status: {0}").format(offer.status))

        # Reject expired-by-deadline for both Issued and Accepted (idempotent re-calls / race with scheduler)
        if offer.status == "Issued":
            deadline = offer.offer_acceptance_deadline
            deadline_label = "offer acceptance deadline"
        else:
            deadline = offer.confirmation_fee_deadline
            deadline_label = "confirmation fee deadline"

        if deadline and getdate(deadline) < getdate(now_datetime()):
            throw(
                _("This offer is no longer valid: the {0} ({1}) has passed. You cannot proceed.")
                .format(deadline_label, deadline)
            )

        if offer.status == "Issued":
            offer.status = "Accepted"
            offer.accepted_on = now_datetime()
            if needs_accommodation:
                offer.needs_accommodation = needs_accommodation
            offer.save(ignore_permissions=True)

            if needs_accommodation:
                frappe.db.set_value("Applicant", offer.applicant, "needs_accommodation", needs_accommodation)



        # Always try to ensure fee assignment exists if it's accepted
        OfferService.create_fee_assignment_from_offer(offer)
        return True

    @staticmethod
    def reject_applicant_other_offer(applicant , reason):
        if not applicant:
            throw(_("Applicant is required"))
        applicant_other_offers = frappe.get_all("Offer Letter", filters={
            "applicant": applicant,
            "status": "Issued",
            "name": ["!=", frappe.flags.current_offer or ""]
        }, fields=["name"])
        for offer in applicant_other_offers:
            OfferService.reject_offer(offer.name, reason)
        return True

    @staticmethod
    def update_applicant_status(applicant, status):
        if not applicant:
            throw(_("Applicant is required"))

        # Map Seat Allocation selection statuses to specific Applicant Statuses
        status_map = {
            "Selected": "Seat Selected",
            "Waitlisted": "Seat Waitlisted",
            "Rejected": "Seat Rejected"
        }
        
        if status in status_map:
            status = status_map[status]

        # Use db_set to bypass full validation (validate_eligibility) which may throw 
        # for ineligible applicants during status synchronization.
        frappe.db.set_value("Applicant", applicant, "status", status, update_modified=True)
        
        # Ensure 'current_stage' is updated if needed (safety fallback)
        if status in ["Offer Accepted", "Seat Selected"]:
            # Check if 'Admission Confirmed' stage exists before setting it
            if frappe.db.exists("Stages", "Admission Confirmed"):
                frappe.db.set_value("Applicant", applicant, "current_stage", "Admission Confirmed")
            elif frappe.db.exists("Stages", "Seat Allocation"):
                frappe.db.set_value("Applicant", applicant, "current_stage", "Seat Allocation")
            
        return True

    @staticmethod
    def process_fee_payment(offer_name, payment_mode="Cash", reference_number=None):
        return FeeService.process_fee_payment(offer_name, payment_mode, reference_number)
    
    @staticmethod
    def reject_offer(offer_name, reason=None):
        """
        Handles student/admin rejection of an offer.
        """
        offer = frappe.get_doc("Offer Letter", offer_name)
        
        status = offer.status or "Draft"
        if status not in ["Issued", "Draft"]:
            throw(_("Cannot reject offer in status: {0}").format(status))

        offer.status = "Rejected"
        offer.save(ignore_permissions=True)


        return True

    @staticmethod
    @frappe.whitelist()
    def expire_offers():
        """
        Scheduled job logic to transition 'Issued' and 'Accepted' offers to 'Expired'
        after the payment deadline (if payment is not completed).

        Runs from hooks ``scheduler_events`` (daily). Saving the document runs
        ``OfferLetter.on_update`` → ``sync_status_to_seat_allocation`` so Applicant
        ``status`` becomes "Offer Expired" (see status_map for Expired).

        Note: ``Accepted`` → ``Expired`` must be allowed in ``OfferLetter.validate_status_transition``.
        """
        active_offers = frappe.get_all("Offer Letter", filters={
            "status": ["in", ["Issued", "Accepted", "Confirmation Fee Paid"]]
        }, fields=["name", "status", "offer_acceptance_deadline", "confirmation_fee_deadline", "payment_deadline"])

        now_date = frappe.utils.nowdate()
        to_expire = []

        for row in active_offers:
            should_expire = False
            if row.status == "Issued":
                if row.offer_acceptance_deadline and frappe.utils.getdate(row.offer_acceptance_deadline) < frappe.utils.getdate(now_date):
                    should_expire = True
            elif row.status == "Accepted":
                # Find pending fee assignment
                afa = frappe.db.get_value("Applicant Fee Assignment", 
                    {"offer_letter": row.name, "status": "Assigned", "docstatus": ["!=", 2]}, 
                    ["fee_type"], as_dict=1)
                
                if afa:
                    if afa.fee_type == "Confirmation Fee":
                        if row.confirmation_fee_deadline and frappe.utils.getdate(row.confirmation_fee_deadline) < frappe.utils.getdate(now_date):
                            should_expire = True
                    elif afa.fee_type == "Admission Fee":
                        if row.payment_deadline and frappe.utils.getdate(row.payment_deadline) < frappe.utils.getdate(now_date):
                            should_expire = True

            elif row.status == "Confirmation Fee Paid":
                if row.payment_deadline and frappe.utils.getdate(row.payment_deadline) < frappe.utils.getdate(now_date):
                    should_expire = True

            if should_expire:
                to_expire.append(row.name)

        processed = 0
        batch_size = 50 
        
        for i, offer_name in enumerate(to_expire):
            try:
                # We save each individually to trigger the automated status hook
                doc = frappe.get_doc("Offer Letter", offer_name)
                doc.status = "Expired"

                doc.save(ignore_permissions=True)
                

                
                processed += 1
                
                # Commit in chunks to avoid massive db locks
                if (i + 1) % batch_size == 0:
                    frappe.db.commit()
                    
            except Exception as e:
                frappe.db.rollback()
                frappe.log_error(f"Failed to expire offer {offer_name}: {str(e)}", "Auto Expiry Error")
                
        # Final commit for remaining records
        if processed > 0:
            frappe.db.commit()
            
        return processed

    @staticmethod
    @frappe.whitelist()
    def bulk_generate_offers(applicants):
        """
        Entry point for bulk generation.
        Small batches (< 10) are processed immediately.
        Large batches are sent to background workers.
        """
        if isinstance(applicants, str):
            applicants = json.loads(applicants)

        if not applicants:
            return {"message": "No applicants provided"}

        # Threshold for background processing
        if len(applicants) > 250:
            frappe.enqueue(
                method="slcm.api.service.offer_service.background_bulk_worker",
                queue="long",
                timeout=43200, # 12 hours timeout for massive batches (e.g., 10,000+ records)
                applicants=applicants,
                user=frappe.session.user,
                now=frappe.flags.in_test
            )
            return {
                "queued": True,
                "message": _("Large batch detected ({0} applicants). Processing started safely in the background. You will receive a notification when finished.").format(len(applicants))
            }

        # Otherwise, process immediately (standard behavior)
        return OfferService._process_bulk_batch(applicants)

    @staticmethod
    def _process_bulk_batch(applicants):
        """Internal helper to process a batch and return summary."""
        results = {"success": [], "errors": []}
        for data in applicants:
            try:
                # payload resolution logic...
                if isinstance(data, dict) and "applicant" in data:
                    payload = data
                elif isinstance(data, str):
                    # Handle case where only applicant name is passed
                    applicant_name = data
                    # Fetch basic details from Applicant record as fallback
                    details = frappe.db.get_value("Applicant", applicant_name, 
                        ["campus", "program", "admission_cycle", "admission_year"], as_dict=1)
                    
                    if not details:
                        raise ValueError(_("Applicant {0} not found").format(applicant_name))
                    
                    details = frappe._dict(details)

                    # Try to find the Seat Allocation context
                    # Search for a row where this applicant is 'Selected' or 'Accepted'
                    sa_child_filters = {
                        "parenttype": "Seat Allocation",
                        "selection_status": ["in", ["Selected", "Accepted"]],
                        "applicant_id": applicant_name
                    }

                    sa_child_records = frappe.db.get_all(
                        "Seat Selection Applicant",
                        filters=sa_child_filters,
                        fields=["parent", "program"]
                    )
                    sa_child_data = None
                    for rec in sa_child_records:
                        st = frappe.db.get_value("Seat Allocation", rec.parent, "status")
                        if st == "Published":
                            sa_child_data = rec
                            break
                    if not sa_child_data and sa_child_records:
                        sa_child_data = sa_child_records[0]

                    if sa_child_data:
                        parent_sa = frappe.db.get_value("Seat Allocation", sa_child_data.parent, 
                            ["campus", "admission_cycle"], as_dict=1)
                        if parent_sa:
                            # Prioritize Seat Allocation data
                            campus = parent_sa.campus
                            cycle = parent_sa.admission_cycle
                            program = sa_child_data.program
                        else:
                            campus = details.campus
                            cycle = details.admission_cycle
                            program = details.program
                    else:
                        campus = details.campus
                        cycle = details.admission_cycle
                        program = details.program

                    if not campus:
                        raise ValueError(_("Campus could not be determined for Applicant {0}.").format(applicant_name))
                    if not cycle:
                        raise ValueError(_("Admission Cycle could not be determined for Applicant {0}.").format(applicant_name))
                    if not program:
                        raise ValueError(_("Program could not be determined for Applicant {0}.").format(applicant_name))

                    payload = {
                        "applicant": applicant_name,
                        "campus": campus,
                        "program": program,
                        "cycle": cycle,
                        "admission_year": details.admission_year
                    }
                else:
                    payload = data

                name = OfferService.generate_offer(
                    applicant=payload.get("applicant"),
                    campus=payload.get("campus"),
                    program=payload.get("program"),
                    cycle=payload.get("cycle"),
                    admission_year=payload.get("admission_year")
                )
                results["success"].append({
                    "applicant": payload.get("applicant"), 
                    "offer": name.get("offer_name") if isinstance(name, dict) else name
                })
            except Exception as e:
                frappe.db.rollback()
                error_msg = str(e) or "Unknown Server Error"
                
                # If it's a configuration error regarding deadlines, throw it properly so the UI halts
                if "Deadline cannot be in the past" in error_msg:
                    frappe.throw(error_msg)
                    
                results["errors"].append({"applicant": str(data.get("applicant") if isinstance(data, dict) else data), "error": error_msg})
                frappe.log_error(f"Bulk Offer Generation Error for {str(data)}: {error_msg}", "Offer Service")
        
        return results

    @staticmethod
    def background_bulk_worker(applicants, user):
        """Background task for high-volume generation."""
        # Switch session user to the requester
        frappe.set_user(user)

        total = len(applicants)
        success_count = 0
        error_count = 0
        errors = []

        # Process in chunks and commit to prevent memory leaks and transaction locks
        for i, data in enumerate(applicants):
            try:
                res = OfferService._process_bulk_batch([data])
                if res.get("success"):
                    success_count += len(res["success"])
                    # Commit every record to ensure it is saved immediately
                    frappe.db.commit()
                if res.get("errors"):
                    error_count += len(res["errors"])
                    errors.extend([f"Applicant: {e.get('applicant')} - Error: {e.get('error')}" for e in res["errors"]])
            except Exception as e:
                frappe.db.rollback()
                error_count += 1
                errors.append(f"Fatal error processing {data}: {str(e)}")

        # Create a System Notification upon completion
        summary_msg = _("Successfully generated {0} offers.").format(success_count)
        if error_count > 0:
            summary_msg += _(" {0} errors encountered.").format(error_count)

        error_details = ""
        if errors:
            error_details = "<br><br><b>Recent Errors:</b><ul style='font-size: 11px; color: #e53e3e;'>"
            error_details += "".join([f"<li>{e}</li>" for e in errors[:15]])
            error_details += "</ul>"
            if len(errors) > 15:
                error_details += f"<div style='font-size: 11px;'>...and {len(errors) - 15} more. Check Error Log for full details.</div>"

        notification_content = f"""
            <div style="font-family: sans-serif; padding: 5px;">
                <h4 style="color: #1a202c; margin-bottom: 12px;">{_('Bulk Offer Generation Report')}</h4>
                <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                    <span style="background: #f0fff4; color: #2f855a; padding: 4px 10px; border-radius: 4px; border: 1px solid #c6f6d5; font-weight: bold; font-size: 12px;">
                        {success_count} {_('Successful')}
                    </span>
                    <span style="background: { '#fff5f5' if error_count > 0 else '#f7fafc' }; color: { '#c53030' if error_count > 0 else '#718096' }; padding: 4px 10px; border-radius: 4px; border: 1px solid { '#fed7d7' if error_count > 0 else '#edf2f7' }; font-weight: bold; font-size: 12px;">
                        {error_count} {_('Failed')}
                    </span>
                </div>
                <p style="font-size: 13px; color: #4a5568; line-height: 1.5;">
                    {_('Offer generation process has finished for {0} applicants.').format(total)}
                </p>
                {error_details}
                <div style="margin-top: 15px; border-top: 1px solid #edf2f7; padding-top: 12px;">
                    <a href="/app/offer-letter" style="background: #1a202c; color: #ffffff !important; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 13px; display: inline-block;">
                        {_('View Offer Letters')}
                    </a>
                </div>
            </div>
        """

        # Dispatch standard Frappe notification
        from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
        enqueue_create_notification(
            [user],
            {
                "subject": _("Bulk Offer Generation Finished"),
                "email_content": notification_content,
                "type": "Alert",
                "document_type": "Offer Letter"
            }
        )

        # Also publish real-time alert if user is still logged in
        frappe.publish_realtime(
            "msgprint", 
            {
                "message": summary_msg, 
                "title": _("Background Process Completed"),
                "indicator": "green" if error_count == 0 else "orange",
                "primary_action": {
                    "label": _("View Offer Letters"),
                    "action": "frappe.set_route('List', 'Offer Letter')"
                }
            }, 
            user=user
        )
        
        return {
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors
        }

    @staticmethod
    @frappe.whitelist()
    def bulk_update_status(offer_names, action, notes=None):
        """
        API endpoint for bulk status updates (Accept/Reject).
        """
        if isinstance(offer_names, str):
            offer_names = json.loads(offer_names)

        results = {"success": [], "errors": []}
        
        for name in offer_names:
            try:
                if action == "Accepted":
                    OfferService.accept_offer(name)
                elif action == "Rejected":
                    OfferService.reject_offer(name, reason=notes)
                else:
                    throw(_("Invalid action: {0}").format(action))
                results["success"].append(name)
            except Exception as e:
                results["errors"].append({"name": name, "error": str(e)})

        return results

    # --- Internal Utilities ---

    @staticmethod
    def _calculate_deadline(fee_structure_name):
        return FeeService._calculate_deadline(fee_structure_name)


    
    @staticmethod
    def _calculate_and_freeze_fees(fee_structure_name, is_foreign=False):
        return FeeService._calculate_and_freeze_fees(fee_structure_name, is_foreign=is_foreign)

    @staticmethod
    # Removed _send_offer_letter_email



    @staticmethod
    def _get_template_context(offer):
        """Helper to build rich context for Jinja templates."""
        # Inject virtual fields for template compatibility
        offer.offer_id = offer.name or _("Draft")
        offer.valid_till = offer.payment_deadline

        # Default values to prevent Jinja UndefinedError
        context = {
            "doc": offer,
            "frappe": frappe,
            "applicant": None,
            "applicant_name": None,
            "applicant_doc": frappe._dict(),
            "program": frappe._dict(),
            "campus": frappe._dict(),
            "admission_cycle": frappe._dict()
        }
        
        if offer.applicant:
            try:
                applicant_doc = frappe.get_doc("Applicant", offer.applicant)
                context["applicant_doc"] = applicant_doc
                name = applicant_doc.candidate_name or applicant_doc.name
                context["applicant"] = name
                context["applicant_name"] = name
            except Exception:
                pass
            
        if offer.program:
            try:
                context["program"] = frappe.get_doc("Programme", offer.program)
            except Exception:
                pass
            
        if offer.campus:
            try:
                context["campus"] = frappe.get_doc("Campus", offer.campus)
            except Exception:
                pass
            
        if offer.admission_cycle:
            try:
                context["admission_cycle"] = frappe.get_doc("Admission Cycle", offer.admission_cycle)
            except Exception:
                pass
            
        return context



    @staticmethod
    def _generate_offer_pdf(offer_doc, print_format):
        """Generates PDF and HTML preview, attaching them to the Offer Letter record."""
        try:
            # Generate HTML for preview
            html_content = frappe.get_print("Offer Letter", offer_doc.name, print_format, as_pdf=False)
            offer_doc.db_set("rendered_content", html_content)
            offer_doc.rendered_content = html_content

            # Generate PDF
            # Workaround for wkhtmltopdf HostNotFoundError/deadlock on single-threaded dev servers
            original_host_name = frappe.conf.get("host_name")
            try:
                if frappe.conf.get("developer_mode"):
                    if getattr(frappe.local, "request", None):
                        from urllib.parse import urlparse
                        parsed = urlparse(frappe.request.host_url)
                        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
                        frappe.conf.host_name = f"{parsed.scheme}://127.0.0.1:{port}"
                    else:
                        port = frappe.conf.get("webserver_port") or 8000
                        frappe.conf.host_name = f"http://127.0.0.1:{port}"
                
                try:
                    pdf_content = frappe.get_print("Offer Letter", offer_doc.name, print_format, as_pdf=True)
                except Exception as pdf_err:
                    frappe.log_error(f"wkhtmltopdf crashed during Offer Letter generation: {str(pdf_err)}", "PDF Generation Error")
                    pdf_content = None
            finally:
                if original_host_name is not None:
                    frappe.conf.host_name = original_host_name
                elif "host_name" in frappe.conf:
                    del frappe.conf.host_name
            
            if not pdf_content:
                frappe.log_error(f"PDF Generation returned empty content for {offer_doc.name}", "PDF Generation Warning")
                return
            
            file_name = f"Offer_Letter_{offer_doc.name}.pdf"
            
            _file = frappe.get_doc({
                "doctype": "File",
                "file_name": file_name,
                "attached_to_doctype": "Offer Letter",
                "attached_to_name": offer_doc.name,
                "attached_to_field": "offer_letter_pdf",
                "content": pdf_content,
                "is_private": 1
            })
            _file.insert(ignore_permissions=True)
            
            # Set on object (for the upcoming offer.save() call in single-generation flow)
            offer_doc.offer_letter_pdf = _file.file_url
            
            # Also persist immediately via db_set so the URL is stored even in bulk/background
            # flows where the final offer.save() may not carry the in-memory field value
            offer_doc.db_set("offer_letter_pdf", _file.file_url)
            
        except Exception as e:
            frappe.log_error(f"PDF Generation Failed for {offer_doc.name}: {frappe.get_traceback()}", "PDF Generation Error")
            # Re-raise so the bulk worker correctly counts this as a failure
            raise

    @staticmethod
    def _attach_static_pdf(offer_doc, file_url):
        """Attaches a static PDF from configuration to the Offer Letter record."""
        try:
            if not file_url:
                return

            offer_doc.offer_letter_pdf = file_url
            
            # Find the original file record to copy metadata
            original_files = frappe.get_all("File", filters={"file_url": file_url}, limit=1)
            if original_files:
                original_doc = frappe.get_doc("File", original_files[0].name)
                
                # Create a new File record linked to this Offer Letter
                # This ensures it shows in the sidebar and _send_offer_letter_email can find it
                _file = frappe.new_doc("File")
                _file.file_name = original_doc.file_name
                _file.file_url = original_doc.file_url
                _file.attached_to_doctype = "Offer Letter"
                _file.attached_to_name = offer_doc.name
                _file.attached_to_field = "offer_letter_pdf"
                _file.is_private = original_doc.is_private
                _file.insert(ignore_permissions=True)
                
        except Exception as e:
            frappe.log_error(f"Static PDF Attachment Failed for {offer_doc.name}: {str(e)}")



    @staticmethod
    def sync_seat_allocation_status(offer, status):
        """
        Synchronizes offer status back to the Seat Allocation child table.
        Uses Document API to trigger audit logs and waitlist promotions.
        """
        if not offer or not status:
            return

        # Find the specific Seat Allocation parent
        seat_allocation_name = frappe.db.get_value(
            "Seat Selection Applicant",
            {
                "applicant_id": offer.applicant,
                "program": offer.program,
                "parenttype": "Seat Allocation"
            },
            "parent"
        )

        if not seat_allocation_name:
            return

        try:
            alloc_doc = frappe.get_doc("Seat Allocation", seat_allocation_name)
            
            # Security check: Ensure campus and cycle match (handles multi-program/multi-campus edge cases)
            if alloc_doc.campus != offer.campus or alloc_doc.admission_cycle != offer.admission_cycle:
                # Find matching allocation if the first one wasn't correct
                match = frappe.db.sql("""
                    SELECT parent FROM `tabSeat Selection Applicant`
                    WHERE applicant_id = %s AND program = %s AND parenttype = 'Seat Allocation'
                    AND parent IN (SELECT name FROM `tabSeat Allocation` WHERE campus = %s AND admission_cycle = %s)
                """, (offer.applicant, offer.program, offer.campus, offer.admission_cycle))
                if match:
                    alloc_doc = frappe.get_doc("Seat Allocation", match[0][0])
                else:
                    return

            updated = False
            for row in alloc_doc.selection_applicant:
                if row.applicant_id == offer.applicant and row.program == offer.program:
                    row.selection_status = status
                    updated = True
                    break
            
            if updated:
                # Saving triggers before_save/on_update which handles Waitlist Promotion
                alloc_doc.save(ignore_permissions=True)
                frappe.db.commit()
                
        except Exception as e:
            frappe.log_error(f"Sync Seat Allocation Status Failed for {offer.name}: {str(e)}", "Offer Service")

    @staticmethod
    def create_fee_assignment_from_offer(offer):
        return FeeService.create_fee_assignment_from_offer(offer)

    @staticmethod
    def get_online_payment_url(offer_name, gateway=None):
        return FeeService.get_online_payment_url(offer_name, gateway)

    @staticmethod
    def create_offer_razorpay_order(offer_name):
        return FeeService.create_offer_razorpay_order(offer_name)

    @staticmethod
    def verify_offer_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, offer_name):
        return FeeService.verify_offer_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, offer_name)

    @staticmethod
    @frappe.whitelist()
    def get_pending_offers_list():
        """
        Fetches all Offers with 'Issued' status that haven't passed their deadline.
        Applies standard Frappe permissions dynamically.
        """
        user = frappe.session.user
        if user == "Guest":
            frappe.throw("Not permitted", frappe.PermissionError)

        roles = frappe.get_roles(user)
        filters = {"status": "Issued"}

        # If the user is strictly an Applicant (without desk access), restrict to their own email
        # to ensure they only get their own data, avoiding hardcoding other roles.
        has_desk_access = frappe.db.get_value("User", user, "user_type") == "System User"
        if "Applicant" in roles and not has_desk_access:
            filters["email"] = user

        offers = frappe.get_all(
            "Offer Letter",
            filters=filters,
            fields=["name", "applicant", "program", "offer_acceptance_deadline as payment_deadline"],
            ignore_permissions=False,
            order_by="offer_acceptance_deadline asc"
        )

        from frappe.utils import getdate, nowdate
        today = getdate(nowdate())

        valid_offers = []
        for offer in offers:
            if offer.payment_deadline and getdate(offer.payment_deadline) < today:
                continue

            offer.applicant_name = frappe.db.get_value("Applicant", offer.applicant, "candidate_name")
            valid_offers.append(offer)

        return valid_offers

    @staticmethod
    @frappe.whitelist()
    def send_bulk_reminders(offer_names=None, email_template=None, send_email=True, send_notification=True, sender_email=None):
        """
        API endpoint to send reminders using an Email Template.
        Uses background queueing for large batches.
        """
        from frappe.utils import cint
        
        send_email = bool(cint(send_email))
        send_notification = bool(cint(send_notification))

        if not offer_names:
            frappe.throw(_("Please select at least one offer to send reminders."))

        if isinstance(offer_names, str):
            offer_names = json.loads(offer_names)

        if not email_template:
            frappe.throw(_("Email Template is required for reminders."))

        # Threshold for background processing
        if len(offer_names) > 250:
            frappe.enqueue(
                method="slcm.api.service.offer_service._send_bulk_reminders_worker",
                queue="long",
                offer_names=offer_names,
                email_template=email_template,
                send_email=send_email,
                send_notification=send_notification,
                sender_email=sender_email,
                user=frappe.session.user
            )
            return {
                "status": "success",
                "message": _("Bulk reminder process started in the background for {0} offers. You will receive a notification when finished.").format(len(offer_names))
            }

        return OfferService._send_bulk_reminders_worker(
            offer_names, email_template, send_email, send_notification, sender_email
        )

    @staticmethod
    def _send_bulk_reminders_worker(offer_names, email_template, send_email=True, send_notification=True, sender_email=None, user=None):
        """
        Internal worker to process a batch of reminders.
        """
        if user:
            frappe.set_user(user)

        success_count = 0
        error_count = 0
        error_details = []

        try:
            tpl = frappe.get_doc("Email Template", email_template)
        except Exception as e:
            msg = _("Failed to load Email Template {0}: {1}").format(email_template, str(e))
            if user:
                frappe.log_error(msg, "Offer Reminder Error")
            return {"status": "error", "message": msg}

        actual_sender = None
        if sender_email:
            actual_sender = frappe.db.get_value("Email Account", sender_email, "email_id")
        
        if not actual_sender and tpl.get("email_account"):
            actual_sender = frappe.db.get_value("Email Account", tpl.get("email_account"), "email_id") or tpl.get("email_account")

        for offer_name in offer_names:
            try:
                if not frappe.db.exists("Offer Letter", offer_name):
                    continue
                    
                offer = frappe.get_doc("Offer Letter", offer_name)
                context = OfferService._get_template_context(offer)

                # Render dynamic content
                subject = frappe.render_template(tpl.subject, context)
                message_content = tpl.response_html if tpl.use_html else tpl.response
                final_message = frappe.render_template(message_content, context)
                
                # Email Delivery
                if send_email and offer.applicant:
                    applicant_email = frappe.db.get_value("Applicant", offer.applicant, "email")
                    if applicant_email:
                        cc_list = []
                        if tpl.get("cc"):
                            cc_val = tpl.get("cc")
                            cc_list = [c.strip() for c in cc_val.replace(";", ",").split(",") if c.strip()]

                        frappe.sendmail(
                            recipients=[applicant_email],
                            subject=subject,
                            message=final_message,
                            reference_doctype="Offer Letter",
                            reference_name=offer.name,
                            sender=actual_sender,
                            cc=cc_list if cc_list else None
                        )
                    else:
                        raise ValueError(_("Applicant has no email address."))
                
                # System Notification Delivery
                if send_notification:
                    receiver = offer.notification_receiver
                    if not receiver and offer.applicant:
                        email = frappe.db.get_value("Applicant", offer.applicant, "email")
                        if email:
                            receiver = frappe.db.get_value("User", {"email": email}, "name")
                    
                    if receiver:
                        frappe.get_doc({
                            "doctype": "Notification Log",
                            "subject": subject,
                            "document_type": "Offer Letter",
                            "document_name": offer.name,
                            "for_user": receiver
                        }).insert(ignore_permissions=True)
                    else:
                        raise ValueError(_("No recipient User found for system notification."))
                
                success_count += 1
            except Exception as e:
                error_count += 1
                err_msg = f"{offer_name}: {str(e)}"
                error_details.append(err_msg)
                frappe.log_error(f"Offer Reminder Error for {offer_name}: {err_msg}", "Offer Reminder Error")
                
        # Completion Summary
        summary_msg = _("Processed {0} reminders. Success: {1}, Errors: {2}").format(
            len(offer_names), success_count, error_count
        )

        # Notify user (for background jobs)
        if user:
            from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
            
            report_html = f"<p>{summary_msg}</p>"
            if error_count > 0:
                report_html += f"<b>{_('Error Details:')}</b><ul>"
                for err in error_details:
                    report_html += f"<li>{err}</li>"
                report_html += "</ul>"

            enqueue_create_notification(
                [user],
                {
                    "subject": _("Bulk Offer Reminder Report"),
                    "email_content": report_html,
                    "type": "Alert",
                    "document_type": "Offer Letter"
                }
            )

        return {
            "status": "success" if error_count == 0 else "partial_success",
            "message": summary_msg
        }



@frappe.whitelist()
def generate_offer(applicant, campus, program, cycle, admission_year=None):
    return OfferService.generate_offer(applicant, campus, program, cycle, admission_year)

@frappe.whitelist()
def bulk_generate_offers(applicants):
    return OfferService.bulk_generate_offers(applicants)

@frappe.whitelist()
def bulk_update_status(offer_names, action, notes=None):
    return OfferService.bulk_update_status(offer_names, action, notes)

@frappe.whitelist()
def accept_offer(offer_name, needs_accommodation=None):
    # Set a flag so reject_applicant_other_offer knows which offer was just accepted
    frappe.flags.current_offer = offer_name
    return OfferService.accept_offer(offer_name, needs_accommodation)

@frappe.whitelist()
def reject_applicant_other_offer(applicant, reason):
    return OfferService.reject_applicant_other_offer(applicant, reason)

@frappe.whitelist()
def process_fee_payment(offer_name, payment_mode="Cash", reference_number=None):
    from slcm.api.service.fee_service import FeeService
    return FeeService.process_fee_payment(offer_name, payment_mode, reference_number)

@frappe.whitelist()
def reject_offer(offer_name, reason=None):
    return OfferService.reject_offer(offer_name, reason)

@frappe.whitelist()
def expire_offers():
    return OfferService.expire_offers()

@frappe.whitelist()
def get_online_payment_url(offer_name, gateway=None):
    return OfferService.get_online_payment_url(offer_name, gateway)

@frappe.whitelist(allow_guest=True)
def create_offer_razorpay_order(offer_name):
    from slcm.api.service.fee_service import FeeService
    return FeeService.create_offer_razorpay_order(offer_name)

@frappe.whitelist(allow_guest=True)
def verify_offer_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, offer_name):
    from slcm.api.service.fee_service import FeeService
    return FeeService.verify_offer_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, offer_name)

@frappe.whitelist()
def get_pending_offers_list():
    return OfferService.get_pending_offers_list()

@frappe.whitelist()
def send_bulk_reminders(offer_names=None, email_template=None, send_email=True, send_notification=True, sender_email=None):
    return OfferService.send_bulk_reminders(offer_names, email_template, send_email, send_notification, sender_email)

def background_bulk_worker(applicants, user=None):
    return OfferService.background_bulk_worker(applicants, user)

def _send_bulk_reminders_worker(offer_names, email_template, send_email=True, send_notification=True, sender_email=None, user=None):
    return OfferService._send_bulk_reminders_worker(offer_names, email_template, send_email, send_notification, sender_email, user)
import frappe
from frappe import _
from frappe.utils import flt

@frappe.whitelist(allow_guest=True)
def get_offer_details(offer_name=None):
    """
    Fetches details of a specific offer letter or the latest active one.
    Supports Admin view.
    """
    user = frappe.session.user
    if user == "Guest":
        return {"error": "Authentication required"}

    roles = frappe.get_roles(user)
    is_admin = "Administrator" in roles or "System Manager" in roles

    # Find applicant linked to this user for default filtering
    applicant = frappe.db.get_value("Applicant", {"email": user}, "name")
    if not applicant and frappe.db.exists("Applicant", user):
        applicant = user

    if offer_name:
        # Verify the offer exists. If not admin, verify it belongs to this user's email.
        check_filters = {"name": offer_name}
        if not is_admin:
            check_filters["email"] = user

        exists = frappe.get_all("Offer Letter", filters=check_filters, limit=1, ignore_permissions=True)
        if not exists:
            return {"error": _("Offer Letter {0} not found or you don't have permission to view it.").format(offer_name)}
        offer_id = offer_name
    else:
        # User is looking for their own latest offer
        latest_filters = {
            "status": ["in", ["Issued", "Accepted", "Payment Completed"]]
        }
        if not is_admin:
            latest_filters["email"] = user
            
        offers = frappe.get_all("Offer Letter", 
            filters=latest_filters, 
            fields=["name"], 
            order_by="creation desc", 
            limit=1, 
            ignore_permissions=True
        )
        
        if not offers:
            return {"error": _("No active admission offer found for your account at this time.")}
        offer_id = offers[0].name

    try:
        offer_doc = frappe.get_doc("Offer Letter", offer_id)
        offer_dict = offer_doc.as_dict()
        rendered_content = offer_doc.rendered_content
        target_applicant = offer_doc.applicant
        fee_structure = offer_doc.fee_structure
    except frappe.PermissionError:
        safe_fields = ["name", "applicant", "candidate_name", "program", "status", "rendered_content", "fee_structure", "offer_deadline", "confirmation_fee_due_date", "full_fee_due_date", "campus", "admission_cycle", "accepted_on", "needs_accommodation"]
        offer_fields = frappe.get_all("Offer Letter", filters={"name": offer_id}, fields=safe_fields, limit=1, ignore_permissions=True)
        if not offer_fields:
            return {"error": _("Access Denied")}
        offer_dict = offer_fields[0]
        rendered_content = offer_dict.get("rendered_content")
        target_applicant = offer_dict.get("applicant")
        fee_structure = offer_dict.get("fee_structure")

    fee_data = []

    # First, try to fetch pending components from Applicant Fee Assignment (AFA)
    afa = frappe.db.get_value("Applicant Fee Assignment",
        {"offer_letter": offer_id, "fee_type": "Admission Fee", "status": "Assigned", "docstatus": ["!=", 2]},
        ["name", "final_payable_amount", "scholarship_amount", "scholarship_applied", "total_amount", "fee_type", "confirmation_fee"],
        order_by="creation desc",
        as_dict=True)

    if not afa:
        afa = frappe.db.get_value("Applicant Fee Assignment",
            {"offer_letter": offer_id, "fee_type": "Admission Fee", "docstatus": ["!=", 2]},
            ["name", "final_payable_amount", "scholarship_amount", "scholarship_applied", "total_amount", "fee_type", "confirmation_fee"],
            order_by="creation desc",
            as_dict=True)

    conf_afa = frappe.db.get_value("Applicant Fee Assignment",
        {"offer_letter": offer_id, "fee_type": "Confirmation Fee", "docstatus": ["!=", 2]},
        ["total_amount", "confirmation_fee", "name"],
        order_by="creation desc", as_dict=True)

    confirmation_fee_amount = 0
    if conf_afa:
        confirmation_fee_amount = conf_afa.confirmation_fee or conf_afa.total_amount
    elif afa and afa.confirmation_fee:
        confirmation_fee_amount = afa.confirmation_fee

    if afa:
        if afa.final_payable_amount is not None:
            offer_dict["payable_amount"] = afa.final_payable_amount
            
        afa_components = frappe.get_all("Applicant Fee Component Child",
            filters={"parent": afa.name, "parenttype": "Applicant Fee Assignment"},
            fields=["component_name", "fee_component", "total_amount", "amount"],
            ignore_permissions=True
        )
        for comp in afa_components:
            is_acc = frappe.db.get_value("Fee Component", comp.fee_component, "is_accommodation_fee")
            fee_data.append({
                "component": comp.component_name or comp.fee_component,
                "amount": comp.total_amount or comp.amount,
                "is_accommodation_fee": is_acc
            })

    if not fee_data and fee_structure:
        applicant_nationality = "Indian"
        if target_applicant:
            applicant_nationality = frappe.db.get_value("Applicant", target_applicant, "nationality") or "Indian"

        parentfield = "fee_components_for_indian" if applicant_nationality.strip().lower() == "indian" else "fee_components_for_foreign"

        fs_doc = frappe.get_doc("Fee Structure", fee_structure)
        if fs_doc.is_confirmation_fee_applicable and not confirmation_fee_amount:
            confirmation_fee_amount = fs_doc.confirmation_fee_amount

        fs_components = frappe.get_all("Fee Component Child",
            filters={"parent": fee_structure, "parenttype": "Fee Structure", "parentfield": parentfield},
            fields=["component_name", "fee_component", "total_amount", "amount"],
            ignore_permissions=True
        )
        for comp in fs_components:
            is_acc = frappe.db.get_value("Fee Component", comp.fee_component, "is_accommodation_fee")
            fee_data.append({
                "component": comp.component_name or comp.fee_component,
                "amount": comp.total_amount or comp.amount,
                "is_accommodation_fee": is_acc
            })
            
    offer_dict["confirmation_fee_amount"] = confirmation_fee_amount
    if fee_structure:
        offer_dict["deduct_confirmation_fee"] = frappe.db.get_value("Fee Structure", fee_structure, "deduct_confirmation_fee") or 0
    else:
        offer_dict["deduct_confirmation_fee"] = 0
    offer_dict["program_name"] = frappe.db.get_value("Programme", offer_dict.get("program"), "program_name") or offer_dict.get("program")

    fee_paid = (offer_dict.get("status") == "Payment Completed")
    if not fee_paid:
        is_admission_paid = frappe.db.get_value("Applicant Fee Assignment",
            {"offer_letter": offer_id, "fee_type": "Admission Fee", "status": ["in", ["Paid", "Converted"]]}, "name")
        if is_admission_paid:
            fee_paid = True

    applicant_id = target_applicant
    admission_cycle = offer_dict.get("admission_cycle") or frappe.db.get_value("Applicant", applicant_id, "admission_cycle")
    live_scholarship_query = frappe.db.sql("""
        SELECT SUM(calculated_benefit)
        FROM `tabScholarship Application`
        WHERE applicant_id = %s AND admission_cycle = %s AND status = 'Approved'
    """, (applicant_id, admission_cycle))
    live_scholarship = live_scholarship_query[0][0] if live_scholarship_query and live_scholarship_query[0] else 0
    scholarship_amount = flt(live_scholarship)
    offer_dict["scholarship_amount"] = scholarship_amount

    online_payment_enabled = frappe.db.get_value("Fee Structure", fee_structure, "online_payment") if fee_structure else False

    scholarship_data = None
    latest_sa = frappe.get_all("Scholarship Application",
        filters={"applicant_id": applicant_id, "admission_cycle": admission_cycle, "docstatus": ["!=", 2]},
        fields=["name", "status", "scholarship_scheme", "calculated_benefit", "original_fee_amount", "final_fee_amount", "income_certificate", "supporting_documents"],
        order_by="creation desc",
        limit=1
    )
    if latest_sa:
        scholarship_data = latest_sa[0]
        if scholarship_data.status == "Submitted":
            scholarship_data.status = "Submitted"

    applied_scholarship = 0
    if afa and afa.scholarship_applied and flt(afa.scholarship_amount) > 0:
        offer_dict["payable_amount"] = flt(afa.final_payable_amount)
        applied_scholarship = flt(afa.scholarship_amount)
    elif scholarship_data and scholarship_data.status == "Approved":
        benefit = flt(scholarship_data.calculated_benefit)
        offer_dict["payable_amount"] = max(0, flt(offer_dict["payable_amount"]) - benefit)
        applied_scholarship = benefit

    if applied_scholarship > 0:
        fee_data.append({
            "component": "Scholarship Benefit",
            "amount": -applied_scholarship,
            "is_discount": True
        })

    if afa and afa.fee_type == "Admission Fee" and flt(afa.confirmation_fee) > 0:
        fee_data.append({
            "component": "Confirmation Fee Paid",
            "amount": -flt(afa.confirmation_fee),
            "is_discount": True
        })

    applicant_data = frappe.get_all("Applicant", filters={"name": target_applicant}, fields=["*"], limit=1, ignore_permissions=True)
    applicant_dict = applicant_data[0] if applicant_data else {}
    if applicant_dict and not applicant_dict.get("candidate_photo"):
        applicant_dict["candidate_photo"] = frappe.db.get_value("User", frappe.session.user, "user_image")

    cancellation = frappe.get_all("Admission Cancellation", 
        filters={"offer": offer_id}, 
        fields=["name", "status"], 
        limit=1
    )
    cancellation_info = {
        "has_cancellation": True if cancellation else False,
        "cancellation_name": cancellation[0].name if cancellation else "",
        "cancellation_status": cancellation[0].status if cancellation else ""
    }

    from slcm.admission.utils.scholarship_availability import get_available_scholarships_for_dashboard
    available_scholarships_count = 0
    enable_scholarship = frappe.db.get_value("Admission Cycle", admission_cycle, "enable_scholarship")
    if enable_scholarship:
        try:
            available_scholarships = get_available_scholarships_for_dashboard(
                applicant_id=target_applicant,
                cycle=admission_cycle,
                campus=applicant_dict.get("campus"),
                program=applicant_dict.get("program"),
                applicant_statuses=[applicant_dict.get("status")]
            )
            available_scholarships_count = len(available_scholarships)
        except Exception:
            pass

    receipts = frappe.get_all("Applicant Payment Receipt",
        filters={"offer_letter": offer_id, "docstatus": ["<", 2]},
        fields=["name", "fee_type", "payment_date", "payment_mode", "transaction_id"],
        order_by="creation desc", ignore_permissions=True)

    return {
        "offer": offer_dict,
        "applicant": applicant_dict,
        "fee_breakdown": fee_data,
        "rendered_content": rendered_content,
        "is_admin": is_admin,
        "is_fee_paid": True if fee_paid else False,
        "online_payment_enabled": online_payment_enabled,
        "currency": frappe.defaults.get_global_default("currency") or "INR",
        "cancellation": cancellation_info,
        "available_scholarships_count": available_scholarships_count,
        "scholarship_application": scholarship_data,
        "receipts": receipts
    }

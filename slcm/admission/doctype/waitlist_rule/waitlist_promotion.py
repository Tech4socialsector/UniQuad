import frappe
import math
from frappe.utils import now_datetime, getdate
from slcm.admission.doctype.seat_allocation.seat_allocation import get_category_priority, get_applicant_categories
from slcm.security.access import require_desk_user


def _get_program_quotas(campus: str, admission_cycle: str, program: str) -> dict:
    # 1. Try to find the program row from Admission Cycle for campus-specific linking
    program_row = frappe.db.get_value("Admission Cycle Program", {
        "parent": admission_cycle,
        "campus": campus,
        "program": program
    }, ["name", "seats", "reservation_policy"], as_dict=True)

    result = {"GEN": 0, "Reserved": {}}
    policy_name = None
    fallback_seats = 0

    if program_row:
        policy_name = program_row.reservation_policy
        fallback_seats = int(program_row.seats or 0)
    
    # 2. If no policy found via child table, try direct lookup by cycle and program
    if not policy_name:
        policy_name = frappe.db.get_value("Programme Reservation Policy", {
            "admission_cycle": admission_cycle,
            "program": program,
            "status": ["!=", "Locked"] # Fetch any active or draft policy if not locked
        }, "name")

    if not policy_name and not fallback_seats:
        frappe.throw(f"No active Programme Reservation Policy or Seats found in cycle '{admission_cycle}' for Campus '{campus}' and Program '{program}'")

    if policy_name:
        # 2. Fetch quotas from Programme Reservation Policy
        policy = frappe.get_doc("Programme Reservation Policy", policy_name)
        
        for q in (policy.categories or []):
            seats = int(q.seats or 0)
            
            # Map to GEN pool if category name is General or empty
            if q.category_name == "General" or not q.category_name:
                result["GEN"] += seats
            else:
                # Use category_name for Reserved mapping
                category = q.category_name
                result["Reserved"][category] = result["Reserved"].get(category, 0) + seats
    else:
        # Fallback to total seats if no policy defined
        result["GEN"] = int(fallback_seats or 0)

    # Safety fallback: if computed seats is 0, fallback to total seats
    if int(result.get("GEN") or 0) + sum(int(v or 0) for v in (result.get("Reserved") or {}).values()) <= 0:
        result["GEN"] = int(fallback_seats or 0)
    
    return result


def _get_latest_seat_allocation(admission_cycle: str, campus: str, program_level: str = None):
    filters = {"admission_cycle": admission_cycle, "campus": campus, "docstatus": ["<", 2]}
    if program_level:
        filters["program_level"] = program_level
        
    name = frappe.db.get_value(
        "Seat Allocation",
        filters,
        "name",
        order_by="modified desc",
    )
    if not name:
        return None
    return frappe.get_doc("Seat Allocation", name)


def _lock_seat_allocation(seat_allocation_name: str) -> None:
    # Prevent race conditions if manual + scheduler are run at the same time.
    frappe.db.sql(
        """
        SELECT name
        FROM `tabSeat Allocation`
        WHERE name=%s
        FOR UPDATE
        """,
        (seat_allocation_name,),
    )




def process_waitlist(rule_doc, ignore_cutoff=False):
    if not rule_doc or rule_doc.doctype != "Waitlist Rule":
        frappe.throw("Invalid Waitlist Rule")


    if (rule_doc.status or "").lower() != "active":
        return

    if not ignore_cutoff and rule_doc.upgrade_cutoff_date and getdate(now_datetime()) > getdate(rule_doc.upgrade_cutoff_date):
        return

    seat_alloc = _get_latest_seat_allocation(rule_doc.admission_cycle, rule_doc.campus, rule_doc.program_level)
    if not seat_alloc:
        return

    _lock_seat_allocation(seat_alloc.name)

    # Campus-wide rule: Get all programs in this allocation
    programs_to_process = list(set([r.program for r in seat_alloc.selection_applicant if r.program]))

    any_promoted = False
    promoted_applicants = []
    for program in programs_to_process:
        promoted = _process_single_program_waitlist(seat_alloc, program, rule_doc)
        if promoted:
            any_promoted = True
            promoted_applicants.extend(promoted)

    if any_promoted:
        seat_alloc.save(ignore_permissions=True)
        # Commit to ensure OfferService sees the "Selected" status in the database
        frappe.db.commit()

        from slcm.api.service.offer_service import OfferService
        for app_id, prog in promoted_applicants:
            try:
                OfferService.generate_offer(
                    applicant=app_id,
                    campus=seat_alloc.campus,
                    program=prog,
                    cycle=seat_alloc.admission_cycle
                )
            except Exception as e:
                frappe.log_error(f"Auto Offer Generation Failed for {app_id} (Post-Promotion): {str(e)}", "Waitlist Promotion")

    rule_doc.db_set("last_executed_on", now_datetime(), update_modified=False)
    rule_doc.db_set("execution_log_count", int(rule_doc.execution_log_count or 0) + 1, update_modified=False)

    # Commit is now handled by the caller (scheduled job or manual trigger)
    # to avoid breaking transactions when called from Seat Allocation hooks.


def _process_single_program_waitlist(seat_alloc, program: str, rule_doc) -> list:
    """
    Upgraded promotion logic with Category Sliding.
    Ensures applicants are moved to their highest priority eligible category (GEN first, then Reserved by priority).
    """
    from slcm.admission.doctype.admission_audit_log.audit_service import log_seat_allocation_action
    from slcm.admission.notification_service import notify_status_change

    quotas = _get_program_quotas(rule_doc.campus, rule_doc.admission_cycle, program)
    priority_map = get_category_priority(rule_doc.admission_cycle, rule_doc.campus, program)
    
    # Define active statuses that occupy or want a seat
    # We include people who already have offers to allow them to "slide" to GEN and free up reserved seats
    selection_statuses = ["Selected", "Offer Issued", "Offer Accepted", "Accepted", "Enrolled", "Seat Selected"]
    waitlist_statuses = ["Waitlisted"]
    
    # 1. Gather all active candidates for this program
    active_pool = [
        r for r in seat_alloc.selection_applicant
        if r.program == program and (r.selection_status in selection_statuses or r.selection_status in waitlist_statuses)
    ]
    
    if not active_pool:
        return []

    # Sort by Merit: Total Score DESC, Overall Rank ASC
    active_pool.sort(key=lambda x: (-(x.total_score or 0), x.overall_rank or 999999))

    promoted_list = []
    total_promoted = 0
    
    # Quota tracking
    vacancies = {
        "GEN": quotas["GEN"],
        "Reserved": quotas["Reserved"].copy()
    }

    # 2. Re-allocate everyone in the pool based on current vacancies
    for row in active_pool:
        old_status = row.selection_status
        old_type = row.allocation_type
        old_cat = row.allocated_category
        
        assigned = False
        new_type = None
        new_cat = None
        
        # A. Try GEN first (Highest priority for everyone)
        if vacancies["GEN"] > 0:
            assigned = True
            new_type = "Open"
            new_cat = "General"
            vacancies["GEN"] -= 1
        else:
            # B. Try Reserved Categories in priority order
            applicant_categories = get_applicant_categories(row.applicant_id)
            # Filter and sort applicant's categories by the program's priority policy
            valid_categories = sorted(
                [c for c in applicant_categories if c in vacancies["Reserved"]],
                key=lambda c: priority_map.get(c, 999)
            )
            
            for cat in valid_categories:
                if vacancies["Reserved"][cat] > 0:
                    assigned = True
                    new_type = "Reserved"
                    new_cat = cat
                    vacancies["Reserved"][cat] -= 1
                    break
        
        if assigned:
            if old_status in waitlist_statuses:
                # PROMOTION from Waitlist
                row.selection_status = "Selected"
                row.allocation_type = new_type
                row.vertical_category = new_cat
                row.allocated_category = new_cat
                total_promoted += 1
                promoted_list.append((row.applicant_id, program))
                
                log_seat_allocation_action(
                    seat_allocation=seat_alloc.name,
                    admission_cycle=seat_alloc.admission_cycle,
                    applicant=row.applicant_id,
                    program=program,
                    action_type="Waitlist Promoted",
                    old_value="Waitlisted",
                    new_value="Selected",
                    remarks=f"Promoted to {new_type} seat ({new_cat or 'GEN'}) via Upgradation Engine."
                )
                
                # Sync status to Applicant record immediately
                from slcm.api.service.offer_service import OfferService
                OfferService.update_applicant_status(row.applicant_id, status="Selected")

                notify_status_change(row.applicant_id, program, "Waitlisted", "Selected", seat_alloc.name, seat_alloc.admission_cycle)
            
            elif old_type != new_type or old_cat != new_cat:
                # UPGRADATION / SLIDING
                row.allocation_type = new_type
                row.vertical_category = new_cat
                row.allocated_category = new_cat
                
                log_seat_allocation_action(
                    seat_allocation=seat_alloc.name,
                    admission_cycle=seat_alloc.admission_cycle,
                    applicant=row.applicant_id,
                    program=program,
                    action_type="Seat Allocated",
                    old_value=f"{old_type} ({old_cat or 'GEN'})",
                    new_value=f"{new_type} ({new_cat or 'GEN'})",
                    remarks="Slided to a higher priority category seat."
                )
        else:
            # No seat available. 
            # If they were already Selected, this means quotas were reduced or merit changed.
            # We keep them Selected but mark their category as "Overflow" or just keep the old one?
            # To be safe and avoid demotions, if they were Selected, they MUST keep a seat.
            if old_status in selection_statuses:
                # Force keep their old seat if possible, or just let them stay Selected.
                # However, our logic above ensures merit order. If they don't get a seat now,
                # it's because someone better took it.
                # BUT we should not demote. So we'll give them an 'extra' seat if needed.
                row.selection_status = old_status # Keep it
                row.allocation_type = old_type
                row.allocated_category = old_cat
            else:
                row.selection_status = "Waitlisted"
                row.allocation_type = None
                row.allocated_category = None

    if total_promoted:
        seat_alloc.total_selected = int(seat_alloc.total_selected or 0) + total_promoted
        seat_alloc.total_waitlisted = max(0, int(seat_alloc.total_waitlisted or 0) - total_promoted)
        return promoted_list

    return []


@frappe.whitelist()
def run_manual_waitlist(rule: str):
    require_desk_user()
    rule_doc = frappe.get_doc("Waitlist Rule", rule)
    process_waitlist(rule_doc, ignore_cutoff=True)
    frappe.db.commit()


def run_scheduled_waitlist():
    """
    Scheduled job: runs waitlist promotion based on the 'Upgrade Frequency' setting.
    - 'Automatic': runs every time the scheduler triggers this method (every 10 min).
    - 'Manual': skipped.
    """
    rules = frappe.get_all(
        "Waitlist Rule",
        filters={"status": "Active", "upgrade_frequency": "Automatic"},
        fields=["name"],
    )

    for r in rules:
        try:
            process_waitlist(frappe.get_doc("Waitlist Rule", r.name))
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(f"Scheduled Waitlist Promotion Failed for {r.name}: {str(e)}", "Waitlist Promotion")


def expire_waitlists_past_cutoff():
    """
    Scheduled daily job: identifies active Waitlist Rules where the upgrade_cutoff_date has passed.
    Rejects all remaining Waitlisted applicants for that rule's scope and marks the rule as Inactive.
    """
    rules = frappe.get_all(
        "Waitlist Rule",
        filters={"status": "Active", "upgrade_cutoff_date": ["<", frappe.utils.nowdate()]},
        fields=["name"]
    )
    
    for r in rules:
        try:
            rule_doc = frappe.get_doc("Waitlist Rule", r.name)
            seat_alloc = _get_latest_seat_allocation(rule_doc.admission_cycle, rule_doc.campus, rule_doc.program_level)
            
            if seat_alloc:
                _lock_seat_allocation(seat_alloc.name)
                
                from slcm.admission.doctype.admission_audit_log.audit_service import log_seat_allocation_action
                from slcm.api.service.offer_service import OfferService
                from slcm.admission.notification_service import notify_status_change
                
                rejected_count = 0
                for row in seat_alloc.selection_applicant:
                    if row.selection_status == "Waitlisted":
                        row.selection_status = "Rejected"
                        rejected_count += 1
                        
                        log_seat_allocation_action(
                            seat_allocation=seat_alloc.name,
                            admission_cycle=seat_alloc.admission_cycle,
                            applicant=row.applicant_id,
                            program=row.program,
                            action_type="Seat Rejected",
                            old_value="Waitlisted",
                            new_value="Rejected",
                            remarks="Waitlist expired (cutoff date passed)."
                        )
                        OfferService.update_applicant_status(row.applicant_id, status="Rejected")
                        try:
                            notify_status_change(row.applicant_id, row.program, "Waitlisted", "Rejected", seat_alloc.name, seat_alloc.admission_cycle)
                        except Exception as ne:
                            frappe.log_error(f"Failed to send waitlist expiry notification to {row.applicant_id}: {str(ne)}", "Waitlist Expiry")
                
                if rejected_count > 0:
                    seat_alloc.total_waitlisted = max(0, int(seat_alloc.total_waitlisted or 0) - rejected_count)
                    seat_alloc.total_rejected = int(seat_alloc.total_rejected or 0) + rejected_count
                    seat_alloc.save(ignore_permissions=True)
            
            # Mark the rule as Inactive so it doesn't process again
            rule_doc.db_set("status", "Inactive")
            frappe.db.commit()
            
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(f"Waitlist Expiry Failed for {r.name}: {str(e)}", "Waitlist Expiry")


def process_waitlist_background(admission_cycle: str, campus: str, program_level: str = None, now: bool = False):
    """
    Background worker to run waitlist promotion for all active automatic rules 
    for a specific cycle, campus and program level.
    """
    filters = {
        "status": "Active",
        "admission_cycle": admission_cycle,
        "campus": campus,
        "upgrade_frequency": "Automatic"
    }
    if program_level:
        filters["program_level"] = program_level

    rule_names = frappe.get_all(
        "Waitlist Rule",
        filters=filters,
        pluck="name",
    )

    for rule_name in rule_names:
        frappe.flags.slcm_waitlist_promotion_in_progress = True
        try:
            # Manual triggers (from on_update) should ignore the cutoff date
            process_waitlist(frappe.get_doc("Waitlist Rule", rule_name), ignore_cutoff=True)
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(f"Background Waitlist Promotion Failed for {rule_name}: {str(e)}", "Waitlist Promotion")
        finally:
            frappe.flags.slcm_waitlist_promotion_in_progress = False
def promote_waitlist_without_rule(campus, admission_cycle, program_level=None):
    """
    NLSAT Promotion: Runs promotion for all programs in the latest allocation
    without requiring a Waitlist Rule document.
    """
    seat_alloc = _get_latest_seat_allocation(admission_cycle, campus, program_level)
    if not seat_alloc:
        return

    _lock_seat_allocation(seat_alloc.name)

    programs_to_process = list(set([r.program for r in seat_alloc.selection_applicant if r.program]))

    any_promoted = False
    promoted_applicants = []
    
    # Simple object to mimic rule_doc for internal helpers if needed
    class DummyRule:
        def __init__(self, campus, cycle, level):
            self.campus = campus
            self.admission_cycle = cycle
            self.program_level = level
            self.doctype = "Waitlist Rule"

    dummy_rule = DummyRule(campus, admission_cycle, program_level)

    for program in programs_to_process:
        promoted = _process_single_program_waitlist(seat_alloc, program, dummy_rule)
        if promoted:
            any_promoted = True
            promoted_applicants.extend(promoted)

    if any_promoted:
        seat_alloc.save(ignore_permissions=True)
        frappe.db.commit()

        from slcm.api.service.offer_service import OfferService
        for app_id, prog in promoted_applicants:
            try:
                OfferService.generate_offer(
                    applicant=app_id,
                    campus=seat_alloc.campus,
                    program=prog,
                    cycle=seat_alloc.admission_cycle
                )
            except Exception as e:
                frappe.log_error(f"Auto Offer Generation Failed for {app_id} (Post-Promotion): {str(e)}", "Waitlist Promotion")
    
    return any_promoted

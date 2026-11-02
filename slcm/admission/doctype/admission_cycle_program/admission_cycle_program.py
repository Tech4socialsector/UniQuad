
import frappe
from frappe.model.document import Document
import json
from frappe import _
from slcm.admission.utils.institution import is_multi_campus_enabled
from slcm.security.access import require_desk_user

class AdmissionCycleProgram(Document):
    pass

@frappe.whitelist()
def save_categories(admission_cycle, program, total_seats, policy_document=None, reservation_rows=None, 
                    existing_policy=None, payment_gateway=None, payment_receipt_template=None, campus=None,
                    horizontal_rows=None, compartmental_rows=None, status="Active"):
    require_desk_user()
    if isinstance(reservation_rows, str):
        reservation_rows = json.loads(reservation_rows)
    if isinstance(horizontal_rows, str):
        horizontal_rows = json.loads(horizontal_rows)
    if isinstance(compartmental_rows, str):
        compartmental_rows = json.loads(compartmental_rows)

    # If existing_policy is provided, this is an UPDATE
    if existing_policy:
        if not frappe.db.exists("Programme Reservation Policy", existing_policy):
            frappe.throw(_("Reservation Policy {0} not found.").format(existing_policy))
        doc = frappe.get_doc("Programme Reservation Policy", existing_policy)
    else:
        # NEW record — check for duplicates (Program + Cycle + Campus)
        filters = {
            "admission_cycle": admission_cycle,
            "program": program,
            "campus": campus
        }
        existing = frappe.db.get_value("Programme Reservation Policy", filters, "name")
        if existing:
            frappe.throw(
                _("A reservation policy already exists for {0} at {1} in Cycle {2}.").format(program, campus, admission_cycle)
            )
        doc = frappe.new_doc("Programme Reservation Policy")
        doc.admission_cycle = admission_cycle
        doc.program = program
        doc.campus = campus

    doc.total_seats = total_seats
    doc.status = status
    doc.policy_document = policy_document or ""
    doc.payment_gateway = payment_gateway
    doc.payment_receipt_template = payment_receipt_template

    # 1. Main Categories (Vertical)
    doc.set("categories", [])
    for r in reservation_rows:
        doc.append("categories", {
            "reservation_quota": r.get("reservation_quota"),
            "category_name": r.get("category_name"),
            "priority": r.get("priority"),
            "percentage": r.get("percentage"),
            "seats": r.get("seats"),
            "application_fee": r.get("application_fee"),
            "application_fee_for_indian": r.get("application_fee_for_indian") or r.get("application_fee") or 0,
            "application_fee_for_foreign": r.get("application_fee_for_foreign") or r.get("application_fee") or 0,
            "min_percentile": r.get("min_percentile"),
            "compartmentalized_category": r.get("compartmentalized_category"),
            "compartmentalized_waitlist_seats": r.get("compartmentalized_waitlist_seats")
        })

    # 2. Horizontal Reservations
    doc.set("horizontal_reservations", [])
    if horizontal_rows:
        for r in horizontal_rows:
            doc.append("horizontal_reservations", {
                "category_name": r.get("category_name"),
                "percentage": r.get("percentage"),
                "seats": r.get("seats")
            })

    # 3. Compartmentalised Reservations
    doc.set("compartmental_reservations", [])
    if compartmental_rows:
        for r in compartmental_rows:
            doc.append("compartmental_reservations", {
                "category_name": r.get("category_name"),
                "percentage": r.get("percentage"),
                "seats": r.get("seats")
            })

    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)

    # Automatically generate the reservation matrix preview
    from slcm.admission.doctype.programme_reservation_policy.programme_reservation_policy import generate_matrices
    generate_matrices(doc.name)

    frappe.db.commit()
    
    # Get updated modified timestamp of the parent Admission Cycle
    new_modified = frappe.db.get_value("Admission Cycle", admission_cycle, "modified")
    
    return {
        "policy_name": doc.name,
        "new_modified": new_modified
    }

@frappe.whitelist()
def save_program_media(program, active, brochure_pdf, media_rows, parent_doctype, parent_name):
    """
    Save or update Program Media for a given Program.

    - Doc name is always set to the Program name.
    - If a Program Media doc with name == program already exists, it is updated.
    - If not, a new doc is created with name = program.
    """
    require_desk_user()
    if isinstance(media_rows, str):
        media_rows = json.loads(media_rows)

    active = int(active) if active else 0

    # Check if Program Media doc already exists with name = program
    if frappe.db.exists("Program Media", program):
        doc = frappe.get_doc("Program Media", program)
    else:
        doc = frappe.new_doc("Program Media")
        doc.name = program          # Set doc name = program name
        doc.program = program

    doc.is_active = active
    doc.brochure_pdf = brochure_pdf or ""

    # Clear and re-add child rows
    doc.set("media_gallery", [])

    for row in media_rows:
        if not row.get("media_type") or not row.get("file_url"):
            frappe.throw(_("Media Type and File are mandatory for all rows."))

        doc.append("media_gallery", {
            "media_type": row.get("media_type"),
            "file": row.get("file_url"),
            "sequence": int(row.get("sequence") or 1),
            "caption": row.get("caption") or ""
        })

    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)

    frappe.db.commit()

    return doc.name
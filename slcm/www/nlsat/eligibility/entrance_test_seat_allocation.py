import os
import frappe
from frappe import _
from frappe.utils import format_datetime, get_url

def get_context(context):
    from slcm.admission.utils.portal import get_portal_config
    context.portal_config = get_portal_config()
    
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Please login to view this page"), frappe.PermissionError)

    # Get applicant name for the current user
    applicant_name = frappe.db.get_value("Applicant", {"email": user}, "name")
    if not applicant_name:
        context.no_record = True
        return context

    # Get Seat Allocation record name directly without wasted full field query
    allocation_name = frappe.db.get_value(
        "Entrance Test Seat Allocation", 
        {"applicant": applicant_name},
        "name",
        order_by="creation desc"
    )

    if not allocation_name:
        context.no_record = True
        return context

    doc = frappe.get_doc("Entrance Test Seat Allocation", allocation_name)
    context.doc = doc
    
    # Check if rescheduled
    is_rescheduled = (doc.is_rescheduled == 1 or doc.entrance_test_status == "Rescheduled")
    context.is_rescheduled = is_rescheduled
    
    # Track previous schedule if rescheduled
    if is_rescheduled:
        context.previous_schedule = {
            "center": doc.center_name,
            "address": doc.center_address,
            "date": doc.allocation_date,
            "status": doc.allocation_status or "Rescheduled",
            "reason": doc.reschedule_reason or "System Rescheduled"
        }
    else:
        context.previous_schedule = None
    
    # Get preferences
    raw_prefs = doc.re_assigned_preferences if is_rescheduled else doc.assigned_preferences
    context.preferences = []
    for p in raw_prefs:
        context.preferences.append({
            "provider": p.provider,
            "center_name": p.center_name,
            "center_address": p.center_address
        })
    
    # Check if result is published
    context.show_result = (doc.entrance_test_status in ["Attended", "Absent"] and doc.result_published == 1)

    # Entrance test times calculation (reporting time is 45 mins before start time)
    from slcm.admission.utils.portal import get_entrance_test_times
    test_time_str, rep_time_str = get_entrance_test_times(doc)
    context.test_time = test_time_str
    context.reporting_time = rep_time_str
    # Branding & JSON for client-side generation
    campus_branding = {"campus_name": doc.campus or "Institution of Legal Education", "logo": None}
    try:
        if doc.campus:
            campus = frappe.get_doc("Campus", doc.campus)
            campus_branding["campus_name"] = campus.campus_name or doc.campus
            campus_branding["logo"] = campus.logo
    except: pass
    context.campus_branding = campus_branding
    context.doc_json = frappe.as_json(doc.as_dict())
    
    return context

@frappe.whitelist()
def save_provider(allocation_name, selected_provider, is_rescheduled=False):
    """
    Saves the provider choice for the applicant.
    """
    from slcm.admission.doctype.entrance_test_list.entrance_test_list import (
        confirm_applicant_preference, 
        confirm_rescheduled_preference
    )
    
    # Security check: verify ownership
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Please login to proceed"), frappe.PermissionError)

    applicant_name = frappe.db.get_value("Applicant", {"email": user}, "name")
    
    # Get data from allocation record
    alloc_data = frappe.db.get_value("Entrance Test Seat Allocation", allocation_name, ["applicant", "email"], as_dict=True)
    
    if not alloc_data:
        frappe.throw(_("Entrance Test Seat Allocation record not found."), frappe.DoesNotExistError)

    is_authorized = False
    
    if applicant_name and alloc_data.applicant == applicant_name:
        is_authorized = True
    elif alloc_data.email and alloc_data.email.strip().lower() == user.strip().lower():
        is_authorized = True
    else:
        user_roles = frappe.get_roles(user)
        if any(role in user_roles for role in ["System Manager", "Entrance Test Admin", "Exam Cell"]):
            is_authorized = True

    if not is_authorized:
        frappe.throw(_("You are not authorized to modify this record."), frappe.PermissionError)
    
    # Validation
    doc = frappe.get_doc("Entrance Test Seat Allocation", allocation_name)
    if isinstance(is_rescheduled, str):
        is_rescheduled = is_rescheduled.lower() == "true"

    prefs = doc.re_assigned_preferences if is_rescheduled else doc.assigned_preferences
    if not any(p.provider == selected_provider for p in prefs):
        frappe.throw(_("Please choose from your assigned preference centers."))

    if is_rescheduled:
        return confirm_rescheduled_preference(allocation_name, selected_provider)
    else:
        return confirm_applicant_preference(allocation_name, selected_provider)

@frappe.whitelist(allow_guest=True)
def download_admit_card(allocation_name=None, **kwargs):
    """
    Downloads the Admit Card PDF generated from the 'Admit Card' Print Format.
    Requires authentication and ownership verification.
    """
    if not allocation_name:
        allocation_name = kwargs.get("allocation_name") or frappe.form_dict.get("allocation_name")

    if not allocation_name:
        frappe.throw(_("Missing parameter: allocation_name"), frappe.DataError)

    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Please login to proceed"), frappe.PermissionError)

    allocation_name = str(allocation_name).strip().strip('"').strip("'")

    applicant_name = frappe.db.get_value("Applicant", {"email": user}, "name")
    alloc_data = frappe.db.get_value("Entrance Test Seat Allocation", allocation_name, ["applicant", "email"], as_dict=True)
    
    if not alloc_data:
        frappe.log_error(title="Download Admit Card Error", message=f"Allocation Name: {allocation_name}\nForm Dict: {frappe.form_dict}")
        frappe.throw(_(f"Entrance Test Seat Allocation record not found for name: '{allocation_name}'"), frappe.DoesNotExistError)

    is_authorized = False
    if applicant_name and alloc_data.applicant == applicant_name:
        is_authorized = True
    elif alloc_data.email and alloc_data.email.strip().lower() == user.strip().lower():
        is_authorized = True
    else:
        user_roles = frappe.get_roles(user)
        if any(role in user_roles for role in ["System Manager", "Entrance Test Admin", "Exam Cell"]):
            is_authorized = True

    if not is_authorized:
        frappe.throw(_("You are not authorized to access this admit card."), frappe.PermissionError)

    doc = frappe.get_doc("Entrance Test Seat Allocation", allocation_name)
    
    is_rescheduled = (doc.is_rescheduled == 1 or doc.entrance_test_status == "Rescheduled")
    status = doc.re_allocation_status if is_rescheduled else doc.allocation_status
    
    if status not in ["Allocated", "Reallocated"]:
        frappe.throw(_("Admit Card is only available after seat allocation is confirmed."))

    field_to_check = "re_admit_card_download" if is_rescheduled else "admit_card_download"
    stored_file_url = getattr(doc, field_to_check)

    if stored_file_url and stored_file_url.startswith("/private/files/"):
        try:
            file_doc = frappe.get_doc("File", {"file_url": stored_file_url})
            frappe.local.response.filename = f"Admit_Card_{doc.applicant}.pdf"
            frappe.local.response.filecontent = file_doc.get_content()
            frappe.local.response.type = "download"
            return
        except Exception:
            pass

    # If the URL is dynamic, generate the physical file now and update the document
    from slcm.admission.doctype.entrance_test_list.entrance_test_list import generate_and_store_admit_card
    
    physical_file_url = generate_and_store_admit_card(doc, is_rescheduled)
    
    if physical_file_url and physical_file_url.startswith("/private/files/"):
        try:
            file_doc = frappe.get_doc("File", {"file_url": physical_file_url})
            frappe.local.response.filename = f"Admit_Card_{doc.applicant}.pdf"
            frappe.local.response.filecontent = file_doc.get_content()
            frappe.local.response.type = "download"
            return
        except Exception:
            pass
            
    frappe.throw(_("PDF generation failed for admit card."))

def ensure_admit_card_print_format():
    if not frappe.db.exists("Print Format", "Admit Card"):
        pf_path = frappe.get_app_path("slcm", "admission", "print_format", "admit_card", "admit_card.json")
        if os.path.exists(pf_path):
            import json
            with open(pf_path, "r", encoding="utf-8") as f:
                pf_data = json.load(f)
                pf_doc = frappe.new_doc("Print Format")
                pf_doc.update(pf_data)
                pf_doc.insert(ignore_permissions=True)
                frappe.db.commit()

def get_admit_card_html(doc, is_rescheduled):
    """
    Fetches the Admit Card HTML using the 'Admit Card' Print Format from Desk or direct template fallback.
    """
    ensure_admit_card_print_format()
    print_format_name = "Admit Card"
    
    try:
        frappe.flags.ignore_print_permissions = True
        return frappe.get_print(
            doc.doctype, 
            doc.name, 
            print_format_name, 
            as_pdf=False, 
            no_letterhead=True
        )
    except Exception as e:
        import traceback
        frappe.log_error(
            message=traceback.format_exc(),
            title=f"get_print failed for Admit Card {getattr(doc, 'name', '')}"
        )

    pf_path = frappe.get_app_path("slcm", "admission", "print_format", "admit_card", "admit_card.json")
    if os.path.exists(pf_path):
        import json
        with open(pf_path, "r", encoding="utf-8") as f:
            pf_json = json.load(f)
            html_template = pf_json.get("html")
            if html_template:
                from slcm.admission.utils.jinja import get_file_b64
                return frappe.render_template(html_template, {"doc": doc, "get_file_b64": get_file_b64})

    frappe.throw(_("Admit Card Print Format could not be loaded."))


@frappe.whitelist(allow_guest=True)
def download_result_card(allocation_name=None, **kwargs):
    if not allocation_name:
        allocation_name = kwargs.get("allocation_name") or frappe.form_dict.get("allocation_name")

    if not allocation_name:
        frappe.throw(_("Missing parameter: allocation_name"), frappe.DataError)

    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Please login to proceed"), frappe.PermissionError)

    allocation_name = str(allocation_name).strip().strip('"').strip("'")

    applicant_name = frappe.db.get_value("Applicant", {"email": user}, "name")
    alloc_data = frappe.db.get_value("Entrance Test Seat Allocation", allocation_name, ["applicant", "email"], as_dict=True)
    
    if not alloc_data:
        frappe.throw(_(f"Entrance Test Seat Allocation record not found for name: '{allocation_name}'"), frappe.DoesNotExistError)

    is_authorized = False
    if applicant_name and alloc_data.applicant == applicant_name:
        is_authorized = True
    elif alloc_data.email and alloc_data.email.strip().lower() == user.strip().lower():
        is_authorized = True
    else:
        user_roles = frappe.get_roles(user)
        if any(role in user_roles for role in ["System Manager", "Entrance Test Admin", "Exam Cell"]):
            is_authorized = True

    if not is_authorized:
        frappe.throw(_("You are not authorized to access this result card."), frappe.PermissionError)

    doc = frappe.get_doc("Entrance Test Seat Allocation", allocation_name)
    
    if doc.result_published != 1:
        frappe.throw(_("Result Card is only available after results are published."))

    stored_file_url = doc.entrance_test_result_card

    if stored_file_url and stored_file_url.startswith("/private/files/"):
        try:
            file_doc = frappe.get_doc("File", {"file_url": stored_file_url})
            frappe.local.response.filename = f"Result_Card_{doc.applicant}.pdf"
            frappe.local.response.filecontent = file_doc.get_content()
            frappe.local.response.type = "download"
            return
        except Exception:
            pass

    # Generate physical file now
    physical_file_url = doc._generate_physical_result_card()
    
    if physical_file_url and physical_file_url.startswith("/private/files/"):
        try:
            file_doc = frappe.get_doc("File", {"file_url": physical_file_url})
            frappe.local.response.filename = f"Result_Card_{doc.applicant}.pdf"
            frappe.local.response.filecontent = file_doc.get_content()
            frappe.local.response.type = "download"
            return
        except Exception:
            pass
            
    frappe.throw(_("PDF generation failed for result card."))

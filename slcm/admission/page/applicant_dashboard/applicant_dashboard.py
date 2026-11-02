import frappe
from frappe import _

@frappe.whitelist()
def get_dashboard_data():
    """
    Fetches comprehensive data for the applicant dashboard.
    """
    user = frappe.session.user
    if user == "Guest":
        return {"error": _("Authentication required")}

    # Find applicant record linked to this user's email
    applicant_name = frappe.db.get_value("Applicant", {"email": user}, "name")
    if not applicant_name:
        return {"no_application": True}

    applicant = frappe.get_doc("Applicant", applicant_name)
    
    return {
        "applicant": applicant.as_dict(),
        "campus_status": get_campus_status(applicant.name),
        "pending_actions": get_pending_actions(applicant),
        "documents": get_document_status(applicant.name),
        "deadlines": [],
        "completion": get_completion_percentage(applicant)
    }

def get_campus_status(applicant_name):
    return frappe.get_all(
        "Applicant Campus Preference",
        filters={"applicant": applicant_name},
        fields=[
            "campus", "preference_order", "status",
            "offer_date", "acceptance_deadline", "program"
        ],
        order_by="preference_order asc"
    )

def get_pending_actions(applicant):
    actions = []
    # Check if application is in draft
    if applicant.docstatus == 0:
        actions.append({
            "action": _("Complete Application"),
            "description": _("Your application is not yet submitted"),
            "url": f"/app/applicant/{applicant.name}",
            "type": "warning",
            "icon": "fa fa-edit"
        })
    
    # Check for unverified documents
    unverified_docs = frappe.db.count(
        "Applicant Document",
        {"applicant": applicant.name, "is_verified": 0, "docstatus": 1}
    )
    if unverified_docs:
        actions.append({
            "action": _("Verify Documents"),
            "description": _("{0} document(s) awaiting verification").format(unverified_docs),
            "url": f"/app/applicant-document?applicant={applicant.name}",
            "type": "info",
            "icon": "fa fa-file-text-o"
        })
    
    # Check for offered status in preferences
    offered = frappe.db.exists(
        "Applicant Campus Preference",
        {"applicant": applicant.name, "status": "Offered"}
    )
    if offered:
        actions.append({
            "action": _("Accept Offer"),
            "description": _("You have a pending admission offer. Accept before the deadline."),
            "url": "#applicant-offer-lett",
            "type": "success",
            "icon": "fa fa-check-circle"
        })
    return actions

def get_document_status(applicant_name):
    applicant_doc = frappe.get_doc("Applicant", applicant_name)
    from slcm.admission.utils.documents import get_required_documents
    
    required = get_required_documents(
        applicant_doc.program,
        applicant_doc.whether_scstobc_ncl
    )
    
    uploaded = frappe.get_all(
        "Applicant Document",
        filters={"applicant": applicant_name},
        fields=["document_type", "is_verified", "is_locked"]
    )
    
    uploaded_map = {d.document_type: d for d in uploaded}
    result = []
    
    for doc_type in required:
        uploaded_doc = uploaded_map.get(doc_type)
        result.append({
            "document_type": doc_type,
            "uploaded": bool(uploaded_doc),
            "verified": uploaded_doc.is_verified if uploaded_doc else False,
            "locked": uploaded_doc.is_locked if uploaded_doc else False
        })
    return result

def get_completion_percentage(applicant):
    fields = [
        "candidate_name", "email", "mobile_number",
        "date_of_birth", "gender", "correspondence_address",
        "class_x_percentage", "class_xii_percentage",
        "first_preference", "authorisation_information", 
        "agreement_to_communications", "agreement_withdrawal_conditions",
        "id_proof", "candidate_photo"
    ]
    filled = sum(1 for f in fields if getattr(applicant, f, None))
    return round((filled / len(fields)) * 100)

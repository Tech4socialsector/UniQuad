import frappe
from frappe import _

no_cache = 1

def get_context(context):
    from slcm.admission.utils.portal import get_portal_config
    context.portal_config = get_portal_config()
    
    name = frappe.form_dict.get('name')
    email = frappe.form_dict.get('email')
    mobile = frappe.form_dict.get('mobile')
    
    # If no params, and user is logged in, try to find their application
    if not (name or email or mobile) and frappe.session.user != "Guest":
        email = frappe.session.user

    if not (name or email or mobile):
        context.error = _("Please provide your Application Number, Email, or Mobile Number to track status.")
        return

    filters = {}
    if name:
        filters['name'] = name
    if email:
        filters['email'] = email
    if mobile:
        filters['mobile_number'] = mobile

    applicants = frappe.get_all("Applicant", filters=filters, 
                                fields=["name", "candidate_name", "program", "status", 
                                        "campus", "academic_year", 
                                        "first_preference", "second_preference", "third_preference"],
                                order_by="creation desc")
    
    if not applicants:
        context.error = _("No application found for the provided details.")
        return

    # Use the first applicant object directly
    context.applicant = applicants[0]
    
    # Document Status
    try:
        uploaded_docs = frappe.get_all(
            "Applicant Document",
            filters={"applicant": doc.name},
            fields=["document_type", "document_name", "file", "is_verified", "rejection_reason"],
            ignore_permissions=True
        ) or []
        
        doc_map = {d.document_type: d for d in uploaded_docs}
        required_types = ["10th Certificate", "12th Certificate", "ID Proof", "Photo"]
        
        if doc.intake_type == "External Test":
            required_types.append("CLAT Scorecard")
        elif doc.intake_type == "Internal Test":
            required_types.append("NLSAT Scorecard")
            
        if doc.whether_scstobc_ncl and doc.whether_scstobc_ncl != "NA":
            required_types.append("Category Certificate")
            
        if doc.pwd == "Yes":
            required_types.append("PwD Certificate")
            
        if doc.program_level == "Research Course":
            required_types.append("Research Proposal")
        elif doc.program_level == "PG":
            required_types.append("Degree Certificate")

        context.documents = []
        for dtype in required_types:
            d = doc_map.get(dtype)
            context.documents.append(frappe._dict({
                "document_name": dtype,
                "is_uploaded": bool(d and d.file),
                "verification_status": "Verified" if d and d.is_verified else ("Rejected" if d and d.rejection_reason else ("Uploaded" if d else "Pending"))
            }))
            
        for d in uploaded_docs:
            if d.document_type not in required_types:
                context.documents.append(frappe._dict({
                    "document_name": d.document_name or d.document_type,
                    "is_uploaded": True,
                    "verification_status": "Verified" if d.is_verified else ("Rejected" if d.rejection_reason else "Uploaded")
                }))
    except Exception as e:
        frappe.log_error(f"Admission status document error: {e}")
        context.documents = []

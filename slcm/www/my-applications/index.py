import frappe
from frappe.utils import flt
from slcm.admission.utils.portal import get_portal_config, is_application_editable

from slcm.admission.doctype.eligibility_result.eligibility_result import get_applicant_data
from slcm.admission.web_form.applicant_form.applicant_form import (
    _latest_application_fee_receipt_for_portal,
)

login_required = True

# Portal copy when application is closed / terminal (replaces stage tracker).
_APPLICATION_CLOSED_PORTAL_MESSAGES = {
    "Rejected": (
        "Application Submission – Rejected",
        "Your application has been reviewed and was not selected for further consideration. Thank you for your interest.",
    ),
    "Entrance Test Rejected": (
        "Entrance Test – Rejected",
        "You did not qualify in the entrance test. We appreciate your effort and encourage you to apply again in the future.",
    ),
    "Interview Rejected": (
        "Interview – Rejected",
        "After the interview evaluation, your application was not selected for the next stage. Thank you for your time and participation.",
    ),
    "Seat Rejected": (
        "Seat Allocation – Rejected",
        "We regret to inform you that a seat could not be allocated based on the current selection criteria.",
    ),
    "Offer Declined": (
        "Offer Declined",
        "You have declined the admission offer. If this was unintentional, please contact the admissions office.",
    ),
    "Offer Expired": (
        "Offer Expired",
        "The admission offer has expired as the acceptance deadline has passed.",
    ),
    "Withdrawn": (
        "Application Withdrawn",
        "Your application has been successfully withdrawn as per your request.",
    ),
    "Merit Rejected": (
        "Merit List – Not Selected",
        "We regret to inform you that you have not been selected in the current merit list for the chosen program. Thank you for your interest and we wish you the best in your future endeavors.",
    ),
}

_NEXT_STEPS_DEADLINE_PLACEHOLDER = "Complete all steps before your cycle deadline"


def _clean_status_label(label):
    if not label:
        return ""
    parts = str(label).strip().split(" ", 1)
    if len(parts) > 1:
        return parts[1]
    return label

NEXT_STEPS_IDLE_HINT = (
    "Complete the requirements for your current stage to move forward in the admission process. "
    "Please check this page for updates — our team will share the next steps with you soon."
)


def _next_steps_without_deadline_placeholder(next_steps):
    if not next_steps:
        return []
    out = []
    for s in next_steps:
        t = (s.get("text") if isinstance(s, dict) else getattr(s, "text", None)) or ""
        if t.strip() != _NEXT_STEPS_DEADLINE_PLACEHOLDER:
            out.append(s)
    return out


def _application_closed_portal_message(status, status_type, next_step_note=None):
    """Return {"title", "body"} when the detail view should hide the stage tracker and show a closed panel."""
    app_status = (status or "").strip()
    st_type = (status_type or "").strip()
    if app_status in _APPLICATION_CLOSED_PORTAL_MESSAGES:
        title, fallback_body = _APPLICATION_CLOSED_PORTAL_MESSAGES[app_status]
        return {"title": title, "body": next_step_note if next_step_note else fallback_body}
    if st_type == "Closed" and app_status:
        return {
            "title": app_status,
            "body": next_step_note if next_step_note else "Please contact the admissions office if you have questions about your application.",
        }
    return None


def _set_offer_letter_entries(context):
    """Populate context.offer_letter_entries for list view from Offer Letter doctype."""
    context.offer_letter_entries = []
    try:
        applicant_names = [a.get("name") for a in (context.applications or []) if a.get("name")]
        if not applicant_names:
            applicant_names = [
                r["name"] for r in frappe.get_all(
                    "Applicant",
                    filters={"email": frappe.session.user},
                    fields=["name"],
                    ignore_permissions=True
                )
            ]
        if not applicant_names and frappe.db.exists("Applicant", frappe.session.user):
            applicant_names = [frappe.session.user]
        if applicant_names:
            offers = frappe.get_all(
                "Offer Letter",
                filters={"applicant": ["in", applicant_names]},
                fields=["name", "applicant", "program", "campus", "status", "payable_amount"],
                order_by="creation desc",
                ignore_permissions=True
            )
            for o in offers:
                program_name = frappe.db.get_value("Programme", o.get("program"), "program_name") or o.get("program") or ""
                campus_name = frappe.db.get_value("Campus", o.get("campus"), "campus_name") or o.get("campus") or ""
                context.offer_letter_entries.append({
                    "offer_name": o.get("name"),
                    "applicant_name": o.get("applicant"),
                    "program": o.get("program"),
                    "program_name": program_name,
                    "campus": o.get("campus"),
                    "campus_name": campus_name,
                    "status": o.get("status") or "Issued",
                    "payable_amount": o.get("payable_amount"),
                })
    except Exception:
        context.offer_letter_entries = []

def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/admission/login?redirect=/my-applications"
        raise frappe.Redirect

    context.no_cache     = 1
    context.title        = "My Application"
    context.show_detail  = False
    context.applicant    = None
    context.hide_application_next_steps = False
    context.application_closed_message = None
    context.admission_cycle_end_date_formatted = ""
    context.next_steps_for_display = []
    context.next_steps_idle_hint = NEXT_STEPS_IDLE_HINT
    context.fee_receipt_ready = False

    # ── Tab routing ───────────────────────────────────────────────
    _tab = frappe.request.args.get("tab") if frappe.request else None
    context.show_profile = (_tab == "profile")

    # ── Profile context (always loaded for the sidebar avatar) ───
    _user = frappe.session.user
    _user_doc = frappe.db.get_value("User", _user,
                    ["full_name", "user_image"], as_dict=True) or {}
    context.prof_candidate_name  = _user_doc.get("full_name") or ""
    context.prof_user_image      = _user_doc.get("user_image") or ""

    # Try to load personal details from first Applicant record
    _prof_app = None
    try:
        _prof_apps = frappe.get_all("Applicant",
            filters=[["owner","=",_user]],
            fields=["name","candidate_name","date_of_birth","gender","nationality",
                    "religion","mobile_number","alternate_contact","id_proof",
                    "correspondence_address","city","state","pincode",
                    "status", "intake_type", "whether_scstobc_ncl",
                    "pwd", "program_level"],
            limit=1, order_by="creation desc")
        if not _prof_apps:
            _prof_apps = frappe.get_all("Applicant",
                filters=[["email","=",_user]],
                fields=["name","candidate_name","date_of_birth","gender","nationality",
                        "religion","mobile_number","alternate_contact","id_proof",
                        "correspondence_address","city","state","pincode",
                        "status", "intake_type", "whether_scstobc_ncl",
                        "pwd", "program_level"],
                limit=1, order_by="creation desc")
        if _prof_apps:
            _prof_app = _prof_apps[0]
    except Exception:
        pass

    if _prof_app:
        context.prof_candidate_name  = _prof_app.candidate_name or context.prof_candidate_name
        context.prof_dob             = _prof_app.date_of_birth
        context.prof_gender          = _prof_app.gender
        context.prof_nationality     = _prof_app.nationality
        context.prof_religion        = _prof_app.religion
        context.prof_mobile          = _prof_app.mobile_number
        context.prof_alternate_contact = _prof_app.alternate_contact
        context.prof_id_proof        = _prof_app.id_proof
        context.prof_address         = _prof_app.correspondence_address
        context.prof_city            = _prof_app.city
        context.prof_state           = _prof_app.state
        context.prof_pincode         = _prof_app.pincode
        context.prof_app_status      = _prof_app.status
        context.prof_app_name        = _prof_app.name
    else:
        context.prof_dob             = None
        context.prof_gender          = None
        context.prof_nationality     = None
        context.prof_religion        = None
        context.prof_mobile          = None
        context.prof_alternate_contact = None
        context.prof_id_proof        = None
        context.prof_address         = None
        context.prof_city            = None
        context.prof_state           = None
        context.prof_pincode         = None
        context.prof_app_status      = None
        context.prof_app_name        = None

    # ── Detail mode: if ?app= param provided, load that specific application ──
    _app_name = frappe.form_dict.get("app") or ""

    # ── Auto-open application from ?program= param (from admission cards) ──
    program_filter = frappe.form_dict.get("program") or ""
    context.program_filter = program_filter

    if not _app_name and program_filter:
        _found = frappe.db.sql("""
            SELECT a.name FROM `tabApplicant` a
            JOIN `tabProgramme` p ON a.program = p.name
            WHERE (a.owner = %s OR a.email = %s) AND (p.program_slug = %s OR p.name = %s)
            LIMIT 1
        """, (frappe.session.user, frappe.session.user, program_filter, program_filter))
        if _found:
            _app_name = _found[0][0]

    # ── Determine active application name for document checklist ──
    doc_lookup_name = _app_name or context.prof_app_name

    # ── Documents Logic (Strictly using Applicant fields) ──────────
    context.app_documents = []
    if doc_lookup_name:
        try:
            # Fetch the actual applicant doc for fields
            target_applicant = frappe.get_doc("Applicant", doc_lookup_name, ignore_permissions=True)

            # Standard fields in Applicant DocType
            standard_checklist = [
                {"label": "10th Certificate", "field": "class_x_marksheet", "required": True, "accept": ".pdf,.jpg,.jpeg,.png", "max_size_mb": 5},
                {"label": "12th Certificate", "field": "class_xii_marksheet", "required": True, "accept": ".pdf,.jpg,.jpeg,.png", "max_size_mb": 5},
                {"label": "ID Proof", "field": "id_proof", "required": True, "accept": ".pdf,.jpg,.jpeg,.png", "max_size_mb": 5},
                {"label": "Photo", "field": "candidate_photo", "required": True, "accept": ".jpg,.jpeg,.png", "max_size_mb": 1},
                {"label": "CV", "field": "cv", "required": True, "accept": ".doc,.docx,.pdf", "max_size_mb": 5},
            ]

            # Optional / Conditional fields
            if target_applicant.whether_scstobc_ncl and target_applicant.whether_scstobc_ncl not in ["NA", "General"]:
                standard_checklist.append({"label": "Category Certificate", "field": "caste_certificate", "required": True, "accept": ".jpg,.jpeg,.png", "max_size_mb": 5})
                
            if target_applicant.pwd == "Yes":
                standard_checklist.append({"label": "PwD Certificate", "field": "pwd_certificate", "required": True, "accept": ".jpg,.jpeg,.png", "max_size_mb": 5})
                
            if target_applicant.program_level == "Research Course":
                standard_checklist.append({"label": "Research Proposal", "field": "phd_proposal", "required": True, "accept": ".pdf,.jpg,.jpeg,.png", "max_size_mb": 5})
            
            # Special case for Karnataka category
            if getattr(target_applicant, "ka_study_7yrs", 0):
                standard_checklist.append({"label": "Karnataka Study Certificate", "field": "ka_study_7yrs_certificate", "required": True, "accept": ".jpg,.jpeg,.png", "max_size_mb": 5})
            if getattr(target_applicant, "ka_defence_child", 0):
                standard_checklist.append({"label": "Karnataka Defence Child Certificate", "field": "ka_defence_child_certificate", "required": True, "accept": ".jpg,.jpeg,.png", "max_size_mb": 5})
            if getattr(target_applicant, "ka_govt_child", 0):
                standard_checklist.append({"label": "Karnataka Govt Child Certificate", "field": "ka_govt_child_certificate", "required": True, "accept": ".jpg,.jpeg,.png", "max_size_mb": 5})
            if getattr(target_applicant, "ka_ais_child", 0):
                standard_checklist.append({"label": "Karnataka AIS Child Certificate", "field": "ka_ais_child_certificate", "required": True, "accept": ".jpg,.jpeg,.png", "max_size_mb": 5})
            if getattr(target_applicant, "ka_capf_child", 0):
                standard_checklist.append({"label": "Karnataka CAPF Child Certificate", "field": "ka_capf_child_certificate", "required": True, "accept": ".jpg,.jpeg,.png", "max_size_mb": 5})

            for item in standard_checklist:
                field = item["field"]
                val = target_applicant.get(field)
                
                context.app_documents.append({
                    "document_name": item["label"],
                    "document_type": item["label"],
                    "is_uploaded": bool(val),
                    "file_url": val,
                    "field": field,
                    "doc_name": "",
                    "source": "field",
                    "required": item["required"],
                    "accept": item.get("accept", ".pdf,.jpg,.jpeg,.png"),
                    "max_size_mb": item.get("max_size_mb", 5)
                })

            # Child tables
            if target_applicant.program_level in ["Postgraduate", "Research Course"]:
                for row in target_applicant.get("ug_degree_details", []):
                    context.app_documents.append({
                        "document_name": f"UG Certificate ({row.ug_program or 'Degree'})",
                        "document_type": "UG degree certificate / Bonafide",
                        "is_uploaded": bool(row.degree_certificate),
                        "file_url": row.degree_certificate,
                        "field": "degree_certificate",
                        "doc_name": row.name,
                        "source": "UG Degree Detail",
                        "required": True,
                        "accept": ".pdf,.jpg,.jpeg,.png",
                        "max_size_mb": 5
                    })
                    context.app_documents.append({
                        "document_name": f"UG Marksheets ({row.ug_program or 'Degree'})",
                        "document_type": "Transcripts / Marksheets",
                        "is_uploaded": bool(row.marksheets),
                        "file_url": row.marksheets,
                        "field": "marksheets",
                        "doc_name": row.name,
                        "source": "UG Degree Detail",
                        "required": True,
                        "accept": ".pdf,.jpg,.jpeg,.png",
                        "max_size_mb": 5
                    })

            if target_applicant.program_level == "Research Course":
                for row in target_applicant.get("pg_degree_details", []):
                    context.app_documents.append({
                        "document_name": f"PG Certificate ({row.pg_program or 'Degree'})",
                        "document_type": "PG degree certificate / Bonafide",
                        "is_uploaded": bool(row.pg_degree_certificatebonafide_certificate_to_be_uploaded),
                        "file_url": row.pg_degree_certificatebonafide_certificate_to_be_uploaded,
                        "field": "pg_degree_certificatebonafide_certificate_to_be_uploaded",
                        "doc_name": row.name,
                        "source": "PG Degree Details",
                        "required": True,
                        "accept": ".pdf,.jpg,.jpeg,.png",
                        "max_size_mb": 5
                    })
                    context.app_documents.append({
                        "document_name": f"PG Marksheets ({row.pg_program or 'Degree'})",
                        "document_type": "Transcripts / Marksheets",
                        "is_uploaded": bool(row.transcriptsmarksheets_to_be_uploaded),
                        "file_url": row.transcriptsmarksheets_to_be_uploaded,
                        "field": "transcriptsmarksheets_to_be_uploaded",
                        "doc_name": row.name,
                        "source": "PG Degree Details",
                        "required": True,
                        "accept": ".pdf,.jpg,.jpeg,.png",
                        "max_size_mb": 5
                    })
        except Exception as e:
            frappe.log_error(f"Document checklist error: {e}")

    # ── Portal config (required for theme vars) ──────────────────
    try:
        portal_config = get_portal_config()
        context.portal_config = portal_config
    except Exception:
        portal_config = None
        context.portal_config = None

    if context.show_profile:
        # ── States and Districts ─────────────────────────────────────────
        try:
            context.states = frappe.get_all("State", fields=["name"], order_by="name asc")
            if context.prof_state:
                context.districts = frappe.get_all("District", 
                    filters={"state": context.prof_state},
                    fields=["name"], order_by="name asc")
            else:
                context.districts = []
        except Exception:
            context.states = []
            context.districts = []
        return

    if _app_name:
        # Security: verify ownership
        try:
            applicant = frappe.get_doc("Applicant", _app_name, ignore_permissions=True)
        except frappe.DoesNotExistError:
            context.app_not_found = True
            context.selected_app = None
            return

        # Check access
        _session_user = frappe.session.user
        if applicant.owner != _session_user and applicant.email != _session_user and \
           "Admission Admin" not in frappe.get_roles():
            context.access_denied = True
            context.selected_app = None
            return

        context.selected_app = applicant
        # Ensure program_name is available on applicant object so Jinja can read it
        applicant.program_name = frappe.db.get_value("Programme", applicant.program, "program_name") or applicant.program
        context.is_editable = is_application_editable(applicant)

        # ── Fetch Eligibility Evaluation for exemptions ─────────────
        evaluation = frappe.db.get_value("Eligibility Evaluation", 
            {"applicant_name": applicant.name}, 
            ["exempts_entrance_test", "exempts_interview"], 
            as_dict=True) or {}
        context.evaluation_exemption = evaluation

        # ── Stage tracker ──────────────────────────────────────────────
        stages_with_state = []
        context.cycle_next_step_message = ""
        context.process_completed_message = ""
        try:
            # 1. Get Admission Cycle Doc to check enabled stages
            # ── Use active cycle for stage configuration (per requirement) ──
            active_cycle_name = frappe.db.get_value("Admission Cycle", {"status": "Active"}, "name")
            cycle_name_to_use = active_cycle_name if active_cycle_name else applicant.admission_cycle

            # Post–offer admission fee: paid if offer accepted / payment completed or submitted receipt exists
            admission_fee_paid = False
            try:
                _off_row = frappe.get_all(
                    "Offer Letter",
                    filters={"applicant": applicant.name},
                    fields=["status"],
                    order_by="creation desc",
                    limit=1,
                    ignore_permissions=True,
                )
                if _off_row and (_off_row[0].get("status") or "") in (
                    "Accepted",
                    "Payment Completed",
                ):
                    admission_fee_paid = True
                if not admission_fee_paid:
                    admission_fee_paid = bool(
                        frappe.db.exists(
                            "Applicant Payment Receipt",
                            {"applicant": applicant.name, "docstatus": ["<", 2]},
                        )
                    )
            except Exception:
                admission_fee_paid = False
            
            if cycle_name_to_use:
                cycle_doc = frappe.get_doc("Admission Cycle", cycle_name_to_use, ignore_permissions=True)
                context.process_completed_message = (cycle_doc.get("process_completed_message") or "").strip()
                
            enabled_stages = []
            if applicant.program:
                program_doc = frappe.get_doc("Programme", applicant.program, ignore_permissions=True)
                
                # Check if the applicant is international (foriegn_national == "Yes")
                if applicant.get("foriegn_national") == "Yes":
                    POTENTIAL_STAGES = [
                        {"field": "internationa_application_submitted", "name": "Submitted", "stage_type": "Application"},
                        {"field": "international_entrance_test",       "name": "Entrance Test", "stage_type": "Entrance Test"},
                        {"field": "international_interview",           "name": "Interview", "stage_type": "Interview"},
                        {"field": "international_offer_letter",        "name": "Offer Letter", "stage_type": "Offer Letter"},
                        {"field": "inrternation_admission_fee",        "name": "Admission Fee", "stage_type": "Admission Fee"},
                        {"field": "international_enrolled",            "name": "Enrollment", "stage_type": "Enrollment"},
                    ]
                else:
                    # Potential stages mapping based on checkboxes in Program
                    # Using 'intereview' as per the doctype field name (note the typo)
                    POTENTIAL_STAGES = [
                        {"field": "submitted",       "name": "Submitted", "stage_type": "Application"},
                        {"field": "entrance_test",   "name": "Entrance Test",         "stage_type": "Entrance Test"},
                        {"field": "intereview",      "name": "Interview",             "stage_type": "Interview"},
                        {"field": "merit_list",      "name": "Merit",                 "stage_type": "Merit"},
                        {"field": "seat_allocation", "name": "Seat Allocation",       "stage_type": "Seat Allocation"},
                        {"field": "offer_letter",    "name": "Offer Letter",          "stage_type": "Offer Letter"},
                        {"field": "admission_fee",   "name": "Admission Fee",         "stage_type": "Admission Fee"},
                        {"field": "enrolled",        "name": "Enrollment",            "stage_type": "Enrollment"},
                    ]
                
                enabled_stages = [ps for ps in POTENTIAL_STAGES if program_doc.get(ps["field"])]
                
            # 2. Get current status info from Applicant Status doctype
            status_info = frappe.db.get_value("Applicant Status", 
                applicant.status, 
                ["stage_type", "status_type", "next_step_note"], 
                as_dict=True) or {}
            
            current_stage_type = status_info.get("stage_type")
            current_status_type = status_info.get("status_type")
            
            if status_info.get("next_step_note"):
                context.cycle_next_step_message = status_info.get("next_step_note")
            
            # 3. Determine active index
            active_index = -1
            for i, s in enumerate(enabled_stages):
                if s["stage_type"] == current_stage_type:
                    active_index = i
                    break
            
            # 4. Build stages with state
            for i, s in enumerate(enabled_stages):
                state = "pending"
                if active_index != -1:
                    if i < active_index:
                        state = "completed"
                    elif i == active_index:
                        if current_status_type == "Completed":
                            state = "completed"
                        elif current_status_type == "Closed":
                            state = "closed"
                        else:
                            state = "active"
                
                is_exempted = False
                if s["stage_type"] == "Entrance Test" and evaluation.get("exempts_entrance_test"):
                    is_exempted = True
                elif s["stage_type"] == "Interview" and evaluation.get("exempts_interview"):
                    is_exempted = True

                # Logic for display names:
                # Line 1 (primary): Stage Name
                # Line 2 (subtext): Status Name if active or closed
                
                stage_name = s["name"]
                status_label = ""
                if state in ["active", "closed"]:
                    status_label = _clean_status_label(applicant.status)

                if s["stage_type"] == "Admission Fee" and admission_fee_paid and state in (
                    "completed",
                    "active",
                ):
                    status_label = "Paid"

                stages_with_state.append({
                    "name": stage_name,
                    "display_name": stage_name,
                    "status_label": status_label,
                    "state": state,
                    "is_exempted": is_exempted,
                    "stage_type": s["stage_type"],
                })
        except Exception as e:
            frappe.log_error(f"Stage tracker context error: {e}")

        if not stages_with_state:
            # Fallback based on common statuses
            statuses = [
                {"name": "Submitted", "activate": "Submitted", "closed": "Rejected"},
                {"name": "Review", "activate": "Under Review", "closed": "Rejected"},
                {"name": "Interview", "activate": "Interview Scheduled", "closed": "Interview Rejected"},
                {"name": "Decision", "activate": "Selected", "closed": "Rejected"}
            ]
            current = applicant.get("status") or "Draft"
            stop_found = False
            for st in statuses:
                state = "pending"
                if not stop_found:
                    if st["activate"] == current:
                        state = "active"
                        stop_found = True
                    elif st["closed"] == current:
                        state = "closed"
                        stop_found = True
                    else:
                        state = "completed"

                status_label = ""
                if  state in ["active", "closed"]:
                    status_label = _clean_status_label(current)

                stages_with_state.append({
                    "name": st["name"],
                    "display_name": st["name"],
                    "status_label": status_label,
                    "state": state
                })

        context.stage_tracker = stages_with_state

        # ── Next steps ─────────────────────────────────────────────
        _portal_app_status = applicant.get("status") or "Draft"
        try:
            _pc = frappe.get_doc("Applicant Portal Config")
            _next_steps = []
            if _pc:
                all_steps = (_pc.get("stage_next_steps") or [])
                for step in all_steps:
                    sn = (step.get("stage_name") if hasattr(step,"get") else step.stage_name) or ""
                    if sn.lower() == str(_portal_app_status).lower():
                        _next_steps.append({
                            "text":       (step.get("step_text") if hasattr(step,"get") else step.step_text) or "",
                            "is_link":    (step.get("is_link") if hasattr(step,"get") else step.is_link) or 0,
                            "link_url":   (step.get("link_url") if hasattr(step,"get") else step.link_url) or "",
                            "link_label": (step.get("link_label") if hasattr(step,"get") else step.link_label) or "",
                        })
            if not _next_steps:
                _next_steps = [{"text": _NEXT_STEPS_DEADLINE_PLACEHOLDER, "is_link": 0}]
            context.next_steps = _next_steps
            context.support_name  = _pc.get("support_name") or ""
            context.support_role  = _pc.get("support_role") or ""
            context.support_email = _pc.get("support_email") or ""
            context.campus_image  = _pc.get("hero_image") or ""
        except Exception as ex:
            frappe.log_error(str(ex), "my_applications detail context next steps")

        try:
            _cycle_end = frappe.db.get_value(
                "Admission Cycle",
                {"status": "Active"},
                "cycle_end_date",
            )
            if _cycle_end:
                context.admission_cycle_end_date_formatted = frappe.utils.format_date(
                    _cycle_end, "MMMM d, yyyy"
                )
        except Exception:
            pass

        context.app_narrative = applicant.get("remarks") or ""
        context.submission_date = frappe.utils.format_date(applicant.creation, "MMMM d, yyyy")
        context.app_name_param = _app_name

        from slcm.admission.utils.portal import build_existing_applicant_portal_url

        context.applicant_portal_open_url = build_existing_applicant_portal_url(
            _app_name,
            applicant.admission_cycle,
            edit=context.is_editable,
        )

        # --- Fetch Offer Letter for this applicant ---
        offer_letter = frappe.get_all("Offer Letter", 
            filters={"applicant": applicant.name},
            fields=["name", "status"],
            order_by="creation desc",
            limit=1,
            ignore_permissions=True
        )
        if offer_letter:
            context.offer_name = offer_letter[0].name
            context.status = offer_letter[0].status
        else:
            context.offer_name = ""
            context.status = ""

        # --- Fetch Payment Details for Cancellation Button ---
        context.payment_details = None
        cancellations = frappe.get_all("Admission Cancellation", 
            filters={"applicant": applicant.name, "status": ["not in", ["Rejected"]]},
            fields=["name", "status", "requested_on", "cancellation_reason", "refund_request", "applicant_payment_receipt", "amount_paid"],
            order_by="creation asc"
        )
        if cancellations:
             context.has_cancellation = True
             
             # Fetch all linked Refund Requests for this applicant
             refund_requests = frappe.get_all(
                 "Refund Request",
                 filters={"applicant": applicant.name, "status": ["not in", ["Rejected"]]},
                 fields=["name", "refund_amount", "amount_paid", "refund_date", "status", "applicant_payment_receipt", "applicant_fee_assignment", "refund_type", "admission_cancellation"],
                 order_by="creation asc"
             )
             
             from slcm.admission.utils.refund import get_applicant_refund_policies
             res_ref = get_applicant_refund_policies(applicant.name)
             is_conf_ref = bool(res_ref.get("is_confirmation_fee_refundable", False))
             conf_pct = flt(res_ref.get("confirmation_fee_refund_percentage") or 0.0) if is_conf_ref else 0.0

             total_ref = 0.0
             filtered_refund_requests = []
             for rr in refund_requests:
                 fee_type = "Admission Fee"
                 if rr.get("applicant_fee_assignment"):
                     fee_type = frappe.db.get_value("Applicant Fee Assignment", rr.applicant_fee_assignment, "fee_type") or fee_type
                 elif rr.get("applicant_payment_receipt"):
                     apr_ft = frappe.db.get_value("Applicant Payment Receipt", rr.applicant_payment_receipt, "fee_type")
                     if apr_ft:
                         if "Confirmation" in apr_ft:
                             fee_type = "Confirmation Fee"
                         elif "Admission" in apr_ft:
                             fee_type = "Admission Fee"
                         else:
                             fee_type = apr_ft

                 # Ignore Application/Form Fee receipts
                 if "Application" in fee_type or "Form" in fee_type:
                     continue

                 rr["fee_type"] = fee_type

                 amt_p = flt(rr.amount_paid)
                 if fee_type == "Confirmation Fee":
                     if not is_conf_ref or conf_pct <= 0:
                         continue
                     rr["refund_percentage"] = conf_pct
                     rr["refund_amount"] = round(amt_p * (conf_pct / 100.0), 2)
                 else:
                     amt_r = flt(rr.refund_amount)
                     rr["refund_percentage"] = round((amt_r / amt_p * 100), 1) if amt_p > 0 else 0
                 
                 total_ref += flt(rr["refund_amount"])
                 filtered_refund_requests.append(rr)

             refund_requests = filtered_refund_requests


             first_canc = cancellations[0]

             # Determine overall aggregate withdrawal status across all active refund requests/cancellations
             rr_statuses = [rr.get("status") for rr in refund_requests] if refund_requests else [c.get("status") for c in cancellations]
             if rr_statuses and all(s in ["Processed", "Completed"] for s in rr_statuses):
                 overall_status = "Completed"
             elif any(s in ["Under Review", "Initiated"] for s in rr_statuses):
                 overall_status = "Under Review"
             elif any(s in ["Approved", "Processing"] for s in rr_statuses):
                 overall_status = "Approved"
             else:
                 overall_status = first_canc.status

             context.cancellation_details = {
                 "name": ", ".join(c.name for c in cancellations),
                 "cancellations": cancellations,
                 "status": overall_status,
                 "requested_on": first_canc.requested_on,
                 "refund_requests": refund_requests,
                 "total_refund_amount": total_ref,
                 "refund_amount": total_ref
             }
        else:
             context.cancellation_details = None
             context.has_cancellation = False

        
        # Check for withdrawal/refund eligibility if no existing cancellation request
        context.show_withdraw_button = False
        if not context.has_cancellation:
            # We fetch the latest active Offer Letter.
            _off_name = frappe.db.get_value("Offer Letter", 
                {"applicant": applicant.name, "status": ["not in", ["Rejected", "Withdrawn", "Expired"]]}, 
                "name", order_by="creation desc")
            context.offer_name = _off_name or ""

            _is_full_fee = applicant.status in ["Enrolled", "Full Fee Paid"] or context.status in ["Full Fee Paid", "Payment Completed"]

            # Withdrawal depends on an active Offer Letter and being in Enrolled/Full Fee Paid status
            if context.offer_name and _is_full_fee:
                context.show_withdraw_button = True
                
                # 1. Try finding Student-linked Fee Payment
                student_name = frappe.db.get_value("Student Master", {"application_number": applicant.name}, "name")
                if student_name:
                    payment_name = frappe.db.get_value("Fee Payment", {
                        "student": student_name,
                        "status": "Submitted"
                    }, "name")
                    if payment_name:
                        context.payment_details = frappe.db.get_value("Fee Payment", payment_name, ["name", "amount", "payment_date"], as_dict=True)

                # 2. Fallback to Applicant Payment Receipt
                if not context.payment_details:
                    receipts = frappe.get_all("Applicant Payment Receipt",
                        filters={"offer_letter": context.offer_name, "docstatus": ["<", 2]},
                        fields=["name", "total_amount as amount", "payment_date", "fee_type"],
                        order_by="creation desc")
                    if receipts:
                        context.payment_details = receipts[0]
                        context.payment_receipt = receipts[0].name
                        context.all_receipts = receipts
            else:
                context.payment_details = None
                context.all_receipts = []
        else:
            context.payment_details = None
            context.all_receipts = []

        # --- Confirmation Fee Refund state (for portal header button) ---
        # Show "Refund Confirmation Fee" button ONLY when status is "Confirmation Fee Paid"
        # and full fee is NOT paid yet, and no active cancellation/withdrawal or active RR exists.
        context.show_conf_fee_refund_btn = False
        context.conf_fee_refund_rr = None   # name of active Confirmation Fee Refund Request
        try:
            _is_conf_fee_status = (applicant.status == "Confirmation Fee Paid" or context.status == "Confirmation Fee Paid")
            _is_full_fee_status = (applicant.status in ["Enrolled", "Full Fee Paid"] or context.status in ["Full Fee Paid", "Payment Completed"])
            
            if context.offer_name and _is_conf_fee_status and not _is_full_fee_status and not context.has_cancellation:
                # Check for an active (non-Rejected / non-Failed) Confirmation Fee RR
                _existing_cf_rr = frappe.db.sql("""
                    SELECT rr.name, rr.status, rr.refund_amount
                    FROM `tabRefund Request` rr
                    JOIN `tabApplicant Fee Assignment` afa
                      ON afa.name = rr.applicant_fee_assignment
                    WHERE rr.applicant = %(applicant)s
                      AND afa.offer_letter = %(offer)s
                      AND afa.fee_type = 'Confirmation Fee'
                      AND rr.status NOT IN ('Rejected', 'Failed')
                    LIMIT 1
                """, {"applicant": applicant.name, "offer": context.offer_name}, as_dict=True)

                if _existing_cf_rr:
                    context.conf_fee_refund_rr = _existing_cf_rr[0]
                else:
                    # Only show the refund button if there's a paid Confirmation Fee AFA
                    _conf_afa_paid = frappe.db.exists(
                        "Applicant Fee Assignment",
                        {
                            "offer_letter": context.offer_name,
                            "fee_type": "Confirmation Fee",
                            "status": "Paid",
                            "docstatus": ["!=", 2],
                        }
                    )
                    if _conf_afa_paid:
                        # Check if confirmation fee is marked refundable in Fee Structure
                        from slcm.admission.utils.refund import get_applicant_refund_policies
                        res_ref = get_applicant_refund_policies(applicant.name)
                        if res_ref.get("is_confirmation_fee_refundable", False):
                            context.show_conf_fee_refund_btn = True

        except Exception as _cf_exc:
            frappe.log_error(str(_cf_exc), "my_applications conf_fee_refund context")



        # Combined results
        context.all_results = []
        context.all_merit   = []
        try:
            combined_data = get_applicant_data()
            if isinstance(combined_data, list):
                for entry in combined_data:
                    if entry.get("profile", {}).get("applicant_id") == _app_name:
                        context.all_results = entry.get("results") or []
                        context.all_merit   = entry.get("merit") or []
                        context.eligibility_result = entry.get("profile")
                        break
        except Exception: pass

        # Merit (fallback): pull from published Merit List if applicant_results pipeline didn't return it
        context.merit_list_published_date = ""
        context.merit_total_applicants = 0
        try:
            _need_merit = True
            if context.all_merit and isinstance(context.all_merit, list):
                m0 = context.all_merit[0] if context.all_merit else {}
                if (m0.get("overall_rank") if hasattr(m0, "get") else getattr(m0, "overall_rank", None)) or \
                   (m0.get("total_score") if hasattr(m0, "get") else getattr(m0, "total_score", None)):
                    _need_merit = False

            if _need_merit:
                ml_rows = frappe.get_all(
                    "Merit List",
                    filters={
                        "status": "Published",
                        "admission_cycle": applicant.admission_cycle,
                        "campus": applicant.campus,
                        "program_level": applicant.program_level or None,
                    },
                    fields=["name", "modified"],
                    order_by="modified desc",
                    limit=1,
                    ignore_permissions=True,
                )
                if ml_rows:
                    ml = frappe.get_doc("Merit List", ml_rows[0].name, ignore_permissions=True)
                    # Store published date & total count
                    _pub_date = ml.get("published_on") or ml_rows[0].get("modified")
                    context.merit_list_published_date = frappe.utils.format_datetime(
                        _pub_date, "d MMMM yyyy, hh:mm a"
                    ) if _pub_date else ""
                    context.merit_total_applicants = len(ml.merit_applicants or [])
                    row = next((r for r in (ml.merit_applicants or []) if r.applicant_id == _app_name), None)
                    if row:
                        context.all_merit = [{
                            "overall_rank": row.overall_rank,
                            "total_score": row.total_score,
                            "status": row.status,
                            "program_rank": row.program_rank,
                        }]
            else:
                # Merit already populated — try to fetch the published date from the Merit List
                try:
                    _ml_date_row = frappe.get_all(
                        "Merit List",
                        filters={
                            "status": "Published",
                            "admission_cycle": applicant.admission_cycle,
                            "campus": applicant.campus,
                            "program_level": applicant.program_level or None,
                        },
                        fields=["name", "modified"],
                        order_by="modified desc",
                        limit=1,
                        ignore_permissions=True,
                    )
                    if _ml_date_row:
                        _ml_doc_tmp = frappe.get_doc("Merit List", _ml_date_row[0].name, ignore_permissions=True)
                        _pub_date = _ml_doc_tmp.get("published_on") or _ml_date_row[0].get("modified")
                        context.merit_list_published_date = frappe.utils.format_datetime(
                            _pub_date, "d MMMM yyyy, hh:mm a"
                        ) if _pub_date else ""
                        context.merit_total_applicants = len(_ml_doc_tmp.merit_applicants or [])
                except Exception:
                    pass
        except Exception as ex:
            frappe.log_error(str(ex), "my_applications merit list fallback")

        context.fee_payment_status = applicant.get("application_fee_status") or ""
        context.fee_receipt_ready = False
        if (context.fee_payment_status or "").strip() == "Paid":
            context.fee_receipt_ready = bool(_latest_application_fee_receipt_for_portal(_app_name))

        # Interview
        context.interview_status = ""
        context.interview_date = ""
        try:
            irows = frappe.get_all("Interview Seat Allocation",
                filters={"applicant": _app_name},
                fields=["interview_date", "interview_time", "interview_slot_status", "re_interview_date", "is_rescheduled"],
                order_by="creation desc", limit=1, ignore_permissions=True)
            if irows:
                ir = irows[0]
                context.interview_status = ir.get("interview_slot_status") or "Scheduled"
                _idate = ir.get("re_interview_date") if (ir.get("is_rescheduled") or ir.get("interview_slot_status") == "Rescheduled") else ir.get("interview_date")
                if _idate:
                    context.interview_date = frappe.utils.format_date(_idate, "d MMM yyyy")
        except Exception: pass
        
        context.is_interview_enabled = any(s.get("stage_type") == "Interview" for s in enabled_stages)

        # Merit
        context.merit_rank = ""
        try:
            mrows = frappe.get_all("Applicant Merit", filters={"applicant": _app_name},
                fields=["overall_rank"], limit=1, ignore_permissions=True)
            if mrows: context.merit_rank = str(mrows[0].get("overall_rank") or "")
        except Exception: pass

        # Seat
        context.seat_status = ""
        try:
            srows = frappe.get_all("Seat Allocation", filters={"applicant": _app_name},
                fields=["status"], limit=1, ignore_permissions=True)
            if srows: context.seat_status = (srows[0].get("status") or "").strip()
        except Exception: pass

        # Entrance test
        try:
            et_rows = frappe.get_all("Entrance Test Seat Allocation",
                filters={"applicant": _app_name},
                fields=["name"],
                order_by="creation desc",
                limit=1,
                ignore_permissions=True)
            if et_rows:
                et_doc = frappe.get_doc("Entrance Test Seat Allocation", et_rows[0].name, ignore_permissions=True)
                context.et_doc = et_doc
                context.et_is_rescheduled = (et_doc.is_rescheduled == 1 or et_doc.entrance_test_status == "Rescheduled")
                context.et_show_result = (et_doc.entrance_test_status in ["Attended", "Absent"] and et_doc.result_published == 1)
                
                context.et_preferences = []
                prefs = et_doc.re_assigned_preferences if context.et_is_rescheduled else et_doc.assigned_preferences
                for p in prefs:
                    provider_info = frappe.db.get_value("Entrance Test Provider", p.provider, ["center_name", "center_address", "location", "pwd_accessible"], as_dict=True) or {}
                    context.et_preferences.append({
                        "provider": p.provider,
                        "center_name": provider_info.get("center_name") or p.center_name,
                        "center_address": provider_info.get("center_address") or p.center_address,
                        "location": provider_info.get("location"),
                        "pwd_accessible": provider_info.get("pwd_accessible")
                    })
                
                context.et_is_pwd = getattr(applicant, "pwd", None) == "Yes"
                
                # Fetch latest details for the currently allocated center
                current_provider = et_doc.re_entrance_test_provider if context.et_is_rescheduled else et_doc.entrance_test_provider
                if current_provider:
                    current_provider_info = frappe.db.get_value("Entrance Test Provider", current_provider, ["location", "center_address", "center_name"], as_dict=True) or {}
                    context.et_location = current_provider_info.get("location")
                    context.et_center_address = current_provider_info.get("center_address")
                    context.et_center_name = current_provider_info.get("center_name")
                
                context.et_doc_json = frappe.as_json(et_doc.as_dict())
                
                # Add branding and reporting time
                campus_branding = {"campus_name": et_doc.campus or "Institution of Legal Education", "logo": None}
                try:
                    if et_doc.campus:
                        campus = frappe.get_doc("Campus", et_doc.campus)
                        campus_branding["campus_name"] = campus.campus_name or et_doc.campus
                        campus_branding["logo"] = campus.logo
                except: pass
                context.et_campus_branding = campus_branding

                # Reporting time & Test time calculation (45 minutes before start time)
                from slcm.admission.utils.portal import get_entrance_test_times
                test_time_str, rep_time_str = get_entrance_test_times(et_doc)
                context.et_test_time = test_time_str
                context.et_reporting_time = rep_time_str
        except Exception: pass

        # Interview details
        try:
            i_rows = frappe.get_all("Interview Seat Allocation",
                filters={"applicant": _app_name},
                fields=["name"],
                order_by="creation desc",
                limit=1,
                ignore_permissions=True)
            if i_rows:
                i_doc = frappe.get_doc("Interview Seat Allocation", i_rows[0].name, ignore_permissions=True)
                context.interview_doc = i_doc
                context.interview_is_rescheduled = (i_doc.is_rescheduled == 1 or i_doc.interview_slot_status == "Rescheduled")
                context.interview_show_result = (i_doc.interview_status in ["Attended", "Absent", "Selected", "Rejected"] and i_doc.result_published == 1)
                
                # Show feedback section if results are published
                context.interview_show_feedback = bool(i_doc.result_published)
                context.interview_feedback_submitted = bool(i_doc.feedback)
                
                # Current slot details for display
                is_re = context.interview_is_rescheduled
                f_date = i_doc.re_interview_date if is_re else i_doc.interview_date
                f_time = i_doc.re_interview_time if is_re else i_doc.interview_time
                staff_name = i_doc.re_staff_name if is_re else i_doc.staff_name
                
                # Format time for display
                formatted_time = "—"
                if f_date and f_time:
                    try:
                        formatted_time = frappe.utils.format_datetime(f"{f_date} {f_time}", "hh:mm a")
                    except:
                        formatted_time = f_time

                # Calculate reporting time (1 hour before)
                reporting_time = "—"
                if f_date and f_time:
                    try:
                        from frappe.utils import get_datetime
                        from datetime import timedelta
                        dt = get_datetime(f"{f_date} {f_time}")
                        rep_dt = dt - timedelta(hours=1)
                        reporting_time = frappe.utils.format_datetime(rep_dt, "hh:mm a")
                    except: pass

                interview_location = None
                if staff_name:
                    interview_location = frappe.db.get_value("Interview Staff Member", staff_name, "interview_location")

                context.interview_current_slot = {
                    "staff_name": staff_name,
                    "interview_location": interview_location,
                    "interview_date": frappe.utils.format_date(f_date, "d MMM yyyy") if f_date else "—",
                    "interview_time": formatted_time,
                    "reporting_time": reporting_time,
                    "interview_address": i_doc.re_interview_address if is_re else i_doc.interview_address,
                    "attendance_confirmation": i_doc.re_interview_attendance_confirmation if is_re else i_doc.interview_attendance_confirmation
                }
                context.interview_attendance_options = ["Confirm Attendance", "Decline Interview Invitation", "Request Rescheduling"]
        except Exception: pass

        _closed_meta = frappe.db.get_value(
            "Applicant Status",
            applicant.status,
            ["status_type", "next_step_note"],
            as_dict=True,
        ) or {}
        context.application_closed_message = _application_closed_portal_message(
            applicant.status,
            _closed_meta.get("status_type"),
            _closed_meta.get("next_step_note")
        )
        if context.application_closed_message:
            context.cycle_next_step_message = ""
            context.next_steps = []

        # Hide sidebar only when admission cancellation is completed (refund workflow).
        # Closed / rejected applicants still see "Application Progress End" with portal copy.
        hide_next = False
        _cd = context.get("cancellation_details")
        if _cd:
            _cstat = _cd.get("status") if hasattr(_cd, "get") else getattr(_cd, "status", None)
            if (_cstat or "") == "Completed":
                hide_next = True
        context.hide_application_next_steps = hide_next
        if hide_next:
            context.cycle_next_step_message = ""
            context.next_steps = []

        context.next_steps_for_display = _next_steps_without_deadline_placeholder(
            context.get("next_steps")
        )

        context.show_detail = True
        context.title = f"Application Details: {_app_name}"
        return

    # Default List View
    # Status styling
    STATUS_STYLE = {
        "Draft":          {"color": "#6b7280", "bg": "#f3f4f6"},
        "Submitted":      {"color": "#1d4ed8", "bg": "#dbeafe"},
        "Merit Published":  {"color": "#0369a1", "bg": "#e0f2fe"},
        "Merit Selected":   {"color": "#065f46", "bg": "#d1fae5"},
        "Merit Rejected":   {"color": "#991b1b", "bg": "#fee2e2"},
        "Merit Waitlisted": {"color": "#7c3aed", "bg": "#ede9fe"},
        "Under Review":     {"color": "#d97706", "bg": "#fef3c7"},
        "Shortlisted":      {"color": "#059669", "bg": "#d1fae5"},
        "Waitlisted":       {"color": "#7c3aed", "bg": "#ede9fe"},
        "Offer Issued":     {"color": "#0369a1", "bg": "#e0f2fe"},
        "Offer Accepted":   {"color": "#065f46", "bg": "#d1fae5"},
        "Offer Declined":   {"color": "#9f1239", "bg": "#ffe4e6"},
        "Offer Expired":    {"color": "#9f1239", "bg": "#ffe4e6"},
        "Confirmation Fee Paid": {"color": "#065f46", "bg": "#d1fae5"},
        "Full Fee Paid":    {"color": "#065f46", "bg": "#d1fae5"},
        "Enrolled":         {"color": "#065f46", "bg": "#d1fae5"},
    }

    _user = frappe.session.user
    apps_by_owner = frappe.get_all("Applicant", filters={"owner": _user}, pluck="name", ignore_permissions=True)
    apps_by_email = frappe.get_all("Applicant", filters={"email": _user}, pluck="name", ignore_permissions=True)
    all_app_names = list(set(apps_by_owner + apps_by_email))

    applications = []
    
    # Still fetch offer letters
    _set_offer_letter_entries(context)

    for app_id in all_app_names:
        app_doc = frappe.get_doc("Applicant", app_id)
        
        status = app_doc.status or "Draft"
        style = STATUS_STYLE.get(status, STATUS_STYLE["Draft"])
        
        program_name = frappe.db.get_value("Programme", app_doc.program, "program_name") or app_doc.program
        program_slug = frappe.db.get_value("Programme", app_doc.program, "program_slug") or ""

        # --- Withdrawal Data Logic ---
        _show_withdraw_button = False
        _payment_details = None
        _offer_name = frappe.db.get_value("Offer Letter", {
            "applicant": app_doc.name, 
            "status": ["in", ["Accepted", "Payment Completed"]]
        }, "name")
        
        if status in ["Enrolled", "Confirmation Fee Paid", "Full Fee Paid"] and _offer_name:
            _show_withdraw_button = True
            student_name = frappe.db.get_value("Student Master", {"application_number": app_doc.name}, "name")
            if student_name:
                payment_name = frappe.db.get_value("Fee Payment", {"student": student_name, "status": "Submitted"}, "name")
                if payment_name:
                    _payment_details = frappe.db.get_value("Fee Payment", payment_name, ["name", "amount", "payment_date"], as_dict=True)

        _fee_st = (app_doc.application_fee_status or "").strip()
        summary = {
            "name": app_doc.name,
            "is_editable": is_application_editable(app_doc),
            "offer_name": _offer_name or "",
            "payment_details": _payment_details,
            "show_withdraw_button": _show_withdraw_button,
            "application_fee_status": _fee_st,
            "fee_receipt_ready": (
                _fee_st == "Paid"
                and bool(_latest_application_fee_receipt_for_portal(app_doc.name))
            ),
            "header": {
                "program_name": program_name,
                "applicant_id": app_doc.name,
                "status": status,
                "status_color": style["color"],
                "status_bg": style["bg"],
                "submitted_on": frappe.utils.formatdate(app_doc.creation, "dd MMM yyyy"),
                "cycle": app_doc.admission_cycle
            },
            "personal": [
                {"label": "Full Name", "value": app_doc.candidate_name}
            ]
        }
        applications.append(summary)

    context.applications = applications
    return context

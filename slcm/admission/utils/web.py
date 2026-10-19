import re

import frappe
from frappe import _
from frappe.utils import cint, strip_html
from urllib.parse import quote

@frappe.whitelist(allow_guest=True)
def get_base64_image(url):
    """Returns base64 data URI for a given file URL by reading from local disk."""
    if not url or url in ('None', ''):
        return ''
    
    path = url.strip('/')
    possible_paths = [
        frappe.get_site_path('public', path),
        frappe.get_site_path(path),
        frappe.get_site_path('private', path)
    ]
    
    found_path = None
    import os
    for p in possible_paths:
        if os.path.exists(p):
            found_path = p
            break
            
    if not found_path:
        return frappe.utils.get_url(url)
        
    ext = path.split('.')[-1].lower()
    mime = 'image/png' if ext == 'png' else 'image/jpeg'
    
    try:
        with open(found_path, 'rb') as f:
            content = f.read()
            import base64
            encoded = base64.b64encode(content).decode('utf-8')
            return f"data:{mime};base64,{encoded}"
    except Exception:
        return frappe.utils.get_url(url)

@frappe.whitelist(allow_guest=True)
def get_base64_image(url):
    """Returns base64 data URI for a given file URL by reading from local disk."""
    if not url or url in ('None', ''):
        return ''
    
    path = url.strip('/')
    possible_paths = [
        frappe.get_site_path('public', path),
        frappe.get_site_path(path),
        frappe.get_site_path('private', path)
    ]
    
    found_path = None
    import os
    for p in possible_paths:
        if os.path.exists(p):
            found_path = p
            break
            
    if not found_path:
        return frappe.utils.get_url(url)
        
    ext = path.split('.')[-1].lower()
    mime = 'image/png' if ext == 'png' else 'image/jpeg'
    
    try:
        with open(found_path, 'rb') as f:
            content = f.read()
            import base64
            encoded = base64.b64encode(content).decode('utf-8')
            return f"data:{mime};base64,{encoded}"
    except Exception:
        return frappe.utils.get_url(url)

@frappe.whitelist(methods=["POST", "GET"])
def check_existing_application(admission_cycle=None):
    """
    Returns existing application name if user already applied in this cycle.
    Called from /admission page before showing Apply Now.
    """
    if frappe.session.user == "Guest":
        return {"exists": False, "name": ""}

    filters = {"owner": frappe.session.user}
    if admission_cycle:
        filters["admission_cycle"] = admission_cycle

    existing = frappe.get_all(
        "Applicant",
        filters=filters,
        fields=["name", "admission_cycle", "status"],
        order_by="creation desc",
        limit=1
    )
    if existing:
        return {
            "exists":  True,
            "name":    existing[0].name,
            "status":  existing[0].status,
            "cycle":   existing[0].admission_cycle,
        }
    return {"exists": False, "name": ""}

def _portal_ann_read_cache_key(user: str) -> str:
    return f"slcm_portal_ann_read::{user}"


def _get_portal_announcement_read_ids(user: str) -> set:
    raw = frappe.cache().get_value(_portal_ann_read_cache_key(user))
    if isinstance(raw, list):
        return set(raw)
    return set()


def _append_query_param(url: str, key: str, value: str) -> str:
    if not url or not key or not value:
        return url or ""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{key}={quote(str(value), safe='')}"


def _extract_offer_letter_id_from_text(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"\b(OL-APP-[A-Za-z0-9.\-_]+)\b", text)
    return m.group(1) if m else None


def _resolve_offer_letter_for_portal(document_type, document_name, subject, email_content) -> str:
    """Resolve Offer Letter name from link fields or OL-APP-* in subject/body."""
    plain = strip_html(email_content or "")
    blob = " ".join(x for x in (subject or "", plain) if x)
    extracted = _extract_offer_letter_id_from_text(blob)
    if extracted and frappe.db.exists("Offer Letter", extracted):
        return extracted
    dn = (document_name or "").strip()
    if dn and frappe.db.exists("Offer Letter", dn):
        return dn
    if (document_type or "").strip() == "Offer Letter" and dn:
        return dn
    return ""


def _extract_pace_id_from_text(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"\b(PACE-[A-Za-z0-9.\-_]+)\b", text)
    return m.group(1) if m else None

def _portal_href_for_notification_log(
    document_type,
    document_name,
    link,
    subject=None,
    email_content=None,
    notif_log_name=None,
) -> str:
    """Map Desk Notification Log reference to applicant portal routes."""
    dn = (document_name or "").strip()
    plain = strip_html(email_content or "")
    blob = " ".join(x for x in (subject or "", plain) if x)
    pace_id = _extract_pace_id_from_text(blob) or (dn if str(dn).startswith("PACE-") else None)

    if pace_id:
        base = f"/paceadmissions/progress-tracker?app={quote(pace_id, safe='')}"
    else:
        link = (link or "").strip()
        if link.startswith("/") or link.startswith("http"):
            base = link
        else:
            dt = (document_type or "").strip()
            ol = _resolve_offer_letter_for_portal(dt, dn, subject, email_content)
            if ol:
                base = f"/offer_letter/offer-letter-detail?offer={quote(ol, safe='')}"
            elif dt == "Applicant" and dn:
                base = f"/my-applications?app={quote(dn, safe='')}"
            elif dt in ("Scholarship Application", "Scholarship Scheme", "Scholarship Utilization"):
                base = "/merit-and-scholarship/scholarships"
            elif "Scholarship" in dt:
                base = "/merit-and-scholarship/scholarships"
            elif dt == "User" and dn:
                base = "/merit-and-scholarship/admission_dashboard?panel=profile"
            else:
                base = "/merit-and-scholarship/admission_dashboard"

    if notif_log_name:
        base = _append_query_param(base, "notif", notif_log_name)
    return base


@frappe.whitelist(methods=["POST", "GET"])
def mark_notifications_read(names=None):
    """Mark Notification Log rows read for the current session user."""
    user = frappe.session.user
    if user == "Guest":
        return {"success": False}

    try:
        if not names:
            return {"success": True}
        if isinstance(names, str):
            import json as _json

            try:
                names = _json.loads(names)
            except Exception:
                names = [names]

        for name in names:
            if not name:
                continue
            if frappe.db.exists("Notification Log", {"name": name, "for_user": user}):
                frappe.db.set_value("Notification Log", name, "read", 1)

        frappe.db.commit()
        return {"success": True}
    except Exception as e:
        frappe.log_error(f"mark_notifications_read failed: {e}", "Portal")
        return {"success": False}


@frappe.whitelist(methods=["POST", "GET"])
def mark_portal_announcement_read(name=None):
    """Persist 'read' for a portal announcement (badge count) for this user."""
    user = frappe.session.user
    if user == "Guest" or not name:
        return {"success": False}
    try:
        reads = list(_get_portal_announcement_read_ids(user))
        if name not in reads:
            reads.append(name)
            frappe.cache().set_value(
                _portal_ann_read_cache_key(user), reads, expires_in_sec=86400 * 365
            )
        return {"success": True}
    except Exception as e:
        frappe.log_error(f"mark_portal_announcement_read failed: {e}", "Portal")
        return {"success": False}


@frappe.whitelist(methods=["POST", "GET"])
def get_portal_notifications(notif_page=None, ann_page=None, page_length=None):
    """
    Notifications: Desk Notification Log for session user (paginated).
    Announcements: Portal Announcement with per-user read state (paginated).
    """
    try:
        user = frappe.session.user
        if user == "Guest":
            return {"notifications": [], "announcements": []}

        pl = cint(page_length) or 10
        pl = max(5, min(pl, 50))
        np = cint(notif_page) or 0
        ap = cint(ann_page) or 0
        if np < 0:
            np = 0
        if ap < 0:
            ap = 0

        read_ann = _get_portal_announcement_read_ids(user)

        notif_total = frappe.db.count("Notification Log", filters={"for_user": user})
        notif_unread_count = frappe.db.count(
            "Notification Log", filters={"for_user": user, "read": 0}
        )

        ann_filters = {"is_active": 1, "status": "Published"}
        ann_total = frappe.db.count("Portal Announcement", filters=ann_filters)
        ann_all_names = frappe.get_all(
            "Portal Announcement",
            filters=ann_filters,
            pluck="name",
            limit_page_length=500,
        )
        ann_unread_count = sum(1 for n in ann_all_names if n not in read_ann)

        logs = frappe.get_all(
            "Notification Log",
            filters={"for_user": user},
            fields=[
                "name",
                "subject",
                "document_type",
                "document_name",
                "read",
                "creation",
                "type",
                "link",
                "email_content",
            ],
            order_by="creation desc",
            limit_start=np * pl,
            limit_page_length=pl,
            ignore_permissions=True,
        )

        notifications = []
        for row in logs:
            msg = strip_html(row.get("email_content") or "")
            if len(msg) > 320:
                msg = msg[:317] + "…"
            notifications.append(
                {
                    "name": row.name,
                    "title": row.subject or _("Notification"),
                    "message": msg,
                    "is_read": 1 if row.read else 0,
                    "creation": str(row.creation),
                    "source": "desk",
                    "document_type": row.document_type,
                    "document_name": row.document_name,
                    "portal_href": _portal_href_for_notification_log(
                        row.document_type,
                        row.document_name,
                        row.link,
                        subject=row.subject,
                        email_content=row.get("email_content"),
                        notif_log_name=row.name,
                    ),
                    "notification_type": row.type or "Alert",
                    "owner_fullname": "",
                }
            )

        announcements = frappe.get_all(
            "Portal Announcement",
            filters=ann_filters,
            fields=[
                "name",
                "title",
                "publish_date",
                "announcement_type",
                "summary as content",
                "featured_image as image",
                "owner",
            ],
            order_by="publish_date desc",
            limit_start=ap * pl,
            limit_page_length=pl,
        )
        for a in announcements:
            try:
                a["owner_fullname"] = (
                    frappe.db.get_value("User", a.owner, "full_name") or a.owner
                )
            except Exception:
                a["owner_fullname"] = ""
            a["is_read"] = 1 if a.name in read_ann else 0

        return {
            "notifications": notifications,
            "announcements": announcements,
            "notif_total": notif_total,
            "ann_total": ann_total,
            "notif_page": np,
            "ann_page": ap,
            "page_length": pl,
            "notif_unread_count": notif_unread_count,
            "ann_unread_count": ann_unread_count,
        }
    except Exception as e:
        frappe.log_error(f"get_portal_notifications failed: {e}", "Portal")
        return {"notifications": [], "announcements": []}

@frappe.whitelist(allow_guest=True)
def get_public_announcements(target_audience=None):
    """Returns announcements visible without login"""
    try:
        filters = {"is_active": 1, "status": "Published"}
        if target_audience:
            if isinstance(target_audience, str):
                import json
                try:
                    target_audience = json.loads(target_audience)
                except Exception:
                    target_audience = [target_audience]
            filters["target_audience"] = ["in", target_audience]
            
        ann = frappe.get_all("Portal Announcement",
            filters=filters,
            fields=["name", "title", "publish_date",
                    "announcement_type", "summary as content",
                    "featured_image", "owner"],
            order_by="publish_date desc",
            limit=10)
        
        for a in ann:
            try:
                a["owner_fullname"] = frappe.db.get_value("User", a.owner, "full_name") or a.owner
            except:
                a["owner_fullname"] = ""
                
        return ann or []
    except Exception as e:
        frappe.log_error(f"get_public_announcements failed: {e}", "Portal")
        return []

@frappe.whitelist(methods=["POST", "GET"])
def get_user_type():
    """Returns user_type for the currently logged-in user"""
    try:
        user_type = frappe.db.get_value("User", frappe.session.user, "user_type")
        return {"user_type": user_type or "Website User"}
    except Exception as e:
        frappe.log_error(f"get_user_type failed: {e}", "Portal")
        return {"user_type": "Website User"}

def _get_stage_seq(stages, stage_name):
    """Returns sequence number of a stage by name."""
    for s in stages:
        if s.stage_name == stage_name:
            return getattr(s, "sequence", None) or getattr(s, "sequence_no", None) or 0
    return 0

@frappe.whitelist(allow_guest=False)
def get_stage_tracker_data(applicant_name: str) -> dict:
    """
    Returns stage tracker data for the portal progress bar.
    Directly matches Applicant.status with Admission Cycle Stage.status.
    Filters stages based on Applicant.intake_type.
    """
    applicant = frappe.db.get_value(
        "Applicant", applicant_name,
        ["owner", "email", "admission_cycle", "intake_type", "status", "program", "foriegn_national"],
        as_dict=True
    )
    if not applicant:
        frappe.throw("Not found", frappe.DoesNotExistError)

    user     = frappe.session.user
    is_admin = "Admission Admin" in frappe.get_roles(user)
    if not is_admin and applicant.owner != user and applicant.email != user:
        frappe.throw("Not permitted", frappe.PermissionError)

    if not applicant.admission_cycle:
        return {"stages": [], "progress_pct": 0, "current_status": applicant.status}

    # Admission Cycle Stage was removed; querying it would raise DoesNotExistError
    if not frappe.db.exists("DocType", "Admission Cycle Stage"):
        return {"stages": [], "progress_pct": 0, "current_status": applicant.status}

    # Load all enabled stages for this cycle
    all_stages = frappe.get_all(
        "Admission Cycle Stage",
        filters={
            "parent": applicant.admission_cycle,
            "is_enabled": 1
        },
        fields=[
            "name", "stage_name", "stage_type", "stage_code",
            "sequence_no", "start_date", "end_date", "applicable_workflow",
            "action_label", "action_url", "requires_applicant_action",
            "activate_status", "completed_status", "closed_status"
        ],
        order_by="sequence_no asc"
    )

    # Filter stages by intake_type
    # Admission Cycle Stage.applicable_workflow matches Applicant.intake_type
    # If applicable_workflow is "All", it shows for everyone.
    intake = applicant.intake_type or "External Test"
    filtered_stages = [
        s for s in all_stages
        if s.applicable_workflow == "All" or s.applicable_workflow == intake
    ]

    # Filter stages by Programme configuration (domestic vs international stages)
    if applicant.get("program"):
        try:
            program_doc = frappe.get_doc("Programme", applicant.program, ignore_permissions=True)
            if applicant.get("foriegn_national") == "Yes":
                stage_fields = {
                    "Application": "internationa_application_submitted",
                    "Exam": "international_entrance_test",
                    "Interview": "international_interview",
                    "Fee": "inrternation_admission_fee",
                    "Enrollment": "international_enrolled",
                }
            else:
                stage_fields = {
                    "Application": "submitted",
                    "Exam": "entrance_test",
                    "Interview": "intereview",
                    "Merit": "merit_list",
                    "Evaluation": "seat_allocation",
                    "Offer": "offer_letter",
                    "Fee": "admission_fee",
                    "Enrollment": "enrolled",
                }
            
            filtered_stages = [
                s for s in filtered_stages
                if s.get("stage_type") not in stage_fields or program_doc.get(stage_fields[s.get("stage_type")])
            ]
        except Exception:
            pass

    if not filtered_stages:
        return {"stages": [], "progress_pct": 0, "current_status": applicant.status}

    # Fetch Eligibility Evaluation for exemptions
    evaluation = frappe.db.get_value("Eligibility Evaluation", 
        {"applicant_name": applicant_name}, 
        ["exempts_entrance_test", "exempts_interview"], 
        as_dict=True) or {}

    # Find the active stage by matching status
    # We look for the furthest stage that matches the current status.
    current_status = applicant.status
    active_index = -1
    is_terminal_stop = False
    is_completed_stop = False
    
    for i, s in enumerate(filtered_stages):
        if s.activate_status == current_status:
            active_index = i
            is_terminal_stop = False
            is_completed_stop = False
        elif s.completed_status == current_status:
            active_index = i
            is_terminal_stop = False
            is_completed_stop = True
        elif s.closed_status == current_status:
            active_index = i
            is_terminal_stop = True
            is_completed_stop = False

    # If no exact match, we might need a fallback. 
    # For now, if no match, assume it's before the first stage or past the last.
    
    stages_out = []
    found_active = False

    for i, s in enumerate(filtered_stages):
        state = "pending"
        if active_index != -1:
            if i < active_index:
                state = "completed"
            elif i == active_index:
                if is_terminal_stop:
                    state = "closed"
                elif is_completed_stop:
                    state = "completed"
                else:
                    state = "active"
                found_active = True
            else:
                state = "pending"
        else:
            # Fallback logic if no status match: 
            # This part is tricky. If status doesn't match, maybe it's Draft or something else.
            state = "pending"

        is_exempted = False
        if s.get("stage_type") == "Exam" and evaluation.get("exempts_entrance_test"):
            is_exempted = True
        elif s.get("stage_type") == "Interview" and evaluation.get("exempts_interview"):
            is_exempted = True

        stages_out.append({
            "name":                      s.get("name"),
            "stage_name":                s.get("stage_name") or s.get("stage_type"),
            "stage_type":                s.get("stage_type"),
            "stage_code":                s.get("stage_code") or "",
            "sequence":                  s.get("sequence_no") or 0,
            "state":                     state,
            "status":                    state, # Added for JS compatibility
            "is_exempted":               is_exempted,
            "start_date":                str(s.start_date) if s.get("start_date") else None,
            "end_date":                  str(s.end_date)   if s.get("end_date")   else None,
            "action_label":              s.get("action_label") or "",
            "action_url":                s.get("action_url") or "",
            "requires_applicant_action": s.get("requires_applicant_action") or 0,
            "show_action": bool(
                state == "active" and
                s.get("action_url") and
                s.get("requires_applicant_action")
            ),
        })

    # Calculate progress percentage based on active index
    total_stages = len(filtered_stages)
    if active_index != -1:
        # Progress is (index + 1) / total
        progress_pct = round(((active_index + 1) / total_stages) * 100, 1)
    else:
        progress_pct = 0.0

    return {
        "stages":         stages_out,
        "progress_pct":   progress_pct,
        "current_status": applicant.status,
        "intake_type":    applicant.intake_type
    }




@frappe.whitelist(methods=["POST", "GET"])
def get_edit_permission(applicant_name):
    """
    Returns whether the current applicant can edit their application.
    Two-layer check:
      Layer 1: Portal Config master switch (allow_edit_after_submit)
      Layer 2: Current stage is_editable flag
    """
    # Load applicant
    applicant = frappe.get_doc("Applicant", applicant_name)

    # Only owner can check own permissions
    allowed_roles = {"Admission Admin", "System Manager", "Applicant"}
    is_owner = frappe.session.user == applicant.owner
    has_role = bool(allowed_roles & set(frappe.get_roles()))
    if not is_owner and not has_role:
        return {"editable": False, "reason": "Not permitted"}

    # Draft is always editable
    if applicant.docstatus == 0:
        return {"editable": True, "reason": "draft", "editable_sections": []}

    # Layer 1: Portal Config master switch
    try:
        portal_config = frappe.get_single("Admission Portal Config")
        if not portal_config.allow_edit_after_submit:
            return {
                "editable": False,
                "reason": "Editing is currently disabled by the administrator."
            }
    except Exception:
        # If Portal Config not found, deny by default
        return {"editable": False, "reason": "Portal config not found"}

    # Layer 2: Current stage is_editable flag
    if not applicant.admission_cycle or not applicant.current_stage:
        return {"editable": False, "reason": "No active stage found"}

    cycle_doc = frappe.get_doc("Admission Cycle", applicant.admission_cycle)
    current_stage_row = next(
        (s for s in cycle_doc.stages
         if s.stage_name == applicant.current_stage),
        None
    )

    if not current_stage_row:
        return {"editable": False, "reason": "Current stage not configured"}

    if not current_stage_row.is_editable:
        return {
            "editable": False,
            "reason": f"Editing is not allowed during the {applicant.current_stage} stage."
        }

    return {
        "editable":          True,
        "reason":            "stage_allows",
        "editable_sections": [],   # empty = all sections editable
    }

@frappe.whitelist()
def get_offer_list(limit_start=0, limit_page_length=10):
    """
    Fetches offer letters with pagination. 
    If admin, fetches all. If applicant, fetches only theirs.
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Authentication required", frappe.PermissionError)

    roles = frappe.get_roles(user)
    is_admin = "Administrator" in roles or "System Manager" in roles or "Admission Admin" in roles
    
    filters = {}
    applicant_name = "System View"
    
    if not is_admin:
        # Filter by email directly on Offer Letter (handles multiple applications for one email)
        filters["email"] = user
        # Get candidate name from any of their applicant records for the welcome message
        applicant_name = frappe.db.get_value("Applicant", {"email": user}, "candidate_name") or user
    
    # Fetch total count for pagination
    total_count = frappe.db.count("Offer Letter", filters=filters)

    # Fetch offers
    fields = [
        "name", "program", "issued_on", "status", 
        "payment_deadline", "offer_acceptance_deadline", "confirmation_fee_deadline", 
        "payable_amount", "campus", "applicant",
        "academic_year", "admission_cycle"
    ]
    
    # Ensure integer types for pagination
    limit_start = int(limit_start)
    limit_page_length = int(limit_page_length)

    offers = frappe.get_all(
        "Offer Letter", 
        filters=filters, 
        fields=fields, 
        order_by="creation desc",
        limit_start=limit_start,
        limit_page_length=limit_page_length,
        ignore_permissions=True
    )

    for offer in offers:
        if offer.campus:
            campus_data = frappe.db.get_value("Campus", offer.campus, ["campus_name", "logo"], as_dict=1)
            if campus_data:
                offer.campus_name = campus_data.campus_name or offer.campus
                offer.campus_image = campus_data.logo
            else:
                offer.campus_name = offer.campus
                offer.campus_image = None
        else:
            offer.campus_name = ""
            offer.campus_image = None
            
        offer.candidate_photo = frappe.db.get_value("Applicant", offer.applicant, "candidate_photo")
        if not offer.candidate_photo:
            offer.candidate_photo = frappe.db.get_value("User", frappe.session.user, "user_image")
            
        # Fetch scholarship info from Applicant Fee Assignment
        afa = frappe.db.get_value("Applicant Fee Assignment", 
            {"offer_letter": offer.name, "fee_type": ["in", ["Admission Fee", "Confirmation Fee"]], "docstatus": ["!=", 2]}, 
            ["scholarship_amount", "final_payable_amount"], as_dict=True)
        
        if afa:
            offer.scholarship_amount = afa.scholarship_amount or 0
            offer.final_payable_amount = afa.final_payable_amount if afa.final_payable_amount is not None else offer.payable_amount
            # Ensure the list view also reflects the true total amount if we have an assignment
            offer.payable_amount = offer.final_payable_amount
        else:
            offer.scholarship_amount = 0
            offer.final_payable_amount = offer.payable_amount

        # Fetch cancellation info
        cancellation = frappe.get_all("Admission Cancellation", 
            filters={"offer": offer.name}, 
            fields=["name", "status"], 
            limit=1
        )
        if cancellation:
            offer.has_cancellation = True
            offer.cancellation_name = cancellation[0].name
            offer.cancellation_status = cancellation[0].status
        else:
            offer.has_cancellation = False
            offer.cancellation_name = ""
            offer.cancellation_status = ""

    return {
        "offers": offers,
        "total_count": total_count,
        "applicant_name": applicant_name,
        "is_admin": is_admin,
        "currency": frappe.defaults.get_global_default("currency") or "INR"
    }

@frappe.whitelist(methods=["POST", "GET"])
def download_admit_card(admit_card):
    """
    Custom download function for Admit Card that bypasses standard print permissions
    after verifying that the current user owns the application.
    """
    user = frappe.session.user
    applicant_name = frappe.db.get_value("Applicant", {"email": user}, "name")
    
    try:
        doc = frappe.get_doc("Entrance Test Seat Allocation", admit_card, ignore_permissions=True)
    except frappe.DoesNotExistError:
        frappe.throw("Admit Card not found")

    if not applicant_name or doc.applicant != applicant_name:
        if "Admission Admin" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
            frappe.throw("Not authorized", frappe.PermissionError)

    is_rescheduled = (doc.is_rescheduled == 1 or doc.entrance_test_status == "Rescheduled")
    status = doc.re_allocation_status if is_rescheduled else doc.allocation_status
    
    if status not in ["Allocated", "Reallocated"]:
        frappe.throw("Admit Card is only available after seat allocation is confirmed.")

    field_to_check = "reschedule_admit_card" if is_rescheduled else "admit_card"
    stored_file_url = getattr(doc, field_to_check)

    if stored_file_url:
        try:
            file_doc = frappe.get_doc("File", {"file_url": stored_file_url})
            frappe.local.response.filename = f"Admit_Card_{doc.applicant}.pdf"
            frappe.local.response.filecontent = file_doc.get_content()
            frappe.local.response.type = "download"
            return
        except Exception:
            pass

    frappe.flags.ignore_print_permissions = True
    pdf_content = None
    last_error = None

    for generator in ("wkhtmltopdf", "chrome"):
        try:
            pdf_generator_options = {}
            if generator == "chrome":
                pdf_generator_options = {
                    "no-sandbox": "",
                    "disable-setuid-sandbox": "",
                    "disable-dev-shm-usage": ""
                }

            pdf_content = frappe.get_print(
                "Entrance Test Seat Allocation",
                doc.name,
                "Admit Card",
                as_pdf=True,
                doc=doc,
                pdf_generator=generator,
                pdf_options=pdf_generator_options if generator == "wkhtmltopdf" else None
            )
            if pdf_content:
                break
        except Exception as e:
            last_error = e
            error_details = {
                "admit_card": doc.name,
                "generator": generator,
                "error": str(e),
                "site": frappe.local.site,
                "url": frappe.utils.get_url()
            }
            frappe.log_error(
                title=f"Admit Card Download failed with {generator}",
                message=frappe.as_json(error_details) + "\n" + frappe.get_traceback()
            )
            if generator == "wkhtmltopdf":
                continue
            break

    if not pdf_content:
        frappe.throw(frappe._("PDF generation failed for admit card. Error: {0}").format(str(last_error)))

    frappe.local.response.filename = f"Admit_Card_{doc.applicant}.pdf"
    frappe.local.response.filecontent = pdf_content
    frappe.local.response.type = "download"

@frappe.whitelist(methods=["POST", "GET"])
def download_application(applicant_name):
    """
    Generates and downloads the Applicant PDF for the owner.
    Prefers Chrome PDF generator to avoid wkhtmltopdf issues (unpatched Qt, network errors).
    Falls back to wkhtmltopdf if Chrome is not available.
    """
    user = frappe.session.user
    try:
        applicant = frappe.get_doc("Applicant", applicant_name, ignore_permissions=True)
    except frappe.DoesNotExistError:
        frappe.throw("Application not found")

    if applicant.owner != user and applicant.email != user:
        if "Admission Admin" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
            frappe.throw("Not permitted", frappe.PermissionError)

    frappe.flags.ignore_print_permissions = True
    pdf_content = None
    last_error = None

    # Prefer wkhtmltopdf as it is more stable in web context for this environment.
    # Fallback to Chrome if wkhtmltopdf fails.
    for generator in ("wkhtmltopdf", "chrome"):
        try:
            # For Chrome, we can try to pass options if the frappe version supports it
            pdf_generator_options = {}
            if generator == "chrome":
                pdf_generator_options = {
                    "no-sandbox": "",
                    "disable-setuid-sandbox": "",
                    "disable-dev-shm-usage": ""
                }

            pdf_content = frappe.get_print(
                "Applicant",
                applicant_name,
                "Applicant Application Form",
                as_pdf=True,
                doc=applicant,
                pdf_generator=generator,
                pdf_options=pdf_generator_options if generator == "wkhtmltopdf" else None
            )
            if pdf_content:
                break
        except Exception as e:
            last_error = e
            # Log error for each attempt to help debugging
            error_details = {
                "applicant": applicant_name,
                "generator": generator,
                "error": str(e),
                "site": frappe.local.site,
                "url": frappe.utils.get_url()
            }
            frappe.log_error(
                title=f"Application Download failed with {generator}",
                message=frappe.as_json(error_details) + "\n" + frappe.get_traceback()
            )
            if generator == "wkhtmltopdf":
                continue
            # Do not raise here, let it reach the throw below if both fail
            break

    if not pdf_content:
        error_msg = f"PDF generation failed. Try: Print Format 'Applicant Application Form' → PDF generator = Chrome, or run: bench setup chromium. Error: {str(last_error)}"
        frappe.throw(frappe._(error_msg))

    frappe.local.response.filename = f"Application_{applicant_name}.pdf"
    frappe.local.response.filecontent = pdf_content
    frappe.local.response.type = "download"

@frappe.whitelist(methods=["POST", "GET"])
def download_receipt(receipt_name=None, fee_type=None, offer_letter=None):
    """
    Generates and downloads the Applicant Payment Receipt PDF for the owner.

    Uses Programme Reservation Policy.payment_receipt_template (if configured)
    as the print format, falling back to the default format.
    """
    user = frappe.session.user
    receipt = None
    
    if receipt_name:
        try:
            receipt = frappe.get_doc("Applicant Payment Receipt", receipt_name, ignore_permissions=True)
        except frappe.DoesNotExistError:
            frappe.throw("Receipt not found")
    elif fee_type and offer_letter:
        receipts = frappe.get_all("Applicant Payment Receipt", 
                                 filters={"offer_letter": offer_letter, "fee_type": fee_type},
                                 order_by="creation desc", limit=1)
        if receipts:
            receipt = frappe.get_doc("Applicant Payment Receipt", receipts[0].name, ignore_permissions=True)
        else:
            frappe.throw(f"Receipt for {fee_type} not found")
    else:
        frappe.throw("Receipt details not provided")

    # Check if this user owns the receipt (via the Applicant record)
    applicant_name = receipt.applicant
    applicant_email = frappe.db.get_value("Applicant", applicant_name, "email")

    if receipt.owner != user and applicant_email != user:
        if "Admission Admin" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
            frappe.throw("Not permitted", frappe.PermissionError)

    # Resolve print format dynamically
    print_format = None
    try:
        if receipt.fee_type in ["Confirmation Fee", "Admission Fee"] and receipt.offer_letter:
            offer = frappe.get_doc("Offer Letter", receipt.offer_letter)
            if offer.fee_structure:
                template = frappe.db.get_value("Fee Structure", offer.fee_structure, "receipt_print_format")
                if template:
                    print_format = template

        if not print_format and applicant_name:
            app = frappe.get_doc("Applicant", applicant_name)
            if app.admission_cycle and app.program:
                # Prefer campus-specific policy; fall back to generic program+cycle
                policy_name = None
                if app.campus:
                    policy_name = frappe.db.get_value(
                        "Admission Cycle Program",
                        {
                            "parent": app.admission_cycle,
                            "program": app.program,
                            "campus": app.campus,
                            "is_active": 1,
                        },
                        "reservation_policy",
                    )
                if not policy_name:
                    policy_name = frappe.db.get_value(
                        "Admission Cycle Program",
                        {
                            "parent": app.admission_cycle,
                            "program": app.program,
                            "is_active": 1,
                        },
                        "reservation_policy",
                    )
                if policy_name:
                    template = frappe.db.get_value(
                        "Programme Reservation Policy",
                        policy_name,
                        "payment_receipt_template",
                    )
                    if template:
                        print_format = template
    except Exception:
        # On any lookup error, quietly fall back to None
        pass

    frappe.flags.ignore_print_permissions = True
    pdf_content = None
    last_error = None

    for generator in ("wkhtmltopdf", "chrome"):
        try:
            pdf_generator_options = {}
            if generator == "chrome":
                pdf_generator_options = {
                    "no-sandbox": "",
                    "disable-setuid-sandbox": "",
                    "disable-dev-shm-usage": ""
                }

            pdf_content = frappe.get_print(
                "Applicant Payment Receipt",
                receipt.name,
                print_format,
                as_pdf=True,
                doc=receipt,
                pdf_generator=generator,
                pdf_options=pdf_generator_options if generator == "wkhtmltopdf" else None
            )
            if pdf_content:
                break
        except Exception as e:
            last_error = e
            error_details = {
                "receipt": receipt.name,
                "generator": generator,
                "error": str(e),
                "site": frappe.local.site,
                "url": frappe.utils.get_url()
            }
            frappe.log_error(
                title=f"Receipt Download failed with {generator}",
                message=frappe.as_json(error_details) + "\n" + frappe.get_traceback()
            )
            if generator == "wkhtmltopdf":
                continue
            break

    if not pdf_content:
        frappe.throw(frappe._("PDF generation failed for receipt. Error: {0}").format(str(last_error)))

    candidate_name = frappe.db.get_value("Applicant", receipt.applicant, "candidate_name") or receipt.applicant
    now_str = frappe.utils.now_datetime().strftime("%d-%m-%Y:%H:%M")
    safe_candidate_name = str(candidate_name).replace("/", "-").replace("\\", "-")
    safe_fee_type = str(receipt.fee_type).replace("/", "-").replace("\\", "-")

    frappe.local.response.filename = f"Fee Receipt-{safe_candidate_name}-{safe_fee_type}-{now_str}.pdf"
    frappe.local.response.filecontent = pdf_content
    frappe.local.response.type = "download"


@frappe.whitelist()
def get_latest_application_fee_receipt(applicant_name: str):
    """
    Returns the latest Applicant Payment Receipt name for the given applicant
    for Application Fee payments (receipts not linked to an Offer Letter).
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    applicant_name = (applicant_name or "").strip()
    if not applicant_name:
        return {"receipt_name": None}

    # Ownership check
    applicant_email = frappe.db.get_value("Applicant", applicant_name, "email")
    if applicant_email not in (user, frappe.db.get_value("User", user, "email")):
        if "Admission Admin" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
            frappe.throw("Not permitted", frappe.PermissionError)

    receipt_name = frappe.db.get_value(
        "Applicant Payment Receipt",
        {"applicant": applicant_name, "offer_letter": ["is", "not set"]},
        "name",
        order_by="creation desc",
    )
    return {"receipt_name": receipt_name}

@frappe.whitelist(methods=["POST", "GET"])
def download_offer_letter(offer_letter):
    """
    Generates and downloads the Offer Letter PDF for the owner.
    """
    user = frappe.session.user
    try:
        ol = frappe.get_doc("Offer Letter", offer_letter, ignore_permissions=True)
    except frappe.DoesNotExistError:
        frappe.throw("Offer Letter not found")

    applicant_name = ol.applicant
    applicant = frappe.get_doc("Applicant", applicant_name, ignore_permissions=True)
    
    if applicant.owner != user and applicant.email != user:
        if "Admission Admin" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
            frappe.throw("Not permitted", frappe.PermissionError)
    
    # Check if PDF already stored
    if ol.offer_letter_pdf:
        try:
            file_doc = frappe.get_doc("File", {"file_url": ol.offer_letter_pdf})
            frappe.local.response.filename = f"Offer_Letter_{applicant_name}.pdf"
            frappe.local.response.filecontent = file_doc.get_content()
            frappe.local.response.type = "download"
            return
        except Exception:
            pass

    # Generate PDF
    frappe.flags.ignore_print_permissions = True
    pdf_content = None
    last_error = None

    for generator in ("wkhtmltopdf", "chrome"):
        try:
            pdf_generator_options = {}
            if generator == "chrome":
                pdf_generator_options = {
                    "no-sandbox": "",
                    "disable-setuid-sandbox": "",
                    "disable-dev-shm-usage": ""
                }

            pdf_content = frappe.get_print(
                "Offer Letter",
                offer_letter,
                as_pdf=True,
                doc=ol,
                pdf_generator=generator,
                pdf_options=pdf_generator_options if generator == "wkhtmltopdf" else None
            )
            if pdf_content:
                break
        except Exception as e:
            last_error = e
            error_details = {
                "offer_letter": offer_letter,
                "generator": generator,
                "error": str(e),
                "site": frappe.local.site,
                "url": frappe.utils.get_url()
            }
            frappe.log_error(
                title=f"Offer Letter Download failed with {generator}",
                message=frappe.as_json(error_details) + "\n" + frappe.get_traceback()
            )
            if generator == "wkhtmltopdf":
                continue
            break

    if not pdf_content:
        frappe.throw(frappe._("PDF generation failed for offer letter. Error: {0}").format(str(last_error)))

    frappe.local.response.filename = f"Offer_Letter_{applicant_name}.pdf"
    frappe.local.response.filecontent = pdf_content
    frappe.local.response.type = "download"
    

@frappe.whitelist(methods=["POST", "GET"])
def download_refund_receipt(refund_request):
    """
    Generates and downloads the Refund Request PDF for the owner by rendering the HTML template directly.
    """
    user = frappe.session.user
    try:
        rr = frappe.get_doc("Refund Request", refund_request, ignore_permissions=True)
    except frappe.DoesNotExistError:
        frappe.throw("Refund Request not found")

    # Check if this user owns the refund request (via the Applicant record)
    applicant_email = frappe.db.get_value("Applicant", rr.applicant, "email")

    if rr.owner != user and applicant_email != user:
        if "Admission Admin" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
            frappe.throw("Not permitted", frappe.PermissionError)

    import os
    template_path = os.path.join(frappe.get_app_path("slcm"), "admission", "print_format", "refund_receipt_format", "refund_receipt_format.html")
    
    if not os.path.exists(template_path):
        # Fallback to standard if template missing (should not happen)
        pdf_content = frappe.get_print("Refund Request", refund_request, as_pdf=True, doc=rr)
    else:
        with open(template_path, "r") as f:
            template_content = f.read()

        # Render HTML using Jinja
        html = frappe.render_template(template_content, {
            "doc": rr,
            "frappe": frappe,
            "_": frappe._
        })

        # Generate PDF
        try:
            from frappe.utils.pdf import get_pdf
            pdf_content = get_pdf(html)
        except Exception as e:
            frappe.log_error(f"Refund Receipt PDF generation failed: {str(e)}")
            # Fallback to standard on failure
            pdf_content = frappe.get_print("Refund Request", refund_request, as_pdf=True, doc=rr)

    frappe.local.response.filename = f"Refund_Receipt_{refund_request}.pdf"
    frappe.local.response.filecontent = pdf_content
    frappe.local.response.type = "download"



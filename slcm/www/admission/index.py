import frappe
from slcm.admission.utils.portal import (
    build_applicant_form_new_url,
    build_login_redirect_to_applicant_form_new,
)
from slcm.admission.utils.stage_control import can_apply, get_current_stage

login_required = False

def _load_program_detail(context, slug):
    """Populate context for /admission/[slug] detail view."""
    import frappe
    try:
        from slcm.admission.utils.portal import get_portal_config
        context.portal_config = get_portal_config()
    except Exception:
        context.portal_config = None

    prog_name = frappe.db.get_value(
        "Programme", {"program_slug": slug}, "name")

    if not prog_name:
        context.program_not_found = True
        context.program = None
        _set_empty_pd_context(context, slug)
        return

    try:
        prog = frappe.get_doc("Programme", prog_name)
    except Exception:
        context.program_not_found = True
        context.program = None
        _set_empty_pd_context(context, slug)
        return

    context.program = prog
    context.program_not_found = False

    def gf(field, default=""):
        try:
            return prog.get(field) or default
        except Exception:
            return default

    context.prog_name        = gf("program_name")
    context.prog_level       = gf("program_level")
    context.prog_duration    = gf("program_duration")
    context.prog_credits     = gf("graduation_credits")
    context.prog_dept        = gf("department")
    context.prog_hero        = gf("hero_image")
    context.prog_image       = gf("program_image")   # NEW: program_image field
    context.prog_description = gf("program_description")
    context.prog_intake      = gf("intake_type")
    context.prog_eligibility = gf("eligibility_summary")
    context.prog_app_fee     = gf("application_fee")
    context.prog_deadline    = gf("application_deadline")
    context.prog_brochure    = gf("brochure_file")
    context.prog_app_link    = gf("application_form_link")
    context.prog_slug        = slug

    # Media (child table "media" / Program Media)
    try:
        def _normalize_video_url(url):
            """Convert watch URLs to embed URLs."""
            if not url:
                return url
            import re
            # youtu.be/ID
            m = re.search(r'youtu\.be/([^?&]+)', url)
            if m:
                return 'https://www.youtube.com/embed/' + m.group(1)
            # youtube.com/watch?v=ID
            m = re.search(r'youtube\.com/watch\?v=([^&]+)', url)
            if m:
                return 'https://www.youtube.com/embed/' + m.group(1)
            # vimeo.com/ID
            m = re.search(r'vimeo\.com/(\d+)', url)
            if m:
                return 'https://player.vimeo.com/video/' + m.group(1)
            return url

        media_list = []
        for m in (prog.get("media") or []):
            ext_url  = _pf(m, "external_url") or ""
            med_url  = _pf(m, "media_url") or ""
            mtype    = _pf(m, "media_type") or "Image"

            # Auto-detect video from URL if type not set
            if not mtype or mtype == "Image":
                combined = (ext_url + med_url).lower()
                if any(x in combined for x in ["youtube", "youtu.be", "vimeo"]):
                    mtype = "Video"

            # Prefer external_url over media_url; normalize video URLs
            raw_url = ext_url if ext_url else med_url
            if mtype == "Video":
                display_url = _normalize_video_url(raw_url)
            else:
                display_url = raw_url

            media_list.append(frappe._dict({
                "media_type":   mtype,
                "type":         mtype, # alias
                "media_url":    med_url,
                "external_url": ext_url,
                "display_url":  display_url,
                "url":          display_url, # alias
                "caption":      _pf(m, "caption") or "",
                "is_hero":      _pf(m, "is_hero") or 0,
                "sort_order":   _pf(m, "sort_order") or 0,
            }))

        # Sort by sort_order, hero first
        media_list.sort(key=lambda x: (not x.is_hero, x.sort_order))
        context.prog_media  = media_list
        context.prog_images = [m for m in media_list if m.media_type == "Image"]
        context.prog_videos = [m for m in media_list if m.media_type == "Video"]
    except Exception as ex:
        frappe.log_error(str(ex), "prog_detail:media")
        context.prog_media = context.prog_images = context.prog_videos = []

    # Curriculum
    try:
        curriculum = []
        for c in (gf("curriculum_items",[]) or []):
            raw_s = _pf(c,"subjects") or ""
            curriculum.append({
                "year_label": _pf(c,"year_label") or "",
                "credits":    _pf(c,"credits") or "",
                "subjects":   [s.strip() for s in raw_s.split("\n") if s.strip()],
            })
        context.prog_curriculum = curriculum
    except Exception as ex:
        frappe.log_error(str(ex),"prog_detail:curriculum")
        context.prog_curriculum = []

    # Career
    try:
        career = []
        for c in (gf("career_items",[]) or []):
            career.append({
                "title":       _pf(c,"role_title") or "",
                "icon":        _pf(c,"icon") or "work",
                "salary":      _pf(c,"salary_range") or "",
                "description": _pf(c,"description") or "",
            })
        context.prog_career = career
    except Exception as ex:
        frappe.log_error(str(ex),"prog_detail:career")
        context.prog_career = []

    # Faculty
    try:
        faculty = []
        for f in (gf("faculty_items",[]) or []):
            faculty.append({
                "name":           _pf(f,"faculty_name") or "",
                "designation":    _pf(f,"designation") or "",
                "specialization": _pf(f,"specialization") or "",
                "photo":          _pf(f,"photo") or "",
                "profile_url":    _pf(f,"profile_url") or "",
            })
        context.prog_faculty = faculty
    except Exception as ex:
        frappe.log_error(str(ex),"prog_detail:faculty")
        context.prog_faculty = []

    # Active cycle
    try:
        active_cycle_doc = frappe.get_last_doc(
            "Admission Cycle", filters={"status": "Active"})
        if active_cycle_doc:
            context.active_cycle = frappe._dict({
                "name": active_cycle_doc.name,
                "admission_year": active_cycle_doc.admission_year,
                "cycle_start_date": frappe.utils.getdate(active_cycle_doc.cycle_start_date) if active_cycle_doc.cycle_start_date else None,
                "cycle_end_date": frappe.utils.getdate(active_cycle_doc.cycle_end_date) if active_cycle_doc.cycle_end_date else None,
            "application_start_date": frappe.utils.getdate(active_cycle_doc.application_start_date) if active_cycle_doc.application_start_date else None,
            "application_end_date": frappe.utils.getdate(active_cycle_doc.application_end_date) if active_cycle_doc.application_end_date else None,
                "application_end": active_cycle_doc.application_end_date
            })
            context.admission_cycle = active_cycle_doc.name
            context.admission_year = active_cycle_doc.admission_year
        else:
            context.active_cycle = None
            context.admission_cycle = None
    except Exception:
        context.active_cycle = None
        context.admission_cycle = None
    # Active cycle details for detail view
    if context.active_cycle:
        context.admission_cycle = context.active_cycle.name
        # admission_year might not be in context.active_cycle if not fetched in get_context
        # but Admission Cycle doc has it.
        try:
            context.admission_year = frappe.db.get_value("Admission Cycle", context.active_cycle.name, "admission_year")
        except:
            context.admission_year = None
    else:
        context.admission_cycle = None
        context.admission_year = None

    # Eligibility Rules
    try:
        rules = []
        if prog_name and context.active_cycle:
            mappings = frappe.get_all(
                "Eligibility Rule Mapping",
                filters={
                    "program": prog_name,
                    "admission_cycle": context.active_cycle.name,
                    "is_active": 1
                },
                fields=["name"]
            )
            
            for mapping in mappings:
                mapping_doc = frappe.get_doc("Eligibility Rule Mapping", mapping.name)
                for r_row in mapping_doc.rule:
                    rule_doc = frappe.get_doc("Eligibility Rule", r_row.rule)
                    if rule_doc.is_active:
                        rules.append({
                            "rule_name": rule_doc.rule_name,
                            "qualification_level": rule_doc.qualification_level,
                            "rule_type": rule_doc.rule_type,
                            "required_cgpa": rule_doc.required_cgpa,
                            "required_percentage": rule_doc.required_percentage,
                            "description": rule_doc.description
                        })
        context.eligibility_rules = rules
    except Exception as ex:
        frappe.log_error(str(ex), "prog_detail:eligibility_rules")
        context.eligibility_rules = []

    context.today = frappe.utils.getdate(frappe.utils.today())

    # ── user's existing application for this specific program ──
    context.user_app_name   = ""
    context.user_app_status = ""
    if frappe.session.user and frappe.session.user != "Guest":
        try:
            filters = {
                "email":   frappe.session.user,
                "program": prog.name
            }
            if context.active_cycle:
                filters["admission_cycle"] = context.active_cycle.name

            _recs = frappe.get_all(
                "Applicant",
                filters=filters,
                fields=["name", "status"],
                order_by="creation desc",
                limit=1
            )
            if not _recs:
                # fallback: scan all user apps for program name match in this cycle
                f2 = {"email": frappe.session.user}
                if context.active_cycle:
                    f2["admission_cycle"] = context.active_cycle.name

                _all = frappe.get_all(
                    "Applicant",
                    filters=f2,
                    fields=["name", "program", "status"],
                    order_by="creation desc",
                    limit=30
                )
                for _a in _all:
                    _p = (_a.get("program") or "").strip().lower()
                    _t = (prog.name or "").strip().lower()
                    _s = (context.get("prog_slug") or "").strip().lower()
                    if _p == _t or _p == _s:
                        _recs = [_a]
                        break
            if _recs:
                context.user_app_name   = _recs[0].get("name") or ""
                context.user_app_status = _recs[0].get("status") or ""
        except Exception as _ex:
            frappe.log_error(title="prog_detail_app_lookup", message=str(_ex))

    # Support email
    try:
        pc = context.portal_config
        context.support_email = (
            (_pf(pc,"support_email") if pc else "") or
            "admissions@nlsiu.ac.in"
        )
    except Exception:
        context.support_email = "admissions@nlsiu.ac.in"

    ac_campus = ""
    ac_intake = ""
    ac_prog_level = (gf("level_of_study") or "").strip()
    # Seat-limit flags for the listing and detail views.
    context.prog_seats_full = False
    context.prog_seats_almost_full = False
    context.prog_seats_remaining = None
    if prog_name and context.active_cycle:
        acp = frappe.db.get_value(
            "Admission Cycle Program",
            {"parent": context.active_cycle.name, "program": prog_name, "is_active": 1},
            ["campus", "intake_type", "program_level", "max_applications", "application_count"],
            as_dict=True,
        )
        if acp:
            ac_campus = (acp.get("campus") or "").strip()
            ac_intake = (acp.get("intake_type") or "").strip()
            if acp.get("program_level"):
                ac_prog_level = (acp.get("program_level") or "").strip()

            max_apps = int(acp.get("max_applications") or 0)
            received = int(acp.get("application_count") or 0)

            # If max_applications is 0, assume there is no limitation for intake.
            if max_apps > 0:
                context.prog_seats_remaining = max(0, max_apps - received)
                context.prog_seats_full = received >= max_apps
                pct = round((received / max_apps) * 100) if max_apps else 0
                context.prog_seats_almost_full = (not context.prog_seats_full) and pct >= 90

    _cn = context.active_cycle.name if context.active_cycle else ""
    _ay = (context.active_cycle.get("admission_year") if context.active_cycle else "") or ""
    _aac = (context.active_cycle.get("academic_year") if context.active_cycle else "") or ""

    context.apply_web_form_url = build_applicant_form_new_url(
        slug or "",
        _cn,
        campus=ac_campus,
        intake_type=ac_intake,
        admission_year=_ay,
        academic_year=_aac,
        program_level=ac_prog_level,
    )
    context.apply_web_form_login_url = build_login_redirect_to_applicant_form_new(
        slug or "",
        _cn,
        campus=ac_campus,
        intake_type=ac_intake,
        admission_year=_ay,
        academic_year=_aac,
        program_level=ac_prog_level,
    )


def _pf(obj, field):
    """Safe field accessor for both dicts and Frappe Document rows."""
    try:
        if hasattr(obj, "get"):
            return obj.get(field)
        return getattr(obj, field, None)
    except Exception:
        return None


def _set_empty_pd_context(context, slug):
    for k in ["prog_name","prog_level","prog_duration","prog_credits",
              "prog_dept","prog_hero","prog_image","prog_description","prog_intake",
              "prog_eligibility","prog_app_fee","prog_deadline","prog_brochure"]:
        setattr(context, k, "")
    context.prog_slug        = slug
    context.prog_media       = []
    context.prog_images      = []
    context.prog_videos      = []
    context.prog_curriculum  = []
    context.prog_career      = []
    context.prog_faculty     = []
    context.eligibility_rules = []
    context.active_cycle     = None
    context.admission_cycle  = None
    context.admission_year   = None
    context.support_email    = "admissions@nlsiu.ac.in"
    context.apply_web_form_url = "/admission"
    context.apply_web_form_login_url = "/admission/login?redirect-to=/admission"
    context.allow_multiple_applications = False

def get_context(context):
    if frappe.session.user and frappe.session.user != "Guest":
        roles = frappe.get_roles(frappe.session.user)
        if "PACE Applicant" in roles and "Applicant" not in roles and "System Manager" not in roles:
            frappe.local.flags.redirect_location = "/pace"
            raise frappe.Redirect
            
    # ── Route detection: /admission vs /admission/[slug] ─────────────
    _slug = ""
    try:
        _path = (
            getattr(frappe.local, "path_info", "") or
            (frappe.request.path
             if hasattr(frappe, "request") and frappe.request else "")
        )
        _parts = [p for p in _path.strip("/").split("/") if p]
        # /admission/ba-llb-hons → ['admission', 'ba-llb-hons']
        if len(_parts) == 2 and _parts[0] == "admission":
            _slug = _parts[1]
            if _slug == "login":
                _slug = ""
    except Exception:
        _slug = ""

    # ── 1. Active Admission Cycle ────────────────────────────────────
    # Use db.get_value, not get_doc: public /admission is often loaded as Guest;
    # get_doc enforces DocType read permission and returns 500 on live.
    active_cycle = None
    try:
        active_cycle_name = frappe.db.get_value("Admission Cycle", {"status": "Active"}, "name")
        if active_cycle_name:
            cycle_fields = [
                "cycle_start_date",
                "cycle_end_date",
                "application_start_date",
                "application_end_date",
                "allow_multiple_applications",
                "admission_year",
                "academic_year",
            ]
            if frappe.db.has_column("Admission Cycle", "application_form_type"):
                cycle_fields.append("application_form_type")
            row = frappe.db.get_value(
                "Admission Cycle",
                active_cycle_name,
                cycle_fields,
                as_dict=True,
            ) or {}
            active_cycle = frappe._dict({
                "name": active_cycle_name,
                "cycle_start_date": frappe.utils.getdate(row.get("cycle_start_date"))
                if row.get("cycle_start_date")
                else None,
                "cycle_end_date": frappe.utils.getdate(row.get("cycle_end_date"))
                if row.get("cycle_end_date")
                else None,
                "application_start_date": frappe.utils.getdate(row.get("application_start_date"))
                if row.get("application_start_date")
                else None,
                "application_end_date": frappe.utils.getdate(row.get("application_end_date"))
                if row.get("application_end_date")
                else None,
                "application_end": None,
                "allow_multiple_applications": int(row.get("allow_multiple_applications") or 0),
                "admission_year": row.get("admission_year") or "",
                "academic_year": row.get("academic_year") or "",
                "application_form_type": row.get("application_form_type") or "",
            })
    except Exception:
        frappe.log_error(frappe.get_traceback(), "admission get_context: active_cycle")
        active_cycle = None

    context.active_cycle = active_cycle
    context.allow_multiple_applications = bool(
        active_cycle.get("allow_multiple_applications")
    ) if active_cycle else False
    context.today = frappe.utils.getdate(frappe.utils.today())

    # ── 2. Is application window open? ───────────────────────────────
    app_open = False
    if active_cycle:
        _start = active_cycle.get('application_start_date') or active_cycle.get('cycle_start_date')
        _end = active_cycle.get('application_end_date') or active_cycle.get('cycle_end_date')
        if (not _start or context.today >= _start) and (not _end or context.today <= _end):
            app_open = True
    context.app_open = app_open

    # ── 3. user_app_map: program_name → {app_name, status} ──
    context.user_app_map = {}
    context.has_any_application = False
    if frappe.session.user and frappe.session.user != "Guest":
        try:
            filters = {"email": frappe.session.user}
            if active_cycle:
                filters["admission_cycle"] = active_cycle.name

            _uapps = frappe.get_all(
                "Applicant",
                filters=filters,
                fields=["name", "program", "status"],
                order_by="creation desc",
                limit=50
            )
            for _ua in _uapps:
                _key = (_ua.get("program") or "").strip()
                if _key and _key not in context.user_app_map:
                    context.user_app_map[_key] = {
                        "app_name": _ua.get("name") or "",
                        "status":   _ua.get("status") or ""
                    }
            if context.user_app_map:
                context.has_any_application = True
        except Exception:
            context.user_app_map = {}

    if _slug:
        _load_program_detail(context, _slug)
        context.show_detail = True
        context.title = (context.prog_name or "Programme") + " — Admissions"
        return   # ← exit early, index.html renders detail view

    context.show_detail = False

    from slcm.admission.utils.portal import get_portal_config

    # ── 4. Portal Config ─────────────────────────────────────────────
    portal_config = get_portal_config()
    context.portal_config = portal_config

    # Social media links from Portal Social Link child table
    try:
        context.social_links = [
            row for row in (portal_config.get("social_links") or [])
            if (row.get("is_active") if hasattr(row, 'get') else getattr(row, 'is_active', 1))
        ] if portal_config else []
    except Exception:
        context.social_links = []

    # ── 5. Maintenance mode shortcut ────────────────────────────────
    if not portal_config.get("portal_active", 1):
        context.programs     = []
        context.stats        = {}
        context.announcements = []
        context.active_cycle  = None
        context.app_open      = False
        context.allow_multiple_applications = False
        context.no_cache      = 1
        context.title         = portal_config.get("portal_title", "Admissions")
        return

    # ── 3. Active Admission Cycle ────────────────────────────────────
    active_cycle_name = frappe.db.get_value("Admission Cycle", {"status": "Active"}, "name")
    if active_cycle_name:
        active_cycle_doc = frappe.get_doc("Admission Cycle", active_cycle_name, ignore_permissions=True)
        active_cycle = frappe._dict({
            "name": active_cycle_doc.name,
            "cycle_start_date": frappe.utils.getdate(active_cycle_doc.cycle_start_date) if active_cycle_doc.cycle_start_date else None,
            "cycle_end_date": frappe.utils.getdate(active_cycle_doc.cycle_end_date) if active_cycle_doc.cycle_end_date else None,
            "application_start_date": frappe.utils.getdate(active_cycle_doc.application_start_date) if active_cycle_doc.application_start_date else None,
            "application_end_date": frappe.utils.getdate(active_cycle_doc.application_end_date) if active_cycle_doc.application_end_date else None,
            "application_end": active_cycle_doc.application_end_date
        })
    else:
        active_cycle = None

    context.today = frappe.utils.getdate(frappe.utils.today())

    # ── 4. Is application window open? ───────────────────────────────
    app_open = False
    if active_cycle:
        _start = active_cycle.get('application_start_date') or active_cycle.get('cycle_start_date')
        _end = active_cycle.get('application_end_date') or active_cycle.get('cycle_end_date')
        if (not _start or context.today >= _start) and (not _end or context.today <= _end):
            app_open = True

    # ── 5. Programs & Announcements ──────────────────────────────────
    try:
        from slcm.admission.utils.portal import (
            get_active_programs, get_active_announcements, get_active_events
        )
        programs      = get_active_programs() or []
        context.announcements = get_active_announcements(limit=20, target_audience=["Global", "Admission", "", None]) or []
        context.events = get_active_events(limit=20, target_audience=["Global", "Admission", "", None]) or []

        # Split announcements into non-event ones only
        context.announcements = [
            a for a in (context.announcements or [])
            if (a.get("announcement_type") or "") != "Event"
        ]

        # Stage-driven portal control
        active_cycle_name = active_cycle.name if active_cycle else ""
        
        context.programs = programs
    except Exception as e:
        frappe.log_error(title="Portal Index", message=f"fetch failed: {e}")
        context.programs = []
        context.announcements = []
        context.events = []

    # ── 6. Stats ─────────────────────────────────────────────────────
    try:
        from slcm.admission.utils.portal import api_get_portal_stats
        context.stats = api_get_portal_stats() or {}
    except Exception:
        context.stats = {}

    # Fallback: compute basic stats from what we already have
    if not context.stats or not context.stats.get('total_programs'):
        try:
            context.stats = {
                'total_programs': len(context.programs or []),
                'total_seats': sum(
                    int(p.get('seats') or p.get('total_seats') or 0)
                    for p in (context.programs or [])
                ) or None,
            }
        except Exception:
            context.stats = {'total_programs': len(context.programs or [])}

    context.active_cycle = active_cycle
    context.app_open     = app_open
    context.no_cache     = 1
    context.title        = portal_config.get("portal_title", "Admissions")
    context.build_applicant_form_new_url = build_applicant_form_new_url
    context.build_login_redirect_to_applicant_form_new = build_login_redirect_to_applicant_form_new

    # ── 7. New Portal Config Fields ──────────────────────────────────
    context.portal_tagline    = portal_config.get("portal_subtitle") or portal_config.get("portal_tagline") or ""
    context.institution_since = portal_config.get("institution_since") or ""
    context.hero_cta_label    = portal_config.get("hero_cta_label") or "Explore Programs"
    context.hero_cta2_label   = portal_config.get("hero_cta2_label") or "Virtual Tour"
    context.footer_address    = portal_config.get("footer_address") or ""
    context.footer_phone      = portal_config.get("footer_phone") or ""
    context.footer_email      = portal_config.get("footer_email") or portal_config.get("contact_email") or ""
    context.powerd_by         = portal_config.get("powerd_by") or "boscosoft"
    context.social_links      = portal_config.get("social_links") or []

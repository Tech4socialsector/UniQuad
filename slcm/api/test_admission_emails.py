import frappe
from frappe.utils import get_url, nowdate, add_days

def get_complete_mock_context(recipient="edwinstephano@dbcyelagiri.edu.in"):
    """
    Builds a rich mock data context satisfying all variables across all admission email templates,
    both at top-level and nested within `doc`, `program`, `campus`, `admission_cycle`, etc.
    """
    mock_doc = frappe._dict({
        "name": "APP-2026-41546",
        "applicant": "APP-2026-41546",
        "applicant_id": "APP-2026-41546",
        "applicant_document_id": "APP-2026-41546",
        "candidate_name": "EDWIN STEPHANO",
        "full_name": "EDWIN STEPHANO",
        "applicant_name": "EDWIN STEPHANO",
        "email": recipient,
        "program": "5-Year B.A., LL.B. (Hons.)",
        "program_name": "5-Year B.A., LL.B. (Hons.)",
        "programme": "3-Year LL.B. (Hons.)",
        "campus": "Bengaluru",
        "campus_name": "Bengaluru Campus",
        "admission_cycle": "NLSAT 2026-2027",
        "academic_year": "2026-2027",
        "admission_year": "2026",
        "status": "Submitted",
        "allocation_status": "Allocated",
        "selection_status": "Selected",
        "result_status": "Eligible / Selected",
        "interview_result_status": "Selected for Admission",
        "interview_score": "42/50",
        "et_source": "NLSAT 2026",
        "interview_list": "Interview Panel A",
        "allocated_category": "General Merit",
        "overall_rank": "042",
        "total_score": "88.5",
        "offer_id": "OFF-2026-0042",
        "entrance_test_name": "NLSAT 2026",
        "entrance_test_list": "NLSAT Centre Allocation Round 1",
        "allocation_date": add_days(nowdate(), 10),
        "re_allocation_date": add_days(nowdate(), 14),
        "re_entrance_test_name": "NLSAT 2026 (Rescheduled Session)",
        "reschedule_reason": "Administrative realignment of schedule",
        "start_time": "10:00:00",
        "end_time": "12:30:00",
        "is_reallocation": False,
        "old_center_name": "Delhi Public School, R.K. Puram, New Delhi",
        "payable_amount": 50000,
        "application_fee_amount": 2500,
        "payment_deadline": add_days(nowdate(), 7),
        "confirmation_fee_deadline": add_days(nowdate(), 5),
        "offer_acceptance_deadline": add_days(nowdate(), 5),
        "interview_address": "Main Academic Block, Board Room 2, NLSIU Bengaluru",
        "re_interview_address": "Online via Zoom (Link shared separately)",
        "assigned_preferences": [
            frappe._dict({"center_name": "St. Joseph's College, Bengaluru", "provider": "Test Center A"}),
            frappe._dict({"center_name": "National Law School Campus, Bengaluru", "provider": "Test Center B"})
        ],
        "re_assigned_preferences": [
            frappe._dict({"center_name": "National Law School Campus, Bengaluru", "provider": "Test Center B"})
        ]
    })

    program_obj = frappe._dict({
        "name": "3-Year LL.B. (Hons.)",
        "program_name": "5-Year B.A., LL.B. (Hons.)",
        "department": "Department of Law",
        "program_duration": "3 Years",
        "program_level": "Undergraduate"
    })

    campus_obj = frappe._dict({
        "name": "Bengaluru",
        "campus_name": "Bengaluru Campus",
        "city": "Bengaluru",
        "state": "Karnataka",
        "contact_email": "admissions@nls.ac.in"
    })

    active_cycle_info = frappe.db.get_value(
        "Admission Cycle",
        {"status": "Active"},
        ["name", "application_end_date", "admission_year"],
        as_dict=True
    ) if frappe.db else None

    if active_cycle_info and active_cycle_info.application_end_date:
        app_end_date_str = frappe.utils.formatdate(active_cycle_info.application_end_date, "dd MMMM yyyy")
        admission_yr = str(active_cycle_info.admission_year or "2026")
        cycle_n = active_cycle_info.name
    else:
        app_end_date_str = "03 October 2026"
        admission_yr = "2026"
        cycle_n = "NLSAT 2026-2027"

    cycle_obj = frappe._dict({
        "name": cycle_n,
        "cycle_name": cycle_n,
        "admission_year": admission_yr
    })

    context = {
        "doc": mock_doc,
        "applicant_doc": mock_doc,
        "program": "5-Year B.A., LL.B. (Hons.)",
        "program_name": "5-Year B.A., LL.B. (Hons.)",
        "campus": campus_obj,
        "admission_cycle": cycle_n,
        "cycle_obj": cycle_obj,
        "full_name": "EDWIN STEPHANO",
        "candidate_name": "EDWIN STEPHANO",
        "applicant_name": "EDWIN STEPHANO",
        "applicant_id": "APP-2026-41546",
        "applicant_document_id": "APP-2026-41546",
        "application_id": "APP-2026-41546",
        "admission_year": admission_yr,
        "days_left": "5",
        "app_end_date_formatted": app_end_date_str,
        "cycle_end_date": app_end_date_str,
        "application_end_date": app_end_date_str,
        "program_names": "3-Year LL.B. (Hons.), 5-Year B.A., LL.B. (Hons.), and Master of Public Policy",
        "application_fee_amount": "₹2,500",
        "payable_amount": "₹50,000",
        "institution_name": "National Law School of India University",
        "portal_url": get_url("/nlsat/dashboard"),
        "portal_link": get_url("/nlsat/dashboard"),
        "admission_portal_url": get_url("/nlsatadmissions/login#login"),
        "set_password_link": get_url("/update-password?key=sample_demo_key_12345"),
        "login_url": get_url("/nlsatadmissions/login#login"),
        "link_expiry_hours": 24,
        "overall_rank": "042",
        "total_score": "88.5",
        "published_date": "16 October 2026",
        "staff_name": "Dr. Ramesh Kumar (Faculty Panel Chair)",
        "interview_address": "Main Academic Block, Board Room 2, NLSIU Bengaluru",
        "reschedule_reason": "Administrative realignment of schedule",
        "students": [mock_doc],
        "scheme_name": "Post-Matric Merit-cum-Means Scholarship",
        "benefit_amount": "₹1,20,000",
        "rejection_reason": "Income certificate validity required",
        "razorpay_payment_id": "pay_Oidk9284ksdf9",
        "razorpay_refund_id": "rfnd_Oidk9284ksdf9",
        "refund_amount_str": "₹2,500",
        "is_rescheduled": False
    }
    return context


@frappe.whitelist()
def send_single_test_email(template_name, recipient="edwinstephano@dbcyelagiri.edu.in"):
    """
    Sends a test email for ONE specific admission email template.
    Usage:
        bench --site slcm.com execute slcm.api.test_admission_emails.send_single_test_email --args '["Application Submitted Email", "edwinstephano@dbcyelagiri.edu.in"]'
    """
    context = get_complete_mock_context(recipient)

    if frappe.db.exists("Email Template", template_name):
        tmpl = frappe.get_doc("Email Template", template_name)
        html = tmpl.response_html or tmpl.response or tmpl.message or ""
        subject = tmpl.subject or template_name
    elif template_name in ["Applicant Registration Email", "Signup / Registration Email"]:
        html = frappe.db.get_single_value("Institution Settings", "signup_email_template")
        subject = frappe.db.get_single_value("Institution Settings", "signup_email_subject") or "Welcome to NLSIU - Set Your Password"
        if not html:
            with open("/home/bsoft/frappe-bench/apps/slcm/slcm/admission/Email Template NLSAT/Applicant Registration Email.html") as f:
                html = f.read()
    else:
        # Check files in Email Template NLSAT
        file_path = f"/home/bsoft/frappe-bench/apps/slcm/slcm/admission/Email Template NLSAT/{template_name}.html"
        if frappe.os.path.exists(file_path):
            with open(file_path) as f:
                html = f.read()
            subject = template_name
        else:
            return {"status": "Error", "message": f"Template '{template_name}' not found in database or file system."}

    rendered_msg = frappe.render_template(html, context)
    rendered_sub = frappe.render_template(subject, context)

    frappe.sendmail(
        recipients=[recipient],
        subject=f"[TEST] {rendered_sub}",
        message=rendered_msg,
        now=True
    )
    return {"status": "Success", "template": template_name, "recipient": recipient, "subject": rendered_sub}


@frappe.whitelist()
def sync_not_started_reminder_template():
    file_path = "/home/bsoft/frappe-bench/apps/slcm/slcm/admission/Email Template NLSAT/Applicant Not Started Application Reminder.html"
    with open(file_path, "r", encoding="utf-8") as f:
        html = f.read()

    new_subject = 'Reminder: Start Your Application Before {{ app_end_date_formatted or application_end_date or (frappe.utils.formatdate(frappe.db.get_value("Admission Cycle", {"status": "Active"}, "application_end_date"), "dd MMMM yyyy") if frappe.db.get_value("Admission Cycle", {"status": "Active"}, "application_end_date") else "") or "03 October 2026" }} — {{ institution_name or "National Law School of India University" }}'

    if frappe.db.exists("Email Template", "Applicant Not Started Application Reminder"):
        doc = frappe.get_doc("Email Template", "Applicant Not Started Application Reminder")
        doc.response = html
        doc.response_html = html
        doc.subject = new_subject
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return "Synced Email Template successfully"
    return "Not Found"


@frappe.whitelist()
def sync_all_standard_regards():
    import os, glob

    template_dir = "/home/bsoft/frappe-bench/apps/slcm/slcm/admission/Email Template NLSAT"
    files = sorted(glob.glob(f"{template_dir}/*.html"))
    count = 0

    for fpath in files:
        tname = os.path.basename(fpath).replace(".html", "").strip()
        with open(fpath, "r", encoding="utf-8") as f:
            html = f.read()

        if frappe.db.exists("Email Template", tname):
            frappe.db.set_value("Email Template", tname, {
                "response": html,
                "response_html": html,
                "use_html": 1
            }, update_modified=False)
            count += 1
        elif tname == "Applicant Application Rejected":
            doc = frappe.get_doc({
                "doctype": "Email Template",
                "name": tname,
                "enabled": 1,
                "use_html": 1,
                "subject": "Application Update: {{ rejection_reason or 'Not Eligible' }} — {{ candidate_name or 'Applicant' }}",
                "response": html,
                "response_html": html
            })
            doc.insert(ignore_permissions=True)
            frappe.db.set_value("Email Template", tname, {"response": html, "response_html": html}, update_modified=False)
            count += 1
    frappe.db.commit()
    return f"Synced {count} templates from HTML files to DB"


@frappe.whitelist()
def audit_all_templates():
    import os, glob, re, json

    template_dir = "/home/bsoft/frappe-bench/apps/slcm/slcm/admission/Email Template NLSAT"
    files = sorted(glob.glob(f"{template_dir}/*.html"))
    fixture_path = "/home/bsoft/frappe-bench/apps/slcm/slcm/fixtures/email_template.json"
    
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture_data = json.load(f)
    fixture_dict = {item.get("name"): item for item in fixture_data}

    print("=" * 80)
    print(f"COMPREHENSIVE ADMISSION EMAIL TEMPLATE AUDIT ({len(files)} TEMPLATES)")
    print("=" * 80)

    all_passed = True

    for fpath in files:
        tname = os.path.basename(fpath).replace(".html", "").strip()
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        norm = " ".join(content.split())
        issues = []

        # 1. Header Checks
        if "National Law School of India University" not in norm:
            issues.append("Missing University Name in Header")
        if "Bengaluru" not in norm:
            issues.append("Missing 'Bengaluru' in Header")
        if "NLSIU-logo.png" not in norm and "logo" not in norm:
            issues.append("Missing Logo in Header")
        if "#920c24" not in norm:
            issues.append("Missing Official Crimson styling (#920c24)")

        # 2. Greeting Checks
        if not re.search(r"Dear\s+\{\{", norm):
            issues.append("Missing 'Dear {{ ... }}' greeting")

        # 3. Footer & Regards Checks
        regards_pat = r"Regards,\s*<br>\s*<strong>Admissions Office</strong>\s*<br>\s*National Law School of India University"
        if not re.search(regards_pat, content):
            issues.append("Regards signature does not match standard Admissions Office block")

        disclaimer_pat = r"This is a\s+system-generated email\.\s*Please do not reply to this message\."
        if not re.search(disclaimer_pat, norm):
            issues.append("System-generated disclaimer missing or malformed")

        if "nlsat.query@nls.ac.in" in norm:
            issues.append("Contains removed nlsat.query email")

        # 4. Jinja Syntax
        if len(re.findall(r"\{\{", content)) != len(re.findall(r"\}\}", content)):
            issues.append("Unbalanced {{ }} Jinja expressions")
        if len(re.findall(r"\{%", content)) != len(re.findall(r"%\}", content)):
            issues.append("Unbalanced {% %} Jinja blocks")

        # 5. Tag Balance
        for tag in ["html", "head", "body", "table", "tr", "td"]:
            if len(re.findall(rf"<{tag}[\s>]", content, re.I)) != len(re.findall(rf"</{tag}>", content, re.I)):
                issues.append(f"Unbalanced <{tag}> HTML tags")

        # 6. Database Sync Check
        if tname != "Applicant Registration Email":
            if not frappe.db.exists("Email Template", tname):
                issues.append("Missing in database (tabEmail Template)")
            else:
                db_doc = frappe.get_doc("Email Template", tname)
                if db_doc.response.strip() != content.strip():
                    issues.append("DB response out of sync with HTML file")
                if db_doc.response_html.strip() != content.strip():
                    issues.append("DB response_html out of sync with HTML file")

        # 7. Fixtures Check
        if tname != "Applicant Registration Email":
            if tname not in fixture_dict:
                issues.append("Missing in fixtures/email_template.json")
            else:
                fix_item = fixture_dict[tname]
                if fix_item.get("response", "").strip() != content.strip():
                    issues.append("fixtures response out of sync with HTML file")
                if fix_item.get("response_html", "").strip() != content.strip():
                    issues.append("fixtures response_html out of sync with HTML file")

        status_str = "✓ PASS (All checks OK)" if not issues else f"✗ FAIL: {', '.join(issues)}"
        if issues:
            all_passed = False
        print(f"[{tname[:40]:<40}] {status_str}")

    # Check Institution Settings signup template
    inst_signup = frappe.db.get_single_value("Institution Settings", "signup_email_template")
    inst_issues = []
    if inst_signup:
        inst_norm = " ".join(inst_signup.split())
        if "National Law School of India University" not in inst_norm:
            inst_issues.append("Missing Univ Name")
        if not re.search(r"Regards,\s*<br>\s*<strong>Admissions Office</strong>", inst_signup):
            inst_issues.append("Missing standard regards")
        if "system-generated email" not in inst_norm:
            inst_issues.append("Missing disclaimer")
    else:
        inst_issues.append("signup_email_template is empty")

    inst_status = "✓ PASS" if not inst_issues else f"✗ FAIL: {', '.join(inst_issues)}"
    print(f"[{'Institution Settings: signup_template':<40}] {inst_status}")

    print("=" * 80)
    if all_passed and not inst_issues:
        print("ALL TEMPLATES, HEADERS, FOOTERS, DB RECORDS, AND FIXTURES VERIFIED 100% CORRECT!")
    else:
        print("SOME ISSUES WERE DETECTED. PLEASE REVIEW THE DETAILS ABOVE.")
    print("=" * 80)
    return "Audit Complete: All Passed" if all_passed and not inst_issues else "Audit Found Issues"




"""
Sample data creation script for testing the ID Card module.
Run with:
    bench --site slcm.local execute slcm.setup.sample_data.create_sample_student
"""

import frappe


def create_sample_student():
    frappe.set_user("Administrator")

    # ------------------------------------------------------------------ #
    # 1. Department                                                         #
    # ------------------------------------------------------------------ #
    dept_name = "Computer Science & Engineering"
    if not frappe.db.exists("SLCM Department", dept_name):
        dept = frappe.get_doc({
            "doctype": "SLCM Department",
            "department_name": dept_name,
            "department_id": "CSE",
            "status": "Active",
        })
        dept.insert(ignore_permissions=True, ignore_mandatory=True)
        print(f"  [OK] Created Department: {dept.name}")
    else:
        dept = frappe.get_doc("SLCM Department", dept_name)
        print(f"  [--] Department exists:  {dept.name}")

    # ------------------------------------------------------------------ #
    # 2. Program                                                            #
    # ------------------------------------------------------------------ #
    program_name = "Bachelor of Technology - CSE"
    if not frappe.db.exists("Programme", program_name):
        prog = frappe.get_doc({
            "doctype": "Programme",
            "program_name": program_name,
            "program_code": "BTCSE",
            "program_shortcode": "BTech CSE",
            "department": dept.name,
            "level_of_study": "Undergraduate",
            "program_duration": 4,
            "program_status": "Active",
            "intake_type": "Direct Merit",
        })
        prog.insert(ignore_permissions=True, ignore_mandatory=True)
        print(f"  [OK] Created Program:    {prog.name}")
    else:
        prog = frappe.get_doc("Programme", program_name)
        print(f"  [--] Program exists:     {prog.name}")

    # ------------------------------------------------------------------ #
    # 3. Academic Year (reuse existing or create new)                      #
    # ------------------------------------------------------------------ #
    academic_year = frappe.db.get_value("Academic Year", {"name": "2025-2026"}, "name")
    if not academic_year:
        academic_year = frappe.db.get_value("Academic Year", {}, "name", order_by="creation desc")
    if not academic_year:
        ay = frappe.get_doc({
            "doctype": "Academic Year",
            "academic_year_name": "2025-2026",
            "academic_system": "Semester",
            "year_start_date": "2025-07-01",
            "year_end_date": "2026-06-30",
            "status": "Active",
        })
        ay.insert(ignore_permissions=True)
        academic_year = ay.name
        print(f"  [OK] Created Academic Year: {academic_year}")
    else:
        print(f"  [--] Academic Year exists:  {academic_year}")

    # ------------------------------------------------------------------ #
    # 4. Cohort                                                             #
    # ------------------------------------------------------------------ #
    cohort_name = "BTech CSE 2025 - Semester 1"
    if not frappe.db.exists("SLCM Batch", cohort_name):
        cohort = frappe.get_doc({
            "doctype": "SLCM Batch",
            "cohort_code": "BTCSE-2025-S1",
            "cohort_name": cohort_name,
            "program": prog.name,
            "academic_year": academic_year,
            "term_name": "Semester 1",
            "term_year": "1",
            "batch": "2025",
            "seat_limit": 60,
            "start_date": "2025-07-01",
            "end_date": "2029-06-30",
            "status": "Active",
        })
        cohort.insert(ignore_permissions=True, ignore_mandatory=True)
        print(f"  [OK] Created Cohort:     {cohort.name}")
    else:
        cohort = frappe.get_doc("SLCM Batch", cohort_name)
        print(f"  [--] Cohort exists:      {cohort.name}")

    # ------------------------------------------------------------------ #
    # 5. Gender master records (Frappe Link doctype)                        #
    # ------------------------------------------------------------------ #
    for g in ["Male", "Female", "Other"]:
        if not frappe.db.exists("Gender", g):
            frappe.get_doc({"doctype": "Gender", "gender": g}).insert(ignore_permissions=True)
            print(f"  [OK] Created Gender: {g}")

    # ------------------------------------------------------------------ #
    # 6. Workflow State for registration_status                            #
    # ------------------------------------------------------------------ #
    for ws in ["Draft", "Selected", "Pending REGO", "Pending FINO", "Pending Registration",
               "Pending Print & Scan", "Pending Residences", "Pending IT",
               "Final Verification REGO", "Completed", "Re-Open"]:
        if not frappe.db.exists("Workflow State", ws):
            frappe.get_doc({
                "doctype": "Workflow State",
                "workflow_state_name": ws,
                "style": "Success" if ws == "Completed" else "",
            }).insert(ignore_permissions=True)
            print(f"  [OK] Created Workflow State: {ws}")

    # ------------------------------------------------------------------ #
    # 7. Student Master                                                     #
    # ------------------------------------------------------------------ #
    existing = frappe.db.get_value("Student Master", {"application_number": "APP-SAMPLE-001"}, "name")
    if existing:
        print(f"\n  [--] Student already exists: {existing}")
        _print_links(existing)
        frappe.db.commit()
        return

    student = frappe.get_doc({
        "doctype": "Student Master",
        "naming_series": "STUD-.YYYY.-",

        # ── Registration ──────────────────────────────────────────────
        "application_number": "APP-SAMPLE-001",
        "admission_type": "Regular",
        "quota": "General",
        "academic_year": academic_year,
        "academic_status": "Active",
        "official_email_id": "arjun.sharma@slcm.local",

        # ── Programme Mapping ─────────────────────────────────────────
        "department": dept.name,
        "programme": cohort.name,
        "batch_year": "2025",

        # ── Personal ──────────────────────────────────────────────────
        "first_name": "Arjun",
        "middle_name": "Kumar",
        "last_name": "Sharma",
        "dob": "2005-03-15",
        "gender": "Male",
        "marital_status": "Unmarried",
        "nationality": "Indian",
        "religion": "Hindu",
        "blood_group": "B+",
        "country": "India",
        "city": "Bengaluru",
        "pincode": "560001",
        "aadhaar_number": "1234 5678 9012",

        # ── Contact ───────────────────────────────────────────────────
        "email": "arjun.sharma@student.slcm.local",
        "personal_email": "arjun.sharma@gmail.com",
        "phone": "+91 9876543210",
        "emergency_contact": "+91 9876543211",
        "present_address": "12, MG Road, Bengaluru - 560001",
        "permanent_address": "45, Lake View, Mysuru - 570001",

        # ── Class X ───────────────────────────────────────────────────
        "class_x_completion_year": "2020",
        "class_x_percentage": 91.5,
        "class_x_school": "Delhi Public School, Bengaluru",
        "class_x_board": "CBSE",

        # ── Class XII ─────────────────────────────────────────────────
        "class_xii_exam_name": "CBSE Senior Secondary",
        "class_xii_completion_year": "2022",
        "class_xii_school": "Delhi Public School, Bengaluru",
        "class_xii_board": "CBSE",
        "class_xii_percentage": 88.2,

        # ── UG ────────────────────────────────────────────────────────
        "ug_degree_completed": "No",

        # ── Finance ───────────────────────────────────────────────────
        "applying_scholarship": "No",
        "fee_payment_status": "Paid",
        "total_program_fee": 400000,
        "total_paid_amount": 400000,
        "outstanding_balance": 0,

        # ── Documents ─────────────────────────────────────────────────
        # Using Frappe's bundled avatar image as placeholder photo
        "passport_size_photo": "/assets/frappe/images/default-avatar.png",

        # ── Account / Status ──────────────────────────────────────────
        "student_status": "Active",
        "registration_status": "Completed",
        "id_card_issued": 0,
    })

    student.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
    frappe.db.commit()

    print(f"\n{'='*60}")
    print(f"  Sample Student created!")
    print(f"  Student ID   : {student.name}")
    print(f"  Name         : Arjun Kumar Sharma")
    print(f"  Department   : {dept.name}")
    print(f"  Cohort       : {cohort.name}")
    print(f"  Academic Year: {academic_year}")
    _print_links(student.name)


def _print_links(student_name):
    print(f"\n{'='*60}")
    print(f"  USEFUL LINKS:")
    print(f"  Student Record : /app/student-master/{student_name}")
    print(f"  New ID Card    : /app/id-card-generation/new-id-card-generation-1")
    print(f"  ID Card List   : /app/id-card-generation")
    print(f"{'='*60}")

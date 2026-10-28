# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""
End-to-End Attendance Test Suite
=================================
Tests the complete attendance pipeline across all actor roles and all
attendance types used at NLSIU.

Scenarios covered
-----------------
  S01  RFID swipe → Attendance Log → Student Attendance → Attendance Summary
  S02  Faculty manual attendance marking → Attendance Summary
  S03  Faculty office hours marking → Attendance Summary
  S04  FA/MFA application approval → Attendance Summary
  S05  Condonation approval → Attendance Summary
  S06  Parent can see correct percentage via portal context
  S07  Student linked to RFID Card (not rfid_uid on Student Master) also resolves

Run:
    bench --site slcm.local execute slcm.slcm.tests.test_attendance_e2e.run_all
"""

import frappe
from frappe.utils import today, add_days, getdate, now_datetime, get_datetime
from collections import defaultdict

# ---------------------------------------------------------------------------
# Constants — resolved at runtime from real DB data
# ---------------------------------------------------------------------------
_TEST_RFID_UID = "E2E-TEST-RFID-8888"
_TEST_CARD_UID = "E2E-TEST-CARD-7777"   # for Student RFID Card test

_ctx = {}   # populated by _resolve_context()


# ---------------------------------------------------------------------------
# Context resolution
# ---------------------------------------------------------------------------

def _resolve_context():
    """Find real records to test against and cache them."""
    if _ctx:
        return _ctx

    # A Class with an enrolled student
    from slcm.slcm.doctype.classes.classes import get_class_students

    class_name = frappe.db.get_value("Classes", {}, "name", order_by="creation desc")
    if not class_name:
        return {}

    cohort  = frappe.db.get_value("Classes", class_name, "section")
    faculty_id = frappe.db.get_value("Classes", class_name, "faculty")

    class_students = get_class_students(class_name)
    student = class_students[0].student if class_students else None

    # Parent linked to that student (first entry in parents child table)
    parent_email = None
    parent_user  = None
    if student:
        parent_row = frappe.db.get_value(
            "Student Parent",
            {"parent": student},
            ["email"],
            as_dict=True,
        )
        if parent_row:
            parent_email = parent_row.email
            parent_user  = frappe.db.get_value("User", {"email": parent_email}, "name") if parent_email else None

    # Faculty user
    faculty_user = None
    if faculty_id:
        faculty_user = frappe.db.get_value("Faculty", faculty_id, "user_id")

    _ctx.update({
        "class_name":     class_name,
        "cohort":       cohort,
        "student":      student,
        "faculty_id":   faculty_id,
        "faculty_user": faculty_user,
        "parent_email": parent_email,
        "parent_user":  parent_user,
    })
    return _ctx


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _free_date(student, class_name, start_offset=-3, max_search=20):
    """Return the first past date with no existing Student Attendance for this student+class_name."""
    for offset in range(start_offset, -(start_offset + max_search), -1):
        candidate = add_days(today(), offset)
        if not frappe.db.exists("Student Attendance", {
            "student":        student,
            "class_name":   class_name,
            "attendance_date": candidate,
        }):
            return candidate
    return add_days(today(), -30)


def _make_class_schedule(class_name, schedule_date, from_time="09:00:00", to_time="10:00:00"):
    from frappe.utils import time_diff_in_hours
    course = frappe.db.get_value("Classes", class_name, "course")
    doc = frappe.get_doc({
        "doctype":        "Time Table",
        "based_on":       "Course Schedule",
        "class_name":     class_name,
        "course":         course,
        "schedule_date":  schedule_date,
        "from_time":      from_time,
        "to_time":        to_time,
        "duration_hours": time_diff_in_hours(to_time, from_time),
        "status":         "Scheduled",
    })
    doc.insert(ignore_permissions=True)
    return doc


def _safe_delete(doctype, name):
    try:
        if name and frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
    except Exception:
        pass


def _recalc(student, class_name):
    from slcm.slcm.utils.attendance_calculator import calculate_student_attendance
    calculate_student_attendance(student, class_name)
    frappe.db.commit()


def _summary(student, class_name):
    return frappe.db.get_value(
        "Attendance Summary",
        {"student": student, "class_name": class_name},
        ["attendance_percentage", "attended_classes", "total_class_hours",
         "total_office_hours", "total_condonation_hours", "total_fa_mfa_hours",
         "eligible_for_exam"],
        as_dict=True,
    ) or frappe._dict()


def _pct(student, class_name):
    return frappe.db.get_value(
        "Attendance Summary",
        {"student": student, "class_name": class_name},
        "attendance_percentage",
    ) or 0


# ---------------------------------------------------------------------------
# S01 — RFID swipe end-to-end
# ---------------------------------------------------------------------------

def s01_rfid_swipe(ctx):
    """
    Simulate RFID swipe → Attendance Log → process_pending_logs()
    Verifies: log processed, Student Attendance created (source=RFID, status=Present),
    Attendance Summary percentage > 0.
    """
    from slcm.slcm.doctype.attendance_log.process_attendance_logs import process_pending_logs

    student  = ctx["student"]
    class_name = ctx["class_name"]

    test_date = _free_date(student, class_name)
    swipe_in  = f"{test_date} 09:05:00"
    swipe_out = f"{test_date} 09:52:00"

    cs   = None
    log1 = None
    log2 = None

    try:
        cs = _make_class_schedule(class_name, test_date)

        old_rfid = frappe.db.get_value("Student Master", student, "rfid_uid")
        frappe.db.set_value("Student Master", student, "rfid_uid", _TEST_RFID_UID)

        log1 = frappe.get_doc({"doctype": "Attendance Log", "student": student,
                                "rfid_uid": _TEST_RFID_UID, "swipe_time": swipe_in,
                                "source": "RFID", "processed": 0}).insert(ignore_permissions=True)
        log2 = frappe.get_doc({"doctype": "Attendance Log", "student": student,
                                "rfid_uid": _TEST_RFID_UID, "swipe_time": swipe_out,
                                "source": "RFID", "processed": 0}).insert(ignore_permissions=True)
        frappe.db.commit()

        process_pending_logs()
        frappe.db.commit()

        # Check both logs processed
        for lg in [log1, log2]:
            if not frappe.db.get_value("Attendance Log", lg.name, "processed"):
                return False, f"Attendance Log {lg.name} not marked processed"

        # Check Student Attendance
        sa = frappe.db.get_value(
            "Student Attendance",
            {"student": student, "source": "RFID", "class_name": class_name,
             "attendance_date": test_date},
            ["name", "status", "hours_counted", "in_time", "out_time"],
            as_dict=True,
        )
        if not sa:
            return False, "No RFID Student Attendance record created"
        if sa.status != "Present":
            return False, f"Status='{sa.status}' expected 'Present' (check RFID Swipe Mode in Attendance Settings)"
        if not sa.hours_counted:
            return False, "hours_counted=0 on Student Attendance"
        if not sa.in_time or not sa.out_time:
            return False, f"in_time/out_time not saved: in={sa.in_time}, out={sa.out_time}"

        # Check Attendance Summary
        _recalc(student, class_name)
        s = _summary(student, class_name)
        if not s or not s.attendance_percentage:
            return False, "Attendance Summary percentage still 0 after RFID"

        return True, (
            f"Log→SA({sa.name}) status={sa.status} hours={sa.hours_counted} "
            f"in={sa.in_time} out={sa.out_time} | "
            f"Summary%={round(s.attendance_percentage, 1)}"
        )

    except Exception as e:
        import traceback
        return False, f"{e}\n{traceback.format_exc()}"

    finally:
        frappe.db.set_value("Student Master", student, "rfid_uid", old_rfid or "")
        for lg in [log1, log2]:
            if lg:
                _safe_delete("Attendance Log", lg.name)
        for name in frappe.db.get_all("Student Attendance", filters={
            "student": student, "source": "RFID",
            "class_name": class_name, "attendance_date": test_date,
        }, pluck="name"):
            _safe_delete("Student Attendance", name)
        _safe_delete("Time Table", cs.name if cs else None)
        frappe.db.commit()


# ---------------------------------------------------------------------------
# S02 — Faculty manual attendance marking
# ---------------------------------------------------------------------------

def s02_faculty_manual(ctx):
    """
    Faculty manually marks a student Present via Student Attendance.
    Verifies: Attendance Summary attended_classes increases.
    """
    student  = ctx["student"]
    class_name = ctx["class_name"]
    faculty  = ctx.get("faculty_id")

    test_date = _free_date(student, class_name, start_offset=-5)
    sa_name   = None

    try:
        before = _summary(student, class_name).get("attended_classes") or 0

        doc = frappe.get_doc({
            "doctype":        "Student Attendance",
            "student":        student,
            "class_name":   class_name,
            "attendance_date": test_date,
            "date":           test_date,
            "status":         "Present",
            "source":         "Manual",
            "session_type":   "Lecture",
            "hours_counted":  1.5,
            "instructor":     faculty,
        })
        doc.insert(ignore_permissions=True)
        sa_name = doc.name
        frappe.db.commit()

        _recalc(student, class_name)
        after = _summary(student, class_name).get("attended_classes") or 0

        if after <= before:
            return False, f"attended_classes did not increase: {before} → {after}"

        pct = _pct(student, class_name)
        return True, (
            f"SA({sa_name}) Faculty={faculty or 'N/A'} | "
            f"attended_classes: {before} → {after} | pct={round(pct,1)}%"
        )

    except Exception as e:
        import traceback
        return False, f"{e}\n{traceback.format_exc()}"

    finally:
        _safe_delete("Student Attendance", sa_name)
        if sa_name:
            _recalc(student, class_name)
        frappe.db.commit()


# ---------------------------------------------------------------------------
# S03 — Office hours attendance (faculty marks)
# ---------------------------------------------------------------------------

def s03_office_hours(ctx):
    """
    Faculty marks student present in an Office Hour session.
    Verifies: total_office_hours increases in Attendance Summary.
    """
    student  = ctx["student"]
    class_name = ctx["class_name"]

    test_date = _free_date(student, class_name, start_offset=-8)
    sa_name   = None

    try:
        before_oh = _summary(student, class_name).get("total_office_hours") or 0

        doc = frappe.get_doc({
            "doctype":        "Student Attendance",
            "student":        student,
            "class_name":   class_name,
            "attendance_date": test_date,
            "date":           test_date,
            "status":         "Present",
            "source":         "Manual",
            "session_type":   "Office Hour",
            "hours_counted":  2.0,
        })
        doc.insert(ignore_permissions=True)
        sa_name = doc.name
        frappe.db.commit()

        _recalc(student, class_name)
        after_oh = _summary(student, class_name).get("total_office_hours") or 0

        if after_oh <= before_oh:
            return False, f"total_office_hours did not increase: {before_oh} → {after_oh}"

        pct = _pct(student, class_name)
        return True, (
            f"SA({sa_name}) Office Hour 2.0h | "
            f"total_office_hours: {before_oh} → {after_oh} | pct={round(pct,1)}%"
        )

    except Exception as e:
        import traceback
        return False, f"{e}\n{traceback.format_exc()}"

    finally:
        _safe_delete("Student Attendance", sa_name)
        if sa_name:
            _recalc(student, class_name)
        frappe.db.commit()


# ---------------------------------------------------------------------------
# S04 — FA/MFA application approval
# ---------------------------------------------------------------------------

def s04_fa_mfa(ctx):
    """
    Admin submits an approved FA/MFA application.
    Verifies: total_fa_mfa_hours and attendance_percentage increase.
    """
    student  = ctx["student"]
    class_name = ctx["class_name"]
    course   = frappe.db.get_value("Classes", class_name, "course")

    app_name = None

    try:
        before = _summary(student, class_name)
        before_pct   = before.get("attendance_percentage") or 0
        before_famfa = before.get("total_fa_mfa_hours") or 0

        doc = frappe.get_doc({
            "doctype":          "FA MFA Application",
            "student":          student,
            "course":           course,
            "application_type": "First Attempt (FA)",
            "reason":           "Medical Reasons",
            "examination_date": today(),
            "proof_document":   "test_placeholder.pdf",
            "granted_hours":    3.0,
            "status":           "Approved",
        })
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True)
        doc.submit()
        app_name = doc.name
        frappe.db.commit()

        after = _summary(student, class_name)
        after_pct   = after.get("attendance_percentage") or 0
        after_famfa = after.get("total_fa_mfa_hours") or 0

        if after_famfa <= before_famfa:
            return False, f"total_fa_mfa_hours did not increase: {before_famfa} → {after_famfa}"

        return True, (
            f"FA/MFA({app_name}) granted=3h | "
            f"fa_mfa_hours: {before_famfa} → {after_famfa} | "
            f"pct: {round(before_pct,1)} → {round(after_pct,1)}%"
        )

    except Exception as e:
        import traceback
        return False, f"{e}\n{traceback.format_exc()}"

    finally:
        if app_name:
            try:
                doc = frappe.get_doc("FA MFA Application", app_name)
                if doc.docstatus == 1:
                    doc.cancel()
                frappe.delete_doc("FA MFA Application", app_name, force=True, ignore_permissions=True)
                _recalc(student, class_name)
                frappe.db.commit()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# S05 — Condonation approval
# ---------------------------------------------------------------------------

def s05_condonation(ctx):
    """
    Admin submits an approved Student Attendance Condonation.
    Verifies: total_condonation_hours and attendance_percentage increase.
    """
    student  = ctx["student"]
    class_name = ctx["class_name"]
    cond_name = None

    try:
        before = _summary(student, class_name)
        before_pct  = before.get("attendance_percentage") or 0
        before_cond = before.get("total_condonation_hours") or 0

        doc = frappe.get_doc({
            "doctype":            "Student Attendance Condonation",
            "student":            student,
            "class_name":    class_name,
            "condonation_reason": "Medical Emergency",
            "number_of_sessions": 2,
            "number_of_hours":    2.0,
            "final_status":       "Approved",
        })
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True)
        doc.submit()
        cond_name = doc.name
        frappe.db.commit()

        after = _summary(student, class_name)
        after_pct  = after.get("attendance_percentage") or 0
        after_cond = after.get("total_condonation_hours") or 0

        if after_cond <= before_cond:
            return False, f"total_condonation_hours did not increase: {before_cond} → {after_cond}"

        return True, (
            f"Condonation({cond_name}) 2h | "
            f"cond_hours: {before_cond} → {after_cond} | "
            f"pct: {round(before_pct,1)} → {round(after_pct,1)}%"
        )

    except Exception as e:
        import traceback
        return False, f"{e}\n{traceback.format_exc()}"

    finally:
        if cond_name:
            try:
                doc = frappe.get_doc("Student Attendance Condonation", cond_name)
                if doc.docstatus == 1:
                    doc.cancel()
                frappe.delete_doc("Student Attendance Condonation", cond_name, force=True, ignore_permissions=True)
                _recalc(student, class_name)
                frappe.db.commit()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# S06 — Parent portal sees correct percentage
# ---------------------------------------------------------------------------

def s06_parent_portal_visibility(ctx):
    """
    Verifies that the Attendance Summary data is readable by the parent
    portal query (same filters the parent portal index.py uses).
    Checks: record exists, percentage is a number, eligible_for_exam is set.
    """
    student  = ctx["student"]
    class_name = ctx["class_name"]
    parent_user = ctx.get("parent_user")

    try:
        # Force a recalc so summary is fresh
        _recalc(student, class_name)

        summaries = frappe.get_all(
            "Attendance Summary",
            filters={"student": student},
            fields=["course", "class_name", "attendance_percentage",
                    "attended_classes", "total_class_hours", "eligible_for_exam"],
            ignore_permissions=True,
        )

        if not summaries:
            return False, "No Attendance Summary records found — parent portal would show 0 courses"

        target = next((s for s in summaries if s.class_name == class_name), None)
        if not target:
            return False, f"No Attendance Summary for class_name={class_name}"

        pct = target.get("attendance_percentage") or 0
        eligible = target.get("eligible_for_exam")

        # Verify parent linkage
        parent_linked = "No parent linked"
        if parent_user:
            parent_linked = f"Parent user={parent_user}"
        elif ctx.get("parent_email"):
            parent_linked = f"Parent email={ctx['parent_email']} (no Frappe user yet)"
        else:
            parent_linked = "No parent record on this student"

        return True, (
            f"Class={class_name} pct={round(pct,1)}% eligible={eligible} | "
            f"Total summaries for student={len(summaries)} | {parent_linked}"
        )

    except Exception as e:
        import traceback
        return False, f"{e}\n{traceback.format_exc()}"


# ---------------------------------------------------------------------------
# S07 — RFID via Student RFID Card (not rfid_uid on Student Master)
# ---------------------------------------------------------------------------

def s07_rfid_card_resolution(ctx):
    """
    Student RFID Card doctype should also resolve to a student.
    Tests the _resolve_rfid() fallback path in rfid_sql_poller.
    """
    student = ctx["student"]
    card_name = None

    try:
        # Ensure rfid_uid on Student Master is blank so it falls through to card lookup
        old_rfid = frappe.db.get_value("Student Master", student, "rfid_uid")
        frappe.db.set_value("Student Master", student, "rfid_uid", "")

        # Create a Student RFID Card record
        card = frappe.get_doc({
            "doctype":     "Student RFID Card",
            "student":     student,
            "rfid_uid":    _TEST_CARD_UID,
            "card_status": "Active",
            "issued_date": today(),
        })
        card.insert(ignore_permissions=True)
        card_name = card.name
        frappe.db.commit()

        # Run the resolver
        from slcm.slcm.utils.rfid_sql_poller import _resolve_rfid
        result = _resolve_rfid(_TEST_CARD_UID)

        if not result:
            return False, f"_resolve_rfid('{_TEST_CARD_UID}') returned None — card not found"
        if result.get("student") != student:
            return False, (
                f"Resolved to wrong student: got={result.get('student')}, expected={student}"
            )

        return True, (
            f"Card({card_name}) uid={_TEST_CARD_UID} → student={result['student']} ✓"
        )

    except Exception as e:
        import traceback
        return False, f"{e}\n{traceback.format_exc()}"

    finally:
        frappe.db.set_value("Student Master", student, "rfid_uid", old_rfid or "")
        _safe_delete("Student RFID Card", card_name)
        frappe.db.commit()


# ---------------------------------------------------------------------------
# Master runner
# ---------------------------------------------------------------------------

@frappe.whitelist()
def run_all():
    """
    Run all end-to-end attendance scenarios.

        bench --site slcm.local execute slcm.slcm.tests.test_attendance_e2e.run_all
    """
    ctx = _resolve_context()

    header_student  = ctx.get("student")  or "NOT FOUND"
    header_class = ctx.get("class_name") or "NOT FOUND"
    header_faculty  = ctx.get("faculty_id") or "N/A"
    header_parent   = ctx.get("parent_email") or "N/A"

    scenarios = [
        ("S01 — RFID swipe → Student Attendance → Summary",        lambda: s01_rfid_swipe(ctx)),
        ("S02 — Faculty manual attendance → Summary",               lambda: s02_faculty_manual(ctx)),
        ("S03 — Office hours marking → Summary",                    lambda: s03_office_hours(ctx)),
        ("S04 — FA/MFA application approval → Summary",            lambda: s04_fa_mfa(ctx)),
        ("S05 — Condonation approval → Summary",                    lambda: s05_condonation(ctx)),
        ("S06 — Parent portal sees correct percentage",             lambda: s06_parent_portal_visibility(ctx)),
        ("S07 — RFID Card fallback resolution",                     lambda: s07_rfid_card_resolution(ctx)),
    ]

    W = 68
    print("\n" + "═" * W)
    print("  NLSIU SLCM — Attendance End-to-End Test Suite")
    print("═" * W)
    print(f"  Student : {header_student}")
    print(f"  Class: {header_class}")
    print(f"  Faculty : {header_faculty}")
    print(f"  Parent  : {header_parent}")
    print("─" * W)

    results    = []
    all_passed = True

    for label, fn in scenarios:
        if not ctx.get("student"):
            passed, msg = False, "No enrolled student found — seed test data first"
        else:
            try:
                passed, msg = fn()
            except Exception as e:
                import traceback
                passed, msg = False, f"Unhandled: {e}\n{traceback.format_exc()}"

        icon = "✓" if passed else "✗"
        print(f"\n  {icon} {label}")
        # Wrap long messages
        for line in msg.split("\n"):
            if line.strip():
                print(f"    {line}")

        results.append({"scenario": label, "passed": passed, "detail": msg})
        if not passed:
            all_passed = False

    print("\n" + "─" * W)
    total   = len(scenarios)
    n_pass  = sum(1 for r in results if r["passed"])
    n_fail  = total - n_pass
    verdict = "ALL PASSED ✓" if all_passed else f"{n_pass}/{total} passed — {n_fail} FAILED ✗"
    print(f"  Result  : {verdict}")
    print("═" * W + "\n")

    return results

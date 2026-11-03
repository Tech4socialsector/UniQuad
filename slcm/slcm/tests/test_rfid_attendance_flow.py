# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""
End-to-end test: RFID swipe → Attendance Log → Student Attendance → Attendance Summary

Run with:
    bench --site slcm.local run-tests --app slcm --module slcm.slcm.tests.test_rfid_attendance_flow

Or manually via console:
    bench --site slcm.local execute slcm.slcm.tests.test_rfid_attendance_flow.run_all
"""

import frappe
from frappe.utils import today, now_datetime, add_to_date, getdate
import unittest


# ---------------------------------------------------------------------------
# Test data constants — change these to match real records in your site
# ---------------------------------------------------------------------------
TEST_CLASS           = None   # auto-detected from first available
TEST_STUDENT         = None   # auto-detected from first enrolled student
TEST_RFID_UID        = "TEST-RFID-9999"
TEST_EMP_CODE        = "TEST-RFID-9999"


def _get_test_context():
    """Resolve a real Class and one of its enrolled Students for testing."""
    from slcm.slcm.doctype.classes.classes import get_class_students

    class_name = frappe.db.get_value("Classes", {}, "name", order_by="creation desc")
    if not class_name:
        return None, None

    # A student enrolled in this class
    students = get_class_students(class_name)
    return class_name, (students[0].student if students else None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup(student, class_name):
    """Remove test records created during the test."""
    # Attendance Log
    for name in frappe.db.get_all(
        "Attendance Log",
        filters={"rfid_uid": TEST_RFID_UID},
        pluck="name",
    ):
        frappe.delete_doc("Attendance Log", name, force=True, ignore_permissions=True)

    # Student Attendance
    if student and class_name:
        for name in frappe.db.get_all(
            "Student Attendance",
            filters={"student": student, "source": "RFID", "class_name": class_name},
            pluck="name",
        ):
            frappe.delete_doc("Student Attendance", name, force=True, ignore_permissions=True)

    # Attendance Session created by auto-create logic (tagged by class_schedule link)
    # Only remove ones without any real attendance beyond our test
    frappe.db.commit()


def _make_class_schedule(class_name, session_date, from_time, to_time):
    """Create a minimal Time Table entry for the test."""
    from frappe.utils import time_diff_in_hours
    duration = time_diff_in_hours(to_time, from_time)

    course = frappe.db.get_value("Classes", class_name, "course")

    doc = frappe.get_doc({
        "doctype":       "Time Table",
        "based_on":      "Class",
        "class_name":    class_name,
        "course":        course,
        "schedule_date": session_date,
        "from_time":     from_time,
        "to_time":       to_time,
        "duration_hours": duration,
        "status":        "Scheduled",
    })
    doc.insert(ignore_permissions=True)
    return doc


def _make_attendance_log(student, rfid_uid, swipe_time):
    """Insert a raw Attendance Log as if pulled from the RFID SQL Server."""
    doc = frappe.get_doc({
        "doctype":   "Attendance Log",
        "student":   student,
        "rfid_uid":  rfid_uid,
        "swipe_time": swipe_time,
        "source":    "RFID",
        "processed": 0,
    })
    doc.insert(ignore_permissions=True)
    return doc


# ---------------------------------------------------------------------------
# Individual test functions (also usable outside unittest)
# ---------------------------------------------------------------------------

def test_01_processor_runs_cleanly():
    """Processor should run without exceptions even with no pending logs."""
    from slcm.slcm.doctype.attendance_log.process_attendance_logs import process_pending_logs
    try:
        process_pending_logs()
        return True, "Processor ran cleanly with no pending logs"
    except Exception as e:
        return False, str(e)


def test_02_rfid_swipe_creates_attendance(class_name=None, student=None):
    """
    RFID swipe → Attendance Log → process_pending_logs()
    → Student Attendance created with source=RFID
    → Attendance Summary percentage updated

    Uses a past date (yesterday) with two swipes to satisfy both
    "In Only" and "In and Out" RFID modes.
    """
    from slcm.slcm.doctype.attendance_log.process_attendance_logs import process_pending_logs
    from frappe.utils import add_days

    if not class_name or not student:
        class_name, student = _get_test_context()

    if not class_name or not student:
        return False, "No Class or enrolled Student found in system — add test data first"

    # Use yesterday so the session is always "over" — avoids "In and Out" wait state
    session_date = add_days(today(), -1)
    from_time    = "09:00:00"
    to_time      = "10:00:00"
    swipe_in     = f"{session_date} 09:05:00"
    swipe_out    = f"{session_date} 09:55:00"  # second swipe — covers ≥50% duration

    cs   = None
    log1 = None
    log2 = None
    old_rfid = None

    try:
        # 1. Skip if attendance already recorded for this date (avoid duplicate error)
        existing_sa = frappe.db.exists("Student Attendance", {
            "student":        student,
            "class_name":   class_name,
            "attendance_date": session_date,
        })
        if existing_sa:
            # Use a different past date
            session_date = add_days(today(), -2)
            swipe_in  = f"{session_date} 09:05:00"
            swipe_out = f"{session_date} 09:55:00"

        # 2. Create Time Table entry for that date
        cs = _make_class_schedule(class_name, session_date, from_time, to_time)

        # 3. Set RFID UID on student temporarily
        old_rfid = frappe.db.get_value("Student Master", student, "rfid_uid")
        frappe.db.set_value("Student Master", student, "rfid_uid", TEST_RFID_UID)

        # 4. Insert two raw Attendance Logs (IN + OUT)
        log1 = _make_attendance_log(student, TEST_RFID_UID, swipe_in)
        log2 = _make_attendance_log(student, TEST_RFID_UID, swipe_out)
        frappe.db.commit()

        # 5. Run the processor
        process_pending_logs()
        frappe.db.commit()

        # 6. Verify both logs marked processed
        for log in [log1, log2]:
            processed = frappe.db.get_value("Attendance Log", log.name, "processed")
            if not processed:
                return False, f"Attendance Log {log.name} was NOT marked processed"

        # 7. Verify Student Attendance was created with source=RFID
        sa = frappe.db.get_value(
            "Student Attendance",
            {"student": student, "source": "RFID", "class_name": class_name,
             "attendance_date": session_date},
            ["name", "status", "hours_counted"],
            as_dict=True,
        )
        if not sa:
            return False, (
                f"No RFID Student Attendance found for student={student}, "
                f"class_name={class_name}, date={session_date}"
            )

        if sa.status != "Present":
            return False, (
                f"Status is '{sa.status}', expected 'Present'. "
                f"Check Attendance Settings → RFID Swipe Mode (currently 'In and Out' — "
                f"two swipes were sent covering 50 min of a 60 min session)."
            )

        if not sa.hours_counted:
            return False, f"hours_counted is 0 on Student Attendance {sa.name}"

        # 8. Verify Attendance Summary updated
        from slcm.slcm.utils.attendance_calculator import calculate_student_attendance
        calculate_student_attendance(student, class_name)
        frappe.db.commit()

        summary = frappe.db.get_value(
            "Attendance Summary",
            {"student": student, "class_name": class_name},
            ["attendance_percentage", "attended_classes"],
            as_dict=True,
        )
        if not summary:
            return False, "Attendance Summary not found after RFID attendance"

        return True, (
            f"PASS — SA: {sa.name} | status={sa.status} | hours={sa.hours_counted} | "
            f"Attendance%={round(summary.attendance_percentage or 0, 1)}"
        )

    except Exception as e:
        import traceback
        return False, f"Exception: {e}\n{traceback.format_exc()}"

    finally:
        if old_rfid is not None:
            try:
                frappe.db.set_value("Student Master", student, "rfid_uid", old_rfid or "")
            except Exception:
                pass
        for log in [log1, log2]:
            if log:
                try:
                    frappe.delete_doc("Attendance Log", log.name, force=True, ignore_permissions=True)
                except Exception:
                    pass
        # Remove RFID Student Attendance created by test
        if student and class_name:
            for name in frappe.db.get_all(
                "Student Attendance",
                filters={"student": student, "source": "RFID",
                         "class_name": class_name, "attendance_date": session_date},
                pluck="name",
            ):
                try:
                    frappe.delete_doc("Student Attendance", name, force=True, ignore_permissions=True)
                except Exception:
                    pass
        if cs:
            try:
                frappe.delete_doc("Time Table", cs.name, force=True, ignore_permissions=True)
            except Exception:
                pass
        frappe.db.commit()


def test_03_manual_attendance_recalculates(class_name=None, student=None):
    """
    Manually saved Student Attendance (source=Manual)
    should trigger Attendance Summary recalculation.
    Uses a past date to avoid duplicate-attendance validation errors.
    """
    from frappe.utils import add_days

    if not class_name or not student:
        class_name, student = _get_test_context()

    if not class_name or not student:
        return False, "No Class or enrolled Student found"

    # Pick the first past date (going back up to 10 days) with no existing record
    test_date = None
    for offset in range(3, 13):
        candidate = add_days(today(), -offset)
        if not frappe.db.exists("Student Attendance", {
            "student":        student,
            "class_name":   class_name,
            "attendance_date": candidate,
        }):
            test_date = candidate
            break

    if not test_date:
        return False, "Could not find a free past date for test — student has 10 days of attendance already"

    sa_name = None
    try:
        from slcm.slcm.utils.attendance_calculator import calculate_student_attendance

        # Insert the manual record first
        doc = frappe.get_doc({
            "doctype":        "Student Attendance",
            "student":        student,
            "class_name":   class_name,
            "attendance_date": test_date,
            "date":           test_date,
            "status":         "Present",
            "source":         "Manual",
            "session_type":   "Lecture",
            "hours_counted":  2.0,   # distinct value so we can detect its addition
        })
        doc.insert(ignore_permissions=True)
        sa_name = doc.name
        frappe.db.commit()

        # Force synchronous recalc with the record present → capture "with" value
        calculate_student_attendance(student, class_name)
        frappe.db.commit()
        hours_with = frappe.db.get_value(
            "Attendance Summary",
            {"student": student, "class_name": class_name},
            "attended_classes",
        ) or 0

        # Remove the record and recalc → capture "without" value
        frappe.delete_doc("Student Attendance", sa_name, force=True, ignore_permissions=True)
        sa_name = None
        frappe.db.commit()
        calculate_student_attendance(student, class_name)
        frappe.db.commit()
        hours_without = frappe.db.get_value(
            "Attendance Summary",
            {"student": student, "class_name": class_name},
            "attended_classes",
        ) or 0

        diff = round(hours_with - hours_without, 2)
        if diff < 2.0:
            return False, (
                f"Manual attendance not reflected in Summary. "
                f"hours_with={hours_with}, hours_without={hours_without}, diff={diff} (expected ≥2.0)"
            )

        return True, f"PASS — attended_classes: without={hours_without} → with={hours_with} (diff={diff})"

    except Exception as e:
        import traceback
        return False, f"Exception: {e}\n{traceback.format_exc()}"

    finally:
        if sa_name:
            try:
                frappe.delete_doc("Student Attendance", sa_name, force=True, ignore_permissions=True)
                from slcm.slcm.utils.attendance_calculator import calculate_student_attendance
                calculate_student_attendance(student, class_name)
                frappe.db.commit()
            except Exception:
                pass


def test_04_condonation_recalculates(class_name=None, student=None):
    """
    Submitting a condonation application should increase attendance_percentage.
    """
    if not class_name or not student:
        class_name, student = _get_test_context()

    if not class_name or not student:
        return False, "No Class or enrolled Student found"

    cond_name = None
    try:
        before_pct = frappe.db.get_value(
            "Attendance Summary",
            {"student": student, "class_name": class_name},
            "attendance_percentage",
        ) or 0

        doc = frappe.get_doc({
            "doctype":           "Student Attendance Condonation",
            "student":           student,
            "class_name":   class_name,
            "condonation_reason": "Medical Emergency",
            "number_of_sessions": 1,
            "number_of_hours":    1.0,
            "final_status":      "Approved",
        })
        doc.flags.ignore_validate = True  # skip shortage validation for test
        doc.insert(ignore_permissions=True)
        doc.submit()
        cond_name = doc.name
        frappe.db.commit()

        after_pct = frappe.db.get_value(
            "Attendance Summary",
            {"student": student, "class_name": class_name},
            "attendance_percentage",
        ) or 0

        if after_pct < before_pct:
            return False, f"Percentage decreased after condonation: {before_pct} → {after_pct}"

        return True, f"PASS — attendance_percentage: {round(before_pct,1)} → {round(after_pct,1)}"

    except Exception as e:
        import traceback
        return False, f"Exception: {e}\n{traceback.format_exc()}"

    finally:
        if cond_name:
            try:
                frappe.db.delete("Student Attendance Condonation", cond_name)
                from slcm.slcm.utils.attendance_calculator import calculate_student_attendance
                calculate_student_attendance(student, class_name)
                frappe.db.commit()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Run all tests — callable from bench console
# ---------------------------------------------------------------------------

@frappe.whitelist()
def run_all(class_name=None, student=None):
    """
    Run all RFID attendance flow tests.

    Usage:
        bench --site slcm.local execute slcm.slcm.tests.test_rfid_attendance_flow.run_all
        bench --site slcm.local execute slcm.slcm.tests.test_rfid_attendance_flow.run_all \
            --kwargs '{"class_name": "CLS-27-1-T1-A-00001", "student": "STU-0001"}'
    """
    if not class_name or not student:
        class_name, student = _get_test_context()

    results = []
    tests = [
        ("T01 — Processor runs cleanly",         lambda: test_01_processor_runs_cleanly()),
        ("T02 — RFID swipe creates attendance",  lambda: test_02_rfid_swipe_creates_attendance(class_name, student)),
        ("T03 — Manual attendance recalculates", lambda: test_03_manual_attendance_recalculates(class_name, student)),
        ("T04 — Condonation recalculates",       lambda: test_04_condonation_recalculates(class_name, student)),
    ]

    print("\n" + "="*65)
    print(f"  RFID Attendance Flow Tests")
    print(f"  Student:  {student or 'NOT FOUND'}")
    print(f"  Class: {class_name or 'NOT FOUND'}")
    print("="*65)

    all_passed = True
    for label, fn in tests:
        passed, msg = fn()
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"\n{status}  {label}")
        print(f"         {msg}")
        results.append({"test": label, "passed": passed, "message": msg})
        if not passed:
            all_passed = False

    print("\n" + "="*65)
    print(f"  Result: {'ALL PASSED ✓' if all_passed else 'SOME TESTS FAILED ✗'}")
    print("="*65 + "\n")

    return results


# ---------------------------------------------------------------------------
# unittest runner (bench run-tests)
# ---------------------------------------------------------------------------

class TestRFIDAttendanceFlow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.class_name, cls.student = _get_test_context()

    def test_01_processor_runs_cleanly(self):
        passed, msg = test_01_processor_runs_cleanly()
        self.assertTrue(passed, msg)

    def test_02_rfid_swipe_creates_attendance(self):
        if not self.class_name or not self.student:
            self.skipTest("No Class or enrolled Student in system")
        passed, msg = test_02_rfid_swipe_creates_attendance(self.class_name, self.student)
        self.assertTrue(passed, msg)

    def test_03_manual_attendance_recalculates(self):
        if not self.class_name or not self.student:
            self.skipTest("No Class or enrolled Student in system")
        passed, msg = test_03_manual_attendance_recalculates(self.class_name, self.student)
        self.assertTrue(passed, msg)

    def test_04_condonation_recalculates(self):
        if not self.class_name or not self.student:
            self.skipTest("No Class or enrolled Student in system")
        passed, msg = test_04_condonation_recalculates(self.class_name, self.student)
        self.assertTrue(passed, msg)

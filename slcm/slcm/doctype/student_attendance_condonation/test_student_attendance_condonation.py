import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

class TestStudentAttendanceCondonation(FrappeTestCase):
	def setUp(self):
		pass

	@patch('frappe.db.get_value')
	@patch('frappe.get_single')
	def test_validation_logic(self, mock_get_single, mock_get_value):
		# Mock Settings
		mock_settings = MagicMock()
		mock_settings.condonation_min_percentage = 70
		mock_get_single.return_value = mock_settings

		# Mock Summary
		mock_summary = MagicMock()
		mock_summary.attendance_percentage = 60 # LESS than 70
		mock_get_value.return_value = mock_summary

		# Create a dummy instance to test validate_shortage directly
		# We don't need to save it, just test the method
		from slcm.doctype.student_attendance_condonation.student_attendance_condonation import StudentAttendanceCondonation
		doc = StudentAttendanceCondonation({
			"student": "TEST_STUDENT",
			"class_name": "TEST_CLASS",
			"doctype": "Student Attendance Condonation"
		})
		
		# Allow it to be "new"
		doc.is_new = MagicMock(return_value=True)

		# 1. Expect Failure (60 < 70)
		with self.assertRaises(frappe.exceptions.ValidationError) as cm:
			doc.validate_shortage()
		
		self.assertIn("attendance is less than the required 70.0%", str(cm.exception))

		# 2. Expect Success (75 > 70)
		mock_summary.attendance_percentage = 75
		doc.validate_shortage() # Should not raise

		# 3. Test Default Fallback (if settings is 0 or None, default 66)
		mock_settings.condonation_min_percentage = 0
		# Summary 65 < 66
		mock_summary.attendance_percentage = 65
		with self.assertRaises(frappe.exceptions.ValidationError) as cm:
			doc.validate_shortage()
		self.assertIn("attendance is less than the required 66.0%", str(cm.exception))
		
		# Summary 67 > 66
		mock_summary.attendance_percentage = 67
		doc.validate_shortage() # Should not raise

import frappe
from frappe.utils import get_datetime, add_to_date
from slcm.slcm.doctype.rfid_device_room_mapping.rfid_device_room_mapping import (
	get_active_rooms_for_device,
)


def process_log_entry(log_doc):
	"""Process a raw attendance log entry and mark Student Attendance via RFID."""
	if log_doc.processed:
		return

	swipe_time = get_datetime(log_doc.swipe_time)

	# 1. Anti-Flood / Debounce — ignore if same RFID swiped within last 10 minutes
	window_start = add_to_date(swipe_time, minutes=-10)
	recent_logs = frappe.db.sql("""
		SELECT COUNT(*) FROM `tabAttendance Log`
		WHERE rfid_uid = %s
		AND name != %s
		AND swipe_time > %s
		AND swipe_time < %s
	""", (log_doc.rfid_uid, log_doc.name, window_start, swipe_time))[0][0]

	if recent_logs > 0:
		log_doc.processed = 1
		log_doc.db_update()
		return

	# 2. Identify Student
	student = frappe.db.get_value("Student Master", {"rfid_uid": log_doc.rfid_uid})
	if not student:
		frappe.log_error(
			message=f"Unknown RFID Tag: {log_doc.rfid_uid}",
			title="RFID Processor - Unknown Tag"
		)
		log_doc.processed = 1
		log_doc.db_update()
		return

	log_doc.student = student
	log_doc.db_update()

	# 3. Resolve device → room
	if not log_doc.device_id:
		# No device info — cannot match a session; mark processed to avoid infinite retry
		log_doc.processed = 1
		log_doc.db_update()
		return

	candidate_rooms = get_active_rooms_for_device(log_doc.device_id, on_date=swipe_time.date())
	if not candidate_rooms:
		frappe.log_error(
			message=f"RFID device '{log_doc.device_id}' has no active Room mapping configured.",
			title="RFID Processor - Device Not Configured"
		)
		log_doc.processed = 1
		log_doc.db_update()
		return

	# 4. Find a matching Attendance Session (any mapped room, same date, swipe within session window)
	log_date = swipe_time.date()
	log_time_str = swipe_time.strftime('%H:%M:%S')

	sessions = frappe.db.sql("""
		SELECT name, class_name, course, session_type, duration_hours
		FROM `tabAttendance Session`
		WHERE room IN %s
		AND session_date = %s
		AND session_start_time <= %s
		AND session_end_time >= %s
		AND session_status != 'Cancelled'
		LIMIT 1
	""", (candidate_rooms, log_date, log_time_str, log_time_str), as_dict=True)

	if not sessions:
		# No active session at this time — mark processed so it isn't retried forever
		frappe.log_error(
			message=(
				f"No active session found for student {student}, "
				f"device {log_doc.device_id}, rooms {candidate_rooms}, "
				f"date {log_date}, time {log_time_str}"
			),
			title="RFID Processor - No Session Found"
		)
		log_doc.processed = 1
		log_doc.db_update()
		return

	session = sessions[0]

	# 5. Mark Attendance on the existing Student Attendance record for this session
	attendance_name = frappe.db.exists("Student Attendance", {
		"student": student,
		"attendance_session": session.name
	})

	if attendance_name:
		doc = frappe.get_doc("Student Attendance", attendance_name)
		if doc.status != "Present":
			doc.status = "Present"
			doc.source = "RFID"
			doc.in_time = swipe_time
			doc.attendance_log = log_doc.name
			# Ensure class_name is set so recalculation triggers correctly
			if not doc.class_name and session.class_name:
				doc.class_name = session.class_name
			# Keep hours_counted aligned with the session duration
			if session.duration_hours:
				doc.hours_counted = session.duration_hours
			doc.flags.ignore_attendance_lock = True  # system reconciliation, not a faculty edit
			doc.save(ignore_permissions=True)
			log_doc.student_attendance = doc.name
	else:
		# Record doesn't exist — session wasn't initialised for this student.
		# Create it now so RFID presence is captured.
		if session.class_name:
			new_att = frappe.get_doc({
				"doctype": "Student Attendance",
				"student": student,
				"attendance_session": session.name,
				"class_name": session.class_name,
				"course": session.course,
				"attendance_date": log_date,
				"date": log_date,
				"session_type": session.session_type or "Lecture",
				"status": "Present",
				"source": "RFID",
				"in_time": swipe_time,
				"attendance_log": log_doc.name,
				"hours_counted": session.duration_hours or 1.0,
			})
			new_att.flags.ignore_attendance_lock = True
			new_att.insert(ignore_permissions=True)
			log_doc.student_attendance = new_att.name

	log_doc.processed = 1
	log_doc.db_update()

import frappe
from frappe.utils import today, add_days, now_datetime, getdate


def mark_overdue_demands():
	"""Daily: mark all past-due Fee Demands as Overdue."""
	demands = frappe.get_all(
		"Fee Demand",
		filters={
			"status": ["in", ["Pending", "Partially Paid"]],
			"due_date": ["<", today()],
		},
		fields=["name", "student", "status"],
	)

	for d in demands:
		frappe.db.set_value("Fee Demand", d.name, "status", "Overdue")

	if demands:
		frappe.db.commit()
		frappe.logger().info(f"[fee.scheduler] Marked {len(demands)} demands as Overdue")


def _get_reminder_settings():
	"""Return reminder config from Student Portal Settings with safe defaults."""
	try:
		s = frappe.db.get_singles_dict("Student Portal Settings")
	except Exception:
		s = {}

	def _bool(key, default=1):
		try:
			return bool(int(s.get(key, default)))
		except (TypeError, ValueError):
			return bool(default)

	def _int(key, default):
		try:
			return int(s.get(key, default))
		except (TypeError, ValueError):
			return default

	return {
		"enabled": _bool("enable_fee_reminders", 1),
		"sender_name": s.get("reminder_sender_name") or "Finance & Accounts Office",
		"reply_to": s.get("reminder_from_email") or None,
		"reminders": [
			{
				"offset": 7,
				"flag": "reminder_1_sent",
				"enabled": _bool("enable_7day_reminder", 1),
				"template": s.get("reminder_7day_template") or "Student Fee Reminder - 7 Days Before Due",
			},
			{
				"offset": 1,
				"flag": "reminder_2_sent",
				"enabled": _bool("enable_1day_reminder", 1),
				"template": s.get("reminder_1day_template") or "Student Fee Reminder - 1 Day Before Due",
			},
			{
				"offset": -_int("overdue_notice_offset", 3),
				"flag": "overdue_notice_sent",
				"enabled": _bool("enable_overdue_notice", 1),
				"template": s.get("overdue_notice_template") or "Student Fee Overdue Notice",
			},
		],
	}


def send_due_reminders():
	"""Daily: send reminder emails based on settings in Student Portal Settings."""
	cfg = _get_reminder_settings()
	if not cfg["enabled"]:
		frappe.logger().info("[fee.scheduler] Fee reminders are disabled — skipping")
		return

	for reminder in cfg["reminders"]:
		if not reminder["enabled"]:
			continue

		target_date = add_days(today(), reminder["offset"])
		flag = reminder["flag"]

		# Advance reminders (positive offset): exact date match — only send on the right day.
		# Overdue notice (negative offset): range match — catch all demands past due that
		# were never notified (e.g. demands created before the scheduler was enabled).
		if reminder["offset"] < 0:
			date_filter = ["<=", target_date]
		else:
			date_filter = target_date

		demands = frappe.get_all(
			"Fee Demand",
			filters={
				"due_date": date_filter,
				flag: 0,
				"status": ["not in", ["Paid", "Waived", "Cancelled"]],
			},
			fields=["name", "student", "fee_component", "outstanding_amount", "due_date"],
		)

		for d in demands:
			_send_fee_reminder(d, reminder, cfg["sender_name"], cfg["reply_to"])
			frappe.db.set_value("Fee Demand", d.name, flag, 1)

	frappe.db.commit()


def check_phd_year_transition():
	"""Daily: create correct annual demand for PhD students based on year of study."""
	from frappe.utils import date_diff

	phd_students = frappe.get_all(
		"Student Master",
		filters={"program_type": "PhD", "student_status": "Active"},
		fields=["name", "admission_date", "programme", "academic_year"],
	)

	current_year = frappe.get_value("Academic Year", {"is_current_year": 1}, "name")

	for student in phd_students:
		if not student.admission_date:
			continue

		years_elapsed = date_diff(today(), student.admission_date) // 365
		year_of_study = int(years_elapsed) + 1

		component_type = "Annual Fee (PhD)" if year_of_study <= 3 else "Continuation Fee (PhD)"

		existing = frappe.db.exists(
			"Fee Demand",
			{
				"student": student.name,
				"demand_type": "Academic",
				"academic_year": current_year,
				"fee_component": ["like", f"%PhD%"],
				"status": ["!=", "Cancelled"],
			},
		)

		if not existing:
			_create_phd_demand(student, component_type, year_of_study, current_year)

	frappe.db.commit()


def _create_phd_demand(student, component_type, year_of_study, academic_year):
	fee_component = frappe.get_value(
		"Fee Component", {"component_type": component_type}, "name"
	)
	if not fee_component:
		return

	fee_structure = frappe.get_value(
		"Fee Structure",
		{
			"demand_type": "Academic",
			"program_level": "PhD",
			"academic_year": academic_year,
			"status": "Active",
		},
		["name", "total_amount", "due_offset_days"],
		as_dict=True,
	)
	if not fee_structure:
		return

	due_date = add_days(today(), fee_structure.due_offset_days or 30)

	doc = frappe.get_doc({
		"doctype": "Fee Demand",
		"student": student.name,
		"academic_year": academic_year,
		"demand_type": "Academic",
		"fee_component": fee_component,
		"description": f"{component_type} — Year {year_of_study}",
		"demand_date": today(),
		"due_date": due_date,
		"original_amount": fee_structure.total_amount,
		"trigger_ref_doctype": "Fee Structure",
		"trigger_ref_name": fee_structure.name,
	})
	doc.insert(ignore_permissions=True)


def _send_fee_reminder(demand, config, sender_name=None, reply_to=None):
	result = frappe.db.get_value(
		"Student Master", demand.student,
		["official_email_id", "first_name", "last_name"], as_dict=True
	)
	if not result:
		frappe.logger().warning(f"[fee.scheduler] Student {demand.student} not found, skipping")
		return
	student_email = result.official_email_id or result.get("email")
	student_name = " ".join(filter(None, [result.first_name, result.last_name])) or demand.student

	if not student_email:
		frappe.logger().warning(
			f"[fee.scheduler] No email for student {demand.student}, skipping reminder"
		)
		return

	sender_name = sender_name or "Finance & Accounts Office"
	template_name = config.get("template") or "Fee Due Reminder - 7 Day"

	# Render via Email Template if it exists, else fall back to plain message
	template_doc = frappe.db.get_value(
		"Email Template", template_name, ["subject", "response", "use_html"], as_dict=True
	)

	ctx = {
		"student_name": student_name or demand.student,
		"student_id": demand.student,
		"fee_head": demand.fee_component,
		"outstanding_amount": f"{demand.outstanding_amount:,.2f}",
		"due_date": str(demand.due_date),
		"sender_name": sender_name,
	}

	if template_doc:
		subject = frappe.render_template(template_doc.subject or "", ctx)
		message = frappe.render_template(template_doc.response or "", ctx)
	else:
		# Graceful fallback if template was deleted
		subject = f"Fee Reminder — {demand.fee_component}"
		message = (
			f"<p>Dear {ctx['student_name']},</p>"
			f"<p>Your fee <strong>{demand.fee_component}</strong> of "
			f"&#8377;{ctx['outstanding_amount']} is due on {ctx['due_date']}.</p>"
			f"<p>Please log in to the student portal to pay.</p>"
			f"<p>Regards,<br><strong>{sender_name}</strong></p>"
		)

	mail_kwargs = dict(
		recipients=[student_email],
		subject=subject,
		message=message,
	)
	if reply_to:
		# reply_to holds reminder_from_email — use it as both the sender and reply-to
		mail_kwargs["sender"] = f"{sender_name} <{reply_to}>"
		mail_kwargs["reply_to"] = reply_to

	frappe.sendmail(**mail_kwargs)

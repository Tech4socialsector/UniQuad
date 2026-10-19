import frappe
from frappe.utils import add_days, today


@frappe.whitelist()
def get_pending_demands(program=None, academic_year=None, demand_type=None, reminder_type=None):
	"""
	Return Fee Demands eligible for a manual reminder.
	For manual sends, already-sent flags are ignored — admin can resend to anyone with outstanding dues.
	reminder_type: '7day' | '1day' | 'overdue'
	"""
	flag_map = {
		"7day":    "reminder_1_sent",
		"1day":    "reminder_2_sent",
		"overdue": "overdue_notice_sent",
	}
	flag = flag_map.get(reminder_type or "overdue")

	filters = {
		"status": ["not in", ["Paid", "Waived", "Cancelled"]],
	}
	if program:
		filters["program"] = program
	if academic_year:
		filters["academic_year"] = academic_year
	if demand_type:
		filters["demand_type"] = demand_type

	# Scope by due date based on reminder type
	if reminder_type == "overdue":
		filters["due_date"] = ["<", today()]
	elif reminder_type in ("7day", "1day"):
		filters["due_date"] = [">=", today()]

	demands = frappe.get_all(
		"Fee Demand",
		filters=filters,
		fields=[
			"name", "student", "student_name", "program",
			"academic_year", "demand_type", "fee_component",
			"outstanding_amount", "due_date", "status",
			"reminder_1_sent", "reminder_2_sent", "overdue_notice_sent",
		],
		order_by="due_date asc",
		limit=500,
	)

	# Attach student email and mark whether reminder was already sent
	for d in demands:
		d["student_email"] = frappe.db.get_value("Student Master", d.student, "official_email_id") or ""
		d["already_sent"] = bool(d.get(flag))

	return demands


@frappe.whitelist()
def send_manual_reminders(demand_names, reminder_type):
	"""
	Enqueue bulk fee reminder emails as a background job and return immediately.
	demand_names: JSON list of Fee Demand names
	reminder_type: '7day' | '1day' | 'overdue'
	"""
	import json

	if isinstance(demand_names, str):
		demand_names = json.loads(demand_names)

	if not demand_names:
		frappe.throw("No demands selected.")

	flag_map = {
		"7day":    "reminder_1_sent",
		"1day":    "reminder_2_sent",
		"overdue": "overdue_notice_sent",
	}
	if reminder_type not in flag_map:
		frappe.throw(f"Invalid reminder type: {reminder_type}")

	frappe.enqueue(
		"slcm.slcm.page.fee_reminder_tool.fee_reminder_tool._bulk_send_job",
		queue="long",
		timeout=1800,
		demand_names=demand_names,
		reminder_type=reminder_type,
	)

	return {
		"queued": len(demand_names),
		"message": f"{len(demand_names)} reminder(s) queued. Emails will be delivered shortly.",
	}


def _bulk_send_job(demand_names, reminder_type):
	"""Background job: send reminders and mark flags. Runs outside the HTTP request."""
	from slcm.slcm.fee.scheduler import _send_fee_reminder, _get_reminder_settings

	flag_map = {
		"7day":    "reminder_1_sent",
		"1day":    "reminder_2_sent",
		"overdue": "overdue_notice_sent",
	}
	flag = flag_map[reminder_type]

	cfg = _get_reminder_settings()
	reminder_cfg_map = {r["flag"]: r for r in cfg["reminders"]}
	reminder_cfg = reminder_cfg_map.get(flag)

	if not reminder_cfg:
		frappe.logger().error("[fee_reminder_tool] Reminder config missing for flag: " + flag)
		return

	sent = skipped = 0

	for name in demand_names:
		try:
			demand = frappe.get_doc("Fee Demand", name)
			_send_fee_reminder(demand, reminder_cfg, cfg["sender_name"], cfg["reply_to"])
			frappe.db.set_value("Fee Demand", name, flag, 1)
			sent += 1
		except Exception as e:
			frappe.logger().warning(f"[fee_reminder_tool] Failed for {name}: {e}")
			skipped += 1

	frappe.db.commit()
	frappe.logger().info(f"[fee_reminder_tool] Bulk send done — sent: {sent}, skipped: {skipped}")


@frappe.whitelist()
def get_filter_options():
	"""Return distinct programs and academic years that have unpaid Fee Demands."""
	programs = frappe.db.sql(
		"SELECT DISTINCT program FROM `tabFee Demand` WHERE program IS NOT NULL AND program != '' ORDER BY program",
		as_dict=True,
	)
	years = frappe.db.sql(
		"SELECT DISTINCT academic_year FROM `tabFee Demand` WHERE academic_year IS NOT NULL AND academic_year != '' ORDER BY academic_year DESC",
		as_dict=True,
	)
	demand_types = ["Academic", "Non Academic"]

	return {
		"programs": [r.program for r in programs],
		"academic_years": [r.academic_year for r in years],
		"demand_types": demand_types,
	}

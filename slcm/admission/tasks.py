import frappe
from frappe.utils import today, getdate


def auto_update_cycle_status():
	"""
	Scheduled daily job: Update Admission Cycle status based on dates.
	Upcoming: today < start_date
	Active: start_date <= today <= end_date
	Closed: today > end_date
	"""
	current_today = today()
	
	cycles = frappe.db.get_all(
		"Admission Cycle",
		filters={"docstatus": ["<", 2]},
		fields=["name", "cycle_start_date", "cycle_end_date", "status"]
	)

	updated_count = 0
	for c in cycles:
		new_status = c.status
		new_is_active = c.is_active
		
		# Skip if explicitly closed by admin earlier? 
		# For now, follow the date rules strictly
		
		if getdate(current_today) < getdate(c.cycle_start_date):
			new_status = "Draft" # 'Upcoming' is not a standard status in this doctype (Draft/Active/Closed)
		elif getdate(c.cycle_start_date) <= getdate(current_today) <= getdate(c.cycle_end_date):
			new_status = "Active"
		elif getdate(current_today) > getdate(c.cycle_end_date):
			new_status = "Closed"
			
		if new_status != c.status:
			frappe.db.set_value("Admission Cycle", c.name, {
				"status": new_status
			}, update_modified=False)
			updated_count += 1

	if updated_count:
		frappe.db.commit()
		frappe.log_error(
			title="Auto-Update Admission Cycle Status",
			message="Automatically updated status for {0} Admission Cycle(s)".format(updated_count)
		)

def setup_admission_workflows():
	setup_refund_request_workflow()
	setup_admission_cancellation_workflow()
	frappe.db.commit()

def setup_refund_request_workflow():
	if not frappe.db.exists("Workflow", "Refund Request Workflow"):
		workflow = frappe.new_doc("Workflow")
		workflow.workflow_name = "Refund Request Workflow"
		workflow.document_type = "Refund Request"
		workflow.workflow_state_field = "status"
		workflow.is_active = 1
		
		# States
		workflow.append("states", {"state": "Draft", "doc_status": 0, "allow_edit": "System Manager"})
		workflow.append("states", {"state": "Under Review", "doc_status": 0, "allow_edit": "Admission Manager"})
		workflow.append("states", {"state": "Approved", "doc_status": 0, "allow_edit": "Admission Manager"})
		workflow.append("states", {"state": "Rejected", "doc_status": 0, "allow_edit": "Admission Manager"})
		workflow.append("states", {"state": "Processed", "doc_status": 1, "allow_edit": "Admission Manager"})
		
		# Transitions
		workflow.append("transitions", {"state": "Draft", "action": "Submit for Review", "next_state": "Under Review", "allowed": "System Manager"})
		workflow.append("transitions", {"state": "Under Review", "action": "Approve", "next_state": "Approved", "allowed": "Admission Manager"})
		workflow.append("transitions", {"state": "Under Review", "action": "Reject", "next_state": "Rejected", "allowed": "Admission Manager"})
		workflow.append("transitions", {"state": "Approved", "action": "Process", "next_state": "Processed", "allowed": "Admission Manager"})
		
		workflow.insert()
		print("Refund Request Workflow created")
	else:
		print("Refund Request Workflow already exists")

def setup_admission_cancellation_workflow():
	if not frappe.db.exists("Workflow", "Admission Cancellation Workflow"):
		workflow = frappe.new_doc("Workflow")
		workflow.workflow_name = "Admission Cancellation Workflow"
		workflow.document_type = "Admission Cancellation"
		workflow.workflow_state_field = "status"
		workflow.is_active = 1
		
		# States
		workflow.append("states", {"state": "Initiated", "doc_status": 0, "allow_edit": "System Manager"})
		workflow.append("states", {"state": "Approved", "doc_status": 0, "allow_edit": "Admission Manager"})
		workflow.append("states", {"state": "Completed", "doc_status": 1, "allow_edit": "Admission Manager"})
		
		# Transitions
		workflow.append("transitions", {"state": "Initiated", "action": "Approve", "next_state": "Approved", "allowed": "Admission Manager"})
		workflow.append("transitions", {"state": "Approved", "action": "Complete", "next_state": "Completed", "allowed": "Admission Manager"})
		
		workflow.insert()
		print("Admission Cancellation Workflow created")
	else:
		print("Admission Cancellation Workflow already exists")

"""Daily admission-integrity check: money and records that don't add up, or that applicants changed.

Runs as a daily scheduler job (hooks.py). When any check finds rows it writes an Error Log entry
with the counts and record IDs (no personal data).
Run by hand: bench --site <site> execute slcm.security.discrepancy_check.run
"""

import json

import frappe

def _web_users():
	return set(frappe.get_all("User", {"user_type": "Website User"}, pluck="name"))


def run():
	web = _web_users()
	found = {}

	def add(key, meaning, names):
		names = list(names)
		if names:
			found[key] = {"meaning": meaning, "count": len(names), "ids": names[:20]}

	paid = frappe.get_all("Applicant", {"application_fee_status": "Paid"},
		["name", "application_fee_amount"])
	paid_requests = {r.reference_name: r for r in frappe.get_all("SLCM Payment Request",
		{"reference_doctype": "Applicant", "status": "Paid"}, ["reference_name", "payment_gateway"])}
	receipts = set(frappe.get_all("Applicant Payment Receipt", {"offer_letter": ["is", "not set"]}, pluck="applicant"))

	add("fee_paid_without_payment", "Applicant fee Paid with no Paid payment request",
		(p.name for p in paid if p.name not in paid_requests and p.application_fee_amount))
	add("fee_paid_without_receipt", "Applicant fee Paid with no receipt",
		(p.name for p in paid if p.name not in receipts and p.application_fee_amount))
	add("manual_payment_by_applicant", "Manual payment recorded in an applicant's session",
		frappe.get_all("SLCM Payment Request", {"payment_gateway": "Manual Payment",
			"modified_by": ["in", list(web) or [""]]}, pluck="name"))
	add("receipt_by_applicant", "Payment receipt created in an applicant's session",
		frappe.get_all("Applicant Payment Receipt", {"owner": ["in", list(web) or [""]]}, pluck="name"))
	add("waived_irregular", "Fee Waived with no recorded waiver, or waived by a website user",
		(r.name for r in frappe.get_all("Applicant", {"application_fee_status": "Waived"}, ["name", "fee_waived_by"])
		 if not r.fee_waived_by or r.fee_waived_by in web))
	add("submitted_without_fee", "Applicant past Draft with fee neither Paid nor Waived",
		frappe.get_all("Applicant", {"status": ["not in", ["Draft", "Rejected", "Withdrawn", ""]],
			"application_fee_status": ["not in", ["Paid", "Waived"]], "application_fee_amount": [">", 0]}, pluck="name"))
	add("applicant_changed_by_other_applicant", "Applicant last modified by a different website user",
		(r.name for r in frappe.get_all("Applicant", fields=["name", "owner", "email", "modified_by"])
		 if r.modified_by in web and r.modified_by not in (r.owner, r.email)))
	add("offer_fee_paid_without_receipt", "Offer in a Fee Paid status with no receipt",
		(o for o in frappe.get_all("Offer Letter", {"status": ["in", ["Confirmation Fee Paid", "Full Fee Paid"]]}, pluck="name")
		 if not frappe.db.exists("Applicant Payment Receipt", {"offer_letter": o})))
	add("scholarship_approved_by_applicant", "Scholarship Approved/reviewed by a website user",
		frappe.get_all("Scholarship Application", {"status": "Approved", "reviewed_by": ["in", list(web) or [""]]}, pluck="name"))
	add("student_created_by_applicant", "Student Master created in a website user's session",
		frappe.get_all("Student Master", {"owner": ["in", list(web) or [""]]}, pluck="name"))
	return found


def daily():
	found = run()
	if not found:
		return
	body = json.dumps(found, indent=1, default=str)
	frappe.log_error(title="Admission discrepancy check: issues found", message=body)

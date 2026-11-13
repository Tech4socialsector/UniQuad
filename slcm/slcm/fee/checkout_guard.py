# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""One online payment at a time per charge.

A student and a parent (or two parents) can open the same fees at the same moment. Without a
guard both checkouts go through and the charge is paid twice: the second payment is only
recorded as unapplied money that the Finance Office has to refund.

``ensure_no_other_checkout`` runs when a portal starts a checkout, before any status is marked
"Payment Initiated" or an order is created. It refuses when someone else started a checkout for
any of the same charges in the last ACTIVE_MINUTES that has not finished (paid, failed or
cancelled). The payer's own earlier checkout never blocks them, so a retry always works.

Checkouts of both gateways are Integration Requests: Easebuzz keeps its intent at the top of
``data``, Razorpay under ``data["slcm_intent"]`` (slcm.api.razorpay_reconcile.attach_intent).
The check and the new checkout are serialised on the Student Master row, so two payers who press
Pay together cannot both pass it.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_to_date, format_datetime, get_datetime, now_datetime

# Easebuzz checkout links expire after about 15 minutes; Razorpay leaves an abandoned order Queued
ACTIVE_MINUTES = 20
ACTIVE_STATUSES = ("Queued", "Authorized")
SERVICES = ("Easebuzz", "Razorpay")


def _intent(row):
	try:
		data = json.loads(row.data or "{}")
	except ValueError:
		return {}
	return data.get("slcm_intent") or data if isinstance(data, dict) else {}


def _charges(intent):
	"""(doctype, name) pairs an intent pays for."""
	out = {("Fee Demand", n) for n in intent.get("demand_names") or []}
	out |= {("Re Exam Registration", n) for n in intent.get("re_exam_registrations") or []}
	invoice = intent.get("invoice") or intent.get("invoice_name")
	if invoice:
		out.add(("Fee Invoice", invoice))
	if intent.get("registration"):
		# Razorpay intents say "improvement", Easebuzz ones "improvement_exam"
		doctype = (
			"Improvement Exam Registration" if intent.get("flow") in ("improvement", "improvement_exam")
			else "Re Exam Registration"
		)
		out.add((doctype, intent["registration"]))
	return out


def active_checkout(student, charges, exclude_user=None):
	"""The newest unfinished checkout for any of ``charges`` (set of (doctype, name)) started by
	someone other than ``exclude_user`` in the last ACTIVE_MINUTES, as an intent dict, or None."""
	if not student or not charges:
		return None
	rows = frappe.get_all(
		"Integration Request",
		filters={
			"integration_request_service": ("in", SERVICES),
			"status": ("in", ACTIVE_STATUSES),
			"creation": (">", add_to_date(now_datetime(), minutes=-ACTIVE_MINUTES)),
			"data": ("like", f"%{student}%"),
		},
		fields=["name", "data", "creation"],
		order_by="creation desc",
		ignore_permissions=True,
	)
	for row in rows:
		intent = _intent(row)
		if intent.get("student") != student or (exclude_user and intent.get("user") == exclude_user):
			continue
		if _charges(intent) & charges:
			return {**intent, "started_at": row.creation, "integration_request": row.name}
	return None


CLAIM_SECONDS = 90  # covers creating the order with the gateway; the Integration Request takes over


def _claim_key(student):
	return f"slcm_checkout_claim:{student}"


def _claimed(student, charges, user):
	"""Another payer's claim (see _claim) on any of ``charges`` that has not expired, or None."""
	claims = frappe.cache().get_value(_claim_key(student)) or {}
	cutoff = add_to_date(now_datetime(), seconds=-CLAIM_SECONDS)
	for other_user, claim in claims.items():
		if other_user != user and get_datetime(claim["at"]) > cutoff and set(map(tuple, claim["charges"])) & charges:
			return {"paid_by_role": claim.get("role"), "started_at": claim["at"]}
	return None


def _claim(student, charges, user, role):
	cutoff = add_to_date(now_datetime(), seconds=-CLAIM_SECONDS)
	claims = {
		u: c for u, c in (frappe.cache().get_value(_claim_key(student)) or {}).items()
		if get_datetime(c["at"]) > cutoff
	}
	claims[user] = {"charges": sorted(charges), "role": role, "at": str(now_datetime())}
	frappe.cache().set_value(_claim_key(student), claims, expires_in_sec=CLAIM_SECONDS)


def ensure_no_other_checkout(student, demand_names=(), re_exam_registrations=(), invoice=None,
                             registration=None, registration_doctype="Re Exam Registration", paid_by_role="Student"):
	"""Refuse to start a checkout while another payer's checkout for the same charges is open."""
	charges = {("Fee Demand", n) for n in demand_names or ()}
	charges |= {("Re Exam Registration", n) for n in re_exam_registrations or ()}
	if invoice:
		charges.add(("Fee Invoice", invoice))
	if registration:
		charges.add((registration_doctype, registration))
	if not charges:
		return
	user = frappe.session.user
	# Serialise concurrent "Pay" clicks for this student. Endpoints commit their "Payment Initiated"
	# marks (releasing this lock) before the checkout's Integration Request exists, so a short claim is
	# written while the lock is held: the second click, released by that commit, sees the claim.
	frappe.db.sql("SELECT name FROM `tabStudent Master` WHERE name = %s FOR UPDATE", student)
	other = active_checkout(student, charges, exclude_user=user) or _claimed(student, charges, user)
	if not other:
		_claim(student, charges, user, paid_by_role)
		return
	who = _("the parent") if other.get("paid_by_role") == "Parent" else _("the student")
	retry_at = add_to_date(get_datetime(other["started_at"]), minutes=ACTIVE_MINUTES)
	frappe.throw(
		_(
			"A payment for these fees was started by {0} at {1} and is still in progress. To avoid paying "
			"twice, please wait for it to finish, or try again after {2}."
		).format(who, format_datetime(other["started_at"], "hh:mm a"), format_datetime(retry_at, "hh:mm a")),
		title=_("Payment already in progress"),
	)

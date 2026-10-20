# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class BulkFeeStructureUpdate(Document):
    def validate(self):
        # Skip validation when called internally during apply (flag set by apply_bulk_fee_update)
        if self.flags.get("applying"):
            return
        self._validate_inputs()

    def _validate_inputs(self):
        if self.target_scope == "Programme" and not self.programme:
            frappe.throw(_("Programme (Cohort) is required when Update Scope is 'Programme'."))
        if self.target_scope == "Programme" and not self.program:
            frappe.throw(_("Program is required when Update Scope is 'Programme'."))
        if self.status == "Applied":
            frappe.throw(_("This Bulk Fee Structure Update has already been applied and cannot be modified."))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_program_from_cohort(cohort):
    program = frappe.db.get_value("SLCM Batch", cohort, "program")
    if not program and frappe.db.exists("Programme", cohort):
        program = cohort
    return program


def _get_students_for_scope(target_scope, programme, program, batch_year=None, academic_year=None):
    """Return list of active Student Master dicts matching the scope + optional filters."""
    filters = {"student_status": "Active"}

    # Student Master's cohort field is "batch" (formerly "programme").
    if target_scope == "Programme":
        filters["batch"] = programme
    else:
        # Resolve all cohorts that map to this program
        cohorts = frappe.get_all("SLCM Batch", filters={"program": program}, pluck="name")
        if not cohorts:
            return []
        filters["batch"] = ["in", cohorts]

    if batch_year:
        # Student Master has no batch year of its own; it comes from the student's fee structure.
        fee_structures = frappe.get_all("Fee Structure", filters={"batch_year": batch_year}, pluck="name")
        if not fee_structures:
            return []
        filters["fee_structure"] = ["in", fee_structures]
    if academic_year:
        filters["academic_year"] = academic_year

    return frappe.get_all(
        "Student Master",
        filters=filters,
        fields=[
            "name", "first_name", "last_name", "batch as programme",
            "fee_structure", "total_program_fee", "total_paid_amount",
            "discount_amount", "net_program_fee",
            "applying_scholarship", "scholarship_percentage", "scholarship_amount",
        ],
        ignore_permissions=True,
    )


def _calculate_discount(total_fee, applying_scholarship, scholarship_percentage, scholarship_amount):
    scholarship_pct = flt(scholarship_percentage or 0)
    scholarship_amt = flt(scholarship_amount or 0)
    if applying_scholarship == "Yes" and scholarship_pct:
        return round((total_fee * scholarship_pct) / 100, 2)
    elif applying_scholarship == "Yes" and scholarship_amt:
        return min(scholarship_amt, total_fee)
    return 0.0


def _count_updatable_invoices(student_name):
    return frappe.db.count(
        "Fee Invoice",
        {"student": student_name, "status": ["in", ["Unpaid", "Partially Paid", "Overdue"]]},
    )


def _update_invoices_for_student(student_name, fs_doc):
    """Replace fee_components in outstanding invoices with components from the new fee structure.

    - Unpaid / Overdue: replace all components, recalculate
    - Partially Paid: replace components, recalculate but preserve paid_amount
    - Paid / Cancelled: untouched
    """
    outstanding_invoices = frappe.get_all(
        "Fee Invoice",
        filters={"student": student_name, "status": ["in", ["Unpaid", "Partially Paid", "Overdue"]]},
        fields=["name", "scholarship_amount", "paid_amount"],
        ignore_permissions=True,
    )

    for inv_row in outstanding_invoices:
        try:
            inv = frappe.get_doc("Fee Invoice", inv_row.name, ignore_permissions=True)

            # Replace fee_components from new fee structure
            inv.set("fee_components", [])
            for comp in (fs_doc.components or []):
                inv.append("fee_components", {
                    "fee_component":  comp.fee_component,
                    "component_name": comp.component_name,
                    "amount":         flt(comp.amount or 0),
                    "is_taxable":     comp.is_taxable,
                    "tax_rate":       flt(comp.tax_rate or 0),
                    "tax_amount":     flt(comp.tax_amount or 0),
                    "total_amount":   flt(comp.total_amount or comp.amount or 0),
                })

            inv.calculate_amounts()
            inv.update_status()
            inv.db_update()
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Bulk Fee: invoice update failed — {inv_row.name}")


# ── Whitelisted API ───────────────────────────────────────────────────────────

@frappe.whitelist()
def preview_bulk_fee_update(doc_name):
    """Populate the affected_students child table with a read-only impact preview.

    Returns a summary dict used by the JS alert.
    """
    doc = frappe.get_doc("Bulk Fee Structure Update", doc_name)

    if doc.status == "Applied":
        frappe.throw(_("This update has already been applied."))
    if not doc.new_fee_structure:
        frappe.throw(_("Please select a New Fee Structure before previewing."))

    fs = frappe.get_doc("Fee Structure", doc.new_fee_structure)
    new_total = flt(fs.total_amount_for_indian or 0)
    if not new_total:
        frappe.throw(_("The selected Fee Structure has no components or a zero total amount."))

    students = _get_students_for_scope(
        doc.target_scope, doc.programme, doc.program,
        doc.get("batch_year"), doc.get("academic_year"),
    )
    if not students:
        frappe.throw(_("No active students found for the selected scope and filters."))

    rows = []
    for s in students:
        discount = _calculate_discount(
            new_total,
            s.applying_scholarship,
            s.scholarship_percentage,
            s.scholarship_amount,
        )
        net = new_total - discount
        paid = flt(s.total_paid_amount or 0)
        outstanding = max(net - paid, 0)
        full_name = " ".join(filter(None, [s.first_name, s.last_name])) or s.name

        rows.append({
            "student":               s.name,
            "student_name":          full_name,
            "programme":             s.programme or "",
            "current_fee_structure": s.fee_structure or "(none)",
            "current_total_fee":     flt(s.total_program_fee or 0),
            "new_total_fee":         new_total,
            "already_paid":          paid,
            "scholarship":           discount,
            "new_outstanding":       outstanding,
            "invoices_to_update":    _count_updatable_invoices(s.name) if doc.update_existing_invoices else 0,
            "apply_status":          "Pending",
        })

    doc.set("affected_students", rows)
    doc.total_students_affected = len(rows)
    doc.status = "Previewed"

    # Aggregate stats for the summary stat fields
    total_old_fee = sum(r["current_total_fee"] for r in rows)
    total_new_fee = new_total * len(rows)
    doc.total_fee_increase    = max(total_new_fee - total_old_fee, 0)
    doc.total_new_outstanding = sum(r["new_outstanding"] for r in rows)

    old_avg = (total_old_fee / len(rows)) if rows else 0
    validity = ""
    if fs.valid_from:
        validity = f" &nbsp;·&nbsp; Valid: {frappe.utils.formatdate(str(fs.valid_from), 'dd MMM yyyy')}"
        if fs.valid_until:
            validity += f" – {frappe.utils.formatdate(str(fs.valid_until), 'dd MMM yyyy')}"

    inv_warning = (
        '<br><span style="color:#d97706;font-weight:600;">&#9888; Outstanding invoices will also be updated</span>'
        if doc.update_existing_invoices else ""
    )

    doc.fee_change_note = f"""
    <div style="padding:12px 16px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;font-size:13px;color:#1e3a5f;">
      <strong>Impact Preview</strong>{validity}<br>
      Fee Structure: <strong>{fs.fee_structure_name or doc.new_fee_structure}</strong>
      &nbsp;·&nbsp; New Total: <strong>&#8377;{new_total:,.0f}</strong>
      &nbsp;·&nbsp; Students affected: <strong>{len(rows)}</strong>
      &nbsp;·&nbsp; Avg. old fee: <strong>&#8377;{old_avg:,.0f}</strong>
      {inv_warning}
    </div>
    """

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "student_count": len(rows),
        "new_total":     new_total,
        "fs_name":       fs.fee_structure_name or doc.new_fee_structure,
        "valid_from":    str(fs.valid_from or ""),
        "valid_until":   str(fs.valid_until or ""),
    }


@frappe.whitelist()
def apply_bulk_fee_update(doc_name):
    """Apply the fee structure change to all students in the preview.

    Uses direct DB updates at the end to avoid re-triggering validate.
    """
    doc = frappe.get_doc("Bulk Fee Structure Update", doc_name)

    if doc.status == "Applied":
        frappe.throw(_("This update has already been applied."))
    if doc.status != "Previewed":
        frappe.throw(_("Please run Preview first before applying the update."))
    if not doc.affected_students:
        frappe.throw(_("No students in the preview. Please run Preview first."))

    user_roles = frappe.get_roles()
    allowed = ["System Manager", "slcm_FINO Officer", "Administrator"]
    if not any(r in user_roles for r in allowed) and frappe.session.user != "Administrator":
        frappe.throw(_("You do not have permission to apply bulk fee structure updates."))

    fs = frappe.get_doc("Fee Structure", doc.new_fee_structure)
    new_total = flt(fs.total_amount_for_indian or 0)
    fs_label = fs.fee_structure_name or doc.new_fee_structure

    success = 0
    errors = 0

    for row in doc.affected_students:
        try:
            sm = frappe.get_doc("Student Master", row.student, ignore_permissions=True)

            discount = _calculate_discount(
                new_total,
                sm.applying_scholarship,
                sm.scholarship_percentage,
                sm.scholarship_amount,
            )
            net = new_total - discount
            outstanding = max(net - flt(sm.total_paid_amount or 0), 0)

            sm.fee_structure       = doc.new_fee_structure
            sm.total_program_fee   = new_total
            sm.discount_amount     = discount
            sm.net_program_fee     = net
            sm.outstanding_balance = outstanding

            if fs.instalment_enabled and fs.max_instalments:
                sm.number_of_instalments = fs.max_instalments

            sm.append("fee_structure_history", {
                "fee_structure":       doc.new_fee_structure,
                "fee_structure_label": fs_label,
                "total_program_fee":   new_total,
                "valid_from":          fs.valid_from,
                "valid_until":         fs.valid_until,
                "applied_on":          now_datetime(),
                "applied_by":          frappe.session.user,
                "reason":              doc.reason or "Bulk fee structure update",
            })

            sm.flags.ignore_validate = True
            sm.save(ignore_permissions=True)

            if doc.update_existing_invoices:
                _update_invoices_for_student(row.student, fs)

            new_outstanding = outstanding
            # Persist child row status directly — bypass parent validate
            frappe.db.set_value(
                "Bulk Fee Update Student", row.name,
                {"apply_status": "Applied", "new_outstanding": new_outstanding},
            )

            from slcm.slcm.doctype.student_master.student_master import _append_payment_log
            _append_payment_log(
                row.student,
                "Bulk Fee Update",
                amount=new_total,
                from_status=frappe.db.get_value("Student Master", row.student, "fee_payment_status") or "",
                to_status="",
                remarks=(
                    f"Bulk update {doc.name}: fee structure changed to {fs_label}. "
                    f"Reason: {doc.reason or 'Bulk fee structure update'}"
                ),
            )

            success += 1

        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Bulk Fee: student update failed — {row.student}")
            frappe.db.set_value("Bulk Fee Update Student", row.name, "apply_status", "Error")
            errors += 1

    final_status = "Applied" if success > 0 else "Failed"
    result_notes = (
        f"{success} student(s) updated successfully."
        + (f" {errors} error(s) — check Error Log for details." if errors else "")
        + (" Outstanding invoices also updated." if doc.update_existing_invoices and success else "")
    )

    # Direct DB update — bypasses validate to avoid the "already applied" guard
    frappe.db.set_value("Bulk Fee Structure Update", doc_name, {
        "status":               final_status,
        "applied_on":           now_datetime(),
        "applied_by":           frappe.session.user,
        "success_count":        success,
        "error_count":          errors,
        "result_notes":         result_notes,
    })
    frappe.db.commit()

    return {
        "success": success,
        "errors":  errors,
        "message": result_notes,
    }

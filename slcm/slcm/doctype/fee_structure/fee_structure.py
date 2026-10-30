# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from slcm.api.service.offer_service import OfferService


def _to_date(value):
    """Coerce a date value (str, datetime.date, or None) to datetime.date or None."""
    if not value:
        return None
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return None
    return None


class FeeStructure(Document):
    def validate(self):
        self.validate_dates()
        self.calculate_total()
        self.validate_duplicate_active_fee_structure()
        self.validate_status_transition()

    def validate_duplicate_active_fee_structure(self):
        """Block saving when another Active fee structure covers an overlapping date range
        for the same programme / academic year / year no / applicable / round / gateway combination.

        Two date ranges [A, B] and [C, D] overlap when A <= D and C <= B.
        An open-ended range (no valid_until) is treated as extending to infinity.
        """
        if self.status != "Active":
            return

        filters = {
            "program":         self.program,
            "academic_year":   self.academic_year,
            "year_no":         self.year_no,
            "applicable":      self.applicable,
            "offer_round":     self.offer_round,
            "payment_gateway": self.payment_gateway,
            "status":          "Active",
            "name":            ["!=", self.name],
        }

        existing_list = frappe.get_all(
            "Fee Structure",
            filters=filters,
            fields=["name", "valid_from", "valid_until"],
        )

        my_from  = _to_date(self.valid_from)
        my_until = _to_date(self.valid_until)  # None → open-ended

        for existing in existing_list:
            their_from  = _to_date(existing.valid_from)
            their_until = _to_date(existing.valid_until)  # None → open-ended

            # Overlap: my range starts before their range ends AND their range starts before my range ends
            starts_before_their_end = (not their_until) or (my_from <= their_until)
            their_start_before_my_end = (not my_until) or (their_from <= my_until)

            if starts_before_their_end and their_start_before_my_end:
                frappe.throw(_(
                    "Another active Fee Structure ({0}) with an overlapping validity date range "
                    "already exists for the same Programme, Academic Year, Year No, "
                    "Applicable, and Payment Gateway. Please set non-overlapping Valid From / "
                    "Valid Until dates, or deactivate {0} first."
                ).format(existing.name))

    def validate_status_transition(self):
        """Prevents setting status to 'Inactive' if linked to an active Offer Configuration."""
        if self.status == "Inactive" and not self.is_new():
            old_status = frappe.db.get_value("Fee Structure", self.name, "status")
            if old_status != "Inactive":
                linked_oc = frappe.db.get_all(
                    "Fee Structure Child",
                    filters={
                        "fee_structure": self.name,
                        "parenttype":    "Offer Configuration",
                    },
                    fields=["parent"],
                    limit=1,
                )
                if linked_oc:
                    frappe.throw(_(
                        "Cannot set status to 'Inactive'. This Fee Structure is currently used "
                        "by Offer Configuration {0}. Please remove it from the configuration first."
                    ).format(linked_oc[0].parent))

    def validate_dates(self):
        if self.valid_from and self.valid_until:
            if self.valid_from > self.valid_until:
                frappe.throw(_("Valid From date cannot be after Valid Until date"))

    def calculate_total(self):
        total_indian = 0
        for component in self.get("fee_components_for_indian", []):
            amount   = component.amount or 0
            tax_rate = component.tax_rate or 0

            component.tax_amount   = (amount * tax_rate) / 100
            component.total_amount = amount + component.tax_amount

            total_indian += component.total_amount

        total_foreign = 0
        for component in self.get("fee_components_for_foreign", []):
            amount   = component.amount or 0
            tax_rate = component.tax_rate or 0

            component.tax_amount   = (amount * tax_rate) / 100
            component.total_amount = amount + component.tax_amount

            total_foreign += component.total_amount

        self.total_amount_for_indian = total_indian
        self.total_amount_for_foreign = total_foreign

    def on_update(self):


        # Trigger background student fee sync when Student fee structure becomes active
        # or its validity dates / total amount change
        if self.applicable == "Student" and self.status == "Active":
            if (
                self.has_value_changed("status")
                or self.has_value_changed("valid_from")
                or self.has_value_changed("valid_until")
                or self.has_value_changed("total_amount_for_indian")
            ):
                frappe.enqueue(
                    "slcm.slcm.doctype.student_master.student_master.sync_fee_structures_for_program",
                    program=self.program,
                    queue="default",
                    timeout=600,
                    job_id=f"fee_sync_{self.program}_{frappe.utils.today()}",
                )
                frappe.msgprint(
                    _("Student fee data will be updated in the background to reflect this change."),
                    indicator="blue",
                    alert=True,
                )

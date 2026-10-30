import frappe
from frappe.model.document import Document
from frappe.utils import now, getdate

class AdmissionReportConfig(Document):

    def validate(self):
        if self.from_date and self.to_date:
            if getdate(self.from_date) > getdate(self.to_date):
                frappe.throw(
                    "From Date must be before To Date.",
                    title="Invalid Date Range"
                )

    def before_save(self):
        self.generated_by = frappe.session.user
        self.generated_on = now()

    @frappe.whitelist()
    def generate_report(self):
        self.db_set("status", "Generating")
        try:
            data = self.get_report_data()
            self.db_set("status", "Completed")
            return data
        except Exception as e:
            self.db_set("status", "Failed")
            frappe.log_error(str(e), "Report Generation Error")
            frappe.throw(f"Report generation failed: {str(e)}")

    def get_report_data(self):
        if self.report_type == "Category-wise Seat Allocation":
            return self.category_wise_seat_report()
        elif self.report_type == "Applicant Status Report":
            return self.applicant_status_report()
        elif self.report_type == "Document Verification Status":
            return self.document_verification_report()
        elif self.report_type == "Stage-wise Progress":
            return self.stage_wise_progress_report()
        elif self.report_type == "RTI Response Export":
            return self.rti_export_report()
        return []

    def category_wise_seat_report(self):
        return frappe.db.sql("""
            SELECT
                csm.campus,
                csm.program,
                rc.category,
                rc.total_seats,
                rc.filled_seats,
                (rc.total_seats - rc.filled_seats) AS available_seats,
                rc.cut_off_rank,
                rc.cut_off_score
            FROM `tabCampus Seat Matrix` csm
            JOIN `tabReservation Category` rc ON rc.parent = csm.name
            WHERE csm.admission_cycle = %s
            ORDER BY csm.campus, csm.program, rc.category
        """, (self.admission_cycle,), as_dict=True)

    def applicant_status_report(self):
        filters = {"admission_cycle": self.admission_cycle}
        if self.campus:
            filters["campus"] = self.campus
        if self.program:
            filters["program"] = self.program
        return frappe.get_all(
            "Applicant",
            filters=filters,
            fields=[
                "applicant_id", "candidate_name", "email",
                "application_type", "program", "campus",
                "status", "reservation_category"
            ]
        )

    def document_verification_report(self):
        return frappe.db.sql("""
            SELECT
                a.candidate_name,
                a.applicant_id,
                ad.document_type,
                ad.is_verified,
                ad.verified_by,
                ad.verified_on,
                ad.is_locked
            FROM `tabApplicant Document` ad
            JOIN `tabApplicant` a ON a.name = ad.applicant
            WHERE a.admission_cycle = %s
            ORDER BY a.candidate_name, ad.document_type
        """, (self.admission_cycle,), as_dict=True)

    def stage_wise_progress_report(self):
        return frappe.db.sql("""
            SELECT
                status AS stage,
                COUNT(*) AS applicant_count,
                program,
                campus
            FROM `tabApplicant`
            WHERE admission_cycle = %s
            GROUP BY status, program, campus
            ORDER BY program, campus
        """, (self.admission_cycle,), as_dict=True)

    def rti_export_report(self):
        return frappe.get_all(
            "Admission Audit Log",
            fields=[
                "reference_doctype", "reference_name", "action",
                "field_changed", "old_value", "new_value",
                "user", "timestamp", "ip_address", "legal_relevance"
            ],
            order_by="timestamp asc"
        )
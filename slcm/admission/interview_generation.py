import math
import re

import frappe
from frappe import _


class InterviewGeneration:
    """Eligibility and quota selection for an Interview List."""

    def __init__(self, document):
        self.document = document

    def validate_ratios(self):
        pattern = re.compile(r"^([1-9]\d*:[1-9]\d*|[1-9]\d*)$")
        for fieldname, label in (
            ("enter_domestic_ratio", _("Domestic")),
            ("enter_international_ratio", _("International")),
        ):
            value = self.document.get(fieldname)
            if value and not pattern.match(str(value)):
                frappe.throw(_("{0} Ratio must be a positive integer or use X:Y format.").format(label))

    def get_total_seats(self, applicant_type):
        fieldname = "international_seats" if applicant_type == "International Applicants" else "total_seats"
        filters = {
            "program": self.document.program,
            "admission_cycle": self.document.admission_cycle,
            "campus": self.document.campus,
        }
        seats = frappe.db.get_value("Programme Reservation Policy", {**filters, "status": "Active"}, fieldname)
        return seats or frappe.db.get_value("Programme Reservation Policy", filters, fieldname) or 0

    def get_eligible_applicants(self):
        if not self.document.program:
            return []
        args = {
            "academic_year": self.document.academic_year,
            "campus": self.document.campus,
            "admission_cycle": self.document.admission_cycle,
            "program": self.document.program,
        }
        common = """
            app.academic_year = %(academic_year)s AND app.campus = %(campus)s
            AND app.admission_cycle = %(admission_cycle)s AND app.program = %(program)s
            AND app.status != 'Rejected' AND app.name NOT IN (SELECT applicant_id FROM `tabInterview Applicant`)
            AND ((app.foriegn_national = 'Yes' AND p.international_interview = 1)
                 OR (COALESCE(app.foriegn_national, '') != 'Yes' AND p.intereview = 1))
        """
        columns = """app.name AS applicant_id, app.candidate_name, app.email, app.gender, app.program,
            app.program_level, app.entrance_test, app.intereview, app.foriegn_national"""
        queries = (
            ("National Test (Direct)", f"""SELECT {columns}, 0 AS entrance_test_score, 0 AS part_a_score, 1 AS cumulative_rank
                FROM `tabApplicant` app INNER JOIN `tabEligibility Evaluation` ee ON ee.applicant_name = app.name
                INNER JOIN `tabProgramme` p ON p.name = app.program
                WHERE {common} AND ee.exempts_entrance_test = 1 AND (ee.exempts_interview IS NULL OR ee.exempts_interview = 0)"""),
            ("Academic Eligibility", f"""SELECT {columns}, 0 AS entrance_test_score, 0 AS part_a_score, 1 AS cumulative_rank
                FROM `tabApplicant` app INNER JOIN `tabProgramme` p ON p.name = app.program
                WHERE {common} AND ((app.foriegn_national = 'Yes' AND p.international_entrance_test = 0)
                OR (COALESCE(app.foriegn_national, '') != 'Yes' AND p.entrance_test = 0))
                AND (app.exempts_interview IS NULL OR app.exempts_interview = 0)"""),
        )
        candidates = {}
        for source, query in queries:
            for row in frappe.db.sql(query, args, as_dict=True):
                row.source_type = source
                candidates[row.applicant_id] = row
        if not self.document.fetch_exempted_applicant:
            query = f"""SELECT {columns}, COALESCE(etsa.part_b_total_marks_scored, 0) AS entrance_test_score,
                COALESCE(etsa.part_a_total_marks_scored, 0) AS part_a_score,
                COALESCE(etsa.entrance_test_rank, 999999) AS cumulative_rank
                FROM `tabEntrance Test Seat Allocation` etsa INNER JOIN `tabApplicant` app ON app.name = etsa.applicant
                INNER JOIN `tabProgramme` p ON p.name = app.program
                WHERE {common} AND etsa.result_status = 'Pass' AND COALESCE(etsa.part_b_total_marks_scored, 0) > 0
                AND COALESCE(etsa.exempts_interview, 0) = 0"""
            for row in frappe.db.sql(query, args, as_dict=True):
                row.source_type = "Entrance Test"
                candidates[row.applicant_id] = row
        return list(candidates.values())

    def select(self, applicants):
        domestic = [app for app in applicants if app.get("foriegn_national") != "Yes"]
        international = [app for app in applicants if app.get("foriegn_national") == "Yes"]
        if self.document.applicant_type == "Domestic Applicants":
            return self._select(domestic, "Domestic Applicants", self.document.enter_domestic_ratio)
        if self.document.applicant_type == "International Applicants":
            return self._select(international, "International Applicants", self.document.enter_international_ratio)
        return self._select(domestic, "Domestic Applicants", self.document.enter_domestic_ratio) + self._select(
            international, "International Applicants", self.document.enter_international_ratio
        )

    def get_counts(self):
        applicants = self.get_eligible_applicants()
        selected = self.select(applicants)
        return {"total_eligible": len(applicants), "selected_count": len(selected)}

    def _select(self, applicants, applicant_type, ratio):
        if self.document.fetch_exempted_applicant or not ratio:
            return applicants
        if ":" in ratio:
            left, right = map(float, ratio.split(":"))
            multiplier = max(left, right) / min(left, right)
        else:
            multiplier = float(ratio)
        seats = self.get_total_seats(applicant_type)
        limit = math.ceil(seats * multiplier) if seats else len(applicants)
        selected, cutoff = [], None
        for applicant in sorted(applicants, key=lambda row: row.get("cumulative_rank", 999999)):
            rank = applicant.get("cumulative_rank", 999999)
            if len(selected) < limit or rank == cutoff:
                selected.append(applicant)
                cutoff = rank
            else:
                break
        return selected

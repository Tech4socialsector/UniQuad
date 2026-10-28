# hooks.py → add this to override / extend
# But better to put in custom app → doctype/entrance_test_generation/entrance_test_generation.py

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, getdate, now

class EntranceTestGeneration(Document):

    def before_save(self):
        if not self.generation_code:
            # optional: auto generate code like ETG-YY-#### 
            yr = getdate().strftime("%y")
            self.generation_code = frappe.generate_hash("EntranceTestGeneration", 8).upper()[:8]
            self.generation_code = f"ETG-{yr}-{self.generation_code}"



    @frappe.whitelist()
    def generate_test_list(self):
        if self.status not in ["Draft", "In Progress", "Failed"]: # Included Failed as well
            frappe.throw("Document must be in Draft, In Progress or Failed to generate test list")


        # Ensure schema is synced (updatedb is not a standard Frappe method)
        # frappe.db.updatedb("Entrance Test List")
        # frappe.db.updatedb("Entrance Test Applicant")

        # 1. Fetch Applicants based on Year, Campus, Cycle, and Level
        # 2. Filter out those who are EXEMPT from the entrance test (ee.exempts_entrance_test = 1)
        
        # User Logic:
        # National Test Passed | Exempts Entrance Test | Fetch Student?
        # No                   | -                    | ✅ YES
        # Yes                  | Unchecked            | ✅ YES
        # Yes                  | Checked              | ❌ NO
        
        query_filters = {
            "academic_year": self.academic_year,
            "campus": self.campus,
            "admission_cycle": self.admission_cycle,
            "program_level": self.program_level
        }
        
        program_filter = ""
        if self.program:
            program_filter = "AND app.program = %(program)s"
            query_filters["program"] = self.program

        applicants = frappe.db.sql(f"""
            SELECT 
                app.name as applicant_id,
                app.candidate_name,
                app.email,
                app.gender,
                app.pwd,
                app.program,
                app.program_level,
                app.entrance_test,
                app.intereview,
                COALESCE(ee.exempts_interview, 0) AS exempts_interview
            FROM `tabApplicant` app
            LEFT JOIN `tabEligibility Evaluation` ee ON ee.applicant_name = app.name
            INNER JOIN `tabProgramme` p ON p.name = app.program
            WHERE 
                app.academic_year = %(academic_year)s
                AND app.campus = %(campus)s
                AND app.admission_cycle = %(admission_cycle)s
                AND app.program_level = %(program_level)s
                {program_filter}
                AND (ee.exempts_entrance_test IS NULL OR ee.exempts_entrance_test = 0)
                AND app.name NOT IN (SELECT applicant_id FROM `tabEntrance Test Applicant`)
                AND app.name NOT IN (SELECT applicant FROM `tabEntrance Test Seat Allocation`)
                AND app.status = 'Submitted and Paid'
                AND (
                    (app.foriegn_national = 'Yes' AND p.international_entrance_test = 1)
                    OR
                    (COALESCE(app.foriegn_national, '') != 'Yes' AND p.entrance_test = 1 AND IFNULL(app.center_filled, 0) = 1)
                )
        """, query_filters, as_dict=True)

        if not applicants:
            self.db_set("status", "Failed")
            # Diagnostic for user:
            count_filters = {
                "academic_year": self.academic_year,
                "campus": self.campus,
                "admission_cycle": self.admission_cycle
            }
            if self.program:
                count_filters["program"] = self.program
            count_total = frappe.db.count("Applicant", count_filters)
            
            diagnostic_rows = f"""
                            <tr><td style="padding: 3px 0; font-weight: 600; width: 35%;">Year:</td><td>{self.academic_year}</td></tr>
                            <tr><td style="padding: 3px 0; font-weight: 600;">Campus:</td><td>{self.campus}</td></tr>
                            <tr><td style="padding: 3px 0; font-weight: 600;">Cycle:</td><td>{self.admission_cycle}</td></tr>
                            <tr><td style="padding: 3px 0; font-weight: 600;">Level:</td><td>{self.program_level}</td></tr>
            """
            if self.program:
                diagnostic_rows += f'<tr><td style="padding: 3px 0; font-weight: 600;">Programme:</td><td>{self.program}</td></tr>'

            msg = f"""
                <div style="padding: 15px; background-color: #fffaf0; border-left: 5px solid #ff8c00; border-radius: 8px;">
                    <h3 style="margin-top: 0; color: #d35400; font-size: 16px;">
                        ⚠️ No Eligible Applicants Found
                    </h3>
                    <p style="font-size: 14px; color: #333; margin-bottom: 12px;">
                        We couldn't find any applicants matching your selected criteria who are currently eligible for the Entrance Test list generation.
                    </p>
                    <div style="background: white; padding: 10px; border: 1px solid #ffe0b2; border-radius: 6px; margin-bottom: 15px;">
                        <table style="width: 100%; font-size: 13px; color: #555; border-collapse: collapse;">
                            {diagnostic_rows}
                        </table>
                    </div>
                    <div style="font-size: 12.5px; line-height: 1.5; color: #666;">
                        <strong style="color: #444;">Diagnostic Summary:</strong><br>
                        The system identified <b>{count_total} total applicants</b> matching this configuration. However, none were selected because they may be:
                        <ul style="margin-top: 5px; padding-left: 18px;">
                            <li>Assigned to a different Programme or Programme Level</li>
                            <li>Already included in an existing Entrance Test List</li>
                            <li>Marked as 'Exempt' from the Entrance Test</li>
                            <li>Rejected or in an ineligible application status</li>
                        </ul>
                    </div>
                </div>
            """
            frappe.throw(msg, title=_("Generation Failed"))

        test_list_data = {
            "doctype": "Entrance Test List",
            "academic_year": self.academic_year,
            "campus": self.campus,
            "admission_cycle": self.admission_cycle,
            "program_level": self.program_level,
            "generated_on": now(),
            "status": "Generated",
            "entrance_test_applicant": []
        }
        if self.program:
            test_list_data["program"] = self.program

        test_list = frappe.get_doc(test_list_data)

        for app in applicants:
            test_list.append("entrance_test_applicant", {
                "applicant_id": app.applicant_id,
                "candidate_name": app.candidate_name or "Unknown",
                "program": app.program,
                "program_level": app.program_level,
                "email": app.email,
                "gender": app.get("gender"),
                "pwd": 1 if str(app.get("pwd") or "").strip().lower() == "yes" else 0,
                "entrance_test": app.get("entrance_test"),
                "intereview": app.intereview,
                "exempts_entrance_test": 0,  # These students are NOT exempt from entrance test
                "exempts_interview": app.get("exempts_interview") or 0,
            })

        test_list.insert(ignore_permissions=True)

        self.db_set("status", "Completed")
        self.db_set("generated_on", now())
        self.db_set("generated_by", frappe.session.user)

        return test_list.name


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_program_query(doctype, txt, searchfield, start, page_len, filters):
    program_level = filters.get("program_level")
    admission_cycle = filters.get("admission_cycle")
    campus = filters.get("campus")

    if not admission_cycle:
        return []

    query_filters = {
        "admission_cycle": admission_cycle,
        "txt": f"%{txt}%"
    }

    level_filter = ""
    if program_level:
        level_filter = "AND p.level_of_study = %(program_level)s"
        query_filters["program_level"] = program_level

    campus_filter = ""
    if campus:
        campus_filter = "AND ac_p.campus = %(campus)s"
        query_filters["campus"] = campus

    return frappe.db.sql(f"""
        SELECT DISTINCT p.name, p.program_name
        FROM `tabProgramme` p
        INNER JOIN `tabAdmission Cycle Program` ac_p ON ac_p.program = p.name
        WHERE ac_p.parent = %(admission_cycle)s
          {level_filter}
          {campus_filter}
          AND (p.name LIKE %(txt)s OR p.program_name LIKE %(txt)s)
        ORDER BY p.name ASC
        LIMIT {page_len} OFFSET {start}
    """, query_filters)
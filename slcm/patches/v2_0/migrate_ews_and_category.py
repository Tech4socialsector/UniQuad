import frappe

def execute():
    """
    Migrate existing Applicant records:
    1. Update whether_scstobc_ncl from "NA" to "General".
    2. Move 'ews' = "Yes" applicants to whether_scstobc_ncl = "EWS".
    3. Move 'ews_certificate' to 'caste_certificate' for EWS applicants.
    """
    if frappe.db.has_column("Applicant", "whether_scstobc_ncl"):
        # 1. Update NA to General
        frappe.db.sql("""
            UPDATE `tabApplicant`
            SET whether_scstobc_ncl = 'General'
            WHERE whether_scstobc_ncl = 'NA'
        """)

        # 2. Check if the old EWS columns still exist in the DB
        has_ews = frappe.db.has_column("Applicant", "ews")
        has_ews_cert = frappe.db.has_column("Applicant", "ews_certificate")
        has_caste_cert = frappe.db.has_column("Applicant", "caste_certificate")

        if has_ews:
            if has_ews_cert and has_caste_cert:
                frappe.db.sql("""
                    UPDATE `tabApplicant`
                    SET whether_scstobc_ncl = 'EWS',
                        caste_certificate = IFNULL(ews_certificate, caste_certificate)
                    WHERE ews = 'Yes'
                """)
            else:
                frappe.db.sql("""
                    UPDATE `tabApplicant`
                    SET whether_scstobc_ncl = 'EWS'
                    WHERE ews = 'Yes'
                """)

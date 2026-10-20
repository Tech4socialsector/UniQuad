import frappe
import csv
from frappe.model.document import Document
from frappe.utils import now

class CLATRankImport(Document):
    def validate(self):
        # Check if the cycle has at least one CLAT program.
        is_clat_cycle = frappe.db.exists(
            "Admission Cycle Program",
            {"parent": self.admission_cycle, "exam_type": "CLAT"}
        )
        if not is_clat_cycle:
            frappe.throw(
                "CLAT Rank Import can only be linked to an Admission Cycle that has CLAT programs.",
                title="Invalid Cycle Type"
            )

    def on_submit(self):
        self.db_set("imported_by", frappe.session.user)
        self.db_set("imported_on", now())
        self.db_set("status", "Processing")
        self.process_import()

    def process_import(self):
        try:
            file_doc = frappe.get_doc("File", {"file_url": self.import_file})
            content = file_doc.get_content()
            if isinstance(content, bytes):
                content = content.decode("utf-8")
            reader = csv.DictReader(content.splitlines())
            count = 0
            for row in reader:
                count += 1
            self.db_set("total_records", count)
            self.db_set("status", "Completed")
        except Exception as e:
            self.db_set("status", "Failed")
            self.db_set("error_log", str(e))
            frappe.log_error(str(e), "CLAT Rank Import Error")
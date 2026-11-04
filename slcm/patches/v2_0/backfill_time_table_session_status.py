import frappe

from slcm.slcm.doctype.time_table.time_table import mark_completed_sessions


def execute():
    """Set the new Time Table Session Status on existing entries."""
    frappe.db.sql("UPDATE `tabTime Table` SET session_status = 'Scheduled' WHERE IFNULL(session_status, '') = ''")
    frappe.db.sql("UPDATE `tabTime Table` SET session_status = 'Cancelled' WHERE is_cancelled = 1")
    frappe.db.sql(
        """
        UPDATE `tabTime Table` tt
        SET tt.session_status = 'Swapped'
        WHERE tt.is_cancelled = 0
            AND tt.session_status = 'Scheduled'
            AND EXISTS (
                SELECT 1 FROM `tabClass Schedule Log` l
                WHERE l.time_table = tt.name AND l.action = 'Swapped'
            )
        """
    )
    mark_completed_sessions()

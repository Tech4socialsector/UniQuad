import frappe


def execute():
    """Fill the new Time Table Faculty Name field from the linked Faculty."""
    frappe.db.sql(
        """
        UPDATE `tabTime Table` tt
        JOIN `tabFaculty` f ON f.name = tt.instructor
        SET tt.instructor_name = f.first_name
        WHERE IFNULL(tt.instructor_name, '') != IFNULL(f.first_name, '')
        """
    )

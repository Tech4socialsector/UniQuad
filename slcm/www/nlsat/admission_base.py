"""
admission_base.html is the shared layout every NLSAT/PACE portal page extends.
Pages that extend it do not run this module; it only stops /nlsat/admission_base
from rendering the bare layout as a page.
"""

import frappe


def get_context(context):
	raise frappe.PageDoesNotExistError

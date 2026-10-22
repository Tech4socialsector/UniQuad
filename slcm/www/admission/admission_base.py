"""
admission_base.html is the shared layout every NLSAT/PACE portal page extends.
Pages that extend it do not run this module; it only stops the bare layout from
rendering as a page if its folder path is ever reached.
"""

import frappe


def get_context(context):
	raise frappe.PageDoesNotExistError

import json

import frappe
from frappe import _
from frappe.model.document import Document

from slcm.slcm.utils import id_card_render


class IDCardStarter(Document):
	def validate(self):
		try:
			data = id_card_render.parse_canvas_data(self.canvas_data)
		except ValueError:
			data = None
		if not data:
			frappe.throw(_("The starter design is not valid."))
		if not id_card_render.visible_elements(data, "front"):
			frappe.throw(_("The front side of the starter is empty."), title=_("Empty Design"))


@frappe.whitelist()
def get_gallery(exclude_template=None):
	"""User-saved starters and existing designer templates for the starter gallery."""
	starters = frappe.get_list(
		"ID Card Starter",
		fields=["name", "starter_name", "card_type", "description", "canvas_data"],
		order_by="modified desc",
	)
	templates = frappe.get_list(
		"ID Card Template",
		filters={
			"template_creation_mode": "Drag and Drop",
			"canvas_data": ["is", "set"],
			"name": ["!=", exclude_template or ""],
		},
		fields=["name", "template_name", "card_type", "canvas_data"],
		order_by="modified desc",
	)
	return {
		"starters": starters,
		"templates": templates,
		"can_create": frappe.has_permission("ID Card Starter", "create"),
		"can_delete": frappe.has_permission("ID Card Starter", "delete"),
	}


@frappe.whitelist()
def save_starter(starter_name, card_type, canvas_data, description=None, source_template=None):
	starter_name = (starter_name or "").strip()
	if not starter_name:
		frappe.throw(_("Give the starter a name."))
	if frappe.db.exists("ID Card Starter", starter_name):
		frappe.throw(_("A starter named {0} already exists. Choose another name.").format(frappe.bold(starter_name)))
	if isinstance(canvas_data, (dict, list)):
		canvas_data = json.dumps(canvas_data)

	doc = frappe.get_doc(
		{
			"doctype": "ID Card Starter",
			"starter_name": starter_name,
			"card_type": card_type or "Student",
			"description": description,
			"canvas_data": canvas_data,
			"source_template": source_template
			if source_template and frappe.db.exists("ID Card Template", source_template)
			else None,
		}
	).insert()
	return doc.name


@frappe.whitelist()
def delete_starter(name):
	frappe.delete_doc("ID Card Starter", name)

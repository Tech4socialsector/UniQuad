import frappe


def execute():
	"""Demand Type is now Academic / Non Academic and comes from the Fee Component.

	1. Give every Fee Component a Demand Type (from its component type) where it has none.
	2. Set every Fee Demand's Demand Type from its Fee Component (old values such as Examination,
	   Fine, Service, Hostel become Non Academic).
	"""
	frappe.reload_doc("slcm", "doctype", "fee_component")
	frappe.reload_doc("slcm", "doctype", "fee_demand")

	from slcm.slcm.doctype.fee_demand.fee_demand import demand_type_for_component_type

	component_type = {}
	for c in frappe.get_all("Fee Component", fields=["name", "component_type", "demand_type"]):
		dt = c.demand_type or demand_type_for_component_type(c.component_type)
		if not c.demand_type:
			frappe.db.set_value("Fee Component", c.name, "demand_type", dt, update_modified=False)
		component_type[c.name] = dt

	for d in frappe.get_all("Fee Demand", fields=["name", "fee_component", "demand_type"]):
		new = component_type.get(d.fee_component) or ("Academic" if d.demand_type == "Academic" else "Non Academic")
		if d.demand_type != new:
			frappe.db.set_value("Fee Demand", d.name, "demand_type", new, update_modified=False)

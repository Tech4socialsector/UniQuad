# SLCM Data Entry Map: every module in the order its data has to be entered,
# built from the module's own Workspace Sidebar so it stays in step with the menus.
# Counts go through DatabaseQuery, so the user's permissions apply; doctypes the
# user can't read are left out.

import frappe
from frappe import _
from frappe.model.db_query import DatabaseQuery

# key, title, sidebars it is built from, what it needs first, what it is for
MODULES = [
	("master", "Master setup", ["Master"], "", "Shared lookups used by every module."),
	("programme", "Programme Management", ["Programme Management"], "Master setup",
		"Academic calendar, programmes, courses, batches and classes."),
	("admission", "Admission", ["Eligibility", "Interview", "Merit", "Offer Letters", "Admission Fee", "Scholarship"],
		"Programme Management", "Applicants, eligibility, interviews, merit lists and offers."),
	("registration", "Student Registration", ["Student Registration"], "Admission",
		"Turns admitted applicants into enrolled students."),
	("attendance", "Attendance", ["Attendance"], "Programme Management, Student Registration",
		"Sessions, attendance marking, RFID and condonation."),
	("exams", "Examinations", ["Examinations"], "Programme Management, Attendance",
		"Exam plans, marks, results, re-exams and improvement."),
	("fees", "Fees Management", ["Fees Management", "Fee & Refund"], "Student Registration",
		"Fee structures, dues, collections and refunds."),
	("it", "IT Team", ["IT Team"], "Student Registration", "ID cards and RFID cards."),
	("venue", "Venue Bookings", ["Venue Bookings"], "Master setup", "Room bookings and approvals."),
	("promotions", "Promotions", ["Promotions"], "Examinations", "Moving students to the next year."),
	("transcripts", "Transcript Management", ["Transcript Management"], "Examinations", "Transcript requests and templates."),
	("pace", "PACE", ["PACE"], "Student Registration", "PACE applications."),
	("fle", "FLE", ["FLE"], "Student Registration", "FLE applications."),
]

# the shortest path to a published result
QUICKSTART = [
	("Academic Year", "Academic Year"), ("Academic Term", "Academic Term"), ("Programme", "Programme"),
	("Course", "Course"), ("Batch", "SLCM Batch"), ("Classes", "Classes"),
	("Student Master", "Student Master"), ("Student Enrollment", "Student Enrollment"),
	("Exam Plan", "Exam Plan"), ("Student Course Marks", "Student Course Marks"),
	("Result Publish", "Student Result Publish"),
]

EXCLUDE = {"SLCM Department", "Department"}


def _count(doctype):
	sql = DatabaseQuery(doctype).execute(fields=[f"`tab{doctype}`.name"], run=0)
	return frappe.db.sql(f"select count(*) from ({sql}) t")[0][0]


def _sidebar_sections(sidebar):
	"""[(section label, [(label, doctype)])] from a sidebar's DocType links, plus its home workspace."""
	items = frappe.get_all("Workspace Sidebar Item", filters={"parent": sidebar},
		fields=["type", "label", "link_type", "link_to"], order_by="idx")
	home, sections, current = None, [], None
	for i in items:
		if i.type == "Section Break":
			current = (i.label.strip(), [])
			sections.append(current)
		elif i.type == "Link" and i.link_type == "Workspace" and not home:
			home = i.link_to
		elif i.type == "Link" and i.link_type == "DocType" and i.link_to:
			if current is None:
				current = ("", [])
				sections.append(current)
			current[1].append((i.label, i.link_to))
	return home, [s for s in sections if s[1]]


@frappe.whitelist()
def get_map():
	sidebars = set(frappe.get_all("Workspace Sidebar", pluck="name"))
	seen = set()
	built = {}
	# specific modules claim their doctypes first; Master setup keeps only what is left
	for key, title, bars, needs, about in sorted(MODULES, key=lambda m: m[0] == "master"):
		home, sections = None, []
		for bar in bars:
			if bar not in sidebars:
				continue
			h, secs = _sidebar_sections(bar)
			home = home or h
			if bar != bars[0]:
				# extra sidebars of a module become one section each, named after the sidebar
				secs = [(bar, [link for _label, links in secs for link in links])]
			for label, links in secs:
				label = label or (bar if len(bars) > 1 else _("Records"))
				docs = []
				for doc_label, dt in links:
					if dt in seen or dt in EXCLUDE or not frappe.db.exists("DocType", dt):
						continue
					seen.add(dt)
					if not frappe.has_permission(dt, "read"):
						continue
					single = frappe.get_meta(dt).issingle
					docs.append({"label": (doc_label or dt).strip(), "doctype": dt, "single": single,
						"count": None if single else _count(dt)})
				if docs:
					sections.append({"label": label, "docs": docs})
		if sections:
			built[key] = {"key": key, "title": _(title), "needs": _(needs) if needs else "", "about": _(about),
				"workspace": home, "sections": sections,
				"total": sum(d["count"] or 0 for s in sections for d in s["docs"])}

	modules = [built[m[0]] for m in MODULES if m[0] in built]
	for n, m in enumerate(modules, 1):
		m["num"] = n
	quick = [{"label": _(label), "doctype": dt, "count": _count(dt)}
		for label, dt in QUICKSTART if frappe.db.exists("DocType", dt) and frappe.has_permission(dt, "read")]
	return {"modules": modules, "quickstart": quick}

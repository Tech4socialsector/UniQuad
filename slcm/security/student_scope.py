"""
Row-level access for student-facing doctypes.

A user whose only route to a doctype is a student role (slcm_Student /
Student) may see and touch only records that belong to their own Student
Master. Staff who also hold a student role keep their normal access, as long
as one of their other roles grants read on the doctype.

Wired in hooks.py through `permission_query_conditions` (list / search /
report queries) and `has_permission` (single-record reads, prints, REST).
"""

import frappe

STUDENT_ROLES = frozenset({"slcm_Student", "Student"})

# doctype -> field that holds the Student Master name ("name" = the record itself)
STUDENT_FIELD = {
	"Student Master": "name",
	"Student Placement Profile": "student",
	"Placement Application": "student",
	"Grade Appeal": "student",
	"Re Exam Registration": "student",
	"Improvement Exam Registration": "student",
	"Fee Demand": "student",
	"Fee Receipt": "student",
	"Stipend Payment": "student",
	"Transcript Request": "student",
	"Student Leave Applications": "student",
	"Office Hours Attendance": "student",
	"Attendance Summary": "student",
	"FA MFA Application": "student",
	"Venue Booking": "student",
}


def own_students(user=None):
	"""Student Master names linked to this login (user, email or official email)."""
	user = user or frappe.session.user
	cache = getattr(frappe.local, "slcm_own_students", None)
	if cache is None:
		cache = frappe.local.slcm_own_students = {}
	if user not in cache:
		cache[user] = frappe.db.sql(
			"""SELECT name FROM `tabStudent Master`
			WHERE `user` = %(u)s OR email = %(u)s OR official_email_id = %(u)s""",
			{"u": user},
			pluck=True,
		)
	return cache[user]


def _non_student_read_roles(doctype):
	roles = set()
	for table in ("DocPerm", "Custom DocPerm"):
		roles.update(
			frappe.get_all(table, filters={"parent": doctype, "read": 1}, pluck="role")
		)
	return roles - STUDENT_ROLES


def is_student_scoped(user, doctype):
	"""True when the user reaches `doctype` only through a student role."""
	if not user or user == "Administrator":
		return False
	roles = set(frappe.get_roles(user))
	if not roles & STUDENT_ROLES:
		return False
	return not roles & _non_student_read_roles(doctype)


def student_condition(doctype, user):
	"""SQL fragment restricting `doctype` to the user's own students."""
	field = STUDENT_FIELD[doctype]
	students = own_students(user)
	if not students:
		return "1=0"
	values = ", ".join(frappe.db.escape(s) for s in students)
	return f"`tab{doctype}`.`{field}` IN ({values})"


def query_conditions(user=None, doctype=None):
	user = user or frappe.session.user
	if doctype not in STUDENT_FIELD or not is_student_scoped(user, doctype):
		return ""
	return student_condition(doctype, user)


def has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if doc.doctype not in STUDENT_FIELD or not is_student_scoped(user, doc.doctype):
		return True
	value = doc.get(STUDENT_FIELD[doc.doctype])
	if not value:
		# Brand-new record not yet tied to a student: let validation decide.
		return ptype == "create" and doc.is_new()
	return value in own_students(user)

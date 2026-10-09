# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Class Participation / Office Hours (OH) marking for Time Table sessions.

Class sessions (kind "cp"): a Time Table series carries a "Class
Participation Week Group" table; each row maps a date range
(start_date..end_date) to a Class-Participation Student Group. Every class
falling inside that range is one participation "hour" for that group - the
1st class of the week fills class_participation_1st_hour / 1st_cp_grade on
each student's Student Group Student row, the 2nd class the 2nd hour, and so
on up to the 6 slots the child table has.

OH sessions (kind "oh"): the Time Table's office_hours_group is an Office
Hours Student Group. Every OH session scheduled against that group is one
"hour" - the 1st fills office_hour_1st_hour / 1st_oh_grade, the 2nd
office_hour_2nd_hour / 2nd_oh_grade (the 2 slots the child table has).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, get_datetime, getdate, now_datetime

HOURS = ("1st", "2nd", "3rd", "4th", "5th", "6th")
CP_GROUP_TYPE = "Class-Participation"
OH_GROUP_TYPE = "Office Hours"
OH_SLOTS = 2

# Highest mark a faculty can award for one class / OH session.
CP_MAX_GRADE = 10


def hour_fields(slot, kind="cp"):
	"""(participation check field, grade field) on Student Group Student for a 1-based slot."""
	hour = HOURS[slot - 1]
	if kind == "oh":
		return f"office_hour_{hour}_hour", f"{hour}_oh_grade"
	return f"class_participation_{hour}_hour", f"{hour}_cp_grade"


def get_participation_context(session):
	"""Resolve which Student Group and hour slot an Attendance Session records
	participation into - Class-Participation for class sessions, Office Hours
	for OH sessions. Always returns a dict; `available` is False (with a
	`reason` to show the faculty) when it can't be marked."""
	is_oh = session.session_type == "Office Hour"
	ctx = frappe._dict(
		available=False,
		reason=None,
		max_grade=CP_MAX_GRADE,
		kind="oh" if is_oh else "cp",
		tab_label=_("OH Participants") if is_oh else _("Class Participants"),
	)

	if not session.class_schedule:
		ctx.reason = _("Participation is recorded only for sessions scheduled in the Time Table.")
		return ctx

	tt = frappe.db.get_value(
		"Time Table",
		session.class_schedule,
		["name", "parent_schedule", "schedule_date", "office_hours_group"],
		as_dict=True,
	)
	if not tt:
		ctx.reason = _("The Time Table entry for this session no longer exists.")
		return ctx

	if is_oh:
		return _oh_context(ctx, tt)
	return _cp_context(ctx, session, tt)


def _oh_context(ctx, tt):
	root = tt.parent_schedule or tt.name
	# Older generated occurrences may lack the group - the series root has it.
	group = tt.office_hours_group or (
		frappe.db.get_value("Time Table", root, "office_hours_group") if root != tt.name else None
	)
	if not group:
		ctx.reason = _("No OH Group is set on this session's Time Table.")
		return ctx

	sg = frappe.db.get_value("Student Group", group, ["group_based_on", "week_name"], as_dict=True)
	if not sg:
		ctx.reason = _("OH Group {0} no longer exists.").format(group)
		return ctx
	if sg.group_based_on != OH_GROUP_TYPE:
		ctx.reason = _("Student Group {0} is not an OH group.").format(group)
		return ctx

	# All OH sessions scheduled against this group, across every series that
	# references it, in date/time order -> this session's slot.
	roots = {
		t.parent_schedule or t.name
		for t in frappe.get_all(
			"Time Table", filters={"office_hours_group": group}, fields=["name", "parent_schedule"]
		)
	} | {root}
	sessions = frappe.get_all(
		"Time Table",
		filters={"docstatus": ["<", 2]},
		or_filters={"name": ["in", list(roots)], "parent_schedule": ["in", list(roots)]},
		fields=["name"],
		order_by="schedule_date asc, from_time asc, name asc",
	)
	names = [s.name for s in sessions]
	if tt.name not in names:
		ctx.reason = _("This session is not part of OH Group {0}'s schedule.").format(group)
		return ctx

	slot = names.index(tt.name) + 1
	if slot > OH_SLOTS:
		ctx.reason = _(
			"This is OH session {0} for group {1}, but only {2} OH hours can be recorded per group."
		).format(slot, group, OH_SLOTS)
		return ctx

	ctx.update(
		available=True,
		group=group,
		week_name=sg.week_name or group,
		slot=slot,
		slot_label=_("{0} Hour").format(HOURS[slot - 1]),
		classes_in_week=len(names),
	)
	return ctx


def _cp_context(ctx, session, tt):

	session_date = getdate(session.session_date or tt.schedule_date)
	root = tt.parent_schedule or tt.name

	# Generated occurrences carry a copy of the series' week table; the series
	# root is authoritative, the occurrence's own copy is the fallback.
	week = None
	for parent in dict.fromkeys([root, tt.name]):
		rows = frappe.get_all(
			"Class Participation Week",
			filters={
				"parenttype": "Time Table",
				"parent": parent,
				"start_date": ["<=", session_date],
				"end_date": [">=", session_date],
			},
			fields=["week", "start_date", "end_date"],
			order_by="idx",
			limit=1,
		)
		if rows:
			week = rows[0]
			break

	if not week:
		ctx.reason = _("No Class Participation week is configured in the Time Table for {0}.").format(
			formatdate(session_date)
		)
		return ctx

	if frappe.db.get_value("Student Group", week.week, "group_based_on") != CP_GROUP_TYPE:
		ctx.reason = _("Student Group {0} is not a Class-Participation group.").format(week.week)
		return ctx

	# Every Time Table class mapped to this same group in this week - across
	# all series that reference it, so two weekly series (e.g. Mon + Thu)
	# feeding one group get slots 1 and 2 instead of both claiming slot 1.
	series = frappe.get_all(
		"Class Participation Week",
		filters={"parenttype": "Time Table", "week": week.week},
		pluck="parent",
	)
	classes = frappe.get_all(
		"Time Table",
		filters={
			"schedule_date": ["between", [week.start_date, week.end_date]],
			"docstatus": ["<", 2],
		},
		or_filters={"name": ["in", series], "parent_schedule": ["in", series]},
		fields=["name"],
		order_by="schedule_date asc, from_time asc, name asc",
	)
	class_names = [c.name for c in classes]
	if tt.name not in class_names:
		ctx.reason = _("This class is not part of the Class Participation week schedule.")
		return ctx

	slot = class_names.index(tt.name) + 1
	if slot > len(HOURS):
		ctx.reason = _(
			"This is class {0} in the week of {1} - {2}, but only {3} class participation hours can be recorded per week."
		).format(slot, formatdate(week.start_date), formatdate(week.end_date), len(HOURS))
		return ctx

	ctx.update(
		available=True,
		group=week.week,
		week_name=frappe.db.get_value("Student Group", week.week, "week_name") or week.week,
		start_date=str(week.start_date),
		end_date=str(week.end_date),
		start_date_fmt=formatdate(week.start_date, "dd MMM yyyy"),
		end_date_fmt=formatdate(week.end_date, "dd MMM yyyy"),
		slot=slot,
		slot_label=_("{0} Hour").format(HOURS[slot - 1]),
		classes_in_week=len(class_names),
	)
	return ctx


def get_participation_roster(ctx):
	"""Students of the week's group with what's already recorded in this slot."""
	check_field, grade_field = hour_fields(ctx.slot, ctx.kind)
	group = frappe.get_doc("Student Group", ctx.group)

	student_ids = [row.student for row in group.students if row.student]
	masters = {
		m.name: m
		for m in frappe.get_all(
			"Student Master",
			filters={"name": ["in", student_ids or [""]]},
			fields=["name", "first_name", "last_name", "registration_id", "passport_size_photo"],
			ignore_permissions=True,
		)
	}

	students = []
	for row in group.students:
		if not row.student:
			continue
		m = masters.get(row.student) or frappe._dict()
		participated = cint(row.get(check_field))
		students.append({
			"student": row.student,
			"student_name": " ".join(filter(None, [m.get("first_name"), m.get("last_name")])) or row.student,
			"reg_id": m.get("registration_id") or row.student_id or row.student,
			"student_image": m.get("passport_size_photo"),
			"participated": participated,
			"grade": flt(row.get(grade_field)) if participated else None,
		})

	return {
		"students": students,
		# Whether this hour was saved before - if not, the portal pre-ticks
		# everyone who is present in attendance.
		"slot_recorded": any(s["participated"] for s in students),
	}


def save_class_participation(session, ctx, participation, att_map):
	"""Write participation + marks for this session's slot onto the week's
	Student Group.

	`participation`: list of {student, participated, grade}, or None when the
	faculty didn't edit the Class Participants tab. `att_map`: {student:
	status} just saved for the session. Absent students always have this slot
	cleared, so participation can never outlive a later "Absent" correction.
	"""
	check_field, grade_field = hour_fields(ctx.slot, ctx.kind)
	what = _("OH participation") if ctx.kind == "oh" else _("class participation")
	group = frappe.get_doc("Student Group", ctx.group)
	rows_by_student = {row.student: row for row in group.students if row.student}

	submitted = {}
	for entry in participation or []:
		student = entry.get("student")
		if student not in rows_by_student:
			frappe.throw(_("Student {0} is not in group {1}.").format(student, ctx.group))

		participated = cint(entry.get("participated"))
		grade = entry.get("grade")
		has_grade = grade not in (None, "")

		if participated:
			if att_map.get(student) != "Present":
				frappe.throw(
					_("{0} is not marked Present, so {1} cannot be recorded.").format(student, what)
				)
			# The mark may be entered later (a separate "Grade" pending task) -
			# a blank mark is stored as 0 and counts as not yet graded.
			grade = flt(grade, 2) if has_grade else 0
			if grade < 0 or grade > CP_MAX_GRADE:
				frappe.throw(
					_("Mark for {0} must be between 0 and {1}.").format(student, CP_MAX_GRADE)
				)
		elif has_grade and flt(grade):
			frappe.throw(_("{0} has a mark but is not marked as participated.").format(student))

		submitted[student] = (participated, grade if participated else 0)

	changed = False
	for student, row in rows_by_student.items():
		if student in submitted:
			participated, grade = submitted[student]
		elif att_map.get(student) == "Absent":
			participated, grade = 0, 0
		else:
			continue

		if cint(row.get(check_field)) != participated or flt(row.get(grade_field)) != flt(grade):
			row.set(check_field, participated)
			row.set(grade_field, grade)
			changed = True

	if changed:
		group.save(ignore_permissions=True)


# ── Student view (student portal Attendance page) ────────────────────────

def get_student_participation(student):
	"""The student's Class Participation and OH, per group, for the student
	portal - attendance and participation only. Marks (*_cp_grade /
	*_oh_grade) are deliberately never read here.

	Returns {"cp": [group, ...], "oh": [group, ...]}; each group:
	  group, title (week name), course_name, start_date_fmt / end_date_fmt (CP),
	  sessions: [{date_fmt, weekday, time, venue, faculty, slot_label,
	              attendance: Present | Absent | Not marked | Upcoming,
	              participation: Participated | Did not participate |
	                             Not recorded yet | Upcoming}],
	  attended, participated, held (counts over sessions already held).
	Uses the same group / slot rules as the faculty portal."""
	member_rows = frappe.db.sql(
		"""SELECT sgs.parent AS grp, sg.group_based_on, sg.week_name, sg.course_offering,
		          {checks}
		   FROM `tabStudent Group Student` sgs
		   JOIN `tabStudent Group` sg ON sg.name = sgs.parent
		   WHERE sgs.student = %(student)s AND sgs.parenttype = 'Student Group'""".format(
			checks=", ".join(
				f"sgs.`{hour_fields(n, k)[0]}`"
				for k, count in (("cp", len(HOURS)), ("oh", OH_SLOTS))
				for n in range(1, count + 1)
			)
		),
		{"student": student},
		as_dict=True,
	)
	result = {"cp": [], "oh": []}
	if not member_rows:
		return result

	mine = {}  # group -> (kind, member row)
	for r in member_rows:
		kind = "oh" if r.group_based_on == OH_GROUP_TYPE else "cp" if r.group_based_on == CP_GROUP_TYPE else None
		if kind:
			mine[r.grp] = (kind, r)
	if not mine:
		return result

	# Time Table series that reference the student's groups, and all their entries
	cp_groups = [g for g, (k, _) in mine.items() if k == "cp"]
	oh_groups = [g for g, (k, _) in mine.items() if k == "oh"]
	series = set(frappe.get_all(
		"Class Participation Week",
		filters={"parenttype": "Time Table", "week": ["in", cp_groups or [""]]},
		pluck="parent",
	))
	series |= {
		t.parent_schedule or t.name
		for t in frappe.get_all(
			"Time Table", filters={"office_hours_group": ["in", oh_groups or [""]]},
			fields=["name", "parent_schedule"],
		)
	}
	if not series:
		return result
	tts = {
		t.name: t
		for t in frappe.get_all(
			"Time Table",
			filters={"docstatus": ["<", 2]},
			or_filters={"name": ["in", list(series)], "parent_schedule": ["in", list(series)]},
			fields=["name", "venue", "instructor", "from_time", "to_time"],
		)
	}
	sessions = frappe.get_all(
		"Attendance Session",
		filters={"class_schedule": ["in", list(tts) or [""]], "docstatus": ["<", 2]},
		fields=["name", "class_schedule", "session_date", "session_start_time", "session_type", "course_offering"],
		order_by="session_date asc, session_start_time asc",
	)
	slots = _bulk_session_slots(sessions)
	recorded, _ungraded = _bulk_slot_state(set(mine))

	att_status = dict(frappe.get_all(
		"Student Attendance",
		filters={"student": student, "attendance_session": ["in", [s.name for s in sessions] or [""]], "docstatus": ["<", 2]},
		fields=["attendance_session", "status"],
		as_list=True,
	))
	co_names = dict(frappe.get_all(
		"Course Offering",
		filters={"name": ["in", list({s.course_offering for s in sessions if s.course_offering} | {r.course_offering for _, r in mine.values() if r.course_offering}) or [""]]},
		fields=["name", "course_name"],
		as_list=True,
	))
	faculty_ids = {t.instructor for t in tts.values() if t.instructor}
	faculty_names = {
		str(f.name): " ".join(filter(None, [f.first_name, f.last_name]))
		for f in frappe.get_all("Faculty", filters={"name": ["in", list(faculty_ids) or [""]]},
		                        fields=["name", "first_name", "last_name"])
	}
	# CP week date ranges, per group
	week_range = {}
	for w in frappe.get_all(
		"Class Participation Week",
		filters={"parenttype": "Time Table", "week": ["in", cp_groups or [""]]},
		fields=["week", "start_date", "end_date"],
	):
		lo, hi = week_range.get(w.week, (None, None))
		week_range[w.week] = (min(filter(None, [lo, getdate(w.start_date)])), max(filter(None, [hi, getdate(w.end_date)])))

	now = now_datetime()
	groups = {}
	for s in sessions:
		resolved = slots.get(s.name)
		if not resolved or resolved[1] not in mine:
			continue
		kind, group, slot = resolved
		member = mine[group][1]
		tt = tts.get(s.class_schedule) or frappe._dict()
		started = _session_has_started(s, now)
		if not started:
			attendance = participation = "Upcoming"
		else:
			attendance = att_status.get(s.name) or "Not marked"
			if (kind, group, slot) in recorded:
				participation = "Participated" if cint(member.get(hour_fields(slot, kind)[0])) else "Did not participate"
			else:
				participation = "Not recorded yet"

		g = groups.get(group)
		if not g:
			lo_hi = week_range.get(group)
			g = groups[group] = frappe._dict(
				group=group, kind=kind, title=member.week_name or group,
				# The sessions' own course (what the student actually attends);
				# the group's Course Offering field only as a fallback
				course_name=co_names.get(s.course_offering) or co_names.get(member.course_offering) or "",
				start_date_fmt=formatdate(lo_hi[0], "dd MMM yyyy") if lo_hi else "",
				end_date_fmt=formatdate(lo_hi[1], "dd MMM yyyy") if lo_hi else "",
				sessions=[], attended=0, participated=0, held=0, sort_key=str(s.session_date),
			)
		d = getdate(s.session_date)
		from_fmt, to_fmt = _fmt_12h(s.session_start_time or tt.from_time), _fmt_12h(tt.to_time)
		g.sessions.append(frappe._dict(
			date=str(d), date_fmt=formatdate(d, "dd MMM yyyy"), weekday=d.strftime("%a"),
			from_fmt=from_fmt, to_fmt=to_fmt, course_offering=s.course_offering or "",
			time=" – ".join(filter(None, [from_fmt, to_fmt])),
			venue=tt.venue or "", faculty=faculty_names.get(str(tt.instructor)) or "",
			slot_label=_("{0} Hour").format(HOURS[slot - 1]),
			attendance=attendance, participation=participation,
		))
		if started:
			g.held += 1
			g.attended += attendance == "Present"
			g.participated += participation == "Participated"

	for g in sorted(groups.values(), key=lambda x: x.sort_key):
		result[g.kind].append(g)
	return result


def _fmt_12h(t):
	"""Time / timedelta / "HH:MM:SS" → "9:57 AM" ("" when empty)."""
	if not t:
		return ""
	if hasattr(t, "seconds"):
		h, rem = divmod(int(t.total_seconds()) % 86400, 3600)
		m = rem // 60
	else:
		parts = str(t).split(":")
		h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
	return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


# ── Pending tasks (dashboard card + attendance page filter) ──────────────
TASKS = ("course_att", "cp_att", "cp_grade", "oh_att", "oh_grade")


def _session_has_started(session, now):
	"""Past dates always; today only once the session's start time has passed."""
	day = getdate(session["session_date"])
	if day != now.date():
		return day < now.date()
	start = session.get("session_start_time")
	if not start:
		return True
	return get_datetime(f"{day} {start}") <= now


def get_session_task_flags(sessions, today=None):
	"""{session name: set of pending task keys} for Attendance Sessions that
	have already started (earlier days, or today once the start time has
	passed) - later-today and future sessions are never "pending".
	`sessions`: dicts with name, class_schedule, session_date,
	session_start_time, session_type, attendance_marked.

	  course_att  class session whose attendance isn't marked
	  cp_att      class session whose Class Participation hour isn't recorded
	  cp_grade    CP hour recorded, but a participant has no mark yet
	  oh_att      OH session whose attendance isn't marked
	  oh_grade    OH hour recorded, but a participant has no mark yet

	Same group/slot rules as get_participation_context, resolved in bulk
	(a fixed handful of queries regardless of how many sessions)."""
	now = now_datetime()
	if today and getdate(today) != now.date():
		# Explicit reference day other than today: whole days only
		due = [s for s in sessions if s.get("session_date") and getdate(s["session_date"]) <= getdate(today)]
	else:
		due = [s for s in sessions if s.get("session_date") and _session_has_started(s, now)]
	flags = {s["name"]: set() for s in due}
	if not due:
		return flags

	for s in due:
		is_oh = s.get("session_type") == "Office Hour"
		if not cint(s.get("attendance_marked")):
			flags[s["name"]].add("oh_att" if is_oh else "course_att")

	slots = _bulk_session_slots(due)  # {session: (kind, group, slot)}
	groups = {g for _, g, _ in slots.values()}
	recorded, ungraded = _bulk_slot_state(groups)

	for s in due:
		resolved = slots.get(s["name"])
		if not resolved:
			continue
		kind, group, slot = resolved
		key = (kind, group, slot)
		if kind == "cp" and key not in recorded:
			flags[s["name"]].add("cp_att")
		elif key in ungraded:
			flags[s["name"]].add(f"{kind}_grade")
	return flags


def _bulk_session_slots(sessions):
	tt_names = list({s["class_schedule"] for s in sessions if s.get("class_schedule")})
	if not tt_names:
		return {}

	tts = {
		t.name: t
		for t in frappe.get_all(
			"Time Table",
			filters={"name": ["in", tt_names]},
			fields=["name", "parent_schedule", "office_hours_group"],
		)
	}
	roots = {t.parent_schedule or t.name for t in tts.values()}
	root_oh = dict(
		frappe.get_all(
			"Time Table", filters={"name": ["in", list(roots)]}, fields=["name", "office_hours_group"], as_list=True
		)
	)

	# CP week rows of every series involved
	week_rows = frappe.get_all(
		"Class Participation Week",
		filters={"parenttype": "Time Table", "parent": ["in", list(roots | set(tts))]},
		fields=["parent", "week", "start_date", "end_date", "idx"],
		order_by="idx",
	)
	weeks_by_parent = {}
	for r in week_rows:
		weeks_by_parent.setdefault(r.parent, []).append(r)

	# Every series referencing the CP / OH groups involved, and all their entries
	cp_groups = {r.week for r in week_rows}
	cp_parents_by_group = {}
	for r in frappe.get_all(
		"Class Participation Week",
		filters={"parenttype": "Time Table", "week": ["in", list(cp_groups) or [""]]},
		fields=["parent", "week"],
	):
		cp_parents_by_group.setdefault(r.week, set()).add(r.parent)

	oh_groups = {g for g in list(root_oh.values()) + [t.office_hours_group for t in tts.values()] if g}
	oh_roots_by_group = {}
	for t in frappe.get_all(
		"Time Table",
		filters={"office_hours_group": ["in", list(oh_groups) or [""]]},
		fields=["name", "parent_schedule", "office_hours_group"],
	):
		oh_roots_by_group.setdefault(t.office_hours_group, set()).add(t.parent_schedule or t.name)

	series = set()
	for v in cp_parents_by_group.values():
		series |= v
	for v in oh_roots_by_group.values():
		series |= v
	entries = frappe.get_all(
		"Time Table",
		filters={"docstatus": ["<", 2]},
		or_filters={"name": ["in", list(series) or [""]], "parent_schedule": ["in", list(series) or [""]]},
		fields=["name", "parent_schedule", "schedule_date", "from_time"],
		order_by="schedule_date asc, from_time asc, name asc",
	)

	result = {}
	for s in sessions:
		tt = tts.get(s.get("class_schedule"))
		if not tt:
			continue
		root = tt.parent_schedule or tt.name
		if s.get("session_type") == "Office Hour":
			group = tt.office_hours_group or root_oh.get(root)
			members = oh_roots_by_group.get(group, set())
			ordered = [e.name for e in entries if (e.parent_schedule or e.name) in members]
			kind, max_slots = "oh", OH_SLOTS
		else:
			day = getdate(s["session_date"])
			week = next(
				(w for w in weeks_by_parent.get(root) or weeks_by_parent.get(tt.name) or []
				 if getdate(w.start_date) <= day <= getdate(w.end_date)),
				None,
			)
			if not week:
				continue
			group = week.week
			members = cp_parents_by_group.get(group, set())
			ordered = [
				e.name for e in entries
				if (e.name in members or e.parent_schedule in members)
				and getdate(week.start_date) <= getdate(e.schedule_date) <= getdate(week.end_date)
			]
			kind, max_slots = "cp", len(HOURS)
		if not group or tt.name not in ordered:
			continue
		slot = ordered.index(tt.name) + 1
		if slot <= max_slots:
			result[s["name"]] = (kind, group, slot)
	return result


def _bulk_slot_state(groups):
	"""(recorded, ungraded) sets of (kind, group, slot): recorded = someone is
	ticked in that hour; ungraded = a ticked student has no (zero) mark."""
	recorded, ungraded = set(), set()
	if not groups:
		return recorded, ungraded

	group_kind = {
		g.name: ("oh" if g.group_based_on == OH_GROUP_TYPE else "cp")
		for g in frappe.get_all("Student Group", filters={"name": ["in", list(groups)]}, fields=["name", "group_based_on"])
	}
	cols = []
	for kind, n in (("cp", len(HOURS)), ("oh", OH_SLOTS)):
		for slot in range(1, n + 1):
			cols.extend(hour_fields(slot, kind))
	rows = frappe.db.sql(
		"SELECT parent, {} FROM `tabStudent Group Student` WHERE parenttype = 'Student Group' AND parent IN %(groups)s".format(
			", ".join(f"`{c}`" for c in cols)
		),
		{"groups": tuple(groups)},
		as_dict=True,
	)
	for row in rows:
		kind = group_kind.get(row.parent)
		if not kind:
			continue
		for slot in range(1, (OH_SLOTS if kind == "oh" else len(HOURS)) + 1):
			check_field, grade_field = hour_fields(slot, kind)
			if cint(row.get(check_field)):
				recorded.add((kind, row.parent, slot))
				if not flt(row.get(grade_field)):
					ungraded.add((kind, row.parent, slot))
	return recorded, ungraded

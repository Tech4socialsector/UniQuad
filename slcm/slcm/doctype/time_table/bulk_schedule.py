# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Bulk Time Table creation from the Classes list.

One run schedules several Classes on the same slot pattern (dates, weekdays,
times), each Class with its own Faculty and Venue. preview_bulk_schedule() and
create_bulk_schedule() share build_plan(), so what gets created is exactly what
the preview showed - re-checked against the database at the moment of creation.

Every (Class, weekday) becomes one recurring series: the first session is the
series root and the rest point at it through parent_schedule, so the Time Table
form's "apply to future occurrences" works on them as on any repeated entry.
"""

import json
from datetime import timedelta

import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.utils import cint, formatdate, getdate, to_timedelta

from slcm.slcm.doctype.institutional_calendar.institutional_calendar import DEFAULT_WEEKLY_OFF_DAYS
from slcm.slcm.doctype.time_table.time_table import (
	format_time_12h,
	publish_bulk_progress,
	quiet_bulk_operation,
)

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
REPEATS = ("Never", "Daily", "Weekly", "Monthly")
# Institutional Calendar entry types each Skip option covers (holidays and
# weekly offs are always skipped - Time Table refuses them anyway)
EXAM_ENTRY_TYPES = ("Exam",)
OTHER_ENTRY_TYPES = ("Event", "Orientation", "Other")
# One request inserts every session (plus its Attendance Session); keep a run
# well inside the web request timeout.
MAX_SESSIONS = 600

OK, WARNING, SKIPPED = "ok", "warning", "skipped"


@frappe.whitelist()
def preview_bulk_schedule(args):
	plan = build_plan(_parse_args(args))
	return {"summary": plan["summary"], "classes": plan["classes"], "sessions": plan["sessions"]}


@frappe.whitelist()
def create_bulk_schedule(args):
	from slcm.slcm.doctype.class_schedule_log.class_schedule_log import add_log, no_schedule_log

	args = _parse_args(args)
	plan = build_plan(args)
	to_create = [s for s in plan["sessions"] if s["status"] != SKIPPED]
	if not to_create:
		frappe.throw(_("Nothing to create - every session was skipped."), title=_("Bulk Time Table"))
	if len(to_create) > MAX_SESSIONS:
		frappe.throw(
			_("This run would create {0} sessions; the limit is {1}. Split it into smaller runs (fewer classes or a shorter date range).").format(
				len(to_create), MAX_SESSIONS
			),
			title=_("Too Many Sessions"),
		)

	roots = {}  # (class_name, series key) -> root Time Table name
	series = {}  # root -> details for the Class Schedule Log
	total = len(to_create)
	with quiet_bulk_operation(), no_schedule_log():
		publish_bulk_progress(_("Creating Time Table"), 0, total)
		for i, s in enumerate(to_create, 1):
			key = (s["class_name"], s["series"])
			doc = frappe.get_doc({
				"doctype": "Time Table",
				"based_on": "Class",
				"class_name": s["class_name"],
				"instructor": s["instructor"] or None,
				"schedule_date": s["date"],
				"from_time": s["from_time"],
				"to_time": s["to_time"],
				"venue": s["venue"],
				"repeat_frequency": "Never",
				"parent_schedule": roots.get(key),
			})
			doc.flags.allow_non_teaching_day = bool(s["holiday"])
			doc.insert()
			if key not in roots:
				roots[key] = doc.name
				series[doc.name] = frappe._dict(class_name=s["class_name"], first=s["date"], last=s["date"], count=0, slot=s)
			info = series[roots[key]]
			info.last, info.count = s["date"], info.count + 1
			publish_bulk_progress(_("Creating Time Table"), i, total)

	# Root carries the series' repeat settings, set after the fact so its own
	# after_insert doesn't generate a second copy of the occurrences. Repeats
	# Till is the last session actually created, so it stays inside the term.
	for root, info in series.items():
		if args.repeat != "Never" and info.count > 1:
			frappe.db.set_value(
				"Time Table", root, {"repeat_frequency": args.repeat, "repeats_till": info.last}, update_modified=False
			)
		slot = info.slot
		add_log(
			info.class_name, "Created", root, info.first,
			f"Bulk: {info.count} session(s), {args.repeat if info.count > 1 else 'Once'}, "
			f"{format_time_12h(slot['from_time'])} – {format_time_12h(slot['to_time'])}, {slot['venue']}"
			+ (f", {formatdate(info.first)} to {formatdate(info.last)}" if info.count > 1 else ""),
		)

	summary = plan["summary"]
	return {
		"created": total,
		"skipped": summary["skipped"],
		"warnings": summary["warnings"],
		"series": len(series),
		"classes": sorted({s["class_name"] for s in to_create}),
	}


def _parse_args(args):
	if isinstance(args, str):
		args = json.loads(args)
	args = frappe._dict(args or {})

	if not frappe.has_permission("Time Table", "create"):
		frappe.throw(_("You are not permitted to create Time Table entries."), frappe.PermissionError)

	args.repeat = args.repeat or "Never"
	if args.repeat not in REPEATS:
		frappe.throw(_("Invalid Repeat option {0}.").format(args.repeat))
	if not args.start_date:
		frappe.throw(_("Select the Start Date."))
	args.start_date = getdate(args.start_date)
	if args.repeat == "Never":
		args.repeats_till = args.start_date
	else:
		if not args.repeats_till:
			frappe.throw(_("Select the Repeats Till date."))
		args.repeats_till = getdate(args.repeats_till)
		if args.repeats_till < args.start_date:
			frappe.throw(_("Repeats Till cannot be before the Start Date."))
		if (args.repeats_till - args.start_date).days > 366:
			frappe.throw(_("Repeats Till must be within a year of the Start Date."))

	args.venue_per_day = cint(args.venue_per_day)
	args.skip_holidays = cint(args.skip_holidays)
	args.skip_exams = cint(args.skip_exams)
	args.skip_others = cint(args.skip_others)

	# Time slots: [{day, from_time, to_time, venue}]. A day may have several
	# (e.g. a morning and an afternoon session); day is only used when weekly.
	slots = []
	for d in args.slots or []:
		d = frappe._dict(d)
		if args.repeat == "Weekly":
			if d.day not in WEEKDAYS:
				frappe.throw(_("Invalid weekday {0}.").format(d.day))
		else:
			d.day = None
		slots.append(frappe._dict(day=d.day, from_time=d.from_time, to_time=d.to_time, venue=d.venue if args.venue_per_day else None))
	if not slots:
		frappe.throw(_("Select at least one day of the week.") if args.repeat == "Weekly" else _("Add at least one time slot."))

	by_day = {}
	for slot in slots:
		label = _(slot.day) if slot.day else _("the session")
		if not (slot.from_time and slot.to_time):
			frappe.throw(_("Set the Start and End time for {0}.").format(label))
		slot.from_time, slot.to_time = _normalise_time(slot.from_time), _normalise_time(slot.to_time)
		if to_timedelta(slot.from_time) >= to_timedelta(slot.to_time):
			frappe.throw(_("End time must be after Start time for {0}.").format(label))
		if args.venue_per_day and not slot.venue:
			frappe.throw(_("Select the Venue for {0} ({1} – {2}).").format(label, format_time_12h(slot.from_time), format_time_12h(slot.to_time)))
		for other in by_day.get(slot.day, []):
			if _overlaps(slot.from_time, slot.to_time, other.from_time, other.to_time):
				frappe.throw(_("Time slots {0} – {1} and {2} – {3} on {4} overlap.").format(
					format_time_12h(other.from_time), format_time_12h(other.to_time),
					format_time_12h(slot.from_time), format_time_12h(slot.to_time), label,
				))
		by_day.setdefault(slot.day, []).append(slot)
	args.slots = sorted(slots, key=lambda x: (WEEKDAYS.index(x.day) if x.day else 0, x.from_time))

	# Classes, each with its own faculty and venue
	rows, seen = [], set()
	for r in args.classes or []:
		r = frappe._dict(r)
		if not r.class_name or r.class_name in seen:
			continue
		seen.add(r.class_name)
		rows.append(r)
	if not rows:
		frappe.throw(_("Add at least one Class."))
	if args.venue_per_day and len(rows) > 1:
		frappe.throw(_("A different venue per slot can only be used when scheduling a single Class."))

	readable = set(frappe.get_list("Classes", filters={"name": ["in", list(seen)]}, pluck="name"))
	missing = [r.class_name for r in rows if r.class_name not in readable]
	if missing:
		frappe.throw(_("Class(es) not found or not permitted: {0}").format(", ".join(missing)))
	for r in rows:
		if not args.venue_per_day and not r.venue:
			frappe.throw(_("Select the Venue for Class {0}.").format(r.class_name))
	args.classes = rows
	return args


def _normalise_time(value):
	td = to_timedelta(value)
	total = int(td.total_seconds())
	return f"{total // 3600:02d}:{total % 3600 // 60:02d}:00"


def _overlaps(start1, end1, start2, end2):
	return to_timedelta(start1) < to_timedelta(end2) and to_timedelta(end1) > to_timedelta(start2)


def _dates_for(args, slot):
	"""Candidate dates of one slot, before any skip rule."""
	start, end = args.start_date, args.repeats_till
	if args.repeat == "Never":
		return [start]
	if args.repeat == "Daily":
		# Sundays are never teaching days; leave them out rather than list each as skipped
		days = (start + timedelta(days=i) for i in range((end - start).days + 1))
		return [d for d in days if not (args.skip_holidays and d.strftime("%A") in DEFAULT_WEEKLY_OFF_DAYS)]
	if args.repeat == "Monthly":
		out, n = [], 0
		while True:
			day = start + relativedelta(months=n)
			if day > end:
				return out
			out.append(day)
			n += 1
	# Weekly: every matching weekday in the range
	target = WEEKDAYS.index(slot.day)
	first = start + timedelta(days=(target - start.weekday()) % 7)
	return [first + timedelta(weeks=i) for i in range((end - first).days // 7 + 1)] if first <= end else []


def build_plan(args):
	from slcm.slcm.doctype.institutional_calendar.institutional_calendar import (
		get_calendar_entries,
		get_non_teaching_dates_in_range,
	)
	from slcm.slcm.utils.exam_timetable import get_exam_bookings

	start, end = args.start_date, args.repeats_till
	class_names = [r.class_name for r in args.classes]

	class_info = {
		c.name: c
		for c in frappe.get_all(
			"Classes",
			filters={"name": ["in", class_names]},
			fields=["name", "course", "course_name", "section", "group_name", "faculty", "academic_term"],
		)
	}
	terms = {
		t.name: t
		for t in frappe.get_all(
			"Academic Term",
			filters={"name": ["in", list({c.academic_term for c in class_info.values() if c.academic_term})]},
			fields=["name", "term_start_date", "term_end_date"],
		)
	}

	# Faculty is autoname: autoincrement, so names come back as ints - compare as strings
	for r in args.classes:
		r.instructor = str(r.instructor or class_info[r.class_name].faculty or "")
	faculty_ids = list({r.instructor for r in args.classes} - {""})
	faculty_names = {
		str(f.name): " ".join(filter(None, [f.first_name, f.last_name])) or str(f.name)
		for f in frappe.get_all("Faculty", filters={"name": ["in", faculty_ids]}, fields=["name", "first_name", "last_name"])
	} if faculty_ids else {}

	venues = list({r.venue for r in args.classes if r.venue} | {s.venue for s in args.slots if s.venue})
	inactive = set(frappe.get_all("Venue Master", filters={"name": ["in", venues], "is_active": 0}, pluck="name")) if venues else set()
	unknown = set(venues) - set(frappe.get_all("Venue Master", filters={"name": ["in", venues]}, pluck="name")) if venues else set()
	if unknown:
		frappe.throw(_("Venue(s) not found: {0}").format(", ".join(sorted(unknown))))

	# Everything already booked in the range, fetched once
	non_teaching = get_non_teaching_dates_in_range(start, end)
	calendar_skip = {}
	skip_types = (EXAM_ENTRY_TYPES if args.skip_exams else ()) + (OTHER_ENTRY_TYPES if args.skip_others else ())
	if skip_types:
		for entry in get_calendar_entries(start, end):
			if entry.entry_type not in skip_types:
				continue
			day = max(getdate(entry.start_date), start)
			while day <= min(getdate(entry.end_date), end):
				calendar_skip.setdefault(day, f"{entry.entry_type}: {entry.name1}")
				day += timedelta(days=1)

	existing = frappe.get_all(
		"Time Table",
		filters={"schedule_date": ["between", [start, end]], "docstatus": ["<", 2], "is_cancelled": 0},
		or_filters={"class_name": ["in", class_names], "venue": ["in", venues or [""]], "instructor": ["in", faculty_ids or [""]]},
		fields=["name", "class_name", "venue", "instructor", "schedule_date", "from_time", "to_time", "course"],
	)
	by_class, by_venue, by_faculty = {}, {}, {}
	for row in existing:
		day = getdate(row.schedule_date)
		by_class.setdefault((row.class_name, day), []).append(row)
		by_venue.setdefault((row.venue, day), []).append(row)
		if row.instructor:
			by_faculty.setdefault((str(row.instructor), day), []).append(row)
	for exam in get_exam_bookings(None, start, end):
		if exam.venue in venues:
			by_venue.setdefault((exam.venue, getdate(exam.exam_date)), []).append(frappe._dict(
				name=exam.exam_plan, from_time=exam.start_time, to_time=exam.end_time, course=f"Exam · {exam.course}"
			))

	sessions, class_rows = [], []
	batch_venue, batch_faculty = {}, {}
	for r in args.classes:
		cls = class_info[r.class_name]
		instructor = r.instructor
		term = terms.get(cls.academic_term)
		counts = frappe._dict(ok=0, warning=0, skipped=0)
		for slot in args.slots:
			venue = slot.venue or r.venue
			if venue in inactive:
				frappe.throw(_("Venue {0} is inactive.").format(venue))
			for day in _dates_for(args, slot):
				status, reason, notes = OK, "", []
				ft, tt = slot.from_time, slot.to_time
				holiday = non_teaching.get(day)
				if term and term.term_start_date and term.term_end_date and not (
					getdate(term.term_start_date) <= day <= getdate(term.term_end_date)
				):
					status, reason = SKIPPED, _("Outside {0} ({1} – {2})").format(
						cls.academic_term, formatdate(term.term_start_date), formatdate(term.term_end_date)
					)
				elif holiday and args.skip_holidays:
					status, reason = SKIPPED, holiday
				elif day in calendar_skip:
					status, reason = SKIPPED, calendar_skip[day]
				else:
					clash = next((c for c in by_class.get((r.class_name, day), []) if _overlaps(ft, tt, c.from_time, c.to_time)), None)
					if clash:
						status, reason = SKIPPED, _("Class already scheduled {0} – {1} ({2})").format(
							format_time_12h(clash.from_time), format_time_12h(clash.to_time), clash.name
						)
				if status == OK:
					clash = next((c for c in by_venue.get((venue, day), []) if _overlaps(ft, tt, c.from_time, c.to_time)), None)
					if clash:
						status, reason = SKIPPED, _("{0} booked for {1} ({2} – {3})").format(
							venue, clash.course, format_time_12h(clash.from_time), format_time_12h(clash.to_time)
						)
					else:
						clash = next((c for c in batch_venue.get((venue, day), []) if _overlaps(ft, tt, c["from_time"], c["to_time"])), None)
						if clash:
							status, reason = SKIPPED, _("{0} already used by {1} in this run").format(venue, clash["class_name"])
				if status == OK and instructor:
					busy = next((c for c in by_faculty.get((instructor, day), []) if _overlaps(ft, tt, c.from_time, c.to_time)), None)
					busy = busy or next(
						(frappe._dict(course=c["course"]) for c in batch_faculty.get((instructor, day), []) if _overlaps(ft, tt, c["from_time"], c["to_time"])),
						None,
					)
					if busy:
						notes.append(_("Faculty also teaching {0} at this time").format(busy.course))
				if status == OK and holiday:
					notes.append(_("On a non-teaching day: {0}").format(holiday))
				if status == OK and notes:
					status, reason = WARNING, "; ".join(notes)

				s = {
					"class_name": r.class_name,
					"course": cls.course_name or cls.course,
					"group": cls.section or cls.group_name or "",
					"instructor": instructor or "",
					"faculty_name": faculty_names.get(instructor, instructor or ""),
					"venue": venue,
					"date": str(day),
					"weekday": day.strftime("%A"),
					"from_time": ft,
					"to_time": tt,
					"series": f"{slot.day or 'all'}|{ft}",
					"holiday": 1 if holiday else 0,
					"status": status,
					"reason": reason,
				}
				sessions.append(s)
				counts[status] += 1
				if status != SKIPPED:
					batch_venue.setdefault((venue, day), []).append(s)
					if instructor:
						batch_faculty.setdefault((instructor, day), []).append(s)
		class_rows.append({
			"class_name": r.class_name,
			"course": cls.course_name or cls.course,
			"group": cls.section or cls.group_name or "",
			"faculty_name": faculty_names.get(instructor, instructor or ""),
			"venue": ", ".join(sorted({s.venue or r.venue for s in args.slots})),
			"create": counts.ok + counts.warning,
			"warnings": counts.warning,
			"skipped": counts.skipped,
		})

	sessions.sort(key=lambda s: (s["date"], s["from_time"], s["class_name"]))
	summary = {
		"create": sum(1 for s in sessions if s["status"] != SKIPPED),
		"warnings": sum(1 for s in sessions if s["status"] == WARNING),
		"skipped": sum(1 for s in sessions if s["status"] == SKIPPED),
		"classes": len(class_rows),
		"start_date": str(start),
		"end_date": str(end),
		"repeat": args.repeat,
		"slots": [
			{"day": s.day, "from_time": s.from_time, "to_time": s.to_time, "venue": s.venue} for s in args.slots
		],
		"max_sessions": MAX_SESSIONS,
	}
	return {"summary": summary, "classes": class_rows, "sessions": sessions}

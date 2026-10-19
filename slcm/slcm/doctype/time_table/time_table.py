# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _

def format_time_12h(time_obj):
    import datetime
    if isinstance(time_obj, str):
        # if it's string HH:MM:SS
        parts = time_obj.split(":")
        if len(parts) >= 2:
            time_obj = datetime.timedelta(hours=int(parts[0]), minutes=int(parts[1]), seconds=int(parts[2]) if len(parts)>2 else 0)
    
    if isinstance(time_obj, datetime.timedelta):
        total_seconds = int(time_obj.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        am_pm = "AM" if hours < 12 else "PM"
        hours_12 = hours % 12
        if hours_12 == 0:
            hours_12 = 12
            
        return f"{hours_12:02d}:{minutes:02d} {am_pm}"
    return str(time_obj)

from frappe.model.document import Document
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


from frappe.utils import to_timedelta
from contextlib import contextmanager


@contextmanager
def quiet_bulk_operation():
    """Mute the per-record messages (Attendance Session updates, Google
    Calendar's own 'Event Synced with Google Calendar.' msgprint) while many
    Time Table rows are written in one request, and count what happened so
    the caller can show a single summary instead of a toast per record."""
    prev_mute, prev_stats = frappe.flags.mute_messages, frappe.flags.tt_bulk_stats
    stats = prev_stats or frappe._dict(sessions_created=0, sessions_updated=0, gcal_synced=0, gcal_failed=0)
    frappe.flags.mute_messages = True
    frappe.flags.tt_bulk_stats = stats
    try:
        yield stats
    finally:
        frappe.flags.mute_messages = prev_mute
        frappe.flags.tt_bulk_stats = prev_stats


def bump_bulk_stat(key):
    stats = frappe.flags.tt_bulk_stats
    if stats is not None:
        stats[key] += 1


def publish_bulk_progress(label, done, total):
    """Pushed while the save request is still running - time_table.js renders
    it into the freeze overlay as '<label>... NN%'."""
    frappe.publish_realtime(
        "time_table_bulk_progress",
        {"label": label, "done": done, "total": total, "percent": int(done * 100 / total) if total else 100},
        user=frappe.session.user,
    )


class TimeTable(Document):
    def validate(self):
        """Validate the Time Table entry"""
        self.validate_time()
        self.validate_repeat_settings()
        self.validate_office_hours_group()
        self.validate_class_participation_weeks()
        self.check_holiday_conflict()
        self.check_conflicts()
        self.check_venue_conflict()
        self.calculate_duration()

    def check_holiday_conflict(self):
        """Block scheduling a class on a date that Institutional Calendar marks
        as a Holiday or a configured Weekly Off day (e.g. Sunday)."""
        if not self.schedule_date:
            return

        from slcm.slcm.doctype.institutional_calendar.institutional_calendar import (
            get_non_teaching_reason,
        )

        non_teaching = get_non_teaching_reason(self.schedule_date)
        if non_teaching:
            frappe.throw(
                f"Cannot schedule a class on {self.schedule_date} — it is marked as "
                f"{non_teaching['reason']} ({non_teaching['name1']}) in the Institutional Calendar.",
                title="Non-Teaching Day",
            )

    def on_update(self):
        """Update the corresponding Attendance Session when the Time Table entry is updated"""
        # On insert, after_insert has just created the session from these same
        # values - re-saving it would only add a redundant "updated" toast.
        if self.flags.in_insert:
            return
        self.update_attendance_session()

    def validate_time(self):
        """Validate that to_time is after from_time"""
        if self.from_time and self.to_time:
            if to_timedelta(self.from_time) >= to_timedelta(self.to_time):
                frappe.throw("To Time must be after From Time")

    def calculate_duration(self):
        """Keep duration_hours in sync with from_time/to_time (it's a plain
        read-only field with no fetch_from, so nothing else sets it)."""
        if self.from_time and self.to_time:
            duration_seconds = (to_timedelta(self.to_time) - to_timedelta(self.from_time)).total_seconds()
            hours, remainder = divmod(duration_seconds, 3600); self.duration_hours = hours + ((remainder // 60) / 100.0)

    def validate_repeat_settings(self):
        """Validate repeat frequency and repeats_till"""
        if self.repeat_frequency and self.repeat_frequency != "Never":
            if not self.repeats_till:
                frappe.throw("Please specify 'Repeats Till' date for recurring schedules")
            if self.repeats_till < self.schedule_date:
                frappe.throw("Repeats Till date cannot be before Schedule Date")

    def validate_office_hours_group(self):
        """Office Hours Group links to Student Group - only Office Hours groups
        are allowed (the client-side link filter isn't enforced on the server)."""
        if self.based_on != "Office Hours" or not self.office_hours_group:
            return

        group_based_on = frappe.db.get_value("Student Group", self.office_hours_group, "group_based_on")
        if group_based_on != "Office Hours":
            frappe.throw(
                _("Office Hours Group {0} is not an Office Hours group.").format(frappe.bold(self.office_hours_group)),
                title=_("Invalid Office Hours Group"),
            )

    def get_schedule_range(self):
        """Date range covered by this schedule's series. Generated occurrences
        (parent_schedule set) are copied with repeat 'Never' and their own single
        date, so they are checked against the series root's range instead."""
        from frappe.utils import getdate

        schedule_date, repeat_frequency, repeats_till = self.schedule_date, self.repeat_frequency, self.repeats_till
        if self.parent_schedule:
            root = frappe.db.get_value(
                "Time Table",
                self.parent_schedule,
                ["schedule_date", "repeat_frequency", "repeats_till"],
                as_dict=True,
            )
            if root:
                schedule_date, repeat_frequency, repeats_till = root.schedule_date, root.repeat_frequency, root.repeats_till

        start = getdate(schedule_date)
        end = getdate(repeats_till) if repeat_frequency and repeat_frequency != "Never" and repeats_till else start
        return start, end

    def validate_class_participation_weeks(self):
        """Class Participation Week Group: only Class-Participation groups, no
        duplicate weeks or overlapping date ranges, and every week must fall
        within Schedule Date .. Repeats Till (or on Schedule Date when Repeat
        is 'Never')."""
        from frappe.utils import formatdate, getdate

        rows = self.get("class_participation_week_group") or []
        if not rows or not self.schedule_date:
            return

        range_start, range_end = self.get_schedule_range()

        week_names = list({row.week for row in rows if row.week})
        group_type_by_week = dict(
            frappe.get_all(
                "Student Group",
                filters={"name": ["in", week_names]},
                fields=["name", "group_based_on"],
                as_list=True,
            )
        ) if week_names else {}

        seen_weeks = {}
        checked_rows = []
        for row in rows:
            if not (row.week and row.start_date and row.end_date):
                continue

            if group_type_by_week.get(row.week) != "Class-Participation":
                frappe.throw(
                    _("Row #{0}: Week {1} is not a Class-Participation group.").format(row.idx, frappe.bold(row.week)),
                    title=_("Invalid Week"),
                )

            if row.week in seen_weeks:
                frappe.throw(
                    _("Row #{0}: Week {1} is already added in row #{2}.").format(
                        row.idx, frappe.bold(row.week), seen_weeks[row.week]
                    ),
                    title=_("Duplicate Week"),
                )
            seen_weeks[row.week] = row.idx

            start, end = getdate(row.start_date), getdate(row.end_date)
            if start > end:
                frappe.throw(
                    _("Row #{0}: Start Date cannot be after End Date.").format(row.idx),
                    title=_("Invalid Week Dates"),
                )

            if start < range_start or end > range_end:
                if range_start == range_end:
                    msg = _("Row #{0}: Week dates must be on the Schedule Date {1} since Repeat is 'Never'.").format(
                        row.idx, formatdate(range_start)
                    )
                else:
                    msg = _("Row #{0}: Week dates ({1} - {2}) must be within Schedule Date {3} and Repeats Till {4}.").format(
                        row.idx, formatdate(start), formatdate(end), formatdate(range_start), formatdate(range_end)
                    )
                frappe.throw(msg, title=_("Week Out of Range"))

            for other_idx, other_start, other_end in checked_rows:
                if start <= other_end and end >= other_start:
                    frappe.throw(
                        _("Row #{0}: Week dates ({1} - {2}) overlap with row #{3} ({4} - {5}).").format(
                            row.idx, formatdate(start), formatdate(end),
                            other_idx, formatdate(other_start), formatdate(other_end),
                        ),
                        title=_("Duplicate Week Dates"),
                    )
            checked_rows.append((row.idx, start, end))

    def check_conflicts(self):
        """Check for scheduling conflicts"""
        if not self.schedule_date or not self.from_time or not self.to_time:
            return

        # 1. Check for Duplicate Time Table entry (Same Course Offering, Same Venue,
        # Same Title/Section, Same Date, Overlapping Time). Venue is required and
        # Title carries the section identifier (e.g. "BLM101-Legal Methods-A"), so
        # parallel sections of the same Course Offering meeting at the same time in
        # different venues/sections are a legitimate schedule, not a duplicate — the
        # venue itself is separately protected by check_venue_conflict().
        if self.course_offering:
            filters = {
                "name": ["!=", self.name],
                "course_offering": self.course_offering,
                "schedule_date": self.schedule_date,
                "venue": self.venue,
                "title": self.title,
                "docstatus": ["<", 2] # Exclude cancelled
            }

            conflicts = frappe.get_all(
                "Time Table",
                filters=filters,
                fields=["name", "from_time", "to_time", "course", "course_offering"],
            )

            for conflict in conflicts:
                if self.times_overlap(self.from_time, self.to_time, conflict.from_time, conflict.to_time):
                    frappe.throw(
                        f"Already scheduled same time class {conflict.course} for this Course Offering ({conflict.from_time} - {conflict.to_time})",
                        title="Duplicate Schedule"
                    )

        # 2. Check Instructor Conflict
        if self.instructor:
            conflicts = frappe.get_all(
                "Time Table",
                filters={
                    "name": ["!=", self.name],
                    "instructor": self.instructor,
                    "schedule_date": self.schedule_date,
                    "docstatus": ["<", 2]
                },
                fields=["name", "from_time", "to_time", "course"],
            )

            for conflict in conflicts:
                if self.times_overlap(self.from_time, self.to_time, conflict.from_time, conflict.to_time):
                    frappe.msgprint(
                        f"Warning: Instructor {self.instructor} has another class ({conflict.course}) "
                        f"from {conflict.from_time} to {conflict.to_time} on {self.schedule_date}",
                        indicator="orange",
                        alert=True,
                    )

    def check_venue_conflict(self):
        """Block double-booking a Venue Master for overlapping times on the
        same date. Venue used to be a Link to Venue Booking, which had its own
        availability check; now that venue links directly to Venue Master
        (which has no such check of its own), Time Table must guard against
        double-booking itself."""
        if not self.schedule_date or not self.from_time or not self.to_time or not self.venue:
            return

        conflicts = frappe.get_all(
            "Time Table",
            filters={
                "name": ["!=", self.name],
                "venue": self.venue,
                "schedule_date": self.schedule_date,
                "docstatus": ["<", 2],
            },
            fields=["name", "from_time", "to_time", "course"],
        )

        for conflict in conflicts:
            if self.times_overlap(self.from_time, self.to_time, conflict.from_time, conflict.to_time):
                frappe.throw(
                    _("Venue {0} is already booked for {1} from {2} to {3} on {4}.").format(
                        self.venue, conflict.course, conflict.from_time, conflict.to_time, self.schedule_date
                    ),
                    title=_("Venue Conflict"),
                )

    def times_overlap(self, start1, end1, start2, end2):
        """Check if two time ranges overlap"""
        return to_timedelta(start1) < to_timedelta(end2) and to_timedelta(end1) > to_timedelta(start2)

    def after_insert(self):
        """Create recurring schedules if repeat is enabled"""
        if self.repeat_frequency and self.repeat_frequency != "Never":
            self.create_recurring_schedules()
        
        # Create attendance session for this schedule
        self.create_attendance_session()

    def get_session_office_hours_group(self):
        """Office Hours Group (a Student Group) to carry onto the Attendance Session."""
        if self.based_on != "Office Hours":
            return None
        return self.office_hours_group

    def create_attendance_session(self):
        """Create an attendance session for this schedule"""
        from frappe.utils import getdate

        if not self.schedule_date or not self.from_time or not self.to_time:
            return

        # Check if session already exists
        exists = frappe.db.exists("Attendance Session", {
            "class_schedule": self.name,
            "session_date": self.schedule_date,
            "session_start_time": self.from_time
        })

        if exists:
            return

        based_on = self.based_on or "Time Table"

        doc = frappe.get_doc({
            "doctype": "Attendance Session",
            "based_on": based_on,
            "class_schedule": self.name,
            "course_schedule": self.course_schedule if based_on == "Course Schedule" else None,
            "office_hours_group": self.get_session_office_hours_group(),
            "course_offering": self.course_offering,
            "course": self.course,
            "instructor": self.instructor,
            "session_date": self.schedule_date,
            "session_start_time": self.from_time,
            "session_end_time": self.to_time,
            "session_type": "Office Hour" if based_on == "Office Hours" else "Lecture",
            "session_status": "Scheduled"
        })
        # NOTE: Student Attendance records are intentionally NOT created here.
        # The session's roster is shown live (computed from Student Enrollment)
        # by update_attendance_summary() — real Student Attendance documents
        # only get created when attendance is actually taken (manual mark,
        # bulk mark, or RFID swipe).
        doc.insert(ignore_permissions=True)
        bump_bulk_stat("sessions_created")

    def update_attendance_session(self):
        """Update the corresponding Attendance Session when the Time Table entry is updated"""
        frappe.logger().info(f"update_attendance_session called for {self.name}")
        
        if not self.schedule_date or not self.from_time or not self.to_time:
            frappe.logger().info(f"Missing required fields: schedule_date={self.schedule_date}, from_time={self.from_time}, to_time={self.to_time}")
            return

        # Find the Attendance Session linked to this Time Table entry
        session_name = frappe.db.get_value("Attendance Session", {
            "class_schedule": self.name
        })

        if not session_name:
            frappe.logger().info(f"No Attendance Session found for Time Table entry {self.name}")
            frappe.msgprint(
                f"No Attendance Session found for this Time Table entry. "
                "Please create an Attendance Session first.",
                indicator="orange",
                alert=True
            )
            return

        frappe.logger().info(f"Found Attendance Session: {session_name}")

        # Get the Attendance Session document
        session = frappe.get_doc("Attendance Session", session_name)

        # Only update if attendance hasn't been marked yet
        # This prevents overwriting attendance data
        if session.attendance_marked:
            frappe.msgprint(
                f"Attendance has already been marked for session {session_name}. "
                "Changes to Time Table will not update the session.",
                indicator="orange",
                alert=True
            )
            return

        # Calculate duration in hours
        duration_hours = 0
        if self.from_time and self.to_time:
            from_delta = to_timedelta(self.from_time)
            to_delta = to_timedelta(self.to_time)
            duration_seconds = (to_delta - from_delta).total_seconds()
            hours, remainder = divmod(duration_seconds, 3600); duration_hours = hours + ((remainder // 60) / 100.0)

        frappe.logger().info(f"Updating session {session_name}: from {self.from_time} to {self.to_time}, duration={duration_hours}")

        based_on = self.based_on or "Time Table"

        # Update the session fields
        session.session_date = self.schedule_date
        session.session_start_time = str(self.from_time) if self.from_time else None
        session.session_end_time = str(self.to_time) if self.to_time else None
        session.duration_hours = round(duration_hours, 2)
        session.instructor = self.instructor
        session.course = self.course
        session.course_offering = self.course_offering
        session.based_on = based_on
        session.course_schedule = self.course_schedule if based_on == "Course Schedule" else None
        session.office_hours_group = self.get_session_office_hours_group()

        # Save the session
        session.save(ignore_permissions=True)
        bump_bulk_stat("sessions_updated")

        frappe.msgprint(
            f"Attendance Session {session_name} has been updated successfully.",
            indicator="green",
            alert=True
        )



    def create_recurring_schedules(self):
        """Create recurring class schedules based on repeat frequency"""
        if not self.repeats_till:
            return
        
        # Prevent duplicate creation if this method is called multiple times
        if frappe.db.exists("Time Table", {"parent_schedule": self.name}):
            return

        try:
            current_date = datetime.strptime(str(self.schedule_date), "%Y-%m-%d")
            end_date = datetime.strptime(str(self.repeats_till), "%Y-%m-%d")

            # Determine increment based on frequency
            if self.repeat_frequency == "Daily":
                increment = timedelta(days=1)
            elif self.repeat_frequency == "Weekly":
                increment = timedelta(weeks=1)
            elif self.repeat_frequency == "Monthly":
                increment = relativedelta(months=1)
            else:
                return

            # Create schedules
            current_date += increment  # Skip the first date (already created)
            created_count = 0
            conflict_count = 0
            holiday_skip_count = 0
            schedules_to_create = []

            from frappe.utils import getdate

            from slcm.slcm.doctype.institutional_calendar.institutional_calendar import (
                get_non_teaching_dates_in_range,
            )

            # Batch-fetch non-teaching dates and instructor's existing schedules for the
            # whole range up front instead of querying per iteration — a semester-long
            # Daily repeat would otherwise issue 500+ queries in a single request.
            non_teaching_dates = get_non_teaching_dates_in_range(current_date.date(), end_date.date())

            existing_by_date = {}
            if self.instructor:
                existing = frappe.get_all(
                    "Time Table",
                    filters={
                        "name": ["!=", self.name],
                        "instructor": self.instructor,
                        "schedule_date": ["between", [current_date.date(), end_date.date()]],
                        "docstatus": ["<", 2],
                    },
                    fields=["name", "schedule_date", "from_time", "to_time", "course"],
                )
                for row in existing:
                    existing_by_date.setdefault(getdate(row.schedule_date), []).append(row)

            # Same batch pre-check for venue double-booking as above for the
            # instructor, so a venue clash on one date in the range is skipped
            # up front instead of blowing up mid-loop via check_venue_conflict()
            # inside new_schedule.insert() below.
            venue_conflicts_by_date = {}
            if self.venue:
                venue_existing = frappe.get_all(
                    "Time Table",
                    filters={
                        "name": ["!=", self.name],
                        "venue": self.venue,
                        "schedule_date": ["between", [current_date.date(), end_date.date()]],
                        "docstatus": ["<", 2],
                    },
                    fields=["name", "schedule_date", "from_time", "to_time", "course"],
                )
                for row in venue_existing:
                    venue_conflicts_by_date.setdefault(getdate(row.schedule_date), []).append(row)

            # First, collect all schedules to create and check for conflicts
            while current_date <= end_date:
                date_only = current_date.date()

                # Skip dates marked as a Holiday or Weekly Off (e.g. Sunday) in the Institutional Calendar
                if date_only in non_teaching_dates:
                    holiday_skip_count += 1
                    current_date += increment
                    continue

                # Check for conflicts on this date
                has_conflict = False
                for conflict in existing_by_date.get(date_only, []):
                    if self.times_overlap(
                        self.from_time, self.to_time, conflict.from_time, conflict.to_time
                    ):
                        has_conflict = True
                        conflict_count += 1
                        frappe.logger().warning(
                            f"Skipping schedule on {date_only} due to conflict with {conflict.name}"
                        )
                        break

                if not has_conflict:
                    for conflict in venue_conflicts_by_date.get(date_only, []):
                        if self.times_overlap(
                            self.from_time, self.to_time, conflict.from_time, conflict.to_time
                        ):
                            has_conflict = True
                            conflict_count += 1
                            frappe.logger().warning(
                                f"Skipping schedule on {date_only} due to venue conflict with {conflict.name}"
                            )
                            break

                if not has_conflict:
                    schedules_to_create.append(current_date.strftime("%Y-%m-%d"))

                # Increment based on frequency
                current_date += increment

            # Now create all schedules in a transaction. Each insert creates an
            # Attendance Session and pushes a Google Calendar event, which would
            # otherwise each raise their own toast - collect them into one summary.
            total = len(schedules_to_create)
            with quiet_bulk_operation() as stats:
                publish_bulk_progress("Scheduling", 0, total)
                for schedule_date in schedules_to_create:
                    new_schedule = frappe.copy_doc(self)
                    new_schedule.schedule_date = schedule_date
                    new_schedule.parent_schedule = self.name
                    new_schedule.repeat_frequency = "Never"  # Don't repeat the child schedules
                    new_schedule.repeats_till = None
                    new_schedule.insert(ignore_permissions=True)
                    created_count += 1
                    publish_bulk_progress("Scheduling", created_count, total)

            self.show_scheduling_summary(created_count, conflict_count, holiday_skip_count, stats)
        except Exception as e:
            frappe.log_error(message=f"Error creating recurring schedules: {str(e)}", title="Recurring Schedule Creation Error")
            frappe.throw(f"Error creating recurring schedules: {str(e)}")

    def show_scheduling_summary(self, created_count, conflict_count, holiday_skip_count, stats):
        """One summary dialog for the whole recurring series, replacing the
        per-occurrence 'Attendance Session updated' / 'Event Synced' toasts."""
        from slcm.slcm.doctype.time_table.google_calendar_sync import get_active_google_calendar_account

        # The rest of this request (this schedule's own Google Calendar push)
        # shouldn't add its own toast on top of the summary.
        frappe.flags.tt_summary_shown = True

        if not created_count:
            frappe.msgprint(
                _("Could not create recurring schedules. All dates were skipped ({0} conflicts, {1} holidays).").format(
                    conflict_count, holiday_skip_count
                ),
                title=_("Scheduling Summary"),
                indicator="red",
            )
            return

        lines = [_("Recurring occurrences created: <b>{0}</b> (plus this schedule)").format(created_count)]
        if holiday_skip_count:
            lines.append(_("Skipped due to holidays: <b>{0}</b>").format(holiday_skip_count))
        if conflict_count:
            lines.append(_("Skipped due to faculty/venue conflicts: <b>{0}</b>").format(conflict_count))
        lines.append(_("Attendance sessions created: <b>{0}</b>").format(stats.sessions_created))
        if get_active_google_calendar_account():
            lines.append(_("Synced with Google Calendar: <b>{0}</b>").format(stats.gcal_synced))
            if stats.gcal_failed:
                lines.append(
                    _("Google Calendar sync failed: <b>{0}</b> (see Error Log)").format(stats.gcal_failed)
                )

        frappe.msgprint(
            "<ul style='margin-bottom:0'>" + "".join(f"<li>{line}</li>" for line in lines) + "</ul>",
            title=_("Scheduling Summary"),
            indicator="orange" if (conflict_count or stats.gcal_failed) else "green",
        )


@frappe.whitelist()
def get_timetable_data(term=None, course=None, start_date=None, end_date=None):
    """Get timetable data for calendar view"""
    filters = {}

    if term:
        filters["term"] = term
    if course:
        filters["course"] = course
    if start_date and end_date:
        filters["schedule_date"] = ["between", [start_date, end_date]]
    
    schedules = frappe.get_all(
        "Time Table",
        filters=filters,
        fields=[
            "name",
            "title",
            "course",
            "instructor",
            "schedule_date",
            "from_time",
            "to_time",
            "venue",
            "color",
            "class_configuration",
        ],
        order_by="schedule_date, from_time",
    )

    # Format for calendar
    events = []
    for schedule in schedules:
        events.append({
            "id": schedule.name,
            "title": schedule.title or schedule.course,
            "start": f"{schedule.schedule_date}T{schedule.from_time}",
            "end": f"{schedule.schedule_date}T{schedule.to_time}",
            "backgroundColor": schedule.color or "#3498db",
            "extendedProps": {
                "course": schedule.course,
                "instructor": schedule.instructor,
                "venue": schedule.venue,
                "class_configuration": schedule.class_configuration,
            }
        })

    return events


@frappe.whitelist()
def create_time_table(data):
    """Create a class schedule from timetable configuration"""
    import json
    
    if isinstance(data, str):
        data = json.loads(data)
    
    # Create the schedule
    doc = frappe.get_doc({
        "doctype": "Time Table",
        "class_configuration": data.get("class_configuration"),
        "course": data.get("course"),
        "instructor": data.get("instructor"),
        "schedule_date": data.get("schedule_date"),
        "from_time": data.get("from_time"),
        "to_time": data.get("to_time"),
        "venue": data.get("venue"),
        "repeat_frequency": data.get("repeat_frequency", "Never"),
        "repeats_till": data.get("repeats_till"),
        "term": data.get("term"),
        "programme": data.get("programme"),
        "course_offering": data.get("course_offering"),
    })
    
    doc.insert(ignore_permissions=True)
    
    # If repeat is enabled, create recurring schedules
    if doc.repeat_frequency and doc.repeat_frequency != "Never":
        doc.create_recurring_schedules()
    
    return doc.name


@frappe.whitelist()
def get_events(start, end, filters=None):
    """
    Custom method to get events for FullCalendar.
    Handles the split date (schedule_date) and time (from_time, to_time) fields.
    """
    if not filters:
        filters = []
        
    import json
    if isinstance(filters, str):
        filters = json.loads(filters)

    # Base Query
    query = """
        SELECT
            name,
            class_configuration,
            course,
            instructor,
            schedule_date,
            from_time,
            to_time,
            duration_hours,
            venue,
            color,
            title,
            course_offering,
            based_on,
            course_schedule,
            office_hours_group
        FROM `tabTime Table`
        WHERE
            schedule_date BETWEEN %(start)s AND %(end)s
            AND docstatus < 2
    """
    
    # Add filters if present
    # This is a basic implementation. For complex standard filters, 
    # we might need frappe.get_list logic or get_event_conditions
    condition_values = {"start": start, "end": end}
    
    # Execute
    data = frappe.db.sql(query, condition_values, as_dict=True)

    # Bulk-resolve display-friendly names for instructor so the click
    # popover doesn't show raw IDs.
    instructor_names = {d.instructor for d in data if d.instructor}
    faculty_name_by_id = {}
    if instructor_names:
        faculty_name_by_id = {
            # Faculty uses numeric autonaming, so `name` comes back as an int here
            # while Time Table's `instructor` Link field stores it as a str — cast
            # to str so the lookup below actually matches instead of silently
            # falling back to the raw ID.
            str(f.name): " ".join(filter(None, [f.first_name, f.last_name]))
            for f in frappe.get_all(
                "Faculty", filters={"name": ["in", list(instructor_names)]}, fields=["name", "first_name", "last_name"]
            )
        }

    result = []
    for d in data:
        # Construct ISO datetime strings for FullCalendar
        start_dt = f"{d.schedule_date} {str(d.from_time).zfill(8)}"
        end_dt = f"{d.schedule_date} {str(d.to_time).zfill(8)}"

        instructor_label = faculty_name_by_id.get(d.instructor) or d.instructor

        title = d.title
        if not title:
            parts = [d.course, instructor_label]
            title = " - ".join([p for p in parts if p])
            if d.venue:
                title += f" ({d.venue})"

        result.append({
            "name": d.name,
            "id": d.name,
            "title": title,
            "start": start_dt,
            "end": end_dt,
            "color": d.color or "#3498db",
            "allDay": 0,
            "extendedProps": {
                "based_on": d.based_on,
                "course": d.course,
                "course_offering": d.course_offering,
                "course_schedule": d.course_schedule,
                "office_hours_group": d.office_hours_group,
                "instructor": instructor_label,
                "venue": d.venue,
                "from_time": str(d.from_time) if d.from_time else None,
                "to_time": str(d.to_time) if d.to_time else None,
                "duration_hours": d.duration_hours,
            }
        })

    result.extend(get_institutional_calendar_events(start, end))

    return result


def get_institutional_calendar_events(start, end):
    """Render Institutional Calendar entries (holidays, exams, events, ...)
    as solid, labeled all-day banners on the Time Table calendar view."""
    entries = frappe.db.sql(
        """
        SELECT name, name1, entry_type, start_date, end_date
        FROM `tabInstitutional Calendar`
        WHERE start_date <= %(end)s AND end_date >= %(start)s
        AND status != 'Inactive'
        AND docstatus < 2
        """,
        {"start": start, "end": end},
        as_dict=True,
    )

    entry_colors = {
        "Holiday": "#e74c3c",
        "Exam": "#9b59b6",
        "Semester Start": "#2ecc71",
        "Semester End": "#2ecc71",
        "Event": "#f39c12",
        "Orientation": "#1abc9c",
        "Other": "#95a5a6",
    }

    events = []
    for entry in entries:
        entry_color = entry_colors.get(entry.entry_type, "#95a5a6")
        events.append({
            "name": f"ic-{entry.name}",
            "id": f"ic-{entry.name}",
            "title": f"{entry.entry_type}: {entry.name1}",
            "start": str(entry.start_date),
            "end": str(entry.end_date + timedelta(days=1)),
            "allDay": 1,
            "editable": False,
            "color": entry_color,
            "backgroundColor": entry_color,
            "borderColor": entry_color,
            "textColor": "#ffffff",
            "extendedProps": {
                "institutional_calendar": entry.name,
                "entry_type": entry.entry_type,
            },
        })
    return events


@frappe.whitelist()
def get_future_occurrences(time_table_name):
    """Return this schedule and its sibling occurrences (same recurring series)
    dated today or later, for the 'apply to future occurrences' confirmation."""
    from frappe.utils import getdate, nowdate

    doc = frappe.get_doc("Time Table", time_table_name)
    series_root = doc.parent_schedule or doc.name

    # Series = the root itself plus every child pointing at it.
    series_names = [series_root] + [
        d.name
        for d in frappe.get_all("Time Table", filters={"parent_schedule": series_root}, fields=["name"])
    ]

    future = frappe.get_all(
        "Time Table",
        filters={
            "name": ["in", series_names],
            "schedule_date": [">=", nowdate()],
            "docstatus": ["<", 2],
        },
        fields=["name", "schedule_date", "venue", "from_time", "to_time"],
        order_by="schedule_date",
    )

    return {
        "count": len(future),
        "occurrences": future,
    }


@frappe.whitelist()
def find_sessions(programme=None, section=None, schedule_date=None):
    """List Time Table sessions, optionally narrowed by Programme, Section
    and/or Date (used by the list-view 'Update Venue / Time' dialog so it can
    be opened without pre-checking any row, and browsed/filtered from there).

    All filters are optional and Section in particular is often blank on real
    records (Time Table only fetches it from course_offering.section, and many
    rows only have class_configuration set, not course_offering) - filtering
    on it unconditionally would silently hide otherwise-matching sessions, so
    it's applied only when the caller actually provided a value.
    """
    filters = {"docstatus": ["<", 2]}
    if programme:
        filters["programme"] = programme
    if section:
        filters["section"] = section
    if schedule_date:
        filters["schedule_date"] = schedule_date

    sessions = frappe.get_all(
        "Time Table",
        filters=filters,
        # Only the columns the dialog's session table actually renders -
        # avoid pulling instructor/course_offering/etc. into the response
        # just because they exist on the doctype.
        fields=["name", "course", "programme", "section", "schedule_date", "from_time", "to_time", "venue"],
        order_by="schedule_date desc, from_time",
        limit_page_length=100,
    )

    # `course` is a plain Data field, not a Link - on rows where it was set
    # from a Course record it holds the Course's hashed `name` (e.g.
    # "dkmt49uui9") rather than a readable title, so resolve it to
    # course_name where possible. Rows where `course` was typed in directly
    # (no matching Course record) keep showing as-is.
    course_ids = {s.course for s in sessions if s.course}
    course_name_by_id = {}
    if course_ids:
        course_name_by_id = {
            c.name: c.course_name
            for c in frappe.get_all(
                "Course", filters={"name": ["in", list(course_ids)]}, fields=["name", "course_name"]
            )
        }
    for s in sessions:
        if s.course in course_name_by_id:
            s.course = course_name_by_id[s.course]

    return {"sessions": sessions}


@frappe.whitelist()
def get_sessions_roster(time_table_names):
    """Combined student roster across one or more Time Table sessions, shown
    for confirmation before applying a venue/time change to all of them.
    Resolved via each session's linked Class Configuration's own `students`
    child table rather than Student Enrollment by section, since Time Table's
    `section` field is frequently blank while `class_configuration` is
    reliably set. Multiple sessions sharing the same class_configuration
    (e.g. several dates of the same recurring class) are de-duplicated."""
    import json

    if isinstance(time_table_names, str):
        time_table_names = json.loads(time_table_names)
    time_table_names = list(dict.fromkeys(time_table_names))  # de-dupe, preserve order

    if not time_table_names:
        return {"students": []}

    class_configurations = {
        row.class_configuration
        for row in frappe.get_all(
            "Time Table",
            filters={"name": ["in", time_table_names]},
            fields=["class_configuration"],
        )
        if row.class_configuration
    }

    if not class_configurations:
        return {"students": []}

    students = frappe.get_all(
        "Class Student",
        filters={"parent": ["in", list(class_configurations)], "parenttype": "Class Configuration"},
        fields=["student", "student_name"],
        order_by="student_name",
    )

    # A student enrolled in more than one of the selected classes would
    # otherwise appear once per class - keep one row per student.
    seen = set()
    unique_students = []
    for s in students:
        if s.student in seen:
            continue
        seen.add(s.student)
        unique_students.append(s)

    return {"students": unique_students}


def _parse_updates(updates):
    import json

    if isinstance(updates, str):
        updates = json.loads(updates)

    allowed_fields = {"venue", "from_time", "to_time", "schedule_date", "instructor", "color", "title", "repeat_frequency", "repeats_till", "class_schedule_color"}
    updates = {k: v for k, v in updates.items() if k in allowed_fields}
    if not updates:
        frappe.throw(_("No updatable fields were provided."))
    return updates


def _apply_updates_to_rows(names, updates):
    if not names:
        frappe.throw(_("No occurrences were found to update."))

    # Pre-check conflicts to show a unified table error
    series_names = names
    conflicts = []
    
    for name in names:
        row_doc = frappe.get_doc("Time Table", name)
        for field, value in updates.items():
            row_doc.set(field, value)
            
        if row_doc.venue and row_doc.from_time and row_doc.to_time:
            overlaps = frappe.db.sql("""
                SELECT name, from_time, to_time, based_on, course 
                FROM `tabTime Table` 
                WHERE venue = %s AND schedule_date = %s AND docstatus < 2 AND name NOT IN %s
                AND (
                    (from_time < %s AND to_time > %s) OR
                    (from_time < %s AND to_time > %s) OR
                    (from_time >= %s AND to_time <= %s)
                )
            """, (row_doc.venue, row_doc.schedule_date, tuple(series_names) if series_names else ('',), 
                    row_doc.to_time, row_doc.from_time, 
                    row_doc.from_time, row_doc.to_time, 
                    row_doc.from_time, row_doc.to_time), as_dict=True)
            
            if overlaps:
                conflicts.append({
                    "date": row_doc.schedule_date.strftime("%d/%m/%Y"),
                    "requested": f"{format_time_12h(row_doc.from_time)} - {format_time_12h(row_doc.to_time)}",
                    "booked": "<br>".join([f"{format_time_12h(o.from_time)} - {format_time_12h(o.to_time)}" for o in overlaps]),
                    "status": "Already Booked"
                })
            else:
                conflicts.append({
                    "date": row_doc.schedule_date.strftime("%d/%m/%Y"),
                    "requested": f"{format_time_12h(row_doc.from_time)} - {format_time_12h(row_doc.to_time)}",
                    "booked": "-",
                    "status": "Available"
                })

    has_conflict = any(c["status"] == "Already Booked" for c in conflicts)
    
    if has_conflict:
        frappe.clear_messages()
        
        start_date = conflicts[0]["date"] if conflicts else ""
        end_date = conflicts[-1]["date"] if conflicts else ""

        html = f"<p><b>Booked from {start_date} to {end_date}</b></p>"
        html += "<table class='table table-bordered' style='margin-bottom:0;'><thead><tr><th>Date</th><th>Requested Time</th><th>Already Booked Time</th><th>Status</th></tr></thead><tbody>"
        
        for c in conflicts:
            status_html = f"<span class='text-danger'>{c['status']}</span>" if c["status"] == "Already Booked" else f"<span class='text-success'>{c['status']}</span>"
            html += f"<tr><td>{c['date']}</td><td>{c['requested']}</td><td>{c['booked']}</td><td>{status_html}</td></tr>"
            
        html += "</tbody></table>"
        
        frappe.throw(html, allow_dangerous_html=True, title=_("Update Blocked"))

    docs_to_save = []
    for name in names:
        row_doc = frappe.get_doc("Time Table", name)
        for field, value in updates.items():
            row_doc.set(field, value)
        row_doc.run_method("validate")
        docs_to_save.append(row_doc)

    try:
        # The callers show one "Updated N occurrence(s)" alert - mute the
        # per-row Attendance Session / Google Calendar toasts underneath it.
        total = len(docs_to_save)
        with quiet_bulk_operation():
            publish_bulk_progress("Updating", 0, total)
            for done, row_doc in enumerate(docs_to_save, start=1):
                row_doc.save(ignore_permissions=True)
                publish_bulk_progress("Updating", done, total)
    except Exception:
        frappe.db.rollback()
        raise

    frappe.db.commit()
    return docs_to_save

@frappe.whitelist()
def bulk_update_future_occurrences(time_table_name, updates):
    """Apply a set of field changes (e.g. venue, from_time, to_time, repeats_till, etc) to this
    Time Table occurrence and every future occurrence in the same recurring series.
    """
    from frappe.utils import nowdate, getdate
    import frappe

    updates = _parse_updates(updates)

    doc = frappe.get_doc("Time Table", time_table_name)
    series_root = doc.parent_schedule or doc.name

    # If repeat settings or schedule date are changing, we need to regenerate the series
    needs_regeneration = any(k in updates for k in ['repeat_frequency', 'repeats_till', 'schedule_date'])

    series_names = [series_root] + [
        d.name
        for d in frappe.get_all("Time Table", filters={"parent_schedule": series_root}, fields=["name"])
    ]

    future_rows = frappe.get_all(
        "Time Table",
        filters={
            "name": ["in", series_names],
            "schedule_date": [">=", doc.schedule_date if needs_regeneration else nowdate()],
            "docstatus": ["<", 2],
        },
        fields=["name", "schedule_date"],
        order_by="schedule_date",
    )

    if not future_rows and not needs_regeneration:
        frappe.throw(_("No current or future occurrences found to update."))

    # Apply updates to the current document in memory
    for field, value in updates.items():
        doc.set(field, value)

    if needs_regeneration:
        # Validate the new repeat settings
        if doc.repeat_frequency and doc.repeat_frequency != "Never" and not doc.repeats_till:
            frappe.throw(_("Please specify 'Repeats Till' date for recurring schedules"))

        # Dry run the generation to check for conflicts
        from datetime import datetime, timedelta
        from dateutil.relativedelta import relativedelta
        from slcm.slcm.doctype.institutional_calendar.institutional_calendar import get_non_teaching_dates_in_range

        current_date = datetime.strptime(str(doc.schedule_date), "%Y-%m-%d")
        end_date = datetime.strptime(str(doc.repeats_till) if doc.repeats_till else str(doc.schedule_date), "%Y-%m-%d")

        if doc.repeat_frequency == "Daily":
            increment = timedelta(days=1)
        elif doc.repeat_frequency == "Weekly":
            increment = timedelta(weeks=1)
        elif doc.repeat_frequency == "Monthly":
            increment = relativedelta(months=1)
        else:
            increment = None
            end_date = current_date # Just one day

        non_teaching_dates = get_non_teaching_dates_in_range(current_date.date(), end_date.date())

        test_date = current_date
        simulated_dates = []
        while test_date <= end_date:
            dt_str = test_date.strftime("%Y-%m-%d")
            if dt_str not in non_teaching_dates:
                simulated_dates.append(test_date.date())
            if not increment:
                break
            test_date += increment

        # Now check conflicts for these dates
        conflicts = []
        has_conflict = False
        
        for s_date in simulated_dates:
            # Create a dummy doc to check venue conflicts
            dummy = frappe.new_doc("Time Table")
            dummy.update(doc.as_dict())
            dummy.schedule_date = s_date
            dummy.name = "New Occurrence"

            # Check venue conflict manually
            if dummy.venue and dummy.from_time and dummy.to_time:
                # Find overlapping bookings
                overlaps = frappe.db.sql("""
                    SELECT name, from_time, to_time, based_on, course 
                    FROM `tabTime Table` 
                    WHERE venue = %s AND schedule_date = %s AND docstatus < 2 AND name NOT IN %s
                    AND (
                        (from_time < %s AND to_time > %s) OR
                        (from_time < %s AND to_time > %s) OR
                        (from_time >= %s AND to_time <= %s)
                    )
                """, (dummy.venue, dummy.schedule_date, tuple(series_names) if series_names else ('',), 
                        dummy.to_time, dummy.from_time, 
                        dummy.from_time, dummy.to_time, 
                        dummy.from_time, dummy.to_time), as_dict=True)

                if overlaps:
                    has_conflict = True
                    conflicts.append({
                        "date": s_date.strftime("%d/%m/%Y"),
                        "requested": f"{format_time_12h(dummy.from_time)} - {format_time_12h(dummy.to_time)}",
                        "booked": "<br>".join([f"{format_time_12h(o.from_time)} - {format_time_12h(o.to_time)}" for o in overlaps]),
                        "status": "Already Booked"
                    })
                else:
                    conflicts.append({
                        "date": s_date.strftime("%d/%m/%Y"),
                        "requested": f"{format_time_12h(dummy.from_time)} - {format_time_12h(dummy.to_time)}",
                        "booked": "-",
                        "status": "Available"
                    })

        if has_conflict:
            frappe.clear_messages()
            start_date = conflicts[0]["date"] if conflicts else ""
            end_date = conflicts[-1]["date"] if conflicts else ""
            html = f"<p><b>Booked from {start_date} to {end_date}</b></p>"
            html += "<table class='table table-bordered' style='margin-bottom:0;'><thead><tr><th>Date</th><th>Requested Time</th><th>Already Booked Time</th><th>Status</th></tr></thead><tbody>"
            
            for c in conflicts:
                status_html = f"<span class='text-danger'>{c['status']}</span>" if c["status"] == "Already Booked" else f"<span class='text-success'>{c['status']}</span>"
                html += f"<tr><td>{c['date']}</td><td>{c['requested']}</td><td>{c['booked']}</td><td>{status_html}</td></tr>"
            
            html += "</tbody></table>"
            
            frappe.throw(html, allow_dangerous_html=True, title=_("Update Blocked"))

        # If no conflicts, delete all un-marked future occurrences in this series
        future_names = [r.name for r in future_rows if r.name != doc.name]
        for name in future_names:
            # Check if attendance marked
            session_name = frappe.db.get_value("Attendance Session", {"class_schedule": name})
            if session_name and frappe.db.get_value("Attendance Session", session_name, "attendance_marked"):
                continue # Don't delete marked occurrences
            frappe.delete_doc("Time Table", name, force=1)

        # Save the current doc
        doc.save(ignore_permissions=True)
        # Call create_recurring_schedules to regenerate
        doc.create_recurring_schedules()
        
        updated_count = len(simulated_dates)

        return {
            "updated_count": updated_count,
            "updated_names": [],
        }

    else:
        # Standard update without regeneration
        docs_to_save = _apply_updates_to_rows([r.name for r in future_rows], updates)

        return {
            "updated_count": len(docs_to_save),
            "updated_names": [d.name for d in docs_to_save],
        }

@frappe.whitelist()
def bulk_update_selected_occurrences(names, updates):
    """List-view bulk action: apply a set of field changes (venue, time, ...)
    to exactly the Time Table rows the user checked - no series/date inference,
    since the checkboxes already say precisely which rows are in scope. Reuses
    the same validate-then-save-all-or-nothing logic as the future-occurrences
    action above.
    """
    import json

    if isinstance(names, str):
        names = json.loads(names)
    names = list(dict.fromkeys(names))  # de-dupe, preserve order

    updates = _parse_updates(updates)

    existing = frappe.get_all(
        "Time Table",
        filters={"name": ["in", names], "docstatus": ["<", 2]},
        fields=["name"],
        order_by="schedule_date",
    )
    valid_names = [r.name for r in existing]

    skipped = len(names) - len(valid_names)
    docs_to_save = _apply_updates_to_rows(valid_names, updates)

    return {
        "updated_count": len(docs_to_save),
        "updated_names": [d.name for d in docs_to_save],
        "skipped_count": skipped,
    }


@frappe.whitelist()
def update_event(args, field_map):
    """
    Custom update method for Time Table calendar drag-and-drop.
    Handles the split date (schedule_date) and time (from_time, to_time) fields.
    """
    import json
    from datetime import datetime
    
    if isinstance(args, str):
        args = json.loads(args)
    if isinstance(field_map, str):
        field_map = json.loads(field_map)
    
    args = frappe._dict(args)
    field_map = frappe._dict(field_map)

    if args.doctype != "Time Table":
        frappe.throw(frappe._("This endpoint can only update Time Table records."), frappe.PermissionError)

    # Get the document
    doc = frappe.get_doc(args.doctype, args.name)
    
    # Parse the start datetime
    if field_map.start and args.get(field_map.start):
        start_dt = args[field_map.start]
        if isinstance(start_dt, str):
            start_dt = datetime.strptime(start_dt, "%Y-%m-%d %H:%M:%S")
        
        # Update schedule_date and from_time
        doc.schedule_date = start_dt.date()
        doc.from_time = start_dt.time()
    
    # Parse the end datetime
    if field_map.end and args.get(field_map.end):
        end_dt = args[field_map.end]
        if isinstance(end_dt, str):
            end_dt = datetime.strptime(end_dt, "%Y-%m-%d %H:%M:%S")
        
        # Update to_time (date should remain the same as schedule_date)
        doc.to_time = end_dt.time()
    
    # Save the document
    doc.save()
    
    return doc.name


@frappe.whitelist()
def update_attendance_session_realtime(time_table_name, from_time, to_time, schedule_date, duration_hours):
	"""
	Update Attendance Session in real-time when Time Table entry times change.
	Called from client-side JavaScript without requiring a full save.
	Also triggers recalculation of Attendance Summary for all affected students.
	"""
	try:
		# Find the Attendance Session linked to this Time Table entry
		session_name = frappe.db.get_value("Attendance Session", {
			"class_schedule": time_table_name
		})

		if not session_name:
			return {"success": False, "message": "No Attendance Session found"}

		# Get the Attendance Session document
		session = frappe.get_doc("Attendance Session", session_name)

		# Only update if attendance hasn't been marked yet
		if session.attendance_marked:
			return {"success": False, "message": "Attendance already marked"}

		# Update the session fields
		session.session_start_time = from_time
		session.session_end_time = to_time
		session.duration_hours = duration_hours
		session.session_date = schedule_date

		# Save the session
		session.save(ignore_permissions=True)
		frappe.db.commit()

		# Trigger attendance recalculation for all students in this course offering
		# This updates total_class_hours in Attendance Summary
		if session.course_offering:
			try:
				from slcm.slcm.utils.attendance_calculator import calculate_student_attendance
				
				# Get all students who have attendance records for this course offering
				students = frappe.db.sql("""
					SELECT DISTINCT student
					FROM `tabStudent Attendance`
					WHERE course_offer = %s
				""", session.course_offering, as_dict=True)
				
				# Recalculate attendance for each student
				for student_row in students:
					calculate_student_attendance(student_row.student, session.course_offering)
				
				frappe.db.commit()
			except Exception as calc_error:
				# Log the error but don't fail the entire operation
				frappe.log_error(
					message=f"Error recalculating attendance: {str(calc_error)}", 
					title="Attendance Recalculation Error"
				)

		return {
			"success": True,
			"message": f"Attendance Session {session_name} updated",
			"session_name": session_name
		}

	except Exception as e:
		frappe.log_error(message=str(e), title="Real-time Attendance Session Update Error")
		return {"success": False, "message": str(e)}

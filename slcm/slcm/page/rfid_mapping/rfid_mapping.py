# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""RFID Card Management page.

Everything a person sees or types uses the Student ID (Student Master.registration_id,
e.g. L26001), never the system name (STUD-2026-00130). The system name is only
used internally for links and writes.
"""

import csv
import io
import os

import frappe
from frappe import _

from slcm.permissions import AAD_ROLES
from slcm.slcm.utils.rfid_cards import assign_card, remove_wrong_assignment

FEED_LIMIT = 200  # rows of live punch feed sent to the browser

# Header spellings accepted in an import file (normalised: lower case, spaces -> _)
STUDENT_ID_HEADERS = ("student_id", "studentid", "registration_id", "reg_id", "roll_no", "roll_number")
RFID_HEADERS = ("rfid_uid", "rfid", "uid", "card_uid", "rfid_card", "emp_code", "card_number")


def _check_access():
	frappe.only_for(("System Manager", *AAD_ROLES))


# ── Page data APIs ────────────────────────────────────────────────

_LOG_STATS_SQL = """
	SELECT
		COUNT(*)                                     AS total_logs,
		SUM(student IS NOT NULL AND student != '')   AS linked_logs,
		SUM(student IS NULL OR student = '')         AS unlinked_logs,
		MAX(swipe_time)                              AS last_swipe
	FROM `tabAttendance Log`
"""

_FEED_SQL = """
	SELECT
		al.rfid_uid,
		al.student,
		sm.registration_id  AS student_id,
		sm.first_name       AS student_name,
		al.swipe_time,
		al.terminal_alias,
		al.location         AS area_alias,
		al.device_id,
		al.processed
	FROM `tabAttendance Log` al
	LEFT JOIN `tabStudent Master` sm ON sm.name = al.student
	{where}
	ORDER BY al.swipe_time DESC
	LIMIT {limit}
"""


@frappe.whitelist()
def get_rfid_summary():
	"""Full page load — stats + unlinked cards + linked cards + live feed."""
	_check_access()

	stats = frappe.db.sql(_LOG_STATS_SQL, as_dict=True)[0]

	student_stats = frappe.db.sql("""
		SELECT
			COUNT(*)                                               AS total_students,
			SUM(rfid_uid IS NOT NULL AND rfid_uid != '')          AS students_with_rfid,
			SUM(rfid_uid IS NULL OR rfid_uid = '')                AS students_without_rfid,
			SUM(registration_id IS NULL OR registration_id = '')  AS students_without_id
		FROM `tabStudent Master`
	""", as_dict=True)[0]

	# Distinct RFID UIDs seen on the readers that are NOT linked to any student
	unlinked_cards = frappe.db.sql("""
		SELECT
			al.rfid_uid,
			COUNT(*)               AS swipe_count,
			MAX(al.swipe_time)     AS last_seen,
			MAX(al.device_id)      AS terminal_id,
			MAX(al.terminal_alias) AS terminal,
			MAX(al.location)       AS area
		FROM `tabAttendance Log` al
		WHERE al.student IS NULL OR al.student = ''
		GROUP BY al.rfid_uid
		ORDER BY last_seen DESC
	""", as_dict=True)

	# Students with a card — rfid_uid on Student Master, or already matched on a swipe
	linked_students = frappe.db.sql("""
		SELECT
			sm.name                                   AS student,
			sm.registration_id                        AS student_id,
			sm.first_name                             AS student_name,
			sm.programme_of_study                     AS programme,
			sm.batch                                  AS batch_year,
			sm.department,
			COALESCE(NULLIF(sm.rfid_uid, ''), MAX(al.rfid_uid)) AS rfid_uid,
			(sm.rfid_uid IS NOT NULL AND sm.rfid_uid != '')     AS has_active_card,
			COUNT(al.name)                            AS total_swipes,
			MAX(al.swipe_time)                        AS last_swipe
		FROM `tabStudent Master` sm
		LEFT JOIN `tabAttendance Log` al ON al.student = sm.name
		WHERE (sm.rfid_uid IS NOT NULL AND sm.rfid_uid != '')
		   OR (al.student IS NOT NULL AND al.student != '')
		GROUP BY sm.name, sm.registration_id, sm.first_name, sm.programme_of_study,
		         sm.batch, sm.department, sm.rfid_uid
		ORDER BY sm.first_name ASC
	""", as_dict=True)

	recent_logs = frappe.db.sql(_FEED_SQL.format(where="", limit=FEED_LIMIT), as_dict=True)

	return {
		"stats":           stats,
		"student_stats":   student_stats,
		"unlinked_cards":  unlinked_cards,
		"linked_students": linked_students,
		"recent_logs":     recent_logs,
	}


@frappe.whitelist()
def get_live_feed(since_swipe_time=None):
	"""Incremental refresh — only new logs + updated stats."""
	_check_access()

	stats = frappe.db.sql(_LOG_STATS_SQL, as_dict=True)[0]

	args = []
	where = ""
	if since_swipe_time:
		# >= so swipes in the same second are not missed; the browser de-duplicates
		where = "WHERE al.swipe_time >= %s"
		args.append(since_swipe_time)

	new_logs = frappe.db.sql(_FEED_SQL.format(where=where, limit=FEED_LIMIT), args, as_dict=True)
	return {"stats": stats, "new_logs": new_logs}


@frappe.whitelist()
def pull_now():
	"""'Pull now' button — run the SQL Server poller immediately.
	Same as rfid_sql_agent.poller.poll_now, but allowed for this page's roles
	(poll_now itself is System Manager only). The poll skips rows already imported."""
	_check_access()
	from slcm.slcm.rfid_sql_agent.poller import _run_poll

	try:
		cfg = frappe.get_single("RFID SQL Agent Settings")
		if not cfg.db_server:
			return {"success": False, "message": _("SQL Server is not configured in RFID SQL Agent Settings.")}
		_run_poll(cfg)
		last_id = frappe.db.get_single_value("RFID SQL Agent Settings", "last_log_id")
		return {"success": True, "message": _("Pulled from SQL Server. Last processed ID: {0}").format(last_id)}
	except Exception as e:
		frappe.log_error(title="RFID Card Management — pull_now error", message=frappe.get_traceback())
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def search_students(txt="", only_without_card=1):
	"""Student picker for the Assign dialog — matches Student ID, name or email."""
	_check_access()

	txt = (txt or "").strip()
	conditions = ["sm.registration_id IS NOT NULL", "sm.registration_id != ''"]
	args = {}
	if frappe.utils.cint(only_without_card):
		conditions.append("(sm.rfid_uid IS NULL OR sm.rfid_uid = '')")
	if txt:
		conditions.append(
			"(sm.registration_id LIKE %(like)s OR sm.first_name LIKE %(like)s"
			" OR sm.official_email_id LIKE %(like)s)"
		)
		args["like"] = f"%{txt}%"
		args["txt"] = txt

	order = "(sm.registration_id = %(txt)s) DESC, " if txt else ""
	where = " AND ".join(conditions)
	return frappe.db.sql(f"""
		SELECT
			sm.name, sm.registration_id AS student_id, sm.first_name AS student_name,
			sm.programme_of_study AS programme, sm.batch AS batch_year,
			sm.academic_status, sm.rfid_uid
		FROM `tabStudent Master` sm
		WHERE {where}
		ORDER BY {order}sm.registration_id ASC
		LIMIT 20
	""", args, as_dict=True)


# ── Student ID helpers ────────────────────────────────────────────

def _norm_id(value):
	return (str(value) if value is not None else "").strip().upper()


def _student_label(row):
	"""'Full Name (L26001)' — what people see instead of STUD-2026-xxxxx."""
	sid = row.get("registration_id") or row.get("student_id")
	name = row.get("first_name") or row.get("student_name") or ""
	return f"{name} ({sid})" if sid else name or row.get("name")


def _load_students():
	"""All students keyed by Student ID and by system name, for fast row resolution."""
	rows = frappe.db.sql("""
		SELECT name, registration_id, first_name, rfid_uid
		FROM `tabStudent Master`
	""", as_dict=True)
	by_id, by_name = {}, {}
	for r in rows:
		by_name[r.name] = r
		key = _norm_id(r.registration_id)
		if key:
			by_id.setdefault(key, []).append(r)
	return by_id, by_name


def _resolve(student_id, by_id, by_name):
	"""Student ID -> Student Master row. Returns (row, error)."""
	matches = by_id.get(_norm_id(student_id), [])
	if len(matches) == 1:
		return matches[0], None
	if len(matches) > 1:
		names = ", ".join(m.name for m in matches)
		return None, _("Student ID {0} is used by more than one student ({1}) — fix the duplicate first").format(
			student_id, names
		)
	# Older exports carried the system name — still accept it
	if student_id in by_name:
		return by_name[student_id], None
	return None, _("No student with Student ID {0}").format(student_id)


def _card_owner_by_uid():
	"""RFID UID -> owning Student Master name, from Student Master and card history."""
	owners = {}
	for r in frappe.db.sql(
		"SELECT student, rfid_uid, card_status FROM `tabStudent RFID Card` WHERE IFNULL(rfid_uid, '') != ''",
		as_dict=True,
	):
		owners[r.rfid_uid.strip()] = (r.student, r.card_status)
	for r in frappe.db.sql(
		"SELECT name, rfid_uid FROM `tabStudent Master` WHERE IFNULL(rfid_uid, '') != ''", as_dict=True
	):
		owners[r.rfid_uid.strip()] = (r.name, "Active")
	return owners


# ── Linking APIs ──────────────────────────────────────────────────

@frappe.whitelist()
def link_rfid_to_student(rfid_uid, student):
	"""Make rfid_uid the student's active card (Student Master + Student RFID Card) and backfill swipes.
	`student` is the Student Master name chosen in the picker."""
	_check_access()

	rfid_uid = (rfid_uid or "").strip()
	student = (student or "").strip()
	sm = frappe.db.get_value("Student Master", student, ["name", "registration_id", "first_name"], as_dict=True)
	if not sm:
		frappe.throw(_("Student not found."))

	owner = _card_owner_by_uid().get(rfid_uid)
	if owner and owner[0] != student:
		other = frappe.db.get_value("Student Master", owner[0], ["name", "registration_id", "first_name"], as_dict=True)
		frappe.throw(_("Card {0} already belongs to {1}.").format(
			frappe.bold(rfid_uid), frappe.bold(_student_label(other or {"name": owner[0]}))
		))

	linked = assign_card(student, rfid_uid, "Linked in RFID Card Management")
	frappe.db.commit()
	return {
		"success": True,
		"message": _("Card {0} linked to {1}. {2} swipe(s) matched.").format(
			frappe.bold(rfid_uid), frappe.bold(_student_label(sm)), linked
		),
	}


@frappe.whitelist()
def unlink_rfid_from_student(student):
	"""Undo a wrong link: clear the card from the student, drop its history record and unlink its swipes."""
	_check_access()
	sm = frappe.db.get_value("Student Master", student, ["name", "registration_id", "first_name"], as_dict=True)
	if not sm:
		frappe.throw(_("Student not found."))
	old_uid = remove_wrong_assignment(student)
	frappe.db.commit()
	if not old_uid:
		return {"success": False, "message": _("{0} has no active card.").format(_student_label(sm))}
	return {
		"success": True,
		"message": _("Card {0} removed from {1}.").format(frappe.bold(old_uid), frappe.bold(_student_label(sm))),
	}


# ── Export for vendor ─────────────────────────────────────────────

@frappe.whitelist()
def get_export_data():
	"""Students without a card, keyed by Student ID, for the vendor to fill rfid_uid.
	Students that have no Student ID yet cannot be matched on import, so they are
	left out and counted separately."""
	_check_access()

	rows = frappe.db.sql("""
		SELECT
			sm.registration_id     AS student_id,
			sm.first_name          AS student_name,
			sm.programme_of_study  AS programme,
			sm.batch               AS batch_year,
			sm.department          AS department,
			sm.official_email_id   AS email
		FROM `tabStudent Master` sm
		WHERE (sm.rfid_uid IS NULL OR sm.rfid_uid = '')
		  AND sm.registration_id IS NOT NULL AND sm.registration_id != ''
		  AND IFNULL(sm.academic_status, 'Active') NOT IN ('Graduated', 'Dropped')
		ORDER BY sm.programme_of_study, sm.batch, sm.registration_id
	""", as_dict=True)

	missing_id = frappe.db.sql("""
		SELECT COUNT(*) FROM `tabStudent Master`
		WHERE (rfid_uid IS NULL OR rfid_uid = '')
		  AND (registration_id IS NULL OR registration_id = '')
		  AND IFNULL(academic_status, 'Active') NOT IN ('Graduated', 'Dropped')
	""")[0][0]

	return {"rows": rows, "missing_id": missing_id}


# ── Bulk import ───────────────────────────────────────────────────

def _cell(value):
	"""Excel cell -> clean text (24221.0 -> '24221')."""
	if value is None:
		return ""
	if isinstance(value, float) and value.is_integer():
		value = int(value)
	return str(value).strip()


def _read_file_rows(file_url):
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	path = file_doc.get_full_path()
	if not os.path.exists(path):
		frappe.throw(_("Uploaded file not found on the server. Please upload it again."))

	ext = os.path.splitext(path)[1].lower()
	if ext == ".xlsx":
		import openpyxl

		wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
		try:
			return [[_cell(c) for c in row] for row in wb.active.iter_rows(values_only=True)]
		finally:
			wb.close()
	if ext in (".csv", ".txt"):
		with open(path, encoding="utf-8-sig", newline="") as f:
			return list(csv.reader(f))
	frappe.throw(_("Unsupported file type {0}. Upload a .csv or .xlsx file.").format(ext or "(none)"))


def _parse(csv_data=None, file_url=None):
	"""Returns list of (row_number, student_id, rfid_uid)."""
	if file_url:
		rows = _read_file_rows(file_url)
	else:
		text = (csv_data or "").lstrip("﻿")
		rows = list(csv.reader(io.StringIO(text)))

	# keep the spreadsheet row number (1-based) so problems point at the right line
	rows = [(n, r) for n, r in enumerate(rows, start=1) if any((c or "").strip() for c in r)]
	if not rows:
		frappe.throw(_("The file is empty."))

	header = [(h or "").strip().lstrip("﻿").lower().replace(" ", "_").replace("-", "_") for h in rows[0][1]]
	sid_col = next((header.index(h) for h in STUDENT_ID_HEADERS if h in header), None)
	uid_col = next((header.index(h) for h in RFID_HEADERS if h in header), None)
	if sid_col is None or uid_col is None:
		frappe.throw(_("Header row must contain the columns <code>student_id</code> and <code>rfid_uid</code>. Found: {0}").format(
			", ".join(h for h in header if h) or _("nothing")
		))

	parsed = []
	for i, r in rows[1:]:
		sid = (r[sid_col] if sid_col < len(r) else "").strip()
		uid = (r[uid_col] if uid_col < len(r) else "").strip()
		parsed.append((i, sid, uid))
	return parsed


@frappe.whitelist()
def bulk_import_rfid(csv_data=None, file_url=None, dry_run=1):
	"""Import student_id,rfid_uid pairs (student_id = Student ID such as L26001).

	dry_run=1 validates only and writes nothing, so the user can review a preview.
	dry_run=0 links every valid row; each row is all-or-nothing.
	"""
	_check_access()
	dry_run = frappe.utils.cint(dry_run)

	parsed = _parse(csv_data, file_url)
	by_id, by_name = _load_students()
	owners = _card_owner_by_uid()

	rows = []
	seen_students, seen_uids = {}, {}

	for row_no, sid, uid in parsed:
		item = {"row": row_no, "student_id": sid, "rfid_uid": uid, "student_name": ""}
		rows.append(item)

		if not sid and not uid:
			item.update(status="skipped", reason=_("Blank row"))
			continue
		if not uid:
			item.update(status="skipped", reason=_("No RFID UID filled in"))
			continue
		if not sid:
			item.update(status="error", reason=_("Student ID is missing"))
			continue

		sm, err = _resolve(sid, by_id, by_name)
		if err:
			item.update(status="error", reason=err)
			continue
		item["student_id"] = sm.registration_id or sid
		item["student_name"] = sm.first_name
		item["student"] = sm.name

		if sm.name in seen_students:
			item.update(status="error", reason=_("Student appears again (first on row {0})").format(seen_students[sm.name]))
			continue
		if uid in seen_uids:
			item.update(status="error", reason=_("Card appears again (first on row {0})").format(seen_uids[uid]))
			continue
		seen_students[sm.name] = row_no
		seen_uids[uid] = row_no

		owner = owners.get(uid)
		if owner and owner[0] != sm.name:
			other = by_name.get(owner[0]) or {"name": owner[0]}
			item.update(status="error", reason=_("Card already belongs to {0}").format(_student_label(other)))
			continue

		current = (sm.rfid_uid or "").strip()
		if current == uid:
			item.update(status="unchanged", reason=_("Already has this card"))
			continue
		item["replaces"] = current or None
		item["status"] = "ready"

	if not dry_run:
		for item in rows:
			if item["status"] != "ready":
				continue
			frappe.db.savepoint("rfid_import_row")
			try:
				item["swipes"] = assign_card(item["student"], item["rfid_uid"], "Bulk import in RFID Card Management")
				item["status"] = "linked"
			except Exception as e:
				frappe.db.rollback(save_point="rfid_import_row")
				frappe.clear_messages()
				item.update(status="error", reason=frappe.utils.strip_html(str(e)) or _("Could not link"))
		frappe.db.commit()

	counts = {}
	for item in rows:
		counts[item["status"]] = counts.get(item["status"], 0) + 1
		item.pop("student", None)

	return {"dry_run": dry_run, "counts": counts, "rows": rows}

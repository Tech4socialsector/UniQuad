# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""Student Map — link RFID cards to students from the device database (etpdb).

The device database holds one row per person: the card code (emp_code) and
the person's name. For students the card code IS the Student ID, so:

    device code  ==  Student Master.<map_student_field>   (registration_id)
    ->  Student Master.rfid_uid = device code

Flow
  1. preview()   reads etpdb once, classifies every record, caches the raw records
  2. apply()     creates an "RFID Student Map Log" and runs the mapping in the background
  3. manual_map() maps rows the run could not, straight from the log
  4. unmap_rows() takes cards back off students, straight from the log (the row can then be mapped again)

Which table/columns hold the code and name, and which Student Master field
they match, all come from RFID SQL Agent Settings -> Student Map (nothing
hard-coded). discover_name_sources() / sample_device_records() help pick them.
"""

import re
import uuid

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from slcm.permissions import AAD_ROLES
from slcm.slcm.utils.rfid_cards import UNMAP_REASONS, assign_card, change_source, unmap_card

SETTINGS = "RFID SQL Agent Settings"
LOG = "RFID Student Map Log"
LOG_ITEM = "RFID Student Map Log Item"
CACHE_PREFIX = "rfid_student_map:"
CACHE_SECS = 30 * 60
INACTIVE_STUDENT = ("Graduated", "Dropped", "Alumni", "Withdrawn")
MANUAL_OK = ("Not Matched", "Conflict", "Skipped", "Failed", "Unmapped")
UNMAP_OK = ("Mapped", "Manually Mapped", "Already Mapped")
_IDENT = re.compile(r"^[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)*$")

COUNT_FIELDS = {
	"Mapped": "mapped",
	"Manually Mapped": "manually_mapped",
	"Already Mapped": "already_mapped",
	"Not Matched": "not_matched",
	"Conflict": "conflicts",
	"Skipped": "skipped",
	"Failed": "failed",
	"Unmapped": "unmapped",
}


def _check_access():
	frappe.only_for(("System Manager", *AAD_ROLES))


# ── Settings ──────────────────────────────────────────────────────

def _ident(value, label):
	value = (value or "").strip()
	if not value or not _IDENT.match(value):
		frappe.throw(_("{0} is not set or is not a valid table/column name: {1}").format(label, frappe.bold(value or "—")))
	return value


def _config():
	cfg = frappe.get_single(SETTINGS)

	def val(field, default):
		v = cfg.get(field)
		return default if v is None or v == "" else v

	conf = frappe._dict(
		table=_ident(val("map_source_table", "personnel_employee"), _("Names Table / View")),
		code_col=_ident(val("map_code_column", cfg.sql_empcode_column or "emp_code"), _("Card Code Column")),
		name_cols=[_ident(c, _("Name Column(s)")) for c in str(
			"first_name,last_name" if cfg.get("map_name_columns") is None else cfg.map_name_columns
		).split(",") if c.strip()],
		student_field=(val("map_student_field", "registration_id") or "registration_id").strip(),
		ignore_case=cint(val("map_ignore_case", 1)),
		include_name_mismatch=cint(val("map_include_name_mismatch", 0)),
		database=cfg.db_database or "",
	)
	if conf.student_field != "name" and not frappe.get_meta("Student Master").get_field(conf.student_field):
		frappe.throw(_("Match To Student Master Field {0} does not exist in Student Master.").format(frappe.bold(conf.student_field)))
	conf.source = f"{conf.database}.{conf.table}" if conf.database else conf.table
	student_label = frappe.get_meta("Student Master").get_label(conf.student_field) if conf.student_field != "name" else "ID"
	conf.match_rule = _("{0}.{1} = Student Master {2}").format(conf.table, conf.code_col, student_label)
	return conf


# ── Device database (SQL Server) ──────────────────────────────────

def _text(v):
	if v is None:
		return ""
	if isinstance(v, float) and v.is_integer():
		v = int(v)
	return str(v).strip()


def _query(sql, params=None):
	from slcm.slcm.rfid_sql_agent.connection import get_connection

	conn = get_connection()
	try:
		cur = conn.cursor()
		cur.execute(sql, params or [])
		return cur.fetchall()
	finally:
		conn.close()


def _fetch_device_records(conf, limit=None):
	"""[(code, name), …] from the device database."""
	cols = [conf.code_col] + conf.name_cols
	top = f"TOP {int(limit)} " if limit else ""
	# codes only (e.g. the swipes view): one row per card instead of one per swipe
	distinct = "" if conf.name_cols else "DISTINCT "
	try:
		rows = _query(f"SELECT {distinct}{top}{', '.join(cols)} FROM {conf.table} WHERE {conf.code_col} IS NOT NULL")
	except frappe.ValidationError:
		raise
	except Exception as e:
		err = str(e)
		if "229" in err or "permission was denied" in err.lower():
			login = (frappe.db.get_single_value(SETTINGS, "db_login") or "").strip() or "the SQL login"
			frappe.throw(
				_("The SQL Server login {0} is not allowed to read {1}.<br><br>"
				  "Either ask the SQL Server admin to give it read access (see the Student Map tab for the exact SQL), "
				  "or use <b>Student Map Tools → Find Name Columns</b> to pick a table this login can read. "
				  "Leave Name Column(s) empty to match by Student ID only.").format(frappe.bold(login), frappe.bold(conf.table)),
				title=_("No permission on {0}").format(conf.table),
			)
		frappe.throw(_("Could not read {0} from the device database: {1}").format(frappe.bold(conf.table), err))
	out = []
	for r in rows:
		code = _text(r[0])
		name = " ".join(p for p in (_text(x) for x in r[1:]) if p)
		out.append((code, re.sub(r"\s+", " ", name)))
	return out


@frappe.whitelist()
def discover_name_sources():
	"""Tables in the device database that have a code column and a name column — to pick in the UI."""
	frappe.only_for("System Manager")
	rows = _query("""
		SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE
		FROM INFORMATION_SCHEMA.COLUMNS c
		WHERE HAS_PERMS_BY_NAME(QUOTENAME(c.TABLE_SCHEMA) + '.' + QUOTENAME(c.TABLE_NAME), 'OBJECT', 'SELECT') = 1
		ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
	""")
	tables = {}
	for schema, table, col, dtype in rows:
		key = table if (schema or "dbo") == "dbo" else f"{schema}.{table}"
		tables.setdefault(key, []).append({"name": col, "type": dtype})

	def is_code(c):
		n = c.lower()
		return n in ("emp_code", "empcode", "badgenumber", "badge_number", "pin", "card_no", "cardno", "code") or n.endswith("_code")

	def is_name(c):
		n = c.lower()
		return "name" in n and not n.endswith(("_by", "username")) and n not in ("username", "user_name", "dept_name", "area_name", "terminal_name", "company_name", "position_name")

	found = []
	for table, cols in tables.items():
		code_cols = [c["name"] for c in cols if is_code(c["name"])]
		name_cols = [c["name"] for c in cols if is_name(c["name"])]
		if not code_cols:
			continue
		score = 0
		score += 50 if "emp_code" in [c.lower() for c in code_cols] else 0
		score += 40 if "employee" in table.lower() or "personnel" in table.lower() else 0
		score += 20 if {"first_name", "last_name"} & {c.lower() for c in name_cols} else 0
		score -= 60 if not name_cols else 0  # usable, but codes only
		score -= 30 if any(w in table.lower() for w in ("log", "trans", "history", "audit")) else 0
		found.append({"table": table, "code_columns": code_cols, "name_columns": name_cols, "has_names": bool(name_cols),
		              "columns": [c["name"] for c in cols], "score": score})
	found.sort(key=lambda t: (-t["score"], t["table"]))
	return {"candidates": found[:40], "table_count": len(tables)}


@frappe.whitelist()
def sample_device_records(table, code_column, name_columns):
	"""First 10 rows for the chosen table/columns, so the user can see the names are right before saving."""
	frappe.only_for("System Manager")
	conf = frappe._dict(
		table=_ident(table, _("Table")),
		code_col=_ident(code_column, _("Code column")),
		name_cols=[_ident(c, _("Name column")) for c in (name_columns or "").split(",") if c.strip()],
	)
	return [{"code": c, "name": n} for c, n in _fetch_device_records(conf, limit=10)]


# ── Classification ────────────────────────────────────────────────

def _norm_key(v, ignore_case):
	v = _text(v)
	return re.sub(r"\s+", "", v).upper() if ignore_case else v


def _name_tokens(name):
	tokens = [t for t in re.sub(r"[^a-z]+", " ", (name or "").casefold()).split() if t]
	long_tokens = [t for t in tokens if len(t) > 1]  # drop initials
	return set(long_tokens or tokens)


def _names_same(a, b):
	ta, tb = _name_tokens(a), _name_tokens(b)
	if not ta or not tb:
		return True
	if ta <= tb or tb <= ta:
		return True
	return "".join(sorted("".join(ta))) == "".join(sorted("".join(tb)))


def _students(conf):
	field = "name" if conf.student_field == "name" else f"`{conf.student_field}`"
	return frappe.db.sql(f"""
		SELECT name, {field} AS match_key, registration_id, first_name, official_email_id,
		       rfid_uid, student_status, programme_of_study, batch
		FROM `tabStudent Master`
	""", as_dict=True)


def _card_owners():
	owners = {}
	for r in frappe.db.sql("""SELECT student, rfid_uid FROM `tabStudent RFID Card`
		WHERE IFNULL(rfid_uid, '') != ''""", as_dict=True):
		owners[r.rfid_uid.strip()] = r.student
	for r in frappe.db.sql("""SELECT name, rfid_uid FROM `tabStudent Master`
		WHERE IFNULL(rfid_uid, '') != ''""", as_dict=True):
		owners[r.rfid_uid.strip()] = r.name
	return owners


def _removed_pairs():
	"""(student, card) pairs whose last change in the RFID UID Change Log took the card off the student. An
	automatic run must not put such a card back (a card marked Lost would even become active again)."""
	if not frappe.db.table_exists("RFID UID Change Log Entry"):
		return set()
	state = {}
	for r in frappe.db.sql("""SELECT log.student, c.old_rfid_uid, c.new_rfid_uid
		FROM `tabRFID UID Change Log Entry` c
		JOIN `tabRFID UID Change Log` log ON log.name = c.parent AND c.parenttype = 'RFID UID Change Log'
		ORDER BY c.changed_on, c.idx""", as_dict=True):
		if r.old_rfid_uid:
			state[(r.student, r.old_rfid_uid.strip())] = False
		if r.new_rfid_uid:
			state[(r.student, r.new_rfid_uid.strip())] = True
	return {pair for pair, linked in state.items() if not linked}


def _classify(records, conf, include_name_mismatch):
	"""Decide what happens to every device record. Status: Ready | Already Mapped | Not Matched | Conflict | Skipped."""
	students = _students(conf)
	by_key, by_name = {}, {}
	for s in students:
		by_name[s.name] = s
		k = _norm_key(s.match_key, conf.ignore_case)
		if k:
			by_key.setdefault(k, []).append(s)
	owners = _card_owners()
	removed = _removed_pairs()

	rows, seen, invalid, device_keys = [], {}, 0, set()
	for code, device_name in records:
		if not code:
			invalid += 1
			continue
		key = _norm_key(code, conf.ignore_case)
		if key in seen:  # same person listed twice in the device database
			first = seen[key]
			if device_name and not first["device_name"]:
				first["device_name"] = device_name
			continue
		device_keys.add(key)
		row = {"rfid_uid": code, "device_name": device_name, "student": None, "student_id": None,
		       "student_name": None, "student_email": None, "name_check": "", "status": "", "message": ""}
		seen[key] = row
		rows.append(row)

		matches = by_key.get(key, [])
		if not matches:
			holder = by_name.get(owners.get(code))
			if holder and (holder.rfid_uid or "").strip() == code:  # linked earlier by hand
				row.update(student=holder.name, student_id=holder.registration_id, student_name=holder.first_name,
				           student_email=holder.official_email_id, status="Already Mapped",
				           message=_("Card already linked to this student (mapped by hand)"))
			else:
				row.update(status="Not Matched", message=_("No student with this Student ID"))
			continue
		if len(matches) > 1:
			row.update(status="Conflict", message=_("{0} students share this Student ID: {1}").format(
				len(matches), ", ".join(m.registration_id or m.name for m in matches)))
			continue

		sm = matches[0]
		row.update(student=sm.name, student_id=sm.registration_id, student_name=sm.first_name,
		           student_email=sm.official_email_id, programme=sm.programme_of_study, batch=sm.batch)
		if device_name and sm.first_name:
			row["name_check"] = "Same" if _names_same(device_name, sm.first_name) else "Different"

		current = (sm.rfid_uid or "").strip()
		owner = owners.get(code)
		if current == code:
			row.update(status="Already Mapped", message=_("Card already linked"))
		elif owner and owner != sm.name:
			other = by_name.get(owner) or {}
			row.update(status="Conflict", message=_("Card already belongs to {0} ({1})").format(
				other.get("first_name") or owner, other.get("registration_id") or owner))
		elif current:
			row.update(status="Conflict", message=_("Student already has card {0}").format(current))
		elif (sm.name, code) in removed:
			row.update(status="Skipped", message=_("Card was taken off this student by hand — map by hand to link it again"))
		elif row["name_check"] == "Different" and not include_name_mismatch:
			row.update(status="Skipped", message=_("Names differ — check and map by hand if correct"))
		else:
			row.update(status="Ready", message=_("Names differ — mapped by Student ID") if row["name_check"] == "Different" else "")

	not_on_device = sum(
		1 for s in students
		if _norm_key(s.match_key, conf.ignore_case)
		and _norm_key(s.match_key, conf.ignore_case) not in device_keys
		and not (s.rfid_uid or "").strip()
		and (s.student_status or "Active") not in INACTIVE_STUDENT
	)
	kpi = {
		"device_records": len(rows),
		"ready": sum(r["status"] == "Ready" for r in rows),
		"already_mapped": sum(r["status"] == "Already Mapped" for r in rows),
		"not_matched": sum(r["status"] == "Not Matched" for r in rows),
		"conflicts": sum(r["status"] == "Conflict" for r in rows),
		"skipped": sum(r["status"] == "Skipped" for r in rows),
		"names_differ": sum(r["name_check"] == "Different" for r in rows),
		"blank_codes": invalid,
		"students_not_on_device": not_on_device,
	}
	return rows, kpi


# ── Preview / apply ───────────────────────────────────────────────

@frappe.whitelist()
def preview(include_name_mismatch=None):
	_check_access()
	conf = _config()
	include = conf.include_name_mismatch if include_name_mismatch in (None, "") else cint(include_name_mismatch)
	records = _fetch_device_records(conf)
	rows, kpi = _classify(records, conf, include)

	token = uuid.uuid4().hex
	frappe.cache.set_value(CACHE_PREFIX + token, {"user": frappe.session.user, "records": records}, expires_in_sec=CACHE_SECS)
	return {"token": token, "kpi": kpi, "rows": rows, "source": conf.source, "match_rule": conf.match_rule,
	        "include_name_mismatch": include, "has_names": bool(conf.name_cols)}


def _running_log():
	return frappe.db.get_value(LOG, {"status": "In Progress", "creation": [">", frappe.utils.add_to_date(now_datetime(), hours=-2)]}, "name")


@frappe.whitelist()
def apply(token, include_name_mismatch=0):
	"""Start the mapping for the records shown in the preview. Returns the log name; work runs in the background."""
	_check_access()
	cached = frappe.cache.get_value(CACHE_PREFIX + (token or ""))
	if not cached or cached.get("user") != frappe.session.user:
		frappe.throw(_("This preview has expired. Click Student Map again to load fresh data."))
	running = _running_log()
	if running:
		frappe.throw(_("A Student Map run is already in progress: {0}").format(
			frappe.utils.get_link_to_form(LOG, running)))

	conf = _config()
	log = frappe.get_doc({
		"doctype": LOG,
		"status": "In Progress",
		"run_by": frappe.session.user,
		"run_on": now_datetime(),
		"source": conf.source,
		"match_rule": conf.match_rule,
		"include_name_mismatch": cint(include_name_mismatch),
	}).insert(ignore_permissions=True)
	frappe.cache.delete_value(CACHE_PREFIX + token)

	frappe.enqueue(
		"slcm.slcm.rfid_sql_agent.student_map.run_student_map",
		queue="long", timeout=3600, enqueue_after_commit=True,
		log_name=log.name, records=cached["records"], include_name_mismatch=cint(include_name_mismatch),
	)
	return {"log": log.name}


def _publish(log_name, done, total, finished=False):
	frappe.publish_realtime("rfid_student_map_progress",
	                        {"log": log_name, "done": done, "total": total, "finished": finished},
	                        user=frappe.session.user, after_commit=False)


def run_student_map(log_name, records, include_name_mismatch=0):
	"""Background job: write every record to the log, then link the Ready ones one by one."""
	log = frappe.get_doc(LOG, log_name)
	try:
		conf = _config()
		rows, _kpi = _classify(records, conf, cint(include_name_mismatch))
		item_fields = {df.fieldname for df in frappe.get_meta(LOG_ITEM).fields}
		for r in rows:
			item = {k: v for k, v in r.items() if k in item_fields}
			item["status"] = "Pending" if r["status"] == "Ready" else r["status"]
			log.append("items", item)
		log.total_records = len(rows)
		log.save(ignore_permissions=True)
		frappe.db.commit()

		pending = [i for i in log.items if i.status == "Pending"]
		total = len(pending)
		_publish(log.name, 0, total)
		with change_source(_("Student Map {0}").format(log.name)):
			for n, item in enumerate(pending, 1):
				frappe.db.savepoint("rfid_map_row")
				try:
					swipes = assign_card(item.student, item.rfid_uid, _("Student Map {0}").format(log.name))
					note = item.message + " · " if item.message else ""
					upd = {"status": "Mapped", "message": note + _("{0} earlier swipe(s) matched").format(swipes),
					       "mapped_by": frappe.session.user, "mapped_on": now_datetime()}
				except Exception as e:
					frappe.db.rollback(save_point="rfid_map_row")
					frappe.clear_messages()
					upd = {"status": "Failed", "message": frappe.utils.strip_html(str(e))[:500] or _("Could not link")}
				frappe.db.set_value(LOG_ITEM, item.name, upd, update_modified=False)
				if n % 50 == 0 or n == total:
					frappe.db.commit()
					_publish(log.name, n, total)

		_finish(log.name)
		frappe.db.set_single_value(SETTINGS, "map_last_run", log.name)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"RFID Student Map failed ({log_name})", message=frappe.get_traceback())
		frappe.db.set_value(LOG, log_name, {"status": "Failed", "error_message": frappe.get_traceback()[-2000:]})
		_finish(log_name, failed=True)
		frappe.db.commit()
	_publish(log_name, 0, 0, finished=True)


def _finish(log_name, failed=False):
	"""Recount the log from its rows and set the overall status."""
	counts = dict(frappe.db.sql(
		f"SELECT status, COUNT(*) FROM `tab{LOG_ITEM}` WHERE parent = %s AND parenttype = %s GROUP BY status",
		(log_name, LOG),
	))
	values = {field: counts.get(status, 0) for status, field in COUNT_FIELDS.items()}
	values["total_records"] = sum(counts.values())
	if not failed:
		values["status"] = "Completed with Issues" if values["failed"] or counts.get("Pending") else "Completed"
	frappe.db.set_value(LOG, log_name, values)


# ── Manual mapping from the log ───────────────────────────────────

@frappe.whitelist()
def manual_map(log_name, mappings):
	"""mappings: [{"row": <log item name>, "student": <Student Master name>}]. Links each card by hand."""
	_check_access()
	mappings = frappe.parse_json(mappings) or []
	if not frappe.db.exists(LOG, log_name):
		frappe.throw(_("Log {0} not found.").format(log_name))
	if frappe.db.get_value(LOG, log_name, "status") == "In Progress":
		frappe.throw(_("Wait for this run to finish before mapping by hand."))

	results = []
	with change_source(_("Student Map {0} — mapped by hand").format(log_name)):
		for m in mappings:
			row_name, student = (m.get("row") or "").strip(), (m.get("student") or "").strip()
			item = frappe.db.get_value(LOG_ITEM, {"name": row_name, "parent": log_name},
			                           ["name", "rfid_uid", "status"], as_dict=True)
			if not item or not student:
				continue
			if item.status not in MANUAL_OK:
				results.append({"row": row_name, "ok": False, "message": _("Row is already {0}").format(item.status)})
				continue
			sm = frappe.db.get_value("Student Master", student,
			                         ["name", "registration_id", "first_name", "official_email_id"], as_dict=True)
			if not sm:
				results.append({"row": row_name, "ok": False, "message": _("Student not found")})
				continue
			frappe.db.savepoint("rfid_manual_row")
			try:
				swipes = assign_card(sm.name, item.rfid_uid, _("Student Map {0} — mapped by hand").format(log_name))
				frappe.db.set_value(LOG_ITEM, item.name, {
					"status": "Manually Mapped", "student": sm.name, "student_id": sm.registration_id,
					"student_name": sm.first_name, "student_email": sm.official_email_id,
					"message": _("Mapped by hand · {0} earlier swipe(s) matched").format(swipes),
					"mapped_by": frappe.session.user, "mapped_on": now_datetime(),
				}, update_modified=False)
				results.append({"row": row_name, "ok": True, "message": _("{0} → {1}").format(item.rfid_uid, sm.registration_id or sm.name)})
			except Exception as e:
				frappe.db.rollback(save_point="rfid_manual_row")
				frappe.clear_messages()
				results.append({"row": row_name, "ok": False, "message": frappe.utils.strip_html(str(e))})

	_finish(log_name)
	frappe.db.commit()
	return results


@frappe.whitelist()
def run_card_changes(log_name, student=None, txt=None, start=0, page_len=50):
	"""Card changes newest first, a page at a time: those this log made (its run, manual mapping and unmapping),
	or, when a student is given, every card change of that student from any screen. Returns {rows, total}."""
	_check_access()
	conditions, values = [], {}
	if student:
		conditions.append("log.student = %(student)s")
		values["student"] = student
	else:
		conditions.append("c.source LIKE %(source)s")
		values["source"] = f"%{log_name}%"
	if txt:
		conditions.append("""(log.student_id LIKE %(txt)s OR log.student_name LIKE %(txt)s
			OR c.old_rfid_uid LIKE %(txt)s OR c.new_rfid_uid LIKE %(txt)s)""")
		values["txt"] = f"%{txt.strip()}%"
	base = f"""FROM `tabRFID UID Change Log Entry` c
		JOIN `tabRFID UID Change Log` log ON log.name = c.parent AND c.parenttype = 'RFID UID Change Log'
		WHERE {" AND ".join(conditions)}"""
	total = frappe.db.sql(f"SELECT COUNT(*) {base}", values)[0][0]
	rows = frappe.db.sql(f"""
		SELECT log.name AS log, log.student_id, log.student_name, c.change_type, c.old_rfid_uid, c.new_rfid_uid,
		       c.changed_on, c.changed_by, c.source
		{base}
		ORDER BY c.changed_on DESC, c.idx DESC
		LIMIT %(page_len)s OFFSET %(start)s
	""", {**values, "page_len": min(cint(page_len) or 50, 500), "start": max(cint(start), 0)}, as_dict=True)
	return {"rows": rows, "total": total}


@frappe.whitelist()
def unmap_rows(log_name, rows, reason):
	"""rows: log item names. Takes each row's card off its student (see rfid_cards.unmap_card for the reasons).
	A row is only undone while the student still has that row's card; a student who has since got another
	card is left alone."""
	_check_access()
	rows = [r for r in dict.fromkeys(frappe.parse_json(rows) or []) if r]
	if not frappe.db.exists(LOG, log_name):
		frappe.throw(_("Log {0} not found.").format(log_name))
	if frappe.db.get_value(LOG, log_name, "status") == "In Progress":
		frappe.throw(_("Wait for this run to finish before removing cards."))
	if not rows:
		frappe.throw(_("Select at least one row."))
	if reason not in UNMAP_REASONS:
		frappe.throw(_("Choose why the card is being removed."))

	results = []
	with change_source(_("Student Map {0} — unmapped ({1})").format(log_name, reason)):
		for row_name in rows:
			item = frappe.db.get_value(LOG_ITEM, {"name": row_name, "parent": log_name},
			                           ["name", "rfid_uid", "status", "student", "student_id"], as_dict=True)
			if not item:
				continue
			label = item.student_id or item.student or item.rfid_uid
			if item.status not in UNMAP_OK or not item.student:
				results.append({"row": row_name, "ok": False, "message": _("{0}: row is {1}, nothing to remove").format(label, item.status)})
				continue
			current = (frappe.db.get_value("Student Master", item.student, "rfid_uid") or "").strip()
			if current != (item.rfid_uid or "").strip():
				results.append({"row": row_name, "ok": False, "message": (
					_("{0}: student now has card {1}, not {2}; left as is").format(label, current, item.rfid_uid) if current
					else _("{0}: card {1} is already off this student").format(label, item.rfid_uid))})
				continue
			frappe.db.savepoint("rfid_unmap_row")
			try:
				unmap_card(item.student, reason)
				frappe.db.set_value(LOG_ITEM, item.name, {
					"status": "Unmapped",
					"message": _("Card removed ({0}) by {1}").format(reason, frappe.session.user),
					"mapped_by": frappe.session.user, "mapped_on": now_datetime(),
				}, update_modified=False)
				results.append({"row": row_name, "ok": True, "message": _("{0}: card {1} removed").format(label, item.rfid_uid)})
			except Exception as e:
				frappe.db.rollback(save_point="rfid_unmap_row")
				frappe.clear_messages()
				results.append({"row": row_name, "ok": False, "message": "{0}: {1}".format(label, frappe.utils.strip_html(str(e)))})

	_finish(log_name)
	frappe.db.commit()
	return results


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def student_link_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link-field search for the manual-map dialog: find students by Student ID, name or email."""
	_check_access()
	like = f"%{txt or ''}%"
	return frappe.db.sql("""
		SELECT name, registration_id, first_name, IFNULL(rfid_uid, '')
		FROM `tabStudent Master`
		WHERE registration_id LIKE %(like)s OR first_name LIKE %(like)s
		   OR official_email_id LIKE %(like)s OR name LIKE %(like)s
		ORDER BY (registration_id = %(txt)s) DESC, registration_id
		LIMIT %(start)s, %(page_len)s
	""", {"like": like, "txt": txt or "", "start": cint(start), "page_len": cint(page_len) or 20})

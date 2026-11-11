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
from slcm.slcm.utils.rfid_cards import assign_card, change_source

SETTINGS = "RFID SQL Agent Settings"
LOG = "RFID Student Map Log"
LOG_ITEM = "RFID Student Map Log Item"
CACHE_PREFIX = "rfid_student_map:"
CACHE_SECS = 30 * 60
INACTIVE_STUDENT = ("Graduated", "Dropped", "Alumni", "Withdrawn")
MANUAL_OK = ("Not Matched", "Conflict", "Skipped", "Failed")
_IDENT = re.compile(r"^[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)*$")

COUNT_FIELDS = {
	"Mapped": "mapped",
	"Manually Mapped": "manually_mapped",
	"Already Mapped": "already_mapped",
	"Not Matched": "not_matched",
	"Conflict": "conflicts",
	"Skipped": "skipped",
	"Failed": "failed",
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
		name_cols=[_ident(c, _("Name Column(s)")) for c in str(val("map_name_columns", "first_name,last_name")).split(",") if c.strip()],
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
	try:
		rows = _query(f"SELECT {top}{', '.join(cols)} FROM {conf.table} WHERE {conf.code_col} IS NOT NULL")
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.throw(_("Could not read {0} from the device database: {1}").format(frappe.bold(conf.table), e))
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
		SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
		FROM INFORMATION_SCHEMA.COLUMNS
		ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
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
		if not code_cols or not name_cols:
			continue
		score = 0
		score += 50 if "emp_code" in [c.lower() for c in code_cols] else 0
		score += 40 if "employee" in table.lower() or "personnel" in table.lower() else 0
		score += 20 if {"first_name", "last_name"} & {c.lower() for c in name_cols} else 0
		score -= 30 if any(w in table.lower() for w in ("log", "trans", "history", "audit")) else 0
		found.append({"table": table, "code_columns": code_cols, "name_columns": name_cols,
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
		       rfid_uid, student_status
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
		           student_email=sm.official_email_id)
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
	        "include_name_mismatch": include}


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
		for r in rows:
			log.append("items", {**r, "status": "Pending" if r["status"] == "Ready" else r["status"]})
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

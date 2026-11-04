"""Rendering engine for Drag and Drop ID card designs.

The designer (ID Card Template form) and the card generator both lay a card
out in "design units": a CR80 card is 337 x 212.5 units, the same CSS pixels
the designer draws in. The server renders that exact layout in headless
Chromium at a 3x device scale factor, which yields a 1011 x 638 px image
(85.6 x 54 mm at 300 DPI). Because both sides use the same coordinates and
the same element-to-HTML rules, what the designer shows is what gets printed.

This module is also the single source of truth for the data fields
("tokens") a design can use; the designer fetches them via
`get_designer_meta` instead of keeping its own copy.
"""

import html
import io
import json
import os
import re
import subprocess
import tempfile
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import add_years, format_date, today

CARD_UNITS = {"horizontal": (337, 212.5), "vertical": (212.5, 337)}
RENDER_SCALE = 3

PERSON_LINKS = {
	"Student": ("student", "Student Master"),
	"Faculty": ("faculty", "Faculty"),
	"Driver": ("driver", "SLCM Driver"),
}

# key, label, group, card types (None = every type), sample value
TEXT_TOKENS = [
	("student_name", "Full Name", "Person", None, "Aarav Sharma"),
	("student_id", "ID Number", "Person", None, "NLS2026001"),
	(
		"designation",
		"Designation",
		"Person",
		("Faculty", "Driver", "Visitor", "Non-Faculty"),
		"Assistant Professor",
	),
	("department", "Department", "Person", ("Faculty", "Non-Faculty"), "Faculty of Law"),
	("programme", "Programme", "Academic", ("Student",), "B.A., LL.B. (Hons.)"),
	("batch", "Batch", "Academic", ("Student",), "2026-2031"),
	("academic_year", "Academic Year", "Academic", ("Student",), "AY 2026-2027"),
	("blood_group", "Blood Group", "Person", ("Student", "Faculty", "Driver"), "B+"),
	("date_of_birth", "Date of Birth", "Person", ("Student",), None),
	("email", "Email", "Contact", None, "aarav.sharma@example.edu"),
	("phone", "Phone", "Contact", None, "+91 98765 43210"),
	("address", "Address", "Contact", ("Student",), "Nagarbhavi, Bengaluru 560072"),
	("license_number", "Licence No.", "Person", ("Driver",), "KA01 20260001234"),
	("company", "Company", "Person", ("Visitor", "Non-Faculty"), "Acme Services Pvt Ltd"),
	("purpose", "Purpose of Visit", "Person", ("Visitor",), "Guest lecture"),
	("card_number", "Card Number", "Card", None, "STU-00001"),
	("issue_date", "Issue Date", "Card", None, None),
	("expiry_date", "Valid Till", "Card", None, None),
	("validity_text", "Validity Text", "Institute", None, "Valid for the programme duration"),
	("institute_name", "Institute Name", "Institute", None, "National Law School of India University"),
	("institute_address", "Institute Address", "Institute", None, "Nagarbhavi, Bengaluru 560072"),
]

IMAGE_TOKENS = [
	("photo", "Photo", "Person"),
	("qr_code_image", "QR Code", "Card"),
	("institute_logo", "Institute Logo", "Institute"),
	("authority_signature", "Authority Signature", "Institute"),
	("watermark_image", "Watermark", "Institute"),
]

NAME_LABELS = {
	"Student": "Student Name",
	"Faculty": "Faculty Name",
	"Driver": "Driver Name",
	"Visitor": "Visitor Name",
	"Non-Faculty": "Staff Name",
}
ID_LABELS = {"Student": "Student ID", "Faculty": "Employee ID", "Driver": "Driver ID"}

# Older designs used "[Label]" placeholders; these keep them working.
LEGACY_ALIASES = {
	"student name": "student_name",
	"faculty name": "student_name",
	"driver name": "student_name",
	"visitor name": "student_name",
	"staff name": "student_name",
	"name": "student_name",
	"student id": "student_id",
	"employee id": "student_id",
	"driver id": "student_id",
	"id": "student_id",
	"blood group": "blood_group",
	"group": "blood_group",
	"phone": "phone",
	"email": "email",
	"batch": "batch",
	"programme": "programme",
	"program": "programme",
	"course": "programme",
	"academic year": "academic_year",
	"date of birth": "date_of_birth",
	"expiry date": "expiry_date",
	"issue date": "issue_date",
	"department": "department",
	"dept": "department",
	"institute name": "institute_name",
	"institute address": "institute_address",
	"address": "address",
	"designation": "designation",
	"company": "company",
	"license no": "license_number",
	"purpose": "purpose",
}
MAPPING_ALIASES = {"program": "programme"}

TOKEN_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
LEGACY_RE = re.compile(r"\[([^\[\]{}<>]{1,40})\]")
SAFE_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20}|rgba?\([0-9.,\s%]+\))$")
UNITLESS_CSS = {"opacity", "fontWeight", "lineHeight", "zIndex", "order", "flexGrow", "flexShrink"}

FIT_SCRIPT = (
	"document.querySelectorAll('.idc-fit').forEach(function(e){"
	"var s=parseFloat(getComputedStyle(e).fontSize)||12,i=0;"
	"while(e.scrollWidth>e.clientWidth+0.5&&s>4&&i<200){s-=0.25;e.style.fontSize=s+'px';i++;}});"
)

SAMPLE_PHOTO = "data:image/svg+xml;utf8," + quote(
	'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 120">'
	'<rect width="100" height="120" fill="#dfe6ee"/>'
	'<circle cx="50" cy="45" r="22" fill="#9aa9bb"/>'
	'<path d="M10 120c4-26 20-40 40-40s36 14 40 40z" fill="#9aa9bb"/></svg>'
)


# ----------------------------------------------------------------------
# Tokens and values
# ----------------------------------------------------------------------


def canonical_key(key):
	key = (key or "").strip()
	return MAPPING_ALIASES.get(key, key)


def _get(obj, key):
	if obj is None:
		return None
	getter = getattr(obj, "get", None)
	if callable(getter):
		return getter(key)
	return getattr(obj, key, None)


def _fmt_date(value):
	return format_date(value) if value else ""


def get_token_values(card, template, person):
	"""Text values for every token, for one card."""
	card_type = card.card_type or "Student"
	person_id = {
		"Student": _get(person, "registration_id") or card.student,
		"Faculty": _get(person, "faculty_id") or card.faculty,
		"Driver": _get(person, "driver_id") or card.driver,
	}.get(card_type)

	address = _get(person, "present_address") or _get(person, "permanent_address")
	if not address:
		address = ", ".join(filter(None, [_get(person, "city"), _get(person, "state")]))

	blood_group = _get(person, "blood_group")
	if blood_group == "N/A":
		blood_group = ""

	values = {
		"student_name": card.student_name or _get(person, "full_name") or _get(person, "first_name"),
		"student_id": person_id or card.name,
		"designation": card.designation,
		"department": card.department,
		"programme": card.programme or _get(person, "programme_of_study"),
		"batch": card.batch or _get(person, "batch"),
		"academic_year": card.academic_year or _get(person, "academic_year"),
		"blood_group": blood_group,
		"date_of_birth": _fmt_date(card.date_of_birth or _get(person, "dob")),
		"email": card.email,
		"phone": card.phone,
		"address": address,
		"license_number": _get(person, "license_number"),
		"company": card.visitor_company,
		"purpose": card.remarks if card_type == "Visitor" else "",
		"card_number": card.name,
		"issue_date": _fmt_date(card.issue_date),
		"expiry_date": _fmt_date(card.expiry_date),
		"validity_text": template.validity_text,
		"institute_name": template.institute_name,
		"institute_address": template.institute_address,
	}
	return {k: ("" if v is None else str(v)) for k, v in values.items()}


def get_sample_person(card_type):
	"""A stand-in person used when previewing without real data."""
	samples = {key: sample for key, _label, _group, _types, sample in TEXT_TOKENS if sample}
	return frappe._dict(
		{
			"first_name": samples["student_name"],
			"full_name": samples["student_name"],
			"registration_id": samples["student_id"],
			"faculty_id": "FAC-1042",
			"driver_id": "DRV-0007",
			"blood_group": samples["blood_group"],
			"dob": "2007-08-15",
			"present_address": samples["address"],
			"license_number": samples["license_number"],
			"programme_of_study": samples["programme"],
			"batch": samples["batch"],
			"academic_year": samples["academic_year"],
			"email": samples["email"],
			"phone": samples["phone"],
			"designation": samples["designation"],
			"department": samples["department"],
			"company": samples["company"],
		}
	)


def apply_sample_to_card(card, template):
	person = get_sample_person(card.card_type)
	card.student_name = person.full_name
	card.email = person.email
	card.phone = person.phone
	card.programme = person.programme_of_study
	card.batch = person.batch
	card.academic_year = person.academic_year
	card.date_of_birth = person.dob
	card.designation = person.designation if card.card_type != "Student" else None
	card.department = person.department if card.card_type in ("Faculty", "Non-Faculty") else None
	card.visitor_company = person.company if card.card_type in ("Visitor", "Non-Faculty") else None
	if card.card_type == "Visitor":
		card.remarks = "Guest lecture"
	card.issue_date = today()
	card.expiry_date = add_years(today(), 1)
	return person


@frappe.whitelist()
def get_designer_meta(card_type=None):
	"""Field palette for the designer: every token with a label and sample."""
	card_type = card_type or "Student"
	sample_card = frappe._dict(
		{
			"card_type": card_type,
			"issue_date": today(),
			"expiry_date": add_years(today(), 1),
			"date_of_birth": "2007-08-15",
		}
	)
	tokens = []
	for key, label, group, types, sample in TEXT_TOKENS:
		if types and card_type not in types:
			continue
		if key == "student_name":
			label = NAME_LABELS.get(card_type, label)
		elif key == "student_id":
			label = ID_LABELS.get(card_type, label)
		if sample is None:
			sample = _fmt_date(sample_card.get(key))
		tokens.append({"key": key, "label": label, "group": group, "kind": "text", "sample": sample})
	for key, label, group in IMAGE_TOKENS:
		tokens.append({"key": key, "label": label, "group": group, "kind": "image"})

	return {
		"card_type": card_type,
		"tokens": tokens,
		"all_text_keys": [t[0] for t in TEXT_TOKENS],
		"labels": {t[0]: t[1] for t in TEXT_TOKENS},
		"samples": {
			t[0]: t[4] if t[4] is not None else _fmt_date(sample_card.get(t[0])) for t in TEXT_TOKENS
		},
		"legacy_aliases": LEGACY_ALIASES,
		"mapping_aliases": MAPPING_ALIASES,
		"person_doctype": PERSON_LINKS.get(card_type, (None, None))[1],
		"card_units": CARD_UNITS,
	}


def fill_text(content, values, mapping=None):
	"""Replace {{tokens}} and legacy [Label] placeholders with escaped values.

	The surrounding content is authored by template managers and is trusted
	HTML; only the substituted person data is escaped."""

	def token(m):
		key = canonical_key(m.group(1))
		if key in values:
			return html.escape(values[key])
		return m.group(0)

	def legacy(m):
		key = LEGACY_ALIASES.get(m.group(1).strip().lower())
		if not key and mapping:
			key = canonical_key(mapping)
		if key and key in values:
			return html.escape(values[key])
		return m.group(0)

	return LEGACY_RE.sub(legacy, TOKEN_RE.sub(token, content or ""))


def find_unknown_tokens(data):
	"""Placeholders in a design that no data field resolves."""
	known = {t[0] for t in TEXT_TOKENS}
	unknown = set()
	for side in ("front", "back"):
		for el in data.get(side) or []:
			if el.get("type") != "text":
				continue
			content = el.get("content") or ""
			for m in TOKEN_RE.finditer(content):
				if canonical_key(m.group(1)) not in known:
					unknown.add(m.group(0))
			for m in LEGACY_RE.finditer(content):
				alias = LEGACY_ALIASES.get(m.group(1).strip().lower())
				if not alias and not el.get("mapping"):
					unknown.add(m.group(0))
	return sorted(unknown)


# ----------------------------------------------------------------------
# Files
# ----------------------------------------------------------------------


def get_file_path(file_url):
	"""Absolute disk path for a /files, /private/files or /assets URL.
	Remote (http) URLs are returned unchanged."""
	if not file_url:
		return None
	if file_url.startswith(("http://", "https://", "data:")):
		return file_url

	path = None
	if file_url.startswith("/assets/"):
		asset_path = file_url.replace("/assets/", "", 1)
		full_path = os.path.join(frappe.utils.get_bench_path(), "sites", "assets", asset_path)
		if os.path.exists(full_path):
			path = full_path
		elif "default-avatar.png" in file_url:
			path = frappe.get_app_path("frappe", "public", "images", "default-avatar.png")
	elif file_url.startswith("/private/files/"):
		path = frappe.get_site_path("private", "files", file_url.replace("/private/files/", "", 1))
	elif file_url.startswith("/"):
		path = frappe.get_site_path("public", file_url.lstrip("/"))
	else:
		path = frappe.get_site_path("public", file_url)

	return os.path.abspath(path) if path else None


def to_src(file_url_or_path):
	"""Value usable as <img src> in the file:// page Chromium renders."""
	if not file_url_or_path:
		return ""
	if file_url_or_path.startswith(("http://", "https://", "data:", "file://")):
		return file_url_or_path
	# Site URLs like /private/files/x.png look absolute but are not disk paths.
	is_disk_path = os.path.isabs(file_url_or_path) and not file_url_or_path.startswith(
		("/files/", "/private/files/", "/assets/")
	)
	if not is_disk_path:
		file_url_or_path = get_file_path(file_url_or_path)
	if not file_url_or_path or not os.path.exists(file_url_or_path):
		return ""
	return "file://" + quote(file_url_or_path)


# ----------------------------------------------------------------------
# Canvas → HTML
# ----------------------------------------------------------------------


def parse_canvas_data(raw):
	if not raw:
		return None
	data = json.loads(raw) if isinstance(raw, str) else raw
	if isinstance(data, dict) and isinstance(data.get("elements"), list):
		data = {"front": data["elements"], "back": []}
	if not isinstance(data, dict):
		raise ValueError("Canvas data must be an object")
	data.setdefault("front", [])
	data.setdefault("back", [])
	if data.get("orientation") not in CARD_UNITS:
		data["orientation"] = "horizontal"
	if not isinstance(data.get("bg_color"), dict):
		data["bg_color"] = {"front": "#ffffff", "back": "#ffffff"}
	return data


def visible_elements(data, side):
	return [el for el in (data.get(side) or []) if isinstance(el, dict) and not el.get("hidden")]


def _num(value, default=0.0):
	try:
		return float(str(value).replace("px", ""))
	except (TypeError, ValueError):
		return default


def style_to_css(style):
	"""camelCase style dict → CSS declarations, mirroring jQuery's .css()."""
	parts = []
	for key, value in (style or {}).items():
		if value is None or value == "" or isinstance(value, bool):
			continue
		if not re.fullmatch(r"[A-Za-z]+", key):
			continue
		prop = re.sub(r"([A-Z])", lambda m: "-" + m.group(1).lower(), key)
		if prop.startswith("webkit-"):
			prop = "-" + prop
		if isinstance(value, (int, float)) and key not in UNITLESS_CSS:
			value = f"{value}px"
		value = str(value)
		if any(ch in value for ch in ';{}<>"\\'):
			continue
		parts.append(f"{prop}: {value}")
	return "; ".join(parts)


def element_html(el, values, images):
	el_type = el.get("type")
	x, y = _num(el.get("x")), _num(el.get("y"))
	css = f"position: absolute; left: {x}px; top: {y}px;"
	style = el.get("style") or {}

	if el_type == "text":
		classes = "idc-el"
		css += " white-space: normal;" if el.get("wrap") else " white-space: nowrap;"
		if el.get("width"):
			css += f" width: {_num(el.get('width'))}px;"
			if el.get("fit") and not el.get("wrap"):
				classes += " idc-fit"
				css += " overflow: hidden;"
		css += " " + style_to_css(style)
		content = fill_text(el.get("content"), values, el.get("mapping"))
		return f'<div class="{classes}" style="{html.escape(css)}">{content}</div>'

	w, h = _num(el.get("width")), _num(el.get("height"))
	css += f" width: {w}px; height: {h}px;"

	if el_type == "image":
		css += " overflow: hidden; " + style_to_css(style)
		mapping = canonical_key(el.get("mapping"))
		src = images.get(mapping, "") if mapping else to_src(el.get("content"))
		fit = el.get("object_fit") if el.get("object_fit") in ("cover", "contain", "fill") else "cover"
		inner = ""
		if src:
			inner = (
				f'<img src="{html.escape(src)}" style="width: 100%; height: 100%; '
				f'object-fit: {fit}; display: block;">'
			)
		return f'<div class="idc-el" style="{html.escape(css)}">{inner}</div>'

	if el_type == "rect":
		css += " " + style_to_css(style)
		return f'<div class="idc-el" style="{html.escape(css)}"></div>'

	return ""


def build_canvas_html(data, side, values, images):
	width, height = CARD_UNITS[data["orientation"]]
	bg = (data.get("bg_color") or {}).get(side) or "#ffffff"
	if not SAFE_COLOR_RE.match(bg):
		bg = "#ffffff"
	body = "".join(element_html(el, values, images) for el in visible_elements(data, side))
	return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; padding: 0; background: {bg}; }}
.idc-card {{ position: relative; width: {width}px; height: {height}px; overflow: hidden; background: {bg};
	font-family: Arial, Helvetica, sans-serif; font-size: 16px; line-height: normal; color: #000; text-align: left; }}
.idc-card * {{ box-sizing: border-box; }}
</style></head>
<body><div class="idc-card">{body}</div><script>{FIT_SCRIPT}</script></body></html>"""


# ----------------------------------------------------------------------
# Chromium
# ----------------------------------------------------------------------


def screenshot_html(html_content, width, height, scale=1):
	"""Render an HTML page to PNG bytes of exactly (width*scale, height*scale)."""
	from frappe.utils.print_utils import find_or_download_chromium_executable
	from PIL import Image

	chrome_path = find_or_download_chromium_executable()
	if not chrome_path:
		frappe.throw(_("Chromium executable not found. Cannot render ID card image."))

	with tempfile.TemporaryDirectory(prefix="idcard-") as tmp:
		html_path = os.path.join(tmp, "card.html")
		output_path = os.path.join(tmp, "card.png")
		with open(html_path, "w", encoding="utf-8") as f:
			f.write(html_content)

		args = [
			chrome_path,
			"--headless",
			"--disable-gpu",
			"--no-sandbox",
			"--disable-dev-shm-usage",
			"--hide-scrollbars",
			f"--force-device-scale-factor={scale}",
			f"--window-size={int(-(-width // 1))},{int(-(-height // 1))}",
			"--virtual-time-budget=5000",
			f"--screenshot={output_path}",
			"file://" + quote(html_path),
		]
		try:
			result = subprocess.run(args, capture_output=True, text=True, timeout=120)
		except subprocess.TimeoutExpired:
			frappe.throw(_("Chromium timed out while rendering the ID card."))

		if result.returncode != 0 or not os.path.exists(output_path):
			frappe.throw(_("Chromium failed to render the ID card: {0}").format((result.stderr or "")[-500:]))

		target = (round(width * scale), round(height * scale))
		img = Image.open(output_path)
		if img.size != target:
			img = img.crop((0, 0, min(target[0], img.width), min(target[1], img.height)))
		buf = io.BytesIO()
		img.save(buf, format="PNG", dpi=(300, 300))
		return buf.getvalue()


def render_canvas_side(data, side, values, images):
	width, height = CARD_UNITS[data["orientation"]]
	return screenshot_html(build_canvas_html(data, side, values, images), width, height, RENDER_SCALE)


def make_qr_png(payload):
	import qrcode

	qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
	qr.add_data(payload or "ID CARD")
	qr.make(fit=True)
	buf = io.BytesIO()
	qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
	return buf.getvalue()

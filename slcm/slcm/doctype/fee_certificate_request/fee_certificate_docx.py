# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Word (.docx) version of the Fee Certificate, built from the same context as the
PDF print format so both always carry the same wording and figures."""

import base64
import re
from html import unescape
from html.parser import HTMLParser
from io import BytesIO

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt

FONT = "Cambria"
PAGE_MARGIN = Mm(15)
CONTENT_WIDTH = Mm(210 - 30)


class _Paragraphs(HTMLParser):
	"""Rich-text HTML (<p>, <strong>/<b>, <br>) → [[(text, bold), ...], ...]."""

	def __init__(self):
		super().__init__()
		self.paragraphs, self.current, self.bold = [], [], 0

	def handle_starttag(self, tag, attrs):
		if tag in ("strong", "b"):
			self.bold += 1
		elif tag == "br":
			self.current.append(("\n", False))
		elif tag in ("p", "div") and self.current:
			self._flush()

	def handle_endtag(self, tag):
		if tag in ("strong", "b"):
			self.bold = max(self.bold - 1, 0)
		elif tag in ("p", "div"):
			self._flush()

	def handle_data(self, data):
		if data:
			self.current.append((data, self.bold > 0))

	def _flush(self):
		if "".join(t for t, _b in self.current).strip():
			self.paragraphs.append(self.current)
		self.current = []

	def close(self):
		super().close()
		self._flush()
		return self.paragraphs


def _paragraphs(html):
	# The bank table is added as a real table, so drop it from the text.
	html = re.sub(r"<table.*?</table>", "", html or "", flags=re.S)
	parser = _Paragraphs()
	parser.feed(html)
	return parser.close()


def _style(run, bold=False, size=12, underline=False):
	run.bold = bold
	run.underline = underline
	run.font.size = Pt(size)
	run.font.name = FONT
	run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)


def _spacing(paragraph, after=6, line=1.5):
	fmt = paragraph.paragraph_format
	fmt.space_before = Pt(0)
	fmt.space_after = Pt(after)
	fmt.line_spacing = line


def _image(b64):
	return BytesIO(base64.b64decode(b64))


def _cell_text(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT, size=11):
	cell.text = ""
	p = cell.paragraphs[0]
	p.alignment = align
	_spacing(p, after=0, line=1.15)
	_style(p.add_run(text), bold=bold, size=size)


def _no_borders(table):
	borders = OxmlElement("w:tblBorders")
	for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
		el = OxmlElement(f"w:{edge}")
		el.set(qn("w:val"), "nil")
		borders.append(el)
	table._tbl.tblPr.append(borders)


def build_certificate_docx(ctx):
	"""ctx: fee_certificate_request.get_fee_certificate_context(...) result."""
	settings, table = ctx["settings"], ctx["table"]
	doc = Document()

	section = doc.sections[0]
	section.page_width, section.page_height = Mm(210), Mm(297)
	for side in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
		setattr(section, side, PAGE_MARGIN)
	section.header_distance = section.footer_distance = Mm(8)

	normal = doc.styles["Normal"]
	normal.font.name = FONT
	normal.font.size = Pt(12)
	normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

	# Letterhead: header / footer images repeat on every page, as on the letterhead paper.
	header_p = section.header.paragraphs[0]
	if ctx.get("header_image"):
		stream = _image(ctx["header_image"])
		header_p.add_run().add_picture(stream, width=CONTENT_WIDTH)
	else:
		header_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
		_style(header_p.add_run(settings.get("institute_name") or ""), bold=True, size=16)
		if settings.get("institute_address"):
			_style(section.header.add_paragraph().add_run(settings.institute_address), size=9)
	footer_p = section.footer.paragraphs[0]
	if ctx.get("footer_image"):
		stream = _image(ctx["footer_image"])
		footer_p.add_run().add_picture(stream, width=CONTENT_WIDTH)
	elif settings.get("footer_note"):
		footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
		_style(footer_p.add_run(settings.footer_note), size=8)

	body = doc.add_paragraph()
	body.alignment = WD_ALIGN_PARAGRAPH.RIGHT
	_spacing(body, after=6)
	_style(body.add_run(ctx["generation_date"]))

	title = doc.add_paragraph()
	title.alignment = WD_ALIGN_PARAGRAPH.CENTER
	_spacing(title, after=8)
	_style(title.add_run(ctx["heading"]), bold=True, size=13, underline=True)

	for runs in _paragraphs(ctx.get("body_html")):
		p = doc.add_paragraph()
		p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
		_spacing(p, after=8)
		for text, bold in runs:
			_style(p.add_run(unescape(text)), bold=bold)

	# Fee table
	n_years = len(table["year_labels"])
	grid = doc.add_table(rows=1, cols=2 + n_years)
	grid.style = "Table Grid"
	grid.alignment = WD_TABLE_ALIGNMENT.CENTER
	for i, label in enumerate(["Sl. No.", "Particulars", *table["year_labels"]]):
		_cell_text(grid.rows[0].cells[i], label, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)

	def add_row(sl, label, amounts, bold=False):
		cells = grid.add_row().cells
		_cell_text(cells[0], sl, align=WD_ALIGN_PARAGRAPH.CENTER)
		_cell_text(cells[1], label, bold=bold)
		for i, amount in enumerate(amounts):
			_cell_text(cells[2 + i], amount, bold=bold, align=WD_ALIGN_PARAGRAPH.RIGHT)

	for i, row in enumerate(table["rows"], 1):
		add_row(str(i), row["particulars"], row["amounts"])
	if table.get("show_scholarship_row"):
		add_row("", "Total Course Fee", table["total_row"], bold=True)
		add_row(
			"",
			"Less: University Scholarship",
			[a if a == "-" else f"({a})" for a in table["scholarship_row"]],
		)
		add_row("", ctx["total_label"], table["net_row"], bold=True)
	else:
		add_row("", ctx["total_label"], table["total_row"], bold=True)
	if table.get("show_paid_rows"):
		add_row("", table["paid_row_label"], table["paid_row"], bold=True)
		add_row("", table["outstanding_row_label"], table["outstanding_row"], bold=True)

	widths = [Mm(16), Mm(180 - 16 - 22 * n_years if n_years > 1 else 120)] + [
		Mm(22 if n_years > 1 else 44)
	] * n_years
	for row in grid.rows:
		for cell, width in zip(row.cells, widths):
			cell.width = width
	_spacing(doc.add_paragraph(), after=4)

	# Bank details: the intro text, then the label / value list as a borderless table.
	if ctx.get("bank_details_html"):
		for runs in _paragraphs(ctx["bank_details_html"]):
			p = doc.add_paragraph()
			p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
			_spacing(p, after=4)
			for text, bold in runs:
				_style(p.add_run(unescape(text)), bold=bold)
		bank_rows = [
			(label, value)
			for label, value in (
				("Account Holder Name", settings.get("bank_account_name") or settings.get("institute_name")),
				("Account Number", settings.get("bank_account_no")),
				("IFSC", settings.get("bank_ifsc_code")),
				("Bank Name", settings.get("bank_name")),
				("Branch", settings.get("bank_branch")),
				("Account Type", settings.get("bank_account_type")),
			)
			if value
		]
		# Only when the purpose's bank text uses the list (as the PDF does).
		if "bank_table" in (ctx.get("bank_details_source") or "") and bank_rows:
			bank = doc.add_table(rows=0, cols=2)
			_no_borders(bank)
			for label, value in bank_rows:
				cells = bank.add_row().cells
				_cell_text(cells[0], label)
				_cell_text(cells[1], value)
				cells[0].width, cells[1].width = Mm(50), Mm(130)

	for runs in _paragraphs(ctx.get("closing_html")):
		p = doc.add_paragraph()
		_spacing(p, after=6)
		for text, bold in runs:
			_style(p.add_run(unescape(text)), bold=bold)

	# Signature
	sign = doc.add_paragraph()
	sign.alignment = WD_ALIGN_PARAGRAPH.RIGHT
	_spacing(sign, after=0, line=1.0)
	sign.paragraph_format.space_before = Pt(18)
	if ctx.get("signature_image"):
		stream = _image(ctx["signature_image"])
		sign.add_run().add_picture(stream, height=Mm(24))
	if not (ctx.get("signature_image") and settings.get("signature_includes_designation")):
		for line, bold in ((settings.get("cfo_designation") or "Chief Finance Officer", True), (settings.get("institute_name") or "", False)):
			p = doc.add_paragraph()
			p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
			_spacing(p, after=0, line=1.0)
			_style(p.add_run(line), bold=bold, size=11)

	out = BytesIO()
	doc.save(out)
	return out.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Word → PDF (staff upload an edited .docx; it is stored as the certificate PDF)
# ─────────────────────────────────────────────────────────────────────────────


def docx_to_pdf(content):
	"""PDF bytes for an uploaded .docx: LibreOffice when installed (exact layout),
	else our own HTML rendering of the document through wkhtmltopdf."""
	import shutil

	soffice = shutil.which("soffice") or shutil.which("libreoffice")
	if soffice:
		pdf = _libreoffice_pdf(soffice, content)
		if pdf:
			return pdf
	from frappe.utils.pdf import get_pdf

	# Frappe's PDF helper keeps a 15mm margin on every side (as the generated certificate).
	return get_pdf(_docx_html(content), {"margin-left": "15mm", "margin-right": "15mm"})


def _libreoffice_pdf(soffice, content):
	import os
	import subprocess
	import tempfile

	with tempfile.TemporaryDirectory() as tmp:
		src = os.path.join(tmp, "certificate.docx")
		with open(src, "wb") as f:
			f.write(content)
		try:
			subprocess.run(
				[soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, src],
				check=True,
				timeout=120,
				capture_output=True,
			)
		except Exception:
			return None
		out = os.path.join(tmp, "certificate.pdf")
		return open(out, "rb").read() if os.path.exists(out) else None


_ALIGN = {0: "left", 1: "center", 2: "right", 3: "justify"}
# wkhtmltopdf renders CSS at ~0.75 scale (see the Fee Certificate print format; the
# patched-Qt build is zoomed to match), so real millimetres from the .docx are divided by this.
_SCALE = 0.75


def _esc(text):
	from html import escape

	return escape(text or "").replace("\n", "<br>")


def _run_html(run, part):
	from docx.oxml.ns import qn as _qn

	html = ""
	for blip in run._element.iter(_qn("a:blip")):
		rid = blip.get(_qn("r:embed"))
		image = part.related_parts.get(rid) if rid else None
		if image is None:
			continue
		extent = next(run._element.iter(_qn("wp:extent")), None)
		width_mm = int(extent.get("cx")) / 36000 if extent is not None else None
		style = f"width:{width_mm / _SCALE:.1f}mm;" if width_mm else "max-width:100%;"
		mime = getattr(image, "content_type", "image/png")
		html += f'<img src="data:{mime};base64,{base64.b64encode(image.blob).decode()}" style="{style}">'
	text = run.text
	if text:
		css = []
		if run.bold:
			css.append("font-weight:bold")
		if run.italic:
			css.append("font-style:italic")
		if run.underline:
			css.append("text-decoration:underline")
		if run.font.size:
			css.append(f"font-size:{run.font.size.pt}pt")
		html += f'<span style="{";".join(css)}">{_esc(text)}</span>' if css else _esc(text)
	return html


def _paragraph_html(paragraph, part, tag="p"):
	align = paragraph.alignment
	style = f"text-align:{_ALIGN.get(int(align), 'left')};" if align is not None else ""
	inner = "".join(_run_html(r, part) for r in paragraph.runs) or "&nbsp;"
	return f'<{tag} style="{style}">{inner}</{tag}>'


def _border_edges(tbl_pr):
	"""{edge: has_line} from a <w:tblPr>'s <w:tblBorders>; {} when none are set
	(editors such as Word Online write an empty tag that means "use the style")."""
	from docx.oxml.ns import qn as _qn

	borders = tbl_pr.find(_qn("w:tblBorders")) if tbl_pr is not None else None
	if borders is None:
		return {}
	return {
		el.tag.split("}")[-1]: el.get(_qn("w:val")) not in ("nil", "none", None)
		for el in borders
	}


def _table_has_borders(table):
	"""Direct table borders, else the table style's (following basedOn)."""
	from docx.oxml.ns import qn as _qn

	edges = _border_edges(table._tbl.tblPr)
	style = table.style
	seen = set()
	while not edges and style is not None and style.style_id not in seen:
		seen.add(style.style_id)
		edges = _border_edges(style.element.find(_qn("w:tblPr")))
		style = style.base_style
	return any(edges.values()) if edges else False


def _table_html(table, part):
	cls = "grid" if _table_has_borders(table) else "plain"
	rows = []
	for row in table.rows:
		cells = []
		for cell in row.cells:
			width = f"width:{cell.width.mm / _SCALE:.1f}mm;" if cell.width else ""
			content = "".join(_paragraph_html(p, part, "div") for p in cell.paragraphs)
			cells.append(f'<td style="{width}">{content}</td>')
		rows.append("<tr>" + "".join(cells) + "</tr>")
	return f'<table class="{cls}">{"".join(rows)}</table>'


def _docx_html(content):
	from docx.oxml.ns import qn as _qn
	from docx.table import Table
	from docx.text.paragraph import Paragraph

	doc = Document(BytesIO(content))
	section = doc.sections[0]

	def block_html(element, proxy, part):
		out = []
		for child in element.iterchildren():
			if child.tag == _qn("w:p"):
				out.append(_paragraph_html(Paragraph(child, proxy), part))
			elif child.tag == _qn("w:tbl"):
				out.append(_table_html(Table(child, proxy), part))
		return "".join(out)

	header = block_html(section.header._element, section.header, section.header.part)
	footer = block_html(section.footer._element, section.footer, section.footer.part)
	body = block_html(doc.element.body, doc._body, doc.part)
	# One A4 page inside the 15mm margins: 267mm high on paper, 346mm in CSS here
	# (same box as the Fee Certificate print format); the footer sits at its bottom.
	# The patched-Qt build lays CSS out 1:1, so it is zoomed to the same 0.75.
	from slcm.slcm.doctype.fee_certificate_request.fee_certificate_request import pdf_true_scale

	zoom = "zoom:0.75; height:352mm;" if pdf_true_scale() else ""
	return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
		html, body {{ margin:0; padding:0; }}
		body {{ font-family: Cambria, Georgia, "Times New Roman", serif; font-size:12pt; line-height:1.5; color:#000; }}
		.page {{ position:relative; height:346mm; overflow:hidden; {zoom} }}
		.page img {{ max-width:100%; }}
		p {{ margin:0 0 6pt; }}
		table {{ border-collapse:collapse; width:100%; margin:0 0 8pt; line-height:1.3; }}
		table.grid td {{ border:1px solid #000; padding:3pt 5pt; }}
		table.plain {{ width:auto; }}
		table.plain td {{ border:none; padding:0 18pt 0 0; }}
		.footer {{ position:absolute; left:0; right:0; bottom:0; }}
		.header {{ margin-bottom:6pt; }}
	</style></head><body><div class="page">
		<div class="header">{header}</div>
		<div class="content">{body}</div>
		<div class="footer">{footer}</div>
	</div></body></html>"""

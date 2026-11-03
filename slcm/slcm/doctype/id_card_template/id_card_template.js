/* global slcm */
frappe.provide("slcm.id_card");

// Design units: a landscape CR80 card is 337 x 212.5 (≈ 0.254 mm per unit).
// The server renders the same layout at 3x, so the designer is WYSIWYG.
const IDC_UNITS = { horizontal: [337, 212.5], vertical: [212.5, 337] };
const IDC_MM = { horizontal: "85.6 × 54 mm", vertical: "54 × 85.6 mm" };
const IDC_SAFE = 8;
const IDC_FONTS = [
	["Arial, Helvetica, sans-serif", "Arial"],
	["Helvetica, Arial, sans-serif", "Helvetica"],
	["Verdana, sans-serif", "Verdana"],
	["Tahoma, sans-serif", "Tahoma"],
	["'Trebuchet MS', sans-serif", "Trebuchet MS"],
	["Georgia, serif", "Georgia"],
	["'Times New Roman', serif", "Times New Roman"],
	["Garamond, serif", "Garamond"],
	["'Courier New', monospace", "Courier New"],
];
const IDC_IMAGE_SOURCES = [
	["", "Uploaded image"],
	["photo", "Person photo"],
	["qr_code_image", "QR code"],
	["institute_logo", "Institute logo"],
	["authority_signature", "Authority signature"],
	["watermark_image", "Watermark"],
];

// ---------------------------------------------------------------------
// Shared helpers (designer, thumbnails, preview)
// ---------------------------------------------------------------------

slcm.id_card.icon = function (name, size = 16) {
	const paths = {
		text: '<path d="M4 7V4h16v3M9 20h6M12 4v16"/>',
		heading: '<path d="M6 4v16M18 4v16M6 12h12"/>',
		paragraph: '<path d="M4 6h16M4 10h16M4 14h16M4 18h10"/>',
		image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
		square: '<rect x="3" y="5" width="18" height="14" rx="2"/>',
		circle: '<circle cx="12" cy="12" r="9"/>',
		line: '<path d="M4 12h16"/>',
		header: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/>',
		footer: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 15h18"/>',
		droplet:
			'<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5S12.5 5.5 12 3c-.5 2.5-2 4.9-4 6.5S5 13 5 15a7 7 0 0 0 7 7z"/>',
		user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>',
		qr: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM18 18h3v3h-3zM14 20h2M20 14v2"/>',
		building:
			'<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/>',
		pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
		layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
		eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
		"eye-off":
			'<path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6C3.9 8.4 2 12 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6"/>',
		lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
		unlock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.9-1"/>',
		trash: '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>',
		copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M4 16V5a2 2 0 0 1 2-2h11"/>',
		undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
		redo: '<path d="m15 14 5-5-5-5"/><path d="M20 9H9a5 5 0 0 0 0 10h3"/>',
		"zoom-in": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3M11 8v6M8 11h6"/>',
		"zoom-out": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3M8 11h6"/>',
		guides: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M12 3v18M3 12h18"/>',
		magnet: '<path d="M6 4v8a6 6 0 0 0 12 0V4"/><path d="M6 8h4V4M14 4v4h4"/>',
		braces: '<path d="M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5a2 2 0 0 0 2 2h1M16 21h1a2 2 0 0 0 2-2v-5a2 2 0 0 1 2-2 2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h-1"/>',
		check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
		alert: '<path d="M12 3 2 21h20z"/><path d="M12 10v5M12 18h.01"/>',
		info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
		templates:
			'<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
		upload: '<path d="M12 15V3M7 8l5-5 5 5"/><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>',
		plus: '<path d="M12 5v14M5 12h14"/>',
		grip: '<circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/>',
		"align-left":
			'<path d="M4 3v18"/><rect x="8" y="6" width="12" height="4" rx="1"/><rect x="8" y="14" width="7" height="4" rx="1"/>',
		"align-hcenter":
			'<path d="M12 3v18"/><rect x="5" y="6" width="14" height="4" rx="1"/><rect x="8" y="14" width="8" height="4" rx="1"/>',
		"align-right":
			'<path d="M20 3v18"/><rect x="4" y="6" width="12" height="4" rx="1"/><rect x="9" y="14" width="7" height="4" rx="1"/>',
		"align-top":
			'<path d="M3 4h18"/><rect x="6" y="8" width="4" height="12" rx="1"/><rect x="14" y="8" width="4" height="7" rx="1"/>',
		"align-vmiddle":
			'<path d="M3 12h18"/><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="8" width="4" height="8" rx="1"/>',
		"align-bottom":
			'<path d="M3 20h18"/><rect x="6" y="4" width="4" height="12" rx="1"/><rect x="14" y="9" width="4" height="7" rx="1"/>',
		"text-left": '<path d="M4 6h16M4 10h10M4 14h16M4 18h10"/>',
		"text-center": '<path d="M4 6h16M7 10h10M4 14h16M7 18h10"/>',
		"text-right": '<path d="M4 6h16M10 10h10M4 14h16M10 18h10"/>',
		"to-front": '<path d="M5 3h14M12 21V7M6 13l6-6 6 6"/>',
		"to-back": '<path d="M5 21h14M12 3v14M6 11l6 6 6-6"/>',
		forward: '<path d="m6 15 6-6 6 6"/>',
		backward: '<path d="m6 9 6 6 6-6"/>',
		swap: '<path d="M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7"/>',
	};
	return `<svg class="idc-icon" viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${
		paths[name] || ""
	}</svg>`;
};

slcm.id_card._meta_cache = {};
slcm.id_card.get_meta = function (card_type) {
	card_type = card_type || "Student";
	if (!slcm.id_card._meta_cache[card_type]) {
		slcm.id_card._meta_cache[card_type] = frappe
			.xcall("slcm.slcm.utils.id_card_render.get_designer_meta", { card_type })
			.catch((e) => {
				delete slcm.id_card._meta_cache[card_type];
				throw e;
			});
	}
	return slcm.id_card._meta_cache[card_type];
};

slcm.id_card.canonical = (meta, key) => (meta.mapping_aliases || {})[key] || key;

// Mirrors id_card_render.fill_text on the server.
slcm.id_card.fill_text = function (content, values, mapping, meta) {
	const esc = frappe.utils.escape_html;
	let out = (content || "").replace(/\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g, (m, key) => {
		key = slcm.id_card.canonical(meta, key);
		return key in values ? esc(values[key]) : m;
	});
	out = out.replace(/\[([^\[\]{}<>]{1,40})\]/g, (m, label) => {
		let key = meta.legacy_aliases[label.trim().toLowerCase()];
		if (!key && mapping) key = slcm.id_card.canonical(meta, mapping);
		return key && key in values ? esc(values[key]) : m;
	});
	return out;
};

slcm.id_card.unknown_tokens = function (content, mapping, meta) {
	const known = new Set(meta.all_text_keys);
	const unknown = [];
	(content || "").replace(/\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g, (m, key) => {
		if (!known.has(slcm.id_card.canonical(meta, key))) unknown.push(m);
		return m;
	});
	(content || "").replace(/\[([^\[\]{}<>]{1,40})\]/g, (m, label) => {
		if (!meta.legacy_aliases[label.trim().toLowerCase()] && !mapping) unknown.push(m);
		return m;
	});
	return unknown;
};

// Same filtering as id_card_render.style_to_css, so both render alike.
slcm.id_card.clean_style = function (style) {
	const out = {};
	Object.entries(style || {}).forEach(([key, value]) => {
		if (value === null || value === undefined || value === "" || typeof value === "boolean")
			return;
		if (!/^[A-Za-z]+$/.test(key)) return;
		if (/[;{}<>"\\]/.test(String(value))) return;
		out[key] = value;
	});
	return out;
};

slcm.id_card.placeholder = function (kind) {
	const svgs = {
		photo: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 120"><rect width="100" height="120" fill="#dfe6ee"/><circle cx="50" cy="45" r="22" fill="#9aa9bb"/><path d="M10 120c4-26 20-40 40-40s36 14 40 40z" fill="#9aa9bb"/></svg>',
		qr_code_image:
			'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 21 21" shape-rendering="crispEdges"><rect width="21" height="21" fill="#fff"/><path fill="#111" d="M0 0h7v7H0zM1 1v5h5V1zM2 2h3v3H2zM14 0h7v7h-7zM15 1v5h5V1zM16 2h3v3h-3zM0 14h7v7H0zM1 15v5h5v-5zM2 16h3v3H2zM9 0h2v2H9zM9 3h1v3H9zM11 4h2v2h-2zM8 8h3v1H8zM12 8h1v3h-1zM14 9h2v1h-2zM17 8h3v2h-3zM9 10h2v2H9zM0 9h2v2H0zM3 8h2v3H3zM14 12h3v2h-3zM18 12h3v1h-3zM9 14h2v3H9zM12 15h3v2h-3zM16 15h2v3h-2zM19 15h2v2h-2zM12 18h2v3h-2zM15 19h3v2h-3zM19 18h2v3h-2z"/></svg>',
		institute_logo:
			'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 60"><circle cx="30" cy="30" r="28" fill="#e8edf5" stroke="#9aa9bb" stroke-width="2"/><text x="30" y="35" font-family="Arial" font-size="13" font-weight="bold" text-anchor="middle" fill="#64748b">LOGO</text></svg>',
		authority_signature:
			'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 40"><path d="M8 28c10-18 18-20 20-10s4 10 12-4 10 8 18 2 10-10 16 0 14 2 20-4" fill="none" stroke="#334155" stroke-width="2.5" stroke-linecap="round"/></svg>',
		watermark_image:
			'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="46" fill="none" stroke="#94a3b8" stroke-width="4"/><circle cx="50" cy="50" r="30" fill="none" stroke="#94a3b8" stroke-width="3"/></svg>',
		image: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" fill="#eef2f7"/><path d="M5 17l4-5 3 3 2-2 5 4z" fill="#9aa9bb"/><circle cx="9" cy="8" r="2" fill="#9aa9bb"/></svg>',
	};
	return "data:image/svg+xml;utf8," + encodeURIComponent(svgs[kind] || svgs.image);
};

/** Build one element's DOM. Mirrors id_card_render.element_html. */
slcm.id_card.build_element = function (el, ctx) {
	const $el = $('<div class="idc-el"></div>');
	const base = { position: "absolute", left: (+el.x || 0) + "px", top: (+el.y || 0) + "px" };
	const style = slcm.id_card.clean_style(el.style);

	if (el.type === "text") {
		base.whiteSpace = el.wrap ? "normal" : "nowrap";
		if (el.width) {
			base.width = +el.width + "px";
			if (el.fit && !el.wrap) {
				base.overflow = "hidden";
				$el.addClass("idc-fit");
			}
		}
		$el.css(base).css(style);
		$el.html(slcm.id_card.fill_text(el.content, ctx.values, el.mapping, ctx.meta));
	} else if (el.type === "image") {
		base.width = (+el.width || 0) + "px";
		base.height = (+el.height || 0) + "px";
		base.overflow = "hidden";
		$el.css(base).css(style);
		const mapping = el.mapping ? slcm.id_card.canonical(ctx.meta, el.mapping) : null;
		const src = mapping
			? ctx.images[mapping]
			: el.content || slcm.id_card.placeholder("image");
		const fit = ["cover", "contain", "fill"].includes(el.object_fit) ? el.object_fit : "cover";
		if (src) {
			$("<img draggable='false'>")
				.attr("src", src)
				.css({ width: "100%", height: "100%", objectFit: fit, display: "block" })
				.appendTo($el);
		}
	} else if (el.type === "rect") {
		base.width = (+el.width || 0) + "px";
		base.height = (+el.height || 0) + "px";
		$el.css(base).css(style);
	}
	return $el;
};

/** Shrink auto-fit text until it fits its box. Mirrors FIT_SCRIPT. */
slcm.id_card.apply_fit = function ($root) {
	$root.find(".idc-fit").each(function () {
		let size = parseFloat(getComputedStyle(this).fontSize) || 12;
		let i = 0;
		while (this.scrollWidth > this.clientWidth + 0.5 && size > 4 && i < 200) {
			size -= 0.25;
			this.style.fontSize = size + "px";
			i++;
		}
	});
};

slcm.id_card.design_context = function (frm, meta, show_tokens) {
	const values = {};
	(meta.tokens || []).forEach((t) => {
		if (t.kind === "text") values[t.key] = show_tokens ? `‹${t.label}›` : t.sample;
	});
	Object.entries(meta.samples || {}).forEach(([key, sample]) => {
		if (!(key in values))
			values[key] = show_tokens ? `‹${(meta.labels || {})[key] || key}›` : sample;
	});
	if (!show_tokens) {
		["institute_name", "institute_address", "validity_text"].forEach((key) => {
			if (frm && frm.doc[key]) values[key] = frm.doc[key];
		});
	}
	const doc = (frm && frm.doc) || {};
	return {
		meta,
		values,
		images: {
			photo: slcm.id_card.placeholder("photo"),
			qr_code_image: slcm.id_card.placeholder("qr_code_image"),
			institute_logo: doc.institute_logo || slcm.id_card.placeholder("institute_logo"),
			authority_signature:
				doc.authority_signature || slcm.id_card.placeholder("authority_signature"),
			watermark_image: doc.watermark_image || slcm.id_card.placeholder("watermark_image"),
		},
	};
};

slcm.id_card.normalise = function (data, meta) {
	data = data && typeof data === "object" ? data : {};
	if (Array.isArray(data.elements)) data = { front: data.elements, back: [] };
	data.front = Array.isArray(data.front) ? data.front : [];
	data.back = Array.isArray(data.back) ? data.back : [];
	if (!IDC_UNITS[data.orientation]) data.orientation = "horizontal";
	if (!data.bg_color || typeof data.bg_color !== "object") data.bg_color = {};
	data.bg_color.front = data.bg_color.front || "#ffffff";
	data.bg_color.back = data.bg_color.back || "#ffffff";
	[...data.front, ...data.back].forEach((el) => {
		if (el.type !== "text") return;
		// Older designs kept a text box width inside style; it now lives on the element.
		if (el.style && el.style.width && !el.width) {
			el.width = parseFloat(el.style.width) || undefined;
			delete el.style.width;
		}
		// Older designs used "[Label]" placeholders; switch them to {{field}} tokens.
		// The rendered text is identical; the server understands both.
		if (meta && el.content) {
			el.content = el.content.replace(/\[([^\[\]{}<>]{1,40})\]/g, (m, label) => {
				let key = meta.legacy_aliases[label.trim().toLowerCase()];
				if (!key && el.mapping) key = slcm.id_card.canonical(meta, el.mapping);
				return key ? `{{${key}}}` : m;
			});
			if (!/\[[^\[\]{}<>]{1,40}\]/.test(el.content)) delete el.mapping;
		}
	});
	return data;
};

/** A static, scaled rendering of one side (used for thumbnails). */
slcm.id_card.render_thumbnail = function (data, side, ctx, max_w, max_h) {
	const [w, h] = IDC_UNITS[data.orientation];
	const scale = Math.min(max_w / w, max_h / h);
	const $frame = $(
		`<div class="idc-thumb-frame" style="width:${w * scale}px;height:${h * scale}px"></div>`
	);
	const $card = $(
		`<div class="idc-card" style="width:${w}px;height:${h}px;transform:scale(${scale});background:${
			data.bg_color[side] || "#fff"
		}"></div>`
	).appendTo($frame);
	(data[side] || [])
		.filter((el) => !el.hidden)
		.forEach((el) => $card.append(slcm.id_card.build_element(el, ctx)));
	return $frame;
};

slcm.id_card.to_hex = function (color, fallback = "#000000") {
	if (!color) return fallback;
	if (/^#[0-9a-f]{6}$/i.test(color)) return color;
	const ctx = document.createElement("canvas").getContext("2d");
	ctx.fillStyle = fallback;
	ctx.fillStyle = color;
	const out = ctx.fillStyle;
	return /^#[0-9a-f]{6}$/i.test(out) ? out : fallback;
};

slcm.id_card.inject_css = function () {
	if (document.getElementById("idc-studio-css")) return;
	const css = `
	.idc-studio { --idc-border: var(--border-color, #e2e6ea); --idc-muted: var(--text-muted, #6b7280); --idc-bg: var(--fg-color, #fff);
		--idc-subtle: var(--subtle-fg, #f4f5f7); --idc-accent: var(--primary, #2563eb); --idc-text: var(--text-color, #1f2937);
		border: 1px solid var(--idc-border); border-radius: 12px; background: var(--idc-bg); color: var(--idc-text); overflow: hidden; user-select: none; }
	.idc-studio .idc-icon { display: block; flex-shrink: 0; }
	.idc-toolbar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 8px 10px; border-bottom: 1px solid var(--idc-border); background: var(--idc-bg); }
	.idc-toolbar .idc-sep { width: 1px; height: 22px; background: var(--idc-border); margin: 0 4px; }
	.idc-toolbar .idc-spacer { flex: 1; }
	.idc-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 30px; min-width: 30px; padding: 0 8px;
		border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--idc-text); font-size: 12.5px; font-weight: 500; cursor: pointer; white-space: nowrap; }
	.idc-btn:hover:not(:disabled) { background: var(--idc-subtle); }
	.idc-btn:disabled { opacity: .4; cursor: default; }
	.idc-btn.active { background: var(--idc-subtle); border-color: var(--idc-border); color: var(--idc-accent); }
	.idc-btn.primary { background: var(--idc-accent); color: #fff; }
	.idc-btn.primary:hover { filter: brightness(1.08); background: var(--idc-accent); }
	.idc-btn.outline { border-color: var(--idc-border); }
	.idc-btn.danger { color: var(--red-600, #dc2626); }
	.idc-seg { display: inline-flex; padding: 2px; border-radius: 9px; background: var(--idc-subtle); gap: 2px; }
	.idc-seg .idc-btn { height: 26px; border-radius: 7px; }
	.idc-seg .idc-btn.active { background: var(--idc-bg); border-color: transparent; box-shadow: 0 1px 2px rgba(0,0,0,.12); color: var(--idc-text); }
	.idc-count { font-size: 10.5px; color: var(--idc-muted); font-weight: 500; }
	.idc-zoom-label { min-width: 50px; font-variant-numeric: tabular-nums; }
	.idc-health { position: relative; }
	.idc-health .idc-btn.ok { color: var(--green-600, #16a34a); }
	.idc-health .idc-btn.warn { color: var(--orange-600, #ea580c); }
	.idc-health-pop { position: absolute; right: 0; top: 36px; width: 320px; max-height: 340px; overflow: auto; z-index: 30; background: var(--idc-bg);
		border: 1px solid var(--idc-border); border-radius: 10px; box-shadow: 0 12px 32px rgba(0,0,0,.16); padding: 6px; display: none; }
	.idc-health-pop.open { display: block; }
	.idc-issue { display: flex; gap: 8px; align-items: flex-start; padding: 8px; border-radius: 8px; font-size: 12.5px; line-height: 1.4; cursor: default; }
	.idc-issue[data-index] { cursor: pointer; }
	.idc-issue[data-index]:hover { background: var(--idc-subtle); }
	.idc-issue.error .idc-icon { color: var(--red-600, #dc2626); }
	.idc-issue.warn .idc-icon { color: var(--orange-600, #ea580c); }
	.idc-issue.info .idc-icon { color: var(--blue-500, #3b82f6); }
	.idc-body { display: grid; grid-template-columns: 236px minmax(0, 1fr) 280px; min-height: 600px; }
	.idc-left, .idc-right { background: var(--idc-bg); min-width: 0; }
	.idc-left { border-right: 1px solid var(--idc-border); display: flex; flex-direction: column; }
	.idc-right { border-left: 1px solid var(--idc-border); max-height: 760px; overflow-y: auto; }
	.idc-tabs { display: flex; gap: 2px; padding: 8px; border-bottom: 1px solid var(--idc-border); }
	.idc-tabs .idc-btn { flex: 1; }
	.idc-left-body { padding: 10px; overflow-y: auto; max-height: 700px; }
	.idc-group-title { font-size: 10.5px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--idc-muted); margin: 12px 2px 6px; }
	.idc-group-title:first-child { margin-top: 2px; }
	.idc-tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
	.idc-tile { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 10px 4px 8px; border: 1px solid var(--idc-border); border-radius: 10px;
		background: var(--idc-bg); color: var(--idc-text); font-size: 11px; cursor: pointer; text-align: center; line-height: 1.2; }
	.idc-tile:hover { border-color: var(--idc-accent); color: var(--idc-accent); }
	.idc-search { width: 100%; height: 32px; border-radius: 8px; border: 1px solid var(--idc-border); background: var(--control-bg, var(--idc-subtle)); padding: 0 10px; font-size: 12.5px; color: var(--idc-text); }
	.idc-field { display: flex; align-items: center; gap: 8px; width: 100%; padding: 7px 8px; border: 1px solid transparent; border-radius: 8px; background: transparent;
		color: var(--idc-text); cursor: pointer; text-align: left; }
	.idc-field:hover { background: var(--idc-subtle); border-color: var(--idc-border); }
	.idc-field .idc-field-label { font-size: 12.5px; font-weight: 500; }
	.idc-field .idc-field-sample { font-size: 11px; color: var(--idc-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.idc-field .idc-field-text { min-width: 0; flex: 1; }
	.idc-field-ico { width: 26px; height: 26px; border-radius: 7px; background: var(--idc-subtle); display: flex; align-items: center; justify-content: center; color: var(--idc-muted); flex-shrink: 0; }
	.idc-layer { display: flex; align-items: center; gap: 6px; padding: 5px 6px; border-radius: 8px; border: 1px solid transparent; cursor: pointer; font-size: 12.5px; }
	.idc-layer:hover { background: var(--idc-subtle); }
	.idc-layer.selected { background: var(--idc-subtle); border-color: var(--idc-accent); }
	.idc-layer.drop-target { border-top: 2px solid var(--idc-accent); }
	.idc-layer.is-hidden .idc-layer-name { opacity: .45; }
	.idc-layer-name { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.idc-layer .idc-grip { color: var(--idc-muted); cursor: grab; }
	.idc-layer .idc-btn { height: 24px; min-width: 24px; padding: 0 4px; color: var(--idc-muted); }
	.idc-empty-note { color: var(--idc-muted); font-size: 12.5px; text-align: center; padding: 18px 8px; }
	.idc-stage-wrap { display: flex; flex-direction: column; min-width: 0; background: var(--idc-subtle); }
	.idc-stage { flex: 1; display: flex; align-items: center; justify-content: center; padding: 40px 32px; overflow: auto; min-height: 520px;
		background-image: radial-gradient(circle, rgba(127,127,127,.18) 1px, transparent 1px); background-size: 16px 16px; }
	.idc-artboard { position: relative; flex-shrink: 0; }
	.idc-card { position: absolute; left: 0; top: 0; overflow: hidden; transform-origin: top left; font-family: Arial, Helvetica, sans-serif;
		font-size: 16px; line-height: normal; color: #000; text-align: left; letter-spacing: normal; font-weight: normal; }
	.idc-card * { box-sizing: border-box; }
	.idc-artboard .idc-card { box-shadow: 0 1px 2px rgba(0,0,0,.08), 0 10px 30px rgba(15,23,42,.18); border-radius: 3px; }
	.idc-artboard .idc-el { cursor: move; }
	.idc-artboard .idc-el.locked { cursor: default; }
	.idc-artboard .idc-el:hover { outline: 1px dashed rgba(37,99,235,.7); outline-offset: 0; }
	.idc-overlay { position: absolute; inset: 0; pointer-events: none; }
	.idc-guide-line { position: absolute; background: rgba(37,99,235,.35); }
	.idc-safe { position: absolute; border: 1px dashed rgba(234,88,12,.55); border-radius: 2px; }
	.idc-snap { position: absolute; background: #ec4899; }
	.idc-sel { position: absolute; border: 1.5px solid var(--idc-accent); }
	.idc-sel.locked { border-style: dashed; }
	.idc-handle { position: absolute; width: 9px; height: 9px; background: #fff; border: 1.5px solid var(--idc-accent); border-radius: 2px; pointer-events: auto; }
	.idc-sel-tag { position: absolute; top: -22px; left: -1px; background: var(--idc-accent); color: #fff; font-size: 10.5px; padding: 2px 6px;
		border-radius: 4px; white-space: nowrap; font-variant-numeric: tabular-nums; }
	.idc-stage-foot { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 8px 14px; border-top: 1px solid var(--idc-border);
		font-size: 11.5px; color: var(--idc-muted); background: var(--idc-bg); }
	.idc-stage-foot kbd { font-size: 10.5px; padding: 1px 5px; border-radius: 4px; border: 1px solid var(--idc-border); background: var(--idc-subtle); color: var(--idc-text); }
	.idc-empty { text-align: center; max-width: 420px; padding: 32px; border-radius: 16px; background: var(--idc-bg); border: 1px solid var(--idc-border); box-shadow: 0 10px 30px rgba(15,23,42,.08); }
	.idc-empty h4 { margin: 12px 0 6px; font-weight: 600; }
	.idc-empty p { color: var(--idc-muted); font-size: 13px; margin-bottom: 18px; }
	.idc-empty .idc-empty-actions { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }
	.idc-empty-ico { width: 52px; height: 52px; border-radius: 14px; margin: 0 auto; display: flex; align-items: center; justify-content: center; background: var(--idc-subtle); color: var(--idc-accent); }
	.idc-insp-head { display: flex; align-items: center; gap: 8px; padding: 12px; border-bottom: 1px solid var(--idc-border); }
	.idc-insp-head .idc-field-ico { color: var(--idc-accent); }
	.idc-insp-head input { flex: 1; min-width: 0; border: 1px solid transparent; background: transparent; font-weight: 600; font-size: 13px; border-radius: 6px; padding: 3px 6px; color: var(--idc-text); }
	.idc-insp-head input:hover, .idc-insp-head input:focus { border-color: var(--idc-border); outline: none; }
	.idc-sec { padding: 12px; border-bottom: 1px solid var(--idc-border); }
	.idc-sec-title { font-size: 10.5px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--idc-muted); margin-bottom: 8px; }
	.idc-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
	.idc-grid3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
	.idc-row { display: flex; gap: 6px; align-items: center; }
	.idc-row + .idc-row, .idc-grid2 + .idc-row, .idc-row + .idc-grid2, .idc-grid2 + .idc-grid2, .idc-input + .idc-row, .idc-row + .idc-input { margin-top: 8px; }
	.idc-input { position: relative; display: block; min-width: 0; }
	.idc-input > span { display: block; font-size: 11px; color: var(--idc-muted); margin-bottom: 3px; }
	.idc-input input:not([type=checkbox]):not([type=range]), .idc-input select, .idc-input textarea {
		width: 100%; height: 30px; border: 1px solid var(--idc-border); border-radius: 7px; padding: 0 8px; font-size: 12.5px; background: var(--control-bg, var(--idc-bg)); color: var(--idc-text); user-select: text; }
	.idc-input textarea { height: auto; min-height: 56px; padding: 6px 8px; resize: vertical; line-height: 1.4; }
	.idc-input input:focus, .idc-input select:focus, .idc-input textarea:focus { outline: none; border-color: var(--idc-accent); box-shadow: 0 0 0 2px rgba(37,99,235,.15); }
	.idc-input input[type=color] { padding: 2px; cursor: pointer; }
	.idc-input input[type=range] { width: 100%; }
	.idc-input input:disabled { opacity: .55; }
	.idc-toggle { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12.5px; margin-top: 8px; }
	.idc-toggle small { display: block; color: var(--idc-muted); font-size: 11px; }
	.idc-toggle input { width: 16px; height: 16px; }
	.idc-thumb-frame { position: relative; overflow: hidden; border-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,.1), 0 6px 16px rgba(15,23,42,.12); }
	.idc-thumb-frame .idc-card { pointer-events: none; }
	.idc-gallery-filter { display: flex; gap: 6px; margin-bottom: 14px; flex-wrap: wrap; }
	.idc-gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 14px; }
	.idc-starter { border: 1px solid var(--border-color, #e2e6ea); border-radius: 12px; overflow: hidden; cursor: pointer; background: var(--fg-color, #fff); transition: border-color .15s, box-shadow .15s, transform .15s; }
	.idc-starter:hover { border-color: var(--primary, #2563eb); box-shadow: 0 8px 22px rgba(15,23,42,.12); transform: translateY(-2px); }
	.idc-starter-thumb { height: 170px; display: flex; align-items: center; justify-content: center; gap: 8px; background: var(--subtle-fg, #f4f5f7); }
	.idc-starter-body { padding: 10px 12px; }
	.idc-starter-title { font-weight: 600; font-size: 13px; }
	.idc-starter-desc { font-size: 11.5px; color: var(--text-muted, #6b7280); margin-top: 2px; }
	.idc-pill { display: inline-block; font-size: 10.5px; padding: 1px 7px; border-radius: 99px; background: var(--subtle-fg, #f4f5f7); color: var(--text-muted, #6b7280); margin-top: 6px; margin-right: 4px; }
	.idc-blank { width: 70px; height: 44px; border: 2px dashed var(--border-color, #cbd2d9); border-radius: 6px; display: flex; align-items: center; justify-content: center; color: var(--text-muted, #6b7280); }
	.idc-blank.portrait { width: 44px; height: 70px; }
	.idc-preview-grid { display: flex; gap: 24px; justify-content: center; flex-wrap: wrap; padding: 8px 0 4px; }
	.idc-preview-side { text-align: center; }
	.idc-preview-side .idc-preview-label { font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted, #6b7280); margin-bottom: 8px; }
	.idc-preview-side img { display: block; max-width: 100%; border-radius: 12px; box-shadow: 0 1px 2px rgba(0,0,0,.1), 0 12px 30px rgba(15,23,42,.18); }
	.idc-preview-note { text-align: center; color: var(--text-muted, #6b7280); font-size: 12px; margin-top: 14px; }
	.idc-loading { display: flex; align-items: center; justify-content: center; gap: 10px; min-height: 220px; color: var(--text-muted, #6b7280); font-size: 13px; }
	.idc-spinner { width: 18px; height: 18px; border-radius: 50%; border: 2px solid var(--border-color, #e2e6ea); border-top-color: var(--primary, #2563eb); animation: idc-spin .8s linear infinite; }
	@keyframes idc-spin { to { transform: rotate(360deg); } }
	@media (max-width: 1180px) {
		.idc-body { grid-template-columns: 210px minmax(0, 1fr); }
		.idc-right { grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--idc-border); max-height: none; }
	}
	@media (max-width: 760px) {
		.idc-body { grid-template-columns: minmax(0, 1fr); }
		.idc-left { border-right: 0; border-bottom: 1px solid var(--idc-border); }
	}`;
	$(`<style id="idc-studio-css">${css}</style>`).appendTo("head");
};

// ---------------------------------------------------------------------
// Preview dialog (server-rendered, for every creation mode)
// ---------------------------------------------------------------------

slcm.id_card.show_preview = function (frm) {
	slcm.id_card.inject_css();
	const card_type = frm.doc.card_type || "Student";
	const person_doctype = {
		Student: "Student Master",
		Faculty: "Faculty",
		Driver: "SLCM Driver",
	}[card_type];
	const fields = [];
	if (person_doctype) {
		fields.push({
			fieldtype: "Link",
			fieldname: "person",
			options: person_doctype,
			label: __("Preview as"),
			description: __("Leave empty to preview with sample data."),
			onchange: () => render(),
		});
	}
	fields.push({ fieldtype: "HTML", fieldname: "result" });

	const d = new frappe.ui.Dialog({ title: __("Card Preview"), size: "extra-large", fields });
	// Focusing the person field would open its dropdown over the preview.
	d.focus_on_first_input = () => {};
	let request = 0;
	const render = () => {
		const id = ++request;
		const $result = d.fields_dict.result.$wrapper;
		$result.html(
			`<div class="idc-loading"><div class="idc-spinner"></div>${__(
				"Rendering exactly as it will print…"
			)}</div>`
		);
		frm.call({
			method: "render_preview",
			doc: frm.doc,
			args: { person: person_doctype ? d.get_value("person") || null : null },
		})
			.then((r) => {
				if (id !== request) return;
				const res = r.message || {};
				const sides = ["front", "back"].filter((s) => res[s]);
				$result.html(`
					<div class="idc-preview-grid">
						${sides
							.map(
								(s) => `<div class="idc-preview-side" style="max-width:${
									res.orientation === "vertical" ? 300 : 460
								}px">
									<div class="idc-preview-label">${s === "front" ? __("Front") : __("Back")}</div>
									<img src="${res[s]}" alt="${s}">
								</div>`
							)
							.join("")}
					</div>
					<div class="idc-preview-note">${
						res.sample
							? __("Sample data shown. Pick a person above to check real data.")
							: __("Rendered for {0}.", [frappe.utils.escape_html(res.person || "")])
					} ${__("This is the exact image that will be generated.")}</div>`);
			})
			.catch(() => {
				if (id === request)
					$result.html(
						`<div class="idc-empty-note">${__(
							"Preview failed. Check the design and try again."
						)}</div>`
					);
			});
	};
	d.show();
	render();
};

// ---------------------------------------------------------------------
// Designer
// ---------------------------------------------------------------------

class IDCardStudio {
	constructor(frm) {
		this.frm = frm;
		this.docname = frm.docname;
		this.$wrapper = frm.fields_dict.canvas_editor.$wrapper;
		this.side = "front";
		this.selected = null;
		this.zoom = null; // null = fit to stage
		this.scale = 1;
		this.history = [];
		this.future = [];
		this.show_guides = true;
		this.snap = true;
		this.show_tokens = false;
		this.left_tab = "add";
		this.field_query = "";
		this.active = false;
	}

	async init() {
		slcm.id_card.inject_css();
		this.$wrapper.html(
			`<div class="idc-loading"><div class="idc-spinner"></div>${__(
				"Loading designer…"
			)}</div>`
		);
		try {
			await frappe.require("/assets/slcm/js/id_card_starters.js");
			this.meta = await slcm.id_card.get_meta(this.frm.doc.card_type);
		} catch (e) {
			this.$wrapper.html(
				`<div class="idc-empty-note">${__(
					"Could not load the designer. Reload the page to try again."
				)}</div>`
			);
			return;
		}
		this.load_from_doc();
		this.render_shell();
		this.bind_global();
		this.refresh_all();
	}

	destroy() {
		$(document).off(".idcstudio");
		$(window).off(".idcstudio");
	}

	load_from_doc() {
		const raw = this.frm.doc.canvas_data;
		this.data = null;
		if (raw && raw !== "{}" && raw !== "[]") {
			try {
				this.data = slcm.id_card.normalise(JSON.parse(raw), this.meta);
			} catch (e) {
				this.data = null;
			}
		}
		this.last_json = raw || "";
		this.history = [];
		this.future = [];
		this.selected = null;
	}

	/** Called on form refresh: keep state when the doc still matches. */
	sync_from_doc() {
		if (!this.$root || !$.contains(document.documentElement, this.$root[0])) {
			this.load_from_doc();
			this.render_shell();
			this.refresh_all();
			return;
		}
		if ((this.frm.doc.canvas_data || "") !== this.last_json) {
			this.load_from_doc();
		}
		this.docname = this.frm.docname;
		this.refresh_all();
	}

	async on_card_type_change() {
		try {
			this.meta = await slcm.id_card.get_meta(this.frm.doc.card_type);
		} catch (e) {
			return;
		}
		this.render_left();
		this.refresh_all();
	}

	get elements() {
		return this.data ? this.data[this.side] : [];
	}

	get units() {
		return IDC_UNITS[(this.data && this.data.orientation) || "horizontal"];
	}

	ensure_data(orientation) {
		if (!this.data) {
			this.data = slcm.id_card.normalise({ orientation: orientation || "horizontal" });
		}
	}

	// ----- persistence & history ------------------------------------

	commit() {
		const json = this.data ? JSON.stringify(this.data) : "";
		if (json === this.last_json) return;
		this.history.push(this.last_json);
		if (this.history.length > 100) this.history.shift();
		this.future = [];
		this.last_json = json;
		this.frm.set_value("canvas_data", json);
		this.refresh_chrome();
	}

	undo() {
		if (!this.history.length) return;
		this.future.push(this.last_json);
		this.restore(this.history.pop());
	}

	redo() {
		if (!this.future.length) return;
		this.history.push(this.last_json);
		this.restore(this.future.pop());
	}

	restore(json) {
		this.last_json = json;
		this.data = json ? slcm.id_card.normalise(JSON.parse(json), this.meta) : null;
		this.selected = null;
		this.frm.set_value("canvas_data", json);
		this.refresh_all();
	}

	// ----- shell ------------------------------------------------------

	render_shell() {
		const i = slcm.id_card.icon;
		this.$wrapper.html(`
			<div class="idc-studio" tabindex="-1">
				<div class="idc-toolbar">
					<div class="idc-seg" data-group="side">
						<button class="idc-btn" data-side="front">${__(
							"Front"
						)} <span class="idc-count" data-count="front"></span></button>
						<button class="idc-btn" data-side="back">${__(
							"Back"
						)} <span class="idc-count" data-count="back"></span></button>
					</div>
					<div class="idc-seg" data-group="orientation">
						<button class="idc-btn" data-orientation="horizontal" title="${__("Landscape")}">${__(
			"Landscape"
		)}</button>
						<button class="idc-btn" data-orientation="vertical" title="${__("Portrait")}">${__(
			"Portrait"
		)}</button>
					</div>
					<span class="idc-sep"></span>
					<button class="idc-btn" data-act="undo" title="${__("Undo")} (Ctrl+Z)">${i("undo")}</button>
					<button class="idc-btn" data-act="redo" title="${__("Redo")} (Ctrl+Shift+Z)">${i("redo")}</button>
					<span class="idc-sep"></span>
					<button class="idc-btn" data-act="zoom-out" title="${__("Zoom out")}">${i("zoom-out")}</button>
					<button class="idc-btn idc-zoom-label" data-act="zoom-fit" title="${__("Fit to screen")}"></button>
					<button class="idc-btn" data-act="zoom-in" title="${__("Zoom in")}">${i("zoom-in")}</button>
					<span class="idc-sep"></span>
					<button class="idc-btn" data-studio-toggle="show_guides" title="${__(
						"Centre lines and safe area"
					)}">${i("guides")}</button>
					<button class="idc-btn" data-studio-toggle="snap" title="${__(
						"Snap to guides and elements (hold Alt to bypass)"
					)}">${i("magnet")}</button>
					<button class="idc-btn" data-studio-toggle="show_tokens" title="${__(
						"Show field names instead of sample data"
					)}">${i("braces")}</button>
					<span class="idc-spacer"></span>
					<div class="idc-health"><button class="idc-btn" data-act="health"></button><div class="idc-health-pop"></div></div>
					<button class="idc-btn outline" data-act="starters">${i("templates")} ${__("Starters")}</button>
					<button class="idc-btn primary" data-act="preview">${i("eye")} ${__("Preview")}</button>
				</div>
				<div class="idc-body">
					<aside class="idc-left">
						<div class="idc-tabs">
							<button class="idc-btn" data-tab="add">${i("plus", 14)} ${__("Add")}</button>
							<button class="idc-btn" data-tab="fields">${i("braces", 14)} ${__("Fields")}</button>
							<button class="idc-btn" data-tab="layers">${i("layers", 14)} ${__("Layers")}</button>
						</div>
						<div class="idc-left-body"></div>
					</aside>
					<div class="idc-stage-wrap">
						<div class="idc-stage"></div>
						<div class="idc-stage-foot">
							<span class="idc-dims"></span>
							<span><kbd>←↑→↓</kbd> ${__("nudge")} · <kbd>Shift</kbd> ×10 · <kbd>Ctrl D</kbd> ${__(
			"duplicate"
		)} · <kbd>Del</kbd> ${__("remove")} · <kbd>Alt</kbd> ${__("no snap")}</span>
						</div>
					</div>
					<aside class="idc-right"></aside>
				</div>
			</div>`);

		this.$root = this.$wrapper.find(".idc-studio");
		// Form sections are capped at 900px; the designer uses the full width.
		this.$wrapper.closest(".section-body").css("max-width", "none");
		this.$stage = this.$root.find(".idc-stage");
		this.$left = this.$root.find(".idc-left-body");
		this.$right = this.$root.find(".idc-right");
		this.bind_shell();
		this.render_left();
	}

	bind_shell() {
		const $r = this.$root;
		$r.on("click", "[data-side]", (e) => {
			this.side = $(e.currentTarget).data("side");
			this.selected = null;
			this.refresh_all();
		});
		$r.on("click", "[data-orientation]", (e) => {
			const o = $(e.currentTarget).data("orientation");
			this.ensure_data(o);
			if (this.data.orientation === o) return;
			this.data.orientation = o;
			this.commit();
			this.refresh_all();
		});
		$r.on("click", "[data-tab]", (e) => {
			this.left_tab = $(e.currentTarget).data("tab");
			this.render_left();
		});
		$r.on("click", "[data-studio-toggle]", (e) => {
			const key = $(e.currentTarget).data("studio-toggle");
			this[key] = !this[key];
			this.refresh_all();
		});
		$r.on("click", "[data-act]", (e) => {
			const act = $(e.currentTarget).data("act");
			const zooms = [0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4];
			if (act === "undo") this.undo();
			else if (act === "redo") this.redo();
			else if (act === "zoom-fit") {
				this.zoom = null;
				this.render_canvas();
			} else if (act === "zoom-in") {
				this.zoom = zooms.find((z) => z > this.scale + 0.01) || 4;
				this.render_canvas();
			} else if (act === "zoom-out") {
				this.zoom = [...zooms].reverse().find((z) => z < this.scale - 0.01) || 0.5;
				this.render_canvas();
			} else if (act === "starters") this.open_starters();
			else if (act === "preview") slcm.id_card.show_preview(this.frm);
			else if (act === "health") {
				e.stopPropagation();
				$r.find(".idc-health-pop").toggleClass("open");
			}
		});
		$r.on("click", ".idc-issue[data-index]", (e) => {
			const $i = $(e.currentTarget);
			this.side = $i.data("issue-side");
			this.selected = +$i.data("index");
			$r.find(".idc-health-pop").removeClass("open");
			this.refresh_all();
		});

		// Canvas interaction
		this.$stage.on("mousedown", ".idc-handle", (e) => {
			e.preventDefault();
			e.stopPropagation();
			this.active = true;
			this.start_resize(e, $(e.currentTarget).data("dir"));
		});
		this.$stage.on("mousedown", ".idc-artboard .idc-el", (e) => {
			if (e.button !== 0) return;
			e.preventDefault();
			e.stopPropagation();
			this.active = true;
			this.start_drag(e, +$(e.currentTarget).attr("data-index"));
		});
		this.$stage.on("dblclick", ".idc-artboard .idc-el", () => {
			this.$right.find("[data-prop='content']").trigger("focus").trigger("select");
		});
		this.$stage.on("mousedown", (e) => {
			if ($(e.target).closest(".idc-el, .idc-handle, .idc-empty").length) return;
			if (this.selected !== null) {
				this.selected = null;
				this.refresh_selection();
			}
		});
		this.$stage.on("click", "[data-empty]", (e) => {
			const what = $(e.currentTarget).data("empty");
			if (what === "starters") return this.open_starters();
			this.ensure_data(what);
			this.commit();
			this.refresh_all();
		});

		this.bind_left();
		this.bind_inspector();
	}

	bind_global() {
		this.destroy();
		$(document).on("mousedown.idcstudio", (e) => {
			this.active = !!(this.$root && this.$root[0].contains(e.target));
			if (!$(e.target).closest(".idc-health").length && this.$root) {
				this.$root.find(".idc-health-pop").removeClass("open");
			}
		});
		$(document).on("keydown.idcstudio", (e) => this.on_key(e));
		$(window).on(
			"resize.idcstudio",
			frappe.utils.debounce(() => {
				if (this.zoom === null && this.$root && this.$root.is(":visible"))
					this.render_canvas();
			}, 150)
		);
	}

	on_key(e) {
		if (
			!this.active ||
			!this.$root ||
			!this.$root.is(":visible") ||
			window.cur_frm !== this.frm
		)
			return;
		if ($(e.target).is("input, textarea, select, [contenteditable=true]")) return;
		if ($(".modal.show").length) return;
		const mod = e.ctrlKey || e.metaKey;
		const key = e.key;
		let handled = true;

		if (mod && key.toLowerCase() === "z") e.shiftKey ? this.redo() : this.undo();
		else if (mod && key.toLowerCase() === "y") this.redo();
		else if (mod && key.toLowerCase() === "d") this.duplicate();
		else if (mod && key.toLowerCase() === "c") this.copy();
		else if (mod && key.toLowerCase() === "v") this.paste();
		else if (!mod && (key === "Delete" || key === "Backspace")) this.remove();
		else if (!mod && key === "Escape") {
			this.selected = null;
			this.refresh_selection();
		} else if (!mod && key.startsWith("Arrow")) {
			const el = this.current();
			if (!el || el.locked) return;
			const step = e.shiftKey ? 10 : 1;
			if (key === "ArrowLeft") el.x = round1(+el.x - step);
			if (key === "ArrowRight") el.x = round1(+el.x + step);
			if (key === "ArrowUp") el.y = round1(+el.y - step);
			if (key === "ArrowDown") el.y = round1(+el.y + step);
			this.render_canvas();
			this.commit_debounced();
			this.render_inspector();
		} else handled = false;

		if (handled) e.preventDefault();
	}

	commit_debounced() {
		clearTimeout(this._commit_timer);
		this._commit_timer = setTimeout(() => this.commit(), 350);
	}

	// ----- refresh pipeline -----------------------------------------

	refresh_all() {
		if (!this.$root) return;
		if (this.selected !== null && !this.elements[this.selected]) this.selected = null;
		this.render_canvas();
		this.render_inspector();
		this.refresh_chrome();
	}

	refresh_chrome() {
		this.render_toolbar();
		this.render_health();
		if (this.left_tab === "layers") this.render_left();
	}

	refresh_selection() {
		this.$stage.find(".idc-el").removeClass("is-selected");
		this.render_overlay();
		this.render_inspector();
		if (this.left_tab === "layers") this.render_left();
	}

	render_toolbar() {
		const $r = this.$root;
		$r.find("[data-side]").each((_, b) =>
			$(b).toggleClass("active", $(b).data("side") === this.side)
		);
		const orientation = (this.data && this.data.orientation) || "horizontal";
		$r.find("[data-orientation]").each((_, b) =>
			$(b).toggleClass("active", $(b).data("orientation") === orientation)
		);
		["front", "back"].forEach((s) => {
			const n = this.data ? this.data[s].length : 0;
			$r.find(`[data-count='${s}']`).text(n ? `(${n})` : "");
		});
		$r.find("[data-act='undo']").prop("disabled", !this.history.length);
		$r.find("[data-act='redo']").prop("disabled", !this.future.length);
		$r.find("[data-studio-toggle]").each((_, b) =>
			$(b).toggleClass("active", !!this[$(b).data("studio-toggle")])
		);
		$r.find(".idc-zoom-label").text(Math.round(this.scale * 100) + "%");
		$r.find(".idc-dims").text(
			`${IDC_MM[orientation]} · CR80 · ${this.side === "front" ? __("Front") : __("Back")}`
		);
	}

	// ----- canvas -------------------------------------------------------

	compute_scale() {
		if (this.zoom) return this.zoom;
		const [w, h] = this.units;
		const avail_w = Math.max(this.$stage.innerWidth() - 72, 200);
		const avail_h = 560;
		return Math.max(
			0.5,
			Math.min(3, Math.floor(Math.min(avail_w / w, avail_h / h) * 20) / 20)
		);
	}

	render_canvas() {
		if (!this.data) {
			this.render_empty();
			return;
		}
		const [w, h] = this.units;
		this.scale = this.compute_scale();
		const s = this.scale;
		const ctx = slcm.id_card.design_context(this.frm, this.meta, this.show_tokens);

		const $art = $(
			`<div class="idc-artboard" style="width:${w * s}px;height:${h * s}px"></div>`
		);
		const $card = $(
			`<div class="idc-card" style="width:${w}px;height:${h}px;transform:scale(${s});background:${
				this.data.bg_color[this.side] || "#fff"
			}"></div>`
		).appendTo($art);
		this.elements.forEach((el, index) => {
			if (el.hidden) return;
			const $el = slcm.id_card.build_element(el, ctx).attr("data-index", index);
			if (el.locked) $el.addClass("locked");
			$card.append($el);
		});
		$art.append('<div class="idc-overlay"></div>');

		this.$stage.empty().append($art);
		this.$card = $card;
		this.$overlay = $art.find(".idc-overlay");
		slcm.id_card.apply_fit($card);
		this.render_overlay();
		this.$root.find(".idc-zoom-label").text(Math.round(s * 100) + "%");
	}

	render_empty() {
		const i = slcm.id_card.icon;
		this.$stage.html(`
			<div class="idc-empty">
				<div class="idc-empty-ico">${i("templates", 26)}</div>
				<h4>${__("Design your ID card")}</h4>
				<p>${__(
					"Start from a ready-made starter, or begin with a blank card and add fields from the left panel."
				)}</p>
				<div class="idc-empty-actions">
					<button class="idc-btn primary" data-empty="starters">${i("templates")} ${__(
			"Browse starters"
		)}</button>
					<button class="idc-btn outline" data-empty="horizontal">${__("Blank landscape")}</button>
					<button class="idc-btn outline" data-empty="vertical">${__("Blank portrait")}</button>
				</div>
			</div>`);
		this.$card = null;
	}

	/** Unscaled box of an element on the current side, measured from the DOM. */
	box(index) {
		const node = this.$card && this.$card.find(`[data-index='${index}']`)[0];
		if (!node) return null;
		return {
			x: node.offsetLeft,
			y: node.offsetTop,
			w: node.offsetWidth,
			h: node.offsetHeight,
		};
	}

	render_overlay(snap_lines) {
		if (!this.$overlay) return;
		const s = this.scale;
		const [w, h] = this.units;
		let html = "";
		if (this.show_guides) {
			html += `<div class="idc-guide-line" style="left:${
				(w / 2) * s
			}px;top:0;bottom:0;width:1px"></div>`;
			html += `<div class="idc-guide-line" style="top:${
				(h / 2) * s
			}px;left:0;right:0;height:1px"></div>`;
			html += `<div class="idc-safe" style="left:${IDC_SAFE * s}px;top:${
				IDC_SAFE * s
			}px;width:${(w - 2 * IDC_SAFE) * s}px;height:${(h - 2 * IDC_SAFE) * s}px" title="${__(
				"Safe area"
			)}"></div>`;
		}
		(snap_lines || []).forEach((g) => {
			html +=
				g.axis === "x"
					? `<div class="idc-snap" style="left:${
							g.pos * s
					  }px;top:-8px;bottom:-8px;width:1px"></div>`
					: `<div class="idc-snap" style="top:${
							g.pos * s
					  }px;left:-8px;right:-8px;height:1px"></div>`;
		});

		const el = this.current();
		const b = el && !el.hidden ? this.box(this.selected) : null;
		if (b) {
			const dirs = el.locked
				? []
				: el.type === "text"
				? ["w", "e"]
				: ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
			const pos = {
				nw: [0, 0],
				n: [0.5, 0],
				ne: [1, 0],
				e: [1, 0.5],
				se: [1, 1],
				s: [0.5, 1],
				sw: [0, 1],
				w: [0, 0.5],
			};
			const cursors = {
				nw: "nwse",
				se: "nwse",
				ne: "nesw",
				sw: "nesw",
				n: "ns",
				s: "ns",
				e: "ew",
				w: "ew",
			};
			const bw = b.w * s;
			const bh = b.h * s;
			html += `<div class="idc-sel ${el.locked ? "locked" : ""}" style="left:${
				b.x * s - 1
			}px;top:${b.y * s - 1}px;width:${bw + 2}px;height:${bh + 2}px">
				<div class="idc-sel-tag">${el.locked ? "🔒 " : ""}${Math.round(b.w)} × ${Math.round(b.h)}</div>
				${dirs
					.map(
						(d) =>
							`<div class="idc-handle" data-dir="${d}" style="left:${
								pos[d][0] * (bw + 2) - 5
							}px;top:${pos[d][1] * (bh + 2) - 5}px;cursor:${
								cursors[d]
							}-resize"></div>`
					)
					.join("")}
			</div>`;
		}
		this.$overlay.html(html);
	}

	current() {
		return this.selected === null ? null : this.elements[this.selected] || null;
	}

	select(index) {
		if (this.selected === index) return;
		this.selected = index;
		this.refresh_selection();
	}

	// ----- drag / resize / snap -------------------------------------

	snap_candidates(skip_index) {
		const [w, h] = this.units;
		const xs = [0, w / 2, w, IDC_SAFE, w - IDC_SAFE];
		const ys = [0, h / 2, h, IDC_SAFE, h - IDC_SAFE];
		this.elements.forEach((el, i) => {
			if (i === skip_index || el.hidden) return;
			const b = this.box(i);
			if (!b) return;
			xs.push(b.x, b.x + b.w / 2, b.x + b.w);
			ys.push(b.y, b.y + b.h / 2, b.y + b.h);
		});
		return { xs, ys };
	}

	snap_axis(start, size, targets) {
		const threshold = 5 / this.scale;
		let best = null;
		[0, size / 2, size].forEach((offset) => {
			targets.forEach((t) => {
				const d = t - (start + offset);
				if (Math.abs(d) <= threshold && (!best || Math.abs(d) < Math.abs(best.d)))
					best = { d, pos: t };
			});
		});
		return best;
	}

	start_drag(e, index) {
		this.select(index);
		const el = this.current();
		if (!el || el.locked) return;
		const s = this.scale;
		const b = this.box(index);
		const start = { mx: e.clientX, my: e.clientY, x: +el.x || 0, y: +el.y || 0 };
		// The DOM box can be offset from x/y by margins in legacy styles.
		const off = { x: b.x - start.x, y: b.y - start.y };
		const targets = this.snap ? this.snap_candidates(index) : null;
		const $node = this.$card.find(`[data-index='${index}']`);
		let moved = false;

		const move = (ev) => {
			let dx = (ev.clientX - start.mx) / s;
			let dy = (ev.clientY - start.my) / s;
			if (!moved && Math.abs(dx * s) < 2 && Math.abs(dy * s) < 2) return;
			moved = true;
			if (ev.shiftKey) Math.abs(dx) > Math.abs(dy) ? (dy = 0) : (dx = 0);
			let nx = start.x + dx;
			let ny = start.y + dy;
			const lines = [];
			if (targets && !ev.altKey) {
				const sx = this.snap_axis(nx + off.x, b.w, targets.xs);
				const sy = this.snap_axis(ny + off.y, b.h, targets.ys);
				if (sx) {
					nx += sx.d;
					lines.push({ axis: "x", pos: sx.pos });
				}
				if (sy) {
					ny += sy.d;
					lines.push({ axis: "y", pos: sy.pos });
				}
			}
			el.x = round1(nx);
			el.y = round1(ny);
			$node.css({ left: el.x + "px", top: el.y + "px" });
			this.render_overlay(lines);
		};
		const up = () => {
			$(document).off("mousemove.idcdrag mouseup.idcdrag");
			this.render_overlay();
			if (moved) {
				this.commit();
				this.render_inspector();
			}
		};
		$(document).on("mousemove.idcdrag", move).on("mouseup.idcdrag", up);
	}

	start_resize(e, dir) {
		const el = this.current();
		if (!el || el.locked) return;
		const s = this.scale;
		const b = this.box(this.selected);
		const start = {
			mx: e.clientX,
			my: e.clientY,
			x: +el.x || 0,
			y: +el.y || 0,
			w: el.type === "text" ? +el.width || b.w : +el.width || b.w,
			h: +el.height || b.h,
		};
		const ratio = start.w / (start.h || 1);
		const index = this.selected;

		const move = (ev) => {
			const dx = (ev.clientX - start.mx) / s;
			const dy = (ev.clientY - start.my) / s;
			let { x, y, w, h } = start;
			if (dir.includes("e")) w = start.w + dx;
			if (dir.includes("w")) {
				w = start.w - dx;
				x = start.x + dx;
			}
			if (dir.includes("s")) h = start.h + dy;
			if (dir.includes("n")) {
				h = start.h - dy;
				y = start.y + dy;
			}
			if (ev.shiftKey && dir.length === 2 && el.type !== "text") {
				h = w / ratio;
				if (dir.includes("n")) y = start.y + (start.h - h);
			}
			if (w < 4) {
				if (dir.includes("w")) x -= 4 - w;
				w = 4;
			}
			if (h < 2) {
				if (dir.includes("n")) y -= 2 - h;
				h = 2;
			}
			el.x = round1(x);
			el.width = round1(w);
			if (el.type !== "text") {
				el.y = round1(y);
				el.height = round1(h);
			}
			this.render_canvas();
			this.selected = index;
			this.render_overlay();
		};
		const up = () => {
			$(document).off("mousemove.idcdrag mouseup.idcdrag");
			this.commit();
			this.render_inspector();
		};
		$(document).on("mousemove.idcdrag", move).on("mouseup.idcdrag", up);
	}

	// ----- element operations -------------------------------------------

	add(el, opts = {}) {
		this.ensure_data();
		const [w, h] = this.units;
		if (el.x === undefined) el.x = round1(Math.max(IDC_SAFE, (w - (el.width || 80)) / 2));
		if (el.y === undefined) el.y = round1(Math.max(IDC_SAFE, (h - (el.height || 16)) / 2));
		el.style = el.style || {};
		if (opts.to_back) {
			this.elements.unshift(el);
			this.selected = 0;
		} else {
			this.elements.push(el);
			this.selected = this.elements.length - 1;
		}
		this.commit();
		this.refresh_all();
		if (el.type === "text" && opts.focus) {
			setTimeout(
				() => this.$right.find("[data-prop='content']").trigger("focus").trigger("select"),
				30
			);
		}
	}

	remove() {
		if (this.selected === null) return;
		this.elements.splice(this.selected, 1);
		this.selected = null;
		this.commit();
		this.refresh_all();
	}

	duplicate() {
		const el = this.current();
		if (!el) return;
		const copy = JSON.parse(JSON.stringify(el));
		copy.x = round1(+copy.x + 8);
		copy.y = round1(+copy.y + 8);
		copy.locked = false;
		this.elements.splice(this.selected + 1, 0, copy);
		this.selected += 1;
		this.commit();
		this.refresh_all();
	}

	copy() {
		const el = this.current();
		if (el) {
			slcm.id_card._clipboard = JSON.stringify(el);
			frappe.show_alert(
				{ message: __("Copied. Paste on either side with Ctrl+V."), indicator: "blue" },
				2
			);
		}
	}

	paste() {
		if (!slcm.id_card._clipboard) return;
		const el = JSON.parse(slcm.id_card._clipboard);
		el.x = round1(+el.x + 6);
		el.y = round1(+el.y + 6);
		this.ensure_data();
		this.elements.push(el);
		this.selected = this.elements.length - 1;
		this.commit();
		this.refresh_all();
	}

	copy_to_other_side() {
		const el = this.current();
		if (!el) return;
		const other = this.side === "front" ? "back" : "front";
		this.data[other].push(JSON.parse(JSON.stringify(el)));
		this.commit();
		frappe.show_alert(
			{
				message: __("Copied to the {0}.", [other === "front" ? __("front") : __("back")]),
				indicator: "green",
			},
			2
		);
	}

	move_layer(from, to) {
		const list = this.elements;
		if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return;
		const [el] = list.splice(from, 1);
		list.splice(to, 0, el);
		this.selected = to;
		this.commit();
		this.refresh_all();
	}

	align(where) {
		const el = this.current();
		const b = el && this.box(this.selected);
		if (!b) return;
		const [w, h] = this.units;
		const off = { x: b.x - (+el.x || 0), y: b.y - (+el.y || 0) };
		if (where === "left") el.x = round1(IDC_SAFE - off.x);
		if (where === "hcenter") el.x = round1((w - b.w) / 2 - off.x);
		if (where === "right") el.x = round1(w - IDC_SAFE - b.w - off.x);
		if (where === "top") el.y = round1(IDC_SAFE - off.y);
		if (where === "vmiddle") el.y = round1((h - b.h) / 2 - off.y);
		if (where === "bottom") el.y = round1(h - IDC_SAFE - b.h - off.y);
		this.commit();
		this.refresh_all();
	}

	upload_image(callback) {
		new frappe.ui.FileUploader({
			doctype: this.frm.is_new() ? undefined : this.frm.doctype,
			docname: this.frm.is_new() ? undefined : this.frm.docname,
			folder: "Home/Attachments",
			make_attachments_public: true,
			restrictions: { allowed_file_types: ["image/*"] },
			on_success: (file) => {
				if (!file || !file.file_url) return;
				const img = new Image();
				img.onload = () => callback(file.file_url, img.naturalWidth, img.naturalHeight);
				img.onerror = () => callback(file.file_url, 0, 0);
				img.src = file.file_url;
			},
		});
	}

	layer_name(el) {
		if (el.name) return el.name;
		if (el.type === "text") {
			const labels = { ...(this.meta.labels || {}) };
			(this.meta.tokens || []).forEach((t) => (labels[t.key] = t.label));
			const text = (el.content || "")
				.replace(
					/\{\{\s*([A-Za-z_]+)\s*\}\}/g,
					(m, k) => labels[slcm.id_card.canonical(this.meta, k)] || k
				)
				.replace(/<[^>]*>/g, " ")
				.trim();
			return text || __("Text");
		}
		if (el.type === "image") {
			const src = IDC_IMAGE_SOURCES.find(([k]) => k === (el.mapping || ""));
			return el.mapping && src ? src[1] : __("Image");
		}
		if (el.style && el.style.borderRadius === "50%") return __("Circle");
		return __("Shape");
	}

	layer_icon(el) {
		if (el.type === "text") return "text";
		if (el.type === "image") {
			return (
				{
					photo: "user",
					qr_code_image: "qr",
					institute_logo: "building",
					authority_signature: "pen",
					watermark_image: "droplet",
				}[el.mapping] || "image"
			);
		}
		return el.style && el.style.borderRadius === "50%" ? "circle" : "square";
	}

	// ----- left panel -------------------------------------------------

	render_left() {
		if (!this.$root) return;
		this.$root
			.find("[data-tab]")
			.each((_, b) => $(b).toggleClass("active", $(b).data("tab") === this.left_tab));
		const i = slcm.id_card.icon;

		if (this.left_tab === "add") {
			const tile = (act, icon, label) =>
				`<button class="idc-tile" data-add="${act}">${i(
					icon,
					20
				)}<span>${label}</span></button>`;
			this.$left.html(`
				<div class="idc-group-title">${__("Text")}</div>
				<div class="idc-tiles">
					${tile("heading", "heading", __("Heading"))}
					${tile("text", "text", __("Text"))}
					${tile("paragraph", "paragraph", __("Paragraph"))}
				</div>
				<div class="idc-group-title">${__("Shapes")}</div>
				<div class="idc-tiles">
					${tile("rect", "square", __("Rectangle"))}
					${tile("circle", "circle", __("Circle"))}
					${tile("line", "line", __("Line"))}
					${tile("header", "header", __("Header band"))}
					${tile("footer", "footer", __("Footer band"))}
				</div>
				<div class="idc-group-title">${__("Images")}</div>
				<div class="idc-tiles">
					${tile("image", "upload", __("Upload image"))}
					${tile("background", "image", __("Background"))}
					${tile("map:watermark_image", "droplet", __("Watermark"))}
				</div>
				<div class="idc-group-title">${__("Quick fields")}</div>
				<div class="idc-tiles">
					${tile("map:photo", "user", __("Photo"))}
					${tile("token:student_name", "text", __("Name"))}
					${tile("token:student_id", "braces", __("ID number"))}
					${tile("map:qr_code_image", "qr", __("QR code"))}
					${tile("map:institute_logo", "building", __("Logo"))}
					${tile("map:authority_signature", "pen", __("Signature"))}
				</div>`);
		} else if (this.left_tab === "fields") {
			const q = this.field_query.toLowerCase();
			const groups = {};
			(this.meta.tokens || [])
				.filter((t) => !q || t.label.toLowerCase().includes(q) || t.key.includes(q))
				.forEach((t) => (groups[t.group] = groups[t.group] || []).push(t));
			const icon_for = (t) =>
				t.kind === "image"
					? {
							photo: "user",
							qr_code_image: "qr",
							institute_logo: "building",
							authority_signature: "pen",
							watermark_image: "droplet",
					  }[t.key]
					: "braces";
			const list = Object.entries(groups)
				.map(
					([group, tokens]) => `
					<div class="idc-group-title">${__(group)}</div>
					${tokens
						.map(
							(t) => `<button class="idc-field" data-add="${
								t.kind === "image" ? "map" : "token"
							}:${t.key}" title="${__("Add to card")}">
								<span class="idc-field-ico">${i(icon_for(t), 14)}</span>
								<span class="idc-field-text"><div class="idc-field-label">${frappe.utils.escape_html(
									t.label
								)}</div>
								<div class="idc-field-sample">${
									t.kind === "image"
										? __("Image")
										: frappe.utils.escape_html(t.sample || "")
								}</div></span>
							</button>`
						)
						.join("")}`
				)
				.join("");
			this.$left.html(`
				<input class="idc-search" type="search" placeholder="${__(
					"Search fields…"
				)}" value="${frappe.utils.escape_html(this.field_query)}">
				${list || `<div class="idc-empty-note">${__("No matching fields")}</div>`}
				<div class="idc-empty-note" style="text-align:left;padding:12px 2px">${__(
					"Tip: to put a field inside existing text, select the text and use <b>Insert field</b> in the panel on the right."
				)}</div>`);
		} else {
			const els = this.elements;
			if (!els.length) {
				this.$left.html(
					`<div class="idc-empty-note">${__("No elements on this side yet.")}</div>`
				);
				return;
			}
			const rows = els
				.map((el, index) => ({ el, index }))
				.reverse()
				.map(
					({ el, index }) => `
					<div class="idc-layer ${index === this.selected ? "selected" : ""} ${
						el.hidden ? "is-hidden" : ""
					}" data-layer="${index}" draggable="true">
						<span class="idc-grip">${i("grip", 14)}</span>
						<span class="idc-field-ico" style="width:22px;height:22px">${i(this.layer_icon(el), 13)}</span>
						<span class="idc-layer-name">${frappe.utils.escape_html(this.layer_name(el))}</span>
						<button class="idc-btn" data-layer-act="hidden" title="${el.hidden ? __("Show") : __("Hide")}">${i(
						el.hidden ? "eye-off" : "eye",
						14
					)}</button>
						<button class="idc-btn" data-layer-act="locked" title="${
							el.locked ? __("Unlock") : __("Lock")
						}">${i(el.locked ? "lock" : "unlock", 14)}</button>
					</div>`
				)
				.join("");
			this.$left.html(
				`<div class="idc-empty-note" style="text-align:left;padding:2px 2px 8px">${__(
					"Top of the list is in front. Drag to reorder."
				)}</div>${rows}`
			);
		}
	}

	bind_left() {
		const $l = this.$left;
		$l.on("input", ".idc-search", (e) => {
			this.field_query = e.target.value;
			const pos = e.target.selectionStart;
			this.render_left();
			const input = this.$left.find(".idc-search")[0];
			input.focus();
			input.setSelectionRange(pos, pos);
		});
		$l.on("click", "[data-add]", (e) =>
			this.add_from_palette(String($(e.currentTarget).data("add")))
		);
		$l.on("click", "[data-layer]", (e) => {
			if ($(e.target).closest("[data-layer-act]").length) return;
			this.select(+$(e.currentTarget).data("layer"));
		});
		$l.on("click", "[data-layer-act]", (e) => {
			e.stopPropagation();
			const index = +$(e.currentTarget).closest("[data-layer]").data("layer");
			const key = $(e.currentTarget).data("layer-act");
			const el = this.elements[index];
			el[key] = !el[key];
			if (!el[key]) delete el[key];
			this.commit();
			this.refresh_all();
		});
		$l.on("dragstart", "[data-layer]", (e) => {
			this._drag_layer = +$(e.currentTarget).data("layer");
			e.originalEvent.dataTransfer.effectAllowed = "move";
			e.originalEvent.dataTransfer.setData("text/plain", String(this._drag_layer));
		});
		$l.on("dragover", "[data-layer]", (e) => {
			e.preventDefault();
			$l.find(".drop-target").removeClass("drop-target");
			$(e.currentTarget).addClass("drop-target");
		});
		$l.on("dragleave", "[data-layer]", (e) => $(e.currentTarget).removeClass("drop-target"));
		$l.on("drop", "[data-layer]", (e) => {
			e.preventDefault();
			const to = +$(e.currentTarget).data("layer");
			if (this._drag_layer !== undefined) this.move_layer(this._drag_layer, to);
			this._drag_layer = undefined;
		});
		$l.on("dragend", "[data-layer]", () => $l.find(".drop-target").removeClass("drop-target"));
	}

	add_from_palette(action) {
		this.ensure_data();
		const [w, h] = this.units;
		const [kind, key] = action.split(":");
		const font = this.frm.doc.font_family || "Arial, Helvetica, sans-serif";
		const color = this.frm.doc.base_font_color || "#111827";

		if (kind === "token") {
			const bold = key === "student_name";
			return this.add({
				type: "text",
				content: `{{${key}}}`,
				style: {
					fontSize: bold ? "16px" : "11px",
					fontWeight: bold ? "bold" : "normal",
					color,
					fontFamily: font,
				},
			});
		}
		if (kind === "map") {
			const sizes = {
				photo: [64, 78],
				qr_code_image: [56, 56],
				institute_logo: [40, 40],
				authority_signature: [70, 28],
				watermark_image: [140, 140],
			};
			const [ew, eh] = sizes[key] || [60, 60];
			const el = {
				type: "image",
				mapping: key,
				content: "",
				width: ew,
				height: eh,
				style: { opacity: 1 },
			};
			if (key === "authority_signature" || key === "institute_logo")
				el.object_fit = "contain";
			if (key === "photo") el.style.borderRadius = "6px";
			if (key === "watermark_image") {
				el.object_fit = "contain";
				el.style.opacity = 0.12;
				return this.add(el, { to_back: true });
			}
			return this.add(el);
		}
		const presets = {
			heading: {
				type: "text",
				content: __("Heading"),
				style: { fontSize: "18px", fontWeight: "bold", color, fontFamily: font },
			},
			text: {
				type: "text",
				content: __("Your text"),
				style: { fontSize: "11px", color, fontFamily: font },
			},
			paragraph: {
				type: "text",
				content: __(
					"Use this card for identification on campus. If found, please return it to the institute."
				),
				width: 160,
				wrap: true,
				style: { fontSize: "8px", lineHeight: "1.35", color, fontFamily: font },
			},
			rect: {
				type: "rect",
				width: 100,
				height: 50,
				style: { backgroundColor: "#e5e7eb", opacity: 1 },
			},
			circle: {
				type: "rect",
				width: 50,
				height: 50,
				style: { backgroundColor: "#dbeafe", borderRadius: "50%", opacity: 1 },
			},
			line: {
				type: "rect",
				width: 120,
				height: 1.5,
				style: { backgroundColor: "#111827", opacity: 1 },
			},
			header: {
				type: "rect",
				x: 0,
				y: 0,
				width: w,
				height: 40,
				style: { backgroundColor: "#1e3a8a", opacity: 1 },
			},
			footer: {
				type: "rect",
				x: 0,
				y: round1(h - 24),
				width: w,
				height: 24,
				style: { backgroundColor: "#1e3a8a", opacity: 1 },
			},
		};
		if (presets[kind])
			return this.add(JSON.parse(JSON.stringify(presets[kind])), { focus: kind !== "rect" });

		if (kind === "image" || kind === "background") {
			this.upload_image((url, nw, nh) => {
				if (kind === "background") {
					this.add(
						{
							type: "image",
							content: url,
							x: 0,
							y: 0,
							width: w,
							height: h,
							name: __("Background"),
							style: { opacity: 1 },
						},
						{ to_back: true }
					);
					return;
				}
				const max = 90;
				const r = nw && nh ? nw / nh : 1;
				const ew = r >= 1 ? max : round1(max * r);
				const eh = r >= 1 ? round1(max / r) : max;
				this.add({
					type: "image",
					content: url,
					width: ew,
					height: eh,
					object_fit: "contain",
					style: { opacity: 1 },
				});
			});
		}
	}

	// ----- inspector ------------------------------------------------------

	render_inspector() {
		if (!this.$right) return;
		const el = this.current();
		this.$right.html(el ? this.inspector_html(el) : this.card_panel_html());
		if (this.$card) this.$card.find(".idc-el").removeClass("is-selected");
	}

	card_panel_html() {
		const i = slcm.id_card.icon;
		if (!this.data) {
			return `<div class="idc-sec"><div class="idc-empty-note">${__(
				"Pick a starter or a blank card to begin."
			)}</div></div>`;
		}
		const bg = slcm.id_card.to_hex(this.data.bg_color[this.side], "#ffffff");
		const issues = this.issues();
		return `
			<div class="idc-insp-head"><span class="idc-field-ico">${i(
				"square",
				14
			)}</span><b style="font-size:13px">${__("Card")} · ${
			this.side === "front" ? __("Front") : __("Back")
		}</b></div>
			<div class="idc-sec">
				<div class="idc-sec-title">${__("Background")}</div>
				<div class="idc-row">
					<label class="idc-input" style="flex:1"><span>${__(
						"Colour"
					)}</span><input type="color" data-card="bg" value="${bg}"></label>
					<button class="idc-btn outline" data-card="bg-both" style="margin-top:16px">${__(
						"Use on both sides"
					)}</button>
				</div>
			</div>
			<div class="idc-sec">
				<div class="idc-sec-title">${__("Print check")}</div>
				${
					issues.length
						? issues.map((x) => this.issue_html(x)).join("")
						: `<div class="idc-issue info">${i("check")}<div>${__(
								"Looks ready to print."
						  )}</div></div>`
				}
			</div>
			<div class="idc-sec">
				<div class="idc-empty-note" style="text-align:left;padding:0">${__(
					"Click an element on the card to edit it. Add text, images and data fields from the left panel."
				)}</div>
			</div>`;
	}

	inspector_html(el) {
		const i = slcm.id_card.icon;
		const esc = frappe.utils.escape_html;
		const st = el.style || {};
		const b = this.box(this.selected) || { w: el.width || 0, h: el.height || 0 };
		const rot = (/rotate\((-?[\d.]+)deg\)/.exec(st.transform || "") || [0, 0])[1];
		const num = (prop, label, value, extra = "") =>
			`<label class="idc-input"><span>${label}</span><input type="number" step="0.5" data-prop="${prop}" data-type="num" value="${
				value === undefined || value === "" ? "" : round1(+value)
			}" ${extra}></label>`;

		let html = `
			<div class="idc-insp-head">
				<span class="idc-field-ico">${i(this.layer_icon(el), 14)}</span>
				<input data-prop="name" data-type="str" value="${esc(el.name || "")}" placeholder="${esc(
			this.layer_name(el)
		)}" title="${__("Rename layer")}">
				<button class="idc-btn" data-el="duplicate" title="${__("Duplicate")} (Ctrl+D)">${i(
			"copy",
			15
		)}</button>
				<button class="idc-btn" data-el="lock" title="${el.locked ? __("Unlock") : __("Lock")}">${i(
			el.locked ? "lock" : "unlock",
			15
		)}</button>
				<button class="idc-btn danger" data-el="remove" title="${__("Delete")} (Del)">${i(
			"trash",
			15
		)}</button>
			</div>`;

		if (el.type === "text") {
			const tokens = (this.meta.tokens || []).filter((t) => t.kind === "text");
			const font_options = IDC_FONTS.map(
				([v, l]) =>
					`<option value="${esc(v)}" ${
						st.fontFamily === v ? "selected" : ""
					}>${l}</option>`
			);
			if (st.fontFamily && !IDC_FONTS.some(([v]) => v === st.fontFamily)) {
				font_options.unshift(
					`<option value="${esc(st.fontFamily)}" selected>${esc(st.fontFamily)}</option>`
				);
			}
			const weight_bold = ["bold", "600", "700", "800", "900"].includes(
				String(st.fontWeight)
			);
			const align = st.textAlign || "left";
			html += `
				<div class="idc-sec">
					<div class="idc-sec-title">${__("Content")}</div>
					<label class="idc-input"><textarea data-prop="content" data-type="str" rows="2">${esc(
						el.content || ""
					)}</textarea></label>
					<div class="idc-row">
						<label class="idc-input" style="flex:1"><select data-insert-token>
							<option value="">${__("Insert field…")}</option>
							${tokens.map((t) => `<option value="${t.key}">${esc(t.label)}</option>`).join("")}
						</select></label>
					</div>
				</div>
				<div class="idc-sec">
					<div class="idc-sec-title">${__("Typography")}</div>
					<label class="idc-input"><span>${__(
						"Font"
					)}</span><select data-prop="style.fontFamily" data-type="str">${font_options.join(
				""
			)}</select></label>
					<div class="idc-grid2">
						<label class="idc-input"><span>${__(
							"Size"
						)}</span><input type="number" min="3" step="0.5" data-prop="style.fontSize" data-type="px" value="${
				parseFloat(st.fontSize) || 16
			}"></label>
						<label class="idc-input"><span>${__(
							"Colour"
						)}</span><input type="color" data-prop="style.color" data-type="str" value="${slcm.id_card.to_hex(
				st.color,
				"#000000"
			)}"></label>
					</div>
					<div class="idc-row">
						<div class="idc-seg">
							<button class="idc-btn ${weight_bold ? "active" : ""}" data-text="bold" title="${__(
				"Bold"
			)}"><b>B</b></button>
							<button class="idc-btn ${
								st.fontStyle === "italic" ? "active" : ""
							}" data-text="italic" title="${__("Italic")}"><i>I</i></button>
							<button class="idc-btn ${
								st.textDecoration === "underline" ? "active" : ""
							}" data-text="underline" title="${__("Underline")}"><u>U</u></button>
						</div>
						<div class="idc-seg">
							${["left", "center", "right"]
								.map(
									(a) =>
										`<button class="idc-btn ${
											align === a ? "active" : ""
										}" data-text-align="${a}" title="${__(a)}">${i(
											"text-" + a,
											15
										)}</button>`
								)
								.join("")}
						</div>
					</div>
					<div class="idc-grid2">
						<label class="idc-input"><span>${__(
							"Letter spacing"
						)}</span><input type="number" step="0.1" data-prop="style.letterSpacing" data-type="px" value="${
				parseFloat(st.letterSpacing) || 0
			}"></label>
						<label class="idc-input"><span>${__(
							"Line height"
						)}</span><input type="number" step="0.05" min="0.6" data-prop="style.lineHeight" data-type="str" value="${
				st.lineHeight && st.lineHeight !== "normal" ? parseFloat(st.lineHeight) : ""
			}" placeholder="${__("Auto")}"></label>
					</div>
					<label class="idc-input" style="margin-top:8px"><span>${__(
						"Letter case"
					)}</span><select data-prop="style.textTransform" data-type="str">
						${[
							["", __("As typed")],
							["uppercase", "UPPERCASE"],
							["capitalize", "Title Case"],
							["lowercase", "lowercase"],
						]
							.map(
								([v, l]) =>
									`<option value="${v}" ${
										(st.textTransform || "") === v ? "selected" : ""
									}>${l}</option>`
							)
							.join("")}
					</select></label>
				</div>
				<div class="idc-sec">
					<div class="idc-sec-title">${__("Text box")}</div>
					<label class="idc-toggle"><div>${__("Fixed width")}<small>${__(
				"Needed for alignment and wrapping"
			)}</small></div><input type="checkbox" data-textbox="width" ${
				el.width ? "checked" : ""
			}></label>
					<label class="idc-toggle"><div>${__(
						"Wrap onto lines"
					)}</div><input type="checkbox" data-textbox="wrap" ${
				el.wrap ? "checked" : ""
			} ${el.width ? "" : "disabled"}></label>
					<label class="idc-toggle"><div>${__("Shrink to fit")}<small>${__(
				"Long names get smaller instead of overflowing"
			)}</small></div><input type="checkbox" data-textbox="fit" ${el.fit ? "checked" : ""} ${
				el.width && !el.wrap ? "" : "disabled"
			}></label>
				</div>`;
		}

		if (el.type === "image") {
			const radius =
				st.borderRadius === "50%"
					? "circle"
					: st.clipPath && st.clipPath !== "none"
					? "triangle"
					: parseFloat(st.borderRadius) > 0
					? "rounded"
					: "rect";
			html += `
				<div class="idc-sec">
					<div class="idc-sec-title">${__("Image")}</div>
					<label class="idc-input"><span>${__("Source")}</span><select data-image="mapping">
						${IDC_IMAGE_SOURCES.map(
							([v, l]) =>
								`<option value="${v}" ${
									(el.mapping || "") === v ? "selected" : ""
								}>${__(l)}</option>`
						).join("")}
					</select></label>
					${
						el.mapping
							? ""
							: `<div class="idc-row"><button class="idc-btn outline" data-image="upload" style="flex:1">${i(
									"upload",
									14
							  )} ${
									el.content && !/placehold\.co/.test(el.content)
										? __("Replace image")
										: __("Upload image")
							  }</button></div>`
					}
					<div class="idc-grid2">
						<label class="idc-input"><span>${__("Fit")}</span><select data-prop="object_fit" data-type="str">
							<option value="cover" ${
								el.object_fit !== "contain" && el.object_fit !== "fill"
									? "selected"
									: ""
							}>${__("Fill (crop)")}</option>
							<option value="contain" ${el.object_fit === "contain" ? "selected" : ""}>${__(
				"Fit inside"
			)}</option>
							<option value="fill" ${el.object_fit === "fill" ? "selected" : ""}>${__("Stretch")}</option>
						</select></label>
						<label class="idc-input"><span>${__("Shape")}</span><select data-image="shape">
							<option value="rect" ${radius === "rect" ? "selected" : ""}>${__("Square corners")}</option>
							<option value="rounded" ${radius === "rounded" ? "selected" : ""}>${__("Rounded")}</option>
							<option value="circle" ${radius === "circle" ? "selected" : ""}>${__("Circle")}</option>
							<option value="triangle" ${radius === "triangle" ? "selected" : ""}>${__("Triangle")}</option>
						</select></label>
					</div>
				</div>`;
		}

		if (el.type === "rect") {
			html += `
				<div class="idc-sec">
					<div class="idc-sec-title">${__("Fill")}</div>
					<div class="idc-grid2">
						<label class="idc-input"><span>${__(
							"Colour"
						)}</span><input type="color" data-prop="style.backgroundColor" data-type="str" value="${slcm.id_card.to_hex(
				st.backgroundColor,
				"#e5e7eb"
			)}"></label>
						<label class="idc-input"><span>${__(
							"Corner radius"
						)}</span><input type="number" min="0" step="0.5" data-prop="style.borderRadius" data-type="radius" value="${
				st.borderRadius === "50%" ? "" : parseFloat(st.borderRadius) || 0
			}" placeholder="${st.borderRadius === "50%" ? __("Circle") : ""}"></label>
					</div>
				</div>`;
		}

		html += `
			<div class="idc-sec">
				<div class="idc-sec-title">${__("Position & size")}</div>
				<div class="idc-grid2">
					${num("x", "X", el.x)}
					${num("y", "Y", el.y)}
					${num(
						"width",
						__("Width"),
						el.type === "text" ? el.width : el.width,
						el.type === "text" && !el.width ? `placeholder="${__("Auto")}"` : ""
					)}
					${
						el.type === "text"
							? `<label class="idc-input"><span>${__(
									"Height"
							  )}</span><input type="number" value="${round1(
									b.h
							  )}" disabled></label>`
							: num("height", __("Height"), el.height)
					}
				</div>
				<div class="idc-grid2">
					<label class="idc-input"><span>${__(
						"Rotation°"
					)}</span><input type="number" step="1" data-prop="rotation" data-type="num" value="${
			+rot || 0
		}"></label>
					<label class="idc-input"><span>${__("Opacity")} <b data-opacity-label>${Math.round(
			(st.opacity === undefined ? 1 : +st.opacity) * 100
		)}%</b></span>
						<input type="range" min="0" max="1" step="0.05" data-prop="style.opacity" data-type="num" value="${
							st.opacity === undefined ? 1 : st.opacity
						}"></label>
				</div>
			</div>
			<div class="idc-sec">
				<div class="idc-sec-title">${__("Align to card")}</div>
				<div class="idc-row" style="justify-content:space-between">
					${["left", "hcenter", "right", "top", "vmiddle", "bottom"]
						.map(
							(a) =>
								`<button class="idc-btn outline" data-align="${a}" title="${__(
									"Align"
								)} ${a}">${i("align-" + a, 15)}</button>`
						)
						.join("")}
				</div>
				<div class="idc-sec-title" style="margin-top:12px">${__("Arrange")}</div>
				<div class="idc-row" style="justify-content:space-between">
					<button class="idc-btn outline" data-arrange="back" title="${__("Send to back")}">${i(
			"to-back",
			15
		)}</button>
					<button class="idc-btn outline" data-arrange="backward" title="${__("Send backward")}">${i(
			"backward",
			15
		)}</button>
					<button class="idc-btn outline" data-arrange="forward" title="${__("Bring forward")}">${i(
			"forward",
			15
		)}</button>
					<button class="idc-btn outline" data-arrange="front" title="${__("Bring to front")}">${i(
			"to-front",
			15
		)}</button>
					<button class="idc-btn outline" data-el="other-side" title="${__("Copy to the other side")}">${i(
			"swap",
			15
		)}</button>
				</div>
			</div>`;

		if (el.type !== "text") {
			const bs = this.border_settings(el);
			html += `
				<div class="idc-sec">
					<div class="idc-sec-title">${__("Border")}</div>
					<div class="idc-grid3">
						<label class="idc-input"><span>${__("Style")}</span><select data-border="style">
							${["none", "solid", "dashed", "dotted", "double"]
								.map(
									(v) =>
										`<option value="${v}" ${
											bs.style === v ? "selected" : ""
										}>${__(v)}</option>`
								)
								.join("")}
						</select></label>
						<label class="idc-input"><span>${__(
							"Width"
						)}</span><input type="number" min="0" step="0.5" data-border="width" value="${
				bs.width
			}"></label>
						<label class="idc-input"><span>${__(
							"Colour"
						)}</span><input type="color" data-border="color" value="${slcm.id_card.to_hex(
				bs.color,
				"#000000"
			)}"></label>
					</div>
					<div class="idc-row" style="margin-top:8px">
						${["top", "right", "bottom", "left"]
							.map(
								(sd) =>
									`<label class="idc-toggle" style="margin:0;gap:4px"><input type="checkbox" data-border="${sd}" ${
										bs[sd] ? "checked" : ""
									}> ${__(sd)}</label>`
							)
							.join("")}
					</div>
				</div>`;
		}
		return html;
	}

	border_settings(el) {
		if (el.border_settings) return el.border_settings;
		const st = el.style || {};
		if (st.borderStyle && st.borderStyle !== "none") {
			return {
				style: st.borderStyle,
				width: parseFloat(st.borderWidth) || 1,
				color: st.borderColor || "#000000",
				top: true,
				right: true,
				bottom: true,
				left: true,
			};
		}
		return {
			style: "none",
			width: 1,
			color: "#000000",
			top: true,
			right: true,
			bottom: true,
			left: true,
		};
	}

	apply_border(el, bs) {
		el.border_settings = bs;
		el.style = el.style || {};
		[
			"border",
			"borderWidth",
			"borderStyle",
			"borderColor",
			"borderTop",
			"borderRight",
			"borderBottom",
			"borderLeft",
		].forEach((k) => delete el.style[k]);
		["Top", "Right", "Bottom", "Left"].forEach((side) => {
			const on = bs[side.toLowerCase()] && bs.style !== "none";
			el.style[`border${side}Style`] = on ? bs.style : "none";
			el.style[`border${side}Width`] = on ? `${+bs.width || 0}px` : "0px";
			el.style[`border${side}Color`] = bs.color;
		});
	}

	set_prop(el, prop, type, raw) {
		let value = raw;
		if (type === "num") value = raw === "" ? undefined : parseFloat(raw);
		if (type === "px") value = raw === "" ? undefined : `${parseFloat(raw)}px`;
		if (type === "radius") value = raw === "" ? undefined : `${parseFloat(raw)}px`;
		if (type === "num" && Number.isNaN(value)) return;

		if (prop === "rotation") {
			el.style = el.style || {};
			if (value) el.style.transform = `rotate(${value}deg)`;
			else delete el.style.transform;
			return;
		}
		if (prop.startsWith("style.")) {
			const key = prop.slice(6);
			el.style = el.style || {};
			if (value === undefined || value === "") delete el.style[key];
			else el.style[key] = value;
			if (key === "letterSpacing" && parseFloat(raw) === 0) delete el.style[key];
			return;
		}
		if (value === undefined || value === "") delete el[prop];
		else el[prop] = value;
	}

	bind_inspector() {
		const $p = this.$right;
		const live = (e) => {
			const el = this.current();
			if (!el) return;
			const $t = $(e.currentTarget);
			this.set_prop(el, $t.data("prop"), $t.data("type"), $t.val());
			if ($t.data("prop") === "style.opacity")
				$p.find("[data-opacity-label]").text(Math.round(+$t.val() * 100) + "%");
			this.render_canvas();
		};
		$p.on("input", "[data-prop]", live);
		$p.on("change", "[data-prop]", (e) => {
			live(e);
			this.commit();
			if ($(e.currentTarget).data("prop") === "name") this.render_left();
		});
		$p.on("keydown", "[data-prop]", (e) => {
			if (e.key === "Escape") e.currentTarget.blur();
		});

		$p.on("change", "[data-insert-token]", (e) => {
			const key = e.target.value;
			const el = this.current();
			if (!key || !el) return;
			const $ta = $p.find("[data-prop='content']");
			const ta = $ta[0];
			const token = `{{${key}}}`;
			const text = el.content || "";
			const start =
				ta && document.activeElement === ta
					? ta.selectionStart
					: this._caret ?? text.length;
			const end =
				ta && document.activeElement === ta ? ta.selectionEnd : this._caret ?? text.length;
			el.content = text.slice(0, start) + token + text.slice(end);
			delete el.mapping;
			this.commit();
			this.refresh_all();
		});
		$p.on(
			"keyup click blur",
			"[data-prop='content']",
			(e) => (this._caret = e.currentTarget.selectionStart)
		);

		$p.on("click", "[data-el]", (e) => {
			const act = $(e.currentTarget).data("el");
			const el = this.current();
			if (!el) return;
			if (act === "duplicate") this.duplicate();
			else if (act === "remove") this.remove();
			else if (act === "other-side") this.copy_to_other_side();
			else if (act === "lock") {
				el.locked = !el.locked;
				if (!el.locked) delete el.locked;
				this.commit();
				this.refresh_all();
			}
		});
		$p.on("click", "[data-align]", (e) => this.align($(e.currentTarget).data("align")));
		$p.on("click", "[data-arrange]", (e) => {
			const n = this.elements.length - 1;
			const at = this.selected;
			const to = {
				back: 0,
				backward: Math.max(0, at - 1),
				forward: Math.min(n, at + 1),
				front: n,
			}[$(e.currentTarget).data("arrange")];
			this.move_layer(at, to);
		});
		$p.on("click", "[data-text]", (e) => {
			const el = this.current();
			if (!el) return;
			const st = (el.style = el.style || {});
			const what = $(e.currentTarget).data("text");
			if (what === "bold")
				st.fontWeight = ["bold", "600", "700", "800", "900"].includes(
					String(st.fontWeight)
				)
					? "normal"
					: "bold";
			if (what === "italic")
				st.fontStyle === "italic" ? delete st.fontStyle : (st.fontStyle = "italic");
			if (what === "underline")
				st.textDecoration === "underline"
					? delete st.textDecoration
					: (st.textDecoration = "underline");
			this.commit();
			this.refresh_all();
		});
		$p.on("click", "[data-text-align]", (e) => {
			const el = this.current();
			if (!el) return;
			const a = $(e.currentTarget).data("text-align");
			el.style = el.style || {};
			if (a !== "left" && !el.width) {
				// Alignment only shows inside a fixed-width box.
				const b = this.box(this.selected);
				el.width = round1(Math.max(b ? b.w : 80, 80));
			}
			if (a === "left") delete el.style.textAlign;
			else el.style.textAlign = a;
			this.commit();
			this.refresh_all();
		});
		$p.on("change", "[data-textbox]", (e) => {
			const el = this.current();
			if (!el) return;
			const key = $(e.currentTarget).data("textbox");
			const on = e.currentTarget.checked;
			if (key === "width") {
				if (on) {
					const b = this.box(this.selected);
					el.width = round1(b ? b.w : 100);
				} else {
					delete el.width;
					delete el.wrap;
					delete el.fit;
				}
			} else if (on) {
				el[key] = true;
				if (key === "wrap") delete el.fit;
			} else delete el[key];
			this.commit();
			this.refresh_all();
		});
		$p.on("change", "[data-image='mapping']", (e) => {
			const el = this.current();
			if (!el) return;
			const v = e.target.value;
			if (v) {
				el.mapping = v;
				el.content = "";
			} else {
				delete el.mapping;
			}
			this.commit();
			this.refresh_all();
			if (!v) this.upload_selected();
		});
		$p.on("click", "[data-image='upload']", () => this.upload_selected());
		$p.on("change", "[data-image='shape']", (e) => {
			const el = this.current();
			if (!el) return;
			const st = (el.style = el.style || {});
			const shape = e.target.value;
			delete st.clipPath;
			if (shape === "circle") st.borderRadius = "50%";
			else if (shape === "rounded") st.borderRadius = "8px";
			else delete st.borderRadius;
			if (shape === "triangle") st.clipPath = "polygon(50% 0%, 0% 100%, 100% 100%)";
			el.shape = shape === "triangle" ? "triangle" : shape === "circle" ? "circle" : "rect";
			this.commit();
			this.refresh_all();
		});
		$p.on("input change", "[data-border]", (e) => {
			const el = this.current();
			if (!el) return;
			const bs = { ...this.border_settings(el) };
			const key = $(e.currentTarget).data("border");
			bs[key] =
				e.currentTarget.type === "checkbox"
					? e.currentTarget.checked
					: e.currentTarget.value;
			if (key === "width") bs.width = parseFloat(bs.width) || 0;
			if (key !== "style" && bs.style === "none" && e.type === "change" && key !== "color")
				bs.style = "solid";
			this.apply_border(el, bs);
			this.render_canvas();
			if (e.type === "change") {
				this.commit();
				if (key !== "color") this.render_inspector();
			}
		});
		$p.on("input", "[data-card='bg']", (e) => {
			this.data.bg_color[this.side] = e.target.value;
			this.render_canvas();
		});
		$p.on("change", "[data-card='bg']", () => this.commit());
		$p.on("click", "[data-card='bg-both']", () => {
			this.data.bg_color.front = this.data.bg_color.back = this.data.bg_color[this.side];
			this.commit();
			frappe.show_alert(
				{ message: __("Background applied to both sides."), indicator: "green" },
				2
			);
		});
	}

	upload_selected() {
		const index = this.selected;
		const side = this.side;
		this.upload_image((url) => {
			const el = this.data[side][index];
			if (!el) return;
			el.content = url;
			delete el.mapping;
			this.commit();
			this.refresh_all();
		});
	}

	// ----- print check --------------------------------------------------

	issues() {
		const out = [];
		if (!this.data) return out;
		const doc = this.frm.doc;
		const [w, h] = this.units;
		const seen = new Set();
		const once = (key, issue) => {
			if (!seen.has(key)) {
				seen.add(key);
				out.push(issue);
			}
		};
		let has_photo = false;
		let has_qr = false;

		["front", "back"].forEach((side) => {
			this.data[side].forEach((el, index) => {
				if (el.hidden) return;
				const ref = { side, index };
				const name = this.layer_name(el);
				if (el.type === "text") {
					const unknown = slcm.id_card.unknown_tokens(el.content, el.mapping, this.meta);
					if (unknown.length) {
						out.push({
							level: "error",
							...ref,
							text: __("“{0}” uses unknown field {1}; it will print as typed.", [
								name,
								unknown.join(", "),
							]),
						});
					}
					if (side === this.side && !(el.style && el.style.transform)) {
						const b = this.box(index);
						if (
							b &&
							(b.x < -1 || b.y < -1 || b.x + b.w > w + 1 || b.y + b.h > h + 1)
						) {
							out.push({
								level: "warn",
								...ref,
								text: __("“{0}” runs past the card edge and will be cut off.", [
									name,
								]),
							});
						}
					}
				}
				if (el.type === "image") {
					if (el.mapping === "photo") has_photo = true;
					if (el.mapping === "qr_code_image") has_qr = true;
					const needs = {
						institute_logo: __("Institute Logo"),
						authority_signature: __("Authority Signature"),
						watermark_image: __("Watermark Image"),
					};
					if (needs[el.mapping] && !doc[el.mapping]) {
						once(el.mapping, {
							level: "warn",
							...ref,
							text: __(
								"Upload the {0} in the Branding tab; it is blank on cards now.",
								[needs[el.mapping]]
							),
						});
					}
					if (!el.mapping && (!el.content || /placehold\.co/.test(el.content))) {
						out.push({
							level: "warn",
							...ref,
							text: __("“{0}” is a placeholder. Upload the real image.", [name]),
						});
					}
				}
			});
		});
		if (!this.data.front.filter((el) => !el.hidden).length)
			out.unshift({ level: "error", text: __("The front side is empty.") });
		if (!has_photo && ["Student", "Faculty", "Driver"].includes(doc.card_type || "Student")) {
			out.push({ level: "info", text: __("There is no photo on the card.") });
		}
		if (!has_qr)
			out.push({
				level: "info",
				text: __("There is no QR code, so the card can't be verified by scanning."),
			});
		return out;
	}

	issue_html(x) {
		const icon = { error: "alert", warn: "alert", info: "info" }[x.level];
		const ref =
			x.index === undefined ? "" : `data-issue-side="${x.side}" data-index="${x.index}"`;
		return `<div class="idc-issue ${x.level}" ${ref}>${slcm.id_card.icon(
			icon
		)}<div>${frappe.utils.escape_html(x.text)}</div></div>`;
	}

	render_health() {
		if (!this.$root) return;
		const issues = this.issues();
		const serious = issues.filter((x) => x.level !== "info").length;
		const $btn = this.$root.find("[data-act='health']");
		$btn.removeClass("ok warn")
			.addClass(serious ? "warn" : "ok")
			.html(
				serious
					? `${slcm.id_card.icon("alert")} ${__("{0} to review", [serious])}`
					: `${slcm.id_card.icon("check")} ${__("Print ready")}`
			);
		this.$root
			.find(".idc-health-pop")
			.html(
				issues.length
					? issues.map((x) => this.issue_html(x)).join("")
					: `<div class="idc-issue info">${slcm.id_card.icon("check")}<div>${__(
							"Looks ready to print."
					  )}</div></div>`
			);
	}

	// ----- starters -------------------------------------------------------

	open_starters() {
		const card_type = this.frm.doc.card_type || "Student";
		const starters = (slcm.id_card.starters || []).slice();
		let filter = starters.some((s) => s.card_type === card_type) ? "match" : "all";
		const ctx = slcm.id_card.design_context(this.frm, this.meta, false);

		const d = new frappe.ui.Dialog({
			title: __("Choose a starting point"),
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "gallery" }],
		});
		const $g = d.fields_dict.gallery.$wrapper;

		const render = () => {
			const list = starters.filter((s) => filter === "all" || s.card_type === card_type);
			$g.html(`
				<div class="idc-gallery-filter">
					<button class="idc-btn ${filter === "match" ? "active" : "outline"}" data-filter="match">${__(
				"For {0} cards",
				[__(card_type)]
			)}</button>
					<button class="idc-btn ${filter === "all" ? "active" : "outline"}" data-filter="all">${__(
				"All starters"
			)}</button>
				</div>
				<div class="idc-gallery">
					<div class="idc-starter" data-blank="horizontal">
						<div class="idc-starter-thumb"><div class="idc-blank">${slcm.id_card.icon("plus")}</div></div>
						<div class="idc-starter-body"><div class="idc-starter-title">${__(
							"Blank landscape"
						)}</div><div class="idc-starter-desc">85.6 × 54 mm</div></div>
					</div>
					<div class="idc-starter" data-blank="vertical">
						<div class="idc-starter-thumb"><div class="idc-blank portrait">${slcm.id_card.icon(
							"plus"
						)}</div></div>
						<div class="idc-starter-body"><div class="idc-starter-title">${__(
							"Blank portrait"
						)}</div><div class="idc-starter-desc">54 × 85.6 mm</div></div>
					</div>
					${list
						.map(
							(s) => `<div class="idc-starter" data-starter="${s.id}">
								<div class="idc-starter-thumb" data-thumb="${s.id}"></div>
								<div class="idc-starter-body">
									<div class="idc-starter-title">${frappe.utils.escape_html(s.name)}</div>
									<div class="idc-starter-desc">${frappe.utils.escape_html(s.description || "")}</div>
									<span class="idc-pill">${__(s.card_type)}</span><span class="idc-pill">${
								s.data.orientation === "vertical"
									? __("Portrait")
									: __("Landscape")
							}</span>
									${s.data.back && s.data.back.length ? `<span class="idc-pill">${__("Front + back")}</span>` : ""}
								</div>
							</div>`
						)
						.join("")}
				</div>`);
			list.forEach((s) => {
				const data = slcm.id_card.normalise(JSON.parse(JSON.stringify(s.data)));
				const $thumb = $g.find(`[data-thumb='${s.id}']`);
				$thumb.append(
					slcm.id_card.render_thumbnail(
						data,
						"front",
						ctx,
						data.orientation === "vertical" ? 92 : 170,
						150
					)
				);
				slcm.id_card.apply_fit($thumb);
			});
		};

		const apply = (data, starter_card_type) => {
			const go = () => {
				this.data = slcm.id_card.normalise(data);
				this.side = "front";
				this.selected = null;
				this.zoom = null;
				this.commit();
				this.refresh_all();
				d.hide();
				if (starter_card_type && starter_card_type !== card_type && this.frm.is_new()) {
					this.frm.set_value("card_type", starter_card_type);
				}
			};
			const has_design = this.data && (this.data.front.length || this.data.back.length);
			if (has_design) {
				frappe.confirm(
					__("Replace the current design? You can undo this with Ctrl+Z."),
					go
				);
			} else go();
		};

		$g.on("click", "[data-filter]", (e) => {
			filter = $(e.currentTarget).data("filter");
			render();
		});
		$g.on("click", "[data-blank]", (e) =>
			apply({ orientation: $(e.currentTarget).data("blank") })
		);
		$g.on("click", "[data-starter]", (e) => {
			const s = starters.find((x) => x.id === $(e.currentTarget).data("starter"));
			if (s) apply(JSON.parse(JSON.stringify(s.data)), s.card_type);
		});

		d.show();
		render();
	}
}

function round1(n) {
	return Math.round((+n || 0) * 10) / 10;
}

slcm.id_card.IDCardStudio = IDCardStudio;

// ---------------------------------------------------------------------
// Form
// ---------------------------------------------------------------------

frappe.ui.form.on("ID Card Template", {
	refresh(frm) {
		// The designer needs the full width of the form.
		frm.page.wrapper
			.find(".layout-side-section")
			.toggle(frm.doc.template_creation_mode !== "Drag and Drop");

		const modes = ["Drag and Drop", "Jinja Template", "Field Mapping"];
		if (frm.doc.template_creation_mode === "Canva") modes.push("Canva");
		frm.set_df_property("template_creation_mode", "options", modes.join("\n"));

		frm.add_custom_button(__("Preview"), () => slcm.id_card.show_preview(frm));

		if (!frm.is_new()) {
			if ((frm.doc.card_type || "Student") === "Student") {
				frm.add_custom_button(
					__("Generate for Students"),
					() => {
						slcm.id_card.pending_tool_template = frm.doc.name;
						frappe.set_route("Form", "ID Card Generation Tool");
					},
					__("Use Template")
				);
			}
			frm.add_custom_button(
				__("Create a Single Card"),
				() =>
					frappe.new_doc("ID Card Generation", {
						card_type: frm.doc.card_type || "Student",
						id_card_template: frm.doc.name,
					}),
				__("Use Template")
			);
		}

		frm.trigger("render_editor");
	},

	template_creation_mode(frm) {
		frm.page.wrapper
			.find(".layout-side-section")
			.toggle(frm.doc.template_creation_mode !== "Drag and Drop");
		frm.trigger("render_editor");
	},

	card_type(frm) {
		if (frm.idc_studio) frm.idc_studio.on_card_type_change();
	},

	institute_logo: (frm) => frm.idc_studio && frm.idc_studio.refresh_all(),
	authority_signature: (frm) => frm.idc_studio && frm.idc_studio.refresh_all(),
	watermark_image: (frm) => frm.idc_studio && frm.idc_studio.refresh_all(),
	institute_name: (frm) => frm.idc_studio && frm.idc_studio.refresh_all(),

	render_editor(frm) {
		if (frm.doc.template_creation_mode === "Drag and Drop") {
			const studio = frm.idc_studio;
			const same_doc =
				studio &&
				(studio.docname === frm.docname ||
					(frm.doc.canvas_data || "") === studio.last_json);
			if (studio && same_doc && studio.$root) {
				studio.sync_from_doc();
			} else {
				if (studio) studio.destroy();
				frm.idc_studio = new IDCardStudio(frm);
				frm.idc_studio.init();
			}
		} else if (frm.doc.template_creation_mode === "Canva") {
			frm.fields_dict.canva_button.$wrapper.html(`
				<div class="alert alert-warning" style="margin:0">
					${__(
						"Canva mode is retired. Export your Canva design as PNG, switch to <b>Drag and Drop</b>, and add it with <b>Add → Background</b>. Then place data fields on top."
					)}
				</div>`);
		}
	},
});

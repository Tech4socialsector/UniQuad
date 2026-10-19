// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

// ── Built-in theme presets ────────────────────────────────────────────
const PP_PRESETS = [
    {
        name: "NLSIU Maroon (Default)",
        primary_color: "#920c24", secondary_color: "#c9a84c",
        background_color: "#f0f2f5", card_background: "#ffffff",
        nav_text_color: "#ffffff",
        sidebar_bg_color: "#ffffff", sidebar_text_color: "#475569",
        success_color: "#008000", warning_color: "#d97706",
        danger_color: "#920c24", info_color: "#0369a1",
    },
    {
        name: "Rose Red",
        primary_color: "#e11d48", secondary_color: "#c8a14b",
        background_color: "#f3f6f5", card_background: "#ffffff",
        nav_text_color: "#ffffff",
        sidebar_bg_color: "#2b2e4a", sidebar_text_color: "#e8e9f0",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#0369a1",
    },
    {
        name: "Ocean Blue",
        primary_color: "#1a3c6e", secondary_color: "#c8a14b",
        background_color: "#f0f2f5", card_background: "#ffffff",
        nav_text_color: "#ffffff",
        sidebar_bg_color: "#1a2744", sidebar_text_color: "#e8edf5",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#0369a1",
    },
    {
        name: "Forest Green",
        primary_color: "#14532d", secondary_color: "#f59e0b",
        background_color: "#f0f4f1", card_background: "#ffffff",
        nav_text_color: "#ffffff",
        sidebar_bg_color: "#1a3326", sidebar_text_color: "#e6f0ea",
        success_color: "#15803d", warning_color: "#b45309",
        danger_color: "#dc2626", info_color: "#0369a1",
    },
    {
        name: "Slate Dark",
        primary_color: "#1e293b", secondary_color: "#38bdf8",
        background_color: "#f1f5f9", card_background: "#ffffff",
        nav_text_color: "#ffffff",
        sidebar_bg_color: "#1e293b", sidebar_text_color: "#e2e8f0",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#0284c7",
    },
    {
        name: "Deep Purple",
        primary_color: "#4c1d95", secondary_color: "#f59e0b",
        background_color: "#f5f3ff", card_background: "#ffffff",
        nav_text_color: "#ffffff",
        sidebar_bg_color: "#2e1065", sidebar_text_color: "#ede9fe",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#7c3aed",
    },
    {
        name: "Teal Modern",
        primary_color: "#0f4c5c", secondary_color: "#06b6d4",
        background_color: "#f0f9ff", card_background: "#ffffff",
        nav_text_color: "#ffffff",
        sidebar_bg_color: "#0c3340", sidebar_text_color: "#e0f2f8",
        success_color: "#0d9488", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#0284c7",
    },
    {
        name: "NLSIU Navy",
        font_family: "Merriweather",
        primary_color: "#2b2e4a", secondary_color: "#920c24",
        background_color: "#f3f6f5", card_background: "#ffffff",
        nav_text_color: "#ffffff",
        sidebar_bg_color: "#2b2e4a", sidebar_text_color: "#e8e9f0",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#0369a1",
    },
];

// Fallback colours used by the in-form previews when a field is blank
const PP_FALLBACK_PRIMARY = "#920c24";


// ── Form event handlers ───────────────────────────────────────────────
frappe.ui.form.on("Parent Portal Settings", {
    refresh(frm) {
        _add_action_buttons(frm);
        _render_preset_bar(frm);
        _render_all_previews(frm);
    },

    // Theme color triggers
    primary_color:    (frm) => _render_all_previews(frm),
    secondary_color:  (frm) => _render_all_previews(frm),
    background_color: (frm) => _render_color_preview(frm),
    card_background:  (frm) => _render_color_preview(frm),
    nav_text_color:   (frm) => _render_color_preview(frm),
    success_color:    (frm) => _render_color_preview(frm),
    warning_color:    (frm) => _render_color_preview(frm),
    danger_color:     (frm) => _render_color_preview(frm),
    info_color:       (frm) => _render_color_preview(frm),
    sidebar_bg_color:   (frm) => _render_color_preview(frm),
    sidebar_text_color: (frm) => _render_color_preview(frm),

    // Grade color triggers
    grade_excellent_color: (frm) => _render_color_preview(frm),
    grade_good_color:      (frm) => _render_color_preview(frm),
    grade_average_color:   (frm) => _render_color_preview(frm),
    grade_fail_color:      (frm) => _render_color_preview(frm),
    grade_excellent_label: (frm) => _render_color_preview(frm),
    grade_good_label:      (frm) => _render_color_preview(frm),
    grade_average_label:   (frm) => _render_color_preview(frm),
    grade_fail_label:      (frm) => _render_color_preview(frm),

    // Layout triggers
    sidebar_width:  (frm) => _render_layout_preview(frm),
    nav_height:     (frm) => _render_layout_preview(frm),
    corner_style:   (frm) => _render_layout_preview(frm),
    layout_density: (frm) => _render_layout_preview(frm),

    // Typography triggers
    font_family: (frm) => _render_layout_preview(frm),
    font_size:   (frm) => _render_layout_preview(frm),
});


// ── Action buttons ────────────────────────────────────────────────────
function _add_action_buttons(frm) {
    frm.add_custom_button(__("Preview Portal"), () => _open_preview_dialog(frm));

    frm.add_custom_button(__("Reset to Defaults"), () => {
        frappe.confirm(
            __("Reset all settings to factory defaults? Uploaded logo and favicon are kept."),
            () => {
                frappe.call({
                    method: "slcm.slcm.doctype.parent_portal_settings.parent_portal_settings.get_default_settings",
                }).then((r) => {
                    const values = Object.assign({}, r.message || {});
                    delete values.portal_logo;
                    delete values.portal_favicon;
                    return frm.set_value(values);
                }).then(() => {
                    frappe.show_alert({ message: __("Defaults restored — click Save to apply."), indicator: "blue" });
                    _render_all_previews(frm);
                });
            }
        );
    }, __("Actions"));
}

function _open_preview_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Preview Parent Portal"),
        fields: [
            {
                fieldname: "student", fieldtype: "Link", options: "Student Master",
                label: __("Preview as the parent of"),
                description: __("Leave blank to use the first student with a linked parent. You can switch students from the preview banner."),
            },
        ],
        primary_action_label: __("Open Preview"),
        primary_action(values) {
            const url = "/parent-portal" + (values.student ? "?ward=" + encodeURIComponent(values.student) : "");
            // Open synchronously (inside the click) so the browser doesn't block the pop-up
            const win = window.open("about:blank", "_blank");
            d.hide();
            const go = () => { if (win) { win.location.href = url; } else { window.location.href = url; } };
            if (frm.is_dirty()) {
                frm.save().then(go).catch(() => { if (win) win.close(); });
            } else {
                go();
            }
        },
    });
    if (frm.is_dirty()) {
        d.set_df_property("student", "description",
            __("You have unsaved changes — they will be saved before the preview opens."));
    }
    d.show();
}


// ── Color Preset bar ─────────────────────────────────────────────────
function _render_preset_bar(frm) {
    const wrapper = _section_container(frm, "theme_section");
    if (!wrapper) return;
    if (wrapper.find(".pp-preset-bar").length) return;

    const buttons = PP_PRESETS.map((preset, idx) => `
        <button class="pp-preset-btn" data-idx="${idx}"
            title="${preset.name}"
            style="width:28px;height:28px;border-radius:50%;border:2px solid transparent;
                   cursor:pointer;background:${preset.primary_color};padding:0;
                   transition:transform 0.15s,border-color 0.15s;flex-shrink:0;"
            onmouseover="this.style.transform='scale(1.2)';this.style.borderColor='#fff';"
            onmouseout="this.style.transform='scale(1)';this.style.borderColor='transparent';">
        </button>`).join("");

    const html = `
        <div class="pp-preset-bar" style="padding:10px 0 6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <span style="font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;
                       letter-spacing:.06em;white-space:nowrap;">Quick Themes:</span>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            ${buttons}
          </div>
        </div>`;

    const $bar = $(html).addClass("col-sm-12");
    (_section_body(wrapper) || wrapper).prepend($bar);

    $bar.find(".pp-preset-btn").on("click", function () {
        const preset = PP_PRESETS[$(this).data("idx")];
        const { name, ...values } = preset;
        frm.set_value(values).then(() => {
            frappe.show_alert({ message: __("Theme {0} applied — click Save.", [frappe.utils.escape_html(name)]), indicator: "green" });
            _render_all_previews(frm);
        });
    });
}


// ── Master render ─────────────────────────────────────────────────────
function _render_all_previews(frm) {
    _render_color_preview(frm);
    _render_layout_preview(frm);
}


// ── Color / Theme preview ─────────────────────────────────────────────
function _render_color_preview(frm) {
    const d = frm.doc;
    const primary   = d.primary_color   || PP_FALLBACK_PRIMARY;
    const secondary = d.secondary_color || "#c9a84c";
    const bg        = d.background_color || "#f0f2f5";
    const card      = d.card_background  || "#ffffff";
    const navText   = d.nav_text_color   || "#ffffff";
    const success   = d.success_color   || "#16a34a";
    const warning   = d.warning_color   || "#d97706";
    const danger    = d.danger_color    || "#dc2626";
    const info      = d.info_color      || "#0369a1";

    const gExc = d.grade_excellent_color || "#16a34a";
    const gGood= d.grade_good_color      || "#0369a1";
    const gAvg = d.grade_average_color   || "#d97706";
    const gFail= d.grade_fail_color      || "#dc2626";

    const gExcLabel = d.grade_excellent_label || "A+ / A";
    const gGoodLabel= d.grade_good_label      || "B+ / B";
    const gAvgLabel = d.grade_average_label   || "C+ / C";
    const gFailLabel= d.grade_fail_label      || "D / F";

    const html = `
    <div style="padding:14px 0 4px;">
      <div class="pp-preview-row">
        <div class="pp-preview-group">
          <div class="pp-preview-label">Theme Palette</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;">
            ${_swatch(primary,   "Primary", false, navText)}
            ${_swatch(secondary, "Accent")}
            ${_swatch(bg,        "Background", true)}
            ${_swatch(card,      "Card", true)}
          </div>
        </div>
        <div class="pp-preview-group">
          <div class="pp-preview-label">Status Colors</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;">
            ${_swatch(success, "Success")}
            ${_swatch(warning, "Warning")}
            ${_swatch(danger,  "Danger")}
            ${_swatch(info,    "Info")}
          </div>
        </div>
      </div>
      <div class="pp-preview-group" style="margin-top:12px;">
        <div class="pp-preview-label">Grade Bands</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
          ${_grade_badge(gExc, gExcLabel)}
          ${_grade_badge(gGood, gGoodLabel)}
          ${_grade_badge(gAvg, gAvgLabel)}
          ${_grade_badge(gFail, gFailLabel)}
          <span style="font-size:10px;color:#9ca3af;margin-left:4px;">← shown on Results page</span>
        </div>
      </div>
      <div class="pp-preview-group" style="margin-top:12px;">
        <div class="pp-preview-label">Mini Portal Card</div>
        ${_mini_portal_card(primary, secondary, bg, card, navText, d.sidebar_bg_color || "#ffffff", d.sidebar_text_color || "#475569")}
      </div>
    </div>`;

    _inject_into_section(frm, "theme_section", ".pp-color-preview", html);

    if (!document.getElementById("pp-preview-styles")) {
        $("<style id='pp-preview-styles'>").text(`
            .pp-preview-row { display:flex; gap:24px; flex-wrap:wrap; }
            .pp-preview-group { }
            .pp-preview-label {
                font-size:10px; font-weight:700; text-transform:uppercase;
                letter-spacing:.06em; color:#9ca3af; margin-bottom:6px;
            }
        `).appendTo("head");
    }
}


// ── Layout preview ─────────────────────────────────────────────────────
function _render_layout_preview(frm) {
    const d = frm.doc;
    const width   = d.sidebar_width  || "Normal";
    const size    = d.font_size      || "Normal";
    const corners = d.corner_style   || "Normal";
    const density = d.layout_density || "Normal";
    const primary = d.primary_color  || PP_FALLBACK_PRIMARY;
    const navH    = d.nav_height     || "Normal";
    const font    = d.font_family    || "Inter";

    const sbW    = width   === "Narrow" ? 48  : width   === "Wide" ? 72  : 60;
    const navPx  = navH    === "Compact" ? 13 : navH    === "Tall"  ? 19 : 15;
    const radius = corners === "Sharp"   ? "3px" : corners === "Pill" ? "12px" : "8px";
    const navPad = density === "Compact" ? "3px 6px" : "5px 8px";
    const fsPx   = size    === "Small"   ? "9px" : size === "Large" ? "11px" : "10px";
    const fontLabel = { "Inter": "Inter", "Poppins": "Poppins", "Roboto": "Roboto", "Merriweather": "Merriweather", "System Default": "System" }[font] || font;

    const navItems = [
        ["home", "Dashboard", true],
        ["event_available", "Attendance", false],
        ["school", "Results", false],
        ["payments", "Fees", false],
    ].map(([icon, label, active]) => `
        <div style="padding:${navPad};background:${active ? primary + "1a" : "transparent"};
             border-radius:${radius};font-size:${fsPx};color:${active ? primary : "#6b7280"};
             margin-bottom:2px;display:flex;align-items:center;gap:4px;
             border-left:2px solid ${active ? primary : "transparent"};">
          ${label}
        </div>`).join("");

    const sidebarEl = `
        <div style="width:${sbW}px;background:#fff;padding:5px 3px;border-radius:${radius};
             flex-shrink:0;border:1px solid #e5e7eb;">
          <div style="height:20px;background:linear-gradient(135deg,${primary},${primary}cc);
               border-radius:${radius};margin-bottom:5px;"></div>
          ${navItems}
        </div>`;

    const contentEl = `
        <div style="flex:1;padding:5px;display:flex;flex-direction:column;gap:3px;">
          <div style="height:8px;background:#e5e7eb;border-radius:${radius};width:55%;"></div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:3px;margin-top:2px;">
            <div style="height:20px;background:#fff;border-radius:${radius};border:1px solid #e5e7eb;"></div>
            <div style="height:20px;background:#fff;border-radius:${radius};border:1px solid #e5e7eb;"></div>
            <div style="height:20px;background:#fff;border-radius:${radius};border:1px solid #e5e7eb;"></div>
          </div>
          <div style="height:32px;background:#fff;border-radius:${radius};border:1px solid #e5e7eb;margin-top:2px;"></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:3px;">
            <div style="height:36px;background:#fff;border-radius:${radius};border:1px solid #e5e7eb;"></div>
            <div style="height:36px;background:#fff;border-radius:${radius};border:1px solid #e5e7eb;"></div>
          </div>
        </div>`;

    const tags = [
        `Width: ${width}`, `Nav: ${navH}`,
        `Corners: ${corners}`, `Density: ${density}`,
        `Font: ${fontLabel}`, `Size: ${size}`,
    ].map(t => `<span style="background:#f3f4f6;border:1px solid #e5e7eb;border-radius:4px;
                padding:2px 6px;font-size:9px;color:#6b7280;">${t}</span>`).join("");

    const html = `
    <div style="padding:14px 0 4px;">
      <div class="pp-preview-label">Layout Preview</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;">${tags}</div>
      <div style="background:#f0f2f5;border-radius:8px;overflow:hidden;border:1px solid #e5e7eb;">
        <div style="height:${navPx + 14}px;background:${primary};display:flex;align-items:center;
             padding:0 8px;gap:6px;">
          <div style="display:flex;gap:2px;flex-direction:column;">
            <div style="width:14px;height:1.5px;background:rgba(255,255,255,0.8);border-radius:1px;"></div>
            <div style="width:10px;height:1.5px;background:rgba(255,255,255,0.8);border-radius:1px;"></div>
            <div style="width:14px;height:1.5px;background:rgba(255,255,255,0.8);border-radius:1px;"></div>
          </div>
          <div style="width:22px;height:22px;background:rgba(255,255,255,0.15);border-radius:5px;"></div>
          <div style="flex:1;"></div>
          <div style="background:rgba(255,255,255,0.14);padding:2px 7px;border-radius:12px;
               font-size:8px;color:rgba(255,255,255,0.9);font-weight:600;">PARENT PORTAL</div>
          <div style="width:18px;height:18px;background:rgba(255,255,255,0.2);border-radius:50%;"></div>
        </div>
        <div style="padding:5px;display:flex;gap:4px;">
          ${sidebarEl}${contentEl}
        </div>
      </div>
    </div>`;

    _inject_into_section(frm, "layout_section", ".pp-layout-preview", html);
}


// ── Mini portal card ──────────────────────────────────────────────────
function _mini_portal_card(primary, secondary, bg, card, navText, sidebarBg, sidebarText) {
    return `
    <div style="width:280px;border-radius:10px;overflow:hidden;border:1px solid #e5e7eb;font-family:'Inter',sans-serif;">
      <div style="background:${primary};height:32px;display:flex;align-items:center;
           padding:0 10px;gap:8px;">
        <div style="width:18px;height:18px;background:rgba(255,255,255,0.2);border-radius:4px;"></div>
        <div style="width:60px;height:6px;background:${navText}33;border-radius:3px;"></div>
        <div style="flex:1;"></div>
        <div style="background:rgba(255,255,255,0.14);padding:2px 6px;border-radius:10px;
             font-size:8px;color:rgba(255,255,255,0.9);font-weight:600;">PARENT</div>
        <div style="width:16px;height:16px;background:${secondary};border-radius:50%;"></div>
      </div>
      <div style="display:flex;background:${bg};">
        <div style="width:64px;background:${sidebarBg};padding:6px 4px;border-right:1px solid rgba(0,0,0,0.06);">
          <div style="height:16px;background:linear-gradient(135deg,${primary},${primary}cc);border-radius:5px;margin-bottom:5px;"></div>
          ${["Dashboard","Attendance","Results","Fees"].map((l, i) => `
          <div style="padding:3px 5px;margin-bottom:2px;border-radius:4px;font-size:7px;
               color:${i===0 ? primary : sidebarText};
               background:${i===0 ? primary + "1a" : "transparent"};
               border-left:2px solid ${i===0 ? primary : "transparent"};">
            ${l}
          </div>`).join("")}
        </div>
        <div style="flex:1;padding:6px;">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:4px;">
            <div style="height:28px;background:${card};border:1px solid #e5e7eb;border-radius:6px;"></div>
            <div style="height:28px;background:${card};border:1px solid #e5e7eb;border-radius:6px;"></div>
          </div>
          <div style="height:36px;background:${card};border:1px solid #e5e7eb;border-radius:6px;"></div>
        </div>
      </div>
    </div>`;
}


// ── Helpers ───────────────────────────────────────────────────────────
function _swatch(color, label, bordered, textColor) {
    const border = bordered ? "border:1px solid #e5e7eb;" : "";
    const textDot = textColor
        ? `<div style="width:10px;height:10px;background:${textColor};border-radius:50%;
                      border:1px solid rgba(0,0,0,0.15);margin:2px auto 0;" title="Text: ${textColor}"></div>`
        : "";
    return `
    <div style="text-align:center;flex-shrink:0;">
      <div style="width:38px;height:38px;background:${color};border-radius:8px;${border}position:relative;
                  box-shadow:0 1px 3px rgba(0,0,0,0.12);">
        ${textDot}
      </div>
      <div style="font-size:9px;color:#6b7280;margin-top:3px;max-width:42px;
                  word-break:break-all;line-height:1.2;">${label}<br>
        <span style="font-family:monospace;font-size:8px;color:#9ca3af;">${color}</span>
      </div>
    </div>`;
}

function _grade_badge(color, label) {
    label = frappe.utils.escape_html(label || "");
    return `
    <div style="padding:4px 10px;background:${color}22;border:1px solid ${color}55;
         border-radius:20px;font-size:10px;font-weight:600;color:${color};white-space:nowrap;">
      ${label}
    </div>`;
}

// Section Break wrapper (Frappe 16: .wrapper; older: .$wrapper). Extra UI is
// added to .section-body as a full-width col-sm-12 row, so it lines up with the
// fields and wraps below/above the columns instead of becoming another column.
function _section_container(frm, fieldname) {
    const field = frm.get_field(fieldname);
    if (!field) return null;
    const el = field.wrapper || field.$wrapper;
    return el && el.length ? $(el) : null;
}

function _section_body(wrapper) {
    const body = wrapper.children(".section-body");
    return body.length ? body : null;
}

function _inject_into_section(frm, fieldname, selector, html) {
    const wrapper = _section_container(frm, fieldname);
    if (!wrapper) return;
    let el = wrapper.find(selector);
    if (!el.length) {
        el = $(`<div class="${selector.replace(".", "")} col-sm-12" style="padding-bottom:12px;"></div>`);
        (_section_body(wrapper) || wrapper).append(el);
    }
    el.html(html);
}

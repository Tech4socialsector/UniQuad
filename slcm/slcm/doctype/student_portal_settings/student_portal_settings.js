// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

// ── Built-in theme presets ────────────────────────────────────────────
const SP_PRESETS = [
    {
        name: "Ocean Blue (Default)",
        primary_color: "#1a3c6e", secondary_color: "#c8a14b",
        background_color: "#f0f2f5", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Light",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#0369a1",
    },
    {
        name: "Forest Green",
        primary_color: "#14532d", secondary_color: "#f59e0b",
        background_color: "#f0f4f1", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Dark",
        success_color: "#15803d", warning_color: "#b45309",
        danger_color: "#dc2626", info_color: "#0369a1",
    },
    {
        name: "Slate Dark",
        primary_color: "#1e293b", secondary_color: "#38bdf8",
        background_color: "#f1f5f9", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Dark",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#0284c7",
    },
    {
        name: "Deep Purple",
        primary_color: "#4c1d95", secondary_color: "#f59e0b",
        background_color: "#f5f3ff", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Dark",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#7c3aed",
    },
    {
        name: "Rose Gold",
        primary_color: "#881337", secondary_color: "#f59e0b",
        background_color: "#fff1f2", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Light",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#be123c", info_color: "#0369a1",
    },
    {
        name: "Teal Modern",
        primary_color: "#0f4c5c", secondary_color: "#06b6d4",
        background_color: "#f0f9ff", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Dark",
        success_color: "#0d9488", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#0284c7",
    },
];

const MENU_FIELDS = [
    "menu_dashboard", "menu_courses", "menu_attendance", "menu_timetable",
    "menu_exam_schedule", "menu_fees", "menu_results", "menu_announcements",
    "menu_enrollment", "menu_venue_booking",
    "menu_profile", "menu_documents", "menu_grade_appeal",
    "menu_transcript_request", "menu_placement", "menu_helpdesk"
];

const SP_DEFAULTS = {
    portal_title: "Student Portal", portal_subtitle: "",
    show_logo: 1, nav_brand_text: "", portal_favicon: "",
    font_family: "Poppins", font_size: "Normal",
    primary_color: "#1a3c6e", secondary_color: "#c8a14b",
    background_color: "#f0f2f5", card_background: "#ffffff",
    sidebar_theme: "Light", nav_text_color: "#ffffff",
    success_color: "#16a34a", warning_color: "#d97706",
    danger_color: "#dc2626", info_color: "#0369a1",
    grade_excellent_color: "#16a34a", grade_excellent_label: "A+ / A / S",
    grade_good_color: "#0369a1", grade_good_label: "B+ / B",
    grade_average_color: "#d97706", grade_average_label: "C+ / C",
    grade_color: "#000000", grade_fail_color: "#dc2626", grade_fail_label: "D / F",
    att_good_threshold: 75, att_warn_threshold: 60,
    att_label_good: "Good", att_label_warn: "Low", att_label_danger: "Critical",
    sidebar_position: "Left", sidebar_width: "Normal", nav_height: "Normal",
    corner_style: "Normal", layout_density: "Normal", show_student_id_sidebar: 1,
    show_announcements_ticker: 1, show_cgpa: 1, show_today_classes: 1,
    show_fee_summary: 1, show_quick_actions: 1,
    show_course_insights: 1, show_enrollment_info: 1,
    // Navigation menu toggles
    select_all_menus: 1,
    menu_dashboard: 1, menu_courses: 1, menu_attendance: 1, menu_timetable: 1,
    menu_exam_schedule: 1, menu_fees: 1, menu_results: 1, menu_announcements: 1,
    menu_enrollment: 1, menu_venue_booking: 1,
    menu_profile: 1, menu_documents: 1, menu_grade_appeal: 1,
    menu_transcript_request: 1, menu_placement: 1, menu_helpdesk: 1,
    // Fee reminders
    enable_fee_reminders: 1,
    reminder_sender_name: "Finance & Accounts Office",
    reminder_from_email: "",
    enable_7day_reminder: 1,
    reminder_7day_template: "Student Fee Reminder - 7 Days Before Due",
    enable_1day_reminder: 1,
    reminder_1day_template: "Student Fee Reminder - 1 Day Before Due",
    enable_overdue_notice: 1,
    overdue_notice_offset: 3,
    overdue_notice_template: "Student Fee Overdue Notice",
    custom_css: "",
};


// ── Form event handlers ───────────────────────────────────────────────
const form_events = {
    refresh(frm) {
        _add_action_buttons(frm);
        _render_preset_bar(frm);
        _render_all_previews(frm);
        _update_select_all_checkbox(frm);
        _toggle_reminder_fields(frm);
    },

    select_all_menus(frm) {
        if (frm.prevent_trigger) return;
        frm.prevent_trigger = true;
        const val = frm.doc.select_all_menus;
        MENU_FIELDS.forEach(field => {
            frm.set_value(field, val);
        });
        frm.prevent_trigger = false;
    },

    // Theme color triggers
    primary_color:    (frm) => _render_all_previews(frm),
    secondary_color:  (frm) => _render_all_previews(frm),
    background_color: (frm) => _render_color_preview(frm),
    card_background:  (frm) => _render_color_preview(frm),
    sidebar_theme:    (frm) => _render_all_previews(frm),
    nav_text_color:   (frm) => _render_color_preview(frm),
    success_color:    (frm) => _render_color_preview(frm),
    warning_color:    (frm) => _render_color_preview(frm),
    danger_color:     (frm) => _render_color_preview(frm),
    info_color:       (frm) => _render_color_preview(frm),

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
    sidebar_position: (frm) => _render_layout_preview(frm),
    sidebar_width:    (frm) => _render_layout_preview(frm),
    nav_height:       (frm) => _render_layout_preview(frm),
    corner_style:     (frm) => _render_layout_preview(frm),
    layout_density:   (frm) => _render_layout_preview(frm),

    // Typography triggers
    font_family: (frm) => _render_layout_preview(frm),
    font_size:   (frm) => _render_layout_preview(frm),

    // Reminder visibility toggles
    enable_fee_reminders(frm) { _toggle_reminder_fields(frm); },
    enable_7day_reminder(frm) { _toggle_reminder_sub_fields(frm, "7day"); },
    enable_1day_reminder(frm) { _toggle_reminder_sub_fields(frm, "1day"); },
    enable_overdue_notice(frm) { _toggle_reminder_sub_fields(frm, "overdue"); },
};

MENU_FIELDS.forEach(field => {
    form_events[field] = function(frm) {
        _update_select_all_checkbox(frm);
    };
});

frappe.ui.form.on("Student Portal Settings", form_events);

function _update_select_all_checkbox(frm) {
    if (frm.prevent_trigger) return;
    const all_selected = MENU_FIELDS.every(field => frm.doc[field]);
    frm.prevent_trigger = true;
    frm.set_value("select_all_menus", all_selected ? 1 : 0);
    frm.prevent_trigger = false;
}


// ── Action buttons ────────────────────────────────────────────────────
function _add_action_buttons(frm) {
    frm.add_custom_button(__("Preview Portal"), () => {
        window.open("/student-portal", "_blank");
    }, __("Actions"));

    frm.add_custom_button(__("Reset to Defaults"), () => {
        frappe.confirm(
            __("Reset all settings to factory defaults?"),
            () => {
                Object.entries(SP_DEFAULTS).forEach(([k, v]) => frm.set_value(k, v));
                frappe.show_alert({ message: __("Defaults restored — click Save to apply."), indicator: "blue" });
                setTimeout(() => _render_all_previews(frm), 300);
            }
        );
    }, __("Actions"));

    frm.add_custom_button(__("Send Fee Reminders"), () => {
        _open_reminder_dialog();
    }, __("Actions"));
}


// ── Fee Reminder Dialog ───────────────────────────────────────────────
function _open_reminder_dialog() {
    // Step 1: Fetch filter options, then build dialog
    frappe.call({
        method: "slcm.slcm.page.fee_reminder_tool.fee_reminder_tool.get_filter_options",
        callback(r) {
            const opts = r.message || {};
            _show_reminder_dialog(opts);
        },
    });
}

function _show_reminder_dialog(opts) {
    let all_demands = [];
    let selected_names = new Set();

    const program_options  = [""].concat(opts.programs || []);
    const year_options     = [""].concat(opts.academic_years || []);
    const dtype_options    = ["", "Academic", "Examination", "Service", "Fine", "Hostel", "Deposit", "Other"];

    const d = new frappe.ui.Dialog({
        title: __("Send Fee Reminders"),
        size:  "extra-large",
        fields: [
            // ── Filters row ───────────────────────────────────────────
            {
                fieldtype: "Select",
                fieldname: "reminder_type",
                label:     __("Reminder Type"),
                options:   "Overdue Notice\n7-Day Advance Reminder\n1-Day Final Reminder",
                default:   "Overdue Notice",
                reqd:      1,
            },
            { fieldtype: "Column Break", fieldname: "col_b1" },
            {
                fieldtype: "Link",
                fieldname: "program",
                label:     __("Programme"),
                options:   "Programme",
            },
            { fieldtype: "Column Break", fieldname: "col_b2" },
            {
                fieldtype: "Link",
                fieldname: "academic_year",
                label:     __("Academic Year"),
                options:   "Academic Year",
            },
            { fieldtype: "Column Break", fieldname: "col_b3" },
            {
                fieldtype: "Select",
                fieldname: "demand_type",
                label:     __("Demand Type"),
                options:   "\nAcademic\nNon Academic",
            },
            { fieldtype: "Section Break", fieldname: "sec_results" },
            // ── Results area ──────────────────────────────────────────
            {
                fieldtype: "HTML",
                fieldname: "results_html",
                options:   `<div id="frd-results" style="min-height:40px;"></div>`,
            },
        ],
        primary_action_label: __("Send to Selected"),
        primary_action(values) {
            if (!selected_names.size) {
                frappe.show_alert({ message: __("No students selected."), indicator: "orange" });
                return;
            }
            const label_map = {
                "Overdue Notice":          "Overdue Notice",
                "7-Day Advance Reminder":  "7-Day Advance Reminder",
                "1-Day Final Reminder":    "1-Day Final Reminder",
            };
            frappe.confirm(
                __(`Send <strong>${label_map[values.reminder_type]}</strong> to <strong>${selected_names.size}</strong> student(s)?`),
                () => {
                    const type_map = {
                        "Overdue Notice":         "overdue",
                        "7-Day Advance Reminder":  "7day",
                        "1-Day Final Reminder":    "1day",
                    };
                    const reminder_type = type_map[values.reminder_type];
                    const names = [...selected_names];

                    d.get_primary_btn().prop("disabled", true).text(__("Sending…"));

                    frappe.call({
                        method: "slcm.slcm.page.fee_reminder_tool.fee_reminder_tool.send_manual_reminders",
                        args: { demand_names: names, reminder_type },
                        callback(r) {
                            d.get_primary_btn().prop("disabled", false)
                                .text(__("Send to Selected"));
                            const { queued, message } = r.message || {};
                            frappe.msgprint({
                                title: __("Reminders Queued"),
                                message: message || `${queued} reminder(s) queued for delivery.`,
                                indicator: "green",
                            });
                            d.hide();
                        },
                    });
                }
            );
        },
    });

    // ── Preview / Search button ───────────────────────────────────────
    d.set_secondary_action_label(__("Search Demands"));
    d.set_secondary_action(() => {
        const vals = d.get_values();
        const type_map = {
            "Overdue Notice":         "overdue",
            "7-Day Advance Reminder":  "7day",
            "1-Day Final Reminder":    "1day",
        };
        const reminder_type = type_map[vals.reminder_type || "Overdue Notice"];
        const program       = vals.program || "";
        const academic_year = vals.academic_year || "";
        const demand_type   = vals.demand_type || "";

        const $res = d.$wrapper.find("#frd-results");
        $res.html(`<p style="color:#6b7280;font-size:13px;padding:8px 0;">
            <i class="fa fa-spinner fa-spin"></i> Searching…</p>`);

        frappe.call({
            method: "slcm.slcm.page.fee_reminder_tool.fee_reminder_tool.get_pending_demands",
            args: { program, academic_year, demand_type, reminder_type },
            callback(r) {
                all_demands = r.message || [];
                selected_names = new Set(
                    all_demands.filter(d => d.student_email).map(d => d.name)
                );
                _render_frd_table(d.$wrapper, all_demands, selected_names);
                // keep primary btn label in sync
                d.get_primary_btn().text(
                    selected_names.size
                        ? __(`Send to ${selected_names.size} Student(s)`)
                        : __("Send to Selected")
                );
            },
        });
    });

    d.show();
}

function _render_frd_table($wrapper, demands, selected_names) {
    const $res = $wrapper.find("#frd-results");

    if (!demands.length) {
        $res.html(`<p style="color:#6b7280;font-size:13px;padding:8px 0;text-align:center;">
            No pending demands found for the selected filters.</p>`);
        return;
    }

    const no_mail    = demands.filter(d => !d.student_email).length;
    const resend_ct  = demands.filter(d => d.already_sent).length;
    const total      = demands.length;

    const summary = `<div style="
        background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;
        padding:10px 14px;margin-bottom:10px;font-size:13px;color:#1e40af;
        display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
        <span>Found <strong>${total}</strong> demand${total !== 1 ? "s" : ""}.
        ${resend_ct ? `<span style="color:#92400e;margin-left:8px;">${resend_ct} already sent (marked Resend).</span>` : ""}
        ${no_mail ? `<span style="color:#dc2626;margin-left:6px;">${no_mail} have no email.</span>` : ""}</span>
        <div style="display:flex;gap:6px;">
            <button class="btn btn-xs frd-sel-all"
                style="background:#dbeafe;color:#1e40af;border:none;border-radius:4px;padding:3px 10px;cursor:pointer;">
                Select All</button>
            <button class="btn btn-xs frd-desel-all"
                style="background:#e5e7eb;color:#374151;border:none;border-radius:4px;padding:3px 10px;cursor:pointer;">
                Deselect All</button>
        </div>
    </div>`;

    const rows = demands.map(dem => {
        const noEmail     = !dem.student_email;
        const checked     = selected_names.has(dem.name) ? "checked" : "";
        const disabled    = noEmail ? "disabled title='No email address'" : "";
        const opacity     = noEmail ? "opacity:0.5;" : "";
        const status_colors = {
            "Overdue":        "background:#fee2e2;color:#dc2626",
            "Pending":        "background:#fef9c3;color:#854d0e",
            "Partially Paid": "background:#e0f2fe;color:#0369a1",
        };
        const badge_style   = status_colors[dem.status] || "background:#f3f4f6;color:#374151";
        const fmt_amount    = frappe.format(dem.outstanding_amount, { fieldtype: "Currency" });
        const sent_badge    = dem.already_sent
            ? `<span style="background:#fef9c3;color:#92400e;border-radius:4px;padding:2px 7px;font-size:10px;font-weight:600;margin-left:4px;">Resend</span>`
            : "";
        return `<tr style="${opacity}">
            <td style="padding:8px 10px;text-align:center;">
                <input type="checkbox" class="frd-row-chk" data-name="${dem.name}" ${checked} ${disabled}>
            </td>
            <td style="padding:8px 10px;">
                <div style="font-weight:600;font-size:13px;">${dem.student_name || dem.student}</div>
                <div style="font-size:11px;color:#6b7280;">${dem.student}</div>
            </td>
            <td style="padding:8px 10px;font-size:12px;color:#374151;">${dem.program || "—"}</td>
            <td style="padding:8px 10px;font-size:12px;color:#374151;">${dem.academic_year || "—"}</td>
            <td style="padding:8px 10px;font-size:12px;color:#374151;">${dem.fee_component || "—"}</td>
            <td style="padding:8px 10px;font-size:12px;text-align:right;font-weight:600;">${fmt_amount}</td>
            <td style="padding:8px 10px;font-size:12px;color:#374151;">${dem.due_date || "—"}</td>
            <td style="padding:8px 10px;">
                <span style="${badge_style};border-radius:4px;padding:2px 7px;font-size:11px;font-weight:600;">
                    ${dem.status}</span>${sent_badge}
            </td>
            <td style="padding:8px 10px;font-size:11px;color:#6b7280;">
                ${dem.student_email || '<span style="color:#dc2626;">No email</span>'}</td>
        </tr>`;
    }).join("");

    const table = `<div style="overflow-x:auto;max-height:340px;overflow-y:auto;border:1px solid #e5e7eb;border-radius:6px;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead style="background:#f9fafb;position:sticky;top:0;">
                <tr>
                    <th style="padding:8px 10px;text-align:center;width:36px;border-bottom:1px solid #e5e7eb;">
                        <input type="checkbox" id="frd-check-all"></th>
                    <th style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:left;">Student</th>
                    <th style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:left;">Program</th>
                    <th style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:left;">Acad. Year</th>
                    <th style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:left;">Fee Head</th>
                    <th style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right;">Outstanding</th>
                    <th style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:left;">Due Date</th>
                    <th style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:left;">Status</th>
                    <th style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:left;">Email</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;

    $res.html(summary + table);

    // Sync header checkbox initial state
    const total_checkable = demands.filter(d => d.student_email).length;
    const total_checked   = selected_names.size;
    $res.find("#frd-check-all")
        .prop("checked", total_checked > 0 && total_checked === total_checkable)
        .prop("indeterminate", total_checked > 0 && total_checked < total_checkable);

    // Row checkbox events
    $res.on("change", ".frd-row-chk", function () {
        const name = $(this).data("name");
        if (this.checked) selected_names.add(name);
        else              selected_names.delete(name);
        _sync_frd_header($res, demands, selected_names);
    });

    // Header checkbox
    $res.on("change", "#frd-check-all", function () {
        $res.find(".frd-row-chk:not(:disabled)")
            .prop("checked", this.checked)
            .trigger("change");
    });

    // Select / Deselect all buttons
    $res.find(".frd-sel-all").on("click", () => {
        $res.find(".frd-row-chk:not(:disabled)").prop("checked", true).trigger("change");
    });
    $res.find(".frd-desel-all").on("click", () => {
        $res.find(".frd-row-chk:not(:disabled)").prop("checked", false).trigger("change");
    });
}

function _sync_frd_header($res, demands, selected_names) {
    const total_checkable = demands.filter(d => d.student_email).length;
    const total_checked   = selected_names.size;
    $res.find("#frd-check-all")
        .prop("checked", total_checked > 0 && total_checked === total_checkable)
        .prop("indeterminate", total_checked > 0 && total_checked < total_checkable);
}


// ── Color Preset bar ─────────────────────────────────────────────────
function _render_preset_bar(frm) {
    const section = frm.get_field("theme_section");
    if (!section || !section.$wrapper) return;

    const wrapper = section.$wrapper;
    wrapper.find(".sp-preset-bar").remove();

    const buttons = SP_PRESETS.map((preset, idx) => `
        <button class="sp-preset-btn" data-idx="${idx}"
            title="${preset.name}"
            style="width:28px;height:28px;border-radius:50%;border:2px solid transparent;
                   cursor:pointer;background:${preset.primary_color};padding:0;
                   transition:transform 0.15s,border-color 0.15s;flex-shrink:0;"
            onmouseover="this.style.transform='scale(1.2)';this.style.borderColor='#fff';"
            onmouseout="this.style.transform='scale(1)';this.style.borderColor='transparent';">
        </button>`).join("");

    const html = `
        <div class="sp-preset-bar" style="padding:10px 0 6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <span style="font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;
                       letter-spacing:.06em;white-space:nowrap;">Quick Themes:</span>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            ${buttons}
          </div>
        </div>`;

    const $bar = $(html).prependTo(wrapper);

    $bar.find(".sp-preset-btn").on("click", function () {
        const preset = SP_PRESETS[$(this).data("idx")];
        Object.entries(preset).forEach(([k, v]) => {
            if (k !== "name") frm.set_value(k, v);
        });
        frappe.show_alert({ message: __(`Theme "${preset.name}" applied — click Save.`), indicator: "green" });
        setTimeout(() => _render_all_previews(frm), 200);
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
    const primary   = d.primary_color   || "#1a3c6e";
    const secondary = d.secondary_color || "#c8a14b";
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
      <div class="sp-preview-row">
        <div class="sp-preview-group">
          <div class="sp-preview-label">Theme Palette</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;">
            ${_swatch(primary,   "Primary", false, navText)}
            ${_swatch(secondary, "Accent")}
            ${_swatch(bg,        "Background", true)}
            ${_swatch(card,      "Card", true)}
          </div>
        </div>
        <div class="sp-preview-group">
          <div class="sp-preview-label">Status Colors</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;">
            ${_swatch(success, "Success")}
            ${_swatch(warning, "Warning")}
            ${_swatch(danger,  "Danger")}
            ${_swatch(info,    "Info")}
          </div>
        </div>
      </div>
      <div class="sp-preview-group" style="margin-top:12px;">
        <div class="sp-preview-label">Grade Bands</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
                    
          
          <span style="font-size:10px;color:#9ca3af;margin-left:4px;">← shown on Results page</span>
        </div>
      </div>
      <div class="sp-preview-group" style="margin-top:12px;">
        <div class="sp-preview-label">Mini Portal Card</div>
        ${_mini_portal_card(primary, secondary, bg, card, navText, d.sidebar_theme)}
      </div>
    </div>`;

    _inject_into_section(frm, "theme_section", ".sp-color-preview", html);

    // Inject preview styles once
    if (!document.getElementById("sp-preview-styles")) {
        $("<style id='sp-preview-styles'>").text(`
            .sp-preview-row { display:flex; gap:24px; flex-wrap:wrap; }
            .sp-preview-group { }
            .sp-preview-label {
                font-size:10px; font-weight:700; text-transform:uppercase;
                letter-spacing:.06em; color:#9ca3af; margin-bottom:6px;
            }
        `).appendTo("head");
    }
}


// ── Layout preview ─────────────────────────────────────────────────────
function _render_layout_preview(frm) {
    const d = frm.doc;
    const pos     = d.sidebar_position || "Left";
    const width   = d.sidebar_width    || "Normal";
    const size    = d.font_size        || "Normal";
    const corners = d.corner_style     || "Normal";
    const density = d.layout_density   || "Normal";
    const primary = d.primary_color    || "#1a3c6e";
    const dark    = d.sidebar_theme    === "Dark";
    const navH    = d.nav_height       || "Normal";
    const font    = d.font_family      || "Poppins";

    const sbW    = width   === "Narrow" ? 54  : width   === "Wide" ? 76  : 66;
    const navPx  = navH    === "Compact" ? 14 : navH    === "Tall"  ? 20 : 16;
    const radius = corners === "Sharp"   ? "3px" : corners === "Pill" ? "12px" : "7px";
    const isRight= pos === "Right";
    const navPad = density === "Compact" ? "3px 6px" : "5px 8px";
    const fsPx   = size    === "Small"   ? "9px" : size === "Large" ? "11px" : "10px";
    const sbBg   = dark ? primary : "#ffffff";
    const sbText = dark ? "rgba(255,255,255,0.75)" : "#6b7280";
    const sbActiveBg = dark ? "rgba(255,255,255,0.16)" : "rgba(26,60,110,0.1)";
    const sbActiveText = dark ? "#fff" : primary;
    const fontLabel = { "Poppins": "Poppins", "Inter": "Inter", "Roboto": "Roboto", "System Default": "System" }[font] || font;

    const navItems = [
        ["dashboard", "Dashboard", true],
        ["menu_book", "Courses", false],
        ["event_available", "Attendance", false],
        ["payments", "Fees", false],
    ].map(([icon, label, active]) => `
        <div style="padding:${navPad};background:${active ? sbActiveBg : "transparent"};
             border-radius:${radius};font-size:${fsPx};color:${active ? sbActiveText : sbText};
             margin-bottom:2px;display:flex;align-items:center;gap:4px;
             border-left:2px solid ${active ? (dark ? "#c8a14b" : primary) : "transparent"};">
          <span style="font-family:'Material Symbols Outlined';font-size:12px;opacity:0.6;">${icon}</span>
          ${label}
        </div>`).join("");

    const sidebarEl = `
        <div style="width:${sbW}px;background:${sbBg};padding:5px 3px;border-radius:${radius};
             flex-shrink:0;border:1px solid ${dark ? "rgba(255,255,255,0.1)" : "#e5e7eb"};">
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
        `Sidebar: ${pos}`, `Width: ${width}`, `Nav: ${navH}`,
        `Corners: ${corners}`, `Density: ${density}`,
        `Font: ${fontLabel}`, `Size: ${size}`,
    ].map(t => `<span style="background:#f3f4f6;border:1px solid #e5e7eb;border-radius:4px;
                padding:2px 6px;font-size:9px;color:#6b7280;">${t}</span>`).join("");

    const html = `
    <div style="padding:14px 0 4px;">
      <div class="sp-preview-label">Layout Preview</div>
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
          <div style="width:18px;height:18px;background:rgba(255,255,255,0.2);border-radius:50%;"></div>
        </div>
        <div style="padding:5px;display:flex;gap:4px;flex-direction:${isRight ? "row-reverse" : "row"};">
          ${sidebarEl}${contentEl}
        </div>
      </div>
    </div>`;

    _inject_into_section(frm, "layout_section", ".sp-layout-preview", html);
}


// ── Mini portal card (shown inside color preview) ─────────────────────
function _mini_portal_card(primary, secondary, bg, card, navText, sidebarTheme) {
    const dark = sidebarTheme === "Dark";
    const sbBg = dark ? primary : card;
    const sbText = dark ? "rgba(255,255,255,0.75)" : "#6b7280";

    return `
    <div style="width:280px;border-radius:10px;overflow:hidden;border:1px solid #e5e7eb;font-family:'Poppins',sans-serif;">
      <div style="background:${primary};height:32px;display:flex;align-items:center;
           padding:0 10px;gap:8px;">
        <div style="width:18px;height:18px;background:rgba(255,255,255,0.2);border-radius:4px;"></div>
        <div style="width:60px;height:6px;background:${navText}33;border-radius:3px;"></div>
        <div style="flex:1;"></div>
        <div style="width:16px;height:16px;background:rgba(255,255,255,0.2);border-radius:50%;"></div>
      </div>
      <div style="display:flex;background:${bg};">
        <div style="width:64px;background:${sbBg};padding:6px 4px;border-right:1px solid rgba(0,0,0,0.06);">
          <div style="height:16px;background:linear-gradient(135deg,${primary},${primary}cc);border-radius:5px;margin-bottom:5px;"></div>
          ${["Dashboard","Courses","Fees"].map((l, i) => `
          <div style="padding:3px 5px;margin-bottom:2px;border-radius:4px;font-size:8px;
               color:${i===0 ? (dark ? "#fff" : primary) : sbText};
               background:${i===0 ? (dark ? "rgba(255,255,255,0.16)" : "rgba(26,60,110,0.1)") : "transparent"};
               border-left:2px solid ${i===0 ? (dark ? secondary : primary) : "transparent"};">
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
    return `
    <div style="padding:4px 10px;background:${color}22;border:1px solid ${color}55;
         border-radius:20px;font-size:10px;font-weight:600;color:${color};white-space:nowrap;">
      ${label}
    </div>`;
}

function _inject_into_section(frm, fieldname, selector, html) {
    const field = frm.get_field(fieldname);
    if (!field || !field.$wrapper) return;
    const wrapper = field.$wrapper;
    let el = wrapper.find(selector);
    if (!el.length) {
        el = $(`<div class="${selector.replace(".", "")}"></div>`).appendTo(wrapper);
    }
    el.html(html);
}


// ── Reminder field visibility ─────────────────────────────────────────
function _toggle_reminder_fields(frm) {
    const master_on = !!frm.doc.enable_fee_reminders;

    const reminder_fields = [
        "reminder_sender_name", "reminder_from_email",
        "enable_7day_reminder", "reminder_7day_template",
        "enable_1day_reminder", "reminder_1day_template",
        "enable_overdue_notice", "overdue_notice_offset", "overdue_notice_template",
    ];
    reminder_fields.forEach(f => frm.toggle_enable(f, master_on));

    if (master_on) {
        _toggle_reminder_sub_fields(frm, "7day");
        _toggle_reminder_sub_fields(frm, "1day");
        _toggle_reminder_sub_fields(frm, "overdue");
    }
}

function _toggle_reminder_sub_fields(frm, type) {
    const master_on = !!frm.doc.enable_fee_reminders;
    if (!master_on) return;

    const map = {
        "7day":   { flag: "enable_7day_reminder",  fields: ["reminder_7day_template"] },
        "1day":   { flag: "enable_1day_reminder",  fields: ["reminder_1day_template"] },
        "overdue":{ flag: "enable_overdue_notice", fields: ["overdue_notice_offset", "overdue_notice_template"] },
    };

    const cfg = map[type];
    if (!cfg) return;
    const enabled = !!frm.doc[cfg.flag];
    cfg.fields.forEach(f => frm.toggle_enable(f, enabled));
}

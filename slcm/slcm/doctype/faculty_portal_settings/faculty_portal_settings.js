// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

// ── Theme presets ──────────────────────────────────────────────────────
const FP_PRESETS = [
    {
        name: "Academic Navy (Default)",
        primary_color: "#1e3a5f", secondary_color: "#e8a020",
        background_color: "#f0f2f5", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Light",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#0369a1",
    },
    {
        name: "Maroon Classic",
        primary_color: "#6b1f1f", secondary_color: "#d4a017",
        background_color: "#fdf6f0", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Dark",
        success_color: "#15803d", warning_color: "#b45309",
        danger_color: "#dc2626", info_color: "#0369a1",
    },
    {
        name: "Forest Scholar",
        primary_color: "#14532d", secondary_color: "#f59e0b",
        background_color: "#f0f4f1", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Dark",
        success_color: "#15803d", warning_color: "#b45309",
        danger_color: "#dc2626", info_color: "#0369a1",
    },
    {
        name: "Midnight Slate",
        primary_color: "#1e293b", secondary_color: "#38bdf8",
        background_color: "#f1f5f9", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Dark",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#0284c7",
    },
    {
        name: "Royal Indigo",
        primary_color: "#3730a3", secondary_color: "#f59e0b",
        background_color: "#f5f3ff", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Dark",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#6366f1",
    },
    {
        name: "Teal & Steel",
        primary_color: "#0f4c5c", secondary_color: "#06b6d4",
        background_color: "#f0f9ff", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Dark",
        success_color: "#0d9488", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#0284c7",
    },
    {
        name: "Charcoal & Sage",
        primary_color: "#2d3748", secondary_color: "#48bb78",
        background_color: "#f7fafc", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Dark",
        success_color: "#38a169", warning_color: "#d97706",
        danger_color: "#e53e3e", info_color: "#4299e1",
    },
    {
        name: "Warm Amber",
        primary_color: "#78350f", secondary_color: "#f59e0b",
        background_color: "#fffbeb", card_background: "#ffffff",
        nav_text_color: "#ffffff", sidebar_theme: "Light",
        success_color: "#16a34a", warning_color: "#d97706",
        danger_color: "#dc2626", info_color: "#0369a1",
    },
];

const FP_DEFAULTS = {
    portal_title: "Faculty Portal", portal_subtitle: "",
    show_logo: 1, nav_brand_text: "", portal_favicon: "",
    font_family: "Poppins", font_size: "Normal",
    primary_color: "#1e3a5f", secondary_color: "#e8a020",
    background_color: "#f0f2f5", card_background: "#ffffff",
    sidebar_theme: "Light", nav_text_color: "#ffffff",
    success_color: "#920c24", warning_color: "#920c24",
    danger_color: "#dc2626", info_color: "#0369a1",
    grade_excellent_color: "#16a34a", grade_excellent_label: "A+ / A / S",
    grade_good_color: "#0369a1",      grade_good_label: "B+ / B",
    grade_average_color: "#d97706",   grade_average_label: "C+ / C",
    grade_color: "#000000", grade_fail_color: "#dc2626",      grade_fail_label: "D / F",
    att_good_threshold: 75, att_warn_threshold: 60,
    att_label_good: "Good", att_label_warn: "Low", att_label_danger: "Critical",
    sidebar_position: "Left", sidebar_width: "Normal", nav_height: "Normal",
    corner_style: "Normal", layout_density: "Normal",
    show_faculty_id_sidebar: 1, show_department_sidebar: 1,
    show_announcements_ticker: 1, show_today_schedule: 1, show_pending_evaluations: 1,
    show_class_statistics: 1, show_quick_actions: 1, show_workload_summary: 1,
    show_leave_status: 1, show_student_performance_overview: 1, show_upcoming_exams: 1,
    enable_attendance_marking: 1, enable_bulk_attendance: 1,
    show_student_photos_attendance: 1, auto_close_session_minutes: 120,
    enable_proxy_attendance_alert: 1, allow_attendance_edit_window_days: 2,
    enable_marks_entry: 1, enable_internal_marks: 1, show_class_grade_statistics: 1,
    allow_marks_edit_after_submission: 0, marks_edit_approval_required: 1, enable_grade_remarks: 1,
    enable_assignment_module: 1, allow_late_submission_marking: 1,
    assignment_submission_notification: 1, show_plagiarism_indicator: 0,
    enable_office_hours: 1, show_student_contact_info: 1, enable_student_query_system: 1,
    office_hours_advance_booking_days: 7, max_office_hour_bookings: 10,
    enable_leave_request: 1, show_workload_indicator: 1,
    workload_calculation_method: "Credit Hours", max_weekly_teaching_hours: 20,
    allow_theme_override: 1, allow_density_override: 1, allow_notification_settings: 1,
    allow_dashboard_customization: 1, allow_font_size_override: 1, allow_language_preference: 0,
    custom_css: "",
};


// ── Form event handlers ────────────────────────────────────────────────
frappe.ui.form.on("Faculty Portal Settings", {
    refresh(frm) {
        _add_action_buttons(frm);
        _render_preset_bar(frm);
        _render_all_previews(frm);
        _inject_global_styles();
    },

    // Theme color triggers
    primary_color:    (frm) => _render_all_previews(frm),
    secondary_color:  (frm) => _render_all_previews(frm),
    background_color: (frm) => { _render_color_preview(frm); _render_layout_preview(frm); },
    card_background:  (frm) => { _render_color_preview(frm); _render_layout_preview(frm); },
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
    font_family:      (frm) => _render_layout_preview(frm),
    font_size:        (frm) => _render_layout_preview(frm),

    // Module / feature triggers → update feature matrix
    enable_attendance_marking:      (frm) => _render_feature_matrix(frm),
    enable_marks_entry:             (frm) => _render_feature_matrix(frm),
    enable_assignment_module:       (frm) => _render_feature_matrix(frm),
    enable_office_hours:            (frm) => _render_feature_matrix(frm),
    enable_student_query_system:    (frm) => _render_feature_matrix(frm),
    enable_leave_request:           (frm) => _render_feature_matrix(frm),
    show_workload_indicator:        (frm) => _render_feature_matrix(frm),
    show_class_grade_statistics:    (frm) => _render_feature_matrix(frm),
    show_plagiarism_indicator:      (frm) => _render_feature_matrix(frm),
    enable_bulk_attendance:         (frm) => _render_feature_matrix(frm),
    enable_internal_marks:          (frm) => _render_feature_matrix(frm),
    allow_marks_edit_after_submission: (frm) => _render_feature_matrix(frm),

    // Self-service triggers
    allow_theme_override:         (frm) => _render_self_service_preview(frm),
    allow_density_override:       (frm) => _render_self_service_preview(frm),
    allow_notification_settings:  (frm) => _render_self_service_preview(frm),
    allow_dashboard_customization:(frm) => _render_self_service_preview(frm),
    allow_font_size_override:     (frm) => _render_self_service_preview(frm),
    allow_language_preference:    (frm) => _render_self_service_preview(frm),
});


// ── Action buttons ─────────────────────────────────────────────────────
function _add_action_buttons(frm) {
    frm.add_custom_button(__("Preview Portal"), () => {
        window.open("/faculty-portal", "_blank");
    }, __("Actions"));

    frm.add_custom_button(__("Open User Preferences"), () => {
        frappe.set_route("List", "Faculty Portal User Preferences");
    }, __("Actions"));

    frm.add_custom_button(__("Reset to Defaults"), () => {
        frappe.confirm(
            __("Reset all settings to factory defaults?"),
            () => {
                Object.entries(FP_DEFAULTS).forEach(([k, v]) => frm.set_value(k, v));
                frappe.show_alert({ message: __("Defaults restored — click Save to apply."), indicator: "blue" });
                setTimeout(() => _render_all_previews(frm), 300);
            }
        );
    }, __("Actions"));
}


// ── Preset bar ─────────────────────────────────────────────────────────
function _render_preset_bar(frm) {
    const section = frm.get_field("theme_section");
    if (!section || !section.$wrapper) return;

    const wrapper = section.$wrapper;
    wrapper.find(".fp-preset-bar").remove();

    const buttons = FP_PRESETS.map((preset, idx) => `
        <button class="fp-preset-btn" data-idx="${idx}" title="${preset.name}"
            style="position:relative;width:34px;height:34px;border-radius:8px;border:2px solid transparent;
                   cursor:pointer;background:linear-gradient(135deg,${preset.primary_color},${preset.secondary_color});
                   padding:0;transition:transform 0.15s,border-color 0.15s,box-shadow 0.15s;flex-shrink:0;"
            onmouseover="this.style.transform='scale(1.15)';this.style.borderColor='#fff';
                         this.style.boxShadow='0 4px 12px rgba(0,0,0,0.25)';"
            onmouseout="this.style.transform='scale(1)';this.style.borderColor='transparent';
                        this.style.boxShadow='none';">
        </button>`).join("");

    const html = `
        <div class="fp-preset-bar" style="padding:10px 0 8px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <span style="font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;
                       letter-spacing:.07em;white-space:nowrap;">Quick Themes</span>
          <div style="width:1px;height:20px;background:#e5e7eb;"></div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">${buttons}</div>
        </div>`;

    const $bar = $(html).prependTo(wrapper);

    $bar.find(".fp-preset-btn").on("click", function () {
        const preset = FP_PRESETS[$(this).data("idx")];
        Object.entries(preset).forEach(([k, v]) => {
            if (k !== "name") frm.set_value(k, v);
        });
        frappe.show_alert({ message: __(`Theme "${preset.name}" applied — click Save.`), indicator: "green" });
        setTimeout(() => _render_all_previews(frm), 200);
    });
}


// ── Master render ──────────────────────────────────────────────────────
function _render_all_previews(frm) {
    _render_color_preview(frm);
    _render_layout_preview(frm);
    _render_feature_matrix(frm);
    _render_self_service_preview(frm);
}


// ── Color / Theme preview ──────────────────────────────────────────────
function _render_color_preview(frm) {
    const d = frm.doc;
    const primary   = d.primary_color   || "#1e3a5f";
    const secondary = d.secondary_color || "#e8a020";
    const bg        = d.background_color || "#f0f2f5";
    const card      = d.card_background  || "#ffffff";
    const navText   = d.nav_text_color   || "#ffffff";
    const success   = d.success_color   || "#16a34a";
    const warning   = d.warning_color   || "#d97706";
    const danger    = d.danger_color    || "#dc2626";
    const info      = d.info_color      || "#0369a1";

    const gExc  = d.grade_excellent_color || "#16a34a";
    const gGood = d.grade_good_color      || "#0369a1";
    const gAvg  = d.grade_average_color   || "#d97706";
    const gFail = d.grade_fail_color      || "#dc2626";
    const gExcLabel  = d.grade_excellent_label || "A+ / A";
    const gGoodLabel = d.grade_good_label      || "B+ / B";
    const gAvgLabel  = d.grade_average_label   || "C+ / C";
    const gFailLabel = d.grade_fail_label      || "D / F";

    const html = `
    <div class="fp-preview-wrap">
      <div class="fp-preview-row">
        <div class="fp-preview-group">
          <div class="fp-preview-label">Theme Palette</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;">
            ${_swatch(primary,   "Primary",    false, navText)}
            ${_swatch(secondary, "Accent")}
            ${_swatch(bg,        "Background", true)}
            ${_swatch(card,      "Card",       true)}
          </div>
        </div>
        <div class="fp-preview-group">
          <div class="fp-preview-label">Status Colors</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;">
            ${_swatch(success, "Success")}
            ${_swatch(warning, "Warning")}
            ${_swatch(danger,  "Danger")}
            ${_swatch(info,    "Info")}
          </div>
        </div>
        <div class="fp-preview-group">
          <div class="fp-preview-label">Faculty Portal Card</div>
          ${_mini_faculty_card(primary, secondary, bg, card, navText, d.sidebar_theme)}
        </div>
      </div>
      <div class="fp-preview-group" style="margin-top:14px;">
        <div class="fp-preview-label">Grade Bands</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
                    
          
          <span style="font-size:10px;color:#9ca3af;margin-left:6px;">← shown on Marks Entry & Class Statistics pages</span>
        </div>
      </div>
    </div>`;

    _inject_into_section(frm, "theme_section", ".fp-color-preview", html);
}


// ── Layout preview ─────────────────────────────────────────────────────
function _render_layout_preview(frm) {
    const d = frm.doc;
    const pos     = d.sidebar_position || "Left";
    const width   = d.sidebar_width    || "Normal";
    const size    = d.font_size        || "Normal";
    const corners = d.corner_style     || "Normal";
    const density = d.layout_density   || "Normal";
    const primary = d.primary_color    || "#1e3a5f";
    const secondary= d.secondary_color || "#e8a020";
    const bg      = d.background_color || "#f0f2f5";
    const card    = d.card_background  || "#ffffff";
    const dark    = d.sidebar_theme    === "Dark";
    const navH    = d.nav_height       || "Normal";
    const font    = d.font_family      || "Poppins";

    const sbW    = width   === "Narrow" ? 54  : width   === "Wide" ? 76  : 66;
    const navPx  = navH    === "Compact" ? 14 : navH    === "Tall"  ? 20 : 16;
    const radius = corners === "Sharp"   ? "3px" : corners === "Pill" ? "12px" : "7px";
    const isRight= pos === "Right";
    const navPad = density === "Compact" ? "3px 5px" : "5px 8px";
    const fsPx   = size    === "Small"   ? "9px" : size === "Large" ? "11px" : "10px";
    const sbBg   = dark ? primary : card;
    const sbText = dark ? "rgba(255,255,255,0.70)" : "#6b7280";
    const sbActiveBg   = dark ? "rgba(255,255,255,0.16)" : "rgba(30,58,95,0.1)";
    const sbActiveText = dark ? "#fff" : primary;
    const fontLabel = { "Poppins": "Poppins", "Inter": "Inter", "Roboto": "Roboto", "System Default": "System" }[font] || font;

    const navItems = [
        ["home",         "Dashboard",  true],
        ["menu_book",    "My Courses", false],
        ["fact_check",   "Attendance", false],
        ["grade",        "Marks Entry",false],
        ["assignment",   "Assignments",false],
        ["groups",       "Students",   false],
        ["calendar_today","Schedule",  false],
        ["time_off",     "Leave",      false],
    ].map(([icon, label, active]) => `
        <div style="padding:${navPad};background:${active ? sbActiveBg : "transparent"};
             border-radius:${radius};font-size:${fsPx};color:${active ? sbActiveText : sbText};
             margin-bottom:1.5px;display:flex;align-items:center;gap:3px;
             border-left:2px solid ${active ? (dark ? secondary : primary) : "transparent"};">
          <span style="font-family:'Material Symbols Outlined';font-size:11px;opacity:0.65;">${icon}</span>
          ${width === "Narrow" ? "" : label}
        </div>`).join("");

    const sidebarEl = `
        <div style="width:${sbW}px;background:${sbBg};padding:5px 3px;border-radius:${radius};
             flex-shrink:0;border:1px solid ${dark ? "rgba(255,255,255,0.08)" : "#e5e7eb"};">
          <div style="height:18px;background:linear-gradient(135deg,${primary},${primary}cc);
               border-radius:${radius};margin-bottom:4px;display:flex;align-items:center;
               padding:0 4px;gap:3px;">
            <div style="width:10px;height:10px;background:rgba(255,255,255,0.3);border-radius:50%;flex-shrink:0;"></div>
            ${width !== "Narrow" ? `<div style="width:30px;height:5px;background:rgba(255,255,255,0.4);border-radius:3px;"></div>` : ""}
          </div>
          ${navItems}
        </div>`;

    const success = d.success_color || "#16a34a";
    const warning = d.warning_color || "#d97706";
    const danger  = d.danger_color  || "#dc2626";

    const contentEl = `
        <div style="flex:1;padding:5px;display:flex;flex-direction:column;gap:3px;background:${bg};">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:2px;">
            <div style="height:7px;background:#d1d5db;border-radius:3px;width:40%;"></div>
            <div style="height:14px;background:${primary};border-radius:${radius};width:18%;opacity:0.8;"></div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:3px;">
            ${["Today","Pending","Leave"].map((l, i) => `
            <div style="height:22px;background:${card};border-radius:${radius};border:1px solid #e5e7eb;
                 display:flex;flex-direction:column;padding:3px 4px;justify-content:space-between;">
              <div style="height:3px;background:${[success,warning,"#6b7280"][i]};border-radius:2px;width:40%;"></div>
              <div style="height:4px;background:#e5e7eb;border-radius:2px;"></div>
            </div>`).join("")}
          </div>
          <div style="height:30px;background:${card};border-radius:${radius};border:1px solid #e5e7eb;
               display:flex;gap:3px;padding:4px 5px;">
            ${[0,1,2,3].map(i => `<div style="flex:1;height:100%;background:${bg};border-radius:${Math.max(2, parseInt(radius)-2)}px;"></div>`).join("")}
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:3px;">
            <div style="height:32px;background:${card};border-radius:${radius};border:1px solid #e5e7eb;"></div>
            <div style="height:32px;background:${card};border-radius:${radius};border:1px solid #e5e7eb;"></div>
          </div>
        </div>`;

    const tags = [
        `Sidebar: ${pos}`, `Width: ${width}`, `Nav: ${navH}`,
        `Corners: ${corners}`, `Density: ${density}`,
        `Font: ${fontLabel}`, `Size: ${size}`,
    ].map(t => `<span style="background:#f3f4f6;border:1px solid #e5e7eb;border-radius:4px;
                padding:2px 7px;font-size:9px;color:#6b7280;">${t}</span>`).join("");

    const html = `
    <div class="fp-preview-wrap" style="padding:14px 0 4px;">
      <div class="fp-preview-label">Layout Preview</div>
      <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:8px;">${tags}</div>
      <div style="border-radius:10px;overflow:hidden;border:1px solid #e5e7eb;box-shadow:0 2px 8px rgba(0,0,0,0.07);">
        <div style="height:${navPx + 14}px;background:${primary};display:flex;align-items:center;
             padding:0 10px;gap:7px;">
          <div style="display:flex;gap:2px;flex-direction:column;">
            <div style="width:14px;height:1.5px;background:rgba(255,255,255,0.8);border-radius:1px;"></div>
            <div style="width:10px;height:1.5px;background:rgba(255,255,255,0.8);border-radius:1px;"></div>
            <div style="width:14px;height:1.5px;background:rgba(255,255,255,0.8);border-radius:1px;"></div>
          </div>
          <div style="width:24px;height:24px;background:rgba(255,255,255,0.15);border-radius:5px;"></div>
          <div style="flex:1;"></div>
          <div style="height:18px;background:rgba(255,255,255,0.15);border-radius:${radius};
               padding:0 6px;font-size:8px;color:rgba(255,255,255,0.8);display:flex;align-items:center;gap:3px;">
            <span style="font-family:'Material Symbols Outlined';font-size:10px;">notifications</span>
          </div>
          <div style="width:22px;height:22px;background:${secondary};border-radius:50%;
               display:flex;align-items:center;justify-content:center;">
            <span style="font-family:'Material Symbols Outlined';font-size:10px;color:#fff;">person</span>
          </div>
        </div>
        <div style="display:flex;flex-direction:${isRight ? "row-reverse" : "row"};">
          ${sidebarEl}${contentEl}
        </div>
      </div>
    </div>`;

    _inject_into_section(frm, "layout_section", ".fp-layout-preview", html);
}


// ── Feature module matrix ──────────────────────────────────────────────
function _render_feature_matrix(frm) {
    const d = frm.doc;

    const modules = [
        { icon: "fact_check",    label: "Attendance Marking",    key: "enable_attendance_marking",    sub: d.enable_bulk_attendance ? "Bulk upload enabled" : "Single-entry only" },
        { icon: "grade",         label: "Marks Entry",           key: "enable_marks_entry",            sub: d.enable_internal_marks ? "Internal marks on" : "Final marks only" },
        { icon: "assignment",    label: "Assignments",           key: "enable_assignment_module",      sub: d.allow_late_submission_marking ? "Late subs allowed" : "On-time only" },
        { icon: "event_available",label:"Office Hours Booking",  key: "enable_office_hours",           sub: `${d.office_hours_advance_booking_days || 7}d advance booking` },
        { icon: "forum",         label: "Student Query System",  key: "enable_student_query_system",   sub: "Q&A between students & faculty" },
        { icon: "time_off",      label: "Leave Requests",        key: "enable_leave_request",          sub: "Faculty leave management" },
        { icon: "monitoring",    label: "Workload Indicator",    key: "show_workload_indicator",       sub: `${d.workload_calculation_method || "Credit Hours"} method` },
        { icon: "bar_chart",     label: "Grade Statistics",      key: "show_class_grade_statistics",   sub: "Class performance overview" },
        { icon: "content_copy",  label: "Plagiarism Indicator",  key: "show_plagiarism_indicator",     sub: "Similarity score on subs" },
        { icon: "edit_note",     label: "Marks Edit After Submit",key:"allow_marks_edit_after_submission", sub: d.marks_edit_approval_required ? "HOD approval required" : "Direct edit allowed" },
        { icon: "photo_camera",  label: "Student Photos in Att.",key: "show_student_photos_attendance",sub: "Anti-proxy photo display" },
        { icon: "create",        label: "Grade Remarks",         key: "enable_grade_remarks",          sub: "Per-student text remarks" },
    ];

    const cards = modules.map(m => {
        const enabled = d[m.key] || d[m.key] === 1;
        const dot  = enabled ? "#16a34a" : "#dc2626";
        const bg   = enabled ? "#f0fdf4" : "#fef2f2";
        const border = enabled ? "#bbf7d0" : "#fecaca";
        const textColor = enabled ? "#15803d" : "#b91c1c";
        return `
        <div style="background:${bg};border:1px solid ${border};border-radius:8px;padding:8px 10px;
             display:flex;align-items:flex-start;gap:7px;transition:all 0.2s;">
          <span style="font-family:'Material Symbols Outlined';font-size:18px;color:${textColor};
                flex-shrink:0;opacity:0.8;margin-top:1px;">${m.icon}</span>
          <div style="flex:1;min-width:0;">
            <div style="font-size:11px;font-weight:600;color:${textColor};white-space:nowrap;
                 overflow:hidden;text-overflow:ellipsis;">${m.label}</div>
            <div style="font-size:9.5px;color:${textColor};opacity:0.75;margin-top:1px;
                 white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${m.sub}</div>
          </div>
          <div style="width:7px;height:7px;border-radius:50%;background:${dot};flex-shrink:0;margin-top:3px;"></div>
        </div>`;
    }).join("");

    const enabledCount = modules.filter(m => d[m.key] || d[m.key] === 1).length;
    const pct = Math.round(enabledCount / modules.length * 100);

    const html = `
    <div class="fp-preview-wrap" style="padding:14px 0 4px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
        <div class="fp-preview-label" style="margin-bottom:0;">Feature Modules</div>
        <div style="display:flex;align-items:center;gap:8px;">
          <div style="width:100px;height:5px;background:#e5e7eb;border-radius:3px;overflow:hidden;">
            <div style="width:${pct}%;height:100%;background:#16a34a;border-radius:3px;transition:width 0.3s;"></div>
          </div>
          <span style="font-size:10px;font-weight:600;color:#6b7280;">${enabledCount} / ${modules.length} active</span>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px;">
        ${cards}
      </div>
    </div>`;

    _inject_into_section(frm, "dashboard_section", ".fp-feature-matrix", html);
}


// ── Self-Service capabilities preview ─────────────────────────────────
function _render_self_service_preview(frm) {
    const d = frm.doc;
    const primary = d.primary_color || "#1e3a5f";

    const capabilities = [
        { icon: "palette",         label: "Theme Override",       key: "allow_theme_override",         desc: "Choose accent color or full preset" },
        { icon: "density_medium",  label: "Layout Density",       key: "allow_density_override",       desc: "Compact vs Normal spacing" },
        { icon: "notifications",   label: "Notification Prefs",   key: "allow_notification_settings",  desc: "Email frequency & event filters" },
        { icon: "dashboard_customize",label:"Dashboard Layout",   key: "allow_dashboard_customization",desc: "Show / hide dashboard panels" },
        { icon: "text_fields",     label: "Font Size",            key: "allow_font_size_override",     desc: "Small / Normal / Large text" },
        { icon: "language",        label: "Language",             key: "allow_language_preference",    desc: "Portal interface language" },
    ];

    const enabledCount = capabilities.filter(c => d[c.key] || d[c.key] === 1).length;

    const cards = capabilities.map(c => {
        const on = d[c.key] || d[c.key] === 1;
        return `
        <div style="display:flex;align-items:center;gap:9px;padding:8px 12px;border-radius:8px;
             border:1px solid ${on ? primary + "33" : "#e5e7eb"};
             background:${on ? primary + "0a" : "#fafafa"};">
          <span style="font-family:'Material Symbols Outlined';font-size:20px;
                color:${on ? primary : "#9ca3af"};flex-shrink:0;">${c.icon}</span>
          <div style="flex:1;">
            <div style="font-size:11px;font-weight:600;color:${on ? "#111827" : "#9ca3af"};">${c.label}</div>
            <div style="font-size:9.5px;color:${on ? "#6b7280" : "#d1d5db"};margin-top:1px;">${c.desc}</div>
          </div>
          <div style="width:28px;height:16px;border-radius:8px;background:${on ? primary : "#d1d5db"};
               position:relative;cursor:default;transition:background 0.2s;">
            <div style="position:absolute;top:2px;${on ? "right" : "left"}:2px;width:12px;height:12px;
                 background:#fff;border-radius:50%;transition:all 0.2s;box-shadow:0 1px 3px rgba(0,0,0,0.2);">
            </div>
          </div>
        </div>`;
    }).join("");

    const summaryColor = enabledCount === 6 ? "#16a34a" : enabledCount >= 3 ? "#d97706" : "#6b7280";

    const html = `
    <div class="fp-preview-wrap" style="padding:14px 0 4px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
        <div>
          <div class="fp-preview-label" style="margin-bottom:2px;">Faculty Self-Service Preview</div>
          <div style="font-size:10px;color:#9ca3af;">Capabilities visible in the Faculty Portal User Preferences page</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:18px;font-weight:700;color:${summaryColor};">${enabledCount}<span style="font-size:11px;font-weight:400;color:#9ca3af;"> / 6</span></div>
          <div style="font-size:9px;color:#9ca3af;">settings unlocked</div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:6px;">
        ${cards}
      </div>
      ${enabledCount === 0 ? `
        <div style="margin-top:10px;padding:10px 14px;background:#fef9c3;border:1px solid #fde68a;
             border-radius:8px;font-size:11px;color:#92400e;display:flex;align-items:center;gap:8px;">
          <span style="font-family:'Material Symbols Outlined';font-size:18px;">warning</span>
          All self-service settings are disabled. Faculty cannot personalize any portal settings.
        </div>` : ""}
    </div>`;

    _inject_into_section(frm, "self_service_section", ".fp-selfservice-preview", html);
}


// ── Mini faculty portal card ───────────────────────────────────────────
function _mini_faculty_card(primary, secondary, bg, card, navText, sidebarTheme) {
    const dark  = sidebarTheme === "Dark";
    const sbBg  = dark ? primary : card;
    const sbTxt = dark ? "rgba(255,255,255,0.72)" : "#6b7280";

    const navLinks = ["Dashboard","My Courses","Attendance","Marks Entry","Assignments","Students","Schedule","Leave"];

    return `
    <div style="width:290px;border-radius:10px;overflow:hidden;border:1px solid #e5e7eb;
         font-family:'Poppins',sans-serif;box-shadow:0 2px 10px rgba(0,0,0,0.09);">
      <div style="background:${primary};height:34px;display:flex;align-items:center;
           padding:0 10px;gap:8px;">
        <div style="width:20px;height:20px;background:rgba(255,255,255,0.2);border-radius:4px;"></div>
        <div style="width:65px;height:6px;background:${navText}33;border-radius:3px;"></div>
        <div style="flex:1;"></div>
        <div style="height:18px;background:rgba(255,255,255,0.15);border-radius:4px;
             padding:0 5px;display:flex;align-items:center;">
          <div style="width:5px;height:5px;background:${secondary};border-radius:50%;margin-right:3px;"></div>
          <div style="width:18px;height:4px;background:rgba(255,255,255,0.4);border-radius:2px;"></div>
        </div>
        <div style="width:20px;height:20px;background:${secondary};border-radius:50%;
             display:flex;align-items:center;justify-content:center;">
          <span style="font-family:'Material Symbols Outlined';font-size:11px;color:#fff;">person</span>
        </div>
      </div>
      <div style="display:flex;background:${bg};">
        <div style="width:68px;background:${sbBg};padding:6px 4px;border-right:1px solid rgba(0,0,0,0.05);">
          <div style="height:18px;background:linear-gradient(135deg,${primary},${primary}cc);
               border-radius:5px;margin-bottom:5px;display:flex;align-items:center;padding:0 4px;gap:3px;">
            <div style="width:8px;height:8px;background:rgba(255,255,255,0.3);border-radius:50%;"></div>
            <div style="width:24px;height:4px;background:rgba(255,255,255,0.4);border-radius:2px;"></div>
          </div>
          ${navLinks.map((l, i) => `
          <div style="padding:3px 4px;margin-bottom:1.5px;border-radius:4px;font-size:8px;
               color:${i===0 ? (dark ? "#fff" : primary) : sbTxt};
               background:${i===0 ? (dark ? "rgba(255,255,255,0.16)" : "rgba(30,58,95,0.1)") : "transparent"};
               border-left:2px solid ${i===0 ? (dark ? secondary : primary) : "transparent"};
               white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
            ${l}
          </div>`).join("")}
        </div>
        <div style="flex:1;padding:6px;display:flex;flex-direction:column;gap:4px;">
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:3px;">
            ${["#16a34a","#d97706","#0369a1"].map(c => `
            <div style="height:24px;background:${card};border:1px solid #e5e7eb;border-radius:5px;
                 display:flex;align-items:center;padding:0 4px;gap:3px;">
              <div style="width:5px;height:5px;background:${c};border-radius:50%;"></div>
              <div style="flex:1;height:4px;background:#e5e7eb;border-radius:2px;"></div>
            </div>`).join("")}
          </div>
          <div style="height:32px;background:${card};border:1px solid #e5e7eb;border-radius:5px;
               display:flex;gap:2px;padding:4px 5px;">
            ${[0,1,2,3].map(() => `<div style="flex:1;background:${bg};border-radius:3px;"></div>`).join("")}
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:3px;">
            <div style="height:26px;background:${card};border:1px solid #e5e7eb;border-radius:5px;"></div>
            <div style="height:26px;background:${card};border:1px solid #e5e7eb;border-radius:5px;"></div>
          </div>
        </div>
      </div>
    </div>`;
}


// ── Helpers ────────────────────────────────────────────────────────────
function _swatch(color, label, bordered, textColor) {
    const border = bordered ? "border:1px solid #e5e7eb;" : "";
    const textDot = textColor
        ? `<div style="width:10px;height:10px;background:${textColor};border-radius:50%;
                      border:1px solid rgba(0,0,0,0.15);margin:2px auto 0;" title="Text: ${textColor}"></div>`
        : "";
    return `
    <div style="text-align:center;flex-shrink:0;">
      <div style="width:40px;height:40px;background:${color};border-radius:8px;${border}
                  box-shadow:0 1px 4px rgba(0,0,0,0.12);position:relative;">
        ${textDot}
      </div>
      <div style="font-size:9px;color:#6b7280;margin-top:3px;max-width:44px;
                  word-break:break-all;line-height:1.3;">${label}<br>
        <span style="font-family:monospace;font-size:8px;color:#9ca3af;">${color}</span>
      </div>
    </div>`;
}

function _grade_badge(color, label) {
    return `
    <div style="padding:4px 12px;background:${color}22;border:1px solid ${color}55;
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

function _inject_global_styles() {
    if (document.getElementById("fp-preview-styles")) return;
    $("<style id='fp-preview-styles'>").text(`
        .fp-preview-wrap { padding: 14px 0 4px; }
        .fp-preview-row  { display: flex; gap: 24px; flex-wrap: wrap; align-items: flex-start; }
        .fp-preview-group { }
        .fp-preview-label {
            font-size: 10px; font-weight: 700; text-transform: uppercase;
            letter-spacing: .07em; color: #9ca3af; margin-bottom: 8px;
        }
    `).appendTo("head");
}

// Uniquad Dashboard — SLCM Operations & Insights
//   /desk/uniquad-dashboard                    → command centre (module sidebar, filters, sections, tables)
//   /desk/uniquad-dashboard/student/<student>  → student profile (further drilldown)
//
// Every number and row comes from the server, which reads through frappe.get_list so DocType
// permissions, User Permissions and SLCM's row-level rules apply. The browser only ever sends a
// drilldown key + filter values; nothing here decides who may see what. All data is HTML-escaped
// before it is rendered.

const UQ_PAGE = "uniquad-dashboard";
const UQ_API = "slcm.slcm.page.uniquad_dashboard.uniquad_dashboard.";
const UQ_PAGE_SIZES = [10, 25, 50, 100];
const UQ_BRAND = "#920C24";
const UQ_REFRESH_KEY = "uq-autorefresh-minutes";

frappe.pages[UQ_PAGE].on_page_load = function (wrapper) {
	wrapper.uq = new UniquadDashboard(wrapper);
};
frappe.pages[UQ_PAGE].on_page_show = function (wrapper) {
	wrapper.uq && wrapper.uq.route();
};

// ───────────────────────────────────────────────────────────── helpers

const uq_esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
const uq_int = (v) => format_number(cint(v), "#,##,###.##", 0);
const uq_num = (v, d = 1) => format_number(flt(v), "#,##,###.##", d);
const uq_money = (v) => "₹" + format_number(flt(v), "#,##,###.##", 0);
const uq_date = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 10)) : "—");
const uq_datetime = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 16)) : "—");
const uq_pct = (v) => (v == null || v === "" ? "—" : uq_num(v, 1) + "%");

function uq_format(value, fmt) {
	if (value == null || value === "") return "—";
	if (fmt === "pct") return uq_pct(value);
	if (fmt === "currency") return uq_money(value);
	if (fmt === "gpa") return uq_num(value, 2);
	if (fmt === "text") return String(value);
	return uq_int(value);
}

// frappe.call returns a jQuery Deferred (no .finally); wrap it in a native Promise. `silent` stops Frappe
// from popping raw server messages — the dashboard shows its own loading / empty / error states.
function uq_call(method, args = {}) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method: UQ_API + method,
			args,
			silent: true,
			callback: (r) => resolve(r.message),
			error: (e) => reject(e || new Error("request failed")),
		});
	});
}

function uq_debounce(fn, ms) {
	let t;
	return (...args) => {
		clearTimeout(t);
		t = setTimeout(() => fn(...args), ms);
	};
}

function uq_storage(key, value) {
	try {
		if (value === undefined) return window.localStorage.getItem(key);
		window.localStorage.setItem(key, value);
	} catch (e) {
		return null;
	}
}

function uq_load_font() {
	if (document.getElementById("uq-font")) return;
	$("head").append(
		'<link rel="preconnect" href="https://fonts.googleapis.com">' +
			'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' +
			'<link id="uq-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">'
	);
}

// Lucide icon paths, inlined so the page has one consistent icon family.
const UQ_ICONS = {
	users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
	"user-check": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="m16 11 2 2 4-4"/>',
	"user-plus": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6"/><path d="M22 11h-6"/>',
	"user-x": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="m17 8 5 5"/><path d="m22 8-5 5"/>',
	book: '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>',
	calendar: '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/>',
	check: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
	inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
	alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
	clipboard: '<rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>',
	clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
	file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 13H8"/><path d="M16 17H8"/>',
	edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
	rupee: '<path d="M6 3h12"/><path d="M6 8h12"/><path d="m6 13 8.5 8"/><path d="M6 13h3"/><path d="M9 13c6.667 0 6.667-10 0-10"/>',
	wallet: '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
	card: '<rect width="20" height="14" x="2" y="5" rx="2"/><path d="M2 10h20"/>',
	layers: '<path d="m12.83 2.18 8.58 3.9a1 1 0 0 1 0 1.83l-8.58 3.9a2 2 0 0 1-1.66 0L2.6 7.91a1 1 0 0 1 0-1.83l8.58-3.9a2 2 0 0 1 1.66 0Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
	"x-circle": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
	award: '<circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/>',
	activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
	shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
	loader: '<path d="M21 12a9 9 0 1 1-6.219-8.56"/>',
	chart: '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
	filter: '<path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/>',
	refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
	search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
	download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
	x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
	"chevron-down": '<path d="m6 9 6 6 6-6"/>',
	"chevron-left": '<path d="m15 18-6-6 6-6"/>',
	"chevron-right": '<path d="m9 18 6-6-6-6"/>',
	"chevrons-left": '<path d="m11 17-5-5 5-5"/><path d="m18 17-5-5 5-5"/>',
	"chevrons-right": '<path d="m6 17 5-5-5-5"/><path d="m13 17 5-5-5-5"/>',
	"arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
	"arrow-left": '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
	"sort-none": '<path d="m21 16-4 4-4-4"/><path d="M17 20V4"/><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/>',
	"sort-asc": '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
	"sort-desc": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
	lock: '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
	external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
	maximize: '<path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/>',
	info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
	history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
	table: '<path d="M12 3v18"/><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/>',
	graduation: '<path d="M21.42 10.922a1 1 0 0 0-.019-1.838L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.832l8.57 3.908a2 2 0 0 0 1.66 0z"/><path d="M22 10v6"/><path d="M6 12.5V16a6 3 0 0 0 12 0v-3.5"/>',
	briefcase: '<path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/><rect width="20" height="14" x="2" y="6" rx="2"/>',
	flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
	building: '<rect width="16" height="20" x="4" y="2" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/>',
	home: '<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/><path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
	target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
	scale: '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
	menu: '<path d="M4 12h16"/><path d="M4 6h16"/><path d="M4 18h16"/>',
	"panel-left": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
	dashboard: '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
	sliders: '<path d="M21 4h-7"/><path d="M10 4H3"/><path d="M21 12h-9"/><path d="M8 12H3"/><path d="M21 20h-5"/><path d="M12 20H3"/><path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>',
	"list-todo": '<rect x="3" y="5" width="6" height="6" rx="1"/><path d="m3 17 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/>',
	pulse: '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
	list: '<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M8 6h13"/>',
	tool: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
	"search-x": '<path d="m13.5 8.5-5 5"/><path d="m8.5 8.5 5 5"/><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
};
const uq_icon = (name, size = 16, cls = "") =>
	`<svg class="uq-icon ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${UQ_ICONS[name] || ""}</svg>`;

const UQ_BADGE = {
	good: ["Active", "Present", "Completed", "Conducted", "Eligible", "Marked", "Paid", "Approved", "Enrolled", "Yes", "Submitted", "Locked", "Core", "Full Fee Paid", "Offer Accepted"],
	warn: ["Pending", "Scheduled", "Draft", "Partially Paid", "May Be Approved", "Postponed", "Late", "Requested", "Planned", "Elective", "Selected", "OD", "Excused"],
	bad: ["Overdue", "Cancelled", "Absent", "Shortage", "Not Marked", "Rejected", "Inactive", "Dropped", "Withdrawn", "No", "Dormant", "Blocked", "Offer Declined", "Offer Expired"],
	info: ["Graduated", "Alumni", "Waived"],
};
function uq_badge(value) {
	if (value == null || value === "") return '<span class="muted">—</span>';
	let cls = "";
	for (const [k, list] of Object.entries(UQ_BADGE)) if (list.includes(value)) cls = k;
	if (!cls && /^Pending/.test(value)) cls = "warn";
	return `<span class="uq-badge ${cls}">${uq_esc(value)}</span>`;
}

function uq_pct_cell(value, threshold) {
	if (value == null || value === "") return '<span class="muted">—</span>';
	const v = flt(value);
	const low = threshold && v < threshold;
	return `<span class="uq-pct ${low ? "low" : ""}" title="${low ? __("Below {0}% threshold", [threshold]) : ""}">
		<b>${uq_num(v, 1)}%</b>${low ? '<span class="uq-sr">' + __("below threshold") + "</span>" : ""}
		<span class="uq-pct-bar" aria-hidden="true"><i style="width:${Math.max(0, Math.min(100, v))}%"></i></span></span>`;
}

// ───────────────────────────────────────────────────────────── filter definitions
// `parents` maps an option attribute → the filter whose selection narrows this one. Options with no
// value for that attribute stay visible, and every filter is also directly searchable, so users never
// have to walk the hierarchy to reach a value they already know.

const UQ_FILTERS = [
	{ key: "academic_year", label: __("Academic Year"), primary: true },
	{ key: "academic_term", label: __("Academic Term"), primary: true, parents: { academic_year: "academic_year" } },
	{ key: "programme", label: __("Programme"), primary: true, parents: { academic_year: "academic_year" } },
	{ key: "batch", label: __("Batch"), parents: { programme: "programme", academic_year: "academic_year" } },
	{ key: "section", label: __("Section"), parents: { batch: "batch" } },
	{ key: "faculty", label: __("Faculty") },
	{
		key: "course",
		label: __("Course"),
		parents: { programme: "programme", batch: "batch", academic_term: "academic_term", academic_year: "academic_year", faculty: "faculty" },
	},
	{ key: "student_status", label: __("Student Status") },
	{ key: "gender", label: __("Gender") },
];

// Modules, in the order the office works with them. Each opens its own page with the related data.
const UQ_MODULES = [
	{ key: "admission", title: __("Admission"), icon: "inbox", desc: __("The application pipeline, from submission to enrolment."), charts: ["application_stages"], tables: ["applications"] },
	{ key: "registration", title: __("Student Registration"), icon: "user-check", desc: __("Student population, status and the registration workflow."), charts: ["students_by_stage", "students_by_status", "students_by_programme", "students_by_gender"], tables: ["recent_students"] },
	{ key: "programme", title: __("Programme Management"), icon: "graduation", desc: __("Terms, programmes, batches, courses running and the teaching schedule."), charts: ["classes_weekly"], tables: ["todays_schedule", "offerings"] },
	{ key: "attendance", title: __("Attendance"), icon: "check", desc: __("Attendance levels, entry completeness, shortfalls and condonation."), charts: ["attendance_trend", "course_attendance"], tables: ["attendance_exceptions"] },
	{ key: "idcard", title: __("ID Card"), icon: "card", desc: __("Student ID card generation, printing and RFID coverage."), charts: [], tables: ["idcards"] },
	{ key: "fees", title: __("Fees"), icon: "rupee", desc: __("Dues, collections, payments, refunds and concessions."), charts: [], tables: ["fee_payments", "fee_overdue"] },
	{ key: "venue", title: __("Venue Booking"), icon: "building", desc: __("Venue requests, allotments and venue availability."), charts: ["venue_by_status", "venue_by_approver", "venue_by_requester", "venue_swaps"], tables: ["venue_bookings_all"] },
	{ key: "pace", title: __("PACE"), icon: "layers", desc: __("PACE enquiries, applications and document verification."), charts: [], tables: ["pace_applications"] },
	{ key: "fle", title: __("FLE"), icon: "scale", desc: __("Foundations for a Legal Education registrations, payments and enrolment."), charts: [], tables: ["fle_registrations"] },
	{ key: "exams", title: __("Examinations"), icon: "award", desc: __("Marks entry progress and published results."), charts: [], tables: ["marks_all"] },
];
// Short labels for the three figures on each home tile (full titles stay on the module page).
const UQ_SHORT = {
	applications: __("Applications"), applications_in_progress: __("In progress"), applications_enrolled: __("Enrolled"),
	students: __("Students"), active_students: __("Active"), registration_pending: __("Pending registration"),
	programmes: __("Programmes"), active_offerings: __("Courses running"), todays_classes: __("Classes today"),
	avg_attendance: __("Avg attendance"), entry_rate: __("Entry rate"), below_threshold: __("Below threshold"),
	idcards_generated: __("Cards generated"), id_card_pending: __("Without ID card"), idcards_error: __("Card errors"),
	fee_outstanding: __("Outstanding"), fee_collected: __("Collected"), fee_overdue: __("Overdue dues"),
	venue_bookings_all: __("Bookings"), venue_bookings: __("Allotted"), venue_pending: __("Pending requests"),
	pace_applications: __("Applications"), pace_in_progress: __("In progress"), pace_verification_pending: __("Verifications due"),
	fle_registrations: __("Registrations"), fle_enrolled: __("Enrolled"), fle_unpaid: __("Unpaid"),
	marks_all: __("Marks entries"), results_published: __("Results published"), marks_draft: __("Marks in draft"),
};
// Headline figures on the home Overview (shown only when the user can read them).
const UQ_HOME_KPIS = ["students", "active_offerings"];
// Modules whose open items feed the cross-module Pending Operations list (server whitelist mirrors this).
const PENDING_MODULES = ["attendance", "registration", "venue", "exams", "fees", "idcard", "pace", "fle"];
// Home analytics panel → the module it belongs to (hidden when that module is unticked in Customize).
const UQ_PANEL_MODULE = {
	home_fees: "fees", attendance_trend: "attendance", course_attendance: "attendance",
	students_by_status: "registration", students_by_programme: "registration", students_by_stage: "registration",
	application_stages: "admission",
};
const UQ_MODULE_BY_KEY = Object.fromEntries(UQ_MODULES.map((m) => [m.key, m]));

// ───────────────────────────────────────────────────────────── multi-select

class UqMultiSelect {
	constructor($mount, def, on_change) {
		this.def = def;
		this.on_change = on_change;
		this.options = [];
		this.visible = [];
		this.selected = new Set();
		this.query = "";
		this.id = "uq-ms-" + def.key;
		this.$el = $(`
			<div class="uq-field uq-ms" data-key="${def.key}">
				<span class="uq-field-label" id="${this.id}-label">${uq_esc(def.label)}</span>
				<button type="button" class="uq-ms-toggle" aria-haspopup="listbox" aria-expanded="false" aria-labelledby="${this.id}-label ${this.id}-value">
					<span id="${this.id}-value">${__("All")}</span>${uq_icon("chevron-down", 14)}
				</button>
				<div class="uq-ms-pop" role="dialog" aria-label="${uq_esc(def.label)}">
					<div class="uq-ms-search">${uq_icon("search", 14)}<input type="search" placeholder="${__("Search {0}", [def.label])}" aria-label="${__("Search {0}", [def.label])}"></div>
					<div class="uq-ms-bulk"><button type="button" data-act="all">${__("Select All")}</button><button type="button" data-act="clear">${__("Clear All")}</button></div>
					<div class="uq-ms-list" role="listbox" aria-multiselectable="true"></div>
					<div class="uq-ms-foot"></div>
				</div>
			</div>`).appendTo($mount);
		this.$toggle = this.$el.find(".uq-ms-toggle");
		this.$list = this.$el.find(".uq-ms-list");
		this.$search = this.$el.find("input[type=search]");
		this.bind();
		this.set_loading(true);
	}

	bind() {
		this.$toggle.on("click", () => (this.$el.hasClass("open") ? this.close() : this.open()));
		this.$search.on("input", uq_debounce(() => {
			this.query = this.$search.val().trim().toLowerCase();
			this.render_list();
		}, 120));
		this.$el.on("click", "[data-act=all]", () => {
			this.visible_filtered().forEach((o) => this.selected.add(o.value));
			this.changed();
		});
		this.$el.on("click", "[data-act=clear]", () => {
			this.selected.clear();
			this.changed();
		});
		this.$list.on("change", "input[type=checkbox]", (e) => {
			const v = e.currentTarget.value;
			e.currentTarget.checked ? this.selected.add(v) : this.selected.delete(v);
			this.changed(false);
		});
		this.$el.on("keydown", (e) => {
			if (e.key === "Escape" && this.$el.hasClass("open")) {
				e.stopPropagation();
				this.close();
				this.$toggle.trigger("focus");
			}
			if (e.key === "ArrowDown" && document.activeElement === this.$search[0]) {
				e.preventDefault();
				this.$list.find("input").first().trigger("focus");
			}
		});
	}

	open() {
		$(".uq-ms.open").not(this.$el).each((_, el) => $(el).data("ms")?.close());
		this.$el.addClass("open");
		this.$toggle.attr("aria-expanded", "true");
		const pop = this.$el.find(".uq-ms-pop");
		pop.removeClass("align-right");
		const rect = this.$el[0].getBoundingClientRect();
		if (rect.left + 290 > window.innerWidth) pop.addClass("align-right");
		this.render_list();
		setTimeout(() => this.$search.trigger("focus"), 0);
	}

	close() {
		this.$el.removeClass("open");
		this.$toggle.attr("aria-expanded", "false");
	}

	set_loading(on) {
		this.loading = on;
		this.$toggle.prop("disabled", on);
		if (on) this.$el.find(`#${this.id}-value`).text(__("Loading…"));
	}

	set_options(options) {
		this.options = options || [];
		this.visible = this.options;
		this.set_loading(false);
		this.update_label();
	}

	set_visible(visible) {
		this.visible = visible;
		const allowed = new Set(visible.map((o) => o.value));
		let pruned = false;
		[...this.selected].forEach((v) => {
			if (!allowed.has(v)) {
				this.selected.delete(v);
				pruned = true;
			}
		});
		this.update_label();
		if (this.$el.hasClass("open")) this.render_list();
		return pruned;
	}

	visible_filtered() {
		if (!this.query) return this.visible;
		return this.visible.filter((o) => `${o.label} ${o.value} ${o.hint || ""}`.toLowerCase().includes(this.query));
	}

	render_list() {
		const opts = this.visible_filtered();
		if (!this.options.length) {
			this.$list.html(`<div class="uq-ms-empty">${__("No options available for your access.")}</div>`);
		} else if (!opts.length) {
			this.$list.html(`<div class="uq-ms-empty">${__("No matches for “{0}”.", [uq_esc(this.query)])}</div>`);
		} else {
			this.$list.html(
				opts
					.slice(0, 500)
					.map((o) => {
						const hint = o.hint && o.hint !== o.label ? `<small>${uq_esc(o.hint)}</small>` : "";
						return `<label class="uq-ms-opt" role="option" aria-selected="${this.selected.has(o.value)}">
							<input type="checkbox" value="${uq_esc(o.value)}" ${this.selected.has(o.value) ? "checked" : ""}>
							<span>${uq_esc(o.label)}${hint}</span></label>`;
					})
					.join("")
			);
		}
		const hidden = this.options.length - this.visible.length;
		this.$el.find(".uq-ms-foot").text(
			[
				__("{0} selected", [this.selected.size]),
				hidden > 0 ? __("{0} hidden by other filters", [hidden]) : "",
				opts.length > 500 ? __("showing first 500 — refine your search") : "",
			]
				.filter(Boolean)
				.join(" · ")
		);
	}

	changed(rerender = true) {
		this.update_label();
		if (rerender) this.render_list();
		else this.$el.find(".uq-ms-foot").text(__("{0} selected", [this.selected.size]));
		this.on_change && this.on_change(this.def.key);
	}

	update_label() {
		const n = this.selected.size;
		let text = __("All");
		if (n === 1) {
			const v = [...this.selected][0];
			text = (this.options.find((o) => o.value === v) || {}).label || v;
		} else if (n > 1) text = __("{0} selected", [n]);
		this.$el.find(`#${this.id}-value`).text(text);
		this.$toggle.toggleClass("active", n > 0);
	}

	get_value() {
		return [...this.selected];
	}

	set_value(values) {
		this.selected = new Set(values || []);
		this.update_label();
	}

	label_for(value) {
		return (this.options.find((o) => o.value === value) || {}).label || value;
	}
}

// ───────────────────────────────────────────────────────────── data table (inline + modal)

class UqTable {
	constructor(dash, $mount, { key, params = {}, filters = null, page_size = 10, compact = false, on_meta = null, empty = null }) {
		this.empty_text = empty;
		this.dash = dash;
		this.key = key;
		this.params = params;
		this.filters_override = filters;
		this.page = 1;
		this.page_size = page_size;
		this.search = "";
		this.sort_by = null;
		this.sort_order = null;
		this.on_meta = on_meta;
		this.compact = compact;
		this.req = 0;
		this.$el = $(`
			<div class="uq-dt">
				<div class="uq-dt-bar">
					<div class="uq-search">${uq_icon("search", 14)}<input type="search" placeholder="${__("Search…")}" aria-label="${__("Search records")}"></div>
					<div class="uq-dt-tools"></div>
				</div>
				<div class="uq-dt-scroll" tabindex="0" aria-live="polite"></div>
				<div class="uq-dt-foot"></div>
			</div>`).appendTo($mount);
		this.$scroll = this.$el.find(".uq-dt-scroll");
		this.$foot = this.$el.find(".uq-dt-foot");
		this.bind();
	}

	filters() {
		return this.filters_override || this.dash.applied;
	}

	bind() {
		this.$el.find(".uq-search input").on(
			"input",
			uq_debounce((e) => {
				this.search = e.target.value.trim();
				this.page = 1;
				this.load();
			}, 350)
		);
		this.$scroll.on("click", "th button[data-sort]", (e) => {
			const f = $(e.currentTarget).data("sort");
			if (this.sort_by === f) this.sort_order = this.sort_order === "asc" ? "desc" : "asc";
			else {
				this.sort_by = f;
				this.sort_order = "asc";
			}
			this.page = 1;
			this.load();
		});
		this.$scroll.on("click", "[data-student]", (e) => {
			e.preventDefault();
			this.dash.open_student($(e.currentTarget).attr("data-student"));
		});
		this.$scroll.on("click", "[data-offering]", (e) => {
			e.preventDefault();
			const o = $(e.currentTarget).attr("data-offering");
			this.dash.modal.open({ key: "offering_attendance", params: { course_offering: o }, subtitle: o });
		});
		this.$foot.on("click", "[data-page]", (e) => {
			this.page = cint($(e.currentTarget).attr("data-page"));
			this.load();
		});
		this.$foot.on("change", "select", (e) => {
			this.page_size = cint(e.target.value);
			this.page = 1;
			this.load();
		});
	}

	args() {
		return {
			key: this.key,
			filters: JSON.stringify(this.filters()),
			params: JSON.stringify(this.params || {}),
			search: this.search,
			sort_by: this.sort_by || "",
			sort_order: this.sort_order || "",
		};
	}

	skeleton() {
		const rows = Array.from({ length: Math.min(this.page_size, 6) })
			.map(() => `<tr>${'<td><div class="uq-skel" style="height:12px"></div></td>'.repeat(5)}</tr>`)
			.join("");
		this.$scroll.html(`<table class="uq-table" aria-busy="true"><tbody>${rows}</tbody></table>`);
	}

	load() {
		const id = ++this.req;
		if (!this.data) this.skeleton();
		else this.$scroll.css("opacity", 0.55);
		return uq_call("get_drilldown", { ...this.args(), page: this.page, page_size: this.page_size })
			.then((msg) => {
				if (id !== this.req) return;
				this.$scroll.css("opacity", "");
				const d = msg || {};
				if (d.restricted) return this.render_state("lock", __("Not available for your role"), __("You do not have access to these records."), true);
				if (d.error) return this.render_state("alert", __("Unable to load data."), __("Please try again."));
				this.data = d;
				this.sort_by = d.sort_by;
				this.sort_order = d.sort_order;
				this.render();
				this.on_meta && this.on_meta(d);
			})
			.catch(() => {
				if (id !== this.req) return;
				this.$scroll.css("opacity", "");
				this.render_state("alert", __("Unable to load data."), __("Please try again."));
			});
	}

	render_state(icon, title, text, restricted = false) {
		this.restricted = restricted;
		this.$scroll.html(`<div class="uq-empty">${uq_icon(icon, 28)}<strong>${uq_esc(title)}</strong>${uq_esc(text)}</div>`);
		this.$foot.empty();
		this.on_meta && this.on_meta({ restricted, total: 0 });
	}

	cell(col, row) {
		const v = row[col.field];
		const t = this.dash.threshold;
		switch (col.kind) {
			case "student":
				return v ? `<button type="button" class="uq-link" data-student="${uq_esc(v)}" title="${__("Open student profile")}">${uq_esc(v)}</button>` : "—";
			case "offering":
				return v ? `<button type="button" class="uq-link" data-offering="${uq_esc(v)}" title="${__("View student attendance for this offering")}">${uq_esc(v)}</button>` : "—";
			case "form":
				return v ? `<a href="${uq_esc(frappe.utils.get_form_link(this.data.doctype, v))}" title="${__("Open record")}">${uq_esc(v)}</a>` : "—";
			case "record":
				// multi-source lists: each row names its own doctype
				return v && row.ref_doctype
					? row.ref_doctype === "Student Master"
						? `<button type="button" class="uq-link" data-student="${uq_esc(v)}">${__("View student")}</button>`
						: `<a href="${uq_esc(frappe.utils.get_form_link(row.ref_doctype, v))}">${__("Open")} ${uq_icon("arrow-right", 11)}</a>`
					: "—";
			case "badge":
				return uq_badge(v);
			case "pct":
				return col.field === "attendance_percentage" || col.field === "avg_attendance" ? uq_pct_cell(v, t) : uq_pct(v);
			case "int":
				return v == null ? "—" : uq_int(v);
			case "float":
				return v == null ? "—" : uq_num(v, 1);
			case "currency":
				return v == null ? "—" : uq_money(v);
			case "date":
				return uq_date(v);
			case "datetime":
				return uq_datetime(v);
			default:
				return v == null || v === "" ? '<span class="muted">—</span>' : uq_esc(v);
		}
	}

	render() {
		const d = this.data;
		const num = (c) => ["int", "float", "currency", "pct"].includes(c.kind);
		if (!d.rows.length) {
			const searching = !!this.search;
			this.$scroll.html(`<div class="uq-empty">${uq_icon(searching ? "search-x" : "inbox", 28)}
				<strong>${searching ? __("No records match “{0}”.", [uq_esc(this.search)]) : uq_esc(this.empty_text || __("No data available for the selected filters."))}</strong>
				${searching ? __("Try a different search term.") : this.empty_text ? "" : __("Try changing your filters.")}</div>`);
		} else {
			const head = d.columns
				.map((c) => {
					const cls = num(c) ? "num" : "";
					if (!c.sortable) return `<th scope="col" class="${cls}"><span>${uq_esc(c.label)}</span></th>`;
					const active = d.sort_by === c.field;
					const aria = active ? (d.sort_order === "asc" ? "ascending" : "descending") : "none";
					const icon = active ? (d.sort_order === "asc" ? "sort-asc" : "sort-desc") : "sort-none";
					return `<th scope="col" class="${cls}" aria-sort="${aria}"><button type="button" data-sort="${uq_esc(c.field)}" title="${__("Sort by {0}", [uq_esc(c.label)])}">${uq_esc(c.label)} ${uq_icon(icon, 12)}</button></th>`;
				})
				.join("");
			const body = d.rows
				.map((r) => `<tr>${d.columns.map((c) => `<td class="${num(c) ? "num" : ""}">${this.cell(c, r)}</td>`).join("")}</tr>`)
				.join("");
			this.$scroll.html(`<table class="uq-table"><caption class="uq-sr">${uq_esc(d.title)}</caption><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`);
		}
		const pages = Math.max(1, Math.ceil(d.total / d.page_size));
		const from = d.total ? (d.page - 1) * d.page_size + 1 : 0;
		const to = Math.min(d.page * d.page_size, d.total);
		this.$foot.html(`
			<span>${__("Showing {0}–{1} of {2}", [uq_int(from), uq_int(to), uq_int(d.total)])}</span>
			<div class="uq-pager">
				<label class="uq-sr" for="uq-ps-${this.key}">${__("Rows per page")}</label>
				<select id="uq-ps-${this.key}">${UQ_PAGE_SIZES.map((s) => `<option value="${s}" ${s === d.page_size ? "selected" : ""}>${__("{0} / page", [s])}</option>`).join("")}</select>
				<button type="button" data-page="1" ${d.page <= 1 ? "disabled" : ""} aria-label="${__("First page")}">${uq_icon("chevrons-left", 14)}</button>
				<button type="button" data-page="${d.page - 1}" ${d.page <= 1 ? "disabled" : ""} aria-label="${__("Previous page")}">${uq_icon("chevron-left", 14)}</button>
				<span class="uq-pager-info">${__("Page {0} of {1}", [d.page, pages])}</span>
				<button type="button" data-page="${d.page + 1}" ${d.page >= pages ? "disabled" : ""} aria-label="${__("Next page")}">${uq_icon("chevron-right", 14)}</button>
				<button type="button" data-page="${pages}" ${d.page >= pages ? "disabled" : ""} aria-label="${__("Last page")}">${uq_icon("chevrons-right", 14)}</button>
			</div>`);
	}

	export_csv() {
		if (this.restricted) return;
		open_url_post("/api/method/" + UQ_API + "export_drilldown", this.args());
		frappe.show_alert({ message: __("Preparing CSV export…"), indicator: "blue" }, 3);
	}
}

// ───────────────────────────────────────────────────────────── drilldown modal (centered, stackable)

class UqModal {
	constructor(dash) {
		this.dash = dash;
		this.stack = [];
		this.$root = $(`
			<div class="uq uq-modal-root" aria-hidden="true">
				<div class="uq-modal-backdrop" data-close></div>
				<div class="uq-modal" role="dialog" aria-modal="true" aria-labelledby="uq-modal-title" tabindex="-1">
					<div class="uq-modal-head">
						<div style="min-width:0;flex:1">
							<div class="uq-modal-crumbs"></div>
							<h2 id="uq-modal-title"></h2>
							<p class="uq-modal-desc"></p>
							<div class="uq-modal-scope"></div>
						</div>
						<button type="button" class="uq-modal-close" data-close aria-label="${__("Close")}">${uq_icon("x", 18)}</button>
					</div>
					<div class="uq-modal-body"></div>
					<div class="uq-modal-foot">
						<span class="uq-foot-note">${uq_icon("shield", 14)}${__("Only records you are permitted to access are shown and exported. Current filters and search apply.")}</span>
						<div style="display:flex;gap:8px">
							<button type="button" class="uq-btn" data-back hidden>${uq_icon("arrow-left", 14)} ${__("Back")}</button>
							<button type="button" class="uq-btn" data-export>${uq_icon("download", 14)} ${__("Export CSV")}</button>
							<button type="button" class="uq-btn" data-close data-close-btn>${__("Close")}</button>
							<a class="uq-btn uq-btn-primary" data-open-page hidden href="#">${uq_icon("external", 14)} <span></span></a>
						</div>
					</div>
				</div>
			</div>`).appendTo(document.body);
		this.$root.on("click", "[data-close]", () => this.close());
		// Any link inside the modal (record IDs, "Open …", report links) navigates via Frappe's router.
		// Close *after* the click has bubbled to the router — closing synchronously would detach the
		// link first, and the router would miss it (turning an in-app route into a full page reload).
		this.$root.on("click", "a[href]", (e) => {
			if (e.ctrlKey || e.metaKey || e.shiftKey || e.currentTarget.target === "_blank") return;
			setTimeout(() => this.close(), 0);
		});
		this.$root.on("click", "[data-preview-status]", (e) => {
			const cur = this.current();
			const v = $(e.currentTarget).attr("data-preview-status");
			this.open({ key: cur.view.key, params: { status: v }, subtitle: v || __("Not set"), open: cur.view.open });
		});
		this.$root.on("click", "[data-preview-recent]", () => {
			const cur = this.current();
			this.open({ key: cur.view.key, params: { recent: "range" }, filters: this.dash.applied, subtitle: __("Created in date range"), open: cur.view.open });
		});
		this.$root.on("click", "[data-modal-drill]", (e) => {
			const $b = $(e.currentTarget);
			const params = $b.attr("data-modal-params") ? JSON.parse($b.attr("data-modal-params")) : {};
			this.open({ key: $b.attr("data-modal-drill"), params, subtitle: $b.attr("data-modal-subtitle") || "", open: this.current() && this.current().view.open });
		});
		this.$root.on("click", "[data-preview-ref]", (e) => {
			const dt = $(e.currentTarget).attr("data-preview-ref");
			this.open({ key: "dt:" + dt, preview: dt, open: { route: $(e.currentTarget).attr("data-route"), label: __("Open {0}", [__(dt)]) } });
		});
		this.$root.on("click", "[data-back]", () => this.back());
		this.$root.on("click", "[data-export]", () => this.current() && this.current().table.export_csv());
		this.$root.on("keydown", (e) => {
			if (e.key === "Escape") {
				if ($(e.target).closest(".uq-ms.open").length) return;
				e.preventDefault();
				this.stack.length > 1 ? this.back() : this.close();
			}
			if (e.key === "Tab") this.trap(e);
		});
	}

	current() {
		return this.stack[this.stack.length - 1];
	}

	is_open() {
		return this.$root.hasClass("open");
	}

	trap(e) {
		const focusable = this.$root.find("button:visible:not(:disabled), a[href]:visible, input:visible, select:visible, [tabindex='0']:visible").toArray();
		if (!focusable.length) return;
		const first = focusable[0];
		const last = focusable[focusable.length - 1];
		if (e.shiftKey && document.activeElement === first) {
			e.preventDefault();
			last.focus();
		} else if (!e.shiftKey && document.activeElement === last) {
			e.preventDefault();
			first.focus();
		}
	}

	// view: { key, params?, filters?, title?, subtitle? }
	open(view) {
		if (!this.is_open()) {
			this.stack = [];
			this.return_focus = document.activeElement;
			this.$root.addClass("open").attr("aria-hidden", "false");
			$("body").addClass("uq-modal-open");
			this.dash.lock_scroll(true);
		}
		const $body = $('<div class="uq-modal-view"></div>');
		this.$root.find(".uq-modal-view").hide();
		this.$root.find(".uq-modal-body").append($body);
		const entry = { view, $body };
		this.stack.push(entry);
		if (view.info) {
			// tools / reports: a preview card, no table
			entry.meta = { title: view.title, description: view.description || "", restricted: true, info: true };
			// the title already carries the context; no subtitle needed
			$body.html(`<div class="uq-empty">${uq_icon("loader", 22, "uq-spin")}</div>`);
			view.info($body, entry);
			this.render_head();
			setTimeout(() => this.$root.find(".uq-modal").trigger("focus"), 0);
			return;
		}
		if (view.preview) {
			const $sum = $('<div class="uq-preview-sum"><div class="uq-skel" style="height:64px"></div></div>').appendTo($body);
			uq_call("get_list_preview", { doctype: view.preview, filters: JSON.stringify(this.dash.applied) })
				.then((d) => this.render_preview_summary($sum, d || {}))
				.catch(() => $sum.empty());
		}
		entry.table = new UqTable(this.dash, $body, {
			key: view.key,
			params: view.params,
			filters: view.filters || null,
			page_size: 10,
			on_meta: (d) => {
				entry.meta = d;
				this.render_head();
			},
		});
		this.render_head();
		entry.table.load();
		setTimeout(() => this.$root.find(".uq-modal").trigger("focus"), 0);
	}

	back() {
		const top = this.stack.pop();
		top && top.$body.remove();
		const cur = this.current();
		if (!cur) return this.close();
		cur.$body.show();
		this.render_head();
	}

	render_head() {
		const cur = this.current();
		if (!cur) return;
		const m = cur.meta || {};
		const title = cur.view.title || m.title || __("Loading…");
		this.$root.find("#uq-modal-title").text(title + (cur.view.subtitle ? " — " + cur.view.subtitle : ""));
		this.$root.find(".uq-modal-desc").text(m.description || "").toggle(!!m.description);
		const crumbs = this.stack.slice(0, -1).map((e) => uq_esc((e.meta && e.meta.title) || ""));
		this.$root.find(".uq-modal-crumbs").html(
			[__("Uniquad Dashboard"), ...crumbs].map((c) => `<span>${c}</span>`).join(uq_icon("chevron-right", 11))
		);
		this.$root.find("[data-back]").prop("hidden", this.stack.length < 2);
		this.$root.find("[data-export]").prop("disabled", !!m.restricted || !m.total).toggle(!m.info);
		const open = cur.view.open;
		const $open = this.$root.find("[data-open-page]");
		$open.prop("hidden", !open);
		if (open) $open.attr("href", open.route).find("span").text(open.label);
		const scope = m.info
			? ""
			: m.all_time
			? `<span class="uq-state alltime">${uq_icon("history", 12)} ${__("All-Time — filters not applied")}</span>`
			: this.dash.scope_chips(m.applies || [], cur.view.filters);
		this.$root.find(".uq-modal-scope").html(scope).toggle(!!scope);
		this.$root.find(".uq-foot-note").css("visibility", m.info ? "hidden" : "");
	}

	render_preview_summary($sum, d) {
		if (d.restricted) return $sum.empty();
		const tile = (label, value, attr = "") =>
			`<${attr ? "button type=\"button\"" : "div"} class="uq-pv-tile" ${attr}><span class="uq-pv-v">${uq_esc(value)}</span><span class="uq-pv-l">${uq_esc(label)}</span></${attr ? "button" : "div"}>`;
		const tiles = [
			tile(__("Total records"), uq_int(d.total)),
			d.created_in_range != null ? tile(__("Created in date range"), uq_int(d.created_in_range), d.created_in_range ? "data-preview-recent" : "") : "",
			tile(__("Updated in last 7 days"), uq_int(d.updated_week)),
		].join("");
		const total = (d.statuses || []).reduce((a, b) => a + b.count, 0) || 1;
		const chips = (d.statuses || []).length
			? `<div class="uq-pv-status"><span class="uq-pv-status-l">${uq_esc(d.status_label || __("Status"))}:</span>
				${d.statuses
					.map((st) => `<button type="button" class="uq-pv-chip" data-preview-status="${uq_esc(st.value)}" title="${__("Show only {0}", [uq_esc(st.value || __("Not set"))])}">
						${uq_badge(st.value || __("Not set"))}<b>${uq_int(st.count)}</b><i style="width:${Math.max(4, (100 * st.count) / total)}%"></i></button>`)
					.join("")}</div>`
			: "";
		$sum.html(`<div class="uq-pv-tiles">${tiles}</div>${chips}`);
	}

	close() {
		this.$root.removeClass("open").attr("aria-hidden", "true");
		$("body").removeClass("uq-modal-open");
		this.dash.lock_scroll(false);
		this.$root.find(".uq-modal-body").empty();
		this.stack = [];
		if (this.return_focus && document.body.contains(this.return_focus)) this.return_focus.focus();
	}
}

// ───────────────────────────────────────────────────────────── dashboard (module-first command centre)
//   Home   → module tiles (headline numbers + attention), cross-module Action Required, activity, all-time
//   Module → that module's summary figures, what needs attention, charts, running tables, desk links

const UQ_SB_KEY = "uq-sidebar-collapsed";
const UQ_SB_GROUPS_KEY = "uq-sidebar-groups";
const UQ_HOME_MODULES_KEY = "uq-home-modules";

// Running tables. Every panel states the question it answers.
const UQ_TABLES = {
	applications: { title: __("Application Pipeline"), q: __("Most recently updated applications.") },
	recent_students: { title: __("Recent Students"), q: __("Which student records changed most recently?") },
	todays_schedule: { title: __("Today's Schedule"), q: __("What is on the timetable today, and where?"), empty: __("No classes are scheduled for today.") },
	offerings: { title: __("Course Operations"), q: __("Which running courses have sessions without attendance, or low attendance? Open an offering to see its students.") },
	attendance_exceptions: { title: __("Attendance Exceptions"), q: __("Which past sessions still need attention?"), params: { mode: "unmarked" }, modes: true },
	idcards: { title: __("Student ID Cards"), q: __("Latest ID card records and their status.") },
	fee_payments: { title: __("Recent Fee Payments"), q: __("Payments received within the date range."), empty: __("No fee payments in the selected date range.") },
	fee_overdue: { title: __("Overdue Fee Demands"), q: __("Which dues are past their due date?"), empty: __("No overdue fee demands — all clear.") },
	venue_bookings_all: { title: __("Venue Bookings"), q: __("Bookings starting within the date range, any status."), empty: __("No venue bookings in the selected date range.") },
	pace_applications: { title: __("PACE Applications"), q: __("Most recently updated PACE applications."), empty: __("No PACE applications for the selected academic year.") },
	fle_registrations: { title: __("FLE Registrations"), q: __("Registrations within the date range."), empty: __("No FLE registrations in the selected date range.") },
	marks_all: { title: __("Course Marks"), q: __("Latest marks entries for the selected term.") },
	pending_operations: { title: __("Pending Operations"), q: __("Every open item across modules, oldest first, with who is responsible."), empty: __("Nothing is pending — all clear.") },
	recent_activity: { title: __("Recent Activity"), q: __("What changed most recently across SLCM?"), empty: __("No recent changes in the selected scope.") },
};

const UQ_CHART_PANELS = {
	application_stages: { title: __("Application Pipeline by Stage"), q: __("At which stage are current applicants sitting?"), kind: "bars" },
	students_by_stage: { title: __("Registration Stage"), q: __("Where are students in the registration workflow?"), kind: "bars" },
	students_by_status: { title: __("Students by Status"), q: __("Active versus inactive, graduated or withdrawn. Select a bar to list them."), kind: "bars" },
	students_by_programme: { title: __("Students by Programme"), q: __("Where are students concentrated? Select a bar to list them."), kind: "bars" },
	students_by_gender: { title: __("Gender"), q: __("Gender split of students in scope. Select a bar to list them."), kind: "bars" },
	classes_weekly: { title: __("Classes Scheduled"), q: __("Is the teaching load steady across the date range? (per week, or per day for short ranges)"), kind: "chart" },
	attendance_trend: { title: __("Presence Trend"), q: __("Is attendance improving or slipping? (per week, or per day for short ranges)"), kind: "chart" },
	course_attendance: { title: __("Lowest Course Attendance"), q: __("Which courses have the weakest average attendance? Select one to see its students."), kind: "bars" },
	tickets_open_status: { title: __("Open Tickets"), q: __("Helpdesk tickets not yet resolved or closed, by status (all dates). Select a bar to list them."), kind: "bars" },
	tickets_open_team: { title: __("Open Tickets by Team"), q: __("Which helpdesk team is holding the unresolved tickets? (all dates)"), kind: "bars" },
	tickets_raised_kind: { title: __("Tickets Raised By"), q: __("Are students, faculty or others raising the tickets opened in the date range?"), kind: "bars" },
	tickets_top_raisers: { title: __("Top Ticket Raisers"), q: __("Who raised the most tickets in the date range? Select one to see their tickets."), kind: "bars" },
	tickets_by_type: { title: __("Tickets by Type"), q: __("What are tickets opened in the date range about?"), kind: "bars" },
	venue_by_status: { title: __("Venue Bookings by Status"), q: __("Pending, allotted, rejected and cancelled bookings starting in the date range."), kind: "bars" },
	venue_by_approver: { title: __("Venue Approvals & Rejections"), q: __("Who approved (allotted) or rejected venue requests in the date range?"), kind: "bars" },
	venue_by_requester: { title: __("Venue Requests by Requester"), q: __("Students, faculty or staff — and how their requests were decided."), kind: "bars" },
	venue_swaps: { title: __("Venue Swap Requests"), q: __("Venue swap requests in the date range, by outcome."), kind: "bars" },
};

class UniquadDashboard {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Uniquad Dashboard"), single_column: true });
		$(wrapper).find(".page-head").hide();
		uq_load_font();
		this.threshold = 75;
		this.applied = {};
		this.defaults = {};
		this.filters = {};
		this.tables = {};
		this.charts = {};
		this.nav = [];
		this.view = null; // "home" | module key
		this.dates_touched = false;
		this.home_modules = this.load_home_modules();
		this.$root = $('<div class="uq"></div>').appendTo(this.page.main);
		this.$shell = $('<div class="uq-shell"></div>').appendTo(this.$root);
		this.$sb = $('<aside class="uq-sb" aria-label="' + __("SLCM modules") + '"></aside>').appendTo(this.$shell);
		this.$main = $('<div class="uq-main"></div>').appendTo(this.$shell);
		this.$dash = $('<div class="uq-dash"></div>').appendTo(this.$main);
		this.$profile = $('<div class="uq-profile" hidden></div>').appendTo(this.$main);
		$('<div class="uq-sb-backdrop" hidden></div>').appendTo(this.$shell);
		this.modal = new UqModal(this);
		// Safety net: leaving the dashboard by any route (back button, sidebar, search) closes overlays.
		frappe.router.on("change", () => {
			if (frappe.get_route()[0] === UQ_PAGE) return;
			if (this.modal.is_open()) this.modal.close();
			this.$dash.find(".uq-gs-results").prop("hidden", true);
			if (this.$shell.hasClass("drawer-open")) this.toggle_sidebar(false);
		});
		if (uq_storage(UQ_SB_KEY) === "1") this.$shell.addClass("collapsed");
		this.render_sidebar();
		this.render_shell();
		this.bind();
		this.load_options();
		this.load_navigation();
		this.start_autorefresh();
	}

	// Frappe v16 scrolls `.main-section`, not the window — every scroll action goes through here.
	scroller() {
		return this.$root.closest(".main-section")[0] || document.scrollingElement;
	}

	lock_scroll(on) {
		$(this.scroller()).toggleClass("uq-scroll-lock", on);
	}

	scroll_to(el) {
		if (!el) return;
		const sc = this.scroller();
		const top = el.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop - 12;
		sc.scrollTo({ top: Math.max(0, top), behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
	}

	route() {
		const r = frappe.get_route();
		if (r[1] === "student" && r[2]) {
			this.modal.is_open() && this.modal.close();
			return this.show_profile(decodeURIComponent(r[2]));
		}
		this.$profile.prop("hidden", true).empty();
		this.$dash.prop("hidden", false);
		const view = r[1] === "module" && UQ_MODULE_BY_KEY[r[2]] ? r[2] : "home";
		if (view !== this.view) {
			this.view = view;
			this.render_view();
			this.scroller().scrollTop = 0;
		}
		document.title = view === "home" ? __("Uniquad Dashboard") : `${UQ_MODULE_BY_KEY[view].title} · ${__("Uniquad Dashboard")}`;
		this.mark_active();
	}

	open_module(key) {
		if (this.is_mobile()) this.toggle_sidebar(false);
		frappe.set_route(UQ_PAGE, "module", key);
	}

	open_home() {
		if (this.is_mobile()) this.toggle_sidebar(false);
		frappe.set_route(UQ_PAGE);
	}

	// ── sidebar

	render_sidebar() {
		const modules = UQ_MODULES.map(
			(m) => `<div class="uq-sb-group" data-group="${m.key}">
				<div class="uq-sb-row">
					<a href="/desk/${UQ_PAGE}/module/${m.key}" class="uq-sb-link uq-sb-module" data-module-link="${m.key}" data-tip="${uq_esc(m.title)}">
						${uq_icon(m.icon, 16)}<span class="uq-sb-text">${uq_esc(m.title)}</span><span class="uq-sb-count" data-count="${m.key}"></span></a>
					<button type="button" class="uq-sb-expand" data-expand="${m.key}" aria-expanded="false" aria-label="${uq_esc(__("Show {0} lists and tools", [m.title]))}">${uq_icon("chevron-down", 14, "uq-sb-chev")}</button>
				</div>
				<ul class="uq-sb-children" data-children="${m.key}"><li class="uq-sb-loading">${__("Loading…")}</li></ul>
			</div>`
		).join("");
		this.$sb.html(`
			<div class="uq-sb-head">
				<div class="uq-sb-brand"><span class="uq-sb-mark" aria-hidden="true">U</span>
					<span class="uq-sb-text"><strong>UNIQUAD</strong><small>SLCM</small></span></div>
				<button type="button" class="uq-sb-toggle" data-sb-toggle aria-label="${__("Collapse sidebar")}" aria-expanded="true" data-tip="${__("Expand / collapse")}">${uq_icon("panel-left", 18)}</button>
			</div>
			<div class="uq-sb-scroll">
				<a href="/desk/${UQ_PAGE}" class="uq-sb-link uq-sb-home" data-home-link data-tip="${__("Home")}">${uq_icon("dashboard", 16)}<span class="uq-sb-text">${__("Home")}</span><span class="uq-sb-count" data-count="home"></span></a>
				<div class="uq-sb-block">
					<div class="uq-sb-label uq-sb-text">${__("Modules")}</div>
					<div class="uq-sb-search uq-sb-text"><label class="uq-sr" for="uq-sb-q">${__("Find a module")}</label>
						${uq_icon("search", 13)}<input id="uq-sb-q" type="search" placeholder="${__("Find a module or list…")}"></div>
					<div class="uq-sb-modules">${modules}</div>
				</div>
				<div class="uq-sb-block">
					<button type="button" class="uq-sb-link uq-sb-customize" data-customize data-tip="${__("Customize dashboard")}">
						${uq_icon("sliders", 16)}<span class="uq-sb-text">${__("Customize Dashboard")}</span></button>
				</div>
			</div>`);
		let open = {};
		try {
			open = JSON.parse(uq_storage(UQ_SB_GROUPS_KEY) || "{}");
		} catch (e) {
			open = {};
		}
		Object.entries(open).forEach(([k, on]) => on && this.toggle_group(k, true, false));
		this.update_sb_toggle();
		this.apply_module_visibility();
	}

	// Customize Dashboard selection → sidebar. Only chosen modules are listed; a module opened directly
	// (e.g. from a bookmark) is shown while it is the current page, so the user always sees where they are.
	apply_module_visibility() {
		UQ_MODULES.forEach((m) => {
			const hide = !this.home_modules.has(m.key) && m.key !== this.view;
			this.$sb.find(`.uq-sb-group[data-group="${m.key}"]`).toggleClass("uq-sb-hidden", hide);
		});
	}

	modules_param() {
		// only send a narrowing list when the user actually hid something
		return this.home_modules.size < UQ_MODULES.length ? [...this.home_modules].join(",") : "";
	}

	load_navigation() {
		uq_call("get_navigation")
			.then((groups) => {
				this.nav = groups || [];
				this.render_nav_children();
				this.render_quicklinks();
			})
			.catch(() => this.$sb.find("[data-children]").html(`<li class="uq-sb-loading">${__("Links unavailable.")}</li>`));
	}

	render_nav_children(query = "") {
		const q = query.trim().toLowerCase();
		const by_key = Object.fromEntries(this.nav.map((g) => [g.key, g]));
		UQ_MODULES.forEach((m) => {
			const g = by_key[m.key];
			const items = g ? g.items.filter((i) => !q || (i.label + " " + m.title).toLowerCase().includes(q)) : [];
			const $group = this.$sb.find(`.uq-sb-group[data-group="${m.key}"]`);
			const title_match = !q || m.title.toLowerCase().includes(q);
			$group.toggleClass("uq-sb-nomatch", !(title_match || items.length > 0));
			this.$sb.find(`[data-children="${m.key}"]`).html(
				items.length
					? items
							.map(
								(i) => `<li><a class="uq-sb-sub" href="${uq_esc(i.route)}" ${this.preview_attrs(i)} title="${uq_esc(this.kind_label(i) + ": " + i.label)}">
								${uq_icon(this.kind_icon(i), 13)}<span>${uq_esc(i.label)}</span></a></li>`
							)
							.join("")
					: `<li class="uq-sb-loading">${g ? __("No matching lists.") : __("No lists available for your role.")}</li>`
			);
			if (q && items.length) this.toggle_group(m.key, true, false);
		});
	}

	toggle_group(key, force, persist = true) {
		const $g = this.$sb.find(`.uq-sb-group[data-group="${key}"]`);
		const on = force != null ? force : !$g.hasClass("open");
		if (on && persist) {
			// accordion: one module's lists open at a time keeps the sidebar short
			this.$sb.find(".uq-sb-group.open").not($g).removeClass("open").find("[data-expand]").attr("aria-expanded", "false");
		}
		$g.toggleClass("open", on).find("[data-expand]").attr("aria-expanded", String(on));
		if (!persist) return;
		let open = {};
		try {
			open = JSON.parse(uq_storage(UQ_SB_GROUPS_KEY) || "{}");
		} catch (e) {
			open = {};
		}
		open = on ? { [key]: true } : {};
		uq_storage(UQ_SB_GROUPS_KEY, JSON.stringify(open));
	}

	preview_attrs(i) {
		return `data-pv-kind="${uq_esc(i.type)}" data-pv-name="${uq_esc(i.name)}" data-pv-label="${uq_esc(i.label)}" data-pv-single="${i.single ? 1 : 0}"`;
	}

	// Sub-menu click → drilldown preview first; the modal's "Open …" button then navigates.
	preview_item($a) {
		const kind = $a.attr("data-pv-kind");
		const name = $a.attr("data-pv-name");
		const label = $a.attr("data-pv-label");
		const route = $a.attr("href");
		const open = { route, label: __("Open {0}", [label]) };
		if (kind === "DocType") return this.modal.open({ key: "dt:" + name, preview: name, open, title: label });
		this.modal.open({
			title: label,
			open,
			info: ($body, entry) => {
				uq_call("get_item_preview", { kind, name })
					.then((d) => {
						d = d || {};
						if (d.restricted) return $body.html(`<div class="uq-empty">${uq_icon("lock", 26)}<strong>${__("Not available for your role.")}</strong></div>`);
						const what = kind === "Page" ? __("Tool") : d.report_type || __("Report");
						$body.html(`
							<div class="uq-pv-info">
								<span class="uq-pv-info-icon" aria-hidden="true">${uq_icon(kind === "Page" ? "tool" : "chart", 26)}</span>
								<div>
									<div class="uq-pv-kind">${uq_esc(what)}${d.module ? " · " + uq_esc(d.module) : ""}</div>
									<h3>${uq_esc(d.title || label)}</h3>
									<p>${kind === "Page" ? __("An interactive SLCM tool. Open it to work with live records.") : __("A report built from SLCM records. Open it to run it with its own filters, print or export.")}</p>
									${d.ref_doctype ? `<div class="uq-pv-ref">${uq_icon("list", 14)} ${__("Built on {0} — {1} records you can access.", [uq_esc(__(d.ref_doctype)), uq_int(d.ref_total)])}
										<button type="button" class="uq-btn uq-btn-sm" data-preview-ref="${uq_esc(d.ref_doctype)}" data-route="/desk/${uq_esc(frappe.router.slug(d.ref_doctype))}">${__("Preview records")} ${uq_icon("arrow-right", 12)}</button></div>` : ""}
								</div>
							</div>`);
					})
					.catch(() => $body.html(`<div class="uq-empty">${uq_icon("alert", 24)}<strong>${__("Unable to load this item.")}</strong></div>`));
			},
		});
	}

	kind_icon(i) {
		return i.type === "DocType" ? "list" : i.type === "Page" ? "tool" : "chart";
	}

	kind_label(i) {
		return i.type === "DocType" ? __("List") : i.type === "Page" ? __("Tool") : __("Report");
	}

	mark_active() {
		this.apply_module_visibility();
		this.$sb.find(".uq-sb-link").removeClass("active").removeAttr("aria-current");
		const $a = this.view === "home" ? this.$sb.find("[data-home-link]") : this.$sb.find(`[data-module-link="${this.view}"]`);
		$a.addClass("active").attr("aria-current", "page");
	}

	is_mobile() {
		return window.matchMedia("(max-width: 900px)").matches;
	}

	toggle_sidebar(force) {
		if (this.is_mobile()) {
			const on = force != null ? force : !this.$shell.hasClass("drawer-open");
			this.$shell.toggleClass("drawer-open", on);
			this.$shell.find(".uq-sb-backdrop").prop("hidden", !on);
		} else {
			const collapsed = force != null ? !force : !this.$shell.hasClass("collapsed");
			this.$shell.toggleClass("collapsed", collapsed);
			uq_storage(UQ_SB_KEY, collapsed ? "1" : "0");
			// no manual chart redraw: frappe-charts watches its container with a ResizeObserver
		}
		this.update_sb_toggle();
	}

	update_sb_toggle() {
		const collapsed = this.$shell.hasClass("collapsed") && !this.is_mobile();
		this.$sb.find("[data-sb-toggle]").attr({ "aria-expanded": String(!collapsed), "aria-label": collapsed ? __("Expand sidebar") : __("Collapse sidebar") });
	}

	// ── home customisation (per-viewer convenience, kept in the browser)

	load_home_modules() {
		try {
			const v = JSON.parse(uq_storage(UQ_HOME_MODULES_KEY) || "null");
			if (Array.isArray(v) && v.length) return new Set(v);
		} catch (e) {
			/* ignore */
		}
		return new Set(UQ_MODULES.map((m) => m.key));
	}

	open_customize() {
		if (this.customize_dialog) {
			UQ_MODULES.forEach((m) => this.customize_dialog.set_value(m.key, this.home_modules.has(m.key) ? 1 : 0));
			return this.customize_dialog.show();
		}
		const d = (this.customize_dialog = new frappe.ui.Dialog({
			title: __("Customize Dashboard"),
			fields: [
				{ fieldtype: "HTML", fieldname: "intro", options: `<p class="uq-dialog-intro">${__("Choose the modules you work with. Unticked modules are removed from the sidebar, the home screen, analytics, Week Ahead, Action Required, Pending Operations and Recent Activity. Tick them again here at any time.")}</p>` },
				...UQ_MODULES.map((m) => ({ fieldtype: "Check", fieldname: m.key, label: m.title, default: this.home_modules.has(m.key) ? 1 : 0 })),
			],
			primary_action_label: __("Apply"),
			primary_action: (values) => {
				const keys = UQ_MODULES.map((m) => m.key).filter((k) => values[k]);
				if (!keys.length) return frappe.show_alert({ message: __("Keep at least one module."), indicator: "orange" });
				this.home_modules = new Set(keys);
				uq_storage(UQ_HOME_MODULES_KEY, JSON.stringify(keys));
				d.hide();
				if (this.view !== "home" && !this.home_modules.has(this.view)) {
					frappe.set_route(UQ_PAGE); // the page being viewed was just hidden → go home
				} else {
					this.apply_module_visibility();
					this.render_view(); // re-render the current view with the new selection
				}
				frappe.show_alert({ message: __("Dashboard updated — showing {0} of {1} modules.", [keys.length, UQ_MODULES.length]), indicator: "green" }, 3);
			},
			secondary_action_label: __("Reset"),
			secondary_action: () => UQ_MODULES.forEach((m) => d.set_value(m.key, 1)),
		}));
		d.$wrapper.addClass("uq-dialog");
		d.show();
	}

	// ── shell (header + filters + context stay; the view below changes)

	render_shell() {
		this.$dash.html(`
			<header class="uq-header">
				<div class="uq-brand">
					<button type="button" class="uq-btn uq-menu-btn" data-sb-toggle aria-label="${__("Open module menu")}">${uq_icon("menu", 18)}</button>
					<div>
						<nav class="uq-crumbs" aria-label="${__("Breadcrumb")}"></nav>
						<h1 class="uq-title"></h1>
						<p class="uq-subtitle"></p>
					</div>
				</div>
				<div class="uq-header-tools">
					<div class="uq-gsearch" role="search">
						${uq_icon("search", 15)}
						<label class="uq-sr" for="uq-gs-input">${__("Search SLCM")}</label>
						<input id="uq-gs-input" type="search" autocomplete="off" placeholder="${__("Search students, applicants, courses…")}" aria-controls="uq-gs-results" aria-expanded="false">
						<kbd aria-hidden="true">/</kbd>
						<div class="uq-gs-results" id="uq-gs-results" role="listbox" hidden></div>
					</div>
					<label class="uq-autorefresh">${uq_icon("history", 14)} ${__("Auto refresh")}
						<select data-autorefresh aria-label="${__("Auto refresh interval")}">
							<option value="0">${__("Off")}</option>
							<option value="5">${__("Every 5 min")}</option>
							<option value="15">${__("Every 15 min")}</option>
							<option value="30">${__("Every 30 min")}</option>
						</select>
					</label>
					<button type="button" class="uq-btn uq-btn-sm" data-refresh>${uq_icon("refresh", 14)} ${__("Refresh")}</button>
				</div>
			</header>

			<section class="uq-filters collapsed" aria-label="${__("Dashboard filters")}">
				<div class="uq-fbar">
					<span class="uq-fbar-icon" aria-hidden="true">${uq_icon("filter", 15)}</span>
					<div class="uq-context" aria-live="polite"></div>
					<button type="button" class="uq-btn uq-btn-sm" data-edit-filters aria-expanded="false">${uq_icon("sliders", 13)} <span>${__("Edit filters")}</span></button>
				</div>
				<div class="uq-fbody">
				<div class="uq-filter-grid uq-filter-primary"></div>
				<div class="uq-filter-more" hidden>
					<div class="uq-filters-hint">${__("Pick any combination — options narrow to match your other selections, and every list is searchable.")}</div>
					<div class="uq-filter-grid uq-filter-advanced"></div>
				</div>
				<div class="uq-filter-actions">
					<button type="button" class="uq-btn uq-btn-ghost" data-more aria-expanded="false">${uq_icon("sliders", 14)} <span>${__("More filters")}</span><span class="uq-more-count"></span></button>
					<span class="uq-pending-note" role="status">${uq_icon("info", 13)} ${__("You have unapplied changes")}</span>
					<div class="uq-filter-buttons">
						<button type="button" class="uq-btn uq-btn-ghost" data-current-term title="${__("Current academic year, term and term dates")}">${uq_icon("calendar", 14)} ${__("Current term")}</button>
						<button type="button" class="uq-btn" data-reset title="${__("Remove all filters")}">${uq_icon("x", 14)} ${__("Clear filters")}</button>
						<button type="button" class="uq-btn uq-btn-primary" data-apply><span class="uq-dot" aria-hidden="true"></span>${__("Apply Filters")}</button>
					</div>
				</div>
				</div>
			</section>

			<div class="uq-banner-slot"></div>
			<div class="uq-view"></div>
			<div class="uq-access-note"></div>
		`);
		const $p = this.$dash.find(".uq-filter-primary");
		const $a = this.$dash.find(".uq-filter-advanced");
		UQ_FILTERS.forEach((def) => {
			const ms = new UqMultiSelect(def.primary ? $p : $a, def, (key) => this.on_filter_change(key));
			ms.$el.data("ms", ms);
			this.filters[def.key] = ms;
		});
		$p.append(`
			<div class="uq-field uq-field-dates">
				<span class="uq-field-label" id="uq-dates-label">${__("Date Range")}</span>
				<div class="uq-daterange" role="group" aria-labelledby="uq-dates-label">
					<input type="date" data-date="from_date" aria-label="${__("From date")}">
					<span class="uq-date-sep" aria-hidden="true">–</span>
					<input type="date" data-date="to_date" aria-label="${__("To date")}">
				</div>
			</div>`);
		this.$dash.find("[data-autorefresh]").val(uq_storage(UQ_REFRESH_KEY) || "0");
	}

	section(id, icon, title, desc, body) {
		return `<section class="uq-section" id="${id}" aria-labelledby="${id}-h">
			<div class="uq-section-head"><span class="uq-section-icon" aria-hidden="true">${uq_icon(icon, 18)}</span>
				<div><h2 class="uq-section-title" id="${id}-h">${uq_esc(title)}</h2>${desc ? `<p class="uq-section-desc">${uq_esc(desc)}</p>` : ""}</div></div>
			${body}</section>`;
	}

	panel(id, title, q, body = "", tools = "") {
		return `
			<div class="uq-panel" data-panel="${id}">
				<div class="uq-panel-head"><div><h3 class="uq-panel-title">${uq_esc(title)}</h3><p class="uq-panel-q">${uq_esc(q)}</p></div>
				<div class="uq-panel-tools">${tools}</div></div>
				<div class="uq-panel-body">${body}</div>
			</div>`;
	}

	table_panel(key) {
		const t = UQ_TABLES[key];
		const modes = t.modes
			? `<div class="uq-seg" role="group" aria-label="${__("Exception type")}">
				<button type="button" data-mode="unmarked" aria-pressed="true">${__("Not marked")}</button>
				<button type="button" data-mode="low" aria-pressed="false">${__("Low attendance")}</button></div>`
			: "";
		const tools = `${modes}
			<button type="button" class="uq-btn uq-btn-sm" data-table-export="${key}">${uq_icon("download", 13)} ${__("Export CSV")}</button>
			<button type="button" class="uq-btn uq-btn-sm uq-btn-ghost" data-table-expand="${key}">${uq_icon("maximize", 13)} ${__("Expand")}</button>`;
		return this.panel(`t_${key}`, t.title, t.q, `<div data-table="${key}"></div>`, tools);
	}

	chart_panel(id) {
		const c = UQ_CHART_PANELS[id];
		if (c.kind === "chart") {
			const tools = `<button type="button" class="uq-btn uq-btn-sm uq-btn-ghost" data-chart-table="${id}" aria-pressed="false">${uq_icon("table", 13)} ${__("Data")}</button>`;
			return this.panel(id, c.title, c.q, `<div class="uq-chart" data-chart="${id}"></div>`, tools);
		}
		return this.panel(id, c.title, c.q, `<div data-bars="${id}"></div>`);
	}

	skel_cards(n, cls) {
		const card = `<div class="uq-card" aria-hidden="true"><div class="uq-skel" style="height:14px;width:40%"></div>
			<div class="uq-skel" style="height:28px;width:55%;margin-top:16px"></div><div class="uq-skel" style="height:12px;width:70%;margin-top:10px"></div></div>`;
		return `<div class="uq-grid ${cls}" aria-busy="true">${card.repeat(n)}</div>`;
	}

	// Build the current view's skeleton (header text, sections, chart & table panels), then fill it.
	render_view() {
		Object.values(this.charts).forEach((ch) => {
			try {
				ch.destroy && ch.destroy();
			} catch (e) {
				/* detached */
			}
		});
		this.charts = {};
		this.tables = {};
		const $v = this.$dash.find(".uq-view");
		const $crumbs = this.$dash.find(".uq-crumbs");
		if (this.view === "home") {
			$crumbs.empty().hide();
			this.$dash.find(".uq-title").text(__("Uniquad Dashboard"));
			this.$dash.find(".uq-subtitle").text(__("SLCM Operations Overview — choose a module to see its details"));
			$v.html(
				this.section("uq-home-overview", "pulse", __("Overview"), __("The headline numbers across SLCM for the selected scope. Open any figure to see the records behind it."), `<div data-home-kpis>${this.skel_cards(UQ_HOME_KPIS.length, "uq-grid-home-kpi")}</div>`) +
					this.section(
						"uq-home-analytics",
						"chart",
						__("Analytics"),
						__("Where things stand and how they are trending. Select a bar to drill into its records."),
						`<div class="uq-grid uq-grid-2">
							${this.panel("home_attention", __("Attention by Module"), __("Which modules have the most open action items? Select one to see what needs attention."), '<div data-home-attention></div>')}
							${this.panel("home_fees", __("Fee Position"), __("Collected and outstanding dues, plus payments and refunds in the date range. Select a bar for the records."), '<div data-home-fees></div>')}
							${this.chart_panel("attendance_trend")}
							${this.chart_panel("students_by_status")}
							${this.chart_panel("students_by_programme")}
							${this.chart_panel("course_attendance")}
							${this.chart_panel("application_stages")}
							${this.chart_panel("students_by_stage")}
						</div>`
					) +
					this.section(
						"uq-home-helpdesk",
						"inbox",
						__("Helpdesk Tickets"),
						__("Open tickets and who is raising them. Open-ticket charts ignore the filters; the rest follow the date range."),
						`<div class="uq-grid uq-grid-2">
							${this.chart_panel("tickets_open_status")}
							${this.chart_panel("tickets_raised_kind")}
							${this.chart_panel("tickets_top_raisers")}
							${this.chart_panel("tickets_open_team")}
							${this.chart_panel("tickets_by_type")}
						</div>`
					) +
					this.section(
						"uq-home-venue",
						"building",
						__("Venue Bookings"),
						__("How venue requests in the date range were decided, and by whom."),
						`<div class="uq-grid uq-grid-2">
							${this.chart_panel("venue_by_status")}
							${this.chart_panel("venue_by_approver")}
							${this.chart_panel("venue_by_requester")}
							${this.chart_panel("venue_swaps")}
						</div>`
					) +
					this.section("uq-home-action", "alert", __("Action Required"), __("Open items across all modules, most urgent first."), `<div data-home-alerts>${this.skel_cards(4, "uq-grid-alert")}</div><div class="uq-stack">${this.table_panel("pending_operations")}</div>`) +
					this.section("uq-home-activity", "pulse", __("Recent Activity"), __("The latest changes across SLCM modules you can access."), this.table_panel("recent_activity")) +
					this.section("uq-home-alltime", "history", __("All-Time Statistics"), __("Since inception. These ignore the filters above, but still count only records you can access."), `<div data-alltime>${this.skel_cards(4, "uq-grid-alltime")}</div>`)
			);
		} else {
			const m = UQ_MODULE_BY_KEY[this.view];
			$crumbs.html(`<a href="/desk/${UQ_PAGE}" data-home-link>${__("Uniquad Dashboard")}</a> ${uq_icon("chevron-right", 11)} <span aria-current="page">${uq_esc(m.title)}</span>`).show();
			this.$dash.find(".uq-title").html(`<span class="uq-title-icon" aria-hidden="true">${uq_icon(m.icon, 20)}</span>${uq_esc(m.title)}`);
			this.$dash.find(".uq-subtitle").text(m.desc);
			const charts = m.charts.map((c) => this.chart_panel(c));
			const charts_html = charts.length ? `<div class="uq-grid ${charts.length > 1 ? "uq-grid-2" : ""}">${charts.join("")}</div>` : "";
			$v.html(
				this.section("uq-mod-summary", m.icon, __("Summary"), __("Key figures for {0} in the selected scope.", [m.title]), `<div data-mod-cards>${this.skel_cards(4, "uq-grid-kpi")}</div>`) +
					this.section("uq-mod-attention", "alert", __("Needs Attention"), __("Items in {0} that someone needs to act on.", [m.title]), `<div data-mod-alerts>${this.skel_cards(2, "uq-grid-alert")}</div>`) +
					(charts_html || m.tables.length
						? this.section("uq-mod-detail", "table", __("Details"), __("Trends and the records behind the numbers."), `<div class="uq-stack">${charts_html}${m.tables.map((t) => this.table_panel(t)).join("")}</div>`)
						: "") +
					this.section("uq-mod-links", "external", __("Open in Desk"), __("Lists, tools and reports for {0} that your role can open.", [m.title]), `<div class="uq-quicklinks" data-quicklinks></div>`)
			);
			this.render_quicklinks();
		}
		if (this.data) this.render_data();
		if (this.options) this.init_tables();
	}

	// Attention by Module → drilldown first: the module's checks, each opening its records.
	open_attention(key) {
		const m = UQ_MODULE_BY_KEY[key];
		if (!m || !this.data) return;
		const alerts = (this.cards_by_module()[key] || []).filter((c) => c.alert).sort((a, b) => flt(b.value) - flt(a.value));
		const hot = alerts.filter((c) => flt(c.value) > 0);
		this.modal.open({
			title: __("{0} — Needs Attention", [m.title]),
			description: m.desc,
			open: { route: `/desk/${UQ_PAGE}/module/${key}`, label: __("Open {0}", [m.title]) },
			info: ($body) => {
				const rows = alerts
					.map((c) => {
						const n = flt(c.value);
						return `<li class="uq-attn-row ${n > 0 ? "hot" : "clear"}">
							<span class="uq-attn-v">${c.error ? "—" : uq_esc(uq_format(c.value, c.fmt))}</span>
							<span class="uq-attn-body"><b>${uq_esc(c.title)}</b><small>${uq_esc(c.sub || c.description || "")}</small></span>
							<span class="uq-state ${n > 0 ? "attention" : "clear"}">${uq_icon(n > 0 ? "alert" : "check", 11)} ${n > 0 ? __("Needs attention") : __("All clear")}</span>
							${c.drill && n > 0 ? `<button type="button" class="uq-btn uq-btn-sm" data-modal-drill="${uq_esc(c.drill)}" data-modal-subtitle="">${__("View records")} ${uq_icon("arrow-right", 12)}</button>` : `<span></span>`}
						</li>`;
					})
					.join("");
				$body.html(`
					<div class="uq-attn-sum ${hot.length ? "" : "clear"}">
						<span class="uq-attn-sum-icon" aria-hidden="true">${uq_icon(hot.length ? "alert" : "check", 20)}</span>
						<div><b>${hot.length ? __("{0} of {1} checks need attention in {2}", [hot.length, alerts.length, uq_esc(m.title)]) : __("Everything in {0} is clear", [uq_esc(m.title)])}</b>
						<small>${__("Open a check to see the records behind it, or view every open item for this module.")}</small></div>
						${hot.length && PENDING_MODULES.includes(key) ? `<button type="button" class="uq-btn uq-btn-sm uq-btn-primary" data-modal-drill="pending_operations" data-modal-params='${JSON.stringify({ module: key })}' data-modal-subtitle="${uq_esc(m.title)}">${uq_icon("list-todo", 13)} ${__("View all open items")}</button>` : ""}
					</div>
					${alerts.length ? `<ul class="uq-attn-list">${rows}</ul>` : `<div class="uq-empty">${__("This module has no attention checks.")}</div>`}`);
			},
		});
	}


	// ── global search (permission-scoped on the server)

	bind_search() {
		const $wrap = this.$dash.find(".uq-gsearch");
		const $in = $wrap.find("input");
		const $res = $wrap.find(".uq-gs-results");
		let active = -1;
		const close = () => {
			$res.prop("hidden", true);
			$in.attr("aria-expanded", "false");
			active = -1;
		};
		const run = uq_debounce(() => {
			const q = $in.val().trim();
			if (q.length < 2) return close();
			const id = (this.search_req = (this.search_req || 0) + 1);
			$res.prop("hidden", false).html(`<div class="uq-gs-empty">${uq_icon("loader", 14, "uq-spin")} ${__("Searching…")}</div>`);
			$in.attr("aria-expanded", "true");
			uq_call("global_search", { q })
				.then((rows) => {
					if (id !== this.search_req) return;
					rows = rows || [];
					if (!rows.length) return $res.html(`<div class="uq-gs-empty">${__("No matches for “{0}”.", [uq_esc(q)])}</div>`);
					const groups = {};
					rows.forEach((r) => (groups[r.doctype_label] = groups[r.doctype_label] || []).push(r));
					$res.html(
						Object.entries(groups)
							.map(
								([g, list]) => `<div class="uq-gs-group">${uq_esc(g)}</div>` +
									list
										.map(
											(r) => `<a role="option" class="uq-gs-item" href="${uq_esc(r.kind === "student" ? `/desk/${UQ_PAGE}/student/${encodeURIComponent(r.name)}` : frappe.utils.get_form_link(r.doctype, r.name))}" ${r.kind === "student" ? `data-gs-student="${uq_esc(r.name)}"` : ""}>
												<b>${uq_esc(r.label)}</b><small>${uq_esc(r.name)}${r.sub ? " · " + uq_esc(r.sub) : ""}</small></a>`
										)
										.join("")
							)
							.join("")
					);
				})
				.catch(() => $res.html(`<div class="uq-gs-empty">${__("Search is unavailable right now.")}</div>`));
		}, 250);
		$in.on("input", run);
		$in.on("keydown", (e) => {
			const items = $res.find(".uq-gs-item");
			if (e.key === "ArrowDown" || e.key === "ArrowUp") {
				e.preventDefault();
				active = Math.max(0, Math.min(items.length - 1, active + (e.key === "ArrowDown" ? 1 : -1)));
				items.removeClass("focus").eq(active).addClass("focus")[0]?.scrollIntoView({ block: "nearest" });
			} else if (e.key === "Enter" && active >= 0) {
				e.preventDefault();
				items.eq(active)[0].click();
			} else if (e.key === "Escape") {
				close();
			}
		});
		$res.on("click", "[data-gs-student]", (e) => {
			e.preventDefault();
			close();
			this.open_student($(e.currentTarget).attr("data-gs-student"));
		});
		$res.on("click", ".uq-gs-item:not([data-gs-student])", () => close());
		$(document).on("click.uqgs", (e) => {
			if (!$(e.target).closest(".uq-gsearch").length) close();
		});
		$(document).on("keydown.uqgs", (e) => {
			if (e.key === "/" && !$(e.target).is("input, textarea, select, [contenteditable]") && frappe.get_route()[0] === UQ_PAGE) {
				e.preventDefault();
				$in.trigger("focus");
			}
		});
	}

	render_quicklinks() {
		const $q = this.$dash.find("[data-quicklinks]");
		if (!$q.length) return;
		const g = this.nav.find((x) => x.key === this.view);
		if (!this.nav.length) return $q.html(`<div class="uq-sb-loading">${__("Loading…")}</div>`);
		$q.html(
			g && g.items.length
				? ["DocType", "Page", "Report"]
						.map((type) => {
							const items = g.items.filter((i) => i.type === type);
							if (!items.length) return "";
							const head = { DocType: __("Lists"), Page: __("Tools"), Report: __("Reports") }[type];
							return `<div class="uq-ql-group"><div class="uq-ql-head">${uq_icon(this.kind_icon(items[0]), 14)} ${head}</div>
								<div class="uq-ql-items">${items.map((i) => `<a class="uq-quicklink" href="${uq_esc(i.route)}" ${this.preview_attrs(i)}>${uq_esc(i.label)} ${uq_icon("arrow-right", 11)}</a>`).join("")}</div></div>`;
						})
						.join("")
				: `<div class="uq-empty" style="padding:12px">${__("No lists are available for your role in this module.")}</div>`
		);
	}

	bind() {
		const $d = this.$dash;
		this.$root.on("click", "[data-sb-toggle]", () => this.toggle_sidebar());
		this.$root.on("click", ".uq-sb-backdrop", () => this.toggle_sidebar(false));
		this.$root.on("click", "[data-home-link]", (e) => {
			e.preventDefault();
			this.open_home();
		});
		this.$root.on("click", "[data-module-link]", (e) => {
			e.preventDefault();
			this.open_module($(e.currentTarget).attr("data-module-link"));
		});
		this.$sb.on("click", "[data-expand]", (e) => {
			const key = $(e.currentTarget).attr("data-expand");
			if (this.$shell.hasClass("collapsed") && !this.is_mobile()) this.toggle_sidebar(true);
			this.toggle_group(key);
		});
		// NB: never return `false` from a jQuery handler here — it cancels the link and Frappe never routes.
		// Sidebar sub-links and "Open in Desk" links preview first (Ctrl/Cmd-click still opens directly).
		this.$root.on("click", ".uq-sb-sub[data-pv-kind], .uq-quicklink[data-pv-kind]", (e) => {
			const $a = $(e.currentTarget);
			if (e.ctrlKey || e.metaKey || e.shiftKey || $a.attr("data-pv-single") === "1") return;
			e.preventDefault();
			e.stopPropagation(); // keep Frappe's router from navigating straight away
			if (this.is_mobile()) this.toggle_sidebar(false);
			this.preview_item($a);
		});
		this.$sb.on("click", "[data-customize]", () => this.open_customize());
		this.$sb.on("input", "#uq-sb-q", uq_debounce((e) => this.render_nav_children(e.target.value), 150));
		$(document).on("keydown.uq", (e) => {
			if (e.key === "Escape" && this.$shell.hasClass("drawer-open")) this.toggle_sidebar(false);
		});

		$d.on("click", "[data-edit-filters]", () => this.toggle_filters());
		$d.on("click", "[data-attention-module]", (e) => this.open_attention($(e.currentTarget).attr("data-attention-module")));
		this.bind_search();
		$d.on("click", "[data-apply]", () => this.apply());
		$d.on("click", "[data-reset]", () => this.reset());
		$d.on("click", "[data-current-term]", () => this.use_current_term());
		$d.on("click", "[data-refresh]", () => this.load_dashboard(true));
		$d.on("click", "[data-more]", (e) => {
			const $m = $d.find(".uq-filter-more");
			const open = $m.prop("hidden");
			$m.prop("hidden", !open);
			$(e.currentTarget).attr("aria-expanded", String(open)).find("span").first().text(open ? __("Fewer filters") : __("More filters"));
		});
		$d.on("change", "[data-date]", () => {
			this.dates_touched = true;
			this.mark_dirty();
		});
		$d.on("change", "[data-autorefresh]", (e) => {
			uq_storage(UQ_REFRESH_KEY, e.target.value);
			this.last_load = Date.now();
			this.update_timestamp();
		});
		$d.on("click", "[data-drill]", (e) => {
			e.stopPropagation();
			this.modal.open({ key: $(e.currentTarget).attr("data-drill") });
		});
		$d.on("click", ".uq-card.clickable", (e) => {
			if ($(e.target).closest("button, a").length) return;
			$(e.currentTarget).find("[data-drill]").first().trigger("click");
		});
		$d.on("keydown", ".uq-mod-stat.is-link", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				$(e.currentTarget).trigger("click");
			}
		});
		$d.on("click", "[data-jump]", (e) => {
			e.preventDefault();
			const go = () => this.scroll_to(document.getElementById("uq-home-action"));
			if (this.view === "home") go();
			else Promise.resolve(frappe.set_route(UQ_PAGE)).then(() => setTimeout(go, 80));
		});
		$d.on("click", "[data-bar-drill]", (e) => {
			const $b = $(e.currentTarget);
			const value = $b.attr("data-bar-value");
			const param = $b.attr("data-bar-param");
			// a param bar narrows the drilldown itself; a filter bar adds a dashboard filter
			if (param) return this.modal.open({ key: $b.attr("data-bar-drill"), filters: this.applied, params: { [param]: value }, subtitle: $b.attr("data-bar-label") });
			const filters = { ...this.applied, [$b.attr("data-bar-filter")]: [value] };
			this.modal.open({ key: $b.attr("data-bar-drill"), filters, subtitle: $b.attr("data-bar-label") });
		});
		$d.on("click", "[data-table-export]", (e) => this.tables[$(e.currentTarget).attr("data-table-export")]?.export_csv());
		$d.on("click", "[data-table-expand]", (e) => {
			const key = $(e.currentTarget).attr("data-table-expand");
			const t = this.tables[key];
			this.modal.open({ key, params: t ? t.params : {} });
		});
		$d.on("click", "[data-mode]", (e) => {
			const mode = $(e.currentTarget).attr("data-mode");
			$(e.currentTarget).siblings().attr("aria-pressed", "false");
			$(e.currentTarget).attr("aria-pressed", "true");
			const t = this.tables.attendance_exceptions;
			if (t) {
				t.params = { mode };
				t.page = 1;
				t.load();
			}
		});
		$d.on("click", "[data-chart-table]", (e) => {
			const $b = $(e.currentTarget);
			const on = $b.attr("aria-pressed") !== "true";
			$b.attr("aria-pressed", on ? "true" : "false");
			const $p = $d.find(`[data-panel="${$b.attr("data-chart-table")}"] .uq-panel-body`);
			$p.find(".uq-chart").toggle(!on);
			$p.find(".uq-chart-data").toggle(on);
			if (!on) this.render_charts();
		});
		$(document).on("click.uq", (e) => {
			if (!$(e.target).closest(".uq-ms").length) $(".uq-ms.open").each((_, el) => $(el).data("ms")?.close());
		});
		$(window).on(
			"resize.uq",
			uq_debounce(() => {
				if (!this.is_mobile()) this.$shell.removeClass("drawer-open").find(".uq-sb-backdrop").prop("hidden", true);
				this.update_sb_toggle();
			}, 150)
		);
	}

	// ── data

	load_dashboard(manual = false) {
		const id = (this.dash_req = (this.dash_req || 0) + 1);
		const $btn = this.$dash.find("[data-refresh]");
		$btn.prop("disabled", true).find(".uq-icon").addClass("uq-spin");
		if (this.data) this.$dash.find(".uq-view").addClass("is-loading");
		return uq_call("get_dashboard", { filters: JSON.stringify(this.applied) })
			.then((msg) => {
				if (id !== this.dash_req) return;
				this.data = msg;
				this.threshold = flt(this.data.threshold) || 75;
				this.last_load = Date.now();
				this.$dash.find(".uq-banner-slot").empty();
				this.render_data();
				if (manual) this.reload_tables();
			})
			.catch(() => id === this.dash_req && this.show_error())
			.finally(() => {
				if (id !== this.dash_req) return;
				$btn.prop("disabled", false).find(".uq-icon").removeClass("uq-spin");
				this.$dash.find(".uq-view").removeClass("is-loading");
			});
	}

	show_error() {
		this.$dash.find(".uq-banner-slot").html(`
			<div class="uq-banner" role="alert">
				<span>${uq_icon("alert", 16)} <strong>${__("Unable to load dashboard data.")}</strong> ${__("Please try again.")}</span>
				<button type="button" class="uq-btn uq-btn-sm" data-refresh>${uq_icon("refresh", 13)} ${__("Retry")}</button>
			</div>`);
		if (!this.data) this.$dash.find(".uq-view .uq-grid[aria-busy]").replaceWith(`<div class="uq-empty">${uq_icon("alert", 24)}<strong>${__("Data unavailable")}</strong></div>`);
	}

	cards_by_module() {
		const by = {};
		(this.data.cards || []).forEach((c) => {
			if (!c.restricted) (by[c.section] = by[c.section] || []).push(c);
		});
		return by;
	}

	attention_of(cards) {
		return (cards || []).filter((c) => c.alert && flt(c.value) > 0);
	}

	render_data() {
		this.$dash.find(".uq-banner-slot").empty(); // banners belong to the view that produced them
		const by = this.cards_by_module();
		// sidebar + context counts (every module, regardless of the current view)
		let total = 0;
		UQ_MODULES.forEach((m) => {
			const n = this.attention_of(by[m.key]).length;
			if (this.home_modules.has(m.key)) total += n;
			this.$sb.find(`[data-count="${m.key}"]`).text(n || "").attr("aria-label", n ? __("{0} need attention", [n]) : null);
			// a module the user cannot read at all is dimmed in the sidebar, not hidden
			this.$sb.find(`[data-module-link="${m.key}"]`).toggleClass("uq-sb-dim", !(by[m.key] || []).length);
		});
		this.attention_count = total;
		this.$sb.find('[data-count="home"]').text(total || "");
		this.render_context();

		if (this.view === "home") this.render_home(by);
		else this.render_module(by[this.view] || []);
		this.render_charts();
		if (this.view === "home") {
			Object.entries(UQ_PANEL_MODULE).forEach(([panel, mod]) => !this.home_modules.has(mod) && this.$dash.find(`#uq-home-analytics [data-panel="${panel}"]`).hide());
		}

		const hidden = new Set((this.data.cards || []).filter((c) => c.restricted && (this.view === "home" ? c.all_time || c.alert : c.section === this.view)).map((c) => c.doctype));
		const $note = this.$dash.find(".uq-access-note").empty();
		if (hidden.size) {
			$note.html(`<div class="uq-note">${uq_icon("lock", 14)}<span>${__("Some metrics are hidden because your role cannot access")}: ${[...hidden].map((d) => uq_esc(__(d))).join(", ")}.</span></div>`);
		}
		this.update_timestamp();
	}

	render_home(by) {
		const mods = UQ_MODULES.filter((m) => this.home_modules.has(m.key) && (by[m.key] || []).length);
		// Overview: headline figures across modules (only those the user can read)
		const all_cards = Object.values(by).flat();
		const kpis = UQ_HOME_KPIS.map((k) => all_cards.find((c) => c.key === k)).filter((c) => c && this.home_modules.has(c.section));
		this.$dash.find("[data-home-kpis]").html(kpis.length ? `<div class="uq-grid uq-grid-home-kpi">${kpis.map((c, i) => this.kpi_card(c, i, true)).join("")}</div>` : "");
		this.$dash.find("#uq-home-overview").toggle(kpis.length > 0);
		// Analytics: attention per module (bars open the module)
		const att = mods.map((m) => ({ m, n: this.attention_of(by[m.key]).length })).sort((a, b) => b.n - a.n);
		const max = Math.max(1, ...att.map((a) => a.n));
		this.$dash.find("[data-home-attention]").html(
			att.length
				? `<ul class="uq-bars">${att
						.map(
							({ m, n }) => `<li><button type="button" class="uq-bar" data-attention-module="${m.key}" aria-label="${uq_esc(m.title + ": " + n + " " + __("need attention") + ". " + __("View details"))}">
								<span class="uq-bar-label">${uq_esc(m.title)}</span>
								<span class="uq-bar-track" aria-hidden="true"><span class="uq-bar-fill" style="width:${n ? Math.max(4, (100 * n) / max) : 0}%;display:block"></span></span>
								<span class="uq-bar-value">${n ? uq_int(n) : `<small>${__("clear")}</small>`}</span></button></li>`
						)
						.join("")}</ul>`
				: ""
		);
		this.$dash.find('[data-panel="home_attention"]').toggle(att.length > 0);
		// Analytics: fee position from the fee cards
		const fc = (k) => all_cards.find((c) => c.key === k);
		const fees = [
			[fc("fee_collected"), __("Collected")],
			[fc("fee_outstanding"), __("Outstanding")],
			[fc("fee_payments"), __("Received in date range")],
			[fc("fee_refunds"), __("Refunded in date range")],
		].filter(([c]) => c);
		const fmax = Math.max(1, ...fees.map(([c]) => flt(c.value)));
		this.$dash.find("[data-home-fees]").html(
			`<ul class="uq-bars">${fees
				.map(
					([c, label]) => `<li><button type="button" class="uq-bar" data-drill="${uq_esc(c.drill)}" aria-label="${uq_esc(label + ": " + uq_money(c.value) + ". " + __("View records"))}">
						<span class="uq-bar-label">${uq_esc(label)}</span>
						<span class="uq-bar-track" aria-hidden="true"><span class="uq-bar-fill" style="width:${flt(c.value) ? Math.max(2, (100 * flt(c.value)) / fmax) : 0}%;display:block"></span></span>
						<span class="uq-bar-value">${uq_esc(uq_money(c.value))}</span></button></li>`
				)
				.join("")}</ul>`
		);
		this.$dash.find('[data-panel="home_fees"]').toggle(fees.length > 0 && this.home_modules.has("fees"));
		// analytics panels follow the module they describe
		Object.entries(UQ_PANEL_MODULE).forEach(([panel, mod]) => {
			const $p = this.$dash.find(`#uq-home-analytics [data-panel="${panel}"]`);
			if (!this.home_modules.has(mod)) $p.hide();
		});
		const $an = this.$dash.find("#uq-home-analytics");
		$an.toggle($an.find(".uq-panel").filter((_, el) => $(el).css("display") !== "none").length > 0);
		// Action Required: items needing attention as cards; the all-clear ones summarised in one line.
		const alerts = mods.flatMap((m) => (by[m.key] || []).filter((c) => c.alert).map((c) => ({ ...c, module: m })));
		const hot = alerts.filter((c) => flt(c.value) > 0);
		const clear = alerts.filter((c) => !(flt(c.value) > 0) && !c.error);
		this.$dash.find("[data-home-alerts]").html(
			(hot.length
				? `<div class="uq-grid uq-grid-alert">${hot.map((c) => this.alert_card(c, c.module.title)).join("")}</div>`
				: `<div class="uq-note uq-note-good">${uq_icon("check", 16)}<strong>${__("Nothing needs attention right now.")}</strong></div>`) +
				(clear.length ? `<div class="uq-allclear">${uq_icon("check", 13)} <b>${__("All clear")}:</b> ${clear.map((c) => `<span>${uq_esc(c.title)}</span>`).join("")}</div>` : "")
		);
		const all = (this.data.cards || []).filter((c) => c.section === "all_time" && !c.restricted);
		this.$dash.find("[data-alltime]").html(
			all.length ? `<div class="uq-alltime-wrap"><div class="uq-alltime-head">${uq_icon("history", 14)} ${__("All-Time · not affected by filters")}</div><div class="uq-grid uq-grid-alltime">${all.map((c) => this.alltime_card(c)).join("")}</div></div>` : ""
		);
		this.$dash.find("#uq-home-alltime").toggle(all.length > 0);
	}

	render_module(cards) {
		const metrics = cards.filter((c) => !c.alert);
		const alerts = cards.filter((c) => c.alert).sort((a, b) => (flt(b.value) > 0) - (flt(a.value) > 0));
		const hero = metrics.filter((c) => c.headline);
		const rest = metrics.filter((c) => !c.headline);
		if (!cards.length) {
			this.$dash.find("[data-mod-cards]").html(`<div class="uq-empty">${uq_icon("lock", 26)}<strong>${__("This module is not available for your role.")}</strong>${__("Ask your administrator if you need access.")}</div>`);
			this.$dash.find("#uq-mod-attention, #uq-mod-detail").hide();
			return;
		}
		// one even grid; headline figures lead and carry the brand colour
		this.$dash.find("[data-mod-cards]").html(`<div class="uq-grid uq-grid-summary">${[...hero, ...rest].map((c, i) => this.kpi_card(c, i, c.headline)).join("")}</div>`);
		this.$dash.find("[data-mod-alerts]").html(
			alerts.length
				? `<div class="uq-grid uq-grid-alert">${alerts.map((c) => this.alert_card(c)).join("")}</div>`
				: `<div class="uq-note uq-note-good">${uq_icon("check", 16)}<strong>${__("No open action items in this module.")}</strong></div>`
		);
		const numeric = metrics.filter((c) => c.fmt !== "text");
		if (numeric.length && numeric.every((c) => !flt(c.value)) && !this.attention_of(cards).length) {
			this.$dash.find(".uq-banner-slot").html(`
				<div class="uq-note" role="status">${uq_icon("info", 16)}<div><strong>${__("No data available for the selected filters.")}</strong>
				${__("Try changing your filters.")} <button type="button" class="uq-link" data-reset>${__("Clear filters")}</button></div></div>`);
		}
	}

	// ── running tables (per view)

	init_tables() {
		const keys = this.view === "home" ? ["pending_operations", "recent_activity"] : UQ_MODULE_BY_KEY[this.view].tables;
		keys.forEach((key) => {
			const def = UQ_TABLES[key];
			const $m = this.$dash.find(`[data-table="${key}"]`);
			if (!$m.length) return;
			const params = { ...(def.params || {}) };
			if ((key === "pending_operations" || key === "recent_activity") && this.modules_param()) params.modules = this.modules_param();
			this.tables[key] = new UqTable(this, $m, {
				key,
				params,
				page_size: def.page_size || 10,
				empty: def.empty,
				on_meta: (d) => {
					const $panel = $m.closest(".uq-panel");
					$panel.toggle(!d.restricted);
					$panel.find("[data-table-export]").prop("disabled", !d.total);
				},
			});
			this.tables[key].load();
		});
	}

	reload_tables() {
		Object.values(this.tables).forEach((t) => {
			t.page = 1;
			t.load();
		});
	}

	// ── filters

	load_options() {
		uq_call("get_filter_options")
			.then((o) => {
				o = o || {};
				this.options = o;
				UQ_FILTERS.forEach((def) => this.filters[def.key].set_options(o[def.key] || []));
				this.defaults = o.defaults || {};
				this.set_draft(this.defaults);
				this.cascade();
				this.applied = this.get_draft();
				this.mark_dirty();
				this.render_context();
				// the first route() may have run before options arrived; it builds the view and its tables
				if (!this.view) this.route();
				else this.init_tables();
				this.load_dashboard();
			})
			.catch(() => this.show_error());
	}

	set_draft(values) {
		UQ_FILTERS.forEach((def) => this.filters[def.key].set_value(values[def.key] || []));
		this.$dash.find('[data-date="from_date"]').val(values.from_date || "");
		this.$dash.find('[data-date="to_date"]').val(values.to_date || "");
		this.dates_touched = false;
	}

	get_draft() {
		const out = {};
		UQ_FILTERS.forEach((def) => {
			const v = this.filters[def.key].get_value();
			if (v.length) out[def.key] = v;
		});
		const from = this.$dash.find('[data-date="from_date"]').val();
		const to = this.$dash.find('[data-date="to_date"]').val();
		if (from) out.from_date = from;
		if (to) out.to_date = to;
		return out;
	}

	on_filter_change(key) {
		this.cascade();
		if (key === "academic_term" && !this.dates_touched) this.suggest_term_dates();
		this.mark_dirty();
	}

	// Narrow each filter's options by its parents' selection; runs to a fixed point because pruning a
	// selection can narrow a grandchild. Options with no parent value stay visible.
	cascade() {
		for (let pass = 0; pass < 4; pass++) {
			let changed = false;
			UQ_FILTERS.forEach((def) => {
				if (!def.parents) return;
				const ms = this.filters[def.key];
				const visible = ms.options.filter((o) =>
					Object.entries(def.parents).every(([attr, parent]) => {
						const sel = this.filters[parent].get_value();
						if (!sel.length) return true;
						const v = o[attr];
						if (v == null || v === "" || (Array.isArray(v) && !v.length)) return true;
						return Array.isArray(v) ? v.some((x) => sel.includes(x)) : sel.includes(v);
					})
				);
				if (ms.set_visible(visible)) changed = true;
			});
			if (!changed) break;
		}
	}

	suggest_term_dates() {
		const terms = this.filters.academic_term.get_value();
		const opts = (this.options.academic_term || []).filter((t) => terms.includes(t.value) && t.start && t.end);
		if (!opts.length) return;
		this.$dash.find('[data-date="from_date"]').val(opts.map((t) => t.start).sort()[0]);
		this.$dash.find('[data-date="to_date"]').val(opts.map((t) => t.end).sort().slice(-1)[0]);
	}

	mark_dirty() {
		const dirty = JSON.stringify(this.get_draft()) !== JSON.stringify(this.applied);
		this.$dash.find("[data-apply]").toggleClass("has-changes", dirty);
		this.$dash.find(".uq-pending-note").toggleClass("show", dirty);
		const adv = UQ_FILTERS.filter((f) => !f.primary && this.filters[f.key].get_value().length).length;
		this.$dash.find(".uq-more-count").text(adv ? ` (${adv})` : "");
	}

	toggle_filters(force) {
		const $f = this.$dash.find(".uq-filters");
		const open = force != null ? force : $f.hasClass("collapsed");
		$f.toggleClass("collapsed", !open);
		$f.find("[data-edit-filters]").attr("aria-expanded", String(open)).find("span").text(open ? __("Hide filters") : __("Edit filters"));
	}

	apply() {
		this.toggle_filters(false);
		$(".uq-ms.open").each((_, el) => $(el).data("ms")?.close());
		this.applied = this.get_draft();
		this.mark_dirty();
		this.render_context();
		this.load_dashboard();
		this.reload_tables();
	}

	// Clear every filter (year, term, programme, dates and the advanced ones) → all records you can access.
	reset() {
		this.set_draft({});
		this.cascade();
		this.apply();
	}

	// Re-apply the current academic year, term and that term's dates.
	use_current_term() {
		this.set_draft(this.defaults);
		this.cascade();
		this.apply();
	}

	filter_text(key, filters = this.applied) {
		const v = filters[key];
		if (!v || !v.length) return __("All");
		const ms = this.filters[key];
		return v.length > 2 ? __("{0} selected", [v.length]) : v.map((x) => ms.label_for(x)).join(", ");
	}

	// "Showing: …" strip so everyone knows what the numbers represent.
	render_context() {
		const a = this.applied;
		const parts = [
			[__("Year"), this.filter_text("academic_year")],
			[__("Term"), this.filter_text("academic_term")],
			[__("Programme"), this.filter_text("programme")],
			[__("Dates"), a.from_date || a.to_date ? `${uq_date(a.from_date)} – ${uq_date(a.to_date)}` : __("All dates")],
		];
		const extra = UQ_FILTERS.filter((f) => !f.primary && (a[f.key] || []).length).map((f) => [f.label, this.filter_text(f.key)]);
		const attention = this.attention_count || 0;
		this.$dash.find(".uq-context").html(`
			<div class="uq-context-items">
				${parts.concat(extra).map(([k, v]) => `<span class="uq-context-item"><span>${uq_esc(k)}</span> ${uq_esc(v)}</span>`).join("")}
				<span class="uq-context-time">${uq_icon("clock", 12)} <span data-updated>—</span></span>
			</div>
			${attention ? `<a href="/desk/uniquad-dashboard" class="uq-attention" data-jump="action">${uq_icon("alert", 13)} ${__("{0} areas need attention", [attention])}</a>` : ""}`);
		this.update_timestamp();
	}


	scope_chips(applies, filters) {
		filters = filters || this.applied;
		const label_key = Object.fromEntries(UQ_FILTERS.map((d) => [d.label, d.key]));
		const chips = [];
		applies.forEach((label) => {
			if (label === "Date Range") {
				if (filters.from_date || filters.to_date) chips.push(`<span class="uq-chip"><b>${__("Dates")}:</b> ${uq_esc(uq_date(filters.from_date))} – ${uq_esc(uq_date(filters.to_date))}</span>`);
				return;
			}
			const key = label_key[__(label)] || label_key[label];
			if (!key || !(filters[key] || []).length) return;
			chips.push(`<span class="uq-chip"><b>${uq_esc(__(label))}:</b> ${uq_esc(this.filter_text(key, filters))}</span>`);
		});
		return chips.length ? chips.join("") : `<span class="uq-chip">${__("No filters narrow this list")}</span>`;
	}

	scope_line(c) {
		if (c.all_time) return `<span class="uq-card-scope">${uq_icon("history", 11)} ${__("Since inception")}</span>`;
		const applies = (c.applies || []).map((a) => __(a));
		const title = applies.length ? __("Responds to filters: {0}", [applies.join(", ")]) : __("Not affected by filters");
		const text = applies.length ? __("{0} filters apply", [applies.length]) : __("No filters apply");
		return `<span class="uq-card-scope" title="${uq_esc(title)}">${uq_icon("filter", 11)} ${uq_esc(text)}<span class="uq-sr">: ${uq_esc(applies.join(", "))}</span></span>`;
	}

	value_html(c) {
		if (c.error) return `<div class="uq-card-value uq-card-value-sm">${uq_icon("alert", 14)} ${__("Unavailable")}</div>`;
		if (c.fmt === "text") return `<div class="uq-card-value uq-card-value-text">${uq_esc(c.value || __("None"))}</div>`;
		return `<div class="uq-card-value">${uq_esc(uq_format(c.value, c.fmt))}</div>`;
	}

	drill_btn(c) {
		return c.drill
			? `<button type="button" class="uq-card-link" data-drill="${uq_esc(c.drill)}" aria-label="${uq_esc(__(c.action) + ": " + c.title)}">${uq_esc(__(c.action))} ${uq_icon("arrow-right", 12)}</button>`
			: "";
	}

	kpi_card(c, i, hero = false) {
		const acc = ["", "acc-2", "acc-3", "acc-4"][i % 4];
		const empty = c.value == null || (c.fmt !== "text" && c.fmt !== "pct" && !flt(c.value)) ? "is-empty" : "";
		return `
			<article class="uq-card ${hero ? "hero" : "compact"} ${acc} ${empty} ${c.drill ? "clickable" : ""}" title="${uq_esc(c.description)}">
				<div class="uq-card-top"><span class="uq-card-icon">${uq_icon(c.icon, hero ? 18 : 15)}</span>
					<span class="uq-card-cat">${uq_esc(this.card_category(c))}</span></div>
				${this.value_html(c)}
				<div class="uq-card-label">${uq_esc(c.title)}</div>
				${c.sub ? `<div class="uq-card-sub">${uq_esc(c.sub)}</div>` : ""}
				${this.delta_html(c)}
				<div class="uq-card-foot">${this.scope_line(c)}${this.drill_btn(c)}</div>
			</article>`;
	}

	// Change vs the previous period of equal length (only for date-range metrics the server compared).
	delta_html(c) {
		if (c.previous == null || c.value == null) return "";
		const cur = flt(c.value), prev = flt(c.previous);
		if (!cur && !prev) return "";
		let text, dir;
		if (!prev) {
			text = __("up from 0");
			dir = "up";
		} else {
			const pct = Math.round((100 * (cur - prev)) / Math.abs(prev));
			dir = pct > 0 ? "up" : pct < 0 ? "down" : "flat";
			text = pct === 0 ? __("no change") : `${Math.abs(pct)}%`;
		}
		const arrow = { up: "▲", down: "▼", flat: "■" }[dir];
		return `<div class="uq-delta uq-delta-${dir}" title="${uq_esc(__("Previous period: {0} ({1})", [uq_format(c.previous, c.fmt), c.previous_label]))}">
			<span aria-hidden="true">${arrow}</span> ${uq_esc(text)} <span class="uq-delta-l">${__("vs previous period")}</span></div>`;
	}

	alltime_card(c) {
		return `
			<article class="uq-card alltime ${c.drill ? "clickable" : ""}" title="${uq_esc(c.description)}">
				<div class="uq-card-top"><span class="uq-card-icon">${uq_icon(c.icon, 14)}</span><span class="uq-card-cat">${uq_esc(this.card_category(c))}</span></div>
				${this.value_html(c)}
				<div class="uq-card-label">${uq_esc(c.title)}</div>
				<div class="uq-card-foot">${this.drill_btn(c)}</div>
			</article>`;
	}

	alert_card(c, category = null) {
		const v = flt(c.value);
		let state;
		if (c.error) state = `<span class="uq-state">${__("Unavailable")}</span>`;
		else if (v > 0) state = `<span class="uq-state attention">${uq_icon("alert", 11)} ${__("Needs attention")}</span>`;
		else state = `<span class="uq-state clear">${uq_icon("check", 11)} ${__("All clear")}</span>`;
		return `
			<article class="uq-card alert ${v > 0 ? "attention" : "clear"} ${c.drill ? "clickable" : ""}" title="${uq_esc(c.description)}">
				<div class="uq-card-top"><span class="uq-card-icon">${uq_icon(c.icon, 15)}</span><span class="uq-card-cat">${uq_esc(category || this.card_category(c))}</span><span class="uq-card-flag">${state}</span></div>
				${this.value_html(c)}
				<div class="uq-card-label">${uq_esc(c.title)}</div>
				${c.sub ? `<div class="uq-card-sub">${uq_esc(c.sub)}</div>` : ""}
				<div class="uq-card-foot">${this.scope_line(c)}${this.drill_btn(c)}</div>
			</article>`;
	}

	card_category(c) {
		const map = {
			"Student Master": __("Students"),
			"Course Offering": __("Courses"),
			Course: __("Courses"),
			Programme: __("Programmes"),
			Batch: __("Batches"),
			Faculty: __("Faculty"),
			"Time Table": __("Timetable"),
			"Attendance Session": __("Sessions"),
			"Student Attendance": __("Attendance"),
			"Attendance Summary": __("Attendance"),
			"Student Attendance Condonation": __("Condonation"),
			Applicant: __("Admissions"),
			"Student Course Marks": __("Marks"),
			"Student Result Publish": __("Results"),
			"Fee Demand": __("Fees"),
			"Academic Year": __("Calendar"),
			"Academic Term": __("Calendar"),
			"Institutional Calendar": __("Calendar"),
			"Venue Booking": __("Venues"),
			"Venue Master": __("Venues"),
			"ID Card Generation": __("ID Cards"),
			"ID Card Print Log": __("ID Cards"),
			"Fee Payment": __("Payments"),
			"Fee Refund": __("Refunds"),
			"Fee Concession": __("Concessions"),
			"PACE Application": __("PACE"),
			"PACE Enquiry": __("PACE"),
			"PACE Document Verification": __("PACE"),
			"Foundations for a Legal Education": __("FLE"),
		};
		return map[c.doctype] || (UQ_MODULE_BY_KEY[c.section] || {}).title || "";
	}

	// ── charts

	render_charts() {
		if (!this.data) return;
		const ch = this.data.charts || {};
		const t = this.threshold;
		const line = ch.attendance_trend;
		if (line && !line.restricted) {
			this.time_chart("attendance_trend", line, {
				type: "line",
				name: __("Presence %"),
				color: UQ_BRAND,
				fmt: (v) => uq_num(v, 1) + "%",
				markers: [{ label: __("Required {0}%", [t]), value: t }],
				empty: __("No marked student attendance in the selected date range."),
				data_rows: (line.labels || []).map((l, i) => [l, uq_num(line.values[i], 1) + "%", uq_int(line.counts[i])]),
				data_head: [line.granularity === "week" ? __("Week of") : __("Date"), __("Presence %"), __("Records")],
			});
		}
		const weekly = ch.classes_weekly;
		if (weekly && !weekly.restricted) {
			this.time_chart("classes_weekly", weekly, {
				type: "bar",
				name: __("Classes"),
				color: "#3D4A5C",
				fmt: (v) => uq_int(v),
				empty: __("No classes are timetabled in the selected date range."),
				data_rows: (weekly.labels || []).map((l, i) => [l, uq_int(weekly.values[i])]),
				data_head: [weekly.granularity === "week" ? __("Week of") : __("Date"), __("Classes")],
			});
		}
		const sb = ch.student_breakdowns || {};
		this.bars("students_by_programme", sb.students_by_programme, { drill: "students", filter: "programme" });
		this.bars("students_by_status", sb.students_by_status, { drill: "students", filter: "student_status" });
		this.bars("students_by_stage", sb.students_by_stage, {});
		this.bars("students_by_gender", sb.students_by_gender, { drill: "students", filter: "gender" });
		const ca = ch.course_attendance;
		if (ca && !ca.restricted) this.bars("course_attendance", ca.items, { drill: "attendance_summary", filter: "course", pct: true, threshold: ca.threshold, empty: __("No attendance summaries for the selected scope.") });
		const st = ch.application_stages;
		if (st && !st.restricted) this.bars("application_stages", st, { empty: __("No applications for the selected year and programme.") });

		const tk = ch.tickets || {};
		this.$dash.find("#uq-home-helpdesk").toggle(!tk.restricted && !tk.error);
		if (!tk.restricted) {
			const none_open = __("No open tickets — all clear.");
			const none_raised = __("No tickets were raised in the selected date range.");
			this.bars("tickets_open_status", tk.error ? tk : tk.tickets_open_status, { drill: "tickets_open", param: "status", empty: none_open });
			this.bars("tickets_open_team", tk.error ? tk : tk.tickets_open_team, { drill: "tickets_open", param: "agent_group", empty: none_open });
			this.bars("tickets_raised_kind", tk.error ? tk : tk.tickets_raised_kind, { drill: "tickets_range", param: "kind", empty: none_raised });
			this.bars("tickets_top_raisers", tk.error ? tk : tk.tickets_top_raisers, { drill: "tickets_range", param: "raised_by", empty: none_raised });
			this.bars("tickets_by_type", tk.error ? tk : tk.tickets_by_type, { drill: "tickets_range", param: "ticket_type", empty: none_raised });
			this.panel_total("tickets_open_status", tk.open_total, __("open"));
			this.panel_total("tickets_raised_kind", tk.raised_total, __("raised in range"));
		}
		const vd = ch.venue_decisions || {};
		this.$dash.find("#uq-home-venue").toggle(!vd.restricted && !vd.error && this.home_modules.has("venue"));
		if (!vd.restricted) {
			const none = __("No venue bookings in the selected date range.");
			this.bars("venue_by_status", vd.error ? vd : vd.venue_by_status, { drill: "venue_bookings_all", param: "status", empty: none });
			this.bars("venue_by_approver", vd.error ? vd : vd.venue_by_approver, { drill: "venue_bookings_all", param: "replied_by", empty: __("No venue requests were approved or rejected in the selected date range.") });
			this.bars("venue_by_requester", vd.error ? vd : vd.venue_by_requester, { drill: "venue_bookings_all", param: "requester_type", empty: none });
			this.bars("venue_swaps", vd.error ? vd : vd.venue_swaps, { drill: "venue_bookings_all", param: "swap_status", empty: __("No venue swap requests in the selected date range.") });
		}
	}

	// headline count shown beside a panel title, e.g. "12 open"
	panel_total(id, n, label) {
		const $h = this.$dash.find(`[data-panel="${id}"]`).find(".uq-panel-title").first();
		$h.find(".uq-panel-total").remove();
		if (n != null) $h.append(` <span class="uq-panel-total">${uq_int(n)} ${uq_esc(label)}</span>`);
	}

	time_chart(id, d, o) {
		const $wrap = this.$dash.find(`[data-chart="${id}"]`);
		if (!$wrap.length) return;
		const $body = $wrap.parent();
		$body.find(".uq-chart-data").remove();
		if (this.charts[id]) {
			try {
				this.charts[id].destroy && this.charts[id].destroy();
			} catch (e) {
				/* already detached */
			}
			delete this.charts[id];
		}
		if (d.error) return $wrap.html(`<div class="uq-empty">${uq_icon("alert", 24)}<strong>${__("Unable to load data.")}</strong></div>`);
		if (!d.labels || !d.labels.length) return $wrap.html(`<div class="uq-empty">${uq_icon("chart", 26)}<strong>${__("No data available for the selected filters.")}</strong>${uq_esc(o.empty)}</div>`);
		$wrap.empty().attr({ role: "img", "aria-label": `${o.name}: ` + d.labels.map((l, i) => `${l} ${o.fmt(d.values[i])}`).join(", ") });
		const pressed = this.$dash.find(`[data-chart-table="${id}"]`).attr("aria-pressed") === "true";
		try {
			if (pressed || !$wrap[0].offsetWidth) throw "hidden";
			this.charts[id] = new frappe.Chart($wrap[0], {
				type: d.labels.length < 2 ? "bar" : o.type, // frappe-charts cannot draw a line through one point
				height: 230,
				data: { labels: d.labels, datasets: [{ name: o.name, values: d.values }], yMarkers: o.markers },
				colors: [o.color],
				axisOptions: { xIsSeries: true, shortenYAxisNumbers: true },
				lineOptions: { dotSize: 5, hideDots: 0, regionFill: 0 },
				barOptions: { spaceRatio: 0.55 },
				tooltipOptions: { formatTooltipY: o.fmt },
			});
		} catch (e) {
			if (e !== "hidden") $wrap.html(`<div class="uq-empty">${__("Chart unavailable.")}</div>`);
		}
		const rows = o.data_rows.map((r) => `<tr>${r.map((c, i) => `<td class="${i ? "num" : ""}">${uq_esc(c)}</td>`).join("")}</tr>`).join("");
		$body.append(`<div class="uq-chart-data" ${pressed ? "" : 'style="display:none"'}><div class="uq-dt-scroll"><table class="uq-table" style="min-width:0"><thead><tr>${o.data_head.map((h, i) => `<th class="${i ? "num" : ""}"><span>${uq_esc(h)}</span></th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div></div>`);
		if (pressed) $wrap.hide();
	}

	bars(id, items, o) {
		const $el = this.$dash.find(`[data-bars="${id}"]`);
		if (!$el.length || !items || items.restricted) return;
		if (items.error) return $el.html(`<div class="uq-empty">${uq_icon("alert", 24)}<strong>${__("Unable to load data.")}</strong></div>`);
		if (!items.length) return $el.html(`<div class="uq-empty">${uq_icon("chart", 24)}<strong>${__("No data available for the selected filters.")}</strong>${uq_esc(o.empty || __("Try changing your filters."))}</div>`);
		const max = o.pct ? 100 : Math.max(...items.map((i) => i.value), 1);
		const total = items.reduce((s, i) => s + i.value, 0);
		const html = items
			.map((it) => {
				const w = Math.max(1, (100 * it.value) / max);
				const below = o.pct && it.value < o.threshold;
				// decision bars (venue) break the count into approved / rejected instead of a share
				const decided = it.approved != null ? __("{0} approved · {1} rejected", [uq_int(it.approved), uq_int(it.rejected)]) : "";
				const value = o.pct
					? `${uq_num(it.value, 1)}%${below ? ` <small>${__("below")}</small>` : ""}`
					: `${uq_int(it.value)} <small>${decided ? uq_esc(decided) : total ? Math.round((100 * it.value) / total) + "%" : ""}</small>`;
				const marker = o.pct ? `<span class="uq-bar-marker" style="left:${o.threshold}%" aria-hidden="true"></span>` : "";
				const inner = `<span class="uq-bar-label" title="${uq_esc(it.label)}">${uq_esc(it.label)}${it.sub ? ` <small>${uq_esc(__(it.sub))}</small>` : ""}</span>
					<span class="uq-bar-track" aria-hidden="true"><span class="uq-bar-fill" style="width:${w}%;display:block"></span>${marker}</span>
					<span class="uq-bar-value">${value}</span>`;
				const aria = `${it.label}: ${o.pct ? uq_num(it.value, 1) + "%" : uq_int(it.value)}${decided ? ", " + decided : ""}${below ? ", " + __("below threshold") : ""}`;
				return o.drill && it.key
					? `<li><button type="button" class="uq-bar" data-bar-drill="${o.drill}" ${o.param ? `data-bar-param="${o.param}"` : `data-bar-filter="${o.filter}"`} data-bar-value="${uq_esc(it.key)}" data-bar-label="${uq_esc(it.label)}" aria-label="${uq_esc(aria + ". " + __("View records"))}">${inner}</button></li>`
					: `<li><div class="uq-bar" aria-label="${uq_esc(aria)}">${inner}</div></li>`;
			})
			.join("");
		const legend = o.pct ? `<div class="uq-legend"><span><i class="line"></i>${__("Required {0}%", [o.threshold])}</span><span>${__("Average attendance % per course")}</span></div>` : "";
		$el.html(`<ul class="uq-bars">${html}</ul>${legend}`);
	}

	// ── auto refresh (never triggered by editing filters; reuses the applied filters)

	start_autorefresh() {
		this.last_load = Date.now();
		this.refresh_timer = setInterval(() => {
			const mins = cint(this.$dash.find("[data-autorefresh]").val());
			this.update_timestamp();
			if (!mins || document.hidden || this.modal.is_open() || this.$dash.prop("hidden")) return;
			if (frappe.get_route()[0] !== UQ_PAGE) return;
			if (Date.now() - this.last_load >= mins * 60000) {
				this.load_dashboard();
				this.reload_tables();
			}
		}, 30000);
	}

	update_timestamp() {
		if (!this.last_load || !this.data) return;
		const mins = cint(this.$dash.find("[data-autorefresh]").val());
		const ago = Math.round((Date.now() - this.last_load) / 60000);
		const when = frappe.datetime.str_to_user(frappe.datetime.get_datetime_as_string(new Date(this.last_load))).slice(0, 16);
		this.$dash.find("[data-updated]").text(`${when} (${ago < 1 ? __("just now") : __("{0} min ago", [ago])})${mins ? " · " + __("auto every {0} min", [mins]) : ""}`);
	}

	// ── student profile (further drilldown)

	open_student(student) {
		if (!student) return;
		this.modal.is_open() && this.modal.close();
		frappe.set_route(UQ_PAGE, "student", student);
	}

	show_profile(student) {
		this.$dash.prop("hidden", true);
		this.$profile.prop("hidden", false).html(`
			<div class="uq-profile-top"><button type="button" class="uq-btn" data-back-dash>${uq_icon("arrow-left", 14)} ${this.view && this.view !== "home" ? __("Back to {0}", [uq_esc(UQ_MODULE_BY_KEY[this.view].title)]) : __("Back to Uniquad Dashboard")}</button></div>
			<div class="uq-hero"><div class="uq-skel" style="width:60px;height:60px;border-radius:50%"></div>
				<div style="flex:1"><div class="uq-skel" style="height:20px;width:40%"></div><div class="uq-skel" style="height:12px;width:25%;margin-top:10px"></div></div></div>
			<div class="uq-tiles">${'<div class="uq-tile"><div class="uq-skel" style="height:40px"></div></div>'.repeat(5)}</div>`);
		// back returns to the module (or home) the user came from
		this.$profile.off("click").on("click", "[data-back-dash]", () => (this.view && this.view !== "home" ? frappe.set_route(UQ_PAGE, "module", this.view) : frappe.set_route(UQ_PAGE)));
		this.scroller().scrollTop = 0;
		const id = (this.profile_req = (this.profile_req || 0) + 1);
		uq_call("get_student_profile", { student })
			.then((msg) => id === this.profile_req && this.render_profile(msg || {}))
			.catch(() => id === this.profile_req && this.profile_state("alert", __("Unable to load this student."), __("Please try again.")));
	}

	profile_state(icon, title, text) {
		this.$profile.find(".uq-hero, .uq-tiles, .uq-grid").remove();
		this.$profile.append(`<div class="uq-panel"><div class="uq-empty">${uq_icon(icon, 30)}<strong>${uq_esc(title)}</strong>${uq_esc(text)}</div></div>`);
	}

	render_profile(d) {
		if (d.denied) {
			return this.profile_state("lock", __("This student record is not available to you."), __("It may not exist, or it is outside the records your role can access."));
		}
		const p = d.profile;
		document.title = `${p.first_name || p.name} · ${__("Uniquad Dashboard")}`;
		const t = this.threshold;
		const initials = (p.first_name || p.name || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
		const fact = (label, v) => `<div><dt>${uq_esc(label)}</dt><dd>${v == null || v === "" ? "—" : uq_esc(v)}</dd></div>`;

		const att = d.attendance.rows || [];
		const avg = att.length ? att.reduce((s, r) => s + flt(r.attendance_percentage), 0) / att.length : null;
		const shortage = att.filter((r) => !cint(r.eligible_for_exam)).length;
		const counts = d.session_status_counts || {};
		const recorded = Object.values(counts).reduce((a, b) => a + b, 0);
		const present = ["Present", "Late", "OD"].reduce((s, k) => s + (counts[k] || 0), 0);
		const latest = (d.results.rows || [])[0];
		const fees = d.fees.rows || [];
		const outstanding = fees.reduce((s, f) => s + flt(f.outstanding_amount), 0);

		const tile = (label, value, sub = "", brand = false) =>
			`<div class="uq-tile"><div class="uq-tile-l">${uq_esc(label)}</div><div class="uq-tile-v ${brand ? "brand" : ""}">${uq_esc(value)}</div>${sub ? `<div class="uq-tile-s">${uq_esc(sub)}</div>` : ""}</div>`;
		const tiles = [
			!d.attendance.restricted && tile(__("Average Attendance"), uq_pct(avg), __("across {0} courses", [att.length]), avg != null && avg < t),
			!d.attendance.restricted && tile(__("Attendance Shortage"), uq_int(shortage), shortage ? __("courses below requirement") : __("all courses eligible"), shortage > 0),
			!d.sessions.restricted && tile(__("Recent Sessions Present"), recorded ? `${present}/${recorded}` : "—", __("last {0} records", [recorded])),
			!d.results.restricted && tile(__("Latest CGPA"), latest ? uq_num(latest.cumulative_gpa, 2) : "—", latest ? latest.exam_plan : __("no published result")),
			!d.fees.restricted && tile(__("Outstanding Fees"), uq_money(outstanding), __("{0} open demands", [fees.filter((f) => flt(f.outstanding_amount) > 0).length]), outstanding > 0),
		].filter(Boolean);

		const panel = (title, q, body) => `<div class="uq-panel"><div class="uq-panel-head"><div><h3 class="uq-panel-title">${uq_esc(title)}</h3>${q ? `<p class="uq-panel-q">${uq_esc(q)}</p>` : ""}</div></div><div class="uq-panel-body">${body}</div></div>`;
		const restricted = `<div class="uq-restricted">${uq_icon("lock", 14)} ${__("Not available for your role.")}</div>`;
		const table = (block, cols, empty) => {
			if (block.restricted) return restricted;
			const rows = block.rows || [];
			if (!rows.length) return `<div class="uq-empty" style="padding:16px">${uq_esc(empty)}</div>`;
			const num = (c) => ["int", "float", "currency", "pct", "gpa", "pctplain"].includes(c[2]);
			return `<div class="uq-dt-scroll"><table class="uq-table" style="min-width:480px"><thead><tr>${cols.map((c) => `<th scope="col" class="${num(c) ? "num" : ""}"><span>${uq_esc(c[1])}</span></th>`).join("")}</tr></thead>
				<tbody>${rows.map((r) => `<tr>${cols.map((c) => `<td class="${num(c) ? "num" : ""}">${this.profile_cell(c, r)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
		};

		let enroll_html = restricted;
		if (!d.enrollments.restricted) {
			const en = d.enrollments.rows || [];
			enroll_html = en.length
				? en
						.map(
							(e) => `<div style="margin-bottom:12px"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px">
							<strong>${uq_esc(e.term_name || e.academic_year || e.name)}</strong> ${uq_badge(e.status)}
							<span class="uq-tile-s">${uq_esc([e.program, e.batch, e.section].filter(Boolean).join(" · "))}</span></div>
							${table({ rows: e.courses || [] }, [["course", __("Course"), "text"], ["course_type", __("Type"), "text"], ["credits", __("Credits"), "int"], ["status", __("Status"), "badge"], ["grade", __("Grade"), "text"]], __("No courses on this enrolment."))}</div>`
						)
						.join("")
				: `<div class="uq-empty" style="padding:16px">${__("No enrolment records.")}</div>`;
		}

		this.$profile.html(`
			<div class="uq-profile-top">
				<button type="button" class="uq-btn" data-back-dash>${uq_icon("arrow-left", 14)} ${this.view && this.view !== "home" ? __("Back to {0}", [uq_esc(UQ_MODULE_BY_KEY[this.view].title)]) : __("Back to Uniquad Dashboard")}</button>
				<a class="uq-btn" href="${uq_esc(frappe.utils.get_form_link("Student Master", p.name))}">${uq_icon("external", 14)} ${__("Open Student Record")}</a>
			</div>
			<div class="uq-hero">
				<div class="uq-avatar" aria-hidden="true">${uq_esc(initials)}</div>
				<div class="uq-hero-main">
					<h2>${uq_esc(p.first_name || p.name)}</h2>
					<div class="uq-hero-id">${uq_esc(p.name)}${p.registration_id ? " · " + uq_esc(p.registration_id) : ""}</div>
					<div class="uq-hero-badges">${uq_badge(p.student_status)} ${p.registration_status ? uq_badge(p.registration_status) : ""} ${p.admission_type ? `<span class="uq-badge">${uq_esc(p.admission_type)}</span>` : ""}</div>
				</div>
				<dl class="uq-facts">
					${fact(__("Programme"), p.programme_name ? `${p.programme_name} (${p.programme_of_study})` : p.programme_of_study)}
					${fact(__("Batch"), p.batch)}
					${fact(__("Section"), p.section)}
					${fact(__("Academic Year"), p.academic_year)}
					${fact(__("Current Year"), p.current_year)}
					${fact(__("Gender"), p.gender)}
					${fact(__("Email"), p.official_email_id || p.email)}
					${fact(__("Phone"), p.phone)}
					${fact(__("Registered On"), p.date_of_registration ? uq_date(p.date_of_registration) : "")}
					${fact(__("ID Card Issued"), p.id_card_issued)}
				</dl>
			</div>
			${tiles.length ? `<div class="uq-tiles">${tiles.join("")}</div>` : ""}
			<div class="uq-grid uq-grid-2">
				${panel(__("Course-wise Attendance"), __("Is this student eligible to sit exams in each course?"), table(d.attendance, [["course", __("Course"), "text"], ["term_name", __("Term"), "text"], ["attendance_percentage", __("Attendance"), "pct"], ["minimum_required_percentage", __("Required"), "pctplain"], ["total_class_hours", __("Hours Conducted"), "float"], ["attended_classes", __("Hours Attended"), "float"], ["eligible_for_exam", __("Eligibility"), "eligible"]], __("No attendance summary yet.")))}
				${panel(__("Recent Session History"), __("Latest 50 attendance records."), table(d.sessions, [["attendance_date", __("Date"), "date"], ["course", __("Course"), "text"], ["status", __("Status"), "badge"], ["source", __("Source"), "text"], ["attendance_session", __("Session"), "text"]], __("No attendance records.")))}
				${panel(__("Enrolments"), __("Terms and courses this student is enrolled in."), enroll_html)}
				${panel(__("Assessment Marks"), __("Marks recorded per course and exam."), table(d.marks, [["course", __("Course"), "text"], ["exam_plan", __("Exam"), "text"], ["total_marks", __("Marks"), "float"], ["grade", __("Grade"), "text"], ["status", __("Status"), "badge"]], __("No marks recorded.")))}
				${panel(__("Published Results"), "", table(d.results, [["exam_plan", __("Exam"), "text"], ["term_gpa", __("Term GPA"), "gpa"], ["cumulative_gpa", __("CGPA"), "gpa"], ["term_percentage", __("Term %"), "pctplain"], ["published_on", __("Published"), "datetime"]], __("No published results.")))}
				${panel(__("Attendance Condonation"), "", table(d.condonations, [["name", __("Request"), "text"], ["course", __("Course"), "text"], ["absence_from_date", __("From"), "date"], ["absence_to_date", __("To"), "date"], ["number_of_hours", __("Hours"), "float"], ["final_status", __("Status"), "badge"]], __("No condonation requests.")))}
				${!d.fees.restricted ? panel(__("Fee Demands"), "", table(d.fees, [["fee_component", __("Component"), "text"], ["net_payable", __("Payable"), "currency"], ["paid_amount", __("Paid"), "currency"], ["outstanding_amount", __("Outstanding"), "currency"], ["due_date", __("Due"), "date"], ["status", __("Status"), "badge"]], __("No fee demands."))) : ""}
			</div>`);
	}

	profile_cell(c, r) {
		const v = r[c[0]];
		switch (c[2]) {
			case "pct":
				return uq_pct_cell(v, this.threshold);
			case "pctplain":
				return uq_pct(v);
			case "gpa":
				return v == null ? "—" : uq_num(v, 2);
			case "eligible":
				return uq_badge(cint(v) ? "Eligible" : "Shortage");
			case "badge":
				return uq_badge(v);
			case "int":
				return v == null ? "—" : uq_int(v);
			case "float":
				return v == null ? "—" : uq_num(v, 1);
			case "currency":
				return uq_money(v);
			case "date":
				return uq_date(v);
			case "datetime":
				return uq_datetime(v);
			default:
				return v == null || v === "" ? "—" : uq_esc(v);
		}
	}
}

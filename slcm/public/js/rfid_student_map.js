// Copyright (c) 2026, Nishanth and contributors
// Student Map dialog — shared by RFID SQL Agent Settings, RFID Card Management and the Student Map Log.
// Load with: frappe.require("/assets/slcm/js/rfid_student_map.js", () => slcm.rfid_student_map.open({...}))

frappe.provide("slcm.rfid_student_map");

(function () {
	const API = "slcm.slcm.rfid_sql_agent.student_map.";
	const LOG = "RFID Student Map Log";
	const PAGE = 50;

	const STATUS = {
		Ready: { label: __("Will map"), cls: "ok" },
		"Already Mapped": { label: __("Already mapped"), cls: "info" },
		"Not Matched": { label: __("Not matched"), cls: "warn" },
		Conflict: { label: __("Conflict"), cls: "err" },
		Skipped: { label: __("Held back"), cls: "warn" },
		Mapped: { label: __("Mapped"), cls: "ok" },
		"Manually Mapped": { label: __("Mapped by hand"), cls: "ok" },
		Failed: { label: __("Failed"), cls: "err" },
		Pending: { label: __("Pending"), cls: "info" },
	};

	const esc = (s) => (s == null ? "" : frappe.utils.escape_html(String(s)));
	const fmt = (n) => (parseInt(n, 10) || 0).toLocaleString("en-IN");
	const dash = '<span class="rsm-dim">—</span>';
	const log_links = () => `<span class="rsm-links">
		<a href="/app/rfid-student-map-log" target="_blank" rel="noopener"><i class="fa fa-history"></i> ${__("Student Map Log")}</a>
		<a href="/app/rfid-uid-change-log" target="_blank" rel="noopener"><i class="fa fa-exchange"></i> ${__("RFID UID Change Log")}</a></span>`;

	slcm.rfid_student_map.status_tag = (status) => {
		const s = STATUS[status] || { label: status || "—", cls: "info" };
		return `<span class="rsm-tag ${s.cls}">${esc(s.label)}</span>`;
	};

	slcm.rfid_student_map.inject_css = function () {
		if (!document.getElementById("er-theme-font")) {
			$("head").append('<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
		}
		if (document.getElementById("rsm-css")) return;
		$("head").append(`<style id="rsm-css">
.rsm-scope {
	--rsm-brand:#920C24; --rsm-brand-dk:#6E091B; --rsm-brand-50:#FBF1F3; --rsm-brand-100:#F5DDE2;
	--rsm-ink:#1F1A1C; --rsm-ink-2:#5C5457; --rsm-ink-3:#8E8588; --rsm-surface:#fff; --rsm-canvas:#F7F5F5;
	--rsm-line:#ECE6E7; --rsm-line-2:#F4F0F1; --rsm-dev:#F4F7FA; --rsm-dev-head:#E9EFF5;
	--rsm-ok:#1E7B4C; --rsm-ok-bg:#E7F5EE; --rsm-warn:#8A5A00; --rsm-warn-bg:#FFF4DB;
	--rsm-info:#4B5563; --rsm-info-bg:#F1F2F4; --rsm-err:#B42318; --rsm-err-bg:#FDECEA;
	--rsm-serif:"Merriweather", Georgia, "Times New Roman", serif;
	--rsm-mono:ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
	font-family:var(--rsm-serif); color:var(--rsm-ink);
}
[data-theme="dark"] .rsm-scope {
	--rsm-brand:#E0566F; --rsm-brand-dk:#F07A8F; --rsm-brand-50:#2A1A1E; --rsm-brand-100:#3A2228;
	--rsm-ink:#F2EDEE; --rsm-ink-2:#C2B8BB; --rsm-ink-3:#8E8588; --rsm-surface:#1E1B1C; --rsm-canvas:#161314;
	--rsm-line:#332C2E; --rsm-line-2:#282223; --rsm-dev:#1C2127; --rsm-dev-head:#232A32;
	--rsm-ok:#5CC995; --rsm-ok-bg:#16291F; --rsm-warn:#F2C063; --rsm-warn-bg:#2E2614;
	--rsm-info:#B6BCC6; --rsm-info-bg:#24272B; --rsm-err:#F28B82; --rsm-err-bg:#2E1A18;
}
.rsm-dlg .modal-content { font-family:"Merriweather", Georgia, serif; border-top:4px solid #920C24; }
.rsm-dlg .modal-title { font-weight:800; color:#920C24; letter-spacing:-.01em; }
.rsm-dlg .modal-footer .btn-primary { background:#920C24; border-color:#920C24; color:#fff; font-weight:700; }
.rsm-dlg .modal-footer .btn-primary:hover:not(:disabled) { background:#6E091B; border-color:#6E091B; }
.rsm-dlg .modal-footer .btn-secondary { font-weight:700; }
[data-theme="dark"] .rsm-dlg .modal-title { color:#E0566F; }
.rsm-scope button, .rsm-scope input { font-family:inherit; }
.rsm-meta { display:flex; flex-wrap:wrap; gap:8px 16px; align-items:center; margin-bottom:16px; font-size:12.5px; color:var(--rsm-ink-2); }
.rsm-meta b { color:var(--rsm-ink); }
.rsm-links { display:inline-flex; gap:14px; }
.rsm-links a { color:var(--rsm-brand); font-weight:700; text-decoration:none; white-space:nowrap; }
.rsm-links a:hover { text-decoration:underline; color:var(--rsm-brand-dk); }
.rsm-links .fa { margin-right:3px; }
.rsm-code { font-family:var(--rsm-mono); font-size:12px; background:var(--rsm-line-2); border:1px solid var(--rsm-line); padding:1px 7px; border-radius:6px; }
.rsm-toggle { margin-left:auto; display:inline-flex; align-items:center; gap:8px; cursor:pointer; font-weight:700; color:var(--rsm-ink); margin-bottom:0; }
.rsm-toggle input { margin:0; accent-color:var(--rsm-brand); }
.rsm-kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:10px; margin-bottom:18px; }
.rsm-kpi { text-align:left; border:1px solid var(--rsm-line); background:var(--rsm-surface); border-radius:10px; padding:12px 14px; cursor:pointer;
	transition:border-color .15s, background .15s; }
.rsm-kpi:hover { border-color:var(--rsm-brand); }
.rsm-kpi.on { border-color:var(--rsm-brand); background:var(--rsm-brand-50); }
.rsm-kpi.static { cursor:default; } .rsm-kpi.static:hover { border-color:var(--rsm-line); }
.rsm-kpi b { display:block; font-size:24px; font-weight:800; line-height:1.2; color:var(--rsm-ink); font-variant-numeric:tabular-nums; }
.rsm-kpi.ok b { color:var(--rsm-brand); }
.rsm-kpi span { font-size:12.5px; font-weight:700; color:var(--rsm-ink); display:block; margin-top:2px; }
.rsm-kpi small { font-size:11px; color:var(--rsm-ink-3); display:block; margin-top:1px; }
.rsm-toolbar { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:10px; }
.rsm-search { flex:1; max-width:380px; padding:8px 12px; border:1px solid var(--rsm-line); border-radius:9px; background:var(--rsm-canvas); color:var(--rsm-ink); font-size:13px; outline:none; }
.rsm-search:focus { border-color:var(--rsm-brand); background:var(--rsm-surface); box-shadow:0 0 0 3px var(--rsm-brand-100); }
.rsm-pager { display:flex; align-items:center; gap:6px; font-size:12.5px; color:var(--rsm-ink-3); }
.rsm-iconbtn { width:30px; height:30px; border-radius:8px; border:1px solid var(--rsm-line); background:var(--rsm-surface); color:var(--rsm-ink-2); cursor:pointer; }
.rsm-iconbtn:disabled { opacity:.4; cursor:default; }
.rsm-tablebox { border:1px solid var(--rsm-line); border-radius:10px; overflow:auto; max-height:52vh; }
.rsm-table { width:100%; border-collapse:separate; border-spacing:0; font-size:12.5px; margin:0; }
.rsm-table th { position:sticky; top:0; z-index:1; background:var(--rsm-brand-50); color:var(--rsm-brand); font-size:11px; letter-spacing:.06em;
	text-transform:uppercase; font-weight:800; padding:10px 12px; border-bottom:2px solid var(--rsm-brand-100); white-space:nowrap; text-align:left; }
.rsm-table td { padding:9px 12px; border-bottom:1px solid var(--rsm-line-2); vertical-align:middle; }
.rsm-table tbody tr:hover td { background:var(--rsm-brand-50); }
.rsm-table .rsm-empty td { text-align:center; padding:36px; color:var(--rsm-ink-3); }
.rsm-sid { font-family:var(--rsm-mono); font-size:12px; font-weight:700; color:var(--rsm-brand); background:var(--rsm-brand-50); border:1px solid var(--rsm-brand-100); padding:1px 7px; border-radius:6px; white-space:nowrap; }
.rsm-arrow { color:var(--rsm-ink-3); }
.rsm-dim { color:var(--rsm-ink-3); }
.rsm-note { color:var(--rsm-ink-2); font-size:12px; }
.rsm-tag { display:inline-block; font-size:11px; font-weight:700; padding:2px 9px; border-radius:999px; white-space:nowrap;
	color:var(--rsm-ink-2); background:var(--rsm-line-2); border:1px solid var(--rsm-line); }
.rsm-tag.ok { color:var(--rsm-brand); background:var(--rsm-brand-50); border-color:var(--rsm-brand-100); }
.rsm-tag.err { color:#fff; background:var(--rsm-brand); border-color:var(--rsm-brand); }
.rsm-state { text-align:center; padding:48px 20px; color:var(--rsm-ink-2); }
.rsm-state .fa { font-size:30px; color:var(--rsm-brand); display:block; margin-bottom:12px; }
.rsm-state h4 { font-family:var(--rsm-serif); font-weight:800; margin:0 0 6px; color:var(--rsm-ink); }
.rsm-state p { max-width:560px; margin:0 auto 14px; }
.rsm-state .rsm-err-text { font-family:var(--rsm-mono); font-size:12px; color:var(--rsm-err); background:var(--rsm-err-bg); border-radius:8px; padding:10px 12px; text-align:left; white-space:pre-wrap; max-height:160px; overflow:auto; }
.rsm-bar { height:8px; background:var(--rsm-line-2); border-radius:999px; overflow:hidden; max-width:420px; margin:14px auto 8px; }
.rsm-bar > div { height:100%; width:0; background:var(--rsm-brand); border-radius:999px; transition:width .4s ease; }
.rsm-btn { display:inline-flex; align-items:center; gap:7px; border-radius:8px; padding:7px 14px; font-size:13px; font-weight:700; cursor:pointer; border:1px solid var(--rsm-line); background:var(--rsm-surface); color:var(--rsm-brand); text-decoration:none; }
.rsm-btn:hover { border-color:var(--rsm-brand); text-decoration:none; color:var(--rsm-brand); }
.rsm-btn.primary { background:var(--rsm-brand); color:#fff; border-color:var(--rsm-brand); }
.rsm-btn.primary:hover { background:var(--rsm-brand-dk); color:#fff; }
.rsm-spin { animation:rsm-spin 1s linear infinite; }
.rsm-table td.rsm-dev { background:var(--rsm-dev); }
.rsm-table th.rsm-dev { background:var(--rsm-dev-head); }
.rsm-busy { opacity:.55; pointer-events:none; transition:opacity .15s; }
.rsm-callout { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin:0 0 14px; padding:10px 14px; border-radius:10px;
	background:var(--rsm-warn-bg); border:1px solid var(--rsm-warn); border-left-width:4px; color:var(--rsm-ink); }
.rsm-callout.on { background:var(--rsm-ok-bg); border-color:var(--rsm-ok); }
.rsm-callout > .fa { font-size:18px; color:var(--rsm-warn); }
.rsm-callout.on > .fa { color:var(--rsm-ok); }
.rsm-callout .rsm-callout-text { flex:1 1 260px; min-width:0; font-size:12.5px; line-height:1.45; }
.rsm-callout .rsm-callout-text b { font-size:13.5px; }
.rsm-callout label { display:inline-flex; align-items:center; gap:8px; margin:0; font-weight:800; cursor:pointer; white-space:nowrap;
	padding:6px 12px; border-radius:8px; background:var(--rsm-surface); border:1px solid var(--rsm-line); }
.rsm-callout label input { width:18px; height:18px; margin:0; accent-color:var(--rsm-ok); cursor:pointer; }
.rsm-callout label:focus-within { outline:2px solid var(--rsm-brand); outline-offset:2px; }
@media (prefers-reduced-motion: reduce) { .rsm-busy { transition:none; } .rsm-spin { animation:none; } }
@keyframes rsm-spin { to { transform:rotate(360deg); } }
@media (max-width:720px) { .rsm-toggle { margin-left:0; } .rsm-kpis { grid-template-columns:repeat(2, 1fr); } }
</style>`);
	};

	slcm.rfid_student_map.open = function (opts = {}) {
		slcm.rfid_student_map.inject_css();
		let data = null, filter = "all", q = "", page = 0, include = null, include_removed = false;
		let log_name = null, poll = null;

		// Programme / Batch / Academic Year / Section: any one or several limit the map to those students
		const SCOPE = [
			["programme", "Programme", __("Programme")],
			["batch", "SLCM Batch", __("Batch")],
			["academic_year", "Academic Year", __("Academic Year")],
			["section", "Section", __("Section")],
		];
		let loaded_scope = null, scope_timer = null;
		const scope_fields = [];
		SCOPE.forEach(([fieldname, options, label], i) => {
			if (i) scope_fields.push({ fieldname: `scope_cb_${i}`, fieldtype: "Column Break" });
			scope_fields.push({ fieldname, fieldtype: "Link", options, label,
				onchange: () => { clearTimeout(scope_timer); scope_timer = setTimeout(rescope, 250); } });
		});

		const d = new frappe.ui.Dialog({
			title: __("Student Map"),
			size: "extra-large",
			fields: [...scope_fields, { fieldname: "scope_sb", fieldtype: "Section Break" }, { fieldname: "body", fieldtype: "HTML" }],
			primary_action_label: __("Map students"),
			primary_action: () => confirm_apply(),
			secondary_action_label: __("Close"),
			secondary_action: () => d.hide(),
		});
		d.$wrapper.addClass("rsm-dlg");
		const $b = d.fields_dict.body.$wrapper.addClass("rsm-scope");
		const on_progress = (msg) => {
			if (!msg || msg.log !== log_name) return;
			if (msg.total) $b.find(".rsm-bar > div").css("width", Math.round((msg.done / msg.total) * 100) + "%");
			if (msg.total) $b.find(".rsm-progress-text").text(__("{0} of {1} linked", [fmt(msg.done), fmt(msg.total)]));
			if (msg.finished) check_done();
		};
		frappe.realtime.on("rfid_student_map_progress", on_progress);
		d.onhide = () => {
			frappe.realtime.off("rfid_student_map_progress", on_progress);
			clearInterval(poll);
			if (log_name && opts.on_done) opts.on_done(log_name);
		};

		load();
		d.show();

		function state(icon, title, text, extra = "") {
			$b.html(`<div class="rsm-state"><i class="fa ${icon}"></i><h4>${title}</h4><p>${text}</p>${extra}</div>`);
		}

		function current_scope() {
			const scope = {};
			SCOPE.forEach(([f]) => { const v = d.get_value(f); if (v) scope[f] = v; });
			return scope;
		}

		function show_filters(on) {
			SCOPE.forEach(([f]) => d.set_df_property(f, "hidden", on ? 0 : 1));
		}

		// a filter changed: re-classify the records already read (no new read of etpdb)
		function rescope() {
			const now = JSON.stringify(current_scope());
			if (now === loaded_scope || !data) return;
			load();
		}

		function load() {
			d.get_primary_btn().prop("disabled", true);
			const scope = current_scope();
			const reuse = !!(data && data.token);
			// Re-filtering (an option or a filter changed): keep the table on screen, dimmed, so the dialog does not
			// collapse and jump; the view (tile, search, page) and scroll position are kept.
			const soft = reuse && $b.find(".rsm-kpis").length > 0;
			const view = soft ? { filter, q, page, top: d.$wrapper.scrollTop(), table: $b.find(".rsm-tablebox").scrollTop() } : null;
			if (soft) {
				$b.addClass("rsm-busy").attr("aria-busy", "true");
			} else {
				state("fa-circle-o-notch rsm-spin", reuse ? __("Applying filters…") : __("Reading the device database…"),
					reuse ? __("Matching the card codes already read to the students in these filters.")
						: __("Fetching every card code and name from etpdb and matching them to Student Master."));
			}
			frappe.call({
				method: API + "preview",
				args: { include_name_mismatch: include == null ? "" : include ? 1 : 0, scope: JSON.stringify(scope), token: reuse ? data.token : "",
					include_removed: include_removed ? 1 : 0 },
				callback(r) {
					if (!r.message) return;
					data = r.message;
					loaded_scope = JSON.stringify(scope);
					data.kpi.all = data.kpi.device_records;
					data.kpi.held_back = data.kpi.skipped || 0;
					include = !!data.include_name_mismatch;
					include_removed = !!data.include_removed;
					if (view) {
						({ filter, q, page } = view);
						if (filter !== "all" && !(filter in data.kpi)) filter = "all";
					} else {
						filter = "all"; q = ""; page = 0;
					}
					$b.removeClass("rsm-busy").removeAttr("aria-busy");
					render();
					if (view) {
						d.$wrapper.scrollTop(view.top);
						$b.find(".rsm-tablebox").scrollTop(view.table);
					}
				},
				error(r) {
					if (soft) {
						// keep what is on screen; the server message is shown by Frappe
						$b.removeClass("rsm-busy").removeAttr("aria-busy");
						d.get_primary_btn().prop("disabled", !(data.kpi.ready || 0));
						return;
					}
					const msg = (r && r._server_messages) ? JSON.parse(r._server_messages).map(m => {
						try { return JSON.parse(m).message; } catch (e) { return m; }
					}).join("\n") : __("Unknown error");
					state("fa-plug", __("Could not read the device database"),
						__("Check the SQL Server details and the Student Map table/columns in RFID SQL Agent Settings."),
						`<div class="rsm-err-text">${esc(new DOMParser().parseFromString(msg, "text/html").body.textContent || "")}</div><br>
						<button class="rsm-btn" data-act="retry"><i class="fa fa-refresh"></i> ${__("Try again")}</button>
						<a class="rsm-btn" href="/app/rfid-sql-agent-settings#tab_student_map" target="_blank" rel="noopener"><i class="fa fa-cog"></i> ${__("Open settings")}</a>`);
					$b.find('[data-act="retry"]').on("click", load);
				},
			});
		}

		function kpi(key, label, cls, hint, static_) {
			const n = data.kpi[key] || 0;
			return `<button type="button" class="rsm-kpi ${cls} ${static_ ? "static" : ""} ${filter === key ? "on" : ""}" data-filter="${static_ ? "" : key}">
				<b>${fmt(n)}</b><span>${label}</span>${hint ? `<small>${hint}</small>` : ""}</button>`;
		}

		function render() {
			const k = data.kpi;
			$b.html(`
				<div class="rsm-meta">
					<span>${__("Source")}: <span class="rsm-code">${esc(data.source)}</span></span>
					<span>${__("Rule")}: <b>${esc(data.match_rule)}</b></span>
					${log_links()}
					${data.scope_label ? `<span class="rsm-tag info" title="${__("Only students in these filters are shown and mapped")}">
						<i class="fa fa-filter"></i> ${esc(data.scope_label)}</span>` : ""}
					${data.has_names
						? `<label class="rsm-toggle"><input type="checkbox" ${include ? "checked" : ""} data-act="include">
							${__("Map even when names differ")}</label>`
						: `<span class="rsm-toggle rsm-tag warn" style="cursor:default">${__("No names in this source — matching by Student ID only")}</span>`}
				</div>
				${(k.removed_by_hand || include_removed) ? `<div class="rsm-callout ${include_removed ? "on" : ""}" role="group">
					<i class="fa ${include_removed ? "fa-check-circle" : "fa-hand-paper-o"}" aria-hidden="true"></i>
					<div class="rsm-callout-text">
						<b>${include_removed
							? __("{0} card(s) taken off by hand will be mapped again", [fmt(k.removed_by_hand || 0)])
							: __("{0} card(s) were taken off students by hand and are held back", [fmt(k.removed_by_hand || 0)])}</b><br>
						${__("Tick to map them again in this run. Cards marked Lost, Damaged or Blocked always stay held back.")}
					</div>
					<label><input type="checkbox" ${include_removed ? "checked" : ""} data-act="include_removed">
						${__("Map cards removed by hand ({0})", [fmt(k.removed_by_hand || 0)])}</label>
				</div>` : ""}
				<div class="rsm-kpis">
					${kpi("all", data.scope_label ? __("In these filters") : __("Device records"), "brand",
						data.scope_label ? __("cards of students in the filters") : __("people in etpdb"))}
					${kpi("ready", __("Ready to map"), "ok", __("matched by Student ID"))}
					${kpi("already_mapped", __("Already mapped"), "", __("no change needed"))}
					${kpi("not_matched", __("Not matched"), "warn", __("no student with this ID"))}
					${kpi("conflicts", __("Conflicts"), "err", __("need a decision"))}
					${kpi("held_back", __("Held back"), "warn", __("check, then map"))}
					${data.has_names ? kpi("names_differ", __("Names differ"), "warn", include ? __("will still be mapped") : __("held back")) : ""}
					${kpi("students_not_on_device", __("Students not in etpdb"), "", __("active, no card"), true)}
					${data.scope_label ? kpi("out_of_scope", __("Outside the filters"), "", __("left out of this map"), true) : ""}
				</div>
				<div class="rsm-toolbar">
					<input class="rsm-search" type="search" placeholder="${__("Search code, name, Student ID, email…")}" value="${esc(q)}">
					<div class="rsm-pager"><span class="rsm-page-info"></span>
						<button class="rsm-iconbtn" data-act="prev"><i class="fa fa-chevron-left"></i></button>
						<button class="rsm-iconbtn" data-act="next"><i class="fa fa-chevron-right"></i></button></div>
				</div>
				<div class="rsm-tablebox"><table class="rsm-table">
					<thead><tr><th class="rsm-dev">${__("Card code")}</th><th class="rsm-dev">${__("Name in etpdb")}</th><th></th><th>${__("Student ID")}</th>
						<th>${__("Student name")}</th><th>${__("Email")}</th><th>${__("Name check")}</th><th>${__("Result")}</th><th>${__("Note")}</th></tr></thead>
					<tbody></tbody></table></div>`);

			$b.find(".rsm-kpi[data-filter]").on("click", function () {
				const f = $(this).attr("data-filter");
				if (!f) return;
				filter = f; page = 0;
				$b.find(".rsm-kpi").removeClass("on"); $(this).addClass("on");
				render_rows();
			});
			$b.find('[data-act="include"]').on("change", function () { include = this.checked; load(); });
			$b.find('[data-act="include_removed"]').on("change", function () { include_removed = this.checked; load(); });
			$b.find(".rsm-search").on("input", frappe.utils.debounce(function () { q = (this.value || "").trim().toLowerCase(); page = 0; render_rows(); }, 150));
			$b.find('[data-act="prev"]').on("click", () => { if (page > 0) { page--; render_rows(); } });
			$b.find('[data-act="next"]').on("click", () => { page++; render_rows(); });
			render_rows();

			const ready = k.ready || 0;
			d.set_primary_action(ready ? __("Map {0} student(s)", [fmt(ready)]) : __("Nothing to map"), () => confirm_apply());
			d.get_primary_btn().prop("disabled", !ready);
		}

		function visible_rows() {
			const by_filter = {
				all: () => true,
				ready: (r) => r.status === "Ready",
				already_mapped: (r) => r.status === "Already Mapped",
				not_matched: (r) => r.status === "Not Matched",
				conflicts: (r) => r.status === "Conflict",
				names_differ: (r) => r.name_check === "Different",
				held_back: (r) => r.status === "Skipped",
			}[filter] || (() => true);
			return data.rows.filter((r) => by_filter(r) && (!q ||
				["rfid_uid", "device_name", "student_id", "student_name", "student_email", "message"]
					.some((f) => r[f] && String(r[f]).toLowerCase().includes(q))));
		}

		function render_rows() {
			const rows = visible_rows();
			const max = Math.max(0, Math.ceil(rows.length / PAGE) - 1);
			page = Math.min(page, max);
			const slice = rows.slice(page * PAGE, page * PAGE + PAGE);
			$b.find(".rsm-page-info").text(rows.length ? __("{0}–{1} of {2}", [fmt(page * PAGE + 1), fmt(page * PAGE + slice.length), fmt(rows.length)]) : "");
			$b.find('[data-act="prev"]').prop("disabled", page === 0);
			$b.find('[data-act="next"]').prop("disabled", page >= max);
			$b.find("tbody").html(slice.length ? slice.map((r) => `<tr>
				<td class="rsm-dev"><span class="rsm-code">${esc(r.rfid_uid)}</span></td>
				<td class="rsm-dev">${esc(r.device_name) || dash}</td>
				<td class="rsm-arrow">→</td>
				<td>${r.student_id ? `<span class="rsm-sid">${esc(r.student_id)}</span>` : dash}</td>
				<td><b>${esc(r.student_name) || dash}</b></td>
				<td class="rsm-dim">${esc(r.student_email) || dash}</td>
				<td>${r.name_check === "Same" ? `<span class="rsm-tag ok">${__("Same")}</span>`
					: r.name_check === "Different" ? `<span class="rsm-tag warn">${__("Different")}</span>` : dash}</td>
				<td>${slcm.rfid_student_map.status_tag(r.status)}</td>
				<td class="rsm-note">${esc(r.message)}</td></tr>`).join("")
				: `<tr class="rsm-empty"><td colspan="9">${__("Nothing to show here.")}</td></tr>`);
		}

		// Step 2: review exactly what will be linked before anything is saved
		function confirm_apply() {
			const ready_rows = (data && data.rows || []).filter((r) => r.status === "Ready");
			if (!ready_rows.length) return;
			const k = data.kpi;
			const differ = ready_rows.filter((r) => r.name_check === "Different").length;
			const left = (k.not_matched || 0) + (k.conflicts || 0) + (k.skipped || 0);
			const tile = (n, label, cls, hint) =>
				`<div class="rsm-kpi static ${cls}"><b>${fmt(n)}</b><span>${label}</span>${hint ? `<small>${hint}</small>` : ""}</div>`;

			d.set_title(__("Student Map — review before mapping"));
			show_filters(false);
			$b.html(`
				<div class="rsm-meta">
					<span>${__("These cards will be linked to the Student Master records below. Nothing has been saved yet.")}</span>
					${data.scope_label ? `<span class="rsm-tag info"><i class="fa fa-filter"></i> ${esc(data.scope_label)}</span>` : ""}
					${log_links()}
				</div>
				<div class="rsm-kpis">
					${tile(ready_rows.length, __("Will be mapped"), "ok", __("card → Student Master"))}
					${data.has_names ? tile(differ, __("Names differ"), "warn", __("mapped by Student ID")) : ""}
					${tile(k.already_mapped, __("Already mapped"), "", __("left as they are"))}
					${tile(left, __("Not mapped now"), "warn", __("logged — map by hand later"))}
				</div>
				<div class="rsm-toolbar">
					<input class="rsm-search" type="search" placeholder="${__("Search code, Student ID, name, email…")}">
					<div class="rsm-pager"><span class="rsm-page-info"></span></div>
				</div>
				<div class="rsm-tablebox"><table class="rsm-table">
					<thead><tr><th>#</th><th class="rsm-dev">${__("Card code")}</th>${data.has_names ? `<th class="rsm-dev">${__("Name in etpdb")}</th>` : ""}<th></th>
						<th>${__("Student ID")}</th><th>${__("Student name")}</th><th>${__("Email")}</th><th>${__("Programme")}</th><th>${__("Batch")}</th>
						${data.has_names ? `<th>${__("Name check")}</th>` : ""}</tr></thead>
					<tbody></tbody></table></div>`);

			const draw = (q) => {
				const rows = ready_rows.filter((r) => !q ||
					["rfid_uid", "device_name", "student_id", "student_name", "student_email", "programme", "batch"]
						.some((f) => r[f] && String(r[f]).toLowerCase().includes(q)));
				const shown = rows.slice(0, 500);
				$b.find(".rsm-page-info").text(rows.length > 500
					? __("Showing 500 of {0} — search to find one", [fmt(rows.length)]) : __("{0} card(s)", [fmt(rows.length)]));
				$b.find("tbody").html(shown.map((r, i) => `<tr>
					<td class="rsm-dim">${i + 1}</td>
					<td class="rsm-dev"><span class="rsm-code">${esc(r.rfid_uid)}</span></td>
					${data.has_names ? `<td class="rsm-dev">${esc(r.device_name) || dash}</td>` : ""}
					<td class="rsm-arrow">→</td>
					<td><span class="rsm-sid">${esc(r.student_id || r.student)}</span></td>
					<td><b>${esc(r.student_name) || dash}</b></td>
					<td class="rsm-dim">${esc(r.student_email) || dash}</td>
					<td class="rsm-dim">${esc(r.programme) || dash}</td>
					<td class="rsm-dim">${esc(r.batch) || dash}</td>
					${data.has_names ? `<td>${r.name_check === "Different" ? `<span class="rsm-tag warn">${__("Different")}</span>`
						: r.name_check === "Same" ? `<span class="rsm-tag ok">${__("Same")}</span>` : dash}</td>` : ""}
				</tr>`).join("") || `<tr class="rsm-empty"><td colspan="10">${__("Nothing matches your search.")}</td></tr>`);
			};
			$b.find(".rsm-search").on("input", frappe.utils.debounce(function () { draw((this.value || "").trim().toLowerCase()); }, 150));
			draw("");

			d.set_primary_action(__("Map {0} student(s)", [fmt(ready_rows.length)]), () => start_apply());
			d.get_primary_btn().prop("disabled", false);
			d.set_secondary_action_label(__("Back"));
			d.set_secondary_action(() => {
				d.set_title(__("Student Map"));
				show_filters(true);
				d.set_secondary_action_label(__("Close"));
				d.set_secondary_action(() => d.hide());
				render();
			});
		}

		function start_apply() {
			d.get_primary_btn().prop("disabled", true);
			frappe.call({
				method: API + "apply",
				// the options and filters the reviewed list was made with
				args: { token: data.token, include_name_mismatch: include ? 1 : 0, scope: loaded_scope || "{}", include_removed: data.include_removed ? 1 : 0 },
				freeze: true, freeze_message: __("Starting…"),
				callback(r) {
					if (!r.message) return;
					log_name = r.message.log;
					d.set_secondary_action_label(__("Close"));
					d.set_secondary_action(() => d.hide());
					show_progress();
				},
				error: () => d.get_primary_btn().prop("disabled", false),
			});
		}

		function show_progress() {
			d.set_title(__("Student Map — running"));
			d.get_primary_btn().hide();
			state("fa-circle-o-notch rsm-spin", __("Linking cards…"),
				__("This runs in the background — you can close this window. Everything is recorded in {0}.",
					[`<a href="/app/rfid-student-map-log/${encodeURIComponent(log_name)}" target="_blank" rel="noopener">${esc(log_name)}</a>`]),
				`<div class="rsm-bar"><div></div></div><div class="rsm-progress-text rsm-dim">${__("Preparing…")}</div>`);
			poll = setInterval(check_done, 3000);
		}

		function check_done() {
			frappe.db.get_value(LOG, log_name,
				["status", "mapped", "failed", "already_mapped", "not_matched", "conflicts", "skipped", "total_records"])
				.then(({ message: m }) => {
					if (!m || m.status === "In Progress") return;
					clearInterval(poll);
					show_result(m);
				});
		}

		function show_result(m) {
			d.set_title(__("Student Map — finished"));
			const tile = (n, label, cls) => `<div class="rsm-kpi static ${cls}"><b>${fmt(n)}</b><span>${label}</span></div>`;
			const ok = m.status !== "Failed";
			$b.html(`<div class="rsm-state" style="padding-bottom:20px">
					<i class="fa ${ok ? "fa-check-circle" : "fa-times-circle"}"></i>
					<h4>${ok ? __("Done") : __("The run stopped with an error")}</h4>
					<p>${__("Status")}: ${esc(__(m.status))}</p>${log_links()}</div>
				<div class="rsm-kpis">
					${tile(m.mapped, __("Mapped"), "ok")}
					${tile(m.failed, __("Failed"), "err")}
					${tile(m.already_mapped, __("Already mapped"), "")}
					${tile(m.not_matched, __("Not matched"), "warn")}
					${tile(m.conflicts, __("Conflicts"), "err")}
					${tile(m.skipped, __("Held back"), "warn")}
				</div>`);
			$b.append(`<div class="rsm-tablebox" style="margin-top:4px"><table class="rsm-table">
				<thead><tr><th>${__("Card code")}</th><th></th><th>${__("Student ID")}</th><th>${__("Student name")}</th>
					<th>${__("Email")}</th><th>${__("Result")}</th><th>${__("Note")}</th></tr></thead>
				<tbody><tr class="rsm-empty"><td colspan="7">${__("Loading…")}</td></tr></tbody></table></div>`);
			frappe.db.get_doc(LOG, log_name).then((doc) => {
				const rows = (doc.items || []).filter((r) => ["Mapped", "Failed"].includes(r.status))
					.sort((a, b) => (a.status === "Failed" ? -1 : 0) - (b.status === "Failed" ? -1 : 0));
				$b.find("tbody").html(rows.slice(0, 500).map((r) => `<tr>
					<td><span class="rsm-code">${esc(r.rfid_uid)}</span></td><td class="rsm-arrow">→</td>
					<td>${r.student_id ? `<span class="rsm-sid">${esc(r.student_id)}</span>` : dash}</td>
					<td><b>${esc(r.student_name) || dash}</b></td><td class="rsm-dim">${esc(r.student_email) || dash}</td>
					<td>${slcm.rfid_student_map.status_tag(r.status)}</td><td class="rsm-note">${esc(r.message)}</td></tr>`).join("")
					|| `<tr class="rsm-empty"><td colspan="7">${__("No cards were linked in this run.")}</td></tr>`);
			});
			d.set_primary_action(__("Open log"), () => {
				d.hide();
				frappe.set_route("Form", LOG, log_name);
			});
			d.get_primary_btn().show().prop("disabled", false);
		}
	};
})();

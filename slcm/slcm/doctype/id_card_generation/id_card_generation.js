/* global slcm */
frappe.provide("slcm.id_card");

const IDCG_CSS = `
	.idcg { --b: var(--border-color, #e2e6ea); --m: var(--text-muted, #6b7280); --s: var(--subtle-fg, #f4f5f7); --bg: var(--fg-color, #fff);
		--t: var(--text-color, #1f2937); --a: var(--primary, #2563eb); color: var(--t); display: grid; gap: 16px; }
	.idcg-panel { background: var(--bg); border: 1px solid var(--b); border-radius: 14px; }
	.idcg-hero { display: grid; grid-template-columns: minmax(280px, 440px) minmax(0, 1fr); }
	.idcg-viewer { padding: 22px; background: var(--s); border-radius: 14px 0 0 14px; display: flex; flex-direction: column; align-items: center; gap: 14px; }
	.idcg-stage { position: relative; width: 100%; display: flex; align-items: center; justify-content: center; min-height: 230px; perspective: 1400px; }
	.idcg-flip { position: relative; transition: transform .6s cubic-bezier(.2,.7,.2,1); transform-style: preserve-3d; max-width: 100%; }
	.idcg-flip.flipped { transform: rotateY(180deg); }
	.idcg-face { backface-visibility: hidden; -webkit-backface-visibility: hidden; }
	.idcg-face img { display: block; max-width: 100%; max-height: 300px; border-radius: 12px; box-shadow: 0 1px 2px rgba(0,0,0,.1), 0 14px 34px rgba(15,23,42,.2); }
	.idcg-face.back { position: absolute; inset: 0; transform: rotateY(180deg); display: flex; align-items: center; justify-content: center; }
	.idcg-void img { filter: grayscale(1); opacity: .45; }
	.idcg-stamp { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%) rotate(-12deg); border: 3px solid var(--red-600, #dc2626); z-index: 2;
		color: var(--red-600, #dc2626); font-weight: 700; letter-spacing: .12em; padding: 4px 16px; border-radius: 6px; background: rgba(255,255,255,.9); text-transform: uppercase; }
	.idcg-viewer-tools { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; justify-content: center; }
	.idcg-seg { display: inline-flex; background: var(--bg); border: 1px solid var(--b); border-radius: 9px; padding: 2px; }
	.idcg-seg button { border: 0; background: transparent; color: var(--m); font-size: 12px; padding: 4px 12px; border-radius: 7px; cursor: pointer; }
	.idcg-seg button.active { background: var(--t); color: var(--bg); }
	.idcg-seg button:disabled { opacity: .4; cursor: default; }
	.idcg-placeholder { width: 100%; max-width: 360px; aspect-ratio: 1.586; border: 2px dashed var(--b); border-radius: 14px; display: flex; flex-direction: column;
		align-items: center; justify-content: center; gap: 8px; text-align: center; padding: 20px; color: var(--m); font-size: 13px; background: var(--bg); }
	.idcg-placeholder b { color: var(--t); font-size: 14px; }
	.idcg-placeholder.error { border-color: rgba(220,38,38,.4); }
	.idcg-placeholder.error b { color: var(--red-600, #dc2626); }
	.idcg-spinner { width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--b); border-top-color: var(--a); animation: idcg-spin .8s linear infinite; }
	@keyframes idcg-spin { to { transform: rotate(360deg); } }
	.idcg-info { padding: 22px 24px; display: flex; flex-direction: column; gap: 18px; min-width: 0; }
	.idcg-person { display: flex; gap: 14px; align-items: center; }
	.idcg-avatar { width: 56px; height: 56px; border-radius: 14px; object-fit: cover; flex-shrink: 0; background: var(--s); display: flex; align-items: center;
		justify-content: center; font-weight: 600; font-size: 18px; color: var(--m); }
	.idcg-avatar-btn { position: relative; padding: 0; border: 0; background: none; border-radius: 14px; cursor: pointer; flex-shrink: 0; }
	.idcg-avatar-btn::after { content: attr(data-label); position: absolute; inset: 0; border-radius: 14px; background: rgba(15,23,42,.6); color: #fff;
		font-size: 11px; font-weight: 600; display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity .15s; }
	.idcg-avatar-btn:hover::after, .idcg-avatar-btn:focus-visible::after { opacity: 1; }
	.idcg-avatar.missing { border: 1.5px dashed var(--orange-400, #fb923c); color: var(--orange-600, #ea580c); }
	.idcg-alert-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
	.idcg-person h3 { margin: 0; font-size: 20px; font-weight: 600; letter-spacing: -.01em; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
	.idcg-person-sub { color: var(--m); font-size: 13px; margin-top: 3px; }
	.idcg-person-sub a { color: var(--m); }
	.idcg-person-sub a:hover { color: var(--a); }
	.idcg-track { display: flex; align-items: center; gap: 0; }
	.idcg-track-step { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--m); white-space: nowrap; }
	.idcg-track-dot { width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--b); background: var(--bg); display: flex; align-items: center; justify-content: center; font-size: 11px; }
	.idcg-track-step.done { color: var(--t); }
	.idcg-track-step.done .idcg-track-dot { background: var(--green-500, #22c55e); border-color: var(--green-500, #22c55e); color: #fff; }
	.idcg-track-step.current .idcg-track-dot { border-color: var(--a); box-shadow: 0 0 0 3px rgba(37,99,235,.15); }
	.idcg-track-step.stop .idcg-track-dot { background: var(--red-600, #dc2626); border-color: var(--red-600, #dc2626); color: #fff; }
	.idcg-track-line { flex: 1; min-width: 18px; height: 2px; background: var(--b); margin: 0 10px; }
	.idcg-track-line.done { background: var(--green-500, #22c55e); }
	.idcg-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px 20px; }
	.idcg-fact span { display: block; font-size: 11.5px; color: var(--m); margin-bottom: 3px; }
	.idcg-fact div { font-size: 13.5px; font-weight: 500; overflow-wrap: anywhere; }
	.idcg-fact small { display: block; font-size: 11.5px; font-weight: 400; margin-top: 2px; color: var(--m); }
	.idcg-fact small.warn { color: var(--orange-600, #ea580c); }
	.idcg-fact small.bad { color: var(--red-600, #dc2626); }
	.idcg-fact a { color: var(--t); }
	.idcg-fact a:hover { color: var(--a); }
	.idcg-validity { height: 6px; border-radius: 99px; background: var(--s); overflow: hidden; margin-top: 6px; }
	.idcg-validity > div { height: 100%; border-radius: 99px; background: var(--green-500, #22c55e); }
	.idcg-alerts { display: grid; gap: 8px; }
	.idcg-alert { display: block; padding: 10px 12px; border-radius: 10px; font-size: 12.5px; line-height: 1.45;
		background: var(--s); border: 1px solid var(--b); }
	.idcg-alert b { font-weight: 600; }
	.idcg-alert.warn { background: rgba(234,88,12,.06); border-color: rgba(234,88,12,.3); }
	.idcg-alert.bad { background: rgba(220,38,38,.05); border-color: rgba(220,38,38,.3); }
	.idcg-alert.info { background: rgba(37,99,235,.05); border-color: rgba(37,99,235,.25); }
	.idcg-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: auto; }
	.idcg-panel-head { display: flex; justify-content: space-between; align-items: center; padding: 13px 18px; border-bottom: 1px solid var(--b); }
	.idcg-panel-title { font-weight: 600; font-size: 14px; }
	.idcg-timeline { list-style: none; margin: 0; padding: 14px 18px 6px; }
	.idcg-timeline li { position: relative; padding: 0 0 14px 26px; font-size: 13px; }
	.idcg-timeline li::before { content: ""; position: absolute; left: 6px; top: 14px; bottom: 0; width: 2px; background: var(--b); }
	.idcg-timeline li:last-child::before { display: none; }
	.idcg-tl-dot { position: absolute; left: 0; top: 3px; width: 14px; height: 14px; border-radius: 50%; border: 3px solid var(--bg); box-shadow: 0 0 0 1px var(--b); background: var(--m); }
	.idcg-tl-dot.green { background: var(--green-500, #22c55e); } .idcg-tl-dot.blue { background: var(--blue-500, #3b82f6); }
	.idcg-tl-dot.red { background: var(--red-500, #ef4444); } .idcg-tl-dot.orange { background: var(--orange-500, #f97316); }
	.idcg-tl-when { color: var(--m); font-size: 11.5px; }
	.idcg-empty-note { padding: 18px; color: var(--m); font-size: 13px; text-align: center; }
	@media (max-width: 1000px) {
		.idcg-hero { grid-template-columns: minmax(0, 1fr); }
		.idcg-viewer { border-radius: 14px 14px 0 0; }
		.idcg-facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	}
`;

const IDCG_STATUS_COLOR = {
	Draft: "gray",
	Generated: "blue",
	Printed: "green",
	Cancelled: "red",
	Expired: "orange",
	Error: "red",
};

// Shown in the overview instead; the fields remain the stored record.
const IDCG_HIDDEN_SECTIONS = ["section_break_images", "section_break_history"];

function idcg_person_link(doc) {
	const map = {
		Student: ["Student Master", doc.student],
		Faculty: ["Faculty", doc.faculty],
		Driver: ["SLCM Driver", doc.driver],
	};
	const [doctype, name] = map[doc.card_type] || [];
	return doctype && name
		? { doctype, name, url: `/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}` }
		: null;
}

function idcg_render_preview(frm) {
	if (!document.getElementById("idcg-css"))
		$(`<style id="idcg-css">${IDCG_CSS}</style>`).appendTo("head");
	const field = frm.fields_dict.card_preview;
	if (!field || frm.is_new()) return;
	field.$wrapper.closest(".section-body").css("max-width", "none");

	const doc = frm.doc;
	const esc = frappe.utils.escape_html;
	const status = doc.card_status || "Draft";
	const void_card = ["Cancelled", "Expired"].includes(status);
	const state = (frm.__idcg =
		frm.__idcg && frm.__idcg.name === doc.name
			? frm.__idcg
			: { name: doc.name, side: "front" });
	const front = doc.front_id_image ? frappe.utils.get_file_link(doc.front_id_image) : null;
	const back = doc.back_id_image ? frappe.utils.get_file_link(doc.back_id_image) : null;
	if (!back) state.side = "front";

	// --- Card viewer -------------------------------------------------
	let viewer;
	if (front) {
		viewer = `
			<div class="idcg-stage">
				<div class="idcg-flip ${state.side === "back" ? "flipped" : ""} ${void_card ? "idcg-void" : ""}">
					<div class="idcg-face front"><img src="${esc(front)}" alt="${__("Front")}"></div>
					${back ? `<div class="idcg-face back"><img src="${esc(back)}" alt="${__("Back")}"></div>` : ""}
				</div>
				${void_card ? `<div class="idcg-stamp">${__(status)}</div>` : ""}
			</div>
			<div class="idcg-viewer-tools">
				<div class="idcg-seg">
					<button data-side="front" class="${state.side === "front" ? "active" : ""}">${__("Front")}</button>
					<button data-side="back" class="${state.side === "back" ? "active" : ""}" ${
			back ? "" : "disabled"
		}>${__("Back")}</button>
				</div>
				<a class="btn btn-default btn-xs" data-download href="${esc(
					state.side === "back" && back ? back : front
				)}" download>${__("Download")}</a>
				<a class="btn btn-default btn-xs" data-fullsize href="${esc(
					state.side === "back" && back ? back : front
				)}" target="_blank">${__("Full size")}</a>
			</div>`;
	} else if (status === "Error") {
		viewer = `<div class="idcg-stage"><div class="idcg-placeholder error"><b>${__(
			"Generation failed"
		)}</b>
			<div>${
				frm.__idc_error
					? esc(frm.__idc_error)
					: __("Check the template and the person's details, then generate again.")
			}</div></div></div>`;
	} else if (status === "Draft" && doc.id_card_template && idcg_recent(doc)) {
		viewer = `<div class="idcg-stage"><div class="idcg-placeholder"><div class="idcg-spinner"></div><b>${__(
			"Rendering the card…"
		)}</b>
			<div>${__("This updates by itself in a few seconds.")}</div></div></div>`;
	} else {
		viewer = `<div class="idcg-stage"><div class="idcg-placeholder"><b>${__(
			"Not generated yet"
		)}</b>
			<div>${
				doc.id_card_template
					? __("Generate the card to see it here.")
					: __("Choose an ID Card Template below first.")
			}</div></div></div>`;
	}

	// --- Person ------------------------------------------------------
	const person = idcg_person_link(doc);
	const name = doc.student_name || doc.visitor_name || doc.non_faculty_name || __("Unnamed");
	const initials = name
		.split(/\s+/)
		.map((w) => w[0])
		.slice(0, 2)
		.join("")
		.toUpperCase();
	const photo_card = ["Student", "Faculty", "Driver"].includes(doc.card_type);
	const can_photo = photo_card && !void_card && !!(frm.perm[0] && frm.perm[0].write);
	let avatar = doc.photo
		? `<img class="idcg-avatar" src="${esc(frappe.utils.get_file_link(doc.photo))}" alt="">`
		: `<div class="idcg-avatar ${photo_card ? "missing" : ""}">${esc(initials)}</div>`;
	if (can_photo) {
		const label = doc.photo ? __("Change") : __("Add photo");
		avatar = `<button class="idcg-avatar-btn" data-idcg="photo" data-label="${label}" title="${label}">${avatar}</button>`;
	}
	const sub = [
		person ? `<a href="${person.url}">${esc(person.name)}</a>` : "",
		esc(doc.programme || doc.designation || ""),
		esc(doc.batch || doc.department || doc.visitor_company || ""),
	].filter(Boolean);

	// --- Lifecycle ---------------------------------------------------
	const reached = { Draft: 0, Error: 0, Generated: 1, Printed: 2, Cancelled: -1, Expired: -1 }[
		status
	];
	const steps = [__("Created"), __("Generated"), __("Printed")];
	let track;
	if (reached >= 0) {
		const at = status === "Error" ? 0 : reached;
		track = steps
			.map((label, i) => {
				const cls = i <= at ? "done" : i === at + 1 ? "current" : "";
				const line =
					i < steps.length - 1
						? `<div class="idcg-track-line ${i < at ? "done" : ""}"></div>`
						: "";
				return `<div class="idcg-track-step ${cls}"><div class="idcg-track-dot">${
					i <= at ? "✓" : ""
				}</div>${label}</div>${line}`;
			})
			.join("");
	} else {
		track = `<div class="idcg-track-step done"><div class="idcg-track-dot">✓</div>${__(
			"Issued"
		)}</div>
			<div class="idcg-track-line done"></div>
			<div class="idcg-track-step stop"><div class="idcg-track-dot">✕</div>${__(status)}</div>`;
	}

	// --- Facts -------------------------------------------------------
	const today = frappe.datetime.get_today();
	let validity = "";
	let validity_bar = "";
	if (doc.expiry_date) {
		const left = frappe.datetime.get_day_diff(doc.expiry_date, today);
		const cls = left < 0 ? "bad" : left <= 30 ? "warn" : "";
		validity =
			left < 0
				? __("Expired {0} day(s) ago", [-left])
				: left === 0
				? __("Expires today")
				: __("{0} day(s) left", [left]);
		validity = `<small class="${cls}">${validity}</small>`;
		if (doc.issue_date) {
			const span = Math.max(
				frappe.datetime.get_day_diff(doc.expiry_date, doc.issue_date),
				1
			);
			const used = Math.min(
				Math.max(frappe.datetime.get_day_diff(today, doc.issue_date), 0),
				span
			);
			const pct = Math.round((used / span) * 100);
			const color =
				left < 0
					? "var(--red-500,#ef4444)"
					: left <= 30
					? "var(--orange-500,#f97316)"
					: "";
			validity_bar = `<div class="idcg-validity"><div style="width:${pct}%;${
				color ? `background:${color}` : ""
			}"></div></div>`;
		}
	}
	const fact = (label, value, extra = "") =>
		`<div class="idcg-fact"><span>${label}</span><div>${value}${extra}</div></div>`;
	const last_print = frm.__idcg_prints && frm.__idcg_prints[0];
	const facts = [
		fact(__("Card number"), esc(doc.name)),
		fact(__("Card type"), esc(__(doc.card_type || ""))),
		fact(
			__("Template"),
			doc.id_card_template
				? `<a href="/app/id-card-template/${encodeURIComponent(
						doc.id_card_template
				  )}">${esc(doc.id_card_template)}</a>`
				: "—"
		),
		fact(__("Issued"), doc.issue_date ? frappe.datetime.str_to_user(doc.issue_date) : "—"),
		fact(
			__("Valid till"),
			doc.expiry_date ? frappe.datetime.str_to_user(doc.expiry_date) : "—",
			validity + validity_bar
		),
		fact(
			__("Printed"),
			doc.print_count ? __("{0} time(s)", [doc.print_count]) : __("Not yet"),
			last_print
				? `<small>${__("Last {0}", [
						frappe.datetime.comment_when(last_print.printed_on),
				  ])}</small>`
				: ""
		),
	].join("");

	// --- Alerts ------------------------------------------------------
	const alerts = [];
	if (status === "Cancelled" && doc.cancellation_reason) {
		alerts.push(["bad", `<b>${__("Cancelled.")}</b> ${esc(doc.cancellation_reason)}`]);
	}
	const reissued = /Reissued from (\S+)/.exec(doc.remarks || "");
	if (reissued) {
		alerts.push([
			"info",
			`${__("Replacement for")} <a href="/app/id-card-generation/${encodeURIComponent(
				reissued[1].replace(/\.$/, "")
			)}">${esc(reissued[1].replace(/\.$/, ""))}</a>. ${esc(
				(doc.remarks.split("Reason:")[1] || "").trim()
			)}`,
		]);
	}
	if (!doc.photo && photo_card && !void_card) {
		const person_photo = frm.__idcg_person_photo;
		const source = person ? __(person.doctype) : "";
		alerts.push([
			"warn",
			`<b>${__("No photo.")}</b> ${
				person_photo
					? __("{0} has a photo, but this card isn't using it yet.", [source])
					: __("The default avatar is printed on this card.")
			}
			${
				can_photo
					? `<div class="idcg-alert-actions">
						${
							person_photo
								? `<button class="btn btn-primary btn-xs" data-idcg="person-photo">${__(
										"Use photo from {0}",
										[source]
								  )}</button>`
								: ""
						}
						<button class="btn ${person_photo ? "btn-default" : "btn-primary"} btn-xs" data-idcg="photo">${__(
							"Upload photo"
					  )}</button>
					</div>`
					: ""
			}`,
		]);
	}
	if (frm.__idcg_newer) {
		alerts.push([
			"info",
			`${__(
				"A newer card exists for this person:"
			)} <a href="/app/id-card-generation/${encodeURIComponent(frm.__idcg_newer)}">${esc(
				frm.__idcg_newer
			)}</a>`,
		]);
	}

	// --- Actions -----------------------------------------------------
	const actions = [];
	if (["Draft", "Error"].includes(status))
		actions.push(
			`<button class="btn btn-primary btn-sm" data-idcg="generate">${__(
				"Generate card"
			)}</button>`
		);
	if (front && ["Generated", "Printed"].includes(status)) {
		actions.push(
			`<button class="btn btn-primary btn-sm" data-idcg="print">${__("Print card")}</button>`
		);
		actions.push(
			`<button class="btn btn-default btn-sm" data-idcg="regenerate">${__(
				"Regenerate"
			)}</button>`
		);
		actions.push(
			`<button class="btn btn-default btn-sm" data-idcg="reissue">${__(
				"Lost or damaged? Reissue"
			)}</button>`
		);
	}
	if (person)
		actions.push(
			`<a class="btn btn-default btn-sm" href="${person.url}">${__("Open {0}", [
				__(person.doctype),
			])}</a>`
		);

	// --- Timeline ----------------------------------------------------
	const items = [
		{
			when: doc.creation,
			color: "",
			text: __("Card created by {0}", [esc(frappe.user.full_name(doc.owner))]),
		},
	];
	(doc.events || []).forEach((e) => {
		const color =
			{
				Generated: "blue",
				Printed: "green",
				Cancelled: "red",
				Expired: "orange",
				Error: "red",
			}[e.card_status] || "";
		items.push({
			when: e.timestamp,
			color,
			text: __("Status changed to <b>{0}</b> by {1}", [
				esc(__(e.card_status || "")),
				esc(frappe.user.full_name(e.user)),
			]),
		});
	});
	(frm.__idcg_prints || []).forEach((p) => {
		items.push({
			when: p.printed_on,
			color: "green",
			text: __("{0} print ({1}) by {2}", [
				esc(__(p.print_type || "")),
				esc(__(p.print_action_type || p.print_layout || "")),
				esc(frappe.user.full_name(p.printed_by)),
			]),
		});
	});
	items.sort((a, b) => (b.when || "").localeCompare(a.when || ""));
	const timeline = items
		.map(
			(i) => `<li><span class="idcg-tl-dot ${i.color}"></span><div>${i.text}</div>
			<div class="idcg-tl-when">${
				i.when
					? `${frappe.datetime.str_to_user(i.when)} · ${frappe.datetime.comment_when(
							i.when
					  )}`
					: ""
			}</div></li>`
		)
		.join("");

	field.$wrapper.html(`
		<div class="idcg">
			<section class="idcg-panel idcg-hero">
				<div class="idcg-viewer">${viewer}</div>
				<div class="idcg-info">
					<div class="idcg-person">${avatar}
						<div style="min-width:0">
							<h3>${esc(name)} <span class="indicator-pill ${IDCG_STATUS_COLOR[status] || "gray"}">${__(
		status
	)}</span></h3>
							<div class="idcg-person-sub">${sub.join(" · ")}</div>
						</div>
					</div>
					<div class="idcg-track">${track}</div>
					<div class="idcg-facts">${facts}</div>
					${
						alerts.length
							? `<div class="idcg-alerts">${alerts
									.map(([c, t]) => `<div class="idcg-alert ${c}">${t}</div>`)
									.join("")}</div>`
							: ""
					}
					${actions.length ? `<div class="idcg-actions">${actions.join("")}</div>` : ""}
				</div>
			</section>
			<section class="idcg-panel">
				<div class="idcg-panel-head"><div class="idcg-panel-title">${__("Activity")}</div>
					<span class="text-muted small">${
						frm.__idcg_prints ? __("{0} print(s)", [frm.__idcg_prints.length]) : ""
					}</span></div>
				<ul class="idcg-timeline">${timeline}</ul>
			</section>
		</div>`);

	const $w = field.$wrapper;
	$w.find("[data-side]").on("click", (e) => {
		state.side = $(e.currentTarget).data("side");
		$w.find(".idcg-flip").toggleClass("flipped", state.side === "back");
		$w.find("[data-side]").each((_, b) =>
			$(b).toggleClass("active", $(b).data("side") === state.side)
		);
		const url = state.side === "back" && back ? back : front;
		$w.find("[data-download], [data-fullsize]").attr("href", url);
	});
	$w.find("[data-idcg]").on("click", (e) => {
		const act = $(e.currentTarget).data("idcg");
		if (act === "generate") idcg_generate(frm);
		if (act === "print") idcg_print(frm);
		if (act === "regenerate") idcg_regenerate(frm);
		if (act === "reissue") idcg_reissue(frm);
		if (act === "photo") idcg_upload_photo(frm);
		if (act === "person-photo") idcg_use_person_photo(frm);
	});
}

function idcg_load_extras(frm) {
	if (frm.is_new()) return;
	const name = frm.doc.name;
	const link = idcg_person_link(frm.doc);
	Promise.all([
		frappe
			.xcall("slcm.slcm.doctype.id_card_print_log.id_card_print_log.get_print_history", {
				doctype: "ID Card Generation",
				name,
			})
			.catch(() => []),
		link && ["Cancelled", "Expired"].includes(frm.doc.card_status)
			? frappe.db.get_value(
					"ID Card Generation",
					{
						[{ Student: "student", Faculty: "faculty", Driver: "driver" }[
							frm.doc.card_type
						]]: link.name,
						card_status: ["not in", ["Cancelled", "Expired"]],
					},
					"name"
			  )
			: Promise.resolve(null),
		link && IDCG_PERSON_PHOTO[frm.doc.card_type]
			? frappe.db.get_value(link.doctype, link.name, IDCG_PERSON_PHOTO[frm.doc.card_type])
			: Promise.resolve(null),
	])
		.then(([prints, newer, person]) => {
			if (frm.doc.name !== name) return;
			frm.__idcg_extras_for = name;
			frm.__idcg_prints = prints || [];
			frm.__idcg_newer = (newer && newer.message && newer.message.name) || null;
			frm.__idcg_person_photo =
				(person &&
					person.message &&
					person.message[IDCG_PERSON_PHOTO[frm.doc.card_type]]) ||
				null;
			idcg_render_preview(frm);
		})
		.catch(() => {});
}

// Photo field on each person doctype (mirrors PERSON_PHOTO_FIELDS on the server).
const IDCG_PERSON_PHOTO = { Student: "passport_size_photo", Faculty: "photo", Driver: "photo" };

function idcg_save_photo(frm, file_url, update_person, regenerate) {
	const go = () =>
		frm
			.call({
				doc: frm.doc,
				method: "update_photo",
				args: {
					file_url: file_url || null,
					update_person: update_person ? 1 : 0,
					regenerate: regenerate ? 1 : 0,
				},
				freeze: true,
				freeze_message: regenerate
					? __("Saving the photo and re-rendering the card…")
					: __("Saving the photo…"),
			})
			.then((r) => {
				if (r.exc) return;
				frm.reload_doc();
				frappe.show_alert({
					message:
						r.message && r.message.regenerated
							? __("Photo saved and card regenerated.")
							: __("Photo saved."),
					indicator: "green",
				});
			});
	if (frm.is_dirty()) frm.save().then(go);
	else go();
}

function idcg_upload_photo(frm) {
	const person = idcg_person_link(frm.doc);
	const fields = [
		{
			fieldtype: "Attach Image",
			fieldname: "photo",
			label: __("Photo"),
			reqd: 1,
			description: __("A clear, front-facing passport-style photo prints best."),
		},
	];
	if (person) {
		fields.push({
			fieldtype: "Check",
			fieldname: "update_person",
			label: __("Also save it on {0} {1}", [__(person.doctype), person.name]),
			description: __("Future cards for this person will use it too."),
			default: frm.__idcg_person_photo ? 0 : 1,
		});
	}
	if (frm.doc.id_card_template) {
		fields.push({
			fieldtype: "Check",
			fieldname: "regenerate",
			label: __("Regenerate the card now"),
			default: 1,
		});
	}
	const d = new frappe.ui.Dialog({
		title: frm.doc.photo ? __("Change photo") : __("Add photo"),
		fields,
		primary_action_label: __("Save photo"),
		primary_action(values) {
			d.hide();
			idcg_save_photo(frm, values.photo, values.update_person, values.regenerate);
		},
	});
	d.show();
}

function idcg_use_person_photo(frm) {
	const person = idcg_person_link(frm.doc);
	frappe.confirm(
		__("Use the photo from {0} {1} and regenerate the card?", [
			__(person.doctype),
			person.name,
		]),
		() => idcg_save_photo(frm, null, 0, !!frm.doc.id_card_template)
	);
}

function idcg_regenerate(frm) {
	frappe.confirm(__("Re-render this card with the current template and details?"), () =>
		idcg_generate(frm)
	);
}

function idcg_cancel(frm) {
	frappe.prompt(
		{
			label: __("Reason for Cancellation"),
			fieldname: "reason",
			fieldtype: "Small Text",
			reqd: 1,
		},
		(values) => {
			frm.call({
				doc: frm.doc,
				method: "cancel_card",
				args: { reason: values.reason },
			}).then((r) => {
				if (!r.exc) {
					frm.reload_doc();
					frappe.show_alert({ message: __("Card cancelled."), indicator: "orange" });
				}
			});
		},
		__("Cancel ID Card"),
		__("Confirm Cancellation")
	);
}

function idcg_reissue(frm) {
	frappe.prompt(
		{
			label: __("Reason for Reissue (e.g. Lost, Damaged)"),
			fieldname: "reason",
			fieldtype: "Small Text",
			reqd: 1,
		},
		(values) => {
			frm.call({
				doc: frm.doc,
				method: "reissue_card",
				args: { reason: values.reason },
				freeze: true,
				freeze_message: __("Creating replacement card…"),
			}).then((r) => {
				if (!r.exc && r.message) frappe.set_route("Form", "ID Card Generation", r.message);
			});
		},
		__("Reissue ID Card"),
		__("Confirm Reissue")
	);
}

function idcg_recent(doc) {
	const created = frappe.datetime.str_to_obj(doc.creation);
	return created && Date.now() - created.getTime() < 3 * 60 * 1000;
}

async function idcg_ensure_template(frm) {
	const card_type = frm.doc.card_type || "Student";
	if (frm.doc.id_card_template) {
		const r = await frappe.db.get_value(
			"ID Card Template",
			frm.doc.id_card_template,
			"card_type"
		);
		if (r.message && r.message.card_type === card_type) return;
	}
	const r = await frappe.db.get_value("ID Card Template", { card_type, is_default: 1 }, "name");
	frm.set_value("id_card_template", (r.message && r.message.name) || null);
}

function idcg_generate(frm) {
	const run = () =>
		frm
			.call({
				doc: frm.doc,
				method: "generate_card",
				freeze: true,
				freeze_message: __("Rendering the card…"),
			})
			.then((r) => {
				if (r.exc) return;
				frm.__idc_error = null;
				frm.reload_doc();
				frappe.show_alert({ message: __("ID card generated."), indicator: "green" });
			});
	if (!frm.doc.id_card_template) {
		frappe.msgprint({
			title: __("Missing Template"),
			message: __("Choose an ID Card Template first."),
			indicator: "orange",
		});
		return;
	}
	if (frm.is_dirty()) {
		frm.save().then(() => idcg_generate(frm));
		return;
	}
	if (!frm.doc.photo && ["Student", "Faculty", "Driver"].includes(frm.doc.card_type)) {
		frappe.confirm(
			__(
				"This person has no photo. The default avatar will be printed on the card. Continue?"
			),
			run
		);
		return;
	}
	run();
}

const IDCG_PRINT_CSS = `
	.idcp-preview { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; padding: 18px; border-radius: 12px; background: var(--subtle-fg, #f4f5f7); }
	.idcp-side { text-align: center; }
	.idcp-side img { display: block; max-height: 190px; max-width: 300px; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,.1), 0 8px 22px rgba(15,23,42,.16); }
	.idcp-side.off img { opacity: .25; filter: grayscale(1); }
	.idcp-side span { display: block; margin-top: 8px; font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted, #6b7280); }
	.idcp-label { font-size: 12px; font-weight: 600; color: var(--text-muted, #6b7280); margin: 18px 0 8px; }
	.idcp-printers { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
	.idcp-opt { position: relative; border: 2px solid var(--border-color, #e2e6ea); border-radius: 12px; padding: 12px 14px; cursor: pointer; background: var(--fg-color, #fff); }
	.idcp-opt:hover { border-color: var(--gray-400, #9ca3af); }
	.idcp-opt.on { border-color: var(--text-color, #1f2937); background: var(--subtle-fg, #f4f5f7); }
	.idcp-opt b { display: block; font-size: 13.5px; }
	.idcp-opt small { display: block; color: var(--text-muted, #6b7280); font-size: 12px; margin-top: 3px; line-height: 1.4; }
	.idcp-radio { position: absolute; top: 12px; right: 12px; width: 18px; height: 18px; border-radius: 50%; border: 2px solid var(--border-color, #cbd2d9); }
	.idcp-opt.on .idcp-radio { border: 5px solid var(--text-color, #1f2937); }
	.idcp-row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
	.idcp-chip { display: inline-flex; align-items: center; gap: 8px; padding: 7px 12px; border: 1px solid var(--border-color, #e2e6ea); border-radius: 9px;
		font-size: 13px; cursor: pointer; margin: 0; font-weight: 400; }
	.idcp-chip input { margin: 0; width: 15px; height: 15px; }
	.idcp-chip.disabled { opacity: .45; cursor: default; }
	.idcp-note { margin-top: 14px; padding: 10px 12px; border-radius: 10px; background: var(--subtle-fg, #f4f5f7); font-size: 12.5px; color: var(--text-muted, #6b7280); line-height: 1.5; }
	.idcp-note b { color: var(--text-color, #1f2937); }
`;

const idcg_full_url = (u) => frappe.urllib.get_full_url(frappe.utils.get_file_link(u));

/** Load an image and report its natural size (null when it fails). */
function idcg_probe(url) {
	return new Promise((resolve) => {
		if (!url) return resolve(null);
		const img = new Image();
		img.onload = () => resolve({ url, width: img.naturalWidth, height: img.naturalHeight });
		img.onerror = () => resolve(null);
		img.src = url;
	});
}

/** Printable HTML for the chosen printer. Card sizes are true CR80 (85.6 x 54 mm). */
function idcg_print_html(frm, sides, printer) {
	const esc = frappe.utils.escape_html;
	const portrait = sides[0].height > sides[0].width;
	const [w, h] = portrait ? [54, 85.6] : [85.6, 54];
	const title = esc(`${frm.doc.student_name || frm.doc.name} · ${frm.doc.name}`);

	if (printer === "card") {
		return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${title}</title><style>
			@page { size: ${w}mm ${h}mm; margin: 0; }
			html, body { margin: 0; padding: 0; background: #fff; }
			.page { width: ${w}mm; height: ${h}mm; overflow: hidden; break-after: page; page-break-after: always; }
			.page:last-child { break-after: auto; page-break-after: auto; }
			img { display: block; width: 100%; height: 100%; object-fit: cover; }
		</style></head><body>${sides
			.map((s) => `<div class="page"><img src="${esc(s.url)}" alt=""></div>`)
			.join("")}</body></html>`;
	}

	// Office printer: A4 with the card(s) at true size and crop marks for cutting.
	const mark = (style) => `<i style="${style}"></i>`;
	const marks = [
		"left:-7mm;top:0;width:5mm;height:0;border-top:.2mm solid #888",
		"left:-7mm;bottom:0;width:5mm;height:0;border-top:.2mm solid #888",
		"right:-7mm;top:0;width:5mm;height:0;border-top:.2mm solid #888",
		"right:-7mm;bottom:0;width:5mm;height:0;border-top:.2mm solid #888",
		"top:-7mm;left:0;height:5mm;width:0;border-left:.2mm solid #888",
		"top:-7mm;right:0;height:5mm;width:0;border-left:.2mm solid #888",
		"bottom:-7mm;left:0;height:5mm;width:0;border-left:.2mm solid #888",
		"bottom:-7mm;right:0;height:5mm;width:0;border-left:.2mm solid #888",
	]
		.map(mark)
		.join("");
	return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${title}</title><style>
		@page { size: A4; margin: 15mm; }
		html, body { margin: 0; padding: 0; background: #fff; font-family: Arial, Helvetica, sans-serif; color: #444; }
		.sheet { display: flex; flex-wrap: wrap; justify-content: center; gap: 18mm; padding-top: 20mm; }
		.cell { text-align: center; }
		.card { position: relative; width: ${w}mm; height: ${h}mm; }
		.card img { display: block; width: 100%; height: 100%; object-fit: cover; }
		.card i { position: absolute; }
		.cap { margin-top: 9mm; font-size: 8pt; letter-spacing: .08em; text-transform: uppercase; color: #888; }
		.foot { margin-top: 18mm; text-align: center; font-size: 8pt; color: #999; }
	</style></head><body>
		<div class="sheet">${sides
			.map(
				(s) =>
					`<div class="cell"><div class="card"><img src="${esc(
						s.url
					)}" alt="">${marks}</div><div class="cap">${s.label}</div></div>`
			)
			.join("")}</div>
		<div class="foot">${title} · ${__("Printed at 100% scale. Cut along the marks.")}</div>
	</body></html>`;
}

/** Print an HTML document through a hidden iframe (no pop-up to block). */
function idcg_print_frame(html) {
	return new Promise((resolve) => {
		const frame = document.createElement("iframe");
		frame.setAttribute("aria-hidden", "true");
		frame.style.cssText =
			"position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
		document.body.appendChild(frame);
		const win = frame.contentWindow;
		win.document.open();
		win.document.write(html);
		win.document.close();
		const images = [...win.document.images];
		Promise.all(
			images.map((img) =>
				img.complete ? null : new Promise((r) => (img.onload = img.onerror = r))
			)
		).then(() => {
			const cleanup = () => {
				setTimeout(() => frame.remove(), 500);
				resolve();
			};
			win.addEventListener("afterprint", cleanup, { once: true });
			win.focus();
			win.print();
			// Some browsers never fire afterprint; don't leave the frame behind.
			setTimeout(cleanup, 120000);
		});
	});
}

function idcg_saved_printer() {
	try {
		return localStorage.getItem("slcm_idcard_printer") === "a4" ? "a4" : "card";
	} catch (e) {
		return "card";
	}
}

async function idcg_print(frm) {
	if (!document.getElementById("idcg-print-css"))
		$(`<style id="idcg-print-css">${IDCG_PRINT_CSS}</style>`).appendTo("head");
	const loaded = await Promise.all([
		idcg_probe(frm.doc.front_id_image && idcg_full_url(frm.doc.front_id_image)),
		idcg_probe(frm.doc.back_id_image && idcg_full_url(frm.doc.back_id_image)),
	]);
	const sides = [
		{ key: "front", label: __("Front"), ...(loaded[0] || {}) },
		{ key: "back", label: __("Back"), ...(loaded[1] || {}) },
	].filter((s) => s.url);
	if (!sides.length) {
		frappe.msgprint(
			__("The card images could not be loaded. Regenerate the card and try again.")
		);
		return;
	}

	const state = {
		printer: idcg_saved_printer(),
		sides: new Set(sides.map((s) => s.key)),
		mark: frm.doc.card_status === "Generated",
	};
	const reprint = (frm.doc.print_count || 0) > 0;
	const d = new frappe.ui.Dialog({
		title: reprint ? __("Reprint ID card") : __("Print ID card"),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "body" }],
		primary_action_label: __("Print"),
		primary_action() {
			const chosen = sides.filter((s) => state.sides.has(s.key));
			if (!chosen.length) return;
			try {
				localStorage.setItem("slcm_idcard_printer", state.printer);
			} catch (e) {
				// Private mode: just don't remember the choice.
			}
			d.hide();
			frm.call({
				doc: frm.doc,
				method: "log_print",
				args: { layout: "Single", mark_printed: state.mark ? 1 : 0 },
			}).then((r) => {
				if (r.exc) return;
				idcg_print_frame(idcg_print_html(frm, chosen, state.printer)).then(() =>
					frm.reload_doc()
				);
			});
		},
	});

	const esc = frappe.utils.escape_html;
	const render = () => {
		const opt = (key, title, sub) => `<div class="idcp-opt ${
			state.printer === key ? "on" : ""
		}" data-printer="${key}" role="radio"
			aria-checked="${
				state.printer === key
			}" tabindex="0"><span class="idcp-radio"></span><b>${title}</b><small>${sub}</small></div>`;
		d.fields_dict.body.$wrapper.html(`
			<div class="idcp-preview">${["front", "back"]
				.map((key) => {
					const s = sides.find((x) => x.key === key);
					return s
						? `<div class="idcp-side ${
								state.sides.has(key) ? "" : "off"
						  }"><img src="${esc(s.url)}" alt=""><span>${s.label}</span></div>`
						: "";
				})
				.join("")}</div>
			<div class="idcp-label">${__("Printer")}</div>
			<div class="idcp-printers">
				${opt(
					"card",
					__("ID card printer"),
					__(
						"Each side on its own card-sized page (CR80, 85.6 × 54 mm). Turn on duplex for front and back."
					)
				)}
				${opt(
					"a4",
					__("Office printer (A4)"),
					__("Card at true size on A4 with crop marks, ready to cut and laminate.")
				)}
			</div>
			<div class="idcp-label">${__("Sides")}</div>
			<div class="idcp-row">
				${["front", "back"]
					.map((key) => {
						const s = sides.find((x) => x.key === key);
						const label = key === "front" ? __("Front") : __("Back");
						return `<label class="idcp-chip ${
							s ? "" : "disabled"
						}"><input type="checkbox" data-side-pick="${key}" ${
							state.sides.has(key) ? "checked" : ""
						} ${s ? "" : "disabled"}> ${label}${s ? "" : ` (${__("none")})`}</label>`;
					})
					.join("")}
				${
					frm.doc.card_status === "Generated"
						? `<label class="idcp-chip" style="margin-left:auto"><input type="checkbox" data-mark ${
								state.mark ? "checked" : ""
						  }> ${__("Mark card as Printed")}</label>`
						: ""
				}
			</div>
			<div class="idcp-note">${
				state.printer === "card"
					? __(
							"In the print window choose your card printer, set the paper size to <b>CR80</b> and margins to <b>None</b>."
					  )
					: __(
							"In the print window choose <b>A4</b>, scale <b>100% / Actual size</b> and margins <b>Default</b>. “Fit to page” shrinks the card."
					  )
			}${
			reprint
				? ` ${__("This is reprint #{0}; it is recorded in the ID Card Print Log.", [
						(frm.doc.print_count || 0) + 1,
				  ])}`
				: ""
		}</div>`);
		d.get_primary_btn()
			.prop("disabled", !state.sides.size)
			.text(
				state.sides.size === 2
					? __("Print both sides")
					: state.sides.size
					? __("Print {0}", [state.sides.has("front") ? __("front") : __("back")])
					: __("Choose a side")
			);
	};
	const $b = d.fields_dict.body.$wrapper;
	$b.on("click keydown", "[data-printer]", (e) => {
		if (e.type === "keydown" && e.key !== " " && e.key !== "Enter") return;
		e.preventDefault();
		state.printer = $(e.currentTarget).data("printer");
		render();
	});
	$b.on("change", "[data-side-pick]", (e) => {
		const key = $(e.currentTarget).data("side-pick");
		if (e.currentTarget.checked) state.sides.add(key);
		else state.sides.delete(key);
		render();
	});
	$b.on("change", "[data-mark]", (e) => (state.mark = e.currentTarget.checked));
	d.show();
	render();
}

frappe.ui.form.on("ID Card Generation", {
	setup(frm) {
		frm.set_query("id_card_template", () => ({
			filters: { card_type: frm.doc.card_type || "Student" },
		}));
	},

	onload(frm) {
		if (!slcm.id_card._generation_listener) {
			slcm.id_card._generation_listener = true;
			frappe.realtime.on("id_card_generated", (data) => {
				const f = window.cur_frm;
				if (!f || f.doctype !== data.doctype || f.docname !== data.name) return;
				f.__idc_error = data.error;
				if (f.is_dirty()) {
					frappe.show_alert({
						message: __("The card was rendered. Reload to see it."),
						indicator: "blue",
					});
				} else {
					f.reload_doc();
				}
			});
		}
		if (frm.is_new() && !frm.doc.id_card_template) idcg_ensure_template(frm);
		if (frm.is_new() && frm.doc.student && !frm.doc.student_name) frm.trigger("student");
	},

	refresh(frm) {
		frm.toggle_display(IDCG_HIDDEN_SECTIONS, frm.is_new());
		if (frm.__idcg_extras_for !== frm.doc.name) {
			frm.__idcg_prints = null;
			frm.__idcg_newer = null;
			frm.__idcg_person_photo = null;
		}
		idcg_render_preview(frm);
		if (frm.is_new()) return;
		idcg_load_extras(frm);

		const status = frm.doc.card_status;
		if (["Draft", "Error"].includes(status)) {
			frm.page.set_primary_action(__("Generate Card"), () => idcg_generate(frm));
		}
		if (frm.doc.front_id_image && ["Generated", "Printed"].includes(status)) {
			frm.page.set_primary_action(__("Print Card"), () => idcg_print(frm));
			frm.add_custom_button(__("Regenerate"), () => idcg_regenerate(frm), __("Actions"));
		}
		if (["Generated", "Printed"].includes(status)) {
			frm.add_custom_button(__("Reissue Card"), () => idcg_reissue(frm), __("Actions"));
		}
		if (!["Cancelled", "Expired"].includes(status)) {
			frm.add_custom_button(__("Cancel Card"), () => idcg_cancel(frm), __("Actions"));
		}

		if (frm.doc.qr_code_image) {
			frm.set_df_property(
				"qr_code_preview",
				"options",
				`<img src="${frappe.utils.escape_html(
					frappe.utils.get_file_link(frm.doc.qr_code_image)
				)}" style="width:140px;border:1px solid var(--border-color);border-radius:8px;padding:6px;background:#fff">`
			);
		} else {
			frm.set_df_property("qr_code_preview", "options", "");
		}
	},

	card_type(frm) {
		const series = {
			Student: "STU-.#####",
			Faculty: "FAC-.#####",
			Driver: "DRV-.#####",
			Visitor: "VIS-.#####",
			"Non-Faculty": "STF-.#####",
		};
		if (series[frm.doc.card_type]) frm.set_value("naming_series", series[frm.doc.card_type]);
		[
			"student",
			"faculty",
			"driver",
			"visitor_name",
			"non_faculty_name",
			"designation",
			"department",
			"batch",
			"programme",
			"photo",
			"student_name",
		].forEach((f) => frm.set_value(f, null));
		idcg_ensure_template(frm);
	},

	student(frm) {
		if (!frm.doc.student) return;
		frappe.db
			.get_value("Student Master", frm.doc.student, [
				"first_name",
				"email",
				"phone",
				"passport_size_photo",
				"batch",
				"programme_of_study",
				"dob",
				"academic_year",
			])
			.then((r) => {
				const s = r.message || {};
				frm.set_value({
					student_name: s.first_name || "",
					email: s.email || "",
					phone: s.phone || "",
					photo: s.passport_size_photo || "",
					batch: s.batch || "",
					programme: s.programme_of_study || "",
					date_of_birth: s.dob || "",
					academic_year: s.academic_year || "",
				});
			});
		frappe
			.xcall("slcm.slcm.doctype.id_card_generation.id_card_generation.get_default_expiry", {
				student: frm.doc.student,
			})
			.then((expiry) => {
				if (expiry && frm.is_new()) frm.set_value("expiry_date", expiry);
			});
	},

	faculty(frm) {
		if (!frm.doc.faculty) return;
		frappe.db.get_doc("Faculty", frm.doc.faculty).then((doc) => {
			frm.set_value({
				student_name: `${doc.first_name || ""} ${doc.last_name || ""}`.trim(),
				email: doc.email,
				phone: doc.phone,
				department: doc.department,
				photo: doc.photo,
				designation: doc.designation,
			});
		});
	},

	driver(frm) {
		if (!frm.doc.driver) return;
		frappe.db.get_doc("SLCM Driver", frm.doc.driver).then((doc) => {
			frm.set_value({
				student_name: doc.driver_name,
				phone: doc.phone,
				photo: doc.photo,
				designation: "Driver",
			});
		});
	},
});

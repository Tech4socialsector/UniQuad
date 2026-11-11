// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

// Taking RFID cards off students: the shared "why" dialog and result message used by
// RFID Card Management, the Student Map Log and the Student Master list.
// Server side: slcm.slcm.utils.rfid_cards.unmap_card.

frappe.provide("slcm.rfid_unmap");

slcm.rfid_unmap.REASONS = [
	{
		value: "Wrong student",
		label: __("Given to the wrong student"),
		help: __("Undoes the link completely. The card's past swipes go back to Unassigned and the card can be given to the right student."),
	},
	{
		value: "Lost",
		label: __("Lost"),
		help: __("Keeps the card history and past attendance. The card stops counting and cannot be given to anyone else."),
	},
	{
		value: "Damaged",
		label: __("Damaged"),
		help: __("Keeps the card history and past attendance. The card stops counting and cannot be given to anyone else."),
	},
	{
		value: "Blocked",
		label: __("Blocked (student left, card withdrawn)"),
		help: __("Keeps the card history and past attendance. The card stops counting and cannot be given to anyone else."),
	},
];

// ask({ what: "3 students", on_confirm(reason) })
slcm.rfid_unmap.ask = function ({ what, on_confirm }) {
	const by_value = Object.fromEntries(slcm.rfid_unmap.REASONS.map((r) => [r.value, r]));
	const d = new frappe.ui.Dialog({
		title: __("Remove RFID card"),
		fields: [
			{ fieldname: "intro", fieldtype: "HTML",
			  options: `<p>${__("Remove the card from {0}.", [`<b>${frappe.utils.escape_html(what)}</b>`])}</p>` },
			{ fieldname: "reason", fieldtype: "Select", label: __("Why"), reqd: 1,
			  options: [{ value: "", label: "" }].concat(slcm.rfid_unmap.REASONS.map((r) => ({ value: r.value, label: r.label }))) },
			{ fieldname: "help", fieldtype: "HTML" },
		],
		primary_action_label: __("Remove card"),
		primary_action(values) {
			if (!values.reason) return;
			d.hide();
			on_confirm(values.reason);
		},
	});
	const show_help = () => {
		const r = by_value[d.get_value("reason")];
		d.fields_dict.help.$wrapper.html(r ? `<div class="text-muted small">${r.help}</div>` : "");
	};
	d.fields_dict.reason.$input.on("change", show_help);
	d.show();
	d.get_primary_btn().addClass("btn-danger");
};

// results: [{ ok, message }] from unmap_cards / unmap_rows
slcm.rfid_unmap.show_results = function (results) {
	const esc = (s) => frappe.utils.escape_html(String(s || ""));
	const ok = (results || []).filter((r) => r.ok), bad = (results || []).filter((r) => !r.ok);
	if (!bad.length) {
		frappe.show_alert({ message: __("{0} card(s) removed", [ok.length]), indicator: "green" }, 6);
		return;
	}
	frappe.msgprint({
		title: __("Remove RFID card"),
		indicator: ok.length ? "orange" : "red",
		message: `<p><b>${__("{0} removed", [ok.length])}</b>, <b style="color:var(--red-600)">${__("{0} not removed", [bad.length])}</b></p>
			<ul>${bad.map((r) => `<li>${esc(r.message)}</li>`).join("")}</ul>`,
	});
};

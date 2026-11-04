// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bulk Fee Structure Update", {

	refresh(frm) {
		$(".layout-side-section").hide();
		frm.disable_save();

		if (frm.doc.status === "Applied") {
			frm.set_intro(
				__("This bulk update (") + frm.doc.name + __(") has been applied successfully. " +
				frm.doc.success_count + " student(s) updated. It cannot be modified."),
				"green"
			);
			_render_status_banner(frm);
			return;
		}

		_render_status_banner(frm);

		// ── Preview Impact ──────────────────────────────────────────
		const prev_btn = frm.add_custom_button(__("Preview Impact"), () => _run_preview(frm));
		prev_btn.addClass("btn-primary").css({
			"background-color": "#1a3c6e", "color": "#fff",
			"border-color": "#1a3c6e", "font-weight": "600",
		});

		// ── Apply (only when Previewed + has rows) ──────────────────
		if (frm.doc.status === "Previewed" && (frm.doc.affected_students || []).length > 0) {
			const apply_btn = frm.add_custom_button(__("Apply to All Students"), () => _confirm_and_apply(frm));
			apply_btn.css({
				"background-color": "#b45309", "color": "#fff",
				"border-color": "#b45309", "font-weight": "600",
			});
		}
	},

	// Reset preview when key fields change
	target_scope(frm) {
		if (frm.doc.target_scope === "Batch") frm.set_value("program", "");
		else frm.set_value("programme", "");
		_reset_preview(frm);
	},
	programme(frm)                { _reset_preview(frm); },
	program(frm)                  { _reset_preview(frm); },
	new_fee_structure(frm)        { _reset_preview(frm); },
	batch_year(frm)               { _reset_preview(frm); },
	academic_year(frm)            { _reset_preview(frm); },
	update_existing_invoices(frm) { _reset_preview(frm); },
});


// ── Helpers ──────────────────────────────────────────────────────────────────

function _run_preview(frm) {
	// Client-side validation
	if (frm.doc.target_scope === "Batch" && !frm.doc.programme) {
		frappe.msgprint({ title: __("Required"), message: __("Please select a Batch."), indicator: "orange" });
		return;
	}
	if (frm.doc.target_scope === "Programme" && !frm.doc.program) {
		frappe.msgprint({ title: __("Required"), message: __("Please select a Programme."), indicator: "orange" });
		return;
	}
	if (!frm.doc.new_fee_structure) {
		frappe.msgprint({ title: __("Required"), message: __("Please select a New Fee Structure."), indicator: "orange" });
		return;
	}
	if (!frm.doc.reason || !frm.doc.reason.trim()) {
		frappe.msgprint({ title: __("Required"), message: __("Reason is mandatory before previewing."), indicator: "orange" });
		return;
	}

	frm.save().then(() => {
		frappe.dom.freeze(__("Analysing impact on affected students…"));
		frappe.call({
			method: "slcm.slcm.doctype.bulk_fee_structure_update.bulk_fee_structure_update.preview_bulk_fee_update",
			args: { doc_name: frm.doc.name },
			callback(r) {
				frappe.dom.unfreeze();
				const d = r && r.message;
				if (!d) return;

				let validity = "";
				if (d.valid_from) {
					validity = "  ·  Valid: " + frappe.datetime.str_to_user(d.valid_from);
					if (d.valid_until) validity += " – " + frappe.datetime.str_to_user(d.valid_until);
				}
				frappe.show_alert({
					message: __("{0} student(s) found · New Fee ₹{1} · {2}{3}", [
						d.student_count,
						frappe.utils.fmt_money(d.new_total, 0, "INR"),
						d.fs_name,
						validity,
					]),
					indicator: "blue",
				}, 6);

				frm.reload_doc();
			},
			error() {
				frappe.dom.unfreeze();
				frappe.show_alert({ message: __("Preview failed. Check the Error Log."), indicator: "red" });
			},
		});
	});
}


function _confirm_and_apply(frm) {
	const count       = (frm.doc.affected_students || []).length;
	const scope_label = frm.doc.target_scope === "Batch"
		? (frm.doc.programme || "selected batch")
		: (frm.doc.program   || "selected programme");

	const inv_warning_html = frm.doc.update_existing_invoices
		? `<div style="margin-top:10px;padding:10px 14px;background:#fff7ed;border:1px solid #fed7aa;
		   border-radius:6px;font-size:12.5px;color:#9a3412;">
			<strong>&#9888; Invoice Update Active:</strong> Outstanding (Unpaid / Partially Paid) fee
			invoices for these students will have their fee components replaced.
			<strong>Paid invoices are never modified.</strong>
		   </div>`
		: "";

	const stats_html = `
		<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:12px 0;font-size:12.5px;">
			<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:10px;text-align:center;">
				<div style="font-weight:700;font-size:18px;color:#166534;">${count}</div>
				<div style="color:#15803d;">Students</div>
			</div>
			<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px;text-align:center;">
				<div style="font-weight:700;font-size:18px;color:#1e40af;">
					₹${parseFloat(frm.doc.total_new_outstanding || 0).toLocaleString("en-IN")}
				</div>
				<div style="color:#1d4ed8;">New Outstanding</div>
			</div>
			<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:10px;text-align:center;">
				<div style="font-weight:700;font-size:18px;color:#b45309;">
					₹${parseFloat(frm.doc.total_fee_increase || 0).toLocaleString("en-IN")}
				</div>
				<div style="color:#d97706;">Fee Increase</div>
			</div>
		</div>`;

	frappe.confirm(
		`<div style="font-size:13px;line-height:1.6;">
			You are about to apply fee structure
			<strong>${frappe.utils.escape_html(frm.doc.new_fee_structure)}</strong>
			to <strong>${count} student(s)</strong> in
			<strong>${frappe.utils.escape_html(scope_label)}</strong>.
			${stats_html}
			${inv_warning_html}
			<div style="margin-top:10px;font-size:12px;color:#6b7280;">
				Each student's Fee Structure History will record this change with the provided reason.
				This action cannot be undone automatically.
			</div>
		</div>`,
		() => {
			frappe.dom.freeze(__("Applying fee structure to all students…"));
			frappe.call({
				method: "slcm.slcm.doctype.bulk_fee_structure_update.bulk_fee_structure_update.apply_bulk_fee_update",
				args: { doc_name: frm.doc.name },
				callback(r) {
					frappe.dom.unfreeze();
					const res = r && r.message;
					if (!res) return;
					frappe.show_alert({
						message: res.message,
						indicator: res.errors > 0 ? "orange" : "green",
					}, 8);
					frm.reload_doc();
				},
				error() {
					frappe.dom.unfreeze();
					frappe.show_alert({ message: __("Apply failed. Check the Error Log."), indicator: "red" });
				},
			});
		}
	);
}


function _reset_preview(frm) {
	if (frm.doc.status === "Previewed") {
		frm.set_value("status", "Draft");
		frm.set_value("total_students_affected", 0);
		frm.set_value("total_fee_increase", 0);
		frm.set_value("total_new_outstanding", 0);
	}
}


function _render_status_banner(frm) {
	const cfg = {
		"Draft":     { bg: "#f9fafb", border: "#e5e7eb", text: "#374151",
		               msg: "Click <strong>Preview Impact</strong> to analyse affected students before applying." },
		"Previewed": { bg: "#eff6ff", border: "#bfdbfe", text: "#1e3a5f",
		               msg: "Preview ready. Review the Affected Students table, then click <strong>Apply to All Students</strong>." },
		"Applied":   { bg: "#f0fdf4", border: "#bbf7d0", text: "#166534",
		               msg: `Applied by <strong>${frm.doc.applied_by || ""}</strong> on ${frm.doc.applied_on ? frappe.datetime.str_to_user(frm.doc.applied_on) : ""}.` },
		"Failed":    { bg: "#fff5f5", border: "#fca5a5", text: "#991b1b",
		               msg: "Apply failed — check the Error Log for details." },
	};
	const c = cfg[frm.doc.status] || cfg["Draft"];

	frm.set_df_property("fee_change_note", "options",
		frm.doc.fee_change_note ||
		`<div style="padding:11px 16px;background:${c.bg};border:1px solid ${c.border};
		 border-radius:8px;font-size:13px;color:${c.text};">
			<strong>Status: ${frm.doc.status}</strong> — ${c.msg}
		 </div>`
	);
	frm.refresh_field("fee_change_note");
}

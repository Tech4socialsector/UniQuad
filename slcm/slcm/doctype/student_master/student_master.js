// Copyright (c) 2025, Nishanth and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Master", {
	dob(frm) {
		if (!frm.doc.dob) return;

		const dob = frappe.datetime.str_to_obj(frm.doc.dob);
		const today = frappe.datetime.str_to_obj(frappe.datetime.now_date());

		// DOB cannot be today or future
		if (dob >= today) {
			frappe.msgprint(__("Date of Birth cannot be today or a future date."));
			frm.set_value("dob", "");
			return;
		}

		// DOB cannot be current year
		if (dob.getFullYear() === today.getFullYear()) {
			frappe.msgprint(__("Date of Birth cannot be in the current year."));
			frm.set_value("dob", "");
			return;
		}

		// Minimum age = 15
		let age = today.getFullYear() - dob.getFullYear();
		const m = today.getMonth() - dob.getMonth();

		if (m < 0 || (m === 0 && today.getDate() < dob.getDate())) {
			age--;
		}

		if (age < 15) {
			frappe.msgprint(__("Student must be at least 15 years old."));
			frm.set_value("dob", "");
		}
	},

	refresh(frm) {
		// Hide default left sidebar
		$(".layout-side-section").hide();

		// Render custom right-side profile panel
		frm.trigger("render_profile_sidebar");

		// Custom Status Button
		if (!frm.is_new()) {
			const status_btn = frm.add_custom_button(
				__("Status"),
				function () {
					frm.trigger("show_status_dialog");
				},
				__("Update Status")
			).addClass("btn-primary");

			status_btn.css({
				"background-color": "#000",
				color: "#fff",
				"border-color": "#000",
				"box-shadow": "none",
			});

			// Download Registration Slip
			const download_btn = frm.add_custom_button(
				__("Registration Slip"),
				function () {
					const student_name = frm.doc.name;
					const url = frappe.urllib.get_full_url(
						`/api/method/frappe.utils.print_format.download_pdf?doctype=Student+Master&name=${encodeURIComponent(student_name)}&format=Student+Registration+Slip`
					);
					frappe.show_alert({ message: __("Generating PDF..."), indicator: "blue" });
					fetch(url, { credentials: "same-origin" })
						.then((res) => {
							if (!res.ok) throw new Error("Failed");
							return res.blob();
						})
						.then((blob) => {
							const a = document.createElement("a");
							a.href = URL.createObjectURL(blob);
							a.download = `Registration_Slip_${student_name}.pdf`;
							document.body.appendChild(a);
							a.click();
							a.remove();
							URL.revokeObjectURL(a.href);
						})
						.catch(() => {
							frappe.msgprint({
								title: __("Error"),
								message: __("Could not generate PDF. Please try again."),
								indicator: "red",
							});
						});
				},
				__("Download")
			);

			setDarkButtonStyle(download_btn);

			// ── Fee Invoice / Demand Receipts — tabbed dialog ─────────────
			const inv_dl_btn = frm.add_custom_button(
				__("⬇ Fee Invoice"),
				function () {
					frappe.show_alert({ message: __("Loading fee records…"), indicator: "blue" });
					// Fetch invoices and demands in parallel, then open tabbed dialog
					let invoices = [], demands = [], done = 0;
					function _check() {
						if (++done < 2) return;
						_show_fee_documents_dialog(frm, invoices, demands);
					}
					frappe.call({
						method: "frappe.client.get_list",
						args: {
							doctype:          "Fee Invoice",
							filters:          { student: frm.doc.name },
							fields:           ["name", "academic_term", "academic_year",
							                   "invoice_date", "due_date",
							                   "final_payable_amount", "paid_amount",
							                   "outstanding_amount", "status"],
							order_by:         "invoice_date desc, creation desc",
							limit_page_length: 50,
						},
						callback: function (r) { invoices = r.message || []; _check(); },
						error:    function ()  { _check(); },
					});
					frappe.call({
						method: "frappe.client.get_list",
						args: {
							doctype:          "Fee Demand",
							filters:          { student: frm.doc.name },
							fields:           ["name", "fee_component", "description",
							                   "due_date", "status",
							                   "net_payable", "paid_amount", "outstanding_amount"],
							order_by:         "due_date desc, creation desc",
							limit_page_length: 100,
						},
						callback: function (r) { demands = r.message || []; _check(); },
						error:    function ()  { _check(); },
					});
				}
			);
			inv_dl_btn.css({
				"background-color": "#1a3c6e",
				"color":            "#fff",
				"border-color":     "#1a3c6e",
				"font-weight":      "600",
			});

			// ── View Payment Logs — audit trail dialog ────────────────────
			const logs_btn = frm.add_custom_button(
				__("📋 Payment Logs"),
				function () {
					_show_payment_logs_dialog(frm);
				}
			);
			logs_btn.css({
				"background-color": "#4f46e5",
				"color":            "#fff",
				"border-color":     "#4f46e5",
				"font-weight":      "600",
			});

			// ── Sync Fee Invoices — standalone button ─────────────────────────
			const sync_btn = frm.add_custom_button(
				__("🔄 Sync Fee Invoices"),
				function () {
					frappe.show_alert({ message: __("Syncing fee invoices…"), indicator: "blue" });
					frappe.call({
						method: "slcm.slcm.doctype.student_master.student_master.sync_fee_invoices",
						args:   { student_name: frm.doc.name },
						callback: function (r) {
							const n = (r.message && r.message.synced) || 0;
							frappe.show_alert({
								message:   __(`✔ ${n} invoice(s) synced successfully.`),
								indicator: "green",
							});
							frm.reload_doc();
						},
						error: function () {
							frappe.show_alert({ message: __("Sync failed. Check error log."), indicator: "red" });
						},
					});
				}
			);
			// Style: teal/green background
			sync_btn.css({
				"background-color": "#0d7a5f",
				"color":            "#fff",
				"border-color":     "#0d7a5f",
				"font-weight":      "600",
			});

			// ── Change Fee Structure (admin override) ──────────────────
			const admin_roles = ["System Manager", "Administrator", "slcm_FINO Officer"];
			const user_roles  = frappe.user_roles || [];
			const can_change_fs = admin_roles.some(r => user_roles.includes(r))
				|| frappe.session.user === "Administrator";

			if (can_change_fs) {
				const chg_fs_btn = frm.add_custom_button(
					__("Change Fee Structure"),
					function () {
						_show_change_fee_structure_dialog(frm);
					},
					__("Update Status")
				);
				chg_fs_btn.css({
					"background-color": "#b45309",
					"color":            "#fff",
					"border-color":     "#b45309",
					"font-weight":      "600",
				});
			}

			// ── Send Parent Login Invite ───────────────────────────────
			const parent_invite_btn = frm.add_custom_button(
				__("Send Parent Login Invite"),
				function () {
					const parents = frm.doc.parents || [];
					const with_email = parents.filter(p => p.email);
					if (!parents.length) {
						frappe.msgprint({
							title: __("No Parents Recorded"),
							message: __("Please add parent details (with email) in the Parents table before sending an invite."),
							indicator: "orange",
						});
						return;
					}
					if (!with_email.length) {
						frappe.msgprint({
							title: __("No Email Addresses"),
							message: __("None of the parent records have an email address. Please add email addresses first."),
							indicator: "orange",
						});
						return;
					}
					const names = with_email.map(p => `<li>${p.first_name} ${p.last_name || ""} (${p.email})</li>`).join("");
					frappe.confirm(
						`Send login invites to the following parent(s)?<ul style="margin-top:8px;">${names}</ul>`,
						() => {
							frappe.dom.freeze("Sending invites…");
							frappe.call({
								method: "slcm.slcm.doctype.student_master.student_master.send_parent_login_invite",
								args: { student_name: frm.doc.name },
								callback(r) {
									frappe.dom.unfreeze();
									const results = r.message || [];
									const invited = results.filter(x => x.status === "invited").length;
									const existing = results.filter(x => x.status === "existing").length;
									const no_email = results.filter(x => x.status === "no_email").length;
									let msg = "";
									if (invited) msg += `<b>${invited}</b> invite(s) sent successfully.<br>`;
									if (existing) msg += `<b>${existing}</b> parent(s) already have portal access.<br>`;
									if (no_email) msg += `<b>${no_email}</b> parent(s) skipped — no email.<br>`;
									frappe.msgprint({
										title: __("Parent Invites"),
										message: msg || __("Done."),
										indicator: invited ? "green" : "orange",
									});
								},
								error() {
									frappe.dom.unfreeze();
									frappe.show_alert({ message: __("Failed to send invites. Check Error Log."), indicator: "red" });
								},
							});
						}
					);
				},
				__("Parents")
			);
			parent_invite_btn.css({
				"background-color": "#7c3aed",
				"color": "#fff",
				"border-color": "#7c3aed",
				"font-weight": "600",
			});

			// Render Academic Progress dashboard
			frm.trigger("render_academic_progress");

			// Eagerly load Finance tab analytics (so it's ready if user opens Finance tab)
			if (!frm.is_new()) {
				_render_finance_tab_analytics(frm);
			}

			// Check Enrollment Eligibility and Add Button
			frappe.call({
				method: "slcm.slcm.doctype.student_master.student_master.validate_new_enrollment",
				args: {
					student_id: frm.doc.name,
				},
				callback: function (r) {
					if (r.message && r.message.allowed) {
						const enroll_btn = frm.add_custom_button(__("Enroll"), function () {
							// Re-validate on click to prevent race conditions
							frappe.call({
								method: "slcm.slcm.doctype.student_master.student_master.validate_new_enrollment",
								args: {
									student_id: frm.doc.name,
								},
								callback: function (r2) {
									if (r2.message && r2.message.allowed) {
										frappe.new_doc("Student Enrollment", {
											student: frm.doc.name,
											student_name: [
												frm.doc.first_name,
												frm.doc.middle_name,
												frm.doc.last_name,
											]
												.filter(Boolean)
												.join(" "),
											cohort: frm.doc.programme,
											academic_year: frm.doc.academic_year,
										});
									} else {
										frappe.msgprint({
											title: __("Not Allowed"),
											message: r2.message
												? r2.message.message
												: __("Enrollment not allowed."),
											indicator: "orange",
										});
									}
								},
							});
						}).addClass("btn-primary");
								setDarkButtonStyle(enroll_btn);
					}
				},
			});
		}
	},

	tab_finance(frm) {
		// Render the Finance tab analytics strip whenever the Finance tab is opened
		_render_finance_tab_analytics(frm);
	},

	render_academic_progress(frm) {
		if (frm.is_new()) return;

		// Show loading state immediately using set_df_property (works on any tab)
		frm.set_df_property(
			"academic_progress_html",
			"options",
			`<div style="color:#6b7280;font-size:13px;padding:8px 0;">Loading academic progress…</div>`
		);

		frappe.call({
			method: "slcm.slcm.doctype.student_master.student_master.get_academic_progress_list",
			args: { student_name: frm.doc.name },
			callback(r) {
				const enrollments = (r && r.message) || [];
				_load_academic_progress(frm, null, enrollments);
			},
			error() {
				_load_academic_progress(frm, null, []);
			},
		});
	},

	show_status_dialog(frm) {
		// Fetch available actions
		frappe.call({
			method: "slcm.slcm.doctype.student_master.student_master.get_available_status_actions",
			args: {
				student_id: frm.doc.name,
			},
			callback: function (r) {
				if (r.message) {
					show_status_transition_dialog(frm, r.message);
				}
			},
		});
	},

	render_profile_sidebar(frm) {
		if (frm.is_new()) {
			return;
		}

		const image = frm.doc.student_image || frm.doc.passport_size_photo || "/assets/frappe/images/default-avatar.png";

		const html = `
			<div class="student-profile-card">
				<img src="${image}" class="student-avatar" />
				<button class="btn btn-sm btn-primary upload-btn">
					Upload Image
				</button>
				<hr />
				<div class="attachment-area">
					<h6>Attachments</h6>
					<div class="attachments"></div>
				</div>
			</div>
		`;

		if (frm.fields_dict.profile_sidebar) {
			frm.fields_dict.profile_sidebar.$wrapper.html(html);

			frm.fields_dict.profile_sidebar.$wrapper.find(".upload-btn").on("click", () => {
				new frappe.ui.FileUploader({
					doctype: frm.doctype,
					docname: frm.doc.name,
					on_success(file) {
						if (file.file_url && file.file_url.match(/\.(jpg|jpeg|png|webp)$/i)) {
							frm.set_value("passport_size_photo", file.file_url);
							frm.save().then(() => {
								frm.reload_doc();
							});
						}
					},
				});
			});
		}
	},

	programme(frm) {
		if (!frm.doc.programme) return;

		frappe.call({
			method: "slcm.slcm.doctype.student_master.student_master.fetch_program_fee_details",
			args: { programme: frm.doc.programme },
			callback(r) {
				const data = r && r.message;
				if (!data || !data.total_program_fee) {
					frappe.show_alert({ message: __("No active Student Fee Structure found for this programme."), indicator: "orange" });
					return;
				}
				if (!frm.doc.total_program_fee) {
					frm.set_value("total_program_fee", data.total_program_fee);
				}
				if (data.fee_structure && !frm.doc.fee_structure) {
					frm.set_value("fee_structure", data.fee_structure);
				}
				frappe.show_alert({
					message: __("Fee loaded: ₹{0}", [frappe.utils.fmt_money(data.total_program_fee, 0, "INR")]),
					indicator: "green"
				});
			},
		});
	},

	fee_structure(frm) {
		if (!frm.doc.fee_structure) return;
		frappe.call({
			method: "slcm.slcm.doctype.student_master.student_master.get_fee_structure_details",
			args: { fee_structure: frm.doc.fee_structure },
			callback(r) {
				const data = r && r.message;
				if (!data) {
					frappe.show_alert({ message: __("Could not load Fee Structure details."), indicator: "red" });
					return;
				}

				frm.set_value("total_program_fee", data.total_amount);

				if (data.instalment_enabled && data.max_instalments) {
					frm.set_value("number_of_instalments", data.max_instalments);
				}

				frm.trigger("calculate_fees");

				// Build validity info string
				let validity = "";
				if (data.valid_from) {
					validity = "Valid from " + frappe.datetime.str_to_user(data.valid_from);
					if (data.valid_until) {
						validity += " to " + frappe.datetime.str_to_user(data.valid_until);
					}
				}

				const status_indicator = data.status === "Active" ? "green" : "orange";
				frappe.show_alert({
					message: __("{0} — ₹{1}{2}", [
						data.fee_structure_name,
						frappe.utils.fmt_money(data.total_amount, 0, "INR"),
						validity ? " · " + validity : "",
					]),
					indicator: status_indicator,
				});
			},
		});
	},

	total_program_fee(frm) {
		frm.trigger("calculate_fees");
	},

	scholarship_percentage(frm) {
		frm.trigger("calculate_fees");
	},

	total_paid_amount(frm) {
		frm.trigger("calculate_fees");
	},

	applying_scholarship(frm) {
		if (frm.doc.applying_scholarship !== "Yes") {
			frm.set_value("scholarship_percentage", 0);
		}
		frm.trigger("calculate_fees");
	},

	calculate_fees(frm) {
		let total_fee = frm.doc.total_program_fee || 0;
		let scholarship_pct = frm.doc.scholarship_percentage || 0;
		let paid_amount = frm.doc.total_paid_amount || 0;

		if (frm.doc.applying_scholarship !== "Yes") {
			scholarship_pct = 0;
		}

		let discount = (total_fee * scholarship_pct) / 100;
		let net_fee = total_fee - discount;
		let balance = net_fee - paid_amount;

		frm.set_value("discount_amount", discount);
		frm.set_value("net_program_fee", net_fee);
		frm.set_value("outstanding_balance", balance);
	},

	state(frm) {
		// Clear district when state changes
		if (frm.doc.district) {
			frm.set_value('district', '');
		}

		// Set filter for district based on selected state
		frm.set_query('district', function () {
			return {
				filters: {
					'state': frm.doc.state
				}
			};
		});
	}
});

/* ── Academic Progress Panel ─────────────────────────────────────────────────
   Renders a clean card showing:
     • Current Academic Year & Term
     • Enrolled Courses table
     • Promotion Policy eligibility summary
────────────────────────────────────────────────────────────────────────────── */
function _ordinal_year(val) {
	if (!val) return "";
	const n = parseInt(val, 10);
	if (isNaN(n)) return String(val);
	const suffixes = ["th", "st", "nd", "rd"];
	const v = n % 100;
	const suffix = suffixes[(v - 20) % 10] || suffixes[v] || suffixes[0];
	return `${n}${suffix} Year`;
}

function _load_academic_progress(frm, enrollment_name, enrollments) {
	frappe.call({
		method: "slcm.slcm.doctype.student_master.student_master.get_academic_progress",
		args: {
			student_name: frm.doc.name,
			enrollment_name: enrollment_name || undefined,
		},
		callback(r) {
			const d = r && r.message;
			const selector_html = _build_progress_selector_html(frm, enrollments, enrollment_name);
			const body_html = d
				? _build_academic_progress_html(d)
				: `<div style="color:#ef4444;font-size:13px;">Could not load academic progress.</div>`;
			frm.set_df_property("academic_progress_html", "options", selector_html + body_html);
			frm.refresh_field("academic_progress_html");
			_bind_academic_progress_selector(frm, enrollments);

			// Populate Year of Study field only when viewing current progress
			if (!enrollment_name) {
				const yr = (d && d.current_year) || frm.doc.current_year;
				const new_yr_str = _ordinal_year(yr);
				if (frm.doc.year_of_study !== new_yr_str) {
					frm.set_value("year_of_study", new_yr_str);
				}
			}
		},
		error() {
			const selector_html = _build_progress_selector_html(frm, enrollments, enrollment_name);
			frm.set_df_property(
				"academic_progress_html",
				"options",
				selector_html + `<div style="color:#ef4444;font-size:13px;">Error loading academic progress. Check Error Log.</div>`
			);
			frm.refresh_field("academic_progress_html");
			_bind_academic_progress_selector(frm, enrollments);
		},
	});
}

function _build_progress_selector_html(frm, enrollments, selected_name) {
	const enc = frappe.utils.escape_html;

	if (!enrollments || enrollments.length < 2) return "";

	const options = enrollments.map((en) => {
		const label = `${en.ay_name || en.academic_year || "—"} · ${en.term_name || "—"}` +
			(en.is_current ? " (Current)" : "");
		const value = en.name;
		const selected = (selected_name ? value === selected_name : en.is_current) ? "selected" : "";
		return `<option value="${enc(value)}" ${selected}>${enc(label)}</option>`;
	}).join("");

	return `
	<div style="margin-bottom:14px;display:flex;align-items:center;gap:10px;">
		<label style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.04em;font-weight:600;">
			Viewing
		</label>
		<select class="academic-progress-selector" style="font-size:13px;padding:5px 10px;border:1px solid #d1d5db;
		         border-radius:8px;background:#fff;color:#111827;font-weight:600;min-width:220px;">
			${options}
		</select>
	</div>`;
}

function _bind_academic_progress_selector(frm, enrollments) {
	const $wrapper = frm.get_field("academic_progress_html").$wrapper;
	$wrapper.find(".academic-progress-selector").off("change").on("change", function () {
		const chosen = $(this).val();
		frm.set_df_property(
			"academic_progress_html",
			"options",
			`<div style="color:#6b7280;font-size:13px;padding:8px 0;">Loading academic progress…</div>`
		);
		frm.refresh_field("academic_progress_html");
		_load_academic_progress(frm, chosen, enrollments);
	});
}

function _build_academic_progress_html(d) {
	const enc = frappe.utils.escape_html;

	if (!d.enrollment) {
		return `<div style="padding:16px;background:#fef3c7;border:1px solid #fcd34d;
		         border-radius:10px;color:#92400e;font-size:13px;font-weight:500;">
		         No active enrollment found for this student.
		       </div>`;
	}

	const e = d.enrollment;

	// ── Status badge helper ──────────────────────────────────────────────────
	function badge(label, color) {
		const colours = {
			green:  { bg: "#dcfce7", text: "#166534" },
			red:    { bg: "#fee2e2", text: "#991b1b" },
			orange: { bg: "#fef3c7", text: "#92400e" },
			blue:   { bg: "#dbeafe", text: "#1e40af" },
			gray:   { bg: "#f3f4f6", text: "#4b5563" },
		};
		const c = colours[color] || colours.gray;
		return `<span style="background:${c.bg};color:${c.text};padding:2px 10px;
		         border-radius:20px;font-size:11px;font-weight:700;">${enc(label)}</span>`;
	}

	const status_color = { Enrolled: "green", Dropped: "red", Completed: "blue", Pending: "orange" };
	const ay_color     = { Active: "green", Inactive: "gray" };
	const term_color   = { Active: "green", Inactive: "gray" };

	// ── Top info cards ───────────────────────────────────────────────────────
	function info_card(icon, label, value, sub) {
		return `
		<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;
		            padding:14px 18px;min-width:160px;flex:1;">
			<div style="font-size:20px;margin-bottom:4px;">${icon}</div>
			<div style="font-size:11px;color:#6b7280;text-transform:uppercase;
			            letter-spacing:0.04em;font-weight:600;">${enc(label)}</div>
			<div style="font-size:15px;font-weight:700;color:#111827;margin-top:2px;">${enc(value || "—")}</div>
			${sub ? `<div style="font-size:11px;color:#9ca3af;margin-top:2px;">${sub}</div>` : ""}
		</div>`;
	}

	const ay_date_range = (e.ay_start && e.ay_end)
		? frappe.datetime.str_to_user(e.ay_start) + " – " + frappe.datetime.str_to_user(e.ay_end)
		: "";

	const term_date_range = (e.term_start && e.term_end)
		? frappe.datetime.str_to_user(e.term_start) + " – " + frappe.datetime.str_to_user(e.term_end)
		: "";

	// Year is the promotion unit; terms inside a year advance automatically.
	const pg = d.progression || {};
	const year_label = pg.year_label || (d.current_year ? _ordinal_year(d.current_year) : "");
	const term_pos = pg.term_no
		? (pg.terms_in_year ? `Term ${pg.term_no} of ${pg.terms_in_year}` : `Term ${pg.term_no}`)
		: (e.cohort_term_year ? `Term ${e.cohort_term_year}` : "");
	const term_pos_sub = term_pos
		? enc(term_pos) + (pg.is_last_term ? " · final term of the year" : "")
		: "";

	const cards_html = `
	<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
		${info_card("📅", "Academic Year", e.ay_name || e.academic_year,
		            ay_date_range + (e.ay_status ? " &nbsp;" + badge(e.ay_status, ay_color[e.ay_status] || "gray") : ""))}
		${info_card("📖", "Current Term", e.term_name || "—",
		            term_date_range + (e.term_status ? " &nbsp;" + badge(e.term_status, term_color[e.term_status] || "gray") : ""))}
		${info_card("🎓", "Year of Study", year_label || "—", term_pos_sub)}
		${info_card("🏫", "Enrollment Status", e.status,
		            e.enrollment_date ? "Since " + frappe.datetime.str_to_user(e.enrollment_date) : "")}
	</div>
	<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
		${info_card("📚", "Programme", e.program_name || e.program || "—", e.program && e.program_name && e.program !== e.program_name ? enc(e.program) : "")}
		${info_card("🗂️", "Batch", e.cohort_name || e.cohort || "—",
		            [e.cohort_code ? enc(e.cohort_code) : "", e.cohort_status ? badge(e.cohort_status, e.cohort_status === "Active" ? "green" : "gray") : ""].filter(Boolean).join(" &nbsp;"))}
		${info_card("👥", "Section", e.cohort_section || d.batch_year || e.batch_year || "—", "")}
		${info_card("🧑‍🏫", "Faculty Advisor", e.faculty_advisor_name || e.faculty_advisor || "—", "")}
	</div>
	<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
		<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px 18px;flex:1;display:flex;align-items:center;gap:16px;">
			<span style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.04em;font-weight:600;">Current CGPA</span>
			<span style="font-size:20px;font-weight:800;color:#1a3c6e;">${d.current_cgpa ? d.current_cgpa.toFixed(2) : "—"}</span>
			<span style="margin-left:16px;font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.04em;font-weight:600;">Attendance percentage</span>
			<span style="font-size:20px;font-weight:800;color:${d.term_attendance != null && d.term_attendance < 75 ? "#b91c1c" : "#166534"};">${d.term_attendance != null ? d.term_attendance.toFixed(1) + "%" : (d.attendance_status ? enc(d.attendance_status) : "—")}</span>
			<span style="font-size:11px;color:#9ca3af;">this term's courses</span>
		</div>
	</div>`;

	// ── Courses table ────────────────────────────────────────────────────────
	let courses_html = "";
	if (d.courses && d.courses.length) {
		const course_type_color = { Core: "blue", Elective: "orange" };

		const rows = d.courses.map((c, idx) => {
			const row_bg = idx % 2 === 0 ? "#fff" : "#f9fafb";
			const att_pct = c.attendance_percentage;
			const att_display = (att_pct === null || att_pct === undefined || att_pct === "")
				? "—"
				: `${flt(att_pct).toFixed(1)}%`;
			const att_color = (att_pct === null || att_pct === undefined || att_pct === "")
				? "#6b7280"
				: (flt(att_pct) < 75 ? "#b91c1c" : "#166534");
			return `
			<tr style="background:${row_bg};">
				<td style="padding:9px 12px;font-weight:600;color:#111827;">${enc(c.course || "")}</td>
				<td style="padding:9px 12px;color:#374151;">${enc(c.course_name || "")}</td>
				<td style="padding:9px 12px;">${badge(c.course_type || "Core", course_type_color[c.course_type] || "gray")}</td>
				<td style="padding:9px 12px;text-align:center;color:#374151;">${c.credit_value || c.credits || "—"}</td>
				<td style="padding:9px 12px;text-align:center;font-weight:600;color:${att_color};">${att_display}</td>
			</tr>`;
		}).join("");

		const total_credits = d.courses.reduce((s, c) => s + (c.credits || c.credit_value || 0), 0);

		courses_html = `
		<div style="margin-bottom:16px;">
			<div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:8px;">
				Enrolled Courses &nbsp;<span style="font-weight:400;color:#6b7280;">(${d.courses.length} course${d.courses.length !== 1 ? "s" : ""} · ${total_credits} credits)</span>
			</div>
			<div style="overflow-x:auto;border:1px solid #e5e7eb;border-radius:10px;">
				<table style="width:100%;border-collapse:collapse;font-family:inherit;font-size:13px;">
					<thead>
						<tr style="background:#1a3c6e;">
							<th style="padding:10px 12px;color:#fff;font-size:11px;font-weight:700;text-align:left;
							           text-transform:uppercase;letter-spacing:0.04em;border-radius:10px 0 0 0;">Course ID</th>
							<th style="padding:10px 12px;color:#fff;font-size:11px;font-weight:700;text-align:left;
							           text-transform:uppercase;letter-spacing:0.04em;">Course Name</th>
							<th style="padding:10px 12px;color:#fff;font-size:11px;font-weight:700;text-align:left;
							           text-transform:uppercase;letter-spacing:0.04em;">Type</th>
							<th style="padding:10px 12px;color:#fff;font-size:11px;font-weight:700;text-align:center;
							           text-transform:uppercase;letter-spacing:0.04em;">Credits</th>
							<th style="padding:10px 12px;color:#fff;font-size:11px;font-weight:700;text-align:center;
							           text-transform:uppercase;letter-spacing:0.04em;border-radius:0 10px 0 0;">Attendance Percentage</th>
						</tr>
					</thead>
					<tbody>${rows}</tbody>
				</table>
			</div>
		</div>`;
	} else {
		courses_html = `
		<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;
		            padding:14px 18px;color:#6b7280;font-size:13px;margin-bottom:16px;">
			No courses enrolled for this term yet.
		</div>`;
	}

	// ── Progression: automatic term moves + year-end policy check ────────────
	const promo_html = _build_progression_html(pg, enc, badge);

	return `
	<div style="font-family:inherit;padding:4px 0;">
		${cards_html}
		${courses_html}
		<div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:8px;">Progression &amp; Promotion</div>
		${promo_html}
	</div>`;
}

function _build_progression_html(pg, enc, badge) {
	const box = (inner) => `<div style="border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;margin-bottom:12px;">${inner}</div>`;
	let html = "";

	// 1. Where the student is and what happens next
	if (pg.next_step || pg.term_no) {
		const steps = [];
		const n = pg.terms_in_year || pg.term_no || 0;
		for (let t = 1; t <= n; t++) {
			const done = t < pg.term_no, cur = t === pg.term_no;
			steps.push(`<div style="flex:1;min-width:90px;text-align:center;">
				<div style="height:8px;border-radius:4px;background:${done || cur ? "#920c24" : "#d1d5db"};${cur ? "box-shadow:0 0 0 2px #fff,0 0 0 4px #920c24;" : ""}"></div>
				<div style="font-size:11px;margin-top:5px;color:${cur ? "#920c24" : "#6b7280"};font-weight:${cur ? 700 : 500};">
					Term ${t}${cur ? " · current" : ""}</div></div>`);
		}
		steps.push(`<div style="flex:1;min-width:110px;text-align:center;">
			<div style="height:8px;border-radius:4px;background:#fff;border:2px dashed #920c24;box-sizing:border-box;"></div>
			<div style="font-size:11px;margin-top:5px;color:#6b7280;">Year-end → Year ${enc(String((pg.year || 0) + 1))}</div></div>`);
		html += box(`
			<div style="padding:12px 18px;background:#920c24;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
				<span style="font-size:13px;font-weight:700;color:#fff;">${enc(pg.year_label || "")}</span>
				<span style="font-size:12px;color:#fff;">${enc(pg.next_step || "")}</span>
			</div>
			<div style="padding:14px 18px;display:flex;gap:8px;flex-wrap:wrap;">${steps.join("")}</div>
			<div style="padding:0 18px 12px;font-size:11.5px;color:#6b7280;">
				Term-to-term moves within a year are automatic (Student Enrollment → Promote Students, no policy check).
				The Promotion Policy is applied only for Year → Year promotion (Promotion Management).
			</div>`);
	}

	// 2. Year-end eligibility (same engine as Promotion Management)
	const el = pg.eligibility;
	if (el) {
		const colour = { "Promoted": "green", "Not Promoted": "red", "Conditional": "orange" }[el.status] || "gray";
		const label = { "Promoted": "Eligible", "Not Promoted": "Not Eligible", "Conditional": "Conditional" }[el.status] || el.status;
		const rows = (el.criteria || []).map((c) => `
			<tr>
				<td style="padding:7px 12px;color:#374151;">${enc(c.label)}</td>
				<td style="padding:7px 12px;font-weight:600;color:#111827;">${enc(String(c.value))}</td>
				<td style="padding:7px 12px;color:#6b7280;">${enc(c.required)}</td>
				<td style="padding:7px 12px;text-align:center;font-size:15px;">${c.result === "Pass" ? "✅" : c.result === "Fail" ? "❌" : "—"}</td>
			</tr>`).join("");
		const th = (t, al) => `<th style="padding:7px 12px;text-align:${al || "left"};font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:0.04em;">${t}</th>`;
		html += box(`
			<div style="background:#f9fafb;padding:12px 18px;border-bottom:1px solid #e5e7eb;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
				<span style="font-size:13px;font-weight:700;color:#374151;">Year-end eligibility · Year ${enc(String(el.from_year))} → Year ${enc(String(el.to_year))}</span>
				<a href="/app/promotion-policy/${enc(el.policy)}" style="color:#920c24;font-size:12px;">${enc(el.policy_title || el.policy)}</a>
				<span style="margin-left:auto;">${badge(label + (el.projected ? " (projected)" : ""), colour)}</span>
			</div>
			<div style="padding:12px 18px;">
				${rows ? `<table style="width:100%;border-collapse:collapse;font-size:13px;">
					<thead><tr style="background:#f3f4f6;">${th("Criterion")}${th("Student")}${th("Required")}${th("Result", "center")}</tr></thead>
					<tbody>${rows}</tbody></table>`
					: `<div style="color:#6b7280;font-size:13px;">This policy has no criteria enabled — every student is eligible.</div>`}
				${el.projected ? `<div style="font-size:11.5px;color:#6b7280;margin-top:10px;">Projected from data so far — the decision is made when Year ${enc(String(el.from_year))} promotion is run at year end.</div>` : ""}
			</div>`);
	} else if (pg.year) {
		html += `<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:14px 18px;color:#6b7280;font-size:13px;margin-bottom:12px;">
			No Active Promotion Policy for Year ${enc(String(pg.year))} of this programme and academic year.</div>`;
	}

	// 3. Latest confirmed decision from the Promotion Log
	const ld = pg.last_decision;
	if (ld) {
		const colour = /Not Promoted/.test(ld.promotion_status) ? "red" : /Promoted/.test(ld.promotion_status) ? "green" : "orange";
		const enr = ld.stage === "Draft"
			? `<span style="color:#b45309;">Not applied yet — the student sees no change until it is published.</span>`
			: ld.enrollment_status === "Enrolled"
			? `Enrolled in <a href="/app/student-enrollment/${enc(ld.to_enrollment || "")}">${enc(ld.to_enrollment || "")}</a>`
			: ld.enrollment_status === "Failed" ? `<span style="color:#b91c1c;">Next-year enrollment failed — use Retry Enrollment in Promotion Management</span>` : "";
		html += `<div style="border:1px solid #e5e7eb;border-radius:10px;padding:12px 18px;font-size:12.5px;color:#374151;display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
			<b>Last promotion run:</b> ${badge(ld.promotion_status, colour)}
			${ld.stage === "Draft" ? badge("Draft — not published", "orange") : badge("Published", "blue")}
			<span>Year ${enc(String(ld.current_year || ""))} → ${enc(String(ld.target_year || ""))}</span>
			<span style="color:#6b7280;">${ld.processed_on ? enc(frappe.datetime.str_to_user(ld.processed_on)) : ""}</span>
			${enr ? `<span>${enr}</span>` : ""}
			<a href="/app/promotion-management" style="margin-left:auto;color:#920c24;font-weight:600;">Open Promotion Management →</a>
		</div>`;
	}

	return html || `<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:14px 18px;color:#6b7280;font-size:13px;">
		No progression data available for this student.</div>`;
}

function setDarkButtonStyle(btn) {
	if (!btn || !btn.length) return;
	btn.css({
		"background-color": "#000",
		color: "#fff",
		"border-color": "#000",
		"box-shadow": "none",
	});
}

/* ── Fee Documents Dialog (tabbed: Fee Invoices + Fee Demand Receipts) ────────
   Single dialog opened by the "⬇ Fee Invoice" button.
   Tab 1 — Fee Invoices: term-wise list with PDF download per row.
   Tab 2 — Demand Receipts: additional-charges list; "⬇ Receipt" for paid rows,
            looks up the Fee Receipt via the Fee Payment Demand Row child table.
────────────────────────────────────────────────────────────────────────────── */
function _show_fee_documents_dialog(frm, invoices, demands) {
	const student_label = [frm.doc.first_name, frm.doc.last_name].filter(Boolean).join(" ")
	                      || frm.doc.name;

	const STATUS_COLOR = {
		"Paid":           { bg: "#dcfce7", text: "#166534" },
		"Partially Paid": { bg: "#fef3c7", text: "#92400e" },
		"Unpaid":         { bg: "#fee2e2", text: "#991b1b" },
		"Pending":        { bg: "#fee2e2", text: "#991b1b" },
		"Overdue":        { bg: "#fee2e2", text: "#991b1b" },
		"Waived":         { bg: "#f3f4f6", text: "#6b7280" },
		"Cancelled":      { bg: "#f3f4f6", text: "#6b7280" },
	};

	function fmt_inr(v) {
		return "₹" + parseFloat(v || 0).toLocaleString("en-IN", { minimumFractionDigits: 0 });
	}
	function badge(status) {
		const c = STATUS_COLOR[status] || STATUS_COLOR["Unpaid"];
		return `<span style="background:${c.bg};color:${c.text};padding:2px 10px;
		        border-radius:20px;font-size:11px;font-weight:700;">${status}</span>`;
	}

	// ── Tab 1: Fee Invoices ───────────────────────────────────────────────────
	const inv_rows = invoices.map((inv, idx) => {
		const term   = inv.academic_term  || inv.academic_year || "—";
		const i_date = inv.invoice_date   ? frappe.datetime.str_to_user(inv.invoice_date) : "—";
		const d_date = inv.due_date       ? frappe.datetime.str_to_user(inv.due_date)     : "—";
		const net    = fmt_inr(inv.final_payable_amount);
		const paid   = fmt_inr(inv.paid_amount);
		const due    = fmt_inr(Math.max(inv.outstanding_amount || 0, 0));
		const row_bg = idx % 2 === 0 ? "#fff" : "#f9fafb";

		return `
		<tr style="background:${row_bg};">
			<td style="padding:10px 12px;font-weight:600;color:#1f2937;">${inv.name}</td>
			<td style="padding:10px 12px;color:#374151;">${term}</td>
			<td style="padding:10px 12px;color:#6b7280;font-size:12px;">${i_date}</td>
			<td style="padding:10px 12px;color:#6b7280;font-size:12px;">${d_date}</td>
			<td style="padding:10px 12px;font-weight:600;">${net}</td>
			<td style="padding:10px 12px;color:#16a34a;font-weight:600;">${paid}</td>
			<td style="padding:10px 12px;color:#dc2626;font-weight:600;">${due}</td>
			<td style="padding:10px 12px;">${badge(inv.status)}</td>
			<td style="padding:10px 12px;text-align:center;">
				<button class="btn btn-xs sp-inv-dl-btn"
					data-invoice="${inv.name}"
					style="background:#1a3c6e;color:#fff;border:none;border-radius:6px;
					       padding:5px 12px;font-size:12px;font-weight:600;cursor:pointer;
					       white-space:nowrap;">
					⬇ Receipt
				</button>
			</td>
		</tr>`;
	}).join("");

	const inv_tab_html = invoices.length
		? `<div style="overflow-x:auto;">
			<table class="sp-fee-table">
				<thead><tr>
					<th>Invoice #</th><th>Term</th><th>Invoice Date</th><th>Due Date</th>
					<th>Net Payable</th><th>Paid</th><th>Outstanding</th><th>Status</th>
					<th style="text-align:center;">Download</th>
				</tr></thead>
				<tbody>${inv_rows}</tbody>
			</table>
		</div>
		<p style="font-size:11px;color:#9ca3af;margin-top:8px;">
			${invoices.length} invoice(s) found for <strong>${student_label}</strong>
		</p>`
		: `<p style="color:#6b7280;margin-top:12px;">No fee invoices found for this student.</p>`;

	// ── Tab 2: Fee Demand Receipts ────────────────────────────────────────────
	const dem_rows = demands.map((dem, idx) => {
		const label   = dem.description || dem.fee_component || dem.name;
		const due     = dem.due_date ? frappe.datetime.str_to_user(dem.due_date) : "—";
		const net     = fmt_inr(dem.net_payable);
		const paid    = fmt_inr(dem.paid_amount);
		const outstdg = fmt_inr(Math.max(dem.outstanding_amount || 0, 0));
		const row_bg  = idx % 2 === 0 ? "#fff" : "#f9fafb";
		const can_dl  = dem.status === "Paid" || dem.status === "Partially Paid";

		const dl_btn = can_dl
			? `<button class="btn btn-xs sp-dem-dl-btn"
				data-demand="${dem.name}"
				style="background:#7c3aed;color:#fff;border:none;border-radius:6px;
				       padding:5px 12px;font-size:12px;font-weight:600;cursor:pointer;
				       white-space:nowrap;">
				⬇ Receipt
			</button>`
			: `<span style="color:#9ca3af;font-size:11px;">—</span>`;

		return `
		<tr style="background:${row_bg};">
			<td style="padding:10px 12px;font-weight:600;color:#1f2937;">${dem.name}</td>
			<td style="padding:10px 12px;color:#374151;">${label}</td>
			<td style="padding:10px 12px;color:#6b7280;font-size:12px;">${due}</td>
			<td style="padding:10px 12px;font-weight:600;">${net}</td>
			<td style="padding:10px 12px;color:#16a34a;font-weight:600;">${paid}</td>
			<td style="padding:10px 12px;color:#dc2626;font-weight:600;">${outstdg}</td>
			<td style="padding:10px 12px;">${badge(dem.status)}</td>
			<td style="padding:10px 12px;text-align:center;">${dl_btn}</td>
		</tr>`;
	}).join("");

	const dem_tab_html = demands.length
		? `<div style="overflow-x:auto;">
			<table class="sp-fee-table sp-dem-theme">
				<thead><tr>
					<th>Demand #</th><th>Description</th><th>Due Date</th>
					<th>Net Payable</th><th>Paid</th><th>Outstanding</th>
					<th>Status</th><th style="text-align:center;">Receipt</th>
				</tr></thead>
				<tbody>${dem_rows}</tbody>
			</table>
		</div>
		<p style="font-size:11px;color:#9ca3af;margin-top:8px;">
			${demands.length} demand(s) found for <strong>${student_label}</strong>
		</p>`
		: `<p style="color:#6b7280;margin-top:12px;">No additional fee demands found for this student.</p>`;

	// ── Combined HTML with tab bar ────────────────────────────────────────────
	const combined_html = `
	<style>
		.sp-fee-table { width:100%; border-collapse:collapse; font-family:inherit; }
		.sp-fee-table th { background:#1a3c6e; color:#fff; padding:10px 12px;
		                   font-size:11px; font-weight:700; text-transform:uppercase;
		                   letter-spacing:0.04em; text-align:left; }
		.sp-fee-table tr:hover td { background:#eff6ff !important; }
		.sp-fee-table.sp-dem-theme th { background:#7c3aed; }
		.sp-fee-table.sp-dem-theme tr:hover td { background:#f5f3ff !important; }
		.sp-tab-bar { display:flex; gap:4px; margin-bottom:14px; border-bottom:2px solid #e5e7eb; padding-bottom:0; }
		.sp-tab-btn { padding:8px 20px; border:none; background:none; cursor:pointer;
		              font-size:13px; font-weight:600; color:#6b7280; border-bottom:3px solid transparent;
		              margin-bottom:-2px; border-radius:4px 4px 0 0; }
		.sp-tab-btn.active { color:#1a3c6e; border-bottom-color:#1a3c6e; }
		.sp-tab-btn.active.dem-tab { color:#7c3aed; border-bottom-color:#7c3aed; }
		.sp-tab-panel { display:none; } .sp-tab-panel.active { display:block; }
	</style>
	<div class="sp-tab-bar">
		<button class="sp-tab-btn active" data-tab="invoices">
			Fee Invoices
			<span style="background:#dbeafe;color:#1e40af;padding:1px 7px;border-radius:99px;
			      font-size:10px;font-weight:700;margin-left:4px;">${invoices.length}</span>
		</button>
		<button class="sp-tab-btn dem-tab" data-tab="demands">
			Demand Receipts
			<span style="background:#ede9fe;color:#7c3aed;padding:1px 7px;border-radius:99px;
			      font-size:10px;font-weight:700;margin-left:4px;">${demands.length}</span>
		</button>
	</div>
	<div class="sp-tab-panel active" id="sp-panel-invoices">${inv_tab_html}</div>
	<div class="sp-tab-panel"        id="sp-panel-demands">${dem_tab_html}</div>`;

	const dlg = new frappe.ui.Dialog({
		title:  `Fee Records — ${student_label}`,
		fields: [{ fieldtype: "HTML", fieldname: "fee_tabs", options: combined_html }],
		size:   "extra-large",
	});
	dlg.show();

	// ── Tab switching ─────────────────────────────────────────────────────────
	dlg.$wrapper.on("click", ".sp-tab-btn", function () {
		const tab = $(this).data("tab");
		dlg.$wrapper.find(".sp-tab-btn").removeClass("active");
		$(this).addClass("active");
		dlg.$wrapper.find(".sp-tab-panel").removeClass("active");
		dlg.$wrapper.find(`#sp-panel-${tab}`).addClass("active");
	});

	// ── Invoice PDF download ──────────────────────────────────────────────────
	// Use window.open() — avoids Frappe's request.js which can trigger logout on
	// any concurrent 403 (e.g. route_history permission check).
	dlg.$wrapper.on("click", ".sp-inv-dl-btn", function () {
		const btn      = $(this);
		const inv_name = btn.data("invoice");
		const orig     = btn.html();
		btn.prop("disabled", true).text("…");

		const csrf = frappe.csrf_token || "";
		const url  = `/api/method/slcm.api.student_portal.download_fee_invoice_admin`
		           + `?invoice_name=${encodeURIComponent(inv_name)}`
		           + (csrf ? `&X-Frappe-CSRF-Token=${encodeURIComponent(csrf)}` : "");
		window.open(url, "_blank");
		frappe.show_alert({ message: `Downloading Invoice ${inv_name}…`, indicator: "blue" });

		setTimeout(() => {
			btn.html("✔ Done").css("background", "#16a34a");
			setTimeout(() => { btn.html(orig).css("background", "#1a3c6e").prop("disabled", false); }, 2500);
		}, 600);
	});

	// ── Demand Receipt download ───────────────────────────────────────────────
	// Fee Payment Demand Row has no public permissions, so we use a server-side
	// whitelisted function that runs with ignore_permissions to get the receipt.
	dlg.$wrapper.on("click", ".sp-dem-dl-btn", function () {
		const btn      = $(this);
		const dem_name = btn.data("demand");
		const orig     = btn.html();
		btn.prop("disabled", true).text("…");

		frappe.call({
			method: "slcm.slcm.doctype.student_master.student_master.get_fee_demand_receipt",
			args:   { fee_demand_name: dem_name },
			callback: function (r) {
				const info = r.message;
				if (!info || !info.receipt) {
					frappe.msgprint({
						title:     __("Receipt Not Found"),
						message:   __("No receipt has been generated for this demand yet."),
						indicator: "orange",
					});
					btn.html(orig).prop("disabled", false);
					return;
				}
				const csrf = frappe.csrf_token || "";
				const url  = `/api/method/slcm.api.student_portal.download_fee_demand_receipt_admin`
				           + `?receipt_name=${encodeURIComponent(info.receipt)}`
				           + `&fee_demand_name=${encodeURIComponent(info.fee_demand)}`
				           + (csrf ? `&X-Frappe-CSRF-Token=${encodeURIComponent(csrf)}` : "");
				window.open(url, "_blank");
				frappe.show_alert({ message: `Downloading receipt for ${dem_name}…`, indicator: "blue" });

				setTimeout(() => {
					btn.html("✔ Done").css("background", "#16a34a");
					setTimeout(() => { btn.html(orig).css("background", "#7c3aed").prop("disabled", false); }, 2500);
				}, 600);
			},
			error: function () {
				frappe.show_alert({ message: __("Failed to find receipt."), indicator: "red" });
				btn.html(orig).prop("disabled", false);
			},
		});
	});
}

/* ── Change Fee Structure Dialog ─────────────────────────────────────────────
   Lets admin/FINO officers switch the fee structure for a single student,
   providing a mandatory reason that is saved to the fee_structure_history table.
────────────────────────────────────────────────────────────────────────────── */
function _show_change_fee_structure_dialog(frm) {
	const current_fs    = frm.doc.fee_structure || "(none)";
	const current_total = frm.doc.total_program_fee || 0;

	const d = new frappe.ui.Dialog({
		title: __("Change Fee Structure"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<div class="alert alert-warning" style="margin-bottom:12px;">
					<strong>Current Fee Structure:</strong> ${frappe.utils.escape_html(current_fs)}
					&nbsp;&nbsp;|&nbsp;&nbsp;
					<strong>Total Fee:</strong> ₹${parseFloat(current_total).toLocaleString("en-IN")}
				</div>`,
			},
			{
				fieldtype: "Link",
				fieldname: "new_fee_structure",
				label:     __("New Fee Structure"),
				options:   "Fee Structure",
				reqd:      1,
				filters:   { status: "Active", applicable: "Student" },
				onchange() {
					const fs_val = d.get_value("new_fee_structure");
					if (!fs_val) return;
					frappe.call({
						method: "slcm.slcm.doctype.student_master.student_master.get_fee_structure_details",
						args: { fee_structure: fs_val },
						callback(r) {
							const data = r && r.message;
							if (!data) return;
							let info = `<strong>${frappe.utils.escape_html(data.fee_structure_name)}</strong>`;
							info += ` &nbsp;·&nbsp; Total: <strong>₹${parseFloat(data.total_amount).toLocaleString("en-IN")}</strong>`;
							if (data.valid_from) {
								info += ` &nbsp;·&nbsp; Valid: ${frappe.datetime.str_to_user(data.valid_from)}`;
								if (data.valid_until) info += ` – ${frappe.datetime.str_to_user(data.valid_until)}`;
							}
							info += ` &nbsp;·&nbsp; <span style="color:${data.status === 'Active' ? '#16a34a' : '#d97706'};">${data.status}</span>`;
							d.fields_dict.fs_preview.$wrapper.html(
								`<div style="padding:8px 12px;background:#f0fdf4;border:1px solid #bbf7d0;
								border-radius:8px;font-size:12.5px;margin-bottom:4px;">${info}</div>`
							);
						},
					});
				},
			},
			{
				fieldtype: "HTML",
				fieldname: "fs_preview",
				options:   "",
			},
			{
				fieldtype: "Small Text",
				fieldname: "reason",
				label:     __("Reason for Change"),
				reqd:      1,
				description: __("This will be recorded in the Fee Structure History for audit purposes."),
			},
		],
		primary_action_label: __("Apply Change"),
		primary_action(values) {
			if (!values.new_fee_structure || !values.reason || !values.reason.trim()) {
				frappe.msgprint({ title: __("Required"), message: __("Please fill all required fields."), indicator: "orange" });
				return;
			}
			if (values.new_fee_structure === frm.doc.fee_structure) {
				frappe.msgprint({ title: __("No Change"), message: __("The selected Fee Structure is the same as the current one."), indicator: "orange" });
				return;
			}

			d.hide();
			frappe.dom.freeze(__("Applying fee structure change…"));

			frappe.call({
				method: "slcm.slcm.doctype.student_master.student_master.change_fee_structure_admin",
				args: {
					student_name:      frm.doc.name,
					new_fee_structure: values.new_fee_structure,
					reason:            values.reason.trim(),
				},
				callback(r) {
					frappe.dom.unfreeze();
					const res = r && r.message;
					if (!res || res.status !== "success") {
						frappe.msgprint({ title: __("Error"), message: __("Failed to apply change. Check Error Log."), indicator: "red" });
						return;
					}
					let validity = "";
					if (res.valid_from) {
						validity = " · Valid from " + frappe.datetime.str_to_user(res.valid_from);
						if (res.valid_until) validity += " to " + frappe.datetime.str_to_user(res.valid_until);
					}
					frappe.show_alert({
						message: __("Fee Structure changed to {0} — ₹{1}{2}", [
							res.fee_structure_name,
							frappe.utils.fmt_money(res.total_program_fee, 0, "INR"),
							validity,
						]),
						indicator: "green",
					});
					frm.reload_doc();
				},
				error() {
					frappe.dom.unfreeze();
					frappe.show_alert({ message: __("Error applying change. Check Error Log."), indicator: "red" });
				},
			});
		},
	});

	d.show();
}

function show_status_transition_dialog(frm, data) {
	const current_status = data.current_status || "Selected";
	const available_actions = data.available_actions || [];

	if (available_actions.length === 0) {
		frappe.msgprint({
			title: __("No Actions Available"),
			message: __("You do not have permission to change the status from {0}.", [
				current_status,
			]),
			indicator: "orange",
		});
		return;
	}

	// Create dialog
	let dialog = new frappe.ui.Dialog({
		title: __("Update Registration Status"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<div class="alert alert-info">
					<strong>Current Status:</strong> ${current_status}
				</div>`,
			},
			{
				fieldtype: "Select",
				fieldname: "new_status",
				label: __("New Status"),
				options: available_actions.map((a) => a.next_state).join("\n"),
				reqd: 1,
			},
			{
				fieldtype: "Small Text",
				fieldname: "remarks",
				label: __("Remarks"),
				reqd: 1,
			},
		],
		primary_action_label: __("Update Status"),
		primary_action: function () {
			const values = dialog.get_values();
			if (!values.new_status) {
				frappe.msgprint({
					title: __("Required"),
					message: __("Please select a new status"),
					indicator: "orange",
				});
				return;
			}

			if (!values.remarks || !values.remarks.trim()) {
				frappe.msgprint({
					title: __("Required"),
					message: __("Please enter remarks"),
					indicator: "orange",
				});
				return;
			}

			let confirm_message = __("Are you sure you want to change status from <b>{0}</b> to <b>{1}</b>?", [
				current_status,
				values.new_status,
			]);

			if (values.new_status === "Re-Open") {
				confirm_message = __("Are you sure you want to <b>Re-Open</b> this application? <br>This might require re-verification of all details.");
			}


			// Confirm action
			frappe.confirm(
				confirm_message,
				function () {
					// Yes
					frappe.call({
						method: "slcm.slcm.doctype.student_master.student_master.update_registration_status",
						args: {
							student_id: frm.doc.name,
							new_status: values.new_status,
							remarks: values.remarks,
						},
						freeze: true,
						freeze_message: __("Updating status..."),
						callback: function (r) {
							if (r.message && r.message.status === "success") {
								frappe.show_alert({
									message: r.message.message,
									indicator: "green",
								});
								dialog.hide();
								frm.reload_doc();
							} else {
								frappe.msgprint({
									title: __("Error"),
									message: r.message
										? r.message.message || r.message
										: __("Failed to update status"),
									indicator: "red",
								});
							}
						},
						error: function (r) {
							frappe.msgprint({
								title: __("Error"),
								message:
									r.message || __("Failed to update status. Please try again."),
								indicator: "red",
							});
						},
					});
				},
				function () {
					// No
					dialog.hide();
				}
			);
		},
	});

	dialog.show();
}

/* ── Finance Tab: Analytics strip ────────────────────────────────────────────
   Renders a compact analytics bar above the Fee Details section
   whenever the Finance tab is opened.  Uses the fee_payment_log section's
   HTML field if present, otherwise silently does nothing.
────────────────────────────────────────────────────────────────────────────── */
const _FEE_STATUS_BADGE = {
	"Paid":              { bg: "#dcfce7", text: "#166534" },
	"Partially Paid":    { bg: "#fef3c7", text: "#92400e" },
	"Unpaid":            { bg: "#fee2e2", text: "#991b1b" },
	"Payment Initiated": { bg: "#dbeafe", text: "#1e40af" },
	"Authorized":        { bg: "#d1fae5", text: "#065f46" },
	"Payment Failed":    { bg: "#fee2e2", text: "#991b1b" },
	"Payment Cancelled": { bg: "#fef3c7", text: "#92400e" },
	"Refunded":          { bg: "#ede9fe", text: "#4c1d95" },
};

function _render_finance_tab_analytics(frm) {
	if (frm.is_new()) return;

	// Inject the analytics strip into the fee_payment_log_section header area
	// We target the section heading of the Payment Log collapsible section
	const status     = frm.doc.fee_payment_status || "";
	const sc         = _FEE_STATUS_BADGE[status] || { bg: "#f3f4f6", text: "#374151" };
	const status_badge = status
		? `<span style="display:inline-block;background:${sc.bg};color:${sc.text};
		               padding:3px 14px;border-radius:20px;font-size:12px;
		               font-weight:700;letter-spacing:.02em;">${status}</span>`
		: "";

	// Render into the fee_details_section heading using a subtle top banner
	frappe.call({
		method: "slcm.slcm.doctype.student_master.student_master.get_payment_analytics",
		args:   { student_name: frm.doc.name },
		callback: function (r) {
			const a = (r && r.message) || {};
			if (!a.total_attempts) return;

			const last_ts = a.last_attempt
				? frappe.datetime.str_to_user(a.last_attempt)
				: "—";
			const strip_html = `
			<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;
			            padding:12px 16px;margin:0 0 14px 0;display:flex;
			            flex-wrap:wrap;gap:16px;align-items:center;">
				<div style="font-size:12px;font-weight:600;color:#64748b;
				            text-transform:uppercase;letter-spacing:.05em;">
					Payment Summary
				</div>
				<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;">
					${_mini_stat("Attempts",   a.total_attempts, "#3b82f6")}
					${_mini_stat("Successful", a.successful,     "#16a34a")}
					${_mini_stat("Failed",     a.failed,         "#ef4444")}
					${_mini_stat("Cancelled",  a.cancelled,      "#f59e0b")}
					${_mini_stat("Refunded",   a.refunded,       "#6366f1")}
				</div>
				<div style="margin-left:auto;font-size:11px;color:#94a3b8;">
					Last attempt: ${last_ts}
				</div>
				${status_badge}
			</div>`;

			// Inject into the fee_payment_log_section's wrapper
			const $section = frm.get_field("fee_payment_log_section");
			if ($section && $section.$wrapper) {
				const $existing = $section.$wrapper.find(".finance-analytics-strip");
				if ($existing.length) {
					$existing.replaceWith(`<div class="finance-analytics-strip">${strip_html}</div>`);
				} else {
					$section.$wrapper.prepend(`<div class="finance-analytics-strip">${strip_html}</div>`);
				}
			}
		},
		error: function () { /* silent */ },
	});
}

function _mini_stat(label, value, color, raw) {
	const val_html = raw ? value
		: `<span style="font-size:15px;font-weight:800;color:${color};">${value}</span>`;
	return `<div style="text-align:center;line-height:1.3;">
		${val_html}
		<div style="font-size:10px;color:#94a3b8;font-weight:600;">${label}</div>
	</div>`;
}

/* ── Payment Logs Dialog ──────────────────────────────────────────────────────
   Professional timeline view of all payment attempts for a student.
   Shows colour-coded events, gateway responses (expandable JSON), analytics.
────────────────────────────────────────────────────────────────────────────── */
function _show_payment_logs_dialog(frm) {
	const student_label = [frm.doc.first_name, frm.doc.last_name]
		.filter(Boolean).join(" ") || frm.doc.name;

	const loading_html = `<div style="text-align:center;padding:40px 0;color:#6b7280;">
		<div style="font-size:24px;margin-bottom:8px;">⏳</div>
		<div>Loading payment history…</div></div>`;

	const dialog = new frappe.ui.Dialog({
		title:  __("Payment Audit Trail — {0}", [student_label]),
		size:   "extra-large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "analytics_html",
			},
			{
				fieldtype: "HTML",
				fieldname: "logs_html",
			},
		],
	});

	// Apply wider dialog styling
	dialog.$wrapper.find(".modal-dialog").css({ "max-width": "960px" });
	dialog.show();

	// Set loading state
	dialog.fields_dict.analytics_html.$wrapper.html(loading_html);
	dialog.fields_dict.logs_html.$wrapper.html("");

	// Fetch analytics + logs in parallel
	const p_analytics = new Promise((resolve) =>
		frappe.call({
			method: "slcm.slcm.doctype.student_master.student_master.get_payment_analytics",
			args:   { student_name: frm.doc.name },
			callback: r => resolve((r && r.message) || {}),
			error:    () => resolve({}),
		})
	);
	const p_logs = new Promise((resolve) =>
		frappe.call({
			method: "slcm.slcm.doctype.student_master.student_master.get_payment_logs",
			args:   { student_name: frm.doc.name },
			callback: r => resolve((r && r.message) || []),
			error:    () => resolve([]),
		})
	);

	Promise.all([p_analytics, p_logs]).then(([analytics, logs]) => {
		dialog.fields_dict.analytics_html.$wrapper.html(
			_render_payment_analytics(analytics)
		);

		// Render timeline HTML (returns static markup; filter wiring done below)
		const timeline_html = _render_payment_timeline(logs);
		const $logs_wrap = dialog.fields_dict.logs_html.$wrapper;
		$logs_wrap.html(timeline_html);

		// ── Wire filters directly against the rendered DOM inside this dialog ──
		// We scope every query to $logs_wrap so there's no cross-dialog pollution.
		// Track active tab via a plain variable — no jQuery .data() caching issues
		let _active_src = "invoice";

		function _apply_filters() {
			const q      = ($logs_wrap.find("#plog-search").val() || "").toLowerCase().trim();
			const status = $logs_wrap.find("#plog-filter-status").val() || "";
			let visible  = 0;

			$logs_wrap.find(".plog-item").each(function () {
				// Use getAttribute to always read the real DOM value
				const text      = (this.getAttribute("data-search-text") || "").toLowerCase();
				const evt       = this.getAttribute("data-event") || "";
				const src       = this.getAttribute("data-src") || "invoice";
				const match_q   = !q      || text.indexOf(q) !== -1;
				const match_st  = !status || evt === status;
				const match_src = _active_src === "all" || src === _active_src;
				const show      = match_q && match_st && match_src;
				$(this).toggleClass("hidden", !show);
				if (show) visible++;
			});

			$logs_wrap.find("#plog-no-results")
				.toggle(visible === 0 && logs.length > 0);
		}

		$logs_wrap.on("input",  "#plog-search",        _apply_filters);
		$logs_wrap.on("change", "#plog-filter-status", _apply_filters);

		// ── Tab switching ───────────────────────────────────────────────────
		$logs_wrap.on("click", ".plog-tab", function () {
			_active_src = this.getAttribute("data-src") || "all";

			// Update visual styles on all tabs
			$logs_wrap.find(".plog-tab").each(function () {
				const active = this.getAttribute("data-src") === _active_src;
				$(this).css({
					"border-bottom-color": active ? "#6366f1" : "transparent",
					"color":               active ? "#6366f1" : "#6b7280",
					"font-weight":         active ? "600"     : "500",
				});
			});

			_apply_filters();
		});

		// ── Expand/collapse gateway response blocks ─────────────────────────
		$logs_wrap.on("click", ".plog-toggle-json", function () {
			const target = $(this).data("target");
			const $block = $logs_wrap.find("#" + target);
			const isOpen = $block.is(":visible");
			$block.toggle(!isOpen);
			$(this).text(isOpen ? "▶ Show Gateway Response" : "▼ Hide Gateway Response");
		});

		// ── Download CSV ────────────────────────────────────────────────────
		$logs_wrap.on("click", "#plog-download-csv", function () {
			_download_logs_csv(logs, student_label);
		});

		// ── Download Receipt (Fee Invoice print) ────────────────────────────
		$logs_wrap.on("click", ".plog-download-receipt", function () {
			const inv = $(this).data("invoice");
			if (!inv) return;
			const url = frappe.urllib.get_full_url(
				`/api/method/frappe.utils.print_format.download_pdf?doctype=Fee+Invoice&name=${encodeURIComponent(inv)}&format=Fee+Invoice+Receipt&no_letterhead=0`
			);
			window.open(url, "_blank");
		});

		// ── Download Receipt (Fee Demand receipt PDF) ────────────────────────
		$logs_wrap.on("click", ".plog-download-demand-receipt", function () {
			const btn      = $(this);
			const dem_name = btn.data("demand");
			if (!dem_name) return;
			const orig = btn.html();
			btn.prop("disabled", true).text("…");

			frappe.call({
				method: "slcm.slcm.doctype.student_master.student_master.get_fee_demand_receipt",
				args:   { fee_demand_name: dem_name },
				callback: function (r) {
					const info = r.message;
					if (!info || !info.receipt) {
						frappe.msgprint({
							title:     __("Receipt Not Found"),
							message:   __("No receipt has been generated for this demand yet."),
							indicator: "orange",
						});
						btn.html(orig).prop("disabled", false);
						return;
					}
					const csrf = frappe.csrf_token || "";
					const url  = `/api/method/slcm.api.student_portal.download_fee_demand_receipt_admin`
					           + `?receipt_name=${encodeURIComponent(info.receipt)}`
					           + `&fee_demand_name=${encodeURIComponent(info.fee_demand)}`
					           + (csrf ? `&X-Frappe-CSRF-Token=${encodeURIComponent(csrf)}` : "");
					window.open(url, "_blank");
					frappe.show_alert({ message: `Downloading receipt for ${dem_name}…`, indicator: "blue" });
					setTimeout(() => {
						btn.html("✔ Done").css("background", "#16a34a");
						setTimeout(() => { btn.html(orig).css("background", "#7c3aed").prop("disabled", false); }, 2500);
					}, 600);
				},
				error: function () {
					frappe.show_alert({ message: __("Failed to find receipt."), indicator: "red" });
					btn.html(orig).prop("disabled", false);
				},
			});
		});

		// ── Open linked record on card click ───────────────────────────────
		$logs_wrap.on("click", ".plog-card", function (e) {
			// Don't navigate if clicking a button inside the card
			if ($(e.target).closest("button").length) return;

			const invoice = this.getAttribute("data-open-invoice");
			const demand  = this.getAttribute("data-open-demand");

			if (demand) {
				frappe.set_route("Form", "Fee Demand", demand);
			} else if (invoice) {
				frappe.set_route("Form", "Fee Invoice", invoice);
			}
		});

		// Hover highlight for clickable cards
		$logs_wrap.on("mouseenter", ".plog-card[data-open-invoice], .plog-card[data-open-demand]", function () {
			$(this).css("box-shadow", "0 0 0 2px #6366f1, 0 2px 8px rgba(99,102,241,.15)");
		}).on("mouseleave", ".plog-card[data-open-invoice], .plog-card[data-open-demand]", function () {
			$(this).css("box-shadow", "0 1px 3px rgba(0,0,0,.06)");
		});

		// Apply initial filter so the default Fee Invoice tab hides demand entries on load
		_apply_filters();
	});
}

function _render_payment_analytics(a) {
	if (!a || !a.total_attempts) {
		return `<div style="padding:12px 0 4px;color:#6b7280;font-style:italic;font-size:13px;">
			No payment activity recorded yet.</div>`;
	}

	const last_ts = a.last_attempt
		? frappe.datetime.str_to_user(a.last_attempt)
		: "—";

	const tiles = [
		{ label: "Total Attempts", value: a.total_attempts, color: "#1e40af", bg: "#dbeafe" },
		{ label: "Successful",     value: a.successful,     color: "#166534", bg: "#dcfce7" },
		{ label: "Failed",         value: a.failed,         color: "#991b1b", bg: "#fee2e2" },
		{ label: "Cancelled",      value: a.cancelled,      color: "#92400e", bg: "#fef3c7" },
		{ label: "Refunded",       value: a.refunded,       color: "#4b5563", bg: "#f3f4f6" },
	];

	const tiles_html = tiles.map(t => `
		<div style="background:${t.bg};border-radius:10px;padding:14px 18px;text-align:center;
		            min-width:100px;flex:1;">
			<div style="font-size:22px;font-weight:800;color:${t.color};">${t.value}</div>
			<div style="font-size:11px;color:${t.color};font-weight:600;margin-top:2px;">
				${t.label}</div>
		</div>`).join("");

	return `
	<style>
		.plog-analytics-row { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:16px; }
	</style>
	<div style="padding:4px 0 8px;">
		<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
			<span style="font-size:14px;font-weight:700;color:#374151;">Payment Analytics</span>
			<span style="font-size:12px;color:#6b7280;">Last attempt: ${last_ts}</span>
		</div>
		<div class="plog-analytics-row">${tiles_html}</div>
	</div>`;
}

// Event type → {icon, colour scheme}
const _PLOG_STYLE = {
	"Payment Initiated":    { icon: "🚀", dot: "#3b82f6", badge_bg: "#dbeafe", badge_text: "#1e40af" },
	"Authorized":           { icon: "✅", dot: "#10b981", badge_bg: "#d1fae5", badge_text: "#065f46" },
	"Captured":             { icon: "💰", dot: "#16a34a", badge_bg: "#dcfce7", badge_text: "#166534" },
	"Payment Recorded":     { icon: "💰", dot: "#16a34a", badge_bg: "#dcfce7", badge_text: "#166534" },
	"Payment Failed":       { icon: "❌", dot: "#ef4444", badge_bg: "#fee2e2", badge_text: "#991b1b" },
	"Payment Cancelled":    { icon: "🚫", dot: "#f59e0b", badge_bg: "#fef3c7", badge_text: "#92400e" },
	"Refunded":             { icon: "↩️", dot: "#6366f1", badge_bg: "#ede9fe", badge_text: "#4c1d95" },
	"Partial Paid":         { icon: "⚡", dot: "#f97316", badge_bg: "#ffedd5", badge_text: "#7c2d12" },
	"Pending Verification": { icon: "⏳", dot: "#a855f7", badge_bg: "#f3e8ff", badge_text: "#581c87" },
	"Webhook Received":     { icon: "🔔", dot: "#06b6d4", badge_bg: "#cffafe", badge_text: "#155e75" },
	"Retry Initiated":      { icon: "🔁", dot: "#f59e0b", badge_bg: "#fef3c7", badge_text: "#92400e" },
	"Manual Status Update": { icon: "✏️", dot: "#6b7280", badge_bg: "#f3f4f6", badge_text: "#374151" },
	"Bulk Fee Update":      { icon: "📦", dot: "#6b7280", badge_bg: "#f3f4f6", badge_text: "#374151" },
	"Fee Structure Changed":{ icon: "🔧", dot: "#6b7280", badge_bg: "#f3f4f6", badge_text: "#374151" },
};

function _render_payment_timeline(logs) {
	if (!logs || !logs.length) {
		return `<div style="text-align:center;padding:40px 0;color:#6b7280;">
			<div style="font-size:32px;margin-bottom:8px;">📭</div>
			<div style="font-size:15px;font-weight:600;">No payment logs found</div>
			<div style="font-size:12px;margin-top:4px;">
				Payment activity will appear here once initiated.</div>
		</div>`;
	}

	// Separate invoice vs demand logs
	const inv_logs = logs.filter(r => !r.fee_demand);
	const dem_logs = logs.filter(r => !!r.fee_demand);

	// Tab bar — Fee Invoice (default) and Fee Demand
	const toolbar = `
	<div class="plog-tab-bar" style="display:flex;gap:0;border-bottom:2px solid #e5e7eb;margin-bottom:16px;">
		<button class="plog-tab" data-src="invoice"
		        style="padding:8px 18px;font-size:13px;font-weight:600;border:none;
		               background:none;cursor:pointer;border-bottom:2.5px solid #6366f1;
		               color:#6366f1;margin-bottom:-2px;">
			📄 Fee Invoice <span style="background:#dbeafe;color:#1d4ed8;padding:1px 7px;border-radius:99px;font-size:10px;font-weight:700;margin-left:4px;">${inv_logs.length}</span>
		</button>
		<button class="plog-tab" data-src="demand"
		        style="padding:8px 18px;font-size:13px;font-weight:500;border:none;
		               background:none;cursor:pointer;border-bottom:2.5px solid transparent;
		               color:#6b7280;margin-bottom:-2px;">
			📋 Fee Demand <span style="background:#ede9fe;color:#7c3aed;padding:1px 7px;border-radius:99px;font-size:10px;font-weight:700;margin-left:4px;">${dem_logs.length}</span>
		</button>
	</div>
	<div style="display:flex;gap:10px;align-items:center;margin-bottom:14px;flex-wrap:wrap;">
		<input id="plog-search" type="text" placeholder="🔍 Search by event, demand/invoice ID, payment ID…"
		       style="flex:1;min-width:220px;border:1px solid #d1d5db;border-radius:8px;
		              padding:7px 12px;font-size:13px;outline:none;"/>
		<select id="plog-filter-status" style="border:1px solid #d1d5db;border-radius:8px;
		         padding:7px 12px;font-size:13px;outline:none;background:#fff;cursor:pointer;">
			<option value="">All Events</option>
			<option value="Payment Initiated">Payment Initiated</option>
			<option value="Captured">Captured / Paid</option>
			<option value="Payment Failed">Payment Failed</option>
			<option value="Payment Cancelled">Cancelled</option>
			<option value="Refunded">Refunded</option>
			<option value="Webhook Received">Webhook Received</option>
		</select>
		<button id="plog-download-csv"
		        style="background:#374151;color:#fff;border:none;border-radius:8px;
		               padding:7px 14px;font-size:13px;cursor:pointer;font-weight:600;
		               white-space:nowrap;">
			⬇ Export CSV
		</button>
	</div>`;

	const items_html = logs.map((row, idx) => {
		const style  = _PLOG_STYLE[row.event_type] || _PLOG_STYLE["Manual Status Update"];
		const ts     = row.timestamp ? frappe.datetime.str_to_user(row.timestamp) : "—";
		const amount = row.amount
			? "₹" + parseFloat(row.amount).toLocaleString("en-IN", { minimumFractionDigits: 0 })
			: "";

		const badge_html = `<span style="display:inline-block;background:${style.badge_bg};
			color:${style.badge_text};padding:2px 10px;border-radius:20px;
			font-size:11px;font-weight:700;white-space:nowrap;">${row.event_type}</span>`;

		// Detect source type via dedicated fee_demand field
		const is_demand = !!row.fee_demand;
		const source_badge = is_demand
			? `<span style="background:#ede9fe;color:#7c3aed;padding:1px 8px;border-radius:99px;font-size:10px;font-weight:700;margin-left:4px;">Fee Demand</span>`
			: (row.invoice ? `<span style="background:#eff6ff;color:#1d4ed8;padding:1px 8px;border-radius:99px;font-size:10px;font-weight:700;margin-left:4px;">Fee Invoice</span>` : "");

		// Receipt download — invoice events show invoice receipt; demand events show demand receipt
		const is_captured = ["Captured", "Payment Recorded"].includes(row.event_type);
		const receipt_btn = is_captured && row.invoice && !is_demand
			? `<button class="plog-download-receipt" data-invoice="${row.invoice}"
				style="margin-top:8px;background:#166534;color:#fff;border:none;border-radius:6px;
				       padding:4px 12px;font-size:11px;cursor:pointer;font-weight:600;margin-left:4px;">
				🧾 Download Receipt</button>`
			: is_captured && is_demand
			? `<button class="plog-download-demand-receipt" data-demand="${row.fee_demand}"
				style="margin-top:8px;background:#7c3aed;color:#fff;border:none;border-radius:6px;
				       padding:4px 12px;font-size:11px;cursor:pointer;font-weight:600;margin-left:4px;">
				🧾 Download Receipt</button>`
			: "";

		// Payer badge — shown prominently before other chips
		let payer_html = "";
		if (row.paid_by_role || row.paid_by_name) {
			const role_colors = {
				"Parent":  { bg: "#fef3c7", text: "#92400e", icon: "👨‍👩‍👧" },
				"Student": { bg: "#dbeafe", text: "#1e40af", icon: "🎓" },
				"Staff":   { bg: "#d1fae5", text: "#065f46", icon: "🏫" },
				"System":  { bg: "#f3f4f6", text: "#374151", icon: "⚙️" },
			};
			const rc = role_colors[row.paid_by_role] || { bg: "#f3f4f6", text: "#374151", icon: "👤" };
			const role_label = row.paid_by_role ? `${rc.icon} ${row.paid_by_role}` : "👤 Unknown";
			const name_part  = row.paid_by_name  ? ` — ${frappe.utils.escape_html(row.paid_by_name)}` : "";
			payer_html = `<span style="display:inline-block;background:${rc.bg};color:${rc.text};
				padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;
				white-space:nowrap;margin-left:6px;">${role_label}${name_part}</span>`;
		}

		// Meta chips
		let chips = [];
		if (row.fee_demand)           chips.push(`<span class="plog-chip">📋 ${row.fee_demand}</span>`);
		else if (row.invoice)         chips.push(`<span class="plog-chip">📄 ${row.invoice}</span>`);
		if (row.razorpay_payment_id)  chips.push(`<span class="plog-chip">💳 ${row.razorpay_payment_id}</span>`);
		if (row.razorpay_order_id)    chips.push(`<span class="plog-chip">🗂 ${row.razorpay_order_id}</span>`);
		if (row.transaction_id)       chips.push(`<span class="plog-chip">🔖 ${row.transaction_id}</span>`);
		if (row.payment_method)       chips.push(`<span class="plog-chip">💡 ${row.payment_method}</span>`);
		if (row.payment_mode)         chips.push(`<span class="plog-chip">🏦 ${row.payment_mode}</span>`);
		if (row.attempt_type)         chips.push(`<span class="plog-chip">🔄 ${row.attempt_type}</span>`);
		if (row.retry_count > 0)      chips.push(`<span class="plog-chip">🔁 Retry #${row.retry_count}</span>`);
		if (row.webhook_status && row.webhook_status !== "Not Applicable")
			chips.push(`<span class="plog-chip">🔔 Webhook: ${row.webhook_status}</span>`);
		if (row.ip_address)           chips.push(`<span class="plog-chip">🌐 ${row.ip_address}</span>`);
		if (row.triggered_by)         chips.push(`<span class="plog-chip">👤 ${row.triggered_by}</span>`);

		// Status transition
		let transition = "";
		if (row.from_status || row.to_status) {
			const from_color = row.from_status ? "#6b7280" : "#d1d5db";
			const to_color   = row.to_status   ? "#1f2937" : "#d1d5db";
			transition = `<div style="font-size:11px;margin-top:6px;color:#6b7280;">
				<span style="color:${from_color}">${row.from_status || "—"}</span>
				<span style="margin:0 6px;color:#9ca3af;">→</span>
				<span style="color:${to_color};font-weight:600;">${row.to_status || "—"}</span>
			</div>`;
		}

		// Error / failure info
		let error_html = "";
		if (row.failure_reason || row.error_message) {
			const msg = row.failure_reason || row.error_message;
			error_html = `<div style="margin-top:6px;padding:6px 10px;background:#fee2e2;
				border-left:3px solid #ef4444;border-radius:4px;font-size:12px;color:#991b1b;">
				⚠ ${msg}</div>`;
		}

		// Remarks
		const remarks_html = row.remarks
			? `<div style="font-size:12px;color:#6b7280;margin-top:5px;font-style:italic;">
				${row.remarks}</div>` : "";

		// Gateway JSON toggle
		const json_id   = `plog-json-${idx}`;
		let json_html   = "";
		let toggle_html = "";
		if (row.gateway_response) {
			let pretty = row.gateway_response;
			try { pretty = JSON.stringify(JSON.parse(row.gateway_response), null, 2); } catch(e) {}
			toggle_html = `<button class="plog-toggle-json" data-target="${json_id}"
				style="margin-top:8px;background:none;border:1px solid #d1d5db;border-radius:6px;
				       padding:3px 10px;font-size:11px;cursor:pointer;color:#374151;font-weight:500;">
				▶ Show Gateway Response</button>`;
			json_html = `<div id="${json_id}" style="display:none;margin-top:6px;">
				<pre style="background:#1e293b;color:#e2e8f0;padding:12px;border-radius:8px;
				            font-size:11px;overflow-x:auto;max-height:240px;white-space:pre-wrap;
				            word-break:break-all;line-height:1.5;">${frappe.utils.escape_html(pretty)}</pre>
			</div>`;
		}

		const is_last = idx === logs.length - 1;
		const line_display = is_last ? "none" : "block";

		// source: "demand" for fee demand logs, "invoice" for everything else
		const item_source = is_demand ? "demand" : "invoice";

		const search_text = [
			row.event_type, row.invoice, row.fee_demand, row.razorpay_payment_id,
			row.transaction_id, row.triggered_by, row.paid_by_role, row.paid_by_name, row.remarks,
		].filter(Boolean).join(" ").toLowerCase()
		 .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

		return `
		<div class="plog-item" data-event="${row.event_type}"
		     data-src="${item_source}"
		     data-search-text="${search_text}"
		     style="display:flex;gap:0;margin-bottom:0;">
			<!-- Timeline spine -->
			<div style="display:flex;flex-direction:column;align-items:center;width:28px;flex-shrink:0;">
				<div style="width:14px;height:14px;border-radius:50%;background:${is_demand ? '#7c3aed' : style.dot};
				            margin-top:14px;flex-shrink:0;box-shadow:0 0 0 3px ${is_demand ? '#7c3aed' : style.dot}22;"></div>
				<div style="width:2px;flex:1;background:#e5e7eb;display:${line_display};
				            min-height:20px;"></div>
			</div>
			<!-- Content card — clickable to open the linked record -->
			<div class="plog-card"
			     ${row.invoice  ? `data-open-invoice="${row.invoice}"` : ""}
			     ${row.fee_demand ? `data-open-demand="${row.fee_demand}"` : ""}
			     style="flex:1;background:${is_demand ? '#faf5ff' : '#fff'};
			            border:1px solid ${is_demand ? '#ddd6fe' : '#e5e7eb'};
			            border-radius:10px;padding:12px 16px;margin:6px 0 6px 10px;
			            box-shadow:0 1px 3px rgba(0,0,0,.06);
			            ${(row.invoice || row.fee_demand) ? 'cursor:pointer;' : ''}">
				<div style="display:flex;justify-content:space-between;align-items:flex-start;
				            flex-wrap:wrap;gap:8px;">
					<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
						<span style="font-size:16px;">${is_demand ? '📋' : style.icon}</span>
						${badge_html}
						${source_badge}
						${payer_html}
						${amount ? `<span style="font-weight:700;font-size:14px;color:#1f2937;">${amount}</span>` : ""}
					</div>
					<div style="display:flex;align-items:center;gap:6px;">
						${receipt_btn}
						<span style="font-size:11px;color:#9ca3af;white-space:nowrap;">${ts}</span>
					</div>
				</div>
				${transition}
				${chips.length ? `<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;">${chips.join("")}</div>` : ""}
				${error_html}
				${remarks_html}
				${toggle_html}
				${json_html}
			</div>
		</div>`;
	}).join("");

	const styles = `
	<style>
		.plog-chip {
			background: #f3f4f6; color: #374151; padding: 2px 8px;
			border-radius: 20px; font-size: 11px; font-weight: 500;
			white-space: nowrap;
		}
		#plog-search:focus, #plog-filter-status:focus { border-color: #6366f1; }
		.plog-item { transition: opacity .15s; }
		.plog-item.hidden { display: none !important; }
	</style>`;

	return `
	${styles}
	${toolbar}
	<div id="plog-timeline" style="padding:4px 0;">
		${items_html}
	</div>
	<div id="plog-no-results" style="display:none;text-align:center;padding:30px 0;color:#6b7280;">
		No matching entries found.
	</div>`;
}

function _download_logs_csv(logs, student_label) {
	if (!logs || !logs.length) {
		frappe.show_alert({ message: __("No logs to export."), indicator: "orange" });
		return;
	}
	const cols = [
		"event_type", "timestamp", "amount", "currency", "invoice", "fee_demand",
		"payment_mode", "payment_method", "razorpay_payment_id",
		"razorpay_order_id", "transaction_id", "triggered_by",
		"paid_by_role", "paid_by_name",
		"attempt_type", "retry_count", "webhook_status",
		"from_status", "to_status", "ip_address",
		"error_message", "failure_reason", "remarks",
	];
	const esc = v => `"${String(v == null ? "" : v).replace(/"/g, '""')}"`;
	const header = cols.map(c => esc(c.replace(/_/g, " ").toUpperCase())).join(",");
	const body   = logs.map(r => cols.map(c => esc(r[c] ?? "")).join(",")).join("\n");
	const csv    = header + "\n" + body;
	const blob   = new Blob([csv], { type: "text/csv;charset=utf-8;" });
	const url    = URL.createObjectURL(blob);
	const a      = document.createElement("a");
	a.href       = url;
	a.download   = `payment_logs_${(student_label || "student").replace(/\s+/g, "_")}.csv`;
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
	URL.revokeObjectURL(url);
}

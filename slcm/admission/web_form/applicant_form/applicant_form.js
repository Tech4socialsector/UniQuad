
// Patch FormData to prevent Frappe core from overwriting/deleting files with the identical name
// Renames every uploaded File with a 12-char cryptographic hex suffix before it hits the server,
// so Frappe's native upload handler sets attached_to_* correctly and no backend rename is needed.
if (typeof FormData !== 'undefined' && !window._slcm_fd_patched) {
	window._slcm_fd_patched = true;
	var _orig_fd_append = FormData.prototype.append;
	FormData.prototype.append = function(name, value, filename) {
		if (value instanceof File) {
			var fname = filename || value.name;
			if (fname) {
				var parts = fname.split('.');
				var ext = parts.length > 1 ? parts.pop() : '';
				var base = parts.join('.');
				// 12-char cryptographic hex suffix (crypto.getRandomValues preferred, Math.random fallback)
				var suffix;
				try {
					suffix = Array.from(crypto.getRandomValues(new Uint8Array(6)),
						function(b) { return ('0' + b.toString(16)).slice(-2); }).join('');
				} catch(e) {
					suffix = Math.random().toString(36).substring(2, 14);
				}
				fname = base + '_' + suffix + (ext ? '.' + ext : '');
				try {
					value = new File([value], fname, { type: value.type });
				} catch(e) {}
				return _orig_fd_append.call(this, name, value, fname);
			}
		}
		return _orig_fd_append.apply(this, arguments);
	};
}


// Patch for Autocomplete initialization error
if (window.frappe && frappe.ui && frappe.ui.form && frappe.ui.form.ControlAutocomplete) {
	var _origAutocompleteValidate = frappe.ui.form.ControlAutocomplete.prototype.validate;
	frappe.ui.form.ControlAutocomplete.prototype.validate = function(value) {
		if (!this._list) return value;
		return _origAutocompleteValidate.call(this, value);
	};
}

// Patch for ControlPhone initialization error when selected_icon is not built
if (window.frappe && frappe.ui && frappe.ui.form && frappe.ui.form.ControlPhone) {
	var _origPhoneSetFormattedInput = frappe.ui.form.ControlPhone.prototype.set_formatted_input;
	frappe.ui.form.ControlPhone.prototype.set_formatted_input = async function(value) {
		if (!this.selected_icon && this.setup_country_code_picker) {
			try { this.setup_country_code_picker(); } catch(e) {}
		}
		if (!this.selected_icon) return;
		return _origPhoneSetFormattedInput.call(this, value);
	};
}

// ═══════════════════════════════════════════════════════════════════
//  SLCM — Applicant Web Form client script
//  Features:
//    • Silent fee recalculation on whether_scstobc_ncl change
//    • Save Draft button (always before the Next/Submit primary button)
//    • Application status badge near the applicant-ID heading
//    • Toast notifications — top-right
//    • Submit intercept: mandatory → eligibility (same modal as application_form showEligibilityModal) → fee/Razorpay → submit
//    • No live eligibility banner; query-string prefill for /applicant-form/new?...
// ═══════════════════════════════════════════════════════════════════

// ───────────────────────────────────────────────────────────────────
//  CSS
// ───────────────────────────────────────────────────────────────────
function _injectCSS() {
	if (document.getElementById('slcm-wf-css')) return;

	// ── Material Symbols Outlined (needed for nav + footer icons) ──
	if (!document.getElementById('slcm-material-icons')) {
		var iconLink = document.createElement('link');
		iconLink.id   = 'slcm-material-icons';
		iconLink.rel  = 'stylesheet';
		iconLink.href = 'https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=block';
		document.head.appendChild(iconLink);
	}

	var s = document.createElement('style');
	s.id = 'slcm-wf-css';
	s.textContent = [
		/* Save Draft button */
		'#slcm-save-draft-btn{display:inline-flex;align-items:center;gap:7px;' +
			'padding:7px 18px;border-radius:7px;font-size:13px;font-weight:300;cursor:pointer;' +
			'border:1.5px solid var(--slcm-primary,#1a73e8);background:#fff;color:var(--slcm-primary,#1a73e8);' +
			'transition:background .15s,color .15s;white-space:nowrap;margin-right:10px;}',
		'#slcm-save-draft-btn:hover:not(:disabled){background:color-mix(in srgb,var(--slcm-primary,#1a73e8) 8%,#fff);border-color:var(--slcm-primary,#1a73e8);}',
		'#slcm-save-draft-btn:disabled{opacity:.6;cursor:not-allowed;}',
		/* spinner keyframes */
		'@keyframes slcm-spin{to{transform:rotate(360deg)}}',
		/* ── Hide Frappe default Public Upload Warning ── */
		'.file-uploader .alert-warning{display:none!important;}',
		/* Toast — top-right */
		'#slcm-toast{position:fixed;top:40px;right:24px;z-index:2500000;max-width:min(420px,calc(100vw - 32px));' +
			'min-width:260px;max-width:min(440px,92vw);padding:13px 18px;border-radius:10px;' +
			'font-size:13.5px;font-weight:500;line-height:1.5;pointer-events:auto;' +
			'box-shadow:0 8px 32px rgba(0,0,0,.18);display:none;cursor:default;' +
			'transition:opacity .3s;}',
		'#slcm-toast.slcm-success{background:#f0fdf4;border:1.5px solid #86efac;color:#14532d;}',
		'#slcm-toast.slcm-error  {background:#fff2f2;border:1.5px solid #fca5a5;color:#991b1b;}',
		'#slcm-toast.slcm-info   {background:#eff6ff;border:1.5px solid #93c5fd;color:#1e3a5f;}',
		'#slcm-toast.slcm-warn   {background:#fffbeb;border:1.5px solid #fcd34d;color:#78350f;}',
		'@keyframes slcm-wf-modal-slide-up{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}' +
			/* Portal-themed programme picker (parity with application_form switch overlay) */
			'#slcm-wf-switch-program-overlay.slcm-portal-switch-shell{' +
			'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}' +
			'#slcm-wf-switch-program-overlay .slcm-portal-switch-card{' +
			'background:#fff;border-radius:24px;width:100%;max-width:440px;padding:32px;' +
			'box-shadow:0 25px 50px -12px rgba(0,0,0,0.3);animation:slcm-wf-modal-slide-up .3s cubic-bezier(0.16,1,0.3,1);}' +
			'#slcm-wf-switch-program-overlay .slcm-wf-switch-opt{' +
			'padding:14px 18px;border:1px solid #e2e8f0;border-radius:12px;cursor:pointer;margin-bottom:10px;' +
			'transition:all .2s ease;display:flex;align-items:center;gap:12px;background:#fff;}' +
			'#slcm-wf-switch-program-overlay .slcm-wf-switch-opt:hover{border-color:#1a3c6e;background:#f8fafc;}' +
			'#slcm-wf-switch-program-overlay .slcm-wf-switch-opt.selected{border-color:#1a3c6e;background:#eff6ff;box-shadow:0 0 0 1px #1a3c6e;}' +
			'#slcm-wf-switch-program-overlay .slcm-wf-switch-opt.selected .slcm-wf-switch-radio{border-color:#1a3c6e !important;}' +
			'#slcm-wf-switch-program-overlay .slcm-wf-switch-opt.selected .slcm-wf-switch-radio div{display:block !important;}' +
			'#slcm-wf-switch-program-overlay .slcm-wf-switch-opt.slcm-wf-switch-opt--applied{' +
			'opacity:0.72;cursor:not-allowed;pointer-events:none;border-color:#e2e8f0 !important;background:#f1f5f9 !important;box-shadow:none !important;}' +
			'#slcm-wf-switch-program-overlay .slcm-wf-switch-opt.slcm-wf-switch-opt--applied .slcm-wf-switch-applied-badge{' +
			'display:inline-block;margin-left:8px;font-size:var(--font-size-toast, 11px);font-weight:400;padding:2px 8px;border-radius:999px;background:#e2e8f0;color:#475569;}' +
			'#slcm-wf-switch-opts-container::-webkit-scrollbar{width:4px;}' +
			'#slcm-wf-switch-opts-container::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:4px;}' +
			'#slcm-wf-switch-program-overlay .slcm-portal-switch-actions .slcm-wf-switch-cancel-btn{' +
			'height:52px;border-radius:14px;border:none;background:#f1f5f9;font-weight:400;color:#475569;cursor:pointer;transition:background .15s;font-size:var(--font-size-body, 14px);font-family:var(--font-family, inherit);}' +
			'#slcm-wf-switch-program-overlay .slcm-portal-switch-actions .slcm-wf-switch-cancel-btn:hover{background:#e2e8f0;}' +
			'#slcm-wf-switch-program-overlay .slcm-portal-switch-actions #slcm-wf-confirm-switch-btn{' +
			'height:52px;border-radius:14px;border:none;background:var(--slcm-primary, #1a3c6e);color:#fff;font-weight:400;cursor:pointer;' +
			'box-shadow:0 4px 20px rgba(15,27,76,0.2);transition:filter .15s;font-size:var(--font-size-body, 14px);font-family:var(--font-family, inherit);}' +
			'#slcm-wf-switch-program-overlay .slcm-portal-switch-actions #slcm-wf-confirm-switch-btn:hover:not(:disabled){filter:brightness(1.05);}',
		/* Application ID + status row (inside web-form title h1) */
		'.slcm-app-heading-row{display:flex;align-items:center;flex-wrap:wrap;gap:12px 28px;' +
			'line-height:1.25;margin:0;}',
		'#slcm-app-heading-id{flex:0 1 auto;margin:0;min-width:0;' +
			'font-size:clamp(1.2rem,2.4vw,1.65rem);font-weight:400;color:var(--slcm-primary,#1a3c6e);' +
			'letter-spacing:-.02em;line-height:1.2;}',
		'.web-form .control-label,.web-form .frappe-control > label.control-label,' +
			'.frappe-control .control-label{font-weight:300;color:#0f172a;font-size:13px;margin-bottom:6px;}',
		/* Section Break: no heavy rule on every section (parity with “line only on page break”) */
		'.web-form .form-page .section-head,.web-form .form-page .form-section .section-head{' +
			'border-bottom:none!important;box-shadow:none!important;padding-bottom:6px!important;margin-top:10px!important;}',
		/* (Visual separator for next wizard page REMOVED: No border top style on form-page) */
		'#slcm-app-heading-meta{display:inline-flex;align-items:center;flex-wrap:wrap;gap:6px 10px;' +
			'flex:0 1 auto;margin:0;}',
		'#slcm-app-status-label{font-size:13px;font-weight:500;color:#334155;line-height:1.2;' +
			'white-space:nowrap;margin:0;}',
		/* Application status badge */
		'.slcm-status-badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:20px;' +
			'font-size:11px;font-weight:400;letter-spacing:.4px;line-height:1.2;text-transform:uppercase;}',
		'.slcm-status-draft    {background:#fef3c7;color:#92400e;border:1px solid #fcd34d;}',
		'.slcm-status-submitted{background:#dcfce7;color:#14532d;border:1px solid #86efac;}',
		'.slcm-status-submitted-and-paid{background:#fce7f3;color:#9d174d;border:1px solid #fbcfe8;}',
		'.slcm-status-other    {background:#f1f5f9;color:#475569;border:1px solid #cbd5e1;}',
		/* Link / Autocomplete dropdowns — look like a native select list (input width, rounded, shadow) */
		'.web-form .awesomplete > [role="listbox"]{background:#fff;border:1px solid #cbd5e1;border-radius:8px;' +
			'box-shadow:0 8px 24px rgba(15,23,42,.14);padding:4px;margin-top:0;}',
		'.web-form .awesomplete > [role="listbox"] > li{padding:7px 10px;border-radius:6px;font-size:13.5px;' +
			'line-height:1.35;color:#1e293b;cursor:pointer;white-space:normal;}',
		'.web-form .awesomplete > [role="listbox"] > li:hover,' +
			'.web-form .awesomplete > [role="listbox"] > li[aria-selected="true"]{background:#e5e7eb;color:#0f172a;}',
		/* Fee-payment overlay modal */
		'#slcm-fee-modal{position:fixed;inset:0;z-index:99998;display:none;align-items:center;justify-content:center;padding:16px;}',
		'#slcm-fee-modal.open{display:flex;}',
		'#slcm-fee-backdrop{position:absolute;inset:0;background:rgba(15,23,42,.55);backdrop-filter:blur(4px);}',
		'#slcm-fee-box{position:relative;background:#fff;border-radius:14px;width:100%;max-width:500px;' +
			'max-height:calc(100vh - 32px);overflow-y:auto;padding:28px 26px 26px;text-align:center;font-family:inherit;' +
			'box-shadow:0 24px 64px rgba(15,23,42,.28);animation:slcm-slide-up .3s ease-out;}',
		'#slcm-fee-box .slcm-fee-ms{font-family:"Material Symbols Outlined";font-weight:normal;font-style:normal;' +
			'line-height:1;letter-spacing:normal;text-transform:none;display:inline-block;white-space:nowrap;' +
			'-webkit-font-smoothing:antialiased;}',
		'#slcm-fee-close{position:absolute;top:14px;right:14px;width:36px;height:36px;border-radius:9px;border:none;' +
			'background:#f1f5f9;color:#0f172a;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .15s;}',
		'#slcm-fee-close:hover{background:#e2e8f0;}',
		'#slcm-fee-close .slcm-fee-ms{font-size:22px;}',
		/* Rupee hero icon with decorative bubbles */
		'.slcm-fee-hero{position:relative;width:120px;height:84px;margin:4px auto 12px;}',
		'.slcm-fee-hero-circle{position:absolute;left:50%;top:0;transform:translateX(-50%);width:84px;height:84px;border-radius:50%;' +
			'background:#fbe9ec;background:color-mix(in srgb,var(--slcm-primary,#920C24) 10%,#fff);' +
			'color:var(--slcm-primary,#920C24);display:flex;align-items:center;justify-content:center;}',
		'.slcm-fee-hero-circle .slcm-fee-ms{font-size:46px;font-weight:600;}',
		'.slcm-fee-bubble{position:absolute;border-radius:50%;}',
		'.slcm-fee-bubble.b1{width:22px;height:22px;left:0;bottom:4px;background:#fbe9ec;background:color-mix(in srgb,var(--slcm-primary,#920C24) 12%,#fff);}',
		'.slcm-fee-bubble.b2{width:10px;height:10px;left:-4px;bottom:22px;border:2px solid #f5c9d1;border-color:color-mix(in srgb,var(--slcm-primary,#920C24) 22%,#fff);background:#fff;}',
		'.slcm-fee-bubble.b3{width:14px;height:14px;right:-2px;top:22px;border:2.5px solid #f5c9d1;border-color:color-mix(in srgb,var(--slcm-primary,#920C24) 22%,#fff);background:#fff;}',
		'.slcm-fee-title{margin:0 0 16px;font-size:22px;font-weight:700;color:#1e293b;line-height:1.25;}',
		/* Amount panel */
		'.slcm-fee-amount-box{display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap;' +
			'padding:16px 14px;margin:0 12px 12px;border-radius:10px;' +
			'background:#fdf2f4;background:color-mix(in srgb,var(--slcm-primary,#920C24) 6%,#fff);}',
		'#slcm-fee-amount{font-size:30px;font-weight:700;color:var(--slcm-primary,#920C24);line-height:1.1;margin:0;}',
		'.slcm-fee-secured{display:inline-flex;align-items:center;gap:5px;padding:5px 10px;border-radius:6px;' +
			'background:#dcfce7;color:#166534;font-size:13px;font-weight:500;}',
		'.slcm-fee-secured .slcm-fee-ms{font-size:17px;color:#15803d;font-variation-settings:"FILL" 1;}',
		/* Info + note callouts */
		'.slcm-fee-callout{display:flex;align-items:stretch;text-align:left;border-radius:10px;margin:0 0 12px;overflow:hidden;' +
			'font-size:13.5px;line-height:1.55;}',
		'.slcm-fee-callout-icon{flex:0 0 auto;display:flex;align-items:center;justify-content:center;padding:0 14px;}',
		'.slcm-fee-callout-text{flex:1;padding:12px 14px 12px 4px;}',
		'.slcm-fee-info{background:#fdf2f4;background:color-mix(in srgb,var(--slcm-primary,#920C24) 5%,#fff);color:#64748b;}',
		'.slcm-fee-info .slcm-fee-callout-icon{background:#fbe9ec;background:color-mix(in srgb,var(--slcm-primary,#920C24) 8%,#fff);' +
			'color:var(--slcm-primary,#920C24);padding:0 16px;}',
		'.slcm-fee-info .slcm-fee-callout-text{padding-left:14px;}',
		'.slcm-fee-info .slcm-fee-ms{font-size:24px;}',
		'.slcm-fee-note{background:#fff8eb;color:#5b3a12;}',
		'.slcm-fee-note .slcm-fee-callout-icon{color:#ea8a0c;align-items:flex-start;padding-top:12px;}',
		'.slcm-fee-note .slcm-fee-ms{font-size:24px;}',
		'.slcm-fee-note strong{color:#3f2a0e;font-weight:700;}',
		/* Actions */
		'.slcm-fee-actions{display:flex;flex-direction:column;gap:12px;margin-top:16px;}',
		'#slcm-fee-pay-btn{position:relative;width:100%;padding:13px 44px;border-radius:8px;border:none;cursor:pointer;' +
			'background:var(--slcm-primary,#920C24);color:#fff;font-family:inherit;font-size:16px;font-weight:600;' +
			'display:flex;align-items:center;justify-content:center;gap:10px;transition:filter .15s;}',
		'#slcm-fee-pay-btn .slcm-fee-ms{font-size:22px;}',
		'#slcm-fee-pay-btn .slcm-fee-pay-arrow{position:absolute;right:16px;top:50%;transform:translateY(-50%);}',
		'#slcm-fee-pay-btn:hover:not(:disabled){filter:brightness(1.08);}',
		'#slcm-fee-pay-btn:disabled{opacity:.6;cursor:not-allowed;}',
		'#slcm-fee-later-btn{width:100%;padding:12px 16px;border-radius:8px;cursor:pointer;' +
			'background:#fff;color:#1e293b;border:1.5px solid #cbd5e1;font-family:inherit;font-size:16px;font-weight:600;' +
			'display:flex;align-items:center;justify-content:center;gap:10px;transition:background .15s,border-color .15s;}',
		'#slcm-fee-later-btn:hover{background:#f8fafc;border-color:#94a3b8;}',
		'#slcm-fee-later-btn .slcm-fee-ms{font-size:22px;}',
		// NOTE: keep the space after the opening brace below. This file is rendered through Jinja,
		// and an opening brace directly followed by a hash starts a Jinja comment.
		'@media (max-width:480px){ #slcm-fee-box{padding:24px 18px 20px;}.slcm-fee-amount-box{margin:0 0 12px;}' +
			'#slcm-fee-amount{font-size:26px;}.slcm-fee-title{font-size:20px;}}',
		/* Top-bar: Back (left) + Receipt icon-btn (right) */
		'#slcm-form-topbar{display:flex;align-items:center;justify-content:space-between;' +
			'padding:8px 4px 4px;margin-bottom:4px;}',
		'#slcm-form-topbar-left{display:flex;align-items:center;flex-wrap:wrap;gap:10px 18px;flex:1;min-width:0;}',
		'#slcm-back-btn{display:inline-flex;align-items:center;gap:6px;padding:6px 14px 6px 10px;' +
			'border-radius:8px;font-size:13px;font-weight:300;border:1.5px solid #cbd5e1;' +
			'background:#f8fafc;color:#334155;cursor:pointer;text-decoration:none;' +
			'transition:background .15s,border-color .15s;}',
		'#slcm-back-btn:hover{background:#f1f5f9;border-color:#94a3b8;color:#1e293b;}',
		'#slcm-applying-for-wrap{font-size:14px;line-height:1.45;color:#475569;min-width:0;}',
		'#slcm-applying-for-wrap .slcm-applying-for-lbl{font-weight:300;color:#64748b;margin-right:6px;}',
		'#slcm-applying-for-prog{color:#0f172a;font-weight:400;}',
		'#slcm-fee-receipt-wrap{display:flex;align-items:center;}',
		'#slcm-fee-receipt-btn{display:inline-flex;align-items:center;gap:6px;padding:6px 14px 6px 10px;' +
			'border-radius:8px;font-size:13px;font-weight:300;border:1.5px solid var(--slcm-primary,#1a73e8);' +
			'background:#fff;color:var(--slcm-primary,#1a73e8);cursor:pointer;transition:background .15s;}',
		'#slcm-fee-receipt-btn:hover{background:color-mix(in srgb,var(--slcm-primary,#1a73e8) 8%,#fff);}',
		/* Student Photo — square preview only; default Frappe attach styling (no dashed wrapper override) */
		'.slcm-candidate-photo-preview{margin:0 0 14px;display:flex;align-items:flex-start;}',
		'.slcm-candidate-photo-preview img{display:block;width:140px;height:140px;object-fit:cover;' +
			'border-radius:0;border:2px solid #e2e8f0;box-shadow:0 1px 4px rgba(0,0,0,.06);background:#f8fafc;}',
		'.frappe-control[data-fieldname="candidate_photo"] > .form-group{' +
			'display:flex!important;flex-direction:column!important;align-items:stretch!important;}',
		'.frappe-control[data-fieldname="candidate_photo"] > .form-group > .clearfix{margin-bottom:8px;}',
		/* Submit progress overlay */
		'#slcm-submit-overlay{position:fixed;inset:0;z-index:99997;background:rgba(255,255,255,.8);' +
			'display:none;align-items:center;justify-content:center;flex-direction:column;gap:14px;' +
			'font-size:1rem;color:#334155;font-weight:500;}',
		'#slcm-submit-overlay.open{display:flex;}',
		'#slcm-submit-spinner{width:36px;height:36px;border:4px solid #e2e8f0;' +
			'border-top-color:var(--slcm-primary,#1a73e8);border-radius:50%;animation:slcm-spin .8s linear infinite;}',
		/* Eligibility Evaluation Results (portal submit) */
		'#slcm-ee-modal{position:fixed;inset:0;z-index:99999;display:none;align-items:center;justify-content:center;padding:16px;}',
		'#slcm-ee-modal.open{display:flex;}',
		'#slcm-ee-backdrop{position:absolute;inset:0;background:rgba(15,23,42,.55);backdrop-filter:blur(2px);}',
		'#slcm-ee-panel{position:relative;background:#fff;border-radius:16px;width:100%;max-width:640px;max-height:90vh;' +
			'overflow:hidden;display:flex;flex-direction:column;box-shadow:0 25px 50px -12px rgba(0,0,0,.25);}',
		'#slcm-ee-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:20px 22px 16px;' +
			'border-bottom:1px solid #e2e8f0;flex-shrink:0;}',
		'#slcm-ee-title{margin:0;font-size:1.15rem;font-weight:400;color:#0f172a;line-height:1.35;}',
		'#slcm-ee-close{border:none;background:#f1f5f9;color:#64748b;width:36px;height:36px;border-radius:10px;' +
			'cursor:pointer;font-size:1.25rem;line-height:1;flex-shrink:0;}',
		'#slcm-ee-close:hover{background:#e2e8f0;color:#334155;}',
		'#slcm-ee-body{padding:18px 22px 22px;overflow-y:auto;flex:1;}',
		'.slcm-ee-alert{display:flex;gap:12px;padding:14px 16px;background:#fff1f2;border:1px solid #fecdd3;' +
			'border-left:4px solid #e11d48;border-radius:10px;margin-bottom:18px;}',
		'.slcm-ee-alert-dot{width:10px;height:10px;background:#e11d48;border-radius:50%;flex-shrink:0;margin-top:4px;}',
		'.slcm-ee-alert-text{font-size:14px;line-height:1.55;color:#334155;}',
		'.slcm-ee-sec{margin-bottom:16px;}',
		'.slcm-ee-sec:last-child{margin-bottom:0;}',
		'.slcm-ee-sec-title{margin:0 0 8px;font-size:13px;font-weight:400;color:#0f172a;letter-spacing:.02em;}',
		'.slcm-ee-sec-body{font-size:14px;line-height:1.55;color:#334155;}',
		'.slcm-ee-sec-body .slcm-ee-sec-p{margin:0 0 10px;}',
		'.slcm-ee-sec-body .slcm-ee-sec-p:last-child{margin-bottom:0;}',
		'.slcm-ee-subhead{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;margin-bottom:8px;}',
		'.slcm-ee-subhead strong{font-size:15px;color:#0f172a;}',
		'.slcm-ee-meta{font-size:12px;color:#64748b;}',
		'.slcm-ee-summary{display:flex;align-items:center;gap:8px;margin-bottom:12px;font-size:13px;color:#475569;}',
		'.slcm-ee-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;}',
		'#slcm-ee-table{width:100%;border-collapse:separate;border-spacing:0;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;font-size:13px;}',
		'#slcm-ee-table th{text-align:left;padding:11px 14px;background:#f8fafc;font-weight:300;color:#475569;border-bottom:2px solid #e2e8f0;}',
		'#slcm-ee-table th.slcm-ee-th-actions{text-align:center;width:140px;}',
		'#slcm-ee-table td{padding:11px 14px;border-bottom:1px solid #f1f5f9;vertical-align:middle;color:#1e293b;}',
		'#slcm-ee-table tr:last-child td{border-bottom:none;}',
		'.slcm-ee-status{display:inline-flex;align-items:center;gap:6px;font-weight:500;color:#15803d;}',
		'.slcm-ee-badge{font-size:10px;padding:2px 8px;border-radius:999px;background:var(--slcm-primary,#3b82f6);color:#fff;font-weight:400;}',
		'.slcm-ee-switch{padding:7px 14px;border-radius:8px;border:none;background:var(--slcm-primary,#1d4ed8);color:#fff;font-size:12px;font-weight:300;cursor:pointer;}',
		'.slcm-ee-switch:hover{filter:brightness(1.1);}',
		'.slcm-ee-switch:disabled{opacity:.55;cursor:not-allowed;}',
		'#slcm-ee-foot{padding:14px 22px 18px;border-top:1px solid #e2e8f0;flex-shrink:0;}',
		'#slcm-ee-dismiss{width:100%;padding:11px;border-radius:10px;border:1px solid #cbd5e1;background:#fff;' +
			'color:#334155;font-weight:300;cursor:pointer;font-size:14px;}',
		'#slcm-ee-dismiss:hover{background:#f8fafc;}',
		/* ── Hide Frappe default nav/footer ──────────────────────── */
		'header.navbar,nav.navbar,.web-header,.web-navbar,#navbar-main,' +
		'header[class*="navbar"],.website-header,.website-footer,footer.footer,#footer-main{display:none!important;}',
		'.page-content{margin-top:0!important;padding-top:0!important;}',
		'.main-section{padding-top:0!important;}',
		/* PACE Admission “Open” badge (admission_base.html parity) */
		'@keyframes slcm-partylight-bg{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}',
		'@keyframes slcm-partylight-pulse-text{0%{transform:scale(1);filter:brightness(1)}100%{transform:scale(1.08);filter:brightness(1.2)}}',
		'.slcm-badge-partylight-text{display:inline-block;font-weight:900;text-transform:uppercase;' +
			'background:linear-gradient(-45deg,#ff0055,#ffcc00,#00ff66,#0099ff,#cc00ff,#ff0055);background-size:400% 400%;' +
			'-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;' +
			'animation:slcm-partylight-bg 2s linear infinite,slcm-partylight-pulse-text .8s ease-in-out infinite alternate;' +
			'vertical-align:middle;line-height:1;}',
		/* ── Admission nav bar ────────────────────────────────────── */
		/* Below Frappe msgprint (2000) / Bootstrap modal so dialogs are not covered */
		'.adm-nav{background:var(--slcm-primary,#1a3c6e);padding:10px 24px;display:flex;align-items:center;' +
			'justify-content:space-between;height:60px;position:sticky;top:0;z-index:1020;' +
			'box-shadow:0 2px 8px rgba(0,0,0,.15);}',
		'.adm-nav-brand{display:flex;align-items:center;gap:12px;text-decoration:none;color:#fff;' +
			'font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:65%;margin-top: 1rem!important}',
		'.adm-nav-brand img{height:clamp(28px,6vw,36px);width:auto;flex-shrink:0;}',
		'.adm-nav-links{display:flex;gap:clamp(10px,2vw,20px);align-items:center;}',
		'.adm-nav-links a{color:rgba(255,255,255,.85);text-decoration:none;font-size:14px;font-weight:500;}',
		'.adm-nav-links a:hover{color:#fff;}',
		'#adm-avatar-btn{user-select:none;-webkit-user-select:none;transition:all .2s;overflow:hidden;padding:0;}',
		'#adm-avatar-btn:hover{border-color:rgba(255,255,255,.7)!important;box-shadow:0 0 0 3px rgba(255,255,255,.2)!important;}',
		'#adm-avatar-menu a:hover{background:#f8fafc!important;}',
		/* ── Admission footer ─────────────────────────────────────── */
		'.adm-wf-footer{background:#0f172a;color:#94a3b8;padding:40px 24px 20px;margin-top:48px;' +
			'font-family:inherit;}',
		'.adm-wf-footer-inner{max-width:1400px;margin:0 auto;display:flex;flex-wrap:wrap;gap:32px;' +
			'justify-content:space-between;}',
		'.adm-wf-footer-brand{width:auto;}',
		'.adm-wf-footer-brand h2{font-size:18px;font-weight:400;color:#fff;margin:0 0 10px;}',
		'.adm-wf-footer-brand p{font-size:13px;line-height:1.6;margin:0;}',
		'.adm-wf-footer-links{flex:1 1 200px;}',
		'.adm-wf-footer-links h4{color:#fff;font-size:11px;font-weight:400;letter-spacing:.1em;margin:0 0 12px;}',
		'.adm-wf-footer-links ul{list-style:none;padding:0;margin:0;}',
		'.adm-wf-footer-links li{margin-bottom:7px;}',
		'.adm-wf-footer-links a{color:#94a3b8;text-decoration:none;font-size:13px;transition:color .2s;}',
		'.adm-wf-footer-links a:hover{color:#fff;}',
				'.adm-wf-footer-bottom{border-top:1px solid rgba(255,255,255,.1);margin-top:28px;padding-top:16px;' +
			'display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;font-size:12px;}',
		/* ── Stepper — CSS Grid: max-content columns for pills, 1fr tracks for lines (fills any screen width) ── */
		'#slcm-stepper-wrap{padding:15px 16px 28px;overflow-x:auto;scrollbar-width:none;-ms-overflow-style:none;width:100%;' +
			'box-sizing:border-box;}',
		'#slcm-stepper-wrap::-webkit-scrollbar{display:none;}',
		'.slcm-stepper{box-sizing:border-box;width:100%;max-width:100%;min-width:0;padding:0 6px;}',
		'.slcm-step{display:flex;flex-direction:row;align-items:center;gap:14px;cursor:pointer;position:relative;' +
			'min-width:104px;width:max-content;flex-shrink:0;transition:background .25s,border-color .25s;padding:10px 18px 10px 14px;' +
			'border-radius:14px;border:1px solid transparent;background:#f3f4f6;}',
		'.slcm-step-connector{align-self:center;width:100%;min-width:12px;height:2px;background:#e5e7eb;' +
			'border-radius:1px;pointer-events:none;}',
		/* Completed step: green */
		'.slcm-step.completed:not(.active){background:#ecfdf5;border-color:#bbf7d0;}',
		'.slcm-step.completed .slcm-step-circle{border-color:#22c55e;background:#22c55e;color:#fff;}',
		'.slcm-step.completed .slcm-step-label{color:#15803d;}',
		'.slcm-step.completed:not(.active) .slcm-step-label{color:#166534;}',
		'.slcm-step.completed + .slcm-step-connector{background:#86efac;}',
		/* Active step: blue */
		'.slcm-step.active{background:#e0ecfa;border-color:#2471f3;}',
		'.slcm-step.active .slcm-step-circle{border-color:#2471f3;background:#2471f3;color:#fff;' +
			'box-shadow:0 0 0 4px rgba(36,113,243,0.13);}',
		'.slcm-step.active .slcm-step-label{color:#1e3a8a;}',
		/* Default step: light gray */
		'.slcm-step:not(.active):not(.completed){background:#f3f4f6;border-color:#e5e7eb;}',
		'.slcm-step:not(.active):not(.completed) .slcm-step-circle{border-color:#e5e7eb;background:#fff;color:#9ca3af;}',
		'.slcm-step:not(.active):not(.completed) .slcm-step-label{color:#9ca3af;}',
		/* Common styles */
		'.slcm-step-circle{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;' +
			'font-size:14px;font-weight:400;border:2px solid #e9d5d8;background:#fff;z-index:2;transition:all 0.25s ease;}',
		'.slcm-step-label{font-size:13px;font-weight:400;text-align:left;line-height:1.25;' +
			'white-space:nowrap;max-width:none;transition:color .25s;flex:1;}',
		/* Hover effects (just border brighten on active and completed) */
		'.slcm-step.active:hover .slcm-step-circle{border-color:#1e40af;}',
		'.slcm-step.completed:hover .slcm-step-circle{border-color:#16a34a;}',
		/* Footer container parity */
		'.full-bleed-footer{width:100%;max-width:none;margin-left:0;margin-right:0;position:relative;' +
			'background:var(--footer-color);color:var(--footer-text);padding:48px 0 24px;box-sizing:border-box;}',
		'.footer-container{width:100%;max-width:1400px;margin:0 auto;padding:0 24px;}',
		'@media(min-width:1600px){.footer-container{max-width:1540px;}}',
		'@media(min-width:1920px){.footer-container{max-width:1840px;}}',
		'.slcm-step:hover .slcm-step-circle{border-color:#1e40af;}',
		/* Air between title / back row and stepper card */
		'.web-form-container:has(#slcm-stepper-wrap) .web-form-header{' +
			'padding-bottom:16px;margin-bottom:4px;border-bottom:1px solid #f1f5f9;}',
		'.web-form-container:has(#slcm-stepper-wrap) #slcm-stepper-wrap{' +
			'background:#fff;border:1px solid #e2e8f0;border-bottom:none;border-radius:12px 12px 0 0;' +
			'margin:16px 0 0;padding:20px 16px 28px;position:relative;z-index:1;}',
		/* rounded corners come from border-radius on this form */
		'.web-form-container:has(#slcm-stepper-wrap) form.web-form{' +
			'border:1px solid #e2e8f0!important;border-top:1px solid #eef2f6!important;' +
			'border-radius:0 0 12px 12px!important;background:#fff!important;margin-top:0!important;' +
			'overflow-y:visible;}',
		'.web-form-container:has(#slcm-stepper-wrap) form.web-form .web-form-body{border-top:none!important;}',
		/* Field error highlight */
		'.slcm-field-error{border-color:#ef4444!important;box-shadow:0 0 0 3px rgba(239,68,68,0.15)!important;}',
		/* Small Text / Long Text / Text — taller textarea (Address etc.) */
		'.web-form textarea.form-control,.web-form .frappe-control textarea.form-control{' +
			'min-height:104px;line-height:1.5;padding:10px 12px;resize:vertical;}',
		'.web-form .frappe-control[data-fieldtype="Small Text"] textarea.form-control,' +
			'.web-form .frappe-control[data-fieldtype="Text"] textarea.form-control,' +
			'.web-form .frappe-control[data-fieldtype="Long Text"] textarea.form-control{' +
			'min-height:120px;}',
		/* Required checkbox error (ControlCheck drops .form-control on the input) */
		'.web-form input[type=checkbox].slcm-field-error,.web-form .checkbox.slcm-field-error{' +
			'outline:2px solid #ef4444!important;outline-offset:3px;border-radius:4px;}',

		/* ── Responsive Web Form Footer & Buttons ── */
		'.web-form-footer .btn,.web-form-footer button,#slcm-save-draft-btn{' +
			'min-height:42px!important;padding:8px 24px!important;border-radius:8px!important;font-weight:400!important;white-space:nowrap!important;}',
		'@media(max-width:767px){' +
			'.web-form-footer,.web-form-footer .left-area,.web-form-footer .right-area{display:block!important;width:100%!important;padding:16px!important;}' +
			'.web-form-footer .btn,.web-form-footer button,#slcm-save-draft-btn{' +
				'display:block!important;width:100%!important;margin:0 0 12px 0!important;text-align:center!important;}' +
		'}',
		/* Hide default orange "Not Saved" indicator / badge always */
		'.indicator-pill.orange, .indicator.orange, .not-saved-badge, span[data-state="dirty"], .badge-dirty, span:contains("Not Saved") { display: none !important; }',
		'.indicator-pill.orange, .indicator.orange, .not-saved-badge{display:none!important;}',

	].join('');
	document.head.appendChild(s);
}

// ───────────────────────────────────────────────────────────────────
//  ADMISSION NAV + FOOTER SHELL
//  Mirrors admission_base.html's <nav class="adm-nav"> and <footer>
// ───────────────────────────────────────────────────────────────────
function _injectAdmissionShell() {
	if (document.getElementById('slcm-adm-nav')) return;

	// Single call — server handles all permission-elevated data fetching
	frappe.call({
		method: 'slcm.admission.web_form.applicant_form.applicant_form.get_portal_shell_data',
		callback: function (r) {
			var d = (r && r.message) || {};
			_buildShell(
				{ title: d.site_title },
				{
					portal_title:    d.portal_title,
					primary_color:   d.primary_color,
					secondary_color: d.secondary_color,
					navbar_color:    d.navbar_color,
					footer_color:    d.footer_color,
					footer_text_color: d.footer_text_color,
					button_border_radius: d.button_border_radius,
					font_family:     d.font_family,
					font_size_preset: d.font_size_preset,
					font_size_heading: d.font_size_heading,
					font_size_subheading: d.font_size_subheading,
					font_size_body:  d.font_size_body,
					font_size_form_title: d.font_size_form_title,
					font_size_toast: d.font_size_toast,
					footer_address:  d.footer_address,
					footer_phone:    d.footer_phone,
					contact_email:   d.contact_email,
					programmes:      d.programmes || [],
					pace_enabled:    d.pace_enabled || 0,
					powerd_by:       d.powerd_by || 'boscosoft',
					institution_logo: d.institution_logo || '',
					social_links:    d.social_links || [],
					admission_footer: d.admission_footer || [],
					footer_text:     d.footer_text || '',
					portal_active:   d.portal_active || 0,
				},
				d.user || 'Guest',
				{ full_name: d.full_name, user_image: d.user_image }
			);
		},
		error: function () {
			// Fallback: build shell with defaults if the call fails
			_buildShell({ title: 'SLCM' },
				{
					portal_title: 'Admissions',
					primary_color: '#1a3c6e',
					secondary_color: '#c8a14b',
					font_family: 'System Default',
					programmes: [],
					pace_enabled: 0,
					powerd_by: 'boscosoft',
					admission_footer: [],
					footer_text: '',
					portal_active: 0,
				},
				'Guest', {});
		},
	});
}

function _buildShell(ws, cfg, user, uinfo) {
	if (document.getElementById('slcm-adm-nav')) return;

	var primary       = cfg.primary_color   || '#920c24';
	var secondary     = cfg.secondary_color || '#000000';
	var navbarCol     = cfg.navbar_color    || '';
	var footerCol     = cfg.footer_color    || '';
	var footerTextCol = cfg.footer_text_color || '';
	var btnRadius     = cfg.button_border_radius || '';
	var fHeading      = cfg.font_size_heading || '';
	var fSubheading   = cfg.font_size_subheading || '';
	var fBody         = cfg.font_size_body || '';
	var fFormTitle    = cfg.font_size_form_title || '';
	var fToast        = cfg.font_size_toast || '';
	var fPreset       = cfg.font_size_preset || 'Normal';
	var fontFam       = cfg.font_family     || 'System Default';
	var title         = cfg.portal_title    || ws.title || 'Admissions';
	var logo       = cfg.institution_logo || '';
	var isGuest    = (!user || user === 'Guest');
	var fullName   = uinfo.full_name     || user || '';
	var userImg    = uinfo.user_image    || '';
	var initLetter = fullName ? fullName[0].toUpperCase() : 'U';
	var programmes = cfg.programmes      || [];
	var paceOn     = cfg.pace_enabled    ? 1 : 0;
	var powerd     = cfg.powerd_by       || 'boscosoft';
	var portalActive = cfg.portal_active ? 1 : 0;

	// Apply CSS variables immediately so ALL var(--slcm-primary) references update at once
	var fontCss = "";
	if (fontFam && fontFam !== 'System Default') {
		var fontLink = document.createElement('link');
		fontLink.rel = 'stylesheet';
		fontLink.href = 'https://fonts.googleapis.com/css2?family=' + fontFam.replace(/\s+/g, '+') + ':wght@400;500;600;700;800&display=swap';
		document.head.appendChild(fontLink);
	}

	if (!document.getElementById('fa-icons-css-adm')) {
		var faLink = document.createElement('link');
		faLink.id = 'fa-icons-css-adm';
		faLink.rel = 'stylesheet';
		faLink.href = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.6.0/css/all.min.css';
		document.head.appendChild(faLink);
	}

	if (secondary) { fontCss += 'body, html { background-color: ' + secondary + ' !important; }\n'; }
	if (navbarCol) { fontCss += '.adm-nav { background-color: ' + navbarCol + ' !important; }\n'; }
	if (footerCol) { fontCss += '.adm-wf-footer { background-color: ' + footerCol + ' !important; }\n'; }
	if (footerTextCol) { fontCss += '.adm-wf-footer, .adm-wf-footer a, .adm-wf-footer .text-muted { color: ' + footerTextCol + ' !important; }\n'; }
	if (btnRadius) { fontCss += '.btn, .submit-btn, .btn-next, .btn-submit-web-form { border-radius: ' + btnRadius + ' !important; }\n'; }

	var rootVars = [
		':root {',
		'  --slcm-primary: ' + primary + ';',
		'  --slcm-secondary: ' + secondary + ';',
		'  --font-family: \'' + fontFam + '\', serif;',
		'  --font-size-heading: ' + (fHeading || '19pt') + ';',
		'  --font-size-subheading: ' + (fSubheading || '16pt') + ';',
		'  --font-size-body: ' + (fBody || '10.5pt') + ';',
		'  --font-size-form-title: ' + (fFormTitle || '15pt') + ';',
		'  --font-size-toast: ' + (fToast || '12pt') + ';',
		'}'
	].join('\n');

	var consumerCss = [
		'/* ── Icon font protection ── */',
		'.material-symbols-outlined,',
		'.material-symbols-rounded,',
		'.fa, .fas, .far, .fab,',
		'[class^="icon-"], [class*=" icon-"] {',
		'  font-family: inherit !important;',
		'}',
		'/* ── Font family — everything except icons ── */',
		'.web-form,',
		'.web-form-container,',
		'.web-form-container p,',
		'.web-form-container span,',
		'.web-form-container a,',
		'.web-form-container li,',
		'.web-form-container input,',
		'.web-form-container textarea,',
		'.web-form-container select,',
		'.web-form-container button,',
		'.web-form-container label,',
		'.web-form-container .form-control,',
		'.web-form-container .section-head,',
		'.web-form-container .control-label,',
		'.web-form-container .help-box,',
		'.web-form-container .control-value,',
		'.web-form-container .step-pill span,',
		'.web-form-container .tab-label,',
		'.web-form-container .adm-step-label,',
		'.web-form-container h1,',
		'.web-form-container h2,',
		'.web-form-container h3,',
		'.web-form-container h4,',
		'.web-form-container h5,',
		'.application-id,',
		'.adm-app-id,',
		'.status-badge,',
		'.alert,',
		'.badge,',
		'.indicator {',
		'  font-family: var(--font-family, \'Merriweather\', serif) !important;',
		'}',
		'/* ── Heading size ── */',
		'.web-form-container h1,',
		'.application-id,',
		'.adm-app-id,',
		'.adm-nav-brand {',
		'  font-size: var(--font-size-heading) !important;',
		'}',
		'/* ── Form title size — step pills and section heads ── */',
		'.web-form-container .section-head,',
		'.web-form-container .step-pill span,',
		'.web-form-container .tab-label,',
		'.web-form-container .adm-step-label {',
		'  font-size: var(--font-size-form-title) !important;',
		'}',
		'/* ── Body size bold — labels and help text ── */',
		'.web-form-container .control-label,',
		'.web-form-container .help-box,',
		'.web-form-container label {',
		'  font-size: var(--font-size-body) !important;',
		'}',
		'/* ── Body size normal — values, inputs, paragraph ── */',
		'.web-form-container .control-value,',
		'.web-form-container p,',
		'.web-form-container input,',
		'.web-form-container textarea,',
		'.web-form-container select,',
		'.web-form-container .form-control {',
		'  font-size: var(--font-size-body) !important;',
		'}',
		'/* ── Button size ── */',
		'.web-form-container .btn,',
		'.btn-next,',
		'.submit-btn,',
		'.btn-submit-web-form {',
		'  font-size: var(--font-size-body) !important;',
		'}',
		'/* ── Toast and badge size ── */',
		'.status-badge,',
		'.alert,',
		'.badge,',
		'.indicator {',
		'  font-size: var(--font-size-toast) !important;',
		'}',
		'/* ── Font weight 400 — titles, labels, help text, buttons ── */',
		'.web-form-container h1,',
		'.web-form-container h2,',
		'.web-form-container h3,',
		'.web-form-container h4,',
		'.web-form-container h5,',
		'.web-form-container .section-head,',
		'.web-form-container .step-pill span,',
		'.web-form-container .tab-label,',
		'.web-form-container .adm-step-label,',
		'.web-form-container .control-label,',
		'.web-form-container .help-box,',
		'.web-form-container label,',
		'.application-id,',
		'.adm-app-id,',
		'.btn-next,',
		'.submit-btn,',
		'.btn-submit-web-form {',
		'  font-weight: 400 !important;',
		'}',
		'/* ── Font weight 300 — body text, inputs, values ── */',
		'.web-form-container .control-value,',
		'.web-form-container p,',
		'.web-form-container input,',
		'.web-form-container textarea,',
		'.web-form-container select,',
		'.web-form-container .form-control,',
		'.status-badge,',
		'.alert,',
		'.badge,',
		'.indicator {',
		'  font-weight: 300 !important;',
		'}',
		'/* ── Footer isolation — fixed size and weight, immune to global rules ── */',
		'/* ── Footer font family — dynamic family, fixed size and weight ── */',
		'.adm-wf-footer,',
		'.adm-wf-footer p,',
		'.adm-wf-footer a,',
		'.adm-wf-footer span,',
		'.adm-wf-footer li,',
		'.adm-wf-footer small,',
		'.adm-wf-footer label,',
		'.adm-wf-footer h1,',
		'.adm-wf-footer h2,',
		'.adm-wf-footer h3,',
		'.adm-wf-footer h4,',
		'.adm-wf-footer h5,',
		'.adm-wf-footer .text-muted,',
		'.adm-wf-footer .footer-heading,',
		'.adm-wf-footer .footer-col-title,',
		'.adm-wf-footer .footer-bottom,',
		'.adm-wf-footer .footer-bottom p,',
		'.adm-wf-footer .footer-bottom span,',
		'.adm-wf-footer .footer-bottom a,',
		'.adm-wf-footer .footer-bottom strong,',
		'.adm-wf-footer .footer-bottom b {',
		'  font-family: var(--font-family, \'Merriweather\', serif) !important;',
		'}',
		'/* ── Navbar font family — dynamic family, fixed size and weight ── */',
		'.adm-nav,',
		'.adm-nav a,',
		'.adm-nav span,',
		'.adm-nav li,',
		'.adm-nav button,',
		'.adm-nav .nav-link,',
		'.adm-nav .navbar-brand,',
		'.adm-nav .adm-nav-links,',
		'.adm-nav .adm-nav-links a,',
		'.adm-nav .adm-user-name,',
		'.adm-nav .adm-user-role {',
		'  font-family: var(--font-family, \'Merriweather\', serif) !important;',
		'}',
		'/* ── Navbar Brand Size ── */',
		'',
		'/* Footer column headings: ABOUT, ADMISSION, CONTACT US */',
		'.adm-wf-footer h1,',
		'.adm-wf-footer h2,',
		'.adm-wf-footer h3,',
		'.adm-wf-footer h4,',
		'.adm-wf-footer h5,',
		'.adm-wf-footer .footer-heading,',
		'.adm-wf-footer .footer-col-title {',
		'  font-size: 14px !important;',
		'  font-weight: 400 !important;',
		'}',
		'',
		'/* Footer body text: links, paragraphs, copyright, phone, email */',
		'.adm-wf-footer,',
		'.adm-wf-footer p,',
		'.adm-wf-footer a,',
		'.adm-wf-footer span,',
		'.adm-wf-footer li,',
		'.adm-wf-footer small,',
		'.adm-wf-footer label,',
		'.adm-wf-footer .text-muted {',
		'  font-size: 13px !important;',
		'  font-weight: 300 !important;',
		'}',
		'',
		'/* Footer bottom bar: copyright and powered-by line */',
		'.adm-wf-footer .footer-bottom,',
		'.adm-wf-footer .footer-bottom p,',
		'.adm-wf-footer .footer-bottom span,',
		'.adm-wf-footer .footer-bottom a {',
		'  font-size: 13px !important;',
		'  font-weight: 300 !important;',
		'}',
		'',
		'/* "boscosoft" bold in powered-by — keep it slightly heavier */',
		'.adm-wf-footer .footer-bottom strong,',
		'.adm-wf-footer .footer-bottom b {',
		'  font-size: 13px !important;',
		'  font-weight: 400 !important;',
		'}'
	].join('\n');

	var varStyle = document.createElement('style');
	varStyle.id = 'slcm-theme-vars';
	varStyle.textContent = fontCss + '\n' + rootVars + '\n' + consumerCss + '\n' +
		// Frappe built-in web form elements — Next/Submit/Section heading
		'.btn-next,.submit-btn,.btn-submit-web-form{background:' + primary + '!important;border-color:' + primary + '!important;color:#fff!important;}' +
		'.btn-next:hover,.submit-btn:hover{filter:brightness(1.08)!important;}' +
		'.section-head{color:' + primary + '!important;}' +
		// Section heading colour in web form
		'.web-form-container .section-head,.web-form .section-head{color:' + primary + '!important;}';

	document.head.appendChild(varStyle);

	// ── NAV ────────────────────────────────────────────────────────
	var nav = document.createElement('nav');
	nav.id        = 'slcm-adm-nav';
	nav.className = 'adm-nav';
	nav.innerHTML =
		'<h1 class="adm-nav-brand">' +
			(logo ? '<img src="' + logo + '" alt="Logo">' : '') +
			_esc(title) +
		'</h1>' +
		'<div class="adm-nav-links">' +
			(portalActive ? '<a href="' + _nlsatPortalBase() + '" style="color:rgba(255,255,255,.85);text-decoration:none;font-size:14px;font-weight:500;white-space:nowrap;" onmouseover="this.style.color=\'#fff\'" onmouseout="this.style.color=\'rgba(255,255,255,.85)\'">Admission</a>' : '') +
			// Same route as the admission portal navbar (admission_base.html)
			'<a href="/nlsat/helpdesk" style="color:rgba(255,255,255,.85);text-decoration:none;font-size:14px;font-weight:500;white-space:nowrap;" onmouseover="this.style.color=\'#fff\'" onmouseout="this.style.color=\'rgba(255,255,255,.85)\'">Helpdesk</a>' +
			(isGuest
				? '<a href="/login" style="display:inline-flex;align-items:center;background:' + primary + ';color:#fff;padding:8px 20px;border-radius:8px;font-weight:400;font-size:14px;text-decoration:none;">Login / Apply</a>'
				: '<div style="position:relative;display:flex;align-items:center;gap:10px;">' +
					'<button id="adm-avatar-btn" onclick="_slcmAvatarToggle(event)"' +
						' style="width:38px;height:38px;border-radius:4px;background:rgba(255,255,255,.15);color:#fff;' +
						'border:2px solid rgba(255,255,255,.3);font-weight:400;font-size:15px;cursor:pointer;' +
						'display:flex;align-items:center;justify-content:center;overflow:hidden;">' +
						(userImg ? '<img src="' + _esc(userImg) + '" style="width:100%;height:100%;object-fit:cover;border-radius:4px;">' : _esc(initLetter)) +
					'</button>' +
					'<span style="color:#fff;font-size:13px;font-weight:300;opacity:.95;cursor:pointer;" class="nav-hide-mobile" onclick="_slcmAvatarToggle(event)">' + _esc(fullName) + '</span>' +
					'<div id="adm-avatar-menu" style="display:none;position:absolute;right:0;top:calc(100% + 8px);' +
						'min-width:180px;background:#fff;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.14);' +
						'border:1px solid rgba(0,0,0,.07);overflow:hidden;z-index:9999;">' +
						'<div style="padding:12px 16px;border-bottom:1px solid #f1f5f9;">' +
							'<div style="font-size:11px;color:#94a3b8;font-weight:300;letter-spacing:.05em;">Signed in as</div>' +
							'<div style="font-size:13px;color:#1e293b;font-weight:400;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:160px;">' + _esc(user) + '</div>' +
						'</div>' +
						'<a href="/nlsat/my-profile" style="display:flex;align-items:center;gap:10px;padding:12px 16px;text-decoration:none;color:#334155;font-size:14px;font-weight:300;">' +
							'<span style="font-family:\'Material Symbols Outlined\' !important;font-size:18px;color:' + primary + '">account_circle</span>Profile</a>' +
						'<div style="height:1px;background:#f1f5f9;margin:4px 0;"></div>' +
						'<a href="javascript:void(0)" id="slcm-nav-logout" style="display:flex;align-items:center;gap:10px;padding:12px 16px;text-decoration:none;color:#ef4444;font-size:14px;font-weight:300;">' +
							'<span style="font-family:\'Material Symbols Outlined\' !important;font-size:18px;color:#ef4444">logout</span>Logout</a>' +
					'</div>' +
				'</div>'
			) +
		'</div>';

	document.body.insertBefore(nav, document.body.firstChild);

	// avatar toggle + logout
	window._slcmAvatarToggle = function (e) {
		e.stopPropagation();
		var m = document.getElementById('adm-avatar-menu');
		if (!m) return;
		m.style.display = m.style.display === 'block' ? 'none' : 'block';
	};
	document.addEventListener('click', function (e) {
		var m = document.getElementById('adm-avatar-menu');
		var b = document.getElementById('adm-avatar-btn');
		if (m && !m.contains(e.target) && e.target !== b) m.style.display = 'none';
	});
	var logoutLink = document.getElementById('slcm-nav-logout');
	if (logoutLink) {
		logoutLink.addEventListener('click', function () {
			slcmConfirmLeave(function () {
				frappe.call({ method: 'logout', callback: function () { window.location.href = _nlsatPortalBase() + '/login#login'; } });
			});
		});
	}

	var bellBtn = document.getElementById('slcm-bell-btn');
	if (bellBtn) {
		bellBtn.addEventListener('click', function () {
			slcmConfirmLeave(function () {
				window.location.href = '/nlsat/dashboard';
			});
		});
	}

	// ── FOOTER — mirrors admission_base.html exactly ────────────────
	var yr = new Date().getFullYear();

	var dynColsHtml = '';
	var admCols = cfg.admission_footer || [];
	if (admCols.length > 0) {
		dynColsHtml += '<div class="adm-wf-footer-links" style="grid-column: span 8;flex-grow:1;margin:0 40px;"><div style="display:flex;flex-wrap:wrap;gap:30px;justify-content:flex-start;width:100%;">';
		admCols.forEach(function(col) {
			dynColsHtml += '<div style="min-width:150px;">' +
				'<h4 style="color:' + (footerTextCol || secondary) + ';font-size:14px;font-weight:bold;letter-spacing:.05em;margin:0 0 14px;text-transform:uppercase;">' + _esc(col.title || '') + '</h4>' +
				'<ul style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:8px;">';
			if (col.links && col.links.length) {
				col.links.forEach(function(item) {
					if (item.route) {
						var iColor = footerTextCol ? footerTextCol : 'inherit';
						dynColsHtml += '<li><a href="' + _esc(item.route) + '" style="color:' + iColor + ';font-size:14px;font-weight:normal;text-decoration:none;opacity:0.75;word-break:break-word;">' + _esc(item.label || '') + '</a></li>';
					} else {
						dynColsHtml += '<li><span style="font-size:14px;font-weight:normal;opacity:0.75;display:inline-block;word-break:break-word;color:' + (footerTextCol || 'inherit') + ';">' + _esc(item.label || '') + '</span></li>';
					}
				});
			}
			dynColsHtml += '</ul></div>';
		});
		dynColsHtml += '</div></div>';
	}

	var socialHtml = '';
	if (cfg.social_links && cfg.social_links.length > 0) {
		socialHtml += '<div style="display:flex;flex-direction:column;align-items:flex-end;min-width:220px;">';
		socialHtml += '<div style="display:flex;flex-wrap:wrap;gap:12px;width:210px;justify-content:flex-start;">';
		cfg.social_links.forEach(function (link) {
			if (link.is_active) {
				var p = (link.platform || '').toLowerCase();
				var icon = '';
				var iColor = 'inherit';
				
				if (p === 'facebook') { icon = 'fa-brands fa-facebook'; iColor = '#1877F2'; }
				else if (p === 'instagram') { icon = 'fa-brands fa-instagram'; iColor = '#E4405F'; }
				else if (p.indexOf('twitter') !== -1 || p === 'x') { icon = 'fa-brands fa-x-twitter'; iColor = '#000000'; }
				else if (p === 'linkedin') { icon = 'fa-brands fa-linkedin'; iColor = '#0077b5'; }
				else if (p === 'youtube') { icon = 'fa-brands fa-youtube'; iColor = '#FF0000'; }
				else if (p === 'whatsapp') { icon = 'fa-brands fa-whatsapp'; iColor = '#25D366'; }
				else if (p === 'telegram') { icon = 'fa-brands fa-telegram'; iColor = '#229ED9'; }
				else if (p === 'threads') { icon = 'fa-brands fa-threads'; iColor = '#000000'; }
				else if (p === 'pinterest') { icon = 'fa-brands fa-pinterest'; iColor = '#E60023'; }
				else if (p === 'tiktok') { icon = 'fa-brands fa-tiktok'; iColor = '#000000'; }
				
				if (icon) {
					if (iColor === 'inherit' && footerTextCol) iColor = footerTextCol;
					socialHtml += '<a href="' + _esc(link.url || '') + '" target="_blank" style="color:' + iColor + ' !important;font-size:30px !important;text-decoration:none;transition:transform 0.2s, opacity 0.2s;display:inline-flex;opacity:0.9;" onmouseover="this.style.transform=\'translateY(-3px)\';this.style.opacity=\'1\'" onmouseout="this.style.transform=\'none\';this.style.opacity=\'0.9\'" title="' + _esc(link.platform || '') + '"><i class="' + icon + '"></i></a>';
				}
			}
		});
		socialHtml += '</div></div>';
	}

	var footer = document.createElement('footer');
	footer.id        = 'slcm-adm-footer';
	footer.className = 'adm-wf-footer full-bleed-footer';
	footer.innerHTML =
		'<div class="footer-container">' +
			'<div class="footer-grid" style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:40px;">' +
			// Brand column — school icon + title + tagline
			'<div class="adm-wf-footer-brand" style="min-width:200px;">' +
				'<div style="margin-bottom:16px;display:flex;align-items:flex-start;justify-content:center;">' +
					(cfg.institution_logo
						? '<img src="' + _esc(cfg.institution_logo) + '" style="height:200px;width:200px;object-fit:contain;margin-left:-8px;" alt="Logo" />'
						: '') +
				'</div>' +
			'</div>' +
			// Dynamic Links & Contact
			dynColsHtml +
			// Right side: Social Icons
			socialHtml +
			'</div>' +
			// Bottom bar
			'<div style="margin-top:40px;padding-top:24px;border-top:1px solid rgba(0,0,0,0.1);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;">' +
				'<p style="margin:0;font-size:13px;color:#64748b;opacity:0.8;">© ' + yr + ' ' + _esc(title) + '. All rights reserved.</p>' +
				'<p style="margin:0;font-size:13px;color:#64748b;opacity:0.8;">Powered by <strong style="color:' + (footerTextCol || secondary) + ';font-weight:400;">' + _esc(powerd) + '</strong></p>' +
			'</div>' +
		'</div>';
	document.body.appendChild(footer);
}

function _esc(s) {
	var d = document.createElement('div');
	d.textContent = s == null ? '' : String(s);
	return d.innerHTML;
}

// NLSAT portal the candidate came from (cookie set by the login page, see nlsat_portal.py)
function _nlsatPortalBase() {
	return /(?:^|;\s*)nlsat_portal=International/.test(document.cookie) ? '/nlsat-international' : '/nlsatadmissions';
}

// ───────────────────────────────────────────────────────────────────
//  TOAST — top-right, auto-dismiss 4 s
// ───────────────────────────────────────────────────────────────────
var _toastTimer = null;
/** durationMs optional; default 4000. Stepper validation uses longer messages. */
function showToast(message, type /* success|error|info|warn */, durationMs) {
	var el = document.getElementById('slcm-toast');
	if (!el) {
		el = document.createElement('div');
		el.id = 'slcm-toast';
		el.setAttribute('role', 'alert');
		document.body.appendChild(el);
		el.addEventListener('click', function () {
			el.style.display = 'none';
			if (_toastTimer) clearTimeout(_toastTimer);
		});
	}
	el.className = 'slcm-' + (type || 'info');
	el.textContent = message;
	el.title = __('Click to dismiss');
	el.style.display = 'block';
	if (_toastTimer) clearTimeout(_toastTimer);
	var ms = typeof durationMs === 'number' && durationMs > 0 ? durationMs : 4000;
	_toastTimer = setTimeout(function () { el.style.display = 'none'; }, ms);
}

/** Modal fallback for long validation copy (same content as toast, user must dismiss). */
function showValidationDialog(message) {
	if (typeof frappe !== 'undefined' && frappe.msgprint) {
		frappe.msgprint({
			title: __('Required fields'),
			message: message.replace(/\n/g, '<br>'),
			indicator: 'red',
		});
		return;
	}
	showToast(message, 'error', 12000);
}

// ───────────────────────────────────────────────────────────────────
//  DATA HELPERS
// ───────────────────────────────────────────────────────────────────
function getDocName() {
	var name = frappe.web_form && frappe.web_form.doc && frappe.web_form.doc.name;
	if (!name) {
		var p = new URLSearchParams(window.location.search);
		name = p.get('name') || p.get('doc');
	}
	if (!name && window.location && window.location.pathname) {
		var path = String(window.location.pathname).replace(/\/$/, '');
		var m = path.match(/\/applicant-form\/([^/]+)(?:\/edit)?$/);
		if (m && m[1] && m[1] !== 'new' && m[1] !== 'list') {
			name = decodeURIComponent(m[1]);
		}
	}
	return name || null;
}

/** Absolute URL for /api/... paths — Web Form runs on website bundle (no frappe.urllib). */
function slcmPortalAbsUrl(path) {
	var p = path || '';
	if (p.charAt(0) !== '/') p = '/' + p;
	if (typeof frappe !== 'undefined' && frappe.urllib && typeof frappe.urllib.get_full_url === 'function') {
		return frappe.urllib.get_full_url(p);
	}
	var origin = (typeof window !== 'undefined' && window.location && window.location.origin) || '';
	return origin + p;
}

/** Read a field value from wf.get_value → wf.doc → frappe.reference_doc */
function resolveField(fieldname) {
	var wf = frappe.web_form;
	if (fieldname === 'status' && wf && wf.doc && wf.doc.status) {
		return wf.doc.status;
	}
	var val = '';
	try { val = (wf && wf.get_value(fieldname)) || ''; } catch (e) {}
	if (!val && wf && wf.doc) val = wf.doc[fieldname] || '';
	if (!val && frappe.reference_doc) val = frappe.reference_doc[fieldname] || '';
	return val;
}

/** application_fee_status: same sources as resolveField + visible control text (read-only / slow hydrate). */
function resolveApplicationFeeStatus() {
	var s = (resolveField('application_fee_status') || '').trim();
	if (s) return s;
	try {
		var $cv = $('[data-fieldname="application_fee_status"] .control-value').first();
		if ($cv.length) s = ($cv.text() || '').trim();
		if (!s) {
			var $inp = $('[data-fieldname="application_fee_status"] input, [data-fieldname="application_fee_status"] select').first();
			if ($inp.length) s = ($inp.val() || '').trim();
		}
	} catch (e) {}
	return s || '';
}

/** Mirror server: portal edits only while status is Draft. */
function slcmApplicationPortalLocked() {
	var s = (resolveField('status') || '').trim();
	if (!s) return false;
	var lower = s.toLowerCase();
	return lower !== 'draft' && lower !== 'new';
}

/** Progressive stepper (grey/blue/green) only while status is Draft; any other status = application was finalized. */
function slcmApplicationIsDraft() {
	var s = (resolveField('status') || '').trim();
	return !s || s === 'Draft';
}

function collectDraftData() {
	var wf  = frappe.web_form;
	var doc = (wf && wf.doc) || {};
	var data = {};
	try { data = wf.get_values(true) || {}; } catch (e) {}

	var PRESERVE = [
		'name', 'program', 'admission_cycle', 'academic_year', 'admission_year',
		'campus', 'status', 'application_fee_status',
		'application_fee_amount', 'program_level', 'applicant_id',
	];
	var ref = frappe.reference_doc || {};
	PRESERVE.forEach(function (k) {
		if (!data[k] && doc[k]) data[k] = doc[k];
		if (!data[k] && ref[k])  data[k] = ref[k];
	});

	['ug_degree_details', 'pg_degree_details', 'categories'].forEach(function (ct) {
		if ((!data[ct] || !data[ct].length) && doc[ct] && doc[ct].length) {
			data[ct] = doc[ct];
		}
	});
	// Drop the untouched default row (and any other completely blank degree row)
	['ug_degree_details', 'pg_degree_details'].forEach(function (ct) {
		if (Array.isArray(data[ct])) {
			data[ct] = data[ct].filter(function (row) { return !_slcmIsBlankDegreeRow(row); });
		}
	});
	return data;
}

// ───────────────────────────────────────────────────────────────────
//  APPLICATION STATUS BADGE — injected near the applicant-ID heading
// ───────────────────────────────────────────────────────────────────
function _statusBadgeClass(status) {
	var baseClass = 'slcm-status-badge ';
	if (!status) return baseClass + 'slcm-status-other';
	var s = status.toLowerCase();
	if (s === 'draft')     return baseClass + 'slcm-status-draft';
	if (s === 'submitted') return baseClass + 'slcm-status-submitted';
	if (s === 'submitted and paid' || s === 'completed') return baseClass + 'slcm-status-submitted-and-paid';
	return baseClass + 'slcm-status-other';
}

function updateStatusBadge(status) {
	var badge = document.getElementById('slcm-app-status-badge');
	if (!badge) return;
	badge.className = _statusBadgeClass(status);
	badge.textContent = status || '';
	
	var isNew = false;
	try { isNew = isNewApplicantWebForm(); } catch (e) { }
	var show = (status && !isNew) ? '' : 'none';
	
	badge.style.display = show;

	// Hide Frappe's default "Not Saved" / dirty indicator always to avoid confusing draft users
	$('.indicator-pill.orange, .indicator.orange, .not-saved-badge').hide();

	// Make sure the label is present before the badge
	var label = document.getElementById('slcm-app-status-label');
	if (badge.parentNode && !label) {
		label = document.createElement('span');
		label.id = 'slcm-app-status-label';
		label.className = 'slcm-app-status-label';
		label.textContent = 'Application Status: ';
		badge.parentNode.insertBefore(label, badge);
	}
	if (label) {
		label.style.display = show;
	}
}

function setupStatusBadge() {
	if (window._slcm_badge_done) return;
	var attempts = 0;
	var t = setInterval(function () {
		attempts++;
		// Frappe 16 web-form title selectors (try most specific first)
		var $title = $(
			'.web-form-wrapper .title-area h1, ' +
			'.web-form-head h1, ' +
			'.page-header h1, ' +
			'.web-form-container .page-title'
		).first();

		if (!$title.length) {
			// Fallback: find any heading containing the doc-name pattern
			var docName = getDocName() || '';
			if (docName) {
				$('h1, h2, h3, h4').each(function () {
					if ($(this).text().indexOf(docName.substring(0, 6)) !== -1) {
						$title = $(this);
						return false;
					}
				});
			}
		}

		if ($title.length && !document.getElementById('slcm-app-status-badge')) {
			clearInterval(t);
			window._slcm_badge_done = true;

			var titleEl = $title[0];
			var idText = (titleEl.textContent || '').replace(/\s+/g, ' ').trim();
			titleEl.textContent = '';
			titleEl.classList.add('slcm-app-heading-row');

			var idSpan = document.createElement('span');
			idSpan.id = 'slcm-app-heading-id';
			idSpan.textContent = idText;

			var initStatus = resolveField('status');
			var isNew = false;
			try { isNew = isNewApplicantWebForm(); } catch (e) { }
			var show = (initStatus && !isNew) ? '' : 'none';

			var label = document.createElement('span');
			label.id = 'slcm-app-status-label';
			label.className = 'slcm-app-status-label';
			label.textContent = 'Application Status: ';
			label.style.display = show;

			var badge = document.createElement('span');
			badge.id = 'slcm-app-status-badge';
			badge.className = _statusBadgeClass(initStatus);
			badge.textContent = initStatus || '';
			badge.style.display = show;

			var meta = document.createElement('span');
			meta.id = 'slcm-app-heading-meta';
			meta.appendChild(label);
			meta.appendChild(badge);

			titleEl.appendChild(idSpan);
			titleEl.appendChild(meta);
		}
		if (attempts > 80) clearInterval(t);
	}, 100);
}

// ───────────────────────────────────────────────────────────────────
//  SAVE DRAFT — button + handler
// ───────────────────────────────────────────────────────────────────
function _draftBtnHTML(loading) {
	if (loading) {
		return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" ' +
			'style="animation:slcm-spin .8s linear infinite">' +
			'<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>' +
			' Saving\u2026';
	}
	return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">' +
		'<path stroke-linecap="round" stroke-linejoin="round" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"/></svg>' +
		' Save Draft';
}

function handleSaveDraft(opts) {
	var btn = document.getElementById('slcm-save-draft-btn');
	if (btn) { btn.disabled = true; btn.innerHTML = _draftBtnHTML(true); }

	var data = collectDraftData();

	return new Promise(function (resolve, reject) {
		frappe.call({
			method: 'slcm.admission.web_form.applicant_form.applicant_form.save_applicant_draft',
			args: { data: data, ignore_mandatory: (opts && opts.ignore_mandatory === false) ? false : true },
			freeze: false,
			callback: function (r) {
				if (btn) { btn.disabled = false; btn.innerHTML = _draftBtnHTML(false); }
				var msg = r && r.message;
				if (msg && msg.status === 'success') {
					var wf = frappe.web_form;
				/*
				 * Never use /applicant-form/new?name=DOC — Frappe sees form_dict.name and redirects to
				 * path+/edit → /applicant-form/new/edit (404). Move URL to /applicant-form/DOC/edit without
				 * full reload so Submit flow can keep awaiting handleSaveDraft.
				 */
				if (msg.name) {
					var p = (window.location.pathname || '').replace(/\/$/, '');
					if (p.endsWith('/new')) {
						var rt = (wf && wf.route) || 'applicant-form';
						var newPath = '/' + rt + '/' + encodeURIComponent(msg.name) + '/edit';
						try {
							if (wf && wf.doc) wf.doc.name = msg.name;
							if (wf) {
								wf.is_new = false;
								wf.in_edit_mode = true;
							}
							if (typeof frappe !== 'undefined' && frappe.web_form_doc) {
								frappe.web_form_doc.is_new = false;
								frappe.web_form_doc.in_edit_mode = true;
							}
							window.history.replaceState({}, '', newPath);
						} catch (e2) {}
					} else if (wf && wf.doc && !wf.doc.name) {
						wf.doc.name = msg.name;
					}
				}
				// Set directly on doc — avoids triggering a Frappe field-refresh
				// cascade that would call set_formatted_input on the phone control
				// before its async make_input() has finished.
				try { if (wf && wf.doc) wf.doc.status = 'Draft'; } catch (e) {}
				frappe.form_dirty = false;
				window._slcmUserTouched = false;   // saved — later programmatic refreshes are not "unsaved"
					updateStatusBadge('Draft');
					if (!(opts && opts.silent)) {
						showToast('\u2713  ' + (msg.message || 'Draft saved successfully.'), 'success');
					}
					resolve(msg);
				} else {
					var errMsg = (msg && msg.message) || 'Could not save draft.';
					if (!(opts && opts.silent)) showToast('\u26a0  ' + errMsg, 'error');
					reject(new Error(errMsg));
				}
			},
			error: function () {
				if (btn) { btn.disabled = false; btn.innerHTML = _draftBtnHTML(false); }
				var e = 'Network error. Could not save draft.';
				if (!(opts && opts.silent)) showToast('\u26a0  ' + e, 'error');
				reject(new Error(e));
			},
		});
	});
}

/**
 * Find Frappe's primary action button and inject Save Draft just before it.
 * Uses setInterval so it re-injects on every page/step change.
 */
function setupSaveDraftButton() {
	_injectCSS();

	// Re-check every 500 ms to handle multi-step page changes
	setInterval(function () {
		if (document.getElementById('slcm-save-draft-btn')) return;

		var $primary = $(
			'.web-form-footer .right-area .btn-submit-web-form, ' +
			'.web-form-footer .right-area .btn[type="submit"], ' +
			'.web-form-footer .right-area .btn-primary, ' +
			'.web-form-actions .btn-primary, ' +
			'.page-actions .btn-primary'
		).first();

		if (!$primary.length) {
			$primary = $('form.web-form .btn-primary, .web-form-container .btn-primary').first();
		}

		if ($primary.length) {
			var $btn = $('<button type="button" id="slcm-save-draft-btn"></button>');
			$btn.html(_draftBtnHTML(false));
			$btn.on('click', function (e) {
				e.preventDefault();
				handleSaveDraft();
			});
			// Frappe order: Discard → Next (after discard) → Submit. Place Save Draft before Discard.
			var $discard = $('.web-form-footer .right-area .discard-btn').first();
			if ($discard.length) {
				$discard.before($btn);
			} else {
				$primary.before($btn);
			}
		}
	}, 500);
}

// ───────────────────────────────────────────────────────────────────
//  FEE CALCULATION — silent (no banner)
// ───────────────────────────────────────────────────────────────────
var _feeTimer = null;

function updateFeeForCategory() {
	var wf  = frappe.web_form;
	var doc = (wf && wf.doc) || {};

	var program = resolveField('program');
	if (!program) return;

	var feeStatus = (resolveField('application_fee_status') || '').trim();
	if (feeStatus === 'Paid' || feeStatus === 'Waived') return;

	var category      = resolveField('whether_scstobc_ncl');
	var admissionCycle = resolveField('admission_cycle');

	frappe.call({
		method: 'slcm.admission.web_form.applicant_form.applicant_form.get_application_fee_amount',
		args: {
			program: program,
			category: category || '',
			admission_cycle: admissionCycle || '',
		},
		callback: function (r) {
			if (r && r.message !== undefined && r.message !== null) {
				var fee = parseFloat(r.message) || 0;
				try {
					if (wf && wf.doc) wf.doc.application_fee_amount = fee;
				} catch (e) {}
				if (doc && doc !== (wf && wf.doc)) {
					try { doc.application_fee_amount = fee; } catch (e) {}
				}
				// Update the visible Currency control (category change must reflect in UI).
				try {
					if (wf && typeof wf.set_value === 'function') {
						wf.set_value('application_fee_amount', fee);
					}
				} catch (e) {}
			}
		},
	});
}

function scheduleFeeUpdate() {
	clearTimeout(_feeTimer);
	_feeTimer = setTimeout(updateFeeForCategory, 350);
}

function bindFeeListener() {
	$(document).on(
		'change',
		'[data-fieldname="whether_scstobc_ncl"] select, [data-fieldname="whether_scstobc_ncl"] input',
		scheduleFeeUpdate
	);
	if (frappe.web_form && typeof frappe.web_form.on === 'function') {
		frappe.web_form.on('whether_scstobc_ncl', scheduleFeeUpdate);
	}
}

var _feeReceiptBtnInFlight = false;
var _feeReceiptLastAsk = { name: '', at: 0 };

/** SVG icons for the top-bar buttons */
var _SVG_BACK = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M12 5l-7 7 7 7"/></svg>';
var _SVG_DOWNLOAD = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';

/** Server-provided Program.program_name keyed by program id (from get_program_portal_derivatives). */
var _slcmProgramLabelCache = { id: '', label: '' };

function _slcmEnsureApplyingForWrap(bar) {
	var left = document.getElementById('slcm-form-topbar-left');
	if (!left) {
		left = document.createElement('div');
		left.id = 'slcm-form-topbar-left';
		var back = document.getElementById('slcm-back-btn');
		if (back && back.parentNode === bar) {
			bar.removeChild(back);
			left.appendChild(back);
		}
		var apply = document.createElement('div');
		apply.id = 'slcm-applying-for-wrap';
		apply.setAttribute('aria-live', 'polite');
		apply.innerHTML =
			'<span class="slcm-applying-for-lbl">' +
			__('Applying for:') +
			'</span> ' +
			'<strong id="slcm-applying-for-prog"></strong>';
		left.appendChild(apply);
		bar.insertBefore(left, bar.firstChild);
	} else if (!document.getElementById('slcm-applying-for-wrap')) {
		var apply2 = document.createElement('div');
		apply2.id = 'slcm-applying-for-wrap';
		apply2.setAttribute('aria-live', 'polite');
		apply2.innerHTML =
			'<span class="slcm-applying-for-lbl">' +
			__('Applying for:') +
			'</span> ' +
			'<strong id="slcm-applying-for-prog"></strong>';
		left.appendChild(apply2);
	}
}

/** Update “Applying for: …” next to Back (uses Program name from server when available). */
function syncTopBarApplyingFor() {
	var bar = document.getElementById('slcm-form-topbar');
	if (!bar) {
		return;
	}
	_slcmEnsureApplyingForWrap(bar);
	var wrap = document.getElementById('slcm-applying-for-wrap');
	var strong = document.getElementById('slcm-applying-for-prog');
	if (!wrap || !strong) {
		return;
	}
	var pid = (resolveField('program') || '').trim();
	if (!pid) {
		wrap.style.display = 'none';
		strong.textContent = '';
		return;
	}
	wrap.style.display = '';
	var label = '';
	if (_slcmProgramLabelCache.id === pid && _slcmProgramLabelCache.label) {
		label = _slcmProgramLabelCache.label;
	}
	if (!label) {
		label = pid;
		// Fetch actual program name
		if (window.frappe && frappe.call) {
			frappe.call({
				method: 'frappe.client.get_value',
				args: {
					doctype: 'Programme',
					filters: { name: pid },
					fieldname: 'program_name'
				},
				callback: function(r) {
					if (r && r.message && r.message.program_name) {
						_slcmProgramLabelCache.id = pid;
						_slcmProgramLabelCache.label = r.message.program_name;
						var s = document.getElementById('slcm-applying-for-prog');
						if (s) s.textContent = r.message.program_name;
					}
				}
			});
		}
	}
	strong.textContent = label;
}

/** Ensure the top-bar strip (Back left, Receipt right) exists above the web-form head. */
function _ensureTopBar() {
	var existing = document.getElementById('slcm-form-topbar');
	if (existing) {
		_slcmEnsureApplyingForWrap(existing);
		syncTopBarApplyingFor();
		return document.getElementById('slcm-fee-receipt-wrap');
	}

	var $head = $(
		'.web-form-container .web-form-head, .web-form-head, ' +
			'.web-form-header, .web-form-wrapper .web-form-head'
	).first();
	if (!$head.length) {
		$head = $('form.web-form, .web-form-container, .page-content').first();
	}
	if (!$head.length) return null;

	var bar = document.createElement('div');
	bar.id = 'slcm-form-topbar';

	// ── Back + “Applying for” (left) ─────────────────────────────────
	var topLeft = document.createElement('div');
	topLeft.id = 'slcm-form-topbar-left';

	var backBtn = document.createElement('a');
	backBtn.id = 'slcm-back-btn';
	backBtn.href = 'javascript:void(0)';
	backBtn.title = 'Back';
	backBtn.innerHTML = _SVG_BACK + '<span>Back</span>';
	backBtn.addEventListener('click', function (e) {
		e.preventDefault();
		slcmConfirmLeave(function () {
			history.back();
		});
	});

	var applyWrap = document.createElement('div');
	applyWrap.id = 'slcm-applying-for-wrap';
	applyWrap.setAttribute('aria-live', 'polite');
	applyWrap.innerHTML =
		'<span class="slcm-applying-for-lbl">' +
		__('Applying for:') +
		'</span> ' +
		'<strong id="slcm-applying-for-prog"></strong>';

	topLeft.appendChild(backBtn);
	topLeft.appendChild(applyWrap);
	bar.appendChild(topLeft);

	// ── Receipt placeholder (right) — filled later when receipt is ready ──
	var receiptWrap = document.createElement('div');
	receiptWrap.id = 'slcm-fee-receipt-wrap';
	receiptWrap.style.display = 'none'; // hidden until receipt is confirmed

	bar.appendChild(receiptWrap);

	if ($head.is('form') || ($head.prop('tagName') || '').toLowerCase() === 'form') {
		$head.prepend(bar);
	} else if ($head.hasClass('web-form-container') || $head.hasClass('page-content')) {
		$head.prepend(bar);
	} else {
		$head.before(bar);
	}
	syncTopBarApplyingFor();
	return receiptWrap;
}

function _slcmAppendFeeReceiptButton(applicant, receiptWrap) {
	if (!receiptWrap || document.getElementById('slcm-fee-receipt-btn')) return;
	var btn = document.createElement('button');
	btn.type = 'button';
	btn.id = 'slcm-fee-receipt-btn';
	btn.title = 'Download application fee receipt';
	btn.innerHTML = _SVG_DOWNLOAD + '<span>Receipt</span>';
	btn.onclick = function () {
		var url =
			slcmPortalAbsUrl(
				'/api/method/slcm.admission.web_form.applicant_form.applicant_form.download_portal_application_fee_receipt'
			) + '?applicant_name=' + encodeURIComponent(applicant);
		window.open(url, '_blank', 'noopener,noreferrer');
	};
	receiptWrap.appendChild(btn);
	receiptWrap.style.display = 'flex';
}

/** Paid → show Receipt (client); optional server ready for cases where status is not hydrated yet. */
function syncApplicationFeeReceiptButton() {
	var wf = window.frappe && frappe.web_form;
	if (!wf) return;

	var applicant = getDocName();
	_ensureTopBar();

	if (!applicant) return;

	var st = resolveApplicationFeeStatus();
	var receiptWrap = document.getElementById('slcm-fee-receipt-wrap');
	if (st === 'Pending' || st === 'Requested' || st === 'Waived') {
		if (receiptWrap) {
			receiptWrap.style.display = 'none';
			var old = document.getElementById('slcm-fee-receipt-btn');
			if (old) old.remove();
		}
		return;
	}
	if (st === 'Paid') {
		if (receiptWrap) _slcmAppendFeeReceiptButton(applicant, receiptWrap);		
		return;
	}

	// Fee status unknown on client — fall back to server (receipt row exists)
	if (document.getElementById('slcm-fee-receipt-btn')) return;
	if (_feeReceiptBtnInFlight) return;
	// This runs every 1.2 s; drafts never have a fee status, so without a throttle every open
	// form would hit the server ~50×/min forever. Ask at most once per 30 s per application.
	var _now = Date.now();
	if (_feeReceiptLastAsk.name === applicant && _now - _feeReceiptLastAsk.at < 30000) return;
	_feeReceiptLastAsk = { name: applicant, at: _now };

	_feeReceiptBtnInFlight = true;
	frappe.call({
		method: 'slcm.admission.web_form.applicant_form.applicant_form.portal_application_fee_receipt_ready',
		args: { applicant_name: applicant },
		callback: function (r) {
			_feeReceiptBtnInFlight = false;
			var m = r && r.message;
			if (!m || !m.ready) return;
			_ensureTopBar();
			var wrap = document.getElementById('slcm-fee-receipt-wrap');
			if (!wrap || document.getElementById('slcm-fee-receipt-btn')) return;
			_slcmAppendFeeReceiptButton(applicant, wrap);
		},
		error: function () {
			_feeReceiptBtnInFlight = false;
		},
	});
}

function setupApplicationFeeReceiptDownload() {
	// Inject Back button immediately on load (doesn't need receipt check)
	var t = setInterval(function () {
		if (document.getElementById('slcm-form-topbar') || _ensureTopBar()) {
			clearInterval(t);
		}
	}, 400);
	setInterval(syncApplicationFeeReceiptButton, 1200);
}

/** Hide Frappe header Edit when URL is already .../edit (my-applications opens this directly). */
function setupHideRedundantWebFormEdit() {
	setInterval(function () {
		try {
			var path = (window.location.pathname || '').replace(/\/$/, '');
			if (path.indexOf('/applicant-form/') !== 0 || !/\/edit$/.test(path)) return;
			$('.web-form-header a.edit-button, .web-form-actions a.edit-button').hide();
		} catch (e) {}
	}, 400);
}

/** Locked portal statuses: hide Submit / Save Draft / Edit (footer still shows Discard / nav where shown). */
function setupSubmittedFormUX() {
	setInterval(function () {
		try {
			$('.indicator-pill.orange, .indicator.orange, .not-saved-badge').hide();
		} catch (e) {}

		if (!slcmApplicationPortalLocked()) return;
		try {
			$('#slcm-save-draft-btn').hide();
			$('.edit-button, a.edit-button, .btn-edit').hide();
			$(
				'.web-form-footer .right-area .submit-btn, ' +
					'.web-form-footer .btn-submit-web-form, ' +
					'form.web-form .submit-btn'
			).hide();

			// Hide Frappe built-in "Not Saved" / dirty indicator when not in Draft
			$('.indicator-pill.orange, .indicator.orange, .not-saved-badge').hide();
		} catch (e) {}
	}, 700);
}

var _programDerivTimer = null;

/** When Program or Admission Cycle changes, refresh program_level / intake_type / campus (server). */
function scheduleProgramPortalDerivatives() {
	clearTimeout(_programDerivTimer);
	syncTopBarApplyingFor();
	_programDerivTimer = setTimeout(function () {
		var wf = window.frappe && frappe.web_form;
		if (!wf || typeof wf.get_value !== 'function' || typeof wf.set_value !== 'function') {
			return;
		}
		var program = wf.get_value('program');
		if (!program) {
			_slcmProgramLabelCache = { id: '', label: '' };
			syncTopBarApplyingFor();
			return;
		}

		frappe.call({
			method: 'slcm.admission.web_form.applicant_form.applicant_form.get_program_portal_derivatives',
			args: {
				program: program,
				admission_cycle: wf.get_value('admission_cycle') || '',
			},
			callback: function (r) {
				var d = r && r.message;
				if (!d) return;
				if (program && d.program_label) {
					_slcmProgramLabelCache.id = program;
					_slcmProgramLabelCache.label = d.program_label;
				}
				try {
					if (d.program_level) wf.set_value('program_level', d.program_level);
					if (d.intake_type) wf.set_value('intake_type', d.intake_type);
					if (d.campus) wf.set_value('campus', d.campus);
				} catch (e) {}
				scheduleFeeUpdate();
				syncTopBarApplyingFor();
			},
		});
	}, 320);
}

// ───────────────────────────────────────────────────────────────────
//  SUBMIT INTERCEPT + FULL FLOW
// ───────────────────────────────────────────────────────────────────

/** Show / hide the full-page progress overlay */
function _showSubmitOverlay(msg) {
	var el = document.getElementById('slcm-submit-overlay');
	if (!el) {
		el = document.createElement('div');
		el.id = 'slcm-submit-overlay';
		el.innerHTML = '<div id="slcm-submit-spinner"></div><span id="slcm-submit-msg"></span>';
		document.body.appendChild(el);
	}
	document.getElementById('slcm-submit-msg').textContent = msg || 'Please wait\u2026';
	el.classList.add('open');
}
function _hideSubmitOverlay() {
	var el = document.getElementById('slcm-submit-overlay');
	if (el) el.classList.remove('open');
}

function _slcmEscapeHtml(s) {
	var d = document.createElement('div');
	d.textContent = s == null ? '' : String(s);
	return d.innerHTML;
}

function _slcmEscapeAttr(s) {
	if (s == null) {
		return '';
	}
	return String(s)
		.replace(/&/g, '&amp;')
		.replace(/"/g, '&quot;')
		.replace(/</g, '&lt;');
}

/** Web Form success_url without leading / is resolved under /applicant-form/ — force site-root paths. */
function _slcmNormalizePortalPath(url) {
	if (!url || typeof url !== 'string') {
		return '';
	}
	var u = url.trim();
	if (!u) {
		return '';
	}
	if (/^https?:\/\//i.test(u) || u.indexOf('//') === 0) {
		return u;
	}
	if (u.charAt(0) === '/') {
		return u;
	}
	return '/' + u;
}

function _slcmFormatEeSectionBody(text) {
	if (!text) {
		return '';
	}
	return text
		.split(/\n\n+/)
		.map(function (para) {
			return (
				'<p class="slcm-ee-sec-p">' +
				_slcmEscapeHtml(para).replace(/\n/g, '<br>') +
				'</p>'
			);
		})
		.join('');
}

function _slcmWfGetWebFormField(fieldname) {
	try {
		if (frappe.web_form && typeof frappe.web_form.get_value === 'function') {
			var v = frappe.web_form.get_value(fieldname);
			if (v !== undefined && v !== null) {
				return String(v);
			}
		}
	} catch (e) {}
	return '';
}

/**
 * Formats rejected_reason for the eligibility card: supports '|' (portal) or newline-separated
 * lines from Applicant._build_rule_failure_reason. Omits redundant reservation/category headers.
 */
function _slcmFormatIneligibilityAlertBodyForModal(rawMsg) {
	rawMsg = (rawMsg || '').trim();
	if (!rawMsg) {
		return '';
	}
	var parts;
	if (rawMsg.indexOf('|') !== -1) {
		parts = rawMsg.split('|').map(function (p) { return p.trim(); }).filter(function (p) { return p; });
	} else {
		parts = rawMsg.split(/\r?\n/).map(function (p) { return p.trim(); }).filter(function (p) { return p; });
	}
	parts = parts.filter(function (p) {
		if (/^reservation\s+category$/i.test(p)) {
			return false;
		}
		if (/^•?\s*category:\s*/i.test(p)) {
			return false;
		}
		return true;
	});
	if (parts.length === 0) {
		return '';
	}
	if (parts.length === 1) {
		return _slcmEscapeHtml(parts[0]);
	}
	var title = parts[0].replace(/^\s*•\s*/, '');
	var subParts = parts.slice(1);
	var rowsHtml = '';
	var idx = 1;
	for (var i = 0; i < subParts.length; i++) {
		var p1 = subParts[i].replace(/^\s*•\s*/, '');
		if (p1.indexOf('Minimum required') === 0 && i + 1 < subParts.length) {
			var p2 = subParts[i+1].replace(/^\s*•\s*/, '');
			if (p2.indexOf('You secured') === 0) {
				rowsHtml += '<div style="margin-bottom:4px;font-size:0.8125rem;color:#991b1b;margin-left:8px;">' + idx + '. ' + _slcmEscapeHtml(p1) + ' - ' + _slcmEscapeHtml(p2) + '</div>';
				i++;
				idx++;
				continue;
			}
		}
		rowsHtml += '<div style="margin-bottom:4px;font-size:0.8125rem;color:#991b1b;margin-left:8px;">' + idx + '. ' + _slcmEscapeHtml(p1) + '</div>';
		idx++;
	}

	return (
		'<div style="font-weight:300;margin-bottom:6px;">' +
		_slcmEscapeHtml(title) +
		'</div>' +
		rowsHtml
	);
}

/**
 * Port of slcm/www/application_form/index.html showEligibilityModal(eligRes).
 * Called when check_eligibility returns Ineligible — same table, stats, pipe message, and switch CTA as the application form.
 */
function showSlcmApplicantEligibilityModal(applicantName, eligRes) {
	_injectCSS();
	var existing = document.getElementById('slcm-wf-eligibility-modal-overlay');
	if (existing) {
		existing.remove();
	}
	if (!applicantName) {
		_slcmWfRenderEligibilityModalContent(applicantName, eligRes, {});
		return;
	}
	frappe.call({
		method: 'slcm.admission.web_form.applicant_form.applicant_form.get_applicant_programs_already_applied',
		args: { applicant_name: applicantName },
		callback: function (r) {
			var already = (r.message && r.message.already_applied) || {};
			_slcmWfRenderEligibilityModalContent(applicantName, eligRes, already);
		},
		error: function () {
			_slcmWfRenderEligibilityModalContent(applicantName, eligRes, {});
		},
	});
}

function _slcmWfRenderEligibilityModalContent(applicantName, eligRes, alreadyApplied) {
	alreadyApplied = alreadyApplied || {};
	var existing2 = document.getElementById('slcm-wf-eligibility-modal-overlay');
	if (existing2) {
		existing2.remove();
	}

	var selectedProgram = _slcmWfGetWebFormField('program');
	var campus = _slcmWfGetWebFormField('campus');
	var cycle = _slcmWfGetWebFormField('admission_cycle');

	var programs = (eligRes && eligRes.programs) || [];
	var eligibleCount = programs.filter(function (p) { return p.eligible; }).length;
	var switchablePrograms = programs
		.filter(function (p) {
			return p.eligible && !alreadyApplied[p.program];
		})
		.map(function (p) {
			return p.program;
		});
	var total = programs.length;

	var sorted = programs
		.filter(function (p) { return p.program !== selectedProgram && p.eligible; });

	var rowsHtml = '';
	sorted.forEach(function (p) {
		var isSelected = p.program === selectedProgram;
		var isElig = p.eligible;
		var rowBg = isSelected && !isElig ? '#fff5f5' : isSelected ? '#f0fdf4' : '#fff';
		var badge = isSelected
			? '&nbsp;<span style="font-size:var(--font-size-toast, 10px);padding:2px 8px;background:' +
			  (isElig ? '#27ae60' : '#e74c3c') +
			  ';color:#fff;border-radius:10px;font-weight:300;vertical-align:middle;">' +
			  (isElig ? 'Selected ✓' : 'Choosen Program') +
			  '</span>'
			: '';
		var progDisplay =
			'<strong style="color:#2c3e50;">' + _slcmEscapeHtml(p.program || '') + '</strong>' + badge;
		var statusDot =
			'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;vertical-align:middle;margin-right:4px;background:' +
			(isElig ? '#27ae60' : '#e74c3c') +
			';"></span>';
		var statusLabel =
			'<span style="font-size:var(--font-size-body, 13px);font-weight:300;color:' +
			(isElig ? '#27ae60' : '#e74c3c') +
			';">' +
			(isElig ? 'Eligible' : 'In-Eligible') +
			'</span>';
		var appliedNote =
			isElig && alreadyApplied[p.program]
				? '<div style="font-size:var(--font-size-toast, 11px);color:#64748b;margin-top:6px;font-weight:300;">' +
				  __('Applied') +
				  ' &middot; ' +
				  _slcmEscapeHtml(String(alreadyApplied[p.program])) +
				  '</div>'
				: '';

		var reasonHtml = '';
		if (!isElig && p.reason) {
			var pr = (p.reason || '').split('|').map(function (r) { return r.trim(); }).filter(function (r) { return r; });
			var mainReason = pr[0];
			var subReasons = pr.slice(1);
			reasonHtml =
				'<div style="font-size:var(--font-size-toast, 11px);color:#888;margin-top:4px;font-style:italic;line-height:1.4;">' +
				_slcmEscapeHtml(mainReason) +
				'</div>';
			if (subReasons.length > 0) {
				reasonHtml += subReasons
					.map(function (sr) {
						return (
							'<div style="font-size:var(--font-size-toast, 10px);color:#94a3b8;font-style:normal;margin-top:2px;display:flex;gap:4px;"><span>•</span><span>' +
							_slcmEscapeHtml(sr) +
							'</span></div>'
						);
					})
					.join('');
			}
		}

		rowsHtml +=
			'<tr style="background:' +
			rowBg +
			';">' +
			'<td style="padding:10px 12px;vertical-align:middle;border-bottom:1px solid #eee;">' +
			progDisplay +
			reasonHtml +
			'</td>' +
			'<td style="padding:10px 12px;vertical-align:middle;text-align:center;white-space:nowrap;border-bottom:1px solid #eee;">' +
			'<div style="display:inline-block;text-align:center;">' +
			statusDot +
			statusLabel +
			appliedNote +
			'</div>' +
			'</td>' +
			'</tr>';
	});

	if (!rowsHtml) {
		rowsHtml =
			'<tr><td colspan="2" style="padding:16px;text-align:center;color:#888;">No program data available.</td></tr>';
	}

	var selPName = selectedProgram;
	for (var _i = 0; _i < programs.length; _i++) {
		if (programs[_i].program === selectedProgram && programs[_i].program_name) {
			selPName = programs[_i].program_name;
			break;
		}
	}
	var mainHeading = 'In-Eligible for ' + _slcmEscapeHtml(selPName);

	var rawMsg = ((eligRes && eligRes.message) || (eligRes && eligRes.error) || '').trim();
	if (!rawMsg) {
		rawMsg = 'You do not meet the eligibility criteria for the selected program.';
	}

	/* Same idea as index.html showEligibilityModal: | OR newline-separated reasons; drop redundant category headers. */
	var alertBodyHtml = _slcmFormatIneligibilityAlertBodyForModal(rawMsg);

	var switchBlock = '';
	if (eligibleCount > 0 && switchablePrograms.length > 0) {
		switchBlock =
			'<div style="margin-top:16px; display:flex; justify-content:center;">' +
			'<button type="button" class="slcm-wf-modal-switch-btn" style="display:inline-flex;align-items:center;justify-content:center;gap:10px;padding:12px 24px;font-size:var(--font-size-body, 14px);font-weight:400;border:none;border-radius:12px;background:var(--slcm-primary, #1a3c6e);color:#fff;cursor:pointer;box-shadow:0 10px 15px -3px rgba(15,27,76,0.2);width:auto;">' +
			'<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" style="margin-right:10px; vertical-align:middle;"><path stroke-linecap="round" stroke-linejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"/></svg>' +
			__('Switch to an Eligible Programme Instantly') +
			'</button></div>';
	} else if (eligibleCount > 0 && switchablePrograms.length === 0) {
		switchBlock =
			'<div style="margin-top:16px;padding:12px 16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;text-align:center;font-size:var(--font-size-body, 0.875rem);color:#64748b;">' +
			__('You already have a separate application for every eligible programme in this cycle and campus.') +
			'</div>';
	}

	var html =
		'<div id="slcm-wf-eligibility-modal-overlay" style="position:fixed;inset:0;z-index:199000;display:flex;align-items:center;justify-content:center;padding:1.5rem;font-family:var(--font-family, inherit);background:rgba(15,23,42,0.4);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);">' +
		'<div style="background:#fff;border-radius:20px;width:100%;max-width:680px;box-shadow:0 25px 50px -12px rgba(0,0,0,0.25),0 0 0 1px rgba(0,0,0,0.05);display:flex;flex-direction:column;max-height:90vh;overflow:hidden;">' +
		'<div style="padding:20px 24px;display:flex;justify-content:space-between;align-items:center;background:linear-gradient(135deg,#fef2f2 0%,#fee2e2 100%);border-bottom:1px solid #fecaca;flex-shrink:0;">' +
		'<div style="display:flex;align-items:center;gap:14px;">' +
		'<span style="display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;background:rgba(220,38,38,0.15);border-radius:12px;border:1px solid rgba(220,38,38,0.2);">' +
		'<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="none" viewBox="0 0 24 24" stroke="#dc2626" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>' +
		'</span>' +
		'<div>' +
		'<h3 style="margin:0;font-size:1.125rem;font-weight:400;color:#1e293b;letter-spacing:-0.01em;">Eligibility Evaluation Results</h3>' +
		'<p style="margin:4px 0 0;font-size:0.8125rem;color:#64748b;">Review your programme eligibility below</p>' +
		'</div></div>' +
		'<button type="button" class="slcm-wf-eligibility-modal-close" style="width:40px;height:40px;display:flex;align-items:center;justify-content:center;background:#fff;border:1px solid #e2e8f0;border-radius:10px;cursor:pointer;color:#64748b;font-size:1.25rem;line-height:1;transition:background 0.15s, color 0.15s;" title="Close">&times;</button>' +
		'</div>' +
		'<div style="padding:24px;overflow-y:auto;flex:1;">' +
		'<div style="margin-bottom:24px;padding:18px 20px;background:linear-gradient(135deg,#fff5f5 0%,#fed7d7 8%);border:1px solid #fecaca;border-radius:14px;box-shadow:0 1px 3px rgba(220,38,38,0.08);">' +
		'<div style="font-weight:400;font-size:1rem;color:#b91c1c;margin-bottom:10px;display:flex;align-items:center;gap:8px;">' +
		'<span style="width:6px;height:6px;background:#dc2626;border-radius:50%;"></span>' +
		mainHeading +
		'</div>' +
		'<div style="font-size:var(--font-size-body, 0.875rem);color:#7f1d1d;line-height:1.6;">' +
		alertBodyHtml +
		'</div></div>' +

		'<div style="overflow-x:auto;border-radius:12px;border:1px solid #e2e8f0;overflow:hidden;">' +
		'<table style="width:100%;border-collapse:collapse;font-size:var(--font-size-body, 0.875rem);">' +
		'<thead><tr style="background:#f1f5f9;">' +
		'<th style="padding:14px 18px;text-align:left;font-weight:300;color:#475569;width:70%;border-bottom:2px solid #e2e8f0;">Program</th>' +
		'<th style="padding:14px 18px;text-align:center;font-weight:300;color:#475569;border-bottom:2px solid #e2e8f0;">Eligibility</th>' +
		'</tr></thead><tbody>' +
		rowsHtml +
		'</tbody></table></div>' +
		switchBlock +
		'</div></div></div>';

	document.body.insertAdjacentHTML('beforeend', html);

	var overlay = document.getElementById('slcm-wf-eligibility-modal-overlay');
	if (!overlay) {
		return;
	}

	function closeModal() {
		if (overlay && overlay.parentNode) {
			overlay.remove();
		}
	}
	var closeBtn = overlay.querySelector('.slcm-wf-eligibility-modal-close');
	if (closeBtn) {
		closeBtn.onclick = closeModal;
	}

	var allEligibleIds = programs
		.filter(function (p) {
			return p.eligible;
		})
		.map(function (p) {
			return p.program;
		});
	var sw = overlay.querySelector('.slcm-wf-modal-switch-btn');
	if (sw && applicantName) {
		sw.addEventListener('click', function () {
			_slcmWfHandleToastProgramSwitch(applicantName, allEligibleIds);
		});
	}
}

function _slcmWfExecuteProgramSwitch(applicantName, program, opts) {
	opts = opts || {};
	var confirmBtn = opts.confirmBtn;
	frappe.call({
		method: 'slcm.admission.web_form.applicant_form.applicant_form.switch_applicant_program',
		args: { applicant_name: applicantName, program: program },
		callback: function (r) {
			var m = r && r.message;
			var ov = document.getElementById('slcm-wf-switch-program-overlay');
			if (m && m.status === 'success') {
				if (ov) {
					ov.remove();
				}
				showToast(m.message || __('Programme updated.'), 'success', 5000);
				window.location.reload();
			} else {
				if (confirmBtn) {
					confirmBtn.disabled = false;
					confirmBtn.textContent = __('Update Programme');
				}
				var errSw = (m && m.message) || __('Could not switch programme.');
				showToast(errSw, 'error', errSw.length > 120 ? 10000 : 4000);
			}
		},
		error: function () {
			if (confirmBtn) {
				confirmBtn.disabled = false;
				confirmBtn.textContent = __('Update Programme');
			}
			showToast(__('Could not switch programme.'), 'error');
		},
	});
}

/** Clears toast and opens switch overlay (index.html handleToastProgramSwitch + saveDraft path → web form API + reload). */
function _slcmWfHandleToastProgramSwitch(applicantName, eligibleProgs) {
	if (!eligibleProgs || !eligibleProgs.length || !applicantName) {
		return;
	}
	_injectCSS();
	frappe.call({
		method: 'slcm.admission.web_form.applicant_form.applicant_form.get_applicant_programs_already_applied',
		args: { applicant_name: applicantName },
		callback: function (r) {
			var already = (r.message && r.message.already_applied) || {};
			_slcmWfBuildSwitchProgramOverlay(applicantName, eligibleProgs, already);
		},
		error: function () {
			_slcmWfBuildSwitchProgramOverlay(applicantName, eligibleProgs, {});
		},
	});
}

function _slcmWfBuildSwitchProgramOverlay(applicantName, eligibleProgs, alreadyApplied) {
	alreadyApplied = alreadyApplied || {};
	var eligModal = document.getElementById('slcm-wf-eligibility-modal-overlay');
	if (eligModal) {
		eligModal.remove();
	}
	var tc = document.getElementById('slcm-portal-toast-container');
	if (tc) {
		tc.innerHTML = '';
	}
	var existing = document.getElementById('slcm-wf-switch-program-overlay');
	if (existing) {
		existing.remove();
	}

	var selectable = eligibleProgs.filter(function (pid) {
		return !alreadyApplied[pid];
	});

	if (selectable.length === 0) {
		showToast(
			__(
				'You already have a separate application for each eligible programme in this admission cycle and campus. You cannot switch to another one from here.'
			),
			'info',
			10000
		);
		return;
	}


	var optionsHtml = eligibleProgs
		.map(function (p) {
			var pv = _slcmEscapeAttr(p);
			var pt = _slcmEscapeHtml(p);
			var ref = alreadyApplied[p] ? String(alreadyApplied[p]) : '';
			if (alreadyApplied[p]) {
				return (
					'<div class="slcm-wf-switch-opt slcm-wf-switch-opt--applied" data-value="' +
					pv +
					'" data-applied="1">' +
					'<div class="slcm-wf-switch-radio" style="width:18px;height:18px;border:2px solid #cbd5e1;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;background:#f1f5f9;">' +
					'<div style="width:8px;height:8px;background:#94a3b8;border-radius:50%;display:none !important;"></div></div>' +
					'<span style="font-weight:300;color:#64748b;">' +
					pt +
					'</span>' +
					'<span class="slcm-wf-switch-applied-badge">' +
					__('Applied') +
					'</span>' +
					(ref
						? '<span style="font-size:var(--font-size-toast, 11px);color:#94a3b8;margin-left:6px;">(' +
						  _slcmEscapeHtml(ref) +
						  ')</span>'
						: '') +
					'</div>'
				);
			}
			return (
				'<div class="slcm-wf-switch-opt" data-value="' +
				pv +
				'">' +
				'<div class="slcm-wf-switch-radio" style="width:18px;height:18px;border:2px solid #cbd5e1;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;">' +
				'<div style="width:8px;height:8px;background:#1a3c6e;border-radius:50%;display:none;"></div></div>' +
				'<span style="font-weight:300;color:#334155;">' +
				pt +
				'</span></div>'
			);
		})
		.join('');

	var overlay = document.createElement('div');
	overlay.id = 'slcm-wf-switch-program-overlay';
	overlay.className = 'slcm-portal-switch-shell';
	overlay.style.cssText =
		'position:fixed;inset:0;z-index:200000;background:rgba(15,23,42,0.6);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);display:flex;align-items:center;justify-content:center;padding:20px;font-family:var(--font-family, inherit);';
	overlay.innerHTML =
		'<div class="slcm-portal-switch-card">' +
		'<div style="width:56px;height:56px;background:#f0fdf4;border-radius:16px;display:flex;align-items:center;justify-content:center;margin-bottom:20px;color:#15803d;">' +
		'<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"/></svg></div>' +
		'<h3 style="margin:0 0 8px;font-size:var(--font-size-heading, 1.4rem);font-weight:400;color:#1a3c6e;letter-spacing:-0.02em;">' +
		__('Switch Programme') +
		'</h3>' +
		'<p style="margin:0 0 24px;font-size:var(--font-size-body, 0.95rem);color:#64748b;line-height:1.6;">' +
		__(
			'Please select your new eligible programme. Your current data will be automatically successfully synced.'
		) +
		'</p>' +
		'<div id="slcm-wf-switch-opts-container" style="margin-bottom:28px;max-height:280px;overflow-y:auto;padding-right:4px;">' +
		optionsHtml +
		'</div>' +
		'<div class="slcm-portal-switch-actions" style="display:grid;grid-template-columns:1fr 1.5fr;gap:12px;">' +
		'<button type="button" class="slcm-wf-switch-cancel-btn">' +
		__('Cancel') +
		'</button>' +
		'<button type="button" id="slcm-wf-confirm-switch-btn">' +
		__('Update Programme') +
		'</button></div></div>';
	document.body.appendChild(overlay);
	_injectCSS();

	function selectOpt(el) {
		if (!el || el.classList.contains('slcm-wf-switch-opt--applied')) {
			return;
		}
		var all = overlay.querySelectorAll('.slcm-wf-switch-opt');
		for (var i = 0; i < all.length; i++) {
			all[i].classList.remove('selected');
		}
		el.classList.add('selected');
	}

	var opts = overlay.querySelectorAll('.slcm-wf-switch-opt');
	for (var j = 0; j < opts.length; j++) {
		opts[j].addEventListener('click', function () {
			selectOpt(this);
		});
	}
	var firstOpt = overlay.querySelector('.slcm-wf-switch-opt:not(.slcm-wf-switch-opt--applied)');
	if (firstOpt) {
		selectOpt(firstOpt);
	}
	overlay.querySelector('.slcm-wf-switch-cancel-btn').addEventListener('click', function () {
		overlay.remove();
	});
	var cbtn = document.getElementById('slcm-wf-confirm-switch-btn');
	cbtn.addEventListener('click', function () {
		var selectedOpt = overlay.querySelector('.slcm-wf-switch-opt.selected');
		var newProg = selectedOpt ? selectedOpt.getAttribute('data-value') : null;
		if (!newProg || (selectedOpt && selectedOpt.getAttribute('data-applied') === '1')) {
			showToast(__('Please select a programme you have not already applied for.'), 'error', 7000);
			return;
		}
		cbtn.disabled = true;
		cbtn.innerHTML =
			'<span style="display:inline-block;animation:slcm-spin 1s linear infinite">\u23f3</span> ' +
			__('Processing\u2026');
		_slcmWfExecuteProgramSwitch(applicantName, newProg, { confirmBtn: cbtn });
	});
}

/**
 * Rich "Eligibility Evaluation Results" dialog (data from check_eligibility API).
 * Includes suggested programmes with Switch — avoids duplicating Frappe server throw UI.
 */
function showEligibilityEvaluationModal(applicantName, res) {
	_injectCSS();
	var sug = (res && res.suggestions) || {};
	var programs = sug.programs || [];
	var reason =
		(res && res.failure_reason) ||
		(res && res.message) ||
		'You do not meet the eligibility criteria for the selected program.';

	var modal = document.getElementById('slcm-ee-modal');
	if (!modal) {
		modal = document.createElement('div');
		modal.id = 'slcm-ee-modal';
		modal.setAttribute('role', 'dialog');
		modal.setAttribute('aria-modal', 'true');
		modal.innerHTML =
			'<div id="slcm-ee-backdrop"></div>' +
			'<div id="slcm-ee-panel">' +
				'<div id="slcm-ee-head">' +
					'<h2 id="slcm-ee-title">Eligibility evaluation results</h2>' +
					'<button type="button" id="slcm-ee-close" aria-label="Close">\u00d7</button>' +
				'</div>' +
				'<div id="slcm-ee-body">' +
					'<div class="slcm-ee-alert">' +
						'<span class="slcm-ee-alert-dot"></span>' +
						'<div class="slcm-ee-alert-text" id="slcm-ee-reason"></div>' +
					'</div>' +
					'<div id="slcm-ee-programs-wrap"></div>' +
				'</div>' +
				'<div id="slcm-ee-foot">' +
					'<button type="button" id="slcm-ee-dismiss">Close</button>' +
				'</div>' +
			'</div>';
		document.body.appendChild(modal);

		function closeModal() {
			modal.classList.remove('open');
		}
		function onKey(ev) {
			if (ev.key !== 'Escape') return;
			var m = document.getElementById('slcm-ee-modal');
			if (m && m.classList.contains('open')) m._slcmClose && m._slcmClose();
		}

		document.getElementById('slcm-ee-backdrop').onclick = closeModal;
		document.getElementById('slcm-ee-close').onclick = closeModal;
		document.getElementById('slcm-ee-dismiss').onclick = closeModal;
		modal._slcmClose = closeModal;
		document.addEventListener('keydown', onKey);
	}

	var reasonEl = document.getElementById('slcm-ee-reason');
	var sections = (res && res.failure_sections) || [];
	if (reasonEl) {
		if (sections.length) {
			reasonEl.innerHTML = sections
				.map(function (sec) {
					var h = sec.heading || '';
					var b = sec.body || '';
					return (
						'<div class="slcm-ee-sec">' +
						(h
							? '<h4 class="slcm-ee-sec-title">' + _slcmEscapeHtml(h) + '</h4>'
							: '') +
						'<div class="slcm-ee-sec-body">' +
						_slcmFormatEeSectionBody(b) +
						'</div></div>'
					);
				})
				.join('');
		} else if (reason.indexOf('|') !== -1) {
			reasonEl.innerHTML = reason
				.split('|')
				.map(function (p) {
					return (
						'<p class="slcm-ee-sec-p" style="margin:0 0 8px;">' +
						_slcmEscapeHtml(p.trim()) +
						'</p>'
					);
				})
				.join('');
		} else {
			reasonEl.innerHTML = _slcmFormatEeSectionBody(reason);
		}
	}

	var wrap = document.getElementById('slcm-ee-programs-wrap');
	if (!wrap) return;

	if (!programs.length) {
		wrap.innerHTML =
			'<p style="margin:0;font-size:13px;color:#64748b;">No alternative programmes were found at the same level.</p>';
		modal.classList.add('open');
		return;
	}

	var metaParts = [];
	if (sug.campus) metaParts.push(sug.campus);
	if (sug.cycle) metaParts.push(sug.cycle);
	if (sug.level) metaParts.push(sug.level);
	var metaStr = metaParts.join(' \u00b7 ');

	var ec = sug.eligible_count != null ? sug.eligible_count : programs.length;
	var tc = sug.total_count != null ? sug.total_count : programs.length;

	function _slcmEeFinishProgramsTable(alreadyApplied) {
		alreadyApplied = alreadyApplied || {};
		var rows = programs
			.map(function (p) {
				var name = p.program_name || p.program || '';
				var pid = p.program || '';
				var sel = !!p.selected;
				var progCell =
					'<strong>' +
					_slcmEscapeHtml(name) +
					'</strong>' +
					(sel
						? ' <span class="slcm-ee-badge">Current</span>'
						: '');
				var statusCell =
					'<span class="slcm-ee-status"><span class="slcm-ee-dot"></span> Eligible</span>';
				var actionCell;
				if (sel) {
					actionCell = '<span style="color:#94a3b8;font-size:12px;">\u2014</span>';
				} else if (alreadyApplied[pid]) {
					actionCell =
						'<span style="display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:400;background:#e2e8f0;color:#475569;">' +
						__('Applied') +
						'</span>' +
						'<div style="font-size:11px;color:#94a3b8;margin-top:6px;">' +
						_slcmEscapeHtml(String(alreadyApplied[pid])) +
						'</div>';
				} else {
					actionCell =
						'<button type="button" class="slcm-ee-switch" data-program="' +
						_slcmEscapeAttr(pid) +
						'">Switch</button>';
				}
				return (
					'<tr>' +
					'<td>' +
					progCell +
					'</td>' +
					'<td style="text-align:center;">' +
					statusCell +
					'</td>' +
					'<td style="text-align:center;" class="slcm-ee-td-switch">' +
					actionCell +
					'</td>' +
					'</tr>'
				);
			})
			.join('');

		wrap.innerHTML =
			'<div class="slcm-ee-subhead">' +
			'<strong>Suggested eligible programmes</strong>' +
			(metaStr ? '<span class="slcm-ee-meta">\u2014 ' + _slcmEscapeHtml(metaStr) + '</span>' : '') +
			'</div>' +
			'<div class="slcm-ee-summary">' +
			'<span class="slcm-ee-dot"></span>' +
			'<span><strong>' +
			ec +
			'</strong> eligible programme' +
			(ec === 1 ? '' : 's') +
			' found</span>' +
			'<span style="color:#94a3b8;">(' +
			tc +
			' total at this level)</span>' +
			'</div>' +
			'<div style="overflow-x:auto;">' +
			'<table id="slcm-ee-table">' +
			'<thead><tr>' +
			'<th>Programme</th>' +
			'<th style="text-align:center;">Status</th>' +
			'<th class="slcm-ee-th-actions">Action</th>' +
			'</tr></thead>' +
			'<tbody>' +
			rows +
			'</tbody></table></div>';

		wrap.querySelectorAll('.slcm-ee-switch').forEach(function (btn) {
			btn.onclick = function () {
				var prog = btn.getAttribute('data-program');
				if (!prog || !applicantName) return;
				btn.disabled = true;
				frappe.call({
					method: 'slcm.admission.web_form.applicant_form.applicant_form.switch_applicant_program',
					args: { applicant_name: applicantName, program: prog },
					callback: function (r) {
						var m = r && r.message;
						if (m && m.status === 'success') {
							if (modal._slcmClose) modal._slcmClose();
							showToast(m.message || 'Programme updated.', 'success');
							window.location.reload();
						} else {
							btn.disabled = false;
							var errTb = (m && m.message) || 'Could not switch programme.';
							showToast(errTb, 'error', errTb.length > 120 ? 10000 : 4000);
						}
					},
					error: function () {
						btn.disabled = false;
						showToast('Could not switch programme.', 'error');
					},
				});
			};
		});

		modal.classList.add('open');
	}

	if (!applicantName) {
		_slcmEeFinishProgramsTable({});
		return;
	}
	frappe.call({
		method: 'slcm.admission.web_form.applicant_form.applicant_form.get_applicant_programs_already_applied',
		args: { applicant_name: applicantName },
		callback: function (r) {
			_slcmEeFinishProgramsTable((r.message && r.message.already_applied) || {});
		},
		error: function () {
			_slcmEeFinishProgramsTable({});
		},
	});
}

function _feePayBtnSetLoading(payBtn, loading, label) {
	if (!payBtn) return;
	if (loading) {
		payBtn.innerHTML =
			'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" ' +
			'style="animation:slcm-spin .8s linear infinite;flex-shrink:0" aria-hidden="true">' +
			'<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>' +
			'<span>' + (label || 'Opening\u2026') + '</span>';
	} else if (payBtn.id === 'slcm-fee-pay-btn') {
		payBtn.innerHTML =
			'<span class="slcm-fee-ms" aria-hidden="true">credit_card</span>' +
			'<span>Pay Now</span>' +
			'<span class="slcm-fee-ms slcm-fee-pay-arrow" aria-hidden="true">arrow_forward</span>';
	} else {
		payBtn.textContent = payBtn.id === 'slcm-pay-btn' ? 'Pay Application Fee' : 'Pay Now';
	}
}

/** Fee payment modal */
function _showFeeModal(feeDetails, onPaid) {
	var modal = document.getElementById('slcm-fee-modal');
	if (!modal) {
		modal = document.createElement('div');
		modal.id = 'slcm-fee-modal';
		modal.innerHTML =
			'<div id="slcm-fee-backdrop"></div>' +
			'<div id="slcm-fee-box" role="dialog" aria-modal="true" aria-labelledby="slcm-fee-title">' +
				'<button type="button" id="slcm-fee-close" aria-label="Close"><span class="slcm-fee-ms">close</span></button>' +
				'<div class="slcm-fee-hero" aria-hidden="true">' +
					'<span class="slcm-fee-bubble b1"></span>' +
					'<span class="slcm-fee-bubble b2"></span>' +
					'<span class="slcm-fee-bubble b3"></span>' +
					'<div class="slcm-fee-hero-circle"><span class="slcm-fee-ms">currency_rupee</span></div>' +
				'</div>' +
				'<div class="slcm-fee-title" id="slcm-fee-title">Confirm Your Payment</div>' +
				'<div class="slcm-fee-amount-box">' +
					'<div id="slcm-fee-amount"></div>' +
					'<span class="slcm-fee-secured"><span class="slcm-fee-ms">verified_user</span>Secured</span>' +
				'</div>' +
				'<div class="slcm-fee-callout slcm-fee-info">' +
					'<div class="slcm-fee-callout-icon"><span class="slcm-fee-ms">info</span></div>' +
					'<div class="slcm-fee-callout-text">You are about to complete your application. Please pay the application fee.</div>' +
				'</div>' +
				'<div class="slcm-fee-callout slcm-fee-note">' +
					'<div class="slcm-fee-callout-icon"><span class="slcm-fee-ms">warning</span></div>' +
					'<div class="slcm-fee-callout-text"><strong>Note:</strong> Once the application form is submitted and the application fee is paid, no further modifications will be permitted during subsequent stages of the admission process.</div>' +
				'</div>' +
				'<div class="slcm-fee-actions">' +
					'<button type="button" id="slcm-fee-pay-btn"></button>' +
					'<button type="button" id="slcm-fee-later-btn"><span class="slcm-fee-ms">schedule</span><span>Submit &amp; Pay Later</span></button>' +
				'</div>' +
			'</div>';
		document.body.appendChild(modal);
	}

	var feeNum = Number(feeDetails.fee_amount || 0);
	var amountFormatted = '\u20B9 ' + feeNum.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	document.getElementById('slcm-fee-amount').textContent = amountFormatted;
	var payBtnEl = document.getElementById('slcm-fee-pay-btn');
	if (payBtnEl) {
		payBtnEl.disabled = false;
		_feePayBtnSetLoading(payBtnEl, false);
	}
	// "Submit & Pay Later" only makes sense for a Draft — once the application is
	// submitted (e.g. opened via "Pay Application Fee"), the only option is to pay.
	var laterBtnEl = document.getElementById('slcm-fee-later-btn');
	if (laterBtnEl) {
		var curStatus = (resolveField('status') || '').trim();
		laterBtnEl.style.display = (!curStatus || curStatus === 'Draft') ? '' : 'none';
	}
	modal.classList.add('open');

	function closeModal() { modal.classList.remove('open'); }

	// X only dismisses the dialog — the application stays as it is (no submit)
	document.getElementById('slcm-fee-close').onclick = closeModal;

	document.getElementById('slcm-fee-later-btn').onclick = function () {
		closeModal();
		_doFinalSubmit(feeDetails.applicant_name, 'Submitted');
	};

	document.getElementById('slcm-fee-pay-btn').onclick = function () {
		var payBtn = document.getElementById('slcm-fee-pay-btn');
		payBtn.disabled = true;
		_feePayBtnSetLoading(payBtn, true, 'Creating order\u2026');

		frappe.call({
			method: 'slcm.api.service.fee_service.create_application_fee_razorpay_order',
			args: { applicant_name: feeDetails.applicant_name },
			callback: function (r) {
				var d = r && r.message;
				if (d && d.already_paid) {
					showToast('Application fee has already been paid.', 'success');
					closeModal();
					_doFinalSubmit(feeDetails.applicant_name, 'Submitted and Paid');
					return;
				}
				if (!d || !d.order_id) {
					payBtn.disabled = false;
					_feePayBtnSetLoading(payBtn, false);
					showToast('Could not create payment order. Please try again.', 'error');
					return;
				}

				if (typeof Razorpay === 'undefined') {
					_feePayBtnSetLoading(payBtn, true, 'Loading checkout\u2026');
					// Try loading dynamically
					var sc = document.createElement('script');
					sc.src = 'https://checkout.razorpay.com/v1/checkout.js';
					sc.onload = function () { _openRazorpay(d, feeDetails, onPaid, payBtn, closeModal); };
					sc.onerror = function () {
						payBtn.disabled = false;
						_feePayBtnSetLoading(payBtn, false);
						showToast('Payment gateway script failed to load. Please refresh.', 'error');
					};
					document.head.appendChild(sc);
				} else {
					_feePayBtnSetLoading(payBtn, true, 'Opening checkout\u2026');
					_openRazorpay(d, feeDetails, onPaid, payBtn, closeModal);
				}
			},
			error: function () {
				payBtn.disabled = false;
				_feePayBtnSetLoading(payBtn, false);
				showToast('Network error while creating payment order.', 'error');
			},
		});
	};
}

function _openRazorpay(orderData, feeDetails, onPaid, payBtn, closeModal) {
	var paymentHandled = false;
	var primaryColor = '#1a3c6e';
	try {
		var cssColor = getComputedStyle(document.documentElement).getPropertyValue('--slcm-primary').trim();
		if (cssColor) primaryColor = cssColor;
	} catch (e) {}

	var options = {
		theme: { color: primaryColor },
		key: orderData.key_id,
		amount: orderData.amount,
		currency: orderData.currency || 'INR',
		order_id: orderData.order_id,
		name: 'Application Fee',
		description: 'Application Fee to complete the form',
		handler: function (res) {
			paymentHandled = true;
			_showSubmitOverlay('Verifying payment, Please don\'t refresh or close the page \u2026');
			frappe.call({
				method: 'slcm.api.service.fee_service.verify_application_fee_payment',
				args: {
					razorpay_payment_id: res.razorpay_payment_id,
					razorpay_order_id: res.razorpay_order_id,
					razorpay_signature: res.razorpay_signature,
					applicant_name: feeDetails.applicant_name,
				},
				callback: function (vr) {
					payBtn.disabled = false;
					_feePayBtnSetLoading(payBtn, false);
					if (vr && vr.message && vr.message.status === 'success') {
						showToast('Payment successful!', 'success');
						closeModal();
						_doFinalSubmit(feeDetails.applicant_name, 'Submitted and Paid');
					} else {
						_hideSubmitOverlay();
						showToast((vr && vr.message && vr.message.message) || 'Verification failed.', 'error');
						closeModal();
						_doFinalSubmit(feeDetails.applicant_name, 'Submitted');
					}
				},
				error: function () {
					_hideSubmitOverlay();
					payBtn.disabled = false;
					_feePayBtnSetLoading(payBtn, false);
					showToast('Verification failed. Please contact support.', 'error');
					closeModal();
					_doFinalSubmit(feeDetails.applicant_name, 'Submitted');
				},
			});
		},
		modal: {
			ondismiss: function () {
				if (!paymentHandled) {
					// Handle modal close (e.g. user cancelled)
					closeModal();
					
					// Log the failure so the Payment Request is updated from Requested to Failed/Pending
					frappe.call({
						method: 'slcm.api.service.fee_service.log_application_fee_payment_failure',
						args: {
							applicant_name: feeDetails.applicant_name,
							order_id: orderData.order_id,
							error_data: JSON.stringify({ event: 'modal_dismissed', description: 'User manually closed the payment modal' }),
						},
						callback: function () {
							_doFinalSubmit(feeDetails.applicant_name, 'Submitted');
						},
						error: function () {
							_doFinalSubmit(feeDetails.applicant_name, 'Submitted');
						}
					});
				}
			},
		},
	};

	var rzp = new Razorpay(options);
	rzp.on('payment.failed', function (err) {
		paymentHandled = true;
		frappe.call({
			method: 'slcm.api.service.fee_service.log_application_fee_payment_failure',
			args: {
				applicant_name: feeDetails.applicant_name,
				order_id: orderData.order_id,
				error_data: JSON.stringify(err && err.error ? err.error : err),
			},
		});
		showToast((err && err.error && err.error.description) || 'Payment failed.', 'error');
		payBtn.disabled = false;
		_feePayBtnSetLoading(payBtn, false);
		closeModal();
		_doFinalSubmit(feeDetails.applicant_name, 'Submitted');
	});

	closeModal();
	rzp.open();
	payBtn.disabled = false;
	_feePayBtnSetLoading(payBtn, false);
}

/** Call backend submit_applicant and update UI */
function _doFinalSubmit(applicantName, targetStatus) {
	_showSubmitOverlay('Submitting application, Please don\'t refresh or close the page \u2026');
	frappe.call({
		method: 'slcm.admission.web_form.applicant_form.applicant_form.submit_applicant',
		args: { applicant_name: applicantName, target_status: targetStatus || 'Submitted' },
		callback: function (r) {
			_hideSubmitOverlay();
			var msg = r && r.message;
			if (msg && msg.status === 'success') {
				var finalStatus = msg.doc_status || targetStatus || 'Submitted';
				updateStatusBadge(finalStatus);
				try {
					if (frappe.web_form && frappe.web_form.doc) {
						frappe.web_form.doc.status = finalStatus;
					}
				} catch (e) {}

				if (finalStatus === 'Submitted and Paid' || finalStatus === 'Completed') {
					// ── Use "After Submission" settings ──────────────────────
					var wf = frappe.web_form || {};
					var title = wf.success_title || 'Application Submitted Successfully';
					var message = wf.success_message || '';
					var nextUrl = wf.success_url || '';
					_showSuccessModal(title, message, nextUrl);
				} else {
					showToast('Application saved. Please complete payment from dashboard to finalize.', 'info', 6000);
					setTimeout(function() {
						window.location.reload();
					}, 2000);
				}
			} else {
				showToast('\u26a0  ' + ((msg && msg.message) || 'Submission failed.'), 'error');
			}
		},
		error: function () {
			_hideSubmitOverlay();
			showToast('\u26a0  Network error during submission.', 'error');
		},
	});
}

/** Premium Success Modal */
function _showSuccessModal(title, message, nextUrl) {
	var absDash = _slcmNormalizePortalPath(nextUrl);
	var modalId = 'slcm-success-modal';
	var modal = document.getElementById(modalId);
	if (!modal) {
		modal = document.createElement('div');
		modal.id = modalId;
		// Re-use overlay styles or handle here
		modal.style.cssText =
			'position:fixed;inset:0;z-index:999999;display:flex;align-items:center;justify-content:center;padding:16px;';
		modal.innerHTML =
			'<div style="position:absolute;inset:0;background:rgba(15,23,42,0.6);backdrop-filter:blur(3px);"></div>' +
			'<div style="position:relative;background:#fff;border-radius:20px;width:100%;max-width:500px;' +
			'padding:40px;text-align:center;box-shadow:0 25px 50px -12px rgba(0,0,0,0.5);' +
			'animation:slcm-slide-up 0.4s cubic-bezier(0.16, 1, 0.3, 1);">' +
				'<div style="width:80px;height:80px;background:#f0fdf4;border-radius:50%;margin:0 auto 24px;' +
				'display:flex;align-items:center;justify-content:center;color:#22c55e;border:4px solid #dcfce7;">' +
					'<span style="font-family:Material Symbols Outlined;font-size:48px;font-weight:bold;">check_circle</span>' +
				'</div>' +
				'<h2 style="margin:0 0 12px;font-size:24px;font-weight:400;color:#0f172a;line-height:1.2;">' + _slcmEscapeHtml(title) + '</h2>' +
				'<div style="font-size:15px;line-height:1.6;color:#475569;margin-bottom:32px;">' + message.replace(/\n/g, '<br>') + '</div>' +
				'<div style="display:flex;flex-direction:column;gap:12px;">' +
					(absDash
						? '<a id="slcm-success-goto" href="' +
						  _slcmEscapeAttr(absDash) +
						  '" style="display:flex;align-items:center;justify-content:center;gap:8px;' +
						  'background:var(--slcm-primary,#1a3c6e);color:#fff;padding:14px;border-radius:12px;' +
						  'font-weight:400;text-decoration:none;font-size:16px;transition:all 0.2s;">' +
						  '<span>Go to Dashboard</span><span style="font-family:\'Material Symbols Outlined\' !important;font-size:20px;">arrow_forward</span></a>'
						: '<a id="slcm-success-goto" href="#" style="display:none;"></a>') +
					'<button id="slcm-success-close" style="background:#f1f5f9;color:#475569;border:none;' +
					'padding:14px;border-radius:12px;font-weight:300;cursor:pointer;font-size:15px;">' +
					(nextUrl ? 'Stay on Page' : 'Close and Refresh') + '</button>' +
				'</div>' +
			'</div>';
		document.body.appendChild(modal);
	} else {
		var goExisting = document.getElementById('slcm-success-goto');
		if (goExisting) {
			if (absDash) {
				goExisting.setAttribute('href', absDash);
				goExisting.style.display = '';
			} else {
				goExisting.style.display = 'none';
			}
		}
	}

	// Internal slide-up animation
	if (!document.getElementById('slcm-anim-success')) {
		var s = document.createElement('style');
		s.id = 'slcm-anim-success';
		s.textContent = '@keyframes slcm-slide-up{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}';
		document.head.appendChild(s);
	}

	document.getElementById('slcm-success-close').onclick = function() {
		modal.remove();
		// Always reload so read-only / submitted state and status match the server (incl. "Stay on Page")
		window.location.reload();
	};
}


/**
 * Full submit flow:
 *  1. Save draft with mandatory enforcement  (ignore_mandatory=false)
 *  2. Check eligibility
 *  3. Get fee details
 *  4a. Fee > 0 and not paid → show Razorpay modal → on payment → submit
 *  4b. Fee = 0 or paid/waived → submit directly
 */
function runSubmitFlow() {
	var wf = frappe.web_form;

	// ── Phone validation ──────────────────────────────────────────
	if (typeof window._validate_phone_fields === 'function' && !window._validate_phone_fields()) {
		return;
	}

	// ── Required Check fields (Frappe get_values uses is_null(); is_null(0) is false for unchecked) ──
	var missChkSubmit = _slcmCollectAllEmptyRequiredChecks(wf);
	
	// Explicitly ensure critical checkboxes are checked
	['authorisation_information', 'agreement_to_communications', 'agreement_withdrawal_conditions'].forEach(function(fn) {
		var f = wf.fields_dict[fn];
		if (f && !missChkSubmit.some(function(m) { return m.field === f; })) {
			var val = f.get_value ? f.get_value() : 0;
			if (_slcmCheckValueUnchecked(val)) {
				missChkSubmit.push({ field: f, label: (f.df && f.df.label) || fn });
			}
		}
	});

	if (missChkSubmit.length) {
		_slcmHighlightRequiredCheckFields(missChkSubmit, true);
		showToast(
			'\u26a0 ' +
				__('Please tick all required confirmations before submitting.') +
				' ' +
				__('Missing') +
				': ' +
				missChkSubmit.map(function (m) { return m.label; }).join(', '),
			'error',
			9000
		);
		return;
	}

	// ── 1. Save with mandatory validation ──────────────────────────
	_showSubmitOverlay('Saving and validating, Please don\'t refresh or close the page \u2026');
	handleSaveDraft({ ignore_mandatory: false, silent: true })
		.then(function (saveResult) {
			var applicantName = (saveResult && saveResult.name) || getDocName();
			if (!applicantName) {
				_hideSubmitOverlay();
				showToast('Could not determine applicant. Please save first.', 'error');
				return;
			}

			// ── 2. Eligibility check ────────────────────────────────
			_showSubmitOverlay('Checking eligibility, Please don\'t refresh or close the page \u2026');
			frappe.call({
				method: 'slcm.admission.web_form.applicant_form.applicant_form.check_eligibility',
				args: { applicant_name: applicantName },
				callback: function (r) {
					var res = r && r.message;
					if (!res || res.status === 'Ineligible') {
						_hideSubmitOverlay();
						showSlcmApplicantEligibilityModal(applicantName, res || {});
						return;
					}
					if (res.status === 'Error') {
						_hideSubmitOverlay();
						showToast('\u26a0  ' + ((res && res.message) || 'Eligibility check failed.'), 'error');
						return;
					}

					// ── 3. Fee check ────────────────────────────────
					_showSubmitOverlay('Checking application fee, Please don\'t refresh or close the page \u2026');
					frappe.call({
						method: 'slcm.api.service.application_fee_service.get_application_fee_details',
						args: { applicant_name: applicantName },
						callback: function (fr) {
							_hideSubmitOverlay();
							var fd = fr && fr.message;
							var feeAmount = fd && (fd.fee_amount || 0);
							var canSubmit = fd && fd.can_submit;

							if (feeAmount > 0 && !canSubmit) {
								// ── 4a. Fee required and unpaid ────────────────
								_showFeeModal(fd, function () {
									_doFinalSubmit(applicantName, 'Submitted and Paid');
								});
							} else {
								// ── 4b. No fee / already paid → submit ────────
								_doFinalSubmit(applicantName, 'Submitted and Paid');
							}
						},
						error: function () {
							_hideSubmitOverlay();
							showToast('Could not verify fee status. Please try again.', 'error');
						},
					});
				},
				error: function () {
					_hideSubmitOverlay();
					showToast('Eligibility check failed. Please try again.', 'error');
				},
			});
		})
		.catch(function (err) {
			_hideSubmitOverlay();
			showToast('\u26a0  ' + (err.message || 'Validation failed. Please fill all required fields.'), 'error');
		});
}

/** Override Frappe's web_form.save so our flow runs when Submit is clicked. */
function interceptSubmit() {
	var wf = frappe.web_form;
	if (!wf || wf._slcm_save_patched) return;
	wf._slcm_save_patched = true;
	var _origSave = wf.save.bind(wf);

	/**
	 * Frappe wires: $(".web-form").on("submit", () => this.save());
	 * WebForm.save() must return false so jQuery cancels the native form submit;
	 * otherwise the browser reloads and any modal (e.g. ineligible) disappears.
	 */
	wf.save = function () {
		if (slcmApplicationPortalLocked()) {
			var $sb = $(
				'.web-form-footer .right-area .btn-primary, ' +
					'.web-form-footer .btn-submit-web-form, ' +
					'form.web-form .submit-btn'
			).first();
			var bt = ($sb.text() || '').trim().toLowerCase();
			if (bt === 'submit' || bt.indexOf('submit') !== -1) {
				showToast('This application cannot be edited in its current status.', 'info');
				return false;
			}
		}

		var isLastPage = false;
		try {
			var me = frappe.web_form;
			if (me.is_new && me.is_new()) {
				isLastPage = false;
			} else if (typeof me.current_section !== 'undefined') {
				var sections =
					$('.web-form .form-layout > .form-page').length ||
					(me.pages && me.pages.length) ||
					1;
				isLastPage = me.current_section >= sections - 1;
			} else {
				isLastPage = true;
			}
		} catch (e) {
			isLastPage = false;
		}

		var $btn = $(
			'.web-form-footer .right-area .btn-primary, ' +
				'.web-form-footer .btn-submit-web-form, ' +
				'form.web-form .submit-btn'
		).first();
		var btnText = ($btn.text() || '').trim().toLowerCase();
		var looksLikeSubmit =
			btnText === 'submit' ||
			btnText.indexOf('submit') !== -1 ||
			($('.submit-btn:visible').length > 0 && !$('.btn-next:visible').length);

		if (isLastPage || looksLikeSubmit) {
			runSubmitFlow();
			return false;
		}
		return _origSave();
	};
}

// ───────────────────────────────────────────────────────────────────
//  ATTACH FIELD VALIDATION (Applicant Web Form)
//  • Attach: max 5 MB — png, jpeg, jpg, pdf
//  • Attach Image: max 1 MB — png, jpeg, jpg
//  FileUploader runs in a modal outside .web-form; we wrap the constructor + click context.
// ───────────────────────────────────────────────────────────────────
var _SLCM_ATTACH_MAX_BYTES = 5 * 1024 * 1024;
var _SLCM_ATTACH_IMAGE_MAX_BYTES = 1 * 1024 * 1024;
var _SLCM_ATTACH_ALLOWED = ['png', 'jpeg', 'jpg', 'pdf'];
var _SLCM_ATTACH_IMAGE_ALLOWED = ['png', 'jpeg', 'jpg'];
/** +1 because Frappe uses file.size < max_file_size */
var _SLCM_ATTACH_MAX_STRICT = _SLCM_ATTACH_MAX_BYTES + 1;
var _SLCM_ATTACH_IMAGE_MAX_STRICT = _SLCM_ATTACH_IMAGE_MAX_BYTES + 1;
var _SLCM_ATTACH_FILE_TYPES = [
	'.png', '.jpeg', '.jpg', '.jpe', '.pdf',
	'image/png', 'image/jpeg', 'image/jpg',
	'application/pdf',
];
var _SLCM_ATTACH_IMAGE_FILE_TYPES = [
	'.png', '.jpeg', '.jpg', '.jpe',
	'image/png', 'image/jpeg', 'image/jpg',
];

// ───────────────────────────────────────────────────────────────────
//  STUDENT PHOTO (candidate_photo) — inline preview, all modes / statuses
// ───────────────────────────────────────────────────────────────────

/** Strip ControlAttach "FILENAME,data:image/..." payload to URL/data for <img src>. */
function _slcmNormalizeAttachFieldValue(raw) {
	if (!raw || typeof raw !== 'string') return '';
	var t = raw.trim();
	var m = t.match(/^([^:]+),(.+):(.+)$/);
	if (m) return (m[2] + ':' + m[3]).trim();
	return t;
}

function resolveCandidatePhotoPath() {
	var v = _slcmNormalizeAttachFieldValue(resolveField('candidate_photo') || '');
	if (v) return v;

	var $block = $('[data-fieldname="candidate_photo"]').first();
	if (!$block.length) return '';

	v = $block.find('input[type="hidden"]').val();
	if (v) return _slcmNormalizeAttachFieldValue(String(v).trim());

	v = $block.find('.attached-file-link').attr('href');
	if (v) return _slcmNormalizeAttachFieldValue(String(v).trim());

	v = ($block.find('.control-value').text() || '').trim();
	if (v) return _slcmNormalizeAttachFieldValue(v);

	v = $block.find('a[target="_blank"]').attr('href') || '';
	if (v) return _slcmNormalizeAttachFieldValue(String(v).trim());

	return '';
}

function candidatePhotoToImgSrc(path) {
	if (!path) return '';
	if (/^data:/i.test(path)) return path;
	if (/^https?:\/\//i.test(path)) return path;
	var rel = path.charAt(0) === '/' ? path : '/' + path;
	var parts = rel.split('/');
	var enc = parts.map(function (seg, i) {
		if (i === 0) return seg;
		return encodeURIComponent(seg).replace(/'/g, '%27');
	});
	return slcmPortalAbsUrl(enc.join('/'));
}

function findCandidatePhotoControlWrapper() {
	var $el = $('[data-fieldname="candidate_photo"]').first();
	if (!$el.length) return $();
	var $c = $el.closest('.frappe-control');
	if ($c.length) return $c;
	var $g = $el.closest('.form-group, .webform-group');
	return $g.length ? $g : $el.parent();
}

function syncCandidatePhotoPreview() {
	var path = resolveCandidatePhotoPath();
	var $wrap = findCandidatePhotoControlWrapper();
	if (!$wrap.length) return;

	var $prev = $wrap.children('#slcm-candidate-photo-preview').first();
	if (!path) {
		$prev.remove();
		return;
	}

	var src = candidatePhotoToImgSrc(path);
	if (!src) {
		$prev.remove();
		return;
	}

	if (!$prev.length) {
		$prev = $(
			'<div id="slcm-candidate-photo-preview" class="slcm-candidate-photo-preview">' +
				'<img alt="" decoding="async" />' +
				'</div>'
		);
		$wrap.prepend($prev);
	}

	var $img = $prev.find('img');
	$img.attr('alt', 'Student photo preview');
	if ($img.attr('data-slcm-src') !== src) {
		$img.attr('data-slcm-src', src);
		$img.attr('src', src);
	}

	// Remove mistaken label nodes injected inside .btn-attach (data-fieldname matches button too)
	var $btn = $wrap.find('.btn-attach');
	if ($btn.length && $btn.find('.control-label').length) {
		$btn.find('.control-label').remove();
		$btn.html(__('Attach'));
	}
}

function setupCandidatePhotoPreview() {
	function tick() {
		syncCandidatePhotoPreview();
	}

	tick();
	setInterval(tick, 450);

	$(document).on('click', '.btn-next, .btn-previous', function () {
		setTimeout(tick, 120);
	});

	var bindWf = 0;
	var bindTimer = setInterval(function () {
		bindWf++;
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields_dict && wf.fields_dict.candidate_photo && !wf._slcm_candidate_photo_on) {
			wf._slcm_candidate_photo_on = true;
			try {
				wf.on('candidate_photo', tick);
			} catch (e) {}
		}
		if (wf && wf.events && wf.events.on && !wf._slcm_photo_after_load) {
			wf._slcm_photo_after_load = true;
			try {
				wf.events.on('after_load', tick);
			} catch (e2) {}
		}
		if (bindWf > 100) clearInterval(bindTimer);
	}, 100);
}

function _validateAttachFile(file, fieldtype) {
	if (!file) return true;

	var ext = (file.name || '').split('.').pop().toLowerCase();
	var isImage = fieldtype === 'Attach Image';
	var allowed = isImage ? _SLCM_ATTACH_IMAGE_ALLOWED : _SLCM_ATTACH_ALLOWED;
	var maxBytes = isImage ? _SLCM_ATTACH_IMAGE_MAX_BYTES : _SLCM_ATTACH_MAX_BYTES;
	var maxLabel = isImage ? '1 MB' : '5 MB';

	if (allowed.indexOf(ext) === -1) {
		showToast(
			'\u26a0 Invalid file type “.' +
				ext +
				'”. ' +
				(isImage
					? 'Use png, jpeg, or jpg only (max 1 MB).'
					: 'Use png, jpeg, jpg, or pdf only (max 5 MB).'),
			'error'
		);
		return false;
	}
	if (file.size > maxBytes) {
		showToast(
			'\u26a0 File “' +
				file.name +
				'” exceeds the ' +
				maxLabel +
				' limit (' +
				(file.size / (1024 * 1024)).toFixed(1) +
				' MB).',
			'error'
		);
		return false;
	}
	return true;
}

/** Remember which Attach / Attach Image was opened (uploader modal is outside the form DOM). */
function setupSlcmAttachClickContext() {
	document.addEventListener(
		'click',
		function (e) {
			var t = e.target && e.target.closest && e.target.closest('.btn-attach');
			if (!t || !window.frappe || !frappe.web_form) return;
			if (
				!t.closest(
					'.web-form, .web-form-wrapper, .web-form-container, form.web-form'
				)
			) {
				return;
			}
			var ctrl = t.closest('.frappe-control[data-fieldtype]');
			if (!ctrl) return;
			var ft = ctrl.getAttribute('data-fieldtype');
			if (ft !== 'Attach' && ft !== 'Attach Image') return;
			window._slcmLastAttachCtx = {
				fieldtype: ft,
				fieldname: ctrl.getAttribute('data-fieldname') || '',
				ts: Date.now(),
			};
		},
		true
	);
}

/**
 * Frappe FileUploader filters files in check_restrictions(); empty restrictions allow any type.
 * Merge strict allowed_file_types + max_file_size for Applicant Web Form uploads.
 */
function wrapSlcmApplicantFileUploaderConstructor() {
	if (!window.frappe || !frappe.ui || !frappe.ui.FileUploader) return;
	if (frappe.ui.FileUploader._slcmApplicantWrapped) return;

	var Original = frappe.ui.FileUploader;

	function SlcmFileUploader(opts) {
		opts = opts || {};
		// Force private-only uploads for the applicant form
		opts.is_private = 1;

		// SLCM file uploader options for applicant form
		opts.disable_file_browser = true;
		opts.allow_web_link = false;
		opts.allow_take_photo = false;
		opts.allow_google_drive = false;
		opts.allow_toggle_optimize = false;
		opts.allow_toggle_private = false;
		opts.make_attachments_public = 0;

		if (frappe.web_form && window._slcmLastAttachCtx) {
			var ctx = window._slcmLastAttachCtx;
			if (Date.now() - (ctx.ts || 0) < 120000) {
				var base = Object.assign({}, opts.restrictions || {});
				if (ctx.fieldtype === 'Attach Image') {
					opts.restrictions = Object.assign(base, {
						max_file_size: _SLCM_ATTACH_IMAGE_MAX_STRICT,
						allowed_file_types: _SLCM_ATTACH_IMAGE_FILE_TYPES.slice(),
					});
				} else if (ctx.fieldtype === 'Attach') {
					opts.restrictions = Object.assign(base, {
						max_file_size: _SLCM_ATTACH_MAX_STRICT,
						allowed_file_types: _SLCM_ATTACH_FILE_TYPES.slice(),
					});
				}
			}
		}
		return new Original(opts);
	}

	SlcmFileUploader.UploadOptions = Original.UploadOptions;
	SlcmFileUploader._slcmApplicantWrapped = true;
	frappe.ui.FileUploader = SlcmFileUploader;
}

function setupAttachFieldValidation() {
	setupSlcmAttachClickContext();

	document.addEventListener(
		'change',
		function (e) {
			var input = e.target;
			if (!input || input.type !== 'file' || !window.frappe || !frappe.web_form) return;

			var inForm = input.closest(
				'.web-form-container, form.web-form, .web-form-wrapper'
			);
			var inUploader = input.closest('.file-uploader');
			var ctx = window._slcmLastAttachCtx;
			var ft = null;

			if (inForm) {
				var ctrl = input.closest('[data-fieldtype]');
				ft = ctrl ? ctrl.getAttribute('data-fieldtype') : null;
			} else if (inUploader && ctx && Date.now() - (ctx.ts || 0) < 120000) {
				ft = ctx.fieldtype;
			} else {
				return;
			}

			if (ft !== 'Attach' && ft !== 'Attach Image') return;

			var file = input.files && input.files[0];
			if (!file) return;

			if (!_validateAttachFile(file, ft)) {
				input.value = '';
				e.preventDefault();
				try {
					e.stopImmediatePropagation();
				} catch (err) { /* ignore */ }
			}
		},
		true
	);

	var _upN = 0;
	var _upTimer = setInterval(function () {
		wrapSlcmApplicantFileUploaderConstructor();
		if (
			++_upN > 80 ||
			(window.frappe &&
				frappe.ui &&
				frappe.ui.FileUploader &&
				frappe.ui.FileUploader._slcmApplicantWrapped)
		) {
			clearInterval(_upTimer);
		}
	}, 120);
}

// ───────────────────────────────────────────────────────────────────
//  FORCE PUBLIC UPLOADS — auto-uncheck Private in Frappe upload dialog
// ───────────────────────────────────────────────────────────────────
function _slcmForcePublicInNode(root) {
	if (!root || !root.querySelectorAll) return;
	// 1. Click "Set all public" button if present (handles batch queue)
	root.querySelectorAll('button, .btn').forEach(function (btn) {
		if (!btn._slcmPublicClicked && /set all public/i.test((btn.textContent || '').trim())) {
			btn._slcmPublicClicked = true;
			setTimeout(function () { btn.click(); }, 30);
		}
	});
	// 2. Uncheck any Private checkbox directly
	root.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
		if (cb._slcmPublicDone) return;
		var lbl = cb.closest('label') || cb.parentElement || {};
		var txt = (lbl.textContent || cb.name || cb.id || '').toLowerCase();
		if (txt.indexOf('private') !== -1 && cb.checked) {
			cb._slcmPublicDone = true;
			setTimeout(function () {
				// Trigger Vue reactivity via click, not direct .checked mutation
				if (cb.checked) cb.click();
			}, 40);
		}
	});
}

function setupSlcmForcePublicUploads() {
	// MutationObserver: fires whenever Frappe injects the upload modal into DOM
	var observer = new MutationObserver(function (mutations) {
		mutations.forEach(function (m) {
			m.addedNodes.forEach(function (node) {
				if (!node || node.nodeType !== 1) return;
				// Direct match (the uploader root itself)
				if (node.classList && (node.classList.contains('file-uploader') ||
						node.classList.contains('modal-dialog') ||
						node.classList.contains('modal'))) {
					_slcmForcePublicInNode(node);
				}
				// Descendant match
				if (node.querySelectorAll) {
					node.querySelectorAll('.file-uploader').forEach(_slcmForcePublicInNode);
				}
			});
		});
	});
	observer.observe(document.body, { childList: true, subtree: true });

	// Polling fallback: catches dynamically rendered Vue child nodes
	// that arrive after the modal container is first inserted
	setInterval(function () {
		var uploaders = document.querySelectorAll(
			'.modal.show .file-uploader, ' +
			'.modal[style*="display: block"] .file-uploader, ' +
			'.file-uploader'
		);
		uploaders.forEach(_slcmForcePublicInNode);
		// Also scan open modals for Private checkboxes added by Vue after modal frame
		var modals = document.querySelectorAll('.modal.show, .modal[style*="display: block"]');
		modals.forEach(_slcmForcePublicInNode);
	}, 300);
}


function setupNumericFieldRestriction() {
	// Select common numeric field types used in SLCM (Int, Float, Currency, Percent)
	var NUMERIC_TYPES = ['Int', 'Float', 'Currency', 'Percent'];

	function _slcmNumericWrapper(el) {
		if (!el || !el.closest) return null;
		return el.closest('.frappe-control[data-fieldtype], [data-fieldtype]');
	}

	// keydown backup: keypress does not run for all keys / IME paths
	document.body.addEventListener(
		'keydown',
		function (e) {
			var input = e.target;
			if (!input || input.tagName !== 'INPUT') return;
			var ctrl = _slcmNumericWrapper(input);
			var ft = ctrl ? ctrl.getAttribute('data-fieldtype') : null;
			if (!ft || NUMERIC_TYPES.indexOf(ft) === -1) return;
			if (e.ctrlKey || e.metaKey || e.altKey) return;
			var code = e.keyCode;
			if (code === 8 || code === 9 || code === 13 || code === 27 || code === 46) return;
			if (code >= 35 && code <= 40) return;
			var key = e.key || '';
			if (key.length === 1) {
				if (/\d/.test(key)) return;
				if ((ft === 'Float' || ft === 'Currency' || ft === 'Percent') && key === '.' && input.value.indexOf('.') === -1) {
					return;
				}
				e.preventDefault();
			}
		},
		true
	);

	document.body.addEventListener('keypress', function (e) {
		var input = e.target;
		if (!input || input.tagName !== 'INPUT') return;

		var ctrl = _slcmNumericWrapper(input);
		var ft = ctrl ? ctrl.getAttribute('data-fieldtype') : null;

		if (!ft || NUMERIC_TYPES.indexOf(ft) === -1) return;

		// Key values for digits: 48 to 57
		var charCode = (e.which) ? e.which : e.keyCode;
		
		// Allow: decimal point (46) for Float/Currency/Percent, 
		// but NOT for Int.
		if (charCode === 46) {
			if (ft === 'Int' || input.value.indexOf('.') !== -1) {
				e.preventDefault();
				return false;
			}
			return true;
		}

		// Allow digits only (0-9: 48-57)
		if (charCode > 31 && (charCode < 48 || charCode > 57)) {
			e.preventDefault();
			return false;
		}
		return true;
	});

	// Handle pasted non-numeric values
	document.body.addEventListener('input', function (e) {
		var input = e.target;
		if (!input || input.tagName !== 'INPUT') return;

		var ctrl = _slcmNumericWrapper(input);
		var ft = ctrl ? ctrl.getAttribute('data-fieldtype') : null;

		if (!ft || NUMERIC_TYPES.indexOf(ft) === -1) return;

		var regex = (ft === 'Int') ? /[^0-9]/g : /[^0-9.]/g;
		var val = input.value;
		if (regex.test(val)) {
			input.value = val.replace(regex, '');
		}
	});
}

/** Applicant web form — digit length & numeric bounds (portal). */
var SLCM_APPLICANT_PINCODE_FIELD = 'pincode';
var SLCM_APPLICANT_YEAR_4_FIELDS = {
	class_x_year_of_completion: 1,
	class_xii_year_of_completion: 1,
	year_of_completion: 1,
};
var SLCM_APPLICANT_MAX10_P2_FIELDS = {
	class_x_cgpa: 1,
	if_cgpa_maximum_cgpa_class_xii: 1,
	ug_cgpa: 1,
	pg_cgpa: 1,
};

/** Percentage fields (0–100, 2 decimal places) — not CGPA-on-10 scale. */
var SLCM_APPLICANT_MAX100_P2_FIELDS = {
	class_x_percentage: 1,
	hsc_percentage: 1,
	/** National test “Score or percentage” — percentage or normalized score up to 100. */
	percentage: 1,
};

function _slcmApplicantFormatRuleField(fieldname) {
	if (!fieldname) return false;
	if (fieldname === SLCM_APPLICANT_PINCODE_FIELD) return true;
	return !!(
		SLCM_APPLICANT_YEAR_4_FIELDS[fieldname] ||
		SLCM_APPLICANT_MAX10_P2_FIELDS[fieldname] ||
		SLCM_APPLICANT_MAX100_P2_FIELDS[fieldname]
	);
}

function _slcmApplicantControlFieldname(el) {
	if (!el || !el.closest) return null;
	var c = el.closest('.frappe-control[data-fieldname]');
	return c ? c.getAttribute('data-fieldname') : null;
}

function _slcmClampDecimalInputEl(input, maxVal, precision) {
	var s = (input.value || '').trim();
	if (s === '' || s === '.') return;
	var n = parseFloat(s);
	if (Number.isNaN(n)) return;
	n = Math.max(0, Math.min(maxVal, n));
	var p = Math.pow(10, precision);
	n = Math.round(n * p) / p;
	input.value = String(n);
}

/**
 * Server-style format check. @param rawVal string or number from control / get_value.
 * @returns {string|null} user-facing error line or null if OK / not applicable / empty.
 */
function _slcmApplicantFormatError(fieldname, rawVal, label) {
	var lbl = (label || fieldname || '').trim() || fieldname;
	if (rawVal === undefined || rawVal === null) return null;
	var s0 = typeof rawVal === 'string' ? rawVal.trim() : String(rawVal);
	if (s0 === '') return null;

	if (fieldname === SLCM_APPLICANT_PINCODE_FIELD) {
		var digits = s0.replace(/\D/g, '');
		if (digits.length !== 6) {
			return lbl + ': ' + __('Pincode must be exactly 6 digits');
		}
		return null;
	}

	if (SLCM_APPLICANT_YEAR_4_FIELDS[fieldname]) {
		if (!/^\d{4}$/.test(s0)) {
			return lbl + ': ' + __('Year must be exactly 4 digits');
		}
		var y = parseInt(s0, 10);
		if (y < 1900 || y > 2100) {
			return lbl + ': ' + __('Year must be between 1900 and 2100');
		}
		return null;
	}

	if (SLCM_APPLICANT_MAX100_P2_FIELDS[fieldname]) {
		var n100 = typeof rawVal === 'number' ? rawVal : parseFloat(s0);
		if (Number.isNaN(n100)) {
			return lbl + ': ' + __('Enter a valid number');
		}
		if (n100 < 0) {
			return lbl + ': ' + __('Cannot be negative');
		}
		var max_val = 100;
		if (fieldname === 'hsc_percentage' && window.frappe && frappe.web_form) {
			var cgpa_max = parseFloat(frappe.web_form.get_value('if_cgpa_maximum_cgpa_class_xii'));
			if (!Number.isNaN(cgpa_max) && cgpa_max > 0) {
				max_val = cgpa_max;
			}
		}
		if (n100 > max_val) {
			return lbl + ': ' + __('Cannot be greater than ' + max_val);
		}
		var rounded100 = Math.round(n100 * 100) / 100;
		if (Math.abs(n100 - rounded100) > 1e-6) {
			return lbl + ': ' + __('Use at most 2 decimal places');
		}
		return null;
	}

	if (SLCM_APPLICANT_MAX10_P2_FIELDS[fieldname]) {
		var n = typeof rawVal === 'number' ? rawVal : parseFloat(s0);
		if (Number.isNaN(n)) {
			return lbl + ': ' + __('Enter a valid number');
		}
		if (n < 0) {
			return lbl + ': ' + __('Cannot be negative');
		}
		if (n > 10) {
			return lbl + ': ' + __('Cannot be greater than 10');
		}
		var rounded = Math.round(n * 100) / 100;
		if (Math.abs(n - rounded) > 1e-6) {
			return lbl + ': ' + __('Use at most 2 decimal places');
		}
		return null;
	}

	return null;
}

/** Walk visible controls (includes child-table rows; multiple same fieldname allowed). */
function _slcmValidateApplicantFormatsOnPage(wf, $page, missing) {
	var errSel = '.form-control, .input-with-feedback, .control-value';
	$page.find('.frappe-control[data-fieldname]').each(function () {
		var $w = $(this);
		if ($w.is(':hidden')) return;
		var fn = $w.attr('data-fieldname');
		if (!_slcmApplicantFormatRuleField(fn)) return;

		var $in = $w.find('input:visible, textarea:visible').first();
		var raw = $in.length ? $in.val() : '';
		if (raw === undefined || raw === null) raw = '';
		if (String(raw).trim() === '') return;

		var dfLbl = '';
		try {
			var fd = wf.fields_dict && wf.fields_dict[fn];
			dfLbl = fd && fd.df && fd.df.label ? fd.df.label : '';
		} catch (e1) { /* child row may omit parent fields_dict */ }

		var err = _slcmApplicantFormatError(fn, raw, dfLbl || fn);
		if (err) {
			$w.find(errSel).addClass('slcm-field-error');
			missing.push(err);
		}
	});
}

function setupApplicantFieldBoundaries() {
	document.body.addEventListener(
		'input',
		function (e) {
			var t = e.target;
			if (!t || (t.tagName !== 'INPUT' && t.tagName !== 'TEXTAREA')) return;
			var fn = _slcmApplicantControlFieldname(t);
			if (!fn) return;

			if (fn === SLCM_APPLICANT_PINCODE_FIELD) {
				var pd = String(t.value || '').replace(/\D/g, '').slice(0, 6);
				if (t.value !== pd) t.value = pd;
				return;
			}
			if (SLCM_APPLICANT_YEAR_4_FIELDS[fn]) {
				var yd = String(t.value || '').replace(/\D/g, '').slice(0, 4);
				if (t.value !== yd) t.value = yd;
			}
		},
		true
	);

	document.body.addEventListener(
		'blur',
		function (e) {
			var t = e.target;
			if (!t || t.tagName !== 'INPUT') return;
			var fn = _slcmApplicantControlFieldname(t);
			if (fn && SLCM_APPLICANT_MAX100_P2_FIELDS[fn]) {
				_slcmClampDecimalInputEl(t, 100, 2);
			} else if (fn && SLCM_APPLICANT_MAX10_P2_FIELDS[fn]) {
				_slcmClampDecimalInputEl(t, 10, 2);
			}
		},
		true
	);
}

function setupPhoneValidation() {
	var PHONE_FIELDS = ['mobile_number', 'alternate_contact', 'father_mobile', 'mother_mobile', 'guardian_mobile'];

	// National number lengths (digits after country code). Keys: with and without leading "+".
	var ISD_LENGTHS = {
		// Existing
		'+91': [10], 91: [10],              // India
		'+1': [10], 1: [10],                // USA/Canada
		'+44': [10], 44: [10],              // UK
		'+971': [9], 971: [9],              // UAE
		'+65': [8], 65: [8],                // Singapore
		'+61': [9, 10], 61: [9, 10],        // Australia
		'+966': [9], 966: [9],              // Saudi
	
		// 🔥 Added Top Countries
	
		'+81': [10, 11], 81: [10, 11],      // Japan
		'+49': [10, 11], 49: [10, 11],      // Germany
		'+33': [9], 33: [9],                // France
		'+39': [9, 10], 39: [9, 10],        // Italy
		'+34': [9], 34: [9],                // Spain
		'+86': [11], 86: [11],              // China
		'+82': [9, 10], 82: [9, 10],        // South Korea
		'+7': [10], 7: [10],                // Russia
		'+55': [10, 11], 55: [10, 11],      // Brazil
		'+27': [9], 27: [9],                // South Africa
		'+234': [10], 234: [10],            // Nigeria
		'+20': [10], 20: [10],              // Egypt
		'+92': [10], 92: [10],              // Pakistan
		'+880': [10], 880: [10],            // Bangladesh
		'+62': [10, 11, 12], 62: [10, 11, 12], // Indonesia
		'+63': [10], 63: [10],              // Philippines
		'+60': [9, 10], 60: [9, 10],        // Malaysia
		'+66': [9], 66: [9],                // Thailand
		'+84': [9, 10], 84: [9, 10],        // Vietnam
		'+64': [9, 10], 64: [9, 10],        // New Zealand
	};

	function _slcmPhoneCtrl(input) {
		if (!input || !input.closest) return null;
		return input.closest('.frappe-control[data-fieldtype="Phone"]') ||
			input.closest('[data-fieldtype="Phone"]');
	}

	function _slcmNormalizeIsd(raw) {
		if (raw === undefined || raw === null) return '';
		var s = String(raw).trim().replace(/[^\d+]/g, '');
		if (!s) return '';
		return s.startsWith('+') ? s : ('+' + s);
	}

	function _slcmPhoneIsdLengths(ctrl) {
		if (!ctrl) return null;
		var isdNorm = '';
		var isdEl = ctrl.querySelector('.country') || ctrl.querySelector('.selected-phone .country');
		if (isdEl && isdEl.textContent.trim()) {
			isdNorm = _slcmNormalizeIsd(isdEl.textContent);
		}
		if (!isdNorm) {
			var fn = ctrl.getAttribute('data-fieldname');
			var wf = window.frappe && frappe.web_form;
			if (fn && wf && typeof wf.get_value === 'function') {
				var v = wf.get_value(fn);
				if (v && String(v).indexOf('-') >= 0) {
					var head = String(v).split('-')[0].trim();
					isdNorm = _slcmNormalizeIsd(head.replace(/[^\d+]/g, ''));
				}
			}
		}
		if (!isdNorm) return null;
		var bare = isdNorm.replace(/^\+/, '');
		var lengths = ISD_LENGTHS[isdNorm] || ISD_LENGTHS[bare];
		if (!lengths) return null;
		return { isd: isdNorm, lengths: lengths, limit: Math.max.apply(null, lengths) };
	}

	function _slcmApplyPhoneDigitCap(input) {
		var ctrl = _slcmPhoneCtrl(input);
		if (!ctrl) return;
		var info = _slcmPhoneIsdLengths(ctrl);
		var limit = info ? info.limit : 15;
		input.setAttribute('maxlength', limit);
		var digits = (input.value || '').replace(/\D/g, '');
		if (digits.length > limit) {
			input.value = digits.slice(0, limit);
		}
	}

	// Real-time cap (ISD from flag row or from stored +91-… value while UI still syncing)
	document.body.addEventListener('input', function (e) {
		var input = e.target;
		if (!input || input.tagName !== 'INPUT' || !_slcmPhoneCtrl(input)) return;
		_slcmApplyPhoneDigitCap(input);
	}, true);

	// Block non-digits in national segment; cap length (maxlength is not always enforced for type="tel")
	document.body.addEventListener('keydown', function (e) {
		var input = e.target;
		if (!input || input.tagName !== 'INPUT' || !_slcmPhoneCtrl(input)) return;
		if (e.ctrlKey || e.metaKey || e.altKey) return;
		var k = e.keyCode;
		if (k === 8 || k === 9 || k === 13 || k === 27 || k === 46) return;
		if (k === 35 || k === 36 || k === 37 || k === 38 || k === 39 || k === 40) return;
		var isDigit =
			(k >= 48 && k <= 57) || (k >= 96 && k <= 105) ||
			(e.key && e.key.length === 1 && /\d/.test(e.key));
		if (!isDigit) {
			e.preventDefault();
			return;
		}
		var ctrl = _slcmPhoneCtrl(input);
		var info = _slcmPhoneIsdLengths(ctrl);
		var limit = info ? info.limit : 15;
		var val = input.value || '';
		var digits = val.replace(/\D/g, '');
		var start = typeof input.selectionStart === 'number' ? input.selectionStart : 0;
		var end = typeof input.selectionEnd === 'number' ? input.selectionEnd : 0;
		var selDigits = (val.substring(start, end) || '').replace(/\D/g, '').length;
		if (digits.length - selDigits + 1 > limit) {
			e.preventDefault();
		}
	}, true);

	document.body.addEventListener('paste', function (e) {
		var input = e.target;
		if (!input || input.tagName !== 'INPUT' || !_slcmPhoneCtrl(input)) return;
		setTimeout(function () { _slcmApplyPhoneDigitCap(input); }, 0);
	}, true);

	// Sync when clicking or focusing (handles country picker selection)
	var syncPhone = function (e) {
		var target = e.target;
		setTimeout(function () {
			var input = target.closest ? target.closest('.frappe-control[data-fieldtype="Phone"] input') : null;
			if (!input) {
				input = target.closest ? target.closest('[data-fieldtype="Phone"] input') : null;
			}
			if (!input) return;
			input.dispatchEvent(new Event('input', { bubbles: true }));
		}, 0);
	};
	['click', 'focusin', 'keyup', 'change'].forEach(function (ev) {
		document.body.addEventListener(ev, syncPhone, true);
	});

	document.body.addEventListener('focusout', function (e) {
		var input = e.target;
		if (!input || input.tagName !== 'INPUT' || !_slcmPhoneCtrl(input)) return;
		var ctrl = _slcmPhoneCtrl(input);
		var info = _slcmPhoneIsdLengths(ctrl);
		if (!info) return;
		var val = (input.value || '').replace(/\D/g, '');
		if (val && info.lengths.indexOf(val.length) === -1) {
			var expectedStr = info.lengths.join(' or ');
			showToast('\u26a0 Invalid phone length for ' + info.isd + '. Must be ' + expectedStr + ' digits.', 'error');
			if (val.length > info.limit) input.value = val.slice(0, info.limit);
		}
	}, true);

	window._validate_phone_fields = function () {
		var wf = frappe.web_form;
		var errors = [];

		PHONE_FIELDS.forEach(function (fn) {
			var field = wf.fields_dict[fn];
			if (!field || field.df.hidden || field.df.read_only) return;

			var val = wf.get_value(fn) || '';
			if (!val) return;

			var parts = String(val).split('-');
			var isdRaw = (parts[0] || '').trim();
			var num = parts.slice(1).join('-') || '';

			if (!num) {
				var isRequired = field.df.reqd;
				if (!isRequired && field.df.mandatory_depends_on) {
					try {
						var expr = field.df.mandatory_depends_on.replace(/^eval:/, '');
						isRequired = !!(new Function('doc', 'return (' + expr + ')')(wf.doc));
					} catch (e) { }
				}
				if (isRequired) {
					errors.push((field.df.label || fn) + ' is required.');
				}
				return;
			}

			var isd = _slcmNormalizeIsd(isdRaw.replace(/[^\d+]/g, ''));
			var numClean = num.replace(/\D/g, '');
			var bare = isd.replace(/^\+/, '');
			var expected = ISD_LENGTHS[isd] || ISD_LENGTHS[bare];

			if (expected) {
				if (expected.indexOf(numClean.length) === -1) {
					var expectedStr = expected.join(' or ');
					errors.push((field.df.label || fn) + ': Must be ' + expectedStr + ' digits for ' + isd + '.');
				}
			} else if (numClean.length < 7 || numClean.length > 15) {
				errors.push((field.df.label || fn) + ': Invalid length (' + numClean.length + ').');
			}
		});

		if (errors.length) {
			showToast('\u26a0  ' + errors.join('\n'), 'error');
			return false;
		}
		return true;
	};
}

// ───────────────────────────────────────────────────────────────────
//  QUERY PREFILL — /applicant-form/new?program=...&admission_cycle=...
// ───────────────────────────────────────────────────────────────────
function _slcmShowErrorModal(message, customUrl, customLabel) {
	if (document.getElementById('slcm-error-modal')) return;

	var overlay = document.createElement('div');
	overlay.id = 'slcm-error-modal';
	overlay.style.cssText = [
		'position:fixed', 'inset:0', 'z-index:9999',
		'display:flex', 'align-items:center', 'justify-content:center',
		'background:rgba(0,0,0,0.6)', 'backdrop-filter:blur(5px)'
	].join(';');

	var url = customUrl || '/nlsat/my-profile';
	var label = customLabel || __('My Profile');

	overlay.innerHTML =
		'<div style="max-width:480px;width:90%;background:#fff;border-radius:16px;padding:40px 32px;text-align:center;box-shadow:0 24px 60px rgba(0,0,0,0.2);position:relative;animation:slcmErrorFadeIn 0.35s cubic-bezier(0.16, 1, 0.3, 1)">' +
			'<div style="width:72px;height:72px;background:linear-gradient(135deg,#ef4444,#dc2626);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 24px;box-shadow:0 8px 20px rgba(239,68,68,0.3)">' +
				'<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
					'<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>' +
					'<line x1="12" y1="9" x2="12" y2="13"/>' +
					'<line x1="12" y1="17" x2="12.01" y2="17"/>' +
				'</svg>' +
			'</div>' +
			'<h2 style="font-size:22px;font-weight:700;color:#111827;margin:0 0 14px">' + __('Admission Restriction') + '</h2>' +
			'<p style="font-size:14.5px;color:#4b5563;line-height:1.6;margin:0 0 32px;padding:0 8px">' + _esc(message) + '</p>' +
			'<a href="' + url + '" style="display:inline-block;background:#7B1D1D;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;transition:background 0.2s,transform 0.1s;box-shadow:0 4px 12px rgba(123,29,29,0.2)">' + label + '</a>' +
		'</div>' +
		'<style>' +
			'@keyframes slcmErrorFadeIn{from{opacity:0;transform:scale(0.95)}to{opacity:1;transform:scale(1)}}' +
			'#slcm-error-modal a:hover{background:#5F1616 !important;}' +
		'</style>';

	document.body.appendChild(overlay);
}

// ───────────────────────────────────────────────────────────────────
//  PROGRAMME PICKER — shown when ?program= is absent on /new
// ───────────────────────────────────────────────────────────────────
function _slcmShowProgrammePicker(wf, onConfirm) {
	_slcmRenderSelectProgrammeButton(wf, onConfirm);
	frappe.call({
		method: 'slcm.admission.web_form.applicant_form.applicant_form.get_open_programmes',
		callback: function (r) {
			var programmes = (r && r.message) ? r.message : [];
			_slcmOpenPickerModal(programmes, wf, onConfirm);
		},
		error: function () {
			_slcmOpenPickerModal([], wf, onConfirm);
		}
	});
}

function _slcmOpenPickerModal(programmes, wf, onConfirm) {
	if (document.getElementById('slcm-prog-picker-overlay')) return;

	var primary = getComputedStyle(document.documentElement)
		.getPropertyValue('--slcm-primary').trim() || '#1a3c6e';

	var optionsHtml = '<option value="">— Select a Programme —</option>';
	programmes.forEach(function (p) {
		var val = typeof p === 'object' ? (p.name || p) : p;
		var lbl = typeof p === 'object' ? (p.label || p.name || p) : p;
		optionsHtml += '<option value="' + _esc(val) + '">' + _esc(lbl) + '</option>';
	});

	var overlay = document.createElement('div');
	overlay.id = 'slcm-prog-picker-overlay';
	overlay.style.cssText = 'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(15,23,42,0.6);backdrop-filter:blur(4px);';

	overlay.innerHTML =
		'<div style="background:#fff;border-radius:20px;width:min(480px,92vw);padding:36px 32px;box-shadow:0 24px 60px rgba(0,0,0,0.22);position:relative;animation:slcmPickerIn 0.3s cubic-bezier(0.16,1,0.3,1)">' +
			'<style>@keyframes slcmPickerIn{from{opacity:0;transform:scale(0.94)}to{opacity:1;transform:scale(1)}}</style>' +
			'<div style="width:60px;height:60px;border-radius:50%;background:linear-gradient(135deg,' + primary + ',color-mix(in srgb,' + primary + ' 70%,#000));display:flex;align-items:center;justify-content:center;margin:0 auto 20px;box-shadow:0 8px 20px rgba(0,0,0,0.15)">' +
				'<span class="material-symbols-outlined" style="font-size:30px;color:#fff;font-family:\'Material Symbols Outlined\'!important">school</span>' +
			'</div>' +
			'<h2 style="font-size:20px;font-weight:700;color:#0f172a;text-align:center;margin:0 0 8px">Choose Your Programme</h2>' +
			'<p style="font-size:14px;color:#64748b;text-align:center;margin:0 0 24px;line-height:1.6">Select the programme you wish to apply for. Once confirmed, this <strong>cannot be changed</strong>.</p>' +
			'<div style="margin-bottom:20px">' +
				'<label style="display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:8px">Programme</label>' +
				'<select id="slcm-prog-select" style="width:100%;padding:11px 14px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:14px;color:#0f172a;background:#f8fafc;outline:none;cursor:pointer;appearance:auto">' +
					optionsHtml +
				'</select>' +
			'</div>' +
			'<div id="slcm-prog-warning" style="display:none;background:#fffbeb;border:1px solid #fcd34d;border-radius:10px;padding:12px 14px;font-size:13px;color:#78350f;margin-bottom:20px;line-height:1.5">' +
				'<strong>⚠ Please confirm:</strong> You are applying for <strong id="slcm-prog-warning-name"></strong>. Once you proceed, the programme cannot be changed.' +
			'</div>' +
			'<div style="display:flex;gap:10px">' +
				'<button id="slcm-prog-confirm-btn" style="flex:1;padding:11px;border-radius:10px;border:none;background:' + primary + ';color:#fff;font-size:14px;font-weight:600;cursor:pointer;opacity:0.45;pointer-events:none">Confirm &amp; Proceed</button>' +
			'</div>' +
		'</div>';

	document.body.appendChild(overlay);

	var sel        = document.getElementById('slcm-prog-select');
	var warning    = document.getElementById('slcm-prog-warning');
	var warnName   = document.getElementById('slcm-prog-warning-name');
	var confirmBtn = document.getElementById('slcm-prog-confirm-btn');

	sel.addEventListener('change', function () {
		var chosen = sel.value;
		if (chosen) {
			warning.style.display = 'block';
			warnName.textContent = sel.options[sel.selectedIndex].text;
			confirmBtn.style.opacity = '1';
			confirmBtn.style.pointerEvents = 'auto';
		} else {
			warning.style.display = 'none';
			confirmBtn.style.opacity = '0.45';
			confirmBtn.style.pointerEvents = 'none';
		}
	});

	confirmBtn.addEventListener('click', function () {
		var chosen = sel.value;
		if (!chosen) return;
		overlay.remove();
		var banner = document.getElementById('slcm-select-prog-banner');
		if (banner) banner.remove();
		onConfirm(chosen);
	});


}

function _slcmRenderSelectProgrammeButton(wf, onConfirm) {
	if (document.getElementById('slcm-select-prog-banner')) return;

	var primary = getComputedStyle(document.documentElement)
		.getPropertyValue('--slcm-primary').trim() || '#1a3c6e';

	var banner = document.createElement('div');
	banner.id = 'slcm-select-prog-banner';
	banner.style.cssText = 'width:100%;background:#fffbeb;border-bottom:2px solid #fcd34d;padding:14px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px;box-sizing:border-box;';
	banner.innerHTML =
		'<div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0">' +
			'<span class="material-symbols-outlined" style="font-size:22px;color:#b45309;font-family:\'Material Symbols Outlined\'!important;flex-shrink:0">warning</span>' +
			'<span style="font-size:14px;color:#78350f;font-weight:500">No programme selected. Please choose your programme before filling the application.</span>' +
		'</div>' +
		'<button id="slcm-select-prog-btn" style="padding:9px 20px;border-radius:8px;border:none;background:' + primary + ';color:#fff;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;flex-shrink:0">Select Programme</button>';

	var container = document.querySelector('.web-form-container') || document.querySelector('main') || document.body;
	container.insertBefore(banner, container.firstChild);

	document.getElementById('slcm-select-prog-btn').addEventListener('click', function () {
		if (document.getElementById('slcm-prog-picker-overlay')) return;
		frappe.call({
			method: 'slcm.admission.web_form.applicant_form.applicant_form.get_open_programmes',
			callback: function (r) {
				var programmes = (r && r.message) ? r.message : [];
				_slcmOpenPickerModal(programmes, wf, onConfirm);
			}
		});
	});
}

/**
 * Runs the full prefill + cycle validation flow after the picker confirms a program.
 */
function _slcmRunPrefillWithProgram(wf, program) {
	var params = new URLSearchParams(window.location.search);
	frappe.call({
		method: 'slcm.admission.web_form.applicant_form.applicant_form.validate_new_application_access',
		args: {
			program: program,
			foriegn_national: wf.get_value('foriegn_national') || params.get('foriegn_national') || '',
			nationality: wf.get_value('nationality') || params.get('nationality') || ''
		},
		callback: function (r) {
			var res = r && r.message;
			if (res && !res.allowed) {
				frappe.call({
					method: 'slcm.admission.web_form.applicant_form.applicant_form.get_portal_shell_data',
					callback: function (rd) {
						var url = (rd && rd.message && rd.message.admission_website_url) || '/';
						_slcmShowErrorModal(res.message, url, __('Go to Website'));
					}
				});
				return;
			}
			// Set the program field directly
			var attempts = 0;
			var t = setInterval(function () {
				try {
					var ctrl = wf.fields_dict && wf.fields_dict['program'];
					if (ctrl) {
						clearInterval(t);
						try { wf.set_value('program', res.program || program); } catch (e) { }
						try { wf.set_value('admission_cycle', res.admission_cycle || ''); } catch (e) { }
						try { wf.set_value('admission_year', res.admission_year || ''); } catch (e) { }
						try { wf.set_value('academic_year', res.academic_year || ''); } catch (e) { }
						if (res.campus) {
							try { wf.set_value('campus', res.campus); } catch (e) { }
						}
						if (res.intake_type) {
							try { wf.set_value('intake_type', res.intake_type); } catch (e) { }
						}
						if (res.program_level) {
							try { wf.set_value('program_level', res.program_level); } catch (e) { }
						}
						scheduleProgramPortalDerivatives();
					}
				} catch (err) { }
				if (++attempts > 30) clearInterval(t);
			}, 100);
		}
	});
}

function isNewApplicantWebForm() {
	var path = (window.location.pathname || '').toLowerCase();
	if (path.indexOf('/new') !== -1) return true;
	return !getDocName();
}

function applyQueryStringPrefill() {
	var params = new URLSearchParams(window.location.search);
	
	if (isNewApplicantWebForm() && !params.get('program')) {
		// Wait for web form to be ready before showing picker
		var _pickerTries = 0;
		var _pickerT = setInterval(function () {
			_pickerTries++;
			var wf = window.frappe && frappe.web_form;
			if (wf && typeof wf.set_value === 'function') {
				clearInterval(_pickerT);
				_slcmShowProgrammePicker(wf, function (selectedProg) {
					var url = new URL(window.location.href);
					url.searchParams.set('program', selectedProg);
					window.history.replaceState({}, '', url.toString());
					_slcmRunPrefillWithProgram(wf, selectedProg);
				});
			}
			if (_pickerTries > 100) clearInterval(_pickerT);
		}, 100);
		return;
	}

	if (!params.get('program') && !params.get('admission_cycle')) return;

	var tries = 0;
	var t = setInterval(function () {
		tries++;
		var wf = window.frappe && frappe.web_form;
		if (!wf || typeof wf.set_value !== 'function') {
			if (tries > 120) clearInterval(t);
			return;
		}
		clearInterval(t);
		if (!isNewApplicantWebForm()) return;

		// ── Validate admission cycle and domestic/international scope before allowing new application ──
		frappe.call({
			method: 'slcm.admission.web_form.applicant_form.applicant_form.validate_new_application_access',
			args: {
				program: params.get('program') || '',
				foriegn_national: params.get('foriegn_national') || '',
				nationality: params.get('nationality') || ''
			},
			callback: function (r) {
				var res = r && r.message;
				if (res && !res.allowed) {
					// Lock form
					try { wf.in_edit_mode = false; } catch (e) { }
					if (wf.fields) {
						wf.fields.forEach(function (f) {
							if (f.fieldname) {
								try { wf.set_df_property(f.fieldname, 'read_only', 1); } catch (e2) { }
							}
						});
					}
					$('.web-form input, .web-form select, .web-form textarea').attr('disabled', 'disabled').css('cursor', 'not-allowed');
					$('#slcm-save-draft-btn, .submit-btn, .btn-submit-web-form, .btn-next, .discard-btn').hide();
					// Fetch website URL then show modal
					frappe.call({
						method: 'slcm.admission.web_form.applicant_form.applicant_form.get_portal_shell_data',
						callback: function (rd) {
							var url = (rd && rd.message && rd.message.admission_website_url) || '/';
							_slcmShowErrorModal(res.message, url, __('Go to Website'));
						}
					});
					return; // abort prefill
				}
				// Cycle is open — proceed with normal prefill
				runPrefill(res);
			},
			error: function () {
				// On server error, still allow prefill (fail-open for graceful degradation)
				runPrefill();
			}
		});

		function applyQueryPairs(res) {
			if (res) {
				try { wf.set_value('program', res.program || params.get('program')); } catch (e) {}
				try { wf.set_value('admission_cycle', res.admission_cycle || ''); } catch (e) {}
				try { wf.set_value('admission_year', res.admission_year || ''); } catch (e) {}
				try { wf.set_value('academic_year', res.academic_year || ''); } catch (e) {}
				if (res.campus) {
					try { wf.set_value('campus', res.campus); } catch (e) {}
				}
				if (res.intake_type) {
					try { wf.set_value('intake_type', res.intake_type); } catch (e) {}
				}
				if (res.program_level) {
					try { wf.set_value('program_level', res.program_level); } catch (e) {}
				}
			}

			scheduleFeeUpdate();
		}

		// Wrapped for re-use by the cycle-validation callback
		function runPrefill(res) {
			var SLCM_COPY_SKIP_FIELDS = {
				program: 1,
				admission_cycle: 1,
				admission_year: 1,
				academic_year: 1,
				campus: 1,
				program_level: 1,
				application_type: 1,
				intake_type: 1,
				status: 1,
			};
			frappe.call({
				method: 'slcm.admission.web_form.applicant_form.applicant_form.pop_multiprogram_profile_copy',
				callback: function (r) {
					var payload = r.message;
					if (payload && typeof payload === 'object') {
						Object.keys(payload).forEach(function (k) {
							if (k.indexOf('__') === 0) return;
							if (SLCM_COPY_SKIP_FIELDS[k]) return;
							var v = payload[k];
							if (v === undefined || v === null) return;
							if (Array.isArray(v) && v.length === 0) return;
							try {
								wf.set_value(k, v);
							} catch (e) {}
						});
					}
					applyQueryPairs(res);
					scheduleProgramPortalDerivatives();
				},
				error: function () {
					applyQueryPairs(res);
					scheduleProgramPortalDerivatives();
				},
			});
		}
	}, 80);
}

/** Latest DOB still allowed: 17 full years completed today (no future dates). */
function _slcmMaxDateOfBirth() {
	var d = new Date();
	d.setHours(0, 0, 0, 0);
	d.setFullYear(d.getFullYear() - 17);
	return d;
}

/** Completed age in years from yyyy-mm-dd (or null if invalid). -1 if date is in the future. */
function _slcmAgeCompletedYears(dobVal) {
	if (dobVal === undefined || dobVal === null || dobVal === '') return null;
	var s = String(dobVal).trim();
	var parts = s.split('-');
	if (parts.length < 3) return null;
	var y = parseInt(parts[0], 10);
	var mo = parseInt(parts[1], 10) - 1;
	var day = parseInt(parts[2], 10);
	if (isNaN(y) || isNaN(mo) || isNaN(day)) return null;
	var birth = new Date(y, mo, day);
	if (isNaN(birth.getTime())) return null;
	var today = new Date();
	today.setHours(0, 0, 0, 0);
	birth.setHours(0, 0, 0, 0);
	if (birth > today) return -1;
	var age = today.getFullYear() - birth.getFullYear();
	var md = today.getMonth() - birth.getMonth();
	if (md < 0 || (md === 0 && today.getDate() < birth.getDate())) age--;
	return age;
}

/** Web Form: cap DOB datepicker (max = today − 17 years) and enforce age on change. */
function _slcmTryPatchDateOfBirth(wf) {
	if (!wf || !wf.fields_dict) return;
	var fd = wf.fields_dict.date_of_birth;
	if (!fd || fd.df.fieldtype !== 'Date') return;

	var maxD = _slcmMaxDateOfBirth();
	if (fd.datepicker && typeof fd.datepicker.update === 'function') {
		try {
			fd.datepicker.update({ maxDate: maxD });
		} catch (e) { /* ignore */ }
	}

	if (!fd._slcmDobListeners && fd.$input && fd.$input.length) {
		fd._slcmDobListeners = true;
		fd.$input.on('change.slcmdob', function () {
			var v = wf.get_value && wf.get_value('date_of_birth');
			var age = _slcmAgeCompletedYears(v);
			if (v && (age === null || age < 17)) {
				frappe.msgprint({
					title: __('Invalid Date of Birth'),
					message: __('Applicant must be at least 17 years old. The date cannot be in the future.'),
					indicator: 'red',
				});
				if (typeof wf.set_value === 'function') {
					wf.set_value('date_of_birth', '');
				}
			}
		});
	}
}

/**
 * All Date controls: block letters / stray chars in the text input (flatpickr still works via picker).
 */
function setupWebFormDateInputSanitize() {
	function dateInput(el) {
		return (
			el &&
			el.tagName === 'INPUT' &&
			el.closest &&
			el.closest('.frappe-control[data-fieldtype="Date"], [data-fieldtype="Date"]')
		);
	}
	function stripBad(input) {
		var v = input.value || '';
		var cleaned = v.replace(/[^\d\-/.]/g, '');
		if (cleaned !== v) input.value = cleaned;
	}
	document.body.addEventListener(
		'keydown',
		function (e) {
			var input = e.target;
			if (!dateInput(input)) return;
			if (e.ctrlKey || e.metaKey || e.altKey) return;
			var code = e.keyCode;
			var key = e.key || '';
			if (key === 'Tab' || key === 'Enter' || code === 8 || code === 9 || code === 27 || code === 46) return;
			if (code >= 35 && code <= 40) return;
			if (key.length === 1 && /[\d\-/.]/.test(key)) return;
			if (key.length === 1) {
				e.preventDefault();
			}
		},
		true
	);
	document.body.addEventListener(
		'input',
		function (e) {
			var input = e.target;
			if (!dateInput(input)) return;
			stripBad(input);
		},
		true
	);
	document.body.addEventListener(
		'paste',
		function (e) {
			var input = e.target;
			if (!dateInput(input)) return;
			setTimeout(function () {
				stripBad(input);
			}, 0);
		},
		true
	);
}

/**
 * New web form: Int/Float often hydrate as 0; clear so controls look empty unless the user typed 0.
 */
function slcmClearDefaultZeroNumericFields() {
	var wf = window.frappe && frappe.web_form;
	if (!wf || !wf.is_new || wf.allow_incomplete) return;
	var fields = wf.fields || [];
	for (var i = 0; i < fields.length; i++) {
		var df = fields[i];
		if (!df || !df.fieldname) continue;
		if (df.fieldtype !== 'Int' && df.fieldtype !== 'Float') continue;
		if (df.read_only || df.hidden) continue;
		var v;
		try {
			v = wf.get_value(df.fieldname);
		} catch (e) {
			continue;
		}
		if (v === 0 || v === 0.0) {
			try {
				wf.set_value(df.fieldname, '');
			} catch (e2) {}
		}
	}
}

function setupDateOfBirthWebForm() {
	function tick() {
		var wf = window.frappe && frappe.web_form;
		_slcmTryPatchDateOfBirth(wf);
	}
	if (window.frappe && frappe.web_form && frappe.web_form.events && frappe.web_form.events.on) {
		frappe.web_form.events.on('after_load', function () {
			setTimeout(tick, 0);
		});
	}
	var n = 0;
	var t = setInterval(function () {
		tick();
		var wf = window.frappe && frappe.web_form;
		var fd = wf && wf.fields_dict && wf.fields_dict.date_of_birth;
		if (fd && fd._slcmDobListeners && fd.datepicker) {
			clearInterval(t);
		} else if (++n > 150) {
			clearInterval(t);
		}
	}, 100);
}

/** Remove red validation outline as soon as the user edits the control. */
function setupSlcmFieldErrorClear() {
	$(document).on(
		'input change',
		'.web-form input, .web-form textarea, .web-form select',
		function () {
			var $t = $(this);
			$t.removeClass('slcm-field-error');
			$t.closest('.frappe-control').find('.slcm-field-error').removeClass('slcm-field-error');
		}
	);
}

/**
 * Frappe grid_row repositions Awesomplete for Link cells using getBoundingClientRect mixed with
 * jQuery .offset() (viewport vs document), so lists jump to the top after scroll. Core also uses
 * overflow on .form-grid. Re-anchor the list with position:fixed under the focused input.
 */
/** Nearest ancestor that becomes the containing block for position:fixed descendants (or null = viewport). */
function _slcmFixedContainingBlock(el) {
	var node = el && el.parentElement;
	while (node && node !== document.body && node !== document.documentElement) {
		var cs = getComputedStyle(node);
		if (
			(cs.transform && cs.transform !== 'none') ||
			(cs.perspective && cs.perspective !== 'none') ||
			(cs.filter && cs.filter !== 'none') ||
			(cs.backdropFilter && cs.backdropFilter !== 'none') ||
			/transform|perspective|filter/.test(cs.willChange || '') ||
			/paint|layout|strict|content/.test(cs.contain || '')
		) {
			return node;
		}
		node = node.parentElement;
	}
	return null;
}

function setupSlcmWebFormAwesompletePositionFix() {
	var scrollHandler = null;

	function detachScroll() {
		if (!scrollHandler) {
			return;
		}
		window.removeEventListener('scroll', scrollHandler, true);
		document.querySelectorAll('.web-form').forEach(function (el) {
			el.removeEventListener('scroll', scrollHandler);
		});
		scrollHandler = null;
	}

	function placeListUnderInput(input) {
		if (!input || !input.getAttribute) {
			return;
		}
		var listId = input.getAttribute('aria-owns');
		if (!listId || listId.indexOf('awesomplete_list_') !== 0) {
			return;
		}
		var ul = document.getElementById(listId);
		if (!ul || ul.hasAttribute('hidden')) {
			return;
		}
		var rect = input.getBoundingClientRect();
		if (!rect.width && !rect.height) {
			return;
		}
		// Inside the child-table "Editing Row" panel an ancestor is transformed, and position:fixed
		// is then relative to that ancestor, not the viewport — subtract its offset.
		var cb = _slcmFixedContainingBlock(ul);
		var cbRect = cb ? cb.getBoundingClientRect() : { left: 0, top: 0 };
		$(ul).css({
			position: 'fixed',
			left: Math.round(rect.left - cbRect.left) + 'px',
			top: Math.round(rect.bottom + 4 - cbRect.top) + 'px',
			width: Math.max(180, Math.round(rect.width)) + 'px',
			// Frappe sets min-width:100% inline; with position:fixed that is 100% of the
			// viewport, which stretched every dropdown across the whole screen.
			minWidth: '0',
			zIndex: 10050,
			maxHeight: 'min(60vh, 300px)',
			overflowY: 'auto',
		});
	}

	function resetListStyles(input) {
		var listId = input && input.getAttribute && input.getAttribute('aria-owns');
		if (!listId) {
			return;
		}
		var ul = document.getElementById(listId);
		if (!ul) {
			return;
		}
		$(ul).css({
			position: '',
			left: '',
			top: '',
			width: '',
			minWidth: '100%',
			zIndex: '',
			maxHeight: '',
			overflowY: '',
		});
	}

	$(document).on('awesomplete-open', '.web-form input[aria-owns^="awesomplete_list_"]', function () {
		var input = this;
		var run = function () {
			placeListUnderInput(input);
		};
		requestAnimationFrame(run);
		setTimeout(run, 0);
		setTimeout(run, 320);
		detachScroll();
		scrollHandler = function () {
			placeListUnderInput(input);
		};
		window.addEventListener('scroll', scrollHandler, true);
		document.querySelectorAll('.web-form').forEach(function (el) {
			el.addEventListener('scroll', scrollHandler, { passive: true });
		});
	});

	$(document).on('awesomplete-close', '.web-form input[aria-owns^="awesomplete_list_"]', function () {
		resetListStyles(this);
		detachScroll();
	});
}


// Make input in Uppercase
function makeInputUppercase() {
	const uppercase_fields = [
		"candidate_name",
		"father_occupation",
		"mother_occupation",
		"correspondence_address",
		"father_name",
		"mother_name",
		"class_x_school",
		"class_x_board",
		"class_xii_name_of_examination",
		"class_xii_school",
		"class_xii_board",
		"proposed_phd_topic",
		"other_degree_details",
		"foreigin_city",
		"board_uni_pg",
		"board_uni_ug"
	];

	uppercase_fields.forEach(fieldname => {
		let field = frappe.web_form.get_field(fieldname);
		if (field && field.$input) {
			field.$input.css('text-transform', 'uppercase');
			field.$input.on('input', function() {
				let start = this.selectionStart;
				let end = this.selectionEnd;
				this.value = this.value.toUpperCase();
				this.setSelectionRange(start, end);
			});
		}

		if (field) {
			frappe.web_form.on(fieldname, (f, value) => {
				if (value) {
					frappe.web_form.set_value(
						fieldname,
						value.toUpperCase()
					);
				}
			});
		}
	});

	// For child table fields (UG/PG details) which are rendered dynamically
	$('body').on('input', '[data-fieldname="ug_program"] input, [data-fieldname="college"] input, [data-fieldname="board_uni_ug"] input, [data-fieldname="pg_program"] input, [data-fieldname="collegeuniversity"] input, [data-fieldname="board_uni_pg"] input, [data-fieldname="country"] input', function() {
		let start = this.selectionStart;
		let end = this.selectionEnd;
		this.value = this.value.toUpperCase();
		this.setSelectionRange(start, end);
	});

	const display_uppercase_fields = [
		"country", "state", "city", "hsc_group", "national_test_name","first_preference","second_preference","third_preference", "x_country", "xii_country"
	];

	let parent_display_selectors = display_uppercase_fields.map(f => 
		`[data-fieldname="${f}"] input, [data-fieldname="${f}"] select, [data-fieldname="${f}"] .awesomplete ul li`
	).join(', ');

	let all_css_selectors = [parent_display_selectors].filter(Boolean).join(', ');

	$(`<style>${all_css_selectors} { text-transform: uppercase; }</style>`).appendTo('head');
}

// ───────────────────────────────────────────────────────────────────

function setupPreferenceValidation() {
	var n = 0;
	var t = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields_dict) {
			clearInterval(t);

			function validatePreferences() {
				var f1 = wf.get_value('first_preference');
				var f2 = wf.get_value('second_preference');
				var f3 = wf.get_value('third_preference');

				if (f1 && f2 && f1 === f2) {
					frappe.msgprint('First and Second Preferences cannot be the same.');
					wf.set_value('second_preference', '');
				}
				if (f1 && f3 && f1 === f3) {
					frappe.msgprint('First and Third Preferences cannot be the same.');
					wf.set_value('third_preference', '');
				}
				if (f2 && f3 && f2 === f3) {
					frappe.msgprint('Second and Third Preferences cannot be the same.');
					wf.set_value('third_preference', '');
				}
			}

			wf.on('first_preference', validatePreferences);
			wf.on('second_preference', validatePreferences);
			wf.on('third_preference', validatePreferences);

			function validateNationality() {
				var nat = wf.get_value('nationality');
				var fn = wf.get_value('foriegn_national');

				if (fn === 'Yes' && nat === 'India') {
					// International candidate: Nationality cannot be India
					frappe.msgprint('For International applications, Nationality cannot be India.');
					wf.set_value('nationality', '');
				} else if (wf._slcmOnNationalityChangeForState) {
					// State list follows Nationality: drop a State that no longer belongs to it
					wf._slcmOnNationalityChangeForState();
				}
			}

			/*
			 * Freeze guard — previously this handler flipped foriegn_national on ANY refusal.
			 * Refusals like "window closed", "seats full", "programme not in cycle" apply to
			 * Yes and No alike, so the flip re-fired this handler, was refused again and flipped
			 * back — forever (endless server calls + stacked dialogs = frozen page). It also ran
			 * when a saved draft was opened, because loading values fires the change handler.
			 * Now: skip the value loaded from the saved draft, revert ONLY scope refusals, and
			 * never re-enter while reverting.
			 */
			var _slcmFnReverting = false;
			var _slcmFnLastChecked = isNewApplicantWebForm() ? null : (wf.doc && wf.doc.foriegn_national) || null;
			var _slcmFnLastMsg = '';

			function validateForeignNational() {
				validateNationality();
				_slcmToggleDegreeCountry(wf);
				if (_slcmFnReverting) return;

				var prog = wf.get_value('program');
				var fn = wf.get_value('foriegn_national');
				var nat = wf.get_value('nationality');
				if (!prog || !fn || fn === _slcmFnLastChecked) return;
				_slcmFnLastChecked = fn;

				frappe.call({
					method: 'slcm.admission.web_form.applicant_form.applicant_form.validate_new_application_access',
					args: {
						program: prog,
						foriegn_national: fn,
						nationality: nat || ''
					},
					callback: function (r) {
						var res = r && r.message;
						if (!res || res.allowed) {
							_slcmFnLastMsg = '';
							return;
						}
						// Same refusal twice in a row → don't stack identical dialogs
						if (res.message !== _slcmFnLastMsg) {
							_slcmFnLastMsg = res.message;
							frappe.msgprint({
								title: __('Access Restricted'),
								indicator: 'red',
								message: res.message
							});
						}
						// Only a Domestic/International mismatch is fixed by changing this field
						if (res.reason !== 'scope' || wf.get_value('foriegn_national') !== fn) return;
						var reverted = fn === 'Yes' ? 'No' : 'Yes';
						_slcmFnReverting = true;
						_slcmFnLastChecked = reverted;
						Promise.resolve()
							.then(function () { return wf.set_value('foriegn_national', reverted); })
							.catch(function () {})
							.then(function () { _slcmFnReverting = false; });
					}
				});
			}

			wf.on('nationality', validateNationality);
			// Note: wf.on() replaces any earlier handler for the field, so the country toggle
			// lives inside validateForeignNational rather than a second wf.on() registration.
			wf.on('foriegn_national', validateForeignNational);
			_slcmToggleDegreeCountry(wf);
			// Saved drafts load asynchronously — re-apply once their values are in
			setTimeout(function () { _slcmToggleDegreeCountry(wf); }, 1500);
			/*
			 * Freeze guard — hsc_percentage is numeric, so set_value('') stores 0 and fires this
			 * handler again: 0 < 35 → msgprint + clear → 0 → … an endless synchronous loop that
			 * froze the page behind a stuck dialog. It hit every saved draft with an empty HSC
			 * (stored as 0) as soon as the draft was reopened.
			 * 0 / empty now means "not entered", and our own clearing never re-validates.
			 */
			var _slcmHscClearing = false;

			function clearHscPercentage() {
				_slcmHscClearing = true;
				Promise.resolve()
					.then(function () { return wf.set_value('hsc_percentage', ''); })
					.catch(function () {})
					.then(function () { _slcmHscClearing = false; });
			}

			function validateHscPercentage() {
				if (_slcmHscClearing) return;
				var raw = wf.get_value('hsc_percentage');
				var hsc = parseFloat(raw);
				if (raw === '' || raw === null || raw === undefined || Number.isNaN(hsc) || hsc === 0) return;

				var cgpa_max = parseFloat(wf.get_value('if_cgpa_maximum_cgpa_class_xii'));
				var is_cgpa = (!Number.isNaN(cgpa_max) && cgpa_max > 0);
				var max_val = is_cgpa ? cgpa_max : 100;
				var min_val = is_cgpa ? 4 : 35;

				if (hsc < min_val) {
					frappe.msgprint(is_cgpa ? 'HSC CGPA must be at least 4.' : 'HSC percentage must be at least 35%.');
					clearHscPercentage();
				} else if (hsc > max_val) {
					frappe.msgprint(is_cgpa ? 'HSC CGPA cannot exceed ' + max_val + '.' : 'HSC percentage cannot exceed 100%.');
					clearHscPercentage();
				}
			}

			wf.on('hsc_percentage', validateHscPercentage);
			wf.on('if_cgpa_maximum_cgpa_class_xii', validateHscPercentage);
		}
		if (++n > 100) clearInterval(t);
	}, 200);
}


/** UG / PG degree "Country": shown AND mandatory only for foreign nationals (foriegn_national = Yes). */
function _slcmToggleDegreeCountry(wf) {
	if (!wf || !wf.fields_dict) return;
	var foreign = wf.get_value('foriegn_national') === 'Yes';
	['ug_degree_details', 'pg_degree_details'].forEach(function (ct) {
		var f = wf.fields_dict[ct];
		if (!f || !f.grid) return;
		try {
			f.grid.toggle_display('country', foreign);
			f.grid.toggle_reqd('country', foreign);
		} catch (e) {
			console.warn('Could not toggle country column on', ct, e);
		}
	});
}

// ───────────────────────────────────────────────────────────────────
//  UG / PG DEGREE TABLES — one default row, row click opens the
//  "Editing Row" form instead of column-by-column inline editing,
//  and closing that form keeps the page where it was.
// ───────────────────────────────────────────────────────────────────
var SLCM_DEGREE_TABLES = ['ug_degree_details', 'pg_degree_details'];

/**
 * Frappe's GridRow.hide_form() calls scroll_to(row). In this web form layout jQuery
 * offset() reports 0 at that moment, so the target goes negative and the page jumps to
 * the very top. Patched once on the shared GridRow prototype: keep the scroll position.
 */
function _slcmPatchGridRowScroll(gridRow) {
	var proto = gridRow && Object.getPrototypeOf(gridRow);
	if (!proto || proto._slcmScrollPatched || typeof proto.hide_form !== 'function') return;
	proto._slcmScrollPatched = true;
	var origHide = proto.hide_form;
	proto.hide_form = function () {
		var y = window.scrollY;
		var prev = frappe.flags.disable_auto_scroll;
		frappe.flags.disable_auto_scroll = true;
		try {
			return origHide.apply(this, arguments);
		} finally {
			frappe.flags.disable_auto_scroll = prev;
			var restore = function () {
				if (Math.abs(window.scrollY - y) > 2) window.scrollTo(0, y);
			};
			restore();
			requestAnimationFrame(restore);
			setTimeout(restore, 60);
		}
	};
}

/**
 * Degree-row "Country" is a Link → Country. Web forms turn child Link fields into Autocomplete
 * with options filtered to records the applicant OWNS (allow_read_on_all_link_options can't be
 * set on a child field), so the list came back empty. Load all countries once and feed them in.
 */
var _slcmCountryOptionsPromise = null;
function _slcmLoadCountryOptions() {
	if (!_slcmCountryOptionsPromise) {
		_slcmCountryOptionsPromise = new Promise(function (resolve) {
			frappe.call({
				method: 'frappe.client.get_list',
				args: { doctype: 'Country', fields: ['name'], order_by: 'name asc', limit_page_length: 0 },
				callback: function (r) {
					resolve(((r && r.message) || []).map(function (c) { return c.name; }));
				},
				error: function () {
					_slcmCountryOptionsPromise = null;   // allow a retry on the next check
					resolve([]);
				},
			});
		});
	}
	return _slcmCountryOptionsPromise;
}

function _slcmApplyDegreeCountryOptions(grid) {
	if (grid._slcmCountryOptionsDone || grid._slcmCountryOptionsLoading) return;
	grid._slcmCountryOptionsLoading = true;
	_slcmLoadCountryOptions().then(function (names) {
		grid._slcmCountryOptionsLoading = false;
		if (!names.length) return;
		grid._slcmCountryOptionsDone = true;
		var opts = names.join('\n');
		try { grid.update_docfield_property('country', 'options', opts); } catch (e) { console.warn('country options', e); }
		// A row panel that is already open keeps its own controls — update those too
		(grid.grid_rows || []).forEach(function (row) {
			var ctrl = row.grid_form && row.grid_form.fields_dict && row.grid_form.fields_dict.country;
			if (ctrl) {
				ctrl.df.options = opts;
				if (typeof ctrl.set_data === 'function') {
					try { ctrl.set_data(names); } catch (e) { /* refreshed on next open */ }
				}
			}
		});
	});
}

function _slcmSetupDegreeTable(wf, fieldname) {
	var field = wf.fields_dict && wf.fields_dict[fieldname];
	var grid = field && field.grid;
	if (!grid) return false;
	_slcmApplyDegreeCountryOptions(grid);

	if (!grid._slcmRowFormMode) {
		grid._slcmRowFormMode = true;
		// Instance-level only (meta stays editable_grid=1): a row click now falls through to
		// Frappe's own handler, which opens the row form; "Add row" also opens the new row.
		grid.allow_on_grid_editing = function () { return false; };
	}

	// One empty row by default — only while the table is shown for this programme level,
	// only once per page load (a row the applicant deletes is not re-added).
	var shown = !field.df.hidden && !field.df.hidden_due_to_dependency;
	wf._slcmDefaultDegreeRow = wf._slcmDefaultDegreeRow || {};
	if (shown && !wf._slcmDefaultDegreeRow[fieldname] && grid.is_editable()) {
		wf._slcmDefaultDegreeRow[fieldname] = true;
		if (!(grid.get_data() || []).length) {
			try { grid.add_new_row(null, null, false); } catch (e) { console.warn('default degree row', fieldname, e); }
		}
	}

	if (grid.grid_rows && grid.grid_rows.length) _slcmPatchGridRowScroll(grid.grid_rows[0]);
	return true;
}

/**
 * Close the open "Editing Row" panel when the applicant clicks outside it (on the dark
 * overlay or anywhere else on the page). Clicks inside popups that belong to the panel's
 * fields — date picker, link dropdowns, the attach/file-upload dialog, message dialogs —
 * live elsewhere in the DOM and must not count as "outside".
 */
function _slcmSetupRowFormOutsideClose() {
	if (window._slcmRowFormOutsideClose) return;
	window._slcmRowFormOutsideClose = true;

	// .grid-add-row / .grid-buttons: "Add row" opens the new row in its own click handler —
	// that same click must not immediately close it again.
	var KEEP_OPEN = '.grid-row-open, .grid-add-row, .grid-buttons, .datepicker, .awesomplete, .dropdown-menu, ' +
		'.modal, .modal-backdrop, .pcr-app, .select2-container, #slcm-toast';

	function isOutside(el) {
		return !!el && document.documentElement.contains(el) && !$(el).closest(KEEP_OPEN).length;
	}

	// Remember where the press started: selecting text inside the panel and releasing the
	// mouse outside it is not an "outside click".
	var pressStartedOutside = false;
	document.addEventListener('pointerdown', function (e) {
		pressStartedOutside = isOutside(e.target);
	}, true);

	document.addEventListener('click', function (e) {
		var $open = $('.web-form .grid-row-open');
		if (!$open.length) return;
		// Target removed by the click itself (e.g. a picked dropdown item) → not an outside click
		if (!pressStartedOutside || !isOutside(e.target)) return;

		$open.each(function () {
			var gridRow = $(this).data('grid_row');
			if (gridRow && typeof gridRow.toggle_view === 'function') gridRow.toggle_view(false);
		});
	});
}

/**
 * Frappe's Dialog closes any open grid row form when ANY dialog hides (dialog.js "hide.bs.modal"),
 * unless dialog.keep_grid_form_open is set. So finishing an upload in the Attach dialog — or
 * dismissing a validation message — inside the "Editing Row" panel closed the panel too.
 * Dialogs opened while a row panel is open now keep it open.
 */
function _slcmKeepRowFormOpenAcrossDialogs() {
	var Dialog = window.frappe && frappe.ui && frappe.ui.Dialog;
	if (!Dialog || !Dialog.prototype || Dialog.prototype._slcmKeepGridPatched) return !!(Dialog && Dialog.prototype && Dialog.prototype._slcmKeepGridPatched);
	Dialog.prototype._slcmKeepGridPatched = true;
	var origShow = Dialog.prototype.show;
	Dialog.prototype.show = function () {
		if (this._slcmKeepGridDefault === undefined) this._slcmKeepGridDefault = !!this.keep_grid_form_open;
		this.keep_grid_form_open = this._slcmKeepGridDefault || $('.web-form .grid-row-open').length > 0;
		return origShow.apply(this, arguments);
	};
	return true;
}

/** Next / Previous / stepper switch pages without scrolling — bring the new page into view from its top. */
function _slcmScrollTopOnPageChange(wf) {
	if (!wf || typeof wf.toggle_section !== 'function' || wf._slcmScrollTopPatched) return;
	wf._slcmScrollTopPatched = true;
	var origToggle = wf.toggle_section;
	var lastSection = wf.current_section;
	wf.toggle_section = function () {
		var out = origToggle.apply(this, arguments);
		if (this.current_section !== lastSection) {
			lastSection = this.current_section;
			window.scrollTo({ top: 0, behavior: 'smooth' });
		}
		return out;
	};
}

function setupDegreeTablesUX() {
	_slcmSetupRowFormOutsideClose();
	var _patchN = 0;
	var _patchT = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		_slcmScrollTopOnPageChange(wf);
		if ((_slcmKeepRowFormOpenAcrossDialogs() && wf && wf._slcmScrollTopPatched) || ++_patchN > 60) clearInterval(_patchT);
	}, 200);
	// Cheap visibility check: the tables appear/disappear with program_level (depends_on),
	// which can change at any time, so keep checking at a relaxed pace.
	setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		if (!wf || !wf.fields_dict) return;
		SLCM_DEGREE_TABLES.forEach(function (fn) { _slcmSetupDegreeTable(wf, fn); });
	}, 700);
}

/** A degree row is "blank" when the applicant has not typed anything into it. */
function _slcmIsBlankDegreeRow(row) {
	if (!row) return true;
	var META = { name: 1, idx: 1, doctype: 1, parent: 1, parentfield: 1, parenttype: 1, owner: 1,
		creation: 1, modified: 1, modified_by: 1, docstatus: 1 };
	return Object.keys(row).every(function (k) {
		if (META[k] || k.indexOf('__') === 0) return true;
		var v = row[k];
		return v === null || v === undefined || v === '' || v === 0;
	});
}

/** Get the current Applicant docname from wf.doc or URL */
function _slcmGetApplicantDocName() {
	var wf = window.frappe && frappe.web_form;
	var name = wf && wf.doc && wf.doc.name;
	if (!name) {
		var p = new URLSearchParams(window.location.search);
		name = p.get('name') || p.get('doc');
	}
	if (!name && window.location && window.location.pathname) {
		var path = String(window.location.pathname).replace(/\/$/, '');
		var m = path.match(/\/applicant-form\/([^/]+)(?:\/edit)?$/);
		if (m && m[1] && m[1] !== 'new' && m[1] !== 'list') {
			name = decodeURIComponent(m[1]);
		}
	}
	return name || null;
}

/**
 * Fetch declaration checkbox values DIRECTLY from the server and force them in the DOM.
 * Mirrors _paceRestoreCheckboxValues from PACE form.
 */
function _slcmRestoreApplicantCheckboxValues(wf) {
	var CHECK_FIELDS = [
		'authorisation_information',
		'agreement_to_communications',
		'agreement_withdrawal_conditions'
	];

	function _applyToDOM(data) {
		CHECK_FIELDS.forEach(function (fn) {
			if (data[fn] || data[fn] === 1 || data[fn] === true) {
				$('[data-fieldname="' + fn + '"] input[type="checkbox"]').each(function () {
					this.checked = true;
				});
				if (wf && wf.fields_dict && wf.fields_dict[fn]) {
					try { wf.fields_dict[fn].value = 1; } catch (e) {}
				}
				if (wf && wf.doc) {
					try { wf.doc[fn] = 1; } catch (e) {}
				}
			}
		});
	}

	// 1. Fast path from wf.doc (may be incomplete on first load)
	if (wf && wf.doc) {
		_applyToDOM(wf.doc);
	}

	// 2. Authoritative server fetch
	var docname = _slcmGetApplicantDocName();
	if (!docname || docname === 'new' || window._slcm_chk_fetched) return;
	window._slcm_chk_fetched = true;

	frappe.call({
		method: 'frappe.client.get_value',
		args: {
			doctype: 'Applicant',
			filters: { name: docname },
			fieldname: CHECK_FIELDS
		},
		callback: function (r) {
			if (!r || !r.message) return;
			var data = r.message;

			if (wf && wf.doc) {
				CHECK_FIELDS.forEach(function (fn) { wf.doc[fn] = data[fn] || 0; });
			}

			_applyToDOM(data);

			// Re-apply at staggered intervals to survive Frappe page re-renders
			setTimeout(function () { _applyToDOM(data); }, 300);
			setTimeout(function () { _applyToDOM(data); }, 800);
			setTimeout(function () { _applyToDOM(data); }, 1500);
			setTimeout(function () { _applyToDOM(data); }, 3000);

			// MutationObserver: re-apply whenever the declaration section appears in DOM
			// Critical for multi-page forms where checkboxes render only when page is shown
			if (!window._slcm_chk_observer) {
				// Other timers on this page toggle class/style several times a second, so batch
				// the work into one pass per animation frame instead of running per mutation.
				var _chkQueued = false;
				window._slcm_chk_observer = new MutationObserver(function () {
					if (_chkQueued) return;
					_chkQueued = true;
					requestAnimationFrame(function () {
						_chkQueued = false;
						CHECK_FIELDS.forEach(function (fn) {
							if (!data[fn]) return;
							var $chk = $('[data-fieldname="' + fn + '"] input[type="checkbox"]');
							$chk.each(function () {
								if (!this.checked) this.checked = true;
							});
						});
					});
				});
				window._slcm_chk_observer.observe(
					document.querySelector('.web-form') || document.body,
					{ childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style'] }
				);
			}
		}
	});
}

function setupApplicantCheckboxRenderFix() {
	// Wait for wf to be ready, then use server-fetch restore (mirrors paceSetupDeclarationRenderFix)
	var n = 0;
	var t = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields_dict) {
			clearInterval(t);
			_slcmRestoreApplicantCheckboxValues(wf);
		}
		if (++n > 100) clearInterval(t);
	}, 200);
}

//  BOOTSTRAP
// ───────────────────────────────────────────────────────────────────
frappe.ready(function () {
	setupApplicantCheckboxRenderFix(); // schedules itself via after_load + timeout
	makeInputUppercase();
	setupPreferenceValidation();
	_injectCSS();
	_injectAdmissionShell();
	setupSlcmFieldErrorClear();
	setupSlcmWebFormAwesompletePositionFix();

	// ── FIX: Hydrate Phone fields in Edit mode (Draft) if missing ────────
	var wf = window.frappe && frappe.web_form;
	if (wf && wf.doc) {
		setTimeout(function () {
			var PHONE_FIELDS = ['mobile_number', 'alternate_contact', 'father_mobile', 'mother_mobile', 'guardian_mobile'];
			PHONE_FIELDS.forEach(function (fn) {
				var val = wf.doc[fn];
				var field = wf.fields_dict && wf.fields_dict[fn];
				if (val && field) {
					if (typeof field.set_formatted_input === 'function') {
						field.set_formatted_input(val);
					} else if (typeof field.set_value === 'function') {
						field.set_value(val);
					}
					// Fallback if input is still empty
					if (field.$input && !field.$input.val()) {
						var parts = String(val).split('-');
						var num = parts.length > 1 ? parts.slice(1).join('-') : val;
						field.$input.val(num);
					}
				}
			});
		}, 800);
	}

	try {
		$('#eligibility-alert-box').remove();
	} catch (e) {}

	// Fee (silent)
	bindFeeListener();
	setTimeout(updateFeeForCategory, 600);

	// Program → program_level (and related) when user edits Program or Admission Cycle
	var _bindProgN = 0;
	var _bindProgTimer = setInterval(function () {
		_bindProgN++;
		var wf = window.frappe && frappe.web_form;
		if (wf && typeof wf.on === 'function') {
			clearInterval(_bindProgTimer);
			try {
				wf.on('program', function () {
					syncTopBarApplyingFor();
					scheduleProgramPortalDerivatives();
				});
				wf.on('admission_cycle', scheduleProgramPortalDerivatives);
			} catch (e) {}
		} else if (_bindProgN > 120) {
			clearInterval(_bindProgTimer);
		}
	}, 80);

	applyQueryStringPrefill();

	// Status badge
	setupStatusBadge();
	slcmSetupPayButton();

	// Save Draft button (re-polls on every step change)
	setupSaveDraftButton();
	setupHideRedundantWebFormEdit();

	setupApplicationFeeReceiptDownload();
	if (window.frappe && frappe.web_form && frappe.web_form.events && frappe.web_form.events.on) {
		try {
			frappe.web_form.events.on('after_load', function () {
				_ensureTopBar();
				scheduleProgramPortalDerivatives();
				updateStatusBadge(resolveField('status'));
			});
		} catch (e) {}
	}
	setupSubmittedFormUX();
	setupCandidatePhotoPreview();
	setupDegreeTablesUX();
	setupAttachFieldValidation();
	setupSlcmForcePublicUploads();
	setupNumericFieldRestriction();
	setupApplicantFieldBoundaries();
	setupPhoneValidation();
	setupWebFormDateInputSanitize();
	
	// Submit intercept (retry: web form may attach after this script's first frappe.ready)
	interceptSubmit();
	var _patchAttempts = 0;
	var _patchTimer = setInterval(function () {
		interceptSubmit();
		if ((frappe.web_form && frappe.web_form._slcm_save_patched) || ++_patchAttempts > 60) {
			clearInterval(_patchTimer);
		}
	}, 150);
	// Stepper / Stages
	setupStepper();
	setupDateOfBirthWebForm();
	scheduleApplicantCountryStateCityFilter();

	// Frappe Next: validate_section ignores Attach (no .form-control) — patch after web_form exists
	var _attachSecPatchN = 0;
	var _attachSecTimer = setInterval(function () {
		patchWebFormValidateSectionForAttach();
		if ((frappe.web_form && frappe.web_form._slcmValidateSectionAttachPatched) || ++_attachSecPatchN > 100) {
			clearInterval(_attachSecTimer);
		}
	}, 100);

	var _zeroHookN = 0;
	var _zeroHookTimer = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.events && wf.events.on && !wf._slcmZeroNumericAfterLoad) {
			wf._slcmZeroNumericAfterLoad = true;
			wf.events.on('after_load', function () {
				setTimeout(slcmClearDefaultZeroNumericFields, 0);
				setTimeout(slcmClearDefaultZeroNumericFields, 500);
			});
			clearInterval(_zeroHookTimer);
		} else if (++_zeroHookN > 120) {
			clearInterval(_zeroHookTimer);
		}
	}, 100);

	var _zeroPollN = 0;
	var _zeroPollTimer = setInterval(function () {
		slcmClearDefaultZeroNumericFields();
		if (++_zeroPollN > 40) clearInterval(_zeroPollTimer);
	}, 250);

	setTimeout(function () {
		// Only real field wrappers — inputs/buttons also carry data-fieldname and must not get a prepended label
		document.querySelectorAll('.frappe-control[data-fieldname]').forEach(function (field) {
			var fieldname = field.getAttribute('data-fieldname');
			var fieldtype = field.getAttribute('data-fieldtype');
			if (!fieldtype || !['Attach', 'Attach Image'].includes(fieldtype)) return;
			/* Layout + label order handled in CSS / syncCandidatePhotoPreview; never inject here */
			if (fieldname === 'candidate_photo') return;
			if (field.querySelector('.control-label')) return;
			var df = frappe.web_form.fields_dict[fieldname] && frappe.web_form.fields_dict[fieldname].df;
			var labelText = (df && df.label) || fieldname;
			var lbl = document.createElement('label');
			lbl.className = 'control-label';
			lbl.textContent = labelText;
			field.prepend(lbl);
		});
	}, 500);
});

/**
 * setupStepper — Creates and manages the multi-step navigation bar.
 * Labels are derived dynamically from Page Break fields in frappe.web_form
 * (which mirror the Tab Break fields defined in the Applicant DocType).
 *
 * Stage index comes from frappe.web_form.current_section (Frappe multi-step).
 * DOM uses .form-page / .page-break — not .web-form-page.
 */
function setupStepper() {
	if ($('#slcm-stepper-wrap').length) return;

	let _attempts = 0;
	const _timer = setInterval(function () {
		const wf = window.frappe && frappe.web_form;

		if (wf && wf.fields && wf.fields.length) {
			clearInterval(_timer);
			_renderStepper(wf);
		} else if (++_attempts > 120) {
			clearInterval(_timer);
		}
	}, 100);
}

function _renderStepper(wf) {
	// ── 1. Build step list from Page Break fields (= Applicant DocType Tab Breaks) ──
	// The very first page never has a Page Break; it's always "Personal Information".
	const steps = [{ label: 'Personal Information', index: 0, depends_on: null }];

	(wf.fields || []).forEach(function (f) {
		if (f.fieldtype === 'Page Break' && f.label) {
			steps.push({ label: f.label, index: steps.length, depends_on: f.depends_on || null });
		}
	});

	window._slcm_wf_steps = steps;

	// ── 2. Build stepper HTML (flex: pill | growing line | pill | …) ───────
	var flexInline = 'display:flex;width:max-content;min-width:100%;box-sizing:border-box;align-items:center;column-gap:0;row-gap:10px;';
	let html = '<div id="slcm-stepper-wrap"><div class="slcm-stepper" style="' + flexInline + '">';
	steps.forEach(function (step, i) {
		var lbl = step.label || '';
		var safeTitle = lbl.replace(/"/g, '&quot;').replace(/</g, '&lt;');
		html +=
			'<div class="slcm-step" data-index="' +
			i +
			'" title="' +
			safeTitle +
			'">' +
			'<div class="slcm-step-circle">' +
			(i + 1) +
			'</div>' +
			'<div class="slcm-step-label">' +
			_esc(lbl) +
			'</div>' +
			'</div>';
		if (i < steps.length - 1) {
			html += '<div class="slcm-step-connector" data-connector-index="' + i + '" aria-hidden="true" style="flex:1 1 12px;"></div>';
		}
	});
	html += '</div></div>';

	// ── 3. Find injection target ───────────────────────────────────────────
	// Try: after #slcm-form-topbar → after .web-form-header → before .web-form-body
	if ($('#slcm-form-topbar').length) {
		$('#slcm-form-topbar').after(html);
	} else if ($('.web-form-header').length) {
		$('.web-form-header').after(html);
	} else if ($('.web-form-body').length) {
		$('.web-form-body').before(html);
	} else {
		$('.web-form-container, .page-content').first().prepend(html);
	}

	// ── 4. Current stage index (must match Frappe WebForm.current_section) ─
	function getCurrentPageIdx() {
		const w = window.frappe && frappe.web_form;
		if (w && typeof w.current_section === 'number' && !Number.isNaN(w.current_section)) {
			return Math.max(0, w.current_section);
		}
		const $pages = $('.web-form .form-layout > .form-page');
		if (!$pages.length) return 0;
		let curr = 0;
		$pages.each(function (i) {
			if ($(this).is(':visible')) curr = i;
		});
		return curr;
	}

	function goToWebFormPage(targetIdx) {
		const w = window.frappe && frappe.web_form;
		if (!w || typeof w.toggle_section !== 'function') return;
		const max = (w.page_breaks && w.page_breaks.length) || 0;
		const last = max; // sections 0..page_breaks.length
		const idx = Math.max(0, Math.min(targetIdx, last));
		w.current_section = idx;
		w.toggle_section();
	}

	// ── 5. Update stepper visual state ────────────────────────────────────
	function slcmEvalDependsOn(condition) {
		if (!condition) return true;
		const doc = window.frappe && frappe.web_form && frappe.web_form.doc;
		if (!doc) return true;
		if (condition.startsWith('eval:')) {
			try {
				return !!eval(condition.substr(5));
			} catch (e) {
				return false;
			}
		}
		return !!doc[condition];
	}

	function updateStepperUI() {
		const curr = getCurrentPageIdx();
		const $wrap = $('#slcm-stepper-wrap');
		const draft = typeof slcmApplicationIsDraft === 'function' && slcmApplicationIsDraft();

		const stepsArr = window._slcm_wf_steps || [];
		let visibleIndices = [];
		stepsArr.forEach(function(s) {
			if (slcmEvalDependsOn(s.depends_on)) {
				visibleIndices.push(s.index);
			}
		});

		let visualIndex = 1;

		if (draft) {
			$wrap.removeClass('slcm-stepper-post-draft');
		} else {
			$wrap.addClass('slcm-stepper-post-draft');
		}

		$('.slcm-step').each(function () {
			const $step = $(this);
			const idx = parseInt($step.attr('data-index'), 10);
			const isVisible = visibleIndices.includes(idx);

			if (!isVisible) {
				$step.hide();
				$('.slcm-step-connector[data-connector-index="' + idx + '"]').hide();
			} else {
				$step.show();
				$step.find('.slcm-step-circle').text(visualIndex++);

				const isLastVisible = (idx === visibleIndices[visibleIndices.length - 1]);
				if (!isLastVisible) {
					$('.slcm-step-connector[data-connector-index="' + idx + '"]').show();
				} else {
					$('.slcm-step-connector[data-connector-index="' + idx + '"]').hide();
				}

				$step.removeClass('active completed');
				if (draft) {
					if (idx === curr) $step.addClass('active');
					else if (idx < curr) $step.addClass('completed');
				} else {
					$step.addClass('completed');
					if (idx === curr) $step.addClass('active');
				}
			}
		});
	}

	// Initial render + keep in sync (Next/Previous updates current_section)
	updateStepperUI();
	var _stepperSync = setInterval(updateStepperUI, 280);
	$(window).on('beforeunload', function () {
		clearInterval(_stepperSync);
	});

	// Sync after Frappe's own Next / Previous button clicks
	$(document).on('click', '.btn-next, .btn-previous', function () {
		setTimeout(updateStepperUI, 50);
		setTimeout(updateStepperUI, 200);
	});

	// ── 6. Click handler on stepper tabs ──────────────────────────────────
	$('#slcm-stepper-wrap').on('click', '.slcm-step', function () {
		const targetIdx = parseInt($(this).attr('data-index'), 10);
		const currentIdx = getCurrentPageIdx();
		const $pages = $('.web-form .form-layout > .form-page');

		if (!$pages.length) return;

		if (targetIdx === currentIdx) return;

		if (targetIdx > currentIdx) {
			const skip = _slcmStepperSkipForwardValidation(wf);
			const check = skip ? { ok: true, missing: [] } : _validateStage(wf, $($pages.get(currentIdx)));
			if (check.ok) {
				goToWebFormPage(targetIdx);
				setTimeout(updateStepperUI, 50);
			} else {
				var base = __('Please fill all required fields before proceeding.');
				if (check.missing && check.missing.length && typeof frappe !== 'undefined' && frappe.msgprint) {
					frappe.msgprint({
						title: __('Required fields'),
						message:
							_esc(base) +
							'<br><br><ul><li>' +
							check.missing
								.map(function (lab) {
									return _esc(lab);
								})
								.join('</li><li>') +
							'</li></ul>',
						indicator: 'red',
					});
				} else {
					showToast(base, 'error', 6500);
				}
			}
		} else {
			goToWebFormPage(targetIdx);
			setTimeout(updateStepperUI, 50);
		}
	});
}


/**
 * Stepper tab forward jump: skip our client validation when the user cannot edit
 * (view mode / submitted-locked) or when the web form allows incomplete saves.
 * Otherwise read-only/disabled fields often fail get_value() and falsely block jumps.
 */
function _slcmStepperSkipForwardValidation(wf) {
	if (!wf) return true;
	if (wf.allow_incomplete) return true;
	if (wf.in_view_mode) return true;
	if (typeof slcmApplicationPortalLocked === 'function' && slcmApplicationPortalLocked()) return true;
	return false;
}

/**
 * Frappe WebForm.validate_section() only walks `.form-control`; Attach / Attach Image use
 * `.btn-attach` and are skipped. Collect required attach fields on the active section.
 */
function _slcmPageContainsFieldname($page, fieldname) {
	if (!$page || !$page.length || !fieldname) return false;
	var hit = false;
	$page.find('[data-fieldname]').each(function () {
		if (($(this).attr('data-fieldname') || '') === fieldname) {
			hit = true;
			return false;
		}
	});
	return hit;
}

function _slcmWebFormAttachValueEmpty(val) {
	if (val === undefined || val === null) return true;
	if (typeof val === 'string' && !String(val).trim()) return true;
	return false;
}

function _slcmCollectEmptyRequiredAttachOnPage(wf) {
	if (!wf || wf.allow_incomplete) return [];
	var $page = $(wf.get_page(wf.current_section));
	if (!$page.length) return [];

	var out = [];
	for (var fieldname in wf.fields_dict) {
		if (!Object.prototype.hasOwnProperty.call(wf.fields_dict, fieldname)) continue;
		var field = wf.fields_dict[fieldname];
		var df = field && field.df;
		if (!df) continue;
		if (!df.reqd) continue;
		if (df.fieldtype !== 'Attach' && df.fieldtype !== 'Attach Image') continue;
		if (df.read_only) continue;
		if (field.$wrapper && field.$wrapper.length && field.$wrapper.is(':hidden')) continue;
		if (!_slcmPageContainsFieldname($page, fieldname)) continue;
		var value = field.get_value ? field.get_value() : null;
		if (!_slcmWebFormAttachValueEmpty(value)) continue;
		out.push({ field: field, label: (df.label || fieldname).trim() || fieldname });
	}
	return out;
}

function _slcmHighlightRequiredAttachFields(missing, on) {
	missing.forEach(function (m) {
		var $w = m.field && m.field.$wrapper;
		if (!$w || !$w.length) return;
		var sel =
			'.form-control, .attached-file, .input-with-feedback, .btn-attach, .control-value';
		if (on) {
			$w.find(sel).addClass('slcm-field-error');
		} else {
			$w.find(sel).removeClass('slcm-field-error');
		}
	});
}

/** Unchecked required Check: Frappe is_null(0) is false, so core get_values misses these. */
function _slcmCheckValueUnchecked(val) {
	if (val === '0' || val === 0 || val === false || val === '' || val === null || val === undefined) return true;
	return false;
}

function _slcmCollectEmptyRequiredCheckOnPage(wf) {
	if (!wf || wf.allow_incomplete) return [];
	var $page = $(wf.get_page(wf.current_section));
	if (!$page.length) return [];

	var out = [];
	for (var fieldname in wf.fields_dict) {
		if (!Object.prototype.hasOwnProperty.call(wf.fields_dict, fieldname)) continue;
		var field = wf.fields_dict[fieldname];
		var df = field && field.df;
		if (!df) continue;
		if (!df.reqd || df.fieldtype !== 'Check') continue;
		if (df.read_only) continue;
		if (field.$wrapper && field.$wrapper.length && field.$wrapper.is(':hidden')) continue;
		if (!_slcmPageContainsFieldname($page, fieldname)) continue;
		var value = field.get_value ? field.get_value() : 0;
		if (!_slcmCheckValueUnchecked(value)) continue;
		out.push({ field: field, label: (df.label || fieldname).trim() || fieldname });
	}
	return out;
}

function _slcmCollectAllEmptyRequiredChecks(wf) {
	if (!wf || wf.allow_incomplete) return [];
	var out = [];
	for (var fieldname in wf.fields_dict) {
		if (!Object.prototype.hasOwnProperty.call(wf.fields_dict, fieldname)) continue;
		var field = wf.fields_dict[fieldname];
		var df = field && field.df;
		if (!df) continue;
		if (!df.reqd || df.fieldtype !== 'Check') continue;
		if (df.read_only) continue;
		if (field.$wrapper && field.$wrapper.length && field.$wrapper.is(':hidden')) continue;
		var value = field.get_value ? field.get_value() : 0;
		if (!_slcmCheckValueUnchecked(value)) continue;
		out.push({ field: field, label: (df.label || fieldname).trim() || fieldname });
	}
	return out;
}

function _slcmHighlightRequiredCheckFields(missing, on) {
	missing.forEach(function (m) {
		var $w = m.field && m.field.$wrapper;
		if (!$w || !$w.length) return;
		var $cb = $w.find('input[type="checkbox"]');
		var $box = $w.find('.checkbox').first();
		if (on) {
			$cb.addClass('slcm-field-error');
			$box.addClass('slcm-field-error');
		} else {
			$cb.removeClass('slcm-field-error');
			$box.removeClass('slcm-field-error');
		}
	});
}

/**
 * Replace WebForm.validate_section: core only walks .form-control, so Attach / Attach Image
 * and required Check boxes are skipped. Use _validateStage (same rules as stepper) plus df.invalid.
 */
function patchWebFormValidateSectionForAttach() {
	var wf = window.frappe && frappe.web_form;
	if (!wf || typeof wf.validate_section !== 'function' || wf._slcmValidateSectionAttachPatched) {
		return;
	}
	wf._slcmValidateSectionAttachPatched = true;
	wf.validate_section = function () {
		if (this.allow_incomplete) return true;

		var me = this;
		var $page = $(me.get_page(me.current_section));
		var invalid_values = [];
		$page.find('.form-control').each(function () {
			var fieldname = $(this).attr('data-fieldname');
			if (!fieldname) return;
			var field = me.fields_dict[fieldname];
			if (field && field.df && field.df.invalid) {
				invalid_values.push(__(field.df.label));
			}
		});

		var stage = _validateStage(me, $page);

		var message = '';
		if (invalid_values.length) {
			message +=
				__('Invalid values for fields:', null, 'Error message in web form') +
				'<br><br><ul><li>' +
				invalid_values
					.map(function (lab) {
						return _esc(lab);
					})
					.join('</li><li>') +
				'</li></ul>';
		}
		if (!stage.ok && stage.missing && stage.missing.length) {
			message +=
				__('Mandatory fields required:', null, 'Error message in web form') +
				'<br><br><ul><li>' +
				stage.missing
					.map(function (lab) {
						return _esc(lab);
					})
					.join('</li><li>') +
				'</li></ul>';
		}

		if (invalid_values.length || !stage.ok) {
			frappe.msgprint({
				title: __('Error', null, 'Title of the error message in web form'),
				message: message,
				indicator: 'orange',
			});
			return false;
		}
		return true;
	};
}

/**
 * Layout fieldtypes never store a value; reqd on them in Web Form JSON is a misconfiguration.
 */
function _slcmWebFormLayoutFieldtype(ft) {
	if (!ft) return false;
	var layout = {
		'Section Break': 1,
		'Column Break': 1,
		'Page Break': 1,
		'Tab Break': 1,
		HTML: 1,
		Fold: 1,
		Heading: 1,
		Button: 1,
	};
	return !!layout[ft];
}

/**
 * _validateStage — required (and conditionally required) fields on one page.
 * Returns an object with ok (boolean) and missing (string[]). This file is Jinja-rendered by Frappe Web Form — never use literal double-open-brace sequences in source.
 */
/** Foreign nationals: every filled UG / PG degree row on this page needs a Country. */
function _slcmValidateDegreeCountryOnPage(wf, $page, missing) {
	if (wf.get_value('foriegn_national') !== 'Yes') return;
	SLCM_DEGREE_TABLES.forEach(function (ct) {
		var fw = wf.fields_dict[ct];
		if (!fw || !fw.df || fw.df.hidden || fw.df.hidden_due_to_dependency) return;
		if (!$page.find('[data-fieldname="' + ct + '"]').length) return;
		(wf.get_value(ct) || []).forEach(function (row, i) {
			if (_slcmIsBlankDegreeRow(row)) return;
			if (!((row.country || '') + '').trim()) {
				missing.push(__('{0} — Row {1}: Country', [(fw.df.label || ct).trim(), row.idx || i + 1]));
			}
		});
	});
}

function _validateStage(wf, $page) {
	const missing = [];
	const seen = new Set();

	$page.find('[data-fieldname]').each(function () {
		const fieldname = $(this).attr('data-fieldname');
		if (!fieldname || seen.has(fieldname)) return;
		seen.add(fieldname);

		const fw = wf.fields_dict[fieldname];
		if (!fw) return;

		const df = fw.df;
		if (_slcmWebFormLayoutFieldtype(df.fieldtype)) return;

		let required = df.reqd;

		if (!required && df.mandatory_depends_on) {
			try {
				const expr = df.mandatory_depends_on.replace(/^eval:/, '');
				// eslint-disable-next-line no-new-func
				required = !!(new Function('doc', 'return (' + expr + ')')(wf.doc));
			} catch (e) { /* ignore eval errors */ }
		}

		if (!required) return;

		if (fw.$wrapper && fw.$wrapper.is(':hidden')) return;

		let val = wf.get_value(fieldname);
		if (df.fieldtype === 'Text Editor' && typeof val === 'string' && frappe.utils && frappe.utils.strip_html) {
			val = frappe.utils.strip_html(val);
		}
		let empty;
		if (df.fieldtype === 'Check') {
			empty = _slcmCheckValueUnchecked(val);
		} else if (df.fieldtype === 'Attach' || df.fieldtype === 'Attach Image') {
			empty = _slcmWebFormAttachValueEmpty(val);
		} else if (df.fieldtype === 'Phone') {
			var sVal = String(val || '').trim();
			empty = !sVal || (sVal.indexOf('-') > -1 && !sVal.split('-').slice(1).join('').trim());
		} else if (df.fieldtype === 'Table' && SLCM_DEGREE_TABLES.indexOf(fieldname) !== -1) {
			// The default (untouched) degree row must not satisfy "table is mandatory"
			empty = !(Array.isArray(val) && val.some(function (r) { return !_slcmIsBlankDegreeRow(r); }));
		} else {
			empty =
				val === undefined ||
				val === null ||
				val === '' ||
				(Array.isArray(val) && val.length === 0);
		}

		var errSel =
			'.form-control, .attached-file, .input-with-feedback, .btn-attach, .control-value, input[type="checkbox"], .checkbox';
		if (fieldname === 'date_of_birth' && !empty && df.fieldtype === 'Date') {
			const age = _slcmAgeCompletedYears(val);
			if (age === null || age < 17) {
				fw.$wrapper && fw.$wrapper.find(errSel).addClass('slcm-field-error');
				missing.push((df.label || fieldname).trim() + ': ' + __('must be at least 17 years old'));
				return;
			}
		}

		if (empty) {
			fw.$wrapper && fw.$wrapper.find(errSel).addClass('slcm-field-error');
			missing.push((df.label || fieldname).trim() || fieldname);
		} else {
			fw.$wrapper && fw.$wrapper.find(errSel).removeClass('slcm-field-error');
		}
	});

	_slcmValidateApplicantFormatsOnPage(wf, $page, missing);
	_slcmValidateDegreeCountryOnPage(wf, $page, missing);

	return { ok: missing.length === 0, missing };
}

/** Country → State (India: rows where State.country = India; otherwise only State "Other") → City (City.state + City.country per masterdata) */
function setupCityStateFilter() {
	var wf = window.frappe && frappe.web_form;
	if (!wf || !wf.fields_dict) return false;
	if (!wf.fields_dict.country || !wf.fields_dict.state || !wf.fields_dict.city) return false;
	if (wf._slcmApplicantAddrWired) return true;
	wf._slcmApplicantAddrWired = true;

	// State list follows the applicant's Nationality (falls back to the hidden address country, then India)
	function effCountry() {
		var raw = wf.get_value('nationality') || wf.get_value('country');
		return ((raw || '') + '').trim() || 'India';
	}

	function patchBlock(countryFld, stateFld, cityDataFld) {
		var sf = wf.get_field && wf.get_field(stateFld);
		var cf = wf.get_field && wf.get_field(cityDataFld);
		if (!sf) return false;

		// Not for State: Applicant.state does not allow ignoring user permissions, so search_link
		// rejects every State search (empty dropdown) when this flag is sent
		[countryFld].forEach(function (fn) {
			var fld = wf.get_field(fn);
			if (fld && fld.df) fld.df.ignore_user_permissions = 1;
		});

		function stateQueryFn() {
			var eff = effCountry();
			return {
				query: 'slcm.admission.web_form.applicant_form.applicant_form.state_query',
				filters: { country: eff },
				// Web forms render Link fields as Autocomplete, which only sends `params` to the query
				params: { country: eff }
			};
		}

		function cityQueryFn() {
			var st = wf.get_value(stateFld);
			return {
				query: 'slcm.admission.web_form.applicant_form.applicant_form.city_query',
				filters: { state: st || '' }
			};
		}

		// Clears the State (and City) when it does not belong to the Nationality country
		function checkStateMatchesCountry(stateVal) {
			var eff = effCountry();
			frappe.call({
				method: 'slcm.admission.web_form.applicant_form.applicant_form.state_belongs_to_country',
				args: { state: stateVal, country: eff },
				callback: function (r) {
					if (!r || r.message !== false) return;
					if ((wf.get_value(stateFld) || '').trim() !== stateVal) return; // changed meanwhile
					frappe.msgprint("The selected State '" + stateVal + "' does not belong to '" + eff + "'.");
					wf._is_syncing_address = true;
					wf.set_value(stateFld, '');
					wf.set_value(cityDataFld, '');
					setTimeout(function() { wf._is_syncing_address = false; }, 200);
				}
			});
		}

		// Called from validateNationality (wf.on would replace that handler). Only reacts when the
		// user changes Nationality, so values loading into a saved draft are never cleared.
		wf._slcmOnNationalityChangeForState = function () {
			var natFld = wf.fields_dict.nationality;
			var natInput = natFld && natFld.$input && natFld.$input[0];
			if (!natInput || document.activeElement !== natInput) return;
			// The link control shows cached results first; drop the previous country's list
			if (sf.$input) sf.$input.cache = {};
			var st = (wf.get_value(stateFld) || '').trim();
			if (st && st.toLowerCase() !== 'other') checkStateMatchesCountry(st);
		};

		if (wf.set_query) {
			wf.set_query(stateFld, stateQueryFn);
			wf.set_query(cityDataFld, cityQueryFn);
		}
		if (wf.set_df_property) {
			try { wf.set_df_property(stateFld, 'get_query', stateQueryFn); } catch (e) {}
			try { wf.set_df_property(cityDataFld, 'get_query', cityQueryFn); } catch (e) {}
		}
		if (sf) {
			if (sf.df) sf.df.get_query = stateQueryFn;
			sf.get_query = stateQueryFn;
			// Drop any unfiltered results cached before the query was attached
			if (sf.$input) sf.$input.cache = {};
		}
		if (cf) {
			if (cf.df) cf.df.get_query = cityQueryFn;
			cf.get_query = cityQueryFn;
		}

		var lastCountry = wf.get_value(countryFld);
		var lastState = wf.get_value(stateFld);

		wf.on(countryFld, function () {
			if (wf._is_syncing_address) return;
			var currentCountry = (wf.get_value(countryFld) || '').trim();
			var prevCountry = (lastCountry || '').trim();

			if (!prevCountry && currentCountry) {
				lastCountry = currentCountry;
				return;
			}
			if (prevCountry && currentCountry && prevCountry.toLowerCase() === currentCountry.toLowerCase()) return;
			lastCountry = currentCountry;

			// Country genuinely changed: clear state and the opposite city field
			if (prevCountry && currentCountry && prevCountry.toLowerCase() !== currentCountry.toLowerCase()) {
				wf.set_value(stateFld, '');
				if (currentCountry.toLowerCase() === 'india') {
					wf.set_value('foreigin_city', '');
				} else {
					wf.set_value(cityDataFld, '');
				}
			}
		});

		wf.on(stateFld, function () {
			if (wf._is_syncing_address) return;
			var currentCountry = (wf.get_value(countryFld) || '').trim();
			var currentState = (wf.get_value(stateFld) || '').trim();
			var prevState = (lastState || '').trim();

			if (!prevState && currentState) {
				lastState = currentState;
				return;
			}
			if (prevState && currentState && prevState.toLowerCase() === currentState.toLowerCase()) return;
			lastState = currentState;

			if (!currentState) {
				wf.set_value(cityDataFld, '');
				return;
			}

			// Validate state belongs to the Nationality country ('Other' is always allowed)
			if (currentState.toLowerCase() !== 'other') {
				checkStateMatchesCountry(currentState);
			}

			// Only check/clear city if user genuinely changed from one state to a different state
			if (prevState && currentState && prevState.toLowerCase() !== currentState.toLowerCase()) {
				var currentCity = (wf.get_value(cityDataFld) || '').trim();
				if (currentCity && currentCity.toLowerCase() !== 'other') {
					frappe.call({
						method: 'frappe.client.get_value',
						args: {
							doctype: 'City',
							filters: { name: currentCity },
							fieldname: ['state']
						},
						callback: function(r) {
							if (r.message && r.message.state) {
								var cityState = (r.message.state || '').trim();
								if (cityState && cityState.toLowerCase() !== 'other' && cityState.toLowerCase() !== currentState.toLowerCase()) {
									wf.set_value(cityDataFld, '');
								}
							}
						}
					});
				}
			}
		});

		// Focus show all trick for city
		var cityField = wf.fields_dict.city;
		if (cityField) {
			var $inp = $(cityField.input || cityField.$input);
			if ($inp.length) {
				$inp.off('focus.slcmCity').on('focus.slcmCity', function () {
					var stateVal = wf.get_value('state');
					if (!stateVal) return;
					var currentVal = $inp.val();
					if (!currentVal) {
						$inp.val('');
						$inp.trigger('input');
					}
				});

				$(document).off('awesomplete-open.slcmCity').on('awesomplete-open.slcmCity',
					'[data-fieldname="city"] input',
					function () {
						var $ul = $(this).closest('.awesomplete').find('ul');
						if ($ul.length) {
							$ul.css({
								width: $(this).outerWidth() + 'px',
								minWidth: '0',
								maxWidth: '100%',
								boxSizing: 'border-box'
							});
						}
					}
				);
			}
		}

		// ── Validate city belongs to selected state on awesomplete selection ──
		$(document).off('awesomplete-selectcomplete.slcmCityValidate')
			.on('awesomplete-selectcomplete.slcmCityValidate', '[data-fieldname="' + cityDataFld + '"] input', function () {
				var selectedCity = ($(this).val() || '').trim();
				var currentState = (wf.get_value(stateFld) || '').trim();
				var currentCountry = (wf.get_value(countryFld) || '').trim();
				if (!selectedCity || !currentState) return;
				if (currentCountry && currentCountry.toLowerCase() !== 'india') return; // non-India: uses foreigin_city
				if (selectedCity.toLowerCase() === 'other') return; // 'Other' is always valid

				frappe.call({
					method: 'frappe.client.get_value',
					args: {
						doctype: 'City',
						filters: { name: selectedCity },
						fieldname: ['state', 'country']
					},
					callback: function (r) {
						if (!r.message) return;
						var cityState = (r.message.state || '').trim();
						if (cityState && cityState.toLowerCase() === 'other') return;
						if (cityState && cityState.toLowerCase() !== currentState.toLowerCase()) {
							showToast(
								'\u26a0 "' + selectedCity + '" belongs to ' + cityState +
								', not ' + currentState + '. Please select a city from ' + currentState + '.',
								'error'
							);
							wf.set_value(cityDataFld, '');
						}
					}
				});
			});

		return true;
	}

	return patchBlock('country', 'state', 'city');
}

function scheduleApplicantCountryStateCityFilter() {
	function tryWire() {
		return !!setupCityStateFilter();
	}
	tryWire();
	setTimeout(tryWire, 0);
	var _retries = 0;
	var _t = setInterval(function () {
		if (tryWire() || ++_retries > 80) clearInterval(_t);
	}, 125);
}




function slcmSetupPayButton() {
	setInterval(function () {
		if (document.getElementById('slcm-pay-btn')) return;
		var status = (resolveField('status') || '').trim().toLowerCase();
		if (status === 'draft' || status === 'new' || !status) return;
		
		var feeStatus = resolveApplicationFeeStatus();
		if (feeStatus === 'Paid' || feeStatus === 'Waived') return;
		if (document.getElementById('slcm-fee-receipt-btn')) return;

		var $topbar = $('#slcm-form-topbar');
		if ($topbar.length) {
			var btn = $('<button id="slcm-pay-btn" class="slcm-btn-pay" style="padding: 7px 14px; font-size: 13px; margin-left: auto; background: var(--slcm-primary, #1a3c6e); color: #fff; border: none; border-radius: 4px; cursor: pointer;">Pay Application Fee</button>');
			btn.on('click', function () {
				var applicantName = getDocName();
				if (!applicantName) return;
				
				var payBtnDom = btn.get(0);
				payBtnDom.disabled = true;
				_feePayBtnSetLoading(payBtnDom, true, 'Checking fee\u2026');

				frappe.call({
					method: 'slcm.api.service.application_fee_service.get_application_fee_details',
					args: { applicant_name: applicantName },
					callback: function (fr) {
						var fd = fr && fr.message;
						var feeAmount = fd && (fd.fee_amount || 0);
						var canSubmit = fd && fd.can_submit;
						
						if (feeAmount > 0 && !canSubmit) {
							_feePayBtnSetLoading(payBtnDom, true, 'Creating order\u2026');
							frappe.call({
								method: 'slcm.api.service.fee_service.create_application_fee_razorpay_order',
								args: { applicant_name: fd.applicant_name },
								callback: function (r) {
									var d = r && r.message;
									if (d && d.already_paid) {
										payBtnDom.disabled = false;
										_feePayBtnSetLoading(payBtnDom, false);
										showToast('Application fee has already been paid.', 'success');
										_doFinalSubmit(applicantName, 'Submitted and Paid');
										return;
									}
									if (!d || !d.order_id) {
										payBtnDom.disabled = false;
										_feePayBtnSetLoading(payBtnDom, false);
										showToast('Could not create payment order. Please try again.', 'error');
										return;
									}

									var onPaid = function () {
										_doFinalSubmit(applicantName, 'Submitted and Paid');
									};
									var closeModal = function () {};

									if (typeof Razorpay === 'undefined') {
										_feePayBtnSetLoading(payBtnDom, true, 'Loading checkout\u2026');
										var sc = document.createElement('script');
										sc.src = 'https://checkout.razorpay.com/v1/checkout.js';
										sc.onload = function () { _openRazorpay(d, fd, onPaid, payBtnDom, closeModal); };
										sc.onerror = function () {
											payBtnDom.disabled = false;
											_feePayBtnSetLoading(payBtnDom, false);
											showToast('Payment gateway script failed to load. Please refresh.', 'error');
										};
										document.head.appendChild(sc);
									} else {
										_feePayBtnSetLoading(payBtnDom, true, 'Opening checkout\u2026');
										_openRazorpay(d, fd, onPaid, payBtnDom, closeModal);
									}
								},
								error: function () {
									payBtnDom.disabled = false;
									_feePayBtnSetLoading(payBtnDom, false);
									showToast('Network error while creating payment order.', 'error');
								}
							});
						} else {
							payBtnDom.disabled = false;
							_feePayBtnSetLoading(payBtnDom, false);
							showToast('Application fee is already paid or waived.', 'success');
							_doFinalSubmit(applicantName, 'Submitted and Paid');
						}
					},
					error: function () {
						payBtnDom.disabled = false;
						_feePayBtnSetLoading(payBtnDom, false);
						showToast('Could not verify fee status. Please try again.', 'error');
					}
				});
			});
			$topbar.append(btn);
		}
	}, 2000);
}

function slcmSetupPayButton() {
	setInterval(function () {
		if (document.getElementById('slcm-pay-btn')) return;
		var status = resolveField('status');
		if (status !== 'Submitted') return;

		var $title = $('.slcm-app-heading-row');
		if ($title.length) {
			var btn = $('<button id="slcm-pay-btn" class="slcm-btn-pay" style="padding: 7px 14px; font-size: 13px; margin-left: 15px; background: var(--slcm-primary, #1a3c6e); color: #fff; border: none; border-radius: 4px; cursor: pointer;">Pay Application Fee</button>');
			btn.on('click', function () {
				var applicantName = getDocName();
				if (!applicantName) return;
				
				_showSubmitOverlay('Checking application fee, Please don\'t refresh or close the page \u2026');
				frappe.call({
					method: 'slcm.api.service.application_fee_service.get_application_fee_details',
					args: { applicant_name: applicantName },
					callback: function (fr) {
						_hideSubmitOverlay();
						var fd = fr && fr.message;
						var feeAmount = fd && (fd.fee_amount || 0);
						var canSubmit = fd && fd.can_submit;
						
						if (feeAmount > 0 && !canSubmit) {
							_showFeeModal(fd, function () {
								_doFinalSubmit(applicantName, 'Submitted and Paid');
							});
						} else {
							showToast('Application fee is already paid or waived.', 'success');
							_doFinalSubmit(applicantName, 'Submitted and Paid');
						}
					},
					error: function () {
						_hideSubmitOverlay();
						showToast('Could not verify fee status. Please try again.', 'error');
					}
				});
			});
			$title.append(btn);
		}
	}, 2000);
}

// ── FIX: Force Frappe Web Form to reflect Check fields properly on reload ──
// Frappe's frontend evaluation of depends_on for parent sections wipes out child 
// field values on load. We explicitly fetch the actual saved values from the DB 
// and rehydrate the checkboxes, forcing the DOM to check them.
frappe.ready(function() {
	setTimeout(function() {
		if (frappe.web_form && frappe.web_form.doc && frappe.web_form.doc.name && frappe.web_form.doc.name !== 'new') {
			frappe.call({
				method: 'frappe.client.get',
				args: { doctype: 'Applicant', name: frappe.web_form.doc.name },
				callback: function(r) {
					if (r.message && frappe.web_form.fields_dict) {
						$.each(frappe.web_form.fields_dict, function(fname, field) {
							if (field.df.fieldtype === 'Check') {
								var val = r.message[fname];
								if (val === 1 || val === '1' || val === true) {
									field.set_value(1);
									if (field.$input && field.$input.length) {
										field.$input.prop('checked', true);
									}
								}
							}
						});
					}
				}
			});
		}
	}, 600);
});

// ───────────────────────────────────────────────────────────────────
//  UNSAVED CHANGES — our own "Leave page?" dialog for in-page navigation
//  (links, Back, Logout, notifications). Browsers do not allow replacing
//  their native prompt on tab close / refresh, so beforeunload stays for those.
// ───────────────────────────────────────────────────────────────────
var _slcmLeaveApproved = false;

/** Only an editable (Draft) application can lose work; submitted/completed ones are read-only. */
function slcmHasUnsavedChanges() {
	return !!(window.frappe && frappe.form_dirty) && !slcmApplicationPortalLocked();
}

function slcmConfirmLeave(proceed) {
	if (!slcmHasUnsavedChanges()) {
		proceed();
		return;
	}
	var d = new frappe.ui.Dialog({
		title: __('Leave this page?'),
		primary_action_label: __('Stay on page'),
		primary_action: function () {
			d.hide();
		},
		secondary_action_label: __('Leave page'),
		secondary_action: function () {
			d.hide();
			_slcmLeaveApproved = true;
			// If the navigation turns out to stay on this document, re-arm the warning
			setTimeout(function () { _slcmLeaveApproved = false; }, 4000);
			proceed();
		},
	});
	d.$body.html(
		'<p style="margin:0;font-size:14px;line-height:1.6;color:#475569;">' +
			__('You have unsaved changes in your application. If you leave now, anything entered since your last <b>Save Draft</b> will be lost.') +
			'</p>'
	);
	d.show();
}

frappe.ready(() => {
	// Prevent registering the events more than once.
	if (window.slcm_beforeunload_registered) {
		return;
	}
	window.slcm_beforeunload_registered = true;

	// Loading the saved values — and this script's own prefills / server callbacks (fee amount,
	// programme details …), which can land seconds later — fire change handlers that call
	// make_form_dirty() before the applicant has touched anything. Only count changes once the
	// applicant has actually interacted with a field (typing, picking, ticking, uploading).
	var EDIT_TARGETS = 'input, textarea, select, li, .btn-attach, .datepicker, .modal';
	['keydown', 'input', 'change', 'pointerdown'].forEach(function (ev) {
		document.addEventListener(ev, function (e) {
			if (e.isTrusted && e.target && e.target.closest && e.target.closest(EDIT_TARGETS)) {
				window._slcmUserTouched = true;
			}
		}, true);
	});
	var _dirtyPatchN = 0;
	var _dirtyPatchT = setInterval(function () {
		var wf = frappe.web_form;
		if (wf && typeof wf.make_form_dirty === 'function' && !wf._slcmDirtyPatched) {
			wf._slcmDirtyPatched = true;
			var origDirty = wf.make_form_dirty;
			wf.make_form_dirty = function () {
				if (!window._slcmUserTouched) return;   // programmatic change while loading
				return origDirty.apply(this, arguments);
			};
			if (!window._slcmUserTouched) frappe.form_dirty = false;   // drop anything set before the patch
		}
		if ((wf && wf._slcmDirtyPatched) || ++_dirtyPatchN > 100) clearInterval(_dirtyPatchT);
	}, 100);

	// Tab close / refresh / typing a new URL: only the browser's own prompt is possible here.
	window.addEventListener('beforeunload', (event) => {
		if (_slcmLeaveApproved || !slcmHasUnsavedChanges()) return;
		event.preventDefault();
		event.returnValue = '';
	});

	// Any same-tab link that leaves this page → our dialog instead of the browser prompt
	document.addEventListener(
		'click',
		function (e) {
			if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
			var a = e.target && e.target.closest && e.target.closest('a[href]');
			if (!a || a.hasAttribute('download')) return;
			if (a.target && a.target !== '_self') return;
			var href = (a.getAttribute('href') || '').trim();
			if (!href || href.charAt(0) === '#' || /^(javascript|mailto|tel):/i.test(href)) return;
			var url;
			try { url = new URL(a.href, window.location.href); } catch (err) { return; }
			if (url.pathname === window.location.pathname && url.search === window.location.search) return;
			if (!slcmHasUnsavedChanges()) return;

			e.preventDefault();
			e.stopPropagation();
			slcmConfirmLeave(function () {
				window.location.href = url.href;
			});
		},
		true
	);
});

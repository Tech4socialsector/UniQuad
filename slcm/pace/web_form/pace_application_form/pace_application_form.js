// Patch FormData — rename every uploaded File with a 12-char cryptographic hex suffix
// BEFORE it hits the server. Frappe's native upload handler then sets attached_to_* correctly,
// so no backend rename (handle_file_name) is needed and orphaned-file bugs are impossible.
if (typeof FormData !== 'undefined' && !window._slcm_pace_fd_patched) {
	window._slcm_pace_fd_patched = true;
	var _pace_orig_fd_append = FormData.prototype.append;
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
				return _pace_orig_fd_append.call(this, name, value, fname);
			}
		}
		return _pace_orig_fd_append.apply(this, arguments);
	};
}

// ═══════════════════════════════════════════════════════════════════
//  SLCM — PACE Application Web Form client script
//  Features:
//    • Portal nav/footer shell with Applicant Portal Config theme
//    • Application status badge
//    • Save Draft button with server-side persistence
//    • Stage progress bar (stepper) with mandatory validation
//    • Upload Student Photo inline preview
//    • Attach / Attach Image file type + size validation
//    • Date of Birth: age ≥ 17 enforcement, datepicker capped
//    • Phone number with country-based digit-length validation
//    • Toast notifications — top-right
//    • Numeric field restrictions
// ═══════════════════════════════════════════════════════════════════

// ───────────────────────────────────────────────────────────────────
//  UTILITIES
// ───────────────────────────────────────────────────────────────────
function _paceEsc(s) {
	var d = document.createElement('div');
	d.textContent = s == null ? '' : String(s);
	return d.innerHTML;
}

// ───────────────────────────────────────────────────────────────────
//  CSS INJECTION
// ───────────────────────────────────────────────────────────────────
function _paceInjectCSS() {
	if (document.getElementById('pace-wf-css')) return;

	if (!document.getElementById('pace-material-icons')) {
		var iconLink = document.createElement('link');
		iconLink.id = 'pace-material-icons';
		iconLink.rel = 'stylesheet';
		iconLink.href =
			'https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=block';
		document.head.appendChild(iconLink);
	}

	var s = document.createElement('style');
	s.id = 'pace-wf-css';
	s.textContent = [
		/* ── Toast ── */
		'#pace-toast{position:fixed;top:40px;right:24px;z-index:2500000;max-width:min(420px,calc(100vw - 32px));' +
		'min-width:260px;padding:13px 18px;border-radius:10px;font-size:13.5px;font-weight:500;line-height:1.5;' +
		'pointer-events:auto;box-shadow:0 8px 32px rgba(0,0,0,.18);display:none;cursor:default;transition:opacity .3s;}',
		'#pace-toast.pace-success{background:#f0fdf4;border:1.5px solid #86efac;color:#14532d;}',
		'#pace-toast.pace-error  {background:#fff2f2;border:1.5px solid #fca5a5;color:#991b1b;}',
		'#pace-toast.pace-info   {background:#eff6ff;border:1.5px solid #93c5fd;color:#1e3a5f;}',
		'#pace-toast.pace-warn   {background:#fffbeb;border:1.5px solid #fcd34d;color:#78350f;}',
		/* ── Spin ── */
		'@keyframes pace-spin{to{transform:rotate(360deg)}}',
		/* ── Hide Frappe default Public Upload Warning ── */
		'.file-uploader .alert-warning{display:none!important;}',
		/* ── Hide default Frappe nav/footer ── */
		'header.navbar,nav.navbar,.web-header,.web-navbar,#navbar-main,' +
		'header[class*="navbar"],.website-header,.website-footer,footer.footer,#footer-main{display:none!important;}',
		'.page-content{margin-top:0!important;padding-top:0!important;}',
		'.main-section{padding-top:0!important;}',
		/* PACE Admission “Open” badge (same idea as admission_base.html) */
		'@keyframes pace-partylight-bg{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}',
		'@keyframes pace-partylight-pulse-text{0%{transform:scale(1);filter:brightness(1)}100%{transform:scale(1.08);filter:brightness(1.2)}}',
		'.pace-badge-partylight-text{display:inline-block;font-weight:900;text-transform:uppercase;' +
		'background:linear-gradient(-45deg,#ff0055,#ffcc00,#00ff66,#0099ff,#cc00ff,#ff0055);background-size:400% 400%;' +
		'-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;' +
		'animation:pace-partylight-bg 2s linear infinite,pace-partylight-pulse-text .8s ease-in-out infinite alternate;' +
		'vertical-align:middle;line-height:1;}',
		/* ── Admission shell nav/footer (parity with applicant_form.js / admission_base.html) ── */
		'.adm-nav{background:var(--pace-primary,#1a3c6e);padding:10px 24px;display:flex;align-items:center;' +
		'justify-content:space-between;height:60px;position:sticky;top:0;z-index:1020;' +
		'box-shadow:0 2px 8px rgba(0,0,0,.15);}',
		'.adm-nav-brand{display:flex;align-items:center;gap:12px;text-decoration:none;color:#fff;' +
		'font-weight:400!important;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:65%;margin-top: 1rem!important}',
		'.adm-nav-brand img{height:clamp(28px,6vw,36px);width:auto;flex-shrink:0;}',
		'.adm-nav-links{display:flex;gap:clamp(10px,2vw,20px);align-items:center;}',
		'.adm-nav-links a{color:rgba(255,255,255,.85);text-decoration:none;font-size:14px;font-weight:500;}',
		'.adm-nav-links a:hover{color:#fff;}',
		'#adm-avatar-btn{user-select:none;-webkit-user-select:none;transition:all .2s;overflow:hidden;padding:0;flex-shrink:0;}',
		'#adm-avatar-btn:hover{border-color:rgba(255,255,255,.7)!important;box-shadow:0 0 0 3px rgba(255,255,255,.2)!important;}',
		'#adm-avatar-menu a:hover{background:#f8fafc!important;}',
		/* Mobile slide-down menu (opened via .pace-nav-drawer-open) */
		'#pace-mobile-nav-overlay{position:fixed;inset:0;z-index:2000010;background:rgba(15,23,42,.45);' +
		'opacity:0;visibility:hidden;transition:opacity .22s ease,visibility .22s;pointer-events:none;}' +
		'#pace-mobile-nav-overlay.is-open{opacity:1;visibility:visible;pointer-events:auto;}' +
		'.pace-mobile-nav-panel{position:absolute;left:0;right:0;top:0;background:#fff;' +
		'border-radius:0 0 18px 18px;box-shadow:0 18px 50px rgba(0,0,0,.2);max-height:min(92vh,760px);' +
		'overflow-y:auto;transform:translateY(-10px);opacity:0;transition:transform .24s ease,opacity .24s ease;}' +
		'#pace-mobile-nav-overlay.is-open .pace-mobile-nav-panel{transform:translateY(0);opacity:1;}' +
		'.pace-mobile-nav-panel__head{display:flex;align-items:center;justify-content:space-between;' +
		'gap:12px;padding:12px 16px;background:var(--pace-primary,#1a3c6e);color:#fff;min-height:52px;box-sizing:border-box;}' +
		'.pace-mobile-nav-panel__title{font-size:16px;font-weight:400;letter-spacing:.02em;flex:1;min-width:0;' +
		'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}' +
		'.pace-mobile-nav-panel__close{width:40px;height:40px;border-radius:10px;border:none;cursor:pointer;' +
		'flex-shrink:0;display:flex;align-items:center;justify-content:center;' +
		'background:color-mix(in srgb,var(--pace-primary,#1a3c6e) 72%,#fff);color:#fff;font-size:26px;' +
		'font-weight:300;line-height:1;padding:0;}' +
		'.pace-mobile-nav-panel__profile{display:flex;align-items:flex-start;gap:14px;padding:18px 18px 14px;' +
		'border-bottom:1px solid #e5e7eb;}' +
		'.pace-mobile-nav-panel__avatar{width:48px;height:48px;border-radius:4px;overflow:hidden;flex-shrink:0;' +
		'display:flex;align-items:center;justify-content:center;background:#f1f5f9;font-weight:400;font-size:18px;' +
		'color:var(--pace-primary,#1a3c6e);}' +
		'.pace-mobile-nav-panel__avatar img{width:100%;height:100%;object-fit:cover;}' +
		'.pace-mobile-nav-panel__user{flex:1;min-width:0;padding-right:4px;}' +
		'.pace-mobile-nav-panel__name{font-size:15px;font-weight:400;color:#0f172a;line-height:1.25;word-break:break-word;}' +
		'.pace-mobile-nav-panel__email{font-size:12px;color:#64748b;margin-top:4px;word-break:break-word;}' +
		'.pace-mobile-nav-panel__bell{margin-left:auto;background:none;border:none;color:#334155;cursor:pointer;' +
		'padding:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}' +
		'.pace-mobile-nav-panel__profile--guest{justify-content:center;padding:16px 18px;}' +
		'.pace-drawer-nav-link{display:flex;align-items:center;gap:14px;padding:14px 18px;text-decoration:none;' +
		'color:#0f172a;font-size:15px;font-weight:400;border:none;background:#fff;width:100%;box-sizing:border-box;' +
		'text-align:left;cursor:pointer;font-family:inherit;}' +
		'.pace-drawer-nav-link:hover,.pace-drawer-nav-link:focus{background:#f8fafc;outline:none;}' +
		'.pace-drawer-nav-link__icon{font-family:Material Symbols Outlined;font-size:22px;width:28px;text-align:center;' +
		"font-variation-settings:'FILL' 0,'wght' 500,'GRAD' 0,'opsz' 24;color:var(--pace-primary,#1a3c6e);}" +
		'.pace-drawer-nav-link .pace-badge-partylight-text{margin-left:auto;font-size:9px;}' +
		'.pace-drawer-nav-link--logout{color:#dc2626!important;}' +
		'.pace-drawer-nav-link--logout .pace-drawer-nav-link__icon{color:#dc2626!important;}' +
		'.pace-mobile-nav-panel__hr{height:1px;background:#e5e7eb;margin:6px 0;}' +
		'.pace-nav-drawer-open{display:none;align-items:center;justify-content:center;width:44px;height:44px;' +
		'margin-left:auto;flex-shrink:0;border:none;border-radius:10px;background:rgba(255,255,255,.2);' +
		'color:#fff;cursor:pointer;padding:0;}' +
		'.pace-nav-drawer-open svg{display:block;}' +
		'@media (min-width:992px) { #pace-mobile-nav-overlay{display:none!important;} .pace-nav-drawer-open{display:none!important;} }' +
		/* ≤992px: top bar = brand + menu; links live in drawer */
		'@media (max-width:991.98px){' +
		'.pace-nav-drawer-open{display:flex!important;}' +
		'.adm-nav-links--desktop{display:none!important;}' +
		'.adm-nav{flex-wrap:nowrap;height:56px;min-height:52px;padding:8px 12px;gap:10px;overflow:hidden;' +
		'box-sizing:border-box;align-items:center;justify-content:flex-start;}' +
		'.adm-nav-brand{flex:1 1 auto;min-width:0;max-width:none;margin-right:0;}' +
		'.adm-nav-brand img{height:28px;}' +
		'.adm-nav-login{font-size:12px!important;padding:6px 12px!important;white-space:nowrap;}' +
		'#pace-form-topbar{flex-direction:column;align-items:stretch!important;gap:10px;padding:10px 8px;}' +
		'#pace-form-topbar-left,#pace-form-topbar-right{width:100%;flex-wrap:wrap;justify-content:space-between;}' +
		'.web-form-container,.page-content,.main-section .container,.main-section{max-width:100%!important;' +
		'box-sizing:border-box;padding-left:max(10px,env(safe-area-inset-left))!important;' +
		'padding-right:max(10px,env(safe-area-inset-right))!important;}' +
		'.web-form,.web-form .form-page,.web-form .web-form-body,.web-form .form-layout{max-width:100%;overflow-x:hidden;}' +
		'.web-form .form-column,.web-form .form-grid .form-column{min-width:0!important;}' +
		'}',
		'.adm-wf-footer{background:#0f172a;color:#94a3b8;padding:40px 24px 20px;margin-top:48px;font-family:inherit;}',
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
		'.full-bleed-footer{width:100%;max-width:none;margin-left:0;margin-right:0;position:relative;' +
		'background:var(--footer-color);color:var(--footer-text);padding:48px 0 24px;box-sizing:border-box;}',
		'.footer-container{width:100%;max-width:1400px;margin:0 auto;padding:0 24px;}',
		'@media(min-width:1600px){.footer-container{max-width:1540px;}}',
		'@media(min-width:1920px){.footer-container{max-width:1840px;}}',
		/* ── Save Draft button ── */
		'#pace-save-draft-btn{display:inline-flex;align-items:center;gap:7px;padding:7px 18px;' +
		'border-radius:7px;font-size:13px;font-weight:300;cursor:pointer;' +
		'border:1.5px solid var(--pace-primary,#1a3c6e);background:#fff;color:var(--pace-primary,#1a3c6e);' +
		'transition:background .15s,color .15s;white-space:nowrap;margin-right:10px;}',
		'#pace-save-draft-btn:hover:not(:disabled){background:color-mix(in srgb,var(--pace-primary,#1a3c6e) 8%,#fff);}',
		'#pace-save-draft-btn:disabled{opacity:.6;cursor:not-allowed;}',
		/* ── Application status badge ── */
		'.pace-app-heading-row{display:flex;align-items:center;flex-wrap:wrap;gap:12px 28px;line-height:1.25;margin:0;}',
		'#pace-app-heading-id{flex:0 1 auto;margin:0;min-width:0;font-size:clamp(1.2rem,2.4vw,1.65rem);' +
		'font-weight:400;color:var(--pace-primary,#1a3c6e);letter-spacing:-.02em;line-height:1.2;}',
		'#pace-app-heading-meta{display:inline-flex;align-items:center;flex-wrap:wrap;gap:6px 10px;flex:0 1 auto;margin:0;}',
		'.pace-status-badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:20px;' +
		'font-size:11px;font-weight:400;letter-spacing:.4px;line-height:1.2;text-transform:uppercase;}',
		'.pace-status-draft    {background:#fef3c7;color:#92400e;border:1px solid #fcd34d;}',
		'.pace-status-submitted{background:#dcfce7;color:#14532d;border:1px solid #86efac;}',
		'.pace-status-provisional{background:#ffedd5;color:#9a3412;border:1px solid #fed7aa;}',
		'.pace-status-other    {background:#f1f5f9;color:#475569;border:1px solid #cbd5e1;}',
		/* Hide Frappe Web Form “Not Saved” / dirty-state pill (always) */
		'.web-form-container .indicator-pill.orange,.web-form .indicator-pill.orange,' +
		'.web-form-head .indicator-pill.orange,.page-content .web-form .indicator-pill.orange{display:none!important;}',
		/* Attach / read-only: show field labels (Frappe often omits them when control is read-only) — parity with applicant_form.js */
		'.web-form .control-label,.web-form .frappe-control > label.control-label,' +
		'.frappe-control .control-label{font-weight:300;color:#0f172a;font-size:13px;margin-bottom:6px;display:block;}',
		/* ── Top bar ── */
		'#pace-form-topbar{display:flex;align-items:center;justify-content:space-between;padding:12px 4px;margin-bottom:8px;max-width:1400px;margin-left:auto;margin-right:auto;}',
		'#pace-form-topbar-left{display:flex;align-items:center;gap:20px;}',
		'#pace-form-topbar-right{display:flex;align-items:center;gap:12px;}',
		'#pace-receipt-btn{display:inline-flex;align-items:center;gap:8px;padding:8px 18px;border-radius:8px;' +
		'font-size:13.5px;font-weight:300;border:none;background:var(--pace-primary,#1a3c6e);color:#fff!important;' +
		'cursor:pointer;transition:all .2s;box-shadow:0 2px 5px rgba(0,0,0,0.1);}',
		'#pace-receipt-btn:hover{background:#132d54;transform:translateY(-1px);box-shadow:0 4px 8px rgba(0,0,0,0.15);}',
		'#pace-back-btn{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:8px;' +
		'font-size:13px;font-weight:300;border:1.5px solid #e2e8f0;background:#fff;color:#475569;' +
		'cursor:pointer;text-decoration:none!important;transition:all .2s;}',
		'#pace-back-btn:hover{background:#f8fafc;border-color:#cbd5e1;color:#1e293b;}',
		'#pace-applying-for-wrap{font-size:13px;color:#64748b;}',
		'#pace-applying-for-wrap strong{color:#1e293b;margin-left:4px;}',
		/* ── Stepper ── */
		'#pace-stepper-wrap{padding:15px 16px 28px;overflow-x:auto;scrollbar-width:none;-ms-overflow-style:none;width:100%;box-sizing:border-box;}',
		'#pace-stepper-wrap::-webkit-scrollbar{display:none;}',
		/* Stepper: flex + centered so ultrawide screens do not stretch 1fr gaps between stages */
		'.pace-stepper.pace-stepper-flex{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;' +
		'box-sizing:border-box;width:100%;max-width:100%;min-width:0;padding:0 6px;gap:0;row-gap:10px;}',
		'.pace-stepper.pace-stepper-flex .pace-step{flex:0 0 auto;}',
		'.pace-step{display:flex;flex-direction:row;align-items:center;gap:14px;cursor:pointer;position:relative;' +
		'min-width:104px;max-width:min(220px,32vw);width:max-content;transition:background .25s,border-color .25s;' +
		'padding:10px 10px 10px;border-radius:14px;border:1px solid transparent;background:#f3f4f6;}',
		'.pace-step-connector{flex:0 0 auto;align-self:center;width:clamp(10px,2.2vw,52px);min-width:10px;max-width:52px;' +
		'height:2px;background:#e5e7eb;border-radius:1px;pointer-events:none;}',
		/* Narrow viewports: one row + horizontal scroll (avoid flex-wrap zig-zag on phones) */
		'@media (max-width:991.98px){' +
		'#pace-stepper-wrap,.web-form-container:has(#pace-stepper-wrap) #pace-stepper-wrap{' +
		'padding:12px 10px 18px!important;overflow-x:auto!important;-webkit-overflow-scrolling:touch;' +
		'scroll-snap-type:x proximity;touch-action:pan-x;}' +
		'.pace-stepper.pace-stepper-flex{flex-wrap:nowrap;justify-content:flex-start;width:max-content;max-width:none;' +
		'padding:0 4px;row-gap:0;}' +
		'.pace-stepper.pace-stepper-flex .pace-step{scroll-snap-align:start;min-width:0;max-width:min(168px,46vw);' +
		'padding:8px 8px;gap:8px;}' +
		'.pace-step-connector{width:12px;min-width:8px;max-width:16px;}' +
		'.pace-step-circle{width:20px;height:20px;font-size:12px;}' +
		'.pace-step-label{font-size:10px;max-width:10em;line-height:1.2;}' +
		'}',
		/* Completed */
		'.pace-step.completed:not(.active){background:#ecfdf5;border-color:#bbf7d0;}',
		'.pace-step.completed .pace-step-circle{border-color:#22c55e;background:#22c55e;color:#fff;}',
		'.pace-step.completed .pace-step-label{color:#166534;}',
		'.pace-step.completed + .pace-step-connector{background:#86efac;}',
		/* Active */
		'.pace-step.active{background:#e0ecfa;border-color:#2471f3;}',
		'.pace-step.active .pace-step-circle{border-color:#2471f3;background:#2471f3;color:#fff;box-shadow:0 0 0 4px rgba(36,113,243,0.13);}',
		'.pace-step.active .pace-step-label{color:#1e3a8a;}',
		/* Default */
		'.pace-step:not(.active):not(.completed){background:#f3f4f6;border-color:#e5e7eb;}',
		'.pace-step:not(.active):not(.completed) .pace-step-circle{border-color:#e5e7eb;background:#fff;color:#9ca3af;}',
		'.pace-step:not(.active):not(.completed) .pace-step-label{color:#9ca3af;}',
		/* Common */
		'.pace-step-circle{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;' +
		'font-size:14px;font-weight:400;border:2px solid #e9d5d8;background:#fff;z-index:2;transition:all 0.25s ease;}',
		'.pace-step-label{font-size:14px;font-weight:400;text-align:left;line-height:1.25;white-space:normal;max-width:13em;transition:color .25s;flex:1;}',
		'.pace-step.active:hover .pace-step-circle{border-color:#1e40af;}',
		'.pace-step.completed:hover .pace-step-circle{border-color:#16a34a;}',
		'.pace-step:hover .pace-step-circle{border-color:#1e40af;}',
		/* Stepper card integration */
		'.web-form-container:has(#pace-stepper-wrap) #pace-stepper-wrap{' +
		'background:#fff;border:1px solid #e2e8f0;border-bottom:none;border-radius:12px 12px 0 0;' +
		'margin:16px 0 0;padding:20px 16px 28px;position:relative;z-index:1;}',
		'.web-form-container:has(#pace-stepper-wrap) form.web-form{' +
		'border:1px solid #e2e8f0!important;border-top:1px solid #eef2f6!important;' +
		'border-radius:0 0 12px 12px!important;background:#fff!important;margin-top:0!important;' +
		'overflow-x:visible!important;overflow-y:visible!important;}',
		'.web-form-container:has(#pace-stepper-wrap) form.web-form .web-form-body{border-top:none!important;}',
		/* Section heading colour driven by theme var */
		'.web-form-container .section-head,.web-form .section-head{color:var(--pace-primary,#1a3c6e)!important;}',
		'.btn-next,.submit-btn,.btn-submit-web-form{background:var(--pace-primary,#1a3c6e)!important;' +
		'border-color:var(--pace-primary,#1a3c6e)!important;color:#fff!important;}',
		/* Student photo */
		'.pace-photo-preview{margin:0 0 14px;display:flex;align-items:flex-start;}',
		'.pace-photo-preview img{display:block;width:140px;height:140px;object-fit:cover;' +
		'border-radius:0;border:2px solid #e2e8f0;box-shadow:0 1px 4px rgba(0,0,0,.06);background:#f8fafc;}',
		'.pace-field-error{border-color:#ef4444!important;box-shadow:0 0 0 3px rgba(239,68,68,0.15)!important;}',
		'.pace-loading-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(255,255,255,0.85);' +
		'display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:999999;transition:opacity .3s;}',
		'.pace-spinner{width:48px;height:48px;border:4.5px solid #e2e8f0;border-top:4.5px solid var(--pace-primary,#1a3c6e);' +
		'border-radius:50%;animation:pace-spin .8s linear infinite;margin-bottom:16px;}',
		'.maroon-dots{display:flex;align-items:center;justify-content:center;gap:8px;margin-bottom:20px;}',
		'.maroon-dot{width:12px;height:12px;background-color:#800020;border-radius:9999px!important;display:inline-block;animation:maroon-dot-bounce 1.4s infinite ease-in-out both;}',
		'.maroon-dot:nth-child(1){animation-delay:-0.32s;}',
		'.maroon-dot:nth-child(2){animation-delay:-0.16s;}',
		'@keyframes maroon-dot-bounce{0%,80%,100%{transform:scale(0);opacity:0.3;}40%{transform:scale(1.0);opacity:1;}}',
		'.pace-loading-text{font-size:15px;font-weight:300;color:var(--pace-primary,#1a3c6e);letter-spacing:.01em;}',
		/* Custom Modal */
		'.pace-modal-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(15,23,42,0.6);' +
		'backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;z-index:1000000;}',
		'.pace-modal{background:#fff;border-radius:18px;width:min(440px,90vw);padding:32px;box-shadow:0 20px 25px -5px rgba(0,0,0,0.1);' +
		'animation:pace-modal-in .3s cubic-bezier(0.34, 1.56, 0.64, 1);}',
		'@keyframes pace-modal-in{from{transform:scale(0.92);opacity:0;}to{transform:scale(1);opacity:1;}}',
		'.pace-modal-icon{width:54px;height:54px;background:#f0f7ff;border-radius:50%;display:flex;align-items:center;' +
		'justify-content:center;margin:0 auto 18px;color:var(--pace-primary,#1a3c6e);}',
		'.pace-modal-title{font-size:1.25rem;font-weight:400;color:#1e293b;text-align:center;margin-bottom:8px;letter-spacing:-.01em;}',
		'.pace-modal-text{font-size:14px;color:#64748b;text-align:center;line-height:1.6;margin-bottom:24px;}',
		'.pace-fee-card{background:#f8fafc;border:1.5px solid #eef2f6;border-radius:14px;padding:20px 16px;margin-bottom:28px;text-align:center;}',
		'.pace-fee-label{font-size:11px;font-weight:400;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px;}',
		'.pace-fee-amount{font-size:32px;font-weight:850;color:var(--pace-primary,#1a3c6e);letter-spacing:-.02em;}',
		'.pace-modal-actions{display:flex;flex-direction:column;gap:10px;}',
		'.pace-btn-pay{background:var(--pace-primary,#1a3c6e);color:#fff;border:none;padding:13px;border-radius:10px;' +
		'font-weight:400;font-size:15px;cursor:pointer;transition:transform .1s,filter .2s;display:flex;align-items:center;justify-content:center;gap:8px;}',
		'.pace-btn-pay:active{transform:scale(.98);}',
		'.pace-btn-cancel{background:transparent;color:#94a3b8;border:none;padding:8px;font-weight:300;cursor:pointer;font-size:13px;transition:color .2s;}',
		'.pace-btn-cancel:hover{color:#64748b;}',
		/* Overflow fix — grids + Link autocomplete (awesomplete) under stepper */
		'.web-form .form-grid-container,.web-form .form-grid{overflow-x: auto !important;overflow-y: auto !important;}',
		'.web-form .form-page,.web-form .form-section{overflow:visible!important;}',
		'.web-form .frappe-control[data-fieldname="ug_degree"],' +
		'.web-form [data-fieldname="ug_degree"] .form-grid,' +
		'.web-form [data-fieldname="ug_degree"] .form-grid-container,' +
		'.web-form [data-fieldname="ug_degree"] .grid-body{overflow-x: auto !important;overflow-y: auto !important;}',
		'.web-form .awesomplete > ul{' +
		'z-index:2147483000!important;}',	
		/* Small Text / Text / Long Text — auto height (Web Form custom_css forces .form-control 42px) */
		'.web-form textarea.form-control,.web-form .frappe-control textarea.form-control{' +
		'height:auto!important;min-height:104px!important;line-height:1.5!important;padding:10px 12px!important;' +
		'resize:vertical!important;overflow-y:auto!important;}',
		'.web-form .frappe-control[data-fieldtype="Small Text"] textarea.form-control,' +
		'.web-form .frappe-control[data-fieldtype="Text"] textarea.form-control,' +
		'.web-form .frappe-control[data-fieldtype="Long Text"] textarea.form-control{' +
		'min-height:120px!important;}',
		'.web-form .frappe-control[data-fieldtype="Small Text"] textarea.form-control:disabled,' +
		'.web-form .frappe-control[data-fieldtype="Small Text"] textarea.form-control[disabled],' +
		'.web-form .frappe-control[data-fieldtype="Text"] textarea.form-control:disabled,' +
		'.web-form .frappe-control[data-fieldtype="Long Text"] textarea.form-control:disabled{' +
		'min-height:120px!important;height:auto!important;}',
		'.web-form .frappe-control[data-fieldtype="Small Text"] .control-value,' +
		'.web-form .frappe-control[data-fieldtype="Text"] .control-value,' +
		'.web-form .frappe-control[data-fieldtype="Long Text"] .control-value{' +
		'height:auto!important;min-height:72px!important;white-space:pre-wrap!important;' +
		'overflow:visible!important;line-height:1.5!important;padding:10px 12px!important;}',
	].join('');
	document.head.appendChild(s);
}

// ───────────────────────────────────────────────────────────────────
//  DATA HELPERS
// ───────────────────────────────────────────────────────────────────
function _paceGetDocName() {
	var name = frappe.web_form && frappe.web_form.doc && frappe.web_form.doc.name;
	if (!name) {
		var p = new URLSearchParams(window.location.search);
		name = p.get('name') || p.get('doc');
	}
	if (!name && window.location && window.location.pathname) {
		var path = String(window.location.pathname).replace(/\/$/, '');
		var m = path.match(/\/pace-application-form\/([^/]+)(?:\/edit)?$/);
		if (m && m[1] && m[1] !== 'new' && m[1] !== 'list') {
			name = decodeURIComponent(m[1]);
		}
	}
	return name || null;
}

function _paceResolveField(fieldname) {
	var wf = frappe.web_form;
	var val = '';
	try { val = (wf && wf.get_value(fieldname)) || ''; } catch (e) { }
	if (!val && wf && wf.doc) val = wf.doc[fieldname] || '';
	if (!val && frappe.reference_doc) val = frappe.reference_doc[fieldname] || '';
	return val;
}

/** Editable portal statuses (PACE Application Status link names). */
function _paceIsEditableStatus(status) {
	var s = (status || '').trim().toLowerCase();
	return !s || s === 'draft' || s === 'returned for correction';
}

function _paceResolveApplicationStatus() {
	if (window._pace_server_status) return window._pace_server_status;
	var fromField = (_paceResolveField('status') || '').trim();
	if (fromField) return fromField;
	try {
		if (frappe.web_form && frappe.web_form.doc && frappe.web_form.doc.status) {
			return String(frappe.web_form.doc.status).trim();
		}
	} catch (e) { }
	return '';
}

function _paceRefreshApplicationStatusFromServer(callback) {
	var docname = _paceGetDocName();
	if (!docname || docname === 'new' || docname === 'list') {
		window._pace_server_status = '';
		if (callback) callback('');
		return;
	}
	frappe.call({
		method: 'slcm.pace.web_form.pace_application_form.pace_application_form.get_pace_status',
		args: { application_name: docname },
		callback: function (r) {
			var status = (r && r.message && r.message.status) || '';
			window._pace_server_status = status;
			window._pace_server_status_obj = r && r.message;
			try {
				if (frappe.web_form && frappe.web_form.doc) frappe.web_form.doc.status = status;
			} catch (e2) { }
			_paceUpdateStatusBadge(status);
			if (callback) callback(r && r.message ? r.message : status);
		},
		error: function () {
			if (callback) callback(_paceResolveApplicationStatus());
		},
	});
}

function _pacePortalLocked(statusOverride) {
	var s = (statusOverride != null ? statusOverride : _paceResolveApplicationStatus());
	return !_paceIsEditableStatus(s);
}

/** Lock all fields and hide edit actions (Submitted, Completed, etc.). */
function _paceApplyPortalLock(wf) {
	if (!wf) return;
	try { wf.in_edit_mode = false; } catch (e) { }
	if (wf.fields) {
		wf.fields.forEach(function (f) {
			if (f.fieldname) {
				try { wf.set_df_property(f.fieldname, 'read_only', 1); } catch (e2) { }
			}
		});
	}
	$('#pace-save-draft-btn, .submit-btn, .btn-submit-web-form, .btn-primary[type="submit"], .discard-btn, .btn-edit, .edit-button, [data-label="Edit"], .grid-footer, .grid-add-row, .grid-remove-row, .btn-remove').hide();
	$('.web-form input, .web-form select, .web-form textarea').attr('disabled', 'disabled').css('cursor', 'not-allowed');
	$('.web-form .btn-attach, .web-form .btn-remove, .web-form .reload-file').hide();

	// Restore Check field values — Frappe's read_only re-render and input disable
	// can clear the visual checked state even if the underlying doc value is 1.
	_paceRestoreCheckboxValues(wf);
}

/**
 * Fetch declaration checkbox values DIRECTLY from the server and force them in the DOM.
 * We bypass wf.doc entirely because WebForm.set_values can crash (autocomplete errors)
 * and leave wf.doc with stale/missing values.
 */
function _paceRestoreCheckboxValues(wf) {
	var CHECK_FIELDS = ['acknowledge_check', 'understand_check', 'communication_check'];

	function _applyToDOM(data) {
		CHECK_FIELDS.forEach(function(fn) {
			if (data[fn] || data[fn] === 1 || data[fn] === true) {
				$('[data-fieldname="' + fn + '"] input[type="checkbox"]').each(function() {
					this.checked = true;
					this.removeAttribute('disabled');
					// Re-disable so it stays read-only visually but shows as checked
					this.setAttribute('disabled', 'disabled');
				});
				// Also update Frappe's control value without triggering re-render
				if (wf && wf.fields_dict && wf.fields_dict[fn]) {
					try { wf.fields_dict[fn].value = 1; } catch(e) {}
					try { wf.doc[fn] = 1; } catch(e) {}
				}
			}
		});
	}

	// 1. Try wf.doc first (fast, may be incomplete)
	if (wf && wf.doc) {
		_applyToDOM(wf.doc);
	}

	// 2. Fetch from server (authoritative)
	var docname = _paceGetDocName();
	if (!docname || docname === 'new' || window._pace_chk_fetched) return;
	window._pace_chk_fetched = true;

	frappe.call({
		method: 'frappe.client.get_value',
		args: {
			doctype: 'PACE Application',
			filters: { name: docname },
			fieldname: CHECK_FIELDS
		},
		callback: function(r) {
			if (!r || !r.message) return;
			var data = r.message;
			// Update wf.doc so subsequent calls use correct data
			if (wf && wf.doc) {
				CHECK_FIELDS.forEach(function(fn) { wf.doc[fn] = data[fn] || 0; });
			}
			_applyToDOM(data);
			// Re-apply after short delays to survive Frappe re-renders
			setTimeout(function() { _applyToDOM(data); }, 300);
			setTimeout(function() { _applyToDOM(data); }, 800);
			setTimeout(function() { _applyToDOM(data); }, 1500);
			setTimeout(function() { _applyToDOM(data); }, 3000);

			// MutationObserver — re-apply whenever the declaration page appears
			if (!window._pace_chk_observer) {
				window._pace_chk_observer = new MutationObserver(function() {
					CHECK_FIELDS.forEach(function(fn) {
						var $chk = $('[data-fieldname="' + fn + '"] input[type="checkbox"]');
						if ($chk.length && data[fn]) {
							$chk.each(function() {
								if (!this.checked) {
									this.checked = true;
									this.setAttribute('disabled', 'disabled');
								}
							});
						}
					});
				});
				window._pace_chk_observer.observe(document.querySelector('.web-form') || document.body, {
					childList: true,
					subtree: true,
					attributes: true,
					attributeFilter: ['class', 'style']
				});
			}
		}
	});
}

function _paceCollectDraftData() {
	var wf = frappe.web_form;
	var doc = (wf && wf.doc) || {};
	var data = {};
	try { data = wf.get_values(true) || {}; } catch (e) { }
	// Preserve key fields from doc
	var PRESERVE = ['name', 'programme', 'status'];
	var ref = frappe.reference_doc || {};
	PRESERVE.forEach(function (k) {
		if (!data[k] && doc[k]) data[k] = doc[k];
		if (!data[k] && ref[k]) data[k] = ref[k];
	});
	return data;
}

// ───────────────────────────────────────────────────────────────────
//  TOAST — top-right, auto-dismiss 4 s
// ───────────────────────────────────────────────────────────────────
var _paceToastTimer = null;
function paceShowToast(message, type, durationMs) {
	var el = document.getElementById('pace-toast');
	if (!el) {
		el = document.createElement('div');
		el.id = 'pace-toast';
		el.setAttribute('role', 'alert');
		document.body.appendChild(el);
		el.addEventListener('click', function () {
			el.style.display = 'none';
			if (_paceToastTimer) clearTimeout(_paceToastTimer);
		});
	}
	el.className = 'pace-' + (type || 'info');
	el.textContent = message;
	el.title = 'Click to dismiss';
	el.style.display = 'block';
	if (_paceToastTimer) clearTimeout(_paceToastTimer);
	var ms = typeof durationMs === 'number' && durationMs > 0 ? durationMs : 4000;
	_paceToastTimer = setTimeout(function () { el.style.display = 'none'; }, ms);
}

// ───────────────────────────────────────────────────────────────────
//  PORTAL SHELL — themed nav + footer (Applicant Portal Config)
// ───────────────────────────────────────────────────────────────────
// Module-level store for user data fetched from portal shell
/**
 * Dynamic Applicant Name Sync: concatenates Title + First + Middle + Last
 */
function _paceSetupNameSync() {
	var n = 0;
	var t = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		if (wf && typeof wf.on === 'function') {
			clearInterval(t);

			var runSync = function () {
				// var t = (wf.get_value('title') || '').trim();
				var f = (wf.get_value('first_name') || '').trim();
				var m = (wf.get_value('middle_name') || '').trim();
				var l = (wf.get_value('last_name') || '').trim();

				var parts = [];
				// if (t) parts.push(t);
				if (f) parts.push(f);
				if (m) parts.push(m);
				if (l) parts.push(l);

				var fullName = parts.join(' ');
				if (fullName !== (wf.get_value('applicant_name') || '').trim()) {
					wf.set_value('applicant_name', fullName);
				}
			};

			wf.on('title', runSync);
			wf.on('first_name', runSync);
			wf.on('middle_name', runSync);
			wf.on('last_name', runSync);
		}
		if (++n > 100) clearInterval(t);
	}, 200);
}

var _paceUserData = null;

function _paceInjectPortalShell() {
	if (document.getElementById('slcm-adm-nav')) return;
	frappe.call({
		method: 'slcm.pace.web_form.pace_application_form.pace_application_form.get_pace_portal_shell_data',
		callback: function (r) {
			var d = (r && r.message) || {};
			_paceBuildAdmissionShell(
				{ title: d.site_title },
				{
					portal_title: d.portal_title,
					primary_color: d.primary_color,
					secondary_color: d.secondary_color,
					navbar_color: d.navbar_color,
					footer_color: d.footer_color,
					footer_text_color: d.footer_text_color,
					button_border_radius: d.button_border_radius,
					font_family: d.font_family,
					font_size_preset: d.font_size_preset,
					font_size_heading: d.font_size_heading,
					font_size_subheading: d.font_size_subheading,
					font_size_body: d.font_size_body,
					font_size_form_title: d.font_size_form_title,
					font_size_toast: d.font_size_toast,
					footer_address: d.footer_address,
					footer_phone: d.footer_phone,
					contact_email: d.contact_email,
					footer_text: d.footer_text || '',
					pace_footer: d.pace_footer || [],
					programmes: d.programmes || [],
					pace_enabled: d.pace_enabled || 0,
					powerd_by: d.powerd_by || 'boscosoft',
					institution_logo: d.institution_logo || '',
					social_links: d.social_links || [],
				},
				d.user || 'Guest',
				{ full_name: d.full_name, user_image: d.user_image, email: d.email || '' }
			);
			_paceUserData = d;
			_paceTriggerPrefill();
		},
		error: function () {
			_paceBuildAdmissionShell(
				{ title: 'SLCM' },
				{
					portal_title: 'Admissions',
					primary_color: '#1a3c6e',
					secondary_color: '#c8a14b',
					font_family: 'System Default',
					footer_address: '',
					footer_phone: '',
					contact_email: '',
					footer_text: '',
					pace_footer: [],
					programmes: [],
					pace_enabled: 0,
					powerd_by: 'boscosoft',
				},
				'Guest',
				{}
			);
			_paceUserData = { user: 'Guest' };
			_paceTriggerPrefill();
		},
	});
}

/** 
 * Co-ordinates between Portal Shell API and Web Form Lifecycle.
 * Runs prefill as soon as BOTH are ready.
 */
function _paceTriggerPrefill() {
	var n = 0;
	var t = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		// Wait for web_form AND fields_dict AND our shell user data
		if (wf && wf.fields_dict && Object.keys(wf.fields_dict).length > 0 && _paceUserData) {
			clearInterval(t);
			_paceRunPrefill();
		}
		if (++n > 200) clearInterval(t);
	}, 100);
}

/** Actual prefill execution */
var _pacePrefillDone = false;
function _paceRunPrefill() {
	if (_pacePrefillDone) return;

	var wf = window.frappe && frappe.web_form;
	if (!wf || !wf.fields_dict || !_paceUserData) return;

	// Only prefill for NEW applications
	var isNew = false;
	try {
		isNew = wf.doc && (wf.doc['__islocal'] || wf.doc.name === 'new' || !wf.doc.name || wf.is_new);
	} catch (e) { }
	
	var _pathname = (window.location.pathname || '').replace(/\/$/, '');
	var docNameFromUrl = _paceGetDocName();
	
	if (docNameFromUrl && docNameFromUrl !== 'new' && docNameFromUrl !== 'list') {
		isNew = false; // We have an existing document ID in the URL
	} else if (!isNew && _pathname.indexOf('/new') !== -1) {
		isNew = true;
	}

	if (!isNew) return;
	_pacePrefillDone = true;

	var d = _paceUserData;
	var searchParams = new URLSearchParams(window.location.search);
	var programme = searchParams.get('programme');

	if (!programme) {
		_paceShowProgrammePicker(wf, function (selectedProg) {
			// User confirmed a programme — inject into URL so the rest of the flow works
			var url = new URL(window.location.href);
			url.searchParams.set('programme', selectedProg);
			window.history.replaceState({}, '', url.toString());
			// Trigger the prefill flow with the resolved programme
			_paceRunPrefillWithProgramme(wf, selectedProg);
		});
		return;
	}

	frappe.call({
		method: 'slcm.pace.web_form.pace_application_form.pace_application_form.validate_new_application_access',
		args: { programme: programme },
		callback: function (r) {
			var res = r && r.message;
			if (res && !res.allowed) {
				_paceApplyPortalLock(wf);
				_paceShowErrorModal(res.message);
			}
		}
	});
	// academic_year is NOT taken from URL — always resolved from the active year on the server

	function applyContextValues() {
		// Resolve programme name from route/slug in URL
		if (programme) {
			frappe.call({
				method: 'slcm.pace.web_form.pace_application_form.pace_application_form.get_programme_by_route',
				args: { route: programme },
				callback: function (r) {
					var resolvedProg = (r && r.message) ? r.message : programme;
					// The Link field's autocomplete control may not be ready yet.
					// Retry until _list is initialised (max ~3 s).
					var attempts = 0;
					var t = setInterval(function () {
						try {
							var ctrl = wf.fields_dict && wf.fields_dict['programme'];
							// _list is the internal awesomplete list; wait for it to exist
							if (ctrl && ctrl.awesomplete && ctrl.awesomplete._list !== undefined) {
								clearInterval(t);
								wf.set_value('programme', resolvedProg);
							} else if (ctrl) {
								// Try a direct set anyway — it may succeed once the field is ready
								wf.set_value('programme', resolvedProg);
								clearInterval(t);
							}
						} catch (err) { /* field not ready yet */ }
						if (++attempts > 30) clearInterval(t);
					}, 100);
				}
			});
		}

		// Always use the active academic year from server shell data (URL no longer carries it)
		var ay = (d && d.active_academic_year);
		if (ay) try { wf.set_value('academic_year', ay); } catch (e) { }
	}

	function fillBase() {
		if (d.first_name) try { wf.set_value('first_name', d.first_name); } catch (e) { }
		if (d.middle_name) try { wf.set_value('middle_name', d.middle_name); } catch (e) { }
		if (d.last_name) try { wf.set_value('last_name', d.last_name); } catch (e) { }
		if (d.email) try { wf.set_value('email_address', d.email); } catch (e) { }
		if (d.full_name) try { wf.set_value('applicant_name', d.full_name); } catch (e) { }
	}

	// First pass
	applyContextValues();
	fillBase();
	try { wf.refresh(); } catch (e) { }

	// 2. Check for existing application
	frappe.call({
		method: 'slcm.pace.web_form.pace_application_form.pace_application_form.check_existing_pace_application',
		args: { programme: programme, academic_year: ((_paceUserData && _paceUserData.active_academic_year) || '') },
		callback: function (r) {
			var res = r && r.message;
			if (!res) return;

			var existing = res.existing;
			var allow_multiple = res.allow_multiple;

			if (existing && existing.name) {
				var p = (window.location.pathname || '').replace(/\/$/, '');
				var isNewRoute = p.indexOf('/new') !== -1;

				// If we are on /new but there is already an application, redirect to it
				if (isNewRoute) {
					var rt = (wf && wf.route) || 'pace-application-form';
					var suffix = (existing.status === 'Draft') ? '/edit' : '';
					window.location.href = '/' + rt + '/' + encodeURIComponent(existing.name) + suffix;
					return;
				}
			}

			// 3. Fallback: Fetch old application (from ANY program) for prefill
			_paceFetchOldPrefill(wf, fillBase, applyContextValues);
		},
		error: function () {
			_paceFetchOldPrefill(wf, fillBase, applyContextValues);
		}
	});

	// Aggressive retry for initial empty fields
	var nRetry = 0;
	var retryT = setInterval(function () {
		applyContextValues();
		fillBase();
		if (++nRetry > 10) clearInterval(retryT);
	}, 1000);
}

// ───────────────────────────────────────────────────────────────────
//  PROGRAMME PICKER — shown when ?programme= is absent on /new
// ───────────────────────────────────────────────────────────────────
/**
 * Shows a programme selection dialog.
 * onConfirm(programmeInternalName) is called once the user picks + confirms.
 * A sticky banner button is rendered so the picker can be re-opened.
 */
function _paceShowProgrammePicker(wf, onConfirm) {
	// Render / show the sticky banner button
	_paceRenderSelectProgrammeButton(wf, onConfirm);

	frappe.call({
		method: 'slcm.pace.web_form.pace_application_form.pace_application_form.get_open_pace_programmes',
		callback: function (r) {
			var programmes = r && r.message ? r.message : [];
			_paceOpenPickerModal(programmes, wf, onConfirm);
		},
		error: function () {
			_paceOpenPickerModal([], wf, onConfirm);
		}
	});
}

function _paceOpenPickerModal(programmes, wf, onConfirm) {
	if (document.getElementById('pace-prog-picker-overlay')) return;

	var primary = getComputedStyle(document.documentElement)
		.getPropertyValue('--pace-primary').trim() || '#1a3c6e';

	// Build option HTML
	var optionsHtml = '<option value="">— Select a Programme —</option>';
	programmes.forEach(function (p) {
		// p may be a string (name) or object; server returns strings (pluck="programme")
		var val = typeof p === 'object' ? (p.name || p) : p;
		var lbl = typeof p === 'object' ? (p.label || p.name || p) : p;
		optionsHtml += '<option value="' + _paceEsc(val) + '">' + _paceEsc(lbl) + '</option>';
	});

	var overlay = document.createElement('div');
	overlay.id = 'pace-prog-picker-overlay';
	overlay.style.cssText = 'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(15,23,42,0.6);backdrop-filter:blur(4px);';

	overlay.innerHTML =
		'<div id="pace-prog-picker-card" style="background:#fff;border-radius:20px;width:min(480px,92vw);padding:36px 32px;box-shadow:0 24px 60px rgba(0,0,0,0.22);position:relative;animation:pacePickerIn 0.3s cubic-bezier(0.16,1,0.3,1)">' +
			'<style>@keyframes pacePickerIn{from{opacity:0;transform:scale(0.94)}to{opacity:1;transform:scale(1)}}</style>' +
			// Icon
			'<div style="width:60px;height:60px;border-radius:50%;background:linear-gradient(135deg,' + primary + ',color-mix(in srgb,' + primary + ' 70%,#000));' +
				'display:flex;align-items:center;justify-content:center;margin:0 auto 20px;box-shadow:0 8px 20px rgba(0,0,0,0.15)">' +
				'<span class="material-symbols-outlined" style="font-size:30px;color:#fff;font-family:\'Material Symbols Outlined\'!important">school</span>' +
			'</div>' +
			// Title
			'<h2 style="font-size:20px;font-weight:700;color:#0f172a;text-align:center;margin:0 0 8px">Choose Your Programme</h2>' +
			'<p style="font-size:14px;color:#64748b;text-align:center;margin:0 0 24px;line-height:1.6">Select the programme you wish to apply for. Once confirmed, this <strong>cannot be changed</strong>.</p>' +
			// Select
			'<div style="margin-bottom:20px">' +
				'<label style="display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:8px">Programme</label>' +
				'<select id="pace-prog-select" style="width:100%;padding:11px 14px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:14px;color:#0f172a;background:#f8fafc;outline:none;cursor:pointer;appearance:auto">' +
					optionsHtml +
				'</select>' +
			'</div>' +
			// Warning box (hidden until selection)
			'<div id="pace-prog-warning" style="display:none;background:#fffbeb;border:1px solid #fcd34d;border-radius:10px;padding:12px 14px;font-size:13px;color:#78350f;margin-bottom:20px;line-height:1.5">' +
				'<strong>⚠ Please confirm:</strong> You are applying for <strong id="pace-prog-warning-name"></strong>. Once you proceed, the programme cannot be changed.' +
			'</div>' +
			// Buttons
			'<div style="display:flex;gap:10px">' +
				'<button id="pace-prog-confirm-btn" style="flex:1;padding:11px;border-radius:10px;border:none;background:' + primary + ';color:#fff;font-size:14px;font-weight:600;cursor:pointer;opacity:0.45;pointer-events:none">Confirm & Proceed</button>' +
			'</div>' +
		'</div>';

	document.body.appendChild(overlay);

	var sel     = document.getElementById('pace-prog-select');
	var warning = document.getElementById('pace-prog-warning');
	var warnName= document.getElementById('pace-prog-warning-name');
	var confirmBtn = document.getElementById('pace-prog-confirm-btn');

	sel.addEventListener('change', function () {
		var chosen = sel.value;
		var chosenLabel = chosen ? sel.options[sel.selectedIndex].text : '';
		if (chosen) {
			warning.style.display = 'block';
			warnName.textContent = chosenLabel;
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
		// Hide the banner button (programme now chosen)
		var btn = document.getElementById('pace-select-prog-banner');
		if (btn) btn.remove();
		onConfirm(chosen);
	});


}

/** Sticky banner button at top of web form — shown when programme not yet chosen. */
function _paceRenderSelectProgrammeButton(wf, onConfirm) {
	if (document.getElementById('pace-select-prog-banner')) return;

	var primary = getComputedStyle(document.documentElement)
		.getPropertyValue('--pace-primary').trim() || '#1a3c6e';

	var banner = document.createElement('div');
	banner.id = 'pace-select-prog-banner';
	banner.style.cssText = 'width:100%;background:#fffbeb;border-bottom:2px solid #fcd34d;padding:14px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px;box-sizing:border-box;';
	banner.innerHTML =
		'<div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0">' +
			'<span class="material-symbols-outlined" style="font-size:22px;color:#b45309;font-family:\'Material Symbols Outlined\'!important;flex-shrink:0">warning</span>' +
			'<span style="font-size:14px;color:#78350f;font-weight:500">No programme selected. Please choose your programme before filling the application.</span>' +
		'</div>' +
		'<button id="pace-select-prog-btn" style="padding:9px 20px;border-radius:8px;border:none;background:' + primary + ';color:#fff;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;flex-shrink:0">Select Programme</button>';

	// Insert at top of the web form container
	var container = document.querySelector('.web-form-container') || document.querySelector('main') || document.body;
	container.insertBefore(banner, container.firstChild);

	document.getElementById('pace-select-prog-btn').addEventListener('click', function () {
		if (document.getElementById('pace-prog-picker-overlay')) return;
		frappe.call({
			method: 'slcm.pace.web_form.pace_application_form.pace_application_form.get_open_pace_programmes',
			callback: function (r) {
				var programmes = r && r.message ? r.message : [];
				_paceOpenPickerModal(programmes, wf, onConfirm);
			}
		});
	});
}

/**
 * Runs the standard prefill flow after the picker resolves a programme.
 * Mirrors the tail of _paceRunPrefill (post !programme guard).
 */
function _paceRunPrefillWithProgramme(wf, programme) {
	var d = _paceUserData;
	if (!d) return;

	// Validate cycle access for the selected programme
	frappe.call({
		method: 'slcm.pace.web_form.pace_application_form.pace_application_form.validate_new_application_access',
		args: { programme: programme },
		callback: function (r) {
			var res = r && r.message;
			if (res && !res.allowed) {
				_paceApplyPortalLock(wf);
				_paceShowErrorModal(res.message);
				return;
			}
			_paceDoPrefill(wf, programme, d);
		}
	});
}

/**
 * Core prefill — sets programme + academic_year + user data.
 * Shared between URL-based and picker-based flows.
 */
function _paceDoPrefill(wf, programme, d) {
	function applyContextValues() {
		if (programme) {
			frappe.call({
				method: 'slcm.pace.web_form.pace_application_form.pace_application_form.get_programme_by_route',
				args: { route: programme },
				callback: function (r) {
					var resolvedProg = (r && r.message) ? r.message : programme;
					var attempts = 0;
					var t = setInterval(function () {
						try {
							var ctrl = wf.fields_dict && wf.fields_dict['programme'];
							if (ctrl) {
								clearInterval(t);
								wf.set_value('programme', resolvedProg);
							}
						} catch (err) { }
						if (++attempts > 30) clearInterval(t);
					}, 100);
				}
			});
		}
		var ay = d && d.active_academic_year;
		if (ay) try { wf.set_value('academic_year', ay); } catch (e) { }
	}

	function fillBase() {
		if (d.first_name) try { wf.set_value('first_name', d.first_name); } catch (e) { }
		if (d.middle_name) try { wf.set_value('middle_name', d.middle_name); } catch (e) { }
		if (d.last_name) try { wf.set_value('last_name', d.last_name); } catch (e) { }
		if (d.email) try { wf.set_value('email_address', d.email); } catch (e) { }
		if (d.full_name) try { wf.set_value('applicant_name', d.full_name); } catch (e) { }
	}

	applyContextValues();
	fillBase();
	try { wf.refresh(); } catch (e) { }

	frappe.call({
		method: 'slcm.pace.web_form.pace_application_form.pace_application_form.check_existing_pace_application',
		args: { programme: programme, academic_year: (d.active_academic_year || '') },
		callback: function (r) {
			var res = r && r.message;
			if (!res) return;
			if (res.existing && res.existing.name) {
				var p = (window.location.pathname || '').replace(/\/$/, '');
				if (p.indexOf('/new') !== -1) {
					var rt = (wf && wf.route) || 'pace-application-form';
					var suffix = (res.existing.status === 'Draft') ? '/edit' : '';
					window.location.href = '/' + rt + '/' + encodeURIComponent(res.existing.name) + suffix;
					return;
				}
			}
			_paceFetchOldPrefill(wf, fillBase, applyContextValues);
		},
		error: function () { _paceFetchOldPrefill(wf, fillBase, applyContextValues); }
	});
}

/** Wrapper for the historical prefill logic */
function _paceFetchOldPrefill(wf, fillBase, applyContextValues) {
	frappe.call({
		method: 'slcm.pace.web_form.pace_application_form.pace_application_form.get_old_pace_application',
		callback: function (r) {
			var oldData = r && r.message;
			var count = 0;
			if (oldData && Object.keys(oldData).length > 0) {
				for (var k in oldData) {
					if (!oldData.hasOwnProperty(k)) continue;
					if (k === 'programme' || k === 'academic_year') continue;
					var val = oldData[k];
					var fd = wf.fields_dict[k];

					// Skip attachments except photo
					if (fd && (fd.df.fieldtype === 'Attach' || fd.df.fieldtype === 'Attach Image') && k !== 'upload_student_photo') continue;

					try {
						var curr = wf.get_value(k);
						if ((curr === null || curr === undefined || curr === '') && val) {
							if (Array.isArray(val) && fd && fd.grid) {
								fd.grid.df.data = val;
								fd.grid.refresh();
								count++;
							} else if (!Array.isArray(val)) {
								wf.set_value(k, val);
								count++;
							}
						}
					} catch (e2) { }
				}
				// if (count > 0) paceShowToast('Form auto-filled from your previous application.', 'success', 5000);
			}
			fillBase();
			applyContextValues();
			try { wf.refresh(); } catch (e) { }
		},
		error: function () {
			fillBase();
			applyContextValues();
			try { wf.refresh(); } catch (e) { }
		}
	});
}





/**
 * Mobile slide-down menu: open/close overlay, bell + logout in drawer, Escape + backdrop close.
 */
function _paceSetupMobileNavDrawer() {
	var overlay = document.getElementById('pace-mobile-nav-overlay');
	var openBtn = document.getElementById('pace-nav-drawer-open');
	var closeBtn = document.getElementById('pace-nav-drawer-close');
	if (!overlay || !openBtn) return;

	function closeDrawer() {
		overlay.classList.remove('is-open');
		overlay.setAttribute('aria-hidden', 'true');
		openBtn.setAttribute('aria-expanded', 'false');
		document.body.style.overflow = '';
		try {
			var m = document.getElementById('adm-avatar-menu');
			if (m) m.style.display = 'none';
		} catch (e) { }
	}

	function openDrawer() {
		overlay.classList.add('is-open');
		overlay.setAttribute('aria-hidden', 'false');
		openBtn.setAttribute('aria-expanded', 'true');
		document.body.style.overflow = 'hidden';
	}

	openBtn.addEventListener('click', function (e) {
		e.stopPropagation();
		openDrawer();
	});
	if (closeBtn) {
		closeBtn.addEventListener('click', function (e) {
			e.stopPropagation();
			closeDrawer();
		});
	}
	overlay.addEventListener('click', function (e) {
		if (e.target === overlay) closeDrawer();
	});
	if (!window._paceMobileDrawerKeybound) {
		window._paceMobileDrawerKeybound = true;
		document.addEventListener('keydown', function (e) {
			var ov = document.getElementById('pace-mobile-nav-overlay');
			if (e.key === 'Escape' && ov && ov.classList.contains('is-open')) {
				var ob = document.getElementById('pace-nav-drawer-open');
				ov.classList.remove('is-open');
				ov.setAttribute('aria-hidden', 'true');
				if (ob) ob.setAttribute('aria-expanded', 'false');
				document.body.style.overflow = '';
			}
		});
	}

	var bellD = document.getElementById('slcm-bell-btn-drawer');
	if (bellD) {
		bellD.addEventListener('click', function () {
			closeDrawer();
			window.location.href = '/merit-and-scholarship/admission_dashboard';
		});
	}
	var loD = document.getElementById('slcm-nav-logout-drawer');
	if (loD) {
		loD.addEventListener('click', function (e) {
			e.preventDefault();
			closeDrawer();
			frappe.confirm('Are you sure you want to logout?<br><small><b>Note:</b> Unsaved changes will be lost. Save as Draft to continue later.</small>', function () {
				frappe.call({
					method: 'logout',	
					callback: function () {
						window.location.href = '/paceadmissions/login#login';
					},
				});
			});
		});
	}

	overlay.querySelectorAll('a.pace-drawer-nav-link[href^="/"]').forEach(function (a) {
		a.addEventListener('click', function () {
			closeDrawer();
		});
	});
}

/**
 * Nav + footer matching slcm/admission/web_form/applicant_form.js _buildShell
 * and slcm/www/admission_base.html (Admission, optional PACE Admission, bell, profile, programme grid footer).
 */
function _paceBuildAdmissionShell(ws, cfg, user, uinfo) {
	if (document.getElementById('slcm-adm-nav')) return;

	var primary       = cfg.primary_color || '#1a3c6e';
	var secondary     = cfg.secondary_color || '#c8a14b';
	var navbarCol     = cfg.navbar_color || '';
	var footerCol     = cfg.footer_color || '';
	var footerTextCol = cfg.footer_text_color || '';
	var btnRadius     = cfg.button_border_radius || '';
	var fHeading      = cfg.font_size_heading || '';
	var fSubheading   = cfg.font_size_subheading || '';
	var fBody         = cfg.font_size_body || '';
	var fFormTitle    = cfg.font_size_form_title || '';
	var fToast        = cfg.font_size_toast || '';
	var fPreset       = cfg.font_size_preset || 'Normal';
	var fontFam       = cfg.font_family || 'System Default';
	var title         = cfg.portal_title || (ws && ws.title) || 'Admissions';
	var logo = cfg.institution_logo || '';
	var isGuest = !user || user === 'Guest';
	var fullName = (uinfo && uinfo.full_name) || user || '';
	var userImg = (uinfo && uinfo.user_image) || '';
	var userEmail = (uinfo && uinfo.email) || '';
	var initLetter = fullName ? fullName[0].toUpperCase() : 'U';
	var programmes = cfg.programmes || [];
	var powerd = cfg.powerd_by || 'boscosoft';
	var paceOn = cfg.pace_enabled ? 1 : 0;

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
		'  --pace-primary: ' + primary + ';',
		'  --pace-secondary: ' + secondary + ';',
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
	varStyle.id = 'pace-theme-vars';
	varStyle.textContent = fontCss + '\n' + rootVars + '\n' + consumerCss + '\n' +
		'.btn-next,.submit-btn,.btn-submit-web-form{background:' +
		primary +
		'!important;border-color:' +
		primary +
		'!important;color:#fff!important;}' +
		'.btn-next:hover,.submit-btn:hover{filter:brightness(1.08)!important;}' +
		'.section-head{color:' +
		primary +
		'!important;}' +
		'.web-form-container .section-head,.web-form .section-head{color:' +
		primary +
		'!important;}';
	document.head.appendChild(varStyle);

	var drawerProfileBlock = isGuest
		? '<div class="pace-mobile-nav-panel__profile pace-mobile-nav-panel__profile--guest">' +
		'<a href="/login" class="adm-nav-login" style="display:inline-flex;align-items:center;background:' +
		primary +
		';color:#fff;padding:10px 22px;border-radius:10px;font-weight:400;font-size:14px;text-decoration:none;">Login / Apply</a></div>'
		: '<div class="pace-mobile-nav-panel__profile">' +
		'<div class="pace-mobile-nav-panel__avatar">' +
		(userImg
			? '<img src="' + _paceEsc(userImg) + '" alt="">'
			: _paceEsc(initLetter)) +
		'</div>' +
		'<div class="pace-mobile-nav-panel__user">' +
		'<div class="pace-mobile-nav-panel__name">' +
		_paceEsc(fullName) +
		'</div>' +
		'<div class="pace-mobile-nav-panel__email">' +
		_paceEsc(userEmail || user) +
		'</div></div>' +
		'<button type="button" id="slcm-bell-btn-drawer" class="pace-mobile-nav-panel__bell" aria-label="Notifications">' +
		'<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
		'<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg></button></div>';

	var drawerNavBlock =
		'<div class="pace-mobile-nav-panel__hr"></div>' +
		(isGuest
			? ''
			: '<a href="javascript:void(0)" id="slcm-nav-logout-drawer" class="pace-drawer-nav-link pace-drawer-nav-link--logout">' +
			'<span class="pace-drawer-nav-link__icon" aria-hidden="true">logout</span><span>Logout</span></a>');

	var drawerHtml =
		'<div class="pace-mobile-nav-panel" role="dialog" aria-modal="true" aria-labelledby="pace-drawer-nav-title">' +
		'<div class="pace-mobile-nav-panel__head">' +
		'<span id="pace-drawer-nav-title" class="pace-mobile-nav-panel__title">' +
		_paceEsc(title) +
		'</span>' +
		'<button type="button" id="pace-nav-drawer-close" class="pace-mobile-nav-panel__close" aria-label="Close menu">×</button>' +
		'</div>' +
		drawerProfileBlock +
		'<nav class="pace-mobile-nav-panel__links" aria-label="Portal">' +
		drawerNavBlock +
		'</nav></div>';

	var nav = document.createElement('nav');
	nav.id = 'slcm-adm-nav';
	nav.className = 'adm-nav';
	nav.innerHTML =
		'<h1 class="adm-nav-brand">' +
		(logo ? '<img src="' + _paceEsc(logo) + '" alt="Logo">' : '') +
		_paceEsc(title) +
		'</h1>' +
		'<button type="button" id="pace-nav-drawer-open" class="pace-nav-drawer-open" aria-label="Open menu" aria-expanded="false">' +
		'<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">' +
		'<path d="M4 6h16M4 12h16M4 18h16"/></svg></button>' +
		'<div class="adm-nav-links adm-nav-links--desktop">' +
		(isGuest
			? '<a href="/login" class="adm-nav-login" style="display:inline-flex;align-items:center;background:' +
			primary +
			';color:#fff;padding:8px 20px;border-radius:8px;font-weight:400;font-size:14px;text-decoration:none;">Login / Apply</a>'
			: '<div style="position:relative;display:flex;align-items:center;gap:10px;">' +
			'<button type="button" id="adm-avatar-btn" onclick="_paceAvatarToggle(event)"' +
			' style="width:38px;height:38px;border-radius:4px;background:rgba(255,255,255,.15);color:#fff;' +
			'border:2px solid rgba(255,255,255,.3);font-weight:400;font-size:15px;cursor:pointer;' +
			'display:flex;align-items:center;justify-content:center;overflow:hidden;">' +
			(userImg
				? '<img src="' +
				_paceEsc(userImg) +
				'" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:4px;">'
				: _paceEsc(initLetter)) +
			'</button>' +
			'<span style="color:#fff;font-size:13px;font-weight:300;opacity:.95;cursor:pointer;" class="nav-hide-mobile" onclick="_paceAvatarToggle(event)">' +
			_paceEsc(fullName) +
			'</span>' +
			'<div id="adm-avatar-menu" style="display:none;position:absolute;right:0;top:calc(100% + 8px);' +
			'min-width:180px;background:#fff;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.14);' +
			'border:1px solid rgba(0,0,0,.07);overflow:hidden;z-index:9999;">' +
			'<div style="padding:12px 16px;border-bottom:1px solid #f1f5f9;">' +
			'<div style="font-size:11px;color:#94a3b8;font-weight:300;letter-spacing:.05em;">Signed in as</div>' +
			'<div style="font-size:13px;color:#1e293b;font-weight:400;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:160px;">' +
			_paceEsc(user) +
			'</div></div>' +
			'<a href="/merit-and-scholarship/admission_dashboard?panel=profile" style="display:flex;align-items:center;gap:10px;padding:12px 16px;text-decoration:none;color:#334155;font-size:14px;font-weight:300;">' +
			'<span style="font-family:\'Material Symbols Outlined\' !important;font-size:18px;color:' +
			primary +
			'">account_circle</span>Profile</a>' +
			'<div style="height:1px;background:#f1f5f9;margin:4px 0;"></div>' +
			'<a href="javascript:void(0)" id="slcm-nav-logout" style="display:flex;align-items:center;gap:10px;padding:12px 16px;text-decoration:none;color:#ef4444;font-size:14px;font-weight:300;">' +
			'<span style="font-family:\'Material Symbols Outlined\' !important;font-size:18px;color:#ef4444">logout</span>Logout</a>' +
			'</div></div>') +
		'</div>';

	document.body.insertBefore(nav, document.body.firstChild);

	var overlayEl = document.createElement('div');
	overlayEl.id = 'pace-mobile-nav-overlay';
	overlayEl.setAttribute('aria-hidden', 'true');
	overlayEl.innerHTML = drawerHtml;
	document.body.appendChild(overlayEl);
	_paceSetupMobileNavDrawer();

	window._paceAvatarToggle = function (e) {
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
			frappe.confirm('Are you sure you want to logout?<br><small><b>Note:</b> Unsaved changes will be lost. Save as Draft to continue later.</small>', function () {
				frappe.call({
					method: 'logout',
					callback: function () {
						window.location.href = '/paceadmissions/login#login';
					},
				});
			});
		});
	}

	var bellBtn = document.getElementById('slcm-bell-btn');
	if (bellBtn) {
		bellBtn.addEventListener('click', function () {
			window.location.href = '/merit-and-scholarship/admission_dashboard';
		});
	}

	var dynColsHtml = '';
	var admCols = cfg.pace_footer || [];
	if (admCols.length > 0) {
		dynColsHtml += '<div class="adm-wf-footer-links" style="grid-column: span 8;flex-grow:1;margin:0 40px;"><div style="display:flex;flex-wrap:wrap;gap:30px;justify-content:flex-start;width:100%;">';
		admCols.forEach(function(col) {
			dynColsHtml += '<div style="min-width:150px;">';
			if (col.title) {
				dynColsHtml += '<h4 style="color:' + (footerTextCol || secondary) + ';font-size:14px;font-weight:400;letter-spacing:.05em;margin:0 0 14px;text-transform:uppercase;">' + _paceEsc(col.title) + '</h4>';
			}
			dynColsHtml += '<ul style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:8px;">';
			if (col.links && col.links.length) {
				col.links.forEach(function(item) {
					if (item.route) {
						var iColor = footerTextCol ? footerTextCol : 'inherit';
						dynColsHtml += '<li><a href="' + _paceEsc(item.route) + '" style="color:' + iColor + ';font-size:14px;text-decoration:none;opacity:0.75;word-break:break-word;">' + _paceEsc(item.label || '') + '</a></li>';
					} else {
						dynColsHtml += '<li><span style="font-size:14px;opacity:0.75;display:inline-block;word-break:break-word;color:' + (footerTextCol || 'inherit') + ';">' + _paceEsc(item.label || '') + '</span></li>';
					}
				});
			}
			dynColsHtml += '</ul></div>';
		});
		dynColsHtml += '</div></div>';
	}

	var socialHtml = '';
	if (cfg.social_links && cfg.social_links.length > 0) {
		socialHtml += '<div style="display:flex;flex-direction:column;align-items:flex-end;min-width:220px;">' +
			'<div style="display:flex;flex-wrap:wrap;gap:12px;width:210px;justify-content:flex-start;">';
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
					socialHtml += '<a href="' + _paceEsc(link.url || '') + '" target="_blank" style="color:' + iColor + '!important;font-size:30px!important;text-decoration:none;transition:transform 0.2s, opacity 0.2s;display:inline-flex;opacity:0.9;" onmouseover="this.style.transform=\'translateY(-3px)\';this.style.opacity=\'1\'" onmouseout="this.style.transform=\'none\';this.style.opacity=\'0.9\'" title="' + _paceEsc(link.platform || '') + '"><i class="' + icon + '"></i></a>';
				}
			}
		});
		socialHtml += '</div></div>';
	}

	var footer = document.createElement('footer');
	footer.id = 'slcm-adm-footer';
	footer.className = 'adm-wf-footer full-bleed-footer';
	
	var title = cfg.portal_title || 'Admissions';
	var powerd = cfg.powerd_by || 'boscosoft';
	var yr = new Date().getFullYear();

	footer.innerHTML =
		'<div class="footer-container">' +
			'<div class="footer-grid" style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:40px;">' +
			// Brand column — school icon + title + tagline
			'<div class="adm-wf-footer-brand" style="min-width:200px;">' +
				'<div style="margin-bottom:16px;display:flex;align-items:flex-start;justify-content:center;">' +
					(cfg.institution_logo
						? '<img src="' + _paceEsc(cfg.institution_logo) + '" style="height:200px;width:200px;object-fit:contain;margin-left:-8px;" alt="Logo" />'
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
				'<p style="margin:0;font-size:13px;color:#64748b;opacity:0.8;">© ' + yr + ' ' + _paceEsc(title) + '. All rights reserved.</p>' +
				'<p style="margin:0;font-size:13px;color:#64748b;opacity:0.8;">Powered by <strong style="color:' + (footerTextCol || secondary) + ';font-weight:400;">' + _paceEsc(powerd) + '</strong></p>' +
			'</div>' +
		'</div>';
	document.body.appendChild(footer);
}

/** Legacy stub — actual prefill is now done by _paceRunPrefill via _paceTriggerPrefill */
function pacePrefillUserDetails(d) {
	_paceUserData = d || _paceUserData;
}


// ───────────────────────────────────────────────────────────────────
//  APPLICATION STATUS BADGE
// ───────────────────────────────────────────────────────────────────
function _paceStatusBadgeClass(status) {
	var base = 'pace-status-badge ';
	if (!status) return base + 'pace-status-other';
	var s = status.toLowerCase();
	if (s === 'draft') return base + 'pace-status-draft';
	if (s === 'submitted') return base + 'pace-status-submitted';
	if (s === 'completed') return base + 'pace-status-submitted';
	return base + 'pace-status-other';
}

function _paceUpdateStatusBadge(status) {
	var badge = document.getElementById('pace-app-status-badge');
	if (!badge) return;
	badge.className = _paceStatusBadgeClass(status);
	badge.textContent = status || '';
	badge.style.display = status ? '' : 'none';

	// Also update parent meta section visibility
	var meta = document.getElementById('pace-app-heading-meta');
	if (meta) {
		meta.style.display = status ? '' : 'none';
	}
}

function paceSetupStatusBadge() {
	if (window._pace_badge_done) return;
	var attempts = 0;
	var t = setInterval(function () {
		attempts++;
		var $title = $(
			'.web-form-wrapper .title-area h1, ' +
			'.web-form-head h1, ' +
			'.page-header h1, ' +
			'.web-form-container .page-title'
		).first();

		if ($title.length && !document.getElementById('pace-app-status-badge')) {
			clearInterval(t);
			window._pace_badge_done = true;

			var titleEl = $title[0];
			var docName = _paceGetDocName();
			var idText = (docName && docName !== 'new' && docName !== 'list') ? docName : (titleEl.textContent || '').replace(/\s+/g, ' ').trim();

			titleEl.textContent = '';
			titleEl.classList.add('pace-app-heading-row');

			var idSpan = document.createElement('span');
			idSpan.id = 'pace-app-heading-id';
			idSpan.textContent = idText;

			var label = document.createElement('span');
			label.style.cssText = 'font-size:13px;font-weight:500;color:#334155;white-space:nowrap;';
			label.textContent = 'Status: ';

			var badge = document.createElement('span');
			badge.id = 'pace-app-status-badge';
			var initStatus = _paceResolveField('status');
			badge.className = _paceStatusBadgeClass(initStatus);
			badge.textContent = initStatus || '';
			badge.style.display = initStatus ? '' : 'none';

			var meta = document.createElement('span');
			meta.id = 'pace-app-heading-meta';
			meta.appendChild(label);
			meta.appendChild(badge);

			// Hide status section if empty (new applications)
			if (!initStatus) {
				meta.style.display = 'none';
			}

			titleEl.appendChild(idSpan);
			titleEl.appendChild(meta);
		}
		if (attempts > 80) clearInterval(t);
	}, 100);
}

// ───────────────────────────────────────────────────────────────────
//  TOP BAR (Back Button + Applying For)
// ───────────────────────────────────────────────────────────────────
var _SVG_BACK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M15 18l-6-6 6-6"/></svg>';

function paceSetupTopBar() {
	if (document.getElementById('pace-form-topbar')) return;

	var $head = $('.web-form-container .web-form-head, .web-form-head, .web-form-header').first();
	if (!$head.length) $head = $('form.web-form, .web-form-container').first();
	if (!$head.length) return;

	var bar = document.createElement('div');
	bar.id = 'pace-form-topbar';

	var left = document.createElement('div');
	left.id = 'pace-form-topbar-left';

	var back = document.createElement('a');
	back.id = 'pace-back-btn';
	back.href = 'javascript:void(0)';
	back.title = 'Back';
	back.innerHTML = _SVG_BACK + '<span>Back</span>';
	back.addEventListener('click', function (e) {
		e.preventDefault();
		history.back();
	});

	var apply = document.createElement('div');
	apply.id = 'pace-applying-for-wrap';
	var prog = _paceResolveField('programme') || '';
	apply.innerHTML = '<span>Applying for:</span> <strong id="pace-applying-for-prog">' + _paceEsc(prog) + '</strong>';
	if (prog) _paceUpdateFormattedProgName(prog);

	var right = document.createElement('div');
	right.id = 'pace-form-topbar-right';

	left.appendChild(back);
	left.appendChild(apply);
	bar.appendChild(left);
	bar.appendChild(right);

	if ($head.is('form')) $head.prepend(bar);
	else $head.before(bar);

	// Sync programme name if it changes (e.g. from prefill)
	setInterval(function () {
		var p = _paceResolveField('programme');
		var el = document.getElementById('pace-applying-for-prog');
		if (p && el && el.getAttribute('data-raw') !== p) {
			el.setAttribute('data-raw', p);
			_paceUpdateFormattedProgName(p);
		}
	}, 1500);
}

function _paceUpdateFormattedProgName(prog) {
	if (!prog) return;
	frappe.call({
		method: 'slcm.pace.web_form.pace_application_form.pace_application_form.get_formatted_programme_name',
		args: { programme: prog },
		callback: function (r) {
			var el = document.getElementById('pace-applying-for-prog');
			if (el && r.message) {
				el.textContent = r.message;
				el.setAttribute('data-raw', prog);
			}
		}
	});
}

// ───────────────────────────────────────────────────────────────────
//  SAVE DRAFT BUTTON
// ───────────────────────────────────────────────────────────────────
var _SVG_SAVE =
	'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">' +
	'<path stroke-linecap="round" stroke-linejoin="round" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"/>' +
	'</svg>';

function _paceDraftBtnHTML(loading) {
	if (loading) {
		return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" ' +
			'style="animation:pace-spin .8s linear infinite">' +
			'<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>' +
			'</svg> Saving\u2026';
	}
	return _SVG_SAVE + ' Save Draft';
}

function paceHandleSaveDraft(opts) {
	var btn = document.getElementById('pace-save-draft-btn');
	if (btn) { btn.disabled = true; btn.innerHTML = _paceDraftBtnHTML(true); }

	var data = _paceCollectDraftData();

	return new Promise(function (resolve, reject) {
		frappe.call({
			method: 'slcm.pace.web_form.pace_application_form.pace_application_form.save_pace_draft',
			args: {
				data: data,
				ignore_mandatory: (opts && opts.ignore_mandatory === false) ? false : true,
				retain_draft_status: (opts && opts.retain_draft_status) ? 1 : 0,
			},
			freeze: false,
			callback: function (r) {
				if (btn) { btn.disabled = false; btn.innerHTML = _paceDraftBtnHTML(false); }
				var msg = r && r.message;
				if (msg && msg.status === 'success') {
					var wf = frappe.web_form;
					// Update URL from /new to /DOCNAME/edit without full reload
					if (msg.name) {
						var p = (window.location.pathname || '').replace(/\/$/, '');
						// Match .../new and .../new/ (Frappe / nginx may normalize differently)
						var isNewPath = p.indexOf('/new') !== -1;
						if (isNewPath) {
							var rt = (wf && wf.route) || 'pace-application-form';
							var newPath = '/' + rt + '/' + encodeURIComponent(msg.name) + '/edit';
							try {
								if (wf && wf.doc) wf.doc.name = msg.name;
								if (wf) { wf.is_new = false; wf.in_edit_mode = true; }
								window.history.replaceState({}, '', newPath);
							} catch (e2) { }
						} else if (wf && wf.doc && !wf.doc.name) {
							wf.doc.name = msg.name;
						}
					}
					var retainDraft = opts && opts.retain_draft_status;
					var promoteSubmitted = opts && opts.ignore_mandatory === false && !retainDraft;
					var savedStatus = promoteSubmitted ? 'Submitted' : 'Draft';
					try { if (wf && wf.doc) wf.doc.status = savedStatus; } catch (e) { }
					window._pace_server_status = savedStatus;
					frappe.form_dirty = false;
					_paceUpdateStatusBadge(savedStatus);
					if (promoteSubmitted && wf) {
						_paceApplyPortalLock(wf);
					}
					if (!(opts && opts.silent)) {
						paceShowToast('\u2713  ' + (msg.message || 'Draft saved successfully.'), 'success');
					}
					resolve(msg);
				} else {
					var errMsg = (msg && msg.message) || 'Could not save draft.';
					if (!(opts && opts.silent)) paceShowToast('\u26a0  ' + errMsg, 'error');
					reject(new Error(errMsg));
				}
			},
			error: function () {
				if (btn) { btn.disabled = false; btn.innerHTML = _paceDraftBtnHTML(false); }
				var e = 'Network error. Could not save draft.';
				if (!(opts && opts.silent)) paceShowToast('\u26a0  ' + e, 'error');
				reject(new Error(e));
			},
		});
	});
}

/** Inject Save Draft button just before the primary Next/Submit button */
function paceSetupSaveDraftButton() {
	_paceInjectCSS();
	setInterval(function () {
		if (document.getElementById('pace-save-draft-btn')) return;
		if (_pacePortalLocked()) return; // don't show on submitted forms

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
			var $btn = $('<button type="button" id="pace-save-draft-btn"></button>');
			$btn.html(_paceDraftBtnHTML(false));
			$btn.on('click', function (e) {
				e.preventDefault();
				paceHandleSaveDraft();
			});
			var $discard = $('.web-form-footer .right-area .discard-btn').first();
			if ($discard.length) {
				$discard.before($btn);
			} else {
				$primary.before($btn);
			}
		}
	}, 500);
}

/** Confirmation for Discard button - uses capture phase to intercept before Frappe handlers */
function paceSetupDiscardConfirmation() {
	if (window._pace_discard_hooked) return;
	window._pace_discard_hooked = true;

	document.body.addEventListener('click', function (e) {
		var btn = e.target.closest('.discard-btn');
		if (!btn) return;

		// If already confirmed, let the second click (triggered programmatically) proceed
		if (btn.getAttribute('data-confirmed') === 'true') {
			return;
		}

		// Prevent Frappe's default behavior and navigation
		e.preventDefault();
		e.stopImmediatePropagation();

		frappe.confirm(
			__('Do you want to clear your application and start afresh?'),
			function () {
				btn.setAttribute('data-confirmed', 'true');
				btn.click();
			}
		);
	}, true); // true = capture phase
}

// ───────────────────────────────────────────────────────────────────
//  SUBMISSION & PAYMENT
// ───────────────────────────────────────────────────────────────────

function _paceShowLoading(msg) {
	if (document.getElementById('pace-loading')) return;
	var div = document.createElement('div');
	div.id = 'pace-loading';
	div.className = 'pace-loading-overlay';
	div.innerHTML = '<div class="maroon-dots"><span class="maroon-dot"></span><span class="maroon-dot"></span><span class="maroon-dot"></span></div><div class="pace-loading-text">' + _paceEsc(msg || 'Please wait...') + '</div>';
	document.body.appendChild(div);
}

function _paceHideLoading() {
	var el = document.getElementById('pace-loading');
	if (el) el.remove();
}

/** Best-effort message from a failed frappe.call response (server exception or network). */
function _paceErrFromCall(r) {
	if (!r) return __('Request failed.');
	try {
		if (r._server_messages) {
			var parsed = JSON.parse(r._server_messages);
			if (Array.isArray(parsed) && parsed.length) {
				var inner = typeof parsed[0] === 'string' ? JSON.parse(parsed[0]) : parsed[0];
				if (inner && inner.message) return String(inner.message);
			}
		}
	} catch (e1) { /* ignore */ }
	if (r.exc) {
		var s = String(r.exc);
		var lines = s.split('\n').map(function (x) { return x.trim(); }).filter(Boolean);
		for (var i = lines.length - 1; i >= 0; i--) {
			var line = lines[i];
			if (line.indexOf('File ') === 0) continue;
			if (line.indexOf('Traceback') !== -1) continue;
			return line.length > 400 ? line.slice(0, 400) + '\u2026' : line;
		}
		return s.slice(0, 400);
	}
	if (typeof r.message === 'string' && r.message) return r.message;
	return __('Request failed.');
}

function _paceLoadRazorpay(callback) {
	if (typeof Razorpay !== 'undefined') {
		callback();
		return;
	}
	var sc = document.createElement('script');
	sc.src = 'https://checkout.razorpay.com/v1/checkout.js';
	sc.onload = callback;
	sc.onerror = function () {
		_paceHideLoading();
		paceShowToast('Payment gateway script failed to load. Please refresh.', 'error');
	};
	document.head.appendChild(sc);
}

var _paceGatewayCloseInFlight = false;

/**
 * Save application as Submitted with server-side mandatory validation.
 * Used on fee-modal Cancel and before opening Razorpay (Proceed to Payment).
 */
function _paceSaveSubmittedWithValidation(opts) {
	opts = opts || {};
	return paceHandleSaveDraft({
		ignore_mandatory: false,
		retain_draft_status: false,
		silent: opts.silent !== false,
	});
}

/** Log Razorpay dismiss/failure on server; optional toast + page reload. */
function _pacePayLaterAfterGatewayClose(applicationName, assignmentName, orderId, errorData, reloadPage) {
	if (_paceGatewayCloseInFlight) return;
	_paceGatewayCloseInFlight = true;
	_paceShowLoading(__('Saving...'));
	frappe.call({
		method: 'slcm.pace.web_form.pace_application_form.pace_application_form.log_pace_payment_gateway_closed',
		args: {
			application_name: applicationName,
			assignment_name: assignmentName,
			order_id: orderId || '',
			error_data: errorData || { event: 'modal_dismissed', message: __('User closed the payment modal') },
			finalize_application: 0,
		},
		callback: function () {
			_paceHideLoading();
			_paceGatewayCloseInFlight = false;
			if (reloadPage) {
				paceShowToast(__('Payment was not completed.'), 'info', 4000);
				setTimeout(function () { window.location.reload(); }, 1500);
			}
		},
		error: function () {
			_paceHideLoading();
			_paceGatewayCloseInFlight = false;
			if (reloadPage) {
				paceShowToast(__('Payment was not completed.'), 'info', 4000);
				setTimeout(function () { window.location.reload(); }, 1500);
			}
		},
	});
}

/** After validated Submitted save: toast + reload (fee modal Cancel). */
function _paceFinishSubmittedPayLater() {
	paceShowToast(__('Application submitted. You can pay the fee later.'), 'success', 4000);
	setTimeout(function () { window.location.reload(); }, 1500);
}

/**
 * Open Razorpay checkout with shared dismiss / failure handling.
 * opts: { res, applicationName, wf, theme, name, description, onVerifySuccess }
 */
function _paceOpenRazorpayCheckout(opts) {
	var res = opts.res;
	var wf = opts.wf;
	var applicationName = opts.applicationName;
	if (!res || !res.order_id || !res.key_id || !applicationName || !res.assignment) {
		paceShowToast(__('Payment session could not be created.'), 'error', 8000);
		return;
	}

	var paymentHandled = false;
	var prefill = opts.prefill || {};
	if (wf) {
		prefill.name = (wf.get_value('first_name') || '') + ' ' + (wf.get_value('last_name') || '');
		prefill.email = wf.get_value('email_address') || prefill.email || '';
		prefill.contact = wf.get_value('mobile_number') || prefill.contact || '';
	}
	if (window._paceUserData && !prefill.name) {
		prefill.name = window._paceUserData.full_name || '';
		prefill.email = window._paceUserData.email || prefill.email || '';
	}

	var options = {
		key: res.key_id,
		amount: res.amount,
		currency: res.currency || 'INR',
		order_id: res.order_id,
		name: opts.name || 'PACE Application Fee',
		description: opts.description || 'Application Registration Fee',
		prefill: prefill,
		theme: opts.theme || { color: '#7B1D1D' },
		modal: {
			ondismiss: function () {
				if (paymentHandled) return;
				_pacePayLaterAfterGatewayClose(
					applicationName,
					res.assignment,
					res.order_id,
					{ event: 'modal_dismissed', message: __('User closed the payment modal') },
					true
				);
			},
		},
		handler: function (resp) {
			paymentHandled = true;
			var preventNavigation = function (e) {
				e.preventDefault();
				e.returnValue = 'Payment is being verified. Please do not refresh or leave this page.';
				return e.returnValue;
			};
			window.addEventListener('beforeunload', preventNavigation);

			_paceShowLoading(__('Verifying Payment… Please don\'t refresh or close this page or go back.'));
			frappe.call({
				method: 'slcm.pace.web_form.pace_application_form.pace_application_form.verify_pace_payment_signature',
				args: {
					razorpay_payment_id: resp.razorpay_payment_id,
					razorpay_order_id: resp.razorpay_order_id,
					razorpay_signature: resp.razorpay_signature,
					assignment_name: res.assignment,
				},
				callback: function (vr) {
					window.removeEventListener('beforeunload', preventNavigation);
					_paceHideLoading();
					if (vr.message && vr.message.status === 'success') {
						if (typeof opts.onVerifySuccess === 'function') {
							opts.onVerifySuccess(vr);
						} else {
							paceRenderSuccessPage();
						}
					} else {
						var err = (vr.message && vr.message.message) || __('Verification failed.');
						paceShowToast(String(err), 'error', 8000);
					}
				},
				error: function () {
					_paceHideLoading();
					paceShowToast(__('Verification request failed. Please reload or contact support.'), 'error', 8000);
				},
			});
		},
	};

	try {
		var rzp = new Razorpay(options);
		rzp.on('payment.failed', function (failResp) {
			if (paymentHandled) return;
			paymentHandled = true; // Prevent ondismiss from also firing duplicate UI actions
			var err = (failResp && failResp.error) || failResp;
			var errMsg = (err && (err.description || err.reason)) || __('Payment failed.');
			_pacePayLaterAfterGatewayClose(applicationName, res.assignment, res.order_id, err || failResp, false);
			paceShowToast(String(errMsg), 'error', 8000);
		});
		rzp.open();
	} catch (rzpErr) {
		var rzpMsg = (rzpErr && rzpErr.message) ? String(rzpErr.message) : String(rzpErr);
		paceShowToast(__('Could not open payment window.') + ' ' + rzpMsg, 'error', 8000);
	}
}

function _paceShowSubmissionDialog() {
	var status = (_paceResolveField('status') || '').trim();
	var wf = window.frappe && frappe.web_form;
	if (!wf) return;

	// On a NEW form, status is empty string '' (not yet saved).
	// Treat '' and 'Draft' the same — show the payment dialog.
	// Only non-draft statuses (Submitted, Under Verification, etc.) go to _paceFinalSubmit.
	var isDraftOrNew = !status || status === 'Draft' || status === 'Returned for Correction';
	if (!isDraftOrNew) {
		_paceFinalSubmit();
		return;
	}

	function _paceShowConfirmModal(fee, currency, programme, onConfirm, docname) {
		if (document.getElementById('pace-confirm-modal')) return;

		var overlay = document.createElement('div');
		overlay.id = 'pace-confirm-modal';
		overlay.className = 'pace-modal-overlay';

		var amtStr = format_currency(fee, currency || 'INR', 0);

		overlay.innerHTML =
			'<div class="pace-modal">' +
			'<div class="pace-modal-icon">' +
			'<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h12M6 8h12m-12 5 8.5 8M6 13h3c6.667 0 6.667-10 0-10"/></svg>' +
			'</div>' +
			'<div class="pace-modal-title">Confirm Application Completion</div>' +
			'<div class="pace-modal-text">You are about to complete your application for <strong>' + _paceEsc(programme) + '</strong>. Please review the fee details below.</div>' +
			'<div class="pace-fee-card">' +
			'<div class="pace-fee-label">Application Fee</div>' +
			'<div class="pace-fee-amount">' + amtStr + '</div>' +
			'</div>' +
			'<div class="pace-modal-actions">' +
			'<button class="pace-btn-pay" id="pace-modal-confirm-btn">' +
			'<span>Proceed to Payment</span>' +
			'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>' +
			'</button>' +
			'<button class="pace-btn-cancel" id="pace-modal-close-btn">Cancel</button>' +
			'</div>' +
			'</div>';

		document.body.appendChild(overlay);

		overlay.querySelector('#pace-modal-confirm-btn').onclick = function () {
			overlay.remove();
			onConfirm();
		};
		overlay.querySelector('#pace-modal-close-btn').onclick = function () {
			overlay.remove();
			_paceShowLoading(__('Saving...'));
			_paceSaveSubmittedWithValidation({ silent: true })
				.then(function () {
					_paceHideLoading();
					_paceFinishSubmittedPayLater();
				})
				.catch(function (err) {
					_paceHideLoading();
					paceShowToast(
						(err && err.message) ? String(err.message) : __('Could not save application. Check required fields.'),
						'error',
						8000
					);
				});
		};
	}

	var prog = wf.get_value('programme');
	_paceShowLoading(__('Processing Application...'));

	// Step 1: Validate + persist; stay Draft until user pays or chooses pay-later
	paceHandleSaveDraft({ ignore_mandatory: false, retain_draft_status: true, silent: true }).then(function (savedMsg) {
		var docname = (savedMsg && savedMsg.name) || (wf && wf.doc && wf.doc.name) || _paceGetDocName();
		if (!docname) {
			_paceHideLoading();
			paceShowToast(__('Could not save application. Please try again.'), 'error', 8000);
			return;
		}
		try { if (wf && wf.doc) wf.doc.name = docname; } catch (e) {}

		// Step 2: Fetch the fee
		_paceShowLoading(__('Calculating Fee...'));
		frappe.call({
			method: 'slcm.pace.web_form.pace_application_form.pace_application_form.get_pace_admission_fee',
			args: {
				application: {
					programme: prog,
					academic_year: wf.get_value('academic_year'),
					nationality: wf.get_value('nationality')
				}
			},
			callback: function (r) {
				_paceHideLoading();
				if (r && r.exc) {
					paceShowToast(_paceErrFromCall(r), 'error', 8000);
					return;
				}
				var fee = (r.message && r.message.fee) || 0;

				// Step 3: Show modal — docname already exists in closure from Step 1
				_paceShowConfirmModal(fee, 'INR', prog, function () {
					_paceShowLoading(__('Saving application...'));
					_paceSaveSubmittedWithValidation({ silent: true })
						.then(function () {
							try {
								if (wf && wf.doc) wf.doc.status = 'Submitted';
							} catch (e) { }
							_paceUpdateStatusBadge('Submitted');
							_paceShowLoading(__('Opening Payment Gateway...'));
							_paceStartRazorpayForApplication(docname, wf);
						})
						.catch(function (err) {
							_paceHideLoading();
							paceShowToast(
								(err && err.message) ? String(err.message) : __('Could not save application. Check required fields.'),
								'error',
								8000
							);
						});
				});
			},
			error: function () {
				_paceHideLoading();
				paceShowToast(__('Could not load fee. Check your connection and try again.'), 'error');
			}
		});
	}).catch(function (err) {
		_paceHideLoading();
		paceShowToast(
			(err && err.message) ? String(err.message) : __('Could not save application. Check required fields.'),
			'error',
			8000
		);
	});
}

/** Start Razorpay after application is saved as Submitted. */
function _paceStartRazorpayForApplication(docname, wf) {
	setTimeout(function () {
		frappe.call({
			method: 'slcm.pace.web_form.pace_application_form.pace_application_form.initiate_pace_razorpay_order',
			args: { application_name: docname },
			callback: function (r2) {
				if (r2 && r2.exc) {
					_paceHideLoading();
					paceShowToast(_paceErrFromCall(r2), 'error', 8000);
					return;
				}
				var res = r2.message;
				if (res && (res.status === 'free' || res.status === 'already_paid')) {
					_paceHideLoading();
					paceShowToast(res.message || __('Application submitted.'), 'success');
					setTimeout(function () { window.location.reload(); }, 1500);
					return;
				}
				if (res && res.status === 'error') {
					_paceHideLoading();
					paceShowToast(String(res.message || __('Payment could not be started.')), 'error', 8000);
					return;
				}
				_paceShowLoading(__('Gateway Opening...'));
				if (!res || !res.order_id || !res.key_id) {
					_paceHideLoading();
					paceShowToast(
						__('Payment session could not be created (missing order or gateway key). Contact support.'),
						'error',
						8000
					);
					return;
				}
				_paceLoadRazorpay(function () {
					_paceHideLoading();
					if (typeof Razorpay === 'undefined') {
						paceShowToast(__('Payment checkout failed to load. Refresh the page and try again.'), 'error');
						return;
					}
					_paceOpenRazorpayCheckout({
						res: res,
						applicationName: docname,
						wf: wf,
						theme: { color: '#7B1D1D' },
					});
				});
			},
			error: function (xhr) {
				_paceHideLoading();
				var extra = xhr && xhr.responseJSON && xhr.responseJSON._server_messages
					? _paceErrFromCall(xhr.responseJSON)
					: '';
				paceShowToast(extra || __('Could not contact the server to start payment.'), 'error', 8000);
			},
		});
	}, 0);
}

function _paceFinalSubmit() {
	// Hidden submit for non-payment cases
	_paceShowLoading(__('Submitting Application...'));
	_paceSaveSubmittedWithValidation({ silent: false }).then(function () {
		_paceHideLoading();
		window.location.reload();
	}).catch(function () { _paceHideLoading(); });
}

function paceSetupSubmission() {
	var wf = window.frappe && frappe.web_form;
	if (!wf) return;

	$(document).off('click.paceSubmit').on('click.paceSubmit', '.btn-submit-web-form, .submit-btn', function (e) {
		if (_pacePortalLocked()) return;
		e.preventDefault();
		e.stopImmediatePropagation();

		if (!wf.get_value('acknowledge_check') || !wf.get_value('understand_check') || !wf.get_value('communication_check')) {
			paceShowToast(__('You must agree to all declarations before submitting.'), 'error');
			return false;
		}
		var allPages = _paceValidateAllPages(wf);
		if (!allPages.ok) {
			var baseSubmit = __('Please fill all required fields before submitting.');
			if (allPages.missing && allPages.missing.length && typeof frappe !== 'undefined' && frappe.msgprint) {
				frappe.msgprint({
					title: __('Required fields'),
					message:
						_paceEsc(baseSubmit) +
						'<br><br><ul><li>' +
						allPages.missing.map(function (lab) { return _paceEsc(lab); }).join('</li><li>') +
						'</li></ul>',
					indicator: 'red',
				});
			} else {
				paceShowToast(baseSubmit, 'error', 6500);
			}
			return false;
		}
		_paceShowSubmissionDialog();
	});
}

function paceSetupReadonlyLogic() {
	var wf = window.frappe && frappe.web_form;
	if (!wf) return;

	var runLogic = function () {
		paceInjectAttachFieldLabels();
		var status = _paceResolveApplicationStatus();
		var docname = _paceGetDocName();

		if (!status && docname && docname !== 'new' && docname !== 'list') {
			if (!window._pace_status_fetching) {
				window._pace_status_fetching = true;
				_paceRefreshApplicationStatusFromServer(function (s) {
					window._pace_status_fetching = false;
					runLogicWithStatus(s);
				});
			}
			return;
		}
		runLogicWithStatus(status);
	};

	function runLogicWithStatus(raw_status) {
		var status_obj = (typeof raw_status === 'object') ? raw_status : (window._pace_server_status_obj || { status: raw_status });
		var status = (status_obj.status || '').trim().toLowerCase();
		if (!status) return;

		var is_locked = _pacePortalLocked(status_obj.status);
		if (status_obj.admission_closed) {
			is_locked = true;
			if (!window._pace_admission_closed_shown && status_obj.admission_closed_message) {
				window._pace_admission_closed_shown = true;
				frappe.msgprint({
					title: __('Admission Closed'),
					message: status_obj.admission_closed_message,
					indicator: 'orange'
				});
			}
		}

		if (is_locked) {
			_paceApplyPortalLock(wf);
			var blockRedirect =
				document.getElementById('pace-confirm-modal') ||
				document.querySelector('.razorpay-container') ||
				document.getElementById('pace-loading');
			if (!blockRedirect) {
				var path = window.location.pathname;
				if (path.indexOf('/edit') !== -1) {
					window.location.href = path.replace(/\/edit\/?$/, '');
					return;
				}
			}
		} else if (status === 'returned for correction') {
			var DOC_FIELDS = ['student_signature', 'ug_degree_certificate', 'govt_id', 'upload_student_photo'];

			$('.submit-btn, .btn-submit-web-form, .btn-primary[type="submit"]').hide();
			$('#pace-save-draft-btn').text('Save Changes').show();

			// 1. ALWAYS lock everything first to counter Frappe re-renders
			(wf.fields || []).forEach(f => { if (f.fieldname) wf.set_df_property(f.fieldname, 'read_only', 1); });
			$('.web-form input, .web-form select, .web-form textarea').attr('disabled', 'disabled').css('cursor', 'not-allowed');

			if (window._pace_restricted_done && window._pace_allowed_fields) {
				// 2. ALWAYS Re-apply selective unlock from cached list every interval tick
				window._pace_allowed_fields.forEach(f => {
					wf.set_df_property(f, 'read_only', 0);
					var $ctrl = $('[data-fieldname="' + f + '"]');
					$ctrl.find('input, select, textarea').removeAttr('disabled').css('cursor', '');
					$ctrl.find('.btn-attach, .btn-remove, .reload-file, .btn-file-reload').show();
				});
				return;
			}

			if (window._pace_fetching_restricted) return;
			window._pace_fetching_restricted = true;

			frappe.call({
				method: 'slcm.pace.web_form.pace_application_form.pace_application_form.get_restricted_fields',
				args: { application_name: _paceGetDocName() },
				callback: function (r) {
					window._pace_allowed_fields = (r.message || []).filter(f => DOC_FIELDS.indexOf(f) !== -1);
					window._pace_restricted_done = true;
					window._pace_fetching_restricted = false;
				}
			});
		}
	}

	setTimeout(runLogic, 600);
	setInterval(runLogic, 1000);
	_paceRefreshApplicationStatusFromServer();
}

// ───────────────────────────────────────────────────────────────────
//  RECEIPT BUTTON
// ───────────────────────────────────────────────────────────────────
function paceSetupReceiptButton() {
	setInterval(function () {
		if (document.getElementById('pace-receipt-btn')) return;
		var status = _paceResolveField('status');
		if (!status || status === 'Draft' || status === 'Submitted') return;

		var $actions = $('#pace-form-topbar-right');
		if ($actions.length) {
			var btn = $('<button id="pace-receipt-btn"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right:2px;"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg> Download Receipt</button>');
			btn.on('click', function () {
				var docname = _paceGetDocName();
				paceShowToast(__('Generating receipt\u2026'), 'info');
				frappe.call({
					method: 'slcm.pace.web_form.pace_application_form.pace_application_form.generate_pace_receipt',
					args: { application_name: docname },
					callback: function (r) {
						var receipt_name = r.message;
						if (receipt_name) {
							frappe.call({
								method: 'slcm.pace.web_form.pace_application_form.pace_application_form.get_pace_admission_fee',
								args: { application: docname },
								callback: function (r2) {
									var template = (r2.message && r2.message.template) || 'PACE Payment Reciept';
									var url = '/api/method/frappe.utils.print_format.download_pdf?' +
										'doctype=PACE%20Receipt&name=' + encodeURIComponent(receipt_name) +
										'&format=' + encodeURIComponent(template) + '&no_letterhead=0';
									window.open(url, '_blank');
								}
							});
						} else {
							paceShowToast(__('Receipt not found. If you just paid, please wait or reload.'), 'error');
						}
					}
				});
			});
			$actions.append(btn);
		}
	}, 2000);
}

function paceSetupPayButton() {
	setInterval(function () {
		if (document.getElementById('pace-pay-btn')) return;
		var status = _paceResolveField('status');
		if (status !== 'Submitted') return;

		var $actions = $('#pace-form-topbar-right');
		if ($actions.length) {
			var btn = $('<button id="pace-pay-btn" class="pace-btn-pay" style="padding: 7px 14px; font-size: 13px;">Pay Application Fee</button>');
			btn.on('click', function () {
				_paceShowLoading(__('Initiating Payment...'));
				var docname = _paceGetDocName();
				frappe.call({
					method: 'slcm.pace.web_form.pace_application_form.pace_application_form.initiate_pace_razorpay_order',
					args: { application_name: docname },
					callback: function (r2) {
						if (r2 && r2.exc) {
							_paceHideLoading();
							paceShowToast(_paceErrFromCall(r2), 'error', 8000);
							return;
						}
						var res = r2.message;
						if (res && (res.status === 'free' || res.status === 'already_paid')) {
							_paceHideLoading();
							paceShowToast(res.message || __('Application submitted.'), 'success');
							setTimeout(function () { window.location.reload(); }, 1500);
							return;
						}
						if (res && res.status === 'error') {
							_paceHideLoading();
							paceShowToast(String(res.message || __('Payment could not be started.')), 'error', 8000);
							return;
						}
						_paceShowLoading(__('Gateway Opening...'));
						if (!res || !res.order_id || !res.key_id) {
							_paceHideLoading();
							paceShowToast(__('Payment session could not be created.'), 'error', 8000);
							return;
						}
						_paceLoadRazorpay(function () {
							_paceHideLoading();
							if (typeof Razorpay === 'undefined') {
								paceShowToast(__('Payment checkout failed to load. Refresh the page and try again.'), 'error');
								return;
							}
							_paceOpenRazorpayCheckout({
								res: res,
								applicationName: docname,
								name: 'Application Fee',
								description: 'Application Fee Payment - PACE application to complete application step.',
								theme: { color: window._paceUserData ? window._paceUserData.primary_color : '#1a3c6e' }
							});
						});
					}
				});
			});
			$actions.prepend(btn);
		}
	}, 2000);
}

// ───────────────────────────────────────────────────────────────────
//  STEPPER — VALIDATION HELPERS (mirrors applicant_form.js logic)
// ───────────────────────────────────────────────────────────────────

/** Layout-only fieldtypes do not hold a value; reqd on them is a config error. */
function _paceIsLayoutFieldtype(ft) {
	if (!ft) return false;
	var layout = {
		'Section Break': 1, 'Column Break': 1, 'Page Break': 1,
		'Tab Break': 1, HTML: 1, Fold: 1, Heading: 1, Button: 1
	};
	return !!layout[ft];
}

/** Is an Attach / Attach Image field empty? */
function _paceAttachValueEmpty(val) {
	if (val === undefined || val === null) return true;
	if (typeof val === 'string' && !String(val).trim()) return true;
	return false;
}

/** Is a required Check field unchecked (Frappe is_null(0) is false so core misses it)? */
function _paceCheckUnchecked(val) {
	var n = typeof cint === 'function' ? cint(val) : (val ? 1 : 0);
	return !n;
}

/**
 * Skip forward validation when the form is locked / view-only / allows incomplete saves.
 * Mirrors _slcmStepperSkipForwardValidation from applicant_form.js.
 */
function _paceSkipForwardValidation(wf) {
	if (!wf) return true;
	if (wf.allow_incomplete) return true;
	if (wf.in_view_mode) return true;
	return false;
}

function _paceUgRowIsBlank(row) {
	if (!row || typeof row !== 'object') return true;
	return ['institution_name', 'university', 'programme_studied', 'year_of_passing', 'result_status'].every(function (k) {
		var v = row[k];
		if (v === undefined || v === null || v === '') return true;
		if (typeof v === 'string' && !String(v).trim()) return true;
		if (k === 'year_of_passing') {
			var n = parseInt(v, 10);
			return !n || isNaN(n);
		}
		return false;
	});
}

/**
 * Validate PACE UG Degree child rows (web forms often skip child reqd in client checks).
 * Returns { ok: boolean, missing: string[] }.
 */
function _paceValidateUgDegreeRows(wf) {
	var missing = [];
	var raw = [];
	try {
		var g = wf.fields_dict.ug_degree && wf.fields_dict.ug_degree.grid;
		if (g && typeof g.get_data === 'function') {
			raw = g.get_data() || [];
		}
	} catch (e1) { }
	if (!raw || !raw.length) {
		try {
			raw = (wf.get_value && wf.get_value('ug_degree')) || (wf.doc && wf.doc.ug_degree) || [];
		} catch (e2) {
			raw = [];
		}
	}
	if (!Array.isArray(raw)) raw = [];
	var rows = raw.filter(function (r) { return !_paceUgRowIsBlank(r); });

	if (!rows.length) {
		missing.push(__('UG Degree Details: Please add at least one UG degree entry'));
		return { ok: false, missing: missing };
	}

	function rowVal(r, k) {
		var v = r[k];
		if (v === undefined || v === null) return '';
		if (typeof v === 'string') return v.trim();
		return v;
	}
	function isEmpty(v) {
		return v === '' || v === null || v === undefined;
	}

	rows.forEach(function (row, idx) {
		var n = idx + 1;
		if (isEmpty(rowVal(row, 'institution_name'))) {
			missing.push(__('UG Degree row {0}: Institution Name is required', [String(n)]));
		}
		if (isEmpty(rowVal(row, 'university'))) {
			missing.push(__('UG Degree row {0}: University is required', [String(n)]));
		}
		if (isEmpty(rowVal(row, 'programme_studied'))) {
			missing.push(__('UG Degree row {0}: Programme Studied is required', [String(n)]));
		}
		var yp = rowVal(row, 'year_of_passing');
		if (isEmpty(yp) || parseInt(yp, 10) <= 0 || isNaN(parseInt(yp, 10))) {
			missing.push(__('UG Degree row {0}: Year of Passing is required', [String(n)]));
		}
		var rs = rowVal(row, 'result_status');
		if (isEmpty(rs)) {
			missing.push(__('UG Degree row {0}: Result Status is required', [String(n)]));
		}
		if (rs === 'Declared') {
			if (isEmpty(rowVal(row, 'marking_scheme'))) {
				missing.push(
					__('UG Degree row {0}: Marking Scheme is required when Result is Declared', [String(n)])
				);
			}
			var pct = rowVal(row, 'obtained_percentagecgpa');
			if (isEmpty(pct) && pct !== 0 && pct !== '0') {
				missing.push(
					__(
						'UG Degree row {0}: Obtained Percentage/CGPA is required when Result is Declared',
						[String(n)]
					)
				);
			} else {
				var ms = rowVal(row, 'marking_scheme');
				var num = parseFloat(pct);
				if (!isNaN(num)) {
					if (ms === 'Percentage' && num > 100) {
						missing.push(__('UG Degree row {0}: Obtained Percentage cannot exceed 100', [String(n)]));
					} else if (ms === 'CGPA' && num > 10) {
						missing.push(__('UG Degree row {0}: CGPA cannot exceed 10', [String(n)]));
					}
				}
			}
		}
	});

	try {
		var $ug = $('[data-fieldname="ug_degree"]').first();
		if (missing.length) {
			$ug.find('.grid-row, .form-control, .input-with-feedback').addClass('pace-field-error');
		} else {
			$ug.find('.pace-field-error').removeClass('pace-field-error');
		}
	} catch (e3) { }

	return { ok: missing.length === 0, missing: missing };
}

/** Run _paceValidateStage on every form page (used before final submit). */
function _paceValidateAllPages(wf) {
	if (!wf) return { ok: true, missing: [] };
	var missing = [];
	$('.web-form .form-layout > .form-page').each(function () {
		var check = _paceValidateStage(wf, $(this));
		if (!check.ok) missing = missing.concat(check.missing);
	});
	return { ok: missing.length === 0, missing: missing };
}

/**
 * Validate all required (and conditionally-required) fields on $page.
 * Returns { ok: boolean, missing: string[] }.
 * Mirrors _validateStage from applicant_form.js.
 */
function _paceValidateStage(wf, $page) {
	var missing = [];
	var seen = {};

	$page.find('[data-fieldname]').each(function () {
		var fieldname = $(this).attr('data-fieldname');
		if (!fieldname || seen[fieldname]) return;
		seen[fieldname] = true;

		var fw = wf.fields_dict[fieldname];
		if (!fw) return;

		var df = fw.df;
		if (_paceIsLayoutFieldtype(df.fieldtype)) return;

		var required = df.reqd;

		// Evaluate mandatory_depends_on expression
		if (!required && df.mandatory_depends_on) {
			try {
				var expr = df.mandatory_depends_on.replace(/^eval:/, '');
				// eslint-disable-next-line no-new-func
				required = !!(new Function('doc', 'return (' + expr + ')')(wf.doc));
			} catch (e) { /* ignore eval errors */ }
		}

		if (!required) return;
		if (fw.$wrapper && fw.$wrapper.is(':hidden')) return;

		var val = wf.get_value(fieldname);
		var errSel = '.form-control,.attached-file,.input-with-feedback,.btn-attach,.control-value,input[type="checkbox"],.checkbox';

		// DOB age check (≥ 17)
		if (fieldname === 'date_of_birth' && val && df.fieldtype === 'Date') {
			var age = _paceAgeYears(val);
			if (age === null || age < 17) {
				fw.$wrapper && fw.$wrapper.find(errSel).addClass('pace-field-error');
				missing.push((df.label || fieldname).trim() + ': must be at least 17 years old');
				return;
			}
		}

		var empty;
		if (df.fieldtype === 'Check') {
			empty = _paceCheckUnchecked(val);
		} else if (df.fieldtype === 'Attach' || df.fieldtype === 'Attach Image') {
			empty = _paceAttachValueEmpty(val);
		} else {
			empty = val === undefined || val === null || val === '' || (Array.isArray(val) && val.length === 0);
		}

		if (empty) {
			fw.$wrapper && fw.$wrapper.find(errSel).addClass('pace-field-error');
			missing.push((df.label || fieldname).trim() || fieldname);
		} else {
			fw.$wrapper && fw.$wrapper.find(errSel).removeClass('pace-field-error');
		}
	});

	// Child table: UG degree — required columns (web form grid does not surface child reqd to $page scan above)
	var pageHasUGTable = $page.find('[data-fieldname="ug_degree"]').length > 0;
	if (pageHasUGTable) {
		var ugCheck = _paceValidateUgDegreeRows(wf);
		if (!ugCheck.ok) {
			missing = missing.concat(ugCheck.missing);
		}
	}

	return { ok: missing.length === 0, missing: missing };
}

// ───────────────────────────────────────────────────────────────────
//  STEPPER — Progress bar matching the applicant form style
// ───────────────────────────────────────────────────────────────────
function paceSetupStepper() {
	if ($('#pace-stepper-wrap').length) return;

	var _attempts = 0;
	var _timer = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields && wf.fields.length) {
			clearInterval(_timer);
			_paceRenderStepper(wf);
		} else if (++_attempts > 120) {
			clearInterval(_timer);
		}
	}, 100);
}

function _paceRenderStepper(wf) {
	// Build steps from Page Break fields — first page is always "Basic Details"
	var steps = [{ label: 'Basic Details', index: 0 }];
	(wf.fields || []).forEach(function (f) {
		if (f.fieldtype === 'Page Break' && f.label) {
			steps.push({ label: f.label, index: steps.length });
		}
	});

	// Flex row (see .pace-stepper-flex): connectors use capped width so ultrawide does not add huge gaps
	var html = '<div id="pace-stepper-wrap"><div class="pace-stepper pace-stepper-flex">';
	steps.forEach(function (step, i) {
		var lbl = step.label || '';
		var safeTitle = lbl.replace(/"/g, '&quot;').replace(/</g, '&lt;');
		html +=
			'<div class="pace-step" data-index="' + i + '" title="' + safeTitle + '">' +
			'<div class="pace-step-circle">' + (i + 1) + '</div>' +
			'<div class="pace-step-label">' + _paceEsc(lbl) + '</div>' +
			'</div>';
		if (i < steps.length - 1) {
			html += '<div class="pace-step-connector" aria-hidden="true"></div>';
		}
	});
	html += '</div></div>';

	// Inject stepper into DOM
	if ($('.web-form-header').length) {
		$('.web-form-header').after(html);
	} else if ($('.web-form-body').length) {
		$('.web-form-body').before(html);
	} else {
		$('.web-form-container, .page-content').first().prepend(html);
	}

	// Get current page index
	function getCurrentPageIdx() {
		var w = window.frappe && frappe.web_form;
		if (w && typeof w.current_section === 'number' && !isNaN(w.current_section)) {
			return Math.max(0, w.current_section);
		}
		var $pages = $('.web-form .form-layout > .form-page');
		if (!$pages.length) return 0;
		var curr = 0;
		$pages.each(function (i) {
			if ($(this).is(':visible')) curr = i;
		});
		return curr;
	}

	function goToWebFormPage(targetIdx) {
		var w = window.frappe && frappe.web_form;
		if (!w || typeof w.toggle_section !== 'function') return;
		var max = (w.page_breaks && w.page_breaks.length) || 0;
		var idx = Math.max(0, Math.min(targetIdx, max));
		w.current_section = idx;
		w.toggle_section();
	}

	// Update stepper visual state
	function updateStepperUI() {
		var curr = getCurrentPageIdx();
		$('.pace-step').each(function () {
			var idx = parseInt($(this).attr('data-index'), 10);
			$(this).removeClass('active completed');
			if (idx === curr) $(this).addClass('active');
			else if (idx < curr) $(this).addClass('completed');
		});
	}

	// Initial and periodic sync
	updateStepperUI();
	var _stepperSync = setInterval(updateStepperUI, 280);
	$(window).on('beforeunload', function () { clearInterval(_stepperSync); });

	// Sync on Next/Previous clicks
	$(document).on('click', '.btn-next, .btn-previous', function () {
		setTimeout(updateStepperUI, 50);
		setTimeout(updateStepperUI, 200);
	});

	// INTERCEPT Next Click for Validation (Capture phase to run BEFORE Frappe)
	document.addEventListener('click', function (e) {
		var btn = e.target.closest && e.target.closest('.btn-next');
		if (!btn) return;

		var wf = window.frappe && frappe.web_form;
		if (!wf) return;

		var $pages = $('.web-form .form-layout > .form-page');
		var $currPage = $pages.filter(':visible').first();
		if (!$currPage.length) return;

		// Find index of current page to show in logs if needed, but we use $currPage for validation
		var skip = _paceSkipForwardValidation(wf);
		if (skip) return;

		var check = _paceValidateStage(wf, $currPage);
		if (!check.ok) {
			// Stop Frappe's internal navigation
			e.preventDefault();
			e.stopPropagation();
			e.stopImmediatePropagation();

			var base = __('Please fill all required fields before proceeding.');
			if (check.missing && check.missing.length && typeof frappe !== 'undefined' && frappe.msgprint) {
				frappe.msgprint({
					title: __('Required fields'),
					message: _paceEsc(base) + '<br><br><ul><li>' + check.missing.join('</li><li>') + '</li></ul>',
					indicator: 'red'
				});
			} else {
				paceShowToast(base, 'error');
			}
			return false;
		}
	}, true);

	// Click on stepper step: validate mandatory fields before forward navigation
	$('#pace-stepper-wrap').on('click', '.pace-step', function () {
		var targetIdx = parseInt($(this).attr('data-index'), 10);
		var currentIdx = getCurrentPageIdx();
		var $pages = $('.web-form .form-layout > .form-page');

		if (targetIdx === currentIdx) return;

		if (targetIdx > currentIdx) {
			// Forward navigation: validate current page unless form is locked/view-only
			var skip = _paceSkipForwardValidation(wf);
			var check = skip
				? { ok: true, missing: [] }
				: _paceValidateStage(wf, $($pages.get(currentIdx)));

			if (check.ok) {
				goToWebFormPage(targetIdx);
				setTimeout(updateStepperUI, 50);
			} else {
				var base = __('Please fill all required fields before proceeding.');
				if (check.missing && check.missing.length && typeof frappe !== 'undefined' && frappe.msgprint) {
					frappe.msgprint({
						title: __('Required fields'),
						message:
							_paceEsc(base) +
							'<br><br><ul><li>' +
							check.missing.map(function (lab) { return _paceEsc(lab); }).join('</li><li>') +
							'</li></ul>',
						indicator: 'red',
					});
				} else {
					paceShowToast(base, 'error', 6500);
				}
			}
		} else {
			// Backward navigation: always allowed
			goToWebFormPage(targetIdx);
			setTimeout(updateStepperUI, 50);
		}
	});
}

// ───────────────────────────────────────────────────────────────────
//  STUDENT PHOTO PREVIEW — inline preview for upload_student_photo
// ───────────────────────────────────────────────────────────────────
function _paceNormalizeAttachValue(raw) {
	if (!raw || typeof raw !== 'string') return '';
	var t = raw.trim();
	// Strip "FILENAME,data:..." prefix used by Frappe ControlAttach
	var m = t.match(/^([^:]+),(.+):(.+)$/);
	if (m) return (m[2] + ':' + m[3]).trim();
	return t;
}

function _paceResolvePhotoPath() {
	var wf = window.frappe && frappe.web_form;
	var v = '';
	try {
		v = (wf && wf.get_value && wf.get_value('upload_student_photo')) || '';
	} catch (e) { }
	if (v) return _paceNormalizeAttachValue(String(v));

	var $block = $('[data-fieldname="upload_student_photo"]').first();
	if (!$block.length) return '';

	v = $block.find('input[type="hidden"]').val() || '';
	if (v) return _paceNormalizeAttachValue(v);

	v = $block.find('.attached-file-link').attr('href') || '';
	if (v) return _paceNormalizeAttachValue(v);

	v = ($block.find('.control-value').text() || '').trim();
	if (v) return _paceNormalizeAttachValue(v);

	v = $block.find('a[target="_blank"]').attr('href') || '';
	if (v) return _paceNormalizeAttachValue(v);

	return '';
}

function _pacePhotoToImgSrc(path) {
	if (!path) return '';
	if (/^data:/i.test(path)) return path;
	if (/^https?:\/\//i.test(path)) return path;
	var rel = path.charAt(0) === '/' ? path : '/' + path;
	var parts = rel.split('/');
	var enc = parts.map(function (seg, i) {
		if (i === 0) return seg;
		return encodeURIComponent(seg).replace(/'/g, '%27');
	});
	var origin = (typeof window !== 'undefined' && window.location && window.location.origin) || '';
	return origin + enc.join('/');
}

function _paceSyncPhotoPreview() {
	var path = _paceResolvePhotoPath();
	var $block = $('[data-fieldname="upload_student_photo"]').first();
	if (!$block.length) return;

	var $ctrl = $block.closest('.frappe-control');
	var $wrap = $ctrl.length ? $ctrl : $block.parent();

	var $prev = $wrap.children('#pace-student-photo-preview').first();
	if (!path) {
		$prev.remove();
		return;
	}
	var src = _pacePhotoToImgSrc(path);
	if (!src) { $prev.remove(); return; }

	if (!$prev.length) {
		$prev = $('<div id="pace-student-photo-preview" class="pace-photo-preview"><img alt="Student photo preview" decoding="async" /></div>');
		var $lab = $wrap.children('.control-label').first();
		if ($lab.length) {
			$lab.after($prev);
		} else {
			$wrap.prepend($prev);
		}
	} else {
		var $lab2 = $wrap.children('.control-label').first();
		if ($lab2.length && $prev.prev()[0] !== $lab2[0]) {
			$lab2.after($prev);
		}
	}
	var $img = $prev.find('img');
	if ($img.attr('data-pace-src') !== src) {
		$img.attr('data-pace-src', src).attr('src', src);
	}
}

/**
 * Frappe Web Form often drops visible labels on Attach / Attach Image when read-only (submitted) mode.
 * Same approach as slcm/admission/web_form/applicant_form.js — prepend .control-label from DocField metadata.
 */
function paceInjectAttachFieldLabels() {
	var wf = window.frappe && frappe.web_form;
	if (!wf || !wf.fields_dict) return;

	document.querySelectorAll('.frappe-control[data-fieldname][data-fieldtype]').forEach(function (field) {
		var fieldname = field.getAttribute('data-fieldname');
		var fieldtype = field.getAttribute('data-fieldtype');
		if (!fieldname || !fieldtype) return;
		if (fieldtype !== 'Attach' && fieldtype !== 'Attach Image') return;
		if (field.querySelector('.control-label')) return;

		var fd = wf.fields_dict[fieldname] && wf.fields_dict[fieldname].df;
		var labelText = (fd && fd.label) || fieldname;
		var lbl = document.createElement('label');
		lbl.className = 'control-label';
		lbl.textContent = labelText;
		field.insertBefore(lbl, field.firstChild);
	});

	document.querySelectorAll('.frappe-control .btn-attach').forEach(function (btn) {
		var misplaced = btn.querySelectorAll('.control-label');
		if (!misplaced.length) return;
		misplaced.forEach(function (n) { n.remove(); });
		if (!(btn.textContent || '').trim()) btn.textContent = __('Attach');
	});
}

function paceSetupPhotoPreview() {
	_paceSyncPhotoPreview();
	setInterval(_paceSyncPhotoPreview, 450);

	$(document).on('click', '.btn-next, .btn-previous', function () {
		setTimeout(_paceSyncPhotoPreview, 120);
	});

	var bindN = 0;
	var bindTimer = setInterval(function () {
		bindN++;
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields_dict && wf.fields_dict.upload_student_photo && !wf._pace_photo_on) {
			wf._pace_photo_on = true;
			try { wf.on('upload_student_photo', _paceSyncPhotoPreview); } catch (e) { }
		}
		if (bindN > 100) clearInterval(bindTimer);
	}, 100);
}

// ───────────────────────────────────────────────────────────────────
//  ATTACH FIELD VALIDATION — file type + size limits
//  • All Attachments: max 1 MB
//  • Student Photo: png, jpeg, jpg only
//  • All Other Docs: png, jpeg, jpg, pdf allowed
// ───────────────────────────────────────────────────────────────────
var _PACE_IMG_MAX = 1 * 1024 * 1024;       // 1 MB
var _PACE_DOC_MAX = 1 * 1024 * 1024;       // 1 MB
var _PACE_IMG_EXTS = ['png', 'jpeg', 'jpg'];
var _PACE_DOC_EXTS = ['png', 'jpeg', 'jpg', 'pdf'];
var _PACE_IMG_TYPES = ['.png', '.jpeg', '.jpg', '.jpe', 'image/png', 'image/jpeg', 'image/jpg'];
var _PACE_DOC_TYPES = ['.png', '.jpeg', '.jpg', '.jpe', '.pdf', 'image/png', 'image/jpeg', 'image/jpg', 'application/pdf'];

function _paceValidateFile(file, fieldtype) {
	if (!file) return true;
	var ext = (file.name || '').split('.').pop().toLowerCase();
	var isImg = (fieldtype === 'Attach Image' || (window._paceLastAttachCtx && _paceLastAttachCtx.fieldname === 'upload_student_photo'));
	var allowed = isImg ? _PACE_IMG_EXTS : _PACE_DOC_EXTS;
	var maxBytes = _PACE_IMG_MAX;
	var maxLabel = '1 MB';

	if (allowed.indexOf(ext) === -1) {
		paceShowToast(
			'\u26a0 Invalid file type ".' + ext + '". ' +
			(isImg ? 'Use png, jpeg, or jpg only (max 1 MB).' : 'Use png, jpeg, jpg, or pdf only (max 1 MB).'),
			'error'
		);
		return false;
	}
	if (file.size > maxBytes) {
		paceShowToast(
			'\u26a0 File "' + file.name + '" exceeds the ' + maxLabel + ' limit (' +
			(file.size / (1024 * 1024)).toFixed(1) + ' MB).',
			'error'
		);
		return false;
	}
	return true;
}

/** Track which Attach field was clicked (uploader modal is outside form DOM). */
function paceSetupAttachClickContext() {
	document.addEventListener('click', function (e) {
		var t = e.target && e.target.closest && e.target.closest('.btn-attach');
		if (!t || !window.frappe || !frappe.web_form) return;
		var ctrl = t.closest('.frappe-control[data-fieldtype]');
		if (!ctrl) return;
		var ft = ctrl.getAttribute('data-fieldtype');
		if (ft !== 'Attach' && ft !== 'Attach Image') return;
		window._paceLastAttachCtx = {
			fieldtype: ft,
			fieldname: ctrl.getAttribute('data-fieldname') || '',
			ts: Date.now(),
		};
	}, true);
}

/** Override Frappe FileUploader constructor to enforce allowed_file_types + max_file_size. */
function _paceWrapFileUploader() {
	if (!window.frappe || !frappe.ui || !frappe.ui.FileUploader) return;
	if (frappe.ui.FileUploader._paceWrapped) return;

	var Original = frappe.ui.FileUploader;

	function PaceFileUploader(opts) {
		opts = opts || {};
		// Force private-only uploads for PACE forms
		opts.is_private = 1;

		// SLCM file uploader options for PACE forms
		opts.disable_file_browser = true;
		opts.allow_web_link = false;
		opts.allow_take_photo = false;
		opts.allow_google_drive = false;
		opts.allow_toggle_optimize = false;
		opts.allow_toggle_private = false;
		opts.make_attachments_public = 0;

		if (frappe.web_form && window._paceLastAttachCtx) {
			var ctx = window._paceLastAttachCtx;
			if (Date.now() - (ctx.ts || 0) < 120000) {
				var base = Object.assign({}, opts.restrictions || {});
				var isPhoto = ctx.fieldname === 'upload_student_photo';

				opts.restrictions = Object.assign(base, {
					max_file_size: _PACE_IMG_MAX,
					allowed_file_types: (isPhoto ? _PACE_IMG_TYPES : _PACE_DOC_TYPES).slice(),
				});
			}
		}
		return new Original(opts);
	}

	PaceFileUploader.UploadOptions = Original.UploadOptions;
	PaceFileUploader._paceWrapped = true;
	frappe.ui.FileUploader = PaceFileUploader;
}

function paceSetupAttachValidation() {
	paceSetupAttachClickContext();

	// Validate file on input change
	document.addEventListener('change', function (e) {
		var input = e.target;
		if (!input || input.type !== 'file' || !window.frappe || !frappe.web_form) return;

		var inForm = input.closest('.web-form-container, form.web-form, .web-form-wrapper');
		var inUploader = input.closest('.file-uploader');
		var ctx = window._paceLastAttachCtx;
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

		if (!_paceValidateFile(file, ft)) {
			input.value = '';
			e.preventDefault();
			try { e.stopImmediatePropagation(); } catch (err) { }
		}
	}, true);

	// Wrap FileUploader (retry until available)
	var _upN = 0;
	var _upTimer = setInterval(function () {
		_paceWrapFileUploader();
		if (++_upN > 80 || (window.frappe && frappe.ui && frappe.ui.FileUploader && frappe.ui.FileUploader._paceWrapped)) {
			clearInterval(_upTimer);
		}
	}, 120);

	paceSetupAttachHighlight();
}

/** Rewrite descriptions to show the correct 1MB limits in the UI */
function paceSetupAttachHighlight() {
	var n = 0;
	var t = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields_dict) {
			for (var f in wf.fields_dict) {
				var fd = wf.fields_dict[f];
				if (fd && (fd.df.fieldtype === 'Attach' || fd.df.fieldtype === 'Attach Image')) {
					var txt = fd.df.description || '';
					if (!txt) continue;

					// Update UI if already rendered
					if (fd.$wrapper) {
						var $desc = fd.$wrapper.find('.help-box');
						if ($desc.length) {
							$desc.text(txt).show().css('color', '#64748b');
						} else {
							// For modern Frappe web form fields, description might be in .input-max-width or just after
							$('<div class="help-box small text-muted">' + txt + '</div>').appendTo(fd.$wrapper);
						}
					}
				}
			}
			// Only clear once a reasonable number of fields are loaded
			if (Object.keys(wf.fields_dict).length > 10) clearInterval(t);
		}
		if (++n > 100) clearInterval(t);
	}, 500);
}

// ───────────────────────────────────────────────────────────────────
//  FORCE PUBLIC UPLOADS — auto-uncheck Private in Frappe upload dialog
//  Two-layer: MutationObserver (instant) + polling (catches Vue async renders)
// ───────────────────────────────────────────────────────────────────
function _paceForcePublicInNode(root) {
	if (!root || !root.querySelectorAll) return;
	// 1. Click "Set all public" button (batch queue handler)
	root.querySelectorAll('button, .btn').forEach(function (btn) {
		if (!btn._pacePublicClicked && /set all public/i.test((btn.textContent || '').trim())) {
			btn._pacePublicClicked = true;
			setTimeout(function () { btn.click(); }, 30);
		}
	});
	// 2. Uncheck Private checkbox (triggers Vue reactivity via click)
	root.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
		if (cb._pacePublicDone) return;
		var lbl = cb.closest('label') || cb.parentElement || {};
		var txt = (lbl.textContent || cb.name || cb.id || '').toLowerCase();
		if (txt.indexOf('private') !== -1 && cb.checked) {
			cb._pacePublicDone = true;
			setTimeout(function () { if (cb.checked) cb.click(); }, 40);
		}
	});
}

function paceSetupForcePublicUploads() {
	// MutationObserver: fires as Frappe injects the upload modal
	var observer = new MutationObserver(function (mutations) {
		mutations.forEach(function (m) {
			m.addedNodes.forEach(function (node) {
				if (!node || node.nodeType !== 1) return;
				if (node.classList && (node.classList.contains('file-uploader') ||
					node.classList.contains('modal-dialog') ||
					node.classList.contains('modal'))) {
					_paceForcePublicInNode(node);
				}
				if (node.querySelectorAll) {
					node.querySelectorAll('.file-uploader').forEach(_paceForcePublicInNode);
				}
			});
		});
	});
	observer.observe(document.body, { childList: true, subtree: true });

	// Polling fallback: catches Vue async child renders
	setInterval(function () {
		var uploaders = document.querySelectorAll(
			'.modal.show .file-uploader, ' +
			'.modal[style*="display: block"] .file-uploader, ' +
			'.file-uploader'
		);
		uploaders.forEach(_paceForcePublicInNode);
		var modals = document.querySelectorAll('.modal.show, .modal[style*="display: block"]');
		modals.forEach(_paceForcePublicInNode);
	}, 300);
}

// ───────────────────────────────────────────────────────────────────
//  DATE OF BIRTH — age ≥ 17, max date capped, no future dates
// ───────────────────────────────────────────────────────────────────
function _paceMaxDob() {
	var d = new Date();
	d.setHours(0, 0, 0, 0);
	d.setFullYear(d.getFullYear() - 17);
	return d;
}

function _paceAgeYears(dobVal) {
	if (!dobVal) return null;
	var s = String(dobVal).trim();
	var parts = s.split('-');
	if (parts.length < 3) return null;
	var y = parseInt(parts[0], 10), mo = parseInt(parts[1], 10) - 1, day = parseInt(parts[2], 10);
	if (isNaN(y) || isNaN(mo) || isNaN(day)) return null;
	var birth = new Date(y, mo, day);
	if (isNaN(birth.getTime())) return null;
	var today = new Date(); today.setHours(0, 0, 0, 0); birth.setHours(0, 0, 0, 0);
	if (birth > today) return -1;
	var age = today.getFullYear() - birth.getFullYear();
	var md = today.getMonth() - birth.getMonth();
	if (md < 0 || (md === 0 && today.getDate() < birth.getDate())) age--;
	return age;
}

function _pacePatDob(wf) {
	if (!wf || !wf.fields_dict) return;
	var fd = wf.fields_dict.date_of_birth;
	if (!fd || fd.df.fieldtype !== 'Date') return;

	// Cap datepicker max date
	var maxD = _paceMaxDob();
	if (fd.datepicker && typeof fd.datepicker.update === 'function') {
		try { fd.datepicker.update({ maxDate: maxD }); } catch (e) { }
	}

	// Bind change listener
	if (!fd._paceDobBound && fd.$input && fd.$input.length) {
		fd._paceDobBound = true;
		fd.$input.on('change.pacedob', function () {
			var v = wf.get_value && wf.get_value('date_of_birth');
			var age = _paceAgeYears(v);
			if (v && (age === null || age < 17)) {
				frappe.msgprint({
					title: __('Invalid Date of Birth'),
					message: __('Applicant must be at least 17 years old. The date cannot be in the future.'),
					indicator: 'red',
				});
				try { wf.set_value('date_of_birth', ''); } catch (e2) { }
			}
		});
	}
}

function paceSetupDob() {
	// Block non-date characters in date inputs
	function isDateInput(el) {
		return el && el.tagName === 'INPUT' && el.closest &&
			el.closest('.frappe-control[data-fieldtype="Date"], [data-fieldtype="Date"]');
	}
	function stripBad(input) {
		var v = input.value || '';
		var cleaned = v.replace(/[^\d\-/.]/g, '');
		if (cleaned !== v) input.value = cleaned;
	}
	document.body.addEventListener('keydown', function (e) {
		if (!isDateInput(e.target)) return;
		if (e.ctrlKey || e.metaKey || e.altKey) return;
		var key = e.key || '';
		if (key === 'Tab' || key === 'Enter' || e.keyCode === 8 || e.keyCode === 9 || e.keyCode === 27 || e.keyCode === 46) return;
		if (e.keyCode >= 35 && e.keyCode <= 40) return;
		if (key.length === 1 && /[\d\-/.]/.test(key)) return;
		if (key.length === 1) e.preventDefault();
	}, true);
	document.body.addEventListener('input', function (e) {
		if (isDateInput(e.target)) stripBad(e.target);
	}, true);
	document.body.addEventListener('paste', function (e) {
		if (!isDateInput(e.target)) return;
		setTimeout(function () { stripBad(e.target); }, 0);
	}, true);

	// Poll until web_form and DOB field are ready
	var n = 0;
	var t = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		_pacePatDob(wf);
		var fd = wf && wf.fields_dict && wf.fields_dict.date_of_birth;
		if (fd && fd._paceDobBound && fd.datepicker) {
			clearInterval(t);
		} else if (++n > 150) {
			clearInterval(t);
		}
	}, 100);
}

// ───────────────────────────────────────────────────────────────────
//  PHONE VALIDATION — country-based digit length
// ───────────────────────────────────────────────────────────────────
function paceSetupPhoneValidation() {
	// National number digit lengths per country code
	var ISD_LENGTHS = {
		'+91': [10], 91: [10],              // India
		'+1': [10], 1: [10],                // USA / Canada
		'+44': [10], 44: [10],              // UK
		'+971': [9], 971: [9],              // UAE
		'+65': [8], 65: [8],                // Singapore
		'+61': [9, 10], 61: [9, 10],        // Australia
		'+966': [9], 966: [9],              // Saudi Arabia
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
		'+94': [9], 94: [9],                // Sri Lanka
		'+977': [10], 977: [10],            // Nepal
	};

	function _phoneCtrl(input) {
		if (!input || !input.closest) return null;
		return input.closest('.frappe-control[data-fieldtype="Phone"]') ||
			input.closest('[data-fieldtype="Phone"]');
	}

	function _normalizeIsd(raw) {
		if (!raw) return '';
		var s = String(raw).trim().replace(/[^\d+]/g, '');
		if (!s) return '';
		return s.startsWith('+') ? s : ('+' + s);
	}

	function _isdInfo(ctrl) {
		if (!ctrl) return null;
		var isdNorm = '';
		var isdEl = ctrl.querySelector('.country') || ctrl.querySelector('.selected-phone .country');
		if (isdEl && isdEl.textContent.trim()) {
			isdNorm = _normalizeIsd(isdEl.textContent);
		}
		if (!isdNorm) {
			var fn = ctrl.getAttribute('data-fieldname');
			var wf = window.frappe && frappe.web_form;
			if (fn && wf && typeof wf.get_value === 'function') {
				var v = wf.get_value(fn);
				if (v && String(v).indexOf('-') >= 0) {
					var head = String(v).split('-')[0].trim();
					isdNorm = _normalizeIsd(head.replace(/[^\d+]/g, ''));
				}
			}
		}
		if (!isdNorm) return null;
		var bare = isdNorm.replace(/^\+/, '');
		var lengths = ISD_LENGTHS[isdNorm] || ISD_LENGTHS[bare];
		if (!lengths) return null;
		return { isd: isdNorm, lengths: lengths, limit: Math.max.apply(null, lengths) };
	}

	function _applyDigitCap(input) {
		var ctrl = _phoneCtrl(input);
		if (!ctrl) return;
		var info = _isdInfo(ctrl);
		var limit = info ? info.limit : 15;
		input.setAttribute('maxlength', limit);
		var digits = (input.value || '').replace(/\D/g, '');
		if (digits.length > limit) input.value = digits.slice(0, limit);
	}

	// Real-time cap
	document.body.addEventListener('input', function (e) {
		var input = e.target;
		if (!input || input.tagName !== 'INPUT' || !_phoneCtrl(input)) return;
		_applyDigitCap(input);
	}, true);

	// Block non-digits
	document.body.addEventListener('keydown', function (e) {
		var input = e.target;
		if (!input || input.tagName !== 'INPUT' || !_phoneCtrl(input)) return;
		if (e.ctrlKey || e.metaKey || e.altKey) return;
		var k = e.keyCode;
		if (k === 8 || k === 9 || k === 13 || k === 27 || k === 46) return;
		if (k >= 35 && k <= 40) return;
		var isDigit = (k >= 48 && k <= 57) || (k >= 96 && k <= 105) || (e.key && e.key.length === 1 && /\d/.test(e.key));
		if (!isDigit) { e.preventDefault(); return; }
		var ctrl = _phoneCtrl(input);
		var info = _isdInfo(ctrl);
		var limit = info ? info.limit : 15;
		var digits = (input.value || '').replace(/\D/g, '');
		var start = typeof input.selectionStart === 'number' ? input.selectionStart : 0;
		var end = typeof input.selectionEnd === 'number' ? input.selectionEnd : 0;
		var selDigits = (input.value.substring(start, end) || '').replace(/\D/g, '').length;
		if (digits.length - selDigits + 1 > limit) e.preventDefault();
	}, true);

	// Sync on paste
	document.body.addEventListener('paste', function (e) {
		var input = e.target;
		if (!input || input.tagName !== 'INPUT' || !_phoneCtrl(input)) return;
		setTimeout(function () { _applyDigitCap(input); }, 0);
	}, true);

	// Sync when country picker selection changes
	var syncPhone = function (e) {
		var target = e.target;
		setTimeout(function () {
			var input = target.closest ? target.closest('.frappe-control[data-fieldtype="Phone"] input') : null;
			if (!input) input = target.closest ? target.closest('[data-fieldtype="Phone"] input') : null;
			if (!input) return;
			input.dispatchEvent(new Event('input', { bubbles: true }));
		}, 0);
	};
	['click', 'focusin', 'keyup', 'change'].forEach(function (ev) {
		document.body.addEventListener(ev, syncPhone, true);
	});

	// On blur: validate length
	document.body.addEventListener('focusout', function (e) {
		var input = e.target;
		if (!input || input.tagName !== 'INPUT' || !_phoneCtrl(input)) return;
		var ctrl = _phoneCtrl(input);
		var info = _isdInfo(ctrl);
		if (!info) return;
		var val = (input.value || '').replace(/\D/g, '');
		if (val && info.lengths.indexOf(val.length) === -1) {
			var expectedStr = info.lengths.join(' or ');
			paceShowToast('\u26a0 Invalid phone length for ' + info.isd + '. Must be ' + expectedStr + ' digits.', 'error');
			if (val.length > info.limit) input.value = val.slice(0, info.limit);
		}
	}, true);
}

// ───────────────────────────────────────────────────────────────────
//  NUMERIC FIELD RESTRICTIONS
// ───────────────────────────────────────────────────────────────────
function paceSetupNumericRestrictions() {
	var NUMERIC_TYPES = ['Int', 'Float', 'Currency', 'Percent'];

	function numCtrl(el) {
		if (!el || !el.closest) return null;
		return el.closest('.frappe-control[data-fieldtype], [data-fieldtype]');
	}

	document.body.addEventListener('keydown', function (e) {
		var input = e.target;
		if (!input || input.tagName !== 'INPUT') return;
		var ctrl = numCtrl(input);
		var ft = ctrl ? ctrl.getAttribute('data-fieldtype') : null;
		if (!ft || NUMERIC_TYPES.indexOf(ft) === -1) return;
		if (e.ctrlKey || e.metaKey || e.altKey) return;
		var code = e.keyCode;
		if (code === 8 || code === 9 || code === 13 || code === 27 || code === 46) return;
		if (code >= 35 && code <= 40) return;
		var key = e.key || '';
		if (key.length === 1) {
			if (/\d/.test(key)) return;
			if ((ft === 'Float' || ft === 'Currency' || ft === 'Percent') && key === '.' && input.value.indexOf('.') === -1) return;
			e.preventDefault();
		}
	}, true);

	document.body.addEventListener('input', function (e) {
		var input = e.target;
		if (!input || input.tagName !== 'INPUT') return;
		var ctrl = numCtrl(input);
		var ft = ctrl ? ctrl.getAttribute('data-fieldtype') : null;
		if (!ft || NUMERIC_TYPES.indexOf(ft) === -1) return;
		var regex = (ft === 'Int') ? /[^0-9]/g : /[^0-9.]/g;
		var val = input.value;
		if (regex.test(val)) input.value = val.replace(regex, '');
		var fn = ctrl.getAttribute('data-fieldname');
		if (ft === 'Int' && fn === 'year_of_passing' && input.value.length > 4) {
			input.value = input.value.slice(0, 4);
		}
		if (fn === 'obtained_percentagecgpa') {
			var gridRow = input.closest('.grid-row, .grid-form-row, .form-in-grid');
			if (gridRow) {
				var schemeCtrl = gridRow.querySelector('[data-fieldname="marking_scheme"] select, [data-fieldname="marking_scheme"] input');
				var scheme = '';
				if (schemeCtrl) scheme = schemeCtrl.value;

				if (!scheme && window.frappe && frappe.web_form && frappe.web_form.fields_dict.ug_degree) {
					var rowName = gridRow.getAttribute('data-name');
					if (rowName) {
						var grid = frappe.web_form.fields_dict.ug_degree.grid;
						var rObj = grid.grid_rows.find(function(r) { return r.doc.name === rowName; });
						if (rObj && rObj.doc) scheme = rObj.doc.marking_scheme;
					}
				}

				var num = parseFloat(input.value);
				if (!isNaN(num)) {
					if (scheme === 'Percentage' && num > 100) {
						input.value = '100';
					} else if (scheme === 'CGPA' && num > 10) {
						input.value = '10';
					}
				}
			}
		}
	}, true);
}

/**
 * Awesomplete list in nested grids can anchor to the wrong offset parent; pin under the input.
 */
function paceSetupUgDegreeLinkDropdownFix() {
	if (window._paceUgDegreeLinkDropdownFix) return;
	window._paceUgDegreeLinkDropdownFix = true;

	function reposition(input) {
		var $wrap = $(input).closest('.awesomplete');
		var $ul = $wrap.children('ul');
		if (!$ul.length) return;
		var r = input.getBoundingClientRect();
		$ul.css({
			position: 'fixed',
			left: Math.round(r.left) + 'px',
			top: Math.round(r.bottom + 2) + 'px',
			width: Math.max(Math.round(r.width), 220) + 'px',
			maxHeight: 'min(40vh, 320px)',
			overflowY: 'auto',
			zIndex: 2147483646,
			boxSizing: 'border-box',
		});
	}

	function clearStyle(input) {
		var $ul = $(input).closest('.awesomplete').children('ul');
		$ul.attr('style', '');
	}

	var gridSel = '.web-form .frappe-control[data-fieldname="ug_degree"], .web-form [data-fieldname="ug_degree"]';

	$(document).on('awesomplete-open', gridSel + ' input', function () {
		reposition(this);
	});

	$(document).on('awesomplete-close', gridSel + ' input', function () {
		clearStyle(this);
	});

	window.addEventListener(
		'scroll',
		function () {
			var el = document.activeElement;
			if (!el || el.tagName !== 'INPUT' || !$(el).closest(gridSel).length) return;
			if ($(el).closest('.awesomplete').find('> ul').length) reposition(el);
		},
		true
	);
}

// ───────────────────────────────────────────────────────────────────
function paceSetupFieldErrorClear() {
	$(document).on('input change', '.web-form input, .web-form textarea, .web-form select', function () {
		var $t = $(this);
		$t.removeClass('pace-field-error');
		$t.closest('.frappe-control').find('.pace-field-error').removeClass('pace-field-error');
	});
}

// ───────────────────────────────────────────────────────────────────
//  ADDRESS — Country → State → District (City doctype) link filters
// ───────────────────────────────────────────────────────────────────

/**
 * State is dynamically filtered by State.country.
 * District (City doctype) is filtered by City.state.
 */
function paceWireAddressLinkFilters() {
	var wf = window.frappe && frappe.web_form;
	if (!wf || !wf.fields_dict || !wf.fields_dict.country) return false;

	function showFieldError(fieldname, message) {
		var fieldWrapper = document.querySelector('[data-fieldname="' + fieldname + '"]');
		if (!fieldWrapper) return;
		var errDiv = fieldWrapper.querySelector('.custom-field-error');
		if (!errDiv) {
			errDiv = document.createElement('div');
			errDiv.className = 'custom-field-error text-danger';
			errDiv.style.cssText = 'font-size:12px; margin-top:4px;';
			var inputArea = fieldWrapper.querySelector('.control-input-wrapper') || fieldWrapper.querySelector('.control-input');
			if (inputArea) {
				inputArea.appendChild(errDiv);
			} else {
				fieldWrapper.appendChild(errDiv);
			}
		}
		errDiv.innerText = message;
	}

	function clearFieldError(fieldname) {
		var fieldWrapper = document.querySelector('[data-fieldname="' + fieldname + '"]');
		if (!fieldWrapper) return;
		var errDiv = fieldWrapper.querySelector('.custom-field-error');
		if (errDiv) errDiv.remove();
	}

	function effCountryFrom(field) {
		var raw = wf.get_value(field);
		return ((raw || '') + '').trim() || 'India';
	}

	function patchBlock(countryFld, stateFld, districtFld, cityDataFld) {
		var sf = wf.get_field && wf.get_field(stateFld);
		var df = wf.get_field && wf.get_field(districtFld);
		if (!sf || !df) return false;

		[countryFld, stateFld, districtFld].forEach(function (fn) {
			var fld = wf.get_field(fn);
			if (fld && fld.df) fld.df.ignore_user_permissions = 1;
		});

		function stateQueryFn() {
			var eff = effCountryFrom(countryFld);
			return {
				or_filters: [
					['State', 'country', '=', eff],
					['State', 'name', '=', 'Other']
				]
			};
		}

		function districtQueryFn() {
			var st = wf.get_value(stateFld);
			if (!st) {
				return { filters: [['City', 'name', '=', '__slcm_no_state__']] };
			}
			return {
				or_filters: [
					['City', 'state', '=', st],
					['City', 'name', '=', 'Other']
				]
			};
		}

		if (wf.set_query) {
			wf.set_query(stateFld, stateQueryFn);
			wf.set_query(districtFld, districtQueryFn);
		}
		if (wf.set_df_property) {
			try { wf.set_df_property(stateFld, 'get_query', stateQueryFn); } catch (e) {}
			try { wf.set_df_property(districtFld, 'get_query', districtQueryFn); } catch (e) {}
		}
		if (sf) {
			if (sf.df) sf.df.get_query = stateQueryFn;
			sf.get_query = stateQueryFn;
		}
		if (df) {
			if (df.df) df.df.get_query = districtQueryFn;
			df.get_query = districtQueryFn;
		}

		var lastCountry = wf.get_value(countryFld);
		var lastState = wf.get_value(stateFld);
		var lastDistrict = wf.get_value(districtFld);

		wf.on(countryFld, function () {
			if (wf._is_syncing_address) return;
			var currentCountry = wf.get_value(countryFld);
			if (lastCountry === currentCountry) return;
			lastCountry = currentCountry;

			clearFieldError(stateFld);
			clearFieldError(districtFld);

			wf.set_value(stateFld, '');
			wf.set_value(districtFld, '');
			if (cityDataFld) wf.set_value(cityDataFld, '');
		});

		wf.on(stateFld, function () {
			if (wf._is_syncing_address) return;
			var currentCountry = wf.get_value(countryFld);
			var currentState = wf.get_value(stateFld);
			if (lastState === currentState) return;
			lastState = currentState;

			clearFieldError(stateFld);
			clearFieldError(districtFld);

			if (!currentState) {
				wf.set_value(districtFld, '');
				if (cityDataFld) wf.set_value(cityDataFld, '');
				return;
			}

			// Validate State against Country (bypass if 'Other')
			if (currentCountry && String(currentState).toUpperCase() !== 'OTHER' && String(currentCountry).toUpperCase() !== 'OTHER') {
				frappe.call({
					method: "frappe.client.get_value",
					args: {
						doctype: "State",
						filters: { name: currentState },
						fieldname: ["country"]
					},
					callback: function(r) {
						if (r.message && r.message.country && r.message.country !== currentCountry) {
							frappe.msgprint("The selected State '" + currentState + "' does not belong to '" + currentCountry + "'. Please select a valid state.");
							showFieldError(stateFld, "This state does not belong to the selected country.");
							wf._is_syncing_address = true;
							wf.set_value(stateFld, '');
							wf.set_value(districtFld, '');
							if (cityDataFld) wf.set_value(cityDataFld, '');
							setTimeout(function() { wf._is_syncing_address = false; }, 200);
						} else {
							clearFieldError(stateFld);
						}
					}
				});
			}

			wf.set_value(districtFld, '');
			if (cityDataFld) wf.set_value(cityDataFld, '');
		});

		wf.on(districtFld, function() {
			if (wf._is_syncing_address) return;
			var currentDistrict = wf.get_value(districtFld);
			var currentState = wf.get_value(stateFld);
			if (lastDistrict === currentDistrict) return;
			lastDistrict = currentDistrict;

			if (!currentDistrict) {
				clearFieldError(districtFld);
				return;
			}

			// Validate District against State (bypass if 'Other')
			if (currentState && String(currentDistrict).toUpperCase() !== 'OTHER' && String(currentState).toUpperCase() !== 'OTHER') {
				frappe.call({
					method: "frappe.client.get_value",
					args: {
						doctype: "City",
						filters: { name: currentDistrict },
						fieldname: ["state", "country"]
					},
					callback: function(r) {
						if (r.message && r.message.state && r.message.state !== currentState) {
							frappe.msgprint("The selected District '" + currentDistrict + "' does not belong to '" + currentState + "'. Please select a valid district.");
							showFieldError(districtFld, "This district does not belong to the selected state.");
							wf._is_syncing_address = true;
							wf.set_value(districtFld, '');
							setTimeout(function() { wf._is_syncing_address = false; }, 200);
						} else {
							clearFieldError(districtFld);
						}
					}
				});
			}
		});

		return true;
	}

	var okCorr = !!wf._slcmPaceAddrCorrDone;
	var okPerm = !!wf._slcmPaceAddrPermDone;

	try {
		if (!okCorr && wf.fields_dict.state && wf.fields_dict.district) {
			okCorr = !!patchBlock('country', 'state', 'district', 'city');
			if (okCorr) wf._slcmPaceAddrCorrDone = true;
		}
		var wantPerm = !!(wf.fields_dict.p_country && wf.fields_dict.p_state && wf.fields_dict.p_district);
		if (!okPerm && wantPerm) {
			okPerm = !!patchBlock('p_country', 'p_state', 'p_district', 'p_city');
			if (okPerm) wf._slcmPaceAddrPermDone = true;
		} else if (!wantPerm) {
			okPerm = true;
			wf._slcmPaceAddrPermDone = true;
		}
	} catch (e) {
		console.error('paceWireAddressLinkFilters error:', e);
		return false;
	}

	return !!(okCorr && okPerm);
}

function paceScheduleAddressLinkFilters() {
	function tryWire() {
		return !!paceWireAddressLinkFilters();
	}
	tryWire();
	setTimeout(tryWire, 0);
	var _n = 0;
	var _t = setInterval(function () {
		if (tryWire() || ++_n > 80) clearInterval(_t);
	}, 125);
}

// ───────────────────────────────────────────────────────────────────
//  ADDRESS SYNC — Correspondence to Permanent
// ───────────────────────────────────────────────────────────────────
/**
 * Auto-fetch State and Country when District (City Link) is selected
 * BUG 2 FIX: Removed reverse cascading to prevent auto-filling State/Country from District
 */
function paceSetupDistrictFetch() {
	// Function intentionally left blank to disable reverse fill logic
	// while keeping the function signature intact for existing callers.
}

function paceSetupAddressSync() {

	var n = 0;
	var t = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields_dict && wf.fields_dict.is_permanent_address_same) {
			clearInterval(t);

			var sync = function () {
				if (!wf.get_value('is_permanent_address_same')) return;

				wf._is_syncing_address = true;

				var mapping = [
					['address_line_1', 'p_address_line_1'],
					['address_line_2', 'p_address_line_2'],
					['country', 'p_country'],
					['state', 'p_state'],
					['district', 'p_district'],
					['city', 'p_city'],
					['pincode', 'p_pincode']
				];

				mapping.forEach(function (pair) {
					var src = pair[0];
					var dst = pair[1];
					var val = wf.get_value(src);
					if (val !== undefined && val !== null) {
						wf.set_value(dst, val);
					}
				});

				setTimeout(function () {
					wf._is_syncing_address = false;
				}, 100);
			};

			// Bind to checkbox and all source fields
			wf.on('is_permanent_address_same', sync);
			['address_line_1', 'address_line_2', 'city', 'district', 'state', 'country', 'pincode'].forEach(function (f) {
				wf.on(f, sync);
			});
		}
		if (++n > 100) clearInterval(t);
	}, 200);
}

// ───────────────────────────────────────────────────────────────────
//  PINCODE VALIDATION — 6 digits only
// ───────────────────────────────────────────────────────────────────
function paceSetupPincodeValidation() {
	var validatePincode = function (fieldname) {
		var wf = window.frappe && frappe.web_form;
		if (!wf) return;
		var val = String(wf.get_value(fieldname) || '').trim();
		if (!val) return;

		var digits = val.replace(/\D/g, '');
		if (digits.length !== 6 || val.length !== 6) {
			paceShowToast('\u26a0 Pincode must be exactly 6 numeric digits.', 'error');
			// Optionally clear or trim
			if (digits.length > 6) wf.set_value(fieldname, digits.slice(0, 6));
		}
	};

	var n = 0;
	var t = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields_dict && wf.fields_dict.pincode) {
			clearInterval(t);
			wf.on('pincode', function () { validatePincode('pincode'); });
			if (wf.fields_dict.p_pincode) {
				wf.on('p_pincode', function () { validatePincode('p_pincode'); });
			}
		}
		if (++n > 100) clearInterval(t);
	}, 200);
}

// ───────────────────────────────────────────────────────────────────
//  UG DEGREE CERTIFICATE — visibility / mandatory
// ───────────────────────────────────────────────────────────────────
/**
 * TEMPORARY: Always show UG Degree Certificate and treat it as mandatory.
 * To restore result-status rules, replace this function body with the block
 * in the comment below (Declared vs Waiting for result).
	 */
function paceSetupUGCertificateVisibility() {
	var attempts = 0;
	var initTimer = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields_dict) {
			clearInterval(initTimer);
			if (wf.set_df_property) {
				try { wf.set_df_property('ug_degree_certificate', 'hidden', 0); } catch (e) { }
				try { wf.set_df_property('ug_degree_certificate', 'reqd', 1); } catch (e) { }
			}
			var selectors = [
				'[data-fieldname="ug_degree_certificate"]',
				'.frappe-control[data-fieldname="ug_degree_certificate"]',
				'.form-group[data-fieldname="ug_degree_certificate"]',
			];
			var wrapper = null;
			for (var s = 0; s < selectors.length; s++) {
				wrapper = document.querySelector(selectors[s]);
				if (wrapper) break;
			}
			if (wrapper) {
				wrapper.style.display = '';
			}
			try { wf.refresh_field('ug_degree_certificate'); } catch (e) { }
		}
		if (++attempts > 100) clearInterval(initTimer);
	}, 200);
}

/*
// ─── ORIGINAL (result status): show certificate only if any UG row is "Declared";
//     hide and not mandatory if all rows are "Waiting for result". Restore by
//     swapping the TEMP function above for this implementation. ───
function paceSetupUGCertificateVisibility() {
	var _lastState = null;

	function _getRows() {
		var wf = window.frappe && frappe.web_form;
		var rows = (wf && wf.doc && wf.doc.ug_degree) || [];
		if (!rows.length) {
			try { rows = wf.fields_dict.ug_degree.grid.get_data() || []; } catch (e) {}
		}
		return rows;
	}

	function _hasDeclared() {
		return _getRows().some(function (row) {
			return (row.result_status || '').trim() === 'Declared';
		});
	}

	function applyUGCertVisibility() {
		var show = _hasDeclared();
		if (_lastState === show) return;
		_lastState = show;

		var wf = window.frappe && frappe.web_form;

		if (wf && wf.set_df_property) {
			try { wf.set_df_property('ug_degree_certificate', 'hidden', show ? 0 : 1); } catch (e) {}
			try { wf.set_df_property('ug_degree_certificate', 'reqd',   show ? 1 : 0); } catch (e) {}
		}

		var selectors = [
			'[data-fieldname="ug_degree_certificate"]',
			'.frappe-control[data-fieldname="ug_degree_certificate"]',
			'.form-group[data-fieldname="ug_degree_certificate"]',
		];
		var wrapper = null;
		for (var i = 0; i < selectors.length; i++) {
			wrapper = document.querySelector(selectors[i]);
			if (wrapper) break;
		}
		if (wrapper) {
			wrapper.style.display = show ? '' : 'none';
		}

		if (wf) {
			try { wf.refresh_field('ug_degree_certificate'); } catch (e) {}
		}
	}

	var attempts = 0;
	var initTimer = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields_dict) {
			clearInterval(initTimer);

			applyUGCertVisibility();

			setInterval(applyUGCertVisibility, 600);

			var checkGrid = setInterval(function () {
				var grid = wf.fields_dict.ug_degree && wf.fields_dict.ug_degree.grid;
				if (grid) {
					clearInterval(checkGrid);
					var origAdd = grid.add_new_row && grid.add_new_row.bind(grid);
					if (origAdd) {
						grid.add_new_row = function () {
							var r = origAdd.apply(this, arguments);
							setTimeout(applyUGCertVisibility, 300);
							return r;
						};
					}
				}
			}, 500);
		}
		if (++attempts > 100) clearInterval(initTimer);
	}, 200);
}
*/

function paceSetupDeclarationRenderFix() {
	// Wait for wf to be ready, then use server-fetch-based restore
	var n = 0;
	var t = setInterval(function() {
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields_dict) {
			clearInterval(t);
			// Delegate to the server-fetch based restore
			_paceRestoreCheckboxValues(wf);
		}
		if (++n > 100) clearInterval(t);
	}, 200);
}

function paceSetupUgDegreeInitialRow() {
	var n = 0;
	var t = setInterval(function() {
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields_dict && wf.fields_dict.ug_degree && wf.fields_dict.ug_degree.grid) {
			var g = wf.fields_dict.ug_degree.grid;
			if (g && g.grid_rows && g.grid_rows.length !== undefined) {
				clearInterval(t);
				var is_locked = false;
				try {
					var s = _paceResolveApplicationStatus();
					is_locked = _pacePortalLocked(s);
				} catch (e) {}
				if (g.grid_rows.length === 0 && !is_locked) {
					g.add_new_row();
				}
			}
		}
		if (++n > 100) clearInterval(t);
	}, 100);
}

// ───────────────────────────────────────────────────────────────────
//  BOOTSTRAP — frappe.ready
//  (File attach dialog defaults: slcm/public/js/file_uploader_globals.js + hooks)
// ───────────────────────────────────────────────────────────────────
frappe.ready(function () {
	makeInputUppercase();
	_paceInjectCSS();
	paceSetupFieldErrorClear();

	// Portal shell nav / footer (themed from Applicant Portal Config)
	_paceInjectPortalShell();

	// Trigger autofill immediately (also hooks web_form.on('load') independently of shell call)
	_paceTriggerPrefill();

	// Dynamic Applicant Name sync
	_paceSetupNameSync();

	// Address Sync
	paceSetupAddressSync();

	// District Auto-fetch
	paceSetupDistrictFetch();

	paceScheduleAddressLinkFilters();

	// Filter programme options to only open programmes
	paceSetupProgrammeLinkFilter();

	// Pincode Validation
	paceSetupPincodeValidation();

	// UG Degree Certificate visibility based on Result Status
	paceSetupUGCertificateVisibility();

	// Top Bar (Back + Applying for)
	paceSetupTopBar();

	// Application status badge in page title
	paceSetupStatusBadge();

	// Save Draft button (injected beside Next/Submit)
	paceSetupSaveDraftButton();

	// Confirmation for Discard button
	paceSetupDiscardConfirmation();

	// Read-only logic based on status
	paceSetupReadonlyLogic();

	// Submission and Payment handling
	paceSetupSubmission();
	// Preload Razorpay so the first "Proceed to Payment" is not waiting on the script.
	_paceLoadRazorpay(function () { });

	// Receipt download button
	paceSetupReceiptButton();
	paceSetupPayButton();

	// Stepper with mandatory validation
	paceSetupStepper();

	// Student Photo Preview
	paceSetupPhotoPreview();

	// Attach field validation
	paceSetupAttachValidation();
	// paceSetupForcePublicUploads();

	// Attach labels in read-only / after Frappe re-render (applicant_form parity)
	setTimeout(function () { paceInjectAttachFieldLabels(); }, 500);
	setTimeout(function () { paceInjectAttachFieldLabels(); }, 2000);
	var _paceAttachLblN = 0;
	var _paceAttachLblTimer = setInterval(function () {
		paceInjectAttachFieldLabels();
		if (++_paceAttachLblN > 100) clearInterval(_paceAttachLblTimer);
	}, 400);

	// Date of Birth validation
	paceSetupDob();

	// Phone validation
	paceSetupPhoneValidation();

	// Numeric restrictions
	paceSetupNumericRestrictions();
	paceSetupUgDegreeLinkDropdownFix();

	paceSetupDeclarationRenderFix();
	paceSetupUgDegreeInitialRow();
	// Auto-sync status badge every 2s (picks up changes from web_form events)
	setInterval(function () {
		var s = _paceResolveField('status');
		if (s) _paceUpdateStatusBadge(s);
	}, 2000);

});

// Make input in Uppercase

function makeInputUppercase() {

	const uppercase_fields = [
		"first_name",
		"middle_name",
		"last_name",
		"applicant_name",
		"organization_name",
		"designation",
		"please_specify",
		"father_name",
		"mother_name",
		"address_line_1",
		"address_line_2",
		"city"
	];

	uppercase_fields.forEach(fieldname => {
		let field = frappe.web_form.get_field(fieldname);
		if (field && field.$input) {
			// Visually transform text to uppercase while typing
			field.$input.css('text-transform', 'uppercase');
			
			// Listen to input events to cast value to uppercase as user types
			field.$input.on('input', function() {
				let start = this.selectionStart;
				let end = this.selectionEnd;
				this.value = this.value.toUpperCase();
				this.setSelectionRange(start, end); // Restore cursor position
			});
		}

		frappe.web_form.on(fieldname, (field, value) => {
			if (value) {
				frappe.web_form.set_value(
					fieldname,
					value.toUpperCase()
				);
			}
		});
	});

	// Fields that should only visually appear uppercase via CSS (including awesomplete options)
	const display_uppercase_fields = [
		"country", "state", "district",
		"p_country", "p_state", "p_district"
	];

	let parent_display_selectors = display_uppercase_fields.map(f => 
		`[data-fieldname="${f}"] input, [data-fieldname="${f}"] .awesomplete ul li`
	).join(', ');

	// Handle child table fields dynamically (since rows can be added/edited later)
	const child_uppercase_fields = [
		"institution_name",
		"university",
		"programme_studied"
	];
	
	let child_input_selectors = child_uppercase_fields.map(f => `input[data-fieldname="${f}"]`).join(', ');

	// Child fields that should only visually appear uppercase via CSS (like select fields and their options)
	const child_display_uppercase_fields = [
		"result_status",
		"marking_scheme"
	];

	let child_display_selectors = child_display_uppercase_fields.map(f => 
		`input[data-fieldname="${f}"], select[data-fieldname="${f}"], select[data-fieldname="${f}"] option, [data-fieldname="${f}"] .awesomplete ul li`
	).join(', ');
	
	let all_css_selectors = [parent_display_selectors, child_input_selectors, child_display_selectors].filter(Boolean).join(', ');

	// Apply CSS to make them appear uppercase instantly
	$(`<style>${all_css_selectors} { text-transform: uppercase; }</style>`).appendTo('head');

	// Delegate input event to cast to uppercase while typing (only for fields that save in uppercase)
	$(document).on('input', child_input_selectors, function() {
		let start = this.selectionStart;
		let end = this.selectionEnd;
		if (this.setSelectionRange) {
			this.value = this.value.toUpperCase();
			this.setSelectionRange(start, end);
		}
	});
}
	

/**
 * Renders the After Payment success modal overlay.
 * Called after payment verification succeeds, or on page load when status is Completed.
 */
function paceRenderSuccessPage() {
	// Only show once
	if (document.getElementById('pace-success-modal')) return;

	var wf = frappe.web_form;
	var title = (wf && wf.success_title) || __('Application Submitted Successfully');
	var message = (wf && wf.success_message) || __('Thank you! Your application has been received and the fee has been paid successfully.');
	var success_url = (wf && wf.success_url) || '/pace_application_card';

	var overlay = document.createElement('div');
	overlay.id = 'pace-success-modal';
	overlay.style.cssText = [
		'position:fixed', 'inset:0', 'z-index:9999',
		'display:flex', 'align-items:center', 'justify-content:center',
		'background:rgba(0,0,0,0.55)', 'backdrop-filter:blur(4px)'
	].join(';');

	overlay.innerHTML =
		'<div style="max-width:520px;width:90%;background:#fff;border-radius:16px;padding:48px 40px;text-align:center;box-shadow:0 24px 60px rgba(0,0,0,0.18);position:relative;animation:paceSuccessFadeIn 0.4s ease">' +
			'<div style="width:80px;height:80px;background:linear-gradient(135deg,#10b981,#059669);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 28px;box-shadow:0 8px 24px rgba(16,185,129,0.35)">' +
				'<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>' +
			'</div>' +
			'<h2 style="font-size:24px;font-weight:400;color:#1f2937;margin:0 0 16px">' + _paceEsc(title) + '</h2>' +
			'<p style="font-size:15px;color:#6b7280;line-height:1.7;margin:0 0 36px">' + _paceEsc(message) + '</p>' +
			'<a href="' + success_url + '" id="pace-success-dashboard-btn" style="display:inline-block;background:#7B1D1D;color:#fff;padding:14px 36px;border-radius:8px;text-decoration:none;font-weight:300;font-size:15px;transition:background 0.2s">' + __('Go to Dashboard') + '</a>' +
		'</div>' +
		'<style>@keyframes paceSuccessFadeIn{from{opacity:0;transform:scale(0.93)}to{opacity:1;transform:scale(1)}}</style>';

	document.body.appendChild(overlay);

	// Close on backdrop click
	overlay.addEventListener('click', function (e) {
		if (e.target === overlay) overlay.remove();
	});
}

function paceSetupProgrammeLinkFilter() {
	var n = 0;
	var t = setInterval(function () {
		var wf = window.frappe && frappe.web_form;
		if (wf && wf.fields_dict && wf.fields_dict.programme) {
			clearInterval(t);

			var _openPaceProgrammes = null;
			var fld = wf.get_field('programme');
			var queryFn = function () {
				if (_openPaceProgrammes && _openPaceProgrammes.length > 0) {
					return {
						filters: [
							['name', 'in', _openPaceProgrammes]
						]
					};
				}
				return {
					filters: [['name', '=', '__none__']]
				};
			};

			wf.set_query('programme', queryFn);
			if (fld && fld.df) {
				fld.df.get_query = queryFn;
			}

			frappe.call({
				method: 'slcm.pace.web_form.pace_application_form.pace_application_form.get_open_pace_programmes',
				callback: function (r) {
					_openPaceProgrammes = r.message || [];
				}
			});
		}
		if (++n > 100) clearInterval(t);
	}, 100);
}

function _paceShowErrorModal(message, customUrl, customLabel) {
	// Only show once
	if (document.getElementById('pace-error-modal')) return;

	var overlay = document.createElement('div');
	overlay.id = 'pace-error-modal';
	overlay.style.cssText = [
		'position:fixed', 'inset:0', 'z-index:9999',
		'display:flex', 'align-items:center', 'justify-content:center',
		'background:rgba(0,0,0,0.6)', 'backdrop-filter:blur(5px)'
	].join(';');

	var url = customUrl || '/merit-and-scholarship/admission_dashboard?panel=profile';
	var label = customLabel || __('My Profile');

	overlay.innerHTML =
		'<div style="max-width:480px;width:90%;background:#fff;border-radius:16px;padding:40px 32px;text-align:center;box-shadow:0 24px 60px rgba(0,0,0,0.2);position:relative;animation:paceErrorFadeIn 0.35s cubic-bezier(0.16, 1, 0.3, 1)">' +
			'<div style="width:72px;height:72px;background:linear-gradient(135deg,#ef4444,#dc2626);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 24px;box-shadow:0 8px 20px rgba(239,68,68,0.3)">' +
				'<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
					'<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>' +
					'<line x1="12" y1="9" x2="12" y2="13"/>' +
					'<line x1="12" y1="17" x2="12.01" y2="17"/>' +
				'</svg>' +
			'</div>' +
			'<h2 style="font-size:22px;font-weight:700;color:#111827;margin:0 0 14px">' + __('Admission Restriction') + '</h2>' +
			'<p style="font-size:14.5px;color:#4b5563;line-height:1.6;margin:0 0 32px;padding:0 8px">' + _paceEsc(message) + '</p>' +
			'<a href="' + url + '" style="display:inline-block;background:#7B1D1D;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;transition:background 0.2s,transform 0.1s;box-shadow:0 4px 12px rgba(123,29,29,0.2)">' + label + '</a>' +
		'</div>' +
		'<style>' +
			'@keyframes paceErrorFadeIn{from{opacity:0;transform:scale(0.95)}to{opacity:1;transform:scale(1)}}' +
			'#pace-error-modal a:hover{background:#5F1616 !important;}' +
		'</style>';

	document.body.appendChild(overlay);
}

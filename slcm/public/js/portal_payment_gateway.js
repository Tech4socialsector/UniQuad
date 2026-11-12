/*
 * Student / Parent Portal — gateway-aware checkout helpers.
 *
 * Every portal "create order" endpoint returns either a Razorpay order (opened in the Razorpay
 * popup, as before) or { gateway: "Easebuzz", checkout_url } for a full-page redirect to the
 * Easebuzz hosted checkout. Easebuzz sends the payer back with ?payment_ref=<txnid>; the page
 * then shows the outcome (slcm.api.easebuzz_payment.get_payment_result).
 *
 * "Pay All" endpoints may instead return { status: "split", groups } when the selected charges
 * are collected through different gateways; SlcmGateway.chooseSplit() lets the payer pay one
 * group at a time (the gateway is fixed per charge — the payer never picks it).
 */
(function () {
  'use strict';
  if (window.SlcmGateway) return;

  function csrf() {
    return window._sp_csrf || window.slcmGatewayCsrf || (window.frappe && frappe.csrf_token) ||
      decodeURIComponent((document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/) || [])[1] || '');
  }

  function call(method, args) {
    var body = new URLSearchParams();
    Object.keys(args || {}).forEach(function (k) { body.append(k, args[k] == null ? '' : args[k]); });
    return fetch('/api/method/' + method, {
      method: 'POST', credentials: 'same-origin', body: body,
      headers: { 'X-Frappe-CSRF-Token': csrf(), 'Accept': 'application/json' }
    }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) {
          var msg = '';
          try { msg = JSON.parse(JSON.parse(j._server_messages || '[]')[0] || '{}').message; } catch (e) { /* ignore */ }
          throw new Error(msg || j.exception || 'Request failed');
        }
        return j.message;
      });
    });
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var CSS = '' +
    '.sgw-ov{position:fixed;inset:0;background:rgba(15,23,42,.55);backdrop-filter:blur(3px);z-index:10050;display:flex;align-items:center;justify-content:center;padding:16px}' +
    '.sgw-box{background:var(--spf-card,#fff);color:var(--spf-text,#1f2937);border-radius:16px;max-width:460px;width:100%;max-height:90vh;overflow:auto;box-shadow:0 24px 64px rgba(0,0,0,.25);font-family:inherit}' +
    '.sgw-hd{padding:18px 20px 6px;font-size:16px;font-weight:700}' +
    '.sgw-sub{padding:0 20px 12px;font-size:13px;color:var(--spf-muted,#6b7280);line-height:1.5}' +
    '.sgw-grp{margin:0 16px 12px;border:1px solid var(--spf-border,#e5e7eb);border-radius:12px;padding:12px 14px}' +
    '.sgw-grp-hd{display:flex;justify-content:space-between;align-items:center;gap:8px;font-weight:700;font-size:14px}' +
    '.sgw-tag{font-size:11px;font-weight:600;color:var(--spf-muted,#6b7280);text-transform:uppercase;letter-spacing:.04em}' +
    '.sgw-item{display:flex;justify-content:space-between;gap:8px;font-size:13px;padding:4px 0;color:var(--spf-text,#374151)}' +
    '.sgw-btn{margin-top:10px;width:100%;min-height:42px;border:0;border-radius:10px;background:var(--spf-maroon,#920c24);color:#fff;font-weight:700;font-size:14px;cursor:pointer}' +
    '.sgw-btn[disabled]{opacity:.5;cursor:not-allowed}' +
    '.sgw-ft{padding:4px 16px 16px}' +
    '.sgw-cancel{width:100%;min-height:40px;border:1px solid var(--spf-border,#e5e7eb);border-radius:10px;background:transparent;color:inherit;font-weight:600;cursor:pointer}' +
    '.sgw-note{position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:10060;max-width:min(560px,calc(100vw - 32px));padding:12px 16px;border-radius:12px;font-size:14px;font-weight:600;box-shadow:0 12px 32px rgba(0,0,0,.18);color:#fff}' +
    '.sgw-ok{background:#15803d}.sgw-warn{background:#b45309}.sgw-err{background:#b91c1c}.sgw-info{background:#1d4ed8}';

  function injectCss() {
    if (document.getElementById('sgw-css')) return;
    var st = document.createElement('style'); st.id = 'sgw-css'; st.textContent = CSS;
    document.head.appendChild(st);
  }

  // sticky: stays until clicked (for messages the payer must read, e.g. "do not pay again")
  function notice(text, tone, sticky) {
    injectCss();
    var n = document.createElement('div');
    n.className = 'sgw-note sgw-' + (tone || 'info'); n.setAttribute('role', 'status'); n.textContent = text;
    document.body.appendChild(n);
    if (sticky) {
      n.title = 'Click to close'; n.style.cursor = 'pointer';
      n.addEventListener('click', function () { n.remove(); });
    } else {
      setTimeout(function () { n.remove(); }, 6000);
    }
  }

  var SlcmGateway = {
    call: call,

    /** True when the order must be paid on the Easebuzz hosted page. */
    isRedirect: function (order) {
      return !!(order && order.gateway === 'Easebuzz' && order.checkout_url);
    },

    /** Go to the hosted checkout (keeps the page's own "processing" state while navigating). */
    redirect: function (order) {
      SlcmGateway._leftForCheckout = true;
      window.location.assign(order.checkout_url);
    },

    isSplit: function (res) { return !!(res && res.status === 'split' && res.groups && res.groups.length); },

    /**
     * The selection spans gateways: show one checkout per gateway.
     * onPick(group) is called with the chosen group; onCancel() when dismissed.
     */
    chooseSplit: function (res, onPick, onCancel) {
      injectCss();
      var ov = document.createElement('div');
      ov.className = 'sgw-ov';
      var html = '<div class="sgw-box" role="dialog" aria-modal="true" aria-labelledby="sgw-title">' +
        '<div class="sgw-hd" id="sgw-title">Pay in ' + res.groups.length + ' parts</div>' +
        '<div class="sgw-sub">These charges are collected through different secure payment partners, so they are paid separately. ' +
        'Pay one part now; the rest stays on your fee page.</div>';
      res.groups.forEach(function (g, i) {
        html += '<div class="sgw-grp"><div class="sgw-grp-hd"><span>Part ' + (i + 1) + ' · ' + esc(g.formatted_total) + '</span>' +
          '<span class="sgw-tag">via ' + esc(g.gateway) + '</span></div>';
        (g.items || []).forEach(function (it) {
          html += '<div class="sgw-item"><span>' + esc(it.label) + '</span><span>' + esc(it.amount) + '</span></div>';
        });
        html += '<button type="button" class="sgw-btn" data-i="' + i + '"' + (g.ready ? '' : ' disabled') + '>' +
          (g.ready ? 'Pay ' + esc(g.formatted_total) : 'Not available yet — contact the Finance Office') + '</button></div>';
      });
      html += '<div class="sgw-ft"><button type="button" class="sgw-cancel">Cancel</button></div></div>';
      ov.innerHTML = html;
      document.body.appendChild(ov);
      var prevOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
      function close() { document.removeEventListener('keydown', onKey); ov.remove(); document.body.style.overflow = prevOverflow; }
      function onKey(e) { if (e.key === 'Escape') { close(); if (onCancel) onCancel(); } }
      document.addEventListener('keydown', onKey);
      ov.addEventListener('click', function (e) {
        var b = e.target.closest('.sgw-btn');
        if (b && !b.disabled) { close(); onPick(res.groups[+b.getAttribute('data-i')]); return; }
        if (e.target === ov || e.target.closest('.sgw-cancel')) { close(); if (onCancel) onCancel(); }
      });
      var first = ov.querySelector('.sgw-btn:not([disabled])'); if (first) first.focus();
    },

    /** On load: report the outcome of an Easebuzz checkout that returned here. */
    handleReturn: function (opts) {
      opts = opts || {};
      var params = new URLSearchParams(window.location.search);
      var ref = params.get('payment_ref');
      if (!ref) return;
      params.delete('payment_ref');
      var qs = params.toString();
      history.replaceState(null, '', window.location.pathname + (qs ? '?' + qs : '') + window.location.hash);
      var say = opts.notify || notice;
      say('Checking your payment…', 'info');
      var tries = 0;
      (function poll() {
        call('slcm.api.easebuzz_payment.get_payment_result', { payment_ref: ref }).then(function (r) {
          if (r.status === 'pending' && ++tries < 5) { setTimeout(poll, 3000); return; }
          if (r.status === 'success') {
            say('Payment of ' + r.formatted_amount + ' received. Thank you!', 'ok');
            // Settled after this page was rendered (while we waited, or by this very check):
            // refresh once so the charge shows as paid
            if (tries > 0 || r.settled_now) setTimeout(function () { window.location.reload(); }, 2500);
            if (opts.onSuccess) opts.onSuccess(r);
          } else if (r.status === 'duplicate') {
            say((r.refund_amount && r.refund_amount + 0.01 < r.amount)
              ? 'Some of these fees were already paid. ' + r.formatted_refund + ' of your payment will be refunded by the Finance Office.'
              : 'These fees were already paid. Your payment of ' + r.formatted_amount + ' will be refunded by the Finance Office.',
              'warn', true);
            setTimeout(function () { window.location.reload(); }, 6000);
          } else if (r.status === 'received') {
            say('Payment of ' + r.formatted_amount + ' received' +
              (r.payment_id ? ' (Ref: ' + r.payment_id + ')' : '') +
              '. It will show as paid shortly. Please do not pay again.', 'warn', true);
          } else if (r.status === 'cancelled') {
            say('Payment was cancelled. No money was taken.', 'warn');
          } else if (r.status === 'failed') {
            say('Payment did not go through. Please try again.', 'err');
          } else {
            say('Your payment is being confirmed by the bank. This page will show it within a few minutes.', 'warn');
          }
          if (opts.onDone) opts.onDone(r);
        }).catch(function (e) { say(e.message || 'Could not check the payment status.', 'err'); });
      }());
    }
  };

  // Back button from the hosted checkout restores this page from the bfcache still locked in
  // "Redirecting…": reload it so buttons and statuses are current.
  window.addEventListener('pageshow', function (e) {
    if (e.persisted && SlcmGateway._leftForCheckout) window.location.reload();
  });

  window.SlcmGateway = SlcmGateway;
}());

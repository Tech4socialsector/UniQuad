/*!
 * StageTracker — reusable admission pipeline widget
 * Used by: /nlsat/my-applications (compact) and /applicant-form (full)
 *
 * Usage:
 *   StageTracker.init({
 *     container: '#stage-tracker-wrap',   // CSS selector or DOM element
 *     applicant:  'APP-2026-00001',        // Applicant document name
 *     mode:       'full' | 'compact',     // full = all labels, compact = scroll
 *     csrf:        window.csrf_token
 *   });
 */

(function (global) {
  'use strict';

  var StageTracker = {};

  // ── Status config ────────────────────────────────────────────────
  var STATUS = {
    completed:  { icon: '✓', cls: 'st-completed', line: 'st-line-done'    },
    active:     { icon: '●', cls: 'st-active',    line: 'st-line-active'  },
    pending:    { icon: '',  cls: 'st-pending',    line: 'st-line-pending' },
    rejected:   { icon: '✕', cls: 'st-rejected',  line: 'st-line-done'    },
    waitlisted: { icon: '⏸', cls: 'st-waitlisted',line: 'st-line-active'  },
  };

  // Stage type → icon emoji
  var TYPE_ICON = {
    'Application':  '📝',
    'Screening':    '🔍',
    'Exam':         '✏️',
    'Interview':    '🎤',
    'Evaluation':   '📊',
    'Merit':        '🏆',
    'Document':     '📁',
    'Fee':          '💳',
    'Enrollment':   '🎓',
    '':             '◉',
  };

  // ── Public API ───────────────────────────────────────────────────
  StageTracker.init = function (opts) {
    opts = opts || {};
    var container = typeof opts.container === 'string'
      ? document.querySelector(opts.container)
      : opts.container;

    if (!container) {
      console.warn('StageTracker: container not found', opts.container);
      return;
    }

    var mode = opts.mode || 'full';

    // Show skeleton while loading
    container.innerHTML = _skeleton(mode);

    // Fetch data
    _fetchTrackerData(opts.applicant, opts.csrf, function (err, data) {
      if (err || !data || !data.stages || data.stages.length === 0) {
        container.innerHTML = '<div class="st-empty">No stages configured for this cycle.</div>';
        return;
      }
      container.innerHTML = _render(data, mode);
      _bindActions(container);
      // Scroll active stage into view on compact mode
      if (mode === 'compact') {
        var activeNode = container.querySelector('.st-node.st-active');
        if (activeNode) {
          activeNode.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
        }
      }
    });
  };

  // ── Fetch ────────────────────────────────────────────────────────
  function _fetchTrackerData(applicant, csrf, cb) {
    fetch('/api/method/slcm.admission.utils.web.get_stage_tracker_data', {
      method:  'POST',
      headers: {
        'Content-Type':        'application/json',
        'X-Frappe-CSRF-Token': csrf || ''
      },
      body: JSON.stringify({ applicant_name: applicant })
    })
    .then(function (r) { return r.json(); })
    .then(function (d) { cb(null, d.message); })
    .catch(function (e) { cb(e, null); });
  }

  // ── Render ───────────────────────────────────────────────────────
  function _render(data, mode) {
    var stages     = data.stages || [];
    var trackType  = data.track_type || 'normal';
    var appStatus  = data.app_status || '';

    var html = '<div class="st-wrapper st-mode-' + mode + '">';

    // Status banner for terminal states
    if (appStatus === 'Rejected') {
      html += '<div class="st-banner st-banner-rejected">'
            + '✕ Application not shortlisted at this stage.'
            + '</div>';
    } else if (trackType === 'waitlisted') {
      html += '<div class="st-banner st-banner-waitlisted">'
            + '⏸ You are currently on the waitlist. We will notify you if a seat becomes available.'
            + '</div>';
    } else if (appStatus === 'Offer Issued') {
      html += '<div class="st-banner st-banner-offer">'
            + '🎉 Congratulations! An offer has been issued. Please accept before the deadline.'
            + '</div>';
    }

    // Stage rail
    html += '<div class="st-rail">';

    stages.forEach(function (stage, idx) {
      var sc     = STATUS[stage.status] || STATUS.pending;
      var isLast = idx === stages.length - 1;
      var icon   = TYPE_ICON[stage.stage_type] || TYPE_ICON[''];
      var seq    = stage.sequence || (idx + 1);

      // Node
      html += '<div class="st-node ' + sc.cls + '" data-stage="' + _esc(stage.stage_name) + '">';

      // Circle
      html += '<div class="st-circle">';
      if (stage.status === 'completed') {
        html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"'
              + ' stroke="currentColor" stroke-width="3">'
              + '<polyline points="20 6 9 17 4 12"/></svg>';
      } else if (stage.status === 'rejected') {
        html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"'
              + ' stroke="currentColor" stroke-width="3">'
              + '<line x1="18" y1="6" x2="6" y2="18"/>'
              + '<line x1="6" y1="6" x2="18" y2="18"/></svg>';
      } else if (stage.status === 'waitlisted') {
        html += '⏸';
      } else if (stage.status === 'active') {
        html += '<div class="st-pulse"></div>';
        html += seq;
      } else {
        html += seq;
      }
      html += '</div>'; // .st-circle

      // Label block (hidden in compact on non-active)
      var labelCls = 'st-label';
      if (mode === 'compact' && stage.status !== 'active') {
        labelCls += ' st-label-hide';
      }
      html += '<div class="' + labelCls + '">';
      html += '<div class="st-stage-icon">' + icon + '</div>';
      html += '<div class="st-stage-name">' + _esc(stage.stage_name) + '</div>';
      if (stage.reached_on) {
        html += '<div class="st-stage-date">' + stage.reached_on + '</div>';
      }
      // Action button
      if (stage.show_action && stage.action_label) {
        html += '<a href="' + _esc(stage.action_url || '#') + '"'
              + ' class="st-action-btn">'
              + _esc(stage.action_label)
              + '</a>';
      }
      html += '</div>'; // .st-label

      html += '</div>'; // .st-node

      // Connector line between nodes
      if (!isLast) {
        html += '<div class="st-connector ' + sc.line + '"></div>';
      }
    });

    html += '</div>'; // .st-rail
    html += '</div>'; // .st-wrapper
    return html;
  }

  // ── Skeleton loader ──────────────────────────────────────────────
  function _skeleton(mode) {
    var n = mode === 'compact' ? 4 : 6;
    var html = '<div class="st-wrapper st-skeleton st-mode-' + mode + '"><div class="st-rail">';
    for (var i = 0; i < n; i++) {
      html += '<div class="st-node st-pending">'
            + '<div class="st-circle st-skel-circle"></div>'
            + '<div class="st-label"><div class="st-skel-line"></div></div>'
            + '</div>';
      if (i < n - 1) html += '<div class="st-connector st-line-pending"></div>';
    }
    html += '</div></div>';
    return html;
  }

  // ── Action binding ───────────────────────────────────────────────
  function _bindActions(container) {
    // Tooltip on hover — show date on any node
    container.querySelectorAll('.st-node').forEach(function (node) {
      node.addEventListener('mouseenter', function () {
        var label = node.querySelector('.st-label');
        if (label) label.classList.remove('st-label-hide');
      });
      node.addEventListener('mouseleave', function () {
        // Only re-hide in compact mode for non-active nodes
        var wrapper = node.closest('.st-mode-compact');
        if (wrapper && !node.classList.contains('st-active')) {
          var label = node.querySelector('.st-label');
          if (label) label.classList.add('st-label-hide');
        }
      });
    });
  }

  // ── Utils ────────────────────────────────────────────────────────
  function _esc(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Expose globally
  global.StageTracker = StageTracker;

}(window));

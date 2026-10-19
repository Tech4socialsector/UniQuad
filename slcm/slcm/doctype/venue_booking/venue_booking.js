frappe.listview_settings['Venue Booking'] = {
    add_fields: ['status', 'docstatus'],

    refresh: function (listview) {
        if (!frappe.user.has_role(['System Manager', 'Administrator', 'slcm_Registrar'])) return;

        // ── Guard: run setup only once per listview instance ──────────────────
        if (listview.__vb_bulk_setup) return;
        listview.__vb_bulk_setup = true;

        const STATUSES = [
            { status: 'Pending Allotment', color: '#f59e0b', indicator: 'orange' },
            { status: 'Allotted', color: '#10b981', indicator: 'green' },
            { status: 'Rejected', color: '#ef4444', indicator: 'red' },
            { status: 'Cancelled', color: '#6b7280', indicator: 'grey' }
        ];

        // ── 1a. Standalone Allot / Reject buttons (top-level, always visible) ──
        listview.page.add_inner_button(
            __('Allot'),
            function () { vb_bulk_action(listview, STATUSES[1]); } // Allotted
        );
        listview.page.add_inner_button(
            __('Reject'),
            function () { vb_bulk_action(listview, STATUSES[2]); } // Rejected
        );

        // Frappe's page-actions template ships the custom-actions container with
        // "hidden-xs hidden-md" classes, which hide ALL custom toolbar buttons
        // (this one included) via `display:none` whenever the browser window
        // width falls in the 992–1199px range. Force it visible regardless of
        // window size so these buttons don't silently disappear.
        listview.page.inner_toolbar.removeClass('hidden-xs hidden-md');

        // ── 1b. Page toolbar buttons (always visible in top bar) ────────────────
        STATUSES.forEach(function (cfg) {
            listview.page.add_inner_button(
                __('Mark {0}', [cfg.status]),
                function () { vb_bulk_action(listview, cfg); },
                __('Bulk Status')
            );
        });

        // ── 2. Actions dropdown items (visible when rows are selected) ─────────
        STATUSES.forEach(function (cfg) {
            listview.page.add_actions_menu_item(
                __('Mark as {0}', [cfg.status]),
                function () { vb_bulk_action(listview, cfg); }
            );
        });

        // ── 3. Colored buttons inside the "N items selected" selection bar ─────
        function inject_selection_bar_buttons() {
            if (!listview.$result) return;
            var $bar = listview.$result.find('header .checkbox-actions');
            if (!$bar.length) return;
            if ($bar.find('.vb-status-btn').length) return; // already there

            var $wrap = $('<span></span>').css({
                'margin-left': '14px',
                'display': 'inline-flex',
                'gap': '5px',
                'align-items': 'center',
                'flex-wrap': 'wrap'
            });

            STATUSES.forEach(function (cfg) {
                $('<button class="btn btn-xs vb-status-btn"></button>')
                    .text(__(cfg.status))
                    .css({
                        'background': cfg.color,
                        'color': '#fff',
                        'border': 'none',
                        'border-radius': '4px',
                        'padding': '3px 10px',
                        'font-size': '12px',
                        'font-weight': '600',
                        'cursor': 'pointer',
                        'line-height': '1.4'
                    })
                    .on('click', function (e) {
                        e.stopPropagation();
                        e.preventDefault();
                        vb_bulk_action(listview, cfg);
                    })
                    .appendTo($wrap);
            });

            // Append after the "N items selected" meta span
            $bar.find('.level.list-subject').append($wrap);
        }

        // Override on_row_checked so buttons appear every time rows are checked
        var _orig_row_checked = listview.on_row_checked.bind(listview);
        listview.on_row_checked = function () {
            _orig_row_checked();
            // Re-inject after each check (header may have been re-rendered)
            if (listview.$checks && listview.$checks.length > 0) {
                inject_selection_bar_buttons();
            }
        };

        // Also inject on the result area's click events (belt-and-suspenders)
        listview.$result && listview.$result.on('change.vb_bulk', '.list-row-checkbox', function () {
            setTimeout(inject_selection_bar_buttons, 0);
        });
    },

    formatters: {
        status: function (value, df, doc) {
            // Booking allotment status badge
            const approvalCfg = {
                'Pending Allotment': { bg: '#fef3c7', color: '#92400e', icon: '⏳', label: 'Pending Allotment' },
                'Allotted': { bg: '#d1fae5', color: '#065f46', icon: '✓', label: 'Allotted' },
                'Rejected': { bg: '#fee2e2', color: '#991b1b', icon: '✗', label: 'Rejected' },
                'Cancelled': { bg: '#f3f4f6', color: '#6b7280', icon: '⊘', label: 'Cancelled' }
            };
            const a = approvalCfg[value] || { bg: '#e0f2fe', color: '#0369a1', icon: '•', label: value || '—' };

            return `<span style="background:${a.bg};color:${a.color};
                    padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;
                    white-space:nowrap;display:inline-flex;align-items:center;gap:3px;">
                    ${a.icon} ${a.label}
                </span>`;
        }
    },

    get_indicator: function (doc) {
        const map = {
            'Allotted': ['Allotted', 'green', 'status,=,Allotted'],
            'Rejected': ['Rejected', 'red', 'status,=,Rejected'],
            'Cancelled': ['Cancelled', 'grey', 'status,=,Cancelled'],
            'Pending Allotment': ['Pending Allotment', 'orange', 'status,=,Pending Allotment'],
        };
        return map[doc.status] || ['Pending Allotment', 'orange', 'status,=,Pending Allotment'];
    }
};

frappe.ui.form.on('Venue Booking', {
    onload: function (frm) {
        if (frm.is_new()) {
            _auto_fill_requester(frm);
        }
    },

    setup: function(frm) {
        frm.set_query("venue", function() {
            return {
                query: "slcm.slcm.doctype.venue_booking.venue_booking.get_venue_query",
                filters: {
                    venue_type: frm.doc.venue_type
                }
            };
        });
    },

    refresh: function (frm) {
        _toggle_student_field(frm);

        const canManage = frappe.user.has_role([
            'System Manager', 'Administrator', 'slcm_Registrar'
        ]);

        // ── Recurring series: link back to the parent, or list this series' occurrences ──
        if (!frm.is_new() && frm.doc.parent_booking) {
            frm.dashboard.add_comment(
                __('This booking is part of a recurring series started by {0}.',
                    [`<a href="/app/venue-booking/${frm.doc.parent_booking}">${frm.doc.parent_booking}</a>`]),
                'blue', true
            );
        }
        if (!frm.is_new() && frm.doc.is_recurring && !frm.doc.parent_booking) {
            frm.add_custom_button(__('View Occurrences'), function () {
                frappe.set_route('List', 'Venue Booking', { parent_booking: frm.doc.name });
            });
        }

        if (!frm.is_new() && canManage) {

            // ── Swap Request banner + actions ──────────────────────────
            if (frm.doc.swap_requested && frm.doc.swap_status === 'Pending') {
                const reqRoom = frm.doc.swap_requested_venue || '—';
                const reqReason = frm.doc.swap_request_reason
                    ? `<br><span style="color:#555;font-size:12px;">Reason: ${frm.doc.swap_request_reason}</span>`
                    : '';
                frm.dashboard.add_comment(
                    `<span style="color:#92400e;">&#x21C4; Swap Request Pending</span> — wants to move to <strong>${reqRoom}</strong>${reqReason}`,
                    'yellow', true
                );

                frm.add_custom_button(__('Approve Swap'), function () {
                    frappe.prompt([{
                        label: __('Admin Remarks (optional)'),
                        fieldname: 'admin_remarks',
                        fieldtype: 'Small Text'
                    }], function (vals) {
                        frappe.call({
                            method: 'slcm.slcm.doctype.venue_booking.venue_booking.approve_venue_swap',
                            args: { booking_name: frm.doc.name, admin_remarks: vals.admin_remarks || '' },
                            freeze: true, freeze_message: __('Approving swap…'),
                            callback: function (r) {
                                if (!r.exc) {
                                    frappe.show_alert({ message: __('Swap Approved — venue updated'), indicator: 'green' });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }, __('Approve Swap Request'), __('Approve'));
                }, __('Swap Request'));

                frm.add_custom_button(__('Reject Swap'), function () {
                    frappe.prompt([{
                        label: __('Reason for Rejection'),
                        fieldname: 'admin_remarks',
                        fieldtype: 'Small Text',
                        reqd: 1
                    }], function (vals) {
                        frappe.call({
                            method: 'slcm.slcm.doctype.venue_booking.venue_booking.reject_venue_swap',
                            args: { booking_name: frm.doc.name, admin_remarks: vals.admin_remarks || '' },
                            freeze: true, freeze_message: __('Rejecting swap…'),
                            callback: function (r) {
                                if (!r.exc) {
                                    frappe.show_alert({ message: __('Swap Request Rejected'), indicator: 'red' });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }, __('Reject Swap Request'), __('Reject'));
                }, __('Swap Request'));
            }

            // ── Allot (Pending Allotment only) ─────────────────────────
            if (frm.doc.status === 'Pending Allotment') {
                frm.add_custom_button(__('Allot'), function () {
                    frappe.prompt([
                        {
                            label: __('Remarks (optional)'),
                            fieldname: 'admin_remarks',
                            fieldtype: 'Small Text'
                        }
                    ], function (values) {
                        frappe.call({
                            method: 'slcm.slcm.doctype.venue_booking.venue_booking.approve_booking',
                            args: {
                                booking_name: frm.doc.name,
                                admin_remarks: values.admin_remarks || ''
                            },
                            freeze: true,
                            freeze_message: __('Allotting…'),
                            callback: function (r) {
                                if (!r.exc) {
                                    frappe.show_alert({ message: __('Booking Allotted'), indicator: 'green' });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }, __('Allot Booking'), __('Allot'));
                }, __('Actions'));

                // ── Reject (Pending Allotment only) ────────────────────
                frm.add_custom_button(__('Reject'), function () {
                    frappe.prompt([
                        {
                            label: __('Reason for Rejection'),
                            fieldname: 'admin_remarks',
                            fieldtype: 'Small Text',
                            reqd: 1
                        }
                    ], function (values) {
                        frappe.call({
                            method: 'slcm.slcm.doctype.venue_booking.venue_booking.reject_booking',
                            args: {
                                booking_name: frm.doc.name,
                                admin_remarks: values.admin_remarks || ''
                            },
                            freeze: true,
                            freeze_message: __('Rejecting…'),
                            callback: function (r) {
                                if (!r.exc) {
                                    frappe.show_alert({ message: __('Booking Rejected'), indicator: 'red' });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }, __('Reject Booking'), __('Reject'));
                }, __('Actions'));
            }

            // ── Cancel (Pending Allotment or Allotted) ──────────────────
            if (['Pending Allotment', 'Allotted'].includes(frm.doc.status)) {
                frm.add_custom_button(__('Cancel Booking'), function () {
                    frappe.prompt([
                        {
                            label: __('Reason for Cancellation'),
                            fieldname: 'admin_remarks',
                            fieldtype: 'Small Text'
                        }
                    ], function (values) {
                        frappe.call({
                            method: 'slcm.slcm.doctype.venue_booking.venue_booking.cancel_booking',
                            args: {
                                booking_name: frm.doc.name,
                                admin_remarks: values.admin_remarks || ''
                            },
                            freeze: true,
                            freeze_message: __('Cancelling…'),
                            callback: function (r) {
                                if (!r.exc) {
                                    frappe.show_alert({ message: __('Booking Cancelled'), indicator: 'orange' });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }, __('Cancel Booking'), __('Confirm Cancel'));
                }, __('Actions'));
            }

            // ── Swap Venue ─────────────────────────────────────────────
            if (frm.doc.docstatus < 2) {
                frm.add_custom_button(__('Swap Venue'), function () {
                    // Fetch all swappable bookings with their time details
                    frappe.call({
                        method: 'frappe.client.get_list',
                        args: {
                            doctype: 'Venue Booking',
                            filters: [
                                ['name', '!=', frm.doc.name],
                                ['docstatus', '<', 2],
                                ['status', '!=', 'Cancelled']
                            ],
                            fields: ['name', 'event_name', 'venue', 'start_datetime', 'end_datetime', 'status'],
                            order_by: 'start_datetime asc',
                            limit: 200
                        },
                        callback: function (r) {
                            const bookings = r.message || [];
                            if (!bookings.length) {
                                frappe.msgprint(__('No other bookings available to swap with.'));
                                return;
                            }

                            function fmt_dt(dt) {
                                if (!dt) return '—';
                                const d = frappe.datetime.str_to_obj(dt);
                                return frappe.datetime.get_datetime_as_string(d)
                                    .replace(/:\d{2}$/, ''); // trim seconds
                            }

                            const options = bookings.map(b => {
                                const start = fmt_dt(b.start_datetime);
                                const end = fmt_dt(b.end_datetime);
                                const label = `${b.name} | ${b.event_name || '—'} | ${b.venue || '—'} | ${start} → ${end} [${b.status}]`;
                                return { value: b.name, label: label };
                            });

                            const d = new frappe.ui.Dialog({
                                title: __('Swap Venue'),
                                fields: [
                                    {
                                        label: __('Current Booking'),
                                        fieldname: 'current_info',
                                        fieldtype: 'HTML',
                                        options: `<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:6px;padding:10px 14px;margin-bottom:4px;font-size:12px;">
                                            <strong>${frm.doc.name}</strong> — ${frm.doc.event_name || '—'}<br>
                                            <span style="color:#0369a1;">
                                                📍 ${frm.doc.venue || '—'} &nbsp;|&nbsp;
                                                🕐 ${fmt_dt(frm.doc.start_datetime)} → ${fmt_dt(frm.doc.end_datetime)}
                                            </span>
                                        </div>`
                                    },
                                    {
                                        label: __('Select Booking to Swap With'),
                                        fieldname: 'other_booking',
                                        fieldtype: 'Select',
                                        options: [''].concat(options.map(o => o.value)),
                                        reqd: 1,
                                        description: __('Showing: Booking ID | Event | Venue | Start → End [Status]')
                                    },
                                    {
                                        label: __('Selected Booking Details'),
                                        fieldname: 'selected_info',
                                        fieldtype: 'HTML',
                                        options: '<div id="vb-swap-detail" style="min-height:20px;"></div>'
                                    }
                                ],
                                primary_action_label: __('Swap Venues'),
                                primary_action: function (vals) {
                                    if (!vals.other_booking) {
                                        frappe.msgprint(__('Please select a booking to swap with.'));
                                        return;
                                    }
                                    frappe.call({
                                        method: 'slcm.slcm.doctype.venue_booking.venue_booking.swap_venues',
                                        args: { booking_a: frm.doc.name, booking_b: vals.other_booking },
                                        freeze: true,
                                        freeze_message: __('Swapping venues…'),
                                        callback: function (r) {
                                            if (!r.exc) {
                                                frappe.show_alert({ message: __('Venues swapped successfully'), indicator: 'green' });
                                                d.hide();
                                                frm.reload_doc();
                                            }
                                        }
                                    });
                                }
                            });

                            // Replace select options with labelled display
                            d.show();
                            setTimeout(function () {
                                const $sel = d.get_field('other_booking').$input;
                                $sel.find('option').each(function () {
                                    const val = $(this).val();
                                    if (!val) return;
                                    const match = options.find(o => o.value === val);
                                    if (match) $(this).text(match.label);
                                });

                                // Show detail card on selection
                                $sel.on('change', function () {
                                    const val = $(this).val();
                                    const bk = bookings.find(b => b.name === val);
                                    const $el = d.wrapper.find('#vb-swap-detail');
                                    if (!bk) { $el.html(''); return; }
                                    $el.html(`<div style="background:#fefce8;border:1px solid #fde047;border-radius:6px;padding:10px 14px;font-size:12px;margin-top:4px;">
                                        <strong>${bk.name}</strong> — ${bk.event_name || '—'}<br>
                                        <span style="color:#854d0e;">
                                            📍 ${bk.venue || '—'} &nbsp;|&nbsp;
                                            🕐 ${fmt_dt(bk.start_datetime)} → ${fmt_dt(bk.end_datetime)} &nbsp;|&nbsp;
                                            Status: <b>${bk.status}</b>
                                        </span>
                                    </div>`);
                                });
                            }, 200);
                        }
                    });
                }, __('Actions'));
            }
        }

        // ── Status colour banner ───────────────────────────────────────
        _set_status_banner(frm);
    },

    venue_type: function (frm) {
        // query is handled in setup, but if we need to clear venue on type change:
        if (frm.doc.venue) {
            frm.set_value('venue', '');
        }
    },

    venue: function (frm) {
        if (frm.doc.venue && frm.doc.venue_type) {
            frappe.call({
                method: "slcm.slcm.doctype.venue_booking.venue_booking.get_venue_query",
                args: {
                    doctype: "Venue Master",
                    txt: frm.doc.venue,
                    searchfield: "name",
                    start: 0,
                    page_len: 1,
                    filters: { venue_type: frm.doc.venue_type }
                },
                callback: function(r) {
                    if (!r.message || r.message.length === 0 || r.message[0][0] !== frm.doc.venue) {
                        frappe.msgprint(__("You don't have permission to book this room, or it's invalid."));
                        frm.set_value('venue', '');
                    }
                }
            });
        }
    },

    requester_type: function (frm) {
        _toggle_student_field(frm);
    }
});


// ─────────────────────────────────────────────────────────────────────────────
//  Helpers
// ─────────────────────────────────────────────────────────────────────────────

function _auto_fill_requester(frm) {
    // Set requester_name from current user's full name
    if (!frm.doc.requester_name) {
        frappe.call({
            method: 'frappe.client.get_value',
            args: {
                doctype: 'User',
                filters: { name: frappe.session.user },
                fieldname: 'full_name'
            },
            callback: function (r) {
                if (r.message && r.message.full_name) {
                    frm.set_value('requester_name', r.message.full_name);
                }
            }
        });
    }

    // Auto-detect requester_type from roles
    if (!frm.doc.requester_type) {
        const roles = frappe.user_roles || [];
        let rtype = 'Other';
        if (roles.includes('slcm_Student')) rtype = 'Student';
        else if (roles.includes('slcm_Faculty')) rtype = 'Faculty';
        else if (roles.includes('slcm_Staff')) rtype = 'Staff';
        frm.set_value('requester_type', rtype);
    }
}

function _toggle_student_field(frm) {
    const isStudent = (frm.doc.requester_type === 'Student');
    frm.toggle_display('student', isStudent);
    frm.toggle_reqd('student', false); // student is always optional (auto-filled server-side)
}

function _set_status_banner(frm) {
    if (frm.is_new()) return;
    const colors = {
        'Pending Allotment': 'yellow',
        'Allotted': 'green',
        'Rejected': 'red',
        'Cancelled': 'grey'
    };
    const indicator = colors[frm.doc.status] || 'blue';
    frm.set_indicator_formatter('status', function () { return indicator; });
}


// ─────────────────────────────────────────────────────────────────────────────
//  List-view: bulk status action handler
// ─────────────────────────────────────────────────────────────────────────────
function vb_bulk_action(listview, cfg) {
    var selected = listview.get_checked_items();
    if (!selected.length) {
        frappe.msgprint(__('Please select at least one booking.'));
        return;
    }
    var names = selected.map(function (r) { return r.name; });

    var d = new frappe.ui.Dialog({
        title: __('Mark {0} booking(s) as "{1}"', [names.length, cfg.status]),
        fields: [{
            label: __('Admin Remarks (optional)'),
            fieldname: 'admin_remarks',
            fieldtype: 'Small Text'
        }],
        primary_action_label: __(cfg.status),
        primary_action: function (vals) {
            d.hide();
            frappe.call({
                method: 'slcm.api.student_portal.bulk_update_venue_booking_status',
                args: {
                    booking_names: names,
                    status: cfg.status,
                    admin_remarks: vals.admin_remarks || ''
                },
                freeze: true,
                freeze_message: __('Updating…'),
                callback: function (r) {
                    if (r.exc) return;
                    var updated = (r.message || {}).updated || names.length;
                    frappe.show_alert({
                        message: __('{0} booking(s) marked as {1}', [updated, cfg.status]),
                        indicator: cfg.indicator
                    });
                    listview.refresh();
                }
            });
        }
    });
    d.show();
}


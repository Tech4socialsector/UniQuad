frappe.ui.form.on("Interview List", {
    refresh: function (frm) {

        // ── Status intro message ───────────────────────────────────────────────
        if (frm.doc.status === "Generated") {
            frm.set_intro(
                __("Interview List generated. Use the <b>Allocate Slots</b> button below to allocate interview slots."),
                "blue"
            );
        } else if (frm.doc.status === "In Progress") {
            frm.set_intro(__("Interview slot allocation is in progress."), "orange");
        } else if (frm.doc.status === "Completed") {
            frm.set_intro(__("Interview process completed."), "green");
        }

        // ── Source breakdown dashboard ────────────────────────────────────────
        if (frm.doc.interview_applicant && frm.doc.interview_applicant.length) {
            const rows = frm.doc.interview_applicant;
            const total = rows.length;
            const cnt = {};
            rows.forEach(r => {
                const src = r.source_type || "Unknown";
                cnt[src] = (cnt[src] || 0) + 1;
            });
            let breakdown = Object.entries(cnt)
                .map(([src, n]) => `<b>${src}:</b> ${n}`)
                .join("&nbsp;&nbsp;|&nbsp;&nbsp;");
        }

        
        // Hide only if user is strictly an Interview Staff Member (and not an Admin/Manager)
        let is_staff_only = frappe.user_roles.includes("Interview Staff Member") && 
                           !frappe.user_roles.includes("System Manager") && 
                           !frappe.user_roles.includes("Interview Admin") && 
                           !frappe.user_roles.includes("Entrance Test Admin");

        if (frm.doc.status === "Generated" && !is_staff_only) {
            frm.add_custom_button(__("Allocate Slots"), function () {
                open_slot_dialog(frm);
            })
        }
    }
});


// ─────────────────────────────────────────────────────────────────────────────
// Dialog helpers
// ─────────────────────────────────────────────────────────────────────────────

function open_slot_dialog(frm) {
    const all_applicants = frm.doc.interview_applicant || [];
    const applicants = all_applicants.filter(a => a.interview_status !== "Scheduled");

    if (!applicants.length) {
        const total = all_applicants.length;
        if (total === 0) {
            frappe.msgprint({
                title: __("No Applicants Found"),
                message: __("This Interview List is empty. Please ensure applicants are added before attempting to allocate slots."),
                indicator: "orange"
            });
        } else {
            frappe.msgprint({
                title: __("Scheduling Already Completed"),
                message: __("All <b>{0}</b> applicants in this list have already been scheduled for an interview. <br><br>The system has verified that there are no pending students left for interview slot allocation in this list.", [total]),
                indicator: "blue"
            });
        }
        return;
    }

    // Fetch active Interview Staff Members for this campus
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Interview Staff Member",
            filters: {
                is_active: 1,
                campus: frm.doc.campus,
                academic_year: frm.doc.academic_year,
                admission_cycle: frm.doc.admission_cycle
            },
            fields: ["name", "staff_name", "designation", "email", "contact_number"],
            limit_page_length: 100
        },
        callback: function (r) {
            const staff_list = r.message || [];
            if (!staff_list.length) {
                frappe.msgprint({
                    title: __("No Staff Members Found"),
                    message: __(
                        "No active Interview Staff Members found for this campus, "
                        + "academic year and admission cycle. "
                        + "Please create staff members first."
                    ),
                    indicator: "orange"
                });
                return;
            }
            _show_slot_dialog(frm, applicants, staff_list);
        }
    });
}


function _show_slot_dialog(frm, applicants, staff_list) {
    const selected_applicant_names = new Set();
    let applicant_current_page = 1;
    const applicant_page_size = 10;

    let selected_staff = staff_list.length > 0 ? staff_list[0].name : null;
    let staff_current_page = 1;
    const staff_page_size = 9; // 3x3 grid
    let staff_search_query = "";

    let applicant_filters = {
        applicant_id: "",
        candidate_name: "",
        programme: ""
    };

    function get_filtered_staff() {
        const q = staff_search_query.toLowerCase().trim();
        return staff_list.filter(s => {
            const name = (s.staff_name || "").toLowerCase();
            const desig = (s.designation || "").toLowerCase();
            const email = (s.email || "").toLowerCase();
            return name.includes(q) || desig.includes(q) || email.includes(q);
        });
    }

    function get_filtered_applicants() {
        return applicants.filter(a => {
            const id_match = !applicant_filters.applicant_id || (a.applicant_id || "").toLowerCase().includes(applicant_filters.applicant_id);
            const name_match = !applicant_filters.candidate_name || (a.candidate_name || "").toLowerCase().includes(applicant_filters.candidate_name);
            const prog_match = !applicant_filters.programme || (a.program || "").toLowerCase() === applicant_filters.programme;
            return id_match && name_match && prog_match;
        });
    }

    const unique_programmes = [...new Set(applicants.map(a => a.program).filter(Boolean))].sort();
    const programme_options = unique_programmes.map(p => `<option value="${p}">${p}</option>`).join('');

    let d = new frappe.ui.Dialog({
        title: __("Allocate Interview Slots"),
        size: "extra-large",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "staff_section_label",
                options: `
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px;">
                        <div style="font-weight:600; font-size:13px; color:#333;">
                            ${__("Select Interview Staff Member")}
                            <span style="font-weight:400; font-size:11px; color:#888; margin-left:8px;">
                                — Select exactly one interviewer
                            </span>
                        </div>
                        <div style="position:relative; width:240px;">
                            <input type="text" id="staff-search-input" placeholder="${__("Search staff...")}" 
                                   style="width:100%; padding:6px 12px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px; outline:none; background:#ffffff; transition:border 0.15s;">
                        </div>
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; background:#f1f5f9; padding:6px 12px; border-radius:6px; font-size:12px;">
                        <div style="display:flex; align-items:center; gap:12px;">
                            <button type="button" id="staff-clear-all-btn" class="btn btn-xs btn-default" style="font-size:11px; padding:2px 8px; border-radius:4px;">
                                Clear Selection
                            </button>
                        </div>
                        <div id="staff-sel-count" style="color:#475569; font-weight:600; font-size:12px;">
                            Total Staff: ${staff_list.length} | 0 Selected
                        </div>
                    </div>
                `
            },
            {
                fieldtype: "HTML",
                fieldname: "staff_radios",
                options: `
                    <div id="staff-list" style="display:grid; grid-template-columns: repeat(3, 1fr); gap:10px; min-height:160px; padding:8px; border:1px solid #e2e8f0; border-radius:8px; background:#f8fafc;">
                    </div>
                    <div style="display:flex; justify-content:flex-end; align-items:center; margin-top:8px; margin-bottom:12px;">
                        <div id="staff-pagination" style="display:flex; align-items:center; gap:8px; font-size:12px;">
                            <button type="button" id="staff-prev-btn" class="btn btn-xs btn-default" style="padding:2px 8px; font-size:11px;">
                                &laquo; Prev
                            </button>
                            <span id="staff-page-info" style="font-weight:600; color:#475569;">Page 1 of 1</span>
                            <button type="button" id="staff-next-btn" class="btn btn-xs btn-default" style="padding:2px 8px; font-size:11px;">
                                Next &raquo;
                            </button>
                        </div>
                    </div>
                `
            },
            {
                fieldtype: "Section Break"
            },
            {
                label: __("Interview Date"),
                fieldname: "interview_date",
                fieldtype: "Date",
                reqd: 1,
                description: __("Date on which the interview will be conducted")
            },
            {
                fieldtype: "Column Break"
            },
            {
                label: __("Interview Time"),
                fieldname: "interview_time",
                fieldtype: "Time",
                reqd: 1,
                description: __("Time slot for the interview (optional)")
            },
            {
                fieldtype: "Column Break"
            },
            {
                label: __("Auto-select (Enter Number)"),
                fieldname: "auto_select_count",
                fieldtype: "Int",
                description: __("Enter count to automatically select first N pending applicants")
            },
            {
                fieldtype: "Column Break"
            },
            {
                fieldtype: "Section Break"
            },
            {
                fieldtype: "HTML",
                fieldname: "applicant_table",
                options: `
                    <div style="margin-bottom:10px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                        <div style="display:flex; gap:12px; align-items:center;">
                            <label style="font-weight:600; cursor:pointer; margin:0; display:flex; align-items:center; font-size:13px;">
                                <input type="checkbox" id="select-all-chk" style="width:15px; height:15px; cursor:pointer; margin-right:6px;">
                                Select All Applicants
                            </label>
                            <button type="button" id="applicant-clear-all-btn" class="btn btn-xs btn-default" style="font-size:11px; padding:2px 8px; border-radius:4px;">
                                Clear All
                            </button>
                            <span id="sel-count" style="color:#6c757d; font-size:12px; font-weight:500;">
                                0 of ${applicants.length} selected
                            </span>
                        </div>
                        <div id="applicant-pagination" style="display:flex; align-items:center; gap:8px; font-size:12px;">
                            <button type="button" id="applicant-prev-btn" class="btn btn-xs btn-default" style="padding:2px 8px; font-size:11px;">
                                &laquo; Prev
                            </button>
                            <span id="applicant-page-info" style="font-weight:600; color:#475569;">Page 1 of 1</span>
                            <button type="button" id="applicant-next-btn" class="btn btn-xs btn-default" style="padding:2px 8px; font-size:11px;">
                                Next &raquo;
                            </button>
                        </div>
                    </div>
                    <div style="border:1px solid #d1d8dd; border-radius:8px; overflow:hidden; background:#ffffff;">
                        <table class="table table-bordered table-hover"
                               style="margin:0; font-size:13px; width:100%;">
                            <thead style="background:#f8fafc;">
                                <tr>
                                    <th style="width:40px; text-align:center; vertical-align:middle; padding:8px 4px;"></th>
                                    <th style="width:60px; text-align:center; color:#3b82f6; vertical-align:middle; padding:8px 4px; font-weight:600;">No.</th>
                                    <th style="width:25%; color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Applicant ID</th>
                                    <th style="width:30%; color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Candidate Name</th>
                                    <th style="width:25%; color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Programme</th>
                                    <th style="color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Source</th>
                                </tr>
                                <tr style="background:#f1f5f9;">
                                    <th style="padding:4px 6px; text-align:center;"></th>
                                    <th style="padding:4px 6px; text-align:center;"></th>
                                    <th style="padding:4px 6px;">
                                        <input type="text" id="filter-applicant-id" placeholder="${__("Filter ID...")}" 
                                               style="width:100%; border:1px solid #cbd5e1; border-radius:14px; padding:3px 10px; font-size:11px; font-weight:normal; outline:none; background:#ffffff; box-shadow:inset 0 1px 2px rgba(0,0,0,0.03);">
                                    </th>
                                    <th style="padding:4px 6px;">
                                        <input type="text" id="filter-candidate-name" placeholder="${__("Filter Name...")}" 
                                               style="width:100%; border:1px solid #cbd5e1; border-radius:14px; padding:3px 10px; font-size:11px; font-weight:normal; outline:none; background:#ffffff; box-shadow:inset 0 1px 2px rgba(0,0,0,0.03);">
                                    </th>
                                    <th style="padding:4px 6px;">
                                        <select id="filter-programme" style="width:100%; border:1px solid #cbd5e1; border-radius:14px; padding:3px 10px; font-size:11px; font-weight:normal; outline:none; background:#ffffff; box-shadow:inset 0 1px 2px rgba(0,0,0,0.03);">
                                            <option value="">${__("All Programmes")}</option>
                                            ${programme_options}
                                        </select>
                                    </th>
                                    <th style="padding:4px 6px;"></th>
                                </tr>
                            </thead>
                            <tbody id="applicant-table-body"></tbody>
                        </table>
                    </div>
                `
            }
        ],
        primary_action_label: __("Allocate Slots"),
        primary_action(values) {

            if (!selected_staff) {
                frappe.msgprint(__("Please select an Interview Staff Member."));
                return;
            }

            if (!selected_applicant_names.size) {
                frappe.msgprint(__("Please select at least one applicant."));
                return;
            }

            const selected_applicants = Array.from(selected_applicant_names);

            frappe.call({
                method: "allocate_interview_slots",
                doc: frm.doc,
                args: {
                    staff_member: selected_staff,
                    selected_applicants: selected_applicants,
                    interview_date: values.interview_date,
                    interview_time: values.interview_time || null
                },
                freeze: true,
                freeze_message: __("Allocating Interview Slots… Please wait"),
                callback: function (r) {
                    if (!r.exc) {
                        // Inject keyframe styles once
                        if (!document.getElementById("ivl-toast-style")) {
                            const style = document.createElement("style");
                            style.id = "ivl-toast-style";
                            style.innerHTML = `
                                @keyframes ivlSlideDown {
                                    from { opacity: 0; transform: translateX(-50%) translateY(-30px); }
                                    to   { opacity: 1; transform: translateX(-50%) translateY(0); }
                                }
                                @keyframes ivlSlideUp {
                                    from { opacity: 1; transform: translateX(-50%) translateY(0); }
                                    to   { opacity: 0; transform: translateX(-50%) translateY(-30px); }
                                }
                            `;
                            document.head.appendChild(style);
                        }

                        // Remove existing toast if any
                        const existingToast = document.getElementById("ivl-success-toast");
                        if (existingToast) existingToast.remove();

                        const count = r.message || 0;
                        const toast = document.createElement("div");
                        toast.id = "ivl-success-toast";
                        toast.style.cssText = `
                            position: fixed;
                            top: 20px;
                            left: 50%;
                            z-index: 999999;
                            background: #ffffff;
                            border: 1.5px solid #2da44e;
                            border-left: 5px solid #2da44e;
                            border-radius: 10px;
                            padding: 14px 20px;
                            min-width: 380px;
                            max-width: 550px;
                            box-shadow: 0 10px 40px rgba(45,164,78,0.22), 0 2px 10px rgba(0,0,0,0.12);
                            display: flex;
                            align-items: flex-start;
                            gap: 15px;
                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                            animation: ivlSlideDown 0.4s cubic-bezier(.4,0,.2,1) forwards;
                        `;
                        toast.innerHTML = `
                            <div style="flex-shrink:0; width:38px; height:38px; background:#eafbee;
                                        border-radius:50%; display:flex; align-items:center;
                                        justify-content:center; font-size:20px;">✅</div>
                            <div style="flex:1;">
                                <div style="font-weight:800; font-size:15px; color:#1a7f37; margin-bottom:4px; letter-spacing:-0.2px;">
                                    Interview Scheduled Successfully Updated
                                </div>
                                <div style="font-size:13.5px; color:#4a4a4a; line-height:1.4;">
                                    The interview allocation process has been completed successfully for <span style="font-weight:700; color:#1a7f37;">${count} applicants</span>.
                                </div>
                            </div>
                            <span id="ivl-success-toast-close"
                                  style="cursor:pointer; color:#adb5bd; font-size:20px; line-height:1;
                                         padding:4px; align-self:flex-start; flex-shrink:0; transition: color 0.2s;"
                                  onmouseover="this.style.color='#495057'" onmouseout="this.style.color='#adb5bd'"
                                  title="Dismiss">✕</span>
                        `;
                        document.body.appendChild(toast);

                        const dismissToast = () => {
                            toast.style.animation = "ivlSlideUp 0.4s cubic-bezier(.4,0,.2,1) forwards";
                            setTimeout(() => toast.remove(), 400);
                        };
                        document.getElementById("ivl-success-toast-close").onclick = dismissToast;
                        setTimeout(dismissToast, 6500);

                        d.hide();
                        frm.reload_doc();
                    }
                }
            });
        }
    });

    d.show();

    const $wrapper = d.$wrapper;

    function render_staff_page() {
        const filtered = get_filtered_staff();
        const total_pages = Math.ceil(filtered.length / staff_page_size) || 1;
        if (staff_current_page > total_pages) staff_current_page = total_pages;
        if (staff_current_page < 1) staff_current_page = 1;

        const start = (staff_current_page - 1) * staff_page_size;
        const page_staff = filtered.slice(start, start + staff_page_size);

        if (!page_staff.length) {
            $wrapper.find("#staff-list").html(`
                <div style="grid-column: 1 / -1; text-align:center; padding:30px; color:#94a3b8; font-size:13px;">
                    No interview staff members found matching criteria.
                </div>
            `);
        } else {
            const cards_html = page_staff.map((s) => {
                const is_selected = selected_staff === s.name;
                return `
                    <label style="display:flex; flex-direction:column; justify-content:space-between; gap:6px; padding:10px 12px;
                                   border:1px solid ${is_selected ? '#3b82f6' : '#cbd5e1'}; border-radius:8px; cursor:pointer;
                                   background:${is_selected ? '#eff6ff' : '#ffffff'}; transition: all 0.15s ease;"
                           class="staff-label">
                        <div style="display:flex; align-items:flex-start; gap:8px;">
                            <input type="radio" name="staff_radio" class="staff-radio"
                                   value="${s.name}" style="margin-top:3px; cursor:pointer;"
                                   ${is_selected ? 'checked' : ''}>
                            <div style="flex:1; overflow:hidden;">
                                <div style="font-weight:700; font-size:13px; color:#1e293b; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${s.staff_name}">
                                    ${s.staff_name}
                                </div>
                                ${s.designation ? `<div style="color:#64748b; font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${s.designation}">${s.designation}</div>` : ''}
                            </div>
                        </div>
                        <div style="font-size:11px; color:#64748b; border-top:1px solid #f1f5f9; padding-top:6px; margin-top:2px;">
                            <div style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${s.email || ''}">${s.email || '-'}</div>
                            ${s.contact_number ? `<div style="color:#94a3b8; margin-top:2px;">${s.contact_number}</div>` : ''}
                        </div>
                    </label>
                `;
            }).join("");

            $wrapper.find("#staff-list").html(cards_html);
        }

        $wrapper.find("#staff-page-info").text(`Page ${staff_current_page} of ${total_pages}`);
        $wrapper.find("#staff-prev-btn").prop("disabled", staff_current_page <= 1);
        $wrapper.find("#staff-next-btn").prop("disabled", staff_current_page >= total_pages);
        $wrapper.find("#staff-sel-count").text(`Total Staff: ${staff_list.length} | ${selected_staff ? '1 Selected' : '0 Selected'}`);
    }

    function render_applicant_page() {
        const filtered = get_filtered_applicants();
        const total_pages = Math.ceil(filtered.length / applicant_page_size) || 1;
        if (applicant_current_page > total_pages) applicant_current_page = total_pages;
        if (applicant_current_page < 1) applicant_current_page = 1;

        const start = (applicant_current_page - 1) * applicant_page_size;
        const page_applicants = filtered.slice(start, start + applicant_page_size);

        if (!page_applicants.length) {
            $wrapper.find("#applicant-table-body").html(`
                <tr>
                    <td colspan="6" style="text-align:center; padding:25px; color:#94a3b8; font-size:13px;">
                        No applicants match the filter criteria.
                    </td>
                </tr>
            `);
        } else {
            const rows_html = page_applicants.map((row, p_idx) => {
                const global_idx = start + p_idx + 1;
                const is_checked = selected_applicant_names.has(row.name);
                return `
                    <tr data-name="${row.name}">
                        <td style="text-align:center; width:40px; vertical-align:middle;">
                            <input type="checkbox" class="applicant-checkbox"
                                   data-name="${row.name}" ${is_checked ? 'checked' : ''}>
                        </td>
                        <td style="text-align:center; width:60px; color:#64748b; font-size:12px; vertical-align:middle;">${global_idx}</td>
                        <td style="vertical-align:middle;">${row.applicant_id || "-"}</td>
                        <td style="vertical-align:middle;"><b>${row.candidate_name || "Unknown"}</b></td>
                        <td style="vertical-align:middle;">${row.program || "-"}</td>
                        <td style="vertical-align:middle;">
                            <span style="font-size:11px; padding:2px 7px; border-radius:10px;
                                         background:${row.source_type === "Entrance Test" ? "#e3f2fd" : "#e8f5e9"};
                                         color:${row.source_type === "Entrance Test" ? "#1565c0" : "#2e7d32"};">
                                ${row.source_type || "-"}
                            </span>
                        </td>
                    </tr>
                `;
            }).join("");

            $wrapper.find("#applicant-table-body").html(rows_html);
        }

        $wrapper.find("#applicant-page-info").text(`Page ${applicant_current_page} of ${total_pages}`);
        $wrapper.find("#applicant-prev-btn").prop("disabled", applicant_current_page <= 1);
        $wrapper.find("#applicant-next-btn").prop("disabled", applicant_current_page >= total_pages);

        update_applicant_counts(filtered.length);
    }

    function update_applicant_counts(filtered_length) {
        const sel_count = selected_applicant_names.size;
        const total_count = applicants.length;
        if (filtered_length !== undefined && filtered_length !== total_count) {
            $wrapper.find("#sel-count").text(`${sel_count} of ${total_count} selected (Filtered: ${filtered_length})`);
        } else {
            $wrapper.find("#sel-count").text(`${sel_count} of ${total_count} selected`);
        }
        
        const filtered = get_filtered_applicants();
        const all_selected = filtered.length > 0 && filtered.every(a => selected_applicant_names.has(a.name));
        $wrapper.find("#select-all-chk").prop("checked", all_selected);
    }

    // Initial Renders
    render_staff_page();
    render_applicant_page();

    // Event Bindings for Staff Member 3x3 Grid
    $wrapper.on("change", ".staff-radio", function () {
        selected_staff = $(this).val();
        render_staff_page();
    });

    $wrapper.on("input keyup search", "#staff-search-input", function () {
        staff_search_query = $(this).val();
        staff_current_page = 1;
        render_staff_page();
    });

    $wrapper.find("#staff-clear-all-btn").on("click", function () {
        selected_staff = null;
        render_staff_page();
    });

    $wrapper.find("#staff-prev-btn").on("click", function () {
        if (staff_current_page > 1) {
            staff_current_page--;
            render_staff_page();
        }
    });

    $wrapper.find("#staff-next-btn").on("click", function () {
        const filtered = get_filtered_staff();
        const total_pages = Math.ceil(filtered.length / staff_page_size) || 1;
        if (staff_current_page < total_pages) {
            staff_current_page++;
            render_staff_page();
        }
    });

    // Event Bindings for Applicants
    $wrapper.on("change", ".applicant-checkbox", function () {
        const name = $(this).attr("data-name");
        if (this.checked) {
            selected_applicant_names.add(name);
        } else {
            selected_applicant_names.delete(name);
        }
        const filtered_len = get_filtered_applicants().length;
        update_applicant_counts(filtered_len);
    });

    $wrapper.find("#select-all-chk").on("change", function () {
        const filtered = get_filtered_applicants();
        if (this.checked) {
            filtered.forEach(a => selected_applicant_names.add(a.name));
        } else {
            filtered.forEach(a => selected_applicant_names.delete(a.name));
        }
        render_applicant_page();
    });

    $wrapper.find("#applicant-clear-all-btn").on("click", function () {
        selected_applicant_names.clear();
        $wrapper.find("#select-all-chk").prop("checked", false);
        render_applicant_page();
    });

    $wrapper.find("#applicant-prev-btn").on("click", function () {
        if (applicant_current_page > 1) {
            applicant_current_page--;
            render_applicant_page();
        }
    });

    $wrapper.find("#applicant-next-btn").on("click", function () {
        const list = get_filtered_applicants();
        const total_pages = Math.ceil(list.length / applicant_page_size) || 1;
        if (applicant_current_page < total_pages) {
            applicant_current_page++;
            render_applicant_page();
        }
    });

    $wrapper.on("input keyup search change", "#filter-applicant-id, #filter-candidate-name, #filter-programme", function () {
        applicant_filters.applicant_id = $wrapper.find("#filter-applicant-id").val().toLowerCase().trim();
        applicant_filters.candidate_name = $wrapper.find("#filter-candidate-name").val().toLowerCase().trim();
        applicant_filters.programme = $wrapper.find("#filter-programme").val().toLowerCase().trim();
        applicant_current_page = 1;
        render_applicant_page();
    });

    d.fields_dict.auto_select_count.$input.on("input", function () {
        let val = parseInt($(this).val()) || 0;
        selected_applicant_names.clear();
        applicants.slice(0, val).forEach(a => selected_applicant_names.add(a.name));
        render_applicant_page();
    });

    // ── Past-date validation on Interview Date ──────────────────────────
    d.fields_dict.interview_date.$input.on("change blur", function () {
        const entered = d.get_value("interview_date");
        if (!entered) return;

        // Compare based on date only (today or future)
        const today = frappe.datetime.get_today();
        if (entered < today) {
            // Clear the field
            d.set_value("interview_date", "");

            // Inject keyframe styles once (shared with ivl success toast)
            if (!document.getElementById("ivl-toast-style")) {
                const style = document.createElement("style");
                style.id = "ivl-toast-style";
                style.innerHTML = `
                    @keyframes ivlSlideDown {
                        from { opacity: 0; transform: translateX(-50%) translateY(-30px); }
                        to   { opacity: 1; transform: translateX(-50%) translateY(0); }
                    }
                    @keyframes ivlSlideUp {
                        from { opacity: 1; transform: translateX(-50%) translateY(0); }
                        to   { opacity: 0; transform: translateX(-50%) translateY(-30px); }
                    }
                `;
                document.head.appendChild(style);
            }

            // Remove any existing warning toast
            const existingToast = document.getElementById("ivl-date-toast");
            if (existingToast) existingToast.remove();

            // Build warning toast
            const toast = document.createElement("div");
            toast.id = "ivl-date-toast";
            toast.style.cssText = `
                position: fixed;
                top: 20px;
                left: 50%;
                z-index: 999999;
                background: #fff8e1;
                border: 1.5px solid #f0a500;
                border-left: 5px solid #f0a500;
                border-radius: 10px;
                padding: 14px 20px;
                min-width: 360px;
                max-width: 500px;
                box-shadow: 0 8px 30px rgba(240,165,0,0.18), 0 2px 8px rgba(0,0,0,0.10);
                display: flex;
                align-items: flex-start;
                gap: 12px;
                font-family: inherit;
                animation: ivlSlideDown 0.35s cubic-bezier(.4,0,.2,1) forwards;
            `;
            toast.innerHTML = `
                <div style="flex-shrink:0; width:36px; height:36px; background:#fff3cd;
                            border-radius:50%; display:flex; align-items:center;
                            justify-content:center; font-size:18px;">⚠️</div>
                <div style="flex:1;">
                    <div style="font-weight:700; font-size:14px; color:#856404; margin-bottom:3px;">
                        Invalid Interview Date
                    </div>
                    <div style="font-size:12.5px; color:#555;">
                        choose the Interview Should not Be past date choose future date
                    </div>
                </div>
                <span id="ivl-date-toast-close"
                      style="cursor:pointer; color:#aaa; font-size:18px; line-height:1;
                             padding:0 4px; align-self:flex-start; flex-shrink:0;"
                      title="Dismiss">✕</span>
            `;
            document.body.appendChild(toast);

            const dismissDateToast = () => {
                toast.style.animation = "ivlSlideUp 0.35s cubic-bezier(.4,0,.2,1) forwards";
                setTimeout(() => toast.remove(), 350);
            };
            document.getElementById("ivl-date-toast-close").addEventListener("click", dismissDateToast);
            setTimeout(dismissDateToast, 6000);
        }
    });
}

// ============================================================
// Client Script : Entrance Test Seat Allocation
// DocType       : Entrance Test Seat Allocation
// ============================================================

frappe.ui.form.on("Entrance Test Seat Allocation", {

  onload: function (frm) {
    frm.set_query("admission_cycle", function () {
      return {
        filters: {
          "status": "Active"
        }
      };
    });
  },

  refresh: function (frm) {
    _handle_international_applicant_visibility(frm);

    frm.set_query("entrance_test_provider", function () {
      const preferences = (frm.doc.assigned_preferences || []).map(p => p.provider);
      return { filters: { name: ["in", preferences] } };
    });

    frm.set_query("re_entrance_test_provider", function () {
      const preferences = (frm.doc.re_assigned_preferences || []).map(p => p.provider);
      return { filters: { name: ["in", preferences] } };
    });

    // ── Role based restrictions ──────────────────────────
    // Administrator can do everything — skip all restrictions
    if (frappe.user_roles.includes("Administrator")) {
      frm.set_df_property("tab_9_tab", "hidden", 0);
      frm.set_df_property("reschedule_seat_allocation_section", "hidden", 0);
      frm.set_df_property("section_break_axgb", "hidden", 0);
      frm.set_df_property("entrance_test_status", "read_only", 0);
      frm.set_df_property("part_a_total_marks_scored", "read_only", 0);
      frm.set_df_property("part_a_all_india_rank", "read_only", 0);
      frm.set_df_property("part_b_total_marks_scored", "read_only", 0);
      frm.set_df_property("part_b_all_india_rank", "read_only", 0);
    } else if (frappe.user_roles.includes("Applicant")) {
      _apply_applicant_permissions(frm);

      // Force status to "Scheduled" for applicants if not already set or invalid
      if (!frm.doc.entrance_test_status || frm.doc.entrance_test_status === "Not Scheduled" || frm.doc.entrance_test_status === "") {
        frm.set_value("entrance_test_status", "Scheduled");
      }
      // Ensure it remains read-only for applicants at all times
      frm.set_df_property("entrance_test_status", "read_only", 1);
    } else {
      // FOR OTHER ROLES (non-Admin, non-Applicant):
      // Ensure the Reschedule tab and other sections are ALWAYS visible for them
      frm.set_df_property("tab_9_tab", "hidden", 0);
      frm.set_df_property("reschedule_seat_allocation_section", "hidden", 0);
      frm.set_df_property("section_break_axgb", "hidden", 0);

      // Ensure result and status fields are editable for admins
      frm.set_df_property("entrance_test_status", "read_only", 0);
      frm.set_df_property("part_a_total_marks_scored", "read_only", 0);
      frm.set_df_property("part_a_all_india_rank", "read_only", 0);
      frm.set_df_property("part_b_total_marks_scored", "read_only", 0);
      frm.set_df_property("part_b_all_india_rank", "read_only", 0);
    }

  },

  download_admit_card: function (frm) {
    _handle_admit_card_download(frm, false);
  },

  re_download_admit_card: function (frm) {
    _handle_admit_card_download(frm, true);
  },

  entrance_test_provider: function (frm) {
    const provider = frm.doc.entrance_test_provider;
    if (!provider) {
      frm.set_value("center_name", "");
      frm.set_value("center_address", "");
      return;
    }

    const pref = (frm.doc.assigned_preferences || []).find(p => p.provider === provider);
    if (!pref) {
      frappe.show_alert({ message: __("Please choose from your assigned preference centers."), indicator: "red" });
      frm.set_value("entrance_test_provider", "");
      return;
    }

    frm.set_value("center_name", pref.center_name || "");
    frm.set_value("center_address", pref.center_address || "");

    frappe.call({
      method: "slcm.admission.doctype.entrance_test_list.entrance_test_list.get_applicant_preferences",
      args: { applicant_id: frm.doc.applicant, entrance_test_list: frm.doc.entrance_test_list },
      callback: function (r) {
        if (!r.message) return;
        const pinfo = r.message.find(p => p.entrance_test_provider === provider);
        if (pinfo && pinfo.is_full) {
          frappe.msgprint({
            title: __("Centre Full"),
            message: __("<b>{0}</b> is currently full. Please choose another centre.", [pinfo.center_name || provider]),
            indicator: "orange"
          });
          frm.set_value("entrance_test_provider", "");
        }
      }
    });
  },

  re_entrance_test_provider: function (frm) {
    const provider = frm.doc.re_entrance_test_provider;
    if (!provider) {
      frm.set_value("re_center_name", "");
      frm.set_value("re_center_address", "");
      return;
    }

    const pref = (frm.doc.re_assigned_preferences || []).find(p => p.provider === provider);
    if (!pref) {
      frappe.show_alert({ message: __("Please choose from your assigned preference centers."), indicator: "red" });
      frm.set_value("re_entrance_test_provider", "");
      return;
    }

    frm.set_value("re_center_name", pref.center_name || "");
    frm.set_value("re_center_address", pref.center_address || "");

    frappe.call({
      method: "slcm.admission.doctype.entrance_test_list.entrance_test_list.get_applicant_preferences",
      args: { applicant_id: frm.doc.applicant, entrance_test_list: frm.doc.entrance_test_list },
      callback: function (r) {
        if (!r.message) return;
        const pinfo = r.message.find(p => p.entrance_test_provider === provider);
        if (pinfo && pinfo.is_full) {
          frappe.msgprint({
            title: __("Centre Full"),
            message: __("<b>{0}</b> is currently full. Please choose another centre.", [pinfo.center_name || provider]),
            indicator: "orange"
          });
          frm.set_value("re_entrance_test_provider", "");
        }
      }
    });
  },

  entrance_test_status: function (frm) {
    // Only automatically set timestamp if status is changed by an authorized user (Admin/Entrance Test Admin)
    // The field is read-only for Applicants so they can't trigger this manually
    if (["Attended", "Absent"].includes(frm.doc.entrance_test_status)) {
      frm.set_value("attendance_marked_on", frappe.datetime.now_datetime());
    }
  },

  part_a_total_marks_scored: function (frm) {
    _calculate_total_and_percentage(frm);
  },

  part_b_total_marks_scored: function (frm) {
    _calculate_total_and_percentage(frm);
  },

  total_marks: function (frm) {
    _calculate_total_and_percentage(frm);
  },

  applicant: function (frm) {
    if (!frm.doc.applicant) {
      frm.set_df_property("category", "hidden", 1);
      return;
    }

    // Fetch all needed Applicant information including categories
    frappe.call({
      method: "frappe.client.get",
      args: { doctype: "Applicant", name: frm.doc.applicant },
      callback: function (r) {
        if (!r.message) return;
        const app = r.message;

        // Populate standard fields
        frm.set_value("candidate_name", app.candidate_name);
        frm.set_value("program", app.program);
        frm.set_value("email", app.email);
        frm.set_value("gender", app.gender);
        frm.set_value("date_of_birth", app.date_of_birth);
        frm.set_value("mother_name", app.mother_name);
        frm.set_value("father_name", app.father_name);
        frm.set_value("father_mobile_number", app.father_mobile);
        frm.set_value("exempts_entrance_test", app.exempts_entrance_test);
        frm.set_value("exempts_interview", app.exempts_interview);

        // Show the category table and populate it from reservation fields
        frm.clear_table("category");
        if (app.whether_scstobc_ncl && app.whether_scstobc_ncl.toUpperCase() !== "General") {
          frm.add_child("category", { category: app.whether_scstobc_ncl });
        } else {
          frm.add_child("category", { category: "General" });
        }
        if (app.pwd === "Yes") {
          frm.add_child("category", { category: "PWD" });
        }
        if (app.karnataka_category === "Yes") {
          frm.add_child("category", { category: "Karnataka" });
        }
        }
        frm.refresh_field("category");
        frm.set_df_property("category", "hidden", 0);
      }
    });
  },

  before_save: function (frm) {
    // Initial Allocation Confirmation
    if (frm.doc.entrance_test_provider && frm.doc.allocation_status === "Not Allocated") {
      frappe.validated = false;
      frappe.confirm(
        __("Confirm seat allocation at <b>{0}</b>? This action is permanent.",
          [frm.doc.center_name || frm.doc.entrance_test_provider]),
        function () {
          frappe.call({
            method: "slcm.admission.doctype.entrance_test_list.entrance_test_list.confirm_applicant_preference",
            args: { allocation_name: frm.doc.name, selected_provider: frm.doc.entrance_test_provider },
            freeze: true,
            freeze_message: __("Finalizing your allocation..."),
            callback: function (r) {
              if (!r.exc && r.message) {
                frm.reload_doc();
                frappe.show_alert({
                  message: __("Seat Successfully Allocated! Seat: <b>{0}</b>", [r.message.seat_number]),
                  indicator: "green"
                }, 5);
              }
            }
          });
        }
      );
    }

    // Rescheduled Allocation Confirmation
    if (frm.doc.re_entrance_test_provider && frm.doc.re_allocation_status === "Preferences Assigned") {
      frappe.validated = false;
      frappe.confirm(
        __("Confirm rescheduled seat allocation at <b>{0}</b>? This action is permanent.",
          [frm.doc.re_center_name || frm.doc.re_entrance_test_provider]),
        function () {
          frappe.call({
            method: "slcm.admission.doctype.entrance_test_list.entrance_test_list.confirm_rescheduled_preference",
            args: { allocation_name: frm.doc.name, selected_provider: frm.doc.re_entrance_test_provider },
            freeze: true,
            freeze_message: __("Finalizing your rescheduled allocation..."),
            callback: function (r) {
              if (!r.exc && r.message) {
                frm.reload_doc();
                frappe.show_alert({
                  message: __("Rescheduled Seat Successfully Allocated! Seat: <b>{0}</b>", [r.message.seat_number]),
                  indicator: "green"
                }, 5);
              }
            }
          });
        }
      );
    }
  }
});

// ============================================================
//  _apply_applicant_permissions
//  Called on refresh when the logged-in user has the "Applicant" role.
//
//  Rules:
//   - tab_test_reference  : all fields → read-only
//   - tab_applicant_info  : all fields → read-only
//   - tab_allocation      : all fields → read-only EXCEPT "entrance_test_provider"
//                           "entrance_test_provider" stays editable until
//                           allocation_status is Allocated / Reallocated,
//                           after which it also becomes read-only.
//   - tab_9_tab           : hidden until is_rescheduled == 1
//                           (rescheduling has been assigned by admin)
//   - tab_result          : all fields → read-only
//   - tab_communication   : all fields → read-only
// ============================================================
function _apply_applicant_permissions(frm) {

  // ── 1. tab_test_reference — fully read-only ──────────────
  const test_ref_fields = [
    "profile", "entrance_test_list", "academic_year",
    "admission_cycle", "campus", "program_level"
  ];
  test_ref_fields.forEach(f => frm.set_df_property(f, "read_only", 1));

  // ── 2. tab_applicant_info — fully read-only ───────────────
  const applicant_info_fields = [
    "applicant", "candidate_name", "program", "category",
    "email", "gender", "date_of_birth", "section_break_hynq",
    "mother_name", "father_name", "father_mobile_number"
  ];
  applicant_info_fields.forEach(f => frm.set_df_property(f, "read_only", 1));

  // ── 3. tab_allocation — read-only except entrance_test_provider ──
  const allocation_readonly_fields = [
    "entrance_test_name", "assigned_preferences",
    "center_name", "center_address", "preference_order",
    "room_code", "room_name", "building", "floor",
    "seat_number", "allocation_status", "allocation_date", "allocated_by"
    // "download_admit_card" button — leave as-is (button)
  ];
  allocation_readonly_fields.forEach(f => frm.set_df_property(f, "read_only", 1));

  // entrance_test_provider: editable only when not yet allocated
  const allocated_statuses = ["Allocated", "Reallocated", "Cancelled", "Rejected"];
  const is_allocated = allocated_statuses.includes(frm.doc.allocation_status);
  frm.set_df_property("entrance_test_provider", "read_only", is_allocated ? 1 : 0);

  // ── 4. tab_9_tab — hide for Applicant until rescheduled ──
  const is_rescheduled = (frm.doc.is_rescheduled == 1 || frm.doc.entrance_test_status === "Rescheduled");

  frm.set_df_property("tab_9_tab", "hidden", is_rescheduled ? 0 : 1);
  frm.set_df_property("reschedule_seat_allocation_section", "hidden", is_rescheduled ? 0 : 1);
  frm.set_df_property("section_break_axgb", "hidden", is_rescheduled ? 0 : 1);

  if (is_rescheduled) {
    const reschedule_readonly_fields = [
      "re_entrance_test_name", "re_assigned_preferences",
      "re_center_name", "re_center_address", "re_preference_order",
      "re_room_code", "re_room_name", "re_building", "re_floor",
      "re_seat_number", "re_allocation_status", "re_allocation_date", "re_allocated_by"
    ];
    reschedule_readonly_fields.forEach(f => frm.set_df_property(f, "read_only", 1));

    // re_entrance_test_provider: editable only when not yet allocated
    const is_re_allocated = ["Allocated", "Reallocated", "Cancelled", "Rejected"].includes(frm.doc.re_allocation_status);
    frm.set_df_property("re_entrance_test_provider", "read_only", is_re_allocated ? 1 : 0);
  }

  // ── 5. Part A & Part B tabs — fully read-only ──────────────────────
  const result_fields = [
    "entrance_test_status", "attendance_marked_on",
    "section_break_part_a", "part_a_total_marks_scored", "part_a_all_india_rank", "shortlisted_status",
    "section_break_part_b", "part_b_total_marks_scored", "part_b_all_india_rank",
    "section_break_cumulative", "total_marks", "total_marks_secured_in_part_a_b", "percentile",
    "entrance_test_rank", "result_published", "result_status"
  ];
  result_fields.forEach(f => frm.set_df_property(f, "read_only", 1));

  // ── 6. tab_communication — fully read-only ───────────────
  const communication_fields = [
    "admit_card_generated", "admit_card_number"
  ];
  communication_fields.forEach(f => frm.set_df_property(f, "read_only", 1));
}

function _handle_admit_card_download(frm, is_rescheduled) {
  if (frm.is_dirty()) {
    frappe.msgprint({
      title: __("Unsaved Changes"),
      message: __("Please save the document before downloading the Admit Card."),
      indicator: "orange"
    });
    return;
  }

  const status = is_rescheduled ? frm.doc.re_allocation_status : frm.doc.allocation_status;
  const allowed = ["Allocated", "Reallocated"];

  if (!allowed.includes(status)) {
    frappe.msgprint({
      title: __("Not Allowed"),
      message: __("Admit Card can only be downloaded when status is <b>Allocated</b> or <b>Reallocated</b>."),
      indicator: "red"
    });
    return;
  }

  frappe.show_alert({ message: __("Storing & Generating Admit Card…"), indicator: "blue" }, 3);

  // Trigger server-side storage first
  frappe.call({
    method: "slcm.admission.doctype.entrance_test_list.entrance_test_list.generate_and_store_admit_card",
    args: {
      allocation: frm.doc.name,
      is_rescheduled: is_rescheduled
    },
    callback: function (r) {
      if (!r.exc) {
        frm.reload_doc(() => {
          _generate_local_print(frm, is_rescheduled);
        });
      } else {
        _generate_local_print(frm, is_rescheduled);
      }
    }
  });
}

function _generate_local_print(frm, is_rescheduled) {
  if (!frm.doc.campus) {
    generate_admit_card_pdf(frm.doc, frm, {}, is_rescheduled);
    return;
  }

  frappe.db.get_value("Campus", frm.doc.campus, ["campus_name", "logo"], (r_val) => {
    const branding = {
      campus_name: r_val.campus_name || frm.doc.campus,
      logo: r_val.logo || null
    };
    generate_admit_card_pdf(frm.doc, frm, branding, is_rescheduled);
  });
}

// ============================================================
//  generate_admit_card_pdf
//  NLSAT-LLB exact layout: dark-red header + bordered tables
//  2-page: Page 1 = card, Page 2 = instructions
// ============================================================
function generate_admit_card_pdf(doc, frm, branding = {}, is_rescheduled = false) {

  const esc = (v) => frappe.utils.escape_html(String(v || ""));
  const val = (v) => (v && String(v).trim() !== "") ? esc(v) : "—";

  const admit_no = doc.admit_card_number || ("AC-" + doc.name);

  // Pick fields based on is_rescheduled
  const f_date = is_rescheduled ? doc.re_allocation_date : doc.allocation_date;
  const f_test = is_rescheduled ? (doc.re_entrance_test_name || doc.re_entrance_test_list) : (doc.entrance_test_name || doc.entrance_test_list);
  const f_seat = is_rescheduled ? doc.re_seat_number : doc.seat_number;
  const f_room = is_rescheduled ? doc.re_room_name : doc.room_name;
  const f_code = is_rescheduled ? doc.re_room_code : doc.room_code;
  const f_building = is_rescheduled ? doc.re_building : doc.building;
  const f_floor = is_rescheduled ? doc.re_floor : doc.floor;
  const f_center = is_rescheduled ? doc.re_center_name : doc.center_name;
  const f_address = is_rescheduled ? doc.re_center_address : doc.center_address;
  const f_status = is_rescheduled ? doc.re_allocation_status : doc.allocation_status;

  let alloc_date = "—";
  if (f_date) {
    try { alloc_date = frappe.datetime.str_to_user(f_date); }
    catch (e) { alloc_date = f_date; }
  }

  let dob = "—";
  if (doc.date_of_birth) {
    try { dob = frappe.datetime.str_to_user(doc.date_of_birth); }
    catch (e) { dob = doc.date_of_birth; }
  }

  const issue_date = (() => {
    try { return frappe.datetime.str_to_user(frappe.datetime.nowdate()); }
    catch (e) { return new Date().toLocaleDateString("en-IN"); }
  })();

  const exam_date_time = alloc_date !== "—"
    ? alloc_date + " &nbsp;|&nbsp; As per schedule"
    : "As per schedule";

  let profile_image_url = null;
  if (doc.profile) {
    if (/^(https?:)?\/\//.test(doc.profile)) {
      profile_image_url = doc.profile;
    } else {
      profile_image_url = '/files/' + encodeURIComponent(doc.profile.replace(/^.*[\\\/]/, ""));
    }
  }

  // Dynamic branding
  const campus_display_name = branding.campus_name || doc.campus || "Institution of Legal Education";
  const campus_logo_url = branding.logo ? (branding.logo.startsWith("http") ? branding.logo : '/files/' + encodeURIComponent(branding.logo.replace(/^.*[\\\/]/, ""))) : null;

  const test_list = val(doc.entrance_test_list);
  const prog_level = val(doc.program_level);
  const acad_year = val(doc.academic_year);
  const adm_cycle = val(doc.admission_cycle);

  const centre_parts = [f_center, f_address].filter(v => v && v.trim());
  const centre_full = centre_parts.length ? centre_parts.map(esc).join(", ") : "—";

  /* ── header snippet (used on both pages) ── */
  function headerHTML() {
    return `
        <div class="header">
          <div class="logo-box">
            ${campus_logo_url
        ? `<img src="${campus_logo_url}" alt="Campus Logo" style="max-width:100%;max-height:100%;object-fit:contain;">`
        : `<div class="logo-inner">
                  <span class="logo-icon">⚖</span>
                  <span class="logo-text">LAW<br>SCHOOL</span>
                </div>`
      }
          </div>
          <div class="hdr-center">
            <div class="univ-name">${esc(campus_display_name)}</div>
            <div class="univ-sub">OFFICE OF ADMISSIONS &nbsp;&middot;&nbsp; EXAMINATION CELL</div>
          </div>
        </div>`;
  }

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Admit Card - ${esc(admit_no)}</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: "Times New Roman", Times, serif;
  font-size: 13px;
  background: #c8c8c8;
  color: #000;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}

/* ── Print bar ── */
.print-bar {
  background: #1a237e;
  color: #fff;
  text-align: center;
  padding: 9px 20px;
  font-size: 12.5px;
  font-family: Arial, sans-serif;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
}
.print-btn {
  background: #ffd600;
  color: #1a237e;
  border: none;
  padding: 6px 20px;
  font-size: 13px;
  font-weight: 700;
  border-radius: 3px;
  cursor: pointer;
  font-family: Arial, sans-serif;
}
.print-btn:hover { background: #ffeb3b; }

/* ── Shared page wrapper ── */
.card-page {
  width: 710px;
  margin: 20px auto;
  background: #fff;
  border: 1.5px solid #555;
}

/* ══ HEADER ══ */
.header {
  background: #7b1c1c;
  display: flex;
  align-items: center;
  padding: 10px 18px;
  gap: 16px;
  border-bottom: 3px solid #5a0e0e;
}
.logo-box {
  width: 74px;
  height: 74px;
  background: #fff;
  border: 2px solid rgba(255,255,255,0.6);
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}
.logo-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
}
.logo-icon {
  font-size: 28px;
  line-height: 1;
  color: #7b1c1c;
}
.logo-text {
  font-size: 7.5px;
  font-weight: bold;
  font-family: Arial, sans-serif;
  color: #7b1c1c;
  text-align: center;
  letter-spacing: 0.5px;
  line-height: 1.2;
}
.hdr-center {
  flex: 1;
  text-align: center;
}
.univ-name {
  font-size: 21px;
  font-weight: bold;
  font-family: Arial, sans-serif;
  color: #fff;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  line-height: 1.2;
}
.univ-sub {
  font-size: 11px;
  font-family: Arial, sans-serif;
  color: rgba(255,255,255,0.80);
  letter-spacing: 2.5px;
  text-transform: uppercase;
  margin-top: 3px;
}

/* ── Title row ── */
.title-row {
  text-align: center;
  padding: 9px 18px 7px;
  border-bottom: 1.5px solid #bbb;
}
.title-row .t1 {
  font-size: 14px;
  font-weight: bold;
  font-family: Arial, sans-serif;
  color: #000;
}
.title-row .t2 {
  font-size: 12.5px;
  font-family: Arial, sans-serif;
  color: #111;
  margin-top: 2px;
}

/* ══ INFO TABLE SECTION ══ */
.info-wrap-tbl {
  width: calc(100% - 28px);
  margin: 12px 14px;
  border: 1.5px solid #888;
  border-collapse: collapse;
}
.info-tbl-cell {
  vertical-align: top;
}
.photo-col-cell {
  width: 140px;
  vertical-align: top;
  border-left: 1.5px solid #888;
  padding: 10px 8px;
  height: 250px;
}
.info-tbl {
  width: 100%;
  border-collapse: collapse;
}
.info-tbl tr {
  border-bottom: 1px solid #ccc;
}
.info-tbl tr:last-child { border-bottom: none; }
.info-tbl td {
  padding: 5.5px 8px;
  font-size: 12.5px;
  vertical-align: middle;
  line-height: 1.5;
}
.info-tbl td.lb {
  font-weight: bold;
  font-family: Arial, sans-serif;
  width: 36%;
  white-space: nowrap;
  color: #000;
}
.info-tbl td.sp {
  width: 14px;
  font-weight: bold;
  font-family: Arial, sans-serif;
  color: #000;
  text-align: center;
  padding: 0;
}
.info-tbl td.vl {
  font-family: "Times New Roman", Times, serif;
  font-size: 13px;
  color: #000;
}

/* Seat number pill */
.seat-pill {
  display: inline-block;
  background: #1a237e;
  color: #fff;
  font-weight: bold;
  font-family: Arial, sans-serif;
  font-size: 13px;
  padding: 2px 14px;
  border-radius: 2px;
  letter-spacing: 1px;
}

/* Status pill */
.status-pill {
  display: inline-block;
  border: 1px solid #4caf50;
  color: #1b5e20;
  background: #f0fdf0;
  font-family: Arial, sans-serif;
  font-size: 11px;
  font-weight: bold;
  padding: 1px 10px;
  border-radius: 30px;
}

.photo-inner-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  height: 100%;
}
.photo-box-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.photo-frame {
  width: 120px;
  height: 150px;
  border: 1.5px solid #555;
  overflow: hidden;
  background: #eee;
  display: flex;
  align-items: center;
  justify-content: center;
}
.photo-frame img {
  display: block;
}
.photo-ph {
  font-size: 36px;
  color: #aaa;
  text-align: center;
}
.photo-cap {
  font-size: 9.5px;
  font-family: Arial, sans-serif;
  color: #555;
  text-align: center;
  font-style: italic;
  line-height: 1.3;
}

/* ══ SIGNATURE STRIP ══ */
.sig-note {
  text-align: center;
  font-style: italic;
  font-size: 11.5px;
  font-family: "Times New Roman", Times, serif;
  padding: 6px 14px 3px;
  color: #000;
}
.sig-tbl {
  border-collapse: collapse;
  width: calc(100% - 28px);
  margin: 0 14px 16px;
  border: 1.5px solid #888;
}
.sig-tbl td {
  border: 1.5px solid #888;
  padding: 0;
  width: 50%;
}
.sig-cell-inner {
  display: flex;
  flex-direction: column;
}
.sig-hdr {
  font-weight: bold;
  font-family: Arial, sans-serif;
  font-size: 12px;
  color: #000;
  text-align: center;
  padding: 5px 8px 4px;
  border-bottom: 1.5px solid #888;
  display: block;
}
.sig-body {
  height: 54px;
  display: block;
}

/* ══ PAGE 2 — INSTRUCTIONS ══ */
.inst-outer {
  border: 1.5px solid #888;
  margin: 12px 14px 16px;
  padding: 14px 18px 18px;
}
.inst-main-title {
  font-size: 13.5px;
  font-weight: bold;
  font-family: Arial, sans-serif;
  text-align: center;
  color: #000;
  margin-bottom: 10px;
}
.sec-title {
  font-size: 12.5px;
  font-weight: bold;
  font-family: Arial, sans-serif;
  color: #000;
  margin: 10px 0 3px;
}
.il {
  list-style: none;
  margin: 0;
  padding: 0;
}
.il > li {
  display: flex;
  gap: 6px;
  font-size: 11.5px;
  font-family: Arial, sans-serif;
  color: #000;
  line-height: 1.65;
  padding-left: 18px;
}
.il > li .mk { flex-shrink: 0; min-width: 16px; }
.sl {
  list-style: none;
  margin: 2px 0 2px 52px;
  padding: 0;
}
.sl li {
  display: flex;
  gap: 6px;
  font-size: 11.5px;
  font-family: Arial, sans-serif;
  color: #000;
  line-height: 1.65;
}
.sl li .mk { flex-shrink: 0; min-width: 22px; font-style: italic; }

/* ── Footer ── */
.pg-footer {
  padding: 6px 14px 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid #ddd;
}
.pg-footer span {
  font-size: 8.5px;
  font-family: Arial, sans-serif;
  color: #888;
}

/* ── Print ── */
@media print {
  body { background: #fff; margin: 0; }
  .print-bar { display: none !important; }
  .card-page {
    width: 100%;
    margin: 0;
    box-shadow: none;
    border: 1.5px solid #555;
  }
  .card-page.p1 { page-break-after: always; }
  .card-page.p2 { page-break-before: always; }
}
</style>
</head>
<body>

<!-- Print bar -->
<div class="print-bar">
  <span>Your Admit Card is ready —</span>
  <button class="print-btn" onclick="window.print()">⬇ Download / Print PDF</button>
  <span style="font-size:11.5px;opacity:0.75;">Select <b>Save as PDF</b> in the dialog</span>
</div>


<!-- ════════════════════════════════════
     PAGE 1 — Admit Card
════════════════════════════════════ -->
<div class="card-page p1">

  ${headerHTML()}

  <!-- Title -->
  <div class="title-row">
    <div class="t1">Admit Card (${val(f_test)})</div>
    <div class="t2">Admission to ${prog_level !== "—" ? esc(doc.program_level) : "the Programme"} &nbsp;|&nbsp; ${acad_year} &nbsp;|&nbsp; ${adm_cycle}</div>
  </div>

  <!-- Candidate info + photo -->
  <table class="info-wrap-tbl">
    <tr>
      <td class="info-tbl-cell">
        <table class="info-tbl">
          <tbody>
            <tr><td class="lb">Admit Card Number</td><td class="sp">:</td><td class="vl"><strong>${val(admit_no)}</strong></td></tr>
            <tr><td class="lb">Candidate's Name</td><td class="sp">:</td><td class="vl">${val(doc.candidate_name)}</td></tr>
            <tr><td class="lb">Date of Birth</td><td class="sp">:</td><td class="vl">${val(dob)}</td></tr>
            <tr><td class="lb">Father's Name</td><td class="sp">:</td><td class="vl">${val(doc.father_name)}</td></tr>
            <tr><td class="lb">Mother's Name</td><td class="sp">:</td><td class="vl">${val(doc.mother_name)}</td></tr>
            <tr><td class="lb">Gender</td><td class="sp">:</td><td class="vl">${val(doc.gender)}</td></tr>
            <tr><td class="lb">Programme Applied</td><td class="sp">:</td><td class="vl">${val(doc.program)}</td></tr>
            <tr><td class="lb">Application Number</td><td class="sp">:</td><td class="vl">${val(doc.applicant)}</td></tr>
            <tr><td class="lb">Examination Date &amp; Time</td><td class="sp">:</td><td class="vl">${exam_date_time}</td></tr>
            <tr><td class="lb">Reporting Time</td><td class="sp">:</td><td class="vl">30 minutes before scheduled time</td></tr>
            <tr><td class="lb">Seat Number</td><td class="sp">:</td><td class="vl"><span class="seat-pill">${val(f_seat)}</span></td></tr>
            <tr><td class="lb">Room / Hall</td><td class="sp">:</td><td class="vl">${val(f_room)}${f_code && f_code.trim() ? "&nbsp; (Code:&nbsp;" + esc(f_code) + ")" : ""}</td></tr>
            <tr><td class="lb">Building / Floor</td><td class="sp">:</td><td class="vl">${val(f_building)}${f_floor && f_floor.trim() ? "&nbsp; &middot;&nbsp; Floor:&nbsp;" + esc(f_floor) : ""}</td></tr>
            <tr><td class="lb">Allocation Status</td><td class="sp">:</td><td class="vl"><span class="status-pill">${val(f_status)}</span></td></tr>
            <tr><td class="lb">Test Centre Name &amp;&nbsp;Address</td><td class="sp">:</td><td class="vl" style="font-size:11.5px;">${centre_full}</td></tr>
          </tbody>
        </table>
      </td>
      <td class="photo-col-cell">
        <div class="photo-inner-wrap">
          <div class="photo-box-inner" style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
            <div class="photo-frame">
              ${profile_image_url
                ? `<img src="${profile_image_url}" alt="Candidate Photo" width="120" height="150" style="width: 120px; height: 150px; object-fit: cover; display: block;">`
                : `<div class="photo-ph">👤</div>`
              }
            </div>
            <div class="photo-cap">Candidate's Photograph</div>
          </div>
          <div class="photo-sig-box" style="width: 100%; text-align: center; padding-bottom: 5px;">
            <div style="height: 40px; border-bottom: 1px solid #999; margin-bottom: 4px;"></div>
            <div style="font-size: 8px; font-family: Arial, sans-serif; font-weight: bold; text-transform: uppercase; color: #333; letter-spacing: -0.2px;">Candidate's Signature</div>
          </div>
        </div>
      </td>
    </tr>
  </table>

  <!-- Signature -->
  <div class="sig-note">To be signed in the presence of the Invigilator in the Examination Hall</div>
  <table class="sig-tbl">
    <tr>
      <td>
        <div class="sig-cell-inner">
          <span class="sig-hdr">Candidate's Signature</span>
          <span class="sig-body"></span>
        </div>
      </td>
      <td>
        <div class="sig-cell-inner">
          <span class="sig-hdr">Invigilator's Signature</span>
          <span class="sig-body"></span>
        </div>
      </td>
    </tr>
  </table>

</div><!-- /PAGE 1 -->


<!-- ════════════════════════════════════
     PAGE 2 — Instructions
════════════════════════════════════ -->
<div class="card-page p2">

  <!-- header removed as per new layout -->

  <div class="inst-outer">
    <div class="inst-main-title">Instructions to Candidates</div>

    <!-- 1 -->
    <div class="sec-title">1.&nbsp;&nbsp; General Instructions</div>
    <ul class="il">
      <li><span class="mk">a.</span><span>Candidates should check and review their admit cards carefully and make sure that their Name, Date of Birth, and other personal details mentioned in the admit card are as per the details filled by them in the application form. In case of any discrepancy, please contact the Examination Cell immediately.</span></li>
      <li><span class="mk">b.</span><span>Please carry a printed copy of this admit card to the test centre.</span></li>
    </ul>

    <!-- 2 -->
    <div class="sec-title">2.&nbsp;&nbsp; Reporting to the Test Centre &amp; Test Timings</div>
    <ul class="il">
      <li><span class="mk">a.</span><span>Candidates will be allowed to enter the premises of the test centre 30 minutes before the examination start time and should be seated in the examination hall at least 15 minutes before commencement.</span></li>
      <li><span class="mk">b.</span><span>Candidates should carry a Government-issued photo ID card, preferably the one uploaded with the application form. The ID card will be checked at the time of entry into the centre.</span></li>
      <li><span class="mk">c.</span><span>Candidates who arrive at the test centre beyond the scheduled entry cut-off time will not be permitted entry.</span></li>
      <li><span class="mk">d.</span><span>Once the test commences, Candidates will not be permitted to leave the examination hall until the test is completed, and all the Question Booklets and OMR response sheets have been collected by the invigilator/s.</span></li>
    </ul>

    <!-- 3 -->
    <div class="sec-title">3.&nbsp;&nbsp; Pre-Test Instructions</div>
    <ul class="il">
      <li><span class="mk">a.</span><span>Candidates shall be required to follow all directions issued by the Centre Coordinators and the Institution representatives at their respective test centres.</span></li>
      <li><span class="mk">b.</span><span>Candidates must maintain all protocols in place at their respective test centres.</span></li>
    </ul>

    <!-- 4 -->
    <div class="sec-title">4.&nbsp;&nbsp; Permitted Items</div>
    <ul class="il">
      <li><span class="mk">a.</span><span>Candidates will only be permitted to carry the following inside the Test Centre:</span></li>
    </ul>
    <ul class="sl">
      <li><span class="mk">i.</span><span>Admit Card (In case the photograph on the Admit Card is not clear, candidates should carry a self-attested passport size photograph).</span></li>
      <li><span class="mk">ii.</span><span>Government Issued Photo ID (preferably the one uploaded with the application form).</span></li>
      <li><span class="mk">iii.</span><span>Black or Blue Ballpoint pen.</span></li>
      <li><span class="mk">iv.</span><span>A transparent water bottle.</span></li>
      <li><span class="mk">v.</span><span>A face mask (the Candidate may be asked to remove the face mask for ascertainment of identity).</span></li>
      <li><span class="mk">vi.</span><span>An analogue watch. <strong>Note:</strong> Smart Watches are not permitted.</span></li>
    </ul>

    <!-- 5 -->
    <div class="sec-title">5.&nbsp;&nbsp; Admissions Test Related Instructions</div>
    <ul class="il">
      <li><span class="mk">a.</span><span>An attendance sheet will be circulated during the admissions test. The requisite details should be filled in the attendance sheet.</span></li>
      <li><span class="mk">b.</span><span>Candidates will be provided with a Question Booklet and/or answer sheets. Candidates should use black/blue ball point pen <strong>only</strong> to enter the admit card number and other required details.</span></li>
      <li><span class="mk">c.</span><span>Candidates must read the instructions provided with the Question Booklet before commencing the test.</span></li>
      <li><span class="mk">d.</span><span>Candidates should write the details required on the cover page of the Question Booklet.</span></li>
      <li><span class="mk">e.</span><span>No clarifications can be sought about the Question Booklet from anyone.</span></li>
      <li><span class="mk">f.</span><span>Candidates shall not carry the Question Booklet out of the examination hall under any circumstances.</span></li>
    </ul>

    <!-- 6 -->
    <div class="sec-title">6.&nbsp;&nbsp; Documents to be retained by the Candidate after the test</div>
    <ul class="il">
      <li><span class="mk">a.</span><span>The admit card, with the invigilator's signature, should be retained by the candidate and produced at the Institution at the time of admission.</span></li>
    </ul>

    <!-- 7 -->
    <div class="sec-title">7.&nbsp;&nbsp; Malpractice</div>
    <ul class="il">
      <li><span class="mk">a.</span><span>The use of any unfair means by a Candidate shall result in their disqualification and cancellation of their test.</span></li>
      <li><span class="mk">b.</span><span>Impersonation is an offence, and the Candidate, apart from being disqualified, shall be liable to penal action under the law.</span></li>
      <li><span class="mk">c.</span><span>Possession of electronic devices, including mobile phones, headphones, earphones, smart watches, calculators etc., is strictly prohibited in the examination hall.</span></li>
    </ul>

  </div><!-- /inst-outer -->

  <!-- Footer -->
  <div class="pg-footer">
    <span>Doc: <strong>${val(doc.name)}</strong> &nbsp;·&nbsp; Generated: <strong>${val(issue_date)}</strong> &nbsp;·&nbsp; System-generated. No physical signature required.</span>
    <span>${val(admit_no)}</span>
  </div>

</div><!-- /PAGE 2 -->


<script>
  window.addEventListener("load", function () {
    setTimeout(function () { window.print(); }, 900);
  });
</script>
</body>
</html>`;

  // ── Open popup ──
  const win = window.open("", "_blank", "width=940,height=1100,scrollbars=yes,resizable=yes");
  if (!win) {
    frappe.msgprint({
      title: __("Popup Blocked"),
      message: __("Please allow pop-ups for this site and try again."),
      indicator: "orange"
    });
    return;
  }

  win.document.open();
  win.document.write(html);
  win.document.close();

  // Silently mark admit card as generated
  if (!doc.admit_card_generated) {
    frappe.call({
      method: "frappe.client.set_value",
      args: {
        doctype: "Entrance Test Seat Allocation",
        name: doc.name,
        fieldname: { admit_card_generated: 1, admit_card_number: admit_no }
      },
      callback: function () { if (frm) frm.reload_doc(); }
    });
  }

  frappe.show_alert({
    message: __("Admit Card opened. Select <b>Save as PDF</b> in the print dialog."),
    indicator: "green"
  }, 6);
}

function _calculate_total_and_percentage(frm) {
  const part_a = flt(frm.doc.part_a_total_marks_scored || 0);
  const part_b = flt(frm.doc.part_b_total_marks_scored || 0);
  const total = part_a + part_b;
  
  frm.set_value("total_marks_secured_in_part_a_b", total);
  
  const max_marks = flt(frm.doc.total_marks || 200);
  if (max_marks > 0) {
    const percentage = (total / max_marks) * 100.0;
    frm.set_value("percentage", percentage);
  } else {
    frm.set_value("percentage", 0);
  }
}

function _handle_international_applicant_visibility(frm) {
  const is_intl = frm.doc.is_international_applicant === 1;
  // Hide the tab "Seat Allocation"
  frm.set_df_property("tab_allocation", "hidden", is_intl ? 1 : 0);

  // Hide the individual fields in that tab
  const fields = [
    "entrance_test_provider",
    "assigned_preferences",
    "center_name",
    "center_address",
    "room_code",
    "room_name",
    "building",
    "floor",
    "seat_number",
    "admit_card_download"
  ];
  fields.forEach(f => {
    frm.set_df_property(f, "hidden", is_intl ? 1 : 0);
  });
}
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, getdate
from frappe.utils.data import format_date, get_link_to_form
from slcm.admission.utils.institution import is_multi_campus_enabled


APPLICATION_ID_SERIES_PATTERN = re.compile(r"\{(#+)\}")


def _is_valid_application_id_format(application_id_format):
    if not (application_id_format or "").startswith("format:"):
        return False
    series_tokens = APPLICATION_ID_SERIES_PATTERN.findall(application_id_format)
    return len(series_tokens) == 1 and 5 <= len(series_tokens[0]) <= 6


def _overlap_rows_with_labels(overlaps):
    """Attach start_label / end_label (e.g. 12 Mar 2026) for API consumers."""
    out = []
    for row in overlaps:
        d = dict(row)
        d["start_label"] = (
            format_date(row.get("cycle_start_date"), "dd MMM yyyy")
            if row.get("cycle_start_date")
            else "—"
        )
        d["end_label"] = (
            format_date(row.get("cycle_end_date"), "dd MMM yyyy")
            if row.get("cycle_end_date")
            else "—"
        )
        out.append(d)
    return out


def get_overlapping_admission_cycles(start_date, end_date, exclude_name=None, status=None):
    """
    Return cycles whose [cycle_start_date, cycle_end_date] overlaps [start_date, end_date] (inclusive).
    Overlap iff existing_start <= end_date and existing_end >= start_date.
    """
    if not start_date or not end_date:
        return []
        
    start_d = getdate(start_date)
    end_d = getdate(end_date)
    
    if start_d > end_d:
        return []

    filters = {
        "cycle_start_date": ["<=", end_d],
        "cycle_end_date": [">=", start_d],
        "docstatus": ["<", 2],
    }
    
    if exclude_name:
        filters["name"] = ["!=", exclude_name]
    
    if status:
        filters["status"] = status
    else:
        # By default, only check against Draft/Active cycles
        filters["status"] = ["in", ["Draft", "Active"]]

    overlaps = frappe.get_all(
        "Admission Cycle",
        filters=filters,
        fields=["name", "cycle_name", "cycle_start_date", "cycle_end_date", "status"],
        order_by="cycle_start_date asc",
    )
    
    return overlaps


class AdmissionCycle(Document):

    def validate(self):
        self._validate_cycle_date_range()
        self._validate_application_date_range()
        self._validate_cycle_dates_no_overlap()
        self._validate_single_active_cycle()
        self._validate_programs()
        self._validate_application_id_configurations()

    def on_submit(self):
        """Automatically set status to Active on submission."""
        if self.status != "Active":
            self.db_set("status", "Active")
            self.status = "Active" # Update local object for the rest of request
        self.create_audit_log()


    def _validate_cycle_date_range(self):
        if not self.cycle_start_date or not self.cycle_end_date:
            return
        if getdate(self.cycle_start_date) > getdate(self.cycle_end_date):
            frappe.throw(
                _("Cycle Start Date cannot be after Cycle End Date."),
                title=_("Invalid dates"),
            )

    def _validate_application_date_range(self):
        if not self.application_start_date or not self.application_end_date:
            return
        app_start = getdate(self.application_start_date)
        app_end = getdate(self.application_end_date)
        cyc_start = getdate(self.cycle_start_date) if self.cycle_start_date else None
        cyc_end = getdate(self.cycle_end_date) if self.cycle_end_date else None

        if app_start > app_end:
            frappe.throw(
                _("Application Start Date cannot be after Application End Date."),
                title=_("Invalid dates"),
            )

        if cyc_start and app_start < cyc_start:
            frappe.throw(
                _("Application Start Date must be on or after Cycle Start Date."),
                title=_("Invalid dates"),
            )

        if cyc_end and app_end > cyc_end:
            frappe.throw(
                _("Application End Date must be on or before Cycle End Date."),
                title=_("Invalid dates"),
            )

    def _validate_cycle_dates_no_overlap(self):
        if self.status not in ["Draft", "Active"]:
            return
        if not self.cycle_start_date or not self.cycle_end_date:
            return

        conflicting_cycle = frappe.db.get_value(
            "Admission Cycle",
            {
                "status": ["in", ["Draft", "Active"]],
                "name": ("!=", self.name),
                "cycle_start_date": ("<=", self.cycle_end_date),
                "cycle_end_date": (">=", self.cycle_start_date),
                "docstatus": ("<", 2)
            },
            ["name", "cycle_name", "cycle_start_date", "cycle_end_date"],
            as_dict=True
        )

        if not conflicting_cycle:
            return

        sd = format_date(conflicting_cycle.cycle_start_date, "dd MMM yyyy") if conflicting_cycle.cycle_start_date else "—"
        ed = format_date(conflicting_cycle.cycle_end_date, "dd MMM yyyy") if conflicting_cycle.cycle_end_date else "—"
        label = escape_html(conflicting_cycle.cycle_name or conflicting_cycle.name or "")
        link = get_link_to_form("Admission Cycle", conflicting_cycle.name, label=label)

        msg = _("The selected date range overlaps with an existing Active admission cycle: <b>{0}</b> ({1} to {2})").format(
            link, sd, ed
        )
        msg += "<br><br>" + _("Please adjust the dates to avoid overlapping periods for multiple Active cycles.")
        
        frappe.throw(msg, title=_("Admission Cycle Dates Conflict"))


    def _validate_single_active_cycle(self):
        """Only one cycle can be Active at a time."""
        if self.status == "Active":
            existing = frappe.db.get_value(
                "Admission Cycle",
                {"status": "Active", "name": ("!=", self.name)},
                "cycle_name"
            )
            if existing:
                frappe.throw(
                    msg=_("Cycle <b>{0}</b> is already Active. Close it before activating this one.").format(existing),
                    title=_("Active Cycle Conflict"),
                    primary_action={
                        "label": _("Go to {0}").format(existing),
                        "client_action": "frappe.set_route",
                        "args": ["Form", "Admission Cycle", existing]
                    }
                )

    def _validate_programs(self):
        """Validate duplicate program rows with optional campus constraints."""
        multi_campus = is_multi_campus_enabled()
        seen = set()
        for row in (self.programs or []):
            campus = (row.campus or "").strip()
            if multi_campus and not campus:
                frappe.throw(
                    _("Campus is mandatory for Program <b>{0}</b> when Multi Campus is enabled.").format(
                        row.program_name or row.program or _("Unknown")
                    )
                )

            key = (row.program, campus) if multi_campus else (row.program,)
            if key in seen:
                if multi_campus:
                    frappe.throw(
                        _(
                            "Duplicate entry: Program <b>{0}</b> with Campus <b>{1}</b> is already added in this cycle."
                        ).format(row.program_name or row.program, campus)
                    )
                frappe.throw(
                    _("Duplicate entry: Program <b>{0}</b> is already added in this cycle.").format(
                        row.program_name or row.program
                    )
                )
            seen.add(key)

    def _validate_application_id_configurations(self):
        configured_programmes = set()
        for row in self.application_id_configuration or []:
            if not row.programme:
                frappe.throw(_("Programme is required for each Application ID Configuration row."))

            if row.programme in configured_programmes:
                frappe.throw(
                    _("Application ID Configuration has duplicate Programme {0}.").format(
                        frappe.bold(row.programme)
                    )
                )
            configured_programmes.add(row.programme)

            formats = {
                _("Domestic"): row.domestic_application_id_format,
                _("International"): row.international_application_id_format,
            }
            for label, application_id_format in formats.items():
                if not _is_valid_application_id_format(application_id_format):
                    frappe.throw(
                        _(
                            "{0} Application ID Format for Programme {1} must use Frappe format syntax "
                            "and contain exactly one five- or six-digit series, for example "
                            "format:B6{{######}}."
                        ).format(label, frappe.bold(row.programme))
                    )

            if row.domestic_application_id_format == row.international_application_id_format:
                frappe.throw(
                    _("Domestic and International Application ID Formats must differ for Programme {0}.").format(
                        frappe.bold(row.programme)
                    )
                )

    def get_active_programs(self):
        """Returns list of active program rows in this cycle."""
        return [p for p in (self.programs or []) if p.is_active]

    def on_update(self):
        if not self.flags.in_reservation_sync:
            self._sync_reservation_policies()
        self.create_audit_log()

    def before_cancel(self):
        if self.status not in ["Active", "Closed"]:
            frappe.throw(
                _("Only Active or Closed admission cycles can be cancelled. Current status: {0}").format(self.status),
                title=_("Invalid Status")
            )

    def on_cancel(self):
        self.status = "Closed"
        self.db_set("status", "Closed")
        self.create_audit_log()

    def _sync_reservation_policies(self):
        """
        Sync total_seats from cycle programs to linked Reservation Policies.
        Recalculates category seats based on percentage if seats changed.
        """
        for row in (self.programs or []):
            if row.reservation_policy:
                try:
                    policy = frappe.get_doc("Programme Reservation Policy", row.reservation_policy)
                    if int(policy.total_seats or 0) != int(row.seats or 0):
                        policy.total_seats = row.seats
                        # Recalculate child row seats proportionally
                        categories = policy.get("categories") or []
                        if len(categories) == 1:
                            # Single category: give it all seats even if percentage is missing
                            categories[0].seats = policy.total_seats
                            if not categories[0].percentage:
                                categories[0].percentage = 100.0
                        else:
                            for cat in categories:
                                if cat.percentage:
                                    cat.seats = int((policy.total_seats * cat.percentage) / 100)
                        
                        policy.flags.in_cycle_sync = True
                        policy.save(ignore_permissions=True)
                        
                        # Also update row application_count from policy summary if needed
                        # (Summary might have updated in policy.save via _recalculate_summary)
                        if row.application_count != policy.total_filled:
                            row.application_count = policy.total_filled
                            row.db_update()

                except Exception as e:
                    frappe.log_error(f"Failed to sync policy {row.reservation_policy}: {e}", "Admission Cycle")

    def on_update_after_submit(self):
        self.create_audit_log()

    def create_audit_log(self):
        old_doc = self.get_doc_before_save()
        if not old_doc:
            self._log_audit_entry(
                changed_field="Admission Cycle",
                previous_value="N/A",
                new_value="Created",
                change_type="Status Change",
                reason="Admission Cycle Created"
            )
            return

        # 1. Compare Main Fields
        meta = frappe.get_meta(self.doctype)
        for df in meta.fields:
            if df.fieldtype in ["Section Break", "Column Break", "Tab Break", "HTML", "Heading"]:
                continue
            if df.fieldtype == "Table":
                self._compare_child_table(df.fieldname, df.label or df.fieldname)
                continue
            
            field = df.fieldname
            old_val = old_doc.get(field)
            new_val = self.get(field)
            
            if df.fieldtype in ["Date", "Datetime"]:
                old_val_norm = str(old_val) if old_val else ""
                new_val_norm = str(new_val) if new_val else ""
                if old_val_norm != new_val_norm:
                    change_type = "Deadline Change" if field in ["cycle_start_date", "cycle_end_date", "application_start_date", "application_end_date"] else "Rule Change"
                    self._log_audit_entry(
                        changed_field=df.label or field,
                        previous_value=old_val_norm,
                        new_value=new_val_norm,
                        change_type=change_type
                    )
                continue

            if old_val != new_val:
                change_type = "Rule Change"
                if field == "status":
                    change_type = "Status Change"
                
                self._log_audit_entry(
                    changed_field=df.label or field,
                    previous_value=old_val,
                    new_value=new_val,
                    change_type=change_type
                )

    def _compare_child_table(self, fieldname, table_label):
        old_doc = self.get_doc_before_save()
        if not old_doc:
            return

        old_rows = old_doc.get(fieldname) or []
        new_rows = self.get(fieldname) or []

        old_map = {row.name: row for row in old_rows if row.name}
        new_map = {row.name: row for row in new_rows if row.name}

        def get_row_identity(row):
            for key in ["program", "stage_name", "stage", "entrance_test", "test_name"]:
                if row.get(key):
                    return row.get(key)
            return row.name or f"Row {row.idx}"

        # 1. Deleted rows
        for name, old_row in old_map.items():
            if name not in new_map:
                ident = get_row_identity(old_row)
                self._log_audit_entry(
                    changed_field=f"{table_label}: {ident}",
                    previous_value="Present",
                    new_value="Deleted",
                    change_type="Stage Config Change"
                )

        # 2. Added rows
        for name, new_row in new_map.items():
            if name not in old_map:
                ident = get_row_identity(new_row)
                details = []
                row_meta = frappe.get_meta(new_row.doctype)
                for rdf in row_meta.fields:
                    if rdf.fieldtype in ["Section Break", "Column Break", "Tab Break", "HTML", "Heading", "Table"]:
                        continue
                    val = new_row.get(rdf.fieldname)
                    if val is not None and val != "":
                        details.append(f"{rdf.label or rdf.fieldname}: {val}")
                new_val_summary = "; ".join(details) if details else "Added"
                self._log_audit_entry(
                    changed_field=f"{table_label}: {ident}",
                    previous_value="N/A",
                    new_value=new_val_summary,
                    change_type="Stage Config Change"
                )

        # 3. Modified rows
        for name, new_row in new_map.items():
            if name in old_map:
                old_row = old_map[name]
                ident = get_row_identity(new_row)
                row_meta = frappe.get_meta(new_row.doctype)
                for rdf in row_meta.fields:
                    if rdf.fieldtype in ["Section Break", "Column Break", "Tab Break", "HTML", "Heading", "Table"]:
                        continue
                    field = rdf.fieldname
                    old_val = old_row.get(field)
                    new_val = new_row.get(field)
                    if old_val != new_val:
                        self._log_audit_entry(
                            changed_field=f"{table_label} -> {ident} -> {rdf.label or field}",
                            previous_value=old_val,
                            new_value=new_val,
                            change_type="Stage Config Change"
                        )

    def _log_audit_entry(self, changed_field, previous_value, new_value, change_type, reason=None):
        user = frappe.session.user if frappe.session else "Administrator"
        roles = frappe.get_roles(user) if user else []
        role_str = ", ".join(roles) if roles else "Guest"
        if len(role_str) > 140:
            role_str = role_str[:137] + "..."
        
        if (previous_value is None or previous_value == "") and (new_value is None or new_value == ""):
            return

        prev_str = str(previous_value) if previous_value is not None else ""
        new_str = str(new_value) if new_value is not None else ""
        if not prev_str:
            prev_str = "N/A"
        if not new_str:
            new_str = "N/A"

        try:
            audit_log = frappe.get_doc({
                "doctype": "Admission Cycle Audit Log",
                "admission_cycle": self.name,
                "changed_field": changed_field,
                "changed_by": user,
                "role": role_str,
                "change_timestamp": frappe.utils.now_datetime(),
                "previous_value": prev_str,
                "new_value": new_str,
                "change_type": change_type,
                "reason": reason or ""
            })
            audit_log.insert(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(title="Admission Cycle Audit Log Error", message=frappe.get_traceback())


@frappe.whitelist()
def activate_cycle(name):
    """
    Activate a Draft admission cycle.
    Sets status to 'Active' and docstatus to 1 (Submitted) atomically via db_set.
    This ensures the list view never shows 'Draft' for an Active cycle.
    """
    if not name:
        return {"success": False, "message": _("Missing Cycle Name")}

    doc = frappe.get_doc("Admission Cycle", name)
    if doc.status == "Active":
        return {"success": True, "message": _("Cycle is already Active")}

    # Conflict check: only one Active cycle at a time
    existing_active = frappe.db.get_value(
        "Admission Cycle",
        {"status": "Active", "name": ("!=", doc.name)},
        "cycle_name"
    )
    if existing_active:
        return {
            "success": False,
            "message": _("Cycle <b>{0}</b> is already Active. Close it before activating this one.").format(existing_active),
            "conflict_name": existing_active
        }

    try:
        doc.db_set("status", "Active")
        doc.db_set("docstatus", 1)  # Ensure Frappe treats this as Submitted
        doc._log_audit_entry(
            changed_field="Status",
            previous_value=doc.status,
            new_value="Active",
            change_type="Status Change",
            reason="Cycle Activated"
        )
        return {"success": True, "message": _("Admission Cycle activated successfully.")}
    except Exception as e:
        frappe.log_error(f"Activate Admission Cycle fail: {e}", "Admission Cycle")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def close_cycle(name):
    """
    Close an Active admission cycle.
    Only the custom `status` field is changed to 'Closed'.
    docstatus is intentionally left at 1 (Submitted) so that Frappe
    does NOT render 'Cancelled' in the list and form views.
    """
    if not name:
        return {"success": False, "message": _("Missing Cycle Name")}

    doc = frappe.get_doc("Admission Cycle", name)
    if doc.status == "Closed":
        return {"success": True, "message": _("Cycle is already Closed")}

    try:
        doc.db_set("status", "Closed")
        doc._log_audit_entry(
            changed_field="Status",
            previous_value="Active",
            new_value="Closed",
            change_type="Status Change",
            reason="Cycle Closed"
        )
        return {"success": True, "message": _("Admission Cycle closed successfully.")}
    except Exception as e:
        frappe.log_error(f"Close Admission Cycle fail: {e}", "Admission Cycle")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def reopen_cycle(name):
    """
    Reopen a Closed admission cycle.
    Sets status back to 'Active' and docstatus back to 1 (Submitted).
    Performs conflict checks (Single Active Cycle + Date Overlaps).
    """
    if not name:
        return {"success": False, "message": _("Missing Cycle Name")}

    doc = frappe.get_doc("Admission Cycle", name)
    if doc.status == "Active":
        return {"success": True, "message": _("Cycle is already Active")}

    # 1. Check for any other Active cycle
    existing_active = frappe.db.get_value(
        "Admission Cycle",
        {"status": "Active", "name": ("!=", doc.name)},
        "cycle_name"
    )
    if existing_active:
        return {
            "success": False,
            "message": _("Cycle <b>{0}</b> is already Active. Close it before reopening this one.").format(existing_active),
            "conflict_name": existing_active
        }

    # 2. Check for date overlaps with other Active cycles (though there should be none due to rule #1)
    overlaps = get_overlapping_admission_cycles(
        doc.cycle_start_date, doc.cycle_end_date, exclude_name=doc.name, status="Active"
    )
    if overlaps:
        return {
            "success": False,
            "message": _("Reopening this cycle would cause a date conflict with another active cycle.")
        }

    # Perform the reopen
    try:
        doc.db_set("status", "Active")
        # docstatus stays at 1 (Submitted) — we never change it on close/reopen.
        doc._log_audit_entry(
            changed_field="Status",
            previous_value="Closed",
            new_value="Active",
            change_type="Status Change",
            reason="Cycle Reopened"
        )
        return {"success": True, "message": _("Admission Cycle reopened successfully.")}
    except Exception as e:
        frappe.log_error(f"Reopen Admission Cycle fail: {e}", "Admission Cycle")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def check_admission_cycle_date_overlap(name=None, cycle_start_date=None, cycle_end_date=None, status=None):
    """
    Desk client: check whether the given period overlaps other cycles.
    Returns { valid, overlaps: [{ name, cycle_name, cycle_start_date, cycle_end_date }], message }.
    """
    if not cycle_start_date or not cycle_end_date:
        return {"valid": True, "overlaps": [], "message": ""}

    try:
        start_d = getdate(cycle_start_date)
        end_d = getdate(cycle_end_date)
    except Exception:
        return {"valid": True, "overlaps": [], "message": ""}

    if start_d > end_d:
        return {
            "valid": False,
            "overlaps": [],
            "message": _("Cycle Start Date cannot be after Cycle End Date."),
        }

    overlaps = get_overlapping_admission_cycles(start_d, end_d, exclude_name=name or None, status=status)
    if not overlaps:
        return {"valid": True, "overlaps": [], "message": ""}

    enriched = _overlap_rows_with_labels(overlaps)
    return {
        "valid": False,
        "overlaps": enriched,
        "message": "",
    }

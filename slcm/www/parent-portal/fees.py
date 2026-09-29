import frappe
from slcm.slcm.utils.parent_portal import get_parent_context

no_cache = 1


def get_context(context):
    student = get_parent_context(context)
    if context.is_guest or context.not_a_parent or not student:
        _set_defaults(context)
        return context

    context.active_page = "fees"
    # Per-section load failures, so one failed query doesn't blank the page
    errors = {}
    context.load_errors = errors

    try:
        sm = student
        student_name = sm.name

        # ── Programme-level fee summary from Student Master ──────────────────
        sm_total   = frappe.utils.flt(sm.total_program_fee or 0)
        sm_disc    = (frappe.utils.flt(sm.discount_amount or 0)
                      or frappe.utils.flt(sm.scholarship_amount or 0))
        sm_paid_raw = frappe.utils.flt(sm.total_paid_amount or 0)
        sm_net     = (frappe.utils.flt(sm.net_program_fee or 0)
                      or max(sm_total - sm_disc, 0))

        # Clamp paid to net so progress bar is never > 100%
        sm_paid        = min(sm_paid_raw, sm_net) if sm_net > 0 else sm_paid_raw
        sm_outstanding = max(sm_net - sm_paid, 0)

        # Derive fee_payment_status from actual numbers (same logic as student portal)
        stored_status = sm.fee_payment_status or "Unpaid"
        if sm_net > 0:
            if sm_outstanding <= 0:
                sm_fee_status = "Paid"
            elif sm_paid > 0:
                sm_fee_status = "Partially Paid"
            else:
                if stored_status in ("Payment Initiated", "Authorized"):
                    sm_fee_status = stored_status
                else:
                    sm_fee_status = "Unpaid"
        else:
            sm_fee_status = stored_status or "Unpaid"

        if sm.fee_structure:
            _fs_data = frappe.db.get_value(
                "Fee Structure", sm.fee_structure,
                ["fee_structure_name", "valid_from", "valid_until", "status"],
                as_dict=True,
            ) or {}
            context.fee_structure_name        = _fs_data.get("fee_structure_name") or sm.fee_structure
            context.fee_structure_valid_from  = str(_fs_data.get("valid_from") or "")
            context.fee_structure_valid_until = str(_fs_data.get("valid_until") or "")
            context.fee_structure_status      = _fs_data.get("status") or ""
        else:
            context.fee_structure_name        = ""
            context.fee_structure_valid_from  = ""
            context.fee_structure_valid_until = ""
            context.fee_structure_status      = ""
        context.fee_structure_doc_name = sm.fee_structure or ""

        # Fee structure components for programme-level breakdown card
        fs_components = []
        if sm.fee_structure:
            try:
                fs_components = frappe.db.sql(
                    """
                    SELECT fcc.component_name, fcc.amount, fcc.total_amount,
                           fcc.is_taxable, fcc.tax_rate, fcc.tax_amount
                    FROM `tabFee Component Child` fcc
                    WHERE fcc.parent = %s AND fcc.parenttype = 'Fee Structure'
                    ORDER BY fcc.idx
                    """,
                    sm.fee_structure,
                    as_dict=True,
                )
            except Exception:
                fs_components = []
                errors["fee_structure"] = True
        context.fs_components = fs_components

        # ── Fee Invoices ─────────────────────────────────────────────────────
        try:
            invoices = frappe.get_all(
                "Fee Invoice",
                filters={"student": student_name},
                fields=[
                    "name", "academic_term", "program", "academic_year",
                    "invoice_date", "due_date",
                    "total_amount", "scholarship_amount", "final_payable_amount",
                    "paid_amount", "outstanding_amount", "status",
                ],
                order_by="academic_term asc, creation asc",
                ignore_permissions=True,
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Parent Portal Fees: invoices")
            invoices = []
            # Summary figures are invoice-driven, so they can't be trusted either
            errors["invoices"] = True
            errors["summary"] = True

        # Fallback scholarship from invoices if SM doesn't have it
        if not sm_disc and invoices:
            sm_disc = sum(frappe.utils.flt(i.scholarship_amount or 0) for i in invoices)

        # ── Hero/summary: same logic as student portal ────────────────────────
        # If invoices exist they are the ground truth. Use SM only when no invoices.
        _use_sm_for_summary = sm_total > 0 and not bool(invoices)

        STATUS_STYLE = {
            "Paid":           {"color": "var(--pp-success)", "bg": "var(--pp-success-bg)", "icon": "check_circle"},
            "Partially Paid": {"color": "var(--pp-warning)", "bg": "var(--pp-warning-bg)", "icon": "timelapse"},
            "Unpaid":         {"color": "var(--pp-danger)",  "bg": "var(--pp-danger-bg)",  "icon": "receipt_long"},
            "Overdue":        {"color": "var(--pp-danger)",  "bg": "var(--pp-danger-bg)",  "icon": "error"},
            "Cancelled":      {"color": "var(--pp-text-4)",  "bg": "var(--pp-border-light)", "icon": "cancel"},
        }

        today = frappe.utils.getdate(frappe.utils.today())
        term_map = {}

        for inv in invoices:
            # Per-invoice data-sanity: clamp paid to payable
            inv_payable_amt = frappe.utils.flt(inv.final_payable_amount or 0)
            inv_paid_amt    = frappe.utils.flt(inv.paid_amount or 0)
            if inv_payable_amt > 0:
                inv_paid_amt = min(inv_paid_amt, inv_payable_amt)
            display_outstanding = max(inv_payable_amt - inv_paid_amt, 0)

            # Derive effective invoice status from numbers (same as student portal)
            stored_inv_status = inv.status or "Unpaid"
            if stored_inv_status == "Cancelled":
                effective_status = "Cancelled"
            elif inv_payable_amt > 0 and display_outstanding <= 0:
                effective_status = "Paid"
            elif inv_payable_amt > 0 and inv_paid_amt > 0:
                effective_status = "Partially Paid"
            else:
                effective_status = stored_inv_status if stored_inv_status != "Paid" else "Unpaid"

            inv["eff_status"] = effective_status  # no underscore prefix — Jinja blocks _keys
            sc = STATUS_STYLE.get(effective_status, STATUS_STYLE["Unpaid"])
            inv["status_color"] = sc["color"]
            inv["status_bg"]    = sc["bg"]
            inv["status_icon"]  = sc["icon"]
            inv["is_overdue"]   = (
                effective_status not in ("Paid", "Cancelled")
                and inv.due_date
                and frappe.utils.getdate(inv.due_date) < today
            )
            inv["can_pay"] = (
                effective_status not in ("Paid", "Cancelled")
                and display_outstanding > 0
            )
            inv["formatted_payable"]     = "₹{:,.0f}".format(inv_payable_amt)
            inv["formatted_paid"]        = "₹{:,.0f}".format(inv_paid_amt)
            inv["formatted_outstanding"] = "₹{:,.0f}".format(display_outstanding)
            inv["outstanding_amount"]    = display_outstanding
            inv["paid_amount"]           = inv_paid_amt

            # Fee component breakdown
            try:
                components = frappe.db.sql(
                    """
                    SELECT fcc.component_name, fcc.amount, fcc.total_amount,
                           COALESCE(fc.component_type, 'Other') AS component_type
                    FROM `tabFee Component Child` fcc
                    LEFT JOIN `tabFee Component` fc ON fcc.fee_component = fc.name
                    WHERE fcc.parent = %s AND fcc.parenttype = 'Fee Invoice'
                    ORDER BY fcc.idx
                    """,
                    inv.name,
                    as_dict=True,
                )
                inv["fee_components"] = components or []
            except Exception:
                inv["fee_components"] = []

            # Payment history
            try:
                payments = frappe.get_all(
                    "Fee Payment Entry",
                    filters={"parent": inv.name},
                    fields=["payment", "payment_date", "amount", "payment_mode"],
                    order_by="payment_date desc",
                    ignore_permissions=True,
                )
                for p in payments:
                    try:
                        p["reference_number"] = frappe.db.get_value(
                            "Fee Payment", p.payment, "reference_number") or ""
                    except Exception:
                        p["reference_number"] = ""
                    p["rzp_status"]  = "Captured"
                    p["is_rzp_only"] = False
            except Exception:
                payments = []

            try:
                attempt_irs = frappe.get_all(
                    "Integration Request",
                    filters={
                        "reference_doctype": "Fee Invoice",
                        "reference_docname": inv.name,
                        "status": ["not in", ["Pending", "Queued"]],
                    },
                    fields=["name", "modified", "status", "payment_id"],
                    order_by="modified desc",
                    ignore_permissions=True,
                )
                for ir in attempt_irs:
                    if ir.status == "Completed":
                        continue
                    payments.append({
                        "payment":      ir.payment_id or ir.name,
                        "payment_date": ir.modified,
                        "amount":       0,
                        "payment_mode": "",
                        "rzp_status":   ir.status,
                        "is_rzp_only":  True,
                    })
            except Exception:
                pass

            inv["payments"] = payments

            # Receipts (same as student portal)
            try:
                fp_rows = frappe.get_all(
                    "Fee Payment",
                    filters={"fee_invoice": inv.name, "status": "Submitted",
                             "receipt": ["is", "set"]},
                    fields=["name", "receipt", "reference_number",
                            "payment_mode", "amount", "payment_date"],
                    ignore_permissions=True,
                )
                receipts = []
                for fp in fp_rows:
                    receipts.append({
                        "receipt_name":     fp.receipt,
                        "reference_number": fp.reference_number or "",
                        "payment_mode":     fp.payment_mode or "",
                        "formatted_amount": "₹{:,.0f}".format(
                            frappe.utils.flt(fp.amount or 0)),
                        "payment_date":     fp.payment_date,
                    })
                inv["receipts"]    = receipts
                inv["has_receipt"] = bool(receipts)
            except Exception:
                inv["receipts"]    = []
                inv["has_receipt"] = False

            # Group by term
            term_key = inv.academic_term or "General"
            if term_key not in term_map:
                term_map[term_key] = {
                    "term": term_key,
                    "academic_year": inv.academic_year or "",
                    "invoices": [],
                    "term_total": 0.0,
                    "term_paid": 0.0,
                    "term_outstanding": 0.0,
                }
            term_map[term_key]["invoices"].append(inv)
            term_map[term_key]["term_total"]       += inv_payable_amt
            term_map[term_key]["term_paid"]        += inv_paid_amt
            term_map[term_key]["term_outstanding"] += display_outstanding

        # Format term totals
        for t in term_map.values():
            t["formatted_term_total"]       = "₹{:,.0f}".format(t["term_total"])
            t["formatted_term_paid"]        = "₹{:,.0f}".format(t["term_paid"])
            t["formatted_term_outstanding"] = "₹{:,.0f}".format(t["term_outstanding"])
            t["term_has_dues"]              = t["term_outstanding"] > 0

        context.term_groups  = list(term_map.values())
        context.has_invoices = bool(invoices)
        context.has_fee_data = sm_total > 0 or bool(invoices)

        # ── Apply hero/summary context (same logic as student portal) ─────────
        if _use_sm_for_summary:
            context.total_fee         = sm_total
            context.total_scholarship = sm_disc
            context.total_paid        = sm_paid
            context.total_net         = sm_net
            context.total_payable     = sm_net
            context.total_outstanding = sm_outstanding
            context.has_dues          = sm_outstanding > 0
            context.sm_fee_status     = sm_fee_status
            context.has_sm_inv_mismatch = False
            context.sm_scholarship_amt  = sm_disc
            context.inv_scholarship_amt = 0.0
            context.mismatch_diff       = 0.0
            context.inv_outstanding_raw = sm_outstanding
            context.has_overpayment_flag = sm_paid_raw > sm_net and sm_net > 0
        else:
            inv_payable     = sum(frappe.utils.flt(i.final_payable_amount or 0) for i in invoices)
            inv_paid        = sum(frappe.utils.flt(i.get("paid_amount") or 0) for i in invoices)
            inv_outstanding = sum(frappe.utils.flt(i.get("outstanding_amount") or 0) for i in invoices)
            inv_scholarship = sum(frappe.utils.flt(i.scholarship_amount or 0) for i in invoices)

            if inv_payable > 0:
                if inv_outstanding <= 0:
                    agg_status = "Paid"
                elif inv_paid > 0:
                    agg_status = "Partially Paid"
                else:
                    if sm_fee_status in ("Payment Initiated", "Authorized"):
                        agg_status = sm_fee_status
                    else:
                        agg_status = "Unpaid"
            else:
                agg_status = sm_fee_status or ""

            # Scholarship mismatch detection
            sm_sch_rounded  = round(sm_disc, 2)
            inv_sch_rounded = round(inv_scholarship, 2)
            has_mismatch = (
                sm_sch_rounded > inv_sch_rounded
                and abs(sm_sch_rounded - inv_sch_rounded) > 0.5
                and inv_payable > 0
            )
            effective_outstanding = inv_outstanding
            if has_mismatch:
                pending_sch = round(sm_disc - inv_scholarship, 2)
                effective_outstanding = max(inv_outstanding - pending_sch, 0)

            context.total_fee         = sm_total
            context.total_scholarship = sm_disc
            context.total_paid        = inv_paid
            context.total_net         = inv_payable
            context.total_payable     = inv_payable
            context.total_outstanding = effective_outstanding
            context.has_dues          = effective_outstanding > 0
            context.sm_fee_status     = agg_status
            context.has_sm_inv_mismatch = has_mismatch
            context.sm_scholarship_amt  = sm_disc
            context.inv_scholarship_amt = inv_scholarship
            context.mismatch_diff       = round(sm_disc - inv_scholarship, 2)
            context.inv_outstanding_raw = inv_outstanding
            context.has_overpayment_flag = inv_paid > inv_payable and inv_payable > 0

        # ── Concessions ───────────────────────────────────────────────────────
        try:
            concessions = frappe.get_all(
                "Fee Concession",
                filters={"student": student_name},
                fields=[
                    "name", "concession_type", "waiver_value",
                    "waiver_amount", "original_amount", "fee_component",
                    "status", "reason", "approved_by", "approved_on",
                ],
                order_by="approved_on desc, creation desc",
                ignore_permissions=True,
            )
            for c in concessions:
                c["formatted_waiver"]   = "₹{:,.0f}".format(frappe.utils.flt(c.waiver_amount or 0))
                c["approved_on_fmt"]    = (
                    frappe.utils.formatdate(c.approved_on, "dd MMM yyyy")
                    if c.approved_on else ""
                )
                if c.approved_by:
                    c["approved_by_name"] = (
                        frappe.db.get_value("User", c.approved_by, "full_name") or c.approved_by
                    )
                else:
                    c["approved_by_name"] = ""
            context.concessions     = concessions
            context.has_concessions = bool(concessions)
        except Exception:
            context.concessions     = []
            context.has_concessions = False
            errors["concessions"] = True

        # ── Fee Demands ───────────────────────────────────────────────────────
        try:
            demands_raw = frappe.get_all(
                "Fee Demand",
                filters={"student": student_name, "status": ["not in", ["Cancelled"]]},
                fields=[
                    "name", "fee_component", "description", "demand_type",
                    "demand_date", "due_date", "status", "academic_year",
                    "original_amount", "waiver_amount", "net_payable",
                    "paid_amount", "credit_adjusted", "outstanding_amount",
                    "trigger_ref_doctype", "trigger_ref_name",
                ],
                order_by="due_date asc, creation asc",
                ignore_permissions=True,
            )
            _today = frappe.utils.getdate(frappe.utils.today())
            overdue_list = []
            for d in demands_raw:
                d["formatted_original"]    = "₹{:,.0f}".format(frappe.utils.flt(d.original_amount or 0))
                d["formatted_waiver"]      = "₹{:,.0f}".format(frappe.utils.flt(d.waiver_amount or 0))
                d["formatted_net"]         = "₹{:,.0f}".format(frappe.utils.flt(d.net_payable or 0))
                d["formatted_paid"]        = "₹{:,.0f}".format(frappe.utils.flt(d.paid_amount or 0))
                d["formatted_outstanding"] = "₹{:,.0f}".format(frappe.utils.flt(d.outstanding_amount or 0))
                settled = frappe.utils.flt(d.paid_amount or 0) + frappe.utils.flt(d.credit_adjusted or 0)
                d["settled_amount"]        = settled
                d["formatted_settled"]     = "₹{:,.0f}".format(settled)
                d["has_credit_adj"]        = frappe.utils.flt(d.credit_adjusted or 0) > 0
                d["formatted_credit_adj"]  = "₹{:,.0f}".format(frappe.utils.flt(d.credit_adjusted or 0))
                d["due_date_fmt"]          = frappe.utils.formatdate(d.due_date, "dd MMM yyyy") if d.due_date else ""
                d["demand_date_fmt"]       = frappe.utils.formatdate(d.demand_date, "dd MMM yyyy") if d.demand_date else ""
                if d.due_date and d.status not in ("Paid", "Waived"):
                    diff = (frappe.utils.getdate(d.due_date) - _today).days
                    d["days_overdue"]       = abs(diff) if diff < 0 else 0
                    d["is_demand_overdue"]  = diff < 0
                else:
                    d["days_overdue"]       = 0
                    d["is_demand_overdue"]  = False
                if d.status == "Overdue" or d["is_demand_overdue"]:
                    overdue_list.append(d)
            context.fee_demands          = demands_raw
            context.has_fee_demands      = bool(demands_raw)
            context.overdue_demands      = overdue_list
            context.has_overdue_demands  = bool(overdue_list)
            context.overdue_demand_count = len(overdue_list)
            context.overdue_total        = sum(frappe.utils.flt(d.outstanding_amount or 0) for d in overdue_list)
            context.formatted_overdue_total = "₹{:,.0f}".format(context.overdue_total)

            # ── Demand Analytics (for the Payment Analytics panel) ──────────
            _flt = frappe.utils.flt
            da_total      = len(demands_raw)
            da_paid       = sum(1 for d in demands_raw if d.status == "Paid")
            da_waived     = sum(1 for d in demands_raw if d.status == "Waived")
            da_overdue    = len(overdue_list)
            da_total_amt  = sum(_flt(d.net_payable or 0)        for d in demands_raw)
            da_paid_amt   = sum(_flt(d.paid_amount or 0) +
                                _flt(d.credit_adjusted or 0)    for d in demands_raw)
            da_waived_amt = sum(_flt(d.waiver_amount or 0)      for d in demands_raw)
            da_outstanding= sum(_flt(d.outstanding_amount or 0) for d in demands_raw
                                if d.status not in ("Paid","Waived","Cancelled"))
            da_pct = int(round(da_paid_amt / da_total_amt * 100)) if da_total_amt > 0 else 0

            context.da_total            = da_total
            context.da_paid             = da_paid
            context.da_waived           = da_waived
            context.da_overdue          = da_overdue
            context.da_pending          = da_total - da_paid - da_waived - da_overdue
            context.da_total_amt        = da_total_amt
            context.da_paid_amt         = da_paid_amt
            context.da_waived_amt       = da_waived_amt
            context.da_outstanding      = da_outstanding
            context.da_pct              = da_pct
            context.da_fmt_total        = "₹{:,.0f}".format(da_total_amt)
            context.da_fmt_paid         = "₹{:,.0f}".format(da_paid_amt)
            context.da_fmt_waived       = "₹{:,.0f}".format(da_waived_amt)
            context.da_fmt_outstanding  = "₹{:,.0f}".format(da_outstanding)
        except Exception:
            context.fee_demands          = []
            context.has_fee_demands      = False
            context.overdue_demands      = []
            context.has_overdue_demands  = False
            context.overdue_demand_count = 0
            context.overdue_total        = 0
            context.formatted_overdue_total = "₹0"
            context.da_total = context.da_paid = context.da_waived = 0
            context.da_overdue = context.da_pending = 0
            context.da_pct = 0
            context.da_fmt_total = context.da_fmt_paid = "₹0"
            context.da_fmt_waived = context.da_fmt_outstanding = "₹0"
            context.da_outstanding = 0
            context.da_total_amt = context.da_paid_amt = context.da_waived_amt = 0
            errors["demands"] = True

        # ── Fee Refunds ────────────────────────────────────────────────────────
        try:
            refunds_raw = frappe.get_all(
                "Fee Refund",
                filters={"student": student_name, "status": ["not in", ["Reversed"]]},
                fields=[
                    "name", "fee_demand", "fee_component",
                    "refund_type", "refund_amount", "refund_date", "refund_mode",
                    "bank_name", "account_number", "utr_number",
                    "status", "approved_by", "approved_on", "reason", "remarks",
                ],
                order_by="refund_date desc, creation desc",
                ignore_permissions=True,
            )
            for r in refunds_raw:
                r["formatted_amount"] = "₹{:,.0f}".format(frappe.utils.flt(r.refund_amount or 0))
                r["refund_date_fmt"]  = frappe.utils.formatdate(r.refund_date, "dd MMM yyyy") if r.refund_date else ""
                r["approved_on_fmt"]  = frappe.utils.formatdate(r.approved_on, "dd MMM yyyy") if r.approved_on else ""
                r["approved_by_name"] = (
                    frappe.db.get_value("User", r.approved_by, "full_name") or r.approved_by
                ) if r.approved_by else ""
                acct = str(r.account_number or "")
                r["masked_account"] = ("•••• " + acct[-4:]) if len(acct) > 4 else acct
                try:
                    r["demand_paid_amount"] = frappe.utils.flt(
                        frappe.db.get_value("Fee Demand", r.fee_demand, "paid_amount") or 0
                    )
                except Exception:
                    r["demand_paid_amount"] = 0
            context.fee_refunds     = refunds_raw
            context.has_fee_refunds = bool(refunds_raw)
        except Exception:
            context.fee_refunds     = []
            context.has_fee_refunds = False
            errors["refunds"] = True

        # ── All Transactions (receipt list) ───────────────────────────────────
        try:
            all_txns = frappe.get_all(
                "Fee Receipt",
                filters={"student": student_name, "status": "Active"},
                fields=[
                    "name", "receipt_date", "amount", "payment_mode",
                    "reference_number", "transaction_date", "academic_year", "bank_name",
                    "fee_payment",
                ],
                order_by="receipt_date desc",
                ignore_permissions=True,
            )
            for txn in all_txns:
                txn["formatted_amount"] = "₹{:,.0f}".format(frappe.utils.flt(txn.amount or 0))
                txn["display_date"] = (
                    frappe.utils.formatdate(txn.receipt_date, "dd MMM yyyy")
                    if txn.receipt_date else ""
                )
            context.all_transactions = all_txns
            context.has_transactions  = bool(all_txns)
        except Exception:
            context.all_transactions = []
            context.has_transactions  = False
            errors["receipts"] = True

        # ── Payment gateway availability ──────────────────────────────────────
        try:
            context.payment_enabled = bool(
                frappe.db.get_single_value("Razorpay Settings", "api_key")
            )
        except Exception:
            context.payment_enabled = False
        # Admin preview is read-only: payments need a real parent session
        if context.get("is_preview"):
            context.payment_enabled = False

        # Payer details for Razorpay prefill (parent pays on behalf of ward)
        try:
            parent_user = frappe.session.user
            parent_doc = frappe.db.get_value(
                "Parent Guardian",
                {"email": parent_user},
                ["full_name", "email", "mobile_number"],
                as_dict=True,
            ) or {}
            context.payer_name  = parent_doc.get("full_name") or parent_user
            context.payer_email = parent_doc.get("email") or parent_user
            context.payer_phone = parent_doc.get("mobile_number") or ""
        except Exception:
            context.payer_name  = ""
            context.payer_email = frappe.session.user
            context.payer_phone = ""

        context.ward_student_name = student_name
        context.ward_enrolment_no = (
            getattr(sm, "enrolment_number", "") or getattr(sm, "student_id", "") or sm.name
        )

        _build_view_model(context, errors)

    except Exception as e:
        frappe.log_error(f"Parent Portal Fees error: {e}", "Parent Portal")
        context.portal_error = str(e)
        _set_defaults(context)

    return context


def _fmt_inr(amount):
    return "₹{:,.0f}".format(frappe.utils.flt(amount or 0))


def _fmt_date(value):
    return frappe.utils.formatdate(value, "dd MMM yyyy") if value else ""


def _build_view_model(context, errors):
    """Display-only shaping of the figures computed above, for the page layout.

    Nothing here changes a fee calculation: it regroups invoices, demands and
    receipts that belong to this one ward into the rows the page renders.
    """
    flt = frappe.utils.flt
    today = frappe.utils.getdate(frappe.utils.today())
    invoices = [inv for tg in context.term_groups for inv in tg["invoices"]]

    # ── Payment progress: paid / net payable, never 100% while dues remain ──
    payable = flt(context.total_payable)
    paid = flt(context.total_paid)
    if payable <= 0:
        paid_pct = None
    elif paid >= payable:
        paid_pct = 100
    else:
        paid_pct = int(paid / payable * 100)
        if context.has_dues:
            paid_pct = min(paid_pct, 99)
    context.paid_pct = paid_pct

    # ── Per-invoice display fields ──────────────────────────────────────────
    for inv in invoices:
        comps = inv.get("fee_components") or []
        inv["label"] = comps[0].component_name if len(comps) == 1 else "Programme Fee"
        status = inv.eff_status or inv.status or "Unpaid"
        if inv.is_overdue and status not in ("Paid", "Cancelled", "Partially Paid"):
            status = "Overdue"
        inv["display_status"] = status
        inv["invoice_date_fmt"] = _fmt_date(inv.invoice_date)
        inv["due_date_fmt"] = _fmt_date(inv.due_date)
        inv["due_hint"], inv["due_hint_tone"] = "", ""
        if status not in ("Paid", "Cancelled") and inv.due_date:
            days_left = (frappe.utils.getdate(inv.due_date) - today).days
            if days_left < 0:
                n = abs(days_left)
                inv["due_hint"] = f"Overdue by {n} day{'s' if n != 1 else ''}"
                inv["due_hint_tone"] = "danger"
            elif days_left <= 7:
                inv["due_hint"] = "Due today" if days_left == 0 else f"Due in {days_left} day{'s' if days_left != 1 else ''}"
                inv["due_hint_tone"] = "warning"

    payable_invoices = [inv for inv in invoices if inv.can_pay]
    context.payable_invoices = payable_invoices

    # ── Overdue (programme invoices only, same scope as the other KPIs) ────
    inv_overdue = sum(
        flt(inv.outstanding_amount) for inv in invoices
        if inv.is_overdue and flt(inv.outstanding_amount) > 0
    )
    context.programme_overdue = min(inv_overdue, flt(context.total_outstanding))
    context.programme_overdue_count = sum(
        1 for inv in invoices if inv.is_overdue and flt(inv.outstanding_amount) > 0
    )
    context.demand_outstanding = flt(context.get("da_outstanding") or 0)
    context.demand_overdue = flt(context.get("overdue_total") or 0)

    # ── Upcoming / outstanding: unpaid invoices + unpaid additional charges ─
    rows = []
    for inv in payable_invoices:
        rows.append(frappe._dict(
            component=inv.label, sub=inv.name, kind="invoice",
            due_date=inv.due_date, due_date_fmt=inv.due_date_fmt,
            amount_fmt=inv.formatted_outstanding, status=inv.display_status,
            is_overdue=bool(inv.is_overdue), academic_year=inv.academic_year or "",
        ))
    for d in context.fee_demands:
        if flt(d.outstanding_amount) <= 0 or d.status in ("Paid", "Waived", "Cancelled"):
            continue
        overdue = d.status == "Overdue" or d.is_demand_overdue
        rows.append(frappe._dict(
            component=d.fee_component or d.description or "Additional charge",
            sub="Additional charge", kind="demand",
            due_date=d.due_date, due_date_fmt=d.due_date_fmt,
            amount_fmt=d.formatted_outstanding,
            status="Overdue" if (d.is_demand_overdue and d.status == "Pending") else d.status,
            is_overdue=bool(overdue), days_overdue=d.days_overdue,
            academic_year=d.academic_year or "",
        ))
    rows.sort(key=lambda r: (r.due_date is None, frappe.utils.getdate(r.due_date) if r.due_date else today))
    context.outstanding_rows = rows
    context.outstanding_overdue_count = sum(1 for r in rows if r.is_overdue)
    context.outstanding_pending_count = len(rows) - context.outstanding_overdue_count

    # ── Payment history: invoice payments + receipts, de-duplicated ─────────
    history = []
    try:
        receipt_by_payment = {
            t.fee_payment: t for t in context.all_transactions if t.get("fee_payment")
        }
        merged_payments = set()
        for inv in invoices:
            for p in inv.get("payments") or []:
                pdate = frappe.utils.getdate(p.get("payment_date")) if p.get("payment_date") else None
                if p.get("is_rzp_only"):
                    history.append(frappe._dict(
                        date=pdate, description=inv.label, sub=inv.name,
                        amount_fmt="", method="Online", reference=p.get("payment") or "",
                        status=p.get("rzp_status") or "Failed", ok=False, receipt="",
                        academic_year=inv.academic_year or "",
                    ))
                    continue
                rc = receipt_by_payment.get(p.get("payment"))
                merged_payments.add(p.get("payment"))
                history.append(frappe._dict(
                    date=pdate, description=inv.label, sub=inv.name,
                    amount_fmt=_fmt_inr(p.get("amount")),
                    method=p.get("payment_mode") or (rc.payment_mode if rc else ""),
                    reference=p.get("reference_number") or (rc.reference_number if rc else "") or "",
                    status="Paid", ok=True, receipt=rc.name if rc else "",
                    academic_year=inv.academic_year or "",
                ))

        standalone = [t for t in context.all_transactions if t.get("fee_payment") not in merged_payments]
        paid_for = {}
        if standalone:
            for row in frappe.get_all(
                "Fee Receipt Demands Paid",
                filters={"parent": ["in", [t.name for t in standalone]], "parenttype": "Fee Receipt"},
                fields=["parent", "description"],
                order_by="idx asc",
                ignore_permissions=True,
            ):
                if row.description:
                    paid_for.setdefault(row.parent, []).append(row.description)
        for t in standalone:
            items = paid_for.get(t.name) or []
            history.append(frappe._dict(
                date=frappe.utils.getdate(t.receipt_date) if t.receipt_date else None,
                description=items[0] if items else "Fee payment",
                sub=(f"+{len(items) - 1} more · " if len(items) > 1 else "") + t.name,
                amount_fmt=t.formatted_amount, method=t.payment_mode or "",
                reference=t.reference_number or "", status="Paid", ok=True,
                receipt=t.name, academic_year=t.academic_year or "",
            ))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Parent Portal Fees: payment history")
        history = []
        errors["payments"] = True

    history.sort(key=lambda h: h.date or frappe.utils.getdate("1900-01-01"), reverse=True)
    for h in history:
        h["date_fmt"] = _fmt_date(h.date)
    context.payment_history = history

    # ── Academic years present in this ward's own fee records ──────────────
    years = {inv.academic_year for inv in invoices if inv.academic_year}
    years |= {d.academic_year for d in context.fee_demands if d.get("academic_year")}
    years |= {t.academic_year for t in context.all_transactions if t.get("academic_year")}
    if context.get("ward_academic_year"):
        years.add(context.ward_academic_year)
    context.fee_academic_years = sorted(years, reverse=True)

    context.has_any_fee_records = bool(
        context.has_fee_data or context.has_fee_demands or context.has_transactions
        or context.has_concessions or context.has_fee_refunds or errors
    )


def _set_defaults(context):
    context.total_fee               = 0.0
    context.total_scholarship       = 0.0
    context.total_paid              = 0.0
    context.total_net               = 0.0
    context.total_payable           = 0.0
    context.total_outstanding       = 0.0
    context.has_dues                = False
    context.sm_fee_status           = ""
    context.fee_structure_name      = ""
    context.fee_structure_doc_name  = ""
    context.fee_structure_valid_from  = ""
    context.fee_structure_valid_until = ""
    context.fee_structure_status    = ""
    context.fs_components           = []
    context.term_groups             = []
    context.has_invoices            = False
    context.has_fee_data            = False
    context.has_sm_inv_mismatch     = False
    context.sm_scholarship_amt      = 0.0
    context.inv_scholarship_amt     = 0.0
    context.mismatch_diff           = 0.0
    context.inv_outstanding_raw     = 0.0
    context.has_overpayment_flag    = False
    context.concessions             = []
    context.has_concessions         = False
    context.fee_demands             = []
    context.has_fee_demands         = False
    context.overdue_demands         = []
    context.has_overdue_demands     = False
    context.overdue_demand_count    = 0
    context.overdue_total           = 0
    context.formatted_overdue_total = "₹0"
    context.fee_refunds             = []
    context.has_fee_refunds         = False
    context.all_transactions        = []
    context.has_transactions        = False
    context.portal_error            = ""
    context.payment_enabled         = False
    context.payer_name              = ""
    context.payer_email             = ""
    context.payer_phone             = ""
    context.ward_student_name       = ""
    context.ward_enrolment_no       = context.get("active_ward") or ""
    context.paid_pct                = None
    context.payable_invoices        = []
    context.programme_overdue       = 0.0
    context.programme_overdue_count = 0
    context.demand_outstanding      = 0.0
    context.demand_overdue          = 0.0
    context.outstanding_rows        = []
    context.outstanding_overdue_count = 0
    context.outstanding_pending_count = 0
    context.payment_history         = []
    context.fee_academic_years      = [context.ward_academic_year] if context.get("ward_academic_year") else []
    context.has_any_fee_records     = bool(context.get("portal_error"))
    context.da_total = context.da_paid = context.da_waived = 0
    context.da_overdue = context.da_pending = context.da_pct = 0
    context.da_total_amt = context.da_paid_amt = context.da_waived_amt = 0
    context.da_outstanding = 0
    context.da_fmt_total = context.da_fmt_paid = "₹0"
    context.da_fmt_waived = context.da_fmt_outstanding = "₹0"
    if context.get("load_errors") is None:
        context.load_errors = {}

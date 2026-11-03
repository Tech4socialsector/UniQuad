"""
Manual settlement sync — backfills settlement data into FLE Payment Log.

Call via bench console:
    frappe.call("slcm.api.sync_settlements.run_sync")

Or via API (System Manager only):
    POST /api/method/slcm.api.sync_settlements.run_sync
"""

import datetime

import frappe
import requests


RAZORPAY_BASE   = "https://api.razorpay.com/v1"
PAGE_SIZE       = 100   # max for /v1/settlements
RECON_PAGE_SIZE = 500   # max per page for /v1/settlements/{id}/recon/combined


@frappe.whitelist()
def diagnose_quick():
    """
    Fast diagnosis — no Razorpay API calls.
    Reads only the local FLE Payment Log table and returns counts in < 1 second.
    """
    total = frappe.db.count("FLE Payment Log")

    with_tid = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabFLE Payment Log` WHERE transaction_id IS NOT NULL AND transaction_id != ''",
    )[0][0]

    without_tid = total - with_tid

    with_name = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabFLE Payment Log` WHERE full_name IS NOT NULL AND full_name != ''",
    )[0][0]

    without_name = total - with_name

    with_settlement = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabFLE Payment Log` WHERE settlement_id IS NOT NULL AND settlement_id != ''",
    )[0][0]

    without_settlement = total - with_settlement

    return {
        "total_fle_records":            total,
        "with_razorpay_payment_id":     with_tid,
        "missing_razorpay_payment_id":  without_tid,
        "with_contact_name":            with_name,
        "missing_contact_name":         without_name,
        "synced_with_settlement":       with_settlement,
        "not_yet_synced":               without_settlement,
    }


@frappe.whitelist()
def diagnose_missing_matches():
    """
    Diagnoses why Contact Name is blank in the settlement report.

    Uses /v1/settlements/recon/combined (same API as the report) to collect
    all settled payment IDs, then cross-checks against FLE Payment Log.
    """
    import json
    from datetime import datetime, timezone

    settings   = frappe.get_single("Razorpay Settings")
    api_key    = settings.api_key
    api_secret = settings.get_password("api_secret")
    if not api_key or not api_secret:
        frappe.throw("API credentials are missing in Razorpay Settings.")

    auth = (api_key, api_secret)

    # Step 1: fetch settlement list
    settlements = _fetch_all_settlements(auth)
    if not settlements:
        return {"error": "No settlements returned from Razorpay. Check API credentials."}

    setl_by_id = {s["id"]: s for s in settlements if s.get("id")}

    # Step 2: collect all payment IDs from recon/combined (same logic as the report)
    # Determine year-months from settlements
    year_months = set()
    for s in settlements:
        ts = s.get("created_at")
        if ts:
            try:
                dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                year_months.add((dt.year, dt.month))
            except Exception:
                pass
    year_months = sorted(year_months)

    target_ids      = set(setl_by_id.keys())
    razorpay_pids   = set()   # pay_xxx IDs from recon
    recon_available = False

    for year, month in year_months:
        skip = 0
        while True:
            resp = requests.get(
                "https://api.razorpay.com/v1/settlements/recon/combined",
                auth=auth,
                params={"year": year, "month": month, "count": 1000, "skip": skip},
                timeout=60,
            )
            if resp.status_code == 404:
                break   # recon not enabled
            if not resp.ok:
                break

            recon_available = True
            items = resp.json().get("items", [])
            for item in items:
                if item.get("settlement_id") not in target_ids:
                    continue
                pid = item.get("entity_id") or item.get("payment_id") or ""
                if pid:
                    razorpay_pids.add(pid)

            if len(items) < 1000:
                break
            skip += 1000

    # Step 3: collect payment IDs from FLE Payment Log
    fle_rows = frappe.db.sql(
        """
        SELECT
            name,
            transaction_id,
            full_name,
            gateway_response
        FROM `tabFLE Payment Log`
        """,
        as_dict=True,
    )

    # Build FLE map — also try extracting pay_xxx from gateway_response
    # when transaction_id is NULL (Integration Request data format)
    fle_tid_map  = {}   # pay_xxx → full_name
    null_tid_rows = 0

    for r in fle_rows:
        tid = (r.transaction_id or "").strip()
        if not tid:
            # Try extracting from gateway_response JSON
            try:
                gw   = json.loads(r.gateway_response or "{}")
                tid  = (
                    gw.get("razorpay_payment_id")
                    or gw.get("payload", {}).get("payment", {}).get("entity", {}).get("id")
                    or ""
                )
            except Exception:
                pass
        if tid:
            fle_tid_map[tid] = r.full_name or ""
        else:
            null_tid_rows += 1

    # Step 4: cross-check
    matched    = [pid for pid in razorpay_pids if pid in fle_tid_map]
    unmatched  = [pid for pid in razorpay_pids if pid not in fle_tid_map]
    blank_name = [pid for pid in matched if not fle_tid_map.get(pid)]

    result = {
        "recon_api_available":           recon_available,
        "total_settlements":             len(settlements),
        "total_razorpay_payment_ids":    len(razorpay_pids),
        "total_fle_payment_log_records": len(fle_rows),
        "fle_rows_with_null_tid":        null_tid_rows,
        "matched_with_fle_log":          len(matched),
        "unmatched_no_fle_log":          len(unmatched),
        "matched_but_blank_name":        len(blank_name),
        "sample_unmatched_ids":          unmatched[:10],
        "sample_blank_name_ids":         blank_name[:10],
    }

    frappe.logger().info(f"diagnose_missing_matches: {result}")
    return result


@frappe.whitelist()
def backfill_contact_names():
    """
    One-time backfill: copies candidate_name and email_address from the linked
    'Foundations for a Legal Education' document into any FLE Payment Log rows
    where full_name is blank.

    Run after deployment to fix all existing records:
        bench execute slcm.api.sync_settlements.backfill_contact_names
    Or via API button in the report.
    """
    rows = frappe.db.sql(
        """
        SELECT fpl.name, fpl.reference_no
        FROM `tabFLE Payment Log` fpl
        WHERE (fpl.full_name IS NULL OR fpl.full_name = '')
          AND fpl.reference_no IS NOT NULL
          AND fpl.reference_no != ''
        """,
        as_dict=True,
    )

    updated = 0
    for row in rows:
        fle = frappe.db.get_value(
            "Foundations for a Legal Education",
            row.reference_no,
            ["candidate_name", "email_address"],
            as_dict=True,
        )
        if not fle:
            continue
        frappe.db.set_value("FLE Payment Log", row.name, {
            "full_name": fle.candidate_name or "",
            "email":     fle.email_address  or "",
        }, update_modified=False)
        updated += 1

    frappe.db.commit()
    msg = f"Backfilled contact name/email for {updated} FLE Payment Log records."
    frappe.logger().info(msg)
    return msg


@frappe.whitelist()
def run_sync_background(from_date=None, to_date=None):
    """
    Run sync directly (not as a background job) so it works reliably on
    Frappe Cloud where long-queue workers may be unavailable or Redis job
    IDs expire before the poll completes.
    Returns the result string directly — JS treats this as an instant finish.
    """
    result = run_sync(from_date=from_date, to_date=to_date)
    return {"job_id": "direct", "status": "finished", "result": result}


@frappe.whitelist()
def get_sync_status(job_id=None):
    """
    Check the status of a background sync job.
    Returns: { status: "queued"|"started"|"finished"|"failed", result: "..." }
    """
    if not job_id:
        return {"status": "unknown", "result": ""}
    try:
        from rq.job import Job
        from redis import Redis
        conn   = Redis.from_url(frappe.conf.get("redis_queue") or "redis://localhost:11311")
        job    = Job.fetch(job_id, connection=conn)
        raw_status = job.get_status()
        # Normalise JobStatus enum (RQ ≥ 1.10) to plain lowercase string
        status = str(raw_status).lower().split(".")[-1]
        result = ""
        if status == "finished":
            result = str(job.result or "")
        elif status == "failed":
            result = str(job.exc_info or "Sync failed — check Error Log.")
        return {"status": status, "result": result}
    except Exception as e:
        return {"status": "unknown", "result": str(e)}


@frappe.whitelist()
def sync_single_payment_settlement(pr_name):
    """
    Manually synchronize Razorpay settlement information
    for a single Payment Request.
    """
    import requests
    import datetime
    from slcm.api.razorpay_webhook import complete_payment_settlement
    from frappe import _

    pr = frappe.get_doc("SLCM Payment Request", pr_name)

    if not pr.razorpay_payment_id:
        frappe.throw(_("No Razorpay Payment ID found on this Payment Request."))

    if pr.gateway_status != "captured":
        frappe.throw(_("Settlement can only be checked for a captured payment."))

    settings = frappe.get_single("Razorpay Settings")
    auth = (settings.api_key, settings.get_password("api_secret"))

    # 1. Fetch payment
    payment_url = f"{RAZORPAY_BASE}/payments/{pr.razorpay_payment_id}"
    response = requests.get(payment_url, auth=auth, timeout=30)
    
    if not response.ok:
        frappe.throw(_("Failed to fetch payment from Razorpay: {0}").format(response.status_code))

    payment = response.json()

    # 2. Validate payment ownership
    if payment.get("id") != pr.razorpay_payment_id:
        frappe.throw(_("Payment ID mismatch."))

    if payment.get("order_id") != pr.razorpay_order_id:
        frappe.throw(_("Razorpay Order ID mismatch."))

    if payment.get("status") != "captured":
        frappe.throw(_("Payment is not captured. Settlement cannot be confirmed."))

    # 3. Check settlement via recon/combined
    payment_ts = payment.get("created_at")
    dt = datetime.datetime.fromtimestamp(payment_ts)
    
    # We must scan recon/combined for the month the payment was made
    recon_url = f"{RAZORPAY_BASE}/settlements/recon/combined"
    
    skip = 0
    settlement_id = None
    found_item = None
    
    while True:
        recon_resp = requests.get(recon_url, auth=auth, params={"year": dt.year, "month": dt.month, "count": 100, "skip": skip}, timeout=30)
        if not recon_resp.ok:
            break
            
        items = recon_resp.json().get("items", [])
        if not items:
            break
            
        for item in items:
            if item.get("entity_id") == pr.razorpay_payment_id or item.get("payment_id") == pr.razorpay_payment_id:
                settlement_id = item.get("settlement_id")
                found_item = item
                break
                
        if settlement_id:
            break
            
        if len(items) < 100:
            break
        skip += 100


    if not settlement_id:
        return {
            "status": "pending",
            "message": _("This payment has not been included in a Razorpay settlement yet.")
        }

    # 4. Fetch settlement
    settlement_url = f"{RAZORPAY_BASE}/settlements/{settlement_id}"
    settlement_response = requests.get(settlement_url, auth=auth, timeout=30)

    if not settlement_response.ok:
        frappe.throw(_("Failed to fetch settlement from Razorpay: {0}").format(settlement_response.status_code))

    settlement = settlement_response.json()

    # 5. Validate settlement
    if settlement.get("id") != settlement_id:
        frappe.throw(_("Settlement ID mismatch."))

    settlement_status = settlement.get("status")
    
    # Let it fall through to complete_payment_settlement to update DB
    # even if status is created or failed.

    # 6. Complete settlement
    created_at = settlement.get("created_at")
    settlement_date = None
    if created_at:
        try:
            settlement_date = datetime.datetime.utcfromtimestamp(int(created_at)).date()
        except Exception:
            pass

    settlement_payload = {
        "id": settlement_id,
        "utr": settlement.get("utr") or "",
        "status": settlement_status,
        "settlement_date": settlement_date,
    }

    complete_payment_settlement("SLCM Payment Request", pr.name, found_item, settlement_payload)

    msg = _("Settlement {0} synchronized successfully. Status: {1}").format(settlement_id, settlement_status.title())
    return {
        "status": "success",
        "message": msg,
        "settlement_id": settlement_id,
        "utr": settlement.get("utr")
    }

@frappe.whitelist()
def enqueue_bulk_sync():
    """
    Queue the run_sync method in the background for bulk updating
    all past Payment Requests without freezing the browser.
    """
    frappe.enqueue(
        "slcm.api.sync_settlements.run_sync",
        queue="long",
        timeout=3600,
        from_date=None,
        to_date=None
    )
    return True


@frappe.whitelist()
def run_sync(from_date=None, to_date=None, skip_fle=False):
    """
    Sync settlement data using /v1/settlements/recon/combined.
    from_date / to_date limit which settlements are fetched (YYYY-MM-DD strings).
    """
    import json
    from datetime import datetime, timezone

    settings   = frappe.get_single("Razorpay Settings")
    api_key    = settings.api_key
    api_secret = settings.get_password("api_secret")

    if not api_key or not api_secret:
        frappe.throw("API credentials are missing in Razorpay Settings.")

    auth = (api_key, api_secret)

    # ── Step 1: fetch settlements (date-limited to avoid timeout) ─────────────
    settlements = _fetch_all_settlements(auth, from_date=from_date, to_date=to_date)
    if not settlements:
        return "No settlements found from Razorpay."

    setl_by_id = {s["id"]: s for s in settlements if s.get("id")}

    # ── Step 2: build lookup maps ─────────────────────────────
    if not skip_fle:
        fle_rows = frappe.db.sql(
            """
            SELECT name, transaction_id, paid_amount, settlement_id, gateway_response
            FROM `tabFLE Payment Log`
            WHERE payment_status IN ('Authorized', 'Captured') AND (settlement_status IS NULL OR settlement_status != 'processed')
            """,
            as_dict=True,
        )
    else:
        fle_rows = []
        
    pr_rows = frappe.db.sql(
        """
        SELECT name, razorpay_payment_id, transaction_id, amount as paid_amount, settlement_id, gateway_response
        FROM `tabSLCM Payment Request`
        WHERE status = 'Paid' AND (settlement_status IS NULL OR settlement_status != 'processed')
        """,
        as_dict=True,
    )

    by_tid      = {}   # pay_xxx  → (name, target_doctype)
    by_gw_pay   = {}   # pay_xxx  → (name, target_doctype)
    by_order_id = {}   # order_id → (name, target_doctype)

    def process_rows(rows, target_doctype):
        for r in rows:
            # Direct transaction_id or razorpay_payment_id
            tid = (r.get("transaction_id") or "").strip()
            rzp_pid = (r.get("razorpay_payment_id") or "").strip()
            
            pay_id = rzp_pid if rzp_pid.startswith("pay_") else tid
            if pay_id and pay_id.startswith("pay_") and pay_id not in by_tid:
                by_tid[pay_id] = (r.name, target_doctype)

            # Parse gateway_response for pay_xxx and order_id
            gw_pay = gw_order = ""
            if r.gateway_response:
                try:
                    gw = json.loads(r.gateway_response)
                    # Integration Request format: {"razorpay_payment_id": "pay_xxx", "razorpay_order_id": "order_xxx"}
                    gw_pay   = (gw.get("razorpay_payment_id") or "").strip()
                    gw_order = (gw.get("razorpay_order_id")   or "").strip()
                    # Webhook format: payload.payment.entity.id
                    if not gw_pay:
                        gw_pay = (
                            gw.get("payload", {})
                               .get("payment", {})
                               .get("entity", {})
                               .get("id") or ""
                        ).strip()
                    if not gw_order:
                        gw_order = (
                            gw.get("payload", {})
                               .get("payment", {})
                               .get("entity", {})
                               .get("order_id") or ""
                        ).strip()
                except Exception:
                    pass

            if gw_pay and gw_pay.startswith("pay_") and gw_pay not in by_gw_pay:
                by_gw_pay[gw_pay] = (r.name, target_doctype)
            if gw_order and gw_order not in by_order_id:
                by_order_id[gw_order] = (r.name, target_doctype)

    process_rows(fle_rows, "FLE Payment Log")
    process_rows(pr_rows, "SLCM Payment Request")

    # ── Step 3: determine year-months to query recon ──────────────────────────
    year_months = set()
    for s in settlements:
        ts = s.get("created_at")
        if ts:
            try:
                dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                year_months.add((dt.year, dt.month))
            except Exception:
                pass
    year_months = sorted(year_months)

    if not year_months:
        return "Could not determine date range from settlements."

    # ── Step 4: fetch recon items and match to FLE Payment Log ───────────────
    total_updated  = 0
    recon_fetched  = 0
    recon_matched  = 0
    recon_skipped  = 0
    updated_names  = set()   # avoid double-updating the same log row

    def _resolve_log(item):
        """Try all matching strategies; return (log_name, target_doctype, pay_id) or (None, None, '')."""
        pay_id = (
            item.get("entity_id")
            or item.get("payment_id")
            or item.get("razorpay_payment_id")
            or ""
        ).strip()
        order_id = (item.get("order_id") or "").strip()

        if pay_id:
            res = by_tid.get(pay_id) or by_gw_pay.get(pay_id)
            if res:
                return res[0], res[1], pay_id
        if order_id:
            res = by_order_id.get(order_id)
            if res:
                return res[0], res[1], pay_id
        return None, None, pay_id

    for year, month in year_months:
        skip = 0
        while True:
            resp = requests.get(
                f"{RAZORPAY_BASE}/settlements/recon/combined",
                auth=auth,
                params={"year": year, "month": month, "count": RECON_PAGE_SIZE, "skip": skip},
                timeout=60,
            )

            if resp.status_code == 404:
                frappe.logger().warning(
                    "sync_settlements: recon/combined returned 404 — not enabled on this account."
                )
                break

            if not resp.ok:
                frappe.logger().error(
                    f"sync_settlements: recon error {resp.status_code}: {resp.text[:200]}"
                )
                break

            items = resp.json().get("items") or []
            recon_fetched += len(items)

            for item in items:
                entity_type = (item.get("type") or item.get("entity_type") or "").lower()
                if entity_type and entity_type not in ("payment", ""):
                    continue

                log_name, target_doctype, pay_id = _resolve_log(item)

                if not log_name:
                    recon_skipped += 1
                    if pay_id:
                        frappe.logger().debug(
                            f"sync_settlements: no match for pay_id={pay_id}"
                        )
                    continue

                key = (log_name, target_doctype)
                if key in updated_names:
                    continue

                # Settlement metadata
                sid    = item.get("settlement_id") or ""
                s_data = setl_by_id.get(sid) or {}
                utr    = s_data.get("utr") or ""
                status = s_data.get("status") or "processed"

                settlement_date = None
                ts = s_data.get("settlement_time") or s_data.get("created_at")
                if ts:
                    try:
                        settlement_date = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
                    except Exception:
                        pass

                gross_paise  = int(item.get("amount") or 0)
                fee_paise    = int(item.get("fee")    or item.get("fees") or 0)
                tax_paise    = int(item.get("tax")    or 0)
                net_paise    = int(item.get("credit") or 0)

                fields_to_update = {
                    "settlement_id":     sid,
                    "settlement_utr":    utr,
                    "settlement_date":   settlement_date,
                    "settlement_status": status,
                    "gateway_fees":      round(fee_paise / 100, 2),
                    "gateway_tax":       round(tax_paise / 100, 2),
                    "net_settled":       round(net_paise / 100, 2) if net_paise else round((gross_paise - fee_paise - tax_paise) / 100, 2),
                }

                if target_doctype == "SLCM Payment Request":
                    fields_to_update["settlement_amount"] = round(gross_paise / 100, 2)
                    fields_to_update["settlement_response"] = json.dumps(item, indent=4)

                frappe.db.set_value(target_doctype, log_name, fields_to_update, update_modified=False)

                updated_names.add(key)
                total_updated += 1
                recon_matched += 1

            if len(items) < RECON_PAGE_SIZE:
                break
            skip += RECON_PAGE_SIZE

    # ── Step 5: UTR-based fallback ────────────────────────────────────────────
    # For FLE Payment Log rows that already have settlement_utr populated
    # (written by the webhook on settlement.processed), write the settlement_id
    # and other metadata from the settlements list.
    # This handles the case where recon/combined has no per-payment entity_ids.
    fallback_updated = 0
    utr_to_settlement = {
        s.get("utr"): s for s in settlements
        if s.get("utr") and s.get("id")
    }

    if utr_to_settlement:
        utr_rows = frappe.db.sql(
            """
            SELECT name, settlement_utr
            FROM `tabFLE Payment Log`
            WHERE settlement_utr IS NOT NULL
              AND settlement_utr != ''
              AND (settlement_id IS NULL OR settlement_id = '')
            """,
            as_dict=True,
        )
        pr_utr_rows = frappe.db.sql(
            """
            SELECT name, settlement_utr
            FROM `tabSLCM Payment Request`
            WHERE settlement_utr IS NOT NULL
              AND settlement_utr != ''
              AND (settlement_id IS NULL OR settlement_id = '')
              AND status = 'Paid'
            """,
            as_dict=True,
        )
        all_utr_rows = [(r.name, r.settlement_utr, "FLE Payment Log") for r in utr_rows] + \
                       [(r.name, r.settlement_utr, "SLCM Payment Request") for r in pr_utr_rows]

        for row_name, row_utr, t_doctype in all_utr_rows:
            key = (row_name, t_doctype)
            if key in updated_names:
                continue
            s = utr_to_settlement.get(row_utr)
            if not s:
                continue

            sid    = s.get("id") or ""
            status = s.get("status") or "processed"
            ts     = s.get("settlement_time") or s.get("created_at")
            settlement_date = None
            if ts:
                try:
                    settlement_date = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
                except Exception:
                    pass

            fields_to_update = {
                "settlement_id":     sid,
                "settlement_date":   settlement_date,
            }

            if t_doctype == "SLCM Payment Request":
                fields_to_update["gateway_settlement_status"] = status
                if status == "processed":
                    fields_to_update["settlement_status"] = "Settled"
                elif status == "created":
                    fields_to_update["settlement_status"] = "Processing"
                elif status == "failed":
                    fields_to_update["settlement_status"] = "Failed"
                else:
                    fields_to_update["settlement_status"] = "Pending"
            else:
                fields_to_update["settlement_status"] = status

            frappe.db.set_value(t_doctype, row_name, fields_to_update, update_modified=False)

            updated_names.add(key)
            fallback_updated += 1

    frappe.db.commit()

    total_all = total_updated + fallback_updated
    msg = (
        f"Sync complete. "
        f"Scanned {recon_fetched} recon items across {len(year_months)} month(s). "
        f"Matched {recon_matched} via payment ID, "
        f"{fallback_updated} via UTR fallback. "
        f"Total updated: {total_all} FLE Payment Log record(s). "
        + (f"Unmatched recon items: {recon_skipped}." if recon_skipped else "All items matched.")
    )
    frappe.logger().info(msg)
    return msg


def _fetch_all_settlements(auth, from_date=None, to_date=None):
    """Paginate through /v1/settlements and return all items."""
    from datetime import datetime, time as dtime, timezone

    def _to_unix(date_str, end_of_day=False):
        if not date_str:
            return None
        try:
            d = datetime.strptime(str(date_str), "%Y-%m-%d")
            t = dtime(23, 59, 59) if end_of_day else dtime(0, 0, 0)
            return int(datetime.combine(d.date(), t).replace(tzinfo=timezone.utc).timestamp())
        except Exception:
            return None

    from_ts = _to_unix(from_date, end_of_day=False)
    to_ts   = _to_unix(to_date,   end_of_day=True)

    settlements = []
    skip        = 0

    while True:
        params = {"count": PAGE_SIZE, "skip": skip}
        if from_ts:
            params["from"] = from_ts
        if to_ts:
            params["to"] = to_ts

        resp = requests.get(
            f"{RAZORPAY_BASE}/settlements",
            auth=auth,
            params=params,
            timeout=30,
        )
        if not resp.ok:
            frappe.log_error(
                f"Razorpay /settlements error {resp.status_code}: {resp.text[:300]}",
                "sync_settlements",
            )
            frappe.throw(
                f"Razorpay API error {resp.status_code}: {resp.text[:300]}"
            )

        items = resp.json().get("items", [])
        settlements.extend(items)

        if len(items) < PAGE_SIZE:
            break
        skip += PAGE_SIZE

    return settlements


def daily_sync_settlements():
    """
    Daily background cron job to sync settlements for both Payment Requests and FLE Payment Logs.
    Fetches settlements from the last 5 days to safely account for bank holidays and weekends.
    """
    from datetime import datetime, timedelta
    
    today = datetime.now()
    five_days_ago = today - timedelta(days=5)
    
    from_date_str = five_days_ago.strftime("%Y-%m-%d")
    to_date_str = today.strftime("%Y-%m-%d")
    
    run_sync(from_date=from_date_str, to_date=to_date_str, skip_fle=False)

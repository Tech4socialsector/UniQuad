# Developer Manual: Payment to Custom Success Page Flow

This manual documents the exact architectural flow and code modifications required to intercept a standard Frappe WebForm payment (using Razorpay) and redirect it flawlessly to a custom Success Page (`/fle-success-page`) with all receipt data natively populated for Guest users.

## The Architecture Problem Space
By default, Frappe's `PaymentWebForm` intercepts payment requests, hands them off to the Razorpay Settings controller, and drops all original URL parameters upon returning from the gateway, resolving rigidly to a generic `/payment-success` fallback. To bypass this, we must enforce data preservation across three key layers:
1. **The Core Python Override** (Building the URL)
2. **The Gateway Javascript** (Unwrapping the Return)
3. **The Doctype Controller & Frontend** (Fetching the Data securely as a Guest)


## Layer 1: Modifying the Payment URL Builder
**File:** `apps/payments/payments/overrides/payment_webform.py`

This file builds the initial `redirect_to` payload sent to Razorpay before the user leaves your site. By default, it ignores the document `name`. We modify `get_payment_gateway_url` to forcefully bake the `name` into the `redirect_to` property so Razorpay is carrying the instruction in its payload.

```python
# Around Line 39
def get_payment_gateway_url(self, doc):
    # ... setup code ...
    redirect_url = frappe.utils.get_url(self.success_url or self.route)
    
    # [NEW LOGIC] Assert the document name directly into the Success URL string
    if "?" in redirect_url:
        if "name=" not in redirect_url:
            redirect_url += f"&name={doc.name}"
    else:
        redirect_url += f"?name={doc.name}"

    payment_details = {
        # ... other details ...
        "redirect_to": redirect_url, # Now strictly contains ?name=FLE-XXXX
    }
```


## Layer 2: Unwrapping the Razorpay Return
**File:** `apps/payments/payments/templates/includes/razorpay_checkout.js`

When Razorpay validates the payment and pings Frappe, Frappe's backend creates a nested URL structure like `payment-success?doctype=xyz&redirect_to=/fle-success-page?name=abc`. We modify the javascript callback `make_payment_log` to prioritize and extract our custom `redirect_to` immediately.

```javascript
// Around Line 45 Inside razorpay.make_payment_log
callback: function (r) {
    if (r.message && (r.message.status == 200 || [401, 400, 500].indexOf(r.message.status) > -1)) {
        let final_url = r.message.redirect_to;
        
        // [NEW LOGIC] If Frappe nested our custom URL as a query parameter, unwrap it
        let url_obj = new URL(final_url, window.location.origin);
        if (url_obj.searchParams.has('redirect_to')) {
            final_url = url_obj.searchParams.get('redirect_to');
        }
        
        // Redirect directly to /fle-success-page?name=FLE-XXX
        window.location.href = final_url; 
    }
}
```
> [!WARNING]
> Because this file is a Jinja Template rendered as Javascript (`{{ api_key }}`), be incredibly careful to use `// prettier-ignore` or avoid using Formatter tools in your IDE. Adding spaces inside Jinja brackets (`{ { api_key } }`) will throw severe Javascript Syntax Errors on the checkout page.


## Layer 3: Backend Data Fulfillment for Guests
**File:** `apps/slcm/slcm/slcm/doctype/foundations_for_a_legal_education/foundations_for_a_legal_education.py`

Because Frappe prevents unauthenticated (Guest) users from using the generic `frappe.client.get` API, we must create a dedicated `@frappe.whitelist(allow_guest=True)` function that securely returns only the non-sensitive receipt data.

```python
@frappe.whitelist(allow_guest=True)
def get_receipt_details(doc_name=None):
    try:
        # 1. Fallback Logic: If doc_name is stripped by a gateway failure, fetch their latest record
        if not doc_name:
            filters = {"payment_status": "Paid"}
            if frappe.session.user != "Guest":
                filters["email_address"] = frappe.session.user
            
            latest_docs = frappe.get_all(
                "Foundations for a Legal Education", filters=filters, order_by="modified desc", limit=1
            )
            if not latest_docs: return None
            doc_name = latest_docs[0].name
            
        # 2. Return strict subset of public receipt data
        doc = frappe.get_doc("Foundations for a Legal Education", doc_name)
        return {
            "candidate_name": doc.candidate_name,
            "email_address": doc.email_address,
            "name": doc.name,
            "amount": doc.amount,
            "modified": doc.modified,
            "payment_status": doc.payment_status or "Paid"
        }
    except Exception:
        return None
```


## Layer 4: Frontend Success Page & Fallbacks
**File:** `apps/slcm/slcm/slcm/www/fle_success_page.html`

Finally, the success page reads the unwrapped URL parameters. If it somehow still fails to get the URL parameters, it acts defensively by reading from `localStorage` (which we populated back on the initial form right before clicking checkout).

```javascript
// Extract from fle_success_page.html
frappe.ready(function () {
    let urlParams = new URLSearchParams(window.location.search);
    let receipt_id = urlParams.get('name');

    // FALLBACK 1: Check localStorage if URL Params were stripped
    if (!receipt_id) {
        receipt_id = localStorage.getItem('recent_fle_payment_doc');
        if (receipt_id) localStorage.removeItem('recent_fle_payment_doc');
    }

    // Call our Whitelisted Guest API (Handles FALLBACK 2: Latest Session Record internally)
    frappe.call({
        method: "slcm.slcm.doctype...get_receipt_details",
        args: { doc_name: receipt_id },
        callback: function (r) {
            // ... Populate DOM Elements based on r.message ...
        }
    });
});
```

---

## Testing Verification
If future changes are made, run this exact flow to verify it remains unbroken:
1. Ensure `bench build --app payments` has been run if `razorpay_checkout.js` is altered.
2. Fill out the application form from an Incognito (Guest) browser.
3. Submit and traverse the Razorpay Web Checkout.
4. Verify the user automatically lands on `/fle-success-page`, the URL contains `?name=FLE-...`, and the HTML Table populates cleanly.

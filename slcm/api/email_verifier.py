import frappe
import re
import dns.resolver
from frappe import _
from frappe.rate_limiter import rate_limit

@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60 * 60)
def verify_email(email):
    """
    Verifies an email address using DNS MX record validation.
    Returns status: domain_valid, domain_invalid, invalid_format, or verification_error.
    """
    if not email:
        return {"status": "invalid_format"}

    # Step 1: Validate email format using regex
    # Standard email regex: name@domain.tld
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        return {"status": "invalid_format"}

    # Step 2: Extract domain
    try:
        domain = email.split('@')[1]
    except IndexError:
        return {"status": "invalid_format"}

    # Step 3: Check MX records using dnspython
    try:
        # We use a 10 second timeout for the DNS resolution
        resolver = dns.resolver.Resolver()
        resolver.timeout = 10
        resolver.lifetime = 10
        
        mx_records = resolver.resolve(domain, 'MX')
        
        if mx_records:
            return {"status": "domain_valid"}
        else:
            return {"status": "domain_invalid"}

    except dns.resolver.NXDOMAIN:
        # Domain does not exist
        return {"status": "domain_invalid"}
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        # Domain exists but no MX records found (no mail server)
        return {"status": "domain_invalid"}
    except dns.exception.Timeout:
        # Connection timeout - consider it a verification error
        return {"status": "verification_error"}
    except Exception as e:
        # Log unexpected errors for debugging
        frappe.log_error(f"Email Verification DNS Error for {domain}: {str(e)}", "Email Verification Error")
        return {"status": "verification_error"}

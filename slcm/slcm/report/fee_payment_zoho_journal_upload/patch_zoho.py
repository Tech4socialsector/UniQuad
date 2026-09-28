import re

with open('fee_payment_zoho_journal_upload.py', 'r') as f:
    content = f.read()

new_logic = '''def get_razorpay_settlements(filters):
    from datetime import datetime, timezone
    
    start_ts = None
    end_ts = None
    if filters.get(" from_settlement_date\):

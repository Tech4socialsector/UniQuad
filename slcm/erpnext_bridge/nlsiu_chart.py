"""NLSIU Company with a Chart of Accounts mirroring the audited Financial Statements (FY 2025-26, K.P. Rao & Co.).

Run once per site:  bench --site <site> execute slcm.erpnext_bridge.nlsiu_chart.setup

Idempotent: if the Company already has accounts, the chart is left alone and only blank defaults are filled.
Every leaf maps to one line of Schedules 2-24, so the audited 31-03-2026 balances can be loaded as an
opening Journal Entry line by line. Accounts marked "ERPNext" are not in the statements but are needed
by ERPNext itself (opening entries, rounding, asset purchases).
"""

import re

import frappe

COMPANY = "National Law School of India University"
ABBR = "NLSIU"


def _leaves(start, names, account_type=None):
	extra = {"account_type": account_type} if account_type else {}
	return {name: {"account_number": str(start + i), **extra} for i, name in enumerate(names)}


TANGIBLE = (
	"Computers & Peripherals",
	"Office Equipment",
	"Library Books",
	"Furniture, Fixtures & Fittings",
	"Sports Equipment",
	"Vehicles",
	"Buildings",
	"Electrical Appliances",
)

CHART = {
	"Application of Funds": {
		"root_type": "Asset",
		"account_number": "1000",
		# Sch 8
		"Fixed Assets": {
			"account_number": "1100",
			"Tangible Assets": {"account_number": "1110", **_leaves(1111, TANGIBLE, "Fixed Asset")},
			"Accumulated Depreciation": {
				"account_number": "1120",
				**_leaves(1121, [f"Accumulated Depreciation - {n}" for n in TANGIBLE], "Accumulated Depreciation"),
			},
			"Intangible Assets": {
				"account_number": "1130",
				"Intangible Assets - Software": {"account_number": "1131", "account_type": "Fixed Asset"},
				"Accumulated Amortisation - Intangible Assets": {
					"account_number": "1132",
					"account_type": "Accumulated Depreciation",
				},
			},
			"Capital Work-in-Progress": {
				"account_number": "1140",
				"Capital Work-in-Progress - Assets": {"account_number": "1141", "account_type": "Capital Work in Progress"},
			},
		},
		# Sch 9
		"Long-Term Investments": {
			"account_number": "1200",
			**_leaves(
				1201,
				(
					"Long-Term Deposits - Scheduled Banks",
					"Long-Term Deposits - Financial Institutions/Commercial Banks",
					"Accrued Interest on Long-Term Deposits",
				),
			),
		},
		# Sch 10
		"Other Non-Current Assets": {
			"account_number": "1300",
			**_leaves(1301, ("Capital Advances", "Security Deposit")),
		},
		# Sch 11
		"Current Assets": {
			"account_number": "1400",
			"Sundry Debtors": {"account_number": "1401", "account_type": "Receivable"},
			"Bank Accounts": {
				"account_number": "1410",
				**_leaves(
					1411,
					(
						"Savings Accounts - Scheduled Banks",
						"Savings Accounts - Commercial Banks/Financial Institutions",
					),
					"Bank",
				),
			},
			"Cash In Hand": {
				"account_number": "1420",
				"Cash": {"account_number": "1421", "account_type": "Cash"},
			},
			# ERPNext: online fees until Razorpay / Easebuzz settle them into the bank.
			"Payment Gateway Clearing": {"account_number": "1430"},
		},
		# Sch 12
		"Short-Term Investments": {
			"account_number": "1500",
			**_leaves(
				1501,
				(
					"Short-Term Deposits - Scheduled Banks",
					"Short-Term Deposits - Financial Institutions/Commercial Banks",
					"Accrued Interest on Short-Term Deposits",
				),
			),
		},
		# Sch 13
		"Short-Term Loans, Advances & Deposits": {
			"account_number": "1600",
			**_leaves(
				1601,
				(
					"Advances to Employees (Non-interest bearing)",
					"Loans to Employees (Interest bearing)",
					"Advance to Suppliers",
					"Other Advances",
					"Student Advances",
					"Accrued Interest on Savings Bank A/c",
					"Prepaid Expenses",
				),
			),
			"Other Receivables": {
				"account_number": "1610",
				**_leaves(1611, ("Claims Receivable", "Rent Receivable", "TDS Receivable")),
				"Student Fees Receivable": {"account_number": "1614", "account_type": "Receivable"},
				**_leaves(1615, ("Receivable from LIC", "Projects, Schemes and Grants Receivable")),
			},
		},
		# ERPNext: balancing account for opening entries; must be zero once the opening is complete.
		"Temporary Accounts": {
			"account_number": "1900",
			"Temporary Opening": {"account_number": "1901", "account_type": "Temporary"},
		},
	},
	"Liabilities": {
		"root_type": "Liability",
		"account_number": "2000",
		"Non-Current Liabilities": {
			"account_number": "2100",
			# Sch 5
			"Provision for Employee Benefits": {
				"account_number": "2110",
				**_leaves(2111, ("Salary Equalisation Fund", "Provision for Gratuity - Non-Current")),
			},
			# Sch 6
			"Other Non-Current Liabilities": {
				"account_number": "2120",
				**_leaves(2121, ("Grants-in-aid for Asset Creation", "Rental Deposit", "Library Deposit")),
			},
		},
		# Sch 7 (A)
		"Current Liabilities": {
			"account_number": "2200",
			**_leaves(2201, ("Deposits from Students", "Deposits from Creditors")),
			"Sundry Creditors": {"account_number": "2203", "account_type": "Payable"},
			**_leaves(
				2204,
				(
					"Other Payables to Employees",
					"Unutilised Project Receipts & Grants",
					"Unearned Revenue from External Training Programs",
					"Fees Received in Advance",
					"Deferred Fee",
					"Corporate Credit Card Payable",
				),
			),
			"Statutory Liabilities Payable": {"account_number": "2210", "account_type": "Tax"},
			**_leaves(2211, ("Other Student Payables", "Other Current Liabilities")),
			# ERPNext: clearing account for assets received on a Purchase Receipt before the invoice.
			"Asset Received But Not Billed": {"account_number": "2290", "account_type": "Asset Received But Not Billed"},
		},
		# Sch 7 (B)
		"Provisions": {
			"account_number": "2300",
			**_leaves(2301, ("Provision for Gratuity - Current", "Provision for Earned Leave", "Expenses Payable")),
		},
	},
	"Funds": {
		"root_type": "Equity",
		"account_number": "3000",
		# Sch 2
		"General Fund": {"account_number": "3100", "School Fund": {"account_number": "3101"}},
		# Sch 3
		"Designated Funds": {
			"account_number": "3200",
			**_leaves(
				3201,
				("University Development Fund", "Employee Welfare Fund", "Research Centre Funds", "Scholarship Fund"),
			),
		},
		# Sch 4
		"Restricted Funds": {
			"account_number": "3300",
			**_leaves(
				3301,
				(
					"Endowment Fund - Chairs",
					"Endowment for Scholarship",
					"Endowment for Medals and Prizes",
					"Endowment for Moot Courts & Law Reforms",
					"Endowment for Library Development",
					"NLSIU Alumni Education Aid Endowment",
					"Student Activity Fund",
					"Auditorium Construction Fund",
					"FCRA Fund",
					"COVID Fund",
					"Inclusion & Expansion Fund",
					"QAMRA Fund",
				),
			),
		},
	},
	"Income": {
		"root_type": "Income",
		"account_number": "4000",
		# Sch 14
		"Academic Receipts": {
			"account_number": "4100",
			"Academic Fees": {"account_number": "4110", **_leaves(4111, ("Tuition Fee", "Admission/Registration Fee"))},
			"Examinations": {
				"account_number": "4120",
				**_leaves(4121, ("Examination Fee", "Mark Sheet, Certificate Fee")),
			},
			"Other Fees": {
				"account_number": "4130",
				**_leaves(
					4131,
					("Fine/Miscellaneous Fee", "Convocation Fee", "Hostel and Off Campus Accommodation Fees"),
				),
			},
			"Sale of Publications": {
				"account_number": "4140",
				**_leaves(4141, ("Sale of Syllabus and Question Paper", "Sale of Other Publications")),
			},
			# Refunds reduce Academic Receipts instead of showing as an expense.
			"Fee Refunds": {"account_number": "4150"},
		},
		# Sch 15
		"Other Operating Income": {
			"account_number": "4200",
			**_leaves(
				4201,
				(
					"Income from Research Projects",
					"Income from Training Programmes",
					"Income from Consultancy",
					"Government Grants",
					"Donations & Other Grants",
					"Profit on Sale of Assets",
					"Rental Income",
					"Charges and Recoveries",
				),
			),
		},
		# Sch 16
		"Income from Investments": {
			"account_number": "4300",
			**_leaves(
				4301,
				(
					"Interest on Deposits - Scheduled Banks",
					"Interest on Deposits - Commercial Banks/Financial Institutions",
				),
			),
		},
		# Sch 17
		"Other Incomes": {
			"account_number": "4400",
			**_leaves(
				4401,
				(
					"Interest on Savings Accounts",
					"Other Interest Income",
					"Interest on Staff Loans",
					"Miscellaneous Income",
				),
			),
		},
	},
	"Expenditure": {
		"root_type": "Expense",
		"account_number": "5000",
		# Sch 18
		"Staff Payments & Benefits": {
			"account_number": "5100",
			"Salaries and Wages": {
				"account_number": "5110",
				**_leaves(5111, ("Salaries - Teaching Staff", "Salaries - Non-teaching Staff")),
			},
			**_leaves(
				5121,
				(
					"Children Education Allowance",
					"Medical Reimbursement",
					"Contribution to Provident Fund",
					"Retirement & Terminal Benefits",
					"Staff Welfare Expenses",
				),
			),
		},
		# Sch 19
		"Academic Expenses": {
			"account_number": "5200",
			**_leaves(
				5201,
				(
					"Convocation Expenses",
					"Examination Expenses",
					"Honorarium to Visiting Faculty & Resource Persons",
					"Membership Fees to Professional Bodies & Associations",
					"Newspapers, Magazines & Journals",
					"Publications",
					"Research, Seminar and Workshop Expenses",
					"Stipends and Scholarship",
					"Student Clubs & Events",
					"Student Welfare Expenses",
				),
			),
		},
		# Sch 20: one ledger; individual projects are tracked with ERPNext Projects, not separate accounts.
		"Expenditure Incurred on Research Projects": {
			"account_number": "5300",
			"Research Project Expenditure": {"account_number": "5301"},
		},
		# Sch 21
		"Administrative & General Expenses": {
			"account_number": "5400",
			**_leaves(
				5401,
				(
					"Advertisement and Publicity",
					"Auditors Remuneration & Reimbursements",
					"Electricity and Power",
					"Information Technology (IT) Services and Maintenance",
					"Facility Management Services",
					"Printing, Stationery & Photocopy",
					"Postage & Courier",
					"Telephone Charges",
					"Water Charges",
					"Travel and Conveyance",
					"Meeting Expenses",
					"Rent",
					"Legal & Professional Charges",
					"Cafeteria",
					"Rates and Taxes",
					"Transportation Expenses",
				),
			),
		},
		# Sch 22
		"Repairs & Maintenance": {
			"account_number": "5500",
			**_leaves(5501, ("Repairs & Maintenance - Building", "Repairs & Maintenance - Others")),
		},
		# Sch 23
		"Finance Costs": {
			"account_number": "5600",
			**_leaves(
				5601,
				(
					"Forex Loss/Gain",
					"Interest, Arrears, Penalty on Tax Remittances",
					"Bank Charges",
					"GST on Gateway Charges",
				),
			),
		},
		# Sch 8
		"Depreciation": {
			"account_number": "5700",
			"Depreciation Expense": {"account_number": "5701", "account_type": "Depreciation"},
		},
		# Sch 24
		"Other Expenses": {
			"account_number": "5800",
			**_leaves(5801, ("Write-off/Loss on Sale of Assets", "Miscellaneous Expenses")),
			# ERPNext: rounding differences on invoices and payments.
			"Round Off": {"account_number": "5890", "account_type": "Round Off"},
		},
	},
}

# Company default -> account number. Only blank defaults are filled.
DEFAULTS = {
	"default_receivable_account": "1401",
	"default_payable_account": "2203",
	"default_bank_account": "1411",
	"default_cash_account": "1421",
	"round_off_account": "5890",
	"write_off_account": "5801",
	"exchange_gain_loss_account": "5601",
	"disposal_account": "5801",
	"depreciation_expense_account": "5701",
	"capital_work_in_progress_account": "1141",
	"asset_received_but_not_billed": "2290",
	"default_income_account": "4404",
	"default_expense_account": "5802",
}

ADDED_LEAVES = (
	# (number, name, parent number, account type) - leaves added after the chart was first created
	("1430", "Payment Gateway Clearing", "1400", None),
	("4150", "Fee Refunds", "4100", None),
	("5604", "GST on Gateway Charges", "5600", None),
)

# Account number -> SLCM names posting there (Fee Components, 'PACE <fee type>', 'FLE Course Fee').
# A component matches an account name only through its Ledger ('Tuition Fee' has none, so it matches 4111 as is).
SLCM_MAP = {
	"4111": (
		"Tuition and Facilities Fee",
		"Program Fee",
		"Reregistration Tuition Fee",
		"Course Work Fee",
		"Annual Fee",
		"Continuation / Extension Fee",
		"Deferral Fee",
		"Lab Fee",
		"Library Fee",
		"Sports Fee",
		"Development Fee",
	),
	"4112": ("Admission Fee", "Registration Fee", "Re-admission Fee", "Application Fee"),
	"4121": ("Examination Fee", "Final Presentation Fee", "Re-submission of thesis", "Re Exam Fee", "Improvement Exam Fee"),
	"4122": ("Provisional Transcript", "Duplicate ID Card", "Transcript Fee"),
	"4131": ("Fines - Regular Programmes", "Fine - Mobile Phone, Other Disciplinary Things"),
	"4132": ("Convocation Fee",),
	"4133": (
		"Hostel Residential and Mess Charges",
		"Hostel Fee",
		"Mess Fee",
		"Mess Charges - Others",
		"Laundry Charges",
		"Electric Appliance Usage Charges",
	),
	"4202": ("PACE Course Fee", "PACE Application Fee", "FLE Course Fee"),
	"4208": ("Transport Fee", "Postage Charges"),
	# Sch 4A: student activity fees are credited to the restricted fund, not income.
	"3307": ("Student Activity Fee",),
	"2201": ("Caution Deposit", "Student Refundable Deposit"),
}

# Company "SLCM Fees" tab -> account number.
SLCM_ACCOUNTS = {
	"slcm_default_fee_income_account": "4131",
	"slcm_unallocated_fee_account": "2207",
	"slcm_output_gst_account": "2210",
	"slcm_fee_refund_account": "4150",
	"slcm_gateway_charges_account": "5603",
	"slcm_gateway_gst_account": "5604",
	"slcm_stipend_account": "5208",
}
POSTING_FROM = "2026-04-01"  # the day after the audited balance sheet the opening entry is built from

FISCAL_YEARS = (("2025-2026", "2025-04-01", "2026-03-31"), ("2026-2027", "2026-04-01", "2027-03-31"))


def setup():
	company = _ensure_company()
	if not frappe.db.exists("Account", {"company": company}):
		from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import create_charts

		frappe.local.flags.ignore_root_company_validation = True
		create_charts(company, custom_chart=CHART)
	for number, name, parent, account_type in ADDED_LEAVES:
		_ensure_leaf(company, number, name, parent, account_type)
	_set_defaults(company)
	_ensure_fiscal_years(company)
	frappe.db.commit()
	return company


def connect_slcm(enable=False):
	"""Point the SLCM fee bridge at this Company: fee mapping, payment modes, university banks, SLCM Fees tab.

	Run:  bench --site <site> execute slcm.erpnext_bridge.nlsiu_chart.connect_slcm --kwargs '{"enable": 1}'
	With enable, posting moves here from whichever company had it; Journal Entries already posted stay there.
	"""
	from slcm.erpnext_bridge.install import setup_erpnext_side
	from slcm.erpnext_bridge.setup_accounts import _mode_of_payment, _slcm_modes, _university_bank_accounts

	setup_erpnext_side()  # custom fields, incl. Account "SLCM Fee Components"
	company = setup()

	for number, names in SLCM_MAP.items():
		account = _by_number(company, number)
		listed = frappe.db.get_value("Account", account, "slcm_fee_components") or ""
		lines = [line.strip() for line in listed.splitlines() if line.strip()]
		missing = [name for name in names if name.lower() not in {line.lower() for line in lines}]
		if missing:
			frappe.db.set_value("Account", account, "slcm_fee_components", "\n".join(lines + missing))

	bank_ledgers = [_bank_account(company, label) for label in _university_bank_accounts()]
	if bank_ledgers and frappe.db.get_value("Company", company, "default_bank_account") == _by_number(company, "1411"):
		# Razorpay / Easebuzz settle into the default bank: use the first university bank, not the placeholder.
		frappe.db.set_value("Company", company, "default_bank_account", bank_ledgers[0])
	default_bank = frappe.db.get_value("Company", company, "default_bank_account")
	clearing = _by_number(company, "1430")
	for mode in _slcm_modes():
		if mode == "Cash":
			_mode_of_payment(company, mode, "Cash", _by_number(company, "1421"))
		elif mode in ("Online Payment", "Online"):
			_mode_of_payment(company, mode, "General", clearing)
		else:
			_mode_of_payment(company, mode, "Bank", default_bank)

	current = frappe.db.get_value("Company", company, [*SLCM_ACCOUNTS, "slcm_posting_from_date"], as_dict=True)
	updates = {f: _by_number(company, n) for f, n in SLCM_ACCOUNTS.items() if not current.get(f)}
	if not current.slcm_posting_from_date:
		updates["slcm_posting_from_date"] = POSTING_FROM
	updates["slcm_submit_journal_entries"] = 1
	frappe.db.set_value("Company", company, updates)

	if enable:
		for other in frappe.get_all("Company", {"slcm_enable_fee_posting": 1, "name": ("!=", company)}, pluck="name"):
			frappe.db.set_value("Company", other, "slcm_enable_fee_posting", 0)
		frappe.db.set_value("Company", company, "slcm_enable_fee_posting", 1)
		from slcm.erpnext_bridge.company import validate_company

		validate_company(frappe.get_doc("Company", company))
	frappe.clear_document_cache("Company", company)
	frappe.db.commit()
	return company


def _by_number(company, number):
	return frappe.db.get_value("Account", {"company": company, "account_number": number}, "name")


def _ensure_leaf(company, number, name, parent_number, account_type=None):
	if _by_number(company, number):
		return
	frappe.get_doc(
		{
			"doctype": "Account",
			"company": company,
			"account_name": name,
			"account_number": number,
			"parent_account": _by_number(company, parent_number),
			"account_type": account_type or "",
		}
	).insert(ignore_permissions=True)


def _bank_account(company, label):
	"""Numbered bank ledger under 1410 plus a company Bank Account matched by SLCM's account number.

	Bank Account names are global ('<name> - <bank>'), so the company abbreviation keeps them apart from TFSS's."""
	number = re.findall(r"\d{6,}", label)[-1]
	account_name = re.sub(r"\s*\d{6,}\s*$", "", label)
	found = frappe.db.get_value(
		"Bank Account", {"bank_account_no": number, "company": company, "is_company_account": 1}, "account"
	)
	if found:
		return found
	ledger = frappe.db.get_value("Account", {"company": company, "account_name": label, "is_group": 0}, "name")
	if not ledger:
		used = frappe.get_all(
			"Account", {"company": company, "account_number": ("like", "141%")}, pluck="account_number"
		)
		ledger = frappe.get_doc(
			{
				"doctype": "Account",
				"company": company,
				"account_name": label,
				"account_number": str(max([1412, *map(int, used)]) + 1),
				"parent_account": _by_number(company, "1410"),
				"account_type": "Bank",
			}
		).insert(ignore_permissions=True).name
	bank = label.split(" Bank")[0].strip() + " Bank"
	if not frappe.db.exists("Bank", bank):
		frappe.get_doc({"doctype": "Bank", "bank_name": bank}).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Bank Account",
			"account_name": f"{account_name} ({ABBR})",
			"bank": bank,
			"account": ledger,
			"is_company_account": 1,
			"company": company,
			"bank_account_no": number,
		}
	).insert(ignore_permissions=True)
	return ledger


def _ensure_company():
	if frappe.db.exists("Company", COMPANY):
		return COMPANY
	# Skip ERPNext's standard India chart: on_update would otherwise create it before ours.
	frappe.local.flags.ignore_chart_of_accounts = True
	try:
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": COMPANY,
				"abbr": ABBR,
				"country": "India",
				"default_currency": "INR",
				"create_chart_of_accounts_based_on": "Standard Template",
			}
		).insert(ignore_permissions=True)
	finally:
		frappe.local.flags.ignore_chart_of_accounts = False
	return COMPANY


def _set_defaults(company):
	current = frappe.db.get_value("Company", company, list(DEFAULTS), as_dict=True)
	updates = {}
	for field, number in DEFAULTS.items():
		if current.get(field):
			continue
		account = frappe.db.get_value("Account", {"company": company, "account_number": number}, "name")
		if account:
			updates[field] = account
	if updates:
		frappe.db.set_value("Company", company, updates)
	frappe.clear_document_cache("Company", company)


def _ensure_fiscal_years(company):
	# FY 2025-26 is needed to post the opening balances as on 31-03-2026. New years are scoped to this
	# Company, so they cannot overlap a company-wide year already on the site.
	for name, start, end in FISCAL_YEARS:
		if not frappe.db.exists("Fiscal Year", {"year_start_date": start, "year_end_date": end}):
			frappe.get_doc(
				{
					"doctype": "Fiscal Year",
					"year": name,
					"year_start_date": start,
					"year_end_date": end,
					"companies": [{"company": company}],
				}
			).insert(ignore_permissions=True)

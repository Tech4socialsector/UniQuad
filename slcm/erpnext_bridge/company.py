"""The "SLCM Fee Accounting" section on ERPNext's Company form: validation and its buttons."""

import frappe
from frappe import _

from slcm.erpnext_bridge import erpnext_installed
from slcm.erpnext_bridge import config as conf
from slcm.erpnext_bridge.config import ACCOUNT_FIELDS

MANAGERS = ("System Manager", "Accounts Manager")


def _link(doctype, name):
	"""A clickable record in a message."""
	from frappe.utils import get_link_to_form

	return get_link_to_form(doctype, name) if name else "-"


def _fee_link(name):
	"""An SLCM fee name, linked when it is a Fee Component record."""
	return _link("Fee Component", name) if frappe.db.exists("Fee Component", name) else frappe.bold(name)
# Fee receipts are credited: income, deposits held (liability) or a fund (equity). Never an asset or expense.
FEE_ROOT_TYPES = ("Income", "Liability", "Equity")


def validate_company(doc, method=None):
	"""Company.validate (doc_event). Only acts when the SLCM section is in use."""
	if not doc.get("slcm_enable_fee_posting"):
		return
	if not doc.get("slcm_posting_from_date"):
		frappe.throw(_("SLCM Fee Accounting: set 'Post SLCM Fees Dated On/After'."))
	other = frappe.db.get_value(
		"Company", {"slcm_enable_fee_posting": 1, "name": ("!=", doc.name)}, "name"
	)
	if other:
		frappe.throw(
			_("SLCM fee posting is already enabled for Company {0}. SLCM fees can post to one company only.").format(
				_link("Company", other)
			)
		)
	for fieldname in ACCOUNT_FIELDS:
		if doc.get(fieldname):
			_validate_account(doc, doc.get(fieldname), doc.meta.get_label(fieldname))
	unallocated = doc.get("slcm_unallocated_fee_account")
	if unallocated and frappe.db.get_value("Account", unallocated, "root_type") != "Liability":
		frappe.throw(
			_(
				"{0}: Account {1} must be a Liability account - it holds money owed to students (advances and "
				"excess) until it is applied to a due or refunded."
			).format(doc.meta.get_label("slcm_unallocated_fee_account"), _link("Account", unallocated))
		)


def _validate_account(company, account, label):
	acc = frappe.db.get_value("Account", account, ["company", "is_group", "account_type", "disabled"], as_dict=True)
	if not acc:
		frappe.throw(_("{0}: Account {1} does not exist").format(label, _link("Account", account)))
	if acc.company != company.name:
		frappe.throw(_("{0}: Account {1} does not belong to Company {2}").format(label, _link("Account", account), _link("Company", company.name)))
	if acc.is_group:
		frappe.throw(_("{0}: Account {1} is a group account").format(label, _link("Account", account)))
	if acc.disabled:
		frappe.throw(_("{0}: Account {1} is disabled").format(label, _link("Account", account)))
	# Receivable / Payable ledgers need a Party on every Journal Entry row; the bridge posts without parties.
	if acc.account_type in ("Receivable", "Payable"):
		frappe.throw(_("{0}: Account {1} is a {2} account. Use a non-party ledger.").format(label, _link("Account", account), acc.account_type))


def validate_account(doc, method=None):
	"""Account.validate (doc_event): keeps 'SLCM Fee Components' usable and says when an account starts taking
	SLCM postings by its name, so no fee silently lands in the wrong ledger."""
	if not doc.meta.has_field("slcm_fee_components"):
		return
	names = None
	lines = [line.strip() for line in (doc.slcm_fee_components or "").splitlines() if line.strip()]
	if lines:
		label = doc.meta.get_label("slcm_fee_components")
		if doc.is_group:
			frappe.throw(_("{0}: only ledger (non-group) accounts can take SLCM fees.").format(label))
		if doc.account_type in ("Receivable", "Payable"):
			frappe.throw(
				_("{0}: a {1} account needs a Party on every entry; SLCM posts without one.").format(label, doc.account_type)
			)
		if doc.root_type not in FEE_ROOT_TYPES:
			frappe.throw(
				_("{0}: SLCM fees are credited to an Income, Liability (deposits) or Equity (funds) account, not {1}.").format(
					label, doc.root_type
				)
			)
		names = conf.slcm_fee_names()
		unknown = [line for line in lines if line.lower() not in names]
		if unknown:
			frappe.throw(
				_(
					"{0}: not an SLCM fee name - use a Fee Component or its Ledger, 'PACE [fee type]', 'FLE Course "
					"Fee', 'Re Exam Fee', 'Improvement Exam Fee' or 'Transcript Fee'. Unknown: {1}"
				).format(
					label, ", ".join(unknown)
				)
			)
		repeated = sorted({line for line in lines if [x.lower() for x in lines].count(line.lower()) > 1})
		if repeated:
			frappe.throw(_("{0}: listed more than once: {1}").format(label, ", ".join(repeated)))
		_check_listed_elsewhere(doc, lines, label)
		# Store the canonical spelling, one per line.
		doc.slcm_fee_components = "\n".join(names[line.lower()][0] for line in lines)

	if doc.is_group or doc.account_type in ("Receivable", "Payable") or doc.disabled:
		return
	if not (doc.is_new() or doc.has_value_changed("account_name")):
		return
	match = (names or conf.slcm_fee_names()).get((doc.account_name or "").strip().lower())
	if match and frappe.db.get_value("Company", doc.company, "slcm_enable_fee_posting"):
		frappe.msgprint(
			_(
				"This account is named like SLCM's {0} ({1}), so SLCM postings for it will go here from now on, "
				"ahead of any 'SLCM Fee Components' mapping. Entries already posted stay where they are. "
				"Review: Company {2} > SLCM Fees > Check Fee Mapping."
			).format(_fee_link(match[0]), match[1], _link("Company", doc.company)),
			title=_("SLCM Fee Posting"),
			indicator="orange",
		)


def _check_listed_elsewhere(doc, lines, label):
	wanted = {line.lower(): line for line in lines}
	others = frappe.get_all(
		"Account",
		filters={"company": doc.company, "name": ("!=", doc.name or ""), "slcm_fee_components": ("is", "set")},
		fields=["name", "slcm_fee_components"],
	)
	clashes = [
		_("{0} (already on Account {1})").format(_fee_link(wanted[key]), _link("Account", other.name))
		for other in others
		for key in conf.fee_component_lines(other.slcm_fee_components)
		if key in wanted
	]
	if clashes:
		frappe.throw(_("{0}: each SLCM name can post to one account only - {1}").format(label, "; ".join(clashes)))


@frappe.whitelist()
def fee_mapping(company):
	"""Where each SLCM fee name posts in this company, for the 'Check Fee Mapping' button."""
	frappe.only_for(MANAGERS)
	cfg = conf.get_config(company)
	default = cfg.get("slcm_default_fee_income_account")
	rows = []
	for comp in frappe.get_all("Fee Component", fields=["name", "ledger"], order_by="name"):
		account, how = conf.resolve_component(cfg, comp.name)
		rows.append(_mapping_row(comp.name, _("Fee Component"), account, how, default))
	field = frappe.get_meta("PACE Receipt").get_field("fee_type")
	for fee_type in ((field.options or "") if field else "").split("\n"):
		if fee_type.strip():
			rows.append(_named_row(cfg, f"PACE {fee_type.strip()}", _("PACE Receipt"), default))
	rows.append(_named_row(cfg, "FLE Course Fee", _("FLE Payment Log"), default))
	for doctype, name in conf.EXAM_FEE_NAMES.items():
		rows.append(_named_row(cfg, name, _(doctype), default))
	return {"rows": rows, "enabled": cfg.get("slcm_enable_fee_posting"), "default": default}


def _named_row(cfg, name, source, default):
	account = conf._exact_account(cfg, name)
	how = "Same name" if account else None
	if not account:
		account = conf.mapped_account(cfg, name)
		how = "SLCM Fee Components" if account else None
	return _mapping_row(name, source, account, how, default)


def _mapping_row(name, source, account, how, default):
	if account:
		status = _("Same name") if how == "Same name" else _("Mapped")
	elif default:
		account, status = default, _("Default account")
	else:
		status = _("Not mapped - posting will fail")
	return {"name": name, "source": source, "account": account, "status": status, "ok": bool(how)}


@frappe.whitelist()
def save_fee_mapping(company, mapping):
	"""'Map SLCM Fees': {SLCM name: account or ""} -> each account's 'SLCM Fee Components'. A blank account
	unmaps the name (it then posts to the default fee income ledger). Accounts are validated as they are saved
	(validate_account), all or nothing."""
	frappe.only_for(MANAGERS)
	mapping = frappe.parse_json(mapping) or {}
	names = conf.slcm_fee_names()
	cfg = conf.get_config(company)
	wanted, dropped = {}, set()
	for slcm_name, account in mapping.items():
		key = (slcm_name or "").strip().lower()
		if key not in names:
			frappe.throw(_("Not an SLCM fee name: {0}").format(slcm_name))
		if account and frappe.db.get_value("Account", account, "company") != company:
			frappe.throw(
				_("Account {0} does not belong to Company {1}").format(_link("Account", account), _link("Company", company))
			)
		name = names[key][0]
		# A Fee Component posts by its Ledger's name first (config.resolve_component): that is its exact name, and
		# a listing of the Ledger name would win over the component's, so it goes too.
		exact = conf.component_ledger_name(name) if frappe.db.exists("Fee Component", name) else name
		same = conf._exact_account(cfg, exact)
		if same and account and account != same:
			frappe.throw(
				_("{0}: Account {1} is named exactly like it and always takes it. Choose {1}, or rename it first.").format(
					_fee_link(name), _link("Account", same)
				)
			)
		# An exact-name account needs no listing.
		wanted[key] = None if account == same else (account or None)
		dropped.update({key, exact.lower()})

	current = {
		row.name: conf.fee_component_lines(row.slcm_fee_components)
		for row in frappe.get_all(
			"Account", filters={"company": company, "slcm_fee_components": ("is", "set")}, fields=["name", "slcm_fee_components"]
		)
	}
	target = {account: [line for line in lines if line not in dropped] for account, lines in current.items()}
	for key, account in wanted.items():
		if account:
			target.setdefault(account, []).append(key)

	changed = [account for account, lines in target.items() if lines != current.get(account, [])]
	# Two passes: first only drop names, then list the final ones - so a name moving between accounts never trips
	# "already listed on another account".
	for final in (False, True):
		for account in changed:
			lines = target[account] if final else [x for x in current.get(account, []) if x in target[account]]
			if not final and lines == current.get(account, []):
				continue
			doc = frappe.get_doc("Account", account)
			doc.slcm_fee_components = "\n".join(lines)
			doc.flags.ignore_permissions = True
			doc.save()
	if not changed:
		return _("No changes.")
	return _("Account(s) updated: {0}").format(", ".join(_link("Account", account) for account in changed))


@frappe.whitelist()
def create_fee_ledgers(company):
	frappe.only_for(MANAGERS)
	if not erpnext_installed():
		frappe.throw(_("ERPNext is not installed on this site."))
	from slcm.erpnext_bridge.setup_accounts import setup_fee_accounting

	created = setup_fee_accounting(company)
	return _setup_message(company, created)


def _setup_message(company, created):
	"""What 'Create SLCM Fee Ledgers' did, naming each DocType and linking every record it created."""
	from urllib.parse import quote

	from frappe.utils import get_link_to_form

	parts = []
	labels = {"Account": _("Account (ledger)"), "Mode of Payment": _("Mode of Payment (account row added)"),
		"Bank Account": _("Bank Account")}
	for doctype, label in labels.items():
		names = created.get(doctype) or []
		if names:
			links = ", ".join(get_link_to_form(doctype, name) for name in names)
			parts.append(f"<p><b>{label}</b> - {_('created')} {len(names)}: {links}</p>")
	if created.get("settings"):
		meta = frappe.get_meta("Company")
		filled = ", ".join(meta.get_label(f) or f for f in created["settings"])
		parts.append(f"<p><b>{_('Company')} {get_link_to_form('Company', company)}</b> - {_('filled')}: {filled}</p>")
	if not parts:
		parts.append(f"<p>{_('Nothing new: every ledger, Mode of Payment account and Bank Account already exists.')}</p>")
	if created.get("mapped_chart"):
		parts.append(
			"<p class='text-warning'>"
			+ _("This company maps SLCM fees through the Account field 'SLCM Fee Components', so no per-fee ledgers "
				"were created. Use SLCM Fees > Map SLCM Fees to change it.")
			+ "</p>"
		)
	parts.append(
		"<p>"
		+ (
			_("Posting is enabled. Review with SLCM Fees > Check Fee Mapping. Chart: {0}")
			if frappe.db.get_value("Company", company, "slcm_enable_fee_posting")
			else _("Next: SLCM Fees > Check Fee Mapping, then tick 'Enable SLCM Fee Posting'. Chart: {0}")
		).format(
			f"<a href='/desk/account/view/tree?company={quote(company)}'>{_('Chart of Accounts')}</a>"
		)
		+ "</p>"
	)
	return "".join(parts)


@frappe.whitelist()
def post_pending_now():
	frappe.only_for(MANAGERS)
	frappe.enqueue("slcm.erpnext_bridge.sync.sync_pending", queue="long")
	return _("Queued. Pending SLCM fee documents will be posted in a minute.")


@frappe.whitelist()
def repost(reference_doctype, reference_name):
	"""Re-post one SLCM document whose Journal Entry was cancelled in ERPNext."""
	frappe.only_for(MANAGERS)
	from slcm.erpnext_bridge.sync import last_error, sync_document

	status = sync_document(reference_doctype, reference_name, repost=True)
	if status == "Failed":
		frappe.throw(last_error(reference_doctype, reference_name) or _("Posting failed; see Error Log."))
	return status

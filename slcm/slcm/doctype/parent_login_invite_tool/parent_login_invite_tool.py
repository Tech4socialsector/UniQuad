import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, get_url, validate_email_address

PARENT_ROLE = "slcm_parent"

FILTER_FIELDS = (
	# (tool field, Student Master field, label)
	("academic_year", "academic_year", "Academic Year"),
	("programme", "programme_of_study", "Programme"),
	("batch", "batch", "Batch"),
	("student_status", "student_status", "Student Status"),
)


class ParentLoginInviteTool(Document):
	def validate(self):
		self._validate_batch_matches_year()

	def _validate_batch_matches_year(self):
		if not (self.batch and self.academic_year):
			return
		batch_year = frappe.db.get_value("SLCM Batch", self.batch, "academic_year")
		if batch_year and batch_year != self.academic_year:
			frappe.throw(
				_("Batch {0} belongs to {1}, not {2}.").format(
					frappe.bold(self.batch), frappe.bold(batch_year), frappe.bold(self.academic_year)
				),
				title=_("Batch / Academic Year Mismatch"),
			)

	@frappe.whitelist()
	def get_students(self):
		self.check_permission("write")

		filters = {sm_field: self.get(field) for field, sm_field, _label in FILTER_FIELDS if self.get(field)}
		selected = self.get_selected_students()
		if selected:
			filters["name"] = ["in", selected]
		if not filters:
			frappe.throw(_("Choose at least one filter before fetching students."), title=_("No Filters"))

		students = frappe.get_all(
			"Student Master",
			filters=filters,
			fields=["name", "first_name", "middle_name", "last_name"],
			order_by="name asc",
		)
		if not students:
			applied = ", ".join(
				f"{label}: {self.get(field)}" for field, _sm, label in FILTER_FIELDS if self.get(field)
			)
			if selected:
				applied = ", ".join(x for x in (_("{0} selected student(s)").format(len(selected)), applied) if x)
			frappe.throw(_("No students match these filters ({0}).").format(applied), title=_("No Students"))

		parents_by_student = {}
		for p in frappe.get_all(
			"Student Parent",
			filters={"parenttype": "Student Master", "parent": ["in", [s.name for s in students]]},
			fields=["parent", "relation", "first_name", "middle_name", "last_name", "email"],
			order_by="parent asc, idx asc",
		):
			parents_by_student.setdefault(p.parent, []).append(p)

		emails = {
			(p.email or "").strip().lower()
			for plist in parents_by_student.values()
			for p in plist
			if p.email
		}
		users = _get_user_info(emails)

		self.set("student_list", [])
		for s in students:
			student_name = _join_name(s)
			parents = parents_by_student.get(s.name)
			if not parents:
				self.append(
					"student_list",
					{
						"student": s.name,
						"student_name": student_name,
						"parent_relation": "",
						"parent_name": "",
						"parent_email": "",
						"invite_status": "No Email",
						"remarks": _("No parent / guardian recorded on the Student Master."),
					},
				)
				continue

			for p in parents:
				email = (p.email or "").strip().lower()
				status, remarks = self._classify(email, users.get(email))
				self.append(
					"student_list",
					{
						"student": s.name,
						"student_name": student_name,
						"parent_relation": p.relation or "",
						"parent_name": _join_name(p),
						"parent_email": email,
						"invite_status": status,
						"remarks": remarks,
					},
				)

		self.save()
		return self._counts()

	def get_selected_students(self):
		return [x.strip() for x in (self.selected_students or "").replace(",", "\n").splitlines() if x.strip()]

	def _classify(self, email, user):
		if not email:
			return "No Email", _("Add the parent's email on the Student Master.")
		if not validate_email_address(email):
			return "Invalid Email", _("'{0}' is not a valid email address.").format(email)
		if not user:
			return "Pending", ""
		if not user.enabled:
			return "Already Exists", _("A disabled user account already uses this email.")
		if user.user_type != "Website User" or not user.is_parent:
			return "Already Exists", _("Email belongs to an existing {0} account — not invited.").format(
				user.user_type
			)
		if self.resend_unactivated and not user.last_login:
			return "Pending", _("Account never used — a fresh link will be sent.")
		return "Already Exists", (
			_("Parent account active.") if user.last_login else _("Invited earlier, not logged in yet.")
		)

	@frappe.whitelist()
	def send_invites(self):
		self.check_permission("write")

		pending = [r for r in self.student_list if r.invite_status == "Pending"]
		if not pending:
			frappe.throw(_("There are no Pending rows to invite. Use Get Students first."), title=_("Nothing to Send"))

		# One email per parent, even when siblings share the same parent.
		by_email = {}
		for row in pending:
			by_email.setdefault(row.parent_email.strip().lower(), []).append(row)

		invited = failed = 0
		for email, rows in by_email.items():
			wards = list(dict.fromkeys(r.student_name or r.student for r in rows))
			queue_name = None
			try:
				_create_or_refresh_parent_user(email, rows[0].parent_name)
				queue = _send_parent_invite_email(email, rows[0].parent_name, wards)
				if not queue:
					frappe.throw(_("Email was not queued (address may be unsubscribed or blocked)."))
				queue_name = queue.name
				frappe.db.commit()
				status, remarks = "Invited", _("Queued for delivery on {0}.").format(
					frappe.utils.format_datetime(frappe.utils.now())
				)
				invited += 1
			except Exception as e:
				frappe.db.rollback()
				frappe.log_error(title=f"Parent invite failed: {email}")
				status, remarks = "Failed", str(e)[:250] or _("See Error Log.")
				failed += 1
			for r in rows:
				r.invite_status = status
				r.remarks = remarks
				r.email_queue = queue_name

		self.save()
		return {**self._counts(), "invited_now": invited, "failed_now": failed}

	@frappe.whitelist()
	def check_delivery(self):
		"""Read each invited row's Email Queue entry and report what the mailer did."""
		self.check_permission("write")
		queues = {r.email_queue for r in self.student_list if r.email_queue}
		if not queues:
			frappe.throw(_("No invites have been sent from this record yet."), title=_("Nothing to Check"))

		qinfo = {
			q.name: q
			for q in frappe.get_all(
				"Email Queue", filters={"name": ["in", list(queues)]}, fields=["name", "status", "error", "modified"]
			)
		}
		result = {"Sent": set(), "Queued": set(), "Error": set()}
		for r in self.student_list:
			if not r.email_queue:
				continue
			q = qinfo.get(r.email_queue)
			if not q:
				r.remarks = _("Email Queue entry no longer exists (cleared by retention).")
				continue
			when = frappe.utils.format_datetime(q.modified)
			if q.status == "Sent":
				r.invite_status, r.remarks = "Invited", _("Delivered to mail server on {0}.").format(when)
				result["Sent"].add(r.email_queue)
			elif q.status in ("Error", "Cancelled", "Expired"):
				r.invite_status = "Failed"
				last_line = ((q.error or "").strip().splitlines() or [""])[-1]
				r.remarks = _("Mailer {0}: {1}").format(q.status, last_line[:200] or _("see Email Queue"))
				result["Error"].add(r.email_queue)
			else:
				r.invite_status, r.remarks = "Invited", _("{0} — waiting for the email queue.").format(q.status)
				result["Queued"].add(r.email_queue)
		self.save()
		return {k: len(v) for k, v in result.items()}

	def _counts(self):
		counts = {"total": len(self.student_list)}
		for r in self.student_list:
			counts[r.invite_status] = counts.get(r.invite_status, 0) + 1
		return counts


@frappe.whitelist()
def create_from_students(students):
	"""Student Master list → Action → Parent Login Invite."""
	students = frappe.parse_json(students) if isinstance(students, str) else students
	students = list(dict.fromkeys(s for s in (students or []) if s))
	if not students:
		frappe.throw(_("Select at least one student."))
	if len(students) > 2000:
		frappe.throw(_("Select at most 2000 students at a time."))

	frappe.has_permission("Parent Login Invite Tool", "create", throw=True)
	found = set(frappe.get_all("Student Master", filters={"name": ["in", students]}, pluck="name"))
	missing = [s for s in students if s not in found]
	if missing:
		frappe.throw(_("Student(s) not found: {0}").format(", ".join(missing[:10])))

	tool = frappe.new_doc("Parent Login Invite Tool")
	tool.student_status = ""
	tool.selected_students = "\n".join(students)
	tool.insert()
	tool.get_students()
	return tool.name


def _join_name(d):
	return " ".join(x for x in (d.first_name, d.get("middle_name"), d.last_name) if x).strip()


def _get_user_info(emails):
	if not emails:
		return {}
	users = frappe.get_all(
		"User",
		filters={"name": ["in", list(emails)]},
		fields=["name", "enabled", "user_type", "last_login"],
	)
	parents = set(
		frappe.get_all(
			"Has Role",
			filters={"parenttype": "User", "role": PARENT_ROLE, "parent": ["in", list(emails)]},
			pluck="parent",
		)
	)
	info = {}
	for u in users:
		u.is_parent = u.name in parents
		info[u.name.lower()] = u
	return info


def _ensure_parent_role():
	if not frappe.db.exists("Role", PARENT_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": PARENT_ROLE, "desk_access": 0}).insert(
			ignore_permissions=True
		)


def _create_or_refresh_parent_user(email, full_name):
	"""Create a Website User with the parent role. Existing users are only
	reached here when they are already parent Website Users (resend case)."""
	_ensure_parent_role()

	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		if user.user_type != "Website User":
			frappe.throw(_("{0} is a {1}; refusing to send a parent invite.").format(email, user.user_type))
		if PARENT_ROLE not in [r.role for r in user.roles]:
			user.append("roles", {"role": PARENT_ROLE})
			user.save(ignore_permissions=True)
		return user

	parts = (full_name or "").split()
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": parts[0] if parts else email.split("@")[0],
			"last_name": " ".join(parts[1:]),
			"send_welcome_email": 0,
			"user_type": "Website User",
			"roles": [{"role": PARENT_ROLE}],
		}
	)
	user.insert(ignore_permissions=True)
	return user


def _send_parent_invite_email(email, parent_name, wards):
	# User.reset_password stores the sha256 of the key, which is what
	# /update-password looks up. Storing the raw key gives a dead link.
	reset_link = frappe.get_doc("User", email).reset_password(send_email=False)
	portal_link = get_url("/parent-portal")

	ward_text = ", ".join(escape_html(w) for w in wards)
	ward_label = _("ward's") if len(wards) == 1 else _("wards'")
	subject = _("Parent Portal Access — {0}").format(", ".join(wards))
	message = f"""
<p>Dear {escape_html(parent_name or "Parent/Guardian")},</p>

<p>You have been granted access to the <strong>Parent Portal</strong> to view
your {ward_label} (<strong>{ward_text}</strong>) attendance, academic results and fees.</p>

<p>Please set your password and log in using the link below:</p>

<p style="text-align:center;margin:24px 0;">
  <a href="{reset_link}"
     style="background:#1a3c6e;color:#fff;padding:12px 28px;border-radius:6px;
            text-decoration:none;font-weight:600;font-size:14px;">
    Set Password &amp; Log In
  </a>
</p>

<p>After setting your password, you can always access the portal at:<br>
<a href="{portal_link}">{portal_link}</a></p>

<p style="color:#6b7280;font-size:12px;">
  If you did not expect this email, please contact the Registrar's Office.
</p>
"""
	# Queued, not sent inline: a big batch would otherwise do one SMTP round-trip
	# per parent inside this request, and SMTP errors are swallowed by Frappe
	# (they only show up as Email Queue status = Error → see check_delivery).
	# If the scheduler is off nothing would flush the queue, so send right after commit.
	from frappe.utils.scheduler import is_scheduler_disabled

	return frappe.sendmail(
		recipients=[email],
		subject=subject,
		message=message,
		reference_doctype="User",
		reference_name=email,
		now=is_scheduler_disabled(verbose=False),
	)

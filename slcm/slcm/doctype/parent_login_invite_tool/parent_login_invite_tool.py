import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_url


class ParentLoginInviteTool(Document):

    @frappe.whitelist()
    def get_students(self):
        if not any([self.student_status, self.academic_year, self.batch]):
            frappe.throw(_("Select at least one filter before fetching students."))

        filters = {}
        if self.student_status:
            filters["student_status"] = self.student_status
        if self.academic_year:
            filters["academic_year"] = self.academic_year
        if self.batch:
            filters["batch"] = self.batch

        students = frappe.get_all(
            "Student Master",
            filters=filters,
            fields=["name", "first_name", "last_name"],
        )

        if not students:
            self.set("student_list", [])
            self.save()
            filter_summary = ", ".join(f"{k} = {v}" for k, v in filters.items())
            frappe.throw(_(f"No students found. Filters applied: {filter_summary}"))

        self.set("student_list", [])

        for s in students:
            full_name = f"{s.first_name} {s.last_name or ''}".strip()
            parents = frappe.get_all(
                "Student Parent",
                filters={"parent": s.name, "parenttype": "Student Master"},
                fields=["relation", "first_name", "last_name", "email"],
            )

            if not parents:
                row = self.append("student_list", {})
                row.student = s.name
                row.student_name = full_name
                row.parent_relation = "—"
                row.parent_name = "No parent records"
                row.parent_email = ""
                row.invite_status = "No Email"
                continue

            for p in parents:
                row = self.append("student_list", {})
                row.student = s.name
                row.student_name = full_name
                row.parent_relation = p.relation or "—"
                row.parent_name = f"{p.first_name or ''} {p.last_name or ''}".strip() or "—"
                row.parent_email = p.email or ""
                if not p.email:
                    row.invite_status = "No Email"
                else:
                    existing = frappe.db.exists("User", p.email)
                    row.invite_status = "Already Exists" if existing else "Pending"

        self.set("summary_html", "")
        self.save()
        return len(self.student_list)

    @frappe.whitelist()
    def send_invites(self):
        if not self.student_list:
            frappe.throw(_("No students in the list. Use 'Get Students' first."))

        pending = [r for r in self.student_list if r.invite_status == "Pending"]
        if not pending:
            frappe.throw(_("No pending invites — all parents already have accounts or have no email."))

        invited = 0
        failed = 0
        skipped = 0

        for row in self.student_list:
            if row.invite_status != "Pending":
                skipped += 1
                continue
            try:
                _create_parent_user_and_invite(row.parent_email, row.parent_name, row.student_name)
                row.invite_status = "Invited"
                invited += 1
            except Exception as e:
                frappe.log_error(frappe.get_traceback(), f"Parent invite failed: {row.parent_email}")
                row.invite_status = "Failed"
                failed += 1

        summary_parts = [f"<strong>{invited}</strong> invite(s) sent"]
        if failed:
            summary_parts.append(f"<span style='color:#dc2626'><strong>{failed}</strong> failed</span>")
        if skipped:
            summary_parts.append(f"<strong>{skipped}</strong> skipped (already exist / no email)")

        self.summary_html = (
            "<div style='padding:12px 16px;background:#f0fdf4;border:1px solid #86efac;"
            "border-radius:8px;font-size:13px;'>"
            + " &nbsp;·&nbsp; ".join(summary_parts)
            + "</div>"
        )
        self.save()
        return {"invited": invited, "failed": failed, "skipped": skipped}


def _ensure_parent_role():
    """Create the slcm_parent role if it doesn't exist yet (before bench migrate runs)."""
    if not frappe.db.exists("Role", "slcm_parent"):
        role = frappe.get_doc({
            "doctype": "Role",
            "role_name": "slcm_parent",
            "desk_access": 0,
        })
        role.insert(ignore_permissions=True)
        frappe.db.commit()


def _create_parent_user_and_invite(email, full_name, ward_name):
    if not email:
        return

    _ensure_parent_role()

    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
        if not frappe.db.exists("Has Role", {"parent": email, "role": "slcm_parent"}):
            user.append("roles", {"role": "slcm_parent"})
            user.save(ignore_permissions=True)
        return

    first = full_name.split()[0] if full_name else email.split("@")[0]
    last = " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else ""

    user = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": first,
        "last_name": last,
        "send_welcome_email": 0,
        "user_type": "Website User",
        "roles": [{"role": "slcm_parent"}],
    })
    user.insert(ignore_permissions=True)
    frappe.db.commit()

    _send_parent_invite_email(email, full_name, ward_name)


def _send_parent_invite_email(email, parent_name, ward_name):
    from frappe.utils import get_url
    reset_link = get_url("/update-password?key=" + _get_reset_key(email))
    portal_link = get_url("/parent-portal")

    subject = f"Parent Portal Access — {ward_name}"
    message = f"""
<p>Dear {parent_name or 'Parent/Guardian'},</p>

<p>You have been granted access to the <strong>Parent Portal</strong> to view
your ward's (<strong>{ward_name}</strong>) attendance and academic results.</p>

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
    frappe.sendmail(recipients=[email], subject=subject, message=message, now=True)


def _get_reset_key(email):
    from frappe.utils.password import update_password, get_password_reset_limit
    from frappe.core.doctype.user.user import User as FrappeUser
    import hashlib, time, hmac
    key = frappe.generate_hash(length=32)
    frappe.db.set_value("User", email, "reset_password_key", key)
    frappe.db.set_value("User", email, "last_reset_password_key_generated_on", frappe.utils.now())
    frappe.db.commit()
    return key

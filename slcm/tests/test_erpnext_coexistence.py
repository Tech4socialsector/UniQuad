# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""ERPNext coexistence: SLCM DocTypes renamed to "SLCM <name>" so they don't clash with ERPNext v16.

Run:  bench --site <site> run-tests --module slcm.tests.test_erpnext_coexistence

Uses unittest.TestCase (not IntegrationTestCase) so Frappe doesn't build ERPNext's sample test
records, whose Fiscal Years overlap a real site's. Every test that writes rolls back in tearDown,
so the site is unchanged afterwards. Checklist: docs/erpnext_coexistence_test_checklist.md
"""

import importlib
import json
import os
import pkgutil
import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, getdate, now_datetime

RENAMED = {
	"Batch": "SLCM Batch",
	"Company": "SLCM Company",
	"Department": "SLCM Department",
	"Designation": "SLCM Designation",
	"Driver": "SLCM Driver",
	"Payment Request": "SLCM Payment Request",
	"Video": "SLCM Video",
}
OLD_NAMES = tuple(RENAMED)

# Admission campus fields link to ERPNext's Company on purpose (campus API filters on is_group).
ALLOWED_OLD_LINKS = {
	("Admission Report Config", "campus"),
	("Applicant Campus Preference", "campus"),
	("Applicant Document", "campus"),
	("Campus Seat Matrix", "campus"),
	("Compliance Report Config", "filter_by_campus"),
	("Portal Announcement", "target_campus"),
}

# Removed from fixtures: they belong to DocTypes that no longer exist.
STALE_PROPERTY_SETTERS = (
	"Class Schedule-naming_series-options",
	"LMS Certificate-main-default_print_format",
	"Program Reservation Policy-naming_series-default",
	"Program Reservation Policy-naming_series-options",
)

APP_PATH = frappe.get_app_path("slcm")


def erpnext_installed():
	return "erpnext" in frappe.get_installed_apps()


def slcm_modules():
	return frappe.get_all("Module Def", filters={"app_name": "slcm"}, pluck="name")


class TestRenameSchema(unittest.TestCase):
	"""Read-only checks on DocType metadata, stored references and fixtures."""

	def test_slcm_doctypes_exist_in_slcm_modules(self):
		modules = set(slcm_modules())
		for new in RENAMED.values():
			module = frappe.db.get_value("DocType", new, "module")
			self.assertIn(module, modules, f"{new} missing or not in an SLCM module")
			self.assertTrue(frappe.db.table_exists(new), f"table for {new} missing")
			frappe.get_meta(new)

	def test_bare_names_are_not_owned_by_slcm(self):
		modules = set(slcm_modules())
		for old in OLD_NAMES:
			module = frappe.db.get_value("DocType", old, "module")
			self.assertNotIn(module, modules, f"{old} is still an SLCM DocType")
			if erpnext_installed():
				self.assertEqual(frappe.db.get_value("DocType", old, "custom"), 0)
				self.assertEqual(frappe.get_meta(old).module, module)

	def test_rename_patch_ran(self):
		self.assertTrue(
			frappe.db.exists("Patch Log", {"patch": "slcm.patches.v2_0.rename_erpnext_clashing_doctypes"})
		)

	def test_slcm_fields_link_to_renamed_doctypes(self):
		modules = slcm_modules()
		rows = frappe.db.sql(
			"""select df.parent, df.fieldname, df.options from `tabDocField` df
			join `tabDocType` dt on dt.name = df.parent
			where df.fieldtype in ('Link', 'Table', 'Table MultiSelect')
			and df.options in %(old)s and dt.module in %(modules)s""",
			{"old": OLD_NAMES, "modules": modules},
			as_dict=True,
		)
		bad = [r for r in rows if (r.parent, r.fieldname) not in ALLOWED_OLD_LINKS]
		self.assertEqual(bad, [], "SLCM fields still linking to bare (ERPNext) DocTypes")
		for parent, fieldname in ALLOWED_OLD_LINKS:
			self.assertEqual(frappe.get_meta(parent).get_field(fieldname).options, "Company")

	def test_no_slcm_metadata_on_bare_names(self):
		modules = slcm_modules()
		checks = {
			"Report": ("ref_doctype", {"module": ["in", modules]}),
			"Number Card": ("document_type", {"module": ["in", modules]}),
			"Dashboard Chart": ("document_type", {"module": ["in", modules]}),
			"Notification": ("document_type", {"module": ["in", modules]}),
			"Server Script": ("reference_doctype", {}),
			"Client Script": ("dt", {"module": ["in", modules]}),
		}
		for doctype, (field, filters) in checks.items():
			found = frappe.get_all(doctype, filters={**filters, field: ["in", OLD_NAMES]}, pluck="name")
			self.assertEqual(found, [], f"{doctype} records still pointing at bare names")

		workspaces = frappe.get_all("Workspace", filters={"module": ["in", modules]}, pluck="name")
		for child in ("Workspace Link", "Workspace Shortcut"):
			found = frappe.get_all(
				child,
				filters={"parent": ["in", workspaces], "link_to": ["in", OLD_NAMES]},
				fields=["parent", "link_to"],
			)
			self.assertEqual(found, [], f"{child} in SLCM workspaces still points at bare names")

	def test_property_setters_moved_to_slcm_payment_request(self):
		self.assertTrue(frappe.db.exists("Property Setter", {"doc_type": "SLCM Payment Request"}))
		slcm_props = [
			p for p in frappe.get_all("Property Setter", filters={"doc_type": ["in", OLD_NAMES]}, pluck="name")
			if p.startswith("Payment Request-")
		]
		self.assertEqual(slcm_props, [])

	def test_stale_fixtures_removed(self):
		with open(os.path.join(APP_PATH, "fixtures", "property_setter.json")) as f:
			names = {d["name"] for d in json.load(f)}
		self.assertFalse(names & set(STALE_PROPERTY_SETTERS))
		with open(os.path.join(APP_PATH, "fixtures", "web_form.json")) as f:
			self.assertNotIn("job-opportunity", {d["name"] for d in json.load(f)})
		for name in STALE_PROPERTY_SETTERS:
			self.assertFalse(frappe.db.exists("Property Setter", name), name)

	def test_admission_sidebar_links_slcm_payment_request(self):
		# Frappe 17 "Sidebar" file; synced only once the site is on Frappe 17.
		with open(os.path.join(APP_PATH, "admission", "sidebar", "admission", "admission.json")) as f:
			items = json.load(f)["items"]
		links = {i.get("link_to") for i in items if i.get("link_type") == "DocType"}
		self.assertIn("SLCM Payment Request", links)
		self.assertFalse(links & set(OLD_NAMES) - {"Company"})

	def test_all_slcm_modules_import(self):
		failed = []
		for info in pkgutil.walk_packages([APP_PATH], prefix="slcm."):
			name = info.name
			if ".tests" in name or ".test_" in name or ".www." in name or "-" in name:
				continue
			try:
				importlib.import_module(name)
			except Exception as e:
				failed.append(f"{name}: {type(e).__name__}: {e}")
		self.assertEqual(failed, [])


class RollbackTestCase(unittest.TestCase):
	"""Runs each test in one transaction and rolls it back; background jobs are not queued."""

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		enqueue = patch("frappe.enqueue")
		self.enqueued = enqueue.start()
		self.addCleanup(enqueue.stop)

	def tearDown(self):
		frappe.db.rollback()
		frappe.set_user("Administrator")

	def existing(self, doctype, filters=None, field="name"):
		value = frappe.db.get_value(doctype, filters or {}, field)
		if not value:
			self.skipTest(f"needs an existing {doctype}")
		return value

	def batch_doc(self, name="ZZT MPP 2026 - Trimester I"):
		# Batch dates, year and programme master are always fetched from the Programme, so use one
		# whose term dates and Programme Master are filled in.
		programmes = frappe.get_all(
			"Programme",
			filters={"term_start_date": ["is", "set"], "term_end_date": ["is", "set"]},
			fields=["name", "academic_year", "program_name", "term_start_date", "term_end_date"],
			order_by="term_start_date desc",
		)
		programme = next((p for p in programmes if frappe.db.exists("Programme Master", p.program_name)), None)
		if not programme:
			self.skipTest("needs a Programme with term dates and a Programme Master")
		self.programme = programme
		return frappe.get_doc(
			{
				"doctype": "SLCM Batch",
				"batch_name": name,
				"program": programme.name,
				"academic_year": programme.academic_year,
				"programme_name": programme.program_name,
				"start_date": programme.term_start_date,
				"end_date": programme.term_end_date,
				"status": "Active",
			}
		)

	def make_batch(self, name="ZZT MPP 2026 - Trimester I"):
		return self.batch_doc(name).insert()

	def make_department(self):
		return frappe.get_doc(
			{
				"doctype": "SLCM Department",
				"department_id": "ZZT-CAL",
				"department_name": "ZZT Constitutional & Administrative Law",
				"status": "Active",
			}
		).insert()

	def make_company(self):
		return frappe.get_doc(
			{
				"doctype": "SLCM Company",
				"company_name": "ZZT Khaitan Legal Associates",
				"industry": "Legal",
				"status": "Active",
			}
		).insert()

	def make_driver(self):
		return frappe.get_doc(
			{
				"doctype": "SLCM Driver",
				"driver_id": "ZZT07",
				"driver_name": "Ravi Kumar",
				"license_number": "KA01 20190012345",
				"phone": "9845012345",
				"status": "Active",
			}
		).insert()


class TestSLCMBatch(RollbackTestCase):
	def test_create_from_programme_term(self):
		batch = self.make_batch()
		self.assertEqual(batch.name, "ZZT MPP 2026 - Trimester I")
		self.assertTrue(frappe.db.exists("SLCM Batch", batch.name))
		self.assertEqual(getdate(batch.start_date), getdate(self.programme.term_start_date))
		self.assertEqual(getdate(batch.end_date), getdate(self.programme.term_end_date))
		days = (getdate(batch.end_date) - getdate(batch.start_date)).days
		self.assertEqual((batch.term_days, batch.term_weeks), (days, days // 7))
		if erpnext_installed():
			self.assertFalse(frappe.db.exists("Batch", batch.name), "landed in ERPNext's stock Batch")

	def test_end_before_start_rejected(self):
		# Dates fetched from the Programme override what's typed, so check the controller rule directly.
		batch = self.batch_doc()
		batch.start_date, batch.end_date = "2026-11-30", "2026-07-01"
		with self.assertRaises(frappe.ValidationError):
			batch.validate()

	def test_section_links_to_batch(self):
		batch = self.make_batch()
		section = frappe.get_doc(
			{"doctype": "Section", "batch": batch.name, "section_name": "A", "status": "Active"}
		).insert()
		self.assertEqual(section.name, f"{batch.name}-A")

	def test_student_master_batch_link(self):
		self.assertEqual(frappe.get_meta("Student Master").get_field("batch").options, "SLCM Batch")
		student = frappe.db.get_value("Student Master", {"batch": ["is", "set"]}, ["name", "batch"], as_dict=True)
		if not student:
			self.skipTest("needs a Student Master with a batch")
		self.assertTrue(frappe.db.exists("SLCM Batch", student.batch))


class TestFacultyMasters(RollbackTestCase):
	def test_department_designation_on_faculty(self):
		from slcm.utils.faculty_portal import set_faculty_nav

		department = self.make_department()
		designation = frappe.get_doc({"doctype": "SLCM Designation", "__newname": "ZZT Associate Professor"}).insert()
		faculty = frappe.get_doc(
			{
				"doctype": "Faculty",
				"faculty_id": "ZZT-FAC-001",
				"first_name": "Ananya",
				"last_name": "Rao",
				"email": "ananya.rao.zzt@example.com",
				# An existing image: a missing file is logged as "Error Attaching File" even on rollback.
				"photo": self.existing("File", {"is_private": 0, "file_url": ["like", "/files/%.png"]}, "file_url"),
				"status": "Active",
				"department": department.name,
				"designation": designation.name,
			}
		).insert()

		context = frappe._dict()
		set_faculty_nav(context, faculty)
		self.assertEqual(context.faculty_department, "ZZT Constitutional & Administrative Law")
		self.assertEqual(context.faculty_designation, "ZZT Associate Professor")

	def test_department_on_curriculum_target(self):
		department = self.make_department()
		self.assertEqual(frappe.get_meta("Curriculum").get_field("department").options, "SLCM Department")
		self.assertEqual(frappe.get_meta("Programme").get_field("department").options, "SLCM Department")
		self.assertTrue(frappe.db.exists("SLCM Department", department.name))
		if erpnext_installed():
			self.assertFalse(frappe.db.exists("Department", department.name))


class TestPlacementCompany(RollbackTestCase):
	def setUp(self):
		super().setUp()
		for role in ("ZZT Litigation Associate", "ZZT Legal Analyst"):
			frappe.get_doc({"doctype": "Placement Opportunity setbyuser", "__newname": role}).insert()

	def test_company_contact_and_opportunity(self):
		company = self.make_company()
		contact = frappe.get_doc(
			{
				"doctype": "Company Contact",
				"company": company.name,
				"contact_name": "Meera Iyer",
				"email": "meera.iyer.zzt@example.com",
			}
		).insert()
		self.assertEqual(contact.name, f"{company.name}-Meera Iyer")

		start = now_datetime()
		opportunity = frappe.get_doc(
			{
				"doctype": "Placement Opportunity",
				"company": company.name,
				"opportunity_type": "Internship",
				"status": "Open",
				"application_start": start,
				"application_end": add_days(start, 10),
				"role_name": [{"placement_opportunity": "ZZT Litigation Associate"}],
			}
		).insert()
		self.assertEqual(opportunity.company, company.name)
		if erpnext_installed():
			self.assertFalse(frappe.db.exists("Company", company.name), "recruiter landed in ERPNext Company")

	def test_opportunity_end_before_start_rejected(self):
		company = self.make_company()
		start = now_datetime()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Placement Opportunity",
					"company": company.name,
					"opportunity_type": "Placement",
					"status": "Open",
					"application_start": start,
					"application_end": add_days(start, -1),
					"role_name": [{"placement_opportunity": "ZZT Legal Analyst"}],
				}
			).insert()


class TestDriverAndVideo(RollbackTestCase):
	def test_driver_naming_and_id_card(self):
		driver = self.make_driver()
		self.assertEqual(driver.name, "DRV-ZZT07")

		card = frappe.get_doc(
			{
				"doctype": "Student ID Card",
				"card_type": "Driver",
				"driver": driver.name,
				"id_card_template": self.existing("ID Card Template"),
				"card_status": "Draft",
				"issue_date": getdate(),
				"expiry_date": add_days(getdate(), 365),
			}
		).insert()
		self.assertEqual(card.student_name, "Ravi Kumar")
		self.assertEqual(card.phone, "9845012345")
		self.assertTrue(self.enqueued.called, "ID card image generation should be queued")

	def test_video_naming(self):
		video = frappe.get_doc(
			{
				"doctype": "SLCM Video",
				"title": "Orientation 2026: Welcome Address",
				"url": "https://www.youtube.com/watch?v=zztOrient26",
			}
		).insert()
		self.assertTrue(video.name.startswith("VID-"))
		if erpnext_installed():
			self.assertFalse(frappe.db.exists("Video", video.name))


class TestSLCMPaymentRequest(RollbackTestCase):
	def make_request(self, **values):
		reference = self.make_batch()
		doc = frappe.get_doc(
			{
				"doctype": "SLCM Payment Request",
				"reference_doctype": "SLCM Batch",
				"reference_name": reference.name,
				"amount": 25000,
				"currency": "INR",
				"email_to": "priya.nair.zzt@example.com",
				"status": "Requested",
				**values,
			}
		)
		return doc.insert()

	def test_paid_sets_paid_on(self):
		request = self.make_request(status="Paid")
		self.assertTrue(request.name.startswith("PR-"))
		self.assertIsNotNone(request.paid_on)
		if erpnext_installed():
			self.assertFalse(frappe.db.exists("Payment Request", request.name))

	def test_amount_must_be_positive(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_request(amount=0)

	def test_status_only_changes_from_backend(self):
		request = self.make_request()
		request.status = "Paid"
		with self.assertRaises(frappe.ValidationError):
			request.save()

		request.reload()
		request.status = "Paid"
		frappe.flags.payment_request_status_from_backend = True
		try:
			request.save()
		finally:
			frappe.flags.payment_request_status_from_backend = False
		self.assertEqual(frappe.db.get_value("SLCM Payment Request", request.name, "status"), "Paid")

	def test_receipts_link_to_slcm_payment_request(self):
		self.assertEqual(
			frappe.get_meta("Applicant Payment Receipt").get_field("payment_reference").options,
			"SLCM Payment Request",
		)
		self.assertEqual(
			frappe.get_meta("PACE Receipt").get_field("payment_request").options, "SLCM Payment Request"
		)


@unittest.skipUnless(erpnext_installed(), "ERPNext not installed")
class TestERPNextSide(RollbackTestCase):
	def test_erpnext_department_stays_in_erpnext_table(self):
		company = self.existing("Company")
		department = frappe.get_doc(
			{"doctype": "Department", "department_name": "ZZT Accounts Office", "company": company}
		).insert()
		self.assertTrue(frappe.db.exists("Department", department.name))
		self.assertFalse(frappe.db.exists("SLCM Department", {"department_name": "ZZT Accounts Office"}))

	def test_campus_options_are_erpnext_companies(self):
		from slcm.admission.utils.portal import api_get_campus_options

		companies = set(frappe.get_all("Company", pluck="name"))
		options = api_get_campus_options()
		self.assertTrue(options)
		self.assertTrue({o["name"] for o in options} <= companies)

	def test_erpnext_payment_request_untouched(self):
		meta = frappe.get_meta("Payment Request")
		self.assertEqual(meta.module, "Accounts")
		self.assertIsNotNone(meta.get_field("payment_request_type"))


class TestPortalPages(RollbackTestCase):
	"""Renders student portal pages that read the renamed DocTypes, as a real student."""

	PAGES = (
		"student-portal",
		"student-portal/profile",
		"student-portal/courses",
		"student-portal/fees",
		"student-portal/placement",
		"student-portal/attendance",
		"student-portal/timetable",
		"student-portal/results",
		"student-portal/documents",
	)

	def test_student_pages_render(self):
		from frappe.website.page_renderers.template_page import TemplatePage

		student = frappe.db.get_value(
			"Student Master", {"batch": ["is", "set"], "user": ["is", "set"]}, ["user", "first_name"], as_dict=True
		)
		if not student:
			self.skipTest("needs a Student Master with a batch and a user")
		frappe.set_user(student.user)
		for path in self.PAGES:
			with self.subTest(path=path):
				frappe.local.form_dict = frappe._dict()
				response = TemplatePage(path, 200).render()
				self.assertEqual(response.status_code, 200)
				self.assertNotIn("Traceback", response.get_data(as_text=True))

	def test_data_map_counts(self):
		from slcm.slcm.page.slcm_data_map.slcm_data_map import get_doctype_counts

		counts = get_doctype_counts()
		text = json.dumps(counts, default=str)
		for new in ("SLCM Batch", "SLCM Department"):
			self.assertIn(new, text)

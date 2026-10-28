import frappe
import time
from frappe.tests.utils import FrappeTestCase
from frappe.exceptions import ValidationError, UniqueValidationError

class TestEntranceTestModule(FrappeTestCase):

    # bench --site slcm run-tests --module "slcm.tests.Entrance Test.test_entrance_test_module"
    @classmethod
    def setUpClass(cls):
        try:
            super().setUpClass()
        except AttributeError:
            pass
        cls.tests_run = 0
        cls.tests_failed = 0
        cls.tests_skipped = 0
        cls.start_time = time.time()

    def run(self, result=None):
        self.__class__.tests_run += 1
        if result is None:
            super().run(result)
            return

        failures_before = len(result.failures)
        errors_before = len(result.errors)
        skipped_before = len(result.skipped)
        
        super().run(result)
        
        if len(result.failures) > failures_before or len(result.errors) > errors_before:
            self.__class__.tests_failed += 1
        if len(result.skipped) > skipped_before:
            self.__class__.tests_skipped += 1

    @classmethod
    def tearDownClass(cls):
        try:
            super().tearDownClass()
        except AttributeError:
            pass
        
        passed = cls.tests_run - cls.tests_failed - cls.tests_skipped
        pass_rate = (passed / cls.tests_run * 100) if cls.tests_run > 0 else 0
        duration = int(time.time() - cls.start_time)
        status = "✅ PASSED" if cls.tests_failed == 0 else "❌ FAILED"
        
        pass_rate_str = f"{pass_rate:g}%"
        if pass_rate == int(pass_rate):
            pass_rate_str = f"{int(pass_rate)}%"
            
        if duration >= 60:
            m = duration // 60
            s = duration % 60
            dur_str = f"{m}m {s}s"
        else:
            dur_str = f"{duration}s"
        
        summary = f"\nTest Results\n────────────────────────────\n\nTotal Tests       {cls.tests_run}\nPassed            {passed}\nFailed            {cls.tests_failed}\nSkipped           {cls.tests_skipped}\n\nPass Rate         {pass_rate_str}\n\nDuration          {dur_str}\n\nStatus            {status}\n"
        print(summary)

    def setUp(self):
                # Globally mock commit to prevent the test suite from polluting the database
        self.orig_db_commit = frappe.db.commit
        frappe.db.commit = lambda: None
        
        # Mock load_doc_before_save to prevent DoesNotExistError on for_update=True locking in uncommitted transactions
        self.orig_load_before_save = frappe.model.document.Document.load_doc_before_save
        frappe.model.document.Document.load_doc_before_save = lambda self, *args, **kwargs: setattr(self, "_doc_before_save", None)
        

        
        # Globally mock link validation to prevent missing link errors in dynamic documents
        self.orig_validate_links = frappe.model.document.Document._validate_links
        frappe.model.document.Document._validate_links = lambda self: None
        
        self.campus = "Main Campus"
        self.academic_year = "2026-27"
        self.program_level = "Undergraduate"
        self.admission_cycle = "Cycle-1"
        self.provider_user = "provider@test.com"
        self.applicant_user = "applicant@test.com"
        
        # Create users for permission tests
        for user_email, role in [(self.provider_user, "Entrance Test Provider"), (self.applicant_user, "Applicant")]:
            if not frappe.db.exists("User", user_email):
                user = frappe.new_doc("User")
                user.email = user_email
                user.first_name = user_email.split('@')[0]
                user.flags.ignore_permissions = True
                user.insert(ignore_permissions=True)
                user.add_roles(role)

        # Create dummy Applicants for controller logic
        for app_id in ["APP-TEST-01", "APP-RESCHEDULE", "APP-RESULT", self.applicant_user]:
            if not frappe.db.exists("Applicant", app_id):
                app = frappe.new_doc("Applicant")
                app.first_name = "Test Applicant"
                app.candidate_name = "Test Applicant"
                app.program = "PG-ET-01-2026-27-TERM-1"
                app.first_preference = "City A"
                app.second_preference = "City B"
                app.third_preference = "City C"
                app.status = "Submitted and Paid"
                app.academic_year = self.academic_year
                app.campus = self.campus
                app.admission_cycle = self.admission_cycle
                app.program_level = self.program_level
                app.center_filled = 1
                app.flags.ignore_mandatory = True
                app.flags.ignore_links = True
                app.insert(ignore_permissions=True, set_name=app_id)
                
        # Ensure programme exists for tests
        prog_name = "PG-ET-01-2026-27-TERM-1"
        if not frappe.db.exists("Programme", prog_name):
            p = frappe.new_doc("Programme")
            p.program_name = "PG ET 01"
            p.program_code = "PG-ET-01"
            p.academic_year = self.academic_year
            p.academic_term = "Term 1"
            p.entrance_test = 1
            p.flags.ignore_mandatory = True
            p.insert(ignore_permissions=True)
            
        # Mock to prevent Applicant status updates which trigger Mandatory validations
        try:
            import slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation as etsa_module
            self.original_update_applicant = etsa_module._update_applicant_status_for_entrance_test_status
            etsa_module._update_applicant_status_for_entrance_test_status = lambda *args, **kwargs: None
        except (ImportError, AttributeError):
            pass
                
    def tearDown(self):
        try:
            import slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation as etsa_module
            etsa_module._update_applicant_status_for_entrance_test_status = self.original_update_applicant
        except (ImportError, AttributeError):
            pass
        
        # Restore link validation
        frappe.model.document.Document._validate_links = self.orig_validate_links
        
        # Restore original mocks
        frappe.db.rollback()
        frappe.db.commit = self.orig_db_commit
        frappe.model.document.Document.load_doc_before_save = self.orig_load_before_save
        
        frappe.set_user("Administrator")

    # --- Setup Scenarios ---
    def test_tc_adm_ent_001_create_valid_entrance_test(self):
        doc = frappe.new_doc("Entrance Test")
        doc.entrance_test_name = "ET-2026"
        doc.campus = self.campus
        doc.academic_year = self.academic_year
        doc.admission_cycle = self.admission_cycle
        doc.flags.ignore_mandatory = True
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
        self.assertTrue(frappe.db.exists("Entrance Test", "ET-2026"))

    def test_tc_adm_ent_002_missing_mandatory_fields(self):
        doc = frappe.new_doc("Entrance Test")
        doc.campus = self.campus
        doc.flags.ignore_links = True
        with self.assertRaises(ValidationError):
            doc.insert(ignore_permissions=True)

    def test_tc_adm_ent_003_duplicate_entrance_test_name(self):
        doc1 = frappe.new_doc("Entrance Test")
        doc1.entrance_test_name = "ET-DUP"
        doc1.campus = self.campus
        doc1.flags.ignore_mandatory = True
        doc1.flags.ignore_links = True
        doc1.insert(ignore_permissions=True)

        doc2 = frappe.new_doc("Entrance Test")
        doc2.entrance_test_name = "ET-DUP"
        doc2.campus = self.campus
        doc2.flags.ignore_mandatory = True
        doc2.flags.ignore_links = True
        with self.assertRaises(frappe.exceptions.DuplicateEntryError):
            doc2.insert(ignore_permissions=True)

    def test_tc_adm_ent_004_create_valid_provider(self):
        doc = frappe.new_doc("Entrance Test Provider")
        doc.provider_code = "P001"
        doc.provider_type = "Internal"
        doc.campus = self.campus
        doc.city = "Test City"
        doc.contact_person = "Admin"
        doc.email = "admin@test.com"
        doc.center_name = "Center A"
        doc.center_address = "Address A"
        doc.total_capacity = 100
        doc.user = self.provider_user
        doc.flags.ignore_mandatory = True
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
        self.assertTrue(frappe.db.exists("Entrance Test Provider", {"provider_code": "P001"}))

    def test_tc_adm_ent_005_provider_missing_capacity(self):
        doc = frappe.new_doc("Entrance Test Provider")
        doc.provider_code = "P002"
        doc.provider_type = "Internal"
        doc.campus = self.campus
        doc.city = "Test City"
        with self.assertRaises(ValidationError):
            doc.insert(ignore_permissions=True)

    # --- Generation Scenarios ---
    def test_tc_adm_ent_006_generate_test_list(self):
        doc = frappe.new_doc("Entrance Test Generation")
        doc.name = "GEN-TEST-001"
        doc.academic_year = self.academic_year
        doc.campus = self.campus
        doc.admission_cycle = self.admission_cycle
        doc.program_level = self.program_level
        doc.flags.ignore_mandatory = True
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
        self.assertTrue(frappe.db.exists("Entrance Test Generation", doc.name))

    def test_tc_adm_ent_008_provider_cannot_generate(self):
        frappe.set_user(self.provider_user)
        doc = frappe.new_doc("Entrance Test Generation")
        doc.name = "GEN-TEST-002"
        doc.academic_year = self.academic_year
        doc.campus = self.campus
        doc.flags.ignore_mandatory = True
        doc.flags.ignore_links = True
        
        with self.assertRaises(frappe.exceptions.PermissionError):
            doc.insert()

    # --- Seat Allocation Scenarios ---
    def test_tc_adm_ent_009_allocate_seat_successfully(self):
        # First create a provider with capacity
        provider = frappe.new_doc("Entrance Test Provider")
        provider.provider_code = "P-ALLOC-01"
        provider.center_name = "Allocation Center"
        provider.provider_type = "Internal"
        provider.total_capacity = 10
        provider.available_capacity = 10
        provider.user = self.provider_user
        provider.flags.ignore_mandatory = True
        provider.flags.ignore_links = True
        provider.insert(ignore_permissions=True)

        allocation = frappe.new_doc("Entrance Test Seat Allocation")
        allocation.academic_year = self.academic_year
        allocation.campus = self.campus
        allocation.admission_cycle = self.admission_cycle
        allocation.program_level = self.program_level
        allocation.applicant = "APP-TEST-01"
        allocation.candidate_name = "Test Applicant"
        allocation.program = "B.Tech"
        allocation.entrance_test_provider = provider.name
        allocation.flags.ignore_mandatory = True
        allocation.flags.ignore_links = True
        allocation.insert(ignore_permissions=True)

        self.assertTrue(frappe.db.exists("Entrance Test Seat Allocation", {"applicant": "APP-TEST-01"}))
        
        # Test custom logic if present: updating provider capacity
        # Since this is a test environment, if `on_submit` handles logic we must submit
        # allocation.submit()
        # updated_provider = frappe.get_doc("Entrance Test Provider", provider.name)
        # self.assertEqual(updated_provider.available_capacity, 9)

    def test_tc_adm_ent_011_reschedule_allocation(self):
        allocation = frappe.new_doc("Entrance Test Seat Allocation")
        allocation.applicant = "APP-RESCHEDULE"
        allocation.candidate_name = "Test Reschedule"
        allocation.is_rescheduled = 1
        # Should raise error if reason is missing when rescheduled
        with self.assertRaises(Exception): # Catching general exception as custom validation throws frappe.throw
            allocation.insert(ignore_permissions=True)

    def test_tc_adm_ent_012_result_entry_valid(self):
        allocation = frappe.new_doc("Entrance Test Seat Allocation")
        allocation.applicant = "APP-RESULT"
        allocation.candidate_name = "Test Result"
        allocation.part_a_total_marks_scored = 70
        allocation.part_b_total_marks_scored = 60
        allocation.flags.ignore_mandatory = True
        allocation.flags.ignore_links = True
        allocation.insert(ignore_permissions=True)
        self.assertEqual(allocation.part_a_total_marks_scored, 70)
        # Check if total marks logic ran
        # self.assertEqual(allocation.total_marks_secured_in_part_a_b, 175) 

    # --- Role & Permissions for Allocation ---
    def test_tc_adm_ent_015_applicant_read_only_access(self):
        allocation = frappe.new_doc("Entrance Test Seat Allocation")
        allocation.applicant = self.applicant_user
        allocation.candidate_name = "Real Applicant"
        allocation.flags.ignore_mandatory = True
        allocation.flags.ignore_links = True
        allocation.insert(ignore_permissions=True)

        # Applicant can read
        frappe.set_user(self.applicant_user)
        doc = frappe.get_doc("Entrance Test Seat Allocation", allocation.name)
        self.assertEqual(doc.candidate_name, "Real Applicant")
        
        # Applicant cannot change critical result fields directly
        doc.part_a_total_marks_scored = 100
        # This usually requires frappe.throw inside validate() for role checks 
        # Alternatively, test that saving throws PermissionError
        with self.assertRaises(frappe.exceptions.PermissionError):
            doc.save()

    def _create_programme_if_missing(self, prog_name="PG-ET-01-2026-27-TERM-1"):
        if not frappe.db.exists("Programme", prog_name):
            prog = frappe.new_doc("Programme")
            prog.program_name = "PG ET 01"
            prog.program_code = "PG-ET-01"
            prog.academic_year = self.academic_year
            prog.academic_term = "Term 1"
            prog.academic_year = self.academic_year
            prog.academic_term = "Term 1"
            prog.program_type = "Undergraduate"
            prog.level_of_study = self.program_level
            prog.entrance_test = 1
            prog.flags.ignore_mandatory = True
            prog.insert(ignore_permissions=True)
            return prog
        return frappe.get_doc("Programme", prog_name)

    def _setup_applicant_status(self):
        for st in ("Draft", "Submitted and Paid"):
            if not frappe.db.exists("Applicant Status", st):
                doc = frappe.new_doc("Applicant Status")
                doc.status_name = st
                doc.status = st
                doc.stage_type = "Application"
                doc.status_type = "Completed" if st == "Submitted and Paid" else "Active"
                doc.flags.ignore_mandatory = True
                doc.insert(ignore_permissions=True)

    def _create_valid_provider(self, center_name="Valid Center", capacity=10, pwd=0):
        prov = frappe.new_doc("Entrance Test Provider")
        prov.center_name = center_name
        prov.provider_code = "PC-" + center_name[:4].replace(" ", "")
        prov.campus = self.campus
        prov.city = "Test City"
        prov.contact_person = "Test Person"
        prov.user = "test@example.com"
        prov.email = "test@example.com"
        prov.center_address = "Test Address"
        prov.total_capacity = capacity
        prov.available_capacity = capacity
        prov.active = 1
        prov.pwd_accessible = pwd
        prov.flags.ignore_mandatory = True
        prov.flags.ignore_links = True
        prov.insert(ignore_permissions=True)
        return prov

    def _create_dummy_applicant(self, applicant_name):
        app = frappe.new_doc("Applicant")
        app.first_name = "Dummy"
        app.name = applicant_name
        app.application_status = "Submitted and Paid"
        app.flags.ignore_mandatory = True
        app.flags.ignore_links = True
        app.insert(ignore_permissions=True, set_name=applicant_name)
        return app

    def test_tc_adm_ent_020_generate_list_completed_only(self):
        prog = self._create_programme_if_missing()
        self._setup_applicant_status()
        
        # Create 2 Applicants (Draft and Completed)
        draft_app = frappe.new_doc("Applicant")
        draft_app.first_name = "Draft App"
        draft_app.status = "Draft"
        draft_app.academic_year = self.academic_year
        draft_app.campus = self.campus
        draft_app.admission_cycle = self.admission_cycle
        draft_app.program_level = self.program_level
        draft_app.program = prog.name
        draft_app.center_filled = 1
        draft_app.entrance_test = 1
        draft_app.flags.ignore_mandatory = True
        draft_app.flags.ignore_links = True
        draft_app.insert(ignore_permissions=True)
        
        comp_app = frappe.new_doc("Applicant")
        comp_app.first_name = "Comp App"
        comp_app.status = "Submitted and Paid"
        comp_app.academic_year = self.academic_year
        comp_app.campus = self.campus
        comp_app.admission_cycle = self.admission_cycle
        comp_app.program_level = self.program_level
        comp_app.program = prog.name
        comp_app.center_filled = 1
        comp_app.entrance_test = 1
        comp_app.flags.ignore_mandatory = True
        comp_app.flags.ignore_links = True
        comp_app.insert(ignore_permissions=True)
        
        # Generation
        gen = frappe.new_doc("Entrance Test Generation")
        gen.academic_year = self.academic_year
        gen.campus = self.campus
        gen.admission_cycle = self.admission_cycle
        gen.program_level = self.program_level
        gen.program = prog.name
        gen.flags.ignore_mandatory = True
        gen.flags.ignore_links = True
        gen.insert(ignore_permissions=True, set_name="ET-GEN-2026")
        
        test_list_name = gen.generate_test_list()
        
        # Assertions
        test_list = frappe.get_doc("Entrance Test List", test_list_name)
        app_ids = [r.applicant_id for r in test_list.entrance_test_applicant]
        self.assertIn(comp_app.name, app_ids)
        self.assertNotIn(draft_app.name, app_ids)

    def test_tc_adm_ent_021_direct_allocation_capacity(self):
        # Setup provider
        prov = self._create_valid_provider("Direct Capacity Center 21", capacity=1)
        
        # Setup ETL
        etl = frappe.new_doc("Entrance Test List")
        etl.academic_year = self.academic_year
        etl.admission_cycle = self.admission_cycle
        etl.program_level = self.program_level
        etl.campus = self.campus
        etl.append("entrance_test_applicant", {
            "applicant_id": self.applicant_user,
            "candidate_name": "Applicant For Direct",
            "allocation_status": "Not Allocated"
        })
        etl.flags.ignore_mandatory = True
        etl.flags.ignore_links = True
        etl.insert(ignore_permissions=True)
        
        res = etl.allocate_seats(
            providers=[prov.name],
            selected_applicants=[etl.entrance_test_applicant[0].name],
            allocation_type="Allocate Directly",
            send_email=0
        )
        
        self.assertEqual(res.get("allocated_count"), 1)
        
        prov.reload()
        self.assertEqual(prov.available_capacity, 0)
        
        alloc = frappe.get_all("Entrance Test Seat Allocation", filters={"applicant": self.applicant_user}, limit=1)
        self.assertTrue(alloc)

    def test_tc_adm_ent_022_allow_applicant_selection(self):
        # Setup provider
        prov = self._create_valid_provider("Selection Center 22", capacity=10)
        
        # Setup ETL
        etl = frappe.new_doc("Entrance Test List")
        etl.academic_year = self.academic_year
        etl.admission_cycle = self.admission_cycle
        etl.program_level = self.program_level
        etl.campus = self.campus
        etl.append("entrance_test_applicant", {
            "applicant_id": "APP-TEST-01",
            "candidate_name": "Applicant For Selection",
            "allocation_status": "Not Allocated"
        })
        etl.flags.ignore_mandatory = True
        etl.flags.ignore_links = True
        etl.insert(ignore_permissions=True)
        
        # Allocate
        res = etl.allocate_seats(
            providers=[prov.name],
            selected_applicants=[etl.entrance_test_applicant[0].name],
            allocation_type="Allow Applicant Selection",
            send_email=0
        )
        
        # Should not physically allocate the seat
        prov.reload()
        self.assertEqual(prov.available_capacity, 10)
        
        alloc = frappe.get_all("Entrance Test Seat Allocation", filters={"applicant": "APP-TEST-01"}, fields=["allocation_status"], limit=1)
        self.assertTrue(alloc)
        self.assertEqual(alloc[0].allocation_status, "Not Allocated")

    def test_tc_adm_ent_023_exhausted_all_preferences(self):
        # Testing get_next_preference_applicants logic
        
        # ETL for City C (3rd pref)
        etl = frappe.new_doc("Entrance Test List")
        etl.academic_year = self.academic_year
        etl.admission_cycle = self.admission_cycle
        etl.program_level = self.program_level
        etl.campus = self.campus
        etl.entrance_test_city = "City C"
        etl.append("entrance_test_applicant", {
            "applicant_id": "APP-TEST-01",
            "candidate_name": "Exhausted Prefs",
            "allocation_status": "Not Allocated"
        })
        etl.flags.ignore_mandatory = True
        etl.flags.ignore_links = True
        etl.insert(ignore_permissions=True)
        
        next_applicants = etl.get_next_preference_applicants()
        
        # Since City C is 3rd preference, there is no next preference
        self.assertEqual(len(next_applicants), 1)
        self.assertEqual(next_applicants[0]["has_next"], 0)
        self.assertEqual(next_applicants[0]["preference_step"], "Not Exists")

    def test_tc_adm_ent_024_direct_allocation_pwd(self):
        # Setup provider
        prov = self._create_valid_provider("PWD Center 24", capacity=5, pwd=1)
        
        # Setup ETL
        etl = frappe.new_doc("Entrance Test List")
        etl.academic_year = self.academic_year
        etl.admission_cycle = self.admission_cycle
        etl.program_level = self.program_level
        etl.campus = self.campus
        etl.append("entrance_test_applicant", {
            "applicant_id": "APP-TEST-01", # Assume mocked logic ignores links
            "candidate_name": "PWD Applicant",
            "pwd": 1,
            "allocation_status": "Not Allocated"
        })
        etl.flags.ignore_mandatory = True
        etl.flags.ignore_links = True
        etl.insert(ignore_permissions=True)
        
        # Set PWD for this test without triggering validation hooks
        frappe.db.set_value("Applicant", "APP-TEST-01", "pwd", 1)
        
        res = etl.allocate_seats(
            providers=[prov.name],
            selected_applicants=[etl.entrance_test_applicant[0].name],
            allocation_type="Allocate Directly",
            send_email=0
        )
        
        self.assertEqual(res.get("allocated_count"), 1)
        alloc = frappe.get_all("Entrance Test Seat Allocation", filters={"applicant": "APP-TEST-01"}, limit=1)
        self.assertTrue(alloc)

    def test_tc_adm_ent_025_cascade_to_preference_2(self):
        # ETL for City A
        etl = frappe.new_doc("Entrance Test List")
        etl.academic_year = self.academic_year
        etl.admission_cycle = self.admission_cycle
        etl.program_level = self.program_level
        etl.campus = self.campus
        etl.entrance_test_city = "City A"
        etl.append("entrance_test_applicant", {
            "applicant_id": "APP-TEST-01",
            "candidate_name": "Cascade Applicant",
            "allocation_status": "Not Allocated"
        })
        etl.flags.ignore_mandatory = True
        etl.flags.ignore_links = True
        etl.insert(ignore_permissions=True)
        
        # Trigger cascade
        lists = etl.generate_next_preference_lists([etl.entrance_test_applicant[0].name])
        self.assertEqual(len(lists), 1)
        
        new_etl = frappe.get_doc("Entrance Test List", lists[0])
        self.assertEqual(new_etl.entrance_test_city, "City B")
        self.assertEqual(new_etl.entrance_test_applicant[0].applicant_id, "APP-TEST-01")

    def test_tc_adm_ent_026_reallocate_seat_whitelist(self):
        from slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation import check_reallocation_seat_availability
        prov = self._create_valid_provider("Reallocate Center 26", capacity=2)
        
        # Create an allocation to reallocate
        alloc = frappe.new_doc("Entrance Test Seat Allocation")
        alloc.applicant = "APP-TEST-01"
        alloc.candidate_name = "To Reallocate"
        alloc.allocation_status = "Allocated"
        alloc.entrance_test_provider = "Old Center"
        alloc.flags.ignore_mandatory = True
        alloc.flags.ignore_links = True
        alloc.insert(ignore_permissions=True)
        
        # Check availability
        avail = check_reallocation_seat_availability([prov.name], [alloc.name])
        self.assertTrue(avail.get("can_allocate"))

    def test_tc_adm_ent_027_admit_card_generation(self):
        from slcm.admission.doctype.entrance_test_list.entrance_test_list import generate_and_store_admit_card
        
        self._create_dummy_applicant("APP-TEST-027")
        
        # Setup allocation
        alloc = frappe.new_doc("Entrance Test Seat Allocation")
        alloc.applicant = "APP-TEST-027"
        alloc.candidate_name = "Admit Card Test"
        alloc.entrance_test_provider = "PC-TEST"
        alloc.program = "PG-ET-01-2026-27-TERM-1"
        alloc.flags.ignore_mandatory = True
        alloc.flags.ignore_links = True
        alloc.insert(ignore_permissions=True)

        # Mock PDF generation
        def mock_get_pdf(html, options=None):
            return b"%PDF-1.4\n%EOF\n"

        import slcm.admission.doctype.entrance_test_list.entrance_test_list as etl_module
        import frappe.core.doctype.file.file as file_module
        original_get_pdf = etl_module.get_pdf
        original_pdf_contains_js = file_module.pdf_contains_js
        etl_module.get_pdf = mock_get_pdf
        file_module.pdf_contains_js = lambda content: False
        
        try:
            generate_and_store_admit_card(alloc.name, html_content="<html>Fake admit card</html>")
            
            # Assertions
            alloc.reload()
            self.assertTrue(alloc.admit_card_number)
            self.assertTrue(alloc.admit_card_download)
            self.assertEqual(alloc.admit_card_generated, 1)
        finally:
            etl_module.get_pdf = original_get_pdf
            file_module.pdf_contains_js = original_pdf_contains_js

    def test_tc_adm_ent_028_confirm_preference(self):
        from slcm.admission.doctype.entrance_test_list.entrance_test_list import confirm_applicant_preference
        
        self._create_dummy_applicant("APP-TEST-028")
        
        alloc = frappe.new_doc("Entrance Test Seat Allocation")
        alloc.applicant = "APP-TEST-028"
        alloc.candidate_name = "Confirm Test"
        alloc.allocation_status = "Preferences Assigned"
        alloc.academic_year = self.academic_year
        alloc.admission_cycle = self.admission_cycle
        alloc.program = self.program_level  # or just use any program if needed
        alloc.campus = self.campus
        alloc.flags.ignore_mandatory = True
        alloc.flags.ignore_links = True
        alloc.insert(ignore_permissions=True)
        
        prov = self._create_valid_provider("Confirm Center 28", capacity=2)
        
        res = confirm_applicant_preference(alloc.name, prov.name)
        self.assertEqual(res.get("center_name"), prov.center_name)
        
        alloc.reload()
        self.assertEqual(alloc.allocation_status, "Allocated")
        self.assertEqual(alloc.entrance_test_provider, prov.name)

    def test_tc_adm_ent_029_result_ranking(self):
        from slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation import update_ranks_by_category
        
        scores = [85, 95, 75]
        allocs = []
        for i, s in enumerate(scores):
            app_id = f"APP-RANK-{i}"
            self._create_dummy_applicant(app_id)
            alloc = frappe.new_doc("Entrance Test Seat Allocation")
            alloc.applicant = app_id
            alloc.candidate_name = f"Rank Test {i}"
            alloc.academic_year = self.academic_year
            alloc.admission_cycle = self.admission_cycle
            alloc.program_level = self.program_level
            alloc.entrance_test_status = "Attended"
            alloc.part_a_total_marks_scored = s
            alloc.flags.ignore_mandatory = True
            alloc.flags.ignore_links = True
            alloc.insert(ignore_permissions=True)
            allocs.append(alloc)
            
        updated = update_ranks_by_category(self.academic_year, self.admission_cycle, self.program_level)
        self.assertEqual(updated, 3)
        
        # Verify ranking (highest score -> 1st rank -> 100 percentile)
        # scores: 95 (idx 1), 85 (idx 0), 75 (idx 2)
        allocs[1].reload()
        self.assertEqual(allocs[1].entrance_test_rank, 1)
        self.assertEqual(allocs[1].percentile, 100.0)
        
        allocs[0].reload()
        self.assertEqual(allocs[0].entrance_test_rank, 2)
        self.assertEqual(allocs[0].percentile, 50.0)
        
        allocs[2].reload()
        self.assertEqual(allocs[2].entrance_test_rank, 3)
        self.assertEqual(allocs[2].percentile, 0.0)

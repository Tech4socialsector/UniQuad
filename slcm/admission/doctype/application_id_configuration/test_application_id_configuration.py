# Copyright (c) 2026, TFSS and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from slcm.admission.doctype.admission_cycle.admission_cycle import (
    is_valid_application_id_code,
    normalize_application_id_code,
    parse_application_id_number_format,
)
from slcm.admission.doctype.applicant.applicant import (
    APPLICATION_ID_SERIES_PREFIX,
    application_id_series_key,
    get_application_id_settings,
    next_application_id,
)

APPLICANT_MODULE = "slcm.admission.doctype.applicant.applicant"


class TestApplicationIDConfiguration(FrappeTestCase):
    def test_number_format_is_fixed_part_plus_hashes(self):
        self.assertEqual(parse_application_id_number_format("7#####"), ("7", 5))
        self.assertEqual(parse_application_id_number_format("######"), ("", 6))
        self.assertEqual(parse_application_id_number_format(" 26-#### "), ("26-", 4))
        self.assertEqual(parse_application_id_number_format("a7###"), ("A7", 3))
        self.assertIsNone(parse_application_id_number_format(""))
        self.assertIsNone(parse_application_id_number_format("7"))
        self.assertIsNone(parse_application_id_number_format("7##"))
        self.assertIsNone(parse_application_id_number_format("#" * 11))
        self.assertIsNone(parse_application_id_number_format("##7###"))
        self.assertIsNone(parse_application_id_number_format("B7{######}"))

    def test_code_validation(self):
        self.assertEqual(normalize_application_id_code(" b7 "), "B7")
        self.assertTrue(is_valid_application_id_code("B7"))
        self.assertTrue(is_valid_application_id_code("LLM-7"))
        self.assertFalse(is_valid_application_id_code(""))
        self.assertFalse(is_valid_application_id_code("B7{######}"))
        self.assertFalse(is_valid_application_id_code("B 7"))

    def test_series_key_is_per_cycle_and_fits_tab_series(self):
        self.assertEqual(application_id_series_key("june to july"), APPLICATION_ID_SERIES_PREFIX + "june to july")
        self.assertNotEqual(application_id_series_key("Cycle A"), application_id_series_key("Cycle B"))
        self.assertLessEqual(len(application_id_series_key("x" * 200)), 100)

    @patch(f"{APPLICANT_MODULE}.frappe.db.exists", return_value=False)
    @patch(f"{APPLICANT_MODULE}.getseries", return_value="000041")
    def test_next_application_id_uses_cycle_series(self, getseries, _exists):
        self.assertEqual(next_application_id("june to july", "B7", 6), "B7000041")
        getseries.assert_called_once_with(application_id_series_key("june to july"), 6)

    @patch(f"{APPLICANT_MODULE}.getseries", side_effect=["000001", "000002"])
    def test_next_application_id_skips_existing_names(self, _getseries):
        with patch(f"{APPLICANT_MODULE}.frappe.db.exists", side_effect=[True, False]):
            self.assertEqual(next_application_id("june to july", "A7", 6), "A7000002")

    def test_settings_pick_code_by_nationality(self):
        row = frappe._dict(domestic_application_id_format="B", international_application_id_format="F")

        def get_value(doctype, *args, **kwargs):
            return "7#####" if doctype == "Admission Cycle" else row

        with patch(f"{APPLICANT_MODULE}.frappe.db.get_value", side_effect=get_value):
            self.assertEqual(get_application_id_settings("C", "BA", "No"), ("B7", 5))
            self.assertEqual(get_application_id_settings("C", "BA", "Yes"), ("F7", 5))
            row.international_application_id_format = ""
            self.assertEqual(get_application_id_settings("C", "BA", "Yes"), ("B7", 5))
            self.assertIsNone(get_application_id_settings(None, "BA", "No"))

    @patch(f"{APPLICANT_MODULE}.frappe.db.exists", return_value=False)
    @patch(f"{APPLICANT_MODULE}.getseries", return_value="00001")
    def test_code_b_with_7_hashes_gives_b700001(self, _getseries, _exists):
        self.assertEqual(next_application_id("C", "B7", 5), "B700001")

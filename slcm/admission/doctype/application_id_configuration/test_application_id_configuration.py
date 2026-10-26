# Copyright (c) 2026, TFSS and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from slcm.admission.doctype.admission_cycle.admission_cycle import _is_valid_application_id_format
from slcm.admission.doctype.applicant.applicant import _render_application_id


class TestApplicationIDConfiguration(FrappeTestCase):
    def test_application_id_format_requires_one_five_or_six_digit_series(self):
        self.assertTrue(_is_valid_application_id_format("format:B6{######}"))
        self.assertTrue(_is_valid_application_id_format("format:F{#####}"))
        self.assertFalse(_is_valid_application_id_format("B6{######}"))
        self.assertFalse(_is_valid_application_id_format("format:B6{####}"))
        self.assertFalse(_is_valid_application_id_format("format:B6{######}{#####}"))

    @patch("slcm.admission.doctype.applicant.applicant.getseries", return_value="000041")
    def test_application_id_uses_shared_series(self, getseries):
        application_id = _render_application_id("format:B6{######}", frappe._dict())

        self.assertEqual(application_id, "B6000041")
        getseries.assert_called_once_with("Applicant Application Number", 6)

# Copyright (c) 2026, TFSS and Contributors
# See license.txt

import frappe
import unittest


class TestSeatAllocation(unittest.TestCase):
    def test_seat_allocation_sorting(self):
        doc_names = frappe.get_all("Seat Allocation", order_by="creation desc", limit=1)
        if not doc_names:
            self.skipTest("No Seat Allocation records found in the database.")
            
        doc_name = doc_names[0].name
        doc = frappe.get_doc("Seat Allocation", doc_name)
        
        # Override selection_applicant with controlled test candidates (reusing existing IDs to avoid LinkValidationError)
        if len(doc.selection_applicant) < 3:
            self.skipTest("Not enough applicants in the document to test sorting.")
            
        applicants = doc.selection_applicant[:3]
        
        # Set them to tie completely (same total_score, same Part A and Part B)
        # Map names to applicant IDs so that:
        # - Suresh Das gets APP-2026-00460 (smallest ID)
        # - Vikram Joshi gets APP-2026-01378 (middle ID)
        # - Anjali Reddy gets APP-2026-01674 (largest ID)
        applicants[0].applicant_id = "APP-2026-01674"
        applicants[0].candidate_name = "Anjali Reddy"
        applicants[0].nlsat_part_a_score = 50.0
        applicants[0].nlsat_part_b_score = 50.0
        applicants[0].interview_score = 50.0
        applicants[0].total_score = 100.0
        applicants[0].selection_status = "Selected"
        
        applicants[1].applicant_id = "APP-2026-00460"
        applicants[1].candidate_name = "Suresh Das"
        applicants[1].nlsat_part_a_score = 50.0
        applicants[1].nlsat_part_b_score = 50.0
        applicants[1].interview_score = 50.0
        applicants[1].total_score = 100.0
        applicants[1].selection_status = "Selected"
        
        applicants[2].applicant_id = "APP-2026-01378"
        applicants[2].candidate_name = "Vikram Joshi"
        applicants[2].nlsat_part_a_score = 50.0
        applicants[2].nlsat_part_b_score = 50.0
        applicants[2].interview_score = 50.0
        applicants[2].total_score = 100.0
        applicants[2].selection_status = "Selected"
        
        doc.set("selection_applicant", [applicants[1], applicants[2], applicants[0]])
        
        # Mock doc.save to prevent database writes and name overwriting from database records
        doc.save = lambda *args, **kwargs: doc
        
        doc.status = "Draft"
        doc.allocate_seats()
        
        # Check that top rank 1 candidates are sorted as:
        # 1. Suresh Das
        # 2. Vikram Joshi
        # 3. Anjali Reddy
        rank_1_candidates = [
            (r.candidate_name, r.idx)
            for r in doc.selection_applicant
            if r.overall_rank == 1
        ]
        
        self.assertEqual(len(rank_1_candidates), 3)
        self.assertEqual(rank_1_candidates[0][0], "Suresh Das")
        self.assertEqual(rank_1_candidates[1][0], "Vikram Joshi")
        self.assertEqual(rank_1_candidates[2][0], "Anjali Reddy")

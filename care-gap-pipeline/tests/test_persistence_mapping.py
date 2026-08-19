"""
Unit tests for Star Rating audit and Final Recommendation persistence mappings,
denominator handling, and pipeline stage persistence failure handling.
"""

import os
import sys
import unittest
import uuid
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import backend.services.supabase_service as svc_module
from backend.services.supabase_service import SupabaseService, _MOCK_STORAGE
from backend.services.result_persistence_service import ResultPersistenceService
from backend.services.pipeline_service import (
    PipelineRunState,
    _run_pipeline_thread,
    get_run_state,
    STAGE_KEYS,
)


@patch.object(svc_module, "is_supabase_configured", return_value=False)
class TestPersistenceMapping(unittest.TestCase):
    def setUp(self):
        for k in list(_MOCK_STORAGE.keys()):
            _MOCK_STORAGE[k] = []

    def test_01_star_rating_audit_column_mapping_actual_columns(self, _mock_cfg):
        """
        Verify that actual audit DataFrame columns produced by
        compute_project_estimated_star_contribution() correctly map to Supabase columns.
        """
        run_id = str(uuid.uuid4())
        audit_df = pd.DataFrame([{
            "Member ID": "PT15580",
            "Care Gap": "Controlling Blood Pressure",
            "Measure ID": "C14",
            "Plan ID": "P005",
            "Current Performance": 0.6543,
            "Closure Probability": 0.8765,
            "Projected Performance": 0.6552,
            "Current Measure Star": 3.5,
            "Projected Measure Star": 3.8,
            "Measure Star Improvement": 0.3,
            "Measure Weight": 3.0,
            "Estimated Star Contribution": 0.0012,
            "Final Member Contribution": 0.0012,
        }])

        inserted = ResultPersistenceService.persist_star_rating_contributions(run_id, audit_df)
        self.assertEqual(inserted, 1)

        records = _MOCK_STORAGE.get("star_rating_contributions", [])
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["run_id"], run_id)
        self.assertEqual(rec["member_id"], "PT15580")
        self.assertEqual(rec["plan_id"], "P005")
        self.assertEqual(rec["care_gap"], "Controlling Blood Pressure")
        self.assertEqual(rec["measure_id"], "C14")
        self.assertIsNone(rec.get("denominator"))  # Denominator absent -> None / NULL
        self.assertEqual(rec["current_measure_star"], 3.5)
        self.assertEqual(rec["measure_weight"], 3.0)
        self.assertEqual(rec["closure_probability"], 0.8765)
        self.assertEqual(rec["plan_star_contribution"], 0.0012)

    def test_02_star_rating_audit_with_denominator(self, _mock_cfg):
        """Verify that Denominator is persisted when provided in audit DataFrame."""
        run_id = str(uuid.uuid4())
        audit_df = pd.DataFrame([{
            "Member ID": "PT15580",
            "Care Gap": "Controlling Blood Pressure",
            "Measure ID": "C14",
            "Plan ID": "P005",
            "Denominator": 2500.0,
            "Current Performance": 0.6543,
            "Closure Probability": 0.8765,
            "Current Measure Star": 3.5,
            "Measure Weight": 3.0,
            "Estimated Star Contribution": 0.0012,
        }])

        ResultPersistenceService.persist_star_rating_contributions(run_id, audit_df)
        records = _MOCK_STORAGE.get("star_rating_contributions", [])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["denominator"], 2500.0)

    def test_03_star_rating_audit_database_column_fallback(self, _mock_cfg):
        """Verify fallback to database-style column names."""
        run_id = str(uuid.uuid4())
        audit_df = pd.DataFrame([{
            "member_id": "PT15904",
            "plan_id": "P002",
            "care_gap": "Diabetes Care",
            "measure_id": "C12",
            "denominator": 1500.0,
            "performance_value": 0.72,
            "current_measure_star": 4.0,
            "measure_weight": 3.0,
            "closure_probability": 0.90,
            "plan_star_contribution": 0.0025,
        }])

        ResultPersistenceService.persist_star_rating_contributions(run_id, audit_df)
        records = _MOCK_STORAGE.get("star_rating_contributions", [])
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["member_id"], "PT15904")
        self.assertEqual(rec["plan_id"], "P002")
        self.assertEqual(rec["performance_value"], 0.72)
        self.assertEqual(rec["current_measure_star"], 4.0)
        self.assertEqual(rec["plan_star_contribution"], 0.0025)

    def test_04_final_recommendation_column_mapping(self, _mock_cfg):
        """
        Verify that actual 10-column final member report DataFrame maps
        precisely to Supabase final_recommendations columns.
        """
        run_id = str(uuid.uuid4())
        report_df = pd.DataFrame([{
            "S. No.": 1,
            "Member ID": "PT15580",
            "Member Name": "frances lewis",
            "Age": 82,
            "Gender": "F",
            "Total Gaps (Count)": 5,
            "Care Gap(s) (Gap Name)": "Controlling Blood Pressure; Medication Adherence",
            "Recommended Intervention": "SMS",
            "Gap Status": "Open",
            "Estimated Star Rating Improvement (Contribution)": "+0.0012",
        }])

        inserted = ResultPersistenceService.persist_final_recommendations(run_id, report_df)
        self.assertEqual(inserted, 1)

        records = _MOCK_STORAGE.get("final_recommendations", [])
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["run_id"], run_id)
        self.assertEqual(rec["s_no"], 1)
        self.assertEqual(rec["member_id"], "PT15580")
        self.assertEqual(rec["member_name"], "frances lewis")
        self.assertEqual(rec["age"], 82)
        self.assertEqual(rec["gender"], "F")
        self.assertEqual(rec["total_gaps"], 5)
        self.assertEqual(rec["care_gaps"], "Controlling Blood Pressure; Medication Adherence")
        self.assertEqual(rec["recommended_intervention"], "SMS")
        self.assertEqual(rec["gap_status"], "Open")
        self.assertEqual(rec["star_contribution"], "+0.0012")

    def test_05_star_rating_persistence_failure_fails_pipeline(self, _mock_cfg):
        """Verify that a failure during star rating persistence causes Stage 8 and pipeline to fail."""
        from backend.services.pipeline_service import register_run
        run_id = str(uuid.uuid4())
        raw_wb = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "data", "raw", "FILTERED_8_TABLES_WITH_NAMES.xlsx")
        )
        state = register_run(run_id=run_id, input_excel_path=raw_wb)

        # Mock persist_star_rating_contributions to raise RuntimeError
        with patch.object(
            ResultPersistenceService,
            "persist_star_rating_contributions",
            side_effect=RuntimeError("Supabase upsert into star_rating_contributions failed: schema error")
        ):
            _run_pipeline_thread(state)

        self.assertEqual(state.status, "failed")
        self.assertEqual(state.stages["star_rating_contribution"]["status"], "failed")
        self.assertIn("star_rating_contributions", state.error)

    def test_06_final_recommendation_persistence_failure_fails_pipeline(self, _mock_cfg):
        """Verify that a failure during final recommendation persistence causes Stage 9 and pipeline to fail."""
        from backend.services.pipeline_service import register_run
        run_id = str(uuid.uuid4())
        raw_wb = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "data", "raw", "FILTERED_8_TABLES_WITH_NAMES.xlsx")
        )
        state = register_run(run_id=run_id, input_excel_path=raw_wb)

        # Mock persist_final_recommendations to raise RuntimeError
        with patch.object(
            ResultPersistenceService,
            "persist_final_recommendations",
            side_effect=RuntimeError("Supabase upsert into final_recommendations failed: network timeout")
        ):
            _run_pipeline_thread(state)

        self.assertEqual(state.status, "failed")
        self.assertEqual(state.stages["final_report"]["status"], "failed")
        self.assertIn("final_recommendations", state.error)

    def test_07_full_pipeline_populates_all_result_tables(self, _mock_cfg):
        """
        Verify that a complete successful run populates all 6 result tables in mock storage:
        - care_gaps > 0
        - ml_predictions > 0
        - intervention_selections > 0
        - optimization_results == 250
        - star_rating_contributions > 0
        - final_recommendations == 250
        """
        from backend.services.pipeline_service import register_run
        run_id = str(uuid.uuid4())
        raw_wb = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "data", "raw", "FILTERED_8_TABLES_WITH_NAMES.xlsx")
        )
        state = register_run(run_id=run_id, input_excel_path=raw_wb)
        _run_pipeline_thread(state)

        self.assertEqual(state.status, "completed")
        self.assertEqual(state.stages["star_rating_contribution"]["status"], "completed")
        self.assertEqual(state.stages["final_report"]["status"], "completed")

        # Verify all 6 result tables in mock storage
        cg = [r for r in _MOCK_STORAGE.get("care_gaps", []) if r["run_id"] == run_id]
        ml = [r for r in _MOCK_STORAGE.get("ml_predictions", []) if r["run_id"] == run_id]
        inv = [r for r in _MOCK_STORAGE.get("intervention_selections", []) if r["run_id"] == run_id]
        opt = [r for r in _MOCK_STORAGE.get("optimization_results", []) if r["run_id"] == run_id]
        star = [r for r in _MOCK_STORAGE.get("star_rating_contributions", []) if r["run_id"] == run_id]
        final = [r for r in _MOCK_STORAGE.get("final_recommendations", []) if r["run_id"] == run_id]

        self.assertGreater(len(cg), 0)
        self.assertGreater(len(ml), 0)
        self.assertGreater(len(inv), 0)
        self.assertEqual(len(opt), 250)
        self.assertGreater(len(star), 0)
        self.assertEqual(len(final), 250)


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for Supabase client service, data sanitization, and run tracking.

These tests run in MOCK MODE only — they patch is_supabase_configured() to
return False so that no real Supabase connection is made. This keeps the tests
hermetic, reproducible, and independent of the live database state.
"""

import os
import sys
import math
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import backend.services.supabase_service as svc_module
from backend.services.supabase_service import (
    SupabaseService,
    sanitize_value,
    sanitize_record,
    sanitize_dataframe,
    _MOCK_STORAGE,
)


# Force mock mode for the entire test module regardless of local .env
@patch.object(svc_module, "is_supabase_configured", return_value=False)
class TestSupabaseService(unittest.TestCase):
    def setUp(self):
        # Reset mock storage before each test
        for k in list(_MOCK_STORAGE.keys()):
            _MOCK_STORAGE[k] = []

    def test_01_sanitize_nan_nat_inf_types(self, _mock_cfg):
        """Verify that NaN, NaT, Inf, None, and numpy types are sanitized to pure JSON types."""
        self.assertIsNone(sanitize_value(float("nan")))
        self.assertIsNone(sanitize_value(float("inf")))
        self.assertIsNone(sanitize_value(float("-inf")))
        self.assertIsNone(sanitize_value(np.nan))
        self.assertIsNone(sanitize_value(pd.NA))
        self.assertIsNone(sanitize_value(pd.NaT))
        self.assertIsNone(sanitize_value(None))

        # Valid values pass through unchanged
        self.assertEqual(sanitize_value(42), 42)
        self.assertEqual(sanitize_value(3.1415), 3.1415)
        self.assertEqual(sanitize_value("PT001"), "PT001")
        self.assertEqual(sanitize_value(True), True)

    def test_02_sanitize_record_and_dataframe(self, _mock_cfg):
        """Verify record and DataFrame sanitization."""
        raw_record = {
            "member_id": "M001",
            "age": 65,
            "dob": pd.Timestamp("1958-05-12"),
            "score": np.nan,
            "extra": float("nan"),
        }
        clean = sanitize_record(raw_record)
        self.assertEqual(clean["member_id"], "M001")
        self.assertEqual(clean["age"], 65)
        self.assertEqual(clean["dob"], "1958-05-12T00:00:00")
        self.assertIsNone(clean["score"])
        self.assertIsNone(clean["extra"])

        df = pd.DataFrame([raw_record, {"member_id": "M002", "age": 70, "score": 0.85}])
        clean_list = sanitize_dataframe(df)
        self.assertEqual(len(clean_list), 2)
        self.assertEqual(clean_list[1]["member_id"], "M002")
        self.assertEqual(clean_list[1]["score"], 0.85)

    def test_03_bulk_upsert_and_fetch(self, _mock_cfg):
        """Verify bulk upserting and fetching records with conflict resolution (mock mode)."""
        records = [
            {"plan_id": "H001", "plan_name": "Plan Alpha", "overall_star_rating": 4.5},
            {"plan_id": "H002", "plan_name": "Plan Beta", "overall_star_rating": 4.0},
        ]
        inserted = SupabaseService.bulk_upsert("plans", records, on_conflict="plan_id")
        self.assertEqual(inserted, 2)

        fetched = SupabaseService.fetch_all("plans")
        self.assertEqual(len(fetched), 2)

        # Upsert update for H001 and new H003
        update_records = [
            {"plan_id": "H001", "plan_name": "Plan Alpha Updated", "overall_star_rating": 5.0},
            {"plan_id": "H003", "plan_name": "Plan Gamma", "overall_star_rating": 3.5},
        ]
        SupabaseService.bulk_upsert("plans", update_records, on_conflict="plan_id")

        fetched_after = SupabaseService.fetch_all("plans")
        self.assertEqual(len(fetched_after), 3)
        h001 = [p for p in fetched_after if p["plan_id"] == "H001"][0]
        self.assertEqual(h001["plan_name"], "Plan Alpha Updated")
        self.assertEqual(h001["overall_star_rating"], 5.0)

    def test_04_pipeline_run_and_stages_tracking(self, _mock_cfg):
        """Verify pipeline run registration and stage progression (mock mode)."""
        import uuid
        run_id = str(uuid.uuid4())  # valid UUID — avoids the real Supabase UUID type check
        SupabaseService.register_pipeline_run(run_id, trigger_type="initial_upload", source_file_name="input.xlsx")

        runs = SupabaseService.fetch_all("pipeline_runs", filters={"id": run_id})
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "running")
        self.assertEqual(runs[0]["trigger_type"], "initial_upload")

        # Update stage
        SupabaseService.update_stage(run_id, "rule_engine", "running", "Identifying care gaps...")
        stages = SupabaseService.fetch_all("pipeline_stages", filters={"run_id": run_id})
        self.assertEqual(len(stages), 1)
        self.assertEqual(stages[0]["stage_key"], "rule_engine")
        self.assertEqual(stages[0]["status"], "running")

        # Complete stage and run
        SupabaseService.update_stage(run_id, "rule_engine", "completed", "6431 gaps identified", rows_processed=6431)
        SupabaseService.update_pipeline_run(run_id, status="completed")

        updated_runs = SupabaseService.fetch_all("pipeline_runs", filters={"id": run_id})
        self.assertEqual(updated_runs[0]["status"], "completed")

    def test_05_dataset_update_audit_log(self, _mock_cfg):
        """Verify dataset update audit logging (mock mode)."""
        SupabaseService.log_dataset_update(
            update_type="member_update",
            file_name="members_update.xlsx",
            affected_member_ids=["M001", "M002"],
            status="success",
        )
        logs = SupabaseService.fetch_all("dataset_update_logs")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["update_type"], "member_update")
        self.assertEqual(logs[0]["affected_members_count"], 2)


if __name__ == "__main__":
    unittest.main()

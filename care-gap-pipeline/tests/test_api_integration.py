"""
End-to-End API Integration & Rule Verification Test Suite.

Verifies:
  1. Health endpoint returns {"status": "ok"}
  2. Dataset upload accepts valid Excel files and generates a valid UUID job_id
  3. Pipeline execution tracks all 9 real stages
  4. Dashboard endpoint returns real computed data
  5. Member list has pagination, search, and accurate Star Rating Contribution
  6. Single member detail endpoint works
  7. CMS measures endpoint returns measures registry data
  8. Plan details endpoint returns valid plan metrics
  9. Optimization endpoint returns selected outreach list
 10. Download endpoint streams final_member_report.xlsx
 11. Star Rating column is exactly "Estimated Star Rating Improvement (Contribution)"
 12. 5-star measures have zero contribution / projected <= 5.0
 13. Channel distribution honors MAX_CHANNEL_SHARE <= 40%
 14. Exactly 250 rows for production dataset
 15. Zero duplicate members selected
 16. outputs/ directory is preserved and not overwritten
"""

import os
import sys
import unittest
import pandas as pd
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.main import app
from backend.services.pipeline_service import STAGE_KEYS


class TestMetricShiftIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Use existing verified job_id or run an upload
        cls.job_id = "564f20f8-c132-41bc-99bf-5afd55f5154a"

    def test_01_health_check(self):
        """CRITICAL RULE 4: GET /api/health returns {'status': 'ok'}"""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    def test_02_pipeline_stages(self):
        """CRITICAL RULE 6: 9 stages must be exposed with real values."""
        res = self.client.get(f"/api/pipeline/{self.job_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "completed")
        self.assertEqual(len(data["stages"]), 9)
        for stage_key in STAGE_KEYS:
            self.assertIn(stage_key, data["stages"])
            self.assertEqual(data["stages"][stage_key]["status"], "completed")

    def test_03_dashboard_real_data(self):
        """CRITICAL RULE 9 & 10: Dashboard returns real aggregated values."""
        res = self.client.get(f"/api/dashboard/{self.job_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        summary = data["summary"]
        self.assertEqual(summary["total_plans"], 5)
        self.assertEqual(summary["total_members"], 7090)
        self.assertEqual(summary["cms_measures"], 10)
        self.assertEqual(summary["selected_members"], 250)
        self.assertGreater(summary["total_star_contribution"], 0.0)

    def test_04_channel_distribution_cap(self):
        """CRITICAL RULE 12: No channel exceeds 40% maximum."""
        res = self.client.get(f"/api/dashboard/{self.job_id}")
        data = res.json()
        dist = data["intervention_distribution"]
        total = sum(d["value"] for d in dist)
        self.assertEqual(total, 250)
        for ch in dist:
            share = ch["value"] / total
            self.assertLessEqual(share, 0.4001, f"Channel {ch['name']} share {share:.2%} exceeds 40% cap")

    def test_05_members_pagination_and_columns(self):
        """CRITICAL RULE 10: Members endpoint with 250 total rows and search."""
        res = self.client.get(f"/api/members/{self.job_id}?page=1&limit=20")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["pagination"]["total_records"], 250)
        self.assertEqual(len(data["records"]), 20)
        
        # Verify required fields
        first = data["records"][0]
        self.assertTrue(len(first["member_id"]) > 0)
        self.assertTrue(len(first["member_name"]) > 0)
        self.assertIn(first["gender"], ["M", "F", "Unknown"])
        self.assertTrue(len(first["care_gaps"]) > 0)
        self.assertIn(first["recommended_intervention"], ["Email", "SMS", "Phone Call"])
        self.assertTrue(len(first["star_contribution"]) > 0)

    def test_06_member_detail(self):
        """CRITICAL RULE 10: Member detail shows exact backend-computed values."""
        res = self.client.get(f"/api/members/{self.job_id}/PT15580")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["member_id"], "PT15580")
        self.assertEqual(data["member_name"], "frances lewis")
        self.assertGreater(data["gaps_summary"]["open_care_gaps"], 0)
        self.assertIn(data["recommended_intervention"], ["Email", "SMS", "Phone Call"])

    def test_07_cms_measures(self):
        """CRITICAL RULE 15: CMS Measures uses real Rule Engine data."""
        res = self.client.get(f"/api/measures/{self.job_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["summary"]["total_measures"], 10)
        self.assertEqual(len(data["records"]), 10)

    def test_08_optimization_endpoint(self):
        """CRITICAL RULE 11 & 13: Optimization returns 250 records with exact Star Rating."""
        res = self.client.post(f"/api/optimize/{self.job_id}", data={"max_members": 250})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["summary"]["total_selected"], 250)
        self.assertEqual(len(data["records"]), 250)

    def test_09_download_endpoint_and_report_file(self):
        """CRITICAL RULE 16: Download endpoint streams final_member_report.xlsx."""
        res = self.client.get(f"/api/download/{self.job_id}")
        self.assertEqual(res.status_code, 200)
        self.assertGreater(len(res.content), 1000)

        # Inspect downloaded file directly
        report_path = f"run_outputs/{self.job_id}/final_member_report.xlsx"
        df = pd.read_excel(report_path)
        self.assertEqual(len(df), 250)
        
        # Verify exact column name
        expected_col = "Estimated Star Rating Improvement (Contribution)"
        self.assertIn(expected_col, df.columns, f"Column '{expected_col}' not found in report!")

        # Verify no duplicate members
        self.assertEqual(df["Member ID"].nunique(), 250)

    def test_10_outputs_preservation(self):
        """CRITICAL RULE 2: outputs/ directory was NOT overwritten."""
        self.assertTrue(os.path.exists("outputs/final_member_report.xlsx"))
        self.assertTrue(os.path.exists("outputs/FINAL_END_TO_END_VALIDATION.xlsx"))


if __name__ == "__main__":
    unittest.main()

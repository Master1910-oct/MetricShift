"""
Comprehensive Test Suite for Care-Gap Pipeline & Guardrails.
Covers:
  TEST 1 — Candidate generation (1 row -> Email, SMS, Phone Call)
  TEST 2 — Historical intervention preservation
  TEST 3 — ML inference (3 candidates -> 3 valid probabilities [0, 1])
  TEST 4 — One patient / one final intervention in optimizer
  TEST 5 — Channel capacity (<= 40% per channel)
  TEST 6 — No "No previous intervention" in final recommendations
  TEST 7 — Cost preference within 1% margin
  TEST 8 — Meaningful probability difference (> 1% margin)
  TEST 9 — Unit & Integration test coverage
"""

import os
import sys
import unittest
import numpy as np
import pandas as pd

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pipeline.intervention_candidates import generate_intervention_candidates, ACTIONABLE_CHANNELS
from pipeline.calibration import calibrate_channel_bias
from pipeline.intervention_selection import select_best_interventions
from pipeline.adapters import ml_to_optimizer_input, compute_performance_opportunity
from ml_model.infer import run_inference
from optimizer import (
    run_optimizer,
    build_and_solve,
    apply_cost_efficiency_preference,
    compute_final_score,
    aggregate_member_intervention,
    compute_gap_impacts,
    filter_eligible_open,
    validate_data,
    MAX_CHANNEL_SHARE,
    SELECTION_MARGIN,
    CHANNEL_COST_RANK
)


class TestCareGapPipelineGuardrails(unittest.TestCase):
    """Test suite covering candidate generation, calibration, cost-preference, capacity, and uniqueness."""

    def setUp(self):
        """Set up synthetic sample data."""
        self.sample_row = pd.DataFrame([{
            "patient_id": "PT99999",
            "member_name": "Test Patient",
            "plan_id": "P001",
            "care_gap": "Medication Adherence for Diabetes Medications",
            "intervention_type": "No previous intervention",
            "age": 68,
            "gender": "F",
            "condition": "Diabetes",
            "condition_code": "E11",
            "part": "D",
            "measure_id": "D08",
            "measure_type": "Intermediate Outcome",
            "measure_weight": 3.0,
            "service_name": "Diabetes Adherence",
            "test_name": "Refill",
            "performance_value": 0.70,
            "measure_star": 3.5,
            "enrollment_status": "Active",
            "enrollment_tenure_days": 365,
            "missed_service_count": 0,
            "completed_service_count": 2,
            "days_since_last_service": 30,
            "previous_intervention_count": 0,
            "previous_success_rate": 0.0,
            "previous_phone_count": 0,
            "phone_success_rate": 0.0,
            "previous_sms_count": 0,
            "sms_success_rate": 0.0,
            "previous_email_count": 0,
            "email_success_rate": 0.0,
            "active_medication_count": 2,
            "missed_refill_count": 0,
            "medication_adherence_rate": 0.85,
            "days_since_last_fill": 25,
            "refill_number": 3
        }])

    def test_1_candidate_generation(self):
        """TEST 1: 1 input row must produce 3 actionable candidates (Email, SMS, Phone Call)."""
        candidates = generate_intervention_candidates(self.sample_row)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(sorted(candidates["intervention_type"].tolist()), sorted(["Email", "Phone Call", "SMS"]))

    def test_2_historical_intervention_preservation(self):
        """TEST 2: Historical intervention information must be preserved in historical_intervention_type and counts."""
        candidates = generate_intervention_candidates(self.sample_row)
        self.assertTrue("historical_intervention_type" in candidates.columns)
        self.assertTrue((candidates["historical_intervention_type"] == "No previous intervention").all())
        self.assertTrue((candidates["previous_intervention_count"] == 0).all())

    def test_3_ml_inference_probabilities(self):
        """TEST 3: ML inference produces valid probabilities in [0, 1] for all candidates."""
        candidates = generate_intervention_candidates(self.sample_row)
        ml_preds = run_inference(candidates)
        self.assertEqual(len(ml_preds), 3)
        self.assertTrue((ml_preds["probability_score"] >= 0.0).all())
        self.assertTrue((ml_preds["probability_score"] <= 1.0).all())
        self.assertTrue((ml_preds["uncertainity_range_lower"] <= ml_preds["uncertainity_range_upper"]).all())

    def test_4_one_patient_one_intervention(self):
        """TEST 4: Optimizer never selects more than 1 intervention for the same patient."""
        # Create 10 patients with 3 candidate channels each
        rows = []
        for i in range(10):
            p_id = f"PT0000{i}"
            for ch in ["Email", "SMS", "Phone Call"]:
                rows.append({
                    "patient_id": p_id,
                    "member_id": p_id,
                    "plan_id": "P001",
                    "member_name": f"Member {i}",
                    "age": 70,
                    "gender": "M",
                    "care_gap": "Diabetes Care",
                    "intervention_type": ch,
                    "probability_score": 0.80 + np.random.uniform(-0.05, 0.05),
                    "calibrated_probability": 0.80 + np.random.uniform(-0.05, 0.05),
                    "uncertainty_lower": 0.75,
                    "uncertainty_upper": 0.85,
                    "measure_id": "C12",
                    "measure_weight": 3.0,
                    "performance_opportunity": 0.90,
                    "eligible": 1,
                    "gap_open": 1
                })
        cand_df = pd.DataFrame(rows)
        best_df, _, _ = select_best_interventions(cand_df)
        opt_df = ml_to_optimizer_input(best_df, best_df)
        selected = run_optimizer(opt_df, max_selected_members=5)
        self.assertEqual(len(selected), 5)
        self.assertEqual(selected["member_id"].nunique(), 5)
        # Check no duplicate patient in recommendations
        self.assertEqual(len(selected["member_id"]), len(set(selected["member_id"])))

    def test_5_channel_capacity_40_percent(self):
        """TEST 5: For 250 selected members, each channel count <= 100 (40% capacity)."""
        # Create 300 patients with 3 channels each
        rows = []
        for i in range(300):
            p_id = f"PT{i:05d}"
            for ch in ["Email", "SMS", "Phone Call"]:
                # Near-tie probabilities across channels to test diversity allocation
                prob = 0.85 if ch == "Phone Call" else 0.849
                rows.append({
                    "patient_id": p_id,
                    "member_id": p_id,
                    "plan_id": "P001",
                    "member_name": f"Member {i}",
                    "age": 70,
                    "gender": "M",
                    "care_gap": "Diabetes Care",
                    "intervention_type": ch,
                    "probability_score": prob,
                    "calibrated_probability": prob,
                    "uncertainty_lower": prob - 0.05,
                    "uncertainty_upper": prob + 0.05,
                    "measure_id": "C12",
                    "measure_weight": 3.0,
                    "performance_opportunity": 0.90,
                    "eligible": 1,
                    "gap_open": 1
                })
        cand_df = pd.DataFrame(rows)
        best_df, _, _ = select_best_interventions(cand_df)
        opt_df = ml_to_optimizer_input(best_df, best_df)
        selected = run_optimizer(opt_df, max_selected_members=250)
        self.assertEqual(len(selected), 250)
        max_allowed = int(np.ceil(250 * MAX_CHANNEL_SHARE))
        channel_counts = selected["recommended_intervention"].value_counts()
        for ch, count in channel_counts.items():
            self.assertLessEqual(count, max_allowed, f"Channel {ch} exceeded 40% cap: {count} > {max_allowed}")

    def test_6_no_no_previous_intervention_in_recommendation(self):
        """TEST 6: 'No previous intervention' must never appear as a recommended intervention."""
        # Use synthetic rule engine rows with historical 'No previous intervention'
        cands = generate_intervention_candidates(self.sample_row)
        ml_df = run_inference(cands)
        opt_input = ml_to_optimizer_input(cands, ml_df)
        selected = run_optimizer(opt_input, max_selected_members=1)
        self.assertEqual(len(selected), 1)
        rec = selected.iloc[0]["recommended_intervention"]
        self.assertIn(rec, ["Email", "SMS", "Phone Call"])
        self.assertNotEqual(rec, "No previous intervention")

    def test_7_cost_preference_within_margin(self):
        """TEST 7: If Email=0.851, SMS=0.855, Phone=0.860 (within 0.01 margin), SMS is preferred over Phone Call."""
        df = pd.DataFrame([
            {
                "member_id": "PT001",
                "plan_id": "P001",
                "member_name": "Patient 1",
                "age": 70,
                "gender": "M",
                "care_gaps": "Diabetes Care",
                "gap_count": 1,
                "intervention_type": "Phone Call",
                "robust_quality": 3.0,
                "closure_probability": 0.860,
                "norm_robust_quality": 1.0,
                "norm_closure_probability": 0.860,
                "final_score": 0.70 * 1.0 + 0.30 * 0.860,
            },
            {
                "member_id": "PT001",
                "plan_id": "P001",
                "member_name": "Patient 1",
                "age": 70,
                "gender": "M",
                "care_gaps": "Diabetes Care",
                "gap_count": 1,
                "intervention_type": "SMS",
                "robust_quality": 3.0,
                "closure_probability": 0.855,
                "norm_robust_quality": 1.0,
                "norm_closure_probability": 0.855,
                "final_score": 0.70 * 1.0 + 0.30 * 0.855,
            },
            {
                "member_id": "PT001",
                "plan_id": "P001",
                "member_name": "Patient 1",
                "age": 70,
                "gender": "M",
                "care_gaps": "Diabetes Care",
                "gap_count": 1,
                "intervention_type": "Email",
                "robust_quality": 3.0,
                "closure_probability": 0.740,  # outside margin (> 0.01 from 0.860)
                "norm_robust_quality": 1.0,
                "norm_closure_probability": 0.740,
                "final_score": 0.70 * 1.0 + 0.30 * 0.740,
            }
        ])
        cost_df = apply_cost_efficiency_preference(df, margin=SELECTION_MARGIN)
        # SMS is cheaper than Phone Call and within 0.01 of 0.860, so SMS score should exceed Phone Call score
        sms_score = cost_df[cost_df["intervention_type"] == "SMS"]["final_score"].values[0]
        phone_score = cost_df[cost_df["intervention_type"] == "Phone Call"]["final_score"].values[0]
        self.assertGreater(sms_score, phone_score, "SMS should be preferred over Phone Call when within 0.01 margin")

    def test_8_meaningful_probability_difference(self):
        """TEST 8: If Email=0.70, SMS=0.78, Phone=0.90 (diff > 0.01), Phone Call remains preferred."""
        df = pd.DataFrame([
            {
                "member_id": "PT001",
                "plan_id": "P001",
                "member_name": "Patient 1",
                "age": 70,
                "gender": "M",
                "care_gaps": "Diabetes Care",
                "gap_count": 1,
                "intervention_type": "Phone Call",
                "robust_quality": 3.0,
                "closure_probability": 0.900,
                "norm_robust_quality": 1.0,
                "norm_closure_probability": 0.900,
                "final_score": 0.70 * 1.0 + 0.30 * 0.900,
            },
            {
                "member_id": "PT001",
                "plan_id": "P001",
                "member_name": "Patient 1",
                "age": 70,
                "gender": "M",
                "care_gaps": "Diabetes Care",
                "gap_count": 1,
                "intervention_type": "SMS",
                "robust_quality": 3.0,
                "closure_probability": 0.780,
                "norm_robust_quality": 1.0,
                "norm_closure_probability": 0.780,
                "final_score": 0.70 * 1.0 + 0.30 * 0.780,
            },
            {
                "member_id": "PT001",
                "plan_id": "P001",
                "member_name": "Patient 1",
                "age": 70,
                "gender": "M",
                "care_gaps": "Diabetes Care",
                "gap_count": 1,
                "intervention_type": "Email",
                "robust_quality": 3.0,
                "closure_probability": 0.700,
                "norm_robust_quality": 1.0,
                "norm_closure_probability": 0.700,
                "final_score": 0.70 * 1.0 + 0.30 * 0.700,
            }
        ])
        cost_df = apply_cost_efficiency_preference(df, margin=SELECTION_MARGIN)
        phone_score = cost_df[cost_df["intervention_type"] == "Phone Call"]["final_score"].values[0]
        sms_score = cost_df[cost_df["intervention_type"] == "SMS"]["final_score"].values[0]
        self.assertGreater(phone_score, sms_score, "Phone Call should remain preferred when difference exceeds 0.01")


if __name__ == "__main__":
    unittest.main()

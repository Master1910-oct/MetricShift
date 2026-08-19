"""
Unit and Integration Tests for Pipeline Adapter Layer and Optimizer Integration.
Tests schema validity, null safety, constraint verification, and end-to-end optimizer compatibility.
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pipeline.adapters import (
    ml_to_optimizer_input,
    compute_performance_opportunity,
    PERFORMANCE_OPPORTUNITY_FORMULA
)
from optimizer import (
    REQUIRED_COLUMNS,
    validate_data,
    filter_eligible_open,
    compute_gap_impacts,
    aggregate_member_intervention,
    compute_final_score,
    build_and_solve,
    run_optimizer
)


class TestAdaptersAndOptimizer(unittest.TestCase):
    """Test suite for adapter transformations and optimizer compatibility."""

    def setUp(self):
        """Build synthetic test data matching the schemas of Rule Engine, ML Model, and Performance."""
        # 1. Synthetic Rule Engine DataFrame
        self.patient_ids = ["PT00001", "PT00001", "PT00002", "PT00003", "PT00004"]
        self.member_names = ["John Doe", "John Doe", "Jane Smith", "Robert Brown", "Alice White"]
        self.plan_ids = ["P001", "P001", "P001", "P002", "P003"]
        self.care_gaps = [
            "Medication Adherence for Diabetes Medications",
            "Controlling Blood Pressure",
            "Kidney Health Evaluation for Patients with Diabetes",
            "Medication Adherence for Hypertension (RAS antagonists)",
            "Statin Use in Persons with Diabetes (SUPD)"
        ]
        self.measure_ids = ["D08", "C14", "C13", "D09", "D12"]
        self.intervention_types = ["Phone Call", "SMS", "Email", "Phone Call", "SMS"]

        self.synthetic_rule_engine_df = pd.DataFrame({
            "patient_id": self.patient_ids,
            "member_name": self.member_names,
            "plan_id": self.plan_ids,
            "care_gap": self.care_gaps,
            "age": [65, 65, 72, 58, 61],
            "gender": ["M", "M", "F", "M", "F"],
            "condition": ["Diabetes", "Hypertension", "Diabetes", "Hypertension", "Diabetes"],
            "condition_code": ["E11", "I10", "E11", "I10", "E11"],
            "part": ["D", "C", "C", "D", "D"],
            "measure_id": self.measure_ids,
            "measure_type": ["Intermediate Outcome", "Outcome", "Process", "Intermediate Outcome", "Process"],
            "measure_weight": [3.0, 3.0, 1.0, 3.0, 1.0],
            "service_name": ["Diabetes Adherence", "Blood Pressure Check", "Kidney Evaluation", "Hypertension Adherence", "Statin Fill"],
            "test_name": ["Refill", "Systolic/Diastolic Reading", "eGFR Test", "Refill", "Prescription Fill"],
            "performance_value": [0.75, 0.60, 0.85, 0.70, 0.80],
            "measure_star": [3.5, 3.0, 4.0, 3.5, 4.0],
            "enrollment_status": ["Active", "Active", "Active", "Active", "Active"],
            "enrollment_tenure_days": [365, 365, 730, 180, 500],
            "missed_service_count": [1, 0, 2, 1, 0],
            "completed_service_count": [3, 2, 4, 1, 3],
            "days_since_last_service": [45, 90, 30, 60, 15],
            "previous_intervention_count": [2, 1, 3, 0, 1],
            "previous_success_rate": [0.5, 1.0, 0.67, 0.0, 1.0],
            "previous_phone_count": [1, 0, 2, 0, 0],
            "phone_success_rate": [1.0, 0.0, 0.5, 0.0, 0.0],
            "previous_sms_count": [1, 1, 0, 0, 1],
            "sms_success_rate": [0.0, 1.0, 0.0, 0.0, 1.0],
            "previous_email_count": [0, 0, 1, 0, 0],
            "email_success_rate": [0.0, 0.0, 1.0, 0.0, 0.0],
            "active_medication_count": [2, 1, 3, 1, 2],
            "missed_refill_count": [1, 0, 2, 1, 0],
            "medication_adherence_rate": [0.80, 0.90, 0.65, 0.75, 0.85],
            "days_since_last_fill": [35, 60, 25, 40, 20],
            "refill_number": [3, 4, 2, 1, 5],
            "intervention_type": self.intervention_types
        })

        # 2. Synthetic ML Output DataFrame
        self.synthetic_ml_output_df = pd.DataFrame({
            "patient_id": self.patient_ids,
            "plan_id": self.plan_ids,
            "care_gap": self.care_gaps,
            "intervention_type": self.intervention_types,
            "probability_score": [0.82, 0.74, 0.65, 0.88, 0.79],
            "calibrated_probability_score": [0.82, 0.74, 0.65, 0.88, 0.79],
            "uncertainity_range_lower": [0.78, 0.70, 0.60, 0.85, 0.75],
            "uncertainity_range_upper": [0.86, 0.78, 0.70, 0.91, 0.83]
        })

        # 3. Synthetic Performance DataFrame
        self.synthetic_performance_df = pd.DataFrame({
            "plan_id": ["P001", "P001", "P001", "P002", "P003"],
            "measure_id": ["D08", "C14", "C13", "D09", "D12"],
            "performance_value": [0.75, 0.60, 0.85, 0.70, 0.80],
            "weight": [3.0, 3.0, 1.0, 3.0, 1.0]
        })

    def test_compute_performance_opportunity(self):
        """Test performance opportunity calculation formula."""
        self.assertAlmostEqual(compute_performance_opportunity(0.75, 3.0), (1 - 0.75) * 3.0)
        self.assertAlmostEqual(compute_performance_opportunity(0.0, 1.0), 1.0)
        self.assertAlmostEqual(compute_performance_opportunity(1.0, 3.0), 0.0)

    def test_adapter_schema_and_null_checks(self):
        """Test ml_to_optimizer_input() produces valid schema without nulls."""
        opt_input = ml_to_optimizer_input(
            rule_engine_df=self.synthetic_rule_engine_df,
            ml_output_df=self.synthetic_ml_output_df,
            performance_df=self.synthetic_performance_df
        )

        # 1. Assert all 15 required columns exist
        for col in REQUIRED_COLUMNS:
            self.assertIn(col, opt_input.columns, f"Missing required column: {col}")

        # 2. Assert no required columns contain null values
        null_counts = opt_input[REQUIRED_COLUMNS].isna().sum()
        self.assertEqual(null_counts.sum(), 0, f"Found null values in optimizer input: {null_counts.to_dict()}")

        # 3. Assert performance_opportunity is within valid non-negative range
        self.assertTrue((opt_input["performance_opportunity"] >= 0).all(), "performance_opportunity has negative values")

    def test_optimizer_validation_and_solve_compatibility(self):
        """Test adapter output successfully passes optimizer validation and MILP solve."""
        opt_input = ml_to_optimizer_input(
            rule_engine_df=self.synthetic_rule_engine_df,
            ml_output_df=self.synthetic_ml_output_df,
            performance_df=self.synthetic_performance_df
        )

        # 1. Validate data constraints
        validated = validate_data(opt_input)
        self.assertEqual(len(validated), len(opt_input))

        # 2. Filter eligible and open gaps
        filtered = filter_eligible_open(validated)
        self.assertEqual(len(filtered), len(opt_input))

        # 3. Compute gap impacts
        impact = compute_gap_impacts(filtered)
        self.assertIn("quality_impact", impact.columns)
        self.assertIn("robust_quality_impact", impact.columns)

        # 4. Aggregate per member-intervention
        agg = aggregate_member_intervention(impact)
        self.assertEqual(agg["member_id"].nunique(), 4)  # 4 unique patients in synthetic data

        # 5. Multi-objective scoring
        scored = compute_final_score(agg)
        self.assertIn("final_score", scored.columns)

        # 6. Build and solve MILP
        selected = build_and_solve(scored, max_members=2)
        self.assertLessEqual(len(selected), 2)
        self.assertIn("recommended_intervention", selected.columns)
        self.assertIn("robust_quality", selected.columns)

    def test_end_to_end_run_optimizer(self):
        """Test run_optimizer() directly on adapter output."""
        opt_input = ml_to_optimizer_input(
            rule_engine_df=self.synthetic_rule_engine_df,
            ml_output_df=self.synthetic_ml_output_df,
            performance_df=self.synthetic_performance_df
        )
        selected_df = run_optimizer(opt_input, max_selected_members=2)
        self.assertEqual(len(selected_df), 2)
        self.assertEqual(selected_df["member_id"].nunique(), 2)


if __name__ == "__main__":
    unittest.main()

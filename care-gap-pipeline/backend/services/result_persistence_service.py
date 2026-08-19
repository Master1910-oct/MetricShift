"""
Pipeline results persistence service for Metric Shift.

Persists DataFrames generated during the 9-stage pipeline execution into
run-isolated Supabase result tables:
- care_gaps (Rule Engine)
- ml_predictions (ML Model - all 3 candidate interventions)
- intervention_selections (Best chosen intervention)
- optimization_results (MILP selected members)
- star_rating_contributions (Estimated Star Rating Contribution details)
- final_recommendations (Final Member Report)

CRITICAL:
- Uses bulk batch operations.
- Isolated strictly by run_id (UUID).
- Does not modify input pipeline DataFrames.
- Preserves exact columns and calculations from validated pipeline.
"""

import uuid
from typing import Dict, List, Any, Optional
import pandas as pd

from backend.services.supabase_service import SupabaseService, sanitize_dataframe, sanitize_value


class ResultPersistenceService:
    @staticmethod
    def persist_care_gaps(run_id: str, rule_engine_df: pd.DataFrame) -> int:
        """Persist valid care gaps identified by Rule Engine."""
        if rule_engine_df is None or rule_engine_df.empty:
            return 0

        records = []
        for _, row in rule_engine_df.iterrows():
            pat_id = str(row.get("patient_id", row.get("member_id", ""))).strip()
            records.append({
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "patient_id": pat_id,
                "member_id": pat_id,
                "plan_id": sanitize_value(row.get("plan_id")),
                "care_gap": sanitize_value(row.get("care_gap")),
                "measure_id": sanitize_value(row.get("measure_id", row.get("official_measure_id"))),
                "gap_status": sanitize_value(row.get("gap_status", "Open")),
                "intervention_type": sanitize_value(row.get("intervention_type")),
            })

        return SupabaseService.bulk_upsert("care_gaps", records)

    @staticmethod
    def persist_ml_predictions(run_id: str, ml_output_df: pd.DataFrame) -> int:
        """Persist ML predictions for ALL 3 candidate intervention types."""
        if ml_output_df is None or ml_output_df.empty:
            return 0

        records = []
        for _, row in ml_output_df.iterrows():
            pat_id = str(row.get("patient_id", row.get("member_id", ""))).strip()
            records.append({
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "patient_id": pat_id,
                "member_id": pat_id,
                "plan_id": sanitize_value(row.get("plan_id")),
                "care_gap": sanitize_value(row.get("care_gap")),
                "intervention_type": str(row.get("intervention_type", "")).strip(),
                "probability_score": sanitize_value(row.get("probability_score")),
                "calibrated_probability": sanitize_value(row.get("calibrated_probability", row.get("probability_score"))),
            })

        return SupabaseService.bulk_upsert("ml_predictions", records)

    @staticmethod
    def persist_intervention_selections(
        run_id: str,
        best_cands_df: pd.DataFrame,
        audit_df: Optional[pd.DataFrame] = None,
    ) -> int:
        """Persist selected best interventions per care gap."""
        if best_cands_df is None or best_cands_df.empty:
            return 0

        decision_map = {}
        if audit_df is not None and not audit_df.empty:
            for _, row in audit_df.iterrows():
                key = (
                    str(row.get("patient_id", "")).strip(),
                    str(row.get("care_gap", "")).strip(),
                )
                decision_map[key] = str(row.get("decision_type", row.get("selection_reason", "")))

        records = []
        for _, row in best_cands_df.iterrows():
            pat_id = str(row.get("patient_id", row.get("member_id", ""))).strip()
            cg = str(row.get("care_gap", "")).strip()
            records.append({
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "patient_id": pat_id,
                "member_id": pat_id,
                "plan_id": sanitize_value(row.get("plan_id")),
                "care_gap": cg,
                "intervention_type": str(row.get("intervention_type", "")).strip(),
                "probability_score": sanitize_value(row.get("probability_score")),
                "calibrated_probability": sanitize_value(row.get("calibrated_probability", row.get("probability_score"))),
                "selection_decision": decision_map.get((pat_id, cg), "Selected"),
            })

        return SupabaseService.bulk_upsert("intervention_selections", records)

    @staticmethod
    def persist_optimization_results(run_id: str, selected_df: pd.DataFrame) -> int:
        """Persist MILP optimizer selected member output."""
        if selected_df is None or selected_df.empty:
            return 0

        records = []
        for _, row in selected_df.iterrows():
            records.append({
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "member_id": str(row.get("member_id", "")).strip(),
                "member_name": sanitize_value(row.get("member_name")),
                "age": sanitize_value(row.get("age")),
                "gender": sanitize_value(row.get("gender")),
                "gap_count": sanitize_value(row.get("gap_count")),
                "care_gaps": sanitize_value(row.get("care_gaps")),
                "recommended_intervention": str(row.get("recommended_intervention", "")).strip(),
                "gap_status": sanitize_value(row.get("gap_status", "Open")),
                "closure_probability": sanitize_value(row.get("closure_probability")),
                "robust_quality": sanitize_value(row.get("robust_quality")),
            })

        return SupabaseService.bulk_upsert("optimization_results", records)

    @staticmethod
    def persist_star_rating_contributions(run_id: str, audit_df: pd.DataFrame) -> int:
        """
        Persist Star Rating calculation details from technical audit.
        
        Maps actual columns from compute_project_estimated_star_contribution():
        - "Member ID" -> member_id
        - "Plan ID" -> plan_id
        - "Care Gap" -> care_gap
        - "Measure ID" -> measure_id
        - "Current Measure Star" -> current_measure_star
        - "Projected Measure Star" -> projected_measure_star
        - "Measure Weight" -> measure_weight
        - "Closure Probability" -> closure_probability
        - "Estimated Star Contribution" -> estimated_contribution / plan_star_contribution
        - "Current Performance" -> performance_value (if column exists)
        - "Denominator" -> denominator (if column exists and value not None)
        """
        if audit_df is None or audit_df.empty:
            return 0

        cols = SupabaseService.get_table_columns("star_rating_contributions")
        records = []
        for _, row in audit_df.iterrows():
            star_val = sanitize_value(row.get(
                "Estimated Star Contribution",
                row.get("estimated_contribution", row.get("plan_star_contribution", row.get("star_contribution")))
            ))
            rec: Dict[str, Any] = {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "member_id": str(row.get("Member ID", row.get("member_id", ""))).strip(),
                "plan_id": sanitize_value(row.get("Plan ID", row.get("plan_id"))),
                "care_gap": sanitize_value(row.get("Care Gap", row.get("care_gap"))),
                "measure_id": sanitize_value(row.get("Measure ID", row.get("measure_id"))),
                "current_measure_star": sanitize_value(row.get("Current Measure Star", row.get("current_measure_star", row.get("measure_star")))),
                "projected_measure_star": sanitize_value(row.get("Projected Measure Star", row.get("projected_measure_star"))),
                "measure_weight": sanitize_value(row.get("Measure Weight", row.get("measure_weight", row.get("weight")))),
                "closure_probability": sanitize_value(row.get("Closure Probability", row.get("closure_probability", row.get("probability_score")))),
            }

            # Map star contribution to appropriate column
            if cols and "estimated_contribution" in cols:
                rec["estimated_contribution"] = star_val
            elif cols and "plan_star_contribution" in cols:
                rec["plan_star_contribution"] = star_val
            else:
                rec["estimated_contribution"] = star_val
                rec["plan_star_contribution"] = star_val

            # Performance value (if column exists in schema or offline)
            perf_val = sanitize_value(row.get("Current Performance", row.get("performance_value", row.get("Current Performance Value"))))
            if (not cols) or ("performance_value" in cols):
                if perf_val is not None:
                    rec["performance_value"] = perf_val

            # Denominator (if column exists in schema or offline)
            denom_val = sanitize_value(row.get("Denominator", row.get("denominator")))
            if (not cols) or ("denominator" in cols):
                if denom_val is not None:
                    rec["denominator"] = denom_val

            # Filter rec to only columns that exist on the table if cols is known
            if cols:
                rec = {k: v for k, v in rec.items() if k in cols}

            records.append(rec)

        return SupabaseService.bulk_upsert("star_rating_contributions", records)

    @staticmethod
    def persist_final_recommendations(run_id: str, final_report_df: pd.DataFrame) -> int:
        """
        Persist final member report with exact column preservation.
        
        Maps actual columns from generate_final_member_report():
        - "S. No." -> s_no / "S. No."
        - "Member ID" -> member_id / "Member ID"
        - "Member Name" -> member_name / "Member Name"
        - "Age" -> age / "Age"
        - "Gender" -> gender / "Gender"
        - "Total Gaps (Count)" -> total_gaps / "Total Gaps (Count)"
        - "Care Gap(s) (Gap Name)" -> care_gaps / "Care Gap(s) (Gap Name)"
        - "Recommended Intervention" -> recommended_intervention / "Recommended Intervention"
        - "Gap Status" -> gap_status / "Gap Status"
        - "Estimated Star Rating Improvement (Contribution)" -> star_contribution / "Estimated Star Rating Improvement (Contribution)"
        """
        if final_report_df is None or final_report_df.empty:
            return 0

        cols = SupabaseService.get_table_columns("final_recommendations")
        contrib_col = "Estimated Star Rating Improvement (Contribution)"
        records = []
        for i, (_, row) in enumerate(final_report_df.iterrows(), start=1):
            s_no = sanitize_value(row.get("S. No.", row.get("S.No.", row.get("s_no", row.get("s_no.", i)))))
            contrib_val = str(row.get(contrib_col, row.get("star_contribution", row.get("Star Contribution", "+0.0000")))).strip()

            if cols and "Member ID" in cols:
                # Target table uses human-readable column names with spaces
                rec: Dict[str, Any] = {
                    "id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "S. No.": s_no,
                    "Member ID": str(row.get("Member ID", row.get("member_id", ""))).strip(),
                    "Member Name": sanitize_value(row.get("Member Name", row.get("member_name"))),
                    "Age": sanitize_value(row.get("Age", row.get("age"))),
                    "Gender": sanitize_value(row.get("Gender", row.get("gender"))),
                    "Total Gaps (Count)": sanitize_value(row.get("Total Gaps (Count)", row.get("Total Gaps", row.get("total_gaps")))),
                    "Care Gap(s) (Gap Name)": sanitize_value(row.get("Care Gap(s) (Gap Name)", row.get("Care Gap(s)", row.get("care_gaps", row.get("care_gap"))))),
                    "Recommended Intervention": str(row.get("Recommended Intervention", row.get("recommended_intervention", ""))).strip(),
                    "Gap Status": sanitize_value(row.get("Gap Status", row.get("gap_status", "Open"))),
                    "Estimated Star Rating Improvement (Contribution)": contrib_val,
                }
            else:
                # Target table uses snake_case column names (or offline/mock)
                rec = {
                    "id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "s_no": s_no,
                    "member_id": str(row.get("Member ID", row.get("member_id", ""))).strip(),
                    "member_name": sanitize_value(row.get("Member Name", row.get("member_name"))),
                    "age": sanitize_value(row.get("Age", row.get("age"))),
                    "gender": sanitize_value(row.get("Gender", row.get("gender"))),
                    "total_gaps": sanitize_value(row.get("Total Gaps (Count)", row.get("Total Gaps", row.get("total_gaps")))),
                    "care_gaps": sanitize_value(row.get("Care Gap(s) (Gap Name)", row.get("Care Gap(s)", row.get("care_gaps", row.get("care_gap"))))),
                    "recommended_intervention": str(row.get("Recommended Intervention", row.get("recommended_intervention", ""))).strip(),
                    "gap_status": sanitize_value(row.get("Gap Status", row.get("gap_status", "Open"))),
                    "star_contribution": contrib_val,
                }

            if cols:
                rec = {k: v for k, v in rec.items() if k in cols}

            records.append(rec)

        return SupabaseService.bulk_upsert("final_recommendations", records)

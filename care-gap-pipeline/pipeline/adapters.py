"""
Adapter layer connecting Candidate Generator, ML Model, and MILP Optimizer in-memory.
Transforms and merges stage DataFrames into the exact schema required by the optimizer.
"""

import os
import pandas as pd
import numpy as np
from pipeline.calibration import calibrate_channel_bias

PERFORMANCE_OPPORTUNITY_FORMULA = "(1 - performance_value) * measure_weight"


def compute_performance_opportunity(
    performance_value: float,
    measure_weight: float
) -> float:
    """Calculate performance opportunity for a given measure and weight.

    Parameters
    ----------
    performance_value : float
        Current historical performance value (between 0 and 1).
    measure_weight : float
        CMS / plan measure weight.

    Returns
    -------
    float
        Computed performance improvement opportunity.
    """
    # TODO:
    # Replace this approximation with CMS star threshold
    # based calculation when threshold data is available.
    try:
        pv = float(performance_value) if pd.notna(performance_value) else 0.0
    except (ValueError, TypeError):
        pv = 0.0

    try:
        mw = float(measure_weight) if pd.notna(measure_weight) else 1.0
    except (ValueError, TypeError):
        mw = 1.0

    return (1.0 - pv) * mw


def ml_to_optimizer_input(
    rule_engine_df: pd.DataFrame,
    ml_output_df: pd.DataFrame,
    performance_df: pd.DataFrame = None,
    members_df: pd.DataFrame = None,
    input_excel_path: str = None
) -> pd.DataFrame:
    """Convert Rule Engine and ML inference outputs into the optimizer input schema.

    Parameters
    ----------
    rule_engine_df : pd.DataFrame
        Output DataFrame from the Rule Engine or Candidate Generator.
    ml_output_df : pd.DataFrame
        Output DataFrame from ML Model inference.
    performance_df : pd.DataFrame, optional
        PLAN_MEASURE_PERFORMANCE table if available separately.
    members_df : pd.DataFrame, optional
        MEMBERS table if available separately for member_name resolution.
    input_excel_path : str, optional
        Path to source Excel file to load MEMBERS or PERFORMANCE sheets if needed.

    Returns
    -------
    pd.DataFrame
        DataFrame formatted strictly for optimizer consumption.

    Raises
    ------
    ValueError
        If merge keys do not match 1-to-1 or unmatched rows exist.
    """
    if rule_engine_df is None or ml_output_df is None:
        raise ValueError("rule_engine_df and ml_output_df must both be provided.")

    if len(rule_engine_df) != len(ml_output_df):
        raise ValueError(
            f"Row count mismatch between Rule Engine / Candidates ({len(rule_engine_df)}) and ML Output ({len(ml_output_df)})."
        )

    merge_keys = ["patient_id", "plan_id", "care_gap", "intervention_type"]
    
    # Verify merge keys in both DataFrames
    for k in merge_keys:
        if k not in rule_engine_df.columns:
            raise ValueError(f"Merge key '{k}' missing from Rule Engine DataFrame.")
        if k not in ml_output_df.columns:
            raise ValueError(f"Merge key '{k}' missing from ML Output DataFrame.")

    # Apply Channel Bias Calibration if not already present
    ml_df = ml_output_df.copy()
    if "calibrated_probability" not in ml_df.columns and "calibrated_probability_score" not in ml_df.columns:
        ml_df["calibrated_probability"] = calibrate_channel_bias(ml_df)
    elif "calibrated_probability_score" in ml_df.columns and "calibrated_probability" not in ml_df.columns:
        ml_df["calibrated_probability"] = ml_df["calibrated_probability_score"]

    # In-memory merge
    merged = pd.merge(
        rule_engine_df,
        ml_df,
        on=merge_keys,
        how="inner",
        suffixes=("_re", "_ml")
    )

    if len(merged) != len(rule_engine_df) or len(merged) != len(ml_output_df):
        raise ValueError(
            f"Merge failure: Expected {len(rule_engine_df)} merged rows, but got {len(merged)}. Unmatched rows detected!"
        )

    # 1. Resolve member_name
    member_name_col = None
    if "member_name" in merged.columns and merged["member_name"].notna().any():
        member_name_col = merged["member_name"].astype(str)
    elif members_df is not None and "member_name" in members_df.columns:
        m_map = members_df.drop_duplicates("member_id").set_index("member_id")["member_name"].to_dict()
        member_name_col = merged["patient_id"].map(m_map).fillna(merged["patient_id"].astype(str))
    elif input_excel_path and os.path.exists(input_excel_path):
        m_df = pd.read_excel(input_excel_path, sheet_name="MEMBERS")
        m_df.columns = m_df.columns.astype(str).str.strip().str.lower().str.replace(" ", "_")
        m_map = m_df.drop_duplicates("member_id").set_index("member_id")["member_name"].to_dict()
        member_name_col = merged["patient_id"].map(m_map).fillna(merged["patient_id"].astype(str))
    else:
        # Fallback to patient_id if member_name is not provided
        member_name_col = merged["patient_id"].astype(str)

    # 2. Probability Scores & Uncertainty Bounds
    if "calibrated_probability" in merged.columns:
        closure_probability = pd.to_numeric(merged["calibrated_probability"], errors="coerce").fillna(0.5)
    elif "calibrated_probability_score" in merged.columns:
        closure_probability = pd.to_numeric(merged["calibrated_probability_score"], errors="coerce").fillna(0.5)
    elif "probability_score" in merged.columns:
        closure_probability = pd.to_numeric(merged["probability_score"], errors="coerce").fillna(0.5)
    else:
        closure_probability = pd.to_numeric(merged["probability_score_ml"], errors="coerce").fillna(0.5)

    raw_lower = merged["uncertainity_range_lower"] if "uncertainity_range_lower" in merged.columns else (merged["uncertainity_range_lower_ml"] if "uncertainity_range_lower_ml" in merged.columns else (merged["uncertainty_lower"] if "uncertainty_lower" in merged.columns else pd.Series(0.0, index=merged.index)))
    raw_upper = merged["uncertainity_range_upper"] if "uncertainity_range_upper" in merged.columns else (merged["uncertainity_range_upper_ml"] if "uncertainity_range_upper_ml" in merged.columns else (merged["uncertainty_upper"] if "uncertainty_upper" in merged.columns else pd.Series(1.0, index=merged.index)))
    
    # Ensure calibrated bounds are strictly consistent: uncertainty_lower <= closure_probability <= uncertainty_upper
    raw_lower = pd.to_numeric(raw_lower, errors="coerce").fillna(0.0)
    raw_upper = pd.to_numeric(raw_upper, errors="coerce").fillna(1.0)
    uncertainty_lower = np.minimum(closure_probability, raw_lower)
    uncertainty_upper = np.maximum(closure_probability, raw_upper)

    # 3. Performance Opportunity calculation
    if performance_df is not None:
        perf_lookup = {}
        for _, r in performance_df.iterrows():
            k = (str(r.get("plan_id", "")).strip(), str(r.get("measure_id", "")).strip())
            perf_lookup[k] = r
        
        opp_list = []
        for _, r in merged.iterrows():
            k = (str(r["plan_id"]).strip(), str(r["measure_id"]).strip())
            perf_row = perf_lookup.get(k)
            if perf_row is not None:
                pv = perf_row.get("performance_value", r.get("performance_value", 0.0))
                mw = perf_row.get("weight", perf_row.get("measure_weight", r.get("measure_weight", 1.0)))
            else:
                pv = r.get("performance_value", 0.0)
                mw = r.get("measure_weight", 1.0)
            opp_list.append(compute_performance_opportunity(pv, mw))
        perf_opp = np.array(opp_list)
    else:
        # Calculate from merged rule engine columns
        pv_series = merged["performance_value"] if "performance_value" in merged.columns else pd.Series(0.0, index=merged.index)
        mw_series = merged["measure_weight"] if "measure_weight" in merged.columns else pd.Series(1.0, index=merged.index)
        perf_opp = [compute_performance_opportunity(p, w) for p, w in zip(pv_series, mw_series)]

    # 4. Construct Optimizer DataFrame
    age_ser = merged["age"] if "age" in merged.columns else merged.get("age_re", pd.Series(70, index=merged.index))
    gender_ser = merged["gender"] if "gender" in merged.columns else merged.get("gender_re", pd.Series("Unknown", index=merged.index))
    plan_ser = merged["plan_id"] if "plan_id" in merged.columns else merged.get("plan_id_re", pd.Series("P001", index=merged.index))
    meas_ser = merged["measure_id"] if "measure_id" in merged.columns else merged.get("measure_id_re", pd.Series("M001", index=merged.index))
    weight_ser = merged["measure_weight"] if "measure_weight" in merged.columns else merged.get("measure_weight_re", pd.Series(1.0, index=merged.index))

    # 4. Determine eligibility and open gap status directly from Rule Engine outputs
    if "eligible" in merged.columns:
        eligible_series = pd.to_numeric(merged["eligible"], errors="coerce").fillna(1).astype(int)
    elif "enrollment_status" in merged.columns:
        eligible_series = merged["enrollment_status"].astype(str).str.strip().str.lower().apply(
            lambda s: 1 if s in ("active", "enrolled", "1", "true") else 0
        )
    else:
        eligible_series = pd.Series(1, index=merged.index)

    if "gap_open" in merged.columns:
        gap_open_series = pd.to_numeric(merged["gap_open"], errors="coerce").fillna(1).astype(int)
    elif "gap_status" in merged.columns:
        gap_open_series = merged["gap_status"].astype(str).str.strip().str.lower().apply(
            lambda s: 1 if s in ("open", "active", "1", "true") else 0
        )
    else:
        gap_open_series = pd.Series(1, index=merged.index)

    opt_df = pd.DataFrame({
        "member_id": merged["patient_id"].astype(str),
        "plan_id": plan_ser.astype(str),
        "member_name": member_name_col,
        "age": pd.to_numeric(age_ser, errors="coerce").fillna(0).astype(int),
        "gender": gender_ser.astype(str),
        "care_gap": merged["care_gap"].astype(str),
        "intervention_type": merged["intervention_type"].astype(str),
        "closure_probability": pd.to_numeric(closure_probability, errors="coerce").fillna(0.5),
        "uncertainty_lower": pd.to_numeric(uncertainty_lower, errors="coerce").fillna(0.0),
        "uncertainty_upper": pd.to_numeric(uncertainty_upper, errors="coerce").fillna(1.0),
        "measure_id": meas_ser.astype(str),
        "measure_weight": pd.to_numeric(weight_ser, errors="coerce").fillna(1.0),
        "performance_opportunity": pd.to_numeric(pd.Series(perf_opp, index=merged.index), errors="coerce").fillna(0.0),
        "eligible": eligible_series,
        "gap_open": gap_open_series
    })

    required_cols = [
        "member_id", "plan_id", "member_name", "age", "gender",
        "care_gap", "intervention_type",
        "closure_probability", "uncertainty_lower", "uncertainty_upper",
        "measure_id", "measure_weight", "performance_opportunity",
        "eligible", "gap_open"
    ]

    return opt_df[required_cols]

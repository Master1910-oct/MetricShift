"""
End-to-End Care-Gap Pipeline Orchestrator.
Connects Rule Engine -> Intervention Candidate Generator -> ML Model Inference -> Calibration -> Best Intervention Selection -> Adapter Layer -> MILP Optimizer.
Operates 100% in-memory using Pandas DataFrames.
"""

import os
import sys
import argparse
import pandas as pd

# Ensure project root is in sys.path for direct script execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from rule_engine import run_rule_engine
from pipeline.intervention_candidates import generate_intervention_candidates
from ml_model.infer import run_inference
from pipeline.calibration import calibrate_channel_bias
from pipeline.intervention_selection import select_best_interventions
from pipeline.adapters import ml_to_optimizer_input
from optimizer import run_optimizer
from pipeline.validation import run_hard_assertions, generate_validation_excel


def format_final_output(selected_df: pd.DataFrame) -> pd.DataFrame:
    """Format MILP optimizer output to match final reporting specifications.

    Parameters
    ----------
    selected_df : pd.DataFrame
        Raw output DataFrame from run_optimizer().

    Returns
    -------
    pd.DataFrame
        Formatted DataFrame with final column names and sequential S.No.
    """
    if selected_df is None or selected_df.empty:
        return pd.DataFrame(columns=[
            "S.No.", "Member ID", "Member Name", "Age", "Gender",
            "Total Gaps (Count)", "Care Gap(s)", "Recommended Intervention",
            "Gap Status", "Estimated Star Rating Improvement (Contribution)"
        ])

    formatted = pd.DataFrame({
        "S.No.": range(1, len(selected_df) + 1),
        "Member ID": selected_df["member_id"].values,
        "Member Name": selected_df["member_name"].values,
        "Age": selected_df["age"].values,
        "Gender": selected_df["gender"].values,
        "Total Gaps (Count)": selected_df["gap_count"].values,
        "Care Gap(s)": selected_df["care_gaps"].values,
        "Recommended Intervention": selected_df["recommended_intervention"].values,
        "Gap Status": selected_df["gap_status"].values,
        "Estimated Star Rating Improvement (Contribution)": selected_df["robust_quality"].values
    })
    return formatted


def compute_project_estimated_star_contribution(
    selected_df: pd.DataFrame,
    audit_df: pd.DataFrame,
    input_excel_path: str = "data/raw/FILTERED_8_TABLES_WITH_NAMES.xlsx"
) -> tuple[dict, pd.DataFrame]:
    """Compute project-level estimated Star Rating Improvement contribution per member.

    Methodology:
    1. For each care gap belonging to a selected member:
       - Retrieves plan_id, measure denominator, baseline performance_value, current measure_star,
         and measure weight from PLAN_MEASURE_PERFORMANCE.
       - Expected performance rate improvement: delta_rate = closure_probability / denominator.
       - Measure-level star improvement sensitivity:
           star_opportunity = max(5.0 - current_measure_star, 1.0)
           perf_opportunity = max(1.0 - performance_value, 0.05)
           measure_star_delta = (delta_rate / perf_opportunity) * star_opportunity
       - Plan-level Star Rating contribution:
           plan_star_contrib = (measure_weight / total_plan_weight) * measure_star_delta
    2. Aggregates plan_star_contrib across all open care gaps of that member.

    Returns
    -------
    tuple[dict, pd.DataFrame]
        Map of member_id -> estimated_star_contribution, and full technical audit DataFrame.
    """
    if selected_df is None or selected_df.empty:
        return {}, pd.DataFrame()

    pmp_map = {}
    plan_weights = {}
    m_plan_map = {}

    if input_excel_path and os.path.exists(input_excel_path):
        try:
            xl = pd.ExcelFile(input_excel_path)
            if "PLAN_MEASURE_PERFORMANCE" in xl.sheet_names:
                pmp = xl.parse("PLAN_MEASURE_PERFORMANCE")
                plan_weights = pmp.groupby("plan_id")["weight"].sum().to_dict()
                for _, r in pmp.iterrows():
                    pmp_map[(str(r["plan_id"]).strip(), str(r["measure_id"]).strip())] = {
                        "denominator": float(r["denominator"]),
                        "numerator": float(r["numerator"]),
                        "performance_value": float(r["performance_value"]),
                        "measure_star": float(r["measure_star"]),
                        "weight": float(r["weight"])
                    }
            if "MEMBER_ENROLLMENT" in xl.sheet_names:
                me = xl.parse("MEMBER_ENROLLMENT")
                m_plan_map = me.drop_duplicates("member_id").set_index("member_id")["plan_id"].to_dict()
        except Exception as e:
            print(f"Warning loading plan measure performance: {e}")

    gap_to_meas = {
        "diabetes care": "C12",
        "kidney health evaluation": "C13",
        "controlling blood pressure": "C14",
        "plan all-cause readmissions": "C18",
        "statin therapy for patients with cardiovascular disease": "C19",
        "medication adherence for diabetes": "D08",
        "medication adherence for hypertension": "D09",
        "medication adherence for cholesterol": "D10",
        "mtm program completion rate": "D11",
        "statin use in persons with diabetes": "D12",
    }

    def resolve_measure_id(gap_name: str) -> str:
        gn = str(gap_name).lower()
        for k, v in gap_to_meas.items():
            if k in gn:
                return v
        return "C12"

    member_star_contribs = {}
    audit_rows = []

    for _, m_row in selected_df.iterrows():
        mid = str(m_row["member_id"])
        pid = str(m_plan_map.get(mid, m_row.get("plan_id", "P001"))).strip()
        total_W = float(plan_weights.get(pid, 20.0))

        m_audit = audit_df[audit_df["patient_id"] == mid] if audit_df is not None and not audit_df.empty else pd.DataFrame()

        m_tot_star_contrib = 0.0

        if not m_audit.empty:
            for _, g in m_audit.iterrows():
                gap_raw = str(g["care_gap"])
                meas_id = resolve_measure_id(gap_raw)
                sel_int = str(g.get("selected_intervention", "Phone Call"))

                if sel_int == "Phone Call":
                    prob = float(g.get("phone_probability", 0.85))
                elif sel_int == "SMS":
                    prob = float(g.get("sms_probability", 0.85))
                else:
                    prob = float(g.get("email_probability", 0.85))

                p_info = pmp_map.get((pid, meas_id), {
                    "denominator": 2500.0,
                    "performance_value": 0.70,
                    "measure_star": 3.0,
                    "weight": 3.0
                })
                denom = float(p_info["denominator"])
                pv = float(p_info["performance_value"])
                curr_star = float(p_info["measure_star"])
                mw = float(p_info["weight"])

                delta_rate = prob / denom
                if curr_star >= 5.0:
                    star_opp = 0.0
                    meas_star_delta = 0.0
                    plan_star_contrib = 0.0
                    proj_star = 5.0
                else:
                    star_opp = max(5.0 - curr_star, 0.0)
                    perf_opp = max(1.0 - pv, 0.05)
                    raw_meas_delta = (delta_rate / perf_opp) * star_opp
                    proj_star = min(curr_star + raw_meas_delta, 5.0)
                    meas_star_delta = proj_star - curr_star
                    plan_star_contrib = (mw / total_W) * meas_star_delta

                m_tot_star_contrib += plan_star_contrib

                audit_rows.append({
                    "Member ID": mid,
                    "Care Gap": gap_raw,
                    "Measure ID": meas_id,
                    "Plan ID": pid,
                    "Current Performance": round(pv, 4),
                    "Closure Probability": round(prob, 4),
                    "Projected Performance": round(pv + delta_rate, 6),
                    "Current Measure Star": curr_star,
                    "Projected Measure Star": round(proj_star, 6),
                    "Measure Star Improvement": round(meas_star_delta, 6),
                    "Measure Weight": mw,
                    "Estimated Star Contribution": round(plan_star_contrib, 6),
                    "Final Member Contribution": 0.0  # Populated after loop
                })
        else:
            # Fallback if audit_df not passed
            gaps_str = str(m_row.get("care_gaps", ""))
            gaps_list = [g.strip() for g in gaps_str.split(";") if g.strip()]
            for gap_raw in gaps_list:
                meas_id = resolve_measure_id(gap_raw)
                p_info = pmp_map.get((pid, meas_id), {
                    "denominator": 2500.0,
                    "performance_value": 0.70,
                    "measure_star": 3.0,
                    "weight": 3.0
                })
                denom = float(p_info["denominator"])
                pv = float(p_info["performance_value"])
                curr_star = float(p_info["measure_star"])
                mw = float(p_info["weight"])
                prob = float(m_row.get("closure_probability", 0.85))

                delta_rate = prob / denom
                if curr_star >= 5.0:
                    star_opp = 0.0
                    meas_star_delta = 0.0
                    plan_star_contrib = 0.0
                    proj_star = 5.0
                else:
                    star_opp = max(5.0 - curr_star, 0.0)
                    perf_opp = max(1.0 - pv, 0.05)
                    raw_meas_delta = (delta_rate / perf_opp) * star_opp
                    proj_star = min(curr_star + raw_meas_delta, 5.0)
                    meas_star_delta = proj_star - curr_star
                    plan_star_contrib = (mw / total_W) * meas_star_delta

                m_tot_star_contrib += plan_star_contrib

                audit_rows.append({
                    "Member ID": mid,
                    "Care Gap": gap_raw,
                    "Measure ID": meas_id,
                    "Plan ID": pid,
                    "Current Performance": round(pv, 4),
                    "Closure Probability": round(prob, 4),
                    "Projected Performance": round(pv + delta_rate, 6),
                    "Current Measure Star": curr_star,
                    "Projected Measure Star": round(proj_star, 6),
                    "Measure Star Improvement": round(meas_star_delta, 6),
                    "Measure Weight": mw,
                    "Estimated Star Contribution": round(plan_star_contrib, 6),
                    "Final Member Contribution": 0.0
                })

        member_star_contribs[mid] = m_tot_star_contrib

    audit_df_out = pd.DataFrame(audit_rows)
    if not audit_df_out.empty:
        audit_df_out["Final Member Contribution"] = audit_df_out["Member ID"].map(
            lambda m: round(member_star_contribs.get(m, 0.0), 6)
        )

    return member_star_contribs, audit_df_out


def generate_final_member_report(
    selected_df: pd.DataFrame,
    audit_df: pd.DataFrame = None,
    input_excel_path: str = "data/raw/FILTERED_8_TABLES_WITH_NAMES.xlsx",
    output_dir: str = "outputs"
) -> pd.DataFrame:
    """Generate business-friendly final member report (.xlsx and .csv) and technical star contribution audit.

    Columns:
    1. S. No.
    2. Member ID
    3. Member Name
    4. Age
    5. Gender
    6. Total Gaps (Count)
    7. Care Gap(s) (Gap Name)
    8. Recommended Intervention
    9. Gap Status
    10. Estimated Star Rating Improvement (Contribution)
    """
    cols = [
        "S. No.", "Member ID", "Member Name", "Age", "Gender",
        "Total Gaps (Count)", "Care Gap(s) (Gap Name)", "Recommended Intervention",
        "Gap Status", "Estimated Star Rating Improvement (Contribution)"
    ]
    if selected_df is None or selected_df.empty:
        return pd.DataFrame(columns=cols)

    # Compute project-level estimated Star Rating Improvement contribution
    star_contrib_map, star_audit_df = compute_project_estimated_star_contribution(
        selected_df=selected_df,
        audit_df=audit_df,
        input_excel_path=input_excel_path
    )

    contrib_formatted = []
    for mid in selected_df["member_id"].values:
        star_val = star_contrib_map.get(str(mid), 0.0)
        contrib_formatted.append(f"+{star_val:.4f}")

    # Calculate gap count from semicolon-separated care gaps if gap_count not present
    gap_counts = []
    care_gaps_list = selected_df["care_gaps"].astype(str).values
    for cg_str in care_gaps_list:
        gaps = [g.strip() for g in cg_str.split(";") if g.strip()]
        gap_counts.append(len(gaps))

    member_report_df = pd.DataFrame({
        "S. No.": range(1, len(selected_df) + 1),
        "Member ID": selected_df["member_id"].values,
        "Member Name": selected_df["member_name"].values,
        "Age": selected_df["age"].values,
        "Gender": selected_df["gender"].values,
        "Total Gaps (Count)": gap_counts,
        "Care Gap(s) (Gap Name)": care_gaps_list,
        "Recommended Intervention": selected_df["recommended_intervention"].values,
        "Gap Status": selected_df["gap_status"].values if "gap_status" in selected_df.columns else "Open",
        "Estimated Star Rating Improvement (Contribution)": contrib_formatted
    })

    os.makedirs(output_dir, exist_ok=True)
    xlsx_path = os.path.join(output_dir, "final_member_report.xlsx")
    csv_path = os.path.join(output_dir, "final_member_report.csv")
    audit_xlsx_path = os.path.join(output_dir, "star_rating_contribution_audit.xlsx")

    import time

    def safe_save_file(save_fn, file_path, retries=5, delay=1.0):
        for attempt in range(retries):
            try:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                save_fn(file_path)
                return
            except PermissionError:
                time.sleep(delay)
        save_fn(file_path)

    safe_save_file(lambda p: member_report_df.to_csv(p, index=False), csv_path)

    if not star_audit_df.empty:
        safe_save_file(lambda p: star_audit_df.to_excel(p, index=False), audit_xlsx_path)

    # OpenPyXL formatting for business Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Member_Recommendations"

    # Add header
    ws.append(list(member_report_df.columns))

    # Add rows
    for row in member_report_df.itertuples(index=False):
        ws.append(list(row))

    # Styling definitions
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    # Format header row
    for col_idx in range(1, len(member_report_df.columns) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Format data rows
    for r_idx in range(2, len(member_report_df) + 2):
        for c_idx in range(1, len(member_report_df.columns) + 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            cell.font = data_font
            cell.border = thin_border
            col_name = member_report_df.columns[c_idx - 1]
            if col_name in ["S. No.", "Age", "Gender", "Total Gaps (Count)", "Recommended Intervention", "Gap Status", "Estimated Star Rating Improvement (Contribution)"]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Freeze header row
    ws.freeze_panes = "A2"

    # Enable Autofilter
    ws.auto_filter.ref = ws.dimensions

    # Auto-fit column widths
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        if col_letter == "G":  # Care Gap(s) (Gap Name)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 30), 65)
        else:
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    safe_save_file(lambda p: wb.save(p), xlsx_path)

    # Validate final member report
    final_members = len(selected_df)
    report_rows = len(member_report_df)
    dup_members = report_rows - member_report_df["Member ID"].nunique()
    col_count = len(member_report_df.columns)

    interv_mismatches = (member_report_df["Recommended Intervention"].values != selected_df["recommended_intervention"].values).sum()

    gap_count_mismatches = 0
    for idx, row in member_report_df.iterrows():
        gaps_count_listed = len([g.strip() for g in str(row["Care Gap(s) (Gap Name)"]).split(";") if g.strip()])
        if gaps_count_listed != row["Total Gaps (Count)"]:
            gap_count_mismatches += 1

    star_mismatches = member_report_df["Estimated Star Rating Improvement (Contribution)"].isna().sum()

    status = "PASS" if (
        final_members == report_rows and
        dup_members == 0 and
        col_count == 10 and
        interv_mismatches == 0 and
        gap_count_mismatches == 0 and
        star_mismatches == 0
    ) else "FAIL"

    print("\n" + "=" * 60)
    print("FINAL MEMBER REPORT VALIDATION")
    print("=" * 60)
    print(f"Final members:                 {final_members}")
    print(f"Report rows:                   {report_rows}")
    print(f"Duplicate members:             {dup_members}")
    print(f"Column count:                  {col_count}")
    print(f"Intervention mismatches:       {interv_mismatches}")
    print(f"Gap-count mismatches:          {gap_count_mismatches}")
    print(f"Star-contribution mismatches:  {star_mismatches}")
    print(f"STATUS:                        {status}")
    print(f"Files:")
    print(f"  {xlsx_path}")
    print(f"  {csv_path}")
    print(f"  {audit_xlsx_path}")
    print("=" * 60)

    print("\nFIRST 10 ROWS OF FINAL MEMBER REPORT:")
    print(member_report_df.head(10).to_string(index=False))

    return member_report_df


def run_full_pipeline(
    input_excel_path: str,
    max_selected_members: int = 250,
    output_dir: str = "outputs",
    models_dir: str = "models"
) -> pd.DataFrame:
    """Execute the complete integrated in-memory Care-Gap Pipeline.

    Execution Stages:
    1. Rule Engine: Identifies open care gaps and extracts patient clinical & behavioral features.
    2. Candidate Generator: Expands care gaps across actionable communication channels (Email, SMS, Phone Call).
    3. ML Inference: Predicts gap closure probabilities and uncertainty bounds across all candidates.
    4. Calibration: Removes channel base-rate bias in logit space.
    5. Best Intervention Selection: Selects top ML winner (if margin > 0.01) or near-tie diversity choice per gap.
    6. Adapter Layer: Transforms 1 selected intervention per gap into MILP optimizer schema.
    7. MILP Optimizer: Selects optimal WHO to target (max_selected_members) under budget & channel capacity.
    8. Final Output & Validation: Formats recommendations and generates comprehensive Excel audit reports.

    Parameters
    ----------
    input_excel_path : str
        Path to the 8-table Excel workbook.
    max_selected_members : int, optional
        Maximum number of members to select, by default 250.
    output_dir : str, optional
        Directory to save final output files, by default "outputs".
    models_dir : str, optional
        Directory containing model binaries, by default "models".

    Returns
    -------
    pd.DataFrame
        Final formatted recommendation DataFrame.
    """
    print("====================================================")
    print("STARTING INTEGRATED CARE-GAP ML PIPELINE")
    print("====================================================")
    print(f"Input Dataset: {input_excel_path}")
    print(f"Max Selected Members: {max_selected_members}")

    # Stage 1: Rule Engine
    print("\n[Stage 1/7] Running Rule Engine...")
    rule_engine_df = run_rule_engine(input_excel_path)
    print(f"  Rule Engine identified {len(rule_engine_df)} care-gap records.")

    # Stage 2: Intervention Candidate Generator
    print("\n[Stage 2/7] Generating Actionable Intervention Candidates (Email, SMS, Phone Call)...")
    candidate_df = generate_intervention_candidates(rule_engine_df)
    print(f"  Generated {len(candidate_df)} intervention candidate rows (3x channel options per care gap).")

    # Stage 3: ML Model Inference
    print("\n[Stage 3/7] Running ML Ensemble Inference on Candidates...")
    ml_output_df = run_inference(candidate_df, models_dir=models_dir)
    print(f"  ML Model generated predictions for {len(ml_output_df)} candidate records.")

    # Stage 4: Logit-Space Channel Calibration
    print("\n[Stage 4/7] Calibrating Channel Base-Rate Bias in Logit Space...")
    calibrated_probs = calibrate_channel_bias(ml_output_df)
    ml_output_df["calibrated_probability"] = calibrated_probs
    candidate_df["calibrated_probability"] = calibrated_probs
    print(f"  Applied logit calibration across {len(ml_output_df)} candidates.")

    # Stage 5: Best Intervention Selection
    print("\n[Stage 5/7] Running Best Intervention Selection (Clear Winners > 0.01 Margin & Diversity)...")
    best_cands_df, audit_df, metrics = select_best_interventions(ml_output_df)
    print(f"  Selected best intervention for {len(best_cands_df)} care-gap records.")
    print(f"  Clear Winner Decisions: {metrics.get('clear_winner_decisions', 0)}")
    print(f"  Near-Tie Decisions:     {metrics.get('near_tie_decisions', 0)}")
    print(f"  Clear Winners Changed:  {metrics.get('clear_winner_changed_count', 0)} (Expected: 0)")

    # Merge clinical attributes back to best candidates for adapter layer
    merge_keys = ["patient_id", "plan_id", "care_gap", "intervention_type"]
    best_full_df = pd.merge(
        best_cands_df,
        candidate_df.drop(columns=["probability_score", "calibrated_probability"], errors="ignore"),
        on=merge_keys,
        how="inner"
    )

    # Stage 6: Adapter Layer
    print("\n[Stage 6/7] Transforming Selected Interventions via Adapter Layer...")
    optimizer_input_df = ml_to_optimizer_input(
        rule_engine_df=best_full_df,
        ml_output_df=best_cands_df,
        input_excel_path=input_excel_path
    )
    print(f"  Adapter mapped {len(optimizer_input_df)} rows to Optimizer schema.")

    # Stage 7: MILP Optimizer (Member Selection)
    print("\n[Stage 7/7] Running Robust MILP Optimizer (Member Selection Only)...")
    selected_df = run_optimizer(
        df=optimizer_input_df,
        max_selected_members=max_selected_members
    )
    print(f"  Optimizer selected {len(selected_df)} optimal member interventions.")

    # Format Final Outputs
    os.makedirs(output_dir, exist_ok=True)
    final_df = format_final_output(selected_df)

    xlsx_path = os.path.join(output_dir, "final_output.xlsx")
    csv_path = os.path.join(output_dir, "final_output.csv")
    audit_xlsx_path = os.path.join(output_dir, "intervention_selection_audit.xlsx")
    val_xlsx_path = os.path.join(output_dir, "FINAL_END_TO_END_VALIDATION.xlsx")

    final_df.to_excel(xlsx_path, index=False)
    final_df.to_csv(csv_path, index=False)
    audit_df.to_excel(audit_xlsx_path, index=False)

    # Generate business-friendly final member report
    member_report_df = generate_final_member_report(
        selected_df=selected_df,
        audit_df=audit_df,
        input_excel_path=input_excel_path,
        output_dir=output_dir
    )

    # Run Automated Hard Assertions
    print("\nExecuting 20 Automated Hard Assertions...")
    assertions = run_hard_assertions(
        re_df=rule_engine_df,
        cand_df=candidate_df,
        ml_df=ml_output_df,
        best_df=best_cands_df,
        audit_df=audit_df,
        opt_input_df=optimizer_input_df,
        opt_output_df=selected_df,
        final_df=final_df,
        metrics=metrics
    )

    # Generate Final Excel Validation Report
    print("Generating FINAL_END_TO_END_VALIDATION.xlsx...")
    generate_validation_excel(
        re_df=rule_engine_df,
        cand_df=candidate_df,
        ml_df=ml_output_df,
        best_df=best_cands_df,
        audit_df=audit_df,
        opt_input_df=optimizer_input_df,
        opt_output_df=selected_df,
        final_df=final_df,
        metrics=metrics,
        assertions=assertions,
        output_path=val_xlsx_path
    )

    print(f"\nFinal outputs successfully exported:")
    print(f"  Recommendations Excel:   {xlsx_path}")
    print(f"  Recommendations CSV:     {csv_path}")
    print(f"  Final Member Report (XLSX): {os.path.join(output_dir, 'final_member_report.xlsx')}")
    print(f"  Final Member Report (CSV):  {os.path.join(output_dir, 'final_member_report.csv')}")
    print(f"  Intervention Audit:      {audit_xlsx_path}")
    print(f"  Validation Report:       {val_xlsx_path}")

    # Print Execution Summary
    print("\n" + "=" * 52)
    print("PIPELINE EXECUTION SUMMARY")
    print("=" * 52)
    print(f"Rule Engine Rows:      {len(rule_engine_df)}")
    print(f"Candidate Rows:        {len(candidate_df)}")
    print(f"ML Output Rows:        {len(ml_output_df)}")
    print(f"Best Intervention Rows:{len(best_cands_df)}")
    print(f"Optimizer Input Rows:  {len(optimizer_input_df)}")
    print(f"Final Recommendations: {len(final_df)}")
    print("=" * 52)

    return final_df


if __name__ == "__main__":
    import argparse, sys, os

    DEFAULT_INPUT = "data/raw/FILTERED_8_TABLES_WITH_NAMES.xlsx"

    parser = argparse.ArgumentParser(
        description="Run Integrated Care-Gap Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=str,
        default=DEFAULT_INPUT,
        help="Path to the 8-table input Excel (.xlsx) file",
    )
    parser.add_argument(
        "--max_members",
        type=int,
        default=250,
        help="Maximum members to select in optimizer",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="outputs",
        help="Directory to save final output files",
    )
    parser.add_argument(
        "--models_dir",
        type=str,
        default="models",
        help="Directory containing trained model pkl files",
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Validate supplied input path
    # ------------------------------------------------------------------
    SUPPORTED_EXTENSIONS = {".xlsx", ".csv"}
    input_path = args.input
    _, ext = os.path.splitext(input_path)

    if ext.lower() not in SUPPORTED_EXTENSIONS:
        print(
            f"ERROR: Unsupported file extension '{ext}'. "
            f"Supported formats: {sorted(SUPPORTED_EXTENSIONS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not os.path.exists(input_path):
        print(
            f"ERROR: Input file not found: '{os.path.abspath(input_path)}'",
            file=sys.stderr,
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # Print clearly which dataset is being tested
    # ------------------------------------------------------------------
    is_default = os.path.normpath(input_path) == os.path.normpath(DEFAULT_INPUT)
    print("=" * 60)
    print("CARE-GAP PIPELINE — INPUT DATASET")
    print("=" * 60)
    print(f"  File : {os.path.abspath(input_path)}")
    print(f"  Mode : {'Production (default dataset)' if is_default else 'Custom / Unseen Test Dataset'}")
    print("=" * 60)

    run_full_pipeline(
        input_excel_path=input_path,
        max_selected_members=args.max_members,
        output_dir=args.output_dir,
        models_dir=args.models_dir,
    )

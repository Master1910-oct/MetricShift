"""
Pipeline execution service.

Wraps the existing validated pipeline (pipeline/run_pipeline.py) in a
background thread so FastAPI remains responsive during long-running
pipeline execution.

CRITICAL ARCHITECTURE:
- Reads the CURRENT Supabase database and exports a temporary working workbook.
- Executes the validated pipeline functions WITHOUT modifying their internal logic.
- Persists stage transitions to Supabase pipeline_stages in real-time.
- Persists stage outputs to Supabase result tables (care_gaps, ml_predictions,
  intervention_selections, optimization_results, star_rating_contributions,
  final_recommendations).
- Maintains local file outputs in run_outputs/<run_id>/ for backward compatibility.
- Never touches outputs/ directory.
"""

import os
import sys
import threading
import traceback
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import pandas as pd

# Ensure project root is in sys.path for pipeline imports
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.services.supabase_service import SupabaseService
from backend.services.dataset_service import DatasetService
from backend.services.result_persistence_service import ResultPersistenceService

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

OUTPUT_BASE_DIR = os.environ.get("OUTPUT_BASE_DIR", "run_outputs")
MODELS_DIR = os.environ.get("MODELS_DIR", "models")

# ─────────────────────────────────────────────────────────────────────────────
# Stage definitions (ordered)
# ─────────────────────────────────────────────────────────────────────────────

STAGE_KEYS = [
    "file_upload",
    "rule_engine",
    "candidate_generation",
    "ml_inference",
    "calibration",
    "intervention_selection",
    "milp_optimization",
    "star_rating_contribution",
    "final_report",
]


def _default_stages() -> Dict[str, Dict[str, Any]]:
    stages = {}
    for key in STAGE_KEYS:
        stages[key] = {
            "status": "pending",
            "message": "Waiting",
            "rows": None,
            "error": None,
        }
    stages["file_upload"] = {
        "status": "completed",
        "message": "File uploaded and validated successfully.",
        "rows": None,
        "error": None,
    }
    return stages


@dataclass
class PipelineRunState:
    run_id: str
    status: str = "queued"        # queued | running | completed | failed
    trigger_type: str = "initial_upload"  # initial_upload | member_update | manual
    error: Optional[str] = None
    stages: Dict[str, Dict[str, Any]] = field(default_factory=_default_stages)
    final_report_df: Optional[pd.DataFrame] = None
    input_excel_path: Optional[str] = None
    output_dir: Optional[str] = None
    intervention_counts: Optional[Dict[str, int]] = None


# In-memory run registry — maps run_id -> PipelineRunState
_RUNS: Dict[str, PipelineRunState] = {}
_RUNS_LOCK = threading.Lock()


def register_run(
    run_id: str,
    input_excel_path: str,
    trigger_type: str = "initial_upload",
) -> PipelineRunState:
    """Register a new pipeline run before execution starts."""
    state = PipelineRunState(
        run_id=run_id,
        trigger_type=trigger_type,
        input_excel_path=str(input_excel_path),
        output_dir=str(Path(OUTPUT_BASE_DIR) / run_id),
    )
    with _RUNS_LOCK:
        _RUNS[run_id] = state

    # Persist initial run and stages in Supabase
    try:
        SupabaseService.register_pipeline_run(
            run_id=run_id,
            trigger_type=trigger_type,
            source_file_name=Path(input_excel_path).name if input_excel_path else "",
        )
        SupabaseService.update_stage(
            run_id=run_id,
            stage_key="file_upload",
            status="completed",
            message="File uploaded and validated successfully.",
        )
    except Exception as exc:
        print(f"[pipeline_service] Supabase register warning: {exc}", flush=True)

    return state


def get_run_state(run_id: str) -> Optional[PipelineRunState]:
    """Return the current state of a pipeline run, with disk-recovery fallback."""
    with _RUNS_LOCK:
        if run_id in _RUNS:
            return _RUNS[run_id]

    # Disk fallback: check if report already exists from previous process run
    out_dir = Path(OUTPUT_BASE_DIR) / run_id
    report_file = out_dir / "final_member_report.xlsx"
    if report_file.exists():
        try:
            df = pd.read_excel(report_file)
            input_file = Path("uploads") / run_id / "input.xlsx"
            input_path = str(input_file.resolve()) if input_file.exists() else None

            stages = {}
            for key in STAGE_KEYS:
                stages[key] = {
                    "status": "completed",
                    "message": "Completed",
                    "rows": len(df) if key in ("milp_optimization", "star_rating_contribution", "final_report") else None,
                    "error": None,
                }

            recovered_state = PipelineRunState(
                run_id=run_id,
                status="completed",
                stages=stages,
                final_report_df=df,
                input_excel_path=input_path,
                output_dir=str(out_dir.resolve()),
            )
            with _RUNS_LOCK:
                _RUNS[run_id] = recovered_state
            return recovered_state
        except Exception:
            pass

    return None


def _set_stage(
    state: PipelineRunState,
    key: str,
    status: str,
    message: str = "",
    rows: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    """Thread-safe stage status update with Supabase synchronization."""
    with _RUNS_LOCK:
        state.stages[key] = {
            "status": status,
            "message": message,
            "rows": rows,
            "error": error,
        }

    try:
        SupabaseService.update_stage(
            run_id=state.run_id,
            stage_key=key,
            status=status,
            message=message,
            rows_processed=rows,
            error_message=error,
        )
    except Exception as exc:
        print(f"[pipeline_service] Supabase stage update warning: {exc}", flush=True)


def _run_pipeline_thread(state: PipelineRunState) -> None:
    """Background thread executing the 9-stage pipeline."""
    try:
        from rule_engine import run_rule_engine
        from pipeline.intervention_candidates import generate_intervention_candidates
        from ml_model.infer import run_inference
        from pipeline.calibration import calibrate_channel_bias
        from pipeline.intervention_selection import select_best_interventions
        from pipeline.adapters import ml_to_optimizer_input
        from optimizer import run_optimizer
        from pipeline.run_pipeline import generate_final_member_report

        with _RUNS_LOCK:
            state.status = "running"

        try:
            SupabaseService.update_pipeline_run(state.run_id, status="running")
        except Exception:
            pass

        raw_input_path = state.input_excel_path
        output_dir = state.output_dir
        os.makedirs(output_dir, exist_ok=True)

        working_dir = Path(output_dir) / "working"
        working_dir.mkdir(parents=True, exist_ok=True)
        working_excel_path = str(working_dir / "input.xlsx")

        # ── Construct working workbook from CURRENT Supabase DB ───────────────
        working_input_path = DatasetService.export_current_db_to_working_excel(
            output_excel_path=working_excel_path,
            fallback_source_excel=raw_input_path,
        )
        input_path = working_input_path if os.path.exists(working_input_path) else raw_input_path

        models_dir = MODELS_DIR
        if not os.path.isabs(models_dir):
            models_dir = str(Path(_PROJECT_ROOT) / models_dir)

        # ── STAGE 2: Rule Engine ─────────────────────────────────────────────
        _set_stage(state, "rule_engine", "running", "Identifying care gaps from current database...")
        rule_engine_df = run_rule_engine(input_path)
        re_rows = len(rule_engine_df)

        # Persist care gaps to Supabase
        ResultPersistenceService.persist_care_gaps(state.run_id, rule_engine_df)

        _set_stage(state, "rule_engine", "completed",
                   f"{re_rows} care-gap records identified.", rows=re_rows)

        # ── STAGE 3: Candidate Generation ────────────────────────────────────
        _set_stage(state, "candidate_generation", "running", "Generating intervention candidates (3 channels)...")
        candidate_df = generate_intervention_candidates(rule_engine_df)
        cand_rows = len(candidate_df)
        _set_stage(state, "candidate_generation", "completed",
                   f"{cand_rows} candidate rows generated (3 channels × {re_rows} gaps).",
                   rows=cand_rows)

        # ── STAGE 4: ML Inference ────────────────────────────────────
        _set_stage(state, "ml_inference", "running", "Running ML ensemble inference for all intervention channels...")
        ml_output_df = run_inference(candidate_df, models_dir=models_dir)
        ml_rows = len(ml_output_df)
        _set_stage(state, "ml_inference", "completed",
                   f"ML predictions generated for {ml_rows} candidates.", rows=ml_rows)

        # ── STAGE 5: Calibration ─────────────────────────────────────────────
        _set_stage(state, "calibration", "running", "Calibrating channel base-rate bias...")
        calibrated_probs = calibrate_channel_bias(ml_output_df)
        ml_output_df["calibrated_probability"] = calibrated_probs
        candidate_df["calibrated_probability"] = calibrated_probs

        # Persist ML predictions with calibrated probabilities to Supabase
        ResultPersistenceService.persist_ml_predictions(state.run_id, ml_output_df)

        _set_stage(state, "calibration", "completed",
                   f"Logit calibration applied across {ml_rows} candidates.", rows=ml_rows)

        # ── STAGE 6: Intervention Selection ──────────────────────────────────
        _set_stage(state, "intervention_selection", "running",
                   "Selecting best intervention per care gap...")
        best_cands_df, audit_df, metrics = select_best_interventions(ml_output_df)
        best_rows = len(best_cands_df)

        # Persist selected interventions to Supabase
        ResultPersistenceService.persist_intervention_selections(state.run_id, best_cands_df, audit_df)

        _set_stage(state, "intervention_selection", "completed",
                   f"Best intervention selected for {best_rows} care gaps "
                   f"(clear winners: {metrics.get('clear_winner_decisions', 0)}, "
                   f"near-ties: {metrics.get('near_tie_decisions', 0)}).",
                   rows=best_rows)

        with _RUNS_LOCK:
            ch_counts = best_cands_df["intervention_type"].value_counts().to_dict()
            state.intervention_counts = {str(k): int(v) for k, v in ch_counts.items()}

        merge_keys = ["patient_id", "plan_id", "care_gap", "intervention_type"]
        best_full_df = pd.merge(
            best_cands_df,
            candidate_df.drop(columns=["probability_score", "calibrated_probability"], errors="ignore"),
            on=merge_keys,
            how="inner",
        )

        # ── STAGE 7: MILP Optimization ───────────────────────────────────────
        _set_stage(state, "milp_optimization", "running",
                   "Running MILP optimizer for member selection...")
        optimizer_input_df = ml_to_optimizer_input(
            rule_engine_df=best_full_df,
            ml_output_df=best_cands_df,
            input_excel_path=input_path,
        )
        selected_df = run_optimizer(df=optimizer_input_df, max_selected_members=250)
        opt_rows = len(selected_df)

        # Persist optimization results to Supabase (authoritative for subsequent member updates)
        ResultPersistenceService.persist_optimization_results(state.run_id, selected_df)

        _set_stage(state, "milp_optimization", "completed",
                   f"Optimizer selected {opt_rows} optimal member interventions.",
                   rows=opt_rows)

        # ── STAGE 8: Star Rating Contribution ────────────────────────────────
        _set_stage(state, "star_rating_contribution", "running",
                   "Computing Estimated Star Rating Improvement (Contribution)...")
        from pipeline.run_pipeline import (
            compute_project_estimated_star_contribution,
            generate_final_member_report,
        )
        # A. Star Rating calculation & local report generation
        member_report_df = generate_final_member_report(
            selected_df=selected_df,
            audit_df=audit_df,
            input_excel_path=input_path,
            output_dir=output_dir,
        )
        _, star_audit_df = compute_project_estimated_star_contribution(
            selected_df=selected_df,
            audit_df=audit_df,
            input_excel_path=input_path,
        )
        star_count = len(member_report_df)

        # B. Star Rating persistence (fails Stage 8 if persistence fails)
        ResultPersistenceService.persist_star_rating_contributions(state.run_id, star_audit_df)

        _set_stage(state, "star_rating_contribution", "completed",
                   f"Star Rating contribution computed for {star_count} selected members.",
                   rows=star_count)

        # ── STAGE 9: Final Report ────────────────────────────────────────────
        _set_stage(state, "final_report", "running", "Saving final outputs and persisting recommendations...")
        final_output_path = os.path.join(output_dir, "final_output.xlsx")
        if not os.path.exists(final_output_path):
            from pipeline.run_pipeline import format_final_output
            final_df = format_final_output(selected_df)
            final_df.to_excel(final_output_path, index=False)

        # C. Final Recommendation persistence (fails Stage 9 if persistence fails)
        ResultPersistenceService.persist_final_recommendations(state.run_id, member_report_df)

        _set_stage(state, "final_report", "completed",
                   f"Final report saved with {star_count} member records.",
                   rows=star_count)

        with _RUNS_LOCK:
            state.final_report_df = member_report_df
            state.status = "completed"

        try:
            SupabaseService.update_pipeline_run(state.run_id, status="completed")
        except Exception:
            pass

    except Exception as exc:
        tb = traceback.format_exc()
        error_msg = f"{type(exc).__name__}: {exc}"
        with _RUNS_LOCK:
            state.status = "failed"
            state.error = error_msg
        for key in STAGE_KEYS:
            if state.stages[key]["status"] == "running":
                _set_stage(state, key, "failed",
                           f"Stage failed: {error_msg}", error=tb)
                break
        try:
            SupabaseService.update_pipeline_run(state.run_id, status="failed", error_message=error_msg)
        except Exception:
            pass
        print(f"[pipeline_service] PIPELINE FAILED for run {state.run_id}:\n{tb}", flush=True)


def start_pipeline_run(state: PipelineRunState) -> None:
    """Launch the pipeline in a background daemon thread."""
    t = threading.Thread(
        target=_run_pipeline_thread,
        args=(state,),
        daemon=True,
        name=f"pipeline-{state.run_id[:8]}",
    )
    t.start()


def get_output_dir(run_id: str) -> Optional[str]:
    """Return the output directory for a completed run."""
    state = get_run_state(run_id)
    if state:
        return state.output_dir
    return None


def get_final_report_df(run_id: str) -> Optional[pd.DataFrame]:
    """Return the final member report DataFrame for a completed run."""
    state = get_run_state(run_id)
    if state and state.final_report_df is not None:
        return state.final_report_df.copy()
    report_path = Path(OUTPUT_BASE_DIR) / run_id / "final_member_report.xlsx"
    if report_path.exists():
        return pd.read_excel(report_path)
    return None


def get_input_excel_path(run_id: str) -> Optional[str]:
    """Return the path to the uploaded input Excel file."""
    state = get_run_state(run_id)
    if state and state.input_excel_path:
        return state.input_excel_path
    upload_path = Path("uploads") / run_id / "input.xlsx"
    if upload_path.exists():
        return str(upload_path.resolve())
    return None

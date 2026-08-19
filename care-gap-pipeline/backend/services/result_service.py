"""
Result data service.

Reads pipeline outputs (Supabase result tables with local Excel fallback)
and shapes data for API responses.

Sanitizes all NaN/Inf values so responses are 100% JSON compliant.
Never exposes internal file paths, model files, or Python source to callers.
"""

import os
import math
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
import pandas as pd
import numpy as np

# Automatically load .env if present
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

from backend.services.supabase_service import SupabaseService
from backend.services.pipeline_service import (
    get_run_state,
    get_final_report_df,
    get_input_excel_path,
    get_output_dir,
    OUTPUT_BASE_DIR,
)
from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────────────────────
# JSON sanitization helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clean_float(val: Any, default: float = 0.0) -> float:
    """Safely convert any numeric/string to a JSON-compliant float (no NaN/Inf)."""
    if val is None or pd.isna(val):
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


def _clean_int(val: Any, default: int = 0) -> int:
    """Safely convert to int."""
    if val is None or pd.isna(val):
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _clean_str(val: Any, default: str = "") -> str:
    """Safely convert to string, replacing NaN with empty string."""
    if val is None or pd.isna(val):
        return default
    s = str(val).strip()
    if s.lower() == "nan":
        return default
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Validation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _require_completed_run(run_id: str):
    """Raise 404 if run not found, 202 if still running, 500 if failed."""
    state = get_run_state(run_id)
    if state is None:
        report = Path(OUTPUT_BASE_DIR) / run_id / "final_member_report.xlsx"
        if not report.exists():
            # Check Supabase pipeline_runs
            runs = SupabaseService.fetch_all("pipeline_runs", filters={"id": run_id})
            if not runs:
                raise HTTPException(status_code=404, detail=f"Job '{run_id}' not found.")
            r = runs[0]
            if r.get("status") == "failed":
                raise HTTPException(status_code=500, detail=f"Pipeline failed: {r.get('error_message')}")
            if r.get("status") != "completed":
                raise HTTPException(status_code=202, detail=f"Pipeline is still {r.get('status')}.")
            return
        return  # Disk-based recovery available
    if state.status == "failed":
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {state.error}")
    if state.status not in ("completed",):
        raise HTTPException(status_code=202, detail=f"Pipeline is still {state.status}.")


_INPUT_EXCEL_SHEETS_CACHE: Dict[Tuple[str, str], pd.DataFrame] = {}


def invalidate_cache(run_id: Optional[str] = None):
    """Clear in-memory cache to ensure fresh data is always fetched from Supabase."""
    global _INPUT_EXCEL_SHEETS_CACHE
    if run_id:
        keys_to_del = [k for k in list(_INPUT_EXCEL_SHEETS_CACHE.keys()) if k[0] == run_id]
        for k in keys_to_del:
            _INPUT_EXCEL_SHEETS_CACHE.pop(k, None)
    else:
        _INPUT_EXCEL_SHEETS_CACHE.clear()


def _load_input_excel(run_id: str, sheet_name: str) -> pd.DataFrame:
    """
    Load a source table, prioritizing Supabase as the authoritative source of truth.
    Falls back to local Excel ONLY when Supabase is unconfigured or offline.
    """
    cache_key = (run_id, sheet_name.upper())
    if cache_key in _INPUT_EXCEL_SHEETS_CACHE:
        return _INPUT_EXCEL_SHEETS_CACHE[cache_key]

    table_map = {
        "PLANS": "plans",
        "PLAN_BENEFITS": "plan_benefits",
        "MEMBERS": "members",
        "MEMBER_ENROLLMENT": "member_enrollment",
        "MEMBER_HISTORY": "member_history",
        "CMS_MEASURES": "cms_measures",
        "PLAN_MEASURE_PERFORMANCE": "plan_measure_performance",
        "PART_D_MEDICATION_HISTORY": "part_d_medication_history",
    }
    tbl = table_map.get(sheet_name.upper())

    # 1. Authoritative Source: Supabase
    if tbl and SupabaseService.is_available():
        try:
            rows = SupabaseService.fetch_all(tbl)
            if rows:
                df = pd.DataFrame(rows)
                df.columns = df.columns.astype(str).str.strip()
                _INPUT_EXCEL_SHEETS_CACHE[cache_key] = df
                return df
            else:
                # Legitimate empty table in Supabase
                empty_df = pd.DataFrame()
                _INPUT_EXCEL_SHEETS_CACHE[cache_key] = empty_df
                return empty_df
        except Exception as exc:
            print(f"[result_service] WARNING: Supabase fetch for '{tbl}' failed: {exc}. Trying offline fallback.")

    # 2. Offline / Local fallback
    working_path = Path(OUTPUT_BASE_DIR) / run_id / "working" / "input.xlsx"
    if working_path.exists():
        try:
            df = pd.read_excel(working_path, sheet_name=sheet_name)
            df.columns = df.columns.astype(str).str.strip()
            _INPUT_EXCEL_SHEETS_CACHE[cache_key] = df
            return df
        except Exception:
            pass

    path = get_input_excel_path(run_id)
    if path and os.path.exists(path):
        try:
            df = pd.read_excel(path, sheet_name=sheet_name)
            df.columns = df.columns.astype(str).str.strip()
            _INPUT_EXCEL_SHEETS_CACHE[cache_key] = df
            return df
        except Exception:
            pass

    return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Plan Rating Calculation Helper (Unified Across Entire App)
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_plan_star_rating(plan_row: Any, plan_pmp: pd.DataFrame) -> float:
    """
    Calculate plan star rating consistently across Dashboard, Plans, and Optimization.
    Derives weighted average of measure_star from plan_measure_performance if overall_star_rating is NULL/0.
    """
    plan_rating = 0.0
    if isinstance(plan_row, (pd.Series, dict)):
        plan_rating = _clean_float(plan_row.get("overall_star_rating", 0.0))

    if plan_rating == 0.0 and not plan_pmp.empty and "measure_star" in plan_pmp.columns:
        if "weight" in plan_pmp.columns:
            weights = plan_pmp["weight"].apply(lambda w: _clean_float(w, default=1.0))
            stars = plan_pmp["measure_star"].apply(lambda s: _clean_float(s, default=0.0))
            total_weight = weights.sum()
            if total_weight > 0:
                plan_rating = round(float((stars * weights).sum() / total_weight), 2)
        else:
            plan_rating = round(float(plan_pmp["measure_star"].mean()), 2)

    return plan_rating


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard data
# ─────────────────────────────────────────────────────────────────────────────

def get_dashboard_data(run_id: str) -> Dict[str, Any]:
    """Aggregate dashboard metrics from pipeline outputs and current dataset."""
    _require_completed_run(run_id)

    # 1. Try Supabase final_recommendations first
    report_df = None
    recs = SupabaseService.fetch_all("final_recommendations", filters={"run_id": run_id})
    if recs:
        report_df = pd.DataFrame(recs).rename(columns={
            "member_id": "Member ID",
            "member_name": "Member Name",
            "age": "Age",
            "gender": "Gender",
            "total_gaps": "Total Gaps (Count)",
            "care_gaps": "Care Gap(s) (Gap Name)",
            "recommended_intervention": "Recommended Intervention",
            "gap_status": "Gap Status",
            "star_contribution": "Estimated Star Rating Improvement (Contribution)",
        })
    else:
        report_df = get_final_report_df(run_id)

    if report_df is None:
        raise HTTPException(status_code=404, detail="Final report not available.")

    # ── Source tables ─────────────────────────────────────────────────────────
    members_df = _load_input_excel(run_id, "MEMBERS")
    plans_df = _load_input_excel(run_id, "PLANS")
    measures_df = _load_input_excel(run_id, "CMS_MEASURES")
    pmp_df = _load_input_excel(run_id, "PLAN_MEASURE_PERFORMANCE")
    enrollment_df = _load_input_excel(run_id, "MEMBER_ENROLLMENT")

    # ── Summary metrics ───────────────────────────────────────────────────────
    total_members = int(members_df["member_id"].nunique()) if "member_id" in members_df.columns and not members_df.empty else int(enrollment_df["member_id"].nunique()) if "member_id" in enrollment_df.columns and not enrollment_df.empty else 0
    total_plans = int(plans_df["plan_id"].nunique()) if "plan_id" in plans_df.columns else 0
    cms_measures = int(len(measures_df))
    selected_members = int(len(report_df))

    # Total open care gaps from report or PMP
    if not pmp_df.empty and "denominator" in pmp_df.columns and "numerator" in pmp_df.columns:
        pmp_denom = pd.to_numeric(pmp_df["denominator"], errors="coerce").fillna(0)
        pmp_num = pd.to_numeric(pmp_df["numerator"], errors="coerce").fillna(0)
        total_open_care_gaps = _clean_int((pmp_denom - pmp_num).sum())
    elif "Total Gaps (Count)" in report_df.columns:
        total_open_care_gaps = _clean_int(report_df["Total Gaps (Count)"].sum())
    else:
        total_open_care_gaps = 0

    contrib_col = "Estimated Star Rating Improvement (Contribution)"
    if contrib_col in report_df.columns:
        contrib_vals = report_df[contrib_col].astype(str).str.replace("+", "", regex=False)
        contrib_vals = pd.to_numeric(contrib_vals, errors="coerce").fillna(0.0)
        total_star_contribution = _clean_float(contrib_vals.sum())
    else:
        total_star_contribution = 0.0

    avg_closure_prob = 0.0
    final_output_path = Path(OUTPUT_BASE_DIR) / run_id / "final_output.xlsx"
    if final_output_path.exists():
        try:
            fo_df = pd.read_excel(final_output_path)
            if "closure_probability" in fo_df.columns:
                avg_closure_prob = _clean_float(fo_df["closure_probability"].mean())
            elif "robust_quality" in fo_df.columns:
                avg_closure_prob = _clean_float(fo_df["robust_quality"].mean())
        except Exception:
            pass
    else:
        opt_recs = SupabaseService.fetch_all("optimization_results", filters={"run_id": run_id})
        if opt_recs:
            probs = [r.get("closure_probability") or r.get("robust_quality") or 0.0 for r in opt_recs]
            if probs:
                avg_closure_prob = _clean_float(sum(probs) / len(probs))

    # ── Gaps by plan (open gaps = denominator - numerator) ────────────────────
    gaps_by_plan = []
    if not pmp_df.empty and "plan_id" in pmp_df.columns and "denominator" in pmp_df.columns:
        pmp_copy = pmp_df.copy()
        denom = pd.to_numeric(pmp_copy["denominator"], errors="coerce").fillna(0)
        numer = pd.to_numeric(pmp_copy.get("numerator", 0), errors="coerce").fillna(0)
        pmp_copy["open_gaps"] = denom - numer
        plan_gaps = pmp_copy.groupby("plan_id")["open_gaps"].sum().to_dict()
        for pid in sorted(plan_gaps.keys()):
            gaps_by_plan.append({"plan_id": str(pid), "gaps": _clean_int(plan_gaps[pid])})

    # ── Plan performances (using unified star rating helper) ──────────────────
    plan_performances = []
    if "plan_id" in plans_df.columns:
        name_col = "plan_name" if "plan_name" in plans_df.columns else "plan_id"
        for _, row in plans_df.iterrows():
            pid = _clean_str(row["plan_id"])
            plan_pmp = pmp_df[pmp_df["plan_id"].astype(str).str.strip() == pid] if "plan_id" in pmp_df.columns else pd.DataFrame()
            plan_rating = _calculate_plan_star_rating(row, plan_pmp)
            plan_performances.append({
                "plan_id": pid,
                "plan_name": _clean_str(row.get(name_col, pid)),
                "rating": plan_rating,
            })

    # ── Intervention distribution ─────────────────────────────────────────────
    intervention_distribution = []
    if "Recommended Intervention" in report_df.columns:
        int_counts = report_df["Recommended Intervention"].value_counts().to_dict()
        for name, val in int_counts.items():
            intervention_distribution.append({"name": _clean_str(name), "value": _clean_int(val)})
    else:
        state = get_run_state(run_id)
        if state and state.intervention_counts:
            for name, val in state.intervention_counts.items():
                intervention_distribution.append({"name": _clean_str(name), "value": _clean_int(val)})

    # ── Care gap distribution ─────────────────────────────────────────────────
    care_gap_distribution = []
    gap_col = "Care Gap(s) (Gap Name)" if "Care Gap(s) (Gap Name)" in report_df.columns else "Care Gap(s)"
    if gap_col in report_df.columns:
        all_gaps = []
        for cg_str in report_df[gap_col].astype(str):
            gaps = [g.strip() for g in cg_str.split(";") if g.strip()]
            all_gaps.extend(gaps)
        from collections import Counter
        gap_counter = Counter(all_gaps)
        for gap_name, cnt in gap_counter.most_common(10):
            care_gap_distribution.append({"name": _clean_str(gap_name), "value": _clean_int(cnt)})

    # ── Improvement trend ─────────────────────────────────────────────────────
    improvement_trend = []
    if "rating_year" in pmp_df.columns and "measure_star" in pmp_df.columns:
        year_avg = pmp_df.groupby("rating_year")["measure_star"].mean().to_dict()
        for year, avg in sorted(year_avg.items()):
            improvement_trend.append({"year": _clean_int(year), "rating": round(_clean_float(avg), 2)})

    return {
        "summary": {
            "total_plans": total_plans,
            "total_members": total_members,
            "open_care_gaps": total_open_care_gaps,
            "cms_measures": cms_measures,
            "selected_members": selected_members,
            "avg_closure_probability": round(avg_closure_prob, 4),
            "total_star_contribution": round(total_star_contribution, 6),
        },
        "gaps_by_plan": gaps_by_plan,
        "plan_performances": plan_performances,
        "improvement_trend": improvement_trend,
        "intervention_distribution": intervention_distribution,
        "care_gap_distribution": care_gap_distribution,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Members data
# ─────────────────────────────────────────────────────────────────────────────

def get_members_data(run_id: str, page: int = 1, limit: int = 20,
                     search: str = "", plan_id: str = "") -> Dict[str, Any]:
    """Return paginated member list from final recommendations."""
    _require_completed_run(run_id)

    report_df = None
    recs = SupabaseService.fetch_all("final_recommendations", filters={"run_id": run_id})
    if recs:
        report_df = pd.DataFrame(recs).rename(columns={
            "member_id": "Member ID",
            "member_name": "Member Name",
            "age": "Age",
            "gender": "Gender",
            "total_gaps": "Total Gaps (Count)",
            "care_gaps": "Care Gap(s) (Gap Name)",
            "recommended_intervention": "Recommended Intervention",
            "gap_status": "Gap Status",
            "star_contribution": "Estimated Star Rating Improvement (Contribution)",
        })
    else:
        report_df = get_final_report_df(run_id)

    if report_df is None:
        raise HTTPException(status_code=404, detail="Final report not available.")

    enrollment_df = _load_input_excel(run_id, "MEMBER_ENROLLMENT")
    members_df = _load_input_excel(run_id, "MEMBERS")

    member_plan_map: Dict[str, str] = {}
    if "member_id" in enrollment_df.columns and "plan_id" in enrollment_df.columns:
        member_plan_map = dict(zip(
            enrollment_df["member_id"].astype(str).str.strip(),
            enrollment_df["plan_id"].astype(str).str.strip()
        ))

    dob_map: Dict[str, str] = {}
    cond_map: Dict[str, str] = {}
    if "member_id" in members_df.columns:
        m_ids = members_df["member_id"].astype(str).str.strip()
        if "date_of_birth" in members_df.columns:
            dob_map = dict(zip(m_ids, members_df["date_of_birth"].astype(str).str.strip()))
        if "condition" in members_df.columns:
            cond_map = dict(zip(m_ids, members_df["condition"].astype(str).str.strip()))

    records = []
    contrib_col = "Estimated Star Rating Improvement (Contribution)"
    gap_col = "Care Gap(s) (Gap Name)" if "Care Gap(s) (Gap Name)" in report_df.columns else "Care Gap(s)"

    report_records = report_df.to_dict(orient="records")
    for row in report_records:
        mid = _clean_str(row.get("Member ID", ""))
        records.append({
            "member_id": mid,
            "member_name": _clean_str(row.get("Member Name", "")),
            "dob": dob_map.get(mid, ""),
            "age": _clean_int(row.get("Age", 0)),
            "gender": _clean_str(row.get("Gender", "")),
            "condition": cond_map.get(mid, ""),
            "plan_id": member_plan_map.get(mid, ""),
            "care_gaps": _clean_str(row.get(gap_col, "")),
            "recommended_intervention": _clean_str(row.get("Recommended Intervention", "")),
            "gap_status": _clean_str(row.get("Gap Status", "Open")),
            "star_contribution": _clean_str(row.get(contrib_col, "")),
        })

    if search:
        search_lower = search.lower()
        records = [
            r for r in records
            if search_lower in r["member_id"].lower()
            or search_lower in r["member_name"].lower()
            or search_lower in r["care_gaps"].lower()
        ]
    if plan_id:
        records = [r for r in records if r["plan_id"] == plan_id]

    total = len(records)
    limit = max(1, min(limit, 200))
    page = max(1, page)
    total_pages = max(1, -(-total // limit))
    start = (page - 1) * limit
    end = start + limit
    page_records = records[start:end]

    return {
        "records": page_records,
        "pagination": {
            "total_records": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        },
    }


def get_member_detail(run_id: str, member_id: str) -> Dict[str, Any]:
    """Return full detail for a single selected member."""
    if not member_id or len(member_id) > 50 or not all(c.isalnum() or c in "-_" for c in member_id):
        raise HTTPException(status_code=400, detail="Invalid member_id.")

    _require_completed_run(run_id)

    report_df = None
    recs = SupabaseService.fetch_all("final_recommendations", filters={"run_id": run_id})
    if recs:
        report_df = pd.DataFrame(recs).rename(columns={
            "member_id": "Member ID",
            "member_name": "Member Name",
            "age": "Age",
            "gender": "Gender",
            "total_gaps": "Total Gaps (Count)",
            "care_gaps": "Care Gap(s) (Gap Name)",
            "recommended_intervention": "Recommended Intervention",
            "gap_status": "Gap Status",
            "star_contribution": "Estimated Star Rating Improvement (Contribution)",
        })
    else:
        report_df = get_final_report_df(run_id)

    if report_df is None:
        raise HTTPException(status_code=404, detail="Final report not available.")

    if "Member ID" not in report_df.columns:
        raise HTTPException(status_code=500, detail="Report missing Member ID column.")

    mask = report_df["Member ID"].astype(str).str.strip() == member_id.strip()
    member_rows = report_df[mask]
    if member_rows.empty:
        raise HTTPException(status_code=404, detail=f"Member '{member_id}' not found in selected members.")

    row = member_rows.iloc[0]
    contrib_col = "Estimated Star Rating Improvement (Contribution)"
    gap_col = "Care Gap(s) (Gap Name)" if "Care Gap(s) (Gap Name)" in report_df.columns else "Care Gap(s)"

    members_df = _load_input_excel(run_id, "MEMBERS")
    enrollment_df = _load_input_excel(run_id, "MEMBER_ENROLLMENT")

    member_meta = {}
    if "member_id" in members_df.columns:
        m_mask = members_df["member_id"].astype(str).str.strip() == member_id.strip()
        m_rows = members_df[m_mask]
        if not m_rows.empty:
            mr = m_rows.iloc[0]
            member_meta = {
                "dob": _clean_str(mr.get("date_of_birth", "")),
                "condition": _clean_str(mr.get("condition", "")),
            }

    enrollment_date = ""
    plan_id = ""
    if "member_id" in enrollment_df.columns and "plan_id" in enrollment_df.columns:
        e_mask = enrollment_df["member_id"].astype(str).str.strip() == member_id.strip()
        e_rows = enrollment_df[e_mask]
        if not e_rows.empty:
            er = e_rows.iloc[-1]
            plan_id = _clean_str(er["plan_id"])
            enrollment_date = _clean_str(er.get("enrollment_start_date") or er.get("start_date", ""))

    plan_type = ""
    health_plan_display = plan_id
    plans_df = _load_input_excel(run_id, "PLANS")
    if "plan_id" in plans_df.columns and plan_id:
        p_mask = plans_df["plan_id"].astype(str).str.strip() == plan_id.strip()
        p_rows = plans_df[p_mask]
        if not p_rows.empty:
            pr = p_rows.iloc[0]
            plan_type = _clean_str(pr.get("plan_type", ""))
            plan_name = _clean_str(pr.get("plan_name", ""))
            if plan_name:
                health_plan_display = f"{plan_id} - {plan_name}"

    care_gaps_str = _clean_str(row.get(gap_col, ""))
    gap_names = [g.strip() for g in care_gaps_str.split(";") if g.strip()]
    care_gap_list = [{"care_gap_name": g, "measure_id": "", "status": "Open"} for g in gap_names]
    gap_count = _clean_int(row.get("Total Gaps (Count)", len(gap_names)))

    star_val_str = _clean_str(row.get(contrib_col, ""))
    star_numeric = _clean_float(star_val_str.replace("+", "").replace(",", "") or 0)

    return {
        "member_id": member_id,
        "member_name": _clean_str(row.get("Member Name", "")),
        "overall_priority": "High" if gap_count >= 4 else ("Medium" if gap_count >= 2 else "Low"),
        "priority_score": float(gap_count),
        "details": {
            "health_plan": health_plan_display,
            "dob": member_meta.get("dob", ""),
            "age": _clean_int(row.get("Age", 0)),
            "gender": _clean_str(row.get("Gender", "")),
            "conditions": member_meta.get("condition", ""),
            "enrollment_date": enrollment_date,
            "plan_type": plan_type,
        },
        "gaps_summary": {
            "open_care_gaps": gap_count,
            "closed_care_gaps": 0,
            "high_priority_gaps": gap_count,
        },
        "care_gaps": care_gap_list,
        "recommended_intervention": _clean_str(row.get("Recommended Intervention", "")),
        "closure_probability": star_numeric,
        "star_contribution": star_val_str,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Plans data
# ─────────────────────────────────────────────────────────────────────────────

def get_plan_data(run_id: str, plan_id: str) -> Dict[str, Any]:
    """Return plan-level details from current Supabase source tables."""
    _require_completed_run(run_id)

    plans_df = _load_input_excel(run_id, "PLANS")
    pmp_df = _load_input_excel(run_id, "PLAN_MEASURE_PERFORMANCE")
    enrollment_df = _load_input_excel(run_id, "MEMBER_ENROLLMENT")
    benefits_df = _load_input_excel(run_id, "PLAN_BENEFITS")
    report_df = get_final_report_df(run_id)

    if "plan_id" not in plans_df.columns:
        raise HTTPException(status_code=500, detail="PLANS table missing plan_id column.")
    plan_mask = plans_df["plan_id"].astype(str).str.strip() == plan_id.strip()
    plan_rows = plans_df[plan_mask]
    if plan_rows.empty:
        raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found.")
    plan_row = plan_rows.iloc[0]

    # Total members enrolled in this plan
    total_members_in_plan = 0
    selected_in_plan = 0
    if "plan_id" in enrollment_df.columns and "member_id" in enrollment_df.columns:
        plan_members = enrollment_df[enrollment_df["plan_id"].astype(str).str.strip() == plan_id.strip()]
        total_members_in_plan = int(plan_members["member_id"].nunique())

        if report_df is not None and "Member ID" in report_df.columns:
            selected_ids = set(report_df["Member ID"].astype(str).str.strip())
            selected_in_plan = int(plan_members["member_id"].astype(str).str.strip().isin(selected_ids).sum())

    plan_pmp = pmp_df[pmp_df["plan_id"].astype(str).str.strip() == plan_id.strip()] if "plan_id" in pmp_df.columns else pd.DataFrame()

    total_care_gaps = _clean_int(plan_pmp["denominator"].sum()) if "denominator" in plan_pmp.columns else 0
    closed_care_gaps = _clean_int(plan_pmp["numerator"].sum()) if "numerator" in plan_pmp.columns else 0
    open_care_gaps = max(0, total_care_gaps - closed_care_gaps)

    # Measures list for this plan
    measures_list = []
    if not plan_pmp.empty:
        for _, m_row in plan_pmp.iterrows():
            measures_list.append({
                "measure_id": _clean_str(m_row.get("measure_id", "")),
                "performance_value": _clean_float(m_row.get("performance_value", 0)),
                "measure_star": _clean_float(m_row.get("measure_star", 0)),
                "weight": _clean_float(m_row.get("weight", 1), default=1.0),
            })

    # Improvement trend (historical or current)
    improvement_trend = []
    if "rating_year" in plan_pmp.columns and "measure_star" in plan_pmp.columns:
        year_avg = plan_pmp.groupby("rating_year")["measure_star"].mean().to_dict()
        for year, avg in sorted(year_avg.items()):
            improvement_trend.append({"year": _clean_int(year), "rating": round(_clean_float(avg), 2)})

    # Care gaps resolved over time
    resolved_over_time = []
    if "rating_year" in plan_pmp.columns and "numerator" in plan_pmp.columns:
        year_num = plan_pmp.groupby("rating_year")["numerator"].sum().to_dict()
        for year, val in sorted(year_num.items()):
            resolved_over_time.append({"year": _clean_int(year), "resolved": _clean_int(val)})

    # Plan rating using unified calculation helper
    plan_rating = _calculate_plan_star_rating(plan_row, plan_pmp)

    # Rating year and start date
    rating_year = _clean_int(plan_pmp["rating_year"].max()) if "rating_year" in plan_pmp.columns and len(plan_pmp) > 0 else 2026
    if rating_year == 0 and "rating_year" in plan_row:
        rating_year = _clean_int(plan_row.get("rating_year", 2026))

    start_date = "01/01/2024"
    if "plan_id" in enrollment_df.columns:
        p_enroll = enrollment_df[enrollment_df["plan_id"].astype(str).str.strip() == plan_id.strip()]
        if not p_enroll.empty:
            for col in ["enrollment_start_date", "start_date", "effective_date"]:
                if col in p_enroll.columns and p_enroll[col].dropna().any():
                    start_date = _clean_str(p_enroll[col].dropna().iloc[0])
                    break

    return {
        "summary": {
            "total_members": total_members_in_plan,
            "open_care_gaps": open_care_gaps,
            "total_care_gaps": total_care_gaps,
            "closed_care_gaps": closed_care_gaps,
            "plan_rating": plan_rating,
            "selected_members": selected_in_plan,
        },
        "gaps_by_status": [
            {"name": "Open", "value": open_care_gaps},
            {"name": "Closed", "value": closed_care_gaps},
        ],
        "resolved_over_time": resolved_over_time,
        "improvement_trend": improvement_trend,
        "details": {
            "plan_id": _clean_str(plan_row.get("plan_id", "")),
            "plan_name": _clean_str(plan_row.get("plan_name", "")),
            "contract_id": _clean_str(plan_row.get("contract_id", "")),
            "plan_type": _clean_str(plan_row.get("plan_type", "")),
            "county": _clean_str(plan_row.get("state", "")),
            "rating_year": rating_year,
            "start_date": start_date,
        },
        "measures": measures_list,
    }


def get_plans_list(run_id: str) -> List[Dict[str, Any]]:
    """Return list of all available plans for a run with calculated star ratings."""
    _require_completed_run(run_id)
    plans_df = _load_input_excel(run_id, "PLANS")
    pmp_df = _load_input_excel(run_id, "PLAN_MEASURE_PERFORMANCE")
    enrollment_df = _load_input_excel(run_id, "MEMBER_ENROLLMENT")
    if "plan_id" not in plans_df.columns:
        return []

    plan_member_counts = {}
    if "plan_id" in enrollment_df.columns and "member_id" in enrollment_df.columns:
        plan_member_counts = enrollment_df.groupby("plan_id")["member_id"].nunique().to_dict()

    plans = []
    name_col = "plan_name" if "plan_name" in plans_df.columns else "plan_id"
    for _, row in plans_df.iterrows():
        pid = _clean_str(row.get("plan_id"))
        if pid:
            plan_pmp = pmp_df[pmp_df["plan_id"].astype(str).str.strip() == pid] if "plan_id" in pmp_df.columns else pd.DataFrame()
            plan_rating = _calculate_plan_star_rating(row, plan_pmp)
            plans.append({
                "plan_id": pid,
                "plan_name": _clean_str(row.get(name_col, pid)),
                "rating": plan_rating,
                "plan_type": _clean_str(row.get("plan_type", "")),
                "state": _clean_str(row.get("state", "")),
                "total_members": int(plan_member_counts.get(pid, 0)),
            })
    return plans


# ─────────────────────────────────────────────────────────────────────────────
# CMS Measures
# ─────────────────────────────────────────────────────────────────────────────

def get_measures_data(run_id: str, plan_id: str = "") -> Dict[str, Any]:
    """Return CMS measures from current source tables, optionally filtered by plan."""
    _require_completed_run(run_id)

    measures_df = _load_input_excel(run_id, "CMS_MEASURES")
    pmp_df = _load_input_excel(run_id, "PLAN_MEASURE_PERFORMANCE")

    if plan_id and not pmp_df.empty and "plan_id" in pmp_df.columns:
        plan_pmp = pmp_df[pmp_df["plan_id"].astype(str).str.strip() == plan_id.strip()]
        if not plan_pmp.empty and "measure_id" in plan_pmp.columns:
            plan_measure_ids = set(plan_pmp["measure_id"].astype(str).str.strip())
            if "measure_id" in measures_df.columns:
                measures_df = measures_df[measures_df["measure_id"].astype(str).str.strip().isin(plan_measure_ids)]
            pmp_df = plan_pmp

    avg_perf: Dict[str, float] = {}
    avg_star: Dict[str, float] = {}
    if "measure_id" in pmp_df.columns:
        if "performance_value" in pmp_df.columns:
            avg_perf = pmp_df.groupby("measure_id")["performance_value"].mean().to_dict()
        if "measure_star" in pmp_df.columns:
            avg_star = pmp_df.groupby("measure_id")["measure_star"].mean().to_dict()

    records = []
    rating_year = 2026
    if "rating_year" in pmp_df.columns and len(pmp_df) > 0:
        rating_year = _clean_int(pmp_df["rating_year"].max())

    for _, row in measures_df.iterrows():
        mid = _clean_str(row.get("measure_id", ""))
        official_mid = _clean_str(row.get("official_measure_id", mid))
        records.append({
            "part": _clean_str(row.get("part", "")),
            "measure_id": official_mid or mid,
            "measure_name": _clean_str(row.get("measure_name", "")),
            "measure_type": _clean_str(row.get("measure_type", "")),
            "domain": _clean_str(row.get("domain", "")),
            "description": _clean_str(row.get("description", "")),
            "weight": _clean_float(row.get("weight", 1), default=1.0),
            "performance_value": round(_clean_float(avg_perf.get(mid)), 4) if mid in avg_perf else None,
            "measure_star": round(_clean_float(avg_star.get(mid)), 2) if mid in avg_star else None,
        })

    high_priority = sum(1 for r in records if r["measure_star"] is not None and r["measure_star"] < 4.0)

    return {
        "summary": {
            "total_measures": len(records),
            "high_priority_measures": high_priority,
            "rating_year": rating_year,
        },
        "records": records,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Optimization results
# ─────────────────────────────────────────────────────────────────────────────

def get_optimization_results(run_id: str, plan_id: str = "", max_members: int = 0) -> Dict[str, Any]:
    """
    Return optimization results from final recommendations.
    
    Args:
        run_id: Pipeline run identifier.
        plan_id: Filter results to members enrolled in this plan.
        max_members: If > 0, limit the outreach list to this many members (budget constraint).
    """
    _require_completed_run(run_id)

    # 1. Fetch final recommendations from Supabase first
    report_df = None
    recs = SupabaseService.fetch_all("final_recommendations", filters={"run_id": run_id})
    if recs:
        report_df = pd.DataFrame(recs).rename(columns={
            "member_id": "Member ID",
            "member_name": "Member Name",
            "age": "Age",
            "gender": "Gender",
            "total_gaps": "Total Gaps (Count)",
            "care_gaps": "Care Gap(s) (Gap Name)",
            "recommended_intervention": "Recommended Intervention",
            "gap_status": "Gap Status",
            "star_contribution": "Estimated Star Rating Improvement (Contribution)",
        })
    else:
        report_df = get_final_report_df(run_id)

    if report_df is None:
        raise HTTPException(status_code=404, detail="Optimization results not available.")

    # ── Plan filter ──────────────────────────────────────────────────────────
    plan_total_members = 0
    if plan_id:
        enrollment_df = _load_input_excel(run_id, "MEMBER_ENROLLMENT")
        if "member_id" in enrollment_df.columns and "plan_id" in enrollment_df.columns:
            plan_enroll = enrollment_df[
                enrollment_df["plan_id"].astype(str).str.strip() == plan_id.strip()
            ]
            plan_total_members = int(plan_enroll["member_id"].nunique())
            plan_member_ids = set(plan_enroll["member_id"].astype(str).str.strip())
            if "Member ID" in report_df.columns:
                report_df = report_df[
                    report_df["Member ID"].astype(str).str.strip().isin(plan_member_ids)
                ]

    # ── Budget (max_members) slice ───────────────────────────────────────────
    if max_members > 0 and len(report_df) > max_members:
        report_df = report_df.head(max_members)

    # ── Plan star rating calculations ─────────────────────────────────────────
    prev_plan_rating = 0.0
    projected_plan_rating = 0.0
    star_increase = 0.0
    if plan_id:
        plans_df = _load_input_excel(run_id, "PLANS")
        pmp_df = _load_input_excel(run_id, "PLAN_MEASURE_PERFORMANCE")
        plan_rows = plans_df[plans_df["plan_id"].astype(str).str.strip() == plan_id.strip()] if not plans_df.empty and "plan_id" in plans_df.columns else pd.DataFrame()
        plan_row = plan_rows.iloc[0] if not plan_rows.empty else pd.Series()
        plan_pmp = pmp_df[pmp_df["plan_id"].astype(str).str.strip() == plan_id.strip()] if not pmp_df.empty and "plan_id" in pmp_df.columns else pd.DataFrame()
        prev_plan_rating = _calculate_plan_star_rating(plan_row, plan_pmp)

        # Star increase: sum contributions of selected members for this plan
        contrib_col = "Estimated Star Rating Improvement (Contribution)"
        if contrib_col in report_df.columns and len(report_df) > 0:
            c_vals = pd.to_numeric(report_df[contrib_col].astype(str).str.replace("+", "", regex=False), errors="coerce").fillna(0.0)
            star_increase = round(float(c_vals.sum()), 4)
            projected_plan_rating = round(min(5.0, prev_plan_rating + star_increase), 4)
        else:
            projected_plan_rating = prev_plan_rating
            star_increase = 0.0

    contrib_col = "Estimated Star Rating Improvement (Contribution)"
    gap_col = "Care Gap(s) (Gap Name)" if "Care Gap(s) (Gap Name)" in report_df.columns else "Care Gap(s)"
    records = []
    for i, (_, row) in enumerate(report_df.iterrows(), start=1):
        records.append({
            "s_no": i,
            "member_id": _clean_str(row.get("Member ID", "")),
            "member_name": _clean_str(row.get("Member Name", "")),
            "age": _clean_int(row.get("Age", 0)),
            "gender": _clean_str(row.get("Gender", "")),
            "gap_count": _clean_int(row.get("Total Gaps (Count)", 0)),
            "care_gaps": _clean_str(row.get(gap_col, "")),
            "recommended_intervention": _clean_str(row.get("Recommended Intervention", "")),
            "gap_status": _clean_str(row.get("Gap Status", "Open")),
            "contribution": _clean_str(row.get(contrib_col, "")),
        })

    int_breakdown: Dict[str, int] = {}
    for r in records:
        iv = r["recommended_intervention"]
        int_breakdown[iv] = int_breakdown.get(iv, 0) + 1

    total_gaps = sum(r["gap_count"] for r in records)

    avg_prob = 0.0
    final_output_path = Path(OUTPUT_BASE_DIR) / run_id / "final_output.xlsx"
    if final_output_path.exists():
        try:
            fo_df = pd.read_excel(final_output_path)
            if "closure_probability" in fo_df.columns:
                avg_prob = _clean_float(fo_df["closure_probability"].mean())
        except Exception:
            pass

    return {
        "records": records,
        "summary": {
            "total_selected": len(records),
            "total_gaps": total_gaps,
            "plan_total_members": plan_total_members,
            "intervention_breakdown": int_breakdown,
            "avg_closure_probability": round(avg_prob, 4),
            "prev_plan_rating": prev_plan_rating,
            "projected_plan_rating": projected_plan_rating,
            "star_increase": star_increase,
        },
    }

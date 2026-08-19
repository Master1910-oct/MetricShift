"""
Dataset management service for Metric Shift.

Handles:
1. Initial dataset validation and seeding into 8 current Supabase source tables.
2. Optimized Member Update validation, authorization check, and targeted upserts.
3. Exporting the FULL CURRENT DATABASE to a temporary 8-sheet Excel workbook
   for execution by the validated pipeline.

CRITICAL RULES:
- Supabase source tables represent the SINGLE CURRENT LIVE DATASET (no dataset_versions).
- For Member Updates: ONLY authorized optimized members are updated.
- If ANY uploaded member is unauthorized, the ENTIRE update is rejected atomically.
- Unaffected members remain completely untouched.
- Plan and measure tables are NEVER modified during a member update.
- The next pipeline run always executes against the FULL CURRENT DATABASE.
"""

import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional
import pandas as pd
from fastapi import HTTPException

from backend.services.supabase_service import SupabaseService, sanitize_dataframe


# ─────────────────────────────────────────────────────────────────────────────
# Schema Definitions for 8 Source Tables
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_SOURCE_SHEETS = [
    "PLANS",
    "PLAN_BENEFITS",
    "MEMBERS",
    "MEMBER_ENROLLMENT",
    "MEMBER_HISTORY",
    "CMS_MEASURES",
    "PLAN_MEASURE_PERFORMANCE",
    "PART_D_MEDICATION_HISTORY",
]

MEMBER_SPECIFIC_SHEETS = {
    "MEMBERS": {"table": "members", "pk": "member_condition_id", "member_col": "member_id"},
    "MEMBER_ENROLLMENT": {"table": "member_enrollment", "pk": "enrollment_id", "member_col": "member_id"},
    "MEMBER_HISTORY": {"table": "member_history", "pk": "history_id", "member_col": "member_id"},
    "PART_D_MEDICATION_HISTORY": {"table": "part_d_medication_history", "pk": "rx_history_id", "member_col": "member_id"},
}

PLAN_MEASURE_SHEETS = {
    "PLANS": {"table": "plans", "pk": "plan_id"},
    "PLAN_BENEFITS": {"table": "plan_benefits", "pk": "benefit_id"},
    "CMS_MEASURES": {"table": "cms_measures", "pk": "measure_id"},
    "PLAN_MEASURE_PERFORMANCE": {"table": "plan_measure_performance", "pk": "performance_id"},
}

SHEET_TO_TABLE_CONFIG = {
    "PLANS": {"table": "plans", "pk": "plan_id"},
    "PLAN_BENEFITS": {"table": "plan_benefits", "pk": "benefit_id"},
    "MEMBERS": {"table": "members", "pk": "member_condition_id"},
    "MEMBER_ENROLLMENT": {"table": "member_enrollment", "pk": "enrollment_id"},
    "MEMBER_HISTORY": {"table": "member_history", "pk": "history_id"},
    "CMS_MEASURES": {"table": "cms_measures", "pk": "measure_id"},
    "PLAN_MEASURE_PERFORMANCE": {"table": "plan_measure_performance", "pk": "performance_id"},
    "PART_D_MEDICATION_HISTORY": {"table": "part_d_medication_history", "pk": "rx_history_id"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Date Columns That Require ISO Normalisation Before Supabase Upsert
# ─────────────────────────────────────────────────────────────────────────────

# Maps canonical sheet name -> list of column names that hold DATE values.
# Only these columns are touched; every other column is left as-is.
SHEET_DATE_COLUMNS: Dict[str, List[str]] = {
    "MEMBERS": ["date_of_birth"],
    "MEMBER_ENROLLMENT": ["enrollment_start_date", "enrollment_end_date"],
    "MEMBER_HISTORY": ["service_date", "action_date", "completion_date"],
    "PART_D_MEDICATION_HISTORY": ["fill_date"],
}

# Regex for DD-MM-YYYY strings (the format produced by the Excel workbook)
_DD_MM_YYYY = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")
# Regex for already-ISO YYYY-MM-DD strings
_YYYY_MM_DD = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_date_value(val: Any, *, column_name: str = "") -> Optional[str]:
    """
    Convert a single date value to an ISO 'YYYY-MM-DD' string.

    Supported input types:
      - None / NaN / NaT                -> None (becomes SQL NULL)
      - 'DD-MM-YYYY' string             -> 'YYYY-MM-DD'
      - 'YYYY-MM-DD' string             -> unchanged
      - Python date / datetime object   -> isoformat()[:10]
      - pandas Timestamp                -> .date().isoformat()

    Raises ValueError for non-empty values that cannot be parsed, so that
    data quality problems surface immediately rather than silently becoming NULL.
    """
    # --- Null-like values ---
    if val is None or val is pd.NaT:
        return None
    try:
        if pd.isna(val):  # catches float NaN, numpy NaN
            return None
    except (TypeError, ValueError):
        pass

    # --- Native date/datetime/Timestamp ---
    if isinstance(val, pd.Timestamp):
        if pd.isna(val):
            return None
        return val.date().isoformat()
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()

    # --- String handling ---
    val_str = str(val).strip()
    if not val_str:
        return None

    # DD-MM-YYYY  (workbook format)
    m = _DD_MM_YYYY.match(val_str)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        iso = f"{year}-{month}-{day}"
        # Validate that the resulting date is real
        try:
            datetime.strptime(iso, "%Y-%m-%d")
        except ValueError:
            raise ValueError(
                f"Invalid date '{val_str}' in column '{column_name}': "
                f"converted to '{iso}' which is not a real calendar date."
            )
        return iso

    # YYYY-MM-DD  (already ISO)
    if _YYYY_MM_DD.match(val_str):
        try:
            datetime.strptime(val_str, "%Y-%m-%d")
        except ValueError:
            raise ValueError(
                f"Invalid ISO date '{val_str}' in column '{column_name}'."
            )
        return val_str

    # Unrecognised format — fail loudly rather than silently drop
    raise ValueError(
        f"Unrecognised date format '{val_str}' in column '{column_name}'. "
        "Expected 'DD-MM-YYYY' or 'YYYY-MM-DD'."
    )


def normalize_date_columns(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """
    Normalise the date columns defined in SHEET_DATE_COLUMNS for the given
    sheet.  Operates on a copy; the original DataFrame is not mutated.
    Columns that are not present in the DataFrame are silently skipped.
    """
    date_cols = SHEET_DATE_COLUMNS.get(sheet_name.upper(), [])
    if not date_cols:
        return df

    df = df.copy()
    for col in date_cols:
        if col not in df.columns:
            continue
        try:
            df[col] = df[col].apply(lambda v: normalize_date_value(v, column_name=col))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Date normalisation error in sheet '{sheet_name}', column '{col}': {exc}",
            )
    return df


class DatasetService:
    @staticmethod
    def validate_initial_workbook(file_path: str) -> Dict[str, pd.DataFrame]:
        """
        Validate that the workbook contains all 8 required sheets and proper columns.
        Returns dict of sheet_name -> DataFrame.
        """
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Workbook file not found.")

        try:
            xl = pd.ExcelFile(file_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid Excel workbook: {exc}")

        sheet_names_upper = {s.upper(): s for s in xl.sheet_names}
        missing_sheets = [s for s in REQUIRED_SOURCE_SHEETS if s not in sheet_names_upper]
        if missing_sheets:
            raise HTTPException(
                status_code=400,
                detail=f"Initial dataset missing required sheet(s): {', '.join(missing_sheets)}",
            )

        dfs: Dict[str, pd.DataFrame] = {}
        for canonical_name in REQUIRED_SOURCE_SHEETS:
            actual_name = sheet_names_upper[canonical_name]
            df = xl.parse(actual_name)
            df.columns = df.columns.astype(str).str.strip().str.lower()
            pk_col = SHEET_TO_TABLE_CONFIG[canonical_name]["pk"]
            if pk_col not in df.columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"Sheet '{canonical_name}' is missing primary key column '{pk_col}'.",
                )
            dfs[canonical_name] = df

        return dfs

    @staticmethod
    def sync_initial_dataset(file_path: str, run_id: str, source_file_name: Optional[str] = None) -> Dict[str, int]:
        """
        Ingest the complete 8-sheet Excel workbook and populate current Supabase source tables.
        """
        dfs = DatasetService.validate_initial_workbook(file_path)
        row_counts = {}

        for canonical_name, df in dfs.items():
            cfg = SHEET_TO_TABLE_CONFIG[canonical_name]
            table_name = cfg["table"]
            pk_col = cfg["pk"]

            # Normalise date columns from DD-MM-YYYY -> ISO YYYY-MM-DD before upsert
            df = normalize_date_columns(df, canonical_name)

            records = sanitize_dataframe(df)
            inserted = SupabaseService.bulk_upsert(
                table_name=table_name,
                records=records,
                on_conflict=pk_col,
            )
            row_counts[table_name] = inserted

        # Audit log in upload_events
        all_members = set()
        if "MEMBERS" in dfs and "member_id" in dfs["MEMBERS"].columns:
            all_members = set(dfs["MEMBERS"]["member_id"].dropna().astype(str).str.strip())

        file_name = source_file_name or (Path(file_path).name if file_path else "")
        SupabaseService.log_upload_event(
            upload_type="initial_upload",
            source_file_name=file_name,
            run_id=run_id,
            affected_member_count=len(all_members),
            inserted_row_count=sum(row_counts.values()),
            status="completed",
        )

        return row_counts

    @staticmethod
    def validate_and_apply_member_update(
        file_path: str, run_id: str, source_file_name: Optional[str] = None
    ) -> Tuple[List[str], Dict[str, int], str]:
        """
        Validate and apply targeted member updates for authorized optimized members.

        Workflow:
        1. Read & validate workbook structure.
        2. Validate duplicate source primary keys (reject entire upload if duplicates exist).
        3. Extract uploaded member IDs across all member sheets (reject if empty).
        4. Query latest completed optimization run (reject if no completed run exists).
        5. Authorize: If ANY uploaded member is NOT authorized, reject the entire update.
        6. Apply targeted upsert ONLY for member-specific tables (MEMBERS, MEMBER_ENROLLMENT,
           MEMBER_HISTORY, PART_D_MEDICATION_HISTORY).
        7. Leave PLANS, PLAN_BENEFITS, CMS_MEASURES, PLAN_MEASURE_PERFORMANCE completely untouched.
        8. Record canonical audit in upload_events without PHI.

        Returns:
            (authorized_member_ids, row_counts_dict, authorization_run_id)
        """
        start_iso = datetime.now(timezone.utc).isoformat()
        file_name = source_file_name or (Path(file_path).name if file_path else "")
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Update workbook file not found.")

        try:
            xl = pd.ExcelFile(file_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid Excel workbook: {exc}")

        sheet_names_upper = {s.upper(): s for s in xl.sheet_names}

        # Identify uploaded member-specific sheets
        uploaded_member_sheets: Dict[str, pd.DataFrame] = {}
        for s_upper, s_actual in sheet_names_upper.items():
            if s_upper in MEMBER_SPECIFIC_SHEETS:
                df = xl.parse(s_actual)
                df.columns = df.columns.astype(str).str.strip().str.lower()
                uploaded_member_sheets[s_upper] = df

        if not uploaded_member_sheets:
            error_msg = "Member update workbook contains no member sheets (expected MEMBERS, MEMBER_ENROLLMENT, etc.)"
            end_iso = datetime.now(timezone.utc).isoformat()
            SupabaseService.log_upload_event(
                upload_type="member_update",
                source_file_name=file_name,
                run_id=run_id,
                status="failed",
                error_message=error_msg,
                started_at=start_iso,
                completed_at=end_iso,
            )
            raise HTTPException(status_code=400, detail=error_msg)

        # 1. Validate duplicate source keys in uploaded sheets (Requirement 6)
        for s_name, df in uploaded_member_sheets.items():
            pk_col = MEMBER_SPECIFIC_SHEETS[s_name]["pk"]
            if pk_col in df.columns and not df.empty:
                # Find non-null duplicates
                pk_series = df[pk_col].dropna().astype(str).str.strip()
                pk_series = pk_series[pk_series != ""]
                dups = pk_series[pk_series.duplicated()].unique().tolist()
                if dups:
                    error_msg = (
                        f"Member update rejected: duplicate primary key '{pk_col}' found in sheet '{s_name}'. "
                        f"Duplicate values: {dups[:5]}."
                    )
                    end_iso = datetime.now(timezone.utc).isoformat()
                    SupabaseService.log_upload_event(
                        upload_type="member_update",
                        source_file_name=file_name,
                        run_id=run_id,
                        status="failed",
                        error_message=error_msg,
                        started_at=start_iso,
                        completed_at=end_iso,
                    )
                    raise HTTPException(status_code=400, detail=error_msg)

        # 2. Extract uploaded member IDs across all member sheets
        uploaded_member_ids: Set[str] = set()
        for s_name, df in uploaded_member_sheets.items():
            member_col = MEMBER_SPECIFIC_SHEETS[s_name]["member_col"]
            if member_col in df.columns and not df.empty:
                ids = df[member_col].dropna().astype(str).str.strip()
                ids = ids[ids != ""].tolist()
                uploaded_member_ids.update(ids)

        if not uploaded_member_ids:
            error_msg = "Member update rejected: no valid member records or member IDs found in update workbook."
            end_iso = datetime.now(timezone.utc).isoformat()
            SupabaseService.log_upload_event(
                upload_type="member_update",
                source_file_name=file_name,
                run_id=run_id,
                status="failed",
                error_message=error_msg,
                started_at=start_iso,
                completed_at=end_iso,
            )
            raise HTTPException(status_code=400, detail=error_msg)

        # 3. Retrieve authorized member IDs from latest completed optimization run (Requirement 2 & 8)
        auth_run_id, authorized_members = SupabaseService.get_latest_completed_optimization_run()
        if not auth_run_id or not authorized_members:
            error_msg = "Member update rejected: no completed optimization run found to authorize member updates."
            end_iso = datetime.now(timezone.utc).isoformat()
            SupabaseService.log_upload_event(
                upload_type="member_update",
                source_file_name=file_name,
                run_id=run_id,
                status="failed",
                error_message=error_msg,
                started_at=start_iso,
                completed_at=end_iso,
            )
            raise HTTPException(status_code=400, detail=error_msg)

        # 4. Strictly check authorization against latest completed optimization run
        unauthorized = uploaded_member_ids - authorized_members
        if unauthorized:
            sample_unauthorized = list(sorted(unauthorized))[:5]
            error_msg = (
                f"Member update rejected: {len(unauthorized)} member(s) not present in latest completed "
                f"optimization run '{auth_run_id}'. Examples: {sample_unauthorized}. "
                f"No database modifications were made."
            )
            end_iso = datetime.now(timezone.utc).isoformat()
            SupabaseService.log_upload_event(
                upload_type="member_update",
                source_file_name=file_name,
                run_id=run_id,
                authorized_optimization_run_id=auth_run_id,
                affected_member_count=0,
                inserted_row_count=0,
                updated_row_count=0,
                rejected_member_count=len(unauthorized),
                status="failed",
                error_message=error_msg,
                started_at=start_iso,
                completed_at=end_iso,
            )
            raise HTTPException(status_code=400, detail=error_msg)

        # 5. Apply targeted upsert ONLY for member-specific tables (Requirement 3, 4, 5)
        row_counts: Dict[str, int] = {}
        total_inserted = 0
        total_updated = 0

        for s_name, df in uploaded_member_sheets.items():
            if df.empty:
                continue

            cfg = MEMBER_SPECIFIC_SHEETS[s_name]
            table_name = cfg["table"]
            pk_col = cfg["pk"]
            member_col = cfg["member_col"]

            # Filter dataframe to only include authorized members
            if member_col in df.columns:
                target_df = df[df[member_col].astype(str).str.strip().isin(uploaded_member_ids)]
            else:
                target_df = df

            if target_df.empty:
                continue

            # Calculate inserted vs updated rows by checking existing primary keys in database
            uploaded_pks = target_df[pk_col].dropna().astype(str).str.strip().tolist()
            existing_rows = SupabaseService.fetch_all(table_name, columns=pk_col)
            existing_pks = {str(r.get(pk_col, "")).strip() for r in existing_rows if r.get(pk_col)}

            sheet_updated = len([pk for pk in uploaded_pks if pk in existing_pks])
            sheet_inserted = len([pk for pk in uploaded_pks if pk not in existing_pks])

            # Normalise date columns from DD-MM-YYYY -> ISO YYYY-MM-DD before upsert
            target_df = normalize_date_columns(target_df, s_name)

            records = sanitize_dataframe(target_df)
            inserted = SupabaseService.bulk_upsert(
                table_name=table_name,
                records=records,
                on_conflict=pk_col,
            )
            row_counts[table_name] = inserted
            total_updated += sheet_updated
            total_inserted += sheet_inserted

        # 6. Log successful audit in upload_events (canonical)
        end_iso = datetime.now(timezone.utc).isoformat()
        SupabaseService.log_upload_event(
            upload_type="member_update",
            source_file_name=file_name,
            run_id=run_id,
            authorized_optimization_run_id=auth_run_id,
            affected_member_count=len(uploaded_member_ids),
            inserted_row_count=total_inserted,
            updated_row_count=total_updated,
            rejected_member_count=0,
            status="completed",
            error_message=None,
            started_at=start_iso,
            completed_at=end_iso,
        )

        return list(uploaded_member_ids), row_counts, auth_run_id

    @staticmethod
    def export_current_db_to_working_excel(output_excel_path: str, fallback_source_excel: Optional[str] = None) -> str:
        """
        Export the current live database from Supabase into a standard 8-sheet Excel file.
        This allows the validated pipeline orchestrator to execute against the current DB
        without any internal changes to the Rule Engine or ML models.
        """
        out_dir = Path(output_excel_path).parent
        out_dir.mkdir(parents=True, exist_ok=True)

        sheet_dfs: Dict[str, pd.DataFrame] = {}

        for canonical_name in REQUIRED_SOURCE_SHEETS:
            cfg = SHEET_TO_TABLE_CONFIG[canonical_name]
            table_name = cfg["table"]
            rows = SupabaseService.fetch_all(table_name)
            if rows:
                df = pd.DataFrame(rows)
                # Drop internal timestamps from working sheet if present
                df = df.drop(columns=["created_at", "updated_at"], errors="ignore")
                sheet_dfs[canonical_name] = df
            else:
                # If Supabase table is empty and fallback excel provided, read from fallback
                if fallback_source_excel and os.path.exists(fallback_source_excel):
                    try:
                        xl = pd.ExcelFile(fallback_source_excel)
                        names = {s.upper(): s for s in xl.sheet_names}
                        if canonical_name in names:
                            sheet_dfs[canonical_name] = xl.parse(names[canonical_name])
                    except Exception:
                        sheet_dfs[canonical_name] = pd.DataFrame()
                else:
                    sheet_dfs[canonical_name] = pd.DataFrame()

        with pd.ExcelWriter(output_excel_path, engine="openpyxl") as writer:
            for sheet_name, df in sheet_dfs.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)

        return str(output_excel_path)

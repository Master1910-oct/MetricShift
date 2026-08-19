"""
Supabase client service for Metric Shift.

Provides robust REST/PostgREST connectivity with:
- Batch upserts and inserts with chunking
- Pagination (Range header) for full-table streaming
- Complete NaN/NaT/None sanitization to valid database NULL values
- Atomic run & stage tracking
- Querying authorized optimization member IDs
- Seamless in-memory / local fallback for offline tests and CLI usage

CRITICAL SECURITY:
- SUPABASE_SECRET_KEY is read strictly from environment on the backend.
- Never returned in API responses or logs.
"""

import os
import math
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set, Tuple
import requests
import pandas as pd

# Automatically load .env if present
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Environment Configuration
# ─────────────────────────────────────────────────────────────────────────────

def get_supabase_url() -> str:
    return os.environ.get("SUPABASE_URL", "https://orpnoxylcdnaxftphanl.supabase.co").rstrip("/")


def get_supabase_key() -> str:
    return os.environ.get("SUPABASE_SECRET_KEY", "").strip()


SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "metricshift-files")


_SESSION: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Return a thread-safe requests.Session with connection pooling and retries."""
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=25,
            pool_maxsize=25,
            max_retries=requests.adapters.Retry(
                total=3,
                backoff_factor=0.3,
                status_forcelist=[502, 503, 504],
                raise_on_status=False,
            ),
        )
        _SESSION.mount("https://", adapter)
        _SESSION.mount("http://", adapter)
    return _SESSION


def is_supabase_configured() -> bool:
    """Check if Supabase credentials are configured in environment."""
    key = get_supabase_key()
    url = get_supabase_url()
    return bool(url and key and len(key) > 10)


def _get_headers() -> Dict[str, str]:
    """Build authenticated headers for Supabase REST API."""
    key = get_supabase_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


# ─────────────────────────────────────────────────────────────────────────────
# JSON Sanitization Helpers
# ─────────────────────────────────────────────────────────────────────────────

def sanitize_value(val: Any) -> Any:
    """Recursively sanitize NaN, NaT, Inf, numpy types to pure Python / JSON types."""
    if val is None or val is pd.NaT:
        return None
    if isinstance(val, (dict,)):
        return {k: sanitize_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [sanitize_value(v) for v in val]
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    if isinstance(val, (float, int)):
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    if isinstance(val, (pd.Timestamp, datetime)):
        return val.isoformat()
    return val


def sanitize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize a single dictionary row for database insertion."""
    clean = {}
    for k, v in record.items():
        clean[k] = sanitize_value(v)
    return clean


def sanitize_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert pandas DataFrame to a list of sanitized dictionaries."""
    if df is None or df.empty:
        return []
    # Replace numpy NaN with None
    df_clean = df.copy()
    records = df_clean.to_dict(orient="records")
    return [sanitize_record(r) for r in records]


# ─────────────────────────────────────────────────────────────────────────────
# In-Memory Fallback Cache (for offline testing & mock environment)
# ─────────────────────────────────────────────────────────────────────────────

_MOCK_STORAGE: Dict[str, List[Dict[str, Any]]] = {
    "plans": [],
    "plan_benefits": [],
    "members": [],
    "member_enrollment": [],
    "member_history": [],
    "cms_measures": [],
    "plan_measure_performance": [],
    "part_d_medication_history": [],
    "pipeline_runs": [],
    "pipeline_stages": [],
    "care_gaps": [],
    "ml_predictions": [],
    "intervention_selections": [],
    "optimization_results": [],
    "star_rating_contributions": [],
    "final_recommendations": [],
    "dataset_update_logs": [],
    "upload_events": [],
}


_SCHEMA_COLUMNS_CACHE: Dict[str, Set[str]] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Primary Supabase Service Functions
# ─────────────────────────────────────────────────────────────────────────────

class SupabaseService:
    @staticmethod
    def get_table_columns(table_name: str) -> Optional[Set[str]]:
        """Return the set of known column names for a table from PostgREST OpenAPI spec, or None if offline."""
        global _SCHEMA_COLUMNS_CACHE
        if table_name in _SCHEMA_COLUMNS_CACHE:
            return _SCHEMA_COLUMNS_CACHE[table_name]

        if not is_supabase_configured():
            return None

        try:
            url = f"{get_supabase_url()}/rest/v1/"
            resp = _get_session().get(url, headers=_get_headers(), timeout=5)
            if resp.status_code == 200:
                spec = resp.json()
                definitions = spec.get("definitions", {})
                for tbl, defn in definitions.items():
                    props = defn.get("properties", {})
                    _SCHEMA_COLUMNS_CACHE[tbl] = set(props.keys())
                if table_name in _SCHEMA_COLUMNS_CACHE:
                    return _SCHEMA_COLUMNS_CACHE[table_name]
        except Exception:
            pass

        return None

    @staticmethod
    def is_available() -> bool:
        """Check whether Supabase is configured and reachable."""
        if not is_supabase_configured():
            return False
        try:
            url = f"{get_supabase_url()}/rest/v1/"
            resp = _get_session().get(url, headers=_get_headers(), timeout=3)
            return resp.status_code in (200, 404, 401, 403)
        except Exception:
            return False

    @staticmethod
    def bulk_upsert(
        table_name: str,
        records: List[Dict[str, Any]],
        on_conflict: Optional[str] = None,
        chunk_size: int = 500,
    ) -> int:
        """
        Upsert records into Supabase in chunks.
        Falls back to in-memory store if Supabase is unconfigured.
        """
        if not records:
            return 0

        clean_records = [sanitize_record(r) for r in records]

        if not is_supabase_configured():
            # In-memory mock upsert
            table = _MOCK_STORAGE.setdefault(table_name, [])
            if on_conflict and table:
                conflict_keys = [k.strip() for k in on_conflict.split(",")]
                existing_map = {}
                for idx, item in enumerate(table):
                    k = tuple(str(item.get(ck)) for ck in conflict_keys)
                    existing_map[k] = idx

                for rec in clean_records:
                    k = tuple(str(rec.get(ck)) for ck in conflict_keys)
                    if k in existing_map:
                        table[existing_map[k]].update(rec)
                    else:
                        table.append(rec)
                        existing_map[k] = len(table) - 1
            else:
                table.extend(clean_records)
            return len(clean_records)

        url = f"{get_supabase_url()}/rest/v1/{table_name}"
        headers = _get_headers()
        # PostgREST upsert resolution header
        headers["Prefer"] = "resolution=merge-duplicates"

        params = {}
        if on_conflict:
            params["on_conflict"] = on_conflict

        total_inserted = 0
        for i in range(0, len(clean_records), chunk_size):
            chunk = clean_records[i : i + chunk_size]
            resp = _get_session().post(url, json=chunk, headers=headers, params=params, timeout=30)
            if resp.status_code not in (200, 201, 204):
                raise RuntimeError(
                    f"Supabase upsert into '{table_name}' failed ({resp.status_code}): {resp.text}"
                )
            total_inserted += len(chunk)

        return total_inserted

    @staticmethod
    def fetch_all(
        table_name: str,
        columns: str = "*",
        filters: Optional[Dict[str, str]] = None,
        chunk_size: int = 2500,
    ) -> List[Dict[str, Any]]:
        """
        Stream all records from a Supabase table using Range headers.
        Falls back to in-memory store if unconfigured.
        """
        if not is_supabase_configured():
            table = _MOCK_STORAGE.get(table_name, [])
            if filters:
                filtered = []
                for row in table:
                    match = True
                    for k, v in filters.items():
                        if str(row.get(k)) != str(v):
                            match = False
                            break
                    if match:
                        filtered.append(row)
                    return [dict(r) for r in filtered]
            return [dict(r) for r in table]

        url = f"{get_supabase_url()}/rest/v1/{table_name}"
        headers = _get_headers()
        params = {"select": columns}
        if filters:
            for k, v in filters.items():
                params[k] = f"eq.{v}"

        all_rows: List[Dict[str, Any]] = []
        offset = 0

        while True:
            range_header = f"{offset}-{offset + chunk_size - 1}"
            chunk_headers = dict(headers)
            chunk_headers["Range"] = range_header
            chunk_headers["Prefer"] = "count=exact"

            resp = _get_session().get(url, headers=chunk_headers, params=params, timeout=15)
            if resp.status_code not in (200, 206):
                if resp.status_code == 416:  # Requested range not satisfiable (end of table)
                    break
                raise RuntimeError(
                    f"Supabase fetch from '{table_name}' failed ({resp.status_code}): {resp.text}"
                )

            data = resp.json()
            if not data or not isinstance(data, list) or len(data) == 0:
                break
            all_rows.extend(data)
            offset += len(data)

            cr = resp.headers.get("Content-Range", "")
            if "/" in cr:
                total_str = cr.split("/")[-1].strip()
                if total_str.isdigit() and len(all_rows) >= int(total_str):
                    break

        return all_rows

    @staticmethod
    def get_latest_completed_optimization_run() -> Tuple[Optional[str], Set[str]]:
        """
        Retrieve the latest completed run_id and its set of authorized member_ids.
        Checks final_recommendations first, then optimization_results for that run.
        Returns (latest_run_id, set_of_authorized_member_ids).
        """
        # Find latest completed run from pipeline_runs
        runs = SupabaseService.fetch_all(
            "pipeline_runs",
            columns="id,status,completed_at,created_at",
            filters={"status": "completed"},
        )
        if not runs:
            return None, set()

        # Sort runs by completed_at desc, fallback to created_at desc
        runs_sorted = sorted(
            runs,
            key=lambda r: r.get("completed_at") or r.get("created_at") or "",
            reverse=True,
        )
        latest_run_id = str(runs_sorted[0]["id"])

        # Try final_recommendations first
        rec_rows = SupabaseService.fetch_all(
            "final_recommendations",
            filters={"run_id": latest_run_id},
        )
        if rec_rows:
            member_ids = set()
            for r in rec_rows:
                mid = r.get("Member ID") or r.get("member_id")
                if mid:
                    member_ids.add(str(mid).strip())
            if member_ids:
                return latest_run_id, member_ids

        # Fallback to optimization_results
        opt_rows = SupabaseService.fetch_all(
            "optimization_results",
            filters={"run_id": latest_run_id},
        )
        member_ids = {str(r["member_id"]).strip() for r in opt_rows if r.get("member_id")}
        return latest_run_id, member_ids

    @staticmethod
    def get_latest_completed_optimization_members() -> Set[str]:
        """
        Retrieve the set of member_ids selected by the latest completed optimization run.
        This provides the authoritative whitelist for Member Update uploads.
        """
        _, members = SupabaseService.get_latest_completed_optimization_run()
        return members

    @staticmethod
    def log_upload_event(
        upload_type: str,
        source_file_name: str,
        run_id: str,
        authorized_optimization_run_id: Optional[str] = None,
        affected_member_count: int = 0,
        inserted_row_count: int = 0,
        updated_row_count: int = 0,
        rejected_member_count: int = 0,
        status: str = "completed",
        error_message: Optional[str] = None,
        storage_path: Optional[str] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> None:
        """Record upload event in upload_events audit table conforming to live schema."""
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": str(uuid.uuid4()),
            "upload_type": upload_type,
            "source_file_name": source_file_name,
            "storage_path": storage_path or "",
            "run_id": run_id,
            "authorized_optimization_run_id": authorized_optimization_run_id,
            "affected_member_count": affected_member_count,
            "inserted_row_count": inserted_row_count,
            "updated_row_count": updated_row_count,
            "rejected_member_count": rejected_member_count,
            "status": status,
            "error_message": error_message,
            "started_at": started_at or now,
            "completed_at": completed_at or now,
            "created_at": now,
        }
        SupabaseService.bulk_upsert("upload_events", [record], on_conflict="id")

    @staticmethod
    def register_pipeline_run(
        run_id: str,
        trigger_type: str = "initial_upload",
        source_file_name: str = "",
    ) -> None:
        """Create a new run record in pipeline_runs with status='running' to satisfy check constraint."""
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": run_id,
            "status": "running",
            "trigger_type": trigger_type,
            "source_file_name": source_file_name,
            "started_at": now,
            "completed_at": None,
            "error_message": None,
            "created_at": now,
        }
        try:
            SupabaseService.bulk_upsert("pipeline_runs", [record], on_conflict="id")
        except Exception as exc:  # noqa: BLE001
            print(f"[supabase_service] WARNING: could not register pipeline run {run_id}: {exc}")

    @staticmethod
    def update_pipeline_run(
        run_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Update run status and completion timestamp (best-effort; never crashes the pipeline)."""
        now = datetime.now(timezone.utc).isoformat()
        record: Dict[str, Any] = {
            "id": run_id,
            "status": status,
            "error_message": error_message,
        }
        if status in ("completed", "failed"):
            record["completed_at"] = now
        try:
            SupabaseService.bulk_upsert("pipeline_runs", [record], on_conflict="id")
        except Exception as exc:  # noqa: BLE001
            print(f"[supabase_service] WARNING: could not update pipeline run {run_id}: {exc}")

    @staticmethod
    def update_stage(
        run_id: str,
        stage_key: str,
        status: str,
        message: str = "",
        rows_processed: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Record stage transition in pipeline_stages (best-effort; never crashes the pipeline)."""
        now = datetime.now(timezone.utc).isoformat()
        record: Dict[str, Any] = {
            "run_id": run_id,
            "stage_key": stage_key,
            "status": status,
            "message": message,
            "rows_processed": rows_processed,
            "error_message": error_message,
        }
        if status == "running":
            record["started_at"] = now
        elif status in ("completed", "failed"):
            record["completed_at"] = now
        try:
            SupabaseService.bulk_upsert(
                "pipeline_stages",
                [record],
                on_conflict="run_id,stage_key",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[supabase_service] WARNING: could not update stage {stage_key} for run {run_id}: {exc}")

    @staticmethod
    def log_dataset_update(
        update_type: str,
        file_name: str,
        affected_member_ids: List[str],
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Record dataset audit log entry (best-effort; never crashes the upload)."""
        record = {
            "id": str(uuid.uuid4()),
            "update_type": update_type,
            "file_name": file_name,
            "affected_members_count": len(affected_member_ids),
            "affected_member_ids": affected_member_ids,
            "status": status,
            "error_message": error_message,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            SupabaseService.bulk_upsert("dataset_update_logs", [record], on_conflict="id")
        except Exception as exc:  # noqa: BLE001
            print(f"[supabase_service] WARNING: could not log dataset update ({update_type}): {exc}")

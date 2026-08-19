"""
Pipeline API routes.

Endpoints:
- POST /api/upload                     — file upload (mode=initial | member_update)
- POST /api/dataset/initial-upload     — explicit initial 8-table baseline upload
- POST /api/dataset/member-update      — explicit optimized member update upload
- GET  /api/pipeline/{job_id}          — real-time 9-stage status
- GET  /api/runs                       — pipeline execution history
- GET  /api/runs/{run_id}              — single run details
- GET  /api/updates                    — dataset update audit log

CRITICAL:
- React communicates ONLY with FastAPI.
- Secret keys are never exposed.
"""

import uuid
from typing import Optional, List
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Query, HTTPException

from backend.services.file_service import validate_and_save_upload, generate_run_id
from backend.services.dataset_service import DatasetService
from backend.services.supabase_service import SupabaseService
from backend.services.pipeline_service import (
    register_run,
    start_pipeline_run,
    get_run_state,
    STAGE_KEYS,
)
from backend.schemas.responses import (
    UploadResponse,
    PipelineStatusResponse,
    PipelineStageState,
    PipelineRunListItem,
    DatasetAuditLogItem,
)

router = APIRouter()


async def _handle_upload_flow(file: UploadFile, mode: str = "initial") -> UploadResponse:
    """Internal helper to process upload, sync database, and launch pipeline."""
    run_id = generate_run_id()
    saved_path = await validate_and_save_upload(file, run_id)
    trigger_type = "member_update" if mode == "member_update" else "initial_upload"

    # 1. Register run in memory & database FIRST so foreign keys (upload_events, pipeline_stages) are satisfied
    state = register_run(run_id, str(saved_path), trigger_type=trigger_type)

    affected_count = None
    auth_run_id = None
    try:
        if mode == "member_update":
            # 2. Validate & apply targeted member update against authorized list
            authorized_ids, row_counts, auth_run_id = DatasetService.validate_and_apply_member_update(
                str(saved_path), run_id=run_id, source_file_name=file.filename
            )
            affected_count = len(authorized_ids)
        else:
            # 2. Initial 8-table dataset synchronization into current DB
            DatasetService.sync_initial_dataset(
                str(saved_path), run_id=run_id, source_file_name=file.filename
            )
    except Exception as exc:
        state.status = "failed"
        state.error = str(exc)
        SupabaseService.update_pipeline_run(run_id, status="failed", error_message=str(exc))
        raise

    # 3. Start 9-stage pipeline background thread on FULL current database
    start_pipeline_run(state)

    msg = (
        f"Optimized member update applied ({affected_count} members updated). Pipeline started on current database."
        if mode == "member_update"
        else "Initial dataset seeded into live database. Pipeline started."
    )

    return UploadResponse(
        job_id=run_id,
        status="accepted" if mode == "member_update" else "queued",
        mode=mode,
        authorization_run_id=auth_run_id,
        message=msg,
        affected_members=affected_count,
    )



@router.post("/upload", response_model=UploadResponse)
async def upload_dataset(
    file: UploadFile = File(...),
    mode: str = Query(default="initial", pattern="^(initial|member_update)$"),
):
    """
    Accept an Excel dataset upload (.xlsx/.xls, max 50 MB).
    mode: 'initial' for complete 8-sheet baseline dataset seeding,
          'member_update' for updating authorized optimized members only.
    """
    return await _handle_upload_flow(file, mode=mode)


@router.post("/dataset/initial-upload", response_model=UploadResponse)
async def initial_upload(file: UploadFile = File(...)):
    """Initial seeding of the current 8-table live database."""
    return await _handle_upload_flow(file, mode="initial")


@router.post("/dataset/member-update", response_model=UploadResponse)
async def member_update(file: UploadFile = File(...)):
    """Targeted update of authorized optimized members only."""
    return await _handle_upload_flow(file, mode="member_update")


@router.get("/pipeline/{job_id}", response_model=PipelineStatusResponse)
async def get_pipeline_status(job_id: str):
    """Return real-time pipeline execution status across all 9 stages."""
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job_id format.")

    state = get_run_state(job_id)
    if state is None:
        # Check Supabase
        runs = SupabaseService.fetch_all("pipeline_runs", filters={"id": job_id})
        if not runs:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        r = runs[0]
        st_rows = SupabaseService.fetch_all("pipeline_stages", filters={"run_id": job_id})
        stage_dict = {s["stage_key"]: s for s in st_rows}
        stages = {}
        for key in STAGE_KEYS:
            raw = stage_dict.get(key, {"status": "pending", "message": "Waiting", "rows_processed": None, "error_message": None})
            stages[key] = PipelineStageState(
                status=raw.get("status", "pending"),
                message=raw.get("message", ""),
                rows=raw.get("rows_processed"),
                error=raw.get("error_message"),
            )
        return PipelineStatusResponse(
            run_id=job_id,
            job_id=job_id,
            status=r.get("status", "queued"),
            error=r.get("error_message"),
            stages=stages,
        )

    stages = {}
    for key in STAGE_KEYS:
        raw = state.stages.get(key, {"status": "pending", "message": "Waiting", "rows": None, "error": None})
        stages[key] = PipelineStageState(
            status=raw.get("status", "pending"),
            message=raw.get("message", ""),
            rows=raw.get("rows"),
            error=raw.get("error"),
        )

    return PipelineStatusResponse(
        run_id=job_id,
        job_id=job_id,
        status=state.status,
        error=state.error,
        stages=stages,
    )


@router.get("/runs", response_model=List[PipelineRunListItem])
async def list_runs():
    """List historical pipeline runs."""
    rows = SupabaseService.fetch_all("pipeline_runs")
    items = []
    for r in sorted(rows, key=lambda x: x.get("created_at", ""), reverse=True):
        items.append(
            PipelineRunListItem(
                id=str(r.get("id")),
                status=str(r.get("status", "completed")),
                trigger_type=str(r.get("trigger_type", "initial_upload")),
                source_file_name=r.get("source_file_name"),
                started_at=r.get("started_at"),
                completed_at=r.get("completed_at"),
                error_message=r.get("error_message"),
                created_at=r.get("created_at"),
            )
        )
    return items


@router.get("/runs/latest", response_model=PipelineRunListItem)
async def get_latest_run():
    """Retrieve the latest completed pipeline run."""
    rows = SupabaseService.fetch_all("pipeline_runs")
    completed = [r for r in rows if r.get("status") == "completed"]
    if not completed:
        # Fallback to any latest run
        if not rows:
            raise HTTPException(status_code=404, detail="No pipeline runs found.")
        target = sorted(rows, key=lambda x: x.get("created_at", ""), reverse=True)[0]
    else:
        target = sorted(completed, key=lambda x: x.get("created_at", ""), reverse=True)[0]

    return PipelineRunListItem(
        id=str(target.get("id")),
        status=str(target.get("status", "completed")),
        trigger_type=str(target.get("trigger_type", "initial_upload")),
        source_file_name=target.get("source_file_name"),
        started_at=target.get("started_at"),
        completed_at=target.get("completed_at"),
        error_message=target.get("error_message"),
        created_at=target.get("created_at"),
    )


@router.get("/runs/{run_id}", response_model=PipelineRunListItem)
async def get_run_item(run_id: str):
    """Retrieve details for a single pipeline run."""
    if run_id == "latest":
        return await get_latest_run()
    rows = SupabaseService.fetch_all("pipeline_runs", filters={"id": run_id})
    if not rows:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    r = rows[0]
    return PipelineRunListItem(
        id=str(r.get("id")),
        status=str(r.get("status", "completed")),
        trigger_type=str(r.get("trigger_type", "initial_upload")),
        source_file_name=r.get("source_file_name"),
        started_at=r.get("started_at"),
        completed_at=r.get("completed_at"),
        error_message=r.get("error_message"),
        created_at=r.get("created_at"),
    )


@router.get("/updates", response_model=List[DatasetAuditLogItem])
async def list_dataset_updates():
    """List dataset update audit logs."""
    rows = SupabaseService.fetch_all("dataset_update_logs")
    items = []
    for r in sorted(rows, key=lambda x: x.get("created_at", ""), reverse=True):
        items.append(
            DatasetAuditLogItem(
                id=str(r.get("id")),
                update_type=str(r.get("update_type")),
                file_name=r.get("file_name"),
                affected_members_count=int(r.get("affected_members_count", 0)),
                affected_member_ids=r.get("affected_member_ids"),
                status=str(r.get("status")),
                error_message=r.get("error_message"),
                created_at=r.get("created_at"),
            )
        )
    return items

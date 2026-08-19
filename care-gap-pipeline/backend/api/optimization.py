"""
GET /api/optimize/{job_id}
GET /api/optimization/{job_id}
POST /api/optimize/{job_id}
POST /api/optimization/{job_id}

Returns pre-computed optimization results from the pipeline run.
Does NOT re-run the optimizer.
The contribution column is the exact value from compute_project_estimated_star_contribution().
"""
from fastapi import APIRouter, Form, Query
from typing import Optional
from backend.services.result_service import get_optimization_results

router = APIRouter()


@router.get("/optimize/{job_id}")
async def get_optimization_get(
    job_id: str,
    plan_id: str = Query(default=""),
    max_members: int = Query(default=0),
):
    return get_optimization_results(job_id, plan_id=plan_id, max_members=max_members)


@router.get("/optimization/{job_id}")
async def get_optimization_alias_get(
    job_id: str,
    plan_id: str = Query(default=""),
    max_members: int = Query(default=0),
):
    return get_optimization_results(job_id, plan_id=plan_id, max_members=max_members)


@router.post("/optimize/{job_id}")
async def optimization_results(
    job_id: str,
    plan_id: str = Form(default=""),
    max_members: int = Form(default=0),
):
    return get_optimization_results(job_id, plan_id=plan_id, max_members=max_members)


@router.post("/optimization/{job_id}")
async def optimization_results_alias(
    job_id: str,
    plan_id: str = Form(default=""),
    max_members: int = Form(default=0),
):
    return get_optimization_results(job_id, plan_id=plan_id, max_members=max_members)

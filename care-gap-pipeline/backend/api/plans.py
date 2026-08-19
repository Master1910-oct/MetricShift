"""
GET /api/plans/{job_id}
GET /api/plans/{job_id}/{plan_id}
"""
from fastapi import APIRouter
from backend.services.result_service import get_plan_data, get_plans_list

router = APIRouter()

@router.get("/plans/{job_id}")
async def list_plans(job_id: str):
    return get_plans_list(job_id)

@router.get("/plans/{job_id}/{plan_id}")
async def plan_detail(job_id: str, plan_id: str):
    return get_plan_data(job_id, plan_id)


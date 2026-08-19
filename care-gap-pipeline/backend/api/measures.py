"""
GET /api/measures/{job_id}
"""
from fastapi import APIRouter, Query
from typing import Optional
from backend.services.result_service import get_measures_data

router = APIRouter()


@router.get("/measures/{job_id}")
async def list_measures(job_id: str, plan_id: Optional[str] = Query(default="")):
    return get_measures_data(job_id, plan_id=plan_id or "")

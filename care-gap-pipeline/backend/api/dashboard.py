"""GET /api/dashboard/{job_id}"""
from fastapi import APIRouter
from backend.services.result_service import get_dashboard_data

router = APIRouter()

@router.get("/dashboard/{job_id}")
async def dashboard(job_id: str):
    return get_dashboard_data(job_id)

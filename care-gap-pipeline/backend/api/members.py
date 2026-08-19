"""
GET /api/members/{job_id}         — paginated member list
GET /api/members/{job_id}/{member_id} — single member detail
"""
from fastapi import APIRouter, Query
from backend.services.result_service import get_members_data, get_member_detail

router = APIRouter()

@router.get("/members/{job_id}")
async def list_members(
    job_id: str,
    page: int = Query(default=1, ge=1, le=10000),
    limit: int = Query(default=20, ge=1, le=200),
    search: str = Query(default="", max_length=100),
    plan_id: str = Query(default="", max_length=50),
):
    return get_members_data(job_id, page=page, limit=limit, search=search, plan_id=plan_id)

@router.get("/members/{job_id}/{member_id}")
async def member_detail(job_id: str, member_id: str):
    return get_member_detail(job_id, member_id)

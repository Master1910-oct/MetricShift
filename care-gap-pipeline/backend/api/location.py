"""
GET /api/location/{job_id}

The current pipeline does not produce location/state data.
Returns an empty dict to satisfy the frontend client without errors.
"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/location/{job_id}")
async def get_locations(job_id: str):
    return {}

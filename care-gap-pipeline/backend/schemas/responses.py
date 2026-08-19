"""
Pydantic response schemas for all Metric Shift API endpoints.
These mirror the TypeScript interfaces in frontend/src/api/client.ts exactly.
"""

from __future__ import annotations
from typing import Optional, Dict, List, Any
from pydantic import BaseModel


# ──────────────────────────────────────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"


# ──────────────────────────────────────────────────────────────────────────────
# Upload / Pipeline Status
# ──────────────────────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    job_id: str
    status: str  # "queued" | "accepted"
    mode: Optional[str] = "initial"  # "initial" | "member_update"
    authorization_run_id: Optional[str] = None
    message: Optional[str] = None
    affected_members: Optional[int] = None


class PipelineStageState(BaseModel):
    status: str           # "pending" | "running" | "completed" | "failed"
    message: str = ""
    rows: Optional[int] = None
    error: Optional[str] = None


class PipelineStatusResponse(BaseModel):
    run_id: str
    job_id: str           # same as run_id - matches frontend expectation
    status: str           # "queued" | "running" | "completed" | "failed"
    error: Optional[str] = None
    stages: Dict[str, PipelineStageState]


class PipelineRunListItem(BaseModel):
    id: str
    status: str
    trigger_type: str
    source_file_name: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None


class DatasetAuditLogItem(BaseModel):
    id: str
    update_type: str
    file_name: Optional[str] = None
    affected_members_count: int
    affected_member_ids: Optional[List[str]] = None
    status: str
    error_message: Optional[str] = None
    created_at: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────────────────

class DashboardSummary(BaseModel):
    total_plans: int
    total_members: int
    open_care_gaps: int
    cms_measures: int
    selected_members: int
    avg_closure_probability: float
    total_star_contribution: float


class PlanGapCount(BaseModel):
    plan_id: str
    gaps: int


class PlanPerformance(BaseModel):
    plan_id: str
    plan_name: str
    rating: float


class InterventionCount(BaseModel):
    name: str
    value: int


class CareGapCount(BaseModel):
    name: str
    value: int


class DashboardMetrics(BaseModel):
    summary: DashboardSummary
    gaps_by_plan: List[PlanGapCount]
    plan_performances: List[PlanPerformance]
    improvement_trend: List[Dict[str, Any]]
    intervention_distribution: List[InterventionCount]
    care_gap_distribution: List[CareGapCount]


# ──────────────────────────────────────────────────────────────────────────────
# Members
# ──────────────────────────────────────────────────────────────────────────────

class MemberRecord(BaseModel):
    member_id: str
    member_name: str
    dob: str
    age: int
    gender: str
    condition: str
    plan_id: str
    care_gaps: str
    recommended_intervention: str
    gap_status: str
    star_contribution: str   # "+0.0012" formatted string from backend


class MembersPagination(BaseModel):
    total_records: int
    page: int
    limit: int
    total_pages: int


class MembersResponse(BaseModel):
    records: List[MemberRecord]
    pagination: MembersPagination


class MemberCareGap(BaseModel):
    care_gap_name: str
    measure_id: str
    status: str  # "Open" | "Closed"


class MemberGapsSummary(BaseModel):
    open_care_gaps: int
    closed_care_gaps: int
    high_priority_gaps: int


class MemberDetails(BaseModel):
    member_id: str
    member_name: str
    overall_priority: str
    priority_score: float
    details: Dict[str, Any]
    gaps_summary: MemberGapsSummary
    care_gaps: List[MemberCareGap]
    recommended_intervention: str
    closure_probability: float
    star_contribution: str


# ──────────────────────────────────────────────────────────────────────────────
# Plans
# ──────────────────────────────────────────────────────────────────────────────

class PlanSummary(BaseModel):
    total_members: int
    open_care_gaps: int
    total_care_gaps: int
    plan_rating: float
    selected_members: int


class PlanDetails(BaseModel):
    summary: PlanSummary
    gaps_by_status: List[Dict[str, Any]]
    improvement_trend: List[Dict[str, Any]]
    details: Dict[str, Any]
    measures: List[Dict[str, Any]]


# ──────────────────────────────────────────────────────────────────────────────
# CMS Measures
# ──────────────────────────────────────────────────────────────────────────────

class CMSMeasureSummary(BaseModel):
    total_measures: int
    high_priority_measures: int
    rating_year: int


class CMSMeasureRecord(BaseModel):
    part: str
    measure_id: str
    measure_name: str
    measure_type: str
    domain: str
    measure_id_value: str
    description: str
    weight: float
    performance_value: Optional[float] = None
    measure_star: Optional[float] = None


class CMSMeasuresResponse(BaseModel):
    summary: CMSMeasureSummary
    records: List[CMSMeasureRecord]


# ──────────────────────────────────────────────────────────────────────────────
# Optimization
# ──────────────────────────────────────────────────────────────────────────────

class OptimizationRecord(BaseModel):
    s_no: int
    member_id: str
    member_name: str
    age: int
    gender: str
    gap_count: int
    care_gaps: str
    recommended_intervention: str
    gap_status: str
    contribution: str   # Exactly "Estimated Star Rating Improvement (Contribution)" value


class OptimizationSummary(BaseModel):
    total_selected: int
    total_gaps: int
    intervention_breakdown: Dict[str, int]
    avg_closure_probability: float


class OptimizationResponse(BaseModel):
    records: List[OptimizationRecord]
    summary: OptimizationSummary

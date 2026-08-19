"""
GET /api/download/{job_id}

Streams final_member_report.xlsx for the given job and current optimization parameters (plan_id, max_members).
The file contains the exact columns matching the displayed Optimal Outreach List:
  - S.No.
  - Member ID
  - Member Name
  - Age
  - Gender
  - Total Gaps
  - Care Gap(s) (Gap Name)
  - Recommended Intervention
  - Gap Status
  - Estimated Star Rating Improvement
"""
import io
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
import pandas as pd

from backend.services.pipeline_service import OUTPUT_BASE_DIR
from backend.services.result_service import get_optimization_results

router = APIRouter()


@router.get("/download/{job_id}")
async def download_report(
    job_id: str,
    plan_id: str = Query(default=""),
    max_members: int = Query(default=0),
):
    # Validate UUID to prevent path traversal
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job_id format.")

    # If plan_id or max_members is specified, dynamically generate the exact Excel file matching current optimization result
    if plan_id or max_members > 0:
        opt_res = get_optimization_results(job_id, plan_id=plan_id, max_members=max_members)
        records = opt_res.get("records", [])
        if not records:
            raise HTTPException(
                status_code=404,
                detail=f"No optimization records found for plan '{plan_id}'."
            )

        # Build DataFrame with exact expected column names matching displayed table
        df_export = pd.DataFrame([
            {
                "S.No.": r["s_no"],
                "Member ID": r["member_id"],
                "Member Name": r["member_name"],
                "Age": r["age"],
                "Gender": r["gender"],
                "Total Gaps": r["gap_count"],
                "Care Gap(s) (Gap Name)": r["care_gaps"],
                "Recommended Intervention": r["recommended_intervention"],
                "Gap Status": r["gap_status"],
                "Estimated Star Rating Improvement": r["contribution"],
            }
            for r in records
        ])

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_export.to_excel(writer, index=False, sheet_name="Optimal Outreach List")
        buffer.seek(0)

        filename = f"Metric_Shift_Final_Member_Report_{plan_id}_{job_id[:8]}.xlsx" if plan_id else f"Metric_Shift_Final_Member_Report_{job_id[:8]}.xlsx"

        return Response(
            content=buffer.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )

    # Fallback to static baseline final report if neither plan_id nor max_members provided
    report_path = Path(OUTPUT_BASE_DIR) / job_id / "final_member_report.xlsx"
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Report not found for job '{job_id}'. Pipeline may not be complete."
        )

    filename = f"Metric_Shift_Final_Member_Report_{job_id[:8]}.xlsx"
    return FileResponse(
        path=str(report_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


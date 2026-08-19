"""
Secure file upload service.
Handles upload validation, storage, and run ID generation.
Never exposes internal filesystem paths to the client.
"""

import os
import uuid
import shutil
from pathlib import Path
from fastapi import UploadFile, HTTPException

# ─────────────────────────────────────────────────────────────────────────────
# Configuration (from environment, with safe defaults)
# ─────────────────────────────────────────────────────────────────────────────

def _get_upload_base_dir() -> str:
    env_val = os.environ.get("UPLOAD_BASE_DIR")
    if env_val:
        return env_val
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return "/tmp/uploads"
    return "uploads"

UPLOAD_BASE_DIR = _get_upload_base_dir()
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024   # 50 MB
ALLOWED_EXTENSIONS = {".xlsx", ".xls"}


def generate_run_id() -> str:
    """Generate a cryptographically random run/job ID."""
    return str(uuid.uuid4())


def _validate_run_id(run_id: str) -> None:
    """Validate that run_id is a well-formed UUID (path traversal guard)."""
    try:
        uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job_id format.")


def get_run_upload_dir(run_id: str) -> Path:
    """Return the upload directory for a given run. Creates it if needed."""
    _validate_run_id(run_id)
    path = Path(UPLOAD_BASE_DIR) / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_input_file_path(run_id: str) -> Path:
    """Return the canonical path to the uploaded input file for a run."""
    _validate_run_id(run_id)
    return Path(UPLOAD_BASE_DIR) / run_id / "input.xlsx"


async def validate_and_save_upload(file: UploadFile, run_id: str) -> Path:
    """
    Validate file extension and size, then save to the run's upload directory.

    Parameters
    ----------
    file : UploadFile
        FastAPI uploaded file object.
    run_id : str
        UUID run identifier.

    Returns
    -------
    Path
        Absolute path to the saved file.

    Raises
    ------
    HTTPException 400
        If file extension or size is invalid.
    """
    # Extension check (no path traversal possible since we rename to input.xlsx)
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type '{ext}'. Only .xlsx and .xls files are accepted."
            )

    upload_dir = get_run_upload_dir(run_id)
    dest_path = upload_dir / "input.xlsx"

    # Read in chunks to enforce size limit without loading entire file into memory
    total_bytes = 0
    chunk_size = 64 * 1024  # 64 KB chunks

    try:
        with open(dest_path, "wb") as out_f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                    out_f.close()
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB."
                    )
                out_f.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {exc}")

    return dest_path.resolve()

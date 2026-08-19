"""
Metric Shift FastAPI Application.

Bridge between the React frontend and the validated care-gap pipeline.

Architecture:
    React Frontend -> FastAPI -> Existing Pipeline -> Results -> FastAPI -> React

CRITICAL:
- Never exposes model files, Python source, or internal paths.
- Never re-implements pipeline business logic.
- Never overwrites outputs/ (each run uses run_outputs/<run_id>/).
- CORS is restricted; origins from env variable.
"""

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so pipeline imports work
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(_PROJECT_ROOT) / ".env")
except ImportError:
    pass

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import backend.api.pipeline as pipeline_api
import backend.api.dashboard as dashboard_api
import backend.api.members as members_api
import backend.api.plans as plans_api
import backend.api.measures as measures_api
import backend.api.optimization as optimization_api
import backend.api.downloads as downloads_api
import backend.api.location as location_api


# App configuration
app = FastAPI(
    title="Metric Shift API",
    description="FastAPI bridge between the React dashboard and the validated care-gap pipeline.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


# CORS configuration
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
is_wildcard = "*" in ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app" if not is_wildcard else None,
    allow_credentials=not is_wildcard,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {str(exc)}"},
    )


# Health endpoint (STEP 6 / CRITICAL RULE 4)
@app.get("/api/health", tags=["Health"])
async def health_check():
    """Returns {"status": "ok"} when the API is running."""
    return {"status": "ok"}


# Mount all routers
app.include_router(pipeline_api.router, prefix="/api", tags=["Pipeline"])
app.include_router(dashboard_api.router, prefix="/api", tags=["Dashboard"])
app.include_router(members_api.router, prefix="/api", tags=["Members"])
app.include_router(plans_api.router, prefix="/api", tags=["Plans"])
app.include_router(measures_api.router, prefix="/api", tags=["Measures"])
app.include_router(optimization_api.router, prefix="/api", tags=["Optimization"])
app.include_router(downloads_api.router, prefix="/api", tags=["Downloads"])
app.include_router(location_api.router, prefix="/api", tags=["Location"])

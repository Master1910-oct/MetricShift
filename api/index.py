"""
Vercel Serverless Function entry point for Metric Shift FastAPI backend.
Exposes the existing FastAPI app from care-gap-pipeline/backend/main.py.
"""
import os
import sys
from pathlib import Path

# Ensure project root and care-gap-pipeline directory are in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _PROJECT_ROOT / "care-gap-pipeline"

for p in [str(_BACKEND_DIR), str(_PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Load environment variables if available
try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND_DIR / ".env")
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

# Import the existing FastAPI application
from backend.main import app


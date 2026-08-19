# Metric Shift — Care Gap Detection & Star Rating Simulator

Metric Shift is a Medicare Advantage quality improvement and star-rating simulation platform powered by a validated 9-stage pipeline (Rule Engine, ML Model Ensemble, Mixed-Integer Linear Programming Optimization, and Post-Upload Data Synchronization with Supabase).

---

## ?? Repository Structure

```
MetricShift/
+-- care-gap-pipeline/              # FastAPI Backend, ML Ensemble & MILP Pipeline
¦   +-- backend/                    # FastAPI routers, services, & Supabase integration
¦   +-- rule_engine/                # Deterministic care gap rule evaluation
¦   +-- ml_model/                   # Random Forest + XGBoost soft-voting ensemble
¦   +-- optimizer/                  # Mixed-Integer Linear Programming (MILP) solver
¦   +-- pipeline/                   # Orchestration, candidate generation, calibration
¦   +-- Dockerfile                  # Container definition for cloud deployment
¦   +-- Procfile                    # Web process config for Render / Railway
¦   +-- requirements.txt            # Python dependencies
¦
+-- metric-shift-frontend-only/     # React + TypeScript + Vite Dashboard Frontend
    +-- src/                        # React components, landing page, and pages
    +-- public/                     # Static assets & icons
    +-- vercel.json                 # Vercel SPA routing & build configuration
    +-- package.json                # Frontend dependencies & scripts
```

---

## ?? Deployment

### 1. Frontend Deployment (Vercel)
- **Framework Preset**: Vite
- **Root Directory**: `metric-shift-frontend-only`
- **Build Command**: `npm run build`
- **Output Directory**: `dist`
- **Environment Variable**: `VITE_API_BASE_URL` = `https://your-backend.railway.app` (or Render URL)

### 2. Backend Deployment (Render / Railway / Fly.io / Docker)
- **Root Directory**: `care-gap-pipeline`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- **Environment Variables**:
  - `SUPABASE_URL` = `https://orpnoxylcdnaxftphanl.supabase.co`
  - `SUPABASE_SECRET_KEY` = `<YOUR_SECRET_KEY>`
  - `ALLOWED_ORIGINS` = `https://your-frontend.vercel.app`


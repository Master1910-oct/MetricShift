-- ============================================================================
-- METRIC SHIFT SUPABASE: Service Role Grants + Metadata Table Setup
-- Run this in the Supabase SQL Editor (Dashboard > SQL Editor > New Query)
--
-- Purpose:
--   1. Grant service_role INSERT/UPDATE/SELECT on all 8 source tables
--      (needed because RLS is enabled by default on all tables)
--   2. Create pipeline metadata and result tables if not already created
--   3. Grant service_role access on all metadata/result tables
-- ============================================================================

-- ============================================================================
-- STEP 1: Grant service_role on all 8 LIVE SOURCE TABLES
-- ============================================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON public.plans TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.plan_benefits TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.members TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.member_enrollment TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.member_history TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cms_measures TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.plan_measure_performance TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.part_d_medication_history TO service_role;

-- ============================================================================
-- STEP 2: Create pipeline metadata tables (if not already created by migration)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2.1 PIPELINE RUNS
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status TEXT NOT NULL DEFAULT 'queued',
    trigger_type TEXT NOT NULL DEFAULT 'initial_upload',
    source_file_name TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2.2 PIPELINE STAGES
CREATE TABLE IF NOT EXISTS pipeline_stages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    stage_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    message TEXT,
    rows_processed INTEGER,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CONSTRAINT uq_run_stage UNIQUE(run_id, stage_key)
);

-- 2.3 DATASET UPDATE AUDIT LOGS
CREATE TABLE IF NOT EXISTS dataset_update_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    update_type TEXT NOT NULL,
    file_name TEXT,
    affected_members_count INTEGER,
    affected_member_ids TEXT[],
    status TEXT NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- STEP 3: Create run-isolated result tables (if not already created)
-- ============================================================================

-- 3.1 CARE GAPS
CREATE TABLE IF NOT EXISTS care_gaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    patient_id TEXT NOT NULL,
    member_id TEXT NOT NULL,
    plan_id TEXT,
    care_gap TEXT,
    measure_id TEXT,
    gap_status TEXT,
    intervention_type TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3.2 ML PREDICTIONS
CREATE TABLE IF NOT EXISTS ml_predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    patient_id TEXT NOT NULL,
    member_id TEXT NOT NULL,
    plan_id TEXT,
    care_gap TEXT,
    intervention_type TEXT NOT NULL,
    probability_score NUMERIC(8, 6),
    calibrated_probability NUMERIC(8, 6),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3.3 INTERVENTION SELECTIONS
CREATE TABLE IF NOT EXISTS intervention_selections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    patient_id TEXT NOT NULL,
    member_id TEXT NOT NULL,
    plan_id TEXT,
    care_gap TEXT,
    intervention_type TEXT NOT NULL,
    probability_score NUMERIC(8, 6),
    calibrated_probability NUMERIC(8, 6),
    selection_decision TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3.4 OPTIMIZATION RESULTS
CREATE TABLE IF NOT EXISTS optimization_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL,
    member_name TEXT,
    age INTEGER,
    gender TEXT,
    gap_count INTEGER,
    care_gaps TEXT,
    recommended_intervention TEXT NOT NULL,
    gap_status TEXT,
    closure_probability NUMERIC(8, 6),
    robust_quality NUMERIC(8, 6),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3.5 STAR RATING CONTRIBUTIONS
CREATE TABLE IF NOT EXISTS star_rating_contributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL,
    plan_id TEXT,
    care_gap TEXT,
    measure_id TEXT,
    denominator NUMERIC(12, 4),
    performance_value NUMERIC(8, 6),
    current_measure_star NUMERIC(4, 2),
    measure_weight NUMERIC(4, 2),
    closure_probability NUMERIC(8, 6),
    plan_star_contribution NUMERIC(10, 8),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3.6 FINAL RECOMMENDATIONS
CREATE TABLE IF NOT EXISTS final_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    s_no INTEGER,
    member_id TEXT NOT NULL,
    member_name TEXT,
    age INTEGER,
    gender TEXT,
    total_gaps INTEGER,
    care_gaps TEXT,
    recommended_intervention TEXT NOT NULL,
    gap_status TEXT,
    star_contribution TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- STEP 4: Grant service_role on all metadata and result tables
-- ============================================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON public.pipeline_runs TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.pipeline_stages TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.dataset_update_logs TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.care_gaps TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ml_predictions TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.intervention_selections TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.optimization_results TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.star_rating_contributions TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.final_recommendations TO service_role;

-- ============================================================================
-- Verify tables exist
-- ============================================================================
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

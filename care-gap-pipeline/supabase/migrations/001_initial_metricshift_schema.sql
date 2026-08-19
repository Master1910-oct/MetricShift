-- ============================================================================
-- METRIC SHIFT SUPABASE SCHEMA
-- Migration: 001_initial_metricshift_schema.sql
--
-- Live Current Source Tables + Pipeline Run History + Result Tables
-- ============================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 1. CURRENT LIVE SOURCE TABLES (Single Live Dataset - NO dataset_versions)
-- ============================================================================

-- 1.1 PLANS
CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT PRIMARY KEY,
    contract_id TEXT,
    plan_name TEXT,
    organization_name TEXT,
    plan_type TEXT,
    state TEXT,
    overall_star_rating NUMERIC(4, 2),
    part_c_star_rating NUMERIC(4, 2),
    part_d_star_rating NUMERIC(4, 2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 1.2 PLAN_BENEFITS
CREATE TABLE IF NOT EXISTS plan_benefits (
    benefit_id TEXT PRIMARY KEY,
    plan_id TEXT,
    part TEXT,
    benefit_category TEXT,
    service_name TEXT,
    coverage_status TEXT,
    frequency_limit TEXT,
    benefit_year TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_plan_benefits_plan_id ON plan_benefits(plan_id);

-- 1.3 MEMBERS (member_id is NOT unique; one member may have multiple condition rows)
CREATE TABLE IF NOT EXISTS members (
    member_condition_id TEXT PRIMARY KEY,
    member_id TEXT NOT NULL,
    member_name TEXT,
    date_of_birth TEXT,
    age INTEGER,
    gender TEXT,
    condition TEXT,
    condition_code TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_members_member_id ON members(member_id);

-- 1.4 MEMBER_ENROLLMENT
CREATE TABLE IF NOT EXISTS member_enrollment (
    enrollment_id TEXT PRIMARY KEY,
    member_id TEXT NOT NULL,
    plan_id TEXT,
    enrollment_start_date TEXT,
    enrollment_end_date TEXT,
    enrollment_status TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_member_enrollment_member_id ON member_enrollment(member_id);
CREATE INDEX IF NOT EXISTS idx_member_enrollment_plan_id ON member_enrollment(plan_id);

-- 1.5 MEMBER_HISTORY
CREATE TABLE IF NOT EXISTS member_history (
    history_id TEXT PRIMARY KEY,
    member_id TEXT NOT NULL,
    service_name TEXT,
    test_name TEXT,
    service_date TEXT,
    status TEXT,
    result TEXT,
    event_type TEXT,
    result_value TEXT,
    result_unit TEXT,
    intervention_type TEXT,
    action_date TEXT,
    completion_date TEXT,
    outcome TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_member_history_member_id ON member_history(member_id);

-- 1.6 CMS_MEASURES
CREATE TABLE IF NOT EXISTS cms_measures (
    measure_id TEXT PRIMARY KEY,
    official_measure_id TEXT,
    measure_name TEXT,
    part TEXT,
    domain TEXT,
    measure_type TEXT,
    rating_year INTEGER,
    description TEXT,
    eligibility_rule TEXT,
    numerator_definition TEXT,
    denominator_definition TEXT,
    exclusion_rule TEXT,
    weight NUMERIC(4, 2),
    active TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 1.7 PLAN_MEASURE_PERFORMANCE
CREATE TABLE IF NOT EXISTS plan_measure_performance (
    performance_id TEXT PRIMARY KEY,
    plan_id TEXT,
    measure_id TEXT,
    rating_year INTEGER,
    denominator NUMERIC(12, 4),
    numerator NUMERIC(12, 4),
    performance_value NUMERIC(8, 6),
    measure_star NUMERIC(4, 2),
    weight NUMERIC(4, 2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pmp_plan_id ON plan_measure_performance(plan_id);
CREATE INDEX IF NOT EXISTS idx_pmp_measure_id ON plan_measure_performance(measure_id);

-- 1.8 PART_D_MEDICATION_HISTORY
CREATE TABLE IF NOT EXISTS part_d_medication_history (
    rx_history_id TEXT PRIMARY KEY,
    member_id TEXT NOT NULL,
    medication_name TEXT,
    ndc_code TEXT,
    prescription_id TEXT,
    pharmacy_id TEXT,
    fill_date TEXT,
    days_supply INTEGER,
    quantity_dispensed NUMERIC(10, 2),
    refill_number INTEGER,
    claim_status TEXT,
    amount_paid NUMERIC(10, 2),
    member_copay NUMERIC(10, 2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_part_d_member_id ON part_d_medication_history(member_id);


-- ============================================================================
-- 2. PIPELINE RUN METADATA & AUDIT LOGS
-- ============================================================================

-- 2.1 PIPELINE RUNS (tracks execution history)
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status TEXT NOT NULL DEFAULT 'queued',   -- queued | running | completed | failed
    trigger_type TEXT NOT NULL DEFAULT 'initial_upload', -- initial_upload | member_update | manual
    source_file_name TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_created_at ON pipeline_runs(created_at DESC);

-- 2.2 PIPELINE STAGES (tracks 9 execution stages per run)
CREATE TABLE IF NOT EXISTS pipeline_stages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    stage_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending | running | completed | failed
    message TEXT,
    rows_processed INTEGER,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CONSTRAINT uq_run_stage UNIQUE(run_id, stage_key)
);
CREATE INDEX IF NOT EXISTS idx_pipeline_stages_run_id ON pipeline_stages(run_id);

-- 2.3 DATASET UPDATE AUDIT LOGS (audit only - NOT dataset versioning)
CREATE TABLE IF NOT EXISTS dataset_update_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    update_type TEXT NOT NULL, -- initial_upload | member_update
    file_name TEXT,
    affected_members_count INTEGER,
    affected_member_ids TEXT[],
    status TEXT NOT NULL, -- success | failed
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dataset_update_logs_created_at ON dataset_update_logs(created_at DESC);


-- ============================================================================
-- 3. RUN-SPECIFIC RESULT TABLES (Isolated by run_id)
-- ============================================================================

-- 3.1 CARE GAPS (Rule Engine output)
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
CREATE INDEX IF NOT EXISTS idx_care_gaps_run_id ON care_gaps(run_id);
CREATE INDEX IF NOT EXISTS idx_care_gaps_run_member ON care_gaps(run_id, member_id);

-- 3.2 ML PREDICTIONS (Preserves all candidate interventions with probabilities)
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
CREATE INDEX IF NOT EXISTS idx_ml_predictions_run_id ON ml_predictions(run_id);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_run_member ON ml_predictions(run_id, member_id);

-- 3.3 INTERVENTION SELECTIONS (Best chosen intervention per gap)
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
CREATE INDEX IF NOT EXISTS idx_intervention_selections_run_id ON intervention_selections(run_id);

-- 3.4 OPTIMIZATION RESULTS (MILP optimizer selected members + chosen intervention)
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
CREATE INDEX IF NOT EXISTS idx_opt_results_run_id ON optimization_results(run_id);
CREATE INDEX IF NOT EXISTS idx_opt_results_run_member ON optimization_results(run_id, member_id);

-- 3.5 STAR RATING CONTRIBUTIONS (Exact calculation audit records)
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
CREATE INDEX IF NOT EXISTS idx_star_contrib_run_id ON star_rating_contributions(run_id);

-- 3.6 FINAL RECOMMENDATIONS (Final Member Report)
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
    star_contribution TEXT NOT NULL, -- Preserves exact "+0.0012" formatted contribution
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_final_rec_run_id ON final_recommendations(run_id);
CREATE INDEX IF NOT EXISTS idx_final_rec_run_member ON final_recommendations(run_id, member_id);

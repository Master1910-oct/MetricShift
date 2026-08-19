"""
Comprehensive Member Update Workflow Test Suite (MOCK MODE):

Validates all business rules and safety guarantees for Member Updates:
TEST 1: Authorized update (A, B, C, D in DB; B, D authorized & updated; A, C unchanged)
TEST 2: Unauthorized member rejected atomically (B, D, X -> HTTP 400, no partial commit)
TEST 3: Existing + new source rows (updates existing PK row, inserts new PK row)
TEST 4: Missing rows (unmentioned existing rows for authorized member are not deleted)
TEST 5: Duplicate source keys (duplicate PK in sheet -> rejected HTTP 400)
TEST 6: Static tables protected (plans, plan_benefits, cms_measures, plan_measure_performance untouched)
TEST 7: Full database after update (next pipeline runs on full DB with updated members)
TEST 8: No completed optimization (rejected HTTP 400 if no completed optimization exists)
TEST 9: Empty member update (rejected HTTP 400 if no valid member records/IDs)
TEST 10: Run isolation (upload_events records correct run_id and authorization_run_id)
"""

import os
import sys
import shutil
import tempfile
import unittest
import uuid
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient
from fastapi import HTTPException

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import backend.services.supabase_service as svc_module
from backend.main import app
from backend.services.supabase_service import SupabaseService, _MOCK_STORAGE
from backend.services.dataset_service import DatasetService


@patch.object(svc_module, "is_supabase_configured", return_value=False)
class TestMemberUpdateWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        # Clear ALL mock storage tables before each test for full isolation
        for k in list(_MOCK_STORAGE.keys()):
            _MOCK_STORAGE[k] = []
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ──────────────────────────────────────────────────────────────────────────
    # Helper to create initial baseline workbook with members A, B, C, D, E, F, G
    # ──────────────────────────────────────────────────────────────────────────

    def _create_sample_initial_workbook(self, tmp_path: str) -> str:
        plans_df = pd.DataFrame([{
            "plan_id": "P001", "contract_id": "C001", "plan_name": "Health Plus",
            "organization_name": "Org A", "plan_type": "HMO", "state": "CA",
            "overall_star_rating": 4.5, "part_c_star_rating": 4.5, "part_d_star_rating": 4.5
        }])
        plan_benefits_df = pd.DataFrame([{
            "benefit_id": "B001", "plan_id": "P001", "part": "C",
            "benefit_category": "Preventive", "service_name": "Screening",
            "coverage_status": "Covered", "frequency_limit": "Annual", "benefit_year": "2024"
        }])
        members_data = [
            {"member_condition_id": "MC_A", "member_id": "M_A", "member_name": "Alice", "date_of_birth": "01-01-1960", "age": 64, "gender": "F", "condition": "Diabetes", "condition_code": "E11"},
            {"member_condition_id": "MC_B", "member_id": "M_B", "member_name": "Bob", "date_of_birth": "02-02-1962", "age": 62, "gender": "M", "condition": "Hypertension", "condition_code": "I10"},
            {"member_condition_id": "MC_C", "member_id": "M_C", "member_name": "Charlie", "date_of_birth": "03-03-1958", "age": 66, "gender": "M", "condition": "Diabetes", "condition_code": "E11"},
            {"member_condition_id": "MC_D", "member_id": "M_D", "member_name": "Diana", "date_of_birth": "04-04-1970", "age": 54, "gender": "F", "condition": "Asthma", "condition_code": "J45"},
            {"member_condition_id": "MC_E", "member_id": "M_E", "member_name": "Eve", "date_of_birth": "05-05-1965", "age": 59, "gender": "F", "condition": "Diabetes", "condition_code": "E11"},
            {"member_condition_id": "MC_F", "member_id": "M_F", "member_name": "Frank", "date_of_birth": "06-06-1955", "age": 69, "gender": "M", "condition": "Hypertension", "condition_code": "I10"},
            {"member_condition_id": "MC_G", "member_id": "M_G", "member_name": "Grace", "date_of_birth": "07-07-1968", "age": 56, "gender": "F", "condition": "Diabetes", "condition_code": "E11"},
        ]
        members_df = pd.DataFrame(members_data)
        enrollment_df = pd.DataFrame([
            {"enrollment_id": f"EN_{m['member_id']}", "member_id": m["member_id"], "plan_id": "P001",
             "enrollment_start_date": "01-01-2024", "enrollment_end_date": "", "enrollment_status": "Active"}
            for m in members_data
        ])
        history_df = pd.DataFrame([
            {"history_id": f"H_{m['member_id']}", "member_id": m["member_id"], "service_name": "HbA1c Test",
             "test_name": "HbA1c", "service_date": "01-05-2023", "status": "Completed",
             "result": "8.5", "event_type": "Lab", "result_value": "8.5", "result_unit": "%",
             "intervention_type": "Phone Call", "action_date": "01-05-2023",
             "completion_date": "01-05-2023", "outcome": "Completed"}
            for m in members_data
        ])
        cms_measures_df = pd.DataFrame([{
            "measure_id": "C01", "official_measure_id": "CMS_C01", "measure_name": "Diabetes Care",
            "part": "C", "domain": "Clinical", "measure_type": "Process", "rating_year": 2024,
            "description": "HbA1c control", "eligibility_rule": "Age 18-75 with diabetes",
            "numerator_definition": "HbA1c <= 9%", "denominator_definition": "Diabetic patients",
            "exclusion_rule": "None", "weight": 3.0, "active": "True"
        }])
        pmp_df = pd.DataFrame([{
            "performance_id": "PMP001", "plan_id": "P001", "measure_id": "C01", "rating_year": 2024,
            "denominator": 100.0, "numerator": 75.0, "performance_value": 0.75,
            "measure_star": 4.0, "weight": 3.0
        }])
        rx_df = pd.DataFrame([
            {"rx_history_id": f"RX_{m['member_id']}", "member_id": m["member_id"],
             "medication_name": "Metformin", "ndc_code": "00093-1048-01",
             "prescription_id": f"RX_{m['member_id']}", "pharmacy_id": "PH01",
             "fill_date": "15-01-2024", "days_supply": 30, "quantity_dispensed": 60.0,
             "refill_number": 1, "claim_status": "Paid", "amount_paid": 15.0, "member_copay": 5.0}
            for m in members_data
        ])

        with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
            plans_df.to_excel(writer, sheet_name="PLANS", index=False)
            plan_benefits_df.to_excel(writer, sheet_name="PLAN_BENEFITS", index=False)
            members_df.to_excel(writer, sheet_name="MEMBERS", index=False)
            enrollment_df.to_excel(writer, sheet_name="MEMBER_ENROLLMENT", index=False)
            history_df.to_excel(writer, sheet_name="MEMBER_HISTORY", index=False)
            cms_measures_df.to_excel(writer, sheet_name="CMS_MEASURES", index=False)
            pmp_df.to_excel(writer, sheet_name="PLAN_MEASURE_PERFORMANCE", index=False)
            rx_df.to_excel(writer, sheet_name="PART_D_MEDICATION_HISTORY", index=False)

        return tmp_path

    def _seed_completed_optimization(self, run_id: str, member_ids: list):
        """Seed a completed pipeline run and its optimization results."""
        SupabaseService.register_pipeline_run(run_id, trigger_type="initial_upload")
        opt_records = [
            {"id": str(uuid.uuid4()), "run_id": run_id, "member_id": mid, "recommended_intervention": "SMS"}
            for mid in member_ids
        ]
        SupabaseService.bulk_upsert("optimization_results", opt_records)
        SupabaseService.update_pipeline_run(run_id, status="completed")

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 1: Authorized update
    # ──────────────────────────────────────────────────────────────────────────

    def test_01_authorized_member_update_success(self, _mock_cfg):
        """
        TEST 1: Current DB: A, B, C, D, E, F, G.
        Latest optimization: M_B, M_D, M_F.
        Upload: M_B, M_D, M_F.
        Verify: M_A, M_C, M_E, M_G UNCHANGED; M_B, M_D, M_F UPDATED.
        """
        initial_path = os.path.join(self.temp_dir, "initial.xlsx")
        update_path = os.path.join(self.temp_dir, "update.xlsx")

        self._create_sample_initial_workbook(initial_path)
        DatasetService.sync_initial_dataset(initial_path, run_id=str(uuid.uuid4()))

        opt_run_id = str(uuid.uuid4())
        self._seed_completed_optimization(opt_run_id, ["M_B", "M_D", "M_F"])

        updated_members_df = pd.DataFrame([
            {"member_condition_id": "MC_B", "member_id": "M_B", "member_name": "Bob UPDATED",
             "date_of_birth": "02-02-1962", "age": 63, "gender": "M",
             "condition": "Hypertension Controlled", "condition_code": "I10"},
            {"member_condition_id": "MC_D", "member_id": "M_D", "member_name": "Diana UPDATED",
             "date_of_birth": "04-04-1970", "age": 55, "gender": "F",
             "condition": "Asthma Controlled", "condition_code": "J45"},
            {"member_condition_id": "MC_F", "member_id": "M_F", "member_name": "Frank UPDATED",
             "date_of_birth": "06-06-1955", "age": 70, "gender": "M",
             "condition": "Hypertension Controlled", "condition_code": "I10"},
        ])
        with pd.ExcelWriter(update_path, engine="openpyxl") as writer:
            updated_members_df.to_excel(writer, sheet_name="MEMBERS", index=False)

        with open(update_path, "rb") as f:
            res = self.client.post(
                "/api/dataset/member-update",
                files={"file": ("update.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["mode"], "member_update")
        self.assertEqual(data["authorization_run_id"], opt_run_id)
        self.assertEqual(data["affected_members"], 3)

        current_members = SupabaseService.fetch_all("members")
        self.assertEqual(len(current_members), 7)

        member_map = {m["member_id"]: m for m in current_members}
        # Unaffected members UNCHANGED
        self.assertEqual(member_map["M_A"]["member_name"], "Alice")
        self.assertEqual(member_map["M_A"]["age"], 64)
        self.assertEqual(member_map["M_C"]["member_name"], "Charlie")
        self.assertEqual(member_map["M_E"]["member_name"], "Eve")
        self.assertEqual(member_map["M_G"]["member_name"], "Grace")

        # Authorized members UPDATED
        self.assertEqual(member_map["M_B"]["member_name"], "Bob UPDATED")
        self.assertEqual(member_map["M_B"]["age"], 63)
        self.assertEqual(member_map["M_D"]["member_name"], "Diana UPDATED")
        self.assertEqual(member_map["M_D"]["age"], 55)
        self.assertEqual(member_map["M_F"]["member_name"], "Frank UPDATED")
        self.assertEqual(member_map["M_F"]["age"], 70)

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 2: Unauthorized member rejected atomically
    # ──────────────────────────────────────────────────────────────────────────

    def test_02_unauthorized_member_rejected_atomically(self, _mock_cfg):
        """
        TEST 2: Latest optimization: M_B, M_D.
        Upload: M_B, M_D, M_X (unauthorized).
        Verify: Rejected (HTTP 400), M_B & M_D unchanged, M_X not inserted.
        """
        initial_path = os.path.join(self.temp_dir, "initial.xlsx")
        unauth_path = os.path.join(self.temp_dir, "unauth.xlsx")

        self._create_sample_initial_workbook(initial_path)
        DatasetService.sync_initial_dataset(initial_path, run_id=str(uuid.uuid4()))

        opt_run_id = str(uuid.uuid4())
        self._seed_completed_optimization(opt_run_id, ["M_B", "M_D"])

        unauthorized_df = pd.DataFrame([
            {"member_condition_id": "MC_B", "member_id": "M_B", "member_name": "Bob SHOULD_NOT_CHANGE",
             "date_of_birth": "02-02-1962", "age": 99, "gender": "M",
             "condition": "Hypertension", "condition_code": "I10"},
            {"member_condition_id": "MC_D", "member_id": "M_D", "member_name": "Diana SHOULD_NOT_CHANGE",
             "date_of_birth": "04-04-1970", "age": 99, "gender": "F",
             "condition": "Asthma", "condition_code": "J45"},
            {"member_condition_id": "MC_X", "member_id": "M_X", "member_name": "Xavier UNAUTHORIZED",
             "date_of_birth": "08-08-1980", "age": 44, "gender": "M",
             "condition": "Unknown", "condition_code": "Z00"},
        ])
        with pd.ExcelWriter(unauth_path, engine="openpyxl") as writer:
            unauthorized_df.to_excel(writer, sheet_name="MEMBERS", index=False)

        with open(unauth_path, "rb") as f:
            res = self.client.post(
                "/api/dataset/member-update",
                files={"file": ("unauth.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        self.assertEqual(res.status_code, 400)
        self.assertIn("not present in latest completed optimization", res.json()["detail"].lower())

        # Verify all 4 member tables are completely untouched
        current_members = SupabaseService.fetch_all("members")
        self.assertEqual(len(current_members), 7)
        member_map = {m["member_id"]: m for m in current_members}
        self.assertNotIn("M_X", member_map)
        self.assertEqual(member_map["M_B"]["member_name"], "Bob")
        self.assertEqual(member_map["M_B"]["age"], 62)
        self.assertEqual(member_map["M_D"]["member_name"], "Diana")
        self.assertEqual(member_map["M_D"]["age"], 54)

        current_enrollment = SupabaseService.fetch_all("member_enrollment")
        self.assertEqual(len(current_enrollment), 7)

        current_history = SupabaseService.fetch_all("member_history")
        self.assertEqual(len(current_history), 7)

        current_rx = SupabaseService.fetch_all("part_d_medication_history")
        self.assertEqual(len(current_rx), 7)

        # Verify upload_events has failed audit entry with rejected_member_count = 1
        events = _MOCK_STORAGE.get("upload_events", [])
        failed_evts = [e for e in events if e.get("upload_type") == "member_update" and e.get("status") == "failed"]
        self.assertEqual(len(failed_evts), 1)
        evt = failed_evts[0]
        self.assertEqual(evt["authorized_optimization_run_id"], opt_run_id)
        self.assertEqual(evt["rejected_member_count"], 1)
        self.assertEqual(evt["affected_member_count"], 0)
        self.assertEqual(evt["inserted_row_count"], 0)
        self.assertEqual(evt["updated_row_count"], 0)
        self.assertIsNotNone(evt["error_message"])

        # Verify pipeline_runs status is failed
        p_runs = SupabaseService.fetch_all("pipeline_runs", filters={"id": evt["run_id"]})
        self.assertEqual(len(p_runs), 1)
        self.assertEqual(p_runs[0]["status"], "failed")

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 3: Existing + new source rows
    # ──────────────────────────────────────────────────────────────────────────

    def test_03_existing_and_new_source_rows(self, _mock_cfg):
        """
        TEST 3: Authorized member M_B uploads 1 existing condition row (MC_B)
        and 1 new condition row (MC_B_2).
        Verify: MC_B updated, MC_B_2 inserted, total members rows becomes 8.
        """
        initial_path = os.path.join(self.temp_dir, "initial.xlsx")
        update_path = os.path.join(self.temp_dir, "update.xlsx")

        self._create_sample_initial_workbook(initial_path)
        DatasetService.sync_initial_dataset(initial_path, run_id=str(uuid.uuid4()))

        opt_run_id = str(uuid.uuid4())
        self._seed_completed_optimization(opt_run_id, ["M_B"])

        updated_df = pd.DataFrame([
            {"member_condition_id": "MC_B", "member_id": "M_B", "member_name": "Bob UPDATED",
             "date_of_birth": "02-02-1962", "age": 63, "gender": "M",
             "condition": "Hypertension", "condition_code": "I10"},
            {"member_condition_id": "MC_B_2", "member_id": "M_B", "member_name": "Bob UPDATED",
             "date_of_birth": "02-02-1962", "age": 63, "gender": "M",
             "condition": "Diabetes Added", "condition_code": "E11"},
        ])
        with pd.ExcelWriter(update_path, engine="openpyxl") as writer:
            updated_df.to_excel(writer, sheet_name="MEMBERS", index=False)

        with open(update_path, "rb") as f:
            res = self.client.post(
                "/api/dataset/member-update",
                files={"file": ("update.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        self.assertEqual(res.status_code, 200)

        members = SupabaseService.fetch_all("members")
        self.assertEqual(len(members), 8)  # 7 original - 1 updated + 1 inserted = 8
        mc_map = {m["member_condition_id"]: m for m in members}
        self.assertIn("MC_B", mc_map)
        self.assertIn("MC_B_2", mc_map)
        self.assertEqual(mc_map["MC_B"]["member_name"], "Bob UPDATED")
        self.assertEqual(mc_map["MC_B_2"]["condition"], "Diabetes Added")

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 4: Missing rows not deleted
    # ──────────────────────────────────────────────────────────────────────────

    def test_04_missing_rows_not_deleted(self, _mock_cfg):
        """
        TEST 4: Authorized member M_B updates MEMBERS sheet, but does NOT upload
        MEMBER_HISTORY sheet.
        Verify: M_B's existing MEMBER_HISTORY row remains intact.
        """
        initial_path = os.path.join(self.temp_dir, "initial.xlsx")
        update_path = os.path.join(self.temp_dir, "update.xlsx")

        self._create_sample_initial_workbook(initial_path)
        DatasetService.sync_initial_dataset(initial_path, run_id=str(uuid.uuid4()))

        opt_run_id = str(uuid.uuid4())
        self._seed_completed_optimization(opt_run_id, ["M_B"])

        # Update contains only MEMBERS sheet
        updated_df = pd.DataFrame([
            {"member_condition_id": "MC_B", "member_id": "M_B", "member_name": "Bob UPDATED",
             "date_of_birth": "02-02-1962", "age": 63, "gender": "M",
             "condition": "Hypertension", "condition_code": "I10"},
        ])
        with pd.ExcelWriter(update_path, engine="openpyxl") as writer:
            updated_df.to_excel(writer, sheet_name="MEMBERS", index=False)

        with open(update_path, "rb") as f:
            res = self.client.post(
                "/api/dataset/member-update",
                files={"file": ("update.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        self.assertEqual(res.status_code, 200)

        # Verify history for M_B is still present
        histories = SupabaseService.fetch_all("member_history")
        self.assertEqual(len(histories), 7)
        h_b = [h for h in histories if h["member_id"] == "M_B"]
        self.assertEqual(len(h_b), 1)
        self.assertEqual(h_b[0]["history_id"], "H_M_B")

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 5: Duplicate source keys rejected
    # ──────────────────────────────────────────────────────────────────────────

    def test_05_duplicate_source_keys_rejected(self, _mock_cfg):
        """
        TEST 5: Upload contains duplicate member_condition_id 'MC_B' in MEMBERS sheet.
        Verify: Rejected (HTTP 400), no changes to database.
        """
        initial_path = os.path.join(self.temp_dir, "initial.xlsx")
        dup_path = os.path.join(self.temp_dir, "dup.xlsx")

        self._create_sample_initial_workbook(initial_path)
        DatasetService.sync_initial_dataset(initial_path, run_id=str(uuid.uuid4()))

        opt_run_id = str(uuid.uuid4())
        self._seed_completed_optimization(opt_run_id, ["M_B"])

        dup_df = pd.DataFrame([
            {"member_condition_id": "MC_B", "member_id": "M_B", "member_name": "Bob 1",
             "date_of_birth": "02-02-1962", "age": 63, "gender": "M",
             "condition": "Hypertension", "condition_code": "I10"},
            {"member_condition_id": "MC_B", "member_id": "M_B", "member_name": "Bob 2 (duplicate PK)",
             "date_of_birth": "02-02-1962", "age": 63, "gender": "M",
             "condition": "Hypertension", "condition_code": "I10"},
        ])
        with pd.ExcelWriter(dup_path, engine="openpyxl") as writer:
            dup_df.to_excel(writer, sheet_name="MEMBERS", index=False)

        with open(dup_path, "rb") as f:
            res = self.client.post(
                "/api/dataset/member-update",
                files={"file": ("dup.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        self.assertEqual(res.status_code, 400)
        self.assertIn("duplicate", res.json()["detail"].lower())

        # Verify DB is completely untouched
        members = SupabaseService.fetch_all("members")
        m_b = [m for m in members if m["member_id"] == "M_B"][0]
        self.assertEqual(m_b["member_name"], "Bob")
        self.assertEqual(m_b["age"], 62)

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 6: Static tables protected
    # ──────────────────────────────────────────────────────────────────────────

    def test_06_static_tables_protected_from_modification(self, _mock_cfg):
        """
        TEST 6: Upload workbook includes a modified PLANS sheet.
        Verify: Member update does NOT modify PLANS table.
        """
        initial_path = os.path.join(self.temp_dir, "initial.xlsx")
        update_path = os.path.join(self.temp_dir, "update.xlsx")

        self._create_sample_initial_workbook(initial_path)
        DatasetService.sync_initial_dataset(initial_path, run_id=str(uuid.uuid4()))

        opt_run_id = str(uuid.uuid4())
        self._seed_completed_optimization(opt_run_id, ["M_B"])

        updated_members_df = pd.DataFrame([
            {"member_condition_id": "MC_B", "member_id": "M_B", "member_name": "Bob UPDATED",
             "date_of_birth": "02-02-1962", "age": 63, "gender": "M",
             "condition": "Hypertension", "condition_code": "I10"},
        ])
        malicious_plans_df = pd.DataFrame([{
            "plan_id": "P001", "contract_id": "C001", "plan_name": "MODIFIED PLAN NAME",
            "organization_name": "MODIFIED ORG", "plan_type": "HMO", "state": "CA",
            "overall_star_rating": 1.0, "part_c_star_rating": 1.0, "part_d_star_rating": 1.0
        }])

        with pd.ExcelWriter(update_path, engine="openpyxl") as writer:
            malicious_plans_df.to_excel(writer, sheet_name="PLANS", index=False)
            updated_members_df.to_excel(writer, sheet_name="MEMBERS", index=False)

        with open(update_path, "rb") as f:
            res = self.client.post(
                "/api/dataset/member-update",
                files={"file": ("update.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        self.assertEqual(res.status_code, 200)

        # Verify PLANS table was NOT changed
        plans = SupabaseService.fetch_all("plans")
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["plan_name"], "Health Plus")
        self.assertEqual(plans[0]["overall_star_rating"], 4.5)

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 7: Full database export after update
    # ──────────────────────────────────────────────────────────────────────────

    def test_07_full_database_exported_after_update(self, _mock_cfg):
        """
        TEST 7: After updating M_B and M_D, export_current_db_to_working_excel
        must export all 7 members: A + B(updated) + C + D(updated) + E + F + G.
        """
        initial_path = os.path.join(self.temp_dir, "initial.xlsx")
        update_path = os.path.join(self.temp_dir, "update.xlsx")
        working_path = os.path.join(self.temp_dir, "working.xlsx")

        self._create_sample_initial_workbook(initial_path)
        DatasetService.sync_initial_dataset(initial_path, run_id=str(uuid.uuid4()))

        opt_run_id = str(uuid.uuid4())
        self._seed_completed_optimization(opt_run_id, ["M_B", "M_D"])

        updated_members_df = pd.DataFrame([
            {"member_condition_id": "MC_B", "member_id": "M_B", "member_name": "Bob UPDATED",
             "date_of_birth": "02-02-1962", "age": 63, "gender": "M",
             "condition": "Hypertension", "condition_code": "I10"},
            {"member_condition_id": "MC_D", "member_id": "M_D", "member_name": "Diana UPDATED",
             "date_of_birth": "04-04-1970", "age": 55, "gender": "F",
             "condition": "Asthma", "condition_code": "J45"},
        ])
        with pd.ExcelWriter(update_path, engine="openpyxl") as writer:
            updated_members_df.to_excel(writer, sheet_name="MEMBERS", index=False)

        with open(update_path, "rb") as f:
            self.client.post(
                "/api/dataset/member-update",
                files={"file": ("update.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        out_file = DatasetService.export_current_db_to_working_excel(working_path)
        xl = pd.ExcelFile(out_file)
        members_df = xl.parse("MEMBERS")

        self.assertEqual(len(members_df), 7)
        self.assertEqual(set(members_df["member_id"]), {"M_A", "M_B", "M_C", "M_D", "M_E", "M_F", "M_G"})
        b_row = members_df[members_df["member_id"] == "M_B"].iloc[0]
        self.assertEqual(b_row["member_name"], "Bob UPDATED")

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 8: No completed optimization rejects update
    # ──────────────────────────────────────────────────────────────────────────

    def test_08_no_completed_optimization_rejects_update(self, _mock_cfg):
        """
        TEST 8: If no completed optimization run exists in pipeline_runs,
        reject member-update with HTTP 400.
        """
        initial_path = os.path.join(self.temp_dir, "initial.xlsx")
        update_path = os.path.join(self.temp_dir, "update.xlsx")

        self._create_sample_initial_workbook(initial_path)
        DatasetService.sync_initial_dataset(initial_path, run_id=str(uuid.uuid4()))

        # Note: We do NOT seed any completed optimization run here!
        updated_members_df = pd.DataFrame([
            {"member_condition_id": "MC_B", "member_id": "M_B", "member_name": "Bob UPDATED",
             "date_of_birth": "02-02-1962", "age": 63, "gender": "M",
             "condition": "Hypertension", "condition_code": "I10"},
        ])
        with pd.ExcelWriter(update_path, engine="openpyxl") as writer:
            updated_members_df.to_excel(writer, sheet_name="MEMBERS", index=False)

        with open(update_path, "rb") as f:
            res = self.client.post(
                "/api/dataset/member-update",
                files={"file": ("update.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        self.assertEqual(res.status_code, 400)
        self.assertIn("no completed optimization run found", res.json()["detail"].lower())

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 9: Empty member update rejected
    # ──────────────────────────────────────────────────────────────────────────

    def test_09_empty_member_update_rejected(self, _mock_cfg):
        """
        TEST 9: Reject if no valid member-specific records or member IDs supplied.
        """
        initial_path = os.path.join(self.temp_dir, "initial.xlsx")
        empty_path = os.path.join(self.temp_dir, "empty.xlsx")

        self._create_sample_initial_workbook(initial_path)
        DatasetService.sync_initial_dataset(initial_path, run_id=str(uuid.uuid4()))

        opt_run_id = str(uuid.uuid4())
        self._seed_completed_optimization(opt_run_id, ["M_B"])

        # Empty MEMBERS sheet
        empty_df = pd.DataFrame(columns=["member_condition_id", "member_id", "member_name"])
        with pd.ExcelWriter(empty_path, engine="openpyxl") as writer:
            empty_df.to_excel(writer, sheet_name="MEMBERS", index=False)

        with open(empty_path, "rb") as f:
            res = self.client.post(
                "/api/dataset/member-update",
                files={"file": ("empty.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        self.assertEqual(res.status_code, 400)
        self.assertIn("no valid member", res.json()["detail"].lower())

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 10: Exact upload_events schema and fields validation
    # ──────────────────────────────────────────────────────────────────────────

    def test_10_upload_events_exact_schema_and_fields(self, _mock_cfg):
        """
        TEST 10: Verify upload_events records exact live schema fields:
        - upload_type = 'member_update'
        - run_id is populated
        - authorized_optimization_run_id is populated
        - affected_member_count = 1
        - inserted_row_count = 1 (MC_B_NEW)
        - updated_row_count = 1 (MC_B)
        - rejected_member_count = 0
        - status = 'completed'
        - error_message = None
        - started_at and completed_at are valid ISO timestamps
        """
        initial_path = os.path.join(self.temp_dir, "initial.xlsx")
        update_path = os.path.join(self.temp_dir, "update.xlsx")

        self._create_sample_initial_workbook(initial_path)
        DatasetService.sync_initial_dataset(initial_path, run_id=str(uuid.uuid4()))

        opt_run_id = str(uuid.uuid4())
        self._seed_completed_optimization(opt_run_id, ["M_B"])

        # Upload 1 existing row (MC_B) and 1 new row (MC_B_NEW) for M_B
        updated_members_df = pd.DataFrame([
            {"member_condition_id": "MC_B", "member_id": "M_B", "member_name": "Bob UPDATED",
             "date_of_birth": "02-02-1962", "age": 63, "gender": "M",
             "condition": "Hypertension", "condition_code": "I10"},
            {"member_condition_id": "MC_B_NEW", "member_id": "M_B", "member_name": "Bob UPDATED",
             "date_of_birth": "02-02-1962", "age": 63, "gender": "M",
             "condition": "Diabetes Added", "condition_code": "E11"},
        ])
        with pd.ExcelWriter(update_path, engine="openpyxl") as writer:
            updated_members_df.to_excel(writer, sheet_name="MEMBERS", index=False)

        with open(update_path, "rb") as f:
            res = self.client.post(
                "/api/dataset/member-update",
                files={"file": ("update.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        job_id = data["job_id"]

        # Check upload_events
        events = _MOCK_STORAGE.get("upload_events", [])
        update_events = [e for e in events if e.get("upload_type") == "member_update"]
        self.assertEqual(len(update_events), 1)
        evt = update_events[0]

        self.assertEqual(evt["upload_type"], "member_update")
        self.assertEqual(evt["source_file_name"], "update.xlsx")
        self.assertEqual(evt["run_id"], job_id)
        self.assertEqual(evt["authorized_optimization_run_id"], opt_run_id)
        self.assertEqual(evt["affected_member_count"], 1)
        self.assertEqual(evt["inserted_row_count"], 1)
        self.assertEqual(evt["updated_row_count"], 1)
        self.assertEqual(evt["rejected_member_count"], 0)
        self.assertEqual(evt["status"], "completed")
        self.assertIsNone(evt["error_message"])
        self.assertTrue(bool(evt.get("started_at")))
        self.assertTrue(bool(evt.get("completed_at")))

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 11: Failed update records upload_events status='failed' and error
    # ──────────────────────────────────────────────────────────────────────────

    def test_11_failed_update_records_upload_events_status_and_error(self, _mock_cfg):
        """
        TEST 11: When an unauthorized member is uploaded:
        - upload_events records status='failed'
        - rejected_member_count = 1
        - error_message contains details
        - authorized_optimization_run_id is recorded
        """
        initial_path = os.path.join(self.temp_dir, "initial.xlsx")
        unauth_path = os.path.join(self.temp_dir, "unauth.xlsx")

        self._create_sample_initial_workbook(initial_path)
        DatasetService.sync_initial_dataset(initial_path, run_id=str(uuid.uuid4()))

        opt_run_id = str(uuid.uuid4())
        self._seed_completed_optimization(opt_run_id, ["M_B"])

        unauth_df = pd.DataFrame([
            {"member_condition_id": "MC_X", "member_id": "M_X", "member_name": "Xavier UNAUTHORIZED",
             "date_of_birth": "08-08-1980", "age": 44, "gender": "M",
             "condition": "Unknown", "condition_code": "Z00"},
        ])
        with pd.ExcelWriter(unauth_path, engine="openpyxl") as writer:
            unauth_df.to_excel(writer, sheet_name="MEMBERS", index=False)

        with open(unauth_path, "rb") as f:
            res = self.client.post(
                "/api/dataset/member-update",
                files={"file": ("unauth.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        self.assertEqual(res.status_code, 400)

        events = _MOCK_STORAGE.get("upload_events", [])
        failed_events = [e for e in events if e.get("upload_type") == "member_update"]
        self.assertEqual(len(failed_events), 1)
        evt = failed_events[0]

        self.assertEqual(evt["upload_type"], "member_update")
        self.assertEqual(evt["status"], "failed")
        self.assertEqual(evt["authorized_optimization_run_id"], opt_run_id)
        self.assertEqual(evt["rejected_member_count"], 1)
        self.assertIsNotNone(evt["error_message"])
        self.assertIn("not present in latest completed optimization", evt["error_message"].lower())

    # ──────────────────────────────────────────────────────────────────────────
    # TEST 12: No dataset_update_logs dependency in member update audit path
    # ──────────────────────────────────────────────────────────────────────────

    def test_12_no_dataset_update_logs_dependency_in_member_update(self, _mock_cfg):
        """
        TEST 12: Verify that successful and failed member-update calls write exclusively
        to upload_events and do not populate dataset_update_logs.
        """
        initial_path = os.path.join(self.temp_dir, "initial.xlsx")
        update_path = os.path.join(self.temp_dir, "update.xlsx")

        self._create_sample_initial_workbook(initial_path)
        DatasetService.sync_initial_dataset(initial_path, run_id=str(uuid.uuid4()))

        opt_run_id = str(uuid.uuid4())
        self._seed_completed_optimization(opt_run_id, ["M_B"])

        # Clear dataset_update_logs to test member_update in isolation
        _MOCK_STORAGE["dataset_update_logs"] = []

        updated_members_df = pd.DataFrame([
            {"member_condition_id": "MC_B", "member_id": "M_B", "member_name": "Bob UPDATED",
             "date_of_birth": "02-02-1962", "age": 63, "gender": "M",
             "condition": "Hypertension", "condition_code": "I10"},
        ])
        with pd.ExcelWriter(update_path, engine="openpyxl") as writer:
            updated_members_df.to_excel(writer, sheet_name="MEMBERS", index=False)

        with open(update_path, "rb") as f:
            res = self.client.post(
                "/api/dataset/member-update",
                files={"file": ("update.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        self.assertEqual(res.status_code, 200)

        # upload_events must be populated
        self.assertEqual(len(_MOCK_STORAGE.get("upload_events", [])), 2)  # initial_upload + member_update
        # dataset_update_logs must remain empty for member_update
        member_update_logs = [l for l in _MOCK_STORAGE.get("dataset_update_logs", []) if l.get("update_type") == "member_update"]
        self.assertEqual(len(member_update_logs), 0)


if __name__ == "__main__":
    unittest.main()


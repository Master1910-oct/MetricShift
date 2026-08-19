"""
Unit tests for date normalization in backend/services/dataset_service.py.

Covers normalize_date_value() and normalize_date_columns() for:
- DD-MM-YYYY strings (workbook format) -> YYYY-MM-DD
- Already-ISO YYYY-MM-DD strings       -> unchanged
- Python date / datetime / Timestamp   -> isoformat
- None / NaN / NaT / blank             -> None
- Invalid non-empty dates              -> ValueError
"""

import math
import sys
import os
import unittest
from datetime import date, datetime

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services.dataset_service import normalize_date_value, normalize_date_columns


class TestNormalizeDateValue(unittest.TestCase):
    # ── Null-like inputs ──────────────────────────────────────────────────────
    def test_none_returns_none(self):
        self.assertIsNone(normalize_date_value(None))

    def test_nat_returns_none(self):
        self.assertIsNone(normalize_date_value(pd.NaT))

    def test_float_nan_returns_none(self):
        self.assertIsNone(normalize_date_value(float("nan")))

    def test_numpy_nan_returns_none(self):
        self.assertIsNone(normalize_date_value(np.nan))

    def test_empty_string_returns_none(self):
        self.assertIsNone(normalize_date_value(""))

    def test_whitespace_string_returns_none(self):
        self.assertIsNone(normalize_date_value("   "))

    # ── DD-MM-YYYY workbook format ────────────────────────────────────────────
    def test_dd_mm_yyyy_converts_correctly(self):
        self.assertEqual(normalize_date_value("16-05-1945"), "1945-05-16")

    def test_dd_mm_yyyy_02_01_2020(self):
        """01-02-2020 must be treated as day=01, month=02 -> 2020-02-01."""
        self.assertEqual(normalize_date_value("01-02-2020"), "2020-02-01")

    def test_dd_mm_yyyy_end_of_year(self):
        self.assertEqual(normalize_date_value("31-12-2023"), "2023-12-31")

    def test_dd_mm_yyyy_leap_day(self):
        self.assertEqual(normalize_date_value("29-02-2000"), "2000-02-29")

    # ── Already-ISO YYYY-MM-DD strings ───────────────────────────────────────
    def test_iso_string_unchanged(self):
        self.assertEqual(normalize_date_value("2020-02-01"), "2020-02-01")

    def test_iso_string_historical(self):
        self.assertEqual(normalize_date_value("1945-05-16"), "1945-05-16")

    # ── Native Python / pandas types ─────────────────────────────────────────
    def test_python_date_object(self):
        self.assertEqual(normalize_date_value(date(2022, 3, 15)), "2022-03-15")

    def test_python_datetime_object(self):
        self.assertEqual(normalize_date_value(datetime(2022, 3, 15, 12, 30, 0)), "2022-03-15")

    def test_pandas_timestamp(self):
        self.assertEqual(normalize_date_value(pd.Timestamp("2021-07-04")), "2021-07-04")

    def test_pandas_timestamp_nat(self):
        self.assertIsNone(normalize_date_value(pd.NaT))

    # ── Invalid dates ─────────────────────────────────────────────────────────
    def test_invalid_dd_mm_yyyy_impossible_day_raises(self):
        """32-01-2020 has day=32 which is impossible."""
        with self.assertRaises(ValueError):
            normalize_date_value("32-01-2020", column_name="date_of_birth")

    def test_invalid_leap_day_non_leap_year_raises(self):
        """29-02-2001 is not a real date (2001 is not a leap year)."""
        with self.assertRaises(ValueError):
            normalize_date_value("29-02-2001", column_name="date_of_birth")

    def test_invalid_iso_date_raises(self):
        with self.assertRaises(ValueError):
            normalize_date_value("2020-13-01", column_name="service_date")

    def test_unrecognised_format_raises(self):
        with self.assertRaises(ValueError):
            normalize_date_value("March 2020", column_name="fill_date")

    def test_partial_string_raises(self):
        with self.assertRaises(ValueError):
            normalize_date_value("2020/01/15", column_name="action_date")


class TestNormalizeDateColumns(unittest.TestCase):
    """Tests for the DataFrame-level normalization helper."""

    def _make_df(self, dates, col="date_of_birth"):
        return pd.DataFrame({col: dates, "member_id": ["M1", "M2", "M3", "M4"]})

    def test_members_sheet_date_of_birth(self):
        df = self._make_df(["16-05-1945", "01-02-2020", "2020-02-01", None])
        result = normalize_date_columns(df, "MEMBERS")
        vals = result["date_of_birth"].tolist()
        self.assertEqual(vals[0], "1945-05-16")
        self.assertEqual(vals[1], "2020-02-01")
        self.assertEqual(vals[2], "2020-02-01")
        # pandas stores Python None as float NaN in object columns; both mean NULL
        self.assertTrue(vals[3] is None or (isinstance(vals[3], float) and math.isnan(vals[3])))

    def test_member_enrollment_two_date_cols(self):
        df = pd.DataFrame({
            "enrollment_id": ["E1", "E2"],
            "member_id": ["M1", "M2"],
            "enrollment_start_date": ["01-01-2023", "15-06-2022"],
            "enrollment_end_date": [None, "31-12-2023"],
        })
        result = normalize_date_columns(df, "MEMBER_ENROLLMENT")
        self.assertEqual(result["enrollment_start_date"].tolist(), ["2023-01-01", "2022-06-15"])
        end_vals = result["enrollment_end_date"].tolist()
        # first slot was None -> pandas may represent as NaN; either is acceptable SQL NULL
        self.assertTrue(end_vals[0] is None or (isinstance(end_vals[0], float) and math.isnan(end_vals[0])))
        self.assertEqual(end_vals[1], "2023-12-31")

    def test_member_history_three_date_cols(self):
        df = pd.DataFrame({
            "history_id": ["H1"],
            "member_id": ["M1"],
            "service_date": ["10-03-2023"],
            "action_date": [pd.Timestamp("2023-04-05")],
            "completion_date": [None],
        })
        result = normalize_date_columns(df, "MEMBER_HISTORY")
        self.assertEqual(result["service_date"].tolist(), ["2023-03-10"])
        self.assertEqual(result["action_date"].tolist(), ["2023-04-05"])
        self.assertIsNone(result["completion_date"].tolist()[0])

    def test_part_d_fill_date(self):
        df = pd.DataFrame({
            "rx_history_id": ["R1", "R2"],
            "member_id": ["M1", "M2"],
            "fill_date": ["28-02-2024", float("nan")],
        })
        result = normalize_date_columns(df, "PART_D_MEDICATION_HISTORY")
        self.assertEqual(result["fill_date"].tolist()[0], "2024-02-28")
        null_val = result["fill_date"].tolist()[1]
        # NaN or None both map to SQL NULL after sanitize_dataframe()
        self.assertTrue(null_val is None or (isinstance(null_val, float) and math.isnan(null_val)))

    def test_unknown_sheet_returns_unchanged(self):
        df = pd.DataFrame({"plan_id": ["P1"], "some_col": ["no change"]})
        result = normalize_date_columns(df, "PLANS")
        pd.testing.assert_frame_equal(result, df)

    def test_missing_date_col_is_skipped(self):
        """If a date column is defined in SHEET_DATE_COLUMNS but missing from df, skip gracefully."""
        df = pd.DataFrame({"member_condition_id": ["MC1"], "member_id": ["M1"]})
        # MEMBERS expects date_of_birth but it is absent
        result = normalize_date_columns(df, "MEMBERS")
        self.assertNotIn("date_of_birth", result.columns)

    def test_original_df_not_mutated(self):
        df = pd.DataFrame({"date_of_birth": ["16-05-1945"], "member_id": ["M1"]})
        _ = normalize_date_columns(df, "MEMBERS")
        # original should be untouched
        self.assertEqual(df["date_of_birth"].tolist(), ["16-05-1945"])

    def test_invalid_date_raises_http_exception(self):
        from fastapi import HTTPException
        df = pd.DataFrame({"date_of_birth": ["99-99-9999"], "member_id": ["M1"]})
        with self.assertRaises(HTTPException) as ctx:
            normalize_date_columns(df, "MEMBERS")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Date normalisation error", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()

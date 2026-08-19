"""
ML Inference Module for Medicare Advantage Care-Gap Prediction.

Executes soft-voting ensemble inference (Random Forest + XGBoost)
on in-memory Rule Engine outputs.

Output:
    patient_id
    plan_id
    care_gap
    intervention_type
    probability_score
    uncertainity_range_lower
    uncertainity_range_upper
"""

import os
import pickle

import numpy as np
import pandas as pd


def _resolve_model_path(models_dir: str, filename: str) -> str:
    """Find a model file in models_dir or common fallback locations."""

    candidates = [
        os.path.join(models_dir, filename),
        os.path.join("models", filename),
        os.path.join("Previous", "models", filename),
        os.path.join("ml_model", "models", filename),
        os.path.join(os.path.dirname(__file__), "models", filename),
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "models",
            filename
        ),
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "Previous",
            "models",
            filename
        ),
    ]

    for path in candidates:
        if os.path.exists(path):
            return os.path.abspath(path)

    raise FileNotFoundError(
        f"Model file '{filename}' not found in any candidate path: "
        f"{candidates}"
    )


def run_inference(
    df: pd.DataFrame,
    models_dir: str = "models"
) -> pd.DataFrame:
    """
    Run ML ensemble inference on the Rule Engine DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        In-memory Rule Engine output DataFrame.

    models_dir : str, optional
        Directory containing the trained model binaries.

    Returns
    -------
    pd.DataFrame
        DataFrame containing:

        patient_id
        plan_id
        care_gap
        intervention_type
        probability_score
        uncertainity_range_lower
        uncertainity_range_upper
    """

    # ============================================================
    # 0. Empty input handling
    # ============================================================

    output_columns = [
        "patient_id",
        "plan_id",
        "care_gap",
        "intervention_type",
        "probability_score",
        "uncertainity_range_lower",
        "uncertainity_range_upper",
    ]

    if df is None or len(df) == 0:
        return pd.DataFrame(columns=output_columns)

    # ============================================================
    # 1. Validate required identifier columns
    # ============================================================

    required_identifier_columns = [
        "patient_id",
        "plan_id",
        "care_gap",
        "intervention_type",
    ]

    missing_identifiers = [
        col
        for col in required_identifier_columns
        if col not in df.columns
    ]

    if missing_identifiers:
        raise ValueError(
            "Rule Engine DataFrame is missing required ML identifier "
            f"columns: {missing_identifiers}"
        )

    # ============================================================
    # 2. Load model binaries (with in-memory caching)
    # ============================================================
    global _MODEL_CACHE
    if "_MODEL_CACHE" not in globals():
        _MODEL_CACHE = {}

    preprocessor_path = _resolve_model_path(models_dir, "preprocessor_v1.0.0.pkl")
    rf_path = _resolve_model_path(models_dir, "random_forest_v1.0.0.pkl")
    xgb_path = _resolve_model_path(models_dir, "xgboost_v1.0.0.pkl")

    if "preprocessor" not in _MODEL_CACHE:
        print(f"Loading preprocessor from: {preprocessor_path}")
        with open(preprocessor_path, "rb") as file:
            _MODEL_CACHE["preprocessor"] = pickle.load(file)

    if "rf" not in _MODEL_CACHE:
        print(f"Loading Random Forest from: {rf_path}")
        with open(rf_path, "rb") as file:
            _MODEL_CACHE["rf"] = pickle.load(file)

    if "xgb" not in _MODEL_CACHE:
        print(f"Loading XGBoost from: {xgb_path}")
        with open(xgb_path, "rb") as file:
            _MODEL_CACHE["xgb"] = pickle.load(file)

    preprocessor = _MODEL_CACHE["preprocessor"]
    rf = _MODEL_CACHE["rf"]
    xgb = _MODEL_CACHE["xgb"]

    # ============================================================
    # 3. Verify ML feature columns
    # ============================================================

    # The trained preprocessor contains the exact feature schema
    # used during model training.
    expected_features = getattr(
        preprocessor,
        "feature_names_in_",
        None
    )

    # Exclude identifiers and non-feature columns.
    features = [
        col
        for col in df.columns
        if col not in [
            "patient_id",
            "member_name",
            "outcome",
        ]
    ]

    X = df[features].copy()

    # ============================================================
    # 4. Add missingness indicators
    # ============================================================

    missingness_source_columns = [
        "enrollment_tenure_days",
        "days_since_last_service",
        "days_since_last_fill",
    ]

    for column in missingness_source_columns:

        indicator_column = f"{column}_isnan"

        if column in X.columns:
            X[indicator_column] = (
                X[column].isna().astype(int)
            )
        else:
            X[indicator_column] = 0

    # ============================================================
    # 5. Validate and align features with trained preprocessor
    # ============================================================

    if expected_features is not None:

        missing_features = (
            set(expected_features)
            - set(X.columns)
        )

        if missing_features:
            raise ValueError(
                "Missing ML feature columns required by the trained "
                f"preprocessor: {sorted(missing_features)}"
            )

        # Strictly align the DataFrame to the training feature order.
        X_input = X[list(expected_features)].copy()

    else:
        X_input = X.copy()

    # ============================================================
    # 6. Preprocess features
    # ============================================================

    X_processed = preprocessor.transform(X_input)

    # ============================================================
    # 7. Generate Random Forest probabilities
    # ============================================================

    rf_probs = rf.predict_proba(X_processed)[:, 1]

    # ============================================================
    # 8. Generate XGBoost probabilities
    # ============================================================

    xgb_probs = xgb.predict_proba(X_processed)[:, 1]

    # ============================================================
    # 9. Soft-voting ensemble
    # ============================================================

    # Preserve the existing ensemble logic exactly:
    #
    # probability_score =
    #     (Random Forest probability +
    #      XGBoost probability) / 2

    ensemble_probs = (
        rf_probs + xgb_probs
    ) / 2.0

    # ============================================================
    # 10. Calculate uncertainty bounds
    # ============================================================

    uncertainity_lower = np.minimum(
        rf_probs,
        xgb_probs
    )

    uncertainity_upper = np.maximum(
        rf_probs,
        xgb_probs
    )

    # ============================================================
    # 11. Validate probability outputs
    # ============================================================

    if np.any(
        (ensemble_probs < 0)
        | (ensemble_probs > 1)
    ):
        raise ValueError(
            "Invalid probability_score detected. "
            "Probability values must be between 0 and 1."
        )

    if np.any(
        (uncertainity_lower < 0)
        | (uncertainity_lower > 1)
    ):
        raise ValueError(
            "Invalid uncertainty lower bound detected."
        )

    if np.any(
        (uncertainity_upper < 0)
        | (uncertainity_upper > 1)
    ):
        raise ValueError(
            "Invalid uncertainty upper bound detected."
        )

    # ============================================================
    # 12. Build final ML output
    # ============================================================

    results_df = pd.DataFrame({
        "patient_id": df["patient_id"].values,
        "plan_id": df["plan_id"].values,
        "care_gap": df["care_gap"].values,
        "intervention_type": df["intervention_type"].values,
        "probability_score": ensemble_probs,
        "uncertainity_range_lower": uncertainity_lower,
        "uncertainity_range_upper": uncertainity_upper,
    })

    # ============================================================
    # 13. Enforce exact output schema
    # ============================================================

    return results_df[output_columns]


# ================================================================
# Standalone Testing
# ================================================================

if __name__ == "__main__":

    print("Testing ML inference module...")

    test_file = "CORRECTED_RULE_ENGINE_34_ATTRIBUTES.xlsx"

    if os.path.exists(test_file):

        test_df = pd.read_excel(
            test_file,
            sheet_name="RULE_ENGINE_OUTPUT"
        )

        output_df = run_inference(
            test_df,
            models_dir="models"
        )

        print(
            "ML Inference successful. "
            f"Output shape: {output_df.shape}"
        )

        print("\nOutput columns:")
        print(output_df.columns.tolist())

        print("\nFirst 3 predictions:")
        print(output_df.head(3))

        print("\nProbability range:")

        print(
            "Minimum:",
            output_df["probability_score"].min()
        )

        print(
            "Maximum:",
            output_df["probability_score"].max()
        )

    else:

        print(
            "No test file found. "
            "Import run_inference() in your pipeline."
        )

import os
import time
import pickle
import pandas as pd
import numpy as np
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, brier_score_loss, confusion_matrix
)
from xgboost import XGBClassifier

def main():
    print("====================================================")
    print("Starting Medicare Advantage Care-Gap Model Training")
    print("====================================================")

    # 1. Load Dataset
    data_path = "D:/CTS/Main/Cognizant Project Main/Cognizant Project Main/Training set/ML_Training_Synthetic_100K_5Plans_10Measures_UPDATED.xlsx"
    print(f"Loading dataset from: {data_path}")
    df = pd.read_excel(data_path)
    print(f"Dataset loaded. Shape: {df.shape}")

    # 2. Perform Group Train-Test Split (70/30) by patient_id
    print("\nSplitting dataset into 70% Train and 30% Test splits (patient-grouped)...")
    gss = GroupShuffleSplit(n_splits=1, train_size=0.7, random_state=42)
    train_idx, test_idx = next(gss.split(df, groups=df['patient_id']))

    train_df = df.iloc[train_idx].copy()
    test_df = df.iloc[test_idx].copy()

    print(f"  Train set: {len(train_df)} rows, {train_df['patient_id'].nunique()} unique patients")
    print(f"  Test set:  {len(test_df)} rows, {test_df['patient_id'].nunique()} unique patients")
    
    # Confirm entity overlap is zero
    overlap = set(train_df['patient_id']).intersection(set(test_df['patient_id']))
    print(f"  Patient ID overlap between splits: {len(overlap)} (Expected: 0)")
    
    # Report class stratification
    print("  Train Outcome Balance:")
    print(train_df['outcome'].value_counts(normalize=True).to_dict())
    print("  Test Outcome Balance:")
    print(test_df['outcome'].value_counts(normalize=True).to_dict())

    # 3. Define features and target
    target = 'outcome'
    features = [col for col in df.columns if col not in ['patient_id', 'outcome']]

    X_train = train_df[features].copy()
    y_train = train_df[target].copy()
    X_test = test_df[features].copy()
    y_test = test_df[target].copy()

    # Preserve demographic columns for fairness checks
    protected_attributes = ['age', 'gender']
    X_test_protected = test_df[protected_attributes].copy()

    # 4. Feature Engineering & Preprocessing
    print("\nApplying preprocessing pipeline...")
    # Add missingness indicator columns
    missing_cols = ['enrollment_tenure_days', 'days_since_last_service', 'days_since_last_fill']
    for col in missing_cols:
        X_train[col + '_isnan'] = X_train[col].isna().astype(int)
        X_test[col + '_isnan'] = X_test[col].isna().astype(int)

    # Separate numeric and categorical
    num_cols = X_train.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = X_train.select_dtypes(exclude=[np.number]).columns.tolist()

    print(f"  Numeric features ({len(num_cols)}): {num_cols}")
    print(f"  Categorical features ({len(cat_cols)}): {cat_cols}")

    # Build preprocessing pipeline
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', Pipeline([
                ('imputer', SimpleImputer(strategy='median')),
                ('scaler', StandardScaler())
            ]), num_cols),
            ('cat', Pipeline([
                ('imputer', SimpleImputer(strategy='constant', fill_value='missing')),
                ('encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False))
            ]), cat_cols)
        ]
    )

    X_train_processed = preprocessor.fit_transform(X_train)
    X_test_processed = preprocessor.transform(X_test)
    print(f"  Processed shape: {X_train_processed.shape}")

    # 5. Model Training
    print("\nTraining models...")
    
    # Random Forest - Regularized
    print("  Training Random Forest Classifier (max_depth=12, min_samples_leaf=5)...")
    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=12,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=-1
    )
    rf.fit(X_train_processed, y_train)

    # XGBoost - Regularized
    print("  Training XGBoost Classifier (max_depth=5, learning_rate=0.05, subsample=0.8)...")
    xgb = XGBClassifier(
        n_estimators=150,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
        eval_metric='logloss'
    )
    xgb.fit(X_train_processed, y_train)

    # 6. Evaluation on Train & Test Splits
    print("\nEvaluating model performance...")

    def evaluate_model(model_name, train_probs, train_preds, test_probs, test_preds):
        print(f"\n--- {model_name} ---")
        
        # Train metrics
        tr_acc = accuracy_score(y_train, train_preds)
        tr_prec = precision_score(y_train, train_preds)
        tr_rec = recall_score(y_train, train_preds)
        tr_f1 = f1_score(y_train, train_preds)
        tr_auc = roc_auc_score(y_train, train_probs)
        tr_brier = brier_score_loss(y_train, train_probs)
        
        print("  Train metrics:")
        print(f"    Accuracy:  {tr_acc:.4f} | Precision: {tr_prec:.4f} | Recall: {tr_rec:.4f}")
        print(f"    F1 Score:  {tr_f1:.4f} | ROC-AUC:   {tr_auc:.4f} | Brier:  {tr_brier:.4f}")
        
        # Test metrics
        te_acc = accuracy_score(y_test, test_preds)
        te_prec = precision_score(y_test, test_preds)
        te_rec = recall_score(y_test, test_preds)
        te_f1 = f1_score(y_test, test_preds)
        te_auc = roc_auc_score(y_test, test_probs)
        te_brier = brier_score_loss(y_test, test_probs)
        
        print("  Test metrics:")
        print(f"    Accuracy:  {te_acc:.4f} | Precision: {te_prec:.4f} | Recall: {te_rec:.4f}")
        print(f"    F1 Score:  {te_f1:.4f} | ROC-AUC:   {te_auc:.4f} | Brier:  {te_brier:.4f}")
        
        # Overfitting check
        gap = tr_acc - te_acc
        print(f"  Train-to-Test Accuracy Gap: {gap:.4f} (Threshold: <= 0.0200)")
        if gap > 0.02:
            print("  [Warning] Model exceeds the target overfitting gap threshold!")
        else:
            print("  [Pass] Model is well-regularized and generalizes successfully.")
            
        return {
            'accuracy': te_acc, 'precision': te_prec, 'recall': te_rec,
            'f1': te_f1, 'auc': te_auc, 'brier': te_brier, 'gap': gap
        }

    # Evaluate RF
    rf_train_probs = rf.predict_proba(X_train_processed)[:, 1]
    rf_test_probs = rf.predict_proba(X_test_processed)[:, 1]
    rf_train_preds = rf.predict(X_train_processed)
    rf_test_preds = rf.predict(X_test_processed)
    rf_results = evaluate_model("Random Forest Classifier", rf_train_probs, rf_train_preds, rf_test_probs, rf_test_preds)

    # Evaluate XGBoost
    xgb_train_probs = xgb.predict_proba(X_train_processed)[:, 1]
    xgb_test_probs = xgb.predict_proba(X_test_processed)[:, 1]
    xgb_train_preds = xgb.predict(X_train_processed)
    xgb_test_preds = xgb.predict(X_test_processed)
    xgb_results = evaluate_model("XGBoost Classifier", xgb_train_probs, xgb_train_preds, xgb_test_probs, xgb_test_preds)

    # Evaluate Ensemble (Averaged probabilities)
    ens_train_probs = (rf_train_probs + xgb_train_probs) / 2
    ens_test_probs = (rf_test_probs + xgb_test_probs) / 2
    ens_train_preds = (ens_train_probs >= 0.5).astype(int)
    ens_test_preds = (ens_test_probs >= 0.5).astype(int)
    ens_results = evaluate_model("Ensemble (Random Forest + XGBoost Soft Vote)", ens_train_probs, ens_train_preds, ens_test_probs, ens_test_preds)

    # 7. Subgroup Fairness Audit (on Ensemble results)
    print("\nPerforming Subgroup Fairness Audit on Ensemble Model...")
    
    # Age categorization
    def categorize_age(age):
        if age < 50:
            return "< 50"
        elif age <= 64:
            return "50-64"
        else:
            return "65+"

    test_subgroups = pd.DataFrame({
        'age_group': X_test_protected['age'].apply(categorize_age),
        'gender': X_test_protected['gender'],
        'true': y_test.values,
        'pred': ens_test_preds,
        'prob': ens_test_probs
    })

    print("  Accuracy by Gender Subgroup:")
    for gender, group in test_subgroups.groupby('gender'):
        acc = accuracy_score(group['true'], group['pred'])
        positive_pred_rate = (group['pred'] == 1).mean()
        print(f"    Gender: {gender:6} | Size: {len(group):6} | Accuracy: {acc:.4f} | Positive Selection Rate: {positive_pred_rate:.4f}")

    print("  Accuracy by Age Subgroup:")
    for age_gp, group in test_subgroups.groupby('age_group'):
        acc = accuracy_score(group['true'], group['pred'])
        positive_pred_rate = (group['pred'] == 1).mean()
        print(f"    Age Group: {age_gp:5} | Size: {len(group):6} | Accuracy: {acc:.4f} | Positive Selection Rate: {positive_pred_rate:.4f}")

    # Demographic Parity Check
    psr_m = (test_subgroups[test_subgroups['gender'] == 'M']['pred'] == 1).mean()
    psr_f = (test_subgroups[test_subgroups['gender'] == 'F']['pred'] == 1).mean()
    gender_dp_diff = abs(psr_m - psr_f)
    print(f"  Gender Demographic Parity Difference: {gender_dp_diff:.4f} (Threshold: <= 0.0500)")
    if gender_dp_diff <= 0.05:
        print("    [Pass] Demographic Parity holds for gender.")
    else:
        print("    [Warning] Demographic Parity is breached for gender!")

    # 8. Latency Benchmark
    print("\nPerforming Latency Benchmark (Single-Sample Inference)...")
    single_sample = X_test.iloc[[0]]
    times = []
    # Warm-up run
    _ = preprocessor.transform(single_sample)
    
    # Benchmarking runs
    for _ in range(500):
        t0 = time.perf_counter()
        sample_proc = preprocessor.transform(single_sample)
        p_rf = rf.predict_proba(sample_proc)[:, 1]
        p_xgb = xgb.predict_proba(sample_proc)[:, 1]
        _ = (p_rf + p_xgb) / 2
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000) # ms
        
    p50_latency = np.percentile(times, 50)
    p95_latency = np.percentile(times, 95)
    print(f"  p50 Latency: {p50_latency:.4f} ms")
    print(f"  p95 Latency: {p95_latency:.4f} ms")
    if p95_latency <= 10.0:
        print("  [Pass] Inference latency is within acceptable constraints.")
    else:
        print("  [Warning] Latency is higher than target limit.")

    # 9. Save Artifacts
    print("\nExporting Preprocessor and Model binaries...")
    os.makedirs("./models", exist_ok=True)
    
    with open("./models/preprocessor_v1.0.0.pkl", "wb") as f:
        pickle.dump(preprocessor, f)
        
    with open("./models/random_forest_v1.0.0.pkl", "wb") as f:
        pickle.dump(rf, f)
        
    with open("./models/xgboost_v1.0.0.pkl", "wb") as f:
        pickle.dump(xgb, f)
        
    print("  Successfully saved preprocessor, RF, and XGBoost models to directory './models/'")
    print("\n====================================================")
    print("Training Pipeline Successfully Executed!")
    print("====================================================")

if __name__ == '__main__':
    main()

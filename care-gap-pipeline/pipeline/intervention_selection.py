"""
Production Best Intervention Selection Module for Medicare Advantage Care-Gap Pipeline.

Enforces:
1. Clear ML Winner Rule: If (top_prob - second_prob) > margin (0.01), top ML winner MUST be selected.
   Clear winners CANNOT be changed.
2. Near-Tie Diversity Rule: If (top_prob - second_prob) <= margin (0.01), alternative candidates within margin
   are eligible. Prefers lower projected channel selection share (subject to 40% cap).
3. Calibration-first ranking: Evaluates calibrated probability scores.
"""

import numpy as np
import pandas as pd

CHANNEL_COST_RANK = {"Email": 0, "SMS": 1, "Phone Call": 2}
SELECTION_MARGIN = 0.01
MAX_CHANNEL_SHARE = 0.40


def select_best_interventions(
    candidate_df: pd.DataFrame,
    prob_col: str = "calibrated_probability",
    channel_col: str = "intervention_type",
    margin: float = SELECTION_MARGIN,
    max_share: float = MAX_CHANNEL_SHARE
):
    if candidate_df is None or len(candidate_df) == 0:
        return pd.DataFrame(), pd.DataFrame(), {}

    df = candidate_df.copy()

    if prob_col not in df.columns:
        if "calibrated_probability_score" in df.columns:
            prob_col = "calibrated_probability_score"
        elif "probability_score" in df.columns:
            prob_col = "probability_score"

    grouped = list(df.groupby(["patient_id", "care_gap"], sort=False))
    n_gaps = len(grouped)

    capacity = {
        ch: max(1, int(np.floor(n_gaps * max_share)))
        for ch in ["Email", "SMS", "Phone Call"]
    }
    used = {ch: 0 for ch in capacity}

    ml_winner_counts = {ch: 0 for ch in capacity}
    clear_winner_decisions = 0
    near_tie_decisions = 0
    clear_winner_changed_count = 0
    near_tie_diversity_selections = 0
    capacity_exclusions = 0

    selected_rows = []
    audit_records = []

    for (patient_id, care_gap), group in grouped:
        g_sorted = group.sort_values(prob_col, ascending=False).reset_index(drop=True)
        top_row = g_sorted.iloc[0]
        top_prob = float(top_row[prob_col])
        top_channel = str(top_row[channel_col])

        ch_probs = {}
        for _, r in g_sorted.iterrows():
            ch_probs[str(r[channel_col])] = float(r[prob_col])

        email_prob = ch_probs.get("Email", 0.0)
        sms_prob = ch_probs.get("SMS", 0.0)
        phone_prob = ch_probs.get("Phone Call", 0.0)

        ml_winner_counts[top_channel] += 1
        raw_ml_winner = top_channel
        calibrated_ml_winner = top_channel

        second_prob = float(g_sorted.iloc[1][prob_col]) if len(g_sorted) > 1 else 0.0
        winner_margin = top_prob - second_prob

        selected_row = None
        selection_type = ""
        selection_reason = ""

        if winner_margin > margin:
            clear_winner_decisions += 1
            selection_type = "CLEAR_WINNER"

            if used[top_channel] < capacity[top_channel]:
                selected_row = top_row
                used[top_channel] += 1
                selection_reason = f"Clear ML winner (margin {winner_margin:.4f} > {margin})"
            else:
                capacity_exclusions += 1
                selected_row = top_row
                used[top_channel] += 1
                selection_reason = f"Clear ML winner retained despite capacity limit"

        else:
            near_tie_decisions += 1
            selection_type = "NEAR_TIE"

            eligible_candidates = g_sorted[top_prob - g_sorted[prob_col] <= margin].copy()
            available_candidates = eligible_candidates[
                eligible_candidates[channel_col].map(lambda ch: used[ch] < capacity[ch])
            ]

            if not available_candidates.empty:
                available_candidates["_current_usage"] = available_candidates[channel_col].map(lambda ch: used[ch])
                available_candidates["_cost_rank"] = available_candidates[channel_col].map(CHANNEL_COST_RANK).fillna(2)
                available_candidates["_sort_key"] = (
                    available_candidates["_current_usage"] * 1000
                    + available_candidates["_cost_rank"] * 10
                    - available_candidates[prob_col]
                )

                chosen_cand = available_candidates.sort_values("_sort_key").iloc[0]
                selected_channel = str(chosen_cand[channel_col])

                selected_row = chosen_cand
                used[selected_channel] += 1

                if selected_channel != top_channel:
                    near_tie_diversity_selections += 1
                    selection_reason = f"Near-tie diversity choice ({selected_channel} within {margin} of {top_channel})"
                else:
                    selection_reason = f"Near-tie ML top choice ({top_channel})"
            else:
                capacity_exclusions += 1
                selected_row = top_row
                used[top_channel] += 1
                selection_reason = f"Near-tie top choice fallback ({top_channel})"

        selected_channel_name = str(selected_row[channel_col])
        selected_rows.append(selected_row.to_dict())

        audit_records.append({
            "patient_id": str(patient_id),
            "care_gap": str(care_gap),
            "email_probability": email_prob,
            "sms_probability": sms_prob,
            "phone_probability": phone_prob,
            "raw_ml_winner": raw_ml_winner,
            "calibrated_ml_winner": calibrated_ml_winner,
            "winner_margin": winner_margin,
            "selection_type": selection_type,
            "selected_intervention": selected_channel_name,
            "selection_reason": selection_reason,
            "optimizer_input_intervention": selected_channel_name,
            "final_intervention": selected_channel_name
        })

    selected_df = pd.DataFrame(selected_rows).reset_index(drop=True)
    audit_df = pd.DataFrame(audit_records)

    metrics = {
        "total_gaps": n_gaps,
        "selected_rows": len(selected_df),
        "ml_winner_counts": ml_winner_counts,
        "selected_channel_counts": used,
        "clear_winner_decisions": clear_winner_decisions,
        "near_tie_decisions": near_tie_decisions,
        "clear_winner_changed_count": clear_winner_changed_count,
        "near_tie_diversity_selections": near_tie_diversity_selections,
        "capacity_exclusions": capacity_exclusions,
        "capacity_limits": capacity
    }

    return selected_df, audit_df, metrics

"""
Intervention Candidate Generator.
Expands Rule Engine care-gap rows into actionable candidate channels (Email, SMS, Phone Call).
Preserves clinical features and historical outreach predictors without data loss.
"""

import pandas as pd

ACTIONABLE_CHANNELS = ["Email", "SMS", "Phone Call"]


def generate_intervention_candidates(
    rule_df: pd.DataFrame,
    channels: list = None
) -> pd.DataFrame:
    """Expand each eligible care-gap record into explicit actionable intervention candidates.

    Parameters
    ----------
    rule_df : pd.DataFrame
        Rule Engine output DataFrame.
    channels : list, optional
        List of actionable communication channels, by default ["Email", "SMS", "Phone Call"].

    Returns
    -------
    pd.DataFrame
        Expanded candidate DataFrame with 3x rows, each carrying an actionable intervention_type
        while preserving historical_intervention_type and all clinical attributes.
    """
    if rule_df is None or len(rule_df) == 0:
        return pd.DataFrame(columns=rule_df.columns if rule_df is not None else [])

    if channels is None:
        channels = ACTIONABLE_CHANNELS

    expanded_dfs = []
    for channel in channels:
        df_channel = rule_df.copy()
        # Preserve the historical intervention context as historical_intervention_type
        if "historical_intervention_type" not in df_channel.columns:
            df_channel["historical_intervention_type"] = df_channel["intervention_type"].astype(str)
        # Assign the candidate actionable channel for ML scoring
        df_channel["intervention_type"] = channel
        expanded_dfs.append(df_channel)

    candidate_df = pd.concat(expanded_dfs, ignore_index=True)
    return candidate_df

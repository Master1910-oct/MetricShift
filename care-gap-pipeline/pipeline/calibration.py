"""
Logit-Space Channel Calibration Module.
Removes systemic channel base-rate bias in logit space to ensure fair evaluation of patient channel propensity.
"""

import numpy as np
import pandas as pd


def _logit(p: np.ndarray | pd.Series, eps: float = 1e-6) -> np.ndarray:
    """Compute safe logit transformation with numerical clipping."""
    p_clipped = np.clip(p, eps, 1.0 - eps)
    return np.log(p_clipped / (1.0 - p_clipped))


def _sigmoid(x: np.ndarray | pd.Series) -> np.ndarray:
    """Compute standard sigmoid transformation."""
    return 1.0 / (1.0 + np.exp(-x))


def calibrate_channel_bias(
    df: pd.DataFrame,
    prob_col: str = "probability_score",
    channel_col: str = "intervention_type"
) -> pd.Series:
    """Remove each communication channel's average base-rate bias in logit space.

    Calculates:
        logit(p)
        offset = mean_logit(channel) - mean_logit(global)
        calibrated_logit = logit(p) - offset
        calibrated_probability = sigmoid(calibrated_logit)

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing predicted probabilities and intervention channels.
    prob_col : str, optional
        Column name for raw probability scores, by default "probability_score".
    channel_col : str, optional
        Column name for intervention channels, by default "intervention_type".

    Returns
    -------
    pd.Series
        Calibrated probabilities with channel base-rate bias removed.
    """
    if df is None or len(df) == 0:
        return pd.Series(dtype=float)

    raw_probs = df[prob_col].values
    logit_scores = _logit(raw_probs)
    overall_mean_logit = np.mean(logit_scores)

    calibrated_probs = raw_probs.copy()

    for channel in df[channel_col].unique():
        mask = (df[channel_col] == channel).values
        if not np.any(mask):
            continue
        channel_mean_logit = np.mean(logit_scores[mask])
        channel_offset = channel_mean_logit - overall_mean_logit
        calibrated_logits = logit_scores[mask] - channel_offset
        calibrated_probs[mask] = _sigmoid(calibrated_logits)

    return pd.Series(calibrated_probs, index=df.index, name="calibrated_probability")

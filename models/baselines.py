"""Transparent point forecasts and intervals calibrated only on available outcomes."""
from __future__ import annotations

import numpy as np
import pandas as pd


def predict(history: np.ndarray, horizon: int) -> dict[str, float]:
    """Persistence and endpoint drift over eight calendar weeks; floor counts at zero."""
    if horizon <= 0 or len(history) < 9 or not np.isfinite(history[-9:]).all():
        raise ValueError('Need a positive horizon and nine consecutive weekly observations')
    last = float(history[-1])
    slope = (last - float(history[-9])) / 8
    return {'naive': last, 'drift': max(0.0, last + horizon * slope)}


def mase_scale(history: np.ndarray) -> float | None:
    """Mean absolute adjacent-week change, using only observed training pairs."""
    changes = np.abs(np.diff(history))
    changes = changes[np.isfinite(changes)]
    if not len(changes) or changes.mean() == 0:
        return None  # Undefined scale is reported, never replaced with an epsilon.
    return float(changes.mean())


def calibration_errors(values: np.ndarray, releases: np.ndarray, cutoff: pd.Timestamp,
                       horizon: int, window: int = 52) -> dict[str, np.ndarray]:
    """Historical h-step errors whose target was published by this issue date.

    These are training residuals indexed by observation week, not scored test
    outcomes. Each prediction uses only its own nine-week history. Latest revised
    values still make the entire exercise approximate.
    """
    errors: dict[str, list[float]] = {'naive': [], 'drift': []}
    for t in range(8, len(values) - horizon):
        target = t + horizon
        if releases[target] > np.datetime64(cutoff) or not np.isfinite(values[target]):
            continue
        if not np.isfinite(values[t-8:t+1]).all():
            continue
        predictions = predict(values[:t+1], horizon)
        for model, point in predictions.items():
            errors[model].append(float(values[target] - point))
    return {model: np.asarray(e[-window:]) for model, e in errors.items()}


def interval(point: float, errors: np.ndarray, minimum: int = 8) -> tuple[float, float]:
    """Empirical 80% symmetric error band; serial dependence limits calibration."""
    if len(errors) < minimum:
        raise ValueError('Too few published calibration outcomes')
    rank = min(len(errors) - 1, int(np.ceil(0.8 * (len(errors) + 1))) - 1)
    radius = float(np.sort(np.abs(errors))[rank])
    return max(0.0, point - radius), point + radius

"""Fit-informed capacity draws; a sensitivity ensemble, not structural identification."""
from __future__ import annotations

import numpy as np

from sim.calibrate import CAPACITY_RATIO_BOUNDS
from sim.simulator import initial_state, simulate

BLOCK_WEEKS = 3
RSS_BUDGET_MULTIPLIER = 6.0


def _block_residuals(residuals: np.ndarray, count: int, rng: np.random.Generator) -> np.ndarray:
    """Circular blocks retain short-run residual dependence in the local update."""
    n = len(residuals)
    starts = rng.integers(0, n, (count, int(np.ceil(n / BLOCK_WEEKS))))
    indices = (starts[..., None] + np.arange(BLOCK_WEEKS)) % n
    return residuals[indices.reshape(count, -1)[:, :n]]


def capacity_draws(record: dict, prepared: dict, runs: int = 256,
                   seed: int = 42) -> tuple[np.ndarray, dict]:
    """Return joint capacity ratios with bounded nonlinear-fit plausibility screening.

    The local residual bootstrap informs identifiable directions. Data-poor
    directions use an explicit bounded uniform assumption rather than a zero
    variance pseudoinverse. Every retained pair is replayed through calibration.
    These draws quantify parameter sensitivity conditional on the queue structure.
    """
    if record['status'] != 'calibrated' or prepared['status'] != 'ready':
        raise ValueError('Published calibration data and a calibrated trust are required')
    if prepared['org_code'] != record['org_code'] or str(prepared['issue_date'])[:10] != str(record['issue_date'])[:10]:
        raise ValueError('Capacity draws require the same trust and issue as calibration')
    if runs < 2:
        raise ValueError('At least two capacity draws are required')
    centre = np.asarray(record['capacity_ratios'], dtype=float)
    lower, upper = CAPACITY_RATIO_BOUNDS
    y = np.asarray(prepared['observed'], dtype=float)
    valid = np.isfinite(y)
    valid[0] = False  # The initial count is imposed by construction, not fitted evidence.
    rate = float(record['arrivals_per_day'])
    conversion = float(record['conversion_proxy'])
    initial = initial_state(rate, conversion, float(y[0]), record['prior']['diagnosis_share'])
    arrivals = np.asarray(prepared['arrivals'], dtype=float)

    def replay(ratios: np.ndarray) -> np.ndarray:
        if ratios.ndim == 1:
            return simulate(initial, arrivals, rate * ratios[0],
                            rate * conversion * ratios[1], conversion)[0]['backlog_62'][valid]
        repeated = np.broadcast_to(arrivals, (len(ratios), len(arrivals)))
        return simulate(initial, repeated, rate * ratios[:, :1],
                        rate * conversion * ratios[:, 1:], conversion)[0]['backlog_62'][:, valid]

    fitted = replay(centre)
    residual = y[valid] - fitted
    centred = residual - residual.mean()
    variance = max(1.0, float(np.sum(centred ** 2) / max(1, len(residual) - 2)))
    columns = []
    for k in range(2):
        plus = centre.copy(); minus = centre.copy()
        plus[k] = min(upper, plus[k] + .002)
        minus[k] = max(lower, minus[k] - .002)
        columns.append((replay(plus) - replay(minus)) / (plus[k] - minus[k]))
    jacobian = np.column_stack(columns)
    u, singular, vt = np.linalg.svd(jacobian, full_matrices=False)
    # A direction with one-sigma uncertainty spanning half the permitted range
    # is too weak for a trustworthy local normal approximation.
    cutoff = np.sqrt(variance) * 2 / (upper - lower)
    strong = singular > max(cutoff, 1e-9)
    weak_vectors = vt[~strong]
    base_sse = float(np.sum(residual ** 2))
    extra_budget = RSS_BUDGET_MULTIPLIER * variance * BLOCK_WEEKS
    rss_limit = base_sse + extra_budget
    rng = np.random.default_rng(seed)
    accepted = []
    tried = 0
    accepted_count = 0
    for _ in range(6):
        count = max(128, runs * 2)
        resampled = _block_residuals(centred, count, rng)
        shifts = np.zeros((count, 2))
        if strong.any():
            shifts = (resampled @ u[:, strong] / singular[strong]) @ vt[strong]
        candidates = centre + shifts
        if len(weak_vectors) == 2:
            candidates = rng.uniform(lower, upper, (count, 2))
        elif len(weak_vectors) == 1:
            direction = weak_vectors[0]
            lo = np.full(count, -np.inf); hi = np.full(count, np.inf)
            for k in range(2):
                if abs(direction[k]) > 1e-10:
                    a = (lower - candidates[:, k]) / direction[k]
                    b = (upper - candidates[:, k]) / direction[k]
                    lo = np.maximum(lo, np.minimum(a, b))
                    hi = np.minimum(hi, np.maximum(a, b))
            feasible = lo <= hi
            candidates = candidates[feasible]
            amounts = rng.uniform(size=len(candidates)) * (hi[feasible] - lo[feasible]) + lo[feasible]
            candidates += amounts[:, None] * direction
        candidates = candidates[((candidates >= lower - 1e-12) & (candidates <= upper + 1e-12)).all(axis=1)]
        candidates = np.clip(candidates, lower, upper)  # Only eliminate boundary roundoff after rejection.
        if not len(candidates):
            continue
        tried += len(candidates)
        errors = replay(candidates) - y[valid]
        keep = np.sum(errors ** 2, axis=1) <= rss_limit
        accepted.extend(candidates[keep])
        accepted_count += int(keep.sum())
        if accepted_count >= runs:
            break
    fallback = len(accepted) < runs
    if not accepted:
        # An explicit unavailable uncertainty result is safer than pretending
        # duplicated point estimates quantify parameter uncertainty.
        raise ValueError('No capacity uncertainty draws passed nonlinear fit screening')
    pool = np.asarray(accepted)
    # If the likelihood support is small, report resampling; never fabricate noise.
    draws = pool[rng.choice(len(pool), size=runs, replace=fallback)]
    quantiles = np.quantile(draws, [.1, .5, .9], axis=0)
    metadata = dict(
        method='Linearized circular residual-block bootstrap with bounded weak-direction variation and nonlinear calibration-fit screening',
        parameter_order=['diagnosis_capacity_ratio', 'treatment_capacity_ratio'],
        bounds=[lower, upper], block_weeks=BLOCK_WEEKS, seed=seed,
        draws=runs, effective_rank=int(strong.sum()), weakly_identified=bool((~strong).any()),
        jacobian_singular_values=singular.tolist(), residual_variance=variance,
        variance_floor_patients_squared=1.0, base_residual_sse=base_sse,
        accepted_sse_limit=rss_limit, rss_budget_multiplier=RSS_BUDGET_MULTIPLIER,
        candidates_evaluated=tried, candidates_accepted=accepted_count,
        sampling_with_replacement=fallback,
        capacity_ratio_lower_80=quantiles[0].tolist(),
        capacity_ratio_median=quantiles[1].tolist(),
        capacity_ratio_upper_80=quantiles[2].tolist(),
        assumption='Uniform variation along weak directions within original 0.4–1.8 bounds; allow 6 × residual variance × 3 weeks additional calibration SSE.',
        caveat='Approximate parameter-sensitivity ensemble, not a confidence region or identified structural uncertainty. Conversion, queue split, age shape and service order remain assumed.')
    return draws, metadata

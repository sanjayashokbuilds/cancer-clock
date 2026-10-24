"""Daily age-cohort fluid queues with stochastic arrivals and service variation."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

AGE_MAX = 365  # Final bucket is 365+ days, retained rather than discarded.
DIAGNOSIS_MIN_DAYS = 14


@dataclass
class State:
    """Fractional patient masses by total days since referral; DTT never resets age."""
    diagnosis: np.ndarray
    treatment: np.ndarray

    def copy(self) -> 'State':
        return State(self.diagnosis.copy(), self.treatment.copy())


def _initial_stage(rate: float, overdue: float, first_age: int, include_early: bool) -> np.ndarray:
    """Assumed exponential age mix matching the observed/prior overdue mass exactly."""
    ages = np.arange(AGE_MAX + 1)
    result = np.zeros(AGE_MAX + 1)
    if include_early:
        result[:first_age] = rate
    if overdue <= 0 or rate <= 0:
        return result
    def profile(mean: float) -> np.ndarray:
        # The last bucket contains the entire exponential tail beyond 365 days.
        weights = np.exp(-np.maximum(0, ages - first_age) / mean) * rate
        weights[ages < first_age] = 0.
        weights[-1] /= -np.expm1(-1 / mean)
        return weights
    mean = brentq(lambda value: profile(value)[63:].sum() - overdue, .01, 100000.)
    result += profile(mean)
    return result


def initial_state(arrivals_per_day: float, conversion: float, backlog: float,
                  diagnosis_share: float) -> State:
    """Reconstruct an explicit assumed age mix; only the total >62 count is observed."""
    if arrivals_per_day <= 0 or not 0 <= conversion <= 1 or backlog < 0 or not 0 <= diagnosis_share <= 1:
        raise ValueError('Invalid initial flow, conversion, backlog or split')
    share = diagnosis_share if conversion > 0 else 1.
    return State(_initial_stage(arrivals_per_day, backlog * share, DIAGNOSIS_MIN_DAYS, True),
                 _initial_stage(arrivals_per_day * conversion, backlog * (1 - share), DIAGNOSIS_MIN_DAYS + 1, False))


def age_one_day(queue: np.ndarray) -> np.ndarray:
    """Advance integer day buckets and preserve all mass in the open-ended tail."""
    aged = np.zeros_like(queue)
    aged[..., 1:] = queue[..., :-1]
    aged[..., -1] += queue[..., -1]
    return aged


def serve(queue: np.ndarray, capacity: np.ndarray | float, minimum_age: int = 0) -> np.ndarray:
    """Allocate at most the daily service budget proportionally among eligible ages."""
    eligible = queue[..., minimum_age:]
    total = eligible.sum(axis=-1)
    ratio = np.divide(np.asarray(capacity, dtype=float), total, out=np.zeros_like(total), where=total > 0)
    ratio = np.clip(ratio, 0., 1.)
    served = np.zeros_like(queue)
    served[..., minimum_age:] = eligible * np.expand_dims(ratio, -1)
    return served


def step(state: State, arrivals: np.ndarray | float, diagnosis_capacity: np.ndarray | float,
         treatment_capacity: np.ndarray | float, conversion: float) -> tuple[State, dict]:
    """One day: age, arrive, treat existing T, diagnose D, then transfer without reset."""
    if not 0 <= conversion <= 1 or np.any(np.asarray(arrivals) < 0) or np.any(np.asarray(diagnosis_capacity) < 0) or np.any(np.asarray(treatment_capacity) < 0):
        raise ValueError('Flows and capacities must be nonnegative; conversion in [0,1]')
    d = age_one_day(state.diagnosis); t = age_one_day(state.treatment)
    d[..., 0] += arrivals
    treated = serve(t, treatment_capacity)
    diagnosed = serve(d, diagnosis_capacity, DIAGNOSIS_MIN_DAYS)
    d -= diagnosed
    t = t - treated + conversion * diagnosed
    return State(d, t), dict(arrivals=np.asarray(arrivals), diagnosed=diagnosed.sum(axis=-1),
        treated=treated.sum(axis=-1), discharged_without_treatment=(1 - conversion) * diagnosed.sum(axis=-1))


def measures(state: State) -> dict[str, np.ndarray]:
    """Strict >62 and >104 thresholds; age 62/104 is not counted in its next group."""
    d, t = state.diagnosis, state.treatment
    return dict(backlog_62=(d[..., 63:] + t[..., 63:]).sum(axis=-1),
        long_wait_104=(d[..., 105:] + t[..., 105:]).sum(axis=-1),
        diagnosis_backlog_62=d[..., 63:].sum(axis=-1), treatment_backlog_62=t[..., 63:].sum(axis=-1),
        total_waiting=(d + t).sum(axis=-1))


def simulate(initial: State, arrivals: np.ndarray, diagnosis_capacity: np.ndarray | float,
             treatment_capacity: np.ndarray | float, conversion: float, *, sample_every: int = 7) -> tuple[dict, State]:
    """Run deterministic or vectorised Monte Carlo draws, retaining day-zero state."""
    arrivals = np.asarray(arrivals, dtype=float)
    if arrivals.ndim not in (1, 2):
        raise ValueError('Arrivals must be days or draws × days')
    days = arrivals.shape[-1]
    expected_shape = arrivals.shape[:-1]
    state = initial.copy()
    if state.diagnosis.shape[:-1] != expected_shape:
        state = State(np.broadcast_to(state.diagnosis, (*expected_shape, AGE_MAX + 1)).copy(),
                      np.broadcast_to(state.treatment, (*expected_shape, AGE_MAX + 1)).copy())
    dc = np.broadcast_to(diagnosis_capacity, arrivals.shape)
    tc = np.broadcast_to(treatment_capacity, arrivals.shape)
    recorded = {key: [value.copy()] for key, value in measures(state).items()}
    offsets = [0]
    for day in range(days):
        state, _ = step(state, arrivals[..., day], dc[..., day], tc[..., day], conversion)
        if (day + 1) % sample_every == 0 or day + 1 == days:
            offsets.append(day + 1)
            for key, value in measures(state).items():
                recorded[key].append(value.copy())
    return dict(days=np.array(offsets), **{key: np.stack(values, axis=-1) for key, values in recorded.items()}), state

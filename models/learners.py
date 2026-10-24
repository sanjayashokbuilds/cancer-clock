"""Fixed, small model specifications; fitting uses published training outcomes only."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

PARAMS=dict(learning_rate=0.04, num_leaves=15, min_data_in_leaf=100,
            lambda_l2=10.0, max_bin=63, num_threads=2, verbosity=-1,
            seed=42, deterministic=True, force_col_wise=True)
ROUNDS=100
REVERSION_TERMS=['reversion_weight','season_sin','season_cos','christmas','national_trend']


def reversion_design(rows: pd.DataFrame, context: bool) -> np.ndarray:
    """Normalised changes preserve an interpretable convex reversion coefficient."""
    values=[((rows.rolling_mean26-rows.last_value)/(1+rows.last_value)).to_numpy()]
    if context:
        values.extend(rows[c].fillna(0).to_numpy() for c in ['season_sin_change','season_cos_change','christmas_change'])
        values.append((rows.national_change8.fillna(0)*rows.observation_horizon_weeks/8).to_numpy())
    return np.column_stack(values)


def fit_reversion(train: pd.DataFrame, context: bool) -> np.ndarray:
    """Fit one bounded weight per horizon globally, with regularised context terms.

    Six deterministic IRLS steps approximate a patient-count absolute-error loss.
    No coefficients, penalties or rounds are selected on scored test outcomes.
    """
    x=reversion_design(train,context)
    y=((train.actual-train.last_value)/(1+train.last_value)).to_numpy()
    width=x.shape[1]; prior=np.zeros(width); prior[0]=0.25
    coef=prior.copy()
    count_weight=(1+train.last_value.to_numpy())
    count_weight=count_weight/count_weight.mean()
    penalty=len(train)*0.05
    lower=np.array([0.]+[-0.3]*3+[-1.])[:width]
    upper=np.array([1.]+[0.3]*3+[1.])[:width]
    for _ in range(6):
        weight=np.sqrt(count_weight/np.maximum(np.abs(y-x@coef),0.05))
        fit=lsq_linear(np.vstack([x*weight[:,None],np.eye(width)*np.sqrt(penalty)]),
                       np.r_[y*weight,prior*np.sqrt(penalty)],bounds=(lower,upper),tol=1e-8)
        if not fit.success: raise RuntimeError('Reversion fit failed: '+fit.message)
        coef=fit.x
    return coef


def predict_reversion(rows: pd.DataFrame, coef: np.ndarray, context: bool) -> np.ndarray:
    """Return nonnegative counts; without context this is partial mean reversion."""
    return np.maximum(0,rows.last_value.to_numpy()+(1+rows.last_value.to_numpy())*(reversion_design(rows,context)@coef))


def train_boosters(train: pd.DataFrame, features: list[str]) -> tuple[list,object]:
    """Global quantiles of log((target+1)/(latest+1)) and separate growth probability."""
    try:
        import lightgbm as lgb
    except OSError as exc:
        raise RuntimeError('LightGBM cannot load its native library. On macOS install OpenMP with: brew install libomp') from exc
    x=train[features].to_numpy(dtype=float)
    # Count weighting offsets relative-error emphasis; the cap uses training data only.
    weights=np.sqrt(1+train.last_value.to_numpy())
    weights=np.minimum(weights,np.quantile(weights,0.95));weights/=weights.mean()
    quantiles=[]
    for q in (0.1,0.5,0.9):
        dataset=lgb.Dataset(x,label=train.log_ratio.to_numpy(),weight=weights,feature_name=features)
        quantiles.append(lgb.train({**PARAMS,'objective':'quantile','alpha':q},dataset,num_boost_round=ROUNDS))
    dataset=lgb.Dataset(x,label=train.growth.to_numpy(),feature_name=features)
    classifier=lgb.train({**PARAMS,'objective':'binary'},dataset,num_boost_round=ROUNDS)
    return quantiles,classifier


def predict_boosters(rows: pd.DataFrame, features: list[str], quantiles: list, classifier: object) -> tuple[np.ndarray,np.ndarray]:
    """Sort crossing quantiles; expm1 inversion handles zero backlogs exactly."""
    x=rows[features].to_numpy(dtype=float)
    raw=np.column_stack([booster.predict(x,num_threads=2) for booster in quantiles])
    # Numerical guard only, not a fitted cap on counts.
    counts=np.maximum(0,np.expm1(np.clip(np.log1p(rows.last_value.to_numpy())[:,None]+raw,-30,30)))
    return np.sort(counts,axis=1),np.asarray(classifier.predict(x,num_threads=2))

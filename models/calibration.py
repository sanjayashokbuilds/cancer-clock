"""Prequential uncertainty and probability calibration, with explicit warm-up rules."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit,logit


def past_errors(predictions: pd.DataFrame, issue: pd.Timestamp, horizon: int, model: str) -> pd.DataFrame:
    """Only older issued predictions with now-published actuals may calibrate."""
    if predictions.empty: return predictions
    return predictions.loc[predictions.horizon_weeks.eq(horizon) & predictions.model.eq(model)
        & predictions.as_of_date.lt(issue) & predictions.target_published_on.le(issue)
        & predictions.actual.notna()].copy()


def quantile80(values: np.ndarray) -> float:
    """Finite-sample higher empirical 80th percentile; dependence is not corrected."""
    rank=min(len(values)-1,int(np.ceil(0.8*(len(values)+1)))-1)
    return float(np.sort(values)[rank])


def calibrate_bands(point: np.ndarray, raw_low: np.ndarray, raw_high: np.ndarray,
                    last: np.ndarray, previous: pd.DataFrame, baseline_radius: np.ndarray,
                    model: str) -> tuple[np.ndarray,np.ndarray,str]:
    """Past out-of-sample errors calibrate bands; early cases use baseline widths."""
    if len(previous)<200:
        low=np.minimum(raw_low,point-baseline_radius)
        high=np.maximum(raw_high,point+baseline_radius)
        return np.maximum(0,low),high,'baseline_width_warmup'
    if model=='lightgbm':
        residual=np.maximum.reduce([previous.raw_lower.to_numpy()-previous.actual.to_numpy(),
                   previous.actual.to_numpy()-previous.raw_upper.to_numpy(),np.zeros(len(previous))])/(1+previous.last_value.to_numpy())
        radius=quantile80(residual)*(1+last)
        return np.maximum(0,raw_low-radius),raw_high+radius,'past_issued_quantile_errors'
    residual=np.abs(previous.actual.to_numpy()-previous.prediction.to_numpy())/(1+previous.last_value.to_numpy())
    radius=quantile80(residual)*(1+last)
    return np.maximum(0,point-radius),point+radius,'past_issued_point_errors'


def calibrate_probabilities(raw: np.ndarray, previous: pd.DataFrame) -> tuple[np.ndarray,dict]:
    """Regularised Platt calibration trained on previously issued probabilities."""
    if len(previous)<200 or previous.growth.nunique()<2:
        return raw,{'status':'raw_warmup','n':len(previous),'intercept':0.,'slope':1.}
    x=logit(np.clip(previous.prob_growth_raw.to_numpy(),1e-6,1-1e-6))
    y=previous.growth.to_numpy()
    def objective(beta: np.ndarray) -> tuple[float,np.ndarray]:
        z=beta[0]+beta[1]*x
        penalty=0.01*(beta[0]**2+(beta[1]-1)**2)
        loss=float(np.mean(np.logaddexp(0,z)-y*z)+penalty)
        diff=expit(z)-y
        grad=np.array([diff.mean()+0.02*beta[0],(diff*x).mean()+0.02*(beta[1]-1)])
        return loss,grad
    fit=minimize(objective,np.array([0.,1.]),jac=True,bounds=[(-5,5),(0,5)],method='L-BFGS-B')
    if not fit.success: raise RuntimeError('Probability calibration failed: '+fit.message)
    calibrated=expit(fit.x[0]+fit.x[1]*logit(np.clip(raw,1e-6,1-1e-6)))
    return calibrated,{'status':'past_issued_platt','n':len(previous),'intercept':float(fit.x[0]),'slope':float(fit.x[1])}


def probability_metrics(rows: pd.DataFrame, column: str) -> dict:
    """Brier, discrimination and fixed-width reliability bins; ties are non-growth."""
    y=rows.growth.to_numpy();p=rows[column].to_numpy()
    bins=[]
    for k in range(10):
        chosen=(p>=k/10)&((p<(k+1)/10) if k<9 else (p<=1))
        if chosen.any():
            bins.append(dict(lower=k/10,upper=(k+1)/10,n=int(chosen.sum()),
                             mean_probability=float(p[chosen].mean()),observed_growth_rate=float(y[chosen].mean())))
    non_ties=rows.actual.ne(rows.last_value).to_numpy()
    return dict(n=len(rows),brier=float(np.mean((p-y)**2)),accuracy=float(np.mean((p>=0.5)==y)),
                grow_shrink_accuracy=float(np.mean((p[non_ties]>=0.5)==y[non_ties])) if non_ties.any() else None,
                unchanged_n=int((~non_ties).sum()),growth_rate=float(y.mean()),
                ece_10bin=float(sum(b['n']*abs(b['mean_probability']-b['observed_growth_rate']) for b in bins)/len(rows)),
                calibration_curve=bins)

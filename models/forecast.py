"""Stage 3: paired issue-anchor model evaluation, classifier and latest forecasts."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from config import FORECAST_HORIZONS_WEEKS, OUTPUTS_DIR, PROCESSED_DIR, STATIC_DIR
from models.backtest import LABEL, score
from models.baselines import calibration_errors, interval, mase_scale, predict
from models.calibration import calibrate_bands, calibrate_probabilities, past_errors, probability_metrics
from models.features import build_panel, load_sources, training_rows
from models.learners import PARAMS, ROUNDS, REVERSION_TERMS, fit_reversion, predict_reversion, train_boosters, predict_boosters
from pipeline.common import DataError
from pipeline.universe import load_core_trusts
from pipeline.vintages import available_at

KEY=['org_code','as_of_date','horizon_weeks']
CANDIDATES=('reversion','reversion_context','lightgbm')


def jsonable(value: object) -> object:
    """Convert pandas/numpy scalars and unknown outcomes to strict JSON values."""
    if isinstance(value,dict): return {str(k):jsonable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [jsonable(v) for v in value]
    if isinstance(value,(pd.Timestamp,np.datetime64)): return str(pd.Timestamp(value).date())
    if isinstance(value,(np.integer,)): return int(value)
    if isinstance(value,(np.bool_,)): return bool(value)
    if isinstance(value,(np.floating,float)): return float(value) if np.isfinite(value) else None
    if value is pd.NA or value is pd.NaT: return None
    return value


def write_json(path: Path, data: dict) -> None:
    """Atomic writes avoid presenting interrupted output as a complete result."""
    temp=path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(jsonable(data),indent=2,allow_nan=False)+'\n')
    temp.replace(path)


def paired_cases(baseline: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Require exact Stage 2 issue cases; never silently drop difficult cases."""
    cases=baseline.loc[baseline.anchor.eq('issue') & baseline.model.eq('naive')].copy()
    features=panel.set_index(KEY)
    expected=pd.MultiIndex.from_frame(cases[KEY])
    if not expected.isin(features.index).all(): raise DataError('Stage 2 cases missing from feature panel')
    selected=features.loc[expected].reset_index()
    if not selected.feature_eligible.all(): raise DataError('An approved baseline case lacks eligible features')
    if not np.allclose(selected.actual,cases.actual): raise DataError('Labels differ from saved Stage 2 snapshot')
    return cases


def fit_issue(train: pd.DataFrame, rows: pd.DataFrame, features: list[str], previous: pd.DataFrame,
              baseline: pd.DataFrame, issue: pd.Timestamp, horizon: int) -> tuple[pd.DataFrame,dict]:
    """Fit all candidates once per issue/horizon and calibrate from past issued errors."""
    if len(train)<100 or train.as_of_date.nunique()<2:
        raise DataError(f'Insufficient published training outcomes at {issue.date()}/{horizon}w')
    if train.target_published_on.max()>issue or train.feature_max_published_on.gt(train.as_of_date).any():
        raise DataError('Future information in training')
    base=baseline.set_index('org_code').loc[rows.org_code].reset_index()
    if not np.allclose(base.last_value,rows.last_value): raise DataError('Feature/base alignment failed')
    radius=base.upper_80.to_numpy()-base.last_value.to_numpy()
    quantiles,classifier=train_boosters(train,features)
    counts,prob_raw=predict_boosters(rows,features,quantiles,classifier)
    old=past_errors(previous,issue,horizon,'lightgbm')
    prob,calibrator=calibrate_probabilities(prob_raw,old)
    frequency=float(train.growth.mean())
    audit=dict(as_of_date=issue,horizon_weeks=horizon,training_n=len(train),
               training_first_issue=train.as_of_date.min(),training_last_issue=train.as_of_date.max(),
               training_max_target_published_on=train.target_published_on.max(),
               probability_calibrator=calibrator,coefficients={})
    records=[]
    for model in CANDIDATES:
        if model=='lightgbm':
            raw_low,point,raw_high=counts[:,0],counts[:,1],counts[:,2]
        else:
            coef=fit_reversion(train,context=model=='reversion_context')
            audit['coefficients'][model]=dict(zip(REVERSION_TERMS,coef.tolist()))
            point=predict_reversion(rows,coef,context=model=='reversion_context')
            raw_low=point.copy();raw_high=point.copy()
        past=past_errors(previous,issue,horizon,model)
        low,high,status=calibrate_bands(point,raw_low,raw_high,rows.last_value.to_numpy(),past,radius,model)
        for i,row in enumerate(rows.itertuples(index=False)):
            actual=float(row.actual) if pd.notna(row.actual) else np.nan
            scale=base.training_scale.iloc[i]
            error=abs(actual-point[i])
            records.append(dict(org_code=row.org_code,as_of_date=issue,horizon_weeks=horizon,
                anchor='issue',model=model,target_date=row.target_date,
                target_published_on=row.target_published_on,latest_observation=row.latest_observation,
                feature_max_published_on=row.feature_max_published_on,
                issue_lead_weeks=horizon,observation_horizon_weeks=row.observation_horizon_weeks,
                publication_lag_weeks=row.lag_weeks,target_is_future=True,last_value=row.last_value,
                prediction=float(point[i]),lower_80=float(low[i]),upper_80=float(high[i]),
                raw_lower=float(raw_low[i]),raw_upper=float(raw_high[i]),interval_method=status,
                calibration_n=len(past),training_n=len(train),training_scale=scale,
                training_max_target_published_on=train.target_published_on.max(),
                calibration_max_target_published_on=past.target_published_on.max() if len(past) else pd.NaT,
                actual=actual,absolute_error=error,scaled_error=error/scale if pd.notna(scale) and scale>0 else np.nan,
                growth=float(actual>row.last_value) if np.isfinite(actual) else np.nan,
                prob_growth_raw=float(prob_raw[i]),prob_growth=float(prob[i]),prob_growth_frequency=frequency,
                prob_growth_coin=0.5,prob_growth_persistence=0.,
                direction_correct=bool(np.sign(point[i]-row.last_value)==np.sign(actual-row.last_value)),
                covered_80=bool(low[i]<=actual<=high[i]),availability_label=LABEL,historical_vintage_verified=False))
    return pd.DataFrame(records),audit


def comparison(baselines: pd.DataFrame, predictions: pd.DataFrame) -> list[dict]:
    """All five models share the exact same scored cases at each issue horizon."""
    result=[]
    for horizon in FORECAST_HORIZONS_WEEKS:
        base=baselines.loc[baselines.anchor.eq('issue') & baselines.horizon_weeks.eq(horizon)]
        expected=set(map(tuple,base.loc[base.model.eq('naive'),KEY].to_numpy()))
        joined=pd.concat([base,predictions.loc[predictions.horizon_weeks.eq(horizon)]],ignore_index=True)
        for model,group in joined.groupby('model',sort=True):
            if set(map(tuple,group[KEY].to_numpy()))!=expected or len(group)!=len(expected):
                raise DataError(f'Unpaired cases for {model}/{horizon}w')
            result.append(dict(model=model,horizon_weeks=horizon,**score(group)))
    return result


def choose_model(metrics: list[dict]) -> tuple[str,dict]:
    """Predeclared gate: beat both baselines on MAE and MASE at issue +8 and +12."""
    lookup={(m['model'],m['horizon_weeks']):m for m in metrics}
    gates={}
    for model in CANDIDATES:
        gates[model]=all(lookup[model,h][metric]<lookup[baseline,h][metric]
                        for h in (8,12) for metric in ('mae','mase') for baseline in ('naive','drift'))
    accepted=[m for m in CANDIDATES if gates[m]]
    selected=min(accepted,key=lambda m:sum(lookup[m,h]['mase'] for h in (8,12))) if accepted else 'naive'
    return selected,dict(candidate_pass=gates,selected=selected,
            status='GO_EXPLORATORY' if accepted else 'NO_GO_COUNTS_USE_PERSISTENCE',
            rule='Beat both baselines on paired issue-anchor MAE and MASE at 8 AND 12 weeks.',
            caveat='Selection uses this retrospective comparison; it is not independent confirmation or a clinical deployment approval.')


def latest_baselines(sources: dict, panel: pd.DataFrame, issue: pd.Timestamp) -> pd.DataFrame:
    """Compute persistence bands and scales for the latest issue without target labels."""
    rows=[]
    for code,raw in sources['backlog_trust'].groupby('org_code'):
        known=available_at(raw,issue,allow_approximate=True).sort_values('week_ending')
        if known.empty: continue
        vals=known.backlog.to_numpy(dtype=float)
        if len(vals)<26 or not np.isfinite(vals[-9:]).all(): continue
        for h in FORECAST_HORIZONS_WEEKS:
            steps=int((issue-known.week_ending.max()).days//7+h)
            errors=calibration_errors(vals,known.published_on.to_numpy(),issue,steps)['naive']
            if len(errors)<8: continue
            point=predict(vals,steps)['naive'];low,high=interval(point,errors)
            rows.append(dict(org_code=code,as_of_date=issue,horizon_weeks=h,model='naive',
                last_value=point,prediction=point,lower_80=low,upper_80=high,training_scale=mase_scale(vals)))
    return pd.DataFrame(rows)


def plot_calibration(report: dict, path: Path) -> None:
    """Reliability curves are measured on scored issue cases, with bin sizes in JSON."""
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(12,4),sharex=True,sharey=True)
    for ax,h in zip(axes,FORECAST_HORIZONS_WEEKS):
        ax.plot([0,1],[0,1],color='gray',linestyle='--',linewidth=1)
        for name,color in [('raw','#a8b6c3'),('calibrated','#126c8c')]:
            item=next(x for x in report['metrics'] if x['horizon_weeks']==h and x['model']==name)
            points=item['calibration_curve']
            ax.plot([p['mean_probability'] for p in points],[p['observed_growth_rate'] for p in points],marker='o',label=name,color=color)
        ax.set(title=f'{h} weeks from issue',xlabel='Predicted growth probability',xlim=(0,1),ylim=(0,1));ax.grid(alpha=.2)
    axes[0].set_ylabel('Observed growth frequency');axes[-1].legend()
    fig.suptitle('Growth classifier | approximate: latest revised values',fontsize=12)
    fig.tight_layout();fig.savefig(path,dpi=150);plt.close(fig)


def classifier_summary(report: dict) -> dict:
    """Derive claims from scores; do not hard-code conclusions for future data."""
    summary={}
    for h in FORECAST_HORIZONS_WEEKS:
        scores={m['model']:m['brier'] for m in report['metrics'] if m['horizon_weeks']==h}
        summary[str(h)]=dict(calibration_improved_brier=scores['calibrated']<scores['raw'],
            beats_coin=scores['calibrated']<scores['coin'],
            beats_historical_frequency=scores['calibrated']<scores['historical_frequency'])
    return summary


def probability_status(report: dict, horizon: int) -> str:
    """Mark probability outputs experimental and disclose failed Brier benchmarks."""
    result=classifier_summary(report)[str(horizon)]
    if not result['beats_coin'] or not result['beats_historical_frequency']:
        return 'experimental: fails at least one Brier benchmark at this horizon'
    return 'experimental: retrospective Brier benchmarks passed; future validation still required'


def export_latest(sources: dict, core: pd.DataFrame, panel: pd.DataFrame, features: list[str],
                  predictions: pd.DataFrame, selected: str, latest_issue: pd.Timestamp,
                  gate: dict, classifier_report: dict, national_display: dict | None = None) -> None:
    """Refit and export one explicit source-supported issue with all core statuses."""
    from models.review import BLEND_WEIGHT, direction_signal
    # Refit only once at the latest source-supported issue and export all core statuses.
    base=latest_baselines(sources,panel,latest_issue);latest_parts=[]
    for h in FORECAST_HORIZONS_WEEKS:
        b=base.loc[base.horizon_weeks.eq(h)&base.org_code.isin(core.org_code)]
        rows=panel.set_index(KEY).loc[pd.MultiIndex.from_frame(b[KEY])].reset_index()
        result,audit=fit_issue(training_rows(panel,latest_issue,h),rows,features,predictions,b,latest_issue,h)
        latest_parts.append(result)
    latest=pd.concat(latest_parts,ignore_index=True)
    trusts=[]
    for trust in core.itertuples():
        history=available_at(sources['backlog_trust'],latest_issue,allow_approximate=True)
        history=history.loc[history.org_code.eq(trust.org_code)].sort_values('week_ending').tail(52)
        entry=dict(org_code=trust.org_code,name=trust.name,history=history[['week_ending','backlog','published_on']].to_dict('records'),forecasts=[])
        for h in FORECAST_HORIZONS_WEEKS:
            r=latest.loc[latest.org_code.eq(trust.org_code)&latest.horizon_weeks.eq(h)]
            if r.empty: continue
            raw_model='lightgbm' if selected=='lightgbm_blend' else selected
            row=r.loc[r.model.eq(raw_model)].iloc[0] if selected!='naive' else r.iloc[0]
            point,lo,hi=row.prediction,row.lower_80,row.upper_80
            b=base.loc[base.org_code.eq(trust.org_code)&base.horizon_weeks.eq(h)].iloc[0]
            if selected=='naive':
                point,lo,hi=b.prediction,b.lower_80,b.upper_80
            if selected=='lightgbm_blend':
                point=BLEND_WEIGHT*point+(1-BLEND_WEIGHT)*b.prediction
                lo=BLEND_WEIGHT*lo+(1-BLEND_WEIGHT)*b.lower_80
                hi=BLEND_WEIGHT*hi+(1-BLEND_WEIGHT)*b.upper_80
            forecast=dict(horizon_weeks=h,issue_date=latest_issue,target_date=row.target_date,
                latest_observation=row.latest_observation,point_forecast=point,lower_80=lo,upper_80=hi,model=selected,
                last_value=row.last_value,
                training_n=row.training_n,training_max_target_published_on=row.training_max_target_published_on,
                interpretation='Hospital overdue backlog, not a personal waiting-time prediction.')
            if h==4:
                forecast['growth_signal']=direction_signal(row.prob_growth_raw,row.last_value,point)
                forecast['growth_signal_status']='experimental category; thresholds 0.4/0.6 and point-direction agreement'
            entry['forecasts'].append(forecast)
        entry['status']='forecast_available' if entry['forecasts'] else 'unavailable_missing_recent_history'
        trusts.append(entry)
    write_json(OUTPUTS_DIR/'forecasts_latest.json',dict(stage=4,issue_date=latest_issue,availability_label=LABEL,
        historical_vintage_verified=False,selected_model=selected,gate=gate,
        growth_display=classifier_report.get('display_policy'),
        national_model_forecasts=national_display or dict(enabled=False,reason='No national model forecasts exported.'),
        forecast_trusts=sum(t['status']=='forecast_available' for t in trusts),trusts=trusts))


def run() -> dict:
    """Full reproducible Stage 3 build, offline after dependencies are installed."""
    started=time.monotonic();sources=load_sources();core=load_core_trusts()
    baseline_path=OUTPUTS_DIR/'backtest_baseline_predictions.parquet'
    baselines=pd.read_parquet(baseline_path)
    origins=pd.DatetimeIndex(sorted(baselines.as_of_date.unique()))
    # A Sunday issue keeps exact 4/8/12-week targets aligned to observed weekly counts.
    last_release=sources['backlog_trust'].published_on.max()
    latest_issue=last_release+pd.Timedelta(days=(6-last_release.dayofweek)%7)
    issues=pd.date_range('2023-07-02',latest_issue,freq='7D')
    print('Building published-only feature snapshots...',flush=True)
    panel,features=build_panel(sources,issues)
    cases=paired_cases(baselines,panel)
    predictions=pd.DataFrame();fit_log=[]
    for issue in origins:
        for h in FORECAST_HORIZONS_WEEKS:
            base=cases.loc[cases.as_of_date.eq(issue)&cases.horizon_weeks.eq(h)]
            if base.empty: continue
            rows=panel.set_index(KEY).loc[pd.MultiIndex.from_frame(base[KEY])].reset_index()
            train=training_rows(panel,issue,h)
            result,audit=fit_issue(train,rows,features,predictions,base,issue,h)
            predictions=result if predictions.empty else pd.concat([predictions,result],ignore_index=True)
            fit_log.append(audit)
        print(f'Finished issue {issue.date()} ({time.monotonic()-started:.0f}s)',flush=True)
    metrics=comparison(baselines,predictions);selected,gate=choose_model(metrics)
    probability=predictions.loc[predictions.model.eq('lightgbm')]
    classifier_report=dict(availability_label=LABEL,event='target backlog > latest published backlog; ties are non-growth',
        evaluation_anchor='issue',calibration='Regularised Platt fit on earlier issued predictions whose targets are now published; raw probabilities during warm-up.',metrics=[])
    for h in FORECAST_HORIZONS_WEEKS:
        r=probability.loc[probability.horizon_weeks.eq(h)]
        for model,column in [('raw','prob_growth_raw'),('calibrated','prob_growth'),('historical_frequency','prob_growth_frequency'),('coin','prob_growth_coin'),('persistence_zero','prob_growth_persistence')]:
            classifier_report['metrics'].append(dict(model=model,horizon_weeks=h,**probability_metrics(r,column)))
    classifier_report['interpretation']=classifier_summary(classifier_report)
    report=dict(stage=3,availability_label=LABEL,historical_vintage_verified=False,evaluation_anchor='issue',
        core_trusts=len(core),origins=len(origins),features=features,metrics=metrics,gate=gate,
        target='log1p(target backlog) - log1p(latest published backlog)',
        fixed_lightgbm_parameters={**PARAMS,'num_boost_round':ROUNDS},
        protocol='Fixed model settings. Weekly training snapshots; label release <= issue. Exact saved Stage 2 issue cases. No retuning on reported outcomes.',
        limitations=['Approximate first releases and latest revised values; not reconstructed historical vintages.',
                     'Overlapping targets/trust outcomes are dependent; no significance claim.',
                     'Global reversion coefficients are predictive associations, not causal effects.',
                     'Model selection on this retrospective comparison needs independent future validation.'],
        input_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [*(PROCESSED_DIR/f'{name}.parquet' for name in sources),STATIC_DIR/'core_trusts.csv',STATIC_DIR/'strike_dates.csv']},
        baseline_sha256=hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
        versions={p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','lightgbm']},fit_audit=fit_log)
    predictions.to_parquet(OUTPUTS_DIR/'backtest_model_predictions.parquet',index=False)
    panel.to_parquet(OUTPUTS_DIR/'model_features.parquet',index=False)
    write_json(OUTPUTS_DIR/'backtest_model.json',report)
    write_json(OUTPUTS_DIR/'backtest_classifier.json',classifier_report)
    plot_calibration(classifier_report,OUTPUTS_DIR.parent/'docs'/'fig_growth_calibration.png')
    from models.review import run as review_run
    review=review_run()
    report['review']=review
    print('\nISSUE-ANCHORED, EXACT PAIRED CASES')
    print('Horizon Model                  N     MAE    MASE  Direction Coverage80')
    for m in metrics:
        print(f'{m["horizon_weeks"]:>3}w    {m["model"]:20} {m["n"]:5} {m["mae"]:7.2f} {m["mase"]:7.3f} {m["direction_accuracy"]:8.1%} {m["coverage_80"]:9.1%}')
    print('Original Stage 3 gate:',gate['status'],'| original selection:',selected)
    print('Reviewed trust forecasts:',review['selected_trust_model'])
    for m in classifier_report['metrics']:
        if m['model'] in {'calibrated','historical_frequency'}:
            print(f'Growth {m["horizon_weeks"]:2}w {m["model"]:20} Brier={m["brier"]:.4f}, accuracy={m["accuracy"]:.1%}')
    print(f'Stage 3 complete in {time.monotonic()-started:.0f}s. '+LABEL)
    return report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()

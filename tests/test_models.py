"""Stage 3 leakage, pairing, calibration and forecast-contract regression tests."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from config import OUTPUTS_DIR
from models.calibration import calibrate_bands, calibrate_probabilities, past_errors, probability_metrics
from models.features import META, build_panel, load_sources, training_rows
from models.forecast import KEY, paired_cases, comparison, choose_model
from models.learners import fit_reversion, predict_reversion, train_boosters, predict_boosters


def test_unpublished_features_and_training_labels_are_inaccessible() -> None:
    """Poison every unpublished source value, including past-but-unreleased targets."""
    sources=load_sources();issue=pd.Timestamp('2024-06-16')
    dates=pd.date_range('2023-08-20',issue,freq='28D')
    before,features=build_panel(sources,dates,{'RTH','RRK'})
    changed={k:v.copy() for k,v in sources.items()}
    for name,frame in changed.items():
        future=frame.published_on.gt(issue)
        for col in frame.select_dtypes(include='number').columns:
            frame.loc[future,col]=frame.loc[future,col]+10000
    after,features2=build_panel(changed,dates,{'RTH','RRK'})
    assert features==features2
    pd.testing.assert_frame_equal(before[features],after[features])
    for h in (4,8,12):
        a=training_rows(before,issue,h);b=training_rows(after,issue,h)
        pd.testing.assert_frame_equal(a,b)
        assert a.target_published_on.le(issue).all()
    assert (before.target_date.lt(issue)&before.target_published_on.gt(issue)).any()
    assert not set(features)&META


def reversion_fixture() -> pd.DataFrame:
    """Known half-reversion generating process for an analytical fit check."""
    rng=np.random.default_rng(42);last=rng.uniform(10,400,500)
    mean=rng.uniform(10,400,500)
    return pd.DataFrame(dict(last_value=last,rolling_mean26=mean,actual=last+.5*(mean-last),
        season_sin_change=0.,season_cos_change=0.,christmas_change=0.,national_change8=0.,
        observation_horizon_weeks=16.))


def test_reversion_fit_is_bounded_and_interpretable() -> None:
    rows=reversion_fixture()
    for context in (False,True):
        coef=fit_reversion(rows,context)
        assert 0<=coef[0]<=1
        assert abs(coef[0]-.5)<.03
        point=predict_reversion(rows,coef,context)
        assert np.isfinite(point).all() and (point>=0).all()
        assert np.mean(abs(point-rows.actual))<3
    zeros=rows.copy();zeros['last_value']=0.;zeros['rolling_mean26']=0.
    assert predict_reversion(zeros,np.array([.5]),False).tolist()==[0.]*len(rows)


def test_calibration_ignores_unpublished_outcomes() -> None:
    issue=pd.Timestamp('2025-01-05')
    history=pd.DataFrame(dict(horizon_weeks=[8]*400,model=['lightgbm']*400,
        as_of_date=pd.Timestamp('2024-09-01'),target_published_on=[pd.Timestamp('2024-12-14')]*200+[pd.Timestamp('2025-02-14')]*200,
        actual=np.tile([10.,30.],200),last_value=20.,growth=np.tile([0.,1.],200),
        prob_growth_raw=np.tile([.3,.7],200),raw_lower=12.,raw_upper=28.,prediction=20.))
    earlier=past_errors(history,issue,8,'lightgbm')
    after=history.copy();after.loc[after.target_published_on.gt(issue),['actual','growth']]=99999
    later=past_errors(after,issue,8,'lightgbm')
    pd.testing.assert_frame_equal(earlier,later)
    p1,c1=calibrate_probabilities(np.array([.2,.8]),earlier)
    p2,c2=calibrate_probabilities(np.array([.2,.8]),later)
    np.testing.assert_array_equal(p1,p2);assert c1==c2
    low,high,status=calibrate_bands(np.array([20.]),np.array([12.]),np.array([28.]),np.array([20.]),earlier,np.array([5.]),'lightgbm')
    assert low[0]<=10 and high[0]>=30
    assert status=='past_issued_quantile_errors'


def test_brier_curve_and_unchanged_event_definition() -> None:
    rows=pd.DataFrame(dict(growth=[0.,1.,0.],prob=[.1,.8,.3],actual=[1.,4.,2.],last_value=[2.,2.,2.]))
    m=probability_metrics(rows,'prob')
    assert m['brier']==pytest.approx((.01+.04+.09)/3)
    assert m['unchanged_n']==1 and m['grow_shrink_accuracy']==1
    assert sum(b['n'] for b in m['calibration_curve'])==3


def test_lightgbm_native_api_quantiles_and_zero_counts() -> None:
    rng=np.random.default_rng(42);x=rng.normal(size=300)
    train=pd.DataFrame(dict(x=x,last_value=np.maximum(0,10*x),log_ratio=.1*x,growth=(x>0).astype(float)))
    quantiles,classifier=train_boosters(train,['x'])
    counts,p=predict_boosters(train,['x'],quantiles,classifier)
    assert counts.shape==(300,3) and np.isfinite(counts).all()
    assert (counts>=0).all() and (np.diff(counts,axis=1)>=0).all()
    assert ((p>=0)&(p<=1)).all()


def test_saved_pairing_training_cutoffs_and_gate() -> None:
    report=json.loads((OUTPUTS_DIR/'backtest_model.json').read_text())
    base=pd.read_parquet(OUTPUTS_DIR/'backtest_baseline_predictions.parquet')
    predictions=pd.read_parquet(OUTPUTS_DIR/'backtest_model_predictions.parquet')
    panel=pd.read_parquet(OUTPUTS_DIR/'model_features.parquet')
    assert comparison(base,predictions)==report['metrics']
    assert choose_model(report['metrics'])[1]==report['gate']
    assert len(paired_cases(base,panel))==12547
    assert predictions.target_date.eq(predictions.as_of_date+pd.to_timedelta(predictions.horizon_weeks*7,unit='D')).all()
    assert predictions.feature_max_published_on.le(predictions.as_of_date).all()
    assert predictions.training_max_target_published_on.le(predictions.as_of_date).all()
    measured=predictions.calibration_max_target_published_on.dropna()
    assert measured.le(predictions.loc[measured.index,'as_of_date']).all()
    assert predictions.upper_80.ge(predictions.lower_80).all() and predictions.lower_80.ge(0).all()
    assert predictions.prob_growth.between(0,1).all()
    assert predictions.historical_vintage_verified.eq(False).all()
    assert panel.feature_max_published_on.le(panel.as_of_date).all()


def test_pairing_rejects_missing_cases() -> None:
    base=pd.read_parquet(OUTPUTS_DIR/'backtest_baseline_predictions.parquet')
    predictions=pd.read_parquet(OUTPUTS_DIR/'backtest_model_predictions.parquet')
    from pipeline.common import DataError
    with pytest.raises(DataError,match='Unpaired'):
        comparison(base,predictions.iloc[1:])


def test_latest_forecasts_and_classifier_artifacts() -> None:
    from pipeline.universe import load_core_trusts
    forecast=json.loads((OUTPUTS_DIR/'forecasts_latest.json').read_text())
    assert {r['org_code'] for r in forecast['trusts']}==set(load_core_trusts().org_code)
    assert 'RVY' not in {r['org_code'] for r in forecast['trusts']}
    for trust in forecast['trusts']:
        for f in trust['forecasts']:
            assert pd.Timestamp(f['target_date'])-pd.Timestamp(f['issue_date'])==pd.Timedelta(weeks=f['horizon_weeks'])
            assert 0<=f['lower_80']<=f['upper_80']
            assert not any('probability' in key for key in f)
            if f['horizon_weeks']==4:
                assert f['growth_signal'] in {'likely up','likely down','unclear'}
            else:
                assert 'growth_signal' not in f
    assert forecast['national_model_forecasts']['enabled'] is False
    report=json.loads((OUTPUTS_DIR/'backtest_classifier.json').read_text())
    p=pd.read_parquet(OUTPUTS_DIR/'backtest_model_predictions.parquet')
    p=p.loc[p.model.eq('lightgbm')]
    for h in (4,8,12):
        m=next(x for x in report['metrics'] if x['horizon_weeks']==h and x['model']=='calibrated')
        assert probability_metrics(p.loc[p.horizon_weeks.eq(h)],'prob_growth')['brier']==m['brier']


def test_web_upload_archive_excludes_generated_caches(tmp_path: Path) -> None:
    """Package the working tree after pytest has generated caches, then inspect ZIP bytes."""
    import subprocess
    import sys
    from zipfile import ZipFile
    from config import ROOT_DIR
    target=tmp_path/'upload.zip'
    subprocess.run([sys.executable,str(ROOT_DIR/'scripts/package_repo.py'),str(target)],check=True,capture_output=True)
    with ZipFile(target) as archive:
        names=archive.namelist()
        assert len(names)<=100 and all(n.startswith('cancer-clock/') for n in names)
        assert not any('__pycache__' in n or '.pytest_cache' in n or n.endswith(('.pyc','.pyo')) for n in names)
        assert not any('/data/raw/' in n or '/.venv/' in n or '/node_modules/' in n for n in names)
        assert 'cancer-clock/.env' not in names
        assert all(info.file_size<25_000_000 for info in archive.infolist())

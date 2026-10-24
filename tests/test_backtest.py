"""Analytical fixtures and real snapshot invariants for the evaluation contract."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config import PROCESSED_DIR, STATIC_DIR
from models.backtest import evaluate, summarize
from models.baselines import calibration_errors, interval, mase_scale, predict
from pipeline.check import KEYS
from pipeline.common import first_release
from pipeline.fetch import candidate, select_sources
from pipeline.universe import core_locations, load_core_trusts
from pipeline.vintages import available_at


@pytest.mark.parametrize('name', list(KEYS))
def test_publication_lag_every_dataset(name: str) -> None:
    """Every bundled row follows M+2/day14 and has a 44–75 day observation lag."""
    frame=pd.read_parquet(PROCESSED_DIR/f'{name}.parquet')
    time=frame.week_ending if name.startswith('backlog') else frame.period
    assert frame.published_on.eq(first_release(time)).all()
    assert (frame.published_on-time).dt.days.between(44,75).all()
    assert frame.historical_vintage_verified.eq(False).all()
    assert frame.availability_label.eq('approximate: latest revised values').all()
    assert frame.source_published_on.notna().all()


def test_revision_upload_does_not_hide_first_release() -> None:
    """The late March 2025 revision keeps its 2026 provenance but is available in May 2025."""
    c=candidate('dm01','CSV Extract March 2025 All Provider',
                'https://www.england.nhs.uk/wp-content/uploads/2026/04/DM01-MARCH-2025-full-extract.zip','source')
    assert c['published_on']=='2025-05-14'
    assert c['source_published_on']=='2026-04-14'
    later={**c,'source_published_on':'2026-05-14','url':'later'}
    assert select_sources([c,later])[0]['url']=='later'
    frame=pd.read_parquet(PROCESSED_DIR/'dm01.parquet')
    data=available_at(frame,'2025-05-14',allow_approximate=True)
    assert pd.Timestamp('2025-03-01') in set(data.period)


def test_core_universe_and_real_locations() -> None:
    """Apr–Sep rows train only; RVY and independent providers cannot enter the map."""
    backlog=pd.read_parquet(PROCESSED_DIR/'backlog_trust.parquet')
    observed=backlog.loc[backlog.backlog.notna() & backlog.week_ending.ge('2023-10-01')]
    core=load_core_trusts()
    assert set(core.org_code)==set(observed.org_code)
    assert 'RVY' not in set(core.org_code)
    assert backlog.week_ending.min()==pd.Timestamp('2023-04-09')
    assert backlog.loc[backlog.org_code.eq('RVY') & backlog.week_ending.lt('2023-10-01'),'backlog'].notna().any()
    assert set(core_locations().org_code)==set(core.org_code)
    locations=pd.read_csv(STATIC_DIR/'trust_locations.csv').set_index('org_code')
    for code,postcode in [('RRK','B15 2GW'),('RVJ','BS10 5NB'),('RWP','WR5 1DD'),('RAP','N18 1QX')]:
        assert locations.loc[code,'postcode']==postcode
        assert locations.loc[code,'location_kind']=='representative_main_hospital_postcode'
    assert 'RVY' not in set(locations.loc[locations.map_eligible].index)


def fixture() -> pd.DataFrame:
    """Deterministic synthetic rising series, not bundled as demo output."""
    dates=pd.date_range('2023-04-09',periods=130,freq='7D')
    return pd.DataFrame(dict(org_code='TEST',week_ending=dates,backlog=100.+2*np.arange(len(dates)),
                             published_on=first_release(pd.Series(dates)),historical_vintage_verified=False))


def test_baselines_scale_and_zero_floor() -> None:
    values=np.arange(10.,28.,2.)
    assert predict(values,4)=={'naive':26.,'drift':34.}
    assert predict(values[::-1],12)['drift']==0
    assert mase_scale(values)==2
    assert mase_scale(np.zeros(9)) is None
    assert mase_scale(np.array([1.,np.nan,100.,102.]))==2
    with pytest.raises(ValueError): predict(np.array([1.]*8+[np.nan]),4)
    assert interval(0,np.zeros(8))==(0,0)


def test_time_axis_metrics_and_paired_cases() -> None:
    rows,_=evaluate(fixture(),{'TEST'},pd.DatetimeIndex(['2024-06-16']))
    obs=rows.loc[rows.anchor.eq('observation') & rows.horizon_weeks.eq(4)]
    assert (obs.target_date==obs.latest_observation+pd.Timedelta(weeks=4)).all()
    assert (obs.issue_lead_weeks==4-obs.publication_lag_weeks).all()
    assert obs.issue_lead_weeks.lt(0).all()
    issue=rows.loc[rows.anchor.eq('issue')]
    assert issue.issue_lead_weeks.eq(issue.horizon_weeks).all()
    assert rows.loc[rows.model.eq('drift'),'absolute_error'].eq(0).all()
    assert rows.loc[rows.model.eq('drift'),'covered_80'].all()
    naive=rows.loc[rows.model.eq('naive')]
    assert np.allclose(naive.scaled_error,naive.observation_horizon_weeks)
    assert not naive.direction_correct.any()
    assert all(g.model.nunique()==2 for _,g in rows.groupby(['anchor','horizon_weeks']))
    assert all(m['mase']==0 for m in summarize(rows) if m['model']=='drift')


def test_unpublished_values_cannot_change_predictions_or_intervals() -> None:
    data=fixture(); issue=pd.Timestamp('2024-06-16')
    before,_=evaluate(data,{'TEST'},pd.DatetimeIndex([issue]))
    changed=data.copy()
    changed.loc[changed.published_on.gt(issue),'backlog']+=10000
    after,_=evaluate(changed,{'TEST'},pd.DatetimeIndex([issue]))
    fields=['prediction','lower_80','upper_80','training_scale','calibration_n','latest_observation']
    pd.testing.assert_frame_equal(before[fields],after[fields])
    assert not before.actual.equals(after.actual)


def test_no_core_leakage_and_missing_history() -> None:
    data=fixture(); extra=data.assign(org_code='INDEPENDENT',backlog=9000.)
    rows,_=evaluate(pd.concat([data,extra]),{'TEST'},pd.DatetimeIndex(['2024-06-16']))
    assert set(rows.org_code)=={'TEST'}
    data.loc[data.week_ending.eq('2024-04-28'),'backlog']=np.nan
    from pipeline.common import DataError
    with pytest.raises(DataError,match='No evaluable'):
        evaluate(data,{'TEST'},pd.DatetimeIndex(['2024-06-16']))


def test_calibration_excludes_unpublished_labels() -> None:
    values=np.arange(40,dtype=float)
    dates=pd.date_range('2023-04-09',periods=40,freq='7D')
    releases=first_release(pd.Series(dates)).to_numpy()
    cutoff=pd.Timestamp('2023-10-15')
    before=calibration_errors(values,releases,cutoff,4)
    values[releases>np.datetime64(cutoff)]=99999
    after=calibration_errors(values,releases,cutoff,4)
    for model in before: np.testing.assert_array_equal(before[model],after[model])


def test_saved_results_are_consistent() -> None:
    """Audit artifacts reconcile exactly to summaries and retain their uncertainty bands."""
    import json
    from config import OUTPUTS_DIR
    report=json.loads((OUTPUTS_DIR/'backtest_baselines.json').read_text())
    rows=pd.read_parquet(OUTPUTS_DIR/'backtest_baseline_predictions.parquet')
    assert summarize(rows)==report['metrics']
    assert rows.target_date.ge('2023-10-01').all()
    assert rows.latest_observation.lt(rows.as_of_date).all()
    assert rows.lower_80.ge(0).all() and rows.upper_80.ge(rows.lower_80).all()
    assert rows.calibration_n.ge(8).all()
    assert set(rows.org_code)<=set(load_core_trusts().org_code)

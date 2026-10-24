"""Independent checks of paired resampling, release cutoffs and display restrictions."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from config import OUTPUTS_DIR
from models.review import adjusted_predictions, bias_offset, direction_signal, trust_bootstrap


def test_snapshot_comparison_allows_roundoff_but_rejects_changed_evidence() -> None:
    from copy import deepcopy
    from models.check import assert_snapshot_equal
    from pipeline.common import DataError
    expected=dict(metrics=[dict(mae=28.334155804968983,n=4371,beats_naive=True)],model='lightgbm_blend')
    rounded=deepcopy(expected)
    rounded['metrics'][0]['mae']=np.nextafter(expected['metrics'][0]['mae'],np.inf)
    assert rounded!=expected
    assert_snapshot_equal(rounded,expected)
    for key,bad in [('mae',28.34),('mae',float('nan')),('mae',float('inf')),
                    ('n',4372),('n',4371.0),('beats_naive',False),('beats_naive',1)]:
        changed=deepcopy(expected);changed['metrics'][0][key]=bad
        with pytest.raises(DataError,match=key):
            assert_snapshot_equal(changed,expected)
    with pytest.raises(DataError,match='fields'):
        assert_snapshot_equal({},expected)
    with pytest.raises(DataError,match='lengths'):
        assert_snapshot_equal([],expected['metrics'])
    with pytest.raises(DataError,match='model'):
        assert_snapshot_equal({**expected,'model':'naive'},expected)


def test_full_model_check_handles_bootstrap_roundoff_without_hiding_errors(monkeypatch) -> None:
    from models import check
    from pipeline.common import DataError
    original=check.evaluate
    def rounded(*args):
        result=original(*args)
        stats=result['metrics'][0]['trust_bootstrap']
        stats['ci95_low_pct']=float(np.nextafter(stats['ci95_low_pct'],np.inf))
        return result
    monkeypatch.setattr(check,'evaluate',rounded)
    check.main()
    def corrupted(*args):
        result=original(*args);result['metrics'][0]['mae']+=.01
        return result
    monkeypatch.setattr(check,'evaluate',corrupted)
    with pytest.raises(DataError,match=r'review.metrics\[0\].mae'):
        check.main()


def test_bootstrap_resamples_whole_trusts_not_individual_dates() -> None:
    rows=pd.DataFrame(dict(org_code=['A','A','A'],last_value=[10.,10.,10.],
        actual=[20.,20.,20.],prediction=[20.,0.,10.]))
    # One cluster: no resampling variation despite very different row errors.
    result=trust_bootstrap(rows,replicates=1000)
    assert result['trusts']==1
    assert result['ci95_low_pct']==result['ci95_high_pct']==result['gain_pct']==0.
    two=pd.DataFrame(dict(org_code=['A','A','B','B'],last_value=0.,actual=10.,prediction=[10.,10.,30.,30.]))
    result=trust_bootstrap(two,replicates=1000)
    assert result['ci95_low_pct']==-100. and result['ci95_high_pct']==100.


def test_bias_correction_cannot_use_unpublished_or_current_outcomes() -> None:
    issue=pd.Timestamp('2025-01-05')
    rows=pd.DataFrame(dict(model='lightgbm',horizon_weeks=8,as_of_date=pd.Timestamp('2024-08-04'),
        target_published_on=[pd.Timestamp('2024-11-14')]*200+[pd.Timestamp('2025-02-14')]*200,
        actual=[22.]*400,prediction=[20.]*400))
    before=bias_offset(rows,issue,8)
    assert before['bias_offset']==2. and before['bias_n']==200
    rows.loc[200:,'actual']=999999.
    assert bias_offset(rows,issue,8)==before
    rows.loc[:199,'as_of_date']=issue
    assert bias_offset(rows,issue,8)['bias_n']==0
    assert bias_offset(rows,issue,8)['bias_offset']==0.


def test_adjusted_outputs_are_paired_and_metrics_match_direct_sums() -> None:
    raw=pd.read_parquet(OUTPUTS_DIR/'backtest_model_predictions.parquet')
    baseline=pd.read_parquet(OUTPUTS_DIR/'backtest_baseline_predictions.parquet')
    adjusted=pd.read_parquet(OUTPUTS_DIR/'backtest_adjusted_predictions.parquet')
    pd.testing.assert_frame_equal(adjusted_predictions(raw,baseline),adjusted)
    report=json.loads((OUTPUTS_DIR/'backtest_model.json').read_text())['review']
    for m in report['metrics']:
        source=raw if m['model']=='lightgbm' else adjusted
        r=source.loc[source.model.eq(m['model']) & source.horizon_weeks.eq(m['horizon_weeks'])]
        assert m['mae']==pytest.approx(abs(r.prediction-r.actual).mean())
        assert m['mean_signed_error']==pytest.approx((r.prediction-r.actual).mean())
        sums=r.groupby('as_of_date')[['actual','prediction','last_value']].sum()
        assert m['national_sum']['model_mae']==pytest.approx(abs(sums.prediction-sums.actual).mean())
        swings=abs(r.actual-r.last_value)>.3*r.last_value
        assert m['large_swings']['n']==int(swings.sum())
        assert m['large_swings']['model_mae']==pytest.approx(abs(r.prediction-r.actual)[swings].mean())
    correction=adjusted.loc[adjusted.model.eq('lightgbm_bias_corrected')]
    dates=correction.bias_max_target_published_on.dropna()
    assert dates.le(correction.loc[dates.index,'as_of_date']).all()
    assert report['selected_trust_model']=='lightgbm_blend'


def test_direction_display_abstains_on_disagreement_and_zero_baselines() -> None:
    assert direction_signal(.7,100,110)=='likely up'
    assert direction_signal(.3,100,90)=='likely down'
    assert direction_signal(.5,100,110)=='unclear'
    assert direction_signal(.3,100,110)=='unclear'
    assert direction_signal(.7,100,90)=='unclear'
    assert direction_signal(.2,0,0)=='unclear'
    latest=json.loads((OUTPUTS_DIR/'forecasts_latest.json').read_text())
    assert latest['selected_model']=='lightgbm_blend'
    for t in latest['trusts']:
        for f in t['forecasts']:
            assert f['lower_80']<=f['point_forecast']<=f['upper_80']
            assert not any('probability' in k for k in f)
            assert ('growth_signal' in f)==(f['horizon_weeks']==4)

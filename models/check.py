"""Verify bundled Stage 3 results without repeating model fitting."""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pandas as pd

from config import OUTPUTS_DIR, STATIC_DIR, PROCESSED_DIR
from models.forecast import KEY, comparison, choose_model
from models.calibration import probability_metrics
from models.review import adjusted_predictions, evaluate, merger_impact
from pipeline.common import DataError


def assert_snapshot_equal(actual: object, expected: object, path: str = 'report') -> None:
    """Allow numerical roundoff only; keep structure, counts and decisions exact."""
    if isinstance(actual, np.generic):
        actual = actual.item()
    if isinstance(expected, np.generic):
        expected = expected.item()
    if isinstance(actual, dict) and isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise DataError(f'{path}: report fields differ')
        for key in expected:
            assert_snapshot_equal(actual[key], expected[key], f'{path}.{key}')
        return
    if isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            raise DataError(f'{path}: report lengths differ ({len(actual)} != {len(expected)})')
        for index, (a, e) in enumerate(zip(actual, expected)):
            assert_snapshot_equal(a, e, f'{path}[{index}]')
        return
    if isinstance(actual, float) and isinstance(expected, float):
        # BLAS reductions can differ in their final bits across Mac/Linux builds.
        if math.isfinite(actual) and math.isfinite(expected) and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-10):
            return
    elif type(actual) is type(expected) and actual == expected:
        return
    raise DataError(f'{path}: recalculated {actual!r}, saved {expected!r}')


def main() -> None:
    """Check exact pairing, scoring, cutoffs, bands, probabilities and artifact hashes."""
    path=OUTPUTS_DIR/'backtest_baseline_predictions.parquet'
    baseline=pd.read_parquet(path)
    report=json.loads((OUTPUTS_DIR/'backtest_model.json').read_text())
    for name, expected in report['input_sha256'].items():
        source=(STATIC_DIR if name.endswith('.csv') else PROCESSED_DIR)/name
        if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:
            raise DataError(f'Input changed since model fitting: {name}')
    predictions=pd.read_parquet(OUTPUTS_DIR/'backtest_model_predictions.parquet')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=report['baseline_sha256']:
        raise DataError('Baseline artifact changed; rebuild Stage 3 against the new cases')
    assert_snapshot_equal(comparison(baseline,predictions),report['metrics'],'model.metrics')
    assert_snapshot_equal(choose_model(report['metrics'])[1],report['gate'],'model.gate')
    adjusted=pd.read_parquet(OUTPUTS_DIR/'backtest_adjusted_predictions.parquet')
    pd.testing.assert_frame_equal(adjusted_predictions(predictions,baseline),adjusted,
                                  check_exact=False,rtol=1e-12,atol=1e-10)
    review=evaluate(predictions,adjusted)
    for key,value in review.items():
        assert_snapshot_equal(value,report['review'][key],f'review.{key}')
    checks=[predictions.feature_max_published_on.le(predictions.as_of_date).all(),
            predictions.training_max_target_published_on.le(predictions.as_of_date).all(),
            (predictions.calibration_max_target_published_on.isna() | predictions.calibration_max_target_published_on.le(predictions.as_of_date)).all(),
            predictions.lower_80.ge(0).all(),predictions.upper_80.ge(predictions.lower_80).all(),
            predictions.prob_growth.between(0,1).all(),predictions.historical_vintage_verified.eq(False).all(),
            predictions.target_date.eq(predictions.as_of_date+pd.to_timedelta(predictions.horizon_weeks*7,unit='D')).all()]
    if not all(checks): raise DataError('A date, interval or probability invariant failed')
    classifier=json.loads((OUTPUTS_DIR/'backtest_classifier.json').read_text())
    for h in (4,8,12):
        rows=predictions.loc[predictions.model.eq('lightgbm')&predictions.horizon_weeks.eq(h)]
        m=next(x for x in classifier['metrics'] if x['horizon_weeks']==h and x['model']=='calibrated')
        assert_snapshot_equal(probability_metrics(rows,'prob_growth')['brier'],m['brier'],f'classifier.{h}w.brier')
    latest=json.loads((OUTPUTS_DIR/'forecasts_latest.json').read_text())
    assert_snapshot_equal(merger_impact(report,predictions,adjusted,latest),
                          report['review']['merger_impact'],'review.merger_impact')
    core=pd.read_csv(STATIC_DIR/'core_trusts.csv')
    if {t['org_code'] for t in latest['trusts']}!=set(core.org_code):
        raise DataError('Latest forecasts do not account for every core trust')
    if latest['selected_model']!=report['review']['selected_trust_model']:
        raise DataError('Latest display model differs from reviewed selection')
    if latest['national_model_forecasts']['enabled']:
        raise DataError('Full England model forecasts are not validated')
    for trust in latest['trusts']:
        for forecast in trust['forecasts']:
            if any('probability' in key for key in forecast):
                raise DataError('Numerical growth probabilities entered the display contract')
            if forecast['horizon_weeks']!=4 and 'growth_signal' in forecast:
                raise DataError('Growth signals must be limited to four weeks')
    for h in (4,8,12):
        m=next(m for m in report['review']['metrics'] if m['horizon_weeks']==h and m['model']==latest['selected_model'])
        print(f'Issue +{h} weeks: {m["n"]:,} paired cases; selected {m["model"]}, MAE {m["mae"]:.2f}')
    print(f'Latest issue {latest["issue_date"]}: {latest["forecast_trusts"]}/{len(core)} trusts have sufficient recent history.')
    print('Model and review snapshot checks passed. '+report['availability_label'])


if __name__=='__main__':
    main()

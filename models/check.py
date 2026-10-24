"""Verify bundled Stage 3 results without repeating model fitting."""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from config import OUTPUTS_DIR, STATIC_DIR, PROCESSED_DIR
from models.forecast import KEY, comparison, choose_model
from models.calibration import probability_metrics
from pipeline.common import DataError


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
    if comparison(baseline,predictions)!=report['metrics']:
        raise DataError('Model score report does not match row-level results')
    if choose_model(report['metrics'])[1]!=report['gate']:
        raise DataError('GO/NO-GO report does not match measured results')
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
        if probability_metrics(rows,'prob_growth')['brier']!=m['brier']:
            raise DataError('Classifier Brier score differs from row-level predictions')
    latest=json.loads((OUTPUTS_DIR/'forecasts_latest.json').read_text())
    core=pd.read_csv(STATIC_DIR/'core_trusts.csv')
    if {t['org_code'] for t in latest['trusts']}!=set(core.org_code):
        raise DataError('Latest forecasts do not account for every core trust')
    for h in (4,8,12):
        m=next(m for m in report['metrics'] if m['horizon_weeks']==h and m['model']==report['gate']['selected'])
        print(f'Issue +{h} weeks: {m["n"]:,} paired cases; selected {m["model"]}, MAE {m["mae"]:.2f}')
    print(f'Latest issue {latest["issue_date"]}: {latest["forecast_trusts"]}/{len(core)} trusts have sufficient recent history.')
    print('Stage 3 snapshot checks passed. '+report['availability_label'])


if __name__=='__main__':
    main()

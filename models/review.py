"""Small post-review additions: paired uncertainty, slices, bias and fixed blending."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import FORECAST_HORIZONS_WEEKS, OUTPUTS_DIR
from models.backtest import score
from models.calibration import past_errors
from pipeline.common import DataError

BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 42
BLEND_WEIGHT = 0.5
BIAS_MIN_CASES = 200
KEY = ['org_code', 'as_of_date', 'horizon_weeks']


def trust_bootstrap(rows: pd.DataFrame, *, replicates: int = BOOTSTRAP_REPLICATES,
                    seed: int = BOOTSTRAP_SEED) -> dict:
    """Resample whole trusts, retaining all their paired issue dates per draw."""
    errors = pd.DataFrame({'org_code': rows.org_code,
        'naive': abs(rows.last_value - rows.actual),
        'model': abs(rows.prediction - rows.actual)})
    totals = errors.groupby('org_code', sort=True)[['naive', 'model']].sum().to_numpy()
    if len(totals) == 0 or totals[:, 0].sum() <= 0:
        raise DataError('Bootstrap requires paired cases with positive baseline error')
    rng = np.random.default_rng(seed)
    gains = []
    for start in range(0, replicates, 1000):
        weights = rng.multinomial(len(totals), np.full(len(totals), 1 / len(totals)),
                                 size=min(1000, replicates - start))
        sums = weights @ totals
        valid = sums[:, 0] > 0
        gains.extend((100 * (1 - sums[valid, 1] / sums[valid, 0])).tolist())
    lo, hi = np.quantile(gains, [.025, .975])
    return dict(gain_pct=100 * (1 - totals[:, 1].sum() / totals[:, 0].sum()),
        ci95_low_pct=float(lo), ci95_high_pct=float(hi), trusts=len(totals),
        replicates=replicates, valid_replicates=len(gains), seed=seed,
        method='Percentile paired trust-cluster bootstrap; resample trusts with all their cases.',
        caveat='Preserves within-trust dependence; does not capture shared national shocks or model-selection uncertainty.')


def bias_offset(predictions: pd.DataFrame, issue: pd.Timestamp, horizon: int) -> dict:
    """Expanding mean actual-minus-predicted, from published earlier issued errors."""
    old = past_errors(predictions, issue, horizon, 'lightgbm')
    return dict(bias_offset=float((old.actual - old.prediction).mean()) if len(old) >= BIAS_MIN_CASES else 0.,
        bias_n=len(old), bias_max_target_published_on=old.target_published_on.max() if len(old) else pd.NaT)


def adjusted_predictions(raw: pd.DataFrame, baselines: pd.DataFrame) -> pd.DataFrame:
    """Two fixed experiments; neither fits on the current issue's future outcome."""
    model = raw.loc[raw.model.eq('lightgbm')].copy()
    base = baselines.loc[baselines.anchor.eq('issue') & baselines.model.eq('naive')].set_index(KEY)
    if model.duplicated(KEY).any() or len(base) != len(model):
        raise DataError('Adjustment cases must match baseline one-to-one')
    aligned = base.loc[pd.MultiIndex.from_frame(model[KEY])]
    if not np.allclose(aligned.actual, model.actual) or not np.allclose(aligned.prediction, model.last_value):
        raise DataError('Adjustment baseline values differ')
    corrected = model.copy()
    corrected['model'] = 'lightgbm_bias_corrected'
    corrected['bias_offset'] = 0.
    corrected['bias_n'] = 0
    corrected['bias_max_target_published_on'] = pd.NaT
    for (issue, h), indices in corrected.groupby(['as_of_date', 'horizon_weeks']).groups.items():
        for key, value in bias_offset(model, issue, h).items():
            corrected.loc[indices, key] = value
    for col in ['prediction', 'lower_80', 'upper_80']:
        corrected[col] = (corrected[col] + corrected.bias_offset).clip(lower=0)
    corrected['interval_method'] = 'Original band shifted by published-history bias offset; floored at zero'
    blend = model.copy()
    blend['model'] = 'lightgbm_blend'
    for col in ['prediction', 'lower_80', 'upper_80']:
        blend[col] = BLEND_WEIGHT * model[col].to_numpy() + (1 - BLEND_WEIGHT) * aligned[col].to_numpy()
    blend['interval_method'] = 'Fixed 50:50 blend of model and persistence points/band endpoints; empirical coverage reported'
    parts = []
    for frame in [corrected, blend]:
        frame['absolute_error'] = abs(frame.prediction - frame.actual)
        frame['scaled_error'] = frame.absolute_error / frame.training_scale.where(frame.training_scale.gt(0))
        frame['direction_correct'] = np.sign(frame.prediction - frame.last_value).eq(np.sign(frame.actual - frame.last_value))
        frame['covered_80'] = frame.actual.between(frame.lower_80, frame.upper_80)
        parts.append(frame)
    return pd.concat(parts, ignore_index=True)


def direction_signal(probability: float, last: float, point: float) -> str:
    """Four-week display heuristic; model agreement and a 0.4–0.6 abstention band."""
    if probability >= .6 and point > last:
        return 'likely up'
    if probability <= .4 and point < last:
        return 'likely down'
    return 'unclear'


def evaluate(raw: pd.DataFrame, adjusted: pd.DataFrame) -> dict:
    """Report paired case MAE, aggregate MAE, signed bias and the post-hoc swing slice."""
    combined = pd.concat([raw.loc[raw.model.eq('lightgbm')], adjusted], ignore_index=True)
    metrics = []
    for (model, horizon), rows in combined.groupby(['model', 'horizon_weeks'], sort=True):
        big = rows.loc[abs(rows.actual - rows.last_value) > .3 * rows.last_value]
        national = rows.groupby('as_of_date')[['actual', 'prediction', 'last_value']].sum()
        counts = rows.groupby('as_of_date').size()
        naive_mae = float(abs(rows.last_value - rows.actual).mean())
        national_naive = float(abs(national.last_value - national.actual).mean())
        national_model = float(abs(national.prediction - national.actual).mean())
        big_naive = float(abs(big.last_value - big.actual).mean())
        big_model = float(abs(big.prediction - big.actual).mean())
        metrics.append(dict(model=model, horizon_weeks=int(horizon), **score(rows),
            mean_signed_error=float((rows.prediction - rows.actual).mean()), naive_mae=naive_mae,
            trust_bootstrap=trust_bootstrap(rows),
            large_swings=dict(n=len(big), zero_last_value_n=int(big.last_value.eq(0).sum()),
                naive_mae=big_naive, model_mae=big_model, gain_pct=100 * (1 - big_model / big_naive)),
            national_sum=dict(n_origins=len(national), min_trusts=int(counts.min()), max_trusts=int(counts.max()),
                naive_mae=national_naive, model_mae=national_model,
                gain_pct=100 * (1 - national_model / national_naive), beats_naive=national_model < national_naive,
                scope='Sum over identical scored trusts at each issue; coverage varies, not the official England series.')))
    return dict(metrics=metrics,
        bias_rule=f'Per-horizon expanding mean actual-minus-raw-prediction from earlier issues with target release <= issue; zero until {BIAS_MIN_CASES} cases.',
        blend_rule='Fixed 50:50 LightGBM/last-value blend at every horizon; weight not fitted or searched.',
        large_swings_rule='abs(actual - last) > 0.30 * last; zero last includes any nonzero actual.',
        large_swings_caveat='Outcome-defined, post-hoc diagnostic slice; not a group identifiable at forecast time.',
        evaluation_caveat='Requested after inspection of Stage 3 results; all additions and selection remain exploratory.',
        national_display=dict(enabled=False,
            reason='Only paired cohort sums have been evaluated; full England coverage and aggregate intervals are not established. No national model forecasts exported.'))


def run() -> dict:
    """Refresh the review and latest display contract without rerunning historical fits."""
    from models.forecast import export_latest, write_json
    from models.features import load_sources
    from pipeline.universe import load_core_trusts
    report = json.loads((OUTPUTS_DIR / 'backtest_model.json').read_text())
    raw = pd.read_parquet(OUTPUTS_DIR / 'backtest_model_predictions.parquet')
    base = pd.read_parquet(OUTPUTS_DIR / 'backtest_baseline_predictions.parquet')
    adjusted = adjusted_predictions(raw, base)
    review = evaluate(raw, adjusted)
    original = {(r['model'], r['horizon_weeks']): r for r in report['metrics']}
    blend = {r['horizon_weeks']: r for r in review['metrics'] if r['model'] == 'lightgbm_blend'}
    accept = (all(blend[h][m] < original[b, h][m] for h in (8, 12)
                  for m in ('mae', 'mase') for b in ('naive', 'drift'))
              and all(blend[h]['national_sum']['beats_naive'] for h in FORECAST_HORIZONS_WEEKS))
    review['selected_trust_model'] = 'lightgbm_blend' if accept else report['gate']['selected']
    review['selection_rule'] = 'Use fixed blend if it beats both original baselines on trust MAE/MASE at 8/12w and naive paired-sum MAE at all horizons; otherwise retain Stage 3 selection.'
    report['review'] = review
    report['limitations'] = [s for s in report['limitations'] if 'no significance claim' not in s]
    report['limitations'].append('Trust-cluster bootstrap preserves within-trust dependence but not common national shocks or retrospective selection uncertainty.')
    report['limitations'] = list(dict.fromkeys(report['limitations']))
    adjusted.to_parquet(OUTPUTS_DIR / 'backtest_adjusted_predictions.parquet', index=False)
    write_json(OUTPUTS_DIR / 'backtest_model.json', report)
    classifier = json.loads((OUTPUTS_DIR / 'backtest_classifier.json').read_text())
    classifier['display_policy'] = dict(horizon_weeks=4, labels=['likely up', 'likely down', 'unclear'],
        rule='Raw classifier >=0.6 plus rising point forecast: up; <=0.4 plus falling point: down; else unclear.',
        probabilities_displayed=False, horizons_8_12_displayed=False,
        caveat='Experimental categories, not validated probabilities; thresholds are assumptions.')
    r = raw.loc[raw.model.eq('lightgbm') & raw.horizon_weeks.eq(4)]
    signals = np.array([direction_signal(t.prob_growth_raw, t.last_value, t.prediction) for t in r.itertuples()])
    decisive = signals != 'unclear'
    correct = ((signals == 'likely up') & (r.actual > r.last_value)) | ((signals == 'likely down') & (r.actual < r.last_value))
    classifier['display_policy']['retrospective_4w'] = dict(n=len(r), decisive_n=int(decisive.sum()),
        decisive_accuracy=float(correct[decisive].mean()) if decisive.any() else None,
        unclear_n=int((~decisive).sum()))
    write_json(OUTPUTS_DIR / 'backtest_classifier.json', classifier)
    sources = load_sources()
    panel = pd.read_parquet(OUTPUTS_DIR / 'model_features.parquet')
    latest_issue = panel.as_of_date.max()
    export_latest(sources, load_core_trusts(), panel, report['features'], raw,
                  review['selected_trust_model'], latest_issue, report['gate'], classifier,
                  national_display=review['national_display'])
    for m in review['metrics']:
        print(f'{m["horizon_weeks"]:2}w {m["model"]:25} MAE {m["mae"]:6.2f} bias {m["mean_signed_error"]:+6.2f} '
              f'paired-sum MAE {m["national_sum"]["model_mae"]:7.2f}')
    print('Review complete | trust forecasts:', review['selected_trust_model'], '| national forecasts withheld')
    return review


if __name__ == '__main__':
    run()

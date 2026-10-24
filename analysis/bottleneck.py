"""Stage 4: transparent screening labels, not identified causes of cancer backlogs."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json

import numpy as np
import pandas as pd

from analysis.build_diagnostics import REFERENCE_PATH, SCOPE
from config import DOCS_DIR, OUTPUTS_DIR, PROCESSED_DIR, STATIC_DIR
from models.backtest import LABEL
from models.forecast import jsonable, write_json
from pipeline.common import DataError, assert_unique
from pipeline.parse_cwt import tidy
from pipeline.parse_dm01 import TESTS
from pipeline.universe import load_core_trusts
from pipeline.vintages import available_at

RULES = dict(months=3, minimum_months=2, minimum_fds_volume=100,
    minimum_treatment_volume=30, minimum_dm01_monthly_list=100,
    shrinkage_volume=100, signal_threshold_pp=5., high_strength_threshold_pp=10.,
    high_strength_volume=200, high_diagnosis_requires_fds_corroboration=True,
    status='Assumed screening rules, not fitted or clinically validated thresholds')
CWT_MEASURES = [
    ('fds', 'Faster diagnosis (28-day)', 'diagnosis'),
    ('d31_surgery', 'Surgery 31-day', 'treatment'),
    ('d31_radiotherapy', 'Radiotherapy 31-day', 'treatment'),
    ('d31_drugs', 'Anti-cancer drug treatment 31-day', 'treatment')]
LABELS = {'diagnosis-limited', 'treatment-limited', 'mixed', 'no clear bottleneck'}
INPUTS = [PROCESSED_DIR / f'{n}.parquet' for n in ['cwt_trust_month', 'cwt_national', 'backlog_national']]
INPUTS += [REFERENCE_PATH, STATIC_DIR / 'core_trusts.csv']


def load_inputs() -> dict[str, pd.DataFrame]:
    """Use the shared core cohort; England references retain their official scope."""
    if not REFERENCE_PATH.exists():
        raise DataError('Missing bundled DM01 reference; rebuild with python -m analysis.build_diagnostics after fetching sources.')
    return dict(cwt=pd.read_parquet(INPUTS[0]), national_cwt=pd.read_parquet(INPUTS[1]),
        backlog_national=pd.read_parquet(INPUTS[2]), dm01=pd.read_parquet(REFERENCE_PATH))


def indicator(key: str, name: str, side: str, trust: pd.DataFrame, national: pd.DataFrame,
              numerator: str, denominator: str, minimum: int, *, waiting_list: bool = False) -> dict:
    """Pool counts over matching months; shrink shortfalls for small denominators."""
    cols = ['period', numerator, denominator, 'published_on']
    assert_unique(trust, ['period'], key + ' trust')
    assert_unique(national, ['period'], key + ' England')
    joined = trust[cols].merge(national[cols], on='period', suffixes=('', '_national'), validate='one_to_one')
    valid = joined[[numerator, denominator, numerator + '_national', denominator + '_national']].notna().all(axis=1)
    valid &= joined[denominator].gt(0) & joined[denominator + '_national'].gt(0)
    for suffix in ['', '_national']:
        valid &= joined[numerator + suffix].ge(0) & joined[numerator + suffix].le(joined[denominator + suffix])
    usable = joined.loc[valid]
    result = dict(key=key, name=name, side=side, eligible=False, status='missing_or_zero_volume',
        months_used=int(len(usable)), periods=usable.period.tolist(),
        trust_rate_pct=None, national_rate_pct=None, gap_pp=None, score_pp=None,
        denominator=None, effective_volume=None, positive_months=0,
        max_published_on=usable[['published_on', 'published_on_national']].max().max() if len(usable) else None,
        reference_scope=SCOPE if waiting_list else 'Published England CWT ALL CANCERS, matching route/stage/modality',
        volume_basis='Minimum monthly waiting-list size; pooled denominator is patient-months, not unique people' if waiting_list else 'Completed pathways across matched months')
    if usable.empty:
        return result
    total = float(usable[denominator].sum())
    p = float(100 * usable[numerator].sum() / total)
    q = float(100 * usable[numerator + '_national'].sum() / usable[denominator + '_national'].sum())
    gap = p - q if waiting_list else q - p
    monthly_gap = 100 * (usable[numerator] / usable[denominator] - usable[numerator + '_national'] / usable[denominator + '_national'])
    if not waiting_list:
        monthly_gap = -monthly_gap
    volume = float(usable[denominator].min() if waiting_list else total)
    eligible = len(usable) >= RULES['minimum_months'] and volume >= minimum
    adjusted_gap = max(0., gap) * volume / (volume + RULES['shrinkage_volume'])
    positive_months = int(monthly_gap.gt(0).sum())
    # A single adverse month cannot establish a persistent three-month signal.
    score = adjusted_gap if positive_months >= RULES['minimum_months'] else 0.
    result.update(eligible=eligible, status='usable' if eligible else 'insufficient_months_or_volume',
        trust_rate_pct=p, national_rate_pct=q, gap_pp=gap, score_pp=score if eligible else None,
        denominator=total, effective_volume=volume, positive_months=positive_months)
    return result


def side_summary(indicators: list[dict], side: str) -> dict:
    """Diagnosis uses FDS or the top-two test mean; treatment uses worst modality."""
    eligible = [r for r in indicators if r['side'] == side and r['eligible']]
    if not eligible:
        return dict(score_pp=None, signal=False, driver=None, confidence='low', eligible_indicators=0)
    if side == 'diagnosis':
        fds = next((r for r in eligible if r['key'] == 'fds'), None)
        dm = sorted([r for r in eligible if r['key'] != 'fds'], key=lambda r: r['score_pp'], reverse=True)[:2]
        dm_score = float(np.mean([r['score_pp'] for r in dm])) if dm else -1.
        if fds is not None and fds['score_pp'] >= dm_score:
            value, driver = fds['score_pp'], fds
        else:
            value, driver = dm_score, dm[0]
    else:
        driver = max(eligible, key=lambda r: r['score_pp'])
        value = driver['score_pp']
    signal = value >= RULES['signal_threshold_pp']
    strength = 'low'
    if signal:
        strength = 'high' if (driver['months_used'] == 3 and driver['positive_months'] == 3
            and driver['effective_volume'] >= RULES['high_strength_volume']
            and value >= RULES['high_strength_threshold_pp']) else 'medium'
        if side == 'diagnosis' and not any(r['key'] == 'fds' and r['score_pp'] >= RULES['signal_threshold_pp'] for r in eligible):
            strength = 'medium'  # DM01 includes non-cancer demand; FDS corroboration matters.
    return dict(score_pp=value, signal=signal, driver=driver['key'] if signal else None,
        confidence=strength, eligible_indicators=len(eligible))


def classify(indicators: list[dict]) -> dict:
    """Keep evidence availability separate from the four required display labels."""
    diagnosis = side_summary(indicators, 'diagnosis')
    treatment = side_summary(indicators, 'treatment')
    label = ('mixed' if diagnosis['signal'] and treatment['signal'] else
             'diagnosis-limited' if diagnosis['signal'] else
             'treatment-limited' if treatment['signal'] else 'no clear bottleneck')
    available = sum(r['eligible_indicators'] > 0 for r in [diagnosis, treatment])
    status = {0: 'insufficient_data', 1: 'partial_evidence', 2: 'screened'}[available]
    active = [r for r in [diagnosis, treatment] if r['signal']]
    confidence = 'low' if status != 'screened' or not active else (
        'high' if all(r['confidence'] == 'high' for r in active) else 'medium')
    strongest = max(active, key=lambda r: r['score_pp']) if active else None
    lookup = {r['key']: r for r in indicators}
    driver = lookup[strongest['driver']]['name'] if strongest else None
    caveats = []
    fds = lookup.get('fds')
    if diagnosis['signal'] and not (fds and fds['eligible'] and fds['score_pp'] >= RULES['signal_threshold_pp']):
        caveats.append('Diagnostic-test pressure is not corroborated by an FDS signal; DM01 includes non-cancer demand.')
    if status != 'screened':
        caveats.append('One or both pathway sides lack comparable evidence; missing data does not mean no bottleneck.')
    return dict(label=label, evidence_status=status, confidence=confidence,
        confidence_meaning='Heuristic evidence strength, not a probability or confidence in causation',
        main_driver=driver, diagnosis=diagnosis, treatment=treatment, caveats=caveats)


def build(sources: dict[str, pd.DataFrame], core: pd.DataFrame, issue: pd.Timestamp) -> dict:
    """Select a common calendar window after publication filtering, never backfill it."""
    known = {k: available_at(v, issue, allow_approximate=True) for k, v in sources.items()}
    national_cwt = tidy(known['national_cwt'])
    national_cwt = national_cwt.loc[national_cwt.cancer_type.eq('ALL CANCERS')]
    dm = known['dm01']
    national_dm = dm.loc[dm.org_code.eq('ENGLAND')]
    if national_cwt.empty or national_dm.empty:
        raise DataError('No common published CWT/DM01 reference at this issue')
    last = min(national_cwt.period.max(), national_dm.period.max())
    months = pd.date_range(last - pd.DateOffset(months=2), last, freq='MS')
    cwt = known['cwt'].loc[known['cwt'].cancer_type.eq('ALL CANCERS') & known['cwt'].period.isin(months)]
    national_cwt = national_cwt.loc[national_cwt.period.isin(months)]
    dm = dm.loc[dm.period.isin(months)]
    national_dm = national_dm.loc[national_dm.period.isin(months)]
    trusts = []
    for trust in core.itertuples():
        c = cwt.loc[cwt.org_code.eq(trust.org_code)]
        d = dm.loc[dm.org_code.eq(trust.org_code)]
        indicators = []
        for prefix, name, side in CWT_MEASURES:
            minimum = RULES['minimum_fds_volume'] if prefix == 'fds' else RULES['minimum_treatment_volume']
            indicators.append(indicator(prefix, name, side, c, national_cwt, prefix + '_within', prefix + '_total', minimum))
        for test in TESTS.values():
            name = f'Endoscopy ({test.lower()}) waits' if test in ['Colonoscopy', 'Flexi sigmoidoscopy', 'Gastroscopy', 'Cystoscopy'] else f'{test} diagnostic waits'
            indicators.append(indicator('dm01_' + test, name, 'diagnosis', d.loc[d.test.eq(test)],
                national_dm.loc[national_dm.test.eq(test)], 'waiting_6plus', 'total_waiting_list',
                RULES['minimum_dm01_monthly_list'], waiting_list=True))
        trusts.append(dict(org_code=trust.org_code, name=trust.name, **classify(indicators), indicators=indicators))
    backlog = known['backlog_national'].sort_values('week_ending')
    context = None
    if len(backlog):
        row = backlog.iloc[-1]
        context = dict(week_ending=row.week_ending, published_on=row.published_on, total=row.total,
            no_dtt=row.no_dtt, with_dtt=row.with_dtt, no_dtt_fraction=row.no_dtt / row.total if row.total else None,
            scope='Observed England backlog only; never assigned to a trust or used in its label.',
            interpretation='No recorded decision to treat / recorded decision to treat; this split does not identify the cause of a delay.')
    return dict(stage=4, as_of_date=issue, window_months=list(months), availability_label=LABEL,
        historical_vintage_verified=False, rules=RULES,
        interpretation='Descriptive screening for clinical review, not a causal diagnosis or a capacity estimate.',
        national_context=context, trusts=trusts, counts=dict(Counter(t['label'] for t in trusts)),
        evidence_counts=dict(Counter(t['evidence_status'] for t in trusts)))


def examples(report: dict) -> str:
    """Ten named examples including sparse providers, prepared for Rounak to review."""
    lookup = {t['org_code']: t for t in report['trusts']}
    codes = ['RTH', 'RRK', 'RWP', 'RVJ', 'RAP', 'RY2', 'RGT', 'RJ1', 'R0A', 'RM1']
    codes = [c for c in codes if c in lookup]
    codes += [c for c in sorted(lookup) if c not in codes][:10 - len(codes)]
    text = ['# Rounak: Stage 4 sanity check', '',
        'Window: ' + ', '.join(str(pd.Timestamp(m).date())[:7] for m in report['window_months']) + '.',
        'These are heuristic labels, not a clinical review already completed. Low evidence is not evidence of a healthy pathway.', '',
        '| Trust | Label | Evidence / strength | Diagnosis / treatment score (pp) | Main driver |',
        '| --- | --- | --- | ---: | --- |']
    for code in codes:
        t = lookup[code]
        def show(value: float | None) -> str:
            return '—' if value is None else f'{value:.1f}'
        scores = show(t['diagnosis']['score_pp']) + ' / ' + show(t['treatment']['score_pp'])
        text.append(f'| {code} — {t["name"]} | {t["label"]} | {t["evidence_status"]} / {t["confidence"]} | {scores} | {t["main_driver"] or "No persistent signal / insufficient evidence"} |')
    text += ['', 'Review whether the main service and label fit local knowledge; check referral networks and specialist case mix before interpreting a difference as capacity pressure. Component rates, volumes and matched England rates are in `outputs/bottlenecks.json`.']
    return '\n'.join(text) + '\n'


def main() -> None:
    """Offline build or an exact check of the bundled Stage 4 artifact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', help='Publication cutoff; defaults to latest shared monthly release')
    parser.add_argument('--check', action='store_true', help='Recompute and compare to the saved artifact')
    args = parser.parse_args()
    sources = load_inputs()
    path = OUTPUTS_DIR / 'bottlenecks.json'
    saved = json.loads(path.read_text()) if args.check else None
    issue = pd.Timestamp(args.as_of or (saved['as_of_date'] if saved else
        min(sources['cwt'].published_on.max(), sources['dm01'].published_on.max())))
    report = build(sources, load_core_trusts(), issue)
    report['input_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in INPUTS}
    if args.check:
        if jsonable(report) != saved:
            raise DataError('Bottleneck artifact differs from current inputs or rules; rebuild it')
    else:
        write_json(path, report)
        (DOCS_DIR / 'bottleneck_examples.md').write_text(examples(report))
    print(f'Stage 4 {"snapshot checks passed" if args.check else "complete"}: {len(report["trusts"])} core trusts')
    print('Labels:', report['counts'])
    print('Evidence:', report['evidence_counts'])
    print(LABEL)


if __name__ == '__main__':
    main()

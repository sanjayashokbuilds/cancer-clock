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
    high_strength_volume=200, dm01_role='supporting context only; never a driver',
    status='Assumed screening rules, not fitted or clinically validated thresholds')
CWT_MEASURES = [
    ('d31_surgery', 'Surgery 31-day', 'treatment'),
    ('d31_radiotherapy', 'Radiotherapy 31-day', 'treatment'),
    ('d31_drugs', 'Anti-cancer drug treatment 31-day', 'treatment')]
LABELS = {'diagnosis-limited', 'treatment-limited', 'mixed', 'no clear bottleneck'}
INPUTS = [PROCESSED_DIR / f'{n}.parquet' for n in ['cwt_trust_month', 'cwt_national', 'backlog_national']]
INPUTS += [REFERENCE_PATH, STATIC_DIR / 'core_trusts.csv', STATIC_DIR / 'trust_mergers.csv', STATIC_DIR / 'provider_scope.csv']

LOWER_GI = 'Suspected lower gastrointestinal cancer'
UPPER_GI = 'Suspected upper gastrointestinal cancer'
UROLOGY = 'Suspected urological malignancies (excluding testicular)'
LUNG = 'Suspected lung cancer'
DM_LINKS = {'Colonoscopy': [LOWER_GI], 'Flexi sigmoidoscopy': [LOWER_GI],
    'Gastroscopy': [UPPER_GI], 'Cystoscopy': [UROLOGY], 'CT': [LUNG, LOWER_GI, UPPER_GI, UROLOGY],
    'MRI': [], 'Non-obstetric ultrasound': []}
PATHWAY_NAMES = {LOWER_GI: 'Lower GI', UPPER_GI: 'Upper GI', UROLOGY: 'Urology', LUNG: 'Lung'}


def load_inputs() -> dict[str, pd.DataFrame]:
    """Use the shared core cohort; England references retain their official scope."""
    if not REFERENCE_PATH.exists():
        raise DataError('Missing bundled DM01 reference; rebuild with python -m analysis.build_diagnostics after fetching sources.')
    from pipeline.mergers import load_harmonized
    return dict(cwt=load_harmonized('cwt_trust_month'), national_cwt=pd.read_parquet(INPUTS[1]),
        backlog_national=pd.read_parquet(INPUTS[2]), dm01=load_harmonized('dm01_bottleneck_reference'))


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
    """Only cancer-specific FDS and treatment modalities may drive a label."""
    eligible = [r for r in indicators if r['side'] == side and r['eligible']
                and r.get('role', 'driver') == 'driver' and not r['key'].startswith('dm01_')]
    if not eligible:
        return dict(score_pp=None, signal=False, driver=None, confidence='low', eligible_indicators=0)
    driver = max(eligible, key=lambda r: r['score_pp'])
    value = driver['score_pp']; signal = value >= RULES['signal_threshold_pp']
    strength = 'low'
    if signal:
        strength = 'high' if (driver['months_used'] == 3 and driver['positive_months'] == 3
            and driver['effective_volume'] >= RULES['high_strength_volume']
            and value >= RULES['high_strength_threshold_pp']) else 'medium'
    return dict(score_pp=value, signal=signal, driver=driver['key'] if signal else None,
        confidence=strength, eligible_indicators=len(eligible))


def classify(indicators: list[dict]) -> dict:
    """Expose both drivers for mixed labels, with missing evidence kept explicit."""
    diagnosis = side_summary(indicators, 'diagnosis'); treatment = side_summary(indicators, 'treatment')
    label = ('mixed' if diagnosis['signal'] and treatment['signal'] else
             'diagnosis-limited' if diagnosis['signal'] else
             'treatment-limited' if treatment['signal'] else 'no clear bottleneck')
    available = sum(r['eligible_indicators'] > 0 for r in [diagnosis, treatment])
    status = {0: 'insufficient_data', 1: 'partial_evidence', 2: 'screened'}[available]
    active = [r for r in [diagnosis, treatment] if r['signal']]
    confidence = 'low' if status != 'screened' or not active else (
        'high' if all(r['confidence'] == 'high' for r in active) else 'medium')
    lookup = {r['key']: r for r in indicators}
    drivers = [lookup[r['driver']] for r in active]
    caveats = ['DM01 is routine diagnostic context and includes non-cancer demand; it never determines this label.']
    if status != 'screened':
        caveats.append('One or both pathway sides lack comparable evidence; missing data does not mean no bottleneck.')
    return dict(label=label, evidence_status=status, confidence=confidence,
        confidence_meaning='Heuristic evidence strength, not a probability or confidence in causation',
        main_driver=' + '.join(r['name'] for r in drivers) if drivers else None,
        main_drivers=drivers, diagnosis_driver=lookup.get(diagnosis['driver']),
        treatment_driver=lookup.get(treatment['driver']), diagnosis=diagnosis, treatment=treatment, caveats=caveats)


def supporting_context(row: dict, cancer_indicators: list[dict], test: str) -> dict:
    """Require a qualifying matching cancer FDS gap before calling DM01 corroborated."""
    matches = [r for r in cancer_indicators if r.get('cancer_type') in DM_LINKS[test]]
    adverse = [r for r in matches if r['eligible'] and r['score_pp'] >= RULES['signal_threshold_pp']]
    dm_adverse = row['eligible'] and row['score_pp'] >= RULES['signal_threshold_pp']
    row.update(role='context', matching_cancer_types=DM_LINKS[test],
        corroboration='corroborated' if dm_adverse and adverse else 'uncorroborated',
        corroborated_cancer_types=[r['cancer_type'] for r in adverse] if dm_adverse else [],
        cancer_type_evidence=matches,
        context_note='Broad test with substantial non-cancer demand; no unique cancer mapping' if not DM_LINKS[test]
            else 'Directional concordance of aggregate data, not proof that routine waits delay cancer diagnosis')
    return row


def build(sources: dict[str, pd.DataFrame], core: pd.DataFrame, issue: pd.Timestamp) -> dict:
    """Select a common calendar window after publication filtering, never backfill it."""
    known = {k: available_at(v, issue, allow_approximate=True) for k, v in sources.items()}
    national_cwt = tidy(known['national_cwt'])
    dm = known['dm01']
    national_dm = dm.loc[dm.org_code.eq('ENGLAND')]
    if national_cwt.empty or national_dm.empty:
        raise DataError('No common published CWT/DM01 reference at this issue')
    last = min(national_cwt.period.max(), national_dm.period.max())
    months = pd.date_range(last - pd.DateOffset(months=2), last, freq='MS')
    cwt = known['cwt'].loc[known['cwt'].period.isin(months)]
    national_cwt = national_cwt.loc[national_cwt.period.isin(months)]
    dm = dm.loc[dm.period.isin(months)]
    national_dm = national_dm.loc[national_dm.period.isin(months)]
    trusts = []
    for trust in core.itertuples():
        c = cwt.loc[cwt.org_code.eq(trust.org_code)]
        d = dm.loc[dm.org_code.eq(trust.org_code)]
        indicators = []
        cancer_types = sorted(national_cwt.loc[national_cwt.cancer_type.str.startswith('Suspected ') & national_cwt.fds_total.notna(), 'cancer_type'].unique())
        for cancer in cancer_types:
            name = PATHWAY_NAMES.get(cancer, cancer.removeprefix('Suspected ').removesuffix(' cancer').capitalize()) + ' FDS'
            row = indicator('fds_' + cancer, name, 'diagnosis', c.loc[c.cancer_type.eq(cancer)],
                national_cwt.loc[national_cwt.cancer_type.eq(cancer)], 'fds_within', 'fds_total', RULES['minimum_fds_volume'])
            row.update(cancer_type=cancer, role='driver', reference_scope='Published England FDS, same suspected cancer type and ALL ROUTES')
            indicators.append(row)
        cancer_indicators = indicators.copy()
        for prefix, name, side in CWT_MEASURES:
            row = indicator(prefix, name, side, c.loc[c.cancer_type.eq('ALL CANCERS')],
                national_cwt.loc[national_cwt.cancer_type.eq('ALL CANCERS')], prefix + '_within', prefix + '_total', RULES['minimum_treatment_volume'])
            row['role'] = 'driver'; indicators.append(row)
        for test in TESTS.values():
            row = indicator('dm01_' + test, test + ' 6+ week waits', 'diagnostic_context', d.loc[d.test.eq(test)],
                national_dm.loc[national_dm.test.eq(test)], 'waiting_6plus', 'total_waiting_list', RULES['minimum_dm01_monthly_list'], waiting_list=True)
            indicators.append(supporting_context(row, cancer_indicators, test))
        corroborated = sorted({cancer for r in indicators if r.get('corroboration') == 'corroborated' for cancer in r['corroborated_cancer_types']})
        trusts.append(dict(org_code=trust.org_code, name=trust.name, **classify(indicators),
            corroborated_cancer_types=corroborated, indicators=indicators))
    backlog = known['backlog_national'].sort_values('week_ending')
    context = None
    if len(backlog):
        row = backlog.iloc[-1]
        context = dict(week_ending=row.week_ending, published_on=row.published_on, total=row.total,
            no_dtt=row.no_dtt, with_dtt=row.with_dtt, no_dtt_fraction=row.no_dtt / row.total if row.total else None,
            scope='Observed England backlog only; never assigned to a trust or used in its label.',
            interpretation='No recorded decision to treat / recorded decision to treat; this split does not identify the cause of a delay.')
    from pipeline.mergers import GEOGRAPHY
    return dict(stage=5, geography_label=GEOGRAPHY, as_of_date=issue, window_months=list(months), availability_label=LABEL,
        historical_vintage_verified=False, rules=RULES,
        interpretation='Descriptive screening for clinical review, not a causal diagnosis or a capacity estimate.',
        national_context=context, trusts=trusts, counts=dict(Counter(t['label'] for t in trusts)),
        evidence_counts=dict(Counter(t['evidence_status'] for t in trusts)))


def examples(report: dict) -> str:
    """Ten live acute trusts; clinical review is explicitly still pending."""
    lookup = {t['org_code']: t for t in report['trusts']}
    codes = ['RTH', 'RRK', 'RWP', 'RA7', 'RAL', 'RX1', 'RGT', 'RJ1', 'R0A', 'RM1']
    text = ['# Rounak: clinical review pending', '',
        'Window: ' + ', '.join(str(pd.Timestamp(m).date())[:7] for m in report['window_months']) + '.',
        'Cancer-specific FDS drives diagnosis labels; DM01 is supporting context only. Percentages below are trust vs England.', '',
        '| Trust | Label / strength | Diagnosis evidence | Treatment evidence | DM01 context and cancer corroboration |',
        '| --- | --- | --- | --- | --- |']
    def evidence(row: dict | None) -> str:
        if row is None:
            return 'No qualifying signal'
        return f'{row["name"]}: {row["trust_rate_pct"]:.1f}% vs {row["national_rate_pct"]:.1f}%, n={row["denominator"]:.0f}'
    for code in codes:
        t = lookup[code]
        contexts = [r for r in t['indicators'] if r.get('role') == 'context' and r['eligible'] and r['key'] not in ['dm01_MRI','dm01_Non-obstetric ultrasound']]
        # Audit the previously misleading examples directly, even if another test is worse.
        preferred = {'RTH':'dm01_Gastroscopy','RRK':'dm01_Gastroscopy','RJ1':'dm01_Cystoscopy','RM1':'dm01_Cystoscopy','R0A':'dm01_Colonoscopy'}.get(code)
        context = next((r for r in contexts if r['key'] == preferred), None) or (max(contexts,key=lambda r:r['score_pp']) if contexts else None)
        note = 'No comparable diagnostic context'
        if context:
            linked = context['cancer_type_evidence']
            note = evidence(context) + '; **' + context['corroboration'] + '**'
            if linked:
                note += '; ' + ' / '.join(evidence(r) for r in linked if r['trust_rate_pct'] is not None)
        text.append(f'| {code} | {t["label"]} / {t["confidence"]} | {evidence(t["diagnosis_driver"])} | {evidence(t["treatment_driver"])} | {note} |')
    text += ['', 'Please review case mix, referral networks and the clinical interpretation. No clinical sign-off has been recorded. Full component counts, periods, shrinkage and gaps are in `outputs/bottlenecks.json`.']
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

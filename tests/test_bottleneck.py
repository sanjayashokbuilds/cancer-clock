"""Bottleneck rules, missing-data semantics, provenance and national-context isolation."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from analysis.bottleneck import build, classify, indicator, LABELS, load_inputs
from analysis.build_diagnostics import REFERENCE_PATH
from config import OUTPUTS_DIR
from pipeline.common import first_release
from pipeline.universe import load_core_trusts


def rates(within: list[float], total: list[float]) -> pd.DataFrame:
    months=pd.date_range('2026-06-01',periods=3,freq='MS')
    return pd.DataFrame(dict(period=months,within=within,total=total,published_on=first_release(pd.Series(months))))


def component(key: str, side: str, score: float, eligible: bool=True) -> dict:
    return dict(key=key,name=key,side=side,eligible=eligible,score_pp=score,
        months_used=3,positive_months=3,effective_volume=500)


def test_count_weighted_rates_and_repeated_waiting_list_volume() -> None:
    trust=rates([90,450,50],[100,900,100])
    national=rates([900,900,900],[1000,1000,1000])
    result=indicator('fds','FDS','diagnosis',trust,national,'within','total',100)
    assert result['trust_rate_pct']==pytest.approx(100*590/1100)
    assert result['gap_pp']==pytest.approx(90-100*590/1100)
    assert result['score_pp']==pytest.approx(result['gap_pp']*1100/1200)
    # Repeated DM01 patients cannot turn a monthly list of 100 into 1,100 people.
    dm=indicator('dm01_CT','CT','diagnosis',trust,national,'within','total',100,waiting_list=True)
    assert dm['effective_volume']==100 and dm['denominator']==1100
    assert dm['score_pp']==0  # Lower six-week-wait rate is better, not worse.


def test_missing_low_volume_and_one_bad_month_do_not_create_strong_signal() -> None:
    national=rates([900,900,900],[1000,1000,1000])
    low=indicator('fds','FDS','diagnosis',rates([0,0,0],[1,1,1]),national,'within','total',100)
    assert low['eligible'] is False and low['score_pp'] is None
    missing=indicator('fds','FDS','diagnosis',rates([0,np.nan,np.nan],[1000,1000,1000]),national,'within','total',100)
    assert missing['months_used']==1 and missing['eligible'] is False
    transient=indicator('fds','FDS','diagnosis',rates([0,950,950],[1000,1000,1000]),national,'within','total',100)
    assert transient['gap_pp']>5 and transient['score_pp']==0


@pytest.mark.parametrize('diagnosis,treatment,label',[(20,0,'diagnosis-limited'),(0,20,'treatment-limited'),
    (20,20,'mixed'),(0,0,'no clear bottleneck')])
def test_four_labels_and_missing_side_confidence(diagnosis: float,treatment: float,label: str) -> None:
    r=classify([component('fds','diagnosis',diagnosis),component('d31_surgery','treatment',treatment)])
    assert r['label']==label and r['evidence_status']=='screened'
    if diagnosis or treatment:
        assert r['confidence']=='high'
    partial=classify([component('fds','diagnosis',20)])
    assert partial['label']=='diagnosis-limited' and partial['confidence']=='low'
    assert partial['evidence_status']=='partial_evidence'
    empty=classify([component('fds','diagnosis',0,False)])
    assert empty['evidence_status']=='insufficient_data' and empty['label']=='no clear bottleneck'


def test_dm01_cannot_drive_a_label_even_if_mistagged() -> None:
    r=classify([component('dm01_CT','diagnosis',80),component('dm01_MRI','diagnosis',90),
        component('d31_surgery','treatment',0)])
    assert r['diagnosis']['score_pp'] is None
    assert r['label']=='no clear bottleneck'


def test_past_labels_ignore_future_values_and_national_dtt_split() -> None:
    sources=load_inputs();core=load_core_trusts()
    core=core.loc[core.org_code.isin({'RTH','RRK','RY2'})]
    issue=pd.Timestamp('2025-01-20')
    before=build(sources,core,issue)
    poisoned={k:v.copy() for k,v in sources.items()}
    for frame in poisoned.values():
        future=frame.published_on.gt(issue)
        for col in frame.select_dtypes(include='number'):
            frame.loc[future,col]=frame.loc[future,col]+10000
    after=build(poisoned,core,issue)
    assert before==after
    poisoned['backlog_national']['no_dtt']=0.
    poisoned['backlog_national']['with_dtt']=poisoned['backlog_national'].total
    assert build(poisoned,core,issue)['trusts']==before['trusts']


def test_saved_bottlenecks_cover_only_core_and_auditable_published_window() -> None:
    report=json.loads((OUTPUTS_DIR/'bottlenecks.json').read_text())
    assert {t['org_code'] for t in report['trusts']}==set(load_core_trusts().org_code)
    assert len(report['window_months'])==3 and sum(report['counts'].values())==len(load_core_trusts())
    for trust in report['trusts']:
        assert trust['label'] in LABELS
        assert sum(r.get('role')=='context' for r in trust['indicators'])==7
        assert not any(r['key'].startswith('dm01_') for r in trust['main_drivers'])
        for row in trust['indicators']:
            assert set(row['periods']).issubset(report['window_months'])
            if row['max_published_on']:
                assert row['max_published_on']<=report['as_of_date']
            if row['eligible']:
                assert row['months_used']>=2 and row['effective_volume']>0
    ref=pd.read_parquet(REFERENCE_PATH)
    assert ref.published_on.eq(first_release(ref.period)).all()
    assert (ref.published_on-ref.period).dt.days.between(44,75).all()
    assert not ref.historical_vintage_verified.any()
    from pipeline.mergers import load_harmonized
    assert set(load_harmonized('dm01_bottleneck_reference').org_code)-{'ENGLAND'}<=set(load_core_trusts().org_code)
    assert ref.loc[ref.org_code.eq('ENGLAND'),'provider_count'].max()>133


def test_diagnostic_reference_rebuild_retains_predecessor_counts(monkeypatch, tmp_path) -> None:
    from analysis import build_diagnostics as builder
    raw=pd.read_parquet(REFERENCE_PATH)
    raw=raw.loc[raw.period.eq(raw.period.min()) & raw.org_code.isin({'RA7','RVJ','RAL','RAP'})].copy()
    assert {'RA7','RVJ','RAL','RAP'}<=set(raw.org_code)
    monkeypatch.setattr(builder,'read_manifest',lambda: pd.DataFrame([dict(dataset='dm01',period='2023-10',local_path='unused')]))
    monkeypatch.setattr(builder,'parse_zip',lambda *args,**kwargs: raw)
    monkeypatch.setattr(builder,'load_core_trusts',lambda: pd.DataFrame(dict(org_code=['RA7','RAL'])))
    monkeypatch.setattr(builder,'REFERENCE_PATH',tmp_path/'reference.parquet')
    rebuilt=builder.run()
    assert {'RA7','RVJ','RAL','RAP','ENGLAND'}<=set(rebuilt.org_code)
    assert rebuilt.loc[rebuilt.org_code.eq('RVJ'),'total_waiting_list'].sum()==raw.loc[raw.org_code.eq('RVJ'),'total_waiting_list'].sum()

"""Merger boundaries, cancer linkage and daily stochastic queue contracts."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from config import OUTPUTS_DIR, PROCESSED_DIR, STATIC_DIR
from pipeline.mergers import harmonize, load_harmonized, mask_retired_backlogs, mergers
from pipeline.universe import load_core_trusts
from sim.calibrate import prepare, prior_from_bottleneck
from sim.scenarios import Scenario, compare, recovery_days
from sim.simulator import AGE_MAX, State, initial_state, measures, simulate, step


def test_confirmed_mergers_conserve_pre_boundary_counts_and_mask_retired_zeros() -> None:
    raw=pd.read_parquet(PROCESSED_DIR/'backlog_trust.parquet');merged=harmonize(raw,'backlog_trust')
    masked=mask_retired_backlogs(raw)
    for m in mergers().itertuples():
        before=raw.loc[raw.org_code.isin([m.predecessor,m.successor]) & raw.week_ending.lt(m.effective_week)]
        expected=before.pivot(index='week_ending',columns='org_code',values='backlog').sum(axis=1,min_count=2)
        actual=merged.loc[merged.org_code.eq(m.successor)&merged.week_ending.lt(m.effective_week)].set_index('week_ending').backlog
        pd.testing.assert_series_equal(actual,expected.reindex(actual.index),check_names=False)
        old=raw.loc[raw.org_code.eq(m.successor)&raw.week_ending.ge(m.effective_week)].set_index('week_ending').backlog
        new=merged.loc[merged.org_code.eq(m.successor)&merged.week_ending.ge(m.effective_week)].set_index('week_ending').backlog
        pd.testing.assert_series_equal(old,new,check_names=False)
        assert masked.loc[masked.org_code.eq(m.predecessor)&masked.week_ending.ge(m.effective_week),'backlog'].isna().all()
        assert m.predecessor not in set(merged.org_code)
    assert merged.loc[merged.org_code.eq('RA7')&merged.week_ending.eq('2026-06-28'),'backlog'].item()==423.
    assert merged.loc[merged.org_code.eq('RAL')&merged.week_ending.eq('2024-12-29'),'backlog'].item()==424.


def test_cwt_and_dm01_mergers_sum_counts_then_recompute_rates() -> None:
    for name,numerator,denominator,rate,multiplier in [
        ('cwt_trust_month','fds_within','fds_total','fds_performance',1),
        ('dm01','waiting_6plus','total_waiting_list','pct_waiting_6plus',100)]:
        raw=pd.read_parquet(PROCESSED_DIR/f'{name}.parquet');new=harmonize(raw,name)
        if name=='cwt_trust_month':
            raw=raw.loc[raw.cancer_type.eq('ALL CANCERS')];new=new.loc[new.cancer_type.eq('ALL CANCERS')]
        else:
            raw=raw.loc[raw.test.eq('CT')];new=new.loc[new.test.eq('CT')]
        before=raw.loc[raw.period.eq('2026-06-01')&raw.org_code.isin(['RA7','RVJ'])]
        after=new.loc[new.period.eq('2026-06-01')&new.org_code.eq('RA7')].iloc[0]
        assert after[numerator]==before[numerator].sum()
        assert after[denominator]==before[denominator].sum()
        assert after[rate]==pytest.approx(multiplier*before[numerator].sum()/before[denominator].sum())
    # A missing component is not an invented zero in a combined backlog.
    raw=pd.read_parquet(PROCESSED_DIR/'backlog_trust.parquet')
    raw.loc[raw.org_code.eq('RVJ')&raw.week_ending.eq('2026-06-28'),'backlog']=np.nan
    result=harmonize(raw,'backlog_trust')
    assert result.loc[result.org_code.eq('RA7')&result.week_ending.eq('2026-06-28'),'backlog'].isna().all()


def test_scope_and_detector_do_not_merge_live_specialists() -> None:
    scope=pd.read_csv(STATIC_DIR/'provider_scope.csv',keep_default_na=False).set_index('org_code')
    assert scope.loc[['RET','RP6'],'included'].all()
    assert not scope.loc[['RVJ','RAP','RY2','RVY'],'included'].any()
    assert scope.loc['RY2','service_scope']=='community'
    assert scope.loc['RVJ','note']=='merged into RA7'
    audit=json.loads((OUTPUTS_DIR/'merger_audit.json').read_text())
    detected={r['predecessor']:r for r in audit['detector']}
    for predecessor,successor in [('RVJ','RA7'),('RAP','RAL'),('RY2','RWW'),('RVY','RBN')]:
        assert successor in {r['successor'] for r in detected[predecessor]['candidates']}
        assert not detected[predecessor]['automatic_application']
    assert detected['RET']['monthly_activity_continues'] and detected['RP6']['monthly_activity_continues']
    assert not {'RET','RP6'} & set(mergers().predecessor)


def test_cancer_specific_drivers_and_uncorroborated_context_regressions() -> None:
    r=json.loads((OUTPUTS_DIR/'bottlenecks.json').read_text());trusts={t['org_code']:t for t in r['trusts']}
    for code,test in [('RTH','Gastroscopy'),('RRK','Gastroscopy'),('RJ1','Cystoscopy'),('RM1','Cystoscopy')]:
        context=next(x for x in trusts[code]['indicators'] if x['key']=='dm01_'+test)
        assert context['corroboration']=='uncorroborated'
        assert context['cancer_type_evidence'][0]['trust_rate_pct']>context['cancer_type_evidence'][0]['national_rate_pct']
    assert trusts['RTH']['label']=='treatment-limited'
    assert trusts['RTH']['treatment_driver']['key']=='d31_radiotherapy'
    lower=next(x for x in trusts['R0A']['indicators'] if x.get('cancer_type')=='Suspected lower gastrointestinal cancer')
    assert lower['score_pp']>=5 and lower['denominator']==1926
    assert 59<lower['trust_rate_pct']<60 and 67<lower['national_rate_pct']<68
    assert trusts['R0A']['diagnosis']['signal']
    for trust in r['trusts']:
        if trust['label']=='mixed':
            assert trust['diagnosis_driver'] and trust['treatment_driver'] and len(trust['main_drivers'])==2
        assert all(not d['key'].startswith('dm01_') for d in trust['main_drivers'])


def test_day_thresholds_age_transfer_and_open_tail_conservation() -> None:
    d=np.zeros(AGE_MAX+1);t=d.copy();d[62]=2;t[104]=3;d[-1]=4
    state=State(d,t)
    m=measures(state);assert m['backlog_62']==7 and m['long_wait_104']==4
    next_state,_=step(state,0,0,0,.5)
    m=measures(next_state);assert m['backlog_62']==9 and m['long_wait_104']==7
    assert next_state.diagnosis[-1]==4 and m['total_waiting']==9
    d=np.zeros(AGE_MAX+1);d[70]=10
    transferred,_=step(State(d,np.zeros_like(d)),0,10,0,.4)
    assert transferred.treatment[71]==4 and transferred.treatment[0]==0
    assert measures(transferred)['backlog_62']==4  # age does not reset at diagnosis


def test_daily_flow_balance_and_capacity_limits() -> None:
    d=np.zeros(AGE_MAX+1);t=d.copy();d[70]=20;t[80]=10
    initial=State(d,t)
    after,flows=step(initial,5,4,3,.25)
    assert flows['diagnosed']==4 and flows['treated']==3
    assert measures(after)['total_waiting']==pytest.approx(30+5-3-3)
    assert (after.diagnosis>=0).all() and (after.treatment>=0).all()
    empty=State(np.zeros_like(d),np.zeros_like(d));after,_=step(empty,0,100,100,.3)
    assert measures(after)['total_waiting']==0
    with pytest.raises(ValueError):step(initial,-1,1,1,.3)


def test_earlier_calibration_cannot_read_unpublished_values() -> None:
    from models.features import load_sources
    sources=load_sources();issue=pd.Timestamp('2026-06-21')
    before=prepare(sources,'RTH',issue)
    changed={k:v.copy() for k,v in sources.items()}
    for frame in changed.values():
        for col in frame.select_dtypes(include='number'):
            frame.loc[frame.published_on.gt(issue),col]+=100000
    after=prepare(changed,'RTH',issue)
    assert before['status']==after['status']=='ready'
    np.testing.assert_array_equal(before['arrivals'],after['arrivals'])
    np.testing.assert_array_equal(before['observed'],after['observed'])
    assert before['conversion_proxy']==after['conversion_proxy']
    assert before['maximum_input_published_on']<=issue


def test_corroborated_cancer_types_only_supply_a_weak_prior() -> None:
    base=dict(label='diagnosis-limited',evidence_status='screened',corroborated_cancer_types=[])
    a=prior_from_bottleneck(base)
    b=prior_from_bottleneck({**base,'corroborated_cancer_types':['Suspected lung cancer']})
    assert a['diagnosis_share']==.70 and b['diagnosis_share']==.75
    assert a['capacity_ratio_centres']==b['capacity_ratio_centres']==[.98,1.02]
    assert prior_from_bottleneck({**base,'evidence_status':'partial_evidence'})['diagnosis_share']==.5


def test_paired_scenarios_are_reproducible_and_recovery_is_censored() -> None:
    r=json.loads((OUTPUTS_DIR/'simulation_calibration.json').read_text())
    record=next(t for t in r['trusts'] if t['org_code']=='RTH')
    result=compare(record,[Scenario(),Scenario(name='same_physics')],runs=200,horizon_days=14,seed=17)
    a,b=result['plans']
    assert a['backlog_62']==b['backlog_62'] and a['long_wait_104']==b['long_wait_104']
    assert b['final_backlog_change_vs_baseline']['median']==0
    assert result['publication_bridge_days']==49
    assert all('source' in v and 'value' in v for v in a['assumptions'].values())
    never=recovery_days(np.full((2,30),100.),np.full((2,30),10.),2)
    assert never['recovered_fraction']==0 and never['weeks_after_shock_end_among_recovered'] is None
    assert never['not_recovered_by_horizon']==2
    with pytest.raises(ValueError):Scenario(strike_days=-1).validate()
    with pytest.raises(ValueError):Scenario(extra_diagnosis_capacity=2).validate()


def test_extra_capacity_improves_a_controlled_single_stage_queue() -> None:
    d=np.zeros(AGE_MAX+1);t=d.copy();t[80]=100
    low,_=simulate(State(d,t),np.zeros(14),0,1,0)
    high,_=simulate(State(d,t),np.zeros(14),0,2,0)
    assert low['backlog_62'][-1]==pytest.approx(86)
    assert high['backlog_62'][-1]==pytest.approx(72)


def test_recovery_does_not_precede_a_delayed_surge_peak() -> None:
    baseline=np.full((1,120),10.)
    delayed=baseline.copy();delayed[:,80:90]=30.
    result=recovery_days(delayed,baseline,28)
    assert result['recovered_fraction']==1
    assert result['weeks_after_shock_end_among_recovered']['median']==pytest.approx((90-28)/7)
    # Ten post-peak good days are not enough to establish 14-day recovery.
    assert recovery_days(delayed[:,:100],baseline[:,:100],28)['recovered_fraction']==0


def test_saved_simulation_fit_and_ranges_are_honestly_labelled() -> None:
    report=json.loads((OUTPUTS_DIR/'simulation_calibration.json').read_text())
    assert {t['org_code'] for t in report['trusts']}==set(load_core_trusts().org_code)
    fitted=[t for t in report['trusts'] if t['status']=='calibrated']
    assert len(fitted)==report['calibrated_trusts']
    assert 'In-sample' in report['validation'] and 'not jointly identified' in report['identifiability']
    for r in fitted:
        y=np.array(r['observed_backlog'],float);pred=np.array(r['fitted_backlog']);mask=np.isfinite(y)
        assert r['rmse']==pytest.approx(np.sqrt(np.mean((pred[mask]-y[mask])**2)))
        assert len(r['fitted_end_diagnosis_age_days'])==AGE_MAX+1
        assert len(r['fitted_end_treatment_age_days'])==AGE_MAX+1
        assert r['maximum_input_published_on']<=r['issue_date']

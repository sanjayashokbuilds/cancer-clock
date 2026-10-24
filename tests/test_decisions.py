"""Parameter ensemble, exact queue physics and published decision contracts."""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from config import OUTPUTS_DIR
from models.features import load_sources
from pipeline.universe import load_core_trusts
from sim.calibrate import prepare
from sim.decisions import DOSES, check, simulate_fast, treatment_label, validate_calibration_inputs
from sim.simulator import AGE_MAX, State, initial_state, simulate
from sim.uncertainty import capacity_draws


def test_optimized_daily_queues_match_original_physics_and_keep_open_tail() -> None:
    rng=np.random.default_rng(3)
    initial=initial_state(20,.2,100,.7)
    initial.diagnosis[-1]+=4
    arrivals=rng.poisson(20,(4,100))
    dc=rng.uniform(15,25,(4,100));tc=rng.uniform(2,5,(4,100))
    fast,fast_state=simulate_fast(initial,arrivals,dc,tc,.2)
    slow,slow_state=simulate(initial,arrivals,dc,tc,.2,sample_every=1)
    for key in ['backlog_62','long_wait_104']:
        np.testing.assert_allclose(fast[key],slow[key],atol=1e-10,rtol=1e-12)
    np.testing.assert_allclose(fast_state.diagnosis,slow_state.diagnosis,atol=1e-10)
    np.testing.assert_allclose(fast_state.treatment,slow_state.treatment,atol=1e-10)
    d=np.zeros(AGE_MAX+1);d[62]=2;d[-1]=3;t=np.zeros_like(d);t[104]=4
    rows,state=simulate_fast(State(d,t),np.zeros((1,1)),0,0,.5)
    assert rows['backlog_62'][0].tolist()==[7.,9.]
    assert rows['long_wait_104'][0].tolist()==[3.,7.]
    assert state.diagnosis[0,-1]==3


def test_capacity_bootstrap_is_joint_bounded_reproducible_and_issue_specific() -> None:
    report=json.loads((OUTPUTS_DIR/'simulation_calibration.json').read_text())
    record=next(t for t in report['trusts'] if t['org_code']=='RTH')
    inputs=prepare(load_sources(),'RTH',pd.Timestamp(report['issue_date']))
    a,meta=capacity_draws(record,inputs,runs=64,seed=77)
    b,_=capacity_draws(record,inputs,runs=64,seed=77)
    np.testing.assert_array_equal(a,b)
    assert a.shape==(64,2) and np.isfinite(a).all()
    assert (a>=.4).all() and (a<=1.8).all()
    assert np.ptp(a,axis=0).max()>0
    assert meta['candidates_accepted']>=64 and meta['draws']==64
    assert 'not a confidence region' in meta['caveat']
    with pytest.raises(ValueError):
        capacity_draws(record,{**inputs,'org_code':'RAL'})
    with pytest.raises(ValueError):
        capacity_draws(record,{**inputs,'issue_date':pd.Timestamp('2026-09-01')})


def test_modality_labels_require_treatment_evidence_and_expose_proxy() -> None:
    records=json.loads((OUTPUTS_DIR/'bottlenecks.json').read_text())['trusts']
    rth=next(t for t in records if t['org_code']=='RTH')
    ral=next(t for t in records if t['org_code']=='RAL')
    assert treatment_label(rth)[0]=='Radiotherapy capacity (stage proxy)'
    assert 'entire treatment-stage' in treatment_label(rth)[1]
    assert treatment_label(ral)[0]=='Treatment capacity'
    assert treatment_label({**rth,'evidence_status':'partial_evidence'})[0]=='Treatment capacity'


def test_decision_builder_refuses_changed_calibration_inputs() -> None:
    with pytest.raises(ValueError,match='Calibration input changed'):
        validate_calibration_inputs({'input_sha256': {'core_trusts.csv': 'changed'}})


def test_precomputed_decisions_cover_live_trusts_and_preserve_sources() -> None:
    report=check()
    assert len(report['trusts'])==len(load_core_trusts())==130
    ready=[t for t in report['trusts'] if t['status']=='ready']
    assert len(ready)==124 and report['summary']['unavailable_trusts']==6
    assert report['calibration_sha256']==hashlib.sha256((OUTPUTS_DIR/'simulation_calibration.json').read_bytes()).hexdigest()
    for t in report['trusts']:
        assert t['issue_date']==report['issue_date']
    for t in ready:
        for side in ['diagnosis','treatment']:
            assert [p['extra_capacity_pct'] for p in t['dose_response'][side]]==DOSES
        assert t['runs']==256 and t['horizon_days']==182
        assert 'parameter_uncertainty' in t['assumptions']
        assert t['dose_response']['diagnosis'][0]==t['dose_response']['treatment'][0]
        assert len(t['scenario_comparison'])==6
        for plan in t['scenario_comparison']:
            assert len(plan['dates'])==27
            assert plan['final_backlog']['median']==plan['backlog_62']['median'][-1]
        for c in t['band_widening']['comparisons']:
            assert c['combined_width']==pytest.approx(c['combined_final_backlog']['upper_80']-c['combined_final_backlog']['lower_80'])
            if c['process_only_width']>1e-12:
                assert c['ratio']==pytest.approx(c['combined_width']/c['process_only_width'])
            else:
                assert c['ratio'] is None and c['ratio_reason']
    rth=next(t for t in ready if t['org_code']=='RTH')
    ral=next(t for t in ready if t['org_code']=='RAL')
    assert not rth['prior_conflict'] and ral['prior_conflict']
    reference={p['extra_capacity_pct']:p['median'] for p in rth['process_only_dose_reference']['treatment']}
    for pct,expected in {0:171,2:153,5:127,10:88,20:27}.items():
        assert reference[pct]==pytest.approx(expected,abs=.6)
    assert rth['band_widening']['ratio']>1
    assert 8<rth['dose_response']['marginal_benefit']['treatment']['median']<10

"""Forecast anchoring must preserve the paired simulator's intervention maths."""
from __future__ import annotations

import json

import numpy as np
import pytest

from config import OUTPUTS_DIR
from sim.decisions import simulate_fast
from sim.planning_grid import DOSES, TARGET_DIR, check, combinations, scenario_for
from sim.simulator import initial_state


def test_combined_shock_multipliers_and_exact_prefix_replay() -> None:
    rng = np.random.default_rng(19)
    state = initial_state(14, .2, 50, .65)
    arrivals = rng.poisson(14, (3, 90))
    dc = rng.uniform(13, 15, (3, 90)); tc = rng.uniform(2, 3, (3, 90))
    for _, flags in combinations():
        scenario = scenario_for(flags, 'treatment', 10)
        af, df, tf = scenario.multipliers(90)
        assert af[28] == (1.2 if flags['surge'] else 1)
        expected = (.952 if flags['strike'] else 1) * (.9 if flags['winter'] else 1)
        assert df[28] == pytest.approx(expected)
        assert tf[28] == pytest.approx(expected * 1.1)
        full, full_end = simulate_fast(state, arrivals * af, dc * df, tc * tf, .2)
        prefix, end = simulate_fast(state, arrivals[:, :28], dc[:, :28], tc[:, :28], .2)
        tail, tail_end = simulate_fast(end, arrivals[:, 28:] * af[28:], dc[:, 28:] * df[28:], tc[:, 28:] * tf[28:], .2)
        joined = np.concatenate((prefix['backlog_62'][:, :28], tail['backlog_62']), axis=1)
        np.testing.assert_array_equal(joined, full['backlog_62'])
        np.testing.assert_array_equal(tail_end.diagnosis, full_end.diagnosis)
        np.testing.assert_array_equal(tail_end.treatment, full_end.treatment)
    with pytest.raises(ValueError):
        scenario_for({'strike': False, 'winter': False, 'surge': False}, 'treatment', 7)


def test_new_grid_retains_original_rth_absolute_paths_as_evidence_only() -> None:
    grid = json.loads((TARGET_DIR / 'RTH.json').read_text())
    original = next(t for t in json.loads((OUTPUTS_DIR / 'decision_support.json').read_text())['trusts'] if t['org_code'] == 'RTH')
    scenarios = {s['key']: s for s in grid['scenarios']}
    mappings = [('baseline', 'none', 'diagnosis', 0), ('strike', 'strike', 'diagnosis', 0),
                ('strike_plus_diagnosis', 'strike', 'diagnosis', 10),
                ('strike_plus_treatment', 'strike', 'treatment', 10),
                ('winter_dip', 'winter', 'diagnosis', 0), ('referral_surge', 'surge', 'diagnosis', 0)]
    for old_key, new_key, stage, pct in mappings:
        previous = next(p for p in original['scenario_comparison'] if p['key'] == old_key)
        current = next(p for p in scenarios[new_key]['plans'][stage] if p['extra_capacity_pct'] == pct)
        assert grid['dates'] == previous['dates'][:13]
        for q in ['median', 'lower_80', 'upper_80']:
            np.testing.assert_allclose(current['absolute_simulator']['backlog_62'][q],
                                       previous['backlog_62'][q][:13], atol=1e-9, rtol=0)
    # The main decision view ends at 12 weeks and cannot accidentally expose
    # the old absolute day-182 endpoint as its headline result.
    assert grid['horizon_days'] == 84
    assert grid['dates'][-1] == '2027-01-10'
    assert scenarios['none']['plans']['diagnosis'][0]['final_backlog']['median'] != original['scenario_comparison'][0]['final_backlog']['median']


def test_complete_grid_uses_same_start_and_contains_no_uncomputed_controls() -> None:
    manifest = check()
    assert manifest['ready_trusts'] == 109
    assert manifest['unavailable_trusts'] == 21
    assert not manifest['partial']
    for code in manifest['files']:
        grid = json.loads((TARGET_DIR / f'{code}.json').read_text())
        if grid['status'] != 'ready':
            continue
        baseline = grid['scenarios'][0]['plans']['diagnosis'][0]
        for scenario in grid['scenarios']:
            for stage in ['diagnosis', 'treatment']:
                assert len(scenario['plans'][stage]) == len(DOSES)
                for plan in scenario['plans'][stage]:
                    for q in ['median', 'lower_80', 'upper_80']:
                        # The controls cannot alter any outcome before day28.
                        assert plan['backlog_62'][q][:5] == baseline['backlog_62'][q][:5]


def test_unavailable_calibration_keeps_issue_date_without_running_model() -> None:
    from sim.planning_grid import build_trust, validate_record
    record = build_trust(({'org_code': 'RBD', 'status': 'unavailable', 'reason': 'Missing published input'},
                          {'status': 'unavailable', 'issue_date': '2026-10-18'}, {}))
    assert record['status'] == 'unavailable'
    assert record['issue_date'] == '2026-10-18'
    assert record['reason'] == 'Missing published input'
    validate_record(record, {})

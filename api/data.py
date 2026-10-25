"""Load and validate one immutable snapshot; requests never retrain or simulate."""
from __future__ import annotations

from functools import lru_cache
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from config import OUTPUTS_DIR, PROCESSED_DIR, STATIC_DIR
from pipeline.mergers import harmonize, load_harmonized
from pipeline.universe import core_locations, load_core_trusts

BANDS = [('within_31_days', '≤31 days'), ('in_32_to_38_days', '32–38 days'),
         ('in_39_to_48_days', '39–48 days'), ('in_49_to_62_days', '49–62 days'),
         ('in_63_to_76_days', '63–76 days'), ('in_77_to_90_days', '77–90 days'),
         ('in_91_to_104_days', '91–104 days'), ('after_104_days', '>104 days')]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f'Missing bundled snapshot: {path.name}. Rebuild the decision outputs before starting the API.')
    return json.loads(path.read_text())


def records(frame: pd.DataFrame) -> list[dict]:
    """JSON-safe timestamps/nulls without importing training libraries."""
    return json.loads(frame.to_json(orient='records', date_format='iso', date_unit='s'))


def forecast_direction(forecasts: list[dict], latest_backlog: float | None) -> str:
    """Describe material movement of the central forecast, never its certainty."""
    point = next((f for f in forecasts if f.get('horizon_weeks') == 12), None)
    if point is None or latest_backlog is None:
        return 'unclear'
    values = [latest_backlog, point.get('point_forecast')]
    if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in values):
        return 'unclear'
    delta = point['point_forecast'] - latest_backlog
    threshold = max(10., .1 * latest_backlog)
    if delta < -threshold:
        return 'improving'
    if delta > threshold:
        return 'worsening'
    return 'unclear'


def planning_consistency(forecast: dict, decision: dict, issue_date: str) -> dict:
    """Retain the old absolute-level comparison for Evidence only.

    The public recovery level now comes from the statistical forecast. A
    disagreement with the old absolute queue simulation cannot hold it back.
    """
    target = (date.fromisoformat(issue_date) + timedelta(weeks=12)).isoformat()
    rule = 'central baseline outside forecast80range'
    interpretation = 'Diagnostic comparison of the old absolute queue model only; it does not gate forecast-anchored plans.'

    def valid_quantiles(values: dict | None) -> bool:
        if values is None:
            return False
        q = [values.get(key) for key in ['lower_80', 'median', 'upper_80']]
        return (all(isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value) for value in q)
                and 0 <= q[0] <= q[1] <= q[2])

    point = next((p for p in forecast.get('forecasts', [])
                  if p.get('horizon_weeks') == 12 and p.get('target_date') == target
                  and p.get('issue_date') == issue_date), None)
    forecast_q = ({'median': point.get('point_forecast'), 'lower_80': point.get('lower_80'),
                   'upper_80': point.get('upper_80')} if point else None)
    if not valid_quantiles(forecast_q):
        forecast_q = None
    baseline = next((p for p in decision.get('scenario_comparison', [])
                     if p.get('key') == 'baseline' and p.get('extra_capacity_pct', 0) == 0), None)
    simulator_q = None
    if baseline and (baseline.get('dates') or [None])[0] == issue_date:
        dates = baseline.get('dates', [])
        if dates.count(target) == 1:
            index = dates.index(target)
            offsets = baseline.get('day_offsets')
            offsets_match = offsets is None or (index < len(offsets) and offsets[index] == 84)
            values = baseline.get('backlog_62') or {}
            if offsets_match and all(isinstance(values.get(key), (list, tuple))
                                     and index < len(values[key])
                                     for key in ['median', 'lower_80', 'upper_80']):
                simulator_q = {key: values[key][index] for key in ['median', 'lower_80', 'upper_80']}
    if not valid_quantiles(simulator_q):
        simulator_q = None
    common = dict(comparison_date=target, forecast=forecast_q,
                  simulator_baseline=simulator_q, rule=rule, interpretation=interpretation)
    if forecast_q is None or simulator_q is None:
        return dict(**common, status='unavailable', requires_review=False,
            message='The old absolute queue model cannot be compared at this date. Recovery-plan availability is checked separately from its historical fit and identification.')
    if not forecast_q['lower_80'] <= simulator_q['median'] <= forecast_q['upper_80']:
        return dict(**common, status='conflict', requires_review=False,
            message='The old absolute queue model is outside the forecast range. Recovery plans use the forecast level and paired queue-model effects, so this level difference no longer excludes the hospital.')
    return dict(**common, status='consistent', requires_review=False,
        message='The old absolute queue-model median is inside the 12-week forecast range. This diagnostic is not a validation of recovery-plan effects.')


class Snapshot:
    def __init__(self, decision_file: Path | None = None, planning_dir: Path | None = None):
        self.core = load_core_trusts()
        self.codes = set(self.core.org_code)
        self.paths = {name: OUTPUTS_DIR / f'{name}.json' for name in
                      ['forecasts_latest', 'bottlenecks', 'simulation_calibration',
                       'backtest_model', 'backtest_classifier', 'decision_support']}
        if decision_file is not None:
            self.paths['decision_support'] = decision_file
        self.reports = {name: read_json(path) for name, path in self.paths.items()}
        self.issue_date = self.reports['forecasts_latest']['issue_date']
        self.hashes = {path.name: digest(path) for path in self.paths.values()}
        self.indexes = {}
        self.validate()
        # Alternate decision fixtures are independent snapshots. They must opt
        # into a planning directory rather than silently loading production data.
        self.planning_paths = {}
        self.planning_availability = {}
        directory = planning_dir or (OUTPUTS_DIR / 'planning_grid' if decision_file is None else None)
        if directory is not None:
            self.validate_planning_grid(directory)
        self.meta = dict(issue_date=self.issue_date,
            availability_label=self.reports['forecasts_latest']['availability_label'],
            historical_vintage_verified=False,
            geography_label=self.reports['forecasts_latest']['geography_label'])
        self.backlogs = self.make_backlogs()
        self.trusts = self.make_trusts()
        self.histories = self.make_histories()
        self.national = self.make_national()
        self.map = self.make_map()

    def validate(self) -> None:
        for name in ['forecasts_latest', 'bottlenecks', 'simulation_calibration', 'decision_support']:
            report = self.reports[name]
            rows = report['trusts']
            index = {row['org_code']: row for row in rows}
            if len(index) != len(rows) or set(index) != self.codes:
                raise ValueError(f'{name}: duplicate codes or cohort mismatch')
            # Screening is issued on the release day; forecasts use the following Sunday.
            report_date = pd.Timestamp(report.get('issue_date', report.get('as_of_date')))
            issue = pd.Timestamp(self.issue_date)
            date_ok = (issue - pd.Timedelta(days=6) <= report_date <= issue) if name == 'bottlenecks' else report_date == issue
            if not date_ok:
                raise ValueError(f'{name}: mixed snapshot issue dates')
            self.indexes[name] = index
        decision = self.reports['decision_support']
        for field, filename in [('calibration_sha256', 'simulation_calibration'),
                                ('bottleneck_sha256', 'bottlenecks')]:
            if decision.get(field) != digest(self.paths[filename]):
                raise ValueError(f'Decision output uses different {filename}; regenerate it')
        for name in ['simulation_calibration', 'backtest_model', 'bottlenecks']:
            for filename, expected in self.reports[name]['input_sha256'].items():
                path = (STATIC_DIR if filename.endswith('.csv') else PROCESSED_DIR) / filename
                if digest(path) != expected:
                    raise ValueError(f'{name}: source changed since computation: {filename}')
        for row in self.indexes['decision_support'].values():
            if row.get('status') not in {'ready', 'unavailable'}:
                raise ValueError('Unexpected decision availability status')
            if row['status'] == 'ready':
                curve = row['dose_response']
                if curve['horizon_days'] != 182:
                    raise ValueError('Decision horizon differs from six-month contract')
                for stage in ['diagnosis', 'treatment']:
                    if [p['extra_capacity_pct'] for p in curve[stage]] != curve['capacity_percent']:
                        raise ValueError('Dose curve grid mismatch')
                    if not all(0 <= p['lower_80'] <= p['median'] <= p['upper_80'] for p in curve[stage]):
                        raise ValueError('Invalid dose-response interval')

    def validate_planning_grid(self, directory: Path) -> None:
        """Load optional exact scenario grids only when the whole batch agrees."""
        manifest_path = directory / 'manifest.json'
        if not manifest_path.is_file():
            return
        manifest = read_json(manifest_path)
        if manifest.get('schema_version') != 2 or manifest.get('partial') is not False:
            raise ValueError('Planning grid is incomplete or uses an unsupported schema')
        if manifest.get('issue_date') != self.issue_date:
            raise ValueError('Planning grid uses a different snapshot issue date')
        expected = {name + '.json': digest(self.paths[name])
                    for name in ['simulation_calibration', 'bottlenecks', 'decision_support', 'forecasts_latest']}
        if manifest.get('input_sha256') != expected:
            raise ValueError('Planning grid sources changed; regenerate the complete grid')
        files = manifest.get('files', {})
        if set(files) != self.codes:
            raise ValueError('Planning grid cohort mismatch')
        paths = {}; availability = {}
        if manifest.get('horizon_days') != 84:
            raise ValueError('Planning grid must match the 12-week forecast horizon')
        for code, expected_hash in files.items():
            path = directory / f'{code}.json'
            if not path.is_file() or digest(path) != expected_hash:
                raise ValueError(f'Planning grid file changed or missing: {code}')
            record = read_json(path)
            if record.get('org_code') != code or record.get('issue_date') != self.issue_date:
                raise ValueError(f'Planning grid record does not match its trust or date: {code}')
            if record.get('schema_version') != 2:
                raise ValueError(f'Planning grid schema differs from the manifest: {code}')
            if record.get('input_sha256') != expected:
                raise ValueError(f'Planning grid record uses different sources: {code}')
            if record.get('status') not in {'ready', 'unavailable'}:
                raise ValueError(f'Unexpected planning grid status: {code}')
            if record['status'] == 'ready':
                if record.get('horizon_days') != 84 or record.get('day_offsets') != list(range(0, 85, 7)):
                    raise ValueError(f'Planning grid does not use the 12-week calendar: {code}')
                if not record.get('eligibility', {}).get('eligible', False):
                    raise ValueError(f'Planning grid is ready without simulator eligibility: {code}')
                if record.get('capacity_percent') != manifest.get('capacity_percent'):
                    raise ValueError(f'Planning grid doses differ from the manifest: {code}')
                if len(record.get('scenarios', [])) != 8:
                    raise ValueError(f'Planning grid shock combinations are incomplete: {code}')
            paths[code] = path
            availability[code] = dict(status=record['status'], reason=record.get('reason'), eligibility=record.get('eligibility', {}))
        self.planning_paths = paths
        self.planning_availability = availability

    @lru_cache(maxsize=16)
    def decision(self, code: str) -> dict:
        """Serve forecast-anchored plans; keep absolute simulations in Evidence."""
        absolute = self.indexes['decision_support'][code]
        fields = ['org_code', 'name', 'prior_conflict', 'acceptable_fit', 'treatment_label',
                  'treatment_label_caveat', 'bottleneck_label', 'assumptions']
        result = {**self.meta, **{key: absolute[key] for key in fields if key in absolute}}
        result['absolute_simulator_evidence'] = absolute
        # Historical six-month experiment settings belong only to the evidence.
        result['assumptions'] = {key: value for key, value in absolute.get('assumptions', {}).items()
                                 if key not in {'scenario_grid', 'experiment', 'interpretation'}}
        result['planning_consistency'] = planning_consistency(
            self.indexes['forecasts_latest'][code], absolute, self.issue_date)
        result['method'] = ('Recovery plans use the forecast for the level and the queue model '
                            'for the effect of a change, so the two never contradict.')
        grid = read_json(self.planning_paths[code]) if code in self.planning_paths else None
        if grid is None:
            result.update(status='unavailable', reason='The forecast-anchored planning grid has not been built.',
                          eligibility=dict(eligible=False, reason_codes=['planning_grid_missing'],
                              reasons=['The forecast-anchored planning grid has not been built.']))
        else:
            result.update(status=grid['status'], reason=grid.get('reason'),
                          eligibility=grid.get('eligibility', {}), planning_grid=grid,
                          horizon_days=84)
        return result

    def make_trusts(self) -> dict:
        locations = core_locations().set_index('org_code')
        result = []
        for trust in self.core.itertuples():
            code = trust.org_code
            forecast = self.indexes['forecasts_latest'][code]
            evidence = self.indexes['bottlenecks'][code]
            decision = self.indexes['decision_support'][code]
            observed = [r for r in self.backlogs[code] if r['backlog'] is not None]
            latest = observed[-1] if observed else {}
            point = next((f for f in forecast['forecasts'] if f['horizon_weeks'] == 4), {})
            result.append(dict(org_code=code, name=trust.name,
                lat=float(locations.loc[code, 'lat']) if code in locations.index else None,
                lon=float(locations.loc[code, 'lon']) if code in locations.index else None,
                map_eligible=code in locations.index,
                location_kind=locations.loc[code, 'location_kind'] if code in locations.index else None,
                latest_backlog=latest.get('backlog'), latest_observed_week=latest.get('week_ending'),
                bottleneck_label=evidence['label'], confidence=evidence['confidence'],
                evidence_status=evidence['evidence_status'],
                forecast_status=forecast['status'], growth_signal=point.get('growth_signal', 'unclear'),
                decision_status=self.planning_availability.get(code, {}).get('status', 'unavailable'), prior_conflict=decision.get('prior_conflict', False),
                treatment_label=decision.get('treatment_label', 'Treatment capacity')))
        return dict(**self.meta, trusts=result)

    def make_backlogs(self, limit: int | None = 52) -> dict[str, list[dict]]:
        """Observed history remains available when a model cannot issue a forecast."""
        frame = load_harmonized('backlog_trust')
        frame = frame.loc[frame.published_on.le(pd.Timestamp(self.issue_date))].sort_values('week_ending')
        result = {}
        for code in self.codes:
            selected = frame.loc[frame.org_code.eq(code), ['week_ending','backlog','published_on']]
            rows = records(selected.tail(limit) if limit is not None else selected)
            for row in rows:
                row['week_ending'] = row['week_ending'][:10]
                row['published_on'] = row['published_on'][:10]
            result[code] = rows
        return result

    def make_map(self) -> dict:
        """Presentation-only history and exact forecast anchors for the time map.

        No simulator result is used here. Missing observations are null, and
        the publication gap is explicit rather than being filled with forecasts.
        """
        histories = self.make_backlogs(limit=None)
        national_history = [row for row in self.national['history'] if row['week_ending'] >= '2023-04-01']
        first_week = national_history[0]['week_ending']
        latest_week = national_history[-1]['week_ending']
        end = pd.Timestamp(self.issue_date) + pd.Timedelta(weeks=12)
        weeks = [day.date().isoformat() for day in pd.date_range(first_week, end, freq='W-SUN')]
        observed_weeks = [day for day in weeks if day <= latest_week]
        fields = ['horizon_weeks', 'issue_date', 'target_date', 'latest_observation',
                  'point_forecast', 'lower_80', 'upper_80', 'last_value', 'model']
        result = []
        for trust in self.trusts['trusts']:
            code = trust['org_code']
            lookup = {row['week_ending']: row for row in histories[code]}
            history = [lookup.get(day, dict(week_ending=day, backlog=None, published_on=None))
                       for day in observed_weeks]
            forecasts = [{key: point[key] for key in fields if key in point}
                         for point in self.indexes['forecasts_latest'][code]['forecasts']]
            anchor = next((point for point in forecasts if point['horizon_weeks'] == 12), None)
            latest = trust['latest_backlog']
            threshold = max(10., .1 * latest) if latest is not None else None
            delta = anchor['point_forecast'] - latest if anchor is not None and latest is not None else None
            result.append(dict(**trust, history=history, forecasts=forecasts,
                direction=forecast_direction(forecasts, latest),
                direction_basis=dict(type='central_forecast_material_change',
                    threshold_patients=threshold, delta=delta,
                    note='Central 12-week forecast compared with the latest observed count. This is not confidence in the direction; the 80% ranges can include both rises and falls.')))
        return dict(**self.meta, history_start=first_week,
            latest_observed_week=latest_week, forecast_start=self.issue_date,
            forecast_end=end.date().isoformat(), weeks=weeks, trusts=result,
            national={**self.national, 'history': national_history},
            publication_gap=dict(start=latest_week, end=self.issue_date,
                days=(pd.Timestamp(self.issue_date) - pd.Timestamp(latest_week)).days,
                interpretation='No observed backlog is available for the gap after the latest published week.'),
            direction_rule=dict(horizon_weeks=12,
                label='Central forecast direction',
                threshold='Change greater than the larger of 10 people or 10% of the latest observed backlog.',
                interpretation='Improving or worsening describes the central 12-week estimate, not the certainty of a rise or fall. Smaller changes and unavailable forecasts are unclear. This presentation rule is separate from the four-week growth classifier.'),
            timeline_rule=dict(observed='Exact published weekly counts; missing values stay null.',
                forecast='Only the 4-, 8- and 12-week anchors are model predictions. Any animation between them is for display, not an additional weekly forecast.',
                national='Observed official England totals only. No national forecast is supplied.'))

    def make_histories(self) -> dict[str, dict]:
        # Read only the completed-pathway evidence shown by this route. Filtering
        # before harmonisation preserves the ALL CANCERS sums while avoiding a
        # full per-cancer, per-modality dataframe in every API worker.
        columns = ['org_code', 'org_name', 'period', 'published_on', 'cancer_type',
                   'd62_usc_total', *['d62_usc_' + suffix for suffix, _ in BANDS]]
        raw = pd.read_parquet(PROCESSED_DIR / 'cwt_trust_month.parquet', columns=columns,
                              filters=[('cancer_type', '=', 'ALL CANCERS')])
        frame = harmonize(raw, 'cwt_trust_month')
        frame = frame.loc[frame.published_on.le(pd.Timestamp(self.issue_date))]
        result = {}
        for code in sorted(self.codes):
            months = []
            for row in frame.loc[frame.org_code.eq(code)].sort_values('period').itertuples():
                def number(value):
                    return None if pd.isna(value) else float(value)
                bands = [dict(label=label, count=number(getattr(row, 'd62_usc_' + suffix))) for suffix, label in BANDS]
                total = number(row.d62_usc_total)
                complete = total is not None and total > 0 and all(b['count'] is not None for b in bands)
                matches = complete and abs(sum(b['count'] for b in bands) - total) < 1e-7
                months.append(dict(period=str(row.period.date()), published_on=str(row.published_on.date()),
                    total=total, bands=bands, bands_available=bool(matches)))
            result[code] = dict(**self.meta, org_code=code,
                label='Historical completed pathways; not the waiting-list age mix',
                scope='62-day urgent suspected cancer completed treatments, all cancers',
                interpretation='These patients have completed the pathway. This is not a prediction of personal waiting times or the current queue age distribution.',
                months=months, latest=months[-1] if months else None)
        return result

    def make_national(self) -> dict:
        frame = pd.read_parquet(PROCESSED_DIR / 'backlog_national.parquet')
        frame = frame.loc[frame.published_on.le(pd.Timestamp(self.issue_date))].sort_values('week_ending')
        rows = records(frame[['week_ending', 'total', 'no_dtt', 'with_dtt', 'published_on']])
        for row in rows:
            row['week_ending'] = row['week_ending'][:10]
            row['published_on'] = row['published_on'][:10]
        return dict(**self.meta, observed_only=True, history=rows, latest=rows[-1],
            model_forecasts=dict(enabled=False, reason='No validated complete-England model forecast'),
            interpretation='Official observed England backlog. National No-DTT/With-DTT is not an observed trust-level split.')

    @lru_cache(maxsize=128)
    def select_experiment(self, code: str, scenario: str, stage: str, dose: int) -> dict:
        """Return an exact 12-week paired-effect plan, never an old absolute path."""
        trust = self.decision(code)
        grid = trust.get('planning_grid')
        if trust['status'] != 'ready' or not grid:
            raise ValueError(trust.get('reason') or 'Recovery planning is unavailable for this hospital')
        key = {'baseline': 'none', 'winter_dip': 'winter', 'referral_surge': 'surge'}.get(scenario, scenario)
        selected = next((entry for entry in grid['scenarios'] if entry['key'] == key), None)
        chosen_stage = 'diagnosis' if dose == 0 else stage
        if selected is None or chosen_stage not in {'diagnosis', 'treatment'}:
            raise ValueError('That experiment has not been precomputed')
        plan = next((entry for entry in selected['plans'][chosen_stage]
                     if entry['extra_capacity_pct'] == dose), None)
        if plan is None:
            raise ValueError('That experiment has not been precomputed')
        return dict(**self.meta, org_code=code, scenario=scenario, scenario_key=key,
            stage='none' if dose == 0 else stage, extra_capacity_pct=dose,
            horizon_days=84, precomputed=True, result_kind='trajectory',
            prior_conflict=trust.get('prior_conflict', False),
            treatment_label=trust.get('treatment_label'), assumptions=grid['assumptions'],
            method=trust['method'], forecast_path=grid['forecast_path'],
            pressure_delta=selected.get('pressure_delta'),
            result={**plan, 'dates': grid['dates'], 'day_offsets': grid['day_offsets']})

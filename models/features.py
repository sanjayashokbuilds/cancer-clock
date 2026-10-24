"""As-of snapshots: release filtering happens before any monthly joins or lags."""
from __future__ import annotations

from dateutil.easter import easter
import numpy as np
import pandas as pd

from config import FORECAST_HORIZONS_WEEKS, PROCESSED_DIR, STATIC_DIR
from pipeline.common import DataError, first_release
from pipeline.universe import load_core_trusts
from pipeline.vintages import available_at

META = {'org_code', 'as_of_date', 'target_date', 'target_published_on', 'latest_observation',
        'feature_max_published_on', 'cwt_period', 'dm01_period', 'first_seen_period',
        'actual', 'log_ratio', 'growth', 'horizon_weeks', 'last_value', 'rolling_mean26',
        'history_weeks', 'recent_complete', 'feature_eligible'}
CWT = ['fds_performance', 'd62_usc_performance', 'd31_all_performance',
       'd31_surgery_performance', 'd31_radiotherapy_performance', 'd31_drugs_performance']
TEST_NAMES = {'CT':'ct', 'MRI':'mri', 'Non-obstetric ultrasound':'ultrasound',
              'Colonoscopy':'colonoscopy', 'Flexi sigmoidoscopy':'flexi',
              'Gastroscopy':'gastroscopy', 'Cystoscopy':'cystoscopy'}


def load_sources() -> dict[str, pd.DataFrame]:
    """Keep source data unchanged; models use only the explicit core trust cohort."""
    from pipeline.mergers import load_harmonized
    return {name: load_harmonized(name) for name in
            ['backlog_trust', 'backlog_national', 'cwt_trust_month', 'cwt_first_seen', 'dm01']}


def weekly_features(backlog: pd.DataFrame) -> pd.DataFrame:
    """Trailing windows never use a later observation; gaps remain NaN."""
    pieces=[]
    for code, raw in backlog.groupby('org_code', sort=True):
        raw=raw.set_index('week_ending').sort_index()
        f=raw.reindex(pd.date_range(raw.index.min(),raw.index.max(),freq='7D')).copy()
        y=f.backlog
        f['org_code']=code
        f['week_ending']=f.index
        f['published_on']=first_release(pd.Series(f.index,index=f.index))
        f['last_value']=y
        f['log_backlog']=np.log1p(y)
        f['history_weeks']=np.arange(1,len(f)+1)
        f['recent_complete']=y.rolling(9,min_periods=9).count().eq(9)
        for lag in (1,4,8,12,26):
            f[f'log_lag_{lag}']=np.log1p(y.shift(lag))
            f[f'change_{lag}']=(y-y.shift(lag))/(1+y.shift(lag))
        for window in (4,13,26):
            # 9 observed weeks permits warm-up training; evaluated cases still match Stage 2.
            mean=y.rolling(window,min_periods=min(window,9)).mean()
            f[f'mean_{window}_relative']=(mean-y)/(1+y)
            if window==26: f['rolling_mean26']=mean
        f['observed_26']=y.rolling(26,min_periods=1).count()
        f['std_26_relative']=y.rolling(26,min_periods=9).std()/(1+y)
        pieces.append(f[['org_code','week_ending','published_on','last_value','rolling_mean26',
                         'history_weeks','recent_complete','log_backlog','observed_26','std_26_relative']+
                        [f'log_lag_{k}' for k in (1,4,8,12,26)]+[f'change_{k}' for k in (1,4,8,12,26)]+
                        [f'mean_{k}_relative' for k in (4,13,26)]].reset_index(drop=True))
    return pd.concat(pieces,ignore_index=True)


def strike_calendar() -> set[pd.Timestamp]:
    """Past strike-day indicators, not assumed effects or future announcements."""
    dates=set()
    for row in pd.read_csv(STATIC_DIR/'strike_dates.csv').itertuples():
        dates.update(pd.date_range(row.start,pd.Timestamp(row.end_exclusive)-pd.Timedelta(days=1),freq='D'))
    return dates


def latest_month(frame: pd.DataFrame, issue: pd.Timestamp, code: str='org_code') -> pd.DataFrame:
    """Select the latest *published* month for each provider; preserve missing cells."""
    known=available_at(frame,issue,allow_approximate=True)
    return known.sort_values('period').drop_duplicates(code,keep='last')


def snapshot(sources: dict[str,pd.DataFrame], weekly: pd.DataFrame, issue: pd.Timestamp,
             codes: set[str], strikes: set[pd.Timestamp]) -> pd.DataFrame:
    """One feature row per core trust using data published by a single issue date."""
    f=weekly.loc[weekly.published_on.le(issue) & weekly.org_code.isin(codes)].sort_values('week_ending').drop_duplicates('org_code',keep='last').copy()
    if f.empty: return f
    f=f.rename(columns={'week_ending':'latest_observation','published_on':'feature_max_published_on'})
    f['as_of_date']=issue
    cwt=sources['cwt_trust_month'].loc[sources['cwt_trust_month'].cancer_type.eq('ALL CANCERS')]
    c=latest_month(cwt,issue)[['org_code','period','published_on']+CWT].rename(columns={'period':'cwt_period','published_on':'cwt_release'})
    f=f.merge(c,on='org_code',how='left',validate='one_to_one')
    first=available_at(sources['cwt_first_seen'],issue,allow_approximate=True).sort_values(['org_code','period']).copy()
    first['first_seen_change']=first.groupby('org_code').usc_first_seen.diff()/(1+first.groupby('org_code').usc_first_seen.shift())
    v=first.drop_duplicates('org_code',keep='last')[['org_code','period','published_on','usc_first_seen','first_seen_change']].rename(columns={'period':'first_seen_period','published_on':'first_seen_release'})
    f=f.merge(v,on='org_code',how='left',validate='one_to_one')
    f['log_first_seen']=np.log1p(f.usc_first_seen)
    f['backlog_per_100_first_seen']=100*f.last_value/f.usc_first_seen.where(f.usc_first_seen.gt(0))
    f=f.drop(columns='usc_first_seen')
    dm=available_at(sources['dm01'],issue,allow_approximate=True)
    periods=dm.groupby('org_code').period.max().rename('dm01_period')
    dm=dm.merge(periods,on='org_code')
    dm=dm.loc[dm.period.eq(dm.dm01_period)].copy()
    dm['test_key']=dm.test.map(TEST_NAMES)
    f=f.merge(periods,on='org_code',how='left',validate='one_to_one')
    for measure in ['total_waiting_list','pct_waiting_6plus','activity']:
        pivot=dm.pivot(index='org_code',columns='test_key',values=measure).reindex(columns=list(TEST_NAMES.values()))
        if measure!='pct_waiting_6plus': pivot=np.log1p(pivot)
        pivot=pivot.rename(columns=lambda k:'dm_'+k+'_'+measure)
        f=f.merge(pivot,on='org_code',how='left',validate='one_to_one')
    f['dm01_release']=first_release(f.dm01_period)
    for name in ('cwt','dm01','first_seen'):
        f[name+'_age_days']=(issue-f[name+'_period']).dt.days
        f['feature_max_published_on']=f[['feature_max_published_on',name+'_release']].max(axis=1)
        f=f.drop(columns=name+'_release')
    national=available_at(sources['backlog_national'],issue,allow_approximate=True).sort_values('week_ending')
    if national.empty: raise DataError('No published national backlog at issue')
    nat=national.set_index('week_ending').total
    nlast=float(nat.iloc[-1]); nprev=nat.get(nat.index[-1]-pd.Timedelta(weeks=8),np.nan)
    f['national_log_backlog']=np.log1p(nlast)
    f['national_change8']=(nlast-nprev)/(1+nprev)
    f['feature_max_published_on']=f.feature_max_published_on.clip(lower=national.published_on.max())
    f['lag_weeks']=(issue-f.latest_observation).dt.days/7
    f['strike_days_past28']=sum(issue-pd.Timedelta(days=28)<s<=issue for s in strikes)
    f['feature_eligible']=f.recent_complete & f.rolling_mean26.notna() & f.last_value.notna()
    return f


def calendar_features(f: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Future calendar is deterministic; no future activity or strike data is used."""
    f=f.copy(); f['horizon_weeks']=horizon
    f['target_date']=f.as_of_date+pd.Timedelta(weeks=horizon)
    f['target_published_on']=first_release(f.target_date)
    f['observation_horizon_weeks']=f.lag_weeks+horizon
    for name,col in [('target','target_date'),('observed','latest_observation')]:
        day=f[col].dt.dayofyear
        f[name+'_sin']=np.sin(2*np.pi*day/365.25)
        f[name+'_cos']=np.cos(2*np.pi*day/365.25)
        f[name+'_christmas']=((f[col].dt.month.eq(12)&f[col].dt.day.ge(18)) | (f[col].dt.month.eq(1)&f[col].dt.day.le(7))).astype(float)
    f['season_sin_change']=f.target_sin-f.observed_sin
    f['season_cos_change']=f.target_cos-f.observed_cos
    f['christmas_change']=f.target_christmas-f.observed_christmas
    easters=pd.to_datetime(f.target_date.dt.year.map(lambda year:easter(int(year))))
    f['target_easter']=((f.target_date-easters).dt.days.abs()<=7).astype(float)
    return f


def build_panel(sources: dict[str,pd.DataFrame], issues: pd.DatetimeIndex,
                codes: set[str] | None=None) -> tuple[pd.DataFrame,list[str]]:
    """Build immutable historical snapshots; attach outcomes only after features."""
    codes=codes if codes is not None else set(load_core_trusts().org_code)
    weekly=weekly_features(sources['backlog_trust'])
    strikes=strike_calendar(); frames=[]
    for issue in issues:
        base=snapshot(sources,weekly,pd.Timestamp(issue),codes,strikes)
        if base.empty: continue
        frames.extend(calendar_features(base,h) for h in FORECAST_HORIZONS_WEEKS)
    panel=pd.concat(frames,ignore_index=True)
    targets=sources['backlog_trust'][['org_code','week_ending','backlog']].rename(columns={'week_ending':'target_date','backlog':'actual'})
    panel=panel.merge(targets,on=['org_code','target_date'],how='left',validate='many_to_one')
    panel['log_ratio']=np.log1p(panel.actual)-np.log1p(panel.last_value)
    panel['growth']=panel.actual.gt(panel.last_value).astype(float).where(panel.actual.notna())
    columns=[c for c in panel if c not in META]
    if any(not pd.api.types.is_numeric_dtype(panel[c]) for c in columns):
        raise DataError('A nonnumeric or metadata column entered the feature matrix')
    if not panel.feature_max_published_on.le(panel.as_of_date).all():
        raise DataError('Future release leaked into a feature snapshot')
    return panel,columns


def training_rows(panel: pd.DataFrame, issue: pd.Timestamp, horizon: int) -> pd.DataFrame:
    """No target can train before publication, even if its observation date is past."""
    return panel.loc[panel.horizon_weeks.eq(horizon) & panel.as_of_date.lt(issue)
        & panel.target_published_on.le(issue) & panel.actual.notna() & panel.feature_eligible].copy()

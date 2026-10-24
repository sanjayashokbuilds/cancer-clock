"""Plot observed Oxford series, keeping different time scales and units separate."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from pipeline.common import DataError


def plot_oxford(data: dict[str, pd.DataFrame], destination: Path) -> None:
    """Create the requested RTH chart from data only; visibly label the volume proxy."""
    backlog = data['backlog_trust'].query("org_code == 'RTH'").sort_values('week_ending')
    seen = data['cwt_first_seen'].query("org_code == 'RTH'").sort_values('period')
    dm = data['dm01'].query("org_code == 'RTH'")
    if backlog.empty or seen.empty or dm.empty:
        raise DataError('RTH is missing from a required source; cannot produce the Oxford chart')
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True, layout='constrained')
    fig.suptitle('Oxford University Hospitals (RTH) | published observations', fontsize=17, fontweight='bold')
    axes[0].plot(backlog.week_ending, backlog.backlog, color='#155e75', linewidth=2)
    axes[0].set_title('Cancer patients still waiting beyond 62 days · weekly', loc='left', fontsize=12)
    axes[0].set_ylabel('Patients')
    axes[1].plot(seen.period, seen.usc_first_seen, color='#7c3aed', linewidth=2, marker='.', markersize=4)
    axes[1].set_title('Urgent suspected cancer first attendances · monthly volume proxy, not referrals received', loc='left', fontsize=11)
    axes[1].set_ylabel('Attendances')
    for test in ['CT', 'Colonoscopy', 'Flexi sigmoidoscopy', 'Gastroscopy', 'Cystoscopy']:
        series = dm.loc[dm.test.eq(test)].sort_values('period')
        axes[2].plot(series.period, series.pct_waiting_6plus, label=test, linewidth=1.7)
    axes[2].set_title('Diagnostic waiting lists: share waiting 6+ weeks · includes non-cancer demand', loc='left', fontsize=11)
    axes[2].set_ylabel('Percent (%)')
    axes[2].legend(loc='upper left', ncol=3, fontsize=9)
    axes[2].xaxis.set_major_locator(mdates.MonthLocator(interval=4))
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    for axis in axes:
        axis.grid(alpha=0.2)
        axis.spines[['top', 'right']].set_visible(False)
        axis.set_ylim(bottom=0)
    fig.supxlabel('Observation period · published later; latest revised releases · source: NHS England', fontsize=10)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=160)
    plt.close(fig)

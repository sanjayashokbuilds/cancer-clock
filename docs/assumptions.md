# Assumptions and limits

- First release is approximated by month +2/day14; latest revised values are used.
  Original historical vintages are unverified. Every fitted value obeys its release cutoff.
- The 130-trust current acute/specialist cohort and four mergers use retrospective
  organisation knowledge. This is not an as-was historical deployment test.
  Independent/community-only providers are excluded; source tables remain raw.
- The 50:50 blend was **selected post-hoc on the back-test**. Bootstrap intervals
  handle within-trust dependence, not shared shocks or selection uncertainty.
  Large-swings membership depends on future outcomes.
- Forecast intervals are empirically calibrated, not guaranteed. Early training
  can use 9–25 observed weeks; scored cases require 26-week history. Interval
  warm-up uses baseline widths. Zero-scale MASE cases are counted separately.
- Four-week growth categories are experimental; 0.4/0.6 thresholds are assumed.
  Numeric probabilities and longer-horizon categories are not displayed.
- Bottleneck thresholds/shrinkage are screening rules. FDS measures completed
  pathways; DM01 includes non-cancer demand and repeat waiting-list snapshots.
  Clinical review is pending; neither supplies causal capacity estimates.
- Simulation uses first attendances as an arrival proxy and unmatched 62D-treated
  / first-attendance counts as conversion. Fractional queues, age mix, 14-day
  diagnosis eligibility, proportional service and uniform weekends are assumed.
- Only total >62-day backlog is fitted. Two capacities, stage split and age mix
  are not jointly identified. >104-day counts and the publication-gap nowcast
  are modelled, not observed. Fit error is in-sample; prior conflicts are exposed.
- Poisson arrivals and daily lognormal service sigma 0.05 give conditional process
  ranges, not validated predictive intervals or parameter uncertainty. Strike
  factor 0.952 is editable and unverified as a trust-level cancer effect.
- Recovery is measured after the post-shock excess peak, within max(5 patients,
  5% baseline) for 14 days. Non-recovery is censored at the horizon.
- No personal waiting-time, lives-saved or causal recovery claims. National
  model forecasts remain withheld. Every scenario includes parameter provenance.

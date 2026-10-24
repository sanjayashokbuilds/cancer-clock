# Daily two-stage simulator

Stage 5 process-only method below. Stage 7–8 adds a fit-informed parameter
ensemble and paired dose-response; see `uncertainty.md` and `stage_8.md`.

`sim/simulator.py` tracks fractional patient mass in diagnosis and treatment
queues by total **days since referral**. Diagnosis transfer never resets age.
Count >62 from day 63 and >104 from day 105; retain all older mass in a 365+ bin.
Each day: age queues, add arrivals, serve existing treatment, serve diagnosis,
move the converted fraction to treatment; the rest exits with no treatment.
Newly diagnosed patients cannot finish treatment on the same day.

Arrivals are completed first attendances divided by calendar days, a proxy for
unobserved referrals. Conversion is pooled 62D USC treatments / first attendances
from at least two matching recent months; these are unmatched cohorts. Invalid
ratios are unavailable, not silently clipped. Service is proportional across
eligible age groups, with an assumed 14-day minimum before diagnosis service.

## Calibration and identifiability

Use the latest 13 published weekly backlog points (≥10 observed, both endpoints
required). Fit two constant effective daily service budgets by bounded least
squares, ratios 0.4–1.8 of estimated incoming stage flow. Match total >62 backlog;
initial exponential age shapes exactly match its first value, with an assumed
diagnosis share 0.70 / 0.30 / 0.50 for diagnosis / treatment / mixed-or-unclear.
Corroborated cancer types add 0.05 to diagnosis/mixed shares; partial evidence
uses 0.50. Capacity-ratio prior centres are 0.98/1.02 for diagnosis-limited,
reversed for treatment-limited, otherwise 1/1, with weak penalty 0.15.

**Neither the age mix, split nor two capacities is uniquely identified.** Of
130 trusts, 124 fit; 122 meet the assumed normalised RMSE ≤0.30 threshold
(denominator max(mean observed backlog,10)). All optimizers converged; nine fits
reach a capacity bound and 29 contradict the prior's ordering. Both are flagged.

| In-sample fit error | 10th percentile | Median | 90th percentile | Maximum |
| --- | ---: | ---: | ---: | ---: |
| MAE, patients | 2.39 | 5.51 | 11.93 | 33.37 |
| RMSE, patients | 3.18 | 6.73 | 16.05 | 49.17 |
| Normalised RMSE | 0.038 | 0.076 | 0.156 | 0.353 |

Poor fits: RGR (0.311), RJ6 (0.353). Unavailable: RBD/RJ2 (missing monthly proxy),
RBV/REN (invalid flow ratio), RET (too few conversion months), RGM (missing flow).
Individual curves, parameters and reasons are in `simulation_calibration.json`.
These are in-sample fits, not future validation or evidence that a plan will work.

## Experiments and ranges

Bridge the 49-day publication gap from 30 August to issue 18 October 2026 using
latest flow proxies; the issue queue is an unobserved nowcast. Hold future rates
constant except editable shocks. Use 256 draws (allowed 200–500), Poisson arrivals
and mean-one daily lognormal service noise sigma 0.05. Pair identical random draws
across baseline, strike, extra diagnosis/treatment capacity, winter and surge plans.

Default horizon is 182 days. Shocks/interventions start day 28: five strike days
at 0.952 capacity, six winter weeks at −10%, four surge weeks at +20%, or permanent
+10% capacity in one stage. All are assumptions, including the strike factor.
Report weekly trajectories, daily peaks, >104-day changes and backlog patient-days.
Recovery starts after shock end **and the post-shock excess peak**, within
max(5 patients, 5% baseline) for 14 days. Time is measured from shock end;
non-recovery is censored. A shock always below tolerance has zero recovery time.

Every plan includes its assumptions object. The 10–90% ranges represent chosen
process noise, excluding parameter/structural uncertainty. >104-day counts are
generated from unobserved age assumptions. Simulator baselines can differ from
Stage 3 forecasts; do not present them as validated forecasts or causal rankings.

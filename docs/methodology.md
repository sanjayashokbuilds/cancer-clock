# Methodology status

Stage 0 has no analytical implementation or numerical findings.

The planned outcome is the number of people still waiting beyond 62 days at
trust level. Completed-pathway performance percentages are different measures.
Do not label this overdue count as the entire waiting list.

Before Stage 2, resolve the forecast time axis. If the latest observation is
dated `t`, the forecast is issued on date `a`, and its horizon from observation
is `h` weeks, the target is `t + h`, and its lead from issue is `(t + h) - a`.
Publication lag therefore SHORTENS that lead. Illustration only: with a
7-week lag, horizons of 4, 8 and 12 weeks from observation correspond to -3,
1 and 5 weeks from issue. The negative lead is retrospective estimation of an
unpublished outcome, not a future forecast. For an 8-week forecast from today,
the model must reach 8 weeks plus the observation lag from its last observation.
Report observation date, issue date, target date and both horizons explicitly.

Before calling an evaluation vintage-safe, retain the values actually released
at each historical origin as well as their release dates. Latest revised files
with estimated release dates support only an approximate availability-aware
evaluation. Choosing Final over Provisional for current analysis does not make
Final values available to past forecast origins. Training labels must also have
been published by the training cutoff.

The proposed 10th, 50th and 90th quantiles alone do not uniquely determine a
probability of growth. A later stage must define and validate a probability
estimator or omit that probability. Handle zero backlogs before using log ratios;
do not silently divide by zero or exclude zero-valued trusts.

Per-trust total backlog cannot uniquely identify two stage-specific capacities
or the hidden age distribution. A fitted scenario engine will need explicit
assumptions and sensitivity analysis; a good historical fit does not validate
causal recommendations or estimates of currently waiting patients over 104 days.

# Bottleneck screening method

These labels describe relative pressure in aggregate measures. They do not
identify why cancer patients are delayed or estimate spare capacity.

## Window and references

Filter every source to `published_on <= as_of`. Use the latest common CWT/DM01
month and its two preceding calendar months. Do not substitute old months for a
trust with missing recent data. Keep all 133 core trusts, with explicit evidence status.

FDS uses ALL CANCERS / ALL ROUTES. Treatment uses ALL CANCERS / ALL STAGES / each
of surgery, radiotherapy and anti-cancer drugs. Compare count-weighted performance
with published England CWT totals for the same scope and available months.

DM01 compares each test's six-week-wait proportion separately. The reference
uses full provider–commissioner extracts, excludes `NONC` (non-English
commissioners), and includes all NHS-funded reporting providers. Only core trusts
receive labels. Count commissioners once; exclude CDC-only extracts. Missing
counts propagate, never become zero. The original Stage 3 DM01 snapshot is
preserved for reproducibility; Stage 4 uses a separate English-scope reference.

For each component pool numerator/denominator across matching valid months;
never average percentages. CWT volume is completed pathways. DM01's pooled
denominator is patient-months: its **minimum monthly list**, not the sum, is used
for evidence strength because patients can recur across snapshots.

## Explicit assumed rules

Require at least two usable months and volume >=100 for FDS, >=30 per treatment
modality, or minimum monthly list >=100 for a diagnostic test. A bad gap is
England minus trust performance for CWT; trust minus England six-week waits for DM01.

Shrink positive gaps towards zero by `volume / (volume + 100)`. A component
scores zero unless at least two months are worse than England. Diagnosis score
is the larger of FDS and the mean of the two highest eligible DM01 scores (one
if only one qualifies). Treatment score is the largest eligible modality score.
Both scores use percentage points. The 5-point signal threshold gives the four
labels: diagnosis-limited, treatment-limited, mixed, or no clear bottleneck.

Confidence means heuristic evidence strength. Medium: a qualifying signal.
High: three adverse months, effective volume >=200 and side score >=10 points;
diagnosis also requires an FDS signal. Mixed takes the weaker side. Missing a
whole side caps confidence at low and sets `partial_evidence`; missing both sets
`insufficient_data`. No clear signal has low confidence. A high score does not
mean a high probability of a causal bottleneck. These thresholds need Rounak's
clinical review and have not been fitted to outcomes.

National No-DTT/With-DTT counts are displayed only as observed national context;
they never enter a trust score or supply a fabricated trust split. All labels
retain `approximate: latest revised values`. Case mix, referral networks and
DM01's non-cancer demand can explain differences; above-average FDS alongside
poor DM01 waits is explicitly flagged.

Sources: [CWT definitions](https://www.england.nhs.uk/long-read/national-cancer-waiting-times-monitoring-dataset-guidance/),
[DM01 FAQs, including NONC and repeated diagnostic clocks](https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/01/DM01-FAQs-v5.pdf).
Per-file URLs and hashes remain in the bundled inputs and source manifest.

# Bottleneck screening method

Use the latest three common published CWT/DM01 months, with each source filtered
to `published_on <= as_of`. Use all 130 current acute/specialist core trusts and
merged counts; missing recent evidence stays explicit. This screens relative
pressure, not causes or spare capacity. Rounak's clinical review is pending.

Diagnosis drivers are **cancer-type-specific FDS**, ALL ROUTES. Exclude pooled
ALL CANCERS, missing types and breast symptoms not suspected cancer. Treatment
drivers are **31D by surgery, radiotherapy and anti-cancer drugs**, ALL CANCERS /
ALL STAGES. Compare against matching England types/modalities and matching months.
Pool numerators and denominators; never average percentages.

Require ≥2 valid months, completed volume ≥100 for FDS or ≥30 for treatment,
and ≥2 months worse than England. Shrink the adverse pooled gap by
`volume / (volume + 100)`. Each side's score is its largest qualifying gap;
≥5 percentage points signals that side. Both sides imply mixed; show both top
drivers. Confidence is heuristic: high requires three adverse months, volume
≥200 and gap ≥10 points; otherwise a signal is medium. Missing a whole side
caps strength at low. No clear signal is not evidence of adequate capacity.

**DM01 never drives a label.** Each test is context, using its six-week-wait
fraction and matching England reference. A context is corroborated only if both
it and a linked FDS pathway meet the adverse-gap/volume/persistence rules:

| Diagnostic test | Matching FDS pathway |
| --- | --- |
| Colonoscopy / flexi sigmoidoscopy | Lower gastrointestinal |
| Gastroscopy | Upper gastrointestinal |
| Cystoscopy | Urological, excluding testicular |
| CT | Lung, lower/upper GI, urological |
| MRI / non-obstetric ultrasound | Broad non-cancer demand; no specific corroboration assigned |

English DM01 counts exclude NONC commissioners, include NHS-funded independent
care in the England reference, and retain raw predecessor counts for merger
harmonisation. Repeated monthly waiting lists are not unique people: use the
minimum monthly list (≥100) for shrinkage/strength; pooled counts supply the rate.
Uncorroborated means no qualifying linked adverse pair, not proof of no connection.

RTH/RRK gastroscopy and RJ1/RM1 cystoscopy are uncorroborated because the matching
FDS pathway outperforms England. R0A's lower GI FDS is **59.2% vs 67.4%, n=1,926**
and qualifies; its largest signal is sarcoma. National No-DTT/With-DTT remains
context only, never an observed trust split.

Definitions: [NHS CWT guidance](https://www.england.nhs.uk/long-read/national-cancer-waiting-times-monitoring-dataset-guidance/),
[DM01 FAQs](https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/01/DM01-FAQs-v5.pdf).

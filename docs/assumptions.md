# Assumptions register

Stage 1 verifies actual CWT, backlog and DM01 source files. Publication timing and causal capacity effects remain assumptions.
`config.py` contains proposed defaults with provenance, status and caveats.

| Proposed default | Status | Limitation |
| --- | --- | --- |
| Observation month + 2 months for release | Assumed from brief | Must verify actual release dates where possible |
| Day 14 of release month | Assumed from brief | May precede actual publication; not guaranteed conservative |
| Strike capacity multiplier 0.952 | Assumed from brief | A national activity ratio is not a trust-level cancer capacity estimate |

Additional decisions for later stages:

- Current revised data cannot stand in for original historical vintages without
  clearly disclosing the limitation.
- DM01 includes non-cancer demand. Poor diagnostic waits suggest pressure; they
  do not establish the cause of a particular cancer backlog.
- Treated patients and referrals in one calendar month are not the same cohort.
  Their ratio is at most a rough conversion assumption, not a measured patient
  transition probability; transfers and referral-route differences also matter.
- National No-DTT/With-DTT proportions must not be presented as measured trust
  proportions. Any use in a trust simulator must be an explicit assumption.
- A coarse weekly age bucket cannot classify the 62- and 104-day boundaries
  exactly. Specify a boundary convention or retain day-level age information.
- Strike dates and strike-capacity effects remain unverified. Organisation
  coordinates are sourced through ODS/postcodes.io when available; unresolved
  coordinates remain blank. No invented coordinates are supplied.

No API keys are required or read by Stage 1. Later integrations must be
optional and keep secrets in an excluded `.env` or environment variables.

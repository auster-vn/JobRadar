# Third-party data and attribution

This file inventories third-party datasets bundled in the repository. It does
not replace the upstream licenses stored under `licenses/` or grant a license to
unrelated JobRadar source code.

## VietJobs salary observations

The compact salary baseline in
`data/vietjobs_it_salary_observations.csv` is derived from the
[VinNLP VietJobs dataset](https://github.com/VinNLP/VietJobs) mirrored as
`dinhieufam/VietJobs`, pinned at revision
`ea140511b77935704e93d21c2973b72f46d48902`. The upstream project is licensed
under MIT; its license is retained in `licenses/VietJobs-MIT.txt`.

The tracked derivative contains 1,115 observations and has SHA-256
`f823fdb009c69ff9a2e8a367497936fcd7001adcfa60bc4dc0784d6c55ff357c`.
Each row preserves the dataset name, pinned revision and license in
`source_metadata`. The upstream CSV does not provide a record-level posting
date, so JobRadar treats the derivative as one October 2025 snapshot and never
infers extra monthly history from the publisher's collection range. The 99 MB
upstream CSV and local training artifacts are not committed.

## TopCV 2026 IT salary observations

The compact snapshot in `data/topcv_2026_it_salary_observations.csv` is a
modified derivative of
[`baocgb/vietnam-it-jobs-raw-data-from-topcv-2026`](https://www.kaggle.com/datasets/baocgb/vietnam-it-jobs-raw-data-from-topcv-2026),
published by Kaggle user `baocgb` under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The attribution and
change notice is retained in `licenses/TopCV-Kaggle-CC-BY-4.0.txt`.

Dataset version 1 (`Kaggle dataset ID 9263561`) contains 1,550 IT job rows. Its
raw CSV has SHA-256
`e78ff2b6ed521ad894a70271a3254fcf434813916fdade4f7d449bc4fdf34ef9`.
JobRadar retains 818 rows with disclosed monthly salary inside the model's
1-200 million VND contract, converts 30 USD-denominated rows at the documented
fixed rate of 25,000 VND/USD, normalizes title, experience and location, removes
tracking parameters from source URLs, and keeps the supplied posting dates from
2025-12-16 through 2026-01-15. Four parsed values outside the monthly contract
are excluded rather than repaired or clipped.

The tracked derivative has SHA-256
`977b7da686d78e507b8424a28210d7746bfb3bb20acec1e0920cc1165de1be4e`.
Every row records the upstream dataset, version, raw hash, license, canonical
source URL, original salary currency and normalizer revisions in
`source_metadata`. The raw Kaggle CSV is not committed. Reproduction requires
the exact raw file and `scripts/export_topcv_salary_snapshot.py`; the exporter
fails if its SHA-256 differs.

## MIND technology ontology

The expanded technology taxonomy includes a modified snapshot of the
[MIND Tech Skills & Concepts Ontology](https://github.com/MIND-TechAI/MIND-tech-ontology),
copyright 2025 or-mihai-or-gheorghe, used under the MIT License. Its license is
retained in `licenses/MIND-tech-ontology-MIT.txt`. JobRadar keeps its original
canonical labels first, removes ambiguous aliases, and projects the upstream
ontology into the smaller `name/category/aliases/language/related` contract.
The exact upstream revision and resulting count are recorded in
`nlp/skills_taxonomy.meta.json`.

## Operational source data

JobRadar does not bundle its own raw archive of ITViec, TopCV, VietnamWorks or
LinkedIn postings. The compact TopCV salary derivative above is distributed
only under its upstream dataset attribution; that license does not grant rights
to unrelated live postings. Source adapters are disabled by default and collect
only when the operator enables a source after a current access-policy review.
Robots rules, source throttling, fail-closed validation and deletion requests
remain operational obligations.

O*NET and other historical salary sources were evaluated but are not bundled.
Rejection rationale and data-admission requirements are recorded in
`docs/operations.md` and `docs/completion_audit.md`.

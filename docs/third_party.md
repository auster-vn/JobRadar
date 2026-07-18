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

JobRadar does not bundle a redistributable archive of ITViec, TopCV,
VietnamWorks or LinkedIn postings. Their adapters are disabled by default and
collect only when the operator enables a source after a current access-policy
review. Robots rules, source throttling, fail-closed validation and deletion
requests remain operational obligations; the repository's third-party dataset
licenses do not grant rights to those live postings.

O*NET and other historical salary sources were evaluated but are not bundled.
Rejection rationale and data-admission requirements are recorded in
`docs/operations.md` and `docs/completion_audit.md`.

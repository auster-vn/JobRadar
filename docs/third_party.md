# Third-party Data and Attribution

This inventory covers third-party data distributed in compact form with the
repository. It records provenance and transformations; it does not grant a
license to unrelated JobRadar code or make rights claims where the upstream
source did not publish one.

## VietJobs Salary Observations

`data/vietjobs_it_salary_observations.csv` is derived from the
[VinNLP VietJobs project](https://github.com/VinNLP/VietJobs) and its
[`dinhieufam/VietJobs`](https://huggingface.co/datasets/dinhieufam/VietJobs)
dataset repository, pinned at repository revision
`ea140511b77935704e93d21c2973b72f46d48902`. The upstream project declares MIT;
the retained notice is `licenses/VietJobs-MIT.txt`.

The raw `VietJobs.csv` used for export has SHA-256
`85862b06fda4e814fe0c1d8622f173d189c92758345f77df16d1232d0c49d477`.
The 1,115-row derivative has SHA-256
`f823fdb009c69ff9a2e8a367497936fcd7001adcfa60bc4dc0784d6c55ff357c`.
It contains only IT rows with valid disclosed monthly salary. Because the raw
CSV has no record-level posting date, every row is treated as one 2025-10-31
snapshot; the publisher's broader collection range is not expanded into
invented monthly observations.

## TopCV Kaggle Salary Observations

`data/topcv_2026_it_salary_observations.csv` is a modified derivative of
[`baocgb/vietnam-it-jobs-raw-data-from-topcv-2026`](https://www.kaggle.com/datasets/baocgb/vietnam-it-jobs-raw-data-from-topcv-2026),
Kaggle dataset ID 9263561, version 1. The dataset page declares
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); attribution and the
change notice are retained in `licenses/TopCV-Kaggle-CC-BY-4.0.txt`.

The raw 1,550-row CSV has SHA-256
`e78ff2b6ed521ad894a70271a3254fcf434813916fdade4f7d449bc4fdf34ef9`.
JobRadar retains 818 valid salary rows dated 2025-12-16 through 2026-01-15.
Thirty USD ranges are converted at the documented fixed rate of 25,000 VND/USD;
four values outside the 1-200 million VND monthly contract are excluded. The
derivative SHA-256 is
`977b7da686d78e507b8424a28210d7746bfb3bb20acec1e0920cc1165de1be4e`.

## Canhphu TopCV Archive

`data/topcv_canhphu_2026_salary_observations.csv` is derived from seven dated
CSV snapshots in
[`canhphu/job_prediction`](https://github.com/canhphu/job_prediction), pinned at
Git commit `5cce1ddf501ae3e8ddfce046f3b82a1990570eeb`. The snapshots cover crawler runs
from 2026-05-18 through 2026-06-21. Every raw filename and SHA-256 is pinned in
`api/services/canhphu_topcv_salary_import.py`.

The upstream repository does not assert a dataset license, so each of the 744
retained observations records `license=NOASSERTION`. Natural source IDs are
SHA-256 hashes of case-folded title, company and primary location; repeated
records across snapshots retain the earliest dated observation. The compact
derivative SHA-256 is
`0d8dc1cfa6d48d96e803d55781fdc5757ef763e54b340d5e670601d6189080ee`.

## Operational TopCV and VietnamWorks Snapshots

Two compact derivatives preserve disclosed salary rows collected by JobRadar
before the publication holdout was frozen:

- `data/topcv_operational_2026-07-18_salary_observations.csv`: 180 rows,
  SHA-256
  `97a09d0d8470f31436bf741e8a89d02ba268ef146ad2e8f2d0dd61a022a21575`;
- `data/vietnamworks_operational_2026-07-18_salary_observations.csv`: 172 rows,
  SHA-256
  `d99d899d4cfbda63d9d6d03dc37263d03e5dbde071ad9a017e544d4702634478`.

Rows include the stable platform ID, canonical source URL, company, first-seen
batch ID and timestamp, latest normalized raw-payload SHA-256, source posting
date and normalizer revisions. The cutoff is
`2026-07-19T04:36:28.244910+00:00`. Fifteen TopCV IDs already present in the
Kaggle derivative are excluded. The exporter is
`scripts/export_operational_salary_snapshot.py`.

These source pages did not provide a reusable dataset license, so the compact
metadata records `NOASSERTION`. The repository retains the derivatives for
reproducible personal research; downstream redistributors must perform their
own source-terms review.

## Frozen TopCV Publication Cohort

`data/topcv_2026-07-19_it_salary_observations.csv` contains 179 first-seen TopCV
salary rows from the broad public IT route. It was frozen after the cutoff above
and after excluding nine IDs already present in the older TopCV derivative. Its
SHA-256 is
`33f0ffc88415a05db9dc4e02ce18370aca84e57d2291f2320a677d1f7d37368b`.

`data/salary_holdout_2026-07-19.json` pins all source keys, the completed batch
`eb00da89-c02b-49d1-be3e-68d7a3946c50`, the snapshot hash and first-seen cutoff.
Its SHA-256 is
`fb1a91a94f9f67744971f51b61bcd5ed39226d7caf587a4bd567fa1a2875714c`.
Each row carries `NOASSERTION`, source URL, scrape timestamp, batch ID and raw
payload SHA-256.

## MIND Technology Ontology

The expanded taxonomy contains a modified snapshot of the
[MIND Tech Skills & Concepts Ontology](https://github.com/MIND-TechAI/MIND-tech-ontology),
copyright 2025 or-mihai-or-gheorghe, under MIT. Its notice is retained in
`licenses/MIND-tech-ontology-MIT.txt`. The exact revision and resulting count
are recorded in `nlp/skills_taxonomy.meta.json`.

## Raw Operational Data

The repository does not bundle full raw HTML/JSON archives of live source
postings or candidate data. PostgreSQL retains operational raw payloads while a
collector is running; the compact salary derivatives retain hashes and the
minimum normalized fields needed for reproducible training. Collection remains
robots-aware, throttled and fail-closed on schema or access changes.

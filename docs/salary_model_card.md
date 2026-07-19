# Salary Model Card

- Last candidate evaluation: 2026-07-18
- Last development diagnosis: 2026-07-19
- Last data-readiness audit: 2026-07-19

## Status

`REJECTED` - not available for serving.

Publication requires both MAPE at or below 15% on an individual salary midpoint
evaluation set excluded from fitting and train-only model selection, and a
passing automated data-readiness report. The latest candidate records MAPE
33.78%, so the API
continues to return observed market quantiles with source and period provenance.

## Intended Use

The model estimates monthly VND salary midpoint, P25 and P75 from job title,
level, location, experience and skills. It is intended to support aggregate
Vietnamese technology-market exploration. It is not suitable for compensation
decisions about an individual, employment screening, or protected-attribute
inference.

## Data

- 1,115 licensed historical observations from the October 2025 VietJobs snapshot.
- 172 valid disclosed VietnamWorks salaries dated June-July 2026.
- 1,287 total rows; 1,115 training and 172 temporal evaluation rows.
- The currently admissible retraining pool additionally includes 818 dated
  TopCV IT salary observations from a provenance-pinned CC-BY-4.0 derivative.
  Fifteen source IDs overlap salary-bearing live TopCV jobs and are merged, not
  counted twice. This pool was audited for readiness but was not used to replace
  the recorded candidate or consume a new final holdout.
- Required-experience units are normalized before import; the latest snapshot
  corrected 281 rows that previously treated months or no requirement as years
  or missing values.
- Context-constrained bilingual extraction recovered experience for 327 of 462
  VietnamWorks jobs and 133 of 172 salary-bearing holdout jobs without treating
  calendar years or salary numbers as tenure.
- The source category includes adjacent design and software-sales roles. The
  current canonical technical-role taxonomy maps 401 rows.
- Snapshot import always re-derives title and level from raw title text and
  records title-normalizer revision
  `2f434fba22de3a14c1b199331c8ca18408dc72e702071bf4bbfe380daff40f58`;
  stale derived fields cannot silently survive a re-import.
- The historical source has no posting timestamp. VietnamWorks rows beginning
  2026-06-15 were excluded from fitting and model selection for the recorded
  candidate evaluation. They have since been reused for post-rejection
  diagnosis, so a future publication attempt must use a newly frozen period.

VietJobs itself documents salary variability, source bias and duplicated or
templated descriptions as limitations. Its strongest reported fine-tuned salary
experiment still explains a limited portion of salary variance. See the
[VietJobs paper](https://arxiv.org/abs/2603.05262).

## Method

- Stable source-key 80/20 split; complete-date temporal splitting is preferred
  automatically when both partitions meet minimum sizes.
- Training-only character TF-IDF over raw plus canonical titles, TF-IDF for
  skills, one-hot level, location and canonical role, and numeric experience.
- Regularized XGBoost mean, Q25 and Q75 objectives trained on log salary. Title
  representation, canonical-role feature and tree regularization were selected
  using three historical train-only folds before the evaluation run. The role
  feature reduced mean fold MAPE from 28.83% to 28.73%.
- Q25 and Q75 receive train-only three-fold out-of-fold residual calibration;
  the evaluation holdout does not influence the interval corrections.
- Encoder and all three Boosters are serialized and must reproduce predictions
  after reload before an MLflow run can be logged.
- A separate inference service loads only a complete `current` bundle whose
  metadata is `published`, whose finite MAPE is at most 15%, and whose data
  readiness report explicitly passes.

## Latest Evaluation

| Metric | Candidate | Gate or interpretation |
|---|---:|---|
| MAPE | 33.78% | Must be at most 15% |
| Median-baseline MAPE | 43.60% | Candidate beats baseline but misses publication gate |
| MAE | 11,999,254 VND | Diagnostic |
| R2 | -0.1131 | Diagnostic |
| P25-P75 coverage | 36.05% | Temporal under-coverage |

Calibration offsets are -297,507 VND for P25 and +539,345 VND for P75. MLflow
run: `b4d7b96c9ed2449484411cfdf278a6ba`, tagged with source revision
`b6ae6418eb661cf19fbcff7f61b58a6995db8544`. The compact
[machine-readable evaluation](evidence/salary_evaluation.json) is the input to
the main-branch publication job.

### Holdout Diagnostics

| Diagnostic | Value | Interpretation |
|---|---:|---|
| Predictions within 15% | 27.91% | Most individual estimates remain outside the publication tolerance |
| P90 absolute percentage error | 64.71% | The upper error tail is too large for serving |
| Median percentage bias | -18.86% | The candidate systematically underpredicts the current holdout |
| Actual salary median | 27,500,000 VND | June-July 2026 holdout |
| Predicted salary median | 21,304,422 VND | 6,195,578 VND below the actual median |
| Exact normalized titles unseen in train | 69.77% | Improved coverage, but substantial cross-source vocabulary drift remains |
| Locations unseen in train | 4.65% | Location coverage is not the primary failure mode |

Only titles with at least three holdout rows are reported in the artifact. Their
MAPE ranges from 18.72% for `Backend Developer` to 42.40% for
`Business Analyst`; even the best supported reported segment misses the 15%
gate. These diagnostics are computed strictly after prediction, stored in the
candidate metadata and MLflow artifact, and never feed feature fitting,
selection, calibration or publication decisions.

The temporal result confirms that the October 2025 snapshot does not generalize
to June-July 2026 salaries. Segment-level aggregation can produce a lower number
but is not substituted for the specified row-level gate.

### Development Diagnosis After Rejection

On 2026-07-18, the robots-aware VietnamWorks adapter returned 414 current jobs
across ten pages, of which 152 had valid disclosed salaries dated 2026-06-18
through 2026-07-17. A development-only experiment joined those rows to the
pinned 1,115-row snapshot and compared objectives using three-fold
training-side cross-validation before evaluating the current period. The best
all-role objective measured 28.62% CV MAPE and 32.47% current-period MAPE.
Restricting the scope to 396 canonical technical rows still produced 28.78%
current-period MAPE.

These results are not a replacement candidate or publication evidence. They
show that objective selection and canonical-role filtering do not close the
accuracy gap with the available history. They also make the inspected
June-July period development validation data; it must not be represented as an
untouched holdout in a subsequent model publication.

After adding the licensed TopCV history, a second development-only check on
2026-07-19 excluded every observation on or after 2026-07-11 before any model
fit or metric inspection. The resulting 2,162-row pool used a complete-date
temporal split at 2026-01-09: 1,723 fitting rows and 439 validation rows. It
measured 32.82% MAPE, 8,094,537 VND MAE and 0.2743 R2, versus 58.05% MAPE for
the training-median baseline. TopCV and VietnamWorks validation MAPE were both
approximately 32.8%; canonical roles measured 31.05%, and unseen locations only
1.59%. This rules out source identity or location coverage as the dominant
error and confirms that the current feature/model/data combination remains far
from the 15% gate. The experiment wrote only temporary development artifacts;
it did not update publication evidence or inspect the reserved later period.

## Data Readiness for Retraining

Before reconsidering publication, collect all of the following without bypassing
source policies:

1. At least six distinct monthly observation dates.
2. At least 1,000 disclosed salaries mapped to canonical technical roles.
3. At least 30 observations across three dates for each supported role, level and
   primary-city segment intended for serving.
4. A frozen final-month temporal holdout containing at least 200 rows.
5. Source-level duplicate checks and documented currency conversion dates.

These conditions are enforced by `ml.salary.readiness`, included in every
training result and artifact metadata, exposed through the admin API, and
mirrored to Prometheus after retraining. The serving process rejects bundles
without an explicit passing readiness report even when their MAPE is below 15%.
The latest report has 2,285 unique rows across five distinct months, 948
canonical technical rows, seven qualified and 126 underqualified segments among
133 candidates, and 222 rows in the latest month. Duplicate-source, currency
and latest-month checks pass, but overall readiness remains false.

The next publication evaluation must freeze a later independent period before
development begins. The 15% gate must not be lowered, and those holdout rows
must not influence vocabulary, feature selection, hyperparameter selection or
interval calibration.

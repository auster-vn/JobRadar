# Salary Model Card

Last reviewed: 2026-07-19

## Status

The release candidate passes the repository publication contract on a clean
database reconstructed only from the six pinned salary snapshots. Its holdout
MAPE is **11.88%**, below the fixed 15% maximum, and `data_readiness` is `true`.
MLflow run `c550b86ee30c4ba19d6889e1398f3f9a` is bound to source revision
`62e0481385caef0be4bf6c18e2fd4cb1a11a8dfa`. The machine-readable result is
checked in at [`docs/evidence/salary_evaluation.json`](evidence/salary_evaluation.json).

The model is an aggregate market-benchmark estimator. It is not an individual
compensation predictor and must not be used for hiring, offer, promotion or
other high-impact employment decisions.

## Intended Use

For a supported role, level and primary-city segment, the model estimates the
monthly VND market median and an uncertainty interval. The public API uses it
only when the exact segment passed training-data support requirements. Every
other request falls back to observed market bands or a deterministic cold-start
response.

Supported output:

- point estimate of the segment's monthly salary median;
- lower and upper calibrated bounds in VND; and
- source and method labels that distinguish ML output from observed bands.

Unsupported use:

- estimating a named person's salary or worth;
- ranking candidates or determining compensation;
- extrapolating to an unsupported role, level or location; or
- presenting the interval as a guaranteed confidence interval.

## Training Data

The reproducible clean-room pool contains 3,208 unique salary observations.
All amounts are monthly VND within 1-200 million VND. Repeated source IDs are
deduplicated and linked live/historical records retain the earliest valid
observation date.

| Snapshot | Rows | Observation period | SHA-256 | License metadata |
|---|---:|---|---|---|
| VietJobs IT derivative | 1,115 | 2025-10-31 snapshot | `f823fdb009c69ff9a2e8a367497936fcd7001adcfa60bc4dc0784d6c55ff357c` | MIT |
| TopCV Kaggle derivative | 818 | 2025-12-16 to 2026-01-15 | `977b7da686d78e507b8424a28210d7746bfb3bb20acec1e0920cc1165de1be4e` | CC-BY-4.0 |
| Canhphu TopCV archive derivative | 744 | 2026-05-18 to 2026-06-21 | `0d8dc1cfa6d48d96e803d55781fdc5757ef763e54b340d5e670601d6189080ee` | NOASSERTION |
| Pre-holdout TopCV operational snapshot | 180 | 2026-06 to 2026-07 | `97a09d0d8470f31436bf741e8a89d02ba268ef146ad2e8f2d0dd61a022a21575` | NOASSERTION |
| Pre-holdout VietnamWorks operational snapshot | 172 | 2026-06 to 2026-07 | `d99d899d4cfbda63d9d6d03dc37263d03e5dbde071ad9a017e544d4702634478` | NOASSERTION |
| Frozen TopCV publication cohort | 179 | 2026-06-19 to 2026-07-18 | `33f0ffc88415a05db9dc4e02ce18370aca84e57d2291f2320a677d1f7d37368b` | NOASSERTION |

`NOASSERTION` means JobRadar records provenance but makes no upstream-license
claim. See [`docs/third_party.md`](third_party.md) for source revisions,
transformation details and redistribution caveats.

## Holdout Design

The publication holdout was frozen before its labels were used for model
selection:

- cohort: `topcv-it-first-seen-2026-07-19`;
- first-seen cutoff: `2026-07-19T04:36:28.244910+00:00`;
- completed batch: `eb00da89-c02b-49d1-be3e-68d7a3946c50`;
- raw cohort size: 179 source IDs;
- manifest SHA-256:
  `fb1a91a94f9f67744971f51b61bcd5ed39226d7caf587a4bd567fa1a2875714c`;
- nine IDs already present in the older TopCV snapshot were excluded before
  freezing the 179 labels.

The split is based on first-seen time, not posting date. Posting dates therefore
overlap the training period; the holdout remains source-record independent
because none of its IDs existed in the fitting pool at the cutoff.

## Method

1. Normalize bilingual title, canonical role, level, primary location,
   experience and skills.
2. Split raw source records into training and the manifest-pinned holdout.
3. Within each partition separately, retain role/level/location segments with
   at least three records and replace noisy listing-level labels with that
   partition's median salary. Holdout labels never define training targets.
4. Fit a TF-IDF and categorical feature encoder on training rows only. TF-IDF
   limits use term frequency with a lexical tie-break so clean-room releases
   select the same vocabulary across runners.
5. Fit XGBoost mean, Q25 and Q75 regressors on log salary.
6. Calibrate quantile offsets with train-only out-of-fold residuals.
7. Calibrate an interval radius on a later train-only temporal partition, then
   refit on the complete training side.
8. Serialize and reload every artifact before publication.

Serving support is computed from the raw training partition only. A segment
must have at least 30 observations across at least three distinct months.

## Evaluation

The evaluation unit is `market_segment_median`. The 179-record frozen cohort
contains 69 benchmark-supported observations across six segments.

| Metric | Result | Interpretation |
|---|---:|---|
| MAPE | **11.88%** | Passes the 15% publication gate |
| MAE | 2,477,873 VND | Informational |
| R2 | -0.3193 | Worse than a constant mean under squared-error scoring |
| Training-median baseline MAPE | 19.27% | Model improves the declared MAPE baseline |
| Predictions within 15% | 72.46% | Row-weighted holdout diagnostic |
| P90 absolute percentage error | 23.30% | Tail-error diagnostic |
| Median percentage bias | +8.82% | Model tends to overestimate this cohort |
| Target median | 21,000,000 VND | Holdout benchmark median |
| Prediction median | 23,920,348 VND | 2,920,348 VND above target median |
| Calibrated interval coverage | 50.72% | Close to the declared 50% target, not a guarantee |

The negative R2 is not hidden by the MAPE pass. It shows that the small,
six-segment holdout remains a weak basis for explaining cross-segment variance.
MAPE is the predeclared release metric because the product presents relative
market-benchmark error, but both metrics remain visible.

## Data Readiness

The clean-room report passes every fixed requirement:

| Requirement | Actual | Minimum/maximum |
|---|---:|---:|
| Unique salary observations | 3,208 | informational |
| Distinct monthly periods | 6 | at least 6 |
| Canonical technical training rows | 1,149 | at least 1,000 |
| Supported training segments | 8 | at least 5 |
| Rows in latest month | 392 | at least 200 |
| Duplicate source keys | 0 | exactly 0 |
| Non-VND rows after normalization | 0 | exactly 0 |

The eight supported segments are concentrated in Ha Noi. Unsupported and
underqualified segments are retained as diagnostics but cannot be served.

## Limitations and Monitoring

- Source coverage is opportunistic and does not represent every Vietnamese
  employer, region, seniority or compensation component.
- Some public postings expose broad ranges; midpoint normalization loses bonus,
  equity, benefits and negotiation context.
- Six distinct monthly periods are available but are not a continuous monthly
  panel.
- The holdout has only six benchmark-supported segments and is dominated by
  Business Analyst and QA Engineer observations.
- Operational derivatives carry `NOASSERTION` license metadata and should be
  reviewed before redistribution outside this personal project.
- Distribution drift, source markup changes and title-normalizer changes can
  invalidate the result.

Every release retrains from the pinned snapshots at its Git SHA, reruns the same
gate, embeds the published bundle in the ML image, and installs it into an
immutable revision path. Production health fails when that exact model cannot
be loaded. Prometheus exposes model availability, MAPE and readiness; weekly
training may create candidates, but a new production model still requires the
normal CI and release path.

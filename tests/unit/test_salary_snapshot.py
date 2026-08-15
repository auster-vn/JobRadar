import hashlib
import json
from pathlib import Path

from nlp.title_normalizer import TITLE_NORMALIZER_REVISION
from scripts.import_salary_snapshot import read_snapshot

SNAPSHOT_SHA256 = "f823fdb009c69ff9a2e8a367497936fcd7001adcfa60bc4dc0784d6c55ff357c"
TOPCV_SNAPSHOT_SHA256 = "977b7da686d78e507b8424a28210d7746bfb3bb20acec1e0920cc1165de1be4e"
CANHPHU_TOPCV_SNAPSHOT_SHA256 = "0d8dc1cfa6d48d96e803d55781fdc5757ef763e54b340d5e670601d6189080ee"
TOPCV_LIVE_COHORT_SHA256 = "33f0ffc88415a05db9dc4e02ce18370aca84e57d2291f2320a677d1f7d37368b"
TOPCV_HOLDOUT_MANIFEST_SHA256 = "fb1a91a94f9f67744971f51b61bcd5ed39226d7caf587a4bd567fa1a2875714c"
TOPCV_OPERATIONAL_SHA256 = "97a09d0d8470f31436bf741e8a89d02ba268ef146ad2e8f2d0dd61a022a21575"
VIETNAMWORKS_OPERATIONAL_SHA256 = "d99d899d4cfbda63d9d6d03dc37263d03e5dbde071ad9a017e544d4702634478"


def test_compact_salary_snapshot_is_valid() -> None:
    path = Path("data/vietjobs_it_salary_observations.csv")
    rows = read_snapshot(path)

    assert hashlib.sha256(path.read_bytes()).hexdigest() == SNAPSHOT_SHA256
    assert len(rows) == 1115
    assert len({row["source_record_id"] for row in rows}) == 1115
    assert all(row["salary_min"] is not None or row["salary_max"] is not None for row in rows)
    assert all(
        value is None or 0 <= value <= 15
        for row in rows
        for value in (row["experience_years_min"], row["experience_years_max"])
    )
    business_analysts = [row for row in rows if row["title"] == "BUSINESS ANALYST"]
    assert business_analysts
    assert all(row["title_normalized"] == "Business Analyst" for row in business_analysts)
    assert all(
        isinstance(row["source_metadata"], dict)
        and row["source_metadata"]["title_normalizer_revision"] == TITLE_NORMALIZER_REVISION
        for row in rows
    )


def test_compact_topcv_salary_snapshot_is_valid() -> None:
    path = Path("data/topcv_2026_it_salary_observations.csv")
    rows = read_snapshot(path)

    assert hashlib.sha256(path.read_bytes()).hexdigest() == TOPCV_SNAPSHOT_SHA256
    assert len(rows) == 818
    assert len({row["source_record_id"] for row in rows}) == 818
    assert {row["source_snapshot_date"].isoformat()[:7] for row in rows} == {
        "2025-12",
        "2026-01",
    }
    assert all(row["source"] == "topcv" for row in rows)
    assert all(row["location"] != "Hồ Chí Minh (mới)" for row in rows)
    usd_rows = [
        row
        for row in rows
        if isinstance(row["source_metadata"], dict)
        and row["source_metadata"].get("salary_source_currency") == "USD"
    ]
    assert len(usd_rows) == 30
    assert all(row["source_metadata"].get("usd_to_vnd") == "25000" for row in usd_rows)


def test_canhphu_topcv_salary_snapshot_is_valid() -> None:
    path = Path("data/topcv_canhphu_2026_salary_observations.csv")
    rows = read_snapshot(path)

    assert hashlib.sha256(path.read_bytes()).hexdigest() == CANHPHU_TOPCV_SNAPSHOT_SHA256
    assert len(rows) == 744
    assert len({row["source_record_id"] for row in rows}) == 744
    assert {row["source_snapshot_date"].isoformat()[:7] for row in rows} == {
        "2026-05",
        "2026-06",
    }
    assert all(row["source"] == "topcv_archive" for row in rows)
    assert all(row["source_metadata"].get("dataset_commit") for row in rows)
    assert all(row["source_metadata"].get("license") == "NOASSERTION" for row in rows)
    assert all(row["source_metadata"].get("raw_sha256") for row in rows)


def test_topcv_live_salary_cohort_and_holdout_manifest_are_valid() -> None:
    snapshot_path = Path("data/topcv_2026-07-19_it_salary_observations.csv")
    manifest_path = Path("data/salary_holdout_2026-07-19.json")
    rows = read_snapshot(snapshot_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert hashlib.sha256(snapshot_path.read_bytes()).hexdigest() == TOPCV_LIVE_COHORT_SHA256
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == TOPCV_HOLDOUT_MANIFEST_SHA256
    assert len(rows) == 179
    assert {row["source_snapshot_date"].isoformat()[:7] for row in rows} == {
        "2026-06",
        "2026-07",
    }
    assert all(row["source"] == "topcv" for row in rows)
    assert all(row["source_metadata"].get("license") == "NOASSERTION" for row in rows)
    assert all(row["source_metadata"].get("raw_payload_sha256") for row in rows)
    source_keys = [f"topcv:{row['source_record_id']}" for row in rows]
    assert manifest["source_key_count"] == len(source_keys)
    assert manifest["source_keys"] == source_keys
    assert manifest["snapshot_sha256"] == TOPCV_LIVE_COHORT_SHA256

    historical_ids = {
        row["source_record_id"]
        for row in read_snapshot(Path("data/topcv_2026_it_salary_observations.csv"))
    }
    assert historical_ids.isdisjoint(row["source_record_id"] for row in rows)


def test_pre_holdout_operational_salary_snapshots_are_valid() -> None:
    topcv_path = Path("data/topcv_operational_2026-07-18_salary_observations.csv")
    vietnamworks_path = Path("data/vietnamworks_operational_2026-07-18_salary_observations.csv")
    topcv_rows = read_snapshot(topcv_path)
    vietnamworks_rows = read_snapshot(vietnamworks_path)

    assert hashlib.sha256(topcv_path.read_bytes()).hexdigest() == TOPCV_OPERATIONAL_SHA256
    assert (
        hashlib.sha256(vietnamworks_path.read_bytes()).hexdigest()
        == VIETNAMWORKS_OPERATIONAL_SHA256
    )
    assert len(topcv_rows) == 180
    assert len(vietnamworks_rows) == 172
    assert all(row["source"] == "topcv" for row in topcv_rows)
    assert all(row["source"] == "vietnamworks" for row in vietnamworks_rows)
    assert all(
        row["source_metadata"].get("first_seen_batch_id")
        and row["source_metadata"].get("raw_payload_sha256")
        and row["source_metadata"].get("license") == "NOASSERTION"
        for row in [*topcv_rows, *vietnamworks_rows]
    )

    existing_topcv_ids = {
        row["source_record_id"]
        for path in (
            Path("data/topcv_2026_it_salary_observations.csv"),
            Path("data/topcv_2026-07-19_it_salary_observations.csv"),
        )
        for row in read_snapshot(path)
    }
    assert existing_topcv_ids.isdisjoint(row["source_record_id"] for row in topcv_rows)

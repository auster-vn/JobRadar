from datetime import date, datetime

import pytest

from api.services.salary_observation_import import validate_salary_observation_provenance


def _row() -> dict[str, object]:
    return {
        "source": "licensed_dataset",
        "source_record_id": "record-1",
        "source_snapshot_date": date(2026, 1, 31),
        "source_metadata": {
            "dataset": "publisher/dataset",
            "dataset_commit": "pinned-revision",
            "license": "MIT",
        },
    }


def test_salary_observation_provenance_accepts_auditable_source() -> None:
    validate_salary_observation_provenance([_row()])


@pytest.mark.parametrize("field", ["dataset", "dataset_commit", "license"])
def test_salary_observation_provenance_requires_metadata_field(field: str) -> None:
    row = _row()
    metadata = row["source_metadata"]
    assert isinstance(metadata, dict)
    metadata.pop(field)

    with pytest.raises(ValueError, match=field):
        validate_salary_observation_provenance([row])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source", "", "missing source"),
        ("source_record_id", "", "missing source_record_id"),
        ("source_metadata", None, "missing source_metadata"),
        (
            "source_snapshot_date",
            datetime(2026, 1, 31, 12, 0),
            "invalid source_snapshot_date",
        ),
    ],
)
def test_salary_observation_provenance_rejects_invalid_identity(
    field: str, value: object, message: str
) -> None:
    row = _row()
    row[field] = value

    with pytest.raises(ValueError, match=message):
        validate_salary_observation_provenance([row])

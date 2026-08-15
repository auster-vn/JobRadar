from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import Insert, insert

from api.core.database import session_factory
from api.models import SalaryObservation

UPDATABLE_FIELDS = (
    "source_snapshot_date",
    "title",
    "title_normalized",
    "job_level",
    "location",
    "experience_years_min",
    "experience_years_max",
    "skills",
    "salary_min",
    "salary_max",
    "category",
    "source_metadata",
)

REQUIRED_PROVENANCE_FIELDS = ("dataset", "dataset_commit", "license")


def validate_salary_observation_provenance(rows: Sequence[dict[str, object]]) -> None:
    """Reject historical observations whose origin cannot be audited."""
    for index, row in enumerate(rows):
        source = row.get("source")
        record_id = row.get("source_record_id")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"salary observation {index} is missing source")
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError(f"salary observation {index} is missing source_record_id")

        observed_on = row.get("source_snapshot_date")
        if isinstance(observed_on, datetime) or not isinstance(observed_on, date):
            raise ValueError(f"salary observation {index} has an invalid source_snapshot_date")

        metadata = row.get("source_metadata")
        if not isinstance(metadata, dict):
            raise ValueError(f"salary observation {index} is missing source_metadata")
        missing = [
            field
            for field in REQUIRED_PROVENANCE_FIELDS
            if not isinstance(metadata.get(field), str) or not str(metadata[field]).strip()
        ]
        if missing:
            fields = ", ".join(missing)
            raise ValueError(f"salary observation {index} is missing provenance fields: {fields}")


async def import_salary_observations(rows: Sequence[dict[str, object]]) -> int:
    validate_salary_observation_provenance(rows)
    imported = 0
    async with session_factory() as session, session.begin():
        for offset in range(0, len(rows), 500):
            statement = _upsert_statement(rows[offset : offset + 500])
            result = await session.execute(statement)
            imported += result.rowcount  # type: ignore[attr-defined]
    return imported


def _upsert_statement(rows: Sequence[dict[str, object]]) -> Insert:
    statement = insert(SalaryObservation).values(rows)
    updated_fields = {field: getattr(statement.excluded, field) for field in UPDATABLE_FIELDS}
    updated_fields["source_snapshot_date"] = func.least(
        SalaryObservation.source_snapshot_date,
        statement.excluded.source_snapshot_date,
    )
    return statement.on_conflict_do_update(
        constraint="uq_salary_observation_source_id",
        set_=updated_fields,
    )

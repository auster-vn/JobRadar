from types import SimpleNamespace

import pytest

from api.services import job_location_backfill
from nlp.location_normalizer import (
    normalize_location,
    normalize_locations,
    normalize_primary_location,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hà Nội", "Ha Noi"),
        ("Ha Noi", "Ha Noi"),
        ("TP. Hồ Chí Minh", "Ho Chi Minh"),
        ("Hồ Chí Minh (mới)", "Ho Chi Minh"),
        ("HCM", "Ho Chi Minh"),
        ("Đà Nẵng (mới)", "Da Nang"),
        ("Bắc Ninh (mới)", "Bắc Ninh"),
        ("2 nơi khác", None),
    ],
)
def test_normalize_location(raw: str, expected: str | None) -> None:
    assert normalize_location(raw) == expected


def test_normalize_locations_splits_compound_values_and_preserves_order() -> None:
    assert normalize_locations(["Hồ Chí Minh (mới) & Hà Nội", "TP HCM", "2 nơi khác"]) == [
        "Ho Chi Minh",
        "Ha Noi",
    ]


def test_normalize_primary_location_uses_first_explicit_location() -> None:
    assert normalize_primary_location("Hà Nội & Hồ Chí Minh (mới)") == "Ha Noi"


class _AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Session:
    def __init__(self, jobs: list[SimpleNamespace]) -> None:
        self.jobs = jobs

    def begin(self) -> _AsyncContext:
        return _AsyncContext(self)

    async def scalars(self, _statement: object) -> list[SimpleNamespace]:
        return self.jobs


@pytest.mark.asyncio
async def test_backfill_job_locations_updates_once(monkeypatch: pytest.MonkeyPatch) -> None:
    jobs = [
        SimpleNamespace(location=["Hồ Chí Minh (mới) & Hà Nội"]),
        SimpleNamespace(location=["Da Nang"]),
    ]
    session = _Session(jobs)
    monkeypatch.setattr(
        job_location_backfill,
        "session_factory",
        lambda: _AsyncContext(session),
    )

    first = await job_location_backfill.backfill_job_locations()
    second = await job_location_backfill.backfill_job_locations()

    assert first == {"scanned": 2, "updated": 1}
    assert second == {"scanned": 2, "updated": 0}
    assert jobs[0].location == ["Ho Chi Minh", "Ha Noi"]

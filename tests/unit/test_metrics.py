import math
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from api.core.metrics import (
    SALARY_DATA_CANONICAL_ROWS,
    SALARY_DATA_DISTINCT_MONTHS,
    SALARY_DATA_FINAL_MONTH_ROWS,
    SALARY_DATA_READY,
    SALARY_MODEL_INTERVAL_COVERAGE,
    SALARY_MODEL_MAPE,
    SALARY_MODEL_PUBLISHED,
    _scrape_ages,
    set_salary_evaluation_metrics,
)


def _value(gauge: object) -> float:
    return float(cast(Any, gauge)._value.get())


def test_salary_evaluation_updates_model_and_readiness_metrics() -> None:
    set_salary_evaluation_metrics(
        {
            "status": "rejected",
            "test_mape": 0.3017,
            "interval_coverage": 0.4318,
            "data_readiness": {
                "ready": False,
                "distinct_months": 2,
                "canonical_technical_rows": 109,
                "final_month_rows": 2,
            },
        }
    )

    assert _value(SALARY_MODEL_MAPE) == 0.3017
    assert _value(SALARY_MODEL_INTERVAL_COVERAGE) == 0.4318
    assert _value(SALARY_MODEL_PUBLISHED) == 0
    assert _value(SALARY_DATA_READY) == 0
    assert _value(SALARY_DATA_DISTINCT_MONTHS) == 2
    assert _value(SALARY_DATA_CANONICAL_ROWS) == 109
    assert _value(SALARY_DATA_FINAL_MONTH_ROWS) == 2


def test_scrape_ages_alerts_for_enabled_source_without_success() -> None:
    ages = _scrape_ages({}, {"topcv"}, now=datetime(2026, 7, 16, tzinfo=UTC))

    assert math.isinf(ages["topcv"])


def test_scrape_ages_ignores_disabled_sources_and_tracks_success() -> None:
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)
    ages = _scrape_ages(
        {
            "itviec": now - timedelta(hours=3),
            "topcv": now - timedelta(days=5),
        },
        {"itviec"},
        now=now,
    )

    assert ages == {"itviec": 10_800}

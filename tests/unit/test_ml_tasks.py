import json
from typing import Any

import pytest

from workers.ml_tasks import MODEL_EVALUATION_KEY, persist_model_evaluation


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.closed = False

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def close(self) -> None:
        self.closed = True


def test_model_evaluation_is_persisted_for_api_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = FakeRedis()
    monkeypatch.setattr(
        "workers.ml_tasks.Redis.from_url",
        lambda *args, **kwargs: redis,
    )
    result: dict[str, Any] = {
        "status": "rejected",
        "test_mape": 0.3,
        "interval_coverage": 0.5,
    }

    persist_model_evaluation(result)

    assert json.loads(redis.values[MODEL_EVALUATION_KEY]) == result
    assert redis.closed

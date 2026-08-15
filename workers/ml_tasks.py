import json
from typing import Any

from redis import Redis

from api.core.config import get_settings
from ml.salary.training import train_from_database
from workers.async_runner import run_async
from workers.celery_app import app

MODEL_EVALUATION_KEY = "model:salary:latest_evaluation"


def persist_model_evaluation(result: dict[str, Any]) -> None:
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        client.set(MODEL_EVALUATION_KEY, json.dumps(result, default=str))
    finally:
        client.close()


@app.task(name="workers.ml_tasks.retrain_salary_model")
def retrain_salary_model() -> dict[str, Any]:
    try:
        result = run_async(train_from_database())
    except ModuleNotFoundError as exc:
        result = {
            "status": "skipped",
            "reason": "ml_extra_not_installed",
            "missing_module": exc.name,
        }
    persist_model_evaluation(result)
    return result

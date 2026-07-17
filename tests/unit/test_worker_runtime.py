import asyncio

from workers.async_runner import run_async
from workers.celery_app import app


async def _loop_identity() -> int:
    return id(asyncio.get_running_loop())


def test_worker_reuses_event_loop_between_tasks() -> None:
    assert run_async(_loop_identity()) == run_async(_loop_identity())


def test_nlp_tasks_use_dedicated_routing_key() -> None:
    route = app.amqp.router.route({}, "workers.nlp_tasks.embed_profile")

    assert route["queue"].name == "nlp"
    assert route["routing_key"] == "nlp"


def test_analytics_tasks_use_dedicated_routing_key() -> None:
    route = app.amqp.router.route({}, "workers.analytics_tasks.build_analytics")

    assert route["queue"].name == "analytics"
    assert route["routing_key"] == "analytics"

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

from api.core.config import get_settings

settings = get_settings()
task_exchange = Exchange("jobradar", type="direct")
app = Celery(
    "jobradarvn",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "workers.alert_tasks",
        "workers.analytics_tasks",
        "workers.ml_tasks",
        "workers.nlp_tasks",
        "workers.scrape_tasks",
    ],
)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    broker_pool_limit=settings.celery_broker_pool_limit,
    broker_connection_retry_on_startup=True,
    result_expires=settings.celery_result_expires,
    broker_transport_options={
        "priority_steps": list(range(10)),
        "sep": ":",
        "socket_connect_timeout": settings.redis_socket_timeout,
        "socket_timeout": settings.redis_socket_timeout,
    },
    redis_socket_connect_timeout=settings.redis_socket_timeout,
    redis_socket_timeout=settings.redis_socket_timeout,
    task_routes={
        "workers.scrape_tasks.*": {
            "queue": "scraping",
            "routing_key": "scraping",
            "priority": 2,
        },
        "workers.nlp_tasks.*": {"queue": "nlp", "routing_key": "nlp", "priority": 4},
        "workers.alert_tasks.*": {
            "queue": "alerts",
            "routing_key": "alerts",
            "priority": 8,
        },
        "workers.ml_tasks.*": {"queue": "ml", "routing_key": "ml", "priority": 1},
        "workers.analytics_tasks.*": {
            "queue": "analytics",
            "routing_key": "analytics",
            "priority": 1,
        },
    },
    task_queues=(
        Queue("scraping", task_exchange, routing_key="scraping"),
        Queue("nlp", task_exchange, routing_key="nlp"),
        Queue("alerts", task_exchange, routing_key="alerts"),
        Queue("ml", task_exchange, routing_key="ml"),
        Queue("analytics", task_exchange, routing_key="analytics"),
    ),
    beat_schedule={
        "scrape-itviec": {
            "task": "workers.scrape_tasks.scrape_itviec",
            "schedule": crontab(hour=2, minute=0),
            "kwargs": {"pages": 25, "detail_limit": 25},
        },
        "scrape-vietnamworks": {
            "task": "workers.scrape_tasks.scrape_vietnamworks",
            "schedule": crontab(hour=3, minute=30),
            "kwargs": {"max_pages": 10},
        },
        "scrape-topcv": {
            "task": "workers.scrape_tasks.scrape_topcv",
            "schedule": crontab(hour=4, minute=0),
            "kwargs": {"max_pages": 10},
        },
        "check-alerts": {
            "task": "workers.alert_tasks.check_and_fire",
            "schedule": crontab(minute="*/30"),
        },
        "mark-expired-jobs": {
            "task": "workers.scrape_tasks.mark_expired_jobs",
            "schedule": crontab(hour=6, minute=0),
        },
        "embed-new-jobs": {
            "task": "workers.nlp_tasks.embed_jobs",
            "schedule": crontab(hour=4, minute=30),
            "kwargs": {"limit": 1000},
        },
        "build-analytics": {
            "task": "workers.analytics_tasks.build_analytics",
            "schedule": crontab(hour=5, minute=0),
        },
        "retrain-salary": {
            "task": "workers.ml_tasks.retrain_salary_model",
            "schedule": crontab(day_of_week=0, hour=5, minute=0),
        },
    },
)

if not settings.enable_salary_retraining:
    app.conf.beat_schedule.pop("retrain-salary", None)

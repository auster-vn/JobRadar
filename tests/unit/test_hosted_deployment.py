import importlib
import runpy
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic import context
from alembic.config import Config
from fastapi.testclient import TestClient
from starlette.requests import Request

from api.core import config, rate_limit
from api.core.config import Settings
from ml import serving
from workers import celery_app


def request_with(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/jobs",
            "client": ("10.0.0.1", 1234),
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        }
    )


@pytest.mark.parametrize("address", ["203.0.113.7", "2001:db8::7"])
def test_authenticated_proxy_identity(monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    settings = Settings(proxy_shared_secret="s" * 32)
    monkeypatch.setattr(rate_limit, "get_settings", lambda: settings)
    request = request_with(
        {
            "X-JobRadar-Proxy-Secret": "s" * 32,
            "X-JobRadar-Client-IP": address,
            "X-Forwarded-For": "198.51.100.99",
        }
    )
    assert rate_limit._identity(request) == (f"ip:{address}", False)


@pytest.mark.parametrize(
    "secret,address",
    [
        ("", "203.0.113.7"),
        ("wrong", "203.0.113.7"),
        ("s" * 32, "203.0.113.7, 198.51.100.2"),
        ("s" * 32, ""),
    ],
)
def test_proxy_spoofing_cannot_choose_bucket(
    monkeypatch: pytest.MonkeyPatch,
    secret: str,
    address: str,
) -> None:
    settings = Settings(proxy_shared_secret="s" * 32, trust_proxy_headers=True)
    monkeypatch.setattr(rate_limit, "get_settings", lambda: settings)
    request = request_with(
        {
            "X-JobRadar-Proxy-Secret": secret,
            "X-JobRadar-Client-IP": address,
            "X-Forwarded-For": "198.51.100.99",
        }
    )
    assert rate_limit._identity(request) == ("ip:unverified-proxy", False)


def test_short_proxy_secret_rejected() -> None:
    with pytest.raises(ValueError, match="PROXY_SHARED_SECRET"):
        Settings(proxy_shared_secret="short").validate_production_secrets()  # noqa: S106


@pytest.mark.parametrize("available,status_code", [(False, 503), (True, 200)])
def test_ml_readiness_requires_model(
    monkeypatch: pytest.MonkeyPatch,
    available: bool,
    status_code: int,
) -> None:
    monkeypatch.setattr(serving, "model", Mock(available=available))
    with TestClient(serving.app) as client:
        assert client.get("/health/ready").status_code == status_code
        assert client.get("/health").status_code == 200


def test_alembic_preserves_encoded_password(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "postgresql+asyncpg://user:p%40ss%25word@localhost/postgres?ssl=require"
    settings = Settings(database_url=url)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    alembic_config = Config()
    monkeypatch.setattr(context, "config", alembic_config, raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: True)
    configure = Mock()
    monkeypatch.setattr(context, "configure", configure)
    monkeypatch.setattr(context, "begin_transaction", nullcontext)
    monkeypatch.setattr(context, "run_migrations", lambda: None)
    runpy.run_path(str(Path("migrations/env.py")))
    assert configure.call_args.kwargs["url"] == url


def test_hosted_scheduler_disables_only_retraining(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        with monkeypatch.context() as patch:
            patch.setattr(config, "get_settings", lambda: Settings(enable_salary_retraining=False))
            importlib.reload(celery_app)
            assert "retrain-salary" not in celery_app.app.conf.beat_schedule
            assert "build-analytics" in celery_app.app.conf.beat_schedule
            assert "scrape-topcv" in celery_app.app.conf.beat_schedule
    finally:
        importlib.reload(celery_app)

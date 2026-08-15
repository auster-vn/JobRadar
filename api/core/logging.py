import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import UTC, datetime

from fastapi import Request, Response

from api.core.config import get_settings

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    formatter: logging.Formatter
    if settings.log_json or settings.app_env == "production":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
        )
    for handler in root.handlers:
        handler.setFormatter(formatter)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        return True


async def request_logging_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if _REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    logger = logging.getLogger("jobradar.request")
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed method=%s path=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            (time.perf_counter() - started) * 1000,
        )
        raise
    else:
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_complete method=%s path=%s status=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response
    finally:
        request_id_context.reset(token)


configure_logging()
for _handler in logging.getLogger().handlers:
    _handler.addFilter(RequestIdFilter())

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, Response, status
from starlette.responses import JSONResponse

from api.core.cache import CacheUnavailable, cache
from api.core.config import get_settings
from api.core.security import decode_token

ANONYMOUS_LIMITS: dict[tuple[str, str], tuple[int, int]] = {
    ("POST", "/api/auth/login"): (5, 60),
    ("POST", "/api/auth/register"): (3, 60),
    ("POST", "/api/cron/daily"): (5, 3600),
    ("GET", "/api/jobs"): (30, 60),
    ("POST", "/api/salary/predict"): (5, 60),
}
AUTHENTICATED_LIMITS: dict[tuple[str, str], tuple[int, int]] = {
    ("GET", "/api/jobs"): (120, 60),
    ("POST", "/api/salary/predict"): (30, 60),
    ("GET", "/api/profile/matching-jobs"): (20, 60),
    ("POST", "/api/profile/cv"): (5, 3600),
    ("POST", "/api/alerts"): (10, 3600),
    ("POST", "/api/applications"): (30, 60),
}
logger = logging.getLogger(__name__)


def _normalized_path(path: str) -> str:
    if path.startswith("/api/"):
        return path
    if path == "/jobs" or path == "/applications" or path == "/profile":
        return f"/api{path}"
    if path.startswith(("/auth/", "/jobs/", "/applications/", "/profile/")):
        return f"/api{path}"
    return path


def _limit_for(request: Request, authenticated: bool) -> tuple[int, int] | None:
    limits = AUTHENTICATED_LIMITS if authenticated else ANONYMOUS_LIMITS
    path = _normalized_path(request.url.path)
    exact = limits.get((request.method, path))
    if exact:
        return exact
    if authenticated and request.method == "POST" and path.endswith("/score"):
        return (10, 60)
    if authenticated and request.method == "PATCH" and path.startswith("/api/applications/"):
        return (30, 60)
    return None


def _must_fail_closed(request: Request) -> bool:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    path = _normalized_path(request.url.path)
    return path.startswith(
        (
            "/api/auth/",
            "/api/alerts",
            "/api/applications",
            "/api/cron/",
            "/api/profile/cv",
        )
    ) or path.endswith("/score")


async def _identity(request: Request) -> tuple[str, bool]:
    bearer = request.headers.get("Authorization", "")
    token = bearer.removeprefix("Bearer ") if bearer.startswith("Bearer ") else None
    token = token or request.cookies.get("access_token")
    if token:
        try:
            user_id = await asyncio.to_thread(decode_token, token, "access")
            return f"user:{user_id}", True
        except HTTPException:
            token = None
    forwarded = ""
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    client_ip = forwarded or (request.client.host if request.client else "unknown")
    return f"ip:{client_ip}", False


async def rate_limit_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if not get_settings().rate_limit_enabled:
        return await call_next(request)
    identity, authenticated = await _identity(request)
    rule = _limit_for(request, authenticated)
    if not rule:
        return await call_next(request)
    maximum, window = rule
    bucket = int(time.time()) // window
    digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
    path = _normalized_path(request.url.path)
    key = f"rate:{request.method}:{path}:{digest}:{bucket}"
    try:
        count = await cache.increment(key, window + 1)
        if count > maximum:
            retry_after = window - int(time.time()) % window
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )
    except CacheUnavailable as exc:
        logger.warning("Rate limiting unavailable: %s", type(exc).__name__)
        if get_settings().app_env == "production" and _must_fail_closed(request):
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "Request protection is temporarily unavailable"},
                headers={"Retry-After": "30"},
            )
    return await call_next(request)

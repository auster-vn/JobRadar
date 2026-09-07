import hashlib
import hmac
import ipaddress
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, Response, status
from redis.asyncio import Redis
from starlette.responses import JSONResponse

from api.core.config import get_settings
from api.core.security import decode_token

ANONYMOUS_LIMITS: dict[tuple[str, str], tuple[int, int]] = {
    ("POST", "/api/auth/login"): (5, 60),
    ("POST", "/api/auth/register"): (3, 60),
    ("GET", "/api/jobs"): (30, 60),
    ("POST", "/api/salary/predict"): (5, 60),
}
AUTHENTICATED_LIMITS: dict[tuple[str, str], tuple[int, int]] = {
    ("GET", "/api/jobs"): (120, 60),
    ("POST", "/api/salary/predict"): (30, 60),
    ("GET", "/api/profile/matching-jobs"): (20, 60),
}
redis: Redis = Redis.from_url(
    get_settings().redis_url,
    encoding="utf-8",
    decode_responses=True,
    socket_connect_timeout=get_settings().redis_socket_timeout,
    socket_timeout=get_settings().redis_socket_timeout,
)
logger = logging.getLogger(__name__)


def _identity(request: Request) -> tuple[str, bool]:
    bearer = request.headers.get("Authorization", "")
    token = bearer.removeprefix("Bearer ") if bearer.startswith("Bearer ") else None
    token = token or request.cookies.get("access_token")
    if token:
        try:
            return f"user:{decode_token(token, 'access')}", True
        except HTTPException:
            token = None
    settings = get_settings()
    # In hosted mode, only the authenticated frontend can assert a client IP.
    # Never fall back to arbitrary forwarded headers when this mode is enabled.
    if settings.proxy_shared_secret:
        supplied = request.headers.get("X-JobRadar-Proxy-Secret", "")
        if hmac.compare_digest(supplied.encode(), settings.proxy_shared_secret.encode()):
            try:
                address = ipaddress.ip_address(request.headers.get("X-JobRadar-Client-IP", ""))
                return f"ip:{address}", False
            except ValueError:
                pass
        return "ip:unverified-proxy", False
    forwarded = ""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    client_ip = forwarded or (request.client.host if request.client else "unknown")
    return f"ip:{client_ip}", False


async def rate_limit_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if not get_settings().rate_limit_enabled:
        return await call_next(request)
    identity, authenticated = _identity(request)
    limits = AUTHENTICATED_LIMITS if authenticated else ANONYMOUS_LIMITS
    rule = limits.get((request.method, request.url.path))
    if not rule:
        return await call_next(request)
    maximum, window = rule
    bucket = int(time.time()) // window
    digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
    key = f"rate:{request.method}:{request.url.path}:{digest}:{bucket}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window + 1)
        if count > maximum:
            retry_after = window - int(time.time()) % window
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )
    except Exception as exc:
        # Availability wins when Redis is temporarily unavailable; infrastructure alerts cover it.
        logger.warning("Rate limiting unavailable: %s", type(exc).__name__)
    return await call_next(request)

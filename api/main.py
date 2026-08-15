import asyncio
import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from api.core.cache import cache
from api.core.config import get_settings
from api.core.database import database_is_ready, engine
from api.core.logging import request_logging_middleware
from api.core.metrics import metrics_middleware, metrics_response
from api.core.rate_limit import rate_limit_middleware
from api.core.security import csrf_middleware, security_headers_middleware
from api.routers import (
    admin,
    alerts,
    analytics,
    applications,
    auth,
    cron,
    jobs,
    profile,
    salary,
    scoring,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await cache.close()
    await engine.dispose()


app = FastAPI(
    title="JobRadar VN API",
    version="0.1.0",
    description="Vietnamese technology job market intelligence",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "X-Admin-Key",
        "X-Cron-Secret",
        "X-Request-ID",
    ],
    expose_headers=["Retry-After", "X-RateLimit-Limit", "X-Request-ID"],
)
app.middleware("http")(security_headers_middleware)
app.middleware("http")(metrics_middleware)
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(csrf_middleware)
app.middleware("http")(request_logging_middleware)
app.include_router(jobs.router)
app.include_router(salary.router)
app.include_router(analytics.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(alerts.router)
app.include_router(applications.router)
app.include_router(scoring.router)
app.include_router(admin.router)
app.include_router(cron.router)


def _add_canonical_route_aliases() -> None:
    """Expose the contract paths while retaining the browser-facing `/api` routes."""

    required_paths = {
        "/api/auth/login",
        "/api/jobs",
        "/api/jobs/{job_id}",
        "/api/jobs/{job_id}/score",
        "/api/applications",
        "/api/applications/{application_id}",
        "/api/profile",
    }
    source_routers = (auth.router, jobs.router, applications.router, profile.router, scoring.router)
    for source_router in source_routers:
        for route in source_router.routes:
            if not isinstance(route, APIRoute) or route.path not in required_paths:
                continue
            app.add_api_route(
                route.path.removeprefix("/api"),
                route.endpoint,
                methods=sorted(route.methods) if route.methods else None,
                response_model=route.response_model,
                status_code=route.status_code,
                tags=route.tags,
                dependencies=route.dependencies,
                summary=route.summary,
                description=route.description,
                response_description=route.response_description,
                responses=route.responses,
                deprecated=route.deprecated,
                name=f"{route.name}_canonical",
                operation_id=(f"{route.operation_id}_canonical" if route.operation_id else None),
                response_model_include=route.response_model_include,
                response_model_exclude=route.response_model_exclude,
                response_model_by_alias=route.response_model_by_alias,
                response_model_exclude_unset=route.response_model_exclude_unset,
                response_model_exclude_defaults=route.response_model_exclude_defaults,
                response_model_exclude_none=route.response_model_exclude_none,
                include_in_schema=route.include_in_schema,
                response_class=route.response_class,
            )


_add_canonical_route_aliases()


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "jobradar-api"}


@app.get("/health/ready", tags=["meta"])
async def ready(response: Response) -> dict[str, str]:
    database_ready, cache_ready = await asyncio.gather(database_is_ready(), cache.ping())
    cache_required = settings.app_env == "production"
    if not database_ready or (cache_required and not cache_ready):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "database": "available" if database_ready else "unavailable",
            "cache": "available" if cache_ready else "unavailable",
        }
    return {
        "status": "ready",
        "database": "available",
        "cache": "available" if cache_ready else "optional_unavailable",
    }


@app.get("/version", tags=["meta"])
async def version() -> dict[str, str]:
    return {
        "version": app.version,
        "environment": settings.app_env,
        "source_revision": settings.source_revision,
    }


@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    expected = settings.metrics_token or (
        settings.admin_api_key if settings.app_env == "production" else None
    )
    if expected:
        authorization = request.headers.get("Authorization", "")
        bearer_token = authorization.removeprefix("Bearer ") if authorization else ""
        supplied = request.headers.get("X-Metrics-Token", bearer_token)
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Metrics authentication required",
            )
    return await metrics_response()

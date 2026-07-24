from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from api.core.config import get_settings
from api.core.database import database_is_ready, engine
from api.core.metrics import metrics_middleware, metrics_response
from api.core.rate_limit import rate_limit_middleware
from api.core.security import security_headers_middleware
from api.routers import admin, alerts, analytics, auth, jobs, profile, salary

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Key"],
)
app.middleware("http")(security_headers_middleware)
app.middleware("http")(metrics_middleware)
app.middleware("http")(rate_limit_middleware)
app.include_router(jobs.router)
app.include_router(salary.router)
app.include_router(analytics.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(alerts.router)
app.include_router(admin.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "jobradar-api"}


@app.get("/health/ready", tags=["meta"])
async def ready(response: Response) -> dict[str, str]:
    if not await database_is_ready():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "database": "unavailable"}
    return {"status": "ready", "database": "available"}


@app.get("/version", tags=["meta"])
async def version() -> dict[str, str]:
    return {
        "version": app.version,
        "environment": settings.app_env,
        "source_revision": settings.source_revision,
    }


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return await metrics_response()

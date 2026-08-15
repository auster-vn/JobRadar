from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.core.config import get_settings

settings = get_settings()
engine_options: dict[str, object] = {
    "pool_pre_ping": True,
    "pool_size": settings.database_pool_size,
    "max_overflow": settings.database_max_overflow,
    "pool_timeout": settings.database_pool_timeout_seconds,
    "pool_recycle": settings.database_pool_recycle_seconds,
    "pool_use_lifo": True,
}
if settings.database_url.startswith("postgresql+asyncpg"):
    engine_options["connect_args"] = {
        "statement_cache_size": settings.database_statement_cache_size,
        "server_settings": {"application_name": settings.app_name.lower().replace(" ", "-")},
    }
engine: AsyncEngine = create_async_engine(settings.database_url, **engine_options)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def database_is_ready() -> bool:
    try:
        async with engine.connect() as connection:
            result = await connection.exec_driver_sql(
                """
                SELECT to_regclass('public.jobs') IS NOT NULL
                   AND to_regclass('public.user_profiles') IS NOT NULL
                   AND to_regclass('public.alembic_version') IS NOT NULL
                """
            )
        return bool(result.scalar_one())
    except Exception:  # Readiness must return false rather than crash the process.
        return False

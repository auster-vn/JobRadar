import asyncio
import json
import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from api.core.database import engine, session_factory
from api.models import PipelineRun
from workers.pipeline_tasks import PIPELINE_STALE_AFTER, execute_daily_pipeline


async def main() -> int:
    now = datetime.now(UTC)
    key = (os.environ.get("PIPELINE_IDEMPOTENCY_KEY") or f"daily:{now.date().isoformat()}").strip()
    if not 8 <= len(key) <= 128:
        raise ValueError("PIPELINE_IDEMPOTENCY_KEY must contain 8 to 128 non-whitespace characters")

    candidate_id = uuid.uuid4()
    async with session_factory() as session:
        run_id = await session.scalar(
            insert(PipelineRun)
            .values(
                id=candidate_id,
                kind="daily_ingestion",
                status="queued",
                idempotency_key=key,
            )
            .on_conflict_do_nothing(constraint="uq_pipeline_runs_idempotency_key")
            .returning(PipelineRun.id)
        )
        if run_id is None:
            existing = await session.scalar(
                select(PipelineRun).where(PipelineRun.idempotency_key == key)
            )
            if existing is None:
                raise RuntimeError("Pipeline idempotency conflict could not be resolved")
            if existing.kind != "daily_ingestion":
                raise RuntimeError("Idempotency key belongs to a different pipeline kind")
            fresh_running = existing.status == "running" and (
                existing.started_at is not None
                and existing.started_at >= now - PIPELINE_STALE_AFTER
            )
            if existing.status in {"completed", "partial", "cancelled"} or fresh_running:
                print(
                    json.dumps(
                        {
                            "run_id": str(existing.id),
                            **(existing.details or {}),
                            "status": existing.status,
                        },
                        default=str,
                    )
                )
                return 0 if existing.status != "cancelled" else 1
            run_id = existing.id
        await session.commit()

    result = await execute_daily_pipeline(run_id)
    print(json.dumps({"run_id": str(run_id), **result}, default=str))
    return 0 if result.get("status") in {"completed", "partial", "running"} else 1


if __name__ == "__main__":

    async def _run() -> int:
        try:
            return await main()
        finally:
            await engine.dispose()

    raise SystemExit(asyncio.run(_run()))

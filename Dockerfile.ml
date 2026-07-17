FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
WORKDIR /app

RUN pip install --no-cache-dir uv==0.9.7
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra ml --extra analytics --no-install-project
COPY api api
COPY nlp nlp
COPY scrapers scrapers
COPY workers workers
COPY ml ml
COPY flows flows
COPY scripts scripts
COPY data data
COPY analytics analytics
COPY migrations migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev --extra ml --extra analytics
RUN .venv/bin/dbt deps --project-dir analytics --profiles-dir analytics
RUN groupadd --system jobradar && useradd --system --gid jobradar --home /app jobradar \
    && mkdir -p /app/artifacts /app/.cache \
    && chown -R jobradar:jobradar /app

ARG SOURCE_REVISION=local
ENV PATH="/app/.venv/bin:$PATH" HF_HOME="/app/.cache/huggingface" \
    SOURCE_REVISION=$SOURCE_REVISION GIT_PYTHON_REFRESH=quiet
LABEL org.opencontainers.image.revision=$SOURCE_REVISION
USER jobradar
CMD ["celery", "-A", "workers.celery_app", "worker", "-Q", "nlp,ml,analytics", "--concurrency=1", "--loglevel=info"]

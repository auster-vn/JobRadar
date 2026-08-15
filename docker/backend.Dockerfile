FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000

WORKDIR /app

ARG UV_VERSION=0.12.5
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "uv==$UV_VERSION"

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY api api
COPY nlp nlp
COPY scrapers scrapers
COPY workers workers
COPY ml ml
COPY flows flows
COPY scripts scripts
COPY data data
COPY database database
COPY migrations migrations
COPY alembic.ini ./

RUN uv sync --frozen --no-dev \
    && pip uninstall --yes uv \
    && groupadd --system jobradar \
    && useradd --system --gid jobradar --home-dir /app jobradar \
    && chown -R jobradar:jobradar /app

ARG SOURCE_REVISION=local
ENV SOURCE_REVISION=$SOURCE_REVISION
LABEL org.opencontainers.image.revision=$SOURCE_REVISION

USER jobradar
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health/ready', timeout=3)" || exit 1
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
WORKDIR /app

ARG UV_VERSION=0.11.29
RUN pip install --no-cache-dir "uv==$UV_VERSION"
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project --extra scraping
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN .venv/bin/playwright install --with-deps --only-shell chromium
COPY api api
COPY nlp nlp
COPY scrapers scrapers
COPY workers workers
COPY ml ml
COPY flows flows
COPY scripts scripts
COPY data data
COPY migrations migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev --extra scraping
RUN pip uninstall --yes uv
RUN groupadd --system jobradar && useradd --system --gid jobradar --home /app jobradar \
    && chown -R jobradar:jobradar /app

ARG SOURCE_REVISION=local
ENV PATH="/app/.venv/bin:$PATH" SOURCE_REVISION=$SOURCE_REVISION
LABEL org.opencontainers.image.revision=$SOURCE_REVISION
USER jobradar
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

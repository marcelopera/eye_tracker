FROM python:3.12-slim AS tooling

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

FROM tooling AS base

COPY pyproject.toml uv.lock ./

FROM base AS test

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY app ./app
COPY tests ./tests
RUN uv sync --frozen --group dev --no-install-project
RUN uv run --frozen --group dev python -m pytest

FROM base AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

RUN useradd --create-home --uid 10001 --user-group app \
    && mkdir -p /data/tmp && chown -R app:app /data
ENV EYE_TRACKER_DATA_DIR=/data TMPDIR=/data/tmp
USER app

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

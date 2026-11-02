FROM ghcr.io/astral-sh/uv:0.10.9 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY itracker.py ./
ENTRYPOINT ["/app/.venv/bin/python", "itracker.py"]

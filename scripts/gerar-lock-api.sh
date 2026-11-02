#!/usr/bin/env bash
set -euo pipefail

# Resolve a raiz pelo próprio script, independentemente do diretório do terminal.
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# Este estágio contém Python e uv e não depende de um uv.lock já existente.
docker build --target tooling -t eye-tracker-api-tooling "$project_root/services/api"

# --mount falha para uma origem inexistente, em vez de criar uma pasta como root.
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e UV_CACHE_DIR=/tmp/uv-cache \
  --mount "type=bind,source=$project_root/services/api,target=/app" \
  --workdir /app \
  eye-tracker-api-tooling uv lock

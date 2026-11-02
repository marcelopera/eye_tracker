# Eye Tracker API

Serviço FastAPI mínimo. Expõe `GET /api/health` e `GET /api/info`; a interface
OpenAPI fica disponível em `/docs` e `/openapi.json`. Upload de sessões e
processamento de olhar ainda não estão implementados.

Para gerar ou atualizar o lockfile com Python e uv em container, execute na raiz:

```sh
bash scripts/gerar-lock-api.sh
```

O script monta uma imagem de ferramentas usando o estágio `tooling` do
[Dockerfile](Dockerfile), que combina Python e o binário oficial uv e pode ser
construído antes de existir o lockfile. O arquivo gerado fica nesta pasta e deve
ser versionado junto ao [pyproject.toml](pyproject.toml).

Com Python 3.12 e [uv](https://docs.astral.sh/uv/) instalados, execute em
`services/api`:

```sh
uv sync --frozen --group dev
uv run --frozen --group dev python -m pytest
uv run --frozen uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Para executar em container, a partir da raiz do repositório:

```sh
docker build -t eye-tracker-api services/api
docker run --rm -p 8000:8000 eye-tracker-api
```

Para iniciar a base integrada ao webapp, use `docker compose up --build -d --wait`
na raiz. O Compose fornece Python e uv nas imagens e publica a API pelo webapp.

Para executar os testes em um container, sem instalar Python no host:

```sh
docker build --target test -t eye-tracker-api-test services/api
```

# Eye Tracker API

Serviço FastAPI. Expõe `GET /api/health` e `GET /api/info`, além de cadastro,
consulta e edição de rascunhos em `/api/experiments`; a interface
OpenAPI fica disponível em `/docs` e `/openapi.json`. Upload de sessões e
processamento de olhar ainda não estão implementados. O estímulo aceita MP4 H.264 com até 30 segundos e 100 MB. O protocolo
provisório reproduz o Android atual e não foi validado cientificamente. A publicação
exige vídeo e protocolo e torna o experimento imutável. A criação exige o cabeçalho `Idempotency-Key`;
a mesma chave e o mesmo conteúdo recuperam o rascunho existente.

Os dados ficam em SQLite no diretório `EYE_TRACKER_DATA_DIR` (padrão `./data`).
No Compose, o volume nomeado `experiment_data` é montado em `/data`. Faça uma
cópia consistente de todo o volume (banco e vídeos) com o serviço parado antes de restaurar ou migrar os dados. A remoção de volumes do Compose apaga os rascunhos.

Para gerar ou atualizar o lockfile com Python e uv em container, execute na raiz:

```sh
bash scripts/gerar-lock-api.sh
```

O script monta uma imagem de ferramentas usando o estágio `tooling` do
[Dockerfile](Dockerfile), que combina Python e o binário oficial uv e pode ser
construído antes de existir o lockfile. O arquivo gerado fica nesta pasta e deve
ser versionado junto ao [pyproject.toml](pyproject.toml).

Com `ffprobe` instalado no PATH, Python 3.12 e [uv](https://docs.astral.sh/uv/) instalados, execute em
`services/api`:

```sh
uv sync --frozen --group dev
uv run --frozen --group dev python -m pytest
uv run --frozen uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Para executar em container, a partir da raiz do repositório:

```sh
docker build -t eye-tracker-api services/api
docker run --rm -p 8000:8000 -v eye-tracker-data:/data eye-tracker-api
```

Para iniciar a base integrada ao webapp, use `docker compose up --build -d --wait`
na raiz. O Compose fornece Python e uv nas imagens e publica a API pelo webapp.

Para executar os testes em um container, sem instalar Python no host:

```sh
docker build --target test -t eye-tracker-api-test services/api
```

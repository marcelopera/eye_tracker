# Eye Tracker API

Serviço FastAPI. Expõe `GET /api/health` e `GET /api/info`, além de cadastro,
consulta e edição de rascunhos em `/api/experiments`; a interface
OpenAPI fica disponível em `/docs` e `/openapi.json`. O recebimento de sessões está disponível; o processamento de olhar ainda não está implementado. O estímulo aceita MP4 H.264 com até 30 segundos e 100 MB. O protocolo
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

## Recebimento provisório de coletas

`GET /api/published-experiments/{code}` consulta um experimento publicado. `POST /api/sessions` recebe `experiment_id`, `local_id` (UUID) e `participant_code` e retorna um ID de servidor; repetir com os mesmos dados recupera a sessão. `PUT /api/sessions/{id}/files` recebe multipart com `video`, `events`, `video_sha256` e `events_sha256`. O servidor confere os hashes, a associação dos metadados, a presença de faixa de vídeo e os limites de 500 MB para o vídeo e 5 MB para os eventos. A repetição com os mesmos hashes é idempotente; outros hashes geram conflito. Arquivos e banco ficam no volume de dados. A resposta indica recebimento, não processamento.

O formato recebido é o `sessao.json` original do protótipo com `face.mp4`, não um manifesto v1. Não há dados suficientes para afirmar sincronização, perfil físico ou validade científica. A API não autentica clientes; o HTTP local não cifra os dados. Use dados sintéticos em rede controlada até haver autenticação e TLS.

`GET /api/experiments/{id}/sessions` lista as sessões do experimento, com paginação por `limit` (1 a 100, padrão 50) e `offset`; `GET /api/sessions/{id}` consulta uma sessão. `receipt_status` distingue cadastro pendente de arquivos recebidos e `processing_status` é sempre `unavailable`: nenhuma inferência é executada. O recebimento não comprova sincronização nem qualidade científica.

`GET /api/sessions/{id}/video` e `/events` disponibilizam os arquivos originais recebidos para inspeção; não são resultados de inferência. Assim como as demais rotas, não exigem autenticação.

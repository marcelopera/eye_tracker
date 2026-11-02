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
docker build -f services/api/Dockerfile -t eye-tracker-api .
docker run --rm -p 8000:8000 -v eye-tracker-data:/data eye-tracker-api
```

Para iniciar a base integrada ao webapp, use `docker compose up --build -d --wait`
na raiz. O Compose fornece Python e uv nas imagens e publica a API pelo webapp.

Para executar os testes em um container, sem instalar Python no host:

```sh
docker build -f services/api/Dockerfile --target test -t eye-tracker-api-test .
```

## Recebimento provisório de coletas

`GET /api/published-experiments/{code}` consulta um experimento publicado. `POST /api/sessions` recebe `experiment_id`, `local_id` (UUID) e `participant_code` e retorna um ID de servidor; repetir com os mesmos dados recupera a sessão. `PUT /api/sessions/{id}/files` recebe multipart com `video`, `events`, `video_sha256` e `events_sha256`. O servidor confere os hashes, a associação dos metadados, a presença de faixa de vídeo e os limites de 500 MB para o vídeo e 5 MB para os eventos. A repetição com os mesmos hashes é idempotente; outros hashes geram conflito. Arquivos e banco ficam no volume de dados. A resposta indica recebimento, não processamento.

O formato recebido é o `sessao.json` original do protótipo com `face.mp4`, não um manifesto v1. Não há dados suficientes para afirmar sincronização, perfil físico ou validade científica. A API não autentica clientes; o HTTP local não cifra os dados. Use dados sintéticos em rede controlada até haver autenticação e TLS.

`GET /api/experiments/{id}/sessions` lista as sessões do experimento, com paginação por `limit` (1 a 100, padrão 50) e `offset`; `GET /api/sessions/{id}` consulta uma sessão. `receipt_status` distingue cadastro pendente de arquivos recebidos e `processing_status` indica o estado da última execução (ou `unavailable` quando ainda não há execução). O recebimento não comprova sincronização nem qualidade científica.

`GET /api/sessions/{id}/video` e `/events` disponibilizam os arquivos originais recebidos para inspeção; não são resultados de inferência. Assim como as demais rotas, não exigem autenticação.

## Processamento do olhar

A API agora possui fila persistente local de execuções e consulta/exportação dos resultados. Veja [pipeline: instalação, configuração e rotas](../../docs/pipeline.md). O Compose inclui o runtime CPU e prepara os seis arquivos dos modelos automaticamente no serviço `models`, com hashes fixados e cache no volume `gaze_models`. A API aguarda a preparação e monta o volume somente para leitura. A capability `gaze_processing` indica a presença do runtime; modelos ausentes ou incompatíveis continuam sendo rejeitados na execução.

Para construir o estágio de testes, use a raiz como contexto: `docker build -f services/api/Dockerfile --target test -t eye-tracker-api-test .`.

A preparação automática de uma coleta instrumentada está disponível em `POST /api/sessions/{id}/analysis-config`, com medidas do piloto em `settings`. Retorna configuração e pendências, verifica o hash dos metadados originais e não inicia inferência. Veja [operação, contrato e limites](../../docs/coleta-instrumentada.md).

## Demonstração em MP4

O protocolo atual é atribuído automaticamente aos novos experimentos e aos rascunhos antigos na publicação. A rota legada `PUT /api/experiments/{id}/protocol` está depreciada; o webapp não precisa chamá-la.

`POST /api/sessions/{id}/demonstration` prepara a configuração automática, valida a instrumentação e cria uma execução `kind=demonstration` na fila persistente. O worker executa a inferência e depois renderiza o MP4 em CPU. `GET /api/runs/{id}` informa estado, progresso e `demonstration_available`. Uma execução só termina como `completed` após a publicação do arquivo completo; falhas permitem nova tentativa. Arquivos originais e o estímulo são conferidos por SHA-256. A migração do SQLite preserva o histórico existente como `kind=analysis`.

`GET /api/runs/{id}/demonstration` serve o MP4 para reprodução, com suporte a Range; `?download=true` oferece o download. O resultado inclui estímulo, ponto calibrado e filtrado, câmera/recortes associados e pipeline, sem faixa superior de título. Usa o tempo e a rotação do estímulo. Lacunas curtas são preenchidas por interpolação linear das imagens, recortes e olhar entre duas amostras válidas consecutivas da fase de estímulo, separadas por no máximo 100 ms. O vídeo identifica os quadros interpolados; falhas de detecção e lacunas longas permanecem explícitas. Previsões e métricas de avaliação originais não são modificadas. O erro de validação e as dimensões da tela vêm da sessão. O arquivo não inclui áudio.

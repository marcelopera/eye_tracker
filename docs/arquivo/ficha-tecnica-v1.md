# Ficha técnica v1

> **Histórico — substituída pelo [ADR-0001](../adr/0001-recorte-atual.md); não implementar sem decisão.**

Ficha técnica — Eye tracking por vídeo em celular (100% on‑premises)
Versão 1 — 22/10/2026.
Escopo: coleta (Android) → processamento (detector de landmarks próprio + calibração) → análise (painel web).
Tudo numa máquina do laboratório, via `docker compose`, numa LAN sem exposição à internet.
Formato de cada etapa: Fazer · Atenção · Pronto quando.
0. Decisões fechadas


Tema
Decisão
Por quê
Execução
1 máquina, `docker compose`, LAN do laboratório
Simples; dado biométrico não sai do laboratório
Borda
Traefik v3, único container com porta publicada
Rotas, TLS, rate limit
Identidade
Keycloak, realm próprio, OIDC + PKCE
Mesmo fluxo para web e Android
Serviços
`bff` + `experimento` + `coleta` + `analise` (Quarkus, JVM)
Três contextos reais; um quarto serviço seria artificial
ML
1 `worker` Python disparado por evento; FastAPI só para health/versão
Processar vídeo leva minutos, não cabe numa chamada HTTP
Landmarks
Seu detector, como biblioteca Python versionada, inferência em ONNX Runtime
O mesmo código roda no worker e na avaliação da tese
Gaze
Regressão por sessão (`fit` na calibração, `predict` no restante)
Não confundir com o treino do detector
Fila
Kafka 4.x KRaft (`apache/kafka`), 1 broker
Requisito do projeto; configuração mínima
Banco
PostgreSQL 18, 1 instância; 1 schema + 1 role por serviço; banco separado para o Keycloak
Isolamento sem custo operacional
Storage
SeaweedFS (API S3), URLs pré‑assinadas
O repositório community do MinIO foi descontinuado
Repo/CI
Monorepo GitHub; Actions só para build e teste
Nenhum dado real sai do laboratório
O que saiu com a remoção da nuvem: adaptadores Pub/Sub e Firebase, Terraform, budget kill switch, registries de nuvem, chaves HMAC. Agora cada coisa tem um caminho só.
Dois "fit" diferentes — não misture


Treino do detector
Calibração da sessão
O quê
Rede que localiza olhos, íris e pontos da face
Regressão features → (x, y) na tela
Quando
Offline, ao longo da pesquisa
A cada sessão, no worker
Onde
Máquina com GPU / scripts de treino
Worker (CPU)
Artefato
`model.onnx` + `model_card.json`
`calibracao.joblib` + coeficientes em JSON
Fluxo
```
Web (pesquisador): cria experimento → PUT do estímulo na URL assinada
experimento ──estimulo-enviado──► worker (normaliza) ──estimulo-processado──► experimento: PRONTO (código + QR)
Android (pesquisador logado): código → baixa estímulo → TCLE ok → preparo
UMA gravação contínua da câmera frontal:
marcador A → calibração → estímulo → validação → marcador B
PUT dos arquivos nas URLs assinadas → POST /concluir
coleta ──sessao-coletada──► worker:
confere sha256 → landmarks (seu detector) → sincronização → fit/predict → qualidade → resultados
worker ──sessao-processada──► coleta (status) e analise (ingere) → painel: overlay, heatmap, AOIs, export
```
Etapa 0 — Ética e LGPD
Vale antes de coletar dados de qualquer pessoa além de você.
Fazer
Protocolo no CEP/Plataforma Brasil: Res. CNS 466/2012 (ou 510/2016, se o comitê enquadrar assim). Até a aprovação, colete só vídeos seus.
O TCLE precisa cobrir explicitamente:
gravação de vídeo do rosto (dado biométrico = dado pessoal sensível);
uso dos vídeos para treinar e avaliar o detector — é uso secundário; se não estiver no TCLE, você não pode usar;
uso de imagens do rosto em publicações (autorização separada; o padrão é não usar);
compartilhamento como dataset público — decida agora; sem isso no TCLE, não dá para publicar depois;
retenção: a Res. 466 exige guardar os dados por 5 anos após o término da pesquisa;
retirada do consentimento: dados apagados; modelos já treinados não são retreinados (deixe escrito).
Identidade fora do sistema: TCLE em papel (ou assinatura gov.br) e planilha código↔nome criptografada, fora do servidor. O sistema só conhece `P-0001`.
Critério de exclusão: histórico de epilepsia fotossensível (o app pisca a tela nos marcadores).
Atributos para análise de viés (óculos, cor dos olhos, tom de pele) só se estiverem no protocolo. Tom de pele é dado sensível.
Atenção
Base legal na LGPD: consentimento (art. 11, I) e/ou estudo por órgão de pesquisa (art. 11, II, "c"). Confirme com o CEP e com o encarregado de dados da universidade.
Colegas "testando" o sistema também são participantes.
Não crie no sistema campos de texto livre que convidem a digitar nome.
Pronto quando
Parecer aprovado.
Versão do TCLE registrada em cada sessão.
Procedimento de exclusão de participante testado de ponta a ponta.
Etapa 1 — Spike de viabilidade (sem backend)
Objetivo: provar captura + sincronização e medir o teto do método antes de construir o resto. O app do spike vira o app final, então não o jogue fora.
Fazer
App Android mínimo: marcador A → calibração → estímulo → validação → marcador B, gravando a câmera frontal. Arquivos salvos localmente e copiados com `adb pull`.
Notebook: sincronização (Etapa 8) e FPS real calculado pelos PTS.
Teto com landmarks manuais:
anote à mão o centro da íris e os cantos dos olhos em ~5 frames por ponto de calibração/validação de algumas sessões suas (clique em notebook ou no CVAT);
rode fit/predict e meça o erro na validação.
Se o erro com landmarks humanos já for ruim, o problema é o setup (resolução, distância, luz), não o detector.
Esse número entra na tese como limite superior do método.
Grave 2–3 sessões em condições diferentes (luz, óculos) para ver a sensibilidade.
Teste térmico: 10 min gravando e reproduzindo; confira FPS real e temperatura.
Conta de ordem de grandeza (premissas: campo de visão horizontal da câmera frontal ~75°, rosto a 35 cm, olho girando num raio de ~10–12 mm)


Resolução
mm por pixel no rosto
Íris (~11,7 mm)
1 px de erro no centro da íris
1080p
≈ 0,28
≈ 40 px
≈ 1,3–1,6°
720p
≈ 0,42
≈ 28 px
≈ 2,0–2,4°
1° a 35 cm ≈ 0,6 cm na tela. Um celular deitado tem ~14–16 cm de largura.
Conclusão: precisão sub‑pixel no centro da íris é o que manda. Use 1080p, distância fixa e suporte.
Parte do erro é ruído (some ao agregar em fixações); parte é viés (a calibração absorve).
Pronto quando
Sincronização com erro ≤ 1 frame da câmera.
Erro de validação com landmarks manuais conhecido e compatível com o tamanho dos AOIs que você quer analisar.
Etapa 2 — Infraestrutura on‑prem
2.1 Máquina
Ideal: máquina dedicada com Linux (Ubuntu LTS) para os dias de coleta. WSL2 serve para desenvolver.
RAM: 16 GB no mínimo para o stack; 32 GB se treinar o detector na mesma máquina. GPU NVIDIA só faz falta no treino.
Disco: ≈ 0,1 GB por minuto de gravação 1080p30 (meça o bitrate do seu aparelho). Sessão de 7 min ≈ 0,7–0,9 GB + derivados.
Criptografia de disco obrigatória: LUKS no Linux; no Windows, BitLocker (cobre o disco virtual do WSL).
Se ficar no WSL2:
volumes Docker no ext4 do WSL, nunca em `/mnt/c`;
`.wslconfig`: defina `memory=` (por padrão o WSL usa só parte da RAM do Windows);
acesso pela LAN: `networkingMode=mirrored` (Windows 11 22H2+) + regra no firewall Hyper‑V liberando 443/9443 de entrada. Com Docker Desktop, confira o Firewall do Windows;
desligue a suspensão e agende o Windows Update fora dos dias de coleta;
GPU: use o driver NVIDIA do Windows; não instale driver NVIDIA Linux dentro do WSL.
2.2 Rede do laboratório
Roteador dedicado para o laboratório: servidor no cabo, celular no Wi‑Fi dele. O Wi‑Fi institucional (eduroam e afins) muitas vezes isola os clientes, e aí o celular não alcança o servidor.
IP fixo para o servidor (reserva no DHCP). Exemplo: `192.168.50.10`.
Sem DNS: um único host, com roteamento por caminho:


URL
Destino
Quem acessa
`https://192.168.50.10/`
`web` (nginx com o build do React)
LAN
`https://192.168.50.10/api/…`
`bff`
LAN
`https://192.168.50.10/auth/realms/eyetracking/…` e `/auth/resources/…`
`keycloak`
LAN
`https://192.168.50.10:9443/…`
`seaweedfs` S3 (URLs assinadas)
LAN
`https://127.0.0.1:8443/…`
admin do Keycloak, dashboard do Traefik
só a própria máquina
O S3 tem porta própria porque a assinatura SigV4 inclui o caminho: um prefixo `/s3` quebraria a assinatura.
TLS com `mkcert`: CA local + certificado com o IP no SAN.
Instale a CA no PC do pesquisador e no celular — a tela de login abre no Chrome e precisa confiar no certificado.
No app, embuta a CA em `res/raw` e confie nela via `network_security_config`.
Alternativa, se tiver domínio e internet na LAN: Let's Encrypt via DNS‑01, com o registro DNS apontando para o IP privado. Cuidado com roteadores que bloqueiam DNS rebinding.
2.3 Redes Docker
`borda`: só o Traefik, com as portas publicadas.
`interna` com `internal: true`: Traefik + todos os serviços e a infraestrutura. Nenhum container de dados tem saída para a internet.
Consequência: containers não alcançam o IP da LAN. A comunicação interna é sempre por nome (`http://keycloak:8080`).
2.4 Traefik
Use o provider de arquivo (rotas em YAML) e não monte o `docker.sock` (acesso a ele equivale a root no host). Se optar por labels, use `exposedByDefault=false`.
Entrypoints: `websecure` `:443`, `s3` `:9443`, `admin` `127.0.0.1:8443`.
O `readTimeout` padrão é 60 s, e upload de vídeo pelo Wi‑Fi passa disso. Aumente no entrypoint `s3` (ex.: 30 min).
Não use o middleware `buffering` na rota do S3.
Rate limit leve em `/api` e `/auth`. Headers de segurança. Access log ligado.
2.5 Keycloak
Modo `start` (não `start-dev`), com banco `keycloak` no Postgres.
Variáveis‑chave:
```
KC_HOSTNAME=https://192.168.50.10/auth
KC_HTTP_RELATIVE_PATH=/auth
KC_HTTP_ENABLED=true # TLS termina no Traefik
KC_PROXY_HEADERS=xforwarded
KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true
KC_HEALTH_ENABLED=true
KC_DB=postgres
KC_DB_URL=jdbc:postgresql://postgres:5432/keycloak
KC_DB_POOL_MAX_SIZE=20
KC_BOOTSTRAP_ADMIN_USERNAME / KC_BOOTSTRAP_ADMIN_PASSWORD # só no .env
```
Backchannel dinâmico: o BFF fala com `http://keycloak:8080/auth/realms/eyetracking`, e o `iss` dos tokens continua sendo a URL pública.
Teste: o `iss` do token deve ser igual ao `issuer` do discovery. Se divergir, configure `quarkus.oidc.token.issuer`.
Health na porta 9000, com o mesmo prefixo: `/auth/health/ready`. A imagem não tem `curl`; no healthcheck, use `bash` com `/dev/tcp`.
Realm `eyetracking` versionado em JSON e importado com `--import-realm`.
Só importa se o realm ainda não existir; mudanças feitas pela UI não voltam para o JSON.
Clientes públicos com PKCE S256: `painel-web` (redirect `https://192.168.50.10/`) e `app-android` (redirect com esquema próprio, ex.: `br.edu.seulab.eyetracking:/oauth2redirect`).
Papéis `pesquisador` e `admin-lab`. Auto‑cadastro desligado. Proteção contra força bruta ligada.
Sessão SSO de ~8 h (um dia de coleta); access token curto.
Audience mapper para a API, com validação de `aud` no BFF.
`/auth/admin` e `/auth/realms/master` só no entrypoint `admin`.
2.6 PostgreSQL 18
Volume em `/var/lib/postgresql`. Isso mudou na versão 18; tutoriais antigos montam `/var/lib/postgresql/data` e perdem dados ao recriar o container.
Scripts em `/docker-entrypoint-initdb.d` só rodam com o volume vazio. Se falharem no meio, não rodam de novo: em dev, use `docker compose down -v`.
Banco `eyetracking` com schemas `experimento`, `coleta` e `analise`, cada um pertencente a uma role própria (`svc_experimento`…) e com `search_path` por role. Banco `keycloak` separado.
Flyway por serviço, só no próprio schema. Sem join entre schemas.
A soma dos pools (serviços + Keycloak) tem que ficar abaixo de `max_connections`.
Datas sempre em `timestamptz` (UTC).
2.7 Kafka 4.x (KRaft, 1 nó)
Imagem `apache/kafka:<versão fixa>`.
Configurando por variáveis de ambiente, os padrões do arquivo da imagem não valem. Explicite tudo:
```
KAFKA_NODE_ID=1
KAFKA_PROCESS_ROLES=broker,controller
KAFKA_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093
KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092
KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER
KAFKA_CONTROLLER_QUORUM_VOTERS=1@kafka:9093
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
KAFKA_INTER_BROKER_LISTENER_NAME=PLAINTEXT
CLUSTER_ID=<gerado uma vez com kafka-storage.sh random-uuid>
KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 # sem isso o padrão é 3 e nada funciona
KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1
KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1
KAFKA_SHARE_COORDINATOR_STATE_TOPIC_REPLICATION_FACTOR=1
KAFKA_SHARE_COORDINATOR_STATE_TOPIC_MIN_ISR=1
KAFKA_LOG_DIRS=/var/lib/kafka/data # o exemplo oficial usa /tmp → perde dados
KAFKA_AUTO_CREATE_TOPICS_ENABLE=false
KAFKA_HEAP_OPTS=-Xms512m -Xmx512m
```
Volume nomeado em `/var/lib/kafka/data`.
Nenhuma porta publicada; para depurar, use `docker compose exec kafka /opt/kafka/bin/...`.
Tópicos criados por um container de init (`--if-not-exists`). Chave das mensagens = `sessaoId`.
2.8 SeaweedFS (S3)
Imagem `chrislusf/seaweedfs:<versão fixa>` com o comportamento de `weed mini`: processo único, adequado para nó único servindo URLs assinadas. Volume em `/data`.
Credenciais via `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`; com elas definidas, o acesso anônimo fica fechado. Identidades separadas por serviço podem vir depois, se der tempo.
Deixe a Admin UI em loopback (é o padrão quando `WEED_ADMIN_PASSWORD` não está definido).
Um bucket `eyetracking`, com prefixos:
```
estimulos/{experimentoId}/original.mp4 | normalizado.mp4
sessoes/{sessaoId}/bruto/face.mp4, sync.json, calib.json, device.json, manifest.json
sessoes/{sessaoId}/derivados/landmarks/{versaoDetector}.parquet
sessoes/{sessaoId}/resultados/{versaoPipeline}/gaze.parquet, gaze.csv.gz, qualidade.json, calibracao.joblib
modelos/landmarks/{versao}/model.onnx, model_card.json
```
CORS do bucket, aplicado por container de init (`aws s3api put-bucket-cors`): origem `https://192.168.50.10`, métodos PUT/GET/HEAD, expondo `ETag`.
Clientes S3:
endereçamento path‑style (senão o SDK gera `bucket.host`, que exige DNS curinga);
o presigner usa o endpoint público (`https://192.168.50.10:9443`); o cliente interno usa `http://seaweedfs:8333`;
se o SDK recente der erro de checksum: `WHEN_REQUIRED` no Java; no Python, `AWS_REQUEST_CHECKSUM_CALCULATION=when_required` e `AWS_RESPONSE_CHECKSUM_VALIDATION=when_required`.
Tudo o que o presigner assinar (ex.: `Content-Type`) o cliente tem que enviar igual; senão dá `SignatureDoesNotMatch`.
Upload: um PUT único basta até 1–2 GB na LAN. Multipart só se der problema.
2.9 Compose no dia a dia
Versões fixas em todas as imagens (nada de `latest`).
`depends_on` com `service_healthy` / `service_completed_successfully`. Containers de init: tópicos, bucket e CORS.
Limite de memória por container e `restart: unless-stopped`.
Rotação de log (`json-file` com `max-size: 10m` e `max-file: 3`); sem isso o disco enche.
`.env` fora do git (versione só o `.env.example`); senhas geradas, arquivo com permissão 600.
Opcional: `compose.dev.yml` publicando Postgres e Kafka só em `127.0.0.1`, para rodar o Quarkus em dev mode no host. O Kafka precisa de um listener extra anunciado para o host. Nunca use isso no modo laboratório.
2.10 Backup
Diário: `pg_dump -Fc` dos bancos `eyetracking` e `keycloak` + cópia do bucket (rclone ou restic) para disco externo criptografado. Uma cópia fora da sala.
Teste a restauração antes da primeira coleta real.
A exclusão de um participante só chega aos backups quando eles rotacionam. Escreva isso no protocolo.
Pronto quando
Com uma única linha de comando (`docker compose up -d`), uma máquina limpa sobe tudo saudável.
Do celular, login e upload funcionam.
De fora da LAN, nada responde.
Restauração testada.
Etapa 3 — Contratos (antes dos serviços)
Convenções (`docs/convencoes.md`) — a maior fonte de bug silencioso:
Tela: pixels físicos, origem no canto superior esquerdo, x cresce para a direita e y para baixo.
Vídeo: `x_video, y_video ∈ [0,1]` sobre a área do conteúdo, sem as tarjas. Valor fora de [0,1] = olhando fora do vídeo.
Imagem da câmera: pixels depois de aplicar a rotação; gravação sem espelhamento.
Olhos: "esquerdo" é o olho esquerdo do participante. Na câmera frontal sem espelho, ele aparece à direita da imagem.
Tempo:
no aparelho, tudo em `System.nanoTime()`; no vídeo da câmera, o PTS;
`t_estimulo_ms` = 0 na apresentação do frame 0;
`frame_estimulo` começa em 0.
REST do BFF (OpenAPI versionado; cliente TypeScript gerado a partir dele):
`POST /api/experimentos` → `{id, urlUploadEstimulo}`
`POST /api/experimentos/{id}/estimulo/concluir`
`GET /api/experimentos` e `GET /api/experimentos/{id}`
`GET /api/experimentos/codigo/{codigo}` → protocolo + URL de download do estímulo
`POST /api/sessoes` → `{sessaoId, urlsUpload}`
`POST /api/sessoes/{id}/urls-upload` (renova as URLs)
`POST /api/sessoes/{id}/concluir` (manifest com sha256 e tamanhos)
`POST /api/sessoes/{id}/interromper`
`GET /api/sessoes?experimentoId=`
`POST /api/sessoes/{id}/reprocessar`
`DELETE /api/participantes/{codigo}` (retirada de consentimento)
`GET /api/analise/sessoes/{id}/gaze`
`GET /api/analise/experimentos/{id}/heatmap?inicioMs=&fimMs=`
`POST /api/analise/experimentos/{id}/export`
Eventos (JSON Schema em `contracts/eventos`):
```json
{"idEvento":"uuid","tipo":"coleta.sessao-coletada","versao":1,
"ocorridoEm":"2026-10-22T11:00:00Z","sessaoId":"uuid","dados":{}}
```
O prefixo do tópico é o serviço que publica:
| Tópico | Produtor | Consumidor |
|---|---|---|
| `experimento.estimulo-enviado` | experimento | worker |
| `ml.estimulo-processado` | worker | experimento |
| `coleta.sessao-coletada` | coleta | worker |
| `ml.sessao-iniciada` | worker | coleta |
| `ml.sessao-processada` | worker | coleta, analise |
| `ml.sessao-falhou` | worker | coleta |
| `coleta.participante-excluido` | coleta | analise |
Cada tópico tem o seu `.dlq`.
O payload leva chaves do storage e sha256, nunca o dado em si.
Mudanças só aditivas; se quebrar compatibilidade, crie uma `versao` nova.
Pacote da sessão: `manifest.json` com `versaoSchema`, lista de arquivos, sha256, tamanhos e versão do app.
`landmarks_v1`: lista fixa e ordenada de pontos. É a interface entre o seu detector e o resto do sistema (ver Etapa 7).
`gaze_v1` (uma linha por frame da câmera):
identificação e tempo: `frame_cam`, `t_cam_ms`, `fase` (`calibracao|estimulo|validacao|outro`), `frame_estimulo`, `t_estimulo_ms`;
posição: `x_tela_px`, `y_tela_px`, `x_video`, `y_video`;
qualidade: `valido`, `motivo_invalido`, `confianca`.
Pronto quando: schemas versionados e fixtures de exemplo sendo validadas no CI.
Etapa 4 — Serviços Quarkus
Comum aos quatro
Quarkus LTS, Java LTS (21 ou 25), imagem JVM.
`quarkus-oidc` em todos: o BFF propaga o token e os serviços validam de novo. É barato e dá o `sub` para auditoria.
`@RolesAllowed("pesquisador")` + checagem de dono do experimento.
Erros em `application/problem+json`. Logs em JSON com `sessaoId`, `experimentoId` e `idEvento` no MDC.
Máquina de estados explícita; transição inválida → 409.
Consumidor idempotente: tabela `evento_processado(id_evento)` gravada na mesma transação da mudança de estado.
SmallRye Kafka: o `failure-strategy` padrão é `fail` (o canal para de consumir na primeira exceção). Use `dead-letter-queue`.
Publicação: grave o estado e publique. Um reconciliador agendado republica o que ficou parado — dispensa outbox/Debezium.
Testes com Dev Services (Postgres, Kafka, Keycloak).
bff
Sem banco: valida JWT, agrega chamadas, define timeouts dos REST clients.
Se começar a ter regra de negócio, está errado.
experimento
Estados: `RASCUNHO → PROCESSANDO_ESTIMULO → PRONTO | REJEITADO`; `PRONTO → ENCERRADO`.
Código curto de 6 caracteres no alfabeto Crockford base32 (exclui I, L, O, U). O QR é gerado no front a partir do código.
Protocolo por experimento em JSON: nº de pontos, tempo por ponto, pontos de validação, marcadores, distância.
Experimento com sessões fica congelado. Trocar estímulo ou protocolo = criar um experimento novo.
coleta
Participante com código global (o mesmo em todos os experimentos), gerado pelo sistema e anotado na planilha off‑line.
Estados da sessão: `CRIADA → COLETADA → PROCESSANDO → PROCESSADA | FALHOU`, mais `INTERROMPIDA` (o app avisa) e `ABANDONADA` (marcada pelo reconciliador).
Ao criar a sessão:
valida que o experimento está `PRONTO`;
registra o código do participante, a versão do TCLE e quem registrou o consentimento;
devolve as URLs de upload (validade ~1 h), com chaves fixas.
`concluir`: `HEAD` em cada objeto (existe e o tamanho bate) → `COLETADA` → publica o evento.
Consome os eventos do worker para atualizar o status.
Reconciliador:
`COLETADA` há > 15 min, ou `PROCESSANDO` além do tempo máximo → republica, com contador; estourou as tentativas → `FALHOU`;
`CRIADA` há > 24 h → `ABANDONADA`.
Exclusão de participante: apaga objetos e linhas e publica `participante-excluido`.
analise
Consome `sessao-processada`: lê `gaze.csv.gz` e `qualidade.json` e grava no Postgres com `COPY`. Ler Parquet em Java é trabalho desnecessário.
Guarda resultados por versão do pipeline, sem sobrescrever; o painel escolhe a versão. É assim que você compara versões do detector na tese.
Heatmap agregado no servidor (grade fixa, janela de tempo). AOIs estáticos por intervalo de tempo.
Export: URLs assinadas para os Parquet + dicionário de dados + protocolo + versões.
Pronto quando
O fluxo completo passa nos testes com dados falsos.
Reentregar o mesmo evento não duplica nada.
Etapa 5 — Web (painel)
React + Vite + TypeScript, servido por nginx com fallback para `index.html`.
Login com `react-oidc-context` (oidc-client-ts), Authorization Code + PKCE. Web e API ficam na mesma origem, então não há CORS na API.
Upload do estímulo: PUT direto na URL assinada, com barra de progresso via XHR/axios (`fetch` não informa progresso de upload).
Status por polling a cada 3–5 s. WebSocket/SSE não é necessário.
Tela do experimento: código + QR, protocolo e tabela de sessões com status e qualidade.
Visualizador da sessão:
`<video>` + `<canvas>` sincronizados por `requestVideoFrameCallback`, com `frame = round(mediaTime × fps)`;
ao navegar, faça seek para `(frame + 0.5) / fps`, para não cair na borda entre dois frames;
use Chrome/Edge no laboratório.
Mostre a qualidade antes do heatmap: acurácia, precisão, % de amostras válidas, piscadas, resíduo de sincronização.
Não exiba o vídeo do rosto por padrão. Só para `admin-lab`, com log de acesso.
Etapa 6 — App Android (captura)
Aparelho e ambiente
1–2 modelos fixos.
Celular (< 600dp) é mais simples. Em tablet com Android 16 e `targetSdk ≥ 36`, o travamento de orientação é ignorado. O tablet dá mais resolução relativa de tela; se usar, trate a orientação explicitamente.
Suporte fixo e distância de 30–40 cm, medida com régua e digitada pelo pesquisador em cada sessão.
Luz ambiente constante, sem janela atrás do participante (a contraluz escurece o rosto).
Brilho da tela fixado pelo app (`screenBrightness`). O brilho automático muda a iluminação do rosto e o tamanho da pupila.
Não Perturbe ligado; bateria carregada.
Fluxo
Login com AppAuth‑Android (Custom Tab + PKCE). URL do servidor configurável, por exemplo via QR de configuração.
Código do experimento digitado ou lido do QR.
Download do estímulo para o armazenamento privado do app, conferindo o sha256.
Tela de preparo: preview com oval‑guia para enquadramento e distância.
Uma gravação contínua: marcador A → calibração → descanso de ~2 s → estímulo → validação → marcador B.
Câmera (CameraX `VideoCapture`)
Frontal, `Quality.FHD`, 30 fps fixo (`setTargetFrameRate`), estabilização desligada (`setVideoStabilizationEnabled(false)`), sem áudio.
Grave com `FileOutputOptions` no diretório privado do app — não no MediaStore, que manda o vídeo para a galeria e o backup de fotos.
A gravação sai sem espelhamento (padrão `MIRROR_MODE_OFF`); o preview sai espelhado. Documente.
Espere o evento `Start` e ~1–2 s de convergência da exposição antes do marcador A. No `Finalize`, confira o código de erro.
Bitrate: mantenha alto. A compressão borra a borda da íris, e isso prejudica o detector mais do que o custo de disco. Para padronizar entre aparelhos, use `setTargetVideoEncodingBitRate`.
Exposição: a luz da própria tela muda a exposição automática.
Avalie travar AE/AWB (Camera2Interop, `CONTROL_AE_LOCK`) depois da convergência.
Isso facilita detectar os flashes, mas cenas muito claras ou escuras podem saturar.
Player (Media3 ExoPlayer)
Estímulo local, tela cheia, modo imersivo, `RESIZE_MODE_FIT`.
Logue cada frame com `VideoFrameMetadataListener` (`presentationTimeUs`, `releaseTimeNs`) e os frames perdidos (`onDroppedVideoFrames`).
Logue o retângulo real do vídeo na tela (px, depois do layout e do modo imersivo), além dos insets e do recorte da câmera (cutout).
Alvos, marcadores e interrupções
Para cada alvo de calibração e cada flash, registre o `frameTimeNanos` do Choreographer (ou `withFrameNanos` no Compose) do frame em que aparecem — não o momento da chamada no código.
Marcador = 2 flashes brancos de ~200 ms em fundo preto, separados por ~1 s (no máximo 3 por segundo, WCAG 2.3.1), longe da calibração.
Qualquer interrupção (`onPause`, ligação, notificação, rotação) marca a sessão como `INTERROMPIDA`. Não tente remendar.
`device.json`
Aparelho e app: modelo, versão do Android, versão do app.
Tela: resolução, `xdpi/ydpi`, taxa de atualização, retângulo do vídeo.
Câmera: resolução e FPS reais, rotação, distância focal, tamanho físico do sensor, intrínsecos e distorção (se o aparelho expuser).
Posição da câmera em relação à tela — meça uma vez por modelo.
Ambiente: lux do sensor de luz e status térmico (`getCurrentThermalStatus`) no início e no fim.
Upload e dados no aparelho
WorkManager, com um trabalho único por sessão.
PUT em streaming (OkHttp) e backoff exponencial.
Resposta 403 → pede URLs novas. Se o refresh do token falhar, notifica "faça login".
Estado de cada sessão persistido (Room), para sobreviver a crash.
Só apague os arquivos do aparelho depois de `PROCESSADA` — é o worker que confere o sha256.
Backup: configure `dataExtractionRules` excluindo os arquivos tanto do backup em nuvem quanto da transferência entre aparelhos. No Android 12+, `allowBackup=false` sozinho não cobre a transferência.
Distribuição: APK release assinado, instalado nos aparelhos do laboratório.
Pronto quando
10 sessões seguidas sem perda de arquivo.
FPS real estável.
Sessão interrompida é detectada.
Nada aparece na galeria.
Etapa 7 — Pipeline de landmarks (sua contribuição)
Arquitetura
Pacote Python `ml/landmarks` com API estável, em streaming (frame a frame): `detectar(frames) -> linhas landmarks_v1`.
O mesmo pacote é usado pelo worker e pelos scripts de avaliação da tese.
Treino (PyTorch, GPU, fora do compose) separado da inferência (ONNX Runtime, CPU, dentro do worker).
Pesos fora do git, em `modelos/landmarks/{versao}/`:
`model.onnx` + `model_card.json` (commit, manifesto do dataset, métricas, normalização de entrada, `landmarks_v1`, licenças dos dados);
sha256 conferido ao carregar.
Escopo — onde gastar esforço
Se detectar o rosto não é contribuição sua, use um detector pronto só para a caixa do rosto (ex.: YuNet do OpenCV; confira a licença). Concentre o trabalho em olhos e íris.
Defina o `landmarks_v1` pelo que o gaze precisa (~20–30 pontos), não por 68/98 pontos genéricos. Sugestão:
por olho: 2 cantos, centro da íris, ≥ 5 pontos na borda da íris, 2–3 pontos em cada pálpebra;
na face: ponta e ponte do nariz, cantos da boca e queixo (para a pose da cabeça por PnP);
por ponto: `x`, `y`, `confianca`, `visivel`.
Desenho clássico:
rosto;
recorte alinhado;
recorte dos olhos em resolução nativa;
pontos finos com refinamento sub‑pixel (heatmap + soft‑argmax/integral);
elipse ajustada na borda da íris;
filtro temporal;
piscada.
Armadilhas técnicas
Pálpebra cobrindo a íris: o centróide da região visível puxa o centro para baixo. Ajuste círculo/elipse nos pontos de borda visíveis.
Paridade de pré‑processamento entre treino e inferência (RGB/BGR, normalização, escala do recorte, interpolação): coloque no pacote e teste.
Decodificador: extraia os frames para anotação com o mesmo decodificador da inferência (PyAV). Conversões YUV→RGB diferentes (faixa limitada × completa) mudam os pixels.
Rotação do MP4: aplique a matriz de rotação e teste com um vídeo de orientação conhecida.
Filtro temporal (ex.: One Euro): reduz o tremor, mas não pode atrasar sacadas. Avalie as duas coisas.
Piscada: marque como inválido; não interpole através dela na análise.
Condições difíceis: óculos (reflexo), maquiagem, íris escura em luz visível, pouca luz (ruído e borrão). Estratifique a avaliação por elas.
Memória: decodifique e processe em streaming. 9.000 frames 1080p RGB na memória ≈ 56 GB.
Dados e anotação
Pré‑treino com bases públicas (ex.: WFLW, 300‑W, UnityEyes sintético, BioID, GI4E). Quase todas são só para pesquisa/uso não comercial, e algumas proíbem redistribuir ou publicar imagens. Confira uma a uma.
Ajuste fino e teste com frames seus: câmera frontal de celular ≠ webcam dos datasets. Precisa de TCLE cobrindo esse uso.
Ferramenta de anotação on‑prem: CVAT (pontos/esqueleto, interpolação em vídeo; é pesado, rode à parte) ou Label Studio (mais leve).
Protocolo de anotação escrito, com exemplos: definição de cada ponto e o que fazer em piscada/oclusão (`visivel=false`).
Anote ~10% duas vezes: o erro entre anotadores é o piso de ruído do rótulo. Você não pode afirmar erro abaixo dele.
Amostre frames diversos (direções de olhar, piscadas, poses), não consecutivos.
Divida por participante: nunca a mesma pessoa em treino e teste. Considere também dividir por aparelho.
Os frames de calibração trazem rótulo de olhar de graça (a posição do alvo) e servem para a avaliação ponta a ponta.
Avaliação (o que a banca vai pedir)
Landmarks: NME (diga qual normalização: interocular ou interpupilar), FR@0,1 e AUC@0,1 (curva CED).
Centro do olho/íris:
erro normalizado `e = max(dE, dD) / d(E,D)`, com acurácia em e ≤ 0,05 / 0,10 / 0,25 (padrão BioID/GI4E);
erro em pixels na resolução nativa, nos seus dados.
Estabilidade temporal: desvio dos pontos durante as fixações da calibração.
Tempo: ms/frame na CPU do laboratório.
Ponta a ponta: erro de gaze na validação (em graus, cm e % da largura do vídeo), comparando seu detector × baseline × landmarks manuais (o teto da Etapa 1). É esse número que costura as duas partes da tese.
Baseline externo, só nos scripts de avaliação (fora do sistema): MediaPipe Face Landmarker, OpenFace 2.0 ou dlib. Se usar MediaPipe, as versões atuais só têm a API Tasks; tutoriais com `mp.solutions.face_mesh` não funcionam.
Prepare a justificativa da abordagem por landmarks: em gaze por celular, os melhores resultados da literatura vêm de modelos por aparência (CNN na imagem do olho), às vezes combinados com landmarks.
Reprodutibilidade
Seeds fixas, `uv.lock`, manifesto do dataset com hashes e commit registrado em cada execução.
MLflow é opcional (usa o Postgres e o S3 que você já tem). No início, planilha + `model_card.json` resolvem.
Exportação ONNX com opset fixo e teste de paridade (saída PyTorch × ONNX abaixo de uma tolerância).
Threads do ONNX Runtime fixas — mudar o número de threads pode alterar levemente os resultados.
Desacoplamento
Até o detector ficar bom, rode o sistema com um detector de referência atrás da mesma interface (o mesmo que vai servir de baseline) ou com os landmarks manuais.
O sistema não pode esperar a pesquisa, nem a pesquisa o sistema.
Etapa 8 — Sincronização, calibração e gaze
Sincronização (no worker)
PTS de cada frame da câmera (PyAV). Nunca `índice/fps`: a câmera do celular tem FPS variável.
Luminância média por frame → instantes dos flashes dos marcadores A e B.
Ajuste linear PTS da câmera → `nanoTime` do aparelho com os 4 flashes. Isso corrige o deslocamento e a deriva, e o resíduo estima o erro.
Para cada frame da câmera: qual frame do estímulo estava na tela (pelo log do player) e qual alvo de calibração/validação estava ativo.
Precisão esperada: ~±1 frame da câmera (33 ms). Serve para fixações e AOIs, não para dinâmica de sacadas. Escreva isso na tese.
Teste de sincronização: um estímulo de teste com flashes em frames conhecidos, comparado com o mapeamento.
O flash contrai a pupila e mexe na exposição: deixe ~2 s antes de calibrar ou começar o estímulo.
Estímulo (normalizado pelo worker)
`ffmpeg`: H.264, `yuv420p`, FPS constante (`-fps_mode cfr`), sem B‑frames (`-bf 0`), `+faststart`.
Confira com `ffprobe` que o primeiro frame tem PTS 0. Se não tiver, Android e navegador podem divergir em 1 frame.
Registre `fps`, `nFrames`, duração, resolução e sha256. O app baixa a versão normalizada.
O estímulo pode ter áudio (volume fixo); o áudio do participante não é gravado.
Calibração e validação
9 pontos (3×3) ou 13, cobrindo a área do vídeo com margem, em ordem aleatória.
Alvo que encolhe, com ponto central; 1,5–2 s por ponto.
Descarte os primeiros ~600–800 ms de cada ponto e use a mediana das features. Rejeite janelas com piscada ou variância alta.
Validação: 4–5 pontos diferentes dos de calibração, depois do estímulo (mede a deriva). Opcional: também antes.
Modelo de gaze (`fit`/`predict`)
Features:
centro da íris relativo aos cantos do olho, normalizado pela largura do olho;
abertura das pálpebras;
pose da cabeça (PnP com modelo 3D genérico + intrínsecos aproximados do `device.json`);
escala do rosto.
Baseline: Ridge ou polinômio de grau 2.
9 pontos são 9 amostras independentes, não 9 × 45 frames — frames da mesma fixação são correlacionados. Use poucas features e regularização; polinômio com muitas features sobreajusta.
Salve o `calibracao.joblib` e os coeficientes em JSON. `joblib` é pickle: depende da versão do scikit‑learn e nunca deve ser carregado de fonte externa.
Métricas:
acurácia (erro angular médio na validação);
precisão (RMS amostra a amostra durante fixação);
perda de dados (% inválido).
Conversão de unidades: px → cm (`xdpi`) → graus (distância medida).
Pós‑processamento: fixações por I‑DT, mais adequado que I‑VT a 30 Hz com ruído. Limiares em graus, configuráveis e registrados.
Critérios de exclusão de sessão (ex.: acurácia > X°, válidos < Y%) definidos antes de olhar os resultados.
Etapa 9 — Worker Python
Python com versão fixa (3.12/3.13) e `uv` com lock.
Imagem slim com `ffmpeg` (normalização), PyAV, onnxruntime, scikit‑learn, pyarrow e confluent‑kafka.
Jobs:
`estimulo-enviado` → valida e normaliza → `estimulo-processado` (ok ou motivo).
`sessao-coletada`:
publica `sessao-iniciada`;
baixa os arquivos e confere o sha256;
landmarks (com cache por versão do detector);
sincronização;
fit/predict;
qualidade;
grava em `resultados/{versaoPipeline}/`;
publica `sessao-processada` ou `sessao-falhou` (com etapa e motivo).
Kafka:
`enable.auto.commit=false`, com commit depois de terminar o job;
`max.poll.interval.ms` acima do pior tempo de processamento (ex.: 1 h);
um job por vez.
Em caso de erro: publica `falhou` e faz o commit, para que uma mensagem venenosa não trave a fila.
Idempotência por `sessaoId + versaoPipeline`: pula se o resultado já existe, a menos que venha `forcar=true`.
`versaoPipeline` = commit do worker + versão do detector + hash da configuração. Resultados imutáveis por versão.
FastAPI (opcional): `/health/live`, `/health/ready` (Kafka, S3 e modelo carregado) e `/versao`. Não exponha `fit`/`predict` por HTTP.
Disco temporário em volume próprio, limpo ao fim de cada job.
Meta de desempenho: processar uma sessão em poucos minutos, com o participante ainda na sala para repetir se a qualidade for ruim.
Teste "golden": um vídeo seu de 10 s com saída esperada (dentro de uma tolerância), rodando no CI.
Etapa 10 — Análise e painel
Primeiro a qualidade, depois o mapa: o painel mostra acurácia, precisão, % válido e resíduo de sincronização por sessão, e aplica os critérios de exclusão.
Heatmap:
kernel gaussiano com σ da ordem da acurácia (1–2°), em coordenadas de vídeo;
cada participante com o mesmo peso;
mostre o N incluído.
AOIs estáticos por intervalo de tempo: tempo de permanência, tempo até a 1ª fixação, nº de fixações, revisitas. AOI dinâmico (objeto em movimento) fica para depois.
Export com dicionário de dados (unidade e convenção de cada coluna), protocolo e versões. Os notebooks da tese leem o export, não o banco.
Etapa 11 — Monorepo, CI e deploy
```
apps/android/ apps/web/
services/bff/ services/experimento/ services/coleta/ services/analise/
ml/landmarks/ # seu detector: biblioteca + treino + avaliação
ml/worker/ # usa ml/landmarks
contracts/openapi/ contracts/eventos/ contracts/pacote-sessao/
infra/compose/ # compose, traefik, realm, scripts de init
docs/ # protocolo, convenções, dicionário de dados, roteiro de coleta
```
CI no GitHub Actions (runners do GitHub), com `dorny/paths-filter`:
Quarkus: `./mvnw verify` (Dev Services);
Python: `ruff` + `pytest`;
web: lint + build + testes;
Android: `assembleDebug` + testes unitários;
contratos: fixtures validadas contra os JSON Schemas e diff do OpenAPI.
Sem "módulo common" com regra de negócio compartilhada entre serviços.
Nenhum dado real no repositório nem no CI. Pastas de dados no `.gitignore`. Ligue secret scanning/push protection (se o plano permitir) ou rode gitleaks no CI.
Sem runner self‑hosted na máquina do laboratório: seria código de PR rodando onde estão os dados.
Deploy na máquina do laboratório: `git checkout <tag>` → `docker compose build` → `docker compose up -d`. A tag entra na versão do pipeline e do app.
Etapa 12 — Dia de coleta (checklist)
Antes
[ ] `docker compose ps` com tudo saudável; espaço em disco ok; backup de ontem ok.
[ ] Sessão de teste com você mesmo: sincronização e qualidade ok.
[ ] Celular carregado, Não Perturbe ligado, suporte posicionado, régua à mão, luz conferida.
Por participante
[ ] TCLE assinado (papel) → código atribuído na planilha off‑line.
[ ] No app: código do experimento, código do participante, versão do TCLE, distância medida.
[ ] Preparo (oval) → sessão → upload → aguardar processamento → conferir qualidade → repetir se preciso e se o participante aceitar.
Depois
[ ] Todas as sessões `PROCESSADA`.
[ ] Arquivos apagados do aparelho.
[ ] Ocorrências anotadas pelo código da sessão, nunca pelo nome.
Riscos principais


Risco
Efeito
Mitigação
Detector sem precisão sub‑pixel
1 px ≈ 1,3–2,4° de erro
1080p, distância fixa, recorte nativo, refinamento sub‑pixel, elipse, filtro temporal; medir cedo
Dessincronização câmera × estímulo
Mapa no frame errado
Flashes, log do player, PTS, teste de sincronização
Wi‑Fi isolando clientes
Celular não alcança o servidor
Roteador dedicado
Upload acima de 60 s
Falha no Traefik
`readTimeout` maior no entrypoint S3
Volume de vídeo
Disco cheio
~0,1 GB/min; monitorar; backup externo
Vazamento de biometria
Problema ético/legal
Nada exposto, disco criptografado, sem backup do app, pseudônimos, vídeo fora do painel
Escopo (sistema + detector + gaze)
Tese atrasa
Contrato `landmarks_v1`, baseline atrás da interface, trilhas paralelas
Luz da própria tela
Pupila e exposição variam
Luz ambiente constante, brilho fixo, avaliar travar AE/AWB
Sobreajuste da calibração
Erro alto fora dos pontos
Poucas features, regularização, validação separada
Dados de colegas sem aprovação do CEP
Inutilizáveis
Só você até a aprovação
Ordem de execução (duas trilhas em paralelo)


Trilha A — sistema
Trilha B — pesquisa (detector)
1. Spike (Etapa 1)
1. Protocolo de anotação + `landmarks_v1`
2. Infra compose (Etapa 2)
2. Pré‑treino com bases públicas
3. Contratos (Etapa 3)
3. Anotação dos seus frames (após o CEP)
4. experimento + web
4. Ajuste fino, avaliação, baseline
5. coleta + Android
5. Export ONNX + model card
6. worker com detector de referência
6. Troca do detector no worker → comparação ponta a ponta
7. analise + painel
8. CI + roteiro de coleta
Ponto de encontro das trilhas: `landmarks_v1` + `detectar()` + `modelos/landmarks/{versao}`.

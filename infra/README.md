# Containers

O [Compose da raiz](../compose.yaml) inicia o [webapp](../apps/web/), uma única
[API Python](../services/api/) e o serviço de preparação `models`. API e preparação
usam o mesmo Dockerfile com a raiz do repositório como contexto; o webapp tem seu próprio contexto.

```sh
docker compose up --build -d --wait
docker compose ps
```

A interface fica em [localhost:8080](http://localhost:8080). O Nginx serve o build
React e encaminha `/api/`, `/docs` e `/openapi.json` à API pela rede interna do
Compose. Na primeira execução, `models` baixa os arquivos oficiais do iTracker e do
MediaPipe e verifica os hashes fixados. A API aguarda essa etapa terminar com sucesso;
o webapp aguarda o healthcheck da API. O serviço `models` fica em `Exited (0)` quando
concluído, o que é esperado.

Todos os serviços executam com usuário sem privilégios, filesystem somente de
leitura e uma área temporária gravável. `experiment_data` guarda banco, vídeos e
resultados; `gaze_models` guarda os seis arquivos dos modelos. A preparação pode gravar
no volume dos modelos e a API o monta somente para leitura. Não é necessário criar
pastas nem ajustar permissões no host.

Nas próximas inicializações, arquivos válidos são reutilizados sem rede. Ausentes ou
corrompidos são baixados novamente com publicação atômica e verificação SHA-256.
Uma falha no download interrompe a inicialização; consulte `docker compose logs models`
e repita `docker compose up --build -d --wait` após restabelecer o acesso à internet.
Os modelos continuam fora do Git e das imagens, e os comandos manuais de download
permanecem disponíveis para execução fora do Compose.

`docker compose down` preserva os volumes. `docker compose down -v` remove tanto os
modelos quanto os dados dos experimentos. A pasta local `modelos/itracker` deixa de ser
usada pelo Compose; instalações existentes passam a usar o volume automático.

Copie [.env.example](../.env.example) para `.env` para alterar endereço e porta.
Para acesso pela rede local, configure `WEB_HOST=0.0.0.0` e utilize o IP do PC.

Comandos de operação, testes e limites da entrega estão no [README](../README.md).

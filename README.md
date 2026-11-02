# Eye tracking por vídeo no smartphone

Sistema de pesquisa que coleta vídeo no Android e processa estimativas de olhar no servidor. A base web contém uma interface React e um serviço FastAPI, gerenciado com uv, executados em containers.

**Celular grava → servidor processa → painel mostra o olhar**

**Para outra IA entender o projeto:** leia o [contexto e fluxo do sistema](docs/contexto-projeto.md).

## Subir a base web

Requer Docker Engine com Compose ou Docker Desktop com integração WSL2. Node, Python e uv são fornecidos pelas imagens; não é necessário instalá-los no host para subir a base.

Na raiz do repositório, os builds precisam dos lockfiles do webapp e da API.
Se o lockfile Python ainda não existir, gere-o primeiro:

```sh
bash scripts/gerar-lock-api.sh
```

Depois, inicie a base:

```sh
docker compose up --build -d --wait
```

- Webapp: [http://localhost:8080](http://localhost:8080).
- API pelo mesmo endereço: [estado](http://localhost:8080/api/health) e [informações](http://localhost:8080/api/info).
- Documentação interativa: [http://localhost:8080/docs](http://localhost:8080/docs).
- Contrato OpenAPI: [http://localhost:8080/openapi.json](http://localhost:8080/openapi.json).

A interface permite criar experimentos, receber coletas Android, executar análises de olhar e inspecionar/exportar resultados. A [coleta instrumentada](docs/coleta-instrumentada.md) prepara os dados e as medidas para o piloto. A [pipeline experimental](docs/pipeline.md) usa iTracker congelado e MediaPipe, com calibração e avaliação condicionadas às medidas e à sincronização fornecidas. Baixe e verifique os modelos conforme essa documentação antes de executar análises.

São dois containers: o webapp servido pelo Nginx e uma API Python. O Nginx encaminha as chamadas para a API pela rede interna. O Compose aguarda a API passar pelo healthcheck antes de iniciar a interface.

```sh
docker compose ps
docker compose logs -f
docker compose down
```

Para mudar a porta ou permitir acesso pela rede local, copie [.env.example](.env.example) para `.env` e ajuste `WEB_PORT` e `WEB_HOST`. O endereço padrão é `127.0.0.1`; para a LAN, use `WEB_HOST=0.0.0.0` e o IP do PC. Após mudar essas opções, execute novamente o comando de inicialização.

## Desenvolvimento e verificações

Os builds usam os lockfiles das dependências: npm ci no webapp e uv sync --frozen na API. Para executar os testes Python em um container:

```sh
docker build -f services/api/Dockerfile --target test -t eye-tracker-api-test .
```

Para validar a configuração e compilar ambos os componentes, incluindo a checagem TypeScript:

```sh
docker compose config --quiet
docker compose build
```

Mudanças no código entram na aplicação após `docker compose up --build -d --wait`. Instruções específicas estão nos READMEs do [webapp](apps/web/README.md), da [API](services/api/README.md) e da [infraestrutura](infra/README.md).

O aplicativo Android mantém seu ambiente e build próprios, descritos em [apps/android](apps/android/README.md). Os containers desta entrega executam a parte web e o serviço do servidor.

## Roadmap

| Etapa | Quando | O que fazer | Pronto quando |
| --- | --- | --- | --- |
| ☐ **1. Coletar** | Dias 1–2 | Android grava câmera frontal durante calibração, estímulo e validação, com registros de sincronização. | Vídeo e registros de uma sessão podem ser conferidos no computador. |
| ☐ **2. Enviar** | Dia 3 | Subir o servidor em Docker no Windows. O app recebe o código do experimento, baixa o estímulo e envia a coleta. | Uma sessão chega íntegra ao servidor. |
| ☐ **3. Processar** | Dia 4 | Usar MediaPipe, sincronizar os registros e calcular o olhar no servidor. | A sessão produz coordenadas e medidas de qualidade. |
| ☐ **4. Visualizar** | Dia 5 | Mostrar no painel o estímulo, o olhar estimado e a qualidade. | É possível abrir e inspecionar uma sessão real. |
| ☐ **5. Medir** | Dia 6 | Repetir os testes e organizar erros, falhas e tempo de processamento. | Há uma tabela ou gráfico com resultados reais e limitações. |
| ☐ **6. Apresentar** | Dia 7 | Preparar slides, ensaiar e gravar uma demonstração de reserva. | Apresentação e demonstração estão prontas. |

O roadmap descreve o fluxo de pesquisa completo. O software cobre envio, processamento e consulta de resultados experimentais. Os marcos da coleta em aparelho, sincronização medida e precisão nos alvos ainda dependem do piloto descrito em [coleta instrumentada](docs/coleta-instrumentada.md).

Os dias são uma sequência proposta, não garantia de duração. Marcar uma etapa somente após conferir sua entrega. Ainda não foi verificado aqui se o novo app realiza a coleta.

## Como trabalhar com a IA

Delegar **uma etapa por vez**, usando a coluna “Pronto quando” como critério de conclusão. A IA implementa e verifica o código; você decide o protocolo, testa no celular e confere os resultados. Quando houver dúvida, a IA deve perguntar.

## Escopo desta entrega

- App simples para coleta e envio; processamento no PC Windows, em containers.
- O processamento implementado está documentado na [pipeline](docs/pipeline.md); o [plano do iTracker pré-treinado](docs/plano-itracker-pretreinado.md) preserva as decisões de origem.
- Base de infraestrutura: React/TypeScript, Nginx, FastAPI, uv e Docker Compose. A API persiste experimentos, coletas, execuções e resultados em volume local.
- Atualizar os objetivos da proposta durante a semana. A revisão sistemática e o benchmark entre métodos continuam como trabalho do mestrado, sem precisar estar concluídos nesta demonstração.

## Onde trabalhar

| Pasta | Uso |
| --- | --- |
| [apps/android](apps/android/) | Aplicativo de coleta |
| [apps/web](apps/web/) | Interface React/TypeScript e Nginx |
| [services/api](services/api/) | Único serviço Python, com FastAPI e uv |
| [ml](ml/) | Pipeline de processamento e testes |
| [infra](infra/) | Documentação dos containers; [Compose na raiz](compose.yaml) |
| [docs](docs/) | Material de referência e planos |

As subdivisões serão criadas quando forem necessárias.

Referências: [resumo do reaproveitamento do app](docs/inventario-app.md) · [ficha técnica original](docs/ficha-tecnica-v1.txt).

A ficha original descreve uma arquitetura mais ampla e um detector próprio; este roadmap registra o escopo atual. O repositório anterior em `C:/Users/marce/mestrado/eye tracking` permanece preservado.

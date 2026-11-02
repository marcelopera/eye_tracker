# Webapp

Interface React com TypeScript e Vite. Consulta o estado e as funcionalidades
informadas pela API, com carregamento, timeout, tratamento de indisponibilidade
e atualização manual. Não contém dados simulados de sessões ou participantes.

Para subir com a API, execute na raiz:

```sh
docker compose up --build -d --wait
```

Acesse [localhost:8080](http://localhost:8080). O build compila TypeScript e gera
arquivos estáticos; o container final utiliza Nginx e encaminha as chamadas
relativas à API pela rede interna do Compose.

Ao abrir um experimento publicado, a interface lista suas coletas e distingue arquivos pendentes de recebidos. A inferência e a inspeção de resultados ainda não estão disponíveis.
É possível reproduzir o vídeo original da câmera e baixar os eventos originais de uma coleta recebida. Os tempos desses eventos não estão sincronizados com o estímulo.

O [package.json](package.json) declara os comandos de desenvolvimento e build.
O lockfile é usado com npm ci no [Dockerfile](Dockerfile), sem exigir Node no host.

As rotas `/docs` e `/openapi.json` também são encaminhadas à API.
Configuração de portas e comandos de operação: [README da raiz](../../README.md).

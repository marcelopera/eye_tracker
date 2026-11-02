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

O protocolo de coleta é fixo e atribuído automaticamente. Para publicar, basta salvar o experimento e enviar o estímulo; não há seleção de protocolo.

Ao abrir um experimento publicado, a interface lista suas coletas e distingue arquivos pendentes de recebidos. Cada coleta recebida oferece **Gerar demonstração em MP4**, com processamento em segundo plano e acompanhamento de progresso. Depois, o mesmo cartão apresenta o player e **Baixar MP4**. É possível sair da página e voltar durante a geração; o arquivo e o estado ficam no servidor. Os arquivos originais da câmera e dos eventos permanecem acessíveis em uma seção recolhida.

O [package.json](package.json) declara os comandos de desenvolvimento e build.
O lockfile é usado com npm ci no [Dockerfile](Dockerfile), sem exigir Node no host.

As rotas `/docs` e `/openapi.json` também são encaminhadas à API.
Configuração de portas e comandos de operação: [README da raiz](../../README.md).

O MP4 mostra estímulo, olhar estimado, câmera sincronizada, recortes e as etapas da pipeline, sem o cabeçalho superior de marca. A precisão da calibração aparece no próprio vídeo. Não são solicitadas medidas físicas ou configurações manuais no webapp. As rotas técnicas de análise e CSV/JSONL continuam disponíveis na API.

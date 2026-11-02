# Containers

O [Compose da raiz](../compose.yaml) inicia dois containers: o [webapp](../apps/web/)
e uma única [API Python](../services/api/). Os Dockerfiles ficam junto aos seus
componentes, com contextos de build limitados a essas pastas.

```sh
docker compose up --build -d --wait
docker compose ps
```

A interface fica em [localhost:8080](http://localhost:8080). O Nginx serve o build
React e encaminha `/api/`, `/docs` e `/openapi.json` à API pela rede interna do
Compose. A API inicia antes do webapp e precisa passar pelo healthcheck.

Ambos os containers executam com usuário sem privilégios, filesystem somente de
leitura e uma área temporária gravável. O serviço atual é stateless; não há dados
de pesquisa ou volumes persistentes nesta base.

Copie [.env.example](../.env.example) para `.env` para alterar endereço e porta.
Para acesso pela rede local, configure `WEB_HOST=0.0.0.0` e utilize o IP do PC.

Comandos de operação, testes e limites da entrega estão no [README](../README.md).

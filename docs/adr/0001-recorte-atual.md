# ADR-0001: recorte da demonstração

- Estado: aceito como recorte descrito no contexto atual; funcionalidades ainda precisam ser implementadas e validadas.
- Data: 02/11/2026.

## Contexto

A [ficha v1](../arquivo/ficha-tecnica-v1.md) propunha uma arquitetura maior, detector próprio e Linux dedicado; WSL2 era uma opção de desenvolvimento. O objetivo atual é uma demonstração menor em um PC Windows.

## Decisão

Usar uma única pipeline baseada em MediaPipe, com processamento posterior à coleta no PC Windows em containers Docker, e um app simples de coleta e envio. Não criar ou treinar detector próprio neste recorte. O app legado é referência para adaptação, sujeito à confirmação de sua origem e revisão. O projeto ainda não fornece serviços de backend nem pipeline.

## Consequências

Contratos, componentes de infraestrutura, protocolo e métricas precisam de definição e validação antes da implementação. As escolhas detalhadas da ficha histórica não são requisitos atuais. A pesquisa de revisão e benchmark continua separada da demonstração; uma sessão não comprova precisão nem generalização.

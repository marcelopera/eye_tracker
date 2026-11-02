# Processamento

Reservado para a pipeline de landmarks MediaPipe, sincronização e estimativa de olhar. Ainda não há pipeline, modelo selecionado, dependências, comandos de execução ou testes. Consulte as [convenções](../docs/convencoes-pesquisa.md).

Quando o modelo e sua versão forem escolhidos, obtenha a URL HTTPS oficial e o SHA-256 de uma fonte confiável independente e execute `python scripts/baixar_modelo.py URL SHA256 modelos/modelo.task` na raiz (em sistemas que usam `python3`, substitua o comando). O script não sobrescreve um destino existente e só salva após conferir o hash. Ainda não há URL, versão nem hash adotados pelo projeto; não use um hash obtido apenas do mesmo download como prova de integridade.

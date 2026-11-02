# Plano: criar experimentos no webapp

Data: 02/11/2026. Estado: proposta de implementação; nenhuma funcionalidade de cadastro foi implementada nesta tarefa.

## Resultado esperado

O pesquisador abre **Experimentos → Novo experimento**, informa nome e descrição, envia o vídeo de estímulo, define o protocolo e revisa a configuração. Pode salvar um rascunho e retomá-lo depois. Quando as informações estiverem válidas, publica o experimento e recebe um código para uso posterior no Android.

O experimento deve continuar disponível após recarregar a página, reiniciar os containers e reconstruir as imagens. Publicar significa disponibilizar uma configuração válida para coleta; não significa que houve sessão ou processamento do olhar.

**Escopo proposto para a primeira versão:** nome, descrição, vídeo e protocolo, com rascunho, publicação, listagem e consulta. A consulta do experimento pelo Android, criação de sessões, envio da câmera e inferência serão entregas posteriores. O arquivo enviado aqui é o vídeo de estímulo, não a gravação frontal de uma pessoa.

Essa proposta assume o escopo completo apresentado na pergunta desta conversa. Se a primeira entrega for somente cadastro ou cadastro com vídeo, as etapas de protocolo e publicação devem ser reduzidas, mantendo o estado como rascunho até existir uma configuração completa.

## Estado atual conferido no código

| Componente | O que existe | Mudança necessária |
| --- | --- | --- |
| [Webapp](../apps/web/src/App.tsx) | Monitor de disponibilidade da API, com atualização manual e tratamento de erro. | Navegação, formulário, envio de vídeo, revisão e listagem dos experimentos. |
| [API](../services/api/app/main.py) | GET /api/health e GET /api/info. | Contratos, regras de criação/publicação e persistência. |
| [Dependências Python](../services/api/pyproject.toml) | FastAPI e Uvicorn; testes com httpx e pytest. | Adicionar dependências de upload com uv e atualizar o lockfile. |
| [Compose](../compose.yaml) | Um webapp e uma API; API com filesystem somente de leitura e tmpfs temporário. | Volume persistente gravável para banco e vídeos, mantendo o restante somente de leitura. |
| [Imagem da API](../services/api/Dockerfile) | Python, uv e execução com usuário não privilegiado. | Preparar diretórios/permissões do volume e incluir a ferramenta de inspeção de vídeo. |
| [Nginx](../apps/web/nginx.conf) | Proxy das chamadas /api e fallback para a aplicação React. | Limites e tratamento de upload, temporários e timeouts compatíveis com os vídeos. |
| [Testes da API](../services/api/tests/test_api.py) | Contratos de estado e informações; teste que permite somente as duas rotas atuais. | Atualizar a expectativa de rotas e cobrir o fluxo de experimentos. |

Ambos os lockfiles estão presentes nesta inspeção. Não foi executado um build ou teste funcional nesta tarefa de planejamento. O [contexto do projeto](contexto-projeto.md) foi usado para separar experimento, estímulo, protocolo e sessão.

## Arquitetura proposta

- Manter React/TypeScript, Nginx e a única API FastAPI existentes.
- Usar SQLite para os metadados, acessado pelo serviço Python, com migrações versionadas. SQLite permite armazenamento em disco sem um servidor de banco separado; é adequado como ponto de partida para esta base local. [Referência Python](https://docs.python.org/3.12/library/sqlite3.html).
- Armazenar vídeos em arquivos no mesmo volume persistente, e guardar no banco somente sua referência e metadados. Não armazenar o vídeo no banco nem no navegador.
- Montar o volume na API e garantir escrita pelo usuário da aplicação. Banco, arquivos e temporários de upload devem usar esse volume, e não o tmpfs em memória. O volume precisa sobreviver à substituição dos containers. [Referência Docker](https://docs.docker.com/engine/storage/volumes/).
- Manter as rotas de experimentos, validação e armazenamento separadas dentro do serviço atual, sem criar novos serviços ou uma estrutura extensa.
- Gerenciar as alterações Python com uv. O recebimento multipart exige python-multipart, que não consta no lockfile atual. [Referência FastAPI](https://fastapi.tiangolo.com/tutorial/request-files/).

O primeiro fluxo pode executar upload e inspeção no próprio serviço. Não haverá transcodificação automática nessa entrega: o perfil aceito será definido a partir de um vídeo piloto e da compatibilidade desejada. Caso a preparação dos vídeos exija trabalho demorado em segundo plano, o processamento deverá ser especificado antes de ampliar essa arquitetura.

## Fluxo no webapp

1. **Listar:** mostrar experimentos existentes, código quando publicado e situação atual. Exibir um estado vazio com a ação Novo experimento.
2. **Identificar:** informar nome obrigatório e descrição opcional. Salvar o rascunho no servidor e manter seu identificador ao avançar.
3. **Enviar estímulo:** selecionar o vídeo, mostrar progresso e informar o resultado da validação. Após o envio, exibir prévia e metadados derivados do arquivo.
4. **Configurar protocolo:** selecionar um modelo aprovado e/ou preencher os parâmetros definidos no contrato. Mostrar as fases na ordem: marcador A, calibração, descanso, estímulo, validação e marcador B.
5. **Revisar:** apresentar nome, vídeo, fases, parâmetros e pendências. O botão Publicar só fica habilitado quando a configuração estiver completa; a API repete essa validação.
6. **Confirmar:** apresentar o código e permitir copiá-lo ou selecioná-lo manualmente. O experimento aparece na listagem e pode ser reaberto.

O formulário deve preservar os dados já salvos após falha de envio, exibir erros junto ao campo correspondente e impedir submissões simultâneas. O tempo de upload não deve reutilizar o timeout curto do monitor de saúde atual; progresso, cancelamento e limites precisam de tratamento próprio.

## Dados e regras

| Grupo | Dados propostos | Origem |
| --- | --- | --- |
| Identidade | ID interno, código público quando publicado, datas de criação/publicação e estado. | Gerados pelo backend. |
| Descrição | Nome e descrição. | Pesquisador. |
| Estímulo | Referência interna do arquivo, nome original para exibição, tamanho, hash, duração, dimensões, contêiner e codecs. | Nome original recebido; demais dados verificados pelo servidor. |
| Protocolo | Versão do esquema, fases, alvos, tempos, convenções de coordenadas e demais parâmetros aprovados. | Pesquisador/modelo de protocolo aprovado. |

- ID interno e código do experimento são valores diferentes. Proposta: UUID para o ID e código curto gerado pelo servidor, com unicidade garantida no banco. Comprimento, alfabeto e normalização do código serão fixados no contrato.
- Nome não será tratado como identificador único. O sistema deve permitir experimentos diferentes com o mesmo nome, distinguindo-os pelo ID/código.
- O experimento nasce como **rascunho**, sem código publicado. Receber um arquivo, por si só, não muda seu estado para pronto.
- **Publicado/pronto para coleta** exige estímulo completo e válido, protocolo válido e confirmação da revisão. Uma falha mantém o rascunho e informa a pendência.
- Publicações repetidas devem retornar o mesmo experimento e código. Requisições simultâneas não podem gerar códigos diferentes para o mesmo registro.
- A configuração publicada fica imutável nesta primeira versão. Mudanças posteriores exigirão uma nova versão/experimento, evitando alterar a configuração que futuras sessões referenciarão.
- O protocolo será salvo como uma configuração versionada própria do experimento, sem depender de um modelo global que possa mudar depois.
- Calibração e validação devem ser fases explicitamente distintas. Os dados de validação não fazem parte do ajuste da calibração.
- Não inserir parâmetros científicos padrão apenas para permitir a publicação. É possível salvar um rascunho enquanto esses valores ainda não foram definidos.

## Contrato HTTP proposto

As rotas abaixo são uma proposta para a etapa 1, e não endpoints já disponíveis. Campos, envelopes de resposta e limites serão descritos no contrato OpenAPI antes da integração web.

| Método e rota | Responsabilidade |
| --- | --- |
| POST /api/experiments | Criar rascunho e retornar seu identificador e estado. |
| GET /api/experiments | Listar registros salvos, com paginação simples. |
| GET /api/experiments/{id} | Consultar descrição, estímulo, protocolo e pendências. |
| PATCH /api/experiments/{id} | Alterar descrição e protocolo de um rascunho. |
| PUT /api/experiments/{id}/stimulus | Associar ou substituir o vídeo de um rascunho. |
| GET /api/experiments/{id}/stimulus | Disponibilizar o vídeo persistido para prévia, com suporte a requisições parciais. |
| POST /api/experiments/{id}/publish | Validar a configuração e publicar, gerando um código estável. |

A consulta por código para o Android será definida em uma entrega posterior. As respostas desta funcionalidade já devem preservar a separação entre ID, código, experimento e sessão.

Definir erros distinguíveis para campos inválidos, registro inexistente, alteração de registro publicado, vídeo incompatível, tamanho excedido e falha de armazenamento. Repetição após perda de uma resposta não deve criar registros duplicados: o contrato de criação deve prever uma chave de idempotência para a mesma tentativa de cadastro.

## Etapas e critérios de conclusão

### 1. Fechar contrato e comportamento

- Confirmar o escopo da primeira versão e registrar o fluxo rascunho/publicação.
- Definir campos, limites de texto, representação do protocolo e convenções de coordenadas/tempo.
- Definir limites técnicos do vídeo e o perfil inicial aceito, com um arquivo piloto.
- Fixar regras de ID/código, alterações após publicação, idempotência e erros.
- Separar os parâmetros científicos já definidos das pendências, com exemplos sintéticos de configuração completa e incompleta.

**Pronto quando:** existir um contrato revisável, com exemplos de criação, consulta, vídeo inválido e publicação bloqueada; nenhuma pendência científica for preenchida silenciosamente.

### 2. Implementar persistência e rascunhos

- Criar esquema e migrações para metadados do experimento, referência do estímulo e protocolo versionado.
- Implementar o repositório SQLite com transações e restrições de unicidade.
- Adicionar o volume no Compose e preparar suas permissões para o usuário da API. Manter o filesystem da imagem somente de leitura.
- Implementar criação, consulta, listagem e atualização de rascunhos, incluindo o tratamento de repetição da criação.
- Testar os dados com banco e volume temporários isolados.

**Pronto quando:** um rascunho criado pela API puder ser consultado e alterado, mantiver seu ID após reiniciar/recriar containers e uma repetição idempotente retornar o mesmo registro.

### 3. Implementar upload e validação do estímulo

- Adicionar o suporte a multipart via uv e instalar na imagem a ferramenta de inspeção de vídeo escolhida, inicialmente ffprobe.
- Receber o conteúdo com limites de tamanho e armazenamento em disco, evitando carregar o vídeo inteiro em memória. Configurar também o diretório de spool multipart no volume gravável.
- Salvar primeiro em uma área temporária, calcular hash e verificar o conteúdo real, não apenas a extensão ou o MIME informado pelo navegador.
- Gerar nomes internos independentes do nome original e impedir que o cliente escolha caminhos de armazenamento.
- Somente associar o arquivo final ao experimento após a validação. Tratar falha de transação/renomeação com compensação, pois banco e filesystem não formam uma única transação.
- Ajustar Nginx e API para os mesmos limites. A configuração local não define client_max_body_size; o padrão documentado do Nginx é 1m, insuficiente para muitos vídeos. Planejar também buffering e temporários para não usar o tmpfs em memória para arquivos grandes. [Referência Nginx](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size).
- Implementar prévia a partir do arquivo persistido, incluindo requisições parciais e identificação de conteúdo compatível.

**Pronto quando:** um vídeo válido puder ser enviado e reproduzido após recarregar a página; arquivo incompatível, excesso de tamanho, cancelamento e falha de armazenamento não publicarem o experimento nem deixarem uma associação com arquivo incompleto.

### 4. Implementar protocolo e publicação

- Validar estrutura, versão e regras aprovadas do protocolo.
- Conferir que o estímulo exista e esteja validado antes da publicação.
- Gerar o código público em transação, com unicidade e tratamento de colisão; repetir a publicação deve preservar o código.
- Bloquear alterações silenciosas de uma configuração já publicada.
- Salvar as pendências de rascunhos e retornar erros que possam ser associados aos campos da tela.

**Pronto quando:** apenas experimentos completos forem publicados, rascunhos incompletos apresentarem pendências compreensíveis e tentativas repetidas/concorrentes preservarem identidade e código.

### 5. Implementar o fluxo no webapp

- Introduzir navegação entre lista, criação e detalhe, mantendo o acesso ao monitor de estado do serviço.
- Criar formulário acessível de identificação, vídeo e protocolo, com validação local e mensagens da API.
- Permitir salvar/retomar rascunhos, acompanhar e cancelar envio e tentar novamente após falha.
- Apresentar revisão antes da publicação e confirmação com código após sucesso.
- Exibir estados vazio, carregando, indisponível e erro de validação, usando dados reais do backend.
- Preservar a descrição já salva quando uma etapa posterior falhar; não mostrar sucesso apenas porque o navegador selecionou um arquivo.

**Pronto quando:** o fluxo completo puder ser feito pela interface, o registro reaparecer ao reabrir a página e mensagens de upload, rascunho e publicação corresponderem aos estados reais do servidor.

### 6. Validar a entrega integrada

- API: cobrir persistência, idempotência, colisão de código, publicação incompleta, imutabilidade após publicação e consistência entre arquivo e banco.
- Upload pelo Nginx: testar vídeo válido, conteúdo inválido com extensão de vídeo, tamanho excedido, cancelamento e mensagem compreensível para erro 413.
- Web: testar erros de campo, indisponibilidade, retomada de rascunho e publicação repetida; conferir navegação e apresentação em tela pequena.
- Ponta a ponta: criar um experimento pela interface, enviar um vídeo sintético de teste, configurar protocolo aprovado, publicar, copiar o código e consultar novamente após reiniciar os containers.
- Usar um volume de teste isolado para verificar recriação e recuperação; preservar os dados do volume de trabalho.
- Atualizar os testes que hoje exigem somente duas rotas, a CI, os READMEs e as instruções de cópia/restauração dos dados persistentes.
- Executar testes Python pelo target test da API, checagem TypeScript/build do webapp e smoke test contra o Compose.

**Pronto quando:** o fluxo de criação estiver reproduzível a partir de uma instalação limpa, os dados sobreviverem à recriação dos containers e as falhas cobertas não produzirem experimentos publicados incorretamente. Isso valida o cadastro no webapp; ainda não valida a execução do experimento no Android nem a estimativa de olhar.

## Decisões ainda necessárias

1. Confirmar se a primeira versão inclui vídeo e protocolo, ou apenas rascunho/cadastro.
2. Definir o primeiro protocolo aprovado: fases, alvos, durações, convenções e parâmetros obrigatórios. As constantes atuais do Android são uma referência de código, não uma validação científica.
3. Definir tamanho/duração máximos e perfil de vídeo aceito a partir do uso previsto e de um estímulo piloto.

SQLite e volume local são a proposta técnica para manter a estrutura mínima. As pendências de protocolo e vídeo não impedem iniciar contrato, persistência e rascunhos; a publicação deve continuar bloqueada enquanto os requisitos correspondentes não estiverem definidos.

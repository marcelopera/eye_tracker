# Tarefa: migrar o aplicativo Android para Kotlin com MVVM enxuto

Preparada em 27/10/2026 a pedido do pesquisador, para implementação por outro agente.

## Objetivo e autorização

Implementar o aplicativo Android em Kotlin com MVVM enxuto, migrando o código Java existente e separando interface, estado, execução da sessão e persistência. Corrigir os problemas de restauração, navegação e apresentação encontrados na avaliação, preservando o fluxo e o escopo da coleta local.

O usuário escolheu explicitamente MVVM enxuto e, posteriormente, determinou que o projeto Android seja feito em Kotlin. Ambas as decisões estão autorizadas. Esta tarefa prepara a implementação; nenhuma refatoração ou migração foi executada pelo agente que escreveu este documento.

## Contexto que deve ser lido primeiro

- Workspace: este repositório.
- `README.md`: roadmap e foco atual na coleta local.
- `docs/contexto-projeto.md`: conceitos, fluxo desejado e restrições do projeto.
- `apps/android/README.md`: comportamento e limitações do protótipo atual.
- `docs/inventario-app.md`: referência de reaproveitamento, sem autorização para alterar o projeto anterior.
- Verificar se surgiram instruções `AGENTS.md` desde esta avaliação. Nenhum arquivo com esse nome foi encontrado na busca realizada no workspace.

O sistema pretendido grava a câmera frontal no Android, processa no servidor e mostra resultados em um painel. Nesta etapa, busca do experimento, disponibilidade de coletas e envio são simulados. O vídeo de estímulo é selecionado localmente. A coleta não realiza inferência no aparelho.

## Trabalho já realizado e limites da avaliação

Foi feita inspeção estática dos seguintes arquivos:

- Os quatro documentos de contexto citados acima.
- `apps/android/app/src/main/java/br/com/marcelopera/eye_tracking/MainActivity.java`.
- `apps/android/app/src/main/AndroidManifest.xml`.
- `apps/android/app/src/main/res/values/themes.xml` e `values-night/themes.xml`.
- `apps/android/app/src/main/res/values/strings.xml`.
- `apps/android/app/build.gradle.kts`, `settings.gradle.kts`, `gradle.properties` e `gradle/libs.versions.toml`.
- `ExampleUnitTest.kt` e `ExampleInstrumentedTest.kt` nos source sets de teste.

Também foram consultadas as referências oficiais listadas ao final. Não foram executados build, testes, emulador ou aplicativo em aparelho. Não houve inspeção visual das telas em execução. Os problemas de apresentação apontados são riscos identificados no código, não defeitos visuais reproduzidos.

O comando `git status --short` na raiz retornou que ela não é um repositório Git. Não houve diff, commit ou alteração de código na avaliação. Não inicializar Git nem pressupor disponibilidade de histórico como parte desta tarefa; verificar o ambiente antes de usar operações Git.

Os testes encontrados são exemplos do template: soma de inteiros e nome do pacote. Eles não validam navegação, estado ou coleta. Esta tarefa é o único arquivo criado neste encaminhamento.

## Diagnóstico

As linhas abaixo correspondem ao arquivo inspecionado e podem mudar. Localizar os métodos pelo nome antes de editar.

| Achado | Evidência | Consequência |
| --- | --- | --- |
| Responsabilidades concentradas | `MainActivity`: `page`/`showId`/`showHome`, `startSession` (linha 149), protocolo e `saveMetadata` (linha 249) | Interface, câmera, protocolo e arquivos precisam mudar na mesma classe; testes isolados ficam difíceis. |
| Estado de preparação não restaurado | Campos `experimentId` e `stimulus`; `onCreate` sempre chama `showId` (linhas 61–65) | Recriação perde ID, vídeo e tela. Se ocorrer durante o seletor de documentos, o retorno pode abrir `showHome` com ID nulo. |
| Voltar usa API antiga | `onBackPressed` (linhas 280–282), target SDK 37 e ausência de opt-out no manifesto | Em Android 16+ o callback antigo não recebe o evento nessa configuração; a navegação pretendida deixa de funcionar. |
| Estilos inconsistentes | Fundo/textos fixos em `page`/`label`, mas controles herdam tema `DayNight` | Risco de contraste inadequado no modo escuro. Textos também estão embutidos no Java. |
| Barras do sistema sem tratamento explícito | Padding fixo em `page`, telas de sessão construídas diretamente | Risco de sobreposição e de geometria inconsistente em dispositivos com diferentes barras/recortes. |
| Estado distribuído em booleanos | `active`, `finishing`, `completed`, `screenVisible`, `interruptedInBackground` e callbacks | Transições difíceis de verificar e potencial de combinações incoerentes. Visibilidade da Activity deve permanecer uma preocupação de ciclo de vida, separada do estado da coleta. |

Dois comentários de revisão foram apresentados no chat: `[P2] Restaurar o estado de preparação` e `[P2] Migrar a interceptação de Voltar`. Não foram inseridos no código.

Decisões positivas a preservar: validação de ID vazio, exigência de vídeo antes do início, permissão de câmera solicitada ao iniciar, gravação frontal sem áudio, vínculo da câmera ao ciclo de vida, interrupção ao sair da tela, arquivos privados e backup desativado. O sucesso atualmente depende do evento `VideoRecordEvent.Finalize`, da ausência de erro e da gravação dos metadados; preservar essa condição.

## Arquitetura desejada

Kotlin é obrigatório para o código-fonte do aplicativo Android e para os testes implementados nesta tarefa. Migrar `MainActivity.java` para `MainActivity.kt` e escrever os componentes extraídos em Kotlin idiomático, com nulabilidade explícita e estados tipados. As referências a Java neste documento descrevem apenas o código original inspecionado. Manter o sistema de Views existente; migrar para Kotlin não exige migrar para Compose.

Preferir `ViewModel`, `SavedStateHandle` e `StateFlow` para o estado observável, coletado pela UI com respeito ao ciclo de vida, e coroutines para operações assíncronas quando apropriado. Adicionar somente as dependências necessárias, com versões compatíveis verificadas no ambiente. Conferir o suporte a Kotlin já fornecido pela versão do Android Gradle Plugin antes de alterar plugins, evitando configuração duplicada ou incompatível.

| Componente sugerido | Responsabilidade |
| --- | --- |
| `MainActivity` e classes de telas em `ui` | Renderizar estado, encaminhar ações, abrir seletor de vídeo, solicitar permissão, integrar navegação e ciclo de vida. |
| `SessionViewModel` e `SessionUiState` em `ui` | Manter o estado observável da preparação e da tela, validar ações e refletir resultados da sessão. |
| `SessionController` em `session` | Coordenar as fases, tempos e gravação, emitir mudanças de estado e resultados. Isolar recursos dependentes de ciclo de vida da lógica testável. |
| `SessionRepository` em `data` | Criar diretórios, registrar e persistir metadados e informar sucesso/falha. Futuras integrações de servidor ficam fora da implementação atual. |

Esses nomes são sugestões; preservar a separação de responsabilidades é o requisito. Usar um único módulo de aplicativo, composição manual das dependências e poucas classes coesas. Não criar uma camada de casos de uso, framework de injeção, hierarquias genéricas ou interfaces sem necessidade concreta.

Fluxo esperado: ação da tela → ViewModel/coordenação → controlador ou repositório → atualização de estado → renderização. Evitar que a Activity seja responsável por criar JSON, abrir arquivos ou decidir a sequência inteira do protocolo.

Não colocar `Activity`, `View`, `VideoView`, `LifecycleOwner` ou callbacks que capturem uma Activity dentro de um ViewModel retido. Recursos de câmera/player e apresentação de alvos precisam de um proprietário com ciclo de vida explícito. O estado de preparação sobrevive à recriação; uma gravação interrompida não deve ser automaticamente retomada. Não conservar uma Activity destruída para manter a câmera funcionando.

## Escopo de implementação

**Requisito transversal — Kotlin:** migrar todo o código Java de produção próprio do aplicativo para Kotlin, incluindo a Activity e os componentes resultantes da refatoração. Preservar pacote, `applicationId` e integração com o manifesto. Remover os arquivos Java substituídos após conferir a migração, sem manter classes duplicadas. Verificar configuração de Kotlin/JVM e compatibilidade com o alvo Java existente; manter os testes existentes em Kotlin. Esse requisito não se aplica a scripts gerados, dependências de terceiros ou futuros serviços de backend.

1. **Extrair o estado e as transições.** Representar explicitamente as fases necessárias, por exemplo identificação, preparação, câmera iniciando, marcadores, calibração, descanso, estímulo, validação, finalização, conclusão e interrupção/erro. Separar o destino de navegação do estado da coleta quando isso simplificar o modelo. Impedir início duplicado e ações incompatíveis com a fase atual.
2. **Restaurar a preparação.** Preservar ID/digitação, URI do vídeo e destino de tela usando estado salvo adequado. Não armazenar vídeo, player ou grandes listas de eventos em `SavedStateHandle`. Revalidar acesso à URI após restauração e pedir nova seleção quando necessário. Resultados de seletor e permissão nunca devem iniciar uma coleta com preparação incompleta.
3. **Modernizar as integrações de UI.** Usar Activity Result API para seleção de documento e permissão, com registro compatível com recriação. Usar `OnBackPressedDispatcher` para retornar à identificação na preparação e interromper uma coleta ativa. Definir comportamento consistente durante a finalização, sem permitir nova coleta concorrente.
4. **Extrair a execução da sessão.** Preservar o protocolo piloto existente, sem modificar posições, durações ou critérios científicos. Cancelar tarefas temporizadas e tratar callbacks tardios sem contaminar outra sessão ou acessar telas destruídas. Preservar a espera pela finalização efetiva da gravação antes de anunciar sucesso.
5. **Extrair a persistência.** Manter `files/sessoes/<id>/face.mp4` e `sessao.json`, incluindo campos e eventos existentes. Propagar falhas ao estado da tela. Fazer I/O fora da thread principal, com ordenação que impeça o anúncio de sucesso antes da persistência e a mistura de dados de sessões diferentes.
6. **Organizar as telas e recursos.** Tirar textos para `strings.xml` e centralizar cores/estilos em recursos coerentes com os temas claro e escuro. Pode manter Views programáticas ou extrair layouts XML pequenos. Aplicar insets das barras/recortes; na coleta, alinhar área de apresentação dos alvos e dimensões registradas. Não assumir que padding fixo equivale à área útil.
7. **Atualizar a documentação.** Registrar a organização final, como validar e as limitações ainda existentes em `apps/android/README.md`. Manter claro que experimento/envio são simulados e que a sincronização científica ainda não está validada.

## Fora do escopo

- Backend, upload, endpoints, autenticação, painel e download do estímulo.
- Inferência local, calibração matemática e processamento no servidor.
- Novo contrato científico, PTS/sincronização completa, hashes ou pacote definitivo descrito no contexto do projeto.
- Alteração do protocolo, parâmetros experimentais ou exigência de participante.
- Migração para Compose ou substituição ampla do sistema de UI, multimódulos, Hilt/Dagger, Room ou WorkManager sem necessidade desta refatoração. A migração de Java para Kotlin faz parte obrigatória do escopo.
- Alterar o app legado ou outros projetos anteriores.

A refatoração não deve apresentar o protótipo como coleta validada para pesquisa. Se uma decisão científica ou contrato externo for indispensável, perguntar ao pesquisador. Decisões rotineiras de organização do código podem ser tomadas pelo agente.

## Verificação e critérios de aceite

Executar testes significativos das transições e restauração, evitando testes que apenas repitam getters ou o template. Priorizar:

- ID vazio ou ausência de vídeo impede iniciar; ID e URI válidos permitem preparar a sessão.
- Recriação durante preparação ou retorno do seletor preserva contexto e não produz experimento nulo.
- Retorno de permissão não inicia sessão duplicada ou sem preparação válida.
- Finalização pendente não é sucesso; erro de gravação ou persistência não produz tela de conclusão.
- Interrupção cancela sequência; callbacks antigos não mudam uma nova sessão.

Rodar em `apps/android` os comandos compatíveis com o ambiente:

```powershell
.\gradlew.bat :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

Se houver aparelho/emulador disponível, verificar também:

- Fluxo completo com vídeo local, câmera frontal e arquivos finais.
- Voltar na identificação, preparação, coleta e finalização, especialmente em Android 16+.
- Saída para segundo plano durante coleta e retorno com indicação de interrupção.
- Recriação da Activity durante preparação e seletor; não depender apenas de rotação, pois o manifesto atual fixa retrato.
- Tema claro/escuro, teclado, fonte ampliada e barras do sistema; botões e textos devem permanecer legíveis e acessíveis.
- Alvos continuam posicionados na mesma área cujas dimensões são registradas.

Critérios finais:

- [ ] Código de produção próprio do aplicativo migrado para Kotlin, incluindo `MainActivity.kt`, sem classes Java substituídas remanescentes ou duplicadas.
- [ ] Novos componentes e testes escritos em Kotlin; configuração Kotlin/JVM compatível e compilação verificada.
- [ ] Activity dedicada à interface e às integrações Android, sem persistência de arquivos ou sequência completa de protocolo embutida.
- [ ] Estado observável e transições explícitas, com preparação restaurável.
- [ ] Nenhuma referência à Activity/View retida pelo ViewModel.
- [ ] Navegação Voltar e Activity Result API integradas corretamente.
- [ ] Controlador e repositório separados, sem expansão desnecessária da arquitetura.
- [ ] Fluxo local, protocolo e formatos existentes preservados.
- [ ] Conclusão exibida somente após gravação e metadados concluídos com sucesso.
- [ ] Estilos e insets tratados; documentação atualizada.
- [ ] Build/testes/lint executados ou limitações de execução identificadas precisamente.
- [ ] Testes em aparelho reportados separadamente dos testes automatizados; não declarar validação que não foi realizada.

Ao entregar, informar arquivos alterados, decisões de arquitetura, comandos executados e respectivos resultados, cenários conferidos em aparelho e pendências reais. Não marcar etapas do roadmap como concluídas apenas pela refatoração.

## Referências consultadas na avaliação

- [Recomendações de arquitetura Android](https://developer.android.com/topic/architecture/recommendations): separação de responsabilidades, camada de UI/dados, ViewModel e fluxo unidirecional; adaptar ao tamanho do app.
- [Preservação de estado de UI](https://developer.android.com/topic/libraries/architecture/saving-states): diferenças entre ViewModel, estado salvo e persistência.
- [Mudanças para apps com target Android 16+](https://developer.android.com/about/versions/16/behavior-changes-16): navegação preditiva, substituição de `onBackPressed` e exigências de edge-to-edge.

## Prompt para iniciar a implementação

> Implemente a tarefa descrita em `docs/tarefa-mvvm-enxuto.md`. O aplicativo Android deve ser implementado em Kotlin com MVVM enxuto, migrando o código Java existente e mantendo o sistema de Views. Leia o contexto e confira o código atual antes de editar; preserve o fluxo de coleta local e as limitações documentadas. Faça a migração, a refatoração, as correções e as verificações previstas, e entregue um resumo com evidências e pendências. Não implemente backend nem altere o protocolo científico.

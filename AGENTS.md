# Orientações para trabalho neste repositório

Leia [o contexto](docs/contexto-projeto.md), o [ADR-0001](docs/adr/0001-recorte-atual.md) e a issue da tarefa; confira o código antes de afirmar que algo funciona.

- Trabalhe em uma etapa por vez e use o respectivo “Pronto quando” como definição de concluído.
- Pergunte ao pesquisador quando uma dúvida impedir a implementação. Não invente endpoints, IDs, formatos ou parâmetros de coleta.
- Nunca faça commit de dados de pessoas, vídeos, credenciais ou artefatos de pesquisa. Preserve o trabalho existente.
- O Android coleta; o processamento planejado ocorre no servidor com MediaPipe. Não implemente detector próprio sem nova decisão.

## Estrutura e verificações

`apps/android` contém o app e seus testes; `apps/web`, `services`, `ml` e `infra` ainda não têm aplicação executável. `docs` contém decisões e histórico. No diretório `apps/android`, execute `./gradlew :app:assembleDebug :app:testDebugUnitTest :app:lintDebug` (Windows: `.\gradlew.bat` com as mesmas tarefas). Há JDK 25 e Gradle wrapper configurados; Android SDK é necessário. Informe separadamente o que foi verificado em dispositivo.

# Aplicativo Android

Protótipo local de uma sessão: informe o ID do experimento, selecione um vídeo no aparelho e inicie. O app grava a câmera frontal sem áudio durante marcadores, calibração, vídeo e validação. Ao terminar, mostra o identificador local da coleta. A simulação contém uma coleta por experimento e não solicita o código do participante.

O protocolo piloto apresenta cinco posições de calibração duas vezes, por dois segundos cada, seguidas do vídeo e de cinco posições de validação diferentes. Os valores são provisórios e não representam precisão validada. A gravação e os registros de eventos são armazenados em `files/sessoes/<id>/` no armazenamento privado do aplicativo. Uma sessão interrompida é marcada como tal; o backup do app está desativado.

## Organização do código

O aplicativo usa Kotlin, o sistema de Views e um MVVM enxuto, sem injeção de dependência, casos de uso ou módulos adicionais.

| Pacote | Responsabilidade |
| --- | --- |
| `br.com.marcelopera.eye_tracking` | `MainActivity`: telas, seleção de vídeo, permissão de câmera, navegação e insets. |
| `ui` | `SessionViewModel`, `SessionUiState`, destinos de tela e componentes visuais. O estado observável usa `StateFlow` e `SavedStateHandle`. |
| `session` | `SessionController` coordena o protocolo, a gravação e os eventos. `CameraRecordingEngine` isola o CameraX. |
| `data` | `SessionRepository` cria a pasta da coleta e grava `sessao.json` fora da thread principal. |

Fluxo: ação da tela → `SessionViewModel` valida e atualiza o estado → `SessionController` executa a sessão → `SessionRepository` persiste → estado e tela são atualizados.

As fases são explícitas (`PreparingCamera`, `MarkerA`, `Calibration`, `Rest`, `Stimulus`, `Validation`, `MarkerB`, `Finalizing`, entre outras). O destino de navegação é separado da fase da coleta. Uma gravação em andamento nunca é retomada automaticamente após recriação, segundo plano ou interrupção.

A preparação guarda apenas o texto digitado, o ID confirmado, a URI do vídeo e o destino da tela no estado salvo. Player, câmera, `VideoView` e a Activity não são retidos pelo ViewModel. A URI é revalidada ao retornar à tela e, se o acesso tiver sido perdido, o app pede nova seleção.

A seleção de vídeo e a permissão de câmera usam a Activity Result API. O botão Voltar usa `OnBackPressedDispatcher`: na preparação retorna à identificação; durante a coleta interrompe e finaliza os arquivos; durante a finalização não inicia outra coleta. Textos estão em `strings.xml` e as cores da interface têm variantes clara e escura. As barras do sistema e o teclado são tratados por insets; a área usada para apresentar alvos é a mesma cuja largura e altura são registradas.

## Verificação

Para compilar, testar e rodar o lint no Windows:

```powershell
.\gradlew.bat :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

Em Linux/macOS:

```bash
./gradlew :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

Os testes unitários cobrem validação de ID e vídeo, permissão negada, restauração da preparação, restauração de coleta como interrompida, callbacks de sessões antigas, finalização pendente, erro de gravação, falha de persistência, interrupção e erro durante o estímulo com preservação do evento de início e a sequência de eventos do protocolo.

O lint passa sem erros e mantém três avisos: dois sobre a orientação fixa em retrato e um sobre o atributo de navegação introduzido na API 33. Não houve execução em aparelho ou emulador nesta verificação; a validação em dispositivo continua necessária.

## Limitações atuais

- A busca de experimento, o identificador de coleta e a disponibilidade de outras coletas são simulados; não há backend nem envio.
- O vídeo escolhido é reproduzido pelo provedor de arquivos, sem download ou verificação de integridade.
- O arquivo `sessao.json` registra eventos e coordenadas dos alvos, mas ainda não contém PTS do vídeo de estímulo, geometria completa, hashes nem a sincronização validada com os quadros da câmera. Ele não substitui o pacote descrito em `docs/contexto-projeto.md`.
- Um encerramento abrupto do processo durante a sessão pode deixar uma gravação parcial sem metadados finais; o app não retoma essa gravação.
- É necessário testar gravação, reprodução, interrupções, recriação, tema escuro e barras do sistema em um aparelho antes de usar os dados para pesquisa.

O APK de depuração fica em `app/build/outputs/apk/debug/`.

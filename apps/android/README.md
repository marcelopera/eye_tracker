# Aplicativo Android

O aplicativo consulta um experimento publicado pelo código, baixa o estímulo e confere tamanho, SHA-256 e protocolo antes da coleta. Informe o endereço da API (ou do webapp que a encaminha) e um código pseudônimo do participante. Ao concluir, a gravação e os eventos são enviados; em caso de falha, use **Coletas pendentes** na tela inicial. Os arquivos locais são mantidos após o recebimento.

Para uso na rede local configure `WEB_HOST=0.0.0.0` no `.env` do Compose e informe no celular o endereço do computador, por exemplo `http://192.168.1.10:8080`. O serviço atual não possui autenticação nem TLS: a gravação e o código do participante trafegam em texto aberto via HTTP. Use apenas dados sintéticos em rede controlada até configurar proteção adequada. O recebimento não significa processamento ou validação científica.

O protocolo piloto apresenta cinco posições de calibração duas vezes, por dois segundos cada, seguidas do vídeo e de cinco posições de validação diferentes. Os valores são provisórios. Os arquivos ficam em `files/sessoes/<id>/`, no armazenamento privado; o backup está desativado.

## Organização do código

O aplicativo usa Kotlin, o sistema de Views e um MVVM enxuto, sem injeção de dependência, casos de uso ou módulos adicionais.

| Pacote | Responsabilidade |
| --- | --- |
| `br.com.marcelopera.eye_tracking` | `MainActivity`: telas, conexão com a API, permissão de câmera, navegação e insets. |
| `ui` | `SessionViewModel`, `SessionUiState`, destinos de tela e componentes visuais. O estado observável usa `StateFlow` e `SavedStateHandle`. |
| `session` | `SessionController` coordena o protocolo, a gravação e os eventos. `CameraRecordingEngine` isola o CameraX. |
| `data` | `SessionRepository` cria a pasta da coleta e grava `sessao.json` fora da thread principal. |

Fluxo: ação da tela → `SessionViewModel` valida e atualiza o estado → `SessionController` executa a sessão → `SessionRepository` persiste → estado e tela são atualizados.

As fases são explícitas (`PreparingCamera`, `MarkerA`, `Calibration`, `Rest`, `Stimulus`, `Validation`, `MarkerB`, `Finalizing`, entre outras). O destino de navegação é separado da fase da coleta. Uma gravação em andamento nunca é retomada automaticamente após recriação, segundo plano ou interrupção.

A preparação guarda apenas o texto digitado, o ID confirmado, a URI do vídeo e o destino da tela no estado salvo. Player, câmera, `VideoView` e a Activity não são retidos pelo ViewModel. A URI é revalidada ao retornar à tela e, se o acesso tiver sido perdido, o app pede uma nova consulta ao experimento.

A permissão de câmera usa a Activity Result API. O botão Voltar usa `OnBackPressedDispatcher`: na preparação retorna à identificação; durante a coleta interrompe e finaliza os arquivos; durante a finalização não inicia outra coleta. Textos estão em `strings.xml` e as cores da interface têm variantes clara e escura. As barras do sistema e o teclado são tratados por insets; a área usada para apresentar alvos é a mesma cuja largura e altura são registradas.

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

O lint pode apresentar avisos, inclusive sobre orientação fixa e configuração de rede. Não houve execução em aparelho ou emulador nesta verificação; a validação em dispositivo continua necessária.

## Limitações atuais

- Sessões interrompidas com gravação e metadados são colocadas na fila para envio manual. Uma interrupção abrupta antes de registrar os dados de envio pode exigir recuperação manual.
- Não há retomada parcial de upload: uma nova tentativa reenvia os arquivos completos.
- O arquivo `sessao.json` registra eventos e coordenadas dos alvos, mas ainda não contém PTS do vídeo de estímulo, geometria completa, hashes nem a sincronização validada com os quadros da câmera. Ele não substitui o pacote descrito em `docs/contexto-projeto.md`.
- Um encerramento abrupto do processo durante a sessão pode deixar uma gravação parcial sem metadados finais; o app não retoma essa gravação.
- É necessário testar gravação, reprodução, interrupções, recriação, tema escuro e barras do sistema em um aparelho antes de usar os dados para pesquisa.

O APK de depuração fica em `app/build/outputs/apk/debug/`.

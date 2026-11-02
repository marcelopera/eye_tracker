# Contrato proposto para a pipeline, versão 1

Estado: proposta para revisão; ainda não implementado. Este contrato define uma interface para discussão, não afirma que o Android atual exporta estes campos. Uma sessão é um diretório transferido localmente contendo `manifest.json` e os arquivos relativos declarados nele. JSON usa UTF-8; caminhos são relativos ao diretório da sessão, sem caminhos absolutos ou `..`. A integridade é SHA-256 dos bytes de cada arquivo declarado; não confundir com hash de objeto Git.

## Manifesto

Campos obrigatórios no manifesto:

- `schema_version`: inteiro `1`; versões desconhecidas são rejeitadas.
- `session_id`, `experiment_id`: identificadores não vazios; `status`: `completed` ou `interrupted`.
- `camera_video` e `events`: objetos com `path` e `sha256` hexadecimal minúsculo de 64 caracteres. Os arquivos devem existir e corresponder ao hash. O vídeo deve ser decodificável; eventos são JSON UTF-8.
- `capture`: `rotation_degrees` (0, 90, 180 ou 270, rotação horária necessária para deixar a imagem em pé) e `mirrored` (se os pixels armazenados estão espelhados horizontalmente). Os dados dos olhos usam sempre o lado anatômico do participante após desfazer o espelhamento.
- `device_profile` e `synchronization`: objeto definido abaixo ou `null` quando desconhecido. Não preencher valores presumidos.

Um perfil completo contém `screen_width_px`, `screen_height_px`, `screen_width_mm`, `screen_height_mm`, `camera_x_mm` e `camera_y_mm`. As dimensões descrevem a área ativa na orientação do vídeo de estímulo; origem no canto superior esquerdo, x para a direita e y para baixo. A posição da câmera é medida a partir dessa origem e pode estar fora da área ativa. Também é necessário registrar orientação, insets e retângulo de apresentação efetivo do estímulo antes da conversão; seu formato permanece pendente de revisão e validação em aparelho.

A sincronização exige uma transformação medida entre PTS da câmera e relógios dos eventos, bem como tempos de quadros do estímulo efetivamente apresentados, com método, erro e deriva. O formato e os limiares permanecem pendentes de validação; um objeto não deve ser interpretado como sincronização válida apenas por existir. Até serem definidos e medidos, conversão temporal para o estímulo e métricas relacionadas ficam indisponíveis.

## Eventos e saídas

O arquivo de eventos deve manter o nome, tempo inteiro em nanossegundos, identificador do relógio e dados de cada evento, sem converter relógios sem relação comprovada. Calibração e validação são fases distintas; alvos, instantes, unidades e referência espacial precisam ser explicitados antes de ajustar ou avaliar um modelo. A representação exata dos alvos e da apresentação do estímulo será fechada com o protocolo; não interpretar a string de dados antiga sem versão.

A saída deverá registrar uma linha por quadro decodificado, com PTS inteiro e time base racional originais, tempo do estímulo somente quando comprovadamente associado, validade e motivo de falha, previsão bruta em centímetros no referencial do modelo, features quando habilitadas, e coordenadas de tela/estímulo somente quando as transformações estiverem verificadas. Registrar revisão e hashes dos modelos, configuração, perfil e versão da pipeline. Quadros sem rosto ou recorte válido não recebem coordenadas artificiais. A orientação dos eixos e a origem das saídas do modelo devem ser verificadas contra a referência oficial antes da conversão para tela.

## Coletas existentes e casos incompletos

O `sessao.json` atual tem `experimento`, `coleta_local`, `estado` e `eventos`, cujos tempos usam os rótulos `elapsedRealtimeNanos` e `frameTimeNanos`. Não contém uma transformação comprovada para PTS, tempos efetivos dos quadros do vídeo exibido nem perfil físico completo. Não é um manifesto v1. Uma importação futura deve preservar o original e marcar esses dados como ausentes; não fabricar correspondência por FPS ou pelo início da gravação. Uma sessão interrompida pode ser inspecionada, mas não deve ser apresentada como avaliação completa.

[Exemplo sintético estrutural](exemplos-contrato/manifesto-valido.json) usa hashes ilustrativos e pressupõe arquivos de exemplo com esses hashes; sozinho não é um pacote íntegro. [Exemplo inválido](exemplos-contrato/manifesto-invalido.json) viola versão, integridade e caminho. A validação executável será implementada após revisão do contrato.

# Pipeline de vídeo e análise do olhar

A pipeline experimental executa em CPU, preserva cada quadro decodificado e produz baseline e variante calibrada separados. O processamento pode ser disparado em **Experimento → Coletas → Processar e consultar olhar**, consultado após recarregar o navegador e repetido em uma nova execução. Os arquivos originais permanecem intactos. A ausência de medidas ou correspondência temporal não impede inferência bruta: impede as conversões que delas dependem.

## Coletas instrumentadas

O Android atualizado registra a relação entre imagens/PTS codificados, quadros renderizados, alvos e geometria de apresentação. O painel pode gerar a configuração automaticamente com medidas do pesquisador. Consulte [coleta instrumentada e piloto](coleta-instrumentada.md) para operação, contrato, limites e critérios de entrega.

## Instalação e execução

Na raiz, com Python 3.12, uv e Docker:

```sh
uv run --directory ml/itracker --frozen python itracker.py download --models ../../modelos/itracker
uv run --directory ml/itracker --frozen python itracker.py download-detector --models ../../modelos/itracker
uv run --directory ml/itracker --frozen --group dev python -m pytest
docker compose up --build -d
```

Os modelos são baixados explicitamente após conferir as licenças dos autores; não estão no Git nem na imagem. O Compose monta `modelos/itracker` somente para leitura. A imagem da API contém um ambiente Python separado em `/opt/pipeline`, com dependências fixadas, um worker local e subprocessos limitados a uma execução simultânea. O volume de dados contém SQLite, originais e diretórios separados por execução. Use **um processo da API por volume de dados**. Execuções que estavam na fila sobrevivem a reinícios; uma execução interrompida é marcada como falha, mantendo o histórico e permitindo nova tentativa. O processamento tem limite de duas horas, 100000 quadros e 16 megapixels por quadro.

A API aceita `POST /api/sessions/{id}/runs` com `{"config": ...}`, devolvendo 202 e um identificador. `GET /api/sessions/{id}/runs`, `/api/runs/{id}`, `/summary`, `/samples?offset=0&limit=100`, `/at?time_ms=...`, `/export/csv`, `/export/jsonl` e `/previews/{frame_index}` permitem acompanhar e inspecionar. Recebimento, execução concluída e validade científica são condições diferentes. Uma segunda execução simultânea da mesma sessão retorna 409. Configuração inválida ou modelo ausente produz falha explícita; nunca sucesso com pontos fabricados.

Para uso por arquivos, dentro de `ml/itracker`:

```sh
uv run --frozen python itracker.py process --models ../../modelos/itracker --video /caminho/face.mp4 --events /caminho/sessao.json --config /caminho/analise.json --output /caminho/nova-execucao
```

O diretório de saída deve ser novo. O JSON original do Android é preservado e seu estado `concluida`/`interrompida` aparece no relatório. Este importador não o apresenta como manifesto v1 completo. A API verifica novamente os hashes recebidos antes de processar. O relatório registra hashes de entrada, configuração integral, versões e hashes dos modelos. A CLI também calcula hashes, mas não substitui a conferência de integridade do transporte.

## Configuração mínima

Informe explicitamente a correção para pixels armazenados; o espelhamento é desfeito **antes** da rotação horária. Metadados de rotação automática do container não são usados para duplicar essa correção.

```json
{"schema_version":1,"capture":{"rotation_degrees":0,"mirrored":false},"geometry":null,"synchronization":null,"calibration":null,"targets":[],"criteria":null,"export_features":false,"preview_frames":3}
```

Sem geometria, somente a previsão em centímetros no referencial do modelo está disponível. Sem sincronização suficiente, fase, tempo do estímulo e associação com alvos ficam ausentes. Não são inferidos a partir de índice/FPS, início do player ou strings de eventos antigos. A interface importa uma configuração JSON v1 e permite conferir o conteúdo antes de executar.

## Geometria medida

`geometry` contém `screen_width_px`, `screen_height_px`, `screen_width_mm`, `screen_height_mm`, `camera_x_mm`, `camera_y_mm`, `model_axes`, `measurement_evidence`, `axes_evidence`, `stimulus_rect`, `stimulus_width_px`, `stimulus_height_px`.

A tela usa a área ativa física na orientação da apresentação, origem no canto superior esquerdo. A câmera é medida em mm nessa mesma referência. `model_axes` é uma matriz 2×2 que orienta os centímetros do modelo nos eixos da tela. A transformação é `screen_mm = camera_mm + 10 * model_axes @ prediction_cm`, seguida da escala física por eixo. Não existe um perfil presumido de M52. A matriz e sua evidência precisam ser verificadas para a orientação usada; a referência oficial [cam2screen](https://github.com/CSAILVision/GazeCapture/blob/e4af90da3c4c9068fbce433fa648d1f9bc7a394b/code/cam2screen.m) também depende do aparelho e da orientação.

`stimulus_rect` é `[x,y,largura,altura]` em pixels da tela, cobrindo **o conteúdo do vídeo original inteiro**, após escala. Em letterbox, exclui as barras; em center-crop pode exceder o viewport. Inclua offsets de insets. O ponto no vídeo original é a transformação inversa desse retângulo. Coordenadas fora da tela ou vídeo são preservadas e sinalizadas, sem clamp. A interface exibe o ponto somente dentro do vídeo, mantendo seus valores numéricos.

## Correspondência temporal

`synchronization` contém:

- `method`, `evidence` e `event_clock`: descrição e referência da medição, e relógio comum das apresentações e alvos;
- `anchors`: pelo menos três pares estritamente crescentes `{"camera_ns":...,"event_ns":...}`. `camera_ns` deriva do **PTS × time base**, sem remover o PTS inicial;
- `measurement_error_ms`: limite de incerteza medido pelo método; `max_error_ms`: critério escolhido antes da avaliação;
- `presented_frames`: registros `{"event_ns":...,"media_time_ms":...,"duration_ms":...}` para quadros renderizados. `media_duration_ms` opcional distingue a duração no vídeo original da permanência na tela em caso de pausa/buffering.

A pipeline ajusta uma transformação afim entre relógios, relata deriva em ppm, residual máximo e a soma conservadora do residual com a incerteza declarada. Rejeita a associação se exceder o critério e não extrapola além dos anchors. Associa uma amostra ao quadro efetivamente apresentado que cobre aquele instante, limitado à sua duração e ao próximo registro. O timestamp exportado é o tempo de mídia desse quadro, não uma interpolação por FPS. Lacunas ficam explícitas. Na reprodução pelo webapp, só há sobreposição nos intervalos de mídia declarados e com amostras associadas.

Esses registros devem vir de uma medição do aparelho; escrever `evidence` não demonstra por si só que a sincronização é válida. Os eventos legados de VideoView/Choreographer **não** são automaticamente convertidos nesses registros. Coletas novas usam a instrumentação descrita em [coleta instrumentada](coleta-instrumentada.md). Coletas antigas permitem testar detecção/inferência, mas exigem evidência adicional ou nova coleta para análise sincronizada. A instrumentação nova não altera evidências de coletas antigas.

## Alvos, calibração e critérios

`targets` é uma lista de intervalos não sobrepostos `{"phase":"calibration" ou "validation","start_ns":...,"end_ns":...,"x_px":...,"y_px":...}`. Tempos estão no relógio de eventos indicado em `synchronization`; alvos estão em pixels físicos da tela. Forneça somente os intervalos de fixação aproveitados conforme o protocolo, já excluindo transições. Sem associação temporal aceita, nenhum quadro é usado para ajuste ou avaliação.

`calibration` define explicitamente `kernel` (`linear`/`rbf`), `C`, `epsilon`, `gamma`, `min_samples` e `min_targets`. Não há parâmetros científicos presumidos. Dois SVRs usam as 128 features de `relufc2`; a padronização é ajustada **somente** sobre calibração. As features, scaler e SVRs podem ser reconstruídos com os originais, configuração e modelos identificados; os modelos Python não são desserializados de arquivos externos. O baseline bruto permanece disponível. Poucos dados geram `insufficient_calibration`.

A validação só mede erro: média, mediana, P95 em pixels, média em cm quando há dimensões físicas, denominadores e exclusões por variante. `criteria` opcional contém `max_mean_error_px` e `max_invalid_fraction`; ausência gera critério não avaliado. O relatório não afirma precisão científica nem aprovação do piloto apenas porque a execução terminou. A proporção global de quadros sem inferência é separada das exclusões da validação.

## Pré-processamento e inspeção

O detector é Face Landmarker float16 v1, com SHA-256 fixado. Rejeita ausência de rosto e múltiplos rostos. Usa quadrado do conjunto de landmarks com fator 1,1 para rosto e fator 1,8 ao redor dos landmarks de cada olho; o lado é anatômico após desfazer o espelhamento. Recortes que alcançam as bordas repetem o pixel de borda. Redimensiona para 224×224 bilinear, subtrai a média oficial em BGR 0–255 e gera NCHW float32. O grid segue o arredondamento MATLAB e achatamento por linhas da [referência oficial](https://github.com/CSAILVision/GazeCapture/blob/e4af90da3c4c9068fbce433fa648d1f9bc7a394b/code/faceGridFromFaceRect.m).

As três médias `.mat` foram comparadas numericamente com os `binaryproto` oficiais nesta implementação: diferença máxima zero, sem inversão de canais. A configuração Caffe não contém normalização por 255. Isso não torna os recortes MediaPipe equivalentes às detecções Apple de treinamento. Recortes válidos são disponibilizados como imagens locais para inspeção pelo pesquisador, com índice e fase do quadro; quando possível, a seleção cobre calibração, estímulo e validação. Não publique imagens ou vídeos identificáveis no GitHub.

## Saídas e verificação

`samples.jsonl` mantém um registro por quadro, inclusive inválidos, PTS/base originais, fase, tempo associado, motivo de falha, previsão bruta, coordenadas baseline/calibradas, flags de posição e caixas dos recortes. `samples.csv` apresenta os mesmos valores essenciais em colunas; ausentes ficam vazios. `summary.json` registra proveniência, parâmetros, sincronização, calibração, métricas, duração e vazão. As features são exportadas somente se solicitadas, mas sempre estão disponíveis durante o ajuste.

Os testes automatizados cobrem timestamps irregulares, transformações e limites temporais, geometria com barras e pontos externos, grid, bordas, separação entre ajuste/validação, exportação dos inválidos, fila, repetição e falhas. Uma coleta piloto no M52 ainda deve verificar medidas, orientação, recortes, relação entre relógios/apresentação e erro com critérios escolhidos pelo pesquisador. Isso é validação empírica pendente, não algo que o software pode fabricar.

Uma [configuração mínima para importação](exemplos-contrato/analise-minima.json) está disponível; confira a orientação antes de usá-la. Para obter os tipos, campos e limites exatos: `uv run --directory ml/itracker --frozen python itracker.py config-schema`. O formato é validado por Pydantic, rejeitando campos desconhecidos, números não finitos, matrizes singulares, alvos sobrepostos e relógios não crescentes.

## Registro desta implementação (02/11/2026)

A execução local de uma gravação recebida produziu **1553 registros e 1553 previsões brutas**, sem falhas de detecção nessa gravação, em **144,4 segundos** (10,75 quadros/s). A correção de orientação de 270° foi inspecionada visualmente; o processamento usou espelhamento desativado. Foram inspecionados rosto e ambos os olhos nos primeiros recortes. Nenhuma imagem, identificador de participante ou gravação foi adicionada ao repositório. A execução não tinha medidas físicas nem correspondência temporal verificável: não produziu coordenadas do estímulo, calibração ou erro espacial e não constitui validação científica.

O caso completo de geometria, anchors, apresentações, calibração separada e validação foi exercitado com vídeo e medidas **sintéticos**, incluindo pontos fora do estímulo e preservação dos inválidos. A integração em container usa o Caffe e o MediaPipe reais também para confirmar a condição sem rosto. Os testes não substituem a coleta instrumentada nem estabelecem precisão no M52.

A verificação integrada final também processou oito quadros derivados de uma imagem real usando os modelos reais no container, combinados com geometria, anchors e alvos explicitamente sintéticos: confirmou ajuste SVR, dois quadros reservados para validação, consulta temporal, recortes e exportação. A seleção de uma amostra e a sobreposição calibrada foram conferidas no navegador. O histórico e os resultados persistiram após recriar os containers de teste. Esses números verificam o fluxo técnico e não são métricas de precisão de uma coleta sincronizada.

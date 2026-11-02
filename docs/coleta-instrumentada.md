# Coleta instrumentada e piloto de estimativa do olhar

O fluxo implementado é **experimento → Android → arquivos íntegros → preparação da análise → inferência → calibração e validação → inspeção**. O iTracker usa os pesos oficiais congelados. A precisão no aparelho e o erro temporal precisam de medição; a execução dos testes de software não substitui esse piloto.

## Operação

1. Instale o APK atualizado, prepare o experimento e realize uma nova coleta com o celular em tela inteira. O protocolo mantém cinco posições de calibração, repetidas duas vezes, e cinco posições distintas para validação. As durações continuam provisórias.
2. Abra **Experimento → Coletas → Processar e consultar olhar → Preparar análise a partir desta coleta**.
3. Informe a largura e a altura físicas da **área ativa** da tela em mm, na orientação usada; a posição do centro da câmera a partir do canto superior esquerdo; os eixos do modelo e como foram conferidos. A posição vertical pode ser negativa. Não use DPI nominal ou dimensões do corpo do aparelho como medida da tela.
4. Meça no aparelho a incerteza temporal total e registre método, evidência e limite de aceitação. Inclua exposição/rolling shutter, apresentação no display, callbacks de renderização e submissão dos alvos. A precisão de uma leitura de relógio não mede esses efeitos. Valores declarados pelo operador continuam sujeitos à conferência experimental.
5. Escolha a janela a excluir após cada troca de alvo, os parâmetros SVR, a quantidade mínima de amostras/posições e os limites de erro/perdas **antes** de examinar a validação. O formulário fornece propostas editáveis para o piloto; elas não são valores cientificamente validados.
6. Gere a configuração, confira as pendências e execute. Há configurações parciais úteis para inspeção bruta; elas não ganham sincronização ou geometria presumidas. Os registros antigos continuam disponíveis para importação manual.
7. Inspecione os recortes, compare baseline e calibração nos alvos separados, confira erro médio/mediana/P95, perdas e pontos fora da tela. Repita em sessões e participantes independentes antes de generalizar a precisão.

Critério de entrega do piloto: uma coleta real com correspondência temporal medida, coordenadas sobre o estímulo, recortes conferidos e erros apresentados em alvos que não participaram do ajuste. Não foi executada coleta instrumentada em aparelho nesta implementação.

## Contrato de instrumentação Android

O pacote continua com `face.mp4` e `sessao.json`, enviados pela API com tamanho/hash verificados. O JSON novo declara `schema_version: 2`; não é o manifesto de coleta proposto no contrato v1. Os eventos históricos são preservados. Os novos eventos têm `relogio: "frameTimeNanos"` (base monotônica de `System.nanoTime`) e `dados` contendo um objeto JSON serializado:

| Evento | Campos em `dados` | Significado |
| --- | --- | --- |
| `camera_info_v1` | `rotation_degrees`, `mirrored`, `width`, `height`, `timestamp_source_realtime`, `pts_origin_sensor_ns` | Geometria dos pixels YUV e capacidade declarada do relógio da câmera. |
| `camera_frame_v1` | `pts_us`, `assigned_pts_us`, `sensor_ns`, `clock_error_ns` | Um evento por amostra efetivamente codificada/escrita. `tempo_nanos` relaciona o timestamp do sensor ao relógio dos alvos e do player. |
| `display_v1` | `screen_width_px`, `screen_height_px`, `manufacturer`, `model`, `sdk` | Dimensões da tela e identificação técnica do aparelho. Não contém dimensões físicas presumidas. |
| `stimulus_geometry_v1` | `x_px`, `y_px`, `width_px`, `height_px`, `video_width_px`, `video_height_px`, `rotation_degrees` | Retângulo real da Surface do player em coordenadas da tela, incluindo os offsets das barras/insets. O player usa ajuste proporcional com barras e preserva áudio. |
| `stimulus_timing_v1` | `media_pts_us` | PTS dos quadros do arquivo de estímulo, ordenados por apresentação. Permitem distinguir quadros consecutivos de lacunas de callbacks. |
| `presented_frame_v1` | `media_time_us` | PTS de mídia e instante monotônico reportados pelo callback do codec ao renderizar na Surface. Não é `currentPosition` nem um horário de renderização planejado. |
| `target_v1` | `phase`, `x_px`, `y_px`, `duration_ms`, `committed` | Centro do alvo na tela e instante de submissão do frame. `committed` usa frame-commit com aceleração de hardware, disponível a partir da API 29. |

A captura usa CameraX ImageAnalysis e codificação H.264 baseline por MediaCodec, sem áudio da câmera. Copia os planos YUV respeitando strides e atribui explicitamente o PTS a partir do timestamp da imagem. Após finalizar o muxer, relê os timestamps armazenados com MediaExtractor e os associa, em ordem, às amostras escritas. Assim, a normalização feita pelo MP4 não é confundida com a origem temporal do sensor. O perfil baseline evita reordenação por B-frames. A gravação só é considerada finalizada após conferir essa correspondência.

Quando o encoder não dispõe de entrada, o quadro não é codificado e nenhum PTS é fabricado. CameraX pode descartar imagens antes do analyzer: os resultados descrevem os quadros gravados, não a totalidade das exposições do sensor. A execução em aparelho precisa conferir vazão, consumo, estabilidade e interrupções do encoder YUV.

A conversão sensor → monotônico usa leituras limitantes de elapsed-realtime antes/depois de System.nanoTime por imagem. A associação automática é desabilitada quando a câmera não declara `SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME`. O erro numérico da leitura e a quantização em microssegundos são somados à incerteza empírica informada pelo operador.

Frame-commit e callback do codec representam etapas da renderização; não certificam por si só o instante de emissão de luz do display. A configuração só recebe sincronização automática após informar a medição temporal. Em Android anterior à API 29 ou sem registros de submissão dos alvos, a calibração/validação automática fica indisponível; a inferência bruta permanece utilizável. A coleta interrompe ao sair da Activity e não retoma gravações após recriação.

## Preparação no servidor

`POST /api/sessions/{id}/analysis-config` recebe `{"settings": ...}` e devolve `config`, `issues` e `ready_for_pilot`. Verifica o hash do JSON original antes de executar o preparador no ambiente da pipeline. Não altera arquivos originais nem inicia inferência. Configuração completa significa pronta para executar um piloto, sem afirmar validade científica.

As medidas têm o seguinte esquema (todos os números abaixo são **sintéticos**, destinados somente a demonstrar o formato):

```json
{
  "physical": {
    "screen_width_mm": 100, "screen_height_mm": 200,
    "camera_x_mm": 50, "camera_y_mm": 0,
    "model_axes": [[1, 0], [0, -1]],
    "measurement_evidence": "exemplo sintético",
    "axes_evidence": "exemplo sintético"
  },
  "timing": {
    "measurement_error_ms": 2, "max_error_ms": 5,
    "evidence": "exemplo sintético"
  },
  "settling_ms": 500,
  "calibration": {
    "kernel": "linear", "C": 100, "epsilon": 1, "gamma": 0.01,
    "min_samples": 30, "min_targets": 5
  },
  "criteria": {"max_mean_error_px": 100, "max_invalid_fraction": 0.2}
}
```

O preparador ordena os registros por seus tempos originais, rejeita duplicatas, relógios incompatíveis, PTS não crescentes, alvos sobrepostos e uso das mesmas posições em calibração/validação. Retira o intervalo de acomodação escolhido de cada alvo. Não usa as strings antigas de alvos nem o callback histórico de início do vídeo para fabricar associações.

Cada par consecutivo de callbacks só delimita um intervalo associado quando também corresponde a quadros consecutivos do arquivo de estímulo. Saltos deixam uma lacuna; não se presume que o quadro anterior permaneceu visível quando um callback pode ter faltado. O tempo de mídia vem do listener de metadados do renderer e é associado ao PTS interno do codec antes da liberação do buffer. Só o callback de renderização confirma a associação; o deslocamento interno de stream do Media3 não é exportado como tempo do estímulo. `duration_ms` representa tempo de parede; `media_duration_ms` representa a extensão no vídeo original. Esses valores divergem durante pausas/buffering e não são intercambiáveis. A consulta da sobreposição usa a duração de mídia. O último quadro não recebe duração presumida sem callback sucessor; callbacks ausentes permanecem lacunas.

Uso por arquivos, na raiz:

```sh
uv run --directory ml/itracker --frozen python itracker.py prepare --events /caminho/sessao.json --settings /caminho/medidas.json
```

O JSON retornado contém `config`, utilizável com o comando `process` documentado em [pipeline.md](pipeline.md). As saídas mantêm hashes, configuração integral, previsões brutas/calibradas, denominadores e a indicação de validação empírica pendente.

## Referências e limites

- [MediaCodec.OnFrameRenderedListener](https://developer.android.com/reference/android/media/MediaCodec.OnFrameRenderedListener): callback e significado dos timestamps da renderização.
- [SENSOR_INFO_TIMESTAMP_SOURCE](https://developer.android.com/reference/android/hardware/camera2/CameraCharacteristics#SENSOR_INFO_TIMESTAMP_SOURCE): compatibilidade do timestamp da câmera.
- [Frame commit](https://developer.android.com/reference/android/view/ViewTreeObserver#registerFrameCommitCallback(java.lang.Runnable)): submissão para swap chain, distinta de apresentação física.
- [Eye Tracking for Everyone](https://arxiv.org/pdf/1606.05814): o iTracker prevê coordenadas relativas à câmera e avalia erro em dados próprios. Os recortes MediaPipe usados aqui não equivalem ao detector Apple original, e a calibração atual usa features `relufc2`; a implementação é uma adaptação a validar, sem promessa dos números do artigo.

## Verificação de software desta entrega

Foram executados build do APK, testes unitários e lint Android; testes da pipeline e da API; build/typecheck do webapp e inicialização em containers separados. A integração pelo servidor recebeu 30 quadros de vídeo gerados a partir de uma imagem pública do OpenCV, com relógios, alvos e dimensões explicitamente sintéticos. Executou os modelos reais, ajustou cinco posições de calibração, avaliou posições separadas e verificou consulta temporal e exportações. Isso verifica o fluxo técnico, sem medir precisão em um participante ou substituir o teste da captura no aparelho.

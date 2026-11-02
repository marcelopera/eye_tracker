# Núcleo iTracker Caffe

A pipeline experimental agora decodifica vídeos, detecta rosto/olhos com MediaPipe, prepara os tensores, executa o Caffe e exporta previsões por quadro. Também suporta sincronização por anchors medidos, conversão espacial com geometria explícita, calibração SVR e métricas em alvos separados. A API e o webapp permitem executar e inspecionar as análises. Consulte a [operação e configuração completas](../../docs/pipeline.md).

Os resultados científicos dependem das medidas físicas, correspondência temporal e validação em aparelho. Coletas antigas sem esses dados podem gerar inferência bruta, sem coordenadas sincronizadas do estímulo.

O modelo e as médias pertencem aos autores do GazeCapture, cuja [licença](https://github.com/CSAILVision/GazeCapture/blob/e4af90da3c4c9068fbce433fa648d1f9bc7a394b/LICENSE.md) restringe uso e redistribuição e exige citação. Antes de baixar ou usar, confira a licença. Os SHA-256 são fingerprints calculados localmente no estudo do plano, não checksums publicados pelos autores. Os arquivos não são incluídos no repositório ou na imagem.

Com Python 3.12 e uv, nesta pasta:

```sh
uv sync --frozen --group dev
uv run --frozen python -m pytest
uv run --frozen python itracker.py download --models ../../modelos/itracker
uv run --frozen python itracker.py smoke --models ../../modelos/itracker
```

`smoke` usa apenas zeros e verifica a execução, não a precisão nem o pré-processamento. Para inferência experimental, `infer --models ../../modelos/itracker --input entrada.npz` recebe quatro arrays float32 finitos: `face`, `left` e `right` com forma `(1,3,224,224)`, e `grid` com forma `(1,625)`. Devem já estar no formato e escala esperados pelo Caffe; não há conversão nem subtração de médias neste comando. A saída JSON inclui `prediction_cm` da camada `fc3`, 128 `features` de `relufc2`, revisão e hash dos pesos. O comando `process` aplica o pré-processamento descrito na documentação; os recortes adaptados precisam de avaliação no aparelho.

Em Docker, da mesma pasta, usando um diretório de modelos local já baixado:

```sh
docker build -t eye-tracker-itracker .
docker run --rm -v "$(realpath ../../modelos/itracker):/models:ro" eye-tracker-itracker smoke --models /models
```

Também é possível baixar com o container usando um volume gravável e `download --models /models`. O código confere o SHA-256 antes de usar os dois arquivos da rede e falha quando ausentes ou alterados. As três médias são verificadas e aplicadas no comando `process`.

## Inspeção inicial de vídeo

`uv run --frozen python itracker.py inspect-video --video face.mp4 --output quadros.jsonl --rotation 0` decodifica o primeiro fluxo de vídeo e escreve um registro por quadro em JSONL. Informe a rotação horária necessária para deixá-lo em pé e acrescente `--mirrored` apenas se os pixels armazenados estiverem espelhados; o espelhamento é desfeito antes da rotação. O comando não modifica o vídeo e só publica a saída após a decodificação completa. O PTS inteiro e a base de tempo racional `[numerador, denominador]` são os informados pelo decodificador, inclusive `null` se ausentes; o índice não é usado para estimar tempo.

Este diagnóstico **não executa detecção nem inferência**. Cada linha marca a previsão como indisponível e o tempo do estímulo como não comprovado. Ele pode ser usado em coletas antigas para inspecionar a decodificação, mas não valida sincronização, orientação, recortes ou precisão em imagens reais. A geometria, a associação temporal e os demais passos da issue 16 continuam pendentes.

## Renderizar demonstração

Com uma execução concluída em modo demonstração e `ffprobe` disponível no PATH:

```sh
uv run --frozen python demonstration.py \
  --camera face.mp4 --stimulus estimulo.mp4 \
  --results resultados --output demonstracao.mp4
```

O renderizador usa a configuração e as amostras da execução, sem rodar a rede novamente. Gera H.264 em 1440 × 896, sem áudio nem cabeçalho superior, com estímulo, marcador, câmera/recortes sincronizados e pipeline. Respeita a rotação de exibição e os timestamps variáveis do estímulo; não preenche intervalos sem amostra nem força pontos para dentro da imagem. A saída é publicada atomicamente, e a ausência de calibração ou pontos associados produz erro explícito. O webapp executa inferência e renderização em uma única solicitação.

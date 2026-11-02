# ADR 0001: iTracker pré-treinado no servidor

Estado: proposta para revisão. Data: 2026-11-02. Issue: #12.

## Contexto

O plano de iTracker substitui a descrição anterior de processamento baseado apenas em MediaPipe. A decisão anterior mencionada no plano não está presente na main; sua referência histórica está no [plano](../plano-itracker-pretreinado.md). O Android grava vídeo e eventos, mas ainda não fornece sincronização comprovada nem geometria física suficiente para converter o olhar em pontos do estímulo.

## Decisão proposta

Executar após a coleta, no servidor e inicialmente em CPU, o modelo Caffe oficial iTracker com pesos congelados `itracker25x_iter_92000.caffemodel`, na revisão `e4af90da3c4c9068fbce433fa648d1f9bc7a394b` do GazeCapture. MediaPipe Face Landmarker localiza rosto e olhos; não se presume que seus recortes equivalham aos detectores originais. Uma variante opcional ajustará SVRs por sessão usando as 128 features `relufc2`, somente com dados de calibração. A previsão sem calibração permanece disponível. Não há treinamento da rede, aumentação na inferência nem ajuste por dispositivo nesta proposta.

A entrada inicial é um pacote local por arquivos, conforme o [contrato proposto](../contrato-pipeline-v1.md); API, upload e painel não são dependências. Arquivos oficiais de terceiros são obtidos separadamente e verificados, sem redistribuição neste repositório ou em imagens publicadas. Sua licença restringe o uso e exige citação: consulte a [licença oficial](https://github.com/CSAILVision/GazeCapture/blob/e4af90da3c4c9068fbce433fa648d1f9bc7a394b/LICENSE.md).

## Consequências

Os pesos publicados não garantem precisão no aparelho ou na população desta coleta. É necessário validar recortes, sincronização, geometria e resultados com dados reais; parâmetros de calibração e critérios de aceitação dependem do pesquisador. Sessões antigas não adquirem sincronização ou geometria por inferência. O contrato e os marcos de validação precisam de revisão antes da execução das etapas seguintes.
